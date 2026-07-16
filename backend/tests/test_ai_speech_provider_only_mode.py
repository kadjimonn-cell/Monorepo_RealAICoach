# ruff: noqa
"""
Voice Studio (Feature 17) - Provider-Only Mode Verification Tests
Tests: Verify NO fallback behavior for transcribe/synthesize when provider fails
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Generate unique guest ID for test isolation
TEST_GUEST_ID = f"user_provonly_{uuid.uuid4().hex[:12]}"


class TestSetup:
    """Setup helper to create a project for testing"""
    
    @staticmethod
    def create_test_project(guest_id: str) -> str:
        """Create a test project and return project_id"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Provider-Only Test {uuid.uuid4().hex[:8]}",
                "brief": "Project for provider-only mode testing",
                "objective": "presentation",
                "fallback_user_id": guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if response.status_code == 200:
            return response.json().get("project", {}).get("project_id")
        return None


class TestHealthAndBootstrap:
    """Basic health and bootstrap tests"""
    
    def test_health_endpoint_returns_200(self):
        """GET /api/ai-speech-studio/health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature") == "Voice Studio"
        assert data.get("feature_id") == "ai-speech"
        print(f"✓ Health endpoint: status={data.get('status')}, feature={data.get('feature')}")
    
    def test_bootstrap_returns_plan_and_limits(self):
        """GET /api/ai-speech-studio/bootstrap should return plan and limits"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/bootstrap",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") is True
        assert "plan" in data
        assert "limits" in data
        assert "usage" in data
        print(f"✓ Bootstrap: plan={data.get('plan')}, limits={data.get('limits')}")


class TestProjectCreate:
    """Project creation tests"""
    
    def test_create_project_returns_200(self):
        """POST /api/ai-speech-studio/projects/create should create project"""
        unique_guest = f"user_create_{uuid.uuid4().hex[:12]}"
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"Test Project {uuid.uuid4().hex[:8]}",
                "brief": "Test project creation",
                "objective": "presentation",
                "fallback_user_id": unique_guest
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "project" in data
        project = data.get("project", {})
        assert project.get("project_id", "").startswith("aivs_")
        print(f"✓ Project created: project_id={project.get('project_id')}")


