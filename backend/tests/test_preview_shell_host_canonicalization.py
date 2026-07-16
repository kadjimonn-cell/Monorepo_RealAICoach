"""
Preview Shell Host Canonicalization Tests

These tests verify the stale wrapper path recovery and host canonicalization
features implemented to prevent stale code being served in preview environments.

Key behaviors tested:
1. Wrapper artifact paths (/wo, /loading-preview, /s/*) redirect to root with recovery marker
2. _preview/health endpoint reflects runtime request host, not stale startup host
3. Normal routes (/, /verify) are not affected by recovery middleware
"""

import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")


def _expected_host() -> str:
    return BASE_URL.replace("https://", "").replace("http://", "").split("/")[0]


def test_wo_path_recovers_to_root_with_marker():
    """Checkpoint D: /wo wrapper path must redirect to root with previewHostRecovered marker."""
    res = requests.get(
        f"{BASE_URL}/wo",
        headers={
            "accept": "text/html",
            "sec-fetch-dest": "document",
        },
        allow_redirects=False,
        timeout=20,
    )

    assert res.status_code in (301, 302, 307, 308), f"Expected redirect, got {res.status_code}"
    location = str(res.headers.get("location") or "")
    assert "previewHostRecovered=1" in location, f"Expected recovery marker in redirect location, got {location}"
    assert "/wo" not in location, f"Expected /wo to be canonicalized away, got {location}"
    
    # Verify recovery header is set
    recovery_header = res.headers.get("x-rac-wrapper-path-recovered", "")
    assert recovery_header == "/wo", f"Expected x-rac-wrapper-path-recovered=/wo, got {recovery_header}"


def test_loading_preview_path_recovers_to_root():
    """/loading-preview artifact path must redirect to root with recovery marker."""
    res = requests.get(
        f"{BASE_URL}/loading-preview",
        headers={
            "accept": "text/html",
            "sec-fetch-dest": "document",
        },
        allow_redirects=False,
        timeout=20,
    )

    assert res.status_code in (301, 302, 307, 308), f"Expected redirect, got {res.status_code}"
    location = str(res.headers.get("location") or "")
    assert "previewHostRecovered=1" in location, f"Expected recovery marker, got {location}"
    
    recovery_header = res.headers.get("x-rac-wrapper-path-recovered", "")
    assert recovery_header == "/loading-preview", f"Expected recovery header, got {recovery_header}"


def test_s_artifact_path_recovers_to_root():
    """/s/* artifact paths must redirect to root with recovery marker."""
    res = requests.get(
        f"{BASE_URL}/s/test-artifact",
        headers={
            "accept": "text/html",
            "sec-fetch-dest": "document",
        },
        allow_redirects=False,
        timeout=20,
    )

    assert res.status_code in (301, 302, 307, 308), f"Expected redirect, got {res.status_code}"
    location = str(res.headers.get("location") or "")
    assert "previewHostRecovered=1" in location, f"Expected recovery marker, got {location}"
    
    recovery_header = res.headers.get("x-rac-wrapper-path-recovered", "")
    assert "/s/" in recovery_header, f"Expected /s/ in recovery header, got {recovery_header}"


def test_preview_health_reports_runtime_expected_host_not_stale_env_host():
    """Health endpoint must reflect runtime request host, not stale startup expected host."""
    expected_host = _expected_host()
    res = requests.get(
        f"{BASE_URL}/_preview/health",
        headers={"x-forwarded-host": expected_host},
        timeout=20,
    )
    assert res.status_code == 200, f"Expected 200 from _preview/health, got {res.status_code}"
    payload = res.json()
    reported = str(payload.get("expected_preview_host") or "")
    assert reported == expected_host, f"expected_preview_host mismatch: got={reported}, want={expected_host}"


def test_normal_root_route_not_redirected():
    """Normal root route / should return 200, not redirect."""
    res = requests.get(
        f"{BASE_URL}/",
        headers={
            "accept": "text/html",
            "sec-fetch-dest": "document",
        },
        allow_redirects=False,
        timeout=20,
    )
    
    assert res.status_code == 200, f"Expected 200 for root route, got {res.status_code}"


def test_normal_verify_route_not_redirected():
    """Normal /verify route should return 200, not redirect."""
    res = requests.get(
        f"{BASE_URL}/verify",
        headers={
            "accept": "text/html",
            "sec-fetch-dest": "document",
        },
        allow_redirects=False,
        timeout=20,
    )
    
    assert res.status_code == 200, f"Expected 200 for /verify route, got {res.status_code}"


def test_api_health_endpoint_working():
    """Backend API health endpoint should return healthy status."""
    res = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert res.status_code == 200, f"Expected 200 from /api/health, got {res.status_code}"
    payload = res.json()
    assert payload.get("status") == "healthy", f"Expected healthy status, got {payload}"
