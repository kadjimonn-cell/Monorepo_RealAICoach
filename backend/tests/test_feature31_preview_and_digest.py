"""Feature 31 additions: Preview lifecycle + Weekly Coaching Digest.

Covers:
- Free user coach preview flags on GET /coaches (career available; other 3 preview_available:true)
- Full preview lifecycle:
    - create preview session (is_preview:true)
    - first message -> 200 with preview_used:true, preview_gate:true, decremented remaining_today
    - second message on same session -> 402 with code PREVIEW_USED, upgrade_route
    - GET /sessions/{id} -> preview_gate:true, 2 messages persisted
    - After consumption, /coaches shows preview_available:false for that coach
    - New session for same coach -> 402 COACH_LOCKED
- Preview isolation across coaches (previewing interview_coach must NOT consume resume/negotiation previews)
- Preview quota interaction: preview messages count against 5/day quota
- Premium/admin never sees preview flags: available:true for all, preview_available:false
- Admin digest dry_run: candidates>=1, sent>=1, errors:0, no email sent (has dry_run:true)
- Email preferences: 'coaching_digest' key present, default enabled, opt-out then dry_run counts skipped_pref
- Template audit: 'coaching_team_weekly_digest' present with status 'pass'; overall 0 broken issues.

All prompts kept to SHORT one-liners to conserve free user's 5/day LLM quota.
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"

CSRF = {"X-Requested-With": "XMLHttpRequest"}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(CSRF)
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login(FREE_EMAIL, FREE_PASS)


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASS)


# --- Preview flags ------------------------------------------------------------


class TestPreviewFlags:
    def test_free_user_preview_flags(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        by_key = {c["coach_key"]: c for c in data["coaches"]}
        assert by_key["career_coach"]["available"] is True
        assert by_key["career_coach"]["preview_available"] is False
        for locked in ("interview_coach", "resume_specialist", "negotiation_coach"):
            assert by_key[locked]["available"] is False, f"{locked} should be locked for free"
            assert by_key[locked]["preview_available"] is True, f"{locked} preview_available expected True"

    def test_admin_never_sees_preview_flags(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["all_coaches_unlocked"] is True
        for c in data["coaches"]:
            assert c["available"] is True, f"{c['coach_key']} must be available for admin"
            assert c["preview_available"] is False, f"admin should not see preview_available for {c['coach_key']}"


# --- Preview lifecycle (interview_coach) --------------------------------------


class TestPreviewLifecycle:
    """Runs interview_coach preview end-to-end, uses ~2 messages of free quota."""

    def test_preview_lifecycle_interview_coach(self, free_session):
        base = f"{BASE_URL}/api/ai-coaching-team"

        # baseline status
        st = free_session.get(f"{base}/status", timeout=15).json()
        assert st["daily_limit"] == 5
        remaining_before = st["remaining_today"]
        if remaining_before <= 0:
            pytest.skip("Free user daily quota already exhausted; can't run preview lifecycle")

        # baseline coaches: interview_coach preview_available=true
        coaches = free_session.get(f"{base}/coaches", timeout=15).json()
        by_key = {c["coach_key"]: c for c in coaches["coaches"]}
        assert by_key["interview_coach"]["preview_available"] is True

        # 1) create preview session
        r = free_session.post(f"{base}/sessions", json={"coach_key": "interview_coach"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        session = r.json()
        assert session.get("is_preview") is True
        assert session["coach_key"] == "interview_coach"
        session_id = session["session_id"]

        # 2) first message -> real LLM reply + preview flags
        r = free_session.post(
            f"{base}/sessions/{session_id}/message",
            json={"message": "One tip for a 2-min elevator pitch?"},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("preview_used") is True
        assert body.get("preview_gate") is True
        assert isinstance(body.get("reply"), str) and len(body["reply"]) > 0
        assert body.get("remaining_today") == max(0, remaining_before - 1)

        # 3) second message same session -> 402 PREVIEW_USED
        r2 = free_session.post(
            f"{base}/sessions/{session_id}/message",
            json={"message": "Follow-up?"},
            timeout=30,
        )
        assert r2.status_code == 402, r2.text[:300]
        detail = r2.json().get("detail", {})
        assert detail.get("code") == "PREVIEW_USED"
        assert detail.get("upgrade_route") == "/subscription/plans"

        # 4) GET session shows preview_gate:true and 2 messages persisted
        gs = free_session.get(f"{base}/sessions/{session_id}", timeout=15)
        assert gs.status_code == 200
        gsd = gs.json()
        assert gsd.get("preview_gate") is True
        assert len(gsd.get("messages") or []) == 2
        roles = [m["role"] for m in gsd["messages"]]
        assert roles == ["user", "assistant"]

        # 5) coaches now: interview_coach preview_available=false
        coaches2 = free_session.get(f"{base}/coaches", timeout=15).json()
        by_key2 = {c["coach_key"]: c for c in coaches2["coaches"]}
        assert by_key2["interview_coach"]["preview_available"] is False
        assert by_key2["interview_coach"]["available"] is False

        # 6) create new session for interview_coach -> 402 COACH_LOCKED
        r3 = free_session.post(f"{base}/sessions", json={"coach_key": "interview_coach"}, timeout=15)
        assert r3.status_code == 402, r3.text[:300]
        d3 = r3.json().get("detail", {})
        assert d3.get("code") == "COACH_LOCKED"
        assert d3.get("upgrade_route") == "/subscription/plans"

    def test_preview_isolation_resume_and_negotiation_still_previewable(self, free_session):
        """After consuming interview_coach preview, resume_specialist + negotiation_coach must still be previewable."""
        base = f"{BASE_URL}/api/ai-coaching-team"
        coaches = free_session.get(f"{base}/coaches", timeout=15).json()
        by_key = {c["coach_key"]: c for c in coaches["coaches"]}
        assert by_key["resume_specialist"]["preview_available"] is True
        assert by_key["negotiation_coach"]["preview_available"] is True
        # career_coach still free and normal (no preview_available since it's already available)
        assert by_key["career_coach"]["available"] is True
        assert by_key["career_coach"]["preview_available"] is False


# --- Digest -------------------------------------------------------------------


class TestDigest:
    def test_admin_dry_run(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/run?dry_run=true",
            timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("dry_run") is True
        assert body.get("errors", 0) == 0
        assert body.get("candidates", 0) >= 1
        assert body.get("sent", 0) >= 1
        assert "week" in body

    def test_non_admin_cannot_run_digest(self, free_session):
        r = free_session.post(f"{BASE_URL}/api/ai-coaching-team/digest/run?dry_run=true", timeout=30)
        assert r.status_code in (401, 403), r.text[:200]

    def test_preferences_has_coaching_digest_default_on(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/email-notifications/preferences", timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        prefs = body.get("preferences") or body
        # search for coaching_digest key
        found = None
        if isinstance(prefs, dict):
            if "coaching_digest" in prefs:
                found = prefs["coaching_digest"]
            else:
                for k in ("email_types", "types", "items"):
                    v = prefs.get(k)
                    if isinstance(v, dict) and "coaching_digest" in v:
                        found = v["coaching_digest"]
                        break
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and item.get("key") == "coaching_digest":
                                found = item
                                break
                        if found is not None:
                            break
        assert found is not None, f"coaching_digest not found in preferences response: {body}"
        # enabled default True (accept a couple of shapes)
        if isinstance(found, dict):
            assert found.get("enabled", found.get("value", True)) is True
            assert bool(found.get("always_on", False)) is False
        else:
            assert bool(found) is True

    def test_opt_out_then_skipped_pref_then_reenable(self, free_session, admin_session):
        # 1) opt out coaching_digest for free user
        put_r = free_session.put(
            f"{BASE_URL}/api/email-notifications/preferences",
            json={"coaching_digest": False},
            timeout=15,
        )
        assert put_r.status_code in (200, 204), put_r.text[:300]

        # verify it's now False in GET
        get_r = free_session.get(f"{BASE_URL}/api/email-notifications/preferences", timeout=15)
        assert get_r.status_code == 200
        body = get_r.json()
        # extract coaching_digest
        cd_val = None
        prefs = body.get("preferences") or body
        if isinstance(prefs, dict):
            if "coaching_digest" in prefs:
                v = prefs["coaching_digest"]
                cd_val = v.get("enabled") if isinstance(v, dict) else v
            else:
                for k in ("email_types", "types", "items"):
                    v = prefs.get(k)
                    if isinstance(v, dict) and "coaching_digest" in v:
                        vv = v["coaching_digest"]
                        cd_val = vv.get("enabled") if isinstance(vv, dict) else vv
                        break
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and item.get("key") == "coaching_digest":
                                cd_val = item.get("enabled", item.get("value"))
                                break
                        if cd_val is not None:
                            break
        assert cd_val is False, f"coaching_digest still enabled after opt-out: {body}"

        # 2) run dry_run and confirm skipped_pref >= 1
        try:
            dr = admin_session.post(
                f"{BASE_URL}/api/ai-coaching-team/digest/run?dry_run=true",
                timeout=60,
            )
            assert dr.status_code == 200, dr.text[:300]
            summary = dr.json()
            assert summary.get("skipped_pref", 0) >= 1, f"skipped_pref not incremented: {summary}"
        finally:
            # 3) re-enable to preserve fixture state
            free_session.put(
                f"{BASE_URL}/api/email-notifications/preferences",
                json={"coaching_digest": True},
                timeout=15,
            )

    def test_template_audit_pass(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/email-notifications/templates/audit", timeout=60)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        templates = body.get("templates") or body.get("results") or []
        # find coaching template
        entry = None
        for t in templates:
            if not isinstance(t, dict):
                continue
            key = t.get("template_key") or t.get("key") or t.get("name")
            if key == "coaching_team_weekly_digest":
                entry = t
                break
        assert entry is not None, "coaching_team_weekly_digest not in audit templates"
        assert (entry.get("status") or entry.get("audit_status") or "").lower() == "pass", entry

        # overall audit stats  (0 issues)
        # accept top-level totals if present
        total_issues = (
            body.get("templates_with_issues")
            or body.get("issue_count")
            or body.get("failing")
            or 0
        )
        assert int(total_issues) == 0, f"expected 0 templates with issues, got {total_issues}: {body}"
