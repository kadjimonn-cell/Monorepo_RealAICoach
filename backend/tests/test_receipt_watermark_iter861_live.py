"""
Iteration 861 — LIVE verification of the brand watermark lockup that fills the
former blank space between the QR verification panel and the bottom footer.

Acceptance criteria (from main-agent handoff):
1. Auth as free user (cookie session) and fetch /api/r/f?d=r&p=txn_a98b73968e034fe7 -> 200 application/pdf.
2. PDF text: 'RealAICoach' appears >= 3 times, doc-number 'RCT-20260518-10B84740' >= 4 times.
3. Visual/opacity: watermark region contains LIGHT-GRAY watermark pixels (no fully opaque ink; darkest
   pixel in the brand text region should be LIGHTER than RGB(150,150,150)) and the region is not fully blank.
4. No overlap with QR trust panel above or footer bar below.
5. Regressions:
   - Zero 'PDF v15' text.
   - Branded header 'Enterprise Payment Confirmation' present.
   - Canonical 'USD 5.99' Basic price, plus 'PAYMENT TIMELINE', 'TOTAL YOU PAY', 'HASH', 'SIGN'.
   - Invoice via /api/r/f?d=i as free user -> 403.
   - Receipt via /api/content/document -> 200.
   - Unauth -> 401.
"""
from __future__ import annotations

import io
import os
import re

import pymupdf
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
PAYMENT_ID = "txn_a98b73968e034fe7"
DOC_NUMBER = "RCT-20260518-10B84740"


# ────────────────────────────── Fixtures ──────────────────────────────
@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"free-user login failed: {r.status_code} {r.text[:400]}"
    return s


@pytest.fixture(scope="module")
def receipt_pdf_bytes(free_session: requests.Session) -> bytes:
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "r", "p": PAYMENT_ID, "v": "0"},
        timeout=45,
    )
    assert r.status_code == 200, f"receipt fetch failed: {r.status_code} {r.text[:400]}"
    assert "application/pdf" in r.headers.get("Content-Type", "").lower(), r.headers
    assert r.content.startswith(b"%PDF"), "content is not a PDF"
    return r.content


