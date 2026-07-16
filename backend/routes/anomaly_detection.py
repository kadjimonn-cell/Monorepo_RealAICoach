"""Anomaly Detection API — Aggregates auto-fix engine data into trend visualizations."""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/anomaly-detection", tags=["anomaly-detection"])


def get_db():
    from server import db
    return db


@router.get("/trends")
async def get_anomaly_trends(days: int = 7, db=Depends(get_db)):
    """Return issue/fix trends per domain over the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {
                "domain": "$domain",
                "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}
            },
            "total_issues": {"$sum": "$issues_found"},
            "total_fixes": {"$sum": "$fixes_applied"},
            "runs": {"$sum": 1},
        }},
        {"$sort": {"_id.day": 1}},
    ]
    try:
        results = await db["auto_fix_runs"].aggregate(pipeline).to_list(length=500)
    except Exception:
        results = []

    # Reshape into {domain: [{day, issues, fixes, runs}, ...]}
    by_domain: dict = {}
    for r in results:
        d = r["_id"]["domain"]
        by_domain.setdefault(d, []).append({
            "day": r["_id"]["day"],
            "issues": r["total_issues"],
            "fixes": r["total_fixes"],
            "runs": r["runs"],
        })

    return {"trends": by_domain, "period_days": days}


@router.get("/hotspots")
async def get_anomaly_hotspots(db=Depends(get_db)):
    """Return the top domains with the most issues in the last 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$domain",
            "total_issues": {"$sum": "$issues_found"},
            "total_fixes": {"$sum": "$fixes_applied"},
            "last_run": {"$max": "$timestamp"},
            "runs": {"$sum": 1},
        }},
        {"$sort": {"total_issues": -1}},
        {"$limit": 20},
    ]
    try:
        results = await db["auto_fix_runs"].aggregate(pipeline).to_list(length=20)
    except Exception:
        results = []

    hotspots = []
    for r in results:
        hotspots.append({
            "domain": r["_id"],
            "issues": r["total_issues"],
            "fixes": r["total_fixes"],
            "runs": r["runs"],
            "last_run": r["last_run"].isoformat() if r.get("last_run") else None,
            "fix_rate": round(r["total_fixes"] / max(r["total_issues"], 1) * 100, 1),
        })

    return {"hotspots": hotspots}


@router.get("/summary")
async def get_anomaly_summary(db=Depends(get_db)):
    """Aggregate summary: total issues/fixes across all time, plus last 24h and 7d."""
    now = datetime.now(timezone.utc)
    h24 = now - timedelta(hours=24)
    d7 = now - timedelta(days=7)

    async def count_period(since):
        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "issues": {"$sum": "$issues_found"},
                "fixes": {"$sum": "$fixes_applied"},
                "runs": {"$sum": 1},
                "domains": {"$addToSet": "$domain"},
            }},
        ]
        try:
            results = await db["auto_fix_runs"].aggregate(pipeline).to_list(length=1)
            if results:
                r = results[0]
                return {"issues": r["issues"], "fixes": r["fixes"], "runs": r["runs"], "active_domains": len(r["domains"])}
        except Exception:
            pass
        return {"issues": 0, "fixes": 0, "runs": 0, "active_domains": 0}

    last_24h = await count_period(h24)
    last_7d = await count_period(d7)

    # Current domain statuses from auto-fix engine
    from routes.admin_autofix_engine import DOMAINS
    healthy = 0
    warning = 0
    critical = 0
    for key in DOMAINS:
        doc = await db["auto_fix_runs"].find_one({"domain": key}, sort=[("timestamp", -1)])
        if doc:
            if doc.get("issues_found", 0) == 0:
                healthy += 1
            elif doc.get("issues_found", 0) <= 5:
                warning += 1
            else:
                critical += 1
        else:
            healthy += 1

    return {
        "last_24h": last_24h,
        "last_7d": last_7d,
        "domain_health": {"healthy": healthy, "warning": warning, "critical": critical},
        "total_domains": len(DOMAINS),
    }


@router.get("/recent-events")
async def get_recent_events(limit: int = 30, db=Depends(get_db)):
    """Return the most recent auto-fix events for the activity feed."""
    try:
        cursor = db["auto_fix_runs"].find(
            {},
            {"_id": 0, "domain": 1, "action": 1, "issues_found": 1, "fixes_applied": 1, "timestamp": 1, "status": 1}
        ).sort("timestamp", -1).limit(limit)
        events = await cursor.to_list(length=limit)
        for e in events:
            if isinstance(e.get("timestamp"), datetime):
                e["timestamp"] = e["timestamp"].isoformat()
        return {"events": events}
    except Exception:
        return {"events": []}


@router.get("/alert-config")
async def get_alert_config(db=Depends(get_db)):
    """Get anomaly alert configuration."""
    from services.anomaly_digest import _get_config
    cfg = await _get_config(db)
    return {"config": cfg}


@router.put("/alert-config")
async def update_alert_config(body: dict, db=Depends(get_db)):
    """Update anomaly alert configuration."""
    from services.anomaly_digest import ALERT_CONFIG_COLLECTION, DEFAULT_CONFIG
    allowed_keys = set(DEFAULT_CONFIG.keys())
    update = {k: v for k, v in body.items() if k in allowed_keys}
    if not update:
        return {"error": "No valid fields to update"}
    await db[ALERT_CONFIG_COLLECTION].update_one(
        {"_id": "global"}, {"$set": update}, upsert=True
    )
    return {"success": True, "updated": list(update.keys())}


@router.get("/alert-history")
async def get_alert_history(limit: int = 20, db=Depends(get_db)):
    """Get recent alert digest history."""
    from services.anomaly_digest import ALERT_HISTORY_COLLECTION
    try:
        cursor = db[ALERT_HISTORY_COLLECTION].find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        history = await cursor.to_list(length=limit)
        for h in history:
            if isinstance(h.get("timestamp"), datetime):
                h["timestamp"] = h["timestamp"].isoformat()
        return {"history": history}
    except Exception:
        return {"history": []}


@router.post("/send-test-digest")
async def send_test_digest(db=Depends(get_db)):
    """Manually trigger a test digest email."""
    from services.anomaly_digest import send_daily_digest
    try:
        await send_daily_digest(db)
        return {"success": True, "message": "Test digest triggered"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/trigger-autofix")
async def trigger_autofix_from_anomaly(db=Depends(get_db)):
    """Manually trigger auto-fix sweep from anomaly detection."""
    try:
        from routes.admin_autofix_engine import scheduled_autofix_sweep
        await scheduled_autofix_sweep()
        return {"success": True, "message": "Auto-fix sweep triggered"}
    except Exception as e:
        return {"success": False, "error": str(e)}
