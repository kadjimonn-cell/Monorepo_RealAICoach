import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")


def test_gps_health_does_not_false_degrade_when_runtime_is_live():
    """If runtime is live and dependencies are healthy, freshness must use runtime last_success_at.

    This prevents false degraded mode when global_platform_state.updated_at is old but
    the GPS runtime feed is currently healthy.
    """

    state_res = requests.get(f"{BASE_URL}/api/gps/state", timeout=20)
    assert state_res.status_code == 200, f"gps/state failed: {state_res.status_code}"
    state_payload = state_res.json()
    runtime = state_payload.get("_gps_runtime") or {}

    health_res = requests.get(f"{BASE_URL}/api/gps/health", timeout=20)
    assert health_res.status_code == 200, f"gps/health failed: {health_res.status_code}"
    health_payload = health_res.json()

    deps = health_payload.get("dependencies") or {}
    deps_all_healthy = all((row or {}).get("status") == "healthy" for row in deps.values())
    failed_checks = (health_payload.get("completeness") or {}).get("failed_checks") or []

    if runtime.get("mode") == "live" and deps_all_healthy:
        assert "freshness_contract" not in failed_checks, (
            "freshness_contract should not fail when runtime is live and dependencies are healthy"
        )
        assert health_payload.get("mode") == "live", (
            f"Expected gps/health mode=live, got {health_payload.get('mode')} with checks={failed_checks}"
        )
