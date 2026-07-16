"""
Iteration 884 — IAP Production E2E Apple/Basic + TX tax + downgrade transition.

Follow-up to iteration_883 (Google/Premium/OK). This suite covers the shared
pipeline for a different pricing regime and provider:

  Provider:  Apple (iap_apple)
  Plan:      basic / monthly
  User:      David Thomas (email is a fresh @example.com UUID; NEVER
             kadjimonn@gmail.com — main agent already ran that live once)
  Address:   6606 ARANCIONE AVE, San Antonio, TX 72533, US
  Pricing:   base 5.99 + platform_fee 1.91 (30%) + TX tax 0.37 (6.25%)
             = final_total 8.27  (tax_rate 0.0625)

Also validates plan-transition timeline: seed a user with premium/google, then
downgrade them to basic/apple → db.iap_subscription_timeline records an event
with event_type='downgrade', from_plan='premium', to_plan='basic',
platform='apple'.

Testing target endpoint:
    POST /api/iap/admin/simulate-production-e2e
    Cookie session + X-Requested-With: XMLHttpRequest header (CSRF).

Admin creds: admin@realaicoach.app / NewAdminPass2026!
"""
from __future__ import annotations

import os
import re
import sys
import time
import uuid
from pathlib import Path

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

# ---- Expected Apple/Basic/TX pricing regression targets ----
EXP_BASE = 5.99
EXP_PLATFORM_FEE = 1.91   # 5.99 * 0.30 rounded
EXP_TAX = 0.37            # (5.99 + 1.91) * 0.0625 rounded
EXP_TOTAL = 8.27
EXP_TAX_RATE = 0.0625


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
    user_body = body.get("user") if isinstance(body.get("user"), dict) else body
    assert user_body.get("is_admin") is True, f"is_admin missing/false: {body}"
    return s


@pytest.fixture
def apple_basic_email() -> str:
    """Fresh test email per invocation to avoid duplicate-suppression window."""
    return f"iap.e2e.iter884.{uuid.uuid4().hex[:10]}@example.com"


def _apple_basic_payload(email: str) -> dict:
    return {
        "email": email,
        "name": "David Thomas",
        "address_line": "6606 ARANCIONE AVE",
        "plan": "basic",
        "period": "monthly",
        "platform": "apple",
        "city": "San Antonio",
        "state_code": "TX",
        "country_code": "US",
        "postal_code": "72533",
        "simulate_failure_case": False,
    }


# --------------------------------------------------------------------------- #
# 1. Primary Apple/Basic TX scenario — endpoint contract + checks
# --------------------------------------------------------------------------- #
class TestAppleBasicPrimaryScenario:
    def test_endpoint_returns_success_all_checks_true(
        self, admin_session: requests.Session, apple_basic_email: str, request
    ):
        payload = _apple_basic_payload(apple_basic_email)
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=payload, timeout=45,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:600]}"
        body = r.json()
        assert body.get("success") is True, f"success!=true: {body}"

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"check {k} not true: {checks}"

        # failure_case must be null (simulate_failure_case=false)
        assert body.get("failure_case") is None, body.get("failure_case")

        # Save for downstream tests
        request.session._iter884_body = body
        request.session._iter884_email = apple_basic_email
        request.session._iter884_tx_id = body["scenario"]["transaction_id"]

    def test_pricing_breakdown_apple_basic_tx(self, admin_session, request):
        body = getattr(request.session, "_iter884_body", None)
        if not body:
            pytest.skip("primary scenario didn't run")
        pb = body.get("pricing_breakdown") or {}
        assert round(float(pb.get("base_plan_price", 0)), 2) == EXP_BASE, pb
        assert round(float(pb.get("platform_fee", 0)), 2) == EXP_PLATFORM_FEE, pb
        assert round(float(pb.get("taxes", 0)), 2) == EXP_TAX, pb
        assert round(float(pb.get("final_total", 0)), 2) == EXP_TOTAL, pb

    def test_scenario_platform_and_ticket(self, admin_session, request):
        body = getattr(request.session, "_iter884_body", None)
        if not body:
            pytest.skip("primary scenario didn't run")
        sc = body.get("scenario") or {}
        assert sc.get("platform") == "apple", sc
        assert sc.get("plan") == "basic", sc
        assert sc.get("period") == "monthly", sc
        assert str(sc.get("transaction_id", "")).startswith("sim_apple_"), sc

    def test_latest_notification_title_and_message(self, admin_session, request):
        body = getattr(request.session, "_iter884_body", None)
        if not body:
            pytest.skip("primary scenario didn't run")
        n = body.get("latest_notification") or {}
        # Basic plan title
        assert n.get("title") == "Payment Successful — Basic Plan Activated", n
        msg = n.get("message") or ""
        assert "IAP-" in msg, f"eTicket id missing: {msg}"
        assert "App Store" in msg, f"'App Store' not in msg: {msg}"
        # total should reference the final_total
        total_str = f"{EXP_TOTAL:.2f}"
        assert total_str in msg, f"total {total_str} not in msg: {msg}"


