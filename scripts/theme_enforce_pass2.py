#!/usr/bin/env python3
"""
Theme Enforcement Migration — Pass 2
Handles remaining patterns not caught by Pass 1:
  1. JSX attribute color="hex" → color={colors.TOKEN}
  2. Custom data-object fields: bg:, text:, border:, icon:, dot: etc.
  3. Extended alpha variants (08, 10, 20, 30, 40, 55) for semantic colors
  4. Simple ternary expressions where both branches are known tokens
"""

import re
from pathlib import Path

FRONTEND = Path('/app/frontend')
SCAN_DIRS = [FRONTEND / 'src', FRONTEND / 'app']

# ── All-alpha SEMANTIC mapping (lowercase hex → token) ───────────────────────
# Covers all common alpha suffixes for the main semantic colors

def build_alpha_map():
    bases = {
        '10b981': 'successSoft', '059669': 'successSoft', '22c55e': 'successSoft',
        'ef4444': 'errorSoft',   'dc2626': 'errorSoft',   'e11d48': 'errorSoft',
        'f59e0b': 'warningSoft', 'd97706': 'warningSoft',
        '3b82f6': 'primarySoft', '2563eb': 'primarySoft',
        '8b5cf6': 'purpleSoft',  '7c3aed': 'purpleSoft',
        '6366f1': 'indigoSoft',  '4f46e5': 'indigoSoft',
        'f97316': 'orangeSoft',
        '06b6d4': 'infoSoft',    '0ea5e9': 'infoSoft',
        '00d4aa': 'accentSoft',  '0d9488': 'accentSoft',
    }
    suffixes = ['08', '10', '12', '14', '15', '16', '18', '1a', '20', '25',
                '30', '35', '40', '45', '50', '55', '60', '66', '70', '80']
    result = {}
    for base, token in bases.items():
        for sfx in suffixes:
            result[base + sfx] = f'colors.{token}'
    return result

ALPHA_MAP = build_alpha_map()

# ── Base semantic colors (no alpha) ───────────────────────────────────────────
SEMANTIC_BASE = {
    '10b981': 'colors.success',  '059669': 'colors.success',
    '16a34a': 'colors.success',  '22c55e': 'colors.success',
    'f59e0b': 'colors.warning',  'd97706': 'colors.warning',
    'eab308': 'colors.warning',
    'ef4444': 'colors.error',    'dc2626': 'colors.error',
    'e11d48': 'colors.error',    'f87171': 'colors.error',
    '06b6d4': 'colors.info',     '0891b2': 'colors.info',
    '0ea5e9': 'colors.info',     '22d3ee': 'colors.info',
    '3b82f6': 'colors.primary',  '2563eb': 'colors.primary',
    '1d4ed8': 'colors.primary',
    '8b5cf6': 'colors.purple',   '7c3aed': 'colors.purple',
    'a855f7': 'colors.purple',
    '6366f1': 'colors.indigo',   '4f46e5': 'colors.indigo',
    'f97316': 'colors.orange',   'ea580c': 'colors.orange',
    '00d4aa': 'colors.accent',   '0d9488': 'colors.accent',
    '14b8a6': 'colors.accent',
}

# Combined: alpha variants first (longer hex → higher specificity)
ALL_SEMANTIC = {**ALPHA_MAP, **SEMANTIC_BASE}

# Sort keys by length descending for longest-first matching
SORTED_HEX = sorted(ALL_SEMANTIC.keys(), key=len, reverse=True)

# ── Data-object property names that hold color values ─────────────────────────
DATA_COLOR_PROPS = r'(?:bg|text|border|icon|dot|ring|color|fill|stroke|badge|tag|indicator|accent|highlight|line|track|tint|overlay|glow|shadow|foreground|label(?:Color)?|value(?:Color)?|active(?:Color)?|inactive(?:Color)?)'

# ── Patterns ──────────────────────────────────────────────────────────────────

# 1. JSX attribute:  color="#hex" or stroke="#hex"  →  color={TOKEN}
JSX_ATTR_PATTERN = re.compile(
    r'\b(color|fill|stroke|tintColor|activeColor|inactiveColor)="(#[0-9a-fA-F]{3,8})"',
    re.IGNORECASE
)

