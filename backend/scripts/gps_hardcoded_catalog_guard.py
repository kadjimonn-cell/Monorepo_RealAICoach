#!/usr/bin/env python3
"""GPS Hardcoded Catalog Guard

Blocks CI when hardcoded feature/FAQ catalogs are introduced outside GPS state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TARGET_GLOBS = [
    "backend/**/*.py",
    "frontend/**/*.ts",
    "frontend/**/*.tsx",
]

IGNORE_PARTS = {
    "/node_modules/",
    "/venv/",
    "/.git/",
    "/test_reports/",
    "/memory/",
    "/tests/",
    "/__tests__/",
}

BANNED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("HARDCODED_DEFAULT_FEATURES", re.compile(r"\bDEFAULT_FEATURES\s*=\s*\[", re.MULTILINE)),
    ("HARDCODED_FAQ_CATALOG", re.compile(r"\bFAQ_DATA_[A-Z0-9_]*\s*=\s*\[", re.MULTILINE)),
    ("HARDCODED_FAQ_TRANSLATIONS", re.compile(r"\bFAQ_TRANSLATIONS\s*=\s*\{", re.MULTILINE)),
    ("HARDCODED_FEATURES_CONST", re.compile(r"\bconst\s+FEATURES\s*=\s*\[", re.MULTILINE)),
    ("HARDCODED_NOVA_FEATURE_SUGGESTIONS", re.compile(r"\bFEATURE_SUGGESTIONS\s*=\s*\{", re.MULTILINE)),
    ("HARDCODED_NOVA_TOPIC_MAP", re.compile(r"\bTOPIC_CATEGORY_MAP\s*=\s*\{", re.MULTILINE)),
    ("HARDCODED_FEATURE_PREVIEWS", re.compile(r"\bFEATURE_PREVIEWS\s*[:=]", re.MULTILINE)),
    ("HARDCODED_PLAN_CATALOG", re.compile(r"\bBASE_PLANS\s*=\s*\[", re.MULTILINE)),
    ("HARDCODED_SUBSCRIPTION_PLANS", re.compile(r"\bSUBSCRIPTION_PLANS\s*=\s*\{", re.MULTILINE)),
    ("HARDCODED_SUPPORT_CATEGORY_CATALOG", re.compile(r"\b(CATEGORY_META|FEATURE_CATEGORIES)\s*[:=]\s*\{", re.MULTILINE)),
    ("STALE_STATIC_AI_COUNT", re.compile(r"\b(26|32)\+?\s+(?:AI\s+)?(?:specialized\s+)?(?:features?|tools?|copilots?)\b", re.IGNORECASE)),
]


def _should_scan(path: Path) -> bool:
    p = f"/{path.as_posix()}/"
    return not any(part in p for part in IGNORE_PARTS)


def _line_number(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def run_guard() -> dict:
    blockers = []
    seen: set[str] = set()
    for glob in TARGET_GLOBS:
        for path in ROOT.glob(glob):
            if not path.is_file() or not _should_scan(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = path.relative_to(ROOT).as_posix()
            for code, pattern in BANNED_PATTERNS:
                for match in pattern.finditer(content):
                    fingerprint = f"{rel}:{code}:{match.start()}"
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    blockers.append(
                        {
                            "file": rel,
                            "line": _line_number(content, match.start()),
                            "code": code,
                            "message": "Hardcoded feature/FAQ catalog detected. Move to GlobalPlatformState.",
                        }
                    )

    return {"passed": len(blockers) == 0, "blocker_count": len(blockers), "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description="GPS hardcoded catalog CI guard")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    result = run_guard()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print("[PASSED] GPS hardcoded catalog guard")
        else:
            print(f"[BLOCKED] {result['blocker_count']} hardcoded catalog violation(s)")
            for b in result["blockers"]:
                print(f" - {b['code']} {b['file']}:{b['line']} {b['message']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
