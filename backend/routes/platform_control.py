"""Platform Operations Control Center APIs + shared runtime state helpers."""

from __future__ import annotations

import asyncio
import csv
import copy
import json
import uuid
from io import StringIO
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from routes.db import db, get_current_user, require_admin
from routes.notification_engine import emit_notification


router = APIRouter(prefix="/platform-control", tags=["Platform Control Center"])

PLATFORM_CONTROL_DOC_KEY = "global"
CONTROL_CACHE_TTL_SECONDS = 5
SYSTEM_STATUS_VALUES = {"ONLINE", "MAINTENANCE", "DEGRADED", "OUTAGE"}
STAFF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


DEFAULT_PLATFORM_CONTROL: Dict[str, Any] = {
    "system_status": "ONLINE",
    "system_status_reason": "",
    "emergency_shutdown": {
        "enabled": False,
        "reason": "",
        "activated_at": None,
        "deactivated_at": None,
    },
    "maintenance": {
        "enabled": False,
        "title": "Scheduled Platform Maintenance",
        "reason": "",
        "starts_at": None,
        "ends_at": None,
        "allow_staff_read_only": True,
        "window_id": None,
    },
    "feature_toggles": {
        "ai_modules": True,
        "payments": True,
        "tools": True,
        "experimental": True,
    },
    "notification_channels": {
        "in_app": True,
        "email": True,
        "sms": False,
        "push": False,
    },
    "announcement": {
        "title": "",
        "message": "",
        "updated_at": None,
    },
    "updated_at": None,
    "updated_by": None,
    "last_auto_recovery_at": None,
}


LOCK_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/system/health",
    "/api/status/",
    "/api/platform-control/public/",
    "/api/config/global",
    "/api/auth/",
    "/api/webhook/",
    "/api/webhooks/",
    "/api/payments/fedapay/webhook",
    "/api/platform-shell-health/",
    "/api/cron/",
    "/api/vitals/",
)


_CONTROL_CACHE: Dict[str, Any] = {"ts": 0.0, "state": None}


class MaintenanceUpdateRequest(BaseModel):
    enabled: bool
    title: Optional[str] = None
    reason: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    allow_staff_read_only: Optional[bool] = None
    notify_users: bool = True
    force_replace: bool = False


class EmergencyShutdownRequest(BaseModel):
    enabled: bool
    reason: str = "Emergency platform lockdown in progress."
    notify_users: bool = True


class SystemStatusUpdateRequest(BaseModel):
    status: Literal["ONLINE", "MAINTENANCE", "DEGRADED", "OUTAGE"]
    reason: str = ""
    notify_users: bool = True


class FeatureTogglesUpdateRequest(BaseModel):
    feature_toggles: Dict[str, bool] = Field(default_factory=dict)


class NotificationChannelsUpdateRequest(BaseModel):
    in_app: Optional[bool] = None
    email: Optional[bool] = None
    sms: Optional[bool] = None
    push: Optional[bool] = None


class BroadcastMessageRequest(BaseModel):
    title: str
    message: str
    audience: Literal["all_non_admin", "all_users", "staff_only"] = "all_non_admin"


class AnnouncementTemplateCreateRequest(BaseModel):
    name: str
    title: str
    message: str
    audience: Literal["all_non_admin", "all_users", "staff_only"] = "all_non_admin"
    schedule_type: Literal["one_time", "daily", "weekly"] = "one_time"
    scheduled_for: Optional[str] = None
    daily_time_utc: Optional[str] = None  # HH:MM
    weekly_day_utc: Optional[int] = None  # 0=Mon, 6=Sun
    weekly_time_utc: Optional[str] = None  # HH:MM
    channels: Dict[str, bool] = Field(default_factory=lambda: {"in_app": True, "email": True})
    enabled: bool = True


class AnnouncementTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    audience: Optional[Literal["all_non_admin", "all_users", "staff_only"]] = None
    schedule_type: Optional[Literal["one_time", "daily", "weekly"]] = None
    scheduled_for: Optional[str] = None
    daily_time_utc: Optional[str] = None
    weekly_day_utc: Optional[int] = None
    weekly_time_utc: Optional[str] = None
    channels: Optional[Dict[str, bool]] = None
    enabled: Optional[bool] = None


class AnnouncementTemplateDispatchRequest(BaseModel):
    notify_immediately: bool = True


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().isoformat()


def _parse_iso_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime for {field_name}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _parse_hhmm(value: Optional[str], field_name: str) -> Optional[tuple[int, int]]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if ":" not in text:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}; expected HH:MM")
    hh_str, mm_str = text.split(":", 1)
    try:
        hh = int(hh_str)
        mm = int(mm_str)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}; expected HH:MM") from exc
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}; expected HH:MM")
    return hh, mm


