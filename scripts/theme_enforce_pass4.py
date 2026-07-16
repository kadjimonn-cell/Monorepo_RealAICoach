#!/usr/bin/env python3
"""
Theme Enforcement Migration — Pass 4 (Final Cleanup)
Handles:
  1. Fixed ternary pattern (lookahead to not consume separators)
  2. ALL hex alpha variants (22, 33, 44, 55... any suffix)
  3. Structural colors remaining in ternaries / complex expressions
  4. Remaining backgroundColor/borderColor with structural values
"""

import re
from pathlib import Path

FRONTEND = Path('/app/frontend')
SCAN_DIRS = [FRONTEND / 'src', FRONTEND / 'app']

# ── COMPLETE map: ANY hex → token (built from full semantic + structural) ─────

def build_full_map():
    # Semantic base colors
    semantic_base = {
        '10b981': 'colors.success',   '059669': 'colors.success',
        '16a34a': 'colors.success',   '22c55e': 'colors.success',
        '6ee7b7': 'colors.success',   '34d399': 'colors.success',
        'f59e0b': 'colors.warning',   'd97706': 'colors.warning',
        'eab308': 'colors.warning',   'fbbf24': 'colors.warning',
        'ef4444': 'colors.error',     'dc2626': 'colors.error',
        'e11d48': 'colors.error',     'f87171': 'colors.error',
        '06b6d4': 'colors.info',      '0891b2': 'colors.info',
        '0ea5e9': 'colors.info',      '22d3ee': 'colors.info',
        '38bdf8': 'colors.info',      '7dd3fc': 'colors.info',
        '3b82f6': 'colors.primary',   '2563eb': 'colors.primary',
        '1d4ed8': 'colors.primary',   '60a5fa': 'colors.primary',
        '8b5cf6': 'colors.purple',    '7c3aed': 'colors.purple',
        'a855f7': 'colors.purple',    'a78bfa': 'colors.purple',
        '6366f1': 'colors.indigo',    '4f46e5': 'colors.indigo',
        '818cf8': 'colors.indigo',    '635bff': 'colors.indigo',
        'f97316': 'colors.orange',    'ea580c': 'colors.orange',
        'fb923c': 'colors.orange',
        '00d4aa': 'colors.accent',    '0d9488': 'colors.accent',
        '14b8a6': 'colors.accent',    '2dd4bf': 'colors.accent',
    }

    # Structural colors
    structural = {
        # Dark backgrounds
        '050a18': 'colors.bg',        '060a18': 'colors.bg',
        '070b1a': 'colors.bg',        '040810': 'colors.bg',
        '080e24': 'colors.bgAlt',     '090f20': 'colors.bgAlt',
        '0a1120': 'colors.bgAlt',     '0b1120': 'colors.bgAlt',
        '0d1117': 'colors.card',      '0f172a': 'colors.card',
        '0f1117': 'colors.card',      '0f1015': 'colors.card',
        '0f1118': 'colors.card',      '10172b': 'colors.card',
        '111827': 'colors.cardMuted', '121929': 'colors.cardMuted',
        '131c2d': 'colors.cardMuted', '141e30': 'colors.cardMuted',
        '161822': 'colors.card',      '162032': 'colors.card',
        '151f36': 'colors.card',      '1a2035': 'colors.card',
        '1a2133': 'colors.card',      '1a2234': 'colors.card',
        '1b2438': 'colors.card',      '1c2333': 'colors.card',
        '1c2436': 'colors.card',      '1d2535': 'colors.card',
        '1e2030': 'colors.card',      '1e213a': 'colors.card',
        '1f2937': 'colors.cardMuted', '202937': 'colors.cardMuted',
        '243046': 'colors.surfaceHover',
        '1e293b': 'colors.surfaceHover',
        # Light backgrounds
        'ffffff': 'colors.card',      'fafafa': 'colors.bg',
        'f9fafb': 'colors.bgAlt',     'f8fafc': 'colors.bg',
        'f1f5f9': 'colors.bgAlt',     'f0f4f8': 'colors.bgAlt',
        'eef2f7': 'colors.bgSoft',    'e8edf5': 'colors.bgSoft',
        'e2e8f0': 'colors.bgSoft',    'dde3ef': 'colors.bgSoft',
        'eef2ff': 'colors.primarySoft', 'dbeafe': 'colors.primarySoft',
        'bfdbfe': 'colors.primarySoft', '93c5fd': 'colors.primarySoft',
        # Gray text
        '334155': 'colors.textSec',   '4b5563': 'colors.textSec',
        '374151': 'colors.textSec',   '3d4f63': 'colors.textSec',
        '475569': 'colors.textDisabled',
        '64748b': 'colors.textMuted', '6b7280': 'colors.textMuted',
        '737373': 'colors.textMuted', '6e7d8c': 'colors.textMuted',
        '9ca3af': 'colors.textMuted', '94a3b8': 'colors.textDim',
        'cbd5e1': 'colors.textSec',   'd1d5db': 'colors.textDim',
        'e5e7eb': 'colors.textDim',   'b0b9c8': 'colors.textMuted',
        # Border colors
        '374151': 'colors.borderMd',
    }

    # Generate ALL alpha variants for semantic colors
    # Cover hex alpha suffixes 00-ff
    all_alphas = [f'{i:02x}' for i in range(5, 256, 4)]  # every 4 steps

    alpha_bases = {
        '10b981': 'successSoft', '059669': 'successSoft', '22c55e': 'successSoft',
        'ef4444': 'errorSoft',   'dc2626': 'errorSoft',
        'f59e0b': 'warningSoft', 'd97706': 'warningSoft',
        '3b82f6': 'primarySoft', '2563eb': 'primarySoft',
        '8b5cf6': 'purpleSoft',  '7c3aed': 'purpleSoft',
        '6366f1': 'indigoSoft',  '4f46e5': 'indigoSoft',
        'f97316': 'orangeSoft',
        '06b6d4': 'infoSoft',    '0ea5e9': 'infoSoft',
        '00d4aa': 'accentSoft',  '0d9488': 'accentSoft',
    }
    alpha_map = {}
    for base, token in alpha_bases.items():
        for sfx in all_alphas:
            alpha_map[base + sfx] = f'colors.{token}'
        # Also common named alphas
        for sfx in ['08', '0a', '0c', '0e', '10', '12', '14', '15', '16',
                    '18', '1a', '1c', '1e', '20', '22', '25', '28', '2a',
                    '2c', '2e', '30', '33', '35', '38', '3a', '3c', '3e',
                    '40', '44', '45', '48', '4a', '4c', '4e', '50', '55',
                    '58', '5a', '5c', '5e', '60', '66', '68', '6a', '70',
                    '77', '78', '7a', '7e', '80', '88', '8a', '8e',
                    '90', '99', '9e', 'a0', 'aa', 'b0', 'bb', 'cc', 'dd', 'ee']:
            alpha_map[base + sfx] = f'colors.{token}'

    combined = {}
    combined.update(alpha_map)   # alpha first (longer keys)
    combined.update(semantic_base)
    combined.update(structural)
    return combined

