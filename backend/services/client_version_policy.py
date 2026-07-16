"""Client version policy — DB-backed min-version enforcement for native clients.

Single source of truth consumed by the bootstrap endpoint, the enforcement
middleware and the admin management routes. Fail-open by design: DB errors,
missing headers or unparseable versions never block a request.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

PLATFORM_KEYS = ("android", "ios", "expo", "default")
DEFAULT_ENTRY = {
    "min_supported_version": "1.0.0",
    "latest_version": "1.0.0",
    "update_url": "",
    "enforced": True,
}
_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, Any] = {"data": None, "expires": 0.0}

_VERSION_RE = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(raw) -> Optional[tuple]:
    match = _VERSION_RE.match(str(raw or ""))
    if not match:
        return None
    return tuple(int(group or 0) for group in match.groups())


def resolve_platform_key(header_value: str) -> str:
    value = str(header_value or "").strip().lower()
    return value if value in ("android", "ios", "expo") else "default"


def invalidate_policy_cache() -> None:
    _cache["data"] = None
    _cache["expires"] = 0.0


async def get_client_version_policy(force: bool = False) -> dict:
    now = time.monotonic()
    if not force and _cache["data"] is not None and now < _cache["expires"]:
        return _cache["data"]

    policy = {key: dict(DEFAULT_ENTRY) for key in PLATFORM_KEYS}
    try:
        from routes.db import db
        async for doc in db.client_version_policy.find({}):
            key = str(doc.get("platform") or "").lower()
            if key not in PLATFORM_KEYS:
                continue
            for field in DEFAULT_ENTRY:
                if field in doc and doc[field] is not None:
                    policy[key][field] = doc[field]
    except Exception:
        return policy  # fail-open, do not cache a partial read

    _cache["data"] = policy
    _cache["expires"] = now + _CACHE_TTL_SECONDS
    return policy


async def update_platform_policy(platform: str, updates: dict, actor_id: str) -> dict:
    from routes.db import db

    platform = str(platform).lower()
    clean = {k: updates[k] for k in DEFAULT_ENTRY if k in updates and updates[k] is not None}
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.client_version_policy.update_one(
        {"platform": platform},
        {"$set": {**clean, "platform": platform, "updated_at": now_iso, "updated_by": actor_id}},
        upsert=True,
    )
    await db.client_version_policy_audit.insert_one(
        {"platform": platform, "changes": clean, "actor_id": actor_id, "at": now_iso}
    )
    invalidate_policy_cache()
    policy = await get_client_version_policy(force=True)
    return policy[platform]


async def evaluate_version_block(platform_header: str, app_version: str) -> Optional[dict]:
    client_version = parse_version(app_version)
    if client_version is None:
        return None

    key = resolve_platform_key(platform_header)
    policy = await get_client_version_policy()
    entry = policy.get(key) or DEFAULT_ENTRY
    if not entry.get("enforced", True):
        return None

    minimum = parse_version(entry.get("min_supported_version"))
    if minimum is None or client_version >= minimum:
        return None

    return {
        "detail": "This app version is no longer supported. Please update to continue.",
        "code": "CLIENT_UPDATE_REQUIRED",
        "platform": key,
        "client_version": str(app_version).strip(),
        "min_supported_version": entry.get("min_supported_version"),
        "latest_version": entry.get("latest_version"),
        "update_url": entry.get("update_url") or "",
    }
