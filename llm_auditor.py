"""
llm_auditor.py
--------------
The AI brain of the system. Makes two LLM calls:

  Step 1 — PARSE: Extract structured fields from raw OCR text
           (merchant, date, amount, currency)

  Step 2 — AUDIT: Given the parsed receipt + business purpose + policy,
           decide: Approved / Flagged / Rejected, with a one-line reason.

Why two calls?
  Separating parsing from decision-making makes each prompt simpler and
  the results more reliable. A single monolithic prompt tends to confuse
  the model and produce inconsistent output.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize the OpenAI client once at module load
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── STEP 1: PARSE RECEIPT ─────────────────────────────────────────────────────

def parse_receipt_fields(raw_ocr_text: str) -> dict:
    """
    Send raw OCR text to GPT-4 and ask it to extract key fields.
    Returns a clean Python dict with merchant, date, amount, currency.
    
    Args:
        raw_ocr_text: messy text from Tesseract (may include noise)
    
    Returns:
        {
            "merchant_name": "The Italian Place",
            "date": "2024-03-15",
            "total_amount": 68.50,
            "currency": "USD"
        }
    """
    system_prompt = """You are a receipt parser. 
Extract key fields from raw OCR text of a receipt.
Return ONLY a JSON object with these exact keys:
- merchant_name (string)
- date (string, format YYYY-MM-DD, or "unknown" if not found)
- total_amount (number, the final total including tax/tip, or null if not found)
- currency (string, 3-letter code like USD, EUR, GBP — default to USD if unclear)

Do not include any explanation or markdown. Return raw JSON only."""

    user_prompt = f"""Here is the raw OCR text from a receipt:

---
{raw_ocr_text}
---

Extract the fields and return JSON."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",          # Fast and cheap for parsing
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,                # Zero temperature = deterministic parsing
        max_tokens=200,
    )
    
    raw_json = response.choices[0].message.content.strip()
    
    # Strip markdown code fences if GPT adds them (e.g. ```json ... ```)
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]
    
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        # Fallback if parsing fails
        return {
            "merchant_name": "Unknown",
            "date": "unknown",
            "total_amount": None,
            "currency": "USD",
            "parse_error": raw_json,
        }


# ── STEP 2: AUDIT AGAINST POLICY ─────────────────────────────────────────────

def audit_expense(
    receipt_fields: dict,
    business_purpose: str,
    policy_text: str,
) -> dict:
    """
    Send the parsed receipt + business purpose + full policy to GPT-4.
    The model categorizes the expense and renders a verdict.
    
    Args:
        receipt_fields:   output from parse_receipt_fields()
        business_purpose: user's explanation (e.g. "Client dinner with Acme team")
        policy_text:      full text of the company policy PDF
    
    Returns:
        {
            "category": "Meals",
            "status": "Flagged",
            "policy_rule": "Meals capped at $75 per person; amount $68.50 is within limit but no receipt for alcohol.",
            "explanation": "..."
        }
    """
    system_prompt = """You are a corporate expense auditor AI.
You will receive:
1. Parsed receipt data (merchant, date, amount, currency)
2. Business purpose stated by the employee
3. Company expense policy text

Your job:
A. Categorize the expense into ONE of: Meals, Travel, Lodging, Office Supplies, Equipment, Other
B. Find the most relevant policy rule(s) for this category and amount
C. Render a verdict: Approved, Flagged, or Rejected
   - Approved: clearly within all policy limits
   - Flagged: borderline, needs manager review, or missing information
   - Rejected: clearly violates policy (over limit, prohibited item, missing receipt)
D. Write ONE sentence explaining the decision, citing the specific policy rule.

Return ONLY a JSON object with these exact keys:
- category (string)
- status (string: "Approved", "Flagged", or "Rejected")
- policy_rule (string: the specific rule you applied, quoted from policy)
- explanation (string: one sentence combining status + rule + amount)

No markdown. Raw JSON only."""

    user_prompt = f"""RECEIPT DATA:
{json.dumps(receipt_fields, indent=2)}

BUSINESS PURPOSE:
{business_purpose}

COMPANY EXPENSE POLICY:
{policy_text}

Audit this expense and return your JSON verdict."""

    response = client.chat.completions.create(
        model="gpt-4o",               # Use the smarter model for the actual decision
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
        max_tokens=400,
    )
    
    raw_json = response.choices[0].message.content.strip()
    
    # Strip markdown code fences
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]
    
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return {
            "category": "Unknown",
            "status": "Flagged",
            "policy_rule": "Could not parse AI response",
            "explanation": raw_json,
        }


# ── CONVENIENCE WRAPPER ───────────────────────────────────────────────────────

def run_full_audit(
    raw_ocr_text: str,
    business_purpose: str,
    policy_text: str,
) -> dict:
    """
    Full pipeline: OCR text → parse fields → audit → return combined result.
    
    This is the main function called by the FastAPI endpoint.
    
    Returns a combined dict with both parsed receipt data and the audit verdict.
    """
    # Step 1: Parse
    receipt_fields = parse_receipt_fields(raw_ocr_text)
    
    # Step 2: Audit
    audit_result = audit_expense(receipt_fields, business_purpose, policy_text)
    
    # Combine into one response object
    return {
        "receipt": receipt_fields,
        "audit": audit_result,
    }
