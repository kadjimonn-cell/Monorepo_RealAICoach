#!/usr/bin/env python3
"""One-shot codemod: strip `@autofix-moved` comments from admin panels.

Context: Earlier autofix passes moved module-scope helper objects
(`STATUS_META`, `REPAIR_ICONS`, etc.) INTO the main component body so
they could reference component-scoped `colors`/`AC` values. That broke
module-scope helper components (e.g. `StatusPill`, `FeatureRow`) which
still referenced those same names and could not see the now-inner
definitions — causing the "Something went wrong" ReferenceError class.

We already repaired the substantive bugs by hand (see PRD entries for
the Admin Crash Audit v2 sweep). Everything still carrying the
`@autofix-moved: was module-level const X` comment has been manually
reviewed and either:
  - already has a module-scope fallback alongside the moved copy, or
  - the helper that needed the module-scope value has been inlined.

So the only remaining job is to strip the stale comments so future
greps stay quiet. This script is idempotent: running it twice is a
no-op on the second run.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path("/app/frontend/src/components/admin")

# Matches lines like:
#   // @autofix-moved: was module-level const STATUS_META
#   // @autofix-moved: was module-level const EVENT_ICONS
# …with any leading whitespace.
_STALE_COMMENT = re.compile(r"^\s*//\s*@autofix-moved:[^\n]*\n", re.MULTILINE)


def strip_comments(path: pathlib.Path, *, dry_run: bool) -> int:
    """Return the number of @autofix-moved lines removed from `path`."""
    src = path.read_text(encoding="utf-8")
    matches = list(_STALE_COMMENT.finditer(src))
    if not matches:
        return 0
    out = _STALE_COMMENT.sub("", src)
    if not dry_run:
        path.write_text(out, encoding="utf-8")
    return len(matches)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report only; don't write.")
    args = ap.parse_args()

    if not ROOT.is_dir():
        print(f"error: admin dir not found: {ROOT}", file=sys.stderr)
        return 1

    files = sorted(ROOT.glob("*.tsx"))
    total_lines = 0
    touched: list[tuple[str, int]] = []
    for f in files:
        n = strip_comments(f, dry_run=args.dry_run)
        if n:
            touched.append((f.name, n))
            total_lines += n
    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"[autofix-codemod] {mode}: {len(touched)} file(s), {total_lines} comment line(s)")
    for name, n in touched:
        print(f"  - {name}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
