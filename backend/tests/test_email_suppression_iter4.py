"""Iter4: Verify NONPROD_EMAIL_SUPPRESS_TEMPLATES_ALL_RECIPIENTS and WEBHOOK_AUTO_SYNC_ENABLED guards.

Login as admin (cookie auth, CSRF header), POST send-test for a suppressed template and
a non-suppressed template. We assert on HTTP status + response body markers; the log grep
is done separately by the test agent.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://full-stack-migrate-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PW = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:400]}"
    # verify /me is_admin
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 200
    body = me.json()
    assert body.get("is_admin") is True, f"expected admin, got: {body}"
    return s


LOG_PATH = "/var/log/supervisor/backend.err.log"


def _read_recent_log(after_iso: str) -> str:
    """Return the last 2 MB of the log filtered for lines newer than after_iso."""
    try:
        with open(LOG_PATH, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 2_000_000))
            tail = fh.read().decode("utf-8", errors="ignore")
        out = []
        for line in tail.splitlines():
            if after_iso in line or (line and line > after_iso):
                out.append(line)
        return "\n".join(out)
    except FileNotFoundError:
        return ""


class TestEmailSuppression:
    def test_suppressed_template_system_alert_admin(self, admin_session):
        """system_alert_admin is in NONPROD suppress list → log must show 'suppressed for all recipients'."""
        from datetime import datetime, timezone
        before_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        r = admin_session.post(
            f"{BASE_URL}/api/email-notifications/send-test/system_alert_admin",
            json={},
            timeout=30,
        )
        assert r.status_code in (200, 400, 500), f"unexpected status: {r.status_code} {r.text[:400]}"
        time.sleep(1.5)  # let logger flush
        recent = _read_recent_log(before_iso)
        assert "non-production template suppressed for all recipients" in recent and "template=system_alert_admin" in recent, (
            f"expected suppression log line for system_alert_admin after {before_iso}; recent log tail:\n{recent[-2000:]}"
        )
        # And there must be NO Resend Email sent line for system_alert_admin after our marker
        assert "system_alert_admin" not in recent or "[Resend] Email sent" not in recent.split("system_alert_admin")[-1][:600], (
            "unexpected [Resend] Email sent for system_alert_admin after suppression marker"
        )
        print(f"[iter4] system_alert_admin OK: status={r.status_code} body_head={r.text[:200]}")

    def test_normal_template_welcome_not_suppressed(self, admin_session):
        """welcome is NOT in NONPROD suppress list → log must NOT show 'suppressed for all recipients' for welcome."""
        from datetime import datetime, timezone
        before_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        r = admin_session.post(
            f"{BASE_URL}/api/email-notifications/send-test/welcome",
            json={},
            timeout=45,
        )
        assert r.status_code == 200, f"welcome send-test failed: {r.status_code} {r.text[:400]}"
        time.sleep(1.5)
        recent = _read_recent_log(before_iso)
        # welcome must not have been NONPROD-suppressed (cap-guardrail/dedupe is allowed - separate concern)
        forbidden = any(
            ("non-production template suppressed for all recipients" in ln and "template=welcome" in ln)
            for ln in recent.splitlines()
        )
        assert not forbidden, f"welcome was unexpectedly NONPROD-suppressed. recent tail:\n{recent[-2000:]}"
        print(f"[iter4] welcome not-suppressed OK: status={r.status_code} body_head={r.text[:200]}")
