"""Feature 34 Calendar Core routes (modularized from integrations.py)."""

from fastapi import APIRouter, Request

from routes.integrations import (
    get_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    delete_event_series,
    reschedule_event,
    calendar_status,
    get_due_reminders,
    get_upcoming_events,
    CalendarEventCreate,
    CalendarEventUpdate,
)


router = APIRouter()


@router.get("/calendar/events/{user_id}")
async def get_calendar_events_route(user_id: str, request: Request):
    return await get_calendar_events(user_id, request)


@router.post("/calendar/events")
async def create_calendar_event_route(request: CalendarEventCreate, req: Request):
    return await create_calendar_event(request, req)


@router.put("/calendar/events/{event_id}")
async def update_calendar_event_route(event_id: str, request: CalendarEventUpdate, req: Request):
    return await update_calendar_event(event_id, request, req)


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event_route(event_id: str, req: Request):
    return await delete_calendar_event(event_id, req)


@router.delete("/calendar/series/{series_id}")
async def delete_event_series_route(series_id: str, req: Request):
    return await delete_event_series(series_id, req)


@router.put("/calendar/events/{event_id}/reschedule")
async def reschedule_event_route(event_id: str, req: Request):
    return await reschedule_event(event_id, req)


@router.get("/calendar/status")
async def calendar_status_route(request: Request):
    return await calendar_status(request)


@router.get("/calendar/reminders/{user_id}")
async def get_due_reminders_route(user_id: str, request: Request):
    return await get_due_reminders(user_id, request)


@router.get("/calendar/upcoming/{user_id}")
async def get_upcoming_events_route(user_id: str, request: Request, limit: int = 5):
    return await get_upcoming_events(user_id, request, limit=limit)
