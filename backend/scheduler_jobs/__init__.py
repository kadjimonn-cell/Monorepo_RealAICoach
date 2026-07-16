"""
scheduler_jobs — Background job implementations.

PHASE 2 PACKAGE FACADE — DOMAIN-SPLIT COMPLETE
================================================
The original monolithic ``scheduler_jobs.py`` has been fully refactored
into domain-specific modules. The ``_legacy.py`` catch-all has been
renamed to ``misc.py`` and only houses 2 small jobs that were never
prefixed with ``scheduled_`` (``check_meeting_reminders`` and
``run_auto_response_scan``).

Module layout
-------------
    scheduler_jobs/
        __init__.py             ← this facade (explicit re-exports only)
        admin_context.py        ← _SchedulerAdminContext + token mint
        audit_gates.py          ← acceptance/e2e/perf audit jobs
        compliance.py           ← tax + daily-summary jobs
        content.py              ← content automation jobs
        digests.py              ← weekly quality digest
        engagement.py           ← email campaigns + welcome-back
        enterprise_enforcement.py ← RBAC + SLO + lock cycles
        global_parity.py        ← global-parity audits (+ helpers)
        hosting.py              ← assigned-host guardian
        i18n_accessibility.py   ← i18n + dark-mode regression jobs
        key_rotation.py         ← key rotation policy / staleness
        learning.py             ← learning hub jobs
        misc.py                 ← legacy bucket (2 non-scheduled funcs)
        observability.py        ← scheduler heartbeat helper
        payments.py             ← bills + dunning + fedapay
        platform_health.py      ← cache + integrity + 24/7 cycle
        preview_cache.py        ← preview cache hygiene (+ helper)
        pricing.py              ← pricing guard + subscription plans
        security.py             ← zero-trust + release intelligence
        security_defense.py     ← blocked attempts + active defense
        sso_auth_health.py      ← SSO + auth fallback jobs
        theme_guardrails.py     ← theme drift + admin tabs theme
        utils.py                ← pure utilities + _parse_iso_datetime
        visual_audits.py        ← fee visibility visual audits (+ helpers)
        weekly_careers.py       ← weekly careers email pipeline

The catch-all ``dir()`` mirror that previously copied every attribute
off ``_legacy.py`` has been **decommissioned**. All public names below
are now explicitly re-exported from their canonical domain module.
Drift-protection is enforced by
``backend/tests/test_issue3_whitescreen_protections.py``.
"""

# ── Admin / scheduler context (canonical) ───────────────────────────
from scheduler_jobs.admin_context import (  # noqa: F401
    _SchedulerAdminContext,
    _get_scheduler_admin_context,
    _mint_scheduler_admin_token,
)

# ── Observability heartbeat ─────────────────────────────────────────
from scheduler_jobs.observability import (  # noqa: F401
    _record_scheduler_heartbeat,
)

# ── Pure utilities ──────────────────────────────────────────────────
from scheduler_jobs.utils import (  # noqa: F401
    _is_active_user_record,
    _parse_iso_datetime,
    _resolve_frontend_base_url,
    _slugify_weekly_careers,
)

