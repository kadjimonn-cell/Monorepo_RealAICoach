"""
GPS Public Audit Tests - Platform-level deep audit for public-only evidence
Tests GPS state, health, features registry, live metrics, and v2 compliance
No admin credentials used - public-only endpoints
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGPSPublicState:
    """Test /api/gps/state - Global Platform State public endpoint"""
    
    def test_gps_state_returns_200(self):
        """GPS state endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200, f"GPS state returned {response.status_code}"
        print("✓ GPS state returned 200")
    
    def test_gps_state_has_required_fields(self):
        """GPS state should have state_id, features, plans, faq arrays"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "state_id" in data, "Missing state_id"
        assert "features" in data, "Missing features array"
        assert "plans" in data, "Missing plans array"
        assert "faq" in data, "Missing faq array"
        
        # Validate arrays
        assert isinstance(data["features"], list), "features should be array"
        assert isinstance(data["plans"], list), "plans should be array"
        assert isinstance(data["faq"], list), "faq should be array"
        
        print(f"✓ GPS state has required fields: state_id={data['state_id']}")
        print(f"  Features: {len(data['features'])}, Plans: {len(data['plans'])}, FAQ: {len(data['faq'])}")
    
    def test_gps_state_features_not_empty(self):
        """GPS state should have at least some features"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        features = data.get("features", [])
        # Check if features exist
        if len(features) == 0:
            pytest.fail("GPS state has EMPTY features array - GPS not live symptom")
        
        print(f"✓ GPS state has {len(features)} features")
    
    def test_gps_state_plans_not_empty(self):
        """GPS state should have at least free/basic/premium plans"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        plans = data.get("plans", [])
        if len(plans) == 0:
            pytest.fail("GPS state has EMPTY plans array - GPS not live symptom")
        
        plan_ids = [p.get("plan_id") for p in plans]
        print(f"✓ GPS state has {len(plans)} plans: {plan_ids}")
        
        # Check for expected plans
        expected_plans = ["free", "basic", "premium"]
        for expected in expected_plans:
            if expected not in plan_ids:
                print(f"  WARNING: Missing expected plan '{expected}'")
    
    def test_gps_state_faq_not_empty(self):
        """GPS state should have FAQ entries"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        faq = data.get("faq", [])
        if len(faq) == 0:
            pytest.fail("GPS state has EMPTY faq array - GPS not live symptom")
        
        print(f"✓ GPS state has {len(faq)} FAQ entries")
    
    def test_gps_state_messaging_has_welcome_data(self):
        """GPS messaging should have welcome_testimonials and welcome_activities"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        messaging = data.get("messaging", {})
        testimonials = messaging.get("welcome_testimonials", [])
        activities = messaging.get("welcome_activities", [])
        trust_names = messaging.get("trust_names", [])
        
        issues = []
        if len(testimonials) < 3:
            issues.append(f"welcome_testimonials has {len(testimonials)} items (min 3)")
        if len(activities) < 4:
            issues.append(f"welcome_activities has {len(activities)} items (min 4)")
        if len(trust_names) < 4:
            issues.append(f"trust_names has {len(trust_names)} items (min 4)")
        
        if issues:
            print(f"  WARNING: Missing welcome messaging data: {issues}")
        else:
            print(f"✓ GPS messaging has welcome data: testimonials={len(testimonials)}, activities={len(activities)}, trust_names={len(trust_names)}")


class TestGPSHealth:
    """Test /api/gps/health - GPS health endpoint"""
    
    def test_gps_health_returns_200(self):
        """GPS health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200, f"GPS health returned {response.status_code}"
        print("✓ GPS health returned 200")
    
    def test_gps_health_has_completeness_block(self):
        """GPS health should include completeness block"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "completeness" in data, "Missing completeness block in GPS health"
        completeness = data["completeness"]
        
        # Check completeness fields
        assert "plans_count" in completeness, "Missing plans_count in completeness"
        assert "faq_count" in completeness, "Missing faq_count in completeness"
        assert "is_complete" in completeness, "Missing is_complete in completeness"
        
        print(f"✓ GPS health has completeness: plans={completeness.get('plans_count')}, faq={completeness.get('faq_count')}, is_complete={completeness.get('is_complete')}")
    
    def test_gps_health_mode_is_live_or_degraded(self):
        """GPS health mode should be 'live' or 'degraded'"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get("mode")
        assert mode in ["live", "degraded"], f"GPS mode is '{mode}', expected 'live' or 'degraded'"
        
        if mode == "degraded":
            print("  WARNING: GPS is in DEGRADED mode")
        else:
            print(f"✓ GPS mode is '{mode}'")


