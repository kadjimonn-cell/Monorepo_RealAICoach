"""GTEC C5 Executive Compliance Report v2 — PDF regeneration tests.

Covers:
1. `_build_gtec_final_output_pdf_bundle` invoked with real report from
    db.gtec_scan_c5_reports (motor fetch, no import of module-level db)
2. Structural validation of the redesigned 3-page PDF (page 1 executive
    verdict, page 2 runtime enforcement, page 3 compliance appendix)
3. Synthetic PASS + FAIL variants rendered via `_render_gtec_final_output_pdf`
4. Trend helper edge case: no MONGO_URL -> [] and normal fetch <=7 rows
5. Email pipeline unit-level wiring — monkeypatch `send_catalog_template` and
   assert PDF attachment is forwarded (base64 valid PDF, correct filename)
"""
from __future__ import annotations

import asyncio
import base64
import copy
import io
import os
import re
import sys

import pytest

sys.path.append("/app/backend")

# Load .env early so MONGO_URL / DB_NAME / GTEC_PDF_GUARDRAIL_STRICT are set
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

# --- Module under test -----------------------------------------------------
from services import gtec_scan_v2 as svc  # noqa: E402
from services.gtec_scan_v2 import (  # noqa: E402
    _build_gtec_final_output_pdf_bundle,
    _fetch_gtec_c5_trend_rows,
    _render_gtec_final_output_pdf,
    REPORTS_COL,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _fetch_latest_report_via_motor() -> dict:
    """Motor client — fresh per call to avoid loop-binding gotcha."""
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run() -> dict:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        assert mongo_url and db_name, "MONGO_URL/DB_NAME missing in .env"
        client = AsyncIOMotorClient(mongo_url)
        try:
            doc = await client[db_name][REPORTS_COL].find_one(
                {}, sort=[("generated_at", -1)]
            )
            assert doc is not None, "no GTEC C5 report present in DB"
            if "_id" in doc:
                doc.pop("_id", None)
            return doc
        finally:
            client.close()

    return asyncio.run(_run())


@pytest.fixture(scope="module")
def latest_report() -> dict:
    return _fetch_latest_report_via_motor()


# ---------------------------------------------------------------------------
# 1. Bundle build from real latest report
# ---------------------------------------------------------------------------

class TestBundleBuild:
    def test_bundle_from_real_latest_report(self, latest_report):
        bundle = _build_gtec_final_output_pdf_bundle(latest_report)
        assert bundle is not None, "bundle build returned None"

        # Guardrails
        assert bundle.get("guardrail_passed") is True, (
            f"guardrail failures={bundle.get('guardrail_failures')}"
        )
        assert bundle.get("guardrail_failures") == []

        # Filename canonical pattern
        filename = bundle.get("filename") or ""
        assert filename.startswith("rac-compliance-"), filename
        assert filename.endswith(".pdf"), filename
        # Timestamp ends in Z before extension
        assert re.search(r"-\d{8}T\d{6}Z\.pdf$", filename), filename
        # task_id slug present (dashes not underscores)
        task_id = str(latest_report.get("task_id") or "")
        slug = re.sub(r"[^a-z0-9]+", "-", task_id.lower()).strip("-")[:80]
        assert slug in filename, f"task_id slug '{slug}' not in filename '{filename}'"

        # sha256 present + 64 hex chars
        sha = bundle.get("sha256") or ""
        assert isinstance(sha, str) and len(sha) == 64 and re.fullmatch(r"[0-9a-f]{64}", sha)

        # pdf_bytes valid PDF v1.4
        pdf_bytes = bundle.get("pdf_bytes")
        assert isinstance(pdf_bytes, bytes) and pdf_bytes.startswith(b"%PDF-1.4")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")

        # Attachment mirrors pdf_bytes as base64
        attachment = bundle.get("attachment") or {}
        assert attachment.get("filename") == filename
        assert attachment.get("content_type") == "application/pdf"
        decoded = base64.b64decode(attachment.get("content") or "")
        assert decoded == pdf_bytes


# ---------------------------------------------------------------------------
# 2. Structural validation across all 3 pages
# ---------------------------------------------------------------------------

class TestPdfStructure:
    @pytest.fixture(scope="class")
    def rendered(self, latest_report):
        bundle = _build_gtec_final_output_pdf_bundle(latest_report)
        assert bundle is not None
        return {
            "pdf_bytes": bundle["pdf_bytes"],
            "report": latest_report,
        }

    def _pypdf_page_text(self, pdf_bytes: bytes) -> list[str]:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(p.extract_text() or "") for p in reader.pages]

    def _pymupdf_page_text(self, pdf_bytes: bytes) -> list[str]:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return [doc.load_page(i).get_text() for i in range(doc.page_count)]
        finally:
            doc.close()

    def _pymupdf_page_images(self, pdf_bytes: bytes, page_index: int) -> list:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return doc.load_page(page_index).get_images(full=True)
        finally:
            doc.close()

    def test_three_pages(self, rendered):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(rendered["pdf_bytes"]))
        assert len(reader.pages) == 3, f"expected 3 pages, got {len(reader.pages)}"

    def test_page1_executive_verdict(self, rendered):
        # Merge pypdf + pymupdf extraction for resilience against font kerning
        text_py = self._pypdf_page_text(rendered["pdf_bytes"])
        text_mu = self._pymupdf_page_text(rendered["pdf_bytes"])

        def _combined(idx: int) -> str:
            return (text_py[idx] + "\n" + text_mu[idx]).upper()

        page1 = _combined(0)

        status = str(rendered["report"].get("status") or "UNKNOWN").upper()
        assert status in page1, f"verdict '{status}' missing in page1"

        for marker in (
            "C5 TRUST SCORE",
            "FINDINGS BY SEVERITY",
            "TRUST SCORE TREND",
            "COMPLIANCE DOMAIN SCORECARD",
            "LIVE OPS DASHBOARD",
        ):
            assert marker in page1, f"page1 missing marker: {marker}"

    def test_page2_runtime_enforcement(self, rendered):
        text_py = self._pypdf_page_text(rendered["pdf_bytes"])
        text_mu = self._pymupdf_page_text(rendered["pdf_bytes"])
        page2 = (text_py[1] + "\n" + text_mu[1]).upper()

        for marker in (
            "C5 RUNTIME SUMMARY",
            "WHITE SCREEN SENTRY STATUS",
            "EXTERNAL CERT STATUS",
            "INCIDENTS AUTO CLOSED",
            "VIEWPORT MATRIX",
        ):
            assert marker in page2, f"page2 missing legacy marker: {marker}"

    def test_page3_compliance_appendix(self, rendered):
        text_py = self._pypdf_page_text(rendered["pdf_bytes"])
        text_mu = self._pymupdf_page_text(rendered["pdf_bytes"])
        page3 = text_py[2] + "\n" + text_mu[2]
        page3_up = page3.upper()

        # Guardrail-locked headings
        assert re.search(r"§?\s*12\s+FINAL\s+OUTPUT", page3_up), "§12 heading missing"
        assert re.search(r"§?\s*13\s*V3\s+FINAL\s+OUTPUT", page3_up), "§13 v3 heading missing"

        # Literal fields
        for field in ("TASK_ID", "EXECUTION_HASH", "SYSTEM_STATUS", "CONFIDENCE_LEVEL"):
            assert field in page3_up, f"§12/§13 field missing: {field}"

    def test_brand_marker_and_logo(self, rendered):
        text_py = self._pypdf_page_text(rendered["pdf_bytes"])
        full = "\n".join(text_py)
        assert "RealAICoach Security" in full, "brand heading missing"

        # Page1 must contain >=2 images (logo + QR)
        imgs = self._pymupdf_page_images(rendered["pdf_bytes"], 0)
        assert len(imgs) >= 2, (
            f"page1 must contain at least 2 images (logo + QR), got {len(imgs)}"
        )