# ── Weekly careers ──────────────────────────────────────────────────
from scheduler_jobs.weekly_careers import (  # noqa: F401
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

# ── Talent network role-alert automation ────────────────────────────
from scheduler_jobs.talent_network import (  # noqa: F401
    TALENT_NETWORK_ALERT_STATE_KEY,
    TALENT_NETWORK_CAMPAIGN_HEARTBEAT_ID,
    TALENT_NETWORK_COL,
    TALENT_NETWORK_DISPATCH_EVENTS_COL,
    TALENT_NETWORK_DISPATCH_RUNS_COL,
    TALENT_NETWORK_JOB_HEARTBEAT_ID,
    scheduled_talent_network_campaign_scheduler,
    scheduled_talent_network_role_alert_dispatch,
)

# ── Security / audits ───────────────────────────────────────────────
from scheduler_jobs.security import (  # noqa: F401
    scheduled_production_security_policy_gate,
    scheduled_release_intelligence_monitor,
    scheduled_security_incident_runbook_monitor,
    scheduled_zero_trust_auto_mitigation,
    scheduled_zero_trust_daily_email_digest,
)
from scheduler_jobs.security_defense import (  # noqa: F401
    scheduled_active_defense_nightly_scan,
    scheduled_autonomous_blocked_attempts_export,
    scheduled_siem_webhook_dead_letter_retry,
)

# ── Digests & payments ──────────────────────────────────────────────
from scheduler_jobs.digests import (  # noqa: F401
    _send_weekly_quality_digest,
    scheduled_weekly_quality_digest,
    _send_job_search_weekly_digest,
    scheduled_job_search_weekly_digest,
)
from scheduler_jobs.payments import (  # noqa: F401
    scheduled_bill_generator_hourly_daemon,
    scheduled_fedapay_webhook_self_heal,
    scheduled_resend_webhook_guard,
    scheduled_invoice_dunning,
    scheduled_stale_payment_expiry_sweep,
)

# ── Content & learning ──────────────────────────────────────────────
from scheduler_jobs.content import (  # noqa: F401
    scheduled_watch_videos_daily_drop,
)
from scheduler_jobs.learning import (  # noqa: F401
    scheduled_learning_certificate_anchor_batch,
    scheduled_learning_hub_assurance_guard,
    scheduled_learning_hub_email_dispatcher,
    scheduled_learning_hub_integrity_guard,
    scheduled_learning_hub_synthetic_canary,
    scheduled_learning_hub_video_maintenance,
    scheduled_learning_hub_weekly_autopublish,
)

# ── SSO / Auth / Visual audits / Preview cache / Global parity ──────
from scheduler_jobs.sso_auth_health import (  # noqa: F401
    scheduled_admin_e2e_health_gate,
    scheduled_auth_fallback_link_guardian,
    scheduled_cia_trust_heartbeat,
    scheduled_multi_region_auth_probe,
    scheduled_sso_e2e_validation_alerts,
    scheduled_sso_provider_registration_alignment_auto,
    scheduled_sso_redirect_auto_sync,
    scheduled_sso_redirect_drift_sentinel,
)
from scheduler_jobs.visual_audits import (  # noqa: F401
    scheduled_fee_visibility_visual_audit_hourly,
    scheduled_fee_visibility_visual_audit_nightly,
)
from scheduler_jobs.preview_cache import (  # noqa: F401
    scheduled_preview_cache_hygiene_hourly,
    scheduled_preview_cache_hygiene_nightly,
)
from scheduler_jobs.global_parity import (  # noqa: F401
    scheduled_global_parity_audit_hourly,
    scheduled_global_parity_audit_nightly,
)

# ── Theme guardrails / Key rotation ─────────────────────────────────
from scheduler_jobs.theme_guardrails import (  # noqa: F401
    scheduled_admin_tabs_theme_drift_report,
    scheduled_admin_tabs_theme_drift_weekly_digest,
    scheduled_theme_drift_nightly_detector,
    scheduled_theme_guardrail_scan,
)
from scheduler_jobs.key_rotation import (  # noqa: F401
    scheduled_key_rotation_compliance_bundle_autogen,
    scheduled_key_rotation_game_day_staleness_guard,
    scheduled_key_rotation_policy_attestation,
    scheduled_key_rotation_status_drift_monitor,
)

# ── Engagement / Enterprise / Pricing / i18n ────────────────────────
from scheduler_jobs.engagement import (  # noqa: F401
    scheduled_blog_v2_weekly_digest_cycle,
    scheduled_card_expiry_check,
    scheduled_referral_weekly_email,
    scheduled_smart_weekly_digest,
    scheduled_streak_protection_nudge,
    scheduled_weekly_engagement_emails,
    scheduled_welcome_back_check,
)
from scheduler_jobs.enterprise_enforcement import (  # noqa: F401
    scheduled_enterprise_lock_cycle,
    scheduled_global_rbac_subscription_enforcement,
    scheduled_quarterly_access_recertification,
    scheduled_slo_breach_auto_mitigation,
    scheduled_weekly_enterprise_standard_enforcement,
)
from scheduler_jobs.pricing import (  # noqa: F401
    scheduled_pricing_guard_nightly_monitor,
    scheduled_subscription_plan_guardrail,
)
from scheduler_jobs.i18n_accessibility import (  # noqa: F401
    scheduled_i18n_literal_autofix_dry_run_report,
    scheduled_nightly_darkmode_regression_scan,
    scheduled_weekly_email_contrast_compliance,
)

# ── Audit gates / Compliance / Hosting / Platform health ────────────
from scheduler_jobs.audit_gates import (  # noqa: F401
    scheduled_acceptance_report_refresh,
    scheduled_critical_journey_monitor,
    scheduled_e2e_regression_gate,
    scheduled_full_system_auto_audit,
    scheduled_logo_render_probe,
    scheduled_perf_audit,
    scheduled_preview_browser_e2e_wake_and_run,
)
from scheduler_jobs.compliance import (  # noqa: F401
    scheduled_daily_usage_summary,
    scheduled_tax_compliance_audit,
)
from scheduler_jobs.hosting import (  # noqa: F401
    _run_scheduled_assigned_host_guard,
    scheduled_assigned_host_guardian,
)
from scheduler_jobs.platform_health import (  # noqa: F401
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

# ── Misc (legacy bucket — 2 non-scheduled_* funcs) ──────────────────
from scheduler_jobs.misc import (  # noqa: F401
    check_meeting_reminders,
    run_auto_response_scan,
)

# ── Feature 32 policy lifecycle jobs ─────────────────────────────────
from scheduler_jobs.feature32_policy import (  # noqa: F401
    scheduled_feature32_override_policy_expiry_sweeper,
)
