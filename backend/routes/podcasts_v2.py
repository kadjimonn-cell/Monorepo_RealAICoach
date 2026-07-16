from __future__ import annotations

from fastapi import APIRouter, Query, Request

from .watch_audio_shared import AudioPlayRequest, InboxMarkListenedRequest
from .podcasts_v2_service import (
    podcasts_v2_admin_conversion_dashboard,
    podcasts_v2_bootstrap,
    podcasts_v2_continue_listening,
    podcasts_v2_daily_drop_inbox,
    podcasts_v2_mark_listened,
    podcasts_v2_play,
    podcasts_v2_season_arc,
    podcasts_v2_source_health,
)


router = APIRouter(prefix="/podcasts/v2", tags=["Podcasts v2"])


@router.get("/bootstrap")
async def bootstrap(request: Request):
    return await podcasts_v2_bootstrap(request)


@router.post("/play")
async def play(request: Request, payload: AudioPlayRequest):
    return await podcasts_v2_play(request, payload)


@router.get("/daily-drop-inbox")
async def daily_drop_inbox(request: Request):
    return await podcasts_v2_daily_drop_inbox(request)


@router.post("/daily-drop-inbox/mark-listened")
async def mark_listened(request: Request, payload: InboxMarkListenedRequest):
    return await podcasts_v2_mark_listened(request, payload)


@router.get("/continue-listening")
async def continue_listening(request: Request):
    return await podcasts_v2_continue_listening(request)


@router.get("/season-arc")
async def season_arc(request: Request, series_name: str = Query(default="", max_length=140)):
    return await podcasts_v2_season_arc(request, series_name)


@router.get("/source-health")
async def source_health(request: Request):
    return await podcasts_v2_source_health(request)


@router.get("/admin/conversion-dashboard")
async def admin_conversion_dashboard(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    return await podcasts_v2_admin_conversion_dashboard(request, window_days)
