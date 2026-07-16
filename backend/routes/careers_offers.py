"""
Careers — Offer Studio (Phase 1 + smart picks: e-sig, templates, benchmarking, auto-expiry).

Endpoints:
  Admin (auth):
    POST   /api/careers/offers/draft                       — create draft from application_id
    PATCH  /api/careers/offers/{offer_id}                  — update draft fields
    POST   /api/careers/offers/{offer_id}/ai-draft-body    — AI-generate offer body copy
    POST   /api/careers/offers/{offer_id}/send             — finalize + send via Resend
    POST   /api/careers/offers/{offer_id}/rescind          — rescind a sent offer
    GET    /api/careers/offers/{offer_id}                  — get full offer
    GET    /api/careers/offers/{offer_id}/pdf              — download offer PDF
    GET    /api/careers/offers                             — list offers
    GET    /api/careers/offers/benchmark                   — benchmarking stats
    GET    /api/careers/offer-templates                    — library list
    POST   /api/careers/offer-templates                    — save library entry
    DELETE /api/careers/offer-templates/{tid}              — delete library entry

  Public (token):
    GET    /api/careers/offers/public/{token}              — candidate view
    POST   /api/careers/offers/public/{token}/accept       — accept w/ typed e-sig
    POST   /api/careers/offers/public/{token}/decline      — decline w/ reason
    GET    /api/careers/offers/public/{token}/pdf          — download PDF
    GET    /api/careers/offers/public/{token}/pixel.gif    — email tracking pixel

  Internal:
    sweep_expired_offers()  — called by scheduler every hour
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from utils.pdf_v15_filename import build_pdf_v15_filename
from services.pdf_v15_theme import get_canonical_logo_tile_path

from routes.db import db, EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)

router = APIRouter()

OFFERS_COL = "career_offers"
OFFER_TEMPLATES_COL = "career_offer_templates"
APPS_COL = "careers_applications"

OFFERS_DIR = Path("/app/backend/uploads/offers")
OFFERS_DIR.mkdir(parents=True, exist_ok=True)
OFFER_PDF_THEME_SIGNATURE = "pdf-v15-offer-letter-pro-v6"


# ── Auth helpers ──────────────────────────────────────────────
async def _require_admin(request: Request):
    # Reuse the existing auth from careers.py
    from routes.careers import _require_admin as careers_admin
    return await careers_admin(request)


# ── Models ────────────────────────────────────────────────────
class OfferDraftBody(BaseModel):
    application_id: str
    # Compensation
    base_salary_usd: int = 0
    bonus_target_pct: int = 0
    equity_shares: int | None = None
    equity_pct: float | None = None
    signing_bonus_usd: int = 0
    relocation_usd: int = 0
    pto_days: int = 20
    # Logistics
    start_date: str = ""
    reporting_manager: str = ""
    work_location: str = "remote"
    work_city: str = ""
    department: str = ""
    employment_type: str = "Full-time"
    candidate_address: str = ""
    # Lifecycle
    expiry_days: int = 5
    personal_message: str = ""
    offer_body_md: str = ""


class OfferPatchBody(BaseModel):
    base_salary_usd: int | None = None
    bonus_target_pct: int | None = None
    equity_shares: int | None = None
    equity_pct: float | None = None
    signing_bonus_usd: int | None = None
    relocation_usd: int | None = None
    pto_days: int | None = None
    start_date: str | None = None
    reporting_manager: str | None = None
    work_location: str | None = None
    work_city: str | None = None
    department: str | None = None
    employment_type: str | None = None
    candidate_address: str | None = None
    expiry_days: int | None = None
    personal_message: str | None = None
    offer_body_md: str | None = None


class RescindBody(BaseModel):
    reason: str


class PublicAcceptBody(BaseModel):
    signed_name: str = Field(..., min_length=2)
    acknowledge_terms: bool


class PublicDeclineBody(BaseModel):
    reason: str | None = None


class AIDraftBody(BaseModel):
    tone: str = "professional"  # professional | warm | celebratory


class TemplateSaveBody(BaseModel):
    name: str = Field(..., min_length=2)
    base_salary_usd: int = 0
    bonus_target_pct: int = 0
    equity_shares: int | None = None
    equity_pct: float | None = None
    signing_bonus_usd: int = 0
    relocation_usd: int = 0
    pto_days: int = 20
    work_location: str = "remote"
    expiry_days: int = 5
    offer_body_md: str = ""


# ── Helpers ───────────────────────────────────────────────────
def _clean(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_offer_or_404(offer_id: str) -> dict[str, Any]:
    doc = await db[OFFERS_COL].find_one({"offer_id": offer_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Offer not found")
    return doc


def _variant_for_offer(offer: dict[str, Any]) -> str:
    state = str(offer.get("state") or "").lower()
    if state == "accepted":
        return "accepted"
    if state == "declined":
        return "declined"
    if state == "rescinded":
        return "rescinded"
    if state == "expired":
        return "expired"
    return "original"


async def _ensure_offer_pdf_current_theme(offer: dict[str, Any]) -> dict[str, Any]:
    """Regenerate cached offer PDF if theme signature/variant/file is stale."""
    expected_variant = _variant_for_offer(offer)
    full = Path("/app/backend") / offer["pdf_path"] if offer.get("pdf_path") else None
    has_valid_file = bool(full and full.exists())
    has_valid_signature = offer.get("pdf_theme_signature") == OFFER_PDF_THEME_SIGNATURE
    has_expected_variant = offer.get("pdf_variant") == expected_variant

    if offer.get("pdf_path") and has_valid_file and has_valid_signature and has_expected_variant:
        return offer

    _branding = await _load_offer_branding()
    pdf_bytes = _generate_offer_pdf(offer, variant=expected_variant, branding=_branding)
    pdf_path, pdf_hash = await _persist_pdf(offer["offer_id"], pdf_bytes, expected_variant)
    now_iso = _now_iso()
    await db[OFFERS_COL].update_one(
        {"offer_id": offer["offer_id"]},
        {
            "$set": {
                "pdf_path": pdf_path,
                "pdf_hash": pdf_hash,
                "pdf_variant": expected_variant,
                "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
                "pdf_regenerated_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )
    return await _get_offer_or_404(offer["offer_id"])


async def _find_by_candidate_token(token: str) -> dict[str, Any]:
    if not token or len(token) < 16:
        raise HTTPException(status_code=400, detail="Invalid token")
    doc = await db[OFFERS_COL].find_one({"candidate_token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Offer link invalid or expired")
    return doc


def _fmt_money(cents_or_units: int, currency: str = "USD") -> str:
    if not cents_or_units:
        return "—"
    return f"${int(cents_or_units):,} {currency}"


def _append_event(offer: dict[str, Any], ev_type: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    events = offer.get("events") or []
    events.append({"ts": _now_iso(), "type": ev_type, "meta": meta or {}})
    return {"events": events, "updated_at": _now_iso()}


# ── PDF Generator ─────────────────────────────────────────────
# ── Authoritative platform constants (mirrored from existing code paths) ──
# These values already live in the codebase in 10+ places (global_email_footer.html,
# brand_protection.py, payments.py, churn_recovery.py, reengagement.py, careers.py,
# scheduler.py, email_templates.py footer) — we re-use them here instead of re-typing
# or prompting the admin. Source of truth, not fabrication.
_PLATFORM_LEGAL_NAME = "RealAICoach LLC"
_PLATFORM_HQ_ADDRESS = "11501 Domain Dr, Suite 200, Austin, TX 78758, USA"
# CEO name/title/signature mirror the certificate signer used everywhere in the
# Learning Hub — see ai_learning_hub.CERTIFICATE_SIGNER_NAME / CERTIFICATE_SIGNER_ROLE.
# We import lazily (inside the function) to avoid a circular import at module load.
_PLATFORM_LOGO_FS_PATH = "/app/backend/static/branding/realaicoach-logo.png"
_PLATFORM_CEO_SIGNATURE_FS_PATH = "/app/backend/static/branding/adjimon-signature-handwritten.png"

# ── ZERO ASSUMPTIONS POLICY — runtime guardrail ──────────────────────────────
# Source: /app/memory/ZERO_ASSUMPTIONS_POLICY.md
# The canonical token list + scanner now live in utils.zero_assumptions so that
# the receipt/invoice generator, certificate signer, and email transport all
# enforce the same rule. The tuple below is a direct alias preserved for the
# CI static guard's sentinel-marker exemption AND for backward-compat with
# any external callers. DO NOT fork the list — extend utils.zero_assumptions.
from utils.zero_assumptions import (
    FORBIDDEN_TOKENS as _ZA_FORBIDDEN_TOKENS,
    assert_no_fabrication as _za_assert_no_fabrication,
)

_FORBIDDEN_FABRICATION_TOKENS: tuple[str, ...] = (
    "Samir Patel",
    "2261 Market Street",
    "2261 Market St,",
    "San Francisco, CA 94114",
    "RealAICoach, Inc.",  # note the comma — real entity is "RealAICoach LLC"
)
assert set(_FORBIDDEN_FABRICATION_TOKENS) == set(_ZA_FORBIDDEN_TOKENS), (
    "Drift between careers_offers._FORBIDDEN_FABRICATION_TOKENS and "
    "utils.zero_assumptions.FORBIDDEN_TOKENS — update both or (preferred) "
    "delete this local copy in favour of the shared list."
)


def _assert_no_fabrication(branding: dict[str, Any]) -> None:
    """Scan the branding doc for forbidden fabricated tokens before rendering.
    Fails loudly — no silent fallback. Trips the ZERO ASSUMPTIONS POLICY guard."""
    _za_assert_no_fabrication(branding, context="offer_branding")


async def _scrub_fabricated_branding() -> int:
    """Boot-time DB scrubber. Deletes settings.offer_branding / receipt_branding
    if they contain any fabricated tokens. Returns count removed. Invoked from
    server.py on startup so no legacy bad data can survive a reboot."""
    removed = 0
    for key in ("offer_branding", "receipt_branding"):
        try:
            doc = await db.settings.find_one({"key": key}, {"_id": 0})
        except Exception:
            continue
        if not doc:
            continue
        blob = str(doc)
        hits = [t for t in _FORBIDDEN_FABRICATION_TOKENS if t in blob]
        if hits:
            logger.error(
                "[ZERO-ASSUMPTIONS] Scrubbing settings.%s — contained fabricated tokens: %s",
                key, hits,
            )
            try:
                await db.settings.delete_one({"key": key})
                removed += 1
            except Exception as e:
                logger.error("[ZERO-ASSUMPTIONS] Failed to scrub settings.%s: %s", key, e)
    return removed


async def _load_offer_branding() -> dict[str, Any]:
    """Fetch real platform branding for offer PDFs.

    Source of truth (in priority order):
      1. settings.offer_branding  (admin overrides via PUT /careers/offer-branding)
      2. settings.receipt_branding (brand name, colors, logo, support email)
      3. Hardcoded platform constants (Legal Name, HQ Address, CEO name/title/signature)
         — identical to what the Learning Hub certificates and the global email footer
         already render. Zero fabrication.

    Enforces the ZERO ASSUMPTIONS POLICY via _assert_no_fabrication before returning.
    """
    branding: dict[str, Any] = {}
    # Layer 3 → Layer 2 → Layer 1 (later writes win)
    # --- Layer 3: platform-wide defaults (already used by certificates + email footers) ---
    try:
        from routes.ai_learning_hub import (
            CERTIFICATE_SIGNER_NAME as _CEO,
            CERTIFICATE_SIGNER_ROLE as _CEO_ROLE,
        )
    except Exception:
        _CEO, _CEO_ROLE = "", ""
    branding.update({
        "legal_name": _PLATFORM_LEGAL_NAME,
        "hq_address": _PLATFORM_HQ_ADDRESS,
        "signer_name": _CEO,
        "signer_title": _CEO_ROLE,
        "signer_signature_image": _PLATFORM_CEO_SIGNATURE_FS_PATH,
        "custom_logo": _PLATFORM_LOGO_FS_PATH,
    })
    # --- Layer 2: receipt_branding (admin-configured brand identity) ---
    try:
        receipt = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
        if receipt and receipt.get("value"):
            branding.update({k: v for k, v in receipt["value"].items() if v not in (None, "")})
    except Exception:
        pass
    # --- Layer 1: offer_branding (explicit admin overrides for offers only) ---
    try:
        offer = await db.settings.find_one({"key": "offer_branding"}, {"_id": 0})
        if offer and offer.get("value"):
            branding.update({k: v for k, v in offer["value"].items() if v not in (None, "")})
    except Exception:
        pass
    # Runtime ZERO ASSUMPTIONS guard — final check before returning.
    _assert_no_fabrication(branding)
    return branding


class OfferDataValidationError(Exception):
    """Raised when required platform data is missing for offer PDF generation."""
    def __init__(self, missing: list[str], section: str = ""):
        self.missing = missing
        self.section = section
        super().__init__(f"DATA_VALIDATION_ERROR: Missing required field(s): {', '.join(missing)}")


def _cropped_signature_png_buffer(path: str) -> BytesIO | None:
    """Ink-cropped CEO signature (white padding removed, white→alpha). Returns PNG buffer."""
    try:
        from PIL import Image, ImageChops
        import numpy as np

        with Image.open(path) as raw:
            img = raw.convert("RGB")
        darkness = ImageChops.invert(img.convert("L"))
        mask = np.array(darkness) > 30
        rows = np.where(mask.sum(axis=1) >= 6)[0]
        cols = np.where(mask.sum(axis=0) >= 6)[0]
        if not len(rows) or not len(cols):
            return None
        pad = 10
        bbox = (max(0, int(cols[0]) - pad), max(0, int(rows[0]) - pad),
                min(img.width, int(cols[-1]) + 1 + pad), min(img.height, int(rows[-1]) + 1 + pad))
        img = img.crop(bbox)
        darkness = darkness.crop(bbox)
        alpha = darkness.point(lambda v: min(255, int(v * 2.2)))
        rgba = img.convert("RGBA")
        rgba.putalpha(alpha)
        out = BytesIO()
        rgba.save(out, format="PNG")
        out.seek(0)
        return out
    except Exception:
        return None


def _offer_qr_png_buffer(url: str) -> BytesIO | None:
    try:
        import qrcode

        img = qrcode.make(url, box_size=6, border=1)
        out = BytesIO()
        (img.get_image() if hasattr(img, "get_image") else img).convert("RGB").save(out, format="PNG")
        out.seek(0)
        return out
    except Exception:
        return None


def _generate_offer_pdf(offer: dict[str, Any], *, variant: str = "original",
                         branding: dict[str, Any] | None = None) -> bytes:
    """STRICT DATA-BOUND MODE — fails loudly when any required field is missing.
    variant: 'original' | 'accepted' | 'declined' | 'rescinded' | 'expired'
    """
    # ── STRICT VALIDATION: NO FABRICATION ──────────────────────
    branding = branding or {}
    missing: list[str] = []
    # Company (from receipt_branding + offer_branding)
    if not branding.get("brand_name"):
        missing.append("company.brand_name")
    if not branding.get("legal_name"):
        missing.append("company.legal_name")
    if not branding.get("custom_logo"):
        missing.append("company.logo")
    if not branding.get("hq_address"):
        missing.append("company.registered_address")
    if not branding.get("company_info"):
        missing.append("company.official_email")
    # Executive
    if not branding.get("signer_name"):
        missing.append("executive.ceo_full_name")
    # signer_title comes from the offer-branding config chain (admin-editable)
    # signature: ok to be optional (falls back to stylised italic) — but warn if admin wants real one
    # Candidate
    if not offer.get("candidate_name"):
        missing.append("candidate.full_name")
    if not offer.get("candidate_address"):
        missing.append("candidate.address")
    if not offer.get("role_title"):
        missing.append("candidate.position_title")
    if not offer.get("department"):
        missing.append("candidate.department")
    if not offer.get("start_date"):
        missing.append("candidate.start_date")
    if not offer.get("base_salary_usd"):
        missing.append("candidate.salary")
    if not offer.get("employment_type"):
        missing.append("candidate.employment_type")
    # Reporting manager is optional per spec ("if available") — not flagged
    if missing:
        raise OfferDataValidationError(missing)

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfgen.canvas import Canvas

    # Real platform branding — zero fabrication
    brand_name   = branding["brand_name"]
    legal_name   = branding["legal_name"]
    primary_hex  = branding.get("primary_color") or "#2563EB"
    secondary_hex = branding.get("secondary_color") or "#F97316"
    logo_rel     = branding["custom_logo"]
    contact_email = branding["company_info"]
    website      = branding.get("website") or ""
    hq_address   = branding["hq_address"]
    signer_name  = branding["signer_name"]
    signer_title = branding.get("signer_title") or "Human Resources (HR) Manager"
    logo_fs_path = ("/app/backend" + logo_rel.replace("/api/", "/")) if logo_rel.startswith("/api/") else logo_rel
    strict_header_logo_fs_path = get_canonical_logo_tile_path() or logo_fs_path

    PRIMARY = HexColor(primary_hex)
    HexColor(secondary_hex)
    INK = HexColor("#0F172A")
    SLATE = HexColor("#475569")
    SLATE_SOFT = HexColor("#F1F5F9")
    SUCCESS = HexColor("#047857")
    DANGER = HexColor("#B91C1C")
    GREY = HexColor("#64748B")

    # Extended palette — V2 Teal Enterprise
    TEAL        = HexColor("#14B8A6")
    TEAL_DEEP   = HexColor("#0F766E")
    TEAL_50     = HexColor("#F0FDFA")   # very light teal wash
    TEAL_100    = HexColor("#CCFBF1")
    AMBER       = HexColor("#F59E0B")
    HexColor("#FFFBEB")
    INDIGO      = HexColor("#4F46E5")
    HexColor("#EEF2FF")
    HexColor("#E11D48")
    EMERALD_50  = HexColor("#ECFDF5")
    BORDER_SOFT = HexColor("#E2E8F0")
    HexColor("#FAFAFA")

    variant_meta = {
        "original":  {"badge": None, "color": PRIMARY},
        "accepted":  {"badge": "ACCEPTED & COUNTERSIGNED", "color": SUCCESS},
        "declined":  {"badge": "RESPECTFULLY DECLINED", "color": GREY},
        "rescinded": {"badge": "RESCINDED - NO LONGER IN EFFECT", "color": DANGER},
        "expired":   {"badge": "OFFER EXPIRED - NO LONGER VALID", "color": AMBER},
    }[variant]

    buf = BytesIO()

    def _header_footer(canvas: Canvas, doc_inner):
        canvas.saveState()
        page_w, page_h = letter[0], letter[1]

        # ── Soft confidentiality watermark (page 2 only) ────────────────────
        # ── RESCINDED diagonal watermark (page 1) ───────────────────────────
        if variant == "rescinded" and doc_inner.page == 1:
            canvas.saveState()
            canvas.setFillColor(DANGER)
            canvas.setFillAlpha(0.08)
            canvas.setFont("Helvetica-Bold", 88)
            canvas.translate(page_w / 2, page_h / 2)
            canvas.rotate(30)
            canvas.drawCentredString(0, 0, "RESCINDED")
            canvas.restoreState()

        # ── EXPIRED diagonal watermark (page 1) ─────────────────────────────
        if variant == "expired" and doc_inner.page == 1:
            canvas.saveState()
            canvas.setFillColor(AMBER)
            canvas.setFillAlpha(0.08)
            canvas.setFont("Helvetica-Bold", 88)
            canvas.translate(page_w / 2, page_h / 2)
            canvas.rotate(30)
            canvas.drawCentredString(0, 0, "EXPIRED")
            canvas.restoreState()

        if doc_inner.page >= 2:
            try:
                if os.path.exists(logo_fs_path):
                    canvas.saveState()
                    canvas.setFillAlpha(0.05)
                    canvas.drawImage(logo_fs_path, page_w / 2 - 2.5 * inch, page_h / 2 - 2.5 * inch,
                                     width=5 * inch, height=5 * inch, mask="auto", preserveAspectRatio=True)
                    canvas.restoreState()
                # Large diagonal CONFIDENTIAL stamp
                canvas.saveState()
                canvas.setFillColor(SLATE)
                canvas.setFillAlpha(0.04)
                canvas.setFont("Helvetica-Bold", 72)
                canvas.translate(page_w / 2, page_h / 2)
                canvas.rotate(30)
                canvas.drawCentredString(0, 0, "CONFIDENTIAL")
                canvas.restoreState()
            except Exception:
                pass

        # ── Top dual-tone accent strip (teal → primary) ─────────────────────
        canvas.setFillColor(TEAL)
        canvas.rect(0, page_h - 0.06 * inch, page_w * 0.55, 0.06 * inch, stroke=0, fill=1)
        canvas.setFillColor(PRIMARY)
        canvas.rect(page_w * 0.55, page_h - 0.06 * inch, page_w * 0.45, 0.06 * inch, stroke=0, fill=1)

        # ── Main header bar (primary) with subtle right-edge fade to indigo ─
        canvas.setFillColor(PRIMARY)
        canvas.rect(0, page_h - 1.1 * inch, page_w, 1.04 * inch, stroke=0, fill=1)
        canvas.setFillColor(INDIGO)
        canvas.rect(page_w * 0.72, page_h - 1.1 * inch, page_w * 0.28, 1.04 * inch, stroke=0, fill=1)
        canvas.setFillAlpha(0.35)
        canvas.setFillColor(PRIMARY)
        canvas.rect(page_w * 0.72, page_h - 1.1 * inch, page_w * 0.28, 1.04 * inch, stroke=0, fill=1)
        canvas.setFillAlpha(1.0)

        # Thin teal divider under the header
        canvas.setFillColor(TEAL)
        canvas.rect(0, page_h - 1.13 * inch, page_w, 0.03 * inch, stroke=0, fill=1)

        # ── Rounded-corner white tile behind the logo ────────────────────────
        tile_x = 0.45 * inch
        tile_y = page_h - 0.98 * inch
        canvas.setFillColor(white)
        canvas.roundRect(tile_x, tile_y, 0.78 * inch, 0.78 * inch, 6, stroke=0, fill=1)

        # Logo
        try:
            if strict_header_logo_fs_path and os.path.exists(strict_header_logo_fs_path):
                canvas.drawImage(strict_header_logo_fs_path, tile_x + 0.08 * inch, tile_y + 0.08 * inch,
                                 width=0.62 * inch, height=0.62 * inch,
                                 mask="auto", preserveAspectRatio=True)
        except Exception:
            pass

        # ── Legal name + subtitle ────────────────────────────────────────────
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(1.4 * inch, page_h - 0.52 * inch, legal_name)
        # Small teal dot between subtitle components
        canvas.setFillColor(TEAL_100)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(1.4 * inch, page_h - 0.72 * inch, "Official Job Offer  •  Confidential  •  Enterprise Issue")

        # ── Right column contact (stack of emails + location) ──────────────
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.45 * inch, contact_email)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.58 * inch, "hiring@realaicoach.app")
        canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.71 * inch, "careers@realaicoach.app")
        canvas.setFont("Helvetica", 7.5)
        if website:
            canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.85 * inch, website)
            canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.98 * inch, hq_address)
        else:
            canvas.drawRightString(page_w - 0.5 * inch, page_h - 0.85 * inch, hq_address)

        # ── Variant badge (second bar below header) ──────────────────────────
        if variant_meta["badge"]:
            canvas.setFillColor(variant_meta["color"])
            canvas.rect(0, page_h - 1.4 * inch, page_w, 0.27 * inch, stroke=0, fill=1)
            # Small white dot accents
            canvas.setFillColor(white)
            canvas.circle(0.55 * inch, page_h - 1.265 * inch, 0.04 * inch, stroke=0, fill=1)
            canvas.circle(page_w - 0.55 * inch, page_h - 1.265 * inch, 0.04 * inch, stroke=0, fill=1)
            canvas.setFont("Helvetica-Bold", 9.5)
            canvas.drawCentredString(page_w / 2, page_h - 1.33 * inch, variant_meta["badge"])

        # ── Left decorative side rail (page 1 only, below header) ────────────
        if doc_inner.page == 1:
            rail_x = 0.22 * inch
            rail_top = page_h - 1.55 * inch
            rail_bot = 0.7 * inch
            # Teal ribbon
            canvas.setFillColor(TEAL)
            canvas.rect(rail_x, rail_bot, 0.08 * inch, rail_top - rail_bot, stroke=0, fill=1)
            # Decorative dots
            canvas.setFillColor(AMBER)
            for i, y in enumerate([rail_top - 0.4 * inch, rail_top - 1.2 * inch, rail_top - 2.0 * inch]):
                canvas.circle(rail_x + 0.04 * inch, y, 0.06 * inch, stroke=0, fill=1)
            canvas.setFillColor(INDIGO)
            canvas.circle(rail_x + 0.04 * inch, rail_top - 2.8 * inch, 0.06 * inch, stroke=0, fill=1)

        # ── Footer: teal top divider + content bar ───────────────────────────
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0.48 * inch, page_w, 0.03 * inch, stroke=0, fill=1)
        canvas.setFillColor(SLATE_SOFT)
        canvas.rect(0, 0, page_w, 0.48 * inch, stroke=0, fill=1)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.5 * inch, 0.30 * inch, f"{legal_name}  •  {hq_address}")
        # Page number pill
        pill_x = page_w - 0.95 * inch
        canvas.setFillColor(PRIMARY)
        canvas.roundRect(pill_x, 0.22 * inch, 0.5 * inch, 0.18 * inch, 3, stroke=0, fill=1)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(pill_x + 0.25 * inch, 0.275 * inch, f"Page {doc_inner.page}")
        # Contact
        canvas.setFillColor(PRIMARY)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(0.5 * inch, 0.16 * inch, contact_email)
        if website:
            canvas.setFillColor(TEAL_DEEP)
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(page_w - 0.5 * inch, 0.16 * inch, website)
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawCentredString(page_w / 2, 0.05 * inch,
                                 f"Confidential — intended solely for the named candidate. © {datetime.now(timezone.utc).year} {legal_name}.")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=(1.65 if variant_meta["badge"] else 1.35) * inch,
                            bottomMargin=0.7 * inch,
                            title=f"Official Job Offer - {offer.get('role_title','')}",
                            author=legal_name)

    styles = getSampleStyleSheet()
    h2s = ParagraphStyle("h2s", parent=styles["Heading2"], fontName="Helvetica-Bold",
                         fontSize=11.5, textColor=PRIMARY, spaceBefore=12, spaceAfter=6, leading=14)
    dateS = ParagraphStyle("dateS", parent=styles["BodyText"], fontName="Helvetica",
                           fontSize=9.5, textColor=SLATE, spaceAfter=10)
    subjS = ParagraphStyle("subjS", parent=styles["Heading2"], fontName="Helvetica-Bold",
                           fontSize=13, textColor=INK, spaceBefore=4, spaceAfter=10, leading=16)
    bodyS = ParagraphStyle("bodyS", parent=styles["BodyText"], fontName="Helvetica",
                           fontSize=10.5, textColor=INK, leading=14.5, spaceAfter=7)
    mutedS = ParagraphStyle("mutedS", parent=styles["BodyText"], fontName="Helvetica",
                            fontSize=9, textColor=SLATE, leading=12, spaceAfter=5)
    ParagraphStyle("sigNameS", parent=styles["BodyText"], fontName="Helvetica-Bold",
                              fontSize=11, textColor=INK, leading=14, spaceAfter=2)
    sigTitleS = ParagraphStyle("sigTitleS", parent=styles["BodyText"], fontName="Helvetica",
                               fontSize=10, textColor=SLATE, leading=13, spaceAfter=2)
    ParagraphStyle("sigCursive", parent=styles["BodyText"], fontName="Helvetica-Oblique",
                                fontSize=18, textColor=PRIMARY, leading=22, spaceAfter=2)
    candAddrS = ParagraphStyle("candAddrS", parent=styles["BodyText"], fontName="Helvetica",
                               fontSize=9.5, textColor=SLATE, leading=12.5, spaceAfter=1)

    from reportlab.platypus import KeepTogether
    story = []

    # 2. DATE
    today = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    story.append(Paragraph(today, dateS))

    # 3. CANDIDATE SECTION (single compact block)
    story.append(Paragraph(f"<b>{offer['candidate_name']}</b>", bodyS))
    story.append(Paragraph(str(offer["candidate_address"]).strip(), candAddrS))
    story.append(Spacer(1, 8))

    # 4. SUBJECT LINE
    story.append(Paragraph(f"Subject: Official Job Offer - {offer['role_title']}", subjS))

    # 5. GREETING
    story.append(Paragraph(f"Dear {offer['candidate_name']},", bodyS))

    # 6. BODY CONTENT
    intro = (offer.get("offer_body_md") or "").strip()
    if not intro:
        intro = (f"On behalf of <b>{legal_name}</b>, I am delighted to formally offer you the position of "
                 f"<b>{offer['role_title']}</b> within our <b>{offer['department']}</b> department. "
                 f"Your skills and professional values align outstandingly with the objectives of {brand_name}, "
                 "and we look forward to having you as part of the team.")
    story.append(Paragraph(intro, bodyS))

    if offer.get("personal_message"):
        story.append(Paragraph(offer["personal_message"], bodyS))

    # ── YEAR-1 TOTAL COMPENSATION HERO ──────────────────────────
    from reportlab.platypus import Flowable, Image as RLImage

    class _StackedBar(Flowable):
        def __init__(self, segments: list[tuple[float, Any]], width: float, height: float = 11):
            super().__init__()
            self.segments = [(v, c) for v, c in segments if v > 0]
            self.width = width
            self.height = height

        def draw(self):
            total = sum(v for v, _ in self.segments) or 1.0
            x = 0.0
            for v, color in self.segments:
                w = self.width * (v / total)
                self.canv.setFillColor(color)
                self.canv.rect(x, 0, w, self.height, stroke=0, fill=1)
                x += w

    comp_base = int(offer.get("base_salary_usd") or 0)
    comp_bonus = int(round(comp_base * (int(offer.get("bonus_target_pct") or 0) / 100.0)))
    comp_signing = int(offer.get("signing_bonus_usd") or 0)
    comp_reloc = int(offer.get("relocation_usd") or 0)
    comp_total_y1 = comp_base + comp_bonus + comp_signing + comp_reloc

    heroLabelS = ParagraphStyle("heroLbl", parent=bodyS, fontSize=8, textColor=TEAL_100, leading=10, spaceAfter=0)
    hero_bg = TEAL_DEEP
    hero_label = "YEAR-1 TOTAL COMPENSATION VALUE"
    hero_total_size = 26
    if variant == "declined":
        hero_bg = HexColor("#475569")
        hero_label = "YEAR-1 TOTAL COMPENSATION VALUE — HISTORICAL RECORD"
        hero_total_size = 17
    elif variant == "expired":
        hero_bg = HexColor("#92400E")
        hero_label = "YEAR-1 TOTAL COMPENSATION VALUE — EXPIRED UNACCEPTED"
        hero_total_size = 17
    heroTotalS = ParagraphStyle("heroTotal", parent=bodyS, fontName="Helvetica-Bold", fontSize=hero_total_size,
                                textColor=white, leading=hero_total_size + 4, spaceAfter=0)
    heroLegendS = ParagraphStyle("heroLegend", parent=bodyS, fontSize=8.2, textColor=white, leading=11, spaceAfter=0)

    legend_bits = [f'<font color="#5EEAD4">■</font> Base ${comp_base:,}']
    if comp_bonus:
        legend_bits.append(f'<font color="#A5B4FC">■</font> Bonus target ${comp_bonus:,}')
    if comp_signing:
        legend_bits.append(f'<font color="#FCD34D">■</font> Signing ${comp_signing:,}')
    if comp_reloc:
        legend_bits.append(f'<font color="#FDA4AF">■</font> Relocation ${comp_reloc:,}')
    equity_line = ""
    if offer.get("equity_shares"):
        equity_line = f'&nbsp;&nbsp;<font size="10" color="#CCFBF1">+ <b>{int(offer["equity_shares"]):,} equity shares</b> (standard vesting)</font>'
    elif offer.get("equity_pct"):
        equity_line = f'&nbsp;&nbsp;<font size="10" color="#CCFBF1">+ <b>{offer["equity_pct"]}% equity</b> (standard vesting)</font>'

    hero_rows = [
        [Paragraph(hero_label, heroLabelS)],
        [Paragraph(f"${comp_total_y1:,} <font size='10' color='#CCFBF1'>USD</font>{equity_line}", heroTotalS)],
        [_StackedBar([
            (comp_base, HexColor("#5EEAD4")),
            (comp_bonus, HexColor("#A5B4FC")),
            (comp_signing, HexColor("#FCD34D")),
            (comp_reloc, HexColor("#FDA4AF")),
        ], width=6.3 * inch)],
        [Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(legend_bits), heroLegendS)],
    ]
    if variant == "rescinded":
        hero_rows.append([Paragraph(
            "NO LONGER IN EFFECT — THIS COMPENSATION PACKAGE IS VOID",
            ParagraphStyle("heroVoid", parent=bodyS, fontName="Helvetica-Bold", fontSize=9.5,
                           textColor=white, leading=12, spaceAfter=0, alignment=1))])
    hero_tbl = Table(hero_rows, colWidths=[6.8 * inch])
    hero_style = [
        ("BACKGROUND", (0, 0), (-1, -1), hero_bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("TOPPADDING", (0, 2), (-1, 2), 0), ("BOTTOMPADDING", (0, 2), (-1, 2), 6),
        ("TOPPADDING", (0, 3), (-1, 3), 0), ("BOTTOMPADDING", (0, 3), (-1, 3), 12),
        ("LINEBELOW", (0, -1), (-1, -1), 3, TEAL if variant != "rescinded" else DANGER),
    ]
    if variant == "rescinded":
        hero_style += [
            ("BACKGROUND", (0, 4), (-1, 4), DANGER),
            ("TOPPADDING", (0, 4), (-1, 4), 7), ("BOTTOMPADDING", (0, 4), (-1, 4), 7),
        ]
    hero_tbl.setStyle(TableStyle(hero_style))
    story.append(Spacer(1, 6))
    story.append(hero_tbl)

    # ── OFFER COUNTDOWN RIBBON ──────────────────────────────────
    if offer.get("expires_at") and variant == "original":
        try:
            _exp_dt = datetime.fromisoformat(str(offer["expires_at"]).replace("Z", "+00:00"))
            _days_left = max(0, (_exp_dt - datetime.now(timezone.utc)).days)
            _urgent = _days_left <= 3
            ribbon_bg = HexColor("#FEF3C7") if _urgent else TEAL_50
            ribbon_fg = HexColor("#92400E") if _urgent else TEAL_DEEP
            ribbon_rail = AMBER if _urgent else TEAL
            ribbon_txt = (f"<b>This offer is valid until {str(offer['expires_at'])[:10]}</b> — "
                          f"<b>{_days_left} day{'s' if _days_left != 1 else ''} remaining</b> to accept via your secure candidate portal.")
            ribbon = Table([[Paragraph(ribbon_txt, ParagraphStyle("ribbonS", parent=bodyS, fontSize=9.5, textColor=ribbon_fg, leading=12, spaceAfter=0))]], colWidths=[6.8 * inch])
            ribbon.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), ribbon_bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3, ribbon_rail),
                ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.append(Spacer(1, 6))
            story.append(ribbon)
        except Exception:
            pass

    # ── ACCEPTED RIBBON + START COUNTDOWN ───────────────────────
    if variant == "accepted":
        _accepted_on = (offer.get("responded_at") or "")[:10]
        acc_txt = f"<b>OFFER ACCEPTED</b> — fully executed on <b>{_accepted_on or 'record date'}</b> via secure electronic signature."
        acc_ribbon = Table([[Paragraph(acc_txt, ParagraphStyle("accRibS", parent=bodyS, fontSize=9.5, textColor=SUCCESS, leading=12, spaceAfter=0))]], colWidths=[6.8 * inch])
        acc_ribbon.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), EMERALD_50),
            ("LINEBEFORE", (0, 0), (0, -1), 3, SUCCESS),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(Spacer(1, 6))
        story.append(acc_ribbon)
        try:
            _start_dt = datetime.fromisoformat(str(offer["start_date"])).replace(tzinfo=timezone.utc)
            _days_to_start = (_start_dt - datetime.now(timezone.utc)).days
            if _days_to_start > 0:
                jt = (f"<b>Your journey begins in {_days_to_start} day{'s' if _days_to_start != 1 else ''}</b> — "
                      f"first day <b>{offer['start_date']}</b>. Welcome aboard, {offer['candidate_name'].split(' ')[0]}!")
                j_card = Table([[Paragraph(jt, ParagraphStyle("jS", parent=bodyS, fontSize=9.5, textColor=TEAL_DEEP, leading=12, spaceAfter=0))]], colWidths=[6.8 * inch])
                j_card.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), TEAL_50),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story.append(Spacer(1, 4))
                story.append(j_card)
        except Exception:
            pass

    # ── BENEFITS SNAPSHOT CHIPS ─────────────────────────────────
    chipLblS = ParagraphStyle("chipLbl", parent=bodyS, fontSize=7, textColor=SLATE, leading=9, spaceAfter=0, alignment=1)
    chipValS = ParagraphStyle("chipVal", parent=bodyS, fontName="Helvetica-Bold", fontSize=9.5, textColor=TEAL_DEEP, leading=12, spaceAfter=0, alignment=1)
    chip_loc = (offer.get("work_location") or "").title()
    if offer.get("work_city"):
        chip_loc = f"{chip_loc} · {offer['work_city']}"
    chip_cells = [
        [Paragraph("START DATE", chipLblS), Paragraph("EMPLOYMENT", chipLblS), Paragraph("LOCATION", chipLblS), Paragraph("PAID TIME OFF", chipLblS)],
        [Paragraph(str(offer["start_date"]), chipValS), Paragraph(str(offer["employment_type"]), chipValS),
         Paragraph(chip_loc or "—", chipValS), Paragraph(f"{int(offer.get('pto_days') or 0)} days / yr", chipValS)],
    ]
    chips_tbl = Table(chip_cells, colWidths=[1.7 * inch] * 4)
    chips_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_50),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, TEAL_100),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER_SOFT),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER_SOFT),
    ]))
    story.append(Spacer(1, 6))
    story.append(chips_tbl)

    # Key Employment Terms (colourful card w/ alternating rows)
    story.append(Paragraph('<font color="#14B8A6">■</font>  <font color="#0F766E">Key Employment Terms</font>', h2s))
    key_rows = [
        ["Position Title", offer["role_title"]],
        ["Department", offer["department"]],
        ["Employment Type", offer["employment_type"]],
        ["Start Date", offer["start_date"]],
        ["Compensation (annual base)", f"${int(offer['base_salary_usd']):,} USD"],
    ]
    if offer.get("bonus_target_pct"):
        key_rows.append(["Performance Bonus", f"{offer['bonus_target_pct']}% of annual base (target)"])
    if offer.get("equity_shares"):
        key_rows.append(["Equity Grant", f"{int(offer['equity_shares']):,} shares (standard vesting)"])
    if offer.get("signing_bonus_usd"):
        key_rows.append(["Signing Bonus", f"${int(offer['signing_bonus_usd']):,} USD"])
    if offer.get("relocation_usd"):
        key_rows.append(["Relocation Allowance", f"${int(offer['relocation_usd']):,} USD"])
    if offer.get("pto_days"):
        key_rows.append(["Paid Time Off", f"{offer['pto_days']} days / calendar year"])
    work_loc_str = (offer.get("work_location") or "").title()
    if offer.get("work_city"):
        work_loc_str += f"  •  {offer['work_city']}"
    if work_loc_str:
        key_rows.append(["Work Location", work_loc_str])
    if offer.get("reporting_manager"):
        key_rows.append(["Reporting To", offer["reporting_manager"]])
    if offer.get("expires_at"):
        key_rows.append(["Offer Expires", (offer["expires_at"] or "")[:10]])

    tbl = Table(key_rows, colWidths=[2.1 * inch, 4.7 * inch])
    tbl_style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        # Thick left teal rail
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        # Subtle right outer border
        ("LINEAFTER", (-1, 0), (-1, -1), 0.5, BORDER_SOFT),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER_SOFT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER_SOFT),
    ]
    # Alternating row backgrounds (label col gets soft slate, value col gets teal-50 on evens)
    for i in range(len(key_rows)):
        tbl_style.append(("BACKGROUND", (0, i), (0, i), SLATE_SOFT))
        if i % 2 == 1:
            tbl_style.append(("BACKGROUND", (1, i), (1, i), TEAL_50))
    # Highlight salary row (index 4)
    tbl_style.append(("BACKGROUND", (1, 4), (1, 4), HexColor("#FEF3C7")))  # amber-100
    tbl_style.append(("TEXTCOLOR", (1, 4), (1, 4), HexColor("#92400E")))   # amber-800
    tbl_style.append(("FONTSIZE", (1, 4), (1, 4), 11))
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)

    # 7. TERMS & CONDITIONS (numbered cards with teal badges)
    story.append(Paragraph('<font color="#14B8A6">■</font>  <font color="#0F766E">Terms &amp; Conditions</font>', h2s))
    terms_lines = [
        ("At-Will Employment", f"Employment with {legal_name} is at-will and may be terminated by either party, with or without cause, subject to applicable law."),
        ("Confidentiality &amp; IP", f"You will sign {brand_name}'s standard Confidentiality, Invention Assignment, and Non-Disclosure Agreement before your start date."),
        ("Background &amp; References", "This offer is contingent on successful completion of background and reference checks as permitted by law."),
        ("Work Authorisation", "This offer is contingent on your legal right to work in the jurisdiction of employment."),
        ("Entire Agreement", "This letter is the entire agreement and supersedes any prior representations."),
    ]
    terms_rows = []
    for idx, (title, text) in enumerate(terms_lines, start=1):
        terms_rows.append([
            Paragraph(f'<font color="#14B8A6"><b>{idx}</b></font>', ParagraphStyle("num", parent=bodyS, fontSize=13, textColor=TEAL, alignment=1, leading=15)),
            Paragraph(f"<b>{title}.</b>  {text}", bodyS),
        ])
    terms_tbl = Table(terms_rows, colWidths=[0.35 * inch, 6.45 * inch])
    terms_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), TEAL_50),
        ("LINEBEFORE", (0, 0), (0, -1), 2, TEAL),
        ("LEFTPADDING", (0, 0), (0, -1), 6), ("RIGHTPADDING", (0, 0), (0, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 12), ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER_SOFT),
    ]))
    story.append(terms_tbl)

    # 8. CLOSING STATEMENT — acceptance callout card
    accept_text = (
        f'<font color="#0F766E"><b>Acceptance.</b></font>  '
        f'This offer remains valid until <b>{(offer.get("expires_at") or "")[:10] or "the expiry date shown above"}</b>. '
        'To accept, use the secure candidate portal link in your offer email to record your electronic signature '
        f'in accordance with the <i>E-SIGN Act</i> and <i>eIDAS</i>. We look forward to welcoming you to {brand_name}.'
    )
    accept_para = Paragraph(accept_text, bodyS)
    portal_url = offer.get("public_confirm_url") or ""
    if not portal_url and offer.get("candidate_token"):
        _fe_base = (os.environ.get("FRONTEND_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
        if _fe_base:
            portal_url = f"{_fe_base}/careers/offer/confirm?token={offer['candidate_token']}"
    qr_buf = _offer_qr_png_buffer(portal_url) if (portal_url and variant in ("original", "accepted")) else None
    if qr_buf:
        qr_label = "SCAN TO ACCEPT" if variant == "original" else "SCAN TO VIEW"
        qr_cell = [
            RLImage(qr_buf, width=0.85 * inch, height=0.85 * inch),
            Paragraph(qr_label, ParagraphStyle("qrLbl", parent=mutedS, fontSize=6.5, textColor=TEAL_DEEP, alignment=1, leading=8, spaceAfter=0)),
        ]
        accept_card = Table([[accept_para, qr_cell]], colWidths=[5.55 * inch, 1.25 * inch])
    else:
        accept_card = Table([[accept_para]], colWidths=[6.8 * inch])
    accept_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_50),
        ("LINEBEFORE", (0, 0), (0, -1), 4, TEAL),
        ("LINEABOVE", (0, 0), (-1, 0), 0.3, TEAL_100),
        ("LINEBELOW", (0, -1), (-1, -1), 0.3, TEAL_100),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(Spacer(1, 6))
    story.append(accept_card)

    # Variant-specific footer block
    # Shared: ink-cropped CEO signature flowable builder
    def _make_ceo_sig_flowable() -> Any:
        _sig_src = branding.get("signer_signature_image") or ""
        if not (_sig_src and os.path.exists(_sig_src)):
            return None
        _sig_buf = _cropped_signature_png_buffer(_sig_src)
        if not _sig_buf:
            return None
        try:
            from PIL import Image as _PILImage
            _sig_buf.seek(0)
            with _PILImage.open(_sig_buf) as _probe:
                _aspect = _probe.width / max(1, _probe.height)
            _sig_buf.seek(0)
            _sig_h = 0.52 * inch
            _sig_w = min(2.6 * inch, _sig_h * _aspect)
            _sig_h = _sig_w / _aspect
            return RLImage(_sig_buf, width=_sig_w, height=_sig_h, hAlign="LEFT")
        except Exception:
            return None

    if variant == "accepted" and offer.get("signed_name"):
        # ── FULLY EXECUTED AGREEMENT — dual-signature execution block ──
        exec_hdr = Paragraph(
            '<font color="#FFFFFF"><b>FULLY EXECUTED AGREEMENT — ELECTRONIC SIGNATURE RECORD</b></font>',
            ParagraphStyle("execHdr", parent=sigTitleS, fontSize=9.5, textColor=white, leading=12, alignment=1))
        smallLbl = ParagraphStyle("smallLbl", parent=mutedS, fontSize=7, textColor=SLATE, leading=9, spaceAfter=3)
        companyCell = [
            Paragraph(f"FOR {legal_name.upper()}", smallLbl),
        ]
        _ceo_sig = _make_ceo_sig_flowable()
        if _ceo_sig is not None:
            companyCell.append(_ceo_sig)
        companyCell.append(Paragraph(
            f'<font color="#0F172A"><b>{signer_name}</b></font><br/>'
            f'<font color="#475569">{signer_title}</font>',
            ParagraphStyle("execCo", parent=sigTitleS, fontSize=9.5, textColor=INK, leading=13)))
        candCell = [
            Paragraph("CANDIDATE", smallLbl),
            Paragraph(f'<font color="#047857"><i>{offer.get("signed_name","")}</i></font>',
                      ParagraphStyle("candScript", parent=sigTitleS, fontName="Helvetica-BoldOblique",
                                     fontSize=17, textColor=SUCCESS, leading=21, spaceAfter=4)),
            Paragraph(
                f'Signed <b>{(offer.get("responded_at") or "")[:19].replace("T", " ")} UTC</b><br/>'
                f'IP {offer.get("response_ip") or "-"}<br/>'
                f'SHA-256 {(offer.get("signed_hash") or "")[:32]}…',
                ParagraphStyle("candMeta", parent=mutedS, fontSize=7.5, textColor=SLATE, leading=10)),
        ]
        exec_tbl = Table([[exec_hdr, ""], [companyCell, candCell]],
                         colWidths=[3.4 * inch, 3.4 * inch])
        exec_tbl.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), SUCCESS),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, 1), HexColor("#F7FEFB")),
            ("VALIGN", (0, 1), (-1, 1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 1), (-1, 1), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("LINEAFTER", (0, 1), (0, 1), 0.6, HexColor("#6EE7B7")),
            ("LINEBELOW", (0, -1), (-1, -1), 3, SUCCESS),
            ("LINEBEFORE", (0, 0), (0, -1), 0.6, BORDER_SOFT),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.6, BORDER_SOFT),
        ]))
        story.append(KeepTogether([Spacer(1, 14), exec_tbl]))
    elif variant == "declined":
        # ── RESPECTFUL CLOSURE CARD ──
        dec_hdr = Paragraph('<font color="#FFFFFF"><b>CANDIDATE RESPONSE — RESPECTFULLY DECLINED</b></font>',
                            ParagraphStyle("decHdr", parent=sigTitleS, fontSize=9.5, textColor=white, leading=12))
        dec_body_parts = [f"The candidate respectfully declined this offer on <b>{(offer.get('responded_at') or '')[:10] or 'record date'}</b>."]
        dec_body = [Paragraph(" ".join(dec_body_parts), bodyS)]
        if offer.get("decline_reason"):
            dec_body.append(Paragraph(f'<i>“{offer.get("decline_reason")}”</i>',
                                      ParagraphStyle("decQuote", parent=bodyS, fontName="Helvetica-Oblique",
                                                     fontSize=10, textColor=SLATE, leading=13, leftIndent=10)))
        dec_body.append(Paragraph(
            f"<b>The door remains open.</b> {brand_name} would welcome the opportunity to reconnect for future roles — "
            "the candidate remains part of our talent network with our best wishes.",
            ParagraphStyle("decGoodwill", parent=bodyS, fontSize=9.5, textColor=TEAL_DEEP, leading=12.5)))
        dec_tbl = Table([[dec_hdr], [dec_body]], colWidths=[6.8 * inch])
        dec_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#475569")),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, 1), SLATE_SOFT),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 1), (-1, 1), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("LINEBELOW", (0, -1), (-1, -1), 3, HexColor("#94A3B8")),
            ("LINEBEFORE", (0, 0), (0, -1), 0.6, BORDER_SOFT),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.6, BORDER_SOFT),
        ]))
        story.append(KeepTogether([Spacer(1, 14), dec_tbl]))
    elif variant == "rescinded":
        # ── FORMAL RESCISSION NOTICE ──
        res_hdr = Paragraph('<font color="#FFFFFF"><b>FORMAL RESCISSION NOTICE</b></font>',
                            ParagraphStyle("resHdr", parent=sigTitleS, fontSize=9.5, textColor=white, leading=12))
        res_body = [Paragraph(
            f"This offer has been rescinded by <b>{legal_name}</b> on <b>{(offer.get('rescinded_at') or '')[:10] or 'record date'}</b> "
            "and is no longer in effect.", bodyS)]
        if offer.get("rescind_reason"):
            res_body.append(Paragraph(f"<b>Reason:</b> {offer.get('rescind_reason')}", bodyS))
        res_body.append(Paragraph(
            "<b>Legal effect.</b> Effective immediately, this offer letter and all prior versions, drafts, and "
            "communications relating to it are void and of no further force or effect. No acceptance, reliance, or "
            "action taken after the rescission date creates any obligation on the company.",
            ParagraphStyle("resLegal", parent=bodyS, fontSize=9.5, textColor=DANGER, leading=12.5)))
        res_tbl = Table([[res_hdr], [res_body]], colWidths=[6.8 * inch])
        res_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DANGER),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, 1), HexColor("#FEF2F2")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 1), (-1, 1), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("LINEBELOW", (0, -1), (-1, -1), 3, DANGER),
            ("LINEBEFORE", (0, 0), (0, -1), 0.6, BORDER_SOFT),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.6, BORDER_SOFT),
        ]))
        story.append(KeepTogether([Spacer(1, 14), res_tbl]))
    elif variant == "expired":
        # ── OFFER EXPIRATION NOTICE ──
        exp_hdr = Paragraph('<font color="#FFFFFF"><b>OFFER EXPIRATION NOTICE</b></font>',
                            ParagraphStyle("expHdr", parent=sigTitleS, fontSize=9.5, textColor=white, leading=12))
        exp_on = (offer.get("expires_at") or "")[:10] or "record date"
        exp_body = [Paragraph(
            f"This offer expired on <b>{exp_on}</b> without acceptance. The validity window defined in the "
            "original offer letter has passed and no candidate action was recorded before the deadline.", bodyS)]
        exp_body.append(Paragraph(
            "<b>Effect of expiration.</b> This offer letter is no longer capable of acceptance. Any subsequent "
            "acceptance attempt has no legal effect and creates no obligation on the company.",
            ParagraphStyle("expLegal", parent=bodyS, fontSize=9.5, textColor=HexColor("#92400E"), leading=12.5)))
        exp_body.append(Paragraph(
            f"<b>The door remains open.</b> {brand_name} would welcome a conversation about current openings — "
            "an expired offer does not close the relationship, and the candidate remains part of our talent network.",
            ParagraphStyle("expGoodwill", parent=bodyS, fontSize=9.5, textColor=TEAL_DEEP, leading=12.5)))
        exp_tbl = Table([[exp_hdr], [exp_body]], colWidths=[6.8 * inch])
        exp_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#B45309")),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, 1), HexColor("#FFFBEB")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 1), (-1, 1), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("LINEBELOW", (0, -1), (-1, -1), 3, AMBER),
            ("LINEBEFORE", (0, 0), (0, -1), 0.6, BORDER_SOFT),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.6, BORDER_SOFT),
        ]))
        story.append(KeepTogether([Spacer(1, 14), exp_tbl]))

    # 9. SIGNATURE BLOCK — company signature (skipped on accepted: dual execution block above covers it)
    if variant != "accepted" or not offer.get("signed_name"):
        sig_label = Paragraph(
            f'<font color="#FFFFFF"><b>Signed by {legal_name}</b></font>',
            ParagraphStyle("sigLbl", parent=sigTitleS, fontSize=9.5, textColor=white, leading=12))
        sig_body = Paragraph(
            f'<font color="#0F172A"><b>{signer_name}</b></font><br/>'
            f'<font color="#475569">{signer_title}</font><br/>'
            f'<font color="#0F766E"><b>{legal_name}</b></font>',
            ParagraphStyle("sigBody", parent=sigTitleS, fontSize=10.5, textColor=INK, leading=15))

        sig_img_flowable = _make_ceo_sig_flowable()

        sig_rows = [[sig_label]]
        if sig_img_flowable is not None:
            sig_rows.append([sig_img_flowable])
        sig_rows.append([sig_body])

        sig_box = Table(sig_rows, colWidths=[3.4 * inch])
        _sig_last = len(sig_rows) - 1
        sig_box.setStyle(TableStyle([
            # Header ribbon (primary)
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("LEFTPADDING", (0, 0), (-1, 0), 12), ("RIGHTPADDING", (0, 0), (-1, 0), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            # Body card (white with teal border)
            ("BACKGROUND", (0, 1), (-1, _sig_last), white),
            ("LEFTPADDING", (0, 1), (-1, _sig_last), 14), ("RIGHTPADDING", (0, 1), (-1, _sig_last), 14),
            ("TOPPADDING", (0, 1), (-1, 1), 12), ("BOTTOMPADDING", (0, _sig_last), (-1, _sig_last), 14),
            ("ALIGN", (0, 1), (-1, _sig_last), "LEFT"),
            ("LINEBELOW", (0, _sig_last), (-1, _sig_last), 3, TEAL),
            ("LINEBEFORE", (0, 0), (0, -1), 0.6, BORDER_SOFT),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.6, BORDER_SOFT),
        ]))
        sig_elements = [Spacer(1, 18), sig_box]
        story.append(KeepTogether(sig_elements))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


async def _persist_pdf(offer_id: str, pdf_bytes: bytes, variant: str = "original") -> tuple[str, str]:
    """Write PDF to disk, return (relative_path, sha256_hex)."""
    filename = build_pdf_v15_filename("job-offer", f"{offer_id}-{variant}")
    path = OFFERS_DIR / filename
    path.write_bytes(pdf_bytes)
    return (f"uploads/offers/{filename}", hashlib.sha256(pdf_bytes).hexdigest())


# ── Admin endpoints ──────────────────────────────────────────
# ── Offer branding config (signer, legal name, HQ address) ───
class OfferBrandingBody(BaseModel):
    brand_name: str | None = None
    company_info: str | None = None  # official contact email shown on the PDF
    legal_name: str | None = None
    hq_address: str | None = None
    signer_name: str | None = None
    signer_title: str | None = None
    signer_board_note: str | None = None
    signer_signature_image: str | None = None  # /api/static/... path or public URL


@router.get("/careers/offer-branding")
async def admin_get_offer_branding(request: Request):
    """Return merged offer branding (receipt_branding + offer_branding)."""
    await _require_admin(request)
    b = await _load_offer_branding()
    # Hide internal fields
    return {"success": True, "branding": b}


@router.put("/careers/offer-branding")
async def admin_put_offer_branding(request: Request, body: OfferBrandingBody):
    admin = await _require_admin(request)
    value = {k: v for k, v in body.model_dump().items() if v is not None}
    if not value:
        raise HTTPException(status_code=400, detail="At least one field required")
    # ZERO ASSUMPTIONS POLICY: reject fabricated tokens at the write boundary.
    # No admin — not even the platform owner — may persist a fabricated identity.
    blob = " \u0000 ".join(str(v) for v in value.values())
    bad = [t for t in _FORBIDDEN_FABRICATION_TOKENS if t in blob]
    if bad:
        logger.error("[ZERO-ASSUMPTIONS] Refused PUT /careers/offer-branding: fabricated tokens=%s", bad)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ZERO_ASSUMPTIONS_VIOLATION",
                "fabricated_tokens": bad,
                "message": (
                    "This value contains fabricated platform-identity data and is blocked "
                    "by the Zero Assumptions Policy. See /app/memory/ZERO_ASSUMPTIONS_POLICY.md."
                ),
            },
        )
    value["updated_at"] = _now_iso()
    existing = await db.settings.find_one({"key": "offer_branding"}, {"_id": 0})
    merged_value = {**((existing or {}).get("value") or {}), **value}
    await db.settings.update_one(
        {"key": "offer_branding"},
        {"$set": {"key": "offer_branding", "value": merged_value, "updated_at": _now_iso(),
                   "updated_by": getattr(admin, "email", None)}},
        upsert=True,
    )
    merged = await _load_offer_branding()
    return {"success": True, "branding": merged}


@router.post("/careers/offer-branding/seed-demo")
async def admin_seed_demo_offer_branding(request: Request):
    """Preview-parity seed: populate offer_branding with the canonical
    RealAICoach values so the full offer-draft → send → PDF flow can be
    exercised end-to-end in preview / staging WITHOUT manually filling every
    field. Safe — writes only if no doc exists OR if the existing doc is
    the placeholder default; never overrides a real admin-configured doc."""
    admin = await _require_admin(request)

    try:
        from routes.ai_learning_hub import (
            CERTIFICATE_SIGNER_NAME as _seed_ceo,
            CERTIFICATE_SIGNER_ROLE as _seed_ceo_role,
        )
    except Exception:
        _seed_ceo, _seed_ceo_role = "", ""

    # Keys below are EXACTLY what _load_offer_branding/_generate_offer_pdf read.
    canonical = {
        "brand_name": "RealAICoach",
        "legal_name": _PLATFORM_LEGAL_NAME,
        "hq_address": _PLATFORM_HQ_ADDRESS,
        "company_info": "security@realaicoach.app",
        "signer_name": _seed_ceo,
        "signer_title": _seed_ceo_role or "Chief Executive Officer (CEO)",
    }
    canonical = {k: v for k, v in canonical.items() if v}

    # Defensive: canonical values must themselves pass the Zero-Assumptions guard.
    _assert_no_fabrication(canonical)

    existing = await db.settings.find_one({"key": "offer_branding"}, {"_id": 0})
    was_present = bool(existing and existing.get("value"))
    if was_present:
        prev_val = existing.get("value") or {}
        # If the admin has already set ANY field to a non-canonical value, do not overwrite.
        admin_customized = any(
            prev_val.get(k) and prev_val.get(k) != canonical.get(k)
            for k in canonical
        )
        if admin_customized:
            return {
                "success": True,
                "skipped": True,
                "reason": "admin_already_customized",
                "branding": await _load_offer_branding(),
            }

    now = _now_iso()
    await db.settings.update_one(
        {"key": "offer_branding"},
        {"$set": {
            "key": "offer_branding",
            "value": {**canonical, "updated_at": now, "seeded_demo": True},
            "updated_at": now,
            "updated_by": getattr(admin, "email", None),
            "seeded_demo": True,
        }},
        upsert=True,
    )
    merged = await _load_offer_branding()
    return {
        "success": True,
        "seeded": True,
        "was_present": was_present,
        "branding": merged,
    }


@router.post("/careers/offers/draft")
async def admin_create_draft(request: Request, body: OfferDraftBody):
    admin = await _require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": body.application_id}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    offer_id = f"off_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    doc = {
        "offer_id": offer_id,
        "application_id": body.application_id,
        "candidate_name": app_doc.get("name") or app_doc.get("full_name") or "",
        "candidate_email": app_doc.get("email") or "",
        "role_title": app_doc.get("role_title") or app_doc.get("position") or "",
        "state": "draft",
        **body.model_dump(),
        "created_at": now, "updated_at": now,
        "created_by": getattr(admin, "email", None) or getattr(admin, "user_id", None),
        "events": [{"ts": now, "type": "draft_created", "meta": {}}],
        "view_count": 0, "open_count": 0,
        "sent_at": None, "expires_at": None,
        "viewed_at_first": None, "opened_at_first": None,
        "responded_at": None, "response_ip": None, "response_ua": None,
        "signed_name": None, "signed_hash": None,
        "decline_reason": None,
        "rescind_reason": None, "rescinded_at": None, "rescinded_by": None,
        "candidate_token": None, "public_confirm_url": None,
        "pdf_path": None, "pdf_hash": None,
        "pdf_variant": None,
        "pdf_theme_signature": None,
    }
    await db[OFFERS_COL].insert_one(doc)
    return {"success": True, **_clean(doc)}


@router.patch("/careers/offers/{offer_id}")
async def admin_patch_offer(request: Request, offer_id: str, body: OfferPatchBody):
    await _require_admin(request)
    offer = await _get_offer_or_404(offer_id)
    if offer["state"] not in ("draft",):
        raise HTTPException(status_code=409, detail=f"Cannot edit an offer in state '{offer['state']}'")
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        return {"success": True, **offer}
    update["updated_at"] = _now_iso()
    await db[OFFERS_COL].update_one({"offer_id": offer_id}, {"$set": update})
    fresh = await _get_offer_or_404(offer_id)
    return {"success": True, **fresh}


@router.post("/careers/offers/{offer_id}/ai-draft-body")
async def admin_ai_draft_body(request: Request, offer_id: str, body: AIDraftBody):
    await _require_admin(request)
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    offer = await _get_offer_or_404(offer_id)

    tone_hint = {
        "professional": "Warm, formal, concise. Modern SaaS company voice.",
        "warm": "Warm and human, show genuine excitement about the candidate joining.",
        "celebratory": "Celebratory and enthusiastic without being over-the-top.",
    }.get(body.tone, "Warm, formal, concise. Modern SaaS company voice.")

    prompt = f"""Write the BODY of an enterprise offer letter from RealAICoach to a candidate.

