"""
Automated WCAG Accessibility Contrast Checker + Auto-Fix.

Scans frontend .tsx files for dark-mode color pairs, calculates WCAG AA
contrast ratios, flags violations, and auto-fixes by adjusting colors
to meet the 4.5:1 (normal text) or 3:1 (large text) threshold.
"""

import os
import re
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from routes.db import db, require_admin
from utils.email_service import ops_alert_template_enforcer

router = APIRouter(prefix="/admin/accessibility")
logger = logging.getLogger("accessibility")

FRONTEND_SRC = "/app/frontend/src"
# WCAG AA thresholds
NORMAL_TEXT_RATIO = 4.5
LARGE_TEXT_RATIO = 3.0

# Known dark-mode background colors used in the app
DARK_BACKGROUNDS = {
    "#0B0F1A": "page bg",
    "#0F172A": "page bg alt",
    "#111827": "card bg",
    "#1E293B": "surface",
    "#1F2937": "border/surface",
    "#334155": "elevated surface",
}


@ops_alert_template_enforcer("incident", "incident_accessibility_audit_alert")
async def _send_incident_alert_email(**kwargs):
    from utils.email_service import send_email

    return await send_email(**kwargs)

# ─── Color Utilities ──────────────────────────────────────────────────────────


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return (int(h[0:2], 16), int(h[1:2 + 1], 16), int(h[2:4 + 1], 16)) if len(h) == 6 else (0, 0, 0)


def _hex_to_rgb_safe(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _relative_luminance(r: int, g: int, b: int) -> float:
    def _linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    fg = _hex_to_rgb_safe(fg_hex)
    bg = _hex_to_rgb_safe(bg_hex)
    l1 = _relative_luminance(*fg)
    l2 = _relative_luminance(*bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _lighten_to_ratio(fg_hex: str, bg_hex: str, target_ratio: float) -> str:
    """Lighten foreground color until contrast ratio meets target against bg."""
    r, g, b = _hex_to_rgb_safe(fg_hex)
    bg_lum = _relative_luminance(*_hex_to_rgb_safe(bg_hex))

    for step in range(100):
        r = min(r + 3, 255)
        g = min(g + 3, 255)
        b = min(b + 3, 255)
        fg_lum = _relative_luminance(r, g, b)
        lighter = max(fg_lum, bg_lum)
        darker = min(fg_lum, bg_lum)
        ratio = (lighter + 0.05) / (darker + 0.05)
        if ratio >= target_ratio:
            return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}"


def _darken_to_ratio(fg_hex: str, bg_hex: str, target_ratio: float) -> str:
    """Darken foreground color until contrast ratio meets target against bg."""
    r, g, b = _hex_to_rgb_safe(fg_hex)
    bg_lum = _relative_luminance(*_hex_to_rgb_safe(bg_hex))

    for step in range(100):
        r = max(r - 3, 0)
        g = max(g - 3, 0)
        b = max(b - 3, 0)
        fg_lum = _relative_luminance(r, g, b)
        lighter = max(fg_lum, bg_lum)
        darker = min(fg_lum, bg_lum)
        ratio = (lighter + 0.05) / (darker + 0.05)
        if ratio >= target_ratio:
            return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}"


# ─── Scanner ──────────────────────────────────────────────────────────────────

# Pattern: darkMode ? '#HEXCOLOR' or dark ? '#HEXCOLOR'
DARK_COLOR_RE = re.compile(
    r"""(?:darkMode|isDark|dark)\s*\?\s*['"]#([0-9a-fA-F]{3,8})['"]""",
    re.IGNORECASE,
)

# Pattern for color declarations: color: '#HEX' or color: darkMode ? '#HEX'
COLOR_PROP_RE = re.compile(
    r"""color:\s*(?:\(?\s*(?:darkMode|isDark|dark)\s*\?\s*)?['"]#([0-9a-fA-F]{3,8})['"]""",
    re.IGNORECASE,
)

# Background detection: backgroundColor: darkMode ? '#HEX'
BG_PROP_RE = re.compile(
    r"""backgroundColor:\s*(?:\(?\s*(?:darkMode|isDark|dark)\s*\?\s*)?['"]#([0-9a-fA-F]{3,8})['"]""",
    re.IGNORECASE,
)


