# Autonomous Engine — Module Architecture

The `autonomous_engine` package was refactored from a single 11,002-line file into 9 domain-specific modules. All 133 route endpoints are preserved with full backward compatibility.

## Package Structure

```
backend/routes/autonomous_engine/
├── __init__.py           # Router aggregator + backward-compatible re-exports
├── _shared.py            # Constants, default policies, DB helpers, shared utilities
├── core_pipeline.py      # Pipeline orchestration, gates, auto-heal, baseline
├── theme.py              # Theme health, guardrail, drift, remediation, tickets
├── zero_trust.py         # Zero-trust mitigation, active defense, nightly scans
├── baseline_deploy.py    # Baseline, certificates, completion, coverage, deployment, canary
├── monitoring.py         # Reality validation, monitoring, anomalies, feedback loop
├── memory_predictive.py  # System memory, failure memory, predictive, feature builds, perf audit
└── operations.py         # Drift detection, tiers, scaling, continuous cycle, architecture
```

## Module Responsibilities

### `_shared.py` (527 lines)
Shared infrastructure used by all other modules:
- Router definition (`APIRouter(prefix="/admin/autonomous-engine")`)
- All default policy constants (`DEFAULT_DRIFT_POLICY`, `DEFAULT_ZERO_TRUST_AUTOMATION_POLICY`, etc.)
- DB helper (`_db()`), admin auth check (`_require_admin()`)
- Engine config CRUD (`_get_engine_config()`, `_save_engine_config()`)
- File utilities (`_safe_read_json_file()`, `_tail_file_lines()`, `_recent_evidence_files()`)

### `core_pipeline.py` (3,007 lines, 7 routes)
The heart of the autonomous engine:
- Pipeline execution (`run_full_pipeline()`)
- All quality gates: tests, coverage, validation, performance, E2E, visual, deployment
- Auto-heal loop (`_attempt_auto_heal()`)
- System memory helpers for pipeline capture
- Gate lock state computation
- Email V2 inheritance checks
- **Routes**: `/run`, `/status`, `/history`, `/config`, `/gate-lock`, `/run-gate/{name}`

### `theme.py` (1,482 lines, 22 routes)
All theme-related scanning and remediation:
- Theme guardrail scanning (`_run_theme_guardrail_scan()`)
- Theme drift nightly detector (`_run_theme_drift_nightly_detector()`)
- Theme Health Center overview
- Theme token auto-remediation engine
- Responsive guardrail scanning
- Theme drift ticket CRUD
- **Routes**: `/theme-health-center/*`, `/theme-guardrail/*`, `/theme-token-remediation/*`, `/theme-drift-tickets/*`, `/responsive-guardrail/*`

### `zero_trust.py` (1,810 lines, 23 routes)
Zero-trust security automation:
- Active Defense scanners (SAST, DAST, WAF, Red Team, Assume Breach, Core Controls, Live Monitoring, Evidence)
- Auto-mitigation cycle (`run_zero_trust_auto_mitigation_cycle()`)
- Nightly active defense scans (`run_active_defense_nightly_scan()`)
- Daily security status emails
- Security trend dashboard
- Executive security posture
- Slack/Teams drift alerts
- **Routes**: `/zero-trust/*`, `/drift-alerts/*`, `/executive/security-posture`, `/send-test-anomaly-email`

### `baseline_deploy.py` (910 lines, 19 routes)
Release management and deployment:
- Baseline lock/unlock
- Release readiness certificates (PDF generation)
- Completion audit and enforcement
- Coverage policy management
- Deployment gate (load testing)
- Canary rollout management
- **Routes**: `/baseline/*`, `/certificate/*`, `/completion-audit`, `/coverage/*`, `/deployment/*`, `/canary/*`

### `monitoring.py` (712 lines, 14 routes)
Real-time monitoring and feedback:
- Reality validation policy and execution
- Live metrics monitoring
- Anomaly detection
- Feedback loop analysis
- **Routes**: `/reality-validation/*`, `/monitor/*`, `/feedback/*`

### `memory_predictive.py` (2,115 lines, 28 routes)
Knowledge management and prediction:
- System memory (store, query, library, dashboard)
- Failure memory (log, lookup, resolve, reconcile, assign-owner)
- Predictive failure prevention
- Darkmode regression tracking
- Feature build automation
- Performance audit engine
- **Routes**: `/memory/*`, `/failure-memory/*`, `/predictive/*`, `/darkmode-regression/*`, `/feature/*`, `/perf-audit/*`

### `operations.py` (776 lines, 20 routes)
Operational controls:
- Drift detection (baseline, rolling, dual)
- Module tiering system
- Controlled scaling
- Continuous cycle mode
- Architecture compliance dashboard
- Content marketing automation
- **Routes**: `/drift/*`, `/tiers/*`, `/controlled-scaling/*`, `/continuous/*`, `/architecture/*`, `/content-marketing/*`

## Cross-Module Dependencies

```
_shared ← (all modules)
core_pipeline ← baseline_deploy, monitoring, memory_predictive, operations
core_pipeline ↔ zero_trust (circular, uses lazy imports)
core_pipeline ↔ theme (circular, uses lazy imports)
memory_predictive ← core_pipeline (lazy), monitoring, operations
```

Circular dependencies between `core_pipeline ↔ zero_trust` and `core_pipeline ↔ theme` are resolved with **lazy imports inside functions** to avoid import cycles.

## External Callers

The `__init__.py` re-exports all symbols needed by external callers:

| Caller | Symbols Imported |
|--------|-----------------|
| `server.py` | `router` |
| `scheduler_jobs.py` | `run_perf_audit`, `run_continuous_cycle`, `_get_engine_config`, `_build_gate_lock_state`, `run_full_pipeline`, `run_zero_trust_auto_mitigation_cycle`, `run_zero_trust_daily_status_email`, `_run_theme_guardrail_scan`, `_run_theme_drift_nightly_detector`, `run_predictive_failure_prevention`, `run_active_defense_nightly_scan` |
| `platform_health.py` | `evaluate_completion_gate_and_audit` |
| `executive_dashboard.py` | `_build_gate_lock_state`, `_get_engine_config` |
| `scheduler.py` | `_get_engine_config` |
| `test_email_v2_release_gate.py` | `EMAIL_V2_INHERITANCE_TEST_PATH`, `_summarize_email_v2_iteration_report`, `_evaluate_email_v2_inheritance_release_check`, `_run_deployment_gate`, `os` |

## How to Add New Endpoints

1. Identify the domain module that matches your feature area
2. Add your route handler to that module (it already has `router` imported from `_shared`)
3. If your function needs to be called from `scheduler_jobs.py` or another external file, add a re-export line in `__init__.py`
4. If you need functions from another domain module, use **lazy imports inside your function** to avoid circular dependencies
