"""
Iteration 885 — Stripe/Premium/Yearly/TX production-e2e simulator.

Target endpoint:
    POST /api/admin/payments/simulate-stripe-production-e2e

Scenario mirrors TOM GOLDAM (5873 RANDOLPH AVE, Dallas, TX 72533) — but uses
FRESH test emails (stripe.e2e.iter885.<uuid>@example.com). NEVER emails
hypoduchrist@gmail.com or kadjimonn@gmail.com.

Pricing target (premium yearly, TX):
    base 153.50 + processing_fee 5.03 (Stripe 2.9% + $0.30 on gross 163.09)
    + taxes 9.59 (6.25% TX)  = final_total 168.12   (tax_rate 0.0625)

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
SIM_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-stripe-production-e2e"

# ---- Expected pricing (Stripe / Premium yearly / TX) ----
EXP_BASE = 153.50
EXP_FEE = 5.03
EXP_TAX = 9.59
EXP_TOTAL = 168.12
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
def fresh_email() -> str:
    return f"stripe.e2e.iter885.{uuid.uuid4().hex[:10]}@example.com"


def _tom_payload(email: str, *, plan: str = "premium", period: str = "yearly",
                 simulate_failure_case: bool = False) -> dict:
    return {
        "email": email,
        "name": "TOM GOLDAM",
        "address_line": "5873 RANDOLPH AVE",
        "plan": plan,
        "period": period,
        "city": "Dallas",
        "state_code": "TX",
        "country_code": "US",
        "postal_code": "72533",
        "simulate_failure_case": simulate_failure_case,
    }


# --------------------------------------------------------------------------- #
# 1. Auth / CSRF gating
# --------------------------------------------------------------------------- #
class TestEndpointAuthGating:
    def test_anonymous_forbidden(self, fresh_email):
        anon = requests.Session()
        anon.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        r = anon.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=30)
        assert r.status_code in (401, 403), f"unexpected: {r.status_code} {r.text[:300]}"

    def test_non_admin_forbidden(self, fresh_email):
        # Use a known free/non-admin user
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
        r = s.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=30)
        assert r.status_code == 403, f"non-admin should be 403; got {r.status_code}: {r.text[:300]}"


# --------------------------------------------------------------------------- #
# 2. Happy path — endpoint contract + checks + pricing
# --------------------------------------------------------------------------- #
class TestStripePremiumYearlyPrimary:
    def test_success_all_checks_true(self, admin_session, fresh_email, request):
        r = admin_session.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=45)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:600]}"
        body = r.json()
        assert body.get("success") is True, body

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"check {k} not true: {checks}"

        assert body.get("failure_case") is None, body.get("failure_case")

        request.session._iter885_body = body
        request.session._iter885_email = fresh_email
        request.session._iter885_tx_id = body["scenario"]["transaction_id"]
        request.session._iter885_ticket = body["ticket_id"]

    def test_pricing_breakdown(self, admin_session, request):
        body = getattr(request.session, "_iter885_body", None)
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
        body = getattr(request.session, "_iter885_body", None)
        if not body:
            pytest.skip("primary didn't run")
        sc = body.get("scenario") or {}
        assert sc.get("platform") == "stripe", sc
        assert sc.get("plan") == "premium", sc
        assert sc.get("period") == "yearly", sc
        assert str(sc.get("transaction_id", "")).startswith("sim_stripe_"), sc
        assert str(body.get("ticket_id", "")).startswith("STR-"), body.get("ticket_id")

    def test_subscription_update_shape(self, admin_session, request):
        body = getattr(request.session, "_iter885_body", None)
        if not body:
            pytest.skip("primary didn't run")
        su = body.get("subscription_update") or {}
        assert su.get("subscription_plan") == "premium", su
        assert su.get("subscription_status") == "active", su
        assert isinstance(su.get("subscription_end_date"), str), su


# --------------------------------------------------------------------------- #
# 3. DB side effects — user / tx / notification / payments / ledger / audit
# --------------------------------------------------------------------------- #
class TestStripeDbSideEffects:
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
        # Strip quotes if inherited from os.environ (some loaders keep them)
        mongo_url = mongo_url.strip().strip('"').strip("'")
        db_name = db_name.strip().strip('"').strip("'")
        return MongoClient(mongo_url)[db_name]

    def test_all_db_records(self, admin_session, fresh_email):
        db = self._mongo()
        r = admin_session.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=45)
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
        assert tx.get("provider") == "stripe", tx.get("provider")
        assert tx.get("status") == "completed", tx.get("status")
        assert tx.get("environment") == "production_simulated", tx.get("environment")
        assert tx.get("notification_sent") is True, "notification_sent should flip true"
        assert round(float(tx.get("tax_rate", 0)), 4) == EXP_TAX_RATE, tx.get("tax_rate")

        jur = tx.get("jurisdiction") or {}
        assert jur.get("country") == "US", jur
        assert jur.get("state") == "TX", jur
        assert jur.get("postal_code") == "72533", jur
        assert jur.get("city") == "Dallas", jur
        assert jur.get("address_line") == "5873 RANDOLPH AVE", jur

        # User record
        user = db.users.find_one({"email": fresh_email}, {"_id": 0})
        assert user, "user missing"
        assert user.get("name") == "TOM GOLDAM", user
        assert user.get("subscription_plan") == "premium", user
        assert user.get("subscription_status") == "active", user
        assert user.get("payment_verified") is True, user
        assert user.get("last_payment_id") == tx_id, user
        assert user.get("billing_address_line") == "5873 RANDOLPH AVE", user
        # subscription_end_date roughly 1 year out
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

        # financial_ledger_entries provider_webhook_confirmed entry
        ledger = db.financial_ledger_entries.find_one(
            {"transaction_id": tx_id, "event_type": "provider_webhook_confirmed"}, {"_id": 0}
        )
        assert ledger, f"financial_ledger_entries provider_webhook_confirmed missing for {tx_id}"
        assert ledger.get("provider") == "stripe", ledger

        # In-app notification
        notif = db.notifications.find_one(
            {"user_id": user["user_id"], "type": "payment_confirmation",
             "metadata.ticket_id": ticket_id},
            {"_id": 0},
        )
        assert notif, "in-app payment_confirmation notification missing"
        msg = notif.get("message") or ""
        assert "168.12" in msg, f"$168.12 not in notif message: {msg}"
        assert "Stripe" in msg or "stripe" in msg.lower(), f"'Stripe' not in msg: {msg}"


# --------------------------------------------------------------------------- #
# 4. Validation — invalid period / invalid plan
# --------------------------------------------------------------------------- #
class TestStripeValidation:
    def test_invalid_period_returns_400(self, admin_session, fresh_email):
        payload = _tom_payload(fresh_email, period="weekly")
        r = admin_session.post(SIM_ENDPOINT, json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:300]}"

    def test_invalid_plan_returns_404(self, admin_session, fresh_email):
        payload = _tom_payload(fresh_email, plan="platinum")
        r = admin_session.post(SIM_ENDPOINT, json=payload, timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:300]}"


# --------------------------------------------------------------------------- #
# 5. Existing-user re-run: second call keeps user and re-notifies
# --------------------------------------------------------------------------- #
class TestExistingUserRerun:
    def test_second_run_succeeds_and_notifies(self, admin_session, fresh_email):
        r1 = admin_session.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=45)
        assert r1.status_code == 200, r1.text[:400]
        assert r1.json().get("success") is True

        r2 = admin_session.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=45)
        assert r2.status_code == 200, r2.text[:400]
        body2 = r2.json()
        assert body2.get("success") is True, body2
        checks = body2.get("checks") or {}
        # Because each invocation has a new session_id, notification should still fire
        assert checks.get("notification_latency_under_2s") is True, checks
        assert checks.get("subscription_active") is True, checks

        # Distinct tx ids
        assert r1.json()["scenario"]["transaction_id"] != body2["scenario"]["transaction_id"]


# --------------------------------------------------------------------------- #
# 6. Backend log signals — Stripe subjects + admin receipt lines
# --------------------------------------------------------------------------- #
class TestBackendLogSignalsStripe:
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

    def test_logs_show_stripe_subjects(self, admin_session, fresh_email):
        r = admin_session.post(SIM_ENDPOINT, json=_tom_payload(fresh_email), timeout=45)
        assert r.status_code == 200, r.text[:400]
        tx_id = r.json()["scenario"]["transaction_id"]
        # Give email pipeline time to log
        time.sleep(4.0)
        logs = self._read_recent_logs()

        # (a) User receipt subject — either the problem-statement variant or the
        #     fixed 'Subscription Confirmed — Receipt Enclosed' variant used by
        #     the unified pipeline. Accept both.
        has_user_subject = (
            ("Payment Receipt - Premium Plan" in logs) or
            ("Subscription Confirmed — Receipt Enclosed" in logs)
        )
        assert has_user_subject, "User receipt subject line missing from logs"

        # (b) Branded receipt email log line
        assert re.search(r"Branded receipt email sent", logs) is not None, (
            "'Branded receipt email sent' log line missing"
        )

        # (c) Admin alert subject — Stripe / Card variant
        assert re.search(
            r"\[Admin\]\s+Payment Confirmed via Card \(Stripe\)\s+—\s+RCT-",
            logs,
        ) is not None, "Admin '[Admin] Payment Confirmed via Card (Stripe) — RCT-...' subject missing"

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
# 7. Regression — existing Stripe endpoints unaffected
# --------------------------------------------------------------------------- #
class TestStripeRegression:
    def test_checkout_status_fake_id_returns_404_or_500(self, admin_session):
        # Endpoint requires auth (401 for anonymous, before it reaches Stripe lookup).
        # With admin auth: expect 404 or 500 for a non-existent session id — NOT
        # a 500 from an import error.
        r = admin_session.get(
            f"{BASE_URL}/api/subscriptions/checkout-status/cs_test_fake_id_iter885_{uuid.uuid4().hex[:8]}",
            timeout=30,
        )
        assert r.status_code in (404, 500), f"unexpected {r.status_code}: {r.text[:400]}"
        # Must NOT be 500 due to ImportError (would surface as 'name is not defined' text)
        body_txt = r.text[:1000].lower()
        assert "importerror" not in body_txt, "ImportError leaking through checkout-status"
        assert "not defined" not in body_txt, "NameError leaking through checkout-status"

    def test_webhook_bad_signature_returns_400(self):
        r = requests.post(
            f"{BASE_URL}/api/webhook/stripe",
            data=b'{"foo":"bar"}',
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": "t=0,v1=deadbeef",
            },
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:400]}"


# --------------------------------------------------------------------------- #
# 8. Cross-module regression — IAP simulator still works
# --------------------------------------------------------------------------- #
class TestIapCrossModuleRegression:
    def test_iap_google_basic_still_works(self, admin_session):
        email = f"stripe.e2e.iter885.iapx.{uuid.uuid4().hex[:8]}@example.com"
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
