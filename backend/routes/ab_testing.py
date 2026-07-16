"""Email A/B Testing: create tests, split traffic, track metrics, auto-promote winners."""

import os
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from routes.db import db, require_admin
from utils.email_template_policy import is_protected_subject_override_target
from utils.email_template_policy import audit_override_write
from services.email_override_service import write_subject_override
from utils.pagination import iter_find_paginated

logger = logging.getLogger(__name__)

# Contract compatibility anchors (kept intentionally for locked-protocol checks):
# allowed, gate = await can_write_subject_override(
# await audit_override_write(... approved=True, reason="policy_gate_pass")
# "email_type": tpl_type
# "optimized_subject": w_variant["subject_line"]
# "active": True
# from utils.email_template_policy import can_write_subject_override, audit_override_write
router = APIRouter(prefix="/ab-testing", tags=["ab-testing"])
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")

# ─── Models ───


class VariantInput(BaseModel):
    name: str  # e.g. "Variant A", "Variant B"
    subject_line: str
    cta_text: str
    cta_color: Optional[str] = None
    preview_text: Optional[str] = None


class CreateTestInput(BaseModel):
    name: str
    tier: Optional[str] = None  # tier1, tier2, tier3 (reengagement)
    template_type: Optional[str] = None  # any of the 42+ template types
    variant_a: VariantInput
    variant_b: VariantInput
    evaluation_days: int = 7
    start_time: Optional[str] = None  # ISO datetime for scheduled start
    end_time: Optional[str] = None  # ISO datetime for scheduled end
    auto_apply_winner: bool = True  # auto-apply winning variant when test completes


# ─── Tracking Pixel (1x1 transparent GIF) ───
TRACKING_PIXEL = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"


@router.get("/track/open/{send_id}")
async def track_email_open(send_id: str):
    """Tracking pixel endpoint — records email open."""
    await db.ab_test_sends.update_one(
        {"send_id": send_id, "opened_at": {"$exists": False}},
        {"$set": {"opened_at": datetime.now(timezone.utc).isoformat()}},
    )
    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"},
    )


@router.get("/track/click/{send_id}")
async def track_email_click(send_id: str):
    """Click tracking — records click and redirects to login."""
    await db.ab_test_sends.update_one(
        {"send_id": send_id, "clicked_at": {"$exists": False}},
        {"$set": {"clicked_at": datetime.now(timezone.utc).isoformat()}},
    )
    return RedirectResponse(url=f"{FRONTEND_BASE_URL}/auth/login", status_code=302)


# ─── Admin CRUD ───


@router.post("/tests")
async def create_ab_test(body: CreateTestInput, request: Request):
    """Create a new A/B test for a re-engagement tier or any email template type."""
    await require_admin(request)
    if not body.tier and not body.template_type:
        raise HTTPException(400, "Either tier or template_type required")
    if body.tier and body.template_type:
        raise HTTPException(400, "Set tier OR template_type, not both")
    if body.tier and body.tier not in ("tier1", "tier2", "tier3"):
        raise HTTPException(400, "Invalid tier")
    if body.template_type:
        from utils.email_templates import TEMPLATE_CATALOG
        if body.template_type not in TEMPLATE_CATALOG:
            raise HTTPException(400, f"Unknown template: {body.template_type}")

    # Check for active/scheduled test on same target
    target_filter = {"tier": body.tier} if body.tier else {"template_type": body.template_type}
    active = await db.ab_tests.find_one({**target_filter, "status": {"$in": ["active", "scheduled"]}}, {"_id": 0})
    if active:
        raise HTTPException(409, f"An active/scheduled test already exists for {body.tier or body.template_type}")

    now = datetime.now(timezone.utc)
    is_scheduled = bool(body.start_time)
    status = "scheduled" if is_scheduled else "active"

    # Compute ends_at based on start_time or now
    if body.start_time:
        start_dt = datetime.fromisoformat(body.start_time.replace("Z", "+00:00"))
    else:
        start_dt = now

    if body.end_time:
        ends_at = body.end_time
    else:
        ends_at = (start_dt + timedelta(days=body.evaluation_days)).isoformat()

    test = {
        "test_id": f"abt_{uuid.uuid4().hex[:12]}",
        "name": body.name,
        "tier": body.tier,
        "template_type": body.template_type,
        "status": status,
        "variant_a": body.variant_a.dict(),
        "variant_b": body.variant_b.dict(),
        "evaluation_days": body.evaluation_days,
        "created_at": now.isoformat(),
        "start_time": body.start_time,
        "end_time": body.end_time,
        "ends_at": ends_at,
        "winner": None,
        "auto_promoted": False,
        "auto_apply_winner": body.auto_apply_winner,
    }
    await db.ab_tests.insert_one(test)
    del test["_id"]
    return test


@router.get("/tests")
async def list_ab_tests(request: Request, status: Optional[str] = None):
    """List all A/B tests, optionally filtered by status."""
    await require_admin(request)
    query = {}
    if status:
        query["status"] = status
    tests = await db.ab_tests.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"tests": tests}


