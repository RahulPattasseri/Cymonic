"""
app.py  —  Streamlit Frontend for the AI Expense Auditor
---------------------------------------------------------
Run with:
  streamlit run app.py

This assumes the FastAPI backend is running on http://localhost:8000
"""

import streamlit as st
import requests
import json

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Expense Auditor",
    page_icon="🧾",
    layout="centered",
)

BACKEND_URL = "http://localhost:8000"

# ── HEADER ────────────────────────────────────────────────────────────────────
st.title("🧾 AI Expense Auditor")
st.markdown(
    "Upload a receipt and let the AI check it against your company policy automatically."
)
st.divider()


# ── SIDEBAR: POLICY UPLOAD ────────────────────────────────────────────────────
with st.sidebar:
    st.header("📋 Company Policy")
    st.markdown(
        "Upload your expense policy PDF once. "
        "It will be used for all audits in this session."
    )
    
    policy_file = st.file_uploader(
        "Upload policy PDF",
        type=["pdf"],
        help="Your company's expense reimbursement policy document",
    )
    
    if policy_file and st.button("Upload Policy", type="primary"):
        with st.spinner("Reading policy..."):
            response = requests.post(
                f"{BACKEND_URL}/upload-policy",
                files={"policy_pdf": (policy_file.name, policy_file.read(), "application/pdf")},
            )
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Policy loaded ({data['characters_extracted']:,} characters)")
                st.session_state["policy_loaded"] = True
            else:
                st.error(f"Failed: {response.json().get('detail', 'Unknown error')}")
    
    if not st.session_state.get("policy_loaded"):
        st.info("💡 No policy uploaded — using the built-in sample policy for demo.")
    
    st.divider()
    st.caption("Built with FastAPI · Tesseract OCR · OpenAI GPT-4")


# ── MAIN FORM ─────────────────────────────────────────────────────────────────
st.subheader("Submit an Expense")

col1, col2 = st.columns(2)

with col1:
    receipt_file = st.file_uploader(
        "Receipt file *",
        type=["jpg", "jpeg", "png", "pdf"],
        help="Photo or scan of your receipt",
    )

with col2:
    # Show a preview if an image was uploaded
    if receipt_file and receipt_file.type.startswith("image"):
        st.image(receipt_file, caption="Receipt preview", use_column_width=True)

business_purpose = st.text_area(
    "Business Purpose *",
    placeholder="e.g. Client dinner with Acme Corp team to discuss Q3 contract renewal",
    height=100,
    help="Clearly describe why this expense was incurred",
)

submit = st.button("🔍 Audit This Expense", type="primary", use_container_width=True)


# ── SUBMIT & DISPLAY RESULT ───────────────────────────────────────────────────
if submit:
    # Validate inputs
    if not receipt_file:
        st.error("Please upload a receipt file.")
        st.stop()
    if not business_purpose.strip():
        st.error("Please enter a business purpose.")
        st.stop()
    
    with st.spinner("Running AI audit... this takes a few seconds"):
        try:
            response = requests.post(
                f"{BACKEND_URL}/audit",
                files={"receipt": (receipt_file.name, receipt_file.read(), receipt_file.type)},
                data={"business_purpose": business_purpose},
                timeout=60,
            )
        except requests.exceptions.ConnectionError:
            st.error(
                "Cannot connect to the backend. "
                "Make sure FastAPI is running: `uvicorn main:app --reload`"
            )
            st.stop()
    
    if response.status_code != 200:
        st.error(f"Audit failed: {response.json().get('detail', 'Unknown error')}")
        st.stop()
    
    data = response.json()
    
    # ── RESULT CARD ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Audit Result")
    
    status = data["status"]
    status_emoji = {"Approved": "✅", "Flagged": "⚠️", "Rejected": "❌"}.get(status, "❓")
    status_color = {"Approved": "green",  "Flagged": "orange", "Rejected": "red"}.get(status, "gray")
    
    # Big status banner
    st.markdown(
        f"<h2 style='color:{status_color};'>{status_emoji} {status}</h2>",
        unsafe_allow_html=True,
    )
    
    # Explanation sentence
    st.info(f"**{data['explanation']}**")
    
    # Two-column receipt details
    st.subheader("Receipt Details")
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.metric("Merchant",  data.get("merchant_name") or "—")
        st.metric("Date",      data.get("date") or "—")
    
    with col_b:
        amount = data.get("total_amount")
        currency = data.get("currency", "USD")
        st.metric("Total Amount", f"{currency} {amount:.2f}" if amount else "—")
        st.metric("Category", data.get("category") or "—")
    
    # Policy rule used
    st.subheader("Policy Rule Applied")
    st.code(data.get("policy_rule", "—"), language=None)
    
    # Expandable raw OCR text for debugging
    with st.expander("🔍 Raw OCR text (for debugging)"):
        st.text(data.get("raw_ocr_text", "—"))
    
    # Download JSON result
    st.download_button(
        label="⬇️ Download audit result (JSON)",
        data=json.dumps(data, indent=2),
        file_name="audit_result.json",
        mime="application/json",
    )
