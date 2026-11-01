# AIWriter Studio — Complete local + Vercel project

This folder contains the project files at the correct repository root. Keep `web_app.py`, `pyproject.toml`, and `requirements.txt` at the root when uploading to GitHub.

## Included changes

- White sidebar theme and a working hide/show button with saved preference.
- Existing signup, email OTP, login, history, usage, plans, account and generation routes retained from the supplied project.
- Local Ollama configuration example using the OpenAI-compatible `/v1` endpoint.
- `check_local_ai.py` to test the configured AI connection without displaying secrets.
- `.env` and local database files are deliberately excluded from this ZIP. Do not commit your real `.env`.

## Windows local setup

Use Python 3.12 or 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Install Ollama from https://ollama.com/download/windows, then in PowerShell:

```powershell
ollama pull qwen3:1.7b
ollama list
```

Ollama normally runs as a background service on Windows. If it is not running, start it from the Start menu or run:

```powershell
ollama serve
```

In a second terminal, copy `.env.example` to `.env` if you do not already have your own `.env`:

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in your own `SECRET_KEY`, email/SMTP values and any database settings you already use. For local Ollama, these values should be:

```env
APP_ENV=development
AI_API_URL=http://127.0.0.1:11434/v1
AI_API_KEY=
AI_MODEL=qwen3:1.7b
AI_TIMEOUT=120
```

Do not replace your existing working email or Neon database credentials with placeholders. Keep `.env` on your computer only.

Test Ollama before starting the web app:

```powershell
python check_local_ai.py
```

If the test succeeds, initialize the database if needed and start Flask:

```powershell
python -m flask --app web_app init-db
python web_app.py
```

Open http://127.0.0.1:5000/ and sign in. Generate a short draft to confirm the full app flow.

## GitHub upload

Upload the **contents of this folder** to the root of the GitHub repository. Do not upload the parent folder as an extra nested layer. Do not upload `.env`, `.venv`, `instance/`, or database files.

## Vercel

The project entrypoint remains `web_app:app`. Local Ollama at `127.0.0.1` works only on the computer running the app; Vercel cannot access your laptop's localhost. For Vercel production, configure a separate public HTTPS AI endpoint and API key in Vercel Environment Variables, plus the production database, mail and secret settings. Never set Vercel's AI URL to `127.0.0.1`.

## Validation note

Python source compilation and the base Jinja template syntax were checked while preparing this folder. The full pytest suite could not be executed in the preparation environment because Flask is not installed there; install `requirements-dev.txt` before running `python -m pytest`.
