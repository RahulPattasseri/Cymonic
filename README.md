# AI Expense Auditor

Automatically audit expense receipts against company policy using OCR + GPT-4.

---

## Project Structure

```
expense_auditor/
├── main.py            # FastAPI backend (the server)
├── ocr_extractor.py   # Tesseract OCR logic
├── policy_parser.py   # PDF policy reader + sample policy
├── llm_auditor.py     # GPT-4 parse + audit pipeline
├── app.py             # Streamlit frontend (the UI)
├── test_cases.py      # Test cases (no real receipt needed)
├── requirements.txt   # Python dependencies
└── .env               # Your API keys (never commit this!)
```

---

## Setup (step by step)

### 1. Install system dependencies

**Tesseract OCR** (required for image receipts):
```bash
# Mac
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr

# Windows
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Create a Python virtual environment
```bash
cd expense_auditor
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
```

### 3. Install Python packages
```bash
pip install -r requirements.txt
```

### 4. Set your OpenAI API key
Edit the `.env` file:
```
OPENAI_API_KEY=sk-your-real-key-here
```
Get a key at: https://platform.openai.com/api-keys

---

## Running the App

You need TWO terminal windows open at the same time.

**Terminal 1 — Start the backend:**
```bash
uvicorn main:app --reload --port 8000
```
Visit http://localhost:8000/docs to see the API documentation.

**Terminal 2 — Start the frontend:**
```bash
streamlit run app.py
```
Visit http://localhost:8501 to use the UI.

---

## Running Tests (no real receipt needed)

```bash
python test_cases.py
```

This runs 6 test cases with simulated OCR text and prints the verdict for each.

---

## How It Works

1. **User uploads** a receipt (JPG/PNG/PDF) and writes a business purpose
2. **Tesseract OCR** reads the receipt and extracts raw text
3. **GPT-4o-mini** parses the raw text → extracts merchant, date, amount, currency
4. **GPT-4o** reads the parsed receipt + business purpose + policy text
5. **GPT-4o** categorizes the expense and renders: Approved / Flagged / Rejected
6. The result is displayed in the Streamlit UI with the specific policy rule cited

---

## Sample Test Cases

| Scenario                        | Expected Result |
|---------------------------------|-----------------|
| $84 dinner for 2 (no alcohol)   | Approved        |
| $443 steak dinner with wine     | Rejected        |
| Hotel at $220/night             | Approved        |
| Hotel suite at $450/night       | Rejected        |
| Office supplies $79 (over $50)  | Flagged         |
| Uber ride from airport          | Approved        |

---

## Improving the System

- **Better OCR**: Add `pdf2image` to handle scanned PDFs
- **Database**: Store past audits in SQLite or PostgreSQL
- **Auth**: Add login so employees can only see their own expenses
- **Email**: Send audit results to managers via SendGrid
- **Batch processing**: Allow uploading multiple receipts at once
