from datetime import datetime, timezone
from typing import Dict


def prune_window(window: list, max_age_seconds: int):
    if not window:
        return
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    while window and window[0].get("ts", 0) < cutoff:
        window.pop(0)


def compute_live_metrics(policy: dict, monitor_window: Dict[str, list]) -> dict:
    window_sec = policy.get("window_seconds", 300)

    for key in monitor_window:
        prune_window(monitor_window[key], window_sec)

    lats = [e["value"] for e in monitor_window["api_latency"] if "value" in e]
    avg_lat = round(sum(lats) / len(lats), 1) if lats else 0
    p95_lat = round(sorted(lats)[int(len(lats) * 0.95)], 1) if lats else 0

    errs = monitor_window["api_errors"]
    total_reqs = len(lats) + len(errs)
    error_count = len(errs)
    error_rate = round((error_count / max(total_reqs, 1)) * 100, 1)

    crashes = monitor_window["ui_crashes"]
    crash_count = len(crashes)
    window_min = max(window_sec / 60, 1)
    crash_rate_per_min = round(crash_count / window_min, 1)

    flows = monitor_window["user_flows"]
    completed = sum(1 for f in flows if f.get("completed"))
    started = len(flows)
    completion_rate = round((completed / max(started, 1)) * 100, 1)
    dropoff_rate = round(100 - completion_rate, 1) if started > 0 else 0

    endpoint_stats: Dict[str, dict] = {}
    for entry in monitor_window["api_latency"]:
        ep = entry.get("endpoint", "unknown")
        if ep not in endpoint_stats:
            endpoint_stats[ep] = {"latencies": [], "count": 0}
        endpoint_stats[ep]["latencies"].append(entry["value"])
        endpoint_stats[ep]["count"] += 1
    for entry in monitor_window["api_errors"]:
        ep = entry.get("endpoint", "unknown")
        if ep not in endpoint_stats:
            endpoint_stats[ep] = {"latencies": [], "count": 0, "errors": 0}
        endpoint_stats[ep].setdefault("errors", 0)
        endpoint_stats[ep]["errors"] = endpoint_stats[ep].get("errors", 0) + 1

    endpoints_summary = {}
    for ep, data in endpoint_stats.items():
        ep_lats = data["latencies"]
        endpoints_summary[ep] = {
            "avg_latency_ms": round(sum(ep_lats) / len(ep_lats), 1) if ep_lats else 0,
            "request_count": data["count"],
            "error_count": data.get("errors", 0),
        }

    return {
        "window_seconds": window_sec,
        "api_latency": {"avg_ms": avg_lat, "p95_ms": p95_lat, "sample_count": len(lats)},
        "error_rate": {"error_count": error_count, "total_requests": total_reqs, "rate_pct": error_rate},
        "ui_crashes": {"count": crash_count, "rate_per_min": crash_rate_per_min},
        "user_flows": {
            "started": started,
            "completed": completed,
            "completion_rate_pct": completion_rate,
            "dropoff_rate_pct": dropoff_rate,
        },
        "endpoints": endpoints_summary,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def detect_anomalies(metrics: dict, policy: dict) -> list:
    anomalies = []
    baseline_ms = policy.get("latency_baseline_ms", 500)
    spike_factor = policy.get("latency_spike_factor", 3.0)
    err_threshold = policy.get("error_rate_threshold_pct", 5.0)
    crash_threshold = policy.get("ui_crash_threshold_per_min", 10)
    dropoff_threshold = policy.get("flow_dropoff_threshold_pct", 50.0)
    now_iso = datetime.now(timezone.utc).isoformat()

    avg_lat = metrics["api_latency"]["avg_ms"]
    if avg_lat > 0 and avg_lat > baseline_ms * spike_factor:
        anomalies.append(
            {
                "type": "latency_spike",
                "severity": "critical",
                "detected_at": now_iso,
                "detail": f"Avg latency {avg_lat}ms exceeds {baseline_ms * spike_factor}ms ({spike_factor}x baseline)",
                "value": avg_lat,
                "threshold": baseline_ms * spike_factor,
            }
        )

    err_rate = metrics["error_rate"]["rate_pct"]
    if metrics["error_rate"]["total_requests"] > 0 and err_rate > err_threshold:
        anomalies.append(
            {
                "type": "error_rate_spike",
                "severity": "critical",
                "detected_at": now_iso,
                "detail": f"Error rate {err_rate}% exceeds {err_threshold}% threshold",
                "value": err_rate,
                "threshold": err_threshold,
            }
        )

    crash_rate = metrics["ui_crashes"]["rate_per_min"]
    if crash_rate > crash_threshold:
        anomalies.append(
            {
                "type": "ui_crash_spike",
                "severity": "high",
                "detected_at": now_iso,
                "detail": f"UI crash rate {crash_rate}/min exceeds {crash_threshold}/min threshold",
                "value": crash_rate,
                "threshold": crash_threshold,
            }
        )

    dropoff = metrics["user_flows"]["dropoff_rate_pct"]
    if metrics["user_flows"]["started"] >= 5 and dropoff > dropoff_threshold:
        anomalies.append(
            {
                "type": "flow_dropoff",
                "severity": "high",
                "detected_at": now_iso,
                "detail": f"User flow drop-off {dropoff}% exceeds {dropoff_threshold}% threshold",
                "value": dropoff,
                "threshold": dropoff_threshold,
            }
        )

    return anomalies
