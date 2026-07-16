"""RED→GREEN remediation: policy gate checks, CIA heartbeat, payment sweep,
a11y auto-fixer corruption guard."""

import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


def _db():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient

    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited")
    assert r.status_code == 200
    return sess


class TestPolicyGate:
    @pytest.mark.asyncio
    async def test_all_four_checks_pass(self):
        from utils.production_security_policy_gate import collect_policy_gate_signals

        sig = await collect_policy_gate_signals(_db())
        by_name = {c["name"]: c["passed"] for c in sig["checks"]}
        assert by_name["admin_e2e_health_gate"] is True
        assert by_name["subscription_plan_guardrail"] is True
        assert by_name["sso_e2e_validation"] is True
        assert by_name["cia_trust_score"] is True

    @pytest.mark.asyncio
    async def test_guardrail_accepts_status_field(self):
        db = _db()
        doc = await db.subscription_plan_guardrail_runs.find_one({}, sort=[("ran_at", -1)])
        assert doc.get("status") == "pass" and "state" not in doc, "writer schema uses 'status'"
        from utils.production_security_policy_gate import collect_policy_gate_signals

        sig = await collect_policy_gate_signals(db)
        check = next(c for c in sig["checks"] if c["name"] == "subscription_plan_guardrail")
        assert check["passed"] is True, "gate must tolerate status-field schema"


class TestCiaTrustHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_persisted_with_pillars(self):
        db = _db()
        hb = await db.cia_trust_heartbeat.find_one({}, sort=[("captured_at", -1)])
        assert hb, "cia_trust_heartbeat must have documents now"
        assert float(hb["trust_score"]) >= 75
        for pillar in ("confidentiality", "integrity", "availability"):
            assert hb.get(pillar) is not None

    @pytest.mark.asyncio
    async def test_no_stale_pending_payments(self):
        from datetime import datetime, timezone, timedelta

        db = _db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        stale = await db.payment_transactions.count_documents(
            {"status": {"$in": ["pending", "processing"]}, "created_at": {"$lt": cutoff}})
        assert stale == 0, f"{stale} stale pending payments remain"


class TestRunbookRag:
    @pytest.mark.asyncio
    async def test_latest_run_is_amber_with_rag_change_email(self):
        db = _db()
        run = await db.security_runbook_monitor_runs.find_one({}, sort=[("executed_at", -1)])
        assert run["rag"] in ("AMBER", "GREEN"), f"runbook still {run['rag']}"
        ntf = await db.security_runbook_monitor_notifications.find_one(
            {"send_reason": "rag_change", "previous_rag": "RED"}, sort=[("created_at", -1)])
        assert ntf and ntf["success"] is True


class TestA11yAutoFixerSafety:
    def test_safe_insert_skips_generics(self):
        from routes.accessibility_audit import _safe_insert_label

        assert _safe_insert_label('  const r = useRef<TextInput>(null);', "TextInput", "X") is None

    def test_safe_insert_skips_arrow_only_lines(self):
        from routes.accessibility_audit import _safe_insert_label

        line = '<TouchableOpacity onPress={() => setX(1)} style={s.btn}>'
        out = _safe_insert_label(line, "TouchableOpacity", "Button")
        assert out == '<TouchableOpacity onPress={() => setX(1)} style={s.btn} accessibilityLabel="Button">'
        assert "= accessibilityLabel" not in out.replace('} accessibilityLabel', '')

    def test_safe_insert_self_closing(self):
        from routes.accessibility_audit import _safe_insert_label

        out = _safe_insert_label('<Image source={img} />', "Image", "Logo")
        assert out == '<Image source={img}  accessibilityLabel="Logo"/>'

    def test_safe_insert_multiline_tag_returns_none(self):
        from routes.accessibility_audit import _safe_insert_label

        assert _safe_insert_label('<TouchableOpacity', "TouchableOpacity", "X") is None

    def test_no_corruption_patterns_in_source(self):
        import subprocess

        guard = subprocess.run(["python3", "/app/scripts/auto_fixer_corruption_guard.py"],
                               capture_output=True, text=True, timeout=120)
        assert guard.returncode == 0, guard.stdout[-1000:]


class TestFrontendRoutesServe:
    @pytest.mark.parametrize("path", ["/", "/dashboard", "/admin-console", "/careers/offer/confirm"])
    def test_route_returns_200(self, path):
        r = requests.get(f"{BASE_URL}{path}", timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


class TestRegression:
    def test_platform_perf_audits_healthy(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/platform-perf/navigation-lock-audit", timeout=60)
        assert r.json().get("status") == "healthy"
        r2 = admin.get(f"{BASE_URL}/api/admin/platform-perf/route-integrity-checker", timeout=60)
        assert r2.json().get("missing_from_whitelist") == []
        assert r2.json().get("stale_whitelist_segments") == []

    def test_agent_framework_untouched(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/overview", timeout=60)
        assert r.status_code == 200 and r.json()["agents"] >= 200
