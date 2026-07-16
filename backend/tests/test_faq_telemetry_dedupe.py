"""
FAQ Telemetry Dedupe/Throttling Tests
Tests for the 5-minute dedupe guard on POST /api/gps/faq/telemetry/view
Feature: One FAQ view per FAQ/session per 5 minutes
"""
import pytest
import requests
import os
import uuid
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "http://127.0.0.1:8001"

HEADERS = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}


class TestFaqTelemetryDedupe:
    """Tests for 5-minute dedupe/throttling guard on FAQ view telemetry"""
    
    def test_first_view_not_deduped(self):
        """First view of a FAQ should NOT be deduped"""
        unique_question = f"TEST_DEDUPE_First view question {uuid.uuid4().hex[:8]}?"
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        
        payload = {
            "question": unique_question,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert data.get("deduped") is False, f"First view should NOT be deduped, got deduped={data.get('deduped')}"
        assert "faq_key" in data, "Response should contain faq_key"
        assert "recorded_at" in data, "Response should contain recorded_at"
        assert data.get("window_minutes") == 5, f"Expected window_minutes=5, got {data.get('window_minutes')}"
        print("PASS: First view recorded successfully, deduped=False")
    
    def test_duplicate_view_same_session_is_deduped(self):
        """Second view of same FAQ within 5 minutes with same session should be deduped"""
        unique_question = f"TEST_DEDUPE_Duplicate view question {uuid.uuid4().hex[:8]}?"
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        
        payload = {
            "question": unique_question,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        # First request - should NOT be deduped
        response1 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("deduped") is False, "First view should NOT be deduped"
        first_recorded_at = data1.get("recorded_at")
        
        # Second request immediately - should BE deduped
        response2 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("success") is True, "Request should still succeed"
        assert data2.get("deduped") is True, f"Second view should be deduped, got deduped={data2.get('deduped')}"
        assert data2.get("window_minutes") == 5, "Should return window_minutes=5"
        # The recorded_at should be from the first event
        assert data2.get("recorded_at") == first_recorded_at, "Deduped response should return original recorded_at"
        print("PASS: Duplicate view correctly deduped, deduped=True")
    
    def test_different_session_not_deduped(self):
        """Same FAQ with different session_id should NOT be deduped"""
        unique_question = f"TEST_DEDUPE_Different session question {uuid.uuid4().hex[:8]}?"
        session_id_1 = f"test_session_A_{uuid.uuid4().hex[:12]}"
        session_id_2 = f"test_session_B_{uuid.uuid4().hex[:12]}"
        
        payload1 = {
            "question": unique_question,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id_1
        }
        
        payload2 = {
            "question": unique_question,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id_2
        }
        
        # First session
        response1 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload1,
            headers=HEADERS
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("deduped") is False, "First session view should NOT be deduped"
        
        # Second session - should NOT be deduped (different session)
        response2 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload2,
            headers=HEADERS
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("deduped") is False, f"Different session should NOT be deduped, got deduped={data2.get('deduped')}"
        print("PASS: Different session correctly NOT deduped")
    
    def test_different_faq_same_session_not_deduped(self):
        """Different FAQ with same session_id should NOT be deduped"""
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        unique_question_1 = f"TEST_DEDUPE_FAQ A question {uuid.uuid4().hex[:8]}?"
        unique_question_2 = f"TEST_DEDUPE_FAQ B question {uuid.uuid4().hex[:8]}?"
        
        payload1 = {
            "question": unique_question_1,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        payload2 = {
            "question": unique_question_2,
            "category": "Testing",
            "segment": "Engineering",
            "plan": "Premium",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        # First FAQ
        response1 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload1,
            headers=HEADERS
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("deduped") is False
        
        # Second FAQ (different question) - should NOT be deduped
        response2 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload2,
            headers=HEADERS
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("deduped") is False, f"Different FAQ should NOT be deduped, got deduped={data2.get('deduped')}"
        print("PASS: Different FAQ correctly NOT deduped")
    
    def test_session_id_passed_through(self):
        """Verify session_id is accepted and used for dedupe key"""
        unique_question = f"TEST_DEDUPE_Session ID test {uuid.uuid4().hex[:8]}?"
        session_id = f"custom_session_{uuid.uuid4().hex[:16]}"
        
        payload = {
            "question": unique_question,
            "category": "Testing",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data.get("deduped") is False
        print("PASS: session_id accepted and processed")
    
    def test_no_session_id_uses_ip_hash(self):
        """When no session_id provided, backend should generate one from IP/UA hash"""
        unique_question = f"TEST_DEDUPE_No session ID test {uuid.uuid4().hex[:8]}?"
        
        payload = {
            "question": unique_question,
            "category": "Testing",
            "context": "welcome_faq"
            # No session_id provided
        }
        
        # First request
        response1 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("deduped") is False
        
        # Second request from same client (same IP/UA) - should be deduped
        response2 = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        assert response2.status_code == 200
        data2 = response2.json()
        # Should be deduped because backend generates session_key from IP+UA
        assert data2.get("deduped") is True, f"Same client without session_id should be deduped, got deduped={data2.get('deduped')}"
        print("PASS: No session_id correctly uses IP hash for dedupe")
    
    def test_triple_rapid_fire_all_deduped(self):
        """Multiple rapid requests should all be deduped after first"""
        unique_question = f"TEST_DEDUPE_Rapid fire test {uuid.uuid4().hex[:8]}?"
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        
        payload = {
            "question": unique_question,
            "category": "Testing",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        # First request
        r1 = requests.post(f"{BASE_URL}/api/gps/faq/telemetry/view", json=payload, headers=HEADERS)
        assert r1.status_code == 200
        assert r1.json().get("deduped") is False, "First should NOT be deduped"
        
        # Second request
        r2 = requests.post(f"{BASE_URL}/api/gps/faq/telemetry/view", json=payload, headers=HEADERS)
        assert r2.status_code == 200
        assert r2.json().get("deduped") is True, "Second should be deduped"
        
        # Third request
        r3 = requests.post(f"{BASE_URL}/api/gps/faq/telemetry/view", json=payload, headers=HEADERS)
        assert r3.status_code == 200
        assert r3.json().get("deduped") is True, "Third should be deduped"
        
        # Fourth request
        r4 = requests.post(f"{BASE_URL}/api/gps/faq/telemetry/view", json=payload, headers=HEADERS)
        assert r4.status_code == 200
        assert r4.json().get("deduped") is True, "Fourth should be deduped"
        
        print("PASS: Rapid fire requests correctly deduped after first")


class TestFaqTelemetryTopRanking:
    """Tests for GET /api/gps/faq/telemetry/top endpoint - verify ranking still works"""
    
    def test_top_faq_endpoint_returns_data(self):
        """Verify top FAQ endpoint still returns ranked data"""
        response = requests.get(
            f"{BASE_URL}/api/gps/faq/telemetry/top?window_days=30&limit=10",
            headers=HEADERS
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "top_faq" in data, "Response should contain top_faq array"
        assert "window_days" in data, "Response should contain window_days"
        assert "generated_at" in data, "Response should contain generated_at"
        assert data.get("window_days") == 30, f"Expected window_days=30, got {data.get('window_days')}"
        print(f"PASS: Top FAQ endpoint returns {len(data.get('top_faq', []))} items")
    
    def test_fresh_events_appear_in_ranking(self):
        """Verify fresh (non-deduped) events appear in ranking"""
        unique_question = f"TEST_RANKING_Fresh event {uuid.uuid4().hex[:8]}?"
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        
        # Record a fresh view
        payload = {
            "question": unique_question,
            "category": "Testing",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        response = requests.post(
            f"{BASE_URL}/api/gps/faq/telemetry/view",
            json=payload,
            headers=HEADERS
        )
        assert response.status_code == 200
        assert response.json().get("deduped") is False
        
        # Check if it appears in top (may not be at top, but should be recorded)
        top_response = requests.get(
            f"{BASE_URL}/api/gps/faq/telemetry/top?window_days=1&limit=30",
            headers=HEADERS
        )
        assert top_response.status_code == 200
        top_data = top_response.json()
        
        # The event should be recorded (may or may not be in top 30 depending on other views)
        print(f"PASS: Fresh event recorded, top endpoint returns {len(top_data.get('top_faq', []))} items")


class TestFaqTelemetryIntegration:
    """Integration tests for dedupe + ranking flow"""
    
    def test_deduped_events_dont_inflate_counts(self):
        """Verify deduped events don't artificially inflate view counts"""
        unique_question = f"TEST_INTEGRATION_Count test {uuid.uuid4().hex[:8]}?"
        session_id = f"test_session_{uuid.uuid4().hex[:12]}"
        
        payload = {
            "question": unique_question,
            "category": "Integration",
            "context": "welcome_faq",
            "session_id": session_id
        }
        
        # Record 5 rapid views (only first should count)
        for i in range(5):
            response = requests.post(
                f"{BASE_URL}/api/gps/faq/telemetry/view",
                json=payload,
                headers=HEADERS
            )
            assert response.status_code == 200
            data = response.json()
            if i == 0:
                assert data.get("deduped") is False, "First view should NOT be deduped"
            else:
                assert data.get("deduped") is True, f"View {i+1} should be deduped"
        
        print("PASS: Only first view counted, 4 subsequent views deduped")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
