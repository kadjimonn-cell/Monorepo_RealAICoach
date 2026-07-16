"""
Feature 15: Video Creator Studio - Guest Mode Tests
Tests for /api/video-studio/* endpoints with fallback_user_id (guest mode)

Main fix tested: bootstrap endpoint now accepts fallback_user_id and returns 200 for valid user_* IDs
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Guest fallback ID from test_credentials.md
GUEST_FALLBACK_ID = "user_testfeature15abc12345"

# Common headers for API requests (CSRF bypass)
API_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestVideoStudioGuestBootstrap:
    """Bootstrap endpoint tests with fallback_user_id (guest mode)"""
    
    def test_bootstrap_with_valid_fallback_user_id_returns_200(self):
        """Test bootstrap accepts valid fallback_user_id and returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/video-studio/bootstrap",
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success")
        assert "plan" in data
        assert "limits" in data
        assert "projects" in data
        assert "platform_presets" in data
        assert "templates" in data
        assert "features" in data
        
        print(f"PASS: Bootstrap with fallback_user_id returns 200, plan={data['plan']}")
    
    def test_bootstrap_without_auth_or_fallback_returns_401(self):
        """Test bootstrap returns 401 when no auth and no fallback_user_id"""
        response = requests.get(f"{BASE_URL}/api/video-studio/bootstrap")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "video_studio_auth_required"
        
        print("PASS: Bootstrap without auth/fallback returns 401 with video_studio_auth_required")
    
    def test_bootstrap_with_invalid_fallback_user_id_returns_400(self):
        """Test bootstrap returns 400 for invalid fallback_user_id format"""
        # Test with invalid format (doesn't match user_[a-zA-Z0-9_-]{12,80})
        invalid_ids = [
            "invalid_id",  # doesn't start with user_
            "user_short",  # too short (less than 12 chars after user_)
            "user_",  # empty after prefix
            "user_abc",  # too short
            "user_!@#$%^&*()",  # invalid characters
        ]
        
        for invalid_id in invalid_ids:
            response = requests.get(
                f"{BASE_URL}/api/video-studio/bootstrap",
                params={"fallback_user_id": invalid_id}
            )
            
            assert response.status_code == 400, f"Expected 400 for '{invalid_id}', got {response.status_code}"
            
            data = response.json()
            detail = data.get("detail", {})
            assert detail.get("error_code") == "video_studio_invalid_guest_id", \
                f"Expected video_studio_invalid_guest_id for '{invalid_id}', got {detail}"
        
        print("PASS: Bootstrap with invalid fallback_user_id returns 400 with video_studio_invalid_guest_id")


