from pathlib import Path
import importlib.util


MODULE_PATH = Path("/app/backend/scripts/preview_host_guard.py")
SPEC = importlib.util.spec_from_file_location("preview_host_guard", MODULE_PATH)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


CURRENT_PREVIEW_HOST = "platform-hardening-7.preview.emergentagent.com"
STALE_PREVIEW_HOST = "auth-methods-qa.preview.emergentagent.com"


def _write_env(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def test_startup_guard_allows_noncritical_stale_preview_aliases(monkeypatch, tmp_path: Path) -> None:
    frontend_env = tmp_path / "frontend.env"
    backend_env = tmp_path / "backend.env"

    _write_env(
        frontend_env,
        f"""
        REACT_APP_BACKEND_URL=https://{CURRENT_PREVIEW_HOST}
        EXPO_PUBLIC_BACKEND_URL=https://{CURRENT_PREVIEW_HOST}
        EXPO_TUNNEL_SUBDOMAIN=coach-web-preview
        """,
    )

    _write_env(
        backend_env,
        f"""
        FRONTEND_BASE_URL=https://{CURRENT_PREVIEW_HOST}
        SSO_REDIRECT_BASE_URL=https://{CURRENT_PREVIEW_HOST}
        SSO_CANONICAL_REDIRECT_BASE=https://{STALE_PREVIEW_HOST}
        MS_SSO_CANONICAL_REDIRECT_BASE=https://{STALE_PREVIEW_HOST}
        APPLE_SSO_CANONICAL_REDIRECT_BASE=https://{STALE_PREVIEW_HOST}
        APPLE_SSO_REGISTERED_REDIRECT_URIS=https://{STALE_PREVIEW_HOST},https://realaicoach.app
        """,
    )

    monkeypatch.setattr(guard, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(guard, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(guard, "get_allowed_preview_host", lambda: CURRENT_PREVIEW_HOST)

    violations = guard.run_startup_guard()
    assert violations == []


def test_startup_guard_fails_on_critical_preview_host_mismatch(monkeypatch, tmp_path: Path) -> None:
    frontend_env = tmp_path / "frontend.env"
    backend_env = tmp_path / "backend.env"

    _write_env(
        frontend_env,
        f"""
        REACT_APP_BACKEND_URL=https://{CURRENT_PREVIEW_HOST}
        EXPO_TUNNEL_SUBDOMAIN=coach-web-preview
        """,
    )

    _write_env(
        backend_env,
        f"""
        FRONTEND_BASE_URL=https://{STALE_PREVIEW_HOST}
        SSO_REDIRECT_BASE_URL=https://{CURRENT_PREVIEW_HOST}
        """,
    )

    monkeypatch.setattr(guard, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(guard, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(guard, "get_allowed_preview_host", lambda: CURRENT_PREVIEW_HOST)

    violations = guard.run_startup_guard()
    assert any("critical key 'FRONTEND_BASE_URL'" in item for item in violations)


def test_startup_guard_fails_on_blocked_token(monkeypatch, tmp_path: Path) -> None:
    frontend_env = tmp_path / "frontend.env"
    backend_env = tmp_path / "backend.env"

    _write_env(
        frontend_env,
        f"""
        REACT_APP_BACKEND_URL=https://{CURRENT_PREVIEW_HOST}
        EXPO_TUNNEL_SUBDOMAIN=coach-web-preview
        """,
    )

    _write_env(
        backend_env,
        f"""
        FRONTEND_BASE_URL=https://{CURRENT_PREVIEW_HOST}
        SSO_REDIRECT_BASE_URL=https://{CURRENT_PREVIEW_HOST}
        SECURITY_NOTE=trust-layer-checkout
        """,
    )

    monkeypatch.setattr(guard, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(guard, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(guard, "get_allowed_preview_host", lambda: CURRENT_PREVIEW_HOST)

    violations = guard.run_startup_guard()
    assert any("blocked token" in item for item in violations)


def test_ci_guard_still_flags_stale_preview_hosts(monkeypatch, tmp_path: Path) -> None:
    frontend_env = tmp_path / "frontend.env"
    backend_env = tmp_path / "backend.env"
    sample_file = tmp_path / "settings.env"

    _write_env(
        frontend_env,
        f"""
        REACT_APP_BACKEND_URL=https://{CURRENT_PREVIEW_HOST}
        EXPO_TUNNEL_SUBDOMAIN=coach-web-preview
        """,
    )
    _write_env(backend_env, "FRONTEND_BASE_URL=https://coach-web-preview.preview.emergentagent.com")
    _write_env(sample_file, f"BROKER_REDIRECT=https://{STALE_PREVIEW_HOST}/api/auth/apple/callback")

    monkeypatch.setattr(guard, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(guard, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(guard, "SCAN_ROOTS", [tmp_path])
    monkeypatch.setattr(guard, "get_allowed_preview_host", lambda: CURRENT_PREVIEW_HOST)

    violations = guard.run_ci_guard()
    assert any("stale preview host" in item for item in violations)
