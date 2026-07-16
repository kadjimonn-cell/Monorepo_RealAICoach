"""
Iteration 849 — Verify _dispatch_certificate_completion_email attaches BOTH
portrait AND landscape certificate PDFs to the learner completion email.

Approach (per review request):
- Monkeypatch utils.email_service.send_email (async) to CAPTURE kwargs.
- Also patch utils.email_service.is_email_configured -> True so the code path
  is not short-circuited.
- Call _dispatch_certificate_completion_email(cert_doc, force=True) with a
  synthetic cert dict containing learner_email.
- Assert:
   * dispatcher returned True (send was invoked & our patched send returned success)
   * attachments length == 2
   * filenames match realaicoach-certificate-{verification_id}-portrait.pdf
                     realaicoach-certificate-{verification_id}-landscape.pdf
   * both content_type == application/pdf
   * both content base64 non-empty and decodes to bytes starting with %PDF
   * portrait payload page size ~ A4 portrait (210x297mm)
   * landscape payload page size ~ A4 landscape (297x210mm)
   * both PDFs contain enlarged blue-ink signature (>=45mm wide, all above line)
     — reuses the blue-ink detection from iteration_848.

Also runs regression checks:
- Backend /api/health -> 200 (no import errors after edit)
- All test cases assert isolated (dispatcher does NOT talk to real Resend / DB writes).

CRITICAL: This test does NOT trigger a real email dispatch. It relies on
monkeypatching send_email at the module symbol imported inside the function
(the dispatcher does `from utils.email_service import send_email` at call
time, so we patch `utils.email_service.send_email`).
"""
import asyncio
import base64
import os
import sys

import numpy as np
import pytest
import requests

# Ensure /app/backend on path for direct import
sys.path.insert(0, "/app/backend")

BASE_URL = "http://localhost:8001"


