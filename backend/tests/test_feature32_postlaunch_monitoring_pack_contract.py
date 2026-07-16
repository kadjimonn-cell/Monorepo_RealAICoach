from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feature32_reliability_endpoints_exist_and_are_admin_guarded() -> None:
    source = _read("/app/backend/routes/email_notifications.py")
    assert '@router.get("/reliability/overview")' in source
    assert '@router.get("/reliability/weekly-report-template")' in source
    assert 'raise HTTPException(status_code=403, detail="Admin only")' in source


def test_feature32_reliability_payload_contract_markers_present() -> None:
    source = _read("/app/backend/routes/email_notifications.py")
    assert 'async def _collect_feature32_reliability(window_days: int) -> dict:' in source
    assert '"uno_dispatch_success_rate_pct"' in source
    assert '"duplicate_key_collisions"' in source
    assert '"weekly_report_template"' in source
    assert '"template_markdown"' in source


def test_feature32_email_reliability_tab_wired_in_admin_console() -> None:
    panel_source = _read("/app/frontend/src/components/admin/EmailTemplatesPanel.tsx")
    console_source = _read("/app/frontend/src/components/OperationsConsoleView.tsx")
    phase_b_source = _read("/app/frontend/src/config/phaseBTabConsolidation.ts")

    assert "{ id: 'reliability', label: 'Reliability'" in panel_source
    assert "case 'email-reliability':" in console_source
    assert 'admin-console-open-email-reliability-button' in console_source
    assert "{ id: 'email-reliability', label: 'Email Reliability'" in phase_b_source
