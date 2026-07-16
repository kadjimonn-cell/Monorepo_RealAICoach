"""Compliance report helpers for enterprise runbook flows."""

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from routes.db import db
from utils.email_service import is_email_configured, render_email_header_panel
from utils.pdf_v15_filename import build_pdf_v15_filename
from services.platform_health.compliance_pdf import generate_compliance_pdf


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email or "").strip()))


async def get_admin_distribution_recipients() -> List[str]:
    admins = await db.users.find(
        {
            "$or": [
                {"is_admin": True},
                {"role": "admin"},
                {"roles": "admin"},
                {"roles": {"$in": ["admin"]}},
            ]
        },
        {"_id": 0, "email": 1},
    ).to_list(250)
    return sorted({str(row.get("email", "")).strip().lower() for row in admins if is_valid_email(row.get("email", ""))})


def build_enterprise_compliance_report(run_id: str, enforcement_doc: Dict[str, Any], generated_by: str, trigger_mode: str) -> Dict[str, Any]:
    baseline = enforcement_doc.get("baseline") or {}
    final_scan = enforcement_doc.get("final_scan") or {}
    final_state = enforcement_doc.get("final_state") or {}
    enterprise_audit = enforcement_doc.get("enterprise_audit") or {}
    fedapay = enforcement_doc.get("fedapay") or {}

    return {
        "report_id": f"eir_{run_id}",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "trigger_mode": trigger_mode,
        "runbook": {
            "status": str(enforcement_doc.get("status") or "unknown"),
            "phase": str(enforcement_doc.get("phase") or "unknown"),
            "duration_seconds": float(enforcement_doc.get("duration_seconds") or 0),
        },
        "baseline": {
            "score": int(baseline.get("score") or 0),
            "issues": int(baseline.get("total_issues") or 0),
        },
        "final_state": {
            "score": int(final_state.get("score") or 0),
            "issues": int(final_state.get("issues") or 0),
            "stable": bool(final_state.get("stable")),
        },
        "post_enforcement": {
            "score": int(final_scan.get("score") or 0),
            "issues": int(final_scan.get("total_issues") or 0),
        },
        "enterprise_audit": {
            "score": int((enterprise_audit.get("final_state") or {}).get("score") or (enterprise_audit.get("latest_scan") or {}).get("score") or 0),
            "issues": int((enterprise_audit.get("final_state") or {}).get("issues") or (enterprise_audit.get("latest_scan") or {}).get("total_issues") or 0),
        },
        "reliability": {
            "fedapay_sync_status": str((fedapay.get("sync") or {}).get("status") or "unknown"),
            "fedapay_retry_processed": int((fedapay.get("retry") or {}).get("processed") or 0),
            "fedapay_dead_replayed": int((fedapay.get("dead_replay") or {}).get("replayed") or 0),
            "learning_hub_status": str((enforcement_doc.get("learning_hub_assurance") or {}).get("status") or "unknown"),
        },
    }


def build_enterprise_compliance_csv(report: Dict[str, Any]) -> str:
    rows = [
        ("Report ID", report.get("report_id")),
        ("Run ID", report.get("run_id")),
        ("Generated At", report.get("generated_at")),
        ("Trigger Mode", report.get("trigger_mode")),
        ("Runbook Status", (report.get("runbook") or {}).get("status")),
        ("Runbook Phase", (report.get("runbook") or {}).get("phase")),
        ("Duration Seconds", (report.get("runbook") or {}).get("duration_seconds")),
        ("Baseline Score", (report.get("baseline") or {}).get("score")),
        ("Baseline Issues", (report.get("baseline") or {}).get("issues")),
        ("Final Score", (report.get("final_state") or {}).get("score")),
        ("Final Issues", (report.get("final_state") or {}).get("issues")),
        ("Stable", (report.get("final_state") or {}).get("stable")),
        ("Post Enforcement Score", (report.get("post_enforcement") or {}).get("score")),
        ("Post Enforcement Issues", (report.get("post_enforcement") or {}).get("issues")),
        ("Enterprise Audit Score", (report.get("enterprise_audit") or {}).get("score")),
        ("Enterprise Audit Issues", (report.get("enterprise_audit") or {}).get("issues")),
        ("FedaPay Sync Status", (report.get("reliability") or {}).get("fedapay_sync_status")),
        ("FedaPay Retry Processed", (report.get("reliability") or {}).get("fedapay_retry_processed")),
        ("FedaPay Dead Replayed", (report.get("reliability") or {}).get("fedapay_dead_replayed")),
        ("Learning Hub Assurance", (report.get("reliability") or {}).get("learning_hub_status")),
    ]

    def _escape(value: Any) -> str:
        return '"' + str(value if value is not None else '').replace('"', '""') + '"'

    escaped = [f"{_escape(k)},{_escape(v)}" for k, v in rows]
    return "Metric,Value\n" + "\n".join(escaped)


