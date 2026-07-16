"""Feature 36 Integrity Alerts + Trends + Policy Recommendation - Comprehensive Backend Tests."""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


def _login_session_with_retry(email: str, password: str, max_attempts: int = 5) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        login = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        if login.status_code == 200:
            return session

        last_error = f"{login.status_code} {login.text}"
        if login.status_code not in {401, 429, 503} or attempt >= max_attempts:
            break

        wait_seconds = 1.25 * attempt
        try:
            payload = login.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, dict):
                retry_after = float(detail.get("retry_after_seconds") or detail.get("retryAfterSeconds") or 0)
                if retry_after > 0:
                    wait_seconds = max(wait_seconds, min(retry_after + 0.25, 8.0))
        except Exception:
            pass

        time.sleep(wait_seconds)

    raise AssertionError(f"Login failed for {email}: {last_error}")


_ADMIN_SESSION_CACHE: requests.Session | None = None
_BASIC_SESSION_CACHE: requests.Session | None = None
_FREE_SESSION_CACHE: requests.Session | None = None


def _reuse_or_login(cache: requests.Session | None, email: str, password: str) -> requests.Session:
    if cache is not None:
        try:
            me = cache.get(f"{BASE_URL}/api/auth/me", timeout=20)
            if me.status_code == 200:
                return cache
        except Exception:
            pass
    return _login_session_with_retry(email, password)


def _admin_session() -> requests.Session:
    """Create authenticated admin session."""
    global _ADMIN_SESSION_CACHE
    _ADMIN_SESSION_CACHE = _reuse_or_login(_ADMIN_SESSION_CACHE, ADMIN_EMAIL, ADMIN_PASSWORD)
    return _ADMIN_SESSION_CACHE


def _basic_session() -> requests.Session:
    """Create authenticated basic user session."""
    global _BASIC_SESSION_CACHE
    _BASIC_SESSION_CACHE = _reuse_or_login(_BASIC_SESSION_CACHE, BASIC_EMAIL, BASIC_PASSWORD)
    return _BASIC_SESSION_CACHE


def _free_session() -> requests.Session:
    """Create authenticated free user session."""
    global _FREE_SESSION_CACHE
    _FREE_SESSION_CACHE = _reuse_or_login(_FREE_SESSION_CACHE, FREE_EMAIL, FREE_PASSWORD)
    return _FREE_SESSION_CACHE


class TestIntegrityAlertsAPI:
    """Test integrity alerts endpoints."""

    def test_integrity_alerts_list_returns_expected_structure(self):
        """GET /api/referrals/admin/integrity-alerts returns alerts/data/total_count."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify required fields
        assert "alerts" in body, "Missing 'alerts' field"
        assert "data" in body, "Missing 'data' field"
        assert "total_count" in body, "Missing 'total_count' field"
        assert "page" in body, "Missing 'page' field"
        assert "page_size" in body, "Missing 'page_size' field"
        assert "status" in body, "Missing 'status' field"
        
        # Verify types
        assert isinstance(body["alerts"], list), "alerts should be a list"
        assert isinstance(body["total_count"], int), "total_count should be int"
        assert body["page"] == 1, "page should be 1"
        assert body["page_size"] == 10, "page_size should be 10"
        assert body["status"] == "open", "status should be 'open'"

    def test_integrity_alerts_pagination(self):
        """Test pagination parameters work correctly."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?page=2&page_size=5", timeout=30)
        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 2
        assert body["page_size"] == 5

    def test_integrity_alerts_status_filter(self):
        """Test status filter works for resolved alerts."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=resolved", timeout=30)
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "resolved"


class TestIntegrityEvaluateAPI:
    """Test integrity alert evaluation endpoint."""

    def test_evaluate_returns_success_and_metrics(self):
        """POST /api/referrals/admin/integrity-alerts/evaluate returns success, metrics, recommendation."""
        admin = _admin_session()
        res = admin.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate", json={}, timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify required fields
        assert body.get("success") is True, "success should be True"
        assert "metrics" in body, "Missing 'metrics' field"
        assert "recommendation" in body, "Missing 'recommendation' field"
        
        # Verify metrics structure
        metrics = body["metrics"]
        assert "open_high_alerts" in metrics, "Missing open_high_alerts in metrics"
        assert "open_total_alerts" in metrics, "Missing open_total_alerts in metrics"
        assert "duplicate_dedupe_keys_24h" in metrics, "Missing duplicate_dedupe_keys_24h in metrics"
        assert "payout_credits_24h" in metrics, "Missing payout_credits_24h in metrics"
        assert "expected_credits_24h" in metrics, "Missing expected_credits_24h in metrics"
        assert "payout_anomaly" in metrics, "Missing payout_anomaly in metrics"
        
        # Verify recommendation structure
        recommendation = body["recommendation"]
        assert "recommended_profile" in recommendation, "Missing recommended_profile"
        assert recommendation["recommended_profile"] in {"balanced", "strict"}, "Invalid profile"

    def test_evaluate_does_not_500(self):
        """Ensure evaluate endpoint doesn't return 500 error."""
        admin = _admin_session()
        res = admin.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate", json={}, timeout=30)
        assert res.status_code != 500, f"Got 500 error: {res.text}"
        assert res.status_code == 200


