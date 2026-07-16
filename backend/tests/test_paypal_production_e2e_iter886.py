"""
Iteration 886 — PayPal / Basic / Yearly / KY production-e2e simulator.

Target endpoint:
    POST /api/admin/payments/simulate-paypal-production-e2e

Scenario mirrors MR. WALTER W. WITHERSPOON JR. MDM ENTERPRISES, INC.
(1401 S. MAIN ST., Plummers Landing, KY 41081-1411) — but uses
FRESH test emails (paypal.e2e.iter886.<uuid>@example.com). NEVER emails
realaicoach@gmail.com, hypoduchrist@gmail.com, or kadjimonn@gmail.com.

Pricing target (basic yearly, KY):
    base 57.50 + processing_fee 2.62 (PayPal 3.49% + $0.49 on gross 60.95)
    + taxes 3.45 (KY 6%)  = final_total 63.57   (tax_rate 0.06)

Also spot-runs the iter885 Stripe suite parity checks + one IAP regression.
Admin creds: admin@realaicoach.app / NewAdminPass2026!
"""
from __future__ import annotations

import os
import re
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
PP_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-paypal-production-e2e"
ST_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-stripe-production-e2e"

# ---- Expected pricing (PayPal / Basic / yearly / KY) ----
EXP_BASE = 57.50
EXP_FEE = 2.62
EXP_TAX = 3.45
EXP_TOTAL = 63.57
EXP_TAX_RATE = 0.06

WITHERSPOON_NAME = "MR. WALTER W. WITHERSPOON JR. MDM ENTERPRISES, INC."


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
def fresh_email() -> str:
    return f"paypal.e2e.iter886.{uuid.uuid4().hex[:10]}@example.com"


def _witherspoon_payload(email: str, *, plan: str = "basic", period: str = "yearly",
                         simulate_failure_case: bool = False) -> dict:
    return {
        "email": email,
        "name": WITHERSPOON_NAME,
        "address_line": "1401 S. MAIN ST.",
        "plan": plan,
        "period": period,
        "city": "Plummers Landing",
        "state_code": "KY",
        "country_code": "US",
        "postal_code": "41081-1411",
        "simulate_failure_case": simulate_failure_case,
    }


# --------------------------------------------------------------------------- #
# 1. Auth / CSRF gating
# --------------------------------------------------------------------------- #
class TestPayPalEndpointAuthGating:
    def test_anonymous_forbidden(self, fresh_email):
        anon = requests.Session()
        anon.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        r = anon.post(PP_ENDPOINT, json=_witherspoon_payload(fresh_email), timeout=30)
        assert r.status_code in (401, 403), f"unexpected: {r.status_code} {r.text[:300]}"

    def test_non_admin_forbidden(self, fresh_email):
        s = requests.Session()
        s.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        login = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
            timeout=30,
        )
        if login.status_code != 200:
            pytest.skip(f"non-admin login unavailable: {login.status_code}")
        r = s.post(PP_ENDPOINT, json=_witherspoon_payload(fresh_email), timeout=30)
        assert r.status_code == 403, f"non-admin should be 403; got {r.status_code}: {r.text[:300]}"


# --------------------------------------------------------------------------- #
# 2. Happy path — endpoint contract + checks + pricing
# --------------------------------------------------------------------------- #
class TestPayPalBasicYearlyPrimary:
    def test_success_all_checks_true(self, admin_session, fresh_email, request):
        r = admin_session.post(PP_ENDPOINT, json=_witherspoon_payload(fresh_email), timeout=45)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:600]}"
        body = r.json()
        assert body.get("success") is True, body

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"check {k} not true: {checks}"

        assert body.get("failure_case") is None, body.get("failure_case")

        request.session._iter886_body = body
        request.session._iter886_email = fresh_email

    def test_pricing_breakdown(self, admin_session, request):
        body = getattr(request.session, "_iter886_body", None)
        if not body:
            pytest.skip("primary didn't run")
        pb = body.get("pricing_breakdown") or {}
        assert round(float(pb.get("base_plan_price", 0)), 2) == EXP_BASE, pb
        assert round(float(pb.get("processing_fee", 0)), 2) == EXP_FEE, pb
        assert round(float(pb.get("taxes", 0)), 2) == EXP_TAX, pb
        assert round(float(pb.get("final_total", 0)), 2) == EXP_TOTAL, pb
        assert round(float(pb.get("tax_rate", 0)), 4) == EXP_TAX_RATE, pb
        assert pb.get("currency") == "USD", pb

    def test_scenario_platform_and_ticket(self, admin_session, request):
        body = getattr(request.session, "_iter886_body", None)
        if not body:
            pytest.skip("primary didn't run")
        sc = body.get("scenario") or {}
        assert sc.get("platform") == "paypal", sc
        assert sc.get("plan") == "basic", sc
        assert sc.get("period") == "yearly", sc
        assert str(sc.get("transaction_id", "")).startswith("sim_paypal_"), sc
        assert str(body.get("ticket_id", "")).startswith("PP-"), body.get("ticket_id")

    def test_subscription_update_shape(self, admin_session, request):
        body = getattr(request.session, "_iter886_body", None)
        if not body:
            pytest.skip("primary didn't run")
        su = body.get("subscription_update") or {}
        assert su.get("subscription_plan") == "basic", su
        assert su.get("subscription_status") == "active", su
        assert isinstance(su.get("subscription_end_date"), str), su


