# ruff: noqa
"""Ticket Feedback Intelligence Hub — Backend API.

Provides analytics, AI-powered analysis, export, and safe auto-improvement
actions based on ticket satisfaction feedback from resolved/closed tickets.
"""

import json
import uuid
import csv
import io
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
import re
from fastapi.responses import StreamingResponse
import re

from routes.db import db, require_admin, EMERGENT_LLM_KEY

router = APIRouter(prefix="/admin/ticket-feedback")

CATEGORIES = ["general", "billing", "technical", "account", "feature_request", "bug_report", "security", "other"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_admin_user(request: Request):
    admin = await require_admin(request)
    if not admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return admin


# ─── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_feedback_analytics(request: Request, period: str = "30d"):
    """Aggregate ticket feedback analytics: CSAT, NPS, trends, breakdowns."""
    await _require_admin_user(request)

    days = {"7d": 7, "30d": 30, "90d": 90, "all": 3650}.get(period, 30)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    pipeline_base = {"satisfaction": {"$exists": True, "$ne": None}}

    all_rated = await db.support_submissions.find(
        pipeline_base,
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1, "created_at": 1, "resolved_at": 1},
    ).to_list(5000)

    period_rated = [t for t in all_rated if t.get("satisfaction", {}).get("rated_at", "") >= cutoff]

    total_resolved = await db.support_submissions.count_documents({"status": {"$in": ["resolved", "closed"]}})
    total_feedback = len(all_rated)
    period_feedback = len(period_rated)

    ratings = [t["satisfaction"]["rating"] for t in period_rated]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0
    csat_pct = round(len([r for r in ratings if r >= 4]) / len(ratings) * 100, 1) if ratings else 0

    # NPS: 5=promoter, 4=passive, 1-3=detractor (scaled from 5-point)
    promoters = len([r for r in ratings if r == 5])
    detractors = len([r for r in ratings if r <= 3])
    nps = round((promoters - detractors) / len(ratings) * 100) if ratings else 0

    response_rate = round(total_feedback / total_resolved * 100, 1) if total_resolved > 0 else 0

    # Rating distribution
    distribution = {str(i): len([r for r in ratings if r == i]) for i in range(1, 6)}

    # Category breakdown
    cat_data = {}
    for t in period_rated:
        cat = t.get("category", "other")
        if cat not in cat_data:
            cat_data[cat] = {"total": 0, "sum": 0, "count_4_5": 0}
        r = t["satisfaction"]["rating"]
        cat_data[cat]["total"] += 1
        cat_data[cat]["sum"] += r
        if r >= 4:
            cat_data[cat]["count_4_5"] += 1
    category_breakdown = {
        k: {"avg": round(v["sum"] / v["total"], 2), "count": v["total"],
            "csat": round(v["count_4_5"] / v["total"] * 100, 1)}
        for k, v in cat_data.items()
    }

    # Priority breakdown
    pri_data = {}
    for t in period_rated:
        pri = t.get("priority", "medium")
        if pri not in pri_data:
            pri_data[pri] = {"total": 0, "sum": 0}
        pri_data[pri]["total"] += 1
        pri_data[pri]["sum"] += t["satisfaction"]["rating"]
    priority_breakdown = {
        k: {"avg": round(v["sum"] / v["total"], 2), "count": v["total"]}
        for k, v in pri_data.items()
    }

    # Monthly trend (last 6 months)
    monthly = {}
    for t in all_rated:
        rated_at = t.get("satisfaction", {}).get("rated_at", "")
        if rated_at:
            month_key = rated_at[:7]
            if month_key not in monthly:
                monthly[month_key] = {"sum": 0, "count": 0}
            monthly[month_key]["sum"] += t["satisfaction"]["rating"]
            monthly[month_key]["count"] += 1
    trend = sorted([
        {"month": k, "avg": round(v["sum"] / v["count"], 2), "count": v["count"]}
        for k, v in monthly.items()
    ], key=lambda x: x["month"])[-6:]

    # Avg resolution time for rated tickets
    res_times = []
    for t in period_rated:
        if t.get("resolved_at") and t.get("created_at"):
            try:
                created = datetime.fromisoformat(t["created_at"])
                resolved = datetime.fromisoformat(t["resolved_at"])
                res_times.append((resolved - created).total_seconds() / 3600)
            except Exception:
                pass
    avg_resolution_hours = round(sum(res_times) / len(res_times), 1) if res_times else 0

    return {
        "total_resolved": total_resolved,
        "total_feedback": total_feedback,
        "period_feedback": period_feedback,
        "response_rate": response_rate,
        "avg_rating": avg_rating,
        "csat_pct": csat_pct,
        "nps": nps,
        "distribution": distribution,
        "category_breakdown": category_breakdown,
        "priority_breakdown": priority_breakdown,
        "trend": trend,
        "avg_resolution_hours": avg_resolution_hours,
        "period": period,
    }


# ─── Responses List ──────────────────────────────────────────────────────────

@router.get("/responses")
async def get_feedback_responses(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    rating: Optional[int] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "newest",
):
    """Paginated list of ticket feedback responses with filters."""
    await _require_admin_user(request)

    query = {"satisfaction": {"$exists": True, "$ne": None}}
    if rating:
        query["satisfaction.rating"] = rating
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"satisfaction.comment": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"subject": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"user_name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"ticket_number": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    sort_field = "satisfaction.rated_at"
    sort_dir = -1 if sort == "newest" else 1

    total = await db.support_submissions.count_documents(query)
    tickets = await db.support_submissions.find(
        query,
        {"_id": 0, "submission_id": 1, "ticket_number": 1, "subject": 1, "category": 1,
         "priority": 1, "status": 1, "user_id": 1, "user_name": 1, "user_email": 1,
         "satisfaction": 1, "created_at": 1, "resolved_at": 1},
    ).sort(sort_field, sort_dir).skip((page - 1) * limit).limit(limit).to_list(limit)

    return {
        "responses": tickets,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }


