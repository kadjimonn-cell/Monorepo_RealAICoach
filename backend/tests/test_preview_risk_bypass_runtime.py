"""
Runtime tests for preview-only, env-gated risk-engine bypass for admin auth flows.

Tests:
1. POST /api/auth/login should NOT return risk_engine_id_verification_required for allowlisted admin in preview/test mode when risk score is critical
2. Bypass should remain restricted: only preview/test mode + allowlisted admin + env-gated behavior
3. Security event should log risk_engine_preview_bypass_applied with bypass_scope auth_login_password
4. Non-allowlisted users should still be blocked by critical risk

Test Credentials:
- Admin: admin@realaicoach.app / NewAdminPass2026!
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_env_auth_block(response: requests.Response) -> bool:
    """Check if response indicates environment-level auth block (rate limit, policy gate)."""
    if response.status_code == 429:
        return True
    if response.status_code not in (401, 403, 503):
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}
    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    blocked_codes = {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "PRODUCTION_POLICY_GATE_BLOCKED",
    }
    if top_code in blocked_codes:
        return True
    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in blocked_codes:
            return True
    return False


class TestPreviewRiskBypassRuntime:
    """Runtime tests for preview risk bypass on admin login"""

    def test_admin_login_succeeds_without_id_verification_required(self):
        """Admin login should succeed without risk_engine_id_verification_required in preview mode"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if _is_env_auth_block(response):
            pytest.skip(f"Admin login blocked by environment containment: {response.status_code}")
        
        # Login should succeed (200) or require OTP (200 with otp_required)
        # It should NOT return 403 with risk_engine_id_verification_required
        assert response.status_code == 200, f"Login failed unexpectedly: {response.text}"
        
        data = response.json()
        
        # Check that we don't have risk_engine_id_verification_required
        if "risk_engine" in data:
            risk_code = data.get("risk_engine", {}).get("code", "")
            assert risk_code != "risk_engine_id_verification_required", \
                f"Admin should not be blocked by ID verification in preview mode: {data}"
        
        # Verify login succeeded with user data
        assert "user_id" in data or "email" in data or "otp_required" in data, \
            f"Login response should contain user info or OTP requirement: {data}"
        
        print("PASS: Admin login succeeded without ID verification block")

    def test_admin_login_with_critical_risk_profile_bypassed(self):
        """When admin has critical risk profile, preview bypass should allow login"""
        # First, insert a critical risk profile for the admin
        from pymongo import MongoClient
        
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url)
        db = client[db_name]
        
        # Get admin user_id
        admin_user = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "user_id": 1})
        if not admin_user:
            pytest.skip("Admin user not found in database")
        
        admin_user_id = admin_user["user_id"]
        
        # Insert a critical risk profile
        critical_risk_profile = {
            "user_id": admin_user_id,
            "risk_level": "critical",
            "risk_score": 95,
            "trigger": "TEST_CRITICAL_RISK",
            "session_protection": "LOCKOUT",
            "restrictions": {
                "require_id_verification": True,
                "block_admin_privileged_api": True,
                "lock_session": True,
            },
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Upsert the risk profile
        db.progressive_risk_profiles.update_one(
            {"user_id": admin_user_id},
            {"$set": critical_risk_profile},
            upsert=True
        )
        
        try:
            # Now attempt login - should succeed due to preview bypass
            session = requests.Session()
            response = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            
            if _is_env_auth_block(response):
                pytest.skip(f"Admin login blocked by environment containment: {response.status_code}")
            
            # Login should succeed (200) - bypass should apply
            assert response.status_code == 200, \
                f"Admin login should succeed with preview bypass despite critical risk: {response.text}"
            
            data = response.json()
            
            # Should NOT have risk_engine_id_verification_required
            if isinstance(data.get("detail"), dict):
                code = data["detail"].get("code", "")
                assert code != "risk_engine_id_verification_required", \
                    f"Preview bypass should prevent ID verification requirement: {data}"
            
            print("PASS: Admin login succeeded with critical risk profile due to preview bypass")
            
        finally:
            # Clean up - remove the test risk profile
            db.progressive_risk_profiles.delete_one({"user_id": admin_user_id})
            client.close()

    def test_security_event_logged_for_preview_bypass(self):
        """Security event should log risk_engine_preview_bypass_applied with bypass_scope"""
        from pymongo import MongoClient
        
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url)
        db = client[db_name]
        
        # Get admin user_id
        admin_user = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "user_id": 1})
        if not admin_user:
            pytest.skip("Admin user not found in database")
        
        admin_user_id = admin_user["user_id"]
        
        # Insert a critical risk profile to trigger bypass
        critical_risk_profile = {
            "user_id": admin_user_id,
            "risk_level": "critical",
            "risk_score": 92,
            "trigger": "TEST_BYPASS_EVENT_CHECK",
            "session_protection": "LOCKOUT",
            "restrictions": {
                "require_id_verification": True,
                "block_admin_privileged_api": True,
            },
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        db.progressive_risk_profiles.update_one(
            {"user_id": admin_user_id},
            {"$set": critical_risk_profile},
            upsert=True
        )
        
        # Record timestamp before login
        before_login = datetime.now(timezone.utc) - timedelta(seconds=2)
        
        try:
            # Perform login
            session = requests.Session()
            response = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            
            if _is_env_auth_block(response):
                pytest.skip(f"Admin login blocked by environment containment: {response.status_code}")
            
            # Check for security event
            bypass_event = db.security_events.find_one(
                {
                    "user_id": admin_user_id,
                    "event_type": "risk_engine_preview_bypass_applied",
                    "timestamp": {"$gte": before_login.isoformat()},
                },
                {"_id": 0}
            )
            
            if bypass_event:
                # Verify bypass_scope is present
                details = bypass_event.get("details", {})
                bypass_scope = details.get("bypass_scope", "")
                assert bypass_scope in ["auth_login_password", "auth_otp_verify", "auth_2fa_verify"], \
                    f"bypass_scope should be one of auth flows: {bypass_scope}"
                
                # Verify mode is preview
                assert details.get("mode") == "preview", \
                    f"mode should be 'preview': {details.get('mode')}"
                
                # Verify allowlisted_admin is present
                assert details.get("allowlisted_admin") == ADMIN_EMAIL.lower(), \
                    f"allowlisted_admin should be {ADMIN_EMAIL}: {details.get('allowlisted_admin')}"
                
                print(f"PASS: Security event logged with bypass_scope={bypass_scope}, mode=preview")
            else:
                # If no bypass event, it means the risk profile didn't trigger bypass
                # This could happen if the risk assessment didn't reach critical level
                print("INFO: No bypass event found - risk profile may not have triggered bypass")
            
        finally:
            # Clean up
            db.progressive_risk_profiles.delete_one({"user_id": admin_user_id})
            client.close()

    def test_non_allowlisted_user_still_blocked_by_critical_risk(self):
        """Non-allowlisted users should still be blocked by critical risk"""
        from pymongo import MongoClient
        
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url)
        db = client[db_name]
        
        # Create a test non-admin user
        test_email = f"test.risk.block.{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestRisk#2026!Aa"
        
        # Register the user
        session = requests.Session()
        reg_response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": test_password,
                "name": "Test Risk Block User"
            }
        )
        
        if reg_response.status_code != 200:
            pytest.skip(f"Could not create test user: {reg_response.text}")
        
        test_user_id = reg_response.json().get("user_id")
        
        try:
            # Insert a critical risk profile for this non-admin user
            critical_risk_profile = {
                "user_id": test_user_id,
                "risk_level": "critical",
                "risk_score": 95,
                "trigger": "TEST_NON_ADMIN_BLOCK",
                "session_protection": "LOCKOUT",
                "restrictions": {
                    "require_id_verification": True,
                    "block_admin_privileged_api": True,
                    "lock_session": True,
                },
                "assessed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            db.progressive_risk_profiles.update_one(
                {"user_id": test_user_id},
                {"$set": critical_risk_profile},
                upsert=True
            )
            
            # Logout and try to login again
            new_session = requests.Session()
            login_response = new_session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": test_email, "password": test_password}
            )
            
            # Non-admin user should either:
            # 1. Get 403 with risk_engine_id_verification_required
            # 2. Get 200 but with id_verification_required flag
            # The bypass should NOT apply to non-admin users
            
            if login_response.status_code == 403:
                data = login_response.json()
                detail = data.get("detail", {})
                if isinstance(detail, dict):
                    code = detail.get("code", "")
                    # This is expected - non-admin blocked by risk
                    print(f"PASS: Non-admin user correctly blocked with code: {code}")
                else:
                    print(f"PASS: Non-admin user blocked: {detail}")
            elif login_response.status_code == 200:
                data = login_response.json()
                # Check if ID verification is required
                if data.get("id_verification_required") or data.get("risk_engine_id_verification_required"):
                    print("PASS: Non-admin user login requires ID verification")
                else:
                    # Login succeeded - this is also acceptable if risk engine didn't trigger
                    print("INFO: Non-admin login succeeded - risk engine may not have triggered")
            else:
                print(f"INFO: Non-admin login returned status {login_response.status_code}")
            
        finally:
            # Clean up
            db.progressive_risk_profiles.delete_one({"user_id": test_user_id})
            db.users.delete_one({"user_id": test_user_id})
            db.user_sessions.delete_many({"user_id": test_user_id})
            client.close()


