import smtplib
from datetime import datetime, timedelta, timezone

import pytest

from aiwriter import mailer, otp, repo

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def user(db):
    with db.connection() as conn:
        uid = repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
        return repo.get_user_by_id(conn, uid)


def fresh(db, user_id):
    with db.connection() as conn:
        return repo.get_user_by_id(conn, user_id)


def test_codes_are_six_digits_and_keep_leading_zeros(monkeypatch):
    for _ in range(200):
        code = otp.generate_code()
        assert len(code) == 6 and code.isdigit()
    monkeypatch.setattr(otp.secrets, "randbelow", lambda n: 7)
    assert otp.generate_code() == "000007"


def test_hash_is_bound_to_user_email_and_secret():
    base = otp.hash_code("secret", 1, "a@example.com", "123456")
    assert base != otp.hash_code("secret", 2, "a@example.com", "123456")
    assert base != otp.hash_code("secret", 1, "b@example.com", "123456")
    assert base != otp.hash_code("other", 1, "a@example.com", "123456")
    assert "123456" not in base and len(base) == 64


def test_send_code_stores_only_a_hash_and_expiry(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    stored = fresh(db, user["id"])
    code = mailbox[-1]["code"]
    assert mailbox[-1]["to"] == "ann@example.com"
    assert stored["verification_code_hash"] and code not in stored["verification_code_hash"]
    assert stored["verification_expires_at"] == NOW + timedelta(minutes=10)
    assert stored["verification_last_sent_at"] == NOW
    assert stored["verification_attempts"] == 0


def test_correct_code_verifies_the_account(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    result = otp.check_code(db, settings, user["id"], mailbox[-1]["code"], now=NOW + timedelta(minutes=1))
    assert result.status == otp.OK
    stored = fresh(db, user["id"])
    assert stored["email_verified"] is True and stored["verification_code_hash"] is None


def test_code_expires_after_ten_minutes(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    code = mailbox[-1]["code"]
    assert otp.check_code(db, settings, user["id"], code, now=NOW + timedelta(minutes=10, seconds=1)).status == otp.EXPIRED
    assert fresh(db, user["id"])["email_verified"] is False
    assert otp.check_code(db, settings, user["id"], code, now=NOW + timedelta(minutes=1)).status == otp.NO_CODE


def test_code_is_still_valid_just_before_expiry(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    result = otp.check_code(db, settings, user["id"], mailbox[-1]["code"], now=NOW + timedelta(minutes=9, seconds=59))
    assert result.status == otp.OK


def test_wrong_codes_are_counted_and_lock_after_five(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    real = mailbox[-1]["code"]
    wrong = "000000" if real != "000000" else "111111"
    left = []
    for _ in range(4):
        result = otp.check_code(db, settings, user["id"], wrong, now=NOW)
        assert result.status == otp.INVALID
        left.append(result.attempts_left)
    assert left == [4, 3, 2, 1]
    assert otp.check_code(db, settings, user["id"], wrong, now=NOW).status == otp.LOCKED
    # even the right code no longer works until a new one is requested
    assert otp.check_code(db, settings, user["id"], real, now=NOW).status == otp.NO_CODE
    assert fresh(db, user["id"])["email_verified"] is False


def test_resend_cooldown_is_sixty_seconds(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    current = fresh(db, user["id"])
    with pytest.raises(otp.CooldownActive) as info:
        otp.send_code(db, settings, current, now=NOW + timedelta(seconds=30))
    assert info.value.seconds == 30
    otp.send_code(db, settings, current, now=NOW + timedelta(seconds=60))
    assert len(mailbox) == 2
    assert otp.cooldown_remaining(None, NOW) == 0


def test_new_code_invalidates_the_old_one_and_resets_attempts(db, settings, user, mailbox):
    otp.send_code(db, settings, user, now=NOW)
    old = mailbox[-1]["code"]
    otp.check_code(db, settings, user["id"], "999999" if old != "999999" else "888888", now=NOW)
    later = NOW + timedelta(seconds=61)
    otp.send_code(db, settings, fresh(db, user["id"]), now=later)
    new = mailbox[-1]["code"]
    assert fresh(db, user["id"])["verification_attempts"] == 0
    if new != old:
        assert otp.check_code(db, settings, user["id"], old, now=later).status == otp.INVALID
    assert otp.check_code(db, settings, user["id"], new, now=later).status == otp.OK


def test_smtp_failure_does_not_store_a_code(db, settings, user, monkeypatch):
    def broken(*args, **kwargs):
        raise mailer.MailError("could not send")

    monkeypatch.setattr(mailer, "send_otp_email", broken)
    with pytest.raises(mailer.MailError):
        otp.send_code(db, settings, user, now=NOW)
    stored = fresh(db, user["id"])
    assert stored["verification_code_hash"] is None and stored["verification_last_sent_at"] is None


def test_already_verified_account_is_reported(db, settings, user):
    with db.connection() as conn:
        repo.mark_verified(conn, user["id"])
    assert otp.check_code(db, settings, user["id"], "123456", now=NOW).status == otp.ALREADY_VERIFIED


# ----------------------------------------------------------- SMTP delivery (mocked)


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.calls = host, port, []
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.sent = message


def test_smtp_delivery_uses_tls_login_and_contains_code(monkeypatch, env):
    from aiwriter.config import load_settings
    cfg = load_settings(dict(env, MAIL_USERNAME="mailer", MAIL_PASSWORD="smtp-pass-123", MAIL_PORT="587"))
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailer.send_otp_email(cfg, "ann@example.com", "Ann", "123456")
    smtp = FakeSMTP.instances[0]
    assert smtp.calls[0] == "starttls" and smtp.calls[1] == ("login", "mailer", "smtp-pass-123")
    assert smtp.sent["To"] == "ann@example.com"
    assert "123456" in smtp.sent.get_content()


def test_smtp_failure_raises_safe_mail_error(monkeypatch, env):
    from aiwriter.config import load_settings
    cfg = load_settings(dict(env, MAIL_USERNAME="mailer", MAIL_PASSWORD="smtp-pass-123"))

    class Exploding(FakeSMTP):
        def login(self, username, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials smtp-pass-123")

    monkeypatch.setattr(smtplib, "SMTP", Exploding)
    with pytest.raises(mailer.MailError) as info:
        mailer.send_otp_email(cfg, "ann@example.com", "Ann", "123456")
    assert "smtp-pass-123" not in str(info.value) and "123456" not in str(info.value)


def test_missing_mail_configuration_raises_mail_error(env):
    from aiwriter.config import load_settings
    cfg = load_settings(dict(env, MAIL_SERVER=""))
    with pytest.raises(mailer.MailError):
        mailer.send_otp_email(cfg, "ann@example.com", "Ann", "123456")


def test_newline_in_name_cannot_inject_headers(monkeypatch, env):
    from aiwriter.config import load_settings
    cfg = load_settings(env)
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailer.send_otp_email(cfg, "ann@example.com", "Ann\r\nBcc: evil@example.com", "123456")
    assert FakeSMTP.instances[0].sent["Bcc"] is None
