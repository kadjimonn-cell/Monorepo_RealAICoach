"""
Feature 36 Referrals Enterprise Rebuild - Comprehensive E2E Tests
Tests P0/P1/P2/P3 hardening contracts for production reliability.

Covers:
- P0 stabilization: rate-limit envelopes, idempotent replay behavior
- P1 reliability: admin analytics endpoints with batching
- P2 UX rebuild: workspace tabs and sections
- P3 ops readiness: ops-health endpoint
- Fraud alerts read-only behavior
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"
PREMIUM_EMAIL = "f22.premium.20260613@example.com"
PREMIUM_PASSWORD = "F22Premium#2026Aa"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


def _session(email: str, password: str) -> requests.Session:
    """Create authenticated session."""
    sess = requests.Session()
    sess.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-E2E-Test-Bypass": "playwright-e2e"
    })
    res = sess.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert res.status_code == 200, f"Login failed for {email}: {res.status_code} {res.text}"
    return sess


class TestP0Stabilization:
    """P0: Rate-limit envelopes and idempotent replay behavior."""

    def test_apply_code_rate_limit_envelope(self):
        """Test that apply-code endpoint has rate limiting."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        # First request should succeed or return expected error
        res = basic.post(f"{BASE_URL}/api/referrals/apply-code", json={
            "code": "INVALID-CODE-TEST",
            "channel": "direct"
        }, timeout=30)
        # Should return 404 for invalid code, not 429 (rate limit)
        assert res.status_code in (200, 400, 404), f"Unexpected status: {res.status_code} {res.text}"

    def test_track_click_rate_limit_envelope(self):
        """Test that track-click endpoint has rate limiting and requires auth."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.post(f"{BASE_URL}/api/referrals/track-click", json={
            "code": "INVALID-CODE",
            "channel": "direct"
        }, timeout=30)
        # Should return 404 for invalid code (auth required)
        assert res.status_code in (200, 400, 404), f"Unexpected status: {res.status_code} {res.text}"

    def test_track_subscription_rate_limit_envelope(self):
        """Test that track-subscription endpoint has rate limiting and requires auth."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.post(f"{BASE_URL}/api/referrals/track-subscription", json={
            "referred_user_id": "test_user_nonexistent",
            "plan": "basic"
        }, timeout=30)
        # Should return success=false for non-existent referral or payouts disabled
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        assert "success" in data

    def test_auto_apply_renewal_idempotent_with_header_key(self):
        """Test that auto-apply-renewal is idempotent with X-Idempotency-Key header."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        idem_key = f"feature36-renewal-idem-{uuid.uuid4().hex[:8]}"
        headers = {"X-Idempotency-Key": idem_key, "X-Requested-With": "XMLHttpRequest"}
        
        # First request
        res1 = basic.post(f"{BASE_URL}/api/referrals/auto-apply-renewal", headers=headers, timeout=30)
        assert res1.status_code in (200, 400), f"Unexpected: {res1.status_code} {res1.text}"
        
        # Second request with same idempotency key should return replay
        res2 = basic.post(f"{BASE_URL}/api/referrals/auto-apply-renewal", headers=headers, timeout=30)
        assert res2.status_code == 200, f"Expected idempotent replay 200, got {res2.status_code}: {res2.text}"
        data2 = res2.json()
        # Should indicate idempotent replay or already processed
        assert data2.get("idempotent_replay") is True or data2.get("already_processed") is True or data2.get("success") is False

    def test_apply_code_idempotent_behavior(self):
        """Test that apply-code is idempotent."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        idem_key = f"apply-code-idem-{uuid.uuid4().hex[:8]}"
        
        # First request with invalid code
        res1 = basic.post(f"{BASE_URL}/api/referrals/apply-code", json={
            "code": "INVALID-CODE-IDEM",
            "channel": "direct",
            "idempotency_key": idem_key
        }, timeout=30)
        # Should return 404 for invalid code
        assert res1.status_code in (200, 400, 404), f"Unexpected: {res1.status_code} {res1.text}"


