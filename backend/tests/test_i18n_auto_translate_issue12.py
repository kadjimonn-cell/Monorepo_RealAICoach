"""
Issue 12: i18n Localization and Auto-Translation API Contract Tests

Tests for:
- POST /api/i18n/auto-translate - batch translate UI strings on-demand
- POST /api/i18n/auto-translate/jobs - create async translation job
- GET /api/i18n/auto-translate/jobs/status/{job_id} - check job status
- No ObjectId serialization or 500s in i18n endpoints
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestI18nAutoTranslateEndpoints:
    """Test i18n auto-translate API endpoints for Issue 12"""

    # ========== POST /api/i18n/auto-translate ==========
    
    def test_auto_translate_returns_valid_payload_for_french(self):
        """POST /api/i18n/auto-translate returns valid translation payload for French"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": ["Hello", "Support Center", "Dashboard"], "lang": "fr"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "translations" in data, f"Response missing 'translations' key: {data}"
        assert isinstance(data["translations"], dict), f"translations should be dict: {data}"
        
        # Verify all input texts have corresponding translations
        for text in ["Hello", "Support Center", "Dashboard"]:
            assert text in data["translations"], f"Missing translation for '{text}': {data}"
        
        print(f"PASSED: auto-translate returns valid payload - {data}")

    def test_auto_translate_returns_identity_for_english(self):
        """POST /api/i18n/auto-translate returns identity mapping for English"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": ["Hello", "World"], "lang": "en"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "translations" in data
        # For English, texts should map to themselves
        assert data["translations"].get("Hello") == "Hello"
        assert data["translations"].get("World") == "World"
        
        print(f"PASSED: auto-translate returns identity for English - {data}")

    def test_auto_translate_handles_empty_texts(self):
        """POST /api/i18n/auto-translate handles empty texts array gracefully"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": [], "lang": "fr"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "translations" in data
        assert data["translations"] == {}
        
        print(f"PASSED: auto-translate handles empty texts - {data}")

    def test_auto_translate_handles_unsupported_language(self):
        """POST /api/i18n/auto-translate handles unsupported language gracefully"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": ["Hello"], "lang": "xyz"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "translations" in data
        # For unsupported language, should return identity mapping
        assert data["translations"].get("Hello") == "Hello"
        
        print(f"PASSED: auto-translate handles unsupported language - {data}")

    def test_auto_translate_no_500_error(self):
        """POST /api/i18n/auto-translate does not return 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": ["Test string"], "lang": "es"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        print("PASSED: auto-translate no 500 error")

    # ========== POST /api/i18n/auto-translate/jobs ==========
    
    def test_auto_translate_jobs_creates_async_job(self):
        """POST /api/i18n/auto-translate/jobs creates async job and returns job_id"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": ["fr"]},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "success" in data, f"Response missing 'success' key: {data}"
        assert data["success"], f"Expected success=True: {data}"
        assert "job_id" in data, f"Response missing 'job_id' key: {data}"
        assert "status" in data, f"Response missing 'status' key: {data}"
        assert data["status"] == "queued", f"Expected status='queued': {data}"
        
        # Verify job_id is a valid string
        assert isinstance(data["job_id"], str), f"job_id should be string: {data}"
        assert len(data["job_id"]) > 0, f"job_id should not be empty: {data}"
        
        print(f"PASSED: auto-translate/jobs creates async job - job_id={data['job_id']}")
        return data["job_id"]

    def test_auto_translate_jobs_no_500_error(self):
        """POST /api/i18n/auto-translate/jobs does not return 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": []},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        print("PASSED: auto-translate/jobs no 500 error")

    # ========== GET /api/i18n/auto-translate/jobs/status/{job_id} ==========
    
    def test_auto_translate_job_status_returns_completed_or_queued_shape(self):
        """GET /api/i18n/auto-translate/jobs/status/{job_id} returns completed/queued shape"""
        # First create a job
        create_response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": ["es"]},
            headers={"Content-Type": "application/json"}
        )
        assert create_response.status_code == 200, f"Failed to create job: {create_response.text}"
        job_id = create_response.json()["job_id"]
        
        # Check status
        status_response = requests.get(
            f"{BASE_URL}/api/i18n/auto-translate/jobs/status/{job_id}",
            headers={"Content-Type": "application/json"}
        )
        assert status_response.status_code == 200, f"Expected 200, got {status_response.status_code}: {status_response.text}"
        
        data = status_response.json()
        
        # Verify required fields
        assert "job_id" in data, f"Response missing 'job_id': {data}"
        assert "status" in data, f"Response missing 'status': {data}"
        assert data["status"] in ["queued", "running", "completed", "error"], f"Invalid status: {data['status']}"
        
        # Verify no ObjectId serialization issues (no _id field or it's properly excluded)
        assert "_id" not in data, f"Response contains _id (ObjectId serialization issue): {data}"
        
        print(f"PASSED: job status returns valid shape - status={data['status']}")

    def test_auto_translate_job_status_not_found(self):
        """GET /api/i18n/auto-translate/jobs/status/{job_id} returns 404 for invalid job_id"""
        response = requests.get(
            f"{BASE_URL}/api/i18n/auto-translate/jobs/status/nonexistent_job_123",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        print("PASSED: job status returns 404 for invalid job_id")

    def test_auto_translate_job_status_no_500_error(self):
        """GET /api/i18n/auto-translate/jobs/status/{job_id} does not return 500 error"""
        # Create a job first
        create_response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": ["de"]},
            headers={"Content-Type": "application/json"}
        )
        job_id = create_response.json().get("job_id", "test_job")
        
        response = requests.get(
            f"{BASE_URL}/api/i18n/auto-translate/jobs/status/{job_id}",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        
        print("PASSED: job status no 500 error")

    # ========== ObjectId Serialization Tests ==========
    
    def test_no_objectid_in_auto_translate_response(self):
        """Verify no ObjectId serialization issues in auto-translate response"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate",
            json={"texts": ["Test"], "lang": "fr"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Check response is valid JSON (no ObjectId serialization error)
        try:
            data = response.json()
            # Verify no _id field
            assert "_id" not in data, f"Response contains _id: {data}"
            print("PASSED: no ObjectId in auto-translate response")
        except Exception as e:
            pytest.fail(f"JSON parsing failed (possible ObjectId issue): {e}")

    def test_no_objectid_in_jobs_response(self):
        """Verify no ObjectId serialization issues in jobs response"""
        response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": ["pt"]},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        try:
            data = response.json()
            assert "_id" not in data, f"Response contains _id: {data}"
            print("PASSED: no ObjectId in jobs response")
        except Exception as e:
            pytest.fail(f"JSON parsing failed (possible ObjectId issue): {e}")

    # ========== Additional i18n Endpoint Stability Tests ==========
    
    def test_i18n_languages_endpoint(self):
        """GET /api/i18n/languages returns supported languages"""
        response = requests.get(
            f"{BASE_URL}/api/i18n/languages",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "languages" in data, f"Response missing 'languages': {data}"
        assert isinstance(data["languages"], list), f"languages should be list: {data}"
        assert len(data["languages"]) > 0, f"languages should not be empty: {data}"
        
        # Verify language structure
        first_lang = data["languages"][0]
        assert "code" in first_lang, f"Language missing 'code': {first_lang}"
        
        print(f"PASSED: i18n/languages returns {len(data['languages'])} languages")

    def test_i18n_translations_endpoint(self):
        """GET /api/i18n/translations/{lang} returns translations (may require auth)"""
        response = requests.get(
            f"{BASE_URL}/api/i18n/translations/en",
            headers={"Content-Type": "application/json"}
        )
        # This endpoint may require auth - both 200 and 401 are acceptable
        # The key Issue 12 endpoints (auto-translate) don't require auth
        if response.status_code == 401:
            print("PASSED: i18n/translations/en requires auth (expected behavior)")
            return
        
        assert response.status_code == 200, f"Expected 200 or 401, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "lang" in data, f"Response missing 'lang': {data}"
        assert "translations" in data, f"Response missing 'translations': {data}"
        assert data["lang"] == "en", f"Expected lang='en': {data}"
        
        print("PASSED: i18n/translations/en returns valid data")

    def test_i18n_locales_endpoint(self):
        """GET /api/i18n/locales returns locale list"""
        response = requests.get(
            f"{BASE_URL}/api/i18n/locales",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "locales" in data, f"Response missing 'locales': {data}"
        assert "default" in data, f"Response missing 'default': {data}"
        
        print("PASSED: i18n/locales returns valid data")


class TestI18nJobLifecycle:
    """Test the full lifecycle of an auto-translate job"""
    
    def test_job_lifecycle_create_and_poll(self):
        """Test creating a job and polling for status"""
        # Create job
        create_response = requests.post(
            f"{BASE_URL}/api/i18n/auto-translate/jobs",
            json={"languages": ["ja"]},
            headers={"Content-Type": "application/json"}
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Poll status (up to 3 times)
        for i in range(3):
            status_response = requests.get(
                f"{BASE_URL}/api/i18n/auto-translate/jobs/status/{job_id}"
            )
            assert status_response.status_code == 200
            
            data = status_response.json()
            status = data.get("status")
            
            print(f"Poll {i+1}: job_id={job_id}, status={status}")
            
            # Verify response shape
            assert "job_id" in data
            assert "status" in data
            assert "_id" not in data  # No ObjectId
            
            if status in ["completed", "error"]:
                break
            
            time.sleep(1)
        
        print(f"PASSED: job lifecycle test completed - final status={status}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