# --------------------------------------------------------------------------- #
# 3. DB side effects — user / tx / notification / payments / ledger / audit
# --------------------------------------------------------------------------- #
class TestPayPalDbSideEffects:
    def _mongo(self):
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            for line in Path("/app/backend/.env").read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("MONGO_URL=") and not mongo_url:
                    mongo_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("DB_NAME=") and not db_name:
                    db_name = line.split("=", 1)[1].strip().strip('"').strip("'")
        assert mongo_url and db_name, "MONGO_URL / DB_NAME missing"
        mongo_url = mongo_url.strip().strip('"').strip("'")
        db_name = db_name.strip().strip('"').strip("'")
        return MongoClient(mongo_url)[db_name]

    def test_all_db_records(self, admin_session, fresh_email):
        db = self._mongo()
        r = admin_session.post(PP_ENDPOINT, json=_witherspoon_payload(fresh_email), timeout=45)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        tx_id = body["scenario"]["transaction_id"]
        ticket_id = body["ticket_id"]

        # Wait for async notification pipeline
        deadline = time.time() + 12
        tx = None
        while time.time() < deadline:
            tx = db.payment_transactions.find_one({"transaction_id": tx_id}, {"_id": 0})
            if tx and tx.get("notification_sent"):
                break
            time.sleep(0.5)
        assert tx, f"tx {tx_id} not found"
        assert tx.get("provider") == "paypal", tx.get("provider")
        assert tx.get("payment_method") == "paypal_js", tx.get("payment_method")
        assert tx.get("status") == "completed", tx.get("status")
        assert tx.get("environment") == "production_simulated", tx.get("environment")
        assert tx.get("notification_sent") is True, "notification_sent should flip true"
        assert round(float(tx.get("tax_rate", 0)), 4) == EXP_TAX_RATE, tx.get("tax_rate")

        jur = tx.get("jurisdiction") or {}
        assert jur.get("country") == "US", jur
        assert jur.get("state") == "KY", jur
        assert jur.get("postal_code") == "41081-1411", jur
        assert jur.get("city") == "Plummers Landing", jur
        assert jur.get("address_line") == "1401 S. MAIN ST.", jur

        # User record — name stored VERBATIM
        user = db.users.find_one({"email": fresh_email}, {"_id": 0})
        assert user, "user missing"
        assert user.get("name") == WITHERSPOON_NAME, f"name not verbatim: {user.get('name')}"
        assert user.get("subscription_plan") == "basic", user
        assert user.get("subscription_status") == "active", user
        assert user.get("payment_verified") is True, user
        assert user.get("last_payment_id") == tx_id, user
        assert user.get("billing_address_line") == "1401 S. MAIN ST.", user
        assert user.get("last_payment_method") == "paypal_js", user
        end = user.get("subscription_end_date")
        assert end is not None, "subscription_end_date missing"

        # payments record with payment_id == tx_id
        payment = db.payments.find_one({"payment_id": tx_id}, {"_id": 0})
        assert payment, f"payments row missing for {tx_id}"

        # subscription_audit_log
        audit = db.subscription_audit_log.find_one(
            {"session_id": tx_id, "action": "simulated_production_activation"}, {"_id": 0}
        )
        assert audit, "simulated_production_activation audit entry missing"

        # financial_ledger_entries provider_capture_completed entry
        ledger = db.financial_ledger_entries.find_one(
            {"transaction_id": tx_id, "event_type": "provider_capture_completed"}, {"_id": 0}
        )
        assert ledger, f"financial_ledger_entries provider_capture_completed missing for {tx_id}"
        assert ledger.get("provider") == "paypal", ledger

        # In-app notification
        notif = db.notifications.find_one(
            {"user_id": user["user_id"], "type": "payment_confirmation",
             "metadata.ticket_id": ticket_id},
            {"_id": 0},
        )
        assert notif, "in-app payment_confirmation notification missing"
        msg = notif.get("message") or ""
        assert "63.57" in msg, f"$63.57 not in notif message: {msg}"
        assert "PayPal" in msg or "paypal" in msg.lower(), f"'PayPal' not in msg: {msg}"


