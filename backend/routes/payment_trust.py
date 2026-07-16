from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from routes.db import get_current_user, require_admin, resolve_user_role
from services.unified_trust_layer import (
    build_unified_trust_snapshot,
    get_unified_trust_settings,
    upsert_unified_trust_settings,
)


router = APIRouter()


class TrustSettingsUpdateRequest(BaseModel):
    trust_signals_enabled: Optional[bool] = None
    guarantee_message: Optional[str] = None
    fraud_notice: Optional[str] = None
    compliance_labels: Optional[List[str]] = None
    display_level: Optional[str] = None
    allow_nova_security_answers: Optional[bool] = None


@router.get("/payments/trust/assurance")
async def payment_trust_assurance(
    request: Request,
    provider: str = "all",
    context: str = "checkout",
):
    user = await get_current_user(request)
    is_admin = bool(user and resolve_user_role(user) == "admin")
    snapshot = await build_unified_trust_snapshot(
        provider=provider,
        context=context,
        request=request if is_admin else None,
        mode="live" if is_admin else "static",
    )
    snapshot["audience"] = "admin" if is_admin else "public"
    snapshot["viewer_is_admin"] = is_admin
    return snapshot


@router.get("/admin/payment-trust/settings")
async def get_payment_trust_settings(request: Request):
    await require_admin(request)
    settings = await get_unified_trust_settings()
    return {
        "settings": settings,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/admin/payment-trust/settings")
async def update_payment_trust_settings(payload: TrustSettingsUpdateRequest, request: Request):
    admin_user = await require_admin(request)
    updated = await upsert_unified_trust_settings(
        partial=payload.model_dump(exclude_none=True),
        actor_user_id=getattr(admin_user, "user_id", None),
    )
    return {
        "success": True,
        "settings": updated,
        "updated_at": updated.get("updated_at"),
    }
