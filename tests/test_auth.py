import logging
import re

from aiwriter import repo
from aiwriter.db import DBError

from conftest import EMAIL, PASSWORD, csrf_token, login, post, register_and_login, signup, user_id_for, verify


# ----------------------------------------------------------- signup validation


def test_signup_page_renders(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.get_data(as_text=True)


def test_signup_validates_every_field(client, mailbox):
    response = post(client, "/signup", {"name": "", "email": "not-an-email", "password": "short",
                                        "confirm_password": "different"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Please enter your name." in html
    assert "valid email address" in html
    assert "at least 8 characters" in html
    assert mailbox == []


def test_signup_rejects_mismatched_and_weak_passwords(client, mailbox):
    response = post(client, "/signup", {"name": "A", "email": "a@example.com", "password": "Password1",
                                        "confirm_password": "Password2"})
    assert response.status_code == 400 and "Passwords do not match." in response.get_data(as_text=True)
    response = post(client, "/signup", {"name": "A", "email": "a@example.com", "password": "onlyletters",
                                        "confirm_password": "onlyletters"})
    assert response.status_code == 400 and "letter and one number" in response.get_data(as_text=True)


def test_signup_creates_unverified_account_and_sends_code(client, mailbox, app_db):
    response = signup(client, email="  Writer@Example.COM ")
    assert response.status_code == 302 and response.headers["Location"].endswith("/verify-email")
    assert len(mailbox) == 1 and mailbox[0]["to"] == EMAIL  # email normalised
    with app_db.connection() as conn:
        user = repo.get_user_by_email(conn, EMAIL)
    assert user["email_verified"] is False
    assert user["password_hash"] != PASSWORD and user["password_hash"].startswith(("scrypt:", "pbkdf2:"))
    assert user["plan"] == "free"


def test_duplicate_verified_email_is_rejected(client, mailbox):
    register_and_login(client, mailbox)
    other = client.application.test_client()
    response = signup(other, name="Someone Else")
    assert response.status_code == 400
    assert "already exists" in response.get_data(as_text=True)


def test_smtp_failure_does_not_leave_an_unusable_account(client, monkeypatch, app_db):
    from aiwriter import mailer

    def broken(*args, **kwargs):
        raise mailer.MailError("We could not send the verification email. Please try again in a few minutes.")

    monkeypatch.setattr(mailer, "send_otp_email", broken)
    response = signup(client)
    assert response.status_code == 503
    assert "could not send the verification email" in response.get_data(as_text=True)
    with app_db.connection() as conn:
        assert repo.get_user_by_email(conn, EMAIL) is None  # can simply try again later


def test_unverified_signup_can_be_restarted_with_new_password(client, mailbox, app_db):
    assert signup(client).status_code == 302
    assert signup(client, password="An0therPass!").status_code == 302
    assert len(mailbox) == 1  # resend cooldown still applies
    assert verify(client, mailbox).status_code == 302
    assert login(client, password="An0therPass!").status_code == 302


# ----------------------------------------------------------- verification flow


def test_verify_requires_a_pending_account(client):
    response = client.get("/verify-email")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_verify_rejects_malformed_and_wrong_codes(client, mailbox):
    signup(client)
    assert post(client, "/verify-email", {"code": "12ab"}).status_code == 400
    wrong = "000000" if mailbox[-1]["code"] != "000000" else "111111"
    response = post(client, "/verify-email", {"code": wrong})
    assert response.status_code == 400 and "4 attempts left" in response.get_data(as_text=True)


def test_verify_locks_after_five_wrong_attempts(client, mailbox):
    signup(client)
    wrong = "000000" if mailbox[-1]["code"] != "000000" else "111111"
    statuses = [post(client, "/verify-email", {"code": wrong}).status_code for _ in range(5)]
    assert statuses == [400, 400, 400, 400, 429]
    assert verify(client, mailbox).status_code == 400  # real code refused until a new one is sent


def test_resend_is_rate_limited_then_replaces_old_code(client, mailbox, app_db):
    signup(client)
    response = post(client, "/verify-email/resend", follow_redirects=True)
    assert "Please wait" in response.get_data(as_text=True) and len(mailbox) == 1
    with app_db.connection() as conn:  # move the last-sent time back past the cooldown
        conn.execute("UPDATE users SET verification_last_sent_at = ?", ("2000-01-01 00:00:00.000000+00:00",))
    post(client, "/verify-email/resend", follow_redirects=True)
    assert len(mailbox) == 2
    assert verify(client, mailbox).status_code == 302


def test_unverified_user_cannot_use_protected_pages(client, mailbox):
    signup(client)
    assert login(client).status_code == 302  # credentials right, email not verified
    response = client.get("/dashboard")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_login_with_unverified_email_redirects_to_verification(client, mailbox):
    signup(client)
    fresh = client.application.test_client()
    response = login(fresh)
    assert response.status_code == 302 and response.headers["Location"].endswith("/verify-email")
    assert fresh.get("/dashboard").status_code == 302


# ----------------------------------------------------------- login / session


def test_login_with_wrong_password_and_unknown_email_share_one_message(client, mailbox):
    register_and_login(client, mailbox)
    other = client.application.test_client()
    bad_password = login(other, password="WrongPass1")
    unknown = login(other, email="nobody@example.com")
    assert bad_password.status_code == unknown.status_code == 401
    assert "Incorrect email or password." in bad_password.get_data(as_text=True)
    assert "Incorrect email or password." in unknown.get_data(as_text=True)


def test_anonymous_users_are_redirected_from_protected_pages(client):
    for path in ("/dashboard", "/history", "/account"):
        response = client.get(path)
        assert response.status_code == 302 and "/login" in response.headers["Location"], path
    assert client.post("/generate", data={"csrf_token": csrf_token(client)}).status_code == 302


def test_login_persists_across_separate_requests(logged_in):
    for _ in range(3):
        assert logged_in.get("/dashboard").status_code == 200
    assert logged_in.get("/history").status_code == 200
    assert logged_in.get("/account").status_code == 200


def test_login_persists_across_application_instances(logged_in, env, mailbox):
    """A new serverless invocation (new process) must accept the same session cookie."""
    from web_app import create_app
    cookie = logged_in.get_cookie("aiwriter_session")
    second = create_app(env).test_client()
    second.set_cookie("aiwriter_session", cookie.value)
    assert second.get("/dashboard").status_code == 200


def test_session_cookie_flags(client, mailbox):
    signup(client)
    verify(client, mailbox)
    response = login(client)
    cookies = [c for c in response.headers.getlist("Set-Cookie") if c.startswith("aiwriter_session=")]
    assert cookies, "login did not set the session cookie"
    assert "HttpOnly" in cookies[-1] and "SameSite=Lax" in cookies[-1]


def test_secure_cookie_flag_is_set_in_production_mode(env, mailbox):
    from web_app import create_app
    app = create_app(dict(env, COOKIE_SECURE="true"))
    client = app.test_client()
    client.get("/plans", base_url="https://localhost")
    cookie = client.get_cookie("aiwriter_session")
    assert cookie is not None and cookie.secure is True


def test_deleted_user_invalidates_session_with_a_message(logged_in, app_db):
    with app_db.connection() as conn:
        conn.execute("DELETE FROM users")
    response = logged_in.get("/dashboard")
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    page = logged_in.get("/login").get_data(as_text=True)
    assert "no longer valid" in page


def test_database_outage_does_not_clear_a_valid_session(logged_in, monkeypatch):
    original = repo.get_user_by_id

    def failing(conn, user_id):
        raise DBError("database error: OperationalError")

    monkeypatch.setattr(repo, "get_user_by_id", failing)
    response = logged_in.get("/dashboard")
    assert response.status_code == 503  # temporary error page, NOT a redirect to login
    monkeypatch.setattr(repo, "get_user_by_id", original)
    assert logged_in.get("/dashboard").status_code == 200  # still signed in


def test_next_redirect_only_allows_local_paths(client, mailbox):
    signup(client)
    verify(client, mailbox)
    for evil in ("//evil.example.com", "https://evil.example.com", "/\\evil.example.com", "javascript:alert(1)"):
        fresh = client.application.test_client()
        response = post(fresh, "/login", {"email": EMAIL, "password": PASSWORD, "next": evil})
        assert response.status_code == 302 and response.headers["Location"].endswith("/dashboard"), evil
    good = client.application.test_client()
    response = post(good, "/login", {"email": EMAIL, "password": PASSWORD, "next": "/history"})
    assert response.headers["Location"].endswith("/history")


def test_protected_page_redirect_remembers_destination(client, mailbox):
    signup(client)
    verify(client, mailbox)
    location = client.get("/history").headers["Location"]
    assert "next=" in location and "history" in location


# ----------------------------------------------------------- CSRF and logout


def test_post_without_csrf_token_is_rejected(client):
    for path in ("/login", "/signup", "/logout", "/verify-email", "/verify-email/resend"):
        response = client.post(path, data={"email": "a@example.com", "password": "x"})
        assert response.status_code == 400, path
        assert "expired or is invalid" in response.get_data(as_text=True)


def test_post_with_wrong_csrf_token_is_rejected(client):
    csrf_token(client)
    response = client.post("/login", data={"email": EMAIL, "password": PASSWORD, "csrf_token": "forged"})
    assert response.status_code == 400


def test_logout_requires_post_and_csrf_and_ends_session(logged_in):
    assert logged_in.get("/logout").status_code == 405
    assert logged_in.post("/logout").status_code == 400
    assert logged_in.get("/dashboard").status_code == 200  # still signed in after the rejected attempts
    response = post(logged_in, "/logout")
    assert response.status_code == 302
    assert logged_in.get("/dashboard").status_code == 302


def test_full_user_journey(client, mailbox, ai):
    """signup -> OTP -> login -> dashboard -> generate -> history -> logout -> login again."""
    assert signup(client).status_code == 302
    assert verify(client, mailbox).status_code == 302
    assert login(client).status_code == 302
    assert client.get("/dashboard").status_code == 200

    response = post(client, "/generate", {"prompt": "Welcome email", "writing_type": "email",
                                          "output_language": "english", "tone": "friendly", "length": "short"})
    assert response.status_code == 302
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Here is your generated text." in page
    assert "Welcome email" in client.get("/history").get_data(as_text=True)

    assert post(client, "/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302
    assert login(client).status_code == 302
    assert "Welcome email" in client.get("/history").get_data(as_text=True)  # data persisted


# ----------------------------------------------------------- account


def test_profile_name_update(logged_in):
    response = post(logged_in, "/account/profile", {"name": "New Name"}, follow_redirects=True)
    assert "Your profile was updated." in response.get_data(as_text=True)
    assert "New Name" in logged_in.get("/account").get_data(as_text=True)


def test_profile_rejects_empty_name(logged_in):
    response = post(logged_in, "/account/profile", {"name": "   "})
    assert response.status_code == 400 and "Please enter your name." in response.get_data(as_text=True)


def test_password_change_requires_current_password_and_valid_new_one(logged_in):
    bad_current = post(logged_in, "/account/password", {"current_password": "Nope12345", "new_password": "N3wPassword!",
                                                        "confirm_password": "N3wPassword!"})
    assert bad_current.status_code == 400 and "current password is incorrect" in bad_current.get_data(as_text=True)
    weak = post(logged_in, "/account/password", {"current_password": PASSWORD, "new_password": "short",
                                                 "confirm_password": "short"})
    assert weak.status_code == 400
    mismatch = post(logged_in, "/account/password", {"current_password": PASSWORD, "new_password": "N3wPassword!",
                                                     "confirm_password": "Different1"})
    assert mismatch.status_code == 400 and "do not match" in mismatch.get_data(as_text=True)


def test_password_change_works_and_signs_out_other_sessions(logged_in):
    other = logged_in.application.test_client()
    assert login(other).status_code == 302 and other.get("/dashboard").status_code == 200

    response = post(logged_in, "/account/password", {"current_password": PASSWORD, "new_password": "N3wPassword!",
                                                     "confirm_password": "N3wPassword!"})
    assert response.status_code == 302
    assert logged_in.get("/dashboard").status_code == 200  # this session stays valid
    assert other.get("/dashboard").status_code == 302  # the other device is signed out

    fresh = logged_in.application.test_client()
    assert login(fresh, password=PASSWORD).status_code == 401
    assert login(fresh, password="N3wPassword!").status_code == 302


# ----------------------------------------------------------- logging hygiene


def test_logs_never_contain_codes_passwords_or_secrets(client, mailbox, ai, env):
    records = []

    class Collector(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Collector()
    logging.getLogger().addHandler(handler)
    try:
        register_and_login(client, mailbox)
        login(client.application.test_client(), password="WrongPass1")
        post(client, "/generate", {"prompt": "Secret plan", "writing_type": "general", "output_language": "english",
                                   "tone": "formal", "length": "short"})
    finally:
        logging.getLogger().removeHandler(handler)
    text = "\n".join(records)
    for secret in (mailbox[-1]["code"], PASSWORD, env["SECRET_KEY"], env["AI_API_KEY"]):
        assert secret not in text
