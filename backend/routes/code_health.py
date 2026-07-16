"""Code Health monitoring — runs ruff lint checks, auto-fixes, and alerts."""

import logging
import subprocess
import re
import shutil
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request

from routes.db import db, require_admin
from utils.email_service import ops_alert_template_enforcer

router = APIRouter(prefix="/admin/code-health")
logger = logging.getLogger("code-health")

RUFF_BIN = shutil.which("ruff") or "/root/.venv/bin/ruff"
BACKEND_DIR = "/app/backend"
ENTITLEMENT_DRIFT_COLLECTION = "entitlement_drift_audit_log"
ENTITLEMENT_DRIFT_MAX_HISTORY = 30

# Auto-fixable rule sets
SAFE_FIX_RULES = "F541,E401"
UNSAFE_FIX_RULES = "F841,F401"
ALL_FIX_RULES = f"{SAFE_FIX_RULES},{UNSAFE_FIX_RULES}"
CRITICAL_RULES = "F821,F811,F601,E722"


@ops_alert_template_enforcer("monitoring", "monitoring_code_health_alert")
async def _send_monitoring_ops_email(**kwargs):
    from utils.email_service import send_email

    return await send_email(**kwargs)


def _run_ruff(select: str = "") -> dict:
    """Run ruff check and parse output into structured results."""
    try:
        cmd = [RUFF_BIN, "check", ".", "--statistics"]
        if select:
            cmd.extend(["--select", select])
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BACKEND_DIR, timeout=30)
        raw = result.stdout + result.stderr

        categories = []
        total_issues = 0
        for line in raw.strip().split("\n"):
            m = re.match(r"\s*(\d+)\s+([A-Z]\d+)\s+(?:\[.\]\s+)?(.+)", line.strip())
            if m:
                count = int(m.group(1))
                code = m.group(2)
                name = m.group(3).strip()
                severity = "error" if code.startswith("F") else "warning"
                categories.append({"code": code, "name": name, "count": count, "severity": severity})
                total_issues += count

        found_match = re.search(r"Found (\d+) errors?", raw)
        if found_match:
            total_issues = int(found_match.group(1))

        categories.sort(key=lambda x: x["count"], reverse=True)
        return {
            "total_issues": total_issues,
            "categories": categories,
            "error_count": sum(c["count"] for c in categories if c["severity"] == "error"),
            "warning_count": sum(c["count"] for c in categories if c["severity"] == "warning"),
            "raw_output": raw[:2000],
            "status": "pass" if total_issues == 0 else "issues_found",
        }
    except subprocess.TimeoutExpired:
        return {"total_issues": -1, "categories": [], "error_count": 0, "warning_count": 0, "raw_output": "Timeout", "status": "timeout"}
    except Exception as e:
        return {"total_issues": -1, "categories": [], "error_count": 0, "warning_count": 0, "raw_output": str(e), "status": "error"}


def _run_ruff_critical() -> dict:
    """Run ruff for critical-only issues."""
    try:
        result = subprocess.run(
            [RUFF_BIN, "check", ".", "--select", CRITICAL_RULES, "--statistics"],
            capture_output=True, text=True, cwd=BACKEND_DIR, timeout=30,
        )
        raw = result.stdout + result.stderr
        found = re.search(r"Found (\d+) errors?", raw)
        count = int(found.group(1)) if found else 0
        return {"critical_issues": count, "passed": count == 0}
    except Exception:
        return {"critical_issues": -1, "passed": False}


def _run_ruff_fix(safe_only: bool = True) -> dict:
    """Run ruff --fix and return what was fixed."""
    try:
        rules = SAFE_FIX_RULES if safe_only else ALL_FIX_RULES
        cmd = [RUFF_BIN, "check", ".", "--select", rules, "--fix"]
        if not safe_only:
            cmd.append("--unsafe-fixes")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BACKEND_DIR, timeout=60)
        raw = result.stdout + result.stderr

        fixed_match = re.search(r"(\d+) fixed", raw)
        found_match = re.search(r"Found (\d+) errors?", raw)
        fixed_count = int(fixed_match.group(1)) if fixed_match else 0
        remaining = int(found_match.group(1)) if found_match else 0

        return {"fixed": fixed_count, "remaining": remaining, "raw": raw[:1000], "success": True}
    except Exception as e:
        return {"fixed": 0, "remaining": -1, "raw": str(e), "success": False}


