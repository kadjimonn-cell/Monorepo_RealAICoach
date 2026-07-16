"""Shared PDF v15 enterprise visual system helpers.

This module centralizes the canonical RealAICoach PDF v15 visual language so
all generators can reuse a consistent chrome: dual accent strip, branded
header band, status ribbon, and enterprise footer.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib.colors import HexColor, white


PALETTE = {
    "primary": HexColor("#0F766E"),
    "teal": HexColor("#14B8A6"),
    "indigo": HexColor("#4F46E5"),
    "ink": HexColor("#0F172A"),
    "slate": HexColor("#475569"),
    "slate_soft": HexColor("#F1F5F9"),
    "border_soft": HexColor("#E2E8F0"),
    "success": HexColor("#047857"),
    "warning": HexColor("#B45309"),
    "danger": HexColor("#B91C1C"),
}

_CANONICAL_TILE_PATHS = [
    Path("/app/backend/static/images/brand-logo-chip.png"),
    Path("/app/backend/static/branding/realaicoach-logo.png"),
]


def get_canonical_logo_tile_path() -> str | None:
    """Return canonical receipt-style logo-tile path for PDF headers."""
    for candidate in _CANONICAL_TILE_PATHS:
        if candidate.exists():
            return str(candidate)
    return None


def status_color(status: str) -> Any:
    normalized = str(status or "").upper()
    if normalized in {"PASS", "SUCCESS", "APPROVED", "INFO", "OK"}:
        return PALETTE["success"]
    if normalized in {"WARN", "WARNING", "PENDING", "UNDER_REVIEW"}:
        return PALETTE["warning"]
    return PALETTE["danger"]


def draw_page_chrome(
    pdf,
    *,
    width: float,
    height: float,
    margin_x: float,
    page_no: int,
    title: str,
    subtitle: str,
    right_primary: str,
    right_secondary: str,
    badge_text: str,
    badge_status: str,
    footer_text: str,
) -> float:
    """Draw canonical v15 chrome and return starting y-coordinate for content.

    Global requirement:
    - Must be reusable by middleware policy so all current/future PDF generators
      inherit the same header/footer automatically.
    - Enterprise-first visual hierarchy (clean, low-noise, readable in mobile
      PDF viewers).
    """

    def _fit_text(value: str, *, font: str, size: float, max_w: float) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if pdf.stringWidth(text, font, size) <= max_w:
            return text
        ellipsis = "..."
        cut = text
        while cut and pdf.stringWidth(cut + ellipsis, font, size) > max_w:
            cut = cut[:-1]
        return (cut + ellipsis) if cut else ellipsis

    content_w = max(180.0, width - (2 * margin_x))

    # Top accent (subtle)
    top_strip_h = 3.0
    pdf.setFillColor(PALETTE["teal"])
    pdf.rect(0, height - top_strip_h, width * 0.42, top_strip_h, stroke=0, fill=1)
    pdf.setFillColor(PALETTE["primary"])
    pdf.rect(width * 0.42, height - top_strip_h, width * 0.58, top_strip_h, stroke=0, fill=1)

    # Header card shell
    header_h = max(54.0, min(66.0, height * 0.09))
    header_y = height - top_strip_h - header_h - 5.0
    pdf.setStrokeColor(PALETTE["border_soft"])
    pdf.setFillColor(white)
    pdf.roundRect(margin_x, header_y, content_w, header_h, 6, stroke=1, fill=1)

    # Right meta panel
    meta_w = max(128.0, min(188.0, content_w * 0.34))
    meta_h = header_h - 14.0
    meta_x = margin_x + content_w - meta_w - 8.0
    meta_y = header_y + 7.0
    pdf.setFillColor(PALETTE["slate_soft"])
    pdf.roundRect(meta_x, meta_y, meta_w, meta_h, 4, stroke=0, fill=1)

    # Brand tile
    tile = max(32.0, min(38.0, header_h - 16.0))
    tile_x = margin_x + 9.0
    tile_y = header_y + ((header_h - tile) / 2)
    pdf.setStrokeColor(PALETTE["border_soft"])
    pdf.setFillColor(white)
    pdf.roundRect(tile_x, tile_y, tile, tile, 4, stroke=1, fill=1)

    logo_path = get_canonical_logo_tile_path()
    drew_logo = False
    try:
        if logo_path and os.path.exists(logo_path):
            inset = max(3.0, tile * 0.12)
            pdf.drawImage(
                logo_path,
                tile_x + inset,
                tile_y + inset,
                width=max(14.0, tile - (2 * inset)),
                height=max(14.0, tile - (2 * inset)),
                preserveAspectRatio=True,
                mask="auto",
            )
            drew_logo = True
    except Exception:
        drew_logo = False
    if not drew_logo:
        pdf.setFillColor(PALETTE["primary"])
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawCentredString(tile_x + (tile / 2), tile_y + (tile / 2) - 2.5, "RAI")

    # Header left text block
    text_x = tile_x + tile + 8.0
    text_w = max(84.0, meta_x - text_x - 10.0)
    title_txt = _fit_text(title, font="Helvetica-Bold", size=11.6, max_w=text_w)
    subtitle_txt = _fit_text(subtitle, font="Helvetica", size=8.1, max_w=text_w)

    pdf.setFillColor(PALETTE["ink"])
    pdf.setFont("Helvetica-Bold", 11.6)
    pdf.drawString(text_x, header_y + header_h - 20.0, title_txt)
    pdf.setFillColor(PALETTE["slate"])
    pdf.setFont("Helvetica", 8.1)
    pdf.drawString(text_x, header_y + 14.2, subtitle_txt)

    # Header right meta text
    rp_txt = _fit_text(right_primary, font="Helvetica-Bold", size=8.1, max_w=meta_w - 14.0)
    rs_txt = _fit_text(right_secondary, font="Helvetica", size=7.5, max_w=meta_w - 14.0)
    pdf.setFillColor(PALETTE["ink"])
    pdf.setFont("Helvetica-Bold", 8.1)
    pdf.drawRightString(meta_x + meta_w - 7.0, meta_y + meta_h - 9.4, rp_txt)
    pdf.setFillColor(PALETTE["slate"])
    pdf.setFont("Helvetica", 7.5)
    pdf.drawRightString(meta_x + meta_w - 7.0, meta_y + 8.0, rs_txt)

    # Policy badge (compact, centered)
    badge_h = 11.8
    badge_y = header_y - badge_h - 4.4
    badge_w = max(150.0, min(330.0, content_w * 0.62))
    badge_x = (width - badge_w) / 2
    pdf.setFillColor(status_color(badge_status))
    pdf.roundRect(badge_x, badge_y, badge_w, badge_h, 3, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7.3)
    badge_label = _fit_text(badge_text, font="Helvetica-Bold", size=7.3, max_w=badge_w - 10.0)
    pdf.drawCentredString(badge_x + (badge_w / 2), badge_y + 3.1, badge_label)

    # Footer (clean legal strip)
    footer_h = max(20.0, min(24.0, height * 0.035))
    pdf.setFillColor(white)
    pdf.rect(0, 0, width, footer_h, stroke=0, fill=1)
    pdf.setFillColor(PALETTE["border_soft"])
    pdf.rect(0, footer_h - 1.1, width, 1.1, stroke=0, fill=1)
    pdf.setFillColor(PALETTE["teal"])
    pdf.rect(0, footer_h, width, 1.6, stroke=0, fill=1)

    footer_txt = _fit_text(
        footer_text or "RealAICoach • enterprise document standard",
        font="Helvetica",
        size=7.0,
        max_w=max(80.0, content_w - 56.0),
    )
    pdf.setFillColor(PALETTE["slate"])
    pdf.setFont("Helvetica", 7.0)
    pdf.drawString(margin_x, 8.0, footer_txt)

    pill_w = 34.0
    pill_h = 10.8
    pill_x = width - margin_x - pill_w
    pill_y = 5.8
    pdf.setFillColor(PALETTE["primary"])
    pdf.roundRect(pill_x, pill_y, pill_w, pill_h, 2.5, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 6.9)
    pdf.drawCentredString(pill_x + (pill_w / 2), pill_y + 2.9, f"Page {page_no}")

    return badge_y - 7.0


def draw_kv_card(
    pdf,
    *,
    margin_x: float,
    content_w: float,
    y: float,
    title: str,
    rows: Iterable[tuple[str, Any]],
    tone,
    line_h: float = 11,
    label_col_w: float = 185,
) -> float:
    """Draw ribbon card with key/value rows and return new y."""

    rows = list(rows)
    value_col_w = max(120, int(content_w - label_col_w - 24))

    wrapped_rows: list[tuple[str, list[str]]] = []
    total_lines = 0
    for key, val in rows:
        value_text = "" if val is None else str(val)
        chunks: list[str] = []
        for part in (value_text.splitlines() or [value_text]):
            chunks.extend(textwrap.wrap(part, width=max(30, int(value_col_w / 5.3))) or [""])
        chunks = chunks or [""]
        wrapped_rows.append((str(key), chunks))
        total_lines += max(1, len(chunks))

    body_h = 14 + (total_lines * line_h) + (len(rows) * 1.2)
    header_h = 17
    total_h = header_h + 4 + body_h + 11

    pdf.setFillColor(tone)
    pdf.roundRect(margin_x, y - header_h, content_w, header_h, 5, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 9.6)
    pdf.drawString(margin_x + 8, y - 11.5, title)

    body_top = y - header_h - 4
    pdf.setFillColor(white)
    pdf.setStrokeColor(PALETTE["border_soft"])
    pdf.roundRect(margin_x, body_top - body_h, content_w, body_h, 7, stroke=1, fill=1)

    cursor = body_top - 10
    key_right = margin_x + 8 + label_col_w
    val_x = key_right + 10
    for key, chunks in wrapped_rows:
        pdf.setFillColor(PALETTE["ink"])
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawRightString(key_right, cursor, f"{key}:")
        pdf.setFont("Helvetica", 8.8)
        pdf.drawString(val_x, cursor, chunks[0])
        cursor -= line_h
        for line in chunks[1:]:
            pdf.drawString(val_x, cursor, line)
            cursor -= line_h
        pdf.setStrokeColor(PALETTE["border_soft"])
        pdf.setLineWidth(0.28)
        pdf.line(margin_x + 7, cursor + 4, margin_x + content_w - 7, cursor + 4)
        cursor -= 1

    return y - total_h


def draw_callout_card(
    pdf,
    *,
    margin_x: float,
    content_w: float,
    y: float,
    title: str,
    subtitle: str,
    detail: str,
    status: str,
) -> float:
    """Draw compact outcome card and return new y."""

    if str(status).upper() in {"PASS", "SUCCESS", "APPROVED", "INFO", "OK"}:
        bg = HexColor("#ECFDF5")
    elif str(status).upper() in {"WARN", "WARNING", "PENDING", "UNDER_REVIEW"}:
        bg = HexColor("#FFF7ED")
    else:
        bg = HexColor("#FEF2F2")

    card_h = 62
    pdf.setFillColor(bg)
    pdf.setStrokeColor(PALETTE["border_soft"])
    pdf.roundRect(margin_x, y - card_h, content_w, card_h, 8, stroke=1, fill=1)
    pdf.setFillColor(PALETTE["teal"])
    pdf.rect(margin_x, y - card_h, 4, card_h, stroke=0, fill=1)

    pdf.setFillColor(PALETTE["ink"])
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(margin_x + 11, y - 19, title)
    pdf.setFont("Helvetica", 8.9)
    pdf.drawString(margin_x + 11, y - 33, subtitle[:130])
    pdf.setFont("Helvetica-Bold", 8.9)
    pdf.drawString(margin_x + 11, y - 47, detail[:130])
    return y - card_h - 10
