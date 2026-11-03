# AIWriter Fresh Studio

This is a separate AIWriter application inside the repository. Its Vercel project uses this root directory:

`AIWriter-Fresh-Studio/`

The previous AIWriter project remains in its existing folder and is not modified by this application.

## Stack

- Flask application with secure authentication, email verification, AI generation, usage accounting and writing history.
- Public website, dashboard, writer workspace and design system.
- Static assets in `public/assets/`, served at `/assets/`.
- Vercel Python entrypoint: `app.py` → `web_app.py`.
- Paddle Billing checkout with signed webhook handling and subscription-to-user plan provisioning.

## Local setup

Use Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python web_app.py
```

Open `http://127.0.0.1:5000/`.

Use a dedicated production PostgreSQL database. SQLite files on serverless deployments are not persistent.

## Email verification / OTP

For Vercel production, the app supports Resend's HTTPS email API. Add `RESEND_API_KEY` and set `MAIL_DEFAULT_SENDER` to an address on a domain verified in Resend. When `RESEND_API_KEY` is present, OTP email uses Resend. If it is absent, the existing SMTP fallback uses `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER`.

Never put an API key or SMTP password in source code or commit a real `.env` file. OTP codes expire after 10 minutes, resend is rate-limited, and failed attempts are limited.

## Paddle Billing

The current implementation includes:
- Pro and Business monthly plan cards and Paddle overlay checkout.
- A signed custom-data reference that ties checkout to the authenticated AIWriter user.
- Webhook signature verification, event de-duplication, out-of-order event protection, and subscription-to-plan updates.
- Cancellation and subscription status handling in the webhook.

The current Vercel project is configured for **Paddle Sandbox**. Sandbox uses test cards and does not charge real money.

### Required environment variables

Keep each set of values within the same Paddle environment:

| Variable | Sandbox | Live |
|---|---|---|
| `PADDLE_ENVIRONMENT` | `sandbox` | `production` |
| `PADDLE_CLIENT_TOKEN` | `test_...` | `live_...` |
| `PADDLE_PRICE_PRO` | Sandbox Pro `pri_...` | Live Pro `pri_...` |
| `PADDLE_PRICE_BUSINESS` | Sandbox Business `pri_...` | Live Business `pri_...` |
| `PADDLE_WEBHOOK_SECRET` | Sandbox notification secret | Live notification secret |

The app now refuses to enable checkout when the selected environment and client-token prefix do not match. Do not copy Sandbox price IDs or webhook secrets into Live.

### Webhook endpoint

Configure the Paddle notification destination to call:

`https://ai-writer-pro-y3pe.vercel.app/webhooks/paddle`

Subscribe to:
- `transaction.completed`
- `subscription.created`
- `subscription.updated`
- `subscription.canceled`

The app verifies the `Paddle-Signature` header against the raw request body before accepting events.

### Sandbox-to-Live go-live checklist

Paddle Sandbox and Live are separate environments. Before accepting real payments:

1. Complete Paddle Live account verification.
2. Recreate the Pro and Business products/prices in Live. Record the new Live Price IDs; Sandbox IDs are not reusable.
3. Create a Live client-side token and a Live notification destination. Save the Live signing secret in Vercel.
4. Submit the exact website domain used for checkout under Paddle → My account → Settings → Website approval. Live checkout only works on approved domains.
5. Set the Live default payment link to an HTTPS page on that approved domain.
6. Publish accessible Terms & Conditions, Privacy Policy, and Refund/Cancellation Policy pages. Ensure displayed prices match the Live Paddle catalog and a support contact is reachable from the homepage.
7. Add payout details in Paddle, set all five Paddle variables above to Live values in Vercel Production, then redeploy.
8. Run a final low-value real transaction only after Paddle confirms the account and domain are approved. Confirm the webhook updates the correct AIWriter user and plan.

Do not set `PADDLE_ENVIRONMENT=production` while Sandbox credentials are still configured. This project does not currently create Paddle products, Live tokens, notification destinations, or customer-portal sessions automatically; those are created/configured in the Paddle dashboard.

## Paddle product/pricing

The plans page currently displays Pro at $11.99/month and Business at $29.99/month. Keep those amounts synchronized with the corresponding Paddle catalog prices. The app's webhook only grants a paid plan when the verified event's Price ID matches one of the configured plan Price IDs.


### Customer billing portal

To let signed-in customers manage subscriptions, update payment methods, and view invoices from Account settings, create a Paddle server-side API key in the same environment as checkout. Grant only `customer_portal_session.write`, then add it to Vercel as the encrypted production variable `PADDLE_API_KEY`. Live API keys use the `pdl_live_` prefix; Sandbox keys use `pdl_sdbx_`. The application creates a short-lived customer portal session on demand and never stores the generated portal URL. This key is separate from `PADDLE_CLIENT_TOKEN` and must never be exposed in browser code.

The webhook destination should subscribe to `transaction.completed`, `subscription.created`, `subscription.updated`, `subscription.canceled`, `subscription.activated`, `subscription.trialing`, `subscription.past_due`, `subscription.paused`, and `subscription.resumed`. The handler verifies Paddle signatures, deduplicates event IDs, ignores stale subscription events, and updates the plan from the subscription lifecycle.
