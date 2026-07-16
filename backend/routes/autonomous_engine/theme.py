"""Theme health center, guardrail scanning, drift detection, token remediation, drift tickets."""
import hashlib
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, DEFAULT_DRIFT_ALERT_CONFIG,
)
from services.autonomous.common import resolve_external_base_url as _resolve_external_base_url


def _responsive_guardrail_target_files() -> List[Path]:
    app_root = Path(__file__).resolve().parents[3]
    frontend_root = app_root / "frontend"
    patterns = [
        "app/**/*.tsx",
        "src/components/admin/**/*.tsx",
        "src/components/executive/**/*.tsx",
    ]
    files: List[Path] = []
    seen = set()
    for pattern in patterns:
        for path in frontend_root.glob(pattern):
            if not path.is_file():
                continue
            if path.name.endswith(".d.ts"):
                continue
            if str(path) in seen:
                continue
            seen.add(str(path))
            files.append(path)
    return sorted(files, key=lambda p: str(p))


def _scan_file_for_responsive_risks(path: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = text.splitlines()
    responsive_tokens = ["tab", "tabs", "chip", "chips", "pill", "pills", "filter", "quick-link", "section", "preset", "category"]

    for idx, line in enumerate(lines):
        low = line.lower()
        if "scrollview" in low and "horizontal" in low:
            window = "\n".join(lines[idx: min(idx + 25, len(lines))]).lower()
            has_responsive_context = any(token in window for token in responsive_tokens)
            if has_responsive_context and "flexwrap" not in window and "flex-wrap" not in window:
                findings.append({
                    "rule": "horizontal-scroll-no-wrap",
                    "severity": "medium",
                    "line": idx + 1,
                    "message": "Responsive tab/chip rail uses horizontal ScrollView without nearby wrap fallback.",
                })

        if "overflow" in low and "hidden" in low and any(k in low for k in ["tab", "chip", "pill", "filter"]):
            findings.append({
                "rule": "overflow-hidden-tab-like-container",
                "severity": "medium",
                "line": idx + 1,
                "message": "Overflow hidden detected around tab/chip context.",
            })

    return findings


async def _run_responsive_guardrail_scan(triggered_by: str) -> Dict[str, Any]:
    db = await _db()
    files = _responsive_guardrail_target_files()
    findings: List[Dict[str, Any]] = []

    app_root = Path(__file__).resolve().parents[3]
    for path in files:
        rel = str(path.relative_to(app_root))
        file_findings = _scan_file_for_responsive_risks(path)
        for item in file_findings:
            findings.append({"file": rel, **item})

    high_count = sum(1 for f in findings if f.get("severity") == "high")
    medium_count = sum(1 for f in findings if f.get("severity") == "medium")
    low_count = sum(1 for f in findings if f.get("severity") == "low")
    deductions = (high_count * 12.0) + (medium_count * 0.6) + (low_count * 0.2)
    guardrail_score = round(max(0.0, 100.0 - deductions), 1)
    status = "PASS" if high_count == 0 else "FAIL"

    run = {
        "run_id": f"rg_{uuid.uuid4().hex[:10]}",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "responsive_guardrail_score": guardrail_score,
        "files_scanned": len(files),
        "issues_total": len(findings),
        "issues_by_severity": {
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
        },
        "findings": findings[:200],
        "triggered_by": triggered_by,
    }
    await db.responsive_guardrail_runs.insert_one({**run})
    return run


async def _latest_responsive_guardrail_run() -> Optional[Dict[str, Any]]:
    db = await _db()
    return await db.responsive_guardrail_runs.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])


def _theme_guardrail_target_files() -> List[Path]:
    app_root = Path(__file__).resolve().parents[3]
    frontend_root = app_root / "frontend"
    patterns = [
        "app/**/*.tsx",
        "src/components/**/*.tsx",
    ]
    files: List[Path] = []
    seen = set()
    for pattern in patterns:
        for path in frontend_root.glob(pattern):
            if not path.is_file() or str(path) in seen:
                continue
            seen.add(str(path))
            files.append(path)
    return sorted(files, key=lambda p: str(p))


def _scan_file_for_theme_risks(path: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = text.splitlines()
    lower = text.lower()
    has_use_theme = "usetheme(" in lower
    has_colors_prop = bool(re.search(r"\{\s*colors\s*\}|colors\s*:\s*any|colors\s*:\s*\w+", text))
    has_theme_tokens = "colors." in lower or "darkmode" in lower or "themeMode" in lower or has_colors_prop
    has_app_shell = "<appshell" in lower
    has_public_shell = "publicpageshell" in lower or "publicpagelayout" in lower
    path_lower = str(path).lower()
    is_admin_or_core_surface = any(token in path_lower for token in ["/admin", "dashboard", "console", "autonomous", "executive"])

    hex_matches = re.findall(r"#[0-9a-fA-F]{6,8}", text)
    hex_count = len(hex_matches)

    if hex_count >= 40 and not has_use_theme and not has_public_shell and not has_theme_tokens:
        findings.append({
            "rule": "hardcoded-colors-without-theme-hook",
            "severity": "medium",
            "line": 1,
            "message": f"{hex_count} hardcoded colors found without useTheme hook.",
        })
    elif hex_count >= 30 and has_use_theme and not has_theme_tokens:
        findings.append({
            "rule": "theme-hook-not-used-in-styles",
            "severity": "medium",
            "line": 1,
            "message": f"{hex_count} hardcoded colors found while theme hook tokens are scarcely used.",
        })

    dark_bg_hits = 0
    for idx, line in enumerate(lines, start=1):
        low = line.lower()
        if "backgroundcolor" in low and re.search(r"#0[0-9a-f]{5,7}", low):
            dark_bg_hits += 1
        if "color" in low and "#fff" in low and "darkmode" not in low and "colors." not in low:
            findings.append({
                "rule": "hardcoded-white-text-no-theme-guard",
                "severity": "low",
                "line": idx,
                "message": "Hardcoded white text without explicit theme guard.",
            })

    if dark_bg_hits >= 5 and has_app_shell and not has_theme_tokens:
        findings.append({
            "rule": "appshell-dark-only-surface",
            "severity": "high" if is_admin_or_core_surface else "medium",
            "line": 1,
            "message": "AppShell page appears dark-only with no light-mode token switching.",
        })
    elif dark_bg_hits >= 5 and not has_theme_tokens:
        findings.append({
            "rule": "dark-only-surface-pattern",
            "severity": "low",
            "line": 1,
            "message": "Multiple dark-only backgrounds found without theme fallback.",
        })

    return findings


async def _trim_theme_guardrail_history(max_rows: int = 500):
    db = await _db()
    total = await db.theme_guardrail_runs.count_documents({})
    if total <= max_rows:
        return
    overflow = total - max_rows
    rows = await db.theme_guardrail_runs.find({}, {"_id": 1}).sort("checked_at", 1).limit(overflow).to_list(overflow)
    if rows:
        await db.theme_guardrail_runs.delete_many({"_id": {"$in": [row["_id"] for row in rows]}})


async def _run_theme_guardrail_scan(triggered_by: str) -> Dict[str, Any]:
    db = await _db()
    files = _theme_guardrail_target_files()
    findings: List[Dict[str, Any]] = []
    app_root = Path(__file__).resolve().parents[3]

    for path in files:
        rel = str(path.relative_to(app_root))
        file_findings = _scan_file_for_theme_risks(path)
        for item in file_findings:
            findings.append({"file": rel, **item})

    high_count = sum(1 for f in findings if f.get("severity") == "high")
    medium_count = sum(1 for f in findings if f.get("severity") == "medium")
    low_count = sum(1 for f in findings if f.get("severity") == "low")
    deductions = (high_count * 8.0) + (medium_count * 0.8) + (low_count * 0.02)
    score = round(max(0.0, 100.0 - deductions), 1)
    status = "PASS" if high_count == 0 else "FAIL"

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(findings, key=lambda row: (severity_order.get(str(row.get("severity") or "low"), 3), row.get("file", "")))

    run = {
        "run_id": f"tg_{uuid.uuid4().hex[:10]}",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "theme_guardrail_score": score,
        "files_scanned": len(files),
        "issues_total": len(findings),
        "issues_by_severity": {"high": high_count, "medium": medium_count, "low": low_count},
        "findings": findings[:250],
        "triggered_by": triggered_by,
    }
    await db.theme_guardrail_runs.insert_one({**run})
    await _trim_theme_guardrail_history(500)
    return run


async def _latest_theme_guardrail_run() -> Optional[Dict[str, Any]]:
    db = await _db()
    return await db.theme_guardrail_runs.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])


