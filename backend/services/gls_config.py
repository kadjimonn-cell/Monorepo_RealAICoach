from __future__ import annotations

from typing import Any, Dict


GLS_DEFAULTS: Dict[str, Any] = {
    "max_width": 1240,
    "max_width_wide": 1440,
    "max_width_narrow": 960,
    "padding_mobile": 18,
    "padding_tablet": 28,
    "padding_desktop": 32,
    "padding_large": 40,
    "section_padding_mobile": 48,
    "section_padding_tablet": 64,
    "section_padding_desktop": 80,
    "breakpoint_tablet": 768,
    "breakpoint_desktop": 1024,
    "breakpoint_large": 1440,
    "layout_mode": "centered",
    "responsive_enabled": True,
}


def normalize_gls_config(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    merged = {**GLS_DEFAULTS}

    int_keys = {
        "max_width",
        "max_width_wide",
        "max_width_narrow",
        "padding_mobile",
        "padding_tablet",
        "padding_desktop",
        "padding_large",
        "section_padding_mobile",
        "section_padding_tablet",
        "section_padding_desktop",
        "breakpoint_tablet",
        "breakpoint_desktop",
        "breakpoint_large",
    }

    for key in GLS_DEFAULTS.keys():
        if key not in source:
            continue
        value = source.get(key)
        if key in int_keys:
            try:
                merged[key] = int(value)
            except Exception:
                continue
            continue
        if key == "responsive_enabled":
            merged[key] = bool(value)
            continue
        if key == "layout_mode":
            layout_mode = str(value or "").strip().lower()
            if layout_mode in {"centered", "full-width", "compact"}:
                merged[key] = layout_mode

    if merged["breakpoint_tablet"] < 600:
        merged["breakpoint_tablet"] = 600
    if merged["breakpoint_desktop"] <= merged["breakpoint_tablet"]:
        merged["breakpoint_desktop"] = merged["breakpoint_tablet"] + 1
    if merged["breakpoint_large"] <= merged["breakpoint_desktop"]:
        merged["breakpoint_large"] = merged["breakpoint_desktop"] + 1

    if merged["max_width_narrow"] > merged["max_width"]:
        merged["max_width_narrow"] = merged["max_width"]
    if merged["max_width"] > merged["max_width_wide"]:
        merged["max_width"] = merged["max_width_wide"]

    return merged
