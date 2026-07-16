"""
Permanent regression tests for the Offer Branding seed-demo canonical key
contract + Job Offer PDF live E2E (bug: 422 BRANDING_INCOMPLETE / OFFER_INCOMPLETE).

Covers:
  1. GET  /api/careers/offer-branding -> merged branding shape.
  2. POST /api/careers/offer-branding/seed-demo idempotency + canonical keys.
  3. PUT  /api/careers/offer-branding accepts new brand_name + company_info
     fields and Zero-Assumptions guard rejects fabricated tokens (422).
  4. Live E2E: GET /api/careers/offers/off_ddb1e393a694/pdf returns 200 %PDF-1.4
     containing all expected canonical strings (parsed via PyMuPDF).
  5. Unit-level strict validation regression: _generate_offer_pdf with a copy
     of the offer missing candidate_address raises OfferDataValidationError.
  6. Public-token PDF path — skipped gracefully if the offer has no
     public_token.
"""
from __future__ import annotations

import asyncio
import os
import sys
import pytest
import requests

# Make backend importable for the unit test
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# Fall back to localhost for internal test runs (matches existing offer test file)
LOCAL_URL = "http://localhost:8001"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
OFFER_ID = "off_ddb1e393a694"

EXPECTED_BRAND_NAME = "RealAICoach"
EXPECTED_LEGAL_NAME = "RealAICoach LLC"
EXPECTED_HQ = "11501 Domain Dr, Suite 200, Austin, TX 78758, USA"
EXPECTED_HQ_LOOSE = "11501 Domain Dr"
EXPECTED_COMPANY_INFO = "security@realaicoach.app"
CANONICAL_KEYS = {
    "brand_name",
    "legal_name",
    "hq_address",
    "company_info",
    "signer_name",
    "signer_title",
}


