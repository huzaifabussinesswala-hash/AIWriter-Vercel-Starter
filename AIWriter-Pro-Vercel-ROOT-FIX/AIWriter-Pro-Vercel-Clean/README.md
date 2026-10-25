# AIWriter Pro

AIWriter Pro is a Flask AI-writing SaaS starter with registration, email OTP verification, a dashboard, generation history, plan quotas, account settings, and an OpenAI-compatible AI provider integration.

## Repository root

The repository root is the folder containing `web_app.py`, `requirements.txt`, `pyproject.toml`, `templates/`, `static/`, and `tests/`. If uploading this project to GitHub, upload the contents of this folder at the repository root. In Vercel, set **Root Directory** to the repository root (leave it blank or set `.` if `web_app.py` is at the top level). The Flask entrypoint is declared as `web_app:app` in `pyproject.toml`; do not add an extra nested project folder.

## Local setup

1. Install Python 3.10+ (Python 3.12 recommended).
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`.
5. Set `SECRET_KEY` to a long random value. For local development only, the app can start without a `.env`; it uses a local SQLite database.
6. Configure SMTP and a reachable OpenAI-compatible AI API if you want email verification and generation to work.
7. Run `python web_app.py`, then open `http://127.0.0.1:5000`.

Local SQLite is only a development convenience. Production should use a persistent PostgreSQL database.

## PostgreSQL

Set `DATABASE_URL` to a PostgreSQL connection URL, for example `postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require`. The app normalizes it to SQLAlchemy's `postgresql+psycopg` driver. The schema is initialized using `CREATE TABLE IF NOT EXISTS`; this does not drop existing data. For a larger production system, use a versioned migration tool such as Alembic and run migrations as a controlled deployment step.

## Email OTP

Configure `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER`. OTPs expire after ten minutes, attempts are limited, and resend requests have a 60-second cooldown. SMTP credentials belong only in environment variables, never in source control.

## AI provider

Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL`. `AI_API_URL` must be a remote endpoint accessible from the deployed server and should accept the OpenAI-compatible `POST /chat/completions` request shape. Do not use localhost for production. The provider must return `choices[0].message.content`.

## Vercel deployment

1. Push this directory's contents to a Git repository.
2. Import that repository into Vercel.
3. Set Root Directory to the folder containing `web_app.py` (normally `./`).
4. Add `SECRET_KEY`, `DATABASE_URL`, `COOKIE_SECURE=true`, SMTP variables, and AI variables in Vercel Project Settings → Environment Variables.
5. Deploy and visit `/health`. It should return `{"status":"ok","database":"connected"}` when the database is reachable.
6. If deployment fails, inspect Vercel → Deployments → the failed deployment → Build Logs and Function Logs.

The included `vercel.json` uses Vercel's Python builder with `web_app.py` as the function entrypoint. Platform support and configuration formats can change; a real Vercel deployment was not run in this environment, so verify the build on your Vercel account before launch.

## Plans

- Free: 5 successful generations/day, 150/month.
- Pro: no daily cap, 500/month.
- Business: no daily cap, 2,000/month.

Paid-plan checkout is intentionally not implemented. Do not manually assign paid plans in production; integrate a trusted payment provider and verify payment server-side before changing plan status.

## Security notes and known limitations

- Flask-WTF CSRF protection is enabled, including POST logout.
- Passwords use Werkzeug's password hashing; OTP values are stored as keyed hashes.
- Use HTTPS and a strong persistent `SECRET_KEY` in production.
- Email change is intentionally disabled until a second verification flow is added.
- Concurrent generation quota checks are not fully serialized; add database locking/atomic quota reservations before high-volume production use.
- For production-grade migrations, use Alembic and deploy migrations explicitly.
- Do not claim production readiness until you configure external services and run tests against a staging PostgreSQL instance.

## Tests

Run `pytest -q`. Tests mock external AI/email services and use a dedicated temporary SQLite database where applicable.
