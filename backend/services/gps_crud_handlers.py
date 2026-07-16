from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import HTTPException

from services.gps_governance import is_high_impact_change


async def _queue_if_needed(*, user: Any, workflow_mode: str, can_publish, create_change_request, entity_type: str, operation: str, payload: Dict[str, Any], reason: str):
    requires_peer_review = is_high_impact_change(entity_type, operation, payload)
    if workflow_mode == "publish" and can_publish(user) and not requires_peer_review:
        return None
    change = await create_change_request(
        user=user,
        entity_type=entity_type,
        operation=operation,
        payload=payload,
        reason=reason,
        workflow_mode="review" if workflow_mode == "publish" and requires_peer_review else workflow_mode,
        requires_peer_review=requires_peer_review,
    )
    return {"status": "queued_for_approval", "change_request": change}


async def upsert_feature(*, payload: Any, user: Any, get_state, persist_emit, create_change_request, can_publish, sanitize_features, now_iso):
    normalized = sanitize_features([payload.item])
    item = normalized[0] if normalized else None
    if not item:
        raise HTTPException(status_code=400, detail="Invalid feature payload")
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=payload.workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="feature",
        operation="upsert",
        payload=item,
        reason=payload.reason,
    )
    if queued:
        return queued

    state = await get_state()
    features = state.get("features") or []
    idx = next((i for i, f in enumerate(features) if f.get("feature_id") == item.get("feature_id")), -1)
    event_type = "FeatureAdded" if idx < 0 else "FeatureUpdated"
    if idx < 0:
        features.append(item)
    else:
        features[idx] = {**features[idx], **item, "updated_at": now_iso()}
    state["features"] = sanitize_features(features)
    state = await persist_emit(
        state=state,
        event_type=event_type,
        what_changed=f"Feature `{item.get('title')}` {('added' if event_type == 'FeatureAdded' else 'updated')}",
        why_changed=payload.reason or "Admin updated GPS feature catalog",
        impact="Feature Index, Help, and Nova immediately reflect the latest feature definition.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def delete_feature(*, feature_id: str, reason: str, workflow_mode: str, user: Any, get_state, persist_emit, create_change_request, can_publish):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="feature",
        operation="delete",
        payload={"feature_id": feature_id},
        reason=reason,
    )
    if queued:
        return queued
    state = await get_state()
    before = len(state.get("features") or [])
    state["features"] = [f for f in (state.get("features") or []) if f.get("feature_id") != feature_id]
    if before == len(state.get("features") or []):
        raise HTTPException(status_code=404, detail="Feature not found")
    state = await persist_emit(
        state=state,
        event_type="FeatureRemoved",
        what_changed=f"Feature `{feature_id}` removed",
        why_changed=reason or "Admin removed deprecated feature",
        impact="Removed feature no longer appears in GPS-driven pages and Nova responses.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def upsert_plan(*, payload: Any, user: Any, get_state, persist_emit, create_change_request, can_publish, sanitize_plans, now_iso):
    normalized = sanitize_plans([payload.item])
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid plan payload")
    item = normalized[0]
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=payload.workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="plan",
        operation="upsert",
        payload=item,
        reason=payload.reason,
    )
    if queued:
        return queued
    state = await get_state()
    plans = state.get("plans") or []
    idx = next((i for i, p in enumerate(plans) if p.get("plan_id") == item.get("plan_id")), -1)
    if idx < 0:
        plans.append(item)
    else:
        plans[idx] = {**plans[idx], **item, "updated_at": now_iso()}
    state["plans"] = sanitize_plans(plans)
    state = await persist_emit(
        state=state,
        event_type="PlanChanged",
        what_changed=f"Plan `{item.get('name')}` updated",
        why_changed=payload.reason or "Admin updated plan catalog",
        impact="Pricing surfaces and upgrade guidance are now synced platform-wide.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def delete_plan(*, plan_id: str, reason: str, workflow_mode: str, user: Any, get_state, persist_emit, create_change_request, can_publish):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="plan",
        operation="delete",
        payload={"plan_id": plan_id},
        reason=reason,
    )
    if queued:
        return queued
    state = await get_state()
    before = len(state.get("plans") or [])
    state["plans"] = [p for p in (state.get("plans") or []) if p.get("plan_id") != plan_id]
    if before == len(state.get("plans") or []):
        raise HTTPException(status_code=404, detail="Plan not found")
    state = await persist_emit(
        state=state,
        event_type="PlanChanged",
        what_changed=f"Plan `{plan_id}` removed",
        why_changed=reason or "Admin removed plan",
        impact="Plan no longer appears in GPS pricing contexts.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def upsert_faq(*, payload: Any, user: Any, get_state, persist_emit, create_change_request, can_publish, sanitize_faq, now_iso):
    normalized = sanitize_faq([payload.item])
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid FAQ payload")
    item = normalized[0]
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=payload.workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="faq",
        operation="upsert",
        payload=item,
        reason=payload.reason,
    )
    if queued:
        return queued
    state = await get_state()
    faq_items = state.get("faq") or []
    idx = next((i for i, f in enumerate(faq_items) if f.get("faq_id") == item.get("faq_id")), -1)
    if idx < 0:
        faq_items.append(item)
    else:
        faq_items[idx] = {**faq_items[idx], **item, "updated_at": now_iso()}
    state["faq"] = sanitize_faq(faq_items)
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"FAQ `{item.get('faq_id')}` updated",
        why_changed=payload.reason or "Admin updated FAQ knowledge",
        impact="FAQ and Nova support answers are refreshed immediately.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def delete_faq(*, faq_id: str, reason: str, workflow_mode: str, user: Any, get_state, persist_emit, create_change_request, can_publish):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="faq",
        operation="delete",
        payload={"faq_id": faq_id},
        reason=reason,
    )
    if queued:
        return queued
    state = await get_state()
    before = len(state.get("faq") or [])
    state["faq"] = [f for f in (state.get("faq") or []) if f.get("faq_id") != faq_id]
    if before == len(state.get("faq") or []):
        raise HTTPException(status_code=404, detail="FAQ not found")
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"FAQ `{faq_id}` removed",
        why_changed=reason or "Admin removed FAQ",
        impact="FAQ/help results and Nova no longer include removed item.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def upsert_ui_label(*, payload: Any, user: Any, get_state, persist_emit, create_change_request, can_publish):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=payload.workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="ui_label",
        operation="upsert",
        payload={"key": payload.key, "value": payload.value},
        reason=payload.reason,
    )
    if queued:
        return queued
    state = await get_state()
    labels = state.get("ui_labels") or {}
    labels[str(payload.key)] = str(payload.value)
    state["ui_labels"] = labels
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"UI label `{payload.key}` updated",
        why_changed=payload.reason or "Admin updated UI label",
        impact="UI text is synced immediately across GPS-driven pages.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def delete_ui_label(*, key: str, reason: str, workflow_mode: str, user: Any, get_state, persist_emit, create_change_request, can_publish):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="ui_label",
        operation="delete",
        payload={"key": key},
        reason=reason,
    )
    if queued:
        return queued
    state = await get_state()
    labels = state.get("ui_labels") or {}
    if key not in labels:
        raise HTTPException(status_code=404, detail="UI label not found")
    labels.pop(key, None)
    state["ui_labels"] = labels
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"UI label `{key}` removed",
        why_changed=reason or "Admin removed UI label",
        impact="Removed label key falls back to local defaults where applicable.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def upsert_knowledge(*, payload: Any, user: Any, get_state, persist_emit, create_change_request, can_publish, now_iso):
    item = dict(payload.item or {})
    doc_id = str(item.get("doc_id") or item.get("id") or f"doc_{uuid.uuid4().hex[:8]}")
    item["doc_id"] = doc_id
    item["updated_at"] = now_iso()
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=payload.workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="knowledge",
        operation="upsert",
        payload=item,
        reason=payload.reason,
    )
    if queued:
        return queued
    state = await get_state()
    knowledge = (state.get("assistant_knowledge") or {}).get("documents") or []
    idx = next((i for i, d in enumerate(knowledge) if str(d.get("doc_id") or d.get("id")) == doc_id), -1)
    if idx < 0:
        knowledge.append(item)
    else:
        knowledge[idx] = {**knowledge[idx], **item}
    state["assistant_knowledge"] = {"documents": knowledge, "last_refreshed_at": now_iso()}
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"Knowledge document `{doc_id}` updated",
        why_changed=payload.reason or "Admin updated Nova knowledge base",
        impact="Nova answers now use the updated knowledge document immediately.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}


async def delete_knowledge(*, doc_id: str, reason: str, workflow_mode: str, user: Any, get_state, persist_emit, create_change_request, can_publish, now_iso):
    queued = await _queue_if_needed(
        user=user,
        workflow_mode=workflow_mode,
        can_publish=can_publish,
        create_change_request=create_change_request,
        entity_type="knowledge",
        operation="delete",
        payload={"doc_id": doc_id},
        reason=reason,
    )
    if queued:
        return queued
    state = await get_state()
    knowledge = (state.get("assistant_knowledge") or {}).get("documents") or []
    next_docs = [d for d in knowledge if str(d.get("doc_id") or d.get("id")) != doc_id]
    if len(next_docs) == len(knowledge):
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    state["assistant_knowledge"] = {"documents": next_docs, "last_refreshed_at": now_iso()}
    state = await persist_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"Knowledge document `{doc_id}` removed",
        why_changed=reason or "Admin removed knowledge document",
        impact="Nova no longer references the removed knowledge document.",
        actor_user_id=user.user_id,
    )
    return {"status": "ok", "state": state}