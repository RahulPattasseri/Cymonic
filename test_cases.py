"""
test_cases.py
-------------
Sample test cases for the Expense Auditor.
Run these to verify your system works correctly without needing a real receipt image.

Usage:
  1. Start the FastAPI backend:  uvicorn main:app --reload
  2. Run this file:              python test_cases.py

Each test case injects raw OCR text directly into the LLM pipeline
(bypassing Tesseract) so you can test the AI logic independently.
"""

import json
from llm_auditor import run_full_audit
from policy_parser import SAMPLE_POLICY


# ── SAMPLE OCR TEXTS ──────────────────────────────────────────────────────────
# These simulate what Tesseract would extract from real receipts

RECEIPT_DINNER_OK = """
THE ITALIAN PLACE
123 Main Street, San Francisco CA 94105
Tel: (415) 555-0100

Date: 03/15/2024   Time: 7:34 PM
Table: 12           Server: Maria

2x Pasta Carbonara          $36.00
1x Caesar Salad             $14.00
2x Sparkling Water           $8.00
1x Tiramisu                 $9.00

Subtotal:                   $67.00
Tax (8.5%):                  $5.70
Tip (18%):                  $12.06

TOTAL:                      $84.76

VISA ending 4242
Auth: 773421
"""

RECEIPT_DINNER_OVER_LIMIT = """
PRIME STEAKHOUSE
One Market Plaza, San Francisco CA 94105

Date: 03/20/2024
Party of 2

Wagyu Ribeye (2x)          $180.00
Lobster Bisque              $28.00
Bottle of Cabernet          $95.00
Dessert Assortment          $42.00

Subtotal:                  $345.00
Tax:                        $29.33
Tip:                        $69.00

TOTAL:                     $443.33

AMEX ending 5005
"""

RECEIPT_HOTEL_OK = """
MARRIOTT DOWNTOWN
200 Market St
San Francisco, CA 94105

Guest: John Smith
Check In:  March 18, 2024
Check Out: March 20, 2024
Nights: 2

Room Rate (2 nights):     $440.00
  ($220/night)
Parking:                   $60.00
Room Service:              $45.00

Taxes & Fees:              $58.75

TOTAL DUE:                $603.75

Charged to: VISA xxxx-1234
"""

RECEIPT_HOTEL_OVER_LIMIT = """
FOUR SEASONS HOTEL
757 Market St, San Francisco

FOLIO - John Smith
Mar 15-17, 2024 (2 nights)

Suite Deluxe - 2 nights:    $900.00
  ($450/night)
Spa services:                $250.00
Minibar:                      $85.00
Restaurant:                  $120.00

Total:                     $1,355.00
"""

RECEIPT_OFFICE_SUPPLIES = """
OFFICE DEPOT #1847
456 Mission St, SF

Date: 2024-03-10   11:42 AM

Printer Paper (2 reams)    $24.98
Black Ink Cartridge        $32.99
Sticky Notes (3-pack)       $8.99
Pens - Box of 12            $6.49

Subtotal:                  $73.45
Tax:                        $6.44

TOTAL:                     $79.89

Cash
"""

RECEIPT_UBER = """
Uber Trip Receipt
Trip on March 22, 2024

From: SFO International Airport
To: Moscone Center, San Francisco

Distance: 14.2 miles
Duration: 28 min

Base fare:    $12.00
Distance:     $18.40
Surge (1.2x):  $6.08

Total charged to Visa: $36.48
"""


# ── TEST RUNNER ───────────────────────────────────────────────────────────────

def run_test(name: str, ocr_text: str, business_purpose: str):
    """Run one test case and print formatted results."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"Purpose: {business_purpose}")
    print("-" * 60)
    
    result = run_full_audit(
        raw_ocr_text=ocr_text,
        business_purpose=business_purpose,
        policy_text=SAMPLE_POLICY,
    )
    
    receipt = result["receipt"]
    audit   = result["audit"]
    
    print(f"Merchant:  {receipt.get('merchant_name')}")
    print(f"Date:      {receipt.get('date')}")
    print(f"Amount:    {receipt.get('currency')} {receipt.get('total_amount')}")
    print()
    print(f"Category:  {audit.get('category')}")
    status = audit.get('status')
    emoji  = {"Approved": "✅", "Flagged": "⚠️", "Rejected": "❌"}.get(status, "❓")
    print(f"Status:    {emoji} {status}")
    print(f"Rule:      {audit.get('policy_rule')}")
    print(f"Decision:  {audit.get('explanation')}")


if __name__ == "__main__":
    print("AI EXPENSE AUDITOR — TEST SUITE")
    print("Using sample policy (ACME Corp)")
    
    run_test(
        name="Dinner within limit — EXPECT: Approved",
        ocr_text=RECEIPT_DINNER_OK,
        business_purpose="Team dinner with 2 colleagues to debrief after client presentation",
    )
    
    run_test(
        name="Expensive steakhouse with alcohol — EXPECT: Rejected",
        ocr_text=RECEIPT_DINNER_OVER_LIMIT,
        business_purpose="Client dinner for contract negotiation",
    )
    
    run_test(
        name="Hotel within $250/night limit — EXPECT: Approved",
        ocr_text=RECEIPT_HOTEL_OK,
        business_purpose="2-night stay in SF for annual sales conference",
    )
    
    run_test(
        name="Luxury hotel suite over limit — EXPECT: Rejected",
        ocr_text=RECEIPT_HOTEL_OVER_LIMIT,
        business_purpose="Hotel stay during customer meeting",
    )
    
    run_test(
        name="Office supplies over $50 — EXPECT: Flagged (needs manager approval)",
        ocr_text=RECEIPT_OFFICE_SUPPLIES,
        business_purpose="Office supplies for home office setup",
    )
    
    run_test(
        name="Uber from airport — EXPECT: Approved",
        ocr_text=RECEIPT_UBER,
        business_purpose="Ride from SFO airport to Moscone Center for conference",
    )
    
    print(f"\n{'='*60}")
    print("All tests complete.")
