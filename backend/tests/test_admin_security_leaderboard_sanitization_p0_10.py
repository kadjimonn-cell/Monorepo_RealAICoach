from pathlib import Path
import ast


SOURCE_PATH = Path("/app/backend/routes/admin_console.py")


def _security_leaderboard_segment() -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    marker = '@router.get("/admin/security-leaderboard")'
    start = source.index(marker)
    return source[start:]


def _extract_security_leaderboard_function() -> ast.AsyncFunctionDef:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "security_leaderboard":
            return node
    raise AssertionError("security_leaderboard function not found")


def _dict_const_keys(node: ast.Dict) -> set[str]:
    keys: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def test_security_leaderboard_does_not_expose_sensitive_security_signals() -> None:
    segment = _security_leaderboard_segment()

    assert '"password_hash": 1' not in segment
    assert "backup_codes" not in segment
    assert "biometric_pins" not in segment
    assert "security_events.count_documents" not in segment
    assert '"score"' not in segment
    assert '"factors"' not in segment


def test_security_leaderboard_returns_only_boolean_security_aggregates() -> None:
    segment = _security_leaderboard_segment()

    assert '"has_2fa": has_2fa' in segment
    assert '"has_passkey": bool(has_pk)' in segment
    assert '"has_2fa_count": has_2fa_count' in segment
    assert '"has_passkey_count": has_passkey_count' in segment


def test_security_leaderboard_contract_uses_strict_allowlisted_keys() -> None:
    fn = _extract_security_leaderboard_function()

    per_user_dict_keys: set[str] | None = None
    return_dict_keys: set[str] | None = None

    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Dict)
        ):
            per_user_dict_keys = _dict_const_keys(node.args[0])

        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return_dict_keys = _dict_const_keys(node.value)

    assert per_user_dict_keys == {
        "user_id",
        "email",
        "name",
        "has_2fa",
        "has_passkey",
    }

    assert return_dict_keys == {
        "users",
        "total_users",
        "has_2fa_count",
        "has_passkey_count",
    }


def test_security_leaderboard_uses_batched_queries_not_per_user_find_one() -> None:
    segment = _security_leaderboard_segment()

    assert '"user_id": {"$in": user_ids}' in segment
    assert "db.user_security.find_one" not in segment
    assert "db.webauthn_credentials.find_one" not in segment
    assert "db.user_security.find(" in segment
    assert "db.webauthn_credentials.find(" in segment
