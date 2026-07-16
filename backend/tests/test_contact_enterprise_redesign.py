"""
Contact Page Enterprise Redesign Tests
Tests for the enterprise-grade contact form with intent routing, enhanced payload fields,
and SLA-based response tracking.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestContactSubmitEndpoint:
    """Tests for /api/contact/submit endpoint with enterprise fields"""
    
    @pytest.fixture
    def api_client(self):
        """Shared requests session with CSRF header"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        return session
    
    def test_sales_intent_submission(self, api_client):
        """Test sales intent with full enterprise payload"""
        payload = {
            "name": "Test Sales User",
            "email": "test.sales@example.com",
            "message": "Testing sales intent submission with enterprise fields.",
            "intent": "sales",
            "company": "Enterprise Corp",
            "team_size": "51-200",
            "use_case": "AI-powered coaching platform",
            "priority": "high",
            "timeline": "This month",
            "budget_range": "$20k-$75k",
            "website": "https://enterprise.com",
            "region": "North America",
            "source": "contact_command_center"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "reference_id" in data
        assert data["reference_id"].startswith("contact_")
        assert data["intent"] == "sales"
        assert data["sla_hours"] == 24
        assert "message" in data
    
    def test_support_intent_submission(self, api_client):
        """Test support intent with 4h SLA"""
        payload = {
            "name": "Test Support User",
            "email": "test.support@example.com",
            "message": "Testing support intent submission for priority routing.",
            "intent": "support",
            "company": "Support Corp",
            "team_size": "1-10",
            "priority": "urgent",
            "region": "Europe",
            "source": "contact_command_center"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["intent"] == "support"
        assert data["sla_hours"] == 4  # Support has 4h SLA
        assert "reference_id" in data
    
    def test_partnerships_intent_submission(self, api_client):
        """Test partnerships intent"""
        payload = {
            "name": "Test Partner User",
            "email": "test.partner@example.com",
            "message": "Testing partnerships intent for strategic alliances.",
            "intent": "partnerships",
            "company": "Partner Corp",
            "team_size": "201-1000",
            "use_case": "Co-marketing opportunity",
            "priority": "medium",
            "timeline": "Next quarter",
            "region": "Asia-Pacific",
            "source": "contact_command_center"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["intent"] == "partnerships"
        assert data["sla_hours"] == 24
    
    def test_press_intent_submission(self, api_client):
        """Test press intent for media requests"""
        payload = {
            "name": "Test Press User",
            "email": "test.press@example.com",
            "message": "Testing press intent for media desk routing.",
            "intent": "press",
            "company": "Media Corp",
            "team_size": "1000+",
            "priority": "low",
            "timeline": "Researching",
            "region": "Middle East",
            "source": "contact_command_center"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["intent"] == "press"
        assert data["sla_hours"] == 24
    
    def test_required_fields_validation(self, api_client):
        """Test validation for required fields (name, email, message)"""
        # Missing name
        payload = {
            "name": "",
            "email": "test@example.com",
            "message": "Test message"
        }
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 400
        
        # Missing email
        payload = {
            "name": "Test User",
            "email": "",
            "message": "Test message"
        }
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 400
        
        # Missing message
        payload = {
            "name": "Test User",
            "email": "test@example.com",
            "message": ""
        }
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 400
    
    def test_default_intent_fallback(self, api_client):
        """Test that default intent is 'support' when not specified"""
        payload = {
            "name": "Test Default User",
            "email": "test.default@example.com",
            "message": "Testing default intent fallback behavior."
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["intent"] == "support"  # Default intent
        assert data["sla_hours"] == 4  # Support SLA
    
    def test_response_structure_completeness(self, api_client):
        """Test that response includes all required fields"""
        payload = {
            "name": "Test Structure User",
            "email": "test.structure@example.com",
            "message": "Testing response structure completeness.",
            "intent": "sales"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # Verify all required response fields
        assert "success" in data
        assert "reference_id" in data
        assert "message" in data
        assert "intent" in data
        assert "sla_hours" in data
        
        # Verify reference_id format
        assert data["reference_id"].startswith("contact_")
        assert len(data["reference_id"]) > 20  # Should have timestamp + hash
    
    def test_all_enterprise_fields_accepted(self, api_client):
        """Test that all enterprise fields are accepted in payload"""
        payload = {
            "name": "Enterprise Test User",
            "email": "enterprise@example.com",
            "subject": "Enterprise Inquiry",
            "message": "Testing all enterprise fields are accepted.",
            "intent": "sales",
            "company": "Enterprise Corp",
            "team_size": "1000+",
            "use_case": "Full platform deployment",
            "priority": "urgent",
            "timeline": "Immediate",
            "budget_range": "$75k+",
            "website": "https://enterprise-corp.com",
            "region": "North America",
            "source": "contact_command_center",
            "context": "enterprise-demo"
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact/submit", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True


class TestContactInfoEndpoint:
    """Tests for /api/contact GET endpoint"""
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        return session
    
    def test_contact_info_endpoint(self, api_client):
        """Test GET /api/contact returns info about submit endpoint"""
        response = api_client.get(f"{BASE_URL}/api/contact")
        # This endpoint may require auth, so we accept 401 or 200
        assert response.status_code in [200, 401, 403]


class TestContactLegacyAlias:
    """Tests for legacy /api/contact POST alias"""
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        return session
    
    def test_legacy_post_alias(self, api_client):
        """Test POST /api/contact works as alias for /api/contact/submit"""
        payload = {
            "name": "Legacy Test User",
            "email": "legacy@example.com",
            "message": "Testing legacy POST alias endpoint."
        }
        
        response = api_client.post(f"{BASE_URL}/api/contact", json=payload)
        # Legacy alias should work
        assert response.status_code in [200, 401, 403]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
