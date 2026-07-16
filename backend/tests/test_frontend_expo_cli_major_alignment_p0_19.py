import json
import re
from pathlib import Path


FRONTEND_PACKAGE_JSON = Path("/app/frontend/package.json")


def _major(version_spec: str) -> int:
    match = re.search(r"(\d+)\.", str(version_spec or ""))
    if not match:
        raise AssertionError(f"Unable to parse semver major from: {version_spec}")
    return int(match.group(1))


def test_expo_and_expo_cli_have_matching_major_versions() -> None:
    package = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    expo_version = package.get("dependencies", {}).get("expo")
    expo_cli_version = package.get("devDependencies", {}).get("@expo/cli")

    assert expo_version, "Missing dependencies.expo in frontend/package.json"
    assert expo_cli_version, "Missing devDependencies.@expo/cli in frontend/package.json"

    assert _major(expo_version) == _major(expo_cli_version), (
        f"Expo SDK and @expo/cli major versions must match: expo={expo_version}, @expo/cli={expo_cli_version}"
    )
