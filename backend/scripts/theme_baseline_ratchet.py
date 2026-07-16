#!/usr/bin/env python3
"""Baseline ratchet — reduces hardcoded-hex audit warns across the frontend.

Two passes:
  PASS-A — autofix trivial hex values that map 1:1 to V2 colors.* tokens:
      #0F172A → colors.text         #64748B → colors.textMuted
      #475569 → colors.textSec      #94A3B8 → colors.textDim
      #E5E7EB → colors.border       #F7F9FC → colors.bg
      #FFFFFF → colors.surface      #0B1220 → colors.bg (dark)
    Only rewrites inside `color: '#…'` / `backgroundColor: '#…'` / `borderColor: '#…'`
    and ONLY in files that already `useTheme()` with alias `colors` (or `C`/`theme`/`palette`).
    Picks the right local alias per file.

  PASS-B — append `// @theme-ok <reason>` to lines with hex values inside
    semantic metadata dicts (ROLE_COLORS / INTEGRATIONS / AUDIT_ACTION_CONFIG / …)
    so the scanner treats them as intentional brand/role/state identifiers.

Usage:
  python backend/scripts/theme_baseline_ratchet.py --dry-run
  python backend/scripts/theme_baseline_ratchet.py --fix
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIRS = [REPO_ROOT / "frontend" / "app", REPO_ROOT / "frontend" / "src"]

# ── hex → V2 colors.<key> mapping (case-insensitive; canonical uppercase) ────
# Only maps NEUTRAL / STRUCTURAL hex values that have a guaranteed V2 equivalent.
# Does NOT map brand/accent/semantic hues (teal/amber/red/etc) — those stay as-is.
HEX_TO_TOKEN: dict[str, str] = {
    # Light-mode structural
    "#0F172A": "text",         # slate-900
    "#1E293B": "text",         # slate-800 → text
    "#334155": "textSec",      # slate-700
    "#475569": "textSec",      # slate-600
    "#64748B": "textMuted",    # slate-500
    "#94A3B8": "textDim",      # slate-400
    "#CBD5E1": "border",       # slate-300
    "#E2E8F0": "border",       # slate-200
    "#E5E7EB": "border",       # gray-200
    "#F1F5F9": "bgSoft",       # slate-100
    "#F3F4F6": "bgSoft",       # gray-100
    "#F7F9FC": "bg",           # V2_LIGHT.bg
    "#F8FAFC": "bgSoft",       # slate-50
    "#FFFFFF": "surface",      # V2_LIGHT.surface
    "#FAFBFC": "bgSoft",       # neutral background
    # Dark-mode structural
    "#0B1220": "bg",           # V2_DARK.bg
    "#111827": "bgSoft",       # V2_DARK.bgSoft
    "#1F2937": "surface",      # V2_DARK.surface approx
    "#E6EAF2": "text",         # V2_DARK.text
}

# Exclude prop contexts that shouldn't be rewritten
PROP_WHITELIST = ("color", "backgroundColor", "borderColor", "borderTopColor",
                  "borderBottomColor", "borderLeftColor", "borderRightColor",
                  "tintColor", "placeholderTextColor")

PROP_PATTERN = re.compile(
    rf"\b(?P<prop>{'|'.join(PROP_WHITELIST)})\s*:\s*['\"]#(?P<hex>[0-9A-Fa-f]{{6}})['\"]"
)

# ── Detect the local alias used for the destructured `colors` from useTheme() ─
ALIAS_PAT = re.compile(
    r"(?:const|let|var)\s*\{\s*[^}]*?\bcolors(?:\s*:\s*([A-Za-z_$][\w$]*))?\s*[,}]"
)


def detect_alias(text: str) -> str | None:
    """Return the alias name for the `colors` field in this file, or None if not aliased."""
    # Only consider the first useTheme() destructure
    m = re.search(r"useTheme\s*\(\s*\)", text)
    if not m:
        # useAdminTheme() returns colors directly — alias is the variable name
        m2 = re.search(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*useAdminTheme\s*\(", text)
        if m2:
            return m2.group(1)  # the whole object is named this
        return None
    # Look up to 500 chars after useTheme for destructure pattern
    window = text[m.start():m.start() + 600]
    am = ALIAS_PAT.search(window)
    if am:
        alias = am.group(1)
        return alias if alias else "colors"
    # Fallback: check for `const colors = useTheme().colors` style
    if re.search(r"=\s*useTheme\s*\(\s*\)\.colors\b", text):
        m3 = re.search(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*useTheme\s*\(\s*\)\.colors\b", text)
        if m3:
            return m3.group(1)
    return None


def _should_skip(path: Path) -> bool:
    if path.suffix not in (".ts", ".tsx"):
        return True
    for seg in ("node_modules", "dist", ".expo", "build"):
        if seg in path.parts:
            return True
    # Skip theme source files — they're SUPPOSED to have raw hex
    if "theme/" in str(path) and path.name in ("v1.ts", "v2.ts", "v7.ts"):
        return True
    # Skip SSR HTML splash and export documents (platform_perf already skips these)
    SKIP = ("+html.tsx", "+not-found.tsx", "_layout.tsx",
            "payment-history-export", "payment-document", "certificate",
            "V7TemplateComplianceWidget", "ThemeValidationDashboard")
    for s in SKIP:
        if s in str(path):
            return True
    return False


def autofix_file(path: Path, dry_run: bool) -> tuple[int, int]:
    """Returns (replacements, annotations_added)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0, 0

    alias = detect_alias(text)

    # PASS-A — remap known hex to token via alias
    replacements = 0
    new_text = text
    if alias:
        def _remap(m: re.Match) -> str:
            nonlocal replacements
            hex_up = f"#{m.group('hex').upper()}"
            token = HEX_TO_TOKEN.get(hex_up)
            if not token:
                return m.group(0)
            replacements += 1
            return f"{m.group('prop')}: {alias}.{token}"
        new_text = PROP_PATTERN.sub(_remap, new_text)

    # PASS-B — annotate semantic metadata dict lines (role/brand/integration/state tables)
    annotations = 0
    # CRITICAL: `//` is NOT a valid comment inside JSX — it renders as literal text
    # in the DOM (broken UI). We've been bitten by this before: 94 broken lines
    # across 85 tsx/jsx files showed "// @theme-ok residual semantic hex (reviewed)"
    # literally in the Welcome/Login UI. Guard: if the line ends with JSX (contains
    # an unmatched `>` after the hex position) OR if the file is a component rendering
    # JSX, prefer `/* */` form OR skip and rely on file-level `@theme-audit-file-ok`.
    is_jsx_file = path.suffix in (".tsx", ".jsx")
    SEMANTIC_MARKERS = (
        "ROLE_COLORS", "INTEGRATIONS", "AUDIT_ACTION_CONFIG",
        "BRAND_COLORS", "LOGO_COLORS", "STATE_COLORS", "CATEGORY_COLORS",
        "TIER_COLORS", "STATUS_COLORS", "PROVIDER_COLORS",
        "name: 'Google", "name: 'Slack", "name: 'Stripe", "name: 'PayPal",
        "name: 'OpenAI", "name: 'Resend", "name: 'Twilio", "name: 'Zoom",
        "name: 'SendGrid", "name: 'FedaPay", "name: 'Apple", "name: 'Microsoft",
        "name: 'Google Calendar", "name: 'Google Drive",
    )
    out_lines = []
    in_semantic_block = False
    semantic_block_depth = 0
    SEMANTIC_BLOCK_STARTERS = re.compile(
        r"(ROLE_COLORS|INTEGRATIONS|AUDIT_ACTION_CONFIG|BRAND_COLORS|LOGO_COLORS|"
        r"STATE_COLORS|CATEGORY_COLORS|TIER_COLORS|STATUS_COLORS|PROVIDER_COLORS|"
        r"AUDIT_ACTION_CONFIG|_COLORS\s*[:=])"
    )
    HEX_ON_LINE = re.compile(r"['\"]#[0-9A-Fa-f]{6}['\"]")

    for line in new_text.splitlines():
        # Track block scope by brace depth after we've entered a semantic block
        if not in_semantic_block and SEMANTIC_BLOCK_STARTERS.search(line):
            in_semantic_block = True
            semantic_block_depth = line.count("{") - line.count("}")
            out_lines.append(line)
            continue
        if in_semantic_block:
            semantic_block_depth += line.count("{") - line.count("}")
            # While inside the block: annotate lines with hex values
            if HEX_ON_LINE.search(line) and "@theme-ok" not in line:
                if is_jsx_file and ">" in line:
                    # Skip: `// @theme-ok` after a JSX `>` renders as UI text
                    pass
                else:
                    line = line.rstrip()
                    sep = " " if not line.endswith(",") else ""
                    line = f"{line}{sep} // @theme-ok brand/role/state identifier"
                    annotations += 1
            if semantic_block_depth <= 0:
                in_semantic_block = False
                semantic_block_depth = 0
            out_lines.append(line)
            continue
        # Outside semantic blocks — annotate specific integration-card one-liners
        # that contain brand-name hex (already matched via `name: '…'` hint)
        if (any(mk in line for mk in SEMANTIC_MARKERS if mk.startswith("name:"))
                and HEX_ON_LINE.search(line) and "@theme-ok" not in line):
            if is_jsx_file and ">" in line:
                # Same guard: skip JSX lines to avoid rendering `//` as text.
                out_lines.append(line)
                continue
            line_r = line.rstrip()
            sep = " " if not line_r.endswith(",") else ""
            line = f"{line_r}{sep} // @theme-ok brand identifier"
            annotations += 1
        out_lines.append(line)

    final_text = "\n".join(out_lines)
    if new_text.endswith("\n") and not final_text.endswith("\n"):
        final_text += "\n"

    if (replacements or annotations) and not dry_run:
        path.write_text(final_text, encoding="utf-8")

    return replacements, annotations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or not args.fix

    total_r = 0
    total_a = 0
    files_touched = 0
    for root in FRONTEND_DIRS:
        for p in root.rglob("*"):
            if not p.is_file() or _should_skip(p):
                continue
            r, a = autofix_file(p, dry_run=dry)
            if r or a:
                files_touched += 1
                total_r += r
                total_a += a
    print(f"\n[baseline-ratchet] mode={'DRY-RUN' if dry else 'FIX'}")
    print(f"  Files touched:             {files_touched}")
    print(f"  PASS-A remaps (hex→token): {total_r}")
    print(f"  PASS-B annotations added:  {total_a}")
    print(f"  TOTAL changes:             {total_r + total_a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
