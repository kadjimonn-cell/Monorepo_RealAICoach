"""Deep validation tests for Money Strategy Hub - Feature 9.

Validates:
1. No ObjectId serialization leaks in responses
2. Budget-expense linkage (spent_amount updates)
3. Expense deletion reverses budget spent_amount
4. All response structures are JSON-serializable
"""

import os
import json
import requests

BASE_URL = str(os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")

API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}


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


def check_no_objectid(data, path="root"):
    """Recursively check for MongoDB ObjectId leaks."""
    if isinstance(data, dict):
        if "_id" in data:
            return f"ObjectId leak at {path}._id"
        for key, value in data.items():
            result = check_no_objectid(value, f"{path}.{key}")
            if result:
                return result
    elif isinstance(data, list):
        for i, item in enumerate(data):
            result = check_no_objectid(item, f"{path}[{i}]")
            if result:
                return result
    return None


def check_json_serializable(data, path="root"):
    """Verify data is JSON serializable."""
    try:
        json.dumps(data)
        return None
    except (TypeError, ValueError) as e:
        return f"Not JSON serializable at {path}: {e}"


def login():
    resp = session.post(f"{API_BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        log_test("Login", False, f"status={resp.status_code}")
        return False
    log_test("Login", True)
    return True


def test_bootstrap_no_objectid():
    resp = session.get(f"{API_BASE}/money-strategy-hub/bootstrap")
    if resp.status_code != 200:
        log_test("Bootstrap status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    # Check no ObjectId
    leak = check_no_objectid(data)
    log_test("Bootstrap no ObjectId leak", leak is None, leak or "Clean")
    
    # Check JSON serializable
    err = check_json_serializable(data)
    log_test("Bootstrap JSON serializable", err is None, err or "Valid JSON")


def test_profile_no_objectid():
    # Create profile
    resp = session.post(f"{API_BASE}/money-strategy-hub/profile", json={
        "currency": "USD",
        "monthly_income": 5000,
        "risk_tolerance": "moderate"
    })
    if resp.status_code != 200:
        log_test("Profile create status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Profile create no ObjectId leak", leak is None, leak or "Clean")
    
    # Get profile
    resp = session.get(f"{API_BASE}/money-strategy-hub/profile")
    data = resp.json()
    leak = check_no_objectid(data)
    log_test("Profile get no ObjectId leak", leak is None, leak or "Clean")


def test_budget_expense_linkage():
    """Test that expenses correctly update budget spent_amount."""
    
    # Create a fresh budget
    budget_resp = session.post(f"{API_BASE}/money-strategy-hub/budgets", json={
        "name": "Linkage Test Budget",
        "category": "testing",
        "monthly_limit": 1000
    })
    if budget_resp.status_code != 200:
        log_test("Linkage budget create", False, f"status={budget_resp.status_code}")
        return
    
    budget = budget_resp.json().get("budget", {})
    budget_id = budget.get("budget_id")
    
    # Verify initial state
    initial_spent = float(budget.get("spent_amount", 0))
    initial_remaining = float(budget.get("remaining_amount", 0))
    log_test("Budget initial spent=0", initial_spent == 0, f"spent={initial_spent}")
    log_test("Budget initial remaining=limit", initial_remaining == 1000, f"remaining={initial_remaining}")
    
    # Check no ObjectId in budget
    leak = check_no_objectid(budget)
    log_test("Budget no ObjectId leak", leak is None, leak or "Clean")
    
    # Create expense linked to budget
    expense_resp = session.post(f"{API_BASE}/money-strategy-hub/expenses", json={
        "amount": 150.50,
        "category": "testing",
        "merchant": "Test Merchant",
        "budget_id": budget_id
    })
    if expense_resp.status_code != 200:
        log_test("Linked expense create", False, f"status={expense_resp.status_code}")
        return
    
    expense = expense_resp.json().get("expense", {})
    expense_id = expense.get("expense_id")
    
    # Check no ObjectId in expense
    leak = check_no_objectid(expense)
    log_test("Expense no ObjectId leak", leak is None, leak or "Clean")
    
    # Verify budget spent_amount updated
    budget_list_resp = session.get(f"{API_BASE}/money-strategy-hub/budgets?status=all")
    budgets = budget_list_resp.json().get("budgets", [])
    updated_budget = next((b for b in budgets if b.get("budget_id") == budget_id), None)
    
    if updated_budget:
        new_spent = float(updated_budget.get("spent_amount", 0))
        new_remaining = float(updated_budget.get("remaining_amount", 0))
        log_test("Budget spent_amount updated after expense", new_spent == 150.50, f"spent={new_spent}")
        log_test("Budget remaining_amount updated", new_remaining == 849.50, f"remaining={new_remaining}")
    else:
        log_test("Budget found after expense", False, "Budget not found")
    
    # Delete expense and verify budget reverts
    delete_resp = session.delete(f"{API_BASE}/money-strategy-hub/expenses/{expense_id}")
    log_test("Expense delete status", delete_resp.status_code == 200, f"status={delete_resp.status_code}")
    
    # Verify budget spent_amount reverted
    budget_list_resp = session.get(f"{API_BASE}/money-strategy-hub/budgets?status=all")
    budgets = budget_list_resp.json().get("budgets", [])
    reverted_budget = next((b for b in budgets if b.get("budget_id") == budget_id), None)
    
    if reverted_budget:
        reverted_spent = float(reverted_budget.get("spent_amount", 0))
        reverted_remaining = float(reverted_budget.get("remaining_amount", 0))
        log_test("Budget spent_amount reverted after delete", reverted_spent == 0, f"spent={reverted_spent}")
        log_test("Budget remaining_amount reverted", reverted_remaining == 1000, f"remaining={reverted_remaining}")
    
    # Cleanup: archive the test budget
    session.delete(f"{API_BASE}/money-strategy-hub/budgets/{budget_id}")


def test_expenses_list_no_objectid():
    resp = session.get(f"{API_BASE}/money-strategy-hub/expenses")
    if resp.status_code != 200:
        log_test("Expenses list status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Expenses list no ObjectId leak", leak is None, leak or "Clean")
    
    err = check_json_serializable(data)
    log_test("Expenses list JSON serializable", err is None, err or "Valid JSON")


def test_expense_analytics_no_objectid():
    resp = session.get(f"{API_BASE}/money-strategy-hub/expenses/analytics")
    if resp.status_code != 200:
        log_test("Expense analytics status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Expense analytics no ObjectId leak", leak is None, leak or "Clean")
    
    # Verify structure
    has_summary = "summary" in data
    has_categories = "top_categories" in data
    has_trend = "daily_trend" in data
    log_test("Expense analytics structure", has_summary and has_categories and has_trend, 
             f"summary={has_summary}, categories={has_categories}, trend={has_trend}")


def test_savings_goals_no_objectid():
    # Create
    resp = session.post(f"{API_BASE}/money-strategy-hub/savings-goals", json={
        "title": "ObjectId Test Goal",
        "target_amount": 5000
    })
    if resp.status_code != 200:
        log_test("Savings goal create status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Savings goal create no ObjectId leak", leak is None, leak or "Clean")
    
    # List
    resp = session.get(f"{API_BASE}/money-strategy-hub/savings-goals")
    data = resp.json()
    leak = check_no_objectid(data)
    log_test("Savings goals list no ObjectId leak", leak is None, leak or "Clean")


def test_bill_reminders_no_objectid():
    from datetime import datetime, timezone, timedelta
    due_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    
    resp = session.post(f"{API_BASE}/money-strategy-hub/bill-reminders", json={
        "title": "ObjectId Test Bill",
        "amount_due": 99.99,
        "due_date": due_date
    })
    if resp.status_code != 200:
        log_test("Bill reminder create status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Bill reminder create no ObjectId leak", leak is None, leak or "Clean")
    
    # List
    resp = session.get(f"{API_BASE}/money-strategy-hub/bill-reminders?status=all")
    data = resp.json()
    leak = check_no_objectid(data)
    log_test("Bill reminders list no ObjectId leak", leak is None, leak or "Clean")


def test_portfolio_no_objectid():
    # Create position
    resp = session.post(f"{API_BASE}/money-strategy-hub/portfolio/positions", json={
        "asset_type": "etf",
        "symbol": "VTI",
        "quantity": 10,
        "average_cost": 220,
        "current_price": 235
    })
    if resp.status_code != 200:
        log_test("Portfolio position create status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Portfolio position create no ObjectId leak", leak is None, leak or "Clean")
    
    # List
    resp = session.get(f"{API_BASE}/money-strategy-hub/portfolio/positions")
    data = resp.json()
    leak = check_no_objectid(data)
    log_test("Portfolio positions list no ObjectId leak", leak is None, leak or "Clean")
    
    # Analytics
    resp = session.get(f"{API_BASE}/money-strategy-hub/portfolio/analytics")
    data = resp.json()
    leak = check_no_objectid(data)
    log_test("Portfolio analytics no ObjectId leak", leak is None, leak or "Clean")
    
    # Verify analytics structure
    has_summary = "summary" in data
    has_allocation = "allocation" in data
    log_test("Portfolio analytics structure", has_summary and has_allocation,
             f"summary={has_summary}, allocation={has_allocation}")


def test_receipt_scan_no_objectid():
    resp = session.post(f"{API_BASE}/money-strategy-hub/receipt-scan", json={
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGP8z8Dwn4GBgYGJAQoAHxcCAr7mDbQAAAAASUVORK5CYII="
    })
    if resp.status_code != 200:
        log_test("Receipt scan status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("Receipt scan no ObjectId leak", leak is None, leak or "Clean")
    
    # Verify structure
    has_scan = "scan" in data
    has_draft = "expense_draft" in data
    log_test("Receipt scan structure", has_scan and has_draft, f"scan={has_scan}, draft={has_draft}")


def test_ai_advisor_no_objectid():
    resp = session.post(f"{API_BASE}/money-strategy-hub/ai-advisor", json={
        "question": "What's a good savings strategy?",
        "planning_horizon_months": 6
    })
    if resp.status_code != 200:
        log_test("AI advisor status", False, f"status={resp.status_code}")
        return
    data = resp.json()
    
    leak = check_no_objectid(data)
    log_test("AI advisor no ObjectId leak", leak is None, leak or "Clean")
    
    # Verify structure
    has_run = "run" in data
    has_context = "context_snapshot" in data
    run = data.get("run", {})
    has_advice = "advice" in run
    log_test("AI advisor structure", has_run and has_context and has_advice,
             f"run={has_run}, context={has_context}, advice={has_advice}")


def print_summary():
    print("\n" + "=" * 88)
    print("MONEY STRATEGY HUB DEEP VALIDATION SUMMARY")
    print("=" * 88)
    print(f"Total:  {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    if results["errors"]:
        print("\nErrors:")
        for err in results["errors"]:
            print(f"- {err}")
    print("=" * 88)
    return 1 if results["failed"] else 0


def run_all():
    if not login():
        return 1
    
    test_bootstrap_no_objectid()
    test_profile_no_objectid()
    test_budget_expense_linkage()
    test_expenses_list_no_objectid()
    test_expense_analytics_no_objectid()
    test_savings_goals_no_objectid()
    test_bill_reminders_no_objectid()
    test_portfolio_no_objectid()
    test_receipt_scan_no_objectid()
    test_ai_advisor_no_objectid()
    
    return print_summary()


if __name__ == "__main__":
    raise SystemExit(run_all())
