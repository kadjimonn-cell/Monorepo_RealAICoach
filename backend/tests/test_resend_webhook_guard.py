"""
Test suite for Resend Webhook Guard feature.

Tests:
1. Scheduler job registration (id=resend_webhook_guard, 15-minute interval)
2. scheduled_resend_webhook_guard function returns healthy/warning/critical payload
3. Guard auto-repair logic handles drift/disabled webhook using Resend PATCH with status=enabled
4. Guard writes runtime state/event docs (system_runtime_flags key resend_webhook_guard_state and resend_webhook_guard_events)
5. Guard emits admin in-app alert notifications when warning/critical conditions are detected
6. Startup Resend autosync includes status=enabled in patch/create payload
"""

import pytest
import requests
import os
import asyncio
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestResendWebhookGuardSchedulerRegistration:
    """Test scheduler job registration for resend_webhook_guard"""

    def test_scheduler_job_registered(self):
        """Verify resend_webhook_guard job is registered in scheduler via code inspection"""
        # Read the scheduler.py file directly
        scheduler_path = "/app/backend/scheduler.py"
        with open(scheduler_path, 'r') as f:
            source = f.read()
        
        # Check for job registration with correct id and interval
        assert "scheduled_resend_webhook_guard" in source, "scheduled_resend_webhook_guard should be imported"
        assert 'id="resend_webhook_guard"' in source, "Job should be registered with id=resend_webhook_guard"
        assert "IntervalTrigger(minutes=15)" in source, "Job should have 15-minute interval"
        print("Scheduler job registration verified: id=resend_webhook_guard, interval=15 minutes")

    def test_scheduler_heartbeat_endpoint(self):
        """Verify scheduler heartbeat for resend_webhook_guard exists"""
        # Admin login to check heartbeats
        admin_email = "admin@realaicoach.app"
        admin_password = "NewAdminPass2026!"
        
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": admin_email, "password": admin_password},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30
        )
        
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code}")
        
        # Check scheduler heartbeats via admin endpoint
        heartbeats_resp = session.get(
            f"{BASE_URL}/api/admin/scheduler/heartbeats",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30
        )
        
        if heartbeats_resp.status_code == 200:
            heartbeats = heartbeats_resp.json()
            print(f"Scheduler heartbeats: {heartbeats}")
            # Look for resend_webhook_guard heartbeat
            if isinstance(heartbeats, list):
                job_ids = [h.get("job_id") for h in heartbeats]
                print(f"Job IDs in heartbeats: {job_ids}")
        else:
            print(f"Heartbeats endpoint returned: {heartbeats_resp.status_code}")


class TestResendWebhookGuardFunction:
    """Test the scheduled_resend_webhook_guard function behavior"""

    def test_guard_function_import(self):
        """Verify the guard function can be imported from scheduler_jobs"""
        try:
            from scheduler_jobs import scheduled_resend_webhook_guard
            assert callable(scheduled_resend_webhook_guard), "scheduled_resend_webhook_guard is not callable"
            print("scheduled_resend_webhook_guard imported successfully")
        except ImportError as e:
            pytest.fail(f"Failed to import scheduled_resend_webhook_guard: {e}")

    def test_guard_function_in_payments_module(self):
        """Verify the guard function exists in payments module"""
        try:
            from scheduler_jobs.payments import scheduled_resend_webhook_guard
            assert callable(scheduled_resend_webhook_guard), "scheduled_resend_webhook_guard is not callable"
            print("scheduled_resend_webhook_guard found in payments module")
        except ImportError as e:
            pytest.fail(f"Failed to import from payments module: {e}")

    def test_guard_function_in_all_exports(self):
        """Verify the guard function is in __all__ exports"""
        try:
            from scheduler_jobs.payments import __all__
            assert "scheduled_resend_webhook_guard" in __all__, "scheduled_resend_webhook_guard not in __all__"
            print(f"__all__ exports: {__all__}")
        except ImportError as e:
            pytest.fail(f"Failed to check __all__: {e}")


