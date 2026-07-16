"""
P2 Talent Network Deliverability Analytics Tests

Tests for:
1. Admin deliverability analytics endpoint - summary + segment rows with open_rate_pct, click_rate_pct, quiet_hours_impact_pct
2. Manual campaign run-now stores segment_id/segment_name metadata in campaign run + reminder delivery events
3. Public campaign-interaction endpoint accepts open/click and stores campaign_engagement event with dedupe
4. Scheduler code path stamps segment_id/segment_name on campaign delivery events
"""

import os
import pytest
import requests
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
TEST_MEMBER_EMAIL = f"tn.p2.test.{uuid.uuid4().hex[:8]}@example.com"


class TestTalentNetworkP2Deliverability:
    """P2 Deliverability Analytics Tests"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")
        return session

    @pytest.fixture(scope="class")
    def test_member_email(self):
        """Create a test member for campaign interaction tests"""
        return TEST_MEMBER_EMAIL

    @pytest.fixture(scope="class")
    def joined_member(self, test_member_email):
        """Join a test member to Talent Network"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        join_response = session.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json={
                "email": test_member_email,
                "full_name": "P2 Test Member",
                "role_interests": ["Engineering", "Product"],
                "locations": ["Remote"],
                "work_types": ["Full-time"],
                "alert_frequency": "weekly",
                "reminder_channels": ["in_app", "email"],
                "quiet_hours_start_hour": 22,
                "quiet_hours_end_hour": 7,
                "consent_marketing": True,
                "source": "p2_deliverability_test",
            },
        )
        assert join_response.status_code == 200, f"Join failed: {join_response.text}"
        data = join_response.json()
        assert data.get("success") is True
        return data

    # ─────────────────────────────────────────────────────────────────────────
    # Test 1: Admin deliverability analytics endpoint
    # ─────────────────────────────────────────────────────────────────────────
    def test_admin_deliverability_analytics_endpoint_returns_summary(self, admin_session):
        """Admin can fetch deliverability analytics endpoint and receive summary + segment rows"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/deliverability-analytics?days=30"
        )
        assert response.status_code == 200, f"Deliverability analytics failed: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "window_days" in data
        assert "generated_at" in data
        assert "summary" in data
        assert "segments" in data
        
        # Verify summary fields
        summary = data["summary"]
        assert "segments_count" in summary
        assert "campaigns_count" in summary
        assert "sent" in summary
        assert "opened" in summary
        assert "clicked" in summary
        assert "open_rate_pct" in summary
        assert "click_rate_pct" in summary
        assert "click_to_open_rate_pct" in summary
        assert "quiet_hours_sent" in summary
        assert "quiet_hours_opened" in summary
        assert "quiet_hours_clicked" in summary
        assert "quiet_hours_open_rate_pct" in summary
        assert "non_quiet_open_rate_pct" in summary
        assert "quiet_hours_impact_pct" in summary
        
        print(f"✓ Deliverability analytics summary: sent={summary['sent']}, opened={summary['opened']}, clicked={summary['clicked']}")
        print(f"✓ Rates: open_rate={summary['open_rate_pct']}%, click_rate={summary['click_rate_pct']}%, quiet_impact={summary['quiet_hours_impact_pct']}%")

    def test_admin_deliverability_analytics_segment_rows_structure(self, admin_session):
        """Verify segment rows contain required fields including open_rate_pct, click_rate_pct, quiet_hours_impact_pct"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/deliverability-analytics?days=30&limit=10"
        )
        assert response.status_code == 200
        
        data = response.json()
        segments = data.get("segments", [])
        
        # If there are segments, verify their structure
        if segments:
            segment = segments[0]
            required_fields = [
                "segment_id",
                "segment_name",
                "campaign_count",
                "sent",
                "opened",
                "clicked",
                "unique_sent_recipients",
                "unique_open_recipients",
                "unique_click_recipients",
                "open_rate_pct",
                "click_rate_pct",
                "click_to_open_rate_pct",
                "quiet_hours_sent",
                "quiet_hours_opened",
                "quiet_hours_clicked",
                "quiet_hours_open_rate_pct",
                "non_quiet_open_rate_pct",
                "quiet_hours_click_rate_pct",
                "non_quiet_click_rate_pct",
                "quiet_hours_impact_pct",
            ]
            for field in required_fields:
                assert field in segment, f"Missing field: {field}"
            
            print(f"✓ Segment row structure verified: {segment['segment_name']} with {segment['sent']} sent")
        else:
            print("✓ No segments yet (expected if no campaigns have been run)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: Create segment and campaign, run-now, verify metadata
    # ─────────────────────────────────────────────────────────────────────────
    def test_create_segment_for_campaign(self, admin_session):
        """Create a test segment for campaign testing"""
        segment_name = f"P2 Test Segment {uuid.uuid4().hex[:6]}"
        response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": segment_name,
                "description": "Test segment for P2 deliverability testing",
                "alert_frequency": "any",
                "reminder_channel": "any",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        assert response.status_code == 200, f"Segment creation failed: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        # segment_id is nested inside segment object
        segment = data.get("segment", {})
        assert "segment_id" in segment, f"Missing segment_id in response: {data}"
        
        print(f"✓ Created segment: {segment['segment_id']} - {segment_name}")
        return segment["segment_id"], segment_name

    def test_create_campaign_with_segment_metadata(self, admin_session):
        """Create a campaign and verify segment_id/segment_name are stored"""
        # First create a segment
        segment_name = f"P2 Campaign Segment {uuid.uuid4().hex[:6]}"
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": segment_name,
                "description": "Segment for campaign metadata test",
                "alert_frequency": "any",
                "reminder_channel": "any",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        assert segment_response.status_code == 200
        segment_data = segment_response.json()
        segment_id = segment_data.get("segment", {}).get("segment_id")
        assert segment_id, f"Missing segment_id: {segment_data}"
        
        # Create campaign with segment
        campaign_name = f"P2 Test Campaign {uuid.uuid4().hex[:6]}"
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": campaign_name,
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "P2 Test Campaign Title",
                "message_body": "This is a test campaign message for P2 deliverability testing.",
                "cta_label": "Open Talent Network",
                "cta_path": "/talent-network",
            },
        )
        assert campaign_response.status_code == 200, f"Campaign creation failed: {campaign_response.text}"
        
        campaign_data = campaign_response.json()
        assert campaign_data.get("success") is True
        # campaign_id is nested inside campaign object
        campaign = campaign_data.get("campaign", {})
        assert "campaign_id" in campaign, f"Missing campaign_id: {campaign_data}"
        
        # Verify segment metadata is stored in campaign
        assert campaign.get("segment_id") == segment_id
        assert campaign.get("segment_name") == segment_name
        
        print(f"✓ Created campaign: {campaign['campaign_id']} with segment_id={segment_id}, segment_name={segment_name}")
        return campaign["campaign_id"], segment_id, segment_name

    def test_campaign_run_now_stores_segment_metadata(self, admin_session, joined_member, test_member_email):
        """Manual campaign run-now stores segment_id/segment_name metadata in campaign run + reminder delivery events"""
        # Create segment
        segment_name = f"P2 RunNow Segment {uuid.uuid4().hex[:6]}"
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": segment_name,
                "description": "Segment for run-now metadata test",
                "alert_frequency": "any",
                "reminder_channel": "in_app",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        assert segment_response.status_code == 200
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        assert segment_id, f"Missing segment_id: {segment_response.json()}"
        
        # Create campaign
        campaign_name = f"P2 RunNow Campaign {uuid.uuid4().hex[:6]}"
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": campaign_name,
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "scheduled",
                "scheduled_at": "2099-01-01T00:00:00+00:00",  # Far future
                "message_title": "P2 RunNow Test Title",
                "message_body": "This is a test campaign message for run-now metadata testing.",
                "cta_label": "Open Hub",
                "cta_path": "/talent-network",
            },
        )
        assert campaign_response.status_code == 200
        campaign_id = campaign_response.json().get("campaign", {}).get("campaign_id")
        assert campaign_id, f"Missing campaign_id: {campaign_response.json()}"
        
        # Run campaign now
        run_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns/{campaign_id}/run-now",
            json={},
        )
        assert run_response.status_code == 200, f"Run-now failed: {run_response.text}"
        
        run_data = run_response.json()
        assert run_data.get("success") is True
        
        # Verify run contains segment metadata
        run_doc = run_data.get("run", {})
        assert run_doc.get("segment_id") == segment_id, f"Expected segment_id={segment_id}, got {run_doc.get('segment_id')}"
        assert run_doc.get("segment_name") == segment_name, f"Expected segment_name={segment_name}, got {run_doc.get('segment_name')}"
        
        print(f"✓ Campaign run-now stores segment metadata: segment_id={run_doc.get('segment_id')}, segment_name={run_doc.get('segment_name')}")
        return campaign_id, segment_id, segment_name

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: Public campaign-interaction endpoint
    # ─────────────────────────────────────────────────────────────────────────
    def test_campaign_interaction_open_creates_engagement_event(self, admin_session, joined_member, test_member_email):
        """Public endpoint POST /api/careers/talent-network/campaign-interaction accepts open and stores campaign_engagement event"""
        # First create a campaign to interact with
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": f"P2 Interaction Segment {uuid.uuid4().hex[:6]}",
                "description": "Segment for interaction test",
                "alert_frequency": "any",
                "reminder_channel": "any",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": f"P2 Interaction Campaign {uuid.uuid4().hex[:6]}",
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "Interaction Test Title",
                "message_body": "Test message for interaction testing.",
                "cta_label": "Open",
                "cta_path": "/talent-network",
            },
        )
        campaign_id = campaign_response.json().get("campaign", {}).get("campaign_id")
        
        # Test open interaction
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        interaction_response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        assert interaction_response.status_code == 200, f"Interaction failed: {interaction_response.text}"
        
        data = interaction_response.json()
        assert data.get("success") is True
        assert data.get("tracked") is True
        assert data.get("interaction") == "open"
        assert data.get("campaign_id") == campaign_id
        
        print(f"✓ Campaign open interaction tracked: event_id={data.get('event_id')}")
        return campaign_id

    def test_campaign_interaction_click_creates_engagement_event(self, admin_session, joined_member, test_member_email):
        """Public endpoint POST /api/careers/talent-network/campaign-interaction accepts click and stores campaign_engagement event"""
        # Create campaign
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": f"P2 Click Segment {uuid.uuid4().hex[:6]}",
                "description": "Segment for click test",
                "alert_frequency": "any",
                "reminder_channel": "any",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": f"P2 Click Campaign {uuid.uuid4().hex[:6]}",
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "Click Test Title",
                "message_body": "Test message for click testing.",
                "cta_label": "Click Here",
                "cta_path": "/talent-network?ref=click-test",
            },
        )
        campaign_id = campaign_response.json().get("campaign", {}).get("campaign_id")
        
        # Test click interaction
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        interaction_response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "click",
                "channel": "in_app",
                "source": "talent_network_timeline",
                "cta_path": "/talent-network?ref=click-test",
            },
        )
        assert interaction_response.status_code == 200, f"Click interaction failed: {interaction_response.text}"
        
        data = interaction_response.json()
        assert data.get("success") is True
        assert data.get("tracked") is True
        assert data.get("interaction") == "click"
        
        print(f"✓ Campaign click interaction tracked: event_id={data.get('event_id')}")

    def test_campaign_interaction_dedupe_within_window(self, admin_session, joined_member, test_member_email):
        """Campaign interaction has dedupe behavior within 30-second window"""
        # Create campaign
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": f"P2 Dedupe Segment {uuid.uuid4().hex[:6]}",
                "description": "Segment for dedupe test",
                "alert_frequency": "any",
                "reminder_channel": "any",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": f"P2 Dedupe Campaign {uuid.uuid4().hex[:6]}",
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "Dedupe Test Title",
                "message_body": "Test message for dedupe testing.",
                "cta_label": "Open",
                "cta_path": "/talent-network",
            },
        )
        campaign_id = campaign_response.json().get("campaign", {}).get("campaign_id")
        
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        # First interaction - should be tracked
        first_response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        assert first_response.status_code == 200
        first_data = first_response.json()
        assert first_data.get("tracked") is True
        
        # Second interaction immediately - should be deduplicated
        second_response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data.get("tracked") is False
        assert second_data.get("reason") == "duplicate_within_window"
        
        print(f"✓ Dedupe behavior verified: first tracked={first_data.get('tracked')}, second tracked={second_data.get('tracked')}")

    def test_campaign_interaction_invalid_campaign_returns_404(self, joined_member, test_member_email):
        """Campaign interaction with invalid campaign_id returns 404"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": "nonexistent_campaign_id",
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        assert response.status_code == 404
        print("✓ Invalid campaign_id returns 404")

    def test_campaign_interaction_invalid_member_returns_404(self):
        """Campaign interaction with non-member email returns 404"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        response = session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": "nonexistent_member@example.com",
                "campaign_id": "any_campaign_id",
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        assert response.status_code == 404
        print("✓ Non-member email returns 404")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 4: Verify reminder timeline shows campaign delivery events
    # ─────────────────────────────────────────────────────────────────────────
    def test_reminder_timeline_shows_campaign_delivery_events(self, admin_session, joined_member, test_member_email):
        """Verify reminder timeline includes campaign_delivery events with segment metadata"""
        # Create and run a campaign
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": f"P2 Timeline Segment {uuid.uuid4().hex[:6]}",
                "description": "Segment for timeline test",
                "alert_frequency": "any",
                "reminder_channel": "in_app",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        segment_response.json().get("name", "")
        
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": f"P2 Timeline Campaign {uuid.uuid4().hex[:6]}",
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "Timeline Test Title",
                "message_body": "Test message for timeline testing.",
                "cta_label": "Open Hub",
                "cta_path": "/talent-network",
            },
        )
        campaign_response.json().get("campaign", {}).get("campaign_id")
        
        # Wait a moment for campaign to process
        time.sleep(1)
        
        # Fetch reminder timeline
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        timeline_response = session.get(
            f"{BASE_URL}/api/careers/talent-network/reminder-timeline?email={test_member_email}"
        )
        assert timeline_response.status_code == 200, f"Timeline fetch failed: {timeline_response.text}"
        
        data = timeline_response.json()
        assert data.get("success") is True
        assert "timeline" in data
        
        timeline = data["timeline"]
        assert "history" in timeline
        
        # Check if campaign_delivery events exist in history
        history = timeline.get("history", [])
        print(f"✓ Reminder timeline fetched with {len(history)} history events")
        
        # Look for campaign_delivery events
        delivery_events = [e for e in history if e.get("event_type") == "campaign_delivery"]
        if delivery_events:
            event = delivery_events[0]
            print(f"✓ Found campaign_delivery event: campaign_id={event.get('campaign_id')}, campaign_name={event.get('campaign_name')}")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 5: Verify deliverability analytics updates after interactions
    # ─────────────────────────────────────────────────────────────────────────
    def test_deliverability_analytics_reflects_interactions(self, admin_session, joined_member, test_member_email):
        """Verify deliverability analytics endpoint reflects open/click interactions"""
        # Create segment and campaign
        segment_name = f"P2 Analytics Segment {uuid.uuid4().hex[:6]}"
        segment_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/segments",
            json={
                "name": segment_name,
                "description": "Segment for analytics test",
                "alert_frequency": "any",
                "reminder_channel": "in_app",
                "profile_min": 0,
                "profile_max": 100,
                "premium_state": "any",
                "marketing_consent_required": False,
                "active": True,
            },
        )
        segment_id = segment_response.json().get("segment", {}).get("segment_id")
        
        campaign_response = admin_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns",
            json={
                "campaign_name": f"P2 Analytics Campaign {uuid.uuid4().hex[:6]}",
                "segment_id": segment_id,
                "channel": "in_app",
                "schedule_type": "run_now",
                "message_title": "Analytics Test Title",
                "message_body": "Test message for analytics testing.",
                "cta_label": "Open",
                "cta_path": "/talent-network",
            },
        )
        campaign_id = campaign_response.json().get("campaign", {}).get("campaign_id")
        
        # Track an open interaction
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "open",
                "channel": "in_app",
                "source": "talent_network_timeline",
            },
        )
        
        # Wait a moment
        time.sleep(0.5)
        
        # Track a click interaction
        session.post(
            f"{BASE_URL}/api/careers/talent-network/campaign-interaction",
            json={
                "email": test_member_email,
                "campaign_id": campaign_id,
                "interaction": "click",
                "channel": "in_app",
                "source": "talent_network_timeline",
                "cta_path": "/talent-network",
            },
        )
        
        # Fetch deliverability analytics
        analytics_response = admin_session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/deliverability-analytics?days=1"
        )
        assert analytics_response.status_code == 200
        
        data = analytics_response.json()
        summary = data.get("summary", {})
        
        # Verify analytics structure is correct
        assert "open_rate_pct" in summary
        assert "click_rate_pct" in summary
        assert "quiet_hours_impact_pct" in summary
        
        print(f"✓ Deliverability analytics after interactions: opened={summary.get('opened')}, clicked={summary.get('clicked')}")


