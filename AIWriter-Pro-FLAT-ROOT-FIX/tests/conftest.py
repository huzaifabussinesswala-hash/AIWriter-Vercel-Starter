import os
import tempfile
import pytest
from web_app import create_app, init_db

@pytest.fixture()
def app(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + path)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.delenv("VERCEL", raising=False)
    # Module engine is created at import time; tests use the same configured engine only if import happens after env setup.
    from sqlalchemy import create_engine, text
    import web_app
    old_engine = web_app.engine
    web_app.engine = create_engine("sqlite:///" + path, future=True)
    web_app.init_db()
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "test-secret"})
    yield app
    web_app.engine.dispose()
    web_app.engine = old_engine
    try: os.remove(path)
    except OSError: pass

@pytest.fixture()
def client(app):
    return app.test_client()
