"""GPS runtime/public/admin-sync routes extracted from global_platform_state."""

from __future__ import annotations

import asyncio
import json
import logging
import copy
from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from routes.admin_push_notifications import emit_realtime_alert
from routes.db import db, get_current_user, require_admin
from routes.global_platform_state import (
    GPS_STATE_ID,
    ConsistencyCheckPayload,
    GpsEventPayload,
    GpsUpdatePayload,
    _build_meta,
    _build_payment_plan_drift_report,
    _create_change_request,
    _now_iso,
    _run_stale_count_scan,
    get_global_platform_state,
    publish_gps_event,
    sync_global_faq,
    sync_global_features,
    sync_global_plans,
)
from services.gps_consistency import check_and_optionally_repair_consistency
from services.gps_catalog_guard import (
    assess_gps_catalog_completeness,
    ensure_gps_catalog_integrity,
    generate_platform_integrity_artifact,
)
from services.gps_governance import is_high_impact_change
from services.gls_config import GLS_DEFAULTS, normalize_gls_config
from utils.email_service import is_email_configured, send_catalog_template


router = APIRouter(prefix="/gps", tags=["Global Platform State"])

logger = logging.getLogger(__name__)

GPS_RUNTIME_TIMEOUT_SECONDS = 6.0
GPS_SELF_HEAL_COOLDOWN_SECONDS = 90
GPS_FALLBACK_MAX_AGE_SECONDS = 15 * 60
GPS_CONTRACT_REPAIR_COOLDOWN_SECONDS = 120
GPS_RUNTIME_CACHE: Dict[str, Any] = {
    "state": None,
    "last_success_at": None,
    "last_error_at": None,
    "last_error": None,
    "failing_component": None,
    "lifecycle_stage": None,
    "source": "none",
    "last_incident_alert_at": None,
}

GPS_SELF_HEAL_STATE: Dict[str, Any] = {
    "in_progress": False,
    "last_attempt_at": None,
}

GPS_CONTRACT_REPAIR_STATE: Dict[str, Any] = {
    "in_progress": False,
    "last_attempt_at": None,
}

GPS_FAQ_VIEW_EVENTS_COL = "gps_faq_view_events"


class FaqViewTelemetryPayload(BaseModel):
    question: str = Field(min_length=6, max_length=260)
    faq_id: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    segment: str | None = Field(default=None, max_length=80)
    plan: str | None = Field(default=None, max_length=60)
    context: str | None = Field(default="welcome_faq", max_length=80)
    session_id: str | None = Field(default=None, max_length=120)

RUNTIME_CACHE_PATH = Path("/app/backend/.runtime")
RUNTIME_CACHE_PATH.mkdir(parents=True, exist_ok=True)
GPS_LKG_FILE = RUNTIME_CACHE_PATH / "gps_last_known_good.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _snapshot_age_seconds(state: Dict[str, Any]) -> Optional[int]:
    runtime = state.get("_gps_runtime") or {}
    ts = runtime.get("last_success_at") or state.get("updated_at") or state.get("created_at")
    parsed = _parse_iso(ts)
    if not parsed:
        return None
    return int((datetime.now(timezone.utc) - parsed).total_seconds())


def _normalize_lang_code(raw_lang: Optional[str]) -> str:
    code = str(raw_lang or "en").strip().lower().replace("_", "-")
    if not code:
        return "en"
    return code.split("-")[0]


