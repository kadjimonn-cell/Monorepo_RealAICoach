# DEPLOY ENVIRONMENT VARIABLES CHECKLIST — Web Management Platform (visa-polish-v2 shared DB)

Set these in: **Deploy button → Publishing Panel → Environment Variables** (panel values OVERRIDE backend/.env at deploy time — confirmed by Emergent support 2026-07-16).

## 1. REQUIRED — Database (points this deployment at the SAME production DB)

MONGO_URL=mongodb+srv://visa-polish-v2:d9bf8q5dkjgc73fceeig@customer-apps.ralxxc.mongodb.net/?retryWrites=true&w=majority&appName=visa-polish-v2&maxPoolSize=5

DB_NAME=visa-polish-v2
# ⚠️ VERIFY THIS FIRST: check the OLD visa-polish-v2 deployment's Environment Variables /
# Database tab for its DB_NAME value and use EXACTLY that. Code default is "realtalk_db".
# Wrong DB_NAME = app boots against an empty database (looks like all data is gone).

## 2. RECOMMENDED — Production URL overrides
# backend/.env values point at the dev preview host. For the deployed app, set these to
# your production host (realaicoach.app, a subdomain like manage.realaicoach.app, or the
# new deployment's *.emergent.host URL):

FRONTEND_BASE_URL=https://<production-host>
RESET_LINK_BASE=https://<production-host>/auth/reset-password
VERIFY_LINK_BASE=https://<production-host>/api/auth/verify
GOOGLE_OAUTH_REDIRECT_URI=https://<production-host>/api/oauth/calendar/callback
SSO_REDIRECT_BASE_URL=https://<production-host>
SSO_CANONICAL_REDIRECT_BASE=https://<production-host>
MS_SSO_CANONICAL_REDIRECT_BASE=https://<production-host>
APPLE_SSO_CANONICAL_REDIRECT_BASE=https://<production-host>

# Note: Google/Microsoft/Apple SSO will only work on hosts registered in those providers'
# consoles. realaicoach.app is already registered (used by the existing deployment);
# a brand-new host would need to be added at each provider.

## 3. ALREADY COVERED — no action needed
# All API keys/secrets (Stripe, PayPal, Resend, FedaPay, Google/Apple SSO, JWT, VAPID,
# EMERGENT_LLM_KEY, field encryption key, admin emails) are present in backend/.env and
# carry into the deployment automatically.
# Frontend backend-URL: the platform wires the deployed frontend to its own /api origin.

## 4. FACTS VERIFIED (2026-07-16)
- Dev/preview pods CANNOT reach customer-apps.ralxxc.mongodb.net (TCP 27017 filtered;
  IP-allowlist admits deployed infra only). Preview therefore stays on local MongoDB —
  this is a platform restriction, not a choice.
- Panel env vars override backend/.env at deploy: confirmed by support.
- Deployment readiness check: PASS (zero findings).