FULL_MAP = build_full_map()
SORTED_HEX = sorted(FULL_MAP.keys(), key=len, reverse=True)

# Precompile big alternation pattern for quoted hex values
HEX_ALT = '|'.join(re.escape(h) for h in SORTED_HEX)
QUOTED_HEX = re.compile(
    r"(['\"])#(" + HEX_ALT + r")\1",
    re.IGNORECASE
)


def hex_to_token(h: str) -> str | None:
    return FULL_MAP.get(h.lower())


def transform(content: str) -> tuple[str, int]:
    changes = 0

    # ── Pass A: Fix ternary — BOTH branches using lookahead ──────────────────
    # Matches: ? '#hex' or : '#hex' followed (lookahead) by ternary/end chars
    ternary_fixed = re.compile(
        r"([?:]\s*)(['\"])#([0-9a-fA-F]{3,8})\2(?=\s*[?:,)\]}\s]|$)",
        re.IGNORECASE | re.MULTILINE
    )
    def replace_ternary(m):
        nonlocal changes
        hex_v = m.group(3)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return m.group(1) + token
        return m.group(0)

    # Apply multiple times to catch chained ternaries
    for _ in range(3):
        new = ternary_fixed.sub(replace_ternary, content)
        if new == content:
            break
        content = new

    # ── Pass B: Remaining quoted hex — SEMANTIC ONLY (context-safe) ──────────
    # Only replace semantic/brand colors unconditionally (not structural bg/text)
    # Structural colors are ambiguous: #0f172a = card in bg context, text in text context
    SEMANTIC_ONLY_KEYS = {k for k, v in FULL_MAP.items()
                          if not any(v.endswith(t) for t in [
                              'bg', 'bgAlt', 'bgSoft', 'card', 'cardMuted',
                              'surface', 'surfaceHover', 'text', 'textSec',
                              'textMuted', 'textDim', 'textDisabled', 'border',
                              'borderMd', 'borderLight', 'skeleton'])}
    semantic_alts = '|'.join(re.escape(h) for h in
                             sorted(SEMANTIC_ONLY_KEYS, key=len, reverse=True))
    semantic_quoted = re.compile(r"(['\"])#(" + semantic_alts + r")\1", re.IGNORECASE)

    def replace_semantic_quoted(m):
        nonlocal changes
        hex_v = m.group(2)
        token = hex_to_token(hex_v)
        if token:
            changes += 1
            return token
        return m.group(0)

    content = semantic_quoted.sub(replace_semantic_quoted, content)

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
    print(f'\n=== Pass 4 Summary ===')
    print(f'Files modified:  {total_changed}')
    print(f'Replacements:    {total_replacements}')

if __name__ == '__main__':
    print('=== Theme Enforcement — Pass 4 (Final) ===\n')
    run()
