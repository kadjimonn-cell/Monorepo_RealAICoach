"""IP Geolocation service — uses ip-api.com (free, no key required) with MongoDB caching."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from math import radians, sin, cos, sqrt, atan2

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = 30
_BATCH_SIZE = 100  # ip-api.com batch limit
_PRIVATE_PREFIXES = (
    "10.",
    "172.16",
    "172.17",
    "172.18",
    "172.19",
    "172.2",
    "172.3",
    "192.168",
    "127.",
    "0.",
    "169.254",
    "fc",
    "fd",
    "fe80",
)


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in _PRIVATE_PREFIXES)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points on Earth in km."""
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = radians(lat1), radians(lon1), radians(lat2), radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


async def lookup_ip(db, ip: str) -> Optional[dict]:
    """Resolve a single IP to geolocation, using cache first."""
    if not ip or ip == "N/A" or _is_private(ip):
        return None

    cached = await db.ip_geolocation.find_one({"ip": ip}, {"_id": 0})
    if cached:
        cached_at = cached.get("cached_at")
        if isinstance(cached_at, str):
            try:
                cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            except Exception:
                cached_at = None
        if cached_at and (
            datetime.now(timezone.utc) - cached_at.replace(tzinfo=timezone.utc)
            if cached_at.tzinfo is None
            else datetime.now(timezone.utc) - cached_at
        ) < timedelta(days=_CACHE_TTL_DAYS):
            return cached

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,lat,lon,isp,org,as,query"
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    geo = {
                        "ip": ip,
                        "country": data.get("country", ""),
                        "country_code": data.get("countryCode", ""),
                        "region": data.get("regionName", ""),
                        "city": data.get("city", ""),
                        "lat": data.get("lat", 0),
                        "lon": data.get("lon", 0),
                        "isp": data.get("isp", ""),
                        "org": data.get("org", ""),
                        "as_name": data.get("as", ""),
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.ip_geolocation.update_one({"ip": ip}, {"$set": geo}, upsert=True)
                    return geo
    except Exception as e:
        logger.warning(f"IP geolocation lookup failed for {ip}: {e}")
    return None


async def batch_lookup_ips(db, ips: list[str]) -> dict[str, dict]:
    """Batch lookup multiple IPs. Uses cache first, then batch API for misses."""
    results: dict[str, dict] = {}
    to_fetch: list[str] = []

    public_ips = [ip for ip in set(ips) if ip and ip != "N/A" and not _is_private(ip)]
    if not public_ips:
        return results

    # Check cache
    cached = await db.ip_geolocation.find({"ip": {"$in": public_ips}}, {"_id": 0}).to_list(len(public_ips))
    now = datetime.now(timezone.utc)
    for c in cached:
        cached_at = c.get("cached_at")
        if isinstance(cached_at, str):
            try:
                cached_at = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            except Exception:
                cached_at = None
        if cached_at:
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            if (now - cached_at) < timedelta(days=_CACHE_TTL_DAYS):
                results[c["ip"]] = c
                continue
        to_fetch.append(c["ip"])

    for ip in public_ips:
        if ip not in results and ip not in to_fetch:
            to_fetch.append(ip)

    # Batch fetch from ip-api.com (max 100 per request)
    for i in range(0, len(to_fetch), _BATCH_SIZE):
        batch = to_fetch[i : i + _BATCH_SIZE]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "http://ip-api.com/batch?fields=status,country,countryCode,regionName,city,lat,lon,isp,org,as,query",
                    json=[{"query": ip} for ip in batch],
                )
                if resp.status_code == 200:
                    for data in resp.json():
                        if data.get("status") == "success":
                            ip = data.get("query", "")
                            geo = {
                                "ip": ip,
                                "country": data.get("country", ""),
                                "country_code": data.get("countryCode", ""),
                                "region": data.get("regionName", ""),
                                "city": data.get("city", ""),
                                "lat": data.get("lat", 0),
                                "lon": data.get("lon", 0),
                                "isp": data.get("isp", ""),
                                "org": data.get("org", ""),
                                "as_name": data.get("as", ""),
                                "cached_at": now.isoformat(),
                            }
                            results[ip] = geo
                            await db.ip_geolocation.update_one({"ip": ip}, {"$set": geo}, upsert=True)
        except Exception as e:
            logger.warning(f"Batch IP geolocation failed: {e}")
        if i + _BATCH_SIZE < len(to_fetch):
            await asyncio.sleep(1.5)  # rate limit: 45 req/min

    return results


def detect_impossible_travel(sessions_with_geo: list[dict], max_speed_kmh: float = 900) -> list[dict]:
    """Detect impossible travel: sessions from locations that can't be reached in the time gap.
    max_speed_kmh=900 allows for commercial flights (~850-950 km/h).
    """
    flags = []
    sorted_sessions = sorted(sessions_with_geo, key=lambda s: s.get("ts", ""))

    for i in range(1, len(sorted_sessions)):
        prev = sorted_sessions[i - 1]
        curr = sorted_sessions[i]

        plat, plon = prev.get("lat"), prev.get("lon")
        clat, clon = curr.get("lat"), curr.get("lon")
        if not all([plat, plon, clat, clon]):
            continue
        if plat == clat and plon == clon:
            continue

        dist_km = _haversine_km(plat, plon, clat, clon)
        if dist_km < 50:
            continue

        pts = prev.get("ts", "")
        cts = curr.get("ts", "")
        try:
            if isinstance(pts, str):
                pt = datetime.fromisoformat(pts.replace("Z", "+00:00"))
            else:
                pt = pts
            if isinstance(cts, str):
                ct = datetime.fromisoformat(cts.replace("Z", "+00:00"))
            else:
                ct = cts
            if pt.tzinfo is None:
                pt = pt.replace(tzinfo=timezone.utc)
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        hours = max((ct - pt).total_seconds() / 3600, 0.01)
        speed = dist_km / hours

        if speed > max_speed_kmh:
            flags.append(
                {
                    "type": "impossible_travel",
                    "severity": "critical",
                    "detail": f"{prev.get('city', '?')}, {prev.get('country_code', '?')} -> {curr.get('city', '?')}, {curr.get('country_code', '?')} ({int(dist_km)} km in {hours:.1f}h = {int(speed)} km/h)",
                    "from_ip": prev.get("ip", ""),
                    "to_ip": curr.get("ip", ""),
                    "from_location": f"{prev.get('city', '')}, {prev.get('country_code', '')}",
                    "to_location": f"{curr.get('city', '')}, {curr.get('country_code', '')}",
                    "distance_km": round(dist_km),
                    "time_hours": round(hours, 2),
                    "speed_kmh": round(speed),
                }
            )

    return flags
