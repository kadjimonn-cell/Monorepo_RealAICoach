"""Feature 34 Calendar Sync routes (modularized from integrations.py)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from routes.db import db
from routes.integrations import (
    get_current_user,
    calendar_connect,
    calendar_oauth_callback,
    get_google_calendars,
    select_google_calendar,
    disconnect_google_calendar,
    sync_calendar,
    set_calendar_timezone,
    CalendarSelectRequest,
)


router = APIRouter()


@router.get("/integrations/calendar/auth")
@router.get("/calendar/connect")
async def calendar_connect_route(request: Request):
    return await calendar_connect(request)


@router.get("/oauth/calendar/callback")
async def calendar_oauth_callback_route(request: Request, code: str = "", state: str = "", error: str = ""):
    return await calendar_oauth_callback(request=request, code=code, state=state, error=error)


@router.get("/calendar/calendars")
async def get_google_calendars_route(request: Request):
    return await get_google_calendars(request)


@router.post("/calendar/select")
async def select_google_calendar_route(request: CalendarSelectRequest, req: Request):
    return await select_google_calendar(request, req)


@router.post("/calendar/disconnect")
async def disconnect_google_calendar_route(request: Request):
    return await disconnect_google_calendar(request)


@router.post("/calendar/sync")
async def sync_calendar_route(request: Request):
    started = datetime.now(timezone.utc)
    status = "success"
    response_payload = None
    user_id = ""
    try:
        user = await get_current_user(request)
        user_id = getattr(user, "user_id", "") if user else ""
        response_payload = await sync_calendar(request)
        return response_payload
    except Exception:
        status = "error"
        raise
    finally:
        ended = datetime.now(timezone.utc)
        latency_ms = int((ended - started).total_seconds() * 1000)
        try:
            if user_id:
                await db.calendar_sync_telemetry.insert_one(
                    {
                        "id": f"sync_{started.timestamp()}_{user_id[:8]}",
                        "user_id": user_id,
                        "status": status,
                        "latency_ms": latency_ms,
                        "created_at": ended.isoformat(),
                        "meta": {
                            "sync_mode": (response_payload or {}).get("sync_mode"),
                            "synced": (response_payload or {}).get("synced", 0),
                        },
                    }
                )
        except Exception:
            pass


@router.put("/calendar/timezone")
async def set_calendar_timezone_route(request: Request):
    return await set_calendar_timezone(request)
