"""Enterprise access governance helpers: dual-admin approvals, break-glass, tamper-evident ledger."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import uuid
from typing import Any

from fastapi import HTTPException, Request
from utils.pagination import iter_find_paginated


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_fingerprint(action: str, target_user_id: str | None, payload: dict[str, Any] | None) -> str:
    canonical = _canonical_json(
        {
            "action": str(action or "").strip().lower(),
            "target_user_id": str(target_user_id or "").strip(),
            "payload": payload or {},
        }
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def append_access_ledger(
    *,
    event_type: str,
    actor_user_id: str,
    actor_email: str,
    target_user_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from routes.db import db

    previous = await db.enterprise_access_ledger.find_one({}, {"_id": 0, "hash": 1}, sort=[("created_at", -1)]) or {}
    previous_hash = str(previous.get("hash") or "")
    now_iso = _iso_now()

    payload = {
        "event_type": str(event_type or "access_event"),
        "actor_user_id": str(actor_user_id or ""),
        "actor_email": str(actor_email or ""),
        "target_user_id": str(target_user_id or ""),
        "metadata": metadata or {},
        "created_at": now_iso,
    }
    payload_hash = hashlib.sha256(f"{previous_hash}|{_canonical_json(payload)}".encode()).hexdigest()
    entry = {
        "entry_id": f"acl_{uuid.uuid4().hex[:16]}",
        **payload,
        "previous_hash": previous_hash,
        "hash": payload_hash,
    }
    await db.enterprise_access_ledger.insert_one(entry)
    safe_entry = dict(entry)
    safe_entry.pop("_id", None)
    return safe_entry


async def has_active_break_glass(admin_user_id: str, incident_ticket_id: str = "") -> bool:
    from routes.db import db

    now_iso = _iso_now()
    query: dict[str, Any] = {
        "admin_user_id": admin_user_id,
        "status": "active",
        "expires_at": {"$gt": now_iso},
    }
    if incident_ticket_id:
        query["incident_ticket_id"] = incident_ticket_id
    record = await db.admin_break_glass_sessions.find_one(query, {"_id": 0, "session_id": 1})
    return bool(record)


async def require_dual_admin_approval(
    request: Request,
    *,
    action: str,
    target_user_id: str = "",
    payload: dict[str, Any] | None = None,
):
    """Require second-admin approval token for high-risk RBAC operations."""
    from routes.db import db, require_admin

    actor = await require_admin(request)
    action_norm = str(action or "").strip().lower() or "rbac_change"
    target_norm = str(target_user_id or "").strip()
    payload_norm = payload or {}
    fingerprint = build_fingerprint(action_norm, target_norm, payload_norm)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    break_glass_ticket = str(request.headers.get("x-break-glass-ticket-id") or "").strip()
    if break_glass_ticket and await has_active_break_glass(actor.user_id, break_glass_ticket):
        await append_access_ledger(
            event_type="rbac_break_glass_bypass",
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            target_user_id=target_norm,
            metadata={"action": action_norm, "incident_ticket_id": break_glass_ticket},
        )
        return actor

    approval_token = str(request.headers.get("x-rbac-approval-token") or "").strip()
    if not approval_token:
        request_id = f"rbacreq_{uuid.uuid4().hex[:12]}"
        expires_at = (now + timedelta(hours=24)).isoformat()
        await db.rbac_dual_approval_requests.insert_one(
            {
                "request_id": request_id,
                "status": "pending",
                "action": action_norm,
                "target_user_id": target_norm,
                "payload_fingerprint": fingerprint,
                "requested_by_user_id": actor.user_id,
                "requested_by_email": actor.email,
                "requested_at": now_iso,
                "expires_at": expires_at,
                "metadata": payload_norm,
            }
        )
        await append_access_ledger(
            event_type="rbac_dual_approval_requested",
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            target_user_id=target_norm,
            metadata={"request_id": request_id, "action": action_norm},
        )
        raise HTTPException(
            status_code=428,
            detail={
                "message": "Dual-admin approval required for high-risk RBAC operation.",
                "approval_request_id": request_id,
                "next_step": "A different admin must approve this request via /api/admin/access-control/approvals/{approval_request_id}/approve, then retry with x-rbac-approval-token.",
            },
        )

    approval = await db.rbac_dual_approval_requests.find_one(
        {
            "approval_token": approval_token,
            "status": "approved",
            "requested_by_user_id": actor.user_id,
            "action": action_norm,
            "target_user_id": target_norm,
            "payload_fingerprint": fingerprint,
            "approval_expires_at": {"$gt": now_iso},
        },
        {"_id": 0, "request_id": 1, "approved_by_user_id": 1, "approval_expires_at": 1},
    )
    if not approval:
        raise HTTPException(status_code=403, detail="Valid dual-admin approval token required")

    await db.rbac_dual_approval_requests.update_one(
        {"request_id": approval["request_id"]},
        {
            "$set": {
                "status": "consumed",
                "consumed_at": now_iso,
                "consumed_by_user_id": actor.user_id,
            }
        },
    )
    await append_access_ledger(
        event_type="rbac_dual_approval_consumed",
        actor_user_id=actor.user_id,
        actor_email=actor.email,
        target_user_id=target_norm,
        metadata={
            "request_id": approval["request_id"],
            "approved_by_user_id": approval.get("approved_by_user_id"),
            "action": action_norm,
        },
    )
    return actor


def _admin_email_allowlist() -> set[str]:
    from os import environ

    merged: set[str] = set()
    for key in ("ADMIN_EMAILS", "ADMIN_OVERRIDE_EMAILS"):
        raw = str(environ.get(key) or "")
        for value in raw.split(","):
            email = value.strip().lower()
            if email:
                merged.add(email)
    primary = str(environ.get("ADMIN_EMAIL") or "").strip().lower()
    if primary:
        merged.add(primary)
    return merged


async def apply_global_rbac_subscription_enforcement(
    *,
    trigger: str,
    actor_user_id: str,
    actor_email: str,
    baseline_reset_non_admin_paid: bool = False,
    migrate_legacy_paid_flags: bool = True,
) -> dict[str, Any]:
    """Global no-bypass RBAC/subscription enforcement.

    baseline_reset_non_admin_paid=True performs one-time downgrade of all non-admin paid users.
    """
    from routes.db import db

    now_iso = _iso_now()
    admin_allowlist = list(_admin_email_allowlist())

    non_admin_selector: dict[str, Any] = {
        "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
        "email": {"$nin": admin_allowlist},
    }

    result: dict[str, Any] = {
        "trigger": trigger,
        "baseline_reset_non_admin_paid": baseline_reset_non_admin_paid,
        "migrate_legacy_paid_flags": migrate_legacy_paid_flags,
        "started_at": now_iso,
    }

    if baseline_reset_non_admin_paid:
        baseline_query = {
            **non_admin_selector,
            "subscription_plan": {"$in": ["basic", "premium"]},
        }
        impacted_user_ids: list[str] = []
        async for row in iter_find_paginated(db.users, baseline_query, {"_id": 0, "user_id": 1}):
            user_id = str(row.get("user_id") or "")
            if user_id:
                impacted_user_ids.append(user_id)
        baseline = await db.users.update_many(
            baseline_query,
            {
                "$set": {
                    "subscription_plan": "free",
                    "subscription_status": "expired",
                    "payment_verified": False,
                    "premium_access": False,
                    "full_access": False,
                    "subscription_permanent": False,
                    "updated_at": now_iso,
                },
                "$inc": {"token_version": 1},
            },
        )
        if impacted_user_ids:
            await db.user_sessions.delete_many({"user_id": {"$in": impacted_user_ids}})
        result["baseline_downgraded_non_admin_paid"] = int(baseline.modified_count)

    migrated_legacy_users = 0
    cleared_legacy_flags_users = 0
    if migrate_legacy_paid_flags:
        legacy_selector = {
            **non_admin_selector,
            "$or": [
                {"full_access": True},
                {"subscription_permanent": True},
                {"premium_access": True},
            ],
        }

        legacy_rows = []
        async for row in iter_find_paginated(
            db.users,
            legacy_selector,
            {
                "_id": 0,
                "user_id": 1,
                "subscription_plan": 1,
                "subscription_status": 1,
                "full_access": 1,
                "subscription_permanent": 1,
                "premium_access": 1,
            },
        ):
            legacy_rows.append(row)

        for row in legacy_rows:
            user_id = str(row.get("user_id") or "").strip()
            if not user_id:
                continue

            current_plan = str(row.get("subscription_plan") or "free").strip().lower()
            current_status = str(row.get("subscription_status") or "active").strip().lower()

            target_plan = current_plan if current_plan in {"basic", "premium"} else "premium"
            target_status = current_status if current_status in {"active", "trial", "past_due", "cancelled"} else "active"

            update = await db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "subscription_plan": target_plan,
                        "subscription_status": target_status,
                        "payment_verified": True,
                        "updated_at": now_iso,
                    },
                    "$unset": {
                        "full_access": "",
                        "subscription_permanent": "",
                        "premium_access": "",
                    },
                    "$inc": {"token_version": 1},
                },
            )

            if update.modified_count > 0:
                migrated_legacy_users += 1

        cleared_legacy_flags_users = len(legacy_rows)

    result["migrated_legacy_paid_flag_users"] = int(migrated_legacy_users)
    result["cleared_legacy_paid_flag_users"] = int(cleared_legacy_flags_users)

    revoked_privilege = await db.users.update_many(
        {
            **non_admin_selector,
            "$or": [
                {"full_access": True},
                {"subscription_permanent": True},
                {"premium_access": True},
            ],
        },
        {
            "$set": {
                "full_access": False,
                "subscription_permanent": False,
                "premium_access": False,
                "updated_at": now_iso,
            },
            "$inc": {"token_version": 1},
        },
    )

    unverified_paid = await db.users.update_many(
        {
            **non_admin_selector,
            "subscription_plan": {"$in": ["basic", "premium"]},
            "payment_verified": {"$ne": True},
        },
        {
            "$set": {
                "subscription_plan": "free",
                "subscription_status": "expired",
                "updated_at": now_iso,
            },
            "$inc": {"token_version": 1},
        },
    )

    realtime_counts = {
        "non_admin_basic": await db.users.count_documents({**non_admin_selector, "subscription_plan": "basic"}),
        "non_admin_premium": await db.users.count_documents({**non_admin_selector, "subscription_plan": "premium"}),
        "non_admin_full_access": await db.users.count_documents({**non_admin_selector, "full_access": True}),
        "non_admin_subscription_permanent": await db.users.count_documents({**non_admin_selector, "subscription_permanent": True}),
        "non_admin_paid_without_payment_verified": await db.users.count_documents(
            {**non_admin_selector, "subscription_plan": {"$in": ["basic", "premium"]}, "payment_verified": {"$ne": True}}
        ),
    }

    result.update(
        {
            "revoked_non_admin_privileged_flags": int(revoked_privilege.modified_count),
            "downgraded_non_admin_unverified_paid": int(unverified_paid.modified_count),
            "post_enforcement_counts": realtime_counts,
            "finished_at": _iso_now(),
        }
    )

    run_id = f"globenf_{uuid.uuid4().hex[:12]}"
    result["run_id"] = run_id
    await db.global_rbac_subscription_enforcement_runs.insert_one({
        "run_id": run_id,
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
        **result,
    })
    await append_access_ledger(
        event_type="global_rbac_subscription_enforcement",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        metadata=result,
    )
    return result