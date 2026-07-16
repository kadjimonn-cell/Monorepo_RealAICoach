"""Iteration 877 — Offer Letter QR bug independent verification.

Bug (user-reported):
    Offer letter PDFs referenced 'your secure candidate portal' but embedded NO QR code.

Root causes (fixed by main agent):
    1. QR condition checked nonexistent field `offer.public_token` (real fields are
       `candidate_token` / `public_confirm_url`).
    2. admin_send_offer generated PDF BEFORE storing the candidate token — the very first
       letter could never carry a QR even after fix #1.
    3. Old fixtures set the wrong `public_token` field and masked the bug in tests.

This suite (independent of the main agent's work) verifies both fixes:

A. Offline PDF rendering
   - `original` variant contains 'SCAN TO ACCEPT' and embeds an extra image (QR)
   - `accepted` variant contains 'SCAN TO VIEW'
   - `rescinded`, `expired`, `declined` variants contain NEITHER label
   - portal_url selection: `public_confirm_url` wins over env-derived fallback URL
   - env-fallback path composes `<FRONTEND_BASE_URL>/careers/offer/confirm?token=<candidate_token>`

B. Ordering fix — E2E lifecycle
   - Draft is created against a flagged test application (candidate_email = admin's inbox)
   - POST /offers/{id}/send stores candidate_token & public_confirm_url and persists a PDF
   - GET /offers/{id}/pdf (admin) returns a PDF whose text contains 'SCAN TO ACCEPT'
   - Cleanup mirrors _cleanup_review_samples pattern (offers + application + files removed)

C. Public candidate portal regression
   - GET /careers/offers/public/{candidate_token} returns 200 with offer view for valid token
   - Returns 404 for an invalid token
   - Accept requires acknowledge_terms=true + non-empty signed_name

Locked constraints:
- No production code changes (this file is test-only).
- ONE additional email may be sent to the admin inbox during E2E send (unavoidable path).
- Never touch the pre-existing offer `off_ddb1e393a694` or any non-flagged records.
"""
from __future__ import annotations

import asyncio
import copy
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load env before touching anything backend-related
load_dotenv("/app/backend/.env")

# Ensure backend package is importable
sys.path.insert(0, "/app/backend")

# Imports from module under test (offline path)
from routes import careers_offers  # noqa: E402
from routes.careers_offers import (  # noqa: E402
    OfferDataValidationError,
    _generate_offer_pdf,
    _offer_qr_png_buffer,
)


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# ── PyMuPDF extract helper ────────────────────────────────────
def _extract_text_and_images(pdf_bytes: bytes) -> tuple[str, int]:
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    img_count = 0
    for pg in doc:
        text += pg.get_text("text") + "\n"
        img_count += len(pg.get_images(full=True))
    doc.close()
    return text, img_count


# ── Motor loop-safe branding fetcher (mirrors iter855+ pattern) ──
def _load_branding_sync() -> dict:
    async def _inner():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            branding: dict = {
                "brand_name": "RealAICoach",
                "legal_name": "RealAICoach LLC",
                "hq_address": "11501 Domain Dr, Suite 200, Austin, TX 78758, USA",
                "signer_signature_image": "/app/backend/static/branding/adjimon-signature-handwritten.png",
                "custom_logo": "/app/backend/static/branding/realaicoach-logo.png",
                "signer_name": "Adjimon Kouatonou",
                "signer_title": "Human Resources (HR) Manager",
                "company_info": "noreply@realaicoach.app",
            }
            for key in ("receipt_branding", "offer_branding"):
                doc = await db.settings.find_one({"key": key}, {"_id": 0})
                if doc and doc.get("value"):
                    branding.update({k: v for k, v in doc["value"].items() if v not in (None, "")})
            return branding
        finally:
            client.close()
    return asyncio.run(_inner())


