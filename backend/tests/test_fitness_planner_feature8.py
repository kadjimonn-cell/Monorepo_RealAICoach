"""
Feature 8: Fitness Planner Pro - Backend API Tests
Tests for workout plans, progress tracking, exercises, and personal records.
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
VALID_GUEST_ID = "user_testfeature8abc12345"
INVALID_GUEST_ID = "invalid_id"
CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


class TestFitnessBootstrap:
    """Bootstrap endpoint tests"""
    
    def test_bootstrap_with_valid_guest_id(self):
        """Bootstrap returns tier, usage, and features for valid guest ID"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "owner_id" in data
        assert data["owner_id"] == f"guest:{VALID_GUEST_ID}"
        assert "tier" in data
        assert data["tier"] in ["free", "basic", "premium"]
        assert "usage" in data
        assert "tier_limits" in data
        assert "features" in data
        assert "exercise_categories" in data
        
    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """Bootstrap without fallback_user_id returns 401 fitness_auth_required"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/bootstrap")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "fitness_auth_required"
        
    def test_bootstrap_with_invalid_guest_id_returns_400(self):
        """Bootstrap with invalid guest ID returns 400 fitness_invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "fitness_invalid_guest_id"


class TestWorkoutPlans:
    """Workout plans CRUD tests"""
    
    def test_list_workout_plans_empty(self):
        """List workout plans returns empty list for new user"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/workout-plans",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert isinstance(data["plans"], list)
        assert "count" in data
        
    def test_list_workout_plans_without_auth_returns_401(self):
        """List workout plans without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/workout-plans")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "fitness_auth_required"
        
    def test_create_workout_plan(self):
        """Create workout plan returns plan with correct structure or tier limit error"""
        payload = {
            "fallback_user_id": VALID_GUEST_ID,
            "plan_name": f"Test Plan {uuid.uuid4().hex[:8]}",
            "plan_type": "weekly",
            "focus_areas": ["strength", "cardio"],
            "difficulty": "intermediate",
            "duration_weeks": 4,
            "session_duration_minutes": 45,
            "equipment_available": ["bodyweight", "dumbbells"]
        }
        response = requests.post(
            f"{BASE_URL}/api/fitness-planner/workout-plans",
            json=payload,
            headers=CSRF_HEADERS
        )
        
        # Either 200 (success) or 403 (tier limit reached) is acceptable
        assert response.status_code in [200, 403]
        data = response.json()
        
        if response.status_code == 200:
            # Verify response structure
            assert "message" in data
            assert "plan" in data
            plan = data["plan"]
            assert "plan_id" in plan
            assert plan["plan_name"] == payload["plan_name"]
            assert plan["focus_areas"] == payload["focus_areas"]
            assert plan["difficulty"] == payload["difficulty"]
            assert plan["owner_id"] == f"guest:{VALID_GUEST_ID}"
        else:
            # Tier limit reached - verify error structure
            assert "detail" in data
            assert data["detail"]["error_code"] == "workout_plan_limit_reached"
            print(f"Tier limit reached: {data['detail']['message']}")
        
    def test_get_workout_plan_by_id(self):
        """Get specific workout plan by ID"""
        # Get existing plans first
        list_response = requests.get(
            f"{BASE_URL}/api/fitness-planner/workout-plans",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert list_response.status_code == 200
        plans = list_response.json()["plans"]
        
        if not plans:
            pytest.skip("No existing plans to test get by ID")
        
        # Use the first existing plan
        plan_id = plans[0]["plan_id"]
        
        # Get the plan
        get_response = requests.get(
            f"{BASE_URL}/api/fitness-planner/workout-plans/{plan_id}",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert "plan" in data
        assert data["plan"]["plan_id"] == plan_id
        
    def test_delete_workout_plan(self):
        """Delete workout plan archives it"""
        # Get existing plans first
        list_response = requests.get(
            f"{BASE_URL}/api/fitness-planner/workout-plans",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert list_response.status_code == 200
        plans = list_response.json()["plans"]
        
        if not plans:
            pytest.skip("No existing plans to delete")
        
        # Use the first existing plan for deletion test
        plan_id = plans[0]["plan_id"]
        
        # Delete the plan
        delete_response = requests.delete(
            f"{BASE_URL}/api/fitness-planner/workout-plans/{plan_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["message"] == "Workout plan archived successfully"


class TestWorkoutHistory:
    """Workout history tests"""
    
    def test_get_workout_history(self):
        """Get workout history returns list"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/workouts/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        assert "count" in data
        assert "period_days" in data
        
    def test_get_workout_history_without_auth_returns_401(self):
        """Get workout history without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/workouts/history")
        assert response.status_code == 401


class TestProgressAnalytics:
    """Progress analytics tests"""
    
    def test_get_progress_analytics(self):
        """Get progress analytics returns trends and data"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/progress/analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert "trends" in data
        assert "raw_data" in data
        
    def test_get_progress_analytics_without_auth_returns_401(self):
        """Get progress analytics without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/progress/analytics")
        assert response.status_code == 401


class TestExerciseLibrary:
    """Exercise library tests"""
    
    def test_get_exercises(self):
        """Get exercise library returns list"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/exercises")
        assert response.status_code == 200
        data = response.json()
        assert "exercises" in data
        assert isinstance(data["exercises"], list)
        assert "count" in data
        assert "filters" in data
        
    def test_get_exercises_with_filters(self):
        """Get exercises with filters"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/exercises",
            params={"muscle_group": "chest", "difficulty": "beginner"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "exercises" in data
        assert data["filters"]["muscle_group"] == "chest"
        assert data["filters"]["difficulty"] == "beginner"


class TestPersonalRecords:
    """Personal records tests"""
    
    def test_get_personal_records(self):
        """Get personal records returns list"""
        response = requests.get(
            f"{BASE_URL}/api/fitness-planner/personal-records",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert "personal_records" in data
        assert isinstance(data["personal_records"], list)
        assert "count" in data
        
    def test_get_personal_records_without_auth_returns_401(self):
        """Get personal records without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/fitness-planner/personal-records")
        assert response.status_code == 401


class TestPublicAPIContract:
    """Public API contract tests"""
    
    def test_fitness_planner_prefix_is_public(self):
        """Verify /api/fitness-planner/ is in public API contract"""
        # Import the contract module
        import sys
        sys.path.insert(0, '/app/backend')
        from utils.public_api_contract import PUBLIC_API_PREFIXES, is_public_api_path
        
        # Check prefix is in contract
        assert "/api/fitness-planner/" in PUBLIC_API_PREFIXES
        
        # Check various paths are recognized as public
        assert is_public_api_path("/api/fitness-planner/bootstrap")
        assert is_public_api_path("/api/fitness-planner/workout-plans")
        assert is_public_api_path("/api/fitness-planner/exercises")
        assert is_public_api_path("/api/fitness-planner/personal-records")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