async def dispatch_enterprise_compliance_report_email(report: Dict[str, Any], requested_by: str, trigger_mode: str) -> Dict[str, Any]:
    recipients = await get_admin_distribution_recipients()
    if not recipients:
        return {"status": "skipped", "reason": "no_admin_recipients", "sent_count": 0, "failed": []}
    if not is_email_configured():
        return {
            "status": "skipped",
            "reason": "email_not_configured",
            "sent_count": 0,
            "failed": [],
            "recipients_count": len(recipients),
        }

    report_json = json.dumps(report, indent=2)
    report_csv = build_enterprise_compliance_csv(report)
    report_pdf = generate_compliance_pdf(report)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_identity = report.get("run_id") or report.get("report_id") or stamp
    attachments = [
        {
            "filename": f"enterprise_integrity_compliance_{stamp}.json",
            "content": base64.b64encode(report_json.encode("utf-8")).decode("utf-8"),
            "content_type": "application/json",
        },
        {
            "filename": f"enterprise_integrity_compliance_{stamp}.csv",
            "content": base64.b64encode(report_csv.encode("utf-8")).decode("utf-8"),
            "content_type": "text/csv",
        },
        {
            "filename": build_pdf_v15_filename("compliance", report_identity),
            "content": base64.b64encode(report_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
    ]

    header_html = render_email_header_panel(
        title="Enterprise Integrity Compliance Report",
        subtitle="Automated enterprise runbook execution summary and compliance artifacts.",
        variant="report",
        accent="#1D4ED8",
        meta_label="Run ID",
        meta_value=str(report.get("run_id") or "N/A"),
    )
    final_state = report.get("final_state") or {}
    reliability = report.get("reliability") or {}
    f"""
    <div style=\"font-family:Arial,sans-serif;max-width:660px;margin:0 auto;padding:20px;background:#F8FAFC;\">
      <div style=\"border-radius:20px;overflow:hidden;margin-bottom:18px;\">{header_html}</div>
      <div class=\"em-force-light-card\" style=\"background:#ffffff;border:1px solid #E2E8F0;border-radius:14px;padding:16px;\">
        <p class=\"em-force-muted-text\" style=\"margin:0 0 10px;color:#334155;font-size:13px;\">Distribution mode: <strong class=\"em-force-dark-text\">{trigger_mode.upper()}</strong> · Requested by: <strong class=\"em-force-dark-text\">{requested_by}</strong></p>
        <table class=\"em-force-light-card\" style=\"width:100%;border-collapse:collapse;background:#FFFFFF;\">
          <tr><td class=\"em-force-muted-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;\">Final Score</td><td class=\"em-force-dark-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;\">{final_state.get('score', 0)}</td></tr>
          <tr><td class=\"em-force-muted-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;\">Final Issues</td><td class=\"em-force-dark-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;\">{final_state.get('issues', 0)}</td></tr>
          <tr><td class=\"em-force-muted-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;\">Stable</td><td class=\"em-force-dark-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;\">{str(final_state.get('stable', False)).upper()}</td></tr>
          <tr><td class=\"em-force-muted-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;\">FedaPay Sync</td><td class=\"em-force-dark-text\" style=\"padding:8px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;\">{reliability.get('fedapay_sync_status', 'unknown')}</td></tr>
          <tr><td class=\"em-force-muted-text\" style=\"padding:8px;color:#64748B;\">Learning Hub Assurance</td><td class=\"em-force-dark-text\" style=\"padding:8px;font-weight:700;color:#0F172A;\">{reliability.get('learning_hub_status', 'unknown')}</td></tr>
        </table>
        <p class=\"em-force-muted-text\" style=\"margin:12px 0 0;color:#64748B;font-size:12px;\">Attached: JSON + CSV compliance files for audit distribution.</p>
      </div>
    </div>
    """

    sent_count = 0
    failed: List[Dict[str, str]] = []
    final_state = report.get("final_state") or {}
    overall_score = int(final_state.get("score") or (report.get("post_enforcement") or {}).get("score") or 0)
    final_issues = int(final_state.get("issues") or (report.get("post_enforcement") or {}).get("issues") or 0)
    if overall_score >= 95:
        grade = "A"
    elif overall_score >= 85:
        grade = "B"
    elif overall_score >= 70:
        grade = "C"
    else:
        grade = "D"
    generated_at = str(report.get("generated_at") or datetime.now(timezone.utc).isoformat())
    report_date = generated_at.replace("T", " ")[:16]
    for recipient in recipients:
        from utils.email_service import send_catalog_template
        result = await send_catalog_template(
            recipient_email=recipient,
            template_key="compliance_report",
            report_date=report_date,
            overall_score=overall_score,
            grade=grade,
            checks_passed=max(0, overall_score - final_issues),
            checks_total=100,
            attachments=attachments,
        )
        if result.get("success"):
            sent_count += 1
        else:
            failed.append({"email": recipient, "error": str(result.get("error") or "send_failed")[:180]})

    dispatch = {
        "status": "sent" if sent_count > 0 else "failed",
        "trigger_mode": trigger_mode,
        "requested_by": requested_by,
        "sent_count": sent_count,
        "recipients_count": len(recipients),
        "failed": failed,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.enterprise_integrity_email_delivery_logs.insert_one(
        {
            "report_id": report.get("report_id"),
            "run_id": report.get("run_id"),
            **dispatch,
        }
    )
    return dispatch
