"""
Feature 20: Lexicon Intelligence Hub - 3-Tier Entitlement Verification Tests
Tests for /api/word-forge/* endpoints across Free/Basic/Premium tiers

Test credentials:
- Free: p1.free.1779113329@example.com / P1Free#2026!Aa
- Basic: f21.basic.1781338672@example.com / F21Basic#2026Aa
- Admin/Premium: admin@realaicoach.app / NewAdminPass2026!
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
PREMIUM_USER = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


class TestFeature20FreeTier:
    """Free tier verification for Feature 20"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as free user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=FREE_USER
        )
        if login_response.status_code != 200:
            pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text[:200]}")
        print(f"Free user login successful: {FREE_USER['email']}")
    
    def test_bootstrap_free_tier(self):
        """Bootstrap returns free plan with correct limits"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text[:200]}"
        data = response.json()
        
        # Verify plan
        assert data.get("plan") == "free", f"Expected plan=free, got {data.get('plan')}"
        assert data.get("scope_label") == "Limited access", f"Expected scope_label='Limited access', got {data.get('scope_label')}"
        
        # Verify limits are present and limited
        limits = data.get("limits", {})
        assert limits.get("generate_word") == 4, f"Expected generate_word=4, got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == 12, f"Expected quiz_attempt=12, got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == 24, f"Expected save_word=24, got {limits.get('save_word')}"
        
        # Verify daily_word structure
        assert "daily_word" in data, "Missing daily_word"
        assert "capabilities" in data, "Missing capabilities"
        
        print(f"PASS: Free tier bootstrap - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
        print(f"PASS: Free tier limits - generate_word={limits.get('generate_word')}, quiz_attempt={limits.get('quiz_attempt')}")
    
    def test_templates_free_tier(self):
        """Templates returns free plan recommendations"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "free"
        assert "templates" in data
        assert len(data.get("templates", [])) >= 1
        
        # Free tier should get specific recommendations
        recommended = data.get("recommended_template_ids", [])
        assert "cross-functional-ops" in recommended or "client-escalation-calm" in recommended, \
            f"Free tier should get cross-functional-ops or client-escalation-calm, got {recommended}"
        
        print(f"PASS: Free tier templates - count={len(data.get('templates', []))}, recommended={recommended}")
    
    def test_export_free_tier(self):
        """Export returns free plan data"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "payload"})
        assert response.status_code == 200, f"Export failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "free"
        assert data.get("scope_label") == "Limited access"
        assert "profile" in data
        assert "usage_summary" in data
        
        print(f"PASS: Free tier export - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
    
    def test_recommendations_free_tier(self):
        """Recommendations accessible for free tier"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 200, f"Recommendations failed: {response.text[:200]}"
        data = response.json()
        
        assert "recommendations" in data
        assert data.get("feature_id") == "lexicon-intelligence"
        
        print(f"PASS: Free tier recommendations - count={len(data.get('recommendations', []))}")


