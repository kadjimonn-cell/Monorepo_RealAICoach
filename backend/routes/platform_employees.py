"""Platform Employee Management.
Admin can add users as platform employees, assign roles, grant/revoke premium access,
and manage per-role feature permissions. All actions are audit-logged.
"""

import os
import uuid
import io
import csv
import json
import logging
import re
import secrets
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from routes.db import db, require_auth, require_admin
from utils.email_service import is_email_configured
from utils.access_governance import append_access_ledger
from utils.access_control_engine import (
    PLATFORM_EMPLOYEE_PERMISSIONS,
    PLATFORM_EMPLOYEE_ROLES,
    DEFAULT_ROLE_PERMISSIONS,
)

logger = logging.getLogger("platform_employees")
router = APIRouter(prefix="/admin/employees", tags=["Platform Employees"])

LEGACY_PLATFORM_ROLES = [
    "Manager", "Support Team", "Developer", "Finance Advisor",
    "Engineer", "Designer", "QA", "Marketing", "Operations", "Custom",
]
PLATFORM_ROLES = sorted(set([*LEGACY_PLATFORM_ROLES, *PLATFORM_EMPLOYEE_ROLES]))

# Default feature access per role (what each role can access without premium_access)
DEFAULT_ROLE_FEATURES: dict[str, list[str]] = {
    "Manager": [
        "dashboard", "analytics", "team_management", "conversations",
        "ai_coach", "reports", "calendar", "documents",
    ],
    "Support Team": [
        "dashboard", "conversations", "ai_coach", "support_tickets",
    ],
    "Developer": [
        "dashboard", "api_access", "ai_coach", "documents",
        "integrations", "system_logs",
    ],
    "Finance Advisor": [
        "dashboard", "analytics", "reports", "revenue",
        "subscriptions", "invoices",
    ],
    "Engineer": [
        "dashboard", "api_access", "ai_coach", "documents",
        "integrations", "system_logs", "infrastructure",
    ],
    "Designer": [
        "dashboard", "ai_coach", "documents", "branding",
    ],
    "QA": [
        "dashboard", "ai_coach", "documents", "system_logs", "testing",
    ],
    "Marketing": [
        "dashboard", "analytics", "ai_coach", "documents",
        "campaigns", "reports",
    ],
    "Operations": [
        "dashboard", "analytics", "team_management", "reports",
        "infrastructure", "system_logs",
    ],
    "Custom": [],
}

# All available features that can be granted
ALL_FEATURES = sorted(set(
    f for features in DEFAULT_ROLE_FEATURES.values() for f in features
) | {
    "executive_dashboard", "automation", "advanced_analytics",
    "export", "billing", "webhooks", "ai_features",
})


# ── Models ──

class BulkInviteEntry(BaseModel):
    email: str
    platform_role: str
    premium_access: bool = False


class BulkInvite(BaseModel):
    invites: list[BulkInviteEntry] = Field(default_factory=list)


class AddEmployee(BaseModel):
    email: str
    platform_role: str
    premium_access: bool = False
    feature_access: list[str] = Field(default_factory=list)
    employee_permissions: list[str] = Field(default_factory=list)


class UpdateEmployee(BaseModel):
    platform_role: Optional[str] = None
    premium_access: Optional[bool] = None
    feature_access: Optional[list[str]] = None
    employee_permissions: Optional[list[str]] = None


class ActivityEventRequest(BaseModel):
    event_type: str
    feature: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    source: str = "web"


class AICommandRequest(BaseModel):
    command: str
    execute: bool = False


class AccessRequestDecision(BaseModel):
    action: str
    reason: Optional[str] = None


class CreateAccessRequest(BaseModel):
    requested_role: Optional[str] = None
    requested_features: list[str] = Field(default_factory=list)
    requested_permissions: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


def _filter_permissions(permissions: list[str] | None) -> list[str]:
    return sorted([p for p in set(permissions or []) if p in PLATFORM_EMPLOYEE_PERMISSIONS])


def _default_permissions_for_role(role: str) -> list[str]:
    return _filter_permissions(DEFAULT_ROLE_PERMISSIONS.get(role, []))


async def _require_platform_access(request: Request, permission: str):
    return await require_admin(request)


async def _require_any_platform_access(request: Request, permissions: list[str]):
    if not permissions:
        raise HTTPException(500, "Permission configuration error")
    last_error: HTTPException | None = None
    for permission in permissions:
        try:
            return await _require_platform_access(request, permission)
        except HTTPException as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise HTTPException(403, "Insufficient employee permissions")


# ── Audit Log Helper ──

