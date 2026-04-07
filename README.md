# ExpenseAuditor AI — Intelligent Expense Compliance Platform

---

## The Problem

Enterprise expense management is broken. Finance teams manually review hundreds of receipts every month, catching policy violations too late, missing VAT reclaim opportunities worth thousands of dollars, and having no way to detect split-bill fraud until damage is done. Employees submit expenses without clear feedback, leading to slow reimbursements, policy disputes, and audit risk — all from a process that should be automated.

---

## The Solution

ExpenseAuditor AI is a full-stack, AI-powered expense auditing platform that instantly analyses every receipt against your company's policy, flags fraud, recovers VAT, and benchmarks costs against real-world market rates — all in a single submission.

### Core capabilities

**Instant AI audit with policy enforcement**
Employees upload a receipt (JPG, PNG, or PDF) and write a brief business purpose. The system runs Tesseract OCR to extract the receipt text, then uses a two-step GPT-4 pipeline: a fast `gpt-4o-mini` pass parses the receipt into structured fields (merchant, date, amount, currency), and a `gpt-4o` pass reads those fields alongside the full policy document to render a verdict — Approved, Flagged, or Rejected — with a one-sentence explanation that cites the exact policy rule applied.

**Fraud detection (duplicate + split-bill)**
Every receipt is fingerprinted with an MD5 hash. Exact re-submissions are blocked immediately before any OCR or LLM cost is incurred. A second check scans the database for similar amounts at the same merchant within a 24-hour window per employee, detecting split-bill fraud where transactions are broken up to stay under per-item policy limits.

**VAT / GST reclaim identification**
A dedicated tax classifier LLM call reads the receipt for VAT registration numbers, tax amounts, and country of purchase. It cross-references a reclaimability ruleset covering UK (20% VAT), Germany (19%), France (20%), India (18%), Australia (10%), Canada (5% GST/HST), and Singapore (9% GST) to flag receipts where the company can file a tax reclaim, with an estimated reclaim amount shown in the result.

**Dynamic market benchmarking ("Living Policy")**
Submitted amounts are compared against fair-market rates for the city and expense category using a tiered city model (Tier 1: SF, NYC, London, Tokyo; Tier 2: Chicago, Berlin, Toronto; Tier 3: Bangalore, Dallas, Prague). A hotel at $220/night in San Francisco is treated differently from the same amount in Phoenix. Expenses more than 20% above market automatically escalate from Approved to Flagged, even if they fall within the stated policy dollar limit.

**AI clarification chatbot**
Flagged expenses open a GPT-4 powered chat panel where the employee can explain context. The AI asks one targeted question per reply (e.g. "Were there alcohol charges on this receipt?") and provides a final recommendation — Approve, Escalate to Manager, or Reject — based on the conversation.

**User authentication and submission history**
Employees register and log in with hashed credentials stored in SQLite. Every audited submission is persisted to a fraud database with merchant, amount, date, category, and status. A fraud report endpoint exposes the full submission history for finance team review.

**Custom policy management**
Finance admins upload their company's expense policy as a PDF. The system extracts the text with PyPDF and persists it to disk so it survives server restarts. All future audits use the custom policy instead of the built-in default. Admins can replace or remove the policy at any time from the Policy page.

---

## Tech Stack

### Programming languages
- Python 3.11 (backend)
- JavaScript ES2022 (frontend — vanilla, no framework)
- HTML5 / CSS3

### Frameworks and libraries
- **FastAPI** — REST API backend with automatic OpenAPI docs
- **Uvicorn** — ASGI server for FastAPI
- **Pydantic v2** — request and response data validation
- **Pillow** — image loading and grayscale preprocessing for OCR
- **Pytesseract** — Python wrapper for Tesseract OCR engine
- **PyPDF** — PDF text extraction for receipts and policy documents
- **pdf2image** — page rasterisation for scanned PDFs
- **python-dotenv** — environment variable management

### Databases
- **SQLite** — two local databases:
  - `users.db` — user accounts and session tokens
  - `expenses.db` — submission history for fraud detection

