"""
Growth Intelligence Module API Tests
Tests for the /api/system/live-metrics endpoint's growth_intelligence payload
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGrowthIntelligencePayload:
    """Tests for the growth_intelligence payload structure and data contract"""
    
    def test_live_metrics_endpoint_exists(self):
        """Verify /api/system/live-metrics endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: live-metrics endpoint exists and returns 200")
    
    def test_growth_intelligence_present_in_response(self):
        """Verify growth_intelligence key is present in response"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        assert response.status_code == 200
        data = response.json()
        assert "growth_intelligence" in data, "growth_intelligence key missing from response"
        print("PASS: growth_intelligence key present in response")
    
    def test_headline_metric_structure(self):
        """Verify headline_metric has correct structure"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "headline_metric" in gi, "headline_metric missing"
        hm = gi["headline_metric"]
        
        assert "label" in hm, "headline_metric.label missing"
        assert "value" in hm, "headline_metric.value missing"
        assert "unit" in hm, "headline_metric.unit missing"
        assert "delta_vs_baseline" in hm, "headline_metric.delta_vs_baseline missing"
        
        assert isinstance(hm["value"], (int, float)), "headline_metric.value should be numeric"
        assert isinstance(hm["delta_vs_baseline"], (int, float)), "delta_vs_baseline should be numeric"
        print(f"PASS: headline_metric structure valid - value={hm['value']}, delta={hm['delta_vs_baseline']}")
    
    def test_proof_points_structure(self):
        """Verify proof_points array has correct structure"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "proof_points" in gi, "proof_points missing"
        pp = gi["proof_points"]
        
        assert isinstance(pp, list), "proof_points should be a list"
        assert len(pp) == 4, f"Expected 4 proof_points, got {len(pp)}"
        
        for i, point in enumerate(pp):
            assert "label" in point, f"proof_points[{i}].label missing"
            assert "value" in point, f"proof_points[{i}].value missing"
            assert "tone" in point, f"proof_points[{i}].tone missing"
            assert isinstance(point["value"], (int, float)), f"proof_points[{i}].value should be numeric"
        
        print(f"PASS: proof_points structure valid - {len(pp)} points with correct fields")
    
    def test_ranges_structure(self):
        """Verify ranges object has 30d, 90d, 12m keys"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "ranges" in gi, "ranges missing"
        ranges = gi["ranges"]
        
        expected_keys = ["30d", "90d", "12m"]
        for key in expected_keys:
            assert key in ranges, f"ranges.{key} missing"
        
        print(f"PASS: ranges has all expected keys: {list(ranges.keys())}")
    
    def test_range_points_structure(self):
        """Verify each range has points array with correct structure"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        ranges = gi.get("ranges", {})
        
        for range_key in ["30d", "90d", "12m"]:
            range_data = ranges.get(range_key, {})
            assert "points" in range_data, f"ranges.{range_key}.points missing"
            assert "label" in range_data, f"ranges.{range_key}.label missing"
            assert "comparison_label" in range_data, f"ranges.{range_key}.comparison_label missing"
            assert "strongest_period_label" in range_data, f"ranges.{range_key}.strongest_period_label missing"
            assert "weakest_period_label" in range_data, f"ranges.{range_key}.weakest_period_label missing"
            assert "forecast_teaser" in range_data, f"ranges.{range_key}.forecast_teaser missing"
            
            points = range_data["points"]
            assert isinstance(points, list), f"ranges.{range_key}.points should be a list"
            assert len(points) > 0, f"ranges.{range_key}.points should not be empty"
            
            # Check first point structure
            point = points[0]
            required_fields = ["label", "period_start", "growth_score", "benchmark_score", 
                             "active_users", "ai_sessions", "completion_rate", "conversion_velocity"]
            for field in required_fields:
                assert field in point, f"ranges.{range_key}.points[0].{field} missing"
        
        print("PASS: All range points have correct structure")
    
    def test_default_range_value(self):
        """Verify default_range is set to 90d"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "default_range" in gi, "default_range missing"
        assert gi["default_range"] == "90d", f"Expected default_range='90d', got '{gi['default_range']}'"
        print("PASS: default_range is '90d'")
    
    def test_confidence_structure(self):
        """Verify confidence object has score and label"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "confidence" in gi, "confidence missing"
        conf = gi["confidence"]
        
        assert "score" in conf, "confidence.score missing"
        assert "label" in conf, "confidence.label missing"
        assert isinstance(conf["score"], (int, float)), "confidence.score should be numeric"
        assert 0 <= conf["score"] <= 100, f"confidence.score should be 0-100, got {conf['score']}"
        
        print(f"PASS: confidence structure valid - score={conf['score']}")
    
    def test_narrative_and_teaser_present(self):
        """Verify narrative_summary and premium_teaser are present"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        
        assert "narrative_summary" in gi, "narrative_summary missing"
        assert "premium_teaser" in gi, "premium_teaser missing"
        assert len(gi["narrative_summary"]) > 0, "narrative_summary should not be empty"
        assert len(gi["premium_teaser"]) > 0, "premium_teaser should not be empty"
        
        print("PASS: narrative_summary and premium_teaser present and non-empty")
    
    def test_milestone_in_points(self):
        """Verify some points have milestone data"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        ranges = gi.get("ranges", {})
        
        milestone_count = 0
        for range_key, range_data in ranges.items():
            for point in range_data.get("points", []):
                if point.get("milestone"):
                    milestone_count += 1
                    milestone = point["milestone"]
                    assert "title" in milestone, "milestone.title missing"
                    assert "impact_label" in milestone, "milestone.impact_label missing"
        
        assert milestone_count > 0, "Expected at least one milestone in points"
        print(f"PASS: Found {milestone_count} milestones across all ranges")
    
    def test_growth_scores_in_valid_range(self):
        """Verify growth_score and benchmark_score are in valid range (0-100)"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        data = response.json()
        gi = data.get("growth_intelligence", {})
        ranges = gi.get("ranges", {})
        
        for range_key, range_data in ranges.items():
            for i, point in enumerate(range_data.get("points", [])):
                gs = point.get("growth_score", 0)
                bs = point.get("benchmark_score", 0)
                assert 0 <= gs <= 100, f"ranges.{range_key}.points[{i}].growth_score={gs} out of range"
                assert 0 <= bs <= 100, f"ranges.{range_key}.points[{i}].benchmark_score={bs} out of range"
        
        print("PASS: All growth_score and benchmark_score values in valid range (0-100)")


class TestLiveMetricsModes:
    """Tests for different modes of the live-metrics endpoint"""
    
    def test_standard_mode(self):
        """Verify standard mode returns growth_intelligence"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=standard")
        assert response.status_code == 200
        data = response.json()
        assert "growth_intelligence" in data
        print("PASS: standard mode returns growth_intelligence")
    
    def test_stream_mode(self):
        """Verify stream mode returns growth_intelligence"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=stream")
        assert response.status_code == 200
        data = response.json()
        assert "growth_intelligence" in data
        print("PASS: stream mode returns growth_intelligence")
    
    def test_sse_mode_content_type(self):
        """Verify SSE mode returns text/event-stream content type"""
        response = requests.get(f"{BASE_URL}/api/system/live-metrics?mode=sse", stream=True)
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type, f"Expected text/event-stream, got {content_type}"
        print("PASS: SSE mode returns correct content-type")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
