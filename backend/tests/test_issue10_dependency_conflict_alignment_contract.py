import json
from pathlib import Path


FRONTEND_PACKAGE = Path('/app/frontend/package.json')
FRONTEND_RESOLUTION_AUDIT = Path('/app/frontend/resolutions_audit.md')
BACKEND_REQUIREMENTS = Path('/app/backend/requirements.txt')


def _requirements_map() -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw in BACKEND_REQUIREMENTS.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '==' not in line:
            continue
        name, version = line.split('==', 1)
        pairs[name.strip()] = version.strip()
    return pairs


def test_issue10_frontend_exact_pins_and_server_deps_absent() -> None:
    package = json.loads(FRONTEND_PACKAGE.read_text(encoding='utf-8'))
    deps = package.get('dependencies', {})
    dev_deps = package.get('devDependencies', {})

    exact_expectations = {
        'expo': '54.0.34',
        'react-native-reanimated': '4.1.1',
        '@opentelemetry/api': '1.9.1',
        '@opentelemetry/resources': '2.7.1',
        '@opentelemetry/sdk-trace-web': '2.7.1',
        '@opentelemetry/exporter-trace-otlp-http': '0.218.0',
        '@opentelemetry/instrumentation': '0.218.0',
        '@opentelemetry/instrumentation-fetch': '0.218.0',
        '@opentelemetry/semantic-conventions': '1.41.1',
    }
    for key, expected in exact_expectations.items():
        assert deps.get(key) == expected, f'{key} must be exact pinned to {expected}'

    assert dev_deps.get('@expo/cli') == '54.0.24'

    for server_only in ['express', 'serve-static', 'http-proxy-middleware']:
        assert server_only not in deps
        assert server_only not in dev_deps


def test_issue10_resolutions_audit_file_tracks_all_resolution_keys() -> None:
    package = json.loads(FRONTEND_PACKAGE.read_text(encoding='utf-8'))
    resolutions = package.get('resolutions', {})
    audit_content = FRONTEND_RESOLUTION_AUDIT.read_text(encoding='utf-8')

    assert FRONTEND_RESOLUTION_AUDIT.exists()
    for resolution_key in resolutions.keys():
        assert resolution_key in audit_content, f'Missing resolution audit entry for {resolution_key}'


def test_issue10_backend_google_auth_pinned_to_stable_and_instrumentation_consistent() -> None:
    reqs = _requirements_map()

    assert reqs.get('google-auth') == '2.53.0'
    assert 'dev' not in reqs.get('google-auth', '')
    assert reqs.get('opentelemetry-sdk') == '1.42.1'

    expected_beta = '0.63b1'
    instrumentation_packages = [
        'opentelemetry-instrumentation',
        'opentelemetry-instrumentation-asgi',
        'opentelemetry-instrumentation-fastapi',
        'opentelemetry-instrumentation-httpx',
        'opentelemetry-instrumentation-logging',
        'opentelemetry-instrumentation-pymongo',
    ]
    for package_name in instrumentation_packages:
        assert reqs.get(package_name) == expected_beta
