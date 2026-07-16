from __future__ import annotations

import uuid
from typing import Any, Dict


def apply_change_to_state(
    state: Dict[str, Any],
    entity_type: str,
    operation: str,
    payload: Dict[str, Any],
    *,
    sanitize_features,
    sanitize_plans,
    sanitize_faq,
    now_iso,
):
    entity_type = (entity_type or "").lower()
    operation = (operation or "").lower()

    if entity_type in {"global_state", "state"} and operation in {"partial_update", "replace"}:
        update_payload = payload.get("update") if isinstance(payload.get("update"), dict) else payload
        if update_payload.get("features") is not None:
            state["features"] = sanitize_features(update_payload.get("features") or [])
        if update_payload.get("plans") is not None:
            state["plans"] = sanitize_plans(update_payload.get("plans") or [])
        if update_payload.get("faq") is not None:
            state["faq"] = sanitize_faq(update_payload.get("faq") or [])
        if update_payload.get("assistant_knowledge") is not None:
            docs = update_payload.get("assistant_knowledge", {}).get("documents") if isinstance(update_payload.get("assistant_knowledge"), dict) else []
            state["assistant_knowledge"] = {"documents": docs if isinstance(docs, list) else [], "last_refreshed_at": now_iso()}
        if update_payload.get("ui_labels") is not None:
            state["ui_labels"] = {str(k): str(v) for k, v in (update_payload.get("ui_labels") or {}).items()}
        if update_payload.get("messaging") is not None:
            state["messaging"] = update_payload.get("messaging") or {}
        if update_payload.get("state") is not None and operation == "replace":
            next_state = update_payload.get("state") or {}
            state.clear()
            state.update(next_state)
        return "ContentUpdated", "GlobalPlatformState partial update applied"

    if entity_type == "rollback" and operation == "rollback_to_version":
        target_state = payload.get("state") or {}
        if not isinstance(target_state, dict) or not target_state:
            raise ValueError("Rollback payload missing target state")
        state.clear()
        state.update(target_state)
        return "ContentUpdated", f"Rollback to version {payload.get('target_version') or payload.get('version_id')} applied"

    if operation == "bulk_import":
        section = str(payload.get("section") or entity_type or "").lower()
        parsed = payload.get("parsed")
        if section == "features":
            state["features"] = sanitize_features(parsed if isinstance(parsed, list) else [])
            return "ContentUpdated", "Bulk import applied for features"
        if section == "plans":
            state["plans"] = sanitize_plans(parsed if isinstance(parsed, list) else [])
            return "ContentUpdated", "Bulk import applied for plans"
        if section == "faq":
            state["faq"] = sanitize_faq(parsed if isinstance(parsed, list) else [])
            return "ContentUpdated", "Bulk import applied for faq"
        if section == "labels":
            if isinstance(parsed, dict):
                state["ui_labels"] = {str(k): str(v) for k, v in parsed.items()}
            elif isinstance(parsed, list):
                state["ui_labels"] = {str(item.get("key")): str(item.get("value", "")) for item in parsed if item.get("key")}
            return "ContentUpdated", "Bulk import applied for labels"
        if section == "knowledge":
            state["assistant_knowledge"] = {"documents": parsed if isinstance(parsed, list) else [], "last_refreshed_at": now_iso()}
            return "ContentUpdated", "Bulk import applied for knowledge"
        raise ValueError(f"Unsupported bulk import section: {section}")

    if entity_type == "feature":
        if operation == "upsert":
            normalized = sanitize_features([payload])
            item = normalized[0] if normalized else None
            if not item:
                raise ValueError("Invalid feature payload")
            features = state.get("features") or []
            idx = next((i for i, f in enumerate(features) if f.get("feature_id") == item.get("feature_id")), -1)
            if idx < 0:
                features.append(item)
                evt = "FeatureAdded"
            else:
                features[idx] = {**features[idx], **item, "updated_at": now_iso()}
                evt = "FeatureUpdated"
            state["features"] = sanitize_features(features)
            return evt, f"Feature `{item.get('feature_id')}` upserted"
        if operation == "delete":
            fid = payload.get("feature_id")
            state["features"] = [f for f in (state.get("features") or []) if f.get("feature_id") != fid]
            return "FeatureRemoved", f"Feature `{fid}` deleted"

    if entity_type == "plan":
        if operation == "upsert":
            normalized = sanitize_plans([payload])
            item = normalized[0] if normalized else None
            if not item:
                raise ValueError("Invalid plan payload")
            plans = state.get("plans") or []
            idx = next((i for i, p in enumerate(plans) if p.get("plan_id") == item.get("plan_id")), -1)
            if idx < 0:
                plans.append(item)
            else:
                plans[idx] = {**plans[idx], **item, "updated_at": now_iso()}
            state["plans"] = sanitize_plans(plans)
            return "PlanChanged", f"Plan `{item.get('plan_id')}` upserted"
        if operation == "delete":
            pid = payload.get("plan_id")
            state["plans"] = [p for p in (state.get("plans") or []) if p.get("plan_id") != pid]
            return "PlanChanged", f"Plan `{pid}` deleted"

    if entity_type == "faq":
        if operation == "upsert":
            normalized = sanitize_faq([payload])
            item = normalized[0] if normalized else None
            if not item:
                raise ValueError("Invalid FAQ payload")
            faq_items = state.get("faq") or []
            idx = next((i for i, f in enumerate(faq_items) if f.get("faq_id") == item.get("faq_id")), -1)
            if idx < 0:
                faq_items.append(item)
            else:
                faq_items[idx] = {**faq_items[idx], **item, "updated_at": now_iso()}
            state["faq"] = sanitize_faq(faq_items)
            return "ContentUpdated", f"FAQ `{item.get('faq_id')}` upserted"
        if operation == "delete":
            fid = payload.get("faq_id")
            state["faq"] = [f for f in (state.get("faq") or []) if f.get("faq_id") != fid]
            return "ContentUpdated", f"FAQ `{fid}` deleted"

    if entity_type == "ui_label":
        labels = state.get("ui_labels") or {}
        if operation == "upsert":
            labels[str(payload.get("key"))] = str(payload.get("value") or "")
            state["ui_labels"] = labels
            return "ContentUpdated", f"UI label `{payload.get('key')}` upserted"
        if operation == "delete":
            labels.pop(str(payload.get("key")), None)
            state["ui_labels"] = labels
            return "ContentUpdated", f"UI label `{payload.get('key')}` deleted"

    if entity_type == "knowledge":
        knowledge = (state.get("assistant_knowledge") or {}).get("documents") or []
        if operation == "upsert":
            item = dict(payload or {})
            doc_id = str(item.get("doc_id") or item.get("id") or f"doc_{uuid.uuid4().hex[:8]}")
            item["doc_id"] = doc_id
            item["updated_at"] = now_iso()
            idx = next((i for i, d in enumerate(knowledge) if str(d.get("doc_id") or d.get("id")) == doc_id), -1)
            if idx < 0:
                knowledge.append(item)
            else:
                knowledge[idx] = {**knowledge[idx], **item}
            state["assistant_knowledge"] = {"documents": knowledge, "last_refreshed_at": now_iso()}
            return "ContentUpdated", f"Knowledge `{doc_id}` upserted"
        if operation == "delete":
            doc_id = str(payload.get("doc_id") or "")
            state["assistant_knowledge"] = {
                "documents": [d for d in knowledge if str(d.get("doc_id") or d.get("id")) != doc_id],
                "last_refreshed_at": now_iso(),
            }
            return "ContentUpdated", f"Knowledge `{doc_id}` deleted"

    raise ValueError(f"Unsupported entity/operation: {entity_type}/{operation}")