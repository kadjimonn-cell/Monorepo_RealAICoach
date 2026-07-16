"""Fix-verification E2E backend tests for iteration_858.

These tests specifically verify that the plan-gate bypasses discovered in
iteration_857 have been closed:

1. Free user CAN download own RECEIPT via /api/content/document (was 403 → now 200 PDF)
2. Free user CANNOT bypass invoice gate via /api/r/f?d=i (now 403 with upgrade payload)
3. Same bypass closed for /api/r/v?d=i and /api/asset/f?d=i
4. /api/content/document?doc_type=invoice → 403 JSON detail contains required_plan=basic + upgrade_url
5. Validation for doc_type=bogus and missing payment_id is now REACHABLE (400)
6. Admin (basic+ equivalent) is NOT gated (no 403 with subscription_required payload)
"""

from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://coach-web-preview.preview.emergentagent.com"
)

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
TXN_ID = "txn_a98b73968e034fe7"


# ------------- fixtures ------------- #

@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    s.headers.update({"X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Free user login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


# ------------- Fix 1: content_document receipt path unblocked for free ------------- #

def test_free_receipt_via_content_document_is_200_pdf(free_session):
    """Regression: was 403 in iter_857 (SubscriptionEnforcement middleware). Should now be 200 PDF."""
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": TXN_ID},
        timeout=60,
    )
    assert r.status_code == 200, f"expected 200 receipt PDF, got {r.status_code}: {r.text[:300]}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 5000


# ------------- Fix 2: /api/r/f?d=i bypass closed ------------- #

def _assert_invoice_403_payload(r: requests.Response, alias: str):
    assert r.status_code == 403, f"[{alias}] expected 403, got {r.status_code}: {r.text[:400]}"
    try:
        body = r.json()
    except Exception:
        body = {"detail": r.text}
    txt = str(body).lower()
    # Required-plan basic and upgrade_url should be present (nested under detail)
    assert "basic" in txt, f"[{alias}] required_plan basic missing: {body}"
    assert "upgrade" in txt, f"[{alias}] upgrade_url/upgrade text missing: {body}"


def test_free_invoice_via_relay_f_returns_403(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "i", "p": TXN_ID, "v": "0"},
        timeout=30,
    )
    _assert_invoice_403_payload(r, "/api/r/f?d=i")


def test_free_invoice_via_relay_v_returns_403(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/r/v",
        params={"d": "i", "p": TXN_ID},
        timeout=30,
        allow_redirects=False,
    )
    _assert_invoice_403_payload(r, "/api/r/v?d=i")


def test_free_invoice_via_asset_f_returns_403(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/asset/f",
        params={"d": "i", "p": TXN_ID},
        timeout=30,
    )
    _assert_invoice_403_payload(r, "/api/asset/f?d=i")


# ------------- Fix 3: content_document invoice → 403 with structured detail ------------- #

def test_free_invoice_via_content_document_structured_403(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "invoice", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:400]}"
    body = r.json()
    # Detail may be nested (FastAPI HTTPException wraps under "detail")
    detail = body.get("detail", body)
    detail_str = str(detail).lower()
    assert "basic" in detail_str, f"required_plan basic missing: {body}"
    assert "upgrade" in detail_str, f"upgrade_url missing: {body}"


# ------------- Fix 4: receipt via /api/r/f?d=r still works (regression) ------------- #

def test_free_receipt_via_relay_still_200(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": TXN_ID, "v": "0"},
        timeout=60,
    )
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


# ------------- Fix 5: validation now reachable ------------- #

def test_bogus_doc_type_returns_400(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "bogus", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code == 400


def test_missing_payment_id_returns_400(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt"},
        timeout=30,
    )
    assert r.status_code == 400


def test_unauth_relay_receipt_returns_401():
    r = requests.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": TXN_ID, "v": "0"},
        timeout=30,
    )
    assert r.status_code == 401


# ------------- Fix 6: Admin plan-gate NOT triggered (not blocked by subscription_required) ------------- #

def test_admin_invoice_not_blocked_by_plan_gate(admin_session):
    """Admin should never see a 403 subscription_required payload for invoice access.

    Since the admin might not own txn_a98b73968e034fe7, the response can legitimately be 404
    or a permission-denied "not the owner" 403. What we assert: the 403 payload (if any) must
    NOT be a plan-gate. Concretely: response body must NOT contain required_plan/upgrade_url.
    """
    r = admin_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "invoice", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code in (200, 403, 404), f"unexpected admin status {r.status_code}: {r.text[:400]}"
    if r.status_code == 200:
        assert r.headers.get("content-type", "").startswith("application/pdf")
        return
    # Non-200: assert body is NOT a plan gate
    try:
        body = r.json()
    except Exception:
        body = {"detail": r.text}
    detail = str(body.get("detail", body)).lower()
    assert "required_plan" not in detail and "upgrade_url" not in detail, (
        f"admin got a plan-gate payload (should be permission/ownership error): {body}"
    )


def test_admin_receipt_not_blocked_by_plan_gate(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code in (200, 403, 404), f"unexpected admin status {r.status_code}: {r.text[:400]}"
    if r.status_code != 200:
        try:
            body = r.json()
        except Exception:
            body = {"detail": r.text}
        detail = str(body.get("detail", body)).lower()
        assert "required_plan" not in detail, f"admin got plan-gate: {body}"
