"""
Feature 1: Smart Writing Studio - Runtime Fix Verification Tests
Tests for:
- GET /api/writing-studio/bootstrap (with fallback_user_id)
- POST /api/writing-studio/documents (create document)
- POST /api/writing-studio/runs (AI run - regression for prior 500 writing_studio_run_failed)
- POST /api/writing-studio/documents/{doc_id}/export (export - regression for prior 500 StreamingResponse NameError)
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Generate a unique guest user ID for testing
TEST_GUEST_USER_ID = f"user_test_{uuid.uuid4().hex[:16]}"

# Headers to bypass CSRF validation for API testing
API_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestWritingStudioBootstrap:
    """Test GET /api/writing-studio/bootstrap endpoint"""

    def test_bootstrap_returns_200_with_fallback_user_id(self):
        """Bootstrap endpoint should return 200 with presets and templates"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/bootstrap",
            params={"fallback_user_id": TEST_GUEST_USER_ID},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "owner_id" in data, "Response should contain owner_id"
        assert "tier" in data, "Response should contain tier"
        assert "documents" in data, "Response should contain documents"
        assert "templates" in data, "Response should contain templates"
        assert "presets" in data, "Response should contain presets"
        assert "stats" in data, "Response should contain stats"
        
        # Verify presets structure
        presets = data.get("presets", {})
        assert "tasks" in presets, "Presets should contain tasks"
        assert "tones" in presets, "Presets should contain tones"
        assert "reading_levels" in presets, "Presets should contain reading_levels"
        
        # Verify tasks list
        expected_tasks = ["draft", "rewrite", "shorten", "expand", "tone_shift", "grammar_polish", "seo_optimize"]
        assert presets.get("tasks") == expected_tasks, f"Tasks mismatch: {presets.get('tasks')}"
        
        print(f"✓ Bootstrap returned successfully with {len(data.get('templates', []))} templates")

    def test_bootstrap_without_auth_or_fallback_returns_401(self):
        """Bootstrap without auth or fallback_user_id should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/bootstrap",
            timeout=30
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Bootstrap correctly returns 401 without auth or fallback_user_id")


class TestWritingStudioDocuments:
    """Test document CRUD operations"""

    def test_create_document_returns_201_or_200(self):
        """POST /api/writing-studio/documents should create a document"""
        payload = {
            "title": f"Test Document {uuid.uuid4().hex[:8]}",
            "content": "This is test content for the Smart Writing Studio document.",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        # Accept both 200 and 201 as success
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "document" in data, "Response should contain document"
        
        doc = data["document"]
        assert "doc_id" in doc, "Document should have doc_id"
        assert "title" in doc, "Document should have title"
        assert "current_content" in doc, "Document should have current_content"
        assert "versions" in doc, "Document should have versions"
        
        print(f"✓ Document created successfully: {doc.get('doc_id')}")
        return doc.get("doc_id")

    def test_get_document_returns_200(self):
        """GET /api/writing-studio/documents/{doc_id} should return document"""
        # First create a document
        create_payload = {
            "title": f"Get Test Doc {uuid.uuid4().hex[:8]}",
            "content": "Content for get test",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=create_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Now get the document
        get_response = requests.get(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}",
            params={"fallback_user_id": TEST_GUEST_USER_ID},
            timeout=30
        )
        
        assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}: {get_response.text}"
        
        data = get_response.json()
        assert "document" in data, "Response should contain document"
        assert data["document"]["doc_id"] == doc_id, "Document ID should match"
        
        print(f"✓ Document retrieved successfully: {doc_id}")


class TestWritingStudioRuns:
    """Test AI run endpoint - regression for prior 500 writing_studio_run_failed"""

    def test_run_writing_task_no_500_error(self):
        """POST /api/writing-studio/runs should NOT return 500 (regression test)"""
        # First create a document
        create_payload = {
            "title": f"Run Test Doc {uuid.uuid4().hex[:8]}",
            "content": "This is content that needs to be rewritten for better clarity and engagement.",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=create_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Now run a writing task
        run_payload = {
            "document_id": doc_id,
            "task": "rewrite",
            "instructions": "Rewrite this content to be more engaging and professional.",
            "tone": "professional",
            "audience": "business professionals",
            "reading_level": "professional",
            "fallback_user_id": TEST_GUEST_USER_ID,
            "idempotency_key": f"test_run_{uuid.uuid4().hex[:12]}"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/runs",
            json=run_payload,
            headers=API_HEADERS,
            timeout=120  # AI calls can take time
        )
        
        # The key regression test: should NOT be 500
        assert response.status_code != 500, f"REGRESSION: Got 500 error: {response.text}"
        
        # Accept 200 (success) or 403 (tier limit) as valid responses
        if response.status_code == 200:
            data = response.json()
            assert "run" in data, "Response should contain run"
            assert "document" in data, "Response should contain document"
            print(f"✓ Run completed successfully for document {doc_id}")
        elif response.status_code == 403:
            # Tier limit reached is acceptable
            data = response.json()
            print(f"✓ Run returned 403 (tier limit): {data.get('detail', {}).get('message', 'limit reached')}")
        else:
            print(f"✓ Run returned {response.status_code} (not 500 - regression passed)")

    def test_run_with_draft_task(self):
        """Test draft task type"""
        create_payload = {
            "title": f"Draft Test {uuid.uuid4().hex[:8]}",
            "content": "Write a blog post about AI in healthcare",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=create_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        doc_id = create_response.json()["document"]["doc_id"]
        
        run_payload = {
            "document_id": doc_id,
            "task": "draft",
            "instructions": "Create a draft blog post about AI in healthcare",
            "tone": "professional",
            "audience": "healthcare professionals",
            "reading_level": "professional",
            "fallback_user_id": TEST_GUEST_USER_ID,
            "idempotency_key": f"test_draft_{uuid.uuid4().hex[:12]}"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/runs",
            json=run_payload,
            headers=API_HEADERS,
            timeout=120
        )
        
        # Should not be 500
        assert response.status_code != 500, f"REGRESSION: Got 500 error: {response.text}"
        print(f"✓ Draft task returned {response.status_code} (not 500)")


class TestWritingStudioExport:
    """Test export endpoint - regression for prior 500 StreamingResponse NameError"""

    def test_export_txt_no_500_error(self):
        """POST /api/writing-studio/documents/{doc_id}/export should NOT return 500 (regression test)"""
        # First create a document
        create_payload = {
            "title": f"Export Test Doc {uuid.uuid4().hex[:8]}",
            "content": "This is content to be exported as a text file.",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=create_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        doc_id = create_response.json()["document"]["doc_id"]
        
        # Now export the document as txt
        export_payload = {
            "export_format": "txt",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}/export",
            json=export_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        # The key regression test: should NOT be 500
        assert response.status_code != 500, f"REGRESSION: Got 500 error (StreamingResponse NameError?): {response.text}"
        
        # Accept 200 (success) or 403 (tier limit) as valid responses
        if response.status_code == 200:
            # Should return file content
            assert len(response.content) > 0, "Export should return content"
            content_disposition = response.headers.get("Content-Disposition", "")
            assert "attachment" in content_disposition, "Should have attachment header"
            print(f"✓ Export TXT successful for document {doc_id}")
        elif response.status_code == 403:
            print("✓ Export returned 403 (tier limit for format)")
        else:
            print(f"✓ Export returned {response.status_code} (not 500 - regression passed)")

    def test_export_csv_format(self):
        """Test CSV export format"""
        create_payload = {
            "title": f"CSV Export Test {uuid.uuid4().hex[:8]}",
            "content": "Content for CSV export test.",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents",
            json=create_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        doc_id = create_response.json()["document"]["doc_id"]
        
        export_payload = {
            "export_format": "csv",
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/api/writing-studio/documents/{doc_id}/export",
            json=export_payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        # Should not be 500
        assert response.status_code != 500, f"REGRESSION: Got 500 error: {response.text}"
        
        # CSV might require higher tier
        if response.status_code == 200:
            print(f"✓ Export CSV successful for document {doc_id}")
        elif response.status_code == 403:
            print("✓ Export CSV returned 403 (tier limit - expected for free tier)")
        else:
            print(f"✓ Export CSV returned {response.status_code}")


class TestWritingStudioTemplates:
    """Test templates endpoint"""

    def test_get_templates_returns_200(self):
        """GET /api/writing-studio/templates should return templates list"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/templates",
            params={"fallback_user_id": TEST_GUEST_USER_ID},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "templates" in data, "Response should contain templates"
        assert "tier" in data, "Response should contain tier"
        
        templates = data.get("templates", [])
        assert len(templates) > 0, "Should have at least some templates"
        
        # Verify template structure
        first_template = templates[0]
        assert "id" in first_template, "Template should have id"
        assert "name" in first_template, "Template should have name"
        assert "category" in first_template, "Template should have category"
        
        print(f"✓ Templates endpoint returned {len(templates)} templates")


