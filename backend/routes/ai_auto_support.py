"""AI Auto-Support Bot — Auto-resolve tickets using AI before human escalation.

Matches tickets to FAQ knowledge base, generates AI responses, and auto-resolves
common issues. Escalates complex or unresolved tickets to human agents.

API:
- POST /api/ai-support/auto-respond       — Auto-respond to a ticket
- POST /api/admin/ai-support/bulk-resolve  — Bulk auto-resolve all open tickets
- GET  /api/admin/ai-support/dashboard     — Admin dashboard with resolution stats + AI summary
- POST /api/admin/ai-support/configure     — Configure auto-support settings
- GET  /api/admin/ai-support/log           — AI resolution log
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json, ai_generate

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_CONFIG = {
    "enabled": True,
    "auto_resolve_confidence": 0.8,
    "max_auto_responses_per_ticket": 2,
    "escalation_keywords": ["human", "agent", "manager", "refund", "urgent"],
    "categories": ["general", "billing", "technical", "account", "feature_request"],
}


async def _get_config():
    config = await db.ai_support_config.find_one({"config_id": "main"}, {"_id": 0})
    return config or DEFAULT_CONFIG


async def _search_faq(query: str, limit: int = 5) -> list:
    """Search FAQ knowledge base for relevant answers."""
    try:
        faqs = (
            await db.faqs.find(
                {"$text": {"$search": query}},
                {"_id": 0, "question": 1, "answer": 1, "category": 1, "score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
            .to_list(limit)
        )
    except Exception:
        faqs = []

    if not faqs:
        try:
            words = query.split()[:5]
            pattern = "|".join(words)
            faqs = (
                await db.faqs.find(
                    {
                        "$or": [
                            {"question": {"$regex": pattern, "$options": "i"}},
                            {"answer": {"$regex": pattern, "$options": "i"}},
                        ]
                    },
                    {"_id": 0, "question": 1, "answer": 1, "category": 1},
                )
                .limit(limit)
                .to_list(limit)
            )
        except Exception:
            faqs = []
    return faqs


async def _auto_respond_internal(ticket_id: str, user_id: str):
    """Internal auto-respond (called from ticket creation, no auth needed)."""
    try:
        config = await _get_config()
        if not config.get("enabled", True):
            return

        ticket = await db.support_submissions.find_one(
            {"$or": [{"ticket_id": ticket_id}, {"submission_id": ticket_id}]}, {"_id": 0}
        )
        if not ticket:
            return

        subject = ticket.get("subject", "")
        description = ticket.get("description", ticket.get("message", ""))
        full_text = f"{subject} {description}".lower()

        for kw in config.get("escalation_keywords", []):
            if kw in full_text:
                return

        faqs = await _search_faq(f"{subject} {description}")
        faq_context = "\n".join([f"Q: {f['question']}\nA: {f['answer']}" for f in faqs[:3]])

        system_msg = """You are a Support AI Assistant. Based on the knowledge base and ticket, provide a helpful response.
Return ONLY valid JSON:
{
  "response": "Your helpful response to the user",
  "confidence": 0.85,
  "category": "general|billing|technical|account|feature_request",
  "suggested_resolution": true
}"""
        prompt = f"Ticket: {subject}\nDetails: {description}\nKB:\n{faq_context or 'No FAQ matches.'}\nGenerate a helpful response:"

        result = await ai_generate_json(system_msg, prompt, f"auto-{ticket_id[:8]}")
        confidence = result.get("confidence", 0)
        threshold = config.get("auto_resolve_confidence", 0.8)

        now = datetime.now(timezone.utc).isoformat()
        log_entry = {
            "log_id": f"ailog_{uuid.uuid4().hex[:12]}",
            "ticket_id": ticket_id,
            "user_id": user_id,
            "response": result.get("response", ""),
            "confidence": confidence,
            "category": result.get("category", "general"),
            "auto_resolved": confidence >= threshold,
            "trigger": "auto",
            "faq_matches": len(faqs),
            "created_at": now,
        }
        await db.ai_support_log.insert_one(log_entry)

        if confidence >= threshold:
            tid = ticket.get("ticket_id") or ticket.get("submission_id")
            await db.support_submissions.update_one(
                {"$or": [{"ticket_id": tid}, {"submission_id": tid}]},
                {
                    "$push": {
                        "reply_logs": {
                            "reply_id": f"reply_{uuid.uuid4().hex[:8]}",
                            "sender": "AI Support Bot",
                            "sender_role": "ai_bot",
                            "content": result["response"],
                            "created_at": now,
                        }
                    },
                    "$set": {"status": "ai_responded", "updated_at": now},
                },
            )
            logger.info(f"AI auto-resolved ticket {ticket_id} (confidence={confidence:.0%})")
    except Exception as e:
        logger.error(f"Internal auto-respond error for {ticket_id}: {e}")


class AutoRespond(BaseModel):
    ticket_id: str


class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_resolve_confidence: Optional[float] = None
    max_auto_responses_per_ticket: Optional[int] = None


@router.post("/ai-support/auto-respond")
async def auto_respond_ticket(request: Request, body: AutoRespond):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    config = await _get_config()
    if not config.get("enabled", True):
        return {"auto_responded": False, "reason": "AI support is disabled"}

    ticket = await db.support_submissions.find_one(
        {"$or": [{"ticket_id": body.ticket_id}, {"submission_id": body.ticket_id}]}, {"_id": 0}
    )
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    auto_count = await db.ai_support_log.count_documents({"ticket_id": body.ticket_id})
    if auto_count >= config.get("max_auto_responses_per_ticket", 2):
        return {"auto_responded": False, "reason": "Max auto-responses reached, escalating to human"}

    subject = ticket.get("subject", "").lower()
    description = ticket.get("description", ticket.get("message", "")).lower()
    full_text = f"{subject} {description}"
    for kw in config.get("escalation_keywords", []):
        if kw in full_text:
            return {"auto_responded": False, "reason": f"Escalation keyword detected: '{kw}'", "escalated": True}

    faqs = await _search_faq(f"{ticket.get('subject', '')} {ticket.get('description', ticket.get('message', ''))}")
    faq_context = "\n".join([f"Q: {f['question']}\nA: {f['answer']}" for f in faqs[:3]])

    system_msg = """You are a Support AI Assistant. Based on the knowledge base and ticket, provide a helpful response.
