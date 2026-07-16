from __future__ import annotations

import sys

sys.path.append("/app/backend")

from services.gtec_scan_v2 import (
    _validate_notification_snapshot,
    build_snapshot_from_report_email_dispatch,
)


def test_build_snapshot_from_email_dispatch_runtime_summary():
    report = {
        "task_id": "gtec_c5_hist_001",
        "execution_hash": "hash001",
        "generated_at": "2026-05-15T00:00:00+00:00",
        "status": "FAIL",
        "security_scan": "FAIL",
        "email_dispatch": {
            "sent_at": "2026-05-15T01:00:00+00:00",
            "c5_runtime_summary": {
                "trust": {"score_percent": 100.0, "passed_gates": 9, "total_gates": 9},
                "white_screen_sentry": {
                    "status": "FAIL",
                    "run_id": "wss_001",
                    "failed_checks": 60,
                    "total_checks": 60,
                },
                "external_host_certification": {
                    "status": "fail",
                    "certification_id": "ext_001",
                    "retry_needed": False,
                },
                "incident_auto_closure": {
                    "evaluated_incidents": 9,
                    "transitioned_to_pending_verification": 0,
                    "auto_closed": 0,
                    "reopened": 2,
                },
            },
        },
    }

    snapshot = build_snapshot_from_report_email_dispatch(report)
    assert snapshot.get("source_task_id") == "gtec_c5_hist_001"
    assert snapshot.get("data_freshness") == "REPORT_MIRRORED"
    assert (snapshot.get("trust") or {}).get("passed_gates") == 9
    assert (snapshot.get("white_screen_sentry") or {}).get("failed_checks") == 60
    assert (snapshot.get("external_host_certification") or {}).get("status") == "fail"


def test_snapshot_validator_flags_ratio_contradiction():
    report = {
        "task_id": "gtec_c5_bad_001",
        "status": "FAIL",
        "security_scan": "FAIL",
    }
    snapshot = {
        "source_task_id": "gtec_c5_bad_001",
        "trust": {"passed_gates": 12, "total_gates": 9},
        "white_screen_sentry": {"status": "PASS", "failed_checks": 5, "total_checks": 3},
        "responsive_viewport_matrix": {"artifact_count": 0},
        "incident_auto_closure": {
            "evaluated_incidents": 1,
            "transitioned_to_pending_verification": 0,
            "auto_closed": 2,
            "reopened": 0,
        },
    }
    result = _validate_notification_snapshot(snapshot, report)
    assert result.get("passed") is False
    issues = result.get("issues") or []
    assert "trust_gates_invalid_ratio" in issues
    assert "white_screen_invalid_ratio" in issues
    assert "incident_counts_exceed_evaluated" in issues