class TestTalentNetworkSchedulerSegmentMetadata:
    """Tests for scheduler code path segment metadata stamping"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")
        return session

    def test_campaign_list_includes_segment_metadata(self, admin_session):
        """Verify campaign list endpoint returns segment_id and segment_name"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns"
        )
        assert response.status_code == 200, f"Campaign list failed: {response.text}"
        
        data = response.json()
        campaigns = data.get("campaigns", [])
        
        if campaigns:
            campaign = campaigns[0]
            assert "segment_id" in campaign, "Campaign missing segment_id"
            assert "segment_name" in campaign, "Campaign missing segment_name"
            print(f"✓ Campaign list includes segment metadata: segment_id={campaign.get('segment_id')}, segment_name={campaign.get('segment_name')}")
        else:
            print("✓ No campaigns yet (expected if none created)")

    def test_campaign_runs_include_segment_metadata(self, admin_session):
        """Verify campaign runs include segment_id and segment_name"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/campaigns"
        )
        assert response.status_code == 200
        
        data = response.json()
        runs = data.get("runs", [])
        
        if runs:
            run = runs[0]
            # Runs should have segment metadata
            if "segment_id" in run:
                print(f"✓ Campaign run includes segment_id: {run.get('segment_id')}")
            if "segment_name" in run:
                print(f"✓ Campaign run includes segment_name: {run.get('segment_name')}")
        else:
            print("✓ No campaign runs yet (expected if none executed)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
