
import os
import sqlite3
import secrets
import smtplib
import hashlib
import re
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from pathlib import Path
from datetime import date
from functools import wraps
from contextlib import contextmanager

import requests

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# 1. CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
# Load .env from this project folder, even when launched from another directory.
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)
# Serverless deployments (including Vercel) have a read-only app directory.
# Use /tmp for temporary files there; local development keeps ./instance.
IS_SERVERLESS = any(
    os.getenv(name, "").strip().lower() in ("1", "true", "yes")
    for name in ("VERCEL", "AWS_LAMBDA_FUNCTION_NAME", "FUNCTIONS_WORKER_RUNTIME")
) or str(BASE_DIR).startswith("/var/task")

if IS_SERVERLESS:
    INSTANCE_DIR = Path("/tmp/aiwriter_instance")
else:
    INSTANCE_DIR = BASE_DIR / "instance"

# Create only a directory in the writable filesystem.
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if IS_SERVERLESS and len(SECRET_KEY) < 32:
    raise RuntimeError(
        "Set SECRET_KEY in Vercel Environment Variables to a long random value (at least 32 characters)."
    )
app.config["SECRET_KEY"] = SECRET_KEY or "local-development-only-change-me"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
# HTTPS par Vercel cookies ko secure hona chahiye; local HTTP par default false rahega.
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "COOKIE_SECURE", "1" if IS_SERVERLESS else "0"
).strip().lower() in ("1", "true", "yes")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

csrf = CSRFProtect(app)


def get_positive_int_env(name, default, minimum=1):
    """Read an integer environment variable safely."""
    try:
        value = int(os.getenv(name, str(default)))
        return value if value >= minimum else default
    except (TypeError, ValueError):
        return default



# Persistent PostgreSQL is used whenever DATABASE_URL is configured.
# SQLite remains available for local development only.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)
if IS_SERVERLESS and not USE_POSTGRES:
    raise RuntimeError(
        "DATABASE_URL is required on Vercel. Configure a persistent PostgreSQL database "
        "and add its connection URL to Vercel Environment Variables."
    )
if USE_POSTGRES and psycopg is None:
    raise RuntimeError("PostgreSQL driver missing. Add psycopg[binary] to requirements.txt.")

if not USE_POSTGRES:
    DATABASE_PATH = Path(
        os.getenv("DATABASE_PATH", str(INSTANCE_DIR / "aiwriter_pro.db"))
    ).expanduser()
    if not DATABASE_PATH.is_absolute():
        DATABASE_PATH = BASE_DIR / DATABASE_PATH
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://127.0.0.1:11434/api/generate",
).strip()

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:1b",
).strip()

OLLAMA_TIMEOUT = get_positive_int_env("OLLAMA_TIMEOUT", 120)
# Vercel par local Ollama accessible nahi hota. Optional OpenAI-compatible endpoint:
# AI_API_URL=https://provider.example/v1/chat/completions
AI_API_URL = os.getenv("AI_API_URL", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip()

MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com").strip()
MAIL_PORT = get_positive_int_env("MAIL_PORT", 587)
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").strip().lower() in ("1", "true", "yes")
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip()
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").replace(" ", "").strip()
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME).strip()
OTP_EXPIRY_MINUTES = 10
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def send_verification_email(recipient, otp):
    """Send a short-lived email verification code through configured SMTP."""
    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_DEFAULT_SENDER:
        raise RuntimeError("Email SMTP is not configured. Set MAIL_USERNAME, MAIL_PASSWORD and MAIL_DEFAULT_SENDER in .env.")

    message = EmailMessage()
    message["Subject"] = "Verify your email address | AIWriter Pro"
    message["From"] = MAIL_DEFAULT_SENDER
    message["To"] = recipient
    message.set_content(
        "Hello,\n\n"
        "Thank you for creating an AIWriter Pro account.\n\n"
        f"Your email verification code is: {otp}\n\n"
        f"For your security, this code will expire in {OTP_EXPIRY_MINUTES} minutes. "
        "Please do not share this code with anyone.\n\n"
        "If you did not request this verification, you can safely ignore this email.\n\n"
        "Best regards,\n"
        "The AIWriter Pro Team"
    )

    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=20) as server:
        if MAIL_USE_TLS:
            server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)


