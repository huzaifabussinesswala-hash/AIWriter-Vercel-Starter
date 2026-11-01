"""SQL queries. Portable SQL only (``?`` placeholders, no engine-specific functions)."""
from __future__ import annotations

# --------------------------------------------------------------------------- users


def get_user_by_id(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(conn, email):
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_user(conn, name, email, password_hash, now):
    return conn.execute(
        "INSERT INTO users (name, email, password_hash, plan, created_at, email_verified, "
        "verification_attempts) VALUES (?, ?, ?, 'free', ?, ?, 0) RETURNING id",
        (name, email, password_hash, now, False),
    ).scalar()


def delete_unverified_user(conn, user_id):
    conn.execute("DELETE FROM users WHERE id = ? AND email_verified = ?", (user_id, False))


def update_unverified_signup(conn, user_id, name, password_hash):
    conn.execute("UPDATE users SET name = ?, password_hash = ? WHERE id = ? AND email_verified = ?",
                 (name, password_hash, user_id, False))


def store_verification(conn, user_id, code_hash, expires_at, sent_at):
    """Store a fresh OTP hash (invalidating any previous one) and reset the attempt counter."""
    conn.execute(
        "UPDATE users SET verification_code_hash = ?, verification_expires_at = ?, "
        "verification_attempts = 0, verification_last_sent_at = ? WHERE id = ?",
        (code_hash, expires_at, sent_at, user_id))


def clear_verification_code(conn, user_id):
    conn.execute("UPDATE users SET verification_code_hash = NULL, verification_expires_at = NULL "
                 "WHERE id = ?", (user_id,))


def bump_verification_attempts(conn, user_id):
    conn.execute("UPDATE users SET verification_attempts = verification_attempts + 1 WHERE id = ?",
                 (user_id,))
    return conn.execute("SELECT verification_attempts FROM users WHERE id = ?", (user_id,)).scalar()


def mark_verified(conn, user_id):
    conn.execute(
        "UPDATE users SET email_verified = ?, verification_code_hash = NULL, "
        "verification_expires_at = NULL, verification_attempts = 0 WHERE id = ?", (True, user_id))


def update_name(conn, user_id, name):
    conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))


def update_password(conn, user_id, password_hash):
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


# --------------------------------------------------------------------------- generations


def insert_generation(conn, user_id, writing_type, prompt, output_language, tone, length,
                      generated_text, now):
    return conn.execute(
        "INSERT INTO generations (user_id, writing_type, prompt, output_language, tone, length, "
        "generated_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (user_id, writing_type, prompt, output_language, tone, length, generated_text, now),
    ).scalar()


def count_generations(conn, user_id, start=None, end=None):
    """Count a user's saved generations, optionally within [start, end) (UTC)."""
    sql = "SELECT COUNT(*) FROM generations WHERE user_id = ?"
    params = [user_id]
    if start is not None:
        sql += " AND created_at >= ?"
        params.append(start)
    if end is not None:
        sql += " AND created_at < ?"
        params.append(end)
    return int(conn.execute(sql, params).scalar() or 0)


def recent_generations(conn, user_id, limit=5, offset=0):
    return conn.execute(
        "SELECT * FROM generations WHERE user_id = ? ORDER BY created_at DESC, id DESC "
        "LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()


def get_generation(conn, user_id, generation_id):
    return conn.execute("SELECT * FROM generations WHERE id = ? AND user_id = ?",
                        (generation_id, user_id)).fetchone()
