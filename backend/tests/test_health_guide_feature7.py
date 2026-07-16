"""
Feature 7: Health Guide (MediMate) - Backend API Tests
Tests for P0 fixes: canonical API paths, symptom flow, symptom logs, insights history, medications
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com')
GUEST_USER_ID = "user_testfeature7abc12345"


class TestHealthGuideBootstrap:
    """Bootstrap endpoint tests"""
    
    def test_bootstrap_with_valid_guest_id(self):
        """Bootstrap returns tier, usage, features for valid guest ID"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/bootstrap",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "owner_id" in data
        assert "tier" in data
        assert "usage" in data
        assert "features" in data
        assert "tier_limits" in data
        
        # Verify owner_id format
        assert data["owner_id"] == f"guest:{GUEST_USER_ID}"
        assert data["tier"] == "free"
        
    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """Bootstrap without fallback_user_id returns 401"""
        response = requests.get(f"{BASE_URL}/api/health-guide/bootstrap")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "health_guide_auth_required"
        
    def test_bootstrap_with_invalid_guest_id_returns_400(self):
        """Bootstrap with invalid guest ID format returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/bootstrap",
            params={"fallback_user_id": "invalid_id"}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "health_guide_invalid_guest_id"


class TestHealthGuideSymptomCheck:
    """Symptom check endpoint tests"""
    
    def test_symptom_check_with_correct_payload(self):
        """Symptom check works with required fields: symptoms, duration, severity (string)"""
        response = requests.post(
            f"{BASE_URL}/api/health-guide/symptom-check",
            json={
                "symptoms": ["headache", "fatigue"],
                "severity": "moderate",  # String severity
                "duration": "2 days",     # Required duration field
                "fallback_user_id": GUEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "symptom_summary" in data
        assert "general_information" in data
        assert "self_care_suggestions" in data
        assert "when_to_seek_care" in data
        assert "legal_disclaimer" in data
        
    def test_symptom_check_missing_symptoms_returns_422(self):
        """Symptom check without symptoms returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/health-guide/symptom-check",
            json={
                "severity": "moderate",
                "duration": "2 days",
                "fallback_user_id": GUEST_USER_ID
            }
        )
        assert response.status_code == 422  # Validation error


class TestHealthGuideSymptomHistory:
    """Symptom checks history endpoint tests"""
    
    def test_symptom_checks_history_returns_list(self):
        """GET /api/health-guide/symptom-checks-history returns history list"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/symptom-checks-history",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "symptom_checks_history" in data
        assert "count" in data
        assert isinstance(data["symptom_checks_history"], list)
        
        # If there are entries, verify structure
        if data["count"] > 0:
            entry = data["symptom_checks_history"][0]
            assert "check_id" in entry
            assert "symptoms" in entry
            assert "severity" in entry
            assert "duration" in entry
            assert "created_at" in entry


class TestHealthGuideInsightsHistory:
    """Insights history endpoint tests"""
    
    def test_insights_history_returns_list(self):
        """GET /api/health-guide/insights-history returns history list"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/insights-history",
            params={"fallback_user_id": GUEST_USER_ID, "limit": 1}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "insights_history" in data
        assert "count" in data
        assert isinstance(data["insights_history"], list)


class TestHealthGuideMedications:
    """Medications CRUD endpoint tests"""
    
    def test_list_medications(self):
        """GET /api/health-guide/medications returns medications list"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/medications",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "medications" in data
        assert "count" in data
        assert isinstance(data["medications"], list)
        
    def test_add_medication(self):
        """POST /api/health-guide/medications adds medication"""
        response = requests.post(
            f"{BASE_URL}/api/health-guide/medications",
            json={
                "name": "TestMed_Feature7",
                "dosage": "50mg",
                "frequency": "daily",
                "fallback_user_id": GUEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "medication" in data
        assert data["medication"]["name"] == "TestMed_Feature7"
        assert data["medication"]["dosage"] == "50mg"
        assert data["medication"]["frequency"] == "daily"
        assert "medication_id" in data["medication"]
        
        # Store medication_id for cleanup
        return data["medication"]["medication_id"]
        
    def test_medication_crud_flow(self):
        """Full CRUD flow: create -> list -> verify -> delete"""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/health-guide/medications",
            json={
                "name": "CRUDTestMed",
                "dosage": "25mg",
                "frequency": "twice_daily",
                "fallback_user_id": GUEST_USER_ID
            }
        )
        assert create_response.status_code == 200
        med_id = create_response.json()["medication"]["medication_id"]
        
        # List and verify
        list_response = requests.get(
            f"{BASE_URL}/api/health-guide/medications",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert list_response.status_code == 200
        medications = list_response.json()["medications"]
        found = any(m["medication_id"] == med_id for m in medications)
        assert found, "Created medication should appear in list"
        
        # Delete (deactivate)
        delete_response = requests.delete(
            f"{BASE_URL}/api/health-guide/medications/{med_id}",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert delete_response.status_code == 200


class TestHealthGuidePublicContract:
    """Public API contract tests"""
    
    def test_health_guide_prefix_is_public(self):
        """Verify /api/health-guide/ is in public API contract"""
        # This is verified by the fact that we can access endpoints without auth
        # Just with fallback_user_id
        response = requests.get(
            f"{BASE_URL}/api/health-guide/bootstrap",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200


class TestHealthGuideProfile:
    """Health profile endpoint tests"""
    
    def test_get_profile_no_profile(self):
        """GET /api/health-guide/profile returns no profile message"""
        response = requests.get(
            f"{BASE_URL}/api/health-guide/profile",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "has_profile" in data
        
    def test_create_profile(self):
        """POST /api/health-guide/profile creates profile"""
        response = requests.post(
            f"{BASE_URL}/api/health-guide/profile",
            json={
                "age": 30,
                "gender": "male",
                "height_cm": 175,
                "weight_kg": 70,
                "fallback_user_id": GUEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "profile" in data
        assert data["profile"]["age"] == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