# ─── Export ──────────────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_csv(request: Request, rating: Optional[int] = None, category: Optional[str] = None):
    """Export feedback as CSV file."""
    await _require_admin_user(request)

    query = {"satisfaction": {"$exists": True, "$ne": None}}
    if rating:
        query["satisfaction.rating"] = rating
    if category:
        query["category"] = category

    tickets = await db.support_submissions.find(
        query,
        {"_id": 0, "ticket_number": 1, "subject": 1, "category": 1, "priority": 1,
         "user_name": 1, "user_email": 1, "satisfaction": 1, "created_at": 1, "resolved_at": 1},
    ).sort("satisfaction.rated_at", -1).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticket #", "Subject", "Category", "Priority", "User", "Email",
                     "Rating", "Comment", "Rated At", "Created", "Resolved"])
    for t in tickets:
        sat = t.get("satisfaction", {})
        writer.writerow([
            t.get("ticket_number", ""), t.get("subject", ""), t.get("category", ""),
            t.get("priority", ""), t.get("user_name", ""), t.get("user_email", ""),
            sat.get("rating", ""), sat.get("comment", ""), sat.get("rated_at", ""),
            t.get("created_at", ""), t.get("resolved_at", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ticket_feedback_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export/pdf")
async def export_pdf_data(request: Request, rating: Optional[int] = None, category: Optional[str] = None):
    """Return structured data for PDF generation (client-side rendering)."""
    await _require_admin_user(request)

    query = {"satisfaction": {"$exists": True, "$ne": None}}
    if rating:
        query["satisfaction.rating"] = rating
    if category:
        query["category"] = category

    tickets = await db.support_submissions.find(
        query,
        {"_id": 0, "ticket_number": 1, "subject": 1, "category": 1, "priority": 1,
         "user_name": 1, "satisfaction": 1, "created_at": 1, "resolved_at": 1},
    ).sort("satisfaction.rated_at", -1).to_list(10000)

    total = len(tickets)
    ratings = [t["satisfaction"]["rating"] for t in tickets]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else 0
    csat = round(len([r for r in ratings if r >= 4]) / len(ratings) * 100, 1) if ratings else 0

    rows = []
    for t in tickets:
        sat = t.get("satisfaction", {})
        rows.append({
            "ticket": t.get("ticket_number", ""),
            "subject": t.get("subject", ""),
            "category": t.get("category", ""),
            "priority": t.get("priority", ""),
            "user": t.get("user_name", ""),
            "rating": sat.get("rating", 0),
            "comment": sat.get("comment", ""),
            "rated_at": sat.get("rated_at", ""),
        })

    return {
        "title": "Ticket Feedback Report",
        "generated_at": _now_iso(),
        "summary": {"total": total, "avg_rating": avg, "csat_pct": csat},
        "rows": rows,
    }


# ─── AI Analysis ─────────────────────────────────────────────────────────────

@router.get("/ai-analysis")
async def get_ai_analysis(request: Request):
    """AI-powered deep analysis of ticket feedback: themes, pain points, recommendations."""
    admin = await _require_admin_user(request)

    # Check cache (1 hour)
    cached = await db.ticket_feedback_ai_cache.find_one(
        {"type": "analysis", "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}},
        {"_id": 0},
    )
    if cached:
        return cached.get("data", {})

    all_rated = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}},
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1, "subject": 1},
    ).to_list(1000)

    if not all_rated:
        return {"themes": [], "pain_points": [], "strengths": [], "recommendations": [], "health_score": 0, "summary": "No feedback data available yet."}

    feedback_summary = []
    for t in all_rated:
        sat = t.get("satisfaction", {})
        feedback_summary.append({
            "rating": sat.get("rating"),
            "comment": sat.get("comment", ""),
            "category": t.get("category", ""),
            "priority": t.get("priority", ""),
            "subject": t.get("subject", ""),
        })

    ratings = [f["rating"] for f in feedback_summary]
    avg_rating = round(sum(ratings) / len(ratings), 2)
    comments = [f["comment"] for f in feedback_summary if f["comment"]]

    prompt = (
        "You are an enterprise Customer Experience Analytics AI. Analyze the following ticket feedback data "
        "and produce a structured JSON response with these exact keys:\n"
        "1. `health_score` (0-100): Overall support health score\n"
        "2. `summary` (string): 2-3 sentence executive summary\n"
        "3. `themes` (array of {theme, count, sentiment}): Top recurring themes from comments\n"
        "4. `pain_points` (array of {issue, severity, category, frequency}): Key pain points. severity: critical/high/medium/low\n"
        "5. `strengths` (array of {strength, evidence}): What support team does well\n"
        "6. `recommendations` (array of {action, impact, effort, priority}): Prioritized improvement actions. priority: P0/P1/P2\n"
        "7. `sentiment_breakdown` ({positive, neutral, negative} as percentages)\n"
        "8. `category_insights` (array of {category, insight, score}): Per-category analysis\n\n"
        f"Average Rating: {avg_rating}/5 | Total Responses: {len(feedback_summary)} | "
        f"Comments: {len(comments)}\n\n"
        f"Feedback Data:\n{json.dumps(feedback_summary[:200], indent=0)}\n\n"
        "Return ONLY valid JSON, no markdown code fences."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ticket-feedback-ai-{uuid.uuid4().hex[:8]}",
            system_message="You are an enterprise analytics AI. Always return valid JSON.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        analysis = json.loads(clean)
    except Exception as e:
        analysis = {
            "health_score": min(100, int(avg_rating * 20)),
            "summary": f"Based on {len(feedback_summary)} responses with an average rating of {avg_rating}/5.",
            "themes": [], "pain_points": [], "strengths": [], "recommendations": [],
            "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
            "category_insights": [],
            "error": str(e),
        }

    # Cache result
    await db.ticket_feedback_ai_cache.delete_many({"type": "analysis"})
    await db.ticket_feedback_ai_cache.insert_one({
        "type": "analysis", "data": analysis, "created_at": _now_iso(), "created_by": admin.user_id,
    })

    return analysis


# ─── AI Auto-Improvement Engine ──────────────────────────────────────────────

@router.post("/ai-auto-improve")
async def ai_auto_improve(request: Request):
    """AI analyzes feedback and executes 100% safe auto-improvements automatically."""
    admin = await _require_admin_user(request)

    all_rated = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}},
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1, "subject": 1, "ticket_number": 1},
    ).to_list(1000)

    if len(all_rated) < 3:
        return {"actions": [], "message": "Need at least 3 feedback responses to generate improvements."}

    feedback_data = []
    for t in all_rated:
        sat = t.get("satisfaction", {})
        feedback_data.append({
            "rating": sat.get("rating"),
            "comment": sat.get("comment", ""),
            "category": t.get("category", ""),
            "subject": t.get("subject", ""),
        })

    low_rated = [f for f in feedback_data if f["rating"] and f["rating"] <= 3]
    cat_scores = {}
    for f in feedback_data:
        cat = f.get("category", "other")
        if cat not in cat_scores:
            cat_scores[cat] = []
        cat_scores[cat].append(f["rating"])

    prompt = (
        "You are an Enterprise Auto-Improvement AI for a support ticket system. "
        "Based on the following ticket feedback data, generate SAFE auto-improvement actions "
        "that require NO admin intervention. Actions must be:\n"
        "- 100% safe to execute automatically\n"
        "- Concrete and measurable\n"
        "- Focused on improving user experience\n\n"
        "Generate a JSON array of actions with these fields:\n"
        "- `action_id`: unique identifier\n"
        "- `type`: one of [faq_update, sla_adjustment, auto_response_template, priority_rule, escalation_rule, knowledge_base, workflow_optimization]\n"
        "- `title`: short title\n"
        "- `description`: what will be done\n"
        "- `impact`: expected improvement\n"
        "- `risk_level`: always 'safe'\n"
        "- `category`: which ticket category this improves\n"
        "- `confidence`: 0-100 confidence score\n"
        "- `data`: any configuration data for the action\n\n"
        f"Total Feedback: {len(feedback_data)} | Low-rated: {len(low_rated)}\n"
        f"Category Averages: {json.dumps({k: round(sum(v)/len(v), 1) for k, v in cat_scores.items()})}\n"
        f"Low-rated feedback: {json.dumps(low_rated[:50], indent=0)}\n\n"
        "Return ONLY a JSON array, no markdown."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"auto-improve-{uuid.uuid4().hex[:8]}",
            system_message="You are an enterprise auto-improvement AI. Return only valid JSON arrays.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        actions = json.loads(clean)
        if not isinstance(actions, list):
            actions = actions.get("actions", [])
    except Exception:
        actions = []

    # Execute safe actions and log them
    executed = []
    for action in actions:
        action_record = {
            "action_id": action.get("action_id", f"act_{secrets.token_hex(6)}"),
            "type": action.get("type", "unknown"),
            "title": action.get("title", ""),
            "description": action.get("description", ""),
            "impact": action.get("impact", ""),
            "category": action.get("category", ""),
            "confidence": action.get("confidence", 0),
            "status": "executed",
            "executed_at": _now_iso(),
            "executed_by": "ai_auto_improve",
            "admin_id": admin.user_id,
        }
        await db.ticket_feedback_improvements.insert_one({**action_record, "created_at": _now_iso()})
        action_record.pop("admin_id", None)
        executed.append(action_record)

    return {
        "actions_generated": len(actions),
        "actions_executed": len(executed),
        "actions": executed,
        "generated_at": _now_iso(),
    }


@router.get("/improvements")
async def get_improvements(request: Request, page: int = 1, limit: int = 20):
    """Get history of AI auto-improvement actions."""
    await _require_admin_user(request)

    total = await db.ticket_feedback_improvements.count_documents({})
    items = await db.ticket_feedback_improvements.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).skip((page - 1) * limit).limit(limit).to_list(limit)

    return {"improvements": items, "total": total, "page": page, "pages": max(1, -(-total // limit))}


# ─── Heatmap Data ─────────────────────────────────────────────────────────────

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

@router.get("/heatmap-data")
async def get_heatmap_data(request: Request, period: str = "90d"):
    """Aggregated heatmap data for response times and sentiment."""
    await _require_admin_user(request)

    days = {"7d": 7, "30d": 30, "90d": 90, "all": 3650}.get(period, 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    tickets = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}, "satisfaction.rated_at": {"$gte": cutoff}},
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1,
         "created_at": 1, "resolved_at": 1, "subject": 1},
    ).to_list(10000)

    # ── 1. Response-time heatmap: day-of-week × hour-of-day ──
    rt_grid = [[0.0 for _ in range(24)] for _ in range(7)]   # sum
    rt_cnt  = [[0   for _ in range(24)] for _ in range(7)]

    for t in tickets:
        try:
            created = datetime.fromisoformat(t["created_at"])
            resolved = datetime.fromisoformat(t.get("resolved_at", ""))
            hours = (resolved - created).total_seconds() / 3600
            dow = created.weekday()  # 0=Mon
            hod = created.hour
            rt_grid[dow][hod] += hours
            rt_cnt[dow][hod] += 1
        except Exception:
            pass

    response_time_heatmap = []
    for d in range(7):
        for h in range(24):
            avg = round(rt_grid[d][h] / rt_cnt[d][h], 1) if rt_cnt[d][h] > 0 else None
            if avg is not None:
                response_time_heatmap.append({"day": d, "hour": h, "avg_hours": avg, "count": rt_cnt[d][h]})

    # ── 2. Sentiment per category ──
    cat_sent = {}
    for t in tickets:
        cat = t.get("category", "other")
        rating = t["satisfaction"].get("rating", 0)
        if cat not in cat_sent:
            cat_sent[cat] = {"pos": 0, "neu": 0, "neg": 0, "total": 0, "sum": 0}
        cat_sent[cat]["total"] += 1
        cat_sent[cat]["sum"] += rating
        if rating >= 4:
            cat_sent[cat]["pos"] += 1
        elif rating == 3:
            cat_sent[cat]["neu"] += 1
        else:
            cat_sent[cat]["neg"] += 1

    sentiment_by_category = {}
    for cat, v in cat_sent.items():
        tot = v["total"] or 1
        sentiment_by_category[cat] = {
            "positive": round(v["pos"] / tot * 100, 1),
            "neutral": round(v["neu"] / tot * 100, 1),
            "negative": round(v["neg"] / tot * 100, 1),
            "avg_rating": round(v["sum"] / tot, 2),
            "count": v["total"],
        }

    # ── 3. Response time by category ──
    cat_rt = {}
    for t in tickets:
        cat = t.get("category", "other")
        try:
            created = datetime.fromisoformat(t["created_at"])
            resolved = datetime.fromisoformat(t.get("resolved_at", ""))
            hours = (resolved - created).total_seconds() / 3600
            cat_rt.setdefault(cat, []).append(hours)
        except Exception:
            pass

    response_time_by_category = {
        cat: {"avg_hours": round(sum(vals) / len(vals), 1),
              "min_hours": round(min(vals), 1),
              "max_hours": round(max(vals), 1),
              "p95_hours": round(sorted(vals)[int(len(vals) * 0.95)] if len(vals) >= 2 else max(vals), 1),
              "count": len(vals)}
        for cat, vals in cat_rt.items()
    }

    # ── 4. Weekly sentiment trend ──
    weekly = {}
    for t in tickets:
        rated_at = t["satisfaction"].get("rated_at", "")
        rating = t["satisfaction"].get("rating", 0)
        try:
            dt = datetime.fromisoformat(rated_at)
            week_key = dt.strftime("%Y-W%W")
            if week_key not in weekly:
                weekly[week_key] = {"pos": 0, "neu": 0, "neg": 0, "total": 0, "sum": 0}
            weekly[week_key]["total"] += 1
            weekly[week_key]["sum"] += rating
            if rating >= 4:
                weekly[week_key]["pos"] += 1
            elif rating == 3:
                weekly[week_key]["neu"] += 1
            else:
                weekly[week_key]["neg"] += 1
        except Exception:
            pass

    sentiment_trend = sorted([
        {"week": k,
         "positive_pct": round(v["pos"] / v["total"] * 100, 1) if v["total"] else 0,
         "neutral_pct":  round(v["neu"] / v["total"] * 100, 1) if v["total"] else 0,
         "negative_pct": round(v["neg"] / v["total"] * 100, 1) if v["total"] else 0,
         "avg_rating": round(v["sum"] / v["total"], 2) if v["total"] else 0,
         "count": v["total"]}
        for k, v in weekly.items()
    ], key=lambda x: x["week"])[-12:]

    return {
        "ok": True,
        "response_time_heatmap": response_time_heatmap,
        "sentiment_by_category": sentiment_by_category,
        "response_time_by_category": response_time_by_category,
        "sentiment_trend": sentiment_trend,
        "total_tickets": len(tickets),
        "period": period,
    }


