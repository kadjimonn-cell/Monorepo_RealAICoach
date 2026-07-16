"""Backend verification for Checkpoint D bug fix (iteration 876):

Offer letter PDFs (original, rescinded, expired, declined, accepted) must show
'Human Resources (HR) Manager' as the signer title under 'Adjimon Kouatonou'
and must NOT contain 'Chief Executive Officer (CEO)' anywhere.

Covers:
- API: GET /api/careers/offer-branding (admin) returns HR title + Adjimon name.
- API: PUT /api/careers/offer-branding preserves signer_title on unrelated
  field updates (round-trip merge check).
- OFFLINE: PDF generation via routes.careers_offers._generate_offer_pdf for all
  four requested variants + accepted; extract text with PyMuPDF and assert
  presence/absence of expected strings.
- REGRESSION: seed guard — POST /api/careers/offer-branding/seed-demo does not
  overwrite admin-set signer_title with the CEO default.
- REGRESSION: GET /api/careers/offers (200), agent-framework overview >=200 agents.

Note: Skips POST /api/careers/offers/letters/review-email since it sends real
emails (main agent already invoked it once at 05:30Z). The offline PDF path uses
the same _generate_offer_pdf function.
"""

# ── imports & shared fixtures ──────────────────────────────────────────────
import asyncio
import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load backend .env for MONGO_URL when we import backend modules offline.
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

EXPECTED_TITLE = "Human Resources (HR) Manager"
FORBIDDEN_TITLE = "Chief Executive Officer (CEO)"
EXPECTED_SIGNER = "Adjimon Kouatonou"


# --- Admin session fixture ---------------------------------------------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


# ── Feature 1: GET /api/careers/offer-branding — signer_title / signer_name ─
class TestOfferBrandingRead:
    def test_get_offer_branding_returns_hr_title(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/careers/offer-branding", timeout=30)
        assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text[:200]}"
        data = r.json()
        # response may wrap branding under 'branding' or return flat
        branding = data.get("branding", data)
        assert branding.get("signer_title") == EXPECTED_TITLE, (
            f"expected signer_title '{EXPECTED_TITLE}', got {branding.get('signer_title')!r}"
        )
        assert branding.get("signer_name") == EXPECTED_SIGNER, (
            f"expected signer_name '{EXPECTED_SIGNER}', got {branding.get('signer_name')!r}"
        )


# ── Feature 2: PUT /api/careers/offer-branding — merge preserves signer_title
class TestOfferBrandingPreservation:
    def test_put_unrelated_field_preserves_signer_title(self, admin_session):
        # capture existing company_info to restore afterwards
        r = admin_session.get(f"{BASE_URL}/api/careers/offer-branding", timeout=30)
        assert r.status_code == 200
        current = r.json().get("branding", r.json())
        original_company_info = current.get("company_info")
        marker_value = "verify-signer-preserved-iter876@realaicoach.app"

        # PUT only company_info — do NOT send signer_title
        put1 = admin_session.put(
            f"{BASE_URL}/api/careers/offer-branding",
            json={"company_info": marker_value},
            timeout=30,
        )
        assert put1.status_code == 200, f"PUT failed: {put1.status_code} {put1.text[:200]}"

        # re-fetch and confirm signer_title is still HR Manager
        r2 = admin_session.get(f"{BASE_URL}/api/careers/offer-branding", timeout=30)
        assert r2.status_code == 200
        merged = r2.json().get("branding", r2.json())
        assert merged.get("company_info") == marker_value
        assert merged.get("signer_title") == EXPECTED_TITLE, (
            f"signer_title clobbered after unrelated PUT: {merged.get('signer_title')!r}"
        )
        assert merged.get("signer_name") == EXPECTED_SIGNER

        # restore original value
        if original_company_info:
            restore = admin_session.put(
                f"{BASE_URL}/api/careers/offer-branding",
                json={"company_info": original_company_info},
                timeout=30,
            )
            assert restore.status_code == 200


# ── Feature 3: Seed guard — does NOT overwrite admin signer_title  ──────────
class TestSeedGuardRegression:
    def test_seed_demo_does_not_clobber_admin_title(self, admin_session):
        # endpoint may or may not exist; if it does, verify guard.
        r = admin_session.post(
            f"{BASE_URL}/api/careers/offer-branding/seed-demo",
            json={},
            timeout=30,
        )
        if r.status_code == 404:
            pytest.skip("seed-demo endpoint not exposed")
        assert r.status_code == 200, f"seed-demo failed: {r.status_code} {r.text[:200]}"
        payload = r.json()
        branding = payload.get("branding", {})
        # signer_title must remain HR Manager (admin-set) regardless of seed skip/apply
        assert branding.get("signer_title") == EXPECTED_TITLE, (
            f"seed clobbered signer_title -> {branding.get('signer_title')!r}"
        )
        # re-check via GET
        r2 = admin_session.get(f"{BASE_URL}/api/careers/offer-branding", timeout=30)
        b2 = r2.json().get("branding", r2.json())
        assert b2.get("signer_title") == EXPECTED_TITLE