Candidate name: {offer.get('candidate_name','')}
Role: {offer.get('role_title','')}
Work location: {offer.get('work_location','remote')}
Base salary (USD): {offer.get('base_salary_usd',0)}
Target bonus (% of base): {offer.get('bonus_target_pct',0)}
Start date: {offer.get('start_date','')}
Tone: {tone_hint}

Rules:
- 120–180 words total.
- 2–3 short paragraphs.
- Open with excitement about them joining.
- DO NOT include the comp numbers (they're rendered elsewhere in a table).
- DO NOT include generic corporate filler.
- End with a clear "we look forward" close.
- No markdown, no emojis, no salutation (no "Dear X") — that's added separately.
- Plain prose only.

Return STRICT JSON: {{"body": "..."}}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"offer-{offer_id[-6:]}-{uuid.uuid4().hex[:6]}",
                        system_message="You write elegant, personal enterprise offer letter bodies. Return only the JSON specified.")
                .with_model("anthropic", "claude-sonnet-4-5-20250929"))
        t0 = time.time()
        response = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=25.0)
        latency_ms = int((time.time() - t0) * 1000)
        text = response.text if hasattr(response, "text") else str(response)
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        note = (parsed.get("body") or "").strip()
        if not note:
            raise ValueError("Empty body in AI response")
        try:
            from services.llm_usage_logger import log_llm_call
            await log_llm_call(model="claude-sonnet-4-5-20250929", provider="anthropic",
                               feature="careers-ai-offer-body", user_id=None,
                               session_id=f"offer-{offer_id[-6:]}",
                               prompt_text=prompt, response_text=text, latency_ms=latency_ms, success=True)
        except Exception:
            pass
        return {"success": True, "body": note, "tone": body.tone}
    except Exception as e:
        logger.warning(f"[offers] ai-draft-body failed for {offer_id}: {e}")
        raise HTTPException(status_code=502, detail="AI drafting failed — please try again")


