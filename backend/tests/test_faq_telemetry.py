"""
FAQ Telemetry API Tests
Tests for POST /api/gps/faq/telemetry/view and GET /api/gps/faq/telemetry/top endpoints
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "http://127.0.0.1:8001"


class TestFaqTelemetryView:
    """Tests for POST /api/gps/faq/telemetry/view endpoint"""
    
    def test_record_faq_view_success(self):
        """Test recording a FAQ view successfully"""
        unique_question = f"Test FAQ question {uuid.uuid4().hex[:8]}?"
        payload = {
            "question": unique_question,
            "category": "Getting Started",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq"
        }
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert "faq_key" in data, "Response should contain faq_key"
        assert "recorded_at" in data, "Response should contain recorded_at"
        # Verify faq_key is lowercase normalized
        assert data["faq_key"] == unique_question.lower().strip(), f"faq_key should be lowercase: {data['faq_key']}"
    
    def test_record_faq_view_with_faq_id(self):
        """Test recording a FAQ view with explicit faq_id"""
        payload = {
            "question": "How does pricing work for enterprise?",
            "faq_id": "faq_pricing_enterprise_001",
            "category": "Pricing",
            "segment": "Executive",
            "plan": "Enterprise",
            "context": "welcome_faq"
        }
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        # When faq_id is provided, it should be used as the key
        assert data["faq_key"] == "faq_pricing_enterprise_001"
    
    def test_record_faq_view_minimal_payload(self):
        """Test recording with only required field (question)"""
        payload = {
            "question": "What is the minimum question length?"
        }
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
    
    def test_record_faq_view_invalid_short_question(self):
        """Test that short questions are rejected (min_length=6)"""
        payload = {
            "question": "Hi?"  # Too short
        }
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422 for short question, got {response.status_code}"
    
    def test_record_faq_view_empty_question(self):
        """Test that empty questions are rejected"""
        payload = {
            "question": ""
        }
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422 for empty question, got {response.status_code}"
    
    def test_record_faq_view_all_segments(self):
        """Test recording views with different segments"""
        segments = ["L&D", "Executive", "Compliance", "Engineering", "Revenue", "All"]
        
        for segment in segments:
            payload = {
                "question": f"Test question for segment {segment}?",
                "segment": segment,
                "plan": "Premium",
                "context": "welcome_faq"
            }
            response = requests.post(
                f"{BASE_URL}/api/gps/faq/telemetry/view",
                json=payload,
                headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
            )
            
            assert response.status_code == 200, f"Failed for segment {segment}: {response.text}"
            data = response.json()
            assert data.get("success") is True, f"Failed for segment {segment}"
    
    def test_record_faq_view_all_plans(self):
        """Test recording views with different plans"""
        plans = ["Free", "Basic", "Premium", "Enterprise"]
        
        for plan in plans:
            payload = {
                "question": f"Test question for plan {plan}?",
                "plan": plan,
                "context": "welcome_faq"
            }
            response = requests.post(
                f"{BASE_URL}/api/gps/faq/telemetry/view",
                json=payload,
                headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
            )
            
            assert response.status_code == 200, f"Failed for plan {plan}: {response.text}"
            data = response.json()
            assert data.get("success") is True, f"Failed for plan {plan}"


class TestFaqTelemetryTop:
    """Tests for GET /api/gps/faq/telemetry/top endpoint"""
    
    def test_get_top_faq_default_params(self):
        """Test getting top FAQ with default parameters"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "window_days" in data, "Response should contain window_days"
        assert "generated_at" in data, "Response should contain generated_at"
        assert "top_faq" in data, "Response should contain top_faq"
        assert isinstance(data["top_faq"], list), "top_faq should be a list"
        
        # Default window is 30 days
        assert data["window_days"] == 30, f"Default window should be 30, got {data['window_days']}"
    
    def test_get_top_faq_custom_window(self):
        """Test getting top FAQ with custom window_days"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?window_days=7")
        
        assert response.status_code == 200
        data = response.json()
        assert data["window_days"] == 7
    
    def test_get_top_faq_custom_limit(self):
        """Test getting top FAQ with custom limit"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        # Limit should cap results
        assert len(data["top_faq"]) <= 5
    
    def test_get_top_faq_max_window(self):
        """Test that window_days is capped at 180"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?window_days=365")
        
        assert response.status_code == 200
        data = response.json()
        # Should be capped at 180
        assert data["window_days"] == 180, f"Window should be capped at 180, got {data['window_days']}"
    
    def test_get_top_faq_max_limit(self):
        """Test that limit is capped at 30"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?limit=100")
        
        assert response.status_code == 200
        data = response.json()
        # Results should be capped at 30
        assert len(data["top_faq"]) <= 30
    
    def test_get_top_faq_response_structure(self):
        """Test that each FAQ item has correct structure"""
        # First record a view to ensure we have data
        payload = {
            "question": "Test structure question for telemetry?",
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq"
        }
        requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?limit=10")
        
        assert response.status_code == 200
        data = response.json()
        
        if data["top_faq"]:
            item = data["top_faq"][0]
            # Verify item structure
            assert "faq_key" in item, "Item should have faq_key"
            assert "faq_id" in item, "Item should have faq_id"
            assert "question" in item, "Item should have question"
            assert "category" in item, "Item should have category"
            assert "views" in item, "Item should have views"
            assert "last_viewed_at" in item, "Item should have last_viewed_at"
            assert "segments" in item, "Item should have segments"
            assert "plans" in item, "Item should have plans"
            
            # Verify types
            assert isinstance(item["views"], int), "views should be int"
            assert isinstance(item["segments"], list), "segments should be list"
            assert isinstance(item["plans"], list), "plans should be list"
    
    def test_get_top_faq_sorted_by_views(self):
        """Test that results are sorted by views descending"""
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?limit=10")
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data["top_faq"]) >= 2:
            views = [item["views"] for item in data["top_faq"]]
            # Verify descending order
            assert views == sorted(views, reverse=True), "Results should be sorted by views descending"


class TestFaqTelemetryIntegration:
    """Integration tests for FAQ telemetry flow"""
    
    def test_record_and_retrieve_flow(self):
        """Test full flow: record views and verify they appear in top list"""
        unique_question = f"Integration test FAQ {uuid.uuid4().hex[:8]}?"
        
        # Record multiple views for the same question
        for i in range(3):
            payload = {
                "question": unique_question,
                "category": "Integration",
                "segment": "Engineering",
                "plan": "Enterprise",
                "context": "welcome_faq"
            }
            response = requests.post(
                f"{BASE_URL}/api/gps/faq/telemetry/view",
                json=payload,
                headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
            )
            assert response.status_code == 200
        
        # Retrieve top FAQ
        response = requests.get(f"{BASE_URL}/api/gps/faq/telemetry/top?limit=20")
        assert response.status_code == 200
        data = response.json()
        
        # Find our question in results
        found = False
        for item in data["top_faq"]:
            if item["question"].lower() == unique_question.lower():
                found = True
                assert item["views"] >= 3, f"Expected at least 3 views, got {item['views']}"
                assert "Engineering" in item["segments"], "Segment should be recorded"
                assert "Enterprise" in item["plans"], "Plan should be recorded"
                break
        
        assert found, f"Question '{unique_question}' should appear in top FAQ results"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
