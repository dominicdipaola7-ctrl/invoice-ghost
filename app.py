import os, io
from flask import Flask, request, jsonify, send_file, render_template, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from invoice_ai import parse_invoice_description
from pdf_generator import generate_pdf

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
FREE_LIMIT = 3

def get_usage(): return session.get("invoice_count", 0)
def increment_usage():
    session["invoice_count"] = session.get("invoice_count", 0) + 1
    session.modified = True
def is_pro(): return session.get("pro", False)

@app.route("/")
def index():
    return render_template("index.html", usage=get_usage(), pro=is_pro(), free_limit=FREE_LIMIT, stripe_key=os.environ.get("STRIPE_SECRET_KEY",""), upgraded=request.args.get("upgrade")=="success")

@app.route("/generate", methods=["POST"])
@limiter.limit("20 per hour")
def generate():
    if not is_pro() and get_usage() >= FREE_LIMIT:
        return jsonify({"error": "free_limit", "message": "Daily free limit reached. Upgrade to Pro for unlimited invoices."}), 429
    data = request.get_json()
    description = (data.get("description") or "").strip()
    if not description or len(description) < 10:
        return jsonify({"error": "invalid", "message": "Please provide a work description."}), 400
    try:
        invoice_data = parse_invoice_description(
            description,
            freelancer_name=data.get("freelancer_name", ""),
            client_name=data.get("client_name", "")
        )
        if data.get("brand_color"):
            invoice_data["brand_color"] = data["brand_color"]
        increment_usage()
        return jsonify({"success": True, "invoice": invoice_data})
    except Exception as e:
        return jsonify({"error": "ai_error", "message": str(e)}), 500

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    invoice_data = data.get("invoice", {})
    try:
        pdf_bytes = generate_pdf(invoice_data)
        return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf",
            as_attachment=True, download_name=f"invoice-{invoice_data.get(chr(39)+'invoice_number'+chr(39), 'ghost')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/checkout", methods=["POST"])
def checkout():
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    price_id = os.environ.get("STRIPE_PRICE_ID")
    domain = os.environ.get("DOMAIN", "http://localhost:5000")
    if not stripe.api_key:
        return jsonify({"error": "Stripe not configured"}), 500
    if not price_id:
        return jsonify({"error": "No price ID configured"}), 500
    try:
        data = request.get_json() or {}
        email = data.get("email", "")
        params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{domain}/?upgrade=success",
            "cancel_url": f"{domain}/?upgrade=cancelled",
            "allow_promotion_codes": True,
        }
        if email:
            params["customer_email"] = email
        checkout_session = stripe.checkout.Session.create(**params)
        return jsonify({"url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    payload = request.get_data(as_text=True)
    sig = request.headers.get("Stripe-Signature")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
        if event["type"] == "checkout.session.completed":
            session["pro"] = True
    except Exception:
        pass
    return jsonify({"received": True})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=False, port=5000)
