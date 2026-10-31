"""Environment-driven configuration with startup validation.

Validation problems are reported by *variable name only*; secret values are never
included in messages or logs.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
DEV_DEFAULT_DATABASE_URL = "sqlite:///instance/aiwriter_dev.db"


class ConfigError(RuntimeError):
    """Raised by callers that prefer to fail hard on invalid configuration."""


@dataclass(frozen=True)
class Settings:
    environment: str
    debug: bool
    secret_key: str
    database_url: str
    cookie_secure: bool
    mail_server: str
    mail_port: int
    mail_use_tls: bool
    mail_username: str
    mail_password: str
    mail_default_sender: str
    ai_api_url: str
    ai_api_key: str
    ai_model: str
    ai_timeout: float
    problems: tuple = ()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secret_values(self) -> list:
        """Values that must never appear in logs."""
        values = [self.secret_key, self.mail_password, self.ai_api_key]
        parsed = urlparse(self.database_url)
        if parsed.password:
            values.append(parsed.password)
        return [v for v in values if v and len(v) >= 6]


def _text(env: Mapping, name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


def _flag(env: Mapping, name: str, default: bool, problems: list) -> bool:
    raw = _text(env, name).lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    problems.append(f"{name} must be true or false.")
    return default


def _number(env: Mapping, name: str, default: float, problems: list, cast=int) -> float:
    raw = _text(env, name)
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        problems.append(f"{name} must be a number.")
        return default


def _detect_environment(env: Mapping) -> str:
    explicit = _text(env, "APP_ENV").lower()
    if explicit in {"production", "development", "testing"}:
        return explicit
    if _text(env, "VERCEL") or _text(env, "VERCEL_ENV"):
        return "production"
    return "development"


def _is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".local")


def load_settings(env: Mapping | None = None) -> Settings:
    """Read settings from ``env`` (defaults to ``os.environ``) and validate them."""
    env = os.environ if env is None else env
    problems: list = []
    environment = _detect_environment(env)
    production = environment == "production"

    debug = _flag(env, "FLASK_DEBUG", False, problems)
    secret_key = _text(env, "SECRET_KEY")
    database_url = _text(env, "DATABASE_URL")
    cookie_secure = _flag(env, "COOKIE_SECURE", production, problems)

    mail_port = int(_number(env, "MAIL_PORT", 587, problems))
    mail_use_tls = _flag(env, "MAIL_USE_TLS", True, problems)
    ai_timeout = float(_number(env, "AI_TIMEOUT", 30.0, problems, cast=float))

    if not 1 <= ai_timeout <= 120:
        problems.append("AI_TIMEOUT must be between 1 and 120 seconds.")
        ai_timeout = 30.0

    settings_kwargs = dict(
        environment=environment,
        debug=debug,
        cookie_secure=cookie_secure,
        mail_server=_text(env, "MAIL_SERVER"),
        mail_port=mail_port,
        mail_use_tls=mail_use_tls,
        mail_username=_text(env, "MAIL_USERNAME"),
        mail_password=_text(env, "MAIL_PASSWORD"),
        mail_default_sender=_text(env, "MAIL_DEFAULT_SENDER"),
        ai_api_url=_text(env, "AI_API_URL"),
        ai_api_key=_text(env, "AI_API_KEY"),
        ai_model=_text(env, "AI_MODEL"),
        ai_timeout=ai_timeout,
    )

    if production:
        if len(secret_key) < 32:
            problems.append("SECRET_KEY is missing or shorter than 32 characters.")
        if not database_url:
            problems.append("DATABASE_URL is missing (a hosted PostgreSQL URL is required).")
        elif not database_url.lower().startswith(("postgresql://", "postgres://")):
            problems.append("DATABASE_URL must be a postgresql:// URL in production.")
        if not cookie_secure:
            problems.append("COOKIE_SECURE must be true in production.")
        if debug:
            problems.append("FLASK_DEBUG must be false in production.")
        if not settings_kwargs["mail_server"]:
            problems.append("MAIL_SERVER is missing.")
        if not settings_kwargs["mail_default_sender"]:
            problems.append("MAIL_DEFAULT_SENDER is missing.")
        if bool(settings_kwargs["mail_username"]) != bool(settings_kwargs["mail_password"]):
            problems.append("MAIL_USERNAME and MAIL_PASSWORD must be set together.")
        ai_url = settings_kwargs["ai_api_url"]
        if not ai_url:
            problems.append("AI_API_URL is missing.")
        elif not ai_url.lower().startswith(("http://", "https://")):
            problems.append("AI_API_URL must start with https:// (or http://).")
        elif _is_local_url(ai_url):
            problems.append("AI_API_URL must be reachable from the deployment, not localhost.")
        if not settings_kwargs["ai_api_key"]:
            problems.append("AI_API_KEY is missing.")
        if not settings_kwargs["ai_model"]:
            problems.append("AI_MODEL is missing.")
    else:
        if not secret_key:
            secret_key = secrets.token_hex(32)
            log.warning("SECRET_KEY not set; using a temporary key (sessions reset on restart). "
                        "Never do this in production.")
        if not database_url:
            database_url = DEV_DEFAULT_DATABASE_URL

    if production and not secret_key:
        # Keep Flask bootable so /health and the configuration error page still work.
        secret_key = secrets.token_hex(32)

    settings = Settings(secret_key=secret_key, database_url=database_url,
                        problems=tuple(problems), **settings_kwargs)
    for problem in settings.problems:
        log.error("Configuration problem: %s", problem)
    return settings
