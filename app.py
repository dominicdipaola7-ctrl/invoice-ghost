import os, json, stripe
from flask import Flask, request, jsonify, send_file, render_template, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from invoice_ai import parse_invoice_description
from pdf_generator import generate_pdf
import io

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')
# stripe.api_key set inside routes

limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

FREE_LIMIT = 3

def get_usage():
    return session.get('invoice_count', 0)

def increment_usage():
    session['invoice_count'] = session.get('invoice_count', 0) + 1
    session.modified = True

def is_pro():
    return session.get('pro', False)

@app.route('/')
def index():
    return render_template('index.html',
        stripe_key=os.getenv('STRIPE_SECRET_KEY', ''),
        price_id=os.getenv('STRIPE_PRICE_ID', ''),
        usage=get_usage(), pro=is_pro(), free_limit=FREE_LIMIT)

@app.route('/generate', methods=['POST'])
@limiter.limit("20 per hour")
def generate():
    if not is_pro() and get_usage() >= FREE_LIMIT:
        return jsonify({'error': 'free_limit', 'message': 'Daily free limit reached. Upgrade to Pro for unlimited invoices.'}), 429

    data = request.get_json()
    description = (data.get('description') or '').strip()
    if not description or len(description) < 10:
        return jsonify({'error': 'invalid', 'message': 'Please provide a work description.'}), 400

    try:
        invoice_data = parse_invoice_description(
            description,
            freelancer_name=data.get('freelancer_name', ''),
            client_name=data.get('client_name', '')
        )
        if data.get('brand_color'):
            invoice_data['brand_color'] = data['brand_color']
        return jsonify({'success': True, 'invoice': invoice_data})
    except Exception as e:
        return jsonify({'error': 'ai_error', 'message': str(e)}), 500

@app.route('/download', methods=['POST'])
@limiter.limit("20 per hour")
def download():
    if not is_pro() and get_usage() >= FREE_LIMIT:
        return jsonify({'error': 'free_limit'}), 429

    data = request.get_json()
    invoice_data = data.get('invoice', {})
    brand_color = data.get('brand_color', '#1A1A2E')
    if not invoice_data:
        return jsonify({'error': 'No invoice data'}), 400

    try:
        pdf_bytes = generate_pdf(invoice_data, brand_color=brand_color)
        if not is_pro():
            increment_usage()
        inv_num = invoice_data.get('invoice_number', 'invoice').replace('/', '-')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=f"{inv_num}.pdf")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create-checkout', methods=['POST'])
def create_checkout():
    try:
        base = os.getenv('BASE_URL', request.host_url.rstrip('/'))
        session_obj = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{'price': os.getenv('STRIPE_PRICE_ID'), 'quantity': 1}],
            success_url=f"{base}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/",
        )
        return jsonify({'url': session_obj.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/success')
def success():
    sid = request.args.get('session_id')
    if sid:
        try:
            s = stripe.checkout.Session.retrieve(sid)
            if s.payment_status == 'paid':
                session['pro'] = True
        except Exception:
            pass
    return render_template('index.html',
        stripe_key=os.getenv('STRIPE_SECRET_KEY', ''),
        price_id=os.getenv('STRIPE_PRICE_ID', ''),
        usage=get_usage(), pro=True, free_limit=FREE_LIMIT, upgraded=True)

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig = request.headers.get('Stripe-Signature', '')
    try:
        event = stripe.Webhook.construct_event(payload, sig, os.getenv('STRIPE_WEBHOOK_SECRET', ''))
        if event['type'] == 'checkout.session.completed':
            pass  # Could set user pro status in a DB here
    except Exception:
        return '', 400
    return '', 200

@app.route('/status')
def status():
    return jsonify({'usage': get_usage(), 'pro': is_pro(), 'limit': FREE_LIMIT})

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/checkout', methods=['POST'])
def checkout():
    import stripe
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    price_id = os.environ.get('STRIPE_PRICE_ID')
    domain = os.environ.get('DOMAIN', 'http://localhost:5000')
    try:
        data = request.get_json() or {}
        email = data.get('email', '')
        params = {
            'mode': 'subscription',
            'line_items': [{'price': price_id, 'quantity': 1}],
            'success_url': f'{domain}/?upgrade=success',
            'cancel_url': f'{domain}/?upgrade=cancelled',
            'allow_promotion_codes': True,
        }
        if email:
            params['customer_email'] = email
        checkout_session = stripe.checkout.Session.create(**params)
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