def _theme_drift_ticket_key(file_path: str, rule: str) -> str:
    seed = f"{str(file_path or '').strip()}|{str(rule or '').strip().lower()}"
    return f"tgt_{hashlib.md5(seed.encode()).hexdigest()[:16]}"


async def _upsert_theme_drift_ticket(
    grouped_finding: Dict[str, Any],
    run_id: str,
    checked_at: str,
) -> Dict[str, Any]:
    db = await _db()
    file_path = str(grouped_finding.get("file") or "")
    rule = str(grouped_finding.get("rule") or "unknown")
    severity = str(grouped_finding.get("severity") or "medium").lower()
    message = str(grouped_finding.get("message") or "Theme drift detected")
    line = int(grouped_finding.get("line") or 0)
    occurrence_delta = int(grouped_finding.get("occurrence_count") or 1)
    sample_lines = [int(v) for v in (grouped_finding.get("sample_lines") or []) if int(v) > 0][:8]
    ticket_key = _theme_drift_ticket_key(file_path, rule)
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = await db.theme_guardrail_tickets.find_one(
        {"ticket_key": ticket_key},
        {"_id": 0, "ticket_id": 1, "status": 1, "occurrence_count": 1},
    )

    if existing and str(existing.get("status") or "").lower() in {"open", "in_progress"}:
        await db.theme_guardrail_tickets.update_one(
            {"ticket_key": ticket_key},
            {
                "$set": {
                    "severity": severity,
                    "message": message,
                    "file": file_path,
                    "rule": rule,
                    "line": line,
                    "sample_lines": sample_lines,
                    "latest_run_id": run_id,
                    "latest_detected_at": checked_at,
                    "updated_at": now_iso,
                },
                "$inc": {"occurrence_count": max(1, occurrence_delta)},
            },
            upsert=False,
        )
        return {"action": "updated", "ticket_id": existing.get("ticket_id"), "ticket_key": ticket_key}

    ticket_id = f"TGT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "ticket_id": ticket_id,
        "ticket_key": ticket_key,
        "status": "open",
        "severity": severity,
        "message": message,
        "file": file_path,
        "rule": rule,
        "line": line,
        "sample_lines": sample_lines,
        "occurrence_count": max(1, occurrence_delta),
        "created_at": now_iso,
        "updated_at": now_iso,
        "first_detected_at": checked_at,
        "latest_detected_at": checked_at,
        "latest_run_id": run_id,
        "source": "theme_drift_nightly",
    }
    await db.theme_guardrail_tickets.insert_one({**payload})
    return {"action": "created", "ticket_id": ticket_id, "ticket_key": ticket_key}


async def _trim_theme_drift_nightly_history(max_rows: int = 365):
    db = await _db()
    total = await db.theme_guardrail_nightly_runs.count_documents({})
    if total <= max_rows:
        return
    overflow = total - max_rows
    rows = (
        await db.theme_guardrail_nightly_runs.find({}, {"_id": 1})
        .sort("checked_at", 1)
        .limit(overflow)
        .to_list(overflow)
    )
    if rows:
        await db.theme_guardrail_nightly_runs.delete_many({"_id": {"$in": [row["_id"] for row in rows]}})