def _compute_next_run_at(template: Dict[str, Any], now: Optional[datetime] = None) -> Optional[str]:
    now = now or _now_utc()
    schedule_type = str(template.get("schedule_type") or "one_time").lower()

    if schedule_type == "one_time":
        scheduled_for = _parse_iso_datetime(template.get("scheduled_for"), "scheduled_for")
        if not scheduled_for:
            raise HTTPException(status_code=422, detail="scheduled_for is required for one_time templates")
        if scheduled_for <= now:
            raise HTTPException(status_code=422, detail="scheduled_for must be in the future")
        return _to_iso(scheduled_for)

    if schedule_type == "daily":
        hhmm = _parse_hhmm(template.get("daily_time_utc"), "daily_time_utc")
        if not hhmm:
            raise HTTPException(status_code=422, detail="daily_time_utc is required for daily templates")
        hh, mm = hhmm
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            from datetime import timedelta

            candidate = candidate + timedelta(days=1)
        return _to_iso(candidate)

    if schedule_type == "weekly":
        weekly_day = template.get("weekly_day_utc")
        if weekly_day is None:
            raise HTTPException(status_code=422, detail="weekly_day_utc is required for weekly templates")
        try:
            day_idx = int(weekly_day)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="weekly_day_utc must be an integer between 0 and 6") from exc
        if day_idx < 0 or day_idx > 6:
            raise HTTPException(status_code=422, detail="weekly_day_utc must be an integer between 0 and 6")
        hhmm = _parse_hhmm(template.get("weekly_time_utc"), "weekly_time_utc")
        if not hhmm:
            raise HTTPException(status_code=422, detail="weekly_time_utc is required for weekly templates")
        hh, mm = hhmm

        from datetime import timedelta

        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        day_delta = (day_idx - candidate.weekday()) % 7
        candidate = candidate + timedelta(days=day_delta)
        if candidate <= now:
            candidate = candidate + timedelta(days=7)
        return _to_iso(candidate)

    raise HTTPException(status_code=422, detail="schedule_type must be one_time, daily, or weekly")


def _normalize_template_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    doc = copy.deepcopy(raw or {})
    doc.pop("_id", None)
    doc["template_id"] = str(doc.get("template_id") or f"ann_tpl_{uuid.uuid4().hex[:12]}")
    doc["name"] = str(doc.get("name") or "Announcement Template")[:120]
    doc["title"] = str(doc.get("title") or "Platform update")[:120]
    doc["message"] = str(doc.get("message") or "")[:1800]
    doc["audience"] = str(doc.get("audience") or "all_non_admin")
    doc["schedule_type"] = str(doc.get("schedule_type") or "one_time").lower()
    doc["scheduled_for"] = doc.get("scheduled_for")
    doc["daily_time_utc"] = doc.get("daily_time_utc")
    doc["weekly_day_utc"] = doc.get("weekly_day_utc")
    doc["weekly_time_utc"] = doc.get("weekly_time_utc")
    channels = doc.get("channels") or {}
    doc["channels"] = {
        "in_app": bool(channels.get("in_app", True)),
        "email": bool(channels.get("email", True)),
    }
    doc["enabled"] = bool(doc.get("enabled", True))
    doc["next_run_at"] = doc.get("next_run_at")
    doc["last_run_at"] = doc.get("last_run_at")
    doc["last_dispatch_summary"] = doc.get("last_dispatch_summary") or {}
    doc["run_count"] = int(doc.get("run_count") or 0)
    doc["created_at"] = doc.get("created_at") or _iso_now()
    doc["updated_at"] = doc.get("updated_at") or _iso_now()
    doc["created_by"] = doc.get("created_by")
    doc["updated_by"] = doc.get("updated_by")
    return doc


