from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from routes.db import db, require_admin


router = APIRouter(prefix="/admin/system", tags=["Admin System Alerts"])


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_doc(payload: dict | None) -> dict:
    if not payload:
        return {}
    return {k: _to_iso(v) for k, v in payload.items()}


@router.get("/alerts/state")
async def get_alert_dispatch_state(user=Depends(require_admin)):
    _ = user
    integrity_doc = await db.system_state.find_one(
        {"key": "ai_platform_integrity_alert_state_v1"},
        {"_id": 0, "value": 1, "updated_at": 1},
    )
    integrity_value = _serialize_doc((integrity_doc or {}).get("value") or {})
    integrity_updated_at = _to_iso((integrity_doc or {}).get("updated_at"))

    spike_state = await db.anomaly_alert_runtime_state.find_one(
        {"_id": "spike_alert_state"},
        {"_id": 0},
    )

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integrity": {
            "state_key": "ai_platform_integrity_alert_state_v1",
            "unchanged_state_suppression_enabled": True,
            "updated_at": integrity_updated_at,
            **integrity_value,
        },
        "spike": {
            "state_doc_id": "spike_alert_state",
            "active_incident_suppression_enabled": True,
            **_serialize_doc(spike_state),
        },
    }
