"""Deprecated tombstone for legacy Watch Audio Hub wrappers.

Runtime ownership moved to:
- routes/watch_audio_shared.py (shared runtime logic)
- canonical v2 routes under /api/audio-studio/v2, /api/podcasts/v2, /api/sports/v2
- routes/watch_videos_retirement_governance.py for admin retirement controls
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/videos", tags=["Watch Audio Hub (Deprecated)"])


def _legacy_wrapper_retired_error(path_hint: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "LEGACY_WRAPPER_RETIRED",
            "message": "Legacy /api/videos wrapper retired. Use canonical v2 endpoints.",
            "path": path_hint,
            "migrate_to": [
                "/api/audio-studio/v2/*",
                "/api/podcasts/v2/*",
                "/api/sports/v2/*",
            ],
        },
    )


@router.get("/audio-studio/bootstrap")
async def deprecated_audio_studio_bootstrap():
    raise _legacy_wrapper_retired_error("/api/videos/audio-studio/bootstrap")


@router.post("/audio-studio/play")
async def deprecated_audio_studio_play():
    raise _legacy_wrapper_retired_error("/api/videos/audio-studio/play")


@router.get("/audio-studio/daily-drop-inbox")
async def deprecated_audio_studio_daily_drop_inbox():
    raise _legacy_wrapper_retired_error("/api/videos/audio-studio/daily-drop-inbox")


@router.post("/audio-studio/daily-drop-inbox/mark-listened")
async def deprecated_audio_studio_mark_listened():
    raise _legacy_wrapper_retired_error("/api/videos/audio-studio/daily-drop-inbox/mark-listened")


@router.get("/podcasts/bootstrap")
async def deprecated_podcasts_bootstrap():
    raise _legacy_wrapper_retired_error("/api/videos/podcasts/bootstrap")


@router.post("/podcasts/play")
async def deprecated_podcasts_play():
    raise _legacy_wrapper_retired_error("/api/videos/podcasts/play")


@router.get("/podcasts/daily-drop-inbox")
async def deprecated_podcasts_daily_drop_inbox():
    raise _legacy_wrapper_retired_error("/api/videos/podcasts/daily-drop-inbox")


@router.post("/podcasts/daily-drop-inbox/mark-listened")
async def deprecated_podcasts_mark_listened():
    raise _legacy_wrapper_retired_error("/api/videos/podcasts/daily-drop-inbox/mark-listened")


@router.get("/sports/bootstrap")
async def deprecated_sports_bootstrap():
    raise _legacy_wrapper_retired_error("/api/videos/sports/bootstrap")


@router.post("/sports/play")
async def deprecated_sports_play():
    raise _legacy_wrapper_retired_error("/api/videos/sports/play")


@router.get("/sports/daily-drop-inbox")
async def deprecated_sports_daily_drop_inbox():
    raise _legacy_wrapper_retired_error("/api/videos/sports/daily-drop-inbox")


@router.post("/sports/daily-drop-inbox/mark-listened")
async def deprecated_sports_mark_listened():
    raise _legacy_wrapper_retired_error("/api/videos/sports/daily-drop-inbox/mark-listened")


@router.post("/sports/follow-league")
async def deprecated_sports_follow_league():
    raise _legacy_wrapper_retired_error("/api/videos/sports/follow-league")


@router.post("/sports/reminder-settings")
async def deprecated_sports_reminder_settings():
    raise _legacy_wrapper_retired_error("/api/videos/sports/reminder-settings")
