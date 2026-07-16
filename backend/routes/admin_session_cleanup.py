"""Admin Session Cleanup Policies — automated session revocation rules."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
import uuid
import logging
from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/session-policies", tags=["Session Cleanup Policies"])


@router.get("")
async def list_policies(request: Request):
    """List all session cleanup policies."""
    await require_admin(request)
    policies = await db.session_cleanup_policies.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"policies": policies}


@router.post("")
async def create_policy(request: Request):
    """Create a new session cleanup policy."""
    await require_admin(request)
    body = await request.json()
    name = body.get("name", "").strip()
    rule_type = body.get("rule_type")  # max_age_days, max_sessions_per_user, inactive_days
    threshold = body.get("threshold")
    enabled = body.get("enabled", True)

    if not name or not rule_type or threshold is None:
        return JSONResponse({"detail": "name, rule_type, and threshold are required"}, status_code=400)
    if rule_type not in ("max_age_days", "max_sessions_per_user", "inactive_days"):
        return JSONResponse(
            {"detail": "rule_type must be max_age_days, max_sessions_per_user, or inactive_days"}, status_code=400
        )
    try:
        threshold = int(threshold)
        if threshold < 1:
            raise ValueError
    except (ValueError, TypeError):
        return JSONResponse({"detail": "threshold must be a positive integer"}, status_code=400)

    policy = {
        "policy_id": f"pol_{uuid.uuid4().hex[:12]}",
        "name": name,
        "rule_type": rule_type,
        "threshold": threshold,
        "enabled": enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "last_run_deleted": 0,
    }
    await db.session_cleanup_policies.insert_one({**policy, "_id": policy["policy_id"]})
    return policy


@router.put("/{policy_id}")
async def update_policy(request: Request, policy_id: str):
    """Update an existing policy."""
    await require_admin(request)
    body = await request.json()
    updates = {}
    if "name" in body:
        updates["name"] = body["name"].strip()
    if "threshold" in body:
        try:
            updates["threshold"] = int(body["threshold"])
        except (ValueError, TypeError):
            return JSONResponse({"detail": "threshold must be a positive integer"}, status_code=400)
    if "enabled" in body:
        updates["enabled"] = bool(body["enabled"])

    if not updates:
        return JSONResponse({"detail": "No fields to update"}, status_code=400)

    result = await db.session_cleanup_policies.update_one({"policy_id": policy_id}, {"$set": updates})
    if result.matched_count == 0:
        return JSONResponse({"detail": "Policy not found"}, status_code=404)
    updated = await db.session_cleanup_policies.find_one({"policy_id": policy_id}, {"_id": 0})
    return updated


@router.delete("/{policy_id}")
async def delete_policy(request: Request, policy_id: str):
    """Delete a policy."""
    await require_admin(request)
    result = await db.session_cleanup_policies.delete_one({"policy_id": policy_id})
    if result.deleted_count == 0:
        return JSONResponse({"detail": "Policy not found"}, status_code=404)
    return {"status": "deleted", "policy_id": policy_id}


@router.post("/{policy_id}/run")
async def run_policy_now(request: Request, policy_id: str):
    """Manually trigger a policy execution."""
    await require_admin(request)
    policy = await db.session_cleanup_policies.find_one({"policy_id": policy_id}, {"_id": 0})
    if not policy:
        return JSONResponse({"detail": "Policy not found"}, status_code=404)
    deleted = await _execute_policy(policy)
    return {"status": "executed", "policy_id": policy_id, "deleted": deleted}


@router.get("/history")
async def cleanup_history(request: Request, limit: int = 20):
    """Get cleanup execution history."""
    await require_admin(request)
    history = await db.session_cleanup_history.find({}, {"_id": 0}).sort("executed_at", -1).limit(limit).to_list(limit)
    return {"history": history}


async def _execute_policy(policy: dict) -> int:
    """Execute a single cleanup policy. Returns number of deleted sessions."""
    rule_type = policy["rule_type"]
    threshold = policy["threshold"]
    now = datetime.now(timezone.utc)
    deleted = 0

    try:
        if rule_type == "max_age_days":
            cutoff = (now - timedelta(days=threshold)).isoformat()
            result = await db.user_sessions.delete_many({"created_at": {"$lt": cutoff}})
            # Also try datetime objects
            cutoff_dt = now - timedelta(days=threshold)
            result2 = await db.user_sessions.delete_many({"created_at": {"$lt": cutoff_dt}})
            deleted = result.deleted_count + result2.deleted_count

        elif rule_type == "max_sessions_per_user":
            pipeline = [
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": threshold}}},
            ]
            over_limit = await db.user_sessions.aggregate(pipeline).to_list(1000)
            for user_doc in over_limit:
                uid = user_doc["_id"]
                excess = user_doc["count"] - threshold
                oldest = (
                    await db.user_sessions.find({"user_id": uid}).sort("created_at", 1).limit(excess).to_list(excess)
                )
                if oldest:
                    tokens = [s.get("session_token") for s in oldest if s.get("session_token")]
                    if tokens:
                        r = await db.user_sessions.delete_many({"session_token": {"$in": tokens}})
                        deleted += r.deleted_count

        elif rule_type == "inactive_days":
            cutoff = (now - timedelta(days=threshold)).isoformat()
            result = await db.user_sessions.delete_many({"last_active": {"$lt": cutoff}})
            cutoff_dt = now - timedelta(days=threshold)
            result2 = await db.user_sessions.delete_many({"last_active": {"$lt": cutoff_dt}})
            deleted = result.deleted_count + result2.deleted_count

    except Exception as e:
        logger.error(f"Policy execution error ({policy.get('policy_id')}): {e}")

    # Update policy and log history
    await db.session_cleanup_policies.update_one(
        {"policy_id": policy["policy_id"]},
        {"$set": {"last_run": now.isoformat(), "last_run_deleted": deleted}},
    )
    await db.session_cleanup_history.insert_one(
        {
            "policy_id": policy["policy_id"],
            "policy_name": policy.get("name", ""),
            "rule_type": rule_type,
            "threshold": threshold,
            "deleted": deleted,
            "executed_at": now.isoformat(),
        }
    )
    logger.info(f"Session cleanup policy '{policy.get('name')}' executed: {deleted} sessions deleted")
    return deleted


async def run_all_enabled_policies():
    """Run all enabled cleanup policies. Called by scheduler."""
    policies = await db.session_cleanup_policies.find({"enabled": True}, {"_id": 0}).to_list(50)
    total_deleted = 0
    for policy in policies:
        deleted = await _execute_policy(policy)
        total_deleted += deleted
    if total_deleted > 0:
        logger.info(
            f"Session cleanup scheduler: {total_deleted} total sessions deleted across {len(policies)} policies"
        )
    return total_deleted