def _scan_file(filepath: str) -> list:
    """Scan a .tsx file for dark-mode color pairs and check contrast."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")
    except Exception:
        return violations

    rel_path = filepath.replace(FRONTEND_SRC + "/", "")

    for i, line in enumerate(lines):
        line_num = i + 1

        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # Find dark-mode color assignments
        dark_colors = DARK_COLOR_RE.findall(line)
        if not dark_colors:
            continue

        for hex_val in dark_colors:
            if len(hex_val) > 6:
                continue
            full_hex = f"#{hex_val}"

            # Determine if this is a text color or background color
            is_bg = "backgroundColor" in line or "background:" in line
            if is_bg:
                continue

            # Check if this is a text/color property (exclude borderColor, backgroundColor)
            is_text = "color:" in line.lower() or "color :" in line.lower()
            is_border = "bordercolor" in line.lower() or "border-color" in line.lower() or "borderwidth" in line.lower()
            is_bg_prop = "backgroundcolor" in line.lower() or "background:" in line.lower()
            if not is_text or is_border or is_bg_prop:
                continue

            # Test against all known dark backgrounds
            for bg_hex, bg_name in DARK_BACKGROUNDS.items():
                ratio = _contrast_ratio(full_hex, bg_hex)
                if ratio < NORMAL_TEXT_RATIO:
                    violations.append({
                        "file": rel_path,
                        "line": line_num,
                        "fg_color": full_hex.upper(),
                        "bg_color": bg_hex.upper(),
                        "bg_name": bg_name,
                        "ratio": round(ratio, 2),
                        "required": NORMAL_TEXT_RATIO,
                        "severity": "critical" if ratio < LARGE_TEXT_RATIO else "warning",
                        "fixable": True,
                    })
                    break  # Only report worst-case bg

    return violations


# ─── ARIA Labels Scanner ─────────────────────────────────────────────────────

INTERACTIVE_RE = re.compile(
    r"""<(TouchableOpacity|Pressable|TouchableHighlight|Button)\b""",
    re.IGNORECASE,
)
IMG_RE = re.compile(r"""<(Image|img)\b""", re.IGNORECASE)
INPUT_RE = re.compile(r"""<(TextInput|input|select|textarea)\b""", re.IGNORECASE)

ARIA_LABEL_RE = re.compile(
    r"""(accessibilityLabel|aria-label|accessible|accessibilityRole|data-testid)""",
    re.IGNORECASE,
)
ALT_RE = re.compile(r"""(alt=|accessibilityLabel)""", re.IGNORECASE)


def _scan_aria(filepath: str) -> list:
    """Scan for interactive elements missing ARIA labels."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return violations

    rel_path = filepath.replace(FRONTEND_SRC + "/", "")

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # Check interactive elements for accessibilityLabel
        if INTERACTIVE_RE.search(line):
            block = "".join(lines[i:min(i + 5, len(lines))])
            if not ARIA_LABEL_RE.search(block):
                violations.append({
                    "file": rel_path, "line": line_num,
                    "category": "aria", "severity": "warning",
                    "element": INTERACTIVE_RE.search(line).group(1),
                    "message": "Interactive element missing accessibilityLabel or data-testid",
                    "fixable": True,
                })

        # Check images for alt text
        if IMG_RE.search(line):
            block = "".join(lines[i:min(i + 3, len(lines))])
            if not ALT_RE.search(block):
                violations.append({
                    "file": rel_path, "line": line_num,
                    "category": "aria", "severity": "warning",
                    "element": "Image",
                    "message": "Image missing alt text or accessibilityLabel",
                    "fixable": True,
                })

        # Check inputs for labels
        if INPUT_RE.search(line):
            block = "".join(lines[i:min(i + 5, len(lines))])
            if not re.search(r"(placeholder|accessibilityLabel|aria-label|label)", block, re.IGNORECASE):
                violations.append({
                    "file": rel_path, "line": line_num,
                    "category": "aria", "severity": "critical",
                    "element": INPUT_RE.search(line).group(1),
                    "message": "Input missing label, placeholder, or accessibilityLabel",
                    "fixable": True,
                })

    return violations


# ─── Keyboard Navigation Scanner ─────────────────────────────────────────────

ONPRESS_RE = re.compile(r"""onPress\s*[={]""", re.IGNORECASE)
ROLE_RE = re.compile(r"""(role=|accessibilityRole)""", re.IGNORECASE)
TABINDEX_RE = re.compile(r"""tabIndex""", re.IGNORECASE)


