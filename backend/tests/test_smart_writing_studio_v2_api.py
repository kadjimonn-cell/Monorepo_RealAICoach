"""Smart Writing Studio v2 API Tests

Tests for the enterprise writing workspace APIs:
- Bootstrap endpoint (workspace initialization)
- Document CRUD operations
- Version history and restore
- Brand profile management
- Run task execution (AI generation)
"""

import os
import pytest
import requests
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

# Guest user ID for testing (follows the required pattern)
TEST_GUEST_ID = f"user_test_{uuid.uuid4().hex[:16]}"

# Headers to bypass CSRF for API calls
API_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json"
}


class TestWritingStudioBootstrap:
    """Bootstrap endpoint tests - workspace initialization"""
    
    def test_bootstrap_returns_200_with_guest_id(self):
        """Bootstrap should return 200 with valid guest fallback_user_id"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/bootstrap",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "owner_id" in data
        assert "documents" in data
        assert "brand_profile" in data
        assert "presets" in data
        assert "stats" in data
        
        # Verify presets structure
        presets = data["presets"]
        assert "tasks" in presets
        assert "tones" in presets
        assert "reading_levels" in presets
        
        # Verify expected tasks are present
        expected_tasks = ["draft", "rewrite", "shorten", "expand", "tone_shift", "grammar_polish", "seo_optimize"]
        for task in expected_tasks:
            assert task in presets["tasks"], f"Missing task: {task}"
    
    def test_bootstrap_requires_auth_or_fallback_id(self):
        """Bootstrap should return 401 without auth or fallback_user_id"""
        response = requests.get(f"{BASE_URL}/api/writing-studio/bootstrap")
        assert response.status_code == 401
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "writing_studio_auth_required"
    
    def test_bootstrap_rejects_invalid_guest_id_format(self):
        """Bootstrap should reject invalid fallback_user_id format"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/bootstrap",
            params={"fallback_user_id": "invalid-format"}
        )
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "writing_studio_invalid_guest_id"


