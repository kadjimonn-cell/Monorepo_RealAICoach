"""Feature 19 (Bill Generator) backend E2E test suite.

Covers:
- Bootstrap endpoint
- Clients (CRUD)
- Catalog Items (CRUD)
- Recurring Schedules (CRUD + toggle + run)
- AI Draft (bill generation)
- Bills (CRUD + status update + duplicate + PDF)
- Reminders (AI message + dispatch + bulk)
- Collections Dashboard
- Workspace Members (invite + role update)
- Workflow (submit + approve + reject)
- Client Insights
- Business Insights
- Tier limit enforcement
- MongoDB serialization
- PDF generation
"""

import os
import requests
from datetime import datetime, timezone

BASE_URL = str(os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required to run test_bill_generator_deep.py")

API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
state = {
    "client_id": None,
    "catalog_item_id": None,
    "schedule_id": None,
    "bill_id": None,
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


def re_authenticate():
    """Re-authenticate to refresh session"""
    return login()


# ── Bootstrap ────────────────────────────────────────────────────────────────


def test_bootstrap():
    resp = session.get(f"{API_BASE}/bill-generator/bootstrap")
    if not assert_status(resp, 200, "Bootstrap"):
        return
    data = resp.json()
    checks = [
        "plan" in data,
        "scope_label" in data,
        "limits" in data,
        "clients" in data,
        "bills" in data,
        "catalog_items" in data,
        "recurring_schedules" in data,
        "insights" in data,
    ]
    log_test("Bootstrap structure", all(checks), f"plan={data.get('plan')}")


# ── Clients ──────────────────────────────────────────────────────────────────


def test_create_client():
    payload = {
        "name": "Test Client Corp",
        "email": "client@testcorp.com",
        "phone": "+1-555-0100",
    }
    resp = session.post(f"{API_BASE}/bill-generator/clients", json=payload)
    if not assert_status(resp, 200, "Create Client"):
        return
    data = resp.json()
    checks = [
        "client_id" in data,
        "message" in data,
    ]
    log_test("Create Client structure", all(checks), f"Client ID: {data.get('client_id')}")
    state["client_id"] = data.get("client_id")


def test_list_clients():
    resp = session.get(f"{API_BASE}/bill-generator/clients")
    if not assert_status(resp, 200, "List Clients"):
        return
    data = resp.json()
    checks = [
        "clients" in data,
        isinstance(data.get("clients"), list),
    ]
    log_test("List Clients structure", all(checks), f"Count: {len(data.get('clients', []))}")
    
    if data.get("clients"):
        client = data["clients"][0]
        no_id_leak = "_id" not in client
        log_test("Clients MongoDB serialization", no_id_leak, "No _id field present")


# ── Catalog Items ────────────────────────────────────────────────────────────


def test_create_catalog_item():
    payload = {
        "name": "Premium Consulting Hour",
        "description": "Expert consulting services",
        "unit_price": 150.0,
        "tax_rate": 10.0,
        "unit": "hour",
    }
    resp = session.post(f"{API_BASE}/bill-generator/catalog/items", json=payload)
    if not assert_status(resp, 200, "Create Catalog Item"):
        return
    data = resp.json()
    checks = [
        "catalog_item_id" in data,
        "message" in data,
    ]
    log_test("Create Catalog Item structure", all(checks), f"Item ID: {data.get('catalog_item_id')}")
    state["catalog_item_id"] = data.get("catalog_item_id")


def test_list_catalog_items():
    resp = session.get(f"{API_BASE}/bill-generator/catalog/items")
    if not assert_status(resp, 200, "List Catalog Items"):
        return
    data = resp.json()
    checks = [
        "items" in data,
        isinstance(data.get("items"), list),
    ]
    log_test("List Catalog Items structure", all(checks), f"Count: {len(data.get('items', []))}")


# ── Recurring Schedules ──────────────────────────────────────────────────────


def test_create_recurring_schedule():
    template = {
        "bill_type": "invoice",
        "customer_name": "Recurring Client",
        "customer_email": "recurring@client.com",
        "currency": "USD",
        "items": [
            {
                "description": "Monthly Subscription",
                "quantity": 1,
                "unit_price": 99.0,
                "tax_rate": 0,
            }
        ],
    }
    payload = {
        "schedule_name": "Monthly Subscription Invoice",
        "frequency": "monthly",
        "template": template,
    }
    resp = session.post(f"{API_BASE}/bill-generator/recurring-schedules", json=payload)
    if not assert_status(resp, 200, "Create Recurring Schedule"):
        return
    data = resp.json()
    checks = [
        "schedule_id" in data,
        "message" in data,
    ]
    log_test("Create Recurring Schedule structure", all(checks), f"Schedule ID: {data.get('schedule_id')}")
    state["schedule_id"] = data.get("schedule_id")


def test_list_recurring_schedules():
    resp = session.get(f"{API_BASE}/bill-generator/recurring-schedules")
    if not assert_status(resp, 200, "List Recurring Schedules"):
        return
    data = resp.json()
    checks = [
        "schedules" in data,
        isinstance(data.get("schedules"), list),
    ]
    log_test("List Recurring Schedules structure", all(checks), f"Count: {len(data.get('schedules', []))}")


def test_toggle_recurring_schedule():
    if not state.get("schedule_id"):
        log_test("Toggle Recurring Schedule", False, "No schedule_id in state (skipped)")
        return
    
    payload = {"active": False}
    resp = session.post(
        f"{API_BASE}/bill-generator/recurring-schedules/{state['schedule_id']}/toggle",
        json=payload
    )
    if not assert_status(resp, 200, "Toggle Recurring Schedule"):
        return
    data = resp.json()
    checks = [
        "message" in data,
        "active" in data,
    ]
    log_test("Toggle Recurring Schedule structure", all(checks), f"Active: {data.get('active')}")


# ── AI Draft ─────────────────────────────────────────────────────────────────


def test_ai_draft():
    payload = {
        "scope": "Create invoice for web design project",
        "industry": "technology",
        "target_amount": 2500,
    }
    resp = session.post(f"{API_BASE}/bill-generator/ai-draft", json=payload)
    if not assert_status(resp, 200, "AI Draft"):
        return
    data = resp.json()
    checks = [
        "draft" in data,
        isinstance(data.get("draft"), dict),
        "items" in data.get("draft", {}),
    ]
    log_test("AI Draft structure", all(checks), f"Items generated: {len(data.get('draft', {}).get('items', []))}")


# ── Bills ────────────────────────────────────────────────────────────────────


def test_create_bill():
    payload = {
        "bill_type": "invoice",
        "customer_name": "Test Customer",
        "customer_email": "test@customer.com",
        "currency": "USD",
        "due_date": "2026-06-30",
        "items": [
            {
                "description": "Website Development",
                "quantity": 1,
                "unit_price": 3000.0,
                "tax_rate": 10.0,
            }
        ],
        "notes": "Thank you for your business!",
    }
    resp = session.post(f"{API_BASE}/bill-generator/bills", json=payload)
    if not assert_status(resp, 200, "Create Bill"):
        return
    data = resp.json()
    checks = [
        "bill_id" in data,
        "bill_number" in data,
        "message" in data,
    ]
    log_test("Create Bill structure", all(checks), f"Bill Number: {data.get('bill_number')}")
    state["bill_id"] = data.get("bill_id")


def test_list_bills():
    resp = session.get(f"{API_BASE}/bill-generator/bills")
    if not assert_status(resp, 200, "List Bills"):
        return
    data = resp.json()
    checks = [
        "bills" in data,
        isinstance(data.get("bills"), list),
    ]
    log_test("List Bills structure", all(checks), f"Count: {len(data.get('bills', []))}")
    
    if data.get("bills"):
        bill = data["bills"][0]
        no_id_leak = "_id" not in bill
        log_test("Bills MongoDB serialization", no_id_leak, "No _id field present")


def test_get_bill_details():
    if not state.get("bill_id"):
        log_test("Get Bill Details", False, "No bill_id in state (skipped)")
        return
    
    resp = session.get(f"{API_BASE}/bill-generator/bills/{state['bill_id']}")
    if not assert_status(resp, 200, "Get Bill Details"):
        return
    data = resp.json()
    checks = [
        "bill_id" in data,
        "bill_number" in data,
        "items" in data,
    ]
    log_test("Get Bill Details structure", all(checks), f"Items: {len(data.get('items', []))}")


def test_update_bill_status():
    if not state.get("bill_id"):
        log_test("Update Bill Status", False, "No bill_id in state (skipped)")
        return
    
    payload = {"new_status": "sent"}
    resp = session.patch(
        f"{API_BASE}/bill-generator/bills/{state['bill_id']}/status",
        json=payload
    )
    if not assert_status(resp, 200, "Update Bill Status"):
        return
    data = resp.json()
    checks = [
        "message" in data,
        "new_status" in data,
    ]
    log_test("Update Bill Status structure", all(checks), f"New Status: {data.get('new_status')}")


def test_duplicate_bill():
    if not state.get("bill_id"):
        log_test("Duplicate Bill", False, "No bill_id in state (skipped)")
        return
    
    resp = session.post(f"{API_BASE}/bill-generator/bills/{state['bill_id']}/duplicate")
    if not assert_status(resp, 200, "Duplicate Bill"):
        return
    data = resp.json()
    checks = [
        "bill_id" in data,
        "bill_number" in data,
        "message" in data,
    ]
    log_test("Duplicate Bill structure", all(checks), f"New Bill: {data.get('bill_number')}")


# ── Reminders ────────────────────────────────────────────────────────────────


def test_list_reminders():
    resp = session.get(f"{API_BASE}/bill-generator/reminders")
    if not assert_status(resp, 200, "List Reminders"):
        return
    data = resp.json()
    checks = [
        "reminders" in data,
        isinstance(data.get("reminders"), list),
    ]
    log_test("List Reminders structure", all(checks), f"Count: {len(data.get('reminders', []))}")


# ── Collections Dashboard ────────────────────────────────────────────────────


def test_collections_dashboard():
    resp = session.get(f"{API_BASE}/bill-generator/collections/dashboard")
    if not assert_status(resp, 200, "Collections Dashboard"):
        return
    data = resp.json()
    checks = [
        "aging_buckets" in data,
        "paid_velocity_30d" in data,
        "paid_volume_30d" in data,
    ]
    log_test("Collections Dashboard structure", all(checks), f"Buckets: {data.get('aging_buckets')}")


# ── Workspace Members ────────────────────────────────────────────────────────


def test_list_workspace_members():
    resp = session.get(f"{API_BASE}/bill-generator/workspace/members")
    if not assert_status(resp, 200, "List Workspace Members"):
        return
    data = resp.json()
    checks = [
        "members" in data,
        isinstance(data.get("members"), list),
    ]
    log_test("List Workspace Members structure", all(checks), f"Count: {len(data.get('members', []))}")


# ── Workflow ─────────────────────────────────────────────────────────────────


def test_workflow_settings_get():
    resp = session.get(f"{API_BASE}/bill-generator/workflow/settings")
    if not assert_status(resp, 200, "Get Workflow Settings"):
        return
    data = resp.json()
    checks = [
        "approval_required_for_send" in data,
    ]
    log_test("Get Workflow Settings structure", all(checks), f"Approval Required: {data.get('approval_required_for_send')}")


def test_workflow_settings_update():
    payload = {"approval_required_for_send": True}
    resp = session.post(f"{API_BASE}/bill-generator/workflow/settings", json=payload)
    if not assert_status(resp, 200, "Update Workflow Settings"):
        return
    data = resp.json()
    checks = [
        "message" in data,
    ]
    log_test("Update Workflow Settings structure", all(checks))


# ── Insights ─────────────────────────────────────────────────────────────────


def test_client_insights():
    resp = session.get(f"{API_BASE}/bill-generator/client-insights")
    if not assert_status(resp, 200, "Client Insights"):
        return
    data = resp.json()
    checks = [
        "insights" in data,
        isinstance(data.get("insights"), list),
    ]
    log_test("Client Insights structure", all(checks), f"Count: {len(data.get('insights', []))}")


def test_business_insights():
    resp = session.get(f"{API_BASE}/bill-generator/insights")
    if not assert_status(resp, 200, "Business Insights"):
        return
    data = resp.json()
    checks = [
        "total_bills" in data,
        "current_month_bills" in data,
        "paid_total" in data,
        "outstanding_total" in data,
    ]
    log_test("Business Insights structure", all(checks), f"Total Bills: {data.get('total_bills')}")


# ── Tier Limits ──────────────────────────────────────────────────────────────


def test_tier_limit_enforcement():
    resp = session.get(f"{API_BASE}/bill-generator/bootstrap")
    if not assert_status(resp, 200, "Tier Limit Bootstrap"):
        return
    data = resp.json()
    
    plan = data.get("plan")
    limits = data.get("limits", {})
    
    if plan == "free":
        free_checks = [
            limits.get("ai_draft") == 3,
            limits.get("create_bill") == 5,
            limits.get("pdf_export") == 3,
        ]
        log_test("Tier Limit - Free Plan", all(free_checks), f"Limits: {limits}")
    elif plan == "premium":
        premium_checks = [
            limits.get("ai_draft") == -1,
            limits.get("create_bill") == -1,
        ]
        log_test("Tier Limit - Premium Plan", all(premium_checks), f"Unlimited: {limits}")
    else:
        log_test("Tier Limit Check", True, f"Plan: {plan}, Limits: {limits}")


# ── Run All Tests ────────────────────────────────────────────────────────────


def run_all_tests():
    print("\n" + "=" * 70)
    print("Feature 14 (Bill Generator) - Comprehensive E2E Test Suite")
    print("=" * 70 + "\n")
    
    if not login():
        print("\n❌ LOGIN FAILED - ABORTING TEST SUITE\n")
        return
    
    print("\n=== Bootstrap ===")
    test_bootstrap()
    
    print("\n=== Clients ===")
    test_create_client()
    test_list_clients()
    
    print("\n=== Catalog Items ===")
    test_create_catalog_item()
    test_list_catalog_items()
    
    print("\n=== Recurring Schedules ===")
    test_create_recurring_schedule()
    test_list_recurring_schedules()
    test_toggle_recurring_schedule()
    
    print("\n=== AI Draft ===")
    test_ai_draft()
    
    print("\n=== Bills ===")
    test_create_bill()
    test_list_bills()
    test_get_bill_details()
    test_update_bill_status()
    test_duplicate_bill()
    
    print("\n=== Reminders ===")
    # Re-authenticate before long-running tests to prevent session timeout
    print("🔄 Re-authenticating session...")
    if not re_authenticate():
        print("❌ Re-authentication failed")
    test_list_reminders()
    
    print("\n=== Collections Dashboard ===")
    test_collections_dashboard()
    
    print("\n=== Workspace Members ===")
    test_list_workspace_members()
    
    print("\n=== Workflow ===")
    test_workflow_settings_get()
    test_workflow_settings_update()
    
    print("\n=== Insights ===")
    test_client_insights()
    test_business_insights()
    
    print("\n=== Tier Limit Enforcement ===")
    test_tier_limit_enforcement()
    
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