async def _run_theme_drift_nightly_detector(triggered_by: str) -> Dict[str, Any]:
    from utils.email_service import is_email_configured

    db = await _db()
    scan = await _run_theme_guardrail_scan(triggered_by=f"{triggered_by}:nightly")
    run_id = str(scan.get("run_id") or f"tgn_{uuid.uuid4().hex[:10]}")
    checked_at = str(scan.get("checked_at") or datetime.now(timezone.utc).isoformat())
    findings = scan.get("findings") or []

    grouped: Dict[str, Dict[str, Any]] = {}
    for finding in findings:
        severity = str(finding.get("severity") or "").lower()
        if severity not in {"high", "medium"}:
            continue
        file_path = str(finding.get("file") or "")
        rule = str(finding.get("rule") or "unknown")
        key = _theme_drift_ticket_key(file_path, rule)
        if key not in grouped:
            grouped[key] = {
                "file": file_path,
                "rule": rule,
                "severity": severity,
                "message": str(finding.get("message") or "Theme drift detected"),
                "line": int(finding.get("line") or 0),
                "occurrence_count": 0,
                "sample_lines": [],
            }
        grouped[key]["occurrence_count"] += 1
        line = int(finding.get("line") or 0)
        if line > 0 and line not in grouped[key]["sample_lines"] and len(grouped[key]["sample_lines"]) < 8:
            grouped[key]["sample_lines"].append(line)

    created_tickets = 0
    updated_tickets = 0
    ticket_rows: List[Dict[str, Any]] = []
    for entry in grouped.values():
        ticket_result = await _upsert_theme_drift_ticket(entry, run_id=run_id, checked_at=checked_at)
        ticket_rows.append({**entry, **ticket_result})
        if ticket_result.get("action") == "created":
            created_tickets += 1
        elif ticket_result.get("action") == "updated":
            updated_tickets += 1

    open_tickets = await db.theme_guardrail_tickets.count_documents({"status": {"$in": ["open", "in_progress"]}})
    run = {
        "run_id": f"tgn_{uuid.uuid4().hex[:10]}",
        "checked_at": checked_at,
        "triggered_by": triggered_by,
        "source_scan": {
            "run_id": run_id,
            "status": scan.get("status"),
            "theme_guardrail_score": scan.get("theme_guardrail_score"),
            "issues_total": scan.get("issues_total"),
            "issues_by_severity": scan.get("issues_by_severity", {}),
        },
        "ticket_summary": {
            "candidates": len(grouped),
            "created": created_tickets,
            "updated": updated_tickets,
            "open_tickets": open_tickets,
        },
        "tickets": ticket_rows[:100],
    }
    await db.theme_guardrail_nightly_runs.insert_one({**run})
    await _trim_theme_drift_nightly_history(365)

    if ticket_rows and is_email_configured():
        try:
            from routes.db import ADMIN_EMAIL

            recipients: List[str] = []
            admin_rows = await db.users.find(
                {"role": {"$in": ["admin", "super_admin"]}},
                {"_id": 0, "email": 1},
            ).limit(20).to_list(20)
            for row in admin_rows:
                email = str(row.get("email") or "").strip()
                if email and "@" in email:
                    recipients.append(email)
            if not recipients and ADMIN_EMAIL:
                recipients = [str(ADMIN_EMAIL)]
            recipients = sorted(set(recipients))
            if recipients:
                rows_html = "".join(
                    [
                        (
                            "<tr>"
                            f"<td style='padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#0F172A;font-size:12px'>{row.get('ticket_id')}</td>"
                            f"<td style='padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#334155;font-size:12px'>{row.get('severity')}</td>"
                            f"<td style='padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#334155;font-size:12px'>{row.get('file')}</td>"
                            f"<td style='padding:8px 10px;border-bottom:1px solid #E2E8F0;color:#334155;font-size:12px'>{row.get('action')}</td>"
                            "</tr>"
                        )
                        for row in ticket_rows[:20]
                    ]
                )
                (
                    "<div style='background:#F8FAFC;padding:20px;font-family:Arial,sans-serif'>"
                    "<div style='max-width:860px;margin:0 auto;background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:16px'>"
                    "<h2 style='margin:0 0 10px;color:#0F172A'>Nightly Theme Drift Detector</h2>"
                    f"<p style='margin:0 0 12px;color:#475569;font-size:13px'>Run: {run.get('run_id')} • Created: {created_tickets} • Updated: {updated_tickets} • Open: {open_tickets}</p>"
                    "<table style='width:100%;border-collapse:collapse'>"
                    "<thead><tr style='background:#F8FAFC'>"
                    "<th style='padding:8px 10px;text-align:left;color:#475569;font-size:11px'>Ticket</th>"
                    "<th style='padding:8px 10px;text-align:left;color:#475569;font-size:11px'>Severity</th>"
                    "<th style='padding:8px 10px;text-align:left;color:#475569;font-size:11px'>File</th>"
                    "<th style='padding:8px 10px;text-align:left;color:#475569;font-size:11px'>Action</th>"
                    "</tr></thead>"
                    f"<tbody>{rows_html}</tbody></table></div></div>"
                )
                for email in recipients[:5]:
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=email,
                        template_key="admin_detailed_system_alert",
                        title="Theme Drift Detector",
                        intro=f"Nightly scan completed: {created_tickets} tickets created, {updated_tickets} updated.",
                        rows=[("Created", str(created_tickets)), ("Updated", str(updated_tickets))],
                        accent="#8B5CF6",
                        status_label="NIGHTLY",
                        footer_note="Theme Drift Detector — Nightly Scan Report",
                    )
        except Exception:
            pass

    # Auto-remediation step: fix safe tokens automatically
    remediation_result = None
    try:
        remediation_result = await _run_theme_token_auto_remediation(
            triggered_by=f"{triggered_by}:auto-remediation",
            dry_run=False,
            max_fixes=30,
        )
    except Exception as rexc:
        remediation_result = {"error": str(rexc)[:200]}

    run["auto_remediation"] = {
        "run_id": (remediation_result or {}).get("run_id"),
        "total_applied": (remediation_result or {}).get("total_applied", 0),
        "total_findings": (remediation_result or {}).get("total_findings", 0),
        "error": (remediation_result or {}).get("error"),
    }
    await db.theme_guardrail_nightly_runs.update_one(
        {"run_id": run["run_id"]},
        {"$set": {"auto_remediation": run["auto_remediation"]}},
    )

    # Slack/Teams alerts for high-severity new tickets
    alert_results: List[Dict[str, Any]] = []
    new_tickets = [row for row in ticket_rows if row.get("action") == "created"]
    try:
        config_full = await _get_engine_config()
        alert_config = config_full.get("drift_alert_config", {**DEFAULT_DRIFT_ALERT_CONFIG})
        if alert_config.get("enabled") and (alert_config.get("slack_webhook_url") or alert_config.get("teams_webhook_url")):
            from services.drift_alerts import dispatch_drift_alerts
            new_high = [t for t in new_tickets if t.get("severity") in ("high", "critical")]
            if new_high:
                dashboard_url = f"{_resolve_external_base_url()}/executive-dashboard?section=security"
                alert_results = await dispatch_drift_alerts(new_high, alert_config, dashboard_url)
    except Exception as aexc:
        alert_results = [{"error": str(aexc)[:200]}]
    run["drift_alerts"] = {"sent": len([r for r in alert_results if r.get("ok")]), "failed": len([r for r in alert_results if not r.get("ok")]), "results": alert_results[:10]}
    await db.theme_guardrail_nightly_runs.update_one(
        {"run_id": run["run_id"]},
        {"$set": {"drift_alerts": run["drift_alerts"]}},
    )

    return run


async def _latest_theme_drift_nightly_run() -> Optional[Dict[str, Any]]:
    db = await _db()
    return await db.theme_guardrail_nightly_runs.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])


def _theme_surface_label(file_path: str) -> str:
    value = str(file_path or "").strip()
    if not value:
        return "Unknown surface"

    normalized = value.replace("\\", "/")
    if normalized.startswith("frontend/app/"):
        route = normalized.replace("frontend/app", "", 1)
        route = route.replace("index.tsx", "")
        route = route.replace(".tsx", "")
        route = route.replace(".ts", "")
        route = route.replace("/(tabs)", "")
        route = route.replace("//", "/")
        route = route.rstrip("/") or "/"
        return route

    if normalized.startswith("frontend/src/components/"):
        return normalized.replace("frontend/src/components/", "component/")

    return normalized