def make_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_hash(code, email):
    # Bind the hash to the address so a code cannot be reused for another account.
    return hashlib.sha256((email.lower() + ":" + code + ":" + app.config["SECRET_KEY"]).encode("utf-8")).hexdigest()


# =========================================================
# 2. PLANS AND WRITING OPTIONS
# =========================================================

PLANS = {
    "free": {
        "name": "Free",
        "daily_limit": 5,
        "monthly_limit": 150,
    },
    "pro": {
        "name": "Pro",
        "daily_limit": 0,
        "monthly_limit": 500,
    },
    "business": {
        "name": "Business",
        "daily_limit": 0,
        "monthly_limit": 2000,
    },
}

WRITING_TYPES = [
    "General writing",
    "Email",
    "Social media post",
    "Product description",
    "Blog introduction",
    "Blog post",
    "Advertisement",
    "Website copy",
    "SEO meta description",
]

LANGUAGES = [
    "English",
    "Urdu",
    "Roman Urdu",
    "Spanish",
    "French",
    "German",
    "Arabic",
    "Hindi",
]

TONES = [
    "Professional",
    "Friendly",
    "Persuasive",
    "Casual",
    "Creative",
    "Formal",
]

LENGTHS = [
    "Short",
    "Medium",
    "Long",
]


# =========================================================
# 3. DATABASE CONNECTION MANAGEMENT
# =========================================================

