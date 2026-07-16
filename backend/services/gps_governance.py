from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional


def can_publish_changes(user: Any) -> bool:
    email = str(getattr(user, "email", "") or "").lower()
    role = str(getattr(user, "role", "") or "").lower()
    privileged_roles = {"admin", "owner", "super_admin", "platform_owner", "root_admin"}
    return role in privileged_roles or email == "admin@realaicoach.app"


def user_scope(user: Any) -> str:
    return "publisher" if can_publish_changes(user) else "reviewer"


def is_high_impact_change(entity_type: str, operation: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    entity = str(entity_type or "").strip().lower()
    op = str(operation or "").strip().lower()
    payload = payload or {}

    if entity in {"plan", "global_state", "state", "rollback"}:
        return True
    if op in {"bulk_import", "replace", "partial_update", "rollback_to_version"}:
        return True
    if entity == "ui_label" and op == "upsert":
        key = str(payload.get("key") or "").lower()
        return key.startswith(("home.", "help.", "features.", "notifications.", "common.", "pricing.", "checkout."))
    return False


async def create_change_request(
    *,
    db: Any,
    now_iso,
    user: Any,
    entity_type: str,
    operation: str,
    payload: Dict[str, Any],
    reason: str,
    workflow_mode: str,
    requires_peer_review: bool = False,
) -> Dict[str, Any]:
    status = "review" if workflow_mode == "review" else "draft"
    creator_id = getattr(user, "user_id", "unknown")
    doc = {
        "request_id": f"gps_req_{uuid.uuid4().hex[:12]}",
        "entity_type": entity_type,
        "operation": operation,
        "payload": payload,
        "reason": reason or "GPS change request",
        "workflow_mode": workflow_mode,
        "status": status,
        "created_by": creator_id,
        "created_by_email": getattr(user, "email", ""),
        "created_by_scope": user_scope(user),
        "requires_peer_review": bool(requires_peer_review),
        "maker_checker_lock": bool(requires_peer_review),
        "approval_policy": "two_person_publish" if requires_peer_review else "standard",
        "risk_level": "high" if requires_peer_review else "standard",
        "cannot_be_published_by": [creator_id] if requires_peer_review else [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.gps_change_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


def snapshot_state_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(state))


async def store_state_version_snapshot(
    *,
    db: Any,
    now_iso,
    build_meta,
    state: Dict[str, Any],
    actor_user_id: str,
    event_type: str,
    reason: str,
):
    snapshot = {
        "version_id": f"gps_ver_{uuid.uuid4().hex[:12]}",
        "version": int(state.get("version", 1)),
        "event_type": event_type,
        "reason": reason,
        "actor_user_id": actor_user_id,
        "state": snapshot_state_payload(state),
        "meta": build_meta(state),
        "created_at": now_iso(),
    }
    await db.gps_state_versions.insert_one(snapshot)


def compute_state_diff(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    current_features = {f.get("feature_id") for f in (current.get("features") or [])}
    previous_features = {f.get("feature_id") for f in (previous.get("features") or [])}
    current_plans = {p.get("plan_id") for p in (current.get("plans") or [])}
    previous_plans = {p.get("plan_id") for p in (previous.get("plans") or [])}
    current_faq = {f.get("faq_id") for f in (current.get("faq") or [])}
    previous_faq = {f.get("faq_id") for f in (previous.get("faq") or [])}

    return {
        "counts": {
            "features": {"from": len(previous_features), "to": len(current_features)},
            "plans": {"from": len(previous_plans), "to": len(current_plans)},
            "faq": {"from": len(previous_faq), "to": len(current_faq)},
        },
        "features": {
            "added": sorted([x for x in current_features - previous_features if x]),
            "removed": sorted([x for x in previous_features - current_features if x]),
        },
        "plans": {
            "added": sorted([x for x in current_plans - previous_plans if x]),
            "removed": sorted([x for x in previous_plans - current_plans if x]),
        },
        "faq": {
            "added": sorted([x for x in current_faq - previous_faq if x]),
            "removed": sorted([x for x in previous_faq - current_faq if x]),
        },
        "labels_changed": len((current.get("ui_labels") or {}).keys() ^ (previous.get("ui_labels") or {}).keys()),
    }