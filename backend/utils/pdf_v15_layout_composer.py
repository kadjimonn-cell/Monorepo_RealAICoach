from __future__ import annotations

import io
from typing import Any, Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from services.pdf_v15_theme import PALETTE, draw_callout_card, draw_kv_card, draw_page_chrome

PDF_THEME_METADATA_KEY = "/RACPDFTheme"
PDF_THEME_VISUAL_MODE_KEY = "/RACPDFThemeVisualMode"
PDF_THEME_SIGNATURE = "pdf-v15-global-runtime-visual-stamp-v2"
PDF_THEME_METADATA_STATE_KEY = "/RACPDFThemeMetadataState"

def _overlay_page_bytes(
    *,
    page_width: float,
    page_height: float,
    page_no: int,
    title: str,
    subtitle: str,
    right_primary: str,
    right_secondary: str,
    badge_text: str,
    badge_status: str,
    footer_text: str,
    summary_title: str,
    summary_rows: Iterable[tuple[str, Any]],
    callout_title: str,
    callout_subtitle: str,
    callout_detail: str,
    callout_status: str,
    margin_x: float,
    render_cards: bool,
    render_local_badge: bool,
) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(page_width, page_height))

    local_badge_text = badge_text if render_local_badge else " "
    y = draw_page_chrome(
        pdf,
        width=float(page_width),
        height=float(page_height),
        margin_x=margin_x,
        page_no=page_no,
        title=title,
        subtitle=subtitle,
        right_primary=right_primary,
        right_secondary=right_secondary,
        badge_text=local_badge_text,
        badge_status=badge_status,
        footer_text=footer_text,
    )

    if render_cards and page_no == 1:
        content_w = max(240.0, float(page_width) - (2 * margin_x))
        summary_w = min(260.0, content_w * 0.42)
        y2 = draw_kv_card(
            pdf,
            margin_x=margin_x,
            content_w=summary_w,
            y=y - 8,
            title=summary_title,
            rows=summary_rows,
            tone=PALETTE["primary"],
        )
        draw_callout_card(
            pdf,
            margin_x=margin_x + summary_w + 12,
            content_w=max(180.0, content_w - summary_w - 12),
            y=y2,
            title=callout_title,
            subtitle=callout_subtitle,
            detail=callout_detail,
            status=callout_status,
        )

    pdf.showPage()
    pdf.save()
    return out.getvalue()


def compose_pdf_v15_helper_layout(
    pdf_bytes: bytes,
    *,
    title: str,
    subtitle: str,
    right_primary: str,
    right_secondary: str,
    badge_text: str,
    badge_status: str,
    footer_text: str,
    summary_title: str = "Summary",
    summary_rows: Iterable[tuple[str, Any]] = (),
    callout_title: str = "Compliance",
    callout_subtitle: str = "PDF v15 enterprise helper composition",
    callout_detail: str = "Generated with shared v15 helper layout components.",
    callout_status: str = "INFO",
    margin_x: float = 28.0,
    render_cards: bool = False,
    render_local_badge: bool = False,
    stamp_theme_metadata: bool = False,
) -> bytes:
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF-"):
        return bytes(pdf_bytes)

    reader = PdfReader(io.BytesIO(bytes(pdf_bytes)))
    writer = PdfWriter()

    for idx, page in enumerate(reader.pages, start=1):
        overlay_bytes = _overlay_page_bytes(
            page_width=float(page.mediabox.width),
            page_height=float(page.mediabox.height),
            page_no=idx,
            title=title,
            subtitle=subtitle,
            right_primary=right_primary,
            right_secondary=right_secondary,
            badge_text=badge_text,
            badge_status=badge_status,
            footer_text=footer_text,
            summary_title=summary_title,
            summary_rows=summary_rows,
            callout_title=callout_title,
            callout_subtitle=callout_subtitle,
            callout_detail=callout_detail,
            callout_status=callout_status,
            margin_x=margin_x,
            render_cards=render_cards,
            render_local_badge=render_local_badge,
        )
        overlay_page = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    metadata = dict(reader.metadata or {})
    metadata.pop("/Producer", None)
    if stamp_theme_metadata:
        metadata[PDF_THEME_METADATA_KEY] = PDF_THEME_SIGNATURE
        metadata[PDF_THEME_VISUAL_MODE_KEY] = "helper_composed_chrome"
        metadata[PDF_THEME_METADATA_STATE_KEY] = "metadata-present"
    else:
        metadata[PDF_THEME_VISUAL_MODE_KEY] = "metadata_missing_helper_composed"
        metadata[PDF_THEME_METADATA_STATE_KEY] = "metadata-missing"
    try:
        writer.add_metadata(metadata)
    except Exception:
        pass

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
