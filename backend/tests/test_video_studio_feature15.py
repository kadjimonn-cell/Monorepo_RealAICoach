"""
Feature 15: Video Creator Studio - Backend API Tests
Tests for /api/video-studio/* endpoints
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestVideoStudioHealth:
    """Health check endpoint tests"""
    
    def test_health_endpoint_returns_200(self):
        """Test /api/video-studio/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/video-studio/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature") == "Video Creator Studio"
        assert data.get("feature_id") == "ai-video"
        print("PASS: Health endpoint returns healthy status")


class TestVideoStudioAuth:
    """Authentication flow tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session for free user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # CSRF bypass for API calls
        })
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
        
        return session
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated session for admin user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # CSRF bypass for API calls
        })
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Admin auth failed: {response.status_code} - {response.text}")
        
        return session
    
    def test_login_free_user_success(self):
        """Test free user can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        
        data = response.json()
        assert "user_id" in data
        assert data.get("email") == FREE_USER_EMAIL
        assert data.get("subscription_plan") == "free"
        print(f"PASS: Free user login successful, user_id={data.get('user_id')}")


class TestVideoStudioBootstrap:
    """Bootstrap endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.status_code}")
        
        return session
    
    def test_bootstrap_requires_auth(self):
        """Test bootstrap endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/video-studio/bootstrap")
        # Should return 401 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: Bootstrap requires authentication")
    
    def test_bootstrap_returns_user_data(self, auth_session):
        """Test bootstrap returns proper user data structure"""
        response = auth_session.get(f"{BASE_URL}/api/video-studio/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success")
        assert "plan" in data
        assert "limits" in data
        assert "usage" in data
        assert "projects" in data
        assert "platform_presets" in data
        assert "templates" in data
        assert "features" in data
        
        # Verify plan is valid
        assert data["plan"] in ["free", "basic", "premium", "admin"]
        
        # Verify limits structure
        limits = data["limits"]
        assert "projects_per_month" in limits
        assert "scripts_per_day" in limits
        
        # Verify platform presets
        presets = data["platform_presets"]
        assert len(presets) >= 4  # youtube, tiktok, instagram, linkedin
        
        print(f"PASS: Bootstrap returns valid data, plan={data['plan']}, projects={len(data['projects'])}")


class TestVideoStudioProjects:
    """Project CRUD tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.status_code}")
        
        return session
    
    def test_create_project_success(self, auth_session):
        """Test creating a new video project"""
        test_title = f"TEST_Project_{uuid.uuid4().hex[:8]}"
        
        response = auth_session.post(f"{BASE_URL}/api/video-studio/projects/create", json={
            "title": test_title,
            "description": "Test project for Feature 15 validation",
            "platform": "youtube",
            "video_type": "tutorial",
            "target_duration_seconds": 600
        })
        
        assert response.status_code == 200, f"Create failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("success")
        assert "project" in data
        
        project = data["project"]
        assert project.get("title") == test_title
        assert project.get("platform") == "youtube"
        assert project.get("video_type") == "tutorial"
        assert project.get("status") == "draft"
        assert "project_id" in project
        
        print(f"PASS: Project created successfully, project_id={project['project_id']}")
        
        # Cleanup - delete the test project
        project_id = project["project_id"]
        cleanup_response = auth_session.delete(f"{BASE_URL}/api/video-studio/projects/{project_id}")
        assert cleanup_response.status_code == 200, f"Cleanup failed: {cleanup_response.status_code}"
        print("PASS: Test project cleaned up")
    
    def test_create_project_validation(self, auth_session):
        """Test project creation validation - title required"""
        response = auth_session.post(f"{BASE_URL}/api/video-studio/projects/create", json={
            "title": "",  # Empty title should fail
            "platform": "youtube"
        })
        
        # Should return 422 for validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("PASS: Empty title validation works")
    
    def test_list_projects(self, auth_session):
        """Test listing user's projects"""
        response = auth_session.get(f"{BASE_URL}/api/video-studio/projects")
        assert response.status_code == 200, f"List failed: {response.status_code}"
        
        data = response.json()
        assert data.get("success")
        assert "projects" in data
        assert "total" in data
        assert isinstance(data["projects"], list)
        
        print(f"PASS: Projects listed, total={data['total']}")
    
    def test_get_project_not_found(self, auth_session):
        """Test getting non-existent project returns 404"""
        response = auth_session.get(f"{BASE_URL}/api/video-studio/projects/nonexistent_id_12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Non-existent project returns 404")
    
    def test_project_crud_flow(self, auth_session):
        """Test full CRUD flow: Create -> Read -> Update -> Delete"""
        # CREATE
        test_title = f"TEST_CRUD_{uuid.uuid4().hex[:8]}"
        create_response = auth_session.post(f"{BASE_URL}/api/video-studio/projects/create", json={
            "title": test_title,
            "description": "CRUD test project",
            "platform": "tiktok",
            "video_type": "vlog"
        })
        assert create_response.status_code == 200
        project_id = create_response.json()["project"]["project_id"]
        print(f"CREATE: project_id={project_id}")
        
        # READ
        read_response = auth_session.get(f"{BASE_URL}/api/video-studio/projects/{project_id}")
        assert read_response.status_code == 200
        read_data = read_response.json()
        assert read_data["project"]["title"] == test_title
        print(f"READ: title={read_data['project']['title']}")
        
        # UPDATE
        update_response = auth_session.patch(f"{BASE_URL}/api/video-studio/projects/{project_id}", json={
            "title": f"{test_title}_UPDATED",
            "status": "script_ready"
        })
        assert update_response.status_code == 200
        print("UPDATE: success")
        
        # Verify update persisted
        verify_response = auth_session.get(f"{BASE_URL}/api/video-studio/projects/{project_id}")
        assert verify_response.status_code == 200
        assert verify_response.json()["project"]["title"] == f"{test_title}_UPDATED"
        assert verify_response.json()["project"]["status"] == "script_ready"
        print("VERIFY UPDATE: persisted correctly")
        
        # DELETE
        delete_response = auth_session.delete(f"{BASE_URL}/api/video-studio/projects/{project_id}")
        assert delete_response.status_code == 200
        print("DELETE: success")
        
        # Verify deletion
        verify_delete = auth_session.get(f"{BASE_URL}/api/video-studio/projects/{project_id}")
        assert verify_delete.status_code == 404
        print("VERIFY DELETE: project no longer exists")
        
        print("PASS: Full CRUD flow completed successfully")


