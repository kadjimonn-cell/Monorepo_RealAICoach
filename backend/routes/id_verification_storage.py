"""Shared object storage helpers for ID verification uploads."""

from __future__ import annotations

from typing import Optional
import os

from fastapi import HTTPException
import requests

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
ID_CHECKER_STORAGE_PREFIX = "realaicoach-id-checker"
_storage_key: Optional[str] = None


def init_storage_key() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY is missing for object storage")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_storage_object(path: str, data: bytes, content_type: str) -> dict:
    global _storage_key
    key = init_storage_key()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type or "application/octet-stream"},
        data=data,
        timeout=120,
    )
    if resp.status_code == 403:
        _storage_key = None
        key = init_storage_key()
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type or "application/octet-stream"},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_storage_object(path: str) -> tuple[bytes, str]:
    global _storage_key
    key = init_storage_key()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 403:
        _storage_key = None
        key = init_storage_key()
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, (resp.headers.get("Content-Type") or "application/octet-stream")