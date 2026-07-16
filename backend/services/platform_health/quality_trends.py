"""
Executive Quality Trend Analytics — cross-dashboard quality trends for executive visibility.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from routes.db import db


async def get_quality_trend_snapshot(days: int = 30) -> Dict[str, Any]:
    """Compute quality trends across platform health, factory gate, SLO, and integrity."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now = datetime.now(timezone.utc)

    # Platform health scan history
    scans = await db.platform_health_scans.find(
        {"timestamp": {"$gte": cutoff}}, {"_id": 0, "score": 1, "grade": 1, "timestamp": 1, "issues_count": 1}
    ).sort("timestamp", -1).limit(200).to_list(200)
    scan_scores = [s.get("score", 0) for s in scans if s.get("score")]

    # Factory gate results
    gate_results = await db.factory_gate_results.find(
        {"created_at": {"$gte": cutoff}}, {"_id": 0, "status": 1, "created_at": 1, "test_pass_count": 1, "test_fail_count": 1}
    ).sort("created_at", -1).limit(200).to_list(200)
    gate_pass = sum(1 for g in gate_results if g.get("status") == "pass")

    # SLO mitigation history
    slo_history = await db.enterprise_slo_auto_mitigation_history.find(
        {"checked_at": {"$gte": cutoff}}, {"_id": 0, "result": 1, "p95_ms": 1, "checked_at": 1}
    ).sort("checked_at", -1).limit(200).to_list(200)
    slo_breaches = sum(1 for s in slo_history if s.get("result") == "breach_detected")

    # Enforcement runs
    enforcement_runs = await db.enterprise_standard_enforcement_history.find(
        {"started_at": {"$gte": cutoff}}, {"_id": 0, "status": 1, "final_score": 1, "started_at": 1}
    ).sort("started_at", -1).limit(50).to_list(50)
    enforcement_scores = [e.get("final_score", 0) for e in enforcement_runs if e.get("final_score")]

    # Build daily trend
    daily: Dict[str, Dict[str, Any]] = {}
    for s in scans:
        day = (s.get("timestamp") or "")[:10]
        if day:
            daily.setdefault(day, {"health_scores": [], "gate_pass": 0, "gate_total": 0, "slo_breaches": 0})
            daily[day]["health_scores"].append(s.get("score", 0))
    for g in gate_results:
        day = (g.get("created_at") or "")[:10]
        if day:
            daily.setdefault(day, {"health_scores": [], "gate_pass": 0, "gate_total": 0, "slo_breaches": 0})
            daily[day]["gate_total"] += 1
            if g.get("status") == "pass":
                daily[day]["gate_pass"] += 1
    for s in slo_history:
        day = (s.get("checked_at") or "")[:10]
        if day:
            daily.setdefault(day, {"health_scores": [], "gate_pass": 0, "gate_total": 0, "slo_breaches": 0})
            if s.get("result") == "breach_detected":
                daily[day]["slo_breaches"] += 1

    # Flatten daily data
    trend_points = []
    for day in sorted(daily.keys()):
        d = daily[day]
        scores = d["health_scores"]
        trend_points.append({
            "date": day,
            "avg_health_score": round(sum(scores) / len(scores), 1) if scores else None,
            "gate_pass_rate": round(d["gate_pass"] / max(d["gate_total"], 1) * 100, 1) if d["gate_total"] else None,
            "slo_breaches": d["slo_breaches"],
        })

    avg_health = round(sum(scan_scores) / max(len(scan_scores), 1), 1) if scan_scores else 0
    avg_enforcement = round(sum(enforcement_scores) / max(len(enforcement_scores), 1), 1) if enforcement_scores else 0

    return {
        "period_days": days,
        "generated_at": now.isoformat(),
        "summary": {
            "avg_health_score": avg_health,
            "health_grade": "A" if avg_health >= 90 else "B" if avg_health >= 75 else "C" if avg_health >= 60 else "D",
            "total_scans": len(scans),
            "gate_total_runs": len(gate_results),
            "gate_pass_rate": round(gate_pass / max(len(gate_results), 1) * 100, 1) if gate_results else 0,
            "slo_total_checks": len(slo_history),
            "slo_breach_count": slo_breaches,
            "slo_breach_rate": round(slo_breaches / max(len(slo_history), 1) * 100, 1) if slo_history else 0,
            "enforcement_runs": len(enforcement_runs),
            "avg_enforcement_score": avg_enforcement,
        },
        "trend": trend_points[-days:],
    }


async def get_drill_down(domain: str, days: int = 14) -> Dict[str, Any]:
    """Get detailed drill-down data for a specific quality domain."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if domain == "health":
        docs = await db.platform_health_scans.find(
            {"timestamp": {"$gte": cutoff}}, {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        return {"domain": "health", "records": docs}

    if domain == "gate":
        docs = await db.factory_gate_results.find(
            {"created_at": {"$gte": cutoff}}, {"_id": 0}
        ).sort("created_at", -1).limit(50).to_list(50)
        return {"domain": "gate", "records": docs}

    if domain == "slo":
        docs = await db.enterprise_slo_auto_mitigation_history.find(
            {"checked_at": {"$gte": cutoff}}, {"_id": 0}
        ).sort("checked_at", -1).limit(50).to_list(50)
        return {"domain": "slo", "records": docs}

    if domain == "enforcement":
        docs = await db.enterprise_standard_enforcement_history.find(
            {"started_at": {"$gte": cutoff}}, {"_id": 0}
        ).sort("started_at", -1).limit(30).to_list(30)
        return {"domain": "enforcement", "records": docs}

    return {"domain": domain, "records": [], "error": "Unknown domain"}
