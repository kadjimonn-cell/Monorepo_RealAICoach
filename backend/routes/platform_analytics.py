"""Platform Analytics Enhancement - Engagement, Funnel, and Scoring APIs."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta

from routes.db import db, require_admin
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/admin/platform-analytics")


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_end_date"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )


def _NOW():
    return datetime.now(timezone.utc)


def _date_query(days: int) -> dict:
    cutoff = (_NOW() - timedelta(days=days)).isoformat()
    return {"$gte": cutoff}


# ─── Engagement Overview ────────────────────────────────────────────────────


@router.get("/engagement")
async def engagement_metrics(request: Request, days: int = 30):
    """DAU/WAU/MAU, session counts, and retention rates."""
    await require_admin(request)
    now = _NOW()

    # Active user counts from security_events (login_success)
    dau_cutoff = (now - timedelta(days=1)).isoformat()
    wau_cutoff = (now - timedelta(days=7)).isoformat()
    mau_cutoff = (now - timedelta(days=30)).isoformat()

    dau_users = await db.security_events.distinct(
        "user_id", {"event_type": "login_success", "timestamp": {"$gte": dau_cutoff}}
    )
    wau_users = await db.security_events.distinct(
        "user_id", {"event_type": "login_success", "timestamp": {"$gte": wau_cutoff}}
    )
    mau_users = await db.security_events.distinct(
        "user_id", {"event_type": "login_success", "timestamp": {"$gte": mau_cutoff}}
    )

    total_users = await db.users.count_documents({})

    # Session count for the period
    period_cutoff = (now - timedelta(days=days)).isoformat()
    total_sessions = await db.security_events.count_documents(
        {"event_type": "login_success", "timestamp": {"$gte": period_cutoff}}
    )

    # Retention: users active in last 7d who were also active 30d ago
    prev_mau_cutoff = (now - timedelta(days=60)).isoformat()
    prev_mau_users = set(
        await db.security_events.distinct(
            "user_id", {"event_type": "login_success", "timestamp": {"$gte": prev_mau_cutoff, "$lt": mau_cutoff}}
        )
    )
    current_mau = set(mau_users)
    retained = prev_mau_users & current_mau
    retention_30d = round(len(retained) / max(len(prev_mau_users), 1) * 100, 1)

    # Avg sessions per user
    avg_sessions = round(total_sessions / max(len(set(mau_users)), 1), 1)

    # DAU trend (last N days)
    dau_trend = []
    for i in range(min(days, 30)):
        day_start = (now - timedelta(days=i + 1)).replace(hour=0, minute=0, second=0).isoformat()
        day_end = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0).isoformat()
        day_users = await db.security_events.distinct(
            "user_id", {"event_type": "login_success", "timestamp": {"$gte": day_start, "$lt": day_end}}
        )
        day_label = (now - timedelta(days=i + 1)).strftime("%b %d")
        dau_trend.append({"date": day_label, "count": len(day_users)})
    dau_trend.reverse()

    return {
        "dau": len(dau_users),
        "wau": len(wau_users),
        "mau": len(mau_users),
        "total_users": total_users,
        "total_sessions": total_sessions,
        "avg_sessions_per_user": avg_sessions,
        "retention_30d": retention_30d,
        "dau_trend": dau_trend,
        "stickiness": round(len(dau_users) / max(len(mau_users), 1) * 100, 1),
    }


# ─── Feature Adoption ───────────────────────────────────────────────────────


@router.get("/feature-adoption")
async def feature_adoption(request: Request):
    """Feature usage rates across the platform."""
    await require_admin(request)
    total_users = max(await db.users.count_documents({}), 1)

    features = [
        {"name": "AI Coach (Nova)", "collection": "conversations", "field": "user_id"},
        {"name": "AI Goals", "collection": "ai_goals_entries", "field": "user_id"},
        {"name": "AI Learning Hub", "collection": "ai_learning_sessions", "field": "user_id"},
        {"name": "AI Problem Solver", "collection": "ai_problem_sessions", "field": "user_id"},
        {"name": "AI Documents", "collection": "ai_document_sessions", "field": "user_id"},
        {"name": "Referral Program", "collection": "referrals", "field": "referrer_id"},
        {"name": "Support Tickets", "collection": "support_tickets", "field": "user_id"},
        {"name": "ID Checker", "collection": "id_verifications", "field": "user_id"},
    ]

    adoption_data = []
    for feat in features:
        try:
            unique_users = len(await db[feat["collection"]].distinct(feat["field"]))
            rate = round(unique_users / total_users * 100, 1)
            adoption_data.append(
                {
                    "feature": feat["name"],
                    "unique_users": unique_users,
                    "adoption_rate": rate,
                }
            )
        except Exception:
            adoption_data.append(
                {
                    "feature": feat["name"],
                    "unique_users": 0,
                    "adoption_rate": 0,
                }
            )

    adoption_data.sort(key=lambda x: x["adoption_rate"], reverse=True)
    return {"features": adoption_data, "total_users": total_users}


# ─── Peak Hours Heatmap ─────────────────────────────────────────────────────


@router.get("/peak-hours")
async def peak_hours(request: Request, days: int = 14):
    """Hourly activity distribution for heatmap."""
    await require_admin(request)
    cutoff = (_NOW() - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"event_type": "login_success", "timestamp": {"$gte": cutoff}}},
        {"$addFields": {"ts_date": {"$dateFromString": {"dateString": "$timestamp", "onError": None}}}},
        {"$match": {"ts_date": {"$ne": None}}},
        {
            "$group": {
                "_id": {
                    "day": {"$dayOfWeek": "$ts_date"},
                    "hour": {"$hour": "$ts_date"},
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.day": 1, "_id.hour": 1}},
    ]

    results = await db.security_events.aggregate(pipeline).to_list(200)
    day_names = ["", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    heatmap = []
    for r in results:
        heatmap.append(
            {
                "day": day_names[r["_id"]["day"]],
                "day_num": r["_id"]["day"],
                "hour": r["_id"]["hour"],
                "count": r["count"],
            }
        )

    return {"heatmap": heatmap, "period_days": days}


# ─── Referral Conversion Funnel ──────────────────────────────────────────────


@router.get("/referral-funnel")
async def referral_funnel(request: Request):
    """Referral conversion funnel: sent → clicked → signed up → active → paid."""
    await require_admin(request)

    # Total referrals sent
    total_sent = await db.referrals.count_documents({})

    # Clicked (referrals with clicked_at or status != pending)
    clicked = await db.referrals.count_documents(
        {
            "$or": [
                {"clicked_at": {"$exists": True, "$ne": None}},
                {"status": {"$in": ["clicked", "signed_up", "active", "converted"]}},
            ]
        }
    )

    # Signed up (referrals that led to registration)
    signed_up = await db.referrals.count_documents({"status": {"$in": ["signed_up", "active", "converted"]}})

    # Active users from referrals (had at least one session in last 30d)
    mau_cutoff = (_NOW() - timedelta(days=30)).isoformat()
    referred_users = await db.referrals.distinct(
        "referred_user_id", {"referred_user_id": {"$exists": True, "$ne": None}}
    )
    active_referred = 0
    if referred_users:
        active_referred = len(
            await db.security_events.distinct(
                "user_id",
                {"user_id": {"$in": referred_users}, "event_type": "login_success", "timestamp": {"$gte": mau_cutoff}},
            )
        )

    # Converted to paid
    converted = await db.referrals.count_documents({"status": "converted"})

    funnel = [
        {"stage": "Referrals Sent", "count": total_sent, "rate": 100},
        {"stage": "Clicked Link", "count": clicked, "rate": round(clicked / max(total_sent, 1) * 100, 1)},
        {"stage": "Signed Up", "count": signed_up, "rate": round(signed_up / max(total_sent, 1) * 100, 1)},
        {
            "stage": "Active (30d)",
            "count": active_referred,
            "rate": round(active_referred / max(total_sent, 1) * 100, 1),
        },
        {"stage": "Converted to Paid", "count": converted, "rate": round(converted / max(total_sent, 1) * 100, 1)},
    ]

    return {"funnel": funnel}


@router.get("/top-referrers")
async def top_referrers(request: Request, limit: int = 10):
    """Top referrers by number of successful referrals."""
    await require_admin(request)

    pipeline = [
        {"$match": {"referrer_id": {"$exists": True, "$ne": None}}},
        {
            "$group": {
                "_id": "$referrer_id",
                "total_referrals": {"$sum": 1},
                "signed_up": {"$sum": {"$cond": [{"$in": ["$status", ["signed_up", "active", "converted"]]}, 1, 0]}},
                "converted": {"$sum": {"$cond": [{"$eq": ["$status", "converted"]}, 1, 0]}},
            }
        },
        {"$sort": {"total_referrals": -1}},
        {"$limit": limit},
    ]

    results = await db.referrals.aggregate(pipeline).to_list(limit)

    referrers = []
    for r in results:
        user = await db.users.find_one({"user_id": r["_id"]}, {"_id": 0, "name": 1, "email": 1, "profile_image": 1})
        referrers.append(
            {
                "user_id": r["_id"],
                "name": user.get("name", "Unknown") if user else "Unknown",
                "email": user.get("email", "") if user else "",
                "profile_image": user.get("profile_image", "") if user else "",
                "total_referrals": r["total_referrals"],
                "signed_up": r["signed_up"],
                "converted": r["converted"],
                "conversion_rate": round(r["converted"] / max(r["total_referrals"], 1) * 100, 1),
            }
        )

    return {"referrers": referrers}


# ─── Engagement Scoring ──────────────────────────────────────────────────────


@router.get("/engagement-scores")
async def engagement_scores(request: Request, limit: int = 50):
    """Per-user engagement scoring with segmentation."""
    await require_admin(request)
    now = _NOW()
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    # Get all users
    users = await db.users.find(
        {}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1, "created_at": 1}
    ).to_list(5000)

    scored_users = []
    for u in users:
        uid = u.get("user_id", "")
        if not uid:
            continue

        # Login frequency (30d)
        logins_30d = await db.security_events.count_documents(
            {"user_id": uid, "event_type": "login_success", "timestamp": {"$gte": cutoff_30d}}
        )
        logins_7d = await db.security_events.count_documents(
            {"user_id": uid, "event_type": "login_success", "timestamp": {"$gte": cutoff_7d}}
        )

        # Feature usage (30d) - conversations as proxy
        conversations_30d = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": cutoff_30d}})

        # Scoring: login_freq (40%) + feature_usage (40%) + recency (20%)
        login_score = min(logins_30d / 15, 1.0) * 40  # 15+ logins = max
        feature_score = min(conversations_30d / 10, 1.0) * 40  # 10+ conversations = max
        recency_score = 20 if logins_7d > 0 else (10 if logins_30d > 0 else 0)

        total_score = round(login_score + feature_score + recency_score)

        # Segment
        if total_score >= 70:
            segment = "Power User"
        elif total_score >= 30:
            segment = "Regular"
        elif total_score > 0:
            segment = "At Risk"
        else:
            segment = "Dormant"

        scored_users.append(
            {
                "user_id": uid,
                "name": u.get("name", "Unknown"),
                "email": u.get("email", ""),
                "plan": _effective_plan_from_user_doc(u),
                "score": total_score,
                "segment": segment,
                "logins_30d": logins_30d,
                "logins_7d": logins_7d,
                "conversations_30d": conversations_30d,
            }
        )

    scored_users.sort(key=lambda x: x["score"], reverse=True)

    # Segment summary
    segments = {"Power User": 0, "Regular": 0, "At Risk": 0, "Dormant": 0}
    for su in scored_users:
        segments[su["segment"]] += 1

    return {
        "users": scored_users[:limit],
        "total_scored": len(scored_users),
        "segments": segments,
        "avg_score": round(sum(s["score"] for s in scored_users) / max(len(scored_users), 1), 1),
    }


# ─── Cohort Retention Analysis ───────────────────────────────────────────────


@router.get("/cohort-retention")
async def cohort_retention(request: Request, weeks: int = 8):
    """Week-over-week retention cohort: signup week → % active in week N."""
    await require_admin(request)
    now = _NOW()

    cohorts = []
    for w in range(weeks):
        # Cohort = users who signed up in this week
        week_start = (now - timedelta(weeks=w + 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = (now - timedelta(weeks=w)).replace(hour=0, minute=0, second=0, microsecond=0)

        # created_at is stored as native datetime, so query with datetime objects
        cohort_users = await db.users.distinct("user_id", {"created_at": {"$gte": week_start, "$lt": week_end}})
        cohort_size = len(cohort_users)
        if cohort_size == 0:
            cohorts.append(
                {
                    "week_label": week_start.strftime("%b %d"),
                    "cohort_size": 0,
                    "retention": [],
                }
            )
            continue

        # For each subsequent week, check how many from this cohort were active
        retention = []
        max_future_weeks = min(w + 1, 8)  # Can't measure beyond current date
        for fw in range(max_future_weeks):
            fw_start = (week_end + timedelta(weeks=fw)).isoformat()
            fw_end = (week_end + timedelta(weeks=fw + 1)).isoformat()

            active_in_week = await db.security_events.distinct(
                "user_id",
                {
                    "user_id": {"$in": cohort_users},
                    "event_type": "login_success",
                    "timestamp": {"$gte": fw_start, "$lt": fw_end},
                },
            )
            pct = round(len(active_in_week) / cohort_size * 100, 1)
            retention.append({"week": fw, "active": len(active_in_week), "pct": pct})

        cohorts.append(
            {
                "week_label": week_start.strftime("%b %d"),
                "cohort_size": cohort_size,
                "retention": retention,
            }
        )

    cohorts.reverse()
    return {"cohorts": cohorts, "total_weeks": weeks}


# ─── Engagement Trends Over Time ─────────────────────────────────────────────


@router.get("/engagement-trends")
async def engagement_trends(request: Request, days: int = 60):
    """DAU/WAU/MAU trends over a period for line chart visualization."""
    await require_admin(request)
    now = _NOW()

    # Sample at weekly intervals for the given period
    data_points = []
    num_points = min(days // 7, 12)  # Max 12 data points

    for i in range(num_points):
        point_date = now - timedelta(weeks=i)
        point_label = point_date.strftime("%b %d")

        dau_cutoff = (point_date - timedelta(days=1)).isoformat()
        wau_cutoff = (point_date - timedelta(days=7)).isoformat()
        mau_cutoff = (point_date - timedelta(days=30)).isoformat()
        point_iso = point_date.isoformat()

        dau = len(
            await db.security_events.distinct(
                "user_id", {"event_type": "login_success", "timestamp": {"$gte": dau_cutoff, "$lt": point_iso}}
            )
        )
        wau = len(
            await db.security_events.distinct(
                "user_id", {"event_type": "login_success", "timestamp": {"$gte": wau_cutoff, "$lt": point_iso}}
            )
        )
        mau = len(
            await db.security_events.distinct(
                "user_id", {"event_type": "login_success", "timestamp": {"$gte": mau_cutoff, "$lt": point_iso}}
            )
        )

        data_points.append(
            {
                "date": point_label,
                "dau": dau,
                "wau": wau,
                "mau": mau,
            }
        )

    data_points.reverse()

    # Calculate growth rates (latest vs earliest)
    if len(data_points) >= 2:
        first, last = data_points[0], data_points[-1]
        dau_growth = round((last["dau"] - first["dau"]) / max(first["dau"], 1) * 100, 1)
        wau_growth = round((last["wau"] - first["wau"]) / max(first["wau"], 1) * 100, 1)
        mau_growth = round((last["mau"] - first["mau"]) / max(first["mau"], 1) * 100, 1)
    else:
        dau_growth = wau_growth = mau_growth = 0

    return {
        "trends": data_points,
        "growth": {"dau": dau_growth, "wau": wau_growth, "mau": mau_growth},
        "period_days": days,
    }