def _run_bare_except_fix() -> int:
    """Fix bare except: → except Exception: using regex replacement."""
    import os
    fixed_count = 0
    for root, _, files in os.walk(BACKEND_DIR):
        if "node_modules" in root or ".git" in root:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                new_content = re.sub(r"(\s+)except:\s*$", r"\1except Exception:", content, flags=re.MULTILINE)
                if new_content != content:
                    with open(fpath, "w") as f:
                        f.write(new_content)
                    fixed_count += content.count("\nexcept:") - new_content.count("\nexcept:")
            except Exception:
                continue
    return max(fixed_count, 0)


def _build_report(full: dict, critical: dict, source: str = "manual") -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_issues": full["total_issues"],
        "error_count": full["error_count"],
        "warning_count": full["warning_count"],
        "critical_passed": critical["passed"],
        "critical_issues": critical["critical_issues"],
        "categories": full["categories"],
        "status": full["status"],
        "source": source,
    }


def _shape_entitlement_drift_history_row(row: dict | None) -> dict:
    payload = row or {}
    preview_source = "new_findings" if payload.get("new_findings") else "findings"
    preview_source_items = payload.get(preview_source) or []
    preview_findings = []
    for item in preview_source_items[:3]:
        preview_findings.append(
            {
                "path": item.get("path"),
                "line": item.get("line"),
                "pattern": item.get("pattern"),
                "severity": item.get("severity"),
                "snippet": item.get("snippet"),
            }
        )

    return {
        "generated_at": payload.get("generated_at"),
        "trigger": payload.get("trigger") or "unknown",
        "status": payload.get("status") or "unknown",
        "severity": payload.get("severity") or "warning",
        "title": payload.get("title") or "Entitlement drift audit",
        "summary": payload.get("summary") or "",
        "baseline_established": bool(payload.get("baseline_established")),
        "raw_scan_status": payload.get("raw_scan_status") or "unknown",
        "files_scanned": int(payload.get("files_scanned") or 0),
        "finding_count": int(payload.get("finding_count") or 0),
        "high_risk_count": int(payload.get("high_risk_count") or 0),
        "medium_risk_count": int(payload.get("medium_risk_count") or 0),
        "new_finding_count": int(payload.get("new_finding_count") or 0),
        "new_high_risk_count": int(payload.get("new_high_risk_count") or 0),
        "new_medium_risk_count": int(payload.get("new_medium_risk_count") or 0),
        "baseline_previous_finding_count": int(payload.get("baseline_previous_finding_count") or 0),
        "alert_dispatched": bool(payload.get("alert_dispatched")),
        "preview_source": preview_source,
        "preview_findings": preview_findings,
    }


def _build_entitlement_drift_history_payload(rows: list[dict]) -> dict:
    history = [_shape_entitlement_drift_history_row(row) for row in rows]
    breakdown = {
        "pass": sum(1 for row in history if row.get("status") == "pass"),
        "warning": sum(1 for row in history if row.get("status") == "warning"),
        "fail": sum(1 for row in history if row.get("status") == "fail"),
    }
    attention_count = sum(
        1 for row in history if row.get("new_finding_count", 0) > 0 or row.get("status") == "fail"
    )
    return {
        "latest": history[0] if history else None,
        "history": history,
        "total": len(history),
        "status_breakdown": breakdown,
        "attention_count": attention_count,
    }


DEPLOY_GATE_RULES = "F821,F811,F601"