async def _build_theme_health_center_overview(
    matrix_limit: int = 60,
    run_limit: int = 10,
    ticket_limit: int = 12,
) -> Dict[str, Any]:
    latest_scan = await _latest_theme_guardrail_run()
    latest_nightly = await _latest_theme_drift_nightly_run()
    db = await _db()

    history = await db.theme_guardrail_runs.find({}, {"_id": 0}).sort("checked_at", -1).limit(run_limit).to_list(run_limit)
    open_tickets = await db.theme_guardrail_tickets.find(
        {"status": {"$in": ["open", "in_progress"]}},
        {"_id": 0},
    ).sort("updated_at", -1).limit(ticket_limit).to_list(ticket_limit)

    findings = list((latest_scan or {}).get("findings") or [])
    findings_by_file: Dict[str, List[Dict[str, Any]]] = {}
    for finding in findings:
        file_path = str(finding.get("file") or "").strip()
        if not file_path:
            continue
        findings_by_file.setdefault(file_path, []).append(finding)

    matrix_rows: List[Dict[str, Any]] = []
    for path in _theme_guardrail_target_files():
        rel = str(path.relative_to(Path(__file__).resolve().parents[3]))
        file_findings = findings_by_file.get(rel, [])
        severity_counts = {
            "high": sum(1 for item in file_findings if str(item.get("severity") or "").lower() == "high"),
            "medium": sum(1 for item in file_findings if str(item.get("severity") or "").lower() == "medium"),
            "low": sum(1 for item in file_findings if str(item.get("severity") or "").lower() == "low"),
        }
        if severity_counts["high"] > 0 or severity_counts["medium"] > 0:
            status = "attention"
        elif severity_counts["low"] > 0:
            status = "watch"
        else:
            status = "pass"

        rules = []
        for item in file_findings[:3]:
            rule = str(item.get("rule") or "unknown")
            if rule not in rules:
                rules.append(rule)

        matrix_rows.append(
            {
                "surface": _theme_surface_label(rel),
                "file": rel,
                "status": status,
                "issues_total": len(file_findings),
                "issues_by_severity": severity_counts,
                "sample_rules": rules,
            }
        )

    status_rank = {"attention": 0, "watch": 1, "pass": 2}
    matrix_rows = sorted(
        matrix_rows,
        key=lambda row: (
            status_rank.get(str(row.get("status") or "pass"), 9),
            -int(row.get("issues_total") or 0),
            str(row.get("surface") or ""),
        ),
    )

    regression_timeline = []
    for run in reversed(history):
        severity = run.get("issues_by_severity") or {}
        regression_timeline.append(
            {
                "run_id": run.get("run_id"),
                "checked_at": run.get("checked_at"),
                "status": run.get("status"),
                "theme_guardrail_score": run.get("theme_guardrail_score"),
                "issues_total": run.get("issues_total"),
                "high": int(severity.get("high") or 0),
                "medium": int(severity.get("medium") or 0),
                "low": int(severity.get("low") or 0),
            }
        )

    matrix_summary = {
        "total_surfaces": len(matrix_rows),
        "pass": sum(1 for row in matrix_rows if row.get("status") == "pass"),
        "watch": sum(1 for row in matrix_rows if row.get("status") == "watch"),
        "attention": sum(1 for row in matrix_rows if row.get("status") == "attention"),
    }

    top_tickets = [
        {
            "ticket_id": row.get("ticket_id"),
            "status": row.get("status"),
            "severity": row.get("severity"),
            "file": row.get("file"),
            "rule": row.get("rule"),
            "message": row.get("message"),
            "occurrence_count": int(row.get("occurrence_count") or 0),
            "latest_detected_at": row.get("latest_detected_at"),
        }
        for row in open_tickets
    ]

    return {
        "latest_scan": latest_scan
        or {
            "run_id": None,
            "checked_at": None,
            "status": "NOT_RUN",
            "theme_guardrail_score": 0,
            "files_scanned": 0,
            "issues_total": 0,
            "issues_by_severity": {"high": 0, "medium": 0, "low": 0},
            "findings": [],
            "triggered_by": None,
        },
        "latest_nightly": latest_nightly
        or {
            "run_id": None,
            "checked_at": None,
            "triggered_by": None,
            "source_scan": None,
            "ticket_summary": {"candidates": 0, "created": 0, "updated": 0, "open_tickets": 0},
            "tickets": [],
        },
        "matrix_summary": matrix_summary,
        "route_pass_matrix": matrix_rows[:matrix_limit],
        "regression_timeline": regression_timeline,
        "recent_runs": history,
        "open_tickets": top_tickets,
    }


@router.get("/theme-health-center/overview")
async def get_theme_health_center_overview(
    request: Request,
    matrix_limit: int = Query(default=60, ge=10, le=200),
    run_limit: int = Query(default=10, ge=3, le=30),
    ticket_limit: int = Query(default=12, ge=5, le=30),
):
    await _require_admin(request)
    return await _build_theme_health_center_overview(
        matrix_limit=matrix_limit,
        run_limit=run_limit,
        ticket_limit=ticket_limit,
    )


def _theme_rule_recommendation(rule: str) -> Dict[str, Any]:
    normalized = str(rule or "").strip().lower()
    mapping: Dict[str, Dict[str, Any]] = {
        "hardcoded-white-text-no-theme-guard": {
            "safe_auto_fix": True,
            "risk_level": "low",
            "title": "Replace hardcoded white text",
            "suggested_fix": "Replace `#fff`/`#ffffff` text colors with `colors.text` or a dark/light conditional token.",
            "safe_action": "tokenize_text_color",
        },
        "dark-only-surface-pattern": {
            "safe_auto_fix": True,
            "risk_level": "low",
            "title": "Add adaptive surface tokens",
            "suggested_fix": "Replace dark-only background values with `colors.bg`/`colors.card` and `darkMode` guards.",
            "safe_action": "tokenize_surface_background",
        },
        "theme-hook-not-used-in-styles": {
            "safe_auto_fix": False,
            "risk_level": "medium",
            "title": "Theme hook not fully wired",
            "suggested_fix": "Propagate `useTheme()` tokens into style objects used by repeated UI blocks.",
            "safe_action": "requires_manual_review",
        },
        "hardcoded-colors-without-theme-hook": {
            "safe_auto_fix": False,
            "risk_level": "medium",
            "title": "Add useTheme hook",
            "suggested_fix": "Introduce `useTheme()` and replace hardcoded palette with `colors.*` tokens.",
            "safe_action": "requires_manual_review",
        },
    }
    return mapping.get(
        normalized,
        {
            "safe_auto_fix": False,
            "risk_level": "medium",
            "title": "General theme token cleanup",
            "suggested_fix": "Replace hardcoded colors with adaptive `colors.*` tokens and verify dark/light parity.",
            "safe_action": "requires_manual_review",
        },
    )


