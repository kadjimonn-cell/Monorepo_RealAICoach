"""
Factory Gate Health Service — stores CI pipeline gate results and computes PASS/FAIL trends.
"""
from datetime import datetime, timezone, timedelta
from routes.db import db


async def record_gate_result(result: dict) -> dict:
    """Record a CI gate run result."""
    doc = {
        "gate_id": result.get("gate_id", f"gate_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"),
        "status": result.get("status", "unknown"),  # pass | fail | partial
        "pipeline": result.get("pipeline", "ai-software-factory"),
        "trigger": result.get("trigger", "manual"),  # pr | push | manual | schedule
        "branch": result.get("branch", "main"),
        "commit_sha": result.get("commit_sha", ""),
        "stages": result.get("stages", []),
        "performance_score": result.get("performance_score"),
        "fcp_ms": result.get("fcp_ms"),
        "lcp_ms": result.get("lcp_ms"),
        "test_pass_count": result.get("test_pass_count", 0),
        "test_fail_count": result.get("test_fail_count", 0),
        "duration_seconds": result.get("duration_seconds", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.factory_gate_results.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_gate_history(limit: int = 30) -> list:
    """Get recent gate results."""
    docs = await db.factory_gate_results.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return docs


async def get_gate_trends(days: int = 14) -> dict:
    """Compute PASS/FAIL trends for the factory gate."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.factory_gate_results.find(
        {"created_at": {"$gte": cutoff}}, {"_id": 0, "status": 1, "created_at": 1, "pipeline": 1, "duration_seconds": 1, "test_pass_count": 1, "test_fail_count": 1}
    ).sort("created_at", -1).to_list(500)

    total = len(docs)
    passed = sum(1 for d in docs if d.get("status") == "pass")
    failed = sum(1 for d in docs if d.get("status") == "fail")
    partial = total - passed - failed

    avg_duration = sum(d.get("duration_seconds", 0) for d in docs) / max(total, 1)
    total_tests_passed = sum(d.get("test_pass_count", 0) for d in docs)
    total_tests_failed = sum(d.get("test_fail_count", 0) for d in docs)

    # Daily breakdown
    daily = {}
    for d in docs:
        day = d.get("created_at", "")[:10]
        if day not in daily:
            daily[day] = {"pass": 0, "fail": 0, "partial": 0}
        s = d.get("status", "unknown")
        if s == "pass":
            daily[day]["pass"] += 1
        elif s == "fail":
            daily[day]["fail"] += 1
        else:
            daily[day]["partial"] += 1

    # Streak
    pass_streak = 0
    for d in docs:
        if d.get("status") == "pass":
            pass_streak += 1
        else:
            break

    return {
        "period_days": days,
        "total_runs": total,
        "passed": passed,
        "failed": failed,
        "partial": partial,
        "pass_rate": round(passed / max(total, 1) * 100, 1),
        "avg_duration_seconds": round(avg_duration, 1),
        "total_tests_passed": total_tests_passed,
        "total_tests_failed": total_tests_failed,
        "current_pass_streak": pass_streak,
        "daily_breakdown": daily,
        "last_result": docs[0] if docs else None,
    }


async def get_gate_summary() -> dict:
    """Quick summary for the admin card."""
    last = await db.factory_gate_results.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    trends = await get_gate_trends(days=7)
    return {
        "last_run": last,
        "week_trends": {
            "total_runs": trends["total_runs"],
            "pass_rate": trends["pass_rate"],
            "current_streak": trends["current_pass_streak"],
            "failed": trends["failed"],
        },
    }
