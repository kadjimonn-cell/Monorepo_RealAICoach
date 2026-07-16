"""Admin API for AI operating layer v2: intelligent routing, event-driven
orchestration, knowledge management, analytics, alerts, capability discovery."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .db import require_admin
from agent_framework import analytics as analytics_svc
from agent_framework import knowledge as knowledge_svc
from agent_framework import orchestration_v2 as orchestration_svc
from agent_framework import router_service as routing_svc

router = APIRouter(prefix="/agent-framework")


# ── Models ──

class RouteRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=2000)
    feature_key: str = ""
    team_size: int = Field(default=3, ge=1, le=8)


class TriggerUpsert(BaseModel):
    trigger_id: Optional[str] = None
    event_name: str = Field(..., min_length=2, max_length=80)
    workflow_id: str = Field(..., min_length=1)
    description: str = ""
    enabled: bool = True


class EmitEventRequest(BaseModel):
    event_name: str = Field(..., min_length=2, max_length=80)
    payload: Dict[str, Any] = Field(default_factory=dict)


class CollectionUpsert(BaseModel):
    collection_key: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    category: str = "General"
    permissions: List[str] = Field(default_factory=lambda: ["admin"])
    governance: Dict[str, Any] = Field(default_factory=lambda: {"review_required": False, "retention_days": 365})
    status: str = "active"


class SourceAdd(BaseModel):
    collection_key: str = Field(..., min_length=2)
    name: str = Field(..., min_length=1, max_length=200)
    source_type: str = "manual"
    content: str = ""
    url: str = ""
    mongo_collection: str = ""


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    collection_key: str = ""
    limit: int = Field(default=5, ge=1, le=10)


class FeedbackRequest(BaseModel):
    agent_key: str = Field(..., min_length=2)
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""


# ── Intelligent routing & capability discovery ──

@router.post("/route")
async def route_intent(payload: RouteRequest, request: Request):
    admin = await require_admin(request)
    return await routing_svc.route_intent(
        payload.intent, feature_key=payload.feature_key,
        team_size=payload.team_size, user_id=admin.user_id,
    )


@router.get("/route/log")
async def get_routing_log(request: Request, limit: int = 50):
    await require_admin(request)
    return {"routing_log": await routing_svc.routing_log(limit)}


@router.get("/capabilities")
async def get_capabilities(request: Request):
    await require_admin(request)
    return await routing_svc.capability_discovery()


# ── Event-driven orchestration ──

@router.get("/events/triggers")
async def list_triggers(request: Request):
    await require_admin(request)
    return {"triggers": await orchestration_svc.list_triggers()}


@router.post("/events/triggers")
async def upsert_trigger(payload: TriggerUpsert, request: Request):
    admin = await require_admin(request)
    try:
        return await orchestration_svc.upsert_trigger(payload.model_dump(), admin.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/events/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str, request: Request):
    admin = await require_admin(request)
    if not await orchestration_svc.delete_trigger(trigger_id, admin.user_id):
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"deleted": True}


@router.post("/events/emit")
async def emit_event(payload: EmitEventRequest, request: Request):
    admin = await require_admin(request)
    return await orchestration_svc.emit_event(payload.event_name, payload.payload, admin.user_id)


@router.get("/events")
async def list_events(request: Request, limit: int = 50):
    await require_admin(request)
    return {"events": await orchestration_svc.list_events(limit)}


# ── Knowledge management ──

@router.get("/knowledge/overview")
async def knowledge_overview(request: Request):
    await require_admin(request)
    return await knowledge_svc.knowledge_overview()


@router.get("/knowledge/collections")
async def list_collections(request: Request):
    await require_admin(request)
    return {"collections": await knowledge_svc.list_collections()}


@router.post("/knowledge/collections")
async def upsert_collection(payload: CollectionUpsert, request: Request):
    admin = await require_admin(request)
    return await knowledge_svc.upsert_collection(payload.model_dump(), admin.user_id)


@router.delete("/knowledge/collections/{collection_key}")
async def delete_collection(collection_key: str, request: Request):
    admin = await require_admin(request)
    if not await knowledge_svc.delete_collection(collection_key, admin.user_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}


@router.get("/knowledge/sources")
async def list_sources(request: Request, collection_key: str = ""):
    await require_admin(request)
    return {"sources": await knowledge_svc.list_sources(collection_key)}


@router.post("/knowledge/sources")
async def add_source(payload: SourceAdd, request: Request):
    admin = await require_admin(request)
    try:
        return await knowledge_svc.add_source(payload.model_dump(), admin.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/knowledge/sources/{source_id}/sync")
async def sync_source(source_id: str, request: Request):
    admin = await require_admin(request)
    try:
        return await knowledge_svc.sync_source(source_id, admin.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/knowledge/sources/{source_id}")
async def delete_source(source_id: str, request: Request):
    admin = await require_admin(request)
    if not await knowledge_svc.delete_source(source_id, admin.user_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True}


@router.post("/knowledge/search")
async def search_knowledge(payload: KnowledgeSearchRequest, request: Request):
    await require_admin(request)
    return await knowledge_svc.search_knowledge(payload.collection_key, payload.query, payload.limit)


# ── Analytics ──

@router.get("/analytics/overview")
async def analytics_overview(request: Request):
    await require_admin(request)
    return await analytics_svc.analytics_overview()


@router.get("/analytics/trends")
async def analytics_trends(request: Request, days: int = 30):
    await require_admin(request)
    return await analytics_svc.trend_report(days)


@router.get("/analytics/agents/{agent_key}/history")
async def agent_history(agent_key: str, request: Request, limit: int = 30):
    await require_admin(request)
    return await analytics_svc.agent_history(agent_key, limit)


@router.get("/analytics/adoption")
async def feature_adoption(request: Request):
    await require_admin(request)
    return await analytics_svc.feature_adoption()


@router.get("/analytics/recommendations")
async def optimization_recommendations(request: Request):
    await require_admin(request)
    return await analytics_svc.optimization_recommendations()


@router.get("/analytics/alerts")
async def health_alerts(request: Request):
    await require_admin(request)
    return await analytics_svc.health_alerts()


@router.post("/analytics/feedback")
async def record_feedback(payload: FeedbackRequest, request: Request):
    admin = await require_admin(request)
    return await analytics_svc.record_feedback(payload.agent_key, payload.rating, payload.comment, admin.user_id)