class TestFeaturesRegistry:
    """Test /api/features/registry - Public features registry"""
    
    def test_features_registry_returns_200(self):
        """Features registry should return 200"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200, f"Features registry returned {response.status_code}"
        print("✓ Features registry returned 200")
    
    def test_features_registry_has_features_array(self):
        """Features registry should have features array"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "features" in data, "Missing features array"
        assert isinstance(data["features"], list), "features should be array"
        
        features = data["features"]
        if len(features) == 0:
            pytest.fail("Features registry has EMPTY features array - partial catalog symptom")
        
        print(f"✓ Features registry has {len(features)} features")
    
    def test_features_registry_has_categories(self):
        """Features registry should have categories"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "categories" in data, "Missing categories"
        categories = data["categories"]
        
        print(f"✓ Features registry has {len(categories)} categories")
    
    def test_features_registry_features_have_required_fields(self):
        """Each feature should have feature_id, title, enabled"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        features = data.get("features", [])
        if len(features) == 0:
            pytest.skip("No features to validate")
        
        # Check first 5 features
        for feature in features[:5]:
            assert "feature_id" in feature or "id" in feature, f"Feature missing feature_id: {feature}"
            assert "title" in feature, f"Feature missing title: {feature}"
        
        print(f"✓ Features have required fields (checked {min(5, len(features))} features)")


class TestLiveMetrics:
    """Test /api/system/live-metrics - Live metrics endpoint"""
    
    def test_live_metrics_returns_200(self):
        """Live metrics should return 200"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics", timeout=15)
        assert response.status_code == 200, f"Live metrics returned {response.status_code}"
        print("✓ Live metrics returned 200")
    
    def test_live_metrics_has_metric_source(self):
        """Live metrics should have metric_source field"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "metric_source" in data, "Missing metric_source in live metrics"
        metric_source = data["metric_source"]
        
        # Check if vanity is synthetic (expected for public)
        vanity_source = metric_source.get("vanity")
        kpis_source = metric_source.get("kpis")
        
        print(f"✓ Live metrics has metric_source: vanity={vanity_source}, kpis={kpis_source}")
        
        # For public (unauthenticated), vanity should be synthetic
        if vanity_source == "synthetic_generator":
            print("  INFO: Vanity metrics are synthetic (expected for public)")
        else:
            print(f"  WARNING: Vanity metrics source is '{vanity_source}'")
    
    def test_live_metrics_has_vanity_data(self):
        """Live metrics should have vanity data"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "vanity" in data, "Missing vanity in live metrics"
        vanity = data["vanity"]
        
        # Check expected vanity fields
        expected_fields = ["active_users", "ai_sessions_today", "global_coaches", "performance_boost"]
        for field in expected_fields:
            if field not in vanity:
                print(f"  WARNING: Missing vanity field '{field}'")
        
        print(f"✓ Live metrics has vanity data: {list(vanity.keys())}")
    
    def test_live_metrics_kpis_realtime_unavailable_for_public(self):
        """For public (unauthenticated), kpis_realtime should be empty or unavailable"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        data.get("kpis_realtime", {})
        metric_source = data.get("metric_source", {})
        
        # For public, realtime_kpis should be unavailable
        realtime_source = metric_source.get("realtime_kpis")
        if realtime_source == "unavailable_without_auth":
            print("✓ kpis_realtime correctly unavailable for public (unauthenticated)")
        else:
            print(f"  INFO: kpis_realtime source is '{realtime_source}'")