async def _build_theme_low_severity_suggestions(limit: int = 20) -> Dict[str, Any]:
    db = await _db()
    latest = await _latest_theme_guardrail_run()
    if not latest:
        return {
            "source_run_id": None,
            "source_checked_at": None,
            "total": 0,
            "safe_ready": 0,
            "completed": 0,
            "pending": 0,
            "suggestions": [],
        }

    grouped: Dict[str, Dict[str, Any]] = {}
    for finding in latest.get("findings", []):
        if str(finding.get("severity") or "").lower() != "low":
            continue

        file_path = str(finding.get("file") or "")
        rule = str(finding.get("rule") or "unknown")
        message = str(finding.get("message") or "Theme finding")
        line = int(finding.get("line") or 0)
        seed = f"{file_path}|{rule}|{message}"
        suggestion_id = f"tgs_{hashlib.md5(seed.encode()).hexdigest()[:12]}"
        recommendation = _theme_rule_recommendation(rule)

        if suggestion_id not in grouped:
            grouped[suggestion_id] = {
                "suggestion_id": suggestion_id,
                "file": file_path,
                "rule": rule,
                "severity": "low",
                "message": message,
                "occurrence_count": 0,
                "sample_lines": [],
                "safe_auto_fix": bool(recommendation.get("safe_auto_fix")),
                "safe_action": recommendation.get("safe_action"),
                "risk_level": recommendation.get("risk_level"),
                "title": recommendation.get("title"),
                "suggested_fix": recommendation.get("suggested_fix"),
            }

        grouped[suggestion_id]["occurrence_count"] += 1
        if line > 0 and len(grouped[suggestion_id]["sample_lines"]) < 5:
            grouped[suggestion_id]["sample_lines"].append(line)

    suggestions = list(grouped.values())
    if not suggestions:
        return {
            "source_run_id": latest.get("run_id"),
            "source_checked_at": latest.get("checked_at"),
            "total": 0,
            "safe_ready": 0,
            "completed": 0,
            "pending": 0,
            "suggestions": [],
        }

    tracker_rows = await db.theme_guardrail_suggestion_tracker.find(
        {"suggestion_id": {"$in": [row["suggestion_id"] for row in suggestions]}},
        {"_id": 0},
    ).to_list(300)
    tracker_map = {str(row.get("suggestion_id")): row for row in tracker_rows}

    for row in suggestions:
        tracker = tracker_map.get(row["suggestion_id"], {})
        row["status"] = tracker.get("status", "pending")
        row["updated_at"] = tracker.get("updated_at")
        row["updated_by"] = tracker.get("updated_by")
        row["note"] = tracker.get("note")
        row["priority_score"] = (row["occurrence_count"] * 2) + (3 if row["safe_auto_fix"] else 1)

    total_available = len(suggestions)
    completed_total = sum(1 for row in suggestions if row.get("status") == "completed")
    safe_ready_total = sum(1 for row in suggestions if row.get("safe_auto_fix") and row.get("status") == "pending")

    suggestions = sorted(
        suggestions,
        key=lambda row: (
            0 if row.get("status") == "pending" else 1,
            -int(row.get("priority_score") or 0),
            row.get("file") or "",
        ),
    )[: max(1, min(int(limit), 100))]

    return {
        "source_run_id": latest.get("run_id"),
        "source_checked_at": latest.get("checked_at"),
        "total": total_available,
        "safe_ready": safe_ready_total,
        "completed": completed_total,
        "pending": total_available - completed_total,
        "suggestions": suggestions,
    }


async def _trim_theme_safe_autofix_history(max_rows: int = 200):
    db = await _db()
    total = await db.theme_guardrail_safe_autofix_runs.count_documents({})
    if total <= max_rows:
        return
    overflow = total - max_rows
    rows = await db.theme_guardrail_safe_autofix_runs.find({}, {"_id": 1}).sort("executed_at", 1).limit(overflow).to_list(overflow)
    if rows:
        await db.theme_guardrail_safe_autofix_runs.delete_many({"_id": {"$in": [row["_id"] for row in rows]}})


async def _run_theme_safe_autofix(triggered_by: str) -> Dict[str, Any]:
    from routes.ai_autofix_engine import run_all_fixes

    db = await _db()
    executed_at = datetime.now(timezone.utc).isoformat()
    ai_autofix = await run_all_fixes()
    theme_guardrail = await _run_theme_guardrail_scan(triggered_by=f"{triggered_by}:safe-autofix")
    suggestions = await _build_theme_low_severity_suggestions(limit=50)

    run = {
        "run_id": f"tsaf_{uuid.uuid4().hex[:10]}",
        "executed_at": executed_at,
        "triggered_by": triggered_by,
        "safe_mode": "auto_low_risk_only",
        "ai_autofix": {
            "total_proposed": ai_autofix.get("total_proposed", 0),
            "total_applied": ai_autofix.get("total_applied", 0),
            "total_flagged": ai_autofix.get("total_flagged", 0),
            "confidence_threshold": ai_autofix.get("confidence_threshold"),
        },
        "theme_guardrail": {
            "run_id": theme_guardrail.get("run_id"),
            "status": theme_guardrail.get("status"),
            "score": theme_guardrail.get("theme_guardrail_score"),
            "issues_total": theme_guardrail.get("issues_total"),
            "issues_by_severity": theme_guardrail.get("issues_by_severity", {}),
        },
        "suggestion_summary": {
            "total": suggestions.get("total", 0),
            "safe_ready": suggestions.get("safe_ready", 0),
            "completed": suggestions.get("completed", 0),
            "pending": suggestions.get("pending", 0),
        },
    }
    await db.theme_guardrail_safe_autofix_runs.insert_one({**run})
    await _trim_theme_safe_autofix_history(200)
    return run


# ─── Theme Token Auto-Remediation Engine ───

_DARK_TOKEN_REPLACEMENTS: Dict[str, str] = {
    "#0F172A": "colors.card",
    "#111827": "colors.cardMuted",
    "#1E293B": "colors.border",
    "#020617": "colors.bg",
    "#050A18": "colors.bg",
    "#0B0F1A": "colors.bgAlt",
    "#08101F": "colors.bg",
    "#1A2236": "colors.border",
    "#151D2E": "colors.cardMuted",
}

_SKIP_FILENAMES = {"ThemeContext.tsx", "ThemeEnforcer.tsx", "+html.tsx", "colors.ts", "designTokens.ts"}

_SKIP_PATTERNS = re.compile(
    r"(radial-gradient|linear-gradient|\.style\.backgroundColor|var\(--)"
)

_SKIP_LINE_STARTS = re.compile(
    r"^\s*(//|/\*|\*|import\s|from\s)"
)