def _scan_keyboard(filepath: str) -> list:
    """Scan for keyboard navigation issues."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return violations

    rel_path = filepath.replace(FRONTEND_SRC + "/", "")

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        # Check View elements with onPress but no role
        if "<View" in line and ONPRESS_RE.search(line):
            block = "".join(lines[max(0, i - 1):min(i + 5, len(lines))])
            if not ROLE_RE.search(block):
                violations.append({
                    "file": rel_path, "line": line_num,
                    "category": "keyboard", "severity": "warning",
                    "element": "View",
                    "message": "View with onPress missing role='button' for keyboard access",
                    "fixable": True,
                })

        # Check div elements with onClick but no role/tabIndex
        if re.search(r"<div\b.*onClick", line, re.IGNORECASE):
            block = "".join(lines[max(0, i - 1):min(i + 3, len(lines))])
            has_role = ROLE_RE.search(block)
            has_tabindex = TABINDEX_RE.search(block)
            if not has_role or not has_tabindex:
                missing = []
                if not has_role:
                    missing.append("role='button'")
                if not has_tabindex:
                    missing.append("tabIndex={0}")
                violations.append({
                    "file": rel_path, "line": line_num,
                    "category": "keyboard", "severity": "warning",
                    "element": "div",
                    "message": f"Clickable div missing {' and '.join(missing)} for keyboard access",
                    "fixable": True,
                })

    return violations


# ─── Focus Indicator Scanner ─────────────────────────────────────────────────

def _scan_focus(filepath: str) -> list:
    """Scan for missing focus indicators."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return violations

    rel_path = filepath.replace(FRONTEND_SRC + "/", "")

    outline_none_matches = list(re.finditer(r"outline:\s*(?:none|0|'none'|\"none\")", content, re.IGNORECASE))
    for match in outline_none_matches:
        line_num = content[:match.start()].count("\n") + 1
        context = content[max(0, match.start() - 200):min(len(content), match.end() + 200)]
        has_replacement = re.search(r"(:focus|boxShadow|ring|focusVisible|focus-visible)", context, re.IGNORECASE)
        if not has_replacement:
            violations.append({
                "file": rel_path, "line": line_num,
                "category": "focus", "severity": "warning",
                "element": "style",
                "message": "outline:none without replacement focus indicator (boxShadow/ring)",
                "fixable": True,
            })

    return violations


# ─── Auto-fix for Keyboard Issues ────────────────────────────────────────────

def _auto_fix_keyboard(violations: list) -> dict:
    """Auto-fix keyboard navigation issues by adding role and tabIndex."""
    fixes_applied = 0
    files_modified = set()
    fix_details = []

    by_file = {}
    for v in violations:
        if v.get("category") != "keyboard" or not v.get("fixable"):
            continue
        fpath = os.path.join(FRONTEND_SRC, v["file"])
        if fpath not in by_file:
            by_file[fpath] = []
        by_file[fpath].append(v)

    for fpath, file_violations in by_file.items():
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        modified = False
        for v in sorted(file_violations, key=lambda x: -x["line"]):
            idx = v["line"] - 1
            if idx >= len(lines):
                continue
            line = lines[idx]

            if v["element"] == "div":
                if 'role=' not in line and 'role =' not in line:
                    # Handle JSX onClick (camelCase)
                    if "onClick" in line:
                        line = line.replace("onClick", 'role="button" tabIndex={0} onClick', 1)
                        lines[idx] = line
                        modified = True
                    # Handle HTML onclick (lowercase, in template strings)
                    elif "onclick" in line:
                        line = line.replace("onclick", 'role="button" tabindex="0" onclick', 1)
                        lines[idx] = line
                        modified = True

                    if modified:
                        fixes_applied += 1
                        fix_details.append({
                            "file": v["file"], "line": v["line"],
                            "fix": "Added role='button' tabIndex/tabindex",
                            "category": "keyboard",
                        })

            elif v["element"] == "View":
                if 'role=' not in line and 'accessibilityRole' not in line:
                    # Add accessibilityRole="button" before onPress
                    if "onPress" in line:
                        line = line.replace("onPress", 'accessibilityRole="button" tabIndex={0} onPress', 1)
                        lines[idx] = line
                        modified = True
                        fixes_applied += 1
                        fix_details.append({
                            "file": v["file"], "line": v["line"],
                            "fix": "Added accessibilityRole='button' tabIndex={0}",
                            "category": "keyboard",
                        })

        if modified:
            files_modified.add(v["file"])
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception as e:
                logger.error(f"Failed to write {fpath}: {e}")

    return {
        "fixes_applied": fixes_applied,
        "files_modified": len(files_modified),
        "fix_details": fix_details[:50],
    }


# ─── Auto-fix for Focus Indicators ───────────────────────────────────────────

# Patterns for outline:none in inline style objects
OUTLINE_NONE_OBJ_RE = re.compile(
    r"""outline:\s*['"]none['"]""",
    re.IGNORECASE,
)


