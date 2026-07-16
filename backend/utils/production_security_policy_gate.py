from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import hashlib
import hmac
import json
import os
import uuid

from utils.access_control_engine import evaluate_api_access


SENSITIVE_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SENSITIVE_PREFIXES = (
    "/api/admin/security/",
    "/api/admin/access-control/",
    "/api/admin/feature-flags",
    "/api/admin/features/",
    "/api/admin/features",
    "/api/subscriptions/lifecycle/reconcile",
    "/api/admin/access-control/subscription-transition",
)

DEPLOYMENT_CONTROL_PREFIXES = (
    "/api/admin/security/deployments/deploy",
    "/api/admin/security/deployments/rollback",
)

FEATURE_ACTIVATION_PREFIXES = (
    "/api/admin/feature-flags",
    "/api/admin/features/",
    "/api/admin/features",
    "/api/whitelabel/feature-toggles",
)

EXEMPT_PREFIXES = (
    "/api/health",
    "/api/system/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/verify",
    "/api/auth/forgot",
    "/api/auth/reset",
    "/api/auth/apple/callback",
    "/api/auth/microsoft/callback",
    "/api/auth/google/callback",
    "/api/payments/fedapay/webhook",
    "/api/paypal/webhook",
    "/api/iap/apple/webhook",
    "/api/iap/google/webhook",
    "/api/webhook/",
    "/api/admin/security/policy-gate/recover-prerequisites",
)


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _canonical_signature_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def sign_policy_payload(payload: dict[str, Any]) -> str:
    secret = str(os.environ.get("POLICY_GATE_AUDIT_SECRET") or os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("POLICY_GATE_AUDIT_SECRET/JWT_SECRET must be configured with length >= 32")
    canonical = _canonical_signature_payload(payload)
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def _scope_for_path(path: str) -> str:
    normalized = str(path or "").strip().lower()
    if any(normalized.startswith(prefix) for prefix in DEPLOYMENT_CONTROL_PREFIXES):
        return "deployment_control"
    if any(normalized.startswith(prefix) for prefix in FEATURE_ACTIVATION_PREFIXES):
        return "feature_activation"
    return "sensitive_mutation"


def _as_user_doc(user: Any) -> dict[str, Any] | None:
    if user is None:
        return None
    if isinstance(user, dict):
        return user
    doc = {
        "user_id": getattr(user, "user_id", None),
        "email": getattr(user, "email", None),
        "is_admin": bool(getattr(user, "is_admin", False)),
        "role": getattr(user, "role", None),
        "subscription_plan": getattr(user, "subscription_plan", None),
        "is_employee": bool(getattr(user, "is_employee", False)),
        "permissions": getattr(user, "permissions", None),
    }
    return doc


def should_enforce_policy_gate(path: str, method: str) -> bool:
    upper_method = str(method or "").upper()
    if upper_method not in SENSITIVE_MUTATION_METHODS:
        return False
    if any(str(path or "").startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return False
    return any(str(path or "").startswith(prefix) for prefix in SENSITIVE_PREFIXES)


async def collect_policy_gate_signals(db_ref=None, allow_rotation_window_override: bool = False) -> dict[str, Any]:
    if db_ref is None:
        from routes.db import db as global_db
        db_ref = global_db

    now = datetime.now(timezone.utc)

    admin_gate_doc = await db_ref.admin_e2e_health_gate_runs.find_one({}, {"_id": 0}, sort=[("ran_at", -1)]) or {}
    plan_guardrail_doc = await db_ref.subscription_plan_guardrail_runs.find_one({}, {"_id": 0}, sort=[("ran_at", -1)]) or {}
    sso_state_doc = await db_ref.system_runtime_flags.find_one({"key": "sso_e2e_validation_state"}, {"_id": 0}) or {}
    trust_doc = await db_ref.cia_trust_heartbeat.find_one({}, {"_id": 0}, sort=[("captured_at", -1)]) or {}

    cia_score = trust_doc.get("trust_score")
    try:
        cia_score = float(cia_score) if cia_score is not None else None
    except Exception:
        cia_score = None
    cia_min_score = float(os.environ.get("POLICY_GATE_MIN_CIA_SCORE") or 75)

    checks = [
        {
            "name": "admin_e2e_health_gate",
            "passed": str(admin_gate_doc.get("status") or "").lower() == "pass",
            "value": str(admin_gate_doc.get("status") or "unknown").lower(),
            "required": "pass",
        },
        {
            "name": "subscription_plan_guardrail",
            "passed": str(plan_guardrail_doc.get("state") or plan_guardrail_doc.get("status") or "").lower() == "pass",
            "value": str(plan_guardrail_doc.get("state") or plan_guardrail_doc.get("status") or "unknown").lower(),
            "required": "pass",
        },
        {
            "name": "sso_e2e_validation",
            "passed": str(sso_state_doc.get("state") or "").lower() == "pass",
            "value": str(sso_state_doc.get("state") or "unknown").lower(),
            "required": "pass",
        },
        {
            "name": "cia_trust_score",
            "passed": cia_score is not None and cia_score >= cia_min_score,
            "value": cia_score,
            "required": cia_min_score,
        },
    ]

    rotation_window_doc: dict[str, Any] = {}
    override_active = False
    override_expires_at = ""
    if allow_rotation_window_override:
        rotation_window_doc = await db_ref.system_runtime_flags.find_one(
            {"key": "key_rotation_apply_window_state"},
            {"_id": 0},
        ) or {}
        override_expires_at = str(rotation_window_doc.get("expires_at") or "").strip()
        if str(rotation_window_doc.get("state") or "").lower() == "active" and override_expires_at:
            try:
                expiry_dt = datetime.fromisoformat(override_expires_at.replace("Z", "+00:00"))
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                override_active = datetime.now(timezone.utc) <= expiry_dt.astimezone(timezone.utc)
            except Exception:
                override_active = False

    overridden_checks: list[str] = []
    if override_active:
        force_checks = set(rotation_window_doc.get("force_checks") or [
            "admin_e2e_health_gate",
            "subscription_plan_guardrail",
            "sso_e2e_validation",
            "cia_trust_score",
        ])
        for check in checks:
            if check.get("name") in force_checks and not check.get("passed"):
                check["override_applied"] = True
                check["original_passed"] = bool(check.get("passed"))
                check["original_value"] = check.get("value")
                check["value"] = "rotation_window_override"
                check["passed"] = True
                overridden_checks.append(str(check.get("name") or ""))

    failed_checks = [check["name"] for check in checks if not check["passed"]]
    cia_source_ts = trust_doc.get("captured_at") or trust_doc.get("timestamp")
    if hasattr(cia_source_ts, "isoformat"):
        cia_source_ts = cia_source_ts.isoformat()

    return {
        "evaluated_at": now.isoformat(),
        "passed": len(failed_checks) == 0,
        "failed_checks": failed_checks,
        "checks": checks,
        "cia_min_score": cia_min_score,
        "cia_score": cia_score,
        "cia_source_ts": cia_source_ts,
        "rotation_window_override_active": override_active,
        "rotation_window_id": rotation_window_doc.get("window_id") if override_active else None,
        "rotation_window_expires_at": override_expires_at if override_active else None,
        "overridden_checks": overridden_checks,
    }


async def evaluate_policy_gate_decision(path: str, method: str, user: Any, db_ref=None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    decision_id = f"pg_{uuid.uuid4().hex[:14]}"
    user_doc = _as_user_doc(user)

    if not user_doc:
        return {
            "decision_id": decision_id,
            "evaluated_at": now.isoformat(),
            "path": path,
            "method": str(method or "").upper(),
            "scope": _scope_for_path(path),
            "allowed": False,
            "status_code": 401,
            "reason_code": "auth_required",
            "message": "Authentication required for protected action.",
            "failed_checks": ["auth_context"],
            "actor_user_id": None,
            "actor_email": None,
        }

    access_decision = evaluate_api_access(path, str(method or "").upper(), user_doc)
    if not access_decision.get("allowed"):
        reason = str(access_decision.get("reason") or "access_denied")
        status_code = 403
        message = "Blocked by policy gate due to plan or permission mismatch."
        if reason == "subscription_required":
            message = "Blocked by policy gate because required subscription entitlement is missing."
        elif reason == "admin_or_employee_permission_required":
            message = "Blocked by policy gate because delegated admin permission is missing."

        return {
            "decision_id": decision_id,
            "evaluated_at": now.isoformat(),
            "path": path,
            "method": str(method or "").upper(),
            "scope": _scope_for_path(path),
            "allowed": False,
            "status_code": status_code,
            "reason_code": reason,
            "message": message,
            "failed_checks": [reason],
            "required_permission": access_decision.get("required_permission"),
            "required_plan": access_decision.get("required_plan"),
            "current_plan": access_decision.get("current_plan"),
            "actor_user_id": user_doc.get("user_id"),
            "actor_email": user_doc.get("email"),
        }

    signals = await collect_policy_gate_signals(db_ref=db_ref)
    if not signals.get("passed"):
        return {
            "decision_id": decision_id,
            "evaluated_at": now.isoformat(),
            "path": path,
            "method": str(method or "").upper(),
            "scope": _scope_for_path(path),
            "allowed": False,
            "status_code": 503,
            "reason_code": "policy_prerequisites_not_met",
            "message": "Blocked because production policy gate prerequisites are not currently healthy.",
            "failed_checks": signals.get("failed_checks", []),
            "signals": signals,
            "actor_user_id": user_doc.get("user_id"),
            "actor_email": user_doc.get("email"),
        }

    return {
        "decision_id": decision_id,
        "evaluated_at": now.isoformat(),
        "path": path,
        "method": str(method or "").upper(),
        "scope": _scope_for_path(path),
        "allowed": True,
        "status_code": 200,
        "reason_code": "allowed",
        "message": "Allowed by production policy gate.",
        "failed_checks": [],
        "signals": signals,
        "actor_user_id": user_doc.get("user_id"),
        "actor_email": user_doc.get("email"),
    }


async def persist_policy_gate_audit(decision: dict[str, Any], db_ref=None) -> dict[str, Any]:
    if db_ref is None:
        from routes.db import db as global_db
        db_ref = global_db

    snapshot = {
        "decision_id": decision.get("decision_id") or f"pg_{uuid.uuid4().hex[:14]}",
        "evaluated_at": decision.get("evaluated_at") or _json_default(datetime.now(timezone.utc)),
        "path": decision.get("path"),
        "method": decision.get("method"),
        "scope": decision.get("scope"),
        "allowed": bool(decision.get("allowed")),
        "status_code": int(decision.get("status_code") or 0),
        "reason_code": decision.get("reason_code"),
        "failed_checks": list(decision.get("failed_checks") or []),
        "actor_user_id": decision.get("actor_user_id"),
        "actor_email": decision.get("actor_email"),
    }
    signature = sign_policy_payload(snapshot)
    audit_doc = {
        **snapshot,
        "signature": signature,
        "signals": decision.get("signals"),
        "message": decision.get("message"),
    }
    await db_ref.production_security_policy_gate_audit_logs.insert_one(audit_doc)
    safe_audit_doc = dict(audit_doc)
    safe_audit_doc.pop("_id", None)
    return safe_audit_doc