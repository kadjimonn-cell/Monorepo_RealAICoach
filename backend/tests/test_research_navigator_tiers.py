"""
Test Deep Research Navigator Tier Enforcement (Feature 3)

Tests the tier enforcement system for the Deep Research Navigator feature
to ensure proper quota management across Free, Basic, and Premium tiers.
"""

import httpx
import pytest
from datetime import datetime


# Base URL from environment
BASE_URL = "https://coach-web-preview.preview.emergentagent.com/api"

# Test credentials
GUEST_USER_PREFIX = "user_test_"


def generate_guest_id():
    """Generate a unique guest user ID for testing."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{GUEST_USER_PREFIX}{timestamp}"


@pytest.mark.asyncio
async def test_usage_endpoint_returns_tier_info():
    """Test 1: Usage endpoint returns correct tier information for guest users."""
    guest_id = generate_guest_id()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/research-navigator/usage",
            params={"fallback_user_id": guest_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "usage" in data, "Response missing 'usage' field"
        assert "tier_limits" in data, "Response missing 'tier_limits' field"
        
        usage = data["usage"]
        tier_limits = data["tier_limits"]
        
        # Verify usage fields
        assert "can_run" in usage, "Usage missing 'can_run' field"
        assert "runs_used_today" in usage, "Usage missing 'runs_used_today' field"
        assert "daily_limit" in usage, "Usage missing 'daily_limit' field"
        assert "tier" in usage, "Usage missing 'tier' field"
        assert "limit_reached" in usage, "Usage missing 'limit_reached' field"
        
        # Verify guest user defaults to free tier
        assert usage["tier"] == "free", f"Expected tier 'free', got '{usage['tier']}'"
        assert usage["daily_limit"] == 5, f"Expected daily_limit 5, got {usage['daily_limit']}"
        assert usage["can_run"] is True, "New guest user should be able to run research"
        assert usage["runs_used_today"] == 0, "New guest user should have 0 runs used"
        assert usage["limit_reached"] is False, "New guest user should not have limit reached"
        
        # Verify tier limits
        assert tier_limits["runs_per_day"] == 5, f"Expected runs_per_day 5, got {tier_limits['runs_per_day']}"
        assert tier_limits["max_sources"] == 15, f"Expected max_sources 15, got {tier_limits['max_sources']}"
        assert tier_limits["export_formats"] == ["txt"], f"Expected export_formats ['txt'], got {tier_limits['export_formats']}"
        
        print(f"✅ Test 1 PASSED: Usage endpoint returns correct tier info for guest user {guest_id}")


@pytest.mark.asyncio
async def test_bootstrap_includes_usage():
    """Test 2: Bootstrap endpoint includes usage field in response."""
    guest_id = generate_guest_id()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/research-navigator/bootstrap",
            params={"fallback_user_id": guest_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "usage" in data, "Bootstrap response missing 'usage' field"
        assert "owner_id" in data, "Bootstrap response missing 'owner_id' field"
        assert "projects" in data, "Bootstrap response missing 'projects' field"
        assert "insight_notes" in data, "Bootstrap response missing 'insight_notes' field"
        assert "stats" in data, "Bootstrap response missing 'stats' field"
        
        usage = data["usage"]
        
        # Verify usage fields
        assert "can_run" in usage, "Usage missing 'can_run' field"
        assert "tier" in usage, "Usage missing 'tier' field"
        assert usage["tier"] == "free", f"Expected tier 'free', got '{usage['tier']}'"
        
        print(f"✅ Test 2 PASSED: Bootstrap includes usage data for guest user {guest_id}")


@pytest.mark.asyncio
async def test_free_tier_limit_enforcement():
    """Test 3: Free tier limit enforced at 5 runs/day."""
    guest_id = generate_guest_id()
    
    # CSRF header required for POST requests
    headers = {"X-Requested-With": "XMLHttpRequest"}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Create a test project
        create_response = await client.post(
            f"{BASE_URL}/research-navigator/projects",
            json={
                "title": "Tier Enforcement Test Project",
                "topic": "Testing free tier limits",
                "fallback_user_id": guest_id
            },
            headers=headers
        )
        
        assert create_response.status_code == 200, f"Failed to create project: {create_response.status_code}: {create_response.text}"
        
        project_data = create_response.json()
        project_id = project_data["project"]["project_id"]
        
        print(f"Created test project: {project_id}")
        
        # Step 2: Run research 5 times (should all succeed)
        for i in range(1, 6):
            # Check usage before run
            usage_response = await client.get(
                f"{BASE_URL}/research-navigator/usage",
                params={"fallback_user_id": guest_id}
            )
            usage_data = usage_response.json()
            print(f"Before run {i}: runs_used_today={usage_data['usage']['runs_used_today']}, can_run={usage_data['usage']['can_run']}")
            
            # Run research
            run_response = await client.post(
                f"{BASE_URL}/research-navigator/projects/{project_id}/runs",
                json={
                    "query": f"Test query {i} for tier enforcement",
                    "fallback_user_id": guest_id,
                    "idempotency_key": f"test_tier_enforcement_{guest_id}_{i}"
                },
                headers=headers
            )
            
            assert run_response.status_code == 200, f"Run {i} failed: {run_response.status_code}: {run_response.text}"
            print(f"✅ Run {i}/5 succeeded")
            
            # Check usage after run
            usage_response = await client.get(
                f"{BASE_URL}/research-navigator/usage",
                params={"fallback_user_id": guest_id}
            )
            usage_data = usage_response.json()
            assert usage_data["usage"]["runs_used_today"] == i, f"Expected {i} runs used, got {usage_data['usage']['runs_used_today']}"
            print(f"After run {i}: runs_used_today={usage_data['usage']['runs_used_today']}")
        
        # Step 3: Check usage after 5 runs
        usage_response = await client.get(
            f"{BASE_URL}/research-navigator/usage",
            params={"fallback_user_id": guest_id}
        )
        usage_data = usage_response.json()
        assert usage_data["usage"]["runs_used_today"] == 5, f"Expected 5 runs used, got {usage_data['usage']['runs_used_today']}"
        assert usage_data["usage"]["can_run"] is False, "After 5 runs, can_run should be False"
        assert usage_data["usage"]["limit_reached"] is True, "After 5 runs, limit_reached should be True"
        print(f"After 5 runs: limit_reached={usage_data['usage']['limit_reached']}, can_run={usage_data['usage']['can_run']}")
        
        # Step 4: Attempt 6th run (should fail with 403)
        run_response = await client.post(
            f"{BASE_URL}/research-navigator/projects/{project_id}/runs",
            json={
                "query": "Test query 6 - should fail",
                "fallback_user_id": guest_id,
                "idempotency_key": f"test_tier_enforcement_{guest_id}_6"
            },
            headers=headers
        )
        
        assert run_response.status_code == 403, f"Expected 403 Forbidden, got {run_response.status_code}"
        
        error_data = run_response.json()
        detail = error_data.get("detail", {})
        
        # Verify error response structure
        assert "error_code" in detail, "Error response missing 'error_code'"
        assert detail["error_code"] == "research_nav_limit_reached", f"Expected error_code 'research_nav_limit_reached', got '{detail['error_code']}'"
        
        assert "message" in detail, "Error response missing 'message'"
        assert "5/day" in detail["message"], f"Error message should mention '5/day': {detail['message']}"
        assert "free tier" in detail["message"].lower(), f"Error message should mention 'free tier': {detail['message']}"
        assert "Upgrade" in detail["message"], f"Error message should mention 'Upgrade': {detail['message']}"
        
        assert "upgrade_prompt" in detail, "Error response missing 'upgrade_prompt'"
        assert detail["upgrade_prompt"] is True, "upgrade_prompt should be True"
        
        assert "current_tier" in detail, "Error response missing 'current_tier'"
        assert detail["current_tier"] == "free", f"Expected current_tier 'free', got '{detail['current_tier']}'"
        
        assert "runs_used_today" in detail, "Error response missing 'runs_used_today'"
        assert detail["runs_used_today"] == 5, f"Expected runs_used_today 5, got {detail['runs_used_today']}"
        
        assert "daily_limit" in detail, "Error response missing 'daily_limit'"
        assert detail["daily_limit"] == 5, f"Expected daily_limit 5, got {detail['daily_limit']}"
        
        print("✅ Test 3 PASSED: Free tier limit enforced at 5 runs/day")
        print(f"   Error response: {detail}")


@pytest.mark.asyncio
async def test_invalid_guest_id_format():
    """Test 4: Invalid guest ID format returns 400 error."""
    invalid_ids = [
        "short",  # Too short
        "user_abc",  # Too short after prefix
        "invalid_format_123456789012",  # Wrong prefix
        "",  # Empty
    ]
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for invalid_id in invalid_ids:
            response = await client.get(
                f"{BASE_URL}/research-navigator/usage",
                params={"fallback_user_id": invalid_id}
            )
            
            if invalid_id == "":
                # Empty ID should return 401 (auth required)
                assert response.status_code == 401, f"Expected 401 for empty ID, got {response.status_code}"
            else:
                # Invalid format should return 400
                assert response.status_code == 400, f"Expected 400 for invalid ID '{invalid_id}', got {response.status_code}"
                
                error_data = response.json()
                detail = error_data.get("detail", {})
                assert detail.get("error_code") == "research_nav_invalid_guest_id", f"Expected error_code 'research_nav_invalid_guest_id', got '{detail.get('error_code')}'"
        
        print("✅ Test 4 PASSED: Invalid guest ID formats properly rejected")


@pytest.mark.asyncio
async def test_missing_fallback_user_id():
    """Test 5: Missing fallback_user_id returns 401 error."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BASE_URL}/research-navigator/usage")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        error_data = response.json()
        detail = error_data.get("detail", {})
        assert detail.get("error_code") == "research_nav_auth_required", f"Expected error_code 'research_nav_auth_required', got '{detail.get('error_code')}'"
        
        print("✅ Test 5 PASSED: Missing fallback_user_id returns 401")


if __name__ == "__main__":
    import asyncio
    
    print("=" * 80)
    print("Deep Research Navigator Tier Enforcement Tests")
    print("=" * 80)
    print()
    
    async def run_all_tests():
        try:
            await test_usage_endpoint_returns_tier_info()
            print()
            await test_bootstrap_includes_usage()
            print()
            await test_free_tier_limit_enforcement()
            print()
            await test_invalid_guest_id_format()
            print()
            await test_missing_fallback_user_id()
            print()
            print("=" * 80)
            print("✅ ALL TESTS PASSED")
            print("=" * 80)
        except AssertionError as e:
            print()
            print("=" * 80)
            print(f"❌ TEST FAILED: {e}")
            print("=" * 80)
            raise
        except Exception as e:
            print()
            print("=" * 80)
            print(f"❌ TEST ERROR: {e}")
            print("=" * 80)
            raise
    
    asyncio.run(run_all_tests())
