"""AIWriter Studio - Flask application.

Vercel entrypoint: ``web_app:app`` (declared in pyproject.toml under [tool.vercel]).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from aiwriter import ai_provider, mailer, options, otp, repo
from aiwriter.config import Settings, load_settings
from aiwriter.db import Database, DBError, DBIntegrityError, run_migrations, utcnow
from aiwriter.usage import LIMIT_MESSAGES, PLANS, compute_usage
from aiwriter.validation import (is_safe_next, normalize_email, password_fingerprint, validate_email,
                                 validate_name, validate_password)

BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"
HISTORY_PAGE_SIZE = 20
DASHBOARD_RECENT = 5

# Used to make unknown-email logins take as long as real ones (reduces account enumeration).
_DUMMY_HASH = generate_password_hash("not-a-real-password-1")

log = logging.getLogger("aiwriter")


def verify_paddle_signature(raw_body: bytes, signature_header: str, secret: str,
                            tolerance_seconds: int = 300) -> bool:
    """Verify Paddle's ts:raw-body HMAC-SHA256 signature and reject stale requests."""
    if not raw_body or not signature_header or not secret:
        return False
    values = {}
    for part in signature_header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key:
            values.setdefault(key, []).append(value)
    timestamps = values.get("ts") or []
    signatures = values.get("h1") or []
    if not timestamps or not signatures:
        return False
    timestamp = timestamps[0]
    try:
        timestamp_number = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp_number) > tolerance_seconds:
        return False
    signed_payload = timestamp.encode("utf-8") + b":" + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


