"""
fraud_detector.py
-----------------
Detects two types of expense fraud using a local SQLite database:

1. DUPLICATE RECEIPTS — same receipt bytes (MD5 hash) submitted again
2. SPLIT-BILL FRAUD  — same employee submits similar amounts at the same
                       merchant within a 24-hour window to stay under policy
                       limits (e.g., $150 dinner split into two $75 receipts)
"""

import hashlib
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")


# ── DATABASE SETUP ────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the submissions table if it doesn't already exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                employee      TEXT    NOT NULL,
                merchant      TEXT,
                amount        REAL,
                expense_date  TEXT,
                receipt_hash  TEXT    NOT NULL,
                category      TEXT,
                status        TEXT,
                submitted_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


# Initialise on module load
init_db()


# ── FRAUD CHECK ───────────────────────────────────────────────────────────────

def check_fraud(
    employee: str,
    merchant: Optional[str],
    amount: Optional[float],
    expense_date: Optional[str],
    receipt_bytes: bytes,
) -> dict:
    """
    Run pre-audit fraud checks.

    Returns:
        {
          "is_duplicate":  bool,   # exact same file submitted before
          "is_split_bill": bool,   # same employee/merchant/amount cluster in 24h
          "confidence":    str,    # "HIGH" | "MEDIUM" | "LOW"
          "details":       str,    # human-readable explanation
          "similar_count": int,    # how many similar submissions found
        }
    """
    receipt_hash = hashlib.md5(receipt_bytes).hexdigest()

    with _get_conn() as conn:
        # ── 1. Exact duplicate check ──────────────────────────────────────────
        dup = conn.execute(
            "SELECT id, submitted_at FROM submissions WHERE receipt_hash = ? AND employee = ?",
            (receipt_hash, employee),
        ).fetchone()

        if dup:
            return {
                "is_duplicate":  True,
                "is_split_bill": False,
                "confidence":    "HIGH",
                "details": (
                    f"⚠️ Duplicate receipt detected. This exact receipt was already "
                    f"submitted on {dup['submitted_at'][:10]}. Submission blocked."
                ),
                "similar_count": 1,
            }

        # ── 2. Split-bill detection ───────────────────────────────────────────
        if amount and merchant and expense_date:
            try:
                ref_date = datetime.fromisoformat(expense_date)
            except ValueError:
                ref_date = datetime.utcnow()

            window_start = (ref_date - timedelta(hours=24)).isoformat()
            window_end   = (ref_date + timedelta(hours=24)).isoformat()
            low_amount   = amount * 0.75
            high_amount  = amount * 1.25

            similar = conn.execute(
                """
                SELECT id, amount, submitted_at FROM submissions
                WHERE employee     = ?
                  AND merchant     LIKE ?
                  AND amount       BETWEEN ? AND ?
                  AND expense_date BETWEEN ? AND ?
                """,
                (employee, f"%{merchant[:10]}%", low_amount, high_amount,
                 window_start[:10], window_end[:10]),
            ).fetchall()

            if similar:
                total_known = sum(r["amount"] for r in similar) + amount
                return {
                    "is_duplicate":  False,
                    "is_split_bill": True,
                    "confidence":    "HIGH" if len(similar) >= 2 else "MEDIUM",
                    "details": (
                        f"🚨 Potential split-bill fraud: {len(similar)} similar "
                        f"submission(s) from '{merchant}' within 24 hours. "
                        f"Combined total: ${total_known:.2f}. "
                        f"This may indicate a split transaction to stay under policy limits."
                    ),
                    "similar_count": len(similar),
                }

    return {
        "is_duplicate":  False,
        "is_split_bill": False,
        "confidence":    "LOW",
        "details":       "",
        "similar_count": 0,
    }


# ── RECORD SUBMISSION ─────────────────────────────────────────────────────────

def record_submission(
    employee: str,
    merchant: Optional[str],
    amount: Optional[float],
    expense_date: Optional[str],
    receipt_bytes: bytes,
    category: str = "",
    status: str = "",
):
    """Persist a clean (non-duplicate) submission to the database."""
    receipt_hash = hashlib.md5(receipt_bytes).hexdigest()
    now = datetime.utcnow().isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO submissions
                (employee, merchant, amount, expense_date, receipt_hash,
                 category, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (employee, merchant, amount, expense_date,
             receipt_hash, category, status, now),
        )
        conn.commit()


# ── FRAUD REPORT ──────────────────────────────────────────────────────────────

def get_fraud_report(limit: int = 50) -> list:
    """Return recent submissions with flagged/rejected status for the report endpoint."""
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM submissions
            ORDER BY submitted_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
