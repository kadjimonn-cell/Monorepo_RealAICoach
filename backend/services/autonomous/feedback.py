def feedback_issue_score(issue_type: str, metric_value: float, threshold: float) -> int:
    if threshold <= 0:
        return 0
    ratio = metric_value / threshold
    if issue_type == "route_dropoff":
        return min(100, int(round(ratio * 65 + 20)))
    if issue_type == "slow_interaction":
        return min(100, int(round(ratio * 55 + 25)))
    if issue_type == "runtime_errors":
        return min(100, int(round(ratio * 60 + 20)))
    return min(100, int(round(ratio * 50)))
