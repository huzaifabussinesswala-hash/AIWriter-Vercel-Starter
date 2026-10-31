"""Database access layer.

PostgreSQL (psycopg 3) is the production engine. SQLite is supported for local
development and tests only. SQL is written once with ``?`` placeholders and kept to
the common subset of both engines; the layer translates placeholders, timestamps and
booleans.

All timestamps are stored and compared in UTC.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

try:  # psycopg is required in production; optional for SQLite-only development.
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only where psycopg is absent
    psycopg = None
    dict_row = None

log = logging.getLogger(__name__)

SQLITE_TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f+00:00"
MIGRATION_LOCK_ID = 727274
_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.(postgresql|sqlite)\.sql$")


class DBError(Exception):
    """Any database failure (connection, query, ...). Never carries query parameters."""


class DBIntegrityError(DBError):
    """Constraint violation (for example a duplicate email)."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_dt(value):
    """Return an aware UTC datetime from a datetime, ISO string or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    return to_utc(datetime.fromisoformat(str(value)))


def _convert_row(row):
    if row is None:
        return None
    out = dict(row)
    for key, value in out.items():
        if key.endswith("_at"):
            out[key] = parse_dt(value)
        elif key == "email_verified":
            out[key] = bool(value)
    return out


def _wrap_error(exc: Exception) -> DBError:
    integrity = [sqlite3.IntegrityError]
    if psycopg is not None:
        integrity.append(psycopg.IntegrityError)
    detail = type(exc).__name__
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate:
        detail += f" (SQLSTATE {sqlstate})"
    cls = DBIntegrityError if isinstance(exc, tuple(integrity)) else DBError
    return cls(f"database error: {detail}")


class Result:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return _convert_row(self._cursor.fetchone())

    def fetchall(self):
        return [_convert_row(r) for r in self._cursor.fetchall()]

    def scalar(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return next(iter(dict(row).values()))

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class Connection:
    """Thin wrapper translating portable SQL for the underlying engine."""

    def __init__(self, raw, dialect: str):
        self._raw = raw
        self.dialect = dialect

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgresql" else sql

    def _params(self, params):
        out = []
        for value in params:
            if isinstance(value, datetime):
                value = to_utc(value)
                if self.dialect == "sqlite":
                    value = value.strftime(SQLITE_TS_FORMAT)
            out.append(value)
        return tuple(out)

    def execute(self, sql: str, params=()) -> Result:
        params = self._params(params)
        sql = self._sql(sql)
        try:
            # Statements without parameters are sent as-is (no placeholder parsing).
            cursor = self._raw.execute(sql, params) if params else self._raw.execute(sql)
        except Exception as exc:  # noqa: BLE001 - normalised to DBError
            raise _wrap_error(exc) from exc
        return Result(cursor)

    def lock_user(self, user_id: int):
        """Serialise concurrent work for one user (row lock on PostgreSQL)."""
        suffix = " FOR UPDATE" if self.dialect == "postgresql" else ""
        return self.execute(f"SELECT id FROM users WHERE id = ?{suffix}", (user_id,)).fetchone()


class Database:
    def __init__(self, url: str):
        if not url:
            raise DBError("database error: DATABASE_URL is empty")
        self.url = url
        scheme = urlparse(url).scheme.lower()
        if scheme in ("postgresql", "postgres"):
            if psycopg is None:
                raise DBError("database error: psycopg is not installed")
            self.dialect = "postgresql"
            # psycopg only understands the "postgresql" scheme.
            self._pg_url = "postgresql://" + url.split("://", 1)[1]
        elif scheme == "sqlite":
            self.dialect = "sqlite"
            path = unquote(urlparse(url).path)
            path = path[1:] if path.startswith("/") else path
            if not path or path == ":memory:":
                raise DBError("database error: in-memory SQLite does not persist between connections")
            self._sqlite_path = path
        else:
            raise DBError(f"database error: unsupported DATABASE_URL scheme '{scheme}'")

    def _connect(self):
        if self.dialect == "postgresql":
            return psycopg.connect(self._pg_url, row_factory=dict_row, connect_timeout=10)
        path = Path(self._sqlite_path)
        if path.parent and str(path.parent) != ".":
            path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(self._sqlite_path, timeout=10, isolation_level=None)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        return raw

    @contextmanager
    def connection(self):
        """Yield a transactional connection: commit on success, roll back on any error."""
        try:
            raw = self._connect()
        except Exception as exc:  # noqa: BLE001
            raise _wrap_error(exc) from exc
        try:
            if self.dialect == "sqlite":
                raw.execute("BEGIN IMMEDIATE")
            conn = Connection(raw, self.dialect)
            try:
                yield conn
                raw.execute("COMMIT") if self.dialect == "sqlite" else raw.commit()
            except BaseException:
                try:
                    raw.execute("ROLLBACK") if self.dialect == "sqlite" else raw.rollback()
                except Exception:  # noqa: BLE001
                    log.exception("rollback failed")
                raise
        except DBError:
            raise
        except (sqlite3.Error, *( (psycopg.Error,) if psycopg else () )) as exc:
            raise _wrap_error(exc) from exc
        finally:
            try:
                raw.close()
            except Exception:  # noqa: BLE001
                pass

    def ping(self) -> bool:
        with self.connection() as conn:
            return conn.execute("SELECT 1").scalar() == 1


# --------------------------------------------------------------------------- migrations

def discover_migrations(directory: Path, dialect: str):
    """Return [(version, name, path)] for ``dialect`` sorted by version."""
    found = []
    for path in Path(directory).iterdir():
        match = _MIGRATION_RE.match(path.name)
        if match and match.group(3) == dialect:
            found.append((match.group(1), match.group(2), path))
    return sorted(found)


def split_statements(script: str):
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def run_migrations(db: Database, directory) -> list:
    """Apply pending migrations in order. Idempotent; never drops or recreates data."""
    applied_now = []
    with db.connection() as conn:
        if db.dialect == "postgresql":
            conn.execute("SELECT pg_advisory_xact_lock(%d)" % MIGRATION_LOCK_ID)
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                     "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for version, name, path in discover_migrations(Path(directory), db.dialect):
            if version in done:
                continue
            for statement in split_statements(path.read_text(encoding="utf-8")):
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                         (version, utcnow().isoformat()))
            applied_now.append(f"{version}_{name}")
            log.info("Applied migration %s_%s", version, name)
    return applied_now
