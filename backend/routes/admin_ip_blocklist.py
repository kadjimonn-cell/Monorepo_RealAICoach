"""Admin IP Blocklist — manage blocked and whitelisted IPs."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from routes.db import db, require_admin
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/sessions/blocked-ips", tags=["IP Blocklist"])


@router.get("")
async def list_blocked_ips(request: Request):
    await require_admin(request)
    blocked = await db.blocked_ips.find({}, {"_id": 0}).sort("blocked_at", -1).to_list(500)
    whitelisted = await db.whitelisted_ips.find({}, {"_id": 0}).sort("added_at", -1).to_list(500)

    # Enrich with geo data
    all_ips = [b["ip"] for b in blocked] + [w["ip"] for w in whitelisted]
    geo_map = {}
    if all_ips:
        try:
            from utils.ip_geolocation import batch_lookup_ips

            geo_map = await batch_lookup_ips(db, list(set(all_ips)))
        except Exception:
            pass

    for item in blocked:
        geo = geo_map.get(item["ip"], {})
        item["city"] = geo.get("city", "")
        item["country"] = geo.get("country", "")
        item["country_code"] = geo.get("country_code", "")
        item["isp"] = geo.get("isp", "")

    for item in whitelisted:
        geo = geo_map.get(item["ip"], {})
        item["city"] = geo.get("city", "")
        item["country"] = geo.get("country", "")
        item["country_code"] = geo.get("country_code", "")
        item["isp"] = geo.get("isp", "")

    auto_count = sum(1 for b in blocked if b.get("reason") == "auto-response")
    manual_count = sum(1 for b in blocked if b.get("reason") != "auto-response")

    return {
        "blocked": blocked,
        "whitelisted": whitelisted,
        "stats": {
            "total_blocked": len(blocked),
            "auto_blocked": auto_count,
            "manual_blocked": manual_count,
            "whitelisted": len(whitelisted),
        },
    }


@router.post("")
async def block_ip(request: Request):
    await require_admin(request)
    body = await request.json()
    ip = body.get("ip", "").strip()
    reason = body.get("reason", "manual").strip()

    if not ip:
        return JSONResponse(status_code=400, content={"error": "IP address is required"})

    # Check if already blocked
    existing = await db.blocked_ips.find_one({"ip": ip}, {"_id": 0})
    if existing:
        return JSONResponse(status_code=409, content={"error": f"IP {ip} is already blocked"})

    # Check if whitelisted
    wl = await db.whitelisted_ips.find_one({"ip": ip}, {"_id": 0})
    if wl:
        return JSONResponse(status_code=409, content={"error": f"IP {ip} is whitelisted — remove from whitelist first"})

    entry = {
        "ip": ip,
        "reason": reason or "manual",
        "blocked_at": datetime.now(timezone.utc).isoformat(),
        "block_id": f"blk_{uuid.uuid4().hex[:12]}",
    }
    await db.blocked_ips.insert_one(entry)
    entry.pop("_id", None)
    return {"blocked": entry}


@router.delete("/{ip}")
async def unblock_ip(ip: str, request: Request):
    await require_admin(request)
    result = await db.blocked_ips.delete_one({"ip": ip})
    return {"unblocked": result.deleted_count > 0, "ip": ip}


@router.post("/{ip}/whitelist")
async def whitelist_ip(ip: str, request: Request):
    await require_admin(request)

    # Remove from blocked if present
    await db.blocked_ips.delete_one({"ip": ip})

    # Add to whitelist
    existing = await db.whitelisted_ips.find_one({"ip": ip}, {"_id": 0})
    if existing:
        return {"whitelisted": existing, "already": True}

    entry = {
        "ip": ip,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "wl_id": f"wl_{uuid.uuid4().hex[:12]}",
    }
    await db.whitelisted_ips.insert_one(entry)
    entry.pop("_id", None)
    return {"whitelisted": entry}


@router.delete("/{ip}/whitelist")
async def remove_whitelist(ip: str, request: Request):
    await require_admin(request)
    result = await db.whitelisted_ips.delete_one({"ip": ip})
    return {"removed": result.deleted_count > 0, "ip": ip}
