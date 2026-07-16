import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from utils.access_control_engine import compute_effective_plan, evaluate_api_access


def test_compute_effective_plan_requires_payment_verified_for_paid_plans():
    doc = {
        "is_admin": False,
        "subscription_plan": "premium",
        "subscription_status": "active",
        "payment_verified": False,
    }
    assert compute_effective_plan(doc) == "free"


def test_compute_effective_plan_allows_verified_paid_plan():
    doc = {
        "is_admin": False,
        "subscription_plan": "premium",
        "subscription_status": "active",
        "payment_verified": True,
    }
    assert compute_effective_plan(doc) == "premium"


def test_non_admin_platform_employee_cannot_access_team_management_admin_api():
    doc = {
        "is_admin": False,
        "subscription_plan": "premium",
        "subscription_status": "active",
        "payment_verified": True,
        "platform_role": "Support Team",
        "employee_permissions": ["employee.manage_access"],
    }
    decision = evaluate_api_access("/api/admin/employees", "GET", doc)
    assert decision["allowed"] is False
    assert decision["reason"] == "admin_required"


def test_non_admin_platform_employee_cannot_access_admin_access_control_api():
    doc = {
        "is_admin": False,
        "subscription_plan": "premium",
        "subscription_status": "active",
        "payment_verified": True,
        "platform_role": "Operations",
        "employee_permissions": ["employee.manage_subscriptions"],
    }
    decision = evaluate_api_access("/api/admin/access-control/subscription-transition", "POST", doc)
    assert decision["allowed"] is False
    assert decision["reason"] == "admin_required"
