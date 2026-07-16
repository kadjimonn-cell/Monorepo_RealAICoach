import ast
import json
from pathlib import Path


FRONTEND_ROOT = Path('/app/frontend')
E2E_DIR = FRONTEND_ROOT / 'e2e'
PLAYWRIGHT_CONFIG = FRONTEND_ROOT / 'playwright.config.ts'
CI_WORKFLOW = Path('/app/.github/workflows/ci-quality-gate.yml')
FRONTEND_PACKAGE = FRONTEND_ROOT / 'package.json'
WEB_RUNTIME_PACKAGE = FRONTEND_ROOT / 'tools/web-runtime/package.json'
RESOLUTIONS_DOC = FRONTEND_ROOT / 'docs/resolutions-rationale.md'
SCHEDULER_PATH = Path('/app/backend/scheduler.py')
SCHEDULER_JOBS_DIR = Path('/app/backend/scheduler_jobs')


def _add_job_calls(tree: ast.AST):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'add_job'
    ]


def test_required_e2e_specs_exist_for_core_domains() -> None:
    required_specs = [
        E2E_DIR / 'auth.spec.ts',
        E2E_DIR / 'subscription.spec.ts',
        E2E_DIR / 'ai-coaching.spec.ts',
        E2E_DIR / 'notifications.spec.ts',
        E2E_DIR / 'admin-dashboard.spec.ts',
    ]
    missing = [str(path) for path in required_specs if not path.exists()]
    assert not missing, f'Missing required E2E specs: {missing}'


def test_playwright_config_workers_and_retries_contract() -> None:
    source = PLAYWRIGHT_CONFIG.read_text(encoding='utf-8')

    assert "testDir: './e2e'" in source
    assert 'workers: 4' in source
    assert 'retries: 2' in source


def test_ci_workflow_runs_component_frontend_e2e_step() -> None:
    source = CI_WORKFLOW.read_text(encoding='utf-8')

    assert 'frontend-component-e2e-core-flows:' in source
    assert 'Run frontend component E2E core flows' in source
    assert '--grep "@component"' in source
    assert '--workers=4' in source
    assert '--retries=2' in source
    for spec in [
        'e2e/auth.spec.ts',
        'e2e/subscription.spec.ts',
        'e2e/ai-coaching.spec.ts',
        'e2e/notifications.spec.ts',
        'e2e/admin-dashboard.spec.ts',
    ]:
        assert spec in source, f'Missing CI component E2E spec wiring: {spec}'

    assert 'rbac-admin-visibility-auth-session:' in source
    assert 'RBAC Admin Visibility Auth Session — Multi Breakpoint' in source
    assert 'e2e/admin-visibility-auth-session.spec.ts' in source
    assert '--project=desktop-chromium --project=tablet-chromium --project=mobile-chromium' in source


def test_frontend_runtime_deps_are_isolated_from_main_package() -> None:
    frontend_pkg = json.loads(FRONTEND_PACKAGE.read_text(encoding='utf-8'))
    deps = frontend_pkg.get('dependencies', {})

    for runtime_dep in ['express', 'serve-static', 'http-proxy-middleware']:
        assert runtime_dep not in deps, f'{runtime_dep} must not be in frontend/package.json dependencies'

    assert deps.get('@realaicoach/web-runtime') == 'file:tools/web-runtime'


def test_web_runtime_package_contains_server_runtime_dependencies() -> None:
    runtime_pkg = json.loads(WEB_RUNTIME_PACKAGE.read_text(encoding='utf-8'))
    runtime_deps = runtime_pkg.get('dependencies', {})

    assert runtime_deps.get('express')
    assert runtime_deps.get('serve-static')
    assert runtime_deps.get('http-proxy-middleware')


def test_every_resolution_override_is_documented() -> None:
    frontend_pkg = json.loads(FRONTEND_PACKAGE.read_text(encoding='utf-8'))
    resolution_keys = list((frontend_pkg.get('resolutions') or {}).keys())
    doc = RESOLUTIONS_DOC.read_text(encoding='utf-8')

    missing = [key for key in resolution_keys if key not in doc]
    assert not missing, f'Resolutions missing documentation entries: {missing}'


def test_scheduler_add_jobs_are_protected_with_max_instances_one() -> None:
    scheduler_tree = ast.parse(SCHEDULER_PATH.read_text(encoding='utf-8'))

    trees = [(SCHEDULER_PATH.name, scheduler_tree)]
    # `scheduler_jobs` was converted from a single file to a package; walk
    # every submodule to ensure no domain module accidentally adds a job
    # without `max_instances=1`.
    if SCHEDULER_JOBS_DIR.is_dir():
        for py_file in sorted(SCHEDULER_JOBS_DIR.glob('*.py')):
            if py_file.name == '__init__.py':
                continue
            trees.append((f'scheduler_jobs/{py_file.name}', ast.parse(py_file.read_text(encoding='utf-8'))))

    for path, tree in trees:
        for call in _add_job_calls(tree):
            kw = next((k for k in call.keywords if isinstance(k, ast.keyword) and k.arg == 'max_instances'), None)
            assert kw is not None, f'{path} add_job missing max_instances at line {call.lineno}'
            assert isinstance(kw.value, ast.Constant) and kw.value.value == 1, (
                f'{path} add_job max_instances must equal 1 at line {call.lineno}'
            )
