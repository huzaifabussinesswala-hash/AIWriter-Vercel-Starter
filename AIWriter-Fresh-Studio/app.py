"""Vercel's standard Flask entrypoint.

Keep the application implementation in web_app.py; this thin wrapper
lets Vercel discover the Flask instance using its conventional app.py name.
"""
from web_app import app

__all__ = ["app"]
