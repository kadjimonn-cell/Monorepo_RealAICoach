from __future__ import annotations

from fastapi import APIRouter, Query, Request

from .sports_v2_schemas import (
    AudioPlayRequest,
    FollowLeagueRequest,
    InboxMarkListenedRequest,
    SportsCategoryCurationPayload,
    SportsBlackoutRulePayload,
    SportsPredictionSubmitRequest,
    SportsReminderSettingsRequest,
)
from .sports_v2_service import (
    sports_v2_admin_conversion_dashboard,
    sports_v2_admin_delete_blackout_rule,
    sports_v2_admin_get_category_curation,
    sports_v2_admin_list_blackout_rules,
    sports_v2_admin_set_category_curation,
    sports_v2_admin_source_health,
    sports_v2_admin_upsert_blackout_rule,
    sports_v2_bootstrap,
    sports_v2_continue_watching,
    sports_v2_daily_drop_inbox,
    sports_v2_follow_league,
    sports_v2_live_now,
    sports_v2_mark_listened,
    sports_v2_matchday_streak,
    sports_v2_play,
    sports_v2_prediction_challenges,
    sports_v2_reminder_settings,
    sports_v2_secure_stream,
    sports_v2_submit_prediction,
    sports_v2_unfollow_league,
)


router = APIRouter(prefix="/sports/v2", tags=["Sports v2"])


@router.get("/bootstrap")
async def bootstrap(request: Request):
    return await sports_v2_bootstrap(request)


@router.post("/play")
async def play(request: Request, payload: AudioPlayRequest):
    return await sports_v2_play(request, payload)


@router.get("/secure-stream")
async def secure_stream(request: Request, item_id: str, token: str):
    return await sports_v2_secure_stream(request, item_id=item_id, token=token)


@router.get("/daily-drop-inbox")
async def daily_drop_inbox(request: Request):
    return await sports_v2_daily_drop_inbox(request)


@router.post("/daily-drop-inbox/mark-listened")
async def mark_listened(request: Request, payload: InboxMarkListenedRequest):
    return await sports_v2_mark_listened(request, payload)


@router.post("/follow-league")
async def follow_league(request: Request, payload: FollowLeagueRequest):
    return await sports_v2_follow_league(request, payload)


@router.post("/unfollow-league")
async def unfollow_league(request: Request, payload: FollowLeagueRequest):
    return await sports_v2_unfollow_league(request, payload)


@router.post("/reminder-settings")
async def reminder_settings(request: Request, payload: SportsReminderSettingsRequest):
    return await sports_v2_reminder_settings(
        request,
        league_name=payload.league_name,
        pre_kickoff_15_enabled=payload.pre_kickoff_15_enabled,
    )


@router.get("/continue-watching")
async def continue_watching(request: Request):
    return await sports_v2_continue_watching(request)


@router.get("/live-now")
async def live_now(request: Request):
    return await sports_v2_live_now(request)


@router.get("/matchday-streak")
async def matchday_streak(request: Request):
    return await sports_v2_matchday_streak(request)


@router.get("/prediction-challenges")
async def prediction_challenges(request: Request):
    return await sports_v2_prediction_challenges(request)


@router.post("/prediction-challenges/submit")
async def submit_prediction(request: Request, payload: SportsPredictionSubmitRequest):
    return await sports_v2_submit_prediction(request, payload)


@router.get("/admin/source-health")
async def admin_source_health(request: Request):
    return await sports_v2_admin_source_health(request)


@router.get("/admin/conversion-dashboard")
async def admin_conversion_dashboard(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    return await sports_v2_admin_conversion_dashboard(request, window_days)


@router.get("/admin/blackout-rules")
async def admin_list_blackout_rules(request: Request):
    return await sports_v2_admin_list_blackout_rules(request)


@router.post("/admin/blackout-rules")
async def admin_upsert_blackout_rule(request: Request, payload: SportsBlackoutRulePayload):
    return await sports_v2_admin_upsert_blackout_rule(
        request,
        rule_id=payload.rule_id,
        league=payload.league,
        countries=payload.countries,
        states=payload.states,
        start_at=payload.start_at,
        end_at=payload.end_at,
        reason=payload.reason,
        is_active=payload.is_active,
    )


@router.delete("/admin/blackout-rules/{rule_id}")
async def admin_delete_blackout_rule(request: Request, rule_id: str):
    return await sports_v2_admin_delete_blackout_rule(request, rule_id)


@router.get("/admin/category-curation")
async def admin_get_category_curation(request: Request):
    return await sports_v2_admin_get_category_curation(request)


@router.post("/admin/category-curation")
async def admin_set_category_curation(request: Request, payload: SportsCategoryCurationPayload):
    return await sports_v2_admin_set_category_curation(
        request,
        ordered_categories=payload.ordered_categories,
        pinned_categories=payload.pinned_categories,
    )