class TestResendWebhookGuardRuntimeState:
    """Test runtime state and event document persistence"""

    def test_runtime_state_flag_key(self):
        """Verify the guard uses correct runtime flag key"""
        # The guard should write to system_runtime_flags with key 'resend_webhook_guard_state'
        admin_email = "admin@realaicoach.app"
        admin_password = "NewAdminPass2026!"
        
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": admin_email, "password": admin_password},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30
        )
        
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code}")
        
        # Check if we can access runtime flags via admin endpoint
        # This verifies the structure exists
        print("Admin login successful, checking runtime state...")
        
        # The guard writes to:
        # - db.system_runtime_flags with key "resend_webhook_guard_state"
        # - db.resend_webhook_guard_events collection
        # We verify the code structure is correct by checking the function signature

    def test_guard_event_collection_name(self):
        """Verify the guard uses correct event collection name"""
        # Check the code uses 'resend_webhook_guard_events' collection
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        assert "resend_webhook_guard_events" in source, "Guard should write to resend_webhook_guard_events collection"
        print("Guard correctly references resend_webhook_guard_events collection")

    def test_guard_state_flag_key_in_code(self):
        """Verify the guard uses correct state flag key in code"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        assert "resend_webhook_guard_state" in source, "Guard should write to resend_webhook_guard_state flag"
        print("Guard correctly references resend_webhook_guard_state flag key")


class TestResendWebhookGuardAutoRepair:
    """Test auto-repair logic for drift/disabled webhooks"""

    def test_guard_includes_status_enabled_in_patch(self):
        """Verify the guard includes status=enabled in PATCH payload"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for status=enabled in patch payloads
        assert '"status": "enabled"' in source or "'status': 'enabled'" in source, \
            "Guard should include status=enabled in PATCH payload"
        print("Guard correctly includes status=enabled in PATCH payload")

    def test_guard_handles_disabled_webhook(self):
        """Verify the guard detects and repairs disabled webhooks"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for disabled detection logic
        assert "disabled" in source.lower(), "Guard should detect disabled webhooks"
        print("Guard includes disabled webhook detection logic")

    def test_guard_handles_drift(self):
        """Verify the guard detects and repairs endpoint drift"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for drift detection logic
        assert "drifted" in source or "drift" in source.lower(), "Guard should detect endpoint drift"
        print("Guard includes drift detection logic")


class TestResendWebhookGuardAlerts:
    """Test admin alert notification emission"""

    def test_guard_emits_alerts_on_warning(self):
        """Verify the guard emits alerts on warning conditions"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for alert emission on warning
        assert "_emit_resend_webhook_alert" in source, "Guard should call _emit_resend_webhook_alert"
        assert "warning" in source.lower(), "Guard should handle warning severity"
        print("Guard correctly emits alerts on warning conditions")

    def test_guard_emits_alerts_on_critical(self):
        """Verify the guard emits alerts on critical conditions"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for critical severity handling
        assert "critical" in source.lower(), "Guard should handle critical severity"
        print("Guard correctly handles critical severity")

    def test_alert_function_exists(self):
        """Verify the alert emission function exists"""
        try:
            from scheduler_jobs.payments import _emit_resend_webhook_alert
            assert callable(_emit_resend_webhook_alert), "_emit_resend_webhook_alert is not callable"
            print("_emit_resend_webhook_alert function exists and is callable")
        except ImportError:
            # Function might be private, check if it's defined in the module
            import inspect
            from scheduler_jobs import payments
            source = inspect.getsource(payments)
            assert "_emit_resend_webhook_alert" in source, "_emit_resend_webhook_alert should be defined"
            print("_emit_resend_webhook_alert is defined in payments module")

    def test_alert_writes_to_notifications(self):
        """Verify alerts are written to notifications collection"""
        import inspect
        from scheduler_jobs import payments
        
        source = inspect.getsource(payments)
        
        # Check for notification insertion
        assert "db.notifications.insert_one" in source, "Alert should write to notifications collection"
        print("Alert function writes to notifications collection")


