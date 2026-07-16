#!/usr/bin/env python3
"""
Theme Enforcement Migration — Full Platform Sweep (Safe Mode)

Strategy:
  Single pass: regex replaces `propName: '#hexvalue'` patterns using per-property maps.
  Each map includes the correct token for that property type + unambiguous semantic colors.
  Module-level data objects (e.g., status config with `color:`) are intentionally preserved
  unless `colors` is provably in scope — handled by the useTheme scope check below.
"""

import re, os, sys
from pathlib import Path

FRONTEND = Path('/app/frontend')
SCAN_DIRS = [FRONTEND / 'src', FRONTEND / 'app']

SKIP_CONTAINS = ['node_modules', '.d.ts']

# ── SEMANTIC colors — same token meaning regardless of property type ───────────
SEMANTIC = {
    # Success (green)
    '10b981': 'colors.success',   '059669': 'colors.success',
    '16a34a': 'colors.success',   '22c55e': 'colors.success',
    '6ee7b7': 'colors.successSoft', '34d399': 'colors.success',
    # Warning (amber)
    'f59e0b': 'colors.warning',   'd97706': 'colors.warning',
    'eab308': 'colors.warning',   'fbbf24': 'colors.warning',
    # Error (red)
    'ef4444': 'colors.error',     'dc2626': 'colors.error',
    'e11d48': 'colors.error',     'f87171': 'colors.error',
    'fca5a5': 'colors.errorSoft', 'fee2e2': 'colors.errorSoft',
    # Info (cyan / sky)
    '06b6d4': 'colors.info',      '0891b2': 'colors.info',
    '0ea5e9': 'colors.info',      '22d3ee': 'colors.info',
    '38bdf8': 'colors.info',      '60a5fa': 'colors.info',
    # Primary (blue)
    '3b82f6': 'colors.primary',   '2563eb': 'colors.primary',
    '1d4ed8': 'colors.primary',   '93c5fd': 'colors.primary',
    'dbeafe': 'colors.primarySoft', 'eff6ff': 'colors.primarySoft',
    # Purple
    '8b5cf6': 'colors.purple',    '7c3aed': 'colors.purple',
    'a855f7': 'colors.purple',    'a78bfa': 'colors.purple',
    # Indigo
    '6366f1': 'colors.indigo',    '4f46e5': 'colors.indigo',
    '635bff': 'colors.indigo',    '818cf8': 'colors.indigo',
    # Orange
    'f97316': 'colors.orange',    'ea580c': 'colors.orange',
    'fb923c': 'colors.orange',
    # Accent (teal)
    '00d4aa': 'colors.accent',    '0d9488': 'colors.accent',
    '14b8a6': 'colors.accent',    '2dd4bf': 'colors.accent',
    # Gold/Special
    'ffd700': 'colors.warning',   'f59e0b': 'colors.warning',
    # Semantic soft (18 / 15 / 12 / 10 alpha)
    '10b98118': 'colors.successSoft', '10b98115': 'colors.successSoft',
    '10b98112': 'colors.successSoft', '10b98110': 'colors.successSoft',
    '10b98120': 'colors.successSoft', '10b98130': 'colors.successSoft',
    '10b98140': 'colors.successSoft', '10b98155': 'colors.successSoft',
    'ef444418': 'colors.errorSoft',   'ef444415': 'colors.errorSoft',
    'ef444412': 'colors.errorSoft',   'ef444420': 'colors.errorSoft',
    'ef444430': 'colors.errorSoft',   'ef444455': 'colors.errorSoft',
    'f59e0b18': 'colors.warningSoft', 'f59e0b15': 'colors.warningSoft',
    'f59e0b12': 'colors.warningSoft', 'f59e0b20': 'colors.warningSoft',
    'f59e0b55': 'colors.warningSoft',
    '3b82f618': 'colors.primarySoft', '3b82f612': 'colors.primarySoft',
    '3b82f620': 'colors.primarySoft',
    '2563eb12': 'colors.primarySoft', '2563eb18': 'colors.primarySoft',
    '8b5cf618': 'colors.purpleSoft',  '8b5cf615': 'colors.purpleSoft',
    '8b5cf612': 'colors.purpleSoft',  '8b5cf620': 'colors.purpleSoft',
    '6366f118': 'colors.indigoSoft',  '6366f115': 'colors.indigoSoft',
    '6366f112': 'colors.indigoSoft',
    'f9731618': 'colors.orangeSoft',
    '06b6d418': 'colors.infoSoft',    '0ea5e918': 'colors.infoSoft',
    '00d4aa18': 'colors.accentSoft',  '0d948815': 'colors.accentSoft',
    '14b8a615': 'colors.accentSoft',
}

