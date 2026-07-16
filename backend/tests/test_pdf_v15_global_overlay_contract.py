"""Contract: the Global PDF v15 visual policy is RETIRED platform-wide.

PDF bytes must pass through enforcement helpers completely unmodified —
no overlay chrome, no metadata stamping, no strict-mode blocking.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from middleware_pdf_policy import PDF_THEME_METADATA_KEY, enforce_pdf_v15_theme_bytes
from utils.pdf_v15_export import enforce_pdf_v15_enterprise


def _make_pdf(pages: int = 1) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(595, 842))
    for idx in range(1, pages + 1):
        pdf.setFont("Helvetica", 12)
        pdf.drawString(72, 760, f"dummy-document-page-{idx}")
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def test_policy_retired_bytes_pass_through_unmodified() -> None:
    payload = _make_pdf(2)
    themed, mode = enforce_pdf_v15_theme_bytes(payload)

    assert mode == "policy_retired"
    assert themed == payload

    reader = PdfReader(io.BytesIO(themed))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    metadata = dict(reader.metadata or {})

    assert "RealAICoach PDF v15" not in text
    assert "GLOBAL PDF V15 POLICY ACTIVE" not in text
    assert "Global PDF v15 enterprise runtime stamp" not in text
    assert PDF_THEME_METADATA_KEY not in metadata


def test_export_helper_is_validated_passthrough() -> None:
    payload = _make_pdf(1)
    assert enforce_pdf_v15_enterprise(payload, "contract-test") == payload


def test_export_helper_rejects_non_pdf_bytes() -> None:
    try:
        enforce_pdf_v15_enterprise(b"not a pdf", "contract-test")
        raise AssertionError("expected RuntimeError for non-PDF bytes")
    except RuntimeError as exc:
        assert "pdf-export-invalid-bytes" in str(exc)


def test_non_pdf_payload_mode_preserved() -> None:
    payload, mode = enforce_pdf_v15_theme_bytes(b"hello")
    assert payload == b"hello"
    assert mode == "non_pdf"


def test_middleware_not_mounted_in_server() -> None:
    source = Path("/app/backend/server.py").read_text(encoding="utf-8")
    assert "add_middleware(PdfVersionPolicyMiddleware)" not in source
