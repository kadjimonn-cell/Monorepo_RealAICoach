# Polling Guardrails — Locked Protocol (Global System Level)

## Objective
Prevent 429 request-flood regressions in all future feature releases.

## Checkpoint A — Evidence (must gather)
- Contract pass:
  - `backend/tests/test_polling_guardrails_locked_protocol_contract.py`
- Endpoint counters from backend logs (latest window):
  - `/api/gps/state`
  - `/api/onboarding-ab/assign`
  - `/api/subscriptions/renewal-banner`
  - `/api/subscriptions/plans`
  - `/api/notifications/*`

## Checkpoint B — Plan (must be explicit)
- If any guardrail is missing, patch before release.
- If counters surge unexpectedly, stop release and patch root causes.

## Checkpoint C — Implementation standards
1. Keep endpoint hard cooldown rules in `frontend/src/services/api.ts`.
2. Keep route-scoped heavy pollers in `frontend/src/components/AppShell.tsx`.
3. Keep GPS polling floor and no client consistency POST in `frontend/src/hooks/useGlobalPlatformState.ts`.
4. Keep session markers in:
   - `frontend/src/components/SmartOnboarding.tsx`
   - `frontend/src/components/RenewalBanner.tsx`
5. Avoid duplicate notification polling when provider scope is active.

## Checkpoint D — Test evidence + artifacts (mandatory)
Run:
```bash
bash /app/scripts/polling_guardrails_locked_protocol_check.sh
```

Artifact output:
- `/app/test_reports/polling_guardrails_<timestamp>.txt`

## Release Acceptance Thresholds
- Frontend observation window (20–30s on key route):
  - total 429s should be near-zero (target: 0)
  - no runaway burst on listed critical endpoints
  - page remains interactive

## Escalation Rule
If flood signs return:
1) pause release,
2) run troubleshoot RCA,
3) patch and re-test,
4) only then proceed.