async def _log_audit(
    admin_id: str,
    admin_email: str,
    action: str,
    target_user_id: str,
    target_email: str,
    details: dict | None = None,
):
    """Write an entry to the employee_audit_log collection."""
    await db.employee_audit_log.insert_one({
        "log_id": f"eal_{uuid.uuid4().hex[:12]}",
        "admin_id": admin_id,
        "admin_email": admin_email,
        "action": action,
        "target_user_id": target_user_id,
        "target_email": target_email,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    await append_access_ledger(
        event_type=f"team_mgmt_{action}",
        actor_user_id=admin_id,
        actor_email=admin_email,
        target_user_id=target_user_id,
        metadata=details or {},
    )


async def _require_high_risk_admin_change(
    request: Request,
    action: str,
    target_user_id: str = "",
    payload: dict | None = None,
):
    admin = await require_admin(request)
    await append_access_ledger(
        event_type="rbac_single_admin_team_management",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        target_user_id=target_user_id,
        metadata={
            "action": action,
            "approval_mode": "single_admin",
            "scope": "team_management",
            "payload": payload or {},
        },
    )
    return admin


@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    action: Optional[str] = None,
    target: Optional[str] = None,
):
    """Get employee management audit log with pagination and filters."""
    await _require_platform_access(request, "employee.view_audit_logs")
    query: dict = {}
    if action:
        query["action"] = action
    if target:
        query["$or"] = [
            {"target_email": {"$regex": re.escape(str(target)), "$options": "i"}},
            {"target_user_id": target},
        ]

    total = await db.employee_audit_log.count_documents(query)
    skip = (page - 1) * limit
    logs = (
        await db.employee_audit_log.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


ACTION_LABELS = {
    "employee_added": "Employee Added",
    "employee_removed": "Employee Removed",
    "premium_granted": "Premium Granted",
    "premium_revoked": "Premium Revoked",
    "role_changed": "Role Changed",
    "access_updated": "Access Updated",
    "access_request_approved": "Access Request Approved",
    "access_request_denied": "Access Request Denied",
    "anomaly_alert_dispatched": "Anomaly Alert Dispatched",
}

TEAM_MANAGEMENT_LEDGER_QUERY = {
    "$or": [
        {"metadata.scope": "team_management"},
        {"event_type": {"$regex": "^team_mgmt_"}},
    ]
}


def _format_details(action: str, details: dict) -> str:
    """Format details dict into a readable string for CSV."""
    if not details:
        return ""
    if action == "employee_added":
        parts = [f"Role: {details.get('role', '?')}"]
        if details.get("premium_access"):
            parts.append("Premium: Yes")
        feats = details.get("feature_access", [])
        if feats:
            parts.append(f"Features: {', '.join(feats)}")
        return "; ".join(parts)
    if action == "employee_removed":
        parts = [f"Was: {details.get('role', '?')}"]
        if details.get("had_premium"):
            parts.append("Had Premium")
        return "; ".join(parts)
    if action in ("premium_granted", "premium_revoked"):
        pa = details.get("premium_access", {})
        if isinstance(pa, dict):
            return f"{pa.get('from', '?')} -> {pa.get('to', '?')}"
        return ""
    if action == "role_changed":
        role = details.get("role", {})
        if isinstance(role, dict):
            return f"{role.get('from', '?')} -> {role.get('to', '?')}"
        return ""
    if action == "access_updated":
        parts = []
        added = details.get("features_added", [])
        removed = details.get("features_removed", [])
        if added:
            parts.append(f"+{', '.join(added)}")
        if removed:
            parts.append(f"-{', '.join(removed)}")
        return "; ".join(parts)
    return str(details)


@router.get("/audit-log/export")
async def export_audit_log(
    request: Request,
    action: Optional[str] = None,
    target: Optional[str] = None,
):
    """Export audit log as CSV for compliance reporting."""
    await _require_platform_access(request, "employee.view_audit_logs")

    query: dict = {}
    if action:
        query["action"] = action
    if target:
        query["$or"] = [
            {"target_email": {"$regex": re.escape(str(target)), "$options": "i"}},
            {"target_user_id": target},
        ]

    logs = (
        await db.employee_audit_log.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(10000)
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Action", "Admin", "Target Employee", "Details"])

    for log in logs:
        ts = log.get("timestamp", "")
        act = ACTION_LABELS.get(log.get("action", ""), log.get("action", ""))
        admin_email = log.get("admin_email", "")
        target_email = log.get("target_email", "")
        details = _format_details(log.get("action", ""), log.get("details", {}))
        writer.writerow([ts, act, admin_email, target_email, details])

    output.seek(0)
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"employee_audit_log_{now}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/approval-mode")
async def get_team_management_approval_mode(request: Request):
    """Return Team Management approval mode with recent ledger-linked evidence."""
    await require_admin(request)
    recent = (
        await db.enterprise_access_ledger.find(
            TEAM_MANAGEMENT_LEDGER_QUERY,
            {
                "_id": 0,
                "entry_id": 1,
                "event_type": 1,
                "actor_email": 1,
                "target_user_id": 1,
                "created_at": 1,
                "metadata": 1,
            },
        )
        .sort("created_at", -1)
        .limit(12)
        .to_list(12)
    )
    evidence_count = await db.enterprise_access_ledger.count_documents(TEAM_MANAGEMENT_LEDGER_QUERY)
    return {
        "scope": "team_management",
        "approval_mode": "single_admin",
        "approval_label": "Single Admin Approval",
        "evidence_count": int(evidence_count),
        "recent_evidence": recent,
    }


@router.get("/approval-mode/evidence/export")
async def export_team_management_approval_evidence(
    request: Request,
    limit: int = Query(500, ge=10, le=5000),
):
    """Export Team Management approval evidence from immutable access ledger as CSV."""
    await require_admin(request)
    rows = (
        await db.enterprise_access_ledger.find(
            TEAM_MANAGEMENT_LEDGER_QUERY,
            {
                "_id": 0,
                "entry_id": 1,
                "event_type": 1,
                "actor_user_id": 1,
                "actor_email": 1,
                "target_user_id": 1,
                "created_at": 1,
                "metadata": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "created_at",
        "entry_id",
        "event_type",
        "actor_user_id",
        "actor_email",
        "target_user_id",
        "action",
        "approval_mode",
        "scope",
        "metadata_json",
    ])

    for row in rows:
        metadata = row.get("metadata") or {}
        writer.writerow([
            row.get("created_at", ""),
            row.get("entry_id", ""),
            row.get("event_type", ""),
            row.get("actor_user_id", ""),
            row.get("actor_email", ""),
            row.get("target_user_id", ""),
            metadata.get("action", ""),
            metadata.get("approval_mode", ""),
            metadata.get("scope", ""),
            json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
        ])

    output.seek(0)
    filename = f"team_management_approval_evidence_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Endpoints ──

@router.get("/roles-config")
async def get_roles_config(request: Request):
    """Get available platform roles, features, and default permissions."""
    await _require_any_platform_access(request, ["employee.manage_users", "employee.manage_access"])
    role_permission_defaults = {role: _default_permissions_for_role(role) for role in PLATFORM_ROLES}
    return {
        "roles": PLATFORM_ROLES,
        "all_features": ALL_FEATURES,
        "default_role_features": DEFAULT_ROLE_FEATURES,
        "all_permissions": PLATFORM_EMPLOYEE_PERMISSIONS,
        "default_role_permissions": role_permission_defaults,
    }


@router.get("/search")
async def search_users(request: Request, q: str = ""):
    """Search users by email to add as platform employees."""
    await _require_any_platform_access(request, ["employee.manage_users", "employee.manage_access"])
    if not q or len(q) < 2:
        return {"users": []}
    users = await db.users.find(
        {"email": {"$regex": re.escape(str(q)), "$options": "i"}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1,
         "subscription_plan": 1, "platform_role": 1, "is_admin": 1},
    ).limit(10).to_list(10)
    return {"users": users}


@router.get("")
async def list_employees(request: Request):
    """List all platform employees."""
    await _require_any_platform_access(request, ["employee.manage_users", "employee.manage_access"])
    employees = await db.users.find(
        {"platform_role": {"$exists": True, "$ne": None}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1,
         "platform_role": 1, "premium_access": 1,
         "feature_access": 1, "employee_permissions": 1, "subscription_plan": 1,
         "is_admin": 1, "last_active": 1, "created_at": 1},
    ).to_list(200)
    return {
        "employees": employees,
        "total": len(employees),
        "premium_count": sum(1 for e in employees if e.get("premium_access")),
        "role_counts": _count_roles(employees),
    }


@router.post("")
async def add_employee(body: AddEmployee, request: Request):
    """Invite a user to become a platform employee.

    SECURITY: Always sends an invitation email and marks the invitation as `pending`.
    The user MUST click the link in the email and explicitly accept before
    `platform_role` is set on their account. This prevents silent onboarding.
    """
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_add",
        target_user_id=body.user_id or body.email,
        payload={"platform_role": body.platform_role, "premium_access": bool(body.premium_access)},
    )
    if body.platform_role not in PLATFORM_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {PLATFORM_ROLES}")

    email_raw = body.email.lower().strip()
    if not email_raw or "@" not in email_raw:
        raise HTTPException(400, "Invalid email")

    user = await db.users.find_one(
        {"email": email_raw},
        {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1},
    )
    if user and user.get("platform_role"):
        raise HTTPException(409, f"User is already a platform employee with role: {user['platform_role']}")

    existing_inv = await db.platform_employee_invitations.find_one(
        {"email": email_raw, "status": "pending"}, {"_id": 0, "invitation_id": 1, "expires_at": 1},
    )
    if existing_inv:
        raise HTTPException(409, f"An invitation is already pending (expires {existing_inv.get('expires_at')})")

    now_iso_dt = datetime.now(timezone.utc)
    now_iso = now_iso_dt.isoformat()
    token = secrets.token_urlsafe(32)
    invitation_id = f"empinv_{uuid.uuid4().hex[:12]}"
    expires_at = now_iso_dt + timedelta(hours=72)

    # Pre-compute desired feature/permission payload so acceptance is deterministic
    features = body.feature_access or DEFAULT_ROLE_FEATURES.get(body.platform_role, [])
    permissions = _filter_permissions(body.employee_permissions or _default_permissions_for_role(body.platform_role))

    await db.platform_employee_invitations.insert_one({
        "invitation_id": invitation_id,
        "token_hash": _hash_invitation_token(token),
        "token_last4": token[-4:],
        "email": email_raw,
        "platform_role": body.platform_role,
        "premium_access": bool(body.premium_access),
        "feature_access": features,
        "employee_permissions": permissions,
        "invited_by_user_id": admin.user_id,
        "invited_by_email": admin.email,
        "status": "pending",
        "created_at": now_iso,
        "expires_at": expires_at.isoformat(),
        "accepted_at": None,
        "accepted_user_id": None,
        "existing_user_id": user["user_id"] if user else None,
    })

    invite_url = _build_invitation_url(token)
    email_sent = False
    email_message_id: Optional[str] = None
    try:
        from utils.email_notifications import send_platform_employee_invitation
        email_res = await send_platform_employee_invitation(
            recipient_email=email_raw,
            platform_role=body.platform_role,
            invited_by_email=admin.email,
            invite_url=invite_url,
            expires_in_hours=72,
        )
        email_sent = bool(email_res and email_res.get("success"))
        email_message_id = (email_res or {}).get("message_id")
    except Exception as exc:
        logger.warning(f"[EMPLOYEE] invitation email failed for {email_raw}: {exc}")

    if email_message_id:
        await db.platform_employee_invitations.update_one(
            {"invitation_id": invitation_id},
            {"$set": {"last_email_id": email_message_id, "last_email_sent_at": now_iso}},
        )

    await _log_audit(
        admin.user_id, admin.email, "employee_invited",
        user["user_id"] if user else None, email_raw,
        {
            "platform_role": body.platform_role,
            "premium_access": bool(body.premium_access),
            "invitation_id": invitation_id,
            "expires_at": expires_at.isoformat(),
            "email_sent": email_sent,
            "existing_user": bool(user),
            "source": "single_invite",
        },
    )

    logger.info(
        f"[EMPLOYEE] Invited {email_raw} as {body.platform_role} "
        f"(premium={body.premium_access}, email_sent={email_sent}, existing_user={bool(user)})"
    )
    return {
        "invited": True,
        "status": "pending",
        "invitation_id": invitation_id,
        "email": email_raw,
        "platform_role": body.platform_role,
        "premium_access": bool(body.premium_access),
        "expires_at": expires_at.isoformat(),
        "email_sent": email_sent,
        "existing_user": bool(user),
        "message": "Invitation email sent. The user must click the link and accept to become an employee.",
    }


@router.post("/bulk-invite")
async def bulk_invite_employees(body: BulkInvite, request: Request):
    """Invite multiple platform employees at once. Applies role defaults for features/permissions.

    Each entry is processed independently; failures are reported per-row and do not abort the batch.
    Caps at 100 entries per call.
    """
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_bulk_invite",
        target_user_id="bulk",
        payload={"invites_count": len(body.invites or [])},
    )
    invites = (body.invites or [])[:100]
    now_iso_dt = datetime.now(timezone.utc)
    now_iso = now_iso_dt.isoformat()
    success: list[dict] = []
    invited: list[dict] = []
    failed: list[dict] = []

    for entry in invites:
        email_raw = (entry.email or "").strip().lower()
        role = (entry.platform_role or "").strip()

        if not email_raw or "@" not in email_raw:
            failed.append({"email": entry.email or "", "reason": "Invalid email"})
            continue
        if role not in PLATFORM_ROLES:
            failed.append({"email": email_raw, "reason": f"Invalid role: {role}"})
            continue

        user = await db.users.find_one(
            {"email": email_raw},
            {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1},
        )
        if user and user.get("platform_role"):
            failed.append({
                "email": email_raw,
                "reason": f"Already employee ({user['platform_role']})",
            })
            continue

        if not user:
            # User doesn't exist — create an invitation with 72h expiry + email signup link
            existing_inv = await db.platform_employee_invitations.find_one(
                {"email": email_raw, "status": "pending"}, {"_id": 0}
            )
            if existing_inv:
                failed.append({"email": email_raw, "reason": "Invitation already pending"})
                continue

            token = secrets.token_urlsafe(32)
            invitation_id = f"empinv_{uuid.uuid4().hex[:12]}"
            expires_at = now_iso_dt + timedelta(hours=72)
            await db.platform_employee_invitations.insert_one({
                "invitation_id": invitation_id,
                "token_hash": _hash_invitation_token(token),
                "token_last4": token[-4:],
                "email": email_raw,
                "platform_role": role,
                "premium_access": bool(entry.premium_access),
                "invited_by_user_id": admin.user_id,
                "invited_by_email": admin.email,
                "status": "pending",
                "created_at": now_iso,
                "expires_at": expires_at.isoformat(),
                "accepted_at": None,
                "accepted_user_id": None,
                "existing_user_id": None,
            })

            invite_url = _build_invitation_url(token)
            email_sent = False
            email_message_id: Optional[str] = None
            try:
                from utils.email_notifications import send_platform_employee_invitation
                email_res = await send_platform_employee_invitation(
                    recipient_email=email_raw,
                    platform_role=role,
                    invited_by_email=admin.email,
                    invite_url=invite_url,
                    expires_in_hours=72,
                )
                email_sent = bool(email_res and email_res.get("success"))
                email_message_id = (email_res or {}).get("message_id")
            except Exception as exc:
                logger.warning(f"[EMPLOYEE-BULK] invitation email failed for {email_raw}: {exc}")

            if email_message_id:
                await db.platform_employee_invitations.update_one(
                    {"invitation_id": invitation_id},
                    {"$set": {
                        "last_email_id": email_message_id,
                        "last_email_sent_at": now_iso,
                    }},
                )

            await _log_audit(
                admin.user_id, admin.email, "employee_invited",
                None, email_raw,
                {
                    "platform_role": role,
                    "premium_access": bool(entry.premium_access),
                    "invitation_id": invitation_id,
                    "expires_at": expires_at.isoformat(),
                    "email_sent": email_sent,
                    "source": "bulk_invite",
                },
            )

            invited.append({
                "email": email_raw,
                "platform_role": role,
                "premium_access": bool(entry.premium_access),
                "invitation_id": invitation_id,
                "expires_at": expires_at.isoformat(),
                "email_sent": email_sent,
            })
            continue

        # ─── EXISTING USER (no platform_role yet) ───────────────────────
        # CRITICAL: do NOT silently grant platform_role. Send the same invitation
        # email + require explicit acceptance via the emailed link. This prevents
        # "silent onboarding" where the user sees themselves added to Team Management
        # without any email or consent.
        existing_inv = await db.platform_employee_invitations.find_one(
            {"email": email_raw, "status": "pending"}, {"_id": 0}
        )
        if existing_inv:
            failed.append({"email": email_raw, "reason": "Invitation already pending"})
            continue

        token = secrets.token_urlsafe(32)
        invitation_id = f"empinv_{uuid.uuid4().hex[:12]}"
        expires_at = now_iso_dt + timedelta(hours=72)
        await db.platform_employee_invitations.insert_one({
            "invitation_id": invitation_id,
            "token_hash": _hash_invitation_token(token),
            "token_last4": token[-4:],
            "email": email_raw,
            "platform_role": role,
            "premium_access": bool(entry.premium_access),
            "invited_by_user_id": admin.user_id,
            "invited_by_email": admin.email,
            "status": "pending",
            "created_at": now_iso,
            "expires_at": expires_at.isoformat(),
            "accepted_at": None,
            "accepted_user_id": None,
            "existing_user_id": user["user_id"],
        })

        invite_url = _build_invitation_url(token)
        email_sent = False
        email_message_id: Optional[str] = None
        try:
            from utils.email_notifications import send_platform_employee_invitation
            email_res = await send_platform_employee_invitation(
                recipient_email=email_raw,
                platform_role=role,
                invited_by_email=admin.email,
                invite_url=invite_url,
                expires_in_hours=72,
            )
            email_sent = bool(email_res and email_res.get("success"))
            email_message_id = (email_res or {}).get("message_id")
        except Exception as exc:
            logger.warning(f"[EMPLOYEE-BULK] invitation email failed for existing user {email_raw}: {exc}")

        if email_message_id:
            await db.platform_employee_invitations.update_one(
                {"invitation_id": invitation_id},
                {"$set": {
                    "last_email_id": email_message_id,
                    "last_email_sent_at": now_iso,
                }},
            )

        await _log_audit(
            admin.user_id, admin.email, "employee_invited",
            user["user_id"], email_raw,
            {
                "platform_role": role,
                "premium_access": bool(entry.premium_access),
                "invitation_id": invitation_id,
                "expires_at": expires_at.isoformat(),
                "email_sent": email_sent,
                "source": "bulk_invite",
                "existing_user": True,
            },
        )

        invited.append({
            "email": email_raw,
            "platform_role": role,
            "premium_access": bool(entry.premium_access),
            "invitation_id": invitation_id,
            "expires_at": expires_at.isoformat(),
            "email_sent": email_sent,
            "existing_user": True,
        })

    logger.info(
        f"[EMPLOYEE-BULK] actor={admin.email} added={len(success)} invited={len(invited)} failed={len(failed)}"
    )
    return {
        "total": len(invites),
        "added": len(success),
        "invited_count": len(invited),
        "failed_count": len(failed),
        "success": success,
        "invited": invited,
        "failed": failed,
    }


@router.post("/access-requests")
async def create_access_request(body: CreateAccessRequest, request: Request):
    """Create an employee access request for admin approval workflow."""
    user = await require_auth(request)
    if not body.requested_role and not body.requested_features and not body.requested_permissions:
        raise HTTPException(400, "requested_role, requested_features, or requested_permissions is required")

    existing_pending = await db.employee_access_requests.find_one(
        {"user_id": user.user_id, "status": "pending"},
        {"_id": 0, "request_id": 1},
    )
    if existing_pending:
        raise HTTPException(409, "A pending access request already exists")

    now = datetime.now(timezone.utc).isoformat()
    req_id = f"ear_{uuid.uuid4().hex[:12]}"
    await db.employee_access_requests.insert_one({
        "request_id": req_id,
        "user_id": user.user_id,
        "email": user.email,
        "requested_role": body.requested_role,
        "requested_features": sorted(list(set(body.requested_features or []))),
        "requested_permissions": _filter_permissions(body.requested_permissions),
        "reason": body.reason or "",
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    })
    return {"success": True, "request_id": req_id, "status": "pending"}


@router.get("/access-requests")
async def list_access_requests(
    request: Request,
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
):
    """List access requests for approval actions."""
    await require_admin(request)
    status = status.strip().lower()
    query = {} if status == "all" else {"status": status}
    requests = await db.employee_access_requests.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"requests": requests, "count": len(requests), "status": status}


