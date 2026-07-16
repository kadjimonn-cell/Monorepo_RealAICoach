"""App Store Connect Routes — Real Apple App Store data integration.

Endpoints:
- GET  /api/admin/appstore/status     — Connection status
- GET  /api/admin/appstore/apps       — List all apps
- GET  /api/admin/appstore/apps/{id}  — App detail + versions
- GET  /api/admin/appstore/sales      — Sales report
- GET  /api/admin/appstore/finance    — Finance report
- GET  /api/admin/appstore/dashboard  — Combined dashboard data
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query
from typing import Optional

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/appstore", tags=["App Store Connect"])


@router.get("/status")
async def appstore_status(request: Request):
    """Test App Store Connect API connection."""
    from services.appstore_connect import get_connection_status
    status = await get_connection_status()
    # Cache the result
    status_doc = {**status, "checked_at": datetime.now(timezone.utc)}
    await db.appstore_status.replace_one({"_id": "latest"}, {**status_doc, "_id": "latest"}, upsert=True)
    status_doc.pop("_id", None)
    return status_doc


@router.get("/apps")
async def list_apps(request: Request):
    """List all apps from App Store Connect."""
    from services.appstore_connect import list_apps as _list
    apps = await _list()
    return {"apps": apps, "count": len(apps), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/apps/{app_id}")
async def get_app_detail(request: Request, app_id: str):
    """Get app details including versions."""
    from services.appstore_connect import get_app_info, get_app_versions
    info = await get_app_info(app_id)
    versions = await get_app_versions(app_id)
    return {"app": info, "versions": versions, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/sales")
async def get_sales(
    request: Request,
    vendor_number: str = Query(..., description="Vendor number from App Store Connect"),
    frequency: str = Query("DAILY", description="DAILY, WEEKLY, or MONTHLY"),
    report_date: Optional[str] = Query(None, description="YYYY-MM-DD for daily, YYYY-MM for monthly"),
):
    """Fetch sales/trends report."""
    from services.appstore_connect import get_sales_report
    result = await get_sales_report(vendor_number, frequency, report_date)
    # Store in DB for history
    if result.get("status") == "ok":
        doc = {**result, "fetched_at": datetime.now(timezone.utc)}
        doc.pop("_id", None)
        await db.appstore_sales.insert_one(doc)
        doc.pop("_id", None)
    return result


@router.get("/finance")
async def get_finance(
    request: Request,
    vendor_number: str = Query(..., description="Vendor number from App Store Connect"),
    region_code: str = Query("US", description="Region code e.g. US, EU, JP"),
    report_date: Optional[str] = Query(None, description="YYYY-MM"),
):
    """Fetch finance report."""
    from services.appstore_connect import get_finance_report
    result = await get_finance_report(vendor_number, region_code, report_date)
    if result.get("status") == "ok":
        doc = {**result, "fetched_at": datetime.now(timezone.utc)}
        doc.pop("_id", None)
        await db.appstore_finance.insert_one(doc)
        doc.pop("_id", None)
    return result


@router.get("/dashboard")
async def appstore_dashboard(request: Request):
    """Combined App Store dashboard — apps, connection status, cached sales."""
    from services.appstore_connect import get_connection_status, list_apps as _list

    status = await get_connection_status()
    apps = await _list() if status.get("connected") else []

    # Get recent sales from cache
    recent_sales = await db.appstore_sales.find(
        {}, {"_id": 0}
    ).sort("fetched_at", -1).limit(5).to_list(5)
    for s in recent_sales:
        if hasattr(s.get("fetched_at"), "isoformat"):
            s["fetched_at"] = s["fetched_at"].isoformat()

    return {
        "connection": status,
        "apps": apps,
        "recent_sales": recent_sales,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
