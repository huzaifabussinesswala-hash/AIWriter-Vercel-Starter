import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aiwriter import repo
from aiwriter.db import (Connection, Database, DBError, DBIntegrityError, discover_migrations,
                         parse_dt, run_migrations, split_statements)

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def table_columns(db, table):
    with db.connection() as conn:
        if db.dialect == "sqlite":
            return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    raise AssertionError("sqlite only")


def test_migrations_create_required_tables_and_columns(db):
    assert table_columns(db, "users") == {
        "id", "name", "email", "password_hash", "plan", "created_at", "email_verified",
        "verification_code_hash", "verification_expires_at", "verification_attempts",
        "verification_last_sent_at"}
    assert table_columns(db, "generations") == {
        "id", "user_id", "writing_type", "prompt", "output_language", "tone", "length",
        "generated_text", "created_at"}


def test_migrations_create_indexes(db):
    with db.connection() as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()}
    assert {"ux_users_email", "ix_generations_user_created"} <= names


def test_migrations_are_idempotent_and_preserve_data(db):
    with db.connection() as conn:
        user_id = repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
    assert run_migrations(db, MIGRATIONS) == []  # nothing pending the second time
    with db.connection() as conn:
        assert repo.get_user_by_id(conn, user_id)["email"] == "ann@example.com"
        versions = [r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()]
    assert versions == ["0001"]


def test_data_persists_across_separate_database_objects(db, settings):
    with db.connection() as conn:
        repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
    other = Database(settings.database_url)  # what a new serverless invocation would do
    with other.connection() as conn:
        assert repo.get_user_by_email(conn, "ann@example.com") is not None


def test_duplicate_email_raises_integrity_error(db):
    with db.connection() as conn:
        repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
    with pytest.raises(DBIntegrityError):
        with db.connection() as conn:
            repo.create_user(conn, "Ann 2", "ann@example.com", "hash", NOW)


def test_failed_transaction_is_rolled_back(db):
    with pytest.raises(RuntimeError):
        with db.connection() as conn:
            repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
            raise RuntimeError("boom")
    with db.connection() as conn:
        assert repo.get_user_by_email(conn, "ann@example.com") is None


def test_foreign_key_and_plan_constraints(db):
    with pytest.raises(DBIntegrityError):
        with db.connection() as conn:
            repo.insert_generation(conn, 999, "general", "p", "english", "friendly", "short", "t", NOW)
    with pytest.raises(DBIntegrityError):
        with db.connection() as conn:
            uid = repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
            conn.execute("UPDATE users SET plan = ? WHERE id = ?", ("platinum", uid))


def test_timestamps_round_trip_as_aware_utc(db):
    with db.connection() as conn:
        uid = repo.create_user(conn, "Ann", "ann@example.com", "hash", NOW)
        user = repo.get_user_by_id(conn, uid)
    assert user["created_at"] == NOW
    assert user["created_at"].tzinfo is not None
    assert user["email_verified"] is False


def test_non_utc_input_is_normalised_to_utc(db):
    plus5 = timezone(timedelta(hours=5))
    local = datetime(2026, 10, 25, 17, 0, 0, tzinfo=plus5)
    with db.connection() as conn:
        uid = repo.create_user(conn, "Ann", "ann@example.com", "hash", local)
        assert repo.get_user_by_id(conn, uid)["created_at"] == NOW
    assert parse_dt("2026-10-25 12:00:00.000000+00:00") == NOW
    assert parse_dt("2026-10-25T12:00:00") == NOW  # naive values are treated as UTC


def test_in_memory_sqlite_and_unknown_schemes_are_rejected():
    with pytest.raises(DBError):
        Database("sqlite:///:memory:")
    with pytest.raises(DBError):
        Database("mysql://u:p@h/db")
    with pytest.raises(DBError):
        Database("")


def test_connection_failure_is_wrapped(tmp_path):
    database = Database(f"sqlite:///{tmp_path}")  # a directory cannot be opened as a database file
    with pytest.raises(DBError):
        with database.connection():
            pass


# ----------------------------------------------------------- PostgreSQL compatibility


def test_postgres_migration_matches_sqlite_schema():
    def columns(path):
        text = path.read_text()
        out = {}
        for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", text, re.S):
            out[table] = {m.group(1) for m in re.finditer(r"^\s{4}(\w+) ", body, re.M)}
        return out

    pg = columns(MIGRATIONS / "0001_initial.postgresql.sql")
    lite = columns(MIGRATIONS / "0001_initial.sqlite.sql")
    assert pg == lite
    assert set(pg) == {"users", "generations"}


def test_postgres_migration_uses_postgres_types_and_no_sqlite_syntax():
    sql = (MIGRATIONS / "0001_initial.postgresql.sql").read_text()
    assert "TIMESTAMPTZ" in sql and "BIGSERIAL" in sql and "BOOLEAN" in sql
    assert "AUTOINCREMENT" not in sql
    assert "REFERENCES users (id) ON DELETE CASCADE" in sql


def test_every_dialect_has_the_same_migration_versions():
    pg = [v for v, _, _ in discover_migrations(MIGRATIONS, "postgresql")]
    lite = [v for v, _, _ in discover_migrations(MIGRATIONS, "sqlite")]
    assert pg == lite and pg


def test_application_sql_is_portable():
    forbidden = [r"AUTOINCREMENT", r"datetime\(", r"strftime", r"INSERT OR ", r"ON CONFLICT", r"ILIKE",
                 r"NOW\(\)", r"date_trunc", r"::", r"PRAGMA", r"%s", r"\$\d"]
    for module in ("repo.py", "otp.py", "usage.py"):
        source = (ROOT / "aiwriter" / module).read_text()
        for sql in re.findall(r'"((?:SELECT|INSERT|UPDATE|DELETE)[^"]*)"', source):
            for pattern in forbidden:
                assert not re.search(pattern, sql, re.I), (module, sql, pattern)
    repo_source = (ROOT / "aiwriter" / "repo.py").read_text()
    assert len(re.findall(r'"(?:SELECT|INSERT|UPDATE|DELETE)', repo_source)) >= 15


def test_placeholders_are_translated_for_postgres_only():
    pg = Connection(raw=None, dialect="postgresql")
    lite = Connection(raw=None, dialect="sqlite")
    sql = "SELECT * FROM users WHERE email = ? AND id = ?"
    assert pg._sql(sql) == "SELECT * FROM users WHERE email = %s AND id = %s"
    assert lite._sql(sql) == sql


def test_datetime_parameters_are_utc_aware_for_postgres_and_strings_for_sqlite():
    plus5 = datetime(2026, 10, 25, 17, 0, tzinfo=timezone(timedelta(hours=5)))
    pg_params = Connection(None, "postgresql")._params([plus5])
    assert pg_params[0] == NOW and pg_params[0].utcoffset() == timedelta(0)
    assert Connection(None, "sqlite")._params([plus5])[0] == "2026-10-25 12:00:00.000000+00:00"


def test_migration_statement_splitter_ignores_comments():
    script = "-- comment; with semicolon\nCREATE TABLE a (id INT);\n\nCREATE INDEX i ON a (id);\n"
    assert split_statements(script) == ["CREATE TABLE a (id INT)", "CREATE INDEX i ON a (id)"]