@router.post("/access-requests/{request_id}/decision")
async def decide_access_request(request_id: str, body: AccessRequestDecision, request: Request):
    """Approve or deny pending access requests with audit + user notification."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_access_request_decision",
        target_user_id=request_id,
        payload={"action": body.action, "reason": body.reason or ""},
    )
    action = str(body.action or "").strip().lower()
    if action not in {"approve", "deny"}:
        raise HTTPException(400, "action must be 'approve' or 'deny'")

    req_doc = await db.employee_access_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not req_doc:
        raise HTTPException(404, "Access request not found")
    if req_doc.get("status") != "pending":
        raise HTTPException(409, f"Request already {req_doc.get('status')}")

    target_user_id = str(req_doc.get("user_id") or "")
    target_email = str(req_doc.get("email") or "")
    requested_role = req_doc.get("requested_role")
    requested_features = list(req_doc.get("requested_features") or [])
    requested_permissions = _filter_permissions(req_doc.get("requested_permissions") or [])
    now = datetime.now(timezone.utc).isoformat()

    if action == "approve":
        target_user = await db.users.find_one(
            {"user_id": target_user_id},
            {"_id": 0, "user_id": 1, "platform_role": 1, "feature_access": 1, "employee_permissions": 1},
        )
        if target_user is None:
            raise HTTPException(404, "Target user not found")
        role_to_set = requested_role or target_user.get("platform_role") or "Custom"
        if role_to_set not in PLATFORM_ROLES:
            role_to_set = "Custom"

        current_features = set(target_user.get("feature_access") or [])
        approved_features = set(requested_features or DEFAULT_ROLE_FEATURES.get(role_to_set, []))
        merged = sorted(list(current_features.union(approved_features)))
        current_permissions = set(_filter_permissions(target_user.get("employee_permissions") or []))
        approved_permissions = set(requested_permissions or _default_permissions_for_role(role_to_set))
        merged_permissions = sorted(list(current_permissions.union(approved_permissions)))
        await db.users.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "platform_role": role_to_set,
                    "feature_access": merged,
                    "employee_permissions": merged_permissions,
                    "updated_at": now,
                }
            },
        )
        await _log_audit(
            admin.user_id,
            admin.email,
            "access_request_approved",
            target_user_id,
            target_email,
            {
                "request_id": request_id,
                "approved_role": role_to_set,
                "approved_features": merged,
                "approved_permissions": merged_permissions,
                "reason": body.reason or "",
            },
        )
        new_status = "approved"
        notif_msg = "Your employee access request was approved."
    else:
        await _log_audit(
            admin.user_id,
            admin.email,
            "access_request_denied",
            target_user_id,
            target_email,
            {
                "request_id": request_id,
                "requested_role": requested_role,
                "requested_features": requested_features,
                "requested_permissions": requested_permissions,
                "reason": body.reason or "",
            },
        )
        new_status = "denied"
        notif_msg = "Your employee access request was denied."

    await db.employee_access_requests.update_one(
        {"request_id": request_id},
        {
            "$set": {
                "status": new_status,
                "decision_reason": body.reason or "",
                "decided_by": admin.email,
                "decided_by_user_id": admin.user_id,
                "decided_at": now,
                "updated_at": now,
            }
        },
    )

    await db.notifications.insert_one({
        "id": f"employee_access_{request_id}_{new_status}",
        "user_id": target_user_id,
        "type": "employee_access_request",
        "title": f"Access Request {new_status.title()}",
        "message": notif_msg,
        "read": False,
        "created_at": now,
        "metadata": {"request_id": request_id, "status": new_status, "reason": body.reason or ""},
    })

    return {"success": True, "request_id": request_id, "status": new_status}


@router.patch("/{user_id}")
async def update_employee(user_id: str, body: UpdateEmployee, request: Request):
    """Update platform role, premium access, or feature access for an employee."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_update",
        target_user_id=user_id,
        payload={
            "platform_role": body.platform_role,
            "premium_access": body.premium_access,
            "feature_access_count": len(body.feature_access or []),
            "employee_permissions_count": len(body.employee_permissions or []),
        },
    )
    user = await db.users.find_one(
        {"user_id": user_id, "platform_role": {"$exists": True, "$ne": None}},
        {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1,
         "premium_access": 1, "feature_access": 1, "employee_permissions": 1},
    )
    if not user:
        raise HTTPException(404, "Employee not found")

    update: dict = {}
    changes: dict = {}
    if body.platform_role is not None:
        if body.platform_role not in PLATFORM_ROLES:
            raise HTTPException(400, f"Invalid role. Must be one of: {PLATFORM_ROLES}")
        if body.platform_role != user.get("platform_role"):
            changes["role"] = {"from": user.get("platform_role"), "to": body.platform_role}
        update["platform_role"] = body.platform_role
    if body.premium_access is not None:
        if body.premium_access != user.get("premium_access"):
            changes["premium_access"] = {"from": user.get("premium_access", False), "to": body.premium_access}
        update["premium_access"] = body.premium_access
    if body.feature_access is not None:
        old_feats = set(user.get("feature_access") or [])
        new_feats = set(body.feature_access)
        if old_feats != new_feats:
            changes["features_added"] = sorted(new_feats - old_feats)
            changes["features_removed"] = sorted(old_feats - new_feats)
        update["feature_access"] = body.feature_access
    if body.employee_permissions is not None:
        old_perms = set(_filter_permissions(user.get("employee_permissions") or []))
        new_perms = set(_filter_permissions(body.employee_permissions))
        if old_perms != new_perms:
            changes["permissions_added"] = sorted(new_perms - old_perms)
            changes["permissions_removed"] = sorted(old_perms - new_perms)
        update["employee_permissions"] = sorted(list(new_perms))

    if not update:
        raise HTTPException(400, "No fields to update")

    await db.users.update_one({"user_id": user_id}, {"$set": update})

    # Determine audit action
    if "premium_access" in changes:
        action = "premium_granted" if body.premium_access else "premium_revoked"
    elif "role" in changes:
        action = "role_changed"
    else:
        action = "access_updated"

    await _log_audit(
        admin.user_id, admin.email, action,
        user_id, user.get("email", ""),
        changes if changes else update,
    )

    logger.info(f"[EMPLOYEE] Updated {user_id}: {update}")
    return {"updated": True, "user_id": user_id, **update}


