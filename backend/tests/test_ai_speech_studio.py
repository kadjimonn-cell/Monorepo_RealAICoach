# ruff: noqa
"""
Voice Studio (Feature 17) - AI Speech Studio Backend API Tests
Tests: health, bootstrap, project create, analyze, history, and free plan limit enforcement
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Generate unique guest ID for test isolation
TEST_GUEST_ID = f"user_test_{uuid.uuid4().hex[:16]}"
LIMIT_TEST_GUEST_ID = f"user_limit_{uuid.uuid4().hex[:16]}"


class TestAISpeechStudioHealth:
    """Health endpoint tests"""
    
    def test_health_endpoint_returns_200(self):
        """GET /api/ai-speech-studio/health should return 200 with healthy status"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got: {data}"
        assert data.get("feature") == "Voice Studio", f"Expected 'Voice Studio' feature, got: {data}"
        assert data.get("feature_id") == "ai-speech", f"Expected 'ai-speech' feature_id, got: {data}"
        print(f"✓ Health endpoint: {data}")


class TestAISpeechStudioBootstrap:
    """Bootstrap endpoint tests for guest flow"""
    
    def test_bootstrap_guest_flow_returns_200(self):
        """GET /api/ai-speech-studio/bootstrap with fallback_user_id should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/bootstrap",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert data.get("feature_id") == "ai-speech", f"Expected feature_id='ai-speech', got: {data}"
        assert data.get("plan") == "free", f"Expected plan='free' for guest, got: {data}"
        assert "limits" in data, f"Expected 'limits' in response, got: {data}"
        assert "usage" in data, f"Expected 'usage' in response, got: {data}"
        assert "projects" in data, f"Expected 'projects' in response, got: {data}"
        assert "recent_history" in data, f"Expected 'recent_history' in response, got: {data}"
        
        # Verify free plan limits structure
        limits = data.get("limits", {})
        assert "projects_per_month" in limits, f"Expected 'projects_per_month' in limits, got: {limits}"
        assert "analyses_per_day" in limits, f"Expected 'analyses_per_day' in limits, got: {limits}"
        assert limits.get("projects_per_month") == 2, f"Expected free plan projects_per_month=2, got: {limits}"
        assert limits.get("analyses_per_day") == 5, f"Expected free plan analyses_per_day=5, got: {limits}"
        
        print(f"✓ Bootstrap guest flow: plan={data.get('plan')}, limits={limits}")
    
    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """GET /api/ai-speech-studio/bootstrap without fallback_user_id should return 401"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_auth_required", f"Expected error_code='ai_speech_auth_required', got: {detail}"
        print(f"✓ Bootstrap without auth returns 401: {detail}")
    
    def test_bootstrap_with_invalid_guest_id_returns_400(self):
        """GET /api/ai-speech-studio/bootstrap with invalid fallback_user_id format should return 400"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/bootstrap",
            params={"fallback_user_id": "invalid_format"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_invalid_guest_id", f"Expected error_code='ai_speech_invalid_guest_id', got: {detail}"
        print(f"✓ Bootstrap with invalid guest ID returns 400: {detail}")


class TestAISpeechStudioProjectCreate:
    """Project creation endpoint tests"""
    
    def test_create_project_guest_flow_returns_200(self):
        """POST /api/ai-speech-studio/projects/create should create project for guest"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Test Project {uuid.uuid4().hex[:8]}",
                "brief": "Test brief for speech coaching",
                "objective": "presentation",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "project" in data, f"Expected 'project' in response, got: {data}"
        
        project = data.get("project", {})
        assert "project_id" in project, f"Expected 'project_id' in project, got: {project}"
        assert project.get("project_id").startswith("aivs_"), f"Expected project_id to start with 'aivs_', got: {project}"
        assert "title" in project, f"Expected 'title' in project, got: {project}"
        assert "created_at" in project, f"Expected 'created_at' in project, got: {project}"
        
        print(f"✓ Create project: project_id={project.get('project_id')}, title={project.get('title')}")
        return project.get("project_id")
    
    def test_create_project_without_title_returns_422(self):
        """POST /api/ai-speech-studio/projects/create without title should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "brief": "Test brief",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        print(f"✓ Create project without title returns 422")
    
    def test_create_project_without_auth_returns_401(self):
        """POST /api/ai-speech-studio/projects/create without auth should return 401"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": "Test Project",
                "brief": "Test brief"
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Create project without auth returns 401")


