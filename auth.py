"""
auth.py
-------
User authentication using SQLite.
Stores registered users with hashed passwords.
Only registered users can sign in.
"""

import sqlite3
import hashlib
import os
import secrets
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db():
    """Create users table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                email        TEXT    NOT NULL UNIQUE,
                password_hash TEXT   NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                email      TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


init_users_db()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(name: str, email: str, password: str) -> dict:
    """
    Register a new user. Returns error if email already exists.
    """
    email = email.lower().strip()
    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters."}

    from datetime import datetime
    now = datetime.utcnow().isoformat()
    pw_hash = _hash_password(password)

    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, pw_hash, now),
            )
            conn.commit()
        token = _create_session(email)
        return {"success": True, "token": token, "name": name, "email": email}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "An account with this email already exists."}


def login_user(email: str, password: str) -> dict:
    """
    Authenticate a registered user. Returns error if not found or wrong password.
    """
    email = email.lower().strip()
    pw_hash = _hash_password(password)

    with _get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password_hash = ?",
            (email, pw_hash),
        ).fetchone()

    if not user:
        return {"success": False, "error": "Invalid email or password. Please register first."}

    token = _create_session(email)
    return {"success": True, "token": token, "name": user["name"], "email": email}


def _create_session(email: str) -> str:
    from datetime import datetime
    token = secrets.token_hex(32)
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, email, created_at) VALUES (?, ?, ?)",
            (token, email, now),
        )
        conn.commit()
    return token


def validate_session(token: str) -> Optional[str]:
    """Returns email if token is valid, else None."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT email FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    return row["email"] if row else None


def logout_user(token: str):
    """Invalidate a session token."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
