import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import middleware


def _clear_origin_env(monkeypatch) -> None:
    for key in [
        "ALLOWED_ORIGINS",
        "BACKEND_URL",
        "REACT_APP_BACKEND_URL",
        "FRONTEND_BASE_URL",
        "ENVIRONMENT",
        "APP_ENV",
        "NODE_ENV",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_cors_localhost_origins_included_only_in_development(monkeypatch) -> None:
    _clear_origin_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    origins = middleware._build_allowed_origins()

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3001" in origins


def test_cors_localhost_origins_excluded_in_production(monkeypatch) -> None:
    _clear_origin_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")

    origins = middleware._build_allowed_origins()

    assert "http://localhost:3000" not in origins
    assert "http://127.0.0.1:3001" not in origins
    assert "https://realaicoach.app" in origins


def test_cors_respects_explicit_allowed_origins(monkeypatch) -> None:
    _clear_origin_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com, https://admin.example.com")

    origins = middleware._build_allowed_origins()

    assert origins == ["https://app.example.com", "https://admin.example.com"]