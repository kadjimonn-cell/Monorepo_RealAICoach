"""
P3 API Refactor Regression Tests
Tests for features 10, 11, 12 after fetch->api.ts migration:
- Feature 10: Smart Shopping Advisor (smartbuy)
- Feature 11: Travel Planner Pro (travelpal)
- Feature 12: Relationship Coach (ai-found-love)

Verifies guest fallback_user_id flows and core bootstrap/list/create actions.
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Guest user IDs for testing - using the exact format from the frontend code
GUEST_RC = "user_rc_guest_workspace_2026v1"
GUEST_TRAVEL = "user_test_travelpal_guest"
GUEST_SHOPPING = "user_test_smartbuy_guest"

# Headers to bypass CSRF for testing
TEST_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestRelationshipCoachFeature12:
    """Feature 12: Relationship Coach (ai-found-love) API tests"""
    
    def test_bootstrap_endpoint(self):
        """Test bootstrap returns tier, limits, usage for guest user"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/bootstrap",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "owner_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert data["tier"] == "free"
        assert "ai_sessions_per_month" in data["limits"]
        assert "important_dates" in data["limits"]
        print(f"✓ Relationship Coach bootstrap: tier={data['tier']}, limits={data['limits']}")
    
    def test_upcoming_reminders_endpoint(self):
        """Test upcoming reminders returns list for guest user"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/upcoming-reminders",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Upcoming reminders failed: {response.text}"
        data = response.json()
        
        assert "upcoming_dates" in data
        assert isinstance(data["upcoming_dates"], list)
        print(f"✓ Relationship Coach upcoming reminders: {len(data['upcoming_dates'])} dates")
    
    def test_important_dates_list(self):
        """Test important dates list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/important-dates",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Important dates list failed: {response.text}"
        data = response.json()
        
        assert "dates" in data
        assert isinstance(data["dates"], list)
        print(f"✓ Relationship Coach important dates: {len(data['dates'])} dates")
    
    def test_sessions_list(self):
        """Test sessions/journal list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/sessions",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Sessions list failed: {response.text}"
        data = response.json()
        
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        print(f"✓ Relationship Coach sessions: {len(data['sessions'])} sessions")
    
    def test_analytics_endpoint(self):
        """Test analytics endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/analytics",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Analytics failed: {response.text}"
        data = response.json()
        
        assert "total_advice_sessions" in data
        assert "total_date_ideas_generated" in data
        print(f"✓ Relationship Coach analytics: sessions={data['total_advice_sessions']}")
    
    def test_date_ideas_history(self):
        """Test date ideas history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/date-ideas/history",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Date ideas history failed: {response.text}"
        data = response.json()
        
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"✓ Relationship Coach date ideas history: {len(data['history'])} ideas")
    
    def test_gift_ideas_history(self):
        """Test gift ideas history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/gift-ideas/history",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Gift ideas history failed: {response.text}"
        data = response.json()
        
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"✓ Relationship Coach gift ideas history: {len(data['history'])} ideas")
    
    def test_assessments_history(self):
        """Test assessments history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/assessments/history",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Assessments history failed: {response.text}"
        data = response.json()
        
        assert "assessments" in data
        assert isinstance(data["assessments"], list)
        print(f"✓ Relationship Coach assessments history: {len(data['assessments'])} assessments")
    
    def test_communication_tips_history(self):
        """Test communication tips history endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/relationship-coach/communication-tips/history",
            params={"fallback_user_id": GUEST_RC}
        )
        assert response.status_code == 200, f"Comm tips history failed: {response.text}"
        data = response.json()
        
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"✓ Relationship Coach comm tips history: {len(data['history'])} tips")