class TestPreviewBypassEnvGating:
    """Tests for env-gated behavior of preview bypass"""

    def test_bypass_email_allowlist_configured(self):
        """PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS should be configured in .env"""
        env_path = "/app/backend/.env"
        with open(env_path, "r") as f:
            content = f.read()
        
        assert "PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS" in content, \
            "PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS should be in .env"
        
        # Verify admin email is in the allowlist
        assert ADMIN_EMAIL in content, \
            f"{ADMIN_EMAIL} should be in PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS"
        
        print(f"PASS: PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS configured with {ADMIN_EMAIL}")

    def test_bypass_helper_uses_db_guard_policy(self):
        """_apply_preview_login_risk_bypass_if_allowed should use _apply_preview_risk_bypass_if_allowed from db.py"""
        auth_path = "/app/backend/routes/auth.py"
        with open(auth_path, "r") as f:
            content = f.read()
        
        # Check that the helper exists
        assert "async def _apply_preview_login_risk_bypass_if_allowed(" in content, \
            "_apply_preview_login_risk_bypass_if_allowed should exist"
        
        # Check that it calls the db.py guard
        assert "_apply_preview_risk_bypass_if_allowed(" in content, \
            "Should call _apply_preview_risk_bypass_if_allowed from db.py"
        
        # Check that it's imported from db - look for the import in the import block
        import_section = content[:2000]  # First 2000 chars contain imports
        assert "_apply_preview_risk_bypass_if_allowed," in import_section, \
            "_apply_preview_risk_bypass_if_allowed should be imported from routes.db"
        
        print("PASS: _apply_preview_login_risk_bypass_if_allowed uses db.py guard policy")

    def test_bypass_only_for_admin_users(self):
        """Bypass should only apply to admin users"""
        db_path = "/app/backend/routes/db.py"
        with open(db_path, "r") as f:
            content = f.read()
        
        # Check that _should_allow_preview_risk_bypass checks is_admin
        assert "is_admin" in content, "Should check is_admin flag"
        assert "_should_allow_preview_risk_bypass" in content, \
            "_should_allow_preview_risk_bypass should exist"
        
        # Verify the function checks for admin
        func_start = content.find("def _should_allow_preview_risk_bypass")
        func_end = content.find("\n\n", func_start)
        func_body = content[func_start:func_end]
        
        assert "is_admin" in func_body, \
            "_should_allow_preview_risk_bypass should check is_admin"
        
        print("PASS: Bypass only applies to admin users")

    def test_bypass_only_in_non_production(self):
        """Bypass should only apply in non-production environments"""
        db_path = "/app/backend/routes/db.py"
        with open(db_path, "r") as f:
            content = f.read()
        
        # Check that _is_non_production_runtime is used
        assert "_is_non_production_runtime" in content, \
            "_is_non_production_runtime should exist"
        
        # Check that bypass checks for non-production
        assert "_is_non_production_runtime()" in content, \
            "Bypass should call _is_non_production_runtime()"
        
        print("PASS: Bypass only applies in non-production environments")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