def _build_audit_log_query(
    action: Optional[str],
    actor: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    search: Optional[str],
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if action:
        query["action"] = str(action).strip()
    if actor:
        query["actor_email"] = {"$regex": str(actor).strip(), "$options": "i"}

    if date_from or date_to:
        date_query: Dict[str, Any] = {}
        if date_from:
            dt = _parse_iso_datetime(date_from, "date_from")
            if dt:
                date_query["$gte"] = _to_iso(dt)
        if date_to:
            dt = _parse_iso_datetime(date_to, "date_to")
            if dt:
                date_query["$lte"] = _to_iso(dt)
        if date_query:
            query["created_at"] = date_query

    if search:
        q = str(search).strip()
        if q:
            query["$or"] = [
                {"action": {"$regex": q, "$options": "i"}},
                {"actor_email": {"$regex": q, "$options": "i"}},
                {"metadata": {"$regex": q, "$options": "i"}},
            ]

    return query


def _audit_status_value(row: Dict[str, Any]) -> str:
    meta = row.get("metadata") or {}
    summary = meta.get("notification_summary") or {}
    if isinstance(summary, dict):
        if summary.get("queued") is True:
            return "queued"
        if summary.get("notified") is not None and summary.get("targeted") is not None:
            return "sent" if int(summary.get("notified") or 0) > 0 else "failed"
    return "n/a"


def _export_audit_logs_csv(rows: list[Dict[str, Any]]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["audit_id", "created_at", "actor_email", "action", "status", "metadata"])
    for row in rows:
        writer.writerow(
            [
                row.get("audit_id"),
                row.get("created_at"),
                row.get("actor_email"),
                row.get("action"),
                _audit_status_value(row),
                json.dumps(row.get("metadata") or {}, ensure_ascii=False),
            ]
        )
    return buffer.getvalue()


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge_dict(base[key], value)
        else:
            base[key] = value
    return base


def _normalize_platform_control(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = copy.deepcopy(DEFAULT_PLATFORM_CONTROL)
    if isinstance(raw, dict):
        clean = copy.deepcopy(raw)
        clean.pop("_id", None)
        clean.pop("key", None)
        _deep_merge_dict(state, clean)

    status = str(state.get("system_status") or "ONLINE").upper()
    state["system_status"] = status if status in SYSTEM_STATUS_VALUES else "ONLINE"
    state["system_status_reason"] = str(state.get("system_status_reason") or "")[:800]

    maint = state.get("maintenance") or {}
    state["maintenance"] = {
        "enabled": bool(maint.get("enabled", False)),
        "title": str(maint.get("title") or "Scheduled Platform Maintenance")[:120],
        "reason": str(maint.get("reason") or "")[:1200],
        "starts_at": maint.get("starts_at"),
        "ends_at": maint.get("ends_at"),
        "allow_staff_read_only": bool(maint.get("allow_staff_read_only", True)),
        "window_id": maint.get("window_id"),
    }

    emergency = state.get("emergency_shutdown") or {}
    state["emergency_shutdown"] = {
        "enabled": bool(emergency.get("enabled", False)),
        "reason": str(emergency.get("reason") or "")[:1200],
        "activated_at": emergency.get("activated_at"),
        "deactivated_at": emergency.get("deactivated_at"),
    }

    toggles = state.get("feature_toggles") or {}
    state["feature_toggles"] = {
        "ai_modules": bool(toggles.get("ai_modules", True)),
        "payments": bool(toggles.get("payments", True)),
        "tools": bool(toggles.get("tools", True)),
        "experimental": bool(toggles.get("experimental", True)),
    }

    channels = state.get("notification_channels") or {}
    state["notification_channels"] = {
        "in_app": bool(channels.get("in_app", True)),
        "email": bool(channels.get("email", True)),
        "sms": bool(channels.get("sms", False)),
        "push": bool(channels.get("push", False)),
    }

    state["updated_at"] = state.get("updated_at")
    state["updated_by"] = state.get("updated_by")
    state["last_auto_recovery_at"] = state.get("last_auto_recovery_at")
    return state


def _is_staff_user(user: Any) -> bool:
    if not user or bool(getattr(user, "is_admin", False)):
        return False
    perms = list(getattr(user, "employee_permissions", []) or [])
    platform_role = str(getattr(user, "platform_role", "") or "").strip().lower()
    return bool(perms) or platform_role in {"staff", "support", "operator", "manager", "analyst"}


def _maintenance_window_active(state: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or _now_utc()
    maint = state.get("maintenance") or {}
    if not bool(maint.get("enabled", False)):
        return False

    starts_at = _parse_iso_datetime(maint.get("starts_at"), "maintenance.starts_at") if maint.get("starts_at") else None
    ends_at = _parse_iso_datetime(maint.get("ends_at"), "maintenance.ends_at") if maint.get("ends_at") else None

    if starts_at and now < starts_at:
        return False
    if ends_at and now > ends_at:
        return False
    return True


def resolve_active_mode(state: Dict[str, Any]) -> str:
    now = _now_utc()
    if bool((state.get("emergency_shutdown") or {}).get("enabled", False)):
        return "EMERGENCY_SHUTDOWN"
    if _maintenance_window_active(state, now):
        return "MAINTENANCE"
    system_status = str(state.get("system_status") or "ONLINE").upper()
    if system_status == "OUTAGE":
        return "OUTAGE"
    if system_status == "DEGRADED":
        return "DEGRADED"
    return "ONLINE"


def is_platform_lock_active(state: Dict[str, Any]) -> bool:
    return resolve_active_mode(state) in {"MAINTENANCE", "EMERGENCY_SHUTDOWN"}


def is_request_exempt_from_platform_lock(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in LOCK_EXEMPT_PREFIXES)


def can_staff_read_only_bypass(user: Any, state: Dict[str, Any], method: str) -> bool:
    if method.upper() not in STAFF_SAFE_METHODS:
        return False
    allow = bool((state.get("maintenance") or {}).get("allow_staff_read_only", True))
    return allow and _is_staff_user(user)


def build_lock_response_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_utc()
    active_mode = resolve_active_mode(state)
    maintenance = state.get("maintenance") or {}
    emergency = state.get("emergency_shutdown") or {}

    starts_at = _parse_iso_datetime(maintenance.get("starts_at"), "maintenance.starts_at") if maintenance.get("starts_at") else None
    ends_at = _parse_iso_datetime(maintenance.get("ends_at"), "maintenance.ends_at") if maintenance.get("ends_at") else None

    countdown_seconds: Optional[int] = None
    if active_mode == "MAINTENANCE" and ends_at:
        countdown_seconds = max(0, int((ends_at - now).total_seconds()))

    reason = (
        str(emergency.get("reason") or "").strip()
        if active_mode == "EMERGENCY_SHUTDOWN"
        else str(maintenance.get("reason") or state.get("system_status_reason") or "").strip()
    )
    title = (
        "Emergency Shutdown"
        if active_mode == "EMERGENCY_SHUTDOWN"
        else str(maintenance.get("title") or "Scheduled Platform Maintenance")
    )

    return {
        "detail": "Platform access is temporarily restricted.",
        "code": "PLATFORM_EMERGENCY_SHUTDOWN" if active_mode == "EMERGENCY_SHUTDOWN" else "PLATFORM_MAINTENANCE_MODE",
        "active_mode": active_mode,
        "system_status": str(state.get("system_status") or "ONLINE").upper(),
        "title": title,
        "reason": reason,
        "starts_at": _to_iso(starts_at),
        "ends_at": _to_iso(ends_at),
        "countdown_seconds": countdown_seconds,
        "allow_staff_read_only": bool(maintenance.get("allow_staff_read_only", True)),
        "updated_at": state.get("updated_at"),
    }


async def _save_platform_control_state(state: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
    normalized = _normalize_platform_control(state)
    normalized["updated_at"] = _iso_now()
    normalized["updated_by"] = str(updated_by or "system")[:180]
    payload = {"key": PLATFORM_CONTROL_DOC_KEY, **normalized}
    await db.platform_control_config.update_one(
        {"key": PLATFORM_CONTROL_DOC_KEY},
        {"$set": payload},
        upsert=True,
    )

    _CONTROL_CACHE["ts"] = 0.0
    _CONTROL_CACHE["state"] = None

    await _sync_legacy_maintenance_mode(bool((normalized.get("maintenance") or {}).get("enabled", False)), normalized["updated_by"])
    return normalized


async def _sync_legacy_maintenance_mode(enabled: bool, updated_by: str) -> None:
    """Keep existing /config/global maintenance_mode in sync for backward compatibility."""
    try:
        await db.platform_runtime_config.update_one(
            {"key": "global"},
            {
                "$set": {
                    "maintenance_mode": bool(enabled),
                    "updated_at": _iso_now(),
                    "updated_by": updated_by,
                }
            },
            upsert=True,
        )
    except Exception:
        # Non-fatal compatibility sync
        pass


async def _write_audit_log(
    actor_user_id: Optional[str],
    actor_email: Optional[str],
    action: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    await db.platform_control_audit_logs.insert_one(
        {
            "audit_id": f"pc_audit_{uuid.uuid4().hex[:12]}",
            "actor_user_id": actor_user_id,
            "actor_email": actor_email,
            "action": action,
            "before": before,
            "after": after,
            "metadata": metadata or {},
            "created_at": _iso_now(),
        }
    )


def _public_state_projection(state: Dict[str, Any]) -> Dict[str, Any]:
    active_mode = resolve_active_mode(state)
    maintenance = state.get("maintenance") or {}
    emergency = state.get("emergency_shutdown") or {}
    payload = {
        "system_status": str(state.get("system_status") or "ONLINE").upper(),
        "active_mode": active_mode,
        "is_blocking": active_mode in {"MAINTENANCE", "EMERGENCY_SHUTDOWN"},
        "maintenance": {
            "enabled": bool(maintenance.get("enabled", False)),
            "title": maintenance.get("title") or "Scheduled Platform Maintenance",
            "reason": maintenance.get("reason") or "",
            "starts_at": maintenance.get("starts_at"),
            "ends_at": maintenance.get("ends_at"),
            "allow_staff_read_only": bool(maintenance.get("allow_staff_read_only", True)),
        },
        "emergency_shutdown": {
            "enabled": bool(emergency.get("enabled", False)),
            "reason": emergency.get("reason") or "",
            "activated_at": emergency.get("activated_at"),
        },
        "feature_toggles": state.get("feature_toggles") or {},
        "updated_at": state.get("updated_at"),
        "server_time": _iso_now(),
    }
    payload["gate_payload"] = build_lock_response_payload(state)
    return payload


async def _update_maintenance_window_registry(state: Dict[str, Any], status: str) -> None:
    maintenance = state.get("maintenance") or {}
    window_id = maintenance.get("window_id")
    if not window_id:
        return
    await db.platform_control_maintenance_windows.update_one(
        {"window_id": window_id},
        {
            "$set": {
                "window_id": window_id,
                "status": status,
                "title": maintenance.get("title"),
                "reason": maintenance.get("reason"),
                "starts_at": maintenance.get("starts_at"),
                "ends_at": maintenance.get("ends_at"),
                "updated_at": _iso_now(),
            },
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )


async def _check_schedule_conflict(starts_at: Optional[str], ends_at: Optional[str], current_window_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not starts_at or not ends_at:
        return None
    overlap_query = {
        "status": {"$in": ["scheduled", "active"]},
        "starts_at": {"$lt": ends_at},
        "ends_at": {"$gt": starts_at},
    }
    if current_window_id:
        overlap_query["window_id"] = {"$ne": current_window_id}
    return await db.platform_control_maintenance_windows.find_one(overlap_query, {"_id": 0})


async def _notify_audience(
    title: str,
    message: str,
    audience: str,
    channels: Dict[str, bool],
    notif_type: str,
    max_recipients: int = 400,
) -> Dict[str, Any]:
    if not bool(channels.get("in_app", True)) and not bool(channels.get("email", True)):
        return {"targeted": 0, "notified": 0, "email_enabled": False}

    query: Dict[str, Any]
    if audience == "all_users":
        query = {}
    elif audience == "staff_only":
        query = {"is_admin": {"$ne": True}, "employee_permissions.0": {"$exists": True}}
    else:
        query = {"is_admin": {"$ne": True}}

    safe_limit = max(1, min(int(max_recipients), 400))
    docs = await db.users.find(query, {"_id": 0, "user_id": 1}).limit(safe_limit).to_list(safe_limit)
    notified = 0
    for row in docs:
        user_id = row.get("user_id")
        if not user_id:
            continue
        try:
            await emit_notification(
                user_id=user_id,
                notif_type=notif_type,
                title=title,
                body=message,
                action_url="/system-status",
                metadata={"source": "platform_control"},
                send_email_notification=bool(channels.get("email", True)),
            )
            notified += 1
        except Exception:
            continue

    return {
        "targeted": len(docs),
        "notified": notified,
        "email_enabled": bool(channels.get("email", True)),
        "in_app_enabled": bool(channels.get("in_app", True)),
        "sms_enabled": bool(channels.get("sms", False)),
        "push_enabled": bool(channels.get("push", False)),
    }


def _audience_query(audience: str) -> Dict[str, Any]:
    if audience == "all_users":
        return {}
    if audience == "staff_only":
        return {"is_admin": {"$ne": True}, "employee_permissions.0": {"$exists": True}}
    return {"is_admin": {"$ne": True}}


async def _estimate_audience_size(audience: str, max_recipients: int = 400) -> int:
    try:
        safe_limit = max(1, min(int(max_recipients), 400))
        return int(await db.users.count_documents(_audience_query(audience), limit=safe_limit))
    except Exception:
        return 0


async def _notify_audience_background(
    title: str,
    message: str,
    audience: str,
    channels: Dict[str, bool],
    notif_type: str,
    max_recipients: int = 400,
) -> None:
    try:
        await _notify_audience(
            title=title,
            message=message,
            audience=audience,
            channels=channels,
            notif_type=notif_type,
            max_recipients=max_recipients,
        )
    except Exception:
        # non-blocking background dispatch
        pass


async def _dispatch_announcement_template(
    template: Dict[str, Any],
    actor_email: str,
    actor_user_id: str,
    trigger: str,
    queue_only: bool = True,
) -> Dict[str, Any]:
    normalized = _normalize_template_doc(template)
    title = str(normalized.get("title") or "Platform update")
    message = str(normalized.get("message") or "")
    audience = str(normalized.get("audience") or "all_non_admin")
    channels = normalized.get("channels") or {"in_app": True, "email": True}

    if queue_only:
        estimated = await _estimate_audience_size(audience, max_recipients=50)
        asyncio.create_task(
            _notify_audience_background(
                title=title,
                message=message,
                audience=audience,
                channels=channels,
                notif_type="platform_scheduled_announcement",
                max_recipients=50,
            )
        )
        summary = {
            "queued": True,
            "estimated_target": estimated,
            "email_enabled": bool(channels.get("email", True)),
            "in_app_enabled": bool(channels.get("in_app", True)),
        }
    else:
        summary = await _notify_audience(
            title=title,
            message=message,
            audience=audience,
            channels=channels,
            notif_type="platform_scheduled_announcement",
            max_recipients=50,
        )

    now_iso = _iso_now()
    next_run = None
    if str(normalized.get("schedule_type") or "one_time") in {"daily", "weekly"} and bool(normalized.get("enabled", True)):
        next_run = _compute_next_run_at(normalized)

    update_doc = {
        "last_run_at": now_iso,
        "last_dispatch_summary": summary,
        "run_count": int(normalized.get("run_count") or 0) + 1,
        "next_run_at": next_run,
        "updated_at": now_iso,
        "updated_by": actor_email,
    }
    if str(normalized.get("schedule_type") or "one_time") == "one_time":
        update_doc["enabled"] = False

    await db.platform_control_announcement_templates.update_one(
        {"template_id": normalized["template_id"]},
        {"$set": update_doc},
    )

    await _write_audit_log(
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action="announcement_template_dispatched",
        before={"template_id": normalized["template_id"], "next_run_at": normalized.get("next_run_at")},
        after={"template_id": normalized["template_id"], **update_doc},
        metadata={"trigger": trigger, "dispatch_summary": summary},
    )

    return summary


async def run_scheduled_platform_announcements(trigger: str = "scheduler") -> Dict[str, Any]:
    now_iso = _iso_now()
    due_templates = await db.platform_control_announcement_templates.find(
        {
            "enabled": True,
            "next_run_at": {"$ne": None, "$lte": now_iso},
        },
        {"_id": 0},
    ).limit(25).to_list(25)

    dispatched = 0
    failed = 0
    for template in due_templates:
        try:
            await _dispatch_announcement_template(
                template=template,
                actor_email="system@platform.local",
                actor_user_id="system",
                trigger=trigger,
                queue_only=True,
            )
            dispatched += 1
        except Exception:
            failed += 1

    return {"evaluated": len(due_templates), "dispatched": dispatched, "failed": failed, "trigger": trigger}


async def _broadcast_platform_state_change() -> None:
    try:
        from utils.ws_manager import broadcast_data_change

        await broadcast_data_change("platform_control", "updated")
    except Exception:
        pass


async def _apply_auto_recovery_if_due(state: Dict[str, Any]) -> Dict[str, Any]:
    maintenance = state.get("maintenance") or {}
    if not bool(maintenance.get("enabled", False)):
        return state

    ends_at_raw = maintenance.get("ends_at")
    if not ends_at_raw:
        return state

    ends_at = _parse_iso_datetime(ends_at_raw, "maintenance.ends_at")
    if not ends_at:
        return state

    if _now_utc() <= ends_at:
        return state

    next_state = copy.deepcopy(state)
    next_state["maintenance"]["enabled"] = False
    if str(next_state.get("system_status") or "ONLINE").upper() == "MAINTENANCE":
        next_state["system_status"] = "ONLINE"
        next_state["system_status_reason"] = ""
    next_state["last_auto_recovery_at"] = _iso_now()

    saved = await _save_platform_control_state(next_state, updated_by="system:auto-recovery")
    await _update_maintenance_window_registry(saved, "completed")
    await _write_audit_log(
        actor_user_id="system",
        actor_email="system@platform.local",
        action="maintenance_auto_recovery",
        before=state,
        after=saved,
        metadata={"reason": "scheduled_end_elapsed"},
    )
    await _broadcast_platform_state_change()
    return saved


async def get_effective_platform_control_state(force_refresh: bool = False) -> Dict[str, Any]:
    now_ts = _now_utc().timestamp()
    if (
        not force_refresh
        and _CONTROL_CACHE.get("state") is not None
        and (now_ts - float(_CONTROL_CACHE.get("ts") or 0.0)) < CONTROL_CACHE_TTL_SECONDS
    ):
        return copy.deepcopy(_CONTROL_CACHE["state"])

    doc = await db.platform_control_config.find_one({"key": PLATFORM_CONTROL_DOC_KEY}, {"_id": 0})
    state = _normalize_platform_control(doc or {})
    state = await _apply_auto_recovery_if_due(state)
    _CONTROL_CACHE["state"] = copy.deepcopy(state)
    _CONTROL_CACHE["ts"] = now_ts
    return state


@router.get("/admin/state")
async def get_admin_platform_control_state(request: Request):
    await require_admin(request)
    state = await get_effective_platform_control_state(force_refresh=True)
    return {
        "state": state,
        "public_state": _public_state_projection(state),
    }


@router.put("/admin/maintenance")
async def update_maintenance_mode(body: MaintenanceUpdateRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    next_state = copy.deepcopy(current)

    starts_at_dt = _parse_iso_datetime(body.starts_at, "starts_at") if body.starts_at else _parse_iso_datetime(next_state["maintenance"].get("starts_at"), "starts_at") if next_state["maintenance"].get("starts_at") else None
    ends_at_dt = _parse_iso_datetime(body.ends_at, "ends_at") if body.ends_at else _parse_iso_datetime(next_state["maintenance"].get("ends_at"), "ends_at") if next_state["maintenance"].get("ends_at") else None

    if body.enabled and starts_at_dt and ends_at_dt and starts_at_dt >= ends_at_dt:
        raise HTTPException(status_code=422, detail="Maintenance ends_at must be after starts_at")

    existing_window_id = next_state["maintenance"].get("window_id")
    starts_at_iso = _to_iso(starts_at_dt)
    ends_at_iso = _to_iso(ends_at_dt)
    conflict = await _check_schedule_conflict(starts_at_iso, ends_at_iso, existing_window_id) if body.enabled else None
    if conflict and not body.force_replace:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Maintenance schedule conflict detected",
                "conflicting_window_id": conflict.get("window_id"),
                "starts_at": conflict.get("starts_at"),
                "ends_at": conflict.get("ends_at"),
            },
        )

    next_state["maintenance"]["enabled"] = bool(body.enabled)
    next_state["maintenance"]["title"] = (body.title or next_state["maintenance"].get("title") or "Scheduled Platform Maintenance")[:120]
    next_state["maintenance"]["reason"] = (body.reason or next_state["maintenance"].get("reason") or "")[:1200]
    next_state["maintenance"]["starts_at"] = starts_at_iso or (_iso_now() if body.enabled else None)
    next_state["maintenance"]["ends_at"] = ends_at_iso
    if body.allow_staff_read_only is not None:
        next_state["maintenance"]["allow_staff_read_only"] = bool(body.allow_staff_read_only)

    if body.enabled and not next_state["maintenance"].get("window_id"):
        next_state["maintenance"]["window_id"] = f"maint_{uuid.uuid4().hex[:10]}"

    if body.enabled:
        if str(next_state.get("system_status") or "ONLINE").upper() == "ONLINE":
            next_state["system_status"] = "MAINTENANCE"
        await _update_maintenance_window_registry(next_state, "scheduled")
    else:
        if str(next_state.get("system_status") or "ONLINE").upper() == "MAINTENANCE" and not bool((next_state.get("emergency_shutdown") or {}).get("enabled", False)):
            next_state["system_status"] = "ONLINE"
            next_state["system_status_reason"] = ""
        await _update_maintenance_window_registry(next_state, "cancelled")

    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="maintenance_mode_updated",
        before=current,
        after=saved,
        metadata={"notify_users": bool(body.notify_users), "force_replace": bool(body.force_replace)},
    )
    await _broadcast_platform_state_change()

    notification_summary = {"queued": False}
    if body.notify_users:
        title = "Scheduled Maintenance Active" if body.enabled else "Maintenance Completed"
        message = (
            saved["maintenance"].get("reason")
            or ("Platform maintenance is now active." if body.enabled else "Platform maintenance has ended. Services are restored.")
        )
        notification_summary = await _notify_audience(
            title=title,
            message=message,
            audience="all_non_admin",
            channels=saved.get("notification_channels") or {},
            notif_type="platform_maintenance",
        )

    return {
        "status": "updated",
        "state": saved,
        "public_state": _public_state_projection(saved),
        "notification_summary": notification_summary,
    }


@router.put("/admin/emergency-shutdown")
async def update_emergency_shutdown(body: EmergencyShutdownRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    next_state = copy.deepcopy(current)

    next_state["emergency_shutdown"]["enabled"] = bool(body.enabled)
    next_state["emergency_shutdown"]["reason"] = str(body.reason or "").strip()[:1200]
    if body.enabled:
        next_state["emergency_shutdown"]["activated_at"] = _iso_now()
        next_state["system_status"] = "OUTAGE"
        next_state["system_status_reason"] = next_state["emergency_shutdown"]["reason"]
    else:
        next_state["emergency_shutdown"]["deactivated_at"] = _iso_now()
        if str(next_state.get("system_status") or "ONLINE").upper() == "OUTAGE":
            next_state["system_status"] = "MAINTENANCE" if bool((next_state.get("maintenance") or {}).get("enabled", False)) else "ONLINE"
            if next_state["system_status"] == "ONLINE":
                next_state["system_status_reason"] = ""

    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="emergency_shutdown_updated",
        before=current,
        after=saved,
        metadata={"notify_users": bool(body.notify_users)},
    )
    await _broadcast_platform_state_change()

    notification_summary = {"queued": False}
    if body.notify_users:
        title = "Emergency Platform Shutdown" if body.enabled else "Emergency Shutdown Lifted"
        message = (
            saved["emergency_shutdown"].get("reason")
            or ("Platform access is temporarily restricted." if body.enabled else "Emergency shutdown has been lifted.")
        )
        notification_summary = await _notify_audience(
            title=title,
            message=message,
            audience="all_non_admin",
            channels=saved.get("notification_channels") or {},
            notif_type="platform_emergency",
        )

    return {
        "status": "updated",
        "state": saved,
        "public_state": _public_state_projection(saved),
        "notification_summary": notification_summary,
    }


@router.put("/admin/system-status")
async def update_system_status(body: SystemStatusUpdateRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    next_state = copy.deepcopy(current)
    next_status = str(body.status).upper()

    if bool((next_state.get("emergency_shutdown") or {}).get("enabled", False)) and next_status != "OUTAGE":
        raise HTTPException(status_code=409, detail="Disable emergency shutdown before changing system status")

    next_state["system_status"] = next_status
    next_state["system_status_reason"] = str(body.reason or "")[:800]

    if next_status == "MAINTENANCE" and not bool((next_state.get("maintenance") or {}).get("enabled", False)):
        next_state["maintenance"]["enabled"] = True
        next_state["maintenance"]["starts_at"] = _iso_now()
        if not next_state["maintenance"].get("window_id"):
            next_state["maintenance"]["window_id"] = f"maint_{uuid.uuid4().hex[:10]}"
        await _update_maintenance_window_registry(next_state, "active")

    if next_status != "MAINTENANCE" and bool((next_state.get("maintenance") or {}).get("enabled", False)):
        next_state["maintenance"]["enabled"] = False
        await _update_maintenance_window_registry(next_state, "completed")

    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="system_status_updated",
        before=current,
        after=saved,
        metadata={"notify_users": bool(body.notify_users)},
    )
    await _broadcast_platform_state_change()

    notification_summary = {"queued": False}
    if body.notify_users and next_status in {"MAINTENANCE", "OUTAGE", "ONLINE"}:
        title = f"Platform Status: {next_status}"
        message = body.reason.strip() or f"Platform is currently {next_status}."
        notification_summary = await _notify_audience(
            title=title,
            message=message,
            audience="all_non_admin",
            channels=saved.get("notification_channels") or {},
            notif_type="platform_status",
        )

    return {
        "status": "updated",
        "state": saved,
        "public_state": _public_state_projection(saved),
        "notification_summary": notification_summary,
    }


@router.put("/admin/feature-toggles")
async def update_feature_toggles(body: FeatureTogglesUpdateRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    next_state = copy.deepcopy(current)
    for key, value in (body.feature_toggles or {}).items():
        next_state["feature_toggles"][str(key)] = bool(value)

    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="feature_toggles_updated",
        before=current,
        after=saved,
        metadata={"updated_keys": sorted(list((body.feature_toggles or {}).keys()))},
    )
    await _broadcast_platform_state_change()

    return {
        "status": "updated",
        "state": saved,
        "feature_toggles": saved.get("feature_toggles") or {},
    }


@router.put("/admin/notification-channels")
async def update_notification_channels(body: NotificationChannelsUpdateRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    next_state = copy.deepcopy(current)

    for key in ["in_app", "email", "sms", "push"]:
        value = getattr(body, key)
        if value is not None:
            next_state["notification_channels"][key] = bool(value)

    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="notification_channels_updated",
        before=current,
        after=saved,
        metadata={"channels": saved.get("notification_channels") or {}},
    )

    return {
        "status": "updated",
        "state": saved,
        "channel_notes": {
            "sms": "Configured channel only. Delivery depends on SMS provider integration.",
            "push": "Configured channel only. Delivery depends on push provider integration.",
        },
    }


@router.post("/admin/broadcast")
async def send_broadcast_message(body: BroadcastMessageRequest, request: Request):
    admin = await require_admin(request)
    current = await get_effective_platform_control_state(force_refresh=True)
    channels = current.get("notification_channels") or {}
    title = str(body.title or "").strip()
    message = str(body.message or "").strip()
    if not title or not message:
        raise HTTPException(status_code=422, detail="title and message are required")

    safe_title = title[:120]
    safe_message = message[:1500]
    estimated_target = await _estimate_audience_size(body.audience)
    asyncio.create_task(
        _notify_audience_background(
            title=safe_title,
            message=safe_message,
            audience=body.audience,
            channels=channels,
            notif_type="platform_broadcast",
        )
    )

    notify_summary = {
        "queued": True,
        "estimated_target": estimated_target,
        "email_enabled": bool(channels.get("email", True)),
        "in_app_enabled": bool(channels.get("in_app", True)),
        "sms_enabled": bool(channels.get("sms", False)),
        "push_enabled": bool(channels.get("push", False)),
    }

    next_state = copy.deepcopy(current)
    next_state["announcement"] = {
        "title": title[:120],
        "message": message[:1500],
        "updated_at": _iso_now(),
    }
    saved = await _save_platform_control_state(next_state, updated_by=getattr(admin, "email", "admin"))
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="broadcast_sent",
        before=current,
        after=saved,
        metadata={"audience": body.audience, "notification_summary": notify_summary},
    )

    return {
        "status": "sent",
        "state": saved,
        "notification_summary": notify_summary,
    }


@router.get("/admin/audit-logs")
async def get_platform_control_audit_logs(
    request: Request,
    limit: int = 50,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    search: Optional[str] = None,
):
    await require_admin(request)
    safe_limit = max(1, min(int(limit), 500))
    query = _build_audit_log_query(action=action, actor=actor, date_from=date_from, date_to=date_to, search=search)
    rows = await db.platform_control_audit_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    for row in rows:
        row["status"] = _audit_status_value(row)
    return {
        "logs": rows,
        "count": len(rows),
        "filters_applied": {
            "action": action,
            "actor": actor,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
        },
    }


@router.get("/admin/audit-logs/export")
async def export_platform_control_audit_logs(
    request: Request,
    format: Literal["csv", "json"] = "csv",
    limit: int = 1000,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    search: Optional[str] = None,
):
    await require_admin(request)
    safe_limit = max(1, min(int(limit), 2000))
    query = _build_audit_log_query(action=action, actor=actor, date_from=date_from, date_to=date_to, search=search)
    rows = await db.platform_control_audit_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    for row in rows:
        row["status"] = _audit_status_value(row)

    if format == "json":
        payload = json.dumps(rows, ensure_ascii=False)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=platform_audit_logs_{int(_now_utc().timestamp())}.json"},
        )

    csv_content = _export_audit_logs_csv(rows)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=platform_audit_logs_{int(_now_utc().timestamp())}.csv"},
    )


@router.get("/admin/announcement-templates")
async def list_announcement_templates(
    request: Request,
    include_disabled: bool = True,
    search: Optional[str] = None,
):
    await require_admin(request)
    query: Dict[str, Any] = {}
    if not include_disabled:
        query["enabled"] = True
    if search:
        query["$or"] = [
            {"name": {"$regex": str(search), "$options": "i"}},
            {"title": {"$regex": str(search), "$options": "i"}},
            {"message": {"$regex": str(search), "$options": "i"}},
        ]
    rows = await db.platform_control_announcement_templates.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"templates": rows, "count": len(rows)}


@router.post("/admin/announcement-templates")
async def create_announcement_template(body: AnnouncementTemplateCreateRequest, request: Request):
    admin = await require_admin(request)
    incoming = {
        "template_id": f"ann_tpl_{uuid.uuid4().hex[:12]}",
        "name": body.name,
        "title": body.title,
        "message": body.message,
        "audience": body.audience,
        "schedule_type": body.schedule_type,
        "scheduled_for": body.scheduled_for,
        "daily_time_utc": body.daily_time_utc,
        "weekly_day_utc": body.weekly_day_utc,
        "weekly_time_utc": body.weekly_time_utc,
        "channels": body.channels,
        "enabled": body.enabled,
        "created_by": getattr(admin, "email", "admin"),
        "updated_by": getattr(admin, "email", "admin"),
    }
    normalized = _normalize_template_doc(incoming)
    normalized["next_run_at"] = _compute_next_run_at(normalized) if normalized.get("enabled") else None
    normalized["updated_at"] = _iso_now()
    normalized["created_at"] = _iso_now()

    template_to_store = copy.deepcopy(normalized)
    await db.platform_control_announcement_templates.insert_one(template_to_store)
    normalized.pop("_id", None)
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="announcement_template_created",
        before={},
        after=normalized,
        metadata={"template_id": normalized["template_id"]},
    )
    return {"status": "created", "template": normalized}


