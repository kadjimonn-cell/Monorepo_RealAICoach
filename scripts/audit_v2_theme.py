#!/usr/bin/env python3
"""Platform-wide V2-theme audit v2 (deep, global scan).

Goes beyond the Apr-23 pass by checking FIVE categories of violation:

  1. module_palette — module-scope `const C/T/AC/theme = { bg: "#0..." ... }`
     literal-dark palettes (helpers and sub-components use these)
  2. inline_dark_bg  — `backgroundColor: "#0A..."`, `"#111..."`, `"#08..."`
     or `"rgb(8..."` / `"rgba(15..."` hardcoded dark bg colors on the visible
     surface
  3. inline_light_text — `color: "#FFF..."` / `"#F0F..."` / `"#E2E..."`
     hardcoded near-white text colors (locks against light-theme flip)
  4. missing_hook    — the file renders <View> / <Text> / <ScrollView>
     but does not import `useTheme` / `useAdminTheme` / `useThemeMode`
     / `useColorScheme` / `useExecTheme` (pure hardcoded UI)
  5. darkmode_ternary — `darkMode ? ... : ...` style selection instead of
     the unified `colors.*` tokens (partial-fix pattern the last autofix
     left behind)

Each file is rated P0/P1/P2 by:
  P0 — hot-path admin surface (src/components/admin/**, app/admin*.tsx,
       app/executive-dashboard.tsx, app/team-management.tsx)
  P1 — user-facing page (app/**/*.tsx except auth/debug/legal)
  P2 — token-gated / debug / print / rarely-seen (everything else)

Outputs a JSON report to /tmp/v2_theme_audit_v2.json + a short stdout
summary. Run from /app.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/app/frontend")
SRC = ROOT / "src"
APP = ROOT / "app"

# ── Regex palette ─────────────────────────────────────────────────────
# Dark hex backgrounds: #00..#2F + some common near-black (#080E24, etc.)
_DARK_HEX = r"#(?:0[0-9A-Fa-f]|1[0-9A-Fa-f]|2[0-9A-Fa-f])[0-9A-Fa-f]{3,4}"
_LIGHT_TEXT_HEX = r"#(?:F[0-9A-Fa-f]|E[89A-Fa-f]|DC|D0|D1|D2|DE)[0-9A-Fa-f]{3,4}"
# Any hex bg of length 6 (solid) that isn't suffixed with an alpha byte.
# (alpha tints like #F59E0B22 remain acceptable for semantic states.)
_SOLID_HEX = r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])"

RE_MODULE_DARK_PALETTE = re.compile(
    r"^\s*(?:const|let)\s+(?:C|T|AC|theme|Palette|colors?)\s*=\s*\{[^{}]*?\bbg:\s*['\"]" + _DARK_HEX + r"['\"]",
    re.MULTILINE,
)
# backgroundColor: '#0XXXXX' OR backgroundColor: '#1XXXXX' — dark-hardcoded
# bg that won't flip in light mode (the "dark block on a light page" bug)
RE_INLINE_DARK_BG = re.compile(
    r"backgroundColor:\s*['\"]" + _DARK_HEX + r"['\"]"
)
# backgroundColor: '#F...' / '#E...' / 'white' — light-hardcoded bg that
# won't flip in dark mode (the "white tab strip on a dark admin page" bug).
# Excludes common semantic tints (success/warning/error alpha backgrounds)
# by matching full hex only (no 1–2 char alpha hex values).
_LIGHT_BG_HEX = r"#(?:F[0-9A-Fa-f]|E[A-Fa-f][0-9A-Fa-f]|F[A-Fa-f]F[0-9A-Fa-f]|fff|FFF|FAFAFA)[0-9A-Fa-f]{0,3}"
# Light-hardcoded backgroundColor — only greys/whites (skip semantic amber/red/pink
# tints like #F59E0B, #FEE2E2). The heuristic: all three RGB channels in the top
# quartile (≥0xE0) with low saturation.
RE_INLINE_LIGHT_BG = re.compile(
    r"backgroundColor:\s*['\"]"
    r"(?:"
      r"white|#FFFFFF|#FFF|"
      r"#F[89A-F][Ff][89A-F][Ff][89A-F][Ff]|"   # near-white greys (#F9F9F9-#FFFFFF)
      r"#F[0-7][Ff][0-9A-F][Ff][0-9A-F]|"       # off-whites like #F7F9FC, #F0F4FC
      r"#E[5-9A-F][Ee][0-9A-F][Ff][0-9A-F]|"    # light greys #E5E7EB, #EEF2F7
      r"#F[13458][FEADC][FAF9EC5][AFBE8][AFEBC][0-9A-F]"  # catch-all for #F[1358]…
    r")"
    r"['\"]"
)
RE_INLINE_LIGHT_TEXT = re.compile(
    r"\bcolor:\s*['\"]" + _LIGHT_TEXT_HEX + r"['\"]"
)
# Any solid (non-alpha) hex bg on an inline style — treat as violation.
# Alpha tints (#xxxxxxNN) and already-exempt lines pass.
RE_INLINE_SOLID_BG = re.compile(
    r"backgroundColor:\s*['\"]" + _SOLID_HEX + r"['\"]"
)
# Raw rgba(0,0,0,...) or rgba(255,255,255,...) used as backgroundColor — these
# are modal/drawer backdrops that don't theme-adapt. Use colors.overlay instead.
RE_INLINE_RAW_OVERLAY = re.compile(
    r"backgroundColor:\s*['\"]rgba\(\s*(?:0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\s*,"
)
# Solid hex borderColor — borders should come from colors.border / border tokens
# so they adapt to light/dark. Exclude alpha-tint borders (#xxxxxxNN).
RE_INLINE_SOLID_BORDER = re.compile(
    r"borderColor:\s*['\"]" + _SOLID_HEX + r"['\"]"
)
# Solid hex `color:` text — text should use colors.text / colors.textSec / etc.
# Semantic colors (colors.success, colors.error) are fine, but inline hex text
# won't theme-flip. Exclude alpha variants and common svg `color: inherit` etc.
RE_INLINE_SOLID_TEXT = re.compile(
    r"\bcolor:\s*['\"]" + _SOLID_HEX + r"['\"]"
)
# Non-CSS color-like keys (`tone:`, `shadowColor:`, `tintColor:`, `fill:`,
# `stroke:`, etc.) carrying solid hex literals. These bypass the primary
# backgroundColor/color/borderColor regexes but still lock the UI to a single
# theme (see the `#0B2545` Processing Fee `tone:` regression, Apr 2026).
_NON_CSS_COLOR_KEYS = (
    r"tone|shadowColor|indicatorColor|tintColor|trackColor|thumbColor|"
    r"underlineColor(?:Android)?|placeholderTextColor|selectionColor|"
    r"rippleColor|fill|stroke"
)
RE_INLINE_SEMANTIC_SOLID_HEX = re.compile(
    r"\b(?:" + _NON_CSS_COLOR_KEYS + r"):\s*['\"]" + _SOLID_HEX + r"['\"]"
)
RE_SOFT_TOKEN_TEXT = re.compile(
    r"<Text[^\n]*\bcolor:\s*(?:"
    r"(?:colors?|C|AC|T|tokens?)\."
    r"(?:primarySoft|successSoft|errorSoft|warningSoft|infoSoft|accentSoft|blueSoft|purpleSoft|indigoSoft|orangeSoft)"
    r")",
)
# Direct useColorScheme() usage that bypasses V2 ThemeContext. The single
# legitimate consumer is the ThemeContext provider itself.
RE_STALE_COLORSCHEME = re.compile(r"\buseColorScheme\s*\(\s*\)")
# darkMode ? X : Y — only flag when at least one branch is a raw hex/rgba literal.
# Already-theme-aware ternaries (colors.bg vs colors.card) and pure label swaps
# (darkMode ? 'Dark' : 'Light') are NOT violations.
RE_DARKMODE_TERNARY = re.compile(
    r"\bdarkMode\s*\?\s*"
    r"(?:"
      # dark branch has a hex or rgba literal
      r"['\"]#[0-9A-Fa-f]{3,8}['\"]"
      r"|rgba?\(\s*\d"
    r")"
)
# Imports of theme hooks
RE_HAS_THEME_HOOK = re.compile(
    r"\b(useTheme|useAdminTheme|useThemeMode|useColorScheme|useExecTheme|ThemeContext)\b"
)
# Imports of react-native visible primitives (so we can detect UI pages)
RE_HAS_UI = re.compile(
    r"from\s+['\"]react-native['\"].*?(\{[^}]*(View|Text|ScrollView|Pressable|TouchableOpacity)[^}]*\})",
    re.DOTALL,
)
# Explicit exemption markers
RE_EXEMPT = re.compile(r"@theme-(audit-file-ok|v2-exempt|ok\b)")

# Structural dark-lock patterns that must be scanned even in exempt files.
RE_MODULE_GETADMIN_TRUE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*getAdminColors\s*\(\s*true\s*\)",
    re.MULTILINE,
)
RE_MAKET_AC_FN = re.compile(
    r"function\s+makeT\s*\(\s*AC\b[^)]*\)\s*\{",
    re.MULTILINE,
)


def _extract_brace_block(src: str, open_brace_idx: int) -> str:
    """Return substring enclosed by the brace at open_brace_idx."""
    if open_brace_idx < 0 or open_brace_idx >= len(src) or src[open_brace_idx] != "{":
        return ""
    depth = 0
    i = open_brace_idx
    while i < len(src):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace_idx + 1 : i]
        i += 1
    return ""

# ── Priority buckets ─────────────────────────────────────────────────
def rank(path: Path) -> str:
    rel = str(path.relative_to(ROOT))
    if rel.startswith(("src/components/admin/", "src/components/operations-console/",
                       "src/components/executive-dashboard/")):
        return "P0"
    if rel.startswith("app/admin") or rel.endswith(
        ("executive-dashboard.tsx", "team-management.tsx", "admin-system.tsx")
    ):
        return "P0"
    if rel.endswith("_layout.tsx") or rel.endswith("+not-found.tsx") or rel.endswith("+html.tsx"):
        return "P2"
    if "/debug" in rel or "sso-debug" in rel or "qr-approve" in rel:
        return "P2"
    if "/print/" in rel or rel.endswith(".print.tsx"):
        return "P2"
    if rel.startswith(("app/", "src/components/")):
        return "P1"
    return "P2"


def scan_file(path: Path) -> dict | None:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    exempt_whole_file = bool(RE_EXEMPT.search(src))
    has_ui = bool(RE_HAS_UI.search(src))
    lines = src.split("\n")
    # Per-line exemption: a comment on the same line (or the line above)
    # containing `@theme-v2-exempt-line` skips that line.
    def _is_exempt_line(ln_1based: int) -> bool:
        if ln_1based < 1 or ln_1based > len(lines):
            return False
        same = lines[ln_1based - 1]
        prev = lines[ln_1based - 2] if ln_1based >= 2 else ""
        return ("@theme-v2-exempt-line" in same) or ("@theme-v2-exempt-line" in prev)

    findings: dict[str, list[int]] = defaultdict(list)

    # Always-on structural checks (even for exempt files):
    # 1) module-scope getAdminColors(true)
    for m in RE_MODULE_GETADMIN_TRUE.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        findings["darklock_getadmin_true"].append(ln)

    # 2) makeT(AC) declared but AC never used inside function body
    for m in RE_MAKET_AC_FN.finditer(src):
        fn_start = m.start()
        open_brace_idx = src.find("{", m.end() - 1)
        body = _extract_brace_block(src, open_brace_idx)
        if not body:
            continue
        if not re.search(r"\bAC(?:\.|\s*\[)", body):
            ln = src[:fn_start].count("\n") + 1
            if _is_exempt_line(ln):
                continue
            findings["darklock_makeT_ignores_ac"].append(ln)

    # For files explicitly exempted, we still report structural dark-locks,
    # but skip all legacy style-hex categories.
    if exempt_whole_file and findings:
        return {
            "file": str(path.relative_to(ROOT)),
            "priority": rank(path),
            "counts": {k: len(v) for k, v in findings.items()},
            "first_line": {k: v[0] for k, v in findings.items() if v and v[0]},
        }
    if exempt_whole_file:
        return None

    if not has_ui and not findings:
        return None  # not a UI-rendering file and no structural dark-lock pattern

    if RE_MODULE_DARK_PALETTE.search(src):
        for m in RE_MODULE_DARK_PALETTE.finditer(src):
            ln = src[:m.start()].count("\n") + 1
            if _is_exempt_line(ln):
                continue
            findings["module_palette"].append(ln)
    for m in RE_INLINE_DARK_BG.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        findings["inline_dark_bg"].append(ln)
    for m in RE_INLINE_LIGHT_BG.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        findings["inline_light_bg"].append(ln)
    for m in RE_INLINE_LIGHT_TEXT.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        findings["inline_light_text"].append(ln)
    # Catch any remaining solid (non-alpha) hex bg — a silent theme escape hatch
    for m in RE_INLINE_SOLID_BG.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        # Skip lines already flagged under a more specific category (dark/light)
        if "@theme-ok" in line_src:
            continue
        if ln in findings.get("inline_dark_bg", []) or ln in findings.get("inline_light_bg", []):
            continue
        findings["inline_solid_bg"].append(ln)
    # Raw rgba(0,0,0,...) / rgba(255,255,255,...) used as backgroundColor
    for m in RE_INLINE_RAW_OVERLAY.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        if "@theme-ok" in line_src:
            continue
        findings["inline_raw_overlay"].append(ln)
    # Solid hex borderColor — borders must theme-adapt
    for m in RE_INLINE_SOLID_BORDER.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        if "@theme-ok" in line_src:
            continue
        findings["inline_solid_border"].append(ln)
    # Solid hex `color:` text — text color must theme-adapt
    for m in RE_INLINE_SOLID_TEXT.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        if "@theme-ok" in line_src:
            continue
        # Skip already-flagged light-text (more specific rule)
        if ln in findings.get("inline_light_text", []):
            continue
        findings["inline_solid_text"].append(ln)
    # Non-CSS color-like keys (tone:, shadowColor:, fill:, stroke:, etc.) carrying
    # solid hex literals — the `#0B2545` Processing-Fee tone regression pattern.
    for m in RE_INLINE_SEMANTIC_SOLID_HEX.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        if "@theme-ok" in line_src:
            continue
        findings["inline_semantic_solid_hex"].append(ln)
    # Soft semantic background tokens cannot be used as Text foreground colors.
    for m in RE_SOFT_TOKEN_TEXT.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        line_src = lines[ln - 1] if ln <= len(lines) else ""
        if "@theme-ok" in line_src:
            continue
        findings["soft_token_text_color"].append(ln)
    # CI guard — static dark-locked theme object inside ExecDashboardPanels.tsx.
    # Blocks reintroduction of the bug fixed in Apr 2026 where
    # `StyleSheet.create(...)` was built at module load using
    # `getAdminColors(true|false)`, locking all 44 downstream components to one
    # theme. Only triggers for this specific file; other panels use their own
    # hooks.
    if path.name == "ExecDashboardPanels.tsx" and re.search(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:StyleSheet\.create|buildExecStyles)\s*\(\s*getAdminColors\s*\(",
        src,
        re.MULTILINE,
    ):
        ln = 1
        for i, row in enumerate(lines):
            if re.search(r"=\s*(?:StyleSheet\.create|buildExecStyles)\s*\(\s*getAdminColors\s*\(", row):
                ln = i + 1
                break
        findings["exec_dashboard_static_theme"].append(ln)
    # Stale useColorScheme() usage — only allowed in ThemeContext.tsx itself
    if "ThemeContext" not in str(path):
        for m in RE_STALE_COLORSCHEME.finditer(src):
            ln = src[:m.start()].count("\n") + 1
            if _is_exempt_line(ln):
                continue
            findings["stale_colorscheme"].append(ln)
    if not RE_HAS_THEME_HOOK.search(src):
        # Not a violation if the component accepts a theme palette as prop.
        # Covers common names: colors, AC, C, T, tokens, palette, theme.
        accepts_colors_prop = bool(re.search(
            r"\{[^}]*\b(?:colors|AC|C|T|tokens|palette|theme)\b[^}]*\}:\s*\{[^}]*\b(?:colors|AC|C|T|tokens|palette|theme)\b[^}]*\}|"
            r"\b(?:colors|AC|C|T|tokens|palette|theme):\s*(?:any|Colors|ThemeColors|typeof\s+V[12]_(?:LIGHT|DARK))\b|"
            r"props\.(?:colors|AC|C|T|tokens|palette|theme)\b",
            src,
        )) or bool(re.search(
            r"function\s+\w+\s*\(\s*\{[^)]*\b(?:colors|AC|C|T|tokens|palette|theme)\b[^)]*\}",
            src,
        )) or bool(re.search(
            # Imports a shared theme palette from a neighbor shared/theme module
            r"from\s+['\"][^'\"]*(?:shared|theme|tokens|palette)(?:\.[tj]sx?)?['\"]",
            src,
        ))
        # Also skip wrapper/animation/context components that don't apply any
        # color styling. Heuristic: no hex literal AND no `color:` /
        # `backgroundColor:` / `borderColor:` style property anywhere.
        renders_colors = bool(re.search(
            r"#[0-9A-Fa-f]{3,8}|"
            r"\bcolor:\s*(?!['\"]inherit|transparent)|"
            r"backgroundColor:\s*|"
            r"borderColor:\s*",
            src,
        ))
        if not accepts_colors_prop and renders_colors:
            findings["missing_hook"].append(0)
    for m in RE_DARKMODE_TERNARY.finditer(src):
        ln = src[:m.start()].count("\n") + 1
        if _is_exempt_line(ln):
            continue
        findings["darkmode_ternary"].append(ln)
    if not findings:
        return None
    return {
        "file": str(path.relative_to(ROOT)),
        "priority": rank(path),
        "counts": {k: len(v) for k, v in findings.items()},
        "first_line": {k: v[0] for k, v in findings.items() if v and v[0]},
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any P0 violations are present (use in CI/pre-commit).")
    ap.add_argument("--budget", type=int, default=0,
                    help="Max tolerable P0 violation count (default 0).")
    ap.add_argument("--baseline", type=str, default="",
                    help="Optional baseline JSON report path to compare against (fail only on regressions).")
    ap.add_argument("--fail-on-new", action="store_true",
                    help="When baseline is provided, fail if any category/file count regresses above baseline.")
    args = ap.parse_args()

    files = list(SRC.rglob("*.tsx")) + list(APP.rglob("*.tsx"))
    results: list[dict] = []
    for f in files:
        r = scan_file(f)
        if r:
            results.append(r)

    totals = Counter()
    by_priority = Counter()
    for r in results:
        for k, v in r["counts"].items():
            totals[k] += v
        by_priority[r["priority"]] += 1

    exempt_count = sum(
        1 for f in files
        if RE_EXEMPT.search(f.read_text(encoding="utf-8", errors="replace") or "")
    )
    compliant_count = sum(
        1 for f in files
        if RE_HAS_THEME_HOOK.search(f.read_text(encoding="utf-8", errors="replace") or "")
    )

    out = {
        "files_scanned": len(files),
        "files_with_violations": len(results),
        "files_theme_compliant": compliant_count,
        "files_explicitly_exempt": exempt_count,
        "violations_by_category": dict(totals),
        "files_by_priority": dict(by_priority),
        "violations": sorted(
            results,
            key=lambda r: (r["priority"], -sum(r["counts"].values()), r["file"]),
        ),
    }
    Path("/tmp/v2_theme_audit_v2.json").write_text(json.dumps(out, indent=2))

    print(f"Files scanned:        {out['files_scanned']}")
    print(f"Theme-compliant:      {out['files_theme_compliant']}")
    print(f"Explicitly exempt:    {out['files_explicitly_exempt']}")
    print(f"Files w/ violations:  {out['files_with_violations']}")
    print(f"By category: {dict(totals)}")
    print(f"By priority: {dict(by_priority)}")
    print("\nTop 20 offenders (priority-sorted):")
    for r in out["violations"][:20]:
        print(f"  [{r['priority']}] {r['file']:70s} {r['counts']}")
    print("\nFull report → /tmp/v2_theme_audit_v2.json")

    regression_count = 0
    if args.baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.exists():
            try:
                baseline = json.loads(baseline_path.read_text())
                baseline_rows = baseline.get("violations", []) if isinstance(baseline, dict) else []
                baseline_map = {
                    row.get("file"): row.get("counts", {})
                    for row in baseline_rows
                    if isinstance(row, dict) and row.get("file")
                }

                regressions = []
                for row in out["violations"]:
                    file_path = row.get("file")
                    counts = row.get("counts", {})
                    prev_counts = baseline_map.get(file_path, {})
                    for cat, now_count in counts.items():
                        prev_count = int(prev_counts.get(cat, 0))
                        if int(now_count) > prev_count:
                            regressions.append((file_path, cat, prev_count, int(now_count)))

                regression_count = len(regressions)
                if regressions:
                    print("\nTheme baseline regressions:")
                    for file_path, cat, prev_count, now_count in regressions[:40]:
                        print(f"  - {file_path} [{cat}] {prev_count} -> {now_count}")
                else:
                    print("\n✅ No theme baseline regressions detected.")
            except Exception as exc:
                print(f"\n⚠️ Unable to parse baseline file ({baseline_path}): {exc}")
        else:
            print(f"\n⚠️ Baseline file not found: {baseline_path}")

    if args.strict:
        p0 = by_priority.get("P0", 0)
        if p0 > args.budget:
            print(f"\n❌ STRICT FAIL — {p0} P0 violations exceed budget of {args.budget}.")
            return 1
        print(f"\n✅ STRICT PASS — P0 violations: {p0} ≤ budget {args.budget}.")

    if args.fail_on_new and args.baseline and regression_count > 0:
        print(f"\n❌ REGRESSION FAIL — {regression_count} theme baseline regressions detected.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
