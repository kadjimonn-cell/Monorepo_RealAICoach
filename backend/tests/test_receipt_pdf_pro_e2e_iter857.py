"""E2E backend tests for Payment Receipt/Invoice Pro PDF v15 (iteration_857).

Covers:
- Free user cookie auth -> download own receipt via /api/r/f (relay) and /api/content/document
- Invoice plan-gate 403 for free user (expected)
- PDF content correctness (RECEIPT, RCT-, email, PAYMENT TIMELINE, TOTAL YOU PAY, HASH, SIGN, RECEIPT EXPLAINABILITY)
- 401 on unauthenticated relay hit
- 400 on invalid doc_type / missing payment_id
- Regression on /api/r/x?f=c (CSV) and /api/r/t?m=csv (HTML)
"""

from __future__ import annotations

import io
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://coach-web-preview.preview.emergentagent.com"

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
TXN_ID = "txn_a98b73968e034fe7"

REQUIRED_KEYWORDS = [
    "RECEIPT",
    "RCT-",
    FREE_EMAIL,
    "PAYMENT TIMELINE",
    "TOTAL YOU PAY",
    "HASH",
    "SIGN",
    "RECEIPT EXPLAINABILITY",
]


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Try pypdf then pdfminer to extract text. Fall back to raw bytes decode."""
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            try:
                text += "\n" + (page.extract_text() or "")
            except Exception:
                continue
    except Exception:
        pass
    if len(text.strip()) < 40:
        try:
            from pdfminer.high_level import extract_text

            text += "\n" + (extract_text(io.BytesIO(pdf_bytes)) or "")
        except Exception:
            pass
    if len(text.strip()) < 40:
        # last-resort raw grep for latin1 text (works for uncompressed ReportLab strings)
        try:
            text += "\n" + pdf_bytes.decode("latin-1", errors="ignore")
        except Exception:
            pass
    return text


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


# ---------- Auth / negative tests ---------- #

def test_unauth_relay_receipt_returns_401():
    r = requests.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": TXN_ID, "v": "0"},
        timeout=30,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


def test_content_document_invalid_doc_type_returns_400(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "bogus", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code == 400


def test_content_document_missing_payment_id_returns_400(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt"},
        timeout=30,
    )
    assert r.status_code == 400


# ---------- Positive: receipt download ---------- #

def test_free_user_receipt_via_relay_returns_pdf(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": TXN_ID, "v": "0"},
        timeout=60,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF"), "body must be a valid PDF"
    assert len(r.content) > 5000, f"pdf trivially small: {len(r.content)} bytes"


def test_free_user_receipt_via_content_document_returns_pdf(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": TXN_ID},
        timeout=60,
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 5000


def test_free_user_invoice_returns_403_plan_gate(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "invoice", "payment_id": TXN_ID},
        timeout=30,
    )
    # Expected plan-gate 403 for free user requesting invoice
    assert r.status_code == 403, f"expected 403 plan-gate, got {r.status_code}: {r.text[:400]}"
    try:
        payload = r.json()
    except Exception:
        payload = {"detail": r.text}
    body_text = str(payload).lower()
    assert (
        "upgrade" in body_text
        or "basic" in body_text
        or "premium" in body_text
        or "plan" in body_text
        or "invoice" in body_text
    ), f"403 body should mention upgrade/plan/invoice: {payload}"


# ---------- PDF content correctness ---------- #

def test_receipt_pdf_contains_required_sections(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": TXN_ID, "v": "0"},
        timeout=60,
    )
    assert r.status_code == 200
    text = _extract_pdf_text(r.content)
    missing = [kw for kw in REQUIRED_KEYWORDS if kw.upper() not in text.upper()]
    assert not missing, (
        f"receipt PDF missing required tokens: {missing}\n"
        f"extracted length: {len(text)} bytes\n"
        f"sample: {text[:800]}"
    )


# ---------- Regression: payment history export endpoints ---------- #

def test_payment_history_csv_export_via_relay(free_session):
    r = free_session.get(f"{BASE_URL}/api/r/x", params={"f": "c"}, timeout=60)
    assert r.status_code == 200, f"CSV relay export failed: {r.status_code} {r.text[:300]}"
    ct = r.headers.get("content-type", "").lower()
    # CSV export may set text/csv or application/octet-stream depending on renderer
    assert "csv" in ct or "octet" in ct or "text" in ct, f"unexpected content-type: {ct}"


def test_payment_history_tool_csv_html_via_relay(free_session):
    r = free_session.get(f"{BASE_URL}/api/r/t", params={"m": "csv"}, timeout=60)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "").lower()
    assert "Payment History CSV" in r.text
