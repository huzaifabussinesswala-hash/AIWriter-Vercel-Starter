import re
import tomllib
from pathlib import Path

from aiwriter.config import load_settings

ROOT = Path(__file__).resolve().parent.parent

PRODUCTION_ENV = {
    "APP_ENV": "production",
    "SECRET_KEY": "p" * 40,
    "DATABASE_URL": "postgresql://user:db-password-1@db.example.com:5432/app?sslmode=require",
    "COOKIE_SECURE": "true",
    "MAIL_SERVER": "smtp.example.com",
    "MAIL_USERNAME": "mailer",
    "MAIL_PASSWORD": "mail-password-1",
    "MAIL_DEFAULT_SENDER": "AIWriter <no-reply@example.com>",
    "AI_API_URL": "https://api.example.com/v1/chat/completions",
    "AI_API_KEY": "ai-key-abcdef",
    "AI_MODEL": "some-model",
}


def test_valid_production_configuration_has_no_problems():
    settings = load_settings(PRODUCTION_ENV)
    assert settings.problems == ()
    assert settings.is_production
    assert settings.cookie_secure is True


def test_empty_production_configuration_lists_actionable_problems():
    settings = load_settings({"APP_ENV": "production"})
    text = " ".join(settings.problems)
    for name in ("SECRET_KEY", "DATABASE_URL", "MAIL_SERVER", "AI_API_URL", "AI_API_KEY", "AI_MODEL"):
        assert name in text


def test_vercel_environment_is_treated_as_production():
    assert load_settings({"VERCEL": "1"}).is_production


def test_production_rejects_sqlite_localhost_ai_and_insecure_cookies():
    env = dict(PRODUCTION_ENV, DATABASE_URL="sqlite:///x.db", AI_API_URL="http://127.0.0.1:11434/v1",
               COOKIE_SECURE="false", FLASK_DEBUG="true")
    text = " ".join(load_settings(env).problems)
    assert "DATABASE_URL" in text
    assert "localhost" in text
    assert "COOKIE_SECURE" in text
    assert "FLASK_DEBUG" in text


def test_short_secret_key_is_rejected_in_production():
    problems = load_settings(dict(PRODUCTION_ENV, SECRET_KEY="short")).problems
    assert any("SECRET_KEY" in p for p in problems)


def test_problem_messages_never_contain_secret_values():
    env = dict(PRODUCTION_ENV, DATABASE_URL="mysql://u:db-password-1@h/db", AI_API_URL="http://localhost/x")
    joined = " ".join(load_settings(env).problems)
    for secret in ("db-password-1", "ai-key-abcdef", "mail-password-1", "p" * 40):
        assert secret not in joined


def test_secret_values_are_listed_for_log_redaction():
    values = load_settings(PRODUCTION_ENV).secret_values
    assert "mail-password-1" in values and "ai-key-abcdef" in values and "db-password-1" in values


def test_development_defaults_are_usable():
    settings = load_settings({})
    assert settings.environment == "development"
    assert settings.database_url.startswith("sqlite:///")
    assert settings.secret_key and settings.cookie_secure is False
    assert settings.ai_timeout == 30.0


def test_invalid_numbers_and_flags_are_reported():
    settings = load_settings({"MAIL_PORT": "abc", "COOKIE_SECURE": "maybe", "AI_TIMEOUT": "500"})
    text = " ".join(settings.problems)
    assert "MAIL_PORT" in text and "COOKIE_SECURE" in text and "AI_TIMEOUT" in text


def test_requirements_match_pyproject_dependencies():
    def norm(items):
        return {re.sub(r"\s+", "", i).lower() for i in items if i.strip() and not i.startswith("#")}

    requirements = norm((ROOT / "requirements.txt").read_text().splitlines())
    declared = norm(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"])
    assert requirements == declared


def test_env_example_contains_all_required_settings_with_placeholders_only():
    text = (ROOT / ".env.example").read_text()
    required = ["SECRET_KEY", "DATABASE_URL", "COOKIE_SECURE", "MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS",
                "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_DEFAULT_SENDER", "AI_API_URL", "AI_API_KEY",
                "AI_MODEL", "AI_TIMEOUT", "FLASK_DEBUG"]
    for name in required:
        assert re.search(rf"^{name}=", text, re.M), name
    assert "127.0.0.1:11434" not in text
