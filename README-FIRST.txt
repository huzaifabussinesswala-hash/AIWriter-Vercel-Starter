AIWRITER PRO — OTP EMAIL SETUP (EASY MODE)

1) Extract this whole folder somewhere easy, e.g. Desktop.
2) Open the AIWriter-Pro folder. Find the file named .env (not .env.example).
   If Windows hides it, enable View > Show > Hidden items in File Explorer.
3) Open .env with VS Code or Notepad.
4) Replace ONLY PASTE_YOUR_GOOGLE_APP_PASSWORD_HERE with the Google App Password
   created for aiwriter.support@gmail.com. Remove spaces from the App Password.
   Do not use your normal Gmail password. Do not add quotes.
5) Press Ctrl+S. Do not send anyone your password or .env file.
6) Double-click RUN_AIWRITER.bat. Wait for Flask to start.
7) Open http://127.0.0.1:5000 in your browser and test signup using an inbox you can access.

IMPORTANT
- web_app.py now loads .env from the same folder as the script, regardless of the terminal's current folder.
- This project folder contains a placeholder only, not your actual password. You must paste the App Password yourself.
- If your Ollama model is needed, make sure Ollama is running and llama3.2:1b is installed.
- Never upload .env publicly. The included SECRET_KEY is only for local testing; replace it before public deployment.
- If email still fails, copy the terminal error but never include any passwords or secret values.
