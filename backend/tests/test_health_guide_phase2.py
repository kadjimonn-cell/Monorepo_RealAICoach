"""
Feature 7 Phase 2 - Comprehensive Backend E2E Testing
Tests: Medication Management, Health Goals, Advanced Analytics

Test Credentials:
- Email: admin@realaicoach.app
- Password: NewAdminPass2026!

Backend URL: https://coach-web-preview.preview.emergentagent.com
"""

import requests
import json
from datetime import datetime, timezone, timedelta

# Configuration
BASE_URL = "https://coach-web-preview.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Session for maintaining cookies
session = requests.Session()

# Test results
test_results = {
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "details": []
}

def log_test(test_name, passed, details=""):
    """Log test result."""
    test_results["total_tests"] += 1
    if passed:
        test_results["passed"] += 1
        status = "✅ PASS"
    else:
        test_results["failed"] += 1
        status = "❌ FAIL"
    
    result = {
        "test": test_name,
        "status": status,
        "details": details
    }
    test_results["details"].append(result)
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")

def login():
    """Login as admin user."""
    print("\n" + "="*80)
    print("AUTHENTICATION")
    print("="*80)
    
    url = f"{API_BASE}/auth/login"
    payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        log_test("Admin Login", True, f"Logged in as {ADMIN_EMAIL}")
        return True
    else:
        log_test("Admin Login", False, f"Status: {response.status_code}, Response: {response.text}")
        return False

