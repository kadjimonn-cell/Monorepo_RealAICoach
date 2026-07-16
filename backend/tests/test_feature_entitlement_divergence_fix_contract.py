from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feature1_writing_studio_normalizes_owner_id_for_user_lookup() -> None:
    source = _read("/app/backend/routes/writing_studio.py")
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '{"user_id": user_id},' in source


def test_feature2_personal_assistant_uses_subscription_plan_field() -> None:
    source = _read("/app/backend/routes/personal_assistant.py")
    assert '"subscription_plan": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source
    assert 'subscription_tier' not in source


def test_feature3_research_navigator_uses_subscription_plan_field() -> None:
    source = _read("/app/backend/routes/research_navigator.py")
    assert '"subscription_plan": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source
    assert 'subscription_tier' not in source


def test_feature5_decision_coach_uses_subscription_plan_field() -> None:
    source = _read("/app/backend/routes/decision_coach.py")
    assert '"subscription_plan": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source
    assert 'subscription_tier' not in source


def test_feature10_smart_shopping_uses_user_id_not_owner_id_field() -> None:
    source = _read("/app/backend/routes/smart_shopping_advisor.py")
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '{"user_id": user_id},' in source
    assert 'find_one({"owner_id": owner_id}' not in source


def test_feature4_workflow_builder_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/workflow_builder.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature8_fitness_planner_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/fitness_planner.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature9_money_strategy_hub_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/money_strategy_hub.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature11_travel_planner_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/travel_planner_pro.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature12_relationship_coach_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/relationship_coach.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature24_learning_coach_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/learning_coach.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature7_health_guide_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/health_guide.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature33_library_route_enforces_plan_gate_with_effective_plan() -> None:
    # POLICY 2026-06.v3: Library is open to Free with limited access; the
    # platform entitlement meter enforces daily limits instead of a 403 gate.
    source = _read("/app/backend/routes/content.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert "def _require_library_plan_access(user_ctx: Any) -> Optional[dict]:" in source
    assert "POLICY 2026-06.v3" in source


def test_feature16_17_18_admin_is_normalized_to_premium() -> None:
    for path in [
        "/app/backend/routes/ai_photo_studio.py",
        "/app/backend/routes/ai_speech_studio.py",
        "/app/backend/routes/ai_enterprise_copilot.py",
    ]:
        source = _read(path)
        assert 'if bool(getattr(user, "is_admin", False)):' in source
        assert 'return "premium"' in source


def test_feature13_mobility_assistant_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/mobility_assistant.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature15_video_creator_studio_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/video_creator_studio.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(getattr(user, "user_id", "") or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "plan = compute_effective_plan(merged_doc)" in source


def test_writing_studio_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/writing_studio.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user or {})" in source


def test_smart_shopping_advisor_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/smart_shopping_advisor.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")' in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_personal_assistant_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/personal_assistant.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_research_navigator_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/research_navigator.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_decision_coach_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/decision_coach.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_health_wellness_learning_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/health_wellness_learning.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_real_estate_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/real_estate.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_school_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/school.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_ai_services_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/ai_services.py")
    assert "from utils.access_control_engine import build_session_entitlements, compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "plan = compute_effective_plan(user_doc or {})" in source


def test_cars_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/cars.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_integrations_ai_image_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert "effective = compute_effective_plan(user_doc or {})" in source


def test_feature_registry_hub_insights_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/feature_registry.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": getattr(user, "payment_verified", False)' in source
    assert "plan = compute_effective_plan(" in source


def test_home_dashboard_command_center_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/home_dashboard.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": getattr(user, "payment_verified", False)' in source
    assert "plan = compute_effective_plan(" in source


def test_sports_v2_service_plan_helper_uses_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/sports_v2_service.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": getattr(user, "payment_verified", False)' in source
    assert "return compute_effective_plan(" in source


