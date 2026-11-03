"""Send verification codes with Resend's HTTP API or SMTP fallback."""
from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

import requests

log = logging.getLogger(__name__)


class MailError(Exception):
    """The email could not be delivered. The message is safe to show to users."""


def build_otp_message(settings, to_email: str, name: str, code: str, minutes: int = 10) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Your AIWriter Pro verification code"
    msg["From"] = settings.mail_default_sender
    msg["To"] = to_email
    msg.set_content(
        f"Hi {name},\n\n"
        f"Your AIWriter Pro verification code is: {code}\n\n"
        f"It expires in {minutes} minutes. If you did not create an account, you can ignore this email.\n"
    )
    return msg


def _send_with_resend(settings, message: EmailMessage, to_email: str) -> None:
    """Send over HTTPS so production delivery does not depend on an SMTP socket."""
    payload = {
        "from": settings.mail_default_sender,
        "to": [to_email],
        "subject": message["Subject"],
        "text": message.get_content(),
    }
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(5, 15),
        )
    except requests.RequestException as exc:
        # Do not log the request, API key, recipient, or message body.
        log.error("Resend API request failed (%s)", type(exc).__name__)
        raise MailError(
            "We could not send the verification email. Please try again in a few minutes."
        ) from None

    if not response.ok:
        # Log the provider's actionable error name/message, but never log addresses or secrets.
        try:
            provider_error = response.json()
        except ValueError:
            provider_error = {}

        error_name = str(provider_error.get("name") or provider_error.get("code") or "unknown")
        error_message = str(provider_error.get("message") or provider_error.get("error") or "")
        error_message = re.sub(
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}",
            "[email]",
            error_message,
            flags=re.IGNORECASE,
        )
        error_message = re.sub(r"re_[A-Za-z0-9_-]+", "[redacted-key]", error_message)
        error_message = re.sub(r"\\s+", " ", error_message).strip()[:240]

        log.error(
            "Resend API rejected email delivery (HTTP %s, %s): %s",
            response.status_code,
            error_name[:80],
            error_message or "No provider message returned",
        )
        raise MailError(
            "We could not send the verification email. Please try again in a few minutes."
        )


def send_otp_email(settings, to_email: str, name: str, code: str) -> None:
    if not settings.mail_default_sender:
        log.error("Email is not configured (MAIL_DEFAULT_SENDER missing)")
        raise MailError("Email delivery is not configured yet. Please contact the site administrator.")

    # Strip control characters so a crafted name cannot inject headers or lines.
    safe_name = "".join(ch for ch in name if ch.isprintable())[:100] or "there"
    message = build_otp_message(settings, to_email, safe_name, code)

    # Prefer the HTTPS provider whenever a Resend key is configured.
    # SMTP remains available as a fallback for existing installations.
    if settings.resend_api_key:
        _send_with_resend(settings, message, to_email)
        return

    if not settings.mail_server:
        log.error("Email is not configured (MAIL_SERVER / RESEND_API_KEY missing)")
        raise MailError("Email delivery is not configured yet. Please contact the site administrator.")

    context = ssl.create_default_context()
    try:
        if settings.mail_port == 465:
            server = smtplib.SMTP_SSL(settings.mail_server, settings.mail_port, timeout=15, context=context)
        else:
            server = smtplib.SMTP(settings.mail_server, settings.mail_port, timeout=15)
        with server:
            if settings.mail_port != 465 and settings.mail_use_tls:
                server.starttls(context=context)
            if settings.mail_username:
                server.login(settings.mail_username, settings.mail_password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        # Log the exception type only: SMTP errors can echo credentials or recipient data.
        log.error("SMTP delivery failed (%s)", type(exc).__name__)
        raise MailError("We could not send the verification email. Please try again in a few minutes.") from None