class TestWritingStudioDocumentCRUD:
    """Document CRUD operations tests"""
    
    @pytest.fixture
    def guest_id(self):
        """Generate a unique guest ID for each test"""
        return f"user_crud_{uuid.uuid4().hex[:16]}"
    
    def test_create_document_success(self, guest_id):
        """Create document should return 200 with valid payload"""
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Test Document",
                "content": "This is test content for the document.",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "document" in data
        doc = data["document"]
        
        # Verify document structure
        assert "doc_id" in doc
        assert doc["doc_id"].startswith("ws_")
        assert doc["title"] == "Test Document"
        assert doc["current_content"] == "This is test content for the document."
        assert "created_at" in doc
        assert "updated_at" in doc
        assert "versions" in doc
        assert len(doc["versions"]) == 1  # Initial version
        assert "last_quality_scores" in doc
    
    def test_create_document_requires_title(self, guest_id):
        """Create document should require a title"""
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "",  # Empty title
                "content": "Some content",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 422  # Validation error
    
    def test_get_document_success(self, guest_id):
        """Get document should return the created document"""
        # First create a document
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Get Test Document",
                "content": "Content for get test",
                "fallback_user_id": guest_id
            }
        )
        assert create_response.status_code == 200
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Now get the document
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            params={"fallback_user_id": guest_id}
        )
        assert get_response.status_code == 200
        
        data = get_response.json()
        assert "document" in data
        assert data["document"]["doc_id"] == doc_id
        assert data["document"]["title"] == "Get Test Document"
    
    def test_get_document_not_found(self, guest_id):
        """Get document should return 404 for non-existent document"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/ws_nonexistent123",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 404
        
        data = response.json()
        assert data["detail"]["error_code"] == "writing_studio_doc_not_found"
    
    def test_update_document_success(self, guest_id):
        """Update document should modify title and content"""
        # Create document
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Original Title",
                "content": "Original content",
                "fallback_user_id": guest_id
            }
        )
        assert create_response.status_code == 200
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Update document
        update_response = requests.patch(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            headers=API_HEADERS,
            json={
                "title": "Updated Title",
                "content": "Updated content",
                "fallback_user_id": guest_id
            }
        )
        assert update_response.status_code == 200
        
        updated_doc = update_response.json()["document"]
        assert updated_doc["title"] == "Updated Title"
        assert updated_doc["current_content"] == "Updated content"
        
        # Verify persistence with GET
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            params={"fallback_user_id": guest_id}
        )
        assert get_response.status_code == 200
        assert get_response.json()["document"]["title"] == "Updated Title"


class TestWritingStudioVersions:
    """Version history and restore tests"""
    
    @pytest.fixture
    def guest_id(self):
        return f"user_ver_{uuid.uuid4().hex[:16]}"
    
    def test_get_versions_success(self, guest_id):
        """Get versions should return version history"""
        # Create document
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Version Test Doc",
                "content": "Initial content",
                "fallback_user_id": guest_id
            }
        )
        assert create_response.status_code == 200
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Get versions
        versions_response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}/versions",
            params={"fallback_user_id": guest_id}
        )
        assert versions_response.status_code == 200
        
        data = versions_response.json()
        assert "doc_id" in data
        assert "versions" in data
        assert len(data["versions"]) >= 1  # At least initial version
    
    def test_restore_version_success(self, guest_id):
        """Restore version should revert document to previous state"""
        # Create document
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Restore Test Doc",
                "content": "Original content to restore",
                "fallback_user_id": guest_id
            }
        )
        assert create_response.status_code == 200
        doc = create_response.json()["document"]
        doc_id = doc["doc_id"]
        original_version_id = doc["versions"][0]["version_id"]
        
        # Update document to create new state
        requests.patch(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            headers=API_HEADERS,
            json={
                "content": "Modified content",
                "fallback_user_id": guest_id
            }
        )
        
        # Restore to original version
        restore_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}/restore/{original_version_id}",
            headers=API_HEADERS,
            params={"fallback_user_id": guest_id}
        )
        assert restore_response.status_code == 200
        
        restored_doc = restore_response.json()["document"]
        assert restored_doc["current_content"] == "Original content to restore"
        # Should have a new version entry for the restore
        assert len(restored_doc["versions"]) >= 2


class TestWritingStudioBrandProfile:
    """Brand profile management tests"""
    
    @pytest.fixture
    def guest_id(self):
        return f"user_brand_{uuid.uuid4().hex[:16]}"
    
    def test_get_brand_profile_default(self, guest_id):
        """Get brand profile should return default empty profile for new user"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/brand-profile",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "brand_profile" in data
        profile = data["brand_profile"]
        assert "brand_name" in profile
        assert "voice_summary" in profile
        assert "preferred_phrases" in profile
        assert "do_not_use" in profile
    
    def test_update_brand_profile_success(self, guest_id):
        """Update brand profile should persist changes"""
        response = requests.put(
            f"{BASE_URL}/api/writing-studio/brand-profile",
            headers=API_HEADERS,
            json={
                "brand_name": "Test Brand",
                "voice_summary": "Professional and friendly tone",
                "preferred_phrases": ["innovative", "customer-first"],
                "do_not_use": ["cheap", "basic"],
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200
        
        profile = response.json()["brand_profile"]
        assert profile["brand_name"] == "Test Brand"
        assert profile["voice_summary"] == "Professional and friendly tone"
        assert "innovative" in profile["preferred_phrases"]
        assert "cheap" in profile["do_not_use"]
        
        # Verify persistence
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/brand-profile",
            params={"fallback_user_id": guest_id}
        )
        assert get_response.status_code == 200
        assert get_response.json()["brand_profile"]["brand_name"] == "Test Brand"


class TestWritingStudioRuns:
    """Run task execution tests"""
    
    @pytest.fixture
    def guest_id(self):
        return f"user_run_{uuid.uuid4().hex[:16]}"
    
    @pytest.fixture
    def document_id(self, guest_id):
        """Create a document for run tests"""
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "Run Test Document",
                "content": "This is content for testing AI generation tasks. It should be rewritten, expanded, or polished.",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200
        return response.json()["document"]["doc_id"]
    
    def test_run_task_rewrite_success(self, guest_id, document_id):
        """Run rewrite task should return generated output"""
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/runs",
            headers=API_HEADERS,
            json={
                "document_id": document_id,
                "task": "rewrite",
                "instructions": "Rewrite this content to be more professional",
                "tone": "professional",
                "audience": "business executives",
                "reading_level": "professional",
                "fallback_user_id": guest_id,
                "idempotency_key": f"test_rewrite_{uuid.uuid4().hex[:8]}"
            },
            timeout=60  # AI generation can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "run" in data
        assert "document" in data
        
        run = data["run"]
        assert run["status"] == "completed"
        assert "output" in run
        assert "quality_scores" in run
        
        # Verify quality scores structure
        quality = run["quality_scores"]
        assert "overall" in quality
        assert "readability" in quality
        assert "clarity" in quality
    
    def test_run_task_requires_document(self, guest_id):
        """Run task should return 404 for non-existent document"""
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/runs",
            headers=API_HEADERS,
            json={
                "document_id": "ws_nonexistent123",
                "task": "rewrite",
                "instructions": "Test",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "writing_studio_doc_not_found"
    
    def test_get_run_success(self, guest_id, document_id):
        """Get run should return run details"""
        # Create a run first
        run_response = requests.post(
            f"{BASE_URL}/api/writing-studio/runs",
            headers=API_HEADERS,
            json={
                "document_id": document_id,
                "task": "shorten",
                "instructions": "Make it shorter",
                "fallback_user_id": guest_id
            },
            timeout=60
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["run"]["run_id"]
        
        # Get the run
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/runs/{run_id}",
            params={"fallback_user_id": guest_id}
        )
        assert get_response.status_code == 200
        
        data = get_response.json()
        assert "run" in data
        assert data["run"]["run_id"] == run_id


class TestWritingStudioOwnerIsolation:
    """Owner isolation tests - ensure users can only access their own data"""
    
    def test_document_owner_isolation(self):
        """Documents should be isolated by owner"""
        guest_id_1 = f"user_iso1_{uuid.uuid4().hex[:16]}"
        guest_id_2 = f"user_iso2_{uuid.uuid4().hex[:16]}"
        
        # Create document as user 1
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            headers=API_HEADERS,
            json={
                "title": "User 1 Private Doc",
                "content": "Private content",
                "fallback_user_id": guest_id_1
            }
        )
        assert create_response.status_code == 200
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Try to access as user 2 - should get 404
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            params={"fallback_user_id": guest_id_2}
        )
        assert get_response.status_code == 404
        
        # User 1 should still be able to access
        get_response_1 = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            params={"fallback_user_id": guest_id_1}
        )
        assert get_response_1.status_code == 200