@router.delete("/{user_id}")
async def remove_employee(user_id: str, request: Request):
    """Remove platform employee status and revoke all granted access."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_remove",
        target_user_id=user_id,
        payload={},
    )
    user = await db.users.find_one(
        {"user_id": user_id, "platform_role": {"$exists": True, "$ne": None}},
        {"_id": 0, "user_id": 1, "email": 1, "is_admin": 1,
         "platform_role": 1, "premium_access": 1},
    )
    if not user:
        raise HTTPException(404, "Employee not found")
    if user.get("is_admin"):
        raise HTTPException(403, "Cannot remove admin employee status")

    await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {
            "platform_role": "",
            "premium_access": "",
            "feature_access": "",
            "employee_permissions": "",
            "employee_since": "",
        }},
    )

    await _log_audit(
        admin.user_id, admin.email, "employee_removed",
        user_id, user.get("email", ""),
        {"role": user.get("platform_role"), "had_premium": user.get("premium_access", False)},
    )

    logger.info(f"[EMPLOYEE] Removed {user.get('email')} from platform employees")
    return {"removed": True, "user_id": user_id}


# ─────────────────────────────────────────────────────────────
# Bulk operations (multi-select from Team Management UI)
# ─────────────────────────────────────────────────────────────

class BulkUpdateRoleBody(BaseModel):
    user_ids: list[str] = Field(..., max_length=200)
    platform_role: str

class BulkPremiumBody(BaseModel):
    user_ids: list[str] = Field(..., max_length=200)
    premium_access: bool

class BulkRemoveBody(BaseModel):
    user_ids: list[str] = Field(..., max_length=200)


@router.post("/bulk-update-role")
async def bulk_update_role(body: BulkUpdateRoleBody, request: Request):
    """Bulk-update platform_role for a selection of employees."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_bulk_update_role",
        target_user_id="bulk",
        payload={"count": len(body.user_ids or []), "platform_role": body.platform_role},
    )
    if body.platform_role not in PLATFORM_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {PLATFORM_ROLES}")
    if not body.user_ids:
        raise HTTPException(400, "No user_ids provided")

    updated, skipped = [], []
    for uid in body.user_ids:
        u = await db.users.find_one(
            {"user_id": uid, "platform_role": {"$exists": True, "$ne": None}},
            {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1, "is_admin": 1},
        )
        if not u:
            skipped.append({"user_id": uid, "reason": "not_found"})
            continue
        if u.get("platform_role") == body.platform_role:
            skipped.append({"user_id": uid, "reason": "unchanged"})
            continue
        await db.users.update_one({"user_id": uid}, {"$set": {"platform_role": body.platform_role}})
        await _log_audit(
            admin.user_id, admin.email, "role_changed",
            uid, u.get("email", ""),
            {"role": {"from": u.get("platform_role"), "to": body.platform_role}, "bulk": True},
        )
        updated.append(uid)

    logger.info(f"[EMPLOYEE BULK] role→{body.platform_role}: updated={len(updated)} skipped={len(skipped)} by {admin.email}")
    return {"updated_count": len(updated), "skipped_count": len(skipped), "updated": updated, "skipped": skipped}


