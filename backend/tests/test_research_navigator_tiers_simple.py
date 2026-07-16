"""
Test Deep Research Navigator Tier Enforcement (Feature 3) - Simplified Version

Tests the tier enforcement system focusing on the usage endpoint and error responses.
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
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
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
async def test_invalid_guest_id_format():
    """Test 3: Invalid guest ID format returns 400 error."""
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
        
        print("✅ Test 3 PASSED: Invalid guest ID formats properly rejected")


@pytest.mark.asyncio
async def test_missing_fallback_user_id():
    """Test 4: Missing fallback_user_id returns 401 error."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BASE_URL}/research-navigator/usage")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        error_data = response.json()
        detail = error_data.get("detail", {})
        assert detail.get("error_code") == "research_nav_auth_required", f"Expected error_code 'research_nav_auth_required', got '{detail.get('error_code')}'"
        
        print("✅ Test 4 PASSED: Missing fallback_user_id returns 401")


@pytest.mark.asyncio
async def test_tier_limits_structure():
    """Test 5: Verify tier limits structure for all tiers."""
    guest_id = generate_guest_id()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/research-navigator/usage",
            params={"fallback_user_id": guest_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        tier_limits = data["tier_limits"]
        
        # Verify all required fields are present
        required_fields = ["runs_per_day", "max_sources", "export_formats"]
        for field in required_fields:
            assert field in tier_limits, f"Tier limits missing required field: {field}"
        
        # Verify free tier specific values
        assert tier_limits["runs_per_day"] == 5, "Free tier should have 5 runs per day"
        assert tier_limits["max_sources"] == 15, "Free tier should have 15 max sources"
        assert isinstance(tier_limits["export_formats"], list), "export_formats should be a list"
        assert "txt" in tier_limits["export_formats"], "Free tier should support txt export"
        
        print("✅ Test 5 PASSED: Tier limits structure verified")


if __name__ == "__main__":
    import asyncio
    
    print("=" * 80)
    print("Deep Research Navigator Tier Enforcement Tests (Simplified)")
    print("=" * 80)
    print()
    
    async def run_all_tests():
        try:
            await test_usage_endpoint_returns_tier_info()
            print()
            await test_bootstrap_includes_usage()
            print()
            await test_invalid_guest_id_format()
            print()
            await test_missing_fallback_user_id()
            print()
            await test_tier_limits_structure()
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