async def _translate_state_payload(state: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
    lang = _normalize_lang_code(target_lang)
    if lang == "en":
        return state

    translated_state = copy.deepcopy(state)
    replacement_targets: list[tuple[dict, str, str]] = []
    list_targets: list[tuple[list, int, str]] = []

    def _queue_dict_text(obj: dict, key: str):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            replacement_targets.append((obj, key, value))

    # Features/plans
    for feature in (translated_state.get("features") or [])[:300]:
        if isinstance(feature, dict):
            for field in ("title", "description", "category", "status", "availability"):
                _queue_dict_text(feature, field)

    for plan in (translated_state.get("plans") or [])[:120]:
        if isinstance(plan, dict):
            for field in ("name", "description"):
                _queue_dict_text(plan, field)
            for list_field in ("features", "limitations"):
                vals = plan.get(list_field)
                if isinstance(vals, list):
                    for idx, item in enumerate(vals[:80]):
                        if isinstance(item, str) and item.strip():
                            list_targets.append((vals, idx, item))

    # FAQ
    for faq in (translated_state.get("faq") or [])[:300]:
        if isinstance(faq, dict):
            for field in ("question", "answer", "category"):
                _queue_dict_text(faq, field)

    # Messaging
    messaging = translated_state.get("messaging") or {}
    if isinstance(messaging, dict):
        quick_questions = messaging.get("quick_questions")
        if isinstance(quick_questions, list):
            for idx, item in enumerate(quick_questions[:80]):
                if isinstance(item, str) and item.strip():
                    list_targets.append((quick_questions, idx, item))

        announcements = messaging.get("announcements")
        if isinstance(announcements, list):
            for ann in announcements[:150]:
                if isinstance(ann, dict):
                    for field in ("title", "message", "content", "summary", "cta_label"):
                        _queue_dict_text(ann, field)

    texts = [original for (_, _, original) in replacement_targets] + [original for (_, _, original) in list_targets]
    if not texts:
        return translated_state

    unique_texts = []
    seen = set()
    for text in texts:
        if text not in seen:
            unique_texts.append(text)
            seen.add(text)
        if len(unique_texts) >= 900:
            break

    try:
        from services.auto_translate import translate_batch

        translated_map = await translate_batch(unique_texts, lang)
    except Exception:
        translated_map = {}

    for obj, key, original in replacement_targets:
        candidate = translated_map.get(original)
        if isinstance(candidate, str) and candidate.strip():
            obj[key] = candidate

    for arr, idx, original in list_targets:
        candidate = translated_map.get(original)
        if isinstance(candidate, str) and candidate.strip() and idx < len(arr):
            arr[idx] = candidate

    translated_state.setdefault("_gps_runtime", {})
    translated_state["_gps_runtime"]["translation"] = {
        "lang": lang,
        "translated_terms": len(translated_map),
    }
    return translated_state


def _degraded_bootstrap(reason: str, error_message: str = "") -> Dict[str, Any]:
    now = _iso_now()
    return {
        "state_id": GPS_STATE_ID,
        "version": 1,
        "features": [],
        "plans": [],
        "faq": [],
        "assistant_knowledge": {"documents": [], "last_refreshed_at": now},
        "ui_labels": {},
        "messaging": {"announcements": [], "quick_questions": []},
        "layout_config": dict(GLS_DEFAULTS),
        "meta": {
            "counts": {"features": 0, "plans": 0, "faq": 0, "assistant_knowledge_docs": 0},
            "categories": [],
        },
        "updated_at": now,
        "_gps_runtime": {
            "mode": "degraded",
            "reason": reason,
            "error": error_message,
            "last_success_at": GPS_RUNTIME_CACHE.get("last_success_at"),
            "source": "bootstrap",
        },
    }


def _save_lkg_to_disk(state: Dict[str, Any]) -> None:
    try:
        GPS_LKG_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("gps: failed writing disk snapshot: %s", exc)


def _load_lkg_from_disk() -> Optional[Dict[str, Any]]:
    if not GPS_LKG_FILE.exists():
        return None
    try:
        payload = json.loads(GPS_LKG_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("state_id"):
            return payload
    except Exception as exc:
        logger.warning("gps: failed reading disk snapshot: %s", exc)
    return None


async def _save_lkg_to_db(state: Dict[str, Any], source: str) -> None:
    try:
        await db.gps_runtime_snapshots.insert_one(
            {
                "snapshot_id": f"gps_rt_{uuid.uuid4().hex[:12]}",
                "source": source,
                "state": state,
                "created_at": _iso_now(),
            }
        )
    except Exception as exc:
        logger.warning("gps: failed writing db snapshot: %s", exc)


async def _load_lkg_from_db() -> Optional[Dict[str, Any]]:
    try:
        doc = await db.global_platform_state.find_one({"state_id": GPS_STATE_ID}, {"_id": 0})
        if doc and isinstance(doc, dict):
            return doc
    except Exception:
        pass

    try:
        snap = await db.gps_runtime_snapshots.find_one({}, {"_id": 0, "state": 1}, sort=[("created_at", -1)])
        if snap and isinstance(snap.get("state"), dict):
            return snap.get("state")
    except Exception:
        pass
    return None


async def _emit_incident_alerts(component: str, lifecycle_stage: str, error_message: str) -> None:
    now = datetime.now(timezone.utc)
    last_alert_iso = GPS_RUNTIME_CACHE.get("last_incident_alert_at")
    if last_alert_iso:
        try:
            last_alert = datetime.fromisoformat(str(last_alert_iso))
            if (now - last_alert).total_seconds() < 300:
                return
        except Exception:
            pass

    GPS_RUNTIME_CACHE["last_incident_alert_at"] = now.isoformat()

    try:
        emit_realtime_alert(
            alert_type="gps_runtime_failure",
            severity="critical",
            title="GPS runtime degraded",
            message=f"GPS failure at {lifecycle_stage} ({component}): {error_message[:220]}",
        )
    except Exception as exc:
        logger.warning("gps: admin realtime alert emit failed: %s", exc)

    try:
        recipients_raw = (
            (str(__import__("os").environ.get("GPS_INCIDENT_ALERT_EMAILS") or "")).strip()
            or (str(__import__("os").environ.get("ADMIN_EMAIL") or "")).strip()
        )
        recipients = [x.strip() for x in recipients_raw.split(",") if x.strip()]
        if recipients and is_email_configured():
            for recipient in recipients:
                await send_catalog_template(
                    recipient_email=recipient,
                    template_key="gps_runtime_incident",
                    component=component,
                    lifecycle_stage=lifecycle_stage,
                    error_message=error_message,
                    timestamp=_iso_now(),
                )
    except Exception as exc:
        logger.warning("gps: incident email dispatch failed: %s", exc)


async def _record_incident(component: str, lifecycle_stage: str, error_message: str) -> None:
    incident = {
        "incident_id": f"gps_inc_{uuid.uuid4().hex[:12]}",
        "component": component,
        "lifecycle_stage": lifecycle_stage,
        "error": error_message,
        "created_at": _iso_now(),
    }
    try:
        await db.gps_runtime_incidents.insert_one(incident)
    except Exception as exc:
        logger.warning("gps: incident write failed: %s", exc)
    await _emit_incident_alerts(component, lifecycle_stage, error_message)


async def _dependency_health() -> Dict[str, Any]:
    checks: Dict[str, Any] = {}

    try:
        await db.command("ping")
        checks["database"] = {"status": "healthy"}
    except Exception as exc:
        checks["database"] = {"status": "unhealthy", "error": str(exc)}

    try:
        await db.feature_registry.estimated_document_count()
        checks["feature_registry"] = {"status": "healthy"}
    except Exception as exc:
        checks["feature_registry"] = {"status": "unhealthy", "error": str(exc)}

    try:
        await db.platform_runtime_config.find_one({}, {"_id": 0, "updated_at": 1})
        checks["config_service"] = {"status": "healthy"}
    except Exception as exc:
        checks["config_service"] = {"status": "unhealthy", "error": str(exc)}

    try:
        await db.global_platform_state.find_one({"state_id": GPS_STATE_ID}, {"_id": 0, "updated_at": 1})
        checks["gps_state_store"] = {"status": "healthy"}
    except Exception as exc:
        checks["gps_state_store"] = {"status": "unhealthy", "error": str(exc)}

    return checks


async def _resolve_gps_state(force_mode: Optional[str] = None) -> Dict[str, Any]:
    try:
        async def _live_fetch() -> Dict[str, Any]:
            if force_mode == "timeout_test":
                await asyncio.sleep(GPS_RUNTIME_TIMEOUT_SECONDS + 0.25)
            if force_mode == "degraded_test":
                raise RuntimeError("forced_gps_degraded_mode_test")
            return await get_global_platform_state()

        state = await asyncio.wait_for(_live_fetch(), timeout=GPS_RUNTIME_TIMEOUT_SECONDS)
        now_iso = _iso_now()
        GPS_RUNTIME_CACHE["state"] = state
        GPS_RUNTIME_CACHE["last_success_at"] = now_iso
        GPS_RUNTIME_CACHE["last_error_at"] = None
        GPS_RUNTIME_CACHE["last_error"] = None
        GPS_RUNTIME_CACHE["failing_component"] = None
        GPS_RUNTIME_CACHE["lifecycle_stage"] = None
        GPS_RUNTIME_CACHE["source"] = "live"

        state_with_meta = {
            **state,
            "_gps_runtime": {
                "mode": "live",
                "source": "live",
                "last_success_at": now_iso,
            },
        }

        completeness = await assess_gps_catalog_completeness(db)
        if not bool(completeness.get("is_complete")):
            repair_now = datetime.now(timezone.utc)
            can_repair = True
            if isinstance(GPS_CONTRACT_REPAIR_STATE.get("last_attempt_at"), str):
                try:
                    elapsed = (repair_now - datetime.fromisoformat(str(GPS_CONTRACT_REPAIR_STATE["last_attempt_at"]))).total_seconds()
                    if elapsed < GPS_CONTRACT_REPAIR_COOLDOWN_SECONDS:
                        can_repair = False
                except Exception:
                    can_repair = True

            if can_repair and not GPS_CONTRACT_REPAIR_STATE.get("in_progress"):
                GPS_CONTRACT_REPAIR_STATE["in_progress"] = True
                GPS_CONTRACT_REPAIR_STATE["last_attempt_at"] = repair_now.isoformat()
                try:
                    await ensure_gps_catalog_integrity(db, actor_user_id="gps_contract_guard")
                    repaired_state = await get_global_platform_state()
                    state_with_meta = {
                        **repaired_state,
                        "_gps_runtime": {
                            "mode": "live",
                            "source": "live_repaired",
                            "last_success_at": now_iso,
                            "repair_trigger": "completeness_contract",
                            "failed_checks": completeness.get("failed_checks") or [],
                        },
                    }
                except Exception as repair_exc:  # noqa: BLE001
                    logger.warning("gps contract repair failed: %s", repair_exc)
                finally:
                    GPS_CONTRACT_REPAIR_STATE["in_progress"] = False

        _save_lkg_to_disk(state_with_meta)
        await _save_lkg_to_db(state_with_meta, source="live")
        return state_with_meta
    except asyncio.TimeoutError:
        component = "gps_service"
        lifecycle_stage = "state_resolution_timeout"
        error_message = f"gps state fetch exceeded {GPS_RUNTIME_TIMEOUT_SECONDS}s timeout"
    except Exception as exc:  # noqa: BLE001
        component = "gps_service"
        lifecycle_stage = "state_resolution_exception"
        error_message = str(exc)

    GPS_RUNTIME_CACHE["last_error_at"] = _iso_now()
    GPS_RUNTIME_CACHE["last_error"] = error_message
    GPS_RUNTIME_CACHE["failing_component"] = component
    GPS_RUNTIME_CACHE["lifecycle_stage"] = lifecycle_stage

    await _record_incident(component, lifecycle_stage, error_message)

    now = datetime.now(timezone.utc)
    last_attempt_raw = GPS_SELF_HEAL_STATE.get("last_attempt_at")
    can_self_heal = True
    if isinstance(last_attempt_raw, str):
        try:
            if (now - datetime.fromisoformat(last_attempt_raw)).total_seconds() < GPS_SELF_HEAL_COOLDOWN_SECONDS:
                can_self_heal = False
        except Exception:
            can_self_heal = True

    if can_self_heal and not GPS_SELF_HEAL_STATE.get("in_progress"):
        GPS_SELF_HEAL_STATE["in_progress"] = True
        GPS_SELF_HEAL_STATE["last_attempt_at"] = now.isoformat()

        async def _self_heal_task():
            try:
                await sync_global_features(reason="GPS self-heal feature sync", actor_user_id="gps_self_heal", event_type="GpsSelfHeal")
                await sync_global_plans(reason="GPS self-heal plan sync", actor_user_id="gps_self_heal")
                await sync_global_faq(reason="GPS self-heal faq sync", actor_user_id="gps_self_heal")
                await ensure_gps_catalog_integrity(db, actor_user_id="gps_self_heal")
                await get_global_platform_state()
            except Exception as heal_exc:
                logger.warning("gps: self-heal attempt failed: %s", heal_exc)
            finally:
                GPS_SELF_HEAL_STATE["in_progress"] = False

        asyncio.create_task(_self_heal_task())

    fallback_state: Optional[Dict[str, Any]] = None
    fallback_source = "none"
    stale_sources: list[str] = []

    if isinstance(GPS_RUNTIME_CACHE.get("state"), dict):
        candidate = dict(GPS_RUNTIME_CACHE.get("state") or {})
        age_seconds = _snapshot_age_seconds(candidate)
        if age_seconds is not None and age_seconds <= GPS_FALLBACK_MAX_AGE_SECONDS:
            fallback_state = candidate
            fallback_source = "memory_snapshot"
        else:
            stale_sources.append("memory_snapshot")

    if fallback_state is None:
        candidate = await _load_lkg_from_db()
        if candidate:
            age_seconds = _snapshot_age_seconds(candidate)
            if age_seconds is not None and age_seconds <= GPS_FALLBACK_MAX_AGE_SECONDS:
                fallback_state = candidate
                fallback_source = "db_snapshot"
            else:
                stale_sources.append("db_snapshot")

    if fallback_state is None:
        candidate = _load_lkg_from_disk()
        if candidate:
            age_seconds = _snapshot_age_seconds(candidate)
            if age_seconds is not None and age_seconds <= GPS_FALLBACK_MAX_AGE_SECONDS:
                fallback_state = candidate
                fallback_source = "disk_snapshot"
            else:
                stale_sources.append("disk_snapshot")

    if fallback_state is None:
        fallback_state = _degraded_bootstrap("bootstrap_fallback_stale_protection", error_message)
        fallback_source = "bootstrap"

    state_payload = {
        **fallback_state,
        "_gps_runtime": {
            "mode": "degraded",
            "source": fallback_source,
            "reason": lifecycle_stage,
            "error": error_message,
            "last_success_at": GPS_RUNTIME_CACHE.get("last_success_at"),
            "failing_component": component,
            "stale_sources": stale_sources,
            "fallback_max_age_seconds": GPS_FALLBACK_MAX_AGE_SECONDS,
        },
    }
    return state_payload


@router.get("/state")
async def get_state(mode: Optional[str] = None, lang: Optional[str] = None):
    safe_mode = mode if mode in {"timeout_test", "degraded_test"} else None
    state = await _resolve_gps_state(force_mode=safe_mode)
    normalized_lang = _normalize_lang_code(lang)
    if normalized_lang != "en":
        return await _translate_state_payload(state, normalized_lang)
    return state


@router.get("/health")
async def gps_health():
    deps = await _dependency_health()
    unhealthy = [name for name, info in deps.items() if info.get("status") != "healthy"]
    state = await _resolve_gps_state(force_mode=None)
    runtime_last_success_at = (state.get("_gps_runtime") or {}).get("last_success_at") or GPS_RUNTIME_CACHE.get("last_success_at")
    completeness = await assess_gps_catalog_completeness(db, freshness_reference_iso=runtime_last_success_at)
    completeness_ready = bool(completeness.get("is_complete"))
    mode = "live" if not unhealthy and not GPS_RUNTIME_CACHE.get("last_error") and completeness_ready else "degraded"
    return {
        "ready": mode == "live",
        "mode": mode,
        "last_success_at": GPS_RUNTIME_CACHE.get("last_success_at"),
        "last_error_at": GPS_RUNTIME_CACHE.get("last_error_at"),
        "last_error": GPS_RUNTIME_CACHE.get("last_error"),
        "failing_component": GPS_RUNTIME_CACHE.get("failing_component") or (unhealthy[0] if unhealthy else None),
        "request_lifecycle_stage": GPS_RUNTIME_CACHE.get("lifecycle_stage"),
        "dependencies": deps,
        "completeness": completeness,
        "timeout_seconds": GPS_RUNTIME_TIMEOUT_SECONDS,
        "source": GPS_RUNTIME_CACHE.get("source"),
        "state_runtime": state.get("_gps_runtime") or {},
        "self_heal": {
            "in_progress": GPS_SELF_HEAL_STATE.get("in_progress"),
            "last_attempt_at": GPS_SELF_HEAL_STATE.get("last_attempt_at"),
            "cooldown_seconds": GPS_SELF_HEAL_COOLDOWN_SECONDS,
        },
    }


@router.get("/admin/catalog-integrity/status")
async def gps_admin_catalog_integrity_status(request: Request):
    await require_admin(request)
    catalog = await assess_gps_catalog_completeness(db)
    return {
        "status": "ok",
        "catalog": catalog,
    }


@router.post("/admin/catalog-integrity/repair")
async def gps_admin_catalog_integrity_repair(request: Request):
    user = await require_admin(request)
    result = await ensure_gps_catalog_integrity(db, actor_user_id=str(user.user_id))
    return {
        "status": "ok",
        "result": result,
    }


@router.post("/admin/integrity-artifacts/run")
async def gps_admin_integrity_artifact_run(request: Request):
    user = await require_admin(request)
    artifact = await generate_platform_integrity_artifact(db, source=f"admin:{user.user_id}")
    return {
        "status": "ok",
        "artifact": artifact,
    }


@router.get("/admin/integrity-artifacts/latest")
async def gps_admin_integrity_artifact_latest(request: Request):
    await require_admin(request)
    latest = await db.platform_integrity_artifacts.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    return {
        "status": "ok",
        "artifact": latest or {},
    }


@router.get("/admin/incidents")
async def gps_runtime_incidents(request: Request, limit: int = 20):
    await require_admin(request)
    safe_limit = max(1, min(limit, 100))
    rows = await db.gps_runtime_incidents.find({}, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    return {
        "items": rows,
        "count": len(rows),
    }


@router.get("/summary")
async def get_state_summary():
    state = await _resolve_gps_state()
    latest_event = await db.global_platform_events.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return {
        "state_id": state.get("state_id"),
        "version": state.get("version"),
        "meta": state.get("meta", {}),
        "latest_event": latest_event,
        "updated_at": state.get("updated_at"),
        "runtime": state.get("_gps_runtime", {}),
    }


@router.post("/faq/telemetry/view")
async def gps_record_faq_view(payload: FaqViewTelemetryPayload, request: Request):
    now = datetime.now(timezone.utc)
    question = str(payload.question or "").strip()
    if not question:
        return {"success": False, "reason": "invalid_question"}

    faq_id = str(payload.faq_id or "").strip().lower()
    faq_key = faq_id or question.lower().strip()
    if not faq_key:
        return {"success": False, "reason": "invalid_key"}

    context = str(payload.context or "welcome_faq").strip() or "welcome_faq"
    source_ip = str(request.client.host if request.client else "")
    user_agent = str(request.headers.get("user-agent") or "")
    raw_session = str(payload.session_id or "").strip()
    session_key = raw_session
    if not session_key:
        session_seed = f"{source_ip}|{user_agent[:120]}"
        session_key = hashlib.sha256(session_seed.encode("utf-8")).hexdigest()[:24]

    dedupe_since_iso = (now - timedelta(minutes=5)).isoformat()
    duplicate = await db[GPS_FAQ_VIEW_EVENTS_COL].find_one(
        {
            "faq_key": faq_key,
            "context": context,
            "session_key": session_key,
            "created_at": {"$gte": dedupe_since_iso},
        },
        {"_id": 0, "event_id": 1, "created_at": 1},
    )
    if duplicate:
        return {
            "success": True,
            "deduped": True,
            "faq_key": faq_key,
            "recorded_at": str(duplicate.get("created_at") or now.isoformat()),
            "window_minutes": 5,
        }

    await db[GPS_FAQ_VIEW_EVENTS_COL].insert_one(
        {
            "event_id": f"gps_faq_view_{uuid.uuid4().hex[:12]}",
            "faq_key": faq_key,
            "faq_id": faq_id,
            "question": question,
            "category": str(payload.category or "General").strip() or "General",
            "segment": str(payload.segment or "").strip() or "All",
            "plan": str(payload.plan or "").strip() or "Unknown",
            "context": context,
            "source_ip": source_ip,
            "user_agent": user_agent[:220],
            "session_key": session_key,
            "created_at": now.isoformat(),
        }
    )

    return {
        "success": True,
        "deduped": False,
        "faq_key": faq_key,
        "recorded_at": now.isoformat(),
        "window_minutes": 5,
    }


@router.get("/faq/telemetry/top")
async def gps_top_faq_views(window_days: int = 30, limit: int = 10):
    safe_window = max(1, min(int(window_days or 30), 180))
    safe_limit = max(3, min(int(limit or 10), 30))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=safe_window)).isoformat()

    pipeline = [
        {
            "$match": {
                "created_at": {"$gte": since_iso},
                "context": {"$in": ["welcome_faq", "welcome"]},
            }
        },
        {
            "$group": {
                "_id": "$faq_key",
                "faq_id": {"$first": "$faq_id"},
                "question": {"$first": "$question"},
                "category": {"$first": "$category"},
                "views": {"$sum": 1},
                "last_viewed_at": {"$max": "$created_at"},
                "segments": {"$addToSet": "$segment"},
                "plans": {"$addToSet": "$plan"},
            }
        },
        {"$sort": {"views": -1, "last_viewed_at": -1}},
        {"$limit": safe_limit},
    ]

    results = await db[GPS_FAQ_VIEW_EVENTS_COL].aggregate(pipeline).to_list(length=safe_limit)
    ranked: list[dict[str, Any]] = []
    for row in results:
        ranked.append(
            {
                "faq_key": str(row.get("_id") or ""),
                "faq_id": str(row.get("faq_id") or ""),
                "question": str(row.get("question") or ""),
                "category": str(row.get("category") or "General"),
                "views": int(row.get("views") or 0),
                "last_viewed_at": str(row.get("last_viewed_at") or ""),
                "segments": [s for s in row.get("segments") or [] if str(s).strip()],
                "plans": [p for p in row.get("plans") or [] if str(p).strip()],
            }
        )

    return {
        "window_days": safe_window,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_faq": ranked,
    }


@router.put("/state")
async def update_state(payload: GpsUpdatePayload, request: Request):
    user = await require_admin(request)
    dump_payload = getattr(payload, "model_dump", payload.dict)
    update_payload = dump_payload(exclude_none=True)
    update_payload.pop("reason", None)
    workflow_mode = str(update_payload.pop("workflow_mode", payload.workflow_mode) or "publish")
    requires_peer_review = is_high_impact_change("global_state", "partial_update", update_payload)
    change = await _create_change_request(
        user=user,
        entity_type="global_state",
        operation="partial_update",
        payload={"update": update_payload},
        reason=payload.reason or "Full GPS state update requested",
        workflow_mode="review" if workflow_mode == "publish" and requires_peer_review else workflow_mode,
        requires_peer_review=requires_peer_review,
    )
    return {"status": "queued_for_approval", "change_request": change}


@router.get("/admin/audit/self-healing")
async def list_self_healing_audit(request: Request, limit: int = 50):
    await require_admin(request)
    safe_limit = max(1, min(limit, 250))
    rows = await db.gps_self_healing_audit.find({}, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    return {"audits": rows, "total": len(rows)}


@router.get("/admin/compliance/stale-count-scan")
async def run_stale_count_scan(request: Request):
    await require_admin(request)
    result = _run_stale_count_scan()
    await db.gps_compliance_scan_runs.insert_one(
        {
            "scan_id": f"gps_scan_{uuid.uuid4().hex[:12]}",
            "scanner": "gps_stale_count_scanner",
            "result": result,
            "created_at": _now_iso(),
        }
    )
    return result


@router.get("/admin/payment-plan-monitor")
async def payment_plan_monitor(request: Request):
    await require_admin(request)
    return await _build_payment_plan_drift_report()


@router.post("/events")
async def create_gps_event(payload: GpsEventPayload, request: Request):
    user = await require_admin(request)
    event = await publish_gps_event(
        event_type=payload.event_type,
        what_changed=payload.what_changed,
        why_changed=payload.why_changed,
        impact=payload.impact,
        metadata=payload.metadata,
        actor_user_id=user.user_id,
    )
    return {"status": "published", "event": event}


@router.get("/events")
async def list_gps_events(limit: int = 50):
    items = await db.global_platform_events.find({}, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 500)))
    return {"events": items, "total": len(items)}


