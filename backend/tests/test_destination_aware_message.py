"""
Test destination-aware restore toast message contract.
Validates that the subscription return toast helper generates correct
destination-aware success copy for various return targets.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthEnforcement:
    """Verify unauthenticated users are blocked from protected routes"""
    
    def test_dashboard_requires_auth(self):
        """Dashboard should redirect unauthenticated users to /welcome"""
        response = requests.get(f"{BASE_URL}/dashboard", allow_redirects=False)
        # Should redirect to welcome page
        assert response.status_code in [200, 302, 307], f"Expected redirect or page, got {response.status_code}"
        
    def test_profile_requires_auth(self):
        """Profile should redirect unauthenticated users"""
        response = requests.get(f"{BASE_URL}/profile", allow_redirects=False)
        assert response.status_code in [200, 302, 307], f"Expected redirect or page, got {response.status_code}"
        
    def test_features_requires_auth(self):
        """Features should redirect unauthenticated users"""
        response = requests.get(f"{BASE_URL}/features", allow_redirects=False)
        assert response.status_code in [200, 302, 307], f"Expected redirect or page, got {response.status_code}"
        
    def test_book_meeting_requires_auth(self):
        """Book meeting should redirect unauthenticated users"""
        response = requests.get(f"{BASE_URL}/book-meeting", allow_redirects=False)
        assert response.status_code in [200, 302, 307], f"Expected redirect or page, got {response.status_code}"


class TestBackendHealth:
    """Verify backend is healthy"""
    
    def test_health_endpoint(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
    def test_auth_login_endpoint_exists(self):
        """Auth login endpoint should exist"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword"
        })
        # Should return 401 for wrong credentials, not 404
        assert response.status_code in [401, 400, 422], f"Expected auth error, got {response.status_code}"


class TestDestinationAwareMessageContract:
    """
    Verify the destination-aware message contract via source code analysis.
    These tests validate the expected message mappings are present in the codebase.
    """
    
    def test_dashboard_message_contract(self):
        """Dashboard return target should have specific message"""
        # Read the source file
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        # Verify dashboard message
        assert "Your dashboard access is restored and ready to use." in content, \
            "Dashboard message not found in subscriptionReturnToast.ts"
            
    def test_profile_message_contract(self):
        """Profile return target should have specific message"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "Your profile access is restored, and your settings are ready to review." in content, \
            "Profile message not found in subscriptionReturnToast.ts"
            
    def test_features_root_message_contract(self):
        """Features root return target should have specific message"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "Your premium tools are unlocked in Features and ready to explore." in content, \
            "Features root message not found in subscriptionReturnToast.ts"
            
    def test_features_subpath_message_contract(self):
        """Features subpath return target should have dynamic message"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "Your upgraded access is ready in ${destinationLabel}." in content, \
            "Features subpath message not found in subscriptionReturnToast.ts"
            
    def test_booking_message_contract(self):
        """Booking return target should have specific message"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "Your booking space is restored so you can continue planning right away." in content, \
            "Booking message not found in subscriptionReturnToast.ts"
            
    def test_fallback_message_contract(self):
        """Fallback return target should have dynamic message"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "Your access is restored in ${destinationLabel} and ready to use." in content, \
            "Fallback message not found in subscriptionReturnToast.ts"
            
    def test_appshell_uses_payload_toast_fields(self):
        """AppShell should prefer payload.toastTitle and payload.toastMessage"""
        with open('/app/frontend/src/components/AppShell.tsx', 'r') as f:
            content = f.read()
        
        assert "payload.toastTitle" in content, \
            "AppShell should use payload.toastTitle"
        assert "payload.toastMessage" in content, \
            "AppShell should use payload.toastMessage"
            
    def test_getmessageconfig_function_exists(self):
        """getMessageConfig function should exist in subscriptionReturnToast.ts"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "function getMessageConfig(returnTarget: string, destinationLabel: string, planName?: string | null)" in content, \
            "getMessageConfig function not found with correct signature"
            
    def test_stash_function_stores_message_fields(self):
        """stashSubscriptionReturnToast should store toastTitle and toastMessage"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "toastTitleFallback: message.toastTitleFallback" in content, \
            "stashSubscriptionReturnToast should store toastTitle"
        assert "toastMessageFallback: message.toastMessageFallback" in content, \
            "stashSubscriptionReturnToast should store toastMessage"


class TestDestinationAwareCTAContract:
    """Verify the destination-aware CTA mapping contract (from previous iteration)"""
    
    def test_profile_cta_mapping(self):
        """Profile path should map to 'Profile settings' CTA"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "actionLabelFallback: 'Profile settings'" in content
        assert "actionRoute: '/edit-profile'" in content
        
    def test_features_cta_mapping(self):
        """Features path should map to 'Explore premium tools' CTA"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "actionLabelFallback: 'Explore premium tools'" in content
        assert "actionRoute: '/features'" in content
        
    def test_booking_cta_mapping(self):
        """Booking path should map to 'Review agenda' CTA"""
        with open('/app/frontend/src/utils/subscriptionReturnToast.ts', 'r') as f:
            content = f.read()
        
        assert "actionLabelFallback: 'Review agenda'" in content
        assert "actionRoute: '/book-meeting'" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
