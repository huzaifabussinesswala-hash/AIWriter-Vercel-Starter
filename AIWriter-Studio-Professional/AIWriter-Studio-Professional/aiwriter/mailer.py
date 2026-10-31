"""SMTP delivery of verification codes. Never logs the code or the SMTP password."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

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


def send_otp_email(settings, to_email: str, name: str, code: str) -> None:
    if not settings.mail_server or not settings.mail_default_sender:
        log.error("Email is not configured (MAIL_SERVER / MAIL_DEFAULT_SENDER missing)")
        raise MailError("Email delivery is not configured yet. Please contact the site administrator.")

    # Strip control characters so a crafted name cannot inject headers or lines.
    safe_name = "".join(ch for ch in name if ch.isprintable())[:100] or "there"
    message = build_otp_message(settings, to_email, safe_name, code)
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
