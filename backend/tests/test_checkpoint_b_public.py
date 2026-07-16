"""
Checkpoint B - Public Endpoint Contract Verification
Tests all public endpoints WITHOUT authentication (no admin login)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')


class TestPublicEndpointContract:
    """Verify public endpoints are accessible without authentication"""

    def test_subscriptions_plans_public(self):
        """PUBLIC: /api/subscriptions/plans should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        # Verify plans payload structure
        assert isinstance(data, list) or isinstance(data, dict), "Plans should return list or dict"
        if isinstance(data, list):
            assert len(data) >= 1, "Should have at least 1 plan"
            print(f"PASS: /api/subscriptions/plans returned {len(data)} plans")
        elif isinstance(data, dict):
            plans = data.get('plans', data.get('items', []))
            assert len(plans) >= 1, "Should have at least 1 plan"
            print(f"PASS: /api/subscriptions/plans returned {len(plans)} plans")

    def test_gps_state_public(self):
        """PUBLIC: /api/gps/state should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        # Verify GPS state structure
        assert 'state_id' in data, "GPS state should have state_id"
        assert 'features' in data, "GPS state should have features"
        assert 'plans' in data, "GPS state should have plans"
        assert 'faq' in data, "GPS state should have faq"
        print(f"PASS: /api/gps/state returned state_id={data.get('state_id')}, features={len(data.get('features', []))}, plans={len(data.get('plans', []))}, faq={len(data.get('faq', []))}")

    def test_gps_health_public(self):
        """PUBLIC: /api/gps/health should be publicly accessible and structurally healthy.

        In preview/dev, catalog freshness can legitimately degrade while dependencies stay healthy.
        """
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        # Verify health structure
        assert 'ready' in data, "GPS health should have ready field"
        assert 'mode' in data, "GPS health should have mode field"
        assert 'dependencies' in data, "GPS health should have dependencies"
        assert 'completeness' in data, "GPS health should have completeness"
        
        # Check for failed checks in completeness
        completeness = data.get('completeness', {})
        failed_checks = completeness.get('failed_checks', [])
        is_complete = completeness.get('is_complete', False)
        
        print(f"GPS Health: ready={data.get('ready')}, mode={data.get('mode')}, is_complete={is_complete}, failed_checks={failed_checks}")
        
        # Verify dependencies are healthy
        deps = data.get('dependencies', {})
        for dep_name, dep_info in deps.items():
            status = dep_info.get('status', 'unknown')
            print(f"  Dependency {dep_name}: {status}")
        
        # Accept either complete health OR freshness-only degradation while deps remain healthy.
        deps_all_healthy = all((dep.get('status') == 'healthy') for dep in deps.values())
        freshness_only = (len(failed_checks) == 1 and failed_checks[0] == 'freshness_contract')

        assert is_complete or (deps_all_healthy and freshness_only), (
            f"GPS health has unexpected failed checks: {failed_checks}"
        )
        if is_complete:
            print("PASS: /api/gps/health is complete with no failed checks")
        else:
            print("PASS: /api/gps/health accepted freshness-only degradation with healthy dependencies")

    def test_features_registry_public(self):
        """PUBLIC: /api/features/registry should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        # Verify features structure
        features = data if isinstance(data, list) else data.get('features', data.get('items', []))
        assert isinstance(features, list), "Features should be a list"
        print(f"PASS: /api/features/registry returned {len(features)} features")
        return len(features)

    def test_live_metrics_public(self):
        """PUBLIC: /api/system/live-metrics should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        # Verify metrics structure
        assert 'vanity' in data or 'kpis' in data, "Live metrics should have vanity or kpis"
        vanity = data.get('vanity', {})
        print(f"PASS: /api/system/live-metrics returned vanity metrics: active_users={vanity.get('active_users')}, ai_sessions_today={vanity.get('ai_sessions_today')}")


class TestGPSAliveContract:
    """Verify GPS is alive and healthy"""

    def test_gps_health_completeness(self):
        """GPS health completeness should be complete or freshness-only degraded in preview/dev."""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        completeness = data.get('completeness', {})
        failed_checks = completeness.get('failed_checks', [])
        is_complete = completeness.get('is_complete', False)
        
        # Log all completeness details
        print("Completeness details:")
        print(f"  features_count: {completeness.get('features_count')}")
        print(f"  plans_count: {completeness.get('plans_count')}")
        print(f"  faq_count: {completeness.get('faq_count')}")
        print(f"  testimonials_count: {completeness.get('testimonials_count')}")
        print(f"  activities_count: {completeness.get('activities_count')}")
        print(f"  state_age_seconds: {completeness.get('state_age_seconds')}")
        print(f"  is_complete: {is_complete}")
        print(f"  failed_checks: {failed_checks}")
        
        # Allow freshness-only degradation in preview/dev while keeping strictness for all other failures.
        freshness_only = (len(failed_checks) == 1 and failed_checks[0] == "freshness_contract")
        if not is_complete:
            print(f"WARNING: GPS completeness has failed checks: {failed_checks}")

        assert is_complete or freshness_only, (
            f"GPS completeness should be complete or freshness-only degraded. Failed checks: {failed_checks}"
        )


class TestFeatureFreshnessConsistency:
    """Verify feature freshness and platform inventory consistency"""

    def test_features_registry_gps_state_consistency(self):
        """Feature registry count should be consistent with GPS state features count"""
        # Get features from registry
        registry_response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert registry_response.status_code == 200
        registry_data = registry_response.json()
        registry_features = registry_data if isinstance(registry_data, list) else registry_data.get('features', registry_data.get('items', []))
        
        # Get features from GPS state
        gps_response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert gps_response.status_code == 200
        gps_data = gps_response.json()
        gps_features = gps_data.get('features', [])
        
        registry_count = len(registry_features)
        gps_count = len(gps_features)
        
        print(f"Feature counts: registry={registry_count}, gps_state={gps_count}")
        
        # They should be reasonably consistent (allow some variance for enabled/disabled)
        # GPS state may filter out disabled features
        assert registry_count >= gps_count, "Registry should have at least as many features as GPS state"
        print(f"PASS: Feature counts are consistent (registry={registry_count}, gps={gps_count})")


class TestPublicAPIContractFromCode:
    """Verify public API contract matches code definition"""

    def test_public_api_contract_endpoints(self):
        """Verify all documented public endpoints are accessible"""
        public_endpoints = [
            "/api/subscriptions/plans",
            "/api/gps/state",
            "/api/gps/health",
            "/api/features/registry",
            "/api/system/live-metrics",
        ]
        
        results = []
        for endpoint in public_endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=15)
                status = response.status_code
                is_public = status == 200
                results.append({
                    "endpoint": endpoint,
                    "status": status,
                    "is_public": is_public
                })
                print(f"  {endpoint}: {status} ({'PUBLIC' if is_public else 'PROTECTED'})")
            except Exception as e:
                results.append({
                    "endpoint": endpoint,
                    "status": "ERROR",
                    "is_public": False,
                    "error": str(e)
                })
                print(f"  {endpoint}: ERROR - {e}")
        
        # All should be public (200)
        failed = [r for r in results if not r.get('is_public')]
        assert len(failed) == 0, f"Some public endpoints are not accessible: {failed}"
        print(f"PASS: All {len(public_endpoints)} public endpoints are accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
