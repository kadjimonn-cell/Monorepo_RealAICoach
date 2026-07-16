"""
Feature 32 Phase-2 API Contract Tests
Tests the new template policy control-plane endpoints:
- GET /api/email-notifications/template-policies
- POST /api/email-notifications/template-policies/protected-sync
- POST /api/email-notifications/template-policies/override-approval
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Non-admin user for permission testing
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with auth cookie."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    
    return session


@pytest.fixture(scope="module")
def free_user_session():
    """Get non-admin user session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    
    if resp.status_code != 200:
        pytest.skip(f"Free user login failed: {resp.status_code} - {resp.text[:200]}")
    
    return session


class TestPhase2PolicyControlPlaneEndpoints:
    """Test Phase-2 template policy control-plane endpoints."""
    
    def test_get_template_policies_requires_admin(self, free_user_session):
        """Non-admin users should be blocked from GET /template-policies."""
        resp = free_user_session.get(f"{BASE_URL}/api/email-notifications/template-policies")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        data = resp.json()
        # May return subscription required or admin only depending on middleware order
        assert "Admin only" in str(data.get("detail", "")) or "Subscription Required" in str(data.get("error", ""))
    
    def test_get_template_policies_admin_success(self, admin_session):
        """Admin should be able to GET /template-policies."""
        resp = admin_session.get(f"{BASE_URL}/api/email-notifications/template-policies")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert "count" in data
        assert "policies" in data
        assert isinstance(data["policies"], list)
    
    def test_protected_sync_requires_admin(self, free_user_session):
        """Non-admin users should be blocked from POST /template-policies/protected-sync."""
        resp = free_user_session.post(f"{BASE_URL}/api/email-notifications/template-policies/protected-sync")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    
    def test_protected_sync_admin_success(self, admin_session):
        """Admin should be able to sync protected template policies."""
        resp = admin_session.post(f"{BASE_URL}/api/email-notifications/template-policies/protected-sync")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert "upserted" in data
        assert data["upserted"] > 0, "Should have upserted at least one protected policy"
        assert "updated_at" in data
    
    def test_override_approval_requires_admin(self, free_user_session):
        """Non-admin users should be blocked from POST /template-policies/override-approval."""
        resp = free_user_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={"template_key": "test_template", "approved": True}
        )
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    
    def test_override_approval_requires_template_key(self, admin_session):
        """Override approval should require template_key."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={"approved": True}
        )
        assert resp.status_code == 400, f"Expected 400 for missing template_key, got {resp.status_code}"
        data = resp.json()
        assert "template_key is required" in str(data.get("detail", ""))
    
    def test_override_approval_blocks_protected_template_approval(self, admin_session):
        """
        CRITICAL: Override approval should REJECT approval for protected templates.
        This is the key Phase-2 policy enforcement test.
        """
        # Test with a known protected template key
        protected_keys = [
            "meeting_reminder",
            "meeting_reminder_calendar",
            "booking_created",
            "booking_confirmed_host",
            "booking_confirmed_guest",
            "booking_cancelled",
            "booking_rescheduled",
            "agenda_reminder",
        ]
        
        for protected_key in protected_keys:
            resp = admin_session.post(
                f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
                json={"template_key": protected_key, "approved": True}
            )
            assert resp.status_code == 400, f"Expected 400 for protected template '{protected_key}', got {resp.status_code}"
            data = resp.json()
            assert "Protected template overrides cannot be approved" in str(data.get("detail", "")), \
                f"Expected protected template rejection message for '{protected_key}', got: {data}"
    
    def test_override_approval_allows_non_protected_template(self, admin_session):
        """Override approval should allow non-protected templates."""
        # Use a non-protected template key
        non_protected_key = "weekly_engagement"
        
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": non_protected_key,
                "approved": True,
                "note": "Test approval",
                "approval_id": "APR-TEST-001",
                "expires_at": "2099-12-31T23:59:59+00:00",
            }
        )
        assert resp.status_code == 200, f"Expected 200 for non-protected template, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("template_key") == non_protected_key
        assert data.get("override_approved") is True
    
    def test_override_approval_allows_rejection_for_protected_template(self, admin_session):
        """Override approval should allow REJECTION (approved=False) for protected templates."""
        protected_key = "meeting_reminder"
        
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={"template_key": protected_key, "approved": False, "note": "Rejecting override"}
        )
        assert resp.status_code == 200, f"Expected 200 for rejection, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("override_approved") is False


class TestSubscriptionRenewalUNODispatch:
    """Test that subscription renewal reminders use UNO dispatch reservation."""
    
    def test_renewal_reminder_dedupe_key_pattern_in_source(self):
        """Verify the dedupe key pattern is correctly implemented."""
        from pathlib import Path
        source = Path("/app/backend/routes/subscription_enforcement.py").read_text()
        
        # Check the dedupe key pattern includes all required components
        assert 'dedupe_key = f"renewal_reminder:{str(user_doc.get(\'user_id\') or \'\')}:{days}:{email_normalized}:{renewal_date}"' in source
        
        # Check reserve_dispatch_once is imported and used
        assert "from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status" in source
        assert "reserved = await reserve_dispatch_once(" in source
        
        # Check the guard pattern exists
        assert "if not reserved:" in source
        
        # Check mark_dispatch_status is called for both success and failure
        assert 'status="sent"' in source
        assert 'status="failed"' in source


class TestProtectedTemplatePolicy:
    """Test the protected template policy module - source code verification."""
    
    def test_protected_keys_include_reminder_family(self):
        """Verify all reminder-family templates are protected in source."""
        from pathlib import Path
        source = Path("/app/backend/utils/email_template_policy.py").read_text()
        
        expected_protected = [
            "meeting_reminder",
            "meeting_reminder_calendar",
            "booking_created",
            "booking_confirmed_host",
            "booking_confirmed_guest",
            "booking_cancelled",
            "booking_rescheduled",
            "agenda_reminder",
        ]
        
        for key in expected_protected:
            assert f'"{key}"' in source, f"'{key}' should be in PROTECTED_SUBJECT_OVERRIDE_KEYS"
    
    def test_prefix_based_protection_in_source(self):
        """Verify prefix-based protection is defined."""
        from pathlib import Path
        source = Path("/app/backend/utils/email_template_policy.py").read_text()
        
        # Check prefixes are defined
        assert '"reminder"' in source
        assert '"meeting_reminder"' in source
        assert '"booking_reminder"' in source
        
        # Check the function exists
        assert "def is_protected_subject_override_target(" in source
