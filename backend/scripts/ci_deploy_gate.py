#!/usr/bin/env python3
"""CI/CD Deploy Gate — standalone script for pipeline integration.

Usage:
  python scripts/ci_deploy_gate.py           # Check and exit 0 (pass) or 1 (fail)
  python scripts/ci_deploy_gate.py --json    # Output JSON result
  python scripts/ci_deploy_gate.py --api     # Check via API (requires running server)

Exit codes:
  0 = Gate passed, safe to deploy
  1 = Gate blocked, critical issues found
  2 = Error running check

Integration examples:
  # GitHub Actions
  - name: Deploy Gate
    run: python backend/scripts/ci_deploy_gate.py

  # GitLab CI
  deploy_gate:
    script: python backend/scripts/ci_deploy_gate.py

  # Docker / Makefile
  make gate  # Add: gate: python scripts/ci_deploy_gate.py
"""

import subprocess
import sys
import json
import os

GATE_RULES = "F821,F811,F601"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUFF_BIN = os.environ.get("RUFF_BIN", "ruff")
NAV_LOCK_GUARD = os.environ.get("NAV_LOCK_GUARD", "python scripts/nav_key_lock_guard.py --strict-governance")
GPS_HARDCODE_GUARD = os.environ.get("GPS_HARDCODE_GUARD", "python scripts/gps_hardcoded_catalog_guard.py --json")
GPS_AUTOFIX_ASSISTANT = os.environ.get("GPS_AUTOFIX_ASSISTANT", "python scripts/gps_premerge_autofix_assistant.py --json")
PREVIEW_HOST_GUARD = os.environ.get("PREVIEW_HOST_GUARD", "python scripts/preview_host_guard.py --mode ci")


def run_gate_local():
    """Run ruff directly for gate check."""
    try:
        result = subprocess.run(
            [RUFF_BIN, "check", ".", "--select", GATE_RULES, "--output-format", "json"],
            capture_output=True, text=True, cwd=BACKEND_DIR, timeout=30,
        )
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        blockers = []
        for issue in issues:
            blockers.append({
                "file": issue.get("filename", "").replace(BACKEND_DIR + "/", ""),
                "line": issue.get("location", {}).get("row", 0),
                "code": issue.get("code", ""),
                "message": issue.get("message", ""),
            })

        nav_guard = subprocess.run(
            NAV_LOCK_GUARD,
            shell=True,
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
            timeout=30,
        )
        if nav_guard.returncode != 0:
            blockers.append({
                "file": ".nav-key-lock-metadata.json",
                "line": 1,
                "code": "NAV_LOCK_GUARD",
                "message": "Navigation key lock metadata out of sync with AppShell nav keys.",
                "details": (nav_guard.stdout or nav_guard.stderr or "").strip()[-600:],
            })

        gps_guard = subprocess.run(
            GPS_HARDCODE_GUARD,
            shell=True,
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
            timeout=45,
        )
        if gps_guard.returncode != 0:
            details = (gps_guard.stdout or gps_guard.stderr or "").strip()
            guard_blockers = []
            try:
                parsed = json.loads(details)
                guard_blockers = parsed.get("blockers", [])
                for item in parsed.get("blockers", []):
                    blockers.append(
                        {
                            "file": item.get("file", "unknown"),
                            "line": item.get("line", 1),
                            "code": item.get("code", "GPS_HARDCODE_GUARD"),
                            "message": item.get("message", "Hardcoded catalog detected."),
                        }
                    )
            except Exception:
                blockers.append(
                    {
                        "file": "gps_hardcoded_catalog_guard.py",
                        "line": 1,
                        "code": "GPS_HARDCODE_GUARD",
                        "message": "Hardcoded feature/FAQ catalog detected.",
                        "details": details[-600:],
                    }
                )

            # Generate patch-ready autofix suggestions (CI failure only)
            try:
                auto_cmd = [
                    "python",
                    "scripts/gps_premerge_autofix_assistant.py",
                    "--json",
                    "--guard-blockers-json",
                    json.dumps(guard_blockers),
                ]
                auto = subprocess.run(
                    auto_cmd,
                    capture_output=True,
                    text=True,
                    cwd=BACKEND_DIR,
                    timeout=45,
                )
                auto_payload = json.loads((auto.stdout or "").strip() or "{}")
                for suggestion in auto_payload.get("suggestions", []):
                    blockers.append(
                        {
                            "file": suggestion.get("file", "gps_premerge_autofix_assistant.py"),
                            "line": suggestion.get("line", 1),
                            "code": suggestion.get("code", "GPS_AUTOFIX"),
                            "message": suggestion.get("guidance", "Autofix suggestion generated."),
                            "details": suggestion.get("patch_hint", ""),
                        }
                    )
            except Exception as auto_exc:
                blockers.append(
                    {
                        "file": "gps_premerge_autofix_assistant.py",
                        "line": 1,
                        "code": "GPS_AUTOFIX_ASSISTANT",
                        "message": f"Autofix assistant execution failed: {auto_exc}",
                    }
                )

        preview_guard = subprocess.run(
            PREVIEW_HOST_GUARD,
            shell=True,
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
            timeout=45,
        )
        if preview_guard.returncode != 0:
            blockers.append(
                {
                    "file": "scripts/preview_host_guard.py",
                    "line": 1,
                    "code": "PREVIEW_HOST_GUARD",
                    "message": "Preview host safety policy failed (stale host or blocked token detected).",
                    "details": (preview_guard.stdout or preview_guard.stderr or "").strip()[-1000:],
                }
            )

        return {"passed": len(blockers) == 0, "blocker_count": len(blockers), "blockers": blockers}
    except FileNotFoundError:
        print(f"ERROR: ruff not found at '{RUFF_BIN}'. Install: pip install ruff", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


def run_gate_api():
    """Run gate check via the API endpoint."""
    import urllib.request
    api_url = os.environ.get("API_URL", "http://localhost:8001")
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        print("ERROR: Set ADMIN_TOKEN env var for API mode", file=sys.stderr)
        sys.exit(2)
    req = urllib.request.Request(
        f"{api_url}/api/admin/code-health/deploy-gate",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    use_json = "--json" in sys.argv
    use_api = "--api" in sys.argv

    result = run_gate_api() if use_api else run_gate_local()

    if use_json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 48)
        print("  Deploy Gate — CI/CD Check")
        print(f"  Rules: {GATE_RULES}")
        print("=" * 48)

        if result["passed"]:
            print("\n  [PASSED] No critical issues. Safe to deploy.\n")
        else:
            print(f"\n  [BLOCKED] {result['blocker_count']} critical issue(s) found!\n")
            for b in result["blockers"]:
                print(f"    {b['code']}  {b['file']}:{b['line']}  {b['message']}")
            print("\n  Fix these before deploying.")
            print("  F821 = Undefined name (runtime crash)")
            print("  F811 = Redefined while unused (logic error)")
            print("  F601 = Duplicate dict key (data loss)\n")
            print("  NAV_LOCK_GUARD = Nav key changed without approved lock metadata update\n")
            print("  GPS_HARDCODE_GUARD = Hardcoded feature/FAQ catalog introduced outside GPS\n")
            print("  GPS_AUTOFIX_ASSISTANT = Patch-ready remediation suggestions generated on CI failure\n")
            print("  PREVIEW_HOST_GUARD = Stale preview host reference or blocked domain token detected\n")

        print("=" * 48)

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
