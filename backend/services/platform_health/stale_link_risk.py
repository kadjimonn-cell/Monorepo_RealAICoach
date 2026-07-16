"""Executive stale-link risk score snapshot."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from routes.db import db


def _to_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


async def get_stale_link_risk_snapshot() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    scans = await db.platform_health_scans.find({}, {"_id": 0}).sort("scanned_at", -1).limit(60).to_list(60)
    route_rows = await db.route_health_history.find({"timestamp": {"$gte": cutoff_7d}}, {"_id": 0, "timestamp": 1, "direct_integrity_pct": 1, "redirect_success_pct": 1}).sort("timestamp", -1).limit(40).to_list(40)
    fixes = await db.platform_health_fixes.find({}, {"_id": 0, "fixed_at": 1, "before": 1, "after": 1, "fix_time": 1}).sort("fixed_at", -1).limit(40).to_list(40)

    latest = scans[0] if scans else {}
    recent_scans = [row for row in scans if (_to_dt(row.get("scanned_at") or row.get("_stored_at")) or now) >= now - timedelta(days=7)]
    stale_counts = [int(((row.get("stale_urls") or {}).get("count", 0) or 0)) for row in recent_scans]
    latest_count = int(((latest.get("stale_urls") or {}).get("count", 0) or 0))
    avg_7d = round(sum(stale_counts) / len(stale_counts), 2) if stale_counts else float(latest_count)
    peak_7d = max(stale_counts) if stale_counts else latest_count
    latest_issues = (latest.get("stale_urls") or {}).get("issues") or []
    sample_files: List[Dict[str, Any]] = []
    for issue in latest_issues[:5]:
        sample_files.append({
            "file": str(issue.get("file") or issue.get("path") or "unknown"),
            "line": issue.get("line"),
            "pattern": issue.get("pattern") or issue.get("match") or "stale-reference",
        })

    route_scores = []
    for row in route_rows:
        direct = float(row.get("direct_integrity_pct", 0) or 0)
        redirect = float(row.get("redirect_success_pct", 0) or 0)
        route_scores.append(round((direct * 0.55) + (redirect * 0.45), 2))
    route_score = round(sum(route_scores) / len(route_scores), 2) if route_scores else 100.0

    recurrence_count = 0
    previous_stale = False
    for row in reversed(recent_scans):
        current = int(((row.get("stale_urls") or {}).get("count", 0) or 0)) > 0 or bool((row.get("build") or {}).get("stale"))
        if current and not previous_stale:
            recurrence_count += 1
        previous_stale = current

    mttr_minutes = 0.0
    fix_samples = []
    for fix in fixes:
        fixed_at = _to_dt(fix.get("fixed_at") or fix.get("_stored_at"))
        if not fixed_at or fixed_at < now - timedelta(days=7):
            continue
        before = fix.get("before") or {}
        if int(before.get("stale_urls", 0) or 0) <= 0:
            continue
        sample = max(float(fix.get("fix_time", 0) or 0) / 60.0, 0.0)
        fix_samples.append(sample)
    if fix_samples:
        mttr_minutes = round(sum(fix_samples) / len(fix_samples), 2)

    # 7-day risk trend (daily, oldest -> latest)
    recent_by_day: Dict[str, Dict[str, Any]] = {}
    for row in sorted(
        recent_scans,
        key=lambda r: (_to_dt(r.get("scanned_at") or r.get("_stored_at")) or now),
    ):
        row_dt = _to_dt(row.get("scanned_at") or row.get("_stored_at")) or now
        recent_by_day[row_dt.date().isoformat()] = row
    trend_source = list(recent_by_day.items())[-7:]
    if not trend_source:
        trend_source = [(now.date().isoformat(), latest)]

    trend_7d: List[Dict[str, Any]] = []
    trend_counts_prefix: List[int] = []
    trend_recurrence = 0
    trend_prev_stale = False
    for day_key, row in trend_source:
        point_count = int(((row.get("stale_urls") or {}).get("count", 0) or 0))
        trend_counts_prefix.append(point_count)
        point_avg = sum(trend_counts_prefix) / max(1, len(trend_counts_prefix))
        point_is_stale = point_count > 0 or bool((row.get("build") or {}).get("stale"))
        if point_is_stale and not trend_prev_stale:
            trend_recurrence += 1
        trend_prev_stale = point_is_stale

        point_score = 100.0
        point_score -= min(point_count * 7.5, 45.0)
        point_score -= min(point_avg * 4.0, 20.0)
        point_score -= min(trend_recurrence * 8.0, 16.0)
        point_score -= max(0.0, (95.0 - route_score) * 0.75)
        point_score -= min(mttr_minutes / 6.0, 10.0)

        trend_7d.append({
            "date": day_key,
            "score": round(_clamp(point_score), 1),
            "stale_urls": point_count,
        })

    risk_delta_7d = round((trend_7d[-1]["score"] - trend_7d[0]["score"]), 1) if len(trend_7d) > 1 else 0.0

    risk_score = 100.0
    risk_score -= min(latest_count * 7.5, 45.0)
    risk_score -= min(avg_7d * 4.0, 20.0)
    risk_score -= min(recurrence_count * 8.0, 16.0)
    risk_score -= max(0.0, (95.0 - route_score) * 0.75)
    risk_score -= min(mttr_minutes / 6.0, 10.0)
    risk_score = round(_clamp(risk_score), 1)

    if risk_score >= 85:
        band, summary = "low", "Route references look stable and recent scans are clean."
    elif risk_score >= 65:
        band, summary = "medium", "A few stale references are recurring and should be cleaned before they spread."
    elif risk_score >= 40:
        band, summary = "high", "Stale link risk is rising across recent scans and may impact admin route integrity."
    else:
        band, summary = "critical", "Stale references are actively degrading route confidence and need immediate cleanup."

    drivers = []
    if latest_count:
        drivers.append(f"Latest scan found {latest_count} stale URL reference{'s' if latest_count != 1 else ''}.")
    if recurrence_count:
        drivers.append(f"Stale-link state recurred {recurrence_count} time{'s' if recurrence_count != 1 else ''} in the last 7 days.")
    if route_score < 95:
        drivers.append(f"Route health average is {route_score}/100, reducing confidence in link freshness.")
    if mttr_minutes:
        drivers.append(f"Mean stale-link recovery time is {mttr_minutes} minutes.")
    if not drivers:
        drivers.append("No stale-link regressions detected in the latest executive window.")

    return {
        "generated_at": now.isoformat(),
        "score": risk_score,
        "band": band,
        "summary": summary,
        "metrics": {
            "latest_stale_urls": latest_count,
            "avg_stale_urls_7d": avg_7d,
            "peak_stale_urls_7d": peak_7d,
            "recurrence_count_7d": recurrence_count,
            "route_health_score_7d": route_score,
            "mttr_minutes_7d": mttr_minutes,
            "risk_score_delta_7d": risk_delta_7d,
        },
        "trend_7d": trend_7d,
        "drivers": drivers,
        "sample_files": sample_files,
        "latest_scan": {
            "scanned_at": latest.get("scanned_at") or latest.get("_stored_at"),
            "grade": latest.get("grade") or "n/a",
            "build_stale": bool((latest.get("build") or {}).get("stale")),
        },
        "recommended_action": "Open Platform Health and clear the top stale references before the next admin audit run.",
    }
