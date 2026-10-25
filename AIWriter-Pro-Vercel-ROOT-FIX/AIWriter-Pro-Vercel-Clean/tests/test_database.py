def test_schema_created(app):
    from web_app import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        names = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars().all()
    assert "users" in names
    assert "generations" in names
