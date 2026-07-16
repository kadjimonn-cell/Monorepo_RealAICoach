"""Emergent Object Storage helper for Learning Hub media and manifests."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_PREFIX = "realaicoach-learning-hub"

_storage_key: Optional[str] = None
_read_cooldown_until = 0.0

READ_TIMEOUT_SECONDS = 8
INIT_TIMEOUT_SECONDS = 12
WRITE_TIMEOUT_SECONDS = 120
READ_COOLDOWN_SECONDS = 120


def _read_cooldown_active() -> bool:
    return _read_cooldown_until > time.time()


def _trip_read_cooldown() -> None:
    global _read_cooldown_until
    _read_cooldown_until = time.time() + READ_COOLDOWN_SECONDS


def _init_storage() -> Optional[str]:
    global _storage_key
    if _storage_key:
        return _storage_key
    if not EMERGENT_KEY:
        logger.warning("Object storage unavailable: EMERGENT_LLM_KEY missing")
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=INIT_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json() if isinstance(resp.json(), dict) else {}
        key = str(payload.get("storage_key") or "").strip()
        if not key:
            logger.warning("Object storage init returned empty storage key")
            return None
        _storage_key = key
        return _storage_key
    except Exception as exc:
        logger.warning(f"Object storage init failed: {exc}")
        return None


def storage_enabled() -> bool:
    return bool(_init_storage())


def put_bytes(path: str, content: bytes, content_type: str) -> Optional[dict]:
    key = _init_storage()
    if not key:
        return None
    try:
        clean_path = str(path or "").strip().lstrip("/")
        if not clean_path:
            return None
        resp = requests.put(
            f"{STORAGE_URL}/objects/{clean_path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=content,
            timeout=WRITE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), dict) else None
    except Exception as exc:
        logger.warning(f"Object storage put failed ({path}): {exc}")
        return None


def put_json(path: str, payload: dict) -> Optional[dict]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return put_bytes(path, body, "application/json")


def get_bytes(path: str) -> Optional[Tuple[bytes, str]]:
    key = _init_storage()
    if not key:
        return None
    if _read_cooldown_active():
        return None
    try:
        clean_path = str(path or "").strip().lstrip("/")
        if not clean_path:
            return None
        resp = requests.get(
            f"{STORAGE_URL}/objects/{clean_path}",
            headers={"X-Storage-Key": key},
            timeout=READ_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code in {429} or resp.status_code >= 500:
            _trip_read_cooldown()
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return resp.content, content_type
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status_code, int) and (status_code in {429} or status_code >= 500):
            _trip_read_cooldown()
        logger.warning(f"Object storage get failed ({path}): {exc}")
        return None


def object_exists(path: str) -> bool:
    data = get_bytes(path)
    return bool(data)
