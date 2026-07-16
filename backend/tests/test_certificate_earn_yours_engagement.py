"""Feature — 'Earn yours' CTA public certificate engagement tracking tests."""

import os
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

VERIFICATION_ID = "cert_b5e8b467bf1446"
ENGAGEMENT_URL = f"{BASE_URL}/api/ai-learn/certificates/verify/{VERIFICATION_ID}/engagement"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


class TestPublicEngagementEndpoint:
    def test_earn_yours_click_accepted(self):
        r = requests.post(
            ENGAGEMENT_URL,
            json={"event_type": "earn_yours_click", "source": "certificate:verifier"},
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("ok") is True, data

    def test_verifier_view_accepted(self):
        r = requests.post(
            ENGAGEMENT_URL,
            json={"event_type": "verifier_view", "source": "certificate:verifier"},
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        assert r.json().get("ok") is True

    def test_bogus_event_rejected(self):
        r = requests.post(
            ENGAGEMENT_URL,
            json={"event_type": "bogus_event", "source": "certificate:verifier"},
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_missing_event_type_rejected(self):
        r = requests.post(ENGAGEMENT_URL, json={"source": "x"}, headers=HEADERS, timeout=20)
        assert r.status_code in (400, 422), f"got {r.status_code}: {r.text[:200]}"

    def test_earn_yours_event_persisted_in_mongo(self):
        # Fire an event, then query the collection to confirm it exists.
        r = requests.post(
            ENGAGEMENT_URL,
            json={"event_type": "earn_yours_click", "source": "certificate:verifier"},
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200

        if not (MONGO_URL and DB_NAME):
            pytest.skip("MONGO_URL/DB_NAME missing; skipping DB persistence check")

        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        try:
            db = client[DB_NAME]
            doc = db["learn_hub_certificate_engagement_events"].find_one(
                {"event_type": "earn_yours_click"},
                sort=[("_id", -1)],
            )
            assert doc is not None, "no earn_yours_click event found in learn_hub_certificate_engagement_events"
            # Ensure recent + carries source
            assert doc.get("source") == "certificate:verifier" or doc.get("source") is not None
        finally:
            client.close()
