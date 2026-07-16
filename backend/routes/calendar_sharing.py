"""Feature 34 Calendar sharing routes (modularized from integrations.py)."""

from fastapi import APIRouter, Request

from routes.integrations import (
    create_calendar_share,
    list_calendar_shares,
    revoke_calendar_share,
    view_shared_calendar,
)


router = APIRouter()


@router.post("/calendar/share")
async def create_calendar_share_route(request: Request):
    return await create_calendar_share(request)


@router.get("/calendar/shares/{user_id}")
async def list_calendar_shares_route(user_id: str, request: Request):
    return await list_calendar_shares(user_id, request)


@router.delete("/calendar/share/{token}")
async def revoke_calendar_share_route(token: str, request: Request):
    return await revoke_calendar_share(token, request)


@router.get("/calendar/shared/{token}")
async def view_shared_calendar_route(token: str):
    return await view_shared_calendar(token)