@router.post("/careers/offers/{offer_id}/send")
async def admin_send_offer(request: Request, offer_id: str):
    await _require_admin(request)
    offer = await _get_offer_or_404(offer_id)
    if offer["state"] != "draft":
        raise HTTPException(status_code=409, detail=f"Only drafts can be sent (current: {offer['state']})")
    if not offer.get("candidate_email"):
        raise HTTPException(status_code=400, detail="Candidate email missing")
    if not offer.get("base_salary_usd"):
        raise HTTPException(status_code=400, detail="Base salary required before sending")

    now_dt = datetime.now(timezone.utc)
    expires_at = (now_dt + timedelta(days=int(offer.get("expiry_days") or 5))).isoformat()
    candidate_token = secrets.token_urlsafe(32)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    public_confirm_url = f"{scheme}://{host}/careers/offer/confirm?token={candidate_token}"

    # Build PDF (original) — token/portal URL included so the QR renders on the first-sent letter
    offer_for_pdf = {**offer, "expires_at": expires_at,
                     "candidate_token": candidate_token, "public_confirm_url": public_confirm_url}
    _branding = await _load_offer_branding()
    try:
        pdf_bytes = _generate_offer_pdf(offer_for_pdf, variant="original", branding=_branding)
    except OfferDataValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "BRANDING_INCOMPLETE", "missing": e.missing,
                    "message": "Cannot send offer — configure Offer Branding (Legal Name, HQ Address, CEO, Logo) before sending.",
                    "fix_url": f"/admin/offer-studio?offerId={offer_id}&panel=branding"},
        )
    pdf_path, pdf_hash = await _persist_pdf(offer_id, pdf_bytes, "original")

    update = {
        "state": "sent",
        "sent_at": now_dt.isoformat(),
        "expires_at": expires_at,
        "candidate_token": candidate_token,
        "public_confirm_url": public_confirm_url,
        "pdf_path": pdf_path,
        "pdf_hash": pdf_hash,
        "pdf_variant": "original",
        "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
        **_append_event(offer, "sent", {"expires_at": expires_at}),
    }
    await db[OFFERS_COL].update_one({"offer_id": offer_id}, {"$set": update})

    # Send email via career_offer_sent template
    tracking_pixel = f"{scheme}://{host}/api/careers/offers/public/{candidate_token}/pixel.gif"
    email_sent = False
    email_error: str | None = None
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        builder = TEMPLATE_CATALOG["career_offer_sent"]["builder"]
        tpl = builder(
            applicant_name=offer.get("candidate_name", ""),
            role_title=offer.get("role_title", ""),
            base_salary_usd=offer.get("base_salary_usd", 0),
            start_date=offer.get("start_date", ""),
            expires_at=expires_at[:10],
            confirm_url=public_confirm_url,
            personal_message=offer.get("personal_message", ""),
            tracking_pixel_url=tracking_pixel,
        )
        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        result = await send_email(
            recipient_email=offer["candidate_email"],
            recipient_name=offer.get("candidate_name"),
            subject=tpl.subject,
            content=tpl.html,
            content_text=tpl.text,
            template_key="career_offer_sent",
            attachments=[{
                "filename": build_pdf_v15_filename("job-offer", offer.get("offer_id") or offer.get("role_title") or "role"),
                "content": pdf_b64,
                "content_type": "application/pdf",
            }],
        )
        email_sent = bool(result and result.get("success"))
        if not email_sent:
            email_error = (result or {}).get("error") or "send failed"
    except Exception as e:
        email_error = str(e)[:160]
        logger.warning(f"[offers] send email failed for {offer_id}: {e}")

    # Fire-and-forget Slack/Teams ping
    asyncio.ensure_future(_ping_recruiter(request, offer_id,
        event_type="career_offer_sent",
        severity="info",
        title="📄 Offer sent to candidate",
        summary=f"Offer sent to {offer.get('candidate_name','')} for {offer.get('role_title','')}",
        fields={
            "Candidate": f"{offer.get('candidate_name','')} <{offer.get('candidate_email','')}>",
            "Role": offer.get("role_title", ""),
            "Base": _fmt_money(offer.get("base_salary_usd", 0)),
            "Expires": expires_at[:10],
        }))

    fresh = await _get_offer_or_404(offer_id)
    return {"success": True, "email_sent": email_sent, "email_error": email_error, **fresh}