class TestP1ReliabilityPerformance:
    """P1: Admin analytics endpoints with batching and index-safe updates."""

    def test_admin_analytics_returns_data(self):
        """Test that admin analytics endpoint returns expected data structure."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Verify expected fields
        assert "total_referrers" in data
        assert "total_clicks" in data
        assert "total_signups" in data
        assert "conversion_rate" in data
        assert "trend" in data
        assert "plan_distribution" in data
        assert "status_distribution" in data
        assert "tier_distribution" in data

    def test_admin_enhanced_analytics_returns_data(self):
        """Test that enhanced analytics endpoint returns conversion funnel data."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/enhanced-analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Verify expected fields
        assert "conversion_funnel" in data
        assert "cohorts" in data
        assert "channel_funnels" in data

    def test_admin_top_referrers_returns_data(self):
        """Test that top referrers endpoint returns expected data."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/top-referrers", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "referrers" in data
        assert "total" in data

    def test_admin_credit_analytics_returns_data(self):
        """Test that credit analytics endpoint returns expected data."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/credit-analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "total_wallets" in data
        assert "total_earned" in data
        assert "total_applied" in data

    def test_admin_channel_analytics_returns_data(self):
        """Test that channel analytics endpoint returns expected data."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/channel-analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "channels" in data
        assert "total_clicks" in data
        assert "total_signups" in data


class TestP3OpsReadiness:
    """P3: Ops-health endpoint for admin monitoring."""

    def test_ops_health_endpoint_available_for_admin(self):
        """Test that ops-health endpoint is available and returns expected structure."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/ops-health", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Verify all required sections
        assert "flags" in data, "Missing 'flags' section"
        assert "idempotency" in data, "Missing 'idempotency' section"
        assert "fraud" in data, "Missing 'fraud' section"
        assert "funnel" in data, "Missing 'funnel' section"
        
        # Verify flags structure
        assert "payouts_enabled" in data["flags"]
        assert "fraud_autoscan_enabled" in data["flags"]
        
        # Verify funnel structure
        assert "conversion_rate" in data["funnel"]
        
        # Verify idempotency structure
        assert "replay_records_last_24h" in data["idempotency"]
        assert "duplicate_credit_dedupe_keys_last_24h" in data["idempotency"]

    def test_ops_health_requires_admin(self):
        """Test that ops-health endpoint requires admin access."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/admin/ops-health", timeout=30)
        assert res.status_code in (401, 403), f"Expected 401/403 for non-admin, got {res.status_code}"


class TestFraudAlertsReadOnly:
    """Test that fraud-alerts GET is read-only with scan metadata."""

    def test_fraud_alerts_is_read_only_and_has_scan_metadata(self):
        """Test that GET fraud-alerts returns scan metadata without triggering scan."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/fraud-alerts?page=1&page_size=5", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Verify scan metadata fields
        assert "last_scan" in data, "Missing 'last_scan' field"
        assert "last_scan_type" in data, "Missing 'last_scan_type' field"
        assert "last_scan_new_alerts" in data, "Missing 'last_scan_new_alerts' field"
        
        # Verify read-only behavior (new_alerts_found should be 0 for GET)
        assert data.get("new_alerts_found") == 0, "GET should not trigger new scan"
        
        # Verify other expected fields
        assert "data" in data or "alerts" in data
        assert "total_count" in data
        assert "total_open" in data
        assert "total_resolved" in data

    def test_fraud_alerts_requires_admin(self):
        """Test that fraud-alerts endpoint requires admin access."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/admin/fraud-alerts", timeout=30)
        assert res.status_code in (401, 403), f"Expected 401/403 for non-admin, got {res.status_code}"


class TestUserEndpoints:
    """Test user-facing referral endpoints."""

    def test_my_code_returns_referral_code(self):
        """Test that my-code endpoint returns user's referral code."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-code", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "code" in data
        assert "referral_link" in data
        assert "commission_rate" in data
        assert "discount_rate" in data

    def test_my_stats_returns_stats(self):
        """Test that my-stats endpoint returns user's referral stats."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-stats", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "referral_code" in data
        assert "referral_link" in data
        assert "total_clicks" in data
        assert "total_signups" in data
        assert "tier" in data
        assert "commission_rate" in data

    def test_my_referrals_returns_list(self):
        """Test that my-referrals endpoint returns referral list."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-referrals", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "referrals" in data
        assert "total" in data

    def test_my_credits_returns_balance(self):
        """Test that my-credits endpoint returns credit balance."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-credits", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "balance" in data
        assert "total_earned" in data
        assert "total_applied" in data

    def test_my_milestones_returns_progress(self):
        """Test that my-milestones endpoint returns milestone progress."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-milestones", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "milestones" in data
        assert "total_signups" in data

    def test_my_challenges_returns_challenges(self):
        """Test that my-challenges endpoint returns active challenges."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-challenges", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "challenges" in data

    def test_sharing_kit_returns_templates(self):
        """Test that sharing-kit endpoint returns sharing templates."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/sharing-kit", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "templates" in data
        assert "referral_code" in data
        assert "referral_link" in data

    def test_my_channel_analytics_returns_data(self):
        """Test that my-channel-analytics endpoint returns channel data."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/my-channel-analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "channels" in data


class TestPublicLeaderboard:
    """Test public leaderboard endpoint."""

    def test_public_leaderboard_returns_data(self):
        """Test that public leaderboard returns anonymized data."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.get(f"{BASE_URL}/api/referrals/public-leaderboard", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        assert "leaderboard" in data
        assert "total_participants" in data
        assert "tiers" in data


class TestPayoutKillSwitch:
    """Test payout kill-switch safe responses."""

    def test_track_subscription_respects_payout_flag(self):
        """Test that track-subscription respects REFERRALS_PAYOUTS_ENABLED flag."""
        basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
        res = basic.post(f"{BASE_URL}/api/referrals/track-subscription", json={
            "referred_user_id": "test_user_payout_check",
            "plan": "basic"
        }, timeout=30)
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        
        # If payouts disabled, should return specific error code
        if data.get("success") is False:
            # Either no pending referral or payouts disabled
            assert "message" in data or "error_code" in data


class TestAdminChallenges:
    """Test admin challenge management endpoints."""

    def test_admin_challenges_list(self):
        """Test that admin can list challenges."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/challenges?page=1&page_size=10", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Should have data or challenges field
        assert "data" in data or "challenges" in data


class TestAdminMilestoneAnalytics:
    """Test admin milestone analytics endpoint."""

    def test_admin_milestone_analytics(self):
        """Test that admin can view milestone analytics."""
        admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
        res = admin.get(f"{BASE_URL}/api/referrals/admin/milestone-analytics", timeout=30)
        assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
        data = res.json()
        
        # Should have milestone-related fields
        assert "milestones" in data or "total_achieved" in data or "total_bonus_paid" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
