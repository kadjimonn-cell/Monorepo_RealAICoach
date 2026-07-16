"""
Security Incident Dashboard — Admin API for viewing 401/403 incident data
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from routes.db import db, require_admin

router = APIRouter(prefix="/admin/security-incidents", tags=["Security Incidents"])


@router.get("")
async def incidents_root(request: Request, hours: int = 24, limit: int = 25):
    """Compatibility root endpoint for incident dashboard clients.

    Returns a compact summary plus latest incident rows.
    """
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    total = await db.security_incidents.count_documents({"ts": {"$gte": cutoff}})
    latest = []
    async for doc in db.security_incidents.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(limit):
        latest.append(doc)
    return {
        "hours": hours,
        "total": total,
        "latest": latest,
        "hint": {
            "summary": "/api/admin/security-incidents/summary",
            "timeline": "/api/admin/security-incidents/timeline",
        },
    }


@router.get("/summary")
async def incident_summary(request: Request, hours: int = 24):
    """Incident counts by status code and incident code over last N hours."""
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"status": "$status", "code": "$code"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    results = await db.security_incidents.aggregate(pipeline).to_list(100)

    total_401 = sum(r["count"] for r in results if r["_id"]["status"] == 401)
    total_403 = sum(r["count"] for r in results if r["_id"]["status"] == 403)
    total = sum(r["count"] for r in results)

    breakdown = [
        {"status": r["_id"]["status"], "code": r["_id"]["code"], "count": r["count"]}
        for r in results
    ]

    return {
        "hours": hours,
        "total": total,
        "total_401": total_401,
        "total_403": total_403,
        "breakdown": breakdown,
    }


@router.get("/timeline")
async def incident_timeline(request: Request, hours: int = 24):
    """Hourly incident counts for charting."""
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$addFields": {"hour": {"$substr": ["$ts", 0, 13]}}},
        {"$group": {
            "_id": {"hour": "$hour", "status": "$status"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.hour": 1}},
    ]
    results = await db.security_incidents.aggregate(pipeline).to_list(500)

    timeline = {}
    for r in results:
        hour = r["_id"]["hour"]
        if hour not in timeline:
            timeline[hour] = {"hour": hour, "count_401": 0, "count_403": 0}
        if r["_id"]["status"] == 401:
            timeline[hour]["count_401"] = r["count"]
        elif r["_id"]["status"] == 403:
            timeline[hour]["count_403"] = r["count"]

    return {"hours": hours, "timeline": sorted(timeline.values(), key=lambda x: x["hour"])}


@router.get("/top-paths")
async def top_blocked_paths(request: Request, hours: int = 24, limit: int = 20):
    """Most frequently blocked paths."""
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"path": "$path", "status": "$status", "code": "$code"},
            "count": {"$sum": 1},
            "last_seen": {"$max": "$ts"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    results = await db.security_incidents.aggregate(pipeline).to_list(limit)

    paths = [
        {
            "path": r["_id"]["path"],
            "status": r["_id"]["status"],
            "code": r["_id"]["code"],
            "count": r["count"],
            "last_seen": r["last_seen"],
        }
        for r in results
    ]
    return {"hours": hours, "paths": paths}


@router.get("/top-ips")
async def top_offending_ips(request: Request, hours: int = 24, limit: int = 15):
    """IPs with the most blocked requests."""
    await require_admin(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"ts": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$ip",
            "count": {"$sum": 1},
            "codes": {"$addToSet": "$code"},
            "last_seen": {"$max": "$ts"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    results = await db.security_incidents.aggregate(pipeline).to_list(limit)

    ips = [
        {
            "ip": r["_id"],
            "count": r["count"],
            "codes": r["codes"],
            "last_seen": r["last_seen"],
        }
        for r in results
    ]
    return {"hours": hours, "ips": ips}


@router.get("/recent")
async def recent_incidents(request: Request, limit: int = 50):
    """Most recent incidents (for live feed)."""
    await require_admin(request)
    incidents = await db.security_incidents.find(
        {}, {"_id": 0}
    ).sort("ts", -1).limit(limit).to_list(limit)
    return {"incidents": incidents}


# ── Incident Spike Alert Configuration ──

DEFAULT_SPIKE_CONFIG = {
    "enabled": True,
    "threshold": 100,            # incidents per window to trigger alert
    "window_minutes": 60,        # sliding window size
    "cooldown_minutes": 120,     # don't re-alert within this period
    "email_enabled": True,
}


@router.get("/alert-config")
async def get_alert_config(request: Request):
    """Get incident spike alert configuration."""
    await require_admin(request)
    config = await db.incident_alert_config.find_one({"key": "spike_config"}, {"_id": 0})
    if not config:
        config = {**DEFAULT_SPIKE_CONFIG, "key": "spike_config"}
    return config


@router.put("/alert-config")
async def update_alert_config(request: Request):
    """Update incident spike alert configuration."""
    await require_admin(request)
    body = await request.json()
    allowed = {"enabled", "threshold", "window_minutes", "cooldown_minutes", "email_enabled"}
    updates = {}
    for k in allowed:
        if k in body:
            updates[k] = body[k]
    # Validate
    if "threshold" in updates:
        updates["threshold"] = max(10, min(int(updates["threshold"]), 10000))
    if "window_minutes" in updates:
        updates["window_minutes"] = max(5, min(int(updates["window_minutes"]), 1440))
    if "cooldown_minutes" in updates:
        updates["cooldown_minutes"] = max(10, min(int(updates["cooldown_minutes"]), 1440))

    await db.incident_alert_config.update_one(
        {"key": "spike_config"}, {"$set": {**updates, "key": "spike_config"}}, upsert=True
    )
    config = await db.incident_alert_config.find_one({"key": "spike_config"}, {"_id": 0})
    return config


@router.get("/alert-history")
async def get_alert_history(request: Request, limit: int = 20):
    """Get incident spike alert history."""
    await require_admin(request)
    alerts = await db.incident_spike_alerts.find(
        {}, {"_id": 0}
    ).sort("alerted_at", -1).limit(limit).to_list(limit)
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/alert-test")
async def test_incident_alert(request: Request):
    """Manually trigger a spike check and alert (admin only)."""
    await require_admin(request)
    result = await check_incident_spike()
    return result


# ── Spike Detection Engine ──

async def get_qa_allowlisted_ips() -> list:
    doc = await db.qa_traffic_allowlist.find_one({"key": "default"}, {"_id": 0, "ips": 1})
    return list((doc or {}).get("ips") or [])


async def check_incident_spike():
    """Check for 401/403 incident spikes and alert admins if threshold exceeded."""
    import logging
    logger = logging.getLogger("incident_alerting")

    try:
        # Load config
        config = await db.incident_alert_config.find_one({"key": "spike_config"}, {"_id": 0})
        if not config:
            config = DEFAULT_SPIKE_CONFIG

        if not config.get("enabled", True):
            return {"status": "disabled", "message": "Incident alerting is disabled"}

        threshold = int(config.get("threshold", 100))
        window_minutes = int(config.get("window_minutes", 60))
        cooldown_minutes = int(config.get("cooldown_minutes", 120))
        email_enabled = config.get("email_enabled", True)

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(minutes=window_minutes)).isoformat()

        # Count incidents in window (excluding internal QA/testing traffic)
        qa_ips = await get_qa_allowlisted_ips()
        base_match: dict = {"ts": {"$gte": cutoff}}
        if qa_ips:
            base_match["ip"] = {"$nin": qa_ips}
        total = await db.security_incidents.count_documents(base_match)

        if total < threshold:
            return {
                "status": "ok",
                "total": total,
                "threshold": threshold,
                "window_minutes": window_minutes,
                "message": f"Below threshold ({total}/{threshold})",
            }

        # Spike detected — check cooldown
        cooldown_cutoff = (now - timedelta(minutes=cooldown_minutes)).isoformat()
        recent_alert = await db.incident_spike_alerts.find_one(
            {"alerted_at": {"$gte": cooldown_cutoff}}, {"_id": 0}
        )
        if recent_alert:
            return {
                "status": "spike_detected_cooldown",
                "total": total,
                "threshold": threshold,
                "message": f"Spike detected ({total}/{threshold}) but in cooldown (last alert: {recent_alert.get('alerted_at', '?')})",
            }

        # Gather details for the alert
        pipeline_401 = [
            {"$match": {**base_match, "status": 401}},
            {"$count": "count"},
        ]
        pipeline_403 = [
            {"$match": {**base_match, "status": 403}},
            {"$count": "count"},
        ]
        count_401_result = await db.security_incidents.aggregate(pipeline_401).to_list(1)
        count_403_result = await db.security_incidents.aggregate(pipeline_403).to_list(1)
        incidents_401 = count_401_result[0]["count"] if count_401_result else 0
        incidents_403 = count_403_result[0]["count"] if count_403_result else 0

        # IDOR blocked count
        idor_blocked = await db.security_incidents.count_documents(
            {**base_match, "code": "IDOR_BLOCKED"}
        )

        # Top IPs
        ip_pipeline = [
            {"$match": base_match},
            {"$group": {"_id": "$ip", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        top_ip_docs = await db.security_incidents.aggregate(ip_pipeline).to_list(5)
        top_ips = ", ".join(f"{d['_id']} ({d['count']})" for d in top_ip_docs if d.get("_id"))

        # Top Paths
        path_pipeline = [
            {"$match": base_match},
            {"$group": {"_id": "$path", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        top_path_docs = await db.security_incidents.aggregate(path_pipeline).to_list(5)
        top_paths = ", ".join(f"{d['_id'][:40]} ({d['count']})" for d in top_path_docs if d.get("_id"))

        # Record the alert
        alert_record = {
            "alerted_at": now.isoformat(),
            "total": total,
            "incidents_401": incidents_401,
            "incidents_403": incidents_403,
            "idor_blocked": idor_blocked,
            "threshold": threshold,
            "window_minutes": window_minutes,
            "top_ips": top_ips,
            "top_paths": top_paths,
        }
        await db.incident_spike_alerts.insert_one(alert_record)

        # Send email alert to admins
        email_sent = False
        if email_enabled:
            try:
                from utils.email_service import send_catalog_template, is_email_configured
                if is_email_configured():
                    admin_users = await db.users.find(
                        {"is_admin": True}, {"_id": 0, "email": 1, "name": 1}
                    ).to_list(20)
                    for admin in admin_users:
                        await send_catalog_template(
                            recipient_email=admin["email"],
                            template_key="security_incident_spike_v7",
                            recipient_name=admin.get("name", "Admin"),
                            total_incidents=total,
                            incidents_401=incidents_401,
                            incidents_403=incidents_403,
                            window_minutes=window_minutes,
                            threshold=threshold,
                            top_ips=top_ips,
                            top_paths=top_paths,
                            idor_blocked=idor_blocked,
                        )
                    email_sent = True
                    logger.info(f"Incident spike alert sent to {len(admin_users)} admins: {total} incidents in {window_minutes}min")
            except Exception as e:
                logger.error(f"Failed to send incident spike email: {e}")

        # Push WebSocket alert
        try:
            from utils.ws_manager import push_admin_alert
            await push_admin_alert(
                "incident_spike",
                f"Security Incident Spike: {total} in {window_minutes}min",
                f"401: {incidents_401} | 403: {incidents_403} | IDOR: {idor_blocked} — Threshold: {threshold}",
                "critical" if total >= threshold * 2 else "warning",
            )
        except Exception:
            pass

        return {
            "status": "spike_alerted",
            "total": total,
            "incidents_401": incidents_401,
            "incidents_403": incidents_403,
            "idor_blocked": idor_blocked,
            "threshold": threshold,
            "window_minutes": window_minutes,
            "top_ips": top_ips,
            "top_paths": top_paths,
            "email_sent": email_sent,
        }

    except Exception as e:
        logger.error(f"Incident spike check failed: {e}")
        return {"status": "error", "message": str(e)}


# ── Automated IP Blocking ──

DEFAULT_AUTOBLOCK_CONFIG = {
    "enabled": True,
    "threshold": 100,           # incidents per IP per window to trigger block
    "window_minutes": 60,       # sliding window
    "block_duration_hours": 24,  # how long the auto-block lasts
    "email_enabled": True,
}

# Only high-risk security signals should contribute to automatic IP blocking.
# Benign/expected auth noise (e.g., AUTH_REQUIRED, ADMIN_NO_AUTH) must never
# trigger global IP blocks, especially on shared proxy/ingress addresses.
AUTOBLOCK_HIGH_RISK_CODES = {
    "CSRF_BLOCKED",
    "IDOR_BLOCKED",
    "WAF_BLOCKED",
    "BOT_BLOCKED",
    "GEO_BLOCKED",
    "RATE_LIMITED",
    "SQLI_PROBE_BLOCKED",
    "NOSQL_INJECTION_BLOCKED",
    "UPLOAD_CONTENT_TOO_LARGE",
}


@router.get("/autoblock-config")
async def get_autoblock_config(request: Request):
    """Get automated IP blocking configuration."""
    await require_admin(request)
    config = await db.incident_alert_config.find_one({"key": "autoblock_config"}, {"_id": 0})
    if not config:
        config = {**DEFAULT_AUTOBLOCK_CONFIG, "key": "autoblock_config"}
    return config


@router.put("/autoblock-config")
async def update_autoblock_config(request: Request):
    """Update automated IP blocking configuration."""
    await require_admin(request)
    body = await request.json()
    allowed = {"enabled", "threshold", "window_minutes", "block_duration_hours", "email_enabled"}
    updates = {}
    for k in allowed:
        if k in body:
            updates[k] = body[k]
    if "threshold" in updates:
        updates["threshold"] = max(10, min(int(updates["threshold"]), 10000))
    if "window_minutes" in updates:
        updates["window_minutes"] = max(5, min(int(updates["window_minutes"]), 1440))
    if "block_duration_hours" in updates:
        updates["block_duration_hours"] = max(1, min(int(updates["block_duration_hours"]), 720))

    await db.incident_alert_config.update_one(
        {"key": "autoblock_config"}, {"$set": {**updates, "key": "autoblock_config"}}, upsert=True
    )
    config = await db.incident_alert_config.find_one({"key": "autoblock_config"}, {"_id": 0})
    return config


@router.get("/autoblock-history")
async def get_autoblock_history(request: Request, limit: int = 50):
    """Get auto-blocked IP history."""
    await require_admin(request)
    history = await db.ip_autoblock_history.find(
        {}, {"_id": 0}
    ).sort("blocked_at", -1).limit(limit).to_list(limit)
    return {"history": history, "total": len(history)}


@router.post("/autoblock-run")
async def run_autoblock_now(request: Request):
    """Manually trigger auto-block scan (admin only)."""
    await require_admin(request)
    result = await check_and_autoblock_ips()
    return result


async def check_and_autoblock_ips():
    """Scan security_incidents for IPs exceeding threshold and auto-block them."""
    import logging
    logger = logging.getLogger("ip_autoblock")

    try:
        config = await db.incident_alert_config.find_one({"key": "autoblock_config"}, {"_id": 0})
        if not config:
            config = DEFAULT_AUTOBLOCK_CONFIG

        if not config.get("enabled", True):
            return {"status": "disabled", "blocked_count": 0}

        threshold = int(config.get("threshold", 100))
        window_minutes = int(config.get("window_minutes", 60))
        block_hours = int(config.get("block_duration_hours", 24))
        email_enabled = config.get("email_enabled", True)

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(minutes=window_minutes)).isoformat()
        expires_at = now + timedelta(hours=block_hours)

        # Find IPs exceeding threshold from high-risk incidents only.
        # This prevents false positives from routine unauthenticated traffic.
        high_risk_filter = {
            "$and": [
                {"ts": {"$gte": cutoff}},
                {
                    "$or": [
                        {"code": {"$in": list(AUTOBLOCK_HIGH_RISK_CODES)}},
                        {"status": 429},
                    ]
                },
            ]
        }

        pipeline = [
            {"$match": high_risk_filter},
            {"$group": {"_id": "$ip", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gte": threshold}}},
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]
        offenders = await db.security_incidents.aggregate(pipeline).to_list(50)

        # Reconcile stale auto-block entries that no longer meet high-risk criteria.
        # This is important when previous versions blocked IPs based on benign auth noise.
        active_auto_blocks = await db.blocked_ips.find(
            {
                "auto": True,
                "expires_at": {"$gt": now},
                "reason": "auto-block: incident threshold exceeded",
            },
            {"_id": 0, "ip": 1},
        ).to_list(500)

        released_blocks = []
        for blocked in active_auto_blocks:
            blocked_ip = str(blocked.get("ip") or "").strip()
            if not blocked_ip:
                continue
            high_risk_count = await db.security_incidents.count_documents(
                {
                    "ip": blocked_ip,
                    "ts": {"$gte": cutoff},
                    "$or": [
                        {"code": {"$in": list(AUTOBLOCK_HIGH_RISK_CODES)}},
                        {"status": 429},
                    ],
                }
            )
            if int(high_risk_count) < threshold:
                await db.blocked_ips.delete_one({"ip": blocked_ip})
                released_blocks.append({"ip": blocked_ip, "high_risk_count": int(high_risk_count)})

        if not offenders:
            return {
                "status": "ok",
                "blocked_count": 0,
                "released_count": len(released_blocks),
                "released_blocks": released_blocks,
                "message": f"No IPs above high-risk threshold ({threshold}/{window_minutes}min)",
            }

        # Load whitelist
        whitelisted_docs = await db.whitelisted_ips.find({}, {"_id": 0, "ip": 1}).to_list(500)
        whitelist = {d["ip"] for d in whitelisted_docs}

        # Load already-blocked IPs
        already_blocked_docs = await db.blocked_ips.find(
            {"expires_at": {"$gt": now}}, {"_id": 0, "ip": 1}
        ).to_list(500)
        already_blocked = {d["ip"] for d in already_blocked_docs}

        # Also skip internal/localhost
        skip_ips = {"127.0.0.1", "::1", "localhost", "unknown", ""}

        blocked_ips = []
        skipped = []

        for offender in offenders:
            ip = offender["_id"]
            count = offender["count"]

            if not ip or ip in skip_ips:
                skipped.append({"ip": ip, "reason": "internal"})
                continue
            if ip in whitelist:
                skipped.append({"ip": ip, "reason": "whitelisted", "count": count})
                continue
            if ip in already_blocked:
                skipped.append({"ip": ip, "reason": "already_blocked", "count": count})
                continue

            # Block this IP
            block_entry = {
                "ip": ip,
                "reason": "auto-block: incident threshold exceeded",
                "blocked_at": now.isoformat(),
                "expires_at": expires_at,
                "block_id": f"ablk_{__import__('uuid').uuid4().hex[:12]}",
                "auto": True,
                "incident_count": count,
                "threshold": threshold,
                "window_minutes": window_minutes,
            }
            await db.blocked_ips.update_one(
                {"ip": ip},
                {"$set": block_entry},
                upsert=True,
            )
            blocked_ips.append({"ip": ip, "count": count})

            # Record in history
            await db.ip_autoblock_history.insert_one({
                "ip": ip,
                "incident_count": count,
                "threshold": threshold,
                "window_minutes": window_minutes,
                "block_duration_hours": block_hours,
                "blocked_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            })

        if not blocked_ips:
            return {
                "status": "ok",
                "blocked_count": 0,
                "skipped": len(skipped),
                "message": f"All {len(offenders)} offender IPs already blocked or whitelisted",
            }

        # Send email alert
        email_sent = False
        if email_enabled and blocked_ips:
            try:
                from utils.email_service import send_catalog_template, is_email_configured
                if is_email_configured():
                    admin_users = await db.users.find(
                        {"is_admin": True}, {"_id": 0, "email": 1, "name": 1}
                    ).to_list(20)
                    ip_list_str = ", ".join(f"{b['ip']} ({b['count']})" for b in blocked_ips[:10])
                    for admin in admin_users:
                        await send_catalog_template(
                            recipient_email=admin["email"],
                            template_key="ip_auto_blocked_v7",
                            recipient_name=admin.get("name", "Admin"),
                            blocked_count=len(blocked_ips),
                            ip_list=ip_list_str,
                            threshold=threshold,
                            window_minutes=window_minutes,
                            block_duration_hours=block_hours,
                        )
                    email_sent = True
                    logger.info(f"Auto-blocked {len(blocked_ips)} IPs, emailed {len(admin_users)} admins")
            except Exception as e:
                logger.error(f"Auto-block email failed: {e}")

        # WebSocket push
        try:
            from utils.ws_manager import push_admin_alert
            await push_admin_alert(
                "ip_auto_blocked",
                f"Auto-Blocked {len(blocked_ips)} IPs",
                f"Threshold: {threshold} incidents/{window_minutes}min. Block duration: {block_hours}h.",
                "critical" if len(blocked_ips) >= 5 else "warning",
            )
        except Exception:
            pass

        logger.info(f"IP auto-block: {len(blocked_ips)} blocked, {len(skipped)} skipped")

        return {
            "status": "blocked",
            "blocked_count": len(blocked_ips),
            "blocked_ips": blocked_ips,
            "released_count": len(released_blocks),
            "released_blocks": released_blocks,
            "skipped": len(skipped),
            "threshold": threshold,
            "window_minutes": window_minutes,
            "block_duration_hours": block_hours,
            "email_sent": email_sent,
        }

    except Exception as e:
        logger.error(f"IP auto-block check failed: {e}")
        return {"status": "error", "message": str(e)}
