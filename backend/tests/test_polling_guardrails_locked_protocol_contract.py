from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_api_has_hard_429_cooldown_rules_for_critical_endpoints() -> None:
    source = _read("/app/frontend/src/services/api.ts")
    assert "const HARD_429_COOLDOWN_RULES" in source
    for endpoint in [
        "/gps/state",
        "/onboarding-ab/assign",
        "/subscriptions/renewal-banner",
        "/subscriptions/plans",
        "/notifications/",
    ]:
        assert endpoint in source


def test_appshel_route_scopes_noncritical_pollers() -> None:
    source = _read("/app/frontend/src/components/AppShell.tsx")
    assert "enableHeavyBackgroundPollers" in source
    assert "shouldShowRenewalBanner" in source
    assert "shouldShowOnboarding" in source


def test_gps_hook_uses_slow_interval_and_no_consistency_post() -> None:
    source = _read("/app/frontend/src/hooks/useGlobalPlatformState.ts")
    assert "const GPS_MAX_POLL_INTERVAL_MS = 300_000;" in source
    assert "const GPS_MIN_POLL_INTERVAL_MS = 45_000;" in source
    assert "const fallbackIntervalMs = shouldRunFastFallback" in source
    assert "Math.max(GPS_MAX_POLL_INTERVAL_MS, retryDelayMs)" in source
    assert "Math.max(GPS_MIN_POLL_INTERVAL_MS, retryDelayMs)" in source
    assert "const id = setInterval(fetchState, fallbackIntervalMs);" in source
    assert "/gps/consistency/check" not in source


def test_p2_gtec_write_path_hydration_and_dast_shared_utility_contract() -> None:
    svc = _read("/app/backend/services/gtec_scan_v2.py")
    util = _read("/app/backend/utils/gtec_scan_artifacts.py")

    assert "async def hydrate_report_write_path" in svc
    assert "final_report = await hydrate_report_write_path(db, final_report, legacy_mirror_on=legacy_mirror_on)" in svc
    assert "def resolve_external_frontend_base_url(" in util
    assert "def is_runtime_429_artifact(" in util
    assert "def is_public_api_auth_rate_limit_artifact(" in util


def test_onboarding_and_renewal_have_session_markers() -> None:
    onboarding = _read("/app/frontend/src/components/SmartOnboarding.tsx")
    renewal = _read("/app/frontend/src/components/RenewalBanner.tsx")
    assert "onboarding:ab:assigned:" in onboarding
    assert "setSessionAssignMarker(currentUserId)" in onboarding
    assert "renewal:banner:fetched:" in renewal
    assert "setRenewalFetchMarker(currentUserId)" in renewal


def test_notifications_workspace_avoids_duplicate_provider_polling() -> None:
    source = _read("/app/frontend/src/components/notifications/NotificationsWorkspace.tsx")
    assert "const providerActive = scope == 'user'".replace("==", "===") in source
    assert "setInterval(() => { void fetchNotificationsRef.current(); }, 120000)" in source


def test_support_tickets_uses_websocket_first_hybrid_fallback_polling() -> None:
    source = _read("/app/frontend/src/components/admin/SupportTicketsPanel.tsx")
    helper = _read("/app/frontend/src/utils/hybridPolling.ts")

    assert "export function getHybridPollingInterval(config: HybridPollingConfig): number" in helper
    assert "export type WorkflowPollingPresetKey" in helper
    assert "export const WORKFLOW_POLLING_PRESETS" in helper
    assert "'support-ticket-fallback':" in helper
    assert "'batch-job-status':" in helper
    assert "'webhook-stream-fallback':" in helper
    assert "export function getWorkflowPollingPreset(" in helper
    assert "const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('support-ticket-fallback');" in source
    assert "const TICKET_POLL_MAX_INTERVAL_MS = WORKFLOW_POLLING_PRESET.slowIntervalMs;" in source
    assert "const TICKET_POLL_MIN_INTERVAL_MS = WORKFLOW_POLLING_PRESET.fastIntervalMs;" in source
    assert "const fallbackIntervalMs = getHybridPollingInterval({" in source
    assert "thresholdAttempt: 3" in source
    assert "TICKET_POLL_MIN_INTERVAL_MS" in source
    assert "TICKET_POLL_MAX_INTERVAL_MS" in source
    assert "runOnMount: WORKFLOW_POLLING_PRESET.runOnMount" in source
    assert "wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled" in source
    assert "const { socketRef: managedSocketRef, lastError, reconnectAttempt } = useManagedWebSocket({" in source