# 2. Data-object field:  bg: '#hex', text: '#hex', border: '#hex'
DATA_OBJ_PATTERN = re.compile(
    r'\b(' + DATA_COLOR_PROPS + r'):\s*[\'"]#([0-9a-fA-F]{3,8})[\'"]',
    re.IGNORECASE
)

# 3. Ternary in JSX attribute:  color={'#hex'}  or  color={cond ? '#hex' : '#hex2'}
JSX_CURLY_PATTERN = re.compile(
    r'\b(color|fill|stroke|tintColor)=\{[\'"]#([0-9a-fA-F]{3,8})[\'"]\}',
    re.IGNORECASE
)


def hex_to_token(hex_val: str) -> str | None:
    return ALL_SEMANTIC.get(hex_val.lower())


def transform_content(content: str) -> tuple[str, int]:
    changes = 0

    # ── Pass A: JSX attribute  color="#hex" → color={TOKEN} ──────────────────
    def replace_jsx_attr(m):
        nonlocal changes
        prop = m.group(1)
        hex_v = m.group(2)[1:]  # strip leading #
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}={{{token}}}'
        return m.group(0)

    content = JSX_ATTR_PATTERN.sub(replace_jsx_attr, content)

    # ── Pass B: JSX curly color={'#hex'} → color={TOKEN} ────────────────────
    def replace_jsx_curly(m):
        nonlocal changes
        prop = m.group(1)
        hex_v = m.group(2)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}={{{token}}}'
        return m.group(0)

    content = JSX_CURLY_PATTERN.sub(replace_jsx_curly, content)

    # ── Pass C: Data object  bg: '#hex', border: '#hex' etc. ─────────────────
    def replace_data_obj(m):
        nonlocal changes
        prop = m.group(1)
        hex_v = m.group(2)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}: {token}'
        return m.group(0)

    content = DATA_OBJ_PATTERN.sub(replace_data_obj, content)

    # ── Pass D: Extended alpha in style contexts (missed by Pass 1) ──────────
    # Matches remaining: backgroundColor: '#10B98155', color: '#ef444440', etc.
    def replace_style_alpha(m):
        nonlocal changes
        prop = m.group(1)
        quote = m.group(2)
        hex_v = m.group(3)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}: {token}'
        return m.group(0)

    alpha_pattern = re.compile(
        r'(backgroundColor|background(?!Image)|(?<![a-zA-Z])color|'
        r'border(?:Top|Bottom|Left|Right)?Color|shadowColor|tintColor|fill|stroke)'
        r':\s*([\'"])#([0-9a-fA-F]{3,8})\2',
        re.IGNORECASE
    )
    content = alpha_pattern.sub(replace_style_alpha, content)

    return content, changes


def ensure_colors_in_scope(content: str) -> str:
    if 'colors.' not in content or 'useTheme' not in content:
        return content
    if re.search(r'const\s*\{[^}]*\bcolors\b', content):
        return content
    def add_colors(m):
        inner = m.group(1).strip()
        if 'colors' not in inner:
            inner = inner + ', colors'
        return f'const {{{inner}}} = useTheme()'
    return re.sub(r'const\s*\{([^}]*)\}\s*=\s*useTheme\(\)', add_colors, content)


def process_file(fpath: Path) -> tuple[bool, int]:
    try:
        original = fpath.read_text(encoding='utf-8')
    except Exception:
        return False, 0

    content, changes = transform_content(original)

    if changes > 0:
        content = ensure_colors_in_scope(content)

    if content != original:
        fpath.write_text(content, encoding='utf-8')
        return True, changes
    return False, 0


def run():
    total_changed = 0
    total_replacements = 0

    for scan_dir in SCAN_DIRS:
        for fpath in sorted(scan_dir.rglob('*')):
            if 'node_modules' in str(fpath) or not fpath.suffix in ('.tsx', '.jsx'):
                continue
            changed, n = process_file(fpath)
            if changed:
                total_changed += 1
                total_replacements += n
                print(f'  ✓ {fpath.relative_to(FRONTEND)}  ({n})')

    print(f'\n=== Pass 2 Summary ===')
    print(f'Files modified:  {total_changed}')
    print(f'Replacements:    {total_replacements}')

if __name__ == '__main__':
    print('=== Theme Enforcement — Pass 2 ===\n')
    run()
