# ruff: noqa
"""
Voice Studio (Feature 17) - P1/P2 Backend API Tests
Tests: transcribe, synthesize, voice-preset, exports, file retrieval, idempotency replay
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Generate unique guest ID for test isolation
TEST_GUEST_ID = f"user_p1p2test_{uuid.uuid4().hex[:12]}"


class TestSetup:
    """Setup helper to create a project for testing"""
    
    @staticmethod
    def create_test_project(guest_id: str) -> str:
        """Create a test project and return project_id"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/create",
            json={
                "title": f"P1P2 Test Project {uuid.uuid4().hex[:8]}",
                "brief": "Project for P1/P2 endpoint testing",
                "objective": "presentation",
                "fallback_user_id": guest_id
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if response.status_code == 200:
            return response.json().get("project", {}).get("project_id")
        return None


class TestTranscribeEndpoint:
    """POST /api/ai-speech-studio/projects/{id}/transcribe tests"""
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for transcribe tests"""
        self.project_id = TestSetup.create_test_project(TEST_GUEST_ID)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping transcribe tests")
    
    def test_transcribe_returns_200_with_transcript(self):
        """POST /api/ai-speech-studio/projects/{id}/transcribe should return transcript"""
        # Create a simple audio-like blob for testing
        audio_content = b"test audio content for transcription"
        files = {"audio": ("test_audio.webm", audio_content, "audio/webm")}
        
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/transcribe",
            params={
                "fallback_user_id": TEST_GUEST_ID,
                "idempotency_key": f"transcribe-test-{uuid.uuid4().hex[:8]}"
            },
            files=files
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "transcript_id" in data, f"Expected 'transcript_id' in response, got: {data}"
        assert data.get("transcript_id").startswith("trn_"), f"Expected transcript_id to start with 'trn_', got: {data}"
        assert "transcript" in data, f"Expected 'transcript' in response, got: {data}"
        assert data.get("idempotent_replay") is False, f"Expected idempotent_replay=False for first call, got: {data}"
        
        print(f"✓ Transcribe: transcript_id={data.get('transcript_id')}")
        print(f"  - transcript: {data.get('transcript')[:100]}...")
        return data
    
    def test_transcribe_idempotency_replay(self):
        """POST /api/ai-speech-studio/projects/{id}/transcribe with same idempotency_key should replay"""
        idempotency_key = f"transcribe-idem-{uuid.uuid4().hex[:8]}"
        audio_content = b"test audio for idempotency"
        files = {"audio": ("test_audio.webm", audio_content, "audio/webm")}
        
        # First call
        response1 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/transcribe",
            params={
                "fallback_user_id": TEST_GUEST_ID,
                "idempotency_key": idempotency_key
            },
            files=files
        )
        assert response1.status_code == 200, f"First transcribe failed: {response1.status_code}: {response1.text}"
        data1 = response1.json()
        assert data1.get("idempotent_replay") is False, f"First call should not be replay: {data1}"
        
        # Second call with same idempotency_key
        files2 = {"audio": ("test_audio.webm", audio_content, "audio/webm")}
        response2 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/transcribe",
            params={
                "fallback_user_id": TEST_GUEST_ID,
                "idempotency_key": idempotency_key
            },
            files=files2
        )
        assert response2.status_code == 200, f"Second transcribe failed: {response2.status_code}: {response2.text}"
        data2 = response2.json()
        assert data2.get("idempotent_replay") is True, f"Second call should be replay: {data2}"
        assert data2.get("transcript_id") == data1.get("transcript_id"), f"Replay should return same transcript_id"
        
        print(f"✓ Transcribe idempotency replay: idempotent_replay={data2.get('idempotent_replay')}")
    
    def test_transcribe_without_auth_returns_401(self):
        """POST /api/ai-speech-studio/projects/{id}/transcribe without auth should return 401"""
        audio_content = b"test audio"
        files = {"audio": ("test_audio.webm", audio_content, "audio/webm")}
        
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/transcribe",
            files=files
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Transcribe without auth returns 401")


class TestSynthesizeEndpoint:
    """POST /api/ai-speech-studio/projects/{id}/synthesize tests"""
    
    @pytest.fixture(autouse=True)
    def setup_project(self):
        """Create a project for synthesize tests"""
        self.project_id = TestSetup.create_test_project(TEST_GUEST_ID)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping synthesize tests")
    
    def test_synthesize_returns_200_with_audio_url(self):
        """POST /api/ai-speech-studio/projects/{id}/synthesize should return audio_url"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Hello, this is a test synthesis for Voice Studio enterprise workflow.",
                "voice": "alloy",
                "format": "mp3",
                "idempotency_key": f"synthesize-test-{uuid.uuid4().hex[:8]}",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "synthesis_id" in data, f"Expected 'synthesis_id' in response, got: {data}"
        assert data.get("synthesis_id").startswith("syn_"), f"Expected synthesis_id to start with 'syn_', got: {data}"
        assert "audio_id" in data, f"Expected 'audio_id' in response, got: {data}"
        assert data.get("audio_id").startswith("aud_"), f"Expected audio_id to start with 'aud_', got: {data}"
        assert "audio_url" in data, f"Expected 'audio_url' in response, got: {data}"
        assert data.get("audio_url").startswith("/api/ai-speech-studio/file/"), f"Expected audio_url to start with '/api/ai-speech-studio/file/', got: {data}"
        assert data.get("voice") == "alloy", f"Expected voice='alloy', got: {data}"
        assert data.get("format") == "mp3", f"Expected format='mp3', got: {data}"
        assert data.get("idempotent_replay") is False, f"Expected idempotent_replay=False for first call, got: {data}"
        
        print(f"✓ Synthesize: synthesis_id={data.get('synthesis_id')}, audio_url={data.get('audio_url')}")
        self.audio_id = data.get("audio_id")
        return data
    
    def test_synthesize_idempotency_replay(self):
        """POST /api/ai-speech-studio/projects/{id}/synthesize with same idempotency_key should replay"""
        idempotency_key = f"synthesize-idem-{uuid.uuid4().hex[:8]}"
        
        # First call
        response1 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Idempotency test synthesis text.",
                "voice": "nova",
                "format": "mp3",
                "idempotency_key": idempotency_key,
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response1.status_code == 200, f"First synthesize failed: {response1.status_code}: {response1.text}"
        data1 = response1.json()
        assert data1.get("idempotent_replay") is False, f"First call should not be replay: {data1}"
        
        # Second call with same idempotency_key
        response2 = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Idempotency test synthesis text.",
                "voice": "nova",
                "format": "mp3",
                "idempotency_key": idempotency_key,
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response2.status_code == 200, f"Second synthesize failed: {response2.status_code}: {response2.text}"
        data2 = response2.json()
        assert data2.get("idempotent_replay") is True, f"Second call should be replay: {data2}"
        assert data2.get("synthesis_id") == data1.get("synthesis_id"), f"Replay should return same synthesis_id"
        assert data2.get("audio_id") == data1.get("audio_id"), f"Replay should return same audio_id"
        
        print(f"✓ Synthesize idempotency replay: idempotent_replay={data2.get('idempotent_replay')}")
    
    def test_synthesize_invalid_voice_returns_422(self):
        """POST /api/ai-speech-studio/projects/{id}/synthesize with invalid voice should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Test text",
                "voice": "invalid_voice_name",
                "format": "mp3",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_invalid_voice", f"Expected error_code='ai_speech_invalid_voice', got: {detail}"
        assert "supported_voices" in detail, f"Expected 'supported_voices' in detail, got: {detail}"
        
        print(f"✓ Synthesize invalid voice returns 422: {detail.get('error_code')}")
    
    def test_synthesize_without_auth_returns_401(self):
        """POST /api/ai-speech-studio/projects/{id}/synthesize without auth should return 401"""
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Test text",
                "voice": "alloy",
                "format": "mp3"
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Synthesize without auth returns 401")


class TestVoicePresetEndpoint:
    """GET/PUT /api/ai-speech-studio/voice-preset tests"""
    
    def test_get_voice_presets_returns_200(self):
        """GET /api/ai-speech-studio/voice-preset should return presets list"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/voice-preset",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "presets" in data, f"Expected 'presets' in response, got: {data}"
        assert isinstance(data.get("presets"), list), f"Expected 'presets' to be a list, got: {type(data.get('presets'))}"
        assert "plan" in data, f"Expected 'plan' in response, got: {data}"
        assert "limit" in data, f"Expected 'limit' in response, got: {data}"
        assert "used" in data, f"Expected 'used' in response, got: {data}"
        
        print(f"✓ Get voice presets: count={len(data.get('presets', []))}, limit={data.get('limit')}, used={data.get('used')}")
    
    def test_put_voice_preset_returns_200(self):
        """PUT /api/ai-speech-studio/voice-preset should upsert preset"""
        response = requests.put(
            f"{BASE_URL}/api/ai-speech-studio/voice-preset",
            json={
                "voice": "alloy",
                "style_notes": "Professional, calm, authoritative tone for business presentations",
                "language": "en",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert "preset" in data, f"Expected 'preset' in response, got: {data}"
        
        preset = data.get("preset", {})
        assert "preset_id" in preset, f"Expected 'preset_id' in preset, got: {preset}"
        assert preset.get("preset_id").startswith("vp_"), f"Expected preset_id to start with 'vp_', got: {preset}"
        assert preset.get("voice") == "alloy", f"Expected voice='alloy', got: {preset}"
        assert preset.get("language") == "en", f"Expected language='en', got: {preset}"
        
        print(f"✓ Put voice preset: preset_id={preset.get('preset_id')}, voice={preset.get('voice')}")
    
    def test_put_voice_preset_invalid_voice_returns_422(self):
        """PUT /api/ai-speech-studio/voice-preset with invalid voice should return 422"""
        response = requests.put(
            f"{BASE_URL}/api/ai-speech-studio/voice-preset",
            json={
                "voice": "invalid_voice",
                "style_notes": "Test notes",
                "language": "en",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_invalid_voice", f"Expected error_code='ai_speech_invalid_voice', got: {detail}"
        
        print(f"✓ Put voice preset invalid voice returns 422")
    
    def test_get_voice_presets_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/voice-preset without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/ai-speech-studio/voice-preset")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Get voice presets without auth returns 401")


class TestExportsEndpoint:
    """GET /api/ai-speech-studio/projects/{id}/exports tests"""
    
    @pytest.fixture(autouse=True)
    def setup_project_with_data(self):
        """Create a project with some data for export tests"""
        self.project_id = TestSetup.create_test_project(TEST_GUEST_ID)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping exports tests")
        
        # Add some analysis data
        requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/analyze",
            json={
                "prompt": "Test prompt for export verification",
                "target": "project",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=60
        )
    
    def test_exports_returns_200_with_data(self):
        """GET /api/ai-speech-studio/projects/{id}/exports should return export data"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/exports",
            params={
                "fallback_user_id": TEST_GUEST_ID,
                "include_analysis": True,
                "include_transcripts": True,
                "include_synthesis": True,
                "limit": 25
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        assert data.get("project_id") == self.project_id, f"Expected project_id={self.project_id}, got: {data}"
        assert "plan" in data, f"Expected 'plan' in response, got: {data}"
        assert "exported_at" in data, f"Expected 'exported_at' in response, got: {data}"
        
        # Check for optional data arrays
        if "analyses" in data:
            assert isinstance(data.get("analyses"), list), f"Expected 'analyses' to be a list"
        if "transcripts" in data:
            assert isinstance(data.get("transcripts"), list), f"Expected 'transcripts' to be a list"
        if "synthesis" in data:
            assert isinstance(data.get("synthesis"), list), f"Expected 'synthesis' to be a list"
            # Check that synthesis items have audio_url
            for item in data.get("synthesis", []):
                if "audio_id" in item:
                    assert "audio_url" in item, f"Expected 'audio_url' in synthesis item, got: {item}"
        
        print(f"✓ Exports: project_id={data.get('project_id')}")
        print(f"  - analyses: {len(data.get('analyses', []))}")
        print(f"  - transcripts: {len(data.get('transcripts', []))}")
        print(f"  - synthesis: {len(data.get('synthesis', []))}")
    
    def test_exports_nonexistent_project_returns_404(self):
        """GET /api/ai-speech-studio/projects/{invalid_id}/exports should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/projects/aivs_nonexistent123/exports",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_project_not_found", f"Expected error_code='ai_speech_project_not_found', got: {detail}"
        
        print(f"✓ Exports nonexistent project returns 404")
    
    def test_exports_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/projects/{id}/exports without auth should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/exports"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ Exports without auth returns 401")


class TestFileEndpoint:
    """GET /api/ai-speech-studio/file/{audio_id} tests"""
    
    @pytest.fixture(autouse=True)
    def setup_project_with_synthesis(self):
        """Create a project with synthesis for file tests"""
        self.project_id = TestSetup.create_test_project(TEST_GUEST_ID)
        if not self.project_id:
            pytest.skip("Project creation failed, skipping file tests")
        
        # Create synthesis to get audio_id
        response = requests.post(
            f"{BASE_URL}/api/ai-speech-studio/projects/{self.project_id}/synthesize",
            json={
                "text": "Test synthesis for file retrieval verification.",
                "voice": "alloy",
                "format": "mp3",
                "idempotency_key": f"file-test-{uuid.uuid4().hex[:8]}",
                "fallback_user_id": TEST_GUEST_ID
            },
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if response.status_code == 200:
            self.audio_id = response.json().get("audio_id")
        else:
            self.audio_id = None
    
    def test_file_returns_audio_content(self):
        """GET /api/ai-speech-studio/file/{audio_id} should return audio content"""
        if not self.audio_id:
            pytest.skip("Synthesis failed, skipping file test")
        
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/file/{self.audio_id}",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "audio" in content_type.lower() or "octet-stream" in content_type.lower(), f"Expected audio content type, got: {content_type}"
        
        # Check that content is not empty
        assert len(response.content) > 0, f"Expected non-empty audio content"
        
        print(f"✓ File retrieval: audio_id={self.audio_id}, content_type={content_type}, size={len(response.content)} bytes")
    
    def test_file_nonexistent_returns_404(self):
        """GET /api/ai-speech-studio/file/{invalid_id} should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/file/aud_nonexistent123",
            params={"fallback_user_id": TEST_GUEST_ID}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        assert detail.get("error_code") == "ai_speech_audio_not_found", f"Expected error_code='ai_speech_audio_not_found', got: {detail}"
        
        print(f"✓ File nonexistent returns 404")
    
    def test_file_without_auth_returns_401(self):
        """GET /api/ai-speech-studio/file/{audio_id} without auth should return 401"""
        if not self.audio_id:
            pytest.skip("Synthesis failed, skipping file auth test")
        
        response = requests.get(
            f"{BASE_URL}/api/ai-speech-studio/file/{self.audio_id}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print(f"✓ File without auth returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
