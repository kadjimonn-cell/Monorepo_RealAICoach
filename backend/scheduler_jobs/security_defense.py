"""
scheduler_jobs.security_defense — Defense & autonomous-blocking scheduled jobs.

**Phase 2 incremental domain split — batch #20.**

Owns the nightly defense pipeline that exports blocked autonomous-engine
completion attempts, runs Active Defense nightly scans, and retries
failed SIEM webhook deliveries.

Jobs in this module
===================
- ``scheduled_autonomous_blocked_attempts_export`` — nightly export of
  blocked Autonomous Engine completion attempts (CSV + JSON + latest
  certificate) to all admin inboxes.
- ``scheduled_active_defense_nightly_scan`` — nightly Active Defense
  scan with auto-blocking and email reports.
- ``scheduled_siem_webhook_dead_letter_retry`` — retry pending SIEM
  webhook dead-letter records with capped attempts.
"""

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat
from utils.pagination import iter_find_paginated


logger = logging.getLogger("scheduler_jobs.security_defense")


async def scheduled_autonomous_blocked_attempts_export():
    """Nightly auto-export of blocked Autonomous Engine completion attempts to admin inbox."""
    job_id = "autonomous_blocked_attempts_nightly_export"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=1)

    try:
        from routes.db import db

        entries = []
        async for entry in iter_find_paginated(
            db.autonomous_engine_completion_audit,
            {
                "blocked": True,
                "timestamp": {"$gte": window_start, "$lte": now},
            },
            {"_id": 0, "timestamp": 0},
            sort=[("attempted_at", -1)],
            max_docs=5000,
        ):
            entries.append(entry)

        summary = {
            "exported_at": now.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "blocked_attempt_count": len(entries),
        }

        headers = [
            "audit_id",
            "attempted_at",
            "workflow_type",
            "workflow_id",
            "close_reason",
            "actor_email",
            "source_endpoint",
            "latest_run_status",
            "latest_run_id",
            "minutes_since_last_pass",
        ]

        def _escape_csv(value: object) -> str:
            return '"' + str(value or "").replace('"', '""') + '"'

        rows = [
            [
                item.get("audit_id"),
                item.get("attempted_at"),
                item.get("workflow_type"),
                item.get("workflow_id"),
                item.get("close_reason"),
                ((item.get("actor") or {}).get("email") or ""),
                item.get("source_endpoint"),
                ((item.get("gate_lock") or {}).get("latest_run_status") or ""),
                ((item.get("gate_lock") or {}).get("latest_run_id") or ""),
                ((item.get("gate_lock") or {}).get("minutes_since_last_pass") or ""),
            ]
            for item in entries
        ]
        csv_content = "\n".join([
            ",".join([_escape_csv(h) for h in headers]),
            *[",".join([_escape_csv(cell) for cell in row]) for row in rows],
        ])
        json_content = {
            "summary": summary,
            "entries": entries,
        }

        csv_filename = f"autonomous_blocked_attempts_{now.strftime('%Y-%m-%d')}.csv"
        json_filename = f"autonomous_blocked_attempts_{now.strftime('%Y-%m-%d')}.json"
        attachments = [
            {
                "filename": csv_filename,
                "content": list(csv_content.encode("utf-8")),
                "content_type": "text/csv",
                "disposition": "attachment",
            },
            {
                "filename": json_filename,
                "content": list(json.dumps(json_content, indent=2).encode("utf-8")),
                "content_type": "application/json",
                "disposition": "attachment",
            },
        ]

        latest_certificate = await db.autonomous_engine_certificates.find_one(
            {},
            {"_id": 0},
            sort=[("issued_at", -1)],
        )
        certificate_attached = False
        if latest_certificate and latest_certificate.get("pdf_base64"):
            try:
                certificate_bytes = base64.b64decode(str(latest_certificate.get("pdf_base64") or ""))
                attachments.append(
                    {
                        "filename": f"latest_release_readiness_certificate_{latest_certificate.get('certificate_id')}.pdf",
                        "content": list(certificate_bytes),
                        "content_type": "application/pdf",
                        "disposition": "attachment",
                    }
                )
                certificate_attached = True
            except Exception:
                pass

        recipients = await db.users.find(
            {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ).to_list(100)
        recipient_emails = sorted({str(r.get("email", "")).strip() for r in recipients if str(r.get("email", "")).strip()})
        if not recipient_emails:
            _fb = os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip()
            recipient_emails = [_fb] if _fb else []

        sent = 0
        for email in recipient_emails:
            try:
                from utils.email_service import send_catalog_template
                tpl_result = await send_catalog_template(
                    recipient_email=email,
                    template_key="nightly_blocked_export_v7",
                    blocked_count=len(entries),
                    window_start=window_start.isoformat(),
                    window_end=now.isoformat(),
                )
                if attachments:
                    from utils.email_templates import TEMPLATE_CATALOG
                    tpl = TEMPLATE_CATALOG["nightly_blocked_export_v7"]["builder"](
                        blocked_count=len(entries),
                        window_start=window_start.isoformat(),
                        window_end=now.isoformat(),
                    )
                    from utils.email_service import send_email
                    result = await send_email(
                        recipient_email=email,
                        subject=tpl.subject,
                        content=tpl.html,
                        template_key="nightly_blocked_export_v7",
                        attachments=attachments,
                    )
                else:
                    result = tpl_result
                if result.get("success"):
                    sent += 1
            except Exception:
                continue

        await db.autonomous_engine_nightly_exports.insert_one(
            {
                "job_id": job_id,
                "run_at": now.isoformat(),
                "window_start": window_start.isoformat(),
                "window_end": now.isoformat(),
                "blocked_attempt_count": len(entries),
                "sent_count": sent,
                "recipients_count": len(recipient_emails),
                "certificate_attached": certificate_attached,
                "certificate_id": (latest_certificate or {}).get("certificate_id") if certificate_attached else None,
            }
        )
        await _record_scheduler_heartbeat(job_id, "healthy", f"blocked={len(entries)} sent={sent}")
    except Exception as exc:
        logger.error(f"Nightly autonomous blocked attempt export failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_active_defense_nightly_scan():
    """Nightly Active Defense scan with auto-blocking and email reports."""
    job_id = "active_defense_nightly_scan"
    try:
        from routes.autonomous_engine import run_active_defense_nightly_scan, _get_engine_config

        config = await _get_engine_config()
        policy = config.get("active_defense_nightly_policy", {})
        if not bool(policy.get("enabled", True)):
            await _record_scheduler_heartbeat(job_id, "skipped", "nightly active defense disabled")
            return

        result = await run_active_defense_nightly_scan(triggered_by="scheduler", force=False)
        status = str(result.get("status") or "unknown")
        zt_status = str(result.get("zero_trust_status") or "UNKNOWN")
        threat = str(result.get("threat_level") or "UNKNOWN")
        pass_count = int(result.get("pass_count") or 0)
        blocked = len(result.get("auto_blocked_ips") or [])
        email_sent = int((result.get("email") or {}).get("sent") or 0)

        if status in {"skipped_already_run", "skipped_disabled"}:
            heartbeat_status = "skipped"
        elif zt_status == "PASS":
            heartbeat_status = "healthy"
        else:
            heartbeat_status = "warning"

        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"status={status} zt={zt_status} threat={threat} checks={pass_count}/8 blocked={blocked} emails={email_sent}",
        )
        logger.info(
            "Active Defense nightly: status=%s zt=%s threat=%s checks=%s/8 blocked=%s emails=%s",
            status, zt_status, threat, pass_count, blocked, email_sent,
        )
    except Exception as exc:
        logger.error(f"scheduled_active_defense_nightly_scan failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_siem_webhook_dead_letter_retry() -> Dict[str, Any]:
    """Retry pending SIEM webhook dead-letter records with capped attempts."""
    job_id = "siem_webhook_dead_letter_retry"
    try:
        from routes.db import db

        max_retry_attempts = max(1, int(str(os.environ.get("SIEM_WEBHOOK_DEAD_LETTER_MAX_ATTEMPTS") or "5")))
        now = datetime.now(timezone.utc).isoformat()
        rows = await db.siem_incident_webhook_dead_letter.find(
            {
                "status": "pending_retry",
                "$or": [
                    {"retry_attempts": {"$exists": False}},
                    {"retry_attempts": {"$lt": max_retry_attempts}},
                ],
            },
            {"_id": 0},
        ).sort("created_at", 1).limit(25).to_list(25)

        processed = 0
        succeeded = 0
        failed = 0

        for row in rows:
            processed += 1
            dead_letter_id = str(row.get("dead_letter_id") or "")
            context = str(row.get("context") or "dead_letter_retry")
            related_run_id = row.get("related_run_id")
            actor_user_id = str(row.get("actor_user_id") or "scheduler")

            try:
                from routes.security_key_rotation import _validate_siem_incident_webhook_delivery

                retry_result = await _validate_siem_incident_webhook_delivery(
                    actor_user_id=actor_user_id,
                    context=f"dead_letter_retry:{context}",
                    related_run_id=related_run_id,
                )
            except Exception as exc:
                retry_result = {"validated": False, "status": "error", "error": str(exc)[:220]}

            retry_attempts = int(row.get("retry_attempts") or 0) + 1
            if bool(retry_result.get("validated")):
                succeeded += 1
                await db.siem_incident_webhook_dead_letter.update_one(
                    {"dead_letter_id": dead_letter_id},
                    {
                        "$set": {
                            "status": "resolved",
                            "resolved_at": now,
                            "retry_attempts": retry_attempts,
                            "last_retry_result": retry_result,
                        }
                    },
                )
            else:
                failed += 1
                next_status = "pending_retry" if retry_attempts < max_retry_attempts else "failed_permanent"
                await db.siem_incident_webhook_dead_letter.update_one(
                    {"dead_letter_id": dead_letter_id},
                    {
                        "$set": {
                            "status": next_status,
                            "retry_attempts": retry_attempts,
                            "last_retry_result": retry_result,
                            "last_retry_at": now,
                        }
                    },
                )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            f"processed={processed} succeeded={succeeded} failed={failed}",
        )
        return {
            "status": "ok",
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "max_retry_attempts": max_retry_attempts,
        }
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


__all__ = [
    "scheduled_autonomous_blocked_attempts_export",
    "scheduled_active_defense_nightly_scan",
    "scheduled_siem_webhook_dead_letter_retry",
]
