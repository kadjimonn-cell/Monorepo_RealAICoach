from __future__ import annotations

import uuid
from typing import Any, Dict


async def check_and_optionally_repair_consistency(
    *,
    db: Any,
    gps_state_id: str,
    state: Dict[str, Any],
    ui_snapshot: Dict[str, Any],
    auto_correct: bool,
    user_id: str,
    build_meta,
    now_iso,
) -> Dict[str, Any]:
    canonical = {
        "feature_count": len([f for f in (state.get("features") or []) if f.get("enabled", True)]),
        "plan_count": len([p for p in (state.get("plans") or []) if p.get("status") != "deprecated"]),
        "faq_count": len([f for f in (state.get("faq") or []) if f.get("active", True)]),
        "version": state.get("version", 1),
    }

    mismatches = []
    for key in ("feature_count", "plan_count", "faq_count", "version"):
        client_val = ui_snapshot.get(key)
        if client_val is None:
            continue
        if client_val != canonical[key]:
            mismatches.append({"key": key, "ui": client_val, "gps": canonical[key]})

    corrected = False
    if auto_correct and state.get("meta", {}).get("counts", {}).get("features") != canonical["feature_count"]:
        state["meta"] = build_meta(state)
        state["updated_at"] = now_iso()
        await db.global_platform_state.update_one(
            {"state_id": gps_state_id},
            {"$set": {"meta": state["meta"], "updated_at": state["updated_at"]}},
            upsert=True,
        )
        corrected = True

    log_doc = {
        "log_id": f"gps_consistency_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "ui_snapshot": ui_snapshot,
        "canonical": canonical,
        "mismatches": mismatches,
        "auto_corrected": corrected,
        "created_at": now_iso(),
    }
    await db.global_platform_consistency_logs.insert_one(log_doc)

    return {
        "canonical": canonical,
        "mismatches": mismatches,
        "auto_corrected": corrected,
        "log_id": log_doc["log_id"],
    }