def test_batch_ai_workflow_panel_uses_shared_polling_preset() -> None:
    source = _read("/app/frontend/src/components/admin/BatchAIPanel.tsx")
    assert "const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('batch-job-status');" in source
    assert "runOnMount: WORKFLOW_POLLING_PRESET.runOnMount" in source
    assert "slowIntervalMs: WORKFLOW_POLLING_PRESET.slowIntervalMs" in source
    assert "fastIntervalMs: WORKFLOW_POLLING_PRESET.fastIntervalMs" in source
    assert "wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled" in source


def test_webhook_event_stream_workflow_panel_uses_shared_polling_preset() -> None:
    source = _read("/app/frontend/src/components/admin/WebhookEventStreamPanel.tsx")
    assert "const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('webhook-stream-fallback');" in source
    assert "runOnMount: WORKFLOW_POLLING_PRESET.runOnMount" in source
    assert "slowIntervalMs: WORKFLOW_POLLING_PRESET.slowIntervalMs" in source
    assert "fastIntervalMs: WORKFLOW_POLLING_PRESET.fastIntervalMs" in source
    assert "wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled" in source


def test_seo_dashboard_uses_hybrid_polling_policy_helper() -> None:
    source = _read("/app/frontend/src/components/admin/SEODashboardPanel.tsx")
    assert "const SEO_POLL_MAX_INTERVAL_MS = 30000;" in source
    assert "const SEO_POLL_MIN_INTERVAL_MS = 12000;" in source
    assert "useHybridPolling({" in source
    assert "errorScope: 'admin/seo-dashboard/hybrid-refresh'" in source
    assert "runOnMount: false" in source
    assert "slowIntervalMs: SEO_POLL_MAX_INTERVAL_MS" in source
    assert "fastIntervalMs: SEO_POLL_MIN_INTERVAL_MS" in source


def test_performance_guardian_uses_hybrid_polling_policy_helper() -> None:
    source = _read("/app/frontend/src/components/admin/PerformanceGuardianPanel.tsx")
    assert "const PERFORMANCE_POLL_MAX_INTERVAL_MS = 30000;" in source
    assert "const PERFORMANCE_POLL_MIN_INTERVAL_MS = 12000;" in source
    assert "useHybridPolling({" in source
    assert "errorScope: 'admin/performance-guardian/hybrid-refresh'" in source
    assert "runOnMount: false" in source
    assert "slowIntervalMs: PERFORMANCE_POLL_MAX_INTERVAL_MS" in source
    assert "fastIntervalMs: PERFORMANCE_POLL_MIN_INTERVAL_MS" in source


def test_web_vitals_uses_hybrid_polling_policy_helper() -> None:
    source = _read("/app/frontend/src/components/admin/WebVitalsPanel.tsx")
    assert "const VITALS_POLL_MAX_INTERVAL_MS = 30000;" in source
    assert "const VITALS_POLL_MIN_INTERVAL_MS = 12000;" in source
    assert "useHybridPolling({" in source
    assert "errorScope: 'admin/web-vitals/hybrid-refresh'" in source
    assert "runOnMount: false" in source
    assert "slowIntervalMs: VITALS_POLL_MAX_INTERVAL_MS" in source
    assert "fastIntervalMs: VITALS_POLL_MIN_INTERVAL_MS" in source


def test_gps_label_blockers_require_live_runtime_mode_on_all_surfaces() -> None:
    welcome = _read("/app/frontend/app/welcome.tsx")
    help_screen = _read("/app/frontend/app/help.tsx")
    features = _read("/app/frontend/app/features/index.tsx")
    home = _read("/app/frontend/app/(tabs)/index.tsx")
    notifications = _read("/app/frontend/src/components/notifications/NotificationsWorkspace.tsx")

    assert (
        "if (!gpsFallbackActive && missingWelcomeDataKeys.length > 0 && !gpsError && gpsStatus === 'healthy' "
        "&& gpsDiagnostics?.mode === 'live')" in welcome
    )
    assert "if (missingHelpLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live')" in help_screen
    assert "if (missingFeatureLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live')" in features
    assert "if (missingHomeLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live')" in home
    assert "if (missingNotificationLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === \"live\")" in notifications