@router.post("/bulk-update-premium")
async def bulk_update_premium(body: BulkPremiumBody, request: Request):
    """Bulk grant or revoke premium_access for a selection of employees."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_bulk_update_premium",
        target_user_id="bulk",
        payload={"count": len(body.user_ids or []), "premium_access": bool(body.premium_access)},
    )
    if not body.user_ids:
        raise HTTPException(400, "No user_ids provided")
    action = "premium_granted" if body.premium_access else "premium_revoked"

    updated, skipped = [], []
    for uid in body.user_ids:
        u = await db.users.find_one(
            {"user_id": uid, "platform_role": {"$exists": True, "$ne": None}},
            {"_id": 0, "user_id": 1, "email": 1, "premium_access": 1},
        )
        if not u:
            skipped.append({"user_id": uid, "reason": "not_found"})
            continue
        if bool(u.get("premium_access")) == bool(body.premium_access):
            skipped.append({"user_id": uid, "reason": "unchanged"})
            continue
        await db.users.update_one({"user_id": uid}, {"$set": {"premium_access": body.premium_access}})
        await _log_audit(
            admin.user_id, admin.email, action,
            uid, u.get("email", ""),
            {"premium_access": {"from": u.get("premium_access", False), "to": body.premium_access}, "bulk": True},
        )
        updated.append(uid)

    logger.info(f"[EMPLOYEE BULK] premium={body.premium_access}: updated={len(updated)} skipped={len(skipped)} by {admin.email}")
    return {"updated_count": len(updated), "skipped_count": len(skipped), "updated": updated, "skipped": skipped}


@router.post("/bulk-remove")
async def bulk_remove_employees(body: BulkRemoveBody, request: Request):
    """Bulk-remove platform employee status. Owner admins are always skipped."""
    admin = await _require_high_risk_admin_change(
        request,
        action="team_employee_bulk_remove",
        target_user_id="bulk",
        payload={"count": len(body.user_ids or [])},
    )
    if not body.user_ids:
        raise HTTPException(400, "No user_ids provided")

    removed, skipped = [], []
    for uid in body.user_ids:
        u = await db.users.find_one(
            {"user_id": uid, "platform_role": {"$exists": True, "$ne": None}},
            {"_id": 0, "user_id": 1, "email": 1, "is_admin": 1, "platform_role": 1, "premium_access": 1},
        )
        if not u:
            skipped.append({"user_id": uid, "reason": "not_found"})
            continue
        if u.get("is_admin"):
            skipped.append({"user_id": uid, "reason": "is_admin"})
            continue
        await db.users.update_one(
            {"user_id": uid},
            {"$unset": {
                "platform_role": "", "premium_access": "", "feature_access": "",
                "employee_permissions": "", "employee_since": "",
            }},
        )
        await _log_audit(
            admin.user_id, admin.email, "employee_removed",
            uid, u.get("email", ""),
            {"role": u.get("platform_role"), "had_premium": u.get("premium_access", False), "bulk": True},
        )
        removed.append(uid)

    logger.info(f"[EMPLOYEE BULK] remove: removed={len(removed)} skipped={len(skipped)} by {admin.email}")
    return {"removed_count": len(removed), "skipped_count": len(skipped), "removed": removed, "skipped": skipped}


def _recommend_role(signal_features: list[str]) -> tuple[str, float, str]:
    """Rule-based role recommendation from feature usage signals."""
    role_weights: dict[str, int] = {role: 0 for role in PLATFORM_ROLES}
    feature_set = set(signal_features)

    role_feature_hints = {
        "Manager": {"dashboard", "analytics", "team_management", "reports"},
        "Support Team": {"support_tickets", "conversations"},
        "Developer": {"api_access", "integrations", "system_logs"},
        "Finance Advisor": {"revenue", "subscriptions", "invoices"},
        "Engineer": {"infrastructure", "integrations", "api_access", "system_logs"},
        "Designer": {"branding", "documents"},
        "QA": {"testing", "system_logs"},
        "Marketing": {"campaigns", "analytics", "reports"},
        "Operations": {"infrastructure", "team_management", "system_logs"},
        "Custom": set(),
    }

    for role, hints in role_feature_hints.items():
        overlap = len(feature_set.intersection(hints))
        role_weights[role] += overlap * 3

    if "executive_dashboard" in feature_set:
        role_weights["Manager"] += 4
    if "automation" in feature_set:
        role_weights["Operations"] += 3
    if "ai_features" in feature_set:
        role_weights["Developer"] += 2
        role_weights["Engineer"] += 2

    ranked = sorted(role_weights.items(), key=lambda x: x[1], reverse=True)
    best_role, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    confidence = round(min(0.98, 0.5 + max(0, best_score - second_score) / 12), 2)
    reason = (
        f"Top signals matched {best_role} access profile "
        f"({best_score} weighted points from {len(feature_set)} observed features)."
    )
    return best_role, confidence, reason


def _compute_risk_score(stats: dict) -> tuple[int, list[str]]:
    """Compute employee risk score and reasons."""
    score = 0
    reasons = []
    denied = int(stats.get("denied_access", 0))
    off_hours = int(stats.get("off_hours", 0))
    sensitive = int(stats.get("sensitive_events", 0))
    ip_changes = max(0, len(stats.get("ips", set())) - 1)
    total_events = int(stats.get("events", 0))

    if denied >= 3:
        score += min(40, denied * 8)
        reasons.append(f"{denied} denied-access events")
    if off_hours >= 5:
        score += min(25, off_hours * 2)
        reasons.append(f"{off_hours} off-hours actions")
    if sensitive >= 4:
        score += min(20, sensitive * 3)
        reasons.append(f"{sensitive} sensitive permission changes")
    if ip_changes >= 3:
        score += min(15, ip_changes * 3)
        reasons.append(f"{ip_changes + 1} distinct IP addresses")
    if total_events >= 120:
        score += 10
        reasons.append("Very high activity volume")

    return min(100, score), reasons


def _risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


async def _build_employee_ai_insights(window_hours: int = 24, limit: int = 3000) -> dict:
    """Generate AI-style operational insights for Platform Employees."""
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=window_hours)).isoformat()

    employees = await db.users.find(
        {"platform_role": {"$exists": True, "$ne": None}},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "platform_role": 1,
            "feature_access": 1,
            "premium_access": 1,
            "last_active": 1,
        },
    ).to_list(limit)
    employee_map = {e["user_id"]: e for e in employees if e.get("user_id")}

    activity_events = await db.employee_activity_events.find(
        {"created_at": {"$gte": since_iso}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)

    audit_events = await db.employee_audit_log.find(
        {"timestamp": {"$gte": since_iso}},
        {"_id": 0, "target_user_id": 1, "action": 1, "timestamp": 1},
    ).to_list(limit)

    per_user = defaultdict(lambda: {
        "events": 0,
        "features": Counter(),
        "event_types": Counter(),
        "denied_access": 0,
        "off_hours": 0,
        "sensitive_events": 0,
        "ips": set(),
    })

    for evt in activity_events:
        user_id = str(evt.get("user_id") or "")
        if not user_id:
            continue
        stat = per_user[user_id]
        stat["events"] += 1
        feature = str(evt.get("feature") or "").strip()
        if feature:
            stat["features"][feature] += 1
        event_type = str(evt.get("event_type") or "unknown").strip().lower()
        stat["event_types"][event_type] += 1
        if event_type in {"denied_access", "permission_denied"}:
            stat["denied_access"] += 1
        if event_type in {"role_change", "premium_change", "access_update", "policy_override"}:
            stat["sensitive_events"] += 1
        ip_address = str(evt.get("ip_address") or "").strip()
        if ip_address:
            stat["ips"].add(ip_address)
        hour = int(evt.get("hour_utc") or 0)
        if hour < 6 or hour >= 22:
            stat["off_hours"] += 1

    for audit_evt in audit_events:
        target_user_id = str(audit_evt.get("target_user_id") or "")
        if not target_user_id:
            continue
        per_user[target_user_id]["sensitive_events"] += 1
        per_user[target_user_id]["event_types"][str(audit_evt.get("action") or "audit_action")] += 1

    smart_access_recommendations = []
    predictive_role_assignment = []
    risk_scores = []
    anomalies = []

    for emp in employees:
        user_id = str(emp.get("user_id") or "")
        if not user_id:
            continue
        stats = per_user[user_id]
        observed_feature_signals = [
            *list((emp.get("feature_access") or [])),
            *[f for f, _ in stats["features"].most_common(10)],
        ]
        rec_role, confidence, reason = _recommend_role(observed_feature_signals)
        current_role = str(emp.get("platform_role") or "Custom")
        rec_features = DEFAULT_ROLE_FEATURES.get(rec_role, [])
        if rec_role != current_role:
            smart_access_recommendations.append({
                "user_id": user_id,
                "email": str(emp.get("email") or ""),
                "current_role": current_role,
                "recommended_role": rec_role,
                "confidence": confidence,
                "reason": reason,
                "recommended_features": rec_features,
            })

        predictive_role_assignment.append({
            "user_id": user_id,
            "email": str(emp.get("email") or ""),
            "predicted_role": rec_role,
            "confidence": confidence,
        })

        risk_score, reasons = _compute_risk_score(stats)
        level = _risk_level(risk_score)
        risk_scores.append({
            "user_id": user_id,
            "email": str(emp.get("email") or ""),
            "role": current_role,
            "risk_score": risk_score,
            "risk_level": level,
            "reasons": reasons,
            "events": stats["events"],
            "denied_access": stats["denied_access"],
        })
        if level in {"medium", "high"}:
            anomalies.append({
                "user_id": user_id,
                "email": str(emp.get("email") or ""),
                "risk_level": level,
                "risk_score": risk_score,
                "signals": reasons,
            })

    smart_access_recommendations.sort(key=lambda x: x["confidence"], reverse=True)
    predictive_role_assignment.sort(key=lambda x: x["confidence"], reverse=True)
    risk_scores.sort(key=lambda x: x["risk_score"], reverse=True)
    anomalies.sort(key=lambda x: x["risk_score"], reverse=True)

    pending_approvals = await db.employee_access_requests.find(
        {"status": "pending"},
        {"_id": 0, "request_id": 1, "user_id": 1, "requested_role": 1, "requested_features": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(50)

    approval_suggestions = []
    for req in pending_approvals:
        req_user_id = str(req.get("user_id") or "")
        emp = employee_map.get(req_user_id)
        current_role = str((emp or {}).get("platform_role") or "Custom")
        baseline = set(DEFAULT_ROLE_FEATURES.get(current_role, []))
        requested = set(req.get("requested_features") or [])
        suggested_action = "approve" if requested.issubset(baseline) else "review"
        confidence = 0.86 if suggested_action == "approve" else 0.54
        approval_suggestions.append({
            "request_id": str(req.get("request_id") or ""),
            "user_id": req_user_id,
            "requested_role": str(req.get("requested_role") or current_role),
            "requested_features": sorted(list(requested)),
            "suggested_action": suggested_action,
            "confidence": confidence,
            "reason": (
                "Requested features align with role baseline."
                if suggested_action == "approve"
                else "Requested features exceed baseline; admin review recommended."
            ),
        })

    realtime_activity = activity_events[:30]
    security_alerts = [
        {
            "alert_type": "employee_risk",
            "severity": r["risk_level"],
            "user_id": r["user_id"],
            "email": r["email"],
            "risk_score": r["risk_score"],
            "message": ", ".join(r["reasons"]) if r["reasons"] else "Risk signal detected",
        }
        for r in risk_scores
        if r["risk_level"] in {"medium", "high"}
    ][:10]

    high_risk_count = sum(1 for r in risk_scores if r["risk_level"] == "high")
    medium_risk_count = sum(1 for r in risk_scores if r["risk_level"] == "medium")

    audit_summary_text = (
        f"Analyzed {len(activity_events)} activity events across {len(employees)} employees in the last {window_hours}h. "
        f"Detected {len(anomalies)} anomaly candidates ({high_risk_count} high-risk, {medium_risk_count} medium-risk). "
        f"Generated {len(smart_access_recommendations)} access recommendations and {len(approval_suggestions)} approval suggestions."
    )

    insights = {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "employees_analyzed": len(employees),
        "smart_access_recommendations": smart_access_recommendations[:25],
        "predictive_role_assignment": predictive_role_assignment[:25],
        "anomalies": anomalies[:25],
        "auto_audit_summary": {
            "summary": audit_summary_text,
            "total_events": len(activity_events),
            "total_anomalies": len(anomalies),
            "high_risk": high_risk_count,
            "medium_risk": medium_risk_count,
        },
        "approval_suggestions": approval_suggestions[:25],
        "realtime_activity": realtime_activity,
        "risk_scores": risk_scores[:50],
        "security_alerts": security_alerts,
    }

    await db.employee_ai_insight_snapshots.insert_one({
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "employees_analyzed": len(employees),
        "high_risk": high_risk_count,
        "medium_risk": medium_risk_count,
        "total_anomalies": len(anomalies),
        "summary": audit_summary_text,
    })

    return insights


@router.post("/activity-event")
async def track_employee_activity_event(body: ActivityEventRequest, request: Request):
    """Track employee activity events for real-time monitoring and AI anomaly analytics."""
    user = await require_auth(request)
    event_type = str(body.event_type or "").strip().lower()
    if not event_type:
        raise HTTPException(400, "event_type is required")

    now = datetime.now(timezone.utc)
    event_doc = {
        "event_id": f"eae_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "email": user.email,
        "event_type": event_type,
        "feature": str(body.feature or "").strip(),
        "metadata": body.metadata or {},
        "source": str(body.source or "web"),
        "ip_address": request.client.host if request.client else "",
        "hour_utc": now.hour,
        "created_at": now.isoformat(),
    }
    await db.employee_activity_events.insert_one(event_doc)
    return {"logged": True, "event_id": event_doc["event_id"]}


@router.get("/activity-stream")
async def get_employee_activity_stream(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    user_id: str = "",
):
    """Real-time employee activity feed for admin monitoring."""
    await _require_platform_access(request, "employee.view_analytics")
    query = {"user_id": user_id} if user_id else {}
    events = await db.employee_activity_events.find(
        query,
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"events": events, "count": len(events)}


@router.get("/ai-insights")
async def get_employee_ai_insights(request: Request, hours: int = Query(24, ge=1, le=168)):
    """AI-powered insight center for employee risk, role prediction, and approval guidance."""
    await _require_platform_access(request, "employee.view_analytics")
    return await _build_employee_ai_insights(window_hours=hours)


@router.post("/ai-command")
async def run_employee_ai_command(body: AICommandRequest, request: Request):
    """Natural-language admin commands for employee operations (safe-by-default)."""
    admin = await _require_platform_access(request, "employee.manage_operations")
    command = str(body.command or "").strip()
    if not command:
        raise HTTPException(400, "command is required")
    normalized = command.lower()

    grant_match = re.search(r"(?:grant|give)\s+premium\s+(?:to\s+)?([\w.+-]+@[\w.-]+)", normalized)
    revoke_match = re.search(r"(?:revoke|remove)\s+premium\s+(?:from\s+)?([\w.+-]+@[\w.-]+)", normalized)
    role_match = re.search(r"recommend\s+role\s+(?:for\s+)?([\w.+-]+@[\w.-]+)", normalized)

    if "high risk" in normalized:
        insights = await _build_employee_ai_insights(window_hours=24)
        high_risk = [r for r in insights.get("risk_scores", []) if r.get("risk_level") == "high"]
        return {
            "understood_intent": "list_high_risk_employees",
            "execute": False,
            "performed": True,
            "result": high_risk[:10],
            "message": f"Found {len(high_risk)} high-risk employee(s).",
        }

    if "pending approvals" in normalized or "pending approval" in normalized:
        insights = await _build_employee_ai_insights(window_hours=24)
        suggestions = insights.get("approval_suggestions", [])
        return {
            "understood_intent": "list_pending_approvals",
            "execute": False,
            "performed": True,
            "result": suggestions[:10],
            "message": f"Found {len(suggestions)} pending approval suggestion(s).",
        }

    if role_match:
        email = role_match.group(1)
        emp = await db.users.find_one(
            {"email": email},
            {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1, "feature_access": 1},
        )
        if not emp:
            raise HTTPException(404, f"No user found with email: {email}")
        signals = list(emp.get("feature_access") or [])
        rec_role, confidence, reason = _recommend_role(signals)
        return {
            "understood_intent": "recommend_role",
            "execute": False,
            "performed": True,
            "result": {
                "email": email,
                "current_role": emp.get("platform_role") or "Custom",
                "recommended_role": rec_role,
                "confidence": confidence,
                "reason": reason,
            },
        }

    if grant_match or revoke_match:
        target_email = (grant_match or revoke_match).group(1)
        target = await db.users.find_one(
            {"email": target_email},
            {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1, "premium_access": 1},
        )
        if not target:
            raise HTTPException(404, f"No user found with email: {target_email}")
        action = "grant_premium" if grant_match else "revoke_premium"
        desired = action == "grant_premium"
        if not target.get("platform_role"):
            return {
                "understood_intent": action,
                "execute": body.execute,
                "performed": False,
                "message": "Target user is not a platform employee. Add employee role first.",
                "next_steps": ["Use Add Employee flow", "Then rerun premium command"],
            }
        if not body.execute:
            return {
                "understood_intent": action,
                "execute": False,
                "performed": False,
                "message": f"Dry run: ready to set premium_access={desired} for {target_email}.",
                "next_steps": ["Resend command with execute=true to apply change"],
            }

        await db.users.update_one({"user_id": target["user_id"]}, {"$set": {"premium_access": desired}})
        await _log_audit(
            admin.user_id,
            admin.email,
            "premium_granted" if desired else "premium_revoked",
            target["user_id"],
            target["email"],
            {"premium_access": {"from": bool(target.get("premium_access")), "to": desired}, "source": "ai_command"},
        )
        return {
            "understood_intent": action,
            "execute": True,
            "performed": True,
            "message": f"Updated premium access for {target_email}.",
        }

    return {
        "understood_intent": "unknown",
        "execute": False,
        "performed": False,
        "message": "Command not recognized. Try: 'show high risk employees', 'list pending approvals', 'recommend role for <email>', or 'grant premium to <email>'.",
    }


@router.post("/anomaly-alerts/dispatch")
async def dispatch_employee_anomaly_alerts(
    request: Request,
    min_risk_score: int = Query(70, ge=40, le=100),
):
    """Route high-risk employee anomalies to in-app notifications and email."""
    admin = await _require_platform_access(request, "employee.manage_operations")
    insights = await _build_employee_ai_insights(window_hours=24)
    alerts = [a for a in (insights.get("security_alerts") or []) if int(a.get("risk_score") or 0) >= min_risk_score]
    now = datetime.now(timezone.utc).isoformat()

    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(100)

    in_app_sent = 0
    for adm in admins:
        uid = str(adm.get("user_id") or "")
        if not uid:
            continue
        await db.notifications.insert_one({
            "id": f"employee_alert_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
            "user_id": uid,
            "type": "employee_security_alert",
            "title": "Employee Security Alert",
            "message": f"{len(alerts)} high-risk employee alerts need review.",
            "read": False,
            "created_at": now,
            "metadata": {"alerts": alerts[:10], "min_risk_score": min_risk_score},
        })
        in_app_sent += 1

    email_sent = 0
    if alerts and is_email_configured():
        company = await db.platform_company_profile.find_one({}, {"_id": 0, "name": 1}) or {}
        risk_summary = [
            {
                "email": a.get("email"),
                "risk_score": a.get("risk_score"),
                "severity": a.get("severity"),
            }
            for a in alerts[:5]
        ]
        rows = "".join(
            f"<li><strong>{a.get('email')}</strong> — risk {a.get('risk_score')} ({a.get('severity')})"
            f"<br/><span style='color:#64748B'>{a.get('message')}</span></li>"
            for a in alerts[:10]
        )
        f"""
        <div style='font-family:Arial,sans-serif;line-height:1.6;color:#0F172A;'>
          <h2 style='margin:0 0 12px;'>High-Risk Employee Alerts</h2>
          <p>Detected <strong>{len(alerts)}</strong> high-risk employee alert(s) in the last 24h.</p>
          <ul>{rows}</ul>
          <p style='margin-top:12px;color:#475569;'>Review in Team Management → Employee AI Security Center.</p>
        </div>
        """
        for adm in admins:
            email = str(adm.get("email") or "").strip()
            if not email:
                continue
            from utils.email_service import send_catalog_template
            result = await send_catalog_template(
                recipient_email=email,
                template_key="employee_risk_alert",
                admin_name=admin.get("name", "HR Admin"),
                alert_count=len(alerts),
                company_name=company.get("name", "Your Organization"),
                top_risks=risk_summary,
            )
            if result.get("success"):
                email_sent += 1

    await _log_audit(
        admin.user_id,
        admin.email,
        "anomaly_alert_dispatched",
        "system",
        "admins",
        {
            "alerts_count": len(alerts),
            "min_risk_score": min_risk_score,
            "in_app_sent": in_app_sent,
            "email_sent": email_sent,
        },
    )

    return {
        "success": True,
        "alerts_count": len(alerts),
        "min_risk_score": min_risk_score,
        "in_app_notifications_sent": in_app_sent,
        "email_notifications_sent": email_sent,
    }


def _count_roles(employees: list) -> dict:
    counts: dict = {}
    for e in employees:
        role = e.get("platform_role", "Unknown")
        counts[role] = counts.get(role, 0) + 1
    return counts


async def run_invitation_cleanup_scheduled(
    trigger: str = "nightly_cron", purge_days: int = 30
) -> dict:
    """Non-HTTP entrypoint for APScheduler.

    1. Marks all `pending` invitations whose `expires_at` is in the past as `status:expired`.
    2. Deletes any `revoked` or `expired` invitation rows older than `purge_days` days.

    Returns a compact summary — never raises.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    now = datetime.now(timezone.utc)

    try:
        now_iso = now.isoformat()
        expired_res = await db.platform_employee_invitations.update_many(
            {"status": "pending", "expires_at": {"$lt": now_iso}},
            {"$set": {"status": "expired"}},
        )

        purge_cutoff = (now - timedelta(days=purge_days)).isoformat()
        delete_res = await db.platform_employee_invitations.delete_many({
            "status": {"$in": ["revoked", "expired"]},
            "$or": [
                {"expires_at": {"$lt": purge_cutoff}},
                {"revoked_at": {"$lt": purge_cutoff}},
            ],
        })

        summary = {
            "ok": True,
            "trigger": trigger,
            "marked_expired": int(expired_res.modified_count or 0),
            "purged": int(delete_res.deleted_count or 0),
            "purge_days": purge_days,
            "ran_at": now_iso,
        }
        _log.info(
            f"[invitation-cleanup] {trigger}: marked_expired={summary['marked_expired']} "
            f"purged={summary['purged']} (cutoff={purge_days}d)"
        )
        return summary
    except Exception as exc:
        _log.error(f"[invitation-cleanup] failed: {exc}")
        return {"ok": False, "error": str(exc), "trigger": trigger}


