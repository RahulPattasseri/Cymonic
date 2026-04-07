"""
main.py  —  Next-Gen AI Expense Auditor (FastAPI Backend)
----------------------------------------------------------
Endpoints:
  GET  /              — serves the HTML frontend
  POST /register      — create a new user account
  POST /login         — authenticate a registered user
  POST /audit         — full AI audit with fraud check, tax classifier, market benchmarking
  POST /clarify       — AI clarification chatbot for flagged expenses
  POST /upload-policy — cache a custom policy PDF
  GET  /fraud-report  — recent submission history
  GET  /health        — health check

Run with:
  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import uvicorn

from ocr_extractor      import extract_receipt_text
from policy_parser      import extract_policy_text, SAMPLE_POLICY
from llm_auditor        import run_full_audit
from fraud_detector     import check_fraud, record_submission, get_fraud_report
from tax_classifier     import classify_tax
from market_benchmarker import get_market_context
from auth               import register_user, login_user


# ── APP SETUP ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Next-Gen AI Expense Auditor",
    description="Fraud detection · VAT recovery · Market benchmarking · AI chat clarification",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cached_policy_text: Optional[str] = None
_cached_policy_name: Optional[str] = None

POLICY_CACHE_FILE = os.path.join(os.path.dirname(__file__), "policy_cache.txt")
POLICY_NAME_FILE  = os.path.join(os.path.dirname(__file__), "policy_name.txt")

# Load previously saved policy on startup
def _load_cached_policy():
    global _cached_policy_text, _cached_policy_name
    if os.path.exists(POLICY_CACHE_FILE):
        with open(POLICY_CACHE_FILE, "r", encoding="utf-8") as f:
            _cached_policy_text = f.read()
    if os.path.exists(POLICY_NAME_FILE):
        with open(POLICY_NAME_FILE, "r", encoding="utf-8") as f:
            _cached_policy_name = f.read().strip()

_load_cached_policy()


# ── RESPONSE MODELS ───────────────────────────────────────────────────────────

class AuditResponse(BaseModel):
    # Receipt fields
    merchant_name:      Optional[str]
    date:               Optional[str]
    total_amount:       Optional[float]
    currency:           Optional[str]
    # Core audit
    category:           str
    status:             str           # "Approved" | "Flagged" | "Rejected"
    policy_rule:        str
    explanation:        str
    # Fraud detection
    fraud_warning:      Optional[str] = None
    is_duplicate:       bool = False
    is_split_bill:      bool = False
    # Tax / VAT
    vat_reclaimable:    bool = False
    vat_number:         Optional[str] = None
    estimated_reclaim:  float = 0.0
    tax_type:           Optional[str] = None
    reclaim_note:       Optional[str] = None
    # Market benchmarking
    fair_market_rate:   Optional[float] = None
    market_context:     Optional[str] = None
    over_market:        bool = False
    # Debug
    raw_ocr_text:       str


class RegisterRequest(BaseModel):
    name:     str
    email:    str
    password: str

class LoginRequest(BaseModel):
    email:    str
    password: str

class ClarifyMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str

class ClarifyRequest(BaseModel):
    expense_context: str          # JSON string of the audit result
    conversation:    List[ClarifyMessage]

class ClarifyResponse(BaseModel):
    reply: str


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serve the ExpenseAuditor HTML frontend."""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0", "message": "Next-Gen Expense Auditor running"}


