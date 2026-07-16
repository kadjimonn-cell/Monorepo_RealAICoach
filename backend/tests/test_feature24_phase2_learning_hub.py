"""
Feature 24 Phase-2 Commercial UX Pass - AI Learning Hub Testing
Tests for onboarding checklist and weekly achievement loop payloads
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated session for free user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Free user login failed: {response.status_code} - {response.text[:200]}")
    
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated session for admin user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    
    return session


class TestHubDashboardPhase2Payloads:
    """Test hub-dashboard endpoint returns Phase-2 payloads"""
    
    def test_hub_dashboard_returns_onboarding_payload(self, free_user_session):
        """Verify hub-dashboard includes onboarding payload"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "onboarding" in data, "onboarding key missing from hub-dashboard response"
        
        onboarding = data["onboarding"]
        assert onboarding is not None, "onboarding payload is None"
        
        # Verify onboarding structure
        assert "version" in onboarding, "onboarding.version missing"
        assert onboarding["version"] == "phase2-commercial-onboarding-v1", f"Unexpected version: {onboarding['version']}"
        
        assert "total_steps" in onboarding, "onboarding.total_steps missing"
        assert isinstance(onboarding["total_steps"], int), "total_steps should be int"
        assert onboarding["total_steps"] == 5, f"Expected 5 steps, got {onboarding['total_steps']}"
        
        assert "completed_steps" in onboarding, "onboarding.completed_steps missing"
        assert isinstance(onboarding["completed_steps"], int), "completed_steps should be int"
        
        assert "completion_pct" in onboarding, "onboarding.completion_pct missing"
        assert isinstance(onboarding["completion_pct"], (int, float)), "completion_pct should be numeric"
        
        assert "steps" in onboarding, "onboarding.steps missing"
        assert isinstance(onboarding["steps"], list), "steps should be a list"
        assert len(onboarding["steps"]) == 5, f"Expected 5 steps, got {len(onboarding['steps'])}"
    
    def test_onboarding_steps_structure(self, free_user_session):
        """Verify each onboarding step has correct structure"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200
        
        data = response.json()
        steps = data.get("onboarding", {}).get("steps", [])
        
        expected_step_ids = [
            "enroll_first_course",
            "complete_first_module",
            "generate_career_sprint",
            "finish_daily_checkin",
            "claim_first_certificate"
        ]
        
        for idx, step in enumerate(steps):
            assert "step_id" in step, f"Step {idx} missing step_id"
            assert step["step_id"] == expected_step_ids[idx], f"Step {idx} has wrong step_id: {step['step_id']}"
            
            assert "title" in step, f"Step {idx} missing title"
            assert isinstance(step["title"], str), f"Step {idx} title should be string"
            
            assert "description" in step, f"Step {idx} missing description"
            assert isinstance(step["description"], str), f"Step {idx} description should be string"
            
            assert "completed" in step, f"Step {idx} missing completed"
            assert isinstance(step["completed"], bool), f"Step {idx} completed should be bool"
            
            assert "action" in step, f"Step {idx} missing action"
            action = step["action"]
            assert "kind" in action, f"Step {idx} action missing kind"
            assert "route" in action, f"Step {idx} action missing route"
            assert "cta_label" in action, f"Step {idx} action missing cta_label"
    
    def test_hub_dashboard_returns_weekly_achievement_loop(self, free_user_session):
        """Verify hub-dashboard includes weekly_achievement_loop payload"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "weekly_achievement_loop" in data, "weekly_achievement_loop key missing from hub-dashboard response"
        
        wal = data["weekly_achievement_loop"]
        assert wal is not None, "weekly_achievement_loop payload is None"
        
        # Verify weekly achievement loop structure
        assert "window" in wal, "weekly_achievement_loop.window missing"
        assert "start_day" in wal["window"], "window.start_day missing"
        assert "end_day" in wal["window"], "window.end_day missing"
        
        assert "xp" in wal, "weekly_achievement_loop.xp missing"
        assert "earned" in wal["xp"], "xp.earned missing"
        assert "goal" in wal["xp"], "xp.goal missing"
        
        assert "minutes" in wal, "weekly_achievement_loop.minutes missing"
        assert "earned" in wal["minutes"], "minutes.earned missing"
        assert "goal" in wal["minutes"], "minutes.goal missing"
        
        assert "missions" in wal, "weekly_achievement_loop.missions missing"
        assert "completed" in wal["missions"], "missions.completed missing"
        assert "total" in wal["missions"], "missions.total missing"
        assert "goal" in wal["missions"], "missions.goal missing"
    
    def test_weekly_achievement_loop_streak_badge(self, free_user_session):
        """Verify streak badge structure in weekly achievement loop"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200
        
        data = response.json()
        wal = data.get("weekly_achievement_loop", {})
        
        assert "streak_badge" in wal, "streak_badge missing from weekly_achievement_loop"
        badge = wal["streak_badge"]
        
        assert "tier" in badge, "streak_badge.tier missing"
        assert "label" in badge, "streak_badge.label missing"
        assert "description" in badge, "streak_badge.description missing"
        assert "style" in badge, "streak_badge.style missing"
        
        # Verify tier is valid
        valid_tiers = ["none", "starter", "rising", "champion", "legend"]
        assert badge["tier"] in valid_tiers, f"Invalid tier: {badge['tier']}"
    
    def test_weekly_achievement_loop_mission_cards(self, free_user_session):
        """Verify mission cards structure in weekly achievement loop"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200
        
        data = response.json()
        wal = data.get("weekly_achievement_loop", {})
        
        assert "mission_cards" in wal, "mission_cards missing from weekly_achievement_loop"
        cards = wal["mission_cards"]
        
        assert isinstance(cards, list), "mission_cards should be a list"
        assert len(cards) == 3, f"Expected 3 mission cards, got {len(cards)}"
        
        expected_card_ids = ["weekly_xp", "weekly_minutes", "weekly_missions"]
        
        for idx, card in enumerate(cards):
            assert "card_id" in card, f"Card {idx} missing card_id"
            assert card["card_id"] == expected_card_ids[idx], f"Card {idx} has wrong card_id: {card['card_id']}"
            
            assert "title" in card, f"Card {idx} missing title"
            assert "description" in card, f"Card {idx} missing description"
            assert "current" in card, f"Card {idx} missing current"
            assert "target" in card, f"Card {idx} missing target"
            assert "unit" in card, f"Card {idx} missing unit"
            assert "progress_pct" in card, f"Card {idx} missing progress_pct"
            assert "completed" in card, f"Card {idx} missing completed"
            assert "reward" in card, f"Card {idx} missing reward"
    
    def test_weekly_achievement_loop_completion_rewards(self, free_user_session):
        """Verify completion rewards structure in weekly achievement loop"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200
        
        data = response.json()
        wal = data.get("weekly_achievement_loop", {})
        
        assert "completion_rewards" in wal, "completion_rewards missing from weekly_achievement_loop"
        rewards = wal["completion_rewards"]
        
        assert isinstance(rewards, list), "completion_rewards should be a list"
        assert len(rewards) == 3, f"Expected 3 completion rewards, got {len(rewards)}"
        
        for idx, reward in enumerate(rewards):
            assert "reward_id" in reward, f"Reward {idx} missing reward_id"
            assert "title" in reward, f"Reward {idx} missing title"
            assert "description" in reward, f"Reward {idx} missing description"
            assert "status" in reward, f"Reward {idx} missing status"
            assert reward["status"] in ["locked", "unlocked"], f"Reward {idx} has invalid status: {reward['status']}"
    
    def test_weekly_achievement_loop_leaderboard_teaser(self, free_user_session):
        """Verify leaderboard teaser structure in weekly achievement loop"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200
        
        data = response.json()
        wal = data.get("weekly_achievement_loop", {})
        
        assert "leaderboard_teaser" in wal, "leaderboard_teaser missing from weekly_achievement_loop"
        teaser = wal["leaderboard_teaser"]
        
        assert "headline" in teaser, "leaderboard_teaser.headline missing"
        assert "entries" in teaser, "leaderboard_teaser.entries missing"
        assert "you" in teaser, "leaderboard_teaser.you missing"
        
        entries = teaser["entries"]
        assert isinstance(entries, list), "entries should be a list"
        
        # Verify at least one entry exists (current user fallback)
        assert len(entries) >= 1, "Expected at least 1 leaderboard entry"
        
        for idx, entry in enumerate(entries):
            assert "rank" in entry, f"Entry {idx} missing rank"
            assert "user_id" in entry, f"Entry {idx} missing user_id"
            assert "display_name" in entry, f"Entry {idx} missing display_name"
            assert "weekly_xp" in entry, f"Entry {idx} missing weekly_xp"
            assert "missions_completed" in entry, f"Entry {idx} missing missions_completed"
            assert "is_current_user" in entry, f"Entry {idx} missing is_current_user"
        
        # Verify "you" structure
        you = teaser["you"]
        assert "user_id" in you, "you.user_id missing"
        assert "weekly_xp" in you, "you.weekly_xp missing"
        assert "in_top_five" in you, "you.in_top_five missing"