### APIs and third-party tools
- **OpenAI API** — `gpt-4o-mini` for receipt field parsing and tax classification; `gpt-4o` for policy auditing and clarification chat
- **Tesseract OCR** — open-source OCR engine (system dependency)
- **Amadeus API** *(optional)* — live hotel rate lookup for market benchmarking; falls back gracefully to the built-in city-tier model when not configured

### Frontend
- Single-page HTML application served directly by FastAPI at `/`
- Inter font (Google Fonts)
- No external JS frameworks — all state managed with vanilla JS

---

## Setup Instructions

### Prerequisites

Install **Tesseract OCR** on your system before anything else:

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr

# Windows
# Download the installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
```

### 1. Clone the repository

```bash
git clone https://github.com/your-username/expense-auditor.git
cd expense-auditor
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-your-openai-key-here

# Optional — only needed for live hotel market rates
AMADEUS_API_KEY=your-amadeus-key
AMADEUS_API_SECRET=your-amadeus-secret
```

Get your OpenAI key at: https://platform.openai.com/api-keys

### 5. Run the application

```bash
uvicorn main:app --reload --port 8000
```

Open your browser at **http://localhost:8000**

The HTML frontend is served automatically — no separate frontend server needed.

### 6. (Optional) View the API documentation

FastAPI generates interactive API docs automatically:

```
http://localhost:8000/docs
```

---

## Running the Test Suite

Test the AI audit logic without needing real receipt images:

```bash
python test_cases.py
```

This runs 6 pre-built scenarios (dinner within limit, steakhouse with alcohol, hotel at limit, luxury suite over limit, office supplies requiring approval, airport rideshare) and prints the verdict, category, policy rule, and explanation for each.

---

## Project Structure

```
expense-auditor/
├── main.py                # FastAPI backend — all endpoints and audit pipeline
├── ocr_extractor.py       # Tesseract OCR for JPG, PNG, and PDF receipts
├── policy_parser.py       # PyPDF policy extraction + built-in sample policy
├── llm_auditor.py         # Two-step GPT-4 parse + audit pipeline
├── fraud_detector.py      # Duplicate hash check + split-bill detection
├── tax_classifier.py      # VAT/GST identification and reclaim flagging
├── market_benchmarker.py  # City-tier market rate benchmarking + Amadeus API
├── auth.py                # User registration, login, and session management
├── index.html             # Full SPA frontend served by FastAPI
├── test_cases.py          # Six test scenarios with simulated OCR text
├── requirements.txt       # Python dependencies
├── .env                   # API keys — never commit this file
├── users.db               # SQLite: user accounts (auto-created on first run)
└── expenses.db            # SQLite: submission history (auto-created on first run)
```

---

## Audit Pipeline — How a Receipt is Processed

```
Upload receipt
      │
      ▼
1. Fraud pre-check   ── Duplicate MD5 hash? → Block immediately
      │
      ▼
2. OCR extraction    ── Tesseract reads JPG/PNG/PDF → raw text
      │
      ▼
3. Tax classification ── GPT-4o-mini extracts VAT number, tax amount, country
      │
      ▼
4. Policy load       ── Custom PDF policy or built-in ACME default
      │
      ▼
5. LLM audit         ── GPT-4o-mini parses fields → GPT-4o audits vs policy
      │
      ▼
6. Market benchmark  ── Compare amount to city-tier fair market rate
      │
      ▼
7. Fraud post-check  ── Split-bill detection (same merchant + amount + 24h window)
      │
      ▼
8. Record + respond  ── Persist to DB, return verdict to frontend
```

---

## Sample Test Results

| Scenario | Amount | Expected verdict |
|---|---|---|
| Team dinner, no alcohol | $84.76 | ✅ Approved |
| Steakhouse + bottle of wine | $443.33 | ❌ Rejected |
| Marriott at $220/night | $603.75 | ✅ Approved |
| Four Seasons suite at $450/night | $1,355.00 | ❌ Rejected |
| Office supplies over $50 | $79.89 | ⚠️ Flagged |
| Uber from airport | $36.48 | ✅ Approved |
