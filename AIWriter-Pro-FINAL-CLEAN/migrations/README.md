# Schema migrations

The application initializes missing tables without deleting existing records. For production schema evolution, add versioned Alembic migrations and apply them as a controlled deployment step. Do not run destructive migrations against production without backups.
