"""Admin Session Management — view/revoke active user sessions + suspicious activity detection."""

from fastapi import APIRouter, Request
import re
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from routes.db import db, require_admin
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/admin/sessions", tags=["Admin Sessions"])


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_end_date") or row.get("subscription_expires_at") or row.get("subscription_end"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )

# Known datacenter / VPN / cloud provider IP prefixes (first 2 octets)
_DATACENTER_PREFIXES = {
    "10.": "Internal/Private",
    "172.16": "Private Range",
    "192.168": "Private Range",
    "34.": "Google Cloud",
    "35.": "Google Cloud",
    "52.": "AWS",
    "54.": "AWS",
    "13.": "AWS",
    "104.": "Cloudflare/GCP",
    "162.158": "Cloudflare",
    "198.41": "Cloudflare",
    "141.101": "Cloudflare",
    "157.240": "Meta",
    "185.220": "Tor Exit",
    "23.128": "Tor Exit",
    "199.249": "Tor Exit",
    "51.": "Azure",
    "40.": "Azure",
    "20.": "Azure",
}

BOT_UA_PATTERNS = ["bot", "crawler", "spider", "curl", "wget", "python", "http", "scraper", "scan"]


async def _collect_cursor_docs(cursor, batch_size: int = 1000):
    docs = []
    while True:
        batch = await cursor.to_list(length=batch_size)
        if not batch:
            break
        docs.extend(batch)
    return docs


def _classify_ip(ip: str) -> str | None:
    """Return a label if the IP matches a known datacenter/VPN prefix."""
    if not ip or ip == "N/A":
        return None
    for prefix, label in _DATACENTER_PREFIXES.items():
        if ip.startswith(prefix):
            return label
    return None


def _classify_ua(ua: str) -> str | None:
    """Return a flag if the user-agent looks suspicious."""
    if not ua or ua == "N/A" or len(ua) < 5:
        return "Missing/Empty UA"
    ua_lower = ua.lower()
    for pattern in BOT_UA_PATTERNS:
        if pattern in ua_lower:
            return f"Bot-like ({pattern})"
    return None


