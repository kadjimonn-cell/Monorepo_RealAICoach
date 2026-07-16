"""
Backend tests for RealAICoach Travel Visa Certificate polish round 2:
  (a) Signature image enlarged (>=100x45pt) & located in lower-left quadrant.
  (b) Masthead spacing (RealAICoach baseline -> TRAVEL VISA ACADEMY baseline) >= 20pt.
  (c) Regression: signatory string, VERIFY AUTHENTICITY panel fit, no raw ISO
      timestamps, month-name issue date.
  (d) Public verify endpoint: HTML 200 VALID CERTIFICATE, JSON valid:true,
      unknown -> 404 in both modes.

Uses http://localhost:8001 directly (external URL is Cloudflare-challenged).
Auth cookie captured once and reused (login is rate-limited).
"""
import io
import os
import re
import pytest
import requests
import fitz  # PyMuPDF

BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
CERT_ID = "TV-6B604E13"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def cert_pdf_bytes(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/travel-visa/certificate/download/{CERT_ID}",
        timeout=30,
    )
    assert r.status_code == 200, f"download failed: {r.status_code} {r.text[:200]}"
    assert r.content[:4] == b"%PDF", "response is not a PDF"
    return r.content


@pytest.fixture(scope="module")
def cert_doc(cert_pdf_bytes):
    doc = fitz.open(stream=cert_pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1
    yield doc
    doc.close()


# ── (a) SIGNATURE SIZE ────────────────────────────────────────────────────
def test_signature_image_enlarged_and_in_lower_left_quadrant(cert_doc):
    """
    In fitz rects, origin is TOP-LEFT.
    Landscape A4 => page.rect ~ (0,0,842,595).
    Signature should be x < 300, y > 380, width >= 100pt, height >= 45pt.
    """
    page = cert_doc[0]
    images = page.get_images(full=True)
    assert len(images) >= 3, f"expected multiple embedded images, got {len(images)}"

    candidates = []
    for img in images:
        xref = img[0]
        rects = page.get_image_rects(xref)
        for rect in rects:
            w = rect.width
            h = rect.height
            candidates.append((xref, rect, w, h))

    # Find at least one image whose rect matches the signature size + region.
    signature_hits = [
        (x, r, w, h) for (x, r, w, h) in candidates
        if w >= 100 and h >= 45 and r.x0 < 300 and r.y0 > 380
    ]
    assert signature_hits, (
        "No signature-sized image (>=100x45pt) found in lower-left quadrant "
        f"(x<300,y>380). Candidates: {[(round(r.x0,1),round(r.y0,1),round(w,1),round(h,1)) for _,r,w,h in candidates]}"
    )
    xref, rect, w, h = signature_hits[0]
    print(f"[SIGNATURE] xref={xref} rect=({rect.x0:.1f},{rect.y0:.1f},{rect.x1:.1f},{rect.y1:.1f}) w={w:.1f}pt h={h:.1f}pt")


# ── (b) MASTHEAD SPACING ──────────────────────────────────────────────────
def test_masthead_spacing_gap_at_least_20pt(cert_doc):
    """
    Extract text spans; find baseline of 'RealAICoach' (top) and the spaced
    'T R A V E L ...' academy line. Vertical gap must be >= 20pt.
    """
    page = cert_doc[0]
    text_dict = page.get_text("dict")
    brand_span = None
    academy_span = None
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                stripped = text.strip()
                if stripped == "RealAICoach" and brand_span is None:
                    brand_span = span
                # Spaced "TRAVEL VISA ACADEMY" -> "T R A V E L  V I S A  A C A D E M Y"
                # Look for a span containing 'T R A V E L' (case-insensitive, tolerant of double spaces)
                normalized = re.sub(r"\s+", " ", stripped.upper())
                if "T R A V E L" in normalized and "A C A D E M Y" in normalized and academy_span is None:
                    academy_span = span
    assert brand_span is not None, "Top masthead 'RealAICoach' text span not found"
    assert academy_span is not None, "Spaced 'TRAVEL VISA ACADEMY' academy line not found"

    # In fitz, span bbox is (x0, y0, x1, y1) with y increasing downward.
    # The baseline is approximately y1 (bottom of the glyphs).
    brand_baseline = brand_span["bbox"][3]
    academy_baseline = academy_span["bbox"][3]
    gap = academy_baseline - brand_baseline
    print(
        f"[MASTHEAD] brand_bbox={brand_span['bbox']} academy_bbox={academy_span['bbox']} baseline_gap={gap:.2f}pt"
    )
    assert gap >= 20.0, f"Masthead spacing gap too small: {gap:.2f}pt (need >= 20pt)"


# ── (c) REGRESSIONS ───────────────────────────────────────────────────────
def test_signatory_text_present(cert_doc):
    text = cert_doc[0].get_text("text")
    assert "Adjimon Kouatonou" in text and "Program Director" in text, (
        "Signatory 'Adjimon Kouatonou — Program Director' not found in PDF text"
    )


def test_verify_authenticity_does_not_overflow_panel(cert_doc):
    """
    'VERIFY AUTHENTICITY' is drawn spaced. Rightmost x of that span must be
    strictly less than 770pt (page 842pt - 72pt margin = verification panel edge).
    """
    page = cert_doc[0]
    text_dict = page.get_text("dict")
    verify_spans = []
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                normalized = re.sub(r"\s+", " ", span.get("text", "").strip().upper())
                if ("V E R I F Y" in normalized and "A U T H E N T I C I T Y" in normalized) \
                        or normalized == "VERIFY AUTHENTICITY":
                    verify_spans.append(span)
    assert verify_spans, "VERIFY AUTHENTICITY label span not found"
    max_right = max(span["bbox"][2] for span in verify_spans)
    print(f"[VERIFY PANEL] max_right={max_right:.2f}pt")
    assert max_right < 770, f"VERIFY AUTHENTICITY overflows panel: right={max_right:.2f}pt"


def test_no_raw_iso_timestamps(cert_doc):
    text = cert_doc[0].get_text("text")
    hits = re.findall(r"T\d{2}:\d{2}:\d{2}", text)
    assert not hits, f"Raw ISO timestamp fragments found: {hits}"


def test_month_name_issue_date_present(cert_doc):
    text = cert_doc[0].get_text("text")
    months = ("January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December")
    assert any(m in text for m in months), f"No month-name issue date in PDF text: {text[:400]!r}"
    assert "Issued" in text, "'Issued <Month DD, YYYY>' label not found"


# ── (d) VERIFY ENDPOINT (public, no auth) ─────────────────────────────────
def test_verify_html_valid():
    r = requests.get(f"{BASE_URL}/api/travel-visa/certificate/verify/{CERT_ID}", timeout=15)
    assert r.status_code == 200
    body = r.text.upper()
    assert "VALID CERTIFICATE" in body, f"'VALID CERTIFICATE' not in HTML body: {r.text[:400]!r}"


def test_verify_json_valid_true():
    r = requests.get(
        f"{BASE_URL}/api/travel-visa/certificate/verify/{CERT_ID}?format=json",
        timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("valid") is True, f"expected valid:true, got: {data}"


def test_verify_unknown_id_404_html():
    r = requests.get(
        f"{BASE_URL}/api/travel-visa/certificate/verify/TV-DOESNOTEXIST999",
        timeout=15,
    )
    assert r.status_code == 404


def test_verify_unknown_id_404_json():
    r = requests.get(
        f"{BASE_URL}/api/travel-visa/certificate/verify/TV-DOESNOTEXIST999?format=json",
        timeout=15,
    )
    assert r.status_code == 404