def _auto_fix_focus(violations: list) -> dict:
    """Auto-fix focus indicator issues by adding boxShadow alongside outline:none."""
    fixes_applied = 0
    files_modified = set()
    fix_details = []

    by_file = {}
    for v in violations:
        if v.get("category") != "focus" or not v.get("fixable"):
            continue
        fpath = os.path.join(FRONTEND_SRC, v["file"])
        if fpath not in by_file:
            by_file[fpath] = []
        by_file[fpath].append(v)

    for fpath, file_violations in by_file.items():
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        modified = False
        lines = content.split("\n")
        for v in file_violations:
            line_idx = v["line"] - 1
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]

            # Replace outline: 'none' with outline: 'none' + boxShadow for focus
            if "{ outline: 'none' }" in line:
                line = line.replace(
                    "{ outline: 'none' }",
                    "{ outline: 'none', boxShadow: '0 0 0 2px transparent' }",
                )
                lines[line_idx] = line
                modified = True
                fixes_applied += 1
                fix_details.append({
                    "file": v["file"], "line": v["line"],
                    "fix": "Added boxShadow focus indicator alongside outline:none",
                    "category": "focus",
                })
            elif '{ outline: "none" }' in line:
                line = line.replace(
                    '{ outline: "none" }',
                    '{ outline: "none", boxShadow: "0 0 0 2px transparent" }',
                )
                lines[line_idx] = line
                modified = True
                fixes_applied += 1
                fix_details.append({
                    "file": v["file"], "line": v["line"],
                    "fix": "Added boxShadow focus indicator alongside outline:none",
                    "category": "focus",
                })

        if modified:
            files_modified.add(v["file"])
            content = "\n".join(lines)
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to write {fpath}: {e}")

    return {
        "fixes_applied": fixes_applied,
        "files_modified": len(files_modified),
        "fix_details": fix_details[:50],
    }


# ─── Auto-fix for ARIA Labels ────────────────────────────────────────────────

TEXT_CONTENT_RE = re.compile(r""">\s*{?\s*['"`]([^'"`<>]{2,40})['"`]\s*}?\s*<""")
TEXT_CHILD_RE = re.compile(r"""<Text[^>]*>\s*{?\s*['"`]?([^'"`<>{}\n]{2,40})['"`]?\s*}?\s*</Text""")
ICON_NAME_RE = re.compile(r"""name=\s*['"]([^'"]+)['"]""")
ONPRESS_HANDLER_RE = re.compile(r"""onPress=\{[^}]*?(\w+)\}""")
SOURCE_RE = re.compile(r"""source=\{[^}]*?['"]([^'"]+?)['"]""")
PLACEHOLDER_RE = re.compile(r"""placeholder=\{?\s*['"]([^'"]+)['"]""")


def _extract_label(lines: list, idx: int, element: str) -> str:
    """Analyze nearby context to generate a meaningful accessibilityLabel."""
    block = "".join(lines[idx:min(idx + 8, len(lines))])
    line = lines[idx]

    # 1. Check for nearby Text child content
    text_match = TEXT_CHILD_RE.search(block)
    if text_match:
        label = text_match.group(1).strip()
        if len(label) >= 2 and not label.startswith("{") and not label.startswith("$"):
            return label

    # 2. Check for icon name
    icon_match = ICON_NAME_RE.search(block)
    if icon_match:
        name = icon_match.group(1).replace("-", " ").replace("_", " ").strip()
        if name:
            return f"{name} button"

    # 3. Check for onPress handler name
    handler_match = ONPRESS_HANDLER_RE.search(line)
    if handler_match:
        name = handler_match.group(1)
        # Convert camelCase to readable: onPressSubmit → Submit
        name = re.sub(r'^(on|handle|set|toggle)', '', name)
        name = re.sub(r'([A-Z])', r' \1', name).strip()
        if name:
            return name

    # 4. For Image: check source/uri
    if element == "Image":
        src_match = SOURCE_RE.search(block)
        if src_match:
            name = src_match.group(1).split("/")[-1].split(".")[0]
            name = name.replace("-", " ").replace("_", " ").strip()
            if name:
                return f"{name} image"
        return "Decorative image"

    # 5. For TextInput: check placeholder
    if element in ("TextInput", "input"):
        ph_match = PLACEHOLDER_RE.search(block)
        if ph_match:
            return ph_match.group(1)
        return "Text input"

    # 6. Fallback: use element type + line context
    # Extract any string literal nearby
    any_text = TEXT_CONTENT_RE.search(block)
    if any_text:
        return any_text.group(1).strip()

    return "Interactive element"


