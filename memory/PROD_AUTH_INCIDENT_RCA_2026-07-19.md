# RCA — "Users unable to register and login" (PRODUCTION) — 2026-07-19

Protocol: Checkpoints A-D (platform-locked). Investigator: E1 agent. Status: **NOT REPRODUCIBLE — production auth verified operational at every layer.**

## Checkpoint A — Reproduction attempts (PRODUCTION https://realaicoach.app, 23:20-23:45 UTC)

| Probe | Result |
|---|---|
| GET /api/health | 200 `{"status":"healthy","init":"complete"}` |
| POST /api/auth/register (throwaway `rca.probe.20260719@example.com`) | 200, user created, httpOnly session cookie set |
| POST /api/auth/login (throwaway) | 200 + session cookie |
| POST /api/auth/login (admin) | 200, `is_admin:true` |
| GET /auth/login HTML | 200, 141 KB, correct page |
| All 3 hashed JS bundles (`/_expo/static/js/web/...`) | 200, correct content-type (main 10.4 MB) |
| CORS w/ `Origin: https://realaicoach.app` | `allow-origin` echo + `allow-credentials: true` |
| **Real browser (Playwright/Chromium) desktop login** | Form fillable (no overlay: `elementFromPoint` = the input itself), submit → biometric enrollment prompt → "Not now" → **redirected to Dashboard**, `/api/auth/me` = 200 |
| **Real browser register UI** | Account created, authenticated (auth/me 200), redirected to `/subscription/payment?planId=basic...` (expected funnel) |
| **Mobile viewport (iPhone 13) login** | Submit visible, login OK, Dashboard reached, auth/me 200 |
| JS console errors | None beyond expected pre-login 401 on `/api/auth/me` bootstrap probe |

## Checkpoint B — Layer analysis & preview comparison

- Preview (localhost:8001) identical: register 200, login 200, admin login 200. Backend suite iteration_13: 13/13 PASS.
- **Production is running the Phase 2B build** (verified: `GET /api/auth/sso-config/native` responds on realaicoach.app) — the user's retry Re-publish succeeded and went live before the report.
- Layer verdict: network/ingress OK, backend OK, auth logic OK, DB connectivity OK (health + writes succeed), frontend HTML/bundles OK, browser runtime OK.
- Traps explicitly checked:
  - Token-redaction middleware on /api/auth/*: web responses correctly cookie-only; frontend session bootstrap via /api/auth/me works (probes reached Dashboard). Not broken.
  - Deferred init / admin seeding: health `init:complete`; admin login works with expected password → `ADMIN_PASSWORD_ENFORCE_SYNC` did NOT rotate anything unexpectedly.
  - Production risk gates / email verification: register grants an immediate session (no verification gate blocking); no OTP forced on the probe accounts.
  - Service worker: deployed sw.js is the hardened version (`realaicoach-v-7e15d8d9`): navigations are network-only (`no-store`), old caches evicted on activate, skipWaiting+claim with page reload on controller change. No stale-chunk lockout path.
  - deployment_agent static scan: PASS/WARN only; the flagged `auth.emergentagent.com` URL is the intentional Emergent Google auth broker (SSO fallback), unrelated to email/password register/login.

## Checkpoint C — Root cause assessment

No code-level defect is provable; production register/login are demonstrably functional from clean desktop, mobile-viewport, and API clients. Most probable explanations for the user reports, in order:

1. **Deploy-transition window disruption**: the Phase 2B Re-publish replaced every hashed bundle. Users with tabs open during the rollout experienced the SW "new controller took over" forced reload (wipes in-progress form input) and possible transient chunk/edge 404s while the deploy propagated. Self-healing: next navigation loads fresh assets.
2. **Post-login biometric enrollment modal**: after successful sign-in a "Would you like to use biometric login?" modal must be dismissed before redirect. Works in all probes, but it sits directly in the login completion path and can be perceived as "login stuck" by users who don't notice it (especially small screens).
3. Per-account lockouts (brute-force protection) for specific users — cannot be confirmed: production runtime logs are not retrievable from this environment (deployment_agent only performs static scans). If reports persist, this is the first thing to check in the production log console.

**No guess-edits were made to production code paths (per protocol).**

## Checkpoint D — Verification

- Production: register + login verified end-to-end AFTER investigation (browser + API, desktop + mobile viewport) — all pass.
- Preview: regression confirmed (register/login/admin 200; iteration_13 suite 13/13 previously green; no code changed during this RCA).

## Runbook if reports continue

1. Ask reporting users for: exact error text/screenshot, URL, browser+OS, timestamp, and whether a hard refresh (Ctrl/Cmd+Shift+R) fixes it.
2. Check production log console (platform dashboard) for 5xx/429/423 on /api/auth/* around the reported timestamps.
3. Check `security_events` collection (prod DB) for `login_failed` / lockout events for the affected emails.
4. If stale-asset symptoms are confirmed (console shows chunk 404s): instruct hard refresh; the SW self-heals on next sw.js fetch (<24 h).
5. Optional hardening (product decision, not applied): make the post-login biometric prompt non-blocking (toast/deferred), and suppress the SW takeover reload while a text input is focused.

## Probe artifacts / cleanup

- Throwaway accounts created on PRODUCTION: `rca.probe.20260719@example.com`, `rca.ui.<timestamp>@example.com` (basic/free). On PREVIEW: `rca.preview.20260719@example.com`. Delete via admin console at leisure.
- Probe scripts: /tmp/rca_login_probe*.py (ephemeral).
