"""
Feature 32 Phase-2 Write Gate Hardening Tests
Tests the new approval workflow hardening:
- Manual override endpoint with write-time policy gate
- Approval ID + expires_at requirements for approved=true
- Expired approval rejection
"""
import os
import pytest
import requests
from datetime import datetime, timezone, timedelta

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


class TestManualOverrideEndpoint:
    """Test the new /api/email-notifications/overrides/manual endpoint."""
    
    def test_manual_override_requires_admin(self, free_user_session):
        """Non-admin users should be blocked from POST /overrides/manual."""
        resp = free_user_session.post(
            f"{BASE_URL}/api/email-notifications/overrides/manual",
            json={"template_key": "test_template", "optimized_subject": "Test Subject"}
        )
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    
    def test_manual_override_requires_template_key(self, admin_session):
        """Manual override should require template_key."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/overrides/manual",
            json={"optimized_subject": "Test Subject"}
        )
        assert resp.status_code == 400, f"Expected 400 for missing template_key, got {resp.status_code}"
        data = resp.json()
        assert "template_key is required" in str(data.get("detail", ""))
    
    def test_manual_override_requires_optimized_subject(self, admin_session):
        """Manual override should require optimized_subject."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/overrides/manual",
            json={"template_key": "weekly_engagement"}
        )
        assert resp.status_code == 400, f"Expected 400 for missing optimized_subject, got {resp.status_code}"
        data = resp.json()
        assert "optimized_subject is required" in str(data.get("detail", ""))
    
    def test_manual_override_blocks_protected_template(self, admin_session):
        """Manual override should block protected templates via write-time policy gate."""
        protected_keys = [
            "meeting_reminder",
            "booking_created",
            "booking_confirmed_host",
            "agenda_reminder",
        ]
        
        for protected_key in protected_keys:
            resp = admin_session.post(
                f"{BASE_URL}/api/email-notifications/overrides/manual",
                json={"template_key": protected_key, "optimized_subject": "Test Subject"}
            )
            assert resp.status_code == 400, f"Expected 400 for protected template '{protected_key}', got {resp.status_code}"
            data = resp.json()
            assert "override blocked" in str(data.get("detail", "")).lower() or "protected" in str(data.get("detail", "")).lower(), \
                f"Expected policy block message for '{protected_key}', got: {data}"
    
    def test_manual_override_allows_non_protected_template(self, admin_session):
        """Manual override should allow non-protected templates."""
        # First, ensure the template has approval if needed
        # Use a non-protected template key
        non_protected_key = "weekly_engagement"
        
        # First approve the template for override
        admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": non_protected_key,
                "approved": True,
                "approval_id": "APR-MANUAL-TEST-001",
                "expires_at": "2099-12-31T23:59:59+00:00",
            }
        )
        
        # Now try manual override
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/overrides/manual",
            json={
                "template_key": non_protected_key,
                "optimized_subject": "Test Manual Override Subject"
            }
        )
        assert resp.status_code == 200, f"Expected 200 for non-protected template, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("template_key") == non_protected_key
        assert data.get("source") == "admin_manual_override"


class TestApprovalIDAndExpiryRequirements:
    """Test that approval_id and expires_at are required for approved=true."""
    
    def test_approval_requires_approval_id(self, admin_session):
        """Override approval with approved=true should require approval_id."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": "weekly_engagement",
                "approved": True,
                "expires_at": "2099-12-31T23:59:59+00:00",
            }
        )
        assert resp.status_code == 400, f"Expected 400 for missing approval_id, got {resp.status_code}"
        data = resp.json()
        assert "approval_id is required when approved=true" in str(data.get("detail", ""))
    
    def test_approval_requires_expires_at(self, admin_session):
        """Override approval with approved=true should require expires_at."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": "weekly_engagement",
                "approved": True,
                "approval_id": "APR-TEST-002",
            }
        )
        assert resp.status_code == 400, f"Expected 400 for missing expires_at, got {resp.status_code}"
        data = resp.json()
        assert "expires_at is required when approved=true" in str(data.get("detail", ""))
    
    def test_approval_rejects_expired_expires_at(self, admin_session):
        """Override approval should reject expires_at in the past."""
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": "weekly_engagement",
                "approved": True,
                "approval_id": "APR-TEST-003",
                "expires_at": past_time,
            }
        )
        assert resp.status_code == 400, f"Expected 400 for expired expires_at, got {resp.status_code}"
        data = resp.json()
        assert "expires_at must be in the future" in str(data.get("detail", ""))
    
    def test_rejection_does_not_require_approval_id_or_expires_at(self, admin_session):
        """Override rejection (approved=false) should NOT require approval_id or expires_at."""
        resp = admin_session.post(
            f"{BASE_URL}/api/email-notifications/template-policies/override-approval",
            json={
                "template_key": "weekly_engagement",
                "approved": False,
                "note": "Rejecting for test purposes"
            }
        )
        assert resp.status_code == 200, f"Expected 200 for rejection, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("override_approved") is False


