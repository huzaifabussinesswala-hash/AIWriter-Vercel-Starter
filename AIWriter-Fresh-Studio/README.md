# AIWriter Pro — Flask + Vercel project

This directory is the **application root** for Vercel. In this GitHub repository it is stored at:

`AIWriter-GitHub-Ready-Fixed/AIWriter-GitHub-Ready/`

In Vercel → Project Settings → Build and Deployment → Root Directory, set the exact path above. The files `app.py`, `web_app.py`, `vercel.json`, `pyproject.toml`, `requirements.txt`, `public/`, and `templates/` must all remain together in this directory.

## Vercel entrypoint

- Vercel loads `app.py`.
- `app.py` imports the Flask instance named `app` from `web_app.py`.
- `pyproject.toml` declares `entrypoint = "app:app"`.
- `vercel.json` routes the Python function through `app.py`.
- Static assets are stored in `public/assets/` and referenced at `/assets/...`.

Do not set the Vercel Root Directory to the outer `AIWriter-GitHub-Ready-Fixed` folder; that folder does not directly contain the Flask entrypoint.

## Included functionality

- Signup, email OTP, login, history, usage, plans, account, and AI text generation routes.
- Desktop sidebar hide/show with saved preference.
- Responsive mobile layout; mobile navigation remains separate from the desktop sidebar collapse.
- Local Ollama configuration example using the OpenAI-compatible `/v1` endpoint.

## Local setup (Windows)

Use Python 3.12 or newer (the project declares Python `>=3.12`).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env`. For local Ollama, keep these values:

```env
APP_ENV=development
AI_API_URL=http://127.0.0.1:11434/v1
AI_API_KEY=
AI_MODEL=qwen3:1.7b
AI_TIMEOUT=120
```

Install and start Ollama, then pull the model:

```powershell
ollama pull qwen3:1.7b
ollama serve
```

Run the app:

```powershell
python web_app.py
```

Open `http://127.0.0.1:5000/`.

## Vercel production environment variables

Set these in Vercel → Project → Settings → Environment Variables, for the Production environment (and Preview too if you deploy previews):

| Variable | Requirement |
|---|---|
| `SECRET_KEY` | Required; use a unique random value of at least 32 characters |
| `DATABASE_URL` | Required; hosted PostgreSQL URL beginning with `postgresql://` or `postgres://` |
| `COOKIE_SECURE` | Set to `true` |
| `FLASK_DEBUG` | Set to `false` |
| `MAIL_SERVER` | Required SMTP hostname |
| `MAIL_DEFAULT_SENDER` | Required sender email address |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | Set both, or leave both empty if your SMTP provider does not require authentication |
| `AI_API_URL` | Required public HTTPS OpenAI-compatible endpoint; it must not be localhost |
| `AI_API_KEY` | Required key for the hosted AI provider |
| `AI_MODEL` | Required model name |
| `AI_TIMEOUT` | Optional; defaults to 30 seconds |

**Important:** Vercel cannot connect to Ollama running on your personal computer at `127.0.0.1`. Configure a hosted AI endpoint for production. Do not paste API keys, database passwords, or your `.env` file into GitHub.

After setting or changing environment variables, redeploy the project. Then open `/health`; a correctly configured app with a reachable database should return `{"status":"ok"}`.

## GitHub structure

Keep the whole project together in this folder. Do not move only `web_app.py` or `app.py` by themselves: the `aiwriter/`, `migrations/`, `public/`, and `templates/` folders are required at runtime.

Never commit `.env`, `.venv/`, local database files, API keys, or production credentials.
