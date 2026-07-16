"""User Behavior Analytics (UBA) — admin endpoints for user engagement insights."""

from fastapi import APIRouter, Query, Request
import re
from datetime import datetime, timezone, timedelta
from routes.db import db, require_admin

router = APIRouter(prefix="/admin/uba", tags=["UBA Analytics"])


@router.get("/overview")
async def uba_overview(req: Request):
    await require_admin(req)
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    active_24h = await db.security_events.distinct(
        "user_id", {"timestamp": {"$gte": day_ago}, "event_type": "login_success"}
    )
    active_7d = await db.security_events.distinct(
        "user_id", {"timestamp": {"$gte": week_ago}, "event_type": "login_success"}
    )
    active_30d = await db.security_events.distinct(
        "user_id", {"timestamp": {"$gte": month_ago}, "event_type": "login_success"}
    )

    total_ai_sessions = await db.ai_usage_log.count_documents({})
    ai_sessions_7d = await db.ai_usage_log.count_documents({"created_at": {"$gte": week_ago}})

    avg_doc = None
    async for doc in db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": week_ago}}},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            {"$group": {"_id": None, "avg": {"$avg": "$count"}, "max": {"$max": "$count"}}},
        ]
    ):
        avg_doc = doc

    return {
        "total_users": total_users,
        "dau": len(active_24h),
        "wau": len(active_7d),
        "mau": len(active_30d),
        "total_ai_sessions": total_ai_sessions,
        "ai_sessions_7d": ai_sessions_7d,
        "avg_sessions_per_user_7d": round(avg_doc["avg"], 1) if avg_doc else 0,
        "max_sessions_user_7d": avg_doc["max"] if avg_doc else 0,
        "dau_wau_ratio": round(len(active_24h) / max(len(active_7d), 1) * 100, 1),
    }


@router.get("/heatmap")
async def uba_heatmap(req: Request, days: int = Query(14, ge=7, le=90)):
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    cells = []
    async for doc in db.security_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": cutoff}, "event_type": "login_success"}},
            {"$addFields": {"ts_date": {"$dateFromString": {"dateString": "$timestamp", "onError": None}}}},
            {"$match": {"ts_date": {"$ne": None}}},
            {"$addFields": {"dow": {"$dayOfWeek": "$ts_date"}, "hour": {"$hour": "$ts_date"}}},
            {"$group": {"_id": {"dow": "$dow", "hour": "$hour"}, "count": {"$sum": 1}}},
        ]
    ):
        cells.append({"dow": doc["_id"]["dow"], "hour": doc["_id"]["hour"], "count": doc["count"]})

    return {"cells": cells}


@router.get("/features")
async def uba_features(req: Request, days: int = Query(30, ge=7, le=90)):
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    features = []
    async for doc in db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$feature", "count": {"$sum": 1}, "users": {"$addToSet": "$user_id"}}},
            {"$addFields": {"unique_users": {"$size": "$users"}}},
            {"$project": {"feature": "$_id", "count": 1, "unique_users": 1, "_id": 0}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
    ):
        features.append(doc)

    return {"features": features}


@router.get("/funnel")
async def uba_funnel(req: Request):
    await require_admin(req)

    total_registered = await db.users.count_documents({})
    onboarded = await db.progress.distinct("user_id")
    ai_users = await db.ai_usage_log.distinct("user_id")

    engaged_users = [
        doc["_id"]
        async for doc in db.ai_usage_log.aggregate(
            [
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gte": 5}}},
            ]
        )
    ]

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    retained = await db.security_events.distinct(
        "user_id", {"timestamp": {"$gte": week_ago}, "event_type": "login_success"}
    )

    return {
        "funnel": [
            {"step": "Registered", "count": total_registered},
            {"step": "Onboarded", "count": len(onboarded)},
            {"step": "First AI Session", "count": len(ai_users)},
            {"step": "Engaged (5+ sessions)", "count": len(engaged_users)},
            {"step": "Retained (7d active)", "count": len(retained)},
        ]
    }


