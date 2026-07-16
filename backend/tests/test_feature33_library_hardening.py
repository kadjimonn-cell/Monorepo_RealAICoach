"""
Feature 33 Library Hardening Tests
Tests for:
- Library search works for Basic/Premium, gated for Free
- Bookmark endpoints enforce actor scope (no cross-user access)
- Export endpoint works for entitled users, blocks free users
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"

# Premium user from credentials
PREMIUM_EMAIL = "googleiap.prod.retest.80ea42d3@gmail.com"
# Note: Premium user may not have password login, will test with admin as premium-equivalent


class TestFeature33LibraryAccess:
    """Test library access control by subscription tier"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
        return session

    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Free user login failed: {resp.status_code} - {resp.text[:200]}")
        return session

    @pytest.fixture(scope="class")
    def basic_session(self):
        """Login as basic user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Basic user login failed: {resp.status_code} - {resp.text[:200]}")
        return session

    def test_library_search_admin_access(self, admin_session):
        """Admin (premium-equivalent) should access library"""
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=5")
        assert resp.status_code == 200, f"Admin library access failed: {resp.status_code} - {resp.text[:300]}"
        data = resp.json()
        assert "items" in data, "Response should contain items"
        assert "total" in data, "Response should contain total"
        assert "page" in data, "Response should contain page"
        assert "total_pages" in data, "Response should contain total_pages"
        print(f"Admin library access: {data.get('total', 0)} total items, page {data.get('page')}/{data.get('total_pages')}")

    def test_library_search_basic_access(self, basic_session):
        """Basic user should access library"""
        resp = basic_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=5")
        assert resp.status_code == 200, f"Basic user library access failed: {resp.status_code} - {resp.text[:300]}"
        data = resp.json()
        assert "items" in data, "Response should contain items"
        print(f"Basic user library access: {data.get('total', 0)} total items")

    def test_library_search_free_user_limited_allowed(self, free_session):
        """POLICY 2026-06.v3: free users can search the library (limited access)"""
        resp = free_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=5")
        assert resp.status_code == 200, f"Free user should get limited access 200, got {resp.status_code}"
        print("Free user has limited library access")

    def test_library_search_unauthenticated_blocked(self):
        """Unauthenticated request should be blocked with 401"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/content/library?page=1&per_page=5")
        assert resp.status_code == 401, f"Unauthenticated should get 401, got {resp.status_code}"
        print("Unauthenticated library access correctly blocked with 401")


class TestFeature33BookmarkSecurity:
    """Test bookmark endpoints enforce actor scope"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code}")
        # Get user_id from /me
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        if me_resp.status_code == 200:
            session.user_id = me_resp.json().get("user_id", "")
        else:
            session.user_id = ""
        return session

    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Free user login failed: {resp.status_code}")
        # Get user_id from /me
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        if me_resp.status_code == 200:
            session.user_id = me_resp.json().get("user_id", "")
        else:
            session.user_id = ""
        return session

    def test_bookmark_toggle_own_user(self, admin_session):
        """User can toggle bookmark for their own user_id"""
        if not admin_session.user_id:
            pytest.skip("Could not get admin user_id")
        
        resp = admin_session.post(f"{BASE_URL}/api/content/bookmarks/toggle", json={
            "user_id": admin_session.user_id,
            "content_id": "test_content_bookmark_toggle",
            "title": "Test Bookmark"
        })
        assert resp.status_code == 200, f"Bookmark toggle failed: {resp.status_code} - {resp.text[:200]}"
        data = resp.json()
        assert "bookmarked" in data, "Response should contain bookmarked status"
        assert "content_id" in data, "Response should contain content_id"
        print(f"Bookmark toggle successful: bookmarked={data.get('bookmarked')}")

    def test_bookmark_toggle_cross_user_blocked(self, free_session, admin_session):
        """Non-admin user cannot toggle bookmark for another user_id"""
        if not admin_session.user_id or not free_session.user_id:
            pytest.skip("Could not get user_ids")
        
        # Free user tries to toggle bookmark for admin's user_id
        resp = free_session.post(f"{BASE_URL}/api/content/bookmarks/toggle", json={
            "user_id": admin_session.user_id,  # Trying to access admin's bookmarks
            "content_id": "test_cross_user_attack",
            "title": "Cross User Attack"
        })
        assert resp.status_code == 403, f"Cross-user bookmark should be blocked with 403, got {resp.status_code}"
        print("Cross-user bookmark toggle correctly blocked with 403")

    def test_get_bookmarks_own_user(self, admin_session):
        """User can get their own bookmarks"""
        if not admin_session.user_id:
            pytest.skip("Could not get admin user_id")
        
        resp = admin_session.get(f"{BASE_URL}/api/content/bookmarks/{admin_session.user_id}")
        assert resp.status_code == 200, f"Get bookmarks failed: {resp.status_code} - {resp.text[:200]}"
        data = resp.json()
        assert "bookmarks" in data, "Response should contain bookmarks"
        assert "count" in data, "Response should contain count"
        print(f"Get bookmarks successful: {data.get('count')} bookmarks")

    def test_get_bookmarks_cross_user_blocked(self, free_session, admin_session):
        """Non-admin user cannot get another user's bookmarks"""
        if not admin_session.user_id:
            pytest.skip("Could not get admin user_id")
        
        # Free user tries to get admin's bookmarks
        resp = free_session.get(f"{BASE_URL}/api/content/bookmarks/{admin_session.user_id}")
        assert resp.status_code == 403, f"Cross-user bookmark read should be blocked with 403, got {resp.status_code}"
        print("Cross-user bookmark read correctly blocked with 403")


