import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes import accessibility
from routes.db import get_current_user


class _FakeAccessibilityPreferencesCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    async def find_one(self, query: dict, projection: dict | None = None):
        user_id = str(query.get("user_id") or "")
        doc = self.docs.get(user_id)
        if not doc:
            return None
        return {k: v for k, v in doc.items() if k != "_id"}

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        user_id = str(query.get("user_id") or "")
        payload = dict(update.get("$set") or {})
        self.docs[user_id] = payload
        return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)


def _build_client(monkeypatch, current_user):
    fake_db = SimpleNamespace(accessibility_preferences=_FakeAccessibilityPreferencesCollection())
    monkeypatch.setattr(accessibility, "db", fake_db)

    app = FastAPI()
    app.include_router(accessibility.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)
    return client, fake_db


def test_accessibility_preferences_requires_authenticated_user(monkeypatch) -> None:
    client, _ = _build_client(monkeypatch, current_user=None)

    response = client.get("/api/accessibility/preferences/user_a")

    assert response.status_code == 401
    assert response.json().get("detail") == "Not authenticated"


def test_accessibility_preferences_blocks_cross_user_access(monkeypatch) -> None:
    current_user = SimpleNamespace(user_id="user_a")
    client, _ = _build_client(monkeypatch, current_user=current_user)

    get_resp = client.get("/api/accessibility/preferences/user_b")
    put_resp = client.put(
        "/api/accessibility/preferences/user_b",
        json={"preferences": {"highContrast": True}},
    )
    reset_resp = client.post("/api/accessibility/preferences/user_b/reset")

    assert get_resp.status_code == 403
    assert put_resp.status_code == 403
    assert reset_resp.status_code == 403


def test_accessibility_preferences_owner_can_read_write_and_reset(monkeypatch) -> None:
    current_user = SimpleNamespace(user_id="owner_1")
    client, _ = _build_client(monkeypatch, current_user=current_user)

    initial = client.get("/api/accessibility/preferences/owner_1")
    assert initial.status_code == 200
    assert initial.json()["user_id"] == "owner_1"
    assert initial.json()["preferences"] == accessibility.DEFAULT_PREFERENCES

    updated = client.put(
        "/api/accessibility/preferences/owner_1",
        json={"preferences": {"highContrast": True, "textSize": "large"}},
    )
    assert updated.status_code == 200
    assert updated.json()["success"] is True
    assert updated.json()["preferences"]["highContrast"] is True
    assert updated.json()["preferences"]["textSize"] == "large"

    reset = client.post("/api/accessibility/preferences/owner_1/reset")
    assert reset.status_code == 200
    assert reset.json()["success"] is True
    assert reset.json()["preferences"] == accessibility.DEFAULT_PREFERENCES
