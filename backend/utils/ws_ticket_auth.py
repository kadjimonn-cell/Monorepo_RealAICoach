"""Shared WebSocket one-time ticket authentication helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Optional, Tuple


def hash_ws_ticket(raw_ticket: str) -> str:
    return hashlib.sha256(str(raw_ticket or "").encode()).hexdigest()


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _reason_to_close_code(reason: str) -> int:
    if reason in {"user_mismatch", "admin_required"}:
        return 4003
    return 4001


async def consume_ws_ticket(
    db,
    raw_ticket: str,
    *,
    channel: str,
    expected_user_id: Optional[str] = None,
    require_admin: bool = False,
) -> Tuple[Optional[dict], int, str]:
    ticket = str(raw_ticket or "").strip()
    if not ticket:
        return None, 4001, "ticket_missing"

    ticket_hash = hash_ws_ticket(ticket)
    ticket_doc = await db.user_ws_tickets.find_one(
        {"ticket_hash": ticket_hash, "used": False},
        {"_id": 0},
    )
    if not ticket_doc:
        return None, 4001, "ticket_invalid"

    ticket_channel = str(ticket_doc.get("channel") or "notifications")
    if ticket_channel != str(channel):
        return None, 4001, "channel_mismatch"

    now = datetime.now(timezone.utc)
    expires_at = _parse_dt(ticket_doc.get("expires_at"))
    if not expires_at or expires_at <= now:
        await db.user_ws_tickets.update_one(
            {"ticket_hash": ticket_hash},
            {"$set": {"used": True, "used_at": now.isoformat(), "invalid_reason": "expired"}},
        )
        return None, 4001, "ticket_expired"

    ticket_user_id = str(ticket_doc.get("user_id") or "")
    if expected_user_id and ticket_user_id != str(expected_user_id):
        return None, _reason_to_close_code("user_mismatch"), "user_mismatch"

    user = await db.users.find_one(
        {"user_id": ticket_user_id},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "is_admin": 1, "token_version": 1},
    )
    if not user:
        return None, 4001, "user_not_found"

    if require_admin and not bool(user.get("is_admin")):
        return None, _reason_to_close_code("admin_required"), "admin_required"

    consume = await db.user_ws_tickets.update_one(
        {"ticket_hash": ticket_hash, "used": False},
        {
            "$set": {
                "used": True,
                "used_at": now.isoformat(),
                "used_channel": str(channel),
            }
        },
    )
    if consume.modified_count != 1:
        return None, 4001, "ticket_replay_or_race"

    return user, 0, "ok"
