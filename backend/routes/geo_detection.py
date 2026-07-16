"""Geo-based Country Auto-Detection — IP-based country detection for signup/login."""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import logging
import httpx

from .db import db, require_auth

router = APIRouter(prefix="/geo")
logger = logging.getLogger(__name__)

# Country metadata
COUNTRIES = {
    "US": {
        "name": "United States",
        "code": "US",
        "region": "north_america",
        "currency": "USD",
        "otp_methods": ["email", "sms"],
    },
    "CA": {
        "name": "Canada",
        "code": "CA",
        "region": "north_america",
        "currency": "CAD",
        "otp_methods": ["email", "sms"],
    },
    "GB": {"name": "United Kingdom", "code": "GB", "region": "europe", "currency": "GBP", "otp_methods": ["email"]},
    "FR": {"name": "France", "code": "FR", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "DE": {"name": "Germany", "code": "DE", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "NG": {"name": "Nigeria", "code": "NG", "region": "africa", "currency": "NGN", "otp_methods": ["email"]},
    "GH": {"name": "Ghana", "code": "GH", "region": "africa", "currency": "GHS", "otp_methods": ["email"]},
    "KE": {"name": "Kenya", "code": "KE", "region": "africa", "currency": "KES", "otp_methods": ["email"]},
    "ZA": {"name": "South Africa", "code": "ZA", "region": "africa", "currency": "ZAR", "otp_methods": ["email"]},
    "CM": {"name": "Cameroon", "code": "CM", "region": "africa", "currency": "XAF", "otp_methods": ["email"]},
    "SN": {"name": "Senegal", "code": "SN", "region": "africa", "currency": "XOF", "otp_methods": ["email"]},
    "IN": {"name": "India", "code": "IN", "region": "asia", "currency": "INR", "otp_methods": ["email"]},
    "CN": {"name": "China", "code": "CN", "region": "asia", "currency": "CNY", "otp_methods": ["email"]},
    "JP": {"name": "Japan", "code": "JP", "region": "asia", "currency": "JPY", "otp_methods": ["email"]},
    "BR": {"name": "Brazil", "code": "BR", "region": "south_america", "currency": "BRL", "otp_methods": ["email"]},
    "AU": {"name": "Australia", "code": "AU", "region": "oceania", "currency": "AUD", "otp_methods": ["email"]},
    "EG": {"name": "Egypt", "code": "EG", "region": "africa", "currency": "EGP", "otp_methods": ["email"]},
    "MA": {"name": "Morocco", "code": "MA", "region": "africa", "currency": "MAD", "otp_methods": ["email"]},
    "CH": {"name": "Switzerland", "code": "CH", "region": "europe", "currency": "CHF", "otp_methods": ["email"]},
    "NL": {"name": "Netherlands", "code": "NL", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "BE": {"name": "Belgium", "code": "BE", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "IT": {"name": "Italy", "code": "IT", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "ES": {"name": "Spain", "code": "ES", "region": "europe", "currency": "EUR", "otp_methods": ["email"]},
    "SE": {"name": "Sweden", "code": "SE", "region": "europe", "currency": "SEK", "otp_methods": ["email"]},
    "MX": {"name": "Mexico", "code": "MX", "region": "north_america", "currency": "MXN", "otp_methods": ["email"]},
    "KR": {"name": "South Korea", "code": "KR", "region": "asia", "currency": "KRW", "otp_methods": ["email"]},
    "AE": {"name": "United Arab Emirates", "code": "AE", "region": "middle_east", "currency": "AED", "otp_methods": ["email"]},
    "SA": {"name": "Saudi Arabia", "code": "SA", "region": "middle_east", "currency": "SAR", "otp_methods": ["email"]},
    "TR": {"name": "Turkey", "code": "TR", "region": "europe", "currency": "TRY", "otp_methods": ["email"]},
    "RU": {"name": "Russia", "code": "RU", "region": "europe", "currency": "RUB", "otp_methods": ["email"]},
    "PL": {"name": "Poland", "code": "PL", "region": "europe", "currency": "PLN", "otp_methods": ["email"]},
    "TH": {"name": "Thailand", "code": "TH", "region": "asia", "currency": "THB", "otp_methods": ["email"]},
    "BJ": {"name": "Benin", "code": "BJ", "region": "africa", "currency": "XOF", "otp_methods": ["email"]},
    "TG": {"name": "Togo", "code": "TG", "region": "africa", "currency": "XOF", "otp_methods": ["email"]},
    "CI": {"name": "Côte d'Ivoire", "code": "CI", "region": "africa", "currency": "XOF", "otp_methods": ["email"]},
    "NE": {"name": "Niger", "code": "NE", "region": "africa", "currency": "XOF", "otp_methods": ["email"]},
}


def _extract_client_ip(request: Request) -> str:
    """Extract real client IP from request headers (handles proxies)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _is_private_ip(ip: str) -> bool:
    """Check if IP is private/local."""
    return (
        not ip
        or ip == "unknown"
        or ip.startswith("10.")
        or ip.startswith("172.")
        or ip.startswith("192.168.")
        or ip.startswith("127.")
        or ip == "::1"
    )


async def detect_country_from_ip(ip: str) -> str:
    """Detect country from IP — cached ip-api lookup first, ipapi.co as fallback."""
    if _is_private_ip(ip):
        return "US"
    try:
        from utils.ip_geolocation import lookup_ip
        geo = await lookup_ip(db, ip)
        code = str((geo or {}).get("country_code", "")).strip().upper()
        if len(code) == 2:
            return code
    except Exception as e:
        logger.warning(f"Cached geo lookup failed for {ip}: {e}")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"https://ipapi.co/{ip}/country/")
            if resp.status_code == 200 and len(resp.text.strip()) == 2:
                return resp.text.strip().upper()
    except Exception as e:
        logger.warning(f"Geo-detection failed for {ip}: {e}")
    return "US"


@router.get("/detect")
async def detect_country(request: Request):
    """Auto-detect user's country from IP address."""
    ip = _extract_client_ip(request)
    country_code = await detect_country_from_ip(ip)
    default_meta = {
        "name": country_code,
        "code": country_code,
        "region": "other",
        "currency": "USD",
        "otp_methods": ["email"],
    }
    country = COUNTRIES.get(country_code, default_meta)

    return {
        "detected_country": country_code,
        "country_name": country.get("name", country_code),
        "region": country.get("region", "other"),
        "default_currency": country.get("currency", "USD"),
        "otp_methods": country.get("otp_methods", ["email"]),
        "is_us": country_code == "US",
        "ip_address": ip,
    }


@router.get("/countries")
async def list_countries(request: Request):
    """List all supported countries."""
    return {"countries": list(COUNTRIES.values())}


@router.post("/set-country")
async def set_user_country(request: Request):
    """User manually sets their country."""
    user = await require_auth(request)
    body = await request.json()
    country_code = body.get("country_code", "US").upper()

    if country_code not in COUNTRIES:
        raise HTTPException(status_code=400, detail=f"Unsupported country: {country_code}")

    country = COUNTRIES[country_code]

    await db.user_security.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "country": country_code,
                "country_name": country["name"],
                "region": country["region"],
                "is_us_resident": country_code == "US",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    return {"success": True, "country": country}


@router.get("/my-country")
async def get_my_country(request: Request):
    """Get user's saved country."""
    user = await require_auth(request)
    security = await db.user_security.find_one(
        {"user_id": user.user_id}, {"_id": 0, "country": 1, "country_name": 1, "region": 1, "is_us_resident": 1}
    )

    if not security or not security.get("country"):
        # Auto-detect
        ip = _extract_client_ip(request)
        code = await detect_country_from_ip(ip)
        country = COUNTRIES.get(code, COUNTRIES["US"])
        return {
            "country": code,
            "country_name": country["name"],
            "region": country["region"],
            "is_us_resident": code == "US",
            "auto_detected": True,
        }

    return {
        "country": security.get("country"),
        "country_name": security.get("country_name"),
        "region": security.get("region"),
        "is_us_resident": security.get("is_us_resident", False),
        "auto_detected": False,
    }
