#!/usr/bin/env python3
"""Theme hardcoded-color scanner/autofixer for scoped frontend surfaces.

Scopes:
- admin-tabs
- non-admin-features
- all
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


HEX_TOKEN_RE = re.compile(r"#[0-9A-Fa-f]{3,8}")

PRIMARY = {
    "0F766E", "14B8A6", "06B6D4", "118AB2", "3B82F6", "6366F1", "8B5CF6", "A78BFA",
    "0EA5E9", "1E40AF", "1D4ED8", "2563EB", "22D3EE", "5EEAD4", "A2AAAD"
}
SUCCESS = {"10B981", "22C55E", "34A853", "06D6A0", "16A34A"}
WARNING = {"F59E0B", "F97316", "EAB308", "FBBF24"}
ERROR = {"EF4444", "DC2626", "991B1B", "FCA5A5", "7F1D1D", "FEF2F2", "B91C1C"}
TEXT = {"0F172A", "111827", "1F2937", "080E24", "0B0F1A", "1E293B", "000000"}
MUTED = {"475569", "64748B", "94A3B8", "9CA3AF", "CBD5E1", "E2E8F0"}
WHITE = {"FFFFFF", "FFF", "F8FAFC", "F9FAFB", "F1F5F9", "FAFBFC", "F5F7FA", "FFFFF0", "FFFAEB"}


def _frontend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def gather_files(scope: str) -> List[Path]:
    root = _frontend_root()
    files: set[Path] = set()

    if scope in {"admin-tabs", "all"}:
        for p in (root / "app").rglob("*.tsx"):
            rel = p.relative_to(root).as_posix()
            if rel.startswith("app/admin/") or rel.startswith("app/(tabs)/") or "/admin" in rel:
                files.add(p)
        for p in (root / "src/components/admin").rglob("*.tsx"):
            files.add(p)

    if scope in {"non-admin-features", "all"}:
        for p in (root / "app/features").rglob("*.tsx"):
            files.add(p)
        for p in (root / "src/components").rglob("*.tsx"):
            rel = p.relative_to(root).as_posix()
            if rel.startswith("src/components/admin/"):
                continue
            files.add(p)

    return sorted(files)


def map_hex_token(token: str) -> str:
    t = token[1:].upper()
    base = t
    alpha = ""
    if len(t) == 8:
        base = t[:6]
        alpha = t[6:]
    elif len(t) == 4:
        base = "".join(ch * 2 for ch in t[:3])
        alpha = t[3] * 2
    elif len(t) == 3:
        base = "".join(ch * 2 for ch in t)

    if base in WHITE:
        return "var(--app-primary-text)"
    if base in TEXT:
        return "var(--app-text)"
    if base in MUTED:
        return "var(--app-text-muted)"
    if base in SUCCESS:
        return "var(--app-success-soft)" if alpha else "var(--app-success)"
    if base in WARNING:
        return "var(--app-warning-soft)" if alpha else "var(--app-warning)"
    if base in ERROR:
        return "var(--app-error-soft)" if alpha else "var(--app-error)"
    if base in PRIMARY:
        return "var(--app-primary-soft)" if alpha else "var(--app-primary)"
    return "var(--app-primary-soft)" if alpha else "var(--app-primary)"


def normalize_var_fallbacks(text: str) -> Tuple[str, bool]:
    out: List[str] = []
    i = 0
    changed = False
    n = len(text)

    while i < n:
        idx = text.find("var(", i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])

        j = idx + 4
        depth = 1
        while j < n and depth > 0:
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            j += 1

        if depth != 0:
            out.append(text[idx:j])
            i = j
            continue

        expr = text[idx + 4 : j - 1]
        d = 0
        comma = -1
        for k, ch in enumerate(expr):
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
            elif ch == "," and d == 0:
                comma = k
                break

        if comma != -1:
            token = expr[:comma].strip()
            if token.startswith("--app-"):
                out.append(f"var({token})")
                changed = True
            else:
                out.append(text[idx:j])
        else:
            out.append(text[idx:j])
        i = j

    return "".join(out), changed


def scan_or_fix(files: List[Path], autofix: bool, max_offenders: int) -> Dict:
    root = _frontend_root()
    offenders = []
    changed_files = []
    total_hex = 0

    for p in files:
        rel = p.relative_to(root).as_posix()
        text = p.read_text(errors="ignore")
        file_hex = 0
        samples = []
        lines = text.splitlines()

        for idx, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
                continue
            matches = HEX_TOKEN_RE.findall(line)
            if matches:
                file_hex += len(matches)
                if len(samples) < 5:
                    samples.append({"line": idx, "code": s[:180]})

        total_hex += file_hex
        if file_hex > 0:
            offenders.append({"file": rel, "count": file_hex, "samples": samples})

        if autofix and file_hex > 0:
            normalized, norm_changed = normalize_var_fallbacks(text)
            replaced = HEX_TOKEN_RE.sub(lambda m: map_hex_token(m.group(0)), normalized)
            if replaced != text or norm_changed:
                p.write_text(replaced)
                changed_files.append(rel)

    offenders.sort(key=lambda x: x["count"], reverse=True)
    return {
        "files_scanned": len(files),
        "files_with_hex": len(offenders),
        "total_hex_tokens": total_hex,
        "offenders": offenders[:max_offenders],
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["admin-tabs", "non-admin-features", "all"], default="admin-tabs")
    parser.add_argument("--mode", choices=["scan", "autofix"], default="scan")
    parser.add_argument("--report-file", default="")
    parser.add_argument("--max-offenders", type=int, default=40)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    files = gather_files(args.scope)
    result = scan_or_fix(files, autofix=args.mode == "autofix", max_offenders=args.max_offenders)
    payload = {
        "scope": args.scope,
        "mode": args.mode,
        **result,
    }

    if args.report_file:
        out_path = Path(args.report_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2))

    print(json.dumps(payload))
    if args.fail_on_findings and int(payload.get("total_hex_tokens", 0)) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
