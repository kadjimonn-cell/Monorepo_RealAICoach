from typing import Optional


def extract_perf_snapshot(snapshot: Optional[dict]) -> dict:
    payload = snapshot or {}
    api_overall_avg_ms = payload.get("api_overall_avg_ms", payload.get("overall_avg_ms", 0))
    try:
        api_overall_avg_ms = round(float(api_overall_avg_ms or 0), 1)
    except Exception:
        api_overall_avg_ms = 0.0
    return {
        "api_overall_avg_ms": api_overall_avg_ms,
        "alert_count": int(payload.get("alert_count", 0) or 0),
        "status": payload.get("status", "UNKNOWN"),
        "audited_at": payload.get("audited_at"),
        "api_metrics": payload.get("api_metrics") or payload.get("endpoints") or {},
    }


def extract_tests_snapshot(result: Optional[dict]) -> dict:
    payload = result or {}
    backend_pytest = ((payload.get("details") or {}).get("backend_pytest") or {}) if isinstance(payload, dict) else {}
    tests_passed = backend_pytest.get("tests_passed")
    try:
        tests_passed = int(tests_passed) if tests_passed is not None else None
    except Exception:
        tests_passed = None
    return {
        "status": payload.get("status", "UNKNOWN"),
        "tests_passed": tests_passed,
        "suite": backend_pytest.get("suite"),
        "return_code": backend_pytest.get("return_code"),
    }


def evaluate_drift_signals(policy: dict, baseline: dict, references: dict, current_perf: dict, current_tests: dict) -> list:
    signals = []
    mode = str(policy.get("baseline_mode") or "dual").lower()
    perf_threshold_pct = float(policy.get("performance_drift_pct", 20.0))
    tests_drop_pct = float(policy.get("tests_passed_drop_pct", 5.0))
    pass_rate_floor = float(policy.get("recent_pass_rate_floor_pct", 80.0))

    current_perf_ms = float(current_perf.get("api_overall_avg_ms") or 0)
    current_tests_status = str(current_tests.get("status") or "UNKNOWN")
    current_tests_passed = current_tests.get("tests_passed")

    perf_candidates = []
    if mode in {"locked", "dual"} and baseline.get("performance_baseline_ms"):
        perf_candidates.append(("locked", float(baseline.get("performance_baseline_ms") or 0)))
    if mode in {"rolling", "dual"} and references.get("rolling_performance_ms"):
        perf_candidates.append(("rolling", float(references.get("rolling_performance_ms") or 0)))

    for source, baseline_ms in perf_candidates:
        if current_perf_ms <= 0 or baseline_ms <= 0:
            continue
        allowed_ms = round(baseline_ms * (1 + perf_threshold_pct / 100), 1)
        if current_perf_ms > allowed_ms:
            signals.append(
                {
                    "type": "performance_drift",
                    "source": source,
                    "current_ms": current_perf_ms,
                    "baseline_ms": round(baseline_ms, 1),
                    "allowed_ms": allowed_ms,
                    "drift_pct": round(((current_perf_ms - baseline_ms) / baseline_ms) * 100, 1),
                }
            )

    rolling_pass_rate = references.get("rolling_test_pass_rate_pct")
    if current_tests_status != "PASS" and (rolling_pass_rate is None or rolling_pass_rate >= pass_rate_floor):
        signals.append(
            {
                "type": "test_status_drift",
                "current_status": current_tests_status,
                "historical_pass_rate_pct": rolling_pass_rate,
                "pass_rate_floor_pct": pass_rate_floor,
            }
        )

    tests_candidates = []
    if mode in {"locked", "dual"} and baseline.get("tests_passed_baseline"):
        tests_candidates.append(("locked", float(baseline.get("tests_passed_baseline") or 0)))
    if mode in {"rolling", "dual"} and references.get("rolling_tests_passed"):
        tests_candidates.append(("rolling", float(references.get("rolling_tests_passed") or 0)))

    if current_tests_passed is not None:
        current_tests_passed = float(current_tests_passed)
        for source, baseline_passed in tests_candidates:
            if baseline_passed <= 0:
                continue
            minimum_expected = round(baseline_passed * (1 - tests_drop_pct / 100), 1)
            if current_tests_passed < minimum_expected:
                signals.append(
                    {
                        "type": "tests_passed_drift",
                        "source": source,
                        "current_tests_passed": current_tests_passed,
                        "baseline_tests_passed": round(baseline_passed, 1),
                        "minimum_expected": minimum_expected,
                    }
                )

    return signals