def test_core_platform_subscription_helpers_use_global_effective_plan_engine() -> None:
    source = _read("/app/backend/routes/core_platform.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert source.count('"payment_verified": getattr(user, "payment_verified", False)') >= 2
    assert "effective_plan = compute_effective_plan(" in source


def test_feature_access_status_uses_effective_tier_for_plan_doc() -> None:
    source = _read("/app/backend/routes/feature_access.py")
    assert 'plan = "admin" if user.is_admin or getattr(user, "full_access", False) else effective_tier' in source
    assert 'plan_doc = await get_subscription_plan_from_gps(plan, default_plan_id="free") or {}' in source


def test_audio_studio_metrics_use_effective_plan_engine_for_user_plan_map() -> None:
    source = _read("/app/backend/routes/audio_studio_v2_service.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert '"payment_verified": 1' in source
    assert 'user_plan_map[uid] = _normalize_plan(compute_effective_plan(row))' in source


def test_ai_usage_analytics_uses_effective_plan_engine_for_reporting() -> None:
    source = _read("/app/backend/routes/ai_usage_analytics.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'plan = _effective_plan_from_user_doc(u)' in source
    assert 'effective_user_ids_by_plan' in source


def test_ai_feature_analytics_power_users_use_effective_plan_labels() -> None:
    source = _read("/app/backend/routes/ai_feature_analytics.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert '"plan": _effective_plan_from_user_doc(u),' in source


def test_platform_analytics_engagement_scores_use_effective_plan_labels() -> None:
    source = _read("/app/backend/routes/platform_analytics.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert '"plan": _effective_plan_from_user_doc(u),' in source


def test_ai_user_insights_use_effective_plan_for_paid_counts_and_labels() -> None:
    source = _read("/app/backend/routes/ai_user_insights.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'paid_users = sum(1 for row in paid_users_cursor if _effective_plan_from_user_doc(row) != "free")' in source
    assert 'paid = sum(1 for row in paid_cursor if _effective_plan_from_user_doc(row) != "free")' in source
    assert 'churn = _churn_risk(es, days_since, effective_plan)' in source


def test_payments_user_analytics_uses_effective_plan_for_plan_summary() -> None:
    source = _read("/app/backend/routes/payments_user_analytics_routes.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'plan_id = _effective_plan_from_user_doc(user_doc)' in source


def test_payments_reporting_uses_effective_plan_for_report_plan_name() -> None:
    source = _read("/app/backend/routes/payments_reporting_routes.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'plan = _effective_plan_from_user_doc(user_doc)' in source


def test_admin_payment_analytics_integrity_check_uses_effective_plan_labels() -> None:
    source = _read("/app/backend/routes/admin_payment_analytics.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'plan = _effective_plan_from_user_doc(user)' in source


def test_admin_sessions_use_effective_plan_labels_in_diagnostics() -> None:
    source = _read("/app/backend/routes/admin_sessions.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert '"plan": _effective_plan_from_user_doc(user_info),' in source


def test_payments_admin_maintenance_uses_effective_plan_labels_for_reminders() -> None:
    source = _read("/app/backend/routes/payments_admin_maintenance_routes.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'plan_name = await get_plan_name(_effective_plan_from_user_doc(u))' in source


def test_admin_console_expiry_notifications_use_effective_plan_labels() -> None:
    source = _read("/app/backend/routes/admin_console.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert '"message": f"{u.get(\'email\', \'\')} — {_effective_plan_from_user_doc(u)} expires soon",' in source


def test_admin_general_analytics_uses_effective_plan_for_paid_counts_and_distribution() -> None:
    source = _read("/app/backend/routes/admin_general_analytics.py")
    assert "from utils.access_control_engine import compute_effective_plan" in source
    assert 'def _effective_plan_from_user_doc(user_doc: dict | None) -> str:' in source
    assert 'paid_users = sum(1 for row in paid_user_rows if _effective_plan_from_user_doc(row) in {"basic", "premium"})' in source
    assert 'subscription_counts[plan] = subscription_counts.get(plan, 0) + 1' in source


def test_entitlement_drift_audit_service_exists_and_scans_sensitive_files() -> None:
    source = _read("/app/backend/services/entitlement_drift_audit.py")
    assert 'AUDIT_COLLECTION = "entitlement_drift_audit_log"' in source
    assert 'SENSITIVE_GLOBS = (' in source
    assert 'def scan_entitlement_drift() -> dict[str, Any]:' in source
    assert 'run_entitlement_drift_audit(trigger: str = "scheduled_daily")' in source
    assert 'baseline_established = previous is None' in source
    assert 'effective_status = "pass" if decorated["new_finding_count"] == 0 else' in source


def test_scheduler_registers_daily_entitlement_drift_audit_job() -> None:
    source = _read("/app/backend/scheduler.py")
    assert 'async def scheduled_entitlement_drift_audit():' in source
    assert 'id="daily_entitlement_drift_audit"' in source
    assert 'CronTrigger(hour=8, minute=20)' in source
