# ruff: noqa
"""
scheduler_jobs.theme_guardrails — Theme drift / guardrail scheduled jobs.

**Phase 2 incremental domain split — batch #13.**

Owns the recurring theme-system hygiene jobs: rapid in-process
guardrail scan, nightly visual drift detector, admin-tabs theme drift
report, and the admin-tabs theme drift weekly digest.

Jobs in this module
===================
- ``scheduled_theme_guardrail_scan`` (5-min in-process scan)
- ``scheduled_theme_drift_nightly_detector`` (nightly visual diff)
- ``scheduled_admin_tabs_theme_drift_report`` (admin-tabs theme drift)
- ``scheduled_admin_tabs_theme_drift_weekly_digest`` (weekly digest fan-out)

All function bodies are byte-identical to the originals in `_legacy.py`
— this is a pure relocation, not a rewrite.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.theme_guardrails")


async def scheduled_theme_guardrail_scan():
    """Periodic global light/dark theme guardrail scan."""
    job_id = "theme_guardrail_scan"
    try:
        from routes.autonomous_engine import _run_theme_guardrail_scan

        result = await _run_theme_guardrail_scan(triggered_by="scheduler")
        status = str(result.get("status") or "UNKNOWN")
        score = result.get("theme_guardrail_score")
        issues = result.get("issues_total")
        heartbeat_status = "healthy" if status == "PASS" else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"status={status} score={score} issues={issues}",
        )
    except Exception as exc:
        logger.error(f"scheduled_theme_guardrail_scan failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_theme_drift_nightly_detector():
    """Nightly theme drift detector: scans and opens/updates theme drift tickets."""
    job_id = "theme_drift_nightly_detector"
    try:
        from routes.autonomous_engine import _run_theme_drift_nightly_detector

        result = await _run_theme_drift_nightly_detector(triggered_by="scheduler-nightly")
        summary = result.get("ticket_summary") or {}
        created = int(summary.get("created") or 0)
        updated = int(summary.get("updated") or 0)
        open_tickets = int(summary.get("open_tickets") or 0)
        candidates = int(summary.get("candidates") or 0)
        source_scan = result.get("source_scan") or {}
        scan_status = str(source_scan.get("status") or "UNKNOWN")
        score = source_scan.get("theme_guardrail_score")

        heartbeat_status = "warning" if created > 0 else "healthy"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            (
                f"scan={scan_status} score={score} candidates={candidates} "
                f"created={created} updated={updated} open={open_tickets}"
            ),
        )
    except Exception as exc:
        logger.error(f"scheduled_theme_drift_nightly_detector failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_admin_tabs_theme_drift_report():
    """Generate a daily admin/tabs theme drift report (hex hardcoded regression telemetry)."""
    job_id = "admin_tabs_theme_drift_report"
    try:
        from routes.db import db

        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%d")
        report_path = Path(f"/app/memory/theme_drift_reports/admin_tabs_theme_drift_{stamp}.json")
        script_path = Path("/app/frontend/scripts/theme_hex_guard.py")

        cmd = [
            "python",
            str(script_path),
            "--scope",
            "admin-tabs",
            "--mode",
            "scan",
            "--report-file",
            str(report_path),
            "--max-offenders",
            "60",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "theme drift scan failed")[-500:]
            raise RuntimeError(err)

        output = (proc.stdout or "").strip().splitlines()
        if not output:
            raise RuntimeError("theme drift scan returned empty output")

        payload = json.loads(output[-1])
        report_doc = {
            "report_id": f"admin_tabs_theme_drift_{stamp}_{uuid.uuid4().hex[:8]}",
            "scope": payload.get("scope", "admin-tabs"),
            "mode": payload.get("mode", "scan"),
            "files_scanned": int(payload.get("files_scanned", 0) or 0),
            "files_with_hex": int(payload.get("files_with_hex", 0) or 0),
            "total_hex_tokens": int(payload.get("total_hex_tokens", 0) or 0),
            "offenders": payload.get("offenders", []),
            "generated_at": now.isoformat(),
            "report_path": str(report_path),
            "source": "scheduler_daily",
        }
        await db.theme_compliance_drift_reports.insert_one(report_doc)

        status = "healthy" if report_doc["total_hex_tokens"] == 0 else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            status,
            (
                f"files={report_doc['files_scanned']} offenders={report_doc['files_with_hex']} "
                f"hex={report_doc['total_hex_tokens']} report={report_path.name}"
            ),
        )
        logger.info(
            "admin-tabs theme drift report generated: files=%s offenders=%s hex=%s path=%s",
            report_doc["files_scanned"],
            report_doc["files_with_hex"],
            report_doc["total_hex_tokens"],
            report_path,
        )
    except Exception as exc:
        logger.error(f"scheduled_admin_tabs_theme_drift_report failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_admin_tabs_theme_drift_weekly_digest():
    """Send weekly email digest of admin/tabs theme drift reports to admin owners."""
    job_id = "admin_tabs_theme_drift_weekly_digest"
    try:
        from routes.db import db
        from utils.email_service import send_catalog_template

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=7)).isoformat()

        rows = await db.theme_compliance_drift_reports.find(
            {
                "scope": "admin-tabs",
                "generated_at": {"$gte": since},
            },
            {"_id": 0},
        ).sort("generated_at", -1).limit(20).to_list(20)

        if not rows:
            await _record_scheduler_heartbeat(job_id, "skipped", "no admin-tabs drift reports in last 7 days")
            return

        total_scans = len(rows)
        total_hex = sum(int(r.get("total_hex_tokens", 0) or 0) for r in rows)
        max_hex = max(int(r.get("total_hex_tokens", 0) or 0) for r in rows)
        avg_hex = round(total_hex / max(total_scans, 1), 2)

        latest = rows[0]
        latest_hex = int(latest.get("total_hex_tokens", 0) or 0)
        latest_files = int(latest.get("files_scanned", 0) or 0)
        latest_generated = str(latest.get("generated_at") or "")

        top_offenders = (latest.get("offenders") or [])[:10]
        top_offender_lines = [
            f"- {o.get('file')}: {int(o.get('count', 0) or 0)}"
            for o in top_offenders
        ]
        description = (
            f"Theme drift weekly summary (admin/tabs)\n"
            f"Reports: {total_scans}\n"
            f"Total hex (7d): {total_hex}\n"
            f"Average/report: {avg_hex}\n"
            f"Worst single report: {max_hex}\n"
            f"Latest report hex: {latest_hex}\n"
            f"Latest files scanned: {latest_files}\n"
            f"Latest generated_at: {latest_generated}\n"
            f"Top offenders:\n" + ("\n".join(top_offender_lines) if top_offender_lines else "- none")
        )

        admin_emails = [e.strip().lower() for e in (os.environ.get("ADMIN_EMAILS") or "").split(",") if e.strip()]
        if not admin_emails:
            admin_emails = ["admin@realaicoach.app"]

        sent = 0
        for email in sorted(set(admin_emails)):
            try:
                result = await send_catalog_template(
                    recipient_email=email,
                    template_key="system_alert_admin",
                    alert_type="Theme Drift Weekly Digest",
                    severity="LOW" if total_hex == 0 else "HIGH",
                    description=description,
                    component="Frontend Theme Guard",
                    timestamp=now.strftime("%Y-%m-%d %H:%M UTC"),
                )
                if (result or {}).get("status") == "sent":
                    sent += 1
            except Exception:
                continue

        heartbeat_status = "healthy" if sent > 0 else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"reports={total_scans} total_hex={total_hex} sent={sent}",
        )
    except Exception as exc:
        logger.error(f"scheduled_admin_tabs_theme_drift_weekly_digest failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_theme_guardrail_scan",
    "scheduled_theme_drift_nightly_detector",
    "scheduled_admin_tabs_theme_drift_report",
    "scheduled_admin_tabs_theme_drift_weekly_digest",
]