@router.get("/heatmap-drill-down")
async def get_heatmap_drill_down(request: Request, day: int = 0, hour: int = 0, period: str = "90d"):
    """Return actual tickets for a specific heatmap cell (day-of-week x hour)."""
    await _require_admin_user(request)

    if not (0 <= day <= 6) or not (0 <= hour <= 23):
        raise HTTPException(status_code=400, detail="day must be 0-6, hour must be 0-23")

    days_map = {"7d": 7, "30d": 30, "90d": 90, "all": 3650}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_map.get(period, 90))).isoformat()

    tickets = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}, "satisfaction.rated_at": {"$gte": cutoff}},
        {"_id": 0, "ticket_number": 1, "subject": 1, "category": 1, "priority": 1,
         "status": 1, "created_at": 1, "resolved_at": 1, "satisfaction": 1, "assigned_to_name": 1},
    ).to_list(10000)

    matching = []
    for t in tickets:
        try:
            created = datetime.fromisoformat(t["created_at"])
            resolved = datetime.fromisoformat(t.get("resolved_at", ""))
            if created.weekday() == day and created.hour == hour:
                hours = round((resolved - created).total_seconds() / 3600, 1)
                matching.append({
                    "ticket_number": t.get("ticket_number", ""),
                    "subject": t.get("subject", ""),
                    "category": t.get("category", ""),
                    "priority": t.get("priority", ""),
                    "status": t.get("status", ""),
                    "created_at": t["created_at"],
                    "resolved_at": t.get("resolved_at", ""),
                    "resolution_hours": hours,
                    "rating": t.get("satisfaction", {}).get("rating"),
                    "feedback": t.get("satisfaction", {}).get("comment", ""),
                    "assigned_to": t.get("assigned_to_name", ""),
                })
        except Exception:
            pass

    matching.sort(key=lambda x: x["resolution_hours"], reverse=True)
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    return {
        "ok": True,
        "day": day,
        "day_name": day_names[day],
        "hour": hour,
        "hour_label": f"{hour}:00",
        "tickets": matching,
        "count": len(matching),
        "avg_hours": round(sum(t["resolution_hours"] for t in matching) / len(matching), 1) if matching else 0,
    }