class TestIntegrityTrendsAPI:
    """Test integrity trends endpoint."""

    def test_trends_returns_points_and_windows(self):
        """GET /api/referrals/admin/integrity-trends?days=90 returns points and windows for 7/30/90."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=90", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify required fields
        assert "points" in body, "Missing 'points' field"
        assert "windows" in body, "Missing 'windows' field"
        assert "days" in body, "Missing 'days' field"
        assert "generated_at" in body, "Missing 'generated_at' field"
        
        # Verify windows structure
        windows = body["windows"]
        assert "7" in windows, "Missing 7-day window"
        assert "30" in windows, "Missing 30-day window"
        assert "90" in windows, "Missing 90-day window"
        
        # Verify each window has required fields
        for window_key in ["7", "30", "90"]:
            window = windows[window_key]
            assert "days" in window, f"Missing 'days' in {window_key}-day window"
            assert "avg_conversion_quality" in window, f"Missing 'avg_conversion_quality' in {window_key}-day window"
            assert "total_signups" in window, f"Missing 'total_signups' in {window_key}-day window"
            assert "total_subscribed" in window, f"Missing 'total_subscribed' in {window_key}-day window"
            assert "duplicate_prevention_breaches" in window, f"Missing 'duplicate_prevention_breaches' in {window_key}-day window"

    def test_trends_points_have_required_fields(self):
        """Verify each point in trends has conversion_quality and duplicate_prevention_breaches."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=7", timeout=30)
        assert res.status_code == 200
        body = res.json()
        
        points = body["points"]
        assert len(points) > 0, "Should have at least one point"
        
        for point in points:
            assert "date" in point, "Missing 'date' in point"
            assert "conversion_quality" in point, "Missing 'conversion_quality' in point"
            assert "duplicate_prevention_breaches" in point, "Missing 'duplicate_prevention_breaches' in point"
            assert "signups" in point, "Missing 'signups' in point"
            assert "subscribed" in point, "Missing 'subscribed' in point"


class TestFraudPolicyRecommendationAPI:
    """Test fraud policy recommendation endpoints."""

    def test_recommendation_returns_active_profile_and_recommendation(self):
        """GET /api/referrals/admin/fraud-policy/recommendation returns active_profile and recommendation."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify required fields
        assert "active_profile" in body, "Missing 'active_profile' field"
        assert "recommendation" in body, "Missing 'recommendation' field"
        assert "metrics" in body, "Missing 'metrics' field"
        assert "is_change_required" in body, "Missing 'is_change_required' field"
        assert "evaluated_at" in body, "Missing 'evaluated_at' field"
        
        # Verify recommendation structure
        recommendation = body["recommendation"]
        assert "recommended_profile" in recommendation, "Missing 'recommended_profile'"
        assert "confidence" in recommendation, "Missing 'confidence'"
        assert "reasons" in recommendation, "Missing 'reasons'"
        assert "recommended_rules" in recommendation, "Missing 'recommended_rules'"
        
        # Verify profile is valid
        assert body["active_profile"] in {"balanced", "strict"}, f"Invalid active_profile: {body['active_profile']}"
        assert recommendation["recommended_profile"] in {"balanced", "strict"}, "Invalid recommended_profile"

    def test_apply_recommendation_returns_success(self):
        """POST /api/referrals/admin/fraud-policy/apply-recommendation applies profile and returns success."""
        admin = _admin_session()
        res = admin.post(f"{BASE_URL}/api/referrals/admin/fraud-policy/apply-recommendation", json={}, timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify required fields
        assert body.get("success") is True, "success should be True"
        assert "applied_profile" in body, "Missing 'applied_profile' field"
        assert "rules" in body, "Missing 'rules' field"
        assert "updated_at" in body, "Missing 'updated_at' field"
        
        # Verify applied profile is valid
        assert body["applied_profile"] in {"balanced", "strict"}, f"Invalid applied_profile: {body['applied_profile']}"


class TestAdminFraudScanWithIntegrityPayload:
    """Test admin fraud scan endpoint includes integrity_alert payload."""

    def test_fraud_scan_includes_integrity_alert(self):
        """POST /api/referrals/admin/fraud-scan/run should include integrity_alert in response."""
        admin = _admin_session()
        res = admin.post(f"{BASE_URL}/api/referrals/admin/fraud-scan/run", json={}, timeout=60)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify integrity_alert is in response
        assert "integrity_alert" in body, "Missing 'integrity_alert' field in fraud scan response"
        
        integrity_alert = body["integrity_alert"]
        assert "success" in integrity_alert, "Missing 'success' in integrity_alert"
        assert "metrics" in integrity_alert, "Missing 'metrics' in integrity_alert"
        assert "recommendation" in integrity_alert, "Missing 'recommendation' in integrity_alert"


class TestRoleBasedAccess:
    """Test admin-only endpoints reject non-admin users."""

    def test_integrity_alerts_rejects_non_admin(self):
        """Non-admin users should be rejected from integrity alerts endpoint."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts", timeout=30)
        assert res.status_code in {401, 403}, f"Expected 401/403 for non-admin, got {res.status_code}"

    def test_integrity_trends_rejects_non_admin(self):
        """Non-admin users should be rejected from integrity trends endpoint."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=30", timeout=30)
        assert res.status_code in {401, 403}, f"Expected 401/403 for non-admin, got {res.status_code}"

    def test_fraud_policy_recommendation_rejects_non_admin(self):
        """Non-admin users should be rejected from fraud policy recommendation endpoint."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation", timeout=30)
        assert res.status_code in {401, 403}, f"Expected 401/403 for non-admin, got {res.status_code}"

    def test_apply_recommendation_rejects_non_admin(self):
        """Non-admin users should be rejected from apply recommendation endpoint."""
        basic = _basic_session()
        res = basic.post(f"{BASE_URL}/api/referrals/admin/fraud-policy/apply-recommendation", json={}, timeout=30)
        assert res.status_code in {401, 403}, f"Expected 401/403 for non-admin, got {res.status_code}"

    def test_integrity_evaluate_rejects_non_admin(self):
        """Non-admin users should be rejected from integrity evaluate endpoint."""
        basic = _basic_session()
        res = basic.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate", json={}, timeout=30)
        assert res.status_code in {401, 403}, f"Expected 401/403 for non-admin, got {res.status_code}"


