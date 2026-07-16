"""
Feature 12: Relationship Coach - Backend API Tests

Tests for:
1. Strict guest-id validation (user_* format required)
2. Invalid fallback_user_id returns 400 invalid_guest_id
3. Missing auth/fallback returns 401 auth_required
4. Valid user_* fallback returns 200 for bootstrap and key endpoints
5. Core CRUD operations for important dates
6. AI endpoints validation
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
VALID_GUEST_ID = "user_testfeature12abc12345"

# Headers for CSRF bypass
HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}
INVALID_GUEST_ID_SHORT = "user_abc"  # Too short (< 12 chars after prefix)
INVALID_GUEST_ID_FORMAT = "guest_12345678901234"  # Wrong prefix
INVALID_GUEST_ID_CHARS = "user_abc!@#$%^&*()"  # Invalid characters


class TestRelationshipCoachGuestIdValidation:
    """Test strict guest-id validation for relationship-coach endpoints"""

    def test_bootstrap_with_valid_guest_id(self):
        """Valid user_* fallback returns 200 for bootstrap"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert data["owner_id"] == f"guest:{VALID_GUEST_ID}"
        print(f"PASS: Bootstrap with valid guest ID returns 200, tier={data['tier']}")

    def test_bootstrap_missing_auth_returns_401(self):
        """Missing auth/fallback returns 401 auth_required"""
        response = requests.get(f"{BASE_URL}/api/relationship-coach/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "auth_required"
        print("PASS: Missing auth returns 401 auth_required")

    def test_bootstrap_invalid_guest_id_short(self):
        """Invalid fallback_user_id (too short) returns 400 invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_SHORT}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Short guest ID returns 400 invalid_guest_id")

    def test_bootstrap_invalid_guest_id_format(self):
        """Invalid fallback_user_id (wrong prefix) returns 400 invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_FORMAT}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Wrong prefix guest ID returns 400 invalid_guest_id")

    def test_bootstrap_invalid_guest_id_chars(self):
        """Invalid fallback_user_id (invalid chars) returns 400 invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_CHARS}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Invalid chars guest ID returns 400 invalid_guest_id")


class TestRelationshipCoachCoreEndpoints:
    """Test core relationship-coach endpoints with valid guest ID"""

    def test_profile_create_and_get(self):
        """Test profile creation and retrieval"""
        unique_id = f"user_test12profile{uuid.uuid4().hex[:12]}"
        
        # Create profile
        create_response = requests.post(
            f"{BASE_URL}/api/relationship-coach/profile",
            headers=HEADERS,
            json={
                "relationship_status": "committed",
                "partner_name": "Test Partner",
                "challenges": ["communication"],
                "goals": ["better understanding"],
                "fallback_user_id": unique_id
            }
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        data = create_response.json()
        assert data.get("message") in ["Profile created", "Profile updated"]
        print("PASS: Profile created successfully")

        # Get profile
        get_response = requests.get(
            f"{BASE_URL}/api/relationship-coach/profile",
            params={"fallback_user_id": unique_id}
        )
        assert get_response.status_code == 200, f"Get failed: {get_response.text}"
        profile = get_response.json().get("profile", {})
        assert profile.get("relationship_status") == "committed"
        assert profile.get("partner_name") == "Test Partner"
        print("PASS: Profile retrieved successfully")

    def test_important_dates_crud(self):
        """Test important dates CRUD operations"""
        unique_id = f"user_test12dates{uuid.uuid4().hex[:12]}"
        
        # Create important date
        create_response = requests.post(
            f"{BASE_URL}/api/relationship-coach/important-dates",
            headers=HEADERS,
            json={
                "title": "Test Anniversary",
                "date": "2026-06-15",
                "category": "anniversary",
                "reminder_days": 7,
                "notes": "Test note",
                "fallback_user_id": unique_id
            }
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        data = create_response.json()
        assert "date_id" in data
        date_id = data["date_id"]
        print(f"PASS: Important date created with ID: {date_id}")

        # Get important dates
        get_response = requests.get(
            f"{BASE_URL}/api/relationship-coach/important-dates",
            params={"fallback_user_id": unique_id}
        )
        assert get_response.status_code == 200, f"Get failed: {get_response.text}"
        dates = get_response.json().get("dates", [])
        assert len(dates) >= 1
        assert any(d["date_id"] == date_id for d in dates)
        print("PASS: Important dates retrieved successfully")

        # Update important date
        update_response = requests.put(
            f"{BASE_URL}/api/relationship-coach/important-dates/{date_id}",
            headers=HEADERS,
            json={
                "title": "Updated Anniversary",
                "date": "2026-06-20",
                "category": "anniversary",
                "reminder_days": 14,
                "notes": "Updated note",
                "fallback_user_id": unique_id
            }
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        print("PASS: Important date updated successfully")

        # Delete important date
        delete_response = requests.delete(
            f"{BASE_URL}/api/relationship-coach/important-dates/{date_id}",
            headers=HEADERS,
            params={"fallback_user_id": unique_id}
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        print("PASS: Important date deleted successfully")

        # Verify deletion
        verify_response = requests.get(
            f"{BASE_URL}/api/relationship-coach/important-dates",
            params={"fallback_user_id": unique_id}
        )
        dates_after = verify_response.json().get("dates", [])
        assert not any(d["date_id"] == date_id for d in dates_after)
        print("PASS: Important date deletion verified")

    def test_upcoming_reminders(self):
        """Test upcoming reminders endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/upcoming-reminders",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "upcoming_dates" in data
        print("PASS: Upcoming reminders endpoint returns 200")

    def test_sessions_history(self):
        """Test sessions history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/sessions",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "sessions" in data
        print("PASS: Sessions history endpoint returns 200")

    def test_analytics_endpoint(self):
        """Test analytics endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_advice_sessions" in data
        assert "total_date_ideas_generated" in data
        assert "total_assessments" in data
        assert "important_dates_tracked" in data
        print("PASS: Analytics endpoint returns 200 with expected fields")

    def test_assessments_history(self):
        """Test assessments history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/assessments/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "assessments" in data
        print("PASS: Assessments history endpoint returns 200")

    def test_date_ideas_history(self):
        """Test date ideas history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/date-ideas/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data
        print("PASS: Date ideas history endpoint returns 200")

    def test_gift_ideas_history(self):
        """Test gift ideas history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/gift-ideas/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data
        print("PASS: Gift ideas history endpoint returns 200")

    def test_communication_tips_history(self):
        """Test communication tips history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/communication-tips/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data
        print("PASS: Communication tips history endpoint returns 200")


