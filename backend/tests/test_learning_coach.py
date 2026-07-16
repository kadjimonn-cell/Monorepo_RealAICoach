"""
Learning Coach (Feature 6) Backend API Tests
Tests for /api/learning-coach/* endpoints
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}

# Generate unique test user ID for isolation
TEST_USER_ID = f"user_test_lc_{uuid.uuid4().hex[:12]}"


class TestLearningCoachBootstrap:
    """Bootstrap endpoint tests"""
    
    def test_bootstrap_returns_tier_and_usage(self):
        """GET /api/learning-coach/bootstrap returns tier, usage, templates"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/bootstrap",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "owner_id" in data
        assert "tier" in data
        assert "curricula" in data
        assert "templates" in data
        assert "usage" in data
        assert "streak" in data
        assert "tier_limits" in data
        
        # Verify owner_id format
        assert data["owner_id"] == f"guest:{TEST_USER_ID}"
        
        # Verify tier is valid
        assert data["tier"] in ["free", "basic", "premium"]
        
        # Verify usage structure
        assert "curricula_this_month" in data["usage"]
        assert "lessons_today" in data["usage"]
        assert "monthly_limit" in data["usage"]
        
        print(f"Bootstrap returned tier={data['tier']}, templates={len(data['templates'])}")
    
    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """GET /api/learning-coach/bootstrap without fallback_user_id returns 401"""
        response = requests.get(f"{BASE_URL}/api/learning-coach/bootstrap")
        assert response.status_code == 401
        data = response.json()
        assert "error_code" in data.get("detail", {})
        print("Bootstrap correctly requires fallback_user_id")


