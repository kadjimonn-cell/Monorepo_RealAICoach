"""
Daily Meditation E2E tests
Scope: feature map, quotas, reminders, exports, and community flow.
"""

import os
import requests
import pytest
import time


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "tv.free.test@realaicoach.app", "password": "TvFree#2026!Aa"}
FREE_CREDS_FALLBACKS = [
    {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
    {"email": "sso.test.1779125847@example.com", "password": "SsoTest#2026Aa"},
    {"email": "apple.link.e2e.1779207440@example.com", "password": "AppleLinkE2E#2026Aa!"},
    {"email": "jobs.free.final.90705154@gmail.com", "password": "JobsFree#2026Aa!"},
]


class Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )
        self.tokens = {}
        self.user_ids = {}

    def login(self, creds: dict, alias: str) -> str:
        attempts = 0
        r = None
        while attempts < 3:
            attempts += 1
            r = self.s.post(
                f"{BASE_URL}/api/auth/login",
                json=creds,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if r.status_code == 200:
                break
            if r.status_code == 429:
                retry_after = 1
                try:
                    payload = r.json()
                    retry_after = int(payload.get("retry_after") or payload.get("detail", {}).get("retry_after_seconds") or 1)
                except Exception:
                    retry_after = 1
                time.sleep(min(max(retry_after, 1), 3))
                continue
            return ""

        if not r or r.status_code != 200:
            return ""
        data = r.json()
        cookie_token = r.cookies.get("session_token") or self.s.cookies.get("session_token")
        token = cookie_token or data.get("session_token") or data.get("token")
        uid = data.get("user_id")
        self.tokens[alias] = token
        self.user_ids[alias] = uid
        return token or ""

    def headers(self, alias: str):
        return {"Authorization": f"Bearer {self.tokens.get(alias, '')}", "Content-Type": "application/json"}


session = Session()


@pytest.fixture(scope="module", autouse=True)
def bootstrap_auth():
    if not session.login(ADMIN_CREDS, "admin"):
        pytest.skip("Admin login failed in current environment")

    free_candidates = [FREE_CREDS, *FREE_CREDS_FALLBACKS]
    for creds in free_candidates:
        if session.login(creds, "free"):
            return
    pytest.skip("No valid free test credential available in current environment")


def test_feature_map_returns_31_features():
    uid = session.user_ids["free"]
    r = requests.get(
        f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
        params={"user_id": uid},
        headers=session.headers("free"),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data.get("total_features") or 0) >= 31, f"Expected at least 31, got {data.get('total_features')}"


def test_free_user_checkin_quota_enforced_daily_limit():
    uid = session.user_ids["free"]
    headers = session.headers("free")

    statuses = []
    payloads = [
        {"user_id": uid, "heart_text": "Need peace and focus.", "mood": "anxious", "energy": 2},
        {"user_id": uid, "heart_text": "Second check-in for today.", "mood": "hopeful", "energy": 3},
        {"user_id": uid, "heart_text": "Third should hit limit.", "mood": "tired", "energy": 2},
    ]
    for body in payloads:
        r = requests.post(f"{BASE_URL}/api/travel-visa/daily-meditation/checkin", headers=headers, json=body)
        statuses.append(r.status_code)

    assert all(code in {200, 429} for code in statuses), f"Unexpected status sequence: {statuses}"
    assert statuses[-1] == 429, f"Expected limit enforcement on last call, got sequence {statuses}"


def test_admin_can_share_community_and_export():
    uid = session.user_ids["admin"]
    headers = session.headers("admin")

    share = requests.post(
        f"{BASE_URL}/api/travel-visa/daily-meditation/community/share",
        headers=headers,
        json={"user_id": uid, "text": "Praying for wisdom and calm execution today.", "anonymized": False, "tags": ["focus"]},
    )
    assert share.status_code == 200, share.text

    export_json = requests.get(
        f"{BASE_URL}/api/travel-visa/daily-meditation/compliance/export/{uid}",
        headers=headers,
        params={"format": "json"},
    )
    assert export_json.status_code == 200, export_json.text
    payload = export_json.json()
    assert payload.get("user_id") == uid
    assert "counts" in payload


def test_reminder_notify_now_dispatches_without_crash():
    uid = session.user_ids["free"]
    headers = session.headers("free")
    r = requests.post(
        f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/notify-now",
        headers=headers,
        json={"user_id": uid, "kind": "daily_gift"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "queued_and_dispatched"
    assert "dispatch" in data
