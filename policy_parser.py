"""
policy_parser.py
----------------
Reads a company expense policy PDF and extracts its text content.
This text is later passed to the LLM so it can make policy-aware decisions.

The LLM will read the policy text and find rules relevant to
a specific expense (e.g. "Meals capped at $75 per person").
"""

import io
from pypdf import PdfReader


def extract_policy_text(policy_file_bytes: bytes) -> str:
    """
    Extract all text from the company policy PDF.
    
    Args:
        policy_file_bytes: raw bytes of the uploaded PDF
    
    Returns:
        Full text of the policy document as a single string
    
    Example output:
        "EXPENSE POLICY v2.3\\n\\nMeals: Up to $75 per person per meal.
         Alcohol is not reimbursable. Receipts required for all expenses
         over $25. Travel: Economy class only for flights under 6 hours..."
    """
    reader = PdfReader(io.BytesIO(policy_file_bytes))
    
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    
    full_text = "\n\n".join(pages_text)
    
    if not full_text.strip():
        raise ValueError(
            "Could not extract text from the policy PDF. "
            "Make sure it's a text-based PDF, not a scanned image."
        )
    
    return full_text.strip()


# ── SAMPLE POLICY ────────────────────────────────────────────────────────────
# Use this as a fallback / for testing when no PDF is uploaded.
# In production, always require a real policy PDF.

SAMPLE_POLICY = """
ACME CORP — EMPLOYEE EXPENSE POLICY (v3.1)

1. MEALS & ENTERTAINMENT
   - Daily meal limit: $75 per person (including tax and tip).
   - Team meals (3+ people): $50 per person.
   - Alcohol is NOT reimbursable under any circumstances.
   - Receipts are required for all meal expenses over $25.
   - Fast food / coffee under $15 may be submitted without a receipt.

2. TRAVEL
   - Flights: Economy class only for routes under 6 hours.
   - Business class allowed for routes over 6 hours with manager pre-approval.
   - Taxis / rideshares: reimbursed in full with receipt.
   - Personal vehicle mileage: $0.67 per mile (IRS standard rate).

3. LODGING
   - Hotel limit: $250 per night (excluding taxes and fees).
   - Airbnb is allowed; same $250 per night cap applies.
   - Suite upgrades are NOT reimbursable.

4. OFFICE SUPPLIES & EQUIPMENT
   - Supplies under $50: no pre-approval needed.
   - Equipment $50–$500: manager approval required.
   - Equipment over $500: VP approval required before purchase.

5. GENERAL RULES
   - All receipts must be submitted within 30 days of the expense.
   - Personal expenses mixed on a business receipt will be rejected.
   - Expenses must have a clear business purpose noted.
   - Duplicate submissions will result in disciplinary action.
"""