@router.post("/consistency/check")
async def check_consistency(payload: ConsistencyCheckPayload, request: Request):
    try:
        user = await get_current_user(request)
    except Exception:
        user = None
    state = await get_global_platform_state()
    return await check_and_optionally_repair_consistency(
        db=db,
        gps_state_id=GPS_STATE_ID,
        state=state,
        ui_snapshot=payload.ui_snapshot or {},
        auto_correct=payload.auto_correct,
        user_id=getattr(user, "user_id", "anonymous"),
        build_meta=_build_meta,
        now_iso=_now_iso,
    )


@router.post("/admin/sync")
async def full_sync(request: Request):
    user = await require_admin(request)
    await sync_global_features(reason="Manual full sync", actor_user_id=user.user_id)
    await sync_global_plans(reason="Manual full sync", actor_user_id=user.user_id)
    await sync_global_faq(reason="Manual full sync", actor_user_id=user.user_id)
    guard = await ensure_gps_catalog_integrity(db, actor_user_id=str(user.user_id))
    state = await get_global_platform_state()
    return {"status": "synced", "state": state, "catalog_guard": guard}


# ── Admin Layout & UI Control ──


@router.get("/admin/layout-config")
async def get_layout_config(request: Request):
    await require_admin(request)
    doc = await db.gls_config.find_one({"config_id": "global-layout"}, {"_id": 0})
    normalized = normalize_gls_config(doc)
    return {**normalized, "config_id": "global-layout"}


@router.put("/admin/layout-config")
async def update_layout_config(request: Request):
    user = await require_admin(request)
    body = await request.json()
    allowed_keys = set(GLS_DEFAULTS.keys())
    update = {k: v for k, v in body.items() if k in allowed_keys}
    if not update:
        return {"status": "no_changes"}
    merged = {**GLS_DEFAULTS}
    existing = await db.gls_config.find_one({"config_id": "global-layout"}, {"_id": 0})
    if existing:
        merged.update({k: v for k, v in existing.items() if k in allowed_keys})
    merged.update(update)
    merged = normalize_gls_config(merged)
    merged["config_id"] = "global-layout"
    merged["updated_at"] = _now_iso()
    merged["updated_by"] = user.user_id
    await db.gls_config.replace_one({"config_id": "global-layout"}, merged, upsert=True)
    await publish_gps_event(
        event_type="gls_config_updated",
        what_changed="Global Layout System configuration",
        why_changed=body.get("reason", "Admin updated layout config"),
        impact="low",
        metadata={"changes": update},
        actor_user_id=user.user_id,
    )
    return {"status": "updated", "config": merged}

