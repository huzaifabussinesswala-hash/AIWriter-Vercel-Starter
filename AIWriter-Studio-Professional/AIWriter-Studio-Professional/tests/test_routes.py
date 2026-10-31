import re
import tomllib
from pathlib import Path

from flask import Flask

from aiwriter.db import DBError

from conftest import register_and_login

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def test_application_imports_and_exports_flask_instance_named_app():
    import web_app
    assert isinstance(web_app.app, Flask)


def test_vercel_entrypoint_points_at_a_real_module_and_flask_variable():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    module_path, _, variable = config["tool"]["vercel"]["entrypoint"].partition(":")
    assert variable == "app"
    assert (ROOT / (module_path.replace(".", "/") + ".py")).is_file()
    import importlib
    assert isinstance(getattr(importlib.import_module(module_path), variable), Flask)
    assert not (ROOT / "vercel.json").exists()  # one authoritative configuration only
    assert not (ROOT / "app.py").exists() and not (ROOT / "index.py").exists()


def test_every_url_for_endpoint_exists(app):
    sources = [ROOT / "web_app.py", *TEMPLATES.glob("*.html")]
    referenced = set()
    for path in sources:
        referenced |= set(re.findall(r"url_for\(\s*['\"]([\w.]+)['\"]", path.read_text()))
    assert referenced
    missing = referenced - set(app.view_functions)
    assert not missing, missing


def test_every_template_exists_and_compiles(app):
    names = set(re.findall(r"render_template\(\s*['\"]([\w./]+)['\"]", (ROOT / "web_app.py").read_text()))
    names |= {p.name for p in TEMPLATES.glob("*.html")}
    for name in names:
        assert (TEMPLATES / name).is_file(), name
        app.jinja_env.get_template(name)  # raises on syntax errors
    for path in TEMPLATES.glob("*.html"):  # {% extends %} / {% from %} targets
        for target in re.findall(r"\{%\s*(?:extends|from|include|import)\s+['\"]([\w./]+)['\"]", path.read_text()):
            assert (TEMPLATES / target).is_file(), (path.name, target)


def test_static_assets_referenced_by_templates_exist(client):
    html = client.get("/").get_data(as_text=True)
    hrefs = re.findall(r'(?:href|src)="(/[^"#?]*\.(?:css|js))"', html)
    assert sorted(hrefs) == ["/assets/app.js", "/assets/style.css"]
    for href in hrefs:
        response = client.get(href)
        assert response.status_code == 200, href
        assert (ROOT / "public" / href.lstrip("/")).is_file()  # public/assets/... is what Vercel serves
    assert not (ROOT / "static").exists()  # Vercel ignores Flask's static folder; assets live in public/


def test_javascript_selectors_match_template_elements():
    js = (ROOT / "public" / "assets" / "app.js").read_text()
    templates = "\n".join(p.read_text() for p in TEMPLATES.glob("*.html"))
    for element_id in set(re.findall(r"getElementById\('([\w-]+)'\)", js)):
        assert f'id="{element_id}"' in templates, element_id


def test_buttons_declare_a_type_and_forms_declare_method_and_csrf():
    for path in TEMPLATES.glob("*.html"):
        text = path.read_text()
        for button in re.findall(r"<button\b[^>]*>", text):
            assert "type=" in button, (path.name, button)
        for form in re.finditer(r"<form\b([^>]*)>(.*?)</form>", text, re.S):
            assert 'method="post"' in form.group(1), (path.name, form.group(1))
            assert "csrf" in form.group(2), (path.name, "missing CSRF token")


def test_home_and_public_pages_render(client):
    for path in ("/", "/plans", "/login", "/signup", "/signin"):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200, path
    assert "AIWriter Pro" in client.get("/").get_data(as_text=True)


def test_security_headers_are_set(client):
    response = client.get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_no_inline_scripts_or_styles_that_the_csp_would_block():
    for path in TEMPLATES.glob("*.html"):
        text = path.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)", text), path.name
        assert " style=" not in text and "<style" not in text, path.name
        assert not re.search(r"\son\w+=", text), path.name


def test_unknown_page_returns_friendly_404(client):
    response = client.get("/definitely-not-here")
    assert response.status_code == 404 and "Page not found" in response.get_data(as_text=True)


def test_health_endpoint_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.get_json() == {"status": "ok"}


def test_health_endpoint_reports_database_outage_without_details(client, monkeypatch):
    from aiwriter.db import Database

    def down(self):
        raise DBError("database error: OperationalError")

    monkeypatch.setattr(Database, "ping", down)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json() == {"status": "degraded", "database": "unavailable"}


def test_misconfigured_production_app_fails_safely():
    from web_app import create_app
    app = create_app({"APP_ENV": "production"})
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 503
    assert "not fully configured" in response.get_data(as_text=True)
    assert "SECRET_KEY" not in response.get_data(as_text=True)  # details go to logs, not visitors
    health = client.get("/health")
    assert health.status_code == 503 and health.get_json() == {"status": "misconfigured"}


def test_database_outage_shows_friendly_page_not_a_stack_trace(logged_in, monkeypatch):
    from aiwriter import repo

    def down(conn, *args, **kwargs):
        raise DBError("database error: OperationalError")

    monkeypatch.setattr(repo, "recent_generations", down)
    response = logged_in.get("/dashboard")
    html = response.get_data(as_text=True)
    assert response.status_code == 503 and "Traceback" not in html and "try again" in html
    assert logged_in.get("/account").status_code == 200


def test_secret_key_is_stable_across_app_instances(env):
    from web_app import create_app
    assert create_app(env).config["SECRET_KEY"] == create_app(env).config["SECRET_KEY"] == env["SECRET_KEY"]


def test_no_hardcoded_secrets_or_localhost_endpoints_in_source():
    for path in [ROOT / "web_app.py", *(ROOT / "aiwriter").glob("*.py"), *(ROOT / "public" / "assets").glob("*"),
                 *TEMPLATES.glob("*.html")]:
        text = path.read_text()
        assert "11434" not in text, path.name
        assert not re.search(r"sk-[A-Za-z0-9]{20,}", text), path.name
        assert not re.search(r"postgres(?:ql)?://\w+:[^@\s{<]+@", text), path.name