def _run_deploy_gate() -> dict:
    """Run deployment gate — checks for blocking critical issues only."""
    try:
        result = subprocess.run(
            [RUFF_BIN, "check", ".", "--select", DEPLOY_GATE_RULES, "--output-format", "json"],
            capture_output=True, text=True, cwd=BACKEND_DIR, timeout=30,
        )
        import json as _json
        issues = _json.loads(result.stdout) if result.stdout.strip() else []
        blockers = []
        for issue in issues:
            blockers.append({
                "file": issue.get("filename", "").replace(BACKEND_DIR + "/", ""),
                "line": issue.get("location", {}).get("row", 0),
                "code": issue.get("code", ""),
                "message": issue.get("message", ""),
            })
        return {
            "passed": len(blockers) == 0,
            "blocker_count": len(blockers),
            "blockers": blockers[:50],
            "rules_checked": DEPLOY_GATE_RULES,
        }
    except Exception as e:
        return {"passed": False, "blocker_count": -1, "blockers": [], "rules_checked": DEPLOY_GATE_RULES, "error": str(e)}


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/deploy-gate")
async def deploy_gate_check(request: Request):
    """Check if code passes the deployment gate (no F821/F811/F601 issues)."""
    await require_admin(request)
    gate = _run_deploy_gate()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": gate["passed"],
        "blocker_count": gate["blocker_count"],
        "blockers": gate["blockers"],
        "rules_checked": gate["rules_checked"],
    }
    await db.deploy_gate_checks.insert_one({**record})
    record.pop("_id", None)
    return record


@router.get("/deploy-gate/history")
async def deploy_gate_history(request: Request, limit: int = 10):
    """Get history of deployment gate checks."""
    await require_admin(request)
    history = (
        await db.deploy_gate_checks.find({}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(limit)
    )
    return {"history": history, "total": len(history)}


@router.get("/check")
async def run_code_health_check(request: Request):
    """Run a full ruff lint check and return results."""
    await require_admin(request)
    full = _run_ruff()
    critical = _run_ruff_critical()
    report = _build_report(full, critical, "manual")
    await db.code_health_reports.insert_one({**report})
    report.pop("_id", None)
    return report


@router.post("/auto-fix")
async def run_auto_fix(request: Request):
    """Run auto-fix for all fixable issues and return before/after diff."""
    await require_admin(request)

    # Before state
    before = _run_ruff()
    before_critical = _run_ruff_critical()

    # Run fixes
    safe_result = _run_ruff_fix(safe_only=True)
    unsafe_result = _run_ruff_fix(safe_only=False)
    bare_except_fixed = _run_bare_except_fix()

    # After state
    after = _run_ruff()
    after_critical = _run_ruff_critical()

    total_fixed = safe_result["fixed"] + unsafe_result["fixed"] + bare_except_fixed
    issues_reduced = max(before["total_issues"] - after["total_issues"], 0)

    fix_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
        "before_issues": before["total_issues"],
        "after_issues": after["total_issues"],
        "issues_reduced": issues_reduced,
        "safe_fixed": safe_result["fixed"],
        "unsafe_fixed": unsafe_result["fixed"],
        "bare_except_fixed": bare_except_fixed,
        "total_fixed": total_fixed,
        "critical_before": before_critical["critical_issues"],
        "critical_after": after_critical["critical_issues"],
        "categories_before": before["categories"],
        "categories_after": after["categories"],
    }
    await db.code_health_fixes.insert_one({**fix_record})
    fix_record.pop("_id", None)

    # Also store post-fix report
    report = _build_report(after, after_critical, "auto-fix")
    await db.code_health_reports.insert_one({**report})

    return fix_record


