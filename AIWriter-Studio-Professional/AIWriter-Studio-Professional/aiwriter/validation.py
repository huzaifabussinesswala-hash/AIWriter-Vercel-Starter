"""Server-side input validation and small security helpers."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128


def normalize_email(value) -> str:
    return (value or "").strip().lower()


def validate_name(value) -> tuple:
    name = " ".join((value or "").split())
    if not name:
        return name, "Please enter your name."
    if len(name) > 100:
        return name, "Name must be 100 characters or fewer."
    if any(not ch.isprintable() for ch in name):
        return name, "Name contains invalid characters."
    return name, None


def validate_email(value) -> tuple:
    email = normalize_email(value)
    if not email:
        return email, "Please enter your email address."
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return email, "Please enter a valid email address."
    return email, None


def validate_password(value):
    """Return an error message or None."""
    password = value or ""
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Password must be {MAX_PASSWORD} characters or fewer."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one number."
    return None


def password_fingerprint(password_hash: str) -> str:
    """Short value stored in the session so a password change invalidates other sessions."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def is_safe_next(target) -> bool:
    """Only allow same-site relative redirects."""
    if not target or not isinstance(target, str):
        return False
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return False
    if any(ord(ch) < 32 for ch in target):
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc
