"""
Performance Guardian - Enterprise-grade auto-monitoring & safe auto-fix system.
Target: All page load times < 1 second.
"""
import logging
import os
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from observability.request_context import extract_request_observability_context

logger = logging.getLogger(__name__)
router = APIRouter()

LOAD_TIME_TARGET_S = 1.0
LOAD_TIME_WARN_S = 0.9
GUARDIAN_CONFIG_VERSION = "guardian_cwv_v2"
VALID_VITALS_FILTER = {
    "lcp": {"$gte": 0, "$lte": 15},
    "fcp": {"$gte": 0, "$lte": 10},
    "ttfb": {"$gte": 0, "$lte": 5},
}
DEFAULT_ROUTE_PERFORMANCE_BUDGETS = [
    {"route": "*", "label": "Global Default", "lcp_budget_ms": 1000, "fcp_budget_ms": 800, "ttfb_budget_ms": 350},
    {"route": "/welcome", "label": "Welcome Route", "lcp_budget_ms": 1100, "fcp_budget_ms": 850, "ttfb_budget_ms": 350},
    {"route": "/dashboard", "label": "Dashboard Route", "lcp_budget_ms": 1000, "fcp_budget_ms": 800, "ttfb_budget_ms": 350},
    {"route": "/admin-console", "label": "Admin Console Route", "lcp_budget_ms": 1000, "fcp_budget_ms": 800, "ttfb_budget_ms": 350},
    {"route": "/notifications", "label": "Notifications Route", "lcp_budget_ms": 1000, "fcp_budget_ms": 800, "ttfb_budget_ms": 350},
    {"route": "/subscription/mobile-money", "label": "Mobile Money Route", "lcp_budget_ms": 1100, "fcp_budget_ms": 850, "ttfb_budget_ms": 350},
]
ENFORCED_ROUTE_BUDGETS = {"*", "/welcome", "/dashboard", "/admin-console", "/notifications", "/subscription/mobile-money"}
MIN_ROUTE_BUDGET_SAMPLES = 3
INSUFFICIENT_DATA_ALERT_HOURS = 6


def _normalize_index_key(index_key) -> tuple[tuple[str, int], ...]:
    normalized = []
    for item in index_key or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            normalized.append((str(item[0]), int(item[1])))
    return tuple(normalized)


async def _missing_performance_indexes(db) -> list[tuple[tuple[str, int], ...]]:
    existing = await db.web_vitals.index_information()
    existing_keys = {_normalize_index_key(meta.get("key")) for meta in existing.values()}
    required = [
        (("timestamp", -1),),
        (("page", 1), ("timestamp", -1)),
        (("release_version", 1), ("timestamp", -1)),
    ]
    return [index_key for index_key in required if index_key not in existing_keys]

async def _get_db():
    from server import db
    return db


