AIWriter Pro — Email OTP + Show Password update

Included: Flask app, templates, static assets, and .env.example. Private .env, local virtual environment, and database are intentionally excluded.

INSTALL
1. Back up your current project folder and database.
2. Extract this ZIP. Copy web_app.py, requirements.txt, templates/, static/, and .env.example into your project, replacing matching source files.
3. Keep your existing .env and database. Add the MAIL_* variables shown in .env.example to your .env.
4. Google Account for aiwriter.support@gmail.com: enable 2-Step Verification, create an App Password at https://myaccount.google.com/apppasswords, and put that app password in MAIL_PASSWORD. Never use your normal Gmail password.
5. Run: pip install -r requirements.txt
6. Run: python web_app.py

SIGNUP FLOW
Signup sends a six-digit code to the submitted email. Code expires in 10 minutes, failed attempts are limited to five, and a resend option is available. A user record is created only after successful verification. Existing accounts in your existing database are preserved and can still log in.

SECURITY NOTES
- Keep .env private; never upload it to public repositories.
- SMTP must be configured before signup can send OTP.
- This package was syntax-checked, but you must test email delivery locally with your own Gmail App Password.
- Payments are not configured by this update.


EMAIL OTP VERIFICATION
---------------------
New signups must verify their email using a six-digit code. Codes expire after
10 minutes; resending is rate-limited to once every 60 seconds and incorrect
attempts are limited. Existing accounts in an older database are migrated as
already verified so they are not locked out.

To enable Gmail delivery, copy .env.example to .env if you do not already have
a .env file, then set:
MAIL_USERNAME=aiwriter.support@gmail.com
MAIL_PASSWORD=<your Google App Password>
MAIL_DEFAULT_SENDER=aiwriter.support@gmail.com
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true

Enable Google 2-Step Verification and create an App Password at
https://myaccount.google.com/apppasswords. Never use your normal Gmail password.
Do not share .env or commit it to Git. The app must be restarted after changing
.env. Verify SMTP delivery locally before launch.