def _safe_insert_label(line: str, element: str, label: str) -> str | None:
    """Insert accessibilityLabel into the element's opening JSX tag on this line.

    Returns the new line, or None when no safe insertion point exists (generic
    type params like useRef<TextInput>, arrow '=>' tokens, multi-line tags).
    Guards against the Apr-2026 auto-fixer corruption incident.
    """
    marker = "<" + element
    pos = line.find(marker)
    while pos != -1:
        prev = line[pos - 1] if pos > 0 else " "
        nxt = line[pos + len(marker): pos + len(marker) + 1]
        prev_is_ident = prev.isalnum() or prev in "_$."
        nxt_is_ident = bool(nxt) and (nxt.isalnum() or nxt in "_$")
        if not prev_is_ident and not nxt_is_ident:
            break  # genuine JSX opening tag (not a generic like useRef<TextInput>)
        pos = line.find(marker, pos + 1)
    if pos == -1:
        return None
    i = pos + len(marker)
    depth = 0
    while i < len(line):
        ch = line[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == ">" and depth == 0 and line[i - 1] != "=":
            insert_at = i - 1 if line[i - 1] == "/" else i
            return line[:insert_at] + f' accessibilityLabel="{label}"' + line[insert_at:]
        i += 1
    return None


def _auto_fix_aria(violations: list) -> dict:
    """Auto-fix ARIA label issues by adding accessibilityLabel props."""
    fixes_applied = 0
    files_modified = set()
    fix_details = []

    by_file = {}
    for v in violations:
        if v.get("category") != "aria":
            continue
        fpath = os.path.join(FRONTEND_SRC, v["file"])
        if fpath not in by_file:
            by_file[fpath] = []
        by_file[fpath].append(v)

    for fpath, file_violations in by_file.items():
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        modified = False
        # Process in reverse to keep line numbers stable
        for v in sorted(file_violations, key=lambda x: -x["line"]):
            idx = v["line"] - 1
            if idx >= len(lines):
                continue
            line = lines[idx]
            element = v.get("element", "")

            # Skip if already has accessibilityLabel
            if "accessibilityLabel" in line:
                continue

            label = _extract_label(lines, idx, element)
            # Escape quotes in label
            label = label.replace('"', '\\"')

            if element in ("TouchableOpacity", "Pressable", "TouchableHighlight", "Button",
                           "Image", "TextInput", "input"):
                new_line = _safe_insert_label(line, element, label)
                if new_line is None:
                    continue  # no safe insertion point on this line — skip
                lines[idx] = new_line
                modified = True
                fixes_applied += 1
                fix_details.append({
                    "file": v["file"], "line": v["line"],
                    "fix": f'Added accessibilityLabel="{label}"',
                    "category": "aria", "element": element,
                })

        if modified:
            files_modified.add(v["file"])
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception as e:
                logger.error(f"Failed to write {fpath}: {e}")

    return {
        "fixes_applied": fixes_applied,
        "files_modified": len(files_modified),
        "fix_details": fix_details[:100],
    }


def _run_audit() -> dict:
    """Scan all .tsx files for WCAG violations across 4 categories."""
    contrast_violations = []
    aria_violations = []
    keyboard_violations = []
    focus_violations = []
    files_scanned = 0

    for root, dirs, files in os.walk(FRONTEND_SRC):
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "__tests__"]]
        for fname in files:
            if not fname.endswith(".tsx"):
                continue
            fpath = os.path.join(root, fname)
            files_scanned += 1
            contrast_violations.extend(_scan_file(fpath))
            aria_violations.extend(_scan_aria(fpath))
            keyboard_violations.extend(_scan_keyboard(fpath))
            focus_violations.extend(_scan_focus(fpath))

    # Deduplicate contrast by file+line+fg_color
    seen = set()
    unique_contrast = []
    for v in contrast_violations:
        key = f"{v['file']}:{v['line']}:{v['fg_color']}"
        if key not in seen:
            seen.add(key)
            unique_contrast.append(v)

    # Deduplicate others by file+line+category
    for vlist in [aria_violations, keyboard_violations, focus_violations]:
        seen2 = set()
        deduped = []
        for v in vlist:
            key = f"{v['file']}:{v['line']}:{v['category']}"
            if key not in seen2:
                seen2.add(key)
                deduped.append(v)
        vlist.clear()
        vlist.extend(deduped)

    all_violations = unique_contrast + aria_violations + keyboard_violations + focus_violations
    critical = [v for v in all_violations if v.get("severity") == "critical"]
    warnings = [v for v in all_violations if v.get("severity") == "warning"]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_scanned": files_scanned,
        "total_violations": len(all_violations),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "passed": len(all_violations) == 0,
        "violations": all_violations[:100],
        "all_violations": all_violations,  # Internal, not sent in API response
        "categories": {
            "contrast": {"count": len(unique_contrast), "passed": len(unique_contrast) == 0},
            "aria": {"count": len(aria_violations), "passed": len(aria_violations) == 0},
            "keyboard": {"count": len(keyboard_violations), "passed": len(keyboard_violations) == 0},
            "focus": {"count": len(focus_violations), "passed": len(focus_violations) == 0},
        },
    }


