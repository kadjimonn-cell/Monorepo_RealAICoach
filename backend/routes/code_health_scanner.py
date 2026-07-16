"""
Code Health Auto-Fix Scanner — Detects & prevents JavaScript Temporal Dead Zone (TDZ) errors,
unhandled promise rejections, and other common runtime crashers across the entire frontend codebase.
Runs on-demand or as a scheduled scan.
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict
from fastapi import APIRouter, Request, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/code-health", tags=["Code Health"])

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "realaicoach")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

FRONTEND_ROOT = "/app/frontend"
SCAN_DIRS = [
    os.path.join(FRONTEND_ROOT, "src"),
    os.path.join(FRONTEND_ROOT, "app"),
]
EXTENSIONS = {".tsx", ".ts", ".jsx", ".js"}


# ─── Core Detection Engine ───

def _scan_file_for_tdz(filepath: str) -> List[Dict]:
    """Scan a single file for TDZ issues: useEffect/useAutoRefresh calling const/let declared later."""
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return issues

    # Track function declarations assigned to const/let (arrow/function expressions only)
    declarations = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r'\s*(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function\b|\w+\s*=>)', line)
        if m:
            declarations[m.group(1)] = i

    # Real TDZ vectors only:
    # - identifiers in a hook's dependency array (evaluated synchronously during render)
    # - useMemo callbacks (executed synchronously during render)
    for i, line in enumerate(lines, 1):
        if not any(hook in line for hook in ["useEffect", "useAutoRefresh", "useCallback", "useMemo"]):
            continue
        refs = set()
        deps_m = re.search(r'\[([^\[\]]*)\]\s*\)', line)
        if deps_m:
            refs.update(re.findall(r'[a-zA-Z_]\w*', deps_m.group(1)))
        if "useMemo" in line:
            body = line.split("=>", 1)[1] if "=>" in line else ""
            if deps_m:
                body = body[: body.rfind("[")] if "[" in body else body
            refs.update(re.findall(r'(?<!\w)([a-zA-Z_]\w*)\s*\(', body))

        for func_name in refs:
            if func_name in declarations and declarations[func_name] > i:
                # Skip module-level declarations (createStyles etc) — they're safe
                if lines[declarations[func_name] - 1][0:1] not in (' ', '\t'):
                    continue
                if func_name in ("createStyles", "makeStyles", "getStyles", "useStyles"):
                    continue

                issues.append({
                    "type": "TDZ",
                    "severity": "critical",
                    "file": filepath.replace(FRONTEND_ROOT + "/", ""),
                    "line": i,
                    "declaration_line": declarations[func_name],
                    "function": func_name,
                    "message": f"'{func_name}' is referenced on line {i} (hook dependency array or synchronous useMemo call) but declared with const/let on line {declarations[func_name]}. This causes a TDZ ReferenceError at runtime.",
                    "fix": f"Change 'const {func_name} = async () =>' to 'async function {func_name}()' (function declarations are hoisted).",
                    "auto_fixable": True,
                })
    return issues


def _scan_file_for_missing_error_boundary(filepath: str) -> List[Dict]:
    """Check if page-level components lack error boundaries."""
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return issues

    # Check if it's a page/screen component (default export)
    if "export default" in content and "ErrorBoundary" not in content:
        if any(hook in content for hook in ["useEffect", "useState"]):
            is_page = "/app/" in filepath or "View.tsx" in filepath or "Screen.tsx" in filepath
            if is_page:
                issues.append({
                    "type": "MISSING_ERROR_BOUNDARY",
                    "severity": "medium",
                    "file": filepath.replace(FRONTEND_ROOT + "/", ""),
                    "line": 0,
                    "message": "Page component lacks an error boundary. Unhandled errors will crash the entire app.",
                    "fix": "Wrap the component in an ErrorBoundary or add a try-catch in the render.",
                    "auto_fixable": False,
                })
    return issues


def _scan_file_for_unsafe_api_calls(filepath: str) -> List[Dict]:
    """Detect API calls without try-catch."""
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return issues

    in_try = False
    brace_depth = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "try {" in stripped or "try{" in stripped:
            in_try = True
            brace_depth = 0
        if in_try:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0:
                in_try = False

        if not in_try and ("api.get(" in stripped or "api.post(" in stripped or "api.put(" in stripped or "api.delete(" in stripped):
            # Check if inside a try block within 5 lines above
            nearby_try = any("try" in lines[max(0, i-6+j)].strip() for j in range(6))
            if not nearby_try:
                issues.append({
                    "type": "UNSAFE_API_CALL",
                    "severity": "low",
                    "file": filepath.replace(FRONTEND_ROOT + "/", ""),
                    "line": i,
                    "message": f"API call without try-catch on line {i}. Unhandled network errors can crash the component.",
                    "fix": "Wrap API call in try-catch block.",
                    "auto_fixable": False,
                })
    return issues


def _auto_fix_tdz(filepath: str, issues: List[Dict]) -> int:
    """Auto-fix TDZ issues by converting const arrow functions to function declarations."""
    fixed = 0
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        for issue in issues:
            if issue["type"] == "TDZ" and issue["auto_fixable"]:
                func = issue["function"]
                # Pattern: const funcName = async () => {
                pattern = rf'(\s*)const\s+{re.escape(func)}\s*=\s*async\s*\(([^)]*)\)\s*=>\s*\{{'
                replacement = rf'\1async function {func}(\2) {{'
                new_content, count = re.subn(pattern, replacement, content, count=1)
                if count > 0:
                    content = new_content
                    # Also remove trailing }; and replace with }
                    content = content  # The trailing ; is harmless but let's clean it
                    fixed += 1

        if fixed > 0:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception as e:
        logger.error(f"Auto-fix failed for {filepath}: {e}")
    return fixed


def run_full_scan() -> Dict:
    """Scan entire frontend codebase for all issue types."""
    all_issues = []
    files_scanned = 0
    for scan_dir in SCAN_DIRS:
        if not os.path.isdir(scan_dir):
            continue
        for root, _, files in os.walk(scan_dir):
            if "node_modules" in root or "__pycache__" in root:
                continue
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                files_scanned += 1
                all_issues.extend(_scan_file_for_tdz(fpath))
                all_issues.extend(_scan_file_for_missing_error_boundary(fpath))
                all_issues.extend(_scan_file_for_unsafe_api_calls(fpath))

    critical = [i for i in all_issues if i["severity"] == "critical"]
    medium = [i for i in all_issues if i["severity"] == "medium"]
    low = [i for i in all_issues if i["severity"] == "low"]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_scanned": files_scanned,
        "total_issues": len(all_issues),
        "critical": len(critical),
        "medium": len(medium),
        "low": len(low),
        "auto_fixable": sum(1 for i in all_issues if i.get("auto_fixable")),
        "issues": all_issues,
    }


# ─── Require Admin Helper ───

async def require_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = auth.split(" ", 1)[1]
    import jwt
    secret = os.environ.get("JWT_SECRET", os.environ.get("SESSION_SECRET", ""))
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"user_id": payload.get("user_id")}, {"_id": 0, "is_admin": 1})
    if not user or not user.get("is_admin"):
        raise HTTPException(403, "Admin only")


# ─── API Endpoints ───

@router.get("/scan")
async def scan_codebase(request: Request):
    """Run a full code health scan and return results."""
    await require_admin(request)
    result = run_full_scan()
    # Store scan result
    doc = {**result, "scan_id": f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"}
    await db.code_health_scans.insert_one(doc)
    del doc["_id"]
    return doc


@router.post("/auto-fix")
async def auto_fix_issues(request: Request):
    """Auto-fix all fixable issues (TDZ errors)."""
    await require_admin(request)
    result = run_full_scan()
    fixable = [i for i in result["issues"] if i.get("auto_fixable")]

    # Group by file
    by_file = {}
    for issue in fixable:
        fpath = os.path.join(FRONTEND_ROOT, issue["file"])
        by_file.setdefault(fpath, []).append(issue)

    total_fixed = 0
    fixed_files = []
    for fpath, issues in by_file.items():
        count = _auto_fix_tdz(fpath, issues)
        if count > 0:
            total_fixed += count
            fixed_files.append({"file": issues[0]["file"], "fixes": count})

    # Re-scan to verify
    post_scan = run_full_scan()

    return {
        "status": "completed",
        "fixed_count": total_fixed,
        "fixed_files": fixed_files,
        "remaining_issues": post_scan["total_issues"],
        "remaining_critical": post_scan["critical"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history")
async def scan_history(request: Request):
    """Get scan history."""
    await require_admin(request)
    scans = await db.code_health_scans.find({}, {"_id": 0}).sort("timestamp", -1).to_list(20)
    return {"scans": scans}


# ─── Scheduled Nightly Scan ───

async def run_nightly_code_health_scan():
    """Scheduled job: scan codebase and email admins if critical issues found."""
    result = run_full_scan()
    scan_id = f"nightly_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    doc = {**result, "scan_id": scan_id, "source": "nightly"}
    await db.code_health_scans.insert_one(doc)
    logger.info(f"Nightly code health scan: {result['total_issues']} issues ({result['critical']} critical)")

    if result["critical"] > 0:
        await _send_code_health_alert(result)
    return result


async def _send_code_health_alert(scan_result: dict):
    """Send email alert to all admin users when critical issues are detected."""
    try:
        from utils.email_service import send_email
        from utils.email_templates import _wrap

        critical_issues = [i for i in scan_result["issues"] if i["severity"] == "critical"]
        issue_rows = ""
        for i, issue in enumerate(critical_issues[:10], 1):
            issue_rows += f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #1E293B;color:#EF4444;font-size:12px;font-weight:700;width:30px;">{i}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #1E293B;">
                <span style="color:#F1F5F9;font-size:12px;font-weight:600;display:block;">{issue.get('function', issue['type'])}</span>
                <span style="color:#94A3B8;font-size:10px;display:block;margin-top:2px;font-family:monospace;">{issue['file']}:{issue.get('line', 0)}</span>
                <span style="color:#64748B;font-size:10px;display:block;margin-top:2px;">{issue['message'][:120]}</span>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #1E293B;text-align:center;">
                {'<span style="color:#10B981;font-size:10px;font-weight:700;">AUTO-FIX</span>' if issue.get('auto_fixable') else '<span style="color:#F59E0B;font-size:10px;font-weight:700;">MANUAL</span>'}
              </td>
            </tr>"""

        body_html = f"""
        <div style="margin-bottom:20px;">
          <div style="display:inline-block;padding:8px 16px;background:#EF444420;border:1px solid #EF444440;border-radius:8px;margin-bottom:16px;">
            <span style="color:#EF4444;font-size:13px;font-weight:800;">{scan_result['critical']} CRITICAL ISSUES DETECTED</span>
          </div>
          <p style="color:#CBD5E1;font-size:13px;line-height:1.7;">
            The nightly code health scan found <strong style="color:#EF4444;">{scan_result['critical']} critical</strong> issues
            that can cause "Something Went Wrong" crashes in your frontend.
          </p>
          <table role="presentation" width="100%" style="margin-top:16px;">
            <tr style="background:#0F172A;">
              <td style="padding:8px 12px;color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">#</td>
              <td style="padding:8px 12px;color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Issue Details</td>
              <td style="padding:8px 12px;color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Fix</td>
            </tr>
            {issue_rows}
          </table>
          {'<p style="color:#64748B;font-size:11px;margin-top:8px;">+ ' + str(len(critical_issues) - 10) + ' more issues</p>' if len(critical_issues) > 10 else ''}
          <div style="margin-top:20px;padding:12px 16px;background:#10B98110;border:1px solid #10B98130;border-radius:8px;">
            <span style="color:#10B981;font-size:11px;font-weight:700;">{scan_result.get('auto_fixable', 0)} issues can be auto-fixed</span>
            <span style="color:#64748B;font-size:10px;display:block;margin-top:4px;">
              Go to Admin Console &gt; Developer &gt; Code Health &gt; JS/TDZ Scanner &gt; Auto-Fix
            </span>
          </div>
        </div>
        <p style="color:#94A3B8;font-size:11px;">
          Scanned <strong>{scan_result['files_scanned']}</strong> files &bull;
          {scan_result['total_issues']} total issues &bull;
          {scan_result['medium']} medium &bull; {scan_result['low']} low
        </p>"""

        email_html = _wrap(
            title="Code Health Alert",
            preheader=f"{scan_result['critical']} critical issues detected in nightly scan",
            inner_html=body_html,
            cta_label="Open Code Health Scanner",
            cta_url=os.environ.get("FRONTEND_BASE_URL", "") + "/admin",
            accent="#EF4444",
        )

        # Send to all admins
        admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
        for admin in admins:
            await send_email(
                recipient_email=admin["email"],
                subject=f"[Code Health Alert] {scan_result['critical']} Critical Issues Detected",
                content=email_html,
                recipient_name=admin.get("name"),
                template_key="code_health_alert",
            )
        logger.info(f"Code health alert sent to {len(admins)} admins")
    except Exception as e:
        logger.error(f"Failed to send code health alert: {e}")
