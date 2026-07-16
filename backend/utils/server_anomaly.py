"""Shared anomaly-detection helpers for server routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging


async def detect_admin_anomalies(db) -> dict:
    anomalies = []
    now = datetime.now(timezone.utc)
    last_24h = (now - timedelta(hours=24)).isoformat()
    last_7d = (now - timedelta(days=7)).isoformat()

    brute_force_pipeline = [
        {"$match": {"event_type": "login_failed", "timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$ip_address", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$match": {"count": {"$gte": 5}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    async for doc in db.security_events.aggregate(brute_force_pipeline):
        anomalies.append({
            "type": "brute_force",
            "severity": "critical" if doc["count"] >= 10 else "high",
            "title": f"Brute force attempt from {doc['_id']}",
            "description": f"{doc['count']} failed login attempts in the last 24 hours",
            "ip": doc["_id"],
            "count": doc["count"],
            "last_seen": doc["last"],
        })

    rate_limit_pipeline = [
        {"$match": {"event_type": {"$in": ["admin_rate_limit", "login_rate_limit"]}, "timestamp": {"$gte": last_7d}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$match": {"count": {"$gte": 10}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    async for doc in db.security_events.aggregate(rate_limit_pipeline):
        uid = doc["_id"]
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1}) if uid else None
        anomalies.append({
            "type": "rate_limit_abuse",
            "severity": "high" if doc["count"] >= 50 else "medium",
            "title": f"Rate limit abuse: {user['email'] if user else uid or 'Unknown'}",
            "description": f"{doc['count']} rate limit hits in the last 7 days",
            "user_id": uid,
            "user_email": user["email"] if user else None,
            "count": doc["count"],
            "last_seen": doc["last"],
        })

    jwt_pipeline = [
        {"$match": {"event_type": "jwt_invalid", "timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$ip_address", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$match": {"count": {"$gte": 5}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    async for doc in db.security_events.aggregate(jwt_pipeline):
        anomalies.append({
            "type": "token_abuse",
            "severity": "high",
            "title": f"Invalid token flood from {doc['_id']}",
            "description": f"{doc['count']} invalid JWT attempts in 24 hours — possible token theft or replay attack",
            "ip": doc["_id"],
            "count": doc["count"],
            "last_seen": doc["last"],
        })

    blocked_pipeline = [
        {"$match": {"event_type": "blocked_ip", "timestamp": {"$gte": last_7d}}},
        {"$group": {"_id": "$ip_address", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$match": {"count": {"$gte": 3}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    async for doc in db.security_events.aggregate(blocked_pipeline):
        anomalies.append({
            "type": "persistent_blocked_ip",
            "severity": "medium",
            "title": f"Persistent blocked IP: {doc['_id']}",
            "description": f"Blocked IP made {doc['count']} attempts in the last 7 days",
            "ip": doc["_id"],
            "count": doc["count"],
            "last_seen": doc["last"],
        })

    multi_ip_pipeline = [
        {"$match": {"event_type": "login_success", "timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$user_id", "ips": {"$addToSet": "$ip_address"}, "count": {"$sum": 1}}},
        {"$addFields": {"ip_count": {"$size": "$ips"}}},
        {"$match": {"ip_count": {"$gte": 3}}},
        {"$sort": {"ip_count": -1}},
        {"$limit": 10},
    ]
    async for doc in db.security_events.aggregate(multi_ip_pipeline):
        uid = doc["_id"]
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1}) if uid else None
        anomalies.append({
            "type": "multi_ip_login",
            "severity": "medium",
            "title": f"Multi-IP login: {user['email'] if user else uid or 'Unknown'}",
            "description": f"Logged in from {doc['ip_count']} different IPs in 24 hours ({doc['count']} sessions)",
            "user_id": uid,
            "user_email": user["email"] if user else None,
            "ips": doc["ips"][:5],
            "count": doc["count"],
        })

    admin_denied_pipeline = [
        {"$match": {"event_type": "admin_access_denied", "timestamp": {"$gte": last_7d}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
        {"$match": {"count": {"$gte": 3}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    async for doc in db.security_events.aggregate(admin_denied_pipeline):
        uid = doc["_id"]
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1}) if uid else None
        anomalies.append({
            "type": "privilege_escalation",
            "severity": "high",
            "title": f"Privilege escalation attempt: {user['email'] if user else uid or 'Unknown'}",
            "description": f"{doc['count']} unauthorized admin access attempts in 7 days",
            "user_id": uid,
            "user_email": user["email"] if user else None,
            "count": doc["count"],
            "last_seen": doc["last"],
        })

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    anomalies.sort(key=lambda a: severity_order.get(a["severity"], 99))
    summary = {
        "total_anomalies": len(anomalies),
        "critical": sum(1 for a in anomalies if a["severity"] == "critical"),
        "high": sum(1 for a in anomalies if a["severity"] == "high"),
        "medium": sum(1 for a in anomalies if a["severity"] == "medium"),
        "low": sum(1 for a in anomalies if a["severity"] == "low"),
        "scan_time": now.isoformat(),
    }
    return {"anomalies": anomalies, "summary": summary}


async def detect_alerting_anomalies(db):
    payload = await detect_admin_anomalies(db)
    return payload["anomalies"], payload["summary"]


async def run_anomaly_alert_check(db):
    from utils.email_service import is_email_configured
    from utils.ws_manager import push_admin_alert

    logger = logging.getLogger("anomaly_alerting")
    try:
        settings = await db.anomaly_alert_settings.find_one({"key": "settings"}, {"_id": 0})
        if not settings:
            settings = {"enabled": True, "email_enabled": True, "min_severity": "high"}
            await db.anomaly_alert_settings.update_one({"key": "settings"}, {"$set": settings}, upsert=True)
        if not settings.get("enabled", True):
            return

        anomalies, _summary = await detect_alerting_anomalies(db)
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        min_sev = settings.get("min_severity", "high")
        min_sev_val = sev_order.get(min_sev, 1)
        filtered = [a for a in anomalies if sev_order.get(a["severity"], 3) <= min_sev_val]
        if not filtered:
            return

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=6)).isoformat()
        new_anomalies = []
        for anomaly in filtered:
            key = f"{anomaly['type']}:{anomaly.get('ip', '')}:{anomaly.get('user_id', '')}:{anomaly.get('user_email', '')}"
            existing = await db.anomaly_alerts.find_one({"alert_key": key, "alerted_at": {"$gte": cutoff}}, {"_id": 0})
            if not existing:
                new_anomalies.append(anomaly)
                await db.anomaly_alerts.insert_one(
                    {
                        "alert_key": key,
                        "anomaly": {k: v for k, v in anomaly.items() if k != "_id"},
                        "alerted_at": now.isoformat(),
                        "severity": anomaly["severity"],
                    }
                )
        if not new_anomalies:
            return

        crit_count = sum(1 for a in new_anomalies if a["severity"] == "critical")
        high_count = sum(1 for a in new_anomalies if a["severity"] == "high")
        title = f"{len(new_anomalies)} new security anomal{'y' if len(new_anomalies) == 1 else 'ies'} detected"
        parts = []
        if crit_count:
            parts.append(f"{crit_count} critical")
        if high_count:
            parts.append(f"{high_count} high")
        await push_admin_alert(
            "anomaly_detected",
            title,
            f"Severity: {', '.join(parts) or 'medium'}. Check Activity Log for details.",
            "critical" if crit_count else "warning",
            extra={
                "anomaly_count": len(new_anomalies),
                "anomalies": [{"type": a["type"], "severity": a["severity"], "title": a["title"]} for a in new_anomalies[:5]],
            },
        )

        if settings.get("email_enabled", True) and is_email_configured():
            from utils.email_service import send_catalog_template

            admin_users = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).to_list(20)
            for admin in admin_users:
                try:
                    await send_catalog_template(
                        recipient_email=admin["email"],
                        template_key="server_anomaly_alert",
                        anomaly_count=len(new_anomalies),
                        anomaly_details="; ".join(a.get("description", "Unknown anomaly") for a in new_anomalies[:3]),
                    )
                except Exception as exc:
                    logger.error("Failed to email anomaly alert to %s: %s", admin["email"], exc)
        logger.info("Anomaly alerting: %s new alerts sent to admins", len(new_anomalies))
    except Exception as exc:
        logger.error("Anomaly alert check failed: %s", exc)