# ── Feature 4: Offline PDF generation + PyMuPDF text extraction — 5 variants ─
class TestOfferPdfSignerTitle:
    """Uses the actual production function _generate_offer_pdf with the merged
    branding (which comes from settings.offer_branding written by the admin PUT).
    We generate all variants offline and text-extract each with PyMuPDF."""

    @pytest.fixture(scope="class")
    def branding_and_offer(self):
        """Load merged branding from DB and return a valid minimal offer dict."""
        from routes.careers_offers import _load_offer_branding  # noqa

        branding = asyncio.get_event_loop().run_until_complete(_load_offer_branding())
        assert branding.get("signer_title") == EXPECTED_TITLE
        assert branding.get("signer_name") == EXPECTED_SIGNER

        offer = {
            "offer_id": "off_iter876test",
            "candidate_name": "Test Candidate",
            "candidate_email": "candidate.iter876@example.com",
            "candidate_address": "123 Test Street, Testville, CA 94000",
            "role_title": "Senior AI Engineer",
            "department": "Engineering",
            "employment_type": "Full-Time",
            "start_date": "2026-03-15",
            "base_salary_usd": 175000,
            # accepted variant needs signed_name to render the e-sig record
            "signed_name": "Test Candidate",
            "responded_at": "2026-01-31T05:30:00Z",
            "response_ip": "127.0.0.1",
            "signed_hash": "a" * 64,
        }
        return branding, offer

    def _extract_text(self, pdf_bytes: bytes) -> str:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()

    @pytest.mark.parametrize("variant", ["original", "rescinded", "expired", "declined", "accepted"])
    def test_variant_shows_hr_title_and_no_ceo(self, branding_and_offer, variant):
        from routes.careers_offers import _generate_offer_pdf  # noqa

        branding, offer = branding_and_offer
        # variant-specific offer state hints (declined needs no signed_name; keep as-is)
        pdf = _generate_offer_pdf(offer, variant=variant, branding=branding)
        assert isinstance(pdf, bytes) and len(pdf) > 1000, f"empty PDF for variant={variant}"

        text = self._extract_text(pdf)
        # Positive assertions
        assert EXPECTED_TITLE in text, (
            f"[{variant}] Missing '{EXPECTED_TITLE}' in PDF text (first 500 chars): {text[:500]!r}"
        )
        assert EXPECTED_SIGNER in text, (
            f"[{variant}] Missing signer name '{EXPECTED_SIGNER}' in PDF text"
        )
        # Negative assertion — the hardcoded CEO title must not appear anywhere
        assert FORBIDDEN_TITLE not in text, (
            f"[{variant}] Forbidden title '{FORBIDDEN_TITLE}' still present in PDF"
        )


# ── Feature 5: Regression — offers module + agent-framework endpoints  ──────
class TestOtherEndpointRegression:
    def test_get_careers_offers_200(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/careers/offers", timeout=30)
        assert r.status_code == 200, f"careers offers failed: {r.status_code} {r.text[:200]}"

    def test_agent_framework_overview_min_200_agents(self, admin_session):
        # Try common overview paths
        candidates = [
            "/api/agent-framework/overview",
            "/api/admin/agent-framework/overview",
        ]
        found_ok = None
        for path in candidates:
            r = admin_session.get(f"{BASE_URL}{path}", timeout=30)
            if r.status_code == 200:
                found_ok = r.json()
                break
        if not found_ok:
            pytest.skip("agent-framework overview endpoint not found under expected paths")
        # locate agent count
        agents = found_ok.get("agents")
        if isinstance(agents, int):
            total = agents
        elif isinstance(agents, dict):
            total = agents.get("total") or agents.get("count") or len(agents.get("items") or agents.get("list") or [])
        elif isinstance(agents, list):
            total = len(agents)
        else:
            total = (
                found_ok.get("total_agents")
                or found_ok.get("agents_count")
                or found_ok.get("summary", {}).get("total_agents")
            )
        assert total is not None, f"could not locate agent count in overview: keys={list(found_ok.keys())}, agents keys={list(agents.keys()) if isinstance(agents, dict) else type(agents)}"
        assert total >= 200, f"expected >=200 agents, got {total}"
