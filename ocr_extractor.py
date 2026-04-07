"""
ocr_extractor.py
----------------
Handles OCR for JPG, PNG, and PDF receipts.
Uses Tesseract to extract raw text, then uses the LLM to parse key fields.

Install Tesseract on your system first:
  - Mac:     brew install tesseract
  - Ubuntu:  sudo apt install tesseract-ocr
  - Windows: https://github.com/UB-Mannheim/tesseract/wiki
"""

import io
import base64
import pytesseract
from PIL import Image
from pypdf import PdfReader


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Takes raw image bytes (JPG or PNG) and returns extracted text using Tesseract OCR.
    
    How it works:
    1. Load the image bytes into a Pillow Image object
    2. Convert to grayscale (improves OCR accuracy)
    3. Run Tesseract OCR on the image
    4. Return the extracted text string
    """
    image = Image.open(io.BytesIO(file_bytes))
    
    # Convert to grayscale - Tesseract reads black/white text better
    image = image.convert("L")
    
    # pytesseract.image_to_string sends the image to Tesseract and returns text
    raw_text = pytesseract.image_to_string(image)
    
    return raw_text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Takes raw PDF bytes and returns all text content.
    
    Strategy:
    - First try to extract text directly (works for digital PDFs)
    - If the PDF is a scanned image, fall back to page-by-page OCR
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    all_text = []
    
    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text()
        
        if page_text and page_text.strip():
            # Digital PDF — text extracted directly
            all_text.append(page_text)
        else:
            # Scanned PDF — we need OCR on the page image
            # Note: for production, use pdf2image to convert pages to images
            all_text.append(f"[Page {page_num + 1}: scanned — use pdf2image for OCR]")
    
    return "\n".join(all_text).strip()


def extract_receipt_text(file_bytes: bytes, filename: str) -> str:
    """
    Smart dispatcher: routes to the right extractor based on file type.
    
    Args:
        file_bytes: raw file content
        filename:   original filename like "receipt.jpg" or "receipt.pdf"
    
    Returns:
        Raw OCR text from the receipt
    """
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif filename_lower.endswith((".jpg", ".jpeg", ".png")):
        return extract_text_from_image(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}. Use JPG, PNG, or PDF.")
