# AIWriter Studio

A Flask-based AI writing SaaS with a redesigned responsive interface. Existing product flows are retained: signup with email verification codes, login/logout, AI generation, saved generation history, usage limits, plans and account settings.

## Project layout

Keep the **contents of this folder** at the GitHub repository root. `web_app.py`, `pyproject.toml` and `requirements.txt` must be visible directly on the repository's main page.

```text
web_app.py
aiwriter/
migrations/
templates/
public/assets/style.css
public/assets/app.js
requirements.txt
requirements-dev.txt
pyproject.toml
.env.example
```

Do not upload `.venv`, `.env`, local databases, or a parent folder around these files.

## Run locally on Windows

Use Python 3.12 or 3.13 for the smoothest dependency compatibility.

1. Open this project folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

4. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

5. Install the packages:

   ```powershell
   python -m pip install -r requirements-dev.txt
   ```

6. Optional: copy `.env.example` to `.env` and configure an AI provider. For local testing, the app can use a local SQLite database automatically. AI generation requires a valid provider URL, API key, and model, or a compatible provider configured in `.env`.
7. Initialize the database:

   ```powershell
   python -m flask --app web_app init-db
   ```

8. Start the app:

   ```powershell
   python web_app.py
   ```

9. Open `http://127.0.0.1:5000/`.

If PowerShell blocks virtual-environment activation, use the VS Code terminal dropdown to choose **Command Prompt**, then run `.venv\Scripts\activate.bat` instead.

## Vercel deployment

The Vercel entrypoint is configured as `web_app:app` in `pyproject.toml`. Import the repository with its root directory set to the directory containing `web_app.py`. Production requires the environment variables described in `.env.example`, including a reachable PostgreSQL database, a strong `SECRET_KEY`, email settings, and a reachable AI provider. Never commit real secrets.

## Notes

- Online payment processing is not enabled in this starter; paid plan cards are informational until a payment provider is integrated.
- Email delivery depends on valid SMTP settings.
- Generated text should be reviewed before publication.
- The updated layout and Python syntax were checked. Full automated tests could not be run in the build environment because Flask is not installed there; install dependencies first, then run `python -m pytest`.

## Local Ollama + Neon PostgreSQL setup

1. Install Ollama from https://ollama.com/download/windows and confirm `ollama --version` works in a new terminal.
2. Download a model, for example `ollama pull qwen3:1.7b`, then test with `ollama run qwen3:1.7b`.
3. Copy `.env.example` to `.env` and generate a secret with:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

4. Set `AI_API_URL=http://127.0.0.1:11434/v1`, `AI_API_KEY=` (blank for local Ollama), `AI_MODEL=qwen3:1.7b`, and `AI_TIMEOUT=120`.
5. For Neon, create a PostgreSQL project in https://console.neon.tech/, copy its connection string from **Connect**, and put it in `DATABASE_URL`. Keep `sslmode=require` in the connection string. For local-only testing, the SQLite default is sufficient.
6. Initialize the database with `python -m flask --app web_app init-db`, then start with `python web_app.py`.

**Deployment warning:** `127.0.0.1` points to the user's own machine. It will not reach your laptop from Vercel. Keep local Ollama for development; production needs a separately hosted, securely reachable AI endpoint. Never expose an unauthenticated Ollama port to the public internet.

## Expanded writing tools

The writing-type selector includes long-form articles, SEO articles and content briefs, landing pages, sales emails, brand stories, video scripts, and e-commerce product descriptions. The generator still uses the same server-side validation, plan limits, generation history, and AI provider adapter.