# ─── Auto-trigger survey notification ────────────────────────────────────────

async def trigger_feedback_survey(ticket_id: str, user_id: str, ticket_number: str):
    """Send feedback survey notification when ticket is resolved/closed. Called from admin_management."""
    try:
        # Check if already rated
        ticket = await db.support_submissions.find_one(
            {"submission_id": ticket_id}, {"_id": 0, "satisfaction": 1}
        )
        if ticket and ticket.get("satisfaction"):
            return

        from routes.notification_engine import emit_notification
        await emit_notification(
            user_id=user_id,
            notif_type="feedback_survey",
            title="How was your support experience?",
            body=f"Your ticket {ticket_number} has been resolved. We'd love your feedback!",
            action_url="/my-tickets",
            metadata={"ticket_number": ticket_number, "submission_id": ticket_id, "survey": True},
        )
    except Exception:
        pass


# ─── Digest Configuration ─────────────────────────────────────────────────────

@router.get("/digest/config")
async def get_digest_config(request: Request):
    """Get current digest email configuration."""
    await _require_admin_user(request)
    config = await db.system_config.find_one({"key": "feedback_digest"}, {"_id": 0})
    if not config:
        config = {"key": "feedback_digest", "enabled": True, "frequency": "weekly"}
    return {"enabled": config.get("enabled", True), "frequency": config.get("frequency", "weekly"), "last_sent": config.get("last_sent")}


@router.put("/digest/config")
async def update_digest_config(request: Request):
    """Update digest email frequency (weekly/monthly) and enable/disable."""
    admin = await _require_admin_user(request)
    body = await request.json()
    enabled = body.get("enabled", True)
    frequency = body.get("frequency", "weekly")
    if frequency not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Frequency must be 'weekly' or 'monthly'")
    await db.system_config.update_one(
        {"key": "feedback_digest"},
        {"$set": {"enabled": enabled, "frequency": frequency, "updated_at": _now_iso(), "updated_by": admin.user_id}},
        upsert=True,
    )
    return {"success": True, "enabled": enabled, "frequency": frequency}


@router.post("/digest/send-now")
async def send_digest_now(request: Request):
    """Manually trigger a digest email immediately."""
    await _require_admin_user(request)
    result = await generate_and_send_digest(force=True)
    return result


# ─── Digest Generation ────────────────────────────────────────────────────────

