"""Advanced Team Management & Permissions.

Granular role-based permissions, team CRUD, invite system, audit trail.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

from .db import db, require_auth, require_admin

router = APIRouter(prefix="/teams")
logger = logging.getLogger("routes.team_management")

ROLES = {
    "owner": {"level": 100, "label": "Owner", "permissions": ["*"]},
    "admin": {
        "level": 80,
        "label": "Admin",
        "permissions": [
            "manage_members",
            "manage_settings",
            "view_analytics",
            "edit_docs",
            "manage_interviews",
            "manage_jobs",
        ],
    },
    "manager": {
        "level": 60,
        "label": "Manager",
        "permissions": ["view_analytics", "edit_docs", "manage_interviews", "manage_jobs"],
    },
    "member": {"level": 40, "label": "Member", "permissions": ["edit_docs", "manage_interviews"]},
    "viewer": {"level": 20, "label": "Viewer", "permissions": ["view_docs", "view_interviews"]},
}

ALL_PERMISSIONS = [
    {"id": "manage_members", "label": "Manage Members", "desc": "Add/remove team members and change roles"},
    {"id": "manage_settings", "label": "Manage Settings", "desc": "Edit team settings and branding"},
    {"id": "view_analytics", "label": "View Analytics", "desc": "Access revenue and usage analytics"},
    {"id": "edit_docs", "label": "Edit Documents", "desc": "Create and edit collaborative documents"},
    {"id": "manage_interviews", "label": "Manage Interviews", "desc": "Schedule and manage interviews"},
    {"id": "manage_jobs", "label": "Manage Jobs", "desc": "Create and edit job postings"},
    {"id": "view_docs", "label": "View Documents", "desc": "Read-only access to documents"},
    {"id": "view_interviews", "label": "View Interviews", "desc": "View interview schedules and results"},
]


@router.get("/roles")
async def list_roles(request: Request):
    """List available team roles and permissions."""
    await require_admin(request)
    roles = [{"id": rid, **r} for rid, r in ROLES.items()]
    return {"roles": roles, "permissions": ALL_PERMISSIONS}


@router.post("/")
async def create_team(request: Request):
    """Create a new team (admin only)."""
    user = await require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    team = {
        "team_id": f"team_{uuid.uuid4().hex[:10]}",
        "name": body.get("name", "").strip(),
        "description": body.get("description", ""),
        "owner_id": user.user_id,
        "owner_name": user.name,
        "members": [
            {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "role": "owner",
                "joined_at": now,
                "invited_by": user.user_id,
            }
        ],
        "member_count": 1,
        "settings": {"allow_self_join": False, "require_approval": True},
        "created_at": now,
        "updated_at": now,
    }

    if not team["name"]:
        raise HTTPException(status_code=400, detail="Team name is required")

    await db.teams.insert_one(team)
    team.pop("_id", None)

    # Audit log
    await _audit("team_created", user, team["team_id"], {"name": team["name"]})

    return {"success": True, "team": team}


@router.get("/")
async def list_teams(request: Request):
    """List all teams (admin sees all, others see their own)."""
    await require_admin(request)
    teams = (
        await db.teams.find(
            {},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(100)
    )
    return {"teams": teams}


@router.get("/{team_id}")
async def get_team(team_id: str, request: Request):
    """Get team details with members (admin only)."""
    await require_admin(request)
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}")
async def update_team(team_id: str, request: Request):
    """Update team settings."""
    user = await require_auth(request)
    body = await request.json()

    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    member = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if not member or ROLES.get(member["role"], {}).get("level", 0) < 80:
        raise HTTPException(status_code=403, detail="Admin role required")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in body:
        update["name"] = body["name"]
    if "description" in body:
        update["description"] = body["description"]
    if "settings" in body:
        update["settings"] = body["settings"]

    await db.teams.update_one({"team_id": team_id}, {"$set": update})
    await _audit("team_updated", user, team_id, update)

    return {"success": True}


@router.post("/{team_id}/invite")
async def invite_member(team_id: str, request: Request):
    """Invite a user to the team."""
    user = await require_auth(request)
    body = await request.json()
    invitee_email = body.get("email", "").strip().lower()
    role = body.get("role", "member")

    if role not in ROLES or role == "owner":
        raise HTTPException(status_code=400, detail="Invalid role")

    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    member = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if (
        not member
        or "manage_members" not in ROLES.get(member["role"], {}).get("permissions", [])
        and "*" not in ROLES.get(member["role"], {}).get("permissions", [])
    ):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if already a member
    if any(m.get("email") == invitee_email for m in team["members"]):
        raise HTTPException(status_code=400, detail="User is already a member")

    # Find user by email
    invitee = await db.users.find_one({"email": invitee_email}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found with that email")

    now = datetime.now(timezone.utc).isoformat()
    new_member = {
        "user_id": invitee["user_id"],
        "name": invitee.get("name", ""),
        "email": invitee_email,
        "role": role,
        "joined_at": now,
        "invited_by": user.user_id,
    }

    await db.teams.update_one(
        {"team_id": team_id},
        {"$push": {"members": new_member}, "$inc": {"member_count": 1}, "$set": {"updated_at": now}},
    )
    await _audit("member_invited", user, team_id, {"invitee": invitee_email, "role": role})

    # Send team invite notification
    try:
        from routes.notification_engine import emit_team_invite

        inviter_name = user.name if hasattr(user, "name") else "A team admin"
        await emit_team_invite(invitee["user_id"], inviter_name, team.get("name", "a team"), role)
    except Exception as e:
        logger.error(f"Team invite notification failed: {e}")

    return {"success": True, "member": new_member}


@router.put("/{team_id}/members/{member_id}/role")
async def change_role(team_id: str, member_id: str, request: Request):
    """Change a team member's role."""
    user = await require_auth(request)
    body = await request.json()
    new_role = body.get("role", "")

    if new_role not in ROLES or new_role == "owner":
        raise HTTPException(status_code=400, detail="Invalid role")

    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    actor = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if not actor or ROLES.get(actor["role"], {}).get("level", 0) < 80:
        raise HTTPException(status_code=403, detail="Admin role required")

    target = next((m for m in team["members"] if m["user_id"] == member_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.teams.update_one(
        {"team_id": team_id, "members.user_id": member_id},
        {"$set": {"members.$.role": new_role, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await _audit("role_changed", user, team_id, {"member": member_id, "old_role": target["role"], "new_role": new_role})

    return {"success": True}


@router.delete("/{team_id}/members/{member_id}")
async def remove_member(team_id: str, member_id: str, request: Request):
    """Remove a member from the team."""
    user = await require_auth(request)

    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    actor = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    is_self = member_id == user.user_id
    if not is_self and (
        not actor
        or "manage_members" not in ROLES.get(actor["role"], {}).get("permissions", [])
        and "*" not in ROLES.get(actor["role"], {}).get("permissions", [])
    ):
        raise HTTPException(status_code=403, detail="Permission denied")

    target = next((m for m in team["members"] if m["user_id"] == member_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target["role"] == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove team owner")

    now = datetime.now(timezone.utc).isoformat()
    await db.teams.update_one(
        {"team_id": team_id},
        {"$pull": {"members": {"user_id": member_id}}, "$inc": {"member_count": -1}, "$set": {"updated_at": now}},
    )
    await _audit("member_removed", user, team_id, {"member": member_id})

    return {"success": True}


@router.get("/{team_id}/audit")
async def get_audit_log(team_id: str, request: Request):
    """Get team audit log."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id, "members.user_id": user.user_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    logs = await db.team_audit.find({"team_id": team_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"audit_logs": logs}


@router.delete("/{team_id}")
async def delete_team(team_id: str, request: Request):
    """Delete a team (owner only)."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only owner can delete team")

    await db.teams.delete_one({"team_id": team_id})
    await db.team_audit.delete_many({"team_id": team_id})
    await db.custom_roles.delete_many({"team_id": team_id})
    return {"success": True}


# ── Custom Roles ──────────────────────────────────────────────


@router.get("/{team_id}/custom-roles")
async def list_custom_roles(team_id: str, request: Request):
    """List custom roles for a team."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id, "members.user_id": user.user_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    roles = await db.custom_roles.find({"team_id": team_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {
        "custom_roles": roles,
        "builtin_roles": [{"id": rid, **r} for rid, r in ROLES.items()],
        "all_permissions": ALL_PERMISSIONS,
    }


@router.post("/{team_id}/custom-roles")
async def create_custom_role(team_id: str, request: Request):
    """Create a custom role for a team."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    actor = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if not actor or actor["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can create custom roles")

    body = await request.json()
    name = body.get("name", "").strip()
    permissions = body.get("permissions", [])
    level = body.get("level", 50)
    color = body.get("color", "#6B7280")

    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if name.lower() in ROLES:
        raise HTTPException(status_code=400, detail="Cannot use a built-in role name")

    # Check for duplicates in team
    existing = await db.custom_roles.find_one({"team_id": team_id, "name_lower": name.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A custom role with this name already exists")

    valid_perms = [p["id"] for p in ALL_PERMISSIONS]
    permissions = [p for p in permissions if p in valid_perms]

    now = datetime.now(timezone.utc).isoformat()
    role = {
        "role_id": f"role_{uuid.uuid4().hex[:10]}",
        "team_id": team_id,
        "name": name,
        "name_lower": name.lower(),
        "label": name,
        "level": min(max(int(level), 10), 90),
        "permissions": permissions,
        "color": color,
        "created_by": user.user_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.custom_roles.insert_one(role)
    role.pop("_id", None)
    await _audit("custom_role_created", user, team_id, {"role_name": name, "permissions": permissions})
    return {"success": True, "role": role}


@router.put("/{team_id}/custom-roles/{role_id}")
async def update_custom_role(team_id: str, role_id: str, request: Request):
    """Update a custom role."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    actor = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if not actor or actor["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can edit custom roles")

    role = await db.custom_roles.find_one({"role_id": role_id, "team_id": team_id})
    if not role:
        raise HTTPException(status_code=404, detail="Custom role not found")

    body = await request.json()
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in body and body["name"].strip():
        new_name = body["name"].strip()
        if new_name.lower() in ROLES:
            raise HTTPException(status_code=400, detail="Cannot use a built-in role name")
        updates["name"] = new_name
        updates["name_lower"] = new_name.lower()
        updates["label"] = new_name
    if "permissions" in body:
        valid_perms = [p["id"] for p in ALL_PERMISSIONS]
        updates["permissions"] = [p for p in body["permissions"] if p in valid_perms]
    if "level" in body:
        updates["level"] = min(max(int(body["level"]), 10), 90)
    if "color" in body:
        updates["color"] = body["color"]

    await db.custom_roles.update_one({"role_id": role_id}, {"$set": updates})
    await _audit("custom_role_updated", user, team_id, {"role_id": role_id, "updates": list(updates.keys())})
    updated = await db.custom_roles.find_one({"role_id": role_id}, {"_id": 0})
    return {"success": True, "role": updated}


@router.delete("/{team_id}/custom-roles/{role_id}")
async def delete_custom_role(team_id: str, role_id: str, request: Request):
    """Delete a custom role."""
    user = await require_auth(request)
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    actor = next((m for m in team["members"] if m["user_id"] == user.user_id), None)
    if not actor or actor["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete custom roles")

    role = await db.custom_roles.find_one({"role_id": role_id, "team_id": team_id})
    if not role:
        raise HTTPException(status_code=404, detail="Custom role not found")

    # Check if any members are using this role
    members_using = [m for m in team["members"] if m.get("role") == role["name_lower"]]
    if members_using:
        raise HTTPException(
            status_code=400, detail=f"{len(members_using)} member(s) still using this role. Reassign them first."
        )

    await db.custom_roles.delete_one({"role_id": role_id})
    await _audit("custom_role_deleted", user, team_id, {"role_name": role["name"]})
    return {"success": True}


# ── Enterprise Team Stats ──────────────────────────────────


@router.get("/admin/stats")
async def team_admin_stats(request: Request):
    """Admin overview: aggregated team metrics."""
    await require_admin(request)
    total_teams = await db.teams.count_documents({})
    total_members = 0
    role_distribution: dict = {}
    async for team in db.teams.find({}, {"_id": 0, "members": 1}):
        members = team.get("members", [])
        total_members += len(members)
        for m in members:
            role = m.get("role", "unknown")
            role_distribution[role] = role_distribution.get(role, 0) + 1

    recent_audit = await db.team_audit.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    custom_roles_count = await db.custom_roles.count_documents({})

    return {
        "total_teams": total_teams,
        "total_members": total_members,
        "role_distribution": role_distribution,
        "custom_roles": custom_roles_count,
        "recent_activity": recent_audit,
    }


@router.post("/{team_id}/bulk-invite")
async def bulk_invite_members(team_id: str, request: Request):
    """Invite multiple members at once (admin only)."""
    user = await require_admin(request)
    body = await request.json()
    invites = body.get("invites", [])  # [{email, role}]

    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    results = {"success": [], "failed": []}
    now = datetime.now(timezone.utc).isoformat()

    for inv in invites[:50]:
        email = inv.get("email", "").strip().lower()
        role = inv.get("role", "member")
        if role not in ROLES or role == "owner":
            results["failed"].append({"email": email, "reason": "Invalid role"})
            continue
        if any(m.get("email") == email for m in team["members"]):
            results["failed"].append({"email": email, "reason": "Already a member"})
            continue
        invitee = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})
        if not invitee:
            results["failed"].append({"email": email, "reason": "User not found"})
            continue

        new_member = {
            "user_id": invitee["user_id"],
            "name": invitee.get("name", ""),
            "email": email,
            "role": role,
            "joined_at": now,
            "invited_by": user.user_id,
        }
        await db.teams.update_one(
            {"team_id": team_id},
            {"$push": {"members": new_member}, "$inc": {"member_count": 1}, "$set": {"updated_at": now}},
        )
        results["success"].append({"email": email, "role": role})

        # Send notification to invitee
        try:
            from utils.notification_helper import create_notification

            await create_notification(
                invitee["user_id"],
                f"Team Invitation: {team['name']}",
                f'You\'ve been added to team "{team["name"]}" as {role}.',
                "team_invite",
            )
        except Exception:
            pass

    await _audit("bulk_invite", user, team_id, {"invited": len(results["success"]), "failed": len(results["failed"])})
    return results


@router.put("/{team_id}/department")
async def update_department(team_id: str, request: Request):
    """Set team department and hierarchy (admin only)."""
    user = await require_admin(request)
    body = await request.json()
    team = await db.teams.find_one({"team_id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "department" in body:
        updates["department"] = body["department"]
    if "parent_team_id" in body:
        updates["parent_team_id"] = body["parent_team_id"]
    if "tags" in body:
        updates["tags"] = body["tags"][:10]

    await db.teams.update_one({"team_id": team_id}, {"$set": updates})
    await _audit("department_updated", user, team_id, updates)
    return {"success": True}


async def _audit(action: str, user, team_id: str, details: dict):
    now = datetime.now(timezone.utc).isoformat()
    await db.team_audit.insert_one(
        {
            "audit_id": f"audit_{uuid.uuid4().hex[:10]}",
            "team_id": team_id,
            "action": action,
            "user_id": user.user_id,
            "user_name": user.name,
            "details": details,
            "created_at": now,
        }
    )
    # Broadcast real-time team event to all team members via WebSocket
    try:
        from utils.ws_manager import ws_manager

        team = await db.teams.find_one({"team_id": team_id}, {"_id": 0, "members": 1, "name": 1})
        if team:
            event_payload = {
                "type": "team_event",
                "action": action,
                "team_id": team_id,
                "team_name": team.get("name", ""),
                "actor_name": user.name,
                "details": details,
                "timestamp": now,
            }
            for m in team.get("members", []):
                if m["user_id"] != user.user_id:
                    await ws_manager.send_to_user(m["user_id"], event_payload)
    except Exception:
        pass