@router.get("/fix-history")
async def fix_history(request: Request, limit: int = 20):
    """Get history of auto-fix runs."""
    await require_admin(request)
    history = (
        await db.code_health_fixes.find({}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(limit)
    )
    return {"history": history, "total": len(history)}


@router.get("/trends")
async def code_health_trends(request: Request, days: int = 30):
    """Get code health trend data over time."""
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    reports = (
        await db.code_health_reports.find(
            {"timestamp": {"$gte": cutoff}},
            {"_id": 0, "timestamp": 1, "total_issues": 1, "error_count": 1, "warning_count": 1, "critical_passed": 1, "source": 1},
        )
        .sort("timestamp", 1)
        .to_list(100)
    )
    return {"trends": reports, "period_days": days, "total_reports": len(reports)}


@router.get("/latest")
async def code_health_latest(request: Request):
    """Get the most recent code health report without running a new check."""
    await require_admin(request)
    latest = await db.code_health_reports.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    if not latest:
        return {"message": "No reports yet. Run a check first.", "has_report": False}
    return {**latest, "has_report": True}


@router.get("/widget")
async def code_health_widget(request: Request):
    """Lightweight combined status for the dashboard widget."""
    await require_admin(request)
    ruff_latest = await db.code_health_reports.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    js_latest = await db.code_health_scans.find_one({}, {"_id": 0, "timestamp": 1, "total_issues": 1, "critical": 1, "medium": 1, "low": 1, "files_scanned": 1, "source": 1}, sort=[("timestamp", -1)])
    gate_latest = await db.deploy_gate_checks.find_one({}, {"_id": 0, "passed": 1, "blocker_count": 1, "timestamp": 1}, sort=[("timestamp", -1)])
    theme_stats = await _v2_theme_audit_snapshot()
    return {
        "ruff": {
            "has_report": bool(ruff_latest),
            "total_issues": ruff_latest.get("total_issues", 0) if ruff_latest else 0,
            "error_count": ruff_latest.get("error_count", 0) if ruff_latest else 0,
            "warning_count": ruff_latest.get("warning_count", 0) if ruff_latest else 0,
            "critical_passed": ruff_latest.get("critical_passed", True) if ruff_latest else True,
            "timestamp": ruff_latest.get("timestamp") if ruff_latest else None,
        },
        "js_scanner": {
            "has_report": bool(js_latest),
            "total_issues": js_latest.get("total_issues", 0) if js_latest else 0,
            "critical": js_latest.get("critical", 0) if js_latest else 0,
            "files_scanned": js_latest.get("files_scanned", 0) if js_latest else 0,
            "timestamp": js_latest.get("timestamp") if js_latest else None,
        },
        "deploy_gate": {
            "passed": gate_latest.get("passed", True) if gate_latest else True,
            "blocker_count": gate_latest.get("blocker_count", 0) if gate_latest else 0,
            "timestamp": gate_latest.get("timestamp") if gate_latest else None,
        },
        "v2_theme_audit": theme_stats,
    }


@router.get("/entitlement-drift/history")
async def entitlement_drift_history(request: Request, limit: int = 7):
    """Recent entitlement drift audit history for the admin console."""
    await require_admin(request)
    safe_limit = max(1, min(int(limit or 7), ENTITLEMENT_DRIFT_MAX_HISTORY))
    rows = (
        await db[ENTITLEMENT_DRIFT_COLLECTION].find({}, {"_id": 0})
        .sort("generated_at", -1)
        .to_list(safe_limit)
    )
    return _build_entitlement_drift_history_payload(rows)


async def _v2_theme_audit_snapshot() -> dict:
    """Run the V2 theme audit script and return a summary.

    Cached for 5 min so callers on the admin dashboard don't pay the full scan
    cost on every page load.
    """
    import subprocess
    import time
    now = time.time()
    cached = getattr(_v2_theme_audit_snapshot, "_cache", None)
    if cached and (now - cached[0]) < 300:
        return cached[1]
    try:
        res = subprocess.run(
            ["python3", "/app/scripts/audit_v2_theme.py"],
            capture_output=True, text=True, timeout=20,
        )
        import json as _json
        raw = _json.loads(open("/tmp/v2_theme_audit_v2.json").read())
        out = {
            "files_scanned": raw.get("files_scanned", 0),
            "files_with_violations": raw.get("files_with_violations", 0),
            "files_theme_compliant": raw.get("files_theme_compliant", 0),
            "violations_by_category": raw.get("violations_by_category", {}),
            "files_by_priority": raw.get("files_by_priority", {}),
            "p0_violations": raw.get("files_by_priority", {}).get("P0", 0),
            "status": "pass" if raw.get("files_by_priority", {}).get("P0", 0) == 0 else "fail",
            "last_run_ok": res.returncode == 0,
        }
    except Exception as e:
        out = {"error": str(e), "status": "unknown", "p0_violations": -1}
    _v2_theme_audit_snapshot._cache = (now, out)  # type: ignore[attr-defined]
    return out


@router.get("/theme-audit")
async def code_health_theme_audit(request: Request):
    """Expose the V2 theme audit snapshot for the AdminHealthDigestWidget."""
    await require_admin(request)
    return await _v2_theme_audit_snapshot()


# ─── Scheduled Job + Email Alert ─────────────────────────────────────────────

async def _send_code_health_email(subject: str, html_body: str, before: dict = None, after: dict = None, fix_result: dict = None, critical: dict = None, gate: dict = None):
    """Send code health alert email to all admin users via V7 pipeline."""
    try:
        from utils.email_service import is_email_configured
        if not is_email_configured():
            logger.warning("Email not configured, skipping code health alert")
            return

        # V7 compliant: use registered template
        from utils.email_templates import build_code_health_alert_email
        score_before = (before or {}).get("total_issues", 0)
        score_after = (after or {}).get("total_issues", 0)
        crit = critical or {"passed": True, "critical_issues": 0}
        gate_info = gate or {}
        tpl = build_code_health_alert_email(
            score_before=score_before,
            score_after=score_after,
            critical_passed=crit.get("passed", True),
            critical_issues=crit.get("critical_issues", 0),
            fixes_applied=(fix_result or {}).get("total_fixed", 0),
            gate_status="PASSED" if gate_info.get("passed", True) else "BLOCKED",
        )

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).to_list(20)
        for admin in admins:
            if admin.get("email"):
                await _send_monitoring_ops_email(
                    recipient_email=admin["email"],
                    subject=tpl.subject,
                    content=tpl.html,
                    template_key="code_health_alert",
                    skip_branding=True,
                )
        logger.info(f"Code health alert sent to {len(admins)} admin(s): {tpl.subject}")
    except Exception as e:
        logger.error(f"Code health alert email failed: {e}")


