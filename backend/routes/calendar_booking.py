"""Feature 34 Calendar Booking routes (modularized from integrations.py)."""

from datetime import datetime, timezone
from fastapi import APIRouter, Request

from routes.db import db
from routes.integrations import (
    create_booking_page,
    list_booking_pages,
    delete_booking_page,
    get_booking_page,
    book_slot,
    list_bookings,
    resend_booking_confirmation,
    cancel_booking_by_host,
    get_series_bookings,
    cancel_series,
    admin_booking_dashboard,
    cancel_booking,
    get_reschedule_info,
    reschedule_booking,
    trigger_reminders_manually,
    download_ics,
)


router = APIRouter()


@router.post("/calendar/booking-page")
async def create_booking_page_route(request: Request):
    return await create_booking_page(request)


@router.get("/calendar/booking-pages/{user_id}")
async def list_booking_pages_route(user_id: str, request: Request):
    return await list_booking_pages(user_id, request)


@router.delete("/calendar/booking-page/{token}")
async def delete_booking_page_route(token: str, request: Request):
    return await delete_booking_page(token, request)


@router.get("/calendar/booking/{token}")
async def get_booking_page_route(token: str, date: str = ""):
    payload = await get_booking_page(token, date=date)
    try:
        page = payload.get("page", {}) if isinstance(payload, dict) else {}
        user_id = str(page.get("user_id") or "").strip()
        if user_id:
            await db.calendar_booking_funnel_events.insert_one(
                {
                    "id": f"funnel_{datetime.now(timezone.utc).timestamp()}_{token[:6]}",
                    "user_id": user_id,
                    "token": token,
                    "stage": "view",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception:
        pass
    return payload


@router.post("/calendar/booking/{token}/book")
async def book_slot_route(token: str, request: Request):
    payload = await book_slot(token, request)
    try:
        booking = (payload or {}).get("booking", {}) if isinstance(payload, dict) else {}
        user_id = str(booking.get("user_id") or "").strip()
        if user_id:
            await db.calendar_booking_funnel_events.insert_one(
                {
                    "id": f"funnel_{datetime.now(timezone.utc).timestamp()}_{token[:6]}",
                    "user_id": user_id,
                    "token": token,
                    "stage": "booked",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "meta": {
                        "booking_id": booking.get("booking_id"),
                        "is_recurring": bool((payload or {}).get("is_recurring")),
                    },
                }
            )
    except Exception:
        pass
    return payload


@router.get("/calendar/bookings/{user_id}")
async def list_bookings_route(user_id: str, request: Request):
    return await list_bookings(user_id, request)


@router.post("/calendar/booking/{token}/resend-confirmation")
async def resend_booking_confirmation_route(token: str, request: Request):
    return await resend_booking_confirmation(token, request)


@router.post("/calendar/bookings/{booking_id}/cancel")
async def cancel_booking_by_host_route(booking_id: str, request: Request):
    return await cancel_booking_by_host(booking_id, request)


@router.get("/calendar/bookings/series/{series_id}")
async def get_series_bookings_route(series_id: str, request: Request):
    return await get_series_bookings(series_id, request)


@router.post("/calendar/bookings/series/{series_id}/cancel")
async def cancel_series_route(series_id: str, request: Request):
    return await cancel_series(series_id, request)


@router.get("/admin/booking-dashboard")
async def admin_booking_dashboard_route(request: Request):
    return await admin_booking_dashboard(request)


@router.get("/calendar/booking/cancel/{cancel_token}")
async def cancel_booking_route(cancel_token: str):
    return await cancel_booking(cancel_token)


@router.get("/calendar/booking/reschedule/{cancel_token}")
async def get_reschedule_info_route(cancel_token: str, date: str = ""):
    return await get_reschedule_info(cancel_token, date=date)


@router.post("/calendar/booking/reschedule/{cancel_token}")
async def reschedule_booking_route(cancel_token: str, request: Request):
    return await reschedule_booking(cancel_token, request)


@router.get("/calendar/booking/ics/{booking_id}")
async def download_ics_route(booking_id: str):
    return await download_ics(booking_id)


@router.post("/calendar/booking/send-reminders")
async def trigger_reminders_manually_route(request: Request):
    return await trigger_reminders_manually(request)
