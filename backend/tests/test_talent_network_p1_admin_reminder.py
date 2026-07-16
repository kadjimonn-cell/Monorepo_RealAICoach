"""
Test Talent Network P1 Features:
- Admin Segment operations (create segment with filters)
- Admin Campaign scheduler (create campaign, run campaign)
- Member Reminder Timeline (next ETA, snooze controls, digest history)
- Enriched admin overview metrics (reminder channel mix, premium unlocked, referrals)
"""
import os
import pytest
import requests
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Authenticate as admin and return session with cookies"""
    login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text[:200]}")
    return api_client


@pytest.fixture(scope="module")
def test_member_email():
    """Generate unique test member email"""
    return f"tn.p1.test.{uuid.uuid4().hex[:8]}@example.com"


class TestTalentNetworkAdminOverview:
    """Test enriched admin overview metrics"""

    def test_admin_overview_loads(self, admin_session):
        """Admin overview endpoint returns expected enriched metrics"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert "summary" in data, "Response should contain summary"
        assert "window_days" in data, "Response should contain window_days"
        
        summary = data["summary"]
        # Check enriched metrics
        assert "total_signups" in summary, "Should have total_signups"
        assert "active_signups" in summary, "Should have active_signups"
        assert "dispatch_totals" in summary, "Should have dispatch_totals"
        assert "frequency_breakdown" in summary, "Should have frequency_breakdown"
        assert "reminder_channel_breakdown" in summary, "Should have reminder_channel_breakdown"
        assert "premium_unlocked_count" in summary, "Should have premium_unlocked_count"
        assert "referral_accept_in_window" in summary, "Should have referral_accept_in_window"
        
        # Validate frequency breakdown structure
        freq = summary.get("frequency_breakdown", {})
        assert "daily" in freq, "frequency_breakdown should have daily"
        assert "weekly" in freq, "frequency_breakdown should have weekly"
        
        # Validate reminder channel breakdown structure
        channels = summary.get("reminder_channel_breakdown", {})
        assert "in_app" in channels, "reminder_channel_breakdown should have in_app"
        assert "email" in channels, "reminder_channel_breakdown should have email"
        
        print(f"Admin overview loaded: {summary.get('total_signups')} total signups, "
              f"premium_unlocked={summary.get('premium_unlocked_count')}, "
              f"referrals_in_window={summary.get('referral_accept_in_window')}")


