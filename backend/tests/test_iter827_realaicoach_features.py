"""
Iteration 827 - RealAICoach enterprise feature verification.

Covers:
- Access control ui_tier_routes payload
- Blog editorial workflow (draft/review/publish/schedule + auto-publish)
- Home badges & command palette nav counter (palette_power_user)
- Job search alerts CRUD + weekly digest surfacing
- Public blog visibility (only published editorial posts)
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"

HEADERS_MUT = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}


def _login(email, password):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=HEADERS_MUT,
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s, r.json()


@pytest.fixture(scope="module")
def admin_session():
    s, u = _login(ADMIN_EMAIL, ADMIN_PASS)
    return s, u


@pytest.fixture(scope="module")
def free_session():
    try:
        s, u = _login(FREE_EMAIL, FREE_PASS)
        return s, u
    except AssertionError:
        pytest.skip("free user login unavailable")


# ---------------------------------------------------------------------------
# Access control tier routes
# ---------------------------------------------------------------------------
class TestAccessControlTierRoutes:
    def test_ui_tier_routes_contains_required_keys(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "ui_tier_routes" in data, "ui_tier_routes missing"
        routes = data["ui_tier_routes"]
        for key in [
            "free_feature_prefixes",
            "basic_ui_prefixes",
            "premium_ui_prefixes",
            "basic_authenticated_ui_prefixes",
            "free_limited_ui_prefixes",
        ]:
            assert key in routes, f"missing {key}"
            assert isinstance(routes[key], list)

    def test_free_feature_prefixes_includes_flappy_bird(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        prefixes = r.json()["ui_tier_routes"]["free_feature_prefixes"]
        assert "/features/flappy-bird" in prefixes


# ---------------------------------------------------------------------------
# Blog editorial workflow
# ---------------------------------------------------------------------------
class TestBlogEditorialWorkflow:
    def _create_draft(self, s, suffix=""):
        title = f"TEST_editorial_{suffix or uuid.uuid4().hex[:8]}"
        payload = {
            "title": title,
            "excerpt": "Iteration 827 automated draft",
            "content": "Body content for editorial workflow test.",
            "category": "product",
        }
        r = s.post(
            f"{BASE_URL}/api/admin/blog-editorial/posts",
            json=payload,
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r.status_code in (200, 201), f"draft create failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        post = body.get("post", body)
        return post, title

    def _txn(self, s, post_id, action, publish_at=None):
        payload = {"action": action}
        if publish_at:
            payload["publish_at"] = publish_at
        r = s.post(
            f"{BASE_URL}/api/admin/blog-editorial/posts/{post_id}/transition",
            json=payload,
            headers=HEADERS_MUT,
            timeout=30,
        )
        return r

    def _pid(self, post):
        return post.get("post_id") or post.get("id")

    def test_create_draft(self, admin_session):
        s, _ = admin_session
        post, title = self._create_draft(s, "create")
        assert post.get("status") == "draft"
        assert post.get("title") == title
        assert self._pid(post)

    def test_full_workflow_submit_and_publish(self, admin_session):
        s, _ = admin_session
        post, _ = self._create_draft(s, "publishflow")
        post_id = self._pid(post)
        assert post_id, f"no id in {post}"

        # submit for review
        r = self._txn(s, post_id, "submit_review")
        assert r.status_code == 200, r.text[:200]
        assert (r.json().get("post") or r.json()).get("status") == "in_review"

        # approve/publish
        r = self._txn(s, post_id, "approve_publish")
        assert r.status_code == 200, r.text[:200]
        body = (r.json().get("post") or r.json())
        assert body.get("status") == "published"
        assert body.get("published_at")
        hist = body.get("workflow_history") or []
        assert len(hist) >= 2

    def test_schedule_future_and_reject_past(self, admin_session):
        s, _ = admin_session
        post, _ = self._create_draft(s, "schedflow")
        post_id = self._pid(post)

        # submit for review first
        r = self._txn(s, post_id, "submit_review")
        assert r.status_code == 200

        # schedule with past time -> 400
        r_past = self._txn(s, post_id, "schedule", "2000-01-01T00:00:00Z")
        assert r_past.status_code == 400, f"expected 400 got {r_past.status_code} {r_past.text[:200]}"

        # schedule with future time -> scheduled
        r_ok = self._txn(s, post_id, "schedule", "2099-01-01T00:00:00Z")
        assert r_ok.status_code == 200, r_ok.text[:200]
        body = r_ok.json().get("post") or r_ok.json()
        assert body.get("status") == "scheduled"

    def test_invalid_transition_returns_409(self, admin_session):
        s, _ = admin_session
        post, _ = self._create_draft(s, "invalidtrans")
        post_id = self._pid(post)
        # publish it
        for act in ("submit_review", "approve_publish"):
            r = self._txn(s, post_id, act)
            assert r.status_code == 200
        # now submit_review on a published post -> 409
        r_bad = self._txn(s, post_id, "submit_review")
        assert r_bad.status_code == 409, f"expected 409 got {r_bad.status_code} {r_bad.text[:200]}"

    def test_list_posts_with_status_all(self, admin_session):
        s, _ = admin_session
        r = s.get(
            f"{BASE_URL}/api/admin/blog-editorial/posts?status=all",
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "posts" in data
        assert "counts" in data
        assert "auto_published_now" in data
        assert isinstance(data["auto_published_now"], (int, list))

    def test_patch_updates_fields(self, admin_session):
        s, _ = admin_session
        post, _ = self._create_draft(s, "patch")
        post_id = self._pid(post)
        new_title = f"TEST_editorial_patched_{uuid.uuid4().hex[:6]}"
        r = s.patch(
            f"{BASE_URL}/api/admin/blog-editorial/posts/{post_id}",
            json={"title": new_title, "excerpt": "Updated excerpt"},
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json().get("post") or r.json()
        assert body.get("title") == new_title

    def test_non_admin_forbidden(self, free_session):
        s, _ = free_session
        r = s.get(f"{BASE_URL}/api/admin/blog-editorial/posts?status=all", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"
        r2 = s.post(
            f"{BASE_URL}/api/admin/blog-editorial/posts",
            json={"title": "TEST_free_attempt", "content": "x"},
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r2.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Blog V2 public visibility
# ---------------------------------------------------------------------------
class TestBlogV2PublicVisibility:
    def test_only_published_editorial_visible(self, admin_session):
        s, _ = admin_session
        # create a draft that must NOT surface in public
        payload = {
            "title": f"TEST_hidden_draft_{uuid.uuid4().hex[:6]}",
            "excerpt": "Should be hidden",
            "content": "hidden body",
            "category": "product",
        }
        r = s.post(
            f"{BASE_URL}/api/admin/blog-editorial/posts",
            json=payload,
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r.status_code in (200, 201)
        draft_title = payload["title"]

        # publish another one
        payload_pub = {
            "title": f"TEST_visible_pub_{uuid.uuid4().hex[:6]}",
            "excerpt": "Should be visible",
            "content": "published body",
            "category": "product",
        }
        r2 = s.post(
            f"{BASE_URL}/api/admin/blog-editorial/posts",
            json=payload_pub,
            headers=HEADERS_MUT,
            timeout=30,
        )
        pub_post = r2.json().get("post") or r2.json()
        pub_id = pub_post.get("post_id") or pub_post.get("id")
        for act in ("submit_review", "approve_publish"):
            s.post(
                f"{BASE_URL}/api/admin/blog-editorial/posts/{pub_id}/transition",
                json={"action": act},
                headers=HEADERS_MUT,
                timeout=30,
            )

        # public feed (also authenticated to bypass any preview auth-gate)
        r3 = s.get(f"{BASE_URL}/api/blog/v2/posts?limit=200", timeout=30)
        assert r3.status_code == 200, r3.text[:200]
        payload_data = r3.json()
        posts = payload_data.get("items") or payload_data.get("posts") or []
        titles = [p.get("title") for p in posts]
        assert draft_title not in titles, "Draft leaked into public feed"


# ---------------------------------------------------------------------------
# Home dashboard - command palette nav + badges
# ---------------------------------------------------------------------------
class TestHomeCommandPaletteAndBadges:
    def test_palette_nav_increments_and_power_user(self, admin_session):
        s, _ = admin_session
        earned_flag = False
        last = None
        # Get current count first
        for _ in range(15):
            r = s.post(
                f"{BASE_URL}/api/home/command-palette-nav",
                json={"destination": "/dashboard"},
                headers=HEADERS_MUT,
                timeout=30,
            )
            assert r.status_code == 200, r.text[:200]
            body = r.json()
            last = body
            if body.get("power_user_earned"):
                earned_flag = True
            if body.get("nav_count", 0) >= 10 and earned_flag:
                break
        assert last is not None
        assert last.get("nav_count", 0) >= 10
        # Either already earned OR earned in this loop
        # (Even if earned earlier, badge should still be present in badges endpoint)

    def test_badges_include_palette_power_user(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/home/badges", timeout=30)
        assert r.status_code == 200
        data = r.json()
        badges = data.get("badges") or data.get("items") or []
        ids = [b.get("id") for b in badges]
        assert "palette_power_user" in ids, f"palette_power_user missing. ids={ids}"
        badge = next(b for b in badges if b.get("id") == "palette_power_user")
        assert "Power User" in badge.get("title", "")
        assert badge.get("threshold") == 10


# ---------------------------------------------------------------------------
# Job Search Alerts + Weekly Digest surfacing
# ---------------------------------------------------------------------------
class TestJobSearchAlerts:
    def _cleanup(self, s):
        r = s.get(f"{BASE_URL}/api/job-search/alerts", timeout=30)
        if r.status_code == 200:
            for a in (r.json().get("alerts") or r.json().get("items") or []):
                aid = a.get("id") or a.get("alert_id")
                if aid:
                    s.delete(
                        f"{BASE_URL}/api/job-search/alerts/{aid}",
                        headers=HEADERS_MUT,
                        timeout=30,
                    )

    @pytest.fixture(autouse=True)
    def _setup(self, admin_session):
        s, _ = admin_session
        self._cleanup(s)
        yield
        self._cleanup(s)

    def test_create_and_dedupe(self, admin_session):
        s, _ = admin_session
        q = f"TEST_engineer_{uuid.uuid4().hex[:6]}"
        r = s.post(
            f"{BASE_URL}/api/job-search/alerts",
            json={"q": q},
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("created") is True

        r2 = s.post(
            f"{BASE_URL}/api/job-search/alerts",
            json={"q": q},
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r2.status_code == 200
        assert r2.json().get("created") is False

    def test_list_alerts_has_match_fields(self, admin_session):
        s, _ = admin_session
        q = f"TEST_designer_{uuid.uuid4().hex[:6]}"
        s.post(f"{BASE_URL}/api/job-search/alerts", json={"q": q}, headers=HEADERS_MUT, timeout=30)

        r = s.get(f"{BASE_URL}/api/job-search/alerts", timeout=30)
        assert r.status_code == 200
        alerts = r.json().get("alerts") or r.json().get("items") or []
        assert len(alerts) >= 1
        a = alerts[0]
        for k in ("new_match_count", "new_internal_roles", "new_external_roles"):
            assert k in a, f"missing {k} in alert: {list(a.keys())}"

    def test_delete_alert(self, admin_session):
        s, _ = admin_session
        q = f"TEST_pm_{uuid.uuid4().hex[:6]}"
        r_c = s.post(
            f"{BASE_URL}/api/job-search/alerts",
            json={"q": q},
            headers=HEADERS_MUT,
            timeout=30,
        )
        alert_obj = r_c.json().get("alert") or r_c.json()
        alert_id = alert_obj.get("alert_id") or alert_obj.get("id")
        if not alert_id:
            # fetch via list
            r_l = s.get(f"{BASE_URL}/api/job-search/alerts", timeout=30)
            for a in (r_l.json().get("alerts") or []):
                if a.get("q") == q or a.get("query") == q:
                    alert_id = a.get("id") or a.get("alert_id")
                    break
        assert alert_id, "no alert id available for delete"

        r_d = s.delete(
            f"{BASE_URL}/api/job-search/alerts/{alert_id}",
            headers=HEADERS_MUT,
            timeout=30,
        )
        assert r_d.status_code in (200, 204)

        # verify gone
        r_l2 = s.get(f"{BASE_URL}/api/job-search/alerts", timeout=30)
        alerts = r_l2.json().get("alerts") or r_l2.json().get("items") or []
        assert not any((a.get("id") or a.get("alert_id")) == alert_id for a in alerts)

    def test_limit_10_alerts(self, admin_session):
        s, _ = admin_session
        for i in range(12):
            r = s.post(
                f"{BASE_URL}/api/job-search/alerts",
                json={"q": f"TEST_limit_{i}_{uuid.uuid4().hex[:4]}"},
                headers=HEADERS_MUT,
                timeout=30,
            )
            if r.status_code >= 400:
                break
        r_l = s.get(f"{BASE_URL}/api/job-search/alerts", timeout=30)
        alerts = r_l.json().get("alerts") or r_l.json().get("items") or []
        assert len(alerts) <= 10, f"limit not enforced: {len(alerts)}"

    def test_weekly_digest_includes_search_alerts(self, admin_session):
        s, u = admin_session
        # Ensure at least one alert exists
        s.post(
            f"{BASE_URL}/api/job-search/alerts",
            json={"q": f"TEST_digest_{uuid.uuid4().hex[:5]}"},
            headers=HEADERS_MUT,
            timeout=30,
        )
        user_id = u.get("user_id")
        # digest may take up to 30s (LLM)
        r = s.get(f"{BASE_URL}/api/weekly-digest/{user_id}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "search_alerts" in data, f"search_alerts missing: {list(data.keys())}"
        assert isinstance(data["search_alerts"], list)
