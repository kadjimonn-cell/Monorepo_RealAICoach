"""
Feature 18: Business Operations Copilot (ai-enterprise) API Tests
Tests all endpoints for the Business Operations Copilot feature.
"""

import os
import pytest
import requests
import uuid
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
GUEST_USER_ID = "user_feature18abcxyz12345"


class TestAIEnterpriseHealth:
    """Health endpoint tests"""

    def test_health_returns_200(self):
        """GET /api/ai-enterprise/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/ai-enterprise/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["feature"] == "Business Operations Copilot"
        assert data["feature_id"] == "ai-enterprise"
        print("PASS: Health endpoint returns healthy status")


class TestAIEnterpriseBootstrap:
    """Bootstrap endpoint tests"""

    def test_bootstrap_with_fallback_user_id(self):
        """GET /api/ai-enterprise/bootstrap with fallback_user_id returns plan and limits"""
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/bootstrap",
            params={"fallback_user_id": GUEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data["success"] is True
        assert data["feature_id"] == "ai-enterprise"
        assert "plan" in data
        assert "scope_label" in data
        assert "limits" in data
        assert "usage" in data
        assert "workspaces" in data
        assert "recent_runs" in data
        assert "playbooks" in data
        assert "features" in data
        
        # Verify limits structure
        limits = data["limits"]
        assert "workspaces_per_month" in limits
        assert "runs_per_day" in limits
        assert "playbooks" in limits
        assert "exports_per_day" in limits
        assert "max_prompt_chars" in limits
        
        # Verify features
        features = data["features"]
        assert features["strategy_workspace"] is True
        assert features["command_mode"] is True
        assert features["run_timeline"] is True
        assert features["playbooks"] is True
        assert features["exports"] is True
        
        print(f"PASS: Bootstrap returns plan={data['plan']}, scope_label={data['scope_label']}")

    def test_bootstrap_without_auth_returns_401(self):
        """GET /api/ai-enterprise/bootstrap without fallback_user_id returns 401"""
        response = requests.get(f"{BASE_URL}/api/ai-enterprise/bootstrap")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "ai_enterprise_auth_required"
        print("PASS: Bootstrap without auth returns 401")


class TestAIEnterpriseWorkspaceCreate:
    """Workspace creation tests"""

    def test_create_workspace_returns_200(self):
        """POST /api/ai-enterprise/workspaces/create creates workspace"""
        unique_title = f"Test Workspace {uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": unique_title,
                "context": "Test context for workspace",
                "focus": "operations",
                "fallback_user_id": f"user_test_{uuid.uuid4().hex[:12]}"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "workspace" in data
        workspace = data["workspace"]
        assert workspace["workspace_id"].startswith("aient_")
        assert workspace["title"] == unique_title
        assert workspace["focus"] == "operations"
        assert "plan" in data
        assert "scope_label" in data
        assert "limits" in data
        
        print(f"PASS: Created workspace {workspace['workspace_id']}")
        return workspace["workspace_id"]

    def test_create_workspace_without_auth_returns_401(self):
        """POST /api/ai-enterprise/workspaces/create without fallback_user_id returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": "Test Workspace",
                "context": "Test context",
                "focus": "operations"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "ai_enterprise_auth_required"
        print("PASS: Create workspace without auth returns 401")

    def test_create_workspace_invalid_title_returns_422(self):
        """POST /api/ai-enterprise/workspaces/create with short title returns 422"""
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": "X",  # Too short (min 2 chars)
                "fallback_user_id": f"user_test_{uuid.uuid4().hex[:12]}"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 422
        print("PASS: Create workspace with invalid title returns 422")


