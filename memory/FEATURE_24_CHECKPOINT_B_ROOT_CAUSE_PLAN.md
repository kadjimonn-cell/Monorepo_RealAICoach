# Feature 24 (AI Learning Hub / Learning Hub) — Checkpoint B Root Cause and Plan

Date: 2026-06-14
Feature Number: 24
Feature ID: ai-learning-hub
Route: /ai-learning-hub
Category: platform
Tracker Status Source: /app/memory/FEATURES_REBUILD_TRACKER.md row #24 = Done

## Root Cause
- Entitlement drift risk: Feature 24 relied on direct `subscription_plan` reads in key endpoints instead of global effective-plan resolution (`compute_effective_plan`) with payment verification.
- Frontend load amplification: duplicate recovery-copilot background refresh in `loadEverything` increased noisy refresh churn.
- Historical auth regression context existed for this feature (false sign-in message for authenticated users), requiring explicit re-validation in current codebase.

## Plan
- Apply permanent global-platform alignment patch:
  - Add `_effective_plan_for_user()` in Feature 24 backend and use it for hub dashboard, courses access-control, enroll flow, and quota enforcement.
  - Remove duplicate background recovery fetch to reduce refresh race/noise.
  - Preserve cookie-first auth behavior for web and token fallback for native certificate downloads.
- Run locked-protocol validation (backend + frontend) and only promote status after PASS evidence.
