"""Scheduled job functions — extracted from server.py inline definitions."""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


WEEKLY_CAREERS_TEMPLATE_FLAG_KEY = "weekly_careers_job_template_config"  # noqa: F811 — re-export shim
WEEKLY_CAREERS_AUTOMATION_STATE_KEY = "weekly_careers_job_automation_state"
WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION = "weekly_careers_job_automation_runs"
WEEKLY_CAREERS_JOB_HEARTBEAT_ID = "weekly_careers_job_automation"
WEEKLY_CAREERS_FALLBACK_TEMPLATES: List[Dict[str, Any]] = []

# Canonical implementations moved to `scheduler_jobs/weekly_careers.py`
# (Phase 2 batch #3). Re-imported here so external `from scheduler_jobs import X`
# callers continue to resolve to the same objects via the facade.
from scheduler_jobs.weekly_careers import (  # noqa: E402, F401, F811
    WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION,
    WEEKLY_CAREERS_AUTOMATION_STATE_KEY,
    WEEKLY_CAREERS_FALLBACK_TEMPLATES,
    WEEKLY_CAREERS_JOB_HEARTBEAT_ID,
    WEEKLY_CAREERS_TEMPLATE_FLAG_KEY,
    _build_weekly_careers_job_doc,
    _emit_weekly_careers_in_app_notifications,
    _get_weekly_careers_template_config,
    _merge_weekly_careers_template,
    _select_weekly_careers_email_recipients,
    _send_weekly_careers_emails,
    scheduled_weekly_careers_job_creation_and_announcement,
)
from scheduler_jobs.security import (  # noqa: E402, F401
    scheduled_production_security_policy_gate,
    scheduled_release_intelligence_monitor,
    scheduled_security_incident_runbook_monitor,
    scheduled_zero_trust_auto_mitigation,
    scheduled_zero_trust_daily_email_digest,
)
from scheduler_jobs.digests import (  # noqa: E402, F401
    _send_weekly_quality_digest,
    scheduled_weekly_quality_digest,
)
from scheduler_jobs.payments import (  # noqa: E402, F401
    scheduled_bill_generator_hourly_daemon,
    scheduled_fedapay_webhook_self_heal,
    scheduled_resend_webhook_guard,
    scheduled_invoice_dunning,
)
from scheduler_jobs.content import (  # noqa: E402, F401
    scheduled_watch_videos_daily_drop,
)
from scheduler_jobs.learning import (  # noqa: E402, F401
    scheduled_learning_certificate_anchor_batch,
    scheduled_learning_hub_assurance_guard,
    scheduled_learning_hub_email_dispatcher,
    scheduled_learning_hub_integrity_guard,
    scheduled_learning_hub_synthetic_canary,
    scheduled_learning_hub_video_maintenance,
    scheduled_learning_hub_weekly_autopublish,
)
from scheduler_jobs.sso_auth_health import (  # noqa: E402, F401
    scheduled_admin_e2e_health_gate,
    scheduled_auth_fallback_link_guardian,
    scheduled_cia_trust_heartbeat,
    scheduled_multi_region_auth_probe,
    scheduled_sso_e2e_validation_alerts,
    scheduled_sso_provider_registration_alignment_auto,
    scheduled_sso_redirect_auto_sync,
    scheduled_sso_redirect_drift_sentinel,
)
from scheduler_jobs.visual_audits import (  # noqa: E402, F401
    scheduled_fee_visibility_visual_audit_hourly,
    scheduled_fee_visibility_visual_audit_nightly,
)
from scheduler_jobs.preview_cache import (  # noqa: E402, F401
    scheduled_preview_cache_hygiene_hourly,
    scheduled_preview_cache_hygiene_nightly,
)
from scheduler_jobs.global_parity import (  # noqa: E402, F401
    scheduled_global_parity_audit_hourly,
    scheduled_global_parity_audit_nightly,
)
from scheduler_jobs.theme_guardrails import (  # noqa: E402, F401
    scheduled_admin_tabs_theme_drift_report,
    scheduled_admin_tabs_theme_drift_weekly_digest,
    scheduled_theme_drift_nightly_detector,
    scheduled_theme_guardrail_scan,
)
from scheduler_jobs.key_rotation import (  # noqa: E402, F401
    scheduled_key_rotation_compliance_bundle_autogen,
    scheduled_key_rotation_game_day_staleness_guard,
    scheduled_key_rotation_policy_attestation,
    scheduled_key_rotation_status_drift_monitor,
)
from scheduler_jobs.engagement import (  # noqa: E402, F401
    scheduled_card_expiry_check,
    scheduled_referral_weekly_email,
    scheduled_weekly_engagement_emails,
    scheduled_welcome_back_check,
)
from scheduler_jobs.enterprise_enforcement import (  # noqa: E402, F401
    scheduled_enterprise_lock_cycle,
    scheduled_global_rbac_subscription_enforcement,
    scheduled_quarterly_access_recertification,
    scheduled_slo_breach_auto_mitigation,
    scheduled_weekly_enterprise_standard_enforcement,
)
from scheduler_jobs.pricing import (  # noqa: E402, F401
    scheduled_pricing_guard_nightly_monitor,
    scheduled_subscription_plan_guardrail,
)
from scheduler_jobs.i18n_accessibility import (  # noqa: E402, F401
    scheduled_i18n_literal_autofix_dry_run_report,
    scheduled_nightly_darkmode_regression_scan,
    scheduled_weekly_email_contrast_compliance,
)
from scheduler_jobs.audit_gates import (  # noqa: E402, F401
    scheduled_acceptance_report_refresh,
    scheduled_critical_journey_monitor,
    scheduled_e2e_regression_gate,
    scheduled_full_system_auto_audit,
    scheduled_logo_render_probe,
    scheduled_perf_audit,
    scheduled_preview_browser_e2e_wake_and_run,
)

