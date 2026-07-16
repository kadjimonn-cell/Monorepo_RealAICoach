#!/usr/bin/env python3
"""Feature 26 frontend runtime guard.

Fails CI when runtime frontend code introduces write calls to legacy
`/jobs/*` or `/employers/*` endpoints instead of `/hiring/v2/*`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SCAN_DIRS = [FRONTEND / "app", FRONTEND / "src"]

WRITE_CALL_RE = re.compile(
    r"api\.(post|put|patch|delete)\(\s*([`'\"])(.+?)\2",
    re.IGNORECASE,
)


def _should_scan(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in {".ts", ".tsx", ".js", ".jsx"}:
        return False
    as_posix = path.as_posix().lower()
    if ".test." in as_posix or ".spec." in as_posix:
        return False
    if "/__tests__/" in as_posix or "/tests/" in as_posix:
        return False
    return True


def main() -> int:
    violations: list[tuple[str, int, str, str]] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*"):
            if not path.is_file() or not _should_scan(path):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                match = WRITE_CALL_RE.search(line)
                if not match:
                    continue
                method = match.group(1).upper()
                endpoint = match.group(3)
                if (
                    endpoint.startswith("/jobs")
                    or endpoint.startswith("/employers")
                    or endpoint.startswith("/api/jobs")
                    or endpoint.startswith("/api/employers")
                ):
                    rel = path.relative_to(ROOT).as_posix()
                    violations.append((rel, line_no, method, endpoint))

    if violations:
        print("Feature 26 legacy write guard failed. Found forbidden runtime endpoints:")
        for rel, line_no, method, endpoint in violations:
            print(f"- {rel}:{line_no} [{method}] {endpoint}")
        print("Use /hiring/v2/* endpoints for runtime write calls.")
        return 1

    print("Feature 26 legacy write guard passed (no runtime /jobs or /employers write callers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
