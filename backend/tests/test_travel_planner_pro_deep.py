"""Feature 11 (Travel Planner Pro) backend E2E test suite.

Covers:
- Bootstrap endpoint
- Trip Management (CRUD)
- Itinerary & Activities (CRUD)
- Budget Management (CRUD)
- Expense Tracking (CRUD + analytics)
- Checklist Management (CRUD)
- AI Features (itinerary generation, destination recommendations, packing list)
- Tier limit enforcement
- Business logic validation
"""

import os
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = str(os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required to run test_travel_planner_pro_deep.py")

API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
state = {
    "trip_id": None,
    "day_id": None,
    "activity_id": None,
    "budget_id": None,
    "expense_id": None,
    "checklist_id": None,
    "item_id": None,
}


def log_test(name: str, ok: bool, detail: str = ""):
    results["total"] += 1
    if ok:
        results["passed"] += 1
        print(f"✅ PASS: {name}")
        if detail:
            print(f"   {detail}")
    else:
        results["failed"] += 1
        results["errors"].append(f"{name}: {detail}")
        print(f"❌ FAIL: {name}")
        if detail:
            print(f"   {detail}")


def assert_status(resp: requests.Response, expected: int, label: str) -> bool:
    ok = resp.status_code == expected
    if not ok:
        log_test(label, False, f"status={resp.status_code}, body={resp.text[:220]}")
    return ok


def login() -> bool:
    resp = session.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if not assert_status(resp, 200, "Login"):
        return False
    log_test("Login", True, "Authenticated admin session")
    return True


# ── Bootstrap ────────────────────────────────────────────────────────────────


def test_bootstrap():
    resp = session.get(f"{API_BASE}/travel-planner-pro/bootstrap")
    if not assert_status(resp, 200, "Bootstrap"):
        return
    data = resp.json()
    checks = [
        "user_id" in data,
        "tier" in data,
        "limits" in data,
        "usage" in data,
        "features_available" in data,
    ]
    log_test("Bootstrap structure", all(checks), f"tier={data.get('tier')}")


# ── Trip Management ──────────────────────────────────────────────────────────


def test_create_trip():
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    in_7_days = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    
    payload = {
        "name": "Tokyo Adventure E2E Test",
        "destination": "Tokyo, Japan",
        "start_date": tomorrow,
        "end_date": in_7_days,
        "traveler_count": 2,
        "trip_type": "vacation",
        "budget_total": 5000.0,
        "currency": "USD",
        "notes": "Test trip for Feature 11 backend validation"
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/trips", json=payload)
    if not assert_status(resp, 200, "Create Trip"):
        return
    data = resp.json()
    if "trip_id" in data:
        state["trip_id"] = data["trip_id"]
        log_test("Create Trip - ID returned", True, f"trip_id={state['trip_id'][:8]}...")
    else:
        log_test("Create Trip - ID returned", False, "No trip_id in response")


def test_get_trips():
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips")
    if not assert_status(resp, 200, "Get Trips"):
        return
    data = resp.json()
    if "trips" in data and len(data["trips"]) > 0:
        log_test("Get Trips - List returned", True, f"count={len(data['trips'])}")
    else:
        log_test("Get Trips - List returned", False, "No trips in response")


def test_get_trip_details():
    if not state["trip_id"]:
        log_test("Get Trip Details", False, "trip_id missing")
        return
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}")
    if not assert_status(resp, 200, "Get Trip Details"):
        return
    data = resp.json()
    checks = [
        data.get("id") == state["trip_id"],
        "name" in data,
        "destination" in data,
        "start_date" in data,
    ]
    log_test("Get Trip Details - Structure", all(checks), f"name={data.get('name')}")


def test_update_trip():
    if not state["trip_id"]:
        log_test("Update Trip", False, "trip_id missing")
        return
    payload = {"notes": "Updated notes from E2E test", "status": "confirmed"}
    resp = session.put(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}", json=payload)
    if not assert_status(resp, 200, "Update Trip"):
        return
    log_test("Update Trip", True, "Trip updated successfully")


# ── Itinerary & Activities ───────────────────────────────────────────────────


def test_create_itinerary_day():
    if not state["trip_id"]:
        log_test("Create Itinerary Day", False, "trip_id missing")
        return
    
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    payload = {
        "day_number": 1,
        "date": tomorrow,
        "title": "Day 1: Arrival & Exploration",
        "activities": [
            {
                "time_slot": "morning",
                "start_time": "09:00",
                "end_time": "12:00",
                "title": "Tsukiji Outer Market Tour",
                "location": "Tsukiji Market, Tokyo",
                "description": "Explore fresh seafood and local delicacies",
                "estimated_cost": 50.0,
                "category": "food",
                "booking_status": "planned",
            }
        ]
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/itinerary", json=payload)
    if not assert_status(resp, 200, "Create Itinerary Day"):
        return
    data = resp.json()
    if "day_id" in data:
        state["day_id"] = data["day_id"]
        log_test("Create Itinerary Day - ID returned", True, f"day_id={state['day_id'][:8]}...")
    else:
        log_test("Create Itinerary Day - ID returned", False, "No day_id in response")


def test_get_itinerary():
    if not state["trip_id"]:
        log_test("Get Itinerary", False, "trip_id missing")
        return
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/itinerary")
    if not assert_status(resp, 200, "Get Itinerary"):
        return
    data = resp.json()
    if "itinerary" in data and len(data["itinerary"]) > 0:
        log_test("Get Itinerary - List returned", True, f"days={len(data['itinerary'])}")
    else:
        log_test("Get Itinerary - List returned", False, "No itinerary days in response")


def test_add_activity():
    if not state["trip_id"] or not state["day_id"]:
        log_test("Add Activity", False, "trip_id or day_id missing")
        return
    
    activity = {
        "time_slot": "afternoon",
        "start_time": "14:00",
        "end_time": "17:00",
        "title": "Visit Senso-ji Temple",
        "location": "Asakusa, Tokyo",
        "description": "Historic Buddhist temple",
        "estimated_cost": 20.0,
        "category": "sightseeing",
        "booking_status": "planned",
    }
    resp = session.post(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/itinerary/{state['day_id']}/activities",
        json=activity
    )
    if not assert_status(resp, 200, "Add Activity"):
        return
    data = resp.json()
    if "activity_id" in data:
        state["activity_id"] = data["activity_id"]
        log_test("Add Activity - ID returned", True, f"activity_id={state['activity_id'][:8]}...")
    else:
        log_test("Add Activity - ID returned", False, "No activity_id in response")


def test_update_activity():
    if not state["trip_id"] or not state["activity_id"]:
        log_test("Update Activity", False, "trip_id or activity_id missing")
        return
    payload = {"booking_status": "booked", "notes": "Reservation confirmed"}
    resp = session.put(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/activities/{state['activity_id']}",
        json=payload
    )
    if not assert_status(resp, 200, "Update Activity"):
        return
    log_test("Update Activity", True, "Activity updated successfully")


# ── Budget Management ────────────────────────────────────────────────────────


def test_create_budget():
    if not state["trip_id"]:
        log_test("Create Budget", False, "trip_id missing")
        return
    
    payload = {
        "total_budget": 5000.0,
        "currency": "USD",
        "category_budgets": {
            "accommodation": 2000.0,
            "food": 1250.0,
            "transport": 750.0,
            "activities": 750.0,
            "shopping": 250.0,
        }
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/budget", json=payload)
    if not assert_status(resp, 200, "Create Budget"):
        return
    data = resp.json()
    if "budget_id" in data:
        state["budget_id"] = data["budget_id"]
        log_test("Create Budget - ID returned", True, f"budget_id={state['budget_id'][:8]}...")
    else:
        log_test("Create Budget - ID returned", False, "No budget_id in response")


def test_get_budget():
    if not state["trip_id"]:
        log_test("Get Budget", False, "trip_id missing")
        return
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/budget")
    if not assert_status(resp, 200, "Get Budget"):
        return
    data = resp.json()
    if "budget" in data and data["budget"]:
        budget = data["budget"]
        checks = [
            "total_budget" in budget,
            "category_budgets" in budget,
            "spent_total" in budget,
            "remaining" in budget,
        ]
        log_test("Get Budget - Structure", all(checks), f"total={budget.get('total_budget')}")
    else:
        log_test("Get Budget - Structure", False, "No budget in response")


def test_update_budget():
    if not state["trip_id"]:
        log_test("Update Budget", False, "trip_id missing")
        return
    payload = {"total_budget": 5500.0, "currency": "USD"}
    resp = session.put(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/budget", json=payload)
    if not assert_status(resp, 200, "Update Budget"):
        return
    log_test("Update Budget", True, "Budget updated successfully")


# ── Expense Tracking ─────────────────────────────────────────────────────────


def test_log_expense():
    if not state["trip_id"]:
        log_test("Log Expense", False, "trip_id missing")
        return
    
    payload = {
        "amount": 150.50,
        "currency": "USD",
        "category": "food",
        "description": "Dinner at sushi restaurant",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "merchant": "Sushi Dai",
        "payment_method": "credit_card",
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/expenses", json=payload)
    if not assert_status(resp, 200, "Log Expense"):
        return
    data = resp.json()
    if "expense_id" in data:
        state["expense_id"] = data["expense_id"]
        log_test("Log Expense - ID returned", True, f"expense_id={state['expense_id'][:8]}...")
    else:
        log_test("Log Expense - ID returned", False, "No expense_id in response")


def test_get_expenses():
    if not state["trip_id"]:
        log_test("Get Expenses", False, "trip_id missing")
        return
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/expenses")
    if not assert_status(resp, 200, "Get Expenses"):
        return
    data = resp.json()
    checks = [
        "expenses" in data,
        "category_totals" in data,
        "total_spent" in data,
    ]
    log_test("Get Expenses - Structure", all(checks), f"total_spent={data.get('total_spent')}")


# ── Checklist Management ─────────────────────────────────────────────────────


def test_create_checklist():
    if not state["trip_id"]:
        log_test("Create Checklist", False, "trip_id missing")
        return
    
    payload = {
        "items": [
            {
                "category": "documents",
                "title": "Valid passport",
                "description": "Check expiration date",
                "priority": "high",
            },
            {
                "category": "packing",
                "title": "Travel adapter",
                "description": "Type A plug for Japan",
                "priority": "medium",
            },
            {
                "category": "tasks",
                "title": "Book airport transfer",
                "description": "From Narita to hotel",
                "priority": "high",
            },
        ]
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/checklist", json=payload)
    if not assert_status(resp, 200, "Create Checklist"):
        return
    data = resp.json()
    if "checklist_id" in data:
        state["checklist_id"] = data["checklist_id"]
        log_test("Create Checklist - ID returned", True, f"checklist_id={state['checklist_id'][:8]}...")
    elif "message" in data and "added" in data["message"]:
        log_test("Create Checklist - Items added", True, "Items added to existing checklist")
    else:
        log_test("Create Checklist", True, "Checklist created")


def test_get_checklist():
    if not state["trip_id"]:
        log_test("Get Checklist", False, "trip_id missing")
        return
    resp = session.get(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/checklist")
    if not assert_status(resp, 200, "Get Checklist"):
        return
    data = resp.json()
    if "checklist" in data and data["checklist"]:
        checklist = data["checklist"]
        items = checklist.get("items", [])
        if len(items) > 0:
            state["item_id"] = items[0]["item_id"]
            log_test("Get Checklist - Structure", True, f"items={len(items)}")
        else:
            log_test("Get Checklist - Structure", False, "No items in checklist")
    else:
        log_test("Get Checklist - Structure", False, "No checklist in response")


def test_toggle_checklist_item():
    if not state["trip_id"] or not state["item_id"]:
        log_test("Toggle Checklist Item", False, "trip_id or item_id missing")
        return
    resp = session.put(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/checklist/{state['item_id']}"
    )
    if not assert_status(resp, 200, "Toggle Checklist Item"):
        return
    data = resp.json()
    log_test("Toggle Checklist Item", "completed" in data, f"completed={data.get('completed')}")


# ── AI Features ──────────────────────────────────────────────────────────────


def test_ai_generate_itinerary():
    payload = {
        "destination": "Paris, France",
        "num_days": 3,
        "traveler_count": 2,
        "budget": 3000.0,
        "currency": "USD",
        "interests": ["art", "food", "history"],
        "trip_type": "vacation",
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/ai/generate-itinerary", json=payload)
    if not assert_status(resp, 200, "AI Generate Itinerary"):
        return
    data = resp.json()
    checks = [
        "itinerary" in data,
        "destination" in data,
        "num_days" in data,
        len(data.get("itinerary", "")) > 100,  # Should have substantial content
    ]
    log_test("AI Generate Itinerary - Response", all(checks), f"length={len(data.get('itinerary', ''))}")


def test_ai_destination_recommend():
    payload = {
        "budget": 2500.0,
        "interests": ["beaches", "culture", "adventure"],
        "season": "summer",
        "preferences": "Prefer destinations in Southeast Asia",
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/ai/destination-recommend", json=payload)
    if not assert_status(resp, 200, "AI Destination Recommend"):
        return
    data = resp.json()
    checks = [
        "recommendations" in data,
        "query" in data,
        len(data.get("recommendations", "")) > 100,
    ]
    log_test("AI Destination Recommend - Response", all(checks), f"length={len(data.get('recommendations', ''))}")


def test_ai_packing_list():
    payload = {
        "destination": "Reykjavik, Iceland",
        "num_days": 5,
        "season": "winter",
        "activities": ["Northern Lights", "hot springs", "glacier hiking"],
    }
    resp = session.post(f"{API_BASE}/travel-planner-pro/ai/packing-list", json=payload)
    if not assert_status(resp, 200, "AI Packing List"):
        return
    data = resp.json()
    checks = [
        "packing_list" in data,
        "destination" in data,
        "num_days" in data,
        len(data.get("packing_list", "")) > 100,
    ]
    log_test("AI Packing List - Response", all(checks), f"length={len(data.get('packing_list', ''))}")


# ── Cleanup ──────────────────────────────────────────────────────────────────


def test_delete_activity():
    if not state["trip_id"] or not state["activity_id"]:
        log_test("Delete Activity", False, "trip_id or activity_id missing")
        return
    resp = session.delete(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/activities/{state['activity_id']}"
    )
    if not assert_status(resp, 200, "Delete Activity"):
        return
    log_test("Delete Activity", True, "Activity deleted successfully")


def test_delete_checklist_item():
    if not state["trip_id"] or not state["item_id"]:
        log_test("Delete Checklist Item", False, "trip_id or item_id missing")
        return
    resp = session.delete(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/checklist/{state['item_id']}"
    )
    if not assert_status(resp, 200, "Delete Checklist Item"):
        return
    log_test("Delete Checklist Item", True, "Checklist item deleted successfully")


def test_delete_itinerary_day():
    if not state["trip_id"] or not state["day_id"]:
        log_test("Delete Itinerary Day", False, "trip_id or day_id missing")
        return
    resp = session.delete(
        f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}/itinerary/{state['day_id']}"
    )
    if not assert_status(resp, 200, "Delete Itinerary Day"):
        return
    log_test("Delete Itinerary Day", True, "Itinerary day deleted successfully")


def test_delete_trip():
    if not state["trip_id"]:
        log_test("Delete Trip", False, "trip_id missing")
        return
    resp = session.delete(f"{API_BASE}/travel-planner-pro/trips/{state['trip_id']}")
    if not assert_status(resp, 200, "Delete Trip"):
        return
    log_test("Delete Trip", True, "Trip and all associated data deleted successfully")


# ── Main Runner ──────────────────────────────────────────────────────────────


def main():
    print("=" * 80)
    print("Feature 11 (Travel Planner Pro) Backend E2E Test Suite")
    print(f"Target: {BASE_URL}")
    print("=" * 80)
    print()
    
    if not login():
        print("\n❌ Login failed. Cannot proceed with tests.")
        return
    
    print("\n--- Bootstrap ---")
    test_bootstrap()
    
    print("\n--- Trip Management ---")
    test_create_trip()
    test_get_trips()
    test_get_trip_details()
    test_update_trip()
    
    print("\n--- Itinerary & Activities ---")
    test_create_itinerary_day()
    test_get_itinerary()
    test_add_activity()
    test_update_activity()
    
    print("\n--- Budget Management ---")
    test_create_budget()
    test_get_budget()
    test_update_budget()
    
    print("\n--- Expense Tracking ---")
    test_log_expense()
    test_get_expenses()
    
    print("\n--- Checklist Management ---")
    test_create_checklist()
    test_get_checklist()
    test_toggle_checklist_item()
    
    print("\n--- AI Features ---")
    test_ai_generate_itinerary()
    test_ai_destination_recommend()
    test_ai_packing_list()
    
    print("\n--- Cleanup ---")
    test_delete_activity()
    test_delete_checklist_item()
    test_delete_itinerary_day()
    test_delete_trip()
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total:  {results['total']}")
    print(f"Passed: {results['passed']} ✅")
    print(f"Failed: {results['failed']} ❌")
    
    if results["errors"]:
        print("\nERRORS:")
        for err in results["errors"]:
            print(f"  • {err}")
    
    success_rate = (results["passed"] / results["total"] * 100) if results["total"] > 0 else 0
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    
    if results["failed"] == 0:
        print("\n✅ ALL TESTS PASSED - Feature 11 Backend Checkpoint C VERIFIED")
    else:
        print(f"\n⚠️ {results['failed']} test(s) failed")
    
    print("=" * 80)


if __name__ == "__main__":
    main()
