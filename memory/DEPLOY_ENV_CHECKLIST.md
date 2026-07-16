# DEPLOY ENVIRONMENT VARIABLES CHECKLIST — RealAICoach Web Platform
# UPDATED 2026-07-16 (deploy slot: spotify-style-2). This is the single source of truth.
# Set these in: Deploy button -> Publishing Panel -> Environment Variables
# (panel values OVERRIDE backend/.env at deploy time — confirmed by Emergent support 2026-07-16).

## 1. REQUIRED — Database
MONGO_URL=mongodb+srv://spotify-style-2:d9ck125dkjgc73bg1u6g@customer-apps.rcho5e.mongodb.net/?retryWrites=true&w=majority&appName=spotify-style-2&maxPoolSize=5
# VALIDATED 2026-07-16: URI parses clean with the backend's pymongo/motor stack; no db in
# the path (correct — the code reads the database from DB_NAME separately). SRV DNS
# resolves (cluster exists). Direct connect from preview pod is blocked by the Atlas IP
# allowlist — EXPECTED, deployed infra is allowlisted; not a blocker.

DB_NAME=visa-polish-v2
# !! VERIFY FIRST — the cluster CHANGED. The old checklist pointed at cluster
# customer-apps.ralxxc (user visa-polish-v2); the new string is cluster customer-apps.rcho5e
# (user spotify-style-2). If the spotify-style-2 deployment previously ran this app, its
# data is in whichever DB name it used on rcho5e — candidates: "visa-polish-v2" (old
# convention) or "realtalk_db" (code/.env default). Check in Atlas -> Browse Collections
# (rcho5e cluster) which DB actually holds collections, or check the old deployment's
# panel DB_NAME, and use EXACTLY that. Wrong DB_NAME = app boots against an empty DB.

## 2. REQUIRED — Runtime markers & policy overrides
ENVIRONMENT=production
# Makes runtime detection unambiguous:
#  - REQUIRED_SECRET_ENV enforcement active (all keys present -> passes)
#  - the preview email-suppression list (NONPROD_EMAIL_SUPPRESS_TEMPLATES_ALL_RECIPIENTS,
#    shipped in backend/.env) auto-disables in production — alerts flow normally
SECRET_VAULT_ENFORCE=false
# Required because backend/.env ships plaintext JWT_SECRET / RESEND_API_KEY /
# GOOGLE_CLIENT_SECRET; without this the prod boot hard-fails on the vault policy.
WEBHOOK_AUTO_SYNC_ENABLED=true
# CRITICAL: backend/.env ships =false (preview anti-hijack). Production MUST override to
# true so each prod boot re-points Stripe/Resend/PayPal/FedaPay webhooks to the
# production host automatically.

## 3. REQUIRED — Production URL overrides
# Use https://realaicoach.app IF the custom domain is attached to the spotify-style-2
# deployment (it is the SSO-registered + Apple-broker domain — strongly preferred).
# Otherwise substitute the deployment's *.emergent.host URL shown in the panel
# (note: Google/MS/Apple SSO will NOT complete on an unregistered host).
FRONTEND_BASE_URL=https://realaicoach.app
RESET_LINK_BASE=https://realaicoach.app/auth/reset-password
VERIFY_LINK_BASE=https://realaicoach.app/api/auth/verify
GOOGLE_OAUTH_REDIRECT_URI=https://realaicoach.app/api/oauth/calendar/callback
SSO_REDIRECT_BASE_URL=https://realaicoach.app
SSO_CANONICAL_REDIRECT_BASE=https://realaicoach.app
MS_SSO_CANONICAL_REDIRECT_BASE=https://realaicoach.app
APPLE_SSO_CANONICAL_REDIRECT_BASE=https://realaicoach.app

## 4. ALREADY COVERED — no panel action needed
# All API keys/secrets (Stripe/PayPal/FedaPay LIVE, Resend, Google/Apple SSO, JWT, VAPID,
# EMERGENT_LLM_KEY, field encryption key, admin accounts) ship in backend/.env.
# Frontend backend-URL: platform wires the deployed frontend to its own /api origin.

## 5. FACTS VERIFIED (2026-07-16)
- Panel env vars override backend/.env at deploy (Emergent support).
- Preview pods cannot reach Atlas (IP allowlist) — preview stays on local MongoDB.
- Build blockers fixed: kkiapay removed from requirements.txt (clean pip exit 0);
  export:web carries NODE_OPTIONS=--max-old-space-size=5632 (cold build exit 0, 354.6s).
- Webhooks re-pointed to https://realaicoach.app (Stripe we_1T4taJ..., Resend 0a272676,
  PayPal 09F7714599439745U, FedaPay 5719). Prod boots with WEBHOOK_AUTO_SYNC_ENABLED=true
  will keep them on the production host.
- RISK: the spotify-style-2 PREVIEW pod (old code, no auto-sync flag) can still re-hijack
  webhooks whenever it wakes, until that job is stopped or its keys rotated. Production
  self-corrects at every boot once deployed.
- SECURITY: the new MONGO_URL password was shared in chat — rotate the Atlas password
  after a successful deploy if this matters to you (update the panel value afterwards).