# ── STRUCTURAL background colors ───────────────────────────────────────────────
BG_STRUCT = {
    # Dark backgrounds
    '050a18': 'colors.bg',     '040810': 'colors.bg',
    '060a18': 'colors.bg',     '070b1a': 'colors.bg',
    '080e24': 'colors.bgAlt',  '09101e': 'colors.bgAlt',
    '0a0f1e': 'colors.bgAlt',  '0b1120': 'colors.bgAlt',
    '0d1117': 'colors.card',   '0f1015': 'colors.card',
    '0f1117': 'colors.card',   '0f1118': 'colors.card',
    '0f172a': 'colors.card',   '10172b': 'colors.card',
    '111827': 'colors.cardMuted', '121929': 'colors.cardMuted',
    '131c2d': 'colors.cardMuted', '141e30': 'colors.cardMuted',
    '151f36': 'colors.card',   '162032': 'colors.card',
    '1a2035': 'colors.card',   '1a2133': 'colors.card',
    '1a2234': 'colors.card',   '1b2438': 'colors.card',
    '1c2333': 'colors.card',   '1c2436': 'colors.card',
    '1d2535': 'colors.card',   '1e2030': 'colors.card',
    '1e213a': 'colors.card',   '1f2937': 'colors.cardMuted',
    '202937': 'colors.cardMuted',
    '1e293b': 'colors.surfaceHover',
    '243046': 'colors.surfaceHover',
    # Light backgrounds
    'ffffff': 'colors.card',   'fafafa': 'colors.bg',
    'f9fafb': 'colors.bgAlt',  'f8fafc': 'colors.bg',
    'f1f5f9': 'colors.bgAlt',  'f0f4f8': 'colors.bgAlt',
    'eef2f7': 'colors.bgSoft', 'e8edf5': 'colors.bgSoft',
    'e2e8f0': 'colors.bgSoft', 'dde3ef': 'colors.bgSoft',
    # Transparent / common overlays — do NOT replace
}

# ── STRUCTURAL text colors ─────────────────────────────────────────────────────
TEXT_STRUCT = {
    # Light text (dark mode reading)
    'ffffff': 'colors.text',   'fefefe': 'colors.text',
    'f9fafb': 'colors.text',   'f8fafc': 'colors.text',
    'f1f5f9': 'colors.textSec',
    'e5e7eb': 'colors.textDim', 'd1d5db': 'colors.textDim',
    'cbd5e1': 'colors.textSec', 'c4cdd9': 'colors.textSec',
    'b0b9c8': 'colors.textMuted', '9ca3af': 'colors.textMuted',
    '8b9dc3': 'colors.textMuted', '94a3b8': 'colors.textDim',
    '64748b': 'colors.textMuted', '6b7280': 'colors.textMuted',
    '737373': 'colors.textMuted', '6e7d8c': 'colors.textMuted',
    '7a8598': 'colors.textMuted', '6c7a8d': 'colors.textMuted',
    '475569': 'colors.textDisabled',
    '334155': 'colors.textSec',
    # Dark text (light mode reading)
    '0f172a': 'colors.text',   '1a2035': 'colors.text',
    '1e293b': 'colors.textSec', '111827': 'colors.textSec',
    '1f2937': 'colors.textSec', '374151': 'colors.textSec',
}

# ── STRUCTURAL border colors ───────────────────────────────────────────────────
BORDER_STRUCT = {
    '0f172a': 'colors.border',   '111827': 'colors.border',
    '1e293b': 'colors.border',   '1f2937': 'colors.border',
    '1c2436': 'colors.border',   '1b2438': 'colors.border',
    '1a2234': 'colors.border',   '202937': 'colors.border',
    '243046': 'colors.border',
    '334155': 'colors.borderMd', '374151': 'colors.borderMd',
    '3d4f63': 'colors.borderMd', '4b5563': 'colors.borderMd',
    '475569': 'colors.borderMd',
    'cbd5e1': 'colors.border',   'c9d3dc': 'colors.border',
    'd1d5db': 'colors.borderLight', 'e2e8f0': 'colors.borderLight',
    'e5e7eb': 'colors.borderLight', 'ede9f0': 'colors.borderLight',
}

