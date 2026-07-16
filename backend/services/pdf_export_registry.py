"""Centralized PDF export registry for governance at scale."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_NAMING_POLICY = "rac-{doc_type}-v15-{entity_id}-{yyyymmddThhmmssZ}.pdf"
CANONICAL_THEME_POLICY = (
    "Global runtime enforcement via PdfVersionPolicyMiddleware "
    "(x-pdf-theme-policy=enforced-v15), canonical logo-tile, and CI guard"
)

_ROUTE_PATTERN = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*(?:f|rf|fr)?[\"']([^\"']+)[\"']")
_PREFIX_PATTERN = re.compile(r"APIRouter\([^\)]*prefix\s*=\s*[\"']([^\"']+)[\"']")


@dataclass
class PDFExportRecord:
    doc_type: str
    endpoint: str
    http_method: str
    owner_module: str
    naming_policy: str
    theme_policy: str
    runtime_enforced: bool
    required_ci_guard: str
    source_file: str


DOC_TYPE_OVERRIDES = {
    "/api/payments/receipt/{payment_id}/pdf": "receipt",
    "/api/payments/invoice/{payment_id}/pdf": "invoice",
    "/api/payments/export-pdf": "payment-history",
    "/api/admin/gtec-scan-v2/report-pdf/{task_id}": "compliance",
    "/api/careers/offers/{offer_id}/pdf": "job-offer",
    "/api/careers/offers/public/{token}/pdf": "job-offer",
    "/api/interview-content/{interview_id}/export/pdf": "interview-content",
    "/api/accessibility/wcag-report/pdf": "compliance",
    "/api/admin/platform-health/enterprise-standard/enforcement/{run_id}/compliance-report/pdf": "compliance",
    "/api/id-checker/admin/export/pdf": "id-checker-report",
    "/api/id-verification/admin/export/pdf": "id-checker-report",
    "/api/admin/export/pdf": "id-checker-report",
    "/api/admin/ai-autofix/export/pdf": "ai-autofix-report",
    "/api/admin/payments-tax-intelligence/export/pdf": "payments-tax-intelligence",
    "/api/admin/ticket-feedback/export/pdf": "ticket-feedback-report",
    "/api/careers/comparison/export-pdf": "candidate-comparison",
    "/api/interview-performance/{interview_id}/export/pdf": "interview-performance",
    "/api/payments/tax-statement/pdf": "tax-statement",
    "/api/support/nova/export/pdf/{conversation_id}": "transcript",
}


def _normalize_endpoint(path: str) -> str:
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    if p.startswith("/api/"):
        return p
    if p == "/api":
        return p
    return "/api" + p


def _derive_doc_type(endpoint: str) -> str:
    ep = endpoint.lower()
    if "autofix" in ep:
        return "ai-autofix-report"
    if "tax-intelligence" in ep:
        return "payments-tax-intelligence"
    if "ticket-feedback" in ep:
        return "ticket-feedback-report"
    if "comparison" in ep and "careers" in ep:
        return "candidate-comparison"
    if "interview-performance" in ep:
        return "interview-performance"
    if "tax-statement" in ep:
        return "tax-statement"
    if "receipt" in ep:
        return "receipt"
    if "invoice" in ep:
        return "invoice"
    if "payment" in ep and "export-pdf" in ep:
        return "payment-history"
    if "job" in ep and "offer" in ep:
        return "job-offer"
    if "interview" in ep and "content" in ep:
        return "interview-content"
    if "compliance" in ep or "report-pdf" in ep or "wcag" in ep:
        return "compliance"
    if "certificate" in ep:
        return "certificate"
    if "audit" in ep:
        return "audit-report"
    if "id-checker" in ep or "id-verification" in ep:
        return "id-checker-report"
    if "transcript" in ep:
        return "transcript"
    return "misc-pdf"


def _discover_pdf_export_routes() -> list[dict[str, Any]]:
    roots = [Path("/app/backend/routes"), Path("/app/backend/routers"), Path("/app/backend/server.py")]
    out: list[dict[str, Any]] = []
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file in files:
            text = file.read_text(encoding="utf-8", errors="ignore")
            prefix_match = _PREFIX_PATTERN.search(text)
            prefix = prefix_match.group(1) if prefix_match else ""
            for m in _ROUTE_PATTERN.finditer(text):
                method = m.group(1).upper()
                raw_path = m.group(2)
                p = raw_path if raw_path.startswith("/") else "/" + raw_path
                if prefix:
                    p = prefix.rstrip("/") + p
                endpoint = _normalize_endpoint(p)
                ep_l = endpoint.lower()
                is_pdf_route = (
                    "/export/pdf" in ep_l
                    or "report-pdf" in ep_l
                    or "export-pdf" in ep_l
                    or ep_l.endswith("/pdf")
                    or "/pdf/" in ep_l
                )
                if not is_pdf_route:
                    continue
                out.append({
                    "endpoint": endpoint,
                    "http_method": method,
                    "source_file": str(file),
                    "owner_module": file.stem,
                })
    uniq: dict[tuple[str, str], dict[str, Any]] = {}
    for row in out:
        uniq[(row["http_method"], row["endpoint"])] = row
    return list(uniq.values())


def build_pdf_export_registry() -> list[dict[str, Any]]:
    rows = _discover_pdf_export_routes()
    records: list[dict[str, Any]] = []
    for row in rows:
        endpoint = row["endpoint"]
        doc_type = DOC_TYPE_OVERRIDES.get(endpoint) or _derive_doc_type(endpoint)
        rec = PDFExportRecord(
            doc_type=doc_type,
            endpoint=endpoint,
            http_method=row["http_method"],
            owner_module=row["owner_module"],
            naming_policy=CANONICAL_NAMING_POLICY,
            theme_policy=CANONICAL_THEME_POLICY,
            runtime_enforced=True,
            required_ci_guard="pdf-v15-logo-tile-guard",
            source_file=row["source_file"],
        )
        records.append(asdict(rec))
    records.sort(key=lambda r: (r["doc_type"], r["endpoint"], r["http_method"]))
    return records


def collect_pdf_export_registry_health() -> dict[str, Any]:
    registry = build_pdf_export_registry()
    by_doc: dict[str, int] = {}
    for row in registry:
        by_doc[row["doc_type"]] = by_doc.get(row["doc_type"], 0) + 1

    unclassified = [r for r in registry if r["doc_type"] == "misc-pdf"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not unclassified else "warn",
        "total_exports": len(registry),
        "doc_types": by_doc,
        "unclassified_count": len(unclassified),
        "unclassified_exports": unclassified,
    }
