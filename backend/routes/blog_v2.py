"""Enterprise Blog V2 API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes.db import db, get_current_user
from services.blog_v2_service import (
    add_bookmark,
    ensure_blog_v2_seed,
    get_ai_summary,
    get_author_profile,
    get_bookmarks,
    get_history,
    get_home_payload,
    get_post_detail,
    get_recommendations,
    list_posts,
    remove_bookmark,
    write_history,
)
from services.blog_v2_engagement_service import (
    apply_owner_reminder_action,
    build_public_engagement_preview,
    claim_referral_bonus,
    consume_unlock_token_for_post,
    record_funnel_event,
    get_next_best_sequence,
    get_owner_engagement_loop,
    get_owner_rewards_snapshot,
    get_weekly_digest,
    send_weekly_digest_email,
    update_owner_reminder_settings,
)
from utils.access_control_engine import compute_effective_plan


router = APIRouter(prefix="/blog/v2", tags=["blog-v2"])


class BlogHistoryWriteRequest(BaseModel):
    post_id: str = Field(..., min_length=3)
    progress_percent: int = Field(default=0, ge=0, le=100)
    dwell_seconds: int = Field(default=0, ge=0, le=36000)


class BlogAISummaryRequest(BaseModel):
    slug: str = Field(..., min_length=2)


class BlogReminderSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = Field(default=None, description="adaptive | daily | three_per_week")
    digest_in_app_enabled: Optional[bool] = None
    digest_email_enabled: Optional[bool] = None


class BlogReminderActionRequest(BaseModel):
    action: str = Field(..., min_length=3, description="snooze_24h | dismiss | trigger_now")


class BlogReferralClaimRequest(BaseModel):
    invite_code: str = Field(..., min_length=4)


class BlogFunnelEventRequest(BaseModel):
    event_name: str = Field(..., min_length=3)
    context: Optional[dict] = None


async def _viewer_context(request: Request) -> tuple[Optional[object], Optional[str], str]:
    user = await get_current_user(request)
    if not user:
        return None, None, "free"

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not user_doc:
        if getattr(user, "is_admin", False):
            return user, f"auth:{user.user_id}", "admin"
        return user, f"auth:{user.user_id}", "free"

    effective = compute_effective_plan(user_doc)
    if getattr(user, "is_admin", False) and effective != "admin":
        effective = "admin"
    return user, f"auth:{user.user_id}", effective


def _require_auth_owner(owner_id: Optional[str]) -> str:
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return owner_id


@router.get("/home")
async def blog_v2_home(request: Request):
    await ensure_blog_v2_seed(db)
    _, owner_id, viewer_plan = await _viewer_context(request)
    payload = await get_home_payload(db, viewer_plan=viewer_plan, owner_id=owner_id)
    payload["viewer_plan"] = viewer_plan
    return payload


@router.get("/posts")
async def blog_v2_posts(
    request: Request,
    q: str = Query(default=""),
    category: str = Query(default=""),
    tag: str = Query(default=""),
    author_slug: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=24),
    sort: str = Query(default="latest"),
):
    await ensure_blog_v2_seed(db)
    _, owner_id, viewer_plan = await _viewer_context(request)
    result = await list_posts(
        db,
        viewer_plan=viewer_plan,
        owner_id=owner_id,
        query=q,
        category=category,
        tag=tag,
        author_slug=author_slug,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    result["viewer_plan"] = viewer_plan
    return result


@router.get("/posts/{slug}")
async def blog_v2_post_detail(request: Request, slug: str):
    await ensure_blog_v2_seed(db)
    _, owner_id, viewer_plan = await _viewer_context(request)
    detail = await get_post_detail(db, slug=slug, viewer_plan=viewer_plan, owner_id=owner_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Post not found")
    detail["viewer_plan"] = viewer_plan
    return detail


@router.get("/authors/{author_slug}")
async def blog_v2_author(request: Request, author_slug: str):
    await ensure_blog_v2_seed(db)
    _, _, viewer_plan = await _viewer_context(request)
    payload = await get_author_profile(db, author_slug=author_slug, viewer_plan=viewer_plan)
    if not payload:
        raise HTTPException(status_code=404, detail="Author not found")
    payload["viewer_plan"] = viewer_plan
    return payload


@router.get("/search")
async def blog_v2_search(
    request: Request,
    q: str = Query(default="", min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=24),
):
    _, owner_id, viewer_plan = await _viewer_context(request)
    result = await list_posts(
        db,
        viewer_plan=viewer_plan,
        owner_id=owner_id,
        query=q,
        page=page,
        page_size=page_size,
        sort="latest",
    )
    result["query"] = q
    return result


@router.get("/recommendations")
async def blog_v2_recommendations(request: Request, limit: int = Query(default=8, ge=1, le=12)):
    _, owner_id, viewer_plan = await _viewer_context(request)
    picks = await get_recommendations(db, owner_id=owner_id, viewer_plan=viewer_plan, limit=limit)
    return {"items": picks, "viewer_plan": viewer_plan}


@router.post("/ai/summary")
async def blog_v2_ai_summary(request: Request, payload: BlogAISummaryRequest):
    _, owner_id, viewer_plan = await _viewer_context(request)
    summary = await get_ai_summary(db, slug=payload.slug, viewer_plan=viewer_plan, owner_id=owner_id)
    if not summary.get("ok"):
        raise HTTPException(status_code=404, detail="Post not found")
    return summary


@router.post("/me/history")
async def blog_v2_write_history(request: Request, payload: BlogHistoryWriteRequest):
    _, owner_id, _viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    return await write_history(
        db,
        owner_id=owner,
        viewer_plan=_viewer_plan,
        post_id=payload.post_id,
        progress_percent=payload.progress_percent,
        dwell_seconds=payload.dwell_seconds,
    )


@router.get("/engagement-loop")
async def blog_v2_engagement_loop(request: Request):
    _, owner_id, viewer_plan = await _viewer_context(request)
    if not owner_id:
        return {"engagement_loop": build_public_engagement_preview(), "viewer_plan": viewer_plan}
    loop = await get_owner_engagement_loop(db, owner_id, viewer_plan)
    return {"engagement_loop": loop, "viewer_plan": viewer_plan}


@router.get("/next-best")
async def blog_v2_next_best(request: Request, limit: int = Query(default=5, ge=1, le=10), refresh: bool = Query(default=False)):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    payload = await get_next_best_sequence(db, owner_id=owner, viewer_plan=viewer_plan, limit=limit, force_refresh=bool(refresh))
    return payload


@router.get("/weekly-digest")
async def blog_v2_weekly_digest(request: Request, refresh: bool = Query(default=False), send_email: bool = Query(default=False)):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    digest = await get_weekly_digest(db, owner_id=owner, viewer_plan=viewer_plan, force_refresh=bool(refresh))
    email_result = None
    if bool(send_email):
        email_result = await send_weekly_digest_email(db, owner_id=owner, viewer_plan=viewer_plan)
    return {"digest": digest, "email_result": email_result}


@router.get("/me/rewards")
async def blog_v2_rewards_snapshot(request: Request):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    payload = await get_owner_rewards_snapshot(db, owner_id=owner, viewer_plan=viewer_plan)
    return payload


@router.post("/me/referral-claim")
async def blog_v2_referral_claim(request: Request, payload: BlogReferralClaimRequest):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    result = await claim_referral_bonus(db, claimer_owner_id=owner, viewer_plan=viewer_plan, invite_code=payload.invite_code)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "referral_claim_failed")
    await record_funnel_event(
        db,
        owner_id=owner,
        event_name="claim_success",
        context={"invite_code": payload.invite_code},
    )
    return result


@router.post("/me/unlock-premium/{post_id}")
async def blog_v2_unlock_premium(request: Request, post_id: str):
    _, owner_id, _viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    result = await consume_unlock_token_for_post(db, owner_id=owner, post_id=post_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "unlock_failed")
    await record_funnel_event(
        db,
        owner_id=owner,
        event_name="premium_unlock_consumed",
        context={"post_id": post_id, "status": result.get("status")},
    )
    return result


@router.post("/me/funnel-event")
async def blog_v2_funnel_event(request: Request, payload: BlogFunnelEventRequest):
    _, owner_id, _viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    result = await record_funnel_event(
        db,
        owner_id=owner,
        event_name=payload.event_name,
        context=payload.context or {},
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "funnel_event_rejected")
    return result


@router.patch("/me/reminder-settings")
async def blog_v2_update_reminder_settings(request: Request, payload: BlogReminderSettingsRequest):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    loop = await update_owner_reminder_settings(
        db,
        owner_id=owner,
        viewer_plan=viewer_plan,
        enabled=payload.enabled,
        mode=payload.mode,
        digest_in_app_enabled=payload.digest_in_app_enabled,
        digest_email_enabled=payload.digest_email_enabled,
    )
    return {"ok": True, "engagement_loop": loop}


@router.post("/me/reminder-action")
async def blog_v2_reminder_action(request: Request, payload: BlogReminderActionRequest):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    loop = await apply_owner_reminder_action(
        db,
        owner_id=owner,
        viewer_plan=viewer_plan,
        action=payload.action,
    )
    return {"ok": True, "engagement_loop": loop}


@router.get("/me/history")
async def blog_v2_history(request: Request):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    rows = await get_history(db, owner_id=owner, viewer_plan=viewer_plan)
    return {"items": rows}


@router.get("/me/bookmarks")
async def blog_v2_bookmarks(request: Request):
    _, owner_id, viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    rows = await get_bookmarks(db, owner_id=owner, viewer_plan=viewer_plan)
    return {"items": rows}


@router.post("/me/bookmarks/{post_id}")
async def blog_v2_add_bookmark(request: Request, post_id: str):
    _, owner_id, _viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    result = await add_bookmark(db, owner_id=owner, post_id=post_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="Post not found")
    return result


@router.delete("/me/bookmarks/{post_id}")
async def blog_v2_remove_bookmark(request: Request, post_id: str):
    _, owner_id, _viewer_plan = await _viewer_context(request)
    owner = _require_auth_owner(owner_id)
    return await remove_bookmark(db, owner_id=owner, post_id=post_id)
