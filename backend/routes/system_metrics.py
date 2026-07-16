"""System Metrics — Real-time system monitoring via REST and WebSocket.

Endpoints:
- GET  /api/admin/system/metrics  — Current system metrics snapshot
- WS   /api/ws/system-metrics     — Real-time system metrics stream (every 3s)
"""

import os
import asyncio
import logging
import time
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from routes.db import get_current_user
from utils.ws_ticket_auth import consume_ws_ticket

logger = logging.getLogger(__name__)
router = APIRouter()

_net_prev = {"bytes_sent": 0, "bytes_recv": 0, "time": 0}


def _get_system_metrics() -> dict:
    """Collect real-time system metrics using psutil."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    now_t = time.time()

    dt = max(0.1, now_t - _net_prev.get("time", now_t - 1))
    bytes_sent_rate = (net.bytes_sent - _net_prev.get("bytes_sent", net.bytes_sent)) / dt
    bytes_recv_rate = (net.bytes_recv - _net_prev.get("bytes_recv", net.bytes_recv)) / dt
    _net_prev["bytes_sent"] = net.bytes_sent
    _net_prev["bytes_recv"] = net.bytes_recv
    _net_prev["time"] = now_t

    proc_count = len(psutil.pids())
    load_avg = os.getloadavg()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "percent": round(cpu, 1),
            "count": psutil.cpu_count(),
            "load_1m": round(load_avg[0], 2),
            "load_5m": round(load_avg[1], 2),
            "load_15m": round(load_avg[2], 2),
        },
        "memory": {
            "percent": round(mem.percent, 1),
            "used_gb": round(mem.used / (1024**3), 2),
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
        },
        "disk": {
            "percent": round(disk.percent, 1),
            "used_gb": round(disk.used / (1024**3), 2),
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        },
        "network": {
            "bytes_sent_rate": round(bytes_sent_rate),
            "bytes_recv_rate": round(bytes_recv_rate),
            "total_sent_gb": round(net.bytes_sent / (1024**3), 3),
            "total_recv_gb": round(net.bytes_recv / (1024**3), 3),
        },
        "processes": proc_count,
    }


@router.get("/admin/system/metrics")
async def get_system_metrics(request: Request):
    """Get current system metrics snapshot (admin only)."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")
    return _get_system_metrics()


@router.websocket("/ws/system-metrics")
async def ws_system_metrics(websocket: WebSocket):
    """Stream real-time system metrics every 3 seconds via WebSocket."""
    from routes.db import db

    _user, close_code, _reason = await consume_ws_ticket(
        db,
        websocket.query_params.get("ticket", ""),
        channel="system_metrics",
        require_admin=True,
    )
    if not _user:
        await websocket.close(code=close_code)
        return

    await websocket.accept()
    logger.info("System metrics WebSocket connected")
    try:
        while True:
            metrics = _get_system_metrics()
            await websocket.send_json(metrics)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        logger.info("System metrics WebSocket disconnected")
    except Exception as e:
        logger.error(f"System metrics WS error: {e}")


@router.get("/system/metrics")
async def get_system_metrics_alias(request: Request):
    """Compatibility endpoint for non-admin system metrics checks."""
    user = await get_current_user(request)
    if not user:
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    if getattr(user, "is_admin", False):
        return _get_system_metrics()
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
