import json
from pathlib import Path


FRONTEND_PACKAGE_JSON = Path('/app/frontend/package.json')
FRONTEND_PACKAGE_LOCK = Path('/app/frontend/package-lock.json')
EXPO_PACKAGE_JSON = Path('/app/frontend/node_modules/expo/package.json')
EXPO_CLI_PACKAGE_JSON = Path('/app/frontend/node_modules/@expo/cli/package.json')


def _has_range_prefix(version_spec: str) -> bool:
    return str(version_spec or '').startswith(('~', '^', '>', '<', '*'))


def test_issue10_expo_and_cli_are_exact_pins() -> None:
    package = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding='utf-8'))
    expo_spec = package.get('dependencies', {}).get('expo')
    cli_spec = package.get('devDependencies', {}).get('@expo/cli')

    assert expo_spec, 'Missing dependencies.expo'
    assert cli_spec, 'Missing devDependencies.@expo/cli'
    assert not _has_range_prefix(expo_spec), f'expo must be exact pinned (found {expo_spec})'
    assert not _has_range_prefix(cli_spec), f'@expo/cli must be exact pinned (found {cli_spec})'


def test_issue10_installed_versions_match_declared_pins() -> None:
    package = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding='utf-8'))
    installed_expo = json.loads(EXPO_PACKAGE_JSON.read_text(encoding='utf-8')).get('version')
    installed_cli = json.loads(EXPO_CLI_PACKAGE_JSON.read_text(encoding='utf-8')).get('version')

    declared_expo = package.get('dependencies', {}).get('expo')
    declared_cli = package.get('devDependencies', {}).get('@expo/cli')

    assert installed_expo == declared_expo, (
        f'Installed expo drift detected: declared={declared_expo}, installed={installed_expo}'
    )
    assert installed_cli == declared_cli, (
        f'Installed @expo/cli drift detected: declared={declared_cli}, installed={installed_cli}'
    )


def test_issue10_no_mixed_package_manager_lockfile() -> None:
    assert not FRONTEND_PACKAGE_LOCK.exists(), (
        'Remove frontend/package-lock.json to avoid npm/yarn mixed lockfile dependency drift.'
    )
