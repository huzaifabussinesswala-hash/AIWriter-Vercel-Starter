AIWriter Pro — Vercel entrypoint structure

Upload the CONTENTS of this ZIP to the GitHub repository root (do not upload an enclosing folder).
Expected repository root:
  pyproject.toml
  vercel.json
  AIWriter-Pro-Postgres-Fix/web_app.py
  AIWriter-Pro-Postgres-Fix/requirements.txt
  AIWriter-Pro-Postgres-Fix/templates/
  AIWriter-Pro-Postgres-Fix/static/

Vercel Settings > Build and Deployment > Root Directory must be the repository root (empty/default), NOT the AIWriter-Pro-Postgres-Fix subfolder.
The pyproject.toml entrypoint follows Vercel's suggested value exactly.

Keep environment variables configured in Vercel: DATABASE_URL, SECRET_KEY, SMTP variables, and an accessible AI endpoint.