class TestVideoStudioScriptGeneration:
    """Script generation tests (AI-powered)"""
    
    @pytest.fixture
    def auth_session_with_project(self):
        """Get authenticated session with a test project"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.status_code}")
        
        # Create test project
        project_response = session.post(f"{BASE_URL}/api/video-studio/projects/create", json={
            "title": f"TEST_Script_{uuid.uuid4().hex[:8]}",
            "platform": "youtube",
            "video_type": "tutorial"
        })
        
        if project_response.status_code != 200:
            pytest.skip(f"Project creation failed: {project_response.status_code}")
        
        project_id = project_response.json()["project"]["project_id"]
        
        yield session, project_id
        
        # Cleanup
        session.delete(f"{BASE_URL}/api/video-studio/projects/{project_id}")
    
    def test_script_generation_requires_project(self, auth_session_with_project):
        """Test script generation requires valid project"""
        session, _ = auth_session_with_project
        
        response = session.post(f"{BASE_URL}/api/video-studio/scripts/generate", json={
            "project_id": "nonexistent_project_id",
            "prompt": "Create a tutorial about Python basics"
        })
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Script generation requires valid project")


class TestVideoStudioThumbnails:
    """Thumbnail generation tests"""
    
    @pytest.fixture
    def auth_session_with_project(self):
        """Get authenticated session with a test project"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Auth failed: {response.status_code}")
        
        # Create test project
        project_response = session.post(f"{BASE_URL}/api/video-studio/projects/create", json={
            "title": f"TEST_Thumb_{uuid.uuid4().hex[:8]}",
            "platform": "youtube",
            "video_type": "tutorial"
        })
        
        if project_response.status_code != 200:
            pytest.skip(f"Project creation failed: {project_response.status_code}")
        
        project_id = project_response.json()["project"]["project_id"]
        
        yield session, project_id
        
        # Cleanup
        session.delete(f"{BASE_URL}/api/video-studio/projects/{project_id}")
    
    def test_thumbnail_generation_requires_project(self, auth_session_with_project):
        """Test thumbnail generation requires valid project"""
        session, _ = auth_session_with_project
        
        response = session.post(f"{BASE_URL}/api/video-studio/thumbnails/generate", json={
            "project_id": "nonexistent_project_id",
            "video_title": "Test Video Title"
        })
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Thumbnail generation requires valid project")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