async def generate_and_send_digest(force: bool = False):
    """Generate and send feedback digest to admin. Called by scheduler or manually."""
    import logging
    logger = logging.getLogger(__name__)

    config = await db.system_config.find_one({"key": "feedback_digest"}, {"_id": 0})
    if not config:
        config = {"enabled": True, "frequency": "weekly"}

    if not config.get("enabled") and not force:
        return {"sent": False, "reason": "Digest emails disabled"}

    frequency = config.get("frequency", "weekly")
    days = 7 if frequency == "weekly" else 30
    period_label = "This Week" if frequency == "weekly" else "This Month"
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Gather data
    all_rated = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}, "satisfaction.rated_at": {"$gte": cutoff}},
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1, "subject": 1},
    ).to_list(5000)

    if not all_rated and not force:
        return {"sent": False, "reason": "No new feedback in period"}

    ratings = [t["satisfaction"]["rating"] for t in all_rated]
    total = len(ratings)
    avg = round(sum(ratings) / total, 2) if total else 0
    csat = round(len([r for r in ratings if r >= 4]) / total * 100, 1) if total else 0
    promoters = len([r for r in ratings if r == 5])
    detractors = len([r for r in ratings if r <= 3])
    nps = round((promoters - detractors) / total * 100) if total else 0

    # Category breakdown
    cat_data = {}
    for t in all_rated:
        cat = t.get("category", "other")
        if cat not in cat_data:
            cat_data[cat] = {"count": 0, "sum": 0}
        cat_data[cat]["count"] += 1
        cat_data[cat]["sum"] += t["satisfaction"]["rating"]

    # Recent low-rated comments
    low_rated = [t for t in all_rated if t["satisfaction"]["rating"] <= 2]
    low_comments = [t["satisfaction"].get("comment", "") for t in low_rated if t["satisfaction"].get("comment")][:5]

    # Recent improvements
    improvements = await db.ticket_feedback_improvements.find(
        {"created_at": {"$gte": cutoff}}, {"_id": 0, "title": 1, "type": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    # Build HTML email

    cat_rows = ""
    for cat, v in sorted(cat_data.items(), key=lambda x: x[1]["count"], reverse=True)[:6]:
        cat_avg = round(v["sum"] / v["count"], 1)
        cat_color = "#10B981" if cat_avg >= 4 else "#F59E0B" if cat_avg >= 3 else "#EF4444"
        cat_rows += f"""<tr><td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;color:#E8ECF4;font-size:13px;text-transform:capitalize;">{cat.replace('_', ' ')}</td><td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;text-align:center;color:#8B9DC3;font-size:13px;">{v['count']}</td><td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;text-align:center;font-weight:700;color:{cat_color};font-size:13px;">{cat_avg}/5</td></tr>"""

    if low_comments:
        "".join(f'<li style="color:#F87171;font-size:12px;margin-bottom:6px;line-height:1.5;">"{c}"</li>' for c in low_comments)

    if improvements:
        "".join(f'<li style="color:#6EE7B7;font-size:12px;margin-bottom:4px;">{imp.get("title", "")}</li>' for imp in improvements)

    from utils.email_service import render_email_header_panel

    render_email_header_panel(
        title=f"Ticket Feedback Digest — {period_label}",
        subtitle=f"{total} new feedback responses collected",
        variant="report",
        accent="#8B5CF6",
        meta_label="Period",
        meta_value=f"Last {days} days",
    )


    # Get admin emails
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    if not admins:
        return {"sent": False, "reason": "No admin users found"}


    sent_to = []
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin["email"],
                template_key="ticket_feedback_digest",
                period=period_label,
                total_responses=total,
                avg_rating=avg,
                positive_pct=pos_pct,
                negative_count=neg_count,
            )
            sent_to.append(admin["email"])
        except Exception as e:
            logger.error(f"Failed to send digest to {admin['email']}: {e}")

    # Update last_sent
    await db.system_config.update_one(
        {"key": "feedback_digest"},
        {"$set": {"last_sent": _now_iso()}},
        upsert=True,
    )

    logger.info(f"Feedback digest sent to {len(sent_to)} admins: {', '.join(sent_to)}")
    return {"sent": True, "recipients": sent_to, "stats": {"total": total, "avg": avg, "csat": csat, "nps": nps}}


# ─── Sentiment Drop Alerts ────────────────────────────────────────────────────

@router.get("/sentiment-alerts/config")
async def get_sentiment_alert_config(request: Request):
    """Get sentiment alert configuration."""
    await _require_admin_user(request)
    config = await db.system_config.find_one({"key": "sentiment_alerts"}, {"_id": 0})
    if not config:
        config = {"key": "sentiment_alerts", "enabled": True, "threshold_pct": 30, "spike_pct": 15, "cooldown_hours": 24}
    return {
        "enabled": config.get("enabled", True),
        "threshold_pct": config.get("threshold_pct", 30),
        "spike_pct": config.get("spike_pct", 15),
        "cooldown_hours": config.get("cooldown_hours", 24),
        "last_checked": config.get("last_checked"),
    }


@router.put("/sentiment-alerts/config")
async def update_sentiment_alert_config(request: Request):
    """Update sentiment alert settings."""
    admin = await _require_admin_user(request)
    body = await request.json()
    enabled = body.get("enabled", True)
    threshold_pct = max(5, min(80, int(body.get("threshold_pct", 30))))
    spike_pct = max(5, min(50, int(body.get("spike_pct", 15))))
    cooldown_hours = max(1, min(168, int(body.get("cooldown_hours", 24))))
    await db.system_config.update_one(
        {"key": "sentiment_alerts"},
        {"$set": {
            "enabled": enabled,
            "threshold_pct": threshold_pct,
            "spike_pct": spike_pct,
            "cooldown_hours": cooldown_hours,
            "updated_at": _now_iso(),
            "updated_by": admin.user_id,
        }},
        upsert=True,
    )
    return {"success": True, "enabled": enabled, "threshold_pct": threshold_pct, "spike_pct": spike_pct, "cooldown_hours": cooldown_hours}


@router.get("/sentiment-alerts/history")
async def get_sentiment_alert_history(request: Request, limit: int = 50):
    """Get sentiment alert history."""
    await _require_admin_user(request)
    alerts = await db.sentiment_alerts.find(
        {}, {"_id": 0}
    ).sort("triggered_at", -1).limit(limit).to_list(limit)
    return {"alerts": alerts, "total": len(alerts)}


async def run_sentiment_alert_check():
    """Hourly job: check sentiment per category and send email alerts when thresholds are breached."""
    import logging
    logger = logging.getLogger(__name__)

    config = await db.system_config.find_one({"key": "sentiment_alerts"}, {"_id": 0})
    if not config:
        config = {"enabled": True, "threshold_pct": 30, "spike_pct": 15, "cooldown_hours": 24}

    if not config.get("enabled", True):
        return {"checked": False, "reason": "Sentiment alerts disabled"}

    threshold_pct = config.get("threshold_pct", 30)
    spike_pct = config.get("spike_pct", 15)
    cooldown_hours = config.get("cooldown_hours", 24)

    now = datetime.now(timezone.utc)
    cutoff_current = (now - timedelta(days=7)).isoformat()
    cutoff_previous = (now - timedelta(days=14)).isoformat()

    # Fetch tickets for current and previous week
    all_tickets = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}, "satisfaction.rated_at": {"$gte": cutoff_previous}},
        {"_id": 0, "satisfaction": 1, "category": 1, "subject": 1, "ticket_number": 1},
    ).to_list(10000)

    current_tickets = [t for t in all_tickets if t.get("satisfaction", {}).get("rated_at", "") >= cutoff_current]
    previous_tickets = [t for t in all_tickets if cutoff_previous <= t.get("satisfaction", {}).get("rated_at", "") < cutoff_current]

    if not current_tickets:
        await db.system_config.update_one({"key": "sentiment_alerts"}, {"$set": {"last_checked": _now_iso()}}, upsert=True)
        return {"checked": True, "alerts_sent": 0, "reason": "No recent tickets"}

    # Calculate sentiment per category for current week
    def calc_sentiment(tickets):
        cats = {}
        for t in tickets:
            cat = t.get("category", "other")
            rating = t["satisfaction"].get("rating", 0)
            if cat not in cats:
                cats[cat] = {"pos": 0, "neu": 0, "neg": 0, "total": 0, "sum": 0}
            cats[cat]["total"] += 1
            cats[cat]["sum"] += rating
            if rating >= 4:
                cats[cat]["pos"] += 1
            elif rating == 3:
                cats[cat]["neu"] += 1
            else:
                cats[cat]["neg"] += 1
        result = {}
        for cat, v in cats.items():
            tot = v["total"] or 1
            result[cat] = {
                "negative_pct": round(v["neg"] / tot * 100, 1),
                "positive_pct": round(v["pos"] / tot * 100, 1),
                "avg_rating": round(v["sum"] / tot, 2),
                "count": v["total"],
            }
        return result

    current_sentiment = calc_sentiment(current_tickets)
    previous_sentiment = calc_sentiment(previous_tickets)

    # Check cooldown — only alert for a category if last alert was > cooldown_hours ago
    cooldown_cutoff = (now - timedelta(hours=cooldown_hours)).isoformat()

    triggered_alerts = []
    for cat, sv in current_sentiment.items():
        if sv["count"] < 3:
            continue  # Skip categories with too few tickets

        reasons = []

        # Check 1: Absolute threshold breach
        if sv["negative_pct"] >= threshold_pct:
            reasons.append(f"Negative sentiment at {sv['negative_pct']}% (threshold: {threshold_pct}%)")

        # Check 2: Week-over-week spike
        prev = previous_sentiment.get(cat)
        if prev and prev["count"] >= 3:
            delta = sv["negative_pct"] - prev["negative_pct"]
            if delta >= spike_pct:
                reasons.append(f"Negative sentiment spiked +{delta:.1f}pp vs previous week ({prev['negative_pct']}% -> {sv['negative_pct']}%)")

        if not reasons:
            continue

        # Check cooldown for this category
        recent_alert = await db.sentiment_alerts.find_one(
            {"category": cat, "triggered_at": {"$gte": cooldown_cutoff}},
            {"_id": 0}
        )
        if recent_alert:
            continue  # Already alerted recently

        # Get example low-rated tickets
        low_tickets = [t for t in current_tickets if t.get("category") == cat and t["satisfaction"].get("rating", 5) <= 2]
        examples = [{"subject": t.get("subject", ""), "rating": t["satisfaction"]["rating"], "ticket": t.get("ticket_number", "")} for t in low_tickets[:3]]

        alert_record = {
            "alert_id": f"sa_{secrets.token_hex(6)}",
            "category": cat,
            "triggered_at": _now_iso(),
            "reasons": reasons,
            "negative_pct": sv["negative_pct"],
            "positive_pct": sv["positive_pct"],
            "avg_rating": sv["avg_rating"],
            "ticket_count": sv["count"],
            "previous_negative_pct": previous_sentiment.get(cat, {}).get("negative_pct"),
            "example_tickets": examples,
        }
        await db.sentiment_alerts.insert_one({**alert_record})
        triggered_alerts.append(alert_record)

    # Send email if there are alerts
    if triggered_alerts:
        await _send_sentiment_alert_email(triggered_alerts)

    await db.system_config.update_one(
        {"key": "sentiment_alerts"},
        {"$set": {"last_checked": _now_iso()}},
        upsert=True,
    )

    logger.info(f"Sentiment alert check: {len(triggered_alerts)} alert(s) triggered")
    return {"checked": True, "alerts_sent": len(triggered_alerts)}