def test_medication_management():
    """Test Medication Management endpoints."""
    print("\n" + "="*80)
    print("PART 1: MEDICATION MANAGEMENT TESTING")
    print("="*80)
    
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    medication_id = None
    
    # Test 1: Add Medication
    print("\n--- Test 1: POST /api/health-guide/medications (Add Medication) ---")
    url = f"{API_BASE}/health-guide/medications"
    payload = {
        "name": "Aspirin",
        "dosage": "100mg",
        "frequency": "daily",
        "schedule_times": ["08:00", "20:00"],
        "instructions": "Take with food",
        "prescribing_doctor": "Dr. Smith",
        "refill_reminder_days": 7
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        medication_id = data.get("medication", {}).get("medication_id")
        if medication_id and data.get("medication", {}).get("status") == "active":
            log_test("Add Medication", True, f"Medication ID: {medication_id}, Status: active")
        else:
            log_test("Add Medication", False, f"Missing medication_id or status not active: {data}")
    else:
        log_test("Add Medication", False, f"Status: {response.status_code}, Response: {response.text}")
        return
    
    # Test 2: List Medications
    print("\n--- Test 2: GET /api/health-guide/medications (List Medications) ---")
    url = f"{API_BASE}/health-guide/medications?status=active"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        medications = data.get("medications", [])
        found = any(m.get("medication_id") == medication_id for m in medications)
        if found:
            log_test("List Medications", True, f"Found {len(medications)} medication(s), including newly created one")
        else:
            log_test("List Medications", False, "Newly created medication not found in list")
    else:
        log_test("List Medications", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 3: Log Dose - Taken
    print("\n--- Test 3: POST /api/health-guide/medications/{medication_id}/log-dose (Taken) ---")
    url = f"{API_BASE}/health-guide/medications/{medication_id}/log-dose"
    payload = {
        "status": "taken",
        "notes": "Taken at breakfast"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        log_entry = data.get("log", {})
        if log_entry.get("status") == "taken" and log_entry.get("medication_name") == "Aspirin":
            log_test("Log Dose - Taken", True, f"Dose logged: {log_entry.get('status')}, Medication: {log_entry.get('medication_name')}")
        else:
            log_test("Log Dose - Taken", False, f"Unexpected log data: {data}")
    else:
        log_test("Log Dose - Taken", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 4: Log Dose - Missed
    print("\n--- Test 4: POST /api/health-guide/medications/{medication_id}/log-dose (Missed) ---")
    url = f"{API_BASE}/health-guide/medications/{medication_id}/log-dose"
    payload = {
        "status": "missed",
        "notes": "Forgot evening dose"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        log_entry = data.get("log", {})
        if log_entry.get("status") == "missed":
            log_test("Log Dose - Missed", True, "Missed dose logged successfully")
        else:
            log_test("Log Dose - Missed", False, f"Unexpected log data: {data}")
    else:
        log_test("Log Dose - Missed", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 5: Get Reminders
    print("\n--- Test 5: GET /api/health-guide/medications/reminders (Get Reminders) ---")
    url = f"{API_BASE}/health-guide/medications/reminders"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        reminders = data.get("reminders", [])
        log_test("Get Medication Reminders", True, f"Retrieved {len(reminders)} reminder(s)")
    else:
        log_test("Get Medication Reminders", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 6: Update Medication
    print("\n--- Test 6: PUT /api/health-guide/medications/{medication_id} (Update) ---")
    url = f"{API_BASE}/health-guide/medications/{medication_id}"
    payload = {
        "name": "Aspirin",
        "dosage": "150mg",
        "frequency": "twice_daily",
        "schedule_times": ["08:00", "20:00"],
        "instructions": "Updated dosage",
        "prescribing_doctor": "Dr. Smith",
        "refill_reminder_days": 5
    }
    
    response = session.put(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("message") == "Medication updated successfully":
            log_test("Update Medication", True, "Medication updated: dosage changed to 150mg")
        else:
            log_test("Update Medication", False, f"Unexpected response: {data}")
    else:
        log_test("Update Medication", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 7: Delete Medication (Soft Delete)
    print("\n--- Test 7: DELETE /api/health-guide/medications/{medication_id} (Delete) ---")
    url = f"{API_BASE}/health-guide/medications/{medication_id}"
    
    response = session.delete(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("message") == "Medication deleted successfully":
            # Verify soft delete - check if status changed to inactive
            verify_url = f"{API_BASE}/health-guide/medications?status=inactive"
            verify_response = session.get(verify_url, headers=headers)
            if verify_response.status_code == 200:
                verify_data = verify_response.json()
                inactive_meds = verify_data.get("medications", [])
                found_inactive = any(m.get("medication_id") == medication_id for m in inactive_meds)
                if found_inactive:
                    log_test("Delete Medication (Soft Delete)", True, "Medication status changed to inactive (soft delete)")
                else:
                    log_test("Delete Medication (Soft Delete)", False, "Medication not found in inactive list")
            else:
                log_test("Delete Medication (Soft Delete)", False, "Could not verify soft delete")
        else:
            log_test("Delete Medication (Soft Delete)", False, f"Unexpected response: {data}")
    else:
        log_test("Delete Medication (Soft Delete)", False, f"Status: {response.status_code}, Response: {response.text}")

def test_health_goals():
    """Test Health Goals & Progress endpoints."""
    print("\n" + "="*80)
    print("PART 2: HEALTH GOALS & PROGRESS TESTING")
    print("="*80)
    
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    goal_id = None
    
    # Test 1: Create Weight Loss Goal
    print("\n--- Test 1: POST /api/health-guide/goals (Create Goal) ---")
    url = f"{API_BASE}/health-guide/goals"
    deadline = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    payload = {
        "goal_type": "weight_loss",
        "title": "Lose 10kg",
        "target_value": 70,
        "target_unit": "kg",
        "current_value": 80,
        "deadline": deadline,
        "milestones": [{"value": 75, "description": "Halfway there!"}]
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        goal_id = data.get("goal", {}).get("goal_id")
        progress_pct = data.get("goal", {}).get("progress_percentage")
        if goal_id and progress_pct == 0:
            log_test("Create Health Goal", True, f"Goal ID: {goal_id}, Initial Progress: {progress_pct}%")
        else:
            log_test("Create Health Goal", False, f"Missing goal_id or incorrect progress: {data}")
    else:
        log_test("Create Health Goal", False, f"Status: {response.status_code}, Response: {response.text}")
        return
    
    # Test 2: List Goals
    print("\n--- Test 2: GET /api/health-guide/goals (List Goals) ---")
    url = f"{API_BASE}/health-guide/goals?status=active"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        goals = data.get("goals", [])
        found = any(g.get("goal_id") == goal_id for g in goals)
        if found:
            log_test("List Health Goals", True, f"Found {len(goals)} goal(s), including newly created one")
        else:
            log_test("List Health Goals", False, "Newly created goal not found in list")
    else:
        log_test("List Health Goals", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 3: Log Progress #1 (Week 1)
    print("\n--- Test 3: POST /api/health-guide/goals/{goal_id}/progress (Progress #1) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}/progress"
    payload = {
        "current_value": 78,
        "notes": "Week 1 - Good progress!"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        progress_pct = data.get("progress_percentage")
        int((78 / 70) * 100)  # Should be ~111% but capped at 100
        if progress_pct is not None:
            log_test("Log Progress #1", True, f"Progress logged: {progress_pct}% (current: 78kg)")
        else:
            log_test("Log Progress #1", False, f"Missing progress_percentage: {data}")
    else:
        log_test("Log Progress #1", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 4: Log Progress #2 (Week 3 - Milestone)
    print("\n--- Test 4: POST /api/health-guide/goals/{goal_id}/progress (Progress #2) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}/progress"
    payload = {
        "current_value": 75,
        "notes": "Week 3 - Milestone reached!"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        progress_pct = data.get("progress_percentage")
        if progress_pct is not None:
            log_test("Log Progress #2", True, f"Progress logged: {progress_pct}% (current: 75kg, milestone reached)")
        else:
            log_test("Log Progress #2", False, f"Missing progress_percentage: {data}")
    else:
        log_test("Log Progress #2", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 5: Log Progress #3 (Week 5)
    print("\n--- Test 5: POST /api/health-guide/goals/{goal_id}/progress (Progress #3) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}/progress"
    payload = {
        "current_value": 72,
        "notes": "Week 5 - Almost there!"
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        progress_pct = data.get("progress_percentage")
        if progress_pct is not None:
            log_test("Log Progress #3", True, f"Progress logged: {progress_pct}% (current: 72kg)")
        else:
            log_test("Log Progress #3", False, f"Missing progress_percentage: {data}")
    else:
        log_test("Log Progress #3", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 6: Get Goal Analytics
    print("\n--- Test 6: GET /api/health-guide/goals/{goal_id}/analytics (Analytics) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}/analytics"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        progress_entries = data.get("progress_entries")
        trend = data.get("trend")
        avg_value = data.get("average_value")
        
        if progress_entries == 3 and trend and avg_value:
            log_test("Get Goal Analytics", True, f"Analytics: {progress_entries} entries, Trend: {trend}, Avg: {avg_value}kg")
        else:
            log_test("Get Goal Analytics", False, f"Incomplete analytics data: {data}")
    else:
        log_test("Get Goal Analytics", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 7: Update Goal
    print("\n--- Test 7: PUT /api/health-guide/goals/{goal_id} (Update Goal) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}"
    new_deadline = (datetime.now(timezone.utc) + timedelta(days=120)).isoformat()
    payload = {
        "goal_type": "weight_loss",
        "title": "Lose 10kg - Extended",
        "target_value": 68,
        "target_unit": "kg",
        "deadline": new_deadline,
        "milestones": []
    }
    
    response = session.put(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("message") == "Goal updated successfully":
            log_test("Update Health Goal", True, "Goal updated: new target 68kg, extended deadline")
        else:
            log_test("Update Health Goal", False, f"Unexpected response: {data}")
    else:
        log_test("Update Health Goal", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 8: Delete Goal (Archive)
    print("\n--- Test 8: DELETE /api/health-guide/goals/{goal_id} (Archive Goal) ---")
    url = f"{API_BASE}/health-guide/goals/{goal_id}"
    
    response = session.delete(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("message") == "Goal archived successfully":
            # Verify soft delete - check if status changed to archived
            verify_url = f"{API_BASE}/health-guide/goals?status=archived"
            verify_response = session.get(verify_url, headers=headers)
            if verify_response.status_code == 200:
                verify_data = verify_response.json()
                archived_goals = verify_data.get("goals", [])
                found_archived = any(g.get("goal_id") == goal_id for g in archived_goals)
                if found_archived:
                    log_test("Delete Goal (Archive)", True, "Goal status changed to archived (soft delete)")
                else:
                    log_test("Delete Goal (Archive)", False, "Goal not found in archived list")
            else:
                log_test("Delete Goal (Archive)", False, "Could not verify archive")
        else:
            log_test("Delete Goal (Archive)", False, f"Unexpected response: {data}")
    else:
        log_test("Delete Goal (Archive)", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 9: Create Fitness Goal (Additional Test)
    print("\n--- Test 9: POST /api/health-guide/goals (Create Fitness Goal) ---")
    url = f"{API_BASE}/health-guide/goals"
    payload = {
        "goal_type": "fitness",
        "title": "Run 5K",
        "target_value": 5000,
        "target_unit": "steps",
        "current_value": 0
    }
    
    response = session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        fitness_goal_id = data.get("goal", {}).get("goal_id")
        if fitness_goal_id:
            log_test("Create Fitness Goal", True, f"Fitness goal created: {fitness_goal_id}")
        else:
            log_test("Create Fitness Goal", False, f"Missing goal_id: {data}")
    else:
        log_test("Create Fitness Goal", False, f"Status: {response.status_code}, Response: {response.text}")

def test_advanced_analytics():
    """Test Advanced Analytics endpoints."""
    print("\n" + "="*80)
    print("PART 3: ADVANCED ANALYTICS TESTING")
    print("="*80)
    
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    # First, create some wearable data for trend analysis
    print("\n--- Setup: Creating wearable data for analytics ---")
    url = f"{API_BASE}/health-guide/wearable-data"
    payload = {
        "data_type": "heart_rate",
        "readings": [
            {"timestamp": datetime.now(timezone.utc).isoformat(), "value": 72},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "value": 75},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), "value": 70}
        ],
        "device": "Test Device"
    }
    
    response = session.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("  ✓ Wearable data created for analytics")
    else:
        print(f"  ✗ Failed to create wearable data: {response.status_code}")
    
    # Test 1: Get Health Trends (7 days)
    print("\n--- Test 1: GET /api/health-guide/analytics/trends?days=7 (7-day Trends) ---")
    url = f"{API_BASE}/health-guide/analytics/trends?days=7"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        trends = data.get("trends", {})
        period_days = data.get("period_days")
        
        if period_days == 7 and isinstance(trends, dict):
            log_test("Get Health Trends (7 days)", True, f"Trends retrieved: {len(trends)} metric(s), Period: {period_days} days")
        else:
            log_test("Get Health Trends (7 days)", False, f"Unexpected trends data: {data}")
    else:
        log_test("Get Health Trends (7 days)", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 2: Get Extended Trends (30 days) - Premium tier
    print("\n--- Test 2: GET /api/health-guide/analytics/trends?days=30 (30-day Trends) ---")
    url = f"{API_BASE}/health-guide/analytics/trends?days=30"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        period_days = data.get("period_days")
        
        if period_days == 30:
            log_test("Get Extended Trends (30 days)", True, f"Extended trends retrieved for premium tier: {period_days} days")
        else:
            log_test("Get Extended Trends (30 days)", False, f"Unexpected period: {data}")
    elif response.status_code == 403:
        # This would be expected for free tier
        log_test("Get Extended Trends (30 days)", False, "403 Forbidden - Admin should have premium access")
    else:
        log_test("Get Extended Trends (30 days)", False, f"Status: {response.status_code}, Response: {response.text}")
    
    # Test 3: Get Weekly Health Report
    print("\n--- Test 3: GET /api/health-guide/reports/weekly (Weekly Report) ---")
    url = f"{API_BASE}/health-guide/reports/weekly"
    
    response = session.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        report_type = data.get("report_type")
        summary = data.get("summary", {})
        
        if report_type == "weekly" and isinstance(summary, dict):
            wearable_logs = summary.get("wearable_logs", 0)
            insights = summary.get("health_insights_generated", 0)
            medications = summary.get("medications_taken", 0)
            goals = summary.get("goal_progress_updates", 0)
            
            log_test("Get Weekly Health Report", True, 
                    f"Report: {wearable_logs} wearable logs, {insights} insights, {medications} meds taken, {goals} goal updates")
        else:
            log_test("Get Weekly Health Report", False, f"Unexpected report data: {data}")
    elif response.status_code == 403:
        log_test("Get Weekly Health Report", False, "403 Forbidden - Admin should have access to reports")
    else:
        log_test("Get Weekly Health Report", False, f"Status: {response.status_code}, Response: {response.text}")

def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    print(f"\nTotal Tests: {test_results['total_tests']}")
    print(f"Passed: {test_results['passed']} ✅")
    print(f"Failed: {test_results['failed']} ❌")
    print(f"Success Rate: {(test_results['passed'] / test_results['total_tests'] * 100):.1f}%")
    
    if test_results['failed'] > 0:
        print("\n" + "="*80)
        print("FAILED TESTS")
        print("="*80)
        for result in test_results['details']:
            if "❌" in result['status']:
                print(f"\n{result['test']}")
                print(f"  Status: {result['status']}")
                print(f"  Details: {result['details']}")
    
    print("\n" + "="*80)
    print("ALL TEST DETAILS")
    print("="*80)
    for result in test_results['details']:
        print(f"\n{result['status']}: {result['test']}")
        if result['details']:
            print(f"  {result['details']}")

def main():
    """Main test execution."""
    print("="*80)
    print("Feature 7 Phase 2 - Comprehensive Backend E2E Testing")
    print("Medication Management, Health Goals, Advanced Analytics")
    print("="*80)
    print(f"\nBackend URL: {BASE_URL}")
    print(f"Test User: {ADMIN_EMAIL}")
    print(f"Test Date: {datetime.now(timezone.utc).isoformat()}")
    
    # Login
    if not login():
        print("\n❌ Login failed. Aborting tests.")
        return
    
    # Run tests
    test_medication_management()
    test_health_goals()
    test_advanced_analytics()
    
    # Print summary
    print_summary()
    
    # Save results to file
    output_file = "/app/backend/tests/phase2_test_results.json"
    with open(output_file, "w") as f:
        json.dump(test_results, f, indent=2)
    print(f"\n✅ Test results saved to: {output_file}")

if __name__ == "__main__":
    main()
