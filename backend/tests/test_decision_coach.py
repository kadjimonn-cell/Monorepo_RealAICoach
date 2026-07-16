"""
Feature 5: Decision Coach API Tests
Tests for /api/decision-coach/* endpoints
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test user ID for guest path
TEST_USER_ID = f"user_test_dc_{int(time.time())}"


class TestDecisionCoachBootstrap:
    """Bootstrap endpoint tests"""
    
    def test_bootstrap_returns_usage_and_templates(self):
        """GET /api/decision-coach/bootstrap returns usage info and templates"""
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/bootstrap",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "owner_id" in data
        assert "tier" in data
        assert "usage" in data
        assert "templates" in data
        assert "stats" in data
        
        # Verify usage info
        usage = data["usage"]
        assert "can_create" in usage
        assert "monthly_limit" in usage
        assert "frameworks_available" in usage
        
        # Free tier should have pros_cons framework
        assert "pros_cons" in usage["frameworks_available"]
        
        # Verify templates exist
        assert len(data["templates"]) >= 3  # At least 3 free templates


class TestDecisionCoachCRUD:
    """Decision CRUD operation tests"""
    
    def test_create_decision_success(self):
        """POST /api/decision-coach/decisions creates a new decision"""
        response = requests.post(
            f"{BASE_URL}/api/decision-coach/decisions",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "title": "TEST_Decision_Create",
                "description": "Testing decision creation",
                "framework_type": "pros_cons",
                "fallback_user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "decision_id" in data
        assert data["title"] == "TEST_Decision_Create"
        assert data["framework_type"] == "pros_cons"
        assert data["status"] == "draft"
        
        # Store for cleanup
        TestDecisionCoachCRUD.created_decision_id = data["decision_id"]
    
    def test_list_decisions(self):
        """GET /api/decision-coach/decisions lists user's decisions"""
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/decisions",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "decisions" in data
        assert isinstance(data["decisions"], list)
    
    def test_get_decision_by_id(self):
        """GET /api/decision-coach/decisions/{id} returns decision details"""
        decision_id = getattr(TestDecisionCoachCRUD, 'created_decision_id', None)
        if not decision_id:
            pytest.skip("No decision created to get")
        
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/decisions/{decision_id}",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["decision_id"] == decision_id
        assert data["title"] == "TEST_Decision_Create"
    
    def test_update_decision(self):
        """PUT /api/decision-coach/decisions/{id} updates decision"""
        decision_id = getattr(TestDecisionCoachCRUD, 'created_decision_id', None)
        if not decision_id:
            pytest.skip("No decision created to update")
        
        response = requests.put(
            f"{BASE_URL}/api/decision-coach/decisions/{decision_id}",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "title": "TEST_Decision_Updated",
                "framework_data": {
                    "options": [
                        {
                            "option_id": "opt0",
                            "name": "Option A",
                            "pros": [{"item_id": "pro_1", "text": "Good salary", "weight": 5}],
                            "cons": [],
                            "score": 50
                        }
                    ]
                },
                "fallback_user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["title"] == "TEST_Decision_Updated"
        assert "framework_data" in data
        assert "options" in data["framework_data"]
    
    def test_delete_decision(self):
        """DELETE /api/decision-coach/decisions/{id} deletes decision"""
        decision_id = getattr(TestDecisionCoachCRUD, 'created_decision_id', None)
        if not decision_id:
            pytest.skip("No decision created to delete")
        
        response = requests.delete(
            f"{BASE_URL}/api/decision-coach/decisions/{decision_id}",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"]
        
        # Verify deletion
        get_response = requests.get(
            f"{BASE_URL}/api/decision-coach/decisions/{decision_id}",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert get_response.status_code == 404


class TestDecisionCoachTemplates:
    """Template-related tests"""
    
    def test_list_templates(self):
        """GET /api/decision-coach/templates returns available templates"""
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/templates",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "templates" in data
        assert "tier" in data
        assert len(data["templates"]) >= 3  # At least 3 free templates
        
        # Verify template structure
        template = data["templates"][0]
        assert "template_id" in template
        assert "name" in template
        assert "framework_type" in template
        assert "tier_requirement" in template
    
    def test_create_from_template(self):
        """POST /api/decision-coach/decisions/from-template creates decision from template"""
        response = requests.post(
            f"{BASE_URL}/api/decision-coach/decisions/from-template",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "template_id": "tmpl_career_change",
                "fallback_user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "decision" in data
        decision = data["decision"]
        assert decision["title"] == "Career Change Decision"
        assert decision["framework_type"] == "pros_cons"
        
        # Should have preset options from template
        assert "framework_data" in decision
        assert "options" in decision["framework_data"]
        assert len(decision["framework_data"]["options"]) == 2
        
        # Store for cleanup
        TestDecisionCoachTemplates.template_decision_id = decision["decision_id"]
    
    def test_cleanup_template_decision(self):
        """Cleanup: Delete template-created decision"""
        decision_id = getattr(TestDecisionCoachTemplates, 'template_decision_id', None)
        if not decision_id:
            pytest.skip("No template decision to cleanup")
        
        response = requests.delete(
            f"{BASE_URL}/api/decision-coach/decisions/{decision_id}",
            params={"fallback_user_id": TEST_USER_ID},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200


class TestDecisionCoachAnalytics:
    """Analytics endpoint tests"""
    
    def test_get_analytics(self):
        """GET /api/decision-coach/analytics returns analytics data"""
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/analytics",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify analytics structure
        assert "total_decisions" in data
        assert "decisions_this_month" in data
        assert "avg_confidence_score" in data
        assert "success_rate" in data
        assert "framework_usage" in data


class TestDecisionCoachEdgeCases:
    """Edge case and error handling tests"""
    
    def test_create_without_title_fails(self):
        """POST /api/decision-coach/decisions without title should fail"""
        response = requests.post(
            f"{BASE_URL}/api/decision-coach/decisions",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "description": "No title provided",
                "framework_type": "pros_cons",
                "fallback_user_id": TEST_USER_ID
            }
        )
        # Should fail validation
        assert response.status_code in [400, 422]
    
    def test_get_nonexistent_decision_returns_404(self):
        """GET /api/decision-coach/decisions/{invalid_id} returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/decision-coach/decisions/dec_nonexistent123",
            params={"fallback_user_id": TEST_USER_ID}
        )
        assert response.status_code == 404
    
    def test_invalid_framework_type_fails(self):
        """POST with invalid framework_type should fail"""
        response = requests.post(
            f"{BASE_URL}/api/decision-coach/decisions",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "title": "TEST_Invalid_Framework",
                "framework_type": "invalid_framework",
                "fallback_user_id": TEST_USER_ID
            }
        )
        # Should fail - invalid framework
        assert response.status_code in [400, 403, 422]
    
    def test_invalid_template_id_returns_404(self):
        """POST /api/decision-coach/decisions/from-template with invalid template returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/decision-coach/decisions/from-template",
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            json={
                "template_id": "tmpl_nonexistent",
                "fallback_user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
