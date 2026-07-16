"""
Terms of Service — Versioning, Acceptance & Admin Management
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from routes.db import db, get_current_user, require_admin, require_auth

router = APIRouter(tags=["Terms of Service"])

# ── Helpers ──
async def _get_active_tos():
    """Return the currently published TOS version, or None."""
    return await db.tos_versions.find_one(
        {"status": "published"},
        {"_id": 0},
        sort=[("published_at", -1)],
    )


# ── Public ──
@router.get("/tos/current")
async def get_current_tos():
    """Public: return the current active Terms of Service."""
    tos = await _get_active_tos()
    if not tos:
        return {"tos": None}
    return {"tos": tos}


# ── Authenticated User ──
@router.get("/tos/acceptance-status")
async def tos_acceptance_status(request: Request):
    """Check whether the logged-in user has accepted the latest TOS."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tos = await _get_active_tos()
    if not tos:
        # No TOS published yet — nothing to accept
        return {"accepted": True, "tos_version_id": None, "reason": "no_tos_published"}

    acceptance = await db.tos_acceptances.find_one(
        {"user_id": user.user_id, "version_id": tos["version_id"]},
        {"_id": 0},
    )
    if acceptance:
        return {"accepted": True, "tos_version_id": tos["version_id"], "accepted_at": acceptance["accepted_at"]}

    return {
        "accepted": False,
        "tos_version_id": tos["version_id"],
        "tos_version_number": tos["version_number"],
        "tos_title": tos.get("title", "Terms of Service"),
        "tos_summary": tos.get("change_summary", ""),
    }


@router.post("/tos/accept")
async def accept_tos(request: Request):
    """User accepts the current TOS version."""
    user = await require_auth(request)
    tos = await _get_active_tos()
    if not tos:
        raise HTTPException(status_code=404, detail="No active Terms of Service to accept")

    version_id = tos["version_id"]

    # Idempotent — skip if already accepted
    existing = await db.tos_acceptances.find_one(
        {"user_id": user.user_id, "version_id": version_id}
    )
    if existing:
        return {"ok": True, "already_accepted": True}

    await db.tos_acceptances.insert_one({
        "user_id": user.user_id,
        "email": user.email,
        "version_id": version_id,
        "version_number": tos["version_number"],
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"ok": True, "version_id": version_id}


@router.get("/tos/acceptance-history")
async def tos_acceptance_history(request: Request):
    """User views their own TOS acceptance history."""
    user = await require_auth(request)
    records = await db.tos_acceptances.find(
        {"user_id": user.user_id},
        {"_id": 0},
    ).sort("accepted_at", -1).to_list(50)
    return {"history": records}


# ── Admin ──
@router.get("/admin/tos/versions")
async def admin_list_tos_versions(request: Request):
    """Admin: list all TOS versions (newest first)."""
    await require_admin(request)
    versions = await db.tos_versions.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"versions": versions}


@router.post("/admin/tos/versions")
async def admin_create_tos_version(request: Request):
    """Admin: create a new TOS version (starts as 'draft')."""
    admin = await require_admin(request)
    body = await request.json()

    title = body.get("title", "Terms of Service")
    content_sections = body.get("content_sections", [])
    change_summary = body.get("change_summary", "")
    version_number = body.get("version_number", "")

    if not content_sections:
        raise HTTPException(status_code=400, detail="content_sections is required")
    if not version_number:
        raise HTTPException(status_code=400, detail="version_number is required (e.g. '2.0')")

    # Check version_number uniqueness
    existing = await db.tos_versions.find_one({"version_number": version_number})
    if existing:
        raise HTTPException(status_code=409, detail=f"Version {version_number} already exists")

    version_id = f"tos_{uuid.uuid4().hex[:12]}"
    doc = {
        "version_id": version_id,
        "version_number": version_number,
        "title": title,
        "content_sections": content_sections,
        "change_summary": change_summary,
        "status": "draft",
        "created_by": admin.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "published_at": None,
    }
    await db.tos_versions.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "version": doc}


