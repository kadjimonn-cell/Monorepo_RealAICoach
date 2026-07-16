#!/usr/bin/env python3
"""
Regression CI runner.

Runs two checks and exits non-zero if either regresses:
    1. Theme Visibility Audit (static scan) — fails on Grade C/D/F OR any FAIL.
    2. Invitation Lifecycle pytest suite (tests/test_invitation_lifecycle.py).

Intended to be invoked from CI (GitHub Actions, GitLab CI, etc.) and locally:

    $ cd /app/backend && python scripts/run_regression_ci.py

Env overrides:
    THEME_AUDIT_MIN_GRADE=A-         (default: A)
    SKIP_THEME_AUDIT=1               (default: 0)
    SKIP_INVITATION_TESTS=1          (default: 0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

GRADE_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A-": 4, "A": 5}


def _log(symbol: str, msg: str) -> None:
    print(f"{symbol} {msg}", flush=True)


def run_theme_audit(min_grade: str) -> tuple[bool, dict]:
    """Static theme-visibility audit — returns (passed, summary)."""
    from routes.platform_perf import _build_theme_visibility_audit

    result = _build_theme_visibility_audit()
    grade = (result.get("overall_grade") or "").upper()
    summary = result.get("summary", {})
    fails = int(summary.get("total_fail_issues", 0))

    grade_ok = GRADE_ORDER.get(grade, -1) >= GRADE_ORDER.get(min_grade, 5)
    passed = grade_ok and fails == 0

    return passed, {
        "grade": grade,
        "fails": fails,
        "warns": summary.get("total_warn_issues"),
        "min_grade": min_grade,
        "files_scanned": summary.get("total_files_scanned"),
    }


def run_invitation_tests() -> tuple[bool, dict]:
    """Invoke pytest on the invitation lifecycle + PII encryption + GDPR + v7 enforcement suites."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_invitation_lifecycle.py",
        "tests/test_contact_support_pii_encryption.py",
        "tests/test_gdpr_self_service.py",
        "tests/test_email_template_key_enforcement.py",
        "tests/test_email_health_summary.py",
        "-v", "--tb=short",
        "-p", "asyncio", "-p", "pytest_asyncio",
        "-o", "asyncio_mode=auto",
        "-q",
    ]
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    started = time.time()
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True)
    duration = round(time.time() - started, 2)

    tail = (proc.stdout or "").splitlines()[-12:]
    passed = proc.returncode == 0
    return passed, {
        "returncode": proc.returncode,
        "duration_s": duration,
        "stdout_tail": "\n".join(tail),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-6:]) if proc.stderr else "",
    }


def main() -> int:
    min_grade = os.environ.get("THEME_AUDIT_MIN_GRADE", "A").upper()
    skip_audit = os.environ.get("SKIP_THEME_AUDIT", "0") == "1"
    skip_tests = os.environ.get("SKIP_INVITATION_TESTS", "0") == "1"

    report: dict = {"theme_audit": None, "invitation_tests": None, "passed": True}

    # Theme audit
    if skip_audit:
        _log("-", "Theme audit skipped (SKIP_THEME_AUDIT=1)")
    else:
        _log("~", f"Running theme visibility audit (min grade = {min_grade})...")
        audit_pass, audit_summary = run_theme_audit(min_grade)
        report["theme_audit"] = {"passed": audit_pass, **audit_summary}
        if audit_pass:
            _log("✓", f"Theme audit: grade={audit_summary['grade']} fails={audit_summary['fails']} warns={audit_summary['warns']}")
        else:
            _log("✗", f"Theme audit FAILED: grade={audit_summary['grade']} (min={min_grade}) fails={audit_summary['fails']}")
            report["passed"] = False

    # Invitation lifecycle tests
    if skip_tests:
        _log("-", "Invitation lifecycle tests skipped (SKIP_INVITATION_TESTS=1)")
    else:
        _log("~", "Running invitation lifecycle pytest suite...")
        tests_pass, tests_summary = run_invitation_tests()
        report["invitation_tests"] = {"passed": tests_pass, **tests_summary}
        if tests_pass:
            _log("✓", f"Invitation lifecycle: all phases passed in {tests_summary['duration_s']}s")
        else:
            _log("✗", f"Invitation lifecycle FAILED (exit={tests_summary['returncode']})")
            if tests_summary.get("stdout_tail"):
                print("  ── stdout tail ──")
                for line in tests_summary["stdout_tail"].splitlines():
                    print(f"  {line}")
            if tests_summary.get("stderr_tail"):
                print("  ── stderr tail ──")
                for line in tests_summary["stderr_tail"].splitlines():
                    print(f"  {line}")
            report["passed"] = False

    # Write a machine-readable report so CI jobs can surface it as an artifact
    out_path = BACKEND_DIR / "regression_ci_report.json"
    try:
        out_path.write_text(json.dumps(report, indent=2))
        _log("~", f"Report written to {out_path.relative_to(BACKEND_DIR)}")
    except Exception:
        pass

    print()
    if report["passed"]:
        _log("✓", "All regression checks passed.")
        return 0
    _log("✗", "Regression detected — failing build.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