class TestTalentNetworkSegmentOperations:
    """Test admin segment CRUD operations"""

    def test_list_segments(self, admin_session):
        """Admin can list segments"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/segments")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "segments" in data, "Response should contain segments list"
        assert isinstance(data["segments"], list), "segments should be a list"
        print(f"Listed {len(data['segments'])} segments")

    def test_create_segment_with_filters(self, admin_session):
        """Admin can create segment with cadence, channel, premium state, profile min/max, consent toggle"""
        segment_name = f"TEST_Segment_{uuid.uuid4().hex[:6]}"
        payload = {
            "name": segment_name,
            "description": "Test segment for P1 validation",
            "alert_frequency": "weekly",
            "reminder_channel": "in_app",
            "profile_min": 30,
            "profile_max": 80,
            "premium_state": "locked",
            "marketing_consent_required": True,
            "active": True
        }
        
        response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/segments", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "segment" in data, "Response should contain segment"
        
        segment = data["segment"]
        assert segment.get("name") == segment_name, "Segment name should match"
        assert segment.get("alert_frequency") == "weekly", "alert_frequency should be weekly"
        assert segment.get("reminder_channel") == "in_app", "reminder_channel should be in_app"
        assert segment.get("profile_min") == 30, "profile_min should be 30"
        assert segment.get("profile_max") == 80, "profile_max should be 80"
        assert segment.get("premium_state") == "locked", "premium_state should be locked"
        assert segment.get("marketing_consent_required") is True, "marketing_consent_required should be True"
        assert "segment_id" in segment, "Segment should have segment_id"
        assert "estimated_members" in segment, "Segment should have estimated_members"
        
        print(f"Created segment: {segment.get('segment_id')} with estimated {segment.get('estimated_members')} members")
        return segment.get("segment_id")

    def test_segment_appears_in_list(self, admin_session):
        """Created segment appears in segment list"""
        # Create a segment first
        segment_name = f"TEST_ListCheck_{uuid.uuid4().hex[:6]}"
        create_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/segments", json={
            "name": segment_name,
            "description": "Test for list verification",
            "alert_frequency": "any",
            "reminder_channel": "any",
            "profile_min": 0,
            "profile_max": 100,
            "premium_state": "any",
            "marketing_consent_required": False,
            "active": True
        })
        assert create_response.status_code == 200
        created_segment = create_response.json().get("segment", {})
        segment_id = created_segment.get("segment_id")
        
        # Verify it appears in list
        list_response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/segments")
        assert list_response.status_code == 200
        
        segments = list_response.json().get("segments", [])
        segment_ids = [s.get("segment_id") for s in segments]
        assert segment_id in segment_ids, f"Created segment {segment_id} should appear in list"
        print(f"Verified segment {segment_id} appears in list")


class TestTalentNetworkCampaignScheduler:
    """Test admin campaign scheduler operations"""

    def test_list_campaigns(self, admin_session):
        """Admin can list campaigns"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/campaigns")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "campaigns" in data, "Response should contain campaigns list"
        assert "runs" in data, "Response should contain runs list"
        print(f"Listed {len(data['campaigns'])} campaigns, {len(data['runs'])} runs")

    def test_create_campaign_with_segment(self, admin_session):
        """Admin can create campaign with segment ID, channel, schedule type, message title/body, CTA"""
        # First create a segment to use
        segment_name = f"TEST_CampaignSeg_{uuid.uuid4().hex[:6]}"
        seg_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/segments", json={
            "name": segment_name,
            "description": "Segment for campaign test",
            "alert_frequency": "any",
            "reminder_channel": "any",
            "profile_min": 0,
            "profile_max": 100,
            "premium_state": "any",
            "marketing_consent_required": False,
            "active": True
        })
        assert seg_response.status_code == 200
        segment_id = seg_response.json().get("segment", {}).get("segment_id")
        
        # Create campaign
        campaign_name = f"TEST_Campaign_{uuid.uuid4().hex[:6]}"
        payload = {
            "campaign_name": campaign_name,
            "segment_id": segment_id,
            "channel": "in_app",
            "schedule_type": "run_now",
            "message_title": "Test Campaign Title",
            "message_body": "This is a test campaign message body for P1 validation testing.",
            "cta_label": "Open Hub",
            "cta_path": "/talent-network"
        }
        
        response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/campaigns", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "campaign" in data, "Response should contain campaign"
        
        campaign = data["campaign"]
        assert campaign.get("campaign_name") == campaign_name, "Campaign name should match"
        assert campaign.get("segment_id") == segment_id, "segment_id should match"
        assert campaign.get("channel") == "in_app", "channel should be in_app"
        assert campaign.get("message_title") == "Test Campaign Title", "message_title should match"
        assert campaign.get("cta_label") == "Open Hub", "cta_label should match"
        assert "campaign_id" in campaign, "Campaign should have campaign_id"
        
        print(f"Created campaign: {campaign.get('campaign_id')}")
        return campaign.get("campaign_id"), segment_id

    def test_campaign_appears_in_list(self, admin_session):
        """Created campaign appears in campaign list"""
        # Create segment and campaign
        segment_name = f"TEST_CmpListSeg_{uuid.uuid4().hex[:6]}"
        seg_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/segments", json={
            "name": segment_name,
            "alert_frequency": "any",
            "reminder_channel": "any",
            "profile_min": 0,
            "profile_max": 100,
            "premium_state": "any",
            "active": True
        })
        segment_id = seg_response.json().get("segment", {}).get("segment_id")
        
        campaign_name = f"TEST_CmpList_{uuid.uuid4().hex[:6]}"
        create_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/campaigns", json={
            "campaign_name": campaign_name,
            "segment_id": segment_id,
            "channel": "email",
            "schedule_type": "run_now",
            "message_title": "List Test Campaign",
            "message_body": "Testing campaign list appearance."
        })
        assert create_response.status_code == 200
        campaign_id = create_response.json().get("campaign", {}).get("campaign_id")
        
        # Verify in list
        list_response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/campaigns")
        assert list_response.status_code == 200
        
        campaigns = list_response.json().get("campaigns", [])
        campaign_ids = [c.get("campaign_id") for c in campaigns]
        assert campaign_id in campaign_ids, f"Created campaign {campaign_id} should appear in list"
        print(f"Verified campaign {campaign_id} appears in list")

    def test_run_campaign_now(self, admin_session):
        """Admin can run campaign and it creates run history"""
        # Create segment and campaign
        segment_name = f"TEST_RunSeg_{uuid.uuid4().hex[:6]}"
        seg_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/segments", json={
            "name": segment_name,
            "alert_frequency": "any",
            "reminder_channel": "any",
            "profile_min": 0,
            "profile_max": 100,
            "premium_state": "any",
            "active": True
        })
        segment_id = seg_response.json().get("segment", {}).get("segment_id")
        
        campaign_name = f"TEST_RunCmp_{uuid.uuid4().hex[:6]}"
        create_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/campaigns", json={
            "campaign_name": campaign_name,
            "segment_id": segment_id,
            "channel": "in_app",
            "schedule_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "message_title": "Run Now Test",
            "message_body": "Testing run now functionality."
        })
        assert create_response.status_code == 200
        campaign_id = create_response.json().get("campaign", {}).get("campaign_id")
        
        # Run campaign now
        run_response = admin_session.post(f"{BASE_URL}/api/admin/careers/talent-network/campaigns/{campaign_id}/run-now")
        assert run_response.status_code == 200, f"Expected 200, got {run_response.status_code}: {run_response.text[:300]}"
        
        data = run_response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "run" in data, "Response should contain run details"
        
        run = data["run"]
        assert "run_id" in run, "Run should have run_id"
        assert "attempted" in run, "Run should have attempted count"
        assert "sent" in run, "Run should have sent count"
        assert "skipped" in run, "Run should have skipped count"
        assert "failed" in run, "Run should have failed count"
        
        print(f"Campaign run completed: {run.get('run_id')} - attempted={run.get('attempted')}, sent={run.get('sent')}, skipped={run.get('skipped')}, failed={run.get('failed')}")