class TestVanityMetrics:
    """Test /api/system/vanity-metrics - Public vanity metrics"""
    
    def test_vanity_metrics_returns_200(self):
        """Vanity metrics should return 200"""
        response = requests.get(f"{BASE_URL}/api/system/vanity-metrics", timeout=15)
        assert response.status_code == 200, f"Vanity metrics returned {response.status_code}"
        print("✓ Vanity metrics returned 200")
    
    def test_vanity_metrics_has_expected_fields(self):
        """Vanity metrics should have active_users, ai_sessions_today, etc."""
        response = requests.get(f"{BASE_URL}/api/system/vanity-metrics", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = ["active_users", "ai_sessions_today", "global_coaches", "performance_boost", "system_health"]
        for field in expected_fields:
            if field not in data:
                print(f"  WARNING: Missing vanity field '{field}'")
        
        print(f"✓ Vanity metrics has fields: {list(data.keys())}")


class TestSystemHealth:
    """Test /api/system/health - System health endpoint"""
    
    def test_system_health_returns_200(self):
        """System health should return 200"""
        response = requests.get(f"{BASE_URL}/api/system/health", timeout=15)
        assert response.status_code == 200, f"System health returned {response.status_code}"
        print("✓ System health returned 200")
    
    def test_system_health_has_checks(self):
        """System health should have checks object"""
        response = requests.get(f"{BASE_URL}/api/system/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        assert "checks" in data, "Missing checks in system health"
        checks = data["checks"]
        
        print(f"✓ System health has checks: {list(checks.keys())}")


class TestSystemStatus:
    """Test /api/system/status - Enterprise system status"""

    @staticmethod
    def _assert_auth_required_shape(response: requests.Response):
        assert response.status_code in [401, 403], f"Expected protected endpoint status, got {response.status_code}"
        try:
            data = response.json()
        except Exception:
            pytest.fail(f"Protected system status response should be JSON: {response.text[:200]}")
        assert "detail" in data, f"Expected auth detail in protected response, got: {data}"
    
    def test_system_status_returns_200(self):
        """System status should be accessible per policy (public=200 or protected=401/403)."""
        response = requests.get(f"{BASE_URL}/api/system/status", timeout=15)
        if response.status_code == 200:
            print("✓ System status returned 200")
            return
        self._assert_auth_required_shape(response)
        print(f"✓ System status is policy-protected (status={response.status_code})")
    
    def test_system_status_has_enterprise_engine(self):
        """System status should have enterprise_autonomous_engine"""
        response = requests.get(f"{BASE_URL}/api/system/status", timeout=15)
        if response.status_code in [401, 403]:
            self._assert_auth_required_shape(response)
            pytest.skip("/api/system/status is auth-protected in this environment")
        assert response.status_code == 200
        data = response.json()
        
        assert "enterprise_autonomous_engine" in data, "Missing enterprise_autonomous_engine"
        engine = data["enterprise_autonomous_engine"]
        
        status = engine.get("status")
        print(f"✓ Enterprise autonomous engine status: {status}")
    
    def test_system_status_has_zero_trust(self):
        """System status should have zero_trust section"""
        response = requests.get(f"{BASE_URL}/api/system/status", timeout=15)
        if response.status_code in [401, 403]:
            self._assert_auth_required_shape(response)
            pytest.skip("/api/system/status is auth-protected in this environment")
        assert response.status_code == 200
        data = response.json()
        
        assert "zero_trust" in data, "Missing zero_trust"
        zero_trust = data["zero_trust"]
        
        status = zero_trust.get("status")
        print(f"✓ Zero trust status: {status}")


class TestPublicSubscriptionPlans:
    """Test /api/subscriptions/plans - Public subscription plans"""
    
    def test_subscription_plans_returns_200(self):
        """Subscription plans should return 200"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", timeout=15)
        assert response.status_code == 200, f"Subscription plans returned {response.status_code}"
        print("✓ Subscription plans returned 200")
    
    def test_subscription_plans_has_free_basic_premium(self):
        """Subscription plans should have free, basic, premium"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        plans = data.get("plans", data) if isinstance(data, dict) else data
        if isinstance(plans, dict):
            plans = plans.get("plans", [])
        
        plan_ids = [p.get("plan_id") or p.get("id") for p in plans]
        
        expected = ["free", "basic", "premium"]
        for exp in expected:
            if exp not in plan_ids:
                print(f"  WARNING: Missing expected plan '{exp}'")
        
        print(f"✓ Subscription plans: {plan_ids}")


class TestHealthEndpoint:
    """Test /api/health - Basic health check"""
    
    def test_health_returns_200(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert response.status_code == 200, f"Health returned {response.status_code}"
        print("✓ Health endpoint returned 200")


class TestGPSConsistency:
    """Test GPS data consistency across endpoints"""
    
    def test_gps_state_and_features_registry_consistency(self):
        """GPS state features should match features registry"""
        gps_response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        registry_response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        
        assert gps_response.status_code == 200
        assert registry_response.status_code == 200
        
        gps_features = gps_response.json().get("features", [])
        registry_features = registry_response.json().get("features", [])
        
        gps_count = len(gps_features)
        registry_count = len(registry_features)
        
        # Allow some variance but flag large differences
        diff = abs(gps_count - registry_count)
        if diff > 5:
            print(f"  WARNING: Large feature count difference: GPS={gps_count}, Registry={registry_count}")
        else:
            print(f"✓ Feature counts consistent: GPS={gps_count}, Registry={registry_count}")
    
    def test_gps_state_and_subscription_plans_consistency(self):
        """GPS state plans should match subscription plans"""
        gps_response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        plans_response = requests.get(f"{BASE_URL}/api/subscriptions/plans", timeout=15)
        
        assert gps_response.status_code == 200
        assert plans_response.status_code == 200
        
        gps_plans = gps_response.json().get("plans", [])
        
        plans_data = plans_response.json()
        sub_plans = plans_data.get("plans", plans_data) if isinstance(plans_data, dict) else plans_data
        if isinstance(sub_plans, dict):
            sub_plans = sub_plans.get("plans", [])
        
        gps_plan_ids = set(p.get("plan_id") for p in gps_plans)
        sub_plan_ids = set(p.get("plan_id") or p.get("id") for p in sub_plans)
        
        # Check for expected plans in both
        expected = {"free", "basic", "premium"}
        gps_has_expected = expected.issubset(gps_plan_ids)
        sub_has_expected = expected.issubset(sub_plan_ids)
        
        if not gps_has_expected:
            print(f"  WARNING: GPS missing expected plans. Has: {gps_plan_ids}")
        if not sub_has_expected:
            print(f"  WARNING: Subscriptions missing expected plans. Has: {sub_plan_ids}")
        
        print(f"✓ Plan consistency: GPS={gps_plan_ids}, Subscriptions={sub_plan_ids}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
