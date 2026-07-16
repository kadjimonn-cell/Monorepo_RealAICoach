"""Internal GTEC event ingestion API (autonomous orchestration)."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routes.db import db
from services import gtec_scan_v2 as svc

router = APIRouter(prefix="/internal/gtec", tags=["gtec-internal"])


class GtecEventIngestBody(BaseModel):
    event_type: str
    source: str
    scope: str
    severity: str = "medium"
    payload: Optional[dict[str, Any]] = None
    dedupe_key: Optional[str] = None


def _require_internal_token(request: Request) -> None:
    expected = os.environ.get("GTEC_INTERNAL_EVENT_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal event ingestion token is not configured")
    provided = request.headers.get("x-gtec-internal-token") or ""
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid internal token")


@router.post("/events/ingest")
async def ingest_event(request: Request, body: GtecEventIngestBody):
    _require_internal_token(request)
    result = await svc.enqueue_event(
        db,
        event_type=body.event_type,
        source=body.source,
        scope=body.scope,
        severity=body.severity,
        payload=body.payload,
        dedupe_key=body.dedupe_key,
    )
    return {
        "ok": True,
        **result,
    }


@router.get("/events/queue-stats")
async def queue_stats(request: Request):
    _require_internal_token(request)
    queued = await db[svc.EVENTS_COL].count_documents({"status": "queued"})
    consumed = await db[svc.EVENTS_COL].count_documents({"status": "consumed"})
    processed = await db[svc.EVENTS_COL].count_documents({"status": "processed"})
    return {
        "queued": queued,
        "consumed": consumed,
        "processed": processed,
    }
