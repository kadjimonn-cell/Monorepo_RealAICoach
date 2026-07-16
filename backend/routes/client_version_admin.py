"""Admin management of the native client version policy."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.client_version_policy import (
    PLATFORM_KEYS,
    get_client_version_policy,
    parse_version,
    update_platform_policy,
)

from .db import require_admin

router = APIRouter(prefix="/admin/client-version-policy", tags=["Client Version Policy"])


class PlatformPolicyUpdate(BaseModel):
    min_supported_version: Optional[str] = Field(None, max_length=32)
    latest_version: Optional[str] = Field(None, max_length=32)
    update_url: Optional[str] = Field(None, max_length=500)
    enforced: Optional[bool] = None


@router.get("")
async def read_client_version_policy(admin=Depends(require_admin)):
    return {
        "platforms": await get_client_version_policy(force=True),
        "enforcement": {
            "platform_header": "X-Client-Platform",
            "version_header": "X-App-Version",
            "blocked_status": 426,
            "blocked_code": "CLIENT_UPDATE_REQUIRED",
            "exempt_paths": ["/api/health", "/api/client/bootstrap"],
        },
    }


@router.put("/{platform}")
async def update_client_version_policy(
    platform: str,
    body: PlatformPolicyUpdate,
    admin=Depends(require_admin),
):
    platform = str(platform).lower()
    if platform not in PLATFORM_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown platform. Allowed: {', '.join(PLATFORM_KEYS)}")

    for field in ("min_supported_version", "latest_version"):
        value = getattr(body, field)
        if value is not None and parse_version(value) is None:
            raise HTTPException(status_code=400, detail=f"Invalid semver for {field}: {value}")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    entry = await update_platform_policy(platform, updates, actor_id=str(getattr(admin, "user_id", "")))
    return {"platform": platform, "policy": entry}
