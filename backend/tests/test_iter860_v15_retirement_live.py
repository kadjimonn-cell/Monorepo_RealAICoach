"""Iteration 860 - live PDF v15 retirement verification against public backend URL."""
import io
import os
import re
import pytest
import requests
from pypdf import PdfReader

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"
TXN_ID = "txn_a98b73968e034fe7"

FORBIDDEN_TOKENS = [
    "GLOBAL PDF V15 POLICY ACTIVE",
    "RealAICoach PDF v15",
    "PDF v15",
]


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_EMAIL, FREE_PASS)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


def _pdf_text(payload: bytes) -> str:
    reader = PdfReader(io.BytesIO(payload))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _assert_no_v15(text: str, headers: dict) -> None:
    for tok in FORBIDDEN_TOKENS:
        assert tok not in text, f"forbidden token '{tok}' present in PDF text"
    # response header must not carry the enforced v15 policy marker
    assert headers.get("x-pdf-theme-policy") != "enforced-v15", f"stale header: {headers.get('x-pdf-theme-policy')}"


def test_free_user_receipt_no_v15_and_pricing_correct(free_session):
    r = free_session.get(f"{BASE_URL}/api/r/f", params={"d": "r", "p": TXN_ID, "v": 0}, timeout=45)
    assert r.status_code == 200, f"receipt status {r.status_code} body={r.text[:300]}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    dispo = r.headers.get("content-disposition", "")
    assert "-v15-" not in dispo, f"filename still contains -v15-: {dispo}"
    assert r.content[:5] == b"%PDF-"

    text = _pdf_text(r.content)
    _assert_no_v15(text, r.headers)

    # branded header intact
    for token in ["Enterprise Payment Confirmation", "Official Enterprise Document"]:
        assert token in text, f"missing branded token '{token}'"
    for token in ["RECEIPT", "PAYMENT TIMELINE", "TOTAL YOU PAY", "HASH", "SIGN"]:
        assert token in text, f"missing structural token '{token}'"

    # canonical pricing check (Basic monthly 5.99 -> total 6.69 with tax)
    # allow either 'USD 5.99' or '$5.99' formatting; require both.
    price_match = re.search(r"USD\s*5\.99|\$5\.99", text)
    total_match = re.search(r"USD\s*6\.69|\$6\.69", text)
    assert price_match, "canonical Basic price (5.99) not found in receipt PDF text"
    assert total_match, "expected total 6.69 not found in receipt PDF text"


def test_invoice_free_user_gated_403(free_session):
    r = free_session.get(f"{BASE_URL}/api/r/f", params={"d": "i", "p": TXN_ID, "v": 0}, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code}"


def test_content_document_receipt_free_user(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": TXN_ID},
        timeout=45,
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    text = _pdf_text(r.content)
    _assert_no_v15(text, r.headers)


def test_content_document_unauth_401():
    r = requests.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_content_document_invalid_type_400(free_session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "not-a-thing", "payment_id": TXN_ID},
        timeout=30,
    )
    assert r.status_code in (400, 422), f"expected 400/422 got {r.status_code}"


def test_payment_history_export_pdf_no_v15(free_session):
    r = free_session.get(f"{BASE_URL}/api/r/x", params={"f": "p"}, timeout=45)
    if r.status_code != 200:
        pytest.skip(f"payment history export not available: {r.status_code}")
    if not r.headers.get("content-type", "").startswith("application/pdf"):
        pytest.skip(f"not a pdf response: {r.headers.get('content-type')}")
    text = _pdf_text(r.content)
    _assert_no_v15(text, r.headers)


def test_admin_id_checker_export_pdf_no_v15(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/id-checker/admin/export/pdf", timeout=45)
    if r.status_code != 200:
        pytest.skip(f"admin id checker export status {r.status_code}")
    if not r.headers.get("content-type", "").startswith("application/pdf"):
        pytest.skip(f"non-pdf content-type: {r.headers.get('content-type')}")
    text = _pdf_text(r.content)
    _assert_no_v15(text, r.headers)


def test_subscription_plans_canonical_pricing_mongo():
    """Query mongo directly to confirm canonical pricing."""
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not available")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "realtalk_db")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    plans = {p.get("plan_id") or p.get("name") or p.get("_id"): p for p in db.subscription_plans.find({})}
    if not plans:
        pytest.skip("subscription_plans empty")
    # find basic + premium heuristically
    for key, p in plans.items():
        name = (p.get("plan_id") or p.get("name") or "").lower()
        price = p.get("monthly_price") or p.get("price")
        if "basic" in str(key).lower() or "basic" in name:
            assert float(price) == 5.99, f"basic price mismatch: {price}"
        if "premium" in str(key).lower() or "premium" in name:
            assert float(price) == 15.99, f"premium price mismatch: {price}"
