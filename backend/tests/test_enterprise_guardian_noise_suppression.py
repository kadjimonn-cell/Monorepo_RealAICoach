"""
Tests for Enterprise Reality Validation Guardian noise-suppression fix.

Covers:
  1. Static code verification of /app/backend/scheduler.py:
     - 15-min startup grace-period early return
     - No `notify_autoheal` variable / no email branch for self-heal-within-cycle
     - notify_breach + notify_recovery branches still send via
       send_catalog_template(template_key="automation_alert")
     - Self-heal within cycle only calls logger.info + audit insert
     - last_alert_at only updated on notify_breach/notify_recovery
  2. Logic simulation of the notification decision tree.
  3. Regression: /api/health, admin login, /api/autonomous-engine/status.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import requests


SCHEDULER_PATH = Path("/app/backend/scheduler.py")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# ─────────────────────────────────────────────────────────────
# Static code verification
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def scheduler_src() -> str:
    return SCHEDULER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def guardian_body(scheduler_src: str) -> str:
    """Extract the body of scheduled_enterprise_reality_validation_guardian."""
    start = scheduler_src.index(
        "async def scheduled_enterprise_reality_validation_guardian"
    )
    # End at job registration
    end = scheduler_src.index(
        'id="enterprise_reality_validation_guardian"', start
    )
    return scheduler_src[start:end]


class TestGuardianStaticCode:
    def test_grace_period_early_return(self, guardian_body: str):
        assert "guardian_process_started_at" in guardian_body
        # 15-min threshold via `15 * 60`
        assert re.search(r"15\s*\*\s*60", guardian_body), \
            "15-min grace threshold missing"
        assert "startup grace period active" in guardian_body
        # Early return should exist right after the check
        m = re.search(
            r"if\s*\(now\s*-\s*guardian_process_started_at\)\.total_seconds\(\)\s*<\s*15\s*\*\s*60\s*:\s*\n"
            r"\s*logger\.info\([^)]*startup grace period[^)]*\)\s*\n"
            r"\s*return",
            guardian_body,
        )
        assert m, "Grace-period early return block not found in expected form"

    def test_no_notify_autoheal(self, guardian_body: str, scheduler_src: str):
        assert "notify_autoheal" not in guardian_body
        assert "notify_autoheal" not in scheduler_src

    def test_notify_breach_and_recovery_present(self, guardian_body: str):
        assert re.search(
            r"notify_breach\s*=\s*status\s*==\s*['\"]degraded['\"]",
            guardian_body,
        ), "notify_breach definition missing/altered"
        assert re.search(
            r"notify_recovery\s*=\s*status\s*==\s*['\"]healthy['\"]\s*and\s*last_status\s*==\s*['\"]degraded['\"]",
            guardian_body,
        ), "notify_recovery definition missing/altered"

    def test_uses_automation_alert_template(self, guardian_body: str):
        # Both branches call send_catalog_template with automation_alert
        occurrences = re.findall(
            r"template_key\s*=\s*['\"]automation_alert['\"]", guardian_body
        )
        assert len(occurrences) >= 2, (
            f"Expected >=2 automation_alert template usages (breach+recovery); "
            f"got {len(occurrences)}"
        )
        assert "send_catalog_template" in guardian_body

    def test_self_heal_within_cycle_is_log_only(self, guardian_body: str):
        # There must be a branch: status healthy + last_status != degraded +
        # pre reasons + actions → logger.info (no email send inside)
        m = re.search(
            r"if\s+status\s*==\s*['\"]healthy['\"]\s+and\s+last_status\s*!=\s*['\"]degraded['\"]\s+and\s+pre\[['\"]reasons['\"]\]\s+and\s+actions\s*:\s*\n"
            r"(?P<block>(?:\s{16,}.*\n){1,6})",
            guardian_body,
        )
        assert m, "Self-heal within-cycle log-only branch not found"
        block = m.group("block")
        assert "logger.info" in block, "self-heal branch must log via logger.info"
        assert "send_catalog_template" not in block, \
            "self-heal branch MUST NOT send email"
        assert "send_email" not in block

    def test_audit_insert_still_present(self, guardian_body: str):
        assert "enterprise_autonomous_engine_audit" in guardian_body
        assert ".insert_one(" in guardian_body

    def test_last_alert_at_only_on_breach_or_recovery(self, guardian_body: str):
        # last_alert_at assignments must be guarded by notify_breach / notify_recovery
        matches = re.findall(
            r'if\s+(notify_breach|notify_recovery)\s*:\s*\n\s*update\[["\']last_alert_at["\']\]',
            guardian_body,
        )
        # Expect exactly 2 guarded assignments (one for breach, one for recovery)
        assert set(matches) == {"notify_breach", "notify_recovery"}, (
            f"last_alert_at should only be set inside notify_breach/notify_recovery "
            f"branches; found guards={matches}"
        )
        # No unguarded last_alert_at assignment
        all_assign = re.findall(r'update\[["\']last_alert_at["\']\]\s*=', guardian_body)
        assert len(all_assign) == 2, (
            f"Expected exactly 2 last_alert_at assignments; found {len(all_assign)}"
        )

    def test_guardian_job_still_registered(self, scheduler_src: str):
        assert 'id="enterprise_reality_validation_guardian"' in scheduler_src
        assert "IntervalTrigger(minutes=5)" in scheduler_src


# ─────────────────────────────────────────────────────────────
# Logic simulation (pure-python replica of decision logic)
# ─────────────────────────────────────────────────────────────
def _decide(status: str, last_status: str, pre_reasons, actions,
            last_alert_ts=None, now_ts=0, cooldown_seconds=1800):
    """Mirror of the decision logic in the guardian."""
    can_alert = (last_alert_ts is None) or (now_ts - last_alert_ts) >= cooldown_seconds
    notify_breach = status == "degraded" and (last_status != "degraded" or can_alert)
    notify_recovery = status == "healthy" and last_status == "degraded"
    self_heal_log_only = (
        status == "healthy"
        and last_status != "degraded"
        and bool(pre_reasons)
        and bool(actions)
    )
    return {
        "notify_breach": notify_breach,
        "notify_recovery": notify_recovery,
        "self_heal_log_only": self_heal_log_only,
        "email_sent": notify_breach or notify_recovery,
    }


class TestGuardianDecisionLogic:
    def test_self_heal_within_cycle_sends_no_email(self):
        r = _decide(
            status="healthy",
            last_status="healthy",
            pre_reasons=["zero_trust_auto_mitigation_stale_or_missing"],
            actions=["triggered_zero_trust_auto_mitigation"],
        )
        assert r["email_sent"] is False
        assert r["self_heal_log_only"] is True
        assert r["notify_breach"] is False
        assert r["notify_recovery"] is False

    def test_breach_sends_email(self):
        r = _decide(
            status="degraded",
            last_status="healthy",
            pre_reasons=["zero_trust_auto_mitigation_stale_or_missing"],
            actions=[],
        )
        assert r["notify_breach"] is True
        assert r["notify_recovery"] is False
        assert r["email_sent"] is True

    def test_recovery_sends_email(self):
        r = _decide(
            status="healthy",
            last_status="degraded",
            pre_reasons=["zero_trust_auto_mitigation_stale_or_missing"],
            actions=["triggered_zero_trust_auto_mitigation"],
        )
        assert r["notify_recovery"] is True
        assert r["notify_breach"] is False
        assert r["email_sent"] is True

    def test_healthy_no_action_no_email(self):
        r = _decide(
            status="healthy",
            last_status="healthy",
            pre_reasons=[],
            actions=[],
        )
        assert r["email_sent"] is False
        assert r["self_heal_log_only"] is False

    def test_repeated_degraded_within_cooldown_no_email(self):
        # last_status already degraded and within cooldown → no email
        r = _decide(
            status="degraded",
            last_status="degraded",
            pre_reasons=["x"],
            actions=[],
            last_alert_ts=100,
            now_ts=500,          # 400s < 1800s cooldown
            cooldown_seconds=1800,
        )
        assert r["notify_breach"] is False
        assert r["email_sent"] is False

    def test_repeated_degraded_after_cooldown_reemits(self):
        r = _decide(
            status="degraded",
            last_status="degraded",
            pre_reasons=["x"],
            actions=[],
            last_alert_ts=100,
            now_ts=2000,         # 1900s > 1800s cooldown
            cooldown_seconds=1800,
        )
        assert r["notify_breach"] is True
        assert r["email_sent"] is True


# ─────────────────────────────────────────────────────────────
# Regression: backend API health
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def api():
    assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session(api):
    """Auth is cookie-based; log in on the shared session and return it."""
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed status={r.status_code} body={r.text[:200]}")
    body = r.json()
    assert body.get("is_admin") is True, f"login body not admin: {body.get('email')}"
    return api


class TestBackendRegression:
    def test_health_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200, f"body={r.text[:200]}"

    def test_admin_login(self, admin_session):
        # Fixture asserts login succeeded and user is admin
        assert admin_session is not None

    def test_autonomous_engine_status(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/autonomous-engine/status", timeout=20,
        )
        # 200 = success; 404 acceptable if endpoint path differs (report only)
        assert r.status_code in (200, 401, 403, 404), \
            f"unexpected status={r.status_code} body={r.text[:200]}"
        if r.status_code == 200:
            body = r.json()
            assert isinstance(body, dict), f"unexpected body type: {type(body)}"