class TestCoreTabsNoRegression:
    """Test that core tabs still load without regressions"""
    
    def test_courses_endpoint_works(self, free_user_session):
        """Verify /api/ai-learn/courses endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/courses")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "courses" in data, "courses key missing"
        assert isinstance(data["courses"], list), "courses should be a list"
    
    def test_my_learning_center_endpoint_works(self, free_user_session):
        """Verify /api/ai-learn/my-learning-center endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/my-learning-center")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "enrollments" in data, "enrollments key missing"
        assert isinstance(data["enrollments"], list), "enrollments should be a list"
    
    def test_habit_loop_summary_endpoint_works(self, free_user_session):
        """Verify /api/ai-learn/habit-loop/summary endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/habit-loop/summary")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Should have summary or missions
        assert "summary" in data or "missions" in data, "Expected summary or missions in response"
    
    def test_papers_latest_endpoint_works(self, free_user_session):
        """Verify /api/ai-learn/papers/latest endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/papers/latest")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "papers" in data, "papers key missing"
        assert isinstance(data["papers"], list), "papers should be a list"


class TestFreeUserAccess:
    """Test that free authenticated user can access AI Learning Hub"""
    
    def test_free_user_can_access_hub_dashboard(self, free_user_session):
        """Verify free user can access hub-dashboard without 403"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        
        assert response.status_code == 200, f"Free user should access hub-dashboard, got {response.status_code}"
        
        data = response.json()
        # Verify user is on free plan
        entitlements = data.get("entitlements", {})
        plan = entitlements.get("plan", "")
        assert plan == "free", f"Expected free plan, got {plan}"
    
    def test_free_user_can_access_courses(self, free_user_session):
        """Verify free user can access courses endpoint"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/courses")
        
        assert response.status_code == 200, f"Free user should access courses, got {response.status_code}"
    
    def test_free_user_can_access_learning_center(self, free_user_session):
        """Verify free user can access my-learning-center endpoint"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/my-learning-center")
        
        assert response.status_code == 200, f"Free user should access learning center, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
