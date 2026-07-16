"""
Blog V2 API Tests - Enterprise Blog Feature
Tests: home, posts, post detail, authors, recommendations, AI summary, bookmarks, history
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
PREMIUM_EMAIL = "f22.premium.20260613@example.com"
PREMIUM_PASSWORD = "F22Premium#2026Aa"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"  # CSRF header
    })
    return session


@pytest.fixture(scope="module")
def premium_session(api_client):
    """Authenticated premium user session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": PREMIUM_EMAIL,
        "password": PREMIUM_PASSWORD
    })
    if response.status_code == 200:
        return api_client
    pytest.skip(f"Premium user login failed: {response.status_code}")


@pytest.fixture(scope="module")
def free_session(api_client):
    """Authenticated free user session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_EMAIL,
        "password": FREE_PASSWORD
    })
    if response.status_code == 200:
        return api_client
    pytest.skip(f"Free user login failed: {response.status_code}")


class TestBlogV2PublicEndpoints:
    """Public Blog V2 API tests - no auth required"""

    def test_blog_v2_home_returns_200(self, api_client):
        """GET /api/blog/v2/home returns 200 with expected structure"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "featured" in data, "Missing 'featured' in home payload"
        assert "trending" in data, "Missing 'trending' in home payload"
        assert "latest" in data, "Missing 'latest' in home payload"
        assert "categories" in data, "Missing 'categories' in home payload"
        assert "authors" in data, "Missing 'authors' in home payload"
        assert "stats" in data, "Missing 'stats' in home payload"
        assert "viewer_plan" in data, "Missing 'viewer_plan' in home payload"
        
        # Verify featured post structure
        if data["featured"]:
            featured = data["featured"]
            assert "post_id" in featured
            assert "slug" in featured
            assert "title" in featured
            assert "excerpt" in featured
            assert "category" in featured
        
        print(f"✓ Blog home loaded with {len(data['latest'])} latest posts, {len(data['categories'])} categories")

    def test_blog_v2_posts_returns_200(self, api_client):
        """GET /api/blog/v2/posts returns paginated posts"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data, "Missing 'items' in posts payload"
        assert "total" in data, "Missing 'total' in posts payload"
        assert "page" in data, "Missing 'page' in posts payload"
        assert "page_size" in data, "Missing 'page_size' in posts payload"
        assert "has_next" in data, "Missing 'has_next' in posts payload"
        
        # Verify post card structure
        if data["items"]:
            post = data["items"][0]
            assert "post_id" in post
            assert "slug" in post
            assert "title" in post
            assert "premium_required" in post
            assert "premium_locked" in post
            assert "bookmarked" in post
        
        print(f"✓ Blog posts returned {len(data['items'])} items, total: {data['total']}")

    def test_blog_v2_posts_with_search(self, api_client):
        """GET /api/blog/v2/posts with search query"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts", params={"q": "AI"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data
        print(f"✓ Blog search for 'AI' returned {len(data['items'])} results")

    def test_blog_v2_posts_with_category_filter(self, api_client):
        """GET /api/blog/v2/posts with category filter"""
        # First get categories from home
        home_response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        home_data = home_response.json()
        
        if home_data.get("categories"):
            category = home_data["categories"][0]["name"]
            response = api_client.get(f"{BASE_URL}/api/blog/v2/posts", params={"category": category})
            assert response.status_code == 200
            
            data = response.json()
            print(f"✓ Blog category filter '{category}' returned {len(data['items'])} posts")

    def test_blog_v2_posts_with_sort(self, api_client):
        """GET /api/blog/v2/posts with sort options"""
        for sort_option in ["latest", "popular", "bookmarked"]:
            response = api_client.get(f"{BASE_URL}/api/blog/v2/posts", params={"sort": sort_option})
            assert response.status_code == 200, f"Sort '{sort_option}' failed"
        
        print("✓ Blog posts sort options (latest, popular, bookmarked) all work")

    def test_blog_v2_post_detail_returns_200(self, api_client):
        """GET /api/blog/v2/posts/{slug} returns post detail"""
        # First get a post slug from the list
        posts_response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        posts_data = posts_response.json()
        
        if not posts_data.get("items"):
            pytest.skip("No posts available for detail test")
        
        slug = posts_data["items"][0]["slug"]
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "post_id" in data
        assert "slug" in data
        assert "title" in data
        assert "content_blocks" in data
        assert "preview_blocks" in data
        assert "premium_gate" in data
        assert "related_posts" in data
        
        # Verify premium gate structure
        gate = data["premium_gate"]
        assert "required" in gate
        assert "unlocked" in gate
        assert "cta" in gate
        
        print(f"✓ Blog post detail loaded: '{data['title'][:50]}...'")

    def test_blog_v2_post_detail_404_for_invalid_slug(self, api_client):
        """GET /api/blog/v2/posts/{invalid_slug} returns 404"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts/invalid-slug-that-does-not-exist-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Blog post detail returns 404 for invalid slug")

    def test_blog_v2_author_profile_returns_200(self, api_client):
        """GET /api/blog/v2/authors/{slug} returns author profile"""
        # First get an author slug from home
        home_response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        home_data = home_response.json()
        
        if not home_data.get("authors"):
            pytest.skip("No authors available for profile test")
        
        author_slug = home_data["authors"][0]["author_slug"]
        response = api_client.get(f"{BASE_URL}/api/blog/v2/authors/{author_slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "author" in data
        assert "posts" in data
        
        author = data["author"]
        assert "author_slug" in author
        assert "name" in author
        assert "role" in author
        assert "bio" in author
        
        print(f"✓ Author profile loaded: '{author['name']}' with {len(data['posts'])} posts")

    def test_blog_v2_author_profile_404_for_invalid_slug(self, api_client):
        """GET /api/blog/v2/authors/{invalid_slug} returns 404"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/authors/invalid-author-slug-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Author profile returns 404 for invalid slug")

    def test_blog_v2_recommendations_returns_200(self, api_client):
        """GET /api/blog/v2/recommendations returns recommendations"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/recommendations")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data
        assert "viewer_plan" in data
        
        print(f"✓ Blog recommendations returned {len(data['items'])} items")


class TestBlogV2AIEndpoint:
    """AI Summary endpoint tests"""

    def test_blog_v2_ai_summary_returns_200(self, api_client):
        """POST /api/blog/v2/ai/summary returns AI-generated summary"""
        # First get a post slug
        posts_response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        posts_data = posts_response.json()
        
        if not posts_data.get("items"):
            pytest.skip("No posts available for AI summary test")
        
        slug = posts_data["items"][0]["slug"]
        response = api_client.post(f"{BASE_URL}/api/blog/v2/ai/summary", json={"slug": slug})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("ok") == True, "AI summary should return ok=True"
        assert "summary" in data, "Missing 'summary' in AI response"
        assert "key_takeaways" in data, "Missing 'key_takeaways' in AI response"
        assert "model" in data, "Missing 'model' in AI response"
        
        # Verify model is gpt-5.2 or fallback
        assert data["model"] in ["gpt-5.2", "fallback"], f"Unexpected model: {data['model']}"
        
        print(f"✓ AI summary generated with model: {data['model']}")

    def test_blog_v2_ai_summary_404_for_invalid_slug(self, api_client):
        """POST /api/blog/v2/ai/summary returns 404 for invalid slug"""
        response = api_client.post(f"{BASE_URL}/api/blog/v2/ai/summary", json={"slug": "invalid-slug-12345"})
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ AI summary returns 404 for invalid slug")


class TestBlogV2AuthenticatedEndpoints:
    """Authenticated Blog V2 API tests - require auth"""

    def test_blog_v2_bookmarks_requires_auth(self, api_client):
        """GET /api/blog/v2/me/bookmarks returns 401 without auth"""
        # Create a fresh session without auth
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Bookmarks endpoint requires authentication")

    def test_blog_v2_history_requires_auth(self, api_client):
        """GET /api/blog/v2/me/history returns 401 without auth"""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/history")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ History endpoint requires authentication")

    def test_blog_v2_add_bookmark_requires_auth(self, api_client):
        """POST /api/blog/v2/me/bookmarks/{post_id} returns 401 without auth"""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = fresh_session.post(f"{BASE_URL}/api/blog/v2/me/bookmarks/test-post-id")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Add bookmark endpoint requires authentication")

    def test_blog_v2_write_history_requires_auth(self, api_client):
        """POST /api/blog/v2/me/history returns 401 without auth"""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = fresh_session.post(f"{BASE_URL}/api/blog/v2/me/history", json={
            "post_id": "test-post-id",
            "progress_percent": 50,
            "dwell_seconds": 120
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Write history endpoint requires authentication")


class TestBlogV2PremiumUserFlow:
    """Premium user flow tests"""

    def test_premium_user_login_and_bookmarks(self):
        """Premium user can login and access bookmarks"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as premium user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": PREMIUM_EMAIL,
            "password": PREMIUM_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_response.status_code}")
        
        # Access bookmarks
        bookmarks_response = session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert bookmarks_response.status_code == 200, f"Expected 200, got {bookmarks_response.status_code}"
        
        data = bookmarks_response.json()
        assert "items" in data
        print(f"✓ Premium user can access bookmarks: {len(data['items'])} items")

    def test_premium_user_can_add_and_remove_bookmark(self):
        """Premium user can add and remove bookmarks"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as premium user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": PREMIUM_EMAIL,
            "password": PREMIUM_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_response.status_code}")
        
        # Get a post to bookmark
        posts_response = session.get(f"{BASE_URL}/api/blog/v2/posts")
        posts_data = posts_response.json()
        
        if not posts_data.get("items"):
            pytest.skip("No posts available for bookmark test")
        
        post_id = posts_data["items"][0]["post_id"]
        
        # Add bookmark
        add_response = session.post(f"{BASE_URL}/api/blog/v2/me/bookmarks/{post_id}")
        assert add_response.status_code == 200, f"Add bookmark failed: {add_response.status_code}"
        
        add_data = add_response.json()
        assert add_data.get("ok") == True
        assert add_data.get("bookmarked") == True
        
        # Remove bookmark
        remove_response = session.delete(f"{BASE_URL}/api/blog/v2/me/bookmarks/{post_id}")
        assert remove_response.status_code == 200, f"Remove bookmark failed: {remove_response.status_code}"
        
        remove_data = remove_response.json()
        assert remove_data.get("ok") == True
        assert remove_data.get("bookmarked") == False
        
        print("✓ Premium user can add and remove bookmarks")

    def test_premium_user_can_write_history(self):
        """Premium user can write reading history"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as premium user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": PREMIUM_EMAIL,
            "password": PREMIUM_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_response.status_code}")
        
        # Get a post
        posts_response = session.get(f"{BASE_URL}/api/blog/v2/posts")
        posts_data = posts_response.json()
        
        if not posts_data.get("items"):
            pytest.skip("No posts available for history test")
        
        post_id = posts_data["items"][0]["post_id"]
        
        # Write history
        history_response = session.post(f"{BASE_URL}/api/blog/v2/me/history", json={
            "post_id": post_id,
            "progress_percent": 75,
            "dwell_seconds": 300
        })
        assert history_response.status_code == 200, f"Write history failed: {history_response.status_code}"
        
        history_data = history_response.json()
        assert history_data.get("ok") == True
        assert history_data.get("progress_percent") == 75
        
        # Verify history is persisted
        get_history_response = session.get(f"{BASE_URL}/api/blog/v2/me/history")
        assert get_history_response.status_code == 200
        
        get_history_data = get_history_response.json()
        assert "items" in get_history_data
        
        print("✓ Premium user can write and read history")


class TestBlogV2ViewerPlanGating:
    """Viewer plan gating tests"""

    def test_unauthenticated_user_sees_free_plan(self, api_client):
        """Unauthenticated user sees viewer_plan=free"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("viewer_plan") == "free", f"Expected 'free', got '{data.get('viewer_plan')}'"
        print("✓ Unauthenticated user sees viewer_plan=free")

    def test_premium_content_locked_for_free_user(self, api_client):
        """Premium content shows premium_locked=True for free users"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/posts")
        data = response.json()
        
        # Find a premium post
        premium_posts = [p for p in data.get("items", []) if p.get("premium_required")]
        
        if not premium_posts:
            pytest.skip("No premium posts available for gating test")
        
        premium_post = premium_posts[0]
        assert premium_post.get("premium_locked") == True, "Premium post should be locked for free user"
        
        print("✓ Premium content is locked for free users")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
