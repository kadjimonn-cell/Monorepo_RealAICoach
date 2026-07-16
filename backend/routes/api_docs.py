"""Admin-gated versioned API documentation (OpenAPI schema + Swagger UI)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from .db import require_admin

router = APIRouter(tags=["API Documentation"])


@router.get("/openapi.json", include_in_schema=False)
async def versioned_openapi(request: Request, admin=Depends(require_admin)):
    schema = request.app.openapi()
    schema = {**schema, "info": {**schema.get("info", {}), "version": "1.0.0"}}
    return JSONResponse(schema)


@router.get("/docs", include_in_schema=False, response_class=HTMLResponse)
async def versioned_docs(request: Request, admin=Depends(require_admin)):
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title="RealAICoach API v1 — Documentation",
    )