class TestFeature33ExportEndpoint:
    """Test export endpoint access control"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code}")
        return session

    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Free user login failed: {resp.status_code}")
        return session

    def test_export_library_admin_txt(self, admin_session):
        """Admin can export library as TXT"""
        test_items = [
            {"title": "Test Item 1", "type": "article", "category": "productivity", "url": "https://example.com/1", "added_date": "2026-01-01"},
            {"title": "Test Item 2", "type": "guide", "category": "health", "url": "https://example.com/2", "added_date": "2026-01-02"}
        ]
        resp = admin_session.post(f"{BASE_URL}/api/content/library/export", json={
            "items": test_items,
            "format": "txt"
        })
        assert resp.status_code == 200, f"Export TXT failed: {resp.status_code} - {resp.text[:200]}"
        assert "text/plain" in resp.headers.get("Content-Type", ""), "Should return text/plain"
        assert "Content-Disposition" in resp.headers, "Should have Content-Disposition header"
        print(f"Export TXT successful, content length: {len(resp.content)} bytes")

    def test_export_library_admin_csv(self, admin_session):
        """Admin can export library as CSV"""
        test_items = [
            {"title": "Test Item 1", "type": "article", "category": "productivity", "url": "https://example.com/1", "added_date": "2026-01-01"}
        ]
        resp = admin_session.post(f"{BASE_URL}/api/content/library/export", json={
            "items": test_items,
            "format": "csv"
        })
        assert resp.status_code == 200, f"Export CSV failed: {resp.status_code} - {resp.text[:200]}"
        assert "text/csv" in resp.headers.get("Content-Type", ""), "Should return text/csv"
        print(f"Export CSV successful, content length: {len(resp.content)} bytes")

    def test_export_library_free_user_limited_allowed(self, free_session):
        """POLICY 2026-06.v3: free users get limited (metered) library export access"""
        test_items = [
            {"title": "Test Item", "type": "article", "category": "productivity", "url": "https://example.com/1", "added_date": "2026-01-01"}
        ]
        resp = free_session.post(f"{BASE_URL}/api/content/library/export", json={
            "items": test_items,
            "format": "txt"
        })
        assert resp.status_code in [200, 429], f"Free user export should be limited-allowed (200) or metered (429), got {resp.status_code}"
        print(f"Free user export limited-allowed: {resp.status_code}")

    def test_export_library_unauthenticated_blocked(self):
        """Unauthenticated request should be blocked with 401"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        test_items = [{"title": "Test", "type": "article", "category": "test", "url": "https://example.com", "added_date": "2026-01-01"}]
        resp = session.post(f"{BASE_URL}/api/content/library/export", json={
            "items": test_items,
            "format": "txt"
        })
        assert resp.status_code == 401, f"Unauthenticated export should get 401, got {resp.status_code}"
        print("Unauthenticated export correctly blocked with 401")