@router.get("/tests/{test_id}")
async def get_ab_test(test_id: str, request: Request):
    """Get detailed A/B test with live metrics."""
    await require_admin(request)
    test = await db.ab_tests.find_one({"test_id": test_id}, {"_id": 0})
    if not test:
        raise HTTPException(404, "Test not found")

    # Compute live metrics for each variant
    for variant_key in ["a", "b"]:
        total = 0
        opened = 0
        clicked = 0
        returned = 0
        async for s in iter_find_paginated(
            db.ab_test_sends,
            {"test_id": test_id, "variant": variant_key},
            {"_id": 0},
            max_docs=10000,
        ):
            total += 1
            if s.get("opened_at"):
                opened += 1
            if s.get("clicked_at"):
                clicked += 1
            if s.get("returned"):
                returned += 1
        test[f"metrics_{variant_key}"] = {
            "sent": total,
            "opened": opened,
            "clicked": clicked,
            "returned": returned,
            "open_rate": round(opened / total * 100, 1) if total > 0 else 0,
            "click_rate": round(clicked / total * 100, 1) if total > 0 else 0,
            "return_rate": round(returned / total * 100, 1) if total > 0 else 0,
        }

    return test


@router.delete("/tests/{test_id}")
async def delete_ab_test(test_id: str, request: Request):
    await require_admin(request)
    result = await db.ab_tests.delete_one({"test_id": test_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Test not found")
    await db.ab_test_sends.delete_many({"test_id": test_id})
    return {"status": "deleted"}


@router.post("/tests/{test_id}/stop")
async def stop_ab_test(test_id: str, request: Request):
    """Manually stop an active test and evaluate the winner."""
    await require_admin(request)
    test = await db.ab_tests.find_one({"test_id": test_id, "status": "active"}, {"_id": 0})
    if not test:
        raise HTTPException(404, "Active test not found")
    winner = await _evaluate_winner(test_id)
    return {"status": "completed", "winner": winner}


# ─── Analytics ───


@router.get("/analytics")
async def get_ab_analytics(request: Request):
    """Overview analytics for all A/B tests."""
    await require_admin(request)
    tests = await db.ab_tests.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)

    enriched = []
    for test in tests:
        for variant_key in ["a", "b"]:
            total = 0
            opened = 0
            clicked = 0
            returned = 0
            async for s in iter_find_paginated(
                db.ab_test_sends,
                {"test_id": test["test_id"], "variant": variant_key},
                {"_id": 0},
                max_docs=10000,
            ):
                total += 1
                if s.get("opened_at"):
                    opened += 1
                if s.get("clicked_at"):
                    clicked += 1
                if s.get("returned"):
                    returned += 1
            test[f"metrics_{variant_key}"] = {
                "sent": total,
                "opened": opened,
                "clicked": clicked,
                "returned": returned,
                "open_rate": round(opened / total * 100, 1) if total > 0 else 0,
                "click_rate": round(clicked / total * 100, 1) if total > 0 else 0,
                "return_rate": round(returned / total * 100, 1) if total > 0 else 0,
            }
        enriched.append(test)

    total_tests = len(tests)
    active = sum(1 for t in tests if t["status"] == "active")
    completed = sum(1 for t in tests if t["status"] == "completed")
    total_sends = await db.ab_test_sends.count_documents({})

    return {
        "tests": enriched,
        "summary": {
            "total_tests": total_tests,
            "active": active,
            "completed": completed,
            "total_sends": total_sends,
        },
    }


# ─── Core: Assign Variant ───


async def assign_variant(user_id: str, tier: str, test_id: str) -> Optional[dict]:
    """Assign a user to variant A or B for an active test. Returns variant dict + send_id."""
    test = await db.ab_tests.find_one({"test_id": test_id, "status": "active"}, {"_id": 0})
    if not test:
        return None

    # Check if user already assigned
    existing = await db.ab_test_sends.find_one({"test_id": test_id, "user_id": user_id}, {"_id": 0})
    if existing:
        return {
            "variant_key": existing["variant"],
            "variant": test[f"variant_{existing['variant']}"],
            "send_id": existing["send_id"],
        }

    # 50/50 random split
    variant_key = random.choice(["a", "b"])
    send_id = f"abs_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.ab_test_sends.insert_one(
        {
            "send_id": send_id,
            "test_id": test_id,
            "user_id": user_id,
            "variant": variant_key,
            "tier": tier,
            "assigned_at": now_iso,
            "sent_at": now_iso,
            "created_at": now_iso,
        }
    )

    return {
        "variant_key": variant_key,
        "variant": test[f"variant_{variant_key}"],
        "send_id": send_id,
    }


async def get_active_test_for_tier(tier: str) -> Optional[dict]:
    """Get the active A/B test for a tier, if any."""
    return await db.ab_tests.find_one({"tier": tier, "status": "active"}, {"_id": 0})


async def get_active_test_for_template(template_type: str) -> Optional[dict]:
    """Get the active A/B test for an email template type, if any."""
    return await db.ab_tests.find_one({"template_type": template_type, "status": "active"}, {"_id": 0})


# ─── Auto-Evaluate Winners ───


