"""Shared fixtures. No real SMTP, AI provider or production database is ever used."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiwriter import ai_provider, mailer, repo  # noqa: E402
from aiwriter.config import load_settings  # noqa: E402
from aiwriter.db import Database, run_migrations  # noqa: E402

PASSWORD = "Sup3rSecret!"
EMAIL = "writer@example.com"


@pytest.fixture
def env(tmp_path):
    """Environment for an isolated test application backed by its own SQLite file."""
    return {
        "APP_ENV": "testing",
        "SECRET_KEY": "test-secret-key-" + "x" * 32,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "COOKIE_SECURE": "false",
        "MAIL_SERVER": "smtp.test.invalid",
        "MAIL_DEFAULT_SENDER": "AIWriter <no-reply@test.invalid>",
        "AI_API_URL": "https://ai.test.invalid/v1/chat/completions",
        "AI_API_KEY": "test-ai-key-123456",
        "AI_MODEL": "test-model",
    }


@pytest.fixture
def settings(env):
    return load_settings(env)


@pytest.fixture
def db(settings):
    database = Database(settings.database_url)
    run_migrations(database, ROOT / "migrations")
    return database


@pytest.fixture
def mailbox(monkeypatch):
    """Capture verification emails instead of sending them."""
    sent = []

    def fake_send(settings, to_email, name, code):
        sent.append({"to": to_email, "name": name, "code": code})

    monkeypatch.setattr(mailer, "send_otp_email", fake_send)
    return sent


class FakeAI:
    def __init__(self):
        self.calls = []
        self.text = "Here is your generated text."
        self.error = None
        self.side_effect = None

    def __call__(self, settings, prompt, writing_type, output_language, tone, length):
        self.calls.append({"prompt": prompt, "writing_type": writing_type,
                           "output_language": output_language, "tone": tone, "length": length})
        if self.side_effect:
            self.side_effect()
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(ai_provider, "generate_text", fake)
    return fake


@pytest.fixture
def app(env, mailbox):
    from web_app import create_app
    application = create_app(env)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_db(app):
    """Direct access to the database used by the app (migrations applied)."""
    from aiwriter.db import run_migrations as migrate
    database = app.extensions["db"]
    migrate(database, ROOT / "migrations")
    return database


# ---------------------------------------------------------------- helpers

def csrf_token(client):
    """Fetch a valid CSRF token for the client's current session."""
    html = client.get("/plans").get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match, "page did not render a CSRF token"
    return match.group(1)


def post(client, path, data=None, **kwargs):
    payload = dict(data or {})
    payload.setdefault("csrf_token", csrf_token(client))
    return client.post(path, data=payload, **kwargs)


def signup(client, email=EMAIL, password=PASSWORD, name="Test Writer", **kwargs):
    return post(client, "/signup", {"name": name, "email": email, "password": password,
                                    "confirm_password": password}, **kwargs)


def verify(client, mailbox, **kwargs):
    return post(client, "/verify-email", {"code": mailbox[-1]["code"]}, **kwargs)


def login(client, email=EMAIL, password=PASSWORD, **kwargs):
    return post(client, "/login", {"email": email, "password": password}, **kwargs)


def register_and_login(client, mailbox, email=EMAIL, password=PASSWORD):
    assert signup(client, email, password).status_code == 302
    assert verify(client, mailbox).status_code == 302
    assert login(client, email, password).status_code == 302


@pytest.fixture
def logged_in(client, mailbox):
    register_and_login(client, mailbox)
    return client


def user_id_for(database, email=EMAIL):
    with database.connection() as conn:
        return repo.get_user_by_email(conn, email)["id"]