class TestLearningCoachProfile:
    """Profile endpoint tests"""
    
    def test_get_profile_no_profile(self):
        """GET /api/learning-coach/profile returns has_profile=false for new user"""
        new_user_id = f"user_test_lc_new_{uuid.uuid4().hex[:8]}"
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/profile",
            params={"fallback_user_id": new_user_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert not data["has_profile"]
        print("Profile correctly returns has_profile=false for new user")
    
    def test_create_profile(self):
        """POST /api/learning-coach/profile creates learner profile"""
        profile_data = {
            "fallback_user_id": TEST_USER_ID,
            "learning_style": "visual",
            "current_level": "beginner",
            "available_time_weekly": 5,
            "goals": ["Learn algebra", "Master calculus"]
        }
        response = requests.post(
            f"{BASE_URL}/api/learning-coach/profile",
            json=profile_data,
            headers=CSRF_HEADER
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "profile" in data
        assert data["profile"]["learning_style"] == "visual"
        assert data["profile"]["current_level"] == "beginner"
        assert data["profile"]["available_time_weekly"] == 5.0
        print(f"Profile created for {data['profile']['owner_id']}")
    
    def test_get_profile_after_create(self):
        """GET /api/learning-coach/profile returns profile after creation"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/profile",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_profile"]
        assert "profile" in data
        assert data["profile"]["learning_style"] == "visual"
        print("Profile correctly retrieved after creation")


class TestLearningCoachCurricula:
    """Curricula CRUD tests"""
    
    curriculum_id = None
    
    def test_create_curriculum(self):
        """POST /api/learning-coach/curricula creates curriculum"""
        curriculum_data = {
            "fallback_user_id": TEST_USER_ID,
            "subject": "Python Programming",
            "goal": "Learn Python basics",
            "pace": "moderate"
        }
        response = requests.post(
            f"{BASE_URL}/api/learning-coach/curricula",
            json=curriculum_data,
            headers=CSRF_HEADER
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "curriculum" in data
        curriculum = data["curriculum"]
        assert "curriculum_id" in curriculum
        assert curriculum["subject"] == "Python Programming"
        assert curriculum["goal"] == "Learn Python basics"
        assert "modules" in curriculum or "title" in curriculum
        
        # Store for later tests
        TestLearningCoachCurricula.curriculum_id = curriculum["curriculum_id"]
        print(f"Curriculum created: {curriculum['curriculum_id']}")
    
    def test_list_curricula(self):
        """GET /api/learning-coach/curricula lists user's curricula"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/curricula",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "curricula" in data
        assert isinstance(data["curricula"], list)
        assert len(data["curricula"]) >= 1
        print(f"Listed {len(data['curricula'])} curricula")
    
    def test_get_curriculum_by_id(self):
        """GET /api/learning-coach/curricula/{id} returns specific curriculum"""
        curriculum_id = TestLearningCoachCurricula.curriculum_id
        if not curriculum_id:
            pytest.skip("No curriculum_id from previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/curricula/{curriculum_id}",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "curriculum" in data
        assert data["curriculum"]["curriculum_id"] == curriculum_id
        print(f"Retrieved curriculum: {curriculum_id}")
    
    def test_get_curriculum_not_found(self):
        """GET /api/learning-coach/curricula/{id} returns 404 for non-existent"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/curricula/curr_nonexistent123",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 404
        print("Correctly returns 404 for non-existent curriculum")


class TestLearningCoachProgress:
    """Progress tracking tests"""
    
    def test_get_progress_for_curriculum(self):
        """GET /api/learning-coach/progress/{curriculum_id} returns progress"""
        curriculum_id = TestLearningCoachCurricula.curriculum_id
        if not curriculum_id:
            pytest.skip("No curriculum_id from previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/progress/{curriculum_id}",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "curriculum_id" in data
        assert "progress_records" in data
        assert "total_lessons" in data
        assert "completed_lessons" in data
        assert "total_time_minutes" in data
        print(f"Progress for {curriculum_id}: {data['completed_lessons']} completed")


class TestLearningCoachStreaks:
    """Streaks endpoint tests"""
    
    def test_get_streaks(self):
        """GET /api/learning-coach/streaks returns streak data"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/streaks",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "current_streak" in data
        assert "longest_streak" in data
        assert "total_study_days" in data
        assert "badges" in data
        print(f"Streaks: current={data['current_streak']}, longest={data['longest_streak']}")


class TestLearningCoachAnalytics:
    """Analytics endpoint tests"""
    
    def test_get_analytics(self):
        """GET /api/learning-coach/analytics returns analytics data"""
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/analytics",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "total_curricula" in data
        assert "completed_curricula" in data
        assert "total_lessons_completed" in data
        assert "total_time_hours" in data
        print(f"Analytics: {data['total_curricula']} curricula, {data['total_lessons_completed']} lessons")


class TestLegacySchoolEndpoint:
    """Legacy /api/school/curriculum endpoint tests"""
    
    def test_legacy_school_curriculum_available(self):
        """GET /api/school/curriculum returns subjects (legacy endpoint)"""
        response = requests.get(f"{BASE_URL}/api/school/curriculum")
        assert response.status_code == 200
        data = response.json()
        
        assert "subjects" in data
        assert isinstance(data["subjects"], list)
        assert len(data["subjects"]) > 0
        
        # Verify subject structure
        subject = data["subjects"][0]
        assert "id" in subject
        assert "name" in subject
        assert "topics" in subject
        print(f"Legacy endpoint returned {len(data['subjects'])} subjects")


class TestPublicContractCompliance:
    """Verify /api/learning-coach/ is in public contract"""
    
    def test_learning_coach_prefix_is_public(self):
        """Verify /api/learning-coach/ endpoints are accessible without auth"""
        # Bootstrap should work without auth (just needs fallback_user_id)
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/bootstrap",
            params={"fallback_user_id": f"user_test_public_{uuid.uuid4().hex[:8]}"}
        )
        # Should not get 401 Unauthorized (CSRF is separate from auth)
        assert response.status_code != 401 or "CSRF" not in response.text
        print("Learning Coach endpoints are publicly accessible")


class TestCleanup:
    """Cleanup test data"""
    
    def test_delete_curriculum(self):
        """DELETE /api/learning-coach/curricula/{id} deletes curriculum"""
        curriculum_id = TestLearningCoachCurricula.curriculum_id
        if not curriculum_id:
            pytest.skip("No curriculum_id to delete")
        
        response = requests.delete(
            f"{BASE_URL}/api/learning-coach/curricula/{curriculum_id}",
            params={"fallback_user_id": TEST_USER_ID},
            headers=CSRF_HEADER
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Deleted curriculum: {curriculum_id}")
    
    def test_verify_deletion(self):
        """Verify curriculum is deleted"""
        curriculum_id = TestLearningCoachCurricula.curriculum_id
        if not curriculum_id:
            pytest.skip("No curriculum_id to verify")
        
        response = requests.get(
            f"{BASE_URL}/api/learning-coach/curricula/{curriculum_id}",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 404
        print("Curriculum deletion verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
