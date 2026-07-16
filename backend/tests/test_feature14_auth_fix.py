#!/usr/bin/env python3
"""
Feature 14 (Property Decision Advisor) - Authentication Fix Validation Test
Tests that the authentication rebuild is working correctly
"""

import requests
import json
import sys
import os

# Configuration
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Test state
session = requests.Session()
test_results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
test_data = {}


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


def test_login():
    """Test authentication"""
    print("\n" + "="*80)
    print("AUTHENTICATION TEST")
    print("="*80)
    
    url = f"{BASE_URL}/api/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    try:
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            resp.json()
            log_test("Admin Login", True)
            return True
        else:
            log_test("Admin Login", False, f"Status {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log_test("Admin Login", False, str(e))
        return False


def test_property_search():
    """Test POST /real-estate/search with authentication"""
    print("\n" + "="*80)
    print("PROPERTY SEARCH TEST - Verify Session Auth Working")
    print("="*80)
    
    url = f"{BASE_URL}/api/real-estate/search"
    payload = {
        "location": "San Francisco, CA",
        "min_price": 500000,
        "max_price": 1500000,
        "beds": 3
    }
    
    try:
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            
            # Verify response structure
            has_properties = "properties" in data
            has_owner_id = "owner_id" in data
            has_tier = "tier" in data
            has_limits = "daily_limit" in data
            
            log_test("Property Search returns correct structure",
                    has_properties and has_owner_id and has_tier and has_limits,
                    f"properties={has_properties}, owner_id={has_owner_id}, tier={has_tier}, limits={has_limits}")
            
            # Verify owner_id format
            owner_id = data.get("owner_id", "")
            correct_format = owner_id.startswith("auth:")
            log_test("owner_id uses correct auth format", correct_format, f"Got: {owner_id}")
            
            # Verify tier
            tier = data.get("tier", "")
            log_test("Tier returned", tier in ["free", "basic", "premium"], f"Got: {tier}")
            
            # Verify properties returned
            properties = data.get("properties", [])
            log_test("Properties returned", len(properties) > 0, f"Got {len(properties)} properties")
            
            print("\n📊 Search Response:")
            print(f"   owner_id: {data.get('owner_id')}")
            print(f"   tier: {data.get('tier')}")
            print(f"   properties_count: {len(properties)}")
            print(f"   used_today: {data.get('used_today', 0)}")
            
        else:
            log_test("Property Search API", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Property Search API", False, str(e))


def test_ai_valuation():
    """Test POST /real-estate/ai-valuation with authentication"""
    print("\n" + "="*80)
    print("AI VALUATION TEST - Verify POST Auth Working")
    print("="*80)
    
    url = f"{BASE_URL}/api/real-estate/ai-valuation"
    payload = {
        "address": "123 Main St, San Francisco, CA"
    }
    
    try:
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            
            has_report = "valuation_report" in data
            has_owner_id = "owner_id" in data
            has_tier = "tier" in data
            
            log_test("AI Valuation returns correct structure",
                    has_report and has_owner_id and has_tier,
                    f"report={has_report}, owner_id={has_owner_id}, tier={has_tier}")
            
            # Verify report is not empty
            report = data.get("valuation_report", "")
            log_test("Valuation report generated", len(report) > 50, f"Report length: {len(report)} chars")
            
            print("\n📊 Valuation Response:")
            print(f"   owner_id: {data.get('owner_id')}")
            print(f"   tier: {data.get('tier')}")
            print(f"   report_length: {len(report)} chars")
            
        else:
            log_test("AI Valuation API", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("AI Valuation API", False, str(e))


def test_mortgage_calculator():
    """Test POST /real-estate/mortgage-calculator (public endpoint)"""
    print("\n" + "="*80)
    print("MORTGAGE CALCULATOR TEST - Public Endpoint")
    print("="*80)
    
    url = f"{BASE_URL}/api/real-estate/mortgage-calculator"
    payload = {
        "price": 800000,
        "down_payment": 160000,
        "rate": 6.5,
        "term_years": 30
    }
    
    try:
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            
            has_monthly = "monthly_payment" in data
            has_total = "total_paid" in data
            has_interest = "total_interest" in data
            
            log_test("Mortgage Calculator returns correct structure",
                    has_monthly and has_total and has_interest,
                    f"monthly={has_monthly}, total={has_total}, interest={has_interest}")
            
            # Verify calculations make sense
            monthly = data.get("monthly_payment", 0)
            log_test("Monthly payment calculated", monthly > 0, f"Got: ${monthly}")
            
            print("\n📊 Mortgage Calculation:")
            print(f"   monthly_payment: ${monthly:,.2f}")
            print(f"   total_paid: ${data.get('total_paid', 0):,.2f}")
            print(f"   total_interest: ${data.get('total_interest', 0):,.2f}")
            
        else:
            log_test("Mortgage Calculator API", False, f"Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log_test("Mortgage Calculator API", False, str(e))


def test_guest_mode():
    """Test guest mode with fallback_user_id"""
    print("\n" + "="*80)
    print("GUEST MODE TEST - Verify fallback_user_id Works")
    print("="*80)
    
    # Create new session without authentication
    guest_session = requests.Session()
    url = f"{BASE_URL}/api/real-estate/search"
    payload = {
        "location": "Austin, TX",
        "fallback_user_id": "guest-test-validation"
    }
    
    try:
        resp = guest_session.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            owner_id = data.get("owner_id", "")
            is_guest = owner_id.startswith("guest:")
            log_test("Guest mode works with fallback_user_id", is_guest, f"Got owner_id: {owner_id}")
            
            tier = data.get("tier", "")
            log_test("Guest gets free tier", tier == "free", f"Got tier: {tier}")
        else:
            log_test("Guest mode", False, f"Status {resp.status_code}")
    except Exception as e:
        log_test("Guest mode", False, str(e))


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total:  {test_results['total']}")
    print(f"Passed: {test_results['passed']} ✅")
    print(f"Failed: {test_results['failed']} ❌")
    
    if test_results['failed'] > 0:
        print("\n❌ FAILED TESTS:")
        for error in test_results['errors']:
            print(f"   • {error}")
    
    success_rate = (test_results['passed'] / test_results['total'] * 100) if test_results['total'] > 0 else 0
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    print("="*80 + "\n")
    
    return test_results['failed'] == 0


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("FEATURE 14: PROPERTY DECISION ADVISOR - AUTHENTICATION VALIDATION")
    print("="*80)
    
    if not test_login():
        print("\n❌ Cannot proceed without successful login")
        sys.exit(1)
    
    test_property_search()
    test_ai_valuation()
    test_mortgage_calculator()
    test_guest_mode()
    
    success = print_summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
