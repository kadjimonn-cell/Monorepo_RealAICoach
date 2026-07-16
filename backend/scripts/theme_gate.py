#!/usr/bin/env python3
"""Theme Compliance Gate — CI/CD enforcement ratchet.

Runs the V2 Teal theme audit against a committed baseline file
(`/app/.theme-baseline.json`) and exits non-zero on any regression
(warns above baseline, fails above baseline, or grade drop).

The baseline is checked into git. To update it after a successful
theme-cleanup pass:

    python backend/scripts/theme_gate.py --update-baseline

Usage:

    # In CI / on PR branches — fails the build if regression detected
    python backend/scripts/theme_gate.py

    # To see current delta without failing
    python backend/scripts/theme_gate.py --report-only

    # Update the baseline after a cleanup lands (run on main after merge)
    python backend/scripts/theme_gate.py --update-baseline

Exit codes:
    0 — pass (current state ≤ baseline)
    1 — regression (build should be blocked)
    2 — infrastructure error (audit couldn't run)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import from /app/backend regardless of where this is invoked
REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # /app
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# DB isn't needed for a pure audit — stub env vars that top-level imports expect
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "gate_stub")

BASELINE_PATH = REPO_ROOT / ".theme-baseline.json"

_GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text())
    except Exception as e:
        print(f"[gate] ERROR: could not parse {BASELINE_PATH}: {e}", file=sys.stderr)
        return None


def _save_baseline(data: dict) -> None:
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _run_audit() -> dict:
    """Import + invoke the audit builder directly. Uses the same scan logic
    as the `/api/admin/platform-perf/theme-visibility-audit` endpoint but
    without going through FastAPI or needing DB/auth."""
    # Import lazily so sys.path tweak above takes effect first
    from routes.platform_perf import _build_theme_visibility_audit

    audit = _build_theme_visibility_audit()
    summary = audit.get("summary", {})
    grade = audit.get("overall_grade", "?")

    # Layer in text-contrast violations (V2 *Text variant enforcement)
    try:
        from scripts.theme_contrast_scanner import get_contrast_violations  # type: ignore
        contrast = get_contrast_violations()
    except Exception as e:
        print(f"[gate] WARN: contrast scanner failed: {e}", file=sys.stderr)
        contrast = []

    return {
        "grade": grade,
        "grade_rank": _GRADE_ORDER.get(grade, 0),
        "warns": int(summary.get("total_warn_issues", 0)),
        "fails": int(summary.get("total_fail_issues", 0)),
        "infos": int(summary.get("total_info_issues", 0)),
        "files_scanned": int(summary.get("total_files_scanned", 0)),
        "files_clean": int(summary.get("files_clean", 0)),
        "contrast_violations": len(contrast),
    }


def _format_report(current: dict, baseline: dict | None, violations: list[str]) -> str:
    lines = [
        "",
        "┌─────────────────────────────────────────────────────────────┐",
        "│           V2 Teal Theme Compliance Gate                     │",
        "└─────────────────────────────────────────────────────────────┘",
        "",
        f"  Grade:         {current['grade']:>6}",
        f"  Warns:         {current['warns']:>6}",
        f"  Fails:         {current['fails']:>6}",
        f"  Contrast:      {current.get('contrast_violations', 0):>6}",
        f"  Files scanned: {current['files_scanned']:>6}",
        f"  Files clean:   {current['files_clean']:>6}",
    ]
    if baseline:
        lines += [
            "",
            "  ── Baseline (committed) ──",
            f"  Grade:  {baseline.get('grade'):>6}",
            f"  Warns:  {baseline.get('warns'):>6}",
            f"  Fails:  {baseline.get('fails'):>6}",
            f"  Locked: {baseline.get('locked_at')}",
        ]
        dw = current["warns"] - baseline.get("warns", 0)
        df = current["fails"] - baseline.get("fails", 0)
        arrow_w = "↑" if dw > 0 else ("↓" if dw < 0 else "·")
        arrow_f = "↑" if df > 0 else ("↓" if df < 0 else "·")
        lines += [
            "",
            "  ── Delta ──",
            f"  Warns: {arrow_w} {dw:+d}",
            f"  Fails: {arrow_f} {df:+d}",
        ]
    else:
        lines += ["", "  (no baseline committed yet — permissive mode)"]
    if violations:
        lines += ["", "  ── VIOLATIONS ──"]
        lines += [f"   ✗ {v}" for v in violations]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 Teal Theme Compliance Gate")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current audit state to the committed baseline file and exit 0.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print the delta report but always exit 0 (for CI notifications, not blocking).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single-line JSON summary to stdout after the human-readable report.",
    )
    args = parser.parse_args()

    # Run audit
    try:
        current = _run_audit()
    except Exception as e:
        print(f"[gate] FATAL: audit failed: {e}", file=sys.stderr)
        return 2

    if args.update_baseline:
        now = datetime.now(timezone.utc).isoformat()
        new_baseline = {
            **current,
            "locked_at": now,
            "locked_by": os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or "manual",
            "locked_via": "theme_gate.py --update-baseline",
        }
        _save_baseline(new_baseline)
        print(_format_report(current, new_baseline, []))
        print(f"[gate] ✓ Baseline updated at {BASELINE_PATH}")
        return 0

    baseline = _load_baseline()
    violations: list[str] = []

    if baseline:
        bl_warns = int(baseline.get("warns", 0))
        bl_fails = int(baseline.get("fails", 0))
        bl_grade_rank = int(baseline.get("grade_rank", 5))

        if current["warns"] > bl_warns:
            violations.append(
                f"warns increased: {bl_warns} → {current['warns']} (Δ +{current['warns'] - bl_warns})"
            )
        if current["fails"] > bl_fails:
            violations.append(
                f"fails increased: {bl_fails} → {current['fails']} (Δ +{current['fails'] - bl_fails})"
            )
        if current["grade_rank"] < bl_grade_rank:
            violations.append(
                f"grade dropped: {baseline.get('grade')} → {current['grade']}"
            )

        bl_contrast = int(baseline.get("contrast_violations", 0))
        if current.get("contrast_violations", 0) > bl_contrast:
            violations.append(
                f"text-contrast violations increased: {bl_contrast} → {current['contrast_violations']} "
                f"(run `python backend/scripts/theme_contrast_scanner.py --fix`)"
            )

    report = _format_report(current, baseline, violations)
    print(report)

    if args.json:
        print(json.dumps({
            "current": current,
            "baseline": baseline,
            "violations": violations,
            "gate": "pass" if not violations else "fail",
            "has_baseline": baseline is not None,
        }))

    if args.report_only:
        return 0

    if not baseline:
        print("[gate] ⚠ No baseline committed — run with --update-baseline first.")
        print("[gate]   Gate is permissive until a baseline is locked.")
        return 0

    if violations:
        print(f"[gate] ✗ BUILD BLOCKED — {len(violations)} regression(s) detected.")
        print(
            "[gate]   Fix the regressions above, or run "
            "`python backend/scripts/theme_gate.py --update-baseline` "
            "locally and commit the new baseline file if the delta is intentional."
        )
        return 1

    print("[gate] ✓ PASS — no theme regressions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
