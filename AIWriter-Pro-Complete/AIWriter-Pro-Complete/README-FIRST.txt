AIWRITER PRO — COMPLETE FLASK PROJECT

PROJECT CONTENTS
- web_app.py: Flask backend with signup, email verification, login/logout, dashboard,
  writing usage limits, plans, account settings and Ollama generation.
- templates/: all HTML templates used by Flask.
- static/: CSS and JavaScript.
- vercel.json: Vercel Python function routing.
- .env.example: safe environment-variable template. It contains no real credentials.

LOCAL WINDOWS SETUP
1. Extract the complete ZIP.
2. Open the extracted folder in VS Code.
3. Create a virtual environment (optional but recommended):
   py -m venv .venv
   .venv\Scripts\activate
4. Install dependencies:
   pip install -r requirements.txt
5. Copy .env.example to .env and set a strong SECRET_KEY.
6. For email OTP, configure MAIL_USERNAME, MAIL_PASSWORD (Gmail App Password),
   and MAIL_DEFAULT_SENDER. Do not share or upload .env.
7. For local AI generation, install/run Ollama and pull the configured model:
   ollama pull llama3.2:1b
8. Run:
   py web_app.py
9. Open http://127.0.0.1:5000

VERCEL NOTES
- The code uses /tmp for SQLite on serverless deployments so it does not try to write
  into Vercel's read-only /var/task directory.
- /tmp is temporary. User accounts and generated text may disappear between instances
  or deployments. Use a persistent hosted database before relying on real users.
- Local Ollama at 127.0.0.1 will NOT be available to a Vercel-hosted app. Configure a
  hosted AI API or a remotely reachable model and update the backend accordingly.
- Set SECRET_KEY and mail variables in Vercel Project Settings > Environment Variables.
- Set COOKIE_SECURE=1 on HTTPS production.
- Do not upload .env to GitHub. If any real credentials were ever public, rotate them.

SECURITY / PAYMENT
- Paid plans are display/usage tiers only. The /upgrade route does not take payment
  and will not grant paid access without a verified payment integration.