class TestReferralsWorkspaceRegression:
    """Regression tests for referrals workspace endpoints."""

    def test_my_stats_endpoint_works(self):
        """GET /api/referrals/my-stats should work for authenticated users."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/my-stats", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        # Verify key fields
        assert "referral_code" in body, "Missing referral_code"
        assert "referral_link" in body, "Missing referral_link"
        assert "total_clicks" in body, "Missing total_clicks"
        assert "total_signups" in body, "Missing total_signups"
        assert "tier" in body, "Missing tier"

    def test_my_referrals_endpoint_works(self):
        """GET /api/referrals/my-referrals should work for authenticated users."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/my-referrals", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "referrals" in body, "Missing referrals"
        assert "total" in body, "Missing total"
        assert isinstance(body["referrals"], list), "referrals should be a list"

    def test_my_credits_endpoint_works(self):
        """GET /api/referrals/my-credits should work for authenticated users."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/my-credits", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "balance" in body, "Missing balance"
        assert "total_earned" in body, "Missing total_earned"
        assert "total_applied" in body, "Missing total_applied"
        assert "transactions" in body, "Missing transactions"

    def test_public_leaderboard_works(self):
        """GET /api/referrals/public-leaderboard should work."""
        basic = _basic_session()
        res = basic.get(f"{BASE_URL}/api/referrals/public-leaderboard", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "leaderboard" in body, "Missing leaderboard"
        assert "total_participants" in body, "Missing total_participants"
        assert "tiers" in body, "Missing tiers"


class TestAdminAnalyticsRegression:
    """Regression tests for admin analytics endpoints."""

    def test_admin_analytics_works(self):
        """GET /api/referrals/admin/analytics should work for admin."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "total_referrers" in body, "Missing total_referrers"
        assert "total_clicks" in body, "Missing total_clicks"
        assert "total_signups" in body, "Missing total_signups"
        assert "conversion_rate" in body, "Missing conversion_rate"
        assert "trend" in body, "Missing trend"
        assert "plan_distribution" in body, "Missing plan_distribution"
        assert "status_distribution" in body, "Missing status_distribution"
        assert "tier_distribution" in body, "Missing tier_distribution"

    def test_admin_top_referrers_works(self):
        """GET /api/referrals/admin/top-referrers should work for admin."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/top-referrers", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "referrers" in body, "Missing referrers"
        assert "total" in body, "Missing total"

    def test_admin_ops_health_works(self):
        """GET /api/referrals/admin/ops-health should work for admin."""
        admin = _admin_session()
        res = admin.get(f"{BASE_URL}/api/referrals/admin/ops-health", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        body = res.json()
        
        assert "flags" in body, "Missing flags"
        assert "funnel" in body, "Missing funnel"
        assert "idempotency" in body, "Missing idempotency"
        assert "fraud" in body, "Missing fraud"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
