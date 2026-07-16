"""Customizable Dashboard Layout — save and load user dashboard widget preferences."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone
from routes.db import db, get_current_user
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard Layout"])

# Default widget layouts for different dashboard types
DEFAULT_LAYOUTS = {
    "executive": [
        {"id": "security_score", "title": "Security Score", "visible": True, "order": 0, "size": "md"},
        {"id": "kpi_overview", "title": "KPI Overview", "visible": True, "order": 1, "size": "lg"},
        {"id": "user_growth", "title": "User Growth", "visible": True, "order": 2, "size": "md"},
        {"id": "revenue_summary", "title": "Revenue Summary", "visible": True, "order": 3, "size": "md"},
        {"id": "ai_usage", "title": "AI Usage", "visible": True, "order": 4, "size": "md"},
        {"id": "active_sessions", "title": "Active Sessions", "visible": True, "order": 5, "size": "sm"},
        {"id": "recent_activity", "title": "Recent Activity", "visible": True, "order": 6, "size": "lg"},
        {"id": "system_health", "title": "System Health", "visible": True, "order": 7, "size": "sm"},
    ],
    "admin": [
        {"id": "quick_stats", "title": "Quick Stats", "visible": True, "order": 0, "size": "lg"},
        {"id": "alerts", "title": "Active Alerts", "visible": True, "order": 1, "size": "md"},
        {"id": "recent_tickets", "title": "Recent Tickets", "visible": True, "order": 2, "size": "md"},
        {"id": "security_overview", "title": "Security Overview", "visible": True, "order": 3, "size": "md"},
        {"id": "performance", "title": "System Performance", "visible": True, "order": 4, "size": "md"},
    ],
}


@router.get("/layout/{dashboard_type}")
async def get_layout(dashboard_type: str, req: Request):
    """Get the user's saved dashboard layout or return defaults."""
    user = await get_current_user(req)
    if not user:
        return {"layout": DEFAULT_LAYOUTS.get(dashboard_type, []), "is_default": True}

    saved = await db.dashboard_layouts.find_one(
        {"user_id": user.user_id, "dashboard_type": dashboard_type},
        {"_id": 0},
    )
    if saved:
        return {"layout": saved.get("widgets", []), "is_default": False, "updated_at": saved.get("updated_at")}

    return {"layout": DEFAULT_LAYOUTS.get(dashboard_type, []), "is_default": True}


@router.post("/layout/{dashboard_type}")
async def save_layout(dashboard_type: str, req: Request, body: dict):
    """Save the user's dashboard widget layout."""
    user = await get_current_user(req)
    if not user:
        return {"ok": False, "error": "Not authenticated"}

    widgets = body.get("widgets", [])
    if not isinstance(widgets, list):
        return {"ok": False, "error": "widgets must be a list"}

    # Validate widget data
    clean_widgets = []
    for w in widgets:
        clean_widgets.append(
            {
                "id": w.get("id", ""),
                "title": w.get("title", ""),
                "visible": w.get("visible", True),
                "order": w.get("order", 0),
                "size": w.get("size", "md"),
            }
        )

    await db.dashboard_layouts.update_one(
        {"user_id": user.user_id, "dashboard_type": dashboard_type},
        {
            "$set": {
                "widgets": clean_widgets,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    return {"ok": True, "widgets": clean_widgets}


@router.post("/layout/{dashboard_type}/reset")
async def reset_layout(dashboard_type: str, req: Request):
    """Reset dashboard layout to defaults."""
    user = await get_current_user(req)
    if not user:
        return {"ok": False, "error": "Not authenticated"}

    await db.dashboard_layouts.delete_one({"user_id": user.user_id, "dashboard_type": dashboard_type})

    return {"ok": True, "layout": DEFAULT_LAYOUTS.get(dashboard_type, [])}
