from typing import Dict, List


def score_predictive_confidence(
    evidence_count: int,
    recent_fail_rate_pct: float,
    correlated_sources: int,
    unresolved_count: int,
) -> int:
    evidence_component = min(36.0, float(max(evidence_count, 0)) * 5.5)
    fail_rate_component = min(24.0, max(0.0, float(recent_fail_rate_pct)) * 0.6)
    source_component = min(18.0, max(0, int(correlated_sources)) * 6.0)
    unresolved_component = min(12.0, max(0, int(unresolved_count)) * 2.0)
    confidence = 20.0 + evidence_component + fail_rate_component + source_component + unresolved_component
    return int(max(0, min(99, round(confidence))))


def top_components(component_counts: Dict[str, int], limit: int = 3) -> List[str]:
    ranked = sorted(component_counts.items(), key=lambda item: item[1], reverse=True)
    return [name for name, _ in ranked[: max(1, int(limit))] if name]


def build_prediction_candidates(signal_profile: dict, min_pattern_occurrences: int) -> list:
    failure_types = signal_profile.get("failure_type_counts", {}) or {}
    drift_types = signal_profile.get("drift_signal_counts", {}) or {}
    monitor_types = signal_profile.get("monitor_anomaly_counts", {}) or {}
    feedback_types = signal_profile.get("feedback_issue_counts", {}) or {}
    pipeline_fail_rate = float(signal_profile.get("pipeline_fail_rate_pct") or 0)
    unresolved = int(signal_profile.get("unresolved_failures") or 0)

    def _sum_types(source: Dict[str, int], keys: List[str]) -> int:
        return sum(int(source.get(k, 0) or 0) for k in keys)

    candidates = []

    test_evidence = (
        _sum_types(failure_types, ["assertion_failure", "gate_failure", "test_drift", "feature_build_blocked"])
        + _sum_types(drift_types, ["tests_passed_drift", "test_status_drift"])
    )
    if test_evidence >= min_pattern_occurrences:
        confidence = score_predictive_confidence(
            evidence_count=test_evidence,
            recent_fail_rate_pct=pipeline_fail_rate,
            correlated_sources=2 if _sum_types(drift_types, ["tests_passed_drift", "test_status_drift"]) > 0 else 1,
            unresolved_count=unresolved,
        )
        candidates.append(
            {
                "predicted_failure_type": "test_regression",
                "confidence": confidence,
                "evidence_count": test_evidence,
                "likely_components": top_components(signal_profile.get("component_counts", {})),
                "recommended_action_key": "stabilize_pipeline",
                "recommended_preemptive_fix": "Run preemptive full pipeline and remediate failing gates before user-facing breakage.",
                "validation_plan": "Run tests gate and verify STATUS=PASS.",
            }
        )

    perf_evidence = (
        _sum_types(drift_types, ["performance_drift"])
        + _sum_types(monitor_types, ["latency_spike", "error_rate_spike", "perf_degradation"])
    )
    if perf_evidence >= min_pattern_occurrences:
        confidence = score_predictive_confidence(
            evidence_count=perf_evidence,
            recent_fail_rate_pct=max(pipeline_fail_rate, float(signal_profile.get("monitor_alert_rate_pct") or 0)),
            correlated_sources=2 if _sum_types(drift_types, ["performance_drift"]) > 0 else 1,
            unresolved_count=unresolved,
        )
        candidates.append(
            {
                "predicted_failure_type": "performance_degradation",
                "confidence": confidence,
                "evidence_count": perf_evidence,
                "likely_components": top_components(signal_profile.get("component_counts", {})),
                "recommended_action_key": "optimize_drift",
                "recommended_preemptive_fix": "Execute drift optimization cycle to prevent upcoming latency/error regressions.",
                "validation_plan": "Re-run tests and verify latency/error thresholds remain healthy.",
            }
        )

    runtime_evidence = (
        _sum_types(failure_types, ["exception_crash", "async_timing_issue", "db_connection_failure"])
        + _sum_types(monitor_types, ["ui_crash_spike", "error_rate_spike"]) 
        + _sum_types(feedback_types, ["runtime_errors", "slow_interaction"])
    )
    if runtime_evidence >= min_pattern_occurrences:
        confidence = score_predictive_confidence(
            evidence_count=runtime_evidence,
            recent_fail_rate_pct=max(pipeline_fail_rate, float(signal_profile.get("feedback_friction_rate_pct") or 0)),
            correlated_sources=3 if _sum_types(feedback_types, ["runtime_errors", "slow_interaction"]) > 0 else 2,
            unresolved_count=unresolved,
        )
        candidates.append(
            {
                "predicted_failure_type": "runtime_stability_risk",
                "confidence": confidence,
                "evidence_count": runtime_evidence,
                "likely_components": top_components(signal_profile.get("component_counts", {})),
                "recommended_action_key": "feedback_hardening",
                "recommended_preemptive_fix": "Run feedback-loop hardening to generate preventive fixes for friction and runtime error hotspots.",
                "validation_plan": "Run validation + tests gates after hardening.",
            }
        )

    candidates.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return candidates