def _compute_token_fix(line: str, hex_token: str, replacement: str) -> Optional[str]:
    """Compute a safe replacement for a hardcoded hex token in a single line."""
    stripped = line.strip()
    if _SKIP_LINE_STARTS.match(stripped):
        return None
    if _SKIP_PATTERNS.search(line):
        return None

    # Pattern 1: darkMode ? '#HEX' : ...  => darkMode ? colors.X : ...
    dark_ternary = re.compile(
        r"""((?:darkMode|dark|dm|isDark|isDarkMode)\s*\?\s*)['"]""" + re.escape(hex_token) + r"""['"]""",
        re.IGNORECASE,
    )
    m = dark_ternary.search(line)
    if m:
        return dark_ternary.sub(m.group(1) + replacement, line)

    # Pattern 2: ... ? '#something' : '#HEX' (dark fallback in else branch)
    else_branch = re.compile(
        r"""(:\s*)['"]""" + re.escape(hex_token) + r"""['"]""",
    )
    m_else = else_branch.search(line)
    if m_else and ("?" in line[:m_else.start()]):
        return else_branch.sub(m_else.group(1) + replacement, line, count=1)

    # Pattern 3: style prop => color/backgroundColor: '#HEX'
    style_prop = re.compile(
        r"""((?:color|backgroundColor|background|borderColor|borderTopColor|borderBottomColor)\s*:\s*)['"]""" + re.escape(hex_token) + r"""['"]""",
        re.IGNORECASE,
    )
    m2 = style_prop.search(line)
    if m2:
        return style_prop.sub(m2.group(1) + replacement, line)

    # Pattern 4: object palette key => key: '#HEX' (inside objects that already have colors.X)
    palette_key = re.compile(
        r"""((?:bgAlt|surface|surfaceHover|neutralBg|card|ink|actionBg|text|loaderBg|sidebarBg|aiBubble|tagBg|summaryBg)\s*:\s*)['"]""" + re.escape(hex_token) + r"""['"]""",
        re.IGNORECASE,
    )
    m4 = palette_key.search(line)
    if m4:
        return palette_key.sub(m4.group(1) + replacement, line)

    # Pattern 5: || '#HEX' fallback => || colors.X
    fallback = re.compile(
        r"""\|\|\s*['"]""" + re.escape(hex_token) + r"""['"]""",
    )
    m3 = fallback.search(line)
    if m3:
        return fallback.sub(f"|| {replacement}", line)

    # Pattern 6: theme === 'dark' ? '#HEX' : ...
    theme_eq = re.compile(
        r"""((?:theme|previewTheme)\s*===?\s*['"]dark['"]\s*\?\s*)['"]""" + re.escape(hex_token) + r"""['"]""",
        re.IGNORECASE,
    )
    m6 = theme_eq.search(line)
    if m6:
        return theme_eq.sub(m6.group(1) + replacement, line)

    return None


def _scan_and_fix_file(path: Path) -> Dict[str, Any]:
    """Scan a file for hardcoded dark tokens and compute safe fixes.
    
    SCOPE SAFETY: Only marks fixes as safe if the target line is inside a
    React component/function that destructures `colors` from `useTheme()`.
    Module-scope functions, standalone getColors(), and any code outside
    a useTheme-aware scope are marked unsafe and never auto-applied.
    """
    filename = path.name
    if filename in _SKIP_FILENAMES:
        return {"file": str(path), "skipped": True, "reason": "excluded file", "fixes": []}

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"file": str(path), "skipped": True, "reason": "unreadable", "fixes": []}

    lines = text.splitlines()

    # ── Build a line-level scope map: which lines are inside a useTheme-aware scope ──
    # A "safe scope" is a function/component body that contains `useTheme()` with `colors`
    # destructured (e.g., `const { colors } = useTheme()` or `const { colors, darkMode } = useTheme()`)
    safe_lines = set()
    _build_safe_scope_map(lines, safe_lines)

    fixes: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        for hex_token, replacement in _DARK_TOKEN_REPLACEMENTS.items():
            if hex_token in line or hex_token.lower() in line.lower():
                fixed_line = _compute_token_fix(line, hex_token, replacement)
                if fixed_line and fixed_line != line:
                    is_safe = (idx + 1) in safe_lines
                    fixes.append({
                        "line": idx + 1,
                        "token": hex_token,
                        "replacement": replacement,
                        "original": line.rstrip()[:200],
                        "fixed": fixed_line.rstrip()[:200],
                        "safe": is_safe,
                    })

    has_any_safe = any(f.get("safe") for f in fixes)
    return {"file": str(path), "skipped": False, "has_theme_import": has_any_safe, "fixes": fixes}


def _build_safe_scope_map(lines: List[str], safe_lines: set):
    """Identify line ranges that are inside a function/component with `colors` from useTheme().
    
    Strategy:
    1. Find all lines with `useTheme()` that destructure `colors`
    2. Walk backward to find the enclosing function/component declaration
    3. Walk forward to find the matching closing brace
    4. Mark all lines within that scope as safe
    """
    colors_usetheme_pattern = re.compile(
        r"""const\s+\{[^}]*\bcolors\b[^}]*\}\s*=\s*useTheme\s*\(""",
    )

    for i, line in enumerate(lines):
        if not colors_usetheme_pattern.search(line):
            continue

        # Found a useTheme destructure with `colors`. Find the enclosing function scope.
        func_start = _find_enclosing_function_start(lines, i)
        if func_start is None:
            continue

        func_end = _find_matching_scope_end(lines, func_start)
        if func_end is None:
            func_end = len(lines) - 1

        # Mark all lines in this scope as safe (1-based)
        for line_num in range(func_start + 1, func_end + 2):  # +1 for 1-based, +1 for inclusive
            safe_lines.add(line_num)


def _find_enclosing_function_start(lines: List[str], target_line: int) -> Optional[int]:
    """Walk backward from target_line to find the enclosing function/component declaration."""
    func_decl = re.compile(
        r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+|"
        r"^(?:export\s+)?const\s+\w+\s*[:=]\s*(?:\([^)]*\)|[\w<>]+)\s*(?:=>|:.*=>)|"
        r"^(?:export\s+)?(?:default\s+)?function\s*\("
    )
    brace_depth = 0
    for j in range(target_line, -1, -1):
        stripped = lines[j].strip()
        # Count braces to track nesting
        brace_depth += stripped.count('}') - stripped.count('{')
        # When we reach a function declaration at the right nesting level
        if brace_depth <= 0 and func_decl.match(stripped):
            return j
    return None


def _find_matching_scope_end(lines: List[str], start_line: int) -> Optional[int]:
    """From a function start line, find the matching closing brace."""
    depth = 0
    found_opening = False
    for j in range(start_line, len(lines)):
        for ch in lines[j]:
            if ch == '{':
                depth += 1
                found_opening = True
            elif ch == '}':
                depth -= 1
                if found_opening and depth == 0:
                    return j
    return None


