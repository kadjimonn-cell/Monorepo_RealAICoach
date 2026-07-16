from __future__ import annotations

import io
import sys

sys.path.append("/app/backend")

from pypdf import PdfReader

from services.gtec_scan_v2 import build_canonical_gtec_pdf_export
from utils.email_templates import build_gtec_scan_v2_report_email


def _sample_report() -> dict:
    return {
        "task_id": "gtec_c5_test_pdf_email_summary",
        "generated_at": "2026-05-15T00:00:00+00:00",
        "execution_hash": "hash_test_123",
        "status": "PASS",
        "critical_vulns": 0,
        "high_vulns": 0,
        "medium_vulns": 1,
        "low_vulns": 2,
        "regressions": "NO",
        "security_scan": "PASS",
        "e2e_tests": "PASS",
        "responsiveness": "PASS",
        "performance": "PASS",
        "rbac_status": "PASS",
        "subscription_enforcement": "PASS",
        "learning_memory_updated": "YES",
        "directive_version": "C5.2026.05",
        "summary": "C5 summary smoke test",
        "severity_counts": {"medium": 1, "low": 2},
        "v3_output": {
            "SYSTEM_STATUS": "PASS",
            "SECURITY_STATUS": "PASS",
            "PERFORMANCE_STATUS": "PASS",
            "I18N_STATUS": "PASS",
            "RBAC_STATUS": "PASS",
            "REGRESSION_STATUS": "PASS",
            "ERROR_COUNT": 3,
            "ACTIVE_FIXES": "NO",
            "MONITORING": "ACTIVE",
            "LEARNING_MEMORY": "UPDATED",
            "CONFIDENCE_LEVEL": "HIGH",
        },
        "c5_notification_snapshot": {
            "trust": {"score_percent": 100.0, "passed_gates": 9, "total_gates": 9},
            "white_screen_sentry": {
                "status": "PASS",
                "run_id": "wss_test_001",
                "failed_checks": 0,
                "total_checks": 60,
                "routes_tested": 20,
                "route_source": "dynamic_inventory",
            },
            "responsive_viewport_matrix": {
                "artifact_count": 60,
                "viewports": ["mobile", "tablet", "desktop"],
                "matrix_summary": {
                    "mobile": {"pass": 20, "fail": 0, "total": 20},
                    "tablet": {"pass": 20, "fail": 0, "total": 20},
                    "desktop": {"pass": 20, "fail": 0, "total": 20},
                },
            },
            "external_host_certification": {
                "status": "pass",
                "certification_id": "ext_cert_test_001",
                "reason": "",
                "retry_plan": {"needs_retry": False, "reasons": []},
            },
            "incident_auto_closure": {
                "evaluated_incidents": 5,
                "transitioned_to_pending_verification": 1,
                "auto_closed": 2,
                "reopened": 0,
                "streak_resets": 1,
                "policy": {"clean_rescans_required": 3, "pending_verification_hours": 24},
            },
        },
    }


def test_pdf_export_contains_c5_runtime_summary_block():
    report = _sample_report()
    exported = build_canonical_gtec_pdf_export(report)
    assert exported is not None
    assert exported.get("pdf_bytes")

    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)

    assert "C5 RUNTIME SUMMARY" in text
    assert "WHITE SCREEN SENTRY STATUS" in text
    assert "EXTERNAL CERT STATUS" in text
    assert "INCIDENTS AUTO CLOSED" in text


def test_email_template_contains_c5_runtime_summary_fields():
    email = build_gtec_scan_v2_report_email(
        task_id="task_gtec_c5_001",
        status="PASS",
        critical_vulns=0,
        high_vulns=0,
        medium_vulns=1,
        low_vulns=2,
        summary="C5 email summary test",
        c5_trust_score_percent=100.0,
        c5_trust_passed_gates=9,
        c5_trust_total_gates=9,
        c5_white_screen_status="PASS",
        c5_white_screen_run_id="wss_test_001",
        c5_white_screen_failed_checks=0,
        c5_white_screen_total_checks=60,
        c5_white_screen_routes_tested=20,
        c5_white_screen_route_source="dynamic_inventory",
        c5_viewport_artifact_count=60,
        c5_viewports="mobile,tablet,desktop",
        c5_external_cert_status="pass",
        c5_external_cert_id="ext_cert_test_001",
        c5_external_cert_retry_needed="NO",
        c5_incidents_evaluated=5,
        c5_incidents_transitioned_pending=1,
        c5_incidents_auto_closed=2,
        c5_incidents_reopened=0,
        c5_incidents_streak_resets=1,
        c5_incident_policy_clean_rescans=3,
        c5_incident_policy_pending_hours=24,
        c5_snapshot_version="c5-notification-snapshot.v2",
        c5_snapshot_status="COMPLETE",
        c5_data_freshness="LIVE",
        c5_consistency_passed="YES",
        c5_consistency_issues="",
        c5_fail_reason_summary="PASS — no failing pillars detected",
    )

    assert "C5 RUNTIME SUMMARY — ENFORCEMENT + CERTIFICATION" in (email.html or "")
    assert "TRUST_GATES" in (email.html or "")
    assert "SNAPSHOT_STATUS" in (email.html or "")
    assert "CONSISTENCY" in (email.html or "")
    assert "WHITE_SCREEN_SENTRY_STATUS" in (email.text or "")
    assert "SNAPSHOT_STATUS: COMPLETE" in (email.text or "")
    assert "CONSISTENCY_PASSED: YES" in (email.text or "")
    assert "EXTERNAL_HOST_CERT_STATUS" in (email.text or "")
    assert "INCIDENT_POLICY" in (email.text or "")