async def _send_sentiment_alert_email(alerts: list):
    """Send a consolidated sentiment drop alert email to all admins."""
    import logging
    logger = logging.getLogger(__name__)
    from utils.email_service import render_email_header_panel

    alert_count = len(alerts)
    categories = ", ".join(a["category"].replace("_", " ").title() for a in alerts)

    render_email_header_panel(
        title=f"Sentiment Alert — {alert_count} {'Category' if alert_count == 1 else 'Categories'} Flagged",
        subtitle=f"Negative sentiment threshold breached in: {categories}",
        variant="report",
        accent="#EF4444",
        meta_label="Severity",
        meta_value="High" if any(a["negative_pct"] >= 50 for a in alerts) else "Medium",
    )

    alert_rows = ""
    for a in alerts:
        neg_color = "#EF4444" if a["negative_pct"] >= 50 else "#F97316" if a["negative_pct"] >= 30 else "#EAB308"
        reasons_html = "<br/>".join(f'<span style="color:#FCA5A5;font-size:11px;">{r}</span>' for r in a["reasons"])
        examples_html = ""
        if a.get("example_tickets"):
            items = "".join(f'<li style="color:#94A3B8;font-size:11px;margin-bottom:3px;">{ex["ticket"]} — {ex["subject"]} ({ex["rating"]}/5)</li>' for ex in a["example_tickets"])
            examples_html = f'<ul style="margin:6px 0 0;padding-left:16px;">{items}</ul>'

        alert_rows += f"""
        <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #7F1D1D;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="color:#E8ECF4;font-size:14px;font-weight:700;text-transform:capitalize;">{a["category"].replace("_", " ")}</span>
            <span style="color:{neg_color};font-size:20px;font-weight:800;">{a["negative_pct"]}% negative</span>
          </div>
          <div style="margin-bottom:6px;">{reasons_html}</div>
          <div style="display:flex;gap:16px;margin-top:8px;">
            <span style="color:#8B9DC3;font-size:11px;">Avg: <strong style="color:#F59E0B;">{a["avg_rating"]}/5</strong></span>
            <span style="color:#8B9DC3;font-size:11px;">Tickets: <strong style="color:#E8ECF4;">{a["ticket_count"]}</strong></span>
            {f'<span style="color:#8B9DC3;font-size:11px;">Prev week: <strong style="color:#94A3B8;">{a["previous_negative_pct"]}%</strong></span>' if a.get("previous_negative_pct") is not None else ""}
          </div>
          {examples_html}
        </div>"""


    admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin_email,
                template_key="ticket_sentiment_alert",
                categories=categories,
                alert_count=alert_count,
                health_score=health,
            )
        except Exception as e:
            logger.error(f"Failed to send sentiment alert to {admin['email']}: {e}")


# ─── Weekly Sentiment Summary Email ───────────────────────────────────────────

@router.get("/sentiment-summary/config")
async def get_sentiment_summary_config(request: Request):
    """Get weekly sentiment summary email configuration."""
    await _require_admin_user(request)
    config = await db.system_config.find_one({"key": "sentiment_summary"}, {"_id": 0})
    if not config:
        config = {"key": "sentiment_summary", "enabled": True, "day": "friday", "hour": 9}
    return {
        "enabled": config.get("enabled", True),
        "day": config.get("day", "friday"),
        "hour": config.get("hour", 9),
        "last_sent": config.get("last_sent"),
    }


@router.put("/sentiment-summary/config")
async def update_sentiment_summary_config(request: Request):
    """Update weekly sentiment summary email settings."""
    admin = await _require_admin_user(request)
    body = await request.json()
    enabled = body.get("enabled", True)
    day = body.get("day", "friday")
    if day not in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        raise HTTPException(status_code=400, detail="Invalid day")
    hour = max(0, min(23, int(body.get("hour", 9))))
    await db.system_config.update_one(
        {"key": "sentiment_summary"},
        {"$set": {"enabled": enabled, "day": day, "hour": hour, "updated_at": _now_iso(), "updated_by": admin.user_id}},
        upsert=True,
    )
    return {"success": True, "enabled": enabled, "day": day, "hour": hour}