@router.get("/cohorts")
async def uba_cohorts(req: Request, weeks: int = Query(8, ge=4, le=16)):
    await require_admin(req)
    now = datetime.now(timezone.utc)

    cohorts = []
    for w in range(weeks):
        week_start = now - timedelta(weeks=w + 1)
        week_end = now - timedelta(weeks=w)
        start_str = week_start.isoformat()
        end_str = week_end.isoformat()

        signup_users = await db.users.distinct("user_id", {"created_at": {"$gte": start_str, "$lt": end_str}})
        if not signup_users:
            cohorts.append(
                {
                    "week": week_start.strftime("%b %d"),
                    "signups": 0,
                    "retained_1w": 0,
                    "retained_2w": 0,
                    "retained_4w": 0,
                }
            )
            continue

        r1 = await db.security_events.distinct(
            "user_id",
            {
                "user_id": {"$in": signup_users},
                "event_type": "login_success",
                "timestamp": {"$gte": week_end.isoformat(), "$lt": (week_end + timedelta(weeks=1)).isoformat()},
            },
        )
        r2 = await db.security_events.distinct(
            "user_id",
            {
                "user_id": {"$in": signup_users},
                "event_type": "login_success",
                "timestamp": {
                    "$gte": (week_end + timedelta(weeks=1)).isoformat(),
                    "$lt": (week_end + timedelta(weeks=2)).isoformat(),
                },
            },
        )
        r4 = await db.security_events.distinct(
            "user_id",
            {
                "user_id": {"$in": signup_users},
                "event_type": "login_success",
                "timestamp": {
                    "$gte": (week_end + timedelta(weeks=3)).isoformat(),
                    "$lt": (week_end + timedelta(weeks=4)).isoformat(),
                },
            },
        )

        cohorts.append(
            {
                "week": week_start.strftime("%b %d"),
                "signups": len(signup_users),
                "retained_1w": len(r1),
                "retained_2w": len(r2),
                "retained_4w": len(r4),
            }
        )

    cohorts.reverse()
    return {"cohorts": cohorts}


@router.get("/export/{section}")
async def uba_export(req: Request, section: str, days: int = Query(30, ge=7, le=90)):
    """Export UBA data as CSV."""
    await require_admin(req)
    import csv
    import io

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    buf = io.StringIO()
    writer = csv.writer(buf)

    if section == "features":
        writer.writerow(["Feature", "Usage Count", "Unique Users"])
        async for doc in db.ai_usage_log.aggregate(
            [
                {"$match": {"created_at": {"$gte": cutoff}}},
                {"$group": {"_id": "$feature", "count": {"$sum": 1}, "users": {"$addToSet": "$user_id"}}},
                {"$addFields": {"unique_users": {"$size": "$users"}}},
                {"$sort": {"count": -1}},
            ]
        ):
            writer.writerow([doc["_id"], doc["count"], doc["unique_users"]])
    elif section == "funnel":
        writer.writerow(["Step", "Count"])
        total = await db.users.count_documents({})
        onboarded = len(await db.progress.distinct("user_id"))
        ai_users = len(await db.ai_usage_log.distinct("user_id"))
        engaged = 0
        async for _ in db.ai_usage_log.aggregate(
            [{"$group": {"_id": "$user_id", "c": {"$sum": 1}}}, {"$match": {"c": {"$gte": 5}}}]
        ):
            engaged += 1
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        retained = len(
            await db.security_events.distinct(
                "user_id", {"timestamp": {"$gte": week_ago}, "event_type": "login_success"}
            )
        )
        for step, count in [
            ("Registered", total),
            ("Onboarded", onboarded),
            ("First AI Session", ai_users),
            ("Engaged (5+)", engaged),
            ("Retained (7d)", retained),
        ]:
            writer.writerow([step, count])
    elif section == "cohorts":
        writer.writerow(["Week", "Signups", "Retained 1w", "Retained 2w", "Retained 4w"])
        now = datetime.now(timezone.utc)
        for w in range(8):
            ws = now - timedelta(weeks=w + 1)
            we = now - timedelta(weeks=w)
            users = await db.users.distinct("user_id", {"created_at": {"$gte": ws.isoformat(), "$lt": we.isoformat()}})
            if not users:
                writer.writerow([ws.strftime("%b %d"), 0, 0, 0, 0])
                continue
            r1 = len(
                await db.security_events.distinct(
                    "user_id",
                    {
                        "user_id": {"$in": users},
                        "event_type": "login_success",
                        "timestamp": {"$gte": we.isoformat(), "$lt": (we + timedelta(weeks=1)).isoformat()},
                    },
                )
            )
            r2 = len(
                await db.security_events.distinct(
                    "user_id",
                    {
                        "user_id": {"$in": users},
                        "event_type": "login_success",
                        "timestamp": {
                            "$gte": (we + timedelta(weeks=1)).isoformat(),
                            "$lt": (we + timedelta(weeks=2)).isoformat(),
                        },
                    },
                )
            )
            r4 = len(
                await db.security_events.distinct(
                    "user_id",
                    {
                        "user_id": {"$in": users},
                        "event_type": "login_success",
                        "timestamp": {
                            "$gte": (we + timedelta(weeks=3)).isoformat(),
                            "$lt": (we + timedelta(weeks=4)).isoformat(),
                        },
                    },
                )
            )
            writer.writerow([ws.strftime("%b %d"), len(users), r1, r2, r4])
    else:
        writer.writerow(["Metric", "Value"])
        now = datetime.now(timezone.utc)
        total = await db.users.count_documents({})
        dau = len(
            await db.security_events.distinct(
                "user_id", {"timestamp": {"$gte": (now - timedelta(days=1)).isoformat()}, "event_type": "login_success"}
            )
        )
        wau = len(
            await db.security_events.distinct(
                "user_id", {"timestamp": {"$gte": (now - timedelta(days=7)).isoformat()}, "event_type": "login_success"}
            )
        )
        mau = len(
            await db.security_events.distinct(
                "user_id",
                {"timestamp": {"$gte": (now - timedelta(days=30)).isoformat()}, "event_type": "login_success"},
            )
        )
        for m, v in [("Total Users", total), ("DAU", dau), ("WAU", wau), ("MAU", mau)]:
            writer.writerow([m, v])

    from fastapi.responses import StreamingResponse

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=uba_{section}_{days}d.csv"},
    )


