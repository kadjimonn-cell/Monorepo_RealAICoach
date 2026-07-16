from __future__ import annotations

from fastapi import APIRouter, Query, Request

from .watch_audio_shared import AudioPlayRequest, FollowArtistRequest, InboxMarkListenedRequest
from .audio_studio_v2_service import (
    audio_studio_v2_admin_conversion_dashboard,
    audio_studio_v2_bootstrap,
    audio_studio_v2_daily_drop_inbox,
    audio_studio_v2_follow_artist,
    audio_studio_v2_mark_listened,
    audio_studio_v2_play,
    audio_studio_v2_unfollow_artist,
)


router = APIRouter(prefix="/audio-studio/v2", tags=["Audio Studio v2"])


@router.get("/bootstrap")
async def bootstrap(request: Request):
    return await audio_studio_v2_bootstrap(request)


@router.post("/play")
async def play(request: Request, payload: AudioPlayRequest):
    return await audio_studio_v2_play(request, payload)


@router.post("/follow-artist")
async def follow_artist(request: Request, payload: FollowArtistRequest):
    return await audio_studio_v2_follow_artist(request, payload)


@router.post("/unfollow-artist")
async def unfollow_artist(request: Request, payload: FollowArtistRequest):
    return await audio_studio_v2_unfollow_artist(request, payload)


@router.get("/daily-drop-inbox")
async def daily_drop_inbox(request: Request):
    return await audio_studio_v2_daily_drop_inbox(request)


@router.post("/daily-drop-inbox/mark-listened")
async def mark_listened(request: Request, payload: InboxMarkListenedRequest):
    return await audio_studio_v2_mark_listened(request, payload)


@router.get("/admin/conversion-dashboard")
async def admin_conversion_dashboard(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    return await audio_studio_v2_admin_conversion_dashboard(request, window_days)
