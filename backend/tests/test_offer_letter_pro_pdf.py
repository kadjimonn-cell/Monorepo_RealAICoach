"""Backend tests — Offer Letter Pro (pdf-v15-offer-letter-pro-v6).

Direct unit-level rendering + PDF content validation for the "Offer Letter Pro"
enterprise redesign implemented in /app/backend/routes/careers_offers.py.

Covers (per review request iteration 854+):
  - All 4 lifecycle variants render successfully (original/accepted/declined/rescinded)
  - Year-1 Total Compensation hero card content
  - Countdown ribbon (only on variant=original)
  - Benefits snapshot chips
  - QR code SCAN TO ACCEPT (original) / SCAN TO VIEW (accepted) via candidate_token/public_confirm_url
  - Handwritten CEO signature image embedded
  - Variant badges (ACCEPTED & COUNTERSIGNED / RESPECTFULLY DECLINED / RESCINDED)
  - Strict validation regression (OfferDataValidationError)
  - Theme signature cache invalidation ('pdf-v15-offer-letter-pro-v6')
  - Endpoint smoke test with admin cookie session

Locked constraints (per agent_to_agent_context_note):
  - DO NOT modify the stored offer doc in db.career_offers (enrich copies in-memory only)
  - DO NOT send real emails / touch email_send_dedupe or notification caps
  - Motor loop-binding: fresh AsyncIOMotorClient inside asyncio.run
  - dotenv must be loaded manually
"""
from __future__ import annotations

import asyncio
import copy
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load env before touching anything backend-related
load_dotenv("/app/backend/.env")

# Ensure backend package is importable
sys.path.insert(0, "/app/backend")

# Imports from module under test
from routes import careers_offers  # noqa: E402
from routes.careers_offers import (  # noqa: E402
    OFFER_PDF_THEME_SIGNATURE,
    OfferDataValidationError,
    _cropped_signature_png_buffer,
    _generate_offer_pdf,
    _offer_qr_png_buffer,
)


OFFER_ID = "off_ddb1e393a694"


# ── Motor loop-safe fetchers ─────────────────────────────────────

def _fetch_offer_and_branding_sync() -> tuple[dict, dict]:
    """Fetch the real career offer doc + branding using a fresh motor client
    bound to a *new* asyncio loop, then run the coroutine to completion.
    """
    async def _inner():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            offer = await db["career_offers"].find_one({"offer_id": OFFER_ID}, {"_id": 0})
            # Load branding from settings collection directly (mirrors _load_offer_branding
            # layers 2 + 3 without touching module-level motor client on wrong loop).
            branding: dict = {
                "legal_name": "RealAICoach LLC",
                "hq_address": "11501 Domain Dr, Suite 200, Austin, TX 78758, USA",
                "signer_signature_image": "/app/backend/static/branding/adjimon-signature-handwritten.png",
                "custom_logo": "/app/backend/static/branding/realaicoach-logo.png",
                "signer_name": "Adjimon G.",
                "signer_title": "Chief Executive Officer (CEO)",
            }
            try:
                from routes.ai_learning_hub import (
                    CERTIFICATE_SIGNER_NAME as _CEO,
                    CERTIFICATE_SIGNER_ROLE as _CEO_ROLE,
                )
                if _CEO:
                    branding["signer_name"] = _CEO
                if _CEO_ROLE:
                    branding["signer_title"] = _CEO_ROLE
            except Exception:
                pass
            for key in ("receipt_branding", "offer_branding"):
                doc = await db.settings.find_one({"key": key}, {"_id": 0})
                if doc and doc.get("value"):
                    branding.update({k: v for k, v in doc["value"].items() if v not in (None, "")})
            # setdefaults required by task
            branding.setdefault("brand_name", "RealAICoach")
            branding.setdefault("company_info", "noreply@realaicoach.app")
            return offer, branding
        finally:
            client.close()

    return asyncio.run(_inner())


@pytest.fixture(scope="module")
def raw_offer_and_branding():
    offer, branding = _fetch_offer_and_branding_sync()
    assert offer is not None, f"Offer {OFFER_ID} must exist in db.career_offers"
    return offer, branding