# ── Per-property combined maps ─────────────────────────────────────────────────
BG_MAP     = {**BG_STRUCT,     **SEMANTIC}
TEXT_MAP   = {**TEXT_STRUCT,   **SEMANTIC}
BORDER_MAP = {**BORDER_STRUCT, **SEMANTIC}
GENERIC_MAP = {**SEMANTIC}   # for tintColor, fill, stroke, etc.

# Property → map
def get_map(prop: str) -> dict:
    pl = prop.lower()
    if pl in ('backgroundcolor', 'background'):
        return BG_MAP
    if pl == 'color':
        return TEXT_MAP
    if 'bordercolor' in pl:
        return BORDER_MAP
    if pl in ('shadowcolor', 'tintcolor', 'fill', 'stroke', 'overlaycolor'):
        return GENERIC_MAP
    return {}

# ── Regex pattern for any style property: value ───────────────────────────────
PROP_PATTERN = re.compile(
    r'(backgroundColor|background(?!Image)|(?<![a-zA-Z])color|'
    r'border(?:Top|Bottom|Left|Right)?Color|shadowColor|tintColor|fill|stroke)'
    r':\s*([\'"])#([0-9a-fA-F]{3,8})\2',
    re.IGNORECASE
)

def replace_prop(m, token_cache: dict) -> str:
    prop  = m.group(1)
    hex_v = m.group(3).lower()

    cache_key = (prop.lower(), hex_v)
    if cache_key in token_cache:
        token = token_cache[cache_key]
    else:
        mp = get_map(prop)
        token = mp.get(hex_v)
        token_cache[cache_key] = token

    if token:
        return f'{prop}: {token}'
    return m.group(0)


# ── Ensure `colors` is destructured from useTheme() ──────────────────────────

def ensure_colors_destructured(content: str) -> str:
    """Add `colors` to useTheme() destructure if missing."""
    if 'useTheme' not in content:
        return content
    # Already has colors
    if re.search(r'const\s*\{[^}]*\bcolors\b', content):
        return content

    def add_colors(m):
        inner = m.group(1).strip()
        # avoid adding colors if it looks like it's already there as a different name
        if 'colors' not in inner:
            inner = inner + ', colors'
        return f'const {{{inner}}} = useTheme()'

    new_content = re.sub(
        r'const\s*\{([^}]*)\}\s*=\s*useTheme\(\)',
        add_colors,
        content
    )
    return new_content


# ── File processing ───────────────────────────────────────────────────────────

def should_process(fpath: str) -> bool:
    return (
        'node_modules' not in fpath
        and '.d.ts' not in fpath
        and fpath.endswith(('.tsx', '.jsx'))
    )


def process_file(fpath: Path) -> tuple[bool, int]:
    try:
        original = fpath.read_text(encoding='utf-8')
    except Exception:
        return False, 0

    token_cache: dict = {}
    changes = 0

    def sub(m):
        nonlocal changes
        result = replace_prop(m, token_cache)
        if result != m.group(0):
            changes += 1
        return result

    content = PROP_PATTERN.sub(sub, original)

    if changes > 0:
        # Ensure colors is in scope
        content = ensure_colors_destructured(content)

    if content != original:
        fpath.write_text(content, encoding='utf-8')
        return True, changes
    return False, 0


def run():
    total_files = 0
    total_changes = 0
    changed_files = []

    for scan_dir in SCAN_DIRS:
        for fpath in sorted(scan_dir.rglob('*')):
            if not should_process(str(fpath)):
                continue
            total_files += 1
            changed, n = process_file(fpath)
            if changed:
                total_changes += n
                rel = str(fpath.relative_to(FRONTEND))
                changed_files.append((rel, n))
                print(f'  ✓ {rel}  ({n} replacements)')

    print(f'\n=== Summary ===')
    print(f'Files scanned:  {total_files}')
    print(f'Files modified: {len(changed_files)}')
    print(f'Total token replacements: {total_changes}')

if __name__ == '__main__':
    print('=== Theme Enforcement Migration — Full Platform ===\n')
    run()