def _build_alert_html(before: dict, after: dict, fix_result: dict, critical: dict, gate: dict | None = None) -> str:
    """Build HTML email for code health alert."""
    critical_status = "PASSED" if critical["passed"] else f"FAILED ({critical['critical_issues']} issues)"
    "#10B981" if critical["passed"] else "#EF4444"

    gate_passed = gate["passed"] if gate else True
    gate_color = "#10B981" if gate_passed else "#EF4444"
    gate_status = "PASSED" if gate_passed else f"BLOCKED ({gate.get('blocker_count', 0)} issues)"

    rows = ""
    for cat in after.get("categories", [])[:10]:
        sev_color = "#EF4444" if cat["severity"] == "error" else "#F59E0B"
        rows += f"""<tr>
            <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#06B6D4;font-family:monospace">{cat["code"]}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#9CA3AF">{cat["name"]}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #1F2937;text-align:center">
                <span style="background:{sev_color}22;color:{sev_color};padding:2px 8px;border-radius:4px;font-size:11px">{cat["severity"]}</span>
            </td>
            <td style="padding:6px 12px;border-bottom:1px solid #1F2937;text-align:right;color:#F9FAFB;font-weight:700">{cat["count"]}</td>
        </tr>"""

    blocker_rows = ""
    if gate and not gate_passed:
        for b in gate.get("blockers", [])[:10]:
            blocker_rows += f"""<tr>
                <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#EF4444;font-family:monospace;font-weight:700">{b.get("code","")}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#06B6D4;font-size:12px">{b.get("file","")}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#6B7280;text-align:center">{b.get("line","")}</td>
                <td style="padding:6px 12px;border-bottom:1px solid #1F2937;color:#9CA3AF;font-size:12px">{b.get("message","")}</td>
            </tr>"""

    total_fixed = fix_result.get("total_fixed", 0)
    before_count = before.get("total_issues", 0)
    after_count = after.get("total_issues", 0)

    blocker_section = ""
    if gate and not gate_passed:
        blocker_section = f"""
            <div style="margin-top:16px">
                <h2 style="color:#EF4444;font-size:16px;margin:0 0 8px">Deployment Blockers</h2>
                <table style="width:100%;background:#111827;border:1px solid #3D1B22;border-radius:10px;border-collapse:collapse;overflow:hidden">
                    <thead>
                        <tr style="background:#0B0F1A">
                            <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Code</th>
                            <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">File</th>
                            <th style="padding:8px 12px;text-align:center;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Line</th>
                            <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Message</th>
                        </tr>
                    </thead>
                    <tbody>{blocker_rows}</tbody>
                </table>
            </div>"""

    return f"""
    <div style="background:#0B0F1A;padding:32px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
        <div style="max-width:600px;margin:0 auto">
            <div style="text-align:center;margin-bottom:24px">
                <h1 style="color:#F9FAFB;font-size:20px;margin:0">Code Health Report</h1>
                <p style="color:#6B7280;font-size:13px;margin:4px 0 0">Daily automated check — {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}</p>
            </div>

            <div style="background:#111827;border:1px solid #3D1B22;border-radius:10px;padding:16px;margin-bottom:16px;text-align:center">
                <p style="color:#EF4444;font-size:16px;font-weight:700;margin:0">Critical Checks: {critical_status}</p>
            </div>

            <div style="background:#111827;border:1px solid {'#1E3530' if gate_passed else '#3D1B22'};border-radius:12px;padding:16px;margin-bottom:16px;text-align:center">
                <p style="color:{gate_color};font-size:16px;font-weight:700;margin:0">Deploy Gate: {gate_status}</p>
            </div>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px">
                <tr>
                    <td width="32%" style="background:#111827;border:1px solid #1F2937;border-radius:10px;padding:14px;text-align:center">
                        <p style="color:#6B7280;font-size:11px;margin:0 0 4px;text-transform:uppercase">Before</p>
                        <p style="color:#F9FAFB;font-size:22px;font-weight:800;margin:0">{before_count}</p>
                    </td>
                    <td width="2%"></td>
                    <td width="32%" style="background:#111827;border:1px solid #1F2937;border-radius:10px;padding:14px;text-align:center">
                        <p style="color:#6B7280;font-size:11px;margin:0 0 4px;text-transform:uppercase">Fixed</p>
                        <p style="color:#10B981;font-size:22px;font-weight:800;margin:0">{total_fixed}</p>
                    </td>
                    <td width="2%"></td>
                    <td width="32%" style="background:#111827;border:1px solid #1F2937;border-radius:10px;padding:14px;text-align:center">
                        <p style="color:#6B7280;font-size:11px;margin:0 0 4px;text-transform:uppercase">After</p>
                        <p style="color:#3B82F6;font-size:22px;font-weight:800;margin:0">{after_count}</p>
                    </td>
                </tr>
            </table>

            <table style="width:100%;background:#111827;border:1px solid #1F2937;border-radius:10px;border-collapse:collapse;overflow:hidden">
                <thead>
                    <tr style="background:#0B0F1A">
                        <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Code</th>
                        <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Description</th>
                        <th style="padding:8px 12px;text-align:center;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Severity</th>
                        <th style="padding:8px 12px;text-align:right;color:#6B7280;font-size:10px;text-transform:uppercase;border-bottom:1px solid #1F2937">Count</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>

            {blocker_section}

            <p style="color:#4B5563;font-size:11px;text-align:center;margin-top:20px">
                Auto-generated by RealAICoach Code Health Monitor
            </p>
        </div>
    </div>"""


