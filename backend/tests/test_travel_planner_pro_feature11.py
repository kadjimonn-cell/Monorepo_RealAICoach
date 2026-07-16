"""
Feature 11: Travel Planner Pro - Backend API Tests
Tests strict fallback_user_id validation and core CRUD operations
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test guest ID - must match user_* format with 12-80 chars after prefix
VALID_GUEST_ID = "user_testfeature11abc12345"
INVALID_GUEST_ID = "guest-travel-planner"  # Old format - should be rejected

# Headers required for POST/PUT/DELETE requests (CSRF bypass)
CSRF_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestTravelPlannerProStrictValidation:
    """Test strict fallback_user_id validation in travel_planner_pro resolver"""

    def test_bootstrap_with_valid_guest_id_returns_200(self):
        """Valid user_* fallback returns 200 for bootstrap"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert "features_available" in data
        print(f"PASS: Bootstrap with valid guest ID returns 200, tier={data['tier']}")

    def test_bootstrap_with_invalid_guest_id_returns_400(self):
        """Invalid fallback_user_id returns 400 travel_planner_invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "travel_planner_invalid_guest_id", \
            f"Expected error_code=travel_planner_invalid_guest_id, got {data}"
        print("PASS: Invalid guest ID returns 400 with travel_planner_invalid_guest_id")

    def test_bootstrap_without_auth_or_fallback_returns_401(self):
        """Missing auth/fallback returns 401 travel_auth_required"""
        response = requests.get(f"{BASE_URL}/api/travel-planner-pro/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "travel_auth_required", \
            f"Expected error_code=travel_auth_required, got {data}"
        print("PASS: Missing auth/fallback returns 401 with travel_auth_required")

    def test_trips_with_valid_guest_id_returns_200(self):
        """Valid user_* fallback returns 200 for trips listing"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trips" in data
        print(f"PASS: Trips with valid guest ID returns 200, trips_count={len(data['trips'])}")

    def test_trips_with_invalid_guest_id_returns_400(self):
        """Invalid fallback_user_id returns 400 for trips"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            params={"fallback_user_id": INVALID_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "travel_planner_invalid_guest_id"
        print("PASS: Trips with invalid guest ID returns 400")


class TestTravelPlannerProTripCRUD:
    """Test trip CRUD operations with valid guest ID"""

    @pytest.fixture
    def trip_id(self):
        """Create a trip and return its ID for testing"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_Trip_{uuid.uuid4().hex[:8]}",
                "destination": "Paris, France",
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "traveler_count": 2,
                "trip_type": "vacation",
                "budget_total": 3000.0,
                "currency": "USD"
            }
        )
        assert response.status_code == 200, f"Failed to create trip: {response.text}"
        data = response.json()
        trip_id = data.get("trip_id")
        yield trip_id
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )

    def test_create_trip_success(self):
        """Create trip with valid guest ID"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_CreateTrip_{uuid.uuid4().hex[:8]}",
                "destination": "Tokyo, Japan",
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "traveler_count": 1,
                "trip_type": "adventure"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trip_id" in data
        assert data.get("message") == "Trip created successfully"
        print(f"PASS: Trip created successfully, trip_id={data['trip_id']}")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{data['trip_id']}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )

    def test_get_trip_details(self, trip_id):
        """Get specific trip details"""
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("id") == trip_id
        assert "destination" in data
        print(f"PASS: Get trip details returns 200, destination={data['destination']}")

    def test_update_trip(self, trip_id):
        """Update trip details"""
        response = requests.put(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": "Updated Trip Name",
                "status": "ongoing"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("message") == "Trip updated successfully"
        print("PASS: Trip updated successfully")

    def test_delete_trip(self):
        """Delete trip"""
        # Create a trip to delete
        create_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_DeleteTrip_{uuid.uuid4().hex[:8]}",
                "destination": "London, UK",
                "start_date": "2026-05-01",
                "end_date": "2026-05-05"
            }
        )
        assert create_response.status_code == 200, f"Failed to create trip: {create_response.text}"
        trip_id = create_response.json().get("trip_id")
        
        # Delete the trip
        response = requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify deletion
        get_response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert get_response.status_code == 404
        print("PASS: Trip deleted successfully and verified")


class TestTravelPlannerProItinerary:
    """Test itinerary operations"""

    @pytest.fixture
    def trip_with_itinerary(self):
        """Create a trip with an itinerary day"""
        # Create trip
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_ItineraryTrip_{uuid.uuid4().hex[:8]}",
                "destination": "Rome, Italy",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05"
            }
        )
        assert trip_response.status_code == 200, f"Failed to create trip: {trip_response.text}"
        trip_id = trip_response.json().get("trip_id")
        
        # Create itinerary day
        day_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/itinerary",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "day_number": 1,
                "date": "2026-06-01",
                "title": "Arrival Day",
                "activities": []
            }
        )
        assert day_response.status_code == 200, f"Failed to create itinerary day: {day_response.text}"
        day_id = day_response.json().get("day_id")
        
        yield {"trip_id": trip_id, "day_id": day_id}
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )

    def test_get_itinerary(self, trip_with_itinerary):
        """Get trip itinerary"""
        trip_id = trip_with_itinerary["trip_id"]
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/itinerary",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "itinerary" in data
        print(f"PASS: Get itinerary returns 200, days_count={len(data['itinerary'])}")

    def test_add_activity_to_day(self, trip_with_itinerary):
        """Add activity to itinerary day"""
        trip_id = trip_with_itinerary["trip_id"]
        day_id = trip_with_itinerary["day_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/itinerary/{day_id}/activities",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS,
            json={
                "time_slot": "morning",
                "title": "Visit Colosseum",
                "location": "Colosseum, Rome",
                "estimated_cost": 50.0,
                "category": "sightseeing"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "activity_id" in data
        print(f"PASS: Activity added successfully, activity_id={data['activity_id']}")


class TestTravelPlannerProBudget:
    """Test budget and expense operations"""

    @pytest.fixture
    def trip_with_budget(self):
        """Create a trip with budget"""
        # Create trip
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_BudgetTrip_{uuid.uuid4().hex[:8]}",
                "destination": "Barcelona, Spain",
                "start_date": "2026-07-01",
                "end_date": "2026-07-07"
            }
        )
        assert trip_response.status_code == 200, f"Failed to create trip: {trip_response.text}"
        trip_id = trip_response.json().get("trip_id")
        
        # Create budget
        budget_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/budget",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "total_budget": 2000.0,
                "currency": "USD"
            }
        )
        assert budget_response.status_code == 200, f"Failed to create budget: {budget_response.text}"
        
        yield trip_id
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )

    def test_get_budget(self, trip_with_budget):
        """Get trip budget"""
        trip_id = trip_with_budget
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/budget",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "budget" in data
        if data["budget"]:
            assert data["budget"]["total_budget"] == 2000.0
        print("PASS: Get budget returns 200")

    def test_log_expense(self, trip_with_budget):
        """Log expense for trip"""
        trip_id = trip_with_budget
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/expenses",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "amount": 150.0,
                "currency": "USD",
                "category": "food",
                "description": "Dinner at local restaurant",
                "merchant": "La Boqueria"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "expense_id" in data
        print(f"PASS: Expense logged successfully, expense_id={data['expense_id']}")


class TestTravelPlannerProChecklist:
    """Test checklist operations"""

    @pytest.fixture
    def trip_with_checklist(self):
        """Create a trip with checklist"""
        # Create trip
        trip_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": f"TEST_ChecklistTrip_{uuid.uuid4().hex[:8]}",
                "destination": "Amsterdam, Netherlands",
                "start_date": "2026-08-01",
                "end_date": "2026-08-05"
            }
        )
        assert trip_response.status_code == 200, f"Failed to create trip: {trip_response.text}"
        trip_id = trip_response.json().get("trip_id")
        
        # Create checklist with items
        checklist_response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/checklist",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "items": [
                    {"category": "documents", "title": "Passport", "priority": "high"},
                    {"category": "packing", "title": "Camera", "priority": "medium"}
                ]
            }
        )
        assert checklist_response.status_code == 200, f"Failed to create checklist: {checklist_response.text}"
        
        yield trip_id
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=CSRF_HEADERS
        )

    def test_get_checklist(self, trip_with_checklist):
        """Get trip checklist"""
        trip_id = trip_with_checklist
        response = requests.get(
            f"{BASE_URL}/api/travel-planner-pro/trips/{trip_id}/checklist",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "checklist" in data
        if data["checklist"]:
            assert "items" in data["checklist"]
            assert "stats" in data
        print("PASS: Get checklist returns 200")


class TestTravelPlannerProAI:
    """Test AI features (basic validation only - no actual AI calls)"""

    def test_ai_itinerary_with_invalid_guest_id_returns_400(self):
        """AI itinerary with invalid guest ID returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/ai/generate-itinerary",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": INVALID_GUEST_ID,
                "destination": "Paris",
                "num_days": 3
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: AI itinerary with invalid guest ID returns 400")

    def test_ai_destination_with_invalid_guest_id_returns_400(self):
        """AI destination with invalid guest ID returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/ai/destination-recommend",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": INVALID_GUEST_ID,
                "budget": 2000,
                "interests": ["history", "food"]
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: AI destination with invalid guest ID returns 400")

    def test_ai_packing_with_invalid_guest_id_returns_400(self):
        """AI packing list with invalid guest ID returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/travel-planner-pro/ai/packing-list",
            headers=CSRF_HEADERS,
            json={
                "fallback_user_id": INVALID_GUEST_ID,
                "destination": "Tokyo",
                "num_days": 7,
                "season": "spring"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: AI packing with invalid guest ID returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