async def _restart_frontend_service() -> tuple[bool, str]:
    """Restart frontend via supervisor, with fallback for legacy service names."""
    for service_name in ("frontend", "expo_manual"):
        proc = await asyncio.create_subprocess_exec(
            "sudo", "supervisorctl", "restart", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        if proc.returncode == 0:
            return True, (stdout.decode().strip() or f"{service_name} restarted")
        err_text = (stderr.decode() or stdout.decode()).strip()
        if "no such process" not in err_text.lower():
            return False, err_text or f"restart {service_name} failed"
    return False, "No matching frontend supervisor service found"


async def _get_latest_vitals_release(db, since: datetime) -> str:
    latest = await db.web_vitals.find_one(
        {"timestamp": {"$gte": since}, "release_version": {"$exists": True, "$ne": ""}},
        {"_id": 0, "release_version": 1},
        sort=[("timestamp", -1)],
    )
    return str((latest or {}).get("release_version") or "")


def _resolve_guardian_config(config: dict | None) -> dict:
    resolved = {
        "auto_fix_enabled": False,
        "target_load_time": LOAD_TIME_TARGET_S,
        "check_interval_minutes": 15,
        "alert_on_fix": True,
        "config_version": GUARDIAN_CONFIG_VERSION,
    }
    if config:
        for key in resolved.keys():
            if key in config:
                resolved[key] = config[key]

    target_value = float(resolved.get("target_load_time") or LOAD_TIME_TARGET_S)
    if str((config or {}).get("config_version") or "") != GUARDIAN_CONFIG_VERSION and target_value <= 1.0:
        resolved["target_load_time"] = LOAD_TIME_TARGET_S
    else:
        resolved["target_load_time"] = target_value

    resolved["config_version"] = GUARDIAN_CONFIG_VERSION
    return resolved


def _with_valid_vitals(match_stage: dict) -> dict:
    return {**match_stage, **VALID_VITALS_FILTER}


def build_default_budget_for_route(route: str) -> dict:
    normalized = str(route or "").strip() or "/"
    budget = {"route": normalized, "label": normalized, "lcp_budget_ms": 1000, "fcp_budget_ms": 800, "ttfb_budget_ms": 350}
    if normalized in {"/", "/welcome"}:
        budget.update({"label": "Welcome Route", "lcp_budget_ms": 1100, "fcp_budget_ms": 850})
    elif normalized.startswith("/admin") or normalized.startswith("/executive"):
        budget.update({"label": normalized.replace("/", " ").strip().title(), "lcp_budget_ms": 1000, "fcp_budget_ms": 800})
    elif normalized.startswith("/dashboard"):
        budget.update({"label": "Dashboard Route", "lcp_budget_ms": 1000, "fcp_budget_ms": 800})
    elif normalized.startswith("/notifications"):
        budget.update({"label": "Notifications Route", "lcp_budget_ms": 1000, "fcp_budget_ms": 800})
    elif normalized.startswith("/subscription/mobile-money"):
        budget.update({"label": "Mobile Money Route", "lcp_budget_ms": 1100, "fcp_budget_ms": 850})
    elif normalized.startswith("/subscription"):
        budget.update({"label": normalized.replace("/", " ").strip().title(), "lcp_budget_ms": 1100, "fcp_budget_ms": 850})
    return budget


async def ensure_performance_budget_for_route(db, route: str, *, seeded_by: str = "guardian_route_autoseed_v1") -> dict:
    normalized = str(route or "").strip()
    if not normalized or normalized == "*":
        return {}
    existing = await db.performance_budgets.find_one({"route": normalized}, {"_id": 0})
    if existing:
        return existing

    payload = {
        **build_default_budget_for_route(normalized),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seeded_by": seeded_by,
        "auto_seeded": True,
    }
    await db.performance_budgets.update_one({"route": normalized}, {"$set": payload}, upsert=True)
    return payload


async def ensure_default_performance_budgets(db) -> list[dict]:
    existing = await db.performance_budgets.find({}, {"_id": 0}).to_list(100)
    existing_by_route = {str(item.get("route") or ""): item for item in existing}

    for budget in DEFAULT_ROUTE_PERFORMANCE_BUDGETS:
        route = str(budget.get("route") or "")
        if route in existing_by_route:
            continue
        payload = {
            **budget,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "seeded_by": "guardian_cwv_v2",
        }
        await db.performance_budgets.update_one({"route": route}, {"$set": payload}, upsert=True)

    return await db.performance_budgets.find({}, {"_id": 0}).to_list(100)


async def build_budget_violations_snapshot(db) -> dict:
    latest_page_perf_routes = await db.page_perf_metrics.distinct("page", {"release_version": {"$exists": True, "$ne": ""}})
    for route in latest_page_perf_routes:
        if isinstance(route, str) and route.startswith("/"):
            await ensure_performance_budget_for_route(db, route)

    budgets = [
        budget for budget in await ensure_default_performance_budgets(db)
        if (
            str(budget.get("route") or "") in ENFORCED_ROUTE_BUDGETS
            or str(budget.get("seeded_by") or "") == "guardian_cwv_v2"
            or bool(budget.get("auto_seeded"))
        )
    ]
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    latest_release = await _get_latest_vitals_release(db, hour_ago)
    match_stage = {"timestamp": {"$gte": hour_ago}}
    if latest_release:
        match_stage["release_version"] = latest_release

    pipe = [
        {"$match": _with_valid_vitals(match_stage)},
        {"$group": {
            "_id": "$page",
            "avg_lcp": {"$avg": "$lcp"},
            "avg_fcp": {"$avg": "$fcp"},
            "avg_ttfb": {"$avg": "$ttfb"},
            "count": {"$sum": 1},
            "last_seen": {"$max": "$timestamp"},
        }}
    ]
    metrics_by_route = {r.get("_id"): r for r in await db.web_vitals.aggregate(pipe).to_list(100)}

    global_pipe = [
        {"$match": _with_valid_vitals(match_stage)},
        {"$group": {"_id": None, "avg_lcp": {"$avg": "$lcp"}, "avg_fcp": {"$avg": "$fcp"}, "avg_ttfb": {"$avg": "$ttfb"}, "count": {"$sum": 1}, "last_seen": {"$max": "$timestamp"}}}
    ]
    global_metrics = await db.web_vitals.aggregate(global_pipe).to_list(1)
    if global_metrics:
        metrics_by_route["*"] = global_metrics[0]

    page_perf_pipe = [
        {"$match": {"timestamp": {"$gte": hour_ago}, "release_version": latest_release} if latest_release else {"timestamp": {"$gte": hour_ago}}},
        {"$group": {
            "_id": "$page",
            "avg_ms": {"$avg": "$duration_ms"},
            "count": {"$sum": 1},
            "last_seen": {"$max": "$timestamp"},
        }},
    ]
    page_perf_by_route = {row.get("_id"): row for row in await db.page_perf_metrics.aggregate(page_perf_pipe).to_list(100)}
    global_page_perf_pipe = [
        {"$match": {"timestamp": {"$gte": hour_ago}, "release_version": latest_release} if latest_release else {"timestamp": {"$gte": hour_ago}}},
        {"$group": {"_id": None, "avg_ms": {"$avg": "$duration_ms"}, "count": {"$sum": 1}, "last_seen": {"$max": "$timestamp"}}},
    ]
    global_page_perf = (await db.page_perf_metrics.aggregate(global_page_perf_pipe).to_list(1) or [{}])[0]

    violations = []
    for budget in budgets:
        route = budget["route"]
        metrics = metrics_by_route.get(route)
        page_perf_metrics = page_perf_by_route.get(route) or {}
        if route == "*":
            metrics = metrics_by_route.get("*", {})
            page_perf_metrics = global_page_perf or {}

        if not metrics and not page_perf_metrics:
            continue

        metrics = metrics or {}
        page_perf_count = int(page_perf_metrics.get("count") or 0)
        page_perf_avg_ms = round(float(page_perf_metrics.get("avg_ms") or 0), 1) if page_perf_count else 0.0
        using_page_perf = page_perf_count > 0

        lcp_ms = page_perf_avg_ms if using_page_perf else (metrics.get("avg_lcp", 0) or 0) * 1000
        fcp_ms = 0 if using_page_perf else (metrics.get("avg_fcp", 0) or 0) * 1000
        ttfb_ms = 0 if using_page_perf else (metrics.get("avg_ttfb", 0) or 0) * 1000

        row = {
            "route": route,
            "label": budget.get("label", route),
            "samples": page_perf_count if using_page_perf else metrics.get("count", 0),
            "vitals_samples": metrics.get("count", 0),
            "page_perf_samples": page_perf_count,
            "last_seen": (page_perf_metrics.get("last_seen") or metrics.get("last_seen")).isoformat() if (page_perf_metrics.get("last_seen") or metrics.get("last_seen")) else None,
            "lcp_actual_ms": round(lcp_ms),
            "lcp_budget_ms": budget["lcp_budget_ms"],
            "lcp_over": max(0, round(lcp_ms - budget["lcp_budget_ms"])),
            "fcp_actual_ms": round(fcp_ms),
            "fcp_budget_ms": budget["fcp_budget_ms"],
            "fcp_over": max(0, round(fcp_ms - budget["fcp_budget_ms"])),
            "ttfb_actual_ms": round(ttfb_ms),
            "ttfb_budget_ms": budget["ttfb_budget_ms"],
            "ttfb_over": max(0, round(ttfb_ms - budget["ttfb_budget_ms"])),
            "measurement_source": "page_perf_metrics" if using_page_perf else "web_vitals",
        }
        row["min_samples_required"] = 1 if route == "*" else MIN_ROUTE_BUDGET_SAMPLES
        if route != "*" and int(row["samples"] or 0) < MIN_ROUTE_BUDGET_SAMPLES:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=INSUFFICIENT_DATA_ALERT_HOURS)
            last_seen_dt = page_perf_metrics.get("last_seen") or metrics.get("last_seen")
            if isinstance(last_seen_dt, datetime) and last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
            coverage_stale = not last_seen_dt or last_seen_dt < stale_cutoff
            row["coverage_status"] = "stale" if coverage_stale else "fresh"
            row["coverage_alert"] = coverage_stale
            row["warmup_source"] = "page_perf_metrics" if page_perf_count > 0 else None
            row["warmup_page_avg_ms"] = page_perf_avg_ms if page_perf_count > 0 else None
            row["total_over_ms"] = row["lcp_over"] if page_perf_count > 0 else 0
            row["status"] = "warmup_covered" if page_perf_count > 0 else "insufficient_data"
        else:
            row["coverage_status"] = "fresh"
            row["coverage_alert"] = False
            row["warmup_source"] = None
            row["warmup_page_avg_ms"] = None
            row["total_over_ms"] = row["lcp_over"] + row["fcp_over"] + row["ttfb_over"]
            row["status"] = "violation" if row["total_over_ms"] > 0 else "within_budget"
        violations.append(row)

    violations.sort(key=lambda item: item["total_over_ms"], reverse=True)
    total_violations = sum(1 for item in violations if item["status"] == "violation")
    insufficient_data_routes = [item["route"] for item in violations if item.get("status") == "insufficient_data"]
    stale_insufficient_routes = [item["route"] for item in violations if item.get("status") == "insufficient_data" and item.get("coverage_alert")]
    return {
        "violations": violations,
        "total_budgets": len(budgets),
        "total_violations": total_violations,
        "insufficient_data_routes": insufficient_data_routes,
        "stale_insufficient_routes": stale_insufficient_routes,
        "coverage_alert_threshold_hours": INSUFFICIENT_DATA_ALERT_HOURS,
        "release_version": latest_release or None,
    }


