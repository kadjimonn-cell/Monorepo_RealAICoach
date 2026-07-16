# Global Platform Security Incident Proposal — Current Implementation Status Matrix

_Generated from current codebase scan and latest available test reports._

## Status taxonomy

- **Implemented + Verified**: Landed in code and validated by recent test evidence.
- **Implemented + Unverified in current preview**: Landed, but preview instability prevented deterministic verification.
- **Partially Implemented**: Framework exists; capability is not complete across providers/flows.
- **Not Implemented**: No code path present.
- **Operational Dependency**: Requires environment credentials/permissions/runbook execution outside code.

---

## A) Rotation control plane and incident workflow

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Readiness → Prepare → Approve → Apply workflow | **Implemented + Verified** | `backend/routes/security_key_rotation.py` (`/readiness`, `/prepare`, `/approve`, `/apply`) | `test_reports/iteration_53.json` | None at framework level | Keep regression tests on each release |
| Evidence retrieval (run steps, incidents, rollbacks) | **Implemented + Verified** | `backend/routes/security_key_rotation.py` (`/runs/{run_id}/evidence`) | `iteration_50.json` | None | Add compliance export bundle |
| Rollback path after failed post-health | **Implemented + Verified** | `_auto_rollback_after_failed_health`, rollback endpoint in `security_key_rotation.py` | `iteration_50.json` (status/summary assertions) | Provider rollback is manual-required for some providers | Add provider-native rollback adapters where possible |
| Rotation policy + game-day endpoints | **Implemented + Verified** | `GET /policy`, `POST /policy/game-day`, `POST /policy/attest` in `security_key_rotation.py` | `iteration_53.json` | None | Monitor attestation freshness in dashboard |
| Go-live checklist and rotate-contract hard gate | **Implemented + Verified** | `GET /go-live-checklist` + apply `contract_blocked` guard in `security_key_rotation.py` | `iteration_53.json` | Rotate providers blocked until env is complete (intentional) | Supply lifecycle credentials and re-validate |

---

## B) Provider capability model correctness

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Contract-aware provider modes (`manual_by_provider_constraint`, `api_probe_only`, `api_rotate_supported`) | **Implemented + Verified** | constants + `apply_contract_mode` in `security_key_rotation.py` | `iteration_50.json` | None | Preserve backward compatibility aliases |
| Apple IAP + Google IAP root-cause correctness | **Implemented + Verified** | `iap_apple`, `iap_google` set to manual contract mode in provider definitions | `iteration_50.json` (`manual_by_provider_constraint`) | Manual lifecycle dependency remains | Maintain manual evidence strict flow |
| API adapter handlers for supported set | **Implemented + Verified** | handlers map in `_execute_provider_api_apply` for Stripe/PayPal/FedaPay/Google OAuth/Microsoft OAuth | `iteration_50.json` step status and `adapter_result` evidence | Handlers are mostly probe/validation contracts | Promote selected providers to true rotate contract after credential checks |
| True API rotate contract actively configured | **Partially Implemented** | `oauth_microsoft` set to `APPLY_CONTRACT_API_ROTATE`; lifecycle helper + revoke status in `security_key_rotation.py` (`provider_revoked`) | `iteration_53.json` verifies contract mode and lifecycle metadata paths | `api_rotate_ready` still `0` in current env due missing lifecycle credentials/flags (`adapter_missing`) | Provide `AZURE_ROTATION_*` lifecycle creds + enable flag, then validate first live `provider_revoked` run |

---

## C) Policy-gate stabilization for live apply windows

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Apply-window activation and expiry | **Implemented + Verified** | `_activate_policy_gate_apply_window` / `_deactivate_policy_gate_apply_window` in `security_key_rotation.py` | `iteration_50.json` apply flow | None | Add dashboard visualization of active window |
| Prerequisite refresh (`admin_e2e_health_gate`, `subscription_plan_guardrail`, `sso_e2e_validation`, `cia_trust`) | **Implemented + Verified** | `_refresh_policy_gate_prerequisites` in `security_key_rotation.py` | `iteration_50.json` | Scheduler import/runtime failures possible in degraded env | Add retry and action-level health score |
| Scoped override during rotation window | **Implemented + Verified** | `collect_policy_gate_signals(...allow_rotation_window_override=True)` in `production_security_policy_gate.py` | `iteration_50.json` (preflight semantics) | Must remain tightly scoped to rotation path | Keep override flag off outside rotation endpoints |

---

## D) Canary and blast-radius controls

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Consecutive failure threshold stop | **Implemented + Verified** | `KEY_ROTATION_CANARY_STOP_AFTER_CONSECUTIVE_FAILURES` logic in apply flow | `iteration_50.json` (`skipped_canary_stop`) | Static threshold may be suboptimal by provider class | Add adaptive thresholds per provider criticality |
| Provider-level skip accounting and evidence | **Implemented + Verified** | step status `skipped_canary_stop`, run/evidence summary counters | `iteration_50.json` | None | Include canary stop reason in admin UI card |

---

## E) Manual-evidence governance for constrained providers

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Manual evidence submission endpoint | **Implemented + Verified** | `POST /runs/{run_id}/manual-evidence` strict checks in `security_key_rotation.py` (min note, links, verification checks, console confirm) | `iteration_53.json` | None | Maintain policy defaults in env |
| Manual status lifecycle (`manual_pending_evidence` → `manual_evidence_uploaded` → `manual_applied_verified`) | **Implemented + Verified** | status model + summary recomputation in `security_key_rotation.py` | `iteration_50.json` | None | Add SLA alerts on long-pending manual states |

