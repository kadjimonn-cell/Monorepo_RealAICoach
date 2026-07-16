"""Global Platform State (GPS) — single source of truth for dynamic platform content."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from routes.notification_engine import emit_notification
from services import gps_crud_handlers
from services.gps_compliance import run_stale_count_scan as execute_stale_count_scan
from services.gps_events_sync import (
    GpsEventBus,
    persist_and_emit_state,
    publish_gps_event_record,
    sync_faq_from_source,
    sync_features_from_registry,
    sync_plans_from_source,
)
from services.gps_governance import (
    can_publish_changes as governance_can_publish_changes,
    compute_state_diff,
    create_change_request as governance_create_change_request,
    snapshot_state_payload,
    store_state_version_snapshot,
    user_scope as governance_user_scope,
)
from services.gps_outbox import (
    enqueue_change_notifications,
    notification_title_for_event,
    process_notification_outbox,
    reconcile_notification_outbox,
)
from services.gps_payment_monitor import build_payment_plan_drift_report
from services.gps_self_healing import align_faq_feature_count_claims, record_self_healing_audit
from services.gps_state_core import (
    build_meta as _build_meta,
    ensure_strict_surface_label_pack as _ensure_strict_surface_label_pack,
    ensure_welcome_messaging_pack as _ensure_welcome_messaging_pack,
    sanitize_faq as _sanitize_faq,
    sanitize_features as _sanitize_features,
    sanitize_plans as _sanitize_plans,
)
from services.gls_config import GLS_DEFAULTS as _GLS_DEFAULTS, normalize_gls_config as _normalize_gls_config
from utils.ws_manager import broadcast_data_change

logger = logging.getLogger("routes.global_platform_state")

router = APIRouter(prefix="/gps", tags=["Global Platform State"])

GPS_STATE_ID = "global-platform-state"
GPS_OUTBOX_MAX_RETRIES = 7

GPS_THEME_POLICY_DEFAULTS: Dict[str, Any] = {
    "pages_theme_version": "v2",
    "email_theme_version": "v7",
    "pdf_theme_version": "v15",
    "pages_theme_enforcement": "mandatory_no_bypass",
    "gls_enforcement": "mandatory",
    "responsive_enforcement": "mandatory",
    "i18n_auto_translate_enforcement": "mandatory",
    "strict_no_bypass": True,
    "strict_route_prefixes": ["/certificate", "/settings", "/profile"],
}


def _normalize_theme_policy(raw_policy: Any) -> Dict[str, Any]:
    policy = dict(GPS_THEME_POLICY_DEFAULTS)
    if isinstance(raw_policy, dict):
        strict_routes = raw_policy.get("strict_route_prefixes")
        if isinstance(strict_routes, list):
            cleaned = [str(route).strip() for route in strict_routes if str(route).strip().startswith("/")]
            if cleaned:
                policy["strict_route_prefixes"] = sorted(set(cleaned))

    # Non-bypass contract is mandatory and immutable at runtime.
    policy["pages_theme_version"] = "v2"
    policy["email_theme_version"] = "v7"
    policy["pdf_theme_version"] = "v15"
    policy["pages_theme_enforcement"] = "mandatory_no_bypass"
    policy["gls_enforcement"] = "mandatory"
    policy["responsive_enforcement"] = "mandatory"
    policy["i18n_auto_translate_enforcement"] = "mandatory"
    policy["strict_no_bypass"] = True
    return policy


def _apply_theme_policy_contract(state: Dict[str, Any]) -> bool:
    normalized = _normalize_theme_policy(state.get("theme_policy"))
    changed = False

    if state.get("theme_policy") != normalized:
        state["theme_policy"] = normalized
        changed = True

    contract_projection = {
        "theme_version": normalized["pages_theme_version"],
        "email_theme_version": normalized["email_theme_version"],
        "pdf_theme_version": normalized["pdf_theme_version"],
        "i18n_auto_translate": True,
        "responsive_enforcement": True,
        "gls_enforcement": True,
    }
    for key, value in contract_projection.items():
        if state.get(key) != value:
            state[key] = value
            changed = True

    return changed

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_stale_count_scan() -> Dict[str, Any]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "gps_stale_count_scanner.py"
    return execute_stale_count_scan(script)


async def _build_payment_plan_drift_report() -> Dict[str, Any]:
    state = await get_global_platform_state()
    return await build_payment_plan_drift_report(db, state, _now_iso)


def _can_publish_changes(user: Any) -> bool:
    return governance_can_publish_changes(user)


def _user_scope(user: Any) -> str:
    return governance_user_scope(user)


async def _create_change_request(
    *,
    user: Any,
    entity_type: str,
    operation: str,
    payload: Dict[str, Any],
    reason: str,
    workflow_mode: str,
    requires_peer_review: bool = False,
) -> Dict[str, Any]:
    return await governance_create_change_request(
        db=db,
        now_iso=_now_iso,
        user=user,
        entity_type=entity_type,
        operation=operation,
        payload=payload,
        reason=reason,
        workflow_mode=workflow_mode,
        requires_peer_review=requires_peer_review,
    )


def _snapshot_state_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    return snapshot_state_payload(state)


async def _store_state_version_snapshot(
    *,
    state: Dict[str, Any],
    actor_user_id: str,
    event_type: str,
    reason: str,
):
    await store_state_version_snapshot(
        db=db,
        now_iso=_now_iso,
        build_meta=_build_meta,
        state=state,
        actor_user_id=actor_user_id,
        event_type=event_type,
        reason=reason,
    )


def _compute_state_diff(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    return compute_state_diff(current, previous)


async def _bootstrap_state_from_live_data() -> Dict[str, Any]:
    now = _now_iso()
    features_raw = await db.feature_registry.find({}, {"_id": 0}).sort("sort_order", 1).to_list(1000)
    plans_raw = await db.subscription_plans.find({}, {"_id": 0}).to_list(200)
    faq_raw = await db.faq_content.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(1000)
    labels_raw = await db.platform_ui_labels.find({}, {"_id": 0, "key": 1, "value": 1}).to_list(500)
    messages_raw = await db.platform_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    knowledge_raw = await db.platform_knowledge.find({}, {"_id": 0}).sort("updated_at", -1).to_list(500)
    layout_raw = await db.gls_config.find_one({"config_id": "global-layout"}, {"_id": 0})

    ui_labels = {str(d.get("key") or "").strip(): str(d.get("value") or "") for d in labels_raw if d.get("key")}
    ui_labels, _ = _ensure_strict_surface_label_pack(ui_labels)
    layout_config = _normalize_gls_config(layout_raw)
    messaging = {
        "announcements": [doc for doc in messages_raw if isinstance(doc, dict)],
        "quick_questions": [
            q
            for q in [
                ui_labels.get("nova.quick_question.1", ""),
                ui_labels.get("nova.quick_question.2", ""),
                ui_labels.get("nova.quick_question.3", ""),
            ]
            if q
        ],
    }
    messaging, _ = _ensure_welcome_messaging_pack(messaging)
    state = {
        "state_id": GPS_STATE_ID,
        "version": 1,
        "features": _sanitize_features(features_raw),
        "plans": _sanitize_plans(plans_raw),
        "faq": _sanitize_faq(faq_raw),
        "assistant_knowledge": {
            "documents": [doc for doc in knowledge_raw if isinstance(doc, dict)],
            "last_refreshed_at": now,
        },
        "ui_labels": ui_labels,
        "messaging": messaging,
        "layout_config": layout_config,
        "theme_policy": _normalize_theme_policy(None),
        "theme_version": "v2",
        "email_theme_version": "v7",
        "pdf_theme_version": "v15",
        "i18n_auto_translate": True,
        "responsive_enforcement": True,
        "gls_enforcement": True,
        "updated_at": now,
    }
    state["meta"] = _build_meta(state)
    await db.global_platform_state.update_one({"state_id": GPS_STATE_ID}, {"$set": state}, upsert=True)
    return state


async def get_global_platform_state() -> Dict[str, Any]:
    state = await db.global_platform_state.find_one({"state_id": GPS_STATE_ID}, {"_id": 0})
    if not state:
        state = await _bootstrap_state_from_live_data()

    changed = False
    repairs: List[Dict[str, Any]] = []
    state.setdefault("features", [])
    state.setdefault("plans", [])
    state.setdefault("faq", [])
    state.setdefault("assistant_knowledge", {"documents": [], "last_refreshed_at": _now_iso()})
    state.setdefault("ui_labels", {})
    state.setdefault("messaging", {"announcements": [], "quick_questions": []})
    state.setdefault("layout_config", dict(_GLS_DEFAULTS))
    state.setdefault("theme_policy", _normalize_theme_policy(None))
    state.setdefault("theme_version", "v2")
    state.setdefault("email_theme_version", "v7")
    state.setdefault("pdf_theme_version", "v15")
    state.setdefault("i18n_auto_translate", True)
    state.setdefault("responsive_enforcement", True)
    state.setdefault("gls_enforcement", True)
    state.setdefault("version", 1)
    state.setdefault("updated_at", _now_iso())

    layout_raw = await db.gls_config.find_one({"config_id": "global-layout"}, {"_id": 0})
    next_layout = _normalize_gls_config(layout_raw or state.get("layout_config") or {})
    if state.get("layout_config") != next_layout:
        state["layout_config"] = next_layout
        changed = True
        repairs.append({"type": "layout_config_repair", "layout_mode": next_layout.get("layout_mode")})

    if not (state.get("features") or []):
        registry = await db.feature_registry.find({}, {"_id": 0}).sort("sort_order", 1).to_list(2000)
        if registry:
            state["features"] = _sanitize_features(registry)
            changed = True
            repairs.append({"type": "feature_registry_hydration", "count": len(state["features"])})

    next_plans = _sanitize_plans(state.get("plans") or [])
    if state.get("plans") != next_plans:
        state["plans"] = next_plans
        changed = True
        repairs.append({"type": "subscription_plan_yearly_price_repair", "count": len(next_plans)})

    faq_repairs = align_faq_feature_count_claims(state, _now_iso)
    if faq_repairs:
        changed = True
        repairs.extend(faq_repairs)

    next_labels, labels_changed = _ensure_strict_surface_label_pack(state.get("ui_labels") or {})
    if labels_changed:
        state["ui_labels"] = next_labels
        changed = True
        repairs.append({"type": "strict_surface_label_pack_repair", "label_count": len(next_labels)})

    next_messaging, messaging_changed = _ensure_welcome_messaging_pack(state.get("messaging") or {})
    if messaging_changed:
        state["messaging"] = next_messaging
        changed = True
        repairs.append({"type": "welcome_messaging_pack_repair", "keys": sorted(list(next_messaging.keys()))})

    if _apply_theme_policy_contract(state):
        changed = True
        repairs.append(
            {
                "type": "theme_policy_contract_repair",
                "pages_theme_version": state.get("theme_version"),
                "email_theme_version": state.get("email_theme_version"),
                "pdf_theme_version": state.get("pdf_theme_version"),
            }
        )

    new_meta = _build_meta(state)
    if state.get("meta") != new_meta:
        repairs.append({"type": "meta_count_repair", "before": state.get("meta"), "after": new_meta})
        state["meta"] = new_meta
        changed = True

    if changed:
        await db.global_platform_state.update_one(
            {"state_id": GPS_STATE_ID},
            {"$set": state},
            upsert=True,
        )
        await record_self_healing_audit(db, repairs, _now_iso)
    return state


gps_event_bus = GpsEventBus()


class GpsUpdatePayload(BaseModel):
    features: Optional[List[Dict[str, Any]]] = None
    plans: Optional[List[Dict[str, Any]]] = None
    faq: Optional[List[Dict[str, Any]]] = None
    assistant_knowledge: Optional[Dict[str, Any]] = None
    ui_labels: Optional[Dict[str, str]] = None
    messaging: Optional[Dict[str, Any]] = None
    layout_config: Optional[Dict[str, Any]] = None
    theme_policy: Optional[Dict[str, Any]] = None
    theme_version: Optional[str] = None
    email_theme_version: Optional[str] = None
    pdf_theme_version: Optional[str] = None
    i18n_auto_translate: Optional[bool] = None
    responsive_enforcement: Optional[bool] = None
    gls_enforcement: Optional[bool] = None
    reason: str = ""
    workflow_mode: str = "publish"


class GpsEventPayload(BaseModel):
    event_type: str = Field(pattern="^(FeatureAdded|FeatureRemoved|FeatureUpdated|ContentUpdated|PlanChanged)$")
    what_changed: str
    why_changed: str
    impact: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConsistencyCheckPayload(BaseModel):
    ui_snapshot: Dict[str, Any] = Field(default_factory=dict)
    auto_correct: bool = True


class GpsEntityUpsertPayload(BaseModel):
    item: Dict[str, Any]
    reason: str = ""
    workflow_mode: str = "publish"


class GpsLabelUpsertPayload(BaseModel):
    key: str
    value: str
    reason: str = ""
    workflow_mode: str = "publish"


def _notification_title_for_event(event_type: str) -> str:
    return notification_title_for_event(event_type)


async def _send_change_notifications(event: Dict[str, Any]):
    await enqueue_change_notifications(db, event, _now_iso, logger)


async def process_gps_notification_outbox(batch_size: int = 250, max_cycles: int = 1) -> Dict[str, Any]:
    return await process_notification_outbox(
        db,
        emit_notification,
        _now_iso,
        max_retries=GPS_OUTBOX_MAX_RETRIES,
        batch_size=batch_size,
        max_cycles=max_cycles,
    )


async def reconcile_gps_notification_outbox(limit_events: int = 25) -> Dict[str, Any]:
    return await reconcile_notification_outbox(db, _now_iso, logger, limit_events=limit_events)


async def publish_gps_event(
    *,
    event_type: str,
    what_changed: str,
    why_changed: str,
    impact: str,
    metadata: Optional[Dict[str, Any]] = None,
    actor_user_id: str = "",
) -> Dict[str, Any]:
    return await publish_gps_event_record(
        db=db,
        event_bus=gps_event_bus,
        broadcast_data_change=broadcast_data_change,
        enqueue_notifications=_send_change_notifications,
        logger=logger,
        now_iso=_now_iso,
        gps_state_id=GPS_STATE_ID,
        event_type=event_type,
        what_changed=what_changed,
        why_changed=why_changed,
        impact=impact,
        metadata=metadata,
        actor_user_id=actor_user_id,
    )


async def _persist_and_emit(
    *,
    state: Dict[str, Any],
    event_type: str,
    what_changed: str,
    why_changed: str,
    impact: str,
    actor_user_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return await persist_and_emit_state(
        db=db,
        gps_state_id=GPS_STATE_ID,
        now_iso=_now_iso,
        build_meta=_build_meta,
        store_snapshot=_store_state_version_snapshot,
        publish_event=publish_gps_event,
        payment_monitor=_build_payment_plan_drift_report,
        state=state,
        event_type=event_type,
        what_changed=what_changed,
        why_changed=why_changed,
        impact=impact,
        actor_user_id=actor_user_id,
        metadata=metadata,
    )


async def sync_global_features(
    reason: str = "Feature registry sync",
    actor_user_id: str = "",
    event_type: str = "FeatureUpdated",
) -> Dict[str, Any]:
    return await sync_features_from_registry(
        db=db,
        gps_state_id=GPS_STATE_ID,
        get_state=get_global_platform_state,
        sanitize_features=_sanitize_features,
        build_meta=_build_meta,
        now_iso=_now_iso,
        publish_event=publish_gps_event,
        payment_monitor=_build_payment_plan_drift_report,
        reason=reason,
        actor_user_id=actor_user_id,
        event_type=event_type,
    )


async def sync_global_faq(reason: str = "FAQ sync", actor_user_id: str = "") -> Dict[str, Any]:
    return await sync_faq_from_source(
        db=db,
        gps_state_id=GPS_STATE_ID,
        get_state=get_global_platform_state,
        sanitize_faq=_sanitize_faq,
        build_meta=_build_meta,
        now_iso=_now_iso,
        publish_event=publish_gps_event,
        reason=reason,
        actor_user_id=actor_user_id,
    )


async def sync_global_plans(reason: str = "Plan sync", actor_user_id: str = "") -> Dict[str, Any]:
    return await sync_plans_from_source(
        db=db,
        gps_state_id=GPS_STATE_ID,
        get_state=get_global_platform_state,
        sanitize_plans=_sanitize_plans,
        build_meta=_build_meta,
        now_iso=_now_iso,
        publish_event=publish_gps_event,
        reason=reason,
        actor_user_id=actor_user_id,
    )


@router.post("/admin/features/upsert")
async def upsert_feature(payload: GpsEntityUpsertPayload, request: Request):
    user = await require_admin(request)
    return await gps_crud_handlers.upsert_feature(
        payload=payload,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
        sanitize_features=_sanitize_features,
        now_iso=_now_iso,
    )


@router.delete("/admin/features/{feature_id}")
async def delete_feature(feature_id: str, request: Request, reason: str = "", workflow_mode: str = "publish"):
    user = await require_admin(request)
    return await gps_crud_handlers.delete_feature(
        feature_id=feature_id,
        reason=reason,
        workflow_mode=workflow_mode,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
    )


@router.post("/admin/plans/upsert")
async def upsert_plan(payload: GpsEntityUpsertPayload, request: Request):
    user = await require_admin(request)
    return await gps_crud_handlers.upsert_plan(
        payload=payload,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
        sanitize_plans=_sanitize_plans,
        now_iso=_now_iso,
    )


@router.delete("/admin/plans/{plan_id}")
async def delete_plan(plan_id: str, request: Request, reason: str = "", workflow_mode: str = "publish"):
    user = await require_admin(request)
    return await gps_crud_handlers.delete_plan(
        plan_id=plan_id,
        reason=reason,
        workflow_mode=workflow_mode,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
    )


@router.post("/admin/faq/upsert")
async def upsert_faq(payload: GpsEntityUpsertPayload, request: Request):
    user = await require_admin(request)
    return await gps_crud_handlers.upsert_faq(
        payload=payload,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
        sanitize_faq=_sanitize_faq,
        now_iso=_now_iso,
    )


@router.delete("/admin/faq/{faq_id}")
async def delete_faq(faq_id: str, request: Request, reason: str = "", workflow_mode: str = "publish"):
    user = await require_admin(request)
    return await gps_crud_handlers.delete_faq(
        faq_id=faq_id,
        reason=reason,
        workflow_mode=workflow_mode,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
    )


@router.put("/admin/ui-label")
async def upsert_ui_label(payload: GpsLabelUpsertPayload, request: Request):
    user = await require_admin(request)
    return await gps_crud_handlers.upsert_ui_label(
        payload=payload,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
    )


@router.delete("/admin/ui-label/{key}")
async def delete_ui_label(key: str, request: Request, reason: str = "", workflow_mode: str = "publish"):
    user = await require_admin(request)
    return await gps_crud_handlers.delete_ui_label(
        key=key,
        reason=reason,
        workflow_mode=workflow_mode,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
    )


@router.post("/admin/knowledge/upsert")
async def upsert_knowledge(payload: GpsEntityUpsertPayload, request: Request):
    user = await require_admin(request)
    return await gps_crud_handlers.upsert_knowledge(
        payload=payload,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
        now_iso=_now_iso,
    )


@router.delete("/admin/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str, request: Request, reason: str = "", workflow_mode: str = "publish"):
    user = await require_admin(request)
    return await gps_crud_handlers.delete_knowledge(
        doc_id=doc_id,
        reason=reason,
        workflow_mode=workflow_mode,
        user=user,
        get_state=get_global_platform_state,
        persist_emit=_persist_and_emit,
        create_change_request=_create_change_request,
        can_publish=_can_publish_changes,
        now_iso=_now_iso,
    )


