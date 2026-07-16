from pathlib import Path


SCHEDULER_PATH = Path('/app/backend/scheduler.py')


def test_scheduler_registers_error_and_missed_listener() -> None:
    source = SCHEDULER_PATH.read_text(encoding='utf-8')

    assert 'from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED' in source
    assert 'def on_job_error(event) -> None:' in source
    assert 'scheduler.add_listener(on_job_error, EVENT_JOB_ERROR | EVENT_JOB_MISSED)' in source


def test_scheduler_error_listener_logs_job_id_and_traceback() -> None:
    source = SCHEDULER_PATH.read_text(encoding='utf-8')

    assert 'job_id = getattr(event, "job_id", "unknown")' in source
    assert 'traceback_text = getattr(event, "traceback", "")' in source
    assert '[apscheduler] job execution failed | job_id=%s code=%s error=%s\\n%s' in source
