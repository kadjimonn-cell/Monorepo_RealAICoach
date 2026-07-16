"""Feature 9 (Money Strategy Hub) backend E2E test suite.

Covers:
- Bootstrap/profile
- Budget CRUD
- Expense CRUD + analytics
- Savings goals
- Bill reminders
- Portfolio positions + analytics
- Receipt scan
- AI advisor
"""

import os
import requests
from datetime import datetime, timezone, timedelta


BASE_URL = str(os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required to run test_money_strategy_hub.py")

API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

session = requests.Session()
session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
state = {
    "budget_id": None,
    "expense_id": None,
    "goal_id": None,
    "bill_id": None,
    "position_id": None,
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


def test_bootstrap():
    resp = session.get(f"{API_BASE}/money-strategy-hub/bootstrap")
    if not assert_status(resp, 200, "Bootstrap"):
        return
    data = resp.json()
    checks = [
        "tier" in data,
        "usage" in data,
        "active" in data,
        "features" in data,
        "tier_limits" in data,
    ]
    log_test("Bootstrap structure", all(checks), f"tier={data.get('tier')}")


def test_profile_upsert_and_update():
    create_payload = {
        "currency": "USD",
        "monthly_income": 8500,
        "fixed_monthly_expenses": 3100,
        "savings_target_monthly": 1800,
        "risk_tolerance": "moderate",
        "investment_horizon_years": 5,
        "financial_goals": ["Emergency fund", "ETF accumulation"],
    }
    resp = session.post(f"{API_BASE}/money-strategy-hub/profile", json=create_payload)
    if not assert_status(resp, 200, "Profile upsert"):
        return
    log_test("Profile upsert", "profile" in resp.json())

    get_resp = session.get(f"{API_BASE}/money-strategy-hub/profile")
    if not assert_status(get_resp, 200, "Profile get"):
        return
    profile = get_resp.json().get("profile") or {}
    log_test("Profile persisted", profile.get("monthly_income") == 8500)

    update_resp = session.put(
        f"{API_BASE}/money-strategy-hub/profile",
        json={"monthly_income": 9000, "savings_target_monthly": 2200},
    )
    if not assert_status(update_resp, 200, "Profile update"):
        return
    updated = update_resp.json().get("profile") or {}
    log_test("Profile update values", updated.get("monthly_income") == 9000)


def test_budget_flow():
    create_resp = session.post(
        f"{API_BASE}/money-strategy-hub/budgets",
        json={"name": "Core Living", "category": "housing", "monthly_limit": 2500},
    )
    if not assert_status(create_resp, 200, "Create budget"):
        return
    budget = create_resp.json().get("budget") or {}
    state["budget_id"] = budget.get("budget_id")
    log_test("Create budget", bool(state["budget_id"]))

    list_resp = session.get(f"{API_BASE}/money-strategy-hub/budgets")
    if not assert_status(list_resp, 200, "List budgets"):
        return
    budgets = list_resp.json().get("budgets", [])
    log_test("Budget appears in list", any(item.get("budget_id") == state["budget_id"] for item in budgets))

    update_resp = session.put(
        f"{API_BASE}/money-strategy-hub/budgets/{state['budget_id']}",
        json={"monthly_limit": 2700, "alert_threshold_pct": 85},
    )
    if not assert_status(update_resp, 200, "Update budget"):
        return
    updated = update_resp.json().get("budget") or {}
    log_test("Budget updated", float(updated.get("monthly_limit") or 0) == 2700)


def test_expense_flow_and_analytics():
    create_resp = session.post(
        f"{API_BASE}/money-strategy-hub/expenses",
        json={
            "amount": 145.75,
            "category": "groceries",
            "merchant": "FreshMart",
            "budget_id": state["budget_id"],
            "payment_method": "card",
        },
    )
    if not assert_status(create_resp, 200, "Create expense"):
        return
    expense = create_resp.json().get("expense") or {}
    state["expense_id"] = expense.get("expense_id")
    log_test("Create expense", bool(state["expense_id"]))

    list_resp = session.get(f"{API_BASE}/money-strategy-hub/expenses")
    if not assert_status(list_resp, 200, "List expenses"):
        return
    expenses = list_resp.json().get("expenses", [])
    log_test("Expense appears in list", any(item.get("expense_id") == state["expense_id"] for item in expenses))

    analytics_resp = session.get(f"{API_BASE}/money-strategy-hub/expenses/analytics")
    if not assert_status(analytics_resp, 200, "Expense analytics"):
        return
    analytics = analytics_resp.json()
    log_test("Expense analytics summary", "summary" in analytics and "top_categories" in analytics)


def test_savings_goal_flow():
    create_resp = session.post(
        f"{API_BASE}/money-strategy-hub/savings-goals",
        json={"title": "Europe Trip", "target_amount": 3000},
    )
    if not assert_status(create_resp, 200, "Create savings goal"):
        return
    goal = create_resp.json().get("goal") or {}
    state["goal_id"] = goal.get("goal_id")
    log_test("Create savings goal", bool(state["goal_id"]))

    list_resp = session.get(f"{API_BASE}/money-strategy-hub/savings-goals")
    if not assert_status(list_resp, 200, "List savings goals"):
        return
    goals = list_resp.json().get("goals", [])
    log_test("Savings goal appears in list", any(item.get("goal_id") == state["goal_id"] for item in goals))

    update_resp = session.put(
        f"{API_BASE}/money-strategy-hub/savings-goals/{state['goal_id']}",
        json={"current_amount": 900},
    )
    if not assert_status(update_resp, 200, "Update savings goal"):
        return
    updated_goal = update_resp.json().get("goal") or {}
    log_test("Savings goal updated", float(updated_goal.get("current_amount") or 0) == 900)


def test_bill_reminder_flow():
    due_date = (datetime.now(timezone.utc) + timedelta(days=12)).isoformat()
    create_resp = session.post(
        f"{API_BASE}/money-strategy-hub/bill-reminders",
        json={"title": "Internet", "amount_due": 79.99, "due_date": due_date},
    )
    if not assert_status(create_resp, 200, "Create bill reminder"):
        return
    reminder = create_resp.json().get("bill_reminder") or {}
    state["bill_id"] = reminder.get("reminder_id")
    log_test("Create bill reminder", bool(state["bill_id"]))

    list_resp = session.get(f"{API_BASE}/money-strategy-hub/bill-reminders")
    if not assert_status(list_resp, 200, "List bill reminders"):
        return
    reminders = list_resp.json().get("bill_reminders", [])
    log_test("Bill appears in list", any(item.get("reminder_id") == state["bill_id"] for item in reminders))

    update_resp = session.put(
        f"{API_BASE}/money-strategy-hub/bill-reminders/{state['bill_id']}",
        json={"status": "paid"},
    )
    if not assert_status(update_resp, 200, "Update bill reminder"):
        return
    updated = update_resp.json().get("bill_reminder") or {}
    log_test("Bill status updated", updated.get("status") == "paid")


def test_portfolio_flow_and_analytics():
    create_resp = session.post(
        f"{API_BASE}/money-strategy-hub/portfolio/positions",
        json={
            "asset_type": "stock",
            "symbol": "MSFT",
            "quantity": 5,
            "average_cost": 340,
            "current_price": 390,
        },
    )
    if not assert_status(create_resp, 200, "Create portfolio position"):
        return
    position = create_resp.json().get("position") or {}
    state["position_id"] = position.get("position_id")
    log_test("Create portfolio position", bool(state["position_id"]))

    list_resp = session.get(f"{API_BASE}/money-strategy-hub/portfolio/positions")
    if not assert_status(list_resp, 200, "List portfolio positions"):
        return
    positions = list_resp.json().get("positions", [])
    log_test("Portfolio position appears in list", any(item.get("position_id") == state["position_id"] for item in positions))

    update_resp = session.put(
        f"{API_BASE}/money-strategy-hub/portfolio/positions/{state['position_id']}",
        json={"current_price": 405},
    )
    if not assert_status(update_resp, 200, "Update portfolio position"):
        return
    updated = update_resp.json().get("position") or {}
    log_test("Portfolio position updated", float(updated.get("current_price") or 0) == 405)

    analytics_resp = session.get(f"{API_BASE}/money-strategy-hub/portfolio/analytics")
    if not assert_status(analytics_resp, 200, "Portfolio analytics"):
        return
    analytics = analytics_resp.json()
    log_test("Portfolio analytics summary", "summary" in analytics and "allocation" in analytics)


def test_ai_endpoints():
    receipt_resp = session.post(
        f"{API_BASE}/money-strategy-hub/receipt-scan",
        json={
            "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGP8z8Dwn4GBgYGJAQoAHxcCAr7mDbQAAAAASUVORK5CYII=",
        },
    )
    if not assert_status(receipt_resp, 200, "Receipt scan"):
        return
    receipt_payload = receipt_resp.json()
    log_test("Receipt scan payload", "scan" in receipt_payload and "expense_draft" in receipt_payload)

    advisor_resp = session.post(
        f"{API_BASE}/money-strategy-hub/ai-advisor",
        json={"question": "How do I improve my budget discipline this quarter?"},
    )
    if not assert_status(advisor_resp, 200, "AI advisor"):
        return
    advisor_payload = advisor_resp.json()
    log_test("AI advisor payload", "run" in advisor_payload and "advice" in (advisor_payload.get("run") or {}))


def test_cleanup():
    if state.get("expense_id"):
        resp = session.delete(f"{API_BASE}/money-strategy-hub/expenses/{state['expense_id']}")
        log_test("Cleanup expense delete", resp.status_code == 200)

    if state.get("budget_id"):
        resp = session.delete(f"{API_BASE}/money-strategy-hub/budgets/{state['budget_id']}")
        log_test("Cleanup budget archive", resp.status_code == 200)


def print_summary():
    print("\n" + "=" * 88)
    print("MONEY STRATEGY HUB E2E SUMMARY")
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


def run_all() -> int:
    if not login():
        return 1
    test_bootstrap()
    test_profile_upsert_and_update()
    test_budget_flow()
    test_expense_flow_and_analytics()
    test_savings_goal_flow()
    test_bill_reminder_flow()
    test_portfolio_flow_and_analytics()
    test_ai_endpoints()
    test_cleanup()
    return print_summary()


if __name__ == "__main__":
    raise SystemExit(run_all())