async def _run_theme_token_auto_remediation(triggered_by: str, dry_run: bool = False, max_fixes: int = 100) -> Dict[str, Any]:
    """Scan all frontend files and auto-fix hardcoded dark tokens."""
    db = await _db()
    app_root = Path(__file__).resolve().parents[3]
    files = _theme_guardrail_target_files()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = f"ttar_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    all_fixes: List[Dict[str, Any]] = []
    applied_count = 0
    skipped_count = 0
    file_results: List[Dict[str, Any]] = []

    for path in files:
        result = _scan_and_fix_file(path)
        rel_path = str(path.relative_to(app_root))
        result["file"] = rel_path

        if result.get("skipped"):
            skipped_count += 1
            file_results.append({"file": rel_path, "status": "skipped", "reason": result.get("reason", "")})
            continue

        file_fixes = result.get("fixes", [])
        if not file_fixes:
            continue

        safe_fixes = [f for f in file_fixes if f.get("safe")]

        if not dry_run and safe_fixes and applied_count < max_fixes:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                lines = text.splitlines()
                applied_lines = set()
                for fix in safe_fixes:
                    line_idx = fix["line"] - 1
                    if line_idx < 0 or line_idx >= len(lines):
                        continue
                    if line_idx in applied_lines:
                        continue
                    current_line = lines[line_idx]
                    if fix["token"] in current_line or fix["token"].lower() in current_line.lower():
                        fixed = _compute_token_fix(current_line, fix["token"], fix["replacement"])
                        if fixed and fixed != current_line:
                            lines[line_idx] = fixed
                            applied_lines.add(line_idx)
                            applied_count += 1
                            fix["applied"] = True

                if applied_lines:
                    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")

                file_results.append({
                    "file": rel_path,
                    "status": "fixed",
                    "total_found": len(file_fixes),
                    "safe_fixes": len(safe_fixes),
                    "applied": len(applied_lines),
                    "unsafe_skipped": len(file_fixes) - len(safe_fixes),
                })
            except Exception as exc:
                file_results.append({"file": rel_path, "status": "error", "error": str(exc)[:120]})
        else:
            file_results.append({
                "file": rel_path,
                "status": "dry_run" if dry_run else ("limit_reached" if applied_count >= max_fixes else "no_safe_fixes"),
                "total_found": len(file_fixes),
                "safe_fixes": len(safe_fixes),
                "applied": 0,
            })

        all_fixes.extend(file_fixes[:20])

    completed_at = datetime.now(timezone.utc).isoformat()
    run_doc = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "triggered_by": triggered_by,
        "dry_run": dry_run,
        "max_fixes": max_fixes,
        "total_files_scanned": len(files),
        "total_findings": len(all_fixes),
        "total_applied": applied_count,
        "total_skipped_files": skipped_count,
        "files_with_fixes": len([f for f in file_results if f.get("status") == "fixed"]),
        "file_results": file_results[:50],
        "sample_fixes": all_fixes[:30],
        "token_stats": {tok: sum(1 for f in all_fixes if f.get("token") == tok) for tok in _DARK_TOKEN_REPLACEMENTS},
    }
    await db.theme_token_remediation_runs.insert_one({**run_doc})

    total_docs = await db.theme_token_remediation_runs.count_documents({})
    if total_docs > 200:
        overflow = total_docs - 200
        old = await db.theme_token_remediation_runs.find({}, {"_id": 1}).sort("completed_at", 1).limit(overflow).to_list(overflow)
        if old:
            await db.theme_token_remediation_runs.delete_many({"_id": {"$in": [r["_id"] for r in old]}})

    return run_doc


class ThemeRemediationRunBody(BaseModel):
    dry_run: bool = True
    max_fixes: int = 50


@router.post("/theme-token-remediation/run")
async def run_theme_token_remediation(request: Request, body: ThemeRemediationRunBody):
    """Run theme token auto-remediation. dry_run=True previews fixes without applying."""
    await _require_admin(request)
    return await _run_theme_token_auto_remediation(
        triggered_by="admin_manual",
        dry_run=body.dry_run,
        max_fixes=body.max_fixes,
    )


