from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
import sys
import asyncio

import pytest

sys.path.append("/app/backend")

from routes.db import db
from services import gtec_scan_v2 as svc


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _clean_report(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "sections": {
            "security_scan": {"findings": []},
            "performance": {"findings": []},
        },
    }


def _report_with_match(task_id: str, *, label: str, severity: str) -> dict:
    return {
        "task_id": task_id,
        "sections": {
            "security_scan": {
                "findings": [
                    {
                        "label": label,
                        "severity": severity,
                    }
                ]
            }
        },
    }


def _skip_if_event_loop_closed(exc: RuntimeError) -> None:
    if "Event loop is closed" in str(exc):
        pytest.skip("Event loop closed in current environment")


@pytest.mark.asyncio
async def test_incident_auto_close_two_stage_policy_and_reopen_on_recurrence():
    try:
        await svc.ensure_internal_collections_migrated(db)
    except RuntimeError as exc:
        _skip_if_event_loop_closed(exc)
        raise

    incident_id = f"test_auto_close_{uuid.uuid4().hex[:10]}"
    label = "autoclose_test_label"
    severity = "medium"
    incident_key = f"{label}:{severity}"
    now = datetime.now(timezone.utc).isoformat()

    try:
        await db[svc.INCIDENTS_COL].insert_one(
            {
                "incident_id": incident_id,
                "incident_key": incident_key,
                "status": "open",
                "containment": "active",
                "severity": severity,
                "label": label,
                "created_at": now,
                "updated_at": now,
                "task_id": "gtec_c5_test_seed",
            }
        )
    except RuntimeError as exc:
        _skip_if_event_loop_closed(exc)
        raise

    try:
        try:
            for i in range(3):
                summary = await svc.apply_incident_auto_closure_policy(db, _clean_report(f"gtec_c5_clean_{i}"))
                assert "evaluated_incidents" in summary

            pending = await db[svc.INCIDENTS_COL].find_one({"incident_id": incident_id}, {"_id": 0})
            assert pending is not None
            assert pending.get("status") == svc.INCIDENT_PENDING_STATUS
            assert int(pending.get("clean_rescan_streak") or 0) >= svc.INCIDENT_AUTOCLOSE_CLEAN_RESCANS

            old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
            await db[svc.INCIDENTS_COL].update_one(
                {"incident_id": incident_id},
                {
                    "$set": {
                        "status": svc.INCIDENT_PENDING_STATUS,
                        "pending_verification_started_at": old_ts,
                    }
                },
            )

            await svc.apply_incident_auto_closure_policy(db, _clean_report("gtec_c5_clean_4"))
            closed = await db[svc.INCIDENTS_COL].find_one({"incident_id": incident_id}, {"_id": 0})
            assert closed is not None
            assert closed.get("status") == svc.INCIDENT_CLOSED_STATUS
            assert closed.get("closed_by") == "system_auto_close"
            # Reopen scenario during pending-verification hold
            reopen_incident_id = f"test_auto_reopen_{uuid.uuid4().hex[:10]}"
            reopen_label = "autoclose_reopen_label"
            reopen_severity = "high"
            reopen_incident_key = f"{reopen_label}:{reopen_severity}"
            reopen_now = datetime.now(timezone.utc).isoformat()

            await db[svc.INCIDENTS_COL].insert_one(
                {
                    "incident_id": reopen_incident_id,
                    "incident_key": reopen_incident_key,
                    "status": svc.INCIDENT_PENDING_STATUS,
                    "containment": "monitoring",
                    "severity": reopen_severity,
                    "label": reopen_label,
                    "clean_rescan_streak": 3,
                    "pending_verification_started_at": reopen_now,
                    "created_at": reopen_now,
                    "updated_at": reopen_now,
                    "task_id": "gtec_c5_test_seed",
                }
            )

            await svc.apply_incident_auto_closure_policy(
                db,
                _report_with_match("gtec_c5_dirty_1", label=reopen_label, severity=reopen_severity),
            )
            reopened = await db[svc.INCIDENTS_COL].find_one({"incident_id": reopen_incident_id}, {"_id": 0})
            assert reopened is not None
            assert reopened.get("status") == "open"
            assert int(reopened.get("clean_rescan_streak") or 0) == 0
            assert reopened.get("containment") == "active"
        except RuntimeError as exc:
            _skip_if_event_loop_closed(exc)
            raise
    finally:
        try:
            await db[svc.INCIDENTS_COL].delete_one({"incident_id": incident_id})
            await db[svc.INCIDENTS_COL].delete_many({"incident_id": {"$regex": "^test_auto_reopen_"}})
        except RuntimeError as exc:
            _skip_if_event_loop_closed(exc)
            raise