@router.put("/admin/tos/versions/{version_id}")
async def admin_update_tos_version(version_id: str, request: Request):
    """Admin: update a draft TOS version."""
    await require_admin(request)
    body = await request.json()

    version = await db.tos_versions.find_one({"version_id": version_id}, {"_id": 0})
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if version["status"] == "published":
        raise HTTPException(status_code=400, detail="Cannot edit a published version. Create a new one.")

    updates = {}
    for field in ["title", "content_sections", "change_summary", "version_number"]:
        if field in body:
            updates[field] = body[field]

    if updates:
        await db.tos_versions.update_one({"version_id": version_id}, {"$set": updates})

    updated = await db.tos_versions.find_one({"version_id": version_id}, {"_id": 0})
    return {"ok": True, "version": updated}


@router.put("/admin/tos/versions/{version_id}/publish")
async def admin_publish_tos_version(version_id: str, request: Request):
    """Admin: publish a TOS version. This becomes the active version and all users must re-accept."""
    admin = await require_admin(request)

    version = await db.tos_versions.find_one({"version_id": version_id}, {"_id": 0})
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version["status"] == "published":
        return {"ok": True, "message": "Already published"}

    # Archive previously published versions
    await db.tos_versions.update_many(
        {"status": "published"},
        {"$set": {"status": "archived"}},
    )

    # Publish this one
    now = datetime.now(timezone.utc).isoformat()
    await db.tos_versions.update_one(
        {"version_id": version_id},
        {"$set": {"status": "published", "published_at": now, "published_by": admin.email}},
    )

    # Auto-broadcast terms_policy_update email to all users (non-blocking)
    import asyncio
    asyncio.ensure_future(_broadcast_tos_email(admin.email, version, now))

    return {"ok": True, "version_id": version_id, "published_at": now}


async def _broadcast_tos_email(admin_email: str, version: dict, published_at: str):
    """Background: send terms_policy_update email to all users & log broadcast."""
    try:
        from utils.email_service import send_catalog_template, is_email_configured
        if not is_email_configured():
            return

        users = await db.users.find(
            {"access_locked": {"$ne": True}, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(10000)

        effective = datetime.fromisoformat(published_at).strftime("%B %d, %Y")
        summary = version.get("change_summary", "Our Terms of Service have been updated.")
        policy_type = version.get("title", "Terms of Service")

        sent, failed = 0, 0
        for u in users:
            try:
                await send_catalog_template(
                    recipient_email=u["email"],
                    template_key="terms_policy_update",
                    recipient_name=u.get("name", ""),
                    user_name=u.get("name", "there"),
                    policy_type=policy_type,
                    effective_date=effective,
                    summary_of_changes=summary,
                    review_url="",
                )
                sent += 1
            except Exception:
                failed += 1

        await db.legal_notice_broadcasts.insert_one({
            "id": f"legal_{uuid.uuid4().hex[:12]}",
            "policy_type": policy_type,
            "effective_date": effective,
            "summary": summary,
            "sent_count": sent,
            "failed_count": failed,
            "total_users": len(users),
            "broadcast_by": admin_email,
            "broadcast_at": datetime.now(timezone.utc).isoformat(),
            "trigger": "tos_publish_auto",
            "tos_version_id": version.get("version_id"),
        })
    except Exception as e:
        import logging
        logging.getLogger("routes.tos").error(f"TOS email broadcast failed: {e}")


@router.get("/admin/tos/stats")
async def admin_tos_stats(request: Request):
    """Admin: acceptance statistics for the current TOS version."""
    await require_admin(request)

    tos = await _get_active_tos()
    if not tos:
        return {"active_version": None, "total_users": 0, "accepted_count": 0, "pending_count": 0, "acceptance_rate": 0}

    total_users = await db.users.count_documents({})
    accepted_count = await db.tos_acceptances.count_documents({"version_id": tos["version_id"]})
    pending_count = max(0, total_users - accepted_count)
    rate = round((accepted_count / total_users * 100), 1) if total_users > 0 else 0

    return {
        "active_version": {
            "version_id": tos["version_id"],
            "version_number": tos["version_number"],
            "title": tos.get("title", "Terms of Service"),
            "published_at": tos.get("published_at"),
        },
        "total_users": total_users,
        "accepted_count": accepted_count,
        "pending_count": pending_count,
        "acceptance_rate": rate,
    }
