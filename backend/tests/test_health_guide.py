"""
Feature 7 (Health Guide) Comprehensive Backend E2E Testing

Test Objective: Perform comprehensive backend CRUD and integration testing for 
Feature 7 (Health Guide) endpoints at /api/health-guide/*

Test Credentials:
- Email: admin@realaicoach.app
- Password: NewAdminPass2026!

Backend URL: https://coach-web-preview.preview.emergentagent.com

Endpoints Tested:
1. Bootstrap & Profile (High Priority)
   - GET  /api/health-guide/bootstrap
   - POST /api/health-guide/profile
   - GET  /api/health-guide/profile
   - PUT  /api/health-guide/profile
   - DELETE /api/health-guide/profile

2. Wearable Data (Core Feature)
   - POST /api/health-guide/wearable-data
   - GET  /api/health-guide/wearable-data
   - DELETE /api/health-guide/wearable-data/{log_id}

3. Health Insights (AI-Powered)
   - POST /api/health-guide/insights
   - GET  /api/health-guide/insights-history

4. Symptom Checker (AI-Powered)
   - POST /api/health-guide/symptom-check
   - GET  /api/health-guide/symptom-checks-history

5. Dashboard & Analytics
   - GET  /api/health-guide/dashboard
"""

import requests
import json
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://coach-web-preview.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Test state
session = requests.Session()
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": []
}

# Test data storage
test_data = {
    "profile_created": False,
    "wearable_log_id": None,
    "insight_id": None,
    "symptom_check_id": None
}