# --------------------------------------------------------------------------- #
# 4. Validation — invalid period / invalid plan
# --------------------------------------------------------------------------- #
class TestPayPalValidation:
    def test_invalid_period_returns_400(self, admin_session, fresh_email):
        payload = _witherspoon_payload(fresh_email, period="weekly")
        r = admin_session.post(PP_ENDPOINT, json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:300]}"

    def test_invalid_plan_returns_404(self, admin_session, fresh_email):
        payload = _witherspoon_payload(fresh_email, plan="platinum")
        r = admin_session.post(PP_ENDPOINT, json=payload, timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:300]}"


# --------------------------------------------------------------------------- #
# 5. Backend log signals — PayPal subjects + admin receipt lines
# --------------------------------------------------------------------------- #
class TestBackendLogSignalsPayPal:
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

    def test_logs_show_paypal_subjects(self, admin_session, fresh_email):
        r = admin_session.post(PP_ENDPOINT, json=_witherspoon_payload(fresh_email), timeout=45)
        assert r.status_code == 200, r.text[:400]
        tx_id = r.json()["scenario"]["transaction_id"]
        time.sleep(4.0)
        logs = self._read_recent_logs()

        # (a) User receipt subject — accept either problem-statement variant or
        #     the unified pipeline variant.
        has_user_subject = (
            ("Payment Receipt - Basic Plan" in logs) or
            ("Subscription Confirmed — Receipt Enclosed" in logs)
        )
        assert has_user_subject, "User receipt subject line missing from logs"

        # (b) Branded receipt email log line
        assert re.search(r"Branded receipt email sent", logs) is not None, (
            "'Branded receipt email sent' log line missing"
        )

        # (c) Admin alert subject — PayPal variant
        assert re.search(
            r"\[Admin\]\s+Payment Confirmed via PayPal\s+—\s+RCT-",
            logs,
        ) is not None, "Admin '[Admin] Payment Confirmed via PayPal — RCT-...' subject missing"

        # (d) Admin receipt email log line
        assert re.search(r"Admin payment receipt email sent", logs) is not None, (
            "'Admin payment receipt email sent' log line missing"
        )

        # (e) No spurious failure notification for this happy-path tx
        window = logs.split(tx_id)[-1] if tx_id in logs else logs[-50_000:]
        failure_re = re.compile(r"payment[_ -]failed", re.IGNORECASE)
        assert failure_re.search(window[:20_000]) is None, (
            f"Spurious failure line near tx {tx_id}"
        )


# --------------------------------------------------------------------------- #
# 6. REFACTOR REGRESSION — Stripe endpoint still works identically
# --------------------------------------------------------------------------- #
class TestStripeRegressionPostRefactor:
    """Spot check that Stripe simulator delegated-to-core still matches iter885 contract."""

    def _tom(self, email: str) -> dict:
        return {
            "email": email,
            "name": "TOM GOLDAM",
            "address_line": "5873 RANDOLPH AVE",
            "plan": "premium",
            "period": "yearly",
            "city": "Dallas",
            "state_code": "TX",
            "country_code": "US",
            "postal_code": "72533",
            "simulate_failure_case": False,
        }

    def test_stripe_premium_yearly_tx_unchanged(self, admin_session):
        email = f"paypal.e2e.iter886.stripe_reg.{uuid.uuid4().hex[:10]}@example.com"
        r = admin_session.post(ST_ENDPOINT, json=self._tom(email), timeout=45)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body
        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"stripe regression check {k}: {checks}"

        pb = body.get("pricing_breakdown") or {}
        assert round(float(pb.get("base_plan_price", 0)), 2) == 153.50, pb
        assert round(float(pb.get("processing_fee", 0)), 2) == 5.03, pb
        assert round(float(pb.get("taxes", 0)), 2) == 9.59, pb
        assert round(float(pb.get("final_total", 0)), 2) == 168.12, pb
        assert round(float(pb.get("tax_rate", 0)), 4) == 0.0625, pb

        sc = body.get("scenario") or {}
        assert sc.get("platform") == "stripe", sc
        assert str(sc.get("transaction_id", "")).startswith("sim_stripe_"), sc
        assert str(body.get("ticket_id", "")).startswith("STR-"), body.get("ticket_id")


# --------------------------------------------------------------------------- #
# 7. Cross-module regression — IAP simulator still works
# --------------------------------------------------------------------------- #
class TestIapCrossModuleRegression:
    def test_iap_google_basic_still_works(self, admin_session):
        email = f"paypal.e2e.iter886.iapx.{uuid.uuid4().hex[:8]}@example.com"
        r = admin_session.post(
            f"{BASE_URL}/api/iap/admin/simulate-production-e2e",
            json={
                "email": email,
                "name": "IAP Regression User",
                "address_line": "1 Regression Way",
                "plan": "basic",
                "period": "monthly",
                "platform": "google",
                "city": "Altus",
                "state_code": "OK",
                "country_code": "US",
                "postal_code": "73521",
                "simulate_failure_case": False,
            },
            timeout=45,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body
        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"IAP regression check {k} failed: {checks}"
