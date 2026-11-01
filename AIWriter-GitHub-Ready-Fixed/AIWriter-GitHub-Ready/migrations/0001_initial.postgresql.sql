-- AIWriter Pro initial schema (PostgreSQL). Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash TEXT NOT NULL,
    plan VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'business')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_code_hash TEXT,
    verification_expires_at TIMESTAMPTZ,
    verification_attempts INTEGER NOT NULL DEFAULT 0 CHECK (verification_attempts >= 0),
    verification_last_sent_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email);

CREATE TABLE IF NOT EXISTS generations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    writing_type VARCHAR(40) NOT NULL,
    prompt TEXT NOT NULL,
    output_language VARCHAR(40) NOT NULL,
    tone VARCHAR(40) NOT NULL,
    length VARCHAR(20) NOT NULL,
    generated_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_generations_user_created ON generations (user_id, created_at DESC);
