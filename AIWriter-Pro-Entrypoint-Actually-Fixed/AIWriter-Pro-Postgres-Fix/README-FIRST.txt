AIWriter Pro — PostgreSQL/Vercel OTP fix

Project root files:
- web_app.py
- requirements.txt
- vercel.json
- templates/
- static/

Important:
1. On Vercel, configure DATABASE_URL to a persistent PostgreSQL connection string from your database provider.
2. Keep the existing email variables configured:
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USERNAME=your Gmail address
   MAIL_PASSWORD=your Google App Password
   MAIL_DEFAULT_SENDER=your Gmail address
3. Configure SECRET_KEY as a long random secret in Vercel Environment Variables. Use the same value for every deployment/instance. Do not share it publicly.
4. Redeploy after setting environment variables.
5. This app uses PostgreSQL when DATABASE_URL is set. SQLite is retained for local development only. Vercel intentionally refuses to start without DATABASE_URL to avoid silently storing accounts/OTPs in temporary /tmp storage.
6. Database tables are created automatically on first startup. This does not copy existing accounts from a previous ephemeral SQLite database; those old test signups may need to sign up again.
7. Ollama at localhost is not reachable from Vercel. The app keeps the original Ollama integration; configure OLLAMA_URL to a publicly reachable secured inference API if you want AI generation to work in production.

Never paste database URLs, Gmail App Passwords, or SECRET_KEY into chat or public repositories.
