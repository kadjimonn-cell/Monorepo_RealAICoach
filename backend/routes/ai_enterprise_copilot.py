"""Business Operations Copilot (Feature 18) — enterprise workspace APIs."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes.db import User, db, get_current_user
from utils.access_control_engine import compute_effective_plan
from utils.llm_helper import generate_verified_text

router = APIRouter(prefix="/ai-enterprise", tags=["Business Operations Copilot"])
logger = logging.getLogger("routes.ai_enterprise_copilot")

FEATURE_ID = "ai-enterprise"
FEATURE_NAME = "Business Operations Copilot"
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

COLL_WORKSPACES = "ai_enterprise_workspaces"
COLL_RUNS = "ai_enterprise_runs"
COLL_PLAYBOOKS = "ai_enterprise_playbooks"
COLL_USAGE = "ai_enterprise_daily_usage"
COLL_IDEMPOTENCY = "ai_enterprise_idempotency"

TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {
        "workspaces_per_month": 1,
        "runs_per_day": 2,
        "playbooks": 2,
        "exports_per_day": 1,
        "max_prompt_chars": 1200,
        "history_retention_days": 14,
    },
    "basic": {
        "workspaces_per_month": 15,
        "runs_per_day": 80,
        "playbooks": 40,
        "exports_per_day": 20,
        "max_prompt_chars": 5000,
        "history_retention_days": 120,
    },
    "premium": {
        "workspaces_per_month": -1,
        "runs_per_day": -1,
        "playbooks": -1,
        "exports_per_day": -1,
        "max_prompt_chars": 12000,
        "history_retention_days": -1,
    },
    "admin": {
        "workspaces_per_month": -1,
        "runs_per_day": -1,
        "playbooks": -1,
        "exports_per_day": -1,
        "max_prompt_chars": 12000,
        "history_retention_days": -1,
    },
    "enterprise": {
        "workspaces_per_month": -1,
        "runs_per_day": -1,
        "playbooks": -1,
        "exports_per_day": -1,
        "max_prompt_chars": 12000,
        "history_retention_days": -1,
    },
}


class WorkspaceCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    context: Optional[str] = Field(default=None, max_length=1200)
    focus: Optional[str] = Field(default="operations", max_length=80)
    fallback_user_id: Optional[str] = None


class EnterpriseRunRequest(BaseModel):
    command: str = Field(min_length=3, max_length=12000)
    objective: Optional[str] = Field(default=None, max_length=240)
    session_id: Optional[str] = Field(default=None, max_length=120)
    idempotency_key: Optional[str] = Field(default=None, max_length=120)
    fallback_user_id: Optional[str] = None


class PlaybookSaveRequest(BaseModel):
    workspace_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=3, max_length=100)
    summary: str = Field(min_length=3, max_length=2500)
    actions: list[str] = Field(default_factory=list)
    fallback_user_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _scope_label(plan: str) -> str:
    if plan in {"premium", "admin", "enterprise"}:
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


def _required_upgrade_plan(plan: str) -> str:
    if plan == "free":
        return "basic"
    if plan == "basic":
        return "premium"
    return "premium"


def _normalize_idempotency_key(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9._-]", "", raw)[:100]


def _resolve_owner_id(user: Optional[User], fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{user.user_id}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "ai_enterprise_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "ai_enterprise_auth_required",
            "message": "Login required or provide fallback_user_id for guest access",
        },
    )


async def _get_current_user_or_none(request: Request) -> Optional[User]:
    try:
        return await get_current_user(request)
    except HTTPException as exc:
        if int(exc.status_code) == 401:
            return None
        raise


def _tier_limits(plan: str) -> Dict[str, int]:
    return TIER_LIMITS.get(plan, TIER_LIMITS["free"])


async def _get_user_plan(user: Optional[User]) -> str:
    if not user:
        return "free"

    if bool(getattr(user, "is_admin", False)):
        return "premium"

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


async def _get_today_usage(owner_id: str) -> Dict[str, int]:
    row = await db[COLL_USAGE].find_one(
        {"owner_id": owner_id, "day_key": _today_key()},
        {"_id": 0, "usage": 1},
    )
    return (row or {}).get("usage") or {}


async def _track_usage(owner_id: str, plan: str, action_key: str) -> Dict[str, int]:
    now = _now_iso()
    await db[COLL_USAGE].update_one(
        {"owner_id": owner_id, "day_key": _today_key()},
        {
            "$set": {
                "owner_id": owner_id,
                "day_key": _today_key(),
                "plan": plan,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
            "$inc": {f"usage.{action_key}": 1},
        },
        upsert=True,
    )
    return await _get_today_usage(owner_id)


async def _month_workspace_count(owner_id: str) -> int:
    month_prefix = _month_key()
    return await db[COLL_WORKSPACES].count_documents(
        {
            "owner_id": owner_id,
            "created_at": {"$regex": f"^{month_prefix}"},
        }
    )


def _raise_limit(plan: str, current_usage: int, limit: int, error_code: str, message: str) -> None:
    raise HTTPException(
        status_code=429,
        detail={
            "error_code": error_code,
            "message": message,
            "current_usage": current_usage,
            "limit": limit,
            "current_plan": plan,
            "required_plan": _required_upgrade_plan(plan),
            "scope_label": _scope_label(plan),
        },
    )


def _check_limit(plan: str, current_usage: int, limit: int, error_code: str, message: str) -> None:
    if limit >= 0 and current_usage >= limit:
        _raise_limit(plan, current_usage, limit, error_code, message)


async def _require_workspace(owner_id: str, workspace_id: str) -> Dict[str, Any]:
    workspace = await db[COLL_WORKSPACES].find_one(
        {"workspace_id": workspace_id, "owner_id": owner_id},
        {"_id": 0},
    )
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ai_enterprise_workspace_not_found",
                "message": "Workspace not found",
            },
        )
    return workspace


def _build_history_filter(owner_id: str, plan: str) -> Dict[str, Any]:
    query: Dict[str, Any] = {"owner_id": owner_id}
    retention_days = int(_tier_limits(plan).get("history_retention_days", -1))
    if retention_days >= 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        query["created_at"] = {"$gte": cutoff}
    return query


async def _idempotency_replay(owner_id: str, endpoint: str, key: str) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    row = await db[COLL_IDEMPOTENCY].find_one(
        {
            "owner_id": owner_id,
            "endpoint": endpoint,
            "idempotency_key": key,
        },
        {"_id": 0, "response": 1},
    )
    if not row:
        return None
    replay = dict((row or {}).get("response") or {})
    if replay:
        replay["idempotent_replay"] = True
    return replay if replay else None


async def _save_idempotency(owner_id: str, endpoint: str, key: str, response: Dict[str, Any]) -> None:
    if not key:
        return
    now = _now_iso()
    await db[COLL_IDEMPOTENCY].update_one(
        {
            "owner_id": owner_id,
            "endpoint": endpoint,
            "idempotency_key": key,
        },
        {
            "$set": {
                "owner_id": owner_id,
                "endpoint": endpoint,
                "idempotency_key": key,
                "response": response,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def _sanitize_actions(actions: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in actions[:12]:
        text = str(item or "").strip()
        if text:
            cleaned.append(text[:220])
    return cleaned


def _build_export_filename(workspace_id: str, ext: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ai_enterprise_{workspace_id}_{stamp}.{ext}"


def _export_to_csv(workspace: Dict[str, Any], runs: list[Dict[str, Any]], playbooks: list[Dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["section", "item", "value"])

    writer.writerow(["workspace", "workspace_id", workspace.get("workspace_id", "")])
    writer.writerow(["workspace", "title", workspace.get("title", "")])
    writer.writerow(["workspace", "focus", workspace.get("focus", "")])
    writer.writerow(["workspace", "context", workspace.get("context", "") or ""])
    writer.writerow(["summary", "run_count", len(runs)])
    writer.writerow(["summary", "playbook_count", len(playbooks)])

    for run in runs:
        rid = str(run.get("run_id") or "")
        writer.writerow(["run", f"{rid}.created_at", run.get("created_at", "")])
        writer.writerow(["run", f"{rid}.session_id", run.get("session_id", "")])
        writer.writerow(["run", f"{rid}.objective", run.get("objective", "")])
        writer.writerow(["run", f"{rid}.command", run.get("command", "")])
        writer.writerow(["run", f"{rid}.output_excerpt", str(run.get("output", ""))[:300]])

    for playbook in playbooks:
        pid = str(playbook.get("playbook_id") or "")
        writer.writerow(["playbook", f"{pid}.name", playbook.get("name", "")])
        writer.writerow(["playbook", f"{pid}.summary", str(playbook.get("summary", ""))[:400]])
        writer.writerow(["playbook", f"{pid}.actions", " | ".join(playbook.get("actions") or [])])

    return stream.getvalue()


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy", "feature": FEATURE_NAME, "feature_id": FEATURE_ID}


@router.get("/bootstrap")
async def bootstrap(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    usage = await _get_today_usage(owner_id)

    workspaces = await (
        db[COLL_WORKSPACES]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(20)
        .to_list(length=20)
    )
    recent_runs = await (
        db[COLL_RUNS]
        .find(_build_history_filter(owner_id, plan), {"_id": 0})
        .sort("created_at", -1)
        .limit(12)
        .to_list(length=12)
    )
    playbooks = await (
        db[COLL_PLAYBOOKS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(20)
        .to_list(length=20)
    )

    return {
        "success": True,
        "feature_id": FEATURE_ID,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": limits,
        "usage": {
            "workspaces_this_month": await _month_workspace_count(owner_id),
            "runs_today": int(usage.get("runs", 0) or 0),
            "exports_today": int(usage.get("exports", 0) or 0),
            "playbooks_total": len(playbooks),
        },
        "workspaces": workspaces,
        "recent_runs": recent_runs,
        "playbooks": playbooks,
        "features": {
            "strategy_workspace": True,
            "command_mode": True,
            "run_timeline": True,
            "playbooks": True,
            "exports": True,
        },
    }


@router.post("/workspaces/create")
async def create_workspace(request: Request, payload: WorkspaceCreateRequest) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)

    workspace_count = await _month_workspace_count(owner_id)
    _check_limit(
        plan,
        workspace_count,
        int(limits.get("workspaces_per_month", -1)),
        "ai_enterprise_workspace_limit_reached",
        "Monthly workspace limit reached for current plan.",
    )

    now = _now_iso()
    workspace_id = f"aient_{uuid.uuid4().hex[:12]}"
    doc = {
        "workspace_id": workspace_id,
        "owner_id": owner_id,
        "title": payload.title.strip(),
        "context": (payload.context or "").strip() or None,
        "focus": (payload.focus or "operations").strip() or "operations",
        "run_count": 0,
        "last_output": None,
        "last_run_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db[COLL_WORKSPACES].insert_one(dict(doc))

    return {
        "success": True,
        "workspace": doc,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": limits,
    }


@router.post("/workspaces/{workspace_id}/run")
async def run_workspace_command(
    workspace_id: str,
    payload: EnterpriseRunRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    workspace = await _require_workspace(owner_id, workspace_id)

    idem = _normalize_idempotency_key(payload.idempotency_key)
    replay = await _idempotency_replay(owner_id, f"run:{workspace_id}", idem)
    if replay:
        return replay

    usage = await _get_today_usage(owner_id)
    _check_limit(
        plan,
        int(usage.get("runs", 0) or 0),
        int(limits.get("runs_per_day", -1)),
        "ai_enterprise_run_limit_reached",
        "Daily command run limit reached for current plan.",
    )

    command = payload.command.strip()
    max_prompt_chars = int(limits.get("max_prompt_chars", 1200))
    if max_prompt_chars >= 0 and len(command) > max_prompt_chars:
        raise HTTPException(
            status_code=413,
            detail={
                "error_code": "ai_enterprise_prompt_too_long",
                "message": f"Command exceeds plan limit of {max_prompt_chars} characters.",
                "current_plan": plan,
                "required_plan": _required_upgrade_plan(plan),
                "scope_label": _scope_label(plan),
            },
        )

    session_id = (payload.session_id or f"ai-enterprise-{uuid.uuid4().hex[:10]}").strip()[:120]
    objective = (payload.objective or "Operational growth, risk control, and execution clarity").strip()
    system_prompt = (
        "You are Business Operations Copilot. Produce concise enterprise outputs with these sections: "
        "(1) Executive Summary, (2) Objective Tree, (3) KPI Pack, (4) Risk Register, (5) 30/60/90 Plan. "
        "Use short bullets, concrete metrics, and practical next actions."
    )
    input_prompt = (
        f"Workspace: {workspace.get('title', 'Untitled')}\n"
        f"Focus: {workspace.get('focus', 'operations')}\n"
        f"Objective: {objective}\n"
        f"Context: {workspace.get('context') or 'N/A'}\n"
        f"Command: {command}"
    )

    try:
        output = await generate_verified_text(input_prompt, system_prompt, session_id)
    except Exception as exc:
        logger.error("Business Operations Copilot run failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "ai_enterprise_run_failed",
                "message": "Copilot execution failed. Please retry.",
            },
        )

    now = _now_iso()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run_doc = {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "owner_id": owner_id,
        "command": command,
        "objective": objective,
        "session_id": session_id,
        "output": output,
        "created_at": now,
    }
    await db[COLL_RUNS].insert_one(dict(run_doc))
    await db[COLL_WORKSPACES].update_one(
        {"workspace_id": workspace_id, "owner_id": owner_id},
        {
            "$set": {"last_output": output, "last_run_at": now, "updated_at": now},
            "$inc": {"run_count": 1},
        },
    )
    tracked_usage = await _track_usage(owner_id, plan, "runs")

    response = {
        "success": True,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "output": output,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": {
            "runs_today": int(tracked_usage.get("runs", 0) or 0),
        },
        "daily_limit": int(limits.get("runs_per_day", -1)),
        "idempotent_replay": False,
    }
    await _save_idempotency(owner_id, f"run:{workspace_id}", idem, response)
    return response


@router.get("/workspaces/{workspace_id}/runs")
async def list_workspace_runs(
    workspace_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    await _require_workspace(owner_id, workspace_id)

    runs = await (
        db[COLL_RUNS]
        .find({"owner_id": owner_id, "workspace_id": workspace_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return {"success": True, "runs": runs}


@router.post("/playbooks/save")
async def save_playbook(request: Request, payload: PlaybookSaveRequest) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    await _require_workspace(owner_id, payload.workspace_id)

    limits = _tier_limits(plan)
    total_playbooks = await db[COLL_PLAYBOOKS].count_documents({"owner_id": owner_id})
    _check_limit(
        plan,
        int(total_playbooks),
        int(limits.get("playbooks", -1)),
        "ai_enterprise_playbook_limit_reached",
        "Playbook limit reached for current plan.",
    )

    now = _now_iso()
    playbook_id = f"pb_{uuid.uuid4().hex[:12]}"
    doc = {
        "playbook_id": playbook_id,
        "workspace_id": payload.workspace_id,
        "owner_id": owner_id,
        "name": payload.name.strip(),
        "summary": payload.summary.strip(),
        "actions": _sanitize_actions(payload.actions),
        "created_at": now,
        "updated_at": now,
    }
    await db[COLL_PLAYBOOKS].insert_one(dict(doc))
    return {"success": True, "playbook": doc, "plan": plan, "scope_label": _scope_label(plan)}


@router.get("/playbooks")
async def list_playbooks(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    playbooks = await (
        db[COLL_PLAYBOOKS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return {"success": True, "playbooks": playbooks}


@router.get("/workspaces/{workspace_id}/export")
async def export_workspace(
    workspace_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    include_runs: bool = Query(default=True),
    include_playbooks: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    format: str = Query(default="payload"),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    workspace = await _require_workspace(owner_id, workspace_id)

    usage = await _get_today_usage(owner_id)
    export_limit = int(_tier_limits(plan).get("exports_per_day", -1))
    _check_limit(
        plan,
        int(usage.get("exports", 0) or 0),
        export_limit,
        "ai_enterprise_export_limit_reached",
        "Daily export limit reached for current plan.",
    )

    runs: list[Dict[str, Any]] = []
    if include_runs:
        runs = await (
            db[COLL_RUNS]
            .find({"owner_id": owner_id, "workspace_id": workspace_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )

    playbooks: list[Dict[str, Any]] = []
    if include_playbooks:
        playbooks = await (
            db[COLL_PLAYBOOKS]
            .find({"owner_id": owner_id, "workspace_id": workspace_id}, {"_id": 0})
            .sort("updated_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )

    tracked_usage = await _track_usage(owner_id, plan, "exports")
    export_id = f"exp_{uuid.uuid4().hex[:12]}"
    payload = {
        "success": True,
        "export_id": export_id,
        "workspace": workspace,
        "runs": runs,
        "playbooks": playbooks,
        "summary": {
            "run_count": len(runs),
            "playbook_count": len(playbooks),
        },
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": {
            "exports_today": int(tracked_usage.get("exports", 0) or 0),
        },
        "daily_limit": export_limit,
        "generated_at": _now_iso(),
    }

    fmt = str(format or "payload").strip().lower()
    if fmt == "payload":
        return payload

    if fmt == "json":
        filename = _build_export_filename(workspace_id, "json")
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        from fastapi.responses import Response

        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if fmt == "csv":
        filename = _build_export_filename(workspace_id, "csv")
        content = _export_to_csv(workspace, runs, playbooks)
        from fastapi.responses import Response

        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "ai_enterprise_invalid_export_format",
            "message": "format must be one of: payload, json, csv",
        },
    )