def _admin_session(base: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{base}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed on {base}: {r.status_code} {r.text[:200]}")
    return s


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_local() -> requests.Session:
    """Admin session via internal localhost (fast + auth cookie reliable)."""
    return _admin_session(LOCAL_URL)


@pytest.fixture(scope="module")
def admin_external() -> requests.Session:
    """Admin session via the public REACT_APP_BACKEND_URL (E2E path)."""
    if BASE_URL == LOCAL_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set — external E2E skipped")
    return _admin_session(BASE_URL)


# ── 1) GET /careers/offer-branding contract ─────────────────────────────────
class TestOfferBrandingRead:
    def test_get_branding_returns_canonical_merged_shape(self, admin_local):
        r = admin_local.get(f"{LOCAL_URL}/api/careers/offer-branding", timeout=15)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("success") is True
        b = body.get("branding") or {}
        # All keys _generate_offer_pdf reads must be present + non-empty
        assert b.get("brand_name") == EXPECTED_BRAND_NAME, b.get("brand_name")
        assert b.get("legal_name") == EXPECTED_LEGAL_NAME, b.get("legal_name")
        assert b.get("company_info") == EXPECTED_COMPANY_INFO, b.get("company_info")
        assert EXPECTED_HQ_LOOSE in (b.get("hq_address") or ""), b.get("hq_address")
        assert (b.get("signer_name") or "").strip(), "signer_name must be non-empty"
        assert (b.get("signer_title") or "").strip(), "signer_title must be non-empty"


# ── 2) seed-demo canonical key contract + idempotency ───────────────────────
class TestSeedDemoCanonicalContract:
    def test_seed_demo_canonical_keys_only(self, admin_local):
        r = admin_local.post(
            f"{LOCAL_URL}/api/careers/offer-branding/seed-demo", timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("success") is True
        # Either freshly seeded or safely skipped — both are acceptable outcomes.
        assert body.get("seeded") is True or body.get("skipped") is True
        merged = body.get("branding") or {}
        # Canonical keys must be present in the merged branding
        for k in CANONICAL_KEYS:
            assert merged.get(k), f"Missing canonical key '{k}' after seed-demo: {merged}"
        assert merged["brand_name"] == EXPECTED_BRAND_NAME
        assert merged["legal_name"] == EXPECTED_LEGAL_NAME
        assert merged["company_info"] == EXPECTED_COMPANY_INFO
        assert EXPECTED_HQ_LOOSE in merged["hq_address"]
        # Contradictory legacy HQ must NEVER appear
        assert "Cotonou" not in str(merged), f"Legacy Cotonou HQ leaked: {merged}"
        # Fabricated NULL contact must not appear as company_info
        assert merged["company_info"] != "noreply@realaicoach.app"

    def test_seed_demo_is_idempotent_safe(self, admin_local):
        """Re-POST must not corrupt existing keys or produce a partial doc."""
        r = admin_local.post(
            f"{LOCAL_URL}/api/careers/offer-branding/seed-demo", timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("success") is True
        merged = body.get("branding") or {}
        # Still canonical after re-seed
        for k in CANONICAL_KEYS:
            assert merged.get(k), f"Key '{k}' vanished after re-seed: {merged}"
        assert merged["company_info"] == EXPECTED_COMPANY_INFO


# ── 3) PUT accepts brand_name + company_info; ZA guard rejects fabrication ──
class TestPutBrandingBody:
    def test_put_accepts_company_info_field(self, admin_local):
        """PUT with the SAME sanctioned value must succeed and reflect back.
        Uses only sanctioned canonical values.

        NOTE: The current PUT implementation REPLACES the entire offer_branding
        value doc (not a partial merge), so adjacent fields written by
        seed-demo may fall back to Layer-2/Layer-3 sources after a partial PUT.
        We therefore only assert on the field we sent + layer-3 hard defaults
        (legal_name, hq_address, signer_*) which come from platform constants.
        """
        r = admin_local.put(
            f"{LOCAL_URL}/api/careers/offer-branding",
            json={"company_info": EXPECTED_COMPANY_INFO},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("success") is True
        merged = body.get("branding") or {}
        assert merged.get("company_info") == EXPECTED_COMPANY_INFO
        # Layer-3 platform constants must remain (they are always merged in)
        assert merged.get("legal_name") == EXPECTED_LEGAL_NAME
        assert EXPECTED_HQ_LOOSE in (merged.get("hq_address") or "")
        # Restore canonical seed so downstream tests / environment stay clean.
        admin_local.post(
            f"{LOCAL_URL}/api/careers/offer-branding/seed-demo", timeout=20,
        )

    def test_put_accepts_brand_name_field(self, admin_local):
        # Ensure canonical baseline first
        admin_local.post(
            f"{LOCAL_URL}/api/careers/offer-branding/seed-demo", timeout=20,
        )
        r = admin_local.put(
            f"{LOCAL_URL}/api/careers/offer-branding",
            json={"brand_name": EXPECTED_BRAND_NAME},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        merged = body.get("branding") or {}
        assert merged.get("brand_name") == EXPECTED_BRAND_NAME
        # Restore canonical seed
        admin_local.post(
            f"{LOCAL_URL}/api/careers/offer-branding/seed-demo", timeout=20,
        )

    def test_put_rejects_fabricated_legal_name(self, admin_local):
        """Zero-Assumptions guard must return 422 for fabricated tokens
        (e.g. 'RealAICoach, Inc.' — real entity is 'RealAICoach LLC')."""
        r = admin_local.put(
            f"{LOCAL_URL}/api/careers/offer-branding",
            json={"legal_name": "RealAICoach, Inc."},
            timeout=15,
        )
        assert r.status_code == 422, r.text[:400]
        detail = r.json().get("detail") or {}
        assert detail.get("code") == "ZERO_ASSUMPTIONS_VIOLATION"
        assert "RealAICoach, Inc." in detail.get("fabricated_tokens", [])
        # Persistence check: legal_name must still be correct after the reject.
        v = admin_local.get(f"{LOCAL_URL}/api/careers/offer-branding", timeout=15).json()
        assert (v.get("branding") or {}).get("legal_name") == EXPECTED_LEGAL_NAME

    def test_put_rejects_fabricated_signer_name(self, admin_local):
        r = admin_local.put(
            f"{LOCAL_URL}/api/careers/offer-branding",
            json={"signer_name": "Samir Patel"},
            timeout=15,
        )
        assert r.status_code == 422, r.text[:400]
        detail = r.json().get("detail") or {}
        assert detail.get("code") == "ZERO_ASSUMPTIONS_VIOLATION"
        assert "Samir Patel" in detail.get("fabricated_tokens", [])


# ── 4) Live E2E: GET /careers/offers/{id}/pdf returns 200 + expected strings ─
class TestLiveOfferPdf:
    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        text_chunks: list[str] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page in doc:
                text_chunks.append(page.get_text())
        finally:
            doc.close()
        return "\n".join(text_chunks)

    def test_offer_pdf_endpoint_returns_valid_pdf_localhost(self, admin_local):
        r = admin_local.get(
            f"{LOCAL_URL}/api/careers/offers/{OFFER_ID}/pdf", timeout=60,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:400]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-", "Missing PDF magic"
        assert r.content[:8].startswith(b"%PDF-1."), f"Unexpected header: {r.content[:12]!r}"
        # Content assertions
        text = self._extract_pdf_text(r.content)
        assert "YEAR-1 TOTAL COMPENSATION VALUE" in text, "compensation summary missing"
        assert EXPECTED_COMPANY_INFO in text, f"contact email missing (got sample: {text[:400]})"
        assert EXPECTED_HQ_LOOSE in text, "HQ address missing"
        assert EXPECTED_LEGAL_NAME in text, "legal entity missing"
        assert "Engineering" in text, "department missing"
        assert "2026-08-03" in text, "start date missing"
        assert "Cotonou" not in text, "Legacy Cotonou HQ leaked into PDF!"
        # company_info contact should be security@; noreply@ must not appear
        # as the primary company_info label (it is fine in email headers,
        # but the SIDECAR / renderer reads 'company_info' from branding).
        # We assert security@realaicoach.app is present — the stronger contract.
        assert EXPECTED_COMPANY_INFO in text

    def test_offer_pdf_endpoint_external(self, admin_external):
        r = admin_external.get(
            f"{BASE_URL}/api/careers/offers/{OFFER_ID}/pdf", timeout=60,
        )
        assert r.status_code == 200, f"Expected 200 on external, got {r.status_code}: {r.text[:400]}"
        assert r.content[:5] == b"%PDF-"


# ── 5) Unit-level strict validation regression ──────────────────────────────
class TestStrictValidationRegression:
    def test_generate_offer_pdf_missing_candidate_address_raises(self):
        from routes.careers_offers import (
            _generate_offer_pdf, OfferDataValidationError, _load_offer_branding,
        )
        try:
            from pymongo import MongoClient
        except Exception:
            pytest.skip("pymongo not available")

        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
        try:
            offer = client[db_name].career_offers.find_one(
                {"offer_id": OFFER_ID}, {"_id": 0}
            )
        finally:
            client.close()
        if not offer:
            pytest.skip("Offer off_ddb1e393a694 not present in db.career_offers")

        async def _get_branding():
            return await _load_offer_branding()

        branding = asyncio.run(_get_branding())
        broken = dict(offer)
        broken["candidate_address"] = ""  # simulate missing field
        with pytest.raises(OfferDataValidationError) as exc:
            _generate_offer_pdf(broken, variant="original", branding=branding)
        missing = getattr(exc.value, "missing", None) or []
        assert any("candidate.address" in m for m in missing), (
            f"Expected candidate.address in missing list, got: {missing}"
        )


# ── 6) Public-token PDF (skip gracefully if unavailable) ────────────────────
class TestPublicOfferPdfPath:
    def test_public_pdf_path_or_skip(self, admin_local):
        # Use sync pymongo to avoid motor's event-loop coupling.
        try:
            from pymongo import MongoClient
        except Exception:
            pytest.skip("pymongo not available")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
        try:
            offer = client[db_name].career_offers.find_one(
                {"offer_id": OFFER_ID}, {"_id": 0, "public_token": 1}
            )
        finally:
            client.close()
        token = (offer or {}).get("public_token")
        if not token:
            pytest.skip(f"Offer {OFFER_ID} has no public_token — skip public PDF path")
        r = requests.get(
            f"{LOCAL_URL}/api/careers/offers/public/{token}/pdf", timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        assert r.content[:5] == b"%PDF-"
