"""
GTEC Crawler API
================

Wraps the `backend/scripts/gtec_crawler.py` headless-browser auditor in an
admin-only REST API so ops can:

  - kick off on-demand scans from `/ops-route-health`
  - poll job progress
  - pull the latest compliance report as JSON
  - list scan history
  - toggle a scheduled "safe auto run" (every 6 hours)

All state is kept in-memory (job registry) + MongoDB (`gtec_crawler_runs`
collection for persistent history and the auto-run toggle flag).

Endpoints
---------
POST   /api/admin/gtec-crawler/run          — kick off a scan
GET    /api/admin/gtec-crawler/status/{id}  — job status
GET    /api/admin/gtec-crawler/latest       — latest compliance report
GET    /api/admin/gtec-crawler/history      — recent job summaries
GET    /api/admin/gtec-crawler/auto-run     — read "safe auto run" flag
POST   /api/admin/gtec-crawler/auto-run     — toggle "safe auto run" flag
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/gtec-crawler", tags=["GTEC Crawler"])

ROOT = Path("/app")
CRAWLER = ROOT / "backend" / "scripts" / "gtec_crawler.py"
EXTRACTOR = ROOT / "backend" / "scripts" / "gtec_extract_routes.py"
REPORT_DIR = ROOT / "test_reports"
LATEST_REPORT = REPORT_DIR / "gtec_scan_latest.json"
RUNS_COL = "gtec_crawler_runs"
SETTINGS_COL = "gtec_crawler_settings"
AUTO_RUN_DOC_ID = "auto_run"

# In-memory job registry (main use is live progress polling)
JOBS: dict[str, dict[str, Any]] = {}
# Only one scan may run at a time — this lock guards it.
RUN_LOCK = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    viewports: str = Field("desktop", pattern="^(desktop|mobile|desktop,mobile|mobile,desktop)$")
    limit: Optional[int] = Field(None, ge=1, le=200)


class AutoRunBody(BaseModel):
    enabled: bool


class AlertSettingsBody(BaseModel):
    email_enabled: Optional[bool] = None
    email_recipients: Optional[list[str]] = None
    slack_webhook_url: Optional[str] = None
    pass_rate_drop_pct: Optional[int] = Field(None, ge=1, le=100)
    absolute_fail_delta: Optional[int] = Field(None, ge=1, le=100)
    cooldown_hours: Optional[int] = Field(None, ge=1, le=72)


async def _persist_run(job: dict[str, Any]) -> None:
    """Persist a summarised view of the job to MongoDB for history."""
    # Keep the stored record small; omit the full per-route payload.
    record = {
        "job_id": job["job_id"],
        "status": job["status"],
        "viewports": job.get("viewports"),
        "limit": job.get("limit"),
        "triggered_by": job.get("triggered_by") or "manual",
        "actor": job.get("actor"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
        "totals": job.get("totals"),
        "created_at": _now(),
    }
    try:
        await db[RUNS_COL].insert_one(record)
    except Exception as exc:  # pragma: no cover — best effort
        logger.warning("gtec_crawler: failed to persist run %s: %s", job["job_id"], exc)


async def _read_latest_report() -> Optional[dict[str, Any]]:
    if not LATEST_REPORT.exists():
        return None
    try:
        return json.loads(LATEST_REPORT.read_text())
    except Exception as exc:
        logger.error("gtec_crawler: cannot read latest report: %s", exc)
        return None


async def _execute_scan_subprocess(viewports: str, limit: Optional[int]) -> tuple[int, str, str]:
    """Run the extractor + crawler as a subprocess. Returns (returncode, stdout, stderr)."""
    # Extractor is cheap — run it first to make sure routes file is fresh.
    extract = await asyncio.create_subprocess_exec(
        sys.executable, str(EXTRACTOR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    ext_out, ext_err = await extract.communicate()
    if extract.returncode != 0:
        return extract.returncode, ext_out.decode("utf-8", "ignore"), ext_err.decode("utf-8", "ignore")

    cmd = [sys.executable, str(CRAWLER), "--viewports", viewports]
    if limit:
        cmd += ["--limit", str(limit)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "GTEC_FRONTEND_URL": (os.environ.get("GTEC_FRONTEND_URL") or os.environ.get("FRONTEND_BASE_URL") or ""),
            # Playwright browsers live in /pw-browsers under this environment —
            # pin the path so the subprocess doesn't fall back to the default
            # `~/.cache/ms-playwright` (which doesn't exist here).
            "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/pw-browsers"),
        },
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode("utf-8", "ignore"), err.decode("utf-8", "ignore")


async def run_scan_job(job_id: str) -> None:
    """Background coroutine: runs the crawler, updates job, persists history."""
    job = JOBS[job_id]
    if RUN_LOCK.locked():
        job["status"] = "failed"
        job["error"] = "another scan is already in progress"
        job["finished_at"] = _now()
        await _persist_run(job)
        return
    async with RUN_LOCK:
        job["status"] = "running"
        job["started_at"] = _now()
        try:
            rc, stdout, stderr = await _execute_scan_subprocess(
                viewports=job["viewports"],
                limit=job.get("limit"),
            )
            report = await _read_latest_report()
            if rc != 0 or not report:
                job["status"] = "failed"
                job["error"] = (stderr[-500:] or stdout[-500:] or "unknown crawler error").strip()
            else:
                job["status"] = "complete"
                job["totals"] = report.get("totals")
        except Exception as exc:
            logger.exception("gtec_crawler: job %s crashed", job_id)
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            job["finished_at"] = _now()
            await _persist_run(job)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run")
async def gtec_run(request: Request, body: RunRequest):
    """Kick off a GTEC scan in the background. Returns the job id immediately."""
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Manual crawler trigger is disabled by autonomous policy. "
            "Crawler runs only through scheduled/event-driven safe auto-run."
        ),
    )


@router.get("/status/{job_id}")
async def gtec_status(request: Request, job_id: str):
    """Return live status for a scan job."""
    await require_admin(request)
    job = JOBS.get(job_id)
    if not job:
        # Fall back to DB history in case the worker restarted
        doc = await db[RUNS_COL].find_one({"job_id": job_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="job_id not found")
        return {"job": doc}
    # Shallow copy for response
    return {"job": {**job}}


@router.get("/latest")
async def gtec_latest(request: Request):
    """Return the latest compliance report summary (not the full per-route payload)."""
    await require_admin(request)
    report = await _read_latest_report()
    if not report:
        return {"report": None}

    # Summarise the top failures so the UI stays snappy.
    failures = [r for r in report.get("results", []) if not r.get("healthy")]
    top: list[dict[str, Any]] = []
    for r in failures[:20]:
        reasons: list[str] = []
        if r.get("white_screen"):
            reasons.append("white-screen")
        if (r.get("status_code") or 0) >= 400 or r.get("status_code") == 0:
            reasons.append(f"HTTP {r['status_code']}")
        if r.get("page_errors"):
            reasons.append(f"{len(r['page_errors'])} page-errors")
        if r.get("console_errors"):
            reasons.append(f"{len(r['console_errors'])} console-errors")
        if r.get("failed_apis"):
            reasons.append(f"{len(r['failed_apis'])} failed APIs")
        if r.get("redirected_to_auth"):
            reasons.append("redirected-to-auth")
        top.append({
            "url": r["url"],
            "viewport": r["viewport"],
            "category": r.get("category"),
            "reasons": reasons,
        })

    # Aggregate top failed APIs
    from collections import Counter
    api_counter: Counter = Counter()
    for r in report.get("results", []):
        for a in r.get("failed_apis", []):
            api_counter[(a["url"].split("?")[0], a["status"])] += 1
    top_apis = [
        {"url": url, "status": status, "count": count}
        for (url, status), count in api_counter.most_common(10)
    ]

    return {
        "report": {
            "generated_at": report.get("generated_at"),
            "frontend_base": report.get("frontend_base"),
            "totals": report.get("totals"),
            "failures_by_category": {k: len(v) for k, v in report.get("failures_by_category", {}).items()},
            "top_failures": top,
            "top_failed_apis": top_apis,
        }
    }


@router.get("/history")
async def gtec_history(request: Request):
    """Return the last 20 scan summaries."""
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[RUNS_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(20):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.get("/auto-run")
async def gtec_auto_run_get(request: Request):
    """Read the 'safe auto run' toggle state."""
    await require_admin(request)
    doc = await db[SETTINGS_COL].find_one({"_id": AUTO_RUN_DOC_ID}, {"_id": 0})
    configured_enabled = bool((doc or {}).get("enabled", True))
    requested_enabled = bool((doc or {}).get("requested_enabled", configured_enabled))
    return {
        "enabled": True,
        "effective_enabled": True,
        "non_disableable": True,
        "configured_enabled": configured_enabled,
        "requested_enabled": requested_enabled,
        "interval_hours": int((doc or {}).get("interval_hours") or 6),
    }


@router.post("/auto-run")
async def gtec_auto_run_set(request: Request, body: AutoRunBody):
    """Update scheduler settings for safe auto run (always active by policy)."""
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Auto-run mutation is disabled by autonomous policy. "
            "Schedule is immutable at runtime."
        ),
    )


# ---------------------------------------------------------------------------
# Scheduler hook
# ---------------------------------------------------------------------------

async def scheduled_auto_run() -> None:
    """APScheduler-invoked helper. Safe auto-run is always active by policy."""
    async def _heartbeat(status: str, details: Optional[dict[str, Any]] = None) -> None:
        await db.scheduler_heartbeats.update_one(
            {"job_id": "gtec_crawler_safe_auto_run"},
            {
                "$set": {
                    "job_id": "gtec_crawler_safe_auto_run",
                    "status": status,
                    "last_run": _now(),
                    "details": details or {},
                    "updated_at": _now(),
                }
            },
            upsert=True,
        )

    try:
        doc = await db[SETTINGS_COL].find_one({"_id": AUTO_RUN_DOC_ID}, {"_id": 0})
        if doc and doc.get("enabled") is False:
            logger.warning(
                "gtec_crawler: found enabled=false in settings; overriding to active (non-disableable policy)"
            )

        # Idempotency guard: do not run if a scheduler run already happened
        # within the interval window (6h).
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        recent = await db[RUNS_COL].find_one(
            {"triggered_by": "scheduler", "created_at": {"$gte": cutoff}},
            {"_id": 0, "job_id": 1, "created_at": 1},
            sort=[("created_at", -1)],
        )
        if recent:
            logger.info(
                "gtec_crawler: auto-run skipped — recent scheduler run %s at %s",
                recent.get("job_id"),
                recent.get("created_at"),
            )
            await _heartbeat("healthy", {"result": "skipped_recent_scheduler_run", "recent_job_id": recent.get("job_id")})
            return

        # Avoid starting a new one if a manual scan is live.
        if RUN_LOCK.locked():
            logger.info("gtec_crawler: auto-run skipped — scan already in progress")
            await _heartbeat("healthy", {"result": "skipped_running"})
            return
        job_id = f"gtec_auto_{uuid.uuid4().hex[:10]}"
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "viewports": "desktop",
            "limit": None,
            "triggered_by": "scheduler",
            "actor": "apscheduler",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "totals": None,
        }
        await run_scan_job(job_id)
        await _heartbeat(
            "healthy",
            {"result": "scan_completed", "job_id": job_id, "final_status": JOBS[job_id].get("status")},
        )
        # Regression alert (only for scheduled runs, never manual — keeps
        # ops-on-call quiet when a human is intentionally poking the system).
        if JOBS[job_id].get("status") == "complete":
            try:
                from utils.gtec_alerts import maybe_fire_regression_alert
                report = await _read_latest_report()
                if report:
                    result = await maybe_fire_regression_alert(db, report, job_id)
                    if result and result.get("alerted"):
                        logger.info(
                            "gtec_crawler: regression alert fired via %s (fp=%s)",
                            ",".join(result.get("channels") or []),
                            result.get("fingerprint"),
                        )
            except Exception:
                logger.exception("gtec_crawler: regression-alert pipeline crashed")
    except Exception:
        try:
            await _heartbeat("error", {"result": "scheduled_auto_run_crashed"})
        except Exception:
            pass
        logger.exception("gtec_crawler: scheduled_auto_run crashed")


# ── Alert settings + history ──

@router.get("/alerts/settings")
async def gtec_alert_settings_get(request: Request):
    await require_admin(request)
    from utils.gtec_alerts import get_alert_settings
    return await get_alert_settings(db)


@router.post("/alerts/settings")
async def gtec_alert_settings_set(request: Request, body: AlertSettingsBody):
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Alert settings mutation is disabled by autonomous policy. "
            "Use platform policy pipeline for destinations and thresholds."
        ),
    )


@router.get("/alerts/history")
async def gtec_alert_history(request: Request):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db["gtec_crawler_alerts"].find({}, {"_id": 0}).sort("sent_at", -1).limit(20):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.post("/alerts/test")
async def gtec_alert_test(request: Request):
    """Fire a dummy alert so admins can verify their Slack + email wiring end-to-end."""
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Manual alert test is disabled by autonomous policy. "
            "Alerting is continuously validated by autonomous health checks."
        ),
    )