@contextmanager
def get_db():
    """Open a PostgreSQL connection in production, or SQLite locally."""
    if USE_POSTGRES:
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
    else:
        connection = sqlite3.connect(str(DATABASE_PATH), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _execute(db, query, params=()):
    """Use one placeholder style for both database engines."""
    if USE_POSTGRES:
        query = query.replace("?", "%s")
    return db.execute(query, params)


def init_db():
    """Create tables and migrate existing columns on either database."""
    with get_db() as db:
        if USE_POSTGRES:
            _execute(db, """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    email_verified INTEGER NOT NULL DEFAULT 1,
                    verification_code_hash TEXT,
                    verification_expires_at TEXT,
                    verification_attempts INTEGER NOT NULL DEFAULT 0,
                    verification_last_sent_at TEXT
                )
            """)
            _execute(db, """
                CREATE TABLE IF NOT EXISTS generations (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    writing_type TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    output_language TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    length TEXT NOT NULL,
                    generated_text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            _execute(db, """
                CREATE INDEX IF NOT EXISTS idx_generations_user_date
                ON generations(user_id, created_at)
            """)
            columns = {
                row["column_name"]
                for row in _execute(db, """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'users'
                """).fetchall()
            }
        else:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    writing_type TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    output_language TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    length TEXT NOT NULL,
                    generated_text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_generations_user_date
                ON generations(user_id, created_at);
            """)
            columns = {
                row["name"]
                for row in _execute(db, "PRAGMA table_info(users)").fetchall()
            }

        migrations = {
            "name": "TEXT NOT NULL DEFAULT ''",
            "plan": "TEXT NOT NULL DEFAULT 'free'",
            "email_verified": "INTEGER NOT NULL DEFAULT 1",
            "verification_code_hash": "TEXT",
            "verification_expires_at": "TEXT",
            "verification_attempts": "INTEGER NOT NULL DEFAULT 0",
            "verification_last_sent_at": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in columns:
                _execute(db, f"ALTER TABLE users ADD COLUMN {column} {definition}")


init_db()


# =========================================================
# 4. USER AND AUTHENTICATION HELPERS
# =========================================================

def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    with get_db() as db:
        row = _execute(db, 
            """
            SELECT id, name, email, plan, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        # Usually means this session belongs to a different/old database deployment.
        app.logger.warning(
            "Session user_id was not found in the configured database; clearing stale session."
        )
        session.clear()
        return None

    user = dict(row)

    # Protect against an unexpected plan value in an older database.
    if user["plan"] not in PLANS:
        user["plan"] = "free"

    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_navigation_user():
    return {"current_user": get_current_user()}


# =========================================================
# 5. USAGE LIMITS
# =========================================================

def get_usage(user):
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()
    plan = PLANS[user["plan"]]

    # PostgreSQL aur SQLite mein date conversion ka syntax alag hai.
    date_expression = "created_at::date" if USE_POSTGRES else "date(created_at)"
    with get_db() as db:
        daily_used = _execute(
            db,
            f"SELECT COUNT(*) AS total FROM generations WHERE user_id = ? AND {date_expression} = ?",
            (user["id"], today),
        ).fetchone()["total"]

        monthly_used = _execute(
            db,
            f"SELECT COUNT(*) AS total FROM generations WHERE user_id = ? AND {date_expression} >= ?",
            (user["id"], month_start),
        ).fetchone()["total"]

    daily_limit = plan["daily_limit"]
    monthly_limit = plan["monthly_limit"]

    # Free plan uses its daily quota for the progress display.
    # Other plans use their monthly quota.
    if daily_limit:
        remaining = max(0, daily_limit - daily_used)
        percent = min(
            100,
            int(daily_used * 100 / daily_limit),
        )
    else:
        remaining = max(0, monthly_limit - monthly_used)
        percent = min(
            100,
            int(monthly_used * 100 / monthly_limit),
        )

    # Keep both detailed quota fields and the simpler names used by templates.
    if daily_limit:
        display_used = daily_used
        display_limit = daily_limit
        period_label = "per day"
    else:
        display_used = monthly_used
        display_limit = monthly_limit
        period_label = "per month"

    return {
        "plan": user["plan"],
        "plan_name": plan["name"],
        "daily_used": daily_used,
        "daily_limit": daily_limit,
        "monthly_used": monthly_used,
        "monthly_limit": monthly_limit,
        "used": display_used,
        "limit": display_limit,
        "period_label": period_label,
        "remaining": remaining,
        "percent": percent,
    }


def can_generate(user, usage):
    plan = PLANS[user["plan"]]

    if (
        plan["daily_limit"]
        and usage["daily_used"] >= plan["daily_limit"]
    ):
        return (
            False,
            "Your daily Free-plan limit has been reached.",
        )

    if usage["monthly_used"] >= plan["monthly_limit"]:
        return (
            False,
            "Your monthly generation limit has been reached.",
        )

    return True, ""


# =========================================================
# 6. OLLAMA AI GENERATION
# =========================================================

def generate_with_ollama(
    prompt,
    writing_type,
    language,
    tone,
    length,
):
    """Generate using configured remote chat API, or Ollama for local development."""
    instructions = f"""You are AIWriter, a helpful writing assistant.
Writing format: {writing_type}
Output language: {language}
Tone: {tone}
Length: {length}
Produce the requested content directly. Follow the requested language and tone.
Do not claim to have researched facts that you have not verified.
If details are missing, make reasonable assumptions without inventing specific real-world facts."""

    # Production option: any OpenAI-compatible chat-completions endpoint.
    if AI_API_URL:
        if not AI_API_KEY or not AI_MODEL:
            raise RuntimeError("AI_API_URL is set but AI_API_KEY or AI_MODEL is missing.")
        response = requests.post(
            AI_API_URL,
            headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        try:
            generated_text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI API returned an unexpected response format.") from exc
    else:
        # Local development fallback. On Vercel, localhost means the Vercel runtime,
        # not the user's PC; configure AI_API_URL for production generation.
        if IS_SERVERLESS:
            raise RuntimeError(
                "AI service is not configured. Set AI_API_URL, AI_API_KEY and AI_MODEL in Vercel."
            )
        if not OLLAMA_URL or not OLLAMA_MODEL:
            raise RuntimeError("Ollama configuration is missing.")
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": f"{instructions}\n\nUser request:\n{prompt}", "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Ollama returned an unexpected response.")
        generated_text = (data.get("response") or "").strip()

    if not generated_text:
        raise RuntimeError("The AI model returned an empty response.")
    return generated_text


# =========================================================
# 7. DASHBOARD RENDERING
# =========================================================

def render_dashboard(result=None, form_data=None):
    user = get_current_user()

    if not user:
        flash("Please log in to continue.", "info")
        return redirect(url_for("login"))

    usage = get_usage(user)

    with get_db() as db:
        recent_rows = _execute(db, 
            """
            SELECT
                id,
                writing_type,
                prompt,
                generated_text,
                created_at
            FROM generations
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (user["id"],),
        ).fetchall()

    recent = [dict(row) for row in recent_rows]

    return render_template(
        "dashboard.html",
        current_user=user,
        user=user,
        usage=usage,
        result=result,
        form_data=form_data or {},
        recent=recent,
        writing_types=WRITING_TYPES,
        languages=LANGUAGES,
        tones=TONES,
        lengths=LENGTHS,
    )


# =========================================================
# 8. HOME PAGE
# =========================================================

@app.route("/")
def index():
    if get_current_user():
        return redirect(url_for("dashboard"))

    return render_template("index.html")


# =========================================================
# 9. SIGNUP AND EMAIL VERIFICATION
# =========================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if get_current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(name) < 2:
            flash("Please enter a name with at least 2 characters.", "error")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")
        if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Please enter a valid email address.", "error")
            return render_template("signup.html")
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("signup.html")
        if len(name) > 100 or len(email) > 254:
            flash("Please shorten your name or email address.", "error")
            return render_template("signup.html")

        code = make_otp()
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
        try:
            with get_db() as db:
                existing = _execute(db, 
                    "SELECT id, email_verified FROM users WHERE email = ?",
                    (email,),
                ).fetchone()
                if existing and existing["email_verified"]:
                    flash("An account with that email already exists. Please log in.", "error")
                    return render_template("signup.html")
                if existing and not existing["email_verified"]:
                    _execute(db, 
                        """UPDATE users SET name=?, password_hash=?, verification_code_hash=?,
                           verification_expires_at=?, verification_attempts=0,
                           verification_last_sent_at=? WHERE id=?""",
                        (name, generate_password_hash(password), otp_hash(code, email),
                         expires, now.isoformat(), existing["id"]),
                    )
                    user_id = existing["id"]
                else:
                    insert_sql = """INSERT INTO users
                           (name, email, password_hash, plan, email_verified,
                            verification_code_hash, verification_expires_at,
                            verification_attempts, verification_last_sent_at)
                           VALUES (?, ?, ?, 'free', 0, ?, ?, 0, ?)"""
                    if USE_POSTGRES:
                        cursor = _execute(db, insert_sql + " RETURNING id",
                            (name, email, generate_password_hash(password),
                             otp_hash(code, email), expires, now.isoformat()))
                        user_id = cursor.fetchone()["id"]
                    else:
                        cursor = _execute(db, insert_sql,
                            (name, email, generate_password_hash(password),
                             otp_hash(code, email), expires, now.isoformat()))
                        user_id = cursor.lastrowid
            try:
                send_verification_email(email, code)
            except Exception:
                app.logger.exception("Failed to send signup verification email")
                flash("Your account has been created, but we couldn't send the verification email at this time. Please confirm your email address and select ‘Send a new code’ to try again. If the issue continues, please contact support.", "error")
                session["pending_verification_user_id"] = user_id
                return redirect(url_for("verify_email"))
            session.clear()
            session["pending_verification_user_id"] = user_id
            flash("We sent a 6-digit verification code to your email.", "success")
            return redirect(url_for("verify_email"))
        except (sqlite3.IntegrityError, Exception) as exc:
            if USE_POSTGRES and psycopg is not None and isinstance(exc, psycopg.Error):
                flash("Could not create this account. Please try again.", "error")
            elif isinstance(exc, sqlite3.IntegrityError):
                flash("Could not create this account. Please try again.", "error")
            else:
                raise
            return render_template("signup.html")

    return render_template("signup.html")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    user_id = session.get("pending_verification_user_id")
    if not user_id:
        flash("Start by creating an account or request a new verification code.", "info")
        return redirect(url_for("signup"))

    with get_db() as db:
        user = _execute(db, 
            "SELECT id, email, email_verified, verification_code_hash, verification_expires_at, verification_attempts FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    if not user:
        session.pop("pending_verification_user_id", None)
        return redirect(url_for("signup"))
    if user["email_verified"]:
        session.pop("pending_verification_user_id", None)
        flash("Your email is already verified. Please log in.", "success")
        return redirect(url_for("login"))

    if request.method == "POST":
        submitted = request.form.get("otp", "").strip()
        if not re.fullmatch(r"\d{6}", submitted):
            flash("Enter the 6-digit code from your email.", "error")
        elif user["verification_attempts"] >= OTP_MAX_ATTEMPTS:
            flash("Too many incorrect attempts. Request a new code.", "error")
        elif not user["verification_expires_at"] or datetime.fromisoformat(user["verification_expires_at"]) < datetime.now(timezone.utc):
            flash("This code has expired. Request a new code.", "error")
        elif not secrets.compare_digest(user["verification_code_hash"] or "", otp_hash(submitted, user["email"])):
            with get_db() as db:
                _execute(db, "UPDATE users SET verification_attempts=verification_attempts+1 WHERE id=?", (user_id,))
            flash("That code is incorrect. Please try again.", "error")
        else:
            with get_db() as db:
                _execute(db, 
                    """UPDATE users SET email_verified=1, verification_code_hash=NULL,
                       verification_expires_at=NULL, verification_attempts=0 WHERE id=?""",
                    (user_id,),
                )
            session.pop("pending_verification_user_id", None)
            flash("Email verified successfully. You can now log in.", "success")
            return redirect(url_for("login"))

    return render_template("verify_email.html", email=user["email"])


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    user_id = session.get("pending_verification_user_id")
    if not user_id:
        flash("Start by creating an account before requesting a verification code.", "info")
        return redirect(url_for("signup"))
    now = datetime.now(timezone.utc)
    with get_db() as db:
        user = _execute(db, 
            "SELECT id, email, email_verified, verification_last_sent_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    if not user:
        session.pop("pending_verification_user_id", None)
        return redirect(url_for("signup"))
    if user["email_verified"]:
        session.pop("pending_verification_user_id", None)
        return redirect(url_for("login"))
    last_sent = user["verification_last_sent_at"]
    if last_sent:
        try:
            elapsed = (now - datetime.fromisoformat(last_sent)).total_seconds()
            if elapsed < OTP_RESEND_SECONDS:
                flash(f"Please wait {int(OTP_RESEND_SECONDS - elapsed)} seconds before requesting another code.", "error")
                return redirect(url_for("verify_email"))
        except ValueError:
            pass
    code = make_otp()
    expires = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
    try:
        send_verification_email(user["email"], code)
    except Exception:
        app.logger.exception("Failed to resend verification email")
        flash("We couldn't send a verification code right now. Please try again in a moment. If the problem persists, contact support.", "error")
        return redirect(url_for("verify_email"))
    with get_db() as db:
        _execute(db, 
            """UPDATE users SET verification_code_hash=?, verification_expires_at=?,
               verification_attempts=0, verification_last_sent_at=? WHERE id=?""",
            (otp_hash(code, user["email"]), expires, now.isoformat(), user_id),
        )
    flash("A new verification code has been sent.", "success")
    return redirect(url_for("verify_email"))


# =========================================================
# 10. LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
@app.route("/signin", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as db:
            user = _execute(db, 
                """
                SELECT id, password_hash, email_verified
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html")

        if not user["email_verified"]:
            session["pending_verification_user_id"] = user["id"]
            flash("Please verify your email before logging in.", "error")
            return redirect(url_for("verify_email"))

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]

        flash("You are now logged in.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


# =========================================================
# 11. LOGOUT
# =========================================================

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# =========================================================
# 12. DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_dashboard()


# =========================================================
# 13. GENERATE WRITING
# =========================================================

@app.route("/generate", methods=["POST"])
@app.route("/api/generate", methods=["POST"])
@login_required
def generate():
    user = get_current_user()

    if not user:
        return redirect(url_for("login"))

    prompt = request.form.get("prompt", "").strip()
    writing_type = request.form.get(
        "writing_type",
        "General writing",
    ).strip()
    language = request.form.get(
        "output_language",
        "English",
    ).strip()
    tone = request.form.get(
        "tone",
        "Professional",
    ).strip()
    length = request.form.get(
        "length",
        "Medium",
    ).strip()

    form_data = {
        "prompt": prompt,
        "writing_type": writing_type,
        "output_language": language,
        "tone": tone,
        "length": length,
    }

    if not prompt:
        flash("Please enter a writing request first.", "error")
        return render_dashboard(form_data=form_data)

    if len(prompt) > 5000:
        flash(
            "Your request is too long. Maximum length is 5,000 characters.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    # Validate all option values against server-side allowlists.
    if writing_type not in WRITING_TYPES:
        writing_type = "General writing"

    if language not in LANGUAGES:
        language = "English"

    if tone not in TONES:
        tone = "Professional"

    if length not in LENGTHS:
        length = "Medium"

    form_data.update({
        "writing_type": writing_type,
        "output_language": language,
        "tone": tone,
        "length": length,
    })

    usage = get_usage(user)
    allowed, message = can_generate(user, usage)

    if not allowed:
        flash(
            message + " Review the available plans for more capacity.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    try:
        result = generate_with_ollama(
            prompt,
            writing_type,
            language,
            tone,
            length,
        )

    except requests.exceptions.ConnectionError:
        flash(
            "Cannot connect to the AI service. Check your AI_API_URL or local Ollama settings.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    except requests.exceptions.Timeout:
        flash(
            "The AI model took too long to respond. "
            "Try again or use a smaller model.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    except requests.exceptions.HTTPError as exc:
        app.logger.warning("Ollama HTTP error: %s", exc)
        flash(
            "The AI service returned an error. Check your API URL, key, and model settings.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    except (ValueError, RuntimeError) as exc:
        app.logger.warning("AI generation error: %s", exc)
        flash(str(exc) if IS_SERVERLESS else "The AI could not generate text this time. Please check the AI settings and try again.", "error")
        return render_dashboard(form_data=form_data)

    except requests.exceptions.RequestException as exc:
        app.logger.warning("Ollama request error: %s", exc)
        flash(
            "There was a problem contacting the AI model.",
            "error",
        )
        return render_dashboard(form_data=form_data)

    # Save only successfully generated text.
    with get_db() as db:
        _execute(db, 
            """
            INSERT INTO generations (
                user_id,
                writing_type,
                prompt,
                output_language,
                tone,
                length,
                generated_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                writing_type,
                prompt,
                language,
                tone,
                length,
                result,
            ),
        )

    return render_dashboard(
        result=result,
        form_data=form_data,
    )


# =========================================================
# 14. PLANS
# =========================================================

@app.route("/plans")
@login_required
def plans():
    user = get_current_user()

    return render_template(
        "plans.html",
        current_user=user,
        user=user,
        usage=get_usage(user),
        plans=PLANS,
    )


@app.route("/upgrade", methods=["POST"])
@login_required
def upgrade():
    # Paid access must not be granted without verified payment.
    flash(
        "Online payments are not connected yet. Paid plans are not "
        "activated automatically. Keep using your current plan for now.",
        "info",
    )

    return redirect(url_for("plans"))


# =========================================================
# 15. ACCOUNT SETTINGS
# =========================================================

@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = get_current_user()

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action", "profile").strip()

        if action == "profile":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()

            if not name or len(name) < 2 or len(name) > 80:
                flash("Enter a name between 2 and 80 characters.", "error")
            elif not email or "@" not in email or len(email) > 254:
                flash("Please enter a valid email address.", "error")
            else:
                try:
                    with get_db() as db:
                        _execute(db, 
                            "UPDATE users SET name = ?, email = ? WHERE id = ?",
                            (name, email, user["id"]),
                        )
                    flash("Your profile has been updated.", "success")
                    return redirect(url_for("account"))
                except (sqlite3.IntegrityError, Exception) as exc:
                    if isinstance(exc, sqlite3.IntegrityError) or (
                        USE_POSTGRES and psycopg is not None and isinstance(exc, psycopg.Error)
                    ):
                        flash("That email address is already in use.", "error")
                    else:
                        raise

        elif action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            with get_db() as db:
                password_row = _execute(db, 
                    "SELECT password_hash FROM users WHERE id = ?",
                    (user["id"],),
                ).fetchone()

            if not password_row or not check_password_hash(
                password_row["password_hash"], current_password
            ):
                flash("Your current password is incorrect.", "error")
            elif len(new_password) < 8:
                flash("New password must be at least 8 characters.", "error")
            elif new_password != confirm_password:
                flash("The new passwords do not match.", "error")
            else:
                with get_db() as db:
                    _execute(db, 
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(new_password), user["id"]),
                    )
                flash("Your password has been changed.", "success")
                return redirect(url_for("account"))
        else:
            flash("Invalid account action.", "error")

    user = get_current_user()
    return render_template(
        "account.html",
        current_user=user,
        user=user,
        usage=get_usage(user),
    )


# =========================================================
# 16. ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def file_too_large(_error):
    return "Request is too large.", 413


@app.errorhandler(400)
def bad_request(_error):
    return (
        "The request could not be verified. "
        "Refresh the page and try again.",
        400,
    )


# =========================================================
# 17. RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=get_positive_int_env("PORT", 5000),
        debug=(
            os.getenv("FLASK_DEBUG", "0").strip().lower()
            in ("1", "true", "yes")
        ),
    )