class TestFeature20BasicTier:
    """Basic tier verification for Feature 20"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as basic user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=BASIC_USER
        )
        if login_response.status_code != 200:
            pytest.skip(f"Basic user login failed: {login_response.status_code} - {login_response.text[:200]}")
        print(f"Basic user login successful: {BASIC_USER['email']}")
    
    def test_bootstrap_basic_tier(self):
        """Bootstrap returns basic plan with correct limits"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text[:200]}"
        data = response.json()
        
        # Verify plan
        assert data.get("plan") == "basic", f"Expected plan=basic, got {data.get('plan')}"
        assert data.get("scope_label") == "Almost unlimited access", f"Expected scope_label='Almost unlimited access', got {data.get('scope_label')}"
        
        # Verify limits are higher than free
        limits = data.get("limits", {})
        assert limits.get("generate_word") == 180, f"Expected generate_word=180, got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == 500, f"Expected quiz_attempt=500, got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == 1000, f"Expected save_word=1000, got {limits.get('save_word')}"
        
        print(f"PASS: Basic tier bootstrap - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
        print(f"PASS: Basic tier limits - generate_word={limits.get('generate_word')}, quiz_attempt={limits.get('quiz_attempt')}")
    
    def test_templates_basic_tier(self):
        """Templates returns basic plan recommendations"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "basic"
        assert "templates" in data
        
        print(f"PASS: Basic tier templates - plan={data.get('plan')}, count={len(data.get('templates', []))}")
    
    def test_export_basic_tier(self):
        """Export returns basic plan data"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "payload"})
        assert response.status_code == 200, f"Export failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "basic"
        assert data.get("scope_label") == "Almost unlimited access"
        
        print(f"PASS: Basic tier export - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
    
    def test_daily_word_basic_tier(self):
        """Daily word generation works for basic tier"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/daily-word", json={
            "domain": "business",
            "difficulty": "adaptive"
        })
        
        # May hit rate limit or succeed
        assert response.status_code in [200, 429], f"Daily word unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "word" in data
            assert "quota" in data
            print(f"PASS: Basic tier daily word - word={data.get('word', {}).get('word')}")
        else:
            print("PASS: Basic tier daily word - rate limited (expected if quota exhausted)")


class TestFeature20PremiumTier:
    """Premium tier verification for Feature 20"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as premium/admin user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=PREMIUM_USER
        )
        if login_response.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_response.status_code} - {login_response.text[:200]}")
        print(f"Premium user login successful: {PREMIUM_USER['email']}")
    
    def test_bootstrap_premium_tier(self):
        """Bootstrap returns premium plan with unlimited limits"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text[:200]}"
        data = response.json()
        
        # Verify plan
        assert data.get("plan") == "premium", f"Expected plan=premium, got {data.get('plan')}"
        assert data.get("scope_label") == "Full unlimited access", f"Expected scope_label='Full unlimited access', got {data.get('scope_label')}"
        
        # Verify limits are unlimited (-1)
        limits = data.get("limits", {})
        assert limits.get("generate_word") == -1, f"Expected generate_word=-1 (unlimited), got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == -1, f"Expected quiz_attempt=-1 (unlimited), got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == -1, f"Expected save_word=-1 (unlimited), got {limits.get('save_word')}"
        
        print(f"PASS: Premium tier bootstrap - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
        print("PASS: Premium tier limits - all unlimited (-1)")
    
    def test_templates_premium_tier(self):
        """Templates returns premium plan recommendations"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "premium"
        
        # Premium should get boardroom-brief and negotiation-edge recommendations
        recommended = data.get("recommended_template_ids", [])
        assert "boardroom-brief" in recommended or "negotiation-edge" in recommended, \
            f"Premium tier should get boardroom-brief or negotiation-edge, got {recommended}"
        
        print(f"PASS: Premium tier templates - plan={data.get('plan')}, recommended={recommended}")
    
    def test_export_premium_tier(self):
        """Export returns premium plan data"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "payload"})
        assert response.status_code == 200, f"Export failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("plan") == "premium"
        assert data.get("scope_label") == "Full unlimited access"
        
        print(f"PASS: Premium tier export - plan={data.get('plan')}, scope_label={data.get('scope_label')}")
    
    def test_export_json_premium_tier(self):
        """Export JSON format works for premium tier"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "json"})
        assert response.status_code == 200, f"Export JSON failed: {response.status_code}"
        
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp.lower() or response.headers.get("content-type") == "application/json"
        
        print(f"PASS: Premium tier export JSON - content-type={response.headers.get('content-type')}")
    
    def test_export_csv_premium_tier(self):
        """Export CSV format works for premium tier"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "csv"})
        assert response.status_code == 200, f"Export CSV failed: {response.status_code}"
        
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type or "attachment" in response.headers.get("content-disposition", "").lower()
        
        print(f"PASS: Premium tier export CSV - content-type={content_type}")
    
    def test_daily_word_premium_tier(self):
        """Daily word generation works for premium tier"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/daily-word", json={
            "domain": "leadership",
            "difficulty": "advanced"
        })
        
        # Premium should always succeed (unlimited)
        assert response.status_code == 200, f"Daily word failed: {response.text[:200]}"
        data = response.json()
        
        assert "word" in data
        word = data["word"]
        assert "word_id" in word
        assert "word" in word
        assert "definition" in word
        
        print(f"PASS: Premium tier daily word - word={word.get('word')}, domain={word.get('domain')}")


class TestFeature20CoreFlowE2E:
    """End-to-end core flow tests for Feature 20"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as premium user for E2E tests"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=PREMIUM_USER
        )
        if login_response.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_response.status_code}")
        print("E2E test user login successful")
    
    def test_e2e_bootstrap_to_quiz_flow(self):
        """E2E: Bootstrap -> Get word -> Submit quiz"""
        # Step 1: Bootstrap
        bootstrap_response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert bootstrap_response.status_code == 200
        bootstrap_data = bootstrap_response.json()
        
        daily_word = bootstrap_data.get("daily_word", {})
        word_id = daily_word.get("word_id")
        quiz = daily_word.get("quiz", {})
        correct_answer = quiz.get("correct_answer", "test")
        
        assert word_id, "No word_id in bootstrap"
        
        # Step 2: Submit quiz
        quiz_response = self.session.post(f"{BASE_URL}/api/word-forge/quiz/submit", json={
            "word_id": word_id,
            "mode": "mcq",
            "answer": correct_answer
        })
        
        assert quiz_response.status_code in [200, 429]
        if quiz_response.status_code == 200:
            quiz_data = quiz_response.json()
            assert "is_correct" in quiz_data
            assert "score" in quiz_data
            print(f"PASS: E2E bootstrap->quiz - is_correct={quiz_data.get('is_correct')}, score={quiz_data.get('score')}")
        else:
            print("PASS: E2E bootstrap->quiz - rate limited")
    
    def test_e2e_template_apply_flow(self):
        """E2E: Get templates -> Apply template"""
        # Step 1: Get templates
        templates_response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert templates_response.status_code == 200
        templates = templates_response.json().get("templates", [])
        
        assert len(templates) > 0, "No templates available"
        template_id = templates[0].get("template_id")
        
        # Step 2: Apply template
        apply_response = self.session.post(f"{BASE_URL}/api/word-forge/templates/apply", json={
            "template_id": template_id
        })
        assert apply_response.status_code == 200
        apply_data = apply_response.json()
        
        assert apply_data.get("status") == "applied"
        print(f"PASS: E2E template apply - template_id={template_id}, status={apply_data.get('status')}")
    
    def test_e2e_recommendations_flow(self):
        """E2E: Get recommendations"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 200
        data = response.json()
        
        assert "recommendations" in data
        recommendations = data.get("recommendations", [])
        
        if recommendations:
            rec = recommendations[0]
            assert "recommendation_id" in rec
            assert "title" in rec
            assert "cta" in rec
            print(f"PASS: E2E recommendations - count={len(recommendations)}, first={rec.get('title')}")
        else:
            print("PASS: E2E recommendations - empty (user may have completed all)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
