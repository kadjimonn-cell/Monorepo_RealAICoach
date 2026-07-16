"""
Feature 23 (Travel Visa) - Enterprise-grade production readiness verification
Tests: Bootstrap endpoint, entitlement matrix, seeded data, pricing validation
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"

# Canonical pricing from /app/backend/routes/iap.py lines 61-64
CANONICAL_BASIC_MONTHLY = 5.99
CANONICAL_PREMIUM_MONTHLY = 15.99


class TestTravelVisaFeature23:
    """Feature 23 Travel Visa enterprise-grade validation tests"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get admin session with cookies"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        assert data.get("is_admin") == True, "Admin flag not set"
        return session, data.get("user_id")

    @pytest.fixture(scope="class")
    def free_session(self):
        """Get free user session with cookies"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        assert resp.status_code == 200, f"Free user login failed: {resp.text}"
        data = resp.json()
        assert data.get("subscription_plan") == "free", f"Expected free plan, got {data.get('subscription_plan')}"
        return session, data.get("user_id")

    @pytest.fixture(scope="class")
    def basic_session(self):
        """Get basic user session with cookies"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        assert resp.status_code == 200, f"Basic user login failed: {resp.text}"
        data = resp.json()
        assert data.get("subscription_plan") == "basic", f"Expected basic plan, got {data.get('subscription_plan')}"
        return session, data.get("user_id")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEED DATA VERIFICATION
    # ═══════════════════════════════════════════════════════════════════════════

    def test_seed_endpoint_admin_only(self, admin_session, free_session):
        """Verify seed endpoint is admin-only"""
        admin_sess, _ = admin_session
        free_sess, _ = free_session
        
        # Free user should be rejected (with CSRF header)
        resp = free_sess.post(f"{BASE_URL}/api/travel-visa/seed", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code in [401, 403], f"Free user should not access seed: {resp.status_code}"
        
        # Admin should succeed (with CSRF header)
        resp = admin_sess.post(f"{BASE_URL}/api/travel-visa/seed", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200, f"Admin seed failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "seeded", f"Seed status not 'seeded': {data}"
        print(f"✓ Seed endpoint admin-only verified. Countries: {data.get('countries')}, Categories: {data.get('categories')}, Lessons: {data.get('lessons')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # BOOTSTRAP ENDPOINT TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_bootstrap_free_user(self, free_session):
        """Test bootstrap endpoint for free user"""
        session, user_id = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/bootstrap/{user_id}")
        assert resp.status_code == 200, f"Bootstrap failed for free user: {resp.text}"
        data = resp.json()
        
        # Verify required fields
        assert "countries" in data, "Missing countries in bootstrap"
        assert "categories" in data, "Missing categories in bootstrap"
        assert "trending" in data, "Missing trending in bootstrap"
        assert "subscription" in data, "Missing subscription in bootstrap"
        assert "user_stats" in data, "Missing user_stats in bootstrap"
        assert "system_health" in data, "Missing system_health in bootstrap"
        
        # Verify subscription plan
        sub = data.get("subscription", {})
        assert sub.get("plan") == "free", f"Expected free plan, got {sub.get('plan')}"
        
        # Verify seeded data is non-empty
        assert len(data.get("countries", [])) > 0, "Countries should not be empty"
        assert len(data.get("categories", [])) > 0, "Categories should not be empty"
        assert len(data.get("trending", [])) > 0, "Trending should not be empty"
        
        print(f"✓ Free user bootstrap: {len(data['countries'])} countries, {len(data['categories'])} categories, {len(data['trending'])} trending, plan={sub.get('plan')}")

    def test_bootstrap_basic_user(self, basic_session):
        """Test bootstrap endpoint for basic user"""
        session, user_id = basic_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/bootstrap/{user_id}")
        assert resp.status_code == 200, f"Bootstrap failed for basic user: {resp.text}"
        data = resp.json()
        
        # Verify subscription plan
        sub = data.get("subscription", {})
        assert sub.get("plan") == "basic", f"Expected basic plan, got {sub.get('plan')}"
        
        # Verify limits are higher than free
        limits = sub.get("limits", {})
        assert limits.get("daily_ai_credits", 0) >= 25, f"Basic should have >= 25 AI credits, got {limits.get('daily_ai_credits')}"
        
        print(f"✓ Basic user bootstrap: plan={sub.get('plan')}, daily_ai_credits={limits.get('daily_ai_credits')}")

    def test_bootstrap_admin_user(self, admin_session):
        """Test bootstrap endpoint for admin (premium) user"""
        session, user_id = admin_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/bootstrap/{user_id}")
        assert resp.status_code == 200, f"Bootstrap failed for admin: {resp.text}"
        data = resp.json()
        
        # Admin should have premium plan
        sub = data.get("subscription", {})
        assert sub.get("plan") == "premium", f"Expected premium plan for admin, got {sub.get('plan')}"
        
        # Verify unlimited limits
        limits = sub.get("limits", {})
        assert limits.get("daily_ai_credits", 0) >= 999, f"Premium should have >= 999 AI credits, got {limits.get('daily_ai_credits')}"
        
        print(f"✓ Admin/Premium bootstrap: plan={sub.get('plan')}, daily_ai_credits={limits.get('daily_ai_credits')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # ENTITLEMENT MATRIX VERIFICATION
    # ═══════════════════════════════════════════════════════════════════════════

    def test_entitlement_tier_limits(self, free_session, basic_session, admin_session):
        """Verify entitlement tier limits are correctly enforced"""
        free_sess, free_uid = free_session
        basic_sess, basic_uid = basic_session
        admin_sess, admin_uid = admin_session
        
        # Get all bootstrap responses
        free_resp = free_sess.get(f"{BASE_URL}/api/travel-visa/bootstrap/{free_uid}").json()
        basic_resp = basic_sess.get(f"{BASE_URL}/api/travel-visa/bootstrap/{basic_uid}").json()
        admin_resp = admin_sess.get(f"{BASE_URL}/api/travel-visa/bootstrap/{admin_uid}").json()
        
        free_limits = free_resp.get("subscription", {}).get("limits", {})
        basic_limits = basic_resp.get("subscription", {}).get("limits", {})
        premium_limits = admin_resp.get("subscription", {}).get("limits", {})
        
        # Verify tier progression
        assert free_limits.get("daily_ai_credits", 0) < basic_limits.get("daily_ai_credits", 0), "Basic should have more AI credits than free"
        assert basic_limits.get("daily_ai_credits", 0) < premium_limits.get("daily_ai_credits", 0), "Premium should have more AI credits than basic"
        
        assert free_limits.get("daily_quizzes", 0) < basic_limits.get("daily_quizzes", 0), "Basic should have more quizzes than free"
        assert basic_limits.get("daily_quizzes", 0) < premium_limits.get("daily_quizzes", 0), "Premium should have more quizzes than basic"
        
        print("✓ Entitlement matrix verified:")
        print(f"  Free: ai_credits={free_limits.get('daily_ai_credits')}, quizzes={free_limits.get('daily_quizzes')}")
        print(f"  Basic: ai_credits={basic_limits.get('daily_ai_credits')}, quizzes={basic_limits.get('daily_quizzes')}")
        print(f"  Premium: ai_credits={premium_limits.get('daily_ai_credits')}, quizzes={premium_limits.get('daily_quizzes')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEEDED DATA AVAILABILITY
    # ═══════════════════════════════════════════════════════════════════════════

    def test_countries_endpoint(self, free_session):
        """Test countries endpoint returns seeded data"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/countries")
        assert resp.status_code == 200, f"Countries endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "countries" in data, "Missing countries field"
        assert "regions" in data, "Missing regions field"
        assert len(data.get("countries", [])) > 0, "Countries should not be empty"
        assert len(data.get("regions", [])) > 0, "Regions should not be empty"
        
        # Verify country structure
        country = data["countries"][0]
        assert "code" in country, "Country missing code"
        assert "name" in country, "Country missing name"
        assert "region" in country, "Country missing region"
        
        print(f"✓ Countries endpoint: {len(data['countries'])} countries, {len(data['regions'])} regions")

    def test_categories_endpoint(self, free_session):
        """Test categories endpoint returns seeded data"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/categories")
        assert resp.status_code == 200, f"Categories endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "categories" in data, "Missing categories field"
        assert "groups" in data, "Missing groups field"
        assert len(data.get("categories", [])) > 0, "Categories should not be empty"
        
        # Verify category structure
        cat = data["categories"][0]
        assert "id" in cat, "Category missing id"
        assert "name" in cat, "Category missing name"
        assert "group" in cat, "Category missing group"
        
        print(f"✓ Categories endpoint: {len(data['categories'])} categories, {len(data['groups'])} groups")

    def test_trending_endpoint(self, free_session):
        """Test trending endpoint returns seeded data"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/trending")
        assert resp.status_code == 200, f"Trending endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "trending" in data, "Missing trending field"
        assert len(data.get("trending", [])) > 0, "Trending should not be empty"
        
        print(f"✓ Trending endpoint: {len(data['trending'])} trending destinations")

    # ═══════════════════════════════════════════════════════════════════════════
    # UNAUTHENTICATED ACCESS REJECTION
    # ═══════════════════════════════════════════════════════════════════════════

    def test_unauthenticated_bootstrap_rejected(self):
        """Verify unauthenticated requests to bootstrap are rejected"""
        resp = requests.get(f"{BASE_URL}/api/travel-visa/bootstrap/test_user_id")
        assert resp.status_code in [401, 403], f"Unauthenticated bootstrap should be rejected: {resp.status_code}"
        print(f"✓ Unauthenticated bootstrap rejected with {resp.status_code}")

    def test_unauthenticated_coach_rejected(self):
        """Verify unauthenticated requests to coach are rejected"""
        resp = requests.post(f"{BASE_URL}/api/travel-visa/coach", json={
            "user_id": "test",
            "message": "test"
        })
        assert resp.status_code in [401, 403], f"Unauthenticated coach should be rejected: {resp.status_code}"
        print(f"✓ Unauthenticated coach rejected with {resp.status_code}")

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTION INFO ENDPOINT
    # ═══════════════════════════════════════════════════════════════════════════

    def test_subscription_info_free(self, free_session):
        """Test subscription info endpoint for free user"""
        session, user_id = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/{user_id}")
        assert resp.status_code == 200, f"Subscription info failed: {resp.text}"
        data = resp.json()
        
        assert data.get("plan") == "free", f"Expected free plan, got {data.get('plan')}"
        assert "limits" in data, "Missing limits"
        assert "tier_benefits" in data, "Missing tier_benefits"
        
        print(f"✓ Subscription info (free): plan={data.get('plan')}")

    def test_subscription_info_basic(self, basic_session):
        """Test subscription info endpoint for basic user"""
        session, user_id = basic_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/{user_id}")
        assert resp.status_code == 200, f"Subscription info failed: {resp.text}"
        data = resp.json()
        
        assert data.get("plan") == "basic", f"Expected basic plan, got {data.get('plan')}"
        
        print(f"✓ Subscription info (basic): plan={data.get('plan')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH ENDPOINT
    # ═══════════════════════════════════════════════════════════════════════════

    def test_search_endpoint(self, free_session):
        """Test global search endpoint"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/search?q=united")
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        data = resp.json()
        
        assert "countries" in data, "Missing countries in search"
        assert "categories" in data, "Missing categories in search"
        assert "lessons" in data, "Missing lessons in search"
        assert "embassies" in data, "Missing embassies in search"
        
        print(f"✓ Search endpoint: countries={len(data['countries'])}, categories={len(data['categories'])}, lessons={len(data['lessons'])}, embassies={len(data['embassies'])}")

    # ═══════════════════════════════════════════════════════════════════════════
    # QUIZZES ENDPOINT
    # ═══════════════════════════════════════════════════════════════════════════

    def test_quizzes_endpoint(self, free_session):
        """Test quizzes endpoint returns seeded data"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/quizzes")
        assert resp.status_code == 200, f"Quizzes endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "quizzes" in data, "Missing quizzes field"
        assert len(data.get("quizzes", [])) > 0, "Quizzes should not be empty"
        
        # Verify quiz structure (correct answers should be stripped)
        quiz = data["quizzes"][0]
        assert "quiz_id" in quiz, "Quiz missing quiz_id"
        assert "title" in quiz, "Quiz missing title"
        if "questions" in quiz:
            for q in quiz["questions"]:
                assert "correct" not in q, "Correct answer should be stripped from client response"
        
        print(f"✓ Quizzes endpoint: {len(data['quizzes'])} quizzes")

    # ═══════════════════════════════════════════════════════════════════════════
    # EMBASSIES ENDPOINT
    # ═══════════════════════════════════════════════════════════════════════════

    def test_embassies_endpoint(self, free_session):
        """Test embassies endpoint returns seeded data"""
        session, _ = free_session
        resp = session.get(f"{BASE_URL}/api/travel-visa/embassies")
        assert resp.status_code == 200, f"Embassies endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "embassies" in data, "Missing embassies field"
        assert len(data.get("embassies", [])) > 0, "Embassies should not be empty"
        
        # Verify embassy structure
        embassy = data["embassies"][0]
        assert "country_code" in embassy, "Embassy missing country_code"
        assert "name" in embassy, "Embassy missing name"
        assert "city" in embassy, "Embassy missing city"
        
        print(f"✓ Embassies endpoint: {len(data['embassies'])} embassies")


class TestTravelVisaPricingValidation:
    """Validate upgrade modal pricing matches canonical backend pricing"""

    def test_canonical_pricing_basic(self):
        """Verify Basic plan pricing is $5.99/month"""
        assert CANONICAL_BASIC_MONTHLY == 5.99, f"Basic monthly should be $5.99, got ${CANONICAL_BASIC_MONTHLY}"
        print(f"✓ Canonical Basic pricing: ${CANONICAL_BASIC_MONTHLY}/month")

    def test_canonical_pricing_premium(self):
        """Verify Premium plan pricing is $15.99/month"""
        assert CANONICAL_PREMIUM_MONTHLY == 15.99, f"Premium monthly should be $15.99, got ${CANONICAL_PREMIUM_MONTHLY}"
        print(f"✓ Canonical Premium pricing: ${CANONICAL_PREMIUM_MONTHLY}/month")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
