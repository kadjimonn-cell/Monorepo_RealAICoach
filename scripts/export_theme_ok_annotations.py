"""Export all `@theme-ok` / `@theme-audit-file-ok` annotations across the frontend as a Markdown report suitable for pasting into a PR comment.

Output:
  - Prints the Markdown to stdout
  - Also writes it to /app/memory/THEME_OK_EXPORT.md (overwritten each run)

Usage:
  python3 /app/scripts/export_theme_ok_annotations.py

Example row:
  | src/components/Logo.tsx | 29 | inline | variant-based (light/dark brand text) |
"""
from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

FRONTEND_ROOTS = [Path("/app/frontend/src"), Path("/app/frontend/app"), Path("/app/frontend/components")]
SKIP = ("node_modules", "__tests__", ".expo", "dist", "build")
SUFFIXES = {".tsx", ".jsx", ".ts"}

INLINE_RE = re.compile(r"@theme-ok\b[:\s]*([^*}\n\r]*)")
FILE_RE = re.compile(r"@theme-audit-file-ok\b[:\s]*([^*}\n\r]*)")


def _clean(reason: str) -> str:
    reason = reason.strip().rstrip("*/}").strip().strip("-—").strip()
    return reason or "(no reason)"


def _scan():
    inline_hits: list[tuple[str, int, str]] = []
    file_hits: list[tuple[str, str]] = []
    for root in FRONTEND_ROOTS:
        if not root.exists():
            continue
        for fp in root.rglob("*"):
            if fp.suffix not in SUFFIXES:
                continue
            if any(seg in str(fp) for seg in SKIP):
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            rel = str(fp).replace("/app/frontend/", "")
            # File-level pragma (only consider first 20 lines)
            head = "\n".join(text.splitlines()[:20])
            m = FILE_RE.search(head)
            if m:
                file_hits.append((rel, _clean(m.group(1))))
            # Inline pragmas
            for i, line in enumerate(text.splitlines(), 1):
                if "@theme-audit-file-ok" in line:
                    continue
                m = INLINE_RE.search(line)
                if m:
                    inline_hits.append((rel, i, _clean(m.group(1))))
    return inline_hits, file_hits


def _render(inline_hits, file_hits) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = []
    out.append("## Theme-OK Annotations Audit")
    out.append("")
    out.append(f"_Generated {now} · {len(file_hits)} file-level pragmas · {len(inline_hits)} inline annotations_")
    out.append("")
    out.append("Every intentional deviation from the V2 Teal theme system is annotated with a `@theme-ok` / `@theme-audit-file-ok` pragma. This report makes those exceptions easy to review in PRs.")
    out.append("")
    if file_hits:
        out.append("### File-level pragmas (always-dark ops panels, etc.)")
        out.append("")
        out.append("| File | Reason |")
        out.append("| --- | --- |")
        for rel, reason in sorted(file_hits):
            out.append(f"| `{rel}` | {reason} |")
        out.append("")
    if inline_hits:
        by_reason: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for rel, ln, reason in inline_hits:
            by_reason[reason].append((rel, ln))
        out.append("### Inline annotations (grouped by reason)")
        out.append("")
        for reason in sorted(by_reason.keys()):
            rows = by_reason[reason]
            out.append(f"**{reason}** — {len(rows)} occurrence{'s' if len(rows) != 1 else ''}")
            out.append("")
            out.append("| File | Line |")
            out.append("| --- | --- |")
            for rel, ln in sorted(rows):
                out.append(f"| `{rel}` | {ln} |")
            out.append("")
    if not file_hits and not inline_hits:
        out.append("_No annotations found — the codebase is fully on-theme._")
    return "\n".join(out) + "\n"


def main() -> int:
    inline_hits, file_hits = _scan()
    md = _render(inline_hits, file_hits)
    out_path = Path("/app/memory/THEME_OK_EXPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWritten to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
