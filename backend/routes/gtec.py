"""
GTEC — Global Task Enforcement Center

Central brain + memory + monitoring system for RealAICoach platform.
Every production task execution is logged here to:
  - track regressions prevented
  - track fixes applied
  - prevent duplicate executions
  - provide real-time system diagnostics

Endpoints
  GET    /api/gtec/overview           — aggregate KPIs (admin)
  GET    /api/gtec/logs               — task-log feed with filters (admin)
  POST   /api/gtec/log                — append new task entry (admin/system)
  DELETE /api/gtec/logs/{task_id}     — remove a log row (admin)
  GET    /api/gtec/health             — real-time system diagnostics
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

GTEC_COL = "gtec_task_logs"


class GTECLogBody(BaseModel):
    task_id: Optional[str] = None
    title: str = Field(..., min_length=2, max_length=200)
    category: str = Field("feature", pattern="^(feature|bug_fix|enhancement|regression|ops|integration|guardrail|cleanup)$")
    status: str = Field("completed", pattern="^(completed|in_progress|rolled_back|blocked)$")
    actions_taken: List[str] = Field(default_factory=list)
    fixes_applied: List[str] = Field(default_factory=list)
    regressions_prevented: List[str] = Field(default_factory=list)
    files_touched: List[str] = Field(default_factory=list)
    pipeline: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    actor: str = "system"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/gtec/overview")
async def gtec_overview(request: Request):
    """Aggregate KPIs for the GTEC dashboard."""
    await require_admin(request)

    total = await db[GTEC_COL].count_documents({})
    completed = await db[GTEC_COL].count_documents({"status": "completed"})
    in_progress = await db[GTEC_COL].count_documents({"status": "in_progress"})
    rolled_back = await db[GTEC_COL].count_documents({"status": "rolled_back"})
    blocked = await db[GTEC_COL].count_documents({"status": "blocked"})

    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    last_24h = await db[GTEC_COL].count_documents({"created_at": {"$gte": cutoff_24h}})

    by_category: dict[str, int] = {}
    async for d in db[GTEC_COL].aggregate([
        {"$group": {"_id": "$category", "n": {"$sum": 1}}}
    ]):
        by_category[d.get("_id") or "other"] = int(d.get("n") or 0)

    regressions_prevented = 0
    fixes_applied = 0
    async for d in db[GTEC_COL].find({}, {"_id": 0, "regressions_prevented": 1, "fixes_applied": 1}):
        regressions_prevented += len(d.get("regressions_prevented") or [])
        fixes_applied += len(d.get("fixes_applied") or [])

    latest = None
    async for d in db[GTEC_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(1):
        latest = d

    return {
        "kpis": {
            "total_tasks": total,
            "completed": completed,
            "in_progress": in_progress,
            "rolled_back": rolled_back,
            "blocked": blocked,
            "last_24h": last_24h,
            "regressions_prevented": regressions_prevented,
            "fixes_applied": fixes_applied,
        },
        "by_category": by_category,
        "latest": latest,
        "generated_at": _now_iso(),
    }


@router.get("/gtec/logs")
async def gtec_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    category: Optional[str] = None,
    status: Optional[str] = None,
):
    await require_admin(request)
    q: dict[str, Any] = {}
    if category:
        q["category"] = category
    if status:
        q["status"] = status
    items: list[dict[str, Any]] = []
    async for d in db[GTEC_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.post("/gtec/log")
async def gtec_log(request: Request, body: GTECLogBody):
    await require_admin(request)
    task_id = body.task_id or f"gtec_{uuid.uuid4().hex[:12]}"
    # de-duplicate explicit task_ids
    existing = await db[GTEC_COL].find_one({"task_id": task_id}, {"_id": 0, "task_id": 1})
    if existing:
        raise HTTPException(status_code=409, detail=f"task_id {task_id} already exists — use a new id or DELETE first")
    doc = {
        "task_id": task_id,
        "title": body.title,
        "category": body.category,
        "status": body.status,
        "actions_taken": body.actions_taken,
        "fixes_applied": body.fixes_applied,
        "regressions_prevented": body.regressions_prevented,
        "files_touched": body.files_touched,
        "pipeline": body.pipeline,
        "notes": body.notes,
        "actor": body.actor,
        "created_at": _now_iso(),
    }
    await db[GTEC_COL].insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "task": doc}


@router.delete("/gtec/logs/{task_id}")
async def gtec_delete_log(request: Request, task_id: str):
    await require_admin(request)
    res = await db[GTEC_COL].delete_one({"task_id": task_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="task_id not found")
    return {"ok": True, "deleted": task_id}


@router.get("/gtec/health")
async def gtec_health(request: Request):
    """Real-time diagnostics for the GTEC monitoring panel."""
    await require_admin(request)
    # DB ping
    db_ok = True
    db_err: Optional[str] = None
    try:
        await db.command("ping")
    except Exception as e:
        db_ok = False
        db_err = str(e)[:160]

    # freshness: is the latest task log within 30 days?
    freshness_ok = False
    latest_ts: Optional[str] = None
    async for d in db[GTEC_COL].find({}, {"_id": 0, "created_at": 1}).sort("created_at", -1).limit(1):
        latest_ts = d.get("created_at")
    if latest_ts:
        try:
            ts = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
            freshness_ok = (datetime.now(timezone.utc) - ts) < timedelta(days=30)
        except Exception:
            freshness_ok = False

    # collection counts for system-wide sanity
    careers_apps = await db["careers_applications"].count_documents({})
    gtec_rows = await db[GTEC_COL].count_documents({})

    checks = [
        {"id": "db_ping", "ok": db_ok, "detail": db_err or "MongoDB reachable"},
        {"id": "log_freshness", "ok": freshness_ok or gtec_rows == 0, "detail": latest_ts or "no-entries-yet"},
        {"id": "gtec_collection", "ok": True, "detail": f"{gtec_rows} task rows"},
        {"id": "careers_collection", "ok": True, "detail": f"{careers_apps} applications"},
    ]
    overall = "pass" if all(c["ok"] for c in checks) else "warning"

    return {
        "overall": overall,
        "checks": checks,
        "last_task_at": latest_ts,
        "generated_at": _now_iso(),
    }
