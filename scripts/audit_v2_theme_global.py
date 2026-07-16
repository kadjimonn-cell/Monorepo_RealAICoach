#!/usr/bin/env python3
"""Deep, GLOBAL V2-theme audit — scans every .tsx file in /app/frontend
(app/** AND src/**), detects every pattern that bypasses the V2 theme,
and prints a ranked list so we can triage + fix.

Detection categories:
  A. module_palette         — module-scope `const/let <name> = { ...hex... }`
  B. inline_dark_bg         — `backgroundColor: '#0XXXXX|#1XXXXX|#2XXXXX'`
  C. inline_light_bg        — `backgroundColor: '#FXXXXX|'white''` on admin
  D. inline_dark_text_on_dark — `color: '#0XXXXX|#1XXXXX|#2XXXXX'` (probable
                                dark-text locked to dark-only theme)
  E. inline_light_text_on_light — `color: '#FXXXXX|'white''` (light-locked)
  F. inline_solid_text      — any solid-hex `color:` that isn't a semantic var
  G. inline_solid_border    — solid-hex `borderColor:`
  H. missing_hook           — file renders <View>/<Text> but never imports
                                any theme hook AND has hex literals
  I. bypass_colorscheme     — direct `useColorScheme()` outside ThemeContext
  J. darkmode_hex_ternary   — `darkMode ? '#xxx' : '#yyy'` / `isDark ? ...`
  K. stale_css_var          — `var(--app-<unknown>)` where the var isn't
                                injected by ThemeContext
  L. hardcoded_shadow       — `shadowColor: '#XXX'` / `tintColor: '#XXX'`
                                (semantic non-css color keys)

Writes: /tmp/v2_theme_audit_global.json
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/app/frontend")
SCAN_DIRS = [ROOT / "app", ROOT / "src"]

# CSS vars actually INJECTED by ThemeContext (post-fix). Anything else in a
# `var(--app-X)` reference is stale and won't theme-flip.
INJECTED_VARS = {
    "bg", "card-bg", "text", "text-sec", "text-muted", "border", "primary",
    "primary-text", "primary-soft", "surface", "success", "success-soft",
    "warning", "warning-soft", "error", "error-soft", "info", "info-soft",
    "surface-hover", "card-muted", "border-strong", "border-bright", "divider",
    "chart-grid", "chart-axis",
}

_DARK_HEX  = r"#(?:0[0-9A-Fa-f]|1[0-9A-Fa-f]|2[0-9A-Fa-f])[0-9A-Fa-f]{3}"
_LIGHT_HEX = r"#(?:F[0-9A-Fa-f]|E[89A-Fa-f]|D[CDE])[0-9A-Fa-f]{3}"
_SOLID_HEX = r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])"

RE_MODULE_PALETTE = re.compile(
    r"^\s*(?:const|let)\s+(?:C|T|AC|theme|Palette|colors?|PALETTE|tokens?)\s*=\s*\{[^{}]*?\b(?:bg|card|surface)\s*:\s*['\"]"
    + _DARK_HEX + r"['\"]",
    re.MULTILINE,
)
RE_INLINE_DARK_BG  = re.compile(r"backgroundColor:\s*['\"]" + _DARK_HEX + r"['\"]")
RE_INLINE_LIGHT_BG = re.compile(r"backgroundColor:\s*['\"](?:" + _LIGHT_HEX + r"|white|#FFF(?:FFF)?)['\"]")
RE_INLINE_DARK_TEXT  = re.compile(r"\bcolor:\s*['\"]" + _DARK_HEX + r"['\"]")
RE_INLINE_LIGHT_TEXT = re.compile(r"\bcolor:\s*['\"](?:" + _LIGHT_HEX + r"|#FFF(?:FFF)?|white)['\"]")
RE_INLINE_SOLID_TEXT   = re.compile(r"\bcolor:\s*['\"]" + _SOLID_HEX + r"['\"]")
RE_INLINE_SOLID_BORDER = re.compile(r"borderColor:\s*['\"]" + _SOLID_HEX + r"['\"]")
RE_DARKMODE_HEX_TERNARY = re.compile(
    r"\b(?:darkMode|isDark|dark|themeMode\s*===\s*['\"]dark['\"])\s*\?\s*['\"]#[0-9A-Fa-f]{3,8}['\"]"
)
RE_USECOLORSCHEME = re.compile(r"\buseColorScheme\s*\(\s*\)")
RE_HAS_THEME_HOOK = re.compile(r"\b(useTheme|useAdminTheme|useThemeMode|useExecTheme)\b")
RE_HAS_UI = re.compile(
    r"from\s+['\"]react-native['\"][^;]*\{[^}]*\b(?:View|Text|ScrollView|Pressable|TouchableOpacity|FlatList)\b",
    re.DOTALL,
)

# M. Semantic token misuse — `text: <bg-token>` or `border: <text-token>`.
#
# This catches the Notifications-page class of bug where a local palette
# object did  `text: darkMode ? C.bg : C.cardMuted` — both values are
# BACKGROUND tokens, making the headline numbers render as invisible ghost
# text on both themes even though the values are formally V2-tokened.
#
# The regex requires:
#   - assignment key is one of the TEXT semantic roles (text / title / label)
#   - value references one of the BACKGROUND semantic roles
# on the same line.
RE_SEMANTIC_MISUSE_TEXT = re.compile(
    r"(?:^|[\{\(,])[ \t]*(?:text|textPrimary|textTitle|title|headline|label|fg|color)\s*:\s*"
    r"[^,;\n\}\)>]*?\b(?:C|colors?|AC|T|tokens?)\.("
    r"bg|bgSoft|bgAlt|card|cardMuted|cardHover|cardBg|"
    r"surface|surfaceMuted|surfaceHover|surfaceAlt|background|backgroundMuted|"
    r"border|borderSoft|borderLight|divider"
    r")\b",
    re.MULTILINE,
)
# N. Reversed misuse — `border: <text-token>` / `border: <muted-text-token>`
# (the Notifications page did `border: darkMode ? "#23314A" : C.textDim`).
RE_SEMANTIC_MISUSE_BORDER = re.compile(
    r"(?:^|[\{\(,])[ \t]*border(?:Color)?\s*:\s*[^,;\n\}\)>]*?\b(?:C|colors?|AC|T|tokens?)\.("
    r"text|textPrimary|textSec|textSecondary|textMuted|textDim|textDisabled"
    r")\b",
    re.MULTILINE,
)
RE_EXEMPT = re.compile(r"@theme-(audit-file-ok|v2-exempt|ok\b)")
RE_CSS_VAR_REF = re.compile(r"var\(\s*--app-([a-z-]+)")
RE_SHADOW = re.compile(r"\b(?:shadowColor|tintColor|trackColor|thumbColor|rippleColor):\s*['\"]" + _SOLID_HEX + r"['\"]")
RE_SAME_FG_BG = re.compile(r"backgroundColor\s*:\s*([^,\n}]+),\s*color\s*:\s*([^,\n}]+)")
RE_SOFT_TOKEN_TEXT = re.compile(
    r"<Text[^\n]*\bcolor:\s*(?:"
    r"(?:colors?|C|AC|T|tokens?)\."
    r"(?:primarySoft|successSoft|errorSoft|warningSoft|infoSoft|accentSoft|blueSoft|purpleSoft|indigoSoft|orangeSoft)"
    r")",
)
RE_MODULE_GETADMIN_TRUE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*getAdminColors\s*\(\s*true\s*\)",
    re.MULTILINE,
)
RE_MAKET_AC_FN = re.compile(
    r"function\s+makeT\s*\(\s*AC\b[^)]*\)\s*\{",
    re.MULTILINE,
)


def _extract_brace_block(src: str, open_brace_idx: int) -> str:
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


def priority(path: Path) -> str:
    rel = str(path.relative_to(ROOT))
    # P0: admin/exec surfaces + top-level routes
    if (rel.startswith("src/components/admin/") or
        rel.startswith("src/components/operations-console/") or
        rel.startswith("src/components/executive-dashboard/") or
        rel.startswith("src/components/executive/")):
        return "P0"
    if rel.startswith("app/admin/") or rel.startswith("app/executive"):
        return "P0"
    # P1: user-facing pages
    if rel.startswith("app/") and not any(rel.startswith(f"app/{skip}") for skip in ("legal/", "debug/", "dev/")):
        return "P1"
    if rel.startswith("src/components/pages/") or rel.startswith("src/components/settings/"):
        return "P1"
    return "P2"


def scan_file(path: Path) -> dict:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    counts: Counter = Counter()
    samples: list[dict] = []

    def add(cat: str, m: re.Match, *, extra: str = "") -> None:
        counts[cat] += 1
        if len([s for s in samples if s["category"] == cat]) < 3:
            line = src[: m.start()].count("\n") + 1
            excerpt = src.splitlines()[line - 1].strip()[:180]
            samples.append({"category": cat, "line": line, "excerpt": excerpt, "extra": extra})

    exempt_whole_file = bool(RE_EXEMPT.search(src[:500]))

    # Only explicitly-scoped @theme-ok markers are honored; generic markers
    # should no longer suppress runtime theme violations.
    ALLOWED_THEME_OK_TAGS = (
        "html-export-fixed-palette",
        "always-dark emergency",
        "css-var-fallback",
        "dep-array-fingerprint",
        "fixed-dark-canvas",
        "brand-fixed-palette",
        "deliberate-high-contrast",
    )
    lines_with_theme_ok = set()
    for line_no, line in enumerate(src.splitlines(), start=1):
        if "@theme-ok" in line and any(tag in line for tag in ALLOWED_THEME_OK_TAGS):
            lines_with_theme_ok.add(line_no)

    def line_of(m: re.Match) -> int:
        return src[: m.start()].count("\n") + 1

    # A. module palette
    # Always-on structural checks (must run even if the file is exempt)
    for m in RE_MODULE_GETADMIN_TRUE.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("darklock_getadmin_true", m)
    for m in RE_MAKET_AC_FN.finditer(src):
        open_brace_idx = src.find("{", m.end() - 1)
        body = _extract_brace_block(src, open_brace_idx)
        if body and not re.search(r"\bAC(?:\.|\s*\[)", body):
            if line_of(m) not in lines_with_theme_ok:
                add("darklock_makeT_ignores_ac", m)

    if exempt_whole_file:
        counts["file_exempt_marker"] += 1
        samples.append({
            "category": "file_exempt_marker",
            "line": 1,
            "excerpt": "@theme-audit-file-ok present — file scanned in report mode (not skipped)",
        })

    for m in RE_MODULE_PALETTE.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("module_palette", m)
    # B-F
    for m in RE_INLINE_DARK_BG.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_dark_bg", m)
    for m in RE_INLINE_LIGHT_BG.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_light_bg", m)
    for m in RE_INLINE_DARK_TEXT.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_dark_text", m)
    for m in RE_INLINE_LIGHT_TEXT.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_light_text", m)
    for m in RE_INLINE_SOLID_TEXT.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_solid_text", m)
    for m in RE_INLINE_SOLID_BORDER.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("inline_solid_border", m)
    # H. missing hook
    if RE_HAS_UI.search(src) and not RE_HAS_THEME_HOOK.search(src):
        # Only flag if the file also has hex color literals (empty/pure helpers are fine)
        if re.search(_SOLID_HEX, src):
            counts["missing_hook"] += 1
            samples.append({"category": "missing_hook", "line": 1, "excerpt": "no theme hook imported yet renders UI with hex colors"})
    # I. bypass_colorscheme (except in ThemeContext itself)
    if "ThemeContext" not in str(path.name):
        for m in RE_USECOLORSCHEME.finditer(src):
            add("bypass_colorscheme", m)
    # J. darkmode hex ternary
    for m in RE_DARKMODE_HEX_TERNARY.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("darkmode_hex_ternary", m)
    # K. stale css var
    for m in RE_CSS_VAR_REF.finditer(src):
        var_name = m.group(1)
        if var_name not in INJECTED_VARS:
            if line_of(m) not in lines_with_theme_ok:
                add("stale_css_var", m, extra=var_name)
    # L. shadow
    for m in RE_SHADOW.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("hardcoded_shadow", m)
    # O. soft tone token used as text color on Text components
    for m in RE_SOFT_TOKEN_TEXT.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("soft_token_text_color", m)
    # P. identical fg/bg expression (common invisible-text regression)
    for m in RE_SAME_FG_BG.finditer(src):
        fg_expr = re.sub(r"\s+", "", m.group(2) or "")
        bg_expr = re.sub(r"\s+", "", m.group(1) or "")
        if fg_expr and bg_expr and fg_expr == bg_expr and line_of(m) not in lines_with_theme_ok:
            add("same_fg_bg_expression", m, extra=fg_expr)
    # M. semantic token misuse — text: <bg-token>
    for m in RE_SEMANTIC_MISUSE_TEXT.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("semantic_misuse_text", m, extra=m.group(1))
    # N. semantic token misuse — border: <text-token>
    for m in RE_SEMANTIC_MISUSE_BORDER.finditer(src):
        if line_of(m) not in lines_with_theme_ok:
            add("semantic_misuse_border", m, extra=m.group(1))

    return {
        "file": str(path.relative_to(ROOT)),
        "priority": priority(path),
        "counts": dict(counts),
        "samples": samples,
        "exempt": exempt_whole_file,
    }


def main():
    results = []
    files_scanned = 0
    for base in SCAN_DIRS:
        for path in base.rglob("*.tsx"):
            if "node_modules" in path.parts or ".expo" in path.parts:
                continue
            files_scanned += 1
            row = scan_file(path)
            if row and row.get("counts"):
                results.append(row)

    by_cat = Counter()
    by_pri = Counter()
    for r in results:
        for k, v in r["counts"].items():
            by_cat[k] += v
        by_pri[r["priority"]] += 1

    out = {
        "files_scanned": files_scanned,
        "files_with_violations": len(results),
        "violations_by_category": dict(by_cat),
        "files_by_priority": dict(by_pri),
        "violations": sorted(results, key=lambda x: (-sum(x["counts"].values()), x["priority"])),
    }
    Path("/tmp/v2_theme_audit_global.json").write_text(json.dumps(out, indent=2))

    print(f"Files scanned:        {files_scanned}")
    print(f"Files w/ violations:  {len(results)}")
    print(f"By category: {dict(by_cat)}")
    print(f"By priority: {dict(by_pri)}\n")
    print("Top 30 offenders (sum-of-violations desc):")
    for r in out["violations"][:30]:
        print(f"  [{r['priority']}] {r['file']:75s} {r['counts']}")
    print("\nFull report → /tmp/v2_theme_audit_global.json")


if __name__ == "__main__":
    main()