async def scheduled_code_health_check():
    """Daily scheduled: check → auto-fix → re-check → deploy gate → email alert."""
    logger.info("Starting scheduled code health check...")

    # Step 1: Initial check
    before = _run_ruff()
    before_critical = _run_ruff_critical()
    logger.info(f"Before fix: {before['total_issues']} issues, critical passed: {before_critical['passed']}")

    # Step 2: Auto-fix
    safe_result = _run_ruff_fix(safe_only=True)
    unsafe_result = _run_ruff_fix(safe_only=False)
    bare_except_fixed = _run_bare_except_fix()
    total_fixed = safe_result["fixed"] + unsafe_result["fixed"] + bare_except_fixed
    logger.info(f"Auto-fix: {total_fixed} issues fixed (safe={safe_result['fixed']}, unsafe={unsafe_result['fixed']}, bare_except={bare_except_fixed})")

    # Step 3: Re-check after fix
    after = _run_ruff()
    after_critical = _run_ruff_critical()
    logger.info(f"After fix: {after['total_issues']} issues, critical passed: {after_critical['passed']}")

    # Step 4: Store report
    report = _build_report(after, after_critical, "scheduled")
    await db.code_health_reports.insert_one({**report})

    # Step 5: Store fix record
    if total_fixed > 0:
        fix_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "scheduled",
            "before_issues": before["total_issues"],
            "after_issues": after["total_issues"],
            "issues_reduced": max(before["total_issues"] - after["total_issues"], 0),
            "safe_fixed": safe_result["fixed"],
            "unsafe_fixed": unsafe_result["fixed"],
            "bare_except_fixed": bare_except_fixed,
            "total_fixed": total_fixed,
            "critical_before": before_critical["critical_issues"],
            "critical_after": after_critical["critical_issues"],
        }
        await db.code_health_fixes.insert_one({**fix_record})

    # Step 6: Deploy gate check
    gate = _run_deploy_gate()
    gate_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": gate["passed"],
        "blocker_count": gate["blocker_count"],
        "blockers": gate["blockers"],
        "rules_checked": gate["rules_checked"],
        "source": "scheduled",
    }
    await db.deploy_gate_checks.insert_one({**gate_record})
    blocker_count = gate["blocker_count"]
    gate_msg = "PASSED" if gate["passed"] else f"BLOCKED ({blocker_count} issues)"
    logger.info(f"Deploy gate: {gate_msg}")

    # Step 7: Send email alert (with deploy gate status)
    html = _build_alert_html(before, after, {"total_fixed": total_fixed}, after_critical, gate)

    if not gate["passed"]:
        subject = f"[DEPLOY BLOCKED] {gate['blocker_count']} Critical Blocker(s) Found — Deployment Unsafe"
    elif not after_critical["passed"]:
        subject = f"[CRITICAL] Code Health Alert — {after_critical['critical_issues']} Critical Issues"
    elif total_fixed > 0:
        subject = f"Code Health: {total_fixed} Issues Auto-Fixed — Deploy Gate PASSED"
    else:
        subject = "Code Health: All Clear — Deploy Gate PASSED"

    await _send_code_health_email(subject, html)
    logger.info("Scheduled code health check complete")