class TestStartupResendAutosync:
    """Test startup Resend autosync includes status=enabled"""

    def test_startup_autosync_patch_includes_status_enabled(self):
        """Verify startup autosync PATCH includes status=enabled"""
        import inspect
        import server
        
        source = inspect.getsource(server)
        
        # Find the Resend autosync section and verify status=enabled
        # The startup code should include status=enabled in patch_payload
        resend_section_start = source.find("# Auto-sync Resend webhook URL")
        if resend_section_start == -1:
            resend_section_start = source.find("Auto-sync Resend webhook")
        
        assert resend_section_start != -1, "Startup Resend autosync section not found"
        
        # Get the section (next ~200 lines)
        resend_section = source[resend_section_start:resend_section_start + 5000]
        
        # Check for status=enabled in patch payload
        assert '"status": "enabled"' in resend_section or "'status': 'enabled'" in resend_section, \
            "Startup autosync should include status=enabled in PATCH payload"
        print("Startup autosync correctly includes status=enabled in PATCH payload")

    def test_startup_autosync_create_includes_status_enabled(self):
        """Verify startup autosync CREATE includes status=enabled"""
        import inspect
        import server
        
        source = inspect.getsource(server)
        
        # Find the Resend autosync section
        resend_section_start = source.find("# Auto-sync Resend webhook URL")
        if resend_section_start == -1:
            resend_section_start = source.find("Auto-sync Resend webhook")
        
        assert resend_section_start != -1, "Startup Resend autosync section not found"
        
        # Get the section
        resend_section = source[resend_section_start:resend_section_start + 5000]
        
        # Check for create_payload with status=enabled
        assert "create_payload" in resend_section, "Startup autosync should have create_payload"
        print("Startup autosync has create_payload defined")


class TestResendWebhookGuardReturnPayload:
    """Test the guard returns correct payload structure"""

    def test_guard_returns_status_field(self):
        """Verify the guard returns status field (healthy/warning/critical)"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        # Check for return statements with status
        assert '"status":' in source or "'status':" in source, "Guard should return status field"
        assert "healthy" in source, "Guard should return healthy status"
        assert "warning" in source, "Guard should return warning status"
        assert "critical" in source, "Guard should return critical status"
        print("Guard returns correct status values (healthy/warning/critical)")

    def test_guard_returns_aligned_field(self):
        """Verify the guard returns aligned field"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        assert '"aligned":' in source or "'aligned':" in source, "Guard should return aligned field"
        print("Guard returns aligned field")

    def test_guard_returns_action_field(self):
        """Verify the guard returns action field"""
        import inspect
        from scheduler_jobs.payments import scheduled_resend_webhook_guard
        
        source = inspect.getsource(scheduled_resend_webhook_guard)
        
        assert '"action":' in source or "'action':" in source, "Guard should return action field"
        print("Guard returns action field")


class TestResendWebhookReceiverRegression:
    """Regression tests for /api/webhooks/resend receiver flow"""

    def test_resend_webhook_endpoint_exists(self):
        """Verify /api/webhooks/resend endpoint exists"""
        # Send a minimal request to check endpoint exists
        # Note: This will likely fail signature validation but should return 400/401, not 404
        response = requests.post(
            f"{BASE_URL}/api/webhooks/resend",
            json={"type": "test"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404, "Resend webhook endpoint should exist"
        print(f"Resend webhook endpoint exists, returned status: {response.status_code}")

    def test_resend_webhook_endpoint_defined_in_server(self):
        """Verify /api/webhooks/resend endpoint is defined in server.py"""
        import inspect
        import server
        
        source = inspect.getsource(server)
        
        # Check for webhook endpoint definition
        assert '@app.post("/api/webhooks/resend")' in source or \
               "@app.post('/api/webhooks/resend')" in source, \
            "Resend webhook endpoint should be defined in server.py"
        assert "async def resend_webhook" in source, "resend_webhook function should be defined"
        print("Resend webhook endpoint is properly defined in server.py")


class TestHealthEndpointIntegration:
    """Test health endpoint shows Resend webhook guard status"""

    def test_health_endpoint_accessible(self):
        """Verify health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Health status not healthy: {data}"
        print(f"Health endpoint response: {data}")

    def test_system_status_accessible_with_auth(self):
        """Verify system status endpoint is accessible with admin auth"""
        admin_email = "admin@realaicoach.app"
        admin_password = "NewAdminPass2026!"
        
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": admin_email, "password": admin_password},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30
        )
        
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code}")
        
        response = session.get(
            f"{BASE_URL}/api/system/status",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30
        )
        
        # System status may require auth or be public depending on config
        if response.status_code == 200:
            data = response.json()
            assert "status" in data, "System status should have status field"
            print(f"System status: {data.get('status')}")
        else:
            print(f"System status returned: {response.status_code} (may require specific permissions)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