class TestWriteGatePolicyEnforcement:
    """Test that write-time policy gate is enforced across all override writers."""
    
    def test_policy_utils_has_gate_reasons(self):
        """Verify email_template_policy defines all required gate reasons."""
        from pathlib import Path
        source = Path("/app/backend/utils/email_template_policy.py").read_text()
        
        # Check for all required gate reasons
        assert '"reason": "protected_template_blocked"' in source
        assert '"reason": "approval_required"' in source
        assert '"reason": "approval_expired"' in source
        assert '"reason": "template_key_required"' in source
    
    def test_autofix_uses_write_gate(self):
        """Verify email_autofix uses can_write_subject_override and audit_override_write."""
        from pathlib import Path
        source = Path("/app/backend/services/email_autofix.py").read_text()
        
        assert "from utils.email_template_policy import can_write_subject_override, audit_override_write" in source
        assert "allowed, gate = await can_write_subject_override(" in source
        assert "await audit_override_write(" in source
        # Check for protected template check
        assert "is_protected_subject_override_target(email_type)" in source
    
    def test_ab_testing_uses_write_gate(self):
        """Verify ab_testing uses can_write_subject_override and audit_override_write."""
        from pathlib import Path
        source = Path("/app/backend/routes/ab_testing.py").read_text()
        
        assert "from utils.email_template_policy import can_write_subject_override, audit_override_write" in source
        assert "allowed, gate = await can_write_subject_override(" in source
        assert "await audit_override_write(" in source
        # Check for policy gate block action
        assert "promotion_blocked_policy_gate" in source
    
    def test_manual_override_uses_write_gate(self):
        """Verify manual override endpoint uses can_write_subject_override and audit_override_write."""
        from pathlib import Path
        source = Path("/app/backend/routes/email_notifications.py").read_text()
        
        assert '@router.post("/overrides/manual")' in source
        assert "allowed, gate = await can_write_subject_override(" in source
        assert "await audit_override_write(" in source
        assert "override blocked:" in source


class TestAuditTrailLogging:
    """Test that audit trail is properly logged for override writes."""
    
    def test_audit_override_write_function_exists(self):
        """Verify audit_override_write function is defined with correct signature."""
        from pathlib import Path
        source = Path("/app/backend/utils/email_template_policy.py").read_text()
        
        assert "async def audit_override_write(" in source
        assert "template_key: str" in source
        assert "actor: str" in source
        assert "source: str" in source
        assert "approved: bool" in source
        assert "reason: str" in source
        assert "metadata: dict" in source
        # Check it writes to audit log collection
        assert "email_override_audit_log" in source
    
    def test_autofix_logs_audit_for_blocked_and_allowed(self):
        """Verify autofix logs audit for both blocked and allowed overrides."""
        from pathlib import Path
        source = Path("/app/backend/services/email_autofix.py").read_text()
        
        # Check for audit logging on blocked
        assert 'approved=False' in source
        assert 'reason="protected_template_blocked"' in source
        # Check for audit logging on allowed
        assert 'approved=True' in source
        assert 'reason="policy_gate_pass"' in source
    
    def test_ab_testing_logs_audit_for_blocked_and_allowed(self):
        """Verify AB testing logs audit for both blocked and allowed promotions."""
        from pathlib import Path
        source = Path("/app/backend/routes/ab_testing.py").read_text()
        
        # Check for audit logging on blocked
        assert 'approved=False' in source
        assert 'reason="protected_template_blocked"' in source
        # Check for audit logging on allowed
        assert 'approved=True' in source
        assert 'reason="policy_gate_pass"' in source