# ── Web Vitals Beacon: Receive real browser metrics ─────────────────
@router.post("/vitals/report")
async def report_web_vitals(request: Request):
    """Receive web vitals from browser clients. No auth required for beacon."""
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "vitals_report", 320, 60)
    if blocked:
        return blocked

    db = await _get_db()
    try:
        body = await request.json()
        metrics = body if isinstance(body, list) else [body]
        metrics = metrics[:100]
        now = datetime.now(timezone.utc)
        docs = []
        obs_ctx = extract_request_observability_context(request)

        def _safe_number(value, default=0.0, floor=0.0, ceil=120000.0):
            try:
                parsed = float(value)
                if parsed != parsed:  # NaN guard
                    return default
                return min(max(parsed, floor), ceil)
            except Exception:
                return default

        for m in metrics:
            if not isinstance(m, dict):
                continue
            page = str(m.get("page", "/") or "/")[:180]
            if not page.startswith("/"):
                page = f"/{page}"

            doc = {
                "timestamp": now,
                "source": "browser",
                "lcp": _safe_number(m.get("lcp", 0), ceil=20000.0) / 1000,
                "fcp": _safe_number(m.get("fcp", 0), ceil=15000.0) / 1000,
                "ttfb": _safe_number(m.get("ttfb", 0), ceil=10000.0) / 1000,
                "cls": _safe_number(m.get("cls", 0), ceil=3.0),
                "inp": _safe_number(m.get("inp", 0), ceil=30000.0),
                "page": page,
                "ua": str(m.get("ua", ""))[:200],
                "release_version": str(m.get("release_version") or "")[:80],
                "correlation_id": str(getattr(request.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
                "trace_id": str(getattr(request.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
                "span_id": str(getattr(request.state, "span_id", "") or obs_ctx.get("span_id") or ""),
                "session_id": str(getattr(request.state, "session_id", "") or obs_ctx.get("session_id") or ""),
            }
            docs.append(doc)
        if docs:
            await db.web_vitals.insert_many(docs, ordered=False)
        return {"status": "ok", "received": len(docs)}
    except Exception as e:
        logger.warning(f"Vitals report error: {e}")
        return {"status": "ok", "received": 0, "error": "invalid_payload"}


async def _send_autofix_alert(db, fixes_applied: list, lcp: float, target: float, triggered_by: str):
    """Send email alert to all admins — only shows actionable fixes, skips already-OK ones."""
    try:
        from utils.email_service import render_email_timestamp_pill

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1}).to_list(50)
        if not admins:
            admins = [{"email": "admin@realaicoach.app", "name": "Admin"}]

        # Categorize fixes
        applied = [f for f in fixes_applied if f.get("status") == "applied"]
        flagged = [f for f in fixes_applied if f.get("status") == "flagged_for_review"]
        skipped = [f for f in fixes_applied if f.get("status") in ("not_needed", "skipped")]
        actionable = applied + flagged  # only these appear in the email table

        applied_count = len(applied)
        flagged_count = len(flagged)
        skipped_count = len(skipped)
        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        render_email_timestamp_pill(now_str)

        # Don't send email if nothing actionable happened
        if not actionable:
            logger.info("Performance Guardian: all checks passed — no email sent (nothing to report)")
            return

        # Build fix rows — only for applied + flagged
        fix_rows = ""
        for f in actionable:
            status = f.get("status", "unknown")
            details = f.get("details", "")
            fix_id = f.get("fix_id", "").replace("_", " ").title()
            if status == "applied":
                color = "#10B981"
                badge = "APPLIED"
            elif status == "flagged_for_review":
                color = "#F59E0B"
                badge = "NEEDS REVIEW"
            else:
                color = "#64748B"
                badge = status.upper()
            fix_rows += f"""
            <tr>
              <td style="padding:10px 14px;border-bottom:1px solid #E2E8F0;color:#0F172A;font-size:14px;font-weight:600;">{fix_id}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #E2E8F0;text-align:center;">
                <span style="display:inline-block;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;background:{color};">{badge}</span>
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #E2E8F0;color:#334155;font-size:13px;">{details}</td>
            </tr>"""


        # Build smart subject line
        parts = []
        if applied_count:
            parts.append(f"{applied_count} Applied")
        if flagged_count:
            parts.append(f"{flagged_count} Needs Review")
        subject_label = ", ".join(parts) if parts else "Check Complete"
        metric_label = f"{float(lcp):.2f}" if lcp else "N/A"

        # Skipped summary note
        skipped_label = ""
        if skipped_count > 0:
            skipped_label = ", ".join(f.get("fix_id", "").replace("_", " ").title() for f in skipped)

        # Summary badge
        summary_badge = f"{applied_count} applied" + (f", {flagged_count} review" if flagged_count else "")

        level_label = "critical" if float(lcp or 0) > float(target or 0) else "warning"
        metric_name = "LCP"
        metric_val = float(lcp or 0)
        threshold = float(target or 0)
        page_url = "/dashboard"


        for admin in admins:
            try:
                from utils.email_service import send_catalog_template
                await send_catalog_template(
                    recipient_email=admin["email"],
                    template_key="performance_degradation_alert",
                    level=level_label,
                    metric=metric_name,
                    current_value=metric_label or str(round(metric_val, 2)),
                    threshold=str(round(threshold, 2)),
                    page=page_url,
                    summary_badge=summary_badge,
                    skipped_fixes=skipped_label,
                    subject_label=subject_label,
                )
                logger.info(f"Performance Guardian alert sent to {admin['email']}")
            except Exception as e:
                logger.warning(f"Failed to send guardian alert to {admin.get('email')}: {e}")

    except Exception as e:
        logger.error(f"Performance Guardian alert email failed: {e}")


# ── Health Check: Real-time performance status ─────────────────────
@router.get("/admin/performance-guardian/status")
async def guardian_status(request: Request):
    """Real-time performance health with actionable diagnostics."""
    db = await _get_db()
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    latest_release = await _get_latest_vitals_release(db, day_ago)
    match_1h = {"timestamp": {"$gte": hour_ago}}
    match_24h = {"timestamp": {"$gte": day_ago}}
    if latest_release:
        match_1h["release_version"] = latest_release
        match_24h["release_version"] = latest_release

    # Last 1h vitals for real-time status
    pipe_1h = [
        {"$match": _with_valid_vitals(match_1h)},
        {"$group": {
            "_id": None,
            "avg_lcp": {"$avg": "$lcp"},
            "avg_fcp": {"$avg": "$fcp"},
            "avg_ttfb": {"$avg": "$ttfb"},
            "avg_cls": {"$avg": "$cls"},
            "avg_inp": {"$avg": "$inp"},
            "p95_lcp": {"$max": "$lcp"},
            "count": {"$sum": 1},
        }},
    ]
    data_1h = await db.web_vitals.aggregate(pipe_1h).to_list(1)
    current = data_1h[0] if data_1h else {}
    current.pop("_id", None)

    # Last 24h for comparison
    pipe_24h = [
        {"$match": _with_valid_vitals(match_24h)},
        {"$group": {
            "_id": None,
            "avg_lcp": {"$avg": "$lcp"},
            "avg_fcp": {"$avg": "$fcp"},
            "avg_ttfb": {"$avg": "$ttfb"},
            "count": {"$sum": 1},
        }},
    ]
    data_24h = await db.web_vitals.aggregate(pipe_24h).to_list(1)
    baseline = data_24h[0] if data_24h else {}
    baseline.pop("_id", None)

    lcp = current.get("avg_lcp", 0)
    fcp = current.get("avg_fcp", 0)
    ttfb = current.get("avg_ttfb", 0)
    samples_1h = current.get("count", 0)
    samples_24h = baseline.get("count", 0)

    # Get auto-fix config
    config = _resolve_guardian_config(await db.performance_guardian_config.find_one({"_id": "guardian"}))
    auto_fix_enabled = config.get("auto_fix_enabled", False)
    target_load_time = config.get("target_load_time", LOAD_TIME_TARGET_S)

    # Detect issues
    issues = []
    if lcp > target_load_time:
        issues.append({
            "id": "lcp_high",
            "severity": "critical" if lcp > 4.0 else "warning",
            "title": f"Page load time ({lcp:.2f}s) exceeds {target_load_time}s target",
            "metric": "LCP",
            "value": round(lcp, 2),
            "target": target_load_time,
            "auto_fixable": True,
        })
    if ttfb > 0.5:
        issues.append({
            "id": "ttfb_high",
            "severity": "critical" if ttfb > 1.0 else "warning",
            "title": f"Server response time ({ttfb:.2f}s) is slow",
            "metric": "TTFB",
            "value": round(ttfb, 2),
            "target": 0.5,
            "auto_fixable": True,
        })
    if fcp > 1.0:
        issues.append({
            "id": "fcp_high",
            "severity": "warning",
            "title": f"First paint ({fcp:.2f}s) needs improvement",
            "metric": "FCP",
            "value": round(fcp, 2),
            "target": 1.0,
            "auto_fixable": True,
        })

    # Determine overall status from current issue severity (avoids overstating warning-only telemetry as critical)
    if samples_1h == 0 and samples_24h == 0:
        status = "no_data"
        status_label = "No Data"
        status_color = "#94A3B8"
    elif any(issue.get("severity") == "critical" for issue in issues):
        status = "critical"
        status_label = "Critical"
        status_color = "#EF4444"
    elif issues:
        status = "warning"
        status_label = "Degraded"
        status_color = "#F59E0B"
    else:
        status = "healthy"
        status_label = "Healthy"
        status_color = "#10B981"

    # Recent fix history
    fixes_raw = await db.performance_fixes.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(10)

    # Hourly trend (last 12h)
    trend_pipe = [
        {"$match": _with_valid_vitals({**match_24h, "timestamp": {"$gte": now - timedelta(hours=12)}})},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%dT%H:00", "date": "$timestamp"}},
            "lcp": {"$avg": "$lcp"},
            "fcp": {"$avg": "$fcp"},
            "ttfb": {"$avg": "$ttfb"},
            "samples": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    trend_raw = await db.web_vitals.aggregate(trend_pipe).to_list(24)
    trend = [{
        "time": doc["_id"],
        "lcp": round(doc.get("lcp") or 0, 2),
        "fcp": round(doc.get("fcp") or 0, 2),
        "ttfb": round(doc.get("ttfb") or 0, 2),
        "samples": doc.get("samples", 0),
    } for doc in trend_raw]

    return {
        "status": status,
        "status_label": status_label,
        "status_color": status_color,
        "target_load_time": target_load_time,
        "release_version": latest_release or None,
        "auto_fix_enabled": auto_fix_enabled,
        "current_metrics": {
            "lcp": round(lcp, 2),
            "fcp": round(fcp, 2),
            "ttfb": round(ttfb, 2),
            "cls": round(current.get("avg_cls", 0), 3),
            "inp": round(current.get("avg_inp", 0), 1),
            "p95_lcp": round(current.get("p95_lcp", 0), 2),
        },
        "samples_1h": samples_1h,
        "samples_24h": samples_24h,
        "issues": issues,
        "trend": trend,
        "recent_fixes": fixes_raw,
        "timestamp": now.isoformat(),
    }


# ── Safe Auto-Fix: Run diagnostics and apply safe fixes ────────────
SAFE_FIXES = [
    {
        "id": "clear_metro_cache",
        "label": "Clear Metro Bundler Cache",
        "description": "Removes stale Metro cache files that can cause slow or failed bundle loading",
        "risk": "none",
        "impact": "Requires one cold rebundle (~30s). No data loss.",
    },
    {
        "id": "disable_lazy_loading",
        "label": "Disable Metro Lazy Loading",
        "description": "Ensures EXPO_NO_METRO_LAZY=true is set to prevent ERR_ABORTED chunk failures",
        "risk": "none",
        "impact": "Larger initial bundle but zero failed chunk requests.",
    },
    {
        "id": "purge_stale_vitals",
        "label": "Purge Stale Performance Data",
        "description": "Remove web vitals records older than 7 days that inflate LCP/FCP averages",
        "risk": "none",
        "impact": "Cleaner metrics. Historical data older than 7d removed.",
    },
    {
        "id": "optimize_db_indexes",
        "label": "Optimize Database Indexes",
        "description": "Ensure proper indexes exist on web_vitals collection for fast queries",
        "risk": "none",
        "impact": "Faster dashboard loading. No downtime.",
    },
    {
        "id": "enable_response_compression",
        "label": "Enable API Response Compression",
        "description": "Configure gzip compression for API responses to reduce payload sizes",
        "risk": "none",
        "impact": "30-70% smaller API responses, faster page loads.",
    },
    {
        "id": "restart_frontend",
        "label": "Restart Frontend Service",
        "description": "Gracefully restarts the Expo/Metro bundler to apply pending fixes",
        "risk": "low",
        "impact": "Brief (~5s) service interruption during restart.",
    },
]


@router.get("/admin/performance-guardian/available-fixes")
async def get_available_fixes():
    """List all available safe auto-fixes with risk assessment."""
    return {"fixes": SAFE_FIXES}


@router.post("/admin/performance-guardian/auto-fix")
async def run_auto_fix(request: Request):
    """Execute AI-powered auto-fix with GPT-4o confidence scoring."""
    db = await _get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    use_ai = body.get("use_ai", True)
    fix_ids = body.get("fixes", [])
    run_all = body.get("run_all", not fix_ids)

    if run_all:
        fix_ids = [f["id"] for f in SAFE_FIXES]

    now = datetime.now(timezone.utc)

    # Fetch current metrics early (used for AI context + email)
    hour_ago = now - timedelta(hours=1)
    metrics_pipe = [
        {"$match": {"timestamp": {"$gte": hour_ago}}},
        {"$group": {"_id": None, "avg_lcp": {"$avg": "$lcp"}, "avg_fcp": {"$avg": "$fcp"}, "avg_ttfb": {"$avg": "$ttfb"}, "count": {"$sum": 1}}}
    ]
    metrics_data = await db.web_vitals.aggregate(metrics_pipe).to_list(1)
    metrics_ctx = metrics_data[0] if metrics_data else {}
    metrics_ctx.pop("_id", None)

    # Phase 1: Propose fixes (gather status without applying)
    proposals = []
    for fix_id in fix_ids:
        proposal = {"fix_id": fix_id, "status": "proposed", "details": "", "risk": "none"}
        if fix_id == "clear_metro_cache":
            cache_dir = "/app/frontend/.metro-cache"
            if os.path.exists(cache_dir):
                size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, filenames in os.walk(cache_dir) for f in filenames)
                proposal["details"] = f"Clear {size / 1024 / 1024:.1f}MB stale Metro cache causing slow bundle loading"
                proposal["risk"] = "none"
            else:
                proposal["status"] = "not_needed"
                proposal["details"] = "Metro cache directory does not exist"
        elif fix_id == "disable_lazy_loading":
            env_path = "/app/frontend/.env"
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    content = f.read()
                if "EXPO_NO_METRO_LAZY=true" in content:
                    proposal["status"] = "not_needed"
                    proposal["details"] = "EXPO_NO_METRO_LAZY=true already set"
                else:
                    proposal["details"] = "Add EXPO_NO_METRO_LAZY=true to prevent ERR_ABORTED chunk failures"
                    proposal["risk"] = "none"
        elif fix_id == "purge_stale_vitals":
            cutoff = now - timedelta(days=7)
            stale_count = await db.web_vitals.count_documents({"timestamp": {"$lt": cutoff}})
            if stale_count > 0:
                proposal["details"] = f"Remove {stale_count} stale web vitals records older than 7 days to improve LCP/FCP averages"
                proposal["risk"] = "none"
            else:
                proposal["status"] = "not_needed"
                proposal["details"] = "No stale vitals data found (all within 7 days)"
        elif fix_id == "optimize_db_indexes":
            missing = await _missing_performance_indexes(db)
            if missing:
                labels = [" + ".join(f"{field}:{order}" for field, order in index_key) for index_key in missing]
                proposal["details"] = f"Create {len(missing)} missing indexes on web_vitals collection ({'; '.join(labels)})"
                proposal["risk"] = "none"
            else:
                proposal["status"] = "not_needed"
                proposal["details"] = "All required performance indexes already exist"
        elif fix_id == "enable_response_compression":
            mw_path = "/app/backend/middleware.py"
            server_path = "/app/backend/server.py"
            found = False
            for path in [mw_path, server_path]:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        content = f.read()
                    if "GZipMiddleware" in content:
                        found = True
                        break
            if found:
                proposal["status"] = "not_needed"
                proposal["details"] = "GZip compression already enabled"
            else:
                proposal["details"] = "Add GZipMiddleware to compress API responses (30-70% size reduction)"
                proposal["risk"] = "none"
        elif fix_id == "restart_frontend":
            proposal["details"] = "Gracefully restart frontend service to apply pending optimizations"
            proposal["risk"] = "low"
        proposals.append(proposal)

    # Filter out not_needed
    actionable = [p for p in proposals if p["status"] == "proposed"]

    # Phase 2: GPT-4o confidence scoring (if AI mode and there are actionable fixes)
    if use_ai and actionable:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            import uuid as uuid_mod
            llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
            chat = LlmChat(
                api_key=llm_key,
                session_id=f"perf-guardian-{uuid_mod.uuid4().hex[:8]}",
                system_message="You are a performance engineering AI. Always return valid JSON only.",
            ).with_model("openai", "gpt-4o")

            eval_prompt = f"""You are a performance engineering AI. Evaluate these proposed fixes for a web application.

Current Performance Metrics:
- LCP (Page Load): {metrics_ctx.get('avg_lcp', 'N/A')}s (Target: {LOAD_TIME_TARGET_S}s)
- FCP (First Paint): {metrics_ctx.get('avg_fcp', 'N/A')}s (Target: 1.0s)
- TTFB (Server): {metrics_ctx.get('avg_ttfb', 'N/A')}s (Target: 0.5s)
- Samples: {metrics_ctx.get('count', 0)} in last hour

Proposed Fixes:
{chr(10).join(f'{i+1}. [{p["fix_id"]}] {p["details"]} (Risk: {p["risk"]})' for i, p in enumerate(actionable))}

For EACH fix, provide a JSON array with objects containing:
- fix_id: the fix identifier
- confidence: 0-100 (how confident this fix will improve performance)
- risk: "none", "low", "medium", or "high"
- reasoning: brief explanation of why this confidence level
- recommended_action: "apply" or "flag_for_review"

Return ONLY valid JSON array, no other text."""

            response = await chat.send_message(UserMessage(text=eval_prompt))
            import json as json_module
            text = response.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            evaluations = json_module.loads(text)

            # Merge evaluations with proposals
            eval_map = {e["fix_id"]: e for e in evaluations}
            for p in actionable:
                ev = eval_map.get(p["fix_id"], {})
                p["confidence"] = ev.get("confidence", 75)
                p["risk"] = ev.get("risk", p["risk"])
                p["reasoning"] = ev.get("reasoning", "")
                p["recommended_action"] = ev.get("recommended_action", "apply")

        except Exception as e:
            logger.warning(f"AI confidence scoring failed, using defaults: {e}")
            for p in actionable:
                p["confidence"] = 85
                p["reasoning"] = "AI evaluation unavailable — using default confidence"
                p["recommended_action"] = "apply"
    elif actionable:
        for p in actionable:
            p["confidence"] = 90
            p["reasoning"] = "Standard mode — no AI evaluation"
            p["recommended_action"] = "apply"

    # Phase 3: Apply high-confidence fixes
    results = []
    for p in proposals:
        if p["status"] == "not_needed":
            results.append(p)
            continue

        conf = p.get("confidence", 0)
        if conf >= CONFIDENCE_THRESHOLD_PERF:
            # Apply the fix
            applied_result = await _apply_fix(p["fix_id"])
            p["status"] = applied_result["status"]
            p["details"] = applied_result["details"]
        else:
            p["status"] = "flagged_for_review"
        results.append(p)

    applied = sum(1 for r in results if r["status"] == "applied")
    flagged = sum(1 for r in results if r["status"] == "flagged_for_review")

    # Store fix record
    fix_record = {
        "timestamp": now.isoformat(),
        "fixes_requested": fix_ids,
        "results": results,
        "triggered_by": "admin",
        "run_all": run_all,
        "ai_powered": use_ai,
        "confidence_threshold": CONFIDENCE_THRESHOLD_PERF,
    }
    await db.performance_fixes.insert_one({**fix_record})

    # Send email alert
    config = await db.performance_guardian_config.find_one({"_id": "guardian"})
    if config and config.get("alert_on_fix", True):
        lcp_val = metrics_ctx.get("avg_lcp", 0)
        target = config.get("target_load_time", LOAD_TIME_TARGET_S)
        await _send_autofix_alert(db, results, lcp_val, target, "admin")

    return {
        "success": True,
        "applied": applied,
        "flagged": flagged,
        "total": len(results),
        "confidence_threshold": CONFIDENCE_THRESHOLD_PERF,
        "results": results,
        "ai_powered": use_ai,
        "message": f"{applied} fix{'es' if applied != 1 else ''} applied, {flagged} flagged for review" if applied + flagged > 0 else "All systems already optimized",
    }


CONFIDENCE_THRESHOLD_PERF = 80


async def _apply_fix(fix_id: str) -> dict:
    """Actually apply a single fix and return its result."""
    result = {"fix_id": fix_id, "status": "skipped", "details": ""}
    try:
        if fix_id == "clear_metro_cache":
            cache_dir = "/app/frontend/.metro-cache"
            if os.path.exists(cache_dir):
                import shutil
                shutil.rmtree(cache_dir, ignore_errors=True)
                result["status"] = "applied"
                result["details"] = "Metro cache cleared successfully"
            else:
                result["status"] = "not_needed"
                result["details"] = "Metro cache directory does not exist"
        elif fix_id == "disable_lazy_loading":
            env_path = "/app/frontend/.env"
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    content = f.read()
                if "EXPO_NO_METRO_LAZY=true" not in content:
                    with open(env_path, "a") as f:
                        f.write("\nEXPO_NO_METRO_LAZY=true\n")
                    result["status"] = "applied"
                    result["details"] = "Added EXPO_NO_METRO_LAZY=true to .env"
                else:
                    result["status"] = "not_needed"
                    result["details"] = "Already configured"
        elif fix_id == "purge_stale_vitals":
            db = await _get_db()
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            r = await db.web_vitals.delete_many({"timestamp": {"$lt": cutoff}})
            if r.deleted_count > 0:
                result["status"] = "applied"
                result["details"] = f"Purged {r.deleted_count} stale web vitals records (older than 7 days)"
            else:
                result["status"] = "not_needed"
                result["details"] = "No stale records found"
        elif fix_id == "optimize_db_indexes":
            db = await _get_db()
            try:
                await db.web_vitals.create_index([("timestamp", -1)], background=True)
                await db.web_vitals.create_index([("page", 1), ("timestamp", -1)], background=True)
                await db.web_vitals.create_index([("release_version", 1), ("timestamp", -1)], background=True)
                await db.page_perf_metrics.create_index([("page", 1), ("timestamp", -1)], background=True)
                await db.page_perf_metrics.create_index([("release_version", 1), ("timestamp", -1)], background=True)
                result["status"] = "applied"
                result["details"] = "Ensured web_vitals/page_perf_metrics indexes for timestamp, page, and release_version"
            except Exception as idx_err:
                result["status"] = "applied"
                result["details"] = f"Indexes ensured (may already exist): {idx_err}"
        elif fix_id == "enable_response_compression":
            mw_path = "/app/backend/middleware.py"
            server_path = "/app/backend/server.py"
            found = False
            for path in [mw_path, server_path]:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        content = f.read()
                    if "GZipMiddleware" in content:
                        found = True
                        break
            if found:
                result["status"] = "not_needed"
                result["details"] = "GZip compression already enabled"
            else:
                # Add to middleware.py
                if os.path.exists(mw_path):
                    with open(mw_path, "r") as f:
                        content = f.read()
                    if "from starlette.middleware.gzip import GZipMiddleware" not in content:
                        content = content.replace(
                            "from starlette.middleware.cors import CORSMiddleware",
                            "from starlette.middleware.cors import CORSMiddleware\nfrom starlette.middleware.gzip import GZipMiddleware"
                        )
                    if "app.add_middleware(GZipMiddleware" not in content:
                        content = content.replace(
                            "app.add_middleware(\n        CORSMiddleware",
                            "app.add_middleware(GZipMiddleware, minimum_size=500)\n    app.add_middleware(\n        CORSMiddleware"
                        )
                    with open(mw_path, "w") as f:
                        f.write(content)
                    result["status"] = "applied"
                    result["details"] = "Added GZipMiddleware for API response compression"
        elif fix_id == "restart_frontend":
            ok, details = await _restart_frontend_service()
            if ok:
                result["status"] = "applied"
                result["details"] = f"Frontend restarted: {details}"
            else:
                result["status"] = "failed"
                result["details"] = f"Restart failed: {details}"
    except Exception as e:
        result["status"] = "failed"
        result["details"] = str(e)
    return result


# ── Settings: Configure auto-fix and thresholds ───────────────────
@router.get("/admin/performance-guardian/settings")
async def get_guardian_settings():
    db = await _get_db()
    config = _resolve_guardian_config(await db.performance_guardian_config.find_one({"_id": "guardian"}))
    return {
        "auto_fix_enabled": config.get("auto_fix_enabled", False),
        "target_load_time": config.get("target_load_time", LOAD_TIME_TARGET_S),
        "check_interval_minutes": config.get("check_interval_minutes", 15),
        "alert_on_fix": config.get("alert_on_fix", True),
        "config_version": config.get("config_version", GUARDIAN_CONFIG_VERSION),
    }


@router.put("/admin/performance-guardian/settings")
async def update_guardian_settings(request: Request):
    db = await _get_db()
    body = await request.json()
    update = {}
    if "auto_fix_enabled" in body:
        update["auto_fix_enabled"] = bool(body["auto_fix_enabled"])
    if "target_load_time" in body:
        val = float(body["target_load_time"])
        update["target_load_time"] = max(0.5, min(10.0, val))
    if "check_interval_minutes" in body:
        update["check_interval_minutes"] = max(5, min(60, int(body["check_interval_minutes"])))
    if "alert_on_fix" in body:
        update["alert_on_fix"] = bool(body["alert_on_fix"])

    if update:
        update["config_version"] = GUARDIAN_CONFIG_VERSION
        await db.performance_guardian_config.update_one(
            {"_id": "guardian"}, {"$set": update}, upsert=True
        )
    return {"status": "ok", "updated": update}


# ── Scheduled auto-fix check (called from main.py scheduler) ──────
async def auto_fix_check():
    """Runs on a schedule. If auto-fix is enabled and metrics are degraded, apply safe fixes."""
    try:
        db = await _get_db()
        config = _resolve_guardian_config(await db.performance_guardian_config.find_one({"_id": "guardian"}))
        if not config.get("auto_fix_enabled", False):
            return

        target = config.get("target_load_time", LOAD_TIME_TARGET_S)
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        pipe = [
            {"$match": {"timestamp": {"$gte": hour_ago}}},
            {"$group": {"_id": None, "avg_lcp": {"$avg": "$lcp"}, "count": {"$sum": 1}}},
        ]
        data = await db.web_vitals.aggregate(pipe).to_list(1)
        if not data or data[0].get("count", 0) < 3:
            return

        lcp = data[0].get("avg_lcp", 0)
        if lcp <= target:
            return

        # Check cooldown (don't auto-fix more than once per hour)
        last_fix = await db.performance_fixes.find_one(
            {"triggered_by": "auto"}, sort=[("timestamp", -1)]
        )
        if last_fix:
            last_ts = last_fix.get("timestamp", "")
            if isinstance(last_ts, str) and last_ts:
                last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                if (now - last_dt).total_seconds() < 3600:
                    return

        # Apply safe fixes (only if actually needed)
        fixes_applied = []

        # 1. Clear metro cache (only if cache exists)
        cache_dir = "/app/frontend/.metro-cache"
        if os.path.exists(cache_dir):
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)
            fixes_applied.append({"fix_id": "clear_metro_cache", "status": "applied", "details": "Metro cache cleared successfully"})

        # 2. Ensure lazy loading disabled (only if not already set)
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            if "EXPO_NO_METRO_LAZY=true" not in content:
                with open(env_path, "a") as f:
                    f.write("\nEXPO_NO_METRO_LAZY=true\n")
                fixes_applied.append({"fix_id": "disable_lazy_loading", "status": "applied", "details": "Added EXPO_NO_METRO_LAZY=true to prevent chunk failures"})

        # 3. Restart frontend only if fixes were applied
        if fixes_applied:
            ok, details = await _restart_frontend_service()
            fixes_applied.append(
                {
                    "fix_id": "restart_frontend",
                    "status": "applied" if ok else "failed",
                    "details": details if ok else f"Restart failed: {details}",
                }
            )

        # Record and send alert
        if fixes_applied:
            await db.performance_fixes.insert_one({
                "timestamp": now.isoformat(),
                "fixes_requested": [f["fix_id"] for f in fixes_applied],
                "results": fixes_applied,
                "triggered_by": "auto",
                "lcp_at_trigger": round(lcp, 2),
                "target": target,
            })
            logger.info(f"Auto-fix applied: {len(fixes_applied)} fixes (LCP was {lcp:.2f}s, target {target}s)")

            # Send email alert if enabled
            if config.get("alert_on_fix", True):
                await _send_autofix_alert(db, fixes_applied, lcp, target, "auto")

    except Exception as e:
        logger.error(f"Auto-fix check failed: {e}")



# ── Proactive Performance Alerts ──────────────────────────────────────
ALERT_THRESHOLDS = {
    "lcp": {"warning": 1.0, "critical": 2.5, "unit": "s"},
    "fcp": {"warning": 1.0, "critical": 2.0, "unit": "s"},
    "ttfb": {"warning": 0.5, "critical": 1.0, "unit": "s"},
    "cls": {"warning": 0.1, "critical": 0.25, "unit": ""},
    "inp": {"warning": 200, "critical": 500, "unit": "ms"},
}

async def proactive_vitals_alert(db_override=None):
    """Scheduled check: send email alerts when web vitals degrade beyond thresholds."""
    try:
        from server import db as server_db
        db = db_override or server_db

        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=1)

        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "avg_lcp": {"$avg": "$lcp"},
                "avg_fcp": {"$avg": "$fcp"},
                "avg_ttfb": {"$avg": "$ttfb"},
                "avg_cls": {"$avg": "$cls"},
                "avg_inp": {"$avg": "$inp"},
                "count": {"$sum": 1},
            }},
        ]
        data = await db.web_vitals.aggregate(pipeline).to_list(1)
        if not data or data[0].get("count", 0) < 3:
            return

        vitals = data[0]
        alerts = []
        for metric, thresholds in ALERT_THRESHOLDS.items():
            val = vitals.get(f"avg_{metric}")
            if val is None:
                continue
            if val > thresholds["critical"]:
                alerts.append({"metric": metric.upper(), "value": round(val, 3), "level": "CRITICAL", "threshold": thresholds["critical"], "unit": thresholds["unit"]})
            elif val > thresholds["warning"]:
                alerts.append({"metric": metric.upper(), "value": round(val, 3), "level": "WARNING", "threshold": thresholds["warning"], "unit": thresholds["unit"]})

        if not alerts:
            return

        # Cooldown: don't send more than 1 alert per 4 hours
        last_alert = await db.performance_alerts.find_one(
            {"type": "vitals_degradation"}, sort=[("timestamp", -1)]
        )
        if last_alert:
            last_ts = last_alert.get("timestamp")
            if isinstance(last_ts, str):
                last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            else:
                last_dt = last_ts
            if (now - last_dt).total_seconds() < 14400:
                return

        # Build and send alert
        critical_count = sum(1 for a in alerts if a["level"] == "CRITICAL")
        warning_count = sum(1 for a in alerts if a["level"] == "WARNING")
        level = "CRITICAL" if critical_count > 0 else "WARNING"

        alert_rows = ""
        for a in alerts:
            color = "#EF4444" if a["level"] == "CRITICAL" else "#F59E0B"
            alert_rows += f"""
            <tr>
              <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:#E2E8F0;font-size:14px;font-weight:700;">{a['metric']}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:{color};font-size:14px;font-weight:700;">{a['value']}{a['unit']}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #1E293B;text-align:center;">
                <span style="display:inline-block;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;background:{color};">{a['level']}</span>
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:#94A3B8;font-size:13px;">Threshold: {a['threshold']}{a['unit']}</td>
            </tr>"""

        from utils.email_service import send_catalog_template

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).to_list(50)
        for admin in (admins or [{"email": "admin@realaicoach.app"}]):
            try:
                await send_catalog_template(
                    recipient_email=admin["email"],
                    template_key="perf_guardian_alert",
                    level=level,
                    critical_count=critical_count,
                    warning_count=warning_count,
                    alerts=alerts,
                    timestamp=now.strftime("%B %d, %Y at %H:%M UTC"),
                )
            except Exception:
                pass

        await db.performance_alerts.insert_one({
            "timestamp": now.isoformat(),
            "type": "vitals_degradation",
            "level": level,
            "alerts": alerts,
            "samples": vitals.get("count", 0),
        })
        logger.info(f"Performance alert sent: {level} ({critical_count} critical, {warning_count} warning)")

    except Exception as e:
        logger.error(f"Proactive vitals alert check failed: {e}")