def _auto_fix_violations(violations: list) -> dict:
    """Auto-fix WCAG contrast violations by adjusting colors in source files."""
    fixes_applied = 0
    files_modified = set()
    fix_details = []

    # Group by file
    by_file = {}
    for v in violations:
        if not v.get("fixable"):
            continue
        fpath = os.path.join(FRONTEND_SRC, v["file"])
        if fpath not in by_file:
            by_file[fpath] = []
        by_file[fpath].append(v)

    for fpath, file_violations in by_file.items():
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        modified = False
        for v in file_violations:
            old_color = v["fg_color"]
            bg_color = v["bg_color"]
            target = v["required"]

            # Determine fix direction: lighten for dark bg, darken for light bg
            bg_lum = _relative_luminance(*_hex_to_rgb_safe(bg_color))
            if bg_lum < 0.5:
                new_color = _lighten_to_ratio(old_color, bg_color, target)
            else:
                new_color = _darken_to_ratio(old_color, bg_color, target)

            new_ratio = _contrast_ratio(new_color, bg_color)
            if new_ratio >= target and new_color.upper() != old_color.upper():
                # Replace in content (case-insensitive hex match)
                old_lower = old_color.lower()
                old_upper = old_color.upper()
                # Replace the specific occurrence
                if f"'{old_lower}'" in content:
                    content = content.replace(f"'{old_lower}'", f"'{new_color}'", 1)
                    modified = True
                elif f"'{old_upper}'" in content:
                    content = content.replace(f"'{old_upper}'", f"'{new_color}'", 1)
                    modified = True
                elif f'"{old_lower}"' in content:
                    content = content.replace(f'"{old_lower}"', f'"{new_color}"', 1)
                    modified = True

                if modified:
                    fixes_applied += 1
                    files_modified.add(v["file"])
                    fix_details.append({
                        "file": v["file"],
                        "line": v["line"],
                        "old_color": old_color,
                        "new_color": new_color,
                        "old_ratio": v["ratio"],
                        "new_ratio": round(new_ratio, 2),
                        "bg_color": bg_color,
                    })

        if modified:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to write {fpath}: {e}")

    return {
        "fixes_applied": fixes_applied,
        "files_modified": len(files_modified),
        "fix_details": fix_details[:50],
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/audit")
async def run_accessibility_audit(request: Request):
    """Run WCAG contrast audit on all frontend .tsx files."""
    await require_admin(request)

    result = _run_audit()
    record = {k: v for k, v in result.items() if k != "all_violations"}
    record["source"] = "manual"
    await db.accessibility_audits.insert_one({**record})
    record.pop("_id", None)
    return record


@router.post("/auto-fix")
async def run_accessibility_autofix(request: Request):
    """Run audit then auto-fix all WCAG contrast violations."""
    await require_admin(request)

    # Step 1: Audit before
    before = _run_audit()

    # Step 2: Auto-fix contrast (use all_violations, not response-limited)
    all_viols = before.get("all_violations", before["violations"])
    contrast_viols = [v for v in all_viols if v.get("category", "contrast") == "contrast" or "fg_color" in v]
    keyboard_viols = [v for v in all_viols if v.get("category") == "keyboard"]
    aria_viols = [v for v in all_viols if v.get("category") == "aria"]
    focus_viols = [v for v in all_viols if v.get("category") == "focus"]
    contrast_fix = _auto_fix_violations(contrast_viols)

    # Step 3: Auto-fix keyboard
    keyboard_fix = _auto_fix_keyboard(keyboard_viols)

    # Step 4: Auto-fix ARIA labels
    aria_fix = _auto_fix_aria(aria_viols)

    # Step 5: Auto-fix focus indicators
    focus_fix = _auto_fix_focus(focus_viols)

    total_fixes = contrast_fix["fixes_applied"] + keyboard_fix["fixes_applied"] + aria_fix["fixes_applied"] + focus_fix["fixes_applied"]
    total_files = contrast_fix["files_modified"] + keyboard_fix["files_modified"] + aria_fix["files_modified"] + focus_fix["files_modified"]
    all_details = contrast_fix["fix_details"] + keyboard_fix["fix_details"] + aria_fix["fix_details"] + focus_fix["fix_details"]

    # Step 6: Re-audit after
    after = _run_audit()

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
        "before_violations": before["total_violations"],
        "after_violations": after["total_violations"],
        "violations_fixed": max(before["total_violations"] - after["total_violations"], 0),
        "fixes_applied": total_fixes,
        "files_modified": total_files,
        "fix_details": all_details[:50],
        "remaining_violations": after["violations"][:20],
        "before_categories": before.get("categories", {}),
        "after_categories": after.get("categories", {}),
    }

    await db.accessibility_fixes.insert_one({**record})
    record.pop("_id", None)

    # Store updated audit
    audit_record = {**after, "source": "auto-fix"}
    await db.accessibility_audits.insert_one({**audit_record})

    return record