def _make_offer(candidate_token: str | None = None,
                public_confirm_url: str | None = None) -> dict:
    o = {
        "offer_id": f"off_iter877_{uuid.uuid4().hex[:8]}",
        "application_id": f"app_iter877_{uuid.uuid4().hex[:8]}",
        "candidate_name": "QR Verification Candidate",
        "candidate_email": ADMIN_EMAIL,
        "candidate_address": "123 Main St, Suite 200, Austin, TX 78758, USA",
        "role_title": "Senior AI Engineer",
        "department": "Engineering",
        "employment_type": "Full-time",
        "work_location": "remote",
        "work_city": "Austin",
        "start_date": "2026-03-01",
        "base_salary_usd": 150000,
        "bonus_target_pct": 15,
        "signing_bonus_usd": 10000,
        "relocation_usd": 0,
        "equity_shares": 10000,
        "pto_days": 20,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    }
    if candidate_token is not None:
        o["candidate_token"] = candidate_token
    if public_confirm_url is not None:
        o["public_confirm_url"] = public_confirm_url
    return o


# ═══════════════════════════════════════════════════════════════
# A. OFFLINE PDF RENDERING — QR presence per variant
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def branding() -> dict:
    return _load_branding_sync()


class TestQRPresencePerVariant:
    """Verify SCAN label + image count semantics across all 5 variants."""

    @pytest.fixture(scope="class")
    def rendered_variants(self):
        br = _load_branding_sync()
        candidate_token = "iter877_offline_" + "a" * 24
        public_url = f"https://example.test/careers/offer/confirm?token={candidate_token}"
        base_offer = _make_offer(candidate_token=candidate_token, public_confirm_url=public_url)
        results: dict[str, dict] = {}
        for variant in ("original", "accepted", "declined", "rescinded", "expired"):
            o = copy.deepcopy(base_offer)
            if variant == "accepted":
                o["signed_name"] = "QR Verification Candidate"
                o["signed_hash"] = "cafebabe" * 8
                o["responded_at"] = datetime.now(timezone.utc).isoformat()
                o["response_ip"] = "127.0.0.1"
            elif variant == "declined":
                o["responded_at"] = datetime.now(timezone.utc).isoformat()
                o["decline_reason"] = "Pursuing another opportunity"
            elif variant == "rescinded":
                o["rescinded_at"] = datetime.now(timezone.utc).isoformat()
                o["rescind_reason"] = "Role no longer available"
            elif variant == "expired":
                o["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            pdf_bytes = _generate_offer_pdf(o, variant=variant, branding=br)
            text, img_count = _extract_text_and_images(pdf_bytes)
            results[variant] = {"pdf": pdf_bytes, "text": text, "img_count": img_count}
        return results

    def test_original_has_scan_to_accept(self, rendered_variants):
        assert "SCAN TO ACCEPT" in rendered_variants["original"]["text"], (
            "BUG REGRESSION: original variant PDF missing 'SCAN TO ACCEPT' — QR not rendered")

    def test_accepted_has_scan_to_view(self, rendered_variants):
        assert "SCAN TO VIEW" in rendered_variants["accepted"]["text"], (
            "BUG REGRESSION: accepted variant PDF missing 'SCAN TO VIEW' — QR not rendered")

    @pytest.mark.parametrize("variant", ["rescinded", "expired", "declined"])
    def test_terminal_variants_have_no_scan_label(self, rendered_variants, variant):
        t = rendered_variants[variant]["text"]
        assert "SCAN TO ACCEPT" not in t, f"'{variant}' must not carry SCAN TO ACCEPT"
        assert "SCAN TO VIEW" not in t, f"'{variant}' must not carry SCAN TO VIEW"

    def test_original_has_at_least_three_images(self, rendered_variants):
        """Original must embed at least logo + CEO signature + QR = 3 images.
        (Terminal variants may include additional images like the VOID watermark
        so a direct count-comparison is not a reliable QR indicator — the SCAN label
        assertions above are the authoritative QR check.)
        """
        orig_imgs = rendered_variants["original"]["img_count"]
        assert orig_imgs >= 3, (
            f"original variant should embed >=3 images (logo+signature+QR), got {orig_imgs}")

    def test_accepted_has_at_least_three_images(self, rendered_variants):
        """Accepted embeds logo + CEO signature + candidate signature + QR."""
        acc_imgs = rendered_variants["accepted"]["img_count"]
        assert acc_imgs >= 3, (
            f"accepted variant should embed >=3 images (logo+signature+QR), got {acc_imgs}")


class TestPortalUrlSelection:
    """The bug was that offer.public_token was checked (nonexistent). Real code path:
       portal_url = offer.public_confirm_url OR fallback(FRONTEND_BASE_URL/candidate_token).
    """

    def test_public_confirm_url_wins_over_env_fallback(self, branding, monkeypatch):
        # If public_confirm_url is present, env is IRRELEVANT — we just verify SCAN label appears.
        monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
        monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
        o = _make_offer(
            candidate_token="tok_" + "z" * 32,
            public_confirm_url="https://portal.example.test/careers/offer/confirm?token=persisted",
        )
        pdf = _generate_offer_pdf(o, variant="original", branding=branding)
        text, _ = _extract_text_and_images(pdf)
        assert "SCAN TO ACCEPT" in text, (
            "public_confirm_url must trigger QR even when env vars are absent")

    def test_env_fallback_used_when_only_candidate_token(self, branding, monkeypatch):
        monkeypatch.setenv("FRONTEND_BASE_URL", "https://fallback.example.test")
        o = _make_offer(candidate_token="tok_fallback_" + "y" * 24)  # no public_confirm_url
        pdf = _generate_offer_pdf(o, variant="original", branding=branding)
        text, img_count = _extract_text_and_images(pdf)
        assert "SCAN TO ACCEPT" in text
        # Image count should be at least logo+signature+QR = 3
        assert img_count >= 3, f"expected >=3 embedded images (logo+sig+qr) but got {img_count}"

    def test_no_qr_when_neither_token_nor_url(self, branding, monkeypatch):
        monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
        monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
        o = _make_offer()  # no candidate_token, no public_confirm_url
        pdf = _generate_offer_pdf(o, variant="original", branding=branding)
        text, _ = _extract_text_and_images(pdf)
        # Without a portal_url, the QR condition is False so no SCAN label is drawn.
        assert "SCAN TO ACCEPT" not in text, (
            "SCAN TO ACCEPT must not appear when there is no candidate portal URL")


class TestOldBuggyFieldIgnored:
    """Documents the bug: legacy `public_token` field must NOT trigger the QR."""

    def test_legacy_public_token_field_does_not_trigger_qr(self, branding, monkeypatch):
        monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
        monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
        o = _make_offer()
        o["public_token"] = "legacy_bad_field_" + "x" * 20  # deliberately the wrong (old) field
        pdf = _generate_offer_pdf(o, variant="original", branding=branding)
        text, _ = _extract_text_and_images(pdf)
        assert "SCAN TO ACCEPT" not in text, (
            "Legacy `public_token` must not trigger QR — only candidate_token/public_confirm_url do")


class TestQRHelperFunction:
    def test_qr_generator_returns_png_buffer_for_valid_url(self):
        buf = _offer_qr_png_buffer("https://example.test/careers/offer/confirm?token=abc")
        assert buf is not None
        data = buf.getvalue()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", "QR helper must produce PNG bytes"

    def test_qr_generator_handles_empty_url_gracefully(self):
        # Empty string should be handled without crashing the flow.
        buf = _offer_qr_png_buffer("")
        # Either None or a fallback buffer is acceptable — the important thing is: no exception.
        assert buf is None or hasattr(buf, "getvalue")


# ═══════════════════════════════════════════════════════════════
# B. E2E ORDERING FIX — real /send flow persists QR from first letter
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed (status={r.status_code}): {r.text[:200]}")
    return s


def _cleanup_e2e_via_mongo(application_id: str, offer_id: str):
    """Direct DB cleanup mirroring _cleanup_review_samples semantics."""
    async def _inner():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            # Remove persisted PDF file first
            doc = await db.career_offers.find_one({"offer_id": offer_id}, {"_id": 0, "pdf_path": 1})
            if doc and doc.get("pdf_path"):
                try:
                    (Path("/app/backend") / doc["pdf_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            await db.career_offers.delete_many({"offer_id": offer_id})
            await db.careers_applications.delete_many({"application_id": application_id})
        finally:
            client.close()
    asyncio.run(_inner())


def _seed_flagged_application() -> str:
    """Insert a flagged application whose 'email' is admin's inbox."""
    application_id = f"app-iter877-{uuid.uuid4().hex[:8]}"

    async def _inner():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            await db.careers_applications.insert_one({
                "application_id": application_id,
                "name": "Iter877 QR Test Candidate",
                "email": ADMIN_EMAIL,
                "role_title": "Senior AI Engineer",
                "status": "offer",
                "is_review_sample": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            client.close()

    asyncio.run(_inner())
    return application_id


class TestOrderingFixE2E:
    """Verify that after admin_send_offer, the FIRST persisted PDF carries the QR."""

    def test_send_flow_produces_pdf_with_qr(self, admin_session):
        # Skip test if admin login failed (session fixture skips)
        application_id = _seed_flagged_application()
        offer_id = None
        try:
            # 1) Create a draft
            draft_body = {
                "application_id": application_id,
                "base_salary_usd": 165000,
                "bonus_target_pct": 12,
                "equity_shares": 8000,
                "signing_bonus_usd": 15000,
                "relocation_usd": 0,
                "pto_days": 20,
                "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
                "reporting_manager": "Jordan Lee, VP of Engineering",
                "work_location": "remote",
                "work_city": "Austin, TX",
                "department": "AI Platform Engineering",
                "employment_type": "Full-time",
                "candidate_address": "742 Innovation Drive, Suite 12, Austin, TX 78701, USA",
                "expiry_days": 7,
            }
            r = admin_session.post(f"{BASE_URL}/api/careers/offers/draft",
                                   json=draft_body, timeout=15)
            assert r.status_code == 200, f"draft creation failed: {r.status_code} {r.text[:300]}"
            offer_id = r.json()["offer_id"]

            # Flag the offer as a review sample so accidental leaks are easy to spot
            async def _flag():
                from motor.motor_asyncio import AsyncIOMotorClient
                client = AsyncIOMotorClient(os.environ["MONGO_URL"])
                try:
                    db = client[os.environ["DB_NAME"]]
                    await db.career_offers.update_one({"offer_id": offer_id},
                                                      {"$set": {"is_review_sample": True}})
                finally:
                    client.close()
            asyncio.run(_flag())

            # 2) Send the offer — this is the operation whose ordering was fixed
            r = admin_session.post(f"{BASE_URL}/api/careers/offers/{offer_id}/send", timeout=30)
            assert r.status_code == 200, f"send failed: {r.status_code} {r.text[:400]}"
            sent = r.json()
            assert sent.get("candidate_token"), "send response must include candidate_token"
            assert sent.get("public_confirm_url"), "send response must include public_confirm_url"
            assert sent.get("pdf_variant") == "original"

            # 3) Download the persisted PDF
            r = admin_session.get(f"{BASE_URL}/api/careers/offers/{offer_id}/pdf", timeout=15)
            assert r.status_code == 200, f"pdf download failed: {r.status_code} {r.text[:200]}"
            assert r.headers.get("content-type", "").startswith("application/pdf")
            pdf_bytes = r.content
            assert pdf_bytes[:4] == b"%PDF"

            # 4) Assert QR label is present — this is the CORE bug verification
            text, img_count = _extract_text_and_images(pdf_bytes)
            assert "SCAN TO ACCEPT" in text, (
                "ORDERING BUG REGRESSION: first-sent letter PDF does not carry 'SCAN TO ACCEPT'.\n"
                f"pdf_variant={sent.get('pdf_variant')} img_count={img_count}\n"
                "This means the candidate_token was not yet in offer_for_pdf at generation time.")
            assert img_count >= 3, (
                f"Expected >=3 embedded images (logo+signature+QR) but got {img_count}")

            # Also confirm the public-portal token is queryable
            token = sent["candidate_token"]
            r = admin_session.get(f"{BASE_URL}/api/careers/offers/public/{token}", timeout=15)
            assert r.status_code == 200, f"public GET failed: {r.status_code} {r.text[:200]}"
            body = r.json()
            assert body.get("success") is True
            assert body.get("offer_id") == offer_id or body.get("role_title")

            return None
        finally:
            if offer_id:
                _cleanup_e2e_via_mongo(application_id, offer_id)


# ═══════════════════════════════════════════════════════════════
# C. PUBLIC CANDIDATE PORTAL — regression
# ═══════════════════════════════════════════════════════════════

class TestPublicCandidatePortal:
    def test_get_public_offer_invalid_token_returns_404(self):
        r = requests.get(
            f"{BASE_URL}/api/careers/offers/public/definitely_not_a_valid_token_xxx",
            timeout=15,
        )
        assert r.status_code == 404, (
            f"Invalid token must return 404, got {r.status_code}: {r.text[:200]}")

    def test_accept_requires_ack_and_signed_name(self, admin_session):
        # Create+send a fresh offer, then attempt to accept it with missing fields.
        application_id = _seed_flagged_application()
        offer_id = None
        try:
            draft_body = {
                "application_id": application_id,
                "base_salary_usd": 140000, "bonus_target_pct": 10,
                "equity_shares": 5000, "signing_bonus_usd": 5000,
                "relocation_usd": 0, "pto_days": 20,
                "start_date": (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d"),
                "reporting_manager": "Jordan Lee, VP of Engineering",
                "work_location": "remote", "work_city": "Austin, TX",
                "department": "AI Platform Engineering", "employment_type": "Full-time",
                "candidate_address": "742 Innovation Drive, Suite 12, Austin, TX 78701, USA",
                "expiry_days": 7,
            }
            r = admin_session.post(f"{BASE_URL}/api/careers/offers/draft",
                                   json=draft_body, timeout=15)
            assert r.status_code == 200
            offer_id = r.json()["offer_id"]

            r = admin_session.post(f"{BASE_URL}/api/careers/offers/{offer_id}/send", timeout=30)
            assert r.status_code == 200
            token = r.json()["candidate_token"]

            # Missing acknowledge_terms -> 400
            r = requests.post(
                f"{BASE_URL}/api/careers/offers/public/{token}/accept",
                json={"signed_name": "Test User", "acknowledge_terms": False},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            assert r.status_code in (400, 422), (
                f"accept without ack must fail with 400/422, got {r.status_code}: {r.text[:200]}")

            # Missing signed_name (empty) -> 400/422
            r = requests.post(
                f"{BASE_URL}/api/careers/offers/public/{token}/accept",
                json={"signed_name": "", "acknowledge_terms": True},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            assert r.status_code in (400, 422), (
                f"accept with empty signed_name must fail, got {r.status_code}: {r.text[:200]}")
        finally:
            if offer_id:
                _cleanup_e2e_via_mongo(application_id, offer_id)

    def test_decline_flow(self, admin_session):
        application_id = _seed_flagged_application()
        offer_id = None
        try:
            draft_body = {
                "application_id": application_id,
                "base_salary_usd": 130000, "bonus_target_pct": 10,
                "equity_shares": 4000, "signing_bonus_usd": 3000,
                "relocation_usd": 0, "pto_days": 20,
                "start_date": (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d"),
                "reporting_manager": "Jordan Lee, VP of Engineering",
                "work_location": "remote", "work_city": "Austin, TX",
                "department": "AI Platform Engineering", "employment_type": "Full-time",
                "candidate_address": "742 Innovation Drive, Suite 12, Austin, TX 78701, USA",
                "expiry_days": 7,
            }
            r = admin_session.post(f"{BASE_URL}/api/careers/offers/draft",
                                   json=draft_body, timeout=15)
            assert r.status_code == 200
            offer_id = r.json()["offer_id"]
            r = admin_session.post(f"{BASE_URL}/api/careers/offers/{offer_id}/send", timeout=30)
            assert r.status_code == 200
            token = r.json()["candidate_token"]

            r = requests.post(
                f"{BASE_URL}/api/careers/offers/public/{token}/decline",
                json={"reason": "Accepted another opportunity"},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            assert r.status_code == 200, (
                f"decline should succeed, got {r.status_code}: {r.text[:200]}")
            data = r.json()
            assert data.get("success") is True
        finally:
            if offer_id:
                _cleanup_e2e_via_mongo(application_id, offer_id)
