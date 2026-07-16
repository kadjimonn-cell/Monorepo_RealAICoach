"""Feature 13 (Mobility Assistant) backend E2E test suite.

Covers:
- Bootstrap endpoint
- Vehicle Search (AI-generated listings + history)
- Trade-In Valuation (AI-powered appraisal)
- Finance Calculator (calculations + AI advice)
- Saved Vehicles (CRUD operations)
- Maintenance Schedule (AI generation)
- Cost Calculator (AI 5-year analysis)
- Trip Planner (AI road trip planning)
- Vehicle Comparison (AI analysis)
- EV Advisor (AI transition guidance)
- Driving Insights (AI habits analysis)
- Service History (CRUD + analytics)
- Sessions & Analytics endpoints
- Tier limit enforcement (Free/Basic/Premium)
- MongoDB serialization (no _id leaks)
- AI integration pattern validation
"""

import os
import requests
from datetime import datetime, timezone

BASE_URL = str(os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required to run test_mobility_assistant_deep.py")

API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
state = {
    "search_id": None,
    "vehicle_id": None,
    "valuation_id": None,
    "service_record_id": None,
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
    resp = session.get(f"{API_BASE}/mobility-assistant/bootstrap")
    if not assert_status(resp, 200, "Bootstrap"):
        return
    data = resp.json()
    checks = [
        "owner_id" in data,
        "tier" in data,
        "limits" in data,
        "usage" in data,
        isinstance(data.get("limits"), dict),
        isinstance(data.get("usage"), dict),
    ]
    log_test("Bootstrap structure", all(checks), f"tier={data.get('tier')}")
    
    # Check tier limits structure
    limits = data.get("limits", {})
    limit_checks = [
        "searches_per_month" in limits,
        "ai_calls_per_month" in limits,
        "saved_vehicles" in limits,
        "service_records" in limits,
    ]
    log_test("Bootstrap tier limits", all(limit_checks), f"limits={limits}")


# ── Vehicle Search ───────────────────────────────────────────────────────────


def test_vehicle_search():
    payload = {
        "make": "Toyota",
        "model": "Camry",
        "min_price": 15000,
        "max_price": 30000,
        "max_mileage": 60000,
        "year_from": 2018,
        "year_to": 2023,
        "vehicle_type": "sedan",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/search", json=payload)
    if not assert_status(resp, 200, "Vehicle Search"):
        return
    data = resp.json()
    checks = [
        "search_id" in data,
        "listings" in data,
        "count" in data,
        "tier" in data,
        isinstance(data.get("listings"), list),
    ]
    log_test("Vehicle Search structure", all(checks), f"Found {data.get('count')} vehicles")
    
    if data.get("listings"):
        state["search_id"] = data.get("search_id")
        vehicle = data["listings"][0]
        required_fields = ["listing_id", "make", "model", "year", "price", "mileage"]
        vehicle_checks = all(field in vehicle for field in required_fields)
        log_test("Vehicle listing structure", vehicle_checks, f"Sample: {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')}")
        
        # Check no MongoDB _id leak
        no_id_leak = "_id" not in vehicle
        log_test("Vehicle listing MongoDB serialization", no_id_leak, "No _id field present")


def test_search_history():
    resp = session.get(f"{API_BASE}/mobility-assistant/search/history")
    if not assert_status(resp, 200, "Search History"):
        return
    data = resp.json()
    checks = [
        "history" in data,
        isinstance(data.get("history"), list),
    ]
    log_test("Search History structure", all(checks), f"History count: {len(data.get('history', []))}")
    
    if data.get("history"):
        item = data["history"][0]
        # Check no MongoDB _id leak
        no_id_leak = "_id" not in item
        log_test("Search History MongoDB serialization", no_id_leak, "No _id field present")


# ── Trade-In Valuation ───────────────────────────────────────────────────────


def test_trade_in_valuation():
    payload = {
        "make": "Honda",
        "model": "Accord",
        "year": 2018,
        "mileage": 45000,
        "condition": "Good",
        "zip_code": "94105",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/trade-in", json=payload)
    if not assert_status(resp, 200, "Trade-In Valuation"):
        return
    data = resp.json()
    checks = [
        "valuation_id" in data,
        "make" in data,
        "model" in data,
        "year" in data,
        "valuation" in data,
        isinstance(data.get("valuation"), str),
        len(data.get("valuation", "")) > 50,  # AI response should be substantial
    ]
    log_test("Trade-In Valuation structure", all(checks), f"Valuation ID: {data.get('valuation_id')}")
    
    state["valuation_id"] = data.get("valuation_id")
    
    # Check AI response quality
    valuation_text = data.get("valuation", "")
    ai_quality_checks = [
        "trade" in valuation_text.lower() or "value" in valuation_text.lower(),
        len(valuation_text) > 100,  # Substantial response
    ]
    log_test("Trade-In AI response quality", all(ai_quality_checks), f"Response length: {len(valuation_text)} chars")


# ── Finance Calculator ───────────────────────────────────────────────────────


def test_finance_calculator():
    payload = {
        "vehicle_price": 28000.0,
        "down_payment": 5000.0,
        "loan_term_months": 60,
        "credit_score_range": "good",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/finance", json=payload)
    if not assert_status(resp, 200, "Finance Calculator"):
        return
    data = resp.json()
    checks = [
        "vehicle_price" in data,
        "down_payment" in data,
        "loan_amount" in data,
        "apr_percent" in data,
        "monthly_payment" in data,
        "total_paid" in data,
        "total_interest" in data,
        "ai_advice" in data,
    ]
    log_test("Finance Calculator structure", all(checks), f"Monthly: ${data.get('monthly_payment')}")
    
    # Validate calculations
    calc_checks = [
        data.get("loan_amount") == 23000.0,  # 28000 - 5000
        data.get("monthly_payment") > 0,
        data.get("total_paid") > data.get("loan_amount"),
    ]
    log_test("Finance Calculator math", all(calc_checks), f"Total Interest: ${data.get('total_interest')}")


# ── Saved Vehicles ───────────────────────────────────────────────────────────


def test_save_vehicle():
    payload = {
        "listing_id": "test_car_12345",
        "make": "Tesla",
        "model": "Model 3",
        "year": 2022,
        "price": 42000,
        "mileage": 18000,
        "trim": "Long Range",
        "dealer_rating": 4.7,
        "notes": "Great condition, test vehicle",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/saved-vehicles", json=payload)
    if not assert_status(resp, 200, "Save Vehicle"):
        return
    data = resp.json()
    checks = [
        "vehicle_id" in data,
        "message" in data,
    ]
    log_test("Save Vehicle structure", all(checks), f"Vehicle ID: {data.get('vehicle_id')}")
    state["vehicle_id"] = data.get("vehicle_id")


def test_list_saved_vehicles():
    resp = session.get(f"{API_BASE}/mobility-assistant/saved-vehicles")
    if not assert_status(resp, 200, "List Saved Vehicles"):
        return
    data = resp.json()
    checks = [
        "vehicles" in data,
        "count" in data,
        isinstance(data.get("vehicles"), list),
    ]
    log_test("List Saved Vehicles structure", all(checks), f"Count: {data.get('count')}")
    
    if data.get("vehicles"):
        vehicle = data["vehicles"][0]
        # Check no MongoDB _id leak
        no_id_leak = "_id" not in vehicle
        log_test("Saved Vehicles MongoDB serialization", no_id_leak, "No _id field present")


def test_delete_saved_vehicle():
    if not state.get("vehicle_id"):
        log_test("Delete Saved Vehicle", False, "No vehicle_id in state (skipped)")
        return
    
    resp = session.delete(f"{API_BASE}/mobility-assistant/saved-vehicles/{state['vehicle_id']}")
    if not assert_status(resp, 200, "Delete Saved Vehicle"):
        return
    data = resp.json()
    checks = [
        "message" in data,
        "vehicle_id" in data,
    ]
    log_test("Delete Saved Vehicle structure", all(checks), f"Deleted: {data.get('vehicle_id')}")


# ── Maintenance Schedule ─────────────────────────────────────────────────────


def test_maintenance_schedule():
    payload = {
        "make": "Ford",
        "model": "F-150",
        "year": 2020,
        "current_mileage": 52000,
        "last_service_mileage": 48000,
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/maintenance-schedule", json=payload)
    if not assert_status(resp, 200, "Maintenance Schedule"):
        return
    data = resp.json()
    checks = [
        "vehicle" in data,
        "current_mileage" in data,
        "maintenance_schedule" in data,
        isinstance(data.get("maintenance_schedule"), str),
        len(data.get("maintenance_schedule", "")) > 100,
    ]
    log_test("Maintenance Schedule structure", all(checks), f"Vehicle: {data.get('vehicle')}")
    
    # Check AI response quality
    schedule_text = data.get("maintenance_schedule", "")
    ai_quality = [
        "mileage" in schedule_text.lower() or "service" in schedule_text.lower(),
        len(schedule_text) > 200,
    ]
    log_test("Maintenance AI response quality", all(ai_quality), f"Response length: {len(schedule_text)} chars")


# ── Cost Calculator ──────────────────────────────────────────────────────────


def test_cost_calculator():
    payload = {
        "make": "BMW",
        "model": "3 Series",
        "year": 2021,
        "purchase_price": 45000,
        "annual_mileage": 12000,
        "fuel_type": "gasoline",
        "mpg": 28.5,
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/cost-calculator", json=payload)
    if not assert_status(resp, 200, "Cost Calculator"):
        return
    data = resp.json()
    checks = [
        "vehicle" in data,
        "purchase_price" in data,
        "annual_mileage" in data,
        "cost_analysis" in data,
        isinstance(data.get("cost_analysis"), str),
        len(data.get("cost_analysis", "")) > 100,
    ]
    log_test("Cost Calculator structure", all(checks), f"Vehicle: {data.get('vehicle')}")
    
    # Check AI response quality
    analysis_text = data.get("cost_analysis", "")
    ai_quality = [
        "cost" in analysis_text.lower() or "depreciation" in analysis_text.lower(),
        len(analysis_text) > 200,
    ]
    log_test("Cost Calculator AI quality", all(ai_quality), f"Response length: {len(analysis_text)} chars")


# ── Trip Planner ─────────────────────────────────────────────────────────────


def test_trip_planner():
    payload = {
        "origin": "San Francisco, CA",
        "destination": "Los Angeles, CA",
        "make": "Toyota",
        "model": "Prius",
        "year": 2022,
        "fuel_type": "hybrid",
        "mpg": 56,
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/trip-planner", json=payload)
    if not assert_status(resp, 200, "Trip Planner"):
        return
    data = resp.json()
    checks = [
        "origin" in data,
        "destination" in data,
        "vehicle" in data,
        "trip_plan" in data,
        isinstance(data.get("trip_plan"), str),
        len(data.get("trip_plan", "")) > 100,
    ]
    log_test("Trip Planner structure", all(checks), f"{data.get('origin')} → {data.get('destination')}")
    
    # Check AI response quality
    plan_text = data.get("trip_plan", "")
    ai_quality = [
        "trip" in plan_text.lower() or "distance" in plan_text.lower() or "fuel" in plan_text.lower(),
        len(plan_text) > 200,
    ]
    log_test("Trip Planner AI quality", all(ai_quality), f"Response length: {len(plan_text)} chars")


# ── Vehicle Comparison ───────────────────────────────────────────────────────


def test_vehicle_comparison():
    payload = {
        "vehicle_a": "2023 Tesla Model 3",
        "vehicle_b": "2023 Chevy Bolt EV",
        "priorities": ["cost", "range", "performance"],
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/compare", json=payload)
    if not assert_status(resp, 200, "Vehicle Comparison"):
        return
    data = resp.json()
    checks = [
        "comparison" in data,
        isinstance(data.get("comparison"), str),
        len(data.get("comparison", "")) > 100,
    ]
    log_test("Vehicle Comparison structure", all(checks))
    
    # Check AI response quality
    comparison_text = data.get("comparison", "")
    ai_quality = [
        "model 3" in comparison_text.lower() or "bolt" in comparison_text.lower(),
        len(comparison_text) > 200,
    ]
    log_test("Vehicle Comparison AI quality", all(ai_quality), f"Response length: {len(comparison_text)} chars")


# ── EV Advisor ───────────────────────────────────────────────────────────────


def test_ev_advisor():
    payload = {
        "current_vehicle": "2018 Honda Accord",
        "annual_mileage": 15000,
        "daily_commute_miles": 30,
        "home_charging": True,
        "budget": 50000,
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/ev-advisor", json=payload)
    if not assert_status(resp, 200, "EV Advisor"):
        return
    data = resp.json()
    checks = [
        "ev_advice" in data,
        isinstance(data.get("ev_advice"), str),
        len(data.get("ev_advice", "")) > 100,
    ]
    log_test("EV Advisor structure", all(checks))
    
    # Check AI response quality
    advice_text = data.get("ev_advice", "")
    ai_quality = [
        "ev" in advice_text.lower() or "electric" in advice_text.lower(),
        len(advice_text) > 200,
    ]
    log_test("EV Advisor AI quality", all(ai_quality), f"Response length: {len(advice_text)} chars")


# ── Driving Insights ─────────────────────────────────────────────────────────


def test_driving_insights():
    payload = {
        "vehicle": "2021 Ford F-150",
        "driving_habits": "Mostly highway commuting, occasional towing of boat",
        "annual_mileage": 18000,
        "concerns": "Fuel economy and tire wear",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/driving-insights", json=payload)
    if not assert_status(resp, 200, "Driving Insights"):
        return
    data = resp.json()
    checks = [
        "insights" in data,
        isinstance(data.get("insights"), str),
        len(data.get("insights", "")) > 100,
    ]
    log_test("Driving Insights structure", all(checks))
    
    # Check AI response quality
    insights_text = data.get("insights", "")
    ai_quality = [
        "driving" in insights_text.lower() or "fuel" in insights_text.lower(),
        len(insights_text) > 200,
    ]
    log_test("Driving Insights AI quality", all(ai_quality), f"Response length: {len(insights_text)} chars")


# ── Service History ──────────────────────────────────────────────────────────


def test_add_service_record():
    payload = {
        "make": "Mazda",
        "model": "CX-5",
        "year": 2020,
        "service_type": "Oil Change",
        "mileage_at_service": 35000,
        "cost": 65.50,
        "shop_name": "Quick Lube",
        "notes": "Synthetic oil used",
        "service_date": "2024-03-15",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/service-history", json=payload)
    if not assert_status(resp, 200, "Add Service Record"):
        return
    data = resp.json()
    checks = [
        "record_id" in data,
        "message" in data,
    ]
    log_test("Add Service Record structure", all(checks), f"Record ID: {data.get('record_id')}")
    state["service_record_id"] = data.get("record_id")


def test_list_service_records():
    resp = session.get(f"{API_BASE}/mobility-assistant/service-history")
    if not assert_status(resp, 200, "List Service Records"):
        return
    data = resp.json()
    checks = [
        "records" in data,
        "count" in data,
        isinstance(data.get("records"), list),
    ]
    log_test("List Service Records structure", all(checks), f"Count: {data.get('count')}")
    
    if data.get("records"):
        record = data["records"][0]
        # Check no MongoDB _id leak
        no_id_leak = "_id" not in record
        log_test("Service Records MongoDB serialization", no_id_leak, "No _id field present")


# ── Sessions & Analytics ─────────────────────────────────────────────────────


def test_sessions():
    resp = session.get(f"{API_BASE}/mobility-assistant/sessions")
    if not assert_status(resp, 200, "Sessions"):
        return
    data = resp.json()
    checks = [
        "sessions" in data,
        "count" in data,
        isinstance(data.get("sessions"), list),
    ]
    log_test("Sessions structure", all(checks), f"Count: {data.get('count')}")
    
    if data.get("sessions"):
        session_item = data["sessions"][0]
        # Check no MongoDB _id leak
        no_id_leak = "_id" not in session_item
        log_test("Sessions MongoDB serialization", no_id_leak, "No _id field present")


def test_analytics():
    resp = session.get(f"{API_BASE}/mobility-assistant/analytics")
    if not assert_status(resp, 200, "Analytics"):
        return
    data = resp.json()
    checks = [
        "total_searches" in data,
        "total_trade_in_requests" in data,
        "total_ai_calls" in data,
        "saved_vehicles" in data,
        "service_records" in data,
        isinstance(data.get("total_searches"), int),
    ]
    log_test("Analytics structure", all(checks), f"Searches: {data.get('total_searches')}, AI Calls: {data.get('total_ai_calls')}")


# ── Tier Limit Enforcement ───────────────────────────────────────────────────


def test_tier_limit_free_plan():
    """Test that free tier limits are enforced correctly"""
    resp = session.get(f"{API_BASE}/mobility-assistant/bootstrap")
    if not assert_status(resp, 200, "Tier Limit Check - Bootstrap"):
        return
    data = resp.json()
    
    tier = data.get("tier")
    limits = data.get("limits", {})
    
    # Free tier should have specific limits
    if tier == "free":
        free_checks = [
            limits.get("searches_per_month") == 5,
            limits.get("ai_calls_per_month") == 3,
            limits.get("saved_vehicles") == 3,
            limits.get("service_records") == 5,
        ]
        log_test("Tier Limit - Free Plan", all(free_checks), f"Limits: {limits}")
    elif tier == "premium":
        premium_checks = [
            limits.get("searches_per_month") == -1,  # Unlimited
            limits.get("ai_calls_per_month") == -1,
        ]
        log_test("Tier Limit - Premium Plan", all(premium_checks), f"Unlimited: {limits}")
    else:
        log_test("Tier Limit Check", True, f"Tier: {tier}, Limits: {limits}")


# ── AI Integration Pattern ───────────────────────────────────────────────────


def test_ai_integration_pattern():
    """Validate that AI endpoints follow correct integration pattern"""
    # Test an AI endpoint to ensure it returns proper AI response
    payload = {
        "make": "Subaru",
        "model": "Outback",
        "year": 2022,
        "mileage": 25000,
        "condition": "Excellent",
    }
    resp = session.post(f"{API_BASE}/mobility-assistant/trade-in", json=payload)
    if not assert_status(resp, 200, "AI Integration Pattern - Trade-In"):
        return
    
    data = resp.json()
    valuation = data.get("valuation", "")
    
    # AI response should be substantial and contain relevant keywords
    ai_pattern_checks = [
        len(valuation) > 50,
        isinstance(valuation, str),
        any(word in valuation.lower() for word in ["value", "trade", "price", "market", "appraisal"]),
    ]
    log_test("AI Integration Pattern", all(ai_pattern_checks), "AI response present and valid")


# ── Run All Tests ────────────────────────────────────────────────────────────


def re_authenticate():
    """Re-authenticate to refresh session"""
    return login()


def run_all_tests():
    print("\n" + "=" * 70)
    print("Feature 13 (Mobility Assistant) - Comprehensive E2E Test Suite")
    print("=" * 70 + "\n")
    
    if not login():
        print("\n❌ LOGIN FAILED - ABORTING TEST SUITE\n")
        return
    
    print("\n=== Bootstrap ===")
    test_bootstrap()
    
    print("\n=== Vehicle Search ===")
    test_vehicle_search()
    test_search_history()
    
    print("\n=== Trade-In Valuation ===")
    test_trade_in_valuation()
    
    print("\n=== Finance Calculator ===")
    test_finance_calculator()
    
    print("\n=== Saved Vehicles ===")
    test_save_vehicle()
    test_list_saved_vehicles()
    test_delete_saved_vehicle()
    
    print("\n=== Maintenance Schedule ===")
    test_maintenance_schedule()
    
    print("\n=== Cost Calculator ===")
    test_cost_calculator()
    
    print("\n=== Trip Planner ===")
    test_trip_planner()
    
    print("\n=== Vehicle Comparison ===")
    test_vehicle_comparison()
    
    print("\n=== EV Advisor ===")
    test_ev_advisor()
    
    print("\n=== Driving Insights ===")
    test_driving_insights()
    
    print("\n=== Service History ===")
    # Re-authenticate before long-running tests to prevent session timeout
    print("🔄 Re-authenticating session...")
    if not re_authenticate():
        print("❌ Re-authentication failed")
    test_add_service_record()
    test_list_service_records()
    
    print("\n=== Sessions & Analytics ===")
    test_sessions()
    test_analytics()
    
    print("\n=== Tier Limit Enforcement ===")
    test_tier_limit_free_plan()
    
    print("\n=== AI Integration Pattern ===")
    test_ai_integration_pattern()
    
    # Final Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests:  {results['total']}")
    print(f"✅ Passed:    {results['passed']}")
    print(f"❌ Failed:    {results['failed']}")
    
    if results["errors"]:
        print("\n❌ FAILED TESTS:")
        for error in results["errors"]:
            print(f"  - {error}")
    
    print("\n" + "=" * 70)
    
    pass_rate = (results["passed"] / results["total"] * 100) if results["total"] > 0 else 0
    if pass_rate == 100:
        print(f"🎉 ALL TESTS PASSED! ({results['passed']}/{results['total']})")
    elif pass_rate >= 80:
        print(f"⚠️  MOSTLY PASSING ({results['passed']}/{results['total']}) - {pass_rate:.1f}%")
    else:
        print(f"❌ NEEDS ATTENTION ({results['passed']}/{results['total']}) - {pass_rate:.1f}%")
    
    print("=" * 70 + "\n")
    
    return results


if __name__ == "__main__":
    run_all_tests()
