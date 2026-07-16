"""
Admin Content Integrity Audit — Real-time contamination alerts & content moderation
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body
from routes.db import db as _singleton_db

router = APIRouter(prefix="/admin/content-integrity", tags=["content-integrity"])

def get_db():
    return _singleton_db

FLAGGED_PATTERNS = [
    {"pattern": r"\b(visa\s*fraud|fake\s*documents?|forged)\b", "severity": "critical", "category": "fraud"},
    {"pattern": r"\b(illegal\s*immigration|smuggling|trafficking)\b", "severity": "critical", "category": "illegal_activity"},
    {"pattern": r"\b(guaranteed\s*approval|100%\s*success|we\s*guarantee)\b", "severity": "high", "category": "misleading_claims"},
    {"pattern": r"\b(buy\s*visa|purchase\s*passport|black\s*market)\b", "severity": "critical", "category": "fraud"},
    {"pattern": r"\b(hack|exploit|bypass\s*security|cheat)\b", "severity": "high", "category": "security_threat"},
    {"pattern": r"\b(spam|click\s*here|act\s*now|limited\s*offer)\b", "severity": "medium", "category": "spam"},
    {"pattern": r"\b(profanity_placeholder_1|profanity_placeholder_2)\b", "severity": "medium", "category": "profanity"},
]

@router.get("/dashboard")
async def integrity_dashboard():
    db = get_db()
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    # Audit stats
    total_alerts = await db.content_integrity_alerts.count_documents({})
    alerts_24h = await db.content_integrity_alerts.count_documents({"created_at": {"$gte": day_ago}})
    alerts_7d = await db.content_integrity_alerts.count_documents({"created_at": {"$gte": week_ago}})
    unresolved = await db.content_integrity_alerts.count_documents({"status": "open"})

    # By severity
    severity_pipeline = [
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    severity_dist = await db.content_integrity_alerts.aggregate(severity_pipeline).to_list(10)

    # By category
    category_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    category_dist = await db.content_integrity_alerts.aggregate(category_pipeline).to_list(20)

    # Content sources health
    coaching_count = await db.tv_coaching_sessions.count_documents({})
    quiz_count = await db.tv_quiz_results.count_documents({})
    lesson_count = await db.tv_lessons.count_documents({})

    # FPS Game integrity (Feature 22)
    gs_events = await db.fps_game_matches.count_documents({"created_at": {"$gte": week_ago}})

    return {
        "generated_at": now.isoformat(),
        "alerts": {"total": total_alerts, "last_24h": alerts_24h, "last_7d": alerts_7d, "unresolved": unresolved},
        "severity_distribution": {s["_id"]: s["count"] for s in severity_dist},
        "category_distribution": {c["_id"]: c["count"] for c in category_dist},
        "content_sources": {
            "coaching_sessions": coaching_count,
            "quiz_submissions": quiz_count,
            "lessons": lesson_count,
            "games_events_7d": gs_events,
        },
        "health_score": max(0, 100 - unresolved * 5),
    }

@router.post("/scan")
async def run_content_scan(scope: str = Body(default="all"), limit: int = Body(default=500)):
    """Run a content integrity scan across user-generated content"""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    alerts = []

    compiled = [(re.compile(fp["pattern"], re.IGNORECASE), fp) for fp in FLAGGED_PATTERNS]

    # Scan coaching messages
    if scope in ("all", "coaching"):
        messages = await db.tv_coaching_sessions.find(
            {"role": "user"}, {"_id": 0, "session_id": 1, "user_id": 1, "content": 1, "created_at": 1}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        for msg in messages:
            content = msg.get("content", "")
            for regex, fp in compiled:
                if regex.search(content):
                    alerts.append({
                        "source": "coaching", "user_id": msg.get("user_id"),
                        "session_id": msg.get("session_id"),
                        "severity": fp["severity"], "category": fp["category"],
                        "matched_pattern": fp["pattern"], "excerpt": content[:200],
                        "status": "open", "created_at": now,
                    })
                    break

    # Scan quiz answers (free-text if any)
    if scope in ("all", "quizzes"):
        await db.tv_quiz_results.find(
            {}, {"_id": 0, "user_id": 1, "quiz_id": 1, "submitted_at": 1}
        ).sort("submitted_at", -1).limit(limit).to_list(limit)
        # Quiz answers are index-based, no free text to scan — mark as clean
        pass

    # Scan challenge messages
    if scope in ("all", "challenges"):
        challenges = await db.tv_challenges.find(
            {}, {"_id": 0, "challenge_id": 1, "challenger_id": 1, "challenged_id": 1, "quiz_title": 1}
        ).limit(limit).to_list(limit)
        for ch in challenges:
            title = ch.get("quiz_title", "")
            for regex, fp in compiled:
                if regex.search(title):
                    alerts.append({
                        "source": "challenge", "user_id": ch.get("challenger_id"),
                        "challenge_id": ch.get("challenge_id"),
                        "severity": fp["severity"], "category": fp["category"],
                        "matched_pattern": fp["pattern"], "excerpt": title[:200],
                        "status": "open", "created_at": now,
                    })
                    break

    # Persist alerts
    if alerts:
        await db.content_integrity_alerts.insert_many(alerts)

    return {
        "scan_completed_at": now,
        "scope": scope,
        "items_scanned": limit,
        "alerts_generated": len(alerts),
        "alerts": alerts[:50],
    }

@router.get("/alerts")
async def get_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    if category:
        query["category"] = category
    alerts = await db.content_integrity_alerts.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    total = await db.content_integrity_alerts.count_documents(query)
    return {"alerts": alerts, "total": total}

@router.post("/alerts/resolve")
async def resolve_alert(alert_index: int = Body(...), resolution: str = Body(default="dismissed"), notes: str = Body(default="")):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    alerts = await db.content_integrity_alerts.find({"status": "open"}).sort("created_at", -1).to_list(200)
    if alert_index < 0 or alert_index >= len(alerts):
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = alerts[alert_index]
    await db.content_integrity_alerts.update_one(
        {"_id": alert["_id"]},
        {"$set": {"status": resolution, "resolved_at": now, "resolution_notes": notes}},
    )
    return {"status": "resolved", "resolution": resolution}

@router.post("/alerts/bulk-resolve")
async def bulk_resolve_alerts(severity: str = Body(...), resolution: str = Body(default="dismissed")):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.content_integrity_alerts.update_many(
        {"severity": severity, "status": "open"},
        {"$set": {"status": resolution, "resolved_at": now}},
    )
    return {"resolved_count": result.modified_count, "severity": severity}

@router.get("/games-station/audit")
async def games_station_audit():
    """Leverage existing games_station contamination detection"""
    db = get_db()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = await db.fps_game_matches.find(
        {"created_at": {"$gte": week_ago}},
        {"_id": 0, "user_id": 1, "score": 1, "won": 1, "duration_ms": 1}
    ).to_list(5000)

    by_user = {}
    for row in rows:
        uid = row.get("user_id", "anon")
        if uid not in by_user:
            by_user[uid] = {"events": 0, "avg_score": 0, "max_score": 0, "fast_high_score_hits": 0, "high_win_rate_hits": 0}
        b = by_user[uid]
        b["events"] += 1
        score = row.get("score", 0)
        b["avg_score"] += score
        b["max_score"] = max(b["max_score"], score)
        dur = row.get("duration_ms", 99999)
        if score >= 800 and dur < 5000:
            b["fast_high_score_hits"] += 1
        if row.get("won") and score >= 900:
            b["high_win_rate_hits"] += 1

    audit_rows = []
    contamination_alerts = []
    for uid, b in by_user.items():
        events = max(1, b["events"])
        avg = round(b["avg_score"] / events, 1)
        risk = min(45, b["fast_high_score_hits"] * 18) + min(35, b["high_win_rate_hits"] * 6) + (18 if b["max_score"] >= 1950 else 0)
        level = "critical" if risk >= 75 else "high" if risk >= 55 else "medium" if risk >= 30 else "low"
        row = {"user_id": uid, "events": events, "max_score": b["max_score"], "avg_score": avg, "risk_score": risk, "risk_level": level}
        audit_rows.append(row)
        if level in ("high", "critical"):
            contamination_alerts.append({"user_id": uid, "risk_level": level, "risk_score": risk, "reason": "Anomalous high-score velocity"})

    audit_rows.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_events": len(rows),
        "audit_rows": audit_rows[:50],
        "contamination_alerts": contamination_alerts,
        "summary": {
            "critical": sum(1 for r in audit_rows if r["risk_level"] == "critical"),
            "high": sum(1 for r in audit_rows if r["risk_level"] == "high"),
            "medium": sum(1 for r in audit_rows if r["risk_level"] == "medium"),
            "low": sum(1 for r in audit_rows if r["risk_level"] == "low"),
        },
    }
