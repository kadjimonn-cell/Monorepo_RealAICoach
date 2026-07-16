"""
Feature 7 Phase 2B - Health Guide Export & Nudges Backend E2E Tests

Tests:
- PART 1: Health Data Export (6 endpoints)
- PART 2: Proactive Health Nudges (4 endpoints)

Test Credentials:
- Email: admin@realaicoach.app
- Password: NewAdminPass2026!
"""

import requests
import json
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://coach-web-preview.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api/health-guide"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Test state
session = requests.Session()
test_results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
test_data = {"nudge_id": None}


def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result."""
    test_results["total"] += 1
    if passed:
        test_results["passed"] += 1
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   {details}")
    else:
        test_results["failed"] += 1
        test_results["errors"].append(f"{test_name}: {details}")
        print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   {details}")


def test_login():
    """Test 0: Login as admin user."""
    print("\n" + "="*80)
    print("TEST 0: Login as Admin User")
    print("="*80)
    
    try:
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 200:
            data = response.json()
            log_test("Login", True, f"Logged in as {data.get('user', {}).get('email', 'admin')}")
            return True
        else:
            log_test("Login", False, f"Status {response.status_code}")
            return False
    except Exception as e:
        log_test("Login", False, str(e))
        return False


def setup_test_data():
    """Setup test data for export testing."""
    print("\n" + "="*80)
    print("SETUP: Creating Test Data")
    print("="*80)
    
    try:
        # Create/update profile
        session.post(
            f"{API_BASE}/profile",
            json={"age": 35, "gender": "male", "height_cm": 180, "weight_kg": 80},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        # Create wearable data
        session.post(
            f"{API_BASE}/wearable-data",
            json={
                "data_type": "heart_rate",
                "device": "Apple Watch",
                "readings": [{"timestamp": datetime.now(timezone.utc).isoformat(), "value": 72}]
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        # Generate insight
        session.post(
            f"{API_BASE}/insights",
            json={"concern": "General wellness check"},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        print("✅ Test data created")
        return True
    except Exception as e:
        print(f"❌ Setup failed: {str(e)}")
        return False


# ══════════ PART 1: HEALTH DATA EXPORT TESTS ══════════

def test_export_profile_json():
    """Test 1: Export health profile in JSON format."""
    print("\n" + "="*80)
    print("TEST 1: Export Health Profile (JSON)")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/profile", params={"format": "json"})
        
        if response.status_code != 200:
            log_test("Export Profile (JSON)", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert data["format"] == "json"
        assert "data" in data and "exported_at" in data and "filename" in data
        assert data["filename"].endswith(".json")
        
        profile_data = data["data"]
        assert "owner_id" in profile_data and "age" in profile_data and "bmi" in profile_data
        
        log_test("Export Profile (JSON)", True, f"Filename: {data['filename']}")
    except Exception as e:
        log_test("Export Profile (JSON)", False, str(e))


def test_export_profile_csv():
    """Test 2: Export health profile in CSV format."""
    print("\n" + "="*80)
    print("TEST 2: Export Health Profile (CSV)")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/profile", params={"format": "csv"})
        
        if response.status_code != 200:
            log_test("Export Profile (CSV)", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert data["format"] == "csv"
        assert "data" in data and "filename" in data
        assert data["filename"].endswith(".csv")
        
        csv_data = data["data"]
        assert csv_data.startswith("field,value\n")
        assert "age," in csv_data and "bmi," in csv_data
        
        log_test("Export Profile (CSV)", True, f"Filename: {data['filename']}")
    except Exception as e:
        log_test("Export Profile (CSV)", False, str(e))


def test_export_wearable_data_csv():
    """Test 3: Export wearable data in CSV format."""
    print("\n" + "="*80)
    print("TEST 3: Export Wearable Data (CSV)")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/wearable-data", params={"days": 30, "format": "csv"})
        
        if response.status_code != 200:
            log_test("Export Wearable Data (CSV)", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert data["format"] == "csv"
        assert "data" in data and "records" in data and "filename" in data
        
        csv_data = data["data"]
        assert csv_data.startswith("log_id,data_type,device,logged_at,reading_timestamp,reading_value\n")
        
        log_test("Export Wearable Data (CSV)", True, f"Records: {data['records']}")
    except Exception as e:
        log_test("Export Wearable Data (CSV)", False, str(e))


def test_export_wearable_data_json():
    """Test 4: Export wearable data in JSON format."""
    print("\n" + "="*80)
    print("TEST 4: Export Wearable Data (JSON)")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/wearable-data", params={"days": 7, "format": "json"})
        
        if response.status_code != 200:
            log_test("Export Wearable Data (JSON)", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert data["format"] == "json"
        assert "data" in data and "records" in data and "period_days" in data
        assert data["period_days"] == 7
        
        log_test("Export Wearable Data (JSON)", True, f"Records: {data['records']}, Period: {data['period_days']} days")
    except Exception as e:
        log_test("Export Wearable Data (JSON)", False, str(e))


def test_export_insights_history():
    """Test 5: Export health insights history."""
    print("\n" + "="*80)
    print("TEST 5: Export Insights History")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/insights", params={"days": 90})
        
        if response.status_code != 200:
            log_test("Export Insights History", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert "format" in data and "data" in data and "records" in data
        assert "period_days" in data and data["period_days"] == 90
        
        log_test("Export Insights History", True, f"Records: {data['records']}, Period: {data['period_days']} days")
    except Exception as e:
        log_test("Export Insights History", False, str(e))


def test_export_comprehensive_report():
    """Test 6: Export comprehensive health report (Premium only)."""
    print("\n" + "="*80)
    print("TEST 6: Export Comprehensive Report")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/export/comprehensive", params={"days": 30})
        
        if response.status_code != 200:
            log_test("Export Comprehensive Report", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert data["format"] == "json"
        assert "report" in data and "exported_at" in data
        
        report = data["report"]
        assert report["report_type"] == "comprehensive_health_report"
        assert "period_days" in report and report["period_days"] == 30
        
        # Verify all data sections
        required_sections = ["profile", "summary", "wearable_data", "medications", 
                           "medication_logs", "health_goals", "goal_progress", 
                           "health_insights", "symptom_checks"]
        for section in required_sections:
            assert section in report, f"Missing section: {section}"
        
        # Verify summary statistics
        summary = report["summary"]
        required_stats = ["wearable_logs", "active_medications", "medication_doses_logged",
                         "active_goals", "goal_progress_entries", "health_insights_generated",
                         "symptom_checks_performed"]
        for stat in required_stats:
            assert stat in summary, f"Missing stat: {stat}"
        
        log_test("Export Comprehensive Report", True, f"Period: {report['period_days']} days, Sections: {len(required_sections)}")
    except Exception as e:
        log_test("Export Comprehensive Report", False, str(e))


# ══════════ PART 2: PROACTIVE HEALTH NUDGES TESTS ══════════

def test_generate_health_nudges():
    """Test 7: Generate AI-powered health nudges."""
    print("\n" + "="*80)
    print("TEST 7: Generate Health Nudges (AI)")
    print("="*80)
    
    try:
        response = session.post(
            f"{API_BASE}/nudges/generate",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code != 200:
            log_test("Generate Health Nudges", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert "message" in data and "nudges" in data and "tier" in data
        
        nudges = data["nudges"]
        assert len(nudges) >= 3 and len(nudges) <= 5, f"Expected 3-5 nudges, got {len(nudges)}"
        
        # Verify nudge structure
        for nudge in nudges:
            assert "nudge_id" in nudge
            assert "type" in nudge and nudge["type"] in ["medication", "activity", "hydration", "sleep", "goal"]
            assert "priority" in nudge and nudge["priority"] in ["high", "medium", "low"]
            assert "title" in nudge and "message" in nudge and "action_button" in nudge
            assert "status" in nudge and nudge["status"] == "active"
        
        # Store first nudge_id for later tests
        test_data["nudge_id"] = nudges[0]["nudge_id"]
        
        log_test("Generate Health Nudges", True, f"Generated {len(nudges)} nudges, Sample: {nudges[0]['title']}")
    except Exception as e:
        log_test("Generate Health Nudges", False, str(e))


def test_get_active_nudges():
    """Test 8: Get list of active nudges."""
    print("\n" + "="*80)
    print("TEST 8: Get Active Nudges")
    print("="*80)
    
    try:
        response = session.get(f"{API_BASE}/nudges", params={"status": "active", "limit": 10})
        
        if response.status_code != 200:
            log_test("Get Active Nudges", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert "nudges" in data and "count" in data and "status_filter" in data
        assert data["status_filter"] == "active"
        
        nudges = data["nudges"]
        assert len(nudges) > 0, "Expected at least 1 active nudge"
        assert data["count"] == len(nudges)
        
        log_test("Get Active Nudges", True, f"Count: {data['count']}")
    except Exception as e:
        log_test("Get Active Nudges", False, str(e))


def test_mark_nudge_completed():
    """Test 9: Mark nudge as completed."""
    print("\n" + "="*80)
    print("TEST 9: Mark Nudge Completed")
    print("="*80)
    
    try:
        nudge_id = test_data["nudge_id"]
        if not nudge_id:
            log_test("Mark Nudge Completed", False, "No nudge_id available")
            return
        
        response = session.post(
            f"{API_BASE}/nudges/{nudge_id}/action",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code != 200:
            log_test("Mark Nudge Completed", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert "message" in data and "nudge_id" in data
        assert data["nudge_id"] == nudge_id
        
        # Verify nudge status changed to completed
        verify_response = session.get(f"{API_BASE}/nudges", params={"status": "completed", "limit": 10})
        completed_nudges = verify_response.json()["nudges"]
        completed_ids = [n["nudge_id"] for n in completed_nudges]
        assert nudge_id in completed_ids, "Nudge should be in completed list"
        
        log_test("Mark Nudge Completed", True, f"Nudge ID: {nudge_id}")
    except Exception as e:
        log_test("Mark Nudge Completed", False, str(e))


def test_update_nudge_preferences():
    """Test 10: Update nudge preferences."""
    print("\n" + "="*80)
    print("TEST 10: Update Nudge Preferences")
    print("="*80)
    
    try:
        preferences = {
            "enabled_types": ["medication", "activity", "sleep"],
            "frequency": "normal",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
        
        response = session.put(
            f"{API_BASE}/nudges/preferences",
            params=preferences,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code != 200:
            log_test("Update Nudge Preferences", False, f"Status {response.status_code}")
            return
        
        data = response.json()
        assert "message" in data and "preferences" in data
        
        prefs = data["preferences"]
        assert "enabled_types" in prefs and set(prefs["enabled_types"]) == set(preferences["enabled_types"])
        assert prefs["frequency"] == preferences["frequency"]
        assert prefs["quiet_hours_start"] == preferences["quiet_hours_start"]
        assert prefs["quiet_hours_end"] == preferences["quiet_hours_end"]
        
        log_test("Update Nudge Preferences", True, f"Enabled types: {prefs['enabled_types']}")
    except Exception as e:
        log_test("Update Nudge Preferences", False, str(e))


def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("FEATURE 7 PHASE 2B - EXPORT & NUDGES BACKEND E2E TEST SUMMARY")
    print("="*80)
    print(f"\nTotal Tests: {test_results['total']}")
    print(f"Passed: {test_results['passed']}")
    print(f"Failed: {test_results['failed']}")
    
    if test_results['failed'] > 0:
        print("\n❌ FAILED TESTS:")
        for error in test_results['errors']:
            print(f"   - {error}")
    else:
        print("\n✅ ALL TESTS PASSED!")
    
    print("\n" + "="*80)
    
    success_rate = (test_results['passed'] / test_results['total'] * 100) if test_results['total'] > 0 else 0
    print(f"Success Rate: {success_rate:.1f}%")
    print("="*80 + "\n")


if __name__ == "__main__":
    # Run all tests
    if test_login():
        setup_test_data()
        
        # Part 1: Export tests
        test_export_profile_json()
        test_export_profile_csv()
        test_export_wearable_data_csv()
        test_export_wearable_data_json()
        test_export_insights_history()
        test_export_comprehensive_report()
        
        # Part 2: Nudges tests
        test_generate_health_nudges()
        test_get_active_nudges()
        test_mark_nudge_completed()
        test_update_nudge_preferences()
    
    print_summary()