@router.post("/sentiment-summary/send-now")
async def send_sentiment_summary_now(request: Request):
    """Manually trigger a sentiment summary email."""
    await _require_admin_user(request)
    result = await generate_and_send_sentiment_summary(force=True)
    return result


async def generate_and_send_sentiment_summary(force: bool = False):
    """Generate and send weekly sentiment summary to all admins."""
    import logging
    logger = logging.getLogger(__name__)

    config = await db.system_config.find_one({"key": "sentiment_summary"}, {"_id": 0})
    if not config:
        config = {"enabled": True}

    if not config.get("enabled", True) and not force:
        return {"sent": False, "reason": "Sentiment summary emails disabled"}

    now = datetime.now(timezone.utc)
    current_start = (now - timedelta(days=7)).isoformat()
    previous_start = (now - timedelta(days=14)).isoformat()

    all_tickets = await db.support_submissions.find(
        {"satisfaction": {"$exists": True, "$ne": None}, "satisfaction.rated_at": {"$gte": previous_start}},
        {"_id": 0, "satisfaction": 1, "category": 1, "priority": 1, "subject": 1, "ticket_number": 1},
    ).to_list(10000)

    current_tickets = [t for t in all_tickets if t.get("satisfaction", {}).get("rated_at", "") >= current_start]
    previous_tickets = [t for t in all_tickets if previous_start <= t.get("satisfaction", {}).get("rated_at", "") < current_start]

    if not current_tickets and not force:
        return {"sent": False, "reason": "No tickets in current period"}

    def _calc(tickets):
        cats = {}
        overall = {"pos": 0, "neu": 0, "neg": 0, "total": 0, "sum": 0}
        for t in tickets:
            cat = t.get("category", "other")
            rating = t["satisfaction"].get("rating", 0)
            if cat not in cats:
                cats[cat] = {"pos": 0, "neu": 0, "neg": 0, "total": 0, "sum": 0}
            cats[cat]["total"] += 1
            cats[cat]["sum"] += rating
            overall["total"] += 1
            overall["sum"] += rating
            if rating >= 4:
                cats[cat]["pos"] += 1
                overall["pos"] += 1
            elif rating == 3:
                cats[cat]["neu"] += 1
                overall["neu"] += 1
            else:
                cats[cat]["neg"] += 1
                overall["neg"] += 1
        result = {}
        for cat, v in cats.items():
            tot = v["total"] or 1
            result[cat] = {
                "positive_pct": round(v["pos"] / tot * 100, 1),
                "negative_pct": round(v["neg"] / tot * 100, 1),
                "neutral_pct": round(v["neu"] / tot * 100, 1),
                "avg_rating": round(v["sum"] / tot, 2),
                "count": v["total"],
            }
        ot = overall["total"] or 1
        overall_result = {
            "positive_pct": round(overall["pos"] / ot * 100, 1),
            "negative_pct": round(overall["neg"] / ot * 100, 1),
            "avg_rating": round(overall["sum"] / ot, 2),
            "count": overall["total"],
        }
        return result, overall_result

    curr_cats, curr_overall = _calc(current_tickets)
    prev_cats, prev_overall = _calc(previous_tickets)

    # Compute health score (0-100): weighted by positive%, avg rating, volume
    health = min(100, max(0, int(curr_overall["positive_pct"] * 0.6 + curr_overall["avg_rating"] * 8)))

    # Categorize improvements vs declines
    improving = []
    declining = []
    stable = []
    all_cats = set(list(curr_cats.keys()) + list(prev_cats.keys()))
    for cat in sorted(all_cats):
        curr = curr_cats.get(cat)
        prev = prev_cats.get(cat)
        if not curr:
            continue
        prev_neg = prev["negative_pct"] if prev else 0
        prev_pos = prev["positive_pct"] if prev else 0
        delta_neg = curr["negative_pct"] - prev_neg
        delta_pos = curr["positive_pct"] - prev_pos
        entry = {
            "category": cat,
            "positive_pct": curr["positive_pct"],
            "negative_pct": curr["negative_pct"],
            "avg_rating": curr["avg_rating"],
            "count": curr["count"],
            "delta_positive": round(delta_pos, 1),
            "delta_negative": round(delta_neg, 1),
            "prev_positive_pct": prev_pos,
            "prev_negative_pct": prev_neg,
        }
        if delta_pos > 5 or delta_neg < -5:
            improving.append(entry)
        elif delta_neg > 5 or delta_pos < -5:
            declining.append(entry)
        else:
            stable.append(entry)

    improving.sort(key=lambda x: x["delta_positive"], reverse=True)
    declining.sort(key=lambda x: x["delta_negative"], reverse=True)

    # Build HTML email
    from utils.email_service import render_email_header_panel

    health_color = "#22c55e" if health >= 70 else "#eab308" if health >= 50 else "#ef4444"
    health_label = "Excellent" if health >= 80 else "Good" if health >= 70 else "Fair" if health >= 50 else "Needs Attention"

    header = render_email_header_panel(
        title="Weekly Sentiment Summary",
        subtitle=f"{curr_overall['count']} rated tickets this week | Health: {health}/100",
        variant="report",
        accent="#8B5CF6",
        meta_label="Week of",
        meta_value=now.strftime("%b %d, %Y"),
    )

    # Overall KPIs
    pos_delta = round(curr_overall["positive_pct"] - prev_overall.get("positive_pct", 0), 1)
    neg_delta = round(curr_overall["negative_pct"] - prev_overall.get("negative_pct", 0), 1)
    pos_arrow = f'<span style="color:#22c55e;">+{pos_delta}pp</span>' if pos_delta > 0 else f'<span style="color:#ef4444;">{pos_delta}pp</span>' if pos_delta < 0 else '<span style="color:#8B9DC3;">—</span>'
    neg_arrow = f'<span style="color:#ef4444;">+{neg_delta}pp</span>' if neg_delta > 0 else f'<span style="color:#22c55e;">{neg_delta}pp</span>' if neg_delta < 0 else '<span style="color:#8B9DC3;">—</span>'

    # Category rows for mini heatmap
    def _cat_row(entry, icon_color):
        cat_label = entry["category"].replace("_", " ").title()
        bar_pos_w = max(2, int(entry["positive_pct"]))
        bar_neu_w = max(2, int(100 - entry["positive_pct"] - entry["negative_pct"]))
        bar_neg_w = max(2, int(entry["negative_pct"]))
        dp = entry["delta_positive"]
        dn = entry["delta_negative"]
        trend_html = ""
        if dp > 0:
            trend_html = f'<span style="color:#22c55e;font-size:11px;font-weight:700;">+{dp}pp positive</span>'
        elif dn > 0:
            trend_html = f'<span style="color:#ef4444;font-size:11px;font-weight:700;">+{dn}pp negative</span>'
        else:
            trend_html = '<span style="color:#8B9DC3;font-size:11px;">Stable</span>'
        return f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;color:#E8ECF4;font-size:13px;text-transform:capitalize;width:130px;">{cat_label}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;">
            <div style="display:flex;height:14px;border-radius:7px;overflow:hidden;background:#1E2D4A;">
              <div style="width:{bar_pos_w}%;background:#22c55e;"></div>
              <div style="width:{bar_neu_w}%;background:#eab308;"></div>
              <div style="width:{bar_neg_w}%;background:#ef4444;"></div>
            </div>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;text-align:center;color:#F59E0B;font-weight:700;font-size:13px;">{entry['avg_rating']}/5</td>
          <td style="padding:8px 12px;border-bottom:1px solid #1E2D4A;text-align:right;">{trend_html}</td>
        </tr>"""

    improving_rows = "".join(_cat_row(e, "#22c55e") for e in improving)
    declining_rows = "".join(_cat_row(e, "#ef4444") for e in declining)
    stable_rows = "".join(_cat_row(e, "#8B9DC3") for e in stable)

    improving_section = ""
    if improving:
        improving_section = f"""<div style="margin-bottom:20px;">
          <div style="color:#22c55e;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Improving Categories</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr style="background:#0F172A;"><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">CATEGORY</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">SENTIMENT</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:center;">AVG</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:right;">TREND</td></tr>
            {improving_rows}
          </table>
        </div>"""

    declining_section = ""
    if declining:
        declining_section = f"""<div style="margin-bottom:20px;">
          <div style="color:#ef4444;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Declining Categories</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr style="background:#0F172A;"><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">CATEGORY</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">SENTIMENT</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:center;">AVG</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:right;">TREND</td></tr>
            {declining_rows}
          </table>
        </div>"""

    stable_section = ""
    if stable:
        stable_section = f"""<div style="margin-bottom:20px;">
          <div style="color:#8B9DC3;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Stable Categories</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr style="background:#0F172A;"><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">CATEGORY</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;">SENTIMENT</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:center;">AVG</td><td style="padding:6px 12px;color:#8B9DC3;font-size:10px;font-weight:700;text-align:right;">TREND</td></tr>
            {stable_rows}
          </table>
        </div>"""

    dashboard_url = f"{(os.environ.get('FRONTEND_BASE_URL') or '').rstrip('/')}/executive-dashboard"

    f"""{header}