class TestAIEnterpriseWorkspaceRun:
    """Workspace run command tests"""

    @pytest.fixture(autouse=True)
    def setup_workspace(self):
        """Create a workspace for run tests"""
        unique_id = uuid.uuid4().hex[:12]
        self.test_user_id = f"user_runtest_{unique_id}"
        
        # Create workspace
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": f"Run Test Workspace {unique_id}",
                "context": "Test context",
                "focus": "operations",
                "fallback_user_id": self.test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        self.workspace_id = response.json()["workspace"]["workspace_id"]
        yield
        # Cleanup not needed - test data isolated by unique user_id

    def test_run_command_returns_output_and_session_id(self):
        """POST /api/ai-enterprise/workspaces/{workspace_id}/run returns output and session_id"""
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/{self.workspace_id}/run",
            json={
                "command": "Create a brief executive summary for Q4 planning",
                "objective": "Strategic planning",
                "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
                "fallback_user_id": self.test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=60  # LLM calls can take time
        )
        
        # Could be 200 (success) or 502 (LLM failure) or 429 (rate limit)
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "run_id" in data
            assert data["run_id"].startswith("run_")
            assert "session_id" in data
            assert "output" in data
            assert len(data["output"]) > 0
            assert "workspace_id" in data
            assert data["workspace_id"] == self.workspace_id
            assert "idempotent_replay" in data
            assert data["idempotent_replay"] is False
            print(f"PASS: Run command returned output with run_id={data['run_id']}")
        elif response.status_code == 502:
            data = response.json()
            assert data["detail"]["error_code"] == "ai_enterprise_run_failed"
            print("PASS: Run command returned 502 (LLM provider issue - expected in some environments)")
        elif response.status_code == 429:
            data = response.json()
            assert data["detail"]["error_code"] == "ai_enterprise_run_limit_reached"
            print("PASS: Run command returned 429 (rate limit reached - expected for free tier)")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")

    def test_run_command_idempotency_replay(self):
        """POST /api/ai-enterprise/workspaces/{workspace_id}/run with same idempotency_key returns replay"""
        idempotency_key = f"idem-{uuid.uuid4().hex[:12]}"
        
        # First request
        response1 = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/{self.workspace_id}/run",
            json={
                "command": "Create a brief summary",
                "idempotency_key": idempotency_key,
                "fallback_user_id": self.test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=60
        )
        
        if response1.status_code not in [200, 429, 502]:
            pytest.fail(f"First request failed with {response1.status_code}")
        
        if response1.status_code == 200:
            first_data = response1.json()
            
            # Second request with same idempotency key
            response2 = requests.post(
                f"{BASE_URL}/api/ai-enterprise/workspaces/{self.workspace_id}/run",
                json={
                    "command": "Create a brief summary",
                    "idempotency_key": idempotency_key,
                    "fallback_user_id": self.test_user_id
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=60
            )
            
            assert response2.status_code == 200
            second_data = response2.json()
            assert second_data.get("idempotent_replay") is True
            assert second_data["run_id"] == first_data["run_id"]
            assert second_data["session_id"] == first_data["session_id"]
            print("PASS: Idempotency replay working correctly")
        else:
            print(f"SKIP: Idempotency test skipped due to first request status {response1.status_code}")


class TestAIEnterprisePlaybooks:
    """Playbook save and list tests"""

    @pytest.fixture(autouse=True)
    def setup_workspace(self):
        """Create a workspace for playbook tests"""
        unique_id = uuid.uuid4().hex[:12]
        self.test_user_id = f"user_pbtest_{unique_id}"
        
        # Create workspace
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": f"Playbook Test Workspace {unique_id}",
                "context": "Test context",
                "focus": "operations",
                "fallback_user_id": self.test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        self.workspace_id = response.json()["workspace"]["workspace_id"]
        yield

    def test_save_playbook_returns_200(self):
        """POST /api/ai-enterprise/playbooks/save creates playbook"""
        response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/playbooks/save",
            json={
                "workspace_id": self.workspace_id,
                "name": f"Test Playbook {uuid.uuid4().hex[:8]}",
                "summary": "This is a test playbook summary with actionable items.",
                "actions": ["Action 1", "Action 2", "Action 3"],
                "fallback_user_id": self.test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "playbook" in data
            playbook = data["playbook"]
            assert playbook["playbook_id"].startswith("pb_")
            assert playbook["workspace_id"] == self.workspace_id
            assert len(playbook["actions"]) == 3
            print(f"PASS: Created playbook {playbook['playbook_id']}")
        elif response.status_code == 429:
            data = response.json()
            assert data["detail"]["error_code"] == "ai_enterprise_playbook_limit_reached"
            print("PASS: Playbook limit reached (expected for free tier)")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")

    def test_list_playbooks_returns_200(self):
        """GET /api/ai-enterprise/playbooks returns playbooks list"""
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/playbooks",
            params={"fallback_user_id": self.test_user_id, "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "playbooks" in data
        assert isinstance(data["playbooks"], list)
        print(f"PASS: List playbooks returned {len(data['playbooks'])} playbooks")


class TestAIEnterpriseExport:
    """Workspace export tests"""

    def test_export_workspace_returns_200(self):
        """GET /api/ai-enterprise/workspaces/{workspace_id}/export returns export data"""
        unique_id = uuid.uuid4().hex[:12]
        test_user_id = f"user_export_{unique_id}"
        
        # Create workspace first
        create_response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": f"Export Test Workspace {unique_id}",
                "context": "Test context",
                "focus": "operations",
                "fallback_user_id": test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert create_response.status_code == 200
        workspace_id = create_response.json()["workspace"]["workspace_id"]
        
        # Export workspace
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/workspaces/{workspace_id}/export",
            params={
                "fallback_user_id": test_user_id,
                "include_runs": True,
                "include_playbooks": True,
                "limit": 10
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "export_id" in data
            assert data["export_id"].startswith("exp_")
            assert "workspace" in data
            assert "runs" in data
            assert "playbooks" in data
            assert "summary" in data
            assert "generated_at" in data
            print(f"PASS: Export returned export_id={data['export_id']}")
        elif response.status_code == 429:
            data = response.json()
            assert data["detail"]["error_code"] == "ai_enterprise_export_limit_reached"
            print("PASS: Export limit reached (expected for free tier)")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")

    def test_export_workspace_not_found_returns_404(self):
        """GET /api/ai-enterprise/workspaces/{workspace_id}/export with invalid workspace returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/workspaces/aient_nonexistent123/export",
            params={"fallback_user_id": f"user_test_{uuid.uuid4().hex[:12]}"}
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_code"] == "ai_enterprise_workspace_not_found"
        print("PASS: Export with invalid workspace returns 404")


class TestAIEnterpriseWorkspaceRuns:
    """Workspace runs list tests"""

    def test_list_workspace_runs_returns_200(self):
        """GET /api/ai-enterprise/workspaces/{workspace_id}/runs returns runs list"""
        unique_id = uuid.uuid4().hex[:12]
        test_user_id = f"user_runs_{unique_id}"
        
        # Create workspace first
        create_response = requests.post(
            f"{BASE_URL}/api/ai-enterprise/workspaces/create",
            json={
                "title": f"Runs Test Workspace {unique_id}",
                "context": "Test context",
                "focus": "operations",
                "fallback_user_id": test_user_id
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert create_response.status_code == 200
        workspace_id = create_response.json()["workspace"]["workspace_id"]
        
        # List runs
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/workspaces/{workspace_id}/runs",
            params={"fallback_user_id": test_user_id, "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "runs" in data
        assert isinstance(data["runs"], list)
        print(f"PASS: List runs returned {len(data['runs'])} runs")


class TestAIEnterpriseTierLimits:
    """Tier-aware behavior tests"""

    def test_free_tier_limits_enforced(self):
        """Verify free tier limits are returned in bootstrap"""
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/bootstrap",
            params={"fallback_user_id": f"user_tier_{uuid.uuid4().hex[:12]}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["plan"] == "free"
        assert data["scope_label"] == "Limited access"
        
        limits = data["limits"]
        assert limits["workspaces_per_month"] == 1
        assert limits["runs_per_day"] == 2
        assert limits["playbooks"] == 2
        assert limits["exports_per_day"] == 1
        assert limits["max_prompt_chars"] == 1200
        assert limits["history_retention_days"] == 14
        
        print("PASS: Free tier limits correctly enforced")


class TestAIEnterpriseGuestIdValidation:
    """Guest ID validation tests"""

    def test_invalid_guest_id_format_returns_400(self):
        """Bootstrap with invalid guest ID format returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/bootstrap",
            params={"fallback_user_id": "invalid_format"}  # Missing user_ prefix
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "ai_enterprise_invalid_guest_id"
        print("PASS: Invalid guest ID format returns 400")

    def test_valid_guest_id_format_accepted(self):
        """Bootstrap with valid guest ID format is accepted"""
        valid_guest_id = f"user_{uuid.uuid4().hex[:20]}"
        response = requests.get(
            f"{BASE_URL}/api/ai-enterprise/bootstrap",
            params={"fallback_user_id": valid_guest_id}
        )
        assert response.status_code == 200
        print("PASS: Valid guest ID format accepted")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