@app.post("/register")
def register(req: RegisterRequest):
    """Register a new user account. Stores credentials in users.db."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    result = register_user(req.name.strip(), req.email.strip(), req.password)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return {"token": result["token"], "name": result["name"], "email": result["email"]}


@app.post("/login")
def login(req: LoginRequest):
    """Authenticate a registered user. Returns error if not registered or wrong password."""
    result = login_user(req.email.strip(), req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["error"])
    return {"token": result["token"], "name": result["name"], "email": result["email"]}


@app.get("/policy-status")
def policy_status():
    """Return whether a custom policy is active and its name."""
    if _cached_policy_text:
        return {
            "active": True,
            "policy_name": _cached_policy_name or "Custom Policy",
            "characters": len(_cached_policy_text),
        }
    return {
        "active": False,
        "policy_name": "ACME CORP — Default Sample Policy",
        "characters": len(SAMPLE_POLICY),
    }


@app.post("/upload-policy")
async def upload_policy(policy_pdf: UploadFile = File(...)):
    """Upload a custom company policy PDF, replacing any previous policy."""
    global _cached_policy_text, _cached_policy_name
    if not policy_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Policy must be a PDF file.")
    policy_bytes = await policy_pdf.read()
    try:
        extracted = extract_policy_text(policy_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Replace in memory
    _cached_policy_text = extracted
    _cached_policy_name = policy_pdf.filename

    # Persist to disk so it survives restarts
    with open(POLICY_CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(extracted)
    with open(POLICY_NAME_FILE, "w", encoding="utf-8") as f:
        f.write(policy_pdf.filename)

    return {
        "message": f"Policy '{policy_pdf.filename}' uploaded and saved. Previous policy replaced.",
        "policy_name": policy_pdf.filename,
        "characters_extracted": len(extracted),
    }


@app.delete("/clear-policy")
def clear_policy():
    """Remove the custom policy and revert to the built-in sample policy."""
    global _cached_policy_text, _cached_policy_name
    _cached_policy_text = None
    _cached_policy_name = None
    if os.path.exists(POLICY_CACHE_FILE):
        os.remove(POLICY_CACHE_FILE)
    if os.path.exists(POLICY_NAME_FILE):
        os.remove(POLICY_NAME_FILE)
    return {"message": "Custom policy removed. Reverted to built-in sample policy."}


@app.get("/fraud-report")
def fraud_report(limit: int = 50):
    """Return the last N submissions for fraud analysis."""
    return {"submissions": get_fraud_report(limit)}


@app.post("/clarify", response_model=ClarifyResponse)
async def clarify_expense(req: ClarifyRequest):
    """
    AI clarification chatbot for flagged expenses.
    Accepts the expense context + conversation history and returns the next AI reply.
    """
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = f"""You are a friendly but professional corporate expense compliance assistant.
You are helping an employee understand why their expense was flagged and collecting clarification.
Be concise. Ask ONE specific question per reply. Once you have enough context, give a clear recommendation.

Expense details:
{req.expense_context}