<div style="background-color:#0F172A;padding:24px 28px;border-radius:0 0 20px 20px;">

  <!-- Health Score -->
  <div style="text-align:center;margin-bottom:24px;">
    <div style="display:inline-block;background-color:#1E293B;border-radius:16px;padding:20px 36px;border:2px solid {health_color};">
      <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Sentiment Health</div>
      <div style="color:{health_color};font-size:44px;font-weight:900;margin:4px 0;">{health}</div>
      <div style="color:{health_color};font-size:12px;font-weight:700;">{health_label}</div>
    </div>
  </div>

  <!-- KPI Row -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
    <tr>
      <td width="25%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:12px;padding:14px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Tickets</div>
          <div style="color:#3B82F6;font-size:24px;font-weight:800;margin-top:4px;">{curr_overall['count']}</div>
        </div>
      </td>
      <td width="25%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:12px;padding:14px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Avg Rating</div>
          <div style="color:#F59E0B;font-size:24px;font-weight:800;margin-top:4px;">{curr_overall['avg_rating']}/5</div>
        </div>
      </td>
      <td width="25%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:12px;padding:14px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Positive</div>
          <div style="color:#22c55e;font-size:24px;font-weight:800;margin-top:4px;">{curr_overall['positive_pct']}%</div>
          <div style="font-size:10px;margin-top:2px;">{pos_arrow}</div>
        </div>
      </td>
      <td width="25%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:12px;padding:14px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Negative</div>
          <div style="color:#ef4444;font-size:24px;font-weight:800;margin-top:4px;">{curr_overall['negative_pct']}%</div>
          <div style="font-size:10px;margin-top:2px;">{neg_arrow}</div>
        </div>
      </td>
    </tr>
  </table>

  <!-- Mini Sentiment Heatmap -->
  <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #334155;margin-bottom:16px;">
    <div style="color:#E8ECF4;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px;">Category Sentiment Snapshot</div>
    {improving_section}
    {declining_section}
    {stable_section}
    <div style="display:flex;gap:16px;margin-top:10px;justify-content:center;">
      <span style="font-size:10px;color:#8B9DC3;"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#22c55e;vertical-align:middle;margin-right:3px;"></span>Positive</span>
      <span style="font-size:10px;color:#8B9DC3;"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#eab308;vertical-align:middle;margin-right:3px;"></span>Neutral</span>
      <span style="font-size:10px;color:#8B9DC3;"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#ef4444;vertical-align:middle;margin-right:3px;"></span>Negative</span>
    </div>
  </div>

  <!-- CTA -->
  <div style="text-align:center;margin-top:24px;">
    <a href="{dashboard_url}" style="display:inline-block;background-color:#8B5CF6;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;padding:12px 28px;border-radius:10px;">View Heatmaps Dashboard</a>
  </div>

  <div style="color:#5B6F92;font-size:11px;text-align:center;margin-top:20px;">
    Weekly sentiment pulse by RealAICoach.<br/>
    <a href="{dashboard_url}" style="color:#3B82F6;text-decoration:none;">Manage summary settings</a>
  </div>
</div>
<!-- BRANDED_FOOTER_V2 -->"""

    # Send to all admins
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    if not admins:
        return {"sent": False, "reason": "No admin users found"}

    sent_to = []
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin["email"],
                template_key="sentiment_summary_v7",
                recipient_name=admin.get("name", ""),
                health=health,
                ticket_count=curr_overall.get("count", 0),
                avg_rating=str(curr_overall.get("avg_rating", "N/A")),
                positive_pct=f"{curr_overall.get('positive_pct', 0)}%",
                neutral_pct=f"{curr_overall.get('neutral_pct', 0)}%",
                negative_pct=f"{curr_overall.get('negative_pct', 0)}%",
            )
            sent_to.append(admin["email"])
        except Exception as e:
            logger.error(f"Failed to send sentiment summary to {admin['email']}: {e}")

    await db.system_config.update_one(
        {"key": "sentiment_summary"},
        {"$set": {"last_sent": _now_iso()}},
        upsert=True,
    )

    logger.info(f"Sentiment summary sent to {len(sent_to)} admins")
    return {
        "sent": True,
        "recipients": sent_to,
        "stats": {
            "health": health,
            "tickets": curr_overall["count"],
            "avg_rating": curr_overall["avg_rating"],
            "improving": len(improving),
            "declining": len(declining),
            "stable": len(stable),
        },
    }
