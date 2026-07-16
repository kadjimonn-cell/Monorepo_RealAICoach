#!/usr/bin/env python3
"""Email V7 theme compliance gate.

Validates that all template previews render and contain dual-theme hooks
required by enterprise email dark/light compliance checks.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.email_templates import get_all_template_previews


def main() -> int:
    previews = get_all_template_previews()
    failing: list[dict] = []

    for p in previews:
        html = str(p.get("html") or "")
        subject = str(p.get("subject") or "")
        if subject.startswith("Error:"):
            failing.append({"key": p.get("key"), "reason": "render_error", "subject": subject})
            continue

        has_light = "data-theme-light" in html
        has_dark = "data-theme-dark" in html
        if not (has_light and has_dark):
            failing.append({
                "key": p.get("key"),
                "reason": "missing_theme_hooks",
                "has_light": has_light,
                "has_dark": has_dark,
            })

    report = {
        "templates_total": len(previews),
        "failing_total": len(failing),
        "failing": failing,
    }
    Path("/tmp/email_v7_theme_gate_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if failing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
