import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")


def _health() -> dict:
    res = requests.get(
        f"{BASE_URL}/_preview/health",
        headers={"X-E2E-Test-Bypass": "playwright-e2e"},
        timeout=25,
    )
    assert res.status_code == 200, f"_preview/health failed: {res.status_code}"
    return res.json()


def test_preview_health_reports_non_stale_reason():
    data = _health()
    dr = data.get("dist_runtime") or {}
    assert dr.get("last_reason") != "fingerprint_changed_serving_last_known_good", (
        "stale-serving reason must be blocked by platform stale guardrails"
    )


def test_preview_health_has_build_state_and_bundle_hash():
    data = _health()
    build_state = data.get("build_state") or {}
    assert build_state, "build_state must be present"
    assert build_state.get("source_fingerprint"), "build_state.source_fingerprint missing"
    assert build_state.get("index_bundle"), "build_state.index_bundle missing"
    assert data.get("active_bundle_hash"), "active_bundle_hash missing"


def test_preview_root_sends_active_bundle_hash_header():
    res = requests.get(
        f"{BASE_URL}/",
        headers={"X-E2E-Test-Bypass": "playwright-e2e"},
        timeout=25,
    )
    assert res.status_code == 200, f"preview root failed: {res.status_code}"
    assert res.headers.get("x-rac-dist-bundle-hash"), "x-rac-dist-bundle-hash header missing"
