"""App Store Connect API Service — Real integration using JWT (ES256) authentication."""

import os
import time
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

ASC_BASE = "https://api.appstoreconnect.apple.com/v1"
_token_cache = {"token": None, "expires_at": 0}


def _generate_jwt() -> str:
    """Generate a JWT for App Store Connect API using the .p8 private key."""
    from authlib.jose import jwt as ajwt

    key_id = os.environ.get("ASC_KEY_ID")
    issuer_id = os.environ.get("ASC_ISSUER_ID")
    key_path = os.environ.get("ASC_PRIVATE_KEY_PATH")

    if not all([key_id, issuer_id, key_path]):
        raise ValueError("Missing ASC_KEY_ID, ASC_ISSUER_ID, or ASC_PRIVATE_KEY_PATH")

    with open(key_path, "r") as f:
        private_key = f.read()

    now = int(time.time())
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 1200,  # 20 minutes max
        "aud": "appstoreconnect-v1",
    }
    token = ajwt.encode(header, payload, private_key)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def get_token() -> str:
    """Get a cached or fresh JWT."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]
    token = _generate_jwt()
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + 1140  # refresh 1 minute before expiry
    return token


async def _asc_get(path: str, params: dict = None) -> dict:
    """Make an authenticated GET to App Store Connect API."""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{ASC_BASE}{path}", headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def list_apps() -> list:
    """Fetch all apps from App Store Connect."""
    try:
        data = await _asc_get("/apps", params={"fields[apps]": "name,bundleId,sku,primaryLocale"})
        apps = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            apps.append({
                "id": item["id"],
                "name": attrs.get("name"),
                "bundle_id": attrs.get("bundleId"),
                "sku": attrs.get("sku"),
                "primary_locale": attrs.get("primaryLocale"),
            })
        return apps
    except Exception as e:
        logger.error(f"ASC list_apps failed: {e}")
        return []


async def get_app_info(app_id: str) -> dict:
    """Fetch detailed app info including version data."""
    try:
        data = await _asc_get(
            f"/apps/{app_id}",
            params={"fields[apps]": "name,bundleId,sku,primaryLocale,contentRightsDeclaration,isOrEverWasMadeForKids"},
        )
        attrs = data.get("data", {}).get("attributes", {})
        return {
            "id": app_id,
            "name": attrs.get("name"),
            "bundle_id": attrs.get("bundleId"),
            "sku": attrs.get("sku"),
            "primary_locale": attrs.get("primaryLocale"),
        }
    except Exception as e:
        logger.error(f"ASC get_app_info failed: {e}")
        return {}


async def get_app_versions(app_id: str) -> list:
    """Fetch app store versions for an app."""
    try:
        data = await _asc_get(
            f"/apps/{app_id}/appStoreVersions",
            params={
                "fields[appStoreVersions]": "versionString,appStoreState,releaseType,createdDate",
                "limit": 10,
            },
        )
        versions = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            versions.append({
                "id": item["id"],
                "version": attrs.get("versionString"),
                "state": attrs.get("appStoreState"),
                "release_type": attrs.get("releaseType"),
                "created": attrs.get("createdDate"),
            })
        return versions
    except Exception as e:
        logger.error(f"ASC get_app_versions failed: {e}")
        return []


async def get_sales_report(vendor_number: str, frequency: str = "DAILY", report_date: str = None) -> dict:
    """Download sales/trends report. Returns parsed data or error."""
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        if not report_date:
            report_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")

        params = {
            "filter[vendorNumber]": vendor_number,
            "filter[frequency]": frequency,
            "filter[reportDate]": report_date,
            "filter[reportSubType]": "SUMMARY",
            "filter[reportType]": "SALES",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{ASC_BASE}/salesReports",
                headers=headers,
                params=params,
            )
            if resp.status_code == 200:
                import gzip
                import io
                import csv
                try:
                    raw = gzip.decompress(resp.content)
                    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t")
                    rows = list(reader)
                    return {"status": "ok", "report_date": report_date, "frequency": frequency, "rows": rows, "count": len(rows)}
                except Exception:
                    return {"status": "ok", "report_date": report_date, "raw_length": len(resp.content)}
            else:
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                return {"status": "error", "code": resp.status_code, "detail": body}
    except Exception as e:
        logger.error(f"ASC sales report failed: {e}")
        return {"status": "error", "detail": str(e)}


async def get_finance_report(vendor_number: str, region_code: str = "US", report_date: str = None) -> dict:
    """Download finance report."""
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        if not report_date:
            report_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m")

        params = {
            "filter[vendorNumber]": vendor_number,
            "filter[regionCode]": region_code,
            "filter[reportDate]": report_date,
            "filter[reportType]": "FINANCIAL",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{ASC_BASE}/financeReports",
                headers=headers,
                params=params,
            )
            if resp.status_code == 200:
                import gzip
                import io
                import csv
                try:
                    raw = gzip.decompress(resp.content)
                    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t")
                    rows = list(reader)
                    return {"status": "ok", "report_date": report_date, "rows": rows, "count": len(rows)}
                except Exception:
                    return {"status": "ok", "report_date": report_date, "raw_length": len(resp.content)}
            else:
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                return {"status": "error", "code": resp.status_code, "detail": body}
    except Exception as e:
        logger.error(f"ASC finance report failed: {e}")
        return {"status": "error", "detail": str(e)}


async def get_connection_status() -> dict:
    """Test the App Store Connect API connection."""
    try:
        apps = await list_apps()
        return {
            "connected": True,
            "apps_found": len(apps),
            "apps": apps,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
