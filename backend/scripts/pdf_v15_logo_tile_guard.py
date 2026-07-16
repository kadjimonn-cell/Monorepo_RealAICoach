#!/usr/bin/env python3
"""Global PDF v15 guard.

Enforces canonical receipt-style logo-tile usage and blocks filename/theme
regressions across backend PDF generators.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path("/app")
BACKEND_ROOT = ROOT / "backend"
REPORT_DIR = ROOT / "test_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_JSON = REPORT_DIR / "pdf_v15_logo_tile_guard.json"

GENERATOR_INDICATORS = (
    "FPDF(",
    "SimpleDocTemplate(",
    "canvas.Canvas(",
)

SHARED_V15_HELPER_TOKENS = (
    "draw_page_chrome(",
    "draw_kv_card(",
    "draw_callout_card(",
    "get_canonical_logo_tile_path(",
    "enforce_pdf_v15_theme_bytes(",
    "enforce_pdf_v15_enterprise(",
)

HELPER_COMPOSER_CALL_TOKEN = "compose_pdf_v15_helper_layout("
HELPER_COMPOSER_ENFORCEMENT_TOKENS = (
    "_enforce_pdf_v15_enterprise(",
    "enforce_pdf_v15_theme_bytes(",
    "stamp_theme_metadata=True",
)

REQUIRED_HELPER_FILES = {
    str(ROOT / "backend/utils/receipt_generator.py"),
    str(ROOT / "backend/services/platform_health/compliance_pdf.py"),
    str(ROOT / "backend/routes/careers.py"),
}

REQUIRED_HELPER_FILES.update(
    {
        str(ROOT / "backend/server.py"),
        str(ROOT / "backend/routes/mock_interview.py"),
        str(ROOT / "backend/routes/live_activity.py"),
        str(ROOT / "backend/routes/support.py"),
        str(ROOT / "backend/routes/payments.py"),
        str(ROOT / "backend/routes/payments_reporting_routes.py"),
        str(ROOT / "backend/routes/ai_learning_hub.py"),
        str(ROOT / "backend/routes/admin_data_management.py"),
        str(ROOT / "backend/routes/global_miniapps.py"),
        str(ROOT / "backend/routes/content.py"),
        str(ROOT / "backend/routes/admin_payments_tax_intelligence.py"),
        str(ROOT / "backend/routes/id_verification.py"),
        str(ROOT / "backend/routes/autonomous_engine/baseline_deploy.py"),
        str(ROOT / "backend/utils/acceptance_report_generator.py"),
    }
)

LEARNING_CERTIFICATE_THEME_EXEMPTION_MARKER = "LEARNING_CERTIFICATE_PDF_V15_THEME_EXEMPTION"
LEARNING_CERTIFICATE_THEME_EXEMPT_FILE = str(ROOT / "backend/routes/ai_learning_hub.py")

MIGRATION_NOTE_REQUIRED = (
    "PDF generator introduced/changed without shared v15 helper usage. "
    "Add migration note in PR description with: impacted file, helper used, and enforcement evidence."
)


CHECKS = [
    {
        "path": ROOT / "backend/utils/pdf_v15_layout_composer.py",
        "must_contain": [
            "PDF_THEME_VISUAL_MODE_KEY",
            "PDF_THEME_METADATA_STATE_KEY",
            "metadata_missing_helper_composed",
            "metadata-missing",
        ],
        "must_not_contain": [],
    },
    {
        "path": ROOT / "backend/services/pdf_v15_theme.py",
        "must_contain": ["brand-logo-chip.png", "get_canonical_logo_tile_path"],
        "must_not_contain": [],
    },
    {
        "path": ROOT / "backend/services/gtec_scan_v2.py",
        "must_contain": ["get_canonical_logo_tile_path"],
        "must_not_contain": ["/app/backend/static/branding/realaicoach-logo.png"],
    },
    {
        "path": ROOT / "backend/routes/payments_reporting_routes.py",
        "must_contain": ["_get_document_logo_bytes()", "logo_block = RLImage(io.BytesIO(logo_bytes), width=16 * mm, height=16 * mm)"],
        "must_not_contain": ["logo_block = RLImage(io.BytesIO(logo_bytes), width=48 * mm, height=15 * mm)"],
    },
    {
        "path": ROOT / "backend/utils/receipt_generator.py",
        "must_contain": ["_get_document_logo_temp_path()", "get_canonical_logo_tile_path"],
        "must_not_contain": [],
    },
    {
        "path": ROOT / "backend/middleware_pdf_policy.py",
        "must_contain": [
            "enforce_pdf_v15_theme_bytes",
            "PDF_THEME_SIGNATURE",
            "PDF_THEME_VISUAL_MODE_KEY",
            "_build_pdf_v15_visual_overlay",
            "merge_page(",
            "x-pdf-theme-policy",
            "strict_theme_enforcement",
            "blocked_",
            "_emit_blocked_theme_alert",
            "pdf_policy_alert_events",
            "_is_learning_certificate_pdf_theme_exempt_path",
            "LEARNING_CERTIFICATE_THEME_EXEMPT_MODE",
        ],
        "must_not_contain": [
            "This is intentionally non-visual",
        ],
    },
    {
        "path": ROOT / "backend/utils/email_service.py",
        "must_contain": [
            "_apply_pdf_theme_policy_to_attachments",
            "_is_learning_certificate_attachment_exempt",
            "pdf-theme-attachment-enforcement-failed",
            "PDF_THEME_STRICT_MODE",
        ],
        "must_not_contain": [],
    },
    {
        "path": ROOT / "backend/server.py",
        "must_contain": [
            "PdfVersionPolicyMiddleware",
            "app.add_middleware(PdfVersionPolicyMiddleware)",
        ],
        "must_not_contain": [],
    },
]

SCAN_DIRS = [
    ROOT / "backend/routes",
    ROOT / "backend/services",
    ROOT / "backend/utils",
    ROOT / "backend/server.py",
]

BANNED_LITERALS = [
    "pdf-v15-for-attachment-",
]

LEGACY_PDF_LITERAL_PATTERNS = [
    re.compile(r"Content-Disposition[^\n]*filename[^\n]*\.pdf", re.IGNORECASE),
    re.compile(r"filename\s*=\s*f?[\"'][^\"']*\.pdf[\"']", re.IGNORECASE),
    re.compile(r"writestr\(\s*f?[\"'][^\"']*\.pdf[\"']", re.IGNORECASE),
    re.compile(r"FileResponse\([^\n]*filename\s*=\s*f?[\"'][^\"']*\.pdf[\"']", re.IGNORECASE),
]


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


def _is_generator_candidate(text: str) -> bool:
    return any(token in text for token in GENERATOR_INDICATORS)


def _uses_shared_v15_helpers(text: str) -> bool:
    return any(token in text for token in SHARED_V15_HELPER_TOKENS)


def _uses_pdf_v15_filename_helper(text: str) -> bool:
    return any(
        token in text
        for token in (
            "build_pdf_v15_filename(",
            "build_pdf_filename=build_pdf_v15_filename",
            "render_activity_log_pdf(",
        )
    )


def main() -> int:
    failures: list[str] = []
    details: list[dict] = []

    for item in CHECKS:
        path: Path = item["path"]
        if not path.exists():
            failures.append(f"missing file: {path}")
            details.append({"path": str(path), "status": "missing"})
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        missing = [needle for needle in item["must_contain"] if needle not in text]
        forbidden = [needle for needle in item["must_not_contain"] if needle in text]

        if missing:
            failures.extend([f"{path}: missing '{m}'" for m in missing])
        if forbidden:
            failures.extend([f"{path}: forbidden '{m}' present" for m in forbidden])

        details.append(
            {
                "path": str(path),
                "missing": missing,
                "forbidden_present": forbidden,
                "status": "pass" if not missing and not forbidden else "fail",
            }
        )

    for path in _iter_py_files():
        path_s = str(path)
        if "/tests/" in path_s or "/scripts/" in path_s or "__pycache__" in path_s:
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        for banned in BANNED_LITERALS:
            if banned in text:
                failures.append(f"{path}: banned literal present '{banned}'")

        for idx, line in enumerate(lines, start=1):
            if "PDF_FILENAME_GUARD_EXEMPT" in line:
                continue
            for pattern in LEGACY_PDF_LITERAL_PATTERNS:
                if pattern.search(line):
                    failures.append(f"{path}:{idx}: hardcoded .pdf filename literal detected")
                    break

        if "application/pdf" in text and "Content-Disposition" in text and not _uses_pdf_v15_filename_helper(text):
            failures.append(f"{path}: missing build_pdf_v15_filename() usage for PDF disposition")

        if _is_generator_candidate(text):
            uses_shared = _uses_shared_v15_helpers(text)
            path_abs = str(path)
            is_learning_certificate_exempt = path_abs == LEARNING_CERTIFICATE_THEME_EXEMPT_FILE and LEARNING_CERTIFICATE_THEME_EXEMPTION_MARKER in text
            if is_learning_certificate_exempt:
                details.append(
                    {
                        "path": path_abs,
                        "status": "learning_certificate_theme_exempt",
                    }
                )
                continue
            if path_abs in REQUIRED_HELPER_FILES and not uses_shared:
                failures.append(f"{path}: required enterprise PDF generator missing shared v15 helper usage")
            elif not uses_shared:
                failures.append(
                    f"{path}: new PDF generator bypasses shared v15 helpers "
                    f"(must use services/pdf_v15_theme.py helpers or middleware enforcer)"
                )

        if HELPER_COMPOSER_CALL_TOKEN in text and "def compose_pdf_v15_helper_layout(" not in text:
            has_enforcement_path = any(token in text for token in HELPER_COMPOSER_ENFORCEMENT_TOKENS)
            if not has_enforcement_path:
                failures.append(
                    f"{path}: helper-composed PDF path missing downstream v15 enforcement or explicit metadata stamp "
                    f"(metadata-missing helper composition would bypass CI assertion)"
                )

    # Registry governance health (doc_type -> endpoint -> policy mapping)
    try:
        if str(BACKEND_ROOT) not in sys.path:
            sys.path.insert(0, str(BACKEND_ROOT))
        from services.pdf_export_registry import collect_pdf_export_registry_health

        health = collect_pdf_export_registry_health()
        if int(health.get("total_exports") or 0) <= 0:
            failures.append("pdf export registry returned zero exports")
        if int(health.get("unclassified_count") or 0) > 0:
            failures.append(
                f"pdf export registry has unclassified exports: {health.get('unclassified_count')}"
            )
    except Exception as exc:
        failures.append(f"pdf export registry health check failed: {exc}")

    payload = {
        "guard": "pdf_v15_logo_tile_guard",
        "status": "failed" if failures else "passed",
        "failure_count": len(failures),
        "failures": failures,
        "migration_note_required": bool(
            any(
                "PDF generator" in f or "required enterprise PDF generator" in f
                for f in failures
            )
        ),
        "migration_note_template": MIGRATION_NOTE_REQUIRED,
        "details": details,
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if failures:
        print("PDF v15 global guard FAILED:")
        for f in failures:
            print(f" - {f}")
        if payload.get("migration_note_required"):
            print(f" - ACTION: {MIGRATION_NOTE_REQUIRED}")
        print(f"report_json={REPORT_JSON}")
        return 1

    print("PDF v15 global guard PASSED")
    print(f"report_json={REPORT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
