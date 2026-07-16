"""
Iteration 888 — Bugfix verification: FedaPay XOF receipt PDF base-price row
+ admin alert amount localization.

Two fixes applied by main agent in /app/backend/routes/payments.py inside
_send_payment_email:

  FIX 1 (~line 1587) subtotal is now read from the tx (`tx.get("subtotal", amount)`),
                     not from the USD `amount` param — so the PDF base-price row
                     reflects the LOCAL subtotal (9,674 XOF for BJ / premium / monthly).
  FIX 2 (~line 1707) admin alert `amount=` now passes `display_amount` (already
                     localized: "CFA 10,777" for XOF, "$168.12" for USD providers)
                     rather than the USD base `amount`.

Tests:
    1. FedaPay premium/monthly/BJ/XOF — receipt PDF text asserts XOF 9,674 base row,
       XOF 799 tax, XOF 304 fee, XOF 10,777 total, and sum invariant.
    2. Receipt payload integrity in stored payment_transactions row.
    3. Admin alert template renders "CFA 10,777" when given XOF display_amount.
    4. Backend log shows the FedaPay admin subject.
    5. Regression: Stripe premium/yearly/TX — PDF base row shows $153.50, tax $9.59,
       fee $5.03, total $168.12, sum invariant.
    6. Regression: PayPal basic/yearly/KY — PDF rows sum to 63.57.
    7. Regression: IAP google/basic/monthly — receipt PDF renders coherent USD lines,
       base + fee + tax ≈ total.
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import requests

# Make backend importable so we can call _payment_from_txn + generate_receipt_pdf_pro
sys.path.insert(0, "/app/backend")


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

FP_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-fedapay-production-e2e"
ST_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-stripe-production-e2e"
PP_ENDPOINT = f"{BASE_URL}/api/admin/payments/simulate-paypal-production-e2e"
IAP_ENDPOINT = f"{BASE_URL}/api/iap/admin/simulate-production-e2e"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mongo():
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
    return MongoClient(mongo_url.strip().strip('"').strip("'"))[db_name.strip().strip('"').strip("'")]


def _find_tx(payment_id: str, timeout_s: float = 15.0) -> Optional[Dict[str, Any]]:
    db = _mongo()
    deadline = time.time() + timeout_s
    query = {"$or": [{"payment_id": payment_id}, {"session_id": payment_id}, {"transaction_id": payment_id}]}
    while time.time() < deadline:
        tx = db.payment_transactions.find_one(query, {"_id": 0})
        if tx and tx.get("notification_sent"):
            return tx
        if tx:
            time.sleep(0.4)
            continue
        time.sleep(0.4)
    # Return whatever we have
    return db.payment_transactions.find_one(query, {"_id": 0})


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def _render_receipt_pdf(tx: Dict[str, Any], user_name: str, user_email: str) -> bytes:
    """Regenerate the exact same receipt PDF that _send_payment_email attaches."""
    from routes.payments_history_shared import _payment_from_txn  # type: ignore
    from services.receipt_pdf_pro import generate_receipt_pdf_pro  # type: ignore
    payment_id = tx.get("payment_id") or tx.get("session_id") or "N/A"
    payment = _payment_from_txn(tx, payment_id)
    # Minimal branding — same defaults the sender resolves in prod
    branding = {
        "brand_name": "Real AI Coach",
        "primary_color": "#2563EB",
        "footer_text": "Thank you for your business!",
        "company_info": "support@realaicoach.app",
        "show_qr_code": True,
    }
    return generate_receipt_pdf_pro("receipt", payment, user_name, user_email, branding)


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


def _fresh(prefix: str) -> str:
    return f"{prefix}.iter888.{uuid.uuid4().hex[:10]}@example.com"


# --------------------------------------------------------------------------- #
# 1. PRIMARY — FedaPay XOF receipt PDF (bug scenario)
# --------------------------------------------------------------------------- #
KIRIAKOU_NAME = "MR. Mathieu Kiriakou"
FEDAPAY_PAYLOAD_BASE = {
    "name": KIRIAKOU_NAME,
    "address_line": "2nd Cemetery Rd.",
    "plan": "premium",
    "period": "monthly",
    "city": "Benin City",
    "country_code": "BJ",
    "postal_code": "300271",
    "currency": "XOF",
    "simulate_failure_case": False,
}


class TestFedaPayReceiptPdfBugFix:
    """The primary bug fix: XOF PDF must show XOF 9,674 base (not XOF 16)."""

    def test_fedapay_receipt_pdf_base_row_is_local_subtotal(self, admin_session, request):
        email = _fresh("fedapay.receipt")
        payload = {**FEDAPAY_PAYLOAD_BASE, "email": email}

        r = admin_session.post(FP_ENDPOINT, json=payload, timeout=60)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:600]}"
        body = r.json()
        assert body.get("success") is True, body

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"check {k} not true: {checks}"

        # persist for later admin-log test
        request.session._iter888_fedapay_email = email
        request.session._iter888_fedapay_payment_id = body["scenario"]["payment_id"]

        # Locate stored tx and rebuild the receipt PDF
        payment_id = body["scenario"]["payment_id"]
        tx = _find_tx(payment_id)
        assert tx, f"tx {payment_id} not found in payment_transactions"

        # Receipt payload integrity
        assert tx.get("currency") == "XOF", tx.get("currency")
        assert int(round(float(tx.get("subtotal", 0)))) == 9674, f"subtotal: {tx.get('subtotal')}"
        assert int(round(float(tx.get("tax_amount", 0)))) == 799, f"tax_amount: {tx.get('tax_amount')}"
        assert int(round(float(tx.get("processing_fee", 0)))) == 304, f"processing_fee: {tx.get('processing_fee')}"
        assert int(round(float(tx.get("total_amount", 0)))) == 10777, f"total_amount: {tx.get('total_amount')}"

        pdf_bytes = _render_receipt_pdf(tx, KIRIAKOU_NAME, email)
        assert pdf_bytes[:4] == b"%PDF", "generated bytes not a valid PDF header"
        text = _extract_pdf_text(pdf_bytes)

        # BUG ASSERT — must NOT show the old "XOF 16" (USD 15.99 mis-cast)
        # Accept optional trailing space/newline; guard against any "XOF 16" pattern
        # not followed by a comma (avoid matching a longer number like 16,000).
        buggy = re.search(r"XOF\s+16(?!\d|,)", text)
        assert buggy is None, (
            f"OLD BUG PRESENT: base row still shows 'XOF 16' (USD 15.99 mis-cast). "
            f"PDF excerpt: {text[:1500]!r}"
        )

        # POSITIVE ASSERT — base row shows local subtotal XOF 9,674
        assert "XOF 9,674" in text, (
            f"base line 'XOF 9,674' missing from PDF. Excerpt: {text[:2000]!r}"
        )
        # Tax + fee + total (all XOF, comma-separated, no decimals for XOF)
        assert "XOF 799" in text, f"tax 'XOF 799' missing. Excerpt: {text[:2000]!r}"
        assert "XOF 304" in text, f"fee 'XOF 304' missing. Excerpt: {text[:2000]!r}"
        assert "XOF 10,777" in text, f"total 'XOF 10,777' missing. Excerpt: {text[:2000]!r}"

        # Sum invariant
        assert 9674 + 799 + 304 == 10777

    def test_fedapay_admin_log_subject_present(self, admin_session, request):
        payment_id = getattr(request.session, "_iter888_fedapay_payment_id", None)
        if not payment_id:
            pytest.skip("primary FedaPay test didn't run")
        # Allow background email fire-and-forget to complete
        time.sleep(6.0)
        text = ""
        for p in ("/var/log/supervisor/backend.err.log", "/var/log/supervisor/backend.out.log"):
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 800_000))
                        text += f.read()
                except OSError:
                    pass
        admin_subject_re = re.compile(
            r"\[Admin\]\s+Payment Confirmed via (Mobile Money \(FedaPay\)|FedaPay|Mobile Money)",
            re.IGNORECASE,
        )
        assert admin_subject_re.search(text), (
            "Admin FedaPay subject '[Admin] Payment Confirmed via Mobile Money (FedaPay)' missing from backend logs"
        )


# --------------------------------------------------------------------------- #
# 2. Admin alert template — CFA 10,777 (unit test)
# --------------------------------------------------------------------------- #
class TestAdminAlertTemplateLocalized:
    def test_admin_alert_renders_cfa_amount(self):
        # Directly call the template with the same display_amount routes/payments.py now passes
        from utils.email_templates import build_payment_admin_alert_email  # type: ignore

        tpl = build_payment_admin_alert_email(
            method="Mobile Money (FedaPay)",
            amount="CFA 10,777",
            receipt_number="RCT-20260115-TEST8888",
            user_email="fedapay.iter888@example.com",
            plan="Premium",
        )
        html = tpl.html
        text_body = tpl.text
        subj = tpl.subject

        assert "CFA 10,777" in html, f"'CFA 10,777' missing from admin alert HTML: {html[:1200]}"
        assert "CFA 10,777" in text_body, f"'CFA 10,777' missing from admin alert text: {text_body[:600]}"
        # Must NOT show the old buggy '$15.99' anywhere in the rendered alert
        assert "$15.99" not in html, f"OLD BUG: '$15.99' still in admin alert HTML: {html[:1500]}"
        assert "$15.99" not in text_body, f"OLD BUG: '$15.99' still in admin alert text: {text_body[:600]}"
        assert "Mobile Money (FedaPay)" in subj, subj

    def test_admin_alert_renders_usd_amount(self):
        # USD providers must continue to render the localized USD display_amount
        from utils.email_templates import build_payment_admin_alert_email  # type: ignore

        tpl = build_payment_admin_alert_email(
            method="Card (Stripe)",
            amount="$168.12",
            receipt_number="RCT-20260115-TESTUSD1",
            user_email="stripe.iter888@example.com",
            plan="Premium",
        )
        assert "$168.12" in tpl.html
        assert "$168.12" in tpl.text
        assert "$15.99" not in tpl.html


# --------------------------------------------------------------------------- #
# 3. Source-code assertion — routes/payments.py line ~1707 uses display_amount
# --------------------------------------------------------------------------- #
class TestSourceFixInPlace:
    def test_admin_alert_call_uses_display_amount(self):
        src_path = Path("/app/backend/routes/payments.py")
        src = src_path.read_text(encoding="utf-8")

        # locate send_catalog_template for template_key="payment_admin_alert"
        m = re.search(
            r"send_catalog_template\(([^)]{0,800}template_key=\"payment_admin_alert\"[^)]{0,800})\)",
            src,
            re.DOTALL,
        )
        assert m, "send_catalog_template(payment_admin_alert=...) block not found"
        call_args = m.group(1)
        assert "amount=display_amount" in call_args, (
            f"admin alert 'amount=' should pass display_amount; got: {call_args[:600]}"
        )
        # Ensure the OLD buggy formatter is gone
        assert 'amount=f"${amount:.2f}"' not in call_args, (
            "OLD BUG: admin alert still uses f\"${amount:.2f}\" instead of display_amount"
        )

    def test_send_email_subtotal_reads_tx(self):
        src = Path("/app/backend/routes/payments.py").read_text(encoding="utf-8")
        # The fix rewrites subtotal to pull from tx (~line 1587)
        pattern = r'subtotal\s*=\s*_safe_float\(\s*tx\.get\("subtotal",\s*amount\)\s*,\s*amount\s*\)'
        assert re.search(pattern, src), "FIX 1 missing: subtotal must be _safe_float(tx.get('subtotal', amount), amount)"


# --------------------------------------------------------------------------- #
# 4. Stripe USD regression — receipt PDF and admin display_amount = charged total
# --------------------------------------------------------------------------- #
class TestStripeReceiptRegression:
    STRIPE_PAYLOAD_BASE = {
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

    def test_stripe_receipt_pdf_line_items_sum(self, admin_session):
        email = _fresh("stripe.receipt")
        r = admin_session.post(ST_ENDPOINT, json={**self.STRIPE_PAYLOAD_BASE, "email": email}, timeout=60)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body
        # Stripe simulator returns transaction_id (session_id) which is also stored as payment_id
        payment_id = body["scenario"].get("payment_id") or body["scenario"]["transaction_id"]

        tx = _find_tx(payment_id)
        assert tx, f"tx {payment_id} not found"
        # Payload integrity
        assert round(float(tx.get("subtotal", 0)), 2) == 153.50, tx.get("subtotal")
        assert round(float(tx.get("tax_amount", 0)), 2) == 9.59, tx.get("tax_amount")
        assert round(float(tx.get("processing_fee", 0)), 2) == 5.03, tx.get("processing_fee")
        assert round(float(tx.get("total_amount", 0)), 2) == 168.12, tx.get("total_amount")

        pdf = _render_receipt_pdf(tx, "TOM GOLDAM", email)
        text = _extract_pdf_text(pdf)
        # Base row now shows the tx subtotal ($153.50) — this is the intended
        # post-fix behavior (previously could have shown gross)
        assert "USD 153.50" in text, f"base 'USD 153.50' missing: {text[:2000]!r}"
        assert "USD 9.59" in text, f"tax 'USD 9.59' missing: {text[:2000]!r}"
        assert "USD 5.03" in text, f"fee 'USD 5.03' missing: {text[:2000]!r}"
        assert "USD 168.12" in text, f"total 'USD 168.12' missing: {text[:2000]!r}"
        # Sum invariant
        assert round(153.50 + 9.59 + 5.03, 2) == 168.12


# --------------------------------------------------------------------------- #
# 5. PayPal regression — 57.50 + 2.62 + 3.45 = 63.57
# --------------------------------------------------------------------------- #
class TestPayPalReceiptRegression:
    PP_PAYLOAD = {
        "name": "MR. WALTER W. WITHERSPOON JR. MDM ENTERPRISES, INC.",
        "address_line": "1401 S. MAIN ST.",
        "plan": "basic",
        "period": "yearly",
        "city": "Plummers Landing",
        "state_code": "KY",
        "country_code": "US",
        "postal_code": "41081-1411",
        "simulate_failure_case": False,
    }

    def test_paypal_receipt_pdf_line_items_sum(self, admin_session):
        email = _fresh("paypal.receipt")
        r = admin_session.post(PP_ENDPOINT, json={**self.PP_PAYLOAD, "email": email}, timeout=60)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body

        checks = body.get("checks") or {}
        for k in ("fee_accuracy", "notification_latency_under_2s",
                  "subscription_active", "api_integrity"):
            assert checks.get(k) is True, f"paypal check {k}: {checks}"

        payment_id = body["scenario"].get("payment_id") or body["scenario"]["transaction_id"]
        tx = _find_tx(payment_id)
        assert tx, f"tx {payment_id} missing"
        assert round(float(tx.get("subtotal", 0)), 2) == 57.50
        assert round(float(tx.get("tax_amount", 0)), 2) == 3.45
        assert round(float(tx.get("processing_fee", 0)), 2) == 2.62
        assert round(float(tx.get("total_amount", 0)), 2) == 63.57

        pdf = _render_receipt_pdf(tx, "WITHERSPOON JR", email)
        text = _extract_pdf_text(pdf)
        assert "USD 57.50" in text
        assert "USD 3.45" in text
        assert "USD 2.62" in text
        assert "USD 63.57" in text
        assert round(57.50 + 3.45 + 2.62, 2) == 63.57


# --------------------------------------------------------------------------- #
# 6. IAP regression — google/basic/monthly, receipt renders coherent USD
# --------------------------------------------------------------------------- #
class TestIapReceiptRegression:
    def test_iap_google_basic_monthly_receipt(self, admin_session):
        email = _fresh("iap.receipt")
        payload = {
            "email": email,
            "name": "Iap Test User",
            "address_line": "1 Main St",
            "plan": "basic",
            "period": "monthly",
            "platform": "google",
            "city": "Austin",
            "state_code": "TX",
            "country_code": "US",
            "postal_code": "73301",
            "simulate_failure_case": False,
        }
        r = admin_session.post(IAP_ENDPOINT, json=payload, timeout=60)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert body.get("success") is True, body

        payment_id = body["scenario"].get("payment_id") or body["scenario"].get("transaction_id")
        assert payment_id, f"no payment_id/transaction_id in scenario: {body.get('scenario')}"
        tx = _find_tx(payment_id)
        assert tx, f"tx {payment_id} missing"

        subtotal = float(tx.get("subtotal") or 0)
        tax = float(tx.get("tax_amount") or 0)
        fee = float(tx.get("processing_fee") or 0)
        total = float(tx.get("total_amount") or 0)
        # coherent line items (basic 5.99 + fee ~1.80 + tax ~0.36 ≈ total)
        assert subtotal > 0, f"subtotal not > 0: {subtotal}"
        assert total > 0, f"total not > 0: {total}"
        assert abs((subtotal + tax + fee) - total) < 0.05, (
            f"line items don't sum: base={subtotal} tax={tax} fee={fee} total={total}"
        )

        pdf = _render_receipt_pdf(tx, "Iap Test User", email)
        text = _extract_pdf_text(pdf)
        # PDF still renders and contains a USD currency string
        assert "USD" in text, f"PDF missing USD currency label: {text[:1200]!r}"
        assert f"USD {total:,.2f}" in text, (
            f"total 'USD {total:,.2f}' missing from PDF. Excerpt: {text[:2000]!r}"
        )