class TestVideoStudioGuestProjectCreate:
    """Project creation tests with fallback_user_id (guest mode)"""
    
    def test_create_project_with_fallback_user_id_success(self):
        """Test creating a project with fallback_user_id works"""
        test_title = f"TEST_GuestProject_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/video-studio/projects/create",
            headers=API_HEADERS,
            json={
                "title": test_title,
                "description": "Guest mode test project",
                "platform": "youtube",
                "video_type": "tutorial",
                "target_duration_seconds": 600,
                "fallback_user_id": GUEST_FALLBACK_ID
            }
        )
        
        assert response.status_code == 200, f"Create failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("success")
        assert "project" in data
        
        project = data["project"]
        assert project.get("title") == test_title
        assert project.get("platform") == "youtube"
        assert "project_id" in project
        
        project_id = project["project_id"]
        print(f"PASS: Guest project created, project_id={project_id}")
        
        # Cleanup - delete the test project
        cleanup_response = requests.delete(
            f"{BASE_URL}/api/video-studio/projects/{project_id}",
            headers=API_HEADERS,
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        assert cleanup_response.status_code == 200, f"Cleanup failed: {cleanup_response.status_code}"
        print("PASS: Guest project cleaned up")
    
    def test_create_project_without_auth_or_fallback_returns_401(self):
        """Test creating project without auth/fallback returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/video-studio/projects/create",
            headers=API_HEADERS,
            json={
                "title": "Test Project",
                "platform": "youtube",
                "video_type": "tutorial"
            }
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Create project without auth/fallback returns 401")


class TestVideoStudioGuestScriptGeneration:
    """Script generation tests with fallback_user_id (guest mode)"""
    
    @pytest.fixture
    def guest_project(self):
        """Create a guest project for testing"""
        test_title = f"TEST_GuestScript_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/video-studio/projects/create",
            headers=API_HEADERS,
            json={
                "title": test_title,
                "platform": "youtube",
                "video_type": "tutorial",
                "fallback_user_id": GUEST_FALLBACK_ID
            }
        )
        
        if response.status_code != 200:
            pytest.skip(f"Guest project creation failed: {response.status_code}")
        
        project_id = response.json()["project"]["project_id"]
        
        yield project_id
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/video-studio/projects/{project_id}",
            headers=API_HEADERS,
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
    
    def test_script_generation_with_fallback_user_id(self, guest_project):
        """Test script generation works with fallback_user_id for guest-owned project"""
        project_id = guest_project
        
        response = requests.post(
            f"{BASE_URL}/api/video-studio/scripts/generate",
            headers=API_HEADERS,
            json={
                "project_id": project_id,
                "prompt": "Create a short tutorial about Python basics for beginners",
                "tone": "professional",
                "include_hook": True,
                "include_cta": True,
                "fallback_user_id": GUEST_FALLBACK_ID
            },
            timeout=60  # AI generation can take time
        )
        
        assert response.status_code == 200, f"Script generation failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("success")
        assert "script" in data
        
        script = data["script"]
        assert "content" in script
        assert "word_count" in script
        assert script["word_count"] > 0
        
        print(f"PASS: Script generated for guest project, word_count={script['word_count']}")


class TestVideoStudioGuestThumbnailGeneration:
    """Thumbnail generation tests with fallback_user_id (guest mode)"""
    
    @pytest.fixture
    def guest_project(self):
        """Create a guest project for testing"""
        test_title = f"TEST_GuestThumb_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/video-studio/projects/create",
            headers=API_HEADERS,
            json={
                "title": test_title,
                "platform": "youtube",
                "video_type": "tutorial",
                "fallback_user_id": GUEST_FALLBACK_ID
            }
        )
        
        if response.status_code != 200:
            pytest.skip(f"Guest project creation failed: {response.status_code}")
        
        project_id = response.json()["project"]["project_id"]
        
        yield project_id
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/video-studio/projects/{project_id}",
            headers=API_HEADERS,
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
    
    def test_thumbnail_generation_with_fallback_user_id(self, guest_project):
        """Test thumbnail generation works with fallback_user_id for guest-owned project"""
        project_id = guest_project
        
        response = requests.post(
            f"{BASE_URL}/api/video-studio/thumbnails/generate",
            headers=API_HEADERS,
            json={
                "project_id": project_id,
                "video_title": "Python Tutorial for Beginners",
                "concept_count": 2,
                "style": "bold",
                "fallback_user_id": GUEST_FALLBACK_ID
            },
            timeout=60  # AI generation can take time
        )
        
        assert response.status_code == 200, f"Thumbnail generation failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("success")
        assert "thumbnails" in data
        
        thumbnails = data["thumbnails"]
        assert "concepts" in thumbnails
        assert len(thumbnails["concepts"]) >= 1
        
        print(f"PASS: Thumbnails generated for guest project, concepts={len(thumbnails['concepts'])}")


class TestVideoStudioGuestProjectDelete:
    """Project deletion tests with fallback_user_id (guest mode)"""
    
    def test_delete_project_with_fallback_user_id(self):
        """Test deleting a project with fallback_user_id works"""
        # First create a project
        test_title = f"TEST_GuestDelete_{uuid.uuid4().hex[:8]}"
        
        create_response = requests.post(
            f"{BASE_URL}/api/video-studio/projects/create",
            headers=API_HEADERS,
            json={
                "title": test_title,
                "platform": "youtube",
                "video_type": "tutorial",
                "fallback_user_id": GUEST_FALLBACK_ID
            }
        )
        
        assert create_response.status_code == 200, f"Create failed: {create_response.status_code}"
        project_id = create_response.json()["project"]["project_id"]
        print(f"Created project for deletion test: {project_id}")
        
        # Now delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/video-studio/projects/{project_id}",
            headers=API_HEADERS,
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.status_code}"
        
        data = delete_response.json()
        assert data.get("success")
        
        print("PASS: Guest project deleted successfully")
        
        # Verify deletion
        get_response = requests.get(
            f"{BASE_URL}/api/video-studio/projects/{project_id}",
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        
        assert get_response.status_code == 404, f"Expected 404 after deletion, got {get_response.status_code}"
        print("PASS: Deleted project returns 404")


class TestVideoStudioGuestProjectList:
    """Project listing tests with fallback_user_id (guest mode)"""
    
    def test_list_projects_with_fallback_user_id(self):
        """Test listing projects with fallback_user_id works"""
        response = requests.get(
            f"{BASE_URL}/api/video-studio/projects",
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        
        assert response.status_code == 200, f"List failed: {response.status_code}"
        
        data = response.json()
        assert data.get("success")
        assert "projects" in data
        assert "total" in data
        assert isinstance(data["projects"], list)
        
        print(f"PASS: Guest projects listed, total={data['total']}")


class TestVideoStudioPublicContract:
    """Verify /api/video-studio/ is in public API contract"""
    
    def test_video_studio_in_public_contract(self):
        """Test that /api/video-studio/ prefix is in public API contract"""
        # This test verifies the route is accessible without full auth
        # by checking that fallback_user_id works (which requires public contract)
        
        response = requests.get(
            f"{BASE_URL}/api/video-studio/bootstrap",
            params={"fallback_user_id": GUEST_FALLBACK_ID}
        )
        
        # If it returns 200, the route is in public contract and fallback works
        assert response.status_code == 200, \
            f"Expected 200 (route in public contract), got {response.status_code}"
        
        print("PASS: /api/video-studio/ is in public API contract")


class TestVideoStudioE2EParityFile:
    """Verify E2E parity file exists"""
    
    def test_e2e_parity_file_exists(self):
        """Test that /app/frontend/e2e/ai-video.spec.ts exists"""
        import os
        e2e_file = "/app/frontend/e2e/ai-video.spec.ts"
        
        assert os.path.exists(e2e_file), f"E2E parity file not found: {e2e_file}"
        
        # Verify it has content
        with open(e2e_file, 'r') as f:
            content = f.read()
        
        assert len(content) > 100, "E2E file appears to be empty or too short"
        assert "video-studio" in content.lower() or "ai-video" in content.lower(), \
            "E2E file doesn't appear to test video studio"
        
        print(f"PASS: E2E parity file exists and has valid content ({len(content)} chars)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