# ---------------------------------------------------------------------------
# 3. Synthetic PASS + FAIL variants
# ---------------------------------------------------------------------------

class TestVariantRendering:
    def _override(self, base_report: dict, *, status: str) -> dict:
        r = copy.deepcopy(base_report)
        r["status"] = status
        # Simulate different domain scorecard + trust
        r.setdefault("c5_notification_snapshot", {})
        r["c5_notification_snapshot"] = copy.deepcopy(r["c5_notification_snapshot"] or {})
        trust = r["c5_notification_snapshot"].setdefault("trust", {})
        if status == "PASS":
            trust["score_percent"] = 96.0
            trust["passed_gates"] = 12
            trust["total_gates"] = 12
            r["critical_vulns"] = 0
            r["high_vulns"] = 0
        else:
            trust["score_percent"] = 41.0
            trust["passed_gates"] = 5
            trust["total_gates"] = 12
            r["critical_vulns"] = 3
            r["high_vulns"] = 7
        # bump task_id slightly to avoid trend-history self-exclusion collision
        r["task_id"] = f"{r.get('task_id','gtec_c5')}_variant_{status.lower()}"
        return r

    def _page_texts(self, pdf_bytes: bytes) -> list[str]:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return [doc.load_page(i).get_text() for i in range(doc.page_count)]
        finally:
            doc.close()

    @pytest.mark.parametrize("variant", ["PASS", "FAIL"])
    def test_variant_renders(self, latest_report, variant):
        report = self._override(latest_report, status=variant)
        pdf_bytes = _render_gtec_final_output_pdf(report)
        assert isinstance(pdf_bytes, bytes) and pdf_bytes.startswith(b"%PDF-")

        # 3 pages
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 3, (
            f"variant={variant}: expected 3 pages, got {len(reader.pages)}"
        )

        # Verdict text on page 1
        pages = self._page_texts(pdf_bytes)
        assert variant in pages[0].upper(), (
            f"variant={variant}: verdict text missing on page1"
        )


# ---------------------------------------------------------------------------
# 4. Trend helper contracts
# ---------------------------------------------------------------------------

