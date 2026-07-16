# Feature 26 (Jobs Portal / Jobs Portal) — Checkpoint C Implementation Record

Date: 2026-06-20
Feature Number: 26
Feature ID: jobs-portal
Route: /job-platform
Category: platform
Tracker Status Source: /app/memory/FEATURES_REBUILD_TRACKER.md row #26

## Implementation Snapshot
- Feature route is registered and operational at `/job-platform`.
- Tier entitlement behavior validated in current codebase:
  - Free: candidate summary/search allowed, admin surfaces blocked, premium candidate boost blocked.
  - Basic: candidate summary/search allowed, admin surfaces blocked, candidate boost allowed.
  - Premium/Admin: candidate summary/search allowed, admin surfaces allowed, employer conversion funnel allowed.
- Approved non-admin employer fixture validated:
  - `/api/hiring/v2/dashboard/summary` allowed.
  - `/api/hiring/v2/admin/*` denied.
- Locked metadata validated from `/api/hiring/v2/health`:
  - `feature_number=26`, `feature_id=jobs-portal`, `version=v2`, `service=hiring-v2`.

## Feature 26 Final Verification Artifacts
- Tier matrix evidence:
  - `/app/test_reports/feature26_final_tier_matrix_latest.json`
  - `/app/test_reports/feature26_final_tier_matrix_20260620T152454Z.json`
- Closure test suite:
  - `/app/backend/tests/test_feature26_final_verification_closure.py`
  - `pytest -q /app/backend/tests/test_feature26_final_verification_closure.py` → `5 passed`
- Prior validated enterprise/F26 artifacts retained:
  - `/app/test_reports/iteration_344.json`
  - `/app/test_reports/iteration_345.json`

## Acceptance Columns Closure (Feature 26)
- E2E Free: **DONE**
- E2E Basic: **DONE**
- E2E Premium: **DONE**
- Responsive: **DONE**
- i18n: **DONE**
- Theme: **DONE**
- Screenshot: **DONE**

## Explicit Contract Clarification (Final)
- **Page Theme Contract (v2 light/dark): PASS**
  - Evidence: Feature 26 route modules use `useTheme()` + tokenized colors (`colors.bg`, `colors.card`, `colors.text`, etc.) across:
    - `/app/frontend/app/job-platform.tsx`
    - `/app/frontend/app/job-platform-candidate.tsx`
    - `/app/frontend/app/job-platform-employer.tsx`
    - `/app/frontend/app/job-platform-admin.tsx`
- **Responsive Contract (mobile/tablet/desktop): PASS**
  - Evidence: Feature 26 route layout uses adaptive width handling and wrapping behaviors (`useWindowDimensions`, `isWide`, `isMedium`, `maxWidth`, `flexWrap`) in `/app/frontend/app/job-platform.tsx` and companion route modules.
- **Email Template Contract (v7): PASS**
  - Evidence: Feature 26 outbound email flows use catalog/template pathways in active jobs/employers routes:
    - `/app/backend/routes/jobs.py` (`send_catalog_template` usage)
    - `/app/backend/routes/employers.py` (`send_catalog_template` with `template_key="employer_notification_v7"`)

## Checkpoint C Decision
- Feature 26 implementation evidence satisfies locked-protocol closure requirements in current codebase.

## 2026-06-21 — P2 Final Legacy Read-Route Retirement Execution
- Executed final read-route retirement for legacy Feature 26 surfaces in:
  - `/app/backend/routes/jobs.py` route family (`/api/jobs/*` legacy read endpoints)
  - `/app/backend/routes/employers.py` route family (`/api/employers/*` legacy read endpoints)
- Enforcement added at platform level:
  - `/app/backend/server.py` middleware `feature26_hard_retire_legacy_v1_reads`
  - Retirement response contract: `410` + explicit `replacement_hint` to v2 routes
- Added/validated v2 read aliases in `/app/backend/routes/hiring_v2.py` to preserve approved user flows post-retirement.
- Frontend migration safety implemented in `/app/frontend/src/services/api.ts`:
  - GET requests targeting retired legacy Feature 26 read paths are rewritten to v2 endpoints.

## 2026-06-21 — Optional Cleanup Pass (post-retirement pruning)
- Physically pruned now-unreachable legacy read route handlers from:
  - `/app/backend/routes/jobs.py` (removed legacy `@router.get` decorators for retired Feature 26 reads)
  - `/app/backend/routes/employers.py` (removed legacy `@router.get` decorators for retired Feature 26 reads)
- Kept underlying shared async logic functions intact for v2 adapter reuse in `hiring_v2.py`.
- Updated outdated regression adapters in `/app/backend/tests/test_feature26_sprint3_v2_adapters.py` to assert retired legacy endpoints return `410` and v2 replacements return expected `200/role-gated` statuses.

## 2026-06-21 — Dead Helper Code Paths Cleanup (post-pruning refinement)
- Removed unreferenced helper code paths not used by v2 adapters:
  - `/app/backend/routes/jobs.py`: `_safe_status_count`, `_is_employer_user`
  - `/app/backend/routes/employers.py`: `_extract_app_document`
- Corrected permission helper return contract in `/app/backend/routes/employers.py`:
  - `require_employer_permission(...)` now explicitly returns `user` on success.