---

## F) SIEM and incident automation

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Default SIEM alert rule seeding | **Implemented + Verified** | `DEFAULT_SIEM_RULES` + ensure seeding in `siem_logging.py` | PRD + prior test iterations (`43-45`) | None | Expand rules for provider-specific rotation failures |
| Incident creation + webhook dispatch | **Implemented + Verified** | `_open_security_incident_for_alert`, `_dispatch_incident_webhook` in `siem_logging.py`; webhook validation + retry/dead-letter path in `security_key_rotation.py`/`scheduler_jobs.py` | `iteration_53.json` | External webhook still requires env config | Set/validate `SIEM_INCIDENT_WEBHOOK_URL` in secure env |
| Containment-only remediation | **Implemented + Verified** | `_apply_containment_for_alert` in `siem_logging.py` | prior SIEM iterations | No destructive automated actions (by design) | Keep policy as containment-only unless explicitly approved |

---

## G) Admin visibility (dashboard/readiness)

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Unified readiness card (preflight + provider capability) | **Implemented + Verified** | `frontend/src/components/admin/SecurityDashboardPanel.tsx` (`rotation-readiness-*` test IDs) | `iteration_49.json`, `iteration_50.json` | Preview intermittency may affect UX checks | Keep component-level tests + fallback UI messaging |
| Contract-mode-aware KPI set (`api_rotate_ready`, `api_probe_only_ready`, `manual_by_constraint`) | **Implemented + Verified** | `SecurityDashboardPanel.tsx` + readiness summary/checklist in backend routes | `iteration_53.json` (code-level verification) | Preview infra may intermittently block UI playback | Keep UI smoke + code-level selector checks |
| Operator controls (attest, webhook validate, bundle generation) | **Implemented + Verified (code)** | `SecurityDashboardPanel.tsx` action handlers + test IDs (`rotation-readiness-operator-actions`, etc.) | `iteration_53.json` | UI end-to-end in preview can be blocked by disk/infra | Re-run frontend e2e when preview disk stabilizes |

---

## I) Scheduler governance automation

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Scheduled policy attestation job | **Implemented + Verified** | `scheduled_key_rotation_policy_attestation` in `scheduler_jobs.py` + registration in `scheduler.py` | `iteration_53.json` | Depends on webhook/env for full green status | Keep heartbeat alerts |
| Scheduled game-day staleness guard | **Implemented + Verified** | `scheduled_key_rotation_game_day_staleness_guard` | `iteration_53.json` | Potential alert fatigue if cadence too strict | Tune interval + dedupe rules |
| Scheduled compliance bundle autogen | **Implemented + Verified** | `scheduled_key_rotation_compliance_bundle_autogen` | `iteration_53.json` | Bundle size growth over time | Add retention/archival policy |
| Scheduled status drift monitor | **Implemented + Verified** | `scheduled_key_rotation_status_drift_monitor` | `iteration_53.json` | Needs env-aware suppression rules | Tune alert severity mapping |
| Scheduled webhook dead-letter retry | **Implemented + Verified** | `scheduled_siem_webhook_dead_letter_retry` | `iteration_53.json` | Infinite retries avoided by max-attempt cap | Monitor failed_permanent queue |

---

## H) Session persistence incident follow-up (platform-level)

| Proposal item | Current status | Code evidence | Test evidence | Gap / risk | Next action |
|---|---|---|---|---|---|
| Clear session only on hard unauth (401); preserve on transient failures | **Implemented + Verified** | `frontend/src/context/AuthContext.tsx` resilient auth bootstrap and classification | `iteration_51.json` | None | Keep auth chaos test in CI |
| Anti-flap route guard grace window | **Implemented + Verified** | `frontend/src/components/RouteAccessGuard.tsx` transient grace logic | `iteration_51.json` | None | Tune grace window from telemetry trends |
| Session telemetry endpoint and rate-limit tuning (`/auth/me` 240/60) | **Implemented + Verified** | `backend/routes/auth.py`, `backend/utils/api_rate_limiter.py`, `backend/middleware.py` allowlist | `iteration_51.json`, `auth_session_persistence_verification.json` | Preview 502 remains infra-side | Continue infra reliability tracking separately |

---

## Summary snapshot (as of current scan)

- **Implemented + Verified:** Core incident-response architecture, policy gate stabilization, SIEM hooks, dashboard visibility, strict manual-evidence flow, canary stop, scheduler governance automation, session persistence hardening.
- **Partially Implemented:** True provider-side API rotate/cutover/revoke (Microsoft rotate contract path now implemented; environment not yet credential-complete for live revoke proof).
- **Operational Dependencies:** Live credentials/permissions, production webhook configuration, provider console/manual evidence execution.
- **Known non-code constraint:** Preview host intermittency (502/ERR_ABORTED) noted in recent reports; backend logic verification still passed in controlled tests.

## Priority closure roadmap (next)

1. Complete operational enablement for Microsoft rotate lifecycle (`AZURE_ROTATION_APP_OBJECT_ID`, lifecycle flag, scope, previous key id for revoke) and validate first `provider_revoked` run evidence.
2. Add remediation guidance in dashboard per provider reason-code (`missing_rotation_scope`, env mismatch, manual pending).
3. Activate and verify SIEM webhook in secured production environment.
4. Validate first live rotate-contract execution (`provider_revoked`) and close remaining amber operational dependencies.