class TestAISpeechStudioAnalyze:
    """Project analysis endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for analysis tests"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Analysis Test Project {uuid.uuid4().hex[:8]}",
                "brief": "Project for analysis testing",
                "objective": "presentation",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if response.status_code == 200:
            self.project_id = response.json().get("project", {}).get("project_id")
        else:
            self.project_id = None
    
    def test_analyze_project_guest_flow_returns_200(self):
        """POST /api/ai-speech-studio/projects/{id}/analyze should return analysis"""
        if not self.project_id:
            pytest.skip("Project creation failed, skipping analyze test")
        
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/analyze",
            json={
                "prompt": "I need to deliver a 10-minute keynote about AI innovation to a tech conference audience. Help me structure my delivery.",
                "target": "project",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=60  # LLM calls can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "analysis" in data, f"Expected 'analysis' in response, got: {data}"
        assert "analysis_id" in data, f"Expected 'analysis_id' in response, got: {data}"
        assert data.get("analysis_id").startswith("ana_"), f"Expected analysis_id to start with 'ana_', got: {data}"
        assert len(data.get("analysis", "")) > 50, f"Expected substantial analysis text, got: {data.get('analysis')[:100]}"
        
        print(f"✓ Analyze project: analysis_id={data.get('analysis_id')}, analysis_length={len(data.get('analysis', ''))}")
    
    def test_analyze_nonexistent_project_returns_404(self):
        """POST /api/ai-speech-studio/projects/{invalid_id}/analyze should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/aivs_nonexistent123/analyze",
            json={
                "prompt": "Test prompt",
                "target": "project",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_project_not_found", f"Expected error_code='ai_speech_project_not_found', got: {detail}"
        print(f"✓ Analyze nonexistent project returns 404: {detail}")


class TestAISpeechStudioHistory:
    """History endpoint tests"""
    
    def test_history_guest_flow_returns_200(self):
        """GET /api/ai-speech-studio/history should return history for guest"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/history",
            params={
                "fallback_user_id": TEST_GUEST_ID,
                "limit": 20,
                "offset": 0
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "history" in data, f"Expected 'history' in response, got: {data}"
        assert "total" in data, f"Expected 'total' in response, got: {data}"
        assert "plan" in data, f"Expected 'plan' in response, got: {data}"
        assert isinstance(data.get("history"), list), f"Expected 'history' to be a list, got: {type(data.get('history'))}"
        
        print(f"✓ History guest flow: total={data.get('total')}, items={len(data.get('history', []))}")
    
    def test_history_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/history without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/history")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ History without auth returns 401")


class TestAISpeechStudioFreePlanLimitEnforcement:
    """Free plan project monthly limit enforcement tests (3rd create should 429)"""
    
    def test_free_plan_project_limit_enforcement(self):
        """Free plan should enforce 2 projects/month limit - 3rd create should return 429"""
        # Use a unique guest ID for limit testing to avoid interference
        limit_guest_id = LIMIT_TEST_GUEST_ID
        
        # Create first project - should succeed
        response1 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Limit Test Project 1 - {uuid.uuid4().hex[:8]}",
                "brief": "First project for limit testing",
                "objective": "presentation",
                "fallback_user_id": limit_guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response1.status_code == 200, f"First project creation failed: {response1.status_code}: {response1.text}"
        print(f"✓ First project created successfully")
        
        # Create second project - should succeed
        response2 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Limit Test Project 2 - {uuid.uuid4().hex[:8]}",
                "brief": "Second project for limit testing",
                "objective": "presentation",
                "fallback_user_id": limit_guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response2.status_code == 200, f"Second project creation failed: {response2.status_code}: {response2.text}"
        print(f"✓ Second project created successfully")
        
        # Create third project - should fail with 429 (limit reached)
        response3 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Limit Test Project 3 - {uuid.uuid4().hex[:8]}",
                "brief": "Third project should be blocked",
                "objective": "presentation",
                "fallback_user_id": limit_guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response3.status_code == 429, f"Expected 429 for third project, got {response3.status_code}: {response3.text}"
        
        data = response3.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_project_limit_reached", f"Expected error_code='ai_speech_project_limit_reached', got: {detail}"
        assert detail.get("current_plan") == "free", f"Expected current_plan='free', got: {detail}"
        assert detail.get("required_plan") == "basic", f"Expected required_plan='basic', got: {detail}"
        assert detail.get("limit") == 2, f"Expected limit=2, got: {detail}"
        assert detail.get("current_usage") == 2, f"Expected current_usage=2, got: {detail}"
        
        print(f"✓ Free plan limit enforcement: 3rd project blocked with 429")
        print(f"  - error_code: {detail.get('error_code')}")
        print(f"  - current_plan: {detail.get('current_plan')}")
        print(f"  - required_plan: {detail.get('required_plan')}")
        print(f"  - limit: {detail.get('limit')}")
        print(f"  - current_usage: {detail.get('current_usage')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
