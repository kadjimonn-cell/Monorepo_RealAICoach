# Preview Parity Checklist Run — 2026-05-07

## Result
- **Status:** ❌ NOT READY / FAILED (external preview still routed to wake-up wrapper)

## Checks executed

### 1) Quick hash parity
- Local `/job-platform`: `200`, non-wrapper HTML, index hash present:
  - `/_expo/static/js/web/index-8197fcb85ab14e48cfc075371cce7643.js`
- External `/job-platform`: `200`, **wrapper HTML** (no app index hash), iframe host mapping:
  - `loading-preview?host=trust-layer-checkout.preview.emergentagent.com`
- **Parity:** ❌ mismatch (divergence before app bundle delivery)

### 2) Jobs Portal funnel parity (external)
- Blocked: external preview returns wrapper page (`title: Loading...`) and not app shell.
- Cannot validate funnel testids on external until routing/cache fix is truly active.

### 3) Legacy wrapper parity
- Local checks pass (app routes reachable).
- External blocked by wrapper shell.

### 4) Regression spot-check APIs
- Previously verified healthy (all 200):
  - `/api/jobs/analytics`
  - `/api/iap/status`
  - `/api/payments/history`
  - `/api/referrals/my-stats`

## Evidence captured
- External parity screenshot state: `/tmp/parity-external-preview-state.png`
- Prior incident evidence: `/app/memory/preview_incident_evidence.md`

## Required next step
- Ask support to confirm they completed **both**:
  1. Preview router host mapping refresh for this run
  2. Edge/CDN invalidation for preview host chain
- Re-run this checklist immediately after their explicit completion confirmation.