Your goals:
1. Explain clearly why the expense was flagged (be specific about the rule)
2. Ask for the missing information that would resolve the flag (e.g., "Were there alcohol charges?", "How many attendees?")
3. Based on their answer, provide a final recommendation: Approve / Escalate to Manager / Reject
"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.conversation:
        messages.append({"role": msg.role, "content": msg.content})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
            max_tokens=300,
        )
        return ClarifyResponse(reply=response.choices[0].message.content.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clarification AI failed: {str(e)}")


@app.post("/audit", response_model=AuditResponse)
async def audit_expense(
    receipt: UploadFile = File(...),
    business_purpose: str = Form(...),
    employee: str = Form("anonymous"),
    policy_pdf: Optional[UploadFile] = File(None),
):
    """
    Full Next-Gen audit pipeline:
      1. Fraud check  (duplicate / split-bill detection)
      2. OCR          (extract text from receipt)
      3. Tax classify (VAT/GST reclaim detection)
      4. Policy load
      5. Market bench (fair market rate for city/category)
      6. LLM audit    (policy check with enriched context)
      7. Record       (persist to fraud DB)
    """
    # ── Validate receipt file ─────────────────────────────────────────────────
    allowed = {".jpg", ".jpeg", ".png", ".pdf"}
    ext = "." + receipt.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    receipt_bytes = await receipt.read()
    if not receipt_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # ── 1. FRAUD CHECK ────────────────────────────────────────────────────────
    # We do a preliminary fraud scan before expensive OCR/LLM calls
    # We'll refine with merchant/amount after OCR
    preliminary_hash_check = check_fraud(
        employee=employee,
        merchant=None,
        amount=None,
        expense_date=None,
        receipt_bytes=receipt_bytes,
    )

    if preliminary_hash_check["is_duplicate"]:
        raise HTTPException(
            status_code=409,
            detail=preliminary_hash_check["details"],
        )

    # ── 2. OCR ────────────────────────────────────────────────────────────────
    try:
        raw_ocr_text = extract_receipt_text(receipt_bytes, receipt.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"OCR failed: {str(e)}")

    if not raw_ocr_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from receipt.")

    # ── 3. TAX CLASSIFICATION ─────────────────────────────────────────────────
    tax_info = classify_tax(raw_ocr_text)

    # ── 4. LOAD POLICY ────────────────────────────────────────────────────────
    global _cached_policy_text
    policy_text = None
    if policy_pdf:
        policy_bytes_data = await policy_pdf.read()
        try:
            policy_text = extract_policy_text(policy_bytes_data)
            _cached_policy_text = policy_text
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    elif _cached_policy_text:
        policy_text = _cached_policy_text
    else:
        policy_text = SAMPLE_POLICY

    # ── 5. LLM AUDIT (first pass to get category+amounts) ────────────────────
    try:
        result = run_full_audit(
            raw_ocr_text=raw_ocr_text,
            business_purpose=business_purpose,
            policy_text=policy_text,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI audit failed: {str(e)}")

    receipt_data = result["receipt"]
    audit_data   = result["audit"]

    merchant  = receipt_data.get("merchant_name")
    amount    = receipt_data.get("total_amount")
    exp_date  = receipt_data.get("date")
    category  = audit_data.get("category", "Unknown")

    # ── 5b. Extract city from OCR for market benchmarking ────────────────────
    # Simple heuristic: look for common city patterns in OCR text
    city = tax_info.get("country", "")  # use country as fallback city hint
    for line in raw_ocr_text.split("\n"):
        line = line.strip()
        if any(keyword in line.lower() for keyword in [
            "san francisco", "new york", "london", "chicago", "los angeles",
            "seattle", "boston", "paris", "berlin", "tokyo", "singapore",
            "mumbai", "dubai", "sydney", "toronto", "austin", "denver",
        ]):
            city = line
            break

    # ── 6. MARKET BENCHMARKING ────────────────────────────────────────────────
    market_info = get_market_context(
        category=category,
        city=city if city else merchant,
        expense_date=exp_date,
        amount=amount,
    )

    # ── 7. FULL FRAUD CHECK (now with merchant + amount from OCR) ─────────────
    fraud_info = check_fraud(
        employee=employee,
        merchant=merchant,
        amount=amount,
        expense_date=exp_date,
        receipt_bytes=receipt_bytes,
    )

    # Downgrade status if split-bill detected
    status = audit_data.get("status", "Flagged")
    fraud_warning = None
    if fraud_info["is_split_bill"]:
        status = "Flagged"
        fraud_warning = fraud_info["details"]
    elif fraud_info["is_duplicate"]:
        status = "Rejected"
        fraud_warning = fraud_info["details"]

    # Upgrade explanation if over market rate
    explanation = audit_data.get("explanation", "")
    if market_info["over_market"] and status == "Approved":
        status = "Flagged"
        explanation += f" Additionally: {market_info['market_context']}"

    # ── 8. RECORD SUBMISSION ──────────────────────────────────────────────────
    record_submission(
        employee=employee,
        merchant=merchant,
        amount=amount,
        expense_date=exp_date,
        receipt_bytes=receipt_bytes,
        category=category,
        status=status,
    )

    return AuditResponse(
        merchant_name     = merchant,
        date              = exp_date,
        total_amount      = amount,
        currency          = receipt_data.get("currency", "USD"),
        category          = category,
        status            = status,
        policy_rule       = audit_data.get("policy_rule", ""),
        explanation       = explanation,
        fraud_warning     = fraud_warning,
        is_duplicate      = fraud_info["is_duplicate"],
        is_split_bill     = fraud_info["is_split_bill"],
        vat_reclaimable   = tax_info["vat_reclaimable"],
        vat_number        = tax_info["vat_number"],
        estimated_reclaim = tax_info["estimated_reclaim"],
        tax_type          = tax_info["tax_type"],
        reclaim_note      = tax_info["reclaim_note"],
        fair_market_rate  = market_info["fair_market_rate"],
        market_context    = market_info["market_context"],
        over_market       = market_info["over_market"],
        raw_ocr_text      = raw_ocr_text,
    )


# ── RUN ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