Return ONLY valid JSON:
{
  "response": "Your helpful response to the user",
  "confidence": 0.85,
  "category": "general|billing|technical|account|feature_request",
  "suggested_resolution": true,
  "follow_up_question": "Optional follow-up question if needed"
}"""
    prompt = f"""Ticket Subject: {ticket.get("subject", "")}
Ticket Description: {ticket.get("description", ticket.get("message", ""))}

Knowledge Base Matches:
{faq_context if faq_context else "No direct FAQ matches found."}

Generate a helpful, accurate response:"""

    try:
        result = await ai_generate_json(system_msg, prompt, f"support-{body.ticket_id[:8]}")
    except Exception as e:
        logger.error(f"Auto-support error: {e}")
        return {"auto_responded": False, "reason": "AI generation failed", "error": str(e)}

    confidence = result.get("confidence", 0)
    threshold = config.get("auto_resolve_confidence", 0.8)

    now = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "log_id": f"ailog_{uuid.uuid4().hex[:12]}",
        "ticket_id": body.ticket_id,
        "user_id": user.user_id,
        "response": result.get("response", ""),
        "confidence": confidence,
        "category": result.get("category", "general"),
        "auto_resolved": confidence >= threshold,
        "trigger": "manual",
        "faq_matches": len(faqs),
        "created_at": now,
    }
    await db.ai_support_log.insert_one(log_entry)
    log_entry.pop("_id", None)

    if confidence >= threshold:
        await db.support_submissions.update_one(
            {"$or": [{"ticket_id": body.ticket_id}, {"submission_id": body.ticket_id}]},
            {
                "$push": {
                    "reply_logs": {
                        "reply_id": f"reply_{uuid.uuid4().hex[:8]}",
                        "sender": "AI Support Bot",
                        "sender_role": "ai_bot",
                        "content": result["response"],
                        "created_at": now,
                    }
                },
                "$set": {"status": "ai_responded", "updated_at": now},
            },
        )
        return {
            "auto_responded": True,
            "response": result["response"],
            "confidence": confidence,
            "category": result.get("category"),
        }
    else:
        return {
            "auto_responded": False,
            "reason": f"Low confidence ({confidence:.0%})",
            "suggested_response": result.get("response"),
            "confidence": confidence,
        }


@router.post("/admin/ai-support/bulk-resolve")
async def bulk_auto_resolve(request: Request):
    """Scan all open tickets and attempt AI auto-resolution."""
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    config = await _get_config()
    if not config.get("enabled", True):
        return {"success": False, "reason": "AI support is disabled"}

    open_tickets = (
        await db.support_submissions.find(
            {"status": {"$in": ["open", "pending", "new"]}},
            {"_id": 0, "submission_id": 1, "ticket_id": 1, "user_id": 1},
        )
        .limit(20)
        .to_list(20)
    )

    results = {"attempted": 0, "resolved": 0, "escalated": 0, "failed": 0}
    for t in open_tickets:
        tid = t.get("submission_id") or t.get("ticket_id")
        uid = t.get("user_id", "system")
        results["attempted"] += 1
        try:
            await _auto_respond_internal(tid, uid)
            log = await db.ai_support_log.find_one({"ticket_id": tid}, {"_id": 0}, sort=[("created_at", -1)])
            if log and log.get("auto_resolved"):
                results["resolved"] += 1
            else:
                results["escalated"] += 1
        except Exception:
            results["failed"] += 1

    return {"success": True, **results}


@router.get("/admin/ai-support/dashboard")
async def support_dashboard(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()

    total_auto = await db.ai_support_log.count_documents({})
    resolved = await db.ai_support_log.count_documents({"auto_resolved": True})
    recent_auto = await db.ai_support_log.count_documents({"created_at": {"$gte": seven_days}})
    recent_resolved = await db.ai_support_log.count_documents(
        {"auto_resolved": True, "created_at": {"$gte": seven_days}}
    )

    # Category breakdown
    pipeline = [
        {
            "$group": {
                "_id": "$category",
                "total": {"$sum": 1},
                "resolved": {"$sum": {"$cond": ["$auto_resolved", 1, 0]}},
            }
        },
    ]
    cat_stats = await db.ai_support_log.aggregate(pipeline).to_list(20)

    # Average confidence
    conf_pipeline = [{"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence"}}}]
    conf_result = await db.ai_support_log.aggregate(conf_pipeline).to_list(1)
    avg_conf = conf_result[0]["avg_confidence"] if conf_result else 0

    # Daily trend (7 days)
    daily_trend = []
    for i in range(6, -1, -1):
        d = now - timedelta(days=i)
        ds = d.replace(hour=0, minute=0, second=0).isoformat()
        de = (d + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
        cnt = await db.ai_support_log.count_documents({"created_at": {"$gte": ds, "$lt": de}})
        res = await db.ai_support_log.count_documents({"auto_resolved": True, "created_at": {"$gte": ds, "$lt": de}})
        daily_trend.append({"date": d.strftime("%m/%d"), "total": cnt, "resolved": res})

    # Confidence distribution
    conf_dist = {"high": 0, "medium": 0, "low": 0}
    async for log in db.ai_support_log.find({"confidence": {"$exists": True}}, {"confidence": 1, "_id": 0}):
        c = log.get("confidence", 0)
        if c >= 0.8:
            conf_dist["high"] += 1
        elif c >= 0.5:
            conf_dist["medium"] += 1
        else:
            conf_dist["low"] += 1

    # Open tickets count
    open_tickets = await db.support_submissions.count_documents({"status": {"$in": ["open", "pending", "new"]}})

    # AI-generated resolution summary
    ai_summary = ""
    if total_auto > 0:
        try:
            ai_summary = await ai_generate(
                "You are a support analytics AI. Summarize the auto-support performance in 3-4 bullet points. Be specific with numbers.",
                f"Total interactions: {total_auto}, Auto-resolved: {resolved} ({round(resolved / max(total_auto, 1) * 100, 1)}%), "
                f"Avg confidence: {round((avg_conf or 0) * 100, 1)}%, Open tickets: {open_tickets}, "
                f"Recent 7d: {recent_auto} interactions, {recent_resolved} resolved. "
                f"Categories: {[{'cat': s['_id'], 'total': s['total'], 'resolved': s['resolved']} for s in cat_stats]}. "
                f"Provide actionable insights:",
                "support-summary",
            )
        except Exception:
            ai_summary = ""

    config = await _get_config()

    return {
        "overview": {
            "total_interactions": total_auto,
            "auto_resolved": resolved,
            "resolution_rate": round(resolved / max(total_auto, 1) * 100, 1),
            "avg_confidence": round((avg_conf or 0) * 100, 1),
            "recent_7d": recent_auto,
            "recent_resolved_7d": recent_resolved,
            "open_tickets": open_tickets,
        },
        "category_breakdown": [
            {"category": s["_id"] or "unknown", "total": s["total"], "resolved": s["resolved"]} for s in cat_stats
        ],
        "daily_trend": daily_trend,
        "confidence_distribution": conf_dist,
        "ai_summary": ai_summary,
        "config": {k: v for k, v in config.items() if k != "config_id"},
        "timestamp": now.isoformat(),
    }


@router.post("/admin/ai-support/configure")
async def configure_support(request: Request, body: ConfigUpdate):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")
    update = {k: v for k, v in body.dict().items() if v is not None}
    if update:
        await db.ai_support_config.update_one(
            {"config_id": "main"},
            {"$set": update},
            upsert=True,
        )
    config = await _get_config()
    return {"success": True, "config": config}


@router.get("/admin/ai-support/log")
async def support_log(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")
    logs = await db.ai_support_log.find({}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"logs": logs}