class TestWritingStudioPublicAPIContract:
    """Verify writing-studio is in public API contract"""
    
    def test_writing_studio_in_public_prefixes(self):
        """Writing studio should be accessible without auth (with fallback_user_id)"""
        from pathlib import Path
        
        contract_path = Path("/app/backend/utils/public_api_contract.py")
        assert contract_path.exists(), "public_api_contract.py not found"
        
        content = contract_path.read_text()
        assert '"/api/writing-studio/"' in content, "writing-studio not in PUBLIC_API_PREFIXES"


class TestWritingStudioContractFiles:
    """Verify CI contract files exist and are valid"""
    
    def test_backend_contract_test_exists(self):
        """Backend contract test file should exist"""
        from pathlib import Path
        
        contract_path = Path("/app/backend/tests/test_smart_writing_studio_rebuild_contract.py")
        assert contract_path.exists(), "Backend contract test file not found"
        
        content = contract_path.read_text()
        assert "test_writing_studio_route_exists_with_core_endpoints" in content
        assert "test_writing_studio_route_included_in_server_registry" in content
    
    def test_frontend_e2e_spec_exists(self):
        """Frontend E2E spec file should exist"""
        from pathlib import Path
        
        spec_path = Path("/app/frontend/e2e/ai-writer.spec.ts")
        assert spec_path.exists(), "Frontend E2E spec file not found"
        
        content = spec_path.read_text()
        assert "Smart Writing Studio v2" in content
        assert "smart-writing-studio-v2-root" in content
    
    def test_ci_workflow_includes_ai_writer_e2e(self):
        """CI workflow should include ai-writer.spec.ts"""
        from pathlib import Path
        
        workflow_path = Path("/app/.github/workflows/ci-quality-gate.yml")
        assert workflow_path.exists(), "CI workflow file not found"
        
        content = workflow_path.read_text()
        assert "ai-writer.spec.ts" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
