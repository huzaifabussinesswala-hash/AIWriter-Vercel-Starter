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

def test_invalid_paddle_environment_disables_checkout():
    assert not billing_settings("unknown", "live_example").billing_ready


def test_same_price_id_cannot_be_used_for_both_paid_tiers():
    settings = load_settings({
        "APP_ENV": "testing",
        "PADDLE_ENVIRONMENT": "sandbox",
        "PADDLE_CLIENT_TOKEN": "test_example",
        "PADDLE_PRICE_PRO": "pri_same",
        "PADDLE_PRICE_BUSINESS": "pri_same",
        "PADDLE_WEBHOOK_SECRET": "secret",
    })
    assert not settings.billing_ready


def test_live_billing_portal_requires_live_api_key():
    settings = load_settings({
        "APP_ENV": "testing",
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_CLIENT_TOKEN": "live_example",
        "PADDLE_PRICE_PRO": "pri_pro_example",
        "PADDLE_PRICE_BUSINESS": "pri_business_example",
        "PADDLE_WEBHOOK_SECRET": "secret",
        "PADDLE_API_KEY": "pdl_live_apikey_example",
    })
    assert settings.billing_portal_ready


def test_sandbox_billing_portal_rejects_live_api_key():
    settings = load_settings({
        "APP_ENV": "testing",
        "PADDLE_ENVIRONMENT": "sandbox",
        "PADDLE_CLIENT_TOKEN": "test_example",
        "PADDLE_PRICE_PRO": "pri_pro_example",
        "PADDLE_PRICE_BUSINESS": "pri_business_example",
        "PADDLE_WEBHOOK_SECRET": "secret",
        "PADDLE_API_KEY": "pdl_live_apikey_example",
    })
    assert not settings.billing_portal_ready