@router.put("/admin/announcement-templates/{template_id}")
async def update_announcement_template(template_id: str, body: AnnouncementTemplateUpdateRequest, request: Request):
    admin = await require_admin(request)
    existing = await db.platform_control_announcement_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement template not found")

    merged = copy.deepcopy(existing)
    update_fields = body.dict(exclude_unset=True)
    for key, value in update_fields.items():
        merged[key] = value

    normalized = _normalize_template_doc(merged)
    normalized["updated_at"] = _iso_now()
    normalized["updated_by"] = getattr(admin, "email", "admin")
    normalized["next_run_at"] = _compute_next_run_at(normalized) if normalized.get("enabled") else None

    await db.platform_control_announcement_templates.update_one(
        {"template_id": template_id},
        {"$set": normalized},
    )
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="announcement_template_updated",
        before=existing,
        after=normalized,
        metadata={"template_id": template_id},
    )
    return {"status": "updated", "template": normalized}


@router.post("/admin/announcement-templates/{template_id}/dispatch")
async def dispatch_announcement_template(template_id: str, body: AnnouncementTemplateDispatchRequest, request: Request):
    admin = await require_admin(request)
    template = await db.platform_control_announcement_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Announcement template not found")
    if not body.notify_immediately:
        return {"status": "skipped", "template_id": template_id}

    summary = await _dispatch_announcement_template(
        template=template,
        actor_email=getattr(admin, "email", "admin"),
        actor_user_id=getattr(admin, "user_id", "admin"),
        trigger="manual_dispatch",
        queue_only=True,
    )
    updated = await db.platform_control_announcement_templates.find_one({"template_id": template_id}, {"_id": 0})
    return {"status": "dispatched", "template": updated, "summary": summary}


