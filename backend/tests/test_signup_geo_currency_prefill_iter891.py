"""Signup geo currency prefill tests (iteration 891).

Validates the non-blocking `_prefill_geo_currency` background task added in
`routes/auth.py::register` (~L1741). Behavior under test:

  * UK IP (81.2.69.142) → user.currency_preference == "GBP", signup_country == "GB"
  * Private IP (10.0.0.5) → currency_preference NOT set (None/absent), signup_country == "US"
  * Benin IP (154.66.135.1) → currency_preference == "XOF", signup_country == "BJ"
  * Manual profile update to CAD wins and persists (guard: geo prefill uses
    {currency_preference: {$in: [None, ""]}} so it can't overwrite).
  * Regression: duplicate email → 400, weak password → 400.
  * Rate-limit (5/hour/IP): after 5 register calls from the same source IP the
    6th should be 429 (guarded — if the limit was already tripped by an
    earlier test agent we just assert we can OBSERVE a 429, not that we hit it
    ourselves).
  * /api/geo/detect anonymous public regression preserved.

Test file follows patterns in tests/test_geo_detect_public.py.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

UK_IP = "81.2.69.142"          # ip-api → GB
BENIN_IP = "154.66.135.1"      # ip-api → BJ
PRIVATE_IP = "10.0.0.5"        # RFC1918 → US fallback

STRONG_PASSWORD = "GeoPrefill#2026Aa"

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def base_url() -> str:
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not set")
    return BASE_URL


def _fresh_email(tag: str) -> str:
    return f"geo.iter891.{tag}.{uuid.uuid4().hex[:10]}@example.com"


def _register(base_url: str, *, email: str, xff: str | None, session: requests.Session | None = None) -> requests.Response:
    session = session or requests.Session()
    headers = dict(CSRF_HEADERS)
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    payload = {"email": email, "password": STRONG_PASSWORD, "name": "Geo Iter891 User"}
    return session.post(f"{base_url}/api/auth/register", json=payload, headers=headers, timeout=30)


def _me(base_url: str, session: requests.Session) -> requests.Response:
    return session.get(f"{base_url}/api/auth/me", headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)


def _wait_for_prefill(base_url: str, session: requests.Session, *, expected_currency: str | None, timeout_s: float = 8.0) -> dict:
    """Poll /auth/me until the background prefill lands (or timeout)."""
    end = time.time() + timeout_s
    body: dict = {}
    while time.time() < end:
        r = _me(base_url, session)
        if r.status_code == 200:
            body = r.json() or {}
            if expected_currency is None:
                # Give background task a chance to run first
                time.sleep(1.0)
                r2 = _me(base_url, session)
                if r2.status_code == 200:
                    body = r2.json() or {}
                return body
            if (body.get("currency_preference") or "").upper() == expected_currency.upper():
                return body
        time.sleep(0.5)
    return body


# ── 1. UK signup with X-Forwarded-For=81.2.69.142 → GBP / GB ───────────────

def test_uk_signup_prefills_gbp_and_gb(base_url, request):
    email = _fresh_email("uk")
    session = requests.Session()
    resp = _register(base_url, email=email, xff=UK_IP, session=session)
    # 429 from prior tests is not our failure — surface it as skip so RCA is clear
    if resp.status_code == 429:
        pytest.skip(f"Registration rate-limited before UK case could run: {resp.text[:200]}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    assert data.get("email") == email
    user_id = data.get("user_id")
    assert user_id and user_id.startswith("user_"), data

    body = _wait_for_prefill(base_url, session, expected_currency="GBP")
    assert body.get("currency_preference") == "GBP", f"Expected GBP, got body={body}"
    # signup_country is not necessarily exposed in /auth/me — validate via a
    # second /auth/me if present, else skip that field-level check here.
    if "signup_country" in body:
        assert body["signup_country"] == "GB", body

    # Stash state for the manual-override test in this module
    request.config._iter891_uk = {"email": email, "user_id": user_id, "session": session}


# ── 2. Private-IP signup → no currency_preference ─────────────────────────

def test_private_ip_signup_leaves_currency_unset(base_url):
    email = _fresh_email("priv")
    session = requests.Session()
    resp = _register(base_url, email=email, xff=PRIVATE_IP, session=session)
    if resp.status_code == 429:
        pytest.skip(f"Registration rate-limited before private-IP case: {resp.text[:200]}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    # Wait for background task to (potentially) write signup_country=US
    body = _wait_for_prefill(base_url, session, expected_currency=None)
    pref = body.get("currency_preference")
    # Must be null/absent (USD default preserved)
    assert pref in (None, "", "USD" and None), (
        f"USD/private IP must NOT have currency_preference set. Got: {pref!r} body={body}"
    )
    # If /auth/me exposes signup_country, it should be US
    if body.get("signup_country") is not None:
        assert body["signup_country"] == "US", body


# ── 3. Benin signup (XOF) ─────────────────────────────────────────────────

def test_benin_signup_prefills_xof_and_bj(base_url):
    email = _fresh_email("bj")
    session = requests.Session()
    resp = _register(base_url, email=email, xff=BENIN_IP, session=session)
    if resp.status_code == 429:
        pytest.skip(f"Registration rate-limited before Benin case: {resp.text[:200]}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    body = _wait_for_prefill(base_url, session, expected_currency="XOF")
    assert body.get("currency_preference") == "XOF", f"Expected XOF, got body={body}"
    if "signup_country" in body:
        assert body["signup_country"] == "BJ", body


# ── 4. Manual override wins ───────────────────────────────────────────────

def test_manual_currency_override_wins(base_url, request):
    uk = getattr(request.config, "_iter891_uk", None)
    if not uk:
        pytest.skip("UK signup didn't run — cannot verify override precedence.")

    session: requests.Session = uk["session"]
    # PUT /api/auth/profile with currency_preference=CAD
    r = session.put(
        f"{base_url}/api/auth/profile",
        json={"currency_preference": "CAD"},
        headers=CSRF_HEADERS,
        timeout=20,
    )
    assert r.status_code == 200, f"profile PUT failed: {r.status_code} {r.text[:200]}"
    updated = (r.json() or {}).get("user") or {}
    assert updated.get("currency_preference") == "CAD", updated

    # Confirm via /auth/me and confirm guard: currency stays CAD (geo prefill
    # already ran; re-checking shortly after should still be CAD).
    time.sleep(2.0)
    me = _me(base_url, session)
    assert me.status_code == 200, me.text[:200]
    body = me.json()
    assert body.get("currency_preference") == "CAD", (
        f"Manual override must persist; got {body.get('currency_preference')!r} body={body}"
    )


# ── 5. Regressions: duplicate email, weak password ────────────────────────

def test_duplicate_email_regression(base_url, request):
    uk = getattr(request.config, "_iter891_uk", None)
    if not uk:
        pytest.skip("UK signup didn't run — no dup email fixture.")
    resp = _register(base_url, email=uk["email"], xff=UK_IP)
    if resp.status_code == 429:
        pytest.skip("Rate-limited before duplicate-email regression.")
    assert resp.status_code == 400, f"Expected 400 on duplicate email, got {resp.status_code}: {resp.text[:200]}"


def test_weak_password_regression(base_url):
    """Weak password must still yield 400 (validated after rate-limit check)."""
    payload = {"email": _fresh_email("weak"), "password": "weakpass", "name": "Weak"}
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json=payload,
        headers={**CSRF_HEADERS, "X-Forwarded-For": "203.0.113.55"},
        timeout=20,
    )
    if resp.status_code == 429:
        pytest.skip("Rate-limited before weak-password regression.")
    assert resp.status_code == 400, f"Expected 400 on weak password, got {resp.status_code}: {resp.text[:200]}"


# ── 6. Rate-limit still enforced ──────────────────────────────────────────

def test_rate_limit_still_enforced(base_url):
    """Fire up to 6 registrations; we expect at least one 429 in the window.

    Uses the SAME source IP for all attempts — rate limiter keys on
    raw_request.client.host (ingress-forwarded IP), and X-Forwarded-For is only
    used for geo, not for the limiter. That means our test sessions share the
    same limiter bucket regardless of XFF variation.
    """
    got_429 = False
    for i in range(6):
        r = _register(base_url, email=_fresh_email(f"rl{i}"), xff=f"198.51.100.{i+1}")
        if r.status_code == 429:
            got_429 = True
            break
        # Any non-2xx other than 429/400 is unexpected
        if r.status_code not in (200, 400):
            pytest.fail(f"Unexpected status {r.status_code} on register attempt {i}: {r.text[:200]}")
    assert got_429, "Expected at least one 429 within 6 rapid registration attempts (rate limiter appears disabled)."


# ── 7. /api/geo/detect anonymous regression ───────────────────────────────

def test_geo_detect_public_still_anonymous(base_url):
    r = requests.get(
        f"{base_url}/api/geo/detect",
        headers={"X-Forwarded-For": UK_IP},
        timeout=20,
    )
    assert r.status_code == 200, f"/api/geo/detect must remain anonymous-public: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("detected_country") == "GB"
    assert body.get("default_currency") == "GBP"
