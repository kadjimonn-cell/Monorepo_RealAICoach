"""Seed script — Populate MongoDB collections with initial data for all dashboard features.
Run: python -m scripts.seed_data
"""
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


async def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    # ── 1. Platform Stats (Home Dashboard hero) ──
    await db.platform_stats.update_one(
        {"key": "global"},
        {"$setOnInsert": {
            "key": "global",
            "active_users": 857262,
            "ai_sessions_today": 26,
            "performance_boost": 98,
            "global_coaches": 2856732,
            "ai_status": "online",
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    print("[seed] platform_stats: seeded")

    # ── 2. Platform Metrics (Enterprise Dashboard overview) ──
    await db.platform_metrics.update_one(
        {"key": "dashboard"},
        {"$setOnInsert": {
            "key": "dashboard",
            "api_requests_24h": 284391,
            "avg_response_ms": 42,
            "error_rate_pct": 0.12,
            "uptime_30d_pct": 99.97,
            "user_growth_monthly": [685, 720, 698, 755, 810, 790, 835, 870, 920, 950, 910, 980],
            "mrr_cents": 12745000,
            "arr_cents": 152940000,
            "regions": [
                {"name": "North America", "users": 3420, "percentage": 39},
                {"name": "Europe", "users": 2650, "percentage": 30},
                {"name": "Asia Pacific", "users": 1540, "percentage": 18},
                {"name": "Latin America", "users": 680, "percentage": 8},
                {"name": "Africa & ME", "users": 452, "percentage": 5},
            ],
            "peak_hour": "14:00 UTC",
            "avg_session_duration_min": 18.4,
            "bounce_rate_pct": 12.3,
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    print("[seed] platform_metrics: seeded")

    # ── 3. Feature Usage Stats (Enterprise Dashboard feature tab) ──
    features = [
        {"feature_id": "ai_career_coaching", "name": "AI Career Coaching", "sessions": 18420, "unique_users": 6230, "avg_duration": "14m", "satisfaction": 4.8, "category": "coaching", "monthly_trend": [1200, 1350, 1280, 1420, 1380, 1500, 1460, 1550, 1620, 1580, 1690, 1750]},
        {"feature_id": "goal_tracking", "name": "Goal Tracking", "sessions": 15890, "unique_users": 5670, "avg_duration": "8m", "satisfaction": 4.6, "category": "productivity", "monthly_trend": [1050, 1100, 1080, 1200, 1150, 1300, 1250, 1350, 1400, 1380, 1450, 1500]},
        {"feature_id": "analytics_dashboard", "name": "Analytics Dashboard", "sessions": 14200, "unique_users": 4890, "avg_duration": "12m", "satisfaction": 4.7, "category": "analytics", "monthly_trend": [950, 1000, 980, 1100, 1050, 1180, 1150, 1220, 1280, 1250, 1320, 1380]},
        {"feature_id": "ai_coaching_team", "name": "AI Coaching Team", "sessions": 12780, "unique_users": 4210, "avg_duration": "18m", "satisfaction": 4.9, "category": "ai", "monthly_trend": [850, 900, 880, 1000, 960, 1080, 1050, 1120, 1180, 1150, 1220, 1280]},
        {"feature_id": "learning_hub", "name": "Learning Hub", "sessions": 11430, "unique_users": 3950, "avg_duration": "22m", "satisfaction": 4.5, "category": "learning", "monthly_trend": [750, 800, 780, 900, 860, 960, 930, 1000, 1050, 1020, 1080, 1130]},
        {"feature_id": "team_collaboration", "name": "Team Collaboration", "sessions": 9870, "unique_users": 3120, "avg_duration": "16m", "satisfaction": 4.4, "category": "collaboration", "monthly_trend": [650, 700, 680, 780, 750, 840, 810, 880, 920, 900, 950, 990]},
        {"feature_id": "life_coach", "name": "Life Coach", "sessions": 8650, "unique_users": 2890, "avg_duration": "20m", "satisfaction": 4.8, "category": "coaching", "monthly_trend": [580, 620, 600, 700, 670, 740, 720, 780, 810, 790, 840, 870]},
        {"feature_id": "document_analyzer", "name": "Document Analyzer", "sessions": 7230, "unique_users": 2450, "avg_duration": "10m", "satisfaction": 4.3, "category": "ai", "monthly_trend": [480, 520, 500, 580, 560, 620, 600, 650, 680, 660, 710, 730]},
        {"feature_id": "resume_builder", "name": "Resume Builder", "sessions": 6890, "unique_users": 2210, "avg_duration": "25m", "satisfaction": 4.6, "category": "tools", "monthly_trend": [450, 480, 470, 540, 520, 580, 560, 610, 640, 620, 670, 690]},
        {"feature_id": "mock_interview", "name": "Mock Interview", "sessions": 5420, "unique_users": 1780, "avg_duration": "30m", "satisfaction": 4.7, "category": "practice", "monthly_trend": [350, 380, 370, 420, 400, 460, 440, 490, 510, 500, 540, 560]},
    ]
    for f in features:
        f["updated_at"] = now
        await db.feature_usage_stats.update_one(
            {"feature_id": f["feature_id"]},
            {"$setOnInsert": f},
            upsert=True,
        )
    print(f"[seed] feature_usage_stats: seeded {len(features)} features")

    # ── 4. Service Health (Enterprise Dashboard system tab) ──
    services = [
        {"service_id": "api_gateway", "name": "API Gateway", "status": "healthy", "uptime_pct": 99.99, "latency_ms": 8},
        {"service_id": "auth_service", "name": "Auth Service", "status": "healthy", "uptime_pct": 99.98, "latency_ms": 15},
        {"service_id": "ai_engine", "name": "AI Engine", "status": "healthy", "uptime_pct": 99.95, "latency_ms": 120},
        {"service_id": "database", "name": "Database", "status": "healthy", "uptime_pct": 99.99, "latency_ms": 3},
        {"service_id": "cache_layer", "name": "Cache Layer", "status": "healthy", "uptime_pct": 100.0, "latency_ms": 1},
        {"service_id": "email_service", "name": "Email Service", "status": "degraded", "uptime_pct": 98.7, "latency_ms": 450},
    ]
    for svc in services:
        svc["updated_at"] = now
        await db.service_health.update_one(
            {"service_id": svc["service_id"]},
            {"$setOnInsert": svc},
            upsert=True,
        )
    print(f"[seed] service_health: seeded {len(services)} services")

    # ── 5. Response time history (Enterprise Dashboard performance tab) ──
    await db.response_time_history.update_one(
        {"key": "weekly"},
        {"$setOnInsert": {
            "key": "weekly",
            "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "p50": [32, 35, 28, 42, 38, 25, 30],
            "p95": [120, 145, 98, 165, 130, 85, 110],
            "p99": [280, 320, 210, 380, 290, 180, 250],
            "updated_at": now,
        }},
        upsert=True,
    )
    print("[seed] response_time_history: seeded")

    # ── 6. Error breakdown (Enterprise Dashboard) ──
    errors = [
        {"type": "4xx Client Errors", "count": 342, "percentage": 68, "color": "#F59E0B"},
        {"type": "5xx Server Errors", "count": 89, "percentage": 18, "color": "#EF4444"},
        {"type": "Timeout Errors", "count": 45, "percentage": 9, "color": "#F97316"},
        {"type": "Rate Limited", "count": 28, "percentage": 5, "color": "#8B5CF6"},
    ]
    for err in errors:
        err["updated_at"] = now
        await db.error_breakdown.update_one(
            {"type": err["type"]},
            {"$setOnInsert": err},
            upsert=True,
        )
    print(f"[seed] error_breakdown: seeded {len(errors)} error types")

    # ── 7. Feature Gallery Metrics ──
    import hashlib
    import math
    STATUSES = ["active", "active", "active", "active", "beta", "active", "active", "active"]
    TRENDS = ["up", "up", "up", "stable", "up", "down", "up", "stable"]
    TIMES = ["2m ago", "5m ago", "12m ago", "1h ago", "3h ago", "30m ago", "8m ago", "45m ago"]
    phase_f_retired_feature_ids = {
        "global-jobs",
        "mobile-money",
        "marketplace",
        "digital-bank",
        "creator-exchange",
        "drama-box",
        "music-streaming",
        "invoice-generator",
        "content-studio",
        "analytics-reports",
    }
    feature_ids = [
        "ai-writer", "ai-chatbot", "ai-search", "ai-automations", "ai-cognitive",
        "medimate", "fitness", "pennypilot", "smartbuy", "travelpal",
        "ai-found-love", "smart-cars", "buy-smart-home", "ai-video", "ai-photo",
        "ai-speech", "ai-enterprise", "global-jobs", "mobile-money", "marketplace",
        "digital-bank", "creator-exchange", "drama-box", "music-streaming",
        "invoice-generator", "school-tutor",
    ]
    feature_ids = [fid for fid in feature_ids if fid not in phase_f_retired_feature_ids]
    for fid in feature_ids:
        s = int(hashlib.md5(fid.encode()).hexdigest()[:8], 16)
        usage = 800 + (s % 15000)
        active = max(100, usage // 3 + (s % 500))
        perf = 72 + (s % 28)
        pop = 1 + (s % 26)
        conf = 70 + (s % 30)
        trend_pct = round(2.0 + (s % 200) / 10.0, 1)
        sparkline = []
        for i in range(7):
            base = usage // 7
            variation = int(base * 0.3 * math.sin(s + i * 1.2))
            sparkline.append(max(10, base + variation + (i * int(base * 0.05))))
        doc = {
            "feature_id": fid,
            "usage_count": usage,
            "active_users": active,
            "performance_score": perf,
            "popularity_rank": pop,
            "confidence_score": conf,
            "status": STATUSES[s % len(STATUSES)],
            "last_updated": TIMES[s % len(TIMES)],
            "sparkline": sparkline,
            "trend": TRENDS[s % len(TRENDS)],
            "trend_pct": trend_pct if TRENDS[s % len(TRENDS)] != "down" else -trend_pct,
            "efficiency": 60 + (s % 40),
            "updated_at": now,
        }
        await db.feature_gallery_metrics.update_one(
            {"feature_id": fid}, {"$setOnInsert": doc}, upsert=True,
        )
    print(f"[seed] feature_gallery_metrics: seeded {len(feature_ids)} features")

    print("\n[seed] All collections seeded successfully!")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
