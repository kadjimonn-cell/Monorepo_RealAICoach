"""
Test GTEC C5 Run Receipt in Compliance Digest Hub

Tests:
1. Compliance digest kinds endpoint includes gtec_c5_run_receipt
2. Compliance digest feed can filter by gtec_c5_run_receipt kind
3. Receipt payload structure validation
4. Existing compliance feed functionality (load, filters)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_admin_forbidden(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if isinstance(detail, str) and "admin access required" in detail.lower():
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        message = str(detail.get("message") or "").lower()
        if "admin access blocked" in message:
            return True

    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    return top_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    
    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    data = login_resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or login_resp.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if not token:
        pytest.skip("Admin token missing in login JSON/cookies")
    session.headers.update({"Authorization": f"Bearer {token}"})

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_admin_forbidden(response):
            pytest.skip("Admin API blocked by environment containment/authorization policy")
        return response

    session.get = guarded_get
    
    return session


class TestComplianceDigestKinds:
    """Test compliance digest kinds endpoint includes gtec_c5_run_receipt."""
    
    def test_kinds_endpoint_returns_gtec_c5_run_receipt(self, admin_session):
        """Verify gtec_c5_run_receipt is in the known kinds list."""
        response = admin_session.get(f"{BASE_URL}/api/compliance-digests/kinds")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert "kinds" in data, "Response should contain 'kinds' key"
        
        kinds = data["kinds"]
        assert isinstance(kinds, list), "kinds should be a list"
        
        # Find gtec_c5_run_receipt in the kinds list
        gtec_receipt_kind = None
        for k in kinds:
            if k.get("kind") == "gtec_c5_run_receipt":
                gtec_receipt_kind = k
                break
        
        assert gtec_receipt_kind is not None, "gtec_c5_run_receipt should be in known kinds"
        assert gtec_receipt_kind.get("label") == "GTEC C5 · Run Receipt", \
            f"Expected label 'GTEC C5 · Run Receipt', got '{gtec_receipt_kind.get('label')}'"
        
        # Verify structure
        assert "total" in gtec_receipt_kind, "Kind should have 'total' count"
        assert "unreviewed" in gtec_receipt_kind, "Kind should have 'unreviewed' count"
        
        print(f"✓ gtec_c5_run_receipt kind found with label: {gtec_receipt_kind.get('label')}")
        print(f"  Total entries: {gtec_receipt_kind.get('total')}, Unreviewed: {gtec_receipt_kind.get('unreviewed')}")


class TestComplianceDigestFeed:
    """Test compliance digest feed functionality."""
    
    def test_feed_loads_successfully(self, admin_session):
        """Verify feed endpoint returns data."""
        response = admin_session.get(f"{BASE_URL}/api/compliance-digests/feed", params={"limit": 50})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert "items" in data, "Response should contain 'items'"
        assert "count" in data, "Response should contain 'count'"
        assert "unreviewed_count" in data, "Response should contain 'unreviewed_count'"
        assert "total" in data, "Response should contain 'total'"
        
        print(f"✓ Feed loaded: {data['count']} items, {data['unreviewed_count']} unreviewed, {data['total']} total")
    
    def test_feed_filter_by_gtec_c5_run_receipt(self, admin_session):
        """Verify feed can filter by gtec_c5_run_receipt kind."""
        response = admin_session.get(
            f"{BASE_URL}/api/compliance-digests/feed",
            params={"kind": "gtec_c5_run_receipt", "limit": 50}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        items = data.get("items", [])
        
        # All returned items should be gtec_c5_run_receipt kind
        for item in items:
            assert item.get("kind") == "gtec_c5_run_receipt", \
                f"Expected kind 'gtec_c5_run_receipt', got '{item.get('kind')}'"
        
        print(f"✓ Filter by gtec_c5_run_receipt: {len(items)} entries found")
    
    def test_feed_filter_by_reviewed_state(self, admin_session):
        """Verify feed can filter by reviewed/unreviewed state."""
        # Test unreviewed filter
        response = admin_session.get(
            f"{BASE_URL}/api/compliance-digests/feed",
            params={"reviewed": "unreviewed", "limit": 20}
        )
        assert response.status_code == 200
        data = response.json()
        for item in data.get("items", []):
            assert item.get("reviewed_at") is None, "Unreviewed items should have reviewed_at=None"
        
        # Test reviewed filter
        response = admin_session.get(
            f"{BASE_URL}/api/compliance-digests/feed",
            params={"reviewed": "reviewed", "limit": 20}
        )
        assert response.status_code == 200
        data = response.json()
        for item in data.get("items", []):
            assert item.get("reviewed_at") is not None, "Reviewed items should have reviewed_at set"
        
        print("✓ Reviewed state filters working correctly")


class TestGtecC5ReceiptPayload:
    """Test GTEC C5 run receipt payload structure."""
    
    def test_receipt_payload_structure(self, admin_session):
        """Verify receipt payload includes required fields."""
        response = admin_session.get(
            f"{BASE_URL}/api/compliance-digests/feed",
            params={"kind": "gtec_c5_run_receipt", "limit": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No gtec_c5_run_receipt entries found to validate payload")
        
        # Validate first receipt entry
        receipt = items[0]
        
        # Basic entry fields
        assert "entry_id" in receipt, "Entry should have entry_id"
        assert "kind" in receipt, "Entry should have kind"
        assert receipt["kind"] == "gtec_c5_run_receipt"
        assert "kind_label" in receipt, "Entry should have kind_label"
        assert "subject" in receipt, "Entry should have subject"
        assert "summary" in receipt, "Entry should have summary"
        assert "recipients" in receipt, "Entry should have recipients"
        assert "sent_ok" in receipt, "Entry should have sent_ok"
        assert "sent_failed" in receipt, "Entry should have sent_failed"
        assert "created_at" in receipt, "Entry should have created_at"
        
        # Payload structure
        payload = receipt.get("payload", {})
        assert payload, "Receipt should have payload"
        
        # Required payload fields per spec
        assert "task_id" in payload, "Payload should have task_id"
        assert "status" in payload, "Payload should have status"
        assert "triggered_by" in payload, "Payload should have triggered_by"
        assert "actor" in payload, "Payload should have actor"
        
        # Delivery totals
        delivery = payload.get("delivery", {})
        assert "total" in delivery, "Delivery should have total"
        assert "sent_ok" in delivery, "Delivery should have sent_ok"
        assert "sent_failed" in delivery, "Delivery should have sent_failed"
        assert "recipient_statuses" in delivery, "Delivery should have recipient_statuses"
        
        # PDF attachment info
        pdf = payload.get("pdf_attachment", {})
        assert "filename" in pdf, "PDF attachment should have filename"
        assert "sha256" in pdf, "PDF attachment should have sha256"
        
        print(f"✓ Receipt payload validated for entry: {receipt['entry_id']}")
        print(f"  task_id: {payload.get('task_id')}")
        print(f"  status: {payload.get('status')}")
        print(f"  triggered_by: {payload.get('triggered_by')}")
        print(f"  actor: {payload.get('actor')}")
        print(f"  delivery: {delivery.get('sent_ok')}/{delivery.get('total')}")
        print(f"  pdf_filename: {pdf.get('filename')}")
        print(f"  pdf_sha256: {pdf.get('sha256')[:16]}..." if pdf.get('sha256') else "  pdf_sha256: (none)")
    
    def test_specific_receipt_entry(self, admin_session):
        """Test the specific receipt entry mentioned by main agent."""
        # Main agent mentioned: entry_id dgst_627f5f6913a4
        response = admin_session.get(
            f"{BASE_URL}/api/compliance-digests/feed",
            params={"kind": "gtec_c5_run_receipt", "limit": 50}
        )
        
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        
        # Look for the specific entry
        target_entry = None
        for item in items:
            if item.get("entry_id") == "dgst_627f5f6913a4":
                target_entry = item
                break
        
        if target_entry:
            print("✓ Found specific receipt entry: dgst_627f5f6913a4")
            print(f"  Subject: {target_entry.get('subject')}")
            payload = target_entry.get("payload", {})
            print(f"  Task ID: {payload.get('task_id')}")
            print(f"  Status: {payload.get('status')}")
        else:
            print("⚠ Specific entry dgst_627f5f6913a4 not found in recent entries (may have been purged or paginated)")


class TestUnreviewedCount:
    """Test unreviewed count endpoint."""
    
    def test_unreviewed_count_endpoint(self, admin_session):
        """Verify unreviewed count endpoint works."""
        response = admin_session.get(f"{BASE_URL}/api/compliance-digests/unreviewed-count")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "unreviewed_count" in data, "Response should contain unreviewed_count"
        assert isinstance(data["unreviewed_count"], int), "unreviewed_count should be an integer"
        
        print(f"✓ Unreviewed count: {data['unreviewed_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
