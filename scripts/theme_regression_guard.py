#!/usr/bin/env python3
"""Theme regression guard.

Fails when:
1) Theme audit reports any violations
2) Exempt markers are reintroduced
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_v2_theme_global.py"
AUDIT_REPORT = pathlib.Path("/tmp/v2_theme_audit_global.json")


def run_audit() -> dict:
    proc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(f"Theme audit command failed with code {proc.returncode}")

    if not AUDIT_REPORT.exists():
        raise SystemExit("Theme audit report not found at /tmp/v2_theme_audit_global.json")

    return json.loads(AUDIT_REPORT.read_text(encoding="utf-8"))


def has_exempt_markers() -> list[str]:
    markers = ["@theme-v2-exempt", "@theme-audit-file-ok"]
    offenders: list[str] = []

    for path in (ROOT / "frontend").rglob("*.tsx"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if any(marker in text for marker in markers):
            offenders.append(str(path.relative_to(ROOT)))

    return offenders


def main() -> int:
    report = run_audit()
    violations = int(report.get("files_with_violations", 0))
    if violations > 0:
        print(f"❌ Theme regression guard failed: {violations} files with violations.")
        return 1

    exempt_offenders = has_exempt_markers()
    if exempt_offenders:
        print("❌ Theme regression guard failed: exempt markers reintroduced:")
        for file in exempt_offenders[:50]:
            print(f"  - {file}")
        if len(exempt_offenders) > 50:
            print(f"  ... and {len(exempt_offenders) - 50} more")
        return 1

    print("✅ Theme regression guard passed: zero violations and zero exempt markers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