@router.get("")
async def list_active_sessions(request: Request, page: int = 1, limit: int = 25, search: str = ""):
    """List all active sessions with user info."""
    await require_admin(request)
    query: dict = {}
    if search:
        user_ids = await db.users.find(
            {
                "$or": [
                    {"email": {"$regex": re.escape(str(search)), "$options": "i"}},
                    {"name": {"$regex": re.escape(str(search)), "$options": "i"}},
                    {"user_id": {"$regex": re.escape(str(search)), "$options": "i"}},
                ]
            },
            {"_id": 0, "user_id": 1},
        ).to_list(200)
        uids = [u["user_id"] for u in user_ids]
        if uids:
            query["user_id"] = {"$in": uids}
        else:
            return {"sessions": [], "total": 0, "page": page, "pages": 0}

    total = await db.user_sessions.count_documents(query)
    skip = (page - 1) * limit
    sessions = (
        await db.user_sessions.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    )

    user_ids = list({s["user_id"] for s in sessions})
    users_map = {}
    if user_ids:
        users = await db.users.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_end": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
        ).to_list(500)
        users_map = {u["user_id"]: u for u in users}

    enriched = []
    for s in sessions:
        user_info = users_map.get(s["user_id"], {})
        created = s.get("created_at")
        if isinstance(created, datetime):
            created = created.isoformat()
        enriched.append(
            {
                "user_id": s["user_id"],
                "session_id": s.get("session_id", ""),
                "session_token": s.get("session_token", "")[:12] + "...",
                "ip_address": s.get("ip_address", "N/A"),
                "user_agent": s.get("user_agent", "N/A"),
                "created_at": created,
                "expires_at": s.get("expires_at").isoformat()
                if isinstance(s.get("expires_at"), datetime)
                else s.get("expires_at"),
                "email": user_info.get("email", "Unknown"),
                "name": user_info.get("name", "Unknown"),
                "plan": _effective_plan_from_user_doc(user_info),
                "is_admin": user_info.get("is_admin", False),
            }
        )

    pages = max(1, -(-total // limit))
    return {"sessions": enriched, "total": total, "page": page, "pages": pages}


@router.delete("/{session_identifier}")
async def revoke_session(request: Request, session_identifier: str):
    """Revoke a specific session by session_id or token prefix."""
    await require_admin(request)
    safe_prefix = re.escape(str(session_identifier))
    lookup = {
        "$or": [
            {"session_id": session_identifier},
            {"session_token": session_identifier},
            {"session_token": {"$regex": f"^{safe_prefix}"}},
        ]
    }
    result = await db.user_sessions.delete_one(lookup)
    if result.deleted_count == 0:
        return JSONResponse({"detail": "Session not found"}, status_code=404)
    return {"status": "revoked", "deleted": 1}


@router.delete("/user/{user_id}")
async def revoke_user_sessions(request: Request, user_id: str):
    """Revoke all sessions for a specific user."""
    await require_admin(request)
    result = await db.user_sessions.delete_many({"user_id": user_id})
    return {"status": "revoked", "deleted": result.deleted_count, "user_id": user_id}


@router.get("/stats")
async def session_stats(request: Request):
    """Get session statistics."""
    await require_admin(request)
    total = await db.user_sessions.count_documents({})
    unique_users = len(await db.user_sessions.distinct("user_id"))

    pipeline = [
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_users_raw = await db.user_sessions.aggregate(pipeline).to_list(5)
    top_user_ids = [t["_id"] for t in top_users_raw]
    top_users_info = {}
    if top_user_ids:
        users = await db.users.find(
            {"user_id": {"$in": top_user_ids}}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}
        ).to_list(10)
        top_users_info = {u["user_id"]: u for u in users}

    top_users = []
    for t in top_users_raw:
        info = top_users_info.get(t["_id"], {})
        top_users.append(
            {
                "user_id": t["_id"],
                "email": info.get("email", "Unknown"),
                "name": info.get("name", "Unknown"),
                "session_count": t["count"],
            }
        )

    return {
        "total_sessions": total,
        "unique_users": unique_users,
        "top_users": top_users,
    }


@router.get("/suspicious")
async def detect_suspicious_sessions(request: Request, page: int = 1, limit: int = 100):
    """Analyze all active sessions and flag suspicious activity patterns with pagination."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    
    # Pagination
    limit = min(limit, 500)  # Max 500 per page
    skip = (page - 1) * limit
    
    # Get paginated sessions
    sessions_cursor = db.user_sessions.find({}, {"_id": 0}).skip(skip).limit(limit)
    all_sessions = await _collect_cursor_docs(sessions_cursor)
    await db.user_sessions.count_documents({})
    
    # Enrich with user info
    user_ids = list({s["user_id"] for s in all_sessions})
    users_map = {}
    if user_ids:
        users = await _collect_cursor_docs(
            db.users.find(
                {"user_id": {"$in": user_ids}},
                {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_end": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
            )
        )
        users_map = {u["user_id"]: u for u in users}

    # Group sessions by user
    by_user: dict[str, list] = defaultdict(list)
    for s in all_sessions:
        by_user[s["user_id"]].append(s)

    flagged = []
    risk_summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for uid, user_sessions in by_user.items():
        user_info = users_map.get(uid, {})
        flags: list[dict] = []
        risk_score = 0

        # 1. Multiple distinct IPs
        ips = list({s.get("ip_address", "N/A") for s in user_sessions if s.get("ip_address", "N/A") != "N/A"})
        if len(ips) > 2:
            flags.append(
                {"type": "multi_ip", "severity": "high", "detail": f"{len(ips)} distinct IPs detected", "ips": ips[:6]}
            )
            risk_score += 30

        # 2. Rapid session creation (>5 in 1 hour)
        recent_count = 0
        for sess in user_sessions:
            ct = sess.get("created_at")
            if isinstance(ct, datetime):
                ct_aware = ct.replace(tzinfo=timezone.utc) if ct.tzinfo is None else ct
                if ct_aware > one_hour_ago:
                    recent_count += 1
            elif isinstance(ct, str):
                try:
                    parsed = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed > one_hour_ago:
                        recent_count += 1
                except Exception:
                    pass
        if recent_count > 5:
            flags.append(
                {"type": "rapid_creation", "severity": "high", "detail": f"{recent_count} sessions in last hour"}
            )
            risk_score += 35

        # 3. Excessive total sessions
        if len(user_sessions) > 20:
            flags.append(
                {"type": "excessive_sessions", "severity": "medium", "detail": f"{len(user_sessions)} active sessions"}
            )
            risk_score += 15
        elif len(user_sessions) > 50:
            flags.append(
                {
                    "type": "excessive_sessions",
                    "severity": "critical",
                    "detail": f"{len(user_sessions)} active sessions",
                }
            )
            risk_score += 40

        # 4. Datacenter / VPN / Tor IPs
        for ip in ips:
            ip_label = _classify_ip(ip)
            if ip_label and "Tor" in ip_label:
                flags.append(
                    {"type": "tor_exit", "severity": "critical", "detail": f"Tor exit node detected: {ip}", "ip": ip}
                )
                risk_score += 50
            elif ip_label and ip_label not in ("Internal/Private", "Private Range"):
                flags.append(
                    {"type": "datacenter_ip", "severity": "medium", "detail": f"{ip_label} IP: {ip}", "ip": ip}
                )
                risk_score += 10

        # 5. Bot-like or missing user agents
        for s in user_sessions:
            ua_flag = _classify_ua(s.get("user_agent", ""))
            if ua_flag:
                flags.append(
                    {
                        "type": "suspicious_ua",
                        "severity": "low",
                        "detail": ua_flag,
                        "ua": s.get("user_agent", "N/A")[:60],
                    }
                )
                risk_score += 5
                break  # one flag per user is enough

        # 6. IP Geolocation + Impossible Travel
        if len(ips) >= 2:
            try:
                from utils.ip_geolocation import batch_lookup_ips, detect_impossible_travel

                geo_map = await batch_lookup_ips(db, ips)
                sessions_with_geo = []
                for sess in user_sessions:
                    ip = sess.get("ip_address", "N/A")
                    geo = geo_map.get(ip)
                    if geo:
                        ct = sess.get("created_at")
                        if isinstance(ct, datetime):
                            ct_str = ct.isoformat()
                        elif isinstance(ct, str):
                            ct_str = ct
                        else:
                            ct_str = ""
                        sessions_with_geo.append(
                            {
                                "ip": ip,
                                "lat": geo.get("lat", 0),
                                "lon": geo.get("lon", 0),
                                "city": geo.get("city", ""),
                                "country_code": geo.get("country_code", ""),
                                "ts": ct_str,
                            }
                        )
                travel_flags = detect_impossible_travel(sessions_with_geo)
                for tf in travel_flags:
                    flags.append(tf)
                    risk_score += 50  # impossible travel is critical
                # Enrich with location data
                geo_locations = []
                for ip in ips:
                    g = geo_map.get(ip)
                    if g:
                        geo_locations.append(
                            {
                                "ip": ip,
                                "city": g.get("city", ""),
                                "country": g.get("country", ""),
                                "country_code": g.get("country_code", ""),
                                "isp": g.get("isp", ""),
                            }
                        )
            except Exception as e:
                geo_locations = []
                import logging

                logging.getLogger(__name__).warning(f"Geolocation error for {uid}: {e}")
        else:
            geo_locations = []

        if not flags:
            continue

        risk_score = min(risk_score, 100)
        level = (
            "critical" if risk_score >= 70 else "high" if risk_score >= 40 else "medium" if risk_score >= 20 else "low"
        )
        risk_summary[level] += 1

        created_times = []
        for s in user_sessions:
            ct = s.get("created_at")
            if isinstance(ct, datetime):
                created_times.append(ct.isoformat())
            elif isinstance(ct, str):
                created_times.append(ct)

        flagged.append(
            {
                "user_id": uid,
                "email": user_info.get("email", "Unknown"),
                "name": user_info.get("name", "Unknown"),
                "plan": _effective_plan_from_user_doc(user_info),
                "is_admin": user_info.get("is_admin", False),
                "session_count": len(user_sessions),
                "distinct_ips": ips[:6],
                "locations": geo_locations[:6],
                "risk_score": risk_score,
                "risk_level": level,
                "flags": flags,
                "latest_session": max(created_times) if created_times else None,
            }
        )

    flagged.sort(key=lambda x: x["risk_score"], reverse=True)

    result = {
        "total_flagged": len(flagged),
        "risk_summary": risk_summary,
        "flagged_users": flagged[:50],
        "scanned_sessions": len(all_sessions),
        "scanned_users": len(by_user),
        "timestamp": now.isoformat(),
    }

    # Trigger email alerts if configured
    try:
        from routes.admin_session_alerts import check_and_send_alerts

        await check_and_send_alerts(result)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Session alert check error: {e}")

    return result


@router.get("/geo-summary")
async def session_geo_summary(request: Request, page: int = 1, limit: int = 100):
    """Aggregate active sessions by geolocation for map visualization with pagination."""
    await require_admin(request)
    
    # Pagination
    limit = min(limit, 500)  # Max 500 per page
    skip = (page - 1) * limit
    
    # Get paginated sessions
    sessions_cursor = db.user_sessions.find({}, {"_id": 0}).skip(skip).limit(limit)
    all_sessions = await _collect_cursor_docs(sessions_cursor)
    await db.user_sessions.count_documents({})
    
    if not all_sessions:
        return {
            "markers": [],
            "total_sessions": 0,
            "geolocated": 0,
            "pagination": {"page": page, "limit": limit, "total": 0, "pages": 0}
        }

    # Collect unique IPs and user info
    user_ids = list({s["user_id"] for s in all_sessions})
    users_map = {}
    if user_ids:
        users = await _collect_cursor_docs(
            db.users.find(
                {"user_id": {"$in": user_ids}},
                {"_id": 0, "user_id": 1, "email": 1, "name": 1},
            )
        )
        users_map = {u["user_id"]: u for u in users}

    # Group sessions by IP
    ip_sessions: dict[str, list] = defaultdict(list)
    for s in all_sessions:
        ip = s.get("ip_address", "N/A")
        if ip and ip != "N/A":
            ip_sessions[ip].append(s)

    unique_ips = list(ip_sessions.keys())

    # Batch geolocation lookup
    try:
        from utils.ip_geolocation import batch_lookup_ips

        geo_map = await batch_lookup_ips(db, unique_ips)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Geo summary lookup error: {e}")
        geo_map = {}

    # Build markers — cluster by rounded lat/lon (0.5 degree = ~55km)
    clusters: dict[str, dict] = {}
    for ip, sessions_list in ip_sessions.items():
        geo = geo_map.get(ip)
        if not geo or not geo.get("lat") or not geo.get("lon"):
            continue
        lat = round(geo["lat"] * 2) / 2
        lon = round(geo["lon"] * 2) / 2
        key = f"{lat},{lon}"
        if key not in clusters:
            clusters[key] = {
                "lat": geo["lat"],
                "lon": geo["lon"],
                "city": geo.get("city", ""),
                "country": geo.get("country", ""),
                "country_code": geo.get("country_code", ""),
                "isp": geo.get("isp", ""),
                "session_count": 0,
                "user_count": 0,
                "ips": [],
                "users": [],
            }
        c = clusters[key]
        c["session_count"] += len(sessions_list)
        c["ips"].append(ip)
        for sess in sessions_list:
            uid = sess["user_id"]
            uinfo = users_map.get(uid, {})
            email = uinfo.get("email", "Unknown")
            if email not in [u["email"] for u in c["users"]]:
                c["users"].append({"email": email, "user_id": uid})
        c["user_count"] = len(c["users"])

    markers = sorted(clusters.values(), key=lambda m: m["session_count"], reverse=True)
    # Cap users list per marker for payload size
    for m in markers:
        m["users"] = m["users"][:5]
        m["ips"] = m["ips"][:5]

    return {
        "markers": markers[:100],
        "total_sessions": len(all_sessions),
        "geolocated": sum(m["session_count"] for m in markers),
        "unique_locations": len(markers),
    }


@router.get("/live-feed")
async def session_live_feed(request: Request, seconds: int = 60):
    """Return sessions created in the last N seconds with geolocation data."""
    await require_admin(request)

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=min(seconds, 300))

    # Find recent sessions (created_at stored as datetime in MongoDB)
    recent = (
        await db.user_sessions.find(
            {"created_at": {"$gte": cutoff}},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(50)
    )

    if not recent:
        return {"events": [], "count": 0, "window_seconds": seconds}

    # Lookup user info
    user_ids = list({s["user_id"] for s in recent})
    users = await db.users.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(500)
    users_map = {u["user_id"]: u for u in users}

    # Batch geo lookup for unique IPs
    unique_ips = list({s.get("ip_address", "") for s in recent if s.get("ip_address")})
    geo_map = {}
    if unique_ips:
        try:
            from utils.ip_geolocation import batch_lookup_ips

            geo_map = await batch_lookup_ips(db, unique_ips)
        except Exception:
            pass

    events = []
    for s in recent:
        ip = s.get("ip_address", "N/A")
        geo = geo_map.get(ip, {})
        uinfo = users_map.get(s["user_id"], {})
        ca = s.get("created_at", "")
        events.append(
            {
                "session_id": s.get("session_id", ""),
                "user_id": s["user_id"],
                "email": uinfo.get("email", "Unknown"),
                "name": uinfo.get("name", ""),
                "ip_address": ip,
                "device": s.get("device_info", "Unknown"),
                "created_at": ca.isoformat() if hasattr(ca, "isoformat") else str(ca),
                "city": geo.get("city", ""),
                "country": geo.get("country", ""),
                "country_code": geo.get("country_code", ""),
                "lat": geo.get("lat"),
                "lon": geo.get("lon"),
                "isp": geo.get("isp", ""),
            }
        )

    return {"events": events, "count": len(events), "window_seconds": seconds}


@router.get("/anomalies")
async def session_anomalies(request: Request, window_minutes: int = 10):
    """Detect login anomalies in recent sessions."""
    await require_admin(request)

    window = min(window_minutes, 60)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)

    recent_cursor = db.user_sessions.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0, "user_id": 1, "ip_address": 1, "created_at": 1, "device_info": 1},
    ).sort("created_at", -1)
    recent = await _collect_cursor_docs(recent_cursor)

    if not recent:
        return {"anomalies": [], "summary": {"critical": 0, "warning": 0, "info": 0}, "window_minutes": window}

    # Lookup user info
    user_ids = list({s["user_id"] for s in recent})
    users = await _collect_cursor_docs(
        db.users.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1, "email": 1},
        )
    )
    email_map = {u["user_id"]: u.get("email", "Unknown") for u in users}

    anomalies = []
    now = datetime.now(timezone.utc)

    # 1. Rapid-fire IP detection: same IP with 5+ sessions in 60s bursts
    ip_times: dict[str, list] = defaultdict(list)
    for s in recent:
        ip = s.get("ip_address", "")
        if ip:
            ip_times[ip].append(s["created_at"])

    for ip, times in ip_times.items():
        times.sort()
        for i in range(len(times)):
            window_end = times[i] + timedelta(seconds=60)
            burst = [t for t in times[i:] if t <= window_end]
            if len(burst) >= 5:
                anomalies.append(
                    {
                        "type": "rapid_fire_ip",
                        "severity": "critical",
                        "title": "Rapid-Fire Logins",
                        "description": f"{len(burst)} sessions from IP {ip} in 60 seconds",
                        "ip_address": ip,
                        "count": len(burst),
                        "detected_at": now.isoformat(),
                        "window_start": times[i].isoformat(),
                    }
                )
                break  # one alert per IP

    # 2. Session flooding: single user with 10+ sessions in window
    user_sessions_map: dict[str, list] = defaultdict(list)
    for s in recent:
        user_sessions_map[s["user_id"]].append(s)

    for uid, sessions in user_sessions_map.items():
        if len(sessions) >= 10:
            anomalies.append(
                {
                    "type": "session_flood",
                    "severity": "warning",
                    "title": "Session Flooding",
                    "description": f"{email_map.get(uid, uid)} created {len(sessions)} sessions in {window}min",
                    "email": email_map.get(uid, "Unknown"),
                    "user_id": uid,
                    "count": len(sessions),
                    "detected_at": now.isoformat(),
                }
            )

    # 3. IP hopping: same user from 3+ different IPs in window
    for uid, sessions in user_sessions_map.items():
        unique_ips = list({s.get("ip_address", "") for s in sessions if s.get("ip_address")})
        if len(unique_ips) >= 3:
            anomalies.append(
                {
                    "type": "ip_hopping",
                    "severity": "warning",
                    "title": "IP Hopping Detected",
                    "description": f"{email_map.get(uid, uid)} logged in from {len(unique_ips)} different IPs",
                    "email": email_map.get(uid, "Unknown"),
                    "user_id": uid,
                    "ips": unique_ips[:5],
                    "count": len(unique_ips),
                    "detected_at": now.isoformat(),
                }
            )

    # 4. Unusual hours: sessions created between 1am-5am UTC
    off_hours = [s for s in recent if 1 <= s["created_at"].hour < 5]
    if len(off_hours) >= 3:
        off_users = list({s["user_id"] for s in off_hours})
        anomalies.append(
            {
                "type": "unusual_hours",
                "severity": "info",
                "title": "Off-Hours Activity",
                "description": f"{len(off_hours)} sessions between 1-5 AM UTC from {len(off_users)} user(s)",
                "count": len(off_hours),
                "user_count": len(off_users),
                "detected_at": now.isoformat(),
            }
        )

    # Sort by severity
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    anomalies.sort(key=lambda a: sev_order.get(a["severity"], 3))

    summary = {
        "critical": sum(1 for a in anomalies if a["severity"] == "critical"),
        "warning": sum(1 for a in anomalies if a["severity"] == "warning"),
        "info": sum(1 for a in anomalies if a["severity"] == "info"),
    }

    return {"anomalies": anomalies, "summary": summary, "window_minutes": window, "sessions_analyzed": len(recent)}


@router.get("/security-overview")
async def security_overview(request: Request):
    """Aggregated security dashboard — all key metrics in one call."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    # Session stats
    total_sessions = await db.user_sessions.count_documents({})
    recent_1h = await db.user_sessions.count_documents({"created_at": {"$gte": hour_ago}})
    recent_24h = await db.user_sessions.count_documents({"created_at": {"$gte": day_ago}})

    # Anomalies (30min window)
    cutoff_30m = now - timedelta(minutes=30)
    recent_sessions = await _collect_cursor_docs(
        db.user_sessions.find(
            {"created_at": {"$gte": cutoff_30m}},
            {"_id": 0, "user_id": 1, "ip_address": 1, "created_at": 1},
        )
    )

    # Quick anomaly count
    ip_times: dict[str, list] = defaultdict(list)
    user_counts: dict[str, int] = defaultdict(int)
    for s in recent_sessions:
        ip = s.get("ip_address", "")
        if ip:
            ip_times[ip].append(s["created_at"])
        user_counts[s["user_id"]] += 1

    anomaly_critical = 0
    anomaly_warning = 0
    for ip, times in ip_times.items():
        times.sort()
        for i in range(len(times)):
            burst = [t for t in times[i:] if t <= times[i] + timedelta(seconds=60)]
            if len(burst) >= 5:
                anomaly_critical += 1
                break
    for uid, count in user_counts.items():
        if count >= 10:
            anomaly_warning += 1

    # Blocked IPs
    blocked_count = await db.blocked_ips.count_documents({})
    auto_blocked = await db.blocked_ips.count_documents({"reason": "auto-response"})
    whitelisted_count = await db.whitelisted_ips.count_documents({})

    # Auto-response stats
    ar_rules = await db.auto_response_rules.find({}, {"_id": 0}).to_list(100)
    active_rules = sum(1 for r in ar_rules if r.get("enabled"))
    total_fired = sum(r.get("trigger_count", 0) for r in ar_rules)
    ar_config = await db.auto_response_config.find_one({"config_id": "scheduler"}, {"_id": 0})
    scheduler_enabled = ar_config.get("enabled", False) if ar_config else False
    last_scan = ar_config.get("last_run") if ar_config else None

    # Recent action log (last 10)
    recent_actions = await db.auto_response_log.find({}, {"_id": 0}).sort("executed_at", -1).to_list(10)

    # Recent blocks (last 5)
    recent_blocks = await db.blocked_ips.find({}, {"_id": 0}).sort("blocked_at", -1).to_list(5)

    # Suspicious users count
    suspicious = await db.user_sessions.aggregate(
        [
            {"$match": {"created_at": {"$gte": cutoff_30m}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "total"},
        ]
    ).to_list(1)
    unique_users_30m = suspicious[0]["total"] if suspicious else 0

    # Compute threat level
    threat_score = 0
    threat_score += anomaly_critical * 30
    threat_score += anomaly_warning * 10
    threat_score += min(blocked_count * 5, 20)
    threat_score += min(recent_1h * 2, 20)
    threat_level = "low"
    if threat_score >= 80:
        threat_level = "critical"
    elif threat_score >= 50:
        threat_level = "high"
    elif threat_score >= 25:
        threat_level = "medium"

    # Build timeline (merged recent events)
    timeline = []
    for a in recent_actions[:5]:
        timeline.append(
            {
                "type": "auto_response",
                "title": a.get("rule_name", "Auto-Response"),
                "detail": a.get("result", {}).get("detail", a.get("action", "")),
                "severity": "warning",
                "timestamp": a.get("executed_at", ""),
            }
        )
    for b in recent_blocks[:3]:
        timeline.append(
            {
                "type": "block",
                "title": f"IP Blocked: {b['ip']}",
                "detail": b.get("reason", "unknown"),
                "severity": "critical" if b.get("reason") == "auto-response" else "info",
                "timestamp": b.get("blocked_at", ""),
            }
        )
    if anomaly_critical > 0:
        timeline.append(
            {
                "type": "anomaly",
                "title": f"{anomaly_critical} Critical Anomal{'y' if anomaly_critical == 1 else 'ies'}",
                "detail": "Rapid-fire login patterns detected",
                "severity": "critical",
                "timestamp": now.isoformat(),
            }
        )
    if anomaly_warning > 0:
        timeline.append(
            {
                "type": "anomaly",
                "title": f"{anomaly_warning} Warning Anomal{'y' if anomaly_warning == 1 else 'ies'}",
                "detail": "Session flooding detected",
                "severity": "warning",
                "timestamp": now.isoformat(),
            }
        )
    # Sort by timestamp desc
    timeline.sort(key=lambda t: t.get("timestamp", ""), reverse=True)

    return {
        "threat_level": threat_level,
        "threat_score": min(threat_score, 100),
        "sessions": {
            "total": total_sessions,
            "last_hour": recent_1h,
            "last_24h": recent_24h,
            "unique_users_30m": unique_users_30m,
        },
        "anomalies": {
            "critical": anomaly_critical,
            "warning": anomaly_warning,
            "total": anomaly_critical + anomaly_warning,
        },
        "blocked_ips": {
            "total": blocked_count,
            "auto": auto_blocked,
            "manual": blocked_count - auto_blocked,
            "whitelisted": whitelisted_count,
        },
        "auto_response": {
            "active_rules": active_rules,
            "total_rules": len(ar_rules),
            "total_fired": total_fired,
            "scheduler_enabled": scheduler_enabled,
            "last_scan": last_scan,
        },
        "timeline": timeline[:10],
    }
