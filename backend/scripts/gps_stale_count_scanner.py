#!/usr/bin/env python3
"""Dedicated CI scanner for stale hardcoded platform counts and GPS catalog drift."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = [ROOT / "frontend" / "app", ROOT / "frontend" / "src", ROOT / "backend"]
EXCLUDED_PARTS = {
    ".git",
    ".metro-cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "media",
    "test_reports",
    "tests",
}
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md"}

PATTERNS = [
    (
        "STALE_AI_COUNT",
        re.compile(
            r"\b(?:26|32)\+?\s+(?:AI\s+)?(?:specialized\s+)?(?:features?|tools?|copilots?)\b|"
            r"\b(?:26|32)\+?\s+AI[-\s](?:driven|powered)",
            re.IGNORECASE,
        ),
    ),
    ("STATIC_SUBSCRIPTION_PLANS", re.compile(r"\bSUBSCRIPTION_PLANS\s*=\s*\{")),
    ("STATIC_BASE_PLANS", re.compile(r"\bBASE_PLANS\s*=\s*\[")),
    ("STATIC_FEATURE_SUGGESTIONS", re.compile(r"\bFEATURE_SUGGESTIONS\s*=\s*\{")),
    ("STATIC_TOPIC_CATEGORY_MAP", re.compile(r"\bTOPIC_CATEGORY_MAP\s*=\s*\{")),
    ("STATIC_FEATURE_PREVIEWS", re.compile(r"\bFEATURE_PREVIEWS\s*[:=]")),
    ("STATIC_FAQ_DATA", re.compile(r"\bFAQ_DATA_[A-Z0-9_]*\s*=")),
]


def iter_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            if path.name == "gps_stale_count_scanner.py":
                continue
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            yield path


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in iter_files():
        text = path.read_text(errors="ignore")
        for code, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                snippet = text[max(0, match.start() - 70) : match.end() + 70].replace("\n", " ").strip()
                findings.append(
                    {
                        "code": code,
                        "path": str(path.relative_to(ROOT)),
                        "line": line,
                        "match": match.group(0),
                        "snippet": snippet,
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = scan()
    payload = {"passed": not findings, "finding_count": len(findings), "findings": findings}
    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        for item in findings:
            print(f"[{item['code']}] {item['path']}:{item['line']} :: {item['match']}")
    else:
        print("[PASSED] GPS stale count scanner")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())