@router.get("/theme-token-remediation/history")
async def get_theme_token_remediation_history(request: Request, limit: int = Query(default=10, ge=1, le=50)):
    """Get history of theme token remediation runs."""
    await _require_admin(request)
    db = await _db()
    rows = await db.theme_token_remediation_runs.find({}, {"_id": 0}).sort("completed_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "returned": len(rows)}


@router.get("/theme-token-remediation/latest")
async def get_latest_theme_token_remediation(request: Request):
    """Get the most recent theme token remediation run."""
    await _require_admin(request)
    db = await _db()
    doc = await db.theme_token_remediation_runs.find_one({}, {"_id": 0}, sort=[("completed_at", -1)])
    if not doc:
        return {"run_id": None, "status": "NOT_RUN"}
    return doc


@router.post("/responsive-guardrail/run")
async def run_responsive_guardrail(request: Request):
    """Run responsive guardrail scan to catch hidden/clipped tabs/chips before release."""
    actor = await _require_admin(request)
    triggered_by = str(getattr(actor, "email", "admin"))
    run = await _run_responsive_guardrail_scan(triggered_by=triggered_by)
    return run


@router.get("/responsive-guardrail/status")
async def responsive_guardrail_status(request: Request):
    """Latest responsive guardrail status."""
    await _require_admin(request)
    latest = await _latest_responsive_guardrail_run()
    if latest:
        return latest
    return {
        "run_id": None,
        "checked_at": None,
        "status": "NOT_RUN",
        "responsive_guardrail_score": 0,
        "files_scanned": 0,
        "issues_total": 0,
        "issues_by_severity": {"high": 0, "medium": 0, "low": 0},
        "findings": [],
        "triggered_by": None,
    }


@router.get("/responsive-guardrail/history")
async def responsive_guardrail_history(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    """Recent responsive guardrail runs."""
    await _require_admin(request)
    db = await _db()
    rows = await db.responsive_guardrail_runs.find({}, {"_id": 0}).sort("checked_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "returned": len(rows), "limit": limit}


@router.post("/theme-guardrail/run")
async def run_theme_guardrail(request: Request):
    actor = await _require_admin(request)
    triggered_by = str(getattr(actor, "email", "admin"))
    return await _run_theme_guardrail_scan(triggered_by=triggered_by)


@router.get("/theme-guardrail/status")
async def get_theme_guardrail_status(request: Request):
    await _require_admin(request)
    latest = await _latest_theme_guardrail_run()
    if latest:
        return latest
    return {
        "run_id": None,
        "checked_at": None,
        "status": "NOT_RUN",
        "theme_guardrail_score": 0,
        "files_scanned": 0,
        "issues_total": 0,
        "issues_by_severity": {"high": 0, "medium": 0, "low": 0},
        "findings": [],
        "triggered_by": None,
    }


@router.get("/theme-guardrail/history")
async def get_theme_guardrail_history(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    await _require_admin(request)
    db = await _db()
    rows = await db.theme_guardrail_runs.find({}, {"_id": 0}).sort("checked_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "returned": len(rows), "limit": limit}


@router.post("/theme-guardrail/nightly/run")
async def run_theme_drift_nightly(request: Request):
    actor = await _require_admin(request)
    triggered_by = str(getattr(actor, "email", "admin"))
    return await _run_theme_drift_nightly_detector(triggered_by=triggered_by)


@router.get("/theme-guardrail/nightly/status")
async def get_theme_drift_nightly_status(request: Request):
    await _require_admin(request)
    latest = await _latest_theme_drift_nightly_run()
    if latest:
        return latest
    return {
        "run_id": None,
        "checked_at": None,
        "triggered_by": None,
        "source_scan": None,
        "ticket_summary": {"candidates": 0, "created": 0, "updated": 0, "open_tickets": 0},
        "tickets": [],
    }


@router.get("/theme-guardrail/low-severity/suggestions")
async def get_theme_low_severity_suggestions(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    await _require_admin(request)
    payload = await _build_theme_low_severity_suggestions(limit=limit)
    return payload


@router.post("/theme-guardrail/low-severity/suggestions/{suggestion_id}/mark-done")
async def mark_theme_suggestion_done(suggestion_id: str, request: Request):
    actor = await _require_admin(request)
    note = ""
    try:
        body = await request.json()
        note = str((body or {}).get("note") or "").strip()
    except Exception:
        note = ""

    db = await _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.theme_guardrail_suggestion_tracker.update_one(
        {"suggestion_id": suggestion_id},
        {
            "$set": {
                "suggestion_id": suggestion_id,
                "status": "completed",
                "note": note,
                "updated_at": now_iso,
                "updated_by": str(getattr(actor, "email", "admin")),
            }
        },
        upsert=True,
    )
    return {
        "success": True,
        "suggestion_id": suggestion_id,
        "status": "completed",
        "updated_at": now_iso,
        "updated_by": str(getattr(actor, "email", "admin")),
    }


@router.post("/theme-guardrail/low-severity/suggestions/{suggestion_id}/reopen")
async def reopen_theme_suggestion(suggestion_id: str, request: Request):
    actor = await _require_admin(request)
    db = await _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.theme_guardrail_suggestion_tracker.update_one(
        {"suggestion_id": suggestion_id},
        {
            "$set": {
                "suggestion_id": suggestion_id,
                "status": "pending",
                "note": "",
                "updated_at": now_iso,
                "updated_by": str(getattr(actor, "email", "admin")),
            }
        },
        upsert=True,
    )
    return {
        "success": True,
        "suggestion_id": suggestion_id,
        "status": "pending",
        "updated_at": now_iso,
        "updated_by": str(getattr(actor, "email", "admin")),
    }


@router.post("/theme-guardrail/safe-autofix/run")
async def run_theme_safe_autofix(request: Request):
    actor = await _require_admin(request)
    triggered_by = str(getattr(actor, "email", "admin"))
    return await _run_theme_safe_autofix(triggered_by=triggered_by)


class TicketAssignBody(BaseModel):
    owner: str

class TicketStatusBody(BaseModel):
    status: str

class TicketSLABody(BaseModel):
    sla_deadline: str

class TicketBulkStatusBody(BaseModel):
    ticket_ids: List[str]
    status: str

class TicketNotesBody(BaseModel):
    notes: str


@router.get("/theme-drift-tickets/list")
async def list_theme_drift_tickets(
    request: Request,
    status_filter: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    owner: Optional[str] = Query(default=None),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    """List all theme drift tickets with optional filtering, sorting and pagination."""
    await _require_admin(request)
    db = await _db()

    query: Dict[str, Any] = {}
    if status_filter:
        valid_statuses = [s.strip().lower() for s in status_filter.split(",") if s.strip()]
        if valid_statuses:
            query["status"] = {"$in": valid_statuses}
    if severity:
        valid_severities = [s.strip().lower() for s in severity.split(",") if s.strip()]
        if valid_severities:
            query["severity"] = {"$in": valid_severities}
    if owner:
        query["owner"] = owner

    allowed_sort_fields = {"updated_at", "created_at", "severity", "occurrence_count", "sla_deadline", "status"}
    sort_field = sort_by if sort_by in allowed_sort_fields else "updated_at"
    direction = -1 if sort_dir == "desc" else 1

    total = await db.theme_guardrail_tickets.count_documents(query)
    rows = await db.theme_guardrail_tickets.find(query, {"_id": 0}).sort(sort_field, direction).skip(skip).limit(limit).to_list(limit)

    # Compute summary counts
    all_count = await db.theme_guardrail_tickets.count_documents({})
    open_count = await db.theme_guardrail_tickets.count_documents({"status": "open"})
    in_progress_count = await db.theme_guardrail_tickets.count_documents({"status": "in_progress"})
    resolved_count = await db.theme_guardrail_tickets.count_documents({"status": "resolved"})
    closed_count = await db.theme_guardrail_tickets.count_documents({"status": "closed"})

    # SLA breach detection
    now_iso = datetime.now(timezone.utc).isoformat()
    for row in rows:
        sla = row.get("sla_deadline")
        if sla and row.get("status") in ("open", "in_progress"):
            row["sla_breached"] = sla < now_iso
        else:
            row["sla_breached"] = False

    return {
        "tickets": rows,
        "total": total,
        "skip": skip,
        "limit": limit,
        "summary": {
            "all": all_count,
            "open": open_count,
            "in_progress": in_progress_count,
            "resolved": resolved_count,
            "closed": closed_count,
        },
    }


@router.patch("/theme-drift-tickets/{ticket_id}/assign")
async def assign_theme_drift_ticket(request: Request, ticket_id: str, body: TicketAssignBody):
    """Assign an owner to a drift ticket."""
    await _require_admin(request)
    db = await _db()
    owner_val = body.owner.strip()
    result = await db.theme_guardrail_tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {"owner": owner_val, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "owner": owner_val, "updated": True}


@router.patch("/theme-drift-tickets/{ticket_id}/status")
async def update_theme_drift_ticket_status(request: Request, ticket_id: str, body: TicketStatusBody):
    """Update the status of a drift ticket."""
    await _require_admin(request)
    db = await _db()
    new_status = body.status.strip().lower()
    valid = {"open", "in_progress", "resolved", "closed"}
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(valid))}")
    update_fields: Dict[str, Any] = {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if new_status == "resolved":
        update_fields["resolved_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.theme_guardrail_tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "status": new_status, "updated": True}


@router.patch("/theme-drift-tickets/{ticket_id}/sla")
async def update_theme_drift_ticket_sla(request: Request, ticket_id: str, body: TicketSLABody):
    """Set or update the SLA deadline for a drift ticket."""
    await _require_admin(request)
    db = await _db()
    sla_val = body.sla_deadline.strip()
    result = await db.theme_guardrail_tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {"sla_deadline": sla_val, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "sla_deadline": sla_val, "updated": True}


@router.patch("/theme-drift-tickets/{ticket_id}/notes")
async def update_theme_drift_ticket_notes(request: Request, ticket_id: str, body: TicketNotesBody):
    """Add or update resolution notes on a drift ticket."""
    await _require_admin(request)
    db = await _db()
    result = await db.theme_guardrail_tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {"notes": body.notes.strip(), "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return {"ticket_id": ticket_id, "updated": True}


@router.post("/theme-drift-tickets/bulk-status")
async def bulk_update_theme_drift_ticket_status(request: Request, body: TicketBulkStatusBody):
    """Bulk update status for multiple drift tickets."""
    await _require_admin(request)
    db = await _db()
    new_status = body.status.strip().lower()
    valid = {"open", "in_progress", "resolved", "closed"}
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status '{new_status}'.")
    update_fields: Dict[str, Any] = {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if new_status == "resolved":
        update_fields["resolved_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.theme_guardrail_tickets.update_many(
        {"ticket_id": {"$in": body.ticket_ids}},
        {"$set": update_fields},
    )
    return {"matched": result.matched_count, "modified": result.modified_count, "status": new_status}


