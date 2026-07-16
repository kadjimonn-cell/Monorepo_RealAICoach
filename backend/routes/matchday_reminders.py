"""
Matchday Reminder Preferences — Weekly + 15-minute pre-match controls across leagues
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from routes.db import db as _singleton_db

router = APIRouter(prefix="/matchday-reminders", tags=["matchday-reminders"])

def get_db():
    return _singleton_db

SUPPORTED_LEAGUES = [
    {"id": "epl", "name": "English Premier League", "country": "England", "sport": "football"},
    {"id": "laliga", "name": "La Liga", "country": "Spain", "sport": "football"},
    {"id": "bundesliga", "name": "Bundesliga", "country": "Germany", "sport": "football"},
    {"id": "seriea", "name": "Serie A", "country": "Italy", "sport": "football"},
    {"id": "ligue1", "name": "Ligue 1", "country": "France", "sport": "football"},
    {"id": "ucl", "name": "UEFA Champions League", "country": "Europe", "sport": "football"},
    {"id": "uel", "name": "UEFA Europa League", "country": "Europe", "sport": "football"},
    {"id": "mls", "name": "Major League Soccer", "country": "USA", "sport": "football"},
    {"id": "nba", "name": "NBA", "country": "USA", "sport": "basketball"},
    {"id": "nfl", "name": "NFL", "country": "USA", "sport": "american_football"},
    {"id": "mlb", "name": "MLB", "country": "USA", "sport": "baseball"},
    {"id": "nhl", "name": "NHL", "country": "USA", "sport": "ice_hockey"},
    {"id": "ipl", "name": "Indian Premier League", "country": "India", "sport": "cricket"},
    {"id": "f1", "name": "Formula 1", "country": "International", "sport": "motorsport"},
    {"id": "ufc", "name": "UFC", "country": "International", "sport": "mma"},
    {"id": "atp", "name": "ATP Tour", "country": "International", "sport": "tennis"},
    {"id": "wta", "name": "WTA Tour", "country": "International", "sport": "tennis"},
    {"id": "afcon", "name": "Africa Cup of Nations", "country": "Africa", "sport": "football"},
    {"id": "copa", "name": "Copa America", "country": "South America", "sport": "football"},
    {"id": "wc", "name": "FIFA World Cup", "country": "International", "sport": "football"},
]

DEFAULT_PREFS = {
    "global_enabled": True,
    "weekly_digest": True,
    "weekly_digest_day": "friday",
    "weekly_digest_time": "09:00",
    "pre_match_15m": True,
    "pre_match_1h": False,
    "pre_match_24h": True,
    "post_match_results": True,
    "delivery_channels": {"in_app": True, "push": True, "email": False},
    "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"},
}

class ReminderPrefsUpdate(BaseModel):
    user_id: str
    global_enabled: Optional[bool] = None
    weekly_digest: Optional[bool] = None
    weekly_digest_day: Optional[str] = None
    weekly_digest_time: Optional[str] = None
    pre_match_15m: Optional[bool] = None
    pre_match_1h: Optional[bool] = None
    pre_match_24h: Optional[bool] = None
    post_match_results: Optional[bool] = None
    delivery_channels: Optional[dict] = None
    quiet_hours: Optional[dict] = None

class LeagueToggle(BaseModel):
    user_id: str
    league_id: str
    enabled: bool

@router.get("/leagues")
async def get_supported_leagues():
    return {"leagues": SUPPORTED_LEAGUES, "total": len(SUPPORTED_LEAGUES)}

@router.get("/prefs/{user_id}")
async def get_reminder_prefs(user_id: str):
    db = get_db()
    prefs = await db.matchday_reminder_prefs.find_one({"user_id": user_id}, {"_id": 0})
    merged = {**DEFAULT_PREFS, "league_subscriptions": {}, **(prefs or {}), "user_id": user_id}
    return {"preferences": merged}

@router.post("/prefs")
async def update_reminder_prefs(req: ReminderPrefsUpdate):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {}
    for field in ["global_enabled", "weekly_digest", "weekly_digest_day", "weekly_digest_time",
                   "pre_match_15m", "pre_match_1h", "pre_match_24h", "post_match_results",
                   "delivery_channels", "quiet_hours"]:
        val = getattr(req, field, None)
        if val is not None:
            update_fields[field] = val
    update_fields["updated_at"] = now
    await db.matchday_reminder_prefs.update_one(
        {"user_id": req.user_id},
        {"$set": update_fields, "$setOnInsert": {"created_at": now, "league_subscriptions": {}}},
        upsert=True,
    )
    prefs = await db.matchday_reminder_prefs.find_one({"user_id": req.user_id}, {"_id": 0})
    return {"status": "updated", "preferences": prefs}

@router.post("/league/toggle")
async def toggle_league_subscription(req: LeagueToggle):
    db = get_db()
    valid_ids = {league["id"] for league in SUPPORTED_LEAGUES}
    if req.league_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown league: {req.league_id}")
    now = datetime.now(timezone.utc).isoformat()
    await db.matchday_reminder_prefs.update_one(
        {"user_id": req.user_id},
        {"$set": {f"league_subscriptions.{req.league_id}": req.enabled, "updated_at": now},
         "$setOnInsert": {"created_at": now, **DEFAULT_PREFS}},
        upsert=True,
    )
    return {"status": "toggled", "league_id": req.league_id, "enabled": req.enabled}

@router.get("/league/subscriptions/{user_id}")
async def get_league_subscriptions(user_id: str):
    db = get_db()
    prefs = await db.matchday_reminder_prefs.find_one({"user_id": user_id}, {"_id": 0, "league_subscriptions": 1})
    subs = prefs.get("league_subscriptions", {}) if prefs else {}
    result = []
    for league in SUPPORTED_LEAGUES:
        result.append({**league, "subscribed": subs.get(league["id"], False)})
    return {"leagues": result, "subscribed_count": sum(1 for v in subs.values() if v)}

@router.post("/bulk-toggle")
async def bulk_toggle_leagues(user_id: str = Body(...), league_ids: list = Body(...), enabled: bool = Body(True)):
    db = get_db()
    valid_ids = {league["id"] for league in SUPPORTED_LEAGUES}
    updates = {}
    for lid in league_ids:
        if lid in valid_ids:
            updates[f"league_subscriptions.{lid}"] = enabled
    if not updates:
        raise HTTPException(status_code=400, detail="No valid league IDs")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.matchday_reminder_prefs.update_one(
        {"user_id": user_id},
        {"$set": updates, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat(), **DEFAULT_PREFS}},
        upsert=True,
    )
    return {"status": "bulk_toggled", "count": len(league_ids), "enabled": enabled}

@router.get("/admin/stats")
async def admin_reminder_stats():
    db = get_db()
    total_users = await db.matchday_reminder_prefs.count_documents({})
    enabled = await db.matchday_reminder_prefs.count_documents({"global_enabled": True})
    weekly_on = await db.matchday_reminder_prefs.count_documents({"weekly_digest": True})
    pre_15m_on = await db.matchday_reminder_prefs.count_documents({"pre_match_15m": True})
    pipeline = [
        {"$project": {"subs": {"$objectToArray": "$league_subscriptions"}}},
        {"$unwind": "$subs"},
        {"$match": {"subs.v": True}},
        {"$group": {"_id": "$subs.k", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    league_pop = await db.matchday_reminder_prefs.aggregate(pipeline).to_list(30)
    return {
        "total_users": total_users, "global_enabled": enabled,
        "weekly_digest_on": weekly_on, "pre_match_15m_on": pre_15m_on,
        "league_popularity": [
            {
                **league_popularity,
                "league_name": next(
                    (
                        league["name"]
                        for league in SUPPORTED_LEAGUES
                        if league["id"] == league_popularity["_id"]
                    ),
                    league_popularity["_id"],
                ),
            }
            for league_popularity in league_pop
        ],
    }
