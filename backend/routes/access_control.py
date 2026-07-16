"""Enterprise access-control APIs: entitlements, lifecycle transitions, and audits."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from routes.db import (
    db,
    require_auth,
    require_admin,
    log_authorization_audit,
)
from utils.access_governance import (
    apply_global_rbac_subscription_enforcement,
    append_access_ledger,
    require_dual_admin_approval,
)
from utils.access_control_engine import (
    PLAN_LEVEL,
    PLATFORM_EMPLOYEE_PERMISSIONS,
    PLATFORM_EMPLOYEE_ROLES,
    DEFAULT_ROLE_PERMISSIONS,
    CANONICAL_FEATURE_METERS,
    SUBSCRIPTION_ACCESS_POLICY_VERSION,
    build_employee_permissions,
    build_session_entitlements,
    compute_effective_plan,
    evaluate_api_access,
    get_feature_daily_action_limit,
    reconcile_due_transition,
)


router = APIRouter(tags=["Access Control"])


class RouteAccessCheckRequest(BaseModel):
    path: str
    method: str = "GET"


class SubscriptionTransitionRequest(BaseModel):
    action: str = Field(description="upgrade | downgrade | cancel")
    target_plan: Optional[str] = None
    reason: Optional[str] = None
    payment_session_id: Optional[str] = None


class EmployeeAccessUpdateRequest(BaseModel):
    user_id: str
    platform_role: Optional[str] = None
    employee_permissions: list[str] = Field(default_factory=list)
    feature_access: list[str] = Field(default_factory=list)
    reason: Optional[str] = None


class AdminSubscriptionTransitionRequest(BaseModel):
    user_id: str
    action: str = Field(description="upgrade | downgrade | cancel")
    target_plan: Optional[str] = None
    reason: str = "admin_override"


class RoleTemplateUpdateRequest(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    feature_access: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    note: Optional[str] = None
    ttl_minutes: int = Field(default=30, ge=5, le=120)


class BreakGlassActivateRequest(BaseModel):
    incident_ticket_id: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=5, max_length=500)
    duration_minutes: int = Field(default=30, ge=5, le=60)


class GlobalEnforcementRequest(BaseModel):
    baseline_reset_non_admin_paid: bool = False
    apply_subscription_access_policy_migration: bool = True


def _normalize_action(action: str) -> str:
    val = str(action or "").strip().lower()
    if val not in {"upgrade", "downgrade", "cancel"}:
        raise HTTPException(status_code=400, detail="action must be one of: upgrade, downgrade, cancel")
    return val


def _normalize_target_plan(action: str, target_plan: Optional[str]) -> str:
    if action == "cancel":
        return "free"
    candidate = str(target_plan or "").strip().lower()
    if candidate not in PLAN_LEVEL:
        raise HTTPException(status_code=400, detail="target_plan must be one of: free, basic, premium")
    return candidate


def _parse_dt(value: Optional[object]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt_val = value
    elif isinstance(value, str):
        try:
            dt_val = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)
    return dt_val


async def _require_high_risk_admin_change(
    request: Request,
    *,
    action: str,
    target_user_id: str = "",
    payload: Optional[dict] = None,
):
    return await require_dual_admin_approval(
        request,
        action=action,
        target_user_id=target_user_id,
        payload=payload or {},
    )


async def _load_user_doc(user_id: str) -> dict:
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "is_admin": 1,
            "full_access": 1,
            "platform_role": 1,
            "employee_permissions": 1,
            "feature_access": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "subscription_permanent": 1,
            "payment_verified": 1,
            "pending_subscription_transition": 1,
        },
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    user_doc, _ = await reconcile_due_transition(db, user_doc)
    return user_doc


async def _write_subscription_lifecycle_event(
    actor_user_id: str,
    actor_email: str,
    target_user_id: str,
    action: str,
    target_plan: str,
    mode: str,
    effective_at: datetime,
    reason: str,
):
    now = datetime.now(timezone.utc)
    await db.subscription_lifecycle_audit.insert_one(
        {
            "event_id": f"slc_{now.strftime('%Y%m%d%H%M%S%f')}",
            "actor_user_id": actor_user_id,
            "actor_email": actor_email,
            "target_user_id": target_user_id,
            "action": action,
            "target_plan": target_plan,
            "mode": mode,
            "reason": reason,
            "effective_at": effective_at.isoformat(),
            "created_at": now.isoformat(),
        }
    )


async def _validate_upgrade_payment(user_id: str, target_plan: str, payment_session_id: Optional[str]):
    if not payment_session_id:
        raise HTTPException(status_code=402, detail="payment_session_id is required for upgrades")
    tx = await db.payment_transactions.find_one(
        {
            "session_id": payment_session_id,
            "user_id": user_id,
            "plan_id": target_plan,
            "payment_status": {"$in": ["completed", "paid", "succeeded"]},
        },
        {"_id": 0, "session_id": 1},
    )
    if not tx:
        raise HTTPException(status_code=402, detail="Valid completed payment not found for requested upgrade")


async def _apply_transition(
    actor_user_id: str,
    actor_email: str,
    target_user_doc: dict,
    action: str,
    target_plan: str,
    reason: str,
    payment_session_id: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    current_plan = compute_effective_plan(target_user_doc)
    current_level = PLAN_LEVEL.get(current_plan, 0)
    target_level = PLAN_LEVEL.get(target_plan, 0)

    if action == "upgrade" and target_level <= current_level:
        raise HTTPException(status_code=400, detail="Upgrade target must be higher than current plan")
    if action == "downgrade" and target_level >= current_level:
        raise HTTPException(status_code=400, detail="Downgrade target must be lower than current plan")

    # Upgrade: immediate with verified payment reference.
    if action == "upgrade":
        await _validate_upgrade_payment(target_user_doc["user_id"], target_plan, payment_session_id)
        await db.users.update_one(
            {"user_id": target_user_doc["user_id"]},
            {
                "$set": {
                    "subscription_plan": target_plan,
                    "subscription_status": "active",
                    "updated_at": now,
                },
                "$unset": {"pending_subscription_transition": ""},
            },
        )
        await _write_subscription_lifecycle_event(
            actor_user_id,
            actor_email,
            target_user_doc["user_id"],
            action,
            target_plan,
            "immediate",
            now,
            reason,
        )
        return {
            "mode": "immediate",
            "effective_at": now.isoformat(),
            "current_plan": current_plan,
            "target_plan": target_plan,
        }

    # Downgrade/cancel: period-boundary by default.
    boundary = _parse_dt(target_user_doc.get("subscription_end_date")) or now
    if boundary < now:
        boundary = now

    pending = {
        "action": action,
        "target_plan": target_plan,
        "requested_at": now.isoformat(),
        "effective_at": boundary.isoformat(),
        "requested_by": actor_user_id,
        "reason": reason,
    }
    status_value = "cancelled" if action == "cancel" else "scheduled_downgrade"
    await db.users.update_one(
        {"user_id": target_user_doc["user_id"]},
        {
            "$set": {
                "subscription_status": status_value,
                "pending_subscription_transition": pending,
                "updated_at": now,
            }
        },
    )
    await _write_subscription_lifecycle_event(
        actor_user_id,
        actor_email,
        target_user_doc["user_id"],
        action,
        target_plan,
        "billing_boundary",
        boundary,
        reason,
    )
    return {
        "mode": "billing_boundary",
        "effective_at": boundary.isoformat(),
        "current_plan": current_plan,
        "target_plan": target_plan,
    }


@router.get("/access-control/session")
async def access_control_session(request: Request):
    user = await require_auth(request)
    user_doc = await _load_user_doc(user.user_id)
    payload = build_session_entitlements(user_doc)
    payload["user_id"] = user.user_id
    payload["email"] = user.email
    payload["pending_subscription_transition"] = user_doc.get("pending_subscription_transition")
    return payload


@router.get("/access-control/feature-meter/{feature_key}")
async def feature_meter_status(feature_key: str, request: Request):
    """Live daily action meter status for one canonical feature (quota pill)."""
    user = await require_auth(request)
    meter = next((m for m in CANONICAL_FEATURE_METERS if m["feature_key"] == feature_key), None)
    if not meter:
        raise HTTPException(status_code=404, detail="Unknown feature key")
    user_doc = await _load_user_doc(user.user_id)
    plan = compute_effective_plan(user_doc)
    limit = get_feature_daily_action_limit(meter, plan)
    used = 0
    if limit >= 0:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used = await db.feature_usage_meter.count_documents(
            {"user_id": user.user_id, "feature_key": feature_key, "day": day}
        )
    return {
        "feature_key": feature_key,
        "plan": plan,
        "limit": limit,
        "used": used,
        "remaining": -1 if limit < 0 else max(0, limit - used),
        "self_enforced": bool(meter.get("self_enforced")),
        "policy_version": SUBSCRIPTION_ACCESS_POLICY_VERSION,
    }


SPECIALIST_PUBLIC_FIELDS = ("agent_key", "name", "role", "category", "subcategory", "description")


class SpecialistClickRequest(BaseModel):
    agent_key: str = Field(..., min_length=2, max_length=80)


@router.get("/access-control/feature-specialists/{feature_key}")
async def feature_specialists(feature_key: str, request: Request, limit: int = 4):
    """Sanitized top specialists for a canonical feature (Suggested AI Specialists strip)."""
    user = await require_auth(request)
    meter = next((m for m in CANONICAL_FEATURE_METERS if m["feature_key"] == feature_key), None)
    if not meter:
        raise HTTPException(status_code=404, detail="Unknown feature key")
    from agent_framework.marketplace import recommend_agents

    recs = await recommend_agents(feature_key, limit=min(max(limit, 1), 6))
    user_doc = await _load_user_doc(user.user_id)
    plan = compute_effective_plan(user_doc)
    return {
        "feature_key": feature_key,
        "plan": plan,
        "specialists": [
            {k: r.get(k, "") for k in SPECIALIST_PUBLIC_FIELDS}
            for r in recs["recommendations"]
        ],
        "cta_route": "/ai-coaching-team",
    }


@router.post("/access-control/feature-specialists/{feature_key}/click")
async def feature_specialist_click(feature_key: str, body: SpecialistClickRequest, request: Request):
    """Conversion event: user tapped a specialist chip (feeds Conversion Pulse analytics)."""
    user = await require_auth(request)
    if not any(m["feature_key"] == feature_key for m in CANONICAL_FEATURE_METERS):
        raise HTTPException(status_code=404, detail="Unknown feature key")
    user_doc = await _load_user_doc(user.user_id)
    await db.specialist_strip_events.insert_one({
        "event_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "feature_key": feature_key,
        "agent_key": body.agent_key,
        "plan": compute_effective_plan(user_doc),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"logged": True}


@router.post("/access-control/check-route")
async def access_control_check_route(body: RouteAccessCheckRequest, request: Request):
    user = await require_auth(request)
    user_doc = await _load_user_doc(user.user_id)
    decision = evaluate_api_access(body.path, body.method, user_doc)
    return decision


@router.post("/subscriptions/lifecycle/transition")
async def request_subscription_transition(body: SubscriptionTransitionRequest, request: Request):
    user = await require_auth(request)
    action = _normalize_action(body.action)
    target_plan = _normalize_target_plan(action, body.target_plan)
    user_doc = await _load_user_doc(user.user_id)

    result = await _apply_transition(
        actor_user_id=user.user_id,
        actor_email=user.email,
        target_user_doc=user_doc,
        action=action,
        target_plan=target_plan,
        reason=body.reason or "user_request",
        payment_session_id=body.payment_session_id,
    )
    await log_authorization_audit(
        user.user_id,
        user.email,
        "subscription_transition_request",
        "allowed",
        request,
        {
            "action": action,
            "target_plan": target_plan,
            "mode": result["mode"],
            "effective_at": result["effective_at"],
        },
    )
    return {"success": True, **result}


@router.get("/subscriptions/lifecycle/pending")
async def get_pending_subscription_transition(request: Request):
    user = await require_auth(request)
    user_doc = await _load_user_doc(user.user_id)
    return {
        "subscription_plan": compute_effective_plan(user_doc),
        "subscription_status": user_doc.get("subscription_status", "active"),
        "pending_transition": user_doc.get("pending_subscription_transition"),
    }


@router.post("/subscriptions/lifecycle/reconcile")
async def reconcile_subscription_lifecycle(request: Request):
    actor = await require_admin(request)
    now = datetime.now(timezone.utc)
    cursor = db.users.find(
        {
            "pending_subscription_transition.effective_at": {"$lte": now.isoformat()},
        },
        {"_id": 0},
    )
    updated = 0
    async for doc in cursor:
        _, changed = await reconcile_due_transition(db, doc)
        if changed:
            updated += 1
    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "subscription_transition_reconcile",
        "allowed",
        request,
        {"updated_count": updated},
    )
    return {"success": True, "updated_count": updated}


@router.post("/admin/access-control/subscription-transition")
async def admin_subscription_transition(body: AdminSubscriptionTransitionRequest, request: Request):
    actor = await _require_high_risk_admin_change(
        request,
        action="admin_subscription_transition",
        target_user_id=body.user_id,
        payload={"action": body.action, "target_plan": body.target_plan, "reason": body.reason},
    )
    action = _normalize_action(body.action)
    target_plan = _normalize_target_plan(action, body.target_plan)
    target_user_doc = await _load_user_doc(body.user_id)

    result = await _apply_transition(
        actor_user_id=actor.user_id,
        actor_email=actor.email,
        target_user_doc=target_user_doc,
        action=action,
        target_plan=target_plan,
        reason=body.reason,
        payment_session_id=None,
    )
    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "admin_subscription_transition",
        "allowed",
        request,
        {"target_user_id": body.user_id, "action": action, "target_plan": target_plan, "mode": result["mode"]},
    )
    return {"success": True, "target_user_id": body.user_id, **result}


@router.post("/admin/access-control/employee-access")
async def admin_update_employee_access(body: EmployeeAccessUpdateRequest, request: Request):
    actor = await _require_high_risk_admin_change(
        request,
        action="admin_employee_access_update",
        target_user_id=body.user_id,
        payload={
            "platform_role": body.platform_role,
            "employee_permissions": body.employee_permissions,
            "feature_access": body.feature_access,
            "reason": body.reason,
        },
    )
    target = await db.users.find_one(
        {"user_id": body.user_id},
        {"_id": 0, "user_id": 1, "platform_role": 1, "employee_permissions": 1, "feature_access": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    update_payload = {
        "employee_permissions": sorted(build_employee_permissions({"platform_role": body.platform_role or target.get("platform_role"), "employee_permissions": body.employee_permissions})),
        "feature_access": sorted(list(set(body.feature_access or []))),
        "updated_at": datetime.now(timezone.utc),
    }
    if body.platform_role is not None:
        update_payload["platform_role"] = body.platform_role

    await db.users.update_one({"user_id": body.user_id}, {"$set": update_payload})
    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "admin_employee_access_update",
        "allowed",
        request,
        {
            "target_user_id": body.user_id,
            "platform_role": body.platform_role,
            "employee_permissions": update_payload["employee_permissions"],
            "feature_access_count": len(update_payload["feature_access"]),
            "reason": body.reason or "",
        },
    )
    return {"success": True, "target_user_id": body.user_id, **update_payload}


@router.get("/admin/access-control/policy-console/bootstrap")
async def policy_console_bootstrap(request: Request):
    _actor = await require_admin(request)
    template_rows = await db.access_role_templates.find({}, {"_id": 0}).to_list(200)
    overrides = {row.get("role"): row for row in template_rows}

    role_templates = []
    for role in PLATFORM_EMPLOYEE_ROLES:
        override = overrides.get(role, {})
        role_templates.append(
            {
                "role": role,
                "permissions": sorted(
                    list(
                        set(
                            override.get("permissions")
                            or DEFAULT_ROLE_PERMISSIONS.get(role, [])
                        )
                    )
                ),
                "feature_access": sorted(list(set(override.get("feature_access") or []))),
                "notes": override.get("notes", ""),
                "updated_at": override.get("updated_at"),
            }
        )

    pending_count = await db.users.count_documents({"pending_subscription_transition": {"$exists": True}})
    return {
        "role_templates": role_templates,
        "permission_catalog": PLATFORM_EMPLOYEE_PERMISSIONS,
        "pending_transition_count": pending_count,
    }


@router.put("/admin/access-control/policy-console/role-template/{role}")
async def policy_console_upsert_role_template(role: str, body: RoleTemplateUpdateRequest, request: Request):
    actor = await require_admin(request)
    if role not in PLATFORM_EMPLOYEE_ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown role: {role}")
    now = datetime.now(timezone.utc)
    payload = {
        "role": role,
        "permissions": sorted(list(set([p for p in body.permissions if p in PLATFORM_EMPLOYEE_PERMISSIONS]))),
        "feature_access": sorted(list(set(body.feature_access or []))),
        "notes": body.notes or "",
        "updated_by": actor.user_id,
        "updated_at": now.isoformat(),
    }
    await db.access_role_templates.update_one({"role": role}, {"$set": payload}, upsert=True)
    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "policy_console_role_template_update",
        "allowed",
        request,
        {"role": role, "permissions_count": len(payload["permissions"]), "feature_access_count": len(payload["feature_access"])},
    )
    return {"success": True, **payload}


@router.get("/admin/access-control/policy-console/pending-transitions")
async def policy_console_pending_transitions(request: Request, limit: int = Query(100, ge=1, le=500)):
    _actor = await require_admin(request)
    rows = await db.users.find(
        {"pending_subscription_transition": {"$exists": True}},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "pending_subscription_transition": 1,
        },
    ).limit(limit).to_list(limit)
    return {"records": rows, "total": len(rows)}


@router.post("/admin/access-control/policy-console/pending-transitions/{user_id}/approve")
async def policy_console_approve_transition(user_id: str, request: Request):
    actor = await _require_high_risk_admin_change(
        request,
        action="policy_console_transition_approve",
        target_user_id=user_id,
        payload={},
    )
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "pending_subscription_transition": 1, "user_id": 1})
    if not target or not target.get("pending_subscription_transition"):
        raise HTTPException(status_code=404, detail="Pending transition not found")

    pending = target["pending_subscription_transition"]
    pending["effective_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"user_id": user_id}, {"$set": {"pending_subscription_transition": pending}})
    refreshed = await _load_user_doc(user_id)
    refreshed, _ = await reconcile_due_transition(db, refreshed)

    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "policy_console_transition_approve",
        "allowed",
        request,
        {"target_user_id": user_id, "action": pending.get("action"), "target_plan": pending.get("target_plan")},
    )
    return {"success": True, "target_user_id": user_id, "applied_plan": refreshed.get("subscription_plan"), "status": refreshed.get("subscription_status")}


@router.post("/admin/access-control/policy-console/pending-transitions/{user_id}/reject")
async def policy_console_reject_transition(user_id: str, request: Request):
    actor = await _require_high_risk_admin_change(
        request,
        action="policy_console_transition_reject",
        target_user_id=user_id,
        payload={},
    )
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "pending_subscription_transition": 1})
    if not target or not target.get("pending_subscription_transition"):
        raise HTTPException(status_code=404, detail="Pending transition not found")

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$unset": {"pending_subscription_transition": ""},
            "$set": {"subscription_status": "active", "updated_at": datetime.now(timezone.utc)},
        },
    )
    await db.subscription_lifecycle_audit.insert_one(
        {
            "event_id": f"slr_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "actor_user_id": actor.user_id,
            "target_user_id": user_id,
            "action": "transition_rejected",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await log_authorization_audit(
        actor.user_id,
        actor.email,
        "policy_console_transition_reject",
        "allowed",
        request,
        {"target_user_id": user_id},
    )
    return {"success": True, "target_user_id": user_id}


@router.get("/admin/access-control/observability")
async def access_control_observability(request: Request):
    _actor = await require_admin(request)
    now = datetime.now(timezone.utc)
    window_start = (now.replace(microsecond=0) - timedelta(days=7)).isoformat()

    denied_cursor = db.authorization_audit_log.aggregate(
        [
            {"$match": {"outcome": "denied", "created_at": {"$gte": window_start}}},
            {"$group": {"_id": "$metadata.path", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 12},
        ]
    )
    denied_rows = await denied_cursor.to_list(12)
    heatmap = [{"path": row.get("_id") or "unknown", "count": row.get("count", 0)} for row in denied_rows]

    template_rows = await db.access_role_templates.find({}, {"_id": 0}).to_list(200)
    template_map = {row.get("role"): set(row.get("permissions") or []) for row in template_rows}
    drift_alerts = []
    users = await db.users.find(
        {"platform_role": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "user_id": 1, "email": 1, "platform_role": 1, "employee_permissions": 1},
    ).to_list(1000)
    for user in users:
        role = user.get("platform_role")
        assigned = set(user.get("employee_permissions") or [])
        baseline = set(template_map.get(role) or DEFAULT_ROLE_PERMISSIONS.get(role, []))
        missing = sorted(list(baseline - assigned))
        extra = sorted(list(assigned - baseline))
        if missing or extra:
            drift_alerts.append(
                {
                    "user_id": user.get("user_id"),
                    "email": user.get("email"),
                    "role": role,
                    "missing_permissions": missing,
                    "extra_permissions": extra,
                    "severity": "high" if len(missing) + len(extra) >= 3 else "medium",
                }
            )
    drift_alerts = sorted(drift_alerts, key=lambda x: (x["severity"] != "high", -(len(x["missing_permissions"]) + len(x["extra_permissions"]))))[:25]

    stale_threshold = (now - timedelta(hours=24)).isoformat()
    stale_pending = await db.users.count_documents({"pending_subscription_transition.effective_at": {"$lt": stale_threshold}})
    rejected_count = await db.subscription_lifecycle_audit.count_documents(
        {"action": {"$in": ["transition_rejected", "transition_failed"]}, "created_at": {"$gte": window_start}}
    )

    return {
        "denied_route_heatmap": heatmap,
        "policy_drift_alerts": drift_alerts,
        "transition_failure_monitor": {
            "stale_pending_count": stale_pending,
            "recent_rejected_or_failed": rejected_count,
            "window_start": window_start,
            "window_end": now.isoformat(),
        },
    }


@router.get("/admin/access-control/audit")
async def admin_access_control_audit(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    _actor = await require_admin(request)
    skip = (page - 1) * limit
    total = await db.authorization_audit_log.count_documents({})
    rows = (
        await db.authorization_audit_log.find({}, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "records": rows,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/admin/access-control/approvals")
async def list_dual_admin_approvals(
    request: Request,
    status: str = Query("pending", pattern="^(pending|approved|consumed|rejected|all)$"),
    limit: int = Query(100, ge=1, le=500),
):
    _admin = await require_admin(request)
    query = {} if status == "all" else {"status": status}
    rows = await db.rbac_dual_approval_requests.find(query, {"_id": 0}).sort("requested_at", -1).limit(limit).to_list(limit)
    return {"status": status, "count": len(rows), "records": rows}


@router.post("/admin/access-control/approvals/{request_id}/approve")
async def approve_dual_admin_request(request_id: str, body: ApprovalDecisionRequest, request: Request):
    admin = await require_admin(request)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    req = await db.rbac_dual_approval_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {req.get('status')}")
    if req.get("requested_by_user_id") == admin.user_id:
        raise HTTPException(status_code=403, detail="A different admin must approve this request")
    expires_at = _parse_dt(req.get("expires_at"))
    if expires_at and expires_at <= now:
        await db.rbac_dual_approval_requests.update_one(
            {"request_id": request_id},
            {"$set": {"status": "expired", "updated_at": now_iso}},
        )
        raise HTTPException(status_code=409, detail="Approval request expired")

    approval_token = f"rbac_appr_{uuid.uuid4().hex}"
    approval_expires_at = (now + timedelta(minutes=body.ttl_minutes)).isoformat()
    await db.rbac_dual_approval_requests.update_one(
        {"request_id": request_id},
        {
            "$set": {
                "status": "approved",
                "approved_by_user_id": admin.user_id,
                "approved_by_email": admin.email,
                "approved_at": now_iso,
                "approval_token": approval_token,
                "approval_expires_at": approval_expires_at,
                "approval_note": body.note or "",
                "updated_at": now_iso,
            }
        },
    )
    await append_access_ledger(
        event_type="rbac_dual_approval_approved",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        target_user_id=str(req.get("target_user_id") or ""),
        metadata={"request_id": request_id, "action": req.get("action"), "approval_note": body.note or ""},
    )
    return {
        "success": True,
        "request_id": request_id,
        "approval_token": approval_token,
        "approval_expires_at": approval_expires_at,
    }


@router.post("/admin/access-control/approvals/{request_id}/reject")
async def reject_dual_admin_request(request_id: str, body: ApprovalDecisionRequest, request: Request):
    admin = await require_admin(request)
    req = await db.rbac_dual_approval_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {req.get('status')}")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.rbac_dual_approval_requests.update_one(
        {"request_id": request_id},
        {
            "$set": {
                "status": "rejected",
                "rejected_by_user_id": admin.user_id,
                "rejected_by_email": admin.email,
                "rejected_at": now_iso,
                "rejection_note": body.note or "",
                "updated_at": now_iso,
            }
        },
    )
    await append_access_ledger(
        event_type="rbac_dual_approval_rejected",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        target_user_id=str(req.get("target_user_id") or ""),
        metadata={"request_id": request_id, "action": req.get("action"), "rejection_note": body.note or ""},
    )
    return {"success": True, "request_id": request_id, "status": "rejected"}


@router.post("/admin/access-control/break-glass/activate")
async def activate_break_glass(body: BreakGlassActivateRequest, request: Request):
    admin = await require_admin(request)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    session_id = f"bg_{uuid.uuid4().hex[:12]}"
    expires_at = (now + timedelta(minutes=body.duration_minutes)).isoformat()
    await db.admin_break_glass_sessions.insert_one(
        {
            "session_id": session_id,
            "admin_user_id": admin.user_id,
            "admin_email": admin.email,
            "incident_ticket_id": body.incident_ticket_id,
            "reason": body.reason,
            "status": "active",
            "started_at": now_iso,
            "expires_at": expires_at,
            "updated_at": now_iso,
        }
    )
    await append_access_ledger(
        event_type="break_glass_activated",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        metadata={
            "session_id": session_id,
            "incident_ticket_id": body.incident_ticket_id,
            "duration_minutes": body.duration_minutes,
        },
    )
    return {"success": True, "session_id": session_id, "expires_at": expires_at}


@router.post("/admin/access-control/break-glass/deactivate")
async def deactivate_break_glass(request: Request):
    admin = await require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.admin_break_glass_sessions.update_many(
        {"admin_user_id": admin.user_id, "status": "active"},
        {"$set": {"status": "closed", "closed_at": now_iso, "updated_at": now_iso}},
    )
    await append_access_ledger(
        event_type="break_glass_deactivated",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        metadata={"closed_sessions": int(result.modified_count)},
    )
    return {"success": True, "closed_sessions": int(result.modified_count)}


@router.get("/admin/access-control/break-glass/status")
async def break_glass_status(request: Request):
    admin = await require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    active = await db.admin_break_glass_sessions.find(
        {"admin_user_id": admin.user_id, "status": "active", "expires_at": {"$gt": now_iso}},
        {"_id": 0},
    ).sort("started_at", -1).to_list(20)
    return {"active_sessions": active, "count": len(active)}


@router.post("/admin/access-control/global-enforcement")
async def run_global_rbac_subscription_enforcement(body: GlobalEnforcementRequest, request: Request):
    admin = await require_admin(request)
    result = await apply_global_rbac_subscription_enforcement(
        trigger="manual_admin_api",
        actor_user_id=admin.user_id,
        actor_email=admin.email,
        baseline_reset_non_admin_paid=bool(body.baseline_reset_non_admin_paid),
        migrate_legacy_paid_flags=bool(body.apply_subscription_access_policy_migration),
    )
    return {"success": True, **result}
