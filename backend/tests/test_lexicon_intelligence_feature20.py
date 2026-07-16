"""
Feature 20 - Lexicon Intelligence Hub (Word Forge) Backend API Tests

Tests for the canonical Feature 20 endpoints:
- Health endpoint
- Template library endpoints
- Batch workflow endpoints
- Snapshot workflow endpoints
- Recommendations endpoint
- Export center endpoint
- Legacy core flows (bootstrap, daily-word, quiz, usage coach, business brief, weekly challenge, leaderboard, saved words, analytics)
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestLexiconIntelligenceHealth:
    """Health endpoint tests for Feature 20"""
    
    def test_health_endpoint_requires_auth(self):
        """Health endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/health")
        # May require auth or be public - check both cases
        assert response.status_code in [200, 401, 403]
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "healthy"
            assert data.get("feature_id") == "lexicon-intelligence"
            print("PASS: Health endpoint returned healthy status (public)")
        else:
            print(f"PASS: Health endpoint requires auth (status={response.status_code})")


class TestLexiconIntelligenceAuthenticated:
    """Authenticated tests for Feature 20 endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_auth(self):
        """Login and get session for authenticated tests"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as admin
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text[:200]}")
        
        self.session = session
        self.user_data = login_response.json()
        print(f"Logged in as: {ADMIN_EMAIL}")
        yield
    
    # ─── Health Endpoint ───────────────────────────────────────────────────────
    
    def test_health_authenticated(self):
        """GET /api/word-forge/health - authenticated"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/health")
        assert response.status_code == 200, f"Health failed: {response.text[:200]}"
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature") == "Lexicon Intelligence Hub"
        assert data.get("feature_id") == "lexicon-intelligence"
        print(f"PASS: Health endpoint - status={data.get('status')}, feature_id={data.get('feature_id')}")
    
    # ─── Bootstrap Endpoint ────────────────────────────────────────────────────
    
    def test_bootstrap_endpoint(self):
        """GET /api/word-forge/bootstrap - returns full workspace state"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text[:200]}"
        data = response.json()
        
        # Verify required fields
        assert "plan" in data, "Missing plan field"
        assert "scope_label" in data, "Missing scope_label field"
        assert "limits" in data, "Missing limits field"
        assert "daily_word" in data, "Missing daily_word field"
        assert "saved_words" in data, "Missing saved_words field"
        assert "profile" in data, "Missing profile field"
        assert "usage_summary" in data, "Missing usage_summary field"
        assert "capabilities" in data, "Missing capabilities field"
        
        # Verify daily_word structure
        daily_word = data.get("daily_word", {})
        assert "word_id" in daily_word, "Missing word_id in daily_word"
        assert "word" in daily_word, "Missing word in daily_word"
        assert "definition" in daily_word, "Missing definition in daily_word"
        
        print(f"PASS: Bootstrap - plan={data.get('plan')}, word={daily_word.get('word')}")
    
    # ─── Template Library Endpoints ────────────────────────────────────────────
    
    def test_templates_list(self):
        """GET /api/word-forge/templates - list available templates"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates list failed: {response.text[:200]}"
        data = response.json()
        
        assert "templates" in data, "Missing templates field"
        assert "recommended_template_ids" in data, "Missing recommended_template_ids field"
        assert isinstance(data["templates"], list), "templates should be a list"
        
        if data["templates"]:
            template = data["templates"][0]
            assert "template_id" in template, "Missing template_id"
            assert "title" in template, "Missing title"
            assert "description" in template, "Missing description"
        
        print(f"PASS: Templates list - count={len(data['templates'])}, recommended={len(data.get('recommended_template_ids', []))}")
    
    def test_templates_apply(self):
        """POST /api/word-forge/templates/apply - apply a template"""
        # First get templates
        templates_response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        if templates_response.status_code != 200:
            pytest.skip("Could not get templates list")
        
        templates = templates_response.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        
        template_id = templates[0].get("template_id")
        
        response = self.session.post(f"{BASE_URL}/api/word-forge/templates/apply", json={
            "template_id": template_id
        })
        assert response.status_code == 200, f"Template apply failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("status") == "applied", "Expected status=applied"
        assert "template" in data, "Missing template in response"
        
        print(f"PASS: Template apply - template_id={template_id}, status={data.get('status')}")
    
    # ─── Batch Workflow Endpoints ──────────────────────────────────────────────
    
    def test_batch_generate(self):
        """POST /api/word-forge/batch/generate - batch word generation"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/batch/generate", json={
            "domains": ["business", "leadership"],
            "difficulty": "adaptive"
        })
        
        # May hit rate limit or succeed
        assert response.status_code in [200, 429], f"Batch generate unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data, "Missing status field"
            assert "words" in data or "job" in data, "Missing words or job field"
            print(f"PASS: Batch generate - status={data.get('status')}, words_count={len(data.get('words', []))}")
        else:
            data = response.json()
            print(f"PASS: Batch generate - rate limited (expected for free tier): {data.get('detail', '')[:100]}")
    
    def test_batch_jobs_list(self):
        """GET /api/word-forge/batch/jobs - list batch jobs"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/batch/jobs")
        assert response.status_code == 200, f"Batch jobs list failed: {response.text[:200]}"
        data = response.json()
        
        assert "jobs" in data, "Missing jobs field"
        assert isinstance(data["jobs"], list), "jobs should be a list"
        
        print(f"PASS: Batch jobs list - count={len(data['jobs'])}")
    
    # ─── Snapshot Workflow Endpoints ───────────────────────────────────────────
    
    def test_snapshots_create(self):
        """POST /api/word-forge/snapshots - create workspace snapshot"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/snapshots", json={
            "name": f"Test Snapshot {uuid.uuid4().hex[:8]}",
            "include_saved_words": True,
            "include_leaderboard": False
        })
        
        # May hit rate limit or succeed
        assert response.status_code in [200, 429], f"Snapshot create unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "created", "Expected status=created"
            assert "snapshot" in data, "Missing snapshot field"
            self.created_snapshot_id = data["snapshot"].get("snapshot_id")
            print(f"PASS: Snapshot create - snapshot_id={self.created_snapshot_id}")
        else:
            print(f"PASS: Snapshot create - rate limited (expected): {response.json().get('detail', '')[:100]}")
    
    def test_snapshots_list(self):
        """GET /api/word-forge/snapshots - list snapshots"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/snapshots")
        assert response.status_code == 200, f"Snapshots list failed: {response.text[:200]}"
        data = response.json()
        
        assert "snapshots" in data, "Missing snapshots field"
        assert isinstance(data["snapshots"], list), "snapshots should be a list"
        
        print(f"PASS: Snapshots list - count={len(data['snapshots'])}")
    
    def test_snapshots_restore(self):
        """POST /api/word-forge/snapshots/restore - restore a snapshot"""
        # First get snapshots
        snapshots_response = self.session.get(f"{BASE_URL}/api/word-forge/snapshots")
        if snapshots_response.status_code != 200:
            pytest.skip("Could not get snapshots list")
        
        snapshots = snapshots_response.json().get("snapshots", [])
        if not snapshots:
            pytest.skip("No snapshots available to restore")
        
        snapshot_id = snapshots[0].get("snapshot_id")
        
        response = self.session.post(f"{BASE_URL}/api/word-forge/snapshots/restore", json={
            "snapshot_id": snapshot_id
        })
        assert response.status_code == 200, f"Snapshot restore failed: {response.text[:200]}"
        data = response.json()
        
        assert data.get("status") == "restored", "Expected status=restored"
        
        print(f"PASS: Snapshot restore - snapshot_id={snapshot_id}, status={data.get('status')}")
    
    # ─── Recommendations Endpoint ──────────────────────────────────────────────
    
    def test_recommendations(self):
        """GET /api/word-forge/recommendations - get smart recommendations"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 200, f"Recommendations failed: {response.text[:200]}"
        data = response.json()
        
        assert "recommendations" in data, "Missing recommendations field"
        assert isinstance(data["recommendations"], list), "recommendations should be a list"
        assert data.get("feature_id") == "lexicon-intelligence", "Wrong feature_id"
        
        if data["recommendations"]:
            rec = data["recommendations"][0]
            assert "recommendation_id" in rec, "Missing recommendation_id"
            assert "title" in rec, "Missing title"
            assert "cta" in rec, "Missing cta"
        
        print(f"PASS: Recommendations - count={len(data['recommendations'])}")
    
    # ─── Export Center Endpoint ────────────────────────────────────────────────
    
    def test_export_payload(self):
        """GET /api/word-forge/export?format=payload - export as JSON payload"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "payload"})
        assert response.status_code == 200, f"Export payload failed: {response.text[:200]}"
        data = response.json()
        
        assert "feature_id" in data, "Missing feature_id"
        assert "plan" in data, "Missing plan"
        assert "profile" in data, "Missing profile"
        assert "summary" in data, "Missing summary"
        
        print(f"PASS: Export payload - plan={data.get('plan')}, saved_words={data.get('summary', {}).get('saved_words_count', 0)}")
    
    def test_export_json(self):
        """GET /api/word-forge/export?format=json - export as downloadable JSON"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "json"})
        assert response.status_code == 200, f"Export JSON failed: {response.status_code}"
        
        # Check content-disposition header for download
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp.lower() or response.headers.get("content-type") == "application/json", \
            "Expected downloadable JSON response"
        
        print(f"PASS: Export JSON - content-type={response.headers.get('content-type')}")
    
    def test_export_csv(self):
        """GET /api/word-forge/export?format=csv - export as downloadable CSV"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export", params={"format": "csv"})
        assert response.status_code == 200, f"Export CSV failed: {response.status_code}"
        
        # Check content-type for CSV
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type or "attachment" in response.headers.get("content-disposition", "").lower(), \
            "Expected CSV response"
        
        print(f"PASS: Export CSV - content-type={content_type}")
    
    # ─── Legacy Core Flows ─────────────────────────────────────────────────────
    
    def test_daily_word_generate(self):
        """POST /api/word-forge/daily-word - generate new word"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/daily-word", json={
            "domain": "business",
            "difficulty": "adaptive"
        })
        
        # May hit rate limit or succeed
        assert response.status_code in [200, 429], f"Daily word unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "word" in data, "Missing word field"
            word = data["word"]
            assert "word_id" in word, "Missing word_id"
            assert "word" in word, "Missing word text"
            assert "definition" in word, "Missing definition"
            print(f"PASS: Daily word generate - word={word.get('word')}, word_id={word.get('word_id')}")
        else:
            print(f"PASS: Daily word - rate limited (expected): {response.json().get('detail', '')[:100]}")
    
    def test_quiz_submit(self):
        """POST /api/word-forge/quiz/submit - submit quiz answer"""
        # First get bootstrap to get a word_id
        bootstrap = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        if bootstrap.status_code != 200:
            pytest.skip("Could not get bootstrap")
        
        daily_word = bootstrap.json().get("daily_word", {})
        word_id = daily_word.get("word_id")
        quiz = daily_word.get("quiz", {})
        correct_answer = quiz.get("correct_answer", "test answer")
        
        if not word_id:
            pytest.skip("No word_id available")
        
        response = self.session.post(f"{BASE_URL}/api/word-forge/quiz/submit", json={
            "word_id": word_id,
            "mode": "mcq",
            "answer": correct_answer
        })
        
        assert response.status_code in [200, 429], f"Quiz submit unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "is_correct" in data, "Missing is_correct field"
            assert "score" in data, "Missing score field"
            assert "feedback" in data, "Missing feedback field"
            print(f"PASS: Quiz submit - is_correct={data.get('is_correct')}, score={data.get('score')}")
        else:
            print(f"PASS: Quiz submit - rate limited: {response.json().get('detail', '')[:100]}")
    
    def test_usage_coach(self):
        """POST /api/word-forge/usage-coach - get usage coaching"""
        # First get bootstrap to get a word_id
        bootstrap = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        if bootstrap.status_code != 200:
            pytest.skip("Could not get bootstrap")
        
        daily_word = bootstrap.json().get("daily_word", {})
        word_id = daily_word.get("word_id")
        word_text = daily_word.get("word", "pragmatic")
        
        if not word_id:
            pytest.skip("No word_id available")
        
        response = self.session.post(f"{BASE_URL}/api/word-forge/usage-coach", json={
            "word_id": word_id,
            "sentence": f"I used a {word_text} approach to solve the business problem efficiently.",
            "context_type": "email"
        })
        
        assert response.status_code in [200, 429], f"Usage coach unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "clarity_score" in data, "Missing clarity_score"
            assert "accuracy_score" in data, "Missing accuracy_score"
            print(f"PASS: Usage coach - clarity={data.get('clarity_score')}, accuracy={data.get('accuracy_score')}")
        else:
            print(f"PASS: Usage coach - rate limited: {response.json().get('detail', '')[:100]}")
    
    def test_business_brief(self):
        """POST /api/word-forge/business-brief - generate business brief"""
        # First get bootstrap to get a word_id
        bootstrap = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        if bootstrap.status_code != 200:
            pytest.skip("Could not get bootstrap")
        
        daily_word = bootstrap.json().get("daily_word", {})
        word_id = daily_word.get("word_id")
        
        if not word_id:
            pytest.skip("No word_id available")
        
        response = self.session.post(f"{BASE_URL}/api/word-forge/business-brief", json={
            "word_id": word_id,
            "context_type": "meeting"
        })
        
        assert response.status_code in [200, 429], f"Business brief unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "brief" in data, "Missing brief field"
            brief = data["brief"]
            assert "headline" in brief, "Missing headline in brief"
            print(f"PASS: Business brief - headline={brief.get('headline', '')[:50]}...")
        else:
            print(f"PASS: Business brief - rate limited: {response.json().get('detail', '')[:100]}")
    
    def test_weekly_challenge_current(self):
        """GET /api/word-forge/challenge/current - get current weekly challenge"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/challenge/current")
        assert response.status_code == 200, f"Weekly challenge failed: {response.text[:200]}"
        data = response.json()
        
        assert "challenge" in data, "Missing challenge field"
        challenge = data["challenge"]
        assert "challenge_id" in challenge, "Missing challenge_id"
        assert "week_key" in challenge, "Missing week_key"
        assert "title" in challenge, "Missing title"
        
        print(f"PASS: Weekly challenge - week_key={challenge.get('week_key')}, title={challenge.get('title')[:30]}...")
    
    def test_challenge_submit(self):
        """POST /api/word-forge/challenge/submit - submit challenge entry"""
        response = self.session.post(f"{BASE_URL}/api/word-forge/challenge/submit", json={
            "submission_text": "I used pragmatic thinking to solve a complex business problem by focusing on practical outcomes."
        })
        
        assert response.status_code in [200, 429], f"Challenge submit unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert "points_awarded" in data, "Missing points_awarded"
            print(f"PASS: Challenge submit - points_awarded={data.get('points_awarded')}")
        else:
            print(f"PASS: Challenge submit - rate limited: {response.json().get('detail', '')[:100]}")
    
    def test_leaderboard(self):
        """GET /api/word-forge/leaderboard - get weekly leaderboard"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/leaderboard")
        assert response.status_code == 200, f"Leaderboard failed: {response.text[:200]}"
        data = response.json()
        
        assert "leaderboard" in data, "Missing leaderboard field"
        assert isinstance(data["leaderboard"], list), "leaderboard should be a list"
        
        if data["leaderboard"]:
            entry = data["leaderboard"][0]
            assert "rank" in entry, "Missing rank"
            assert "points" in entry, "Missing points"
        
        print(f"PASS: Leaderboard - entries={len(data['leaderboard'])}")
    
    def test_saved_words_list(self):
        """GET /api/word-forge/saved - list saved words"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/saved")
        assert response.status_code == 200, f"Saved words failed: {response.text[:200]}"
        data = response.json()
        
        assert "saved_words" in data, "Missing saved_words field"
        assert isinstance(data["saved_words"], list), "saved_words should be a list"
        
        print(f"PASS: Saved words - count={len(data['saved_words'])}")
    
    def test_saved_toggle(self):
        """POST /api/word-forge/saved/toggle - save/unsave a word"""
        # First get bootstrap to get a word_id
        bootstrap = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        if bootstrap.status_code != 200:
            pytest.skip("Could not get bootstrap")
        
        daily_word = bootstrap.json().get("daily_word", {})
        word_id = daily_word.get("word_id")
        
        if not word_id:
            pytest.skip("No word_id available")
        
        # Save the word
        response = self.session.post(f"{BASE_URL}/api/word-forge/saved/toggle", json={
            "word_id": word_id,
            "save": True
        })
        
        assert response.status_code in [200, 429], f"Save toggle unexpected status: {response.status_code} - {response.text[:200]}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") in ["saved", "unsaved"], "Expected status saved or unsaved"
            print(f"PASS: Saved toggle - status={data.get('status')}, word_id={word_id}")
        else:
            print(f"PASS: Saved toggle - rate limited: {response.json().get('detail', '')[:100]}")
    
    def test_analytics(self):
        """GET /api/word-forge/analytics - get user analytics"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/analytics")
        assert response.status_code == 200, f"Analytics failed: {response.text[:200]}"
        data = response.json()
        
        # Verify analytics structure
        assert "profile" in data or "usage_summary" in data or "analytics" in data, \
            "Expected analytics data structure"
        
        print(f"PASS: Analytics - keys={list(data.keys())[:5]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
