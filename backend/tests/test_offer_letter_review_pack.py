"""Offer letter review pack (real-lifecycle flows) + native 'expired' PDF variant."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return sess


# ── Offline: expired variant in the PDF engine ──

class TestExpiredVariant:
    def test_variant_for_offer_expired(self):
        from routes.careers_offers import _variant_for_offer

        assert _variant_for_offer({"state": "expired"}) == "expired"
        assert _variant_for_offer({"state": "sent"}) == "original"
        assert _variant_for_offer({"state": "rescinded"}) == "rescinded"
        assert _variant_for_offer({"state": "declined"}) == "declined"
        assert _variant_for_offer({"state": "accepted"}) == "accepted"

    @pytest.mark.asyncio
    async def test_all_four_variants_generate_pdfs(self):
        from routes.careers_offers import (
            _generate_offer_pdf, _load_offer_branding, REVIEW_SAMPLE_CANDIDATE,
        )

        now = datetime.now(timezone.utc)
        branding = await _load_offer_branding()
        base = {
            "offer_id": "pytest-variant-check",
            "candidate_name": REVIEW_SAMPLE_CANDIDATE["name"],
            "candidate_email": "pytest@example.com",
            "candidate_address": REVIEW_SAMPLE_CANDIDATE["candidate_address"],
            "role_title": REVIEW_SAMPLE_CANDIDATE["role_title"],
            "department": REVIEW_SAMPLE_CANDIDATE["department"],
            "employment_type": "Full-time",
            "start_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
            "base_salary_usd": 185000,
        }
        for variant in ("original", "rescinded", "expired", "declined"):
            offer = dict(base)
            if variant == "expired":
                offer["expires_at"] = (now - timedelta(days=3)).isoformat()
            if variant == "rescinded":
                offer.update({"rescinded_at": now.isoformat(), "rescind_reason": "test"})
            if variant == "declined":
                offer.update({"responded_at": now.isoformat(), "decline_reason": "test"})
            pdf = _generate_offer_pdf(offer, variant=variant, branding=branding)
            assert pdf[:5] == b"%PDF-", f"{variant} did not produce a PDF"
            assert len(pdf) > 50_000, f"{variant} PDF suspiciously small"

    def test_template_registered(self):
        from utils.email_templates import TEMPLATE_CATALOG

        entry = TEMPLATE_CATALOG.get("career_offer_letters_review")
        assert entry, "career_offer_letters_review not in TEMPLATE_CATALOG"
        tpl = entry["builder"](admin_name="Test Admin")
        assert 'class="em-outer"' in tpl.html, "Template must carry v7 _wrap fingerprint"
        assert "4 Letter Variants" in tpl.subject


# ── Live: real-lifecycle review-email endpoint ──

class TestReviewEmailEndpoint:
    def test_requires_admin(self):
        r = requests.post(f"{BASE_URL}/api/careers/offers/letters/review-email",
                          headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_real_lifecycle_pack(self, admin):
        r = admin.post(f"{BASE_URL}/api/careers/offers/letters/review-email", timeout=180)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["success"] is True
        assert data["recipient"] == ADMIN["email"]
        assert data["flow"] == "real-lifecycle"
        assert data["cleaned_up"] is True
        by_letter = {l["letter"]: l for l in data["letters"]}
        assert set(by_letter) == {"offer", "rescinded", "expired", "rejected"}
        # Each letter must come from the genuine lifecycle state + variant
        assert by_letter["offer"]["state"] == "sent" and by_letter["offer"]["pdf_variant"] == "original"
        assert by_letter["rescinded"]["state"] == "rescinded" and by_letter["rescinded"]["pdf_variant"] == "rescinded"
        assert by_letter["expired"]["state"] == "expired" and by_letter["expired"]["pdf_variant"] == "expired"
        assert by_letter["rejected"]["state"] == "declined" and by_letter["rejected"]["pdf_variant"] == "declined"
        assert len(data["attachments"]) == 4
        assert all(name.endswith(".pdf") for name in data["attachments"])

    def test_samples_cleaned_up(self, admin):
        r = admin.get(f"{BASE_URL}/api/careers/offers", timeout=30)
        assert r.status_code == 200
        offers = r.json() if isinstance(r.json(), list) else r.json().get("offers", [])
        assert not any(o.get("is_review_sample") for o in offers), "Sample offers were not cleaned up"


# ── Regression: existing offers module intact ──

class TestOffersRegression:
    def test_list_offers_endpoint(self, admin):
        r = admin.get(f"{BASE_URL}/api/careers/offers", timeout=30)
        assert r.status_code == 200

    def test_agent_framework_untouched(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/overview", timeout=60)
        assert r.status_code == 200
        assert r.json()["agents"] >= 200
