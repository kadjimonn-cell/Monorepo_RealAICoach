import ast
from pathlib import Path


def test_fedapay_notification_calls_use_keyword_arguments_only() -> None:
    file_path = Path(__file__).resolve().parents[1] / "routes" / "payments_fedapay_routes.py"
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_send_payment_notification":
            calls.append(node)

    assert calls, "Expected at least one _send_payment_notification call in payments_fedapay_routes.py"

    required_keys = {
        "user_id",
        "email",
        "user_name",
        "plan_name",
        "amount",
        "payment_method",
        "ticket_id",
        "billing_cycle",
        "renewal_date",
    }

    for call in calls:
        assert len(call.args) == 0, "_send_payment_notification must be called with keyword args only"
        provided = {kw.arg for kw in call.keywords if kw.arg}
        assert required_keys.issubset(provided), "Missing required keyword arguments in _send_payment_notification call"


def test_fedapay_completed_notification_uses_usd_amount_for_pricing_guard() -> None:
    file_path = Path(__file__).resolve().parents[1] / "routes" / "payments_fedapay_routes.py"
    source = file_path.read_text(encoding="utf-8")
    assert 'amount=tx.get("amount_usd", tx.get("amount", 0))' in source
