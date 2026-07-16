"""
Iteration 848 — Programmatic validation of enlarged handwritten signature on
AI Learning Hub Certificate of Completion PDF.

Covers:
- Endpoint regression: /api/ai-learn/certificates, /api/ai-learn/certificates/{id}/pdf/file, .../png/file
- Verify endpoint: /api/ai-learn/certificates/verify/{id}
- Direct _build_certificate_pdf_bytes call (portrait + landscape) with blue-ink
  bounds validation using PyMuPDF (fitz)
"""
import io
import os
import sys
import re
import numpy as np
import pytest
import requests
from PIL import Image

# Use internal localhost (external Cloudflare-challenged for automation)
BASE_URL = "http://localhost:8001"

# Ensure /app/backend on path for direct PDF builder import
sys.path.insert(0, "/app/backend")


# =========================================================
# Fixtures
# =========================================================
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
    )
    assert r.status_code == 200, f"free user login failed: {r.status_code} {r.text[:400]}"
    return s


# =========================================================
# Backend health / import regression
# =========================================================
def test_backend_health():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_import_build_certificate_pdf_bytes():
    """No import/startup error after signature enlargement change."""
    from routes.ai_learning_hub import _build_certificate_pdf_bytes  # noqa: F401
    from routes.ai_learning_hub import _draw_cropped_signature  # noqa: F401
    from routes.ai_learning_hub import _get_cropped_signature_image  # noqa: F401


# =========================================================
# GET /api/ai-learn/certificates (auth users)
# =========================================================
def test_list_certificates_admin_ok(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/certificates")
    assert r.status_code == 200
    data = r.json()
    assert "certificates" in data
    assert isinstance(data["certificates"], list)


def test_list_certificates_free_ok(free_session):
    r = free_session.get(f"{BASE_URL}/api/ai-learn/certificates")
    assert r.status_code == 200
    data = r.json()
    assert "certificates" in data


def test_list_certificates_requires_auth():
    r = requests.get(f"{BASE_URL}/api/ai-learn/certificates")
    assert r.status_code == 401


# =========================================================
# Live PDF/PNG endpoint validation (needs an issued cert)
# =========================================================
def _find_or_issue_cert(session: requests.Session) -> str | None:
    r = session.get(f"{BASE_URL}/api/ai-learn/certificates")
    if r.status_code != 200:
        return None
    certs = r.json().get("certificates") or []
    if certs:
        return certs[0].get("verification_id") or certs[0].get("certificate_id")
    return None


def test_pdf_endpoint_returns_valid_pdf(admin_session):
    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present — endpoint regression skipped (direct builder covers content).")
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/certificates/{vid}/pdf/file",
        params={"layout": "portrait"},
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    assert r.content[:8] == b"%PDF-1.4" or r.content[:5] == b"%PDF-", "not a PDF"
    assert len(r.content) > 20_000


def test_pdf_endpoint_landscape(admin_session):
    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present.")
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/certificates/{vid}/pdf/file",
        params={"layout": "landscape"},
    )
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_png_endpoint(admin_session):
    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present.")
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/certificates/{vid}/png/file",
        params={"layout": "portrait"},
    )
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"


def test_verify_endpoint_returns_valid(admin_session):
    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present.")
    r = admin_session.get(f"{BASE_URL}/api/ai-learn/certificates/verify/{vid}")
    assert r.status_code == 200
    data = r.json()
    # Response should contain certificate data
    assert isinstance(data, dict)


