import time
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import api_rate_limiter as limiter


def _install_fake_cache(monkeypatch):
    cache_state = {}

    async def fake_get(prefix, token):
        key = f"{prefix}:{token}"
        item = cache_state.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at <= time.time():
            cache_state.pop(key, None)
            return None
        return value

    async def fake_set(prefix, token, value, ttl_seconds):
        key = f"{prefix}:{token}"
        cache_state[key] = (bool(value), time.time() + ttl_seconds)

    async def fake_delete(prefix, token):
        cache_state.pop(f"{prefix}:{token}", None)

    monkeypatch.setattr(limiter, "_cache_get_bool", fake_get)
    monkeypatch.setattr(limiter, "_cache_set_bool", fake_set)
    monkeypatch.setattr(limiter, "_cache_delete", fake_delete)
    return cache_state


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def find_one(self, query, projection):
        self.calls += 1
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items()):
                return {k: row.get(k) for k in projection.keys()}
        return None


class _FakeDB:
    def __init__(self, session_rows, user_rows):
        self.sessions = _FakeCollection(session_rows)
        self.users = _FakeCollection(user_rows)


def _request(method: str, path: str, token: str) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_admin_cache_ttl_contract_is_hardened():
    assert limiter.ADMIN_TOKEN_CACHE_TTL_SECONDS <= 5


@pytest.mark.asyncio
async def test_non_mutation_admin_check_can_use_short_cache(monkeypatch):
    token = "token_get_admin"
    cache_state = _install_fake_cache(monkeypatch)

    fake_db = _FakeDB(
        session_rows=[{"session_token": token, "is_active": True, "user_id": "user_admin"}],
        user_rows=[{"user_id": "user_admin", "is_admin": True, "role": "admin"}],
    )

    import routes.db as routes_db

    monkeypatch.setattr(routes_db, "db", fake_db)

    request = _request("GET", "/api/admin/security/audit", token)
    assert await limiter._is_authenticated_admin(request) is True
    assert fake_db.sessions.calls == 1
    assert fake_db.users.calls == 1

    assert await limiter._is_authenticated_admin(request) is True
    assert fake_db.sessions.calls == 1
    assert fake_db.users.calls == 1

    cached = cache_state.get(f"{limiter._ADMIN_TOKEN_CACHE_PREFIX}:{token}")
    assert cached is not None
    ttl_remaining = cached[1] - time.time()
    assert 0 < ttl_remaining <= 5.1


@pytest.mark.asyncio
async def test_admin_mutation_bypasses_cache_and_revalidates(monkeypatch):
    token = "token_post_mutation"
    cache_state = _install_fake_cache(monkeypatch)
    cache_state[f"{limiter._ADMIN_TOKEN_CACHE_PREFIX}:{token}"] = (True, time.time() + 300)

    fake_db = _FakeDB(
        session_rows=[{"session_token": token, "is_active": True, "user_id": "user_revoked"}],
        user_rows=[{"user_id": "user_revoked", "is_admin": False, "role": "user"}],
    )

    import routes.db as routes_db

    monkeypatch.setattr(routes_db, "db", fake_db)

    mutation_request = _request("POST", "/api/admin/security/waf/rules", token)
    assert await limiter._is_authenticated_admin(mutation_request) is False

    assert fake_db.sessions.calls == 1
    assert fake_db.users.calls == 1
    assert f"{limiter._ADMIN_TOKEN_CACHE_PREFIX}:{token}" not in cache_state
