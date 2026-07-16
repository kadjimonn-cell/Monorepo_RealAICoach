"""Global platform subscription access-control regression tests.

Verifies that paid/authenticated feature families are no longer treated as public,
and that Free / Basic / Premium access decisions remain consistent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.public_api_contract import is_public_api_path
from utils.access_control_engine import evaluate_api_access


PAID_AUTH_REQUIRED_PATHS = [
    "/api/bill-generator/bootstrap",
    "/api/personal-assistant/bootstrap",
    "/api/research-navigator/bootstrap",
    "/api/money-strategy-hub/bootstrap",
    "/api/smart-shopping-advisor/bootstrap",
    "/api/travel-planner-pro/bootstrap",
    "/api/video-studio/bootstrap",
    "/api/ai-photo-studio/bootstrap",
    "/api/ai-speech-studio/bootstrap",
    "/api/ai-enterprise/bootstrap",
    "/api/relationship-coach/bootstrap",
    "/api/decision-coach/bootstrap",
    "/api/mobility-assistant/bootstrap",
    "/api/writing-studio/bootstrap",
]


def _doc(plan: str, *, payment_verified: bool = True) -> dict:
    return {
        "user_id": f"user_{plan}",
        "email": f"{plan}@example.com",
        "is_admin": False,
        "subscription_plan": plan,
        "subscription_status": "active",
        "payment_verified": payment_verified,
    }


def test_paid_authenticated_families_are_not_public_anymore():
    for path in PAID_AUTH_REQUIRED_PATHS:
        assert not is_public_api_path(path), f"{path} must not be public"


def test_paid_authenticated_families_require_auth_context():
    for path in PAID_AUTH_REQUIRED_PATHS:
        decision = evaluate_api_access(path, "GET", None)
        assert decision["allowed"] is True
        assert decision["reason"] == "missing_user_context"
        assert decision["required_level"] == 1


def test_free_user_is_blocked_from_paid_authenticated_families():
    free_doc = _doc("free", payment_verified=False)
    for path in PAID_AUTH_REQUIRED_PATHS:
        decision = evaluate_api_access(path, "GET", free_doc)
        assert decision["allowed"] is False
        assert decision["reason"] == "subscription_required"
        assert decision["required_plan"] == "basic"


def test_basic_user_can_access_paid_authenticated_basic_families():
    basic_doc = _doc("basic", payment_verified=True)
    for path in PAID_AUTH_REQUIRED_PATHS:
        decision = evaluate_api_access(path, "GET", basic_doc)
        assert decision["allowed"] is True, f"Basic should access {path}: {decision}"


def test_basic_user_is_blocked_from_real_premium_only_family():
    basic_doc = _doc("basic", payment_verified=True)
    decision = evaluate_api_access("/api/workspace/bootstrap", "GET", basic_doc)
    assert decision["allowed"] is False
    assert decision["reason"] == "subscription_required"
    assert decision["required_plan"] == "premium"
