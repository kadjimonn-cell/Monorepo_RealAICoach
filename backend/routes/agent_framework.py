"""Admin API for the native AI Agent Framework. All endpoints require admin."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .db import db, require_admin
from agent_framework import agents as agents_svc
from agent_framework import marketplace as marketplace_svc
from agent_framework import prompts as prompts_svc
from agent_framework import policy as policy_svc
from agent_framework.audit import log_audit
from agent_framework.engine import start_execution, resume_execution, validate_workflow_steps, count_steps
from agent_framework.providers import provider_registry
from agent_framework.tools import tool_registry

router = APIRouter(prefix="/agent-framework")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Models ──

class AgentUpsert(BaseModel):
    agent_key: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    role: str = ""
    category: str = ""
    subcategory: str = ""
    description: str = ""
    system_prompt: str = Field(..., min_length=1)
    provider: str = "openai"
    model: str = "gpt-4o"
    allowed_tools: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    feature_mappings: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=lambda: ["llm.complete"])
    availability: str = "global"
    status: str = "active"
    dependencies: List[str] = Field(default_factory=list)
    config_profile: Dict[str, Any] = Field(default_factory=lambda: {"temperature": 0.4, "max_tokens": 1400})
    enabled: bool = True


class AgentExecuteRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=20000)
    session_id: Optional[str] = None
    timeout_seconds: Optional[float] = None


class PromptUpsert(BaseModel):
    prompt_key: str = Field(..., min_length=2, max_length=80)
    name: str = ""
    description: str = ""
    template: str = Field(..., min_length=1)
    variables: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class PromptRenderRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)


class WorkflowUpsert(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True


class WorkflowExecuteRequest(BaseModel):
    input: str = Field(default="", max_length=20000)


class ApprovalRequest(BaseModel):
    note: str = ""


class PolicyUpdate(BaseModel):
    changes: Dict[str, Any] = Field(default_factory=dict)


class CloneRequest(BaseModel):
    new_key: str = Field(..., min_length=2, max_length=80)
    new_name: str = ""


class ExportRequest(BaseModel):
    agent_keys: Optional[List[str]] = None


class ImportRequest(BaseModel):
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    overwrite: bool = False


class BulkUpdateRequest(BaseModel):
    agent_keys: List[str] = Field(..., min_length=1)
    changes: Dict[str, Any] = Field(default_factory=dict)


# ── Overview ──

@router.get("/overview")
async def framework_overview(request: Request):
    await require_admin(request)
    await agents_svc.ensure_agents_seeded()
    await prompts_svc.ensure_prompts_seeded()
    agents_count = await db.af_agents.count_documents({})
    workflows_count = await db.af_workflows.count_documents({})
    executions_count = await db.af_executions.count_documents({})
    waiting = await db.af_executions.count_documents({"status": "waiting_human"})
    cat_agg = await db.af_agents.aggregate(
        [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    ).to_list(length=50)
    return {
        "agents": agents_count,
        "workflows": workflows_count,
        "executions": executions_count,
        "waiting_approvals": waiting,
        "tools": len(tool_registry.list_tools()),
        "providers": provider_registry.list_names(),
        "categories": {(c["_id"] or "Uncategorized"): c["count"] for c in cat_agg},
        "policy": await policy_svc.get_policy(),
        "generated_at": _now(),
    }


# ── Providers & Tools ──

@router.get("/providers")
async def list_providers(request: Request):
    await require_admin(request)
    return {"providers": provider_registry.list_names()}


@router.get("/tools")
async def list_tools(request: Request):
    await require_admin(request)
    return {"tools": tool_registry.list_tools()}


# ── Agents ──

@router.get("/agents")
async def list_agents(request: Request):
    await require_admin(request)
    return {"agents": await agents_svc.list_agents()}


@router.get("/agents/{agent_key}")
async def get_agent(agent_key: str, request: Request):
    await require_admin(request)
    agent = await agents_svc.get_agent(agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/agents/{agent_key}/versions")
async def get_agent_versions(agent_key: str, request: Request):
    await require_admin(request)
    return {"versions": await agents_svc.get_agent_versions(agent_key)}


@router.post("/agents")
async def upsert_agent(payload: AgentUpsert, request: Request):
    admin = await require_admin(request)
    try:
        return await agents_svc.upsert_agent(payload.model_dump(), admin.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/agents/{agent_key}")
async def delete_agent(agent_key: str, request: Request):
    admin = await require_admin(request)
    if not await agents_svc.delete_agent(agent_key, admin.user_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"deleted": True}


@router.post("/agents/{agent_key}/execute")
async def execute_agent(agent_key: str, payload: AgentExecuteRequest, request: Request):
    admin = await require_admin(request)
    agent = await agents_svc.get_agent(agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.get("enabled", True):
        raise HTTPException(status_code=409, detail="Agent is disabled")
    await policy_svc.check_execution_quota()
    try:
        return await agents_svc.execute_agent(
            agent, payload.input, session_id=payload.session_id,
            user_id=admin.user_id, timeout_seconds=payload.timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))


# ── Marketplace ──

@router.get("/marketplace/catalog")
async def marketplace_catalog(
    request: Request, q: str = "", category: str = "", subcategory: str = "",
    status: str = "", availability: str = "", tag: str = "", feature: str = "",
    sort: str = "name", order: str = "asc", page: int = 1, page_size: int = 30,
):
    await require_admin(request)
    return await marketplace_svc.search_catalog(
        q=q, category=category, subcategory=subcategory, status=status,
        availability=availability, tag=tag, feature=feature,
        sort=sort, order=order, page=page, page_size=page_size,
    )


@router.get("/marketplace/categories")
async def marketplace_categories(request: Request):
    await require_admin(request)
    return {"categories": await marketplace_svc.category_summaries()}


@router.get("/marketplace/coverage")
async def marketplace_coverage(request: Request):
    await require_admin(request)
    return await marketplace_svc.feature_coverage_matrix()


@router.get("/marketplace/recommendations/{feature_key}")
async def marketplace_recommendations(feature_key: str, request: Request, limit: int = 8):
    await require_admin(request)
    if feature_key not in marketplace_svc.get_feature_keys():
        raise HTTPException(status_code=404, detail="Unknown feature key")
    return await marketplace_svc.recommend_agents(feature_key, limit)


@router.get("/marketplace/dependencies")
async def marketplace_dependencies(request: Request):
    await require_admin(request)
    return await marketplace_svc.dependency_graph()


@router.get("/marketplace/portfolio")
async def marketplace_portfolio(request: Request):
    await require_admin(request)
    return await marketplace_svc.portfolio_overview()


@router.get("/marketplace/readiness")
async def marketplace_readiness(request: Request):
    await require_admin(request)
    return await marketplace_svc.readiness_report()


@router.get("/marketplace/templates")
async def marketplace_templates(request: Request):
    await require_admin(request)
    return {"templates": marketplace_svc.list_templates()}


@router.get("/marketplace/stats")
async def marketplace_stats(request: Request):
    await require_admin(request)
    return await marketplace_svc.agent_stats_report()


@router.post("/marketplace/agents/{agent_key}/clone")
async def marketplace_clone_agent(agent_key: str, payload: CloneRequest, request: Request):
    admin = await require_admin(request)
    try:
        return await marketplace_svc.clone_agent(agent_key, payload.new_key, payload.new_name, admin.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Source agent not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/marketplace/export")
async def marketplace_export(payload: ExportRequest, request: Request):
    await require_admin(request)
    return await marketplace_svc.export_agents(payload.agent_keys)


@router.post("/marketplace/import")
async def marketplace_import(payload: ImportRequest, request: Request):
    admin = await require_admin(request)
    if not payload.agents:
        raise HTTPException(status_code=400, detail="No agents provided")
    if len(payload.agents) > 300:
        raise HTTPException(status_code=400, detail="Import limited to 300 agents per request")
    return await marketplace_svc.import_agents(payload.agents, admin.user_id, payload.overwrite)


@router.post("/marketplace/bulk-status")
async def marketplace_bulk_status(payload: BulkUpdateRequest, request: Request):
    admin = await require_admin(request)
    try:
        return await marketplace_svc.bulk_update(payload.agent_keys, payload.changes, admin.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Prompt templates ──

@router.get("/prompts")
async def list_prompts(request: Request):
    await require_admin(request)
    return {"prompts": await prompts_svc.list_prompts()}


@router.post("/prompts")
async def upsert_prompt(payload: PromptUpsert, request: Request):
    admin = await require_admin(request)
    return await prompts_svc.upsert_prompt(payload.model_dump(), admin.user_id)


@router.delete("/prompts/{prompt_key}")
async def delete_prompt(prompt_key: str, request: Request):
    admin = await require_admin(request)
    if not await prompts_svc.delete_prompt(prompt_key, admin.user_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"deleted": True}


@router.post("/prompts/{prompt_key}/render")
async def render_prompt(prompt_key: str, payload: PromptRenderRequest, request: Request):
    await require_admin(request)
    prompt = await prompts_svc.get_prompt(prompt_key)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"rendered": prompts_svc.render_template(prompt["template"], payload.variables)}


# ── Workflows ──

@router.get("/workflows")
async def list_workflows(request: Request):
    await require_admin(request)
    items = await db.af_workflows.find({}, {"_id": 0}).sort("updated_at", -1).to_list(length=200)
    return {"workflows": items}


@router.post("/workflows")
async def create_workflow(payload: WorkflowUpsert, request: Request):
    admin = await require_admin(request)
    policy = await policy_svc.get_policy()
    try:
        validate_workflow_steps(payload.steps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if count_steps(payload.steps) > int(policy["max_steps_per_workflow"]):
        raise HTTPException(status_code=400, detail="Workflow exceeds max steps policy")
    doc = {
        "workflow_id": str(uuid.uuid4()),
        **payload.model_dump(),
        "version": 1,
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": admin.user_id,
    }
    await db.af_workflows.insert_one(doc)
    doc.pop("_id", None)
    await log_audit("workflow_created", admin.user_id, "workflow", doc["workflow_id"])
    return doc


@router.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, payload: WorkflowUpsert, request: Request):
    admin = await require_admin(request)
    existing = await db.af_workflows.find_one({"workflow_id": workflow_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        validate_workflow_steps(payload.steps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.af_workflow_versions.insert_one({
        "version_id": str(uuid.uuid4()), "workflow_id": workflow_id,
        "snapshot": existing, "archived_at": _now(), "archived_by": admin.user_id,
    })
    updates = {**payload.model_dump(), "version": int(existing.get("version", 1)) + 1, "updated_at": _now()}
    await db.af_workflows.update_one({"workflow_id": workflow_id}, {"$set": updates})
    await log_audit("workflow_updated", admin.user_id, "workflow", workflow_id, {"version": updates["version"]})
    return await db.af_workflows.find_one({"workflow_id": workflow_id}, {"_id": 0})


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request):
    admin = await require_admin(request)
    result = await db.af_workflows.delete_one({"workflow_id": workflow_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await log_audit("workflow_deleted", admin.user_id, "workflow", workflow_id)
    return {"deleted": True}


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, payload: WorkflowExecuteRequest, request: Request):
    admin = await require_admin(request)
    workflow = await db.af_workflows.find_one({"workflow_id": workflow_id}, {"_id": 0})
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.get("enabled", True):
        raise HTTPException(status_code=409, detail="Workflow is disabled")
    await policy_svc.check_execution_quota()
    try:
        return await start_execution(workflow, payload.input, admin.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Executions & HITL ──

@router.get("/executions")
async def list_executions(request: Request, status: Optional[str] = None, limit: int = 50):
    await require_admin(request)
    query = {"status": status} if status else {}
    limit = min(max(limit, 1), 200)
    items = await (
        db.af_executions.find(query, {"_id": 0, "steps": 0})
        .sort("created_at", -1).limit(limit).to_list(length=limit)
    )
    return {"executions": items}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, request: Request):
    await require_admin(request)
    execution = await db.af_executions.find_one({"execution_id": execution_id}, {"_id": 0})
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.post("/executions/{execution_id}/approve")
async def approve_execution(execution_id: str, payload: ApprovalRequest, request: Request):
    admin = await require_admin(request)
    return await resume_execution(execution_id, True, admin.user_id, payload.note)


@router.post("/executions/{execution_id}/reject")
async def reject_execution(execution_id: str, payload: ApprovalRequest, request: Request):
    admin = await require_admin(request)
    return await resume_execution(execution_id, False, admin.user_id, payload.note)


# ── Policy & Audit ──

@router.get("/policy")
async def get_policy(request: Request):
    await require_admin(request)
    return await policy_svc.get_policy()


@router.put("/policy")
async def update_policy(payload: PolicyUpdate, request: Request):
    admin = await require_admin(request)
    return await policy_svc.update_policy(payload.changes, admin.user_id)


@router.get("/audit")
async def list_audit(request: Request, limit: int = 100):
    await require_admin(request)
    limit = min(max(limit, 1), 500)
    items = await (
        db.af_audit_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    )
    return {"audit": items}
