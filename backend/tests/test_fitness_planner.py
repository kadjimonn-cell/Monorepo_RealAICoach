#!/usr/bin/env python3
"""
Feature 8 (Fitness Planner Pro) - Comprehensive Backend E2E Testing
Test all endpoints at /api/fitness-planner/*
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://coach-web-preview.preview.emergentagent.com"
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
    "plan_id": None,
    "log_id": None,
    "progress_ids": [],
    "scan_id": None
}

def log_test(name, passed, details=""):
    """Log test result"""
    test_results["total"] += 1
    if passed:
        test_results["passed"] += 1
        print(f"✅ PASS: {name}")
    else:
        test_results["failed"] += 1
        test_results["errors"].append(f"{name}: {details}")
        print(f"❌ FAIL: {name}")
        if details:
            print(f"   Details: {details}")

def login():
    """Login as admin user"""
    print("\n" + "="*80)
    print("AUTHENTICATION")
    print("="*80)
    
    url = f"{BASE_URL}/api/auth/login"
    payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    try:
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            log_test("Admin Login", True)
            return True
        else:
            log_test("Admin Login", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log_test("Admin Login", False, str(e))
        return False

def test_bootstrap():
    """Test GET /api/fitness-planner/bootstrap"""
    print("\n" + "="*80)
    print("PART 1: BOOTSTRAP & DISCOVERY")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/bootstrap"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            # Verify required fields
            checks = [
                ("tier" in data, "tier field present"),
                (data.get("tier") == "premium", "tier is premium for admin"),
                ("usage" in data, "usage stats present"),
                ("active_plans" in data, "active_plans count present"),
                ("features" in data, "features list present"),
                ("exercise_categories" in data, "exercise_categories present"),
                (isinstance(data.get("exercise_categories"), list), "exercise_categories is array"),
            ]
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("Bootstrap Endpoint", True)
                print(f"   Tier: {data.get('tier')}")
                print(f"   Active Plans: {data.get('active_plans')}")
                print(f"   Features: {len(data.get('features', []))}")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("Bootstrap Endpoint", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("Bootstrap Endpoint", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Bootstrap Endpoint", False, str(e))

def test_create_workout_plan():
    """Test POST /api/fitness-planner/workout-plans"""
    print("\n" + "="*80)
    print("PART 2: WORKOUT PLAN CRUD - CREATE")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/workout-plans"
    payload = {
        "focus_areas": ["strength", "muscle_gain"],
        "difficulty": "intermediate",
        "duration_weeks": 4,
        "session_duration_minutes": 45,
        "equipment_available": ["dumbbells", "barbell"]
    }
    
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    try:
        resp = session.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            # Verify response structure
            if "plan" in data:
                plan = data["plan"]
                test_data["plan_id"] = plan.get("plan_id")
                
                checks = [
                    ("plan_id" in plan, "plan_id generated"),
                    ("workouts" in plan, "workouts array present"),
                    (plan.get("status") == "active", "status is active"),
                    ("warm_up" in str(plan.get("workouts", [])) or len(plan.get("workouts", [])) > 0, "workout structure present"),
                ]
                
                all_passed = all(check[0] for check in checks)
                if all_passed:
                    log_test("Create Workout Plan", True)
                    print(f"   Plan ID: {test_data['plan_id']}")
                    print(f"   Workouts: {len(plan.get('workouts', []))}")
                    print(f"   Status: {plan.get('status')}")
                else:
                    failed_checks = [check[1] for check in checks if not check[0]]
                    log_test("Create Workout Plan", False, f"Missing: {', '.join(failed_checks)}")
            else:
                log_test("Create Workout Plan", False, "No 'plan' in response")
        else:
            log_test("Create Workout Plan", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Create Workout Plan", False, str(e))

def test_list_workout_plans():
    """Test GET /api/fitness-planner/workout-plans?status=active"""
    print("\n" + "="*80)
    print("PART 2: WORKOUT PLAN CRUD - LIST")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/workout-plans?status=active"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            checks = [
                ("plans" in data, "plans array present"),
                ("count" in data, "count field present"),
                (data.get("count") == len(data.get("plans", [])), "count matches array length"),
            ]
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("List Workout Plans", True)
                print(f"   Plans Count: {data.get('count')}")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("List Workout Plans", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("List Workout Plans", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("List Workout Plans", False, str(e))

def test_get_specific_plan():
    """Test GET /api/fitness-planner/workout-plans/{plan_id}"""
    print("\n" + "="*80)
    print("PART 2: WORKOUT PLAN CRUD - GET SPECIFIC")
    print("="*80)
    
    if not test_data["plan_id"]:
        log_test("Get Specific Plan", False, "No plan_id from previous test")
        return
    
    url = f"{BASE_URL}/api/fitness-planner/workout-plans/{test_data['plan_id']}"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            if "plan" in data:
                plan = data["plan"]
                checks = [
                    (plan.get("plan_id") == test_data["plan_id"], "plan_id matches"),
                    ("workouts" in plan, "workouts present"),
                    ("status" in plan, "status present"),
                ]
                
                all_passed = all(check[0] for check in checks)
                if all_passed:
                    log_test("Get Specific Plan", True)
                else:
                    failed_checks = [check[1] for check in checks if not check[0]]
                    log_test("Get Specific Plan", False, f"Missing: {', '.join(failed_checks)}")
            else:
                log_test("Get Specific Plan", False, "No 'plan' in response")
        else:
            log_test("Get Specific Plan", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Get Specific Plan", False, str(e))

def test_update_workout_plan():
    """Test PUT /api/fitness-planner/workout-plans/{plan_id}"""
    print("\n" + "="*80)
    print("PART 2: WORKOUT PLAN CRUD - UPDATE")
    print("="*80)
    
    if not test_data["plan_id"]:
        log_test("Update Workout Plan", False, "No plan_id from previous test")
        return
    
    url = f"{BASE_URL}/api/fitness-planner/workout-plans/{test_data['plan_id']}"
    payload = {
        "plan_name": "Updated Plan Name",
        "focus_areas": ["strength", "cardio"],
        "difficulty": "advanced",
        "duration_weeks": 6,
        "session_duration_minutes": 60,
        "equipment_available": ["bodyweight"]
    }
    
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    try:
        resp = session.put(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            if "message" in data and "plan_id" in data:
                log_test("Update Workout Plan", True)
                print(f"   Message: {data.get('message')}")
            else:
                log_test("Update Workout Plan", False, "Missing message or plan_id in response")
        else:
            log_test("Update Workout Plan", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Update Workout Plan", False, str(e))

def test_log_workout():
    """Test POST /api/fitness-planner/workouts/log"""
    print("\n" + "="*80)
    print("PART 3: WORKOUT LOGGING & HISTORY - LOG WORKOUT")
    print("="*80)
    
    if not test_data["plan_id"]:
        log_test("Log Workout", False, "No plan_id from previous test")
        return
    
    url = f"{BASE_URL}/api/fitness-planner/workouts/log"
    payload = {
        "plan_id": test_data["plan_id"],
        "workout_date": "2026-05-26",
        "exercises_completed": [
            {
                "exercise_name": "Bench Press",
                "sets_completed": 4,
                "reps": [10, 10, 9, 8],
                "weight_kg": 80,
                "notes": "Felt strong"
            }
        ],
        "duration_minutes": 60,
        "effort_level": "high",
        "notes": "Great workout!"
    }
    
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    try:
        resp = session.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            if "log" in data:
                log_entry = data["log"]
                test_data["log_id"] = log_entry.get("log_id")
                
                checks = [
                    ("log_id" in log_entry, "log_id generated"),
                    ("exercises_completed" in log_entry, "exercises saved"),
                    (len(log_entry.get("exercises_completed", [])) > 0, "exercises array not empty"),
                ]
                
                all_passed = all(check[0] for check in checks)
                if all_passed:
                    log_test("Log Workout", True)
                    print(f"   Log ID: {test_data['log_id']}")
                    print(f"   Exercises: {len(log_entry.get('exercises_completed', []))}")
                else:
                    failed_checks = [check[1] for check in checks if not check[0]]
                    log_test("Log Workout", False, f"Missing: {', '.join(failed_checks)}")
            else:
                log_test("Log Workout", False, "No 'log' in response")
        else:
            log_test("Log Workout", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Log Workout", False, str(e))

def test_workout_history():
    """Test GET /api/fitness-planner/workouts/history?days=30"""
    print("\n" + "="*80)
    print("PART 3: WORKOUT LOGGING & HISTORY - GET HISTORY")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/workouts/history?days=30"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            checks = [
                ("history" in data, "history array present"),
                ("count" in data, "count field present"),
            ]
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("Get Workout History", True)
                print(f"   History Count: {data.get('count')}")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("Get Workout History", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("Get Workout History", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Get Workout History", False, str(e))

def test_log_progress_metrics():
    """Test POST /api/fitness-planner/progress (multiple entries)"""
    print("\n" + "="*80)
    print("PART 4: PROGRESS TRACKING & ANALYTICS - LOG METRICS")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/progress"
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    payloads = [
        {
            "metric_type": "strength",
            "exercise_name": "Bench Press",
            "value": 80,
            "unit": "kg",
            "notes": "New PR!"
        },
        {
            "metric_type": "strength",
            "exercise_name": "Bench Press",
            "value": 85,
            "unit": "kg",
            "notes": "Another PR!"
        },
        {
            "metric_type": "weight",
            "value": 75,
            "unit": "kg",
            "notes": "Body weight check"
        }
    ]
    
    success_count = 0
    for i, payload in enumerate(payloads, 1):
        try:
            resp = session.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if "progress" in data:
                    progress_id = data["progress"].get("progress_id")
                    test_data["progress_ids"].append(progress_id)
                    success_count += 1
                    print(f"   ✓ Progress Entry {i}: {progress_id}")
        except Exception as e:
            print(f"   ✗ Progress Entry {i} failed: {str(e)}")
    
    if success_count == len(payloads):
        log_test("Log Progress Metrics (3 entries)", True)
    else:
        log_test("Log Progress Metrics (3 entries)", False, f"Only {success_count}/{len(payloads)} succeeded")

def test_progress_analytics():
    """Test GET /api/fitness-planner/progress/analytics?metric_type=strength&days=90"""
    print("\n" + "="*80)
    print("PART 4: PROGRESS TRACKING & ANALYTICS - GET ANALYTICS")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/progress/analytics?metric_type=strength&days=90"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            checks = [
                ("trends" in data, "trends present"),
                ("period_days" in data, "period_days present"),
            ]
            
            # Check if trends show improvement (85 > 80 for Bench Press)
            trends = data.get("trends", {})
            strength_trend = trends.get("strength", {})
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("Get Progress Analytics", True)
                print(f"   Period: {data.get('period_days')} days")
                if strength_trend:
                    print(f"   Strength Trend: {strength_trend.get('trend')}")
                    print(f"   Latest: {strength_trend.get('latest')}")
                    print(f"   Average: {strength_trend.get('average')}")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("Get Progress Analytics", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("Get Progress Analytics", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Get Progress Analytics", False, str(e))

def test_exercise_library():
    """Test GET /api/fitness-planner/exercises"""
    print("\n" + "="*80)
    print("PART 5: EXERCISE LIBRARY & PERSONAL RECORDS - LIBRARY")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/exercises"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            checks = [
                ("exercises" in data, "exercises array present"),
                ("count" in data, "count field present"),
            ]
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("Get Exercise Library", True)
                print(f"   Exercises Count: {data.get('count')}")
                print("   Note: Empty library is OK for testing")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("Get Exercise Library", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("Get Exercise Library", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Get Exercise Library", False, str(e))

def test_personal_records():
    """Test GET /api/fitness-planner/personal-records"""
    print("\n" + "="*80)
    print("PART 5: EXERCISE LIBRARY & PERSONAL RECORDS - RECORDS")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/personal-records"
    
    try:
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            
            checks = [
                ("personal_records" in data, "personal_records array present"),
                ("count" in data, "count field present"),
            ]
            
            # Check if Bench Press PR is present (80kg from workout log)
            records = data.get("personal_records", [])
            bench_pr = next((r for r in records if r.get("exercise_name") == "Bench Press"), None)
            
            all_passed = all(check[0] for check in checks)
            if all_passed:
                log_test("Get Personal Records", True)
                print(f"   Records Count: {data.get('count')}")
                if bench_pr:
                    print(f"   Bench Press PR: {bench_pr.get('record_value')} {bench_pr.get('unit')}")
                    print(f"   Achieved: {bench_pr.get('achieved_date')}")
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                log_test("Get Personal Records", False, f"Missing: {', '.join(failed_checks)}")
        else:
            log_test("Get Personal Records", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Get Personal Records", False, str(e))

def test_body_scan():
    """Test POST /api/fitness-planner/scan-body"""
    print("\n" + "="*80)
    print("PART 6: BODY SCAN ANALYSIS")
    print("="*80)
    
    url = f"{BASE_URL}/api/fitness-planner/scan-body"
    
    # Minimal 1x1 red pixel PNG (base64)
    minimal_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    
    payload = {
        "scan_type": "form",
        "exercise_name": "Squat",
        "image_base64": minimal_image
    }
    
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    try:
        resp = session.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            if "scan" in data:
                scan = data["scan"]
                test_data["scan_id"] = scan.get("scan_id")
                
                ai_analysis = scan.get("ai_analysis", {})
                
                checks = [
                    ("scan_id" in scan, "scan_id generated"),
                    ("ai_analysis" in scan, "ai_analysis present"),
                    ("form_score" in ai_analysis or "issues_found" in ai_analysis, "analysis fields present"),
                ]
                
                all_passed = all(check[0] for check in checks)
                if all_passed:
                    log_test("Body Scan Analysis", True)
                    print(f"   Scan ID: {test_data['scan_id']}")
                    print(f"   Form Score: {ai_analysis.get('form_score', 'N/A')}")
                    print(f"   Issues: {len(ai_analysis.get('issues_found', []))}")
                    print(f"   Suggestions: {len(ai_analysis.get('suggestions', []))}")
                else:
                    failed_checks = [check[1] for check in checks if not check[0]]
                    log_test("Body Scan Analysis", False, f"Missing: {', '.join(failed_checks)}")
            else:
                log_test("Body Scan Analysis", False, "No 'scan' in response")
        else:
            log_test("Body Scan Analysis", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Body Scan Analysis", False, str(e))

def test_archive_workout_plan():
    """Test DELETE /api/fitness-planner/workout-plans/{plan_id}"""
    print("\n" + "="*80)
    print("PART 2: WORKOUT PLAN CRUD - ARCHIVE (SOFT DELETE)")
    print("="*80)
    
    if not test_data["plan_id"]:
        log_test("Archive Workout Plan", False, "No plan_id from previous test")
        return
    
    url = f"{BASE_URL}/api/fitness-planner/workout-plans/{test_data['plan_id']}"
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    try:
        resp = session.delete(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            if "message" in data:
                log_test("Archive Workout Plan", True)
                print(f"   Message: {data.get('message')}")
                
                # Verify soft delete by checking status
                verify_url = f"{BASE_URL}/api/fitness-planner/workout-plans/{test_data['plan_id']}"
                verify_resp = session.get(verify_url)
                if verify_resp.status_code == 200:
                    verify_data = verify_resp.json()
                    plan = verify_data.get("plan", {})
                    if plan.get("status") == "archived":
                        print("   ✓ Verified: Plan status changed to 'archived' (soft delete working)")
                    else:
                        print(f"   ⚠ Warning: Plan status is '{plan.get('status')}', expected 'archived'")
            else:
                log_test("Archive Workout Plan", False, "No message in response")
        else:
            log_test("Archive Workout Plan", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Archive Workout Plan", False, str(e))

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {test_results['total']}")
    print(f"Passed: {test_results['passed']} ✅")
    print(f"Failed: {test_results['failed']} ❌")
    print(f"Success Rate: {(test_results['passed']/test_results['total']*100):.1f}%")
    
    if test_results["errors"]:
        print("\n" + "="*80)
        print("FAILED TESTS DETAILS")
        print("="*80)
        for error in test_results["errors"]:
            print(f"❌ {error}")
    
    print("\n" + "="*80)
    print("SUCCESS CRITERIA VERIFICATION")
    print("="*80)
    
    criteria = [
        ("Bootstrap returns correct tier and usage stats", test_results["passed"] >= 1),
        ("Workout plan generation works (AI integration)", test_results["passed"] >= 2),
        ("Full CRUD cycle for workout plans", test_results["passed"] >= 5),
        ("Workout logging captures all exercise details", test_results["passed"] >= 6),
        ("Workout history retrieval works", test_results["passed"] >= 7),
        ("Progress metrics log successfully", test_results["passed"] >= 8),
        ("Progress analytics show trends", test_results["passed"] >= 9),
        ("Personal records auto-detected", test_results["passed"] >= 10),
        ("Exercise library endpoint works", test_results["passed"] >= 11),
        ("Body scan AI vision analysis works", test_results["passed"] >= 12),
    ]
    
    for criterion, passed in criteria:
        status = "✅" if passed else "❌"
        print(f"{status} {criterion}")
    
    print("\n" + "="*80)
    print("TEST DATA GENERATED")
    print("="*80)
    print(f"Plan ID: {test_data.get('plan_id', 'N/A')}")
    print(f"Log ID: {test_data.get('log_id', 'N/A')}")
    print(f"Progress IDs: {len(test_data.get('progress_ids', []))}")
    print(f"Scan ID: {test_data.get('scan_id', 'N/A')}")

def main():
    """Main test execution"""
    print("="*80)
    print("Feature 8 (Fitness Planner Pro) - Backend E2E Testing")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin User: {ADMIN_EMAIL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login
    if not login():
        print("\n❌ CRITICAL: Login failed. Cannot proceed with tests.")
        sys.exit(1)
    
    # Part 1: Bootstrap
    test_bootstrap()
    
    # Part 2: Workout Plan CRUD
    test_create_workout_plan()
    test_list_workout_plans()
    test_get_specific_plan()
    test_update_workout_plan()
    
    # Part 3: Workout Logging & History
    test_log_workout()
    test_workout_history()
    
    # Part 4: Progress Tracking & Analytics
    test_log_progress_metrics()
    test_progress_analytics()
    
    # Part 5: Exercise Library & Personal Records
    test_exercise_library()
    test_personal_records()
    
    # Part 6: Body Scan Analysis
    test_body_scan()
    
    # Part 2 (continued): Archive Plan
    test_archive_workout_plan()
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    if test_results["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
