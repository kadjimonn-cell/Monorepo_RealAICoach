# Feature 25 (Daily Meditation / Daily Meditation) — Checkpoint B Root Cause and Plan

Date: 2026-06-14
Feature Number: 25
Feature ID: daily-meditation
Route: /features/daily-meditation
Category: platform
Tracker Status Source: /app/memory/FEATURES_REBUILD_TRACKER.md row #25 = Done

## Root Cause
- Entitlement drift risk: Feature 25 used local `_get_user_plan` based on direct `subscription_plan` reads instead of global `compute_effective_plan` (payment verification + plan transition aware).
- Security/identity drift: many endpoints trusted client-supplied `user_id`, allowing non-admin cross-user probing attempts without strict actor scoping.
- Stability drift in frontend: monolithic refresh path could amplify partial API failures and show broad error banners even when only one subdomain call failed.

## Plan
- Apply global platform-level permanent correction:
  - Replace local plan resolution with `compute_effective_plan` based user document normalization.
  - Enforce request actor scoping for every user-bound endpoint (`require_auth` + scoped user resolver), with admin override only.
  - Gate operational run-now endpoints to admin (`prayer-audio publish`, `catalog seed`, `reminder dispatch`).
  - Harden frontend refresh orchestration with segmented bundles and partial-success behavior to reduce noisy failure UX.
- Execute full backend+frontend locked-protocol verification and only promote status after PASS evidence.
