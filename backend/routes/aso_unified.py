"""Unified ASO Dashboard — Cross-platform App Store Connect + Google Play comparison.

Scheduled weekly reports + on-demand dashboard.
All endpoints admin-only (enforced by /api/admin/* middleware).

Endpoints:
- GET  /api/admin/aso-unified/dashboard       — Live cross-platform overview
- GET  /api/admin/aso-unified/reports          — List of generated reports
- POST /api/admin/aso-unified/reports/generate — Trigger report generation now
- GET  /api/admin/aso-unified/reports/{id}     — Get a specific report

Keyword tracking and alerts are in aso_keywords.py and aso_alerts.py respectively.
"""

import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/aso-unified", tags=["Unified ASO Dashboard"])


async def _fetch_apple_data() -> dict:
    """Fetch live data from App Store Connect."""
    try:
        from routes.apple_api import fetch_app_store_data
        data = await fetch_app_store_data()
        return {"connected": True, "apps_count": data.get("app_count", 0), "data": data}
    except Exception as e:
        logger.warning(f"Apple API unavailable: {e}")
        cached = await db.aso_apple_cache.find_one({}, {"_id": 0}, sort=[("cached_at", -1)])
        return {"connected": False, "apps_count": cached.get("app_count", 0) if cached else 0, "data": cached}


async def _fetch_google_data() -> dict:
    """Fetch live data from Google Play Console."""
    try:
        from routes.google_play_api import fetch_google_play_data
        data = await fetch_google_play_data()
        return {"connected": True, "data": data}
    except Exception as e:
        logger.warning(f"Google Play API unavailable: {e}")
        cached = await db.aso_google_cache.find_one({}, {"_id": 0}, sort=[("cached_at", -1)])
        return {"connected": False, "data": cached}


async def generate_aso_report(trigger: str = "manual") -> dict:
    """Generate a cross-platform ASO report."""
    apple = await _fetch_apple_data()
    google = await _fetch_google_data()

    apple_connected = apple["connected"]
    google_connected = google["connected"]
    apple.get("data") or {}
    google.get("data") or {}

    # Keyword summary
    keywords = await db.aso_keywords.find({}, {"_id": 0}).to_list(200)
    keyword_summary = []
    for kw in keywords:
        keyword_summary.append({
            "keyword": kw["keyword"],
            "apple_rank": kw.get("apple", {}).get("rank", 0),
            "google_rank": kw.get("google", {}).get("rank", 0),
            "data_source": kw.get("data_source", "unknown"),
        })

    # Calculate overall health score
    score = 50
    if apple_connected:
        score += 10
    if google_connected:
        score += 10
    avg_apple = sum(k.get("apple_rank", 0) for k in keyword_summary if k.get("apple_rank")) or 0
    avg_google = sum(k.get("google_rank", 0) for k in keyword_summary if k.get("google_rank")) or 0
    ranked_kws = sum(1 for k in keyword_summary if k.get("apple_rank") or k.get("google_rank"))
    if ranked_kws > 0:
        avg_apple = avg_apple / ranked_kws
        avg_google = avg_google / ranked_kws
        if avg_apple < 50:
            score += 15
        elif avg_apple < 100:
            score += 10
        if avg_google < 50:
            score += 15
        elif avg_google < 100:
            score += 10

    recommendations = []
    if not apple_connected:
        recommendations.append({"type": "warning", "text": "App Store Connect API is disconnected."})
    if not google_connected:
        recommendations.append({"type": "warning", "text": "Google Play Console API is disconnected."})
    if len(keywords) < 5:
        recommendations.append({"type": "info", "text": f"Track more keywords (currently {len(keywords)}). Aim for 10-20."})
    if avg_apple > 100:
        recommendations.append({"type": "action", "text": "Improve App Store rankings — average position is above 100."})

    report = {
        "report_id": f"rpt_{uuid.uuid4().hex[:12]}",
        "generated_at": datetime.now(timezone.utc),
        "trigger": trigger,
        "overall_health_score": min(100, score),
        "platforms": {
            "apple": {"connected": apple_connected, "apps_count": apple.get("apps_count", 0)},
            "google": {"connected": google_connected},
        },
        "keyword_summary": keyword_summary,
        "keyword_count": len(keywords),
        "recommendations": recommendations,
    }
    await db.aso_unified_reports.insert_one({**report})
    report.pop("_id", None)
    report["generated_at"] = report["generated_at"].isoformat()
    return report


@router.get("/dashboard")
async def unified_dashboard(request: Request):
    """Live cross-platform ASO overview."""
    apple = await _fetch_apple_data()
    google = await _fetch_google_data()

    latest_report = await db.aso_unified_reports.find_one(
        {}, {"_id": 0}, sort=[("generated_at", -1)]
    )
    if latest_report and hasattr(latest_report.get("generated_at"), "isoformat"):
        latest_report["generated_at"] = latest_report["generated_at"].isoformat()

    total_reports = await db.aso_unified_reports.count_documents({})

    return {
        "live_status": {
            "apple": {"connected": apple["connected"], "apps_count": apple["apps_count"]},
            "google": {"connected": google["connected"]},
        },
        "total_reports": total_reports,
        "latest_report": latest_report,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/reports")
async def list_reports(request: Request, limit: int = Query(20, ge=1, le=100)):
    """List generated ASO reports."""
    reports = await db.aso_unified_reports.find(
        {}, {"_id": 0, "cached_google_reviews": 0, "cached_apple_sales": 0}
    ).sort("generated_at", -1).limit(limit).to_list(limit)
    return {"reports": reports, "count": len(reports)}


@router.post("/reports/generate")
async def trigger_report(request: Request):
    """Manually trigger an ASO report."""
    report = await generate_aso_report(trigger="manual")
    return report


@router.get("/reports/{report_id}")
async def get_report(request: Request, report_id: str):
    """Get a specific report by ID."""
    report = await db.aso_unified_reports.find_one(
        {"report_id": report_id}, {"_id": 0}
    )
    if not report:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Report not found"}, status_code=404)
    return report


async def scheduled_weekly_report():
    """Called by APScheduler weekly to auto-generate a report."""
    logger.info("Unified ASO: Generating scheduled weekly report...")
    try:
        report = await generate_aso_report(trigger="scheduled_weekly")
        logger.info(f"Unified ASO: Weekly report generated — ID={report['report_id']}, score={report['overall_health_score']}")

        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email="admin@realaicoach.app",
                template_key="admin_detailed_system_alert",
                title="Weekly ASO Report",
                intro=f"Overall Health Score: {report['overall_health_score']}%. Recommendations: {len(report['recommendations'])}.",
                rows=[("Report ID", report['report_id']), ("Health Score", f"{report['overall_health_score']}%"), ("Recommendations", str(len(report['recommendations'])))],
                accent="#3B82F6",
                status_label="WEEKLY",
                footer_note="Open the Admin Console to view the full report.",
            )
        except Exception as e:
            logger.warning(f"Unified ASO: Failed to send email: {e}")
    except Exception as e:
        logger.error(f"Unified ASO: Scheduled report failed: {e}")


def register(api_router, app):
    api_router.include_router(router)
    # IMPORTANT: Register alert_router BEFORE kw_router
    # because kw_router has /{keyword} dynamic routes that would shadow /alerts/*
    from routes.aso_alerts import router as alert_router
    from routes.aso_keywords import router as kw_router
    api_router.include_router(alert_router)
    api_router.include_router(kw_router)
