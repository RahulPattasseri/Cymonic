"""
tax_classifier.py
-----------------
Automatically identifies VAT/GST details on a receipt and determines
whether the company can reclaim the tax from a government.

Companies lose millions globally by failing to reclaim VAT on international
business travel. This module flags eligible receipts.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── Country VAT/GST reclaimability rules ─────────────────────────────────────
# Standard rates and reclaim eligibility for business expenses
COUNTRY_VAT_RULES = {
    "UK":          {"rate": 0.20, "reclaimable": True,  "name": "VAT"},
    "GB":          {"rate": 0.20, "reclaimable": True,  "name": "VAT"},
    "DE":          {"rate": 0.19, "reclaimable": True,  "name": "VAT"},
    "FR":          {"rate": 0.20, "reclaimable": True,  "name": "TVA"},
    "IN":          {"rate": 0.18, "reclaimable": True,  "name": "GST"},
    "AU":          {"rate": 0.10, "reclaimable": True,  "name": "GST"},
    "CA":          {"rate": 0.05, "reclaimable": True,  "name": "GST/HST"},
    "SG":          {"rate": 0.09, "reclaimable": True,  "name": "GST"},
    "US":          {"rate": 0.00, "reclaimable": False, "name": "Sales Tax"},
    "DEFAULT":     {"rate": 0.0,  "reclaimable": False, "name": "Tax"},
}


def classify_tax(raw_ocr_text: str, country_hint: Optional[str] = None) -> dict:
    """
    Use an LLM to extract tax details and determine VAT reclaimability.

    Args:
        raw_ocr_text:  OCR text from the receipt
        country_hint:  Optional country code from parsed receipt (e.g. "UK")

    Returns:
        {
            "vat_number":       str,    # Tax registration number on receipt
            "tax_amount":       float,  # Tax amount on the receipt
            "country":          str,    # Country code detected
            "is_tax_invoice":   bool,   # Does receipt qualify as a tax invoice?
            "vat_reclaimable":  bool,   # Can company reclaim this?
            "estimated_reclaim": float, # Estimated reclaim amount USD
            "tax_type":         str,    # "VAT" | "GST" | "Sales Tax" etc.
            "reclaim_note":     str,    # Human-readable explanation
        }
    """
    system_prompt = """You are a global tax compliance specialist.
Analyse raw OCR text from a receipt and extract tax information.
Return ONLY a JSON object with these exact keys:
- vat_number (string: the VAT/GST registration number on the receipt, or null)
- tax_amount (number: the tax amount shown on receipt, or null)
- country_code (string: 2-letter ISO country code where the purchase was made, or "US" if unclear)
- is_tax_invoice (boolean: does this receipt contain a valid VAT/GST number and itemised details qualifying it as a tax invoice?)
- currency (string: 3-letter currency code)

Return raw JSON only. No markdown."""

    user_prompt = f"""Receipt OCR text:
---
{raw_ocr_text[:2000]}
---
Extract tax information and return JSON."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        llm_data = json.loads(raw)
    except Exception:
        llm_data = {
            "vat_number": None,
            "tax_amount": None,
            "country_code": country_hint or "US",
            "is_tax_invoice": False,
            "currency": "USD",
        }

    country_code = (llm_data.get("country_code") or country_hint or "US").upper()
    rules = COUNTRY_VAT_RULES.get(country_code, COUNTRY_VAT_RULES["DEFAULT"])

    tax_amount = llm_data.get("tax_amount") or 0.0
    is_tax_invoice = llm_data.get("is_tax_invoice", False)
    vat_number = llm_data.get("vat_number")

    # Only reclaimable if: country supports it + receipt is a valid tax invoice + has VAT number
    vat_reclaimable = (
        rules["reclaimable"]
        and is_tax_invoice
        and vat_number is not None
        and tax_amount > 0
    )

    if vat_reclaimable:
        reclaim_note = (
            f"💰 Eligible for {rules['name']} reclaim. "
            f"Tax ID: {vat_number}. "
            f"Estimated reclaim: ${tax_amount:.2f} ({int(rules['rate']*100)}% {rules['name']})."
        )
    elif rules["reclaimable"] and not is_tax_invoice:
        reclaim_note = (
            f"Receipt from {country_code} may be eligible for {rules['name']} reclaim "
            f"but does not appear to be a valid tax invoice (missing VAT number or itemisation)."
        )
    else:
        reclaim_note = ""

    return {
        "vat_number":        vat_number,
        "tax_amount":        tax_amount,
        "country":           country_code,
        "is_tax_invoice":    is_tax_invoice,
        "vat_reclaimable":   vat_reclaimable,
        "estimated_reclaim": tax_amount if vat_reclaimable else 0.0,
        "tax_type":          rules["name"],
        "reclaim_note":      reclaim_note,
    }