def _run(coro_factory):
    """Run an async scenario with a fresh Motor client bound to a fresh loop.
    Patches routes.ai_learning_hub.db and any other module `db` bindings so the
    dispatcher's DB reads use the fresh loop (avoids Motor loop-binding gotcha).
    coro_factory: async fn taking no args (or (db,)) -> result.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=loop)
        fresh_db = client[os.environ["DB_NAME"]]

        patched_modules = []
        for mod_name in ("routes.ai_learning_hub", "routes.db"):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "db"):
                patched_modules.append((mod, mod.db))
                mod.db = fresh_db

        try:
            # allow factory of 0 or 1 arg
            try:
                coro = coro_factory(fresh_db)
            except TypeError:
                coro = coro_factory()
            return loop.run_until_complete(coro)
        finally:
            for mod, orig in patched_modules:
                mod.db = orig
            client.close()
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# =========================================================
# Health / import regression
# =========================================================
def test_backend_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200, f"health failed: {r.status_code}"
    data = r.json()
    assert isinstance(data, dict)


def test_import_dispatcher_and_builders():
    """Regression: no import errors after the change."""
    from routes.ai_learning_hub import (  # noqa: F401
        _dispatch_certificate_completion_email,
        _build_certificate_pdf_base64,
        _build_certificate_pdf_bytes,
    )
    import utils.email_service as email_service  # noqa: F401
    assert callable(email_service.send_email)
    assert callable(email_service.is_email_configured)


# =========================================================
# Core dispatcher attachments test
# =========================================================
@pytest.fixture(scope="module")
def synthetic_cert_doc():
    return {
        "verification_id": "TEST-SIG-EMAIL-ATTACH",
        "certificate_id": "TEST-SIG-EMAIL-ATTACH",
        "user_id": "u_test_email",
        "learner_email": "test-capture-only@example.invalid",
        "learner_name": "Test Learner",
        "course_title": "AI Foundations",
        "issued_at": "2026-01-15T00:00:00Z",
        "signer_name": "Adjimon Kouatonou",
        "signer_role": "Chief Executive Officer",
        "issued_by": "RealAICoach",
    }


def _run_async(coro_factory_or_coro):
    """Compat wrapper that accepts either an awaitable or an async factory taking (db,)."""
    if asyncio.iscoroutine(coro_factory_or_coro):
        # wrap into a factory so we use fresh loop each call
        _c = coro_factory_or_coro

        async def _factory(_db):
            return await _c
        return _run(_factory)
    return _run(coro_factory_or_coro)


def test_dispatch_certificate_email_attaches_portrait_and_landscape(synthetic_cert_doc, monkeypatch):
    """Verify dispatcher builds and passes TWO attachments (portrait + landscape)."""
    import utils.email_service as email_service
    from routes import ai_learning_hub

    captured = {}

    async def _fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"success": True, "id": "fake-msg-id"}

    def _fake_is_email_configured():
        return True

    # Patch symbols at the module the dispatcher imports FROM at call time.
    monkeypatch.setattr(email_service, "send_email", _fake_send_email)
    monkeypatch.setattr(email_service, "is_email_configured", _fake_is_email_configured)

    async def _scenario(_db):
        return await ai_learning_hub._dispatch_certificate_completion_email(
            synthetic_cert_doc, force=True
        )

    ok = _run(_scenario)
    assert ok is True, "dispatcher returned False — did send_email get called?"

    # send_email must have been invoked and captured kwargs
    assert "attachments" in captured, "attachments kwarg missing"
    attachments = captured["attachments"]
    assert isinstance(attachments, list), f"attachments not list: {type(attachments)}"
    assert len(attachments) == 2, f"expected exactly 2 attachments, got {len(attachments)}: {[a.get('filename') for a in attachments]}"

    vid = synthetic_cert_doc["verification_id"]
    expected_portrait = f"realaicoach-certificate-{vid}-portrait.pdf"
    expected_landscape = f"realaicoach-certificate-{vid}-landscape.pdf"

    filenames = [a.get("filename") for a in attachments]
    assert expected_portrait in filenames, f"portrait filename missing. got={filenames}"
    assert expected_landscape in filenames, f"landscape filename missing. got={filenames}"

    for a in attachments:
        assert a.get("content_type") == "application/pdf", f"bad content_type: {a.get('content_type')}"
        content_b64 = a.get("content")
        assert isinstance(content_b64, str) and len(content_b64) > 100, "empty base64 content"
        try:
            raw = base64.b64decode(content_b64)
        except Exception as e:
            pytest.fail(f"attachment {a.get('filename')} content is not valid base64: {e}")
        assert raw[:5] == b"%PDF-", f"attachment {a.get('filename')} not a PDF (first bytes: {raw[:8]!r})"
        assert len(raw) > 10_000, f"attachment {a.get('filename')} too small ({len(raw)} bytes)"


# =========================================================
# Page-size + blue-ink validation on captured attachments
# =========================================================
def _decode_attachment(attachments, suffix):
    for a in attachments:
        if a.get("filename", "").endswith(suffix):
            return base64.b64decode(a["content"])
    raise AssertionError(f"attachment with suffix {suffix} not found")


def _detect_blue_ink_bbox(pdf_bytes: bytes, layout: str):
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

    footer_ymin_px = pix.height - int(60 * px_per_mm_y)
    footer_mask = blue_mask.copy()
    footer_mask[:footer_ymin_px, :] = False
    fys, fxs = np.where(footer_mask)
    if len(fxs) == 0:
        return (0.0, 0.0, 0, 0, 0.0, 0, pix.width, pix.height, page_w_mm, page_h_mm)
    x0, x1 = int(fxs.min()), int(fxs.max())
    y0, y1 = int(fys.min()), int(fys.max())
    w_mm = (x1 - x0) / px_per_mm_x
    h_mm = (y1 - y0) / px_per_mm_y
    sig_y_mm = 31.0
    sig_line_y_px = pix.height - int(sig_y_mm * px_per_mm_y)
    ink_above = int((fys < sig_line_y_px).sum())
    ink_below = int((fys > sig_line_y_px).sum())
    gap_mm = (sig_line_y_px - y1) / px_per_mm_y
    return (w_mm, h_mm, ink_above, ink_below, gap_mm, int(len(fxs)), pix.width, pix.height, page_w_mm, page_h_mm)


@pytest.fixture(scope="module")
def captured_attachments(synthetic_cert_doc):
    """Run dispatcher once (with fresh monkeypatch) and return captured attachments list."""
    import utils.email_service as email_service
    from routes import ai_learning_hub

    captured = {}

    async def _fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"success": True, "id": "fake-msg-id"}

    def _fake_is_email_configured():
        return True

    orig_send = email_service.send_email
    orig_cfg = email_service.is_email_configured
    email_service.send_email = _fake_send_email
    email_service.is_email_configured = _fake_is_email_configured
    try:
        async def _scenario(_db):
            return await ai_learning_hub._dispatch_certificate_completion_email(
                synthetic_cert_doc, force=True
            )
        ok = _run(_scenario)
        assert ok is True
        assert "attachments" in captured
        return captured["attachments"]
    finally:
        email_service.send_email = orig_send
        email_service.is_email_configured = orig_cfg


def test_attachment_portrait_page_size_is_a4_portrait(captured_attachments):
    import fitz
    pdf = _decode_attachment(captured_attachments, "-portrait.pdf")
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc[0]
    # A4 portrait = 210x297mm = 595.28 x 841.89 pt
    w_pt, h_pt = page.rect.width, page.rect.height
    # portrait: height > width
    assert h_pt > w_pt, f"portrait attachment is not portrait orientation: w={w_pt} h={h_pt}"
    # allow small rounding tolerance
    assert 590 <= w_pt <= 600, f"portrait width {w_pt}pt not ~A4 (595pt)"
    assert 836 <= h_pt <= 848, f"portrait height {h_pt}pt not ~A4 (842pt)"


def test_attachment_landscape_page_size_is_a4_landscape(captured_attachments):
    import fitz
    pdf = _decode_attachment(captured_attachments, "-landscape.pdf")
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc[0]
    w_pt, h_pt = page.rect.width, page.rect.height
    # landscape: width > height
    assert w_pt > h_pt, f"landscape attachment is not landscape orientation: w={w_pt} h={h_pt}"
    assert 836 <= w_pt <= 848, f"landscape width {w_pt}pt not ~A4-landscape (842pt)"
    assert 590 <= h_pt <= 600, f"landscape height {h_pt}pt not ~A4-landscape (595pt)"


def test_attachment_portrait_has_enlarged_blue_signature(captured_attachments):
    pdf = _decode_attachment(captured_attachments, "-portrait.pdf")
    w_mm, h_mm, above, below, gap_mm, total, *_ = _detect_blue_ink_bbox(pdf, "portrait")
    print(f"[email-attach portrait] w={w_mm:.2f}mm h={h_mm:.2f}mm above={above} below={below} gap={gap_mm:.2f}mm total={total}")
    assert total > 500, f"insufficient blue-ink pixels in portrait attachment: {total}"
    assert w_mm >= 45.0, f"portrait signature width {w_mm:.2f}mm not enlarged (< 45mm)"
    assert below == 0, f"{below} blue-ink pixels below signature line in portrait attachment"
    assert above > 0
    assert gap_mm >= 0.5, f"portrait ink too close to line: gap {gap_mm:.2f}mm"


def test_attachment_landscape_has_enlarged_blue_signature(captured_attachments):
    pdf = _decode_attachment(captured_attachments, "-landscape.pdf")
    w_mm, h_mm, above, below, gap_mm, total, *_ = _detect_blue_ink_bbox(pdf, "landscape")
    print(f"[email-attach landscape] w={w_mm:.2f}mm h={h_mm:.2f}mm above={above} below={below} gap={gap_mm:.2f}mm total={total}")
    assert total > 500, f"insufficient blue-ink pixels in landscape attachment: {total}"
    assert w_mm >= 45.0, f"landscape signature width {w_mm:.2f}mm not enlarged (< 45mm)"
    assert below == 0, f"{below} blue-ink pixels below signature line in landscape attachment"
    assert above > 0
    assert gap_mm >= 0.5, f"landscape ink too close to line: gap {gap_mm:.2f}mm"


# =========================================================
# Edge cases
# =========================================================
def test_dispatcher_returns_false_when_no_learner_email(monkeypatch):
    from routes import ai_learning_hub
    doc = {"verification_id": "TEST-NO-EMAIL"}

    async def _scenario(_db):
        return await ai_learning_hub._dispatch_certificate_completion_email(doc, force=True)

    ok = _run(_scenario)
    assert ok is False


def test_dispatcher_returns_false_when_email_not_configured(synthetic_cert_doc, monkeypatch):
    """When is_email_configured returns False, dispatcher must NOT invoke send_email."""
    import utils.email_service as email_service
    from routes import ai_learning_hub

    invoked = {"count": 0}

    async def _fake_send_email(**kwargs):
        invoked["count"] += 1
        return {"success": True}

    monkeypatch.setattr(email_service, "is_email_configured", lambda: False)
    monkeypatch.setattr(email_service, "send_email", _fake_send_email)

    async def _scenario(_db):
        return await ai_learning_hub._dispatch_certificate_completion_email(
            synthetic_cert_doc, force=True
        )

    ok = _run(_scenario)
    assert ok is False
    assert invoked["count"] == 0, "send_email should NOT be invoked when email not configured"
