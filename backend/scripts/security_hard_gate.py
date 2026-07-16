#!/usr/bin/env python3
"""Security Hard Gate (PASS/FAIL).

Enforces mandatory security checks across:
1) Vulnerabilities + dependency issues (Python + frontend production deps)
2) Auth bypass risks (static admin-route guard scan + runtime unauthorized checks)
3) Injection risks (static dangerous API scan + runtime payload probes)

Policy:
- HIGH / CRITICAL findings => FAIL
- MEDIUM / LOW / UNKNOWN findings => WARN (reported, non-blocking)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


APP_ROOT = Path("/app")
BACKEND_DIR = APP_ROOT / "backend"
FRONTEND_DIR = APP_ROOT / "frontend"
DEFAULT_REPORT = APP_ROOT / "security_reports" / "latest_security_gate.json"

FAIL_SEVERITIES = {"high", "critical"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], cwd: Path, timeout: int = 240) -> dict[str, Any]:
    try:
        result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return {
            "ok": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": cmd,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": 2,
            "stdout": "",
            "stderr": str(exc),
            "cmd": cmd,
        }


def _severity_normalize(raw: str | None) -> str:
    value = (raw or "unknown").strip().lower()
    if value in {"critical", "high", "medium", "moderate", "low", "unknown"}:
        if value == "moderate":
            return "medium"
        return value
    return "unknown"


def _load_base_url(cli_base_url: str | None) -> str | None:
    if cli_base_url:
        return cli_base_url.rstrip("/")
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env_base:
        return env_base.rstrip("/")

    env_file = FRONTEND_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return None


def scan_python_dependencies() -> dict[str, Any]:
    cmd = ["pip-audit", "--local", "--format", "json"]
    run = _run(cmd, BACKEND_DIR, timeout=300)

    payload: dict[str, Any] = {
        "tool": "pip-audit --local --format json",
        "scan_error": None,
        "high_or_critical": [],
        "warnings": [],
        "summary": {},
    }

    if not run["ok"]:
        payload["scan_error"] = run["stderr"]
        payload["summary"] = {
            "passed": False,
            "reason": "python dependency scan failed to run",
        }
        return payload

    raw = (run.get("stdout") or "").strip()
    if not raw:
        payload["scan_error"] = (run.get("stderr") or "pip-audit returned empty output")[-2000:]
        payload["summary"] = {
            "passed": False,
            "reason": "python dependency scan missing JSON output",
        }
        return payload

    try:
        data = json.loads(raw)
    except Exception:
        payload["scan_error"] = f"Unable to parse pip-audit JSON. stderr={run.get('stderr', '')[-1200:]}"
        payload["summary"] = {
            "passed": False,
            "reason": "python dependency scan JSON parse error",
        }
        return payload

    severity_counts: dict[str, int] = defaultdict(int)
    for dep in data.get("dependencies", []):
        name = dep.get("name")
        version = dep.get("version")
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id")
            severity = _severity_normalize(vuln.get("severity"))
            severity_counts[severity] += 1
            finding = {
                "package": name,
                "version": version,
                "vuln_id": vuln_id,
                "severity": severity,
                "aliases": vuln.get("aliases", []),
                "fix_versions": vuln.get("fix_versions", []),
            }
            if severity in FAIL_SEVERITIES:
                payload["high_or_critical"].append(finding)
            else:
                payload["warnings"].append(finding)

    payload["summary"] = {
        "passed": len(payload["high_or_critical"]) == 0,
        "high_or_critical_count": len(payload["high_or_critical"]),
        "warning_count": len(payload["warnings"]),
        "severity_counts": dict(severity_counts),
    }
    return payload


def _parse_yarn_json_lines(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def scan_frontend_dependencies() -> dict[str, Any]:
    cmd = ["yarn", "audit", "--groups", "dependencies", "--level", "high", "--json"]
    run = _run(cmd, FRONTEND_DIR, timeout=300)

    payload: dict[str, Any] = {
        "tool": "yarn audit --groups dependencies --level high --json",
        "scan_error": None,
        "high_or_critical": [],
        "warnings": [],
        "resolution_warnings": [],
        "summary": {},
    }

    if not run["ok"]:
        payload["scan_error"] = run["stderr"]
        payload["summary"] = {
            "passed": False,
            "reason": "frontend dependency scan failed to run",
        }
        return payload

    entries = _parse_yarn_json_lines((run.get("stdout") or "") + "\n" + (run.get("stderr") or ""))
    if not entries:
        payload["scan_error"] = "No parseable yarn audit JSON entries found"
        payload["summary"] = {
            "passed": False,
            "reason": "frontend dependency scan produced no parseable output",
        }
        return payload

    seen = set()
    for entry in entries:
        entry_type = entry.get("type")
        if entry_type == "warning":
            warning_text = str(entry.get("data", ""))
            payload["resolution_warnings"].append(warning_text)
            continue

        if entry_type != "auditAdvisory":
            continue

        advisory = entry.get("data", {}).get("advisory", {})
        sev = _severity_normalize(advisory.get("severity"))
        module_name = advisory.get("module_name")
        advisory_id = advisory.get("id")
        key = (module_name, advisory_id, sev)
        if key in seen:
            continue
        seen.add(key)

        finding = {
            "module": module_name,
            "advisory_id": advisory_id,
            "severity": sev,
            "title": advisory.get("title"),
            "url": advisory.get("url"),
            "patched_versions": advisory.get("patched_versions"),
            "vulnerable_versions": advisory.get("vulnerable_versions"),
        }
        if sev in FAIL_SEVERITIES:
            payload["high_or_critical"].append(finding)
        else:
            payload["warnings"].append(finding)

    payload["summary"] = {
        "passed": len(payload["high_or_critical"]) == 0,
        "high_or_critical_count": len(payload["high_or_critical"]),
        "warning_count": len(payload["warnings"]),
        "resolution_warning_count": len(payload["resolution_warnings"]),
    }
    return payload


def _route_decorator_path(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in {"get", "post", "put", "delete", "patch"}:
        return None
    if not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _has_admin_guard(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for arg in [*fn.args.args, *fn.args.kwonlyargs]:
        default_node = None
        defaults = list(fn.args.defaults)
        kw_defaults = list(fn.args.kw_defaults)
        if arg in fn.args.args and defaults:
            idx = fn.args.args.index(arg)
            offset = len(fn.args.args) - len(defaults)
            if idx >= offset:
                default_node = defaults[idx - offset]
        elif arg in fn.args.kwonlyargs and kw_defaults:
            idx = fn.args.kwonlyargs.index(arg)
            default_node = kw_defaults[idx]

        if isinstance(default_node, ast.Call) and _call_name(default_node.func).endswith("Depends"):
            for item in default_node.args:
                if _call_name(item) in {"require_admin", "_require_admin"}:
                    return True

    probe = ast.Module(body=fn.body, type_ignores=[])
    for node in ast.walk(probe):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            name = _call_name(node.value.func)
            if name in {"require_admin", "_require_admin"}:
                return True
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"require_admin", "_require_admin"}:
                return True

    has_get_current_user_call = False
    has_is_admin_check = False
    has_getattr_admin_check = False
    has_http_403 = False
    has_admin_literal = False
    for node in ast.walk(probe):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            if _call_name(node.value.func) == "get_current_user":
                has_get_current_user_call = True
        if isinstance(node, ast.Call) and _call_name(node.func) == "get_current_user":
            has_get_current_user_call = True

        if isinstance(node, ast.Call) and _call_name(node.func) == "getattr" and len(node.args) >= 2:
            second = node.args[1]
            if isinstance(second, ast.Constant) and isinstance(second.value, str) and "admin" in second.value.lower():
                has_getattr_admin_check = True

        if isinstance(node, ast.Call) and _call_name(node.func).endswith("HTTPException"):
            status_value = None
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, int):
                    status_value = first.value
            for kw in node.keywords:
                if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                    status_value = kw.value.value
            if status_value == 403:
                has_http_403 = True

        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "admin" in node.value.lower():
            has_admin_literal = True

        if isinstance(node, ast.Attribute) and node.attr == "is_admin":
            has_is_admin_check = True

    if has_get_current_user_call and (has_is_admin_check or has_getattr_admin_check or (has_http_403 and has_admin_literal)):
        return True

    return False


def scan_auth_bypass_static() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    files = [*BACKEND_DIR.glob("routes/**/*.py"), BACKEND_DIR / "server.py"]

    for file_path in files:
        if not file_path.exists():
            continue
        try:
            src = file_path.read_text()
            tree = ast.parse(src)
        except Exception as exc:
            issues.append({
                "file": str(file_path),
                "issue": f"parse_error: {exc}",
                "severity": "high",
            })
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_paths = [
                p for p in (_route_decorator_path(dec) for dec in node.decorator_list) if p is not None
            ]
            for route_path in route_paths:
                if "/admin" not in route_path:
                    continue
                if not _has_admin_guard(node):
                    issues.append({
                        "file": str(file_path),
                        "function": node.name,
                        "route": route_path,
                        "issue": "admin route missing explicit require_admin guard",
                        "severity": "medium",
                        "confidence": "low",
                    })

    return {
        "high_or_critical": [i for i in issues if _severity_normalize(i.get("severity")) in FAIL_SEVERITIES],
        "warnings": [i for i in issues if _severity_normalize(i.get("severity")) not in FAIL_SEVERITIES],
        "summary": {
            "passed": True,
            "issue_count": len(issues),
        },
    }


def discover_admin_get_routes(limit: int = 60) -> list[str]:
    routes: list[str] = []
    files = [*BACKEND_DIR.glob("routes/**/*.py"), BACKEND_DIR / "server.py"]

    for file_path in files:
        if not file_path.exists():
            continue
        try:
            tree = ast.parse(file_path.read_text())
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                if dec.func.attr != "get":
                    continue
                if not dec.args:
                    continue
                first = dec.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    continue
                path = first.value
                if "/admin" not in path:
                    continue
                if "{" in path or "}" in path:
                    continue
                if path not in routes:
                    routes.append(path)
                if len(routes) >= limit:
                    return routes

    return routes


def scan_injection_static() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    files = [
        p
        for p in BACKEND_DIR.glob("**/*.py")
        if "tests" not in p.parts and "__pycache__" not in p.parts and "venv" not in p.parts
    ]

    for file_path in files:
        try:
            src = file_path.read_text()
            tree = ast.parse(src)
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)

            if name in {"eval", "exec"}:
                findings.append({
                    "file": str(file_path),
                    "line": getattr(node, "lineno", 0),
                    "issue": f"dangerous dynamic execution: {name}()",
                    "severity": "critical",
                })

            if name == "os.system":
                findings.append({
                    "file": str(file_path),
                    "line": getattr(node, "lineno", 0),
                    "issue": "command execution via os.system",
                    "severity": "high",
                })

            if name in {"subprocess.run", "subprocess.call", "subprocess.Popen", "subprocess.check_output"}:
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        findings.append({
                            "file": str(file_path),
                            "line": getattr(node, "lineno", 0),
                            "issue": f"subprocess shell=True in {name}",
                            "severity": "critical",
                        })

            if name == "pickle.loads":
                findings.append({
                    "file": str(file_path),
                    "line": getattr(node, "lineno", 0),
                    "issue": "unsafe deserialization via pickle.loads",
                    "severity": "high",
                })

            if name == "yaml.load":
                safe_loader = False
                for kw in node.keywords:
                    if kw.arg == "Loader" and _call_name(kw.value).endswith("SafeLoader"):
                        safe_loader = True
                if not safe_loader:
                    findings.append({
                        "file": str(file_path),
                        "line": getattr(node, "lineno", 0),
                        "issue": "yaml.load without SafeLoader",
                        "severity": "high",
                    })

    return {
        "high_or_critical": [f for f in findings if _severity_normalize(f.get("severity")) in FAIL_SEVERITIES],
        "warnings": [f for f in findings if _severity_normalize(f.get("severity")) not in FAIL_SEVERITIES],
        "summary": {
            "passed": len([f for f in findings if _severity_normalize(f.get("severity")) in FAIL_SEVERITIES]) == 0,
            "issue_count": len(findings),
        },
    }


def runtime_auth_and_injection_checks(base_url: str | None) -> dict[str, Any]:
    payload = {
        "base_url": base_url,
        "auth_bypass": {"checks": [], "failures": []},
        "injection": {"checks": [], "failures": []},
        "summary": {},
    }

    if not base_url:
        payload["summary"] = {
            "passed": False,
            "reason": "missing base URL for runtime security probes",
        }
        payload["auth_bypass"]["failures"].append({
            "issue": "runtime auth probe skipped: missing base URL",
            "severity": "high",
        })
        return payload

    admin_probes = [
        "/api/admin/autonomous-engine/failure-memory/dashboard",
        "/api/admin/activity-log?limit=1",
        "/api/admin/system/metrics",
    ]
    discovered = discover_admin_get_routes(limit=60)
    for route in discovered:
        resolved = route if route.startswith("/api/") else f"/api{route}"
        if resolved not in admin_probes:
            admin_probes.append(resolved)

    session = requests.Session()
    for path in admin_probes:
        url = f"{base_url}{path}"
        try:
            resp = session.get(url, timeout=8)
            check = {"url": url, "status": resp.status_code}
            payload["auth_bypass"]["checks"].append(check)
            if resp.status_code not in {401, 403}:
                if resp.status_code == 200:
                    payload["auth_bypass"]["failures"].append({
                        "url": url,
                        "status": resp.status_code,
                        "issue": "admin endpoint accessible without auth",
                        "severity": "critical",
                    })
                else:
                    payload["auth_bypass"]["checks"].append({
                        "url": url,
                        "status": resp.status_code,
                        "warning": "unexpected status for unauthenticated admin probe",
                    })
        except Exception as exc:
            payload["auth_bypass"]["failures"].append({
                "url": url,
                "issue": f"runtime probe error: {exc}",
                "severity": "high",
            })

    login_url = f"{base_url}/api/auth/login"
    injection_payloads = [
        {"email": "admin@realaicoach.app' OR '1'='1", "password": "anything"},
        {"email": {"$ne": ""}, "password": {"$ne": ""}},
    ]

    for body in injection_payloads:
        try:
            resp = requests.post(login_url, json=body, timeout=15)
            payload["injection"]["checks"].append({
                "url": login_url,
                "status": resp.status_code,
                "payload_type": "nosql_like" if isinstance(body["email"], dict) else "string_sqli_like",
            })
            if resp.status_code == 200 or resp.status_code >= 500:
                payload["injection"]["failures"].append({
                    "url": login_url,
                    "status": resp.status_code,
                    "issue": "login endpoint accepted or crashed on injection probe",
                    "severity": "critical",
                })
        except Exception as exc:
            payload["injection"]["failures"].append({
                "url": login_url,
                "issue": f"runtime injection probe error: {exc}",
                "severity": "high",
            })

    payload["summary"] = {
        "passed": len(payload["auth_bypass"]["failures"]) == 0 and len(payload["injection"]["failures"]) == 0,
        "auth_failure_count": len(payload["auth_bypass"]["failures"]),
        "injection_failure_count": len(payload["injection"]["failures"]),
    }
    return payload


def build_gate_report(base_url: str | None) -> dict[str, Any]:
    python_deps = scan_python_dependencies()
    frontend_deps = scan_frontend_dependencies()
    auth_static = scan_auth_bypass_static()
    injection_static = scan_injection_static()
    runtime = runtime_auth_and_injection_checks(base_url)

    blockers: list[dict[str, Any]] = []

    if not python_deps.get("summary", {}).get("passed", False):
        blockers.extend(python_deps.get("high_or_critical", []))
        if python_deps.get("scan_error"):
            blockers.append({"issue": python_deps.get("scan_error"), "severity": "high", "source": "python_dependency_scan"})

    if not frontend_deps.get("summary", {}).get("passed", False):
        blockers.extend(frontend_deps.get("high_or_critical", []))
        if frontend_deps.get("scan_error"):
            blockers.append({"issue": frontend_deps.get("scan_error"), "severity": "high", "source": "frontend_dependency_scan"})

    # Static auth bypass scan is treated as heuristic warning-only evidence;
    # runtime checks provide blocker-level confirmation.
    blockers.extend(injection_static.get("high_or_critical", []))
    blockers.extend(runtime.get("auth_bypass", {}).get("failures", []))
    blockers.extend(runtime.get("injection", {}).get("failures", []))

    passed = len(blockers) == 0

    report = {
        "generated_at": _now_iso(),
        "policy": {
            "fail_on": sorted(FAIL_SEVERITIES),
            "warn_on": ["medium", "low", "unknown"],
        },
        "base_url": base_url,
        "scans": {
            "dependencies": {
                "python": python_deps,
                "frontend": frontend_deps,
            },
            "auth_bypass": {
                "static": auth_static,
                "runtime": runtime.get("auth_bypass", {}),
            },
            "injection": {
                "static": injection_static,
                "runtime": runtime.get("injection", {}),
            },
        },
        "summary": {
            "passed": passed,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "notes": [
                "Frontend dependency gate uses production-only yarn audit high/critical advisories.",
                "Python dependency gate uses pip-audit local environment scan; unknown severities are warnings.",
            ],
        },
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Security hard gate (mandatory PASS/FAIL).")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--base-url", default=None, help="Base URL for runtime probes")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to write JSON report")
    args = parser.parse_args()

    base_url = _load_base_url(args.base_url)
    report = build_gate_report(base_url)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 60)
        print("Security Hard Gate")
        print("=" * 60)
        print(f"Report: {report_path}")
        print(f"Base URL: {report.get('base_url')}")
        print(f"Result: {'PASS' if report['summary']['passed'] else 'FAIL'}")
        print(f"Blockers: {report['summary']['blocker_count']}")
        print("-" * 60)
        if report["summary"]["passed"]:
            print("No HIGH/CRITICAL security blockers found.")
        else:
            for idx, blocker in enumerate(report["summary"]["blockers"], 1):
                print(f"{idx}. [{blocker.get('severity', 'unknown').upper()}] {blocker.get('issue', blocker)}")
        print("=" * 60)

    sys.exit(0 if report["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()
