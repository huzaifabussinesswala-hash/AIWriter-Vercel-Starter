# AIWriter Fresh Studio

This is a completely separate AIWriter application inside the repository. It has its own Vercel project and root directory:

`AIWriter-Fresh-Studio/`

The previous AIWriter project remains in its existing folder and is not modified by this application.

## Stack

- Flask application with the existing secure authentication, email verification, AI generation, usage accounting and writing history services.
- A separately authored public website, dashboard, writer workspace and design system.
- Static assets in `public/assets/`, served at `/assets/`.
- Vercel Python entrypoint: `app.py` → `web_app.py`.

## Local setup

Use Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python web_app.py
```

Open `http://127.0.0.1:5000/`.

Set the environment values from `.env.example` in the separate Vercel project before enabling account registration or generation. Use a dedicated production PostgreSQL database for this independent product; SQLite files on serverless deployments are not persistent.

## Email verification / OTP

For Vercel production, the app supports Resend's HTTPS email API. This avoids relying on an SMTP socket and is the recommended delivery path for this deployment.

1. Create a Resend account and add/verify a domain you control.
2. Create an API key with email-sending permission.
3. In Vercel → Project → Settings → Environment Variables, add `RESEND_API_KEY` for Production.
4. Set `MAIL_DEFAULT_SENDER` to an address on the verified domain, for example `AIWriter <verify@yourdomain.com>`.
5. Redeploy the project so the new environment variables are loaded.

When `RESEND_API_KEY` is present, the app sends OTP emails through the Resend HTTPS API. If it is absent, the existing SMTP configuration remains available as a fallback: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER`.

Never put an API key or SMTP password in source code or commit a real `.env` file. Keep the OTP expiry, one-minute resend cooldown and attempt limit enabled.

## Paddle billing

Paddle is not wired into checkout yet. When a Paddle seller account is approved, add Paddle client-side token, API credentials and webhook secret as encrypted Vercel environment variables. Keep card data inside Paddle checkout; never store card numbers or CVV in this application.
