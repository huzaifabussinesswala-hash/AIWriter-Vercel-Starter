"""Six-digit email OTP: generation, protected storage, delivery and verification."""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import mailer, repo

log = logging.getLogger(__name__)

OTP_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5

OK = "ok"
ALREADY_VERIFIED = "already_verified"
INVALID = "invalid"
EXPIRED = "expired"
LOCKED = "locked"
NO_CODE = "no_code"


class CooldownActive(Exception):
    def __init__(self, seconds: int):
        super().__init__(f"resend available in {seconds}s")
        self.seconds = seconds


@dataclass(frozen=True)
class CheckResult:
    status: str
    attempts_left: int = 0


def generate_code() -> str:
    """Cryptographically secure six-digit code (leading zeros preserved)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(secret_key: str, user_id: int, email: str, code: str) -> str:
    """HMAC the code with the server secret, binding it to this account and address."""
    message = f"{user_id}:{email}:{code}".encode()
    return hmac.new(secret_key.encode(), message, hashlib.sha256).hexdigest()


def cooldown_remaining(last_sent_at, now: datetime) -> int:
    if last_sent_at is None:
        return 0
    remaining = (last_sent_at + RESEND_COOLDOWN - now).total_seconds()
    return max(0, math.ceil(remaining))


def send_code(db, settings, user, *, now=None, enforce_cooldown=True) -> None:
    """Email a fresh code and store its hash; any earlier code stops working.

    The code is emailed first and stored only after delivery succeeds, so an SMTP failure
    never leaves a stored code the user cannot read. Raises CooldownActive or MailError.
    """
    now = now or datetime.now(timezone.utc)
    if enforce_cooldown:
        wait = cooldown_remaining(user.get("verification_last_sent_at"), now)
        if wait:
            raise CooldownActive(wait)

    code = generate_code()
    mailer.send_otp_email(settings, user["email"], user["name"], code)

    code_hash = hash_code(settings.secret_key, user["id"], user["email"], code)
    with db.connection() as conn:
        repo.store_verification(conn, user["id"], code_hash, now + OTP_TTL, now)


def check_code(db, settings, user_id: int, submitted: str, *, now=None) -> CheckResult:
    """Validate a submitted code, counting failed attempts atomically."""
    now = now or datetime.now(timezone.utc)
    with db.connection() as conn:
        if conn.lock_user(user_id) is None:
            return CheckResult(NO_CODE)
        user = repo.get_user_by_id(conn, user_id)

        if user["email_verified"]:
            return CheckResult(ALREADY_VERIFIED)
        if not user["verification_code_hash"] or user["verification_expires_at"] is None:
            return CheckResult(NO_CODE)
        if now > user["verification_expires_at"]:
            repo.clear_verification_code(conn, user_id)
            return CheckResult(EXPIRED)
        if user["verification_attempts"] >= MAX_ATTEMPTS:
            repo.clear_verification_code(conn, user_id)
            return CheckResult(LOCKED)

        expected = user["verification_code_hash"]
        candidate = hash_code(settings.secret_key, user_id, user["email"], submitted)
        if hmac.compare_digest(expected, candidate):
            repo.mark_verified(conn, user_id)
            return CheckResult(OK)

        attempts = repo.bump_verification_attempts(conn, user_id)
        if attempts >= MAX_ATTEMPTS:
            repo.clear_verification_code(conn, user_id)
            return CheckResult(LOCKED)
        return CheckResult(INVALID, attempts_left=MAX_ATTEMPTS - attempts)
