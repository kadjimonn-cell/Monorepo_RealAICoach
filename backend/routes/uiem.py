"""
UIEM — UI Enforcement Middleware Backend
Receives violation logs from the frontend UIEM system and provides
a dashboard API for viewing enforcement violations.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/uiem")

UIEM_VIOLATIONS_COLLECTION = "uiem_violations"
UIEM_CONFIG_COLLECTION = "uiem_config"


async def _get_db():
    from routes.db import db
    return db


@router.post("/log")
async def log_violation(request: Request):
    """Receive a UIEM violation log from the frontend."""
    body = await request.json()
    db = await _get_db()

    violations = body.get("violations", [body] if "component" in body else [])
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for v in violations[:50]:
        doc = {
            "component": v.get("component", "unknown"),
            "layer": v.get("layer", "unknown"),
            "error_type": v.get("error_type", "unknown"),
            "message": v.get("message", ""),
            "severity": v.get("severity", "warn"),
            "pathname": v.get("pathname", ""),
            "user_agent": str(request.headers.get("user-agent", ""))[:200],
            "created_at": now,
            "resolved": False,
        }
        await db[UIEM_VIOLATIONS_COLLECTION].insert_one(
            {k: v for k, v in doc.items() if k != "_id"}
        )
        inserted += 1

    if inserted > 0:
        logger.warning(f"[UIEM] Logged {inserted} violation(s)")
        # Dispatch Slack/Teams webhook alert for high/critical violations
        try:
            from services.webhook_alerts import send_alert
            crit = [v for v in violations[:50] if str(v.get("severity", "warn")).lower() in ("error", "critical", "fatal")]
            if crit:
                sample = crit[0]
                await send_alert(
                    event_type="uiem_violation",
                    severity="critical",
                    title=f"UIEM: {len(crit)} critical violation(s)",
                    summary=f"Component `{sample.get('component', 'unknown')}` triggered `{sample.get('error_type', 'unknown')}` on `{sample.get('pathname', '')}`.",
                    fields={
                        "Component": sample.get("component", "unknown"),
                        "Error Type": sample.get("error_type", "unknown"),
                        "Pathname": sample.get("pathname", ""),
                        "Message": (sample.get("message") or "")[:200],
                        "Total": len(crit),
                    },
                    url=None,
                )
        except Exception as _e:
            logger.debug(f"[UIEM] webhook alert dispatch skipped: {_e}")

    return {"ok": True, "logged": inserted}


@router.get("/violations")
async def list_violations(request: Request, limit: int = 50, layer: str = "", resolved: str = "false"):
    """List UIEM violations for the admin dashboard."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    query = {}
    if layer:
        query["layer"] = layer
    if resolved == "false":
        query["resolved"] = False
    elif resolved == "true":
        query["resolved"] = True

    cursor = db[UIEM_VIOLATIONS_COLLECTION].find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    violations = await cursor.to_list(length=limit)

    total = await db[UIEM_VIOLATIONS_COLLECTION].count_documents(query)

    # Aggregate by layer
    pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$layer", "count": {"$sum": 1}}},
    ]
    layer_counts_raw = await db[UIEM_VIOLATIONS_COLLECTION].aggregate(pipeline).to_list(10)
    layer_counts = {item["_id"]: item["count"] for item in layer_counts_raw}

    return {
        "violations": violations,
        "total": total,
        "by_layer": layer_counts,
        "filter": {"layer": layer, "resolved": resolved},
    }


@router.get("/summary")
async def uiem_summary(request: Request):
    """Compact summary for dashboard widgets."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()

    total_open = await db[UIEM_VIOLATIONS_COLLECTION].count_documents({"resolved": False})
    total_resolved = await db[UIEM_VIOLATIONS_COLLECTION].count_documents({"resolved": True})

    pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$layer", "count": {"$sum": 1}}},
    ]
    layer_counts_raw = await db[UIEM_VIOLATIONS_COLLECTION].aggregate(pipeline).to_list(10)
    by_layer = {item["_id"]: item["count"] for item in layer_counts_raw}

    severity_pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    severity_raw = await db[UIEM_VIOLATIONS_COLLECTION].aggregate(severity_pipeline).to_list(10)
    by_severity = {item["_id"]: item["count"] for item in severity_raw}

    # Get config
    config = await db[UIEM_CONFIG_COLLECTION].find_one({"kind": "global"}, {"_id": 0}) or {}

    return {
        "enforcement_active": config.get("active", True),
        "mode": config.get("mode", "enforcing"),
        "total_open": total_open,
        "total_resolved": total_resolved,
        "by_layer": by_layer,
        "by_severity": by_severity,
    }


@router.post("/resolve")
async def resolve_violations(request: Request):
    """Bulk-resolve violations by IDs or all."""
    from routes.db import require_admin
    await require_admin(request)

    body = await request.json()
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    if body.get("all"):
        result = await db[UIEM_VIOLATIONS_COLLECTION].update_many(
            {"resolved": False},
            {"$set": {"resolved": True, "resolved_at": now}},
        )
        return {"ok": True, "resolved": result.modified_count}

    components = body.get("components", [])
    if components:
        result = await db[UIEM_VIOLATIONS_COLLECTION].update_many(
            {"component": {"$in": components}, "resolved": False},
            {"$set": {"resolved": True, "resolved_at": now}},
        )
        return {"ok": True, "resolved": result.modified_count}

    return {"ok": False, "message": "Provide 'all' or 'components' list"}


@router.post("/config")
async def update_uiem_config(request: Request):
    """Update UIEM global configuration."""
    from routes.db import require_admin
    await require_admin(request)

    body = await request.json()
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    update = {"kind": "global", "updated_at": now}
    for key in ["active", "mode", "design_validation", "data_validation", "state_validation", "performance_validation"]:
        if key in body:
            update[key] = body[key]

    await db[UIEM_CONFIG_COLLECTION].update_one(
        {"kind": "global"}, {"$set": update}, upsert=True
    )

    config = await db[UIEM_CONFIG_COLLECTION].find_one({"kind": "global"}, {"_id": 0})
    return {"ok": True, "config": config}
