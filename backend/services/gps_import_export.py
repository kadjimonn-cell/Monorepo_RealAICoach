from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict


def select_export_data(state: Dict[str, Any], section: str):
    section = section.lower()
    if section == "full":
        return state
    if section == "features":
        return state.get("features") or []
    if section == "plans":
        return state.get("plans") or []
    if section == "faq":
        return state.get("faq") or []
    if section == "labels":
        return state.get("ui_labels") or {}
    if section == "knowledge":
        return (state.get("assistant_knowledge") or {}).get("documents") or []
    raise ValueError("Unsupported section")


def render_csv(data: Any) -> str:
    rows = data if isinstance(data, list) else [{"key": k, "value": v} for k, v in (data or {}).items()]
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return output.getvalue()


def parse_import_content(content: str, fmt: str):
    fmt = fmt.lower()
    if fmt == "json":
        return json.loads(content or "{}")
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(content or ""))
        return [dict(row) for row in reader]
    raise ValueError("Unsupported import format")


def apply_import_to_state(
    *,
    state: Dict[str, Any],
    section: str,
    parsed: Any,
    gps_state_id: str,
    sanitize_features,
    sanitize_plans,
    sanitize_faq,
    now_iso,
) -> Dict[str, Any]:
    section = section.lower()
    if section == "full":
        if not isinstance(parsed, dict):
            raise ValueError("Full JSON import requires object")
        return {**state, **parsed, "state_id": gps_state_id}
    if section == "features":
        state["features"] = sanitize_features(parsed if isinstance(parsed, list) else [])
    elif section == "plans":
        state["plans"] = sanitize_plans(parsed if isinstance(parsed, list) else [])
    elif section == "faq":
        state["faq"] = sanitize_faq(parsed if isinstance(parsed, list) else [])
    elif section == "labels":
        if isinstance(parsed, dict):
            state["ui_labels"] = {str(k): str(v) for k, v in parsed.items()}
        elif isinstance(parsed, list):
            state["ui_labels"] = {str(item.get("key")): str(item.get("value", "")) for item in parsed if item.get("key")}
    elif section == "knowledge":
        state["assistant_knowledge"] = {"documents": parsed if isinstance(parsed, list) else [], "last_refreshed_at": now_iso()}
    else:
        raise ValueError("Unsupported import section")
    return state