class TestRelationshipCoachAIEndpointsValidation:
    """Test AI endpoints reject invalid guest IDs"""

    def test_advice_invalid_guest_id(self):
        """AI advice endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/advice",
            headers=HEADERS,
            json={
                "situation": "Test situation",
                "fallback_user_id": INVALID_GUEST_ID_SHORT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Advice endpoint rejects invalid guest ID")

    def test_date_ideas_invalid_guest_id(self):
        """Date ideas endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/date-ideas",
            headers=HEADERS,
            json={
                "budget": "moderate",
                "fallback_user_id": INVALID_GUEST_ID_FORMAT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Date ideas endpoint rejects invalid guest ID")

    def test_gift_ideas_invalid_guest_id(self):
        """Gift ideas endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/gift-ideas",
            headers=HEADERS,
            json={
                "occasion": "birthday",
                "fallback_user_id": INVALID_GUEST_ID_SHORT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Gift ideas endpoint rejects invalid guest ID")

    def test_conversation_starters_invalid_guest_id(self):
        """Conversation starters endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/conversation-starters",
            headers=HEADERS,
            json={
                "relationship_stage": "committed",
                "fallback_user_id": INVALID_GUEST_ID_FORMAT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Conversation starters endpoint rejects invalid guest ID")

    def test_communication_tips_invalid_guest_id(self):
        """Communication tips endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/communication-tips",
            headers=HEADERS,
            json={
                "scenario": "difficult_conversation",
                "fallback_user_id": INVALID_GUEST_ID_SHORT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Communication tips endpoint rejects invalid guest ID")

    def test_assessment_invalid_guest_id(self):
        """Assessment endpoint rejects invalid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/assessment",
            headers=HEADERS,
            json={
                "communication_score": 7,
                "trust_score": 8,
                "intimacy_score": 7,
                "conflict_resolution_score": 6,
                "shared_goals_score": 8,
                "fallback_user_id": INVALID_GUEST_ID_FORMAT
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id"
        print("PASS: Assessment endpoint rejects invalid guest ID")


class TestRelationshipCoachAssessment:
    """Test assessment functionality with valid guest ID"""

    def test_assessment_submission(self):
        """Test assessment submission and result"""
        unique_id = f"user_test12assess{uuid.uuid4().hex[:12]}"
        
        response = requests.post(
            f"{BASE_URL}/api/relationship-coach/assessment",
            headers=HEADERS,
            json={
                "communication_score": 8,
                "trust_score": 9,
                "intimacy_score": 7,
                "conflict_resolution_score": 6,
                "shared_goals_score": 8,
                "notes": "Test assessment",
                "fallback_user_id": unique_id
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "assessment_id" in data
        assert "health_score" in data
        assert "strengths" in data
        assert "improvement_areas" in data
        
        # Health score should be calculated correctly: (8+9+7+6+8)/50 * 100 = 76%
        expected_score = (8 + 9 + 7 + 6 + 8) / 50 * 100
        assert abs(data["health_score"] - expected_score) < 0.1
        print(f"PASS: Assessment submitted successfully, health_score={data['health_score']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
