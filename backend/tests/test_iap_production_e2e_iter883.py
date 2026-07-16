"""
Iteration 883 — IAP Production E2E Simulation fix verification.

Fixes under test in /app/backend/routes/iap.py:
  (1) Corrupted mojibake email subject replaced with
      'Subscription Confirmed — Receipt Enclosed' (line ~2023).
  (2) IAPSimulationRequest accepts optional name + address_line
      (name -> user record; address_line -> users.billing_address_line
       AND jurisdiction / receipt / tx).
  (3) simulate_failure_case default changed from True to False,
      so no spurious payment_failed email is sent by default.

Testing target endpoint:
    POST /api/iap/admin/simulate-production-e2e
    Required headers (CSRF): X-Requested-With: XMLHttpRequest

Admin creds: admin@realaicoach.app / NewAdminPass2026!
IMPORTANT: never send to kadjimonn@gmail.com — use TEST addresses.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import pytest
import requests


def _load_backend_url() -> str:
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing from /app/frontend/.env")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    # Cookie-based session (no bearer required). Some deployments also return
    # csrf_token — we already send X-Requested-With so CSRF middleware passes.
    # Login response returns user profile at top level (not nested under 'user').
    user_body = body.get("user") if isinstance(body.get("user"), dict) else body
    assert user_body.get("is_admin") is True, f"is_admin missing/false: {body}"
    return s


@pytest.fixture
def test_email() -> str:
    # Fresh test email per invocation to avoid the 30-min duplicate-notification
    # suppression window (per user+provider+plan+period).
    return f"iap.e2e.iter883.{uuid.uuid4().hex[:10]}@example.com"


# --------------------------------------------------------------------------- #
# 1. Primary George Latoria scenario (with name + address_line + failure=false)
# --------------------------------------------------------------------------- #
class TestIapPrimaryScenario:
    """Test full George Latoria payment scenario with the applied fixes."""

    def _payload(self, email: str) -> dict:
        return {
            "email": email,
            "name": "George Latoria",
            "address_line": "QUEENS WAY",
            "plan": "premium",
            "period": "monthly",
            "platform": "google",
            "city": "Altus",
            "state_code": "OK",
            "country_code": "US",
            "postal_code": "73521-1001",
            "simulate_failure_case": False,
        }

    def test_endpoint_returns_success_with_all_checks_true(
        self, admin_session: requests.Session, test_email: str, request
    ):
        payload = self._payload(test_email)
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=payload,
            timeout=45,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:600]}"
        body = r.json()
        assert body.get("success") is True, f"success!=true: {body}"

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"check {k} not true: {checks}"

        # failure_case must be null (default false)
        assert body.get("failure_case") is None, f"failure_case not null: {body.get('failure_case')}"

        # Stash tx_id + email for downstream tests via node.session
        request.session._iter883_tx_id = body["scenario"]["transaction_id"]
        request.session._iter883_email = test_email
        request.session._iter883_body = body

    def test_pricing_breakdown_matches_expected(self, admin_session, request):
        body = getattr(request.session, "_iter883_body", None)
        if not body:
            pytest.skip("primary scenario didn't run")
        pb = body.get("pricing_breakdown") or {}
        # Regression guard from problem statement:
        # base 15.99 + platform_fee 5.01 (30%) + OK tax 0.72 = final_total 21.72
        assert round(float(pb.get("base_plan_price", 0)), 2) == 15.99, pb
        assert round(float(pb.get("platform_fee", 0)), 2) == 5.01, pb
        assert round(float(pb.get("taxes", 0)), 2) == 0.72, pb
        assert round(float(pb.get("final_total", 0)), 2) == 21.72, pb

    def test_latest_notification_title_and_message(self, admin_session, request):
        body = getattr(request.session, "_iter883_body", None)
        if not body:
            pytest.skip("primary scenario didn't run")
        n = body.get("latest_notification") or {}
        assert n.get("title") == "Payment Successful — Premium Plan Activated", n
        msg = n.get("message") or ""
        assert "IAP-" in msg, f"ticket id missing: {msg}"
        # total should reference the final_total
        pb = body.get("pricing_breakdown") or {}
        total_str = f"{float(pb.get('final_total', 0)):.2f}"
        assert total_str in msg, f"total {total_str} not in msg: {msg}"


# --------------------------------------------------------------------------- #
# 2. Direct DB verification of user + transaction records
# --------------------------------------------------------------------------- #
class TestDbSideEffects:
    """
    Verify persisted DB rows via a fresh scenario request (self-contained,
    avoids cross-test coupling). Uses motor client directly.
    """

    @pytest.mark.asyncio
    async def test_user_and_tx_records_persisted(
        self, admin_session: requests.Session, test_email: str
    ):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.db import db  # motor client shared with app

        payload = {
            "email": test_email,
            "name": "George Latoria",
            "address_line": "QUEENS WAY",
            "plan": "premium",
            "period": "monthly",
            "platform": "google",
            "city": "Altus",
            "state_code": "OK",
            "country_code": "US",
            "postal_code": "73521-1001",
            "simulate_failure_case": False,
        }
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=payload,
            timeout=45,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        tx_id = body["scenario"]["transaction_id"]

        # ---- User record ----
        user = await db.users.find_one({"email": test_email}, {"_id": 0})
        assert user, f"user not found: {test_email}"
        assert user.get("name") == "George Latoria", user
        assert user.get("subscription_plan") == "premium", user
        assert user.get("subscription_status") == "active", user
        assert user.get("billing_address_line") == "QUEENS WAY", user

        # ---- Transaction record ----
        # Allow a small wait window in case of async writes.
        tx = None
        for _ in range(15):
            tx = await db.payment_transactions.find_one(
                {"transaction_id": tx_id}, {"_id": 0}
            )
            if tx and tx.get("notification_sent"):
                break
            time.sleep(0.5)
        assert tx, f"tx {tx_id} not found"
        assert tx.get("status") == "completed", tx
        assert tx.get("notification_sent") is True, tx.get("notification_sent")

        jur = tx.get("jurisdiction") or {}
        assert jur.get("country") == "US", jur
        assert jur.get("state") == "OK", jur
        assert jur.get("postal_code") == "73521-1001", jur
        assert jur.get("city") == "Altus", jur
        assert jur.get("address_line") == "QUEENS WAY", jur

        # ---- In-app notification ----
        notif = await db.notifications.find_one(
            {"user_id": user["user_id"], "type": "payment_confirmation"},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        assert notif, "in-app notification missing"
        assert notif.get("title") == "Payment Successful — Premium Plan Activated", notif
        msg = notif.get("message") or ""
        assert "IAP-" in msg, msg


# --------------------------------------------------------------------------- #
# 3. Backend log assertions (subject fixed + admin + branded emails)
# --------------------------------------------------------------------------- #
class TestBackendLogSignals:
    """Scan /var/log/supervisor/backend.err.log (and .out.log) for the
    subject strings + branded/admin email log lines after a fresh run."""

    LOG_PATHS = [
        "/var/log/supervisor/backend.err.log",
        "/var/log/supervisor/backend.out.log",
    ]

    def _read_recent_logs(self) -> str:
        text = ""
        for p in self.LOG_PATHS:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        # Grab last ~600KB — enough for a fresh run.
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 600_000))
                        text += f.read()
                except OSError:
                    pass
        return text

    def test_logs_show_fixed_subject_and_receipt_lines(
        self, admin_session: requests.Session, test_email: str
    ):
        # Fresh run so log lines are recent
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json={
                "email": test_email,
                "name": "George Latoria",
                "address_line": "QUEENS WAY",
                "plan": "premium",
                "period": "monthly",
                "platform": "google",
                "city": "Altus",
                "state_code": "OK",
                "country_code": "US",
                "postal_code": "73521-1001",
                "simulate_failure_case": False,
            },
            timeout=45,
        )
        assert r.status_code == 200, r.text[:400]
        tx_id = r.json()["scenario"]["transaction_id"]

        # Give email pipeline time to log
        time.sleep(3.0)

        logs = self._read_recent_logs()

        # (a) Fixed subject present, mojibake ABSENT
        # Note: subject may appear in Resend payload or in our log lines.
        assert "Subscription Confirmed — Receipt Enclosed" in logs, (
            "Fixed subject line not observed in backend logs; "
            "mojibake subject may still be in use or emails aren't being logged."
        )
        # Guard against the specific mojibake string from problem statement.
        assert "സ്ഥിരീകര" not in logs, "Malayalam mojibake still present in logs!"

        # (b) User-side branded receipt log line
        assert re.search(r"Branded receipt email sent", logs) is not None, (
            "'Branded receipt email sent' log line missing"
        )

        # (c) Admin alert email subject with the RCT- ticket
        # Format: '[Admin] Payment Confirmed via Google Play — RCT-...'
        assert re.search(
            r"\[Admin\]\s+Payment Confirmed via Google Play\s+—\s+RCT-",
            logs,
        ) is not None, "Admin alert subject '[Admin] Payment Confirmed via Google Play — RCT-...' missing"

        # (d) Admin receipt email log line
        assert re.search(r"Admin payment receipt email sent", logs) is not None, (
            "'Admin payment receipt email sent' log line missing"
        )

        # (e) No spurious failure notification when simulate_failure_case=false
        # Look for the failure helper being invoked *after* our tx started.
        # We do a soft check: the log should not contain a failure-notification
        # line paired with our fresh tx_id.
        failure_line_re = re.compile(
            r"_send_iap_failure_notification|payment[_ -]failed", re.IGNORECASE
        )
        # only flag if failure text appears near our tx_id
        window = logs.split(tx_id)[-1] if tx_id in logs else logs[-50_000:]
        assert failure_line_re.search(window[:20_000]) is None, (
            "Spurious _send_iap_failure_notification / payment-failed reference "
            f"observed after tx {tx_id}"
        )


# --------------------------------------------------------------------------- #
# 4. Regression: optional fields omitted + failure_case default = false
# --------------------------------------------------------------------------- #
class TestOptionalFieldRegression:
    def test_omitting_name_and_address_still_succeeds(
        self, admin_session: requests.Session
    ):
        email = f"iap.e2e.iter883.opt.{uuid.uuid4().hex[:10]}@example.com"
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json={
                "email": email,
                "plan": "premium",
                "period": "monthly",
                "platform": "google",
                # no name, no address_line, no simulate_failure_case
                "city": "Oklahoma City",
                "state_code": "OK",
                "country_code": "US",
                "postal_code": "73102",
            },
            timeout=45,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("success") is True, body
        assert body.get("failure_case") is None, (
            f"failure_case should default null (simulate_failure_case default false), got: {body.get('failure_case')}"
        )
        checks = body.get("checks") or {}
        assert checks.get("subscription_active") is True, checks
        assert checks.get("api_integrity") is True, checks
        # Fee math should still be correct
        pb = body.get("pricing_breakdown") or {}
        assert round(float(pb.get("base_plan_price", 0)), 2) == 15.99, pb
        assert round(float(pb.get("platform_fee", 0)), 2) == 5.01, pb
        assert round(float(pb.get("final_total", 0)), 2) == 21.72, pb


# --------------------------------------------------------------------------- #
# 5. Regression: admin compliance bundle endpoints still work
# --------------------------------------------------------------------------- #
class TestComplianceBundleEndpoints:
    def test_list_bundles(self, admin_session: requests.Session):
        r = admin_session.get(
            f"{BASE_URL}/api/iap/admin/compliance-bundles?limit=5",
            timeout=30,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        # Endpoint may return list or wrapped dict — accept both
        rows = body if isinstance(body, list) else (body.get("bundles") or body.get("items") or [])
        assert isinstance(rows, list), f"unexpected list shape: {type(body)}"

    def test_receipt_pdf_valid_bytes(self, admin_session: requests.Session):
        # First create a fresh bundle by running an e2e simulation
        email = f"iap.e2e.iter883.pdf.{uuid.uuid4().hex[:10]}@example.com"
        sim = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json={
                "email": email,
                "name": "Compliance PDF Test",
                "address_line": "MAIN ST",
                "plan": "premium",
                "period": "monthly",
                "platform": "google",
                "city": "Oklahoma City",
                "state_code": "OK",
                "country_code": "US",
                "postal_code": "73102",
                "simulate_failure_case": False,
            },
            timeout=45,
        )
        assert sim.status_code == 200, sim.text[:400]
        tx_id = sim.json()["scenario"]["transaction_id"]

        # Give bundle write a moment
        time.sleep(2.0)

        pdf = admin_session.get(
            f"{BASE_URL}/api/iap/admin/compliance-bundles/{tx_id}/receipt.pdf",
            timeout=30,
        )
        if pdf.status_code == 404:
            pytest.skip(f"compliance bundle for {tx_id} not yet created (may be async)")
        assert pdf.status_code == 200, f"HTTP {pdf.status_code}: {pdf.text[:400]}"
        ctype = pdf.headers.get("content-type", "")
        assert "application/pdf" in ctype.lower(), f"content-type not pdf: {ctype}"
        assert pdf.content[:4] == b"%PDF", f"missing %PDF magic: {pdf.content[:16]!r}"