class TestFeature33LibraryPagination:
    """Test library pagination and filter response validity"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code != 200:
            pytest.skip(f"Admin login failed: {resp.status_code}")
        # Get user_id
        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        if me_resp.status_code == 200:
            session.user_id = me_resp.json().get("user_id", "")
        else:
            session.user_id = ""
        return session

    def test_library_pagination_valid_response(self, admin_session):
        """Library pagination response should be valid and non-empty for entitled users"""
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=12")
        assert resp.status_code == 200
        data = resp.json()
        
        # Validate response structure
        assert isinstance(data.get("items"), list), "items should be a list"
        assert isinstance(data.get("total"), int), "total should be an integer"
        assert isinstance(data.get("page"), int), "page should be an integer"
        assert isinstance(data.get("per_page"), int), "per_page should be an integer"
        assert isinstance(data.get("total_pages"), int), "total_pages should be an integer"
        assert isinstance(data.get("categories"), list), "categories should be a list"
        assert isinstance(data.get("types"), list), "types should be a list"
        
        # Validate pagination math
        assert data["page"] == 1, "Page should be 1"
        assert data["per_page"] == 12, "per_page should be 12"
        if data["total"] > 0:
            expected_pages = (data["total"] + 11) // 12
            assert data["total_pages"] == expected_pages, f"total_pages calculation mismatch: {data['total_pages']} vs expected {expected_pages}"
        
        print(f"Pagination valid: {data['total']} items, {data['total_pages']} pages, {len(data['categories'])} categories, {len(data['types'])} types")

    def test_library_filter_by_category(self, admin_session):
        """Library filter by category should work"""
        # First get available categories
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=5")
        assert resp.status_code == 200
        data = resp.json()
        categories = data.get("categories", [])
        
        if not categories:
            pytest.skip("No categories available to test filter")
        
        # Filter by first category
        test_category = categories[0]
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=12&category={test_category}")
        assert resp.status_code == 200
        filtered_data = resp.json()
        
        # All items should have the filtered category
        for item in filtered_data.get("items", []):
            assert item.get("category") == test_category, f"Item category mismatch: {item.get('category')} vs {test_category}"
        
        print(f"Category filter '{test_category}' returned {len(filtered_data.get('items', []))} items")

    def test_library_search_query(self, admin_session):
        """Library search query should work"""
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=12&q=productivity")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("items"), list), "items should be a list"
        print(f"Search 'productivity' returned {len(data.get('items', []))} items, total: {data.get('total', 0)}")

    def test_library_sort_newest(self, admin_session):
        """Library sort by newest should work"""
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=12&sort=newest")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", [])
        
        # Verify items are sorted by added_date descending
        if len(items) >= 2:
            for i in range(len(items) - 1):
                date1 = items[i].get("added_date", "")
                date2 = items[i + 1].get("added_date", "")
                if date1 and date2:
                    assert date1 >= date2, f"Sort order violation: {date1} should be >= {date2}"
        
        print(f"Sort newest returned {len(items)} items in correct order")

    def test_library_bookmarked_only_filter(self, admin_session):
        """Library bookmarked_only filter should work"""
        if not admin_session.user_id:
            pytest.skip("Could not get user_id")
        
        resp = admin_session.get(f"{BASE_URL}/api/content/library?page=1&per_page=12&bookmarked_only=true&user_id={admin_session.user_id}")
        assert resp.status_code == 200
        data = resp.json()
        
        # All items should be bookmarked
        for item in data.get("items", []):
            assert item.get("bookmarked") == True, f"Item should be bookmarked: {item.get('title')}"
        
        print(f"Bookmarked only filter returned {len(data.get('items', []))} bookmarked items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
