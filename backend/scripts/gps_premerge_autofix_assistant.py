#!/usr/bin/env python3
"""GPS Pre-merge Autofix Assistant

Generates PR-ready patch suggestions when GPS governance checks fail.
Default scope:
1) Hardcoded catalog guard violations
2) Missing strict-label coverage keys
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_GPS_FILE = ROOT / "backend/services/gps_state_core.py"


def _load_json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


def _extract_backend_required_label_keys() -> set[str]:
    text = BACKEND_GPS_FILE.read_text(encoding="utf-8", errors="ignore")
    marker = "REQUIRED_STRICT_SURFACE_LABEL_KEYS"
    idx = text.find(marker)
    if idx < 0:
        return set()

    # Parse RHS list using AST by slicing from first '[' to matching ']'
    list_start = text.find("[", idx)
    if list_start < 0:
        return set()
    depth = 0
    end = -1
    for i in range(list_start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return set()
    blob = text[list_start : end + 1]
    try:
        node = ast.literal_eval(blob)
        return {str(item).strip() for item in list(node) if str(item).strip()}
    except Exception:
        return set()


def _extract_strict_label_keys_from_frontend() -> set[str]:
    keys: set[str] = set()
    patterns = [
        re.compile(r"strictLabel\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"getMissingLabels\(\s*\[([^\]]+)\]\s*\)", re.DOTALL),
    ]
    for path in ROOT.glob("frontend/**/*.tsx"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in patterns[0].finditer(text):
            keys.add(m.group(1).strip())
        for m in patterns[1].finditer(text):
            inside = m.group(1)
            for quoted in re.findall(r"['\"]([^'\"]+)['\"]", inside):
                keys.add(quoted.strip())
    return {k for k in keys if k}


def _suggest_for_hardcoded_blocker(blocker: dict[str, Any]) -> dict[str, Any]:
    file = blocker.get("file", "")
    code = blocker.get("code", "")
    line = blocker.get("line", 1)

    guidance = "Move static catalog data into GlobalPlatformState and consume via GPS endpoints/hooks."
    patch_hint = "No generic safe auto-edit available. Use GPS Control Center to seed data and remove static declarations."

    if code == "HARDCODED_DEFAULT_FEATURES":
        guidance = "Remove DEFAULT_FEATURES constant and seed feature_registry from GPS features only."
    elif code in {"HARDCODED_FAQ_CATALOG", "HARDCODED_FAQ_TRANSLATIONS"}:
        guidance = "Remove static FAQ dictionaries and read FAQ entries from GPS/faq_content only."
    elif code == "HARDCODED_FEATURES_CONST":
        guidance = "Replace const FEATURES array with GPS-driven feature hooks/context."

    return {
        "type": "hardcoded_catalog_violation",
        "file": file,
        "line": line,
        "code": code,
        "guidance": guidance,
        "patch_hint": patch_hint,
    }


def run_assistant(guard_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []

    # 1) Suggestions for hardcoded catalog violations
    for blocker in guard_blockers:
        suggestions.append(_suggest_for_hardcoded_blocker(blocker))

    # 2) Missing strict label keys in backend required-label catalog
    frontend_keys = _extract_strict_label_keys_from_frontend()
    backend_keys = _extract_backend_required_label_keys()
    missing = sorted([k for k in frontend_keys if k not in backend_keys])
    for key in missing:
        suggestions.append(
            {
                "type": "missing_strict_label_requirement",
                "file": "backend/services/gps_state_core.py",
                "line": 1,
                "code": "MISSING_REQUIRED_STRICT_LABEL_KEY",
                "guidance": f"Add `{key}` to REQUIRED_STRICT_SURFACE_LABEL_KEYS so strict governance checks remain complete.",
                "patch_hint": f"Insert key in REQUIRED_STRICT_SURFACE_LABEL_KEYS: '{key}'",
            }
        )

    return {
        "passed": len(suggestions) == 0,
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pre-merge GPS autofix suggestions")
    parser.add_argument("--guard-blockers-json", type=str, default="[]", help="JSON array from gps_hardcoded_catalog_guard blockers")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    blockers = _load_json(args.guard_blockers_json)
    if not isinstance(blockers, list):
        blockers = []

    result = run_assistant(blockers)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print("[PASSED] GPS pre-merge autofix assistant found no suggestions.")
        else:
            print(f"[INFO] {result['suggestion_count']} autofix suggestion(s) generated.")
            for s in result["suggestions"]:
                print(f" - {s['code']} {s['file']}:{s['line']} {s['guidance']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
