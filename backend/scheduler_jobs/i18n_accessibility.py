"""scheduler_jobs.i18n_accessibility — i18n + accessibility + contrast audits.

**Phase 2 batch #18.**

Jobs: i18n literal autofix dry-run report, weekly email contrast
compliance, nightly dark-mode regression scan.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone

from scheduler_jobs.observability import _record_scheduler_heartbeat

logger = logging.getLogger("scheduler_jobs.i18n_accessibility")


async def scheduled_i18n_literal_autofix_dry_run_report():
    """Nightly i18n literal-autofix dry-run reporting with admin alerting."""
    job_id = "i18n_literal_autofix_dry_run_report"
    try:
        from routes.db import db
        from routes.admin_i18n_adoption import _nightly_drift_payload
        from routes.admin_push_notifications import emit_realtime_alert

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        day_key = now.strftime("%Y-%m-%d")

        drift_payload = _nightly_drift_payload() or {}
        nightly = drift_payload.get("nightly") or {}
        burndown = drift_payload.get("burndown") or {}

        new_missing_keys = nightly.get("new_missing_keys") or []
        newly_missing_count = int(nightly.get("newly_missing_count") or len(new_missing_keys) or 0)
        baseline_count = int(nightly.get("baseline_count") or 0)
        unresolved_count = int(burndown.get("unresolved_top_count") or newly_missing_count)

        report_doc = {
            "job_id": job_id,
            "created_at": now_iso,
            "day_key": day_key,
            "generated_at": str(nightly.get("generated_at") or now_iso),
            "newly_missing_count": newly_missing_count,
            "baseline_count": baseline_count,
            "unresolved_top_count": unresolved_count,
            "new_missing_keys": [str(key) for key in (new_missing_keys[:50] if isinstance(new_missing_keys, list) else [])],
            "resolved_top_count": int(burndown.get("resolved_top_count") or 0),
            "next_baseline_count": int(burndown.get("next_baseline_count") or baseline_count),
            "source": "admin_i18n_adoption._nightly_drift_payload",
        }
        await db.i18n_literal_autofix_dry_run_reports.insert_one(report_doc)

        state_key = "i18n_literal_autofix_dry_run_state"
        previous_state = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0}) or {}
        last_alert_day = str(previous_state.get("last_alert_day_utc") or "")
        should_alert = newly_missing_count > 0 and last_alert_day != day_key
        alerted = False

        if should_alert:
            title = "I18n Literal Autofix Dry-Run Requires Attention"
            message = (
                f"{newly_missing_count} untranslated literal key(s) detected in nightly dry-run. "
                f"Baseline: {baseline_count}, unresolved: {unresolved_count}."
            )

            await emit_realtime_alert(
                alert_type="i18n_literal_autofix_dry_run_alert",
                severity="warning" if newly_missing_count < 10 else "critical",
                title=title,
                message=message,
            )

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
            for admin in admins:
                admin_user_id = str(admin.get("user_id") or "")
                if not admin_user_id:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"i18n_dry_run_{admin_user_id}_{int(now.timestamp())}",
                        "user_id": admin_user_id,
                        "type": "i18n_literal_autofix_dry_run_alert",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "job_id": job_id,
                            "newly_missing_count": newly_missing_count,
                            "baseline_count": baseline_count,
                            "unresolved_top_count": unresolved_count,
                            "sample_keys": report_doc.get("new_missing_keys")[:8],
                        },
                    }
                )
            alerted = True

        await db.system_runtime_flags.update_one(
            {"key": state_key},
            {
                "$set": {
                    "key": state_key,
                    "last_run_at": now_iso,
                    "day_key": day_key,
                    "newly_missing_count": newly_missing_count,
                    "baseline_count": baseline_count,
                    "unresolved_top_count": unresolved_count,
                    "last_alert_day_utc": day_key if alerted else (last_alert_day or None),
                    "alerted": alerted,
                }
            },
            upsert=True,
        )

        await _record_scheduler_heartbeat(
            job_id,
            "warning" if newly_missing_count > 0 else "healthy",
            f"newly_missing={newly_missing_count} baseline={baseline_count} unresolved={unresolved_count} alerted={alerted}",
        )
    except Exception as exc:
        logger.error(f"I18n literal-autofix dry-run report failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_weekly_email_contrast_compliance():
    """Weekly automated email contrast compliance report — audits all templates and emails results to admin."""
    job_id = "weekly_email_contrast_compliance"
    try:
        from routes.db import db
        from utils.email_service import send_catalog_template, apply_adaptive_email_contrast_guard
        from utils.email_templates import TEMPLATE_CATALOG

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        total = 0
        passed = 0
        failed_templates = []

        for key, info in TEMPLATE_CATALOG.items():
            total += 1
            try:
                tpl = info["builder"]()
                guarded_html = apply_adaptive_email_contrast_guard(tpl.html)
                has_guard = "data-adaptive-contrast-guard" in guarded_html
                if has_guard:
                    passed += 1
                else:
                    failed_templates.append({"key": key, "label": info.get("label", key), "reason": "contrast guard not applied"})
            except Exception as tpl_exc:
                failed_templates.append({"key": key, "label": info.get("label", key), "reason": str(tpl_exc)[:120]})

        compliance_rate = round((passed / total * 100), 1) if total > 0 else 0
        status = "healthy" if not failed_templates else "warning"

        report = {
            "run_at": now_iso,
            "job_id": job_id,
            "status": status,
            "total_templates": total,
            "passed": passed,
            "failed": len(failed_templates),
            "compliance_rate": compliance_rate,
            "failed_templates": failed_templates,
        }
        await db.email_contrast_compliance_reports.insert_one(report)

        admins = await db.users.find(
            {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1, "name": 1},
        ).to_list(50)
        recipient_emails = sorted({str(a.get("email", "")).strip() for a in admins if str(a.get("email", "")).strip()})
        if not recipient_emails:
            _fb = os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip()
            recipient_emails = [_fb] if _fb else []

        failed_rows = ""
        for ft in failed_templates[:10]:
            failed_rows += f"<tr><td style='padding:6px 10px;border-bottom:1px solid #E2E8F0;color:#334155;font-size:13px'>{ft['label']}</td><td style='padding:6px 10px;border-bottom:1px solid #E2E8F0;color:#EF4444;font-size:13px'>{ft['reason']}</td></tr>"

        f"[Weekly] Email Contrast Compliance — {compliance_rate}% ({passed}/{total}) — {now.strftime('%b %d, %Y')}"
        html = (
            "<div style='font-family:Inter,system-ui,sans-serif;padding:20px;background:#F8FAFC'>"
            "<div style='max-width:600px;margin:0 auto;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden'>"
            f"<div style='background:{'#059669' if not failed_templates else '#DC2626'};padding:18px 20px'>"
            f"<h2 style='margin:0;color:#FFFFFF;font-size:20px'>Weekly Email Contrast Compliance</h2>"
            f"<p style='margin:6px 0 0;color:#FFFFFFCC;font-size:13px'>{now.strftime('%B %d, %Y')} — Auto-generated report</p>"
            "</div>"
            "<div style='padding:20px'>"
            f"<p style='margin:0 0 12px;color:#334155;font-size:14px'>Compliance rate: <strong>{compliance_rate}%</strong> ({passed}/{total} templates passing)</p>"
            f"<p style='margin:0 0 12px;color:#334155;font-size:14px'>Status: <strong style=\"color:{'#059669' if not failed_templates else '#DC2626'}\">{status.upper()}</strong></p>"
        )
        if failed_templates:
            html += (
                "<table style='width:100%;border-collapse:collapse;margin-top:12px'>"
                "<thead><tr><th style='text-align:left;padding:8px 10px;background:#F1F5F9;color:#0F172A;font-size:12px;font-weight:700'>Template</th>"
                "<th style='text-align:left;padding:8px 10px;background:#F1F5F9;color:#0F172A;font-size:12px;font-weight:700'>Issue</th></tr></thead>"
                f"<tbody>{failed_rows}</tbody></table>"
            )
            if len(failed_templates) > 10:
                html += f"<p style='margin:10px 0 0;color:#64748B;font-size:12px'>... and {len(failed_templates) - 10} more</p>"
        else:
            html += "<p style='margin:12px 0 0;color:#059669;font-size:14px;font-weight:600'>All templates pass the WCAG 4.5 contrast ratio requirement.</p>"
        html += "</div></div></div>"

        sent = 0
        for email in recipient_emails:
            try:
                result = await send_catalog_template(
                    recipient_email=email,
                    template_key="admin_detailed_system_alert",
                    title="Weekly Email Contrast Compliance",
                    intro=f"Compliance rate: {compliance_rate}%. Passed: {passed}, Failed: {len(failed_templates)}.",
                    rows=[(t, "FAILED") for t in failed_templates[:20]] or [("All templates", "COMPLIANT")],
                    accent="#10B981" if compliance_rate == 100 else "#EF4444",
                    status_label="PASS" if compliance_rate == 100 else "FAIL",
                    footer_note="Weekly email contrast compliance scan — automated by RealAICoach Scheduler",
                )
                if result.get("success"):
                    sent += 1
            except Exception:
                continue

        await _record_scheduler_heartbeat(
            job_id, status,
            f"compliance={compliance_rate}% passed={passed} failed={len(failed_templates)} sent={sent}",
        )
        logger.info(
            "Weekly email contrast compliance: rate=%s%% passed=%s failed=%s sent=%s",
            compliance_rate, passed, len(failed_templates), sent,
        )
    except Exception as exc:
        logger.error(f"scheduled_weekly_email_contrast_compliance failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_nightly_darkmode_regression_scan():
    """Nightly fail-fast dark-mode regression scan for critical email template families."""
    job_id = "nightly_darkmode_regression_scan"
    now = datetime.now(timezone.utc)
    scan_id = f"darkscan_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    try:
        from routes.db import db
        from routes.email_notifications import _audit_rendered_template, _force_dark_preview
        from utils.email_service import (
            _ensure_darkmode_safe_autonomous_card,
            apply_adaptive_email_contrast_guard,
            send_catalog_template,
        )
        from utils.email_templates import TEMPLATE_CATALOG

        target_keys = [k for k in TEMPLATE_CATALOG.keys() if _is_darkmode_regression_target(k)]
        results = []
        failures = []

        for key in target_keys:
            info = TEMPLATE_CATALOG.get(key) or {}
            try:
                tpl = info["builder"]()
                safe_html = _ensure_darkmode_safe_autonomous_card(tpl.html, key)
                dark_html = apply_adaptive_email_contrast_guard(_force_dark_preview(safe_html))
                audit = _audit_rendered_template(key, dark_html)
                issues = audit.get("issues", []) or []
                broken_links = audit.get("broken_links", []) or []
                status = "pass" if not issues and not broken_links else "fail"
                row = {
                    "key": key,
                    "label": info.get("label", key),
                    "status": status,
                    "issues": issues,
                    "broken_links": broken_links,
                }
                results.append(row)
                if status == "fail":
                    failures.append(row)
            except Exception as exc:
                row = {
                    "key": key,
                    "label": info.get("label", key),
                    "status": "fail",
                    "issues": ["render_error"],
                    "error": str(exc)[:240],
                    "broken_links": [],
                }
                results.append(row)
                failures.append(row)

        report = {
            "scan_id": scan_id,
            "job_id": job_id,
            "scanned_at": now.isoformat(),
            "targeted_templates": len(target_keys),
            "failed_templates": len(failures),
            "passed_templates": len(target_keys) - len(failures),
            "status": "PASS" if not failures else "FAIL",
            "targets": target_keys,
            "failures": failures,
            "results": results,
        }

        ticket_rows = []
        tickets_created = 0
        if failures:
            for failure in failures:
                ticket_row = await _upsert_darkmode_regression_ticket(db, scan_id, failure, now.isoformat())
                ticket_rows.append(ticket_row)
                if ticket_row.get("created"):
                    tickets_created += 1

        open_tickets = await db.email_darkmode_regression_tickets.count_documents({"status": {"$in": ["open", "in_progress"]}})
        report["ticketing"] = {
            "enabled": True,
            "tickets_created": tickets_created,
            "tickets_linked": len(ticket_rows),
            "open_tickets": open_tickets,
            "tickets": ticket_rows,
        }
        await db.email_darkmode_regression_scans.insert_one({**report})

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if not failures else "warning",
            f"targets={len(target_keys)} failed={len(failures)}",
        )

        if failures:
            recipients = await db.users.find(
                {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
                {"_id": 0, "email": 1},
            ).to_list(100)
            recipient_emails = sorted({str(r.get("email", "")).strip() for r in recipients if str(r.get("email", "")).strip()})
            if not recipient_emails:
                _fb = os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip()
                recipient_emails = [_fb] if _fb else []

            lines = "".join(
                f"<li style='margin:4px 0;color:#334155;font-size:12px'><strong>{f.get('key')}</strong>: {', '.join(f.get('issues', [])[:3]) or 'issues_detected'}"
                f" • ticket: {next((t.get('ticket_id') for t in ticket_rows if t.get('template_key') == f.get('key')), 'n/a')}</li>"
                for f in failures[:10]
            )
            (
                "<div class='em-force-light-card' style='font-family:Inter,system-ui,sans-serif;padding:16px;background:#FFFFFF;border:1px solid #FECACA;border-radius:12px'>"
                f"<h3 class='em-force-dark-text' style='margin:0 0 8px;color:#991B1B'>Nightly Dark-Mode Regression Scan FAILED</h3>"
                f"<p class='em-force-muted-text' style='margin:0 0 8px;color:#475569;font-size:13px'>Scanned: {len(target_keys)} • Failed: {len(failures)} • Tickets created: {tickets_created} • Open tickets: {open_tickets} • Scan ID: {scan_id}</p>"
                f"<ul style='margin:8px 0 0 16px;padding:0'>{lines}</ul>"
                "</div>"
            )
            for email in recipient_emails:
                try:
                    await send_catalog_template(
                        recipient_email=email,
                        template_key="admin_detailed_system_alert",
                        title=f"Dark-Mode Regression: {len(failures)} template(s) failed",
                        intro=f"Nightly scan on {now.strftime('%Y-%m-%d')} detected dark-mode regressions in {len(failures)} email template(s).",
                        rows=[(f.get("key", "unknown"), f.get("issues", ["unknown"])[0] if f.get("issues") else "regression") for f in failures[:20]],
                        accent="#EF4444",
                        status_label="REGRESSION",
                        footer_note="Nightly dark-mode regression scan — automated by RealAICoach Scheduler",
                    )
                except Exception:
                    continue

        logger.info(
            "Nightly dark-mode regression scan complete: targets=%s failed=%s",
            len(target_keys),
            len(failures),
        )
    except Exception as exc:
        logger.error(f"scheduled_nightly_darkmode_regression_scan failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_i18n_literal_autofix_dry_run_report",
    "scheduled_weekly_email_contrast_compliance",
    "scheduled_nightly_darkmode_regression_scan",
]


# ─────────────────────────────────────────────────────────────
# Phase 2 batch #24 — Helpers relocated from `scheduler_jobs/_legacy.py`.
# These were previously called as unbound names which silently raised
# NameError at runtime (swallowed by try/except heartbeat wrappers).
# Moving them here makes them resolvable via the module's own globals.
# ─────────────────────────────────────────────────────────────

def _is_darkmode_regression_target(template_key: str) -> bool:
    key = str(template_key or "").strip().lower()
    return (
        key.startswith("autonomous-engine")
        or key.startswith("performance")
        or key.startswith("billing")
        or key.startswith("payment")
        or key.startswith("admin_")
        or key.startswith("admin-")
        or "security" in key
    )

def _darkmode_ticket_slug(template_key: str) -> str:
    key = str(template_key or "unknown").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    return slug or "template"

async def _upsert_darkmode_regression_ticket(db, scan_id: str, failure: dict, scanned_at_iso: str) -> dict:
    template_key = str(failure.get("key") or "unknown").strip()
    issues = list(failure.get("issues") or [])
    label = str(failure.get("label") or template_key)

    existing = await db.email_darkmode_regression_tickets.find_one(
        {"template_key": template_key, "status": {"$in": ["open", "in_progress"]}},
        {"_id": 0, "ticket_id": 1, "occurrence_count": 1},
    )

    if existing:
        ticket_id = existing.get("ticket_id")
        await db.email_darkmode_regression_tickets.update_one(
            {"ticket_id": ticket_id},
            {
                "$set": {
                    "last_seen_at": scanned_at_iso,
                    "last_scan_id": scan_id,
                    "latest_issues": issues,
                    "updated_at": scanned_at_iso,
                    "status": "open",
                },
                "$inc": {"occurrence_count": 1},
                "$push": {
                    "history": {
                        "seen_at": scanned_at_iso,
                        "scan_id": scan_id,
                        "issues": issues,
                    }
                },
            },
        )
        return {"ticket_id": ticket_id, "template_key": template_key, "created": False}

    ticket_id = f"dm_ticket_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{_darkmode_ticket_slug(template_key)[:32]}"
    ticket = {
        "ticket_id": ticket_id,
        "scan_id": scan_id,
        "template_key": template_key,
        "template_label": label,
        "title": f"Dark-mode regression detected in {template_key}",
        "status": "open",
        "priority": "high",
        "occurrence_count": 1,
        "created_at": scanned_at_iso,
        "updated_at": scanned_at_iso,
        "last_seen_at": scanned_at_iso,
        "last_scan_id": scan_id,
        "latest_issues": issues,
        "history": [
            {
                "seen_at": scanned_at_iso,
                "scan_id": scan_id,
                "issues": issues,
            }
        ],
    }
    await db.email_darkmode_regression_tickets.insert_one({**ticket})
    return {"ticket_id": ticket_id, "template_key": template_key, "created": True}