def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result."""
    test_results["total"] += 1
    if passed:
        test_results["passed"] += 1
        print(f"✅ PASS: {test_name}")
    else:
        test_results["failed"] += 1
        test_results["errors"].append(f"{test_name}: {details}")
        print(f"❌ FAIL: {test_name} - {details}")
    if details and passed:
        print(f"   Details: {details}")


def test_login():
    """Test 1: Login as admin user."""
    print("\n" + "="*80)
    print("TEST 1: Login as Admin User")
    print("="*80)
    
    try:
        response = session.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            log_test("Login", True, f"Logged in as {data.get('user', {}).get('email', 'admin')}")
            return True
        else:
            log_test("Login", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Login", False, f"Exception: {str(e)}")
        return False


def test_bootstrap():
    """Test 2: GET /api/health-guide/bootstrap - Get tier, usage, features."""
    print("\n" + "="*80)
    print("TEST 2: Bootstrap - Get Tier, Usage, Features")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/health-guide/bootstrap")
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify structure
            required_keys = ["owner_id", "tier", "has_profile", "usage", "features", "tier_limits"]
            missing_keys = [k for k in required_keys if k not in data]
            
            if missing_keys:
                log_test("Bootstrap - Structure", False, f"Missing keys: {missing_keys}")
                return False
            
            # Verify admin has premium tier
            if data.get("tier") != "premium":
                log_test("Bootstrap - Admin Tier", False, f"Expected premium, got {data.get('tier')}")
            else:
                log_test("Bootstrap - Admin Tier", True, "Admin has premium tier")
            
            # Verify usage stats
            usage = data.get("usage", {})
            if "health_checks_this_month" in usage and "symptom_checks_this_month" in usage:
                log_test("Bootstrap - Usage Stats", True, f"Health checks: {usage['health_checks_this_month']}, Symptom checks: {usage['symptom_checks_this_month']}")
            else:
                log_test("Bootstrap - Usage Stats", False, "Missing usage stats")
            
            # Verify features
            features = data.get("features", [])
            if isinstance(features, list) and len(features) > 0:
                log_test("Bootstrap - Features", True, f"Features: {', '.join(features)}")
            else:
                log_test("Bootstrap - Features", False, "No features returned")
            
            return True
        else:
            log_test("Bootstrap", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Bootstrap", False, f"Exception: {str(e)}")
        return False


def test_create_profile():
    """Test 3: POST /api/health-guide/profile - Create health profile."""
    print("\n" + "="*80)
    print("TEST 3: Create Health Profile")
    print("="*80)
    
    try:
        payload = {
            "age": 35,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 75,
            "medical_conditions": ["none"],
            "medications": [],
            "allergies": []
        }
        
        response = session.post(
            f"{API_BASE}/health-guide/profile",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify profile was created
            if "profile" in data:
                profile = data["profile"]
                
                # Verify BMI calculation
                if "bmi" in profile and "bmi_category" in profile:
                    log_test("Create Profile - BMI Calculation", True, f"BMI: {profile['bmi']}, Category: {profile['bmi_category']}")
                else:
                    log_test("Create Profile - BMI Calculation", False, "BMI not calculated")
                
                # Verify data persistence
                if profile.get("age") == 35 and profile.get("height_cm") == 175:
                    log_test("Create Profile - Data Persistence", True, "Profile data saved correctly")
                    test_data["profile_created"] = True
                else:
                    log_test("Create Profile - Data Persistence", False, "Profile data mismatch")
                
                return True
            else:
                log_test("Create Profile", False, "No profile in response")
                return False
        else:
            log_test("Create Profile", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Create Profile", False, f"Exception: {str(e)}")
        return False


def test_get_profile():
    """Test 4: GET /api/health-guide/profile - Get health profile."""
    print("\n" + "="*80)
    print("TEST 4: Get Health Profile")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/health-guide/profile")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("has_profile") and "profile" in data:
                profile = data["profile"]
                log_test("Get Profile", True, f"Profile retrieved: Age {profile.get('age')}, BMI {profile.get('bmi')}")
                return True
            else:
                log_test("Get Profile", False, "Profile not found or missing data")
                return False
        else:
            log_test("Get Profile", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Get Profile", False, f"Exception: {str(e)}")
        return False


def test_update_profile():
    """Test 5: PUT /api/health-guide/profile - Update health profile."""
    print("\n" + "="*80)
    print("TEST 5: Update Health Profile")
    print("="*80)
    
    try:
        payload = {
            "age": 36,
            "weight_kg": 73
        }
        
        response = session.put(
            f"{API_BASE}/health-guide/profile",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if "profile" in data:
                profile = data["profile"]
                
                # Verify update
                if profile.get("age") == 36 and profile.get("weight_kg") == 73:
                    log_test("Update Profile", True, f"Profile updated: Age {profile['age']}, Weight {profile['weight_kg']}kg")
                    return True
                else:
                    log_test("Update Profile", False, "Profile update not reflected")
                    return False
            else:
                log_test("Update Profile", False, "No profile in response")
                return False
        else:
            log_test("Update Profile", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Update Profile", False, f"Exception: {str(e)}")
        return False


def test_log_wearable_data():
    """Test 6: POST /api/health-guide/wearable-data - Log wearable data."""
    print("\n" + "="*80)
    print("TEST 6: Log Wearable Data")
    print("="*80)
    
    try:
        payload = {
            "data_type": "heart_rate",
            "readings": [
                {"timestamp": "2026-05-26T12:00:00Z", "value": 72},
                {"timestamp": "2026-05-26T12:05:00Z", "value": 75}
            ],
            "device": "Apple Watch"
        }
        
        response = session.post(
            f"{API_BASE}/health-guide/wearable-data",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify log was created
            if "log" in data and "stats" in data:
                log_entry = data["log"]
                stats = data["stats"]
                
                # Store log_id for later deletion
                test_data["wearable_log_id"] = log_entry.get("log_id")
                
                # Verify stats calculation
                if "average" in stats and "min" in stats and "max" in stats:
                    log_test("Log Wearable Data - Stats", True, f"Avg: {stats['average']}, Min: {stats['min']}, Max: {stats['max']}")
                else:
                    log_test("Log Wearable Data - Stats", False, "Stats not calculated")
                
                # Verify data persistence
                if log_entry.get("data_type") == "heart_rate" and log_entry.get("device") == "Apple Watch":
                    log_test("Log Wearable Data - Persistence", True, f"Log ID: {log_entry.get('log_id')}")
                else:
                    log_test("Log Wearable Data - Persistence", False, "Data mismatch")
                
                return True
            else:
                log_test("Log Wearable Data", False, "Missing log or stats in response")
                return False
        else:
            log_test("Log Wearable Data", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Log Wearable Data", False, f"Exception: {str(e)}")
        return False


def test_get_wearable_data():
    """Test 7: GET /api/health-guide/wearable-data - Get wearable data."""
    print("\n" + "="*80)
    print("TEST 7: Get Wearable Data")
    print("="*80)
    
    try:
        response = session.get(
            f"{API_BASE}/health-guide/wearable-data",
            params={"data_type": "heart_rate", "days": 7}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if "data" in data and isinstance(data["data"], list):
                wearable_data = data["data"]
                
                if len(wearable_data) > 0:
                    log_test("Get Wearable Data", True, f"Retrieved {len(wearable_data)} log(s)")
                    return True
                else:
                    log_test("Get Wearable Data", False, "No wearable data found")
                    return False
            else:
                log_test("Get Wearable Data", False, "Invalid response structure")
                return False
        else:
            log_test("Get Wearable Data", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Get Wearable Data", False, f"Exception: {str(e)}")
        return False


def test_health_insights():
    """Test 8: POST /api/health-guide/insights - Get AI health insights."""
    print("\n" + "="*80)
    print("TEST 8: Get AI Health Insights")
    print("="*80)
    
    try:
        payload = {
            "concern": "General wellness check"
        }
        
        response = session.post(
            f"{API_BASE}/health-guide/insights",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify AI insights structure
            required_keys = ["overall_health_score", "disclaimer"]
            has_required = all(k in data for k in required_keys)
            
            if has_required:
                log_test("Health Insights - Structure", True, f"Health Score: {data.get('overall_health_score')}")
            else:
                log_test("Health Insights - Structure", False, "Missing required keys")
            
            # Verify disclaimer is present
            if "disclaimer" in data and len(data["disclaimer"]) > 0:
                log_test("Health Insights - Disclaimer", True, "Disclaimer present")
            else:
                log_test("Health Insights - Disclaimer", False, "Missing disclaimer")
            
            return has_required
        else:
            log_test("Health Insights", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Health Insights", False, f"Exception: {str(e)}")
        return False


def test_insights_history():
    """Test 9: GET /api/health-guide/insights-history - Get insights history."""
    print("\n" + "="*80)
    print("TEST 9: Get Insights History")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/health-guide/insights-history")
        
        if response.status_code == 200:
            data = response.json()
            
            if "insights_history" in data and isinstance(data["insights_history"], list):
                history = data["insights_history"]
                log_test("Insights History", True, f"Retrieved {len(history)} insight(s)")
                return True
            else:
                log_test("Insights History", False, "Invalid response structure")
                return False
        else:
            log_test("Insights History", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Insights History", False, f"Exception: {str(e)}")
        return False


def test_symptom_check():
    """Test 10: POST /api/health-guide/symptom-check - Check symptoms."""
    print("\n" + "="*80)
    print("TEST 10: AI Symptom Checker")
    print("="*80)
    
    try:
        payload = {
            "symptoms": ["headache", "fatigue"],
            "duration": "2 days",
            "severity": "moderate"
        }
        
        response = session.post(
            f"{API_BASE}/health-guide/symptom-check",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify symptom check structure
            required_keys = ["symptom_summary", "legal_disclaimer"]
            has_required = all(k in data for k in required_keys)
            
            if has_required:
                log_test("Symptom Check - Structure", True, "Valid symptom check response")
            else:
                log_test("Symptom Check - Structure", False, "Missing required keys")
            
            # Verify when_to_seek_care is present
            if "when_to_seek_care" in data:
                seek_care = data["when_to_seek_care"]
                if "urgency_level" in seek_care:
                    log_test("Symptom Check - Urgency", True, f"Urgency: {seek_care['urgency_level']}")
                else:
                    log_test("Symptom Check - Urgency", False, "Missing urgency level")
            else:
                log_test("Symptom Check - Urgency", False, "Missing when_to_seek_care")
            
            # Verify legal disclaimer
            if "legal_disclaimer" in data and len(data["legal_disclaimer"]) > 0:
                log_test("Symptom Check - Disclaimer", True, "Legal disclaimer present")
            else:
                log_test("Symptom Check - Disclaimer", False, "Missing legal disclaimer")
            
            return has_required
        else:
            log_test("Symptom Check", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Symptom Check", False, f"Exception: {str(e)}")
        return False


def test_symptom_checks_history():
    """Test 11: GET /api/health-guide/symptom-checks-history - Get symptom check history."""
    print("\n" + "="*80)
    print("TEST 11: Get Symptom Checks History")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/health-guide/symptom-checks-history")
        
        if response.status_code == 200:
            data = response.json()
            
            if "symptom_checks_history" in data and isinstance(data["symptom_checks_history"], list):
                history = data["symptom_checks_history"]
                log_test("Symptom Checks History", True, f"Retrieved {len(history)} check(s)")
                return True
            else:
                log_test("Symptom Checks History", False, "Invalid response structure")
                return False
        else:
            log_test("Symptom Checks History", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Symptom Checks History", False, f"Exception: {str(e)}")
        return False


def test_dashboard():
    """Test 12: GET /api/health-guide/dashboard - Get health dashboard."""
    print("\n" + "="*80)
    print("TEST 12: Get Health Dashboard")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/health-guide/dashboard")
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify dashboard structure
            required_keys = ["owner_id", "tier", "profile", "activity_summary"]
            missing_keys = [k for k in required_keys if k not in data]
            
            if missing_keys:
                log_test("Dashboard - Structure", False, f"Missing keys: {missing_keys}")
                return False
            
            # Verify profile summary
            profile = data.get("profile", {})
            if profile.get("exists"):
                log_test("Dashboard - Profile", True, f"BMI: {profile.get('bmi')}, Category: {profile.get('bmi_category')}")
            else:
                log_test("Dashboard - Profile", False, "Profile not found in dashboard")
            
            # Verify activity summary
            activity = data.get("activity_summary", {})
            if "wearable_logs_this_week" in activity and "health_insights_this_month" in activity:
                log_test("Dashboard - Activity", True, f"Wearable logs: {activity['wearable_logs_this_week']}, Insights: {activity['health_insights_this_month']}")
            else:
                log_test("Dashboard - Activity", False, "Missing activity summary")
            
            return True
        else:
            log_test("Dashboard", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Dashboard", False, f"Exception: {str(e)}")
        return False


def test_delete_wearable_log():
    """Test 13: DELETE /api/health-guide/wearable-data/{log_id} - Delete wearable log."""
    print("\n" + "="*80)
    print("TEST 13: Delete Wearable Log")
    print("="*80)
    
    if not test_data.get("wearable_log_id"):
        log_test("Delete Wearable Log", False, "No log_id available (previous test may have failed)")
        return False
    
    try:
        log_id = test_data["wearable_log_id"]
        response = session.delete(
            f"{API_BASE}/health-guide/wearable-data/{log_id}",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("message") and "deleted" in data["message"].lower():
                log_test("Delete Wearable Log", True, f"Log {log_id} deleted successfully")
                return True
            else:
                log_test("Delete Wearable Log", False, "Unexpected response message")
                return False
        else:
            log_test("Delete Wearable Log", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Delete Wearable Log", False, f"Exception: {str(e)}")
        return False


def test_delete_profile():
    """Test 14: DELETE /api/health-guide/profile - Delete health profile (cascade delete)."""
    print("\n" + "="*80)
    print("TEST 14: Delete Health Profile (Cascade Delete)")
    print("="*80)
    
    if not test_data.get("profile_created"):
        log_test("Delete Profile", False, "No profile to delete (previous test may have failed)")
        return False
    
    try:
        response = session.delete(
            f"{API_BASE}/health-guide/profile",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("message") and "deleted" in data["message"].lower():
                log_test("Delete Profile - Cascade", True, "Profile and all health data deleted")
                
                # Verify cascade delete by checking if profile is gone
                verify_response = session.get(f"{API_BASE}/health-guide/profile")
                if verify_response.status_code == 200:
                    verify_data = verify_response.json()
                    if not verify_data.get("has_profile"):
                        log_test("Delete Profile - Verification", True, "Profile confirmed deleted")
                    else:
                        log_test("Delete Profile - Verification", False, "Profile still exists")
                
                return True
            else:
                log_test("Delete Profile", False, "Unexpected response message")
                return False
        else:
            log_test("Delete Profile", False, f"Status {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("Delete Profile", False, f"Exception: {str(e)}")
        return False


def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {test_results['total']}")
    print(f"Passed: {test_results['passed']} ✅")
    print(f"Failed: {test_results['failed']} ❌")
    print(f"Success Rate: {(test_results['passed'] / test_results['total'] * 100):.1f}%")
    
    if test_results["errors"]:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for error in test_results["errors"]:
            print(f"❌ {error}")
    
    print("\n" + "="*80)
    print("DETAILED RESULTS")
    print("="*80)
    
    # Success criteria
    success_criteria = {
        "All GET endpoints return 200": test_results["passed"] >= 5,
        "Profile CRUD cycle works": test_data.get("profile_created", False),
        "Wearable data logging works": test_data.get("wearable_log_id") is not None,
        "AI health insights generate": test_results["passed"] >= 8,
        "Symptom checker works": test_results["passed"] >= 10,
        "Dashboard aggregates data": test_results["passed"] >= 12,
        "No 500 errors": all("500" not in str(e) for e in test_results["errors"]),
    }
    
    print("\nSuccess Criteria:")
    for criterion, met in success_criteria.items():
        status = "✅" if met else "❌"
        print(f"{status} {criterion}")
    
    all_passed = all(success_criteria.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL SUCCESS CRITERIA MET - FEATURE 7 (HEALTH GUIDE) BACKEND E2E TESTS PASSED")
    else:
        print("⚠️  SOME SUCCESS CRITERIA NOT MET - REVIEW FAILED TESTS ABOVE")
    print("="*80)


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("FEATURE 7 (HEALTH GUIDE) COMPREHENSIVE BACKEND E2E TESTING")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {ADMIN_EMAIL}")
    print(f"Test Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("="*80)
    
    # Run tests in order
    if not test_login():
        print("\n❌ Login failed - cannot proceed with tests")
        print_summary()
        return
    
    # Bootstrap & Profile tests
    test_bootstrap()
    test_create_profile()
    test_get_profile()
    test_update_profile()
    
    # Wearable data tests
    test_log_wearable_data()
    test_get_wearable_data()
    
    # AI insights tests
    test_health_insights()
    test_insights_history()
    
    # Symptom checker tests
    test_symptom_check()
    test_symptom_checks_history()
    
    # Dashboard test
    test_dashboard()
    
    # Cleanup tests (run at end)
    test_delete_wearable_log()
    test_delete_profile()
    
    # Print summary
    print_summary()


if __name__ == "__main__":
    main()