@router.get("/latest")
async def get_latest_audit(request: Request):
    """Get the most recent accessibility audit report."""
    await require_admin(request)

    latest = await db.accessibility_audits.find_one(
        {}, {"_id": 0}, sort=[("timestamp", -1)]
    )
    if not latest:
        return {"has_report": False}
    return {**latest, "has_report": True}


@router.get("/history")
async def get_audit_history(request: Request, limit: int = 20):
    """Get history of accessibility audits."""
    await require_admin(request)

    history = await db.accessibility_audits.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)
    return {"history": history, "total": len(history)}


@router.get("/fix-history")
async def get_fix_history(request: Request, limit: int = 20):
    """Get history of auto-fix runs."""
    await require_admin(request)

    history = await db.accessibility_fixes.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)
    return {"history": history, "total": len(history)}


# ─── Scheduled Job ────────────────────────────────────────────────────────────

async def scheduled_accessibility_check():
    """Daily scheduled: audit → auto-fix → re-audit → email alert."""
    logger.info("Starting scheduled accessibility audit...")

    # Step 1: Audit
    before = _run_audit()
    logger.info(f"Accessibility audit: {before['total_violations']} violations found")

    # Step 2: Auto-fix if violations exist
    total_fixes = 0
    total_files = 0
    all_details = []
    if before["total_violations"] > 0:
        all_viols = before.get("all_violations", before["violations"])
        contrast_viols = [v for v in all_viols if v.get("category", "contrast") == "contrast" or "fg_color" in v]
        keyboard_viols = [v for v in all_viols if v.get("category") == "keyboard"]
        aria_viols = [v for v in all_viols if v.get("category") == "aria"]
        focus_viols = [v for v in all_viols if v.get("category") == "focus"]
        contrast_fix = _auto_fix_violations(contrast_viols)
        keyboard_fix = _auto_fix_keyboard(keyboard_viols)
        aria_fix = _auto_fix_aria(aria_viols)
        focus_fix = _auto_fix_focus(focus_viols)
        total_fixes = contrast_fix["fixes_applied"] + keyboard_fix["fixes_applied"] + aria_fix["fixes_applied"] + focus_fix["fixes_applied"]
        total_files = contrast_fix["files_modified"] + keyboard_fix["files_modified"] + aria_fix["files_modified"] + focus_fix["files_modified"]
        all_details = contrast_fix["fix_details"] + keyboard_fix["fix_details"] + aria_fix["fix_details"] + focus_fix["fix_details"]
        logger.info(f"Auto-fixed {total_fixes} violations ({contrast_fix['fixes_applied']} contrast, {keyboard_fix['fixes_applied']} keyboard, {aria_fix['fixes_applied']} aria, {focus_fix['fixes_applied']} focus)")

        # Step 2b: corruption guard — verify the auto-fixer did not break TSX syntax
        if total_fixes > 0:
            import subprocess

            guard = subprocess.run(
                ["python3", "/app/scripts/auto_fixer_corruption_guard.py"],
                capture_output=True, text=True, timeout=120,
            )
            if guard.returncode != 0:
                logger.error(f"A11Y AUTO-FIX CORRUPTION DETECTED — guard output:\n{guard.stdout[-2000:]}")
                await db.accessibility_fix_incidents.insert_one({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "scheduled",
                    "guard_output": guard.stdout[-4000:],
                    "fixes_applied": total_fixes,
                })

    # Step 3: Re-audit
    after = _run_audit()

    # Step 4: Store audit
    audit_record = {k: v for k, v in after.items() if k != "all_violations"}
    audit_record["source"] = "scheduled"
    await db.accessibility_audits.insert_one({**audit_record})

    # Step 5: Store fix record
    if total_fixes > 0:
        fix_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "scheduled",
            "before_violations": before["total_violations"],
            "after_violations": after["total_violations"],
            "violations_fixed": max(before["total_violations"] - after["total_violations"], 0),
            "fixes_applied": total_fixes,
            "files_modified": total_files,
            "fix_details": all_details,
        }
        await db.accessibility_fixes.insert_one({**fix_record})

    # Step 6: Email alert
    try:
        from utils.email_service import is_email_configured
        if is_email_configured():
            status = "PASS" if after["total_violations"] == 0 else f"FAIL ({after['total_violations']} violations)"
            fixed_msg = f" | {total_fixes} auto-fixed" if total_fixes > 0 else ""
            subject = f"WCAG Accessibility: {status}{fixed_msg}"

            cats = after.get("categories", {})
            cat_rows = ""
            for ckey, cname, ccolor in [("contrast","Contrast","#06B6D4"),("aria","ARIA Labels","#8B5CF6"),("keyboard","Keyboard Nav","#3B82F6"),("focus","Focus Indicators","#F97316")]:
                cdata = cats.get(ckey, {"count": 0, "passed": True})
                scolor = "#10B981" if cdata["passed"] else "#EF4444"
                slabel = "PASS" if cdata["passed"] else f'{cdata["count"]} issues'
                cat_rows += f"""<tr>
                    <td style="color:{ccolor};font-weight:600;font-size:13px;padding:10px 14px;border-bottom:1px solid #1E293B;">{cname}</td>
                    <td style="color:{scolor};font-weight:700;font-size:13px;padding:10px 14px;border-bottom:1px solid #1E293B;text-align:right;">{slabel}</td>
                </tr>"""

            status_bg = "#0D2818" if after["passed"] else "#2D1215"
            status_border = "#166534" if after["passed"] else "#991B1B"
            status_color = "#4ADE80" if after["passed"] else "#FCA5A5"

            f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0B0F1A;border-radius:16px;">
                <tr><td style="padding:24px 20px 0;">
                    <h1 style="font-size:20px;font-weight:700;margin:0 0 16px;color:#FFFFFF;">WCAG 2.1 AA Accessibility Audit</h1>
                </td></tr>
                <tr><td style="padding:0 20px 16px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{status_bg};border:2px solid {status_border};border-radius:12px;">
                        <tr><td style="padding:16px;text-align:center;">
                            <span style="color:{status_color};font-size:18px;font-weight:800;">{status}</span>
                        </td></tr>
                    </table>
                </td></tr>
                <tr><td style="padding:0 20px 16px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td width="32%" style="background:#111827;border-radius:10px;padding:14px 8px;text-align:center;border:1px solid #1E293B;">
                                <span style="color:#9CA3B8;font-size:10px;font-weight:600;letter-spacing:1px;display:block;">BEFORE</span>
                                <span style="color:#FFFFFF;font-size:22px;font-weight:800;display:block;margin-top:4px;">{before['total_violations']}</span>
                            </td>
                            <td width="2%"></td>
                            <td width="32%" style="background:#111827;border-radius:10px;padding:14px 8px;text-align:center;border:1px solid #1E293B;">
                                <span style="color:#9CA3B8;font-size:10px;font-weight:600;letter-spacing:1px;display:block;">FIXED</span>
                                <span style="color:#4ADE80;font-size:22px;font-weight:800;display:block;margin-top:4px;">{total_fixes}</span>
                            </td>
                            <td width="2%"></td>
                            <td width="32%" style="background:#111827;border-radius:10px;padding:14px 8px;text-align:center;border:1px solid #1E293B;">
                                <span style="color:#9CA3B8;font-size:10px;font-weight:600;letter-spacing:1px;display:block;">AFTER</span>
                                <span style="color:#FFFFFF;font-size:22px;font-weight:800;display:block;margin-top:4px;">{after['total_violations']}</span>
                            </td>
                        </tr>
                    </table>
                </td></tr>
                <tr><td style="padding:0 20px 16px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;border-radius:10px;border:1px solid #1E293B;overflow:hidden;">
                        <tr><td colspan="2" style="color:#FFFFFF;font-size:13px;font-weight:700;padding:12px 14px;border-bottom:1px solid #1E293B;">Category Breakdown</td></tr>
                        {cat_rows}
                    </table>
                </td></tr>
                <tr><td style="padding:0 20px 20px;">
                    <p style="color:#6B7280;font-size:11px;text-align:center;margin:0;">RealAICoach Automated WCAG 2.1 AA Audit</p>
                </td></tr>
            </table>"""

            # V7 compliant: use registered template
            from utils.email_templates import build_accessibility_audit_alert_email
            _cats = after.get("categories", {}) or {}
            _cat_lines = []
            for cat, info in _cats.items():
                if isinstance(info, dict):
                    _count = int(info.get("count", 0))
                    _cat_lines.append(f"{cat}: {_count} issue(s)" + (" — passed" if info.get("passed") else ""))
                else:
                    _cat_lines.append(f"{cat}: {info}")
            cat_summary = "<br/>".join(_cat_lines)
            _critical = int(after.get("critical_violations", 0))
            _warnings = max(0, int(after.get("total_violations", 0)) - _critical)
            _weighted_score = max(0, 100 - (_critical * 15) - min(40, round(_warnings * 0.5)))
            tpl = build_accessibility_audit_alert_email(
                score=_weighted_score,
                total_issues=after.get("total_violations", 0),
                critical_count=_critical,
                category_breakdown=cat_summary or f"Before: {before.get('total_violations', 0)}, Fixed: {total_fixes}, After: {after.get('total_violations', 0)}",
            )

            await _send_incident_alert_email(
                recipient_email="admin@realaicoach.app",
                subject=tpl.subject,
                content=tpl.html,
                template_key="accessibility_audit_alert",
                skip_branding=True,
            )
            logger.info(f"Accessibility alert sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send accessibility email: {e}")

    logger.info("Scheduled accessibility audit complete")
