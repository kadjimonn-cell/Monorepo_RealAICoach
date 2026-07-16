"""
AI Photo Studio (Feature 16) Backend API Tests
Tests bootstrap, project CRUD, generate, analyze, history, and brand preset flows.
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"

# Guest user ID for testing (matches GUEST_ID_RE pattern: user_[a-zA-Z0-9_-]{12,80})
TEST_GUEST_ID = f"user_test_{uuid.uuid4().hex[:16]}"

# Headers to bypass CSRF for state-changing requests
CSRF_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json"
}


class TestAIPhotoStudioHealth:
    """Health check endpoints"""

    def test_health_endpoint(self):
        """Test /api/ai-photo-studio/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/ai-photo-studio/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature") == "Image & Design Studio"
        assert data.get("feature_id") == "ai-photo"
        print(f"✓ Health endpoint OK: {data}")


class TestAIPhotoStudioBootstrap:
    """Bootstrap API tests with guest fallback_user_id"""

    def test_bootstrap_with_guest_id(self):
        """Test GET /api/ai-photo-studio/bootstrap with valid guest fallback_user_id"""
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/bootstrap",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") is True
        assert data.get("feature_id") == "ai-photo"
        assert data.get("plan") in ["free", "basic", "premium", "admin"]
        assert "limits" in data
        assert "usage" in data
        assert "projects" in data
        assert "recent_generations" in data
        assert "style_packs" in data
        assert "quality_packs" in data
        assert "features" in data
        
        # Verify limits structure
        limits = data.get("limits", {})
        assert "projects_per_month" in limits
        assert "generations_per_day" in limits
        assert "analyses_per_day" in limits
        
        # Verify style packs
        style_packs = data.get("style_packs", [])
        assert len(style_packs) >= 4
        style_ids = [s["id"] for s in style_packs]
        assert "cinematic" in style_ids
        assert "studio" in style_ids
        
        print(f"✓ Bootstrap OK: plan={data.get('plan')}, limits={limits}")

    def test_bootstrap_without_auth_or_guest_id_fails(self):
        """Test bootstrap without auth or fallback_user_id returns 401"""
        response = requests.get(f"{BASE_URL}/api/ai-photo-studio/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_photo_auth_required"
        print("✓ Bootstrap without auth correctly returns 401")

    def test_bootstrap_with_invalid_guest_id_fails(self):
        """Test bootstrap with invalid fallback_user_id format returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/bootstrap",
            params={"fallback_user_id": "invalid_format"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_photo_invalid_guest_id"
        print("✓ Bootstrap with invalid guest ID correctly returns 400")


class TestAIPhotoStudioProjects:
    """Project CRUD tests"""

    def test_create_project(self):
        """Test POST /api/ai-photo-studio/projects/create"""
        payload = {
            "title": f"TEST_Project_{uuid.uuid4().hex[:8]}",
            "brief": "Test project for automated testing",
            "style_pack": "cinematic",
            "quality": "ultra",
            "fallback_user_id": TEST_GUEST_ID
        }
        response = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/create",
            json=payload,
            headers=CSRF_HEADERS
        )
        assert response.status_code == 200, f"Create project failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        project = data.get("project", {})
        assert project.get("project_id", "").startswith("aip_")
        assert project.get("title") == payload["title"]
        assert project.get("style_pack") == "cinematic"
        assert project.get("quality") == "ultra"
        
        print(f"✓ Create project OK: project_id={project.get('project_id')}")
        return project.get("project_id")

    def test_list_projects(self):
        """Test GET /api/ai-photo-studio/projects"""
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/projects",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"List projects failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        assert "projects" in data
        assert "total" in data
        assert isinstance(data.get("projects"), list)
        
        print(f"✓ List projects OK: total={data.get('total')}")

    def test_get_project_detail(self):
        """Test GET /api/ai-photo-studio/projects/{project_id}"""
        # First create a project
        project_id = self.test_create_project()
        
        # Then get its details
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/projects/{project_id}",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Get project failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        assert data.get("project", {}).get("project_id") == project_id
        assert "generations" in data
        
        print(f"✓ Get project detail OK: project_id={project_id}")

    def test_toggle_favorite(self):
        """Test POST /api/ai-photo-studio/projects/{project_id}/favorite"""
        # First create a project
        project_id = self.test_create_project()
        
        # Toggle favorite to true
        response = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/{project_id}/favorite",
            json={"favorite": True, "fallback_user_id": TEST_GUEST_ID},
            headers=CSRF_HEADERS
        )
        assert response.status_code == 200, f"Toggle favorite failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        assert data.get("project", {}).get("favorite") is True
        
        print(f"✓ Toggle favorite OK: project_id={project_id}")


class TestAIPhotoStudioHistory:
    """History API tests"""

    def test_get_history(self):
        """Test GET /api/ai-photo-studio/history"""
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/history",
            params={"fallback_user_id": TEST_GUEST_ID, "limit": 20}
        )
        assert response.status_code == 200, f"Get history failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        assert "history" in data
        assert "total" in data
        assert isinstance(data.get("history"), list)
        
        print(f"✓ Get history OK: total={data.get('total')}")


class TestAIPhotoStudioBrandPreset:
    """Brand preset save/get tests"""

    def test_save_brand_preset(self):
        """Test PUT /api/ai-photo-studio/brand-preset"""
        payload = {
            "name": f"TEST_Brand_{uuid.uuid4().hex[:6]}",
            "primary_goal": "Increase conversion rates",
            "audience": "Enterprise B2B decision makers",
            "visual_constraints": "No red colors, minimal text overlay",
            "fallback_user_id": TEST_GUEST_ID
        }
        response = requests.put(
            f"{BASE_URL}/api/ai-photo-studio/brand-preset",
            json=payload,
            headers=CSRF_HEADERS
        )
        assert response.status_code == 200, f"Save brand preset failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        preset = data.get("brand_preset", {})
        assert preset.get("name") == payload["name"]
        assert preset.get("primary_goal") == payload["primary_goal"]
        
        print(f"✓ Save brand preset OK: name={preset.get('name')}")

    def test_get_brand_preset(self):
        """Test GET /api/ai-photo-studio/brand-preset"""
        # First save a preset
        self.test_save_brand_preset()
        
        # Then get it
        response = requests.get(
            f"{BASE_URL}/api/ai-photo-studio/brand-preset",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Get brand preset failed: {response.text}"
        data = response.json()
        
        assert data.get("success") is True
        # brand_preset can be null if none saved
        print(f"✓ Get brand preset OK: preset={data.get('brand_preset')}")


class TestAIPhotoStudioGenerate:
    """Image generation tests (may be slow due to AI processing)"""

    def test_generate_requires_project(self):
        """Test generate endpoint requires valid project"""
        response = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/nonexistent_project/generate",
            json={
                "prompt": "Test prompt",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers=CSRF_HEADERS
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Generate with invalid project correctly returns 404")

    def test_generate_validates_prompt_length(self):
        """Test generate validates prompt length based on plan limits"""
        # Create a project first
        create_resp = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/create",
            json={
                "title": f"TEST_GenProject_{uuid.uuid4().hex[:8]}",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers=CSRF_HEADERS
        )
        assert create_resp.status_code == 200, f"Create project failed: {create_resp.text}"
        project_id = create_resp.json().get("project", {}).get("project_id")
        
        # Try with very long prompt (free tier limit is 650 chars)
        long_prompt = "A" * 700
        response = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/{project_id}/generate",
            json={
                "prompt": long_prompt,
                "fallback_user_id": TEST_GUEST_ID
            },
            headers=CSRF_HEADERS
        )
        # Should return 422 for prompt too long
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_photo_prompt_too_long"
        print("✓ Generate validates prompt length correctly")


class TestAIPhotoStudioAnalyze:
    """Analysis endpoint tests"""

    def test_analyze_requires_project(self):
        """Test analyze endpoint requires valid project"""
        response = requests.post(
            f"{BASE_URL}/api/ai-photo-studio/projects/nonexistent_project/analyze",
            json={
                "prompt": "Analyze this",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers=CSRF_HEADERS
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ Analyze with invalid project correctly returns 404")


class TestAIPhotoStudioFileEndpoint:
    """File serving endpoint tests"""

    def test_file_not_found(self):
        """Test GET /api/ai-photo-studio/file/{image_id} returns 404 for invalid ID"""
        response = requests.get(f"{BASE_URL}/api/ai-photo-studio/file/nonexistent_image_id")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ File endpoint returns 404 for invalid image ID")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