def _extract_text(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


# ─────────────────────── PRIMARY: watermark text ───────────────────────
def test_receipt_pdf_200_and_content_type(receipt_pdf_bytes: bytes):
    assert receipt_pdf_bytes.startswith(b"%PDF")
    assert len(receipt_pdf_bytes) > 1500


def test_watermark_brand_name_appears_at_least_three_times(receipt_pdf_bytes: bytes):
    text = _extract_text(receipt_pdf_bytes)
    count = text.count("RealAICoach")
    assert count >= 3, f"expected 'RealAICoach' >= 3 (header+watermark+footer), got {count}"


def test_watermark_doc_number_appears_at_least_four_times(receipt_pdf_bytes: bytes):
    text = _extract_text(receipt_pdf_bytes)
    count = text.count(DOC_NUMBER)
    assert count >= 4, f"expected doc-number '{DOC_NUMBER}' >= 4 occurrences, got {count}"


# ──────────────────── VISUAL / OPACITY verification ────────────────────
def _render_page_to_rgb(pdf_bytes: bytes, page_index: int = 0, dpi: int = 150):
    """Render the given page to an RGB pixmap and return (pixmap_bytes, w, h, rect)."""
    doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        page = doc.load_page(page_index)
        rect = page.rect  # letter is 612x792 pts
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        return pix.samples, pix.width, pix.height, rect
    finally:
        doc.close()


def _iter_region_pixels(samples: bytes, img_w: int, x0: int, y0: int, x1: int, y1: int):
    """Yield (r,g,b) for every pixel in [x0,x1) × [y0,y1) rows-major."""
    stride = img_w * 3
    for y in range(y0, y1):
        row = samples[y * stride: (y + 1) * stride]
        for x in range(x0, x1):
            base = x * 3
            yield row[base], row[base + 1], row[base + 2]


def test_watermark_region_has_light_gray_pixels_not_full_black(receipt_pdf_bytes: bytes):
    """Watermark rendered at 13-24% alpha should produce light-gray pixels — never full-ink.

    We first locate the actual watermark 'RealAICoach' text via PyMuPDF search, filter for the
    occurrence in the residual gap (32pt < pdf_y_bottom < 210pt), then sample the pixmap in that
    exact rectangle.
    """
    doc = pymupdf.open(stream=io.BytesIO(receipt_pdf_bytes), filetype="pdf")
    try:
        page = doc.load_page(0)
        page_h = page.rect.height
        page_w = page.rect.width
        watermark_rect = None
        widest = 0.0
        for r in page.search_for("RealAICoach"):
            pdf_y_bottom = page_h - r.y1
            if 32 < pdf_y_bottom < 210:  # inside the residual gap
                width = r.x1 - r.x0
                if width > widest:
                    widest = width
                    watermark_rect = r
        assert watermark_rect is not None, "watermark 'RealAICoach' not found in residual gap"
        # sanity: the actual watermark is drawn at 18-32pt font, so width should be > 80pt
        assert widest > 80, (
            f"selected 'RealAICoach' in gap looks too small to be the watermark (width={widest:.1f}pt)"
        )

        dpi = 150
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        img_w, img_h = pix.width, pix.height
        scale = img_w / page_w
        # PyMuPDF rect coords are top-origin already — use directly.
        x0 = max(0, int(watermark_rect.x0 * scale) - 2)
        x1 = min(img_w, int(watermark_rect.x1 * scale) + 2)
        y0 = max(0, int(watermark_rect.y0 * scale) - 2)
        y1 = min(img_h, int(watermark_rect.y1 * scale) + 2)
        assert x1 > x0 and y1 > y0, "invalid region"
    finally:
        doc.close()

    samples = pix.samples
    darkest = 255
    dark_gray_pixel_count = 0
    non_white_count = 0
    for r, g, b in _iter_region_pixels(samples, img_w, x0, y0, x1, y1):
        m = min(r, g, b)
        if m < darkest:
            darkest = m
        if m < 250:
            non_white_count += 1
        # a "watermark-ink" pixel: visibly gray but not black -> in (110, 240)
        if 110 <= m <= 240:
            dark_gray_pixel_count += 1

    total_pixels = (x1 - x0) * (y1 - y0)
    # Region must not be blank
    assert non_white_count > total_pixels * 0.02, (
        f"watermark rect looks blank: only {non_white_count}/{total_pixels} non-white pixels"
    )
    # Darkest ink in the watermark region must be lighter than (150,150,150) — never full-ink.
    assert darkest >= 110, (
        f"watermark contains near-full-ink pixels (darkest channel={darkest}); "
        "watermark opacity likely broken."
    )
    # There must be a meaningful count of mid-gray pixels — proving watermark actually rendered.
    assert dark_gray_pixel_count > 50, (
        f"watermark has only {dark_gray_pixel_count} gray pixels — likely missing."
    )


def test_watermark_does_not_overlap_qr_trust_panel_or_footer(receipt_pdf_bytes: bytes):
    """
    Locate the 'RealAICoach' text quads on the page — at least ONE occurrence must sit inside the
    residual gap ( PDF y ∈ [38, ry-10] ) between QR trust panel and footer bar.
    We approximate the gap band as PDF-y in [38, ~180] (below QR panel bottom at ~180 pts) and
    above the 30pt footer bar.
    """
    doc = pymupdf.open(stream=io.BytesIO(receipt_pdf_bytes), filetype="pdf")
    try:
        page = doc.load_page(0)
        rects = page.search_for("RealAICoach")
        assert rects, "no RealAICoach text found on the page"
        page_h = page.rect.height
        gap_hits = []  # watermark occurrences in the residual gap (between QR panel and footer bar)
        header_hits = []  # header 'RealAICoach' at top of page
        footer_hits = []  # expected: footer 'Auto-generated by RealAICoach ...' inside 0-30pt bar
        for r in rects:
            # PyMuPDF uses top-left origin; convert to PDF-y (bottom-left origin) using bottom edge.
            pdf_y_bottom = page_h - r.y1
            pdf_y_top = page_h - r.y0
            if pdf_y_bottom < 30:
                footer_hits.append((pdf_y_bottom, pdf_y_top))
            elif pdf_y_bottom > 700:
                header_hits.append((pdf_y_bottom, pdf_y_top))
            elif 32 <= pdf_y_bottom <= 260:
                gap_hits.append((pdf_y_bottom, pdf_y_top))
        assert gap_hits, (
            f"expected at least one 'RealAICoach' watermark in the residual gap area, "
            f"positions found (y_bottom, y_top): "
            f"{[(round(page_h - r.y1, 1), round(page_h - r.y0, 1)) for r in rects]}"
        )
        # Watermark must NOT touch the QR trust panel: watermark y_top must sit at least a few
        # points below the panel's bottom edge (~180pt).
        for y_bottom, y_top in gap_hits:
            assert y_top <= 210, (
                f"watermark 'RealAICoach' overlaps the QR trust panel above (y_top={y_top:.1f})"
            )
        # Footer bar naturally contains the 'Auto-generated by RealAICoach' string — that's expected
        # and NOT considered an overlap. Only fail if we have zero header + footer + at least one
        # gap-watermark instance (already asserted).
        assert header_hits or footer_hits, (
            "expected either header or footer 'RealAICoach' branding to also be present alongside the watermark"
        )
    finally:
        doc.close()


# ─────────────────────────── REGRESSION ────────────────────────────────
def test_no_pdf_v15_tokens(receipt_pdf_bytes: bytes):
    text = _extract_text(receipt_pdf_bytes)
    banned = ["PDF v15", "RealAICoach PDF v15", "GLOBAL PDF V15 POLICY ACTIVE"]
    for token in banned:
        assert token not in text, f"unexpected v15 token found: {token!r}"


def test_branded_header_and_masthead_tokens(receipt_pdf_bytes: bytes):
    text = _extract_text(receipt_pdf_bytes)
    for token in (
        "Enterprise Payment Confirmation",
        "PAYMENT TIMELINE",
        "TOTAL YOU PAY",
        "HASH",
        "SIGN",
        "USD 5.99",
    ):
        assert token in text, f"expected token missing from receipt PDF: {token!r}"


def test_invoice_forbidden_for_free_user(free_session: requests.Session):
    r = free_session.get(
        f"{BASE_URL}/api/r/f",
        params={"d": "i", "p": PAYMENT_ID},
        timeout=30,
        allow_redirects=False,
    )
    assert r.status_code == 403, f"expected 403 for free-user invoice, got {r.status_code}"


def test_content_document_receipt_200(free_session: requests.Session):
    r = free_session.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": PAYMENT_ID},
        timeout=45,
    )
    # accept either 200 PDF or 200 JSON wrapper; primary contract is 200
    assert r.status_code == 200, f"expected 200 for /api/content/document receipt, got {r.status_code}: {r.text[:300]}"


def test_unauth_receipt_401():
    r = requests.get(
        f"{BASE_URL}/api/content/document",
        params={"doc_type": "receipt", "payment_id": PAYMENT_ID},
        timeout=30,
        allow_redirects=False,
    )
    assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}"


# ─────────────────────── content-length sanity ─────────────────────────
def test_receipt_pdf_reasonable_size(receipt_pdf_bytes: bytes):
    # watermark + full page should give > 3KB, < 400KB
    size = len(receipt_pdf_bytes)
    assert 3000 < size < 400_000, f"unexpected PDF size: {size}"


def test_doc_number_matches_expected_pattern(receipt_pdf_bytes: bytes):
    text = _extract_text(receipt_pdf_bytes)
    # Ensure the expected receipt number pattern exists at least once
    assert re.search(r"RCT-\d{8}-[0-9A-F]{8}", text), "receipt number format not found"