@router.delete("/admin/announcement-templates/{template_id}")
async def disable_announcement_template(template_id: str, request: Request):
    admin = await require_admin(request)
    existing = await db.platform_control_announcement_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement template not found")

    await db.platform_control_announcement_templates.update_one(
        {"template_id": template_id},
        {
            "$set": {
                "enabled": False,
                "next_run_at": None,
                "updated_at": _iso_now(),
                "updated_by": getattr(admin, "email", "admin"),
            }
        },
    )
    after = await db.platform_control_announcement_templates.find_one({"template_id": template_id}, {"_id": 0})
    await _write_audit_log(
        actor_user_id=getattr(admin, "user_id", None),
        actor_email=getattr(admin, "email", None),
        action="announcement_template_disabled",
        before=existing,
        after=after or {},
        metadata={"template_id": template_id},
    )
    return {"status": "disabled", "template": after}


@router.get("/public/state")
async def get_public_platform_control_state(request: Request):
    user = await get_current_user(request)
    state = await get_effective_platform_control_state(force_refresh=False)
    payload = _public_state_projection(state)
    payload["viewer"] = {
        "is_authenticated": bool(user),
        "is_admin": bool(getattr(user, "is_admin", False)) if user else False,
        "is_staff": _is_staff_user(user) if user else False,
    }
    return payload


@router.get("/public/countdown-stream")
async def countdown_stream():
    async def event_generator():
        while True:
            state = await get_effective_platform_control_state(force_refresh=True)
            payload = {
                "timestamp": _iso_now(),
                "active_mode": resolve_active_mode(state),
                "gate_payload": build_lock_response_payload(state),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/entitlement-lock")
async def get_entitlement_lock(request: Request):
    await require_admin(request)
    from utils.preprod_entitlement_lock import get_preprod_lock_snapshot

    return get_preprod_lock_snapshot()


@router.post("/entitlement-lock")
async def toggle_entitlement_lock(request: Request):
    admin = await require_admin(request)
    from utils.preprod_entitlement_lock import set_preprod_lock_state

    body = await request.json()
    if "active" not in body or not isinstance(body["active"], bool):
        raise HTTPException(status_code=400, detail="Body must include boolean 'active'")
    return await set_preprod_lock_state(body["active"], admin.email)