class TestTalentNetworkMemberReminderTimeline:
    """Test member reminder timeline UX"""

    @pytest.fixture(scope="class")
    def joined_member_email(self, api_client):
        """Create a joined member for timeline tests"""
        email = f"tn.timeline.{uuid.uuid4().hex[:8]}@example.com"
        join_response = api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "full_name": "Timeline Test User",
            "role_interests": ["Engineering"],
            "locations": ["Remote"],
            "work_types": ["Full-time"],
            "alert_frequency": "weekly",
            "reminder_channels": ["in_app", "email"],
            "quiet_hours_start_hour": 22,
            "quiet_hours_end_hour": 7,
            "consent_marketing": True,
            "source": "test_p1_timeline"
        })
        assert join_response.status_code == 200, f"Join failed: {join_response.text[:200]}"
        return email

    def test_reminder_timeline_loads(self, api_client, joined_member_email):
        """Reminder timeline loads for joined user"""
        response = api_client.get(f"{BASE_URL}/api/careers/talent-network/reminder-timeline?email={joined_member_email}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert "timeline" in data, "Response should contain timeline"
        
        timeline = data["timeline"]
        assert timeline.get("email") == joined_member_email, "Email should match"
        assert "next_reminder_eta" in timeline, "Timeline should have next_reminder_eta"
        assert "snoozed_until" in timeline, "Timeline should have snoozed_until"
        assert "last_digest_sent_at" in timeline, "Timeline should have last_digest_sent_at"
        assert "history" in timeline, "Timeline should have history list"
        assert "alert_frequency" in timeline, "Timeline should have alert_frequency"
        assert "reminder_channels" in timeline, "Timeline should have reminder_channels"
        
        print(f"Timeline loaded: next_eta={timeline.get('next_reminder_eta')}, snoozed={timeline.get('snoozed_until')}")

    def test_snooze_1h_action(self, api_client, joined_member_email):
        """Snooze 1h action returns success and updates timeline"""
        response = api_client.post(f"{BASE_URL}/api/careers/talent-network/reminder-action", json={
            "email": joined_member_email,
            "action": "snooze",
            "snooze_hours": 1,
            "note": "Test snooze 1h"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert data.get("action") == "snooze", "Action should be snooze"
        assert "snoozed_until" in data, "Response should have snoozed_until"
        assert data.get("snoozed_until") is not None, "snoozed_until should not be None"
        
        print(f"Snooze 1h: snoozed_until={data.get('snoozed_until')}")

    def test_snooze_6h_action(self, api_client, joined_member_email):
        """Snooze 6h action returns success"""
        response = api_client.post(f"{BASE_URL}/api/careers/talent-network/reminder-action", json={
            "email": joined_member_email,
            "action": "snooze",
            "snooze_hours": 6,
            "note": "Test snooze 6h"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert data.get("action") == "snooze", "Action should be snooze"
        print(f"Snooze 6h: snoozed_until={data.get('snoozed_until')}")

    def test_snooze_24h_action(self, api_client, joined_member_email):
        """Snooze 24h action returns success"""
        response = api_client.post(f"{BASE_URL}/api/careers/talent-network/reminder-action", json={
            "email": joined_member_email,
            "action": "snooze",
            "snooze_hours": 24,
            "note": "Test snooze 24h"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        print(f"Snooze 24h: snoozed_until={data.get('snoozed_until')}")

    def test_resume_now_action(self, api_client, joined_member_email):
        """Resume now action clears snooze and updates timeline"""
        response = api_client.post(f"{BASE_URL}/api/careers/talent-network/reminder-action", json={
            "email": joined_member_email,
            "action": "resume",
            "snooze_hours": 1,  # ignored for resume
            "note": "Test resume"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        assert data.get("success") is True, "Response should indicate success"
        assert data.get("action") == "resume", "Action should be resume"
        assert data.get("snoozed_until") is None, "snoozed_until should be None after resume"
        
        print(f"Resume: next_eta={data.get('next_reminder_eta')}")

    def test_timeline_history_populated(self, api_client, joined_member_email):
        """Timeline history shows recent actions"""
        response = api_client.get(f"{BASE_URL}/api/careers/talent-network/reminder-timeline?email={joined_member_email}")
        assert response.status_code == 200
        
        timeline = response.json().get("timeline", {})
        history = timeline.get("history", [])
        
        # Should have history from snooze/resume actions
        assert len(history) > 0, "History should have entries from previous actions"
        
        # Check history entry structure
        if history:
            entry = history[0]
            assert "event_id" in entry, "History entry should have event_id"
            assert "event_type" in entry, "History entry should have event_type"
            assert "created_at" in entry, "History entry should have created_at"
        
        print(f"Timeline history has {len(history)} entries")


class TestTalentNetworkRegressionChecks:
    """Regression checks for existing Talent Network functionality"""

    def test_join_flow_still_works(self, api_client):
        """Join flow still works"""
        email = f"tn.regression.{uuid.uuid4().hex[:8]}@example.com"
        response = api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "full_name": "Regression Test",
            "role_interests": ["Product"],
            "alert_frequency": "daily",
            "source": "regression_test"
        })
        assert response.status_code == 200, f"Join failed: {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert data.get("success") is True
        assert "network_id" in data
        print(f"Join regression: network_id={data.get('network_id')}")

    def test_hub_loads_for_member(self, api_client):
        """Hub loads for joined member"""
        email = f"tn.hub.{uuid.uuid4().hex[:8]}@example.com"
        # Join first
        join_response = api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "full_name": "Hub Test",
            "source": "hub_test"
        })
        assert join_response.status_code == 200
        
        # Load hub
        hub_response = api_client.get(f"{BASE_URL}/api/careers/talent-network/hub?email={email}")
        assert hub_response.status_code == 200, f"Hub load failed: {hub_response.status_code}: {hub_response.text[:200]}"
        
        data = hub_response.json()
        assert data.get("success") is True
        assert "member" in data
        assert "state" in data
        assert "top_matches" in data
        print(f"Hub regression: profile_completeness={data.get('state', {}).get('profile_completeness')}")

    def test_referral_share_still_works(self, api_client):
        """Referral share still works"""
        email = f"tn.share.{uuid.uuid4().hex[:8]}@example.com"
        # Join first
        api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "source": "share_test"
        })
        
        # Share
        share_response = api_client.post(f"{BASE_URL}/api/careers/talent-network/referral/share", json={
            "email": email,
            "channel": "copy_link",
            "source": "share_test"
        })
        assert share_response.status_code == 200, f"Share failed: {share_response.status_code}: {share_response.text[:200]}"
        
        data = share_response.json()
        assert data.get("success") is True
        assert "referral_code" in data
        print(f"Share regression: referral_code={data.get('referral_code')}")

    def test_check_in_still_works(self, api_client):
        """Check-in still works"""
        email = f"tn.checkin.{uuid.uuid4().hex[:8]}@example.com"
        # Join first
        api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "source": "checkin_test"
        })
        
        # Check in
        checkin_response = api_client.post(f"{BASE_URL}/api/careers/talent-network/check-in", json={
            "email": email,
            "action": "daily_visit",
            "source": "checkin_test"
        })
        assert checkin_response.status_code == 200, f"Check-in failed: {checkin_response.status_code}: {checkin_response.text[:200]}"
        
        data = checkin_response.json()
        assert data.get("success") is True
        assert "momentum" in data
        print(f"Check-in regression: streak={data.get('momentum', {}).get('current_streak')}")


class TestObjectIdSerialization:
    """Test ObjectId serialization safety"""

    def test_admin_overview_no_objectid(self, admin_session):
        """Admin overview response has no MongoDB _id fields"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=7")
        assert response.status_code == 200
        
        text = response.text
        assert '"_id"' not in text, "Response should not contain _id field"
        assert "'_id'" not in text, "Response should not contain _id field"

    def test_segments_list_no_objectid(self, admin_session):
        """Segments list response has no MongoDB _id fields"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/segments")
        assert response.status_code == 200
        
        text = response.text
        assert '"_id"' not in text, "Response should not contain _id field"

    def test_campaigns_list_no_objectid(self, admin_session):
        """Campaigns list response has no MongoDB _id fields"""
        response = admin_session.get(f"{BASE_URL}/api/admin/careers/talent-network/campaigns")
        assert response.status_code == 200
        
        text = response.text
        assert '"_id"' not in text, "Response should not contain _id field"

    def test_reminder_timeline_no_objectid(self, api_client):
        """Reminder timeline response has no MongoDB _id fields"""
        email = f"tn.oid.{uuid.uuid4().hex[:8]}@example.com"
        api_client.post(f"{BASE_URL}/api/careers/talent-network/join", json={
            "email": email,
            "source": "oid_test"
        })
        
        response = api_client.get(f"{BASE_URL}/api/careers/talent-network/reminder-timeline?email={email}")
        assert response.status_code == 200
        
        text = response.text
        assert '"_id"' not in text, "Response should not contain _id field"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
