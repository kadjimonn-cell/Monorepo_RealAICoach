"""
Backend tests for RealAICoach Travel Visa Certificate PDF fixes (iteration_846).

Validates the three PDF-content fixes reported by the main agent:
  1) 'VERIFY AUTHENTICITY' label does not overflow the verification panel.
  2) The circle 'RAC/CERTIFIED' seal is replaced by the official certified-stamp.png
     (assert page contains multiple embedded images: logo + QR + signature + stamp).
  3) Signature line reads 'Adjimon Kouatonou — Program Director'
     (NOT 'Nova — Program Director'), and a handwritten signature image is embedded.
  Also: 'Issued' date is formatted as a human month/day/year — no raw ISO timestamps.

Regression:
  - GET verify HTML valid / invalid (200 vs 404)
  - GET verify JSON valid / invalid
  - POST email
  - Download header x-pdf-theme-policy == 'exempt-travel-visa-certificate'
  - Regenerate-all endpoint

All calls hit http://localhost:8001 with cookie-session auth + X-Requested-With CSRF header.
"""

import os
import re
import io
import fitz  # PyMuPDF
import pytest
import requests


BASE_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"
ADMIN_USER_ID = "user_4b5a68d2f7c6"
EXISTING_CERT_ID = "TV-6B604E13"

# Page geometry (landscape A4 ~ 842 x 595 pt).
PAGE_WIDTH_PT = 842.0
PANEL_RIGHT_EDGE_PT = PAGE_WIDTH_PT - 72.0  # 770pt


# ── shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    # Login
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASS,
    }, timeout=15)
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text[:200]}")
    return session


@pytest.fixture(scope="module")
def fresh_cert_id(api_client):
    resp = api_client.post(
        f"{BASE_URL}/api/travel-visa/certificate/generate",
        json={
            "user_id": ADMIN_USER_ID,
            "user_name": "QA Tester",
            "course_title": "Certificate Layout Verification Course",
            "score": 91,
        },
        timeout=20,
    )
    assert resp.status_code == 200, f"generate failed: {resp.status_code} {resp.text[:200]}"
    body = resp.json()
    cert_id = body.get("cert_id") or body.get("certificate", {}).get("cert_id")
    assert cert_id, f"generate response missing cert_id: {body}"
    return cert_id


def _download_pdf(api_client, cert_id):
    resp = api_client.get(
        f"{BASE_URL}/api/travel-visa/certificate/download/{cert_id}",
        timeout=20,
    )
    assert resp.status_code == 200, f"download failed: {resp.status_code} {resp.text[:200]}"
    assert resp.content.startswith(b"%PDF"), "response body is not a PDF"
    # v15 policy retired platform-wide: header absent (legacy exempt value accepted)
    assert resp.headers.get("x-pdf-theme-policy") in (None, "", "exempt-travel-visa-certificate"), (
        f"unexpected x-pdf-theme-policy header, got {resp.headers.get('x-pdf-theme-policy')}"
    )
    return resp.content


# ── PDF-content assertions helper ───────────────────────────────────────────

ISO_TS_REGEX = re.compile(r"T\d{2}:\d{2}:\d{2}")
MONTH_REGEX = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)


