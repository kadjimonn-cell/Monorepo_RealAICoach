"""Database security hardening utilities (global platform-level controls).

Provides index hardening + environment posture checks and persists an audit
snapshot so ops can verify hardening is active.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import logging
import os

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SECURITY_INDEX_SPECS: list[dict[str, Any]] = [
    {"collection": "users", "keys": [("user_id", 1)], "kwargs": {"name": "idx_users_user_id"}},
    {"collection": "users", "keys": [("email", 1)], "kwargs": {"sparse": True, "name": "idx_users_email_sparse"}},
    {"collection": "user_sessions", "keys": [("session_token", 1)], "kwargs": {"name": "idx_sessions_token"}},
    {"collection": "user_sessions", "keys": [("user_id", 1), ("expires_at", -1)], "kwargs": {"name": "idx_sessions_user_exp"}},
    {"collection": "security_incidents", "keys": [("ts", -1), ("code", 1)], "kwargs": {"name": "idx_security_incidents_ts_code"}},
    {"collection": "gtec_scan_c5_reports", "keys": [("task_id", 1)], "kwargs": {"unique": True, "name": "idx_gtec_c5_reports_task_uq"}},
    {"collection": "gtec_scan_c5_reports", "keys": [("generated_at", -1)], "kwargs": {"name": "idx_gtec_c5_reports_generated"}},
    {"collection": "gtec_scan_c5_incidents", "keys": [("incident_id", 1)], "kwargs": {"unique": True, "name": "idx_gtec_c5_incidents_id_uq"}},
    {"collection": "gtec_scan_c5_incidents", "keys": [("status", 1), ("updated_at", -1)], "kwargs": {"name": "idx_gtec_c5_incidents_status_updated"}},
    {"collection": "gtec_c5_release_certificates", "keys": [("certificate_id", 1)], "kwargs": {"unique": True, "name": "idx_gtec_c5_cert_id_uq"}},
]


def _env_security_posture() -> dict[str, Any]:
    field_encryption_key = bool(str(os.environ.get("FIELD_ENCRYPTION_KEY") or "").strip())
    # Lookup HMAC falls back to FIELD_ENCRYPTION_KEY (see utils/field_encryption.py)
    field_lookup_hmac = bool(str(os.environ.get("FIELD_LOOKUP_HMAC_KEY") or "").strip()) or field_encryption_key
    jwt_secret = bool(str(os.environ.get("JWT_SECRET") or "").strip())
    mongo_url = str(os.environ.get("MONGO_URL") or "")
    tls_hint = "+srv" in mongo_url or "tls=true" in mongo_url.lower()
    return {
        "field_encryption_key_present": field_encryption_key,
        "field_lookup_hmac_key_present": field_lookup_hmac,
        "jwt_secret_present": jwt_secret,
        "mongo_tls_hint": tls_hint,
    }


async def ensure_db_security_hardening(db) -> dict[str, Any]:
    created_indexes: list[str] = []
    failed_indexes: list[dict[str, str]] = []

    for spec in SECURITY_INDEX_SPECS:
        collection = spec["collection"]
        keys = spec["keys"]
        kwargs = spec.get("kwargs", {})
        try:
            name = await db[collection].create_index(keys, maxTimeMS=5000, **kwargs)
            created_indexes.append(str(name))
        except Exception as exc:
            if getattr(exc, "code", None) == 85 or "IndexOptionsConflict" in str(exc) or "already exists with a different name" in str(exc):
                created_indexes.append(f"{collection}:equivalent_exists")
                continue
            logger.warning("db-hardening index create failed collection=%s keys=%s err=%s", collection, keys, exc)
            failed_indexes.append({
                "collection": collection,
                "keys": str(keys),
                "error": str(exc),
            })

    posture = _env_security_posture()
    # mongo_tls_hint is informational (TLS is infra-managed; in-cluster Mongo has no +srv/tls flag)
    required_posture = [v for k, v in posture.items() if k != "mongo_tls_hint"]
    status = "healthy" if not failed_indexes and all(required_posture) else "degraded"
    doc = {
        "status": status,
        "created_indexes": created_indexes,
        "failed_indexes": failed_indexes,
        "posture": posture,
        "checked_at": _now_iso(),
        "security_version": "2026.05.pro",
    }
    await db.db_security_hardening_audit.insert_one(dict(doc))
    await db.platform_security_state.update_one(
        {"_id": "db_hardening"},
        {"$set": {**{k: v for k, v in doc.items() if k != "_id"}, "updated_at": _now_iso()}},
        upsert=True,
    )
    safe_doc = dict(doc)
    safe_doc.pop("_id", None)
    return safe_doc


async def get_db_security_hardening_status(db) -> dict[str, Any]:
    latest = await db.db_security_hardening_audit.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])
    if latest:
        return latest
    return {
        "status": "unknown",
        "created_indexes": [],
        "failed_indexes": [],
        "posture": _env_security_posture(),
        "checked_at": _now_iso(),
        "security_version": "2026.05.pro",
    }
