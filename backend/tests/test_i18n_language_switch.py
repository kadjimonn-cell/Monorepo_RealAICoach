"""
i18n Language Switch Tests - Iteration 225
Tests for language preference persistence and no-rollback behavior.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')

class TestI18nLanguageSwitch:
    """Tests for i18n language switch functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "p1.free.1779113329@example.com",
                "password": "P1Free#2026!Aa"
            }
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user_data = login_response.json()
        yield
        
        # Cleanup - reset language to English
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "en"}
        )
    
    def test_get_user_preference_returns_current_language(self):
        """GET /api/i18n/user-preference returns current language preference"""
        response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
        
        assert response.status_code == 200
        data = response.json()
        assert "language" in data
        assert "has_preference" in data
        assert "source" in data
        print(f"Current language: {data['language']}")
    
    def test_post_user_preference_changes_language(self):
        """POST /api/i18n/user-preference successfully changes language"""
        # Change to German
        response = self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "de"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success")
        assert data.get("language") == "de"
        
        # Verify change persisted
        verify_response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["language"] == "de"
        assert verify_data["has_preference"]
        print("Language changed to German and persisted")
    
    def test_language_change_updates_profile(self):
        """Language change updates user profile language_preference field"""
        # Change to French
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "fr"}
        )
        
        # Verify profile updated
        profile_response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert profile_response.status_code == 200
        profile_data = profile_response.json()
        assert profile_data.get("language_preference") == "fr"
        print("Profile language_preference updated to French")
    
    def test_multiple_language_switches_persist(self):
        """Multiple language switches all persist correctly"""
        languages = ["es", "ja", "zh", "ko", "en"]
        
        for lang in languages:
            # Change language
            response = self.session.post(
                f"{BASE_URL}/api/i18n/user-preference",
                json={"language": lang}
            )
            assert response.status_code == 200
            
            # Verify persisted
            verify_response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
            assert verify_response.status_code == 200
            assert verify_response.json()["language"] == lang
            print(f"Language switch to {lang} persisted")
    
    def test_language_preference_source_is_account_profile(self):
        """Language preference source should be account_profile after setting"""
        # Set a language
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "it"}
        )
        
        # Verify source
        response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "account_profile"
        print("Language preference source is account_profile")
    
    def test_invalid_language_code_handling(self):
        """Invalid language codes should be handled gracefully"""
        # Try setting an invalid language code
        response = self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "invalid_code_xyz"}
        )
        
        # Should either reject or normalize to a valid code
        # The API may accept it and normalize, or return an error
        # Either behavior is acceptable as long as it doesn't crash
        assert response.status_code in [200, 400]
        print(f"Invalid language code handled with status {response.status_code}")


class TestI18nNoRollback:
    """Tests to verify language doesn't roll back after being set"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "p1.free.1779113329@example.com",
                "password": "P1Free#2026!Aa"
            }
        )
        assert login_response.status_code == 200
        yield
        
        # Cleanup
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "en"}
        )
    
    def test_language_persists_after_multiple_gets(self):
        """Language should persist after multiple GET requests"""
        # Set language to Portuguese
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "pt"}
        )
        
        # Make multiple GET requests
        for i in range(5):
            response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
            assert response.status_code == 200
            assert response.json()["language"] == "pt", f"Language rolled back on GET #{i+1}"
        
        print("Language persisted after 5 GET requests")
    
    def test_language_persists_after_profile_fetch(self):
        """Language should persist after fetching user profile"""
        # Set language to Arabic
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "ar"}
        )
        
        # Fetch profile
        self.session.get(f"{BASE_URL}/api/auth/me")
        
        # Verify language still set
        response = self.session.get(f"{BASE_URL}/api/i18n/user-preference")
        assert response.status_code == 200
        assert response.json()["language"] == "ar"
        print("Language persisted after profile fetch")
    
    def test_language_persists_across_sessions(self):
        """Language should persist across login sessions"""
        # Set language to Hindi
        self.session.post(
            f"{BASE_URL}/api/i18n/user-preference",
            json={"language": "hi"}
        )
        
        # Create new session and login again
        new_session = requests.Session()
        new_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = new_session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "p1.free.1779113329@example.com",
                "password": "P1Free#2026!Aa"
            }
        )
        assert login_response.status_code == 200
        
        # Verify language persisted
        response = new_session.get(f"{BASE_URL}/api/i18n/user-preference")
        assert response.status_code == 200
        assert response.json()["language"] == "hi"
        print("Language persisted across sessions")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
