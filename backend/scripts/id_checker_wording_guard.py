#!/usr/bin/env python3
"""ID Checker wording guard.

Blocks CI if banned legacy user-facing phrases are reintroduced.
Also writes PR-comment-friendly artifacts for failed runs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/app")
ARTIFACT_DIR = ROOT / "test_reports"
ARTIFACT_JSON = ARTIFACT_DIR / "id_checker_wording_guard.json"
ARTIFACT_PR_COMMENT = ARTIFACT_DIR / "id_checker_wording_guard_pr_comment.md"

TARGET_GLOBS = [
    "frontend/src/i18n/locales/*.ts",
    "backend/utils/email_templates.py",
    "backend/routes/id_verification.py",
    "backend/routes/auth.py",
    "backend/routes/platform_analytics.py",
]

BANNED_PATTERNS = [
    re.compile(r"\bID Verification\b", re.IGNORECASE),
    re.compile(r"\bIdentity verification\b", re.IGNORECASE),
]

ALLOW_SUBSTRINGS = [
    "idVerification.",
    "id_verification",
    "/id-verification",
]


def is_allowed_line(line: str) -> bool:
    return any(tok in line for tok in ALLOW_SUBSTRINGS)


def _write_artifacts(violations: list[dict]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "guard": "id_checker_wording_guard",
        "status": "failed" if violations else "passed",
        "total_violations": len(violations),
        "violations": violations,
    }
    ARTIFACT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not violations:
        ARTIFACT_PR_COMMENT.write_text(
            "## ✅ ID Checker Wording Guard\n\n"
            "No banned legacy wording found (`ID Verification` / `Identity verification`).\n",
            encoding="utf-8",
        )
        return

    lines = [
        "## ❌ ID Checker Wording Guard Failed",
        "",
        "Legacy wording was detected. Please replace with **ID Checker** and re-run checks.",
        "",
        f"**Total Violations:** {len(violations)}",
        "",
        "| File | Line | Matched Phrase | Snippet |",
        "|---|---:|---|---|",
    ]
    for v in violations[:150]:
        snippet = (v["line_text"][:180] + "…") if len(v["line_text"]) > 180 else v["line_text"]
        snippet = snippet.replace("|", "\\|")
        lines.append(f"| `{v['file']}` | {v['line']} | `{v['matched']}` | `{snippet}` |")

    if len(violations) > 150:
        lines.append("")
        lines.append(f"_…and {len(violations)-150} more (see JSON artifact)_")

    ARTIFACT_PR_COMMENT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    violations: list[dict] = []
    files: list[Path] = []
    for g in TARGET_GLOBS:
        files.extend(ROOT.glob(g))

    for path in sorted(set(files)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(text.splitlines(), start=1):
            if is_allowed_line(line):
                continue
            for pat in BANNED_PATTERNS:
                m = pat.search(line)
                if m:
                    violations.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "line": idx,
                            "matched": m.group(0),
                            "line_text": line.strip(),
                        }
                    )
                    break

    _write_artifacts(violations)

    if violations:
        print("ID Checker wording guard FAILED:")
        for v in violations[:200]:
            print(f"- {v['file']}:{v['line']}: {v['line_text']}")
        if len(violations) > 200:
            print(f"... and {len(violations) - 200} more")
        print(f"PR comment artifact: {ARTIFACT_PR_COMMENT}")
        print(f"JSON artifact: {ARTIFACT_JSON}")
        return 1

    print("ID Checker wording guard PASSED")
    print(f"PR comment artifact: {ARTIFACT_PR_COMMENT}")
    print(f"JSON artifact: {ARTIFACT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