class TestTrendHelper:
    def test_returns_up_to_seven_oldest_first(self, latest_report):
        rows = _fetch_gtec_c5_trend_rows(latest_report, limit=7)
        assert isinstance(rows, list)
        assert len(rows) <= 7

        current = str(latest_report.get("task_id") or "")
        for r in rows:
            # Keys contract
            for key in ("status", "trust_percent", "generated_at"):
                assert key in r, f"trend row missing key {key}: {r}"
            assert r.get("status") != current  # excludes current task by construction

        # oldest -> newest ordering by generated_at
        gens = [row.get("generated_at") or "" for row in rows]
        assert gens == sorted(gens), f"trend rows not oldest→newest: {gens}"

    def test_no_mongo_url_returns_empty(self, latest_report, monkeypatch):
        monkeypatch.delenv("MONGO_URL", raising=False)
        rows = _fetch_gtec_c5_trend_rows(latest_report, limit=7)
        assert rows == []


# ---------------------------------------------------------------------------
# 5. Email dispatch pipeline (unit level — NO REAL EMAIL)
# ---------------------------------------------------------------------------

class TestEmailDispatchWiring:
    """Verifies pdf_bundle -> pdf_attachment -> send_catalog_template payload wiring.

    We do NOT run the full scan (takes minutes). We invoke `_email_report_to_admins`
    with a mocked motor db and monkeypatch send_catalog_template so no real email
    is sent. This exercises services/gtec_scan_v2.py lines ~4561-4667.
    """

    def test_pdf_attachment_forwarded_to_send_catalog(self, latest_report, monkeypatch):
        captured = {"calls": []}

        async def fake_send(recipient_email, template_key, **kwargs):
            captured["calls"].append({
                "recipient": recipient_email,
                "template_key": template_key,
                "attachments": kwargs.get("attachments"),
                "pdf_attachment_name": kwargs.get("pdf_attachment_name"),
                "pdf_guardrail_passed": kwargs.get("pdf_guardrail_passed"),
            })
            return {"success": True}

        # send_catalog_template is imported *inside* _email_report_to_admins;
        # patch the source module so the local import binds to our fake.
        import utils.email_service as email_svc
        monkeypatch.setattr(email_svc, "send_catalog_template", fake_send, raising=True)

        # Build a fake motor-like db with:
        #  * SETTINGS_COL.find_one -> {} (email_enabled default True)
        #  * users.find(...) yielding one admin
        #  * REPORTS_COL.update_one -> no-op
        class _FakeCursor:
            def __init__(self, items):
                self._items = list(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._items:
                    raise StopAsyncIteration
                return self._items.pop(0)

        class _FakeCollection:
            def __init__(self, name):
                self._name = name

            async def find_one(self, *_a, **_kw):
                return {}

            def find(self, *_a, **_kw):
                if self._name == "users":
                    return _FakeCursor([{"email": "admin@realaicoach.app"}])
                return _FakeCursor([])

            async def update_one(self, *_a, **_kw):
                class _R:
                    modified_count = 0
                return _R()

            async def insert_one(self, *_a, **_kw):
                class _R:
                    inserted_id = "x"
                return _R()

        class _FakeDB:
            def __getitem__(self, name):
                return _FakeCollection(name)

        # Also monkeypatch legacy_mirror_write_enabled to avoid extra IO
        async def _no_legacy(_db):
            return False
        monkeypatch.setattr(svc, "legacy_mirror_write_enabled", _no_legacy, raising=False)

        # Ensure c5 snapshot present so we skip the rebuild branch
        report = copy.deepcopy(latest_report)
        report.setdefault("c5_notification_snapshot", report.get("c5_notification_snapshot") or {"trust": {"score_percent": 0}})

        asyncio.run(svc._email_report_to_admins(_FakeDB(), report))

        assert captured["calls"], "send_catalog_template was never invoked"
        call = captured["calls"][0]
        assert call["template_key"] == "gtec_scan_v2_report"

        attachments = call["attachments"]
        assert isinstance(attachments, list) and len(attachments) == 1, attachments
        att = attachments[0]

        # Attachment filename / content_type
        assert att.get("content_type") == "application/pdf"
        fname = att.get("filename") or ""
        assert fname.startswith("rac-compliance-"), fname
        assert fname.endswith(".pdf"), fname
        assert re.search(r"-\d{8}T\d{6}Z\.pdf$", fname), fname

        # Base64 content decodes to a valid PDF
        decoded = base64.b64decode(att.get("content") or "")
        assert decoded.startswith(b"%PDF-1.4")
        assert decoded.rstrip().endswith(b"%%EOF")

        # payload metadata carries guardrail bit
        assert call["pdf_attachment_name"] == fname
        assert call["pdf_guardrail_passed"] is True


# ---------------------------------------------------------------------------
# 6. Backend health smoke — ensures no import errors after change
# ---------------------------------------------------------------------------

class TestBackendHealth:
    def test_api_health(self):
        import requests
        base = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
        r = requests.get(f"{base}/api/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "healthy"