def _build_invitation_url(token: str) -> str:
    """Build the frontend invitation-accept URL. Falls back to a path if no base configured."""
    import os as _os
    base = (
        _os.environ.get("FRONTEND_URL")
        or _os.environ.get("PUBLIC_APP_URL")
        or _os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    return f"{base}/invite-accept?token={token}" if base else f"/invite-accept?token={token}"


def _hash_invitation_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode()).hexdigest()


def _invitation_token_query(raw_token: str) -> dict:
    token = str(raw_token or "")
    token_hash = _hash_invitation_token(token)
    # Backward compatibility for legacy invitations that still store plaintext token.
    return {"$or": [{"token_hash": token_hash}, {"token": token}]}


class InvitationAccept(BaseModel):
    token: str
    password: str
    name: Optional[str] = None


@router.get("/invitations")
async def list_pending_invitations(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    q: Optional[str] = Query(None, description="Substring match on email or inviter email"),
    platform_role: Optional[str] = Query(None, description="Exact role filter"),
    window: Optional[str] = Query(None, description="Time window: 24h, 72h, 7d, 30d"),
):
    """Admin: list pending platform-employee invitations (newest first) with optional filters."""
    await require_admin(request)

    query: dict = {"status": "pending"}
    if platform_role:
        query["platform_role"] = platform_role
    if q:
        safe = re.escape(q.strip())
        if safe:
            query["$or"] = [
                {"email": {"$regex": safe, "$options": "i"}},
                {"invited_by_email": {"$regex": safe, "$options": "i"}},
            ]
    if window:
        window_map = {"24h": 24, "72h": 72, "7d": 24 * 7, "30d": 24 * 30}
        hours = window_map.get(window)
        if hours:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            query["created_at"] = {"$gte": since}

    cursor = db.platform_employee_invitations.find(
        query,
        {
            "_id": 0,
            "invitation_id": 1,
            "email": 1,
            "platform_role": 1,
            "premium_access": 1,
            "invited_by_email": 1,
            "created_at": 1,
            "expires_at": 1,
            "status": 1,
            "last_email_id": 1,
            "last_email_sent_at": 1,
        },
    ).sort("created_at", -1).limit(limit)
    invites = await cursor.to_list(length=limit)
    # Mark expired ones on-the-fly (cheap cleanup)
    now = datetime.now(timezone.utc)
    live: list[dict] = []
    expired_ids: list[str] = []
    for inv in invites:
        try:
            exp = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                expired_ids.append(inv["invitation_id"])
                continue
        except Exception:
            pass
        live.append(inv)
    if expired_ids:
        await db.platform_employee_invitations.update_many(
            {"invitation_id": {"$in": expired_ids}},
            {"$set": {"status": "expired"}},
        )

    # Enrich with latest delivery event (Resend webhook status) per invitation
    email_ids = [inv.get("last_email_id") for inv in live if inv.get("last_email_id")]
    latest_by_email_id: dict = {}
    if email_ids:
        ev_cursor = db.email_delivery_events.find(
            {"email_id": {"$in": email_ids}},
            {"_id": 0, "email_id": 1, "internal_status": 1, "event_type": 1, "created_at": 1},
        ).sort("processed_at", -1)
        async for ev in ev_cursor:
            eid = ev["email_id"]
            # Newest-first; prefer terminal status over interim
            TERMINAL = {"bounced", "complained", "delivered", "opened", "clicked", "delayed"}
            existing = latest_by_email_id.get(eid)
            if not existing:
                latest_by_email_id[eid] = ev
            elif existing.get("internal_status") not in TERMINAL and ev.get("internal_status") in TERMINAL:
                latest_by_email_id[eid] = ev
    for inv in live:
        eid = inv.get("last_email_id")
        if eid and eid in latest_by_email_id:
            ev = latest_by_email_id[eid]
            inv["delivery_status"] = ev.get("internal_status")
            inv["delivery_event_at"] = ev.get("created_at")
        else:
            inv["delivery_status"] = "sent" if eid else None
            inv["delivery_event_at"] = inv.get("last_email_sent_at")

    return {
        "invitations": live,
        "total": len(live),
        "filters": {"q": q, "platform_role": platform_role, "window": window},
    }