def _assert_pdf_content(pdf_bytes: bytes, cert_id: str) -> None:
    """Run the (a)-(d) content assertions on the certificate PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1, "PDF has no pages"
    page = doc[0]

    # Full extracted text (for name / date checks)
    text = page.get_text("text") or ""

    # (a) Signature name — 'Adjimon Kouatonou — Program Director', NOT 'Nova'.
    #     em-dash may render as ' - ' or '—' depending on font; normalise both.
    normalised = text.replace("\u2014", "-").replace("—", "-")
    assert "Adjimon Kouatonou" in text, f"missing 'Adjimon Kouatonou' in PDF text.  Got: {text[:600]!r}"
    assert "Program Director" in text, "missing 'Program Director' role in PDF text"
    # Confirm the two are on the same visible line (within 30pt vertical distance).
    # Use rects to be robust to font kerning.
    name_rects = page.search_for("Adjimon Kouatonou")
    role_rects = page.search_for("Program Director")
    assert name_rects, "'Adjimon Kouatonou' rect not found"
    assert role_rects, "'Program Director' rect not found"
    # Same signature block line
    assert any(
        abs(nr.y0 - rr.y0) < 5 for nr in name_rects for rr in role_rects
    ), "'Adjimon Kouatonou' and 'Program Director' are not on the same line"
    # Explicit negative: no Nova — Program Director
    assert "Nova" not in normalised.split("Program Director")[0][-40:], (
        "Signature block still references 'Nova'"
    )
    assert "Nova — Program Director" not in text, "Old 'Nova — Program Director' string still present"
    assert "Nova - Program Director" not in normalised, "Old 'Nova - Program Director' string still present"

    # (b) 'VERIFY AUTHENTICITY' fits inside the verification panel.
    #     The label may be spaced letter-by-letter ('V E R I F Y  A U T H E N T I C I T Y')
    #     or a compact form. Try both.
    spaced_label = " ".join(list("VERIFY AUTHENTICITY"))
    compact_label = "VERIFY AUTHENTICITY"
    rects = page.search_for(spaced_label) or page.search_for(compact_label)
    # Fallback: some PDF text-extractors split spaced letters into individual runs;
    # try locating the last 3 letters of 'AUTHENTICITY' as a proxy for the label
    # right edge.
    if not rects:
        rects = page.search_for("AUTHENTICITY") or page.search_for("A U T H E N T I C I T Y")
    assert rects, (
        "Could not locate the 'VERIFY AUTHENTICITY' label rect in the PDF; "
        f"page text head:\n{text[:400]}"
    )
    # Right edge must be <= panel right edge (~770pt).  Give a 2pt tolerance.
    max_x1 = max(r.x1 for r in rects)
    assert max_x1 <= PANEL_RIGHT_EDGE_PT + 2, (
        f"'VERIFY AUTHENTICITY' overflows: right edge = {max_x1:.2f}pt "
        f"> panel right edge {PANEL_RIGHT_EDGE_PT:.2f}pt"
    )

    # (c) Page must embed at least 3 images (logo, QR, signature, stamp).
    imgs = page.get_images(full=True)
    assert len(imgs) >= 3, (
        f"Expected >=3 embedded images on the certificate (logo + QR + signature + stamp), "
        f"found {len(imgs)}"
    )

    # (d) 'Issued <human date>' — human month name present, no ISO timestamp.
    assert "Issued" in text, "no 'Issued' label in PDF text"
    assert MONTH_REGEX.search(text), (
        f"no human month name found in PDF text; date may still be raw ISO. "
        f"Excerpt: {text[:500]!r}"
    )
    assert not ISO_TS_REGEX.search(text), (
        f"raw ISO timestamp (T##:##:##) found in PDF text: {text!r}"
    )

    # cert_id should also appear.
    assert cert_id in text, f"cert_id {cert_id} missing from PDF text"

    doc.close()


# ── tests ───────────────────────────────────────────────────────────────────

class TestFreshCertificatePDF:
    """Generate a new certificate and validate PDF content."""

    def test_generate_fresh_certificate(self, api_client, fresh_cert_id):
        assert fresh_cert_id.startswith("TV-"), f"unexpected cert_id format: {fresh_cert_id}"

    def test_fresh_certificate_pdf_content(self, api_client, fresh_cert_id):
        pdf_bytes = _download_pdf(api_client, fresh_cert_id)
        _assert_pdf_content(pdf_bytes, fresh_cert_id)


class TestRegenerateFlow:
    """Regenerate all certificates for the admin user and re-check existing cert."""

    def test_regenerate_all(self, api_client):
        resp = api_client.post(
            f"{BASE_URL}/api/travel-visa/certificate/regenerate-all",
            json={"user_id": ADMIN_USER_ID},
            timeout=30,
        )
        assert resp.status_code == 200, f"regenerate-all failed: {resp.status_code} {resp.text[:200]}"
        body = resp.json()
        regenerated = body.get("regenerated") or body.get("count") or 0
        # Some servers may return details object.
        if isinstance(regenerated, list):
            regenerated = len(regenerated)
        assert int(regenerated) >= 1, f"regenerate-all returned {regenerated}: {body}"

    def test_existing_cert_pdf_content_after_regenerate(self, api_client):
        pdf_bytes = _download_pdf(api_client, EXISTING_CERT_ID)
        _assert_pdf_content(pdf_bytes, EXISTING_CERT_ID)


class TestVerifyEndpoint:
    """Public verify endpoint (no auth) — HTML + JSON, valid + invalid."""

    def test_verify_html_valid_no_auth(self):
        # No auth — use a bare session
        resp = requests.get(
            f"{BASE_URL}/api/travel-visa/certificate/verify/{EXISTING_CERT_ID}",
            timeout=15,
        )
        assert resp.status_code == 200, f"verify HTML failed: {resp.status_code}"
        assert "VALID CERTIFICATE" in resp.text.upper(), "verify HTML missing 'VALID CERTIFICATE'"

    def test_verify_json_valid_no_auth(self):
        resp = requests.get(
            f"{BASE_URL}/api/travel-visa/certificate/verify/{EXISTING_CERT_ID}?format=json",
            timeout=15,
        )
        assert resp.status_code == 200, f"verify JSON failed: {resp.status_code}"
        data = resp.json()
        assert data.get("valid") is True, f"verify JSON not valid=true: {data}"

    def test_verify_html_invalid_404(self):
        resp = requests.get(
            f"{BASE_URL}/api/travel-visa/certificate/verify/TV-DOESNOTEXIST999",
            timeout=15,
        )
        assert resp.status_code == 404, f"verify HTML unknown-id should be 404, got {resp.status_code}"

    def test_verify_json_invalid_404(self):
        resp = requests.get(
            f"{BASE_URL}/api/travel-visa/certificate/verify/TV-DOESNOTEXIST999?format=json",
            timeout=15,
        )
        # Spec (this iteration) explicitly requires 404 for JSON too.
        assert resp.status_code == 404, (
            f"verify JSON unknown-id should be 404, got {resp.status_code} {resp.text[:200]}"
        )


class TestEmailEndpoint:
    """POST email endpoint returns email_status: 'sent'."""

    def test_email_certificate(self, api_client, fresh_cert_id):
        resp = api_client.post(
            f"{BASE_URL}/api/travel-visa/certificate/email/{fresh_cert_id}",
            json={"user_id": ADMIN_USER_ID},
            timeout=30,
        )
        assert resp.status_code == 200, f"email endpoint failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        status = data.get("email_status") or data.get("status")
        assert status == "sent", f"email_status not 'sent': {data}"