async def auto_fix_check(
    source: str = "admin_routes_sentinel",
    context: dict | None = None,
) -> dict:
    """Lightweight auto-remediation hook.

    Runs the core check → auto-fix → re-check flow used by the daily
    scheduled job, but WITHOUT the email/deploy-gate noise. Used by
    ``services.admin_routes_sentinel`` to trigger an immediate repair
    attempt the moment any admin route flips to ``unhealthy`` so the
    team doesn't have to wait for the next 24h cycle.

    Writes a row to ``db.code_health_fixes`` tagged with ``source`` +
    ``context`` so we can trace which sentinel event each fix cycle was
    dispatched for. Returns a JSON-serializable summary.
    """
    ctx = context or {}
    logger.info(f"[auto-fix-hook] triggered source={source} context={ctx}")

    before = _run_ruff()
    before_critical = _run_ruff_critical()

    safe_result = _run_ruff_fix(safe_only=True)
    unsafe_result = _run_ruff_fix(safe_only=False)
    bare_except_fixed = _run_bare_except_fix()
    total_fixed = (
        safe_result["fixed"] + unsafe_result["fixed"] + bare_except_fixed
    )

    after = _run_ruff()
    after_critical = _run_ruff_critical()

    fix_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "context": ctx,
        "before_issues": before["total_issues"],
        "after_issues": after["total_issues"],
        "issues_reduced": max(
            before["total_issues"] - after["total_issues"], 0
        ),
        "safe_fixed": safe_result["fixed"],
        "unsafe_fixed": unsafe_result["fixed"],
        "bare_except_fixed": bare_except_fixed,
        "total_fixed": total_fixed,
        "critical_before": before_critical["critical_issues"],
        "critical_after": after_critical["critical_issues"],
    }
    try:
        await db.code_health_fixes.insert_one({**fix_record})
    except Exception as exc:
        logger.warning(f"[auto-fix-hook] fix record persist failed: {exc}")

    logger.info(
        f"[auto-fix-hook] done source={source} "
        f"before={before['total_issues']} after={after['total_issues']} "
        f"fixed={total_fixed} critical_after={after_critical['critical_issues']}"
    )
    return {
        "source": source,
        "context": ctx,
        "before_issues": fix_record["before_issues"],
        "after_issues": fix_record["after_issues"],
        "issues_reduced": fix_record["issues_reduced"],
        "total_fixed": fix_record["total_fixed"],
        "critical_before": fix_record["critical_before"],
        "critical_after": fix_record["critical_after"],
        "timestamp": fix_record["timestamp"],
    }