# ── Performance Alerts API ───────────────────────────────────────────
@router.get("/admin/performance-guardian/alerts")
async def get_performance_alerts(request: Request):
    """Get recent performance alerts history."""
    db = await _get_db()
    try:
        limit = int(request.query_params.get("limit", "20"))
    except (ValueError, TypeError):
        limit = 20
    limit = min(limit, 100)

    alerts = await db.performance_alerts.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)

    # Also get the latest status summary
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    pipe = [
        {"$match": {"timestamp": {"$gte": hour_ago}}},
        {"$group": {
            "_id": None,
            "avg_lcp": {"$avg": "$lcp"},
            "avg_fcp": {"$avg": "$fcp"},
            "avg_ttfb": {"$avg": "$ttfb"},
            "count": {"$sum": 1},
        }},
    ]
    data = await db.web_vitals.aggregate(pipe).to_list(1)
    current = data[0] if data else {}
    current.pop("_id", None)

    # Determine if there's an active critical alert
    active_alert = None
    if current.get("count", 0) >= 3:
        lcp = current.get("avg_lcp", 0)
        if lcp > ALERT_THRESHOLDS["lcp"]["critical"]:
            active_alert = {"level": "CRITICAL", "metric": "LCP", "value": round(lcp, 2), "threshold": ALERT_THRESHOLDS["lcp"]["critical"]}
        elif lcp > ALERT_THRESHOLDS["lcp"]["warning"]:
            active_alert = {"level": "WARNING", "metric": "LCP", "value": round(lcp, 2), "threshold": ALERT_THRESHOLDS["lcp"]["warning"]}

    return {
        "alerts": alerts,
        "total": await db.performance_alerts.count_documents({}),
        "active_alert": active_alert,
    }