@router.post("/careers/offers/{offer_id}/rescind")
async def admin_rescind_offer(request: Request, offer_id: str, body: RescindBody):
    admin = await _require_admin(request)
    offer = await _get_offer_or_404(offer_id)
    if offer["state"] in ("rescinded", "expired", "declined"):
        raise HTTPException(status_code=409, detail=f"Cannot rescind from state '{offer['state']}'")
    now = _now_iso()
    # Build rescinded PDF variant
    offer_for_pdf = {**offer, "rescind_reason": body.reason, "rescinded_at": now}
    _branding = await _load_offer_branding()
    try:
        pdf_bytes = _generate_offer_pdf(offer_for_pdf, variant="rescinded", branding=_branding)
    except OfferDataValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "BRANDING_INCOMPLETE", "missing": e.missing,
                    "message": "Cannot generate rescission PDF — Offer Branding incomplete.",
                    "fix_url": f"/admin/offer-studio?offerId={offer_id}&panel=branding"},
        )
    pdf_path, pdf_hash = await _persist_pdf(offer_id, pdf_bytes, "rescinded")
    update = {
        "state": "rescinded",
        "rescind_reason": body.reason,
        "rescinded_at": now,
        "rescinded_by": getattr(admin, "email", None) or getattr(admin, "user_id", None),
        "pdf_path": pdf_path,
        "pdf_hash": pdf_hash,
        "pdf_variant": "rescinded",
        "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
        **_append_event(offer, "rescinded", {"reason": body.reason}),
    }
    await db[OFFERS_COL].update_one({"offer_id": offer_id}, {"$set": update})
    # Email
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        tpl = TEMPLATE_CATALOG["career_offer_rescinded"]["builder"](
            applicant_name=offer.get("candidate_name", ""),
            role_title=offer.get("role_title", ""),
            reason=body.reason,
        )
        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        await send_email(
            recipient_email=offer["candidate_email"],
            recipient_name=offer.get("candidate_name"),
            subject=tpl.subject,
            content=tpl.html,
            content_text=tpl.text,
            template_key="career_offer_rescinded",
            attachments=[{
                "filename": build_pdf_v15_filename("job-offer", f"rescinded-{offer_id}"),
                "content": pdf_b64,
                "content_type": "application/pdf",
            }],
        )
    except Exception as e:
        logger.warning(f"[offers] rescind email failed: {e}")
    asyncio.ensure_future(_ping_recruiter(request, offer_id,
        event_type="career_offer_rescinded",
        severity="warning",
        title="🛑 Offer rescinded",
        summary=f"Rescinded offer to {offer.get('candidate_name','')} — {body.reason[:80]}",
        fields={"Candidate": offer.get("candidate_name", ""), "Reason": body.reason[:160]}))
    fresh = await _get_offer_or_404(offer_id)
    return {"success": True, **fresh}