@router.get("/invitations/{invitation_id}/link")
async def get_invitation_link(invitation_id: str, request: Request):
    """Admin: fetch the shareable invite URL for a pending invitation (emits audit entry)."""
    admin = await require_admin(request)
    inv = await db.platform_employee_invitations.find_one(
        {"invitation_id": invitation_id},
        {"_id": 0, "email": 1, "status": 1, "platform_role": 1, "expires_at": 1},
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation is {inv.get('status')}")

    regenerated_token = secrets.token_urlsafe(32)
    regenerated_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    await db.platform_employee_invitations.update_one(
        {"invitation_id": invitation_id},
        {
            "$set": {
                "token_hash": _hash_invitation_token(regenerated_token),
                "token_last4": regenerated_token[-4:],
                "expires_at": regenerated_expires_at.isoformat(),
            },
            "$unset": {"token": ""},
        },
    )
    invite_url = _build_invitation_url(regenerated_token)
    await _log_audit(
        admin.user_id, admin.email, "invitation_link_copied",
        None, inv["email"],
        {"invitation_id": invitation_id, "platform_role": inv["platform_role"]},
    )
    return {
        "invitation_id": invitation_id,
        "email": inv["email"],
        "invite_url": invite_url,
        "expires_at": regenerated_expires_at.isoformat(),
    }


@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(invitation_id: str, request: Request):
    """Admin: re-send the Resend email for a pending invitation and refresh the 72h expiry."""
    admin = await require_admin(request)
    inv = await db.platform_employee_invitations.find_one(
        {"invitation_id": invitation_id}, {"_id": 0}
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation is {inv.get('status')}, cannot resend")

    regenerated_token = secrets.token_urlsafe(32)
    new_expires = datetime.now(timezone.utc) + timedelta(hours=72)
    await db.platform_employee_invitations.update_one(
        {"invitation_id": invitation_id},
        {
            "$set": {
                "expires_at": new_expires.isoformat(),
                "token_hash": _hash_invitation_token(regenerated_token),
                "token_last4": regenerated_token[-4:],
            },
            "$unset": {"token": ""},
        },
    )

    invite_url = _build_invitation_url(regenerated_token)
    email_sent = False
    email_message_id: Optional[str] = None
    try:
        from utils.email_notifications import send_platform_employee_invitation
        res = await send_platform_employee_invitation(
            recipient_email=inv["email"],
            platform_role=inv["platform_role"],
            invited_by_email=admin.email,
            invite_url=invite_url,
            expires_in_hours=72,
        )
        email_sent = bool(res and res.get("success"))
        email_message_id = (res or {}).get("message_id")
    except Exception as exc:
        logger.warning(f"[EMPLOYEE-INVITE] resend email failed for {inv['email']}: {exc}")

    if email_message_id:
        await db.platform_employee_invitations.update_one(
            {"invitation_id": invitation_id},
            {"$set": {
                "last_email_id": email_message_id,
                "last_email_sent_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

    await _log_audit(
        admin.user_id, admin.email, "invitation_resent",
        None, inv["email"],
        {"invitation_id": invitation_id, "platform_role": inv["platform_role"], "email_sent": email_sent},
    )
    return {
        "resent": True,
        "invitation_id": invitation_id,
        "email": inv["email"],
        "email_sent": email_sent,
        "expires_at": new_expires.isoformat(),
    }


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(invitation_id: str, request: Request):
    """Admin: revoke a pending invitation (invalidates the token)."""
    admin = await require_admin(request)
    inv = await db.platform_employee_invitations.find_one(
        {"invitation_id": invitation_id}, {"_id": 0, "email": 1, "status": 1, "platform_role": 1}
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation is {inv.get('status')}, cannot revoke")

    await db.platform_employee_invitations.update_one(
        {"invitation_id": invitation_id},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat(), "revoked_by_email": admin.email}},
    )
    await _log_audit(
        admin.user_id, admin.email, "invitation_revoked",
        None, inv["email"],
        {"invitation_id": invitation_id, "platform_role": inv["platform_role"]},
    )
    return {"revoked": True, "invitation_id": invitation_id, "email": inv["email"]}


@router.get("/invitations/verify")
async def verify_employee_invitation(token: str = Query(..., min_length=10)):
    """Public endpoint: verify an invitation token. Returns invitation meta or {valid: False}."""
    inv = await db.platform_employee_invitations.find_one(
        _invitation_token_query(token),
        {
            "_id": 0,
            "invitation_id": 1,
            "email": 1,
            "platform_role": 1,
            "premium_access": 1,
            "invited_by_email": 1,
            "status": 1,
            "expires_at": 1,
            "created_at": 1,
        },
    )
    if not inv:
        return {"valid": False, "reason": "invalid_token"}

    if inv.get("status") != "pending":
        return {"valid": False, "reason": "already_used", "status": inv.get("status")}

    try:
        expires_at = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            await db.platform_employee_invitations.update_one(
                {"invitation_id": inv["invitation_id"]},
                {"$set": {"status": "expired"}},
            )
            return {"valid": False, "reason": "expired"}
    except Exception:
        pass

    return {
        "valid": True,
        "email": inv["email"],
        "platform_role": inv["platform_role"],
        "premium_access": inv.get("premium_access", False),
        # Branded sender identity shown to candidates (matches the email template).
        # Single source of truth via env — rebranding is a one-line .env change.
        "invited_by_email": os.environ.get("PLATFORM_INVITE_BRAND_SENDER", "careers@realaicoach.app"),
        "expires_at": inv.get("expires_at"),
    }


@router.post("/invitations/accept")
async def accept_employee_invitation(body: InvitationAccept, request: Request):
    """Public endpoint: accept a platform-employee invitation. Creates the user if missing,
    promotes them to the invited platform_role, issues a session token (auto-login).
    """
    from routes.db import hash_password, create_jwt_token, User, UserSession
    from routes.auth import validate_password_strength

    inv = await db.platform_employee_invitations.find_one(_invitation_token_query(body.token), {"_id": 0})
    if not inv or inv.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invalid or already-used invitation")

    try:
        expires_at = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            await db.platform_employee_invitations.update_one(
                {"invitation_id": inv["invitation_id"]},
                {"$set": {"status": "expired"}},
            )
            raise HTTPException(status_code=400, detail="This invitation has expired")
    except HTTPException:
        raise
    except Exception:
        pass

    pw_err = validate_password_strength(body.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    email = inv["email"]
    role = inv["platform_role"]
    premium = bool(inv.get("premium_access"))
    features = DEFAULT_ROLE_FEATURES.get(role, [])
    permissions = _filter_permissions(_default_permissions_for_role(role))
    now_utc = datetime.now(timezone.utc)

    existing = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "platform_role": 1})

    if existing:
        if existing.get("platform_role"):
            await db.platform_employee_invitations.update_one(
                {"invitation_id": inv["invitation_id"]},
                {"$set": {"status": "accepted", "accepted_at": now_utc.isoformat(), "accepted_user_id": existing["user_id"]}},
            )
            raise HTTPException(status_code=400, detail="Account already promoted. Please sign in.")
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "password_hash": hash_password(body.password),
                "platform_role": role,
                "premium_access": premium,
                "feature_access": features,
                "employee_permissions": permissions,
                "employee_since": now_utc.isoformat(),
                "name": body.name or existing.get("name") or email.split("@")[0],
            }},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = User(
            user_id=user_id,
            email=email,
            name=body.name or email.split("@")[0],
            auth_provider="email",
            password_hash=hash_password(body.password),
            roles=["user"],
            role="user",
        )
        doc = user.dict()
        doc.update({
            "platform_role": role,
            "premium_access": premium,
            "feature_access": features,
            "employee_permissions": permissions,
            "employee_since": now_utc.isoformat(),
            "email_verified": True,
        })
        await db.users.insert_one(doc)

    await db.platform_employee_invitations.update_one(
        {"invitation_id": inv["invitation_id"]},
        {"$set": {"status": "accepted", "accepted_at": now_utc.isoformat(), "accepted_user_id": user_id}},
    )

    # Audit
    await _log_audit(
        inv.get("invited_by_user_id", "system"),
        inv.get("invited_by_email", "system"),
        "invitation_accepted",
        user_id,
        email,
        {"platform_role": role, "premium_access": premium, "invitation_id": inv["invitation_id"]},
    )

    # Auto-login: issue a session token
    token_version = 0
    session_token = create_jwt_token(user_id, email, token_version, 60 * 24)
    session = UserSession(
        user_id=user_id,
        session_token=session_token,
        refresh_token=secrets.token_urlsafe(32),
        token_version=token_version,
        issued_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
        ip_address=request.client.host if request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    logger.info(f"[EMPLOYEE-INVITE] accepted email={email} role={role} user_id={user_id}")

    return {
        "accepted": True,
        "user_id": user_id,
        "email": email,
        "platform_role": role,
        "premium_access": premium,
        "session_token": session_token,
    }



class InvitationDecline(BaseModel):
    token: str
    reason: Optional[str] = None


@router.post("/invitations/decline")
async def decline_employee_invitation(body: InvitationDecline):
    """Public endpoint: invitee declines a platform-employee invitation by token.

    Marks the invitation as `declined` and emits an audit record. The invitee
    does NOT need to be logged in — the token itself authenticates the action.
    """
    inv = await db.platform_employee_invitations.find_one(_invitation_token_query(body.token), {"_id": 0})
    if not inv:
        raise HTTPException(status_code=400, detail="Invalid invitation token")

    current_status = inv.get("status")
    if current_status == "declined":
        return {"declined": True, "already": True, "status": "declined"}
    if current_status != "pending":
        raise HTTPException(status_code=400, detail=f"Invitation is {current_status} — cannot decline")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.platform_employee_invitations.update_one(
        {"invitation_id": inv["invitation_id"]},
        {"$set": {
            "status": "declined",
            "declined_at": now_iso,
            "decline_reason": (body.reason or "").strip()[:500] or None,
        }},
    )
    await _log_audit(
        inv.get("invited_by_user_id") or "system",
        inv.get("invited_by_email") or "system",
        "invitation_declined",
        inv.get("existing_user_id"),
        inv.get("email"),
        {
            "invitation_id": inv["invitation_id"],
            "platform_role": inv.get("platform_role"),
            "reason": (body.reason or "").strip()[:500] or None,
        },
    )
    logger.info(f"[EMPLOYEE-INVITE] Declined {inv.get('email')} · reason={body.reason!r}")
    return {"declined": True, "status": "declined", "email": inv.get("email")}


# ─────────────────────────────────────────────────────────────────────────
# Legacy "silent-grant" audit & remediation
# ─────────────────────────────────────────────────────────────────────────
# Identifies users who were granted platform_role by the OLD buggy invite
# code path (pre-2026-02 fix) — i.e. existing users auto-promoted without an
# invitation record and without ever clicking an acceptance link.

async def _find_ghost_employees() -> list[dict]:
    """Return users with platform_role but no matching accepted-invitation record."""
    ghosts: list[dict] = []
    cursor = db.users.find(
        {"platform_role": {"$ne": None, "$exists": True}},
        {
            "_id": 0, "user_id": 1, "email": 1, "name": 1, "platform_role": 1,
            "premium_access": 1, "employee_since": 1, "employee_permissions": 1,
        },
    )
    async for u in cursor:
        email = (u.get("email") or "").lower().strip()
        if not email:
            continue
        # A "legit" employee has either an accepted invitation OR was invited
        # after the fix (any invitation record at all is evidence of consent).
        has_inv = await db.platform_employee_invitations.find_one(
            {"email": email}, {"_id": 0, "invitation_id": 1, "status": 1, "accepted_at": 1},
        )
        if has_inv:
            continue
        ghosts.append({
            "user_id": u["user_id"],
            "email": email,
            "name": u.get("name"),
            "platform_role": u.get("platform_role"),
            "premium_access": bool(u.get("premium_access")),
            "employee_since": u.get("employee_since"),
            "employee_permissions": u.get("employee_permissions") or [],
        })
    return ghosts


@router.get("/ghost-audit")
async def ghost_employee_audit(request: Request):
    """List users granted `platform_role` without a matching invitation record
    (i.e. silently onboarded by the legacy bug). Admin-only."""
    await require_admin(request)
    ghosts = await _find_ghost_employees()
    return {"ghosts": ghosts, "count": len(ghosts)}


class GhostConvertBody(BaseModel):
    user_ids: Optional[list[str]] = None  # if omitted, converts ALL ghosts


@router.post("/ghost-audit/convert-to-pending")
async def ghost_employees_convert_to_pending(body: GhostConvertBody, request: Request):
    """For each silent-grant ghost: revoke their platform_role, create a
    fresh pending invitation, and send the invitation email. Forces explicit
    acceptance before they regain employee status.
    """
    admin = await require_admin(request)
    all_ghosts = await _find_ghost_employees()
    # Treat `None` (field omitted) as "convert all". An empty list `[]` means
    # an explicit empty target set — do not secretly remediate everyone.
    if body.user_ids is None:
        target_ids = {g["user_id"] for g in all_ghosts}
    else:
        target_ids = set(body.user_ids)
    targets = [g for g in all_ghosts if g["user_id"] in target_ids]

    now_iso_dt = datetime.now(timezone.utc)
    now_iso = now_iso_dt.isoformat()
    converted: list[dict] = []
    failed: list[dict] = []

    for g in targets:
        try:
            # 1. Revoke current platform_role (force re-acceptance)
            await db.users.update_one(
                {"user_id": g["user_id"]},
                {"$set": {
                    "platform_role": None,
                    "premium_access": False,
                    "feature_access": [],
                    "employee_permissions": [],
                    "employee_since": None,
                    "ghost_revoked_at": now_iso,
                }},
            )

            # 2. Create fresh pending invitation
            token = secrets.token_urlsafe(32)
            invitation_id = f"empinv_{uuid.uuid4().hex[:12]}"
            expires_at = now_iso_dt + timedelta(hours=72)
            await db.platform_employee_invitations.insert_one({
                "invitation_id": invitation_id,
                "token_hash": _hash_invitation_token(token),
                "token_last4": token[-4:],
                "email": g["email"],
                "platform_role": g["platform_role"],
                "premium_access": g["premium_access"],
                "feature_access": DEFAULT_ROLE_FEATURES.get(g["platform_role"], []),
                "employee_permissions": g["employee_permissions"] or _default_permissions_for_role(g["platform_role"]),
                "invited_by_user_id": admin.user_id,
                "invited_by_email": admin.email,
                "status": "pending",
                "created_at": now_iso,
                "expires_at": expires_at.isoformat(),
                "accepted_at": None,
                "accepted_user_id": None,
                "existing_user_id": g["user_id"],
                "source": "ghost_remediation",
            })

            # 3. Send invitation email
            invite_url = _build_invitation_url(token)
            email_sent = False
            try:
                from utils.email_notifications import send_platform_employee_invitation
                res = await send_platform_employee_invitation(
                    recipient_email=g["email"],
                    platform_role=g["platform_role"],
                    invited_by_email=admin.email,
                    invite_url=invite_url,
                    expires_in_hours=72,
                )
                email_sent = bool(res and res.get("success"))
            except Exception as exc:
                logger.warning(f"[GHOST-REMEDIATION] email failed for {g['email']}: {exc}")

            await _log_audit(
                admin.user_id, admin.email, "ghost_employee_remediated",
                g["user_id"], g["email"],
                {
                    "prior_role": g["platform_role"],
                    "invitation_id": invitation_id,
                    "email_sent": email_sent,
                },
            )
            converted.append({
                "user_id": g["user_id"],
                "email": g["email"],
                "invitation_id": invitation_id,
                "email_sent": email_sent,
            })
        except Exception as exc:
            failed.append({"user_id": g["user_id"], "email": g["email"], "error": str(exc)[:200]})

    return {
        "converted_count": len(converted),
        "failed_count": len(failed),
        "converted": converted,
        "failed": failed,
    }
