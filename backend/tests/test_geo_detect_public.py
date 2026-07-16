"""IP-based geo detection public endpoint tests (iteration 890).

Validates:
- /api/geo/detect is anonymous-public and returns 200 for well-known test IPs.
- COUNTRIES map covers all 23 currencies exposed by /api/payments/currencies.
- Other /api/geo/* routes remain auth-gated.
- Regression: canonical public endpoints (health/currencies/plans) still work,
  and a random /api/users route is still 401 anonymously.
"""
from __future__ import annotations

import os
import sys

import pytest
import requests

if "/app/backend" not in sys.path:
    sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def base_url() -> str:
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not set")
    return BASE_URL


# ---- /api/geo/detect anonymous tests ----

@pytest.mark.parametrize(
    "ip,expected_country,expected_currency",
    [
        ("81.2.69.142", "GB", "GBP"),
        ("168.126.63.1", "KR", "KRW"),
        ("154.66.135.1", "BJ", "XOF"),
    ],
)
def test_detect_public_anonymous_with_xff(base_url, ip, expected_country, expected_currency):
    """Anonymous caller passing X-Forwarded-For -> correct country/currency."""
    resp = requests.get(
        f"{base_url}/api/geo/detect",
        headers={"X-Forwarded-For": ip},
        timeout=20,
    )
    assert resp.status_code == 200, f"Status={resp.status_code} body={resp.text[:200]}"
    body = resp.json()
    assert body.get("detected_country") == expected_country, body
    assert body.get("default_currency") == expected_currency, body
    assert "country_name" in body
    assert "region" in body


def test_detect_public_anonymous_private_ip_falls_back_to_us(base_url):
    """Private IP forwarded -> US/USD fallback but still 200."""
    resp = requests.get(
        f"{base_url}/api/geo/detect",
        headers={"X-Forwarded-For": "10.0.0.5"},
        timeout=20,
    )
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert body.get("detected_country") == "US"
    assert body.get("default_currency") == "USD"
    assert body.get("is_us") is True


def test_detect_public_no_auth_no_cookies(base_url):
    """Ensure /geo/detect responds 200 for anonymous session (no cookies)."""
    session = requests.Session()
    resp = session.get(f"{base_url}/api/geo/detect", timeout=20)
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert "detected_country" in body
    assert "default_currency" in body


# ---- Regression: other /api/geo/* still auth-gated ----

def test_geo_countries_requires_auth(base_url):
    resp = requests.get(f"{base_url}/api/geo/countries", timeout=20)
    assert resp.status_code == 401, f"Expected 401 got {resp.status_code}: {resp.text[:200]}"


def test_geo_set_country_requires_auth(base_url):
    resp = requests.post(
        f"{base_url}/api/geo/set-country",
        json={"country_code": "FR"},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=20,
    )
    assert resp.status_code == 401, f"Expected 401 got {resp.status_code}: {resp.text[:200]}"


def test_geo_my_country_requires_auth(base_url):
    resp = requests.get(f"{base_url}/api/geo/my-country", timeout=20)
    assert resp.status_code == 401, f"Expected 401 got {resp.status_code}: {resp.text[:200]}"


# ---- Regression: canonical public contract still intact ----

def test_public_health_ok(base_url):
    resp = requests.get(f"{base_url}/api/health", timeout=20)
    assert resp.status_code == 200, resp.text[:200]


def test_public_payments_currencies_ok(base_url):
    resp = requests.get(f"{base_url}/api/payments/currencies", timeout=20)
    assert resp.status_code == 200, resp.text[:200]


def test_public_subscription_plans_ok(base_url):
    resp = requests.get(f"{base_url}/api/subscriptions/plans", timeout=20)
    assert resp.status_code == 200, resp.text[:200]


def test_random_api_users_still_authgated(base_url):
    resp = requests.get(f"{base_url}/api/users", timeout=20)
    assert resp.status_code == 401, f"Expected 401 got {resp.status_code}: {resp.text[:200]}"


# ---- Currency coverage: every /api/payments/currencies code is reachable via COUNTRIES ----

def test_all_supported_currencies_reachable_from_countries(base_url):
    """Every currency in /api/payments/currencies must map from at least one COUNTRIES entry."""
    from routes.geo_detection import COUNTRIES

    resp = requests.get(f"{base_url}/api/payments/currencies", timeout=20)
    assert resp.status_code == 200, resp.text[:200]
    payload = resp.json()
    # Possible response shape variants
    if isinstance(payload, dict):
        items = payload.get("currencies") or payload.get("data") or payload.get("items") or []
    else:
        items = payload
    codes = set()
    for item in items:
        if isinstance(item, str):
            codes.add(item.upper())
        elif isinstance(item, dict):
            code = item.get("code") or item.get("currency") or item.get("iso") or ""
            if code:
                codes.add(str(code).upper())
    assert codes, f"Could not parse currency codes from payload: {payload!r}"

    reachable = {c["currency"] for c in COUNTRIES.values()}
    reachable.add("USD")  # default fallback is always US/USD
    missing = codes - reachable
    assert not missing, (
        f"Currencies not reachable via COUNTRIES map: {sorted(missing)}."
        f" Reachable set: {sorted(reachable)}."
    )


def test_countries_map_has_new_entries():
    """New entries from this feature: KR/AE/SA/TR/RU/BJ/TG/CI/NE."""
    from routes.geo_detection import COUNTRIES
    for code in ["KR", "AE", "SA", "TR", "RU", "BJ", "TG", "CI", "NE"]:
        assert code in COUNTRIES, f"Missing new country in COUNTRIES: {code}"
    assert COUNTRIES["KR"]["currency"] == "KRW"
    assert COUNTRIES["AE"]["currency"] == "AED"
    assert COUNTRIES["SA"]["currency"] == "SAR"
    assert COUNTRIES["TR"]["currency"] == "TRY"
    assert COUNTRIES["RU"]["currency"] == "RUB"
    for c in ("BJ", "TG", "CI", "NE"):
        assert COUNTRIES[c]["currency"] == "XOF"


def test_detect_in_public_api_exact():
    """/api/geo/detect must be present in canonical PUBLIC_API_EXACT set."""
    from utils.public_api_contract import PUBLIC_API_EXACT
    assert "/api/geo/detect" in PUBLIC_API_EXACT
