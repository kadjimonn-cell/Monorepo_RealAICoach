"""Preview host safety guard for CI and startup.

Policies enforced:
1) Block any reference to `trust-layer-checkout`.
2) Block any `*.preview.emergentagent.com` host that does not match the
   active canonical preview host (APP_URL/FRONTEND_BASE_URL/frontend env).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path("/app")
FRONTEND_ENV = ROOT / "frontend" / ".env"
BACKEND_ENV = ROOT / "backend" / ".env"

PREVIEW_HOST_RE = re.compile(r"([a-z0-9-]+\.preview\.emergentagent\.com)", re.IGNORECASE)
BLOCKED_HOST_MARKER = "trust-layer-checkout"

CRITICAL_FRONTEND_KEYS = ("REACT_APP_BACKEND_URL", "EXPO_PUBLIC_BACKEND_URL")
CRITICAL_BACKEND_KEYS = ("FRONTEND_BASE_URL", "SSO_REDIRECT_BASE_URL")

SCAN_EXTENSIONS = {".env", ".json", ".yml", ".yaml", ".ts", ".py"}
SCAN_ROOTS = [ROOT / "frontend", ROOT / "backend", ROOT / ".github"]
SKIP_SEGMENTS = {
    "tests",
    "node_modules",
    "dist",
    "test_reports",
    "memory",
    "__pycache__",
    ".git",
    ".emergent",
}


def _normalize_host(value: str) -> str:
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return (urlparse(raw).netloc or "").lower()
    return raw.replace("http://", "").replace("https://", "").split("/", 1)[0].lower()


def _env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        txt = line.strip()
        if not txt or txt.startswith("#") or "=" not in txt:
            continue
        k, v = txt.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return ""


def _proc_env_value(key: str) -> str:
    lookup = str(key or "").strip()
    if not lookup:
        return ""

    for proc_path in (Path("/proc/1/environ"), Path("/proc/self/environ")):
        try:
            raw = proc_path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue
        for token in raw.split("\x00"):
            if token.startswith(f"{lookup}="):
                return token.split("=", 1)[1].strip()
    return ""


def _expected_preview_subdomain(host: str) -> str:
    normalized = str(host or "").strip().lower()
    for suffix in (".preview.emergentagent.com", ".preview.emergentcf.cloud"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return ""


def find_allowed_preview_host() -> str:
    candidates = [
        os.environ.get("PREVIEW_ENDPOINT", ""),
        os.environ.get("preview_endpoint", ""),
        _proc_env_value("PREVIEW_ENDPOINT"),
        _proc_env_value("preview_endpoint"),
        os.environ.get("APP_URL", ""),
        os.environ.get("FRONTEND_BASE_URL", ""),
        os.environ.get("EXPO_PUBLIC_BACKEND_URL", ""),
        _env_value(FRONTEND_ENV, "REACT_APP_BACKEND_URL"),
        os.environ.get("REACT_APP_BACKEND_URL", ""),
        _env_value(FRONTEND_ENV, "EXPO_PUBLIC_BACKEND_URL"),
        _env_value(BACKEND_ENV, "FRONTEND_BASE_URL"),
    ]
    for value in candidates:
        host = _normalize_host(value)
        if host.endswith(".preview.emergentagent.com"):
            return host
    return ""


def get_allowed_preview_host() -> str:
    host = find_allowed_preview_host()
    if host:
        return host
    raise RuntimeError(
        "Unable to determine canonical preview host from frontend/.env "
        "(REACT_APP_BACKEND_URL or EXPO_PUBLIC_BACKEND_URL)."
    )


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts.intersection(SKIP_SEGMENTS):
        return True
    name = path.name.lower()
    if name.startswith("test_") and path.suffix == ".py":
        return True
    if name.endswith("_test.py"):
        return True
    return False


def _scan_text(path: Path, text: str, allowed_host: str) -> list[str]:
    violations: list[str] = []
    lower = text.lower()
    if BLOCKED_HOST_MARKER in lower:
        violations.append(f"{path}: blocked token '{BLOCKED_HOST_MARKER}' detected")

    for host in sorted(set(m.group(1).lower() for m in PREVIEW_HOST_RE.finditer(text))):
        if host != allowed_host:
            violations.append(
                f"{path}: stale preview host '{host}' (allowed '{allowed_host}')"
            )
    return violations


def _host_mismatch_violation(path: Path, key: str, value: str, allowed_host: str) -> str | None:
    host = _normalize_host(value)
    if not host:
        return None
    # Only enforce strict parity on preview hosts; production/stable hosts are permitted.
    if not (
        host.endswith(".preview.emergentagent.com")
        or host.endswith(".preview.emergentcf.cloud")
    ):
        return None
    if host == allowed_host:
        return None
    return (
        f"{path}: critical key '{key}' uses stale preview host "
        f"'{host}' (allowed '{allowed_host}')"
    )


def _startup_validate_critical_keys(path: Path, allowed_host: str, keys: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    if not path.is_file():
        return violations
    for key in keys:
        value = _env_value(path, key)
        violation = _host_mismatch_violation(path, key, value, allowed_host)
        if violation:
            violations.append(violation)
    return violations


def run_startup_guard() -> list[str]:
    allowed_host = find_allowed_preview_host()
    if not allowed_host:
        # Production environment (no preview host resolvable): guard is preview-only.
        return []
    violations: list[str] = []

    for env_path in (FRONTEND_ENV, BACKEND_ENV):
        if not env_path.is_file():
            if env_path == FRONTEND_ENV:
                violations.append(f"{env_path}: missing env file")
            continue
        text = env_path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()
        if BLOCKED_HOST_MARKER in lower:
            violations.append(f"{env_path}: blocked token '{BLOCKED_HOST_MARKER}' detected")

    # Startup mode enforces only critical runtime keys.
    # Broad stale-host scanning across files remains in CI mode.
    violations.extend(_startup_validate_critical_keys(FRONTEND_ENV, allowed_host, CRITICAL_FRONTEND_KEYS))
    violations.extend(_startup_validate_critical_keys(BACKEND_ENV, allowed_host, CRITICAL_BACKEND_KEYS))

    expected_subdomain = _expected_preview_subdomain(allowed_host)
    if expected_subdomain:
        expo_tunnel = _env_value(FRONTEND_ENV, "EXPO_TUNNEL_SUBDOMAIN").strip().strip('"').strip("'")
        if not expo_tunnel:
            violations.append(
                f"{FRONTEND_ENV}: missing EXPO_TUNNEL_SUBDOMAIN (expected '{expected_subdomain}')"
            )
        elif expo_tunnel.lower() != expected_subdomain:
            violations.append(
                f"{FRONTEND_ENV}: EXPO_TUNNEL_SUBDOMAIN '{expo_tunnel}' does not match canonical preview subdomain '{expected_subdomain}'"
            )

    return violations


def run_ci_guard() -> list[str]:
    allowed_host = get_allowed_preview_host()
    violations: list[str] = []

    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if _should_skip(path):
                continue
            suffix = path.suffix.lower()
            name = path.name.lower()
            if suffix not in SCAN_EXTENSIONS and not name.startswith(".env"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            violations.extend(_scan_text(path, text, allowed_host))

    expected_subdomain = _expected_preview_subdomain(allowed_host)
    if expected_subdomain:
        expo_tunnel = _env_value(FRONTEND_ENV, "EXPO_TUNNEL_SUBDOMAIN").strip().strip('"').strip("'")
        if not expo_tunnel:
            violations.append(
                f"{FRONTEND_ENV}: missing EXPO_TUNNEL_SUBDOMAIN (expected '{expected_subdomain}')"
            )
        elif expo_tunnel.lower() != expected_subdomain:
            violations.append(
                f"{FRONTEND_ENV}: EXPO_TUNNEL_SUBDOMAIN '{expo_tunnel}' does not match canonical preview subdomain '{expected_subdomain}'"
            )

    violations.extend(run_production_boot_simulation())

    return violations


def run_production_boot_simulation() -> list[str]:
    """Fake production env vars and assert the startup guard path no-ops (never raises)."""
    code = (
        "from pathlib import Path\n"
        "import scripts.preview_host_guard as g\n"
        "g._proc_env_value = lambda key: ''\n"
        "g.FRONTEND_ENV = Path('/nonexistent/frontend.env')\n"
        "g.BACKEND_ENV = Path('/nonexistent/backend.env')\n"
        "assert g.find_allowed_preview_host() == '', 'preview host leaked into prod sim'\n"
        "g.assert_startup_preview_host_safety()\n"
        "assert g.run_startup_guard() == [], 'startup guard emitted violations in prod env'\n"
        "print('PROD_SIM_OK')\n"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "FRONTEND_BASE_URL": "https://realaicoach.emergent.host",
        "REACT_APP_BACKEND_URL": "https://realaicoach.emergent.host",
        "EXPO_PUBLIC_BACKEND_URL": "https://realaicoach.emergent.host",
        "APP_URL": "https://www.realaicoach.app",
    }
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT / "backend"),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return [f"production boot simulation: could not execute ({exc})"]
    if result.returncode != 0 or "PROD_SIM_OK" not in result.stdout:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = detail[-1] if detail else "unknown error"
        return [
            "production boot simulation: startup guard would BLOCK production boot "
            f"({tail})"
        ]
    return []


def assert_startup_preview_host_safety() -> None:
    if not find_allowed_preview_host():
        import logging

        logging.getLogger("preview_host_guard").info(
            "No preview host detected (production environment): startup guard skipped."
        )
        return
    violations = run_startup_guard()
    if violations:
        raise RuntimeError(
            "Preview startup host guard failed:\n" + "\n".join(f"- {v}" for v in violations)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview host safety guard")
    parser.add_argument("--mode", choices=["startup", "ci", "prod-sim"], default="ci")
    args = parser.parse_args()

    if args.mode == "startup":
        violations = run_startup_guard()
    elif args.mode == "prod-sim":
        violations = run_production_boot_simulation()
    else:
        violations = run_ci_guard()
    if violations:
        print("Preview host guard FAILED")
        for v in violations:
            print(f"- {v}")
        return 1

    print("Preview host guard PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
