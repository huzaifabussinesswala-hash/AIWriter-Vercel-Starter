from aiwriter.config import load_settings


def billing_settings(paddle_environment="sandbox", token="test_example", webhook_secret="secret"):
    return load_settings({
        "APP_ENV": "testing",
        "PADDLE_ENVIRONMENT": paddle_environment,
        "PADDLE_CLIENT_TOKEN": token,
        "PADDLE_PRICE_PRO": "pri_pro_example",
        "PADDLE_PRICE_BUSINESS": "pri_business_example",
        "PADDLE_WEBHOOK_SECRET": webhook_secret,
    })


def test_sandbox_checkout_requires_test_token():
    assert billing_settings().billing_ready


def test_live_checkout_requires_live_token():
    assert billing_settings("production", "live_example").billing_ready


def test_test_token_cannot_enable_live_checkout():
    assert not billing_settings("production", "test_example").billing_ready


def test_live_token_cannot_enable_sandbox_checkout():
    assert not billing_settings("sandbox", "live_example").billing_ready


def test_checkout_requires_webhook_signing_secret():
    assert not billing_settings(webhook_secret="").billing_ready
