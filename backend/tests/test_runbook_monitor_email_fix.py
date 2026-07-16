"""Security Runbook Monitor email fix — dedicated template + noise control."""

import os
import sys
from datetime import datetime, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200
    return sess


class TestDedicatedTemplate:
    def test_registered_in_catalog(self):
        from utils.email_templates import TEMPLATE_CATALOG

        entry = TEMPLATE_CATALOG.get("security_runbook_monitor_report")
        assert entry, "security_runbook_monitor_report missing from TEMPLATE_CATALOG"

    def test_renders_structured_report_not_markdown(self):
        from utils.email_templates import build_security_runbook_monitor_report_email

        tpl = build_security_runbook_monitor_report_email(
            rag="RED", monitor_run_id="keyrot_mon_test123", trigger_source="scheduler",
            executed_at="2026-07-13T00:00:00+00:00", mode="SAFE_AUTO",
            metrics={"api_rotate_ready": 0, "api_probe_only_ready": 3, "manual_by_constraint": 3,
                     "rotate_contract_hard_blocked": 1, "policy_gate_passed": False,
                     "siem_webhook_configured": False, "siem_webhook_validated": False},
            top_risks=["SIEM incident webhook is not configured in runtime environment."],
            milestones={"d30": "Close blockers.", "d60": "Verify cutover.", "d90": "Sustain cadence."},
            bundle_id="N/A", bundle_generated_at="N/A", send_reason="rag_change",
        )
        assert 'class="em-outer"' in tpl.html, "must carry v7 _wrap fingerprint"
        assert "[Security Runbook Monitor] RED" in tpl.subject
        assert "## " not in tpl.html, "raw markdown headings must not appear"
        assert "**RED**" not in tpl.html, "raw markdown bold must not appear"
        assert "keyrot_mon_test123" in tpl.html
        assert "Status change alert" in tpl.html
        assert "SIEM incident webhook" in tpl.html
        assert "not a support conversation" in tpl.html
        # No fake support framing
        assert "responded to your inquiry" not in tpl.html

    def test_rag_color_mapping(self):
        from utils.email_templates import build_security_runbook_monitor_report_email

        assert "#DC2626" in build_security_runbook_monitor_report_email(rag="RED").html
        assert "#D97706" in build_security_runbook_monitor_report_email(rag="AMBER").html
        assert "#059669" in build_security_runbook_monitor_report_email(rag="GREEN").html

    def test_admin_outbound_template_untouched(self):
        from utils.email_templates import build_admin_outbound_email

        tpl = build_admin_outbound_email(body="hello", original_subject="Test")
        assert "responded to your inquiry" in tpl.html
        assert tpl.subject == "Re: Test"

    def test_catalog_builders_map_to_correct_functions(self):
        from utils.email_templates import TEMPLATE_CATALOG

        assert TEMPLATE_CATALOG["admin_outbound"]["builder"].__name__ == "build_admin_outbound_email"
        assert TEMPLATE_CATALOG["security_runbook_monitor_report"]["builder"].__name__ == \
            "build_security_runbook_monitor_report_email"


class TestNoiseControl:
    @pytest.mark.asyncio
    async def test_scheduler_run_suppressed_when_rag_stable_and_already_emailed(self):
        """A scheduler-triggered cycle with unchanged RAG after today's email must be suppressed."""
        from dotenv import load_dotenv

        load_dotenv("/app/backend/.env")
        from routes.security_key_rotation import run_security_runbook_monitor_cycle
        from routes.db import db

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prior = await db.security_runbook_monitor_notifications.count_documents(
            {"success": True, "created_at": {"$gte": today}})
        latest = await db.security_runbook_monitor_runs.find_one({}, {"_id": 0, "rag": 1},
                                                                 sort=[("executed_at", -1)]) or {}
        if not prior or not latest.get("rag"):
            pytest.skip("No prior emailed run today — suppression scenario not reproducible")
        result = await run_security_runbook_monitor_cycle(trigger_source="scheduler", force=True)
        assert result.get("status") == "ok"
        ntf = await db.security_runbook_monitor_notifications.find_one(
            {"monitor_run_id": result["monitor_run_id"]}, {"_id": 0})
        if result.get("rag") == latest["rag"]:
            assert ntf.get("suppressed") is True, f"expected suppression, got {ntf}"
            assert ntf.get("send_reason") is None
            assert ntf.get("success") is False
        else:
            assert ntf.get("send_reason") == "rag_change"

    @pytest.mark.asyncio
    async def test_manual_run_always_emails(self):
        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient

        load_dotenv("/app/backend/.env")
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        ntf = await db.security_runbook_monitor_notifications.find_one(
            {"send_reason": "manual"}, {"_id": 0}, sort=[("created_at", -1)])
        assert ntf, "manual run notification missing"
        assert ntf.get("success") is True


class TestRegression:
    def test_monitor_status_endpoint(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/security/key-rotation/monitor/status", timeout=60)
        assert r.status_code == 200

    def test_monitor_history_endpoint(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/security/key-rotation/monitor/history", timeout=60)
        assert r.status_code == 200