class RedactingFormatter(logging.Formatter):
    """Replace secret values with *** in every log line, including tracebacks."""

    def __init__(self, secrets_getter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._secrets_getter = secrets_getter

    def format(self, record):
        text = super().format(record)
        for secret in self._secrets_getter():
            text = text.replace(secret, "***")
        return text


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_aiwriter", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)  # Vercel captures stdout/stderr
    handler._aiwriter = True
    handler.setFormatter(RedactingFormatter(
        lambda: settings.secret_values, "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if settings.debug and not settings.is_production else logging.INFO)


def create_app(env=None) -> Flask:
    """Application factory. ``env`` is a mapping of environment variables (default: os.environ)."""
    if env is None:
        if not os.environ.get("VERCEL"):
            try:  # local development only
                from dotenv import load_dotenv
                load_dotenv(BASE_DIR / ".env")
            except ImportError:
                pass
        env = os.environ

    settings = load_settings(env)
    configure_logging(settings)

    # Assets live in public/assets: Vercel serves public/** from its CDN (Flask's static folder is
    # ignored there), so the same /assets/... URL works locally and in production.
    app = Flask(__name__, static_folder="public/assets", static_url_path="/assets",
                template_folder="templates")
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_NAME="aiwriter_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=64 * 1024,
        WTF_CSRF_TIME_LIMIT=None,  # token lives as long as the session
        TEMPLATES_AUTO_RELOAD=settings.debug and not settings.is_production,
    )
    app.extensions["settings"] = settings
    app.extensions["db"] = None
    app.extensions["db_ready"] = False
    # Database availability is independent of AI and email provider configuration.
    # This lets login, existing accounts, and verified billing webhooks work while
    # optional providers are being configured.
    problem_text = " ".join(settings.problems)
    core_config_missing = any(key in problem_text for key in (
        "DATABASE_URL", "SECRET_KEY", "COOKIE_SECURE", "FLASK_DEBUG"
    ))
    if not core_config_missing:
        try:
            app.extensions["db"] = Database(settings.database_url)
        except DBError:
            log.exception("database driver or connection configuration is unavailable")
    db_lock = threading.Lock()
    csrf = CSRFProtect(app)

    # ------------------------------------------------------------------ helpers

    def get_db() -> Database:
        return app.extensions["db"]

    def ensure_db() -> None:
        """Apply pending migrations once per process (safe to run concurrently)."""
        if app.extensions["db_ready"]:
            return
        with db_lock:
            if not app.extensions["db_ready"]:
                applied = run_migrations(get_db(), MIGRATIONS_DIR)
                if applied:
                    log.info("Database migrated: %s", ", ".join(applied))
                app.extensions["db_ready"] = True

    def render_error(status, title, message):
        return render_template("error.html", status=status, title=title, message=message), status

    def db_unavailable():
        return render_error(503, "Service temporarily unavailable",
                            "We could not reach the database. Your data is safe - please try again in a moment.")

    @app.context_processor
    def inject_globals():
        problem_text = " ".join(settings.problems)
        core_ready = not any(key in problem_text for key in (
            "DATABASE_URL", "SECRET_KEY", "COOKIE_SECURE", "FLASK_DEBUG"
        ))
        mail_ready = not any(key in problem_text for key in (
            "MAIL_SERVER", "MAIL_DEFAULT_SENDER", "MAIL_USERNAME", "MAIL_PASSWORD"
        ))
        ai_ready = not any(key in problem_text for key in (
            "AI_API_URL", "AI_API_KEY", "AI_MODEL"
        ))
        return {
            "logged_in": bool(session.get("uid")),
            "current_user": getattr(g, "user", None),
            "auth_ready": core_ready,
            "signup_ready": core_ready and mail_ready,
            "generation_ready": core_ready and ai_ready,
            "billing_ready": settings.billing_ready,
            "paddle_client_token": settings.paddle_client_token,
            "paddle_environment": settings.paddle_environment,
            "paddle_price_pro": settings.paddle_price_pro,
            "paddle_price_business": settings.paddle_price_business,
            "current_year": utcnow().year,
            "writing_label": lambda k: options.label_for(options.WRITING_TYPES, k),
            "language_label": lambda k: options.label_for(options.LANGUAGES, k),
            "tone_label": lambda k: options.label_for(options.TONES, k),
            "length_label": lambda k: options.label_for(options.LENGTHS, k),
        }

    @app.template_filter("dt")
    def format_dt(value):
        return value.strftime("%b %d, %Y %H:%M UTC") if value else ""

    # ------------------------------------------------------------------ authentication

    def load_user():
        """Return (state, user). State is one of: anonymous, ok, missing, stale, db_error.

        A database failure is *not* treated as a missing user, so a valid session is
        never cleared because of a transient outage.
        """
        user_id = session.get("uid")
        if not user_id:
            return "anonymous", None
        # No authenticated session can be resolved until this independent app has a DB.
        if app.extensions.get("db") is None:
            return "anonymous", None
        try:
            with get_db().connection() as conn:
                user = repo.get_user_by_id(conn, user_id)
        except DBError:
            log.exception("auth: database error while loading session user id=%s", user_id)
            return "db_error", None
        if user is None:
            return "missing", None
        if session.get("pwv") != password_fingerprint(user["password_hash"]):
            return "stale", None
        return "ok", user

    def start_session(user) -> None:
        session.clear()  # drop any pre-login state (prevents session fixation)
        session.permanent = True
        session["uid"] = user["id"]
        session["pwv"] = password_fingerprint(user["password_hash"])

    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            state, user = load_user()
            if state == "anonymous":
                target = request.full_path.rstrip("?") if request.method == "GET" else None
                return redirect(url_for("login", next=target) if target and is_safe_next(target) else url_for("login"))
            if state == "db_error":
                return db_unavailable()
            if state in ("missing", "stale"):
                log.warning("auth: session invalidated (%s) for user id=%s", state, session.get("uid"))
                session.clear()
                flash("Your session is no longer valid. Please sign in again.", "warning")
                return redirect(url_for("login"))
            if not user["email_verified"]:
                session["pending_uid"] = user["id"]
                flash("Please verify your email address to continue.", "warning")
                return redirect(url_for("verify_email"))
            g.user = user
            return view(*args, **kwargs)
        return wrapper

    def mask_email(email: str) -> str:
        local, _, domain = email.partition("@")
        return f"{local[:1]}***@{domain}"

    def make_checkout_reference(user) -> str:
        """Bind Paddle custom data to the signed-in AIWriter user without trusting raw IDs."""
        user_id = str(user["id"])
        payload = f"aiwriter-paddle-user:{user_id}".encode("utf-8")
        signature = hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"{user_id}.{signature}"

    def user_id_from_checkout_reference(custom_data) -> int | None:
        """Return a user ID only when the Paddle custom-data reference is signed by this app."""
        if not isinstance(custom_data, dict):
            return None
        reference = str(custom_data.get("aiwriter_checkout_ref") or "")
        user_part, separator, signature = reference.partition(".")
        if not separator or not user_part.isdigit() or not signature:
            return None
        expected = hmac.new(
            settings.secret_key.encode("utf-8"),
            f"aiwriter-paddle-user:{user_part}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        try:
            return int(user_part)
        except ValueError:
            return None

    # ------------------------------------------------------------------ request hooks

    @app.before_request
    def guard():
        if request.endpoint in (None, "static", "health"):
            return None
        # Paddle webhooks are server-to-server calls and verify their own signature.
        if request.endpoint == "paddle_webhook":
            if app.extensions.get("db") is None:
                return jsonify({"error": "database_not_configured"}), 503
            return None
        # Keep the independent public landing pages viewable while this fresh deployment is configured.
        # Account actions and workspace routes remain blocked until their own DB/mail/AI settings exist.
        public_preview = request.endpoint in ("index", "plans") or (
            request.endpoint in ("login", "signup") and request.method == "GET"
        )
        if settings.problems:
            problem_text = " ".join(settings.problems)
            core_missing = any(key in problem_text for key in (
                "DATABASE_URL", "SECRET_KEY", "COOKIE_SECURE", "FLASK_DEBUG"
            ))
            mail_missing = any(key in problem_text for key in (
                "MAIL_SERVER", "MAIL_DEFAULT_SENDER", "MAIL_USERNAME", "MAIL_PASSWORD"
            ))
            ai_missing = any(key in problem_text for key in (
                "AI_API_URL", "AI_API_KEY", "AI_MODEL"
            ))

            # Public landing pages and GET-only auth screens remain viewable during setup.
            if public_preview:
                return None

            required_missing = []
            if request.endpoint in ("login", "dashboard", "generate", "history", "account",
                                    "update_profile", "change_password", "logout"):
                if core_missing:
                    required_missing.append("The new workspace database and session settings are not connected yet.")
            elif request.endpoint in ("signup", "verify_email", "resend_code"):
                if core_missing:
                    required_missing.append("The new workspace database and session settings are not connected yet.")
                if mail_missing:
                    required_missing.append("The email delivery service is not configured yet.")
            if request.endpoint == "generate" and ai_missing:
                required_missing.append("The AI writing service is not configured yet.")

            if required_missing:
                return render_error(
                    503, "This feature is not ready yet",
                    " ".join(required_missing) + " Return to the homepage while setup is completed."
                )

        try:
            ensure_db()
        except DBError:
            log.exception("database initialisation failed")
            return db_unavailable()
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://cdn.paddle.com; "
            "connect-src 'self' https://sandbox-api.paddle.com https://api.paddle.com; "
            "frame-src 'self' https://sandbox-checkout.paddle.com https://checkout.paddle.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "base-uri 'self'; form-action 'self' https://sandbox-checkout.paddle.com https://checkout.paddle.com; "
            "frame-ancestors 'none'")
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint not in ("static",):
            response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------------ error handlers

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        log.warning("CSRF check failed on %s %s: %s", request.method, request.path, exc.description)
        return render_error(400, "Form expired",
                            "Your form has expired or is invalid. Go back, reload the page and try again.")

    @app.errorhandler(Exception)
    def unhandled(exc):
        if isinstance(exc, HTTPException):
            titles = {404: "Page not found", 405: "Method not allowed", 413: "Request too large"}
            if exc.code in titles:
                return render_error(exc.code, titles[exc.code], exc.description if exc.code != 404
                                    else "The page you are looking for does not exist.")
            return render_error(exc.code or 500, exc.name, "Something went wrong with that request.")
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return render_error(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    # ------------------------------------------------------------------ public pages

    @app.get("/")
    def index():
        return render_template("index.html", plans=PLANS)

    @app.get("/health")
    def health():
        if settings.problems:
            body, status = {"status": "misconfigured"}, 503
        else:
            try:
                ensure_db()
                get_db().ping()
                body, status = {"status": "ok"}, 200
            except DBError:
                log.exception("health: database check failed")
                body, status = {"status": "degraded", "database": "unavailable"}, 503
        response = jsonify(body)
        response.status_code = status
        return response

    @app.get("/plans")
    def plans():
        current = None
        if session.get("uid"):
            state, user = load_user()
            if state == "ok":
                current = user["plan"]
                g.user = user
        user = getattr(g, "user", None)
        checkout_ref = make_checkout_reference(user) if user else ""
        price_ids = {
            "pro": settings.paddle_price_pro,
            "business": settings.paddle_price_business,
        }
        display_prices = {"free": "$0", "pro": "$11.99", "business": "$29.99"}
        return render_template(
            "plans.html", plans=PLANS, current_plan=current,
            checkout_ref=checkout_ref, price_ids=price_ids, display_prices=display_prices,
        )

    @app.post("/webhooks/paddle")
    @csrf.exempt
    def paddle_webhook():
        """Receive Paddle Billing events and update paid plans only after signature verification."""
        if not settings.paddle_webhook_secret:
            return jsonify({"error": "webhook_not_configured"}), 503
        raw_body = request.get_data(cache=True, as_text=False)
        signature = request.headers.get("Paddle-Signature", "")
        if not verify_paddle_signature(raw_body, signature, settings.paddle_webhook_secret):
            log.warning("paddle webhook rejected: invalid signature")
            return jsonify({"error": "invalid_signature"}), 401

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_json"}), 400
        event_id = str(payload.get("event_id") or "").strip()
        event_type = str(payload.get("event_type") or "").strip()
        occurred_at = payload.get("occurred_at")
        data = payload.get("data") or {}
        if not event_id or not event_type or not isinstance(data, dict):
            return jsonify({"error": "invalid_event"}), 400

        try:
            ensure_db()
            with get_db().connection() as conn:
                if repo.get_paddle_event(conn, event_id):
                    return jsonify({"received": True, "duplicate": True}), 200

                handled_types = {
                    "transaction.completed",
                    "subscription.created",
                    "subscription.updated",
                    "subscription.canceled",
                }
                if event_type not in handled_types:
                    repo.record_paddle_event(conn, event_id, event_type, occurred_at, utcnow())
                    return jsonify({"received": True, "ignored": True}), 200

                if event_type == "transaction.completed":
                    subscription_id = data.get("subscription_id")
                    incoming_status = "active"
                else:
                    subscription_id = data.get("id")
                    incoming_status = str(data.get("status") or "unknown").lower()
                    if event_type == "subscription.canceled":
                        incoming_status = "canceled"

                # A one-off transaction has no subscription_id and must never grant a paid plan.
                if not subscription_id:
                    repo.record_paddle_event(conn, event_id, event_type, occurred_at, utcnow())
                    return jsonify({"received": True, "subscription": False}), 200

                existing = repo.get_paddle_subscription(conn, subscription_id)
                custom_data = data.get("custom_data") or {}
                user_id = user_id_from_checkout_reference(custom_data)
                if user_id is None and existing:
                    user_id = existing["user_id"]

                price_id = None
                for item in data.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    price = item.get("price") or {}
                    if isinstance(price, dict):
                        price_id = price.get("id")
                    price_id = price_id or item.get("price_id")
                    if price_id:
                        break
                if not price_id and existing:
                    price_id = existing["price_id"]

                if price_id == settings.paddle_price_pro:
                    plan = "pro"
                elif price_id == settings.paddle_price_business:
                    plan = "business"
                else:
                    plan = existing["plan"] if existing else None

                if user_id is None or plan is None:
                    log.error(
                        "paddle webhook could not map subscription %s to an AIWriter user/plan; event=%s",
                        subscription_id, event_id,
                    )
                    return jsonify({"error": "subscription_mapping_failed"}), 422

                customer_id = data.get("customer_id") or (existing["paddle_customer_id"] if existing else None)
                period = data.get("current_billing_period") or {}
                period_end = period.get("ends_at") if isinstance(period, dict) else None

                # Ignore stale subscription notifications when Paddle delivers events out of order.
                if existing and existing.get("last_event_at") and occurred_at:
                    old_time = existing["last_event_at"]
                    old_text = old_time.isoformat() if hasattr(old_time, "isoformat") else str(old_time)
                    if str(occurred_at) < old_text:
                        repo.record_paddle_event(conn, event_id, event_type, occurred_at, utcnow())
                        return jsonify({"received": True, "stale": True}), 200

                repo.upsert_paddle_subscription(
                    conn, subscription_id, user_id, customer_id, price_id, plan,
                    incoming_status, period_end, occurred_at, utcnow(),
                )

                if incoming_status in ("active", "trialing", "past_due"):
                    repo.update_user_plan(conn, user_id, plan)
                elif incoming_status in ("canceled", "paused"):
                    repo.update_user_plan(conn, user_id, repo.active_paddle_plan(conn, user_id))

                repo.record_paddle_event(conn, event_id, event_type, occurred_at, utcnow())
        except DBError:
            log.exception("paddle webhook database failure")
            return jsonify({"error": "database_unavailable"}), 503
        except Exception:
            log.exception("paddle webhook processing failure")
            return jsonify({"error": "webhook_processing_failed"}), 500

        return jsonify({"received": True}), 200

    # ------------------------------------------------------------------ signup / OTP

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "GET":
            return render_template("signup.html", form={}, errors={})

        form = {"name": request.form.get("name", ""), "email": request.form.get("email", "")}
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = {}
        name, err = validate_name(form["name"])
        if err:
            errors["name"] = err
        email, err = validate_email(form["email"])
        if err:
            errors["email"] = err
        err = validate_password(password)
        if err:
            errors["password"] = err
        elif password != confirm:
            errors["confirm_password"] = "Passwords do not match."
        form = {"name": name, "email": email or form["email"].strip()}
        if errors:
            return render_template("signup.html", form=form, errors=errors), 400

        password_hash = generate_password_hash(password)
        now = utcnow()
        created_user_id = None
        try:
            with get_db().connection() as conn:
                existing = repo.get_user_by_email(conn, email)
                if existing and existing["email_verified"]:
                    errors["email"] = "An account with this email already exists. Try signing in."
                elif existing:
                    # Unverified registration: let the owner of the address restart it.
                    repo.update_unverified_signup(conn, existing["id"], name, password_hash)
                    user_id = existing["id"]
                else:
                    user_id = created_user_id = repo.create_user(conn, name, email, password_hash, now)
                if not errors:
                    user = repo.get_user_by_id(conn, user_id)
        except DBIntegrityError:
            errors["email"] = "An account with this email already exists. Try signing in."
        except DBError:
            log.exception("signup: database error")
            return db_unavailable()
        if errors:
            return render_template("signup.html", form=form, errors=errors), 400

        try:
            otp.send_code(get_db(), settings, user, now=now)
        except otp.CooldownActive as exc:
            flash(f"A code was sent a moment ago. You can request another in {exc.seconds} seconds.", "info")
        except mailer.MailError as exc:
            if created_user_id is not None:  # never leave an account the user cannot verify
                try:
                    with get_db().connection() as conn:
                        repo.delete_unverified_user(conn, created_user_id)
                except DBError:
                    log.exception("signup: could not remove account after email failure")
            return render_template("signup.html", form=form, errors={"_form": str(exc)}), 503
        except DBError:
            log.exception("signup: could not store verification code")
            return db_unavailable()
        else:
            flash(f"We sent a 6-digit code to {mask_email(email)}. It expires in 10 minutes.", "success")

        session.clear()
        session["pending_uid"] = user["id"]
        return redirect(url_for("verify_email"))

    def pending_user():
        """Return (user, error_response) for the account currently being verified."""
        user_id = session.get("pending_uid") or session.get("uid")
        if not user_id:
            return None, None
        try:
            with get_db().connection() as conn:
                return repo.get_user_by_id(conn, user_id), None
        except DBError:
            log.exception("verify: database error")
            return None, db_unavailable()

    @app.route("/verify-email", methods=["GET", "POST"])
    def verify_email():
        user, failure = pending_user()
        if failure:
            return failure
        if user is None:
            session.pop("pending_uid", None)
            flash("Please sign in or create an account first.", "info")
            return redirect(url_for("login"))
        if user["email_verified"]:
            session.pop("pending_uid", None)
            return redirect(url_for("dashboard") if session.get("uid") == user["id"] else url_for("login"))

        def page(error=None, status=200):
            wait = otp.cooldown_remaining(user.get("verification_last_sent_at"), utcnow())
            return render_template("verify_email.html", masked_email=mask_email(user["email"]),
                                   cooldown=wait, error=error, max_attempts=otp.MAX_ATTEMPTS), status

        if request.method == "GET":
            return page()

        code = "".join((request.form.get("code") or "").split())
        if not (len(code) == 6 and code.isdigit()):
            return page("Enter the 6-digit code from your email.", 400)
        try:
            result = otp.check_code(get_db(), settings, user["id"], code)
        except DBError:
            log.exception("verify: database error while checking code")
            return db_unavailable()

        if result.status in (otp.OK, otp.ALREADY_VERIFIED):
            session.pop("pending_uid", None)
            if result.status == otp.OK:
                flash("Email verified. Welcome to AIWriter Studio!", "success")
            if session.get("uid") == user["id"]:
                return redirect(url_for("dashboard"))
            flash("You can now sign in.", "info")
            return redirect(url_for("login"))
        if result.status == otp.INVALID:
            noun = "attempt" if result.attempts_left == 1 else "attempts"
            return page(f"That code is incorrect. {result.attempts_left} {noun} left.", 400)
        if result.status == otp.EXPIRED:
            return page("That code has expired. Request a new code below.", 400)
        if result.status == otp.LOCKED:
            return page("Too many incorrect attempts. Request a new code below.", 429)
        return page("There is no active code. Request a new code below.", 400)

    @app.post("/verify-email/resend")
    def resend_code():
        user, failure = pending_user()
        if failure:
            return failure
        if user is None:
            flash("Please sign in or create an account first.", "info")
            return redirect(url_for("login"))
        if user["email_verified"]:
            return redirect(url_for("login"))
        try:
            otp.send_code(get_db(), settings, user)
            flash(f"A new code was sent to {mask_email(user['email'])}. Earlier codes no longer work.", "success")
        except otp.CooldownActive as exc:
            flash(f"Please wait {exc.seconds} seconds before requesting another code.", "warning")
        except mailer.MailError as exc:
            flash(str(exc), "error")
        except DBError:
            log.exception("resend: database error")
            return db_unavailable()
        return redirect(url_for("verify_email"))

    # ------------------------------------------------------------------ login / logout

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            state, user = load_user()
            if state == "ok" and user["email_verified"]:
                return redirect(url_for("dashboard"))
            return render_template("login.html", form={}, error=None, next=request.args.get("next", ""))

        email = normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        next_url = request.form.get("next", "")
        try:
            with get_db().connection() as conn:
                user = repo.get_user_by_email(conn, email) if email else None
        except DBError:
            log.exception("login: database error")
            return db_unavailable()

        valid = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password) and user is not None
        if not valid:
            log.info("login: failed attempt")
            return render_template("login.html", form={"email": email}, next=next_url,
                                   error="Incorrect email or password."), 401

        if not user["email_verified"]:
            session.clear()
            session["pending_uid"] = user["id"]
            flash("Please verify your email address to finish signing in.", "warning")
            return redirect(url_for("verify_email"))

        start_session(user)
        flash("Welcome back!", "success")
        return redirect(next_url if is_safe_next(next_url) else url_for("dashboard"))

    app.add_url_rule("/signin", endpoint="signin", view_func=lambda: redirect(url_for("login")))

    @app.post("/logout")
    def logout():
        session.clear()
        flash("You have been signed out.", "info")
        return redirect(url_for("index"))

    # ------------------------------------------------------------------ dashboard & generation

    def clean_form(source) -> dict:
        form = {k: (source.get(k) or "").strip() for k in options.DEFAULT_FORM}
        form["prompt"] = (source.get("prompt") or "").strip()
        return form

    def validate_generation(form) -> dict:
        errors = {}
        if not form["prompt"]:
            errors["prompt"] = "Please describe what you want written."
        elif len(form["prompt"]) > options.MAX_PROMPT_CHARS:
            errors["prompt"] = f"Your request is too long. The limit is {options.MAX_PROMPT_CHARS} characters."
        checks = (("writing_type", options.WRITING_TYPES), ("output_language", options.LANGUAGES),
                  ("tone", options.TONES), ("length", options.LENGTHS))
        for field, choices in checks:
            if form[field] not in options.keys(choices):
                errors[field] = "Please choose one of the listed options."
                form[field] = options.DEFAULT_FORM[field]
        return errors

    def render_dashboard(user, *, form, errors=None, generation=None, status=200):
        try:
            with get_db().connection() as conn:
                usage = compute_usage(conn, user)
                recent = repo.recent_generations(conn, user["id"], DASHBOARD_RECENT)
        except DBError:
            log.exception("dashboard: database error")
            return db_unavailable()
        return render_template(
            "dashboard.html", user=user, usage=usage, recent=recent, form=form, errors=errors or {},
            generation=generation, writing_types=options.pairs(options.WRITING_TYPES),
            languages=options.pairs(options.LANGUAGES), tones=options.pairs(options.TONES),
            lengths=options.pairs(options.LENGTHS), max_prompt=options.MAX_PROMPT_CHARS), status

    @app.get("/dashboard")
    @login_required
    def dashboard():
        user = g.user
        form, generation = dict(options.DEFAULT_FORM), None
        view_id = request.args.get("view", type=int)
        if view_id:
            try:
                with get_db().connection() as conn:
                    generation = repo.get_generation(conn, user["id"], view_id)
            except DBError:
                log.exception("dashboard: database error loading generation")
                return db_unavailable()
            if generation is None:
                flash("That generation could not be found.", "warning")
            else:
                form = {k: generation[k] for k in options.DEFAULT_FORM}
        return render_dashboard(user, form=form, generation=generation)

    @app.post("/generate")
    @login_required
    def generate():
        user = g.user
        form = clean_form(request.form)
        errors = validate_generation(form)
        if errors:
            return render_dashboard(user, form=form, errors=errors, status=400)

        try:
            with get_db().connection() as conn:
                usage = compute_usage(conn, user)
        except DBError:
            log.exception("generate: database error checking usage")
            return db_unavailable()
        if not usage.allowed:  # enforced before any AI call
            return render_dashboard(user, form=form, errors={"_form": LIMIT_MESSAGES[usage.blocked_reason]}, status=429)

        try:
            text = ai_provider.generate_text(settings, form["prompt"], form["writing_type"],
                                             form["output_language"], form["tone"], form["length"])
        except ai_provider.ProviderError as exc:
            return render_dashboard(user, form=form, errors={"_form": exc.user_message}, status=exc.http_status)

        try:
            with get_db().connection() as conn:
                conn.lock_user(user["id"])  # serialise concurrent generations for this user
                usage = compute_usage(conn, user)  # re-check now that we hold the lock
                if not usage.allowed:
                    blocked = LIMIT_MESSAGES[usage.blocked_reason]
                    saved_id = None
                else:
                    blocked = None
                    saved_id = repo.insert_generation(
                        conn, user["id"], form["writing_type"], form["prompt"], form["output_language"],
                        form["tone"], form["length"], text, utcnow())
        except DBError:
            log.exception("generate: could not save generation")
            transient = dict(form, generated_text=text, id=None, created_at=None)
            return render_dashboard(
                user, form=form, generation=transient, status=503,
                errors={"_form": "Your text was generated but could not be saved to your history, "
                                 "so it was not counted. Copy it now if you need it."})
        if blocked:
            return render_dashboard(user, form=form, errors={"_form": blocked}, status=429)
        return redirect(url_for("dashboard", view=saved_id))

    @app.get("/history")
    @login_required
    def history():
        user = g.user
        page = max(1, request.args.get("page", 1, type=int) or 1)
        try:
            with get_db().connection() as conn:
                total = repo.count_generations(conn, user["id"])
                items = repo.recent_generations(conn, user["id"], HISTORY_PAGE_SIZE,
                                                (page - 1) * HISTORY_PAGE_SIZE)
        except DBError:
            log.exception("history: database error")
            return db_unavailable()
        pages = max(1, -(-total // HISTORY_PAGE_SIZE))
        return render_template("history.html", items=items, page=page, pages=pages, total=total)

    # ------------------------------------------------------------------ account

    def render_account(user, *, profile_errors=None, password_errors=None, name=None, status=200):
        return render_template("account.html", user=user, usage_plan=PLANS.get(user["plan"], PLANS["free"]),
                               name=name if name is not None else user["name"],
                               profile_errors=profile_errors or {}, password_errors=password_errors or {}), status

    @app.get("/account")
    @login_required
    def account():
        return render_account(g.user)

    @app.post("/account/profile")
    @login_required
    def update_profile():
        user = g.user
        name, err = validate_name(request.form.get("name"))
        if err:
            return render_account(user, profile_errors={"name": err}, name=request.form.get("name", ""), status=400)
        try:
            with get_db().connection() as conn:
                repo.update_name(conn, user["id"], name)
        except DBError:
            log.exception("account: could not update profile")
            return db_unavailable()
        flash("Your profile was updated.", "success")
        return redirect(url_for("account"))

    @app.post("/account/password")
    @login_required
    def change_password():
        user = g.user
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        errors = {}
        if not check_password_hash(user["password_hash"], current):
            errors["current_password"] = "Your current password is incorrect."
        err = validate_password(new)
        if err:
            errors["new_password"] = err
        elif new == current:
            errors["new_password"] = "Choose a password different from your current one."
        elif new != confirm:
            errors["confirm_password"] = "Passwords do not match."
        if errors:
            return render_account(user, password_errors=errors, status=400)
        new_hash = generate_password_hash(new)
        try:
            with get_db().connection() as conn:
                repo.update_password(conn, user["id"], new_hash)
        except DBError:
            log.exception("account: could not change password")
            return db_unavailable()
        session["pwv"] = password_fingerprint(new_hash)  # other sessions become invalid
        flash("Your password was changed. Other devices have been signed out.", "success")
        return redirect(url_for("account"))

    # ------------------------------------------------------------------ CLI

    @app.cli.command("init-db")
    def init_db_command():
        """Apply database migrations."""
        if settings.problems:
            raise SystemExit("Configuration problems:\n  - " + "\n  - ".join(settings.problems))
        applied = run_migrations(get_db(), MIGRATIONS_DIR)
        print("Applied: " + (", ".join(applied) if applied else "nothing (already up to date)"))

    return app


try:
    app = create_app()
except Exception:  # pragma: no cover - surfaces import-time failures in deployment logs
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("aiwriter").exception("Failed to create the Flask application")
    raise

if __name__ == "__main__":  # local development server
    _settings = app.extensions["settings"]
    app.run(debug=_settings.debug and not _settings.is_production, port=int(os.environ.get("PORT", "5000")))
