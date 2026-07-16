from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional


class GpsEventBus:
    def __init__(self):
        self._subscribers: List[Any] = []

    def subscribe(self, subscriber):
        self._subscribers.append(subscriber)

    async def publish(self, event: Dict[str, Any], logger):
        for subscriber in list(self._subscribers):
            try:
                result = subscriber(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("GPS subscriber error: %s", exc)


async def publish_gps_event_record(
    *,
    db: Any,
    event_bus: GpsEventBus,
    broadcast_data_change,
    enqueue_notifications,
    logger,
    now_iso,
    gps_state_id: str,
    event_type: str,
    what_changed: str,
    why_changed: str,
    impact: str,
    metadata: Optional[Dict[str, Any]] = None,
    actor_user_id: str = "",
) -> Dict[str, Any]:
    refresh_ts = now_iso()
    await db.global_platform_state.update_one(
        {"state_id": gps_state_id},
        {"$set": {"assistant_knowledge.last_refreshed_at": refresh_ts, "updated_at": refresh_ts}},
        upsert=True,
    )

    event = {
        "event_id": f"gps_evt_{uuid.uuid4().hex[:12]}",
        "event_type": event_type,
        "what_changed": what_changed,
        "why_changed": why_changed,
        "impact": impact,
        "metadata": metadata or {},
        "actor_user_id": actor_user_id,
        "created_at": refresh_ts,
    }
    await db.global_platform_events.insert_one(event)
    event.pop("_id", None)
    await event_bus.publish(event, logger)
    await broadcast_data_change("gps", "updated", extra={"event_type": event_type, "event_id": event["event_id"]})
    await broadcast_data_change("config", "updated", extra={"event_type": event_type, "event_id": event["event_id"]})
    asyncio.create_task(enqueue_notifications(event))
    return event


async def persist_and_emit_state(
    *,
    db: Any,
    gps_state_id: str,
    now_iso,
    build_meta,
    store_snapshot,
    publish_event,
    payment_monitor,
    state: Dict[str, Any],
    event_type: str,
    what_changed: str,
    why_changed: str,
    impact: str,
    actor_user_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state["version"] = int(state.get("version", 1)) + 1
    state["updated_at"] = now_iso()
    state["meta"] = build_meta(state)
    await db.global_platform_state.update_one({"state_id": gps_state_id}, {"$set": state}, upsert=True)
    await store_snapshot(state=state, actor_user_id=actor_user_id, event_type=event_type, reason=why_changed)
    await publish_event(
        event_type=event_type,
        what_changed=what_changed,
        why_changed=why_changed,
        impact=impact,
        metadata=metadata or {"version": state["version"]},
        actor_user_id=actor_user_id,
    )
    if event_type == "PlanChanged":
        asyncio.create_task(payment_monitor())
    return state


async def sync_features_from_registry(
    *,
    db: Any,
    gps_state_id: str,
    get_state,
    sanitize_features,
    build_meta,
    now_iso,
    publish_event,
    payment_monitor,
    reason: str,
    actor_user_id: str,
    event_type: str,
) -> Dict[str, Any]:
    state = await get_state()
    registry = await db.feature_registry.find({}, {"_id": 0}).sort("sort_order", 1).to_list(1000)
    state["features"] = sanitize_features(registry)
    state["version"] = int(state.get("version", 1)) + 1
    state["updated_at"] = now_iso()
    state["meta"] = build_meta(state)
    await db.global_platform_state.update_one(
        {"state_id": gps_state_id},
        {"$set": {"features": state["features"], "version": state["version"], "updated_at": state["updated_at"], "meta": state["meta"]}},
        upsert=True,
    )
    if reason:
        await publish_event(
            event_type=event_type,
            what_changed="Feature catalog synchronized",
            why_changed=reason,
            impact="Feature index, help center, and Nova now reflect the latest feature state.",
            metadata={"total_features": len(state["features"])},
            actor_user_id=actor_user_id,
        )
        asyncio.create_task(payment_monitor())
    return state


async def sync_faq_from_source(*, db: Any, gps_state_id: str, get_state, sanitize_faq, build_meta, now_iso, publish_event, reason: str, actor_user_id: str) -> Dict[str, Any]:
    state = await get_state()
    faq_rows = await db.faq_content.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(1000)
    state["faq"] = sanitize_faq(faq_rows)
    state["version"] = int(state.get("version", 1)) + 1
    state["updated_at"] = now_iso()
    state["meta"] = build_meta(state)
    await db.global_platform_state.update_one(
        {"state_id": gps_state_id},
        {"$set": {"faq": state["faq"], "version": state["version"], "updated_at": state["updated_at"], "meta": state["meta"]}},
        upsert=True,
    )
    if reason:
        await publish_event(
            event_type="ContentUpdated",
            what_changed="FAQ knowledge base synchronized",
            why_changed=reason,
            impact="Help, FAQ, and Nova answers now use latest support content.",
            metadata={"total_faq": len(state["faq"])},
            actor_user_id=actor_user_id,
        )
    return state


async def sync_plans_from_source(*, db: Any, gps_state_id: str, get_state, sanitize_plans, build_meta, now_iso, publish_event, reason: str, actor_user_id: str) -> Dict[str, Any]:
    state = await get_state()
    plans_rows = await db.subscription_plans.find({}, {"_id": 0}).to_list(500)
    if plans_rows:
        state["plans"] = sanitize_plans(plans_rows)
    elif not (state.get("plans") or []):
        candidates = await db.gps_state_versions.find(
            {"state.plans.0": {"$exists": True}},
            {"_id": 0, "state.plans": 1, "created_at": 1},
        ).sort("created_at", -1).limit(100).to_list(100)
        recovered = []
        for candidate in candidates:
            candidate_plans = ((candidate or {}).get("state") or {}).get("plans") or []
            stable_plans = [p for p in candidate_plans if not str(p.get("plan_id") or p.get("id") or "").lower().startswith(("iter", "test"))]
            if stable_plans:
                recovered = stable_plans
                break
        state["plans"] = sanitize_plans(recovered)
    state["version"] = int(state.get("version", 1)) + 1
    state["updated_at"] = now_iso()
    state["meta"] = build_meta(state)
    await db.global_platform_state.update_one(
        {"state_id": gps_state_id},
        {"$set": {"plans": state["plans"], "version": state["version"], "updated_at": state["updated_at"], "meta": state["meta"]}},
        upsert=True,
    )
    if reason:
        await publish_event(
            event_type="PlanChanged",
            what_changed="Subscription plans synchronized",
            why_changed=reason,
            impact="Pricing and upgrade prompts now use latest plan definitions.",
            metadata={"total_plans": len(state["plans"])},
            actor_user_id=actor_user_id,
        )
    return state