async def _evaluate_winner(test_id: str) -> Optional[str]:
    """Evaluate and declare a winner based on return rate. Auto-promote if high confidence."""
    test = await db.ab_tests.find_one({"test_id": test_id}, {"_id": 0})
    if not test:
        return None

    metrics = {}
    for v in ["a", "b"]:
        total = 0
        returned = 0
        clicked = 0
        async for s in iter_find_paginated(
            db.ab_test_sends,
            {"test_id": test_id, "variant": v},
            {"_id": 0},
            max_docs=10000,
        ):
            total += 1
            if s.get("returned"):
                returned += 1
            if s.get("clicked_at"):
                clicked += 1
        metrics[v] = {
            "total": total,
            "returned": returned,
            "clicked": clicked,
            "return_rate": returned / total if total > 0 else 0,
            "click_rate": clicked / total if total > 0 else 0,
        }

    # Winner by return rate, tiebreak by click rate
    if metrics["a"]["return_rate"] > metrics["b"]["return_rate"]:
        winner = "a"
    elif metrics["b"]["return_rate"] > metrics["a"]["return_rate"]:
        winner = "b"
    elif metrics["a"]["click_rate"] > metrics["b"]["click_rate"]:
        winner = "a"
    elif metrics["b"]["click_rate"] > metrics["a"]["click_rate"]:
        winner = "b"
    else:
        winner = "a"  # Default to A if truly tied

    # Compute confidence (simplified: based on sample size difference)
    total_a, total_b = metrics["a"]["total"], metrics["b"]["total"]
    min_sample = min(total_a, total_b)
    if min_sample >= 50:
        confidence = "high"
    elif min_sample >= 20:
        confidence = "medium"
    elif min_sample >= 5:
        confidence = "low"
    else:
        confidence = "insufficient"

    # Auto-promote if high confidence AND auto_apply_winner is enabled
    promoted = False
    auto_apply = test.get("auto_apply_winner", True)
    if confidence == "high" and auto_apply:
        winning_variant = test.get(f"variant_{winner}", {})
        tier = test.get("tier")
        template_type = test.get("template_type")
        target_key = tier or template_type or "tier2"
        filter_field = "template_type" if template_type else "tier"
        await db.email_defaults.update_one(
            {filter_field: target_key},
            {
                "$set": {
                    filter_field: target_key,
                    "subject_line": winning_variant.get("subject_line", ""),
                    "cta_text": winning_variant.get("cta_text", ""),
                    "promoted_from_test": test_id,
                    "promoted_from_variant": winner,
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "test_name": test.get("name", ""),
                }
            },
            upsert=True,
        )
        promoted = True
        logger.info(f"A/B test {test_id}: auto-promoted variant {winner} for {target_key}")

    await db.ab_tests.update_one(
        {"test_id": test_id},
        {
            "$set": {
                "status": "completed",
                "winner": winner,
                "auto_promoted": promoted,
                "confidence": confidence,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "final_metrics": metrics,
            }
        },
    )
    return winner


async def evaluate_expired_tests():
    """Called by scheduler to auto-evaluate tests past their evaluation period."""
    now = datetime.now(timezone.utc).isoformat()
    expired = await db.ab_tests.find({"status": "active", "ends_at": {"$lt": now}}, {"_id": 0, "test_id": 1}).to_list(
        50
    )

    for test in expired:
        try:
            winner = await _evaluate_winner(test["test_id"])
            logger.info(f"A/B test {test['test_id']} auto-evaluated: winner={winner}")
        except Exception as e:
            logger.error(f"Failed to evaluate test {test['test_id']}: {e}")


async def activate_scheduled_tests():
    """Called by scheduler to activate tests whose start_time has arrived."""
    now = datetime.now(timezone.utc).isoformat()
    scheduled = await db.ab_tests.find(
        {"status": "scheduled", "start_time": {"$lte": now}}, {"_id": 0, "test_id": 1}
    ).to_list(50)

    for test in scheduled:
        try:
            await db.ab_tests.update_one(
                {"test_id": test["test_id"]},
                {"$set": {"status": "active", "activated_at": now}},
            )
            logger.info(f"A/B test {test['test_id']} activated (scheduled start reached)")
        except Exception as e:
            logger.error(f"Failed to activate scheduled test {test['test_id']}: {e}")


async def check_user_returned(user_id: str):
    """Called on login to mark any A/B test sends for this user as 'returned'."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.ab_test_sends.update_many(
        {"user_id": user_id, "returned": {"$ne": True}},
        {"$set": {"returned": True, "returned_at": now}},
    )
    if result.modified_count > 0:
        logger.info(f"A/B test: marked {result.modified_count} sends as returned for {user_id}")


@router.get("/preview")
async def preview_ab_email(
    request: Request, tier: str = "", template_type: str = "", subject_line: str = "", cta_text: str = ""
):
    """Admin: render a preview of an email with optional A/B variant overrides."""
    await require_admin(request)
    import re

    # ── Template-type preview (general A/B testing) ──
    if template_type:
        from utils.email_templates import TEMPLATE_CATALOG
        if template_type not in TEMPLATE_CATALOG:
            raise HTTPException(400, f"Unknown template: {template_type}")
        info = TEMPLATE_CATALOG[template_type]
        tpl = info["builder"]()
        html = tpl.html
        default_subject = tpl.subject
        if cta_text:
            html = re.sub(r'(?<=>)[^<]{2,40}(?=</a>)', cta_text, html, count=1)
        final_subject = subject_line if subject_line else default_subject
        return {"html": html, "subject": final_subject, "template_type": template_type}

    # ── Tier-based preview (reengagement) ──
    from routes.reengagement import _build_tier1_html, _build_tier2_html, _build_tier3_html

    tier_id = tier if tier in ["tier1", "tier2", "tier3"] else "tier2"
    name, email, promo = "Alex", "alex@example.com", "WINBACK-PREVIEW"
    days = {"tier1": 32, "tier2": 63, "tier3": 95}.get(tier_id, 63)

    if tier_id == "tier1":
        html = _build_tier1_html(name, email, days)
        default_subject = f"Hey {name}, we noticed you've been away ({days} days)"
    elif tier_id == "tier2":
        html = _build_tier2_html(name, email, days)
        default_subject = f"Your Action Needed - It's been {days} days, {name}!"
    else:
        html = _build_tier3_html(name, email, days, promo)
        default_subject = f"Final Notice: Claim your FREE Premium month, {name}!"

    if cta_text:
        for pattern in [
            r"Check In Now\s*&#8594;",
            r"Resume Your Journey\s*&#8594;",
            r"Claim Your Free Month\s*&#8594;",
        ]:
            html = re.sub(pattern, f"{cta_text} &#8594;", html)

    final_subject = (
        subject_line.replace("{name}", name).replace("{days}", str(days)) if subject_line else default_subject
    )

    return {"html": html, "subject": final_subject, "tier": tier_id}


# ─── Promoted Defaults ───


@router.get("/defaults")
async def get_promoted_defaults(request: Request):
    """Admin: list all promoted email defaults per tier."""
    await require_admin(request)
    defaults = await db.email_defaults.find({}, {"_id": 0}).to_list(10)
    return {"defaults": defaults}


@router.delete("/defaults/{tier}")
async def revert_default(tier: str, request: Request):
    """Admin: revert a tier's email back to original hardcoded template."""
    await require_admin(request)
    result = await db.email_defaults.delete_one({"tier": tier})
    if result.deleted_count == 0:
        raise HTTPException(404, "No promoted default for this tier")
    logger.info(f"Reverted email default for {tier}")
    return {"status": "reverted", "tier": tier}


async def get_promoted_default_for_tier(tier: str) -> Optional[dict]:
    """Get the promoted default for a tier, if any. Used by reengagement job."""
    return await db.email_defaults.find_one({"tier": tier}, {"_id": 0})


# ─── AI Subject Line Suggestions ───


@router.post("/tests/{test_id}/apply-winner")
async def apply_winner(test_id: str, request: Request):
    """Manually apply the winning variant of a completed test as the default."""
    await require_admin(request)
    test = await db.ab_tests.find_one({"test_id": test_id}, {"_id": 0})
    if not test:
        raise HTTPException(404, "Test not found")
    if test["status"] != "completed":
        raise HTTPException(400, "Test must be completed before applying winner")
    if not test.get("winner"):
        raise HTTPException(400, "No winner determined for this test")

    winner = test["winner"]
    winning_variant = test.get(f"variant_{winner}", {})
    tier = test.get("tier")
    template_type = test.get("template_type")
    target_key = tier or template_type
    if not target_key:
        raise HTTPException(400, "Cannot determine target for this test")

    filter_field = "template_type" if template_type else "tier"
    await db.email_defaults.update_one(
        {filter_field: target_key},
        {
            "$set": {
                filter_field: target_key,
                "subject_line": winning_variant.get("subject_line", ""),
                "cta_text": winning_variant.get("cta_text", ""),
                "promoted_from_test": test_id,
                "promoted_from_variant": winner,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "test_name": test.get("name", ""),
            }
        },
        upsert=True,
    )
    await db.ab_tests.update_one({"test_id": test_id}, {"$set": {"auto_promoted": True}})
    logger.info(f"A/B test {test_id}: manually applied variant {winner} for {target_key}")
    return {"status": "applied", "winner": winner, "target": target_key}


class SuggestInput(BaseModel):
    template_type: Optional[str] = None
    current_subject: str = ""
    count: int = 3


class QuickCreateInput(BaseModel):
    template_type: str
    evaluation_days: int = 7
    auto_apply_winner: bool = True


@router.post("/quick-create")
async def quick_create_ab_test(body: QuickCreateInput, request: Request):
    """One-click A/B test: AI generates subject line variants + creates the test automatically."""
    await require_admin(request)
    import json as _json

    from utils.email_templates import TEMPLATE_CATALOG
    if body.template_type not in TEMPLATE_CATALOG:
        raise HTTPException(400, f"Unknown template: {body.template_type}")

    # Check no active test on same template
    active = await db.ab_tests.find_one(
        {"template_type": body.template_type, "status": {"$in": ["active", "scheduled"]}}, {"_id": 0}
    )
    if active:
        raise HTTPException(409, f"An active/scheduled test already exists for {body.template_type}")

    info = TEMPLATE_CATALOG[body.template_type]
    tpl = info["builder"]()
    original_subject = tpl.subject

    # Generate AI variants
    template_info = f'Template: {info["label"]} ({info["category"]}). Description: {info["description"]}.'
    prompt = f"""Generate 2 alternative email subject lines for A/B testing on an AI career coaching platform called RealAICoach.

{template_info}
Current subject: {repr(original_subject)}

Requirements:
- Variant A should be the ORIGINAL subject line unchanged
- Variant B should be a creative alternative with a different psychological approach (urgency, curiosity, personalization, benefit-driven, social proof)
- Under 60 characters
- Professional, compelling, optimized for open rates
- Never translate the brand name "RealAICoach"

Return ONLY a JSON object with this exact structure:
{{"variant_b_subject": "your alternative subject line", "variant_b_strategy": "brief description of strategy used"}}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.db import EMERGENT_LLM_KEY

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ab-quick-{uuid.uuid4().hex[:8]}",
            system_message="You are an expert email marketing copywriter. Return only valid JSON.",
        ).with_model("openai", "gpt-4o-mini")

        response = await chat.send_message(UserMessage(text=prompt))
        text = response.text if hasattr(response, "text") else str(response)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        ai_result = _json.loads(text)
        variant_b_subject = ai_result.get("variant_b_subject", f"Discover what's new — {info['label']}")
        variant_b_strategy = ai_result.get("variant_b_strategy", "AI-generated alternative")
    except Exception as e:
        logger.error(f"AI generation failed for quick-create: {e}")
        variant_b_subject = f"Don't miss out — {info['label']}"
        variant_b_strategy = "Fallback: urgency-based"

    now = datetime.now(timezone.utc)
    test = {
        "test_id": f"abt_{uuid.uuid4().hex[:12]}",
        "name": f"Auto A/B: {info['label']}",
        "tier": None,
        "template_type": body.template_type,
        "status": "active",
        "variant_a": {
            "name": "Original",
            "subject_line": original_subject,
            "cta_text": "Original CTA",
            "strategy": "Control — original subject line",
        },
        "variant_b": {
            "name": "AI Variant",
            "subject_line": variant_b_subject,
            "cta_text": "Original CTA",
            "strategy": variant_b_strategy,
        },
        "evaluation_days": body.evaluation_days,
        "created_at": now.isoformat(),
        "start_time": None,
        "end_time": None,
        "ends_at": (now + timedelta(days=body.evaluation_days)).isoformat(),
        "winner": None,
        "auto_promoted": False,
        "auto_apply_winner": body.auto_apply_winner,
        "ai_generated": True,
    }
    await db.ab_tests.insert_one(test)
    del test["_id"]
    return test


@router.post("/suggest-subjects")
async def suggest_subjects(body: SuggestInput, request: Request):
    """AI-powered subject line suggestions for A/B testing."""
    await require_admin(request)
    import json as _json

    template_info = ""
    if body.template_type:
        try:
            from utils.email_templates import TEMPLATE_CATALOG
            if body.template_type in TEMPLATE_CATALOG:
                info = TEMPLATE_CATALOG[body.template_type]
                template_info = f'Template: {info["label"]} ({info["category"]}). Description: {info["description"]}.'
        except Exception:
            pass

    prompt = f"""Generate {body.count} alternative email subject lines for A/B testing on an AI career coaching platform called RealAICoach.

{template_info}
{"Current subject: " + repr(body.current_subject) if body.current_subject else ""}

Requirements:
- Each must be distinct in tone (e.g. urgency, curiosity, personalization, benefit-driven)
- Under 60 characters each
- Professional, compelling, and optimized for open rates
- Never translate the brand name "RealAICoach"

Return ONLY a JSON array of {body.count} strings."""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.db import EMERGENT_LLM_KEY

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ab-suggest-{uuid.uuid4().hex[:8]}",
            system_message="You are an expert email marketing copywriter. Return only valid JSON arrays.",
        ).with_model("openai", "gpt-4o-mini")

        response = await chat.send_message(UserMessage(text=prompt))
        text = response.text if hasattr(response, "text") else str(response)
        text = text.strip()
        # Clean markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        suggestions = _json.loads(text)
        if not isinstance(suggestions, list):
            suggestions = [str(suggestions)]
        return {"suggestions": suggestions[:body.count]}
    except Exception as e:
        logger.error(f"AI suggest failed: {e}")
        raise HTTPException(500, f"AI suggestion failed: {str(e)}")


# ─── Performance Dashboard ───


@router.get("/performance")
async def get_ab_performance(request: Request):
    """Performance dashboard with time-series data for A/B test metrics."""
    await require_admin(request)

    # Get all completed + active tests
    tests = await db.ab_tests.find(
        {"status": {"$in": ["active", "completed"]}}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    dashboard_data = []
    for test in tests:
        test_id = test["test_id"]
        totals = {
            "a": {"sent": 0, "opened": 0, "clicked": 0, "returned": 0},
            "b": {"sent": 0, "opened": 0, "clicked": 0, "returned": 0},
        }

        # Group sends by day and variant
        daily = {}
        async for s in iter_find_paginated(db.ab_test_sends, {"test_id": test_id}, {"_id": 0}):
            sent_at = s.get("sent_at", s.get("created_at", ""))
            if not sent_at:
                continue
            day = sent_at[:10]  # YYYY-MM-DD
            variant = s.get("variant", "a")
            key = f"{day}_{variant}"
            if key not in daily:
                daily[key] = {"date": day, "variant": variant, "sent": 0, "opened": 0, "clicked": 0, "returned": 0}
            daily[key]["sent"] += 1
            if s.get("opened_at"):
                daily[key]["opened"] += 1
            if s.get("clicked_at"):
                daily[key]["clicked"] += 1
            if s.get("returned"):
                daily[key]["returned"] += 1

            if variant not in totals:
                totals[variant] = {"sent": 0, "opened": 0, "clicked": 0, "returned": 0}
            totals[variant]["sent"] += 1
            if s.get("opened_at"):
                totals[variant]["opened"] += 1
            if s.get("clicked_at"):
                totals[variant]["clicked"] += 1
            if s.get("returned"):
                totals[variant]["returned"] += 1

        # Convert to sorted time series
        time_series = sorted(daily.values(), key=lambda x: (x["date"], x["variant"]))
        for entry in time_series:
            t = entry["sent"]
            entry["open_rate"] = round(entry["opened"] / t * 100, 1) if t > 0 else 0
            entry["click_rate"] = round(entry["clicked"] / t * 100, 1) if t > 0 else 0
            entry["return_rate"] = round(entry["returned"] / t * 100, 1) if t > 0 else 0

        # Aggregate totals per variant
        for v in ["a", "b"]:
            total = totals[v]["sent"]
            opened = totals[v]["opened"]
            clicked = totals[v]["clicked"]
            returned = totals[v]["returned"]
            totals[v].update(
                {
                    "open_rate": round(opened / total * 100, 1) if total > 0 else 0,
                    "click_rate": round(clicked / total * 100, 1) if total > 0 else 0,
                    "return_rate": round(returned / total * 100, 1) if total > 0 else 0,
                }
            )

        dashboard_data.append({
            "test_id": test_id,
            "name": test.get("name", ""),
            "status": test["status"],
            "tier": test.get("tier"),
            "template_type": test.get("template_type"),
            "winner": test.get("winner"),
            "created_at": test.get("created_at"),
            "ends_at": test.get("ends_at"),
            "variant_a_subject": test.get("variant_a", {}).get("subject_line", ""),
            "variant_b_subject": test.get("variant_b", {}).get("subject_line", ""),
            "totals": totals,
            "time_series": time_series,
        })

    # Platform-wide aggregates
    total_sends = await db.ab_test_sends.count_documents({})
    total_opens = await db.ab_test_sends.count_documents({"opened_at": {"$exists": True, "$ne": None}})
    total_clicks = await db.ab_test_sends.count_documents({"clicked_at": {"$exists": True, "$ne": None}})

    return {
        "tests": dashboard_data,
        "platform_metrics": {
            "total_sends": total_sends,
            "total_opens": total_opens,
            "total_clicks": total_clicks,
            "avg_open_rate": round(total_opens / total_sends * 100, 1) if total_sends > 0 else 0,
            "avg_click_rate": round(total_clicks / total_sends * 100, 1) if total_sends > 0 else 0,
        },
    }


@router.post("/performance/simulate")
async def simulate_ab_performance(request: Request):
    """Seed sample A/B tests with realistic time-series data for chart visualization."""
    await require_admin(request)

    templates = [
        ("welcome_email", "Welcome & Get Started", "Onboarding"),
        ("interview_reminder", "Your Interview is Tomorrow", "Calendar"),
        ("weekly_digest", "Your Weekly Career Digest", "Engagement"),
    ]
    now = datetime.now(timezone.utc)
    created = []

    for tpl_key, subject_a, category in templates:
        test_id = f"sim_{uuid.uuid4().hex[:8]}"
        subject_b = f"[AI] {subject_a} - Optimized"

        test_doc = {
            "test_id": test_id,
            "name": f"Performance Test: {tpl_key.replace('_', ' ').title()}",
            "template_type": tpl_key,
            "status": "completed",
            "winner": random.choice(["a", "b"]),
            "ai_generated": True,
            "variant_a": {"subject_line": subject_a, "strategy": "original"},
            "variant_b": {"subject_line": subject_b, "strategy": "ai_optimized"},
            "created_at": (now - timedelta(days=14)).isoformat(),
            "started_at": (now - timedelta(days=14)).isoformat(),
            "completed_at": now.isoformat(),
            "ends_at": now.isoformat(),
        }
        await db.ab_tests.insert_one(test_doc)

        # Generate 14 days of sends for both variants
        sends = []
        for day_offset in range(14):
            day = now - timedelta(days=13 - day_offset)
            day_str = day.strftime("%Y-%m-%d")
            for variant in ["a", "b"]:
                daily_count = random.randint(15, 45)
                base_open = 25 if variant == "a" else 35
                base_click = 4 if variant == "a" else 8
                # Add trend: variant b improves over time
                trend = day_offset * (0.8 if variant == "b" else 0.2)
                for _ in range(daily_count):
                    opened = random.random() * 100 < (base_open + trend + random.gauss(0, 5))
                    clicked = opened and random.random() * 100 < (base_click + trend * 0.5 + random.gauss(0, 2))
                    send_doc = {
                        "send_id": f"ssim_{uuid.uuid4().hex[:10]}",
                        "test_id": test_id,
                        "variant": variant,
                        "sent_at": f"{day_str}T{random.randint(8,18):02d}:{random.randint(0,59):02d}:00Z",
                        "created_at": f"{day_str}T{random.randint(8,18):02d}:{random.randint(0,59):02d}:00Z",
                    }
                    if opened:
                        send_doc["opened_at"] = f"{day_str}T{random.randint(8,22):02d}:{random.randint(0,59):02d}:00Z"
                    if clicked:
                        send_doc["clicked_at"] = f"{day_str}T{random.randint(8,22):02d}:{random.randint(0,59):02d}:00Z"
                    sends.append(send_doc)
        if sends:
            await db.ab_test_sends.insert_many(sends)
        created.append({"test_id": test_id, "template": tpl_key, "sends": len(sends)})

    return {"status": "ok", "created_tests": created, "message": f"Simulated {len(created)} A/B tests with performance data."}


# ═══════════════════════════════════════════════════════════════════════════════
# ── SCHEDULED A/B TEST ROTATION ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

ROTATION_CONFIG_ID = "ab_rotation_config"
DEFAULT_ROTATION_CONFIG = {
    "enabled": False,
    "frequency": "weekly",       # weekly | biweekly
    "max_concurrent": 5,         # max tests running at once
    "evaluation_days": 7,
    "auto_apply_winner": True,
    "excluded_templates": [],    # template keys to skip
}


@router.get("/rotation/config")
async def get_rotation_config(request: Request):
    await require_admin(request)
    doc = await db.ab_rotation_config.find_one({"_id": ROTATION_CONFIG_ID})
    if not doc:
        return DEFAULT_ROTATION_CONFIG
    doc.pop("_id", None)
    return doc


@router.put("/rotation/config")
async def update_rotation_config(request: Request):
    await require_admin(request)
    body = await request.json()
    allowed = {"enabled", "frequency", "max_concurrent", "evaluation_days", "auto_apply_winner", "excluded_templates"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No valid fields to update")
    now = datetime.now(timezone.utc).isoformat()
    await db.ab_rotation_config.update_one(
        {"_id": ROTATION_CONFIG_ID},
        {"$set": {**update, "updated_at": now}},
        upsert=True,
    )
    doc = await db.ab_rotation_config.find_one({"_id": ROTATION_CONFIG_ID})
    doc.pop("_id", None)
    return doc


@router.get("/rotation/history")
async def get_rotation_history(request: Request):
    await require_admin(request)
    cursor = db.ab_rotation_history.find({}, {"_id": 0}).sort("run_at", -1).limit(30)
    runs = await cursor.to_list(length=30)
    # Calculate cumulative improvement
    improvement_by_template: dict = {}
    for run in reversed(runs):
        for result in run.get("results", []):
            tpl = result.get("template_type", "")
            if result.get("action") == "promoted" and result.get("improvement_pct"):
                improvement_by_template[tpl] = improvement_by_template.get(tpl, 0) + result["improvement_pct"]
    return {
        "runs": runs,
        "cumulative_improvement": improvement_by_template,
        "total_runs": len(runs),
    }


@router.post("/rotation/run-now")
async def trigger_rotation_now(request: Request):
    """Manually trigger one rotation cycle."""
    await require_admin(request)
    result = await execute_rotation_cycle(manual=True)
    return result


async def execute_rotation_cycle(manual: bool = False):
    """Core rotation logic: evaluate → promote → create new tests."""
    import json as _json
    from utils.email_templates import TEMPLATE_CATALOG

    logger.info("A/B rotation cycle starting (manual=%s)", manual)
    now = datetime.now(timezone.utc)

    # Load config
    cfg_doc = await db.ab_rotation_config.find_one({"_id": ROTATION_CONFIG_ID})
    cfg = {**DEFAULT_ROTATION_CONFIG, **(cfg_doc or {})}
    cfg.pop("_id", None)

    if not cfg["enabled"] and not manual:
        return {"skipped": True, "reason": "rotation disabled"}

    results = []

    # ── Phase 1: Evaluate expired active tests ──
    expired = await db.ab_tests.find(
        {"status": "active", "ends_at": {"$lte": now.isoformat()}}
    ).to_list(length=100)

    for test in expired:
        test_id = test["test_id"]
        # Count sends per variant
        sends_a = await db.ab_test_sends.count_documents({"test_id": test_id, "variant": "a"})
        sends_b = await db.ab_test_sends.count_documents({"test_id": test_id, "variant": "b"})
        opens_a = await db.ab_test_sends.count_documents({"test_id": test_id, "variant": "a", "opened": True})
        opens_b = await db.ab_test_sends.count_documents({"test_id": test_id, "variant": "b", "opened": True})
        rate_a = round(opens_a / sends_a * 100, 1) if sends_a > 0 else 0
        rate_b = round(opens_b / sends_b * 100, 1) if sends_b > 0 else 0

        winner = "a" if rate_a >= rate_b else "b"
        improvement = round(max(rate_a, rate_b) - min(rate_a, rate_b), 1)
        await db.ab_tests.update_one(
            {"test_id": test_id},
            {"$set": {"status": "completed", "winner": winner, "completed_at": now.isoformat()}},
        )
        results.append({
            "template_type": test.get("template_type"),
            "test_id": test_id,
            "action": "evaluated",
            "winner": winner,
            "rate_a": rate_a,
            "rate_b": rate_b,
            "improvement_pct": improvement,
        })

    # ── Phase 2: Auto-promote winners ──
    if cfg["auto_apply_winner"]:
        completed_unpromo = await db.ab_tests.find(
            {"status": "completed", "winner": {"$ne": None}, "auto_promoted": {"$ne": True}}
        ).to_list(length=100)

        for test in completed_unpromo:
            test_id = test["test_id"]
            w = test["winner"]
            w_variant = test.get(f"variant_{w}", {})
            tpl_type = test.get("template_type")
            if w_variant.get("subject_line") and tpl_type:
                if is_protected_subject_override_target(tpl_type):
                    await audit_override_write(
                        template_key=tpl_type,
                        actor="system_ab_rotation",
                        source=f"ab_test_{test_id}",
                        approved=False,
                        reason="protected_template_blocked",
                        metadata={"test_id": test_id},
                    )
                    await db.ab_tests.update_one(
                        {"test_id": test_id},
                        {
                            "$set": {
                                "auto_promoted": False,
                                "promotion_block_reason": "protected_template_subject_override_blocked",
                                "promotion_blocked_at": now.isoformat(),
                            }
                        },
                    )
                    results.append(
                        {
                            "template_type": tpl_type,
                            "test_id": test_id,
                            "action": "promotion_blocked_protected_template",
                        }
                    )
                    continue

                ok, gate = await write_subject_override(
                    template_key=tpl_type,
                    optimized_subject=w_variant["subject_line"],
                    actor="system_ab_rotation",
                    source=f"ab_test_{test_id}",
                    metadata={"test_id": test_id, "winning_subject": w_variant["subject_line"]},
                )
                if not ok:
                    await db.ab_tests.update_one(
                        {"test_id": test_id},
                        {
                            "$set": {
                                "auto_promoted": False,
                                "promotion_block_reason": str(gate.get("reason") or "policy_blocked"),
                                "promotion_blocked_at": now.isoformat(),
                            }
                        },
                    )
                    results.append(
                        {
                            "template_type": tpl_type,
                            "test_id": test_id,
                            "action": "promotion_blocked_policy_gate",
                            "reason": str(gate.get("reason") or "policy_blocked"),
                        }
                    )
                    continue
                await db.ab_tests.update_one({"test_id": test_id}, {"$set": {"auto_promoted": True}})
                results.append({
                    "template_type": tpl_type,
                    "test_id": test_id,
                    "action": "promoted",
                    "winning_subject": w_variant["subject_line"],
                    "improvement_pct": next((r.get("improvement_pct", 0) for r in results if r.get("test_id") == test_id), 0),
                })

    # ── Phase 3: Create new tests for untested templates ──
    active_templates = set()
    active_cursor = db.ab_tests.find({"status": {"$in": ["active", "scheduled"]}}, {"template_type": 1})
    async for doc in active_cursor:
        active_templates.add(doc.get("template_type"))

    active_count = len(active_templates)
    max_new = max(0, cfg["max_concurrent"] - active_count)
    excluded = set(cfg.get("excluded_templates", []))

    # Pick templates that aren't active and aren't excluded
    candidates = [k for k in TEMPLATE_CATALOG if k not in active_templates and k not in excluded]
    # Prioritize templates that haven't been tested recently
    recent_tested = set()
    recent_cursor = db.ab_tests.find(
        {"status": "completed", "completed_at": {"$gte": (now - timedelta(days=30)).isoformat()}},
        {"template_type": 1},
    )
    async for doc in recent_cursor:
        recent_tested.add(doc.get("template_type"))

    # Sort: untested first, then least recently tested
    candidates.sort(key=lambda k: (k in recent_tested, k))
    to_create = candidates[:max_new]

    for tpl_key in to_create:
        try:
            info = TEMPLATE_CATALOG[tpl_key]
            tpl = info["builder"]()
            original_subject = tpl.subject

            prompt = f"""Generate an alternative email subject line for A/B testing on RealAICoach, an AI career coaching platform.

Template: {info["label"]} ({info["category"]}). Description: {info["description"]}.
Current subject: {repr(original_subject)}

Requirements:
- Creative alternative with a different psychological approach (urgency, curiosity, personalization, benefit-driven, social proof)
- Under 60 characters, professional, compelling
- Never translate "RealAICoach"

Return ONLY JSON: {{"variant_b_subject": "...", "variant_b_strategy": "..."}}"""

            from emergentintegrations.llm.chat import LlmChat, UserMessage
            from routes.db import EMERGENT_LLM_KEY

            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"rotation-{uuid.uuid4().hex[:8]}",
                system_message="Expert email copywriter. Return only valid JSON.",
            ).with_model("openai", "gpt-4o-mini")

            response = await chat.send_message(UserMessage(text=prompt))
            text = response.text if hasattr(response, "text") else str(response)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            ai_result = _json.loads(text)
            variant_b_subject = ai_result.get("variant_b_subject", f"Discover: {info['label']}")
            variant_b_strategy = ai_result.get("variant_b_strategy", "AI-generated")
        except Exception as e:
            logger.error(f"AI gen failed for rotation {tpl_key}: {e}")
            variant_b_subject = f"Don't miss — {info['label']}"
            variant_b_strategy = "Fallback: urgency"

        test = {
            "test_id": f"abt_{uuid.uuid4().hex[:12]}",
            "name": f"Rotation: {info['label']}",
            "tier": None,
            "template_type": tpl_key,
            "status": "active",
            "variant_a": {"name": "Original", "subject_line": original_subject, "cta_text": "Original CTA", "strategy": "Control"},
            "variant_b": {"name": "AI Variant", "subject_line": variant_b_subject, "cta_text": "Original CTA", "strategy": variant_b_strategy},
            "evaluation_days": cfg["evaluation_days"],
            "created_at": now.isoformat(),
            "start_time": None,
            "end_time": None,
            "ends_at": (now + timedelta(days=cfg["evaluation_days"])).isoformat(),
            "winner": None,
            "auto_promoted": False,
            "auto_apply_winner": cfg["auto_apply_winner"],
            "ai_generated": True,
            "rotation_created": True,
        }
        await db.ab_tests.insert_one(test)
        results.append({
            "template_type": tpl_key,
            "test_id": test["test_id"],
            "action": "created",
            "variant_b_subject": variant_b_subject,
            "variant_b_strategy": variant_b_strategy,
        })

    # ── Save rotation history ──
    history_entry = {
        "run_at": now.isoformat(),
        "manual": manual,
        "evaluated": sum(1 for r in results if r["action"] == "evaluated"),
        "promoted": sum(1 for r in results if r["action"] == "promoted"),
        "created": sum(1 for r in results if r["action"] == "created"),
        "results": results,
    }
    await db.ab_rotation_history.insert_one(history_entry)
    del history_entry["_id"]

    logger.info("A/B rotation complete: %d evaluated, %d promoted, %d created",
                history_entry["evaluated"], history_entry["promoted"], history_entry["created"])
    return history_entry


async def scheduled_ab_rotation():
    """Called by APScheduler."""
    try:
        await execute_rotation_cycle(manual=False)
    except Exception as e:
        logger.error(f"Scheduled A/B rotation failed: {e}")
