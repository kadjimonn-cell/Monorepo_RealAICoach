import ast
from pathlib import Path


SCHEDULER_PATH = Path('/app/backend/scheduler.py')
SCHEDULER_JOBS_PATH = Path('/app/backend/scheduler_jobs.py')


def _add_job_calls(tree: ast.AST):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'add_job'
    ]


def _max_instances_keyword(call: ast.Call):
    return next(
        (
            kw
            for kw in call.keywords
            if isinstance(kw, ast.keyword) and kw.arg == 'max_instances'
        ),
        None,
    )


def test_scheduler_add_job_calls_require_max_instances_one():
    tree = ast.parse(SCHEDULER_PATH.read_text())
    calls = _add_job_calls(tree)
    assert calls, 'Expected at least one add_job call in scheduler.py'

    missing = []
    invalid = []
    for call in calls:
        kw = _max_instances_keyword(call)
        if kw is None:
            missing.append(call.lineno)
            continue
        if not isinstance(kw.value, ast.Constant) or kw.value.value != 1:
            invalid.append(call.lineno)

    assert not missing, f'add_job calls missing max_instances in scheduler.py lines: {missing}'
    assert not invalid, f'add_job calls with non-1 max_instances in scheduler.py lines: {invalid}'


def test_scheduler_jobs_file_has_no_unprotected_add_job_calls():
    tree = ast.parse(SCHEDULER_JOBS_PATH.read_text())
    calls = _add_job_calls(tree)
    # Contract: either no add_job calls in this module, or every call must carry max_instances=1.
    for call in calls:
        kw = _max_instances_keyword(call)
        assert kw is not None, f'add_job missing max_instances in scheduler_jobs.py line: {call.lineno}'
        assert isinstance(kw.value, ast.Constant) and kw.value.value == 1, (
            f'add_job max_instances must be 1 in scheduler_jobs.py line: {call.lineno}'
        )