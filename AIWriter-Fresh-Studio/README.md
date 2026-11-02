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

## Paddle billing

Paddle is not wired into checkout yet. When a Paddle seller account is approved, add Paddle client-side token, API credentials and webhook secret as encrypted Vercel environment variables. Keep card data inside Paddle checkout; never store card numbers or CVV in this application.