# Click tracking for heatmap / session replay
@router.post("/track-clicks")
async def track_clicks(req: Request, body: dict):
    """Collect click events from frontend for UBA heatmaps."""
    from routes.db import get_current_user

    user = await get_current_user(req)
    if not user:
        return {"ok": False}
    events = body.get("events", [])
    if events:
        docs = []
        for e in events[:50]:  # max 50 per batch
            docs.append(
                {
                    "user_id": user.user_id,
                    "page": e.get("page", ""),
                    "x": e.get("x", 0),
                    "y": e.get("y", 0),
                    "element": e.get("element", ""),
                    "viewport_w": e.get("viewport_w", 0),
                    "viewport_h": e.get("viewport_h", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        await db.uba_click_events.insert_many(docs)
    return {"ok": True, "tracked": len(events)}


@router.get("/click-heatmap")
async def uba_click_heatmap(
    req: Request, page_filter: str = Query("", alias="page"), days: int = Query(7, ge=1, le=30)
):
    """Get aggregated click heatmap data."""
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query: dict = {"timestamp": {"$gte": cutoff}}
    if page_filter:
        query["page"] = {"$regex": re.escape(str(page_filter)), "$options": "i"}

    # Aggregate clicks into grid cells (10px buckets)
    pipeline = [
        {"$match": query},
        {
            "$addFields": {
                "gx": {"$multiply": [{"$floor": {"$divide": ["$x", 20]}}, 20]},
                "gy": {"$multiply": [{"$floor": {"$divide": ["$y", 20]}}, 20]},
            }
        },
        {"$group": {"_id": {"page": "$page", "gx": "$gx", "gy": "$gy"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 500},
    ]
    cells = []
    async for doc in db.uba_click_events.aggregate(pipeline):
        cells.append({"page": doc["_id"]["page"], "x": doc["_id"]["gx"], "y": doc["_id"]["gy"], "count": doc["count"]})

    # Also get page breakdown
    pages_pipeline = [
        {"$match": query},
        {"$group": {"_id": "$page", "clicks": {"$sum": 1}, "users": {"$addToSet": "$user_id"}}},
        {"$addFields": {"unique_users": {"$size": "$users"}}},
        {"$project": {"page": "$_id", "clicks": 1, "unique_users": 1, "_id": 0}},
        {"$sort": {"clicks": -1}},
        {"$limit": 20},
    ]
    pages = [doc async for doc in db.uba_click_events.aggregate(pages_pipeline)]

    return {"cells": cells, "pages": pages, "total_clicks": await db.uba_click_events.count_documents(query)}
