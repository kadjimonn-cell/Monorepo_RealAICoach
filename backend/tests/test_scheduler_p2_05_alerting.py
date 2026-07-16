"""
P2-05 · APScheduler Error Events → Alerting
Regression guard: asserts that on_job_error dispatches to webhook alerting AND
persists a DB audit document, and that apscheduler event types are registered in
the DEFAULT_CONFIG enabled_events list.
"""
import inspect
from pathlib import Path


SCHEDULER_PATH = Path('/app/backend/scheduler.py')
WEBHOOK_ALERTS_PATH = Path('/app/backend/services/webhook_alerts.py')


# ── scheduler.py assertions ───────────────────────────────────────────────────

def test_on_job_error_calls_dispatch_scheduler_alert() -> None:
    """on_job_error must call _dispatch_scheduler_alert for both error and missed paths."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert '_dispatch_scheduler_alert(' in source, (
        "on_job_error must call _dispatch_scheduler_alert() for webhook + DB dispatch"
    )


def test_dispatch_calls_send_alert_fire_and_forget() -> None:
    """_dispatch_scheduler_alert must import and call send_alert_fire_and_forget."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert 'send_alert_fire_and_forget' in source, (
        "_dispatch_scheduler_alert must call send_alert_fire_and_forget from services.webhook_alerts"
    )
    assert 'from services.webhook_alerts import send_alert_fire_and_forget' in source


def test_dispatch_uses_correct_event_types() -> None:
    """_dispatch_scheduler_alert must use 'apscheduler_job_error' and 'apscheduler_job_missed'."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert '"apscheduler_job_error"' in source, (
        "_dispatch_scheduler_alert must pass event_type='apscheduler_job_error'"
    )
    assert '"apscheduler_job_missed"' in source, (
        "_dispatch_scheduler_alert must pass event_type='apscheduler_job_missed'"
    )


def test_dispatch_persists_db_audit_document() -> None:
    """_dispatch_scheduler_alert must fire-and-forget a DB insert to apscheduler_job_error_events."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert 'apscheduler_job_error_events' in source, (
        "_dispatch_scheduler_alert must persist an audit doc to db.apscheduler_job_error_events"
    )
    assert 'loop.create_task(_persist_audit())' in source, (
        "_persist_audit must be scheduled as a fire-and-forget asyncio task"
    )


def test_error_path_uses_critical_severity() -> None:
    """Job errors (exception present) must be dispatched with severity='critical'."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert 'severity="critical"' in source, (
        "apscheduler_job_error must use severity='critical'"
    )


def test_missed_path_uses_warning_severity() -> None:
    """Job misses (no exception) must be dispatched with severity='warning'."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert 'severity="warning"' in source, (
        "apscheduler_job_missed must use severity='warning'"
    )


# ── webhook_alerts.py assertions ─────────────────────────────────────────────

def test_apscheduler_job_error_in_default_enabled_events() -> None:
    """'apscheduler_job_error' must be in DEFAULT_CONFIG['enabled_events']."""
    source = WEBHOOK_ALERTS_PATH.read_text(encoding='utf-8')
    assert '"apscheduler_job_error"' in source, (
        "DEFAULT_CONFIG['enabled_events'] in webhook_alerts.py must include 'apscheduler_job_error'"
    )


def test_apscheduler_job_missed_in_default_enabled_events() -> None:
    """'apscheduler_job_missed' must be in DEFAULT_CONFIG['enabled_events']."""
    source = WEBHOOK_ALERTS_PATH.read_text(encoding='utf-8')
    assert '"apscheduler_job_missed"' in source, (
        "DEFAULT_CONFIG['enabled_events'] in webhook_alerts.py must include 'apscheduler_job_missed'"
    )


# ── P1-13 backward-compat: prior regression assertions still pass ─────────────

def test_scheduler_registers_error_and_missed_listener() -> None:
    """P1-13 compat: add_listener registration must still be present."""
    source = SCHEDULER_PATH.read_text(encoding='utf-8')
    assert 'from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED' in source
    assert 'def on_job_error(event) -> None:' in source
    assert 'scheduler.add_listener(on_job_error, EVENT_JOB_ERROR | EVENT_JOB_MISSED)' in source