@router.get("/careers/offers")
async def admin_list_offers(request: Request, state: str | None = None, application_id: str | None = None):
    await _require_admin(request)
    q: dict[str, Any] = {}
    if state:
        q["state"] = state
    if application_id:
        q["application_id"] = application_id
    items = []
    async for d in db[OFFERS_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(200):
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/careers/offers/benchmark")
async def admin_benchmark(request: Request, role_title: str | None = None, work_location: str | None = None):
    await _require_admin(request)
    q: dict[str, Any] = {"state": {"$in": ["sent", "accepted", "declined", "expired", "rescinded"]}}
    if role_title:
        q["role_title"] = role_title
    if work_location:
        q["work_location"] = work_location
    salaries: list[int] = []
    accepted = 0
    total = 0
    start_days: list[int] = []
    async for d in db[OFFERS_COL].find(q, {"_id": 0, "base_salary_usd": 1, "state": 1, "start_date": 1, "sent_at": 1}):
        total += 1
        if d.get("base_salary_usd"):
            salaries.append(int(d["base_salary_usd"]))
        if d.get("state") == "accepted":
            accepted += 1
        try:
            if d.get("start_date") and d.get("sent_at"):
                sd = datetime.fromisoformat(d["start_date"] + "T00:00:00+00:00")
                snt = datetime.fromisoformat(d["sent_at"].replace("Z", "+00:00"))
                start_days.append(max(0, (sd - snt).days))
        except Exception:
            pass
    if not salaries:
        return {"total": 0, "salary_median": 0, "salary_p25": 0, "salary_p75": 0,
                "acceptance_rate": 0.0, "median_start_days": 0, "has_data": False}
    s = sorted(salaries)

    def _pct(pct: float) -> int:
        if not s:
            return 0
        k = max(0, min(len(s) - 1, int(round((pct/100) * (len(s)-1)))))
        return int(s[k])

    median_start = 0
    if start_days:
        sd = sorted(start_days)
        median_start = int(sd[len(sd) // 2])
    return {
        "total": total,
        "salary_median": _pct(50),
        "salary_p25": _pct(25),
        "salary_p75": _pct(75),
        "salary_min": int(s[0]),
        "salary_max": int(s[-1]),
        "acceptance_rate": round(100.0 * accepted / total, 1) if total else 0.0,
        "median_start_days": median_start,
        "has_data": True,
    }


@router.get("/careers/offers/{offer_id}")
async def admin_get_offer(request: Request, offer_id: str):
    await _require_admin(request)
    offer = await _get_offer_or_404(offer_id)
    return {"success": True, **offer}


@router.get("/careers/offers/{offer_id}/pdf")
async def admin_get_offer_pdf(request: Request, offer_id: str):
    await _require_admin(request)
    offer = await _get_offer_or_404(offer_id)
    try:
        offer = await _ensure_offer_pdf_current_theme(offer)
    except OfferDataValidationError as e:
        has_branding = any(m.startswith(("company.", "executive.")) for m in e.missing)
        has_candidate = any(m.startswith("candidate.") for m in e.missing)
        if has_branding and has_candidate:
            msg = "Cannot generate PDF — Offer Branding AND candidate data incomplete."
        elif has_branding:
            msg = "Cannot generate PDF — configure Offer Branding (Legal Name, HQ Address, CEO, Logo) in Offer Studio → Branding."
        else:
            msg = "Cannot generate PDF — complete the candidate fields in the Offer builder (address, department, start date, salary, employment type)."
        raise HTTPException(
            status_code=422,
            detail={"code": "BRANDING_INCOMPLETE" if has_branding else "OFFER_INCOMPLETE",
                    "missing": e.missing, "message": msg,
                    "fix_url": (f"/admin/offer-studio?offerId={offer_id}&panel=branding" if has_branding else None)},
        )
    full = Path("/app/backend") / offer["pdf_path"]
    if not full.exists():
        raise HTTPException(status_code=404, detail="PDF not found on disk")
    return FileResponse(str(full), media_type="application/pdf",
                        filename=build_pdf_v15_filename("job-offer", offer_id))


@router.get("/careers/offer-templates")
async def list_templates(request: Request):
    await _require_admin(request)
    items = []
    async for d in db[OFFER_TEMPLATES_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(50):
        items.append(d)
    return {"items": items}


@router.post("/careers/offer-templates")
async def save_template(request: Request, body: TemplateSaveBody):
    admin = await _require_admin(request)
    tid = f"tpl_{uuid.uuid4().hex[:10]}"
    now = _now_iso()
    doc = {"template_id": tid, **body.model_dump(), "created_at": now,
           "owner_email": getattr(admin, "email", None)}
    await db[OFFER_TEMPLATES_COL].insert_one(doc)
    return {"success": True, **_clean(doc)}


@router.delete("/careers/offer-templates/{tid}")
async def delete_template(request: Request, tid: str):
    await _require_admin(request)
    r = await db[OFFER_TEMPLATES_COL].delete_one({"template_id": tid})
    return {"success": r.deleted_count > 0}


# ── Public endpoints (token) ─────────────────────────────────
def _public_view(offer: dict[str, Any]) -> dict[str, Any]:
    # Return only what the candidate should see
    keys = [
        "offer_id", "candidate_name", "role_title", "state",
        "base_salary_usd", "bonus_target_pct", "equity_shares", "equity_pct",
        "signing_bonus_usd", "relocation_usd", "pto_days",
        "start_date", "reporting_manager", "work_location", "work_city",
        "expires_at", "sent_at", "responded_at", "signed_name", "decline_reason",
        "rescind_reason", "rescinded_at", "personal_message", "offer_body_md",
    ]
    return {k: offer.get(k) for k in keys}


@router.get("/careers/offers/public/{token}")
async def public_get_offer(token: str, request: Request):
    offer = await _find_by_candidate_token(token)
    # Increment view count, flag first view
    update: dict[str, Any] = {"view_count": int(offer.get("view_count", 0)) + 1, "updated_at": _now_iso()}
    if not offer.get("viewed_at_first"):
        update["viewed_at_first"] = _now_iso()
        update["events"] = (offer.get("events") or []) + [{"ts": _now_iso(), "type": "viewed_first", "meta": {"ip": request.client.host if request.client else None}}]
        # Ping on first view
        asyncio.ensure_future(_ping_recruiter(request, offer["offer_id"],
            event_type="career_offer_viewed",
            severity="info",
            title="👀 Candidate viewed their offer",
            summary=f"{offer.get('candidate_name','Candidate')} opened the offer page.",
            fields={"Candidate": offer.get("candidate_name", ""), "Role": offer.get("role_title", "")}))
    if offer.get("state") == "sent":
        try:
            if offer.get("expires_at") and datetime.now(timezone.utc) > datetime.fromisoformat(offer["expires_at"].replace("Z", "+00:00")):
                update["state"] = "expired"
                update["events"] = (update.get("events") or offer.get("events") or []) + [{"ts": _now_iso(), "type": "auto_expired_on_view", "meta": {}}]
        except Exception:
            pass
    await db[OFFERS_COL].update_one({"offer_id": offer["offer_id"]}, {"$set": update})
    fresh = await _get_offer_or_404(offer["offer_id"])
    return {"success": True, **_public_view(fresh)}


@router.post("/careers/offers/public/{token}/accept")
async def public_accept_offer(token: str, body: PublicAcceptBody, request: Request):
    offer = await _find_by_candidate_token(token)
    if offer["state"] not in ("sent",):
        raise HTTPException(status_code=409, detail=f"Offer is {offer['state']} — cannot accept")
    if not body.acknowledge_terms:
        raise HTTPException(status_code=400, detail="You must acknowledge the terms to accept")
    now = _now_iso()
    ip = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:200]
    sig_payload = f"{offer['offer_id']}|{body.signed_name.strip()}|{now}|{ip}|{ua}"
    signed_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()

    # Re-generate PDF with acceptance stamp
    offer_for_pdf = {**offer, "signed_name": body.signed_name.strip(), "signed_hash": signed_hash,
                     "response_ip": ip, "response_ua": ua, "responded_at": now}
    _branding = await _load_offer_branding()
    try:
        pdf_bytes = _generate_offer_pdf(offer_for_pdf, variant="accepted", branding=_branding)
    except OfferDataValidationError as e:
        logger.error(f"[offers] accept PDF generation failed for {offer['offer_id']}: missing={e.missing}")
        raise HTTPException(status_code=500, detail="Offer countersignature unavailable — please contact the recruiting team.")
    pdf_path, pdf_hash = await _persist_pdf(offer["offer_id"], pdf_bytes, "accepted")

    update = {
        "state": "accepted", "responded_at": now,
        "signed_name": body.signed_name.strip(), "signed_hash": signed_hash,
        "response_ip": ip, "response_ua": ua,
        "pdf_path": pdf_path, "pdf_hash": pdf_hash,
        "pdf_variant": "accepted",
        "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
        **_append_event(offer, "accepted", {"ip": ip, "signed_name": body.signed_name.strip()}),
    }
    await db[OFFERS_COL].update_one({"offer_id": offer["offer_id"]}, {"$set": update})
    # Also advance the application status to offer/hired stay 'offer' for now
    try:
        await db[APPS_COL].update_one(
            {"application_id": offer["application_id"]},
            {"$set": {"status": "offer", "status_updated_at": now}},
        )
    except Exception:
        pass
    # Email confirmation
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        tpl = TEMPLATE_CATALOG["career_offer_accepted"]["builder"](
            applicant_name=offer.get("candidate_name", ""),
            role_title=offer.get("role_title", ""),
            start_date=offer.get("start_date", ""),
        )
        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        await send_email(
            recipient_email=offer["candidate_email"], recipient_name=offer.get("candidate_name"),
            subject=tpl.subject, content=tpl.html, content_text=tpl.text,
            template_key="career_offer_accepted",
            attachments=[{
                "filename": build_pdf_v15_filename("job-offer", f"signed-{offer['offer_id']}"),
                "content": pdf_b64, "content_type": "application/pdf",
            }],
        )
    except Exception as e:
        logger.warning(f"[offers] accept email failed: {e}")
    asyncio.ensure_future(_ping_recruiter(request, offer["offer_id"],
        event_type="career_offer_accepted", severity="info",
        title="🎉 Offer ACCEPTED!",
        summary=f"{offer.get('candidate_name','Candidate')} just signed the offer for {offer.get('role_title','')}.",
        fields={"Candidate": offer.get("candidate_name", ""), "Role": offer.get("role_title", ""),
                "Signed by": body.signed_name.strip(), "IP": ip or "—"}))
    fresh = await _get_offer_or_404(offer["offer_id"])
    return {"success": True, **_public_view(fresh)}


@router.post("/careers/offers/public/{token}/decline")
async def public_decline_offer(token: str, body: PublicDeclineBody, request: Request):
    offer = await _find_by_candidate_token(token)
    if offer["state"] not in ("sent",):
        raise HTTPException(status_code=409, detail=f"Offer is {offer['state']} — cannot decline")
    now = _now_iso()
    ip = request.client.host if request.client else None
    update_offer = {**offer, "decline_reason": body.reason or "", "responded_at": now, "response_ip": ip}
    _branding = await _load_offer_branding()
    try:
        pdf_bytes = _generate_offer_pdf(update_offer, variant="declined", branding=_branding)
    except OfferDataValidationError as e:
        logger.error(f"[offers] decline PDF generation failed for {offer['offer_id']}: missing={e.missing}")
        raise HTTPException(status_code=500, detail="Decline acknowledgement PDF unavailable — please contact the recruiting team.")
    pdf_path, pdf_hash = await _persist_pdf(offer["offer_id"], pdf_bytes, "declined")
    update = {
        "state": "declined", "responded_at": now,
        "decline_reason": body.reason or "",
        "response_ip": ip,
        "pdf_path": pdf_path, "pdf_hash": pdf_hash,
        "pdf_variant": "declined",
        "pdf_theme_signature": OFFER_PDF_THEME_SIGNATURE,
        **_append_event(offer, "declined", {"reason": body.reason or ""}),
    }
    await db[OFFERS_COL].update_one({"offer_id": offer["offer_id"]}, {"$set": update})
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        tpl = TEMPLATE_CATALOG["career_offer_declined"]["builder"](
            applicant_name=offer.get("candidate_name", ""),
            role_title=offer.get("role_title", ""),
            reason=body.reason or "",
        )
        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        await send_email(
            recipient_email=offer["candidate_email"], recipient_name=offer.get("candidate_name"),
            subject=tpl.subject, content=tpl.html, content_text=tpl.text,
            template_key="career_offer_declined",
            attachments=[{
                "filename": build_pdf_v15_filename("job-offer", offer["offer_id"]),
                "content": pdf_b64, "content_type": "application/pdf",
            }],
        )
    except Exception as e:
        logger.warning(f"[offers] decline email failed: {e}")
    asyncio.ensure_future(_ping_recruiter(request, offer["offer_id"],
        event_type="career_offer_declined", severity="warning",
        title="🙏 Offer declined",
        summary=f"{offer.get('candidate_name','Candidate')} declined the offer for {offer.get('role_title','')}.",
        fields={"Candidate": offer.get("candidate_name", ""), "Role": offer.get("role_title", ""),
                "Reason": (body.reason or "—")[:160]}))
    fresh = await _get_offer_or_404(offer["offer_id"])
    return {"success": True, **_public_view(fresh)}


@router.get("/careers/offers/public/{token}/pdf")
async def public_get_offer_pdf(token: str):
    offer = await _find_by_candidate_token(token)
    try:
        offer = await _ensure_offer_pdf_current_theme(offer)
    except OfferDataValidationError:
        raise HTTPException(status_code=404, detail="PDF not available")
    full = Path("/app/backend") / offer["pdf_path"]
    if not full.exists():
        raise HTTPException(status_code=404, detail="PDF not found on disk")
    return FileResponse(str(full), media_type="application/pdf",
                        filename=build_pdf_v15_filename("job-offer", offer["offer_id"]))


# 1x1 transparent GIF for email open tracking
_TRACKING_GIF = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00, 0x00, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0x21, 0xf9, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44, 0x01, 0x00, 0x3b,
])


@router.get("/careers/offers/public/{token}/pixel.gif")
async def public_tracking_pixel(token: str, request: Request):
    try:
        offer = await _find_by_candidate_token(token)
        update: dict[str, Any] = {"open_count": int(offer.get("open_count", 0)) + 1, "updated_at": _now_iso()}
        if not offer.get("opened_at_first"):
            update["opened_at_first"] = _now_iso()
            update["events"] = (offer.get("events") or []) + [{"ts": _now_iso(), "type": "email_opened_first", "meta": {}}]
        await db[OFFERS_COL].update_one({"offer_id": offer["offer_id"]}, {"$set": update})
    except Exception:
        pass
    return Response(content=_TRACKING_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


# ── Recruiter notification helper ────────────────────────────
async def _ping_recruiter(request: Request, offer_id: str, *, event_type: str, severity: str,
                           title: str, summary: str, fields: dict[str, Any]):
    try:
        from services.webhook_alerts import (get_config, _build_slack_payload,
                                               _build_teams_payload, _post_webhook)
        cfg = await get_config()
        slack_url = cfg.get("slack_webhook_url") or ""
        teams_url = cfg.get("teams_webhook_url") or ""
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
        scheme = request.headers.get("x-forwarded-proto") or "https"
        deep_link = f"{scheme}://{host}/admin/offer-studio?offerId={offer_id}"
        if slack_url:
            asyncio.ensure_future(_post_webhook(slack_url,
                _build_slack_payload(event_type, severity, title, summary, fields, deep_link)))
        if teams_url:
            asyncio.ensure_future(_post_webhook(teams_url,
                _build_teams_payload(event_type, severity, title, summary, fields, deep_link)))
        try:
            await db.webhook_alerts_log.insert_one({
                "created_at": _now_iso(), "event_type": event_type, "severity": severity,
                "title": title, "summary": summary, "fields": fields, "url": deep_link,
                "dispatched": bool(slack_url or teams_url),
            })
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[offers] recruiter ping failed: {e}")


# ── Scheduler: sweep expired offers ──────────────────────────
async def sweep_expired_offers():
    """Called by the global scheduler every ~1 hour. Flips past-expiry offers to 'expired'."""
    now = datetime.now(timezone.utc)
    q = {"state": "sent", "expires_at": {"$lt": now.isoformat()}}
    n = 0
    async for d in db[OFFERS_COL].find(q, {"_id": 0}):
        try:
            events = (d.get("events") or []) + [{"ts": now.isoformat(), "type": "auto_expired", "meta": {}}]
            await db[OFFERS_COL].update_one({"offer_id": d["offer_id"]},
                {"$set": {"state": "expired", "updated_at": now.isoformat(), "events": events}})
            # Fire candidate email
            try:
                from utils.email_service import send_email
                from utils.email_templates import TEMPLATE_CATALOG
                tpl = TEMPLATE_CATALOG["career_offer_expired"]["builder"](
                    applicant_name=d.get("candidate_name", ""),
                    role_title=d.get("role_title", ""),
                )
                await send_email(
                    recipient_email=d.get("candidate_email"),
                    recipient_name=d.get("candidate_name"),
                    subject=tpl.subject, content=tpl.html, content_text=tpl.text,
                    template_key="career_offer_expired",
                )
            except Exception:
                pass
            n += 1
        except Exception as e:
            logger.warning(f"[offers] sweep fail for {d.get('offer_id')}: {e}")
    if n:
        logger.info(f"[offers] sweep: {n} offer(s) auto-expired")
    return {"expired": n}

# ── Letter design review pack (admin) ─────────────────────────
# Drives 4 real offers through the existing lifecycle flows (draft → send →
# rescind / expire-sweep / candidate-decline) and emails the persisted PDF
# artifacts to the requesting admin. Sample records are deleted after send.

REVIEW_SAMPLE_CANDIDATE = {
    "name": "Alex Johnson",
    "role_title": "Senior AI Engineer",
    "candidate_address": "742 Innovation Drive, Suite 12, Austin, TX 78701, USA",
    "department": "AI Platform Engineering",
    "reporting_manager": "Jordan Lee, VP of Engineering",
}


def _review_draft_body(application_id: str, now: datetime) -> "OfferDraftBody":
    return OfferDraftBody(
        application_id=application_id,
        base_salary_usd=185000,
        bonus_target_pct=15,
        equity_shares=12000,
        signing_bonus_usd=20000,
        relocation_usd=10000,
        pto_days=25,
        start_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
        reporting_manager=REVIEW_SAMPLE_CANDIDATE["reporting_manager"],
        work_location="hybrid",
        work_city="Austin, TX",
        department=REVIEW_SAMPLE_CANDIDATE["department"],
        employment_type="Full-time",
        candidate_address=REVIEW_SAMPLE_CANDIDATE["candidate_address"],
        expiry_days=7,
    )


async def _cleanup_review_samples(application_id: str, offer_ids: list[str]) -> None:
    """Remove flagged sample offers (+ persisted PDF files) and the sample application."""
    async for doc in db[OFFERS_COL].find({"offer_id": {"$in": offer_ids}}, {"_id": 0, "pdf_path": 1}):
        if doc.get("pdf_path"):
            try:
                (Path("/app/backend") / doc["pdf_path"]).unlink(missing_ok=True)
            except Exception:
                pass
    await db[OFFERS_COL].delete_many({"offer_id": {"$in": offer_ids}})
    await db[APPS_COL].delete_one({"application_id": application_id})


@router.post("/careers/offers/letters/review-email")
async def admin_email_letter_review_pack(request: Request):
    """Run the real offer lifecycle 4 times (offer / rescinded / expired / rejected)
    and email the persisted letter PDFs to the requesting admin for review."""
    admin = await _require_admin(request)
    recipient = getattr(admin, "email", None)
    if not recipient:
        raise HTTPException(status_code=400, detail="Admin account has no email address")

    now = datetime.now(timezone.utc)
    application_id = f"app-letter-review-{uuid.uuid4().hex[:8]}"
    await db[APPS_COL].insert_one({
        "application_id": application_id,
        "name": REVIEW_SAMPLE_CANDIDATE["name"],
        "email": recipient,  # candidate-facing flow emails land in the admin inbox
        "role_title": REVIEW_SAMPLE_CANDIDATE["role_title"],
        "status": "offer",
        "is_review_sample": True,
        "created_at": _now_iso(),
    })

    created_offer_ids: list[str] = []
    attachments: list[dict[str, Any]] = []
    letters: list[dict[str, Any]] = []
    import base64
    try:
        for label in ("offer", "rescinded", "expired", "rejected"):
            # 1) Real draft flow
            draft = await admin_create_draft(request, _review_draft_body(application_id, now))
            offer_id = draft["offer_id"]
            created_offer_ids.append(offer_id)
            await db[OFFERS_COL].update_one({"offer_id": offer_id}, {"$set": {"is_review_sample": True}})

            # 2) Real send flow (persists the original PDF, emails candidate)
            sent = await admin_send_offer(request, offer_id)

            # 3) Real state transition per letter
            if label == "rescinded":
                await admin_rescind_offer(request, offer_id, RescindBody(
                    reason="Role requirements changed following an organizational restructure."))
            elif label == "rejected":
                await public_decline_offer(sent["candidate_token"], PublicDeclineBody(
                    reason="I have accepted another opportunity, but I'm grateful for the offer."), request)
            elif label == "expired":
                # Backdate expiry (time simulation only), then run the REAL scheduler sweep
                await db[OFFERS_COL].update_one(
                    {"offer_id": offer_id},
                    {"$set": {"expires_at": (now - timedelta(days=3)).isoformat()}})
                await sweep_expired_offers()
                # Real regeneration path (same as GET /offers/{id}/pdf)
                await _ensure_offer_pdf_current_theme(await _get_offer_or_404(offer_id))

            # 4) Collect the artifact the flow persisted
            offer = await _get_offer_or_404(offer_id)
            pdf_file = Path("/app/backend") / (offer.get("pdf_path") or "")
            if not offer.get("pdf_path") or not pdf_file.exists():
                raise HTTPException(status_code=500,
                                    detail=f"Lifecycle did not persist a PDF for '{label}' letter (offer {offer_id})")
            attachments.append({
                "filename": build_pdf_v15_filename("job-offer", f"sample-{label}-letter"),
                "content": base64.b64encode(pdf_file.read_bytes()).decode("ascii"),
                "content_type": "application/pdf",
            })
            letters.append({"letter": label, "offer_id": offer_id,
                            "state": offer["state"], "pdf_variant": offer.get("pdf_variant")})

        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        tpl = TEMPLATE_CATALOG["career_offer_letters_review"]["builder"](
            admin_name=getattr(admin, "name", None) or "Admin",
            sample_candidate=REVIEW_SAMPLE_CANDIDATE["name"],
            sample_role=REVIEW_SAMPLE_CANDIDATE["role_title"],
        )
        result = await send_email(
            recipient_email=recipient,
            recipient_name=getattr(admin, "name", None),
            subject=tpl.subject,
            content=tpl.html,
            content_text=tpl.text,
            template_key="career_offer_letters_review",
            attachments=attachments,
            dedupe_key=f"offer-letter-review-pack-{uuid.uuid4().hex}",
        )
        if not (result and result.get("success")):
            raise HTTPException(status_code=502,
                                detail=f"Pack email send failed: {(result or {}).get('error') or 'unknown error'}")
    finally:
        await _cleanup_review_samples(application_id, created_offer_ids)

    return {
        "success": True,
        "recipient": recipient,
        "flow": "real-lifecycle",
        "letters": letters,
        "attachments": [a["filename"] for a in attachments],
        "cleaned_up": True,
    }