# Phase 2 batches #20–#23 — final domain split.
from scheduler_jobs.security_defense import (  # noqa: E402, F401
    scheduled_active_defense_nightly_scan,
    scheduled_autonomous_blocked_attempts_export,
    scheduled_siem_webhook_dead_letter_retry,
)
from scheduler_jobs.compliance import (  # noqa: E402, F401
    scheduled_daily_usage_summary,
    scheduled_tax_compliance_audit,
)
from scheduler_jobs.hosting import (  # noqa: E402, F401
    _run_scheduled_assigned_host_guard,
    scheduled_assigned_host_guardian,
)
from scheduler_jobs.platform_health import (  # noqa: E402, F401
    FRONTEND_EXPORT_LOCKFILE,
    FRONTEND_EXPORT_NODE_OPTIONS,
    _trim_validity_autofix_history,
    scheduled_continuous_cycle,
    scheduled_global_experience_assurance,
    scheduled_growth_integrity_monitor,
    scheduled_platform_cache_freshness_guard,
    scheduled_predictive_failure_prevention,
    scheduled_validity_autofix_refresh,
)
from scheduler_jobs.admin_context import (  # noqa: E402, F401
    _SchedulerAdminContext,
    _get_scheduler_admin_context,
    _mint_scheduler_admin_token,
)


async def _record_scheduler_heartbeat(job_id: str, status: str, detail: str = ""):  # noqa: F811 — re-export shim
    """Replaced by `scheduler_jobs.observability._record_scheduler_heartbeat` (see import below)."""
    raise NotImplementedError  # pragma: no cover


# ── Phase 2 observability extraction ──
# Canonical implementation lives in `scheduler_jobs/observability.py`.
# Re-imported here so the rest of this legacy module (and external callers
# like `services/gtec_scan_v2.py` and `scheduler.py`) keep resolving to
# the same function object via the facade.





def _slugify_weekly_careers(value: str) -> str:  # noqa: F811 — re-export shim
    """Replaced by `scheduler_jobs.utils._slugify_weekly_careers`."""
    raise NotImplementedError  # pragma: no cover


def _resolve_frontend_base_url() -> str:  # noqa: F811 — re-export shim
    """Replaced by `scheduler_jobs.utils._resolve_frontend_base_url`."""
    raise NotImplementedError  # pragma: no cover


# ── Phase 2 helper extraction ──
# Canonical implementations live in `scheduler_jobs/utils.py`.
# Re-imported here so the rest of this legacy module (and any external
# `from scheduler_jobs import _name` callers) continue to resolve to the
# same function objects.
from scheduler_jobs.utils import (  # noqa: E402, F401, F811
    _is_active_user_record,
    _parse_iso_datetime,
    _resolve_frontend_base_url,
    _slugify_weekly_careers,
)


# ── Phase 2 helper extraction ──
# Canonical implementations live in `scheduler_jobs/utils.py`.
# Re-imported here so the rest of this legacy module (and any external
# `from scheduler_jobs import _name` callers) continue to resolve to the
# same function objects.








async def check_meeting_reminders():
    """Send reminders for meetings starting in 15 or 30 minutes."""
    try:
        from routes.db import db

        # Guardrail: booking reminders are dispatched only by
        # routes.integrations.send_booking_reminders, which has strict
        # per-booking+recipient idempotency. This legacy path now only marks
        # scheduler heartbeat compatibility and performs no sends.
        now = datetime.now(timezone.utc)
        for minutes in [30, 15]:
            target = now + timedelta(minutes=minutes)
            window_start = (target - timedelta(minutes=2)).isoformat()
            window_end = (target + timedelta(minutes=2)).isoformat()
            count = await db.calendar_bookings.count_documents(
                {
                    "status": "confirmed",
                    "start": {"$gte": window_start, "$lte": window_end},
                    f"reminder_{minutes}_sent": {"$ne": True},
                }
            )
            if count > 0:
                logger.info(
                    "check_meeting_reminders skip-send guard active: due=%s (minutes=%s); canonical sender=routes.integrations.send_booking_reminders",
                    count,
                    minutes,
                )
    except Exception as e:
        logger.error(f"Meeting reminder check failed: {e}")


async def run_auto_response_scan():
    """Scheduled job: detect anomalies and execute matching auto-response rules."""
    try:
        from routes.db import db
        from routes.admin_auto_response import _execute_scan

        # Check if scheduler is enabled
        config = await db.auto_response_config.find_one({"config_id": "scheduler"}, {"_id": 0})
        if not config or not config.get("enabled", False):
            return
        result = await _execute_scan(db)
        if result["executed"] > 0:
            logger.info(f"Auto-response scan: executed {result['executed']} action(s)")
    except Exception as e:
        logger.error(f"Auto-response scan failed: {e}")


















































# ═══════════════════════════════════════════════════════════
# PRODUCTION-CRITICAL SCHEDULER JOBS
# ═══════════════════════════════════════════════════════════




