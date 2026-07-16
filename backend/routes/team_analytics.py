"""Team Analytics & Webhook Event Stream APIs."""

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone, timedelta
from .db import db, require_auth

router = APIRouter(prefix="/team-analytics", tags=["Team Analytics"])


@router.get("/overview")
async def get_team_analytics(request: Request):
    """Aggregate team analytics for dashboards."""
    await require_auth(request)
    total_teams = await db.teams.count_documents({})
    total_members_pipeline = [
        {"$project": {"member_count": {"$size": {"$ifNull": ["$members", []]}}}},
        {"$group": {"_id": None, "total": {"$sum": "$member_count"}}},
    ]
    members_result = await db.teams.aggregate(total_members_pipeline).to_list(1)
    total_members = members_result[0]["total"] if members_result else 0
    # Role distribution
    role_pipeline = [
        {"$unwind": "$members"},
        {"$group": {"_id": "$members.role", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    role_dist = await db.teams.aggregate(role_pipeline).to_list(10)
    role_distribution = [{"role": r["_id"], "count": r["count"]} for r in role_dist]
    # Team sizes
    size_pipeline = [
        {"$project": {"name": 1, "member_count": {"$size": {"$ifNull": ["$members", []]}}}},
        {"$sort": {"member_count": -1}},
        {"$limit": 10},
    ]
    team_sizes = await db.teams.aggregate(size_pipeline).to_list(10)
    top_teams = [{"name": t.get("name", "Unknown"), "members": t["member_count"]} for t in team_sizes]
    # Recent activity from audit logs
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_activity = await db.team_audit_logs.count_documents({"created_at": {"$gte": seven_days_ago}})
    # Activity by type
    activity_pipeline = [{"$group": {"_id": "$action", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    activity_types = await db.team_audit_logs.aggregate(activity_pipeline).to_list(10)
    activity_breakdown = [{"action": a["_id"], "count": a["count"]} for a in activity_types]
    # Growth (teams created in last 30 days, grouped by day)
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    growth_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$project": {"day": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    growth_data = await db.teams.aggregate(growth_pipeline).to_list(30)
    daily_growth = [{"date": g["_id"], "teams_created": g["count"]} for g in growth_data]

    return {
        "total_teams": total_teams,
        "total_members": total_members,
        "avg_team_size": round(total_members / max(total_teams, 1), 1),
        "role_distribution": role_distribution,
        "top_teams": top_teams,
        "recent_activity_7d": recent_activity,
        "activity_breakdown": activity_breakdown,
        "daily_growth": daily_growth,
    }


webhook_event_router = APIRouter(prefix="/webhook-events", tags=["Webhook Events"])


@webhook_event_router.get("/stream")
async def get_webhook_event_stream(request: Request, limit: int = 50, integration_id: str = None):
    """Get recent webhook events for the event stream."""
    await require_auth(request)
    query = {}
    if integration_id:
        query["integration_id"] = integration_id
    events = await db.webhook_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    stats_pipeline = [{"$group": {"_id": "$event_type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    event_stats = await db.webhook_events.aggregate(stats_pipeline).to_list(20)
    total = await db.webhook_events.count_documents({})
    return {
        "events": events,
        "total": total,
        "event_type_stats": [{"type": s["_id"], "count": s["count"]} for s in event_stats],
    }


@webhook_event_router.post("/simulate")
async def simulate_webhook_event(request: Request):
    """Simulate a webhook event for testing."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    import random

    event_types = [
        "candidate.created",
        "candidate.updated",
        "job.opened",
        "job.closed",
        "interview.scheduled",
        "interview.completed",
        "offer.sent",
        "offer.accepted",
    ]
    integrations = ["greenhouse", "lever", "workday"]
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "event_id": f"evt_{random.randint(100000, 999999)}",
        "integration_id": random.choice(integrations),
        "event_type": random.choice(event_types),
        "payload": {"candidate": f"User_{random.randint(1000, 9999)}", "position": f"Role_{random.randint(100, 999)}"},
        "status": "received",
        "created_at": now,
    }
    await db.webhook_events.insert_one({**event})
    # Push real-time notification to admins
    from utils.ws_manager import push_admin_alert

    await push_admin_alert(
        "webhook_event",
        f"Webhook: {event['event_type']}",
        f"From {event['integration_id']}: {event['event_type']}",
        "info",
        {"event_id": event["event_id"], "integration_id": event["integration_id"]},
    )
    return {"success": True, "event": event}
