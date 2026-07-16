"""Enterprise security key rotation orchestration.

R1: provider readiness + coverage alignment
R2: prepare/approve/apply flows
R3: rollback safeguards
R4: incident linkage
R5: evidence retrieval
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import base64
import hashlib
import hmac
import json
import os
import uuid
import asyncio
from urllib.parse import urlencode
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
import httpx

from routes.db import db, require_admin
from utils.production_security_policy_gate import collect_policy_gate_signals

router = APIRouter(prefix="/admin/security/key-rotation", tags=["security-key-rotation"])


APPLY_CONTRACT_MANUAL = "manual_by_provider_constraint"
APPLY_CONTRACT_PROBE_ONLY = "api_probe_only"
APPLY_CONTRACT_API_ROTATE = "api_rotate_supported"

VALID_APPLY_CONTRACTS = {
    APPLY_CONTRACT_MANUAL,
    APPLY_CONTRACT_PROBE_ONLY,
    APPLY_CONTRACT_API_ROTATE,
}


READINESS_STATUS_BLOCKED = "blocked"
READINESS_STATUS_GUARDED = "guarded"
READINESS_STATUS_ADAPTER_MISSING = "adapter_missing"
READINESS_STATUS_MANUAL_BY_CONSTRAINT = "manual_by_provider_constraint"
READINESS_STATUS_API_PROBE_READY = "api_probe_only_ready"
READINESS_STATUS_API_ROTATE_READY = "api_rotate_ready"


STEP_STATUS_SIMULATED = "simulated"
STEP_STATUS_BLOCKED = "blocked"
STEP_STATUS_CONTRACT_REJECTED = "contract_rejected"
STEP_STATUS_MANUAL_PENDING = "manual_pending_evidence"
STEP_STATUS_MANUAL_EVIDENCE_UPLOADED = "manual_evidence_uploaded"
STEP_STATUS_MANUAL_VERIFIED = "manual_applied_verified"
STEP_STATUS_ADAPTER_MISSING = "adapter_missing"
STEP_STATUS_GUARDED = "guarded"
STEP_STATUS_API_PROBE_VALIDATED = "credential_validated"
STEP_STATUS_API_PROBE_FAILED = "api_probe_failed"
STEP_STATUS_CUTOVER_APPLIED = "cutover_applied"
STEP_STATUS_PROVIDER_REVOKED = "provider_revoked"
STEP_STATUS_CUTOVER_FAILED = "cutover_failed"
STEP_STATUS_SKIPPED_CANARY = "skipped_canary_stop"


class KeyRotationPrepareBody(BaseModel):
    providers: List[str] = Field(default_factory=list)
    reason: str = "scheduled_rotation"
    change_ticket: Optional[str] = None
    execution_mode: Literal["live_guarded", "dry_run"] = "live_guarded"


class KeyRotationApproveBody(BaseModel):
    plan_id: str
    approval_token: str
    approval_note: Optional[str] = None


class KeyRotationApplyBody(BaseModel):
    plan_id: str
    run_note: Optional[str] = None
    execution_mode: Literal["live_guarded", "dry_run"] = "live_guarded"


class KeyRotationManualEvidenceBody(BaseModel):
    provider_id: str
    evidence_note: str = ""
    evidence_links: List[str] = Field(default_factory=list)
    verification_checks: List[str] = Field(default_factory=list)
    provider_console_confirmed: bool = False
    mark_verified: bool = False


class KeyRotationGameDayBody(BaseModel):
    note: str = ""
    evidence_links: List[str] = Field(default_factory=list)


class KeyRotationPolicyAttestationBody(BaseModel):
    note: str = ""
    run_prerequisite_refresh: bool = True
    validate_webhook: bool = True
    include_game_day_snapshot: bool = True


class KeyRotationMonitorRunNowBody(BaseModel):
    include_attestation: bool = True
    force: bool = True


class KeyRotationMonitorResumeBody(BaseModel):
    run_now: bool = False


PROVIDER_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "provider_id": "payments_stripe",
        "label": "Stripe Payments",
        "family": "payments",
        "required_any": [["STRIPE_API_KEY"], ["STRIPE_SECRET_KEY"]],
        "rotation_supported": "api",
        "apply_contract_mode": APPLY_CONTRACT_PROBE_ONLY,
        "api_adapter": "stripe",
        "api_apply_required_any": [["STRIPE_API_KEY"], ["STRIPE_SECRET_KEY"]],
        "rollback_supported": True,
    },
    {
        "provider_id": "payments_paypal",
        "label": "PayPal Payments",
        "family": "payments",
        "required_all": ["PAYPAL_CLIENT_ID"],
        "required_any": [["PAYPAL_SECRET"], ["PAYPAL_CLIENT_SECRET"]],
        "rotation_supported": "api",
        "apply_contract_mode": APPLY_CONTRACT_PROBE_ONLY,
        "api_adapter": "paypal",
        "api_apply_required_all": ["PAYPAL_CLIENT_ID"],
        "api_apply_required_any": [["PAYPAL_SECRET"], ["PAYPAL_CLIENT_SECRET"]],
        "rollback_supported": True,
    },
    {
        "provider_id": "payments_fedapay",
        "label": "FedaPay Payments",
        "family": "payments",
        "required_all": ["FEDAPAY_PUBLIC_KEY"],
        "required_any": [
            ["FEDAPAY_SECRET_KEY", "FEDAPAY_ENV"],
            ["FEDAPAY_SECRET_KEY", "FEDAPAY_ENVIRONMENT"],
            ["FEDAPAY_API_KEY", "FEDAPAY_ENV"],
            ["FEDAPAY_API_KEY", "FEDAPAY_ENVIRONMENT"],
        ],
        "rotation_supported": "api",
        "apply_contract_mode": APPLY_CONTRACT_PROBE_ONLY,
        "api_adapter": "fedapay",
        "api_apply_required_any": [
            ["FEDAPAY_SECRET_KEY", "FEDAPAY_ENV"],
            ["FEDAPAY_SECRET_KEY", "FEDAPAY_ENVIRONMENT"],
            ["FEDAPAY_API_KEY", "FEDAPAY_ENV"],
            ["FEDAPAY_API_KEY", "FEDAPAY_ENVIRONMENT"],
        ],
        "rollback_supported": True,
    },
    {
        "provider_id": "iap_apple",
        "label": "Apple IAP",
        "family": "iap",
        "required_all": ["APPLE_IAP_PRIVATE_KEY_PATH", "APPLE_IAP_KEY_ID", "APPLE_IAP_ISSUER_ID"],
        "rotation_supported": "manual",
        "apply_contract_mode": APPLY_CONTRACT_MANUAL,
        "manual_constraint_code": "provider_console_key_lifecycle",
        "rollback_supported": True,
    },
    {
        "provider_id": "iap_google",
        "label": "Google Play IAP",
        "family": "iap",
        "required_all": ["GOOGLE_PLAY_PACKAGE_NAME"],
        "required_any": [["GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH"], ["GOOGLE_PLAY_SERVICE_ACCOUNT_PATH"]],
        "rotation_supported": "manual",
        "apply_contract_mode": APPLY_CONTRACT_MANUAL,
        "manual_constraint_code": "provider_console_key_lifecycle",
        "rollback_supported": True,
    },
    {
        "provider_id": "oauth_google",
        "label": "Google OAuth",
        "family": "oauth",
        "required_all": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        "api_adapter": "google_oauth_refresh",
        "api_apply_required_all": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_ROTATION_REFRESH_TOKEN"],
        "rotation_supported": "hybrid",
        "apply_contract_mode": APPLY_CONTRACT_PROBE_ONLY,
        "rollback_supported": True,
    },
    {
        "provider_id": "oauth_microsoft",
        "label": "Microsoft OAuth",
        "family": "oauth",
        "required_all": ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"],
        "required_any": [["MS_SSO_REGISTERED_REDIRECT_URIS"], ["MS_SSO_CANONICAL_HOST"]],
        "rotation_supported": "api",
        "apply_contract_mode": APPLY_CONTRACT_API_ROTATE,
        "api_adapter": "microsoft_oauth_cc",
        "api_apply_required_all": [
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_TENANT_ID",
            "AZURE_ROTATION_SCOPE",
            "AZURE_ROTATION_APP_OBJECT_ID",
        ],
        "rollback_supported": True,
    },
    {
        "provider_id": "oauth_apple",
        "label": "Apple OAuth",
        "family": "oauth",
        "required_all": ["APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY"],
        "rotation_supported": "manual",
        "apply_contract_mode": APPLY_CONTRACT_MANUAL,
        "manual_constraint_code": "provider_console_key_lifecycle",
        "rollback_supported": True,
    },
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_has(key: str) -> bool:
    return bool(str(os.environ.get(key) or "").strip())


def _rotation_target_environment() -> str:
    raw = str(os.environ.get("KEY_ROTATION_TARGET_ENV") or os.environ.get("APP_ENV") or "live").strip().lower()
    if raw in {"prod", "production"}:
        return "live"
    if raw in {"dev", "development", "staging", "stage"}:
        return "sandbox"
    return raw or "live"


def _rotate_lifecycle_enabled() -> bool:
    return str(os.environ.get("KEY_ROTATION_ENABLE_PROVIDER_SIDE_LIFECYCLE") or "false").lower() == "true"


def _resolve_api_adapter_missing_requirements(defn: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for key in defn.get("api_apply_required_all", []):
        if not _env_has(key):
            missing.append(key)

    groups = defn.get("api_apply_required_any", [])
    if groups and not any(all(_env_has(item) for item in group) for group in groups):
        missing.append("one_of:" + " | ".join(["+".join(group) for group in groups]))
    return missing


def _infer_adapter_missing_reason(missing_items: List[str]) -> str:
    normalized = " ".join(missing_items).lower()
    if "scope" in normalized:
        return "missing_rotation_scope"
    if "tenant" in normalized:
        return "missing_rotation_tenant"
    if "refresh_token" in normalized:
        return "missing_rotation_refresh_token"
    return "api_adapter_credentials_missing"


def _provider_environment_mismatch(defn: Dict[str, Any]) -> Optional[str]:
    provider_id = str(defn.get("provider_id") or "")
    target_env = _rotation_target_environment()

    if provider_id == "payments_stripe":
        key = _first_env(["STRIPE_ROTATION_TARGET_SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_API_KEY"])
        if key.startswith("sk_test_") and target_env == "live":
            return "stripe_key_mode_test_for_live_target"
        if key.startswith("sk_live_") and target_env in {"sandbox", "test"}:
            return "stripe_key_mode_live_for_sandbox_target"

    if provider_id == "payments_paypal":
        mode = str(os.environ.get("PAYPAL_ENV") or os.environ.get("PAYPAL_MODE") or "live").strip().lower()
        if mode not in {"live", "sandbox"}:
            return "paypal_env_invalid"
        if mode == "sandbox" and target_env == "live":
            return "paypal_mode_sandbox_for_live_target"

    if provider_id == "payments_fedapay":
        mode = str(os.environ.get("FEDAPAY_ENV") or os.environ.get("FEDAPAY_ENVIRONMENT") or "live").strip().lower()
        if mode not in {"live", "sandbox", "test"}:
            return "fedapay_env_invalid"
        if mode in {"sandbox", "test"} and target_env == "live":
            return "fedapay_mode_test_for_live_target"

    return None


def _group_requirements_satisfied(groups: List[List[str]]) -> bool:
    if not groups:
        return True
    return any(all(_env_has(item) for item in group) for group in groups)


def _provider_api_adapter_available(defn: Dict[str, Any]) -> bool:
    adapter = str(defn.get("api_adapter") or "").strip()
    if not adapter:
        return False
    return len(_resolve_api_adapter_missing_requirements(defn)) == 0


def _resolve_apply_capability(provider: Dict[str, Any]) -> Dict[str, Any]:
    live_apply_enabled = str(os.environ.get("KEY_ROTATION_API_LIVE_ENABLE") or "true").lower() == "true"
    rotation_supported = str(provider.get("rotation_supported") or "manual")
    api_adapter_available = bool(provider.get("api_adapter_available"))
    contract_mode = str(provider.get("apply_contract_mode") or "").strip()
    adapter_missing_requirements = list(provider.get("api_adapter_missing_requirements") or [])

    if contract_mode and contract_mode not in VALID_APPLY_CONTRACTS:
        return {
            "status": STEP_STATUS_CONTRACT_REJECTED,
            "reason": "unknown_apply_contract_mode",
            "message": "Provider apply contract mode is invalid.",
            "contract_mode": contract_mode,
        }

    if provider.get("readiness_state") != "ready":
        return {
            "status": READINESS_STATUS_BLOCKED,
            "reason": "provider_not_configured",
            "message": "Provider configuration is incomplete.",
            "contract_mode": contract_mode,
        }

    if contract_mode == APPLY_CONTRACT_MANUAL or rotation_supported not in {"api", "hybrid"}:
        return {
            "status": READINESS_STATUS_MANUAL_BY_CONSTRAINT,
            "reason": "provider_manual_only",
            "message": "Provider requires manual evidence-driven workflow.",
            "contract_mode": APPLY_CONTRACT_MANUAL,
        }

    if not live_apply_enabled:
        return {
            "status": READINESS_STATUS_GUARDED,
            "reason": "live_api_apply_disabled",
            "message": "KEY_ROTATION_API_LIVE_ENABLE is disabled.",
            "contract_mode": contract_mode,
        }

    if not api_adapter_available:
        missing_reason = _infer_adapter_missing_reason(adapter_missing_requirements)
        return {
            "status": READINESS_STATUS_ADAPTER_MISSING,
            "reason": missing_reason,
            "message": "Provider API adapter credentials are incomplete.",
            "missing_requirements": adapter_missing_requirements,
            "contract_mode": contract_mode,
        }

    env_mismatch_reason = provider.get("environment_mismatch_reason")
    if env_mismatch_reason:
        return {
            "status": READINESS_STATUS_GUARDED,
            "reason": "rotation_env_mismatch",
            "message": "Provider credential mode does not match rotation target environment.",
            "environment_mismatch_reason": env_mismatch_reason,
            "contract_mode": contract_mode,
        }

    if contract_mode == APPLY_CONTRACT_API_ROTATE:
        if not _rotate_lifecycle_enabled():
            return {
                "status": READINESS_STATUS_GUARDED,
                "reason": "provider_rotate_lifecycle_disabled",
                "message": "Provider-side create/revoke lifecycle is disabled by policy flag.",
                "contract_mode": contract_mode,
            }
        return {
            "status": READINESS_STATUS_API_ROTATE_READY,
            "reason": "api_rotation_contract_ready",
            "message": "Provider supports API-driven rotation cutover.",
            "contract_mode": contract_mode,
        }

    return {
        "status": READINESS_STATUS_API_PROBE_READY,
        "reason": "api_probe_contract_ready",
        "message": "Provider supports API credential validation (probe-only) in current environment.",
        "contract_mode": contract_mode,
    }


def _provider_readiness(defn: Dict[str, Any]) -> Dict[str, Any]:
    missing: List[str] = []
    for key in defn.get("required_all", []):
        if not _env_has(key):
            missing.append(key)

    any_groups = defn.get("required_any", [])
    if any_groups:
        group_ok = False
        for group in any_groups:
            if all(_env_has(item) for item in group):
                group_ok = True
                break
        if not group_ok:
            missing.append(" | ".join(["+".join(group) for group in any_groups]))

    configured = len(missing) == 0
    contract_mode = str(defn.get("apply_contract_mode") or APPLY_CONTRACT_MANUAL).strip() or APPLY_CONTRACT_MANUAL
    api_adapter_missing_requirements = _resolve_api_adapter_missing_requirements(defn)
    api_adapter_available = _provider_api_adapter_available(defn)
    environment_mismatch_reason = _provider_environment_mismatch(defn)

    provider_doc = {
        "provider_id": defn["provider_id"],
        "label": defn["label"],
        "family": defn["family"],
        "integrated": True,
        "configured": configured,
        "missing_requirements": missing,
        "rotation_supported": defn.get("rotation_supported", "manual"),
        "apply_contract_mode": contract_mode,
        "api_adapter": defn.get("api_adapter"),
        "api_adapter_available": api_adapter_available,
        "api_adapter_missing_requirements": api_adapter_missing_requirements,
        "environment_mismatch_reason": environment_mismatch_reason,
        "manual_constraint_code": defn.get("manual_constraint_code"),
        "rollback_supported": bool(defn.get("rollback_supported", False)),
        "readiness_state": "ready" if configured else "blocked",
    }
    provider_doc["apply_capability"] = _resolve_apply_capability(provider_doc)
    return provider_doc


def _build_readiness_map() -> Dict[str, Dict[str, Any]]:
    return {item["provider_id"]: _provider_readiness(item) for item in PROVIDER_DEFINITIONS}


def _provider_go_live_assessment(provider: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = str(provider.get("provider_id") or "")
    contract_mode = str(provider.get("apply_contract_mode") or "").strip()
    apply_capability = provider.get("apply_capability") or {}
    apply_status = str(apply_capability.get("status") or "unknown").strip()
    apply_reason = str(apply_capability.get("reason") or "").strip()
    hard_blockers: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []

    if provider.get("readiness_state") != "ready":
        hard_blockers.append(
            {
                "code": "provider_not_configured",
                "message": "Provider base configuration is incomplete.",
                "missing_requirements": provider.get("missing_requirements", []),
            }
        )

    if contract_mode == APPLY_CONTRACT_MANUAL:
        advisories.append(
            {
                "code": "manual_workflow_required",
                "message": "Provider is manual-by-constraint and must use manual evidence workflow.",
                "manual_constraint_code": provider.get("manual_constraint_code"),
            }
        )

    if apply_status == READINESS_STATUS_ADAPTER_MISSING:
        hard_blockers.append(
            {
                "code": apply_reason or "api_adapter_credentials_missing",
                "message": "Provider adapter requirements are incomplete.",
                "missing_requirements": apply_capability.get("missing_requirements") or provider.get("api_adapter_missing_requirements") or [],
            }
        )

    if apply_status == READINESS_STATUS_GUARDED:
        hard_blockers.append(
            {
                "code": apply_reason or "apply_guarded",
                "message": str(apply_capability.get("message") or "Provider apply is currently guarded."),
            }
        )

    if apply_status == READINESS_STATUS_BLOCKED:
        hard_blockers.append(
            {
                "code": apply_reason or "provider_not_configured",
                "message": str(apply_capability.get("message") or "Provider is blocked."),
            }
        )

    if contract_mode == APPLY_CONTRACT_API_ROTATE and apply_status != READINESS_STATUS_API_ROTATE_READY:
        hard_blockers.append(
            {
                "code": "rotate_contract_not_ready",
                "message": "Provider rotate contract is not ready for live apply.",
                "expected_status": READINESS_STATUS_API_ROTATE_READY,
                "current_status": apply_status,
            }
        )

    if contract_mode == APPLY_CONTRACT_PROBE_ONLY and apply_status != READINESS_STATUS_API_PROBE_READY:
        advisories.append(
            {
                "code": "probe_contract_not_ready",
                "message": "Probe-only contract cannot validate credentials in current environment.",
                "current_status": apply_status,
            }
        )

    return {
        "provider_id": provider_id,
        "label": provider.get("label"),
        "contract_mode": contract_mode,
        "apply_status": apply_status,
        "apply_reason": apply_reason,
        "hard_blockers": hard_blockers,
        "advisories": advisories,
        "hard_blocked": len(hard_blockers) > 0,
        "ready_for_live_apply": (
            (contract_mode == APPLY_CONTRACT_API_ROTATE and apply_status == READINESS_STATUS_API_ROTATE_READY)
            or (contract_mode == APPLY_CONTRACT_PROBE_ONLY and apply_status == READINESS_STATUS_API_PROBE_READY)
        ),
    }


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("utf-8"))


def _approval_secret() -> bytes:
    secret = str(os.environ.get("POLICY_GATE_AUDIT_SECRET") or os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise HTTPException(status_code=500, detail="Approval signing secret unavailable")
    return secret.encode("utf-8")


def _sign_approval_token(plan_id: str, actor_user_id: str, expires_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "plan_id": plan_id,
        "actor_user_id": actor_user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "nonce": uuid.uuid4().hex[:16],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_approval_secret(), canonical, hashlib.sha256).digest()
    return f"{_b64url_encode(canonical)}.{_b64url_encode(sig)}"


def _verify_approval_token(token: str, expected_plan_id: str) -> Dict[str, Any]:
    try:
        payload_b64, sig_b64 = str(token or "").split(".", 1)
        payload_raw = _b64url_decode(payload_b64)
        provided_sig = _b64url_decode(sig_b64)
        expected_sig = hmac.new(_approval_secret(), payload_raw, hashlib.sha256).digest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise HTTPException(status_code=400, detail="Invalid approval token signature")
        payload = json.loads(payload_raw.decode("utf-8"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed approval token")

    if str(payload.get("plan_id") or "") != expected_plan_id:
        raise HTTPException(status_code=400, detail="Approval token plan mismatch")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if int(payload.get("exp") or 0) < now_ts:
        raise HTTPException(status_code=400, detail="Approval token expired")
    return payload


def _select_providers(requested: List[str], readiness_map: Dict[str, Dict[str, Any]]) -> List[str]:
    if not requested:
        return list(readiness_map.keys())
    unknown = [item for item in requested if item not in readiness_map]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown providers requested: {', '.join(unknown)}")
    return requested


def _build_rotation_targets() -> List[Dict[str, Any]]:
    readiness_map = _build_readiness_map()
    rows: List[Dict[str, Any]] = []
    for item in PROVIDER_DEFINITIONS:
        rid = item["provider_id"]
        ready = readiness_map[rid]
        rows.append(
            {
                "provider_id": rid,
                "label": item["label"],
                "family": item["family"],
                "configured": ready["configured"],
                "rotation_supported": item.get("rotation_supported", "manual"),
                "apply_contract_mode": ready.get("apply_contract_mode"),
                "manual_constraint_code": ready.get("manual_constraint_code"),
                "api_adapter": item.get("api_adapter"),
                "api_adapter_available": bool(ready.get("api_adapter_available")),
                "api_adapter_missing_requirements": ready.get("api_adapter_missing_requirements", []),
                "environment_mismatch_reason": ready.get("environment_mismatch_reason"),
                "apply_capability": ready.get("apply_capability"),
                "rollback_supported": bool(item.get("rollback_supported", False)),
                "required_all": item.get("required_all", []),
                "required_any": item.get("required_any", []),
                "missing_requirements": ready["missing_requirements"],
            }
        )
    return rows


def _build_dry_run_document(user_id: str) -> Dict[str, Any]:
    run_id = f"keyrot_{uuid.uuid4().hex[:12]}"
    created_at = _utc_now_iso()
    targets = _build_rotation_targets()
    steps = [
        "R1 readiness evaluation",
        "R2 prepare + approval",
        "R3 guarded apply",
        "R4 rollback fallback",
        "R5 evidence archival",
    ]
    return {
        "run_id": run_id,
        "mode": "dry_run",
        "status": "completed",
        "created_at": created_at,
        "created_by": user_id,
        "targets": targets,
        "steps": steps,
        "summary": {
            "total_targets": len(targets),
            "configured_targets": len([t for t in targets if t.get("configured")]),
            "unconfigured_targets": len([t for t in targets if not t.get("configured")]),
        },
    }


def _provider_runbook(provider_id: str) -> List[str]:
    mapping = {
        "payments_stripe": [
            "Create new restricted key in Stripe dashboard/API",
            "Deploy new key through secret manager",
            "Validate checkout + webhook signatures",
        ],
        "payments_paypal": [
            "Create/rotate PayPal app secret",
            "Update secret manager and refresh token caches",
            "Validate capture + webhook verification",
        ],
        "payments_fedapay": [
            "Issue replacement FedaPay API key",
            "Rotate webhook secret binding",
            "Validate payment intent + callback signatures",
        ],
        "iap_apple": [
            "Issue replacement Apple IAP private key",
            "Update APPLE_IAP_* env references",
            "Validate signed transaction verification",
        ],
        "iap_google": [
            "Generate new Google Play service-account key",
            "Rotate service account path secret",
            "Validate Google purchase token verification",
        ],
        "oauth_google": [
            "Rotate Google OAuth client secret",
            "Update secret manager and callback checks",
            "Validate Google OAuth login flow",
        ],
        "oauth_microsoft": [
            "Rotate Azure app client secret",
            "Update AZURE_CLIENT_SECRET in vault",
            "Validate MS OAuth callback + token exchange",
        ],
        "oauth_apple": [
            "Rotate Apple Sign-In private key material",
            "Update APPLE_PRIVATE_KEY/KEY_ID/TEAM_ID",
            "Validate Apple code exchange flow",
        ],
    }
    return mapping.get(provider_id, ["Rotate key via provider console", "Update secret manager", "Validate end-to-end flow"])


def _first_env(keys: List[str]) -> str:
    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _rotation_policy_snapshot() -> Dict[str, Any]:
    def _int_env(key: str, fallback: int) -> int:
        try:
            value = int(str(os.environ.get(key) or fallback))
            return value
        except Exception:
            return fallback

    return {
        "default_cadence_days": _int_env("KEY_ROTATION_DEFAULT_CADENCE_DAYS", 90),
        "high_risk_cadence_days": _int_env("KEY_ROTATION_HIGH_RISK_CADENCE_DAYS", 30),
        "require_dual_approval": str(os.environ.get("KEY_ROTATION_REQUIRE_DUAL_APPROVAL") or "true").lower() == "true",
        "require_evidence_links_for_manual": str(os.environ.get("KEY_ROTATION_REQUIRE_MANUAL_EVIDENCE_LINKS") or "true").lower() == "true",
        "manual_min_links": _int_env("KEY_ROTATION_MANUAL_MIN_LINKS", 1),
        "manual_verified_min_links": _int_env("KEY_ROTATION_MANUAL_VERIFIED_MIN_LINKS", 2),
        "game_day_interval_days": _int_env("KEY_ROTATION_GAME_DAY_INTERVAL_DAYS", 90),
        "target_environment": _rotation_target_environment(),
    }


def _normalize_nonempty_lines(items: List[str]) -> List[str]:
    return [str(item).strip() for item in items if str(item).strip()]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _manual_evidence_rules() -> Dict[str, Any]:
    policy = _rotation_policy_snapshot()
    return {
        "require_links": bool(policy.get("require_evidence_links_for_manual")),
        "min_links": int(policy.get("manual_min_links") or 1),
        "min_links_verified": int(policy.get("manual_verified_min_links") or 2),
        "min_note_chars": int(str(os.environ.get("KEY_ROTATION_MANUAL_MIN_NOTE_CHARS") or "16")),
    }


def _runbook_monitor_default_config() -> Dict[str, Any]:
    return {
        "enabled": True,
        "safe_auto_mode": True,
        "allow_live_apply": False,
        "interval_hours": 3,
        "admin_email": str(os.environ.get("SECURITY_RUNBOOK_MONITOR_ADMIN_EMAIL") or "admin@realaicoach.app").strip(),
        "include_attestation": True,
    }


async def _get_runbook_monitor_config() -> Dict[str, Any]:
    defaults = _runbook_monitor_default_config()
    stored = await db.system_runtime_flags.find_one(
        {"key": "key_rotation_runbook_monitor_config"},
        {"_id": 0},
    ) or {}
    return {
        "key": "key_rotation_runbook_monitor_config",
        **defaults,
        **{k: v for k, v in stored.items() if k != "_id"},
    }


async def _set_runbook_monitor_config(update: Dict[str, Any], actor_user_id: str) -> Dict[str, Any]:
    current = await _get_runbook_monitor_config()
    next_config = {
        **current,
        **update,
        "updated_at": _utc_now_iso(),
        "updated_by": actor_user_id,
    }
    await db.system_runtime_flags.update_one(
        {"key": "key_rotation_runbook_monitor_config"},
        {"$set": next_config},
        upsert=True,
    )
    next_config.pop("_id", None)
    return next_config


def _runbook_monitor_rag(summary: Dict[str, Any]) -> str:
    if not bool(summary.get("policy_gate_passed", True)):
        return "RED"
    if summary.get("rotate_contract_hard_blocked", 0) > 0:
        return "AMBER"
    if not bool(summary.get("siem_webhook_configured")):
        return "AMBER"
    if summary.get("siem_webhook_validated") is False:
        return "AMBER"
    return "GREEN"


def _runbook_top_risks(summary: Dict[str, Any]) -> List[str]:
    risks: List[str] = []
    if summary.get("rotate_contract_hard_blocked", 0) > 0:
        risks.append("Rotate-contract providers are blocked by missing lifecycle prerequisites.")
    if not bool(summary.get("siem_webhook_configured")):
        risks.append("SIEM incident webhook is not configured in runtime environment.")
    if summary.get("siem_webhook_validated") is False:
        risks.append("SIEM webhook validation failed during this run.")
    if summary.get("manual_pending_evidence", 0) > 0:
        risks.append("Manual-by-constraint providers still have pending evidence closure.")
    if not risks:
        risks.append("No immediate high-risk blockers detected for safe auto monitoring.")
    return risks


def _render_runbook_monitor_dashboard_markdown(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    top_risks = payload.get("top_risks") or []
    milestones = payload.get("milestones") or {}
    rag = payload.get("rag") or "AMBER"
    latest_bundle = payload.get("latest_bundle") or {}

    lines = [
        "# Global Security Incident Plan — Go-Live Runbook (Amber ➜ Green)",
        "",
        "## Continuous Monitoring Snapshot (Safe Auto)",
        f"- Run ID: {payload.get('monitor_run_id')}",
        f"- Trigger Source: {payload.get('trigger_source')}",
        f"- Executed At: {payload.get('executed_at')}",
        f"- Mode: {'SAFE_AUTO' if bool(summary.get('safe_auto_mode')) else 'MANUAL'}",
        "",
        "## Overall RAG",
        f"- Status: **{rag}**",
        "",
        "## Key Metrics",
        f"- API Rotate Ready: {summary.get('api_rotate_ready', 0)}",
        f"- API Probe Ready: {summary.get('api_probe_only_ready', 0)}",
        f"- Manual By Constraint: {summary.get('manual_by_constraint', 0)}",
        f"- Rotate Contract Hard Blocked: {summary.get('rotate_contract_hard_blocked', 0)}",
        f"- Policy Gate Passed: {summary.get('policy_gate_passed')}",
        f"- SIEM Webhook Configured: {summary.get('siem_webhook_configured')}",
        f"- SIEM Webhook Validated (this run): {summary.get('siem_webhook_validated')}",
        "",
        "## Top Risks",
    ]
    for risk in top_risks[:5]:
        lines.append(f"- {risk}")

    lines.extend(
        [
            "",
            "## 30 / 60 / 90 Day Closure Milestones",
            f"- 30d: {milestones.get('d30')}",
            f"- 60d: {milestones.get('d60')}",
            f"- 90d: {milestones.get('d90')}",
            "",
            "## Latest Compliance Reference",
            f"- Bundle ID: {latest_bundle.get('bundle_id', 'N/A')}",
            f"- Generated At: {latest_bundle.get('generated_at', 'N/A')}",
        ]
    )
    return "\n".join(lines)


async def run_security_runbook_monitor_cycle(
    trigger_source: str,
    force: bool = False,
    include_attestation_override: Optional[bool] = None,
) -> Dict[str, Any]:
    config = await _get_runbook_monitor_config()
    if not force and not bool(config.get("enabled", True)):
        return {
            "status": "skipped",
            "reason": "monitor_paused",
            "config": config,
        }

    interval_hours = max(1, int(config.get("interval_hours") or 3))
    latest_run = await db.security_runbook_monitor_runs.find_one({}, {"_id": 0}, sort=[("executed_at", -1)]) or {}
    if not force and latest_run.get("executed_at"):
        try:
            last_run_at = datetime.fromisoformat(str(latest_run.get("executed_at")).replace("Z", "+00:00"))
            if last_run_at.tzinfo is None:
                last_run_at = last_run_at.replace(tzinfo=timezone.utc)
            elapsed = datetime.now(timezone.utc) - last_run_at.astimezone(timezone.utc)
            if elapsed.total_seconds() < (interval_hours * 3600 * 0.9):
                return {
                    "status": "skipped",
                    "reason": "cooldown",
                    "next_eta_seconds": int((interval_hours * 3600) - elapsed.total_seconds()),
                    "latest_run": latest_run,
                }
        except Exception:
            pass

    executed_at = _utc_now_iso()
    monitor_run_id = f"keyrot_mon_{uuid.uuid4().hex[:12]}"
    include_attestation = bool(config.get("include_attestation", True))
    if include_attestation_override is not None:
        include_attestation = bool(include_attestation_override)

    readiness_map = _build_readiness_map()
    providers = [readiness_map[item["provider_id"]] for item in PROVIDER_DEFINITIONS]
    assessments = [_provider_go_live_assessment(provider) for provider in providers]

    policy_gate_snapshot = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=False)
    policy_snapshot = _rotation_policy_snapshot()
    webhook_configured = bool(str(os.environ.get("SIEM_INCIDENT_WEBHOOK_URL") or "").strip())

    webhook_validation = None
    if include_attestation:
        webhook_validation = await _validate_siem_incident_webhook_delivery(
            actor_user_id="system:runbook-monitor",
            context="continuous_monitor",
            related_run_id=None,
        )

    latest_policy_attestation = await db.security_key_rotation_policy_attestations.find_one({}, {"_id": 0}, sort=[("attested_at", -1)]) or {}
    last_game_day = await db.system_runtime_flags.find_one({"key": "key_rotation_last_game_day"}, {"_id": 0}) or {}
    latest_bundle = await db.security_key_rotation_compliance_bundles.find_one({}, {"_id": 0, "bundle_id": 1, "generated_at": 1}, sort=[("generated_at", -1)]) or {}

    apply_statuses = [str((provider.get("apply_capability") or {}).get("status") or "unknown") for provider in providers]
    summary = {
        "safe_auto_mode": bool(config.get("safe_auto_mode", True)),
        "allow_live_apply": bool(config.get("allow_live_apply", False)),
        "target_environment": _rotation_target_environment(),
        "total_providers": len(providers),
        "api_rotate_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_ROTATE_READY]),
        "api_probe_only_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_PROBE_READY]),
        "manual_by_constraint": len([s for s in apply_statuses if s == READINESS_STATUS_MANUAL_BY_CONSTRAINT]),
        "adapter_missing": len([s for s in apply_statuses if s == READINESS_STATUS_ADAPTER_MISSING]),
        "rotate_contract_hard_blocked": len([
            row for row in assessments
            if row.get("contract_mode") == APPLY_CONTRACT_API_ROTATE and row.get("hard_blocked")
        ]),
        "policy_gate_passed": bool(policy_gate_snapshot.get("passed")),
        "siem_webhook_configured": webhook_configured,
        "siem_webhook_validated": None if webhook_validation is None else bool(webhook_validation.get("validated")),
        "manual_pending_evidence": await db.security_key_rotation_steps.count_documents({"status": STEP_STATUS_MANUAL_PENDING}),
        "manual_evidence_uploaded": await db.security_key_rotation_steps.count_documents({"status": STEP_STATUS_MANUAL_EVIDENCE_UPLOADED}),
    }
    summary["manual_required"] = summary["manual_pending_evidence"] + summary["manual_evidence_uploaded"]

    rag = _runbook_monitor_rag(summary)
    top_risks = _runbook_top_risks(summary)
    milestones = {
        "d30": "Close rotate-contract hard blockers and webhook configuration gaps.",
        "d60": "Verify first live cutover+revoke evidence and expand rotate-ready providers.",
        "d90": "Sustain compliance bundle automation and drift-free governance cadence.",
    }

    dashboard_payload = {
        "monitor_run_id": monitor_run_id,
        "trigger_source": trigger_source,
        "executed_at": executed_at,
        "summary": summary,
        "rag": rag,
        "top_risks": top_risks,
        "milestones": milestones,
        "latest_bundle": latest_bundle,
    }
    dashboard_markdown = _render_runbook_monitor_dashboard_markdown(dashboard_payload)

    run_doc = {
        "monitor_run_id": monitor_run_id,
        "executed_at": executed_at,
        "trigger_source": trigger_source,
        "config_snapshot": config,
        "summary": summary,
        "rag": rag,
        "top_risks": top_risks,
        "go_live_checklist": {
            "providers": assessments,
            "summary": {
                "total": len(assessments),
                "hard_blocked": len([row for row in assessments if row.get("hard_blocked")]),
                "rotate_contract_hard_blocked": summary.get("rotate_contract_hard_blocked"),
            },
        },
        "policy_snapshot": policy_snapshot,
        "policy_gate_snapshot": policy_gate_snapshot,
        "webhook_validation": webhook_validation,
        "last_attestation": latest_policy_attestation,
        "last_game_day": last_game_day,
        "latest_bundle": latest_bundle,
    }
    await db.security_runbook_monitor_runs.insert_one(run_doc)
    run_doc.pop("_id", None)

    dashboard_doc = {
        "dashboard_id": f"keyrot_dash_{uuid.uuid4().hex[:12]}",
        "monitor_run_id": monitor_run_id,
        "generated_at": executed_at,
        "title": "Global Security Incident Plan — Go-Live Runbook (Amber ➜ Green)",
        "rag": rag,
        "content_markdown": dashboard_markdown,
    }
    await db.security_runbook_monitor_dashboard_snapshots.insert_one(dashboard_doc)
    dashboard_doc.pop("_id", None)

    notification_doc = {
        "notification_id": f"keyrot_ntf_{uuid.uuid4().hex[:12]}",
        "monitor_run_id": monitor_run_id,
        "created_at": executed_at,
        "recipient_email": config.get("admin_email"),
        "subject": f"[Security Runbook Monitor] {rag} - {executed_at}",
        "channel": "email",
        "success": False,
        "error": None,
    }

    # ── Noise control: email only on RAG change, once-daily summary, or manual runs ──
    previous_rag = str(latest_run.get("rag") or "").strip().upper()
    is_scheduled = trigger_source == "scheduler"
    send_reason: Optional[str] = None
    if not is_scheduled:
        send_reason = "manual"
    elif not previous_rag or previous_rag != rag:
        send_reason = "rag_change"
    else:
        emailed_today = await db.security_runbook_monitor_notifications.count_documents(
            {"success": True, "created_at": {"$gte": executed_at[:10]}}
        )
        if emailed_today == 0:
            send_reason = "daily_summary"
    notification_doc["send_reason"] = send_reason
    notification_doc["previous_rag"] = previous_rag or None

    recipient_email = str(config.get("admin_email") or "").strip()
    if recipient_email and send_reason is None:
        notification_doc["suppressed"] = True
        notification_doc["error"] = None
    elif recipient_email:
        try:
            from utils.email_service import send_email, is_email_configured
            from utils.email_templates import build_security_runbook_monitor_report_email

            if is_email_configured():
                email_tpl = build_security_runbook_monitor_report_email(
                    rag=rag,
                    monitor_run_id=monitor_run_id,
                    trigger_source=trigger_source,
                    executed_at=executed_at,
                    mode="SAFE_AUTO" if bool(summary.get("safe_auto_mode")) else "MANUAL",
                    metrics=summary,
                    top_risks=top_risks,
                    milestones=milestones,
                    bundle_id=str(latest_bundle.get("bundle_id") or "N/A"),
                    bundle_generated_at=str(latest_bundle.get("generated_at") or "N/A"),
                    send_reason=send_reason,
                )
                send_result = await send_email(
                    recipient_email=recipient_email,
                    subject=email_tpl.subject,
                    content=email_tpl.html,
                    contact_external_id=recipient_email,
                    content_text=email_tpl.text,
                    template_key="security_runbook_monitor_report",
                    dedupe_key=f"runbook-monitor-{monitor_run_id}",
                )
                notification_doc["success"] = bool(send_result.get("success"))
                notification_doc["error"] = send_result.get("error") if not send_result.get("success") else None
                notification_doc["provider_response"] = send_result

                await db.admin_sent_emails.insert_one(
                    {
                        "email_id": f"email_{uuid.uuid4().hex[:12]}",
                        "sent_by": "system:runbook-monitor",
                        "recipient_email": recipient_email,
                        "subject": notification_doc["subject"],
                        "body": dashboard_markdown,
                        "sent_at": executed_at,
                        "email_result": bool(send_result.get("success")),
                    }
                )
            else:
                notification_doc["error"] = "Email service not configured"
        except Exception as exc:
            notification_doc["error"] = str(exc)[:220]

    await db.security_runbook_monitor_notifications.insert_one(notification_doc)
    notification_doc.pop("_id", None)

    return {
        "status": "ok",
        "monitor_run_id": monitor_run_id,
        "executed_at": executed_at,
        "rag": rag,
        "summary": summary,
        "top_risks": top_risks,
        "notification": notification_doc,
        "dashboard": dashboard_doc,
    }


async def _validate_siem_incident_webhook_delivery(
    actor_user_id: str,
    context: str,
    related_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    webhook_url = str(os.environ.get("SIEM_INCIDENT_WEBHOOK_URL") or "").strip()
    now = _utc_now_iso()
    if not webhook_url:
        result = {
            "configured": False,
            "validated": False,
            "status": "not_configured",
            "validated_at": now,
            "context": context,
        }
        await db.siem_incident_webhook_log.insert_one(
            {
                "source": "security_key_rotation_policy_validation",
                "ok": False,
                "status": "not_configured",
                "sent_at": now,
                "context": context,
                "related_run_id": related_run_id,
                "actor_user_id": actor_user_id,
            }
        )
        return result

    payload = {
        "type": "security_key_rotation_webhook_validation",
        "validation_id": f"keyrot_wv_{uuid.uuid4().hex[:12]}",
        "context": context,
        "related_run_id": related_run_id,
        "actor_user_id": actor_user_id,
        "ts": now,
    }
    max_attempts = max(1, int(str(os.environ.get("SIEM_WEBHOOK_VALIDATION_MAX_RETRIES") or "3")))
    retry_backoff_ms = max(100, int(str(os.environ.get("SIEM_WEBHOOK_VALIDATION_RETRY_BACKOFF_MS") or "350")))
    attempts: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {
        "configured": True,
        "validated": False,
        "status": "error",
        "validated_at": now,
        "context": context,
        "attempt_count": 0,
    }

    for idx in range(max_attempts):
        attempt_no = idx + 1
        attempt_doc: Dict[str, Any] = {"attempt": attempt_no, "at": _utc_now_iso()}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(webhook_url, json=payload)
            ok = bool(200 <= int(response.status_code) < 300)
            attempt_doc.update(
                {
                    "ok": ok,
                    "status_code": int(response.status_code),
                    "response_hint": (response.text or "")[:180],
                }
            )
            attempts.append(attempt_doc)

            if ok:
                result = {
                    "configured": True,
                    "validated": True,
                    "status": "success",
                    "status_code": int(response.status_code),
                    "validated_at": _utc_now_iso(),
                    "context": context,
                    "response_hint": (response.text or "")[:180],
                    "attempt_count": attempt_no,
                }
                break

            result = {
                "configured": True,
                "validated": False,
                "status": "failed",
                "status_code": int(response.status_code),
                "validated_at": _utc_now_iso(),
                "context": context,
                "response_hint": (response.text or "")[:180],
                "attempt_count": attempt_no,
            }
        except Exception as exc:
            attempt_doc.update({"ok": False, "error": str(exc)[:220]})
            attempts.append(attempt_doc)
            result = {
                "configured": True,
                "validated": False,
                "status": "error",
                "validated_at": _utc_now_iso(),
                "context": context,
                "error": str(exc)[:220],
                "attempt_count": attempt_no,
            }

        if idx < max_attempts - 1:
            await asyncio.sleep(retry_backoff_ms / 1000.0)

    await db.siem_incident_webhook_log.insert_one(
        {
            "source": "security_key_rotation_policy_validation",
            "ok": bool(result.get("validated")),
            "status": result.get("status"),
            "status_code": result.get("status_code"),
            "error": result.get("error"),
            "sent_at": now,
            "context": context,
            "related_run_id": related_run_id,
            "actor_user_id": actor_user_id,
            "attempts": attempts,
            "attempt_count": result.get("attempt_count"),
        }
    )

    if not bool(result.get("validated")):
        await db.siem_incident_webhook_dead_letter.insert_one(
            {
                "dead_letter_id": f"siem_wdl_{uuid.uuid4().hex[:12]}",
                "source": "security_key_rotation_policy_validation",
                "created_at": _utc_now_iso(),
                "context": context,
                "related_run_id": related_run_id,
                "actor_user_id": actor_user_id,
                "payload": payload,
                "result": result,
                "attempts": attempts,
                "status": "pending_retry",
            }
        )

    result["attempts"] = attempts
    return result


async def _activate_policy_gate_apply_window(plan_id: str, run_id: str, actor_user_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_doc = {
        "key": "key_rotation_apply_window_state",
        "window_id": f"keyrot_win_{uuid.uuid4().hex[:12]}",
        "state": "active",
        "reason": "key_rotation_live_apply",
        "plan_id": plan_id,
        "run_id": run_id,
        "actor_user_id": actor_user_id,
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=20)).isoformat(),
        "force_checks": [
            "admin_e2e_health_gate",
            "subscription_plan_guardrail",
            "sso_e2e_validation",
            "cia_trust_score",
        ],
        "updated_at": now.isoformat(),
    }
    await db.system_runtime_flags.update_one(
        {"key": "key_rotation_apply_window_state"},
        {"$set": window_doc},
        upsert=True,
    )
    return window_doc


async def _deactivate_policy_gate_apply_window(window_doc: Dict[str, Any]) -> None:
    if not window_doc:
        return
    await db.system_runtime_flags.update_one(
        {"key": "key_rotation_apply_window_state"},
        {
            "$set": {
                "key": "key_rotation_apply_window_state",
                "window_id": window_doc.get("window_id"),
                "state": "closed",
                "reason": "key_rotation_live_apply_completed",
                "plan_id": window_doc.get("plan_id"),
                "run_id": window_doc.get("run_id"),
                "actor_user_id": window_doc.get("actor_user_id"),
                "started_at": window_doc.get("started_at"),
                "expires_at": window_doc.get("expires_at"),
                "closed_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
            }
        },
        upsert=True,
    )


async def _refresh_policy_gate_prerequisites(request: Request) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []

    async def _run(label: str, fn):
        try:
            result = await fn()
            actions.append({"action": label, "ok": True})
            return result
        except Exception as exc:
            actions.append({"action": label, "ok": False, "error": str(exc)[:220]})
            return None

    try:
        from scheduler_jobs import (
            scheduled_admin_e2e_health_gate,
            scheduled_production_security_policy_gate,
            scheduled_subscription_plan_guardrail,
        )
    except Exception as exc:
        actions.append({"action": "scheduler_job_import", "ok": False, "error": str(exc)[:220]})
        return {"actions": actions}

    await _run("admin_e2e_health_gate", scheduled_admin_e2e_health_gate)
    await _run("subscription_plan_guardrail", scheduled_subscription_plan_guardrail)

    try:
        from routes.auth import run_sso_e2e_validation_internal

        validation = await run_sso_e2e_validation_internal(request)
        validation_state = "pass" if bool(validation.get("passed")) else "fail"
        await db.system_runtime_flags.update_one(
            {"key": "sso_e2e_validation_state"},
            {
                "$set": {
                    "key": "sso_e2e_validation_state",
                    "state": validation_state,
                    "last_run_at": validation.get("validated_at") or _utc_now_iso(),
                    "failed_checks": [
                        item.get("name")
                        for item in (validation.get("checks") or [])
                        if not item.get("passed")
                    ],
                }
            },
            upsert=True,
        )
        actions.append({"action": "sso_e2e_validation", "ok": True, "state": validation_state})
    except Exception as exc:
        actions.append({"action": "sso_e2e_validation", "ok": False, "error": str(exc)[:220]})

    try:
        from routes.cia_trust import cia_self_heal_heartbeat

        trust = await cia_self_heal_heartbeat(request)
        actions.append(
            {
                "action": "cia_trust_heartbeat",
                "ok": True,
                "trust_score": (trust.get("overview") or {}).get("trust_score"),
            }
        )
    except Exception as exc:
        actions.append({"action": "cia_trust_heartbeat", "ok": False, "error": str(exc)[:220]})

    await _run("production_security_policy_gate", scheduled_production_security_policy_gate)
    return {"actions": actions}


async def _apply_provider_api_stripe() -> Dict[str, Any]:
    api_key = _first_env(["STRIPE_ROTATION_TARGET_SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_API_KEY"])
    if not api_key:
        return {"ok": False, "error": "stripe_key_missing"}

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get("https://api.stripe.com/v1/balance", auth=(api_key, ""))

    return {
        "ok": response.status_code == 200,
        "status_code": int(response.status_code),
        "provider_endpoint": "GET /v1/balance",
        "response_hint": (response.text or "")[:180],
    }


async def _apply_provider_api_paypal() -> Dict[str, Any]:
    client_id = _first_env(["PAYPAL_ROTATION_CLIENT_ID", "PAYPAL_CLIENT_ID"])
    secret = _first_env(["PAYPAL_ROTATION_CLIENT_SECRET", "PAYPAL_SECRET", "PAYPAL_CLIENT_SECRET"])
    if not client_id or not secret:
        return {"ok": False, "error": "paypal_credentials_missing"}

    paypal_mode = str(os.environ.get("PAYPAL_ENV") or os.environ.get("PAYPAL_MODE") or "live").strip().lower()
    base_url = "https://api-m.sandbox.paypal.com" if paypal_mode == "sandbox" else "https://api-m.paypal.com"
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            f"{base_url}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {
        "ok": response.status_code == 200 and bool(payload.get("access_token")),
        "status_code": int(response.status_code),
        "provider_endpoint": "POST /v1/oauth2/token",
        "response_hint": str(payload.get("token_type") or payload.get("error") or "")[:120],
    }


async def _apply_provider_api_fedapay() -> Dict[str, Any]:
    secret_key = _first_env(["FEDAPAY_ROTATION_SECRET_KEY", "FEDAPAY_SECRET_KEY", "FEDAPAY_API_KEY"])
    if not secret_key:
        return {"ok": False, "error": "fedapay_secret_missing"}

    fedapay_mode = str(os.environ.get("FEDAPAY_ENV") or os.environ.get("FEDAPAY_ENVIRONMENT") or "live").strip().lower()
    base_url = "https://sandbox-api.fedapay.com" if fedapay_mode in {"test", "sandbox"} else "https://api.fedapay.com"
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            f"{base_url}/v1/transactions?{urlencode({'limit': 1})}",
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    return {
        "ok": int(response.status_code) < 400,
        "status_code": int(response.status_code),
        "provider_endpoint": "GET /v1/transactions?limit=1",
        "response_hint": (response.text or "")[:180],
    }


async def _apply_provider_api_google_oauth_refresh() -> Dict[str, Any]:
    client_id = _first_env(["GOOGLE_CLIENT_ID"])
    client_secret = _first_env(["GOOGLE_CLIENT_SECRET"])
    refresh_token = _first_env(["GOOGLE_ROTATION_REFRESH_TOKEN"])
    if not client_id or not client_secret or not refresh_token:
        return {"ok": False, "error": "google_oauth_refresh_credentials_missing"}

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {
        "ok": response.status_code == 200 and bool(payload.get("access_token")),
        "status_code": int(response.status_code),
        "provider_endpoint": "POST /token (refresh_token)",
        "response_hint": str(payload.get("token_type") or payload.get("error") or "")[:120],
    }


async def _apply_provider_api_microsoft_oauth_cc() -> Dict[str, Any]:
    tenant_id = _first_env(["AZURE_TENANT_ID"])
    client_id = _first_env(["AZURE_CLIENT_ID"])
    client_secret = _first_env(["AZURE_CLIENT_SECRET"])
    scope = _first_env(["AZURE_ROTATION_SCOPE"])
    if not tenant_id or not client_id or not client_secret or not scope:
        return {"ok": False, "error": "microsoft_oauth_credentials_missing"}

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scope,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {
        "ok": response.status_code == 200 and bool(payload.get("access_token")),
        "status_code": int(response.status_code),
        "provider_endpoint": "POST /oauth2/v2.0/token (client_credentials)",
        "response_hint": str(payload.get("token_type") or payload.get("error") or "")[:120],
    }


async def _apply_provider_api_microsoft_oauth_rotate(provider: Dict[str, Any]) -> Dict[str, Any]:
    tenant_id = _first_env(["AZURE_TENANT_ID"])
    client_id = _first_env(["AZURE_CLIENT_ID"])
    client_secret = _first_env(["AZURE_CLIENT_SECRET"])
    probe_scope = _first_env(["AZURE_ROTATION_SCOPE"])
    app_object_id = _first_env(["AZURE_ROTATION_APP_OBJECT_ID"])
    if not tenant_id or not client_id or not client_secret or not probe_scope or not app_object_id:
        return {"ok": False, "error": "microsoft_oauth_rotate_credentials_missing"}

    graph_scope = _first_env(["AZURE_ROTATION_GRAPH_SCOPE"]) or "https://graph.microsoft.com/.default"
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    now = datetime.now(timezone.utc)
    expiry_days = int(str(os.environ.get("AZURE_ROTATION_SECRET_VALID_DAYS") or "180"))
    display_name = f"key-rotation-{now.strftime('%Y%m%d%H%M%S')}"

    async with httpx.AsyncClient(timeout=14.0) as client:
        graph_token_response = await client.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": graph_scope,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        graph_token_payload = graph_token_response.json() if graph_token_response.headers.get("content-type", "").startswith("application/json") else {}
        graph_access_token = str(graph_token_payload.get("access_token") or "")
        if graph_token_response.status_code != 200 or not graph_access_token:
            return {
                "ok": False,
                "error": "microsoft_graph_token_failed",
                "status_code": int(graph_token_response.status_code),
                "provider_endpoint": "POST /oauth2/v2.0/token (graph)",
                "response_hint": str(graph_token_payload.get("error") or graph_token_payload.get("error_description") or "")[:180],
            }

        add_password_url = f"https://graph.microsoft.com/v1.0/applications/{app_object_id}/addPassword"
        add_password_response = await client.post(
            add_password_url,
            json={
                "passwordCredential": {
                    "displayName": display_name,
                    "endDateTime": (now + timedelta(days=expiry_days)).isoformat(),
                }
            },
            headers={
                "Authorization": f"Bearer {graph_access_token}",
                "Content-Type": "application/json",
            },
        )
        add_password_payload = add_password_response.json() if add_password_response.headers.get("content-type", "").startswith("application/json") else {}
        key_id = str(add_password_payload.get("keyId") or "")
        new_secret = str(add_password_payload.get("secretText") or "")
        if add_password_response.status_code not in {200, 201} or not key_id or not new_secret:
            return {
                "ok": False,
                "error": "microsoft_graph_add_password_failed",
                "status_code": int(add_password_response.status_code),
                "provider_endpoint": "POST /applications/{id}/addPassword",
                "response_hint": str(add_password_payload.get("error", {}).get("message") or add_password_payload.get("error_description") or "")[:180],
            }

        probe_response = await client.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": new_secret,
                "scope": probe_scope,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        probe_payload = probe_response.json() if probe_response.headers.get("content-type", "").startswith("application/json") else {}
        if probe_response.status_code != 200 or not probe_payload.get("access_token"):
            # best-effort cleanup of newly issued secret on failed cutover probe
            try:
                await client.post(
                    f"https://graph.microsoft.com/v1.0/applications/{app_object_id}/removePassword",
                    json={"keyId": key_id},
                    headers={
                        "Authorization": f"Bearer {graph_access_token}",
                        "Content-Type": "application/json",
                    },
                )
            except Exception:
                pass
            return {
                "ok": False,
                "error": "microsoft_oauth_cutover_probe_failed",
                "status_code": int(probe_response.status_code),
                "provider_endpoint": "POST /oauth2/v2.0/token (new secret probe)",
                "response_hint": str(probe_payload.get("error") or probe_payload.get("error_description") or "")[:180],
                "lifecycle": {
                    "created_key_id": key_id,
                    "reverted_on_probe_failure": True,
                },
            }

        revoke_previous = str(os.environ.get("KEY_ROTATION_REVOKE_PREVIOUS_MICROSOFT_SECRET") or "false").lower() == "true"
        previous_key_id = _first_env(["AZURE_ROTATION_PREVIOUS_KEY_ID"])
        provider_revoked = False
        revoke_status = "not_attempted"
        revoke_error = None
        if revoke_previous and previous_key_id:
            remove_response = await client.post(
                f"https://graph.microsoft.com/v1.0/applications/{app_object_id}/removePassword",
                json={"keyId": previous_key_id},
                headers={
                    "Authorization": f"Bearer {graph_access_token}",
                    "Content-Type": "application/json",
                },
            )
            if remove_response.status_code in {200, 204}:
                provider_revoked = True
                revoke_status = "success"
            else:
                revoke_status = "failed"
                revoke_error = (remove_response.text or "")[:180]

    return {
        "ok": True,
        "provider_revoked": provider_revoked,
        "status_code": 200,
        "provider_endpoint": "Graph addPassword + OAuth token probe",
        "response_hint": "microsoft_oauth_rotate_lifecycle_success",
        "lifecycle": {
            "created_key_id": key_id,
            "created_display_name": display_name,
            "provider_revoked": provider_revoked,
            "revoke_status": revoke_status,
            "revoke_error": revoke_error,
            "rotation_scope": probe_scope,
        },
    }


async def _execute_provider_api_apply(provider: Dict[str, Any]) -> Dict[str, Any]:
    adapter = str(provider.get("api_adapter") or "").strip()
    if not adapter:
        return {"ok": False, "error": "adapter_not_configured"}

    handlers = {
        "stripe": _apply_provider_api_stripe,
        "paypal": _apply_provider_api_paypal,
        "fedapay": _apply_provider_api_fedapay,
        "google_oauth_refresh": _apply_provider_api_google_oauth_refresh,
        "microsoft_oauth_cc": _apply_provider_api_microsoft_oauth_cc,
    }
    if adapter == "microsoft_oauth_cc" and str(provider.get("apply_contract_mode") or "") == APPLY_CONTRACT_API_ROTATE:
        try:
            return await _apply_provider_api_microsoft_oauth_rotate(provider)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:220]}

    handler = handlers.get(adapter)
    if not handler:
        return {"ok": False, "error": "adapter_handler_missing"}

    try:
        return await handler()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:220]}


def _legacy_step_status(step_status: str) -> str:
    mapping = {
        STEP_STATUS_MANUAL_PENDING: "manual_required",
        STEP_STATUS_MANUAL_EVIDENCE_UPLOADED: "manual_required",
        STEP_STATUS_MANUAL_VERIFIED: "manual_required",
        STEP_STATUS_API_PROBE_VALIDATED: "applied",
        STEP_STATUS_CUTOVER_APPLIED: "applied",
        STEP_STATUS_PROVIDER_REVOKED: "applied",
        STEP_STATUS_API_PROBE_FAILED: "api_apply_failed",
        STEP_STATUS_CUTOVER_FAILED: "api_apply_failed",
        STEP_STATUS_ADAPTER_MISSING: "adapter_missing",
        STEP_STATUS_GUARDED: "guarded",
    }
    return mapping.get(step_status, step_status)


def _provider_contract_gate(provider: Dict[str, Any]) -> Dict[str, Any]:
    contract_mode = str(provider.get("apply_contract_mode") or "").strip()
    provider_id = str(provider.get("provider_id") or "")
    if contract_mode not in VALID_APPLY_CONTRACTS:
        return {
            "ok": False,
            "reason": "unknown_apply_contract_mode",
            "message": f"Unsupported apply contract mode for {provider_id or 'provider'}.",
        }

    if contract_mode in {APPLY_CONTRACT_PROBE_ONLY, APPLY_CONTRACT_API_ROTATE}:
        if not str(provider.get("api_adapter") or "").strip():
            return {
                "ok": False,
                "reason": "api_adapter_not_configured",
                "message": "Provider contract requires api_adapter but none is configured.",
            }

    mismatch_reason = str(provider.get("environment_mismatch_reason") or "").strip()
    if mismatch_reason:
        return {
            "ok": False,
            "reason": "rotation_env_mismatch",
            "message": f"Provider environment mismatch: {mismatch_reason}",
        }

    if contract_mode == APPLY_CONTRACT_API_ROTATE and not _rotate_lifecycle_enabled():
        return {
            "ok": False,
            "reason": "provider_rotate_lifecycle_disabled",
            "message": "Provider-side create/revoke lifecycle is disabled by policy flag.",
        }

    return {"ok": True}


def _is_provider_failure_status(status: str) -> bool:
    return status in {
        STEP_STATUS_BLOCKED,
        STEP_STATUS_CONTRACT_REJECTED,
        STEP_STATUS_ADAPTER_MISSING,
        STEP_STATUS_GUARDED,
        STEP_STATUS_API_PROBE_FAILED,
        STEP_STATUS_CUTOVER_FAILED,
    }


async def _emit_provider_rotation_signal(
    run_id: str,
    plan_id: str,
    provider_id: str,
    status: str,
    message: str,
    severity: str = "medium",
) -> None:
    if not provider_id:
        return
    await db.siem_triggered_alerts.insert_one(
        {
            "alert_id": f"alert_keyrot_{uuid.uuid4().hex[:12]}",
            "rule_id": "key_rotation_provider_status",
            "rule_name": "Key Rotation Provider Status",
            "event_type": "key_rotation_provider_status",
            "severity": severity,
            "status": "active" if severity in {"high", "critical"} else "observed",
            "triggered_at": _utc_now_iso(),
            "provider_id": provider_id,
            "rotation_run_id": run_id,
            "rotation_plan_id": plan_id,
            "rotation_status": status,
            "message": message,
        }
    )


async def _evaluate_provider_adapter(provider: Dict[str, Any], execution_mode: str) -> Dict[str, Any]:
    provider_id = provider["provider_id"]
    readiness_state = provider["readiness_state"]
    contract_mode = str(provider.get("apply_contract_mode") or APPLY_CONTRACT_MANUAL)

    if readiness_state != "ready":
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_BLOCKED,
            "legacy_status": _legacy_step_status(STEP_STATUS_BLOCKED),
            "message": "Provider readiness blocked",
            "runbook": _provider_runbook(provider_id),
            "missing_requirements": provider.get("missing_requirements", []),
            "applied": False,
            "rollback_available": False,
        }

    if execution_mode == "dry_run":
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_SIMULATED,
            "legacy_status": _legacy_step_status(STEP_STATUS_SIMULATED),
            "message": "Dry-run simulation only",
            "runbook": _provider_runbook(provider_id),
            "applied": False,
            "rollback_available": False,
            "contract_mode": contract_mode,
        }

    contract_gate = _provider_contract_gate(provider)
    if not contract_gate.get("ok"):
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_CONTRACT_REJECTED,
            "legacy_status": _legacy_step_status(STEP_STATUS_CONTRACT_REJECTED),
            "reason": contract_gate.get("reason"),
            "message": contract_gate.get("message") or "Provider contract gate rejected apply.",
            "runbook": _provider_runbook(provider_id),
            "applied": False,
            "rollback_available": bool(provider.get("rollback_supported")),
            "contract_mode": contract_mode,
        }

    # live_guarded mode
    live_apply_enabled = str(os.environ.get("KEY_ROTATION_API_LIVE_ENABLE") or "true").lower() == "true"
    api_adapter_available = bool(provider.get("api_adapter_available", False))
    if not live_apply_enabled:
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_GUARDED,
            "legacy_status": _legacy_step_status(STEP_STATUS_GUARDED),
            "message": "Live apply flag disabled",
            "runbook": _provider_runbook(provider_id),
            "applied": False,
            "rollback_available": bool(provider.get("rollback_supported")),
            "contract_mode": contract_mode,
        }

    if contract_mode == APPLY_CONTRACT_MANUAL:
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_MANUAL_PENDING,
            "legacy_status": _legacy_step_status(STEP_STATUS_MANUAL_PENDING),
            "message": "Manual provider rotation evidence is required before completion.",
            "runbook": _provider_runbook(provider_id),
            "applied": False,
            "requires_manual_evidence": True,
            "manual_constraint_code": provider.get("manual_constraint_code"),
            "rollback_available": bool(provider.get("rollback_supported")),
            "contract_mode": contract_mode,
        }

    if contract_mode in {APPLY_CONTRACT_PROBE_ONLY, APPLY_CONTRACT_API_ROTATE} and not api_adapter_available:
        return {
            "provider_id": provider_id,
            "status": STEP_STATUS_ADAPTER_MISSING,
            "legacy_status": _legacy_step_status(STEP_STATUS_ADAPTER_MISSING),
            "reason": _infer_adapter_missing_reason(list(provider.get("api_adapter_missing_requirements") or [])),
            "message": "Provider API live flag is enabled but adapter prerequisites are not complete",
            "runbook": _provider_runbook(provider_id),
            "applied": False,
            "missing_requirements": provider.get("api_adapter_missing_requirements", []),
            "rollback_available": bool(provider.get("rollback_supported")),
            "contract_mode": contract_mode,
        }

    if contract_mode in {APPLY_CONTRACT_PROBE_ONLY, APPLY_CONTRACT_API_ROTATE} and api_adapter_available:
        api_result = await _execute_provider_api_apply(provider)
        if not api_result.get("ok"):
            failed_status = STEP_STATUS_API_PROBE_FAILED if contract_mode == APPLY_CONTRACT_PROBE_ONLY else STEP_STATUS_CUTOVER_FAILED
            return {
                "provider_id": provider_id,
                "status": failed_status,
                "legacy_status": _legacy_step_status(failed_status),
                "message": "Provider API contract execution failed",
                "runbook": _provider_runbook(provider_id),
                "applied": False,
                "rollback_available": bool(provider.get("rollback_supported")),
                "contract_mode": contract_mode,
                "adapter_result": {
                    "ok": False,
                    "error": api_result.get("error"),
                    "status_code": api_result.get("status_code"),
                    "provider_endpoint": api_result.get("provider_endpoint"),
                    "response_hint": api_result.get("response_hint"),
                },
            }

        success_status = STEP_STATUS_API_PROBE_VALIDATED
        if contract_mode == APPLY_CONTRACT_API_ROTATE:
            success_status = STEP_STATUS_PROVIDER_REVOKED if bool(api_result.get("provider_revoked")) else STEP_STATUS_CUTOVER_APPLIED
        return {
            "provider_id": provider_id,
            "status": success_status,
            "legacy_status": _legacy_step_status(success_status),
            "message": "Provider API contract executed successfully",
            "runbook": _provider_runbook(provider_id),
            "applied": bool(contract_mode == APPLY_CONTRACT_API_ROTATE),
            "contract_mode": contract_mode,
            "rollback_available": bool(provider.get("rollback_supported")),
            "adapter_result": {
                "ok": True,
                "status_code": api_result.get("status_code"),
                "provider_endpoint": api_result.get("provider_endpoint"),
                "response_hint": api_result.get("response_hint"),
                "provider_revoked": bool(api_result.get("provider_revoked")),
                "lifecycle": api_result.get("lifecycle"),
            },
        }

    return {
        "provider_id": provider_id,
        "status": STEP_STATUS_CONTRACT_REJECTED,
        "legacy_status": _legacy_step_status(STEP_STATUS_CONTRACT_REJECTED),
        "message": "Provider contract mode cannot be executed by apply runtime",
        "runbook": _provider_runbook(provider_id),
        "applied": False,
        "rollback_available": bool(provider.get("rollback_supported")),
        "contract_mode": contract_mode,
    }


async def _open_rotation_incident(plan_id: str, run_id: str, severity: str, message: str, details: Dict[str, Any]) -> Dict[str, Any]:
    incident = {
        "incident_id": f"keyrot_inc_{uuid.uuid4().hex[:12]}",
        "source": "key_rotation",
        "status": "open",
        "severity": severity,
        "ts": _utc_now_iso(),
        "created_at": _utc_now_iso(),
        "message": message,
        "plan_id": plan_id,
        "run_id": run_id,
        "details": details,
    }
    await db.security_incidents.insert_one(incident)
    await _dispatch_incident_webhook(incident)
    safe_incident = dict(incident)
    safe_incident.pop("_id", None)
    return safe_incident


async def _dispatch_incident_webhook(incident: Dict[str, Any]) -> None:
    webhook_url = str(os.environ.get("SIEM_INCIDENT_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return

    payload = {
        "type": "security_key_rotation_incident",
        "incident_id": incident.get("incident_id"),
        "source": incident.get("source"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "message": incident.get("message"),
        "plan_id": incident.get("plan_id"),
        "run_id": incident.get("run_id"),
        "ts": incident.get("ts"),
    }
    sent_at = _utc_now_iso()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(webhook_url, json=payload)
        await db.siem_incident_webhook_log.insert_one(
            {
                "incident_id": incident.get("incident_id"),
                "status_code": int(response.status_code),
                "ok": bool(200 <= int(response.status_code) < 300),
                "sent_at": sent_at,
                "source": "security_key_rotation",
            }
        )
    except Exception as exc:
        await db.siem_incident_webhook_log.insert_one(
            {
                "incident_id": incident.get("incident_id"),
                "ok": False,
                "error": str(exc),
                "sent_at": sent_at,
                "source": "security_key_rotation",
            }
        )


async def _auto_rollback_after_failed_health(run_id: str, plan_id: str, actor_user_id: str) -> Dict[str, Any]:
    steps = []
    async for doc in db.security_key_rotation_steps.find({"run_id": run_id}, {"_id": 0}).sort("created_at", -1):
        steps.append(doc)

    rollback_actions = []
    for step in steps:
        action = {
            "provider_id": step.get("provider_id"),
            "status": "no_op",
            "message": "No automatic rollback available",
            "at": _utc_now_iso(),
        }
        if step.get("applied") and step.get("rollback_available"):
            action = {
                "provider_id": step.get("provider_id"),
                "status": "manual_rollback_required",
                "message": "Automatic rollback requested; provider-side rollback must be executed",
                "at": _utc_now_iso(),
            }
        rollback_actions.append(action)

    rollback_doc = {
        "rollback_id": f"keyrot_rb_{uuid.uuid4().hex[:12]}",
        "run_id": run_id,
        "plan_id": plan_id,
        "executed_by": actor_user_id,
        "executed_at": _utc_now_iso(),
        "trigger": "auto_post_health_failure",
        "actions": rollback_actions,
    }
    await db.security_key_rotation_rollbacks.insert_one(rollback_doc)
    safe_rollback_doc = dict(rollback_doc)
    safe_rollback_doc.pop("_id", None)
    return safe_rollback_doc


async def _recompute_run_summary(run_id: str) -> Dict[str, int]:
    rows: List[Dict[str, Any]] = []
    async for doc in db.security_key_rotation_steps.find({"run_id": run_id}, {"_id": 0}):
        rows.append(doc)

    summary = {
        "providers_total": len(rows),
        "cutover_applied": len([s for s in rows if s.get("status") == STEP_STATUS_CUTOVER_APPLIED]),
        "provider_revoked": len([s for s in rows if s.get("status") == STEP_STATUS_PROVIDER_REVOKED]),
        "credential_validated": len([s for s in rows if s.get("status") == STEP_STATUS_API_PROBE_VALIDATED]),
        "manual_pending_evidence": len([s for s in rows if s.get("status") == STEP_STATUS_MANUAL_PENDING]),
        "manual_evidence_uploaded": len([s for s in rows if s.get("status") == STEP_STATUS_MANUAL_EVIDENCE_UPLOADED]),
        "manual_applied_verified": len([s for s in rows if s.get("status") == STEP_STATUS_MANUAL_VERIFIED]),
        "blocked": len([s for s in rows if s.get("status") == STEP_STATUS_BLOCKED]),
        "simulated": len([s for s in rows if s.get("status") == STEP_STATUS_SIMULATED]),
        "adapter_missing": len([s for s in rows if s.get("status") == STEP_STATUS_ADAPTER_MISSING]),
        "api_probe_failed": len([s for s in rows if s.get("status") == STEP_STATUS_API_PROBE_FAILED]),
        "cutover_failed": len([s for s in rows if s.get("status") == STEP_STATUS_CUTOVER_FAILED]),
        "contract_rejected": len([s for s in rows if s.get("status") == STEP_STATUS_CONTRACT_REJECTED]),
        "guarded": len([s for s in rows if s.get("status") == STEP_STATUS_GUARDED]),
        "skipped_canary_stop": len([s for s in rows if s.get("status") == STEP_STATUS_SKIPPED_CANARY]),
    }
    summary["applied"] = summary["cutover_applied"] + summary["provider_revoked"]
    summary["manual_required"] = (
        summary["manual_pending_evidence"]
        + summary["manual_evidence_uploaded"]
        + summary["manual_applied_verified"]
    )
    summary["api_apply_failed"] = summary["api_probe_failed"] + summary["cutover_failed"]
    return summary


@router.get("/readiness")
async def key_rotation_readiness(request: Request):
    await require_admin(request)
    readiness_map = _build_readiness_map()
    providers = [readiness_map[item["provider_id"]] for item in PROVIDER_DEFINITIONS]
    preflight_gate = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=True)

    apply_statuses = [str((p.get("apply_capability") or {}).get("status") or "unknown") for p in providers]
    return {
        "providers": providers,
        "preflight_gate": preflight_gate,
        "rotation_policy": _rotation_policy_snapshot(),
        "summary": {
            "total": len(providers),
            "ready": len([p for p in providers if p.get("readiness_state") == "ready"]),
            "blocked": len([p for p in providers if p.get("readiness_state") != "ready"]),
            "api_rotate_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_ROTATE_READY]),
            "api_probe_only_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_PROBE_READY]),
            "manual_by_constraint": len([s for s in apply_statuses if s == READINESS_STATUS_MANUAL_BY_CONSTRAINT]),
            "guarded": len([s for s in apply_statuses if s == READINESS_STATUS_GUARDED]),
            "adapter_missing": len([s for s in apply_statuses if s == READINESS_STATUS_ADAPTER_MISSING]),
            "contract_rejected": len([s for s in apply_statuses if s == STEP_STATUS_CONTRACT_REJECTED]),
            "target_environment": _rotation_target_environment(),
            # Backward-compatible aliases
            "api_apply_ready": len([s for s in apply_statuses if s in {READINESS_STATUS_API_ROTATE_READY, READINESS_STATUS_API_PROBE_READY}]),
            "manual_required": len([s for s in apply_statuses if s == READINESS_STATUS_MANUAL_BY_CONSTRAINT]),
            "provider_contract_counts": {
                "api_probe_only": len([p for p in providers if str(p.get("apply_contract_mode") or "") == APPLY_CONTRACT_PROBE_ONLY]),
                "api_rotate_supported": len([p for p in providers if str(p.get("apply_contract_mode") or "") == APPLY_CONTRACT_API_ROTATE]),
                "manual_by_provider_constraint": len([p for p in providers if str(p.get("apply_contract_mode") or "") == APPLY_CONTRACT_MANUAL]),
            },
        },
        "generated_at": _utc_now_iso(),
    }


@router.get("/go-live-checklist")
async def key_rotation_go_live_checklist(request: Request):
    await require_admin(request)
    readiness_map = _build_readiness_map()
    providers = [readiness_map[item["provider_id"]] for item in PROVIDER_DEFINITIONS]
    assessments = [_provider_go_live_assessment(provider) for provider in providers]

    rotate_contract_rows = [row for row in assessments if row.get("contract_mode") == APPLY_CONTRACT_API_ROTATE]
    probe_contract_rows = [row for row in assessments if row.get("contract_mode") == APPLY_CONTRACT_PROBE_ONLY]
    manual_contract_rows = [row for row in assessments if row.get("contract_mode") == APPLY_CONTRACT_MANUAL]
    hard_blocked_rows = [row for row in assessments if row.get("hard_blocked")]
    rotate_hard_blocked_rows = [
        row for row in rotate_contract_rows if row.get("hard_blocked")
    ]

    return {
        "generated_at": _utc_now_iso(),
        "target_environment": _rotation_target_environment(),
        "provider_rotate_lifecycle_enabled": _rotate_lifecycle_enabled(),
        "providers": assessments,
        "summary": {
            "total": len(assessments),
            "ready_for_live_apply": len([row for row in assessments if row.get("ready_for_live_apply")]),
            "hard_blocked": len(hard_blocked_rows),
            "rotate_contracts": len(rotate_contract_rows),
            "rotate_contract_hard_blocked": len(rotate_hard_blocked_rows),
            "probe_contracts": len(probe_contract_rows),
            "manual_constraints": len(manual_contract_rows),
            "is_green_for_live_apply": len(rotate_hard_blocked_rows) == 0,
        },
    }


@router.get("/dry-run")
async def key_rotation_dry_run_preview(request: Request):
    user = await require_admin(request)
    run_doc = _build_dry_run_document(getattr(user, "user_id", "admin"))
    run_doc["persisted"] = False
    return run_doc


@router.get("/policy")
async def key_rotation_policy(request: Request):
    await require_admin(request)
    policy = _rotation_policy_snapshot()
    game_day = await db.system_runtime_flags.find_one(
        {"key": "key_rotation_last_game_day"},
        {"_id": 0},
    ) or {}
    last_attestation = await db.security_key_rotation_policy_attestations.find_one({}, {"_id": 0}, sort=[("attested_at", -1)]) or {}
    return {
        "policy": policy,
        "last_game_day": game_day,
        "siem_webhook_configured": bool(str(os.environ.get("SIEM_INCIDENT_WEBHOOK_URL") or "").strip()),
        "last_attestation": last_attestation,
    }


@router.post("/policy/game-day")
async def key_rotation_record_game_day(request: Request, body: KeyRotationGameDayBody):
    user = await require_admin(request)
    links = _normalize_nonempty_lines(body.evidence_links)
    if len(links) < 1:
        raise HTTPException(status_code=400, detail="Game-day recording requires at least one evidence link")
    entry = {
        "key": "key_rotation_last_game_day",
        "recorded_at": _utc_now_iso(),
        "recorded_by": getattr(user, "user_id", "admin"),
        "note": str(body.note or "").strip(),
        "evidence_links": links,
        "evidence_link_hashes": [_sha256_hex(item) for item in links],
    }
    await db.system_runtime_flags.update_one(
        {"key": "key_rotation_last_game_day"},
        {"$set": entry},
        upsert=True,
    )
    policy_snapshot = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=False)
    attestation_doc = {
        "attestation_id": f"keyrot_att_{uuid.uuid4().hex[:12]}",
        "attested_at": _utc_now_iso(),
        "attested_by": getattr(user, "user_id", "admin"),
        "source": "game_day_record",
        "note": entry["note"],
        "policy": _rotation_policy_snapshot(),
        "policy_gate_snapshot": policy_snapshot,
        "game_day_snapshot": entry,
        "webhook_validation": await _validate_siem_incident_webhook_delivery(
            actor_user_id=getattr(user, "user_id", "admin"),
            context="game_day_record",
            related_run_id=None,
        ),
    }
    await db.security_key_rotation_policy_attestations.insert_one(attestation_doc)
    attestation_doc.pop("_id", None)
    return {"ok": True, "entry": entry, "attestation": attestation_doc}


@router.post("/policy/attest")
async def key_rotation_policy_attest(request: Request, body: KeyRotationPolicyAttestationBody):
    user = await require_admin(request)
    actor_user_id = getattr(user, "user_id", "admin")

    prereq_refresh = None
    if body.run_prerequisite_refresh:
        prereq_refresh = await _refresh_policy_gate_prerequisites(request)

    policy_snapshot = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=False)
    webhook_validation = None
    if body.validate_webhook:
        webhook_validation = await _validate_siem_incident_webhook_delivery(
            actor_user_id=actor_user_id,
            context="policy_attestation",
            related_run_id=None,
        )

    game_day_snapshot = None
    if body.include_game_day_snapshot:
        game_day_snapshot = await db.system_runtime_flags.find_one(
            {"key": "key_rotation_last_game_day"},
            {"_id": 0},
        ) or {}

    attestation_doc = {
        "attestation_id": f"keyrot_att_{uuid.uuid4().hex[:12]}",
        "attested_at": _utc_now_iso(),
        "attested_by": actor_user_id,
        "note": body.note,
        "policy": _rotation_policy_snapshot(),
        "policy_gate_snapshot": policy_snapshot,
        "prerequisite_refresh": prereq_refresh,
        "webhook_validation": webhook_validation,
        "game_day_snapshot": game_day_snapshot,
    }
    await db.security_key_rotation_policy_attestations.insert_one(attestation_doc)
    attestation_doc.pop("_id", None)
    return attestation_doc


@router.get("/monitor/status")
async def key_rotation_monitor_status(request: Request):
    await require_admin(request)
    config = await _get_runbook_monitor_config()
    latest_run = await db.security_runbook_monitor_runs.find_one({}, {"_id": 0}, sort=[("executed_at", -1)]) or {}
    latest_dashboard = await db.security_runbook_monitor_dashboard_snapshots.find_one({}, {"_id": 0}, sort=[("generated_at", -1)]) or {}
    latest_notification = await db.security_runbook_monitor_notifications.find_one({}, {"_id": 0}, sort=[("created_at", -1)]) or {}
    return {
        "config": config,
        "latest_run": latest_run,
        "latest_dashboard": latest_dashboard,
        "latest_notification": latest_notification,
    }


@router.get("/monitor/history")
async def key_rotation_monitor_history(request: Request, limit: int = Query(20, ge=1, le=100)):
    await require_admin(request)
    runs = await db.security_runbook_monitor_runs.find({}, {"_id": 0}).sort("executed_at", -1).limit(limit).to_list(limit)
    notifications = await db.security_runbook_monitor_notifications.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    dashboards = await db.security_runbook_monitor_dashboard_snapshots.find({}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return {
        "runs": runs,
        "notifications": notifications,
        "dashboards": dashboards,
    }


@router.post("/monitor/run-now")
async def key_rotation_monitor_run_now(request: Request, body: KeyRotationMonitorRunNowBody):
    user = await require_admin(request)
    result = await run_security_runbook_monitor_cycle(
        trigger_source=f"manual_api:{getattr(user, 'user_id', 'admin')}",
        force=bool(body.force),
        include_attestation_override=bool(body.include_attestation),
    )
    return result


@router.post("/monitor/pause")
async def key_rotation_monitor_pause(request: Request):
    user = await require_admin(request)
    config = await _set_runbook_monitor_config({"enabled": False}, getattr(user, "user_id", "admin"))
    return {
        "ok": True,
        "message": "Runbook monitor paused",
        "config": config,
    }


@router.post("/monitor/resume")
async def key_rotation_monitor_resume(request: Request, body: KeyRotationMonitorResumeBody):
    user = await require_admin(request)
    config = await _set_runbook_monitor_config({"enabled": True}, getattr(user, "user_id", "admin"))
    run_result = None
    if body.run_now:
        run_result = await run_security_runbook_monitor_cycle(
            trigger_source=f"resume_api:{getattr(user, 'user_id', 'admin')}",
            force=True,
            include_attestation_override=None,
        )
    return {
        "ok": True,
        "message": "Runbook monitor resumed",
        "config": config,
        "run_result": run_result,
    }


@router.post("/dry-run")
async def key_rotation_dry_run(request: Request):
    user = await require_admin(request)
    run_doc = _build_dry_run_document(getattr(user, "user_id", "admin"))
    run_doc["persisted"] = True
    await db.security_key_rotation_runs.insert_one(run_doc)
    run_doc.pop("_id", None)
    return run_doc


@router.post("/prepare")
async def key_rotation_prepare(request: Request, body: KeyRotationPrepareBody):
    user = await require_admin(request)
    readiness_map = _build_readiness_map()
    selected = _select_providers(body.providers, readiness_map)
    providers = [readiness_map[item] for item in selected]

    contract_warnings: List[Dict[str, Any]] = []
    for provider in providers:
        gate = _provider_contract_gate(provider)
        if not gate.get("ok"):
            contract_warnings.append(
                {
                    "provider_id": provider.get("provider_id"),
                    "reason": gate.get("reason"),
                    "message": gate.get("message"),
                }
            )

    plan_id = f"keyrot_plan_{uuid.uuid4().hex[:12]}"
    created_at = _utc_now_iso()
    approval_token = _sign_approval_token(plan_id=plan_id, actor_user_id=getattr(user, "user_id", "admin"))

    policy_snapshot = await collect_policy_gate_signals(db_ref=db)

    plan_doc = {
        "plan_id": plan_id,
        "status": "prepared",
        "created_at": created_at,
        "created_by": getattr(user, "user_id", "admin"),
        "reason": body.reason,
        "change_ticket": body.change_ticket,
        "execution_mode": body.execution_mode,
        "providers": providers,
        "contract_warnings": contract_warnings,
        "policy_snapshot": policy_snapshot,
        "approval": {
            "required": True,
            "token_issued_at": created_at,
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "token_hint": approval_token[:24] + "...",
        },
    }
    await db.security_key_rotation_plans.insert_one(plan_doc)

    return {
        "plan_id": plan_id,
        "status": "prepared",
        "providers": providers,
        "contract_warnings": contract_warnings,
        "approval_token": approval_token,
        "approval_expires_at": plan_doc["approval"]["token_expires_at"],
        "policy_snapshot": policy_snapshot,
    }


@router.get("/plans")
async def list_key_rotation_plans(request: Request, limit: int = Query(20, ge=1, le=100)):
    await require_admin(request)
    plans = []
    async for doc in db.security_key_rotation_plans.find({}, {"_id": 0}).sort("created_at", -1).limit(limit):
        plans.append(doc)
    return {"plans": plans, "count": len(plans)}


@router.get("/plans/{plan_id}")
async def get_key_rotation_plan(request: Request, plan_id: str):
    await require_admin(request)
    plan = await db.security_key_rotation_plans.find_one({"plan_id": plan_id}, {"_id": 0})
    if not plan:
        return {"found": False, "plan_id": plan_id}
    return {"found": True, "plan": plan}


@router.post("/approve")
async def key_rotation_approve(request: Request, body: KeyRotationApproveBody):
    user = await require_admin(request)
    plan = await db.security_key_rotation_plans.find_one({"plan_id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if str(plan.get("status") or "") != "prepared":
        raise HTTPException(status_code=400, detail=f"Plan status is {plan.get('status')}, expected prepared")

    token_payload = _verify_approval_token(body.approval_token, expected_plan_id=body.plan_id)

    approved_at = _utc_now_iso()
    await db.security_key_rotation_plans.update_one(
        {"plan_id": body.plan_id},
        {
            "$set": {
                "status": "approved",
                "approved_at": approved_at,
                "approved_by": getattr(user, "user_id", "admin"),
                "approval_note": body.approval_note,
                "approval_token_payload": {
                    "actor_user_id": token_payload.get("actor_user_id"),
                    "iat": token_payload.get("iat"),
                    "exp": token_payload.get("exp"),
                    "nonce": token_payload.get("nonce"),
                },
            }
        },
    )

    return {
        "plan_id": body.plan_id,
        "status": "approved",
        "approved_at": approved_at,
        "approved_by": getattr(user, "user_id", "admin"),
    }


@router.post("/apply")
async def key_rotation_apply(request: Request, body: KeyRotationApplyBody):
    user = await require_admin(request)
    plan = await db.security_key_rotation_plans.find_one({"plan_id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if str(plan.get("status") or "") != "approved":
        raise HTTPException(status_code=400, detail=f"Plan status is {plan.get('status')}, expected approved")

    run_id = f"keyrot_run_{uuid.uuid4().hex[:12]}"
    started_at = _utc_now_iso()
    providers = plan.get("providers") or []
    steps: List[Dict[str, Any]] = []
    has_failures = False
    canary_stop_triggered = False
    consecutive_failures = 0
    try:
        canary_failure_threshold = int(str(os.environ.get("KEY_ROTATION_CANARY_STOP_AFTER_CONSECUTIVE_FAILURES") or "2"))
    except Exception:
        canary_failure_threshold = 2
    if canary_failure_threshold < 1:
        canary_failure_threshold = 1

    apply_window_doc: Dict[str, Any] = {}
    prereq_refresh_result: Dict[str, Any] = {}
    allow_override = body.execution_mode != "dry_run"

    if allow_override:
        apply_window_doc = await _activate_policy_gate_apply_window(
            plan_id=body.plan_id,
            run_id=run_id,
            actor_user_id=getattr(user, "user_id", "admin"),
        )
        prereq_refresh_result = await _refresh_policy_gate_prerequisites(request)

    try:
        preflight_snapshot = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=allow_override)
        preflight_ok = bool(preflight_snapshot.get("passed"))

        rotate_contract_assessments = [
            _provider_go_live_assessment(provider)
            for provider in providers
            if str(provider.get("apply_contract_mode") or "") == APPLY_CONTRACT_API_ROTATE
        ]
        rotate_contract_hard_blockers = [row for row in rotate_contract_assessments if row.get("hard_blocked")]

        if body.execution_mode != "dry_run" and rotate_contract_hard_blockers:
            run_doc = {
                "run_id": run_id,
                "plan_id": body.plan_id,
                "status": "contract_blocked",
                "execution_mode": body.execution_mode,
                "started_at": started_at,
                "finished_at": _utc_now_iso(),
                "initiated_by": getattr(user, "user_id", "admin"),
                "run_note": body.run_note,
                "apply_window": apply_window_doc,
                "prerequisite_refresh": prereq_refresh_result,
                "rotate_contract_go_live_blockers": rotate_contract_hard_blockers,
                "summary": {
                    "providers_total": len(providers),
                    "cutover_applied": 0,
                    "provider_revoked": 0,
                    "credential_validated": 0,
                    "manual_pending_evidence": 0,
                    "manual_evidence_uploaded": 0,
                    "manual_applied_verified": 0,
                    "blocked": 0,
                    "simulated": 0,
                    "adapter_missing": 0,
                    "api_probe_failed": 0,
                    "cutover_failed": 0,
                    "contract_rejected": 0,
                    "guarded": 0,
                    "skipped_canary_stop": 0,
                    "applied": 0,
                    "manual_required": 0,
                    "api_apply_failed": 0,
                },
                "preflight": {"policy_gate_passed": preflight_ok, "snapshot": preflight_snapshot},
                "post_health": None,
                "rollback_required": False,
            }
            await db.security_key_rotation_runs.insert_one(run_doc)
            await db.security_key_rotation_evidence.insert_one(
                {
                    "evidence_id": f"keyrot_evd_{uuid.uuid4().hex[:12]}",
                    "run_id": run_id,
                    "plan_id": body.plan_id,
                    "captured_at": _utc_now_iso(),
                    "status": "contract_blocked",
                    "steps": [],
                    "preflight_snapshot": preflight_snapshot,
                    "policy_snapshot": preflight_snapshot,
                    "rotate_contract_go_live_blockers": rotate_contract_hard_blockers,
                    "apply_window": apply_window_doc,
                    "prerequisite_refresh": prereq_refresh_result,
                }
            )
            await db.security_key_rotation_plans.update_one(
                {"plan_id": body.plan_id},
                {"$set": {"status": "contract_blocked", "last_run_id": run_id, "last_run_at": _utc_now_iso()}},
            )
            return {
                "run_id": run_id,
                "plan_id": body.plan_id,
                "status": "contract_blocked",
                "rotate_contract_go_live_blockers": rotate_contract_hard_blockers,
                "summary": run_doc["summary"],
            }

        if body.execution_mode != "dry_run" and not preflight_ok:
            run_doc = {
                "run_id": run_id,
                "plan_id": body.plan_id,
                "status": "preflight_blocked",
                "execution_mode": body.execution_mode,
                "started_at": started_at,
                "finished_at": _utc_now_iso(),
                "initiated_by": getattr(user, "user_id", "admin"),
                "run_note": body.run_note,
                "apply_window": apply_window_doc,
                "prerequisite_refresh": prereq_refresh_result,
                "summary": {
                    "providers_total": len(providers),
                    "cutover_applied": 0,
                    "provider_revoked": 0,
                    "credential_validated": 0,
                    "manual_pending_evidence": 0,
                    "manual_evidence_uploaded": 0,
                    "manual_applied_verified": 0,
                    "blocked": 0,
                    "simulated": 0,
                    "adapter_missing": 0,
                    "api_probe_failed": 0,
                    "cutover_failed": 0,
                    "contract_rejected": 0,
                    "guarded": 0,
                    "skipped_canary_stop": 0,
                    "applied": 0,
                    "manual_required": 0,
                    "api_apply_failed": 0,
                },
                "preflight": {"policy_gate_passed": preflight_ok, "snapshot": preflight_snapshot},
                "post_health": None,
                "rollback_required": False,
            }
            await db.security_key_rotation_runs.insert_one(run_doc)
            await db.security_key_rotation_evidence.insert_one(
                {
                    "evidence_id": f"keyrot_evd_{uuid.uuid4().hex[:12]}",
                    "run_id": run_id,
                    "plan_id": body.plan_id,
                    "captured_at": _utc_now_iso(),
                    "status": "preflight_blocked",
                    "steps": [],
                    "preflight_snapshot": preflight_snapshot,
                    "policy_snapshot": preflight_snapshot,
                    "apply_window": apply_window_doc,
                    "prerequisite_refresh": prereq_refresh_result,
                }
            )
            await db.security_key_rotation_plans.update_one(
                {"plan_id": body.plan_id},
                {"$set": {"status": "preflight_blocked", "last_run_id": run_id, "last_run_at": _utc_now_iso()}},
            )
            return {"run_id": run_id, "plan_id": body.plan_id, "status": "preflight_blocked", "summary": run_doc["summary"]}

        for provider in providers:
            provider_id = provider.get("provider_id")
            if canary_stop_triggered and body.execution_mode != "dry_run":
                step = {
                    "provider_id": provider_id,
                    "status": STEP_STATUS_SKIPPED_CANARY,
                    "legacy_status": _legacy_step_status(STEP_STATUS_SKIPPED_CANARY),
                    "message": "Provider apply skipped due to canary stop threshold.",
                    "runbook": _provider_runbook(provider_id),
                    "applied": False,
                    "rollback_available": False,
                }
            else:
                step = await _evaluate_provider_adapter(provider, execution_mode=body.execution_mode)

            step_doc = {
                "step_id": f"keyrot_step_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "plan_id": body.plan_id,
                "provider_id": provider_id,
                "status": step.get("status"),
                "legacy_status": step.get("legacy_status") or _legacy_step_status(str(step.get("status") or "")),
                "contract_mode": step.get("contract_mode") or provider.get("apply_contract_mode"),
                "reason": step.get("reason"),
                "message": step.get("message"),
                "runbook": step.get("runbook"),
                "applied": bool(step.get("applied")),
                "rollback_available": bool(step.get("rollback_available")),
                "requires_manual_evidence": bool(step.get("requires_manual_evidence")),
                "manual_constraint_code": step.get("manual_constraint_code") or provider.get("manual_constraint_code"),
                "missing_requirements": step.get("missing_requirements", []),
                "adapter_result": step.get("adapter_result"),
                "created_at": _utc_now_iso(),
            }
            await db.security_key_rotation_steps.insert_one(step_doc)
            step_doc.pop("_id", None)
            steps.append(step_doc)

            step_status = str(step_doc.get("status") or "")
            if _is_provider_failure_status(step_status):
                has_failures = True
                consecutive_failures += 1
                await _emit_provider_rotation_signal(
                    run_id=run_id,
                    plan_id=body.plan_id,
                    provider_id=str(provider_id or ""),
                    status=step_status,
                    message=str(step_doc.get("message") or "Provider rotation failure"),
                    severity="high",
                )
                if body.execution_mode != "dry_run" and consecutive_failures >= canary_failure_threshold:
                    canary_stop_triggered = True
            else:
                consecutive_failures = 0

        policy_snapshot = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=allow_override)
        post_health_ok = bool(policy_snapshot.get("passed"))
        cutover_applied_count = len([s for s in steps if s.get("status") == STEP_STATUS_CUTOVER_APPLIED])
        provider_revoked_count = len([s for s in steps if s.get("status") == STEP_STATUS_PROVIDER_REVOKED])
        credential_validated_count = len([s for s in steps if s.get("status") == STEP_STATUS_API_PROBE_VALIDATED])
        manual_pending_count = len([s for s in steps if s.get("status") == STEP_STATUS_MANUAL_PENDING])
        manual_evidence_uploaded_count = len([s for s in steps if s.get("status") == STEP_STATUS_MANUAL_EVIDENCE_UPLOADED])
        manual_verified_count = len([s for s in steps if s.get("status") == STEP_STATUS_MANUAL_VERIFIED])
        blocked_count = len([s for s in steps if s.get("status") == STEP_STATUS_BLOCKED])
        simulated_count = len([s for s in steps if s.get("status") == STEP_STATUS_SIMULATED])
        adapter_missing_count = len([s for s in steps if s.get("status") == STEP_STATUS_ADAPTER_MISSING])
        api_probe_failed_count = len([s for s in steps if s.get("status") == STEP_STATUS_API_PROBE_FAILED])
        cutover_failed_count = len([s for s in steps if s.get("status") == STEP_STATUS_CUTOVER_FAILED])
        contract_rejected_count = len([s for s in steps if s.get("status") == STEP_STATUS_CONTRACT_REJECTED])
        guarded_count = len([s for s in steps if s.get("status") == STEP_STATUS_GUARDED])
        skipped_canary_count = len([s for s in steps if s.get("status") == STEP_STATUS_SKIPPED_CANARY])

        status = "completed"
        rollback_required = False
        if has_failures:
            status = "completed_with_blocked_providers"
        if skipped_canary_count > 0:
            status = "completed_with_canary_stop"
        if not post_health_ok and body.execution_mode != "dry_run" and (cutover_applied_count + provider_revoked_count) > 0:
            status = "rollback_required"
            rollback_required = True
        elif not post_health_ok and body.execution_mode != "dry_run" and (cutover_applied_count + provider_revoked_count) == 0:
            status = "completed_no_apply_postcheck_failed"

        run_doc = {
            "run_id": run_id,
            "plan_id": body.plan_id,
            "status": status,
            "execution_mode": body.execution_mode,
            "started_at": started_at,
            "finished_at": _utc_now_iso(),
            "initiated_by": getattr(user, "user_id", "admin"),
            "run_note": body.run_note,
            "apply_window": apply_window_doc,
            "prerequisite_refresh": prereq_refresh_result,
            "summary": {
                "providers_total": len(providers),
                "cutover_applied": cutover_applied_count,
                "provider_revoked": provider_revoked_count,
                "credential_validated": credential_validated_count,
                "manual_pending_evidence": manual_pending_count,
                "manual_evidence_uploaded": manual_evidence_uploaded_count,
                "manual_applied_verified": manual_verified_count,
                "blocked": blocked_count,
                "simulated": simulated_count,
                "adapter_missing": adapter_missing_count,
                "api_probe_failed": api_probe_failed_count,
                "cutover_failed": cutover_failed_count,
                "contract_rejected": contract_rejected_count,
                "guarded": guarded_count,
                "skipped_canary_stop": skipped_canary_count,
                "applied": cutover_applied_count + provider_revoked_count,
                "manual_required": manual_pending_count + manual_evidence_uploaded_count + manual_verified_count,
                "api_apply_failed": api_probe_failed_count + cutover_failed_count,
            },
            "preflight": {"policy_gate_passed": preflight_ok, "snapshot": preflight_snapshot},
            "post_health": {"policy_gate_passed": post_health_ok, "snapshot": policy_snapshot},
            "rollback_required": rollback_required,
        }
        await db.security_key_rotation_runs.insert_one(run_doc)
        await db.security_key_rotation_evidence.insert_one(
            {
                "evidence_id": f"keyrot_evd_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "plan_id": body.plan_id,
                "captured_at": _utc_now_iso(),
                "status": status,
                "steps": steps,
                "policy_snapshot": policy_snapshot,
                "apply_window": apply_window_doc,
                "prerequisite_refresh": prereq_refresh_result,
            }
        )

        incident = None
        auto_rollback = None
        if rollback_required:
            auto_rollback = await _auto_rollback_after_failed_health(
                run_id=run_id,
                plan_id=body.plan_id,
                actor_user_id=getattr(user, "user_id", "admin"),
            )
            incident = await _open_rotation_incident(
                plan_id=body.plan_id,
                run_id=run_id,
                severity="critical",
                message="Key rotation apply failed post-health checks",
                details={"policy_snapshot": policy_snapshot},
            )
            await db.security_key_rotation_runs.update_one(
                {"run_id": run_id},
                {"$set": {"status": "rolled_back", "rolled_back_at": auto_rollback.get("executed_at"), "rollback_id": auto_rollback.get("rollback_id")}},
            )

        await db.security_key_rotation_plans.update_one(
            {"plan_id": body.plan_id},
            {"$set": {"status": "applied" if status.startswith("completed") else status, "last_run_id": run_id, "last_run_at": _utc_now_iso()}},
        )

        return {
            "run_id": run_id,
            "plan_id": body.plan_id,
            "status": "rolled_back" if rollback_required else status,
            "rollback_required": rollback_required,
            "rollback_id": (auto_rollback or {}).get("rollback_id") if auto_rollback else None,
            "incident_id": (incident or {}).get("incident_id") if incident else None,
            "summary": run_doc["summary"],
        }
    finally:
        if allow_override:
            await _deactivate_policy_gate_apply_window(apply_window_doc)


@router.post("/rollback/{run_id}")
async def key_rotation_rollback(request: Request, run_id: str):
    user = await require_admin(request)
    run = await db.security_key_rotation_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rollback_doc = await _auto_rollback_after_failed_health(
        run_id=run_id,
        plan_id=str(run.get("plan_id") or ""),
        actor_user_id=getattr(user, "user_id", "admin"),
    )
    await db.security_key_rotation_runs.update_one(
        {"run_id": run_id},
        {"$set": {"status": "rolled_back", "rolled_back_at": rollback_doc.get("executed_at"), "rollback_id": rollback_doc.get("rollback_id")}},
    )
    return {"run_id": run_id, "status": "rolled_back", "rollback_id": rollback_doc.get("rollback_id"), "actions": rollback_doc.get("actions", [])}


@router.post("/runs/{run_id}/manual-evidence")
async def key_rotation_manual_evidence(request: Request, run_id: str, body: KeyRotationManualEvidenceBody):
    user = await require_admin(request)
    run_doc = await db.security_key_rotation_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Run not found")
    step_doc = await db.security_key_rotation_steps.find_one({"run_id": run_id, "provider_id": body.provider_id}, {"_id": 0})
    if not step_doc:
        raise HTTPException(status_code=404, detail="Provider step not found for run")
    current_status = str(step_doc.get("status") or "")
    if current_status not in {STEP_STATUS_MANUAL_PENDING, STEP_STATUS_MANUAL_EVIDENCE_UPLOADED, STEP_STATUS_MANUAL_VERIFIED}:
        raise HTTPException(status_code=400, detail=f"Manual evidence not allowed for status {current_status}")

    rules = _manual_evidence_rules()
    evidence_note = str(body.evidence_note or "").strip()
    evidence_links = _normalize_nonempty_lines(body.evidence_links)
    verification_checks = _normalize_nonempty_lines(body.verification_checks)
    if len(evidence_note) < max(1, int(rules.get("min_note_chars") or 1)):
        raise HTTPException(status_code=400, detail=f"Manual evidence note must be at least {rules.get('min_note_chars')} characters")
    if bool(rules.get("require_links")) and len(evidence_links) < int(rules.get("min_links") or 1):
        raise HTTPException(status_code=400, detail=f"Manual evidence requires at least {rules.get('min_links')} evidence link(s)")
    if body.mark_verified:
        min_links_verified = int(rules.get("min_links_verified") or 2)
        if len(evidence_links) < min_links_verified:
            raise HTTPException(status_code=400, detail=f"Verified manual evidence requires at least {min_links_verified} evidence links")
        if not verification_checks:
            raise HTTPException(status_code=400, detail="Verified manual evidence requires at least one verification check")
        if not bool(body.provider_console_confirmed):
            raise HTTPException(status_code=400, detail="Verified manual evidence requires provider_console_confirmed=true")

    next_status = STEP_STATUS_MANUAL_VERIFIED if body.mark_verified else STEP_STATUS_MANUAL_EVIDENCE_UPLOADED
    evidence_event = {
        "submitted_at": _utc_now_iso(),
        "submitted_by": getattr(user, "user_id", "admin"),
        "evidence_note": evidence_note,
        "evidence_links": evidence_links,
        "evidence_link_hashes": [_sha256_hex(item) for item in evidence_links],
        "verification_checks": verification_checks,
        "provider_console_confirmed": bool(body.provider_console_confirmed),
        "mark_verified": bool(body.mark_verified),
    }
    await db.security_key_rotation_steps.update_one(
        {"run_id": run_id, "provider_id": body.provider_id},
        {
            "$set": {"status": next_status, "legacy_status": _legacy_step_status(next_status), "manual_evidence_last_event": evidence_event, "updated_at": _utc_now_iso()},
            "$push": {"manual_evidence_events": evidence_event},
        },
    )
    updated_step = await db.security_key_rotation_steps.find_one({"run_id": run_id, "provider_id": body.provider_id}, {"_id": 0})
    summary = await _recompute_run_summary(run_id)
    await db.security_key_rotation_runs.update_one(
        {"run_id": run_id},
        {"$set": {"summary": summary, "last_manual_evidence_at": _utc_now_iso(), "last_manual_evidence_provider_id": body.provider_id}},
    )
    await _emit_provider_rotation_signal(
        run_id=run_id,
        plan_id=str(run_doc.get("plan_id") or ""),
        provider_id=body.provider_id,
        status=next_status,
        message="Manual provider evidence updated",
        severity="medium",
    )
    return {"run_id": run_id, "provider_id": body.provider_id, "status": next_status, "step": updated_step, "summary": summary}


@router.get("/runs")
async def list_key_rotation_runs(request: Request, limit: int = Query(20, ge=1, le=100)):
    await require_admin(request)
    runs = []
    async for doc in db.security_key_rotation_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(limit):
        runs.append(doc)
    return {"runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}/evidence")
async def get_key_rotation_evidence(request: Request, run_id: str):
    await require_admin(request)
    run = await db.security_key_rotation_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = await db.security_key_rotation_steps.find({"run_id": run_id}, {"_id": 0}).to_list(1000)
    evidence = await db.security_key_rotation_evidence.find({"run_id": run_id}, {"_id": 0}).to_list(500)
    incidents = await db.security_incidents.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    rollbacks = await db.security_key_rotation_rollbacks.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    return {
        "run": run,
        "steps": steps,
        "evidence": evidence,
        "incidents": incidents,
        "rollbacks": rollbacks,
        "counts": {"steps": len(steps), "evidence": len(evidence), "incidents": len(incidents), "rollbacks": len(rollbacks)},
    }


def _render_compliance_bundle_markdown(bundle: Dict[str, Any]) -> str:
    run = bundle.get("run") or {}
    summary = run.get("summary") or {}
    lines = [
        "# Key Rotation Compliance Bundle",
        "",
        f"- Generated At: {bundle.get('generated_at')}",
        f"- Run ID: {run.get('run_id')}",
        f"- Plan ID: {run.get('plan_id')}",
        f"- Status: {run.get('status')}",
        "",
        "## Summary",
        f"- Providers Total: {summary.get('providers_total')}",
        f"- Credential Validated: {summary.get('credential_validated')}",
        f"- Cutover Applied: {summary.get('cutover_applied')}",
        f"- Provider Revoked: {summary.get('provider_revoked', 0)}",
        f"- Manual Pending: {summary.get('manual_pending_evidence')}",
        f"- Manual Verified: {summary.get('manual_applied_verified')}",
    ]
    return "\n".join(lines)


@router.get("/runs/{run_id}/compliance-bundle")
async def get_key_rotation_compliance_bundle(request: Request, run_id: str, format: Literal["json", "markdown"] = Query("json")):
    await require_admin(request)
    run = await db.security_key_rotation_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    plan = await db.security_key_rotation_plans.find_one({"plan_id": run.get("plan_id")}, {"_id": 0}) or {}
    steps = await db.security_key_rotation_steps.find({"run_id": run_id}, {"_id": 0}).to_list(500)
    evidence = await db.security_key_rotation_evidence.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    incidents = await db.security_incidents.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    rollbacks = await db.security_key_rotation_rollbacks.find({"run_id": run_id}, {"_id": 0}).to_list(200)
    siem_alerts = await db.siem_triggered_alerts.find({"rotation_run_id": run_id}, {"_id": 0}).to_list(500)
    readiness_map = _build_readiness_map()
    providers = [readiness_map[item["provider_id"]] for item in PROVIDER_DEFINITIONS]
    apply_statuses = [str((p.get("apply_capability") or {}).get("status") or "unknown") for p in providers]
    readiness_delta = {
        "api_probe_only_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_PROBE_READY]),
        "api_rotate_ready": len([s for s in apply_statuses if s == READINESS_STATUS_API_ROTATE_READY]),
        "manual_by_constraint": len([s for s in apply_statuses if s == READINESS_STATUS_MANUAL_BY_CONSTRAINT]),
        "adapter_missing": len([s for s in apply_statuses if s == READINESS_STATUS_ADAPTER_MISSING]),
    }
    bundle = {
        "bundle_id": f"keyrot_bundle_{uuid.uuid4().hex[:12]}",
        "generated_at": _utc_now_iso(),
        "run": run,
        "plan": plan,
        "steps": steps,
        "evidence": evidence,
        "incidents": incidents,
        "rollbacks": rollbacks,
        "siem_alerts": siem_alerts,
        "readiness_delta": readiness_delta,
        "counts": {
            "steps": len(steps),
            "evidence": len(evidence),
            "incidents": len(incidents),
            "rollbacks": len(rollbacks),
            "siem_alerts": len(siem_alerts),
            "provider_revoked": len([s for s in steps if s.get("status") == STEP_STATUS_PROVIDER_REVOKED]),
        },
    }
    await db.security_key_rotation_compliance_bundles.insert_one(bundle)
    bundle.pop("_id", None)
    if format == "markdown":
        markdown = _render_compliance_bundle_markdown(bundle)
        return {"bundle_id": bundle["bundle_id"], "format": "markdown", "file_name": f"{run_id}_compliance_bundle.md", "content": markdown}
    return bundle