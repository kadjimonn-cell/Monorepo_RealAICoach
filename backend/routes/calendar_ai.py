"""Feature 34 Calendar AI routes (modularized from integrations.py)."""

from fastapi import APIRouter, Request

from routes.integrations import (
    ai_suggest_time_slots,
    recommend_best_slot,
    best_slot_telemetry,
    commit_best_slot,
    best_slot_weekly_reward_badge,
    smart_suggestions,
    create_focus_blocks,
    AISuggestRequest,
    BestSlotRequest,
    BestSlotTelemetryRequest,
    BestSlotCommitRequest,
)


router = APIRouter()


@router.post("/calendar/ai-suggest")
async def ai_suggest_time_slots_route(request: AISuggestRequest, req: Request):
    return await ai_suggest_time_slots(request, req)


@router.post("/calendar/recommend-best-slot")
async def recommend_best_slot_route(request: BestSlotRequest, req: Request):
    return await recommend_best_slot(request, req)


@router.post("/calendar/recommend-best-slot/telemetry")
async def best_slot_telemetry_route(request: BestSlotTelemetryRequest, req: Request):
    return await best_slot_telemetry(request, req)


@router.post("/calendar/recommend-best-slot/commit")
async def commit_best_slot_route(request: BestSlotCommitRequest, req: Request):
    return await commit_best_slot(request, req)


@router.get("/calendar/recommend-best-slot/reward-badge/{user_id}")
async def best_slot_weekly_reward_badge_route(user_id: str, request: Request):
    return await best_slot_weekly_reward_badge(user_id, request)


@router.get("/calendar/smart-suggestions/{user_id}")
async def smart_suggestions_route(user_id: str, request: Request):
    return await smart_suggestions(user_id, request)


@router.post("/calendar/auto-focus-blocks/{user_id}")
async def create_focus_blocks_route(user_id: str, request: Request):
    return await create_focus_blocks(user_id, request)
