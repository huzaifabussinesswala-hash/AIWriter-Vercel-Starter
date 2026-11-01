"""AIWriter Pro - Flask application.

Vercel entrypoint: ``web_app:app`` (declared in pyproject.toml under [tool.vercel]).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
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
    if not settings.problems:
        app.extensions["db"] = Database(settings.database_url)
    db_lock = threading.Lock()
    CSRFProtect(app)

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
        return {
            "logged_in": bool(session.get("uid")),
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

    # ------------------------------------------------------------------ request hooks

    @app.before_request
    def guard():
        if request.endpoint in (None, "static", "health"):
            return None
        if settings.problems:
            return render_error(503, "Setup in progress",
                                "This site is not fully configured yet. Please try again later.")
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
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
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
        return render_template("plans.html", plans=PLANS, current_plan=current)

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
                flash("Email verified. Welcome to AIWriter Pro!", "success")
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
