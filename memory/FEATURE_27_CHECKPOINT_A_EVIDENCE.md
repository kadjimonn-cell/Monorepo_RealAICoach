# Feature 27 (ID Checker / ID Checker) — Checkpoint A Evidence

Date: 2026-06-20
Feature Number: 27
Feature ID: id-checker
Route: /id-checker
Category: platform
Tracker Status Source: /app/memory/FEATURES_REBUILD_TRACKER.md row #27 = Done

## Evidence Inputs
- Backend route source: `/app/backend/routes/id_verification.py`
  - User status contract endpoint: `GET /api/id-checker/kyc/status`
  - User summary endpoint: `GET /api/id-checker/experience-summary`
  - Admin queue endpoint: `GET /api/id-checker/admin/queue`
  - Admin ops endpoint: `GET /api/id-checker/admin/operations-kpis`
  - Admin funnel endpoint: `GET /api/id-checker/admin/conversion-funnel`
- Frontend user flow source: `/app/frontend/app/id-verification.tsx`
  - Enforced 3-document requirement before review submission.
  - Enterprise status strip with plan lane and SLA metadata.
- Frontend admin panel source: `/app/frontend/src/components/executive/ExecIDCheckerPanel.tsx`
  - Live queue + override actions + commercial KPI/funnel visibility.
- Regression guard source: `/app/frontend/src/components/executive/ExecIdCheckerPanel.tsx`
  - Canonical export shim to remove duplicate implementation drift.
- Test source: `/app/backend/tests/test_feature27_id_checker_enterprise.py`
  - New enterprise-grade contract tests for Feature 27 APIs.

## Checkpoint A Decision
- Evidence inputs are complete for locked-protocol closure validation.
