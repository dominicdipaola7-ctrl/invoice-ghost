import os
import anthropic
import json
import re
from datetime import date, timedelta

# client initialized inside functions

def parse_invoice_description(description: str, freelancer_name: str = "", client_name: str = "") -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    today = date.today()
    due_date = today + timedelta(days=30)

    prompt = f"""You are an invoice parsing assistant. Parse this freelance work description into a structured invoice JSON.

Work description: "{description}"
Freelancer name: "{freelancer_name or 'Freelancer'}"
Client name: "{client_name or 'Client'}"
Invoice date: {today.strftime('%B %d, %Y')}
Due date: {due_date.strftime('%B %d, %Y')}

Return ONLY valid JSON with this exact structure:
{{
  "invoice_number": "INV-{today.strftime('%Y%m%d')}-001",
  "invoice_date": "{today.strftime('%B %d, %Y')}",
  "due_date": "{due_date.strftime('%B %d, %Y')}",
  "freelancer_name": "string",
  "freelancer_email": "string or empty",
  "client_name": "string",
  "client_email": "string or empty",
  "line_items": [
    {{
      "description": "clear professional description of the work",
      "quantity": number,
      "unit": "hours or units or flat",
      "rate": number,
      "amount": number
    }}
  ],
  "subtotal": number,
  "tax_rate": 0,
  "tax_amount": 0,
  "total": number,
  "notes": "Professional thank you note or payment terms",
  "currency": "USD"
}}

Rules:
- Extract all line items mentioned (hours, flat fees, expenses, etc.)
- If hourly: quantity=hours, rate=hourly rate, amount=hours*rate
- If flat fee: quantity=1, unit="flat", rate=total amount
- Make descriptions professional and clear
- Calculate all amounts correctly
- notes should be a brief professional payment note
- Return ONLY the JSON, no other text"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return json.loads(raw)
