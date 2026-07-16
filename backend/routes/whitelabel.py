"""White-Label Configuration System.

Organization branding, feature toggles, theme overrides, tenant isolation.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

from .db import db, require_auth

router = APIRouter(prefix="/whitelabel")
logger = logging.getLogger("routes.whitelabel")

DEFAULT_CONFIG = {
    "company_name": "RealAICoach",
    "logo_url": "",
    "favicon_url": "",
    "primary_color": "#3B82F6",
    "secondary_color": "#6366F1",
    "accent_color": "#10B981",
    "dark_bg": "#0B0F1A",
    "dark_card": "#111827",
    "font_family": "system-ui",
    "custom_domain": "",
    "support_email": "",
    "privacy_url": "",
    "terms_url": "",
    "feature_toggles": {
        "hiring_hub": True,
        "mini_apps": True,
        "leaderboard": True,
        "book_meeting": True,
        "employer_portal": True,
        "ai_coaching": True,
        "video_interviews": True,
        "analytics": True,
        "notifications": True,
    },
    "custom_css": "",
    "welcome_message": "",
    "footer_text": "",
}


async def _require_admin(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/config")
async def get_whitelabel_config(request: Request):
    """Get the current white-label configuration."""
    # Public endpoint - used by frontend to load branding
    config = await db.whitelabel_config.find_one({"active": True}, {"_id": 0})
    if not config:
        return {**DEFAULT_CONFIG, "is_default": True}
    config.pop("active", None)
    return {**config, "is_default": False}


@router.get("/config/admin")
async def get_admin_config(request: Request):
    """Get full white-label config for admin editing."""
    await _require_admin(request)
    config = await db.whitelabel_config.find_one({"active": True}, {"_id": 0})
    if not config:
        return {**DEFAULT_CONFIG, "config_id": None, "is_default": True}
    return config


@router.post("/config")
async def update_whitelabel_config(request: Request):
    """Update white-label configuration (admin only)."""
    admin = await _require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    # Merge with defaults
    existing = await db.whitelabel_config.find_one({"active": True}, {"_id": 0})
    if existing:
        config = {**existing, **body}
    else:
        config = {**DEFAULT_CONFIG, **body}

    config["active"] = True
    config["updated_at"] = now
    config["updated_by"] = admin.user_id

    if not config.get("config_id"):
        config["config_id"] = f"wl_{uuid.uuid4().hex[:12]}"
        config["created_at"] = now

    await db.whitelabel_config.update_one(
        {"active": True},
        {"$set": config},
        upsert=True,
    )
    config.pop("_id", None)

    # Log change
    await db.whitelabel_audit.insert_one(
        {
            "audit_id": f"wla_{uuid.uuid4().hex[:10]}",
            "config_id": config["config_id"],
            "changed_by": admin.user_id,
            "changes": body,
            "created_at": now,
        }
    )

    return {"success": True, "config": config}


@router.get("/feature-toggles")
async def get_feature_toggles(request: Request):
    """Get feature toggles (public - used by frontend for conditional rendering)."""
    config = await db.whitelabel_config.find_one({"active": True}, {"_id": 0, "feature_toggles": 1})
    if not config or not config.get("feature_toggles"):
        return DEFAULT_CONFIG["feature_toggles"]
    return config["feature_toggles"]


@router.post("/feature-toggles")
async def update_feature_toggles(request: Request):
    """Update feature toggles (admin only)."""
    admin = await _require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    await db.whitelabel_config.update_one(
        {"active": True},
        {"$set": {"feature_toggles": body, "updated_at": now, "updated_by": admin.user_id}},
        upsert=True,
    )

    return {"success": True, "feature_toggles": body}


@router.get("/organizations")
async def list_organizations(request: Request):
    """List all organizations (admin only)."""
    await _require_admin(request)
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"organizations": orgs, "total": len(orgs)}


@router.post("/organizations")
async def create_organization(request: Request):
    """Create a new organization."""
    admin = await _require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    org = {
        "org_id": f"org_{uuid.uuid4().hex[:12]}",
        "name": body.get("name", ""),
        "domain": body.get("domain", ""),
        "logo_url": body.get("logo_url", ""),
        "primary_color": body.get("primary_color", "#3B82F6"),
        "plan": body.get("plan", "enterprise"),
        "max_users": body.get("max_users", 50),
        "feature_overrides": body.get("feature_overrides", {}),
        "status": "active",
        "created_by": admin.user_id,
        "created_at": now,
    }
    await db.organizations.insert_one(org)
    org.pop("_id", None)

    return {"success": True, "organization": org}


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str, request: Request):
    """Get organization details."""
    await _require_admin(request)
    org = await db.organizations.find_one({"org_id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Count members
    members = await db.users.count_documents({"org_id": org_id})
    org["member_count"] = members

    return org


@router.put("/organizations/{org_id}")
async def update_organization(org_id: str, request: Request):
    """Update organization settings."""
    await _require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    update = {k: v for k, v in body.items() if k not in ("org_id", "_id")}
    update["updated_at"] = now

    result = await db.organizations.update_one({"org_id": org_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {"success": True, "updated_fields": list(update.keys())}


@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 20):
    """Get white-label configuration change audit log."""
    await _require_admin(request)
    logs = await db.whitelabel_audit.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

    # Enrich with user names
    for log in logs:
        user = await db.users.find_one({"user_id": log.get("changed_by")}, {"_id": 0, "name": 1})
        log["changed_by_name"] = user.get("name", "Unknown") if user else "Unknown"

    return {"logs": logs}