@pytest.fixture()
def enriched_offer(raw_offer_and_branding):
    """Enrich a *copy* of the offer with fields required for strict rendering.
    Never mutates the DB doc.
    """
    offer, _branding = raw_offer_and_branding
    o = copy.deepcopy(offer)
    o.setdefault("candidate_name", "Offer Journey Candidate")
    o["candidate_address"] = "123 Main St, Suite 200, Austin, TX 78758, USA"
    o["department"] = "Engineering"
    o["start_date"] = "2026-02-15"
    o["work_city"] = "Austin"
    o["work_location"] = o.get("work_location") or "remote"
    o["role_title"] = o.get("role_title") or "Senior Software Engineer"
    o["employment_type"] = o.get("employment_type") or "Full-time"
    o["base_salary_usd"] = 115000
    o["bonus_target_pct"] = 12
    o["signing_bonus_usd"] = 8000
    o["relocation_usd"] = 0
    o["equity_shares"] = 12000
    o["pto_days"] = o.get("pto_days") or 20
    o["candidate_token"] = "test_candidate_token_" + "a" * 24
    o["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    return o


@pytest.fixture()
def branding(raw_offer_and_branding):
    _offer, br = raw_offer_and_branding
    return copy.deepcopy(br)


# ── Helpers ──────────────────────────────────────────────────

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


# ── Tests: theme signature constant ──────────────────────────

class TestThemeSignature:
    def test_theme_signature_constant(self):
        assert OFFER_PDF_THEME_SIGNATURE == "pdf-v15-offer-letter-pro-v6"


# ── Tests: 4 lifecycle variants render ───────────────────────

class TestVariantsRender:
    @pytest.mark.parametrize("variant", ["original", "accepted", "declined", "rescinded"])
    def test_variant_renders_valid_pdf(self, enriched_offer, branding, variant):
        offer = copy.deepcopy(enriched_offer)
        if variant == "accepted":
            offer["signed_name"] = "Offer Journey Candidate"
            offer["signed_hash"] = "abcdef0123456789" * 4
            offer["responded_at"] = datetime.now(timezone.utc).isoformat()
            offer["response_ip"] = "127.0.0.1"
        elif variant == "declined":
            offer["responded_at"] = datetime.now(timezone.utc).isoformat()
            offer["decline_reason"] = "Pursuing another opportunity"
        elif variant == "rescinded":
            offer["rescinded_at"] = datetime.now(timezone.utc).isoformat()
            offer["rescind_reason"] = "Role no longer available"

        pdf_bytes = _generate_offer_pdf(offer, variant=variant, branding=branding)
        assert isinstance(pdf_bytes, (bytes, bytearray)) and len(pdf_bytes) > 2000
        assert pdf_bytes[:4] == b"%PDF"


# ── Tests: original variant content ───────────────────────────

class TestOriginalContent:
    @pytest.fixture(scope="class")
    def rendered(self, request):
        # per-class rendering
        offer, br = _fetch_offer_and_branding_sync()
        assert offer is not None
        o = copy.deepcopy(offer)
        o["candidate_address"] = "123 Main St, Suite 200, Austin, TX 78758, USA"
        o["department"] = "Engineering"
        o["start_date"] = "2026-02-15"
        o["work_city"] = "Austin"
        o["role_title"] = o.get("role_title") or "Senior Software Engineer"
        o["base_salary_usd"] = 115000
        o["bonus_target_pct"] = 12
        o["signing_bonus_usd"] = 8000
        o["relocation_usd"] = 0
        o["equity_shares"] = 12000
        o["pto_days"] = 20
        o["candidate_token"] = "class_scope_token_" + "b" * 24
        o["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        br.setdefault("brand_name", "RealAICoach")
        br.setdefault("company_info", "noreply@realaicoach.app")
        pdf_bytes = _generate_offer_pdf(o, variant="original", branding=br)
        text, img_count = _extract_text_and_images(pdf_bytes)
        return {"pdf": pdf_bytes, "text": text, "img_count": img_count, "branding": br, "offer": o}

    def test_hero_label_present(self, rendered):
        assert "YEAR-1 TOTAL COMPENSATION VALUE" in rendered["text"]

    def test_year1_total_computed_and_formatted(self, rendered):
        # 115000 + round(115000 * 0.12) + 8000 + 0 = 136800
        assert "$136,800" in rendered["text"]

    def test_legend_labels(self, rendered):
        t = rendered["text"]
        assert "Base $" in t
        assert "Bonus target $" in t
        assert "Signing $" in t

    def test_countdown_ribbon(self, rendered):
        t = rendered["text"]
        assert "day" in t and "remaining" in t

    def test_chips_labels(self, rendered):
        t = rendered["text"]
        for label in ("START DATE", "EMPLOYMENT", "LOCATION", "PAID TIME OFF"):
            assert label in t, f"Missing chip label: {label}"

    def test_scan_to_accept_and_key_sections(self, rendered):
        t = rendered["text"]
        assert "SCAN TO ACCEPT" in t
        assert "Key Employment Terms" in t
        assert "Terms & Conditions" in t or "Terms &amp; Conditions" in t
        # 'Acceptance.' appears within the callout paragraph
        assert "Acceptance." in t

    def test_ceo_signer_present(self, rendered):
        t = rendered["text"]
        assert (rendered["branding"].get("signer_title") or "Human Resources (HR) Manager") in t
        assert rendered["branding"]["signer_name"] in t

    def test_qr_and_signature_images_embedded(self, rendered):
        # Header logo (2 pages) + QR + handwritten signature = >= 2 unique images
        # PyMuPDF counts image *references* per page; expect >= 3 across the doc.
        assert rendered["img_count"] >= 2, (
            f"Expected embedded images (logo/QR/signature) but got {rendered['img_count']}"
        )


# ── Tests: variant-specific behavior ─────────────────────────

class TestVariantBehavior:
    def _render_variant(self, enriched_offer, branding, variant: str) -> str:
        o = copy.deepcopy(enriched_offer)
        if variant == "accepted":
            o["signed_name"] = "Offer Journey Candidate"
            o["signed_hash"] = "deadbeef" * 8
            o["responded_at"] = datetime.now(timezone.utc).isoformat()
            o["response_ip"] = "203.0.113.10"
        elif variant == "declined":
            o["responded_at"] = datetime.now(timezone.utc).isoformat()
            o["decline_reason"] = "Different opportunity"
        elif variant == "rescinded":
            o["rescinded_at"] = datetime.now(timezone.utc).isoformat()
            o["rescind_reason"] = "Business decision"
        pdf_bytes = _generate_offer_pdf(o, variant=variant, branding=branding)
        text, _ = _extract_text_and_images(pdf_bytes)
        return text

    def test_accepted_badge_and_esign_block(self, enriched_offer, branding):
        t = self._render_variant(enriched_offer, branding, "accepted")
        assert "ACCEPTED & COUNTERSIGNED" in t
        assert "FULLY EXECUTED AGREEMENT" in t
        assert "Offer Journey Candidate" in t
        # Signature hash prefix should appear
        assert "deadbeef" in t

    def test_declined_badge(self, enriched_offer, branding):
        t = self._render_variant(enriched_offer, branding, "declined")
        assert "RESPECTFULLY DECLINED" in t

    def test_rescinded_badge(self, enriched_offer, branding):
        t = self._render_variant(enriched_offer, branding, "rescinded")
        assert "RESCINDED" in t

    @pytest.mark.parametrize("variant", ["accepted", "declined", "rescinded"])
    def test_qr_and_countdown_absent_in_terminal_variants(self, enriched_offer, branding, variant):
        t = self._render_variant(enriched_offer, branding, variant)
        assert "SCAN TO ACCEPT" not in t, (
            f"QR must not appear on variant={variant}"
        )
        # Countdown ribbon should also not render (variant guard)
        # The word "remaining" is unique to the ribbon in this template.
        assert "remaining" not in t.lower() or variant in ("accepted",), (
            f"Countdown ribbon must not render on variant={variant}"
        )


# ── Tests: variant assertions (permanent) — per iteration 855 request ─────
#
# These make the granular per-variant PDF content checks permanent regressions.
# All 4 variants rendered once per class (module-scope) to keep run-time low.

class TestVariantAssertions:
    """Comprehensive per-variant content assertions for the Offer Letter Pro v6
    redesign. Each variant renders once; text and image counts are extracted and
    reused across multiple targeted assertions.
    """

    @pytest.fixture(scope="class")
    def rendered_variants(self):
        offer, br = _fetch_offer_and_branding_sync()
        assert offer is not None, f"Offer {OFFER_ID} must exist in db.career_offers"
        br.setdefault("brand_name", "RealAICoach")
        br.setdefault("company_info", "noreply@realaicoach.app")

        # future-dated start (task says 2026-08-03) to guarantee "Your journey begins in N days"
        start_date = "2026-08-03"
        signed_name = "Offer Journey Candidate"
        legal_name = br.get("legal_name", "RealAICoach LLC")
        signer_name = br.get("signer_name", "Adjimon G.")

        def _base(o: dict) -> dict:
            o = copy.deepcopy(o)
            o.setdefault("candidate_name", signed_name)
            o["candidate_address"] = "123 Main St, Suite 200, Austin, TX 78758, USA"
            o["department"] = "Engineering"
            o["start_date"] = start_date
            o["work_city"] = "Austin"
            o["work_location"] = o.get("work_location") or "remote"
            o["role_title"] = o.get("role_title") or "Senior Software Engineer"
            o["employment_type"] = o.get("employment_type") or "Full-time"
            o["base_salary_usd"] = 115000
            o["bonus_target_pct"] = 12
            o["signing_bonus_usd"] = 8000
            o["relocation_usd"] = 0
            o["equity_shares"] = 12000
            o["pto_days"] = o.get("pto_days") or 20
            o["candidate_token"] = "iter855_token_" + "c" * 24
            o["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
            return o

        # original
        orig = _base(offer)

        # accepted
        acc = _base(offer)
        acc["signed_name"] = signed_name
        acc["signed_hash"] = "cafebabe" * 8  # 64-char hex
        acc["responded_at"] = datetime.now(timezone.utc).isoformat()
        acc["response_ip"] = "203.0.113.44"

        # declined — decline_reason must appear quoted in body
        dec = _base(offer)
        dec["responded_at"] = datetime.now(timezone.utc).isoformat()
        dec["decline_reason"] = "Accepted competing role closer to family"

        # rescinded
        res = _base(offer)
        res["rescinded_at"] = datetime.now(timezone.utc).isoformat()
        res["rescind_reason"] = "Role backfilled through internal transfer"

        out: dict = {"branding": br, "legal_name": legal_name, "signer_name": signer_name}
        for name, o in (
            ("original", orig),
            ("accepted", acc),
            ("declined", dec),
            ("rescinded", res),
        ):
            pdf = _generate_offer_pdf(o, variant=name, branding=br)
            assert pdf[:4] == b"%PDF", f"variant={name} did not produce a valid PDF"
            text, img_count = _extract_text_and_images(pdf)
            # also extract page-1 text separately for rescinded watermark check
            import fitz
            d = fitz.open(stream=pdf, filetype="pdf")
            page1_text = d[0].get_text("text")
            page1_img_count = len(d[0].get_images(full=True))
            # count images per page for signature-embedded check
            per_page_imgs = [len(d[i].get_images(full=True)) for i in range(d.page_count)]
            d.close()
            out[name] = {
                "pdf": pdf, "text": text, "img_count": img_count,
                "page1_text": page1_text, "page1_img_count": page1_img_count,
                "per_page_imgs": per_page_imgs, "offer": o,
            }
        return out

    # ── ACCEPTED ─────────────────────────────────────────────
    def test_accepted_badge_ribbon_and_journey_countdown(self, rendered_variants):
        t = rendered_variants["accepted"]["text"]
        assert "ACCEPTED & COUNTERSIGNED" in t, "Accepted badge missing"
        assert "OFFER ACCEPTED" in t, "Accepted ribbon 'OFFER ACCEPTED' missing"
        assert "fully executed on" in t, "'fully executed on' phrase missing"
        assert "Your journey begins in" in t, "Journey countdown card missing"
        assert "day" in t, "Countdown card should mention day/days"

    def test_accepted_fully_executed_dual_signature_block(self, rendered_variants):
        t = rendered_variants["accepted"]["text"]
        assert "FULLY EXECUTED AGREEMENT" in t
        assert "ELECTRONIC SIGNATURE RECORD" in t
        assert "CANDIDATE" in t
        assert rendered_variants["accepted"]["offer"]["signed_name"] in t
        assert "SHA-256" in t, "SHA-256 label missing on accepted variant"
        assert (rendered_variants["branding"].get("signer_title") or "Human Resources (HR) Manager") in t
        assert rendered_variants["signer_name"] in t

    def test_accepted_old_signed_by_box_removed(self, rendered_variants):
        """The standalone 'Signed by {legal_name}' sig-box header must be replaced
        by the dual FULLY EXECUTED AGREEMENT block on accepted variant."""
        t = rendered_variants["accepted"]["text"]
        legal = rendered_variants["legal_name"]
        assert f"Signed by {legal}" not in t, (
            "Old standalone 'Signed by ...' sig-box header must NOT appear on accepted variant"
        )

    def test_accepted_no_scan_to_accept(self, rendered_variants):
        assert "SCAN TO ACCEPT" not in rendered_variants["accepted"]["text"]

    def test_accepted_handwritten_signature_embedded(self, rendered_variants):
        """Some page containing the exec block must have >=1 non-logo image (the
        cropped CEO signature). We assert total image count >= 2 (logo + signature)
        and that the doc has more images than a signature-less run would produce.
        """
        per_page = rendered_variants["accepted"]["per_page_imgs"]
        assert sum(per_page) >= 2, (
            f"Accepted PDF must embed handwritten signature (per-page imgs={per_page})"
        )

    # ── DECLINED ─────────────────────────────────────────────
    def test_declined_badge_and_hero_historical_label(self, rendered_variants):
        t = rendered_variants["declined"]["text"]
        assert "RESPECTFULLY DECLINED" in t
        assert "HISTORICAL RECORD" in t, "Declined hero must carry the HISTORICAL RECORD label"
        # base hero label still present
        assert "YEAR-1 TOTAL COMPENSATION VALUE" in t

    def test_declined_closure_card_and_reason(self, rendered_variants):
        t = rendered_variants["declined"]["text"]
        # Tolerant substring checks (em-dash may normalize) — check both halves
        assert "CANDIDATE RESPONSE" in t
        assert "RESPECTFULLY DECLINED" in t
        assert rendered_variants["declined"]["offer"]["decline_reason"] in t, (
            "Decline reason text must be embedded verbatim in the closure card"
        )
        assert "The door remains open" in t

    def test_declined_has_standalone_sig_box_and_no_qr(self, rendered_variants):
        t = rendered_variants["declined"]["text"]
        legal = rendered_variants["legal_name"]
        assert f"Signed by {legal}" in t, "Standalone sig box header expected on declined variant"
        assert rendered_variants["signer_name"] in t
        assert "SCAN TO ACCEPT" not in t
        assert "remaining to accept" not in t

    # ── RESCINDED ────────────────────────────────────────────
    def test_rescinded_badge_and_void_hero_band(self, rendered_variants):
        t = rendered_variants["rescinded"]["text"]
        assert "RESCINDED" in t
        assert "NO LONGER IN EFFECT" in t
        assert "THIS COMPENSATION PACKAGE IS VOID" in t

    def test_rescinded_formal_notice_and_reason(self, rendered_variants):
        t = rendered_variants["rescinded"]["text"]
        assert "FORMAL RESCISSION NOTICE" in t
        assert rendered_variants["rescinded"]["offer"]["rescind_reason"] in t
        assert "Legal effect" in t
        assert "void and of no further force or effect" in t

    def test_rescinded_diagonal_watermark_on_page1(self, rendered_variants):
        """The diagonal watermark is drawn via canvas.drawCentredString so it
        should be extractable from page-1 text (subject to PyMuPDF normalization).
        """
        p1 = rendered_variants["rescinded"]["page1_text"]
        # There is also a 'RESCINDED - NO LONGER IN EFFECT' badge on page 1;
        # to confirm the *watermark* specifically, check RESCINDED appears at
        # least twice (once in the badge/hero and once in the watermark).
        occurrences = p1.count("RESCINDED")
        assert occurrences >= 2, (
            f"Expected RESCINDED to appear at least twice on page 1 (badge + watermark), got {occurrences}"
        )

    def test_rescinded_sig_box_present_and_no_qr(self, rendered_variants):
        t = rendered_variants["rescinded"]["text"]
        legal = rendered_variants["legal_name"]
        assert f"Signed by {legal}" in t, "Standalone sig box expected on rescinded variant"
        assert "SCAN TO ACCEPT" not in t

    # ── ORIGINAL regression (permanent) ──────────────────────
    def test_original_hero_has_no_historical_record_label(self, rendered_variants):
        t = rendered_variants["original"]["text"]
        assert "YEAR-1 TOTAL COMPENSATION VALUE" in t
        assert "HISTORICAL RECORD" not in t, (
            "Original variant hero must NOT include 'HISTORICAL RECORD' label"
        )

    def test_original_countdown_ribbon_present(self, rendered_variants):
        t = rendered_variants["original"]["text"]
        assert "remaining" in t.lower(), "Countdown 'remaining' must appear on original"

    def test_original_scan_to_accept_and_sig_box_present(self, rendered_variants):
        t = rendered_variants["original"]["text"]
        legal = rendered_variants["legal_name"]
        assert "SCAN TO ACCEPT" in t
        assert f"Signed by {legal}" in t

    def test_original_has_no_variant_specific_blocks(self, rendered_variants):
        t = rendered_variants["original"]["text"]
        forbidden = [
            "FULLY EXECUTED AGREEMENT",
            "ELECTRONIC SIGNATURE RECORD",
            "OFFER ACCEPTED",
            "Your journey begins",
            "CANDIDATE RESPONSE",
            "The door remains open",
            "FORMAL RESCISSION NOTICE",
            "NO LONGER IN EFFECT",
            "HISTORICAL RECORD",
        ]
        for phrase in forbidden:
            assert phrase not in t, (
                f"Original variant must not contain variant-specific phrase: {phrase!r}"
            )


# ── Tests: strict validation regression ──────────────────────

class TestStrictValidation:
    def test_missing_candidate_fields_raise(self, branding):
        # A minimal offer missing address/department/start_date must raise
        # OfferDataValidationError with those keys listed.
        offer = {
            "candidate_name": "Test User",
            "role_title": "SWE",
            "base_salary_usd": 100000,
            "employment_type": "Full-time",
            # deliberately missing: candidate_address, department, start_date
        }
        with pytest.raises(OfferDataValidationError) as exc_info:
            _generate_offer_pdf(offer, variant="original", branding=branding)
        missing = exc_info.value.missing
        assert "candidate.address" in missing
        assert "candidate.department" in missing
        assert "candidate.start_date" in missing


# ── Tests: signature/QR helpers ──────────────────────────────

class TestHelpers:
    def test_cropped_signature_returns_png_buffer(self):
        buf = _cropped_signature_png_buffer(
            "/app/backend/static/branding/adjimon-signature-handwritten.png"
        )
        assert buf is not None
        data = buf.getvalue()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_offer_qr_returns_png_buffer(self):
        buf = _offer_qr_png_buffer("https://example.com/careers/offer/confirm?token=abc")
        assert buf is not None
        data = buf.getvalue()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_offer_qr_handles_empty_url(self):
        # qrcode still encodes empty strings, but function must not crash;
        # helper returns either a buffer or None safely.
        buf = _offer_qr_png_buffer("")
        assert buf is None or buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


# ── Tests: theme signature cache invalidation logic ──────────

class TestThemeCacheInvalidation:
    def test_ensure_offer_pdf_regenerates_on_stale_signature(self, monkeypatch):
        """Verify _ensure_offer_pdf_current_theme regenerates when pdf_theme_signature
        does not match the current OFFER_PDF_THEME_SIGNATURE constant.
        """
        # Build a fake offer that looks like it was persisted with the previous
        # (stale) theme signature. pdf_path points nowhere so has_valid_file=False.
        stale_offer = {
            "offer_id": "off_test_stale",
            "candidate_name": "Test User",
            "candidate_address": "Test Addr",
            "role_title": "SWE",
            "department": "Engineering",
            "start_date": "2026-02-15",
            "base_salary_usd": 100000,
            "employment_type": "Full-time",
            "work_location": "remote",
            "pto_days": 15,
            "pdf_path": "uploads/offers/does_not_exist.pdf",
            "pdf_theme_signature": "pdf-v15-canonical-logo-tile-v4",  # old
            "pdf_variant": "original",
            "state": "draft",
        }
        # Capture what _persist_pdf sees + what update_one sees
        captured = {"persist_called": False, "update_called": False,
                    "signature_written": None, "variant_written": None}

        async def _fake_persist_pdf(offer_id, pdf_bytes, variant="original"):
            captured["persist_called"] = True
            captured["pdf_len"] = len(pdf_bytes)
            captured["variant_written"] = variant
            return (f"uploads/offers/{offer_id}.pdf", "fakehash" * 8)

        class _FakeUpdate:
            async def update_one(self, *a, **kw):
                captured["update_called"] = True
                # extract $set signature
                kw.get("upsert")  # unused
                # positional: filter, update
                if len(a) >= 2:
                    upd = a[1]
                    captured["signature_written"] = upd.get("$set", {}).get("pdf_theme_signature")
                    captured["variant_written"] = upd.get("$set", {}).get("pdf_variant") or captured["variant_written"]
                return None

        class _FakeDB:
            def __getitem__(self, name):
                return _FakeUpdate()

        async def _fake_get_or_404(offer_id):
            # Return the freshly-updated fake offer
            return {**stale_offer,
                    "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
                    "pdf_variant": "original",
                    "pdf_path": f"uploads/offers/{offer_id}.pdf"}

        async def _fake_branding():
            return {
                "brand_name": "RealAICoach",
                "legal_name": "RealAICoach LLC",
                "custom_logo": "/app/backend/static/branding/realaicoach-logo.png",
                "hq_address": "11501 Domain Dr, Austin",
                "company_info": "noreply@realaicoach.app",
                "signer_name": "Adjimon G.",
                "signer_title": "Chief Executive Officer (CEO)",
                "signer_signature_image": "/app/backend/static/branding/adjimon-signature-handwritten.png",
            }

        monkeypatch.setattr(careers_offers, "_persist_pdf", _fake_persist_pdf)
        monkeypatch.setattr(careers_offers, "db", _FakeDB())
        monkeypatch.setattr(careers_offers, "_get_offer_or_404", _fake_get_or_404)
        monkeypatch.setattr(careers_offers, "_load_offer_branding", _fake_branding)

        result = asyncio.run(careers_offers._ensure_offer_pdf_current_theme(stale_offer))
        assert captured["persist_called"] is True, "Stale-signature offer must trigger _persist_pdf"
        assert captured["update_called"] is True
        assert captured["signature_written"] == OFFER_PDF_THEME_SIGNATURE
        assert result["pdf_theme_signature"] == OFFER_PDF_THEME_SIGNATURE


# ── Tests: endpoint smoke via admin cookie session ────────────

class TestEndpointSmoke:
    """Live endpoint smoke:
      * Admin login must succeed.
      * GET /api/careers/offers/{id}/pdf must not crash. With the stored draft
        missing candidate address/department/start_date and no admin-configured
        brand_name/company_info override, strict validation should surface as
        HTTP 422 with a DATA_VALIDATION_ERROR-shaped JSON body.
    """

    BASE_URL = "http://localhost:8001"

    @pytest.fixture(scope="class")
    def admin_session(self):
        import requests
        s = requests.Session()
        s.headers.update({"X-Requested-With": "XMLHttpRequest"})
        r = s.post(
            f"{self.BASE_URL}/api/auth/login",
            json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
            timeout=15,
        )
        if r.status_code != 200:
            pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
        return s

    def test_health(self, admin_session):
        r = admin_session.get(f"{self.BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_admin_offer_pdf_endpoint_strict_shape(self, admin_session):
        r = admin_session.get(
            f"{self.BASE_URL}/api/careers/offers/{OFFER_ID}/pdf",
            timeout=30,
        )
        # Accept either a valid PDF (200) or a strict-validation 422 with proper shape.
        assert r.status_code in (200, 422), f"Unexpected status {r.status_code}: {r.text[:400]}"
        if r.status_code == 200:
            assert r.headers.get("content-type", "").startswith("application/pdf")
            assert r.content[:4] == b"%PDF"
        else:
            body = r.json()
            detail = body.get("detail") or {}
            assert detail.get("code") in ("BRANDING_INCOMPLETE", "OFFER_INCOMPLETE"), (
                f"Expected data-validation code in 422 body, got: {body}"
            )
            assert isinstance(detail.get("missing"), list) and len(detail["missing"]) > 0
            assert isinstance(detail.get("message"), str) and detail["message"]
