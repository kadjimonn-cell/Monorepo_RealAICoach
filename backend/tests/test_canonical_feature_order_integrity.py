import os
import requests
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


EXPECTED_ORDER = [
    (1, "ai-writer", "Smart Writing Studio"),
    (2, "ai-chatbot", "Personal AI Assistant"),
    (3, "ai-search", "Deep Research Navigator"),
    (4, "ai-automations", "Workflow Builder"),
    (5, "ai-cognitive", "Decision Coach"),
    (6, "school-tutor", "Learning Coach"),
    (7, "medimate", "Health Guide"),
    (8, "fitness", "Fitness Planner Pro"),
    (9, "pennypilot", "Money Strategy Hub"),
    (10, "smartbuy", "Smart Shopping Advisor"),
    (11, "travelpal", "Travel Planner Pro"),
    (12, "ai-found-love", "Relationship Coach"),
    (13, "smart-cars", "Mobility Assistant"),
    (14, "buy-smart-home", "Property Decision Advisor"),
    (15, "ai-video", "Video Creator Studio"),
    (16, "ai-photo", "Image & Design Studio"),
    (17, "ai-speech", "Voice Studio"),
    (18, "ai-enterprise", "Business Operations Copilot"),
    (19, "bill-generator", "Bill Generator"),
    (20, "lexicon-intelligence", "Lexicon Intelligence Hub"),
    (21, "watch-videos", "Watch Videos"),
    (22, "games-station", "FPS Game"),
    (23, "travel-visa", "Travel Visa"),
    (24, "ai-learning-hub", "Learning Hub"),
    (25, "daily-meditation", "Daily Meditation"),
    (26, "jobs-portal", "Job Search"),
    (27, "id-checker", "ID Checker"),
    (28, "audio-studio", "Audio Studio"),
    (29, "my-podcasts", "My Podcasts"),
    (30, "sports", "Sports"),
    (31, "ai-coaching-team", "AI Coaching Team"),
    (32, "ai-briefing", "Daily Briefing"),
    (33, "library", "Library"),
    (34, "book-meeting", "My Agenda"),
    (35, "integrations", "Integrations"),
    (36, "referrals", "Referral Program"),
    (37, "flappy-bird", "Flappy Bird Game"),
]


def test_canonical_feature_order_registry_contract():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set; skipping live canonical registry contract check.")

    response = requests.get(f"{BASE_URL}/api/features/registry", timeout=30)
    assert response.status_code == 200, f"Registry fetch failed: {response.status_code}"

    payload = response.json()
    order_policy = payload.get("order_policy") or {}
    assert order_policy.get("source") == "locked_canonical_36"
    assert int(order_policy.get("locked_feature_count") or 0) == 37

    features = payload.get("features") or []
    assert len(features) >= 37

    by_number = {int(item.get("feature_number")): item for item in features if item.get("feature_number") is not None}
    assert len(by_number) >= 37

    for number, feature_id, title in EXPECTED_ORDER:
        row = by_number.get(number)
        assert row is not None, f"Missing feature_number={number}"
        assert row.get("feature_id") == feature_id, f"feature_number {number} id mismatch"
        assert str(row.get("title") or "").strip() == title, f"feature_number {number} title mismatch"
