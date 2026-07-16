from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_auth_session_cookie_policy_has_localhost_and_secure_modes() -> None:
    source = _read("/app/backend/routes/auth.py")

    assert "def _resolve_session_cookie_security" in source
    assert 'return {"secure": False, "samesite": "lax"}' in source
    assert 'return {"secure": True, "samesite": "none"}' in source


def test_auth_routes_use_session_cookie_helpers_consistently() -> None:
    source = _read("/app/backend/routes/auth.py")

    assert "def _set_session_cookie" in source
    assert "def _delete_session_cookie" in source
    assert source.count("_set_session_cookie(") >= 10
    assert source.count("_delete_session_cookie(") >= 2
