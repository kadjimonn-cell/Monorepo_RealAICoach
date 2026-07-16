from typing import Dict, Set


CONTROLLED_SCALING_SUBSYSTEMS = [
    "baseline_lock",
    "regression_testing",
    "test_first_development",
    "performance_budget",
    "canary_deployment",
    "realtime_monitoring",
    "auto_rollback",
]


def get_controlled_scaling_state(config: dict) -> dict:
    return config.get(
        "controlled_scaling",
        {
            "active": False,
            "activated_at": None,
            "activated_by": None,
        },
    )


def enforce_controlled_scaling(
    config: dict,
    baseline: dict,
    mandatory_gates: Set[str],
) -> dict:
    cs = get_controlled_scaling_state(config)
    if not cs.get("active"):
        return {
            "corrections": [],
            "config": config,
            "baseline": baseline,
            "mandatory_gates": mandatory_gates,
            "config_changed": False,
            "baseline_changed": False,
            "gates_changed": False,
        }

    updated_config = {**config}
    updated_baseline = {**baseline}
    updated_gates = set(mandatory_gates)
    corrections = []
    config_changed = False
    baseline_changed = False
    gates_changed = False

    if not updated_baseline.get("locked"):
        updated_baseline["locked"] = True
        corrections.append("baseline_lock: re-locked")
        baseline_changed = True

    if "coverage" not in updated_gates:
        updated_gates.add("coverage")
        corrections.append("regression_testing: coverage gate re-added to mandatory")
        gates_changed = True

    monitor_policy = {**(updated_config.get("monitor_policy") or {})}
    if not monitor_policy.get("auto_heal_on_anomaly", True):
        monitor_policy["auto_heal_on_anomaly"] = True
        updated_config["monitor_policy"] = monitor_policy
        corrections.append("realtime_monitoring: auto_heal re-enabled")
        config_changed = True

    canary_policy = {**(updated_config.get("canary_policy") or {})}
    if not canary_policy.get("auto_rollback", True):
        canary_policy["auto_rollback"] = True
        updated_config["canary_policy"] = canary_policy
        corrections.append("canary_deployment: auto_rollback re-enabled")
        config_changed = True

    coverage_policy = {**(updated_config.get("coverage_policy") or {})}
    if not coverage_policy.get("fail_on_drop", True):
        coverage_policy["fail_on_drop"] = True
        updated_config["coverage_policy"] = coverage_policy
        corrections.append("performance_budget: fail_on_drop re-enabled")
        config_changed = True
    if not coverage_policy.get("fail_on_missing_tests", True):
        coverage_policy["fail_on_missing_tests"] = True
        updated_config["coverage_policy"] = coverage_policy
        corrections.append("test_first_development: fail_on_missing_tests re-enabled")
        config_changed = True

    deploy_policy = {**(updated_config.get("deployment_policy") or {})}
    if deploy_policy.get("max_error_rate_pct", 5) > 5:
        deploy_policy["max_error_rate_pct"] = 5
        updated_config["deployment_policy"] = deploy_policy
        corrections.append("performance_budget: max_error_rate capped at 5%")
        config_changed = True

    return {
        "corrections": corrections,
        "config": updated_config,
        "baseline": updated_baseline,
        "mandatory_gates": updated_gates,
        "config_changed": config_changed,
        "baseline_changed": baseline_changed,
        "gates_changed": gates_changed,
    }


def check_subsystem_statuses(config: dict, baseline: dict, mandatory_gates: Set[str]) -> Dict[str, dict]:
    monitor_policy = config.get("monitor_policy", {})
    canary_policy = config.get("canary_policy", {})
    coverage_policy = config.get("coverage_policy", {})
    deploy_policy = config.get("deployment_policy", {})

    return {
        "baseline_lock": {
            "enforced": bool(baseline.get("locked")),
            "status": baseline.get("status", "UNKNOWN"),
            "detail": "PASS baseline locked and immutable" if baseline.get("locked") else "Baseline NOT locked",
        },
        "regression_testing": {
            "enforced": "coverage" in mandatory_gates and coverage_policy.get("fail_on_drop", False),
            "detail": "Coverage gate mandatory + fail-on-drop active",
        },
        "test_first_development": {
            "enforced": coverage_policy.get("fail_on_missing_tests", False),
            "detail": "Feature builds blocked without tests" if coverage_policy.get("fail_on_missing_tests") else "Missing tests not enforced",
        },
        "performance_budget": {
            "enforced": deploy_policy.get("max_error_rate_pct", 99) <= 5,
            "max_error_rate_pct": deploy_policy.get("max_error_rate_pct", 5),
            "max_avg_response_ms": deploy_policy.get("max_avg_response_ms", 5000),
            "detail": "Deployment gate + perf audit active with strict thresholds",
        },
        "canary_deployment": {
            "enforced": canary_policy.get("auto_rollback", False),
            "auto_promote": canary_policy.get("auto_promote", True),
            "auto_rollback": canary_policy.get("auto_rollback", True),
            "detail": "Canary staged rollout with auto-rollback on instability",
        },
        "realtime_monitoring": {
            "enforced": monitor_policy.get("auto_heal_on_anomaly", False),
            "auto_heal": monitor_policy.get("auto_heal_on_anomaly", False),
            "alert_admin": monitor_policy.get("alert_admin_on_anomaly", True),
            "detail": "Live anomaly detection + auto-heal pipeline active",
        },
        "auto_rollback": {
            "enforced": (
                canary_policy.get("auto_rollback", False)
                and monitor_policy.get("auto_heal_on_anomaly", False)
                and coverage_policy.get("fail_on_drop", False)
            ),
            "detail": "All rollback triggers armed (canary + monitor + coverage drop)",
        },
    }