class TestWritingStudioBrandProfile:
    """Test brand profile endpoint"""

    def test_get_brand_profile_returns_200(self):
        """GET /api/writing-studio/brand-profile should return brand profile"""
        response = requests.get(
            f"{BASE_URL}/api/writing-studio/brand-profile",
            params={"fallback_user_id": TEST_GUEST_USER_ID},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "brand_profile" in data, "Response should contain brand_profile"
        
        profile = data.get("brand_profile", {})
        assert "owner_id" in profile, "Profile should have owner_id"
        
        print("✓ Brand profile endpoint returned successfully")

    def test_update_brand_profile(self):
        """PUT /api/writing-studio/brand-profile should update profile"""
        payload = {
            "brand_name": "Test Brand",
            "voice_summary": "Professional and friendly",
            "preferred_phrases": ["innovative", "cutting-edge"],
            "do_not_use": ["cheap", "basic"],
            "fallback_user_id": TEST_GUEST_USER_ID
        }
        
        response = requests.put(
            f"{BASE_URL}/api/writing-studio/brand-profile",
            json=payload,
            headers=API_HEADERS,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "brand_profile" in data, "Response should contain brand_profile"
        
        profile = data.get("brand_profile", {})
        assert profile.get("brand_name") == "Test Brand", "Brand name should be updated"
        
        print("✓ Brand profile updated successfully")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
