-- AIWriter Pro initial schema (SQLite, local development and tests only). Idempotent.
-- Timestamps are stored as fixed-format UTC strings so they sort and compare correctly.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash TEXT NOT NULL,
    plan VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'business')),
    created_at TEXT NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT 0,
    verification_code_hash TEXT,
    verification_expires_at TEXT,
    verification_attempts INTEGER NOT NULL DEFAULT 0 CHECK (verification_attempts >= 0),
    verification_last_sent_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email);

CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    writing_type VARCHAR(40) NOT NULL,
    prompt TEXT NOT NULL,
    output_language VARCHAR(40) NOT NULL,
    tone VARCHAR(40) NOT NULL,
    length VARCHAR(20) NOT NULL,
    generated_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_generations_user_created ON generations (user_id, created_at);
