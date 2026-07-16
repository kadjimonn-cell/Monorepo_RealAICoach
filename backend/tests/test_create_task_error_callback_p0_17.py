from pathlib import Path


CAREERS_SOURCE = Path("/app/backend/routes/careers.py")
JOBS_SOURCE = Path("/app/backend/routes/jobs.py")


def test_careers_fire_and_forget_tasks_have_done_callbacks() -> None:
    source = CAREERS_SOURCE.read_text(encoding="utf-8")

    expected_task_vars = [
        "auto_score_task",
        "applicant_confirmation_task",
        "admin_notify_task",
        "withdraw_notify_task",
        "silver_medalist_task",
    ]

    for task_var in expected_task_vars:
        assert f"{task_var} = _asyncio.create_task(" in source
        assert f"{task_var}.add_done_callback(" in source

    assert source.count("_asyncio.create_task(") >= 5
    assert source.count(".add_done_callback(") >= 5


def test_jobs_fire_and_forget_tasks_have_done_callbacks() -> None:
    source = JOBS_SOURCE.read_text(encoding="utf-8")

    expected_task_vars = [
        "notify_matching_task",
        "auto_pipeline_task",
    ]

    for task_var in expected_task_vars:
        assert f"{task_var} = asyncio.create_task(" in source
        assert f"{task_var}.add_done_callback(" in source

    assert source.count("asyncio.create_task(") >= 2
    assert source.count(".add_done_callback(") >= 2


def test_task_error_callback_logs_exceptions() -> None:
    careers_source = CAREERS_SOURCE.read_text(encoding="utf-8")
    jobs_source = JOBS_SOURCE.read_text(encoding="utf-8")

    expected = 'logger.error("Task failed", exc_info=t.exception()) if t.exception() else None'
    assert expected in careers_source
    assert expected in jobs_source
