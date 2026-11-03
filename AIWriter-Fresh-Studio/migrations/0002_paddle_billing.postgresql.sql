-- Paddle subscription and webhook idempotency tables.
CREATE TABLE IF NOT EXISTS paddle_webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS paddle_subscriptions (
    paddle_subscription_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    paddle_customer_id TEXT,
    price_id TEXT NOT NULL,
    plan VARCHAR(20) NOT NULL CHECK (plan IN ('pro', 'business')),
    status VARCHAR(30) NOT NULL,
    current_period_end TIMESTAMPTZ,
    last_event_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_paddle_subscriptions_user_status
    ON paddle_subscriptions (user_id, status, updated_at DESC);