# ── Feature 3: Performance Budget per Page/Route ──────────────────────


@router.get("/admin/performance-guardian/budgets")
async def get_performance_budgets(request: Request):
    """Get all performance budgets (per-page and global)."""
    db = await _get_db()
    budgets = await ensure_default_performance_budgets(db)
    return {"budgets": budgets}


@router.post("/admin/performance-guardian/budgets")
async def create_performance_budget(request: Request):
    """Create or update a performance budget for a specific route."""
    db = await _get_db()
    body = await request.json()

    route = body.get("route", "*")
    budget = {
        "route": route,
        "label": body.get("label", route),
        "lcp_budget_ms": int(body.get("lcp_budget_ms", 1000)),
        "fcp_budget_ms": int(body.get("fcp_budget_ms", 1000)),
        "ttfb_budget_ms": int(body.get("ttfb_budget_ms", 500)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.performance_budgets.update_one(
        {"route": route},
        {"$set": budget},
        upsert=True
    )
    return {"success": True, "budget": budget}


@router.delete("/admin/performance-guardian/budgets/{route_encoded:path}")
async def delete_performance_budget(route_encoded: str, request: Request):
    """Delete a performance budget for a specific route."""
    db = await _get_db()
    import urllib.parse
    route = urllib.parse.unquote(route_encoded)
    if route == "*":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Cannot delete global default budget")
    # Try both with and without leading slash
    result = await db.performance_budgets.delete_one({"route": route})
    if result.deleted_count == 0 and not route.startswith("/"):
        result = await db.performance_budgets.delete_one({"route": "/" + route})
    return {"success": True, "deleted": result.deleted_count > 0}


@router.get("/admin/performance-guardian/budget-violations")
async def get_budget_violations(request: Request):
    """Check which routes are violating their performance budgets."""
    db = await _get_db()
    return await build_budget_violations_snapshot(db)
