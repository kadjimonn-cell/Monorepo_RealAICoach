#!/usr/bin/env python3
"""
Theme Enforcement Migration — Pass 3
Handles remaining patterns:
  1. Ternary expressions:  ? '#10b981' : '#ef4444'
  2. Module-level semantic config objects: success: '#10B981', warning: '#F59E0B' etc.
  3. Remaining after: '#hex'  quoted string values in JSX children (badge labels etc.)
"""

import re
from pathlib import Path

FRONTEND = Path('/app/frontend')
SCAN_DIRS = [FRONTEND / 'src', FRONTEND / 'app']

# Semantic-only map (no structural colors to avoid corrupting data objects)
SEMANTIC = {
    '10b981': 'colors.success',   '059669': 'colors.success',
    '16a34a': 'colors.success',   '22c55e': 'colors.success',
    'f59e0b': 'colors.warning',   'd97706': 'colors.warning',
    'eab308': 'colors.warning',
    'ef4444': 'colors.error',     'dc2626': 'colors.error',
    'e11d48': 'colors.error',
    '06b6d4': 'colors.info',      '0891b2': 'colors.info',
    '0ea5e9': 'colors.info',
    '3b82f6': 'colors.primary',   '2563eb': 'colors.primary',
    '1d4ed8': 'colors.primary',
    '8b5cf6': 'colors.purple',    '7c3aed': 'colors.purple',
    'a855f7': 'colors.purple',
    '6366f1': 'colors.indigo',    '4f46e5': 'colors.indigo',
    'f97316': 'colors.orange',    'ea580c': 'colors.orange',
    '00d4aa': 'colors.accent',    '0d9488': 'colors.accent',
    '14b8a6': 'colors.accent',
    # Soft/alpha
    '10b98115': 'colors.successSoft', '10b98118': 'colors.successSoft',
    '10b98120': 'colors.successSoft', '10b98130': 'colors.successSoft',
    '10b98140': 'colors.successSoft', '10b98108': 'colors.successSoft',
    'ef444415': 'colors.errorSoft',   'ef444418': 'colors.errorSoft',
    'ef444420': 'colors.errorSoft',   'ef444430': 'colors.errorSoft',
    'ef444440': 'colors.errorSoft',   'ef444410': 'colors.errorSoft',
    'f59e0b15': 'colors.warningSoft', 'f59e0b18': 'colors.warningSoft',
    'f59e0b20': 'colors.warningSoft', 'f59e0b30': 'colors.warningSoft',
    '3b82f615': 'colors.primarySoft', '3b82f618': 'colors.primarySoft',
    '3b82f620': 'colors.primarySoft', '3b82f622': 'colors.primarySoft',
    '3b82f640': 'colors.primarySoft', '3b82f610': 'colors.primarySoft',
    '8b5cf610': 'colors.purpleSoft',  '8b5cf630': 'colors.purpleSoft',
    '8b5cf640': 'colors.purpleSoft',
    '6366f115': 'colors.indigoSoft',  '6366f118': 'colors.indigoSoft',
}

SORTED_HEX = sorted(SEMANTIC.keys(), key=len, reverse=True)


def hex_to_token(h: str) -> str | None:
    return SEMANTIC.get(h.lower())


def transform(content: str) -> tuple[str, int]:
    changes = 0

    # ── Pass A: ternary patterns anywhere —  ? '#hex1' : '#hex2' ─────────────
    # Matches: ? '#10b981' :  or  ? '#10b981' : colors.warning
    def replace_ternary_branch(m):
        nonlocal changes
        hex_v = m.group(2)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return m.group(1) + token + m.group(3)
        return m.group(0)

    # Match quoted hex preceded by ? or : (ternary branches)
    ternary_pattern = re.compile(
        r'([?:]\s*)([\'"])#([0-9a-fA-F]{3,8})\2(\s*[?:,)\]}])',
        re.IGNORECASE
    )
    def replace_ternary(m):
        nonlocal changes
        prefix = m.group(1)
        hex_v  = m.group(3)
        suffix = m.group(4)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return prefix + token + suffix
        return m.group(0)

    content = ternary_pattern.sub(replace_ternary, content)

    # ── Pass B: semantic config props: success/warning/error/info/gold/etc. ──
    # Matches: success: '#10B981', warning: '#F59E0B' etc. in object literals
    semantic_prop_pattern = re.compile(
        r'\b(success|warning|error|info|gold|primary|purple|indigo|orange|accent|'
        r'active|inactive|pending|resolved|completed|failed|cancelled|approved|'
        r'rejected|draft|published|archived|critical|high|medium|low|normal|'
        r'danger|safe|idle|running|stopped|online|offline)'
        r':\s*[\'"]#([0-9a-fA-F]{3,8})[\'"]',
        re.IGNORECASE
    )
    def replace_semantic_prop(m):
        nonlocal changes
        prop = m.group(1)
        hex_v = m.group(2)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}: {token}'
        return m.group(0)

    content = semantic_prop_pattern.sub(replace_semantic_prop, content)

    # ── Pass C: remaining color= JSX attributes that still show hex ───────────
    jsx_remaining = re.compile(
        r'\b(color|fill|stroke|tintColor)="(#[0-9a-fA-F]{3,8})"',
        re.IGNORECASE
    )
    def replace_jsx_attr(m):
        nonlocal changes
        prop = m.group(1)
        hex_v = m.group(2)[1:]
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return f'{prop}={{{token}}}'
        return m.group(0)
    content = jsx_remaining.sub(replace_jsx_attr, content)

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
    content, changes = transform(original)
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
            if 'node_modules' in str(fpath) or fpath.suffix not in ('.tsx', '.jsx'):
                continue
            changed, n = process_file(fpath)
            if changed:
                total_changed += 1
                total_replacements += n
                print(f'  ✓ {fpath.relative_to(FRONTEND)} ({n})')
    print(f'\n=== Pass 3 Summary ===')
    print(f'Files modified:  {total_changed}')
    print(f'Replacements:    {total_replacements}')

if __name__ == '__main__':
    print('=== Theme Enforcement — Pass 3 ===\n')
    run()
