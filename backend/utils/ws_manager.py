"""WebSocket connection manager for real-time notifications."""

from fastapi import WebSocket
from typing import Dict, List
import logging

logger = logging.getLogger("routes.db")


class ConnectionManager:
    """Manages active WebSocket connections per user."""

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(ws)
        logger.info(f"WS connected: {user_id} ({len(self.connections[user_id])} connections)")
        # Broadcast updated online count to public activity stream
        await self._broadcast_online_count()

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            self.connections[user_id] = [c for c in self.connections[user_id] if c != ws]
            if not self.connections[user_id]:
                del self.connections[user_id]
        logger.info(f"WS disconnected: {user_id}")
        # Fire-and-forget broadcast (sync context, schedule async)
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._broadcast_online_count())
        except Exception:
            pass

    async def connect_public(self, ws: WebSocket):
        """Connect a public activity stream listener (no auth required)."""
        await ws.accept()
        self.public_stream.append(ws)
        logger.info(f"Public stream connected ({len(self.public_stream)} listeners)")

    def disconnect_public(self, ws: WebSocket):
        self.public_stream = [c for c in self.public_stream if c != ws]
        logger.info(f"Public stream disconnected ({len(self.public_stream)} listeners)")

    async def broadcast_activity(self, event: dict):
        """Broadcast an anonymized activity event to all public stream listeners."""
        dead = []
        for ws in self.public_stream:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_public(ws)

    async def _broadcast_online_count(self):
        """Broadcast updated online user count to public activity stream."""
        from datetime import datetime, timezone

        count = len(self.connections)
        await self.broadcast_activity(
            {
                "type": "online_count",
                "count": count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def send_to_user(self, user_id: str, data: dict):
        if user_id not in self.connections:
            return
        dead = []
        for ws in self.connections[user_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast(self, data: dict):
        for user_id in list(self.connections.keys()):
            await self.send_to_user(user_id, data)

    async def send_to_admins(self, data: dict, admin_user_ids: list):
        """Send a message to all connected admin users."""
        for uid in admin_user_ids:
            if uid in self.connections:
                await self.send_to_user(uid, data)

    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}
        self.public_stream: List[WebSocket] = []
        self.admin_activity_listeners: List[WebSocket] = []
        self.automation_listeners: List[WebSocket] = []
        self.aso_listeners: List[WebSocket] = []

    async def connect_admin_activity(self, ws: WebSocket):
        """Connect an admin activity feed listener."""
        await ws.accept()
        self.admin_activity_listeners.append(ws)
        logger.info(f"Admin activity listener connected ({len(self.admin_activity_listeners)} total)")

    def disconnect_admin_activity(self, ws: WebSocket):
        self.admin_activity_listeners = [c for c in self.admin_activity_listeners if c != ws]
        logger.info(f"Admin activity listener disconnected ({len(self.admin_activity_listeners)} total)")

    async def broadcast_admin_activity(self, event: dict):
        """Broadcast an activity event to all admin activity feed listeners."""
        dead = []
        msg = {"type": "activity_event", "data": event}
        for ws in self.admin_activity_listeners:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_admin_activity(ws)

    # ── Automation Dashboard WebSocket ──────────────────────────────
    async def connect_automation(self, ws: WebSocket):
        """Connect an automation dashboard listener."""
        await ws.accept()
        self.automation_listeners.append(ws)
        logger.info(f"Automation WS connected ({len(self.automation_listeners)} listeners)")

    def disconnect_automation(self, ws: WebSocket):
        self.automation_listeners = [c for c in self.automation_listeners if c != ws]
        logger.info(f"Automation WS disconnected ({len(self.automation_listeners)} listeners)")

    async def broadcast_automation(self, event: dict):
        """Broadcast automation data to all connected automation dashboard listeners."""
        dead = []
        for ws in self.automation_listeners:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_automation(ws)

    # ── ASO Dashboard WebSocket ─────────────────────────────────────
    async def connect_aso(self, ws: WebSocket):
        """Connect an ASO dashboard listener."""
        await ws.accept()
        self.aso_listeners.append(ws)
        logger.info(f"ASO WS connected ({len(self.aso_listeners)} listeners)")

    def disconnect_aso(self, ws: WebSocket):
        self.aso_listeners = [c for c in self.aso_listeners if c != ws]
        logger.info(f"ASO WS disconnected ({len(self.aso_listeners)} listeners)")

    async def broadcast_aso(self, event: dict):
        """Broadcast ASO data to all connected ASO dashboard listeners."""
        dead = []
        for ws in self.aso_listeners:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_aso(ws)

    @property
    def active_count(self) -> int:
        return sum(len(conns) for conns in self.connections.values())


ws_manager = ConnectionManager()


# Event type to human-readable label mapping
_EVENT_LABELS = {
    "login_success": "User signed in",
    "login_failed": "Login attempt failed",
    "login_rate_limit": "Rate limit triggered",
    "blocked_ip": "Suspicious IP blocked",
    "2fa_enabled": "2FA enabled",
    "2fa_disabled": "2FA disabled",
    "backup_codes_regenerated": "Backup codes regenerated",
    "password_changed": "Password updated",
    "password_reset": "Password reset requested",
    "account_created": "New user registered",
    "google_login": "Google SSO login",
    "guest_login": "Guest session started",
}

# Risk level to color
_RISK_COLORS = {
    "low": "#00E0C6",
    "medium": "#FFB800",
    "high": "#FF2E2E",
    "critical": "#FF2E2E",
}


async def broadcast_security_event(event_type: str, risk_level: str = "low"):
    """Broadcast an anonymized security event to the public activity stream."""
    from datetime import datetime, timezone

    label = _EVENT_LABELS.get(event_type, event_type.replace("_", " ").title())
    color = _RISK_COLORS.get(risk_level, "#00F0FF")
    event = {
        "type": "activity",
        "label": label,
        "risk": risk_level,
        "color": color,
        "time": datetime.now(timezone.utc).strftime("%H:%M"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await ws_manager.broadcast_activity(event)


async def push_admin_alert(alert_type: str, title: str, message: str, severity: str = "info", extra: dict = None):
    """Push a real-time alert to all connected admin users."""
    from routes.db import db

    admin_users = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
    admin_ids = [u["user_id"] for u in admin_users]
    payload = {
        "type": "admin_alert",
        "alert_type": alert_type,
        "title": title,
        "message": message,
        "severity": severity,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    if extra:
        payload["extra"] = extra
    await ws_manager.send_to_admins(payload, admin_ids)


async def broadcast_data_change(entity: str, action: str = "updated", user_id: str = None, extra: dict = None):
    """Broadcast a data-change event so dashboards can auto-refresh.

    entity: 'goals', 'sessions', 'payments', 'users', 'teams', 'notifications', etc.
    action: 'created', 'updated', 'deleted'
    user_id: if set, sends to that user only; otherwise broadcasts to all connected users.
    """
    from datetime import datetime, timezone

    payload = {
        "type": "data_change",
        "entity": entity,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload["extra"] = extra
    if user_id:
        await ws_manager.send_to_user(user_id, payload)
    else:
        await ws_manager.broadcast(payload)
