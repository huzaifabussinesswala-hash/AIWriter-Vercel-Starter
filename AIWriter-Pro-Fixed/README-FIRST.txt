AIWriter Pro — fixed repository package

PROJECT ROOT
Keep web_app.py, requirements.txt, vercel.json, templates/ and static/ together in the same Vercel Root Directory. This ZIP is flattened (no extra nested project folder).

VERCEL ENVIRONMENT VARIABLES
1. DATABASE_URL: persistent PostgreSQL connection string. Do not use SQLite on Vercel.
2. SECRET_KEY: long random secret (at least 32 characters); keep it stable across deployments.
3. COOKIE_SECURE=1
4. Email OTP variables: MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER.
5. AI generation on Vercel: AI_API_URL, AI_API_KEY, AI_MODEL for an OpenAI-compatible chat-completions API. Ollama localhost is only for local development; Vercel cannot reach Ollama on your PC.

After changing Vercel environment variables, redeploy. If a user was created in an old temporary SQLite database, sign up again on the new persistent PostgreSQL database.

IMPORTANT
Do not paste DATABASE_URL, AI_API_KEY, MAIL_PASSWORD, or SECRET_KEY into chat or commit real values to GitHub. Configure them in Vercel Environment Variables.

FIXES IN THIS PACKAGE
- Flattened repository layout for correct Vercel Root Directory detection.
- HTTPS secure session cookies enabled by default on serverless deployments; login sessions last 7 days.
- Added a warning log if a session references a user missing from the configured database.
- Fixed usage date queries to work with both SQLite and PostgreSQL.
- Added configurable OpenAI-compatible remote AI endpoint; local Ollama remains supported for local development.
- Preserved signup, OTP verification, login, dashboard, plans, account and generation history.