class TestTranscribeProviderOnlyMode:
    """
    Transcribe endpoint tests - PROVIDER-ONLY MODE
    When provider fails, should return error (NOT fallback text)
    """
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for transcribe tests"""
        self.guest_id = f"user_transcribe_{uuid.uuid4().hex[:12]}"
        self.project_id = TestSetup.create_test_project(self.guest_id)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping transcribe tests")
    
    def test_transcribe_provider_failure_returns_non_200(self):
        """
        POST /api/ai-speech-studio/projects/{id}/transcribe
        When provider fails, should return 500/502 with error_code (NOT 200 with fallback text)
        """
        # Create a fake audio blob that will fail transcription
        audio_content = b"fake audio content that cannot be transcribed"
        files = {"audio": ("test_audio.webm", audio_content, "audio/webm")}
        
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/transcribe",
            params={
                "fallback_user_id": self.guest_id,
                "idempotency_key": f"transcribe-fail-{uuid.uuid4().hex[:8]}"
            },
            files=files
        )
        
        # Provider-only mode: should NOT return 200 with fallback text
        # Should return 500 (provider not configured) or 502 (provider failed)
        assert response.status_code in [500, 502], \
            f"Provider-only mode: Expected 500/502 on provider failure, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        
        # Verify proper error code is returned
        valid_error_codes = ["ai_speech_provider_not_configured", "ai_speech_transcription_failed"]
        assert detail.get("error_code") in valid_error_codes, \
            f"Expected error_code in {valid_error_codes}, got: {detail}"
        
        # CRITICAL: Verify NO fallback transcript text is returned
        assert "transcript" not in data, \
            f"Provider-only mode violation: Should NOT return fallback transcript, got: {data}"
        
        print(f"✓ Transcribe provider-only mode: status={response.status_code}, error_code={detail.get('error_code')}")
        print(f"  - Confirmed: No fallback transcript returned")


class TestSynthesizeProviderOnlyMode:
    """
    Synthesize endpoint tests - PROVIDER-ONLY MODE
    When provider fails, should return error (NOT fallback bytes)
    """
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for synthesize tests"""
        self.guest_id = f"user_synth_{uuid.uuid4().hex[:12]}"
        self.project_id = TestSetup.create_test_project(self.guest_id)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping synthesize tests")
    
    def test_synthesize_success_when_provider_works(self):
        """
        POST /api/ai-speech-studio/projects/{id}/synthesize
        When provider works, should return 200 with audio_url
        """
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Hello, this is a test synthesis for Voice Studio.",
                "voice": "alloy",
                "format": "mp3",
                "idempotency_key": f"synth-success-{uuid.uuid4().hex[:8]}",
                "fallback_user_id": self.guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        # If provider is configured and working, should return 200
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is True
            assert "synthesis_id" in data
            assert data.get("synthesis_id", "").startswith("syn_")
            assert "audio_id" in data
            assert data.get("audio_id", "").startswith("aud_")
            assert "audio_url" in data
            assert data.get("audio_url", "").startswith("/api/ai-speech-studio/file/")
            print(f"✓ Synthesize success: synthesis_id={data.get('synthesis_id')}, audio_url={data.get('audio_url')}")
        else:
            # Provider-only mode: should return 500/502 with error code
            assert response.status_code in [500, 502], \
                f"Expected 200 (success) or 500/502 (provider failure), got {response.status_code}"
            
            data = response.json()
            detail = data.get("detail", {})
            valid_error_codes = ["ai_speech_provider_not_configured", "ai_speech_synthesis_failed"]
            assert detail.get("error_code") in valid_error_codes, \
                f"Expected error_code in {valid_error_codes}, got: {detail}"
            
            # CRITICAL: Verify NO fallback audio is returned
            assert "audio_url" not in data, \
                f"Provider-only mode violation: Should NOT return fallback audio, got: {data}"
            
            print(f"✓ Synthesize provider-only mode: status={response.status_code}, error_code={detail.get('error_code')}")
    
    def test_synthesize_invalid_voice_returns_422(self):
        """POST /api/ai-speech-studio/projects/{id}/synthesize with invalid voice should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Test text",
                "voice": "invalid_voice_name",
                "format": "mp3",
                "fallback_user_id": self.guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_invalid_voice"
        assert "supported_voices" in detail
        print(f"✓ Synthesize invalid voice returns 422: error_code={detail.get('error_code')}")


class TestIdempotencyBehavior:
    """Idempotency replay tests for transcribe and synthesize"""
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for idempotency tests"""
        self.guest_id = f"user_idem_{uuid.uuid4().hex[:12]}"
        self.project_id = TestSetup.create_test_project(self.guest_id)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping idempotency tests")
    
    def test_synthesize_idempotency_replay(self):
        """
        POST /api/ai-speech-studio/projects/{id}/synthesize with same idempotency_key
        Second call should return idempotent_replay=true with same IDs
        """
        idempotency_key = f"synth-idem-{uuid.uuid4().hex[:8]}"
        
        # First call
        response1 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Idempotency test synthesis.",
                "voice": "alloy",
                "format": "mp3",
                "idempotency_key": idempotency_key,
                "fallback_user_id": self.guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        
        if response1.status_code != 200:
            pytest.skip(f"First synthesize call failed with {response1.status_code}, skipping idempotency test")
        
        data1 = response1.json()
        assert data1.get("idempotent_replay") is False, f"First call should not be replay: {data1}"
        
        # Second call with same idempotency_key
        response2 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Idempotency test synthesis.",
                "voice": "alloy",
                "format": "mp3",
                "idempotency_key": idempotency_key,
                "fallback_user_id": self.guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response2.status_code == 200, f"Second call failed: {response2.status_code}: {response2.text}"
        
        data2 = response2.json()
        assert data2.get("idempotent_replay") is True, f"Second call should be replay: {data2}"
        assert data2.get("synthesis_id") == data1.get("synthesis_id"), "Replay should return same synthesis_id"
        assert data2.get("audio_id") == data1.get("audio_id"), "Replay should return same audio_id"
        
        print(f"✓ Synthesize idempotency replay: idempotent_replay={data2.get('idempotent_replay')}")


class TestVoicePresetEndpoint:
    """GET/PUT /api/ai-speech-studio/voice-preset tests"""
    
    def test_get_voice_presets_returns_200(self):
        """GET /api/ai-speech-studio/voice-preset should return presets list"""
        guest_id = f"user_preset_{uuid.uuid4().hex[:12]}"
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/voice-preset",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "presets" in data
        assert isinstance(data.get("presets"), list)
        assert "plan" in data
        assert "limit" in data
        assert "used" in data
        print(f"✓ Get voice presets: count={len(data.get('presets', []))}, limit={data.get('limit')}")
    
    def test_put_voice_preset_returns_200(self):
        """PUT /api/ai-speech-studio/voice-preset should upsert preset"""
        guest_id = f"user_preset_{uuid.uuid4().hex[:12]}"
        response = requests.put(
            f"{BASE_URL}/api/ai-speech-studio/voice-preset",
            json={
                "voice": "alloy",
                "style_notes": "Professional tone for testing",
                "language": "en",
                "fallback_user_id": guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert "preset" in data
        preset = data.get("preset", {})
        assert preset.get("preset_id", "").startswith("vp_")
        assert preset.get("voice") == "alloy"
        print(f"✓ Put voice preset: preset_id={preset.get('preset_id')}")


class TestAuthRequirements:
    """Authentication requirement tests"""
    
    def test_bootstrap_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/bootstrap without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_auth_required"
        print(f"✓ Bootstrap without auth returns 401")
    
    def test_voice_preset_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/voice-preset without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/voice-preset")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Voice preset without auth returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
