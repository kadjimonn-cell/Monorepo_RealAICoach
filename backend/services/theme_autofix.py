"""Theme Autofix Service — applies the V2 Teal hex→token transform that was
pioneered in the Home/admin cleanup batches.

Scope rules:
  - Only files under /app/frontend/app/ and /app/frontend/src/ (prevents traversal)
  - Only .tsx / .ts / .jsx / .js files
  - Only `color:`, `backgroundColor:`, `borderColor:` style-attr string literals
  - Leaves template literals, comments, CSS backticks, and rgba() alone
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Tuple

FRONTEND_ROOT = Path("/app/frontend").resolve()
ALLOWED_SUBDIRS = ("app", "src")
ALLOWED_SUFFIXES = (".tsx", ".ts", ".jsx", ".js")

# Map literal hex codes -> V2 colors.* tokens. Keep in sync with
# `src/components/home/HomeHero.tsx` + `src/theme/v2.ts`.
EXACT_MAP: dict[str, str] = {
    # Brand teal family
    "#0F766E": "colors.primary",
    "#14B8A6": "colors.accent",
    "#10B981": "colors.success",
    "#059669": "colors.success",
    # Alerts / semantics
    "#EF4444": "colors.error",
    "#DC2626": "colors.error",
    "#F59E0B": "colors.warning",
    "#F97316": "colors.warning",
    # Neutrals
    "#9CA3AF": "colors.textMuted",
    "#64748B": "colors.textMuted",
    "#94A3B8": "colors.textMuted",
    "#CBD5E1": "colors.textSecondary",
    "#475569": "colors.textSecondary",
    "#F9FAFB": "colors.text",
    "#F1F5F9": "colors.text",
    "#FEFEFE": "colors.primaryText",
    "#FFFFFF": "colors.primaryText",
    "#FAFAFA": "colors.bgSoft",
    "#0F172A": "colors.card",
    "#1E293B": "colors.border",
    "#0A0A0A": "colors.text",
}

# Low-alpha variants (e.g. "#10B98115") collapse to the matching *Soft token.
ALPHA_BASE: dict[str, str] = {
    "#0F766E": "colors.primarySoft",
    "#14B8A6": "colors.accentSoft",
    "#10B981": "colors.successSoft",
    "#059669": "colors.successSoft",
    "#EF4444": "colors.errorSoft",
    "#DC2626": "colors.errorSoft",
    "#F59E0B": "colors.warningSoft",
    "#F97316": "colors.warningSoft",
}

SOFT_ALPHA_VALUES = frozenset({"08", "10", "12", "15", "16", "18", "20", "24"})
ATTRS = ("color", "backgroundColor", "borderColor")


# ─────────────────────────────────────────────────────────────────────────────
# Transform dialects — some files in the codebase use a theme accessor named
# `C` instead of `colors`, with the same OR a different key namespace (e.g.
# email-templates use `C.blue` for primary). We detect the right dialect per
# file and rewrite hex → `{target_symbol}.{key}` accordingly.
# ─────────────────────────────────────────────────────────────────────────────

# Shorthand token keys, stripped of any symbol prefix (e.g. "colors.primary"
# → "primary"). Used as the canonical token names that the default `colors`
# dialect emits; alternate dialects remap these to their own accessor keys.
def _strip_prefix(val: str) -> str:
    return val.split(".", 1)[1] if "." in val else val


# Dialect: standard V2 Teal accessor `colors.X`
_STD_EXACT: dict[str, str] = {h: _strip_prefix(v) for h, v in EXACT_MAP.items()}
_STD_ALPHA: dict[str, str] = {h: _strip_prefix(v) for h, v in ALPHA_BASE.items()}

# Dialect: help-section `C` prop typed as `ThemeColors` (same keys as standard)
# — literally the same key set as `colors`, just on `C`.
_CHELP_EXACT = dict(_STD_EXACT)
_CHELP_ALPHA = dict(_STD_ALPHA)

# Dialect: email-template `C` from `./shared` (see src/components/admin/
# email-templates/shared.tsx — maps AdminColors to template palette with
# blue/green/amber/red/teal/pink/indigo/purple aliases).
_CEMAIL_EXACT: dict[str, str] = {
    "#0F766E": "blue",   # primary
    "#14B8A6": "teal",   # accent (info alias in template dialect)
    "#10B981": "green",  # success
    "#059669": "green",
    "#EF4444": "red",
    "#DC2626": "red",
    "#F59E0B": "amber",  # warning
    "#F97316": "amber",
    "#64748B": "muted",
    "#9CA3AF": "muted",
    "#1E293B": "border",
    "#0F172A": "card",
}
# email-template dialect has no explicit `Soft` variants — drop alpha to
# suppress the soft-collapse path and keep `C.X + 'AA'` instead.
_CEMAIL_ALPHA: dict[str, str] = {}


class TransformDialect:
    """Bundle of (target_symbol, exact_map, alpha_map) the rewrite uses.

    `target_symbol` is the identifier on the left side of each rewritten
    access (`colors`, `C`, etc.). `exact` / `alpha` are the hex → key maps
    for bare and low-alpha literals respectively.
    """

    __slots__ = ("target_symbol", "exact", "alpha", "name")

    def __init__(self, name: str, target_symbol: str, exact: dict[str, str], alpha: dict[str, str]):
        self.name = name
        self.target_symbol = target_symbol
        self.exact = exact
        self.alpha = alpha

    def exact_expr(self, hex_upper: str) -> str | None:
        key = self.exact.get(hex_upper)
        return f"{self.target_symbol}.{key}" if key else None

    def soft_expr(self, hex_upper: str) -> str | None:
        key = self.alpha.get(hex_upper)
        return f"{self.target_symbol}.{key}" if key else None


DIALECT_STANDARD = TransformDialect("standard", "colors", _STD_EXACT, _STD_ALPHA)
DIALECT_C_HELP = TransformDialect("C-help", "C", _CHELP_EXACT, _CHELP_ALPHA)
DIALECT_C_EMAIL = TransformDialect("C-email", "C", _CEMAIL_EXACT, _CEMAIL_ALPHA)


def detect_dialect(src: str, rel_path: str) -> TransformDialect:
    """Pick the right transform dialect based on file imports / prop types.

    Detection order (most specific first):
      1. File is under `src/components/admin/email-templates/` OR imports
         `C` from `./shared` inside that tree → `DIALECT_C_EMAIL`.
      2. File declares `C: ThemeColors` prop (help-section convention)
         → `DIALECT_C_HELP`.
      3. Fallback → `DIALECT_STANDARD` (`colors.X`).
    """
    rel_posix = rel_path.replace("\\", "/")
    if "src/components/admin/email-templates/" in rel_posix or re.search(
        r"from\s+['\"]\.\./?.*email-templates/shared['\"]", src
    ):
        return DIALECT_C_EMAIL
    # Help-section prop shape: `C: ThemeColors` or `C,\s*...:\s*ThemeColors`
    if re.search(r"\bC\s*:\s*ThemeColors\b", src):
        return DIALECT_C_HELP
    return DIALECT_STANDARD


class AutofixError(ValueError):
    """Raised when the caller provides an invalid or out-of-scope path."""


# Files that look like React but don't actually mount inside the ThemeProvider,
# so `colors.*` references would ReferenceError at runtime.
# Kept as relative POSIX paths from frontend root.
BLOCKLISTED_PATHS = frozenset({
    "app/+html.tsx",
    "app/+not-found.tsx",
    "app/_layout.tsx",  # may exist; safer to block (it's the root layout shell)
    # Multi-line inline type-annotation function signature that the injector
    # can't reliably parse (e.g. `}: {\n  visible: boolean; ...\n}) {`).
    "src/components/branding/EnterpriseMotionOverlay.tsx",
    # Rendered OUTSIDE ThemeProvider — cannot resolve `useTheme()` at runtime.
    "src/components/accessibility/SkipToContent.tsx",
    # Files the autofix transform replaces hex→colors.X inside component bodies
    # that use a different color source (e.g. `C` prop, `getAdminColors`,
    # `getWelcomeLegacyColors`) instead of `useTheme`. Standard autofix can't
    # reliably inject useTheme here without breaking the existing color API.
    "app/auth/qr-approve.tsx",
    "app/welcome.tsx",
    "src/components/admin/email-templates/AnalyticsView.tsx",
    "src/components/admin/email-templates/DeliverabilityView.tsx",
    "src/components/admin/session-management/AlertsPanel.tsx",
    "src/components/hiring/PipelineTab.tsx",
    "src/components/welcome/WelcomeHero.tsx",
})


def _validate_path(rel_or_abs: str) -> Path:
    """Resolve a caller-supplied path and refuse anything outside frontend/app|src."""
    if not rel_or_abs or not isinstance(rel_or_abs, str):
        raise AutofixError("path is required")
    # Normalise: accept both "src/components/Foo.tsx" and "/app/frontend/src/..."
    p = Path(rel_or_abs)
    if not p.is_absolute():
        p = FRONTEND_ROOT / rel_or_abs.lstrip("/")
    p = p.resolve()

    try:
        rel = p.relative_to(FRONTEND_ROOT)
    except ValueError as e:
        raise AutofixError(f"path must be under {FRONTEND_ROOT}") from e

    parts = rel.parts
    if not parts or parts[0] not in ALLOWED_SUBDIRS:
        raise AutofixError(
            f"path must be under frontend/app/ or frontend/src/, got {rel}"
        )
    if p.suffix not in ALLOWED_SUFFIXES:
        raise AutofixError(
            f"only {ALLOWED_SUFFIXES} files supported, got {p.suffix}"
        )
    if not p.is_file():
        raise AutofixError(f"file not found: {rel}")
    rel_str = str(rel).replace("\\", "/")
    if rel_str in BLOCKLISTED_PATHS:
        raise AutofixError(
            f"file is blocklisted from autofix (SSR/static template): {rel_str}"
        )
    return p


def _transform_line(line: str, dialect: TransformDialect = DIALECT_STANDARD) -> Tuple[str, int]:
    count = 0
    new = line

    # ── Pattern 2 FIRST (runs before the bare-literal pattern so we capture
    # the full concat before the bare-hex regex would swallow only the hex
    # portion): `'#XXXXXX' + 'AA'` string-concat alpha ANYWHERE in the line.
    # Collapses to {symbol}.{X}Soft when alpha ∈ SOFT_ALPHA_VALUES, else
    # becomes `{symbol}.X + 'AA'`.
    concat_pat = re.compile(
        r"(['\"])(#[0-9A-Fa-f]{6})\1\s*\+\s*(['\"])([0-9A-Fa-f]{2})\3"
    )

    def _sub_concat(m: re.Match) -> str:
        nonlocal count
        base = m.group(2).upper()
        alpha = m.group(4)
        if alpha.lower() in SOFT_ALPHA_VALUES:
            soft = dialect.soft_expr(base)
            if soft:
                count += 1
                return soft
        exact = dialect.exact_expr(base)
        if exact:
            count += 1
            return f"{exact} + '{alpha}'"
        return m.group(0)

    new = concat_pat.sub(_sub_concat, new)

    for attr in ATTRS:
        # ── Pattern 1: `attr: '#XXXXXX'` or `attr: '#XXXXXXAA'` (bare literal)
        pat = re.compile(
            rf"(?<![a-zA-Z]){attr}:\s*(['\"])(#[0-9A-Fa-f]{{6}})([0-9A-Fa-f]{{2}})?\1"
        )

        def _sub(m: re.Match) -> str:
            nonlocal count
            base = m.group(2).upper()
            alpha = m.group(3)
            if alpha and alpha.lower() in SOFT_ALPHA_VALUES:
                soft = dialect.soft_expr(base)
                if soft:
                    count += 1
                    return f"{attr}: {soft}"
            exact = dialect.exact_expr(base)
            if exact:
                count += 1
                if alpha:
                    return f"{attr}: {exact} + '{alpha}'"
                return f"{attr}: {exact}"
            return m.group(0)

        new = pat.sub(_sub, new)

    # ── Pattern 3: bare `'#HEX'` or `'#HEXAA'` ANYWHERE on a line that is
    # clearly a style context (the line contains one of the known ATTRS
    # followed by `:`). Catches ternary patterns that pattern 1 can't, e.g.:
    #   color: active ? '#10B981' : C.muted
    #   backgroundColor: isOk ? '#10B981' : '#EF4444'
    #   borderColor: [isFoo && '#10B981', base]
    # Gate: the "style-context" sniff prevents false positives on hex
    # literals in JSDoc, string constants, or non-style assignments.
    # Extra guard: skip comment lines (JSDoc `*` or `//`) where prose can
    # include phrasings like "hex color: '#0F766E'" that shouldn't match.
    stripped = new.lstrip()
    is_comment = stripped.startswith("*") or stripped.startswith("//")
    attr_prefix_re = re.compile(
        r"(?<![a-zA-Z])(?:" + "|".join(ATTRS) + r"):"
    )
    if not is_comment and attr_prefix_re.search(new):
        bare_pat = re.compile(
            r"(?<![.\w])(['\"])(#[0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?\1"
        )

        def _sub_bare(m: re.Match) -> str:
            nonlocal count
            base = m.group(2).upper()
            alpha = m.group(3)
            if alpha and alpha.lower() in SOFT_ALPHA_VALUES:
                soft = dialect.soft_expr(base)
                if soft:
                    count += 1
                    return soft
            exact = dialect.exact_expr(base)
            if exact:
                count += 1
                if alpha:
                    return f"{exact} + '{alpha}'"
                return exact
            return m.group(0)

        new = bare_pat.sub(_sub_bare, new)

    return new, count


def transform_source(src: str, *, rel_path: str = "") -> Tuple[str, int]:
    """Transform a source string. Returns (new_src, replacement_count).

    Picks the right dialect automatically via `detect_dialect(src, rel_path)`
    so files using `C.primary` (help-section) or `C.blue` (email-template)
    are rewritten on their own accessor instead of `colors.X`.
    """
    dialect = detect_dialect(src, rel_path)
    out_lines: list[str] = []
    total = 0
    for ln in src.splitlines(keepends=True):
        new_ln, n = _transform_line(ln, dialect)
        total += n
        out_lines.append(new_ln)
    return "".join(out_lines), total


def _detect_risky_edits(original: str, transformed: str) -> list[dict]:
    """Detect likely-unsafe edits — changes to lines that appear to sit inside
    module-level `const`/`let`/`var` declarations (i.e. outside any function or
    React component body). Such edits will produce `ReferenceError: colors is
    not defined` at module load because `colors` only exists inside components.

    Heuristic: walk the original source line-by-line. Track whether we are
    currently inside a top-level declaration block by following brace depth
    starting from any line that matches `^\s*(export\s+)?(const|let|var)\b`
    at indent 0–2. If a changed line falls inside such a block, flag it.
    """
    risky: list[dict] = []
    orig_lines = original.splitlines()
    trans_lines = transformed.splitlines()

    # Build set of changed 1-indexed line numbers
    changed_lines: set[int] = set()
    for i, (o, t) in enumerate(zip(orig_lines, trans_lines), start=1):
        if o != t:
            changed_lines.add(i)

    # Track module-level brace depth
    in_module_const = False
    brace_depth = 0
    module_const_start = 0
    module_const_name = ""

    decl_re = re.compile(r"^(export\s+)?(const|let|var)\s+([A-Za-z_][\w]*)")
    fn_re = re.compile(r"\b(function|=>\s*\{|React\.(memo|forwardRef)\()")

    for i, line in enumerate(orig_lines, start=1):
        # If a function/arrow starts on this line, we leave module-const tracking
        if in_module_const and fn_re.search(line):
            # Arrow inside const like `const X = () => { ... }` — safe, not module-level static
            in_module_const = False
            brace_depth = 0
            continue

        if not in_module_const:
            m = decl_re.match(line)
            if m and (("{" in line) or ("[" in line) or line.rstrip().endswith("=")):
                in_module_const = True
                module_const_start = i
                module_const_name = m.group(3)
                brace_depth = line.count("{") - line.count("}") + line.count("[") - line.count("]")
                # Check if the decl is fully on one line (closed immediately)
                if brace_depth <= 0 and (";" in line or line.rstrip().endswith(",")):
                    in_module_const = False
                    brace_depth = 0
                continue

        if in_module_const:
            brace_depth += line.count("{") - line.count("}")
            brace_depth += line.count("[") - line.count("]")
            if i in changed_lines:
                risky.append({
                    "line": i,
                    "const_name": module_const_name,
                    "decl_line": module_const_start,
                    "code": line.strip()[:160],
                })
            if brace_depth <= 0:
                in_module_const = False
                brace_depth = 0

    return risky


def _find_component_injection_point(src: str) -> dict | None:
    """Locate the first `export default function|export function` in the source.

    Returns a dict with:
      - func_start_line (1-indexed)
      - brace_line (line containing the opening `{` of the function body)
      - inject_line (line AFTER which we inject — right after any existing
        `colors` declaration if present, else right after useTheme() if present,
        else right after the opening brace)
      - has_colors_in_scope (bool) — whether `colors` is already available
        inside the component (via prop destructuring, useTheme(), useAdminTheme(),
        or a `const colors = ...` declaration)
      - needs_use_theme_injection (bool) — whether we need to inject
        `const { colors } = useTheme();` AND add the import
    """
    lines = src.splitlines()

    func_re = re.compile(
        r"^(export\s+default\s+function|export\s+function)\s+([A-Za-z_][\w]*)\s*\("
    )
    func_start = -1
    func_name = None
    for i, ln in enumerate(lines):
        m = func_re.match(ln)
        if m:
            func_start = i
            func_name = m.group(2)
            break
    if func_start < 0:
        return None

    # Find the opening body `{` by walking forward tracking paren depth so we
    # skip any `{` that appears inside an inline type annotation / destructure
    # (e.g. `}: {\n  visible: boolean;\n})`). The body `{` is the first `{`
    # that appears AFTER paren depth has returned to 0 (i.e. after the `)`
    # that closes the arg list).
    brace_line = -1
    signature_text_parts: list[str] = []
    paren_depth = 0
    seen_open_paren = False
    for j in range(func_start, min(func_start + 40, len(lines))):
        signature_text_parts.append(lines[j])
        ln = lines[j]
        # Scan char by char (ignoring strings/comments is overkill here —
        # React component signatures don't contain string/comment parens).
        for ch in ln:
            if ch == "(":
                paren_depth += 1
                seen_open_paren = True
            elif ch == ")":
                if paren_depth > 0:
                    paren_depth -= 1
            elif ch == "{" and seen_open_paren and paren_depth == 0:
                brace_line = j
                break
        if brace_line >= 0:
            break
    if brace_line < 0:
        return None

    signature_text = "\n".join(signature_text_parts)
    # Does the prop signature destructure `colors`? Detect `{ colors }` or
    # `{ colors:` (but NOT `{ colors: _colors }` — renamed means NOT available)
    # and NOT `colors?: ...` inside a type annotation outside the destructure.
    has_colors_from_props = bool(
        re.search(r"\{\s*[^{}]*\bcolors\b(?!\s*:\s*_)[^{}]*\}", signature_text)
    )

    # Scan body (up to ~60 lines) for existing `colors` resolution:
    # - const { colors } = useTheme();
    # - const colors = useAdminTheme();
    # - const { colors, ... } = anything
    # - const colors = anything
    resolve_line = -1
    resolve_patterns = [
        re.compile(r"^\s*const\s+\{\s*[^{}]*\bcolors\b[^{}]*\}\s*=\s*useTheme\s*\(\s*\)"),
        re.compile(r"^\s*const\s+colors\s*=\s*useAdminTheme\s*\(\s*\)"),
        re.compile(r"^\s*const\s+colors\s*=\s*useTheme\s*\(\s*\)"),
        re.compile(r"^\s*const\s+\{\s*[^{}]*\bcolors\b[^{}]*\}\s*=\s*useTheme"),
        re.compile(r"^\s*const\s+colors\s*=\s*"),
        re.compile(r"^\s*const\s+\{\s*[^{}]*\bcolors\b[^{}]*\}\s*="),
    ]
    use_theme_pat = re.compile(r"useTheme\s*\(\s*\)")
    has_use_theme_call = False
    for k in range(brace_line, min(brace_line + 60, len(lines))):
        if use_theme_pat.search(lines[k]):
            has_use_theme_call = True
        for rp in resolve_patterns:
            if rp.search(lines[k]):
                resolve_line = k
                break
        if resolve_line >= 0:
            break

    has_use_theme_import = bool(
        re.search(
            r"\buseTheme\b.*from\s+['\"][^'\"]*ThemeContext['\"]",
            "\n".join(lines[:func_start]),
        )
    )

    has_colors_in_scope = has_colors_from_props or (resolve_line >= 0)

    # Inject point: after resolve_line if found, else after brace_line
    inject_line = resolve_line if resolve_line >= 0 else brace_line

    # We only need to inject useTheme if NO `colors` source is available AND
    # useTheme isn't already called.
    needs_use_theme_injection = (not has_colors_in_scope) and (not has_use_theme_call)
    needs_import = needs_use_theme_injection and (not has_use_theme_import)

    return {
        "func_start_line": func_start + 1,
        "func_name": func_name,
        "brace_line": brace_line + 1,
        "inject_line": inject_line + 1,
        "has_colors_in_scope": has_colors_in_scope,
        "has_colors_from_props": has_colors_from_props,
        "resolve_line": resolve_line + 1 if resolve_line >= 0 else 0,
        "has_use_theme_call": has_use_theme_call,
        "has_use_theme_import": has_use_theme_import,
        "needs_use_theme_injection": needs_use_theme_injection,
        "needs_import": needs_import,
    }


def _extract_const_block(src_lines: list[str], decl_line_1idx: int) -> Tuple[int, int, str] | None:
    """Given the 1-indexed line of a `const NAME` declaration, find the full
    extent of that declaration (end line) by brace-matching. Returns
    (start_idx_0based, end_idx_0based_inclusive, block_text) or None.
    """
    start = decl_line_1idx - 1
    if start < 0 or start >= len(src_lines):
        return None
    decl = src_lines[start]
    # Refuse if exported
    if re.match(r"^\s*export\b", decl):
        return None

    # Brace-match from the first { or [ found in decl
    brace_depth = 0
    open_seen = False
    end = start
    for j in range(start, len(src_lines)):
        ln = src_lines[j]
        for ch in ln:
            if ch in "{[":
                brace_depth += 1
                open_seen = True
            elif ch in "}]":
                brace_depth -= 1
        if open_seen and brace_depth == 0:
            end = j
            break
    if not open_seen:
        return None
    block = "\n".join(src_lines[start : end + 1])
    return start, end, block


def transform_source_aggressive(src: str, *, rel_path: str | None = None) -> Tuple[str, dict]:
    """Aggressive transform: does the standard hex→token swap, AND moves risky
    module-level `const`s into the component body so that `colors` resolves.

    Returns (new_src, stats).
    stats = {
        'replacements': int (total hex→token swaps),
        'consts_moved': list[str] (names of consts relocated),
        'warnings': list[str] (skipped cases with reasons),
    }

    Safety rails:
      - Only moves consts that are NOT `export`ed
      - Only if the file has exactly one `export default function|export function`
      - If useTheme is missing, inserts `const { colors } = useTheme();` at the
        top of the component body AND adds the import
      - No-op if the injection target can't be found
    """
    stats = {"replacements": 0, "consts_moved": [], "warnings": []}

    # First do a normal transform to get the replacement count baseline
    transformed_standard, std_n = transform_source(src)

    # Detect risky edits on the original vs standard-transform
    risky = _detect_risky_edits(src, transformed_standard)
    if not risky:
        return transformed_standard, {**stats, "replacements": std_n}

    # Group risky edits by const name → decl line
    risky_by_const: dict[str, int] = {}
    for r in risky:
        if r["const_name"] not in risky_by_const:
            risky_by_const[r["const_name"]] = r["decl_line"]

    lines = src.splitlines()
    inj = _find_component_injection_point(src)
    if not inj:
        stats["warnings"].append(
            "No `export default function` or `export function` found — falling back to standard transform."
        )
        return transformed_standard, {**stats, "replacements": std_n}

    # Extract + move each risky const. We build a new source line list.
    # Track line indices to delete and blocks to inject (indexed by const_name).
    deletes: set[int] = set()
    injected_blocks: list[str] = []

    # We need to transform each const's contents with the hex→token transform.
    # The transformed contents will use `colors.primary` etc which will resolve
    # because we're about to place them inside the component body.

    for const_name, decl_line in risky_by_const.items():
        extracted = _extract_const_block(lines, decl_line)
        if not extracted:
            stats["warnings"].append(f"Could not extract const {const_name} at L{decl_line}")
            continue
        s, e, block = extracted
        # Transform the block
        transformed_block, n_block = transform_source(block)
        if n_block == 0:
            continue
        # Mark these lines for deletion from module scope
        for k in range(s, e + 1):
            deletes.add(k)
        injected_blocks.append(
            f"  // @autofix-moved: was module-level const {const_name}\n"
            + "  "
            + transformed_block.replace("\n", "\n  ")
        )
        stats["consts_moved"].append(const_name)
        stats["replacements"] += n_block

    if not injected_blocks:
        return transformed_standard, {**stats, "replacements": std_n}

    # Build the output line by line
    out: list[str] = []
    injected = False
    need_use_theme = inj["needs_use_theme_injection"]
    need_import = inj["needs_import"]

    for i, ln in enumerate(lines):
        if i in deletes:
            continue
        out.append(ln)
        # Inject right after the target line (inject_line is 1-indexed)
        if not injected and (i + 1) == inj["inject_line"]:
            if need_use_theme:
                out.append("  const { colors } = useTheme();")
            out.append("")
            for blk in injected_blocks:
                out.append(blk)
            injected = True

    # Handle import
    if need_import:
        # Insert after the last `import` line near the top
        last_import = -1
        for i, ln in enumerate(out[:80]):
            if re.match(r"^\s*import\s", ln):
                last_import = i
        # Compute the correct relative path from this file to src/context/ThemeContext
        if rel_path:
            import_stmt = f"import {{ useTheme }} from '{_relative_theme_import(rel_path)}';"
        else:
            # Fallback used only when caller didn't pass rel_path — emit a
            # project-absolute import via the TypeScript baseUrl. Best-effort.
            import_stmt = "import { useTheme } from 'src/context/ThemeContext';"
        if last_import >= 0:
            out.insert(last_import + 1, import_stmt)
        else:
            out.insert(0, import_stmt)

    # Apply the rest-of-file standard transform to anything outside the moved
    # consts. Simpler approach: run transform_source on the entire built output.
    final_src = "\n".join(out)
    final_transformed, final_n = transform_source(final_src)
    # Preserve trailing newline if original had one
    if src.endswith("\n") and not final_transformed.endswith("\n"):
        final_transformed += "\n"
    stats["replacements"] = max(stats["replacements"], final_n)
    return final_transformed, stats


def _scan_risky_in_source(src: str) -> list[dict]:
    """Scan a SINGLE source string for lines inside module-level const/let/var
    blocks that use `colors.xxx` references — those will ReferenceError at
    module load time. Used post-transform to verify aggressive mode's output.
    """
    risky: list[dict] = []
    lines = src.splitlines()
    in_module_const = False
    brace_depth = 0
    module_const_start = 0
    module_const_name = ""

    # Module-level declarations start at column 0 — anything indented is
    # inside a function/class body and therefore safe.
    decl_re = re.compile(r"^(export\s+)?(const|let|var)\s+([A-Za-z_][\w]*)")
    fn_re = re.compile(r"\b(function|=>\s*\{|React\.(memo|forwardRef)\()")
    colors_ref_re = re.compile(r"(?<![A-Za-z_])colors\.[A-Za-z_]\w*")

    for i, line in enumerate(lines, start=1):
        if in_module_const and fn_re.search(line):
            in_module_const = False
            brace_depth = 0
            continue

        if not in_module_const:
            m = decl_re.match(line)
            if m and (("{" in line) or ("[" in line) or line.rstrip().endswith("=")):
                in_module_const = True
                module_const_start = i
                module_const_name = m.group(3)
                brace_depth = line.count("{") - line.count("}") + line.count("[") - line.count("]")
                if brace_depth <= 0 and (";" in line or line.rstrip().endswith(",")):
                    in_module_const = False
                    brace_depth = 0
                continue

        if in_module_const:
            brace_depth += line.count("{") - line.count("}")
            brace_depth += line.count("[") - line.count("]")
            if colors_ref_re.search(line):
                risky.append({
                    "line": i,
                    "const_name": module_const_name,
                    "decl_line": module_const_start,
                    "code": line.strip()[:160],
                })
            if brace_depth <= 0:
                in_module_const = False
                brace_depth = 0

    return risky


def preview_file(rel_path: str, *, diff_context: int = 3, aggressive: bool = False) -> dict:
    """Return a dict with the unified diff, summary stats, and a risk report.
    Does NOT write the file.

    When `aggressive=True`, risky module-level consts are relocated into the
    component body so that `colors` resolves correctly — the result should pass
    the risk detector cleanly.
    """
    abs_path = _validate_path(rel_path)
    original = abs_path.read_text()
    if aggressive:
        transformed, stats = transform_source_aggressive(original, rel_path=rel_path)
        n = stats["replacements"]
        consts_moved = stats["consts_moved"]
        aggressive_warnings = stats["warnings"]
    else:
        transformed, n = transform_source(original)
        consts_moved = []
        aggressive_warnings = []

    if n == 0:
        return {
            "path": rel_path,
            "replacements": 0,
            "diff": "",
            "original_sha": _short_hash(original),
            "transformed_sha": _short_hash(original),
            "changed": False,
            "lines_changed": 0,
            "risky_edits": [],
            "requires_manual_review": False,
            "aggressive": aggressive,
            "consts_moved": consts_moved,
            "aggressive_warnings": aggressive_warnings,
        }

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        transformed.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        n=diff_context,
    )
    diff_text = "".join(diff)

    lines_changed = sum(
        1
        for ln in diff_text.splitlines()
        if (ln.startswith("+") and not ln.startswith("+++"))
        or (ln.startswith("-") and not ln.startswith("---"))
    )

    # Risk detection:
    # - non-aggressive: detect lines inside module-level consts that were
    #   changed from hex to `colors.*` (will error at module load)
    # - aggressive: scan the TRANSFORMED output for any remaining module-level
    #   `colors.*` references (should ideally be zero if we moved every risky const)
    if aggressive:
        risky = _scan_risky_in_source(transformed)
    else:
        risky = _detect_risky_edits(original, transformed)

    return {
        "path": rel_path,
        "replacements": n,
        "diff": diff_text,
        "original_sha": _short_hash(original),
        "transformed_sha": _short_hash(transformed),
        "changed": True,
        "lines_changed": lines_changed,
        "risky_edits": risky,
        "requires_manual_review": bool(risky),
        "aggressive": aggressive,
        "consts_moved": consts_moved,
        "aggressive_warnings": aggressive_warnings,
    }


def _has_symbol_scope_source(src: str, target_symbol: str) -> bool:
    """Return True if the source file has *some* mechanism for the named
    symbol (e.g. `colors`, `C`) to be resolvable at runtime. Covers hooks
    (useTheme, useAdminTheme, getAdminColors), local const declarations,
    imports from `./shared`, and typed prop destructures."""
    sym = re.escape(target_symbol)
    # A `C` prop typed as ThemeColors: `{ C }: Props` or `{ C, other }: ...: ThemeColors`
    patterns_common = [
        rf"\{{\s*[^{{}}]*\b{sym}\b[^{{}}]*\}}\s*:",   # prop destructure
        rf"^\s*(const|let|var)\s+{sym}\s*[=:]",        # local const assignment
        rf"import\s+[^;]*\b{sym}\b[^;]*from",          # named import
    ]
    if target_symbol == "colors":
        patterns_common += [
            r"useTheme\s*\(",
            r"useAdminTheme\s*\(",
            r"getAdminColors\s*\(",
            r"\{\s*[^}]*\bcolors\b[^}]*\}\s*=\s*(useTheme|useAdminTheme)\s*\(",
        ]
    return any(re.search(p, src, re.M) for p in patterns_common)


def _has_colors_scope_source(src: str) -> bool:
    """Back-compat alias: checks for `colors` scope specifically."""
    return _has_symbol_scope_source(src, "colors")


def apply_file(rel_path: str, *, expected_original_sha: str | None = None, aggressive: bool = False) -> dict:
    """Apply the transform atomically. Returns a result dict.

    When `expected_original_sha` is provided we verify the file hasn't changed
    since preview (optimistic lock). If it has, we return an error and do nothing.
    """
    abs_path = _validate_path(rel_path)
    original = abs_path.read_text()
    current_sha = _short_hash(original)

    if expected_original_sha and current_sha != expected_original_sha:
        return {
            "ok": False,
            "error": "file_changed_since_preview",
            "expected_sha": expected_original_sha,
            "actual_sha": current_sha,
        }

    if aggressive:
        transformed, stats = transform_source_aggressive(original, rel_path=rel_path)
        n = stats["replacements"]
    else:
        transformed, n = transform_source(original, rel_path=rel_path)
    if n == 0:
        return {
            "ok": True,
            "path": rel_path,
            "replacements": 0,
            "changed": False,
            "sha": current_sha,
        }

    # Scope-safety guard: if the transform produced `{symbol}.X` references
    # but the file has NO way to resolve that symbol at runtime (useTheme,
    # useAdminTheme, getAdminColors, prop destructure, local const, named
    # import), SKIP to avoid ReferenceError at module load.
    # Dialect-aware: picks the correct target symbol per file.
    dialect = detect_dialect(transformed, rel_path)
    tgt = dialect.target_symbol
    if re.search(rf"(?<![A-Za-z_]){re.escape(tgt)}\.[A-Za-z_]", transformed) and not _has_symbol_scope_source(transformed, tgt):
        return {
            "ok": True,
            "path": rel_path,
            "replacements": 0,
            "changed": False,
            "skipped": True,
            "skip_reason": f"no_{tgt}_scope_source",
            "requires_manual_review": True,
            "sha": current_sha,
        }

    # Write atomically: write to temp then rename
    tmp = abs_path.with_suffix(abs_path.suffix + ".autofix.tmp")
    tmp.write_text(transformed)
    os.replace(tmp, abs_path)

    return {
        "ok": True,
        "path": rel_path,
        "replacements": n,
        "changed": True,
        "original_sha": current_sha,
        "new_sha": _short_hash(transformed),
    }


def _short_hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _relative_theme_import(rel_path: str) -> str:
    """Compute the correct relative import path to `src/context/ThemeContext`
    from the given file.
    """
    import posixpath

    src_dir = posixpath.dirname(rel_path.replace("\\", "/")) or "."
    target = "src/context/ThemeContext"
    rel = posixpath.relpath(target, src_dir)
    # Ensure the path starts with ./ or ../ (ES import spec requires it)
    if not rel.startswith("."):
        rel = "./" + rel
    return rel


def batch_apply(paths: list[str], *, aggressive: bool = True) -> dict:
    """Apply the autofix to each path in sequence. Returns a per-file report
    plus aggregate stats.

    Per-file record:
      - path, ok, skipped (bool), skip_reason, replacements, sha_before, sha_after,
        consts_moved, requires_manual_review, error

    Halting rules:
      - An AutofixError on any file is recorded and batch continues (other files
        may still succeed).
      - Safe paths only (same _validate_path protection).

    This function does NOT run the frontend compile check. The caller is
    expected to optionally run `npx expo export` and, on failure, roll back.
    The caller is given a `backups` map (path → original content sha)
    so it can decide on rollback policy.
    """
    results: list[dict] = []
    backups: dict[str, str] = {}  # path → original content
    total_reps = 0

    for rel_path in paths:
        try:
            abs_path = _validate_path(rel_path)
            original = abs_path.read_text()
            backups[rel_path] = original
            # Preview first to know if it's worth doing and if it's safe
            prev = preview_file(rel_path, aggressive=aggressive)
            if not prev.get("changed"):
                results.append({
                    "path": rel_path, "ok": True, "skipped": True,
                    "skip_reason": "no_replacements", "replacements": 0,
                })
                continue
            # Without aggressive, skip risky files
            if (not aggressive) and prev.get("requires_manual_review"):
                results.append({
                    "path": rel_path, "ok": True, "skipped": True,
                    "skip_reason": "requires_manual_review",
                    "replacements": prev.get("replacements", 0),
                    "requires_manual_review": True,
                })
                continue
            # Even in aggressive mode, skip if still risky (couldn't clean)
            if aggressive and prev.get("requires_manual_review"):
                results.append({
                    "path": rel_path, "ok": True, "skipped": True,
                    "skip_reason": "aggressive_could_not_clean",
                    "replacements": prev.get("replacements", 0),
                    "requires_manual_review": True,
                })
                continue
            # Apply
            ap = apply_file(rel_path, aggressive=aggressive)
            reps = ap.get("replacements", 0) or 0
            total_reps += reps
            results.append({
                "path": rel_path, "ok": bool(ap.get("ok")),
                "skipped": False,
                "replacements": reps,
                "original_sha": ap.get("original_sha"),
                "new_sha": ap.get("new_sha"),
                "consts_moved": prev.get("consts_moved", []),
            })
        except AutofixError as e:
            results.append({"path": rel_path, "ok": False, "skipped": True, "error": str(e)})
        except Exception as e:  # pragma: no cover
            results.append({"path": rel_path, "ok": False, "skipped": True, "error": f"{type(e).__name__}: {e}"})

    return {
        "results": results,
        "backups": backups,
        "total_replacements": total_reps,
        "files_changed": sum(1 for r in results if not r.get("skipped") and r.get("ok")),
    }


def restore_files(backups: dict[str, str]) -> int:
    """Restore a set of files from a path→original-content map. Returns the
    number of files restored."""
    n = 0
    for rel, original in backups.items():
        try:
            abs_path = _validate_path(rel)
            abs_path.write_text(original)
            n += 1
        except Exception:
            continue
    return n