# =========================================================
# PROGRAMMATIC PDF INK VALIDATION (core of this iteration)
# =========================================================
def _detect_blue_ink_bbox(pdf_bytes: bytes, layout: str):
    """Return (width_mm, height_mm, ink_above_line, ink_below_line, gap_above_line_mm, total_blue_px)."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=200, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

    if layout == "portrait":
        page_w_mm, page_h_mm = 210, 297
    else:
        page_w_mm, page_h_mm = 297, 210
    px_per_mm_x = pix.width / page_w_mm
    px_per_mm_y = pix.height / page_h_mm

    R = arr[..., 0].astype(int)
    G = arr[..., 1].astype(int)
    B = arr[..., 2].astype(int)
    blue_mask = (B > 100) & (R < 120) & (G < 120) & (B - R > 30) & (B - G > 20)

    # Restrict to footer signature area (bottom 60mm)
    footer_ymin_px = pix.height - int(60 * px_per_mm_y)
    footer_mask = blue_mask.copy()
    footer_mask[:footer_ymin_px, :] = False

    fys, fxs = np.where(footer_mask)
    if len(fxs) == 0:
        return (0.0, 0.0, 0, 0, 0.0, 0)

    x0, x1 = int(fxs.min()), int(fxs.max())
    y0, y1 = int(fys.min()), int(fys.max())
    w_mm = (x1 - x0) / px_per_mm_x
    h_mm = (y1 - y0) / px_per_mm_y

    # Signature underline default = signature_y_mm from page bottom = 31mm
    sig_y_mm = 31.0
    sig_line_y_px = pix.height - int(sig_y_mm * px_per_mm_y)
    ink_above = int((fys < sig_line_y_px).sum())
    ink_below = int((fys > sig_line_y_px).sum())
    gap_mm = (sig_line_y_px - y1) / px_per_mm_y  # distance from ink bottom to line
    return (w_mm, h_mm, ink_above, ink_below, gap_mm, int(len(fxs)))


@pytest.fixture(scope="module")
def synthetic_cert_dict():
    return {
        "verification_id": "TEST-SIG-VALIDATION",
        "certificate_id": "TEST-SIG-VALIDATION",
        "user_id": "u_test",
        "learner_name": "Test Learner",
        "course_title": "AI Foundations",
        "issued_at": "2026-01-15T00:00:00Z",
        "signer_name": "Adjimon Kouatonou",
        "signer_role": "Chief Executive Officer",
        "issued_by": "RealAICoach",
    }


def test_direct_pdf_portrait_signature_size_and_position(synthetic_cert_dict):
    from routes.ai_learning_hub import _build_certificate_pdf_bytes

    pdf = _build_certificate_pdf_bytes(synthetic_cert_dict, variant="print", layout="portrait")
    assert pdf[:5] == b"%PDF-"
    w_mm, h_mm, above, below, gap_mm, total = _detect_blue_ink_bbox(pdf, "portrait")
    print(f"[portrait] ink w={w_mm:.2f}mm h={h_mm:.2f}mm above={above} below={below} gap_to_line={gap_mm:.2f}mm total_px={total}")

    # Must have significant blue ink
    assert total > 500, f"insufficient blue-ink pixels detected: {total}"
    # Enlarged: > 45mm (old was ~33mm; +40% => ~46mm; measured ~56.9mm)
    assert w_mm >= 45.0, f"signature width {w_mm:.2f}mm is NOT >= 45mm (target after +40% enlargement)"
    # ALL ink above the line
    assert below == 0, f"{below} blue-ink pixels detected BELOW signature line (should be zero)"
    assert above > 0
    # Ink should end ABOVE the line, not overlap it — gap should be positive small mm
    assert gap_mm >= 0.5, f"ink bottom too close to line: gap {gap_mm:.2f}mm"


def test_direct_pdf_landscape_signature_size_and_position(synthetic_cert_dict):
    from routes.ai_learning_hub import _build_certificate_pdf_bytes

    pdf = _build_certificate_pdf_bytes(synthetic_cert_dict, variant="print", layout="landscape")
    assert pdf[:5] == b"%PDF-"
    w_mm, h_mm, above, below, gap_mm, total = _detect_blue_ink_bbox(pdf, "landscape")
    print(f"[landscape] ink w={w_mm:.2f}mm h={h_mm:.2f}mm above={above} below={below} gap_to_line={gap_mm:.2f}mm total_px={total}")

    assert total > 500, f"insufficient blue-ink pixels: {total}"
    assert w_mm >= 45.0, f"landscape signature width {w_mm:.2f}mm NOT >= 45mm"
    assert below == 0
    assert above > 0
    assert gap_mm >= 0.5


def test_cropped_signature_helper_returns_image():
    from routes.ai_learning_hub import _get_cropped_signature_image

    result = _get_cropped_signature_image()
    assert result is not None, "cropped signature image loader returned None"
    reader, aspect = result
    assert aspect > 1.0, f"expected wide signature (aspect>1), got {aspect}"


def test_served_portrait_pdf_endpoint_has_enlarged_signature(admin_session):
    """REGRESSION: The portrait PDF served by /pdf/file endpoint must have the enlarged signature.
    Landscape is always rebuilt (bypasses cache) so it correctly reflects the change; portrait uses
    the cached blob keyed by _certificate_render_key which does NOT include CERTIFICATE_SIGNATURE_PROFILE_VERSION.
    """
    import fitz

    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present.")

    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/certificates/{vid}/pdf/file",
        params={"layout": "portrait"},
    )
    assert r.status_code == 200
    w_mm, _, above, below, gap_mm, total = _detect_blue_ink_bbox(r.content, "portrait")
    print(f"[endpoint portrait] w={w_mm:.2f}mm above={above} below={below} total={total}")

    # This documents the bug: expected >=45mm but served value may be ~33mm (stale cache)
    assert below == 0, f"portrait PDF signature ink appears BELOW line ({below} px) — regression"
    assert w_mm >= 45.0, (
        f"SERVED portrait PDF ink width is {w_mm:.2f}mm (< 45mm target). "
        "Likely stale storage cache — _certificate_render_key does NOT include "
        "CERTIFICATE_SIGNATURE_PROFILE_VERSION, so the enlargement change did not invalidate the cached PDF. "
        "Fix: bump CERTIFICATE_RENDER_PROFILE_VERSION or include signature profile version in _certificate_render_key."
    )


def test_served_landscape_pdf_endpoint_has_enlarged_signature(admin_session):
    """Landscape is always rebuilt fresh — should correctly show enlarged signature."""
    vid = _find_or_issue_cert(admin_session)
    if not vid:
        pytest.skip("No admin certificate present.")
    r = admin_session.get(
        f"{BASE_URL}/api/ai-learn/certificates/{vid}/pdf/file",
        params={"layout": "landscape"},
    )
    assert r.status_code == 200
    w_mm, _, above, below, gap_mm, total = _detect_blue_ink_bbox(r.content, "landscape")
    print(f"[endpoint landscape] w={w_mm:.2f}mm above={above} below={below} total={total}")
    assert below == 0
    assert w_mm >= 45.0, f"landscape served ink width {w_mm:.2f}mm < 45mm"


def test_signature_larger_than_pre_change_baseline(synthetic_cert_dict):
    """Sanity: measured width should be materially larger than the pre-change ~33mm baseline."""
    from routes.ai_learning_hub import _build_certificate_pdf_bytes

    pdf = _build_certificate_pdf_bytes(synthetic_cert_dict, variant="print", layout="portrait")
    w_mm, _, _, _, _, _ = _detect_blue_ink_bbox(pdf, "portrait")
    # 40% larger than 33mm ~= 46mm; enforce >= 45mm strictly, and note it should be larger
    assert w_mm >= 45.0
    # Not so large that it overflows the certificate
    assert w_mm <= 90.0, f"signature width {w_mm:.2f}mm exceeds safe box bound"
