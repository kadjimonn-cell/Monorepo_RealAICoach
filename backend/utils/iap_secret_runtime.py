from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


CONTRACT_VERSION = "iap-secret-contract-v2"
DEFAULT_RUNTIME_DIR = Path("/run/secrets/iap")
FALLBACK_RUNTIME_DIR = Path("/tmp/realaicoach/iap_secrets")

_HYDRATION_CACHE: Dict[str, Any] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _decode_secret_content(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    # If it already looks like PEM/JSON, return as-is.
    if text.startswith("-----BEGIN") or text.startswith("{"):
        return raw
    try:
        decoded = base64.b64decode(text, validate=True)
        decoded_text = decoded.decode("utf-8")
        if decoded_text.strip().startswith("-----BEGIN") or decoded_text.strip().startswith("{"):
            return decoded_text
    except Exception:
        pass
    return raw


def _fingerprint_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _fingerprint_file(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ""
        return _fingerprint_bytes(p.read_bytes())
    except Exception:
        return ""


def _ensure_runtime_dir() -> Path:
    configured = _env_first("IAP_SECRETS_RUNTIME_DIR")
    candidates = [Path(configured)] if configured else []
    candidates.extend([DEFAULT_RUNTIME_DIR, FALLBACK_RUNTIME_DIR])
    for candidate in candidates:
        if not str(candidate):
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            os.chmod(candidate, 0o700)
            return candidate
        except Exception:
            continue
    FALLBACK_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(FALLBACK_RUNTIME_DIR, 0o700)
    return FALLBACK_RUNTIME_DIR


def _safe_write_secret(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _in_runtime_scope(path: str) -> bool:
    text = str(path or "")
    return text.startswith(str(DEFAULT_RUNTIME_DIR)) or text.startswith(str(FALLBACK_RUNTIME_DIR))


def _normalize_iap_env_aliases() -> None:
    # Canonical Apple identifiers.
    apple_key_id = _env_first("APPLE_IAP_KEY_ID", "ASC_KEY_ID")
    apple_issuer = _env_first("APPLE_IAP_ISSUER_ID", "ASC_ISSUER_ID")
    apple_bundle = _env_first("APPLE_IAP_BUNDLE_ID", "APPLE_BUNDLE_ID")
    if apple_key_id:
        os.environ["APPLE_IAP_KEY_ID"] = apple_key_id
        os.environ.setdefault("ASC_KEY_ID", apple_key_id)
    if apple_issuer:
        os.environ["APPLE_IAP_ISSUER_ID"] = apple_issuer
        os.environ.setdefault("ASC_ISSUER_ID", apple_issuer)
    if apple_bundle:
        os.environ["APPLE_IAP_BUNDLE_ID"] = apple_bundle
        os.environ.setdefault("APPLE_BUNDLE_ID", apple_bundle)

    # Canonical Google identifiers.
    google_pkg = _env_first("GOOGLE_PLAY_IAP_PACKAGE_NAME", "GOOGLE_PLAY_PACKAGE_NAME")
    if google_pkg:
        os.environ["GOOGLE_PLAY_IAP_PACKAGE_NAME"] = google_pkg
        os.environ.setdefault("GOOGLE_PLAY_PACKAGE_NAME", google_pkg)


def hydrate_iap_runtime_secrets(force: bool = False) -> Dict[str, Any]:
    if _HYDRATION_CACHE and not force:
        return dict(_HYDRATION_CACHE)

    _normalize_iap_env_aliases()
    runtime_dir = _ensure_runtime_dir()

    apple_content_raw = _env_first(
        "APPLE_IAP_PRIVATE_KEY_CONTENT",
        "APPLE_IAP_P8_CONTENT",
        "ASC_PRIVATE_KEY_CONTENT",
    )
    google_content_raw = _env_first(
        "GOOGLE_PLAY_SERVICE_ACCOUNT_CONTENT",
        "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON",
        "GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_CONTENT",
    )

    apple_content = _decode_secret_content(apple_content_raw) if apple_content_raw else ""
    google_content = _decode_secret_content(google_content_raw) if google_content_raw else ""

    apple_path_env = _env_first("APPLE_IAP_PRIVATE_KEY_PATH", "ASC_PRIVATE_KEY_PATH")
    google_path_env = _env_first("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH", "GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")

    apple_source = "missing"
    google_source = "missing"
    apple_path = apple_path_env
    google_path = google_path_env
    errors: list[str] = []

    if apple_content:
        try:
            hydrated_path = runtime_dir / "apple_iap_private_key.p8"
            _safe_write_secret(hydrated_path, apple_content)
            apple_path = str(hydrated_path)
            os.environ["APPLE_IAP_PRIVATE_KEY_PATH"] = apple_path
            os.environ.setdefault("ASC_PRIVATE_KEY_PATH", apple_path)
            apple_source = "env_content_hydrated"
        except Exception as exc:
            errors.append(f"apple_hydration_failed:{exc}")
            apple_source = "env_content_failed"
    elif apple_path_env and os.path.exists(apple_path_env):
        apple_source = "path_existing"
    elif apple_path_env:
        apple_source = "path_missing"

    if google_content:
        try:
            hydrated_path = runtime_dir / "google_play_service_account.json"
            # Validate JSON shape before write.
            json.loads(google_content)
            _safe_write_secret(hydrated_path, google_content)
            google_path = str(hydrated_path)
            os.environ["GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH"] = google_path
            os.environ.setdefault("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", google_path)
            google_source = "env_content_hydrated"
        except Exception as exc:
            errors.append(f"google_hydration_failed:{exc}")
            google_source = "env_content_failed"
    elif google_path_env and os.path.exists(google_path_env):
        google_source = "path_existing"
    elif google_path_env:
        google_source = "path_missing"

    report = {
        "contract_version": CONTRACT_VERSION,
        "runtime_dir": str(runtime_dir),
        "created_at": _now_iso(),
        "apple": {
            "path": apple_path,
            "path_exists": bool(apple_path and os.path.exists(apple_path)),
            "source": apple_source,
            "fingerprint": _fingerprint_file(apple_path),
            "runtime_scoped": _in_runtime_scope(apple_path),
        },
        "google": {
            "path": google_path,
            "path_exists": bool(google_path and os.path.exists(google_path)),
            "source": google_source,
            "fingerprint": _fingerprint_file(google_path),
            "runtime_scoped": _in_runtime_scope(google_path),
        },
        "errors": errors,
    }
    _HYDRATION_CACHE.clear()
    _HYDRATION_CACHE.update(report)
    return dict(report)


def compute_iap_provider_readiness() -> Dict[str, Any]:
    hydration = hydrate_iap_runtime_secrets()

    apple_key_path = _env_first("APPLE_IAP_PRIVATE_KEY_PATH", "ASC_PRIVATE_KEY_PATH")
    google_key_path = _env_first("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH", "GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")

    apple_key_exists = bool(apple_key_path and os.path.exists(apple_key_path))
    google_key_exists = bool(google_key_path and os.path.exists(google_key_path))

    apple_mode_raw = str(_env_first("APPLE_IAP_MODE", "APPLE_IAP_ENV") or "live").strip().lower()
    google_mode_raw = str(_env_first("GOOGLE_IAP_MODE", "GOOGLE_PLAY_MODE") or "live").strip().lower()

    apple_mode = "sandbox" if apple_mode_raw in {"sandbox", "test", "testing"} else "live"
    google_mode = "test" if google_mode_raw in {"sandbox", "test", "testing"} else "live"

    apple_sandbox_probe = bool(_env_first("APPLE_SANDBOX_TEST_TRANSACTION_ID"))
    google_sandbox_probe = bool(_env_first("GOOGLE_SANDBOX_TEST_PRODUCT_ID") and _env_first("GOOGLE_SANDBOX_TEST_PURCHASE_TOKEN"))

    apple_key_id = _env_first("APPLE_IAP_KEY_ID", "ASC_KEY_ID")
    apple_issuer = _env_first("APPLE_IAP_ISSUER_ID", "ASC_ISSUER_ID")
    apple_bundle = _env_first("APPLE_IAP_BUNDLE_ID", "APPLE_BUNDLE_ID")
    google_package = _env_first("GOOGLE_PLAY_IAP_PACKAGE_NAME", "GOOGLE_PLAY_PACKAGE_NAME")

    apple_failure_reasons: list[str] = []
    google_failure_reasons: list[str] = []

    if not apple_key_exists:
        apple_failure_reasons.append("missing_private_key")
    if not apple_key_id:
        apple_failure_reasons.append("missing_key_id")
    if not apple_issuer:
        apple_failure_reasons.append("missing_issuer_id")
    if not apple_bundle:
        apple_failure_reasons.append("missing_bundle_id")

    if not google_key_exists:
        google_failure_reasons.append("missing_service_account")
    if not google_package:
        google_failure_reasons.append("missing_package_name")

    apple_ready = apple_key_exists and bool(apple_key_id and apple_issuer and apple_bundle)
    google_ready = google_key_exists and bool(google_package)

    apple_state = (
        "live_ready"
        if apple_ready and apple_mode == "live"
        else "sandbox_ready"
        if (apple_ready and apple_mode == "sandbox") or apple_sandbox_probe
        else "unavailable"
    )
    google_state = (
        "live_ready"
        if google_ready and google_mode == "live"
        else "test_ready"
        if (google_ready and google_mode == "test") or google_sandbox_probe
        else "unavailable"
    )

    apple_label = "Live Ready" if apple_state == "live_ready" else "Sandbox Ready" if apple_state == "sandbox_ready" else "Unavailable"
    google_label = "Live Ready" if google_state == "live_ready" else "Test Ready" if google_state == "test_ready" else "Unavailable"

    providers = {
        "apple": {
            "provider": "apple",
            "label": "Apple App Store",
            "configured": apple_ready,
            "readiness_state": apple_state,
            "status_label": apple_label,
            "mode": apple_mode,
            "message": "Apple IAP credentials and identifiers are configured." if apple_ready else "Apple IAP credentials are missing or incomplete.",
            "sandbox_probe_configured": apple_sandbox_probe,
            "failure_reasons": apple_failure_reasons,
            "secret_fingerprint": hydration.get("apple", {}).get("fingerprint", ""),
            "secret_source": hydration.get("apple", {}).get("source", "missing"),
            "secret_runtime_scoped": bool(hydration.get("apple", {}).get("runtime_scoped")),
            "secret_path": hydration.get("apple", {}).get("path", ""),
        },
        "google": {
            "provider": "google",
            "label": "Google Play",
            "configured": google_ready,
            "readiness_state": google_state,
            "status_label": google_label,
            "mode": google_mode,
            "message": "Google Play IAP credentials and package are configured." if google_ready else "Google Play IAP credentials are missing or incomplete.",
            "sandbox_probe_configured": google_sandbox_probe,
            "failure_reasons": google_failure_reasons,
            "secret_fingerprint": hydration.get("google", {}).get("fingerprint", ""),
            "secret_source": hydration.get("google", {}).get("source", "missing"),
            "secret_runtime_scoped": bool(hydration.get("google", {}).get("runtime_scoped")),
            "secret_path": hydration.get("google", {}).get("path", ""),
        },
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "providers": providers,
        "matrix": [providers["apple"], providers["google"]],
        "last_checked": _now_iso(),
        "hydration": hydration,
    }


def get_iap_secret_diagnostics() -> Dict[str, Any]:
    readiness = compute_iap_provider_readiness()
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": _now_iso(),
        "hydration": readiness.get("hydration", {}),
        "providers": readiness.get("providers", {}),
    }


def _is_production_runtime() -> bool:
    env = _env_first("APP_ENV", "ENVIRONMENT", "STAGE", "NODE_ENV").lower()
    return env in {"prod", "production", "live"}


def enforce_iap_startup_preflight() -> Dict[str, Any]:
    readiness = compute_iap_provider_readiness()
    production_runtime = _is_production_runtime()

    strict = _env_bool("IAP_STARTUP_STRICT", default=production_runtime)
    require_live = _env_bool("IAP_REQUIRE_LIVE_READY", default=production_runtime)

    apple_enabled_default = bool(
        _env_first("APPLE_IAP_KEY_ID", "ASC_KEY_ID")
        or _env_first("APPLE_IAP_ISSUER_ID", "ASC_ISSUER_ID")
        or _env_first("APPLE_IAP_PRIVATE_KEY_CONTENT", "APPLE_IAP_P8_CONTENT", "ASC_PRIVATE_KEY_CONTENT")
        or _env_first("APPLE_IAP_PRIVATE_KEY_PATH", "ASC_PRIVATE_KEY_PATH")
    )
    google_enabled_default = bool(
        _env_first("GOOGLE_PLAY_SERVICE_ACCOUNT_CONTENT", "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_CONTENT")
        or _env_first("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH", "GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")
        or _env_first("GOOGLE_PLAY_IAP_PACKAGE_NAME", "GOOGLE_PLAY_PACKAGE_NAME")
    )

    apple_enabled = _env_bool("APPLE_IAP_ENABLED", default=apple_enabled_default)
    google_enabled = _env_bool("GOOGLE_IAP_ENABLED", default=google_enabled_default)

    allowed_states = {"live_ready"} if require_live else {"live_ready", "sandbox_ready", "test_ready"}
    failures: list[str] = []

    apple_state = str((readiness.get("providers") or {}).get("apple", {}).get("readiness_state") or "unavailable")
    google_state = str((readiness.get("providers") or {}).get("google", {}).get("readiness_state") or "unavailable")

    if strict:
        if apple_enabled and apple_state not in allowed_states:
            apple_reasons = (readiness.get("providers") or {}).get("apple", {}).get("failure_reasons") or []
            failures.append(f"apple_not_ready:{apple_state}:{','.join(apple_reasons)}")
        if google_enabled and google_state not in allowed_states:
            google_reasons = (readiness.get("providers") or {}).get("google", {}).get("failure_reasons") or []
            failures.append(f"google_not_ready:{google_state}:{','.join(google_reasons)}")

    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at": _now_iso(),
        "strict": strict,
        "require_live": require_live,
        "production_runtime": production_runtime,
        "apple_enabled": apple_enabled,
        "google_enabled": google_enabled,
        "apple_state": apple_state,
        "google_state": google_state,
        "failures": failures,
    }

    try:
        report_path = Path("/app/security_reports/latest_iap_startup_preflight.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    if failures:
        raise RuntimeError("IAP startup preflight failed: " + " | ".join(failures))
    return report
