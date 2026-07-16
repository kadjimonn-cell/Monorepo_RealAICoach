"""
Autonomous Engine — Package Init.

Exposes the unified router and re-exports all symbols that external callers need.
The original monolithic autonomous_engine.py has been split into domain modules:

  _shared.py          — Constants, default policies, DB helpers, shared utils
  core_pipeline.py    — Pipeline orchestration, gates, auto-heal, baseline
  theme.py            — Theme health, guardrail, drift, remediation, tickets
  zero_trust.py       — Zero-trust mitigation, active defense, nightly scans
  baseline_deploy.py  — Baseline, certificates, completion, coverage, deployment, canary
  monitoring.py       — Reality validation, monitoring, anomalies, feedback loop
  memory_predictive.py— System memory, failure memory, predictive, feature builds, perf audit
  operations.py       — Drift detection, tiers, scaling, continuous cycle, architecture, content
"""

# Import the shared router — all sub-modules register their routes on this router
from routes.autonomous_engine._shared import router  # noqa: F401

# Import all domain modules to trigger route registration (side effects)
from routes.autonomous_engine import core_pipeline  # noqa: F401
from routes.autonomous_engine import theme  # noqa: F401
from routes.autonomous_engine import zero_trust  # noqa: F401
from routes.autonomous_engine import baseline_deploy  # noqa: F401
from routes.autonomous_engine import monitoring  # noqa: F401
from routes.autonomous_engine import memory_predictive  # noqa: F401
from routes.autonomous_engine import operations  # noqa: F401

# ─── Re-exports for external callers (scheduler_jobs.py, platform_health.py, etc.) ───

# Constants (used by test_email_v2_release_gate.py)
from routes.autonomous_engine._shared import (  # noqa: F401
    EMAIL_V2_INHERITANCE_TEST_PATH,
    _get_engine_config,
)

# Core pipeline functions (used by scheduler_jobs.py, executive_dashboard.py, platform_health.py)
from routes.autonomous_engine.core_pipeline import (  # noqa: F401
    run_full_pipeline,
    _build_gate_lock_state,
    evaluate_completion_gate_and_audit,
    _summarize_email_v2_iteration_report,
    _evaluate_email_v2_inheritance_release_check,
    _run_deployment_gate,
)

# Theme functions (used by scheduler_jobs.py)
from routes.autonomous_engine.theme import (  # noqa: F401
    _run_theme_guardrail_scan,
    _run_theme_drift_nightly_detector,
)

# Zero trust functions (used by scheduler_jobs.py)
from routes.autonomous_engine.zero_trust import (  # noqa: F401
    run_zero_trust_auto_mitigation_cycle,
    run_zero_trust_daily_status_email,
    run_active_defense_nightly_scan,
)

# Memory/Predictive functions (used by scheduler_jobs.py)
from routes.autonomous_engine.memory_predictive import (  # noqa: F401
    run_perf_audit,
    run_predictive_failure_prevention,
)

# Operations functions (used by scheduler_jobs.py)
from routes.autonomous_engine.operations import (  # noqa: F401
    run_continuous_cycle,
)

# Provide `os` module access for test_email_v2_release_gate.py backward compat
import os  # noqa: F401