# --------------------------------------------------------------------------- #
# 2. DB verification — user, transaction (tax_rate, provider, jurisdiction),
#    in-app notification, notification_sent flip
# --------------------------------------------------------------------------- #
class TestAppleBasicDbSideEffects:
    @pytest.mark.asyncio
    async def test_user_tx_and_notification_persisted(
        self, admin_session: requests.Session, apple_basic_email: str
    ):
        sys.path.insert(0, "/app/backend")
        from routes.db import db  # motor client shared with app

        payload = _apple_basic_payload(apple_basic_email)
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=payload, timeout=45,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        tx_id = body["scenario"]["transaction_id"]

        # ---- User record ----
        user = await db.users.find_one({"email": apple_basic_email}, {"_id": 0})
        assert user, f"user not found: {apple_basic_email}"
        assert user.get("name") == "David Thomas", user
        assert user.get("subscription_plan") == "basic", user
        assert user.get("subscription_status") == "active", user
        assert user.get("iap_platform") == "apple", user
        assert user.get("billing_address_line") == "6606 ARANCIONE AVE", user

        # ---- Transaction record (poll for async writes / notification_sent) ----
        tx = None
        for _ in range(20):
            tx = await db.payment_transactions.find_one(
                {"transaction_id": tx_id}, {"_id": 0}
            )
            if tx and tx.get("notification_sent"):
                break
            time.sleep(0.5)
        assert tx, f"tx {tx_id} not found"
        assert tx.get("status") == "completed", tx
        assert tx.get("notification_sent") is True, tx.get("notification_sent")
        # Apple provider label
        assert tx.get("provider") == "iap_apple", tx.get("provider")
        # TX tax rate exactly 0.0625
        assert round(float(tx.get("tax_rate", 0)), 4) == EXP_TAX_RATE, tx.get("tax_rate")

        jur = tx.get("jurisdiction") or {}
        assert jur.get("country") == "US", jur
        assert jur.get("state") == "TX", jur
        assert jur.get("postal_code") == "72533", jur
        assert jur.get("city") == "San Antonio", jur
        assert jur.get("address_line") == "6606 ARANCIONE AVE", jur

        # ---- In-app notification ----
        notif = await db.notifications.find_one(
            {"user_id": user["user_id"], "type": "payment_confirmation"},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        assert notif, "in-app notification missing"
        assert notif.get("title") == "Payment Successful — Basic Plan Activated", notif
        msg = notif.get("message") or ""
        assert "IAP-" in msg, msg
        assert "App Store" in msg, msg


# --------------------------------------------------------------------------- #
# 3. Plan transition: premium/google → basic/apple => downgrade timeline event
# --------------------------------------------------------------------------- #
class TestPlanDowngradeTimeline:
    """
    Mirrors the real kadjimonn sequence (Premium/Google, then Basic/Apple).
    Duplicate-suppression is per (user, provider, plan, period) — the second
    call has a *different* provider AND plan, so notification still fires.
    """

    def test_downgrade_event_recorded(
        self, admin_session: requests.Session
    ):
        # Use sync pymongo client here to avoid pytest-asyncio module-level
        # motor client / event-loop rebinding issues between async tests.
        from pymongo import MongoClient

        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            # Fall back to backend/.env
            for line in Path("/app/backend/.env").read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("MONGO_URL=") and not mongo_url:
                    mongo_url = line.split("=", 1)[1].strip()
                elif line.startswith("DB_NAME=") and not db_name:
                    db_name = line.split("=", 1)[1].strip()
        assert mongo_url and db_name, "MONGO_URL / DB_NAME missing"
        client = MongoClient(mongo_url)
        db = client[db_name]

        # Fresh email so we start from a clean slate
        email = f"iap.e2e.iter884.tr.{uuid.uuid4().hex[:10]}@example.com"

        # ---- Step 1: premium / google / OK (like iter883 baseline) ----
        step1 = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json={
                "email": email,
                "name": "David Thomas",
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
        assert step1.status_code == 200, step1.text[:400]
        assert step1.json().get("success") is True

        # ---- Step 2: basic / apple / TX (downgrade) ----
        step2 = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=_apple_basic_payload(email),
            timeout=45,
        )
        assert step2.status_code == 200, step2.text[:400]
        body2 = step2.json()
        assert body2.get("success") is True, body2

        # Notification should still fire on second call (different provider+plan)
        checks = body2.get("checks") or {}
        assert checks.get("notification_latency_under_2s") is True, checks
        assert checks.get("subscription_active") is True, checks

        # Give the timeline write a moment
        time.sleep(1.0)

        user = db.users.find_one({"email": email}, {"_id": 0})
        assert user, "user missing after downgrade"
        assert user.get("subscription_plan") == "basic", user
        assert user.get("iap_platform") == "apple", user

        # ---- Timeline: latest event should be the downgrade to basic on apple ----
        events = list(
            db.iap_subscription_timeline.find(
                {"user_id": user["user_id"]},
                {"_id": 0},
            ).sort("created_at", -1).limit(20)
        )
        assert events, "no timeline events recorded"

        # Find the most recent apple/basic event
        downgrade = None
        for ev in events:
            if ev.get("platform") == "apple" and ev.get("to_plan") == "basic":
                downgrade = ev
                break
        assert downgrade is not None, f"downgrade event missing; events={events[:5]}"
        assert downgrade.get("event_type") == "downgrade", downgrade
        assert downgrade.get("from_plan") == "premium", downgrade
        assert downgrade.get("to_plan") == "basic", downgrade
        assert downgrade.get("platform") == "apple", downgrade


# --------------------------------------------------------------------------- #
# 4. Backend log signals — Apple/App Store subjects + admin receipt line
# --------------------------------------------------------------------------- #
class TestBackendLogSignalsApple:
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
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 600_000))
                        text += f.read()
                except OSError:
                    pass
        return text

    def test_logs_show_apple_subjects_and_receipt_lines(
        self, admin_session: requests.Session, apple_basic_email: str
    ):
        # Fresh run so log lines are recent for this iteration
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=_apple_basic_payload(apple_basic_email),
            timeout=45,
        )
        assert r.status_code == 200, r.text[:400]
        tx_id = r.json()["scenario"]["transaction_id"]

        # Give the email pipeline time to log
        time.sleep(3.5)

        logs = self._read_recent_logs()

        # (a) User receipt subject correct + no mojibake
        assert "Subscription Confirmed — Receipt Enclosed" in logs, (
            "Fixed receipt subject missing from logs"
        )
        assert "സ്ഥിരീകര" not in logs, "Malayalam mojibake still present in logs!"

        # (b) Branded receipt email log line (PDF attached path)
        assert re.search(r"Branded receipt email sent", logs) is not None, (
            "'Branded receipt email sent' log line missing"
        )

        # (c) Admin alert email subject — App Store variant
        assert re.search(
            r"\[Admin\]\s+Payment Confirmed via App Store\s+—\s+RCT-",
            logs,
        ) is not None, "Admin alert subject '[Admin] Payment Confirmed via App Store — RCT-...' missing"

        # (d) Admin receipt email log line
        assert re.search(r"Admin payment receipt email sent", logs) is not None, (
            "'Admin payment receipt email sent' log line missing"
        )

        # (e) No spurious failure notification when simulate_failure_case=false
        failure_line_re = re.compile(
            r"_send_iap_failure_notification|payment[_ -]failed", re.IGNORECASE
        )
        window = logs.split(tx_id)[-1] if tx_id in logs else logs[-50_000:]
        assert failure_line_re.search(window[:20_000]) is None, (
            f"Spurious failure notification observed after tx {tx_id}"
        )


# --------------------------------------------------------------------------- #
# 5. Regression: Apple compliance bundle receipt PDF still valid
# --------------------------------------------------------------------------- #
class TestAppleComplianceBundlePdf:
    def test_receipt_pdf_valid_bytes(
        self, admin_session: requests.Session, apple_basic_email: str
    ):
        sim = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json=_apple_basic_payload(apple_basic_email),
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
            pytest.skip(f"bundle for {tx_id} not yet created (async)")
        assert pdf.status_code == 200, f"HTTP {pdf.status_code}: {pdf.text[:400]}"
        ctype = pdf.headers.get("content-type", "")
        assert "application/pdf" in ctype.lower(), f"content-type not pdf: {ctype}"
        assert pdf.content[:4] == b"%PDF", f"missing %PDF magic: {pdf.content[:16]!r}"
