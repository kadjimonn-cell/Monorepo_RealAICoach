# Preview Parity Checklist (Post-Support Cache Purge)

Use this immediately after Emergent support confirms preview routing/cache refresh.

## 1) Quick hash parity
- Local URL: `http://127.0.0.1:3000/job-platform`
- External URL: `https://coach-web-preview.preview.emergentagent.com/job-platform`
- Confirm both serve the same `index-*.js` hash in HTML script tags.

## 2) Jobs Portal funnel parity
- Open `/job-platform`
- Verify funnel strip renders: `jobs-portal-funnel-strip`
- Click and verify behavior:
  - `jobs-portal-funnel-stage-open-roles` → `apply-jobs-funnel-focus-banner`
  - `jobs-portal-funnel-stage-applications` → `jobs-candidates-funnel-focus-banner`
  - `jobs-portal-funnel-stage-interviews` → `employer-funnel-focus-banner`
  - `jobs-portal-funnel-stage-offers` → `employer-funnel-focus-banner`

## 3) Legacy wrapper parity
- `/subscription/mobile` should render V2 IAP view.
- `/payment-history` should render V2 Payment History view.

## 4) Regression spot-check APIs
- `GET /api/jobs/analytics`
- `GET /api/iap/status`
- `GET /api/payments/history`
- `GET /api/referrals/my-stats`

## 5) Done criteria
- External preview behavior matches local for all checks above.
- No stale wrapper shell or stale bundle hash mismatch.
- Preview Browser E2E latest payload includes deterministic `status` in `{PASS, FAIL, BLOCKED}`.
- Preview Browser E2E latest payload includes explicit `status_reason_code`.
- If external preview is blocked (Cloudflare/wake-layer), payload must include localhost fallback evidence (`localhost_fallback_status` + fallback checks summary).
- Cloudflare challenge classification must include deterministic guard evidence:
  - `challenge_detection_guard.guard_version = v2_deterministic`
  - strict marker hits, soft marker hits, and app-shell marker hits are all recorded
  - block decision must NOT rely on weak markers alone (e.g., `cloudflare`, `verify you are human`).