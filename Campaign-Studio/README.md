# Campaign Studio

A responsive editorial website and first-party email-OTP workspace for beauty ecommerce brands and agencies.

## Included
- Original responsive marketing site with SEO/social metadata and accessible account forms.
- Passwordless email OTP: hashed codes, 10-minute expiry, one-time use, resend cooldown and database-backed attempt limits.
- Secure HttpOnly session cookies; only token hashes are stored.
- Private customer project storage with per-user access checks and delete controls.
- Account deletion that cascades to saved projects and sessions.
- Daily cleanup endpoint for expired OTPs, sessions and rate-limit rows.
- Neon Postgres schema and Vercel serverless API routes.
- No fabricated testimonials, customer counts or performance claims.

## Required before production
1. Create a Neon Postgres database.
2. Run `database/schema.sql` once in the Neon SQL Editor.
3. Verify a sending domain with Resend. Set `EMAIL_FROM` to an address on that verified domain.
4. Add `DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM`, a random `OTP_SECRET` (32+ characters), and a separate `CRON_SECRET` in Vercel for Preview and Production.
5. Deploy and test: request code, receive email, verify code, reload session, create a project, sign out, and confirm another account cannot read it.
6. Replace draft legal pages with reviewed policies, business details and a monitored privacy contact.
7. Complete security, privacy, retention and deletion testing before public customer onboarding.

## Local preview
Open `index.html` to inspect the marketing page. API routes require Vercel Functions and configured environment variables.

## Security
- OTPs are stored only as HMAC digests; they expire after 10 minutes and are consumed after verification.
- IP and email attempt limits are stored in Postgres.
- Sessions use random tokens stored only as SHA-256 hashes and Secure HttpOnly cookies.
- Users should remove personal data from review uploads. Define retention, deletion and access-request procedures before launch.
- Never commit real credentials. Configure secrets in Vercel.
- Add a scheduled cleanup job for expired OTPs, sessions and old rate-limit rows.

## Current product boundary
Authentication and private project storage are implemented in code but remain inactive until environment variables, database schema and email delivery are configured. AI analysis, campaign generation, payments, team roles and exports are not implemented yet. Do not market these features as available until built and tested.

Privacy and Terms pages are drafts, not legal advice. Complete and review them before launch.