class TestTravelPlannerProFeature11:
    """Feature 11: Travel Planner Pro (travelpal) API tests"""
    
    def test_bootstrap_endpoint(self):
        """Test bootstrap returns tier, limits, usage for guest user"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/bootstrap",
            params={"fallback_user_id": GUEST_TRAVEL}
        )
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        assert "owner_id" in data or "user_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert data["tier"] == "free"
        print(f"✓ Travel Planner Pro bootstrap: tier={data['tier']}, limits={data['limits']}")
    
    def test_trips_list(self):
        """Test trips list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": GUEST_TRAVEL}
        )
        assert response.status_code == 200, f"Trips list failed: {response.text}"
        data = response.json()
        
        assert "trips" in data
        assert isinstance(data["trips"], list)
        print(f"✓ Travel Planner Pro trips: {len(data['trips'])} trips")
    
    def test_create_trip(self):
        """Test trip creation"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": GUEST_TRAVEL},
            headers=TEST_HEADERS,
            json={
                "name": "Test Trip P3",
                "destination": "Paris, France",
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "traveler_count": 2,
                "trip_type": "vacation",
                "currency": "USD"
            }
        )
        assert response.status_code in [200, 201], f"Create trip failed: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data["name"] == "Test Trip P3"
        assert data["destination"] == "Paris, France"
        print(f"✓ Travel Planner Pro trip created: id={data['id']}")
        return data["id"]
    
    def test_trip_itinerary_list(self):
        """Test trip itinerary list (requires trip first)"""
        # Create a trip first
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": GUEST_TRAVEL},
            headers=TEST_HEADERS,
            json={
                "name": "Itinerary Test Trip",
                "destination": "Tokyo, Japan",
                "start_date": "2026-04-01",
                "end_date": "2026-04-05",
                "traveler_count": 1,
                "trip_type": "adventure",
                "currency": "USD"
            }
        )
        assert trip_response.status_code in [200, 201]
        trip_id = trip_response.json()["id"]
        
        # Get itinerary
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/itinerary",
            params={"fallback_user_id": GUEST_TRAVEL}
        )
        assert response.status_code == 200, f"Itinerary list failed: {response.text}"
        data = response.json()
        
        assert "itinerary" in data
        assert isinstance(data["itinerary"], list)
        print(f"✓ Travel Planner Pro itinerary: {len(data['itinerary'])} days")
    
    def test_trip_budget_endpoint(self):
        """Test trip budget endpoint"""
        # Create a trip first
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": GUEST_TRAVEL},
            headers=TEST_HEADERS,
            json={
                "name": "Budget Test Trip",
                "destination": "London, UK",
                "start_date": "2026-05-01",
                "end_date": "2026-05-05",
                "traveler_count": 1,
                "trip_type": "vacation",
                "currency": "USD"
            }
        )
        assert trip_response.status_code in [200, 201]
        trip_id = trip_response.json()["id"]
        
        # Get budget
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/budget",
            params={"fallback_user_id": GUEST_TRAVEL}
        )
        assert response.status_code == 200, f"Budget endpoint failed: {response.text}"
        data = response.json()
        
        # Budget may be null if not created yet
        assert "budget" in data
        print("✓ Travel Planner Pro budget endpoint works")
    
    def test_trip_checklist_endpoint(self):
        """Test trip checklist endpoint"""
        # Create a trip first
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": GUEST_TRAVEL},
            headers=TEST_HEADERS,
            json={
                "name": "Checklist Test Trip",
                "destination": "Rome, Italy",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
                "traveler_count": 1,
                "trip_type": "vacation",
                "currency": "USD"
            }
        )
        assert trip_response.status_code in [200, 201]
        trip_id = trip_response.json()["id"]
        
        # Get checklist
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/checklist",
            params={"fallback_user_id": GUEST_TRAVEL}
        )
        assert response.status_code == 200, f"Checklist endpoint failed: {response.text}"
        data = response.json()
        
        assert "checklist" in data
        print("✓ Travel Planner Pro checklist endpoint works")


class TestSmartShoppingAdvisorFeature10:
    """Feature 10: Smart Shopping Advisor (smartbuy) API tests"""
    
    def test_bootstrap_endpoint(self):
        """Test bootstrap returns tier, limits, usage for guest user"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": GUEST_SHOPPING}
        )
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        assert "owner_id" in data or "user_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert data["tier"] == "free"
        print(f"✓ Smart Shopping Advisor bootstrap: tier={data['tier']}, limits={data['limits']}")
    
    def test_wishlists_list(self):
        """Test wishlists list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": GUEST_SHOPPING}
        )
        assert response.status_code == 200, f"Wishlists list failed: {response.text}"
        data = response.json()
        
        assert "wishlists" in data
        assert isinstance(data["wishlists"], list)
        print(f"✓ Smart Shopping Advisor wishlists: {len(data['wishlists'])} wishlists")
    
    def test_create_wishlist(self):
        """Test wishlist creation"""
        response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": GUEST_SHOPPING},
            headers=TEST_HEADERS,
            json={
                "name": "Test Wishlist P3",
                "description": "Testing P3 refactor",
                "items": []
            }
        )
        assert response.status_code in [200, 201], f"Create wishlist failed: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data["name"] == "Test Wishlist P3"
        print(f"✓ Smart Shopping Advisor wishlist created: id={data['id']}")
        return data["id"]
    
    def test_budgets_list(self):
        """Test budgets list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/budgets",
            params={"fallback_user_id": GUEST_SHOPPING}
        )
        assert response.status_code == 200, f"Budgets list failed: {response.text}"
        data = response.json()
        
        assert "budgets" in data
        assert isinstance(data["budgets"], list)
        print(f"✓ Smart Shopping Advisor budgets: {len(data['budgets'])} budgets")
    
    def test_create_budget(self):
        """Test budget creation"""
        response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/budgets",
            params={"fallback_user_id": GUEST_SHOPPING},
            headers=TEST_HEADERS,
            json={
                "name": "Test Budget P3",
                "category": "electronics",
                "monthly_limit": 500.00,
                "currency": "USD",
                "alert_threshold_pct": 80.0
            }
        )
        assert response.status_code in [200, 201], f"Create budget failed: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data["name"] == "Test Budget P3"
        print(f"✓ Smart Shopping Advisor budget created: id={data['id']}")
        return data["id"]
    
    def test_price_alerts_list(self):
        """Test price alerts list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/price-alerts",
            params={"fallback_user_id": GUEST_SHOPPING}
        )
        assert response.status_code == 200, f"Price alerts list failed: {response.text}"
        data = response.json()
        
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        print(f"✓ Smart Shopping Advisor price alerts: {len(data['alerts'])} alerts")
    
    def test_deals_list(self):
        """Test deals list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/deals",
            params={"fallback_user_id": GUEST_SHOPPING, "limit": 10}
        )
        assert response.status_code == 200, f"Deals list failed: {response.text}"
        data = response.json()
        
        assert "deals" in data
        assert isinstance(data["deals"], list)
        print(f"✓ Smart Shopping Advisor deals: {len(data['deals'])} deals")
    
    def test_carbon_report(self):
        """Test carbon report endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/carbon-report",
            params={"fallback_user_id": GUEST_SHOPPING}
        )
        assert response.status_code == 200, f"Carbon report failed: {response.text}"
        data = response.json()
        
        assert "total_carbon_kg" in data or "month" in data
        print("✓ Smart Shopping Advisor carbon report works")


class TestGuestFallbackFlows:
    """Test guest fallback_user_id flows work correctly across all three features"""
    
    def test_rc_guest_flow_complete(self):
        """Test complete guest flow for Relationship Coach"""
        # Use the exact guest ID from the frontend code
        guest_id = GUEST_RC
        
        # Bootstrap
        r1 = requests.get(f"{BASE_URL}/api/relationship-coach/bootstrap", params={"fallback_user_id": guest_id})
        assert r1.status_code == 200, f"Bootstrap failed: {r1.text}"
        
        # Upcoming reminders
        r2 = requests.get(f"{BASE_URL}/api/relationship-coach/upcoming-reminders", params={"fallback_user_id": guest_id})
        assert r2.status_code == 200, f"Upcoming reminders failed: {r2.text}"
        
        # Important dates
        r3 = requests.get(f"{BASE_URL}/api/relationship-coach/important-dates", params={"fallback_user_id": guest_id})
        assert r3.status_code == 200, f"Important dates failed: {r3.text}"
        
        print(f"✓ Relationship Coach guest flow complete for {guest_id}")
    
    def test_travel_guest_flow_complete(self):
        """Test complete guest flow for Travel Planner Pro"""
        guest_id = GUEST_TRAVEL
        
        # Bootstrap
        r1 = requests.get(f"{BASE_URL}/api/travel-planner-pro/bootstrap", params={"fallback_user_id": guest_id})
        assert r1.status_code == 200, f"Bootstrap failed: {r1.text}"
        
        # Trips list
        r2 = requests.get(f"{BASE_URL}/api/travel-planner-pro/trips", params={"fallback_user_id": guest_id})
        assert r2.status_code == 200, f"Trips list failed: {r2.text}"
        
        print(f"✓ Travel Planner Pro guest flow complete for {guest_id}")
    
    def test_shopping_guest_flow_complete(self):
        """Test complete guest flow for Smart Shopping Advisor"""
        guest_id = GUEST_SHOPPING
        
        # Bootstrap
        r1 = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/bootstrap", params={"fallback_user_id": guest_id})
        assert r1.status_code == 200, f"Bootstrap failed: {r1.text}"
        
        # Wishlists
        r2 = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/wishlists", params={"fallback_user_id": guest_id})
        assert r2.status_code == 200, f"Wishlists failed: {r2.text}"
        
        # Budgets
        r3 = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/budgets", params={"fallback_user_id": guest_id})
        assert r3.status_code == 200, f"Budgets failed: {r3.text}"
        
        print(f"✓ Smart Shopping Advisor guest flow complete for {guest_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
