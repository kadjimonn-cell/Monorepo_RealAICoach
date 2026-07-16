"""ATS & HRIS Integration Connectors.

Webhook-based connectors for Greenhouse, Lever, Workday.
Import/export candidates, jobs, and interview data.
Real sync engine with credential validation, data persistence,
incremental sync, and scheduled auto-sync.
"""

from fastapi import APIRouter, HTTPException, Request, Query
import re
from datetime import datetime, timezone, timedelta
import uuid
import logging
import httpx
from typing import Any
import hashlib
import hmac
import json
import secrets

from .db import db, require_auth, require_admin
from utils.field_encryption import encrypt_field, decrypt_field, is_encrypted

router = APIRouter(prefix="/integrations")
logger = logging.getLogger("routes.ats_integrations")

SYNC_LOCK_TTL_SECONDS = 10 * 60
SCHEDULE_ALLOWED_HOURS = {0, 1, 6, 12, 24, 48, 72, 168}
SENSITIVE_CREDENTIAL_HINTS = ("key", "secret", "token", "password", "client_id")
TEST_MODE_SEED_RETENTION_HOURS = 72
WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = 5 * 60
WEBHOOK_REPLAY_TTL_SECONDS = 24 * 60 * 60


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _is_sensitive_field(field_name: str) -> bool:
    lowered = str(field_name or "").strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in SENSITIVE_CREDENTIAL_HINTS)


def _encrypt_credentials_for_storage(credentials: dict[str, Any]) -> dict[str, Any]:
    secured: dict[str, Any] = {}
    for field, value in (credentials or {}).items():
        if isinstance(value, str) and value and _is_sensitive_field(field):
            try:
                secured[field] = encrypt_field(value)
            except Exception:
                # Fail-open for availability, while keeping runtime stable.
                secured[field] = value
        else:
            secured[field] = value
    return secured


def _decrypt_credentials_for_runtime(credentials: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    runtime_credentials: dict[str, Any] = {}
    found_plain_sensitive = False
    for field, value in (credentials or {}).items():
        if isinstance(value, str) and value and _is_sensitive_field(field):
            if is_encrypted(value):
                try:
                    runtime_credentials[field] = decrypt_field(value)
                except Exception:
                    runtime_credentials[field] = value
            else:
                runtime_credentials[field] = value
                found_plain_sensitive = True
        else:
            runtime_credentials[field] = value
    return runtime_credentials, found_plain_sensitive


def _build_sync_health(config: dict[str, Any]) -> dict[str, Any]:
    sync = (config or {}).get("sync_status") or {}
    errors = int(sync.get("errors") or 0)
    records = int(sync.get("records_synced") or 0)
    if errors > 0:
        status = "degraded"
        score = max(30, 70 - min(errors * 10, 40))
    elif records > 0:
        status = "healthy"
        score = 92
    else:
        status = "idle"
        score = 78
    return {
        "status": status,
        "score": score,
        "records_synced": records,
        "errors": errors,
        "last_sync": sync.get("last_sync"),
    }


def _sanitize_config_for_response(config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(config or {})
    payload.pop("_id", None)
    payload.pop("credentials", None)
    payload["sync_health"] = _build_sync_health(payload)
    payload["has_credentials"] = bool((config or {}).get("credentials"))
    return payload


def _raise_structured_error(status_code: int, code: str, message: str, **extra):
    detail = {
        "error_code": code,
        "message": message,
        **extra,
    }
    raise HTTPException(status_code=status_code, detail=detail)


def _encrypt_webhook_secret(secret_value: str) -> str:
    if not secret_value:
        return ""
    try:
        return encrypt_field(secret_value)
    except Exception:
        return secret_value


def _decrypt_webhook_secret(secret_value: str) -> str:
    if not secret_value:
        return ""
    try:
        if is_encrypted(secret_value):
            return decrypt_field(secret_value)
    except Exception:
        pass
    return secret_value


def _generate_webhook_signing_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(24)}"


def _compute_webhook_signature(secret_value: str, timestamp: int, raw_body: bytes) -> str:
    payload = f"{timestamp}.".encode("utf-8") + raw_body
    digest = hmac.new(secret_value.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _extract_webhook_signature(raw_signature: str) -> str:
    signature = str(raw_signature or "").strip()
    if not signature:
        return ""
    if "=" in signature:
        prefix, value = signature.split("=", 1)
        if prefix.lower().strip() != "sha256":
            return ""
        return f"sha256={value.strip()}"
    return ""


def _parse_iso_datetime(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    try:
        text = str(raw_value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _cleanup_test_mode_seed_connectors(
    *,
    retention_hours: int = TEST_MODE_SEED_RETENTION_HOURS,
    dry_run: bool = False,
    triggered_by: str = "manual",
) -> dict[str, Any]:
    now = _now_utc()
    hours = max(1, min(int(retention_hours or TEST_MODE_SEED_RETENTION_HOURS), 24 * 45))
    cutoff = now - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    configs = await db.integration_configs.find(
        {
            "test_mode": True,
            "$or": [
                {"updated_at": {"$lte": cutoff_iso}},
                {"created_at": {"$lte": cutoff_iso}},
            ],
        },
        {"_id": 0, "config_id": 1, "integration_id": 1, "user_id": 1, "created_at": 1, "updated_at": 1},
    ).to_list(1000)

    candidates_deleted = 0
    jobs_deleted = 0
    logs_deleted = 0
    configs_deleted = 0

    for config in configs:
        config_id = str(config.get("config_id") or "")
        integration_id = str(config.get("integration_id") or "")
        user_id = str(config.get("user_id") or "")
        if not config_id or not user_id:
            continue

        if dry_run:
            continue

        cand_res = await db.ats_candidates.delete_many({"user_id": user_id, "integration_id": integration_id})
        job_res = await db.ats_jobs.delete_many({"user_id": user_id, "integration_id": integration_id})
        log_res = await db.sync_logs.delete_many({"config_id": config_id})
        cfg_res = await db.integration_configs.delete_one({"config_id": config_id, "user_id": user_id, "test_mode": True})

        candidates_deleted += int(cand_res.deleted_count or 0)
        jobs_deleted += int(job_res.deleted_count or 0)
        logs_deleted += int(log_res.deleted_count or 0)
        configs_deleted += int(cfg_res.deleted_count or 0)

    run_summary = {
        "success": True,
        "dry_run": bool(dry_run),
        "retention_hours": hours,
        "cutoff_iso": cutoff_iso,
        "expired_configs": len(configs),
        "deleted": {
            "configs": configs_deleted,
            "ats_candidates": candidates_deleted,
            "ats_jobs": jobs_deleted,
            "sync_logs": logs_deleted,
        },
        "triggered_by": triggered_by,
        "created_at": _now_iso(),
    }

    await db.integration_seed_cleanup_runs.insert_one({**run_summary})
    return run_summary


async def _maybe_run_seed_cleanup_from_scheduler() -> dict[str, Any] | None:
    policy_doc = await db.integration_runtime_policies.find_one(
        {"key": "test_mode_seed_cleanup_policy"},
        {"_id": 0, "value": 1},
    )
    policy = (policy_doc or {}).get("value") if isinstance((policy_doc or {}).get("value"), dict) else {}
    enabled = bool(policy.get("enabled", True))
    if not enabled:
        return None

    latest_scheduler_run = await db.integration_seed_cleanup_runs.find_one(
        {"triggered_by": "scheduler:ats_auto_sync"},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    latest_run_dt = _parse_iso_datetime((latest_scheduler_run or {}).get("created_at"))
    now_dt = _now_utc()
    if latest_run_dt and (now_dt - latest_run_dt).total_seconds() < (6 * 60 * 60):
        return None

    retention_hours = int(policy.get("retention_hours") or TEST_MODE_SEED_RETENTION_HOURS)
    dry_run = bool(policy.get("dry_run", False))
    return await _cleanup_test_mode_seed_connectors(
        retention_hours=retention_hours,
        dry_run=dry_run,
        triggered_by="scheduler:ats_auto_sync",
    )


async def _acquire_sync_lock(config_id: str, user_id: str) -> str | None:
    now = _now_utc()
    token = f"lock_{uuid.uuid4().hex[:12]}"
    expires_at = now + timedelta(seconds=SYNC_LOCK_TTL_SECONDS)
    result = await db.integration_configs.update_one(
        {
            "config_id": config_id,
            "user_id": user_id,
            "$or": [
                {"sync_lock": {"$exists": False}},
                {"sync_lock.expires_at": {"$lte": now}},
                {"sync_lock.user_id": user_id},
            ],
        },
        {
            "$set": {
                "sync_lock": {
                    "token": token,
                    "user_id": user_id,
                    "acquired_at": _now_iso(),
                    "expires_at": expires_at,
                }
            }
        },
    )
    if result.modified_count <= 0:
        return None
    return token


async def _release_sync_lock(config_id: str, user_id: str, token: str) -> None:
    await db.integration_configs.update_one(
        {
            "config_id": config_id,
            "user_id": user_id,
            "sync_lock.token": token,
        },
        {"$unset": {"sync_lock": ""}},
    )

SUPPORTED_INTEGRATIONS = {
    "greenhouse": {
        "name": "Greenhouse",
        "type": "ATS",
        "icon": "leaf",
        "color": "#43A047",
        "fields": ["api_key", "board_token"],
        "webhooks": ["candidate_hired", "interview_scheduled", "job_created"],
        "api_base": "https://harvest.greenhouse.io/v1",
        "auth_type": "basic",
    },
    "lever": {
        "name": "Lever",
        "type": "ATS",
        "icon": "git-branch",
        "color": "#6366F1",
        "fields": ["api_key"],
        "webhooks": ["candidate_stage_change", "interview_created", "offer_created"],
        "api_base": "https://api.lever.co/v1",
        "auth_type": "basic",
    },
    "workday": {
        "name": "Workday",
        "type": "HRIS",
        "icon": "business",
        "color": "#F59E0B",
        "fields": ["tenant_url", "client_id", "client_secret"],
        "webhooks": ["employee_hired", "position_opened", "org_change"],
        "api_base": "",
        "auth_type": "oauth2",
    },
}


async def _validate_greenhouse(creds: dict) -> dict:
    """Validate Greenhouse API credentials by fetching user info."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://harvest.greenhouse.io/v1/users?per_page=1",
                auth=(creds["api_key"], ""),
            )
            if r.status_code == 200:
                return {"valid": True, "message": "Connected to Greenhouse"}
            elif r.status_code == 401:
                return {
                    "valid": False,
                    "message": "Invalid API key. Check Greenhouse > Settings > API Credential Management.",
                }
            return {"valid": False, "message": f"Greenhouse returned {r.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "message": "Greenhouse API timed out. Check network connectivity."}
    except Exception as e:
        return {"valid": False, "message": f"Connection error: {str(e)[:100]}"}


async def _validate_lever(creds: dict) -> dict:
    """Validate Lever API credentials."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.lever.co/v1/postings?limit=1",
                auth=(creds["api_key"], ""),
            )
            if r.status_code == 200:
                return {"valid": True, "message": "Connected to Lever"}
            elif r.status_code == 401:
                return {"valid": False, "message": "Invalid API key. Check Lever > Settings > Integrations."}
            return {"valid": False, "message": f"Lever returned {r.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "message": "Lever API timed out."}
    except Exception as e:
        return {"valid": False, "message": f"Connection error: {str(e)[:100]}"}


async def _validate_workday(creds: dict) -> dict:
    """Validate Workday credentials via OAuth2 token exchange."""
    try:
        tenant_url = creds.get("tenant_url", "").rstrip("/")
        if not tenant_url:
            return {"valid": False, "message": "Tenant URL is required"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{tenant_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                },
            )
            if r.status_code == 200:
                return {"valid": True, "message": "Connected to Workday"}
            elif r.status_code == 401:
                return {
                    "valid": False,
                    "message": "Invalid credentials. Check Workday Integration System User settings.",
                }
            return {"valid": False, "message": f"Workday returned {r.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "message": "Workday tenant timed out. Verify your Tenant URL."}
    except Exception as e:
        return {"valid": False, "message": f"Connection error: {str(e)[:100]}"}


VALIDATORS = {"greenhouse": _validate_greenhouse, "lever": _validate_lever, "workday": _validate_workday}


def _normalize_candidate(raw: dict, source: str) -> dict:
    """Normalize candidate data from different ATS providers into unified schema."""
    now = datetime.now(timezone.utc).isoformat()
    if source == "greenhouse":
        return {
            "source": "greenhouse",
            "external_id": str(raw.get("id", "")),
            "name": f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip(),
            "email": (raw.get("email_addresses") or [{}])[0].get("value", ""),
            "phone": (raw.get("phone_numbers") or [{}])[0].get("value", ""),
            "title": raw.get("title", ""),
            "company": raw.get("company", ""),
            "stage": (raw.get("applications") or [{}])[0].get("current_stage", {}).get("name", ""),
            "status": "active" if not raw.get("is_private") else "private",
            "tags": [t.get("name", "") for t in (raw.get("tags") or [])],
            "created_at_source": raw.get("created_at", ""),
            "synced_at": now,
        }
    elif source == "lever":
        return {
            "source": "lever",
            "external_id": raw.get("id", ""),
            "name": raw.get("name", ""),
            "email": (raw.get("emails") or [""])[0],
            "phone": (raw.get("phones") or [{}])[0].get("value", ""),
            "title": raw.get("headline", ""),
            "company": "",
            "stage": raw.get("stage", ""),
            "status": raw.get("archived", {}).get("reason") if raw.get("archived") else "active",
            "tags": raw.get("tags") or [],
            "created_at_source": raw.get("createdAt", ""),
            "synced_at": now,
        }
    elif source == "workday":
        return {
            "source": "workday",
            "external_id": str(raw.get("id", raw.get("workerId", ""))),
            "name": raw.get("name", raw.get("displayName", "")),
            "email": raw.get("email", raw.get("primaryEmail", "")),
            "phone": raw.get("phone", ""),
            "title": raw.get("jobTitle", raw.get("businessTitle", "")),
            "company": raw.get("organization", ""),
            "stage": raw.get("status", "active"),
            "status": "active",
            "tags": [],
            "created_at_source": raw.get("hireDate", ""),
            "synced_at": now,
        }
    return {"source": source, "external_id": str(raw.get("id", "")), "name": "", "synced_at": now}


def _normalize_job(raw: dict, source: str) -> dict:
    """Normalize job data from different ATS providers."""
    now = datetime.now(timezone.utc).isoformat()
    if source == "greenhouse":
        return {
            "source": "greenhouse",
            "external_id": str(raw.get("id", "")),
            "title": raw.get("name", ""),
            "department": (raw.get("departments") or [{}])[0].get("name", ""),
            "location": (raw.get("offices") or [{}])[0].get("name", ""),
            "status": raw.get("status", "open"),
            "openings": raw.get("openings", []),
            "created_at_source": raw.get("created_at", ""),
            "synced_at": now,
        }
    elif source == "lever":
        return {
            "source": "lever",
            "external_id": raw.get("id", ""),
            "title": raw.get("text", ""),
            "department": raw.get("categories", {}).get("team", ""),
            "location": raw.get("categories", {}).get("location", ""),
            "status": raw.get("state", "published"),
            "openings": [],
            "created_at_source": raw.get("createdAt", ""),
            "synced_at": now,
        }
    return {"source": source, "external_id": str(raw.get("id", "")), "title": "", "synced_at": now}


async def _persist_records(user_id: str, integration_id: str, collection_name: str, records: list):
    """Upsert records into MongoDB with deduplication by (source, external_id, user_id)."""
    stored = 0
    for rec in records:
        rec["user_id"] = user_id
        rec["integration_id"] = integration_id
        await db[collection_name].update_one(
            {"source": rec["source"], "external_id": rec["external_id"], "user_id": user_id},
            {"$set": rec},
            upsert=True,
        )
        stored += 1
    return stored


async def _sync_greenhouse(config: dict) -> dict:
    """Sync candidates and jobs from Greenhouse with data persistence."""
    creds = config.get("credentials", {})
    user_id = config.get("user_id", "")
    last_sync = config.get("sync_status", {}).get("last_sync")
    synced = 0
    errors = 0
    details = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch candidates (incremental if possible)
            url = "https://harvest.greenhouse.io/v1/candidates?per_page=100"
            if last_sync:
                url += f"&updated_after={last_sync}"
            r = await client.get(url, auth=(creds["api_key"], ""))
            if r.status_code == 200:
                candidates = r.json()
                normalized = [_normalize_candidate(c, "greenhouse") for c in candidates]
                stored = await _persist_records(user_id, "greenhouse", "ats_candidates", normalized)
                synced += stored
                details.append(f"{stored} candidates synced")
            else:
                errors += 1
                details.append(f"Candidates fetch failed: {r.status_code}")
            # Fetch jobs
            jurl = "https://harvest.greenhouse.io/v1/jobs?per_page=100"
            if last_sync:
                jurl += f"&updated_after={last_sync}"
            r2 = await client.get(jurl, auth=(creds["api_key"], ""))
            if r2.status_code == 200:
                jobs = r2.json()
                normalized_jobs = [_normalize_job(j, "greenhouse") for j in jobs]
                stored_j = await _persist_records(user_id, "greenhouse", "ats_jobs", normalized_jobs)
                synced += stored_j
                details.append(f"{stored_j} jobs synced")
            else:
                errors += 1
                details.append(f"Jobs fetch failed: {r2.status_code}")
    except Exception as e:
        errors += 1
        details.append(f"Sync error: {str(e)[:80]}")
    return {"synced": synced, "errors": errors, "details": details}


async def _sync_lever(config: dict) -> dict:
    """Sync postings and candidates from Lever with data persistence."""
    creds = config.get("credentials", {})
    user_id = config.get("user_id", "")
    last_sync = config.get("sync_status", {}).get("last_sync")
    synced = 0
    errors = 0
    details = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch postings (jobs)
            url = "https://api.lever.co/v1/postings?limit=100"
            if last_sync:
                url += f"&updated_at_start={int(datetime.fromisoformat(last_sync.replace('Z', '+00:00')).timestamp() * 1000)}"
            r = await client.get(url, auth=(creds["api_key"], ""))
            if r.status_code == 200:
                postings = r.json().get("data", [])
                normalized_jobs = [_normalize_job(p, "lever") for p in postings]
                stored_j = await _persist_records(user_id, "lever", "ats_jobs", normalized_jobs)
                synced += stored_j
                details.append(f"{stored_j} postings synced")
            else:
                errors += 1
                details.append(f"Postings fetch failed: {r.status_code}")
            # Fetch candidates
            curl = "https://api.lever.co/v1/candidates?limit=100"
            r2 = await client.get(curl, auth=(creds["api_key"], ""))
            if r2.status_code == 200:
                candidates = r2.json().get("data", [])
                normalized = [_normalize_candidate(c, "lever") for c in candidates]
                stored = await _persist_records(user_id, "lever", "ats_candidates", normalized)
                synced += stored
                details.append(f"{stored} candidates synced")
            else:
                errors += 1
                details.append(f"Candidates fetch failed: {r2.status_code}")
    except Exception as e:
        errors += 1
        details.append(f"Sync error: {str(e)[:80]}")
    return {"synced": synced, "errors": errors, "details": details}


async def _sync_workday(config: dict) -> dict:
    """Sync employees and positions from Workday with data persistence."""
    creds = config.get("credentials", {})
    user_id = config.get("user_id", "")
    synced = 0
    errors = 0
    details = []
    tenant_url = creds.get("tenant_url", "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Get OAuth token
            tr = await client.post(
                f"{tenant_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                },
            )
            if tr.status_code != 200:
                return {"synced": 0, "errors": 1, "details": ["OAuth token failed"]}
            token = tr.json().get("access_token", "")
            headers = {"Authorization": f"Bearer {token}"}
            # Fetch workers
            r = await client.get(f"{tenant_url}/api/v1/workers?limit=100", headers=headers)
            if r.status_code == 200:
                raw_data = r.json()
                workers = raw_data if isinstance(raw_data, list) else raw_data.get("data", [])
                if isinstance(workers, list):
                    normalized = [_normalize_candidate(w, "workday") for w in workers]
                    stored = await _persist_records(user_id, "workday", "ats_candidates", normalized)
                    synced += stored
                    details.append(f"{stored} workers synced")
            else:
                errors += 1
                details.append(f"Workers fetch failed: {r.status_code}")
    except Exception as e:
        errors += 1
        details.append(f"Sync error: {str(e)[:80]}")
    return {"synced": synced, "errors": errors, "details": details}


SYNC_ENGINES = {"greenhouse": _sync_greenhouse, "lever": _sync_lever, "workday": _sync_workday}


async def _test_mode_sync(config: dict) -> dict:
    """Simulated sync for test mode - generates realistic test records and persists them."""
    import random

    user_id = config.get("user_id", "test_user")
    integration_id = config.get("integration_id", "greenhouse")
    now = datetime.now(timezone.utc).isoformat()

    first_names = ["Sarah", "James", "Maria", "David", "Emma", "Alex", "Priya", "Chen", "Michael", "Aisha"]
    last_names = ["Chen", "Smith", "Garcia", "Johnson", "Williams", "Brown", "Lee", "Patel", "Kim", "Davis"]
    titles = [
        "Software Engineer",
        "Product Manager",
        "Data Scientist",
        "UX Designer",
        "DevOps Engineer",
        "Marketing Lead",
    ]
    companies = ["TechCorp", "InnovateLab", "DataDriven Inc", "DesignHub", "CloudScale", "GrowthWorks"]
    stages = ["Applied", "Phone Screen", "Technical Interview", "Final Round", "Offer", "Hired"]
    job_titles = ["Senior Engineer", "Staff PM", "Lead Designer", "ML Engineer", "Frontend Dev", "Backend Architect"]
    departments = ["Engineering", "Product", "Design", "Marketing", "Sales", "Operations"]
    locations = ["San Francisco, CA", "New York, NY", "Austin, TX", "Seattle, WA", "Remote", "London, UK"]

    num_candidates = random.randint(5, 15)
    num_jobs = random.randint(2, 6)
    candidates = []
    jobs = []

    for i in range(num_candidates):
        fname = random.choice(first_names)
        lname = random.choice(last_names)
        candidates.append(
            {
                "source": integration_id,
                "external_id": f"test_{uuid.uuid4().hex[:8]}",
                "name": f"{fname} {lname}",
                "email": f"{fname.lower()}.{lname.lower()}@example.com",
                "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                "title": random.choice(titles),
                "company": random.choice(companies),
                "stage": random.choice(stages),
                "status": "active",
                "tags": random.sample(["urgent", "referral", "senior", "remote", "diversity"], k=random.randint(0, 2)),
                "created_at_source": now,
                "synced_at": now,
                "user_id": user_id,
                "integration_id": integration_id,
            }
        )

    for i in range(num_jobs):
        jobs.append(
            {
                "source": integration_id,
                "external_id": f"test_job_{uuid.uuid4().hex[:8]}",
                "title": random.choice(job_titles),
                "department": random.choice(departments),
                "location": random.choice(locations),
                "status": random.choice(["open", "open", "open", "closed"]),
                "openings": [],
                "created_at_source": now,
                "synced_at": now,
                "user_id": user_id,
                "integration_id": integration_id,
            }
        )

    stored_c = await _persist_records(user_id, integration_id, "ats_candidates", candidates)
    stored_j = await _persist_records(user_id, integration_id, "ats_jobs", jobs)
    synced = stored_c + stored_j
    return {"synced": synced, "errors": 0, "details": [f"Test mode: {stored_c} candidates, {stored_j} jobs simulated"]}


@router.get("/available")
async def list_available(request: Request):
    """List available integration connectors."""
    await require_auth(request)
    integrations = []
    for iid, info in SUPPORTED_INTEGRATIONS.items():
        integrations.append(
            {
                "id": iid,
                "name": info["name"],
                "type": info["type"],
                "icon": info["icon"],
                "color": info["color"],
                "fields": info["fields"],
                "webhooks": info["webhooks"],
            }
        )
    return {"integrations": integrations}


@router.get("/")
async def list_configured(request: Request):
    """List user's configured integrations."""
    user = await require_auth(request)
    configs = (
        await db.integration_configs.find({"user_id": user.user_id}, {"_id": 0, "credentials": 0})
        .sort("created_at", -1)
        .to_list(20)
    )
    return {
        "integrations": [_sanitize_config_for_response(config) for config in configs],
        "count": len(configs),
    }


@router.post("/")
async def configure_integration(request: Request):
    """Configure a new integration with credential validation."""
    user = await require_auth(request)
    body = await request.json()
    integration_id = str(body.get("integration_id", "")).strip().lower()
    credentials = body.get("credentials", {})
    test_mode = bool(body.get("test_mode", False))

    if not integration_id:
        _raise_structured_error(
            400,
            "integration_id_required",
            "integration_id is required.",
            retryable=False,
            action_hint="Select a connector before continuing.",
        )

    if not isinstance(credentials, dict):
        _raise_structured_error(
            400,
            "invalid_credentials_shape",
            "credentials must be a key/value object.",
            retryable=False,
            action_hint="Provide credential fields as an object.",
        )

    if integration_id not in SUPPORTED_INTEGRATIONS:
        _raise_structured_error(
            400,
            "unsupported_integration",
            f"Unsupported integration: {integration_id}",
            retryable=False,
            action_hint="Choose one of the available connectors.",
        )

    info = SUPPORTED_INTEGRATIONS[integration_id]
    if not test_mode:
        missing = [f for f in info["fields"] if not credentials.get(f)]
        if missing:
            _raise_structured_error(
                400,
                "missing_required_fields",
                f"Missing required fields: {missing}",
                retryable=False,
                action_hint="Complete all required credential fields.",
                missing_fields=missing,
            )

        # Validate credentials against real API
        validator = VALIDATORS.get(integration_id)
        if validator:
            result = await validator(credentials)
            if not result["valid"]:
                _raise_structured_error(
                    400,
                    "credential_validation_failed",
                    str(result["message"]),
                    retryable=False,
                    action_hint="Verify connector credentials and try again.",
                )

    now = _now_iso()
    stored_credentials = _encrypt_credentials_for_storage(credentials)
    webhook_secret = _generate_webhook_signing_secret()
    config = {
        "config_id": f"intg_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "integration_id": integration_id,
        "integration_name": info["name"],
        "integration_type": info["type"],
        "credentials": stored_credentials,
        "enabled_webhooks": body.get("webhooks", info["webhooks"]),
        "test_mode": test_mode,
        "status": "active",
        "sync_status": {"last_sync": None, "records_synced": 0, "errors": 0},
        "sync_health": {"status": "idle", "score": 78},
        "webhook_security": {
            "signature_algorithm": "hmac-sha256",
            "signature_header": "X-Integration-Signature",
            "timestamp_header": "X-Integration-Timestamp",
            "event_id_header": "X-Integration-Event-Id",
            "replay_ttl_seconds": WEBHOOK_REPLAY_TTL_SECONDS,
            "signature_tolerance_seconds": WEBHOOK_SIGNATURE_TOLERANCE_SECONDS,
            "webhook_signing_secret": _encrypt_webhook_secret(webhook_secret),
            "webhook_signing_secret_prefix": webhook_secret[:12],
            "rotated_at": now,
        },
        "seed_policy": {
            "is_test_mode_seed": bool(test_mode),
            "cleanup_eligible_after_hours": TEST_MODE_SEED_RETENTION_HOURS,
        },
        "last_error": None,
        "feature_version": "35.upgrade.v2",
        "created_at": now,
        "updated_at": now,
    }

    # Check for existing config
    existing = await db.integration_configs.find_one({"user_id": user.user_id, "integration_id": integration_id})
    if existing:
        await db.integration_configs.update_one(
            {"user_id": user.user_id, "integration_id": integration_id},
            {"$set": {**config, "config_id": str(existing.get("config_id", config["config_id"]))}},
        )
        config["config_id"] = str(existing.get("config_id", config["config_id"]))
    else:
        await db.integration_configs.insert_one(config)
    return {
        "success": True,
        "config": _sanitize_config_for_response(config),
        "message": "Integration configured successfully.",
        "next_action": "Run sync to import latest records.",
        "webhook_signature_headers": {
            "signature": "X-Integration-Signature",
            "timestamp": "X-Integration-Timestamp",
            "event_id": "X-Integration-Event-Id",
        },
        "webhook_signing_secret": webhook_secret,
        "webhook_secret_hint": webhook_secret[:12],
    }


@router.get("/{config_id}")
async def get_integration(config_id: str, request: Request):
    """Get integration config details (no credentials)."""
    user = await require_auth(request)
    config = await db.integration_configs.find_one(
        {"config_id": config_id, "user_id": user.user_id}, {"_id": 0, "credentials": 0}
    )
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )
    return _sanitize_config_for_response(config)


@router.post("/{config_id}/sync")
async def trigger_sync(config_id: str, request: Request):
    """Trigger a manual sync using the real ATS/HRIS API or test mode."""
    user = await require_auth(request)
    config = await db.integration_configs.find_one({"config_id": config_id, "user_id": user.user_id}, {"_id": 0})
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )

    now = _now_iso()
    integration_id = config["integration_id"]
    lock_token = await _acquire_sync_lock(config_id, user.user_id)
    if not lock_token:
        _raise_structured_error(
            409,
            "sync_already_in_progress",
            "A sync is already in progress for this connector.",
            retryable=True,
            action_hint="Wait for current sync to complete, then retry.",
            retry_after_seconds=30,
        )

    runtime_credentials, found_plain_sensitive = _decrypt_credentials_for_runtime(config.get("credentials") or {})
    runtime_config = {**config, "credentials": runtime_credentials}

    try:
        # Use real sync engine or test mode
        if runtime_config.get("test_mode"):
            result = await _test_mode_sync(runtime_config)
        else:
            engine = SYNC_ENGINES.get(integration_id)
            if engine:
                result = await engine(runtime_config)
            else:
                result = await _test_mode_sync(runtime_config)

        synced = int(result.get("synced") or 0)
        errors = int(result.get("errors") or 0)
        details = result.get("details", [])
        status = "completed" if errors == 0 else "completed_with_errors"
        sync_health = _build_sync_health(
            {
                "sync_status": {
                    "last_sync": now,
                    "records_synced": synced,
                    "errors": errors,
                }
            }
        )

        update_payload: dict[str, Any] = {
            "sync_status.last_sync": now,
            "sync_status.records_synced": synced,
            "sync_status.errors": errors,
            "sync_health": sync_health,
            "last_error": None if errors == 0 else {"at": now, "details": details[:5]},
            "updated_at": now,
        }
        if found_plain_sensitive:
            update_payload["credentials"] = _encrypt_credentials_for_storage(runtime_credentials)

        await db.integration_configs.update_one(
            {"config_id": config_id},
            {"$set": update_payload},
        )

        # Log sync event
        await db.sync_logs.insert_one(
            {
                "log_id": f"sync_{uuid.uuid4().hex[:10]}",
                "config_id": config_id,
                "integration_id": integration_id,
                "user_id": user.user_id,
                "records_synced": synced,
                "errors": errors,
                "details": details,
                "status": status,
                "health_status": sync_health.get("status"),
                "created_at": now,
            }
        )

        return {
            "success": True,
            "records_synced": synced,
            "errors": errors,
            "details": details,
            "sync_time": now,
            "sync_health": sync_health,
            "status": status,
        }
    finally:
        await _release_sync_lock(config_id, user.user_id, lock_token)


@router.get("/{config_id}/logs")
async def get_sync_logs(config_id: str, request: Request):
    """Get sync history for an integration."""
    user = await require_auth(request)
    config = await db.integration_configs.find_one({"config_id": config_id, "user_id": user.user_id}, {"_id": 0})
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )

    logs = await db.sync_logs.find({"config_id": config_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {
        "logs": logs,
        "count": len(logs),
    }


@router.post("/webhook/{integration_id}")
async def handle_webhook(integration_id: str, request: Request):
    """Handle incoming webhook from ATS/HRIS."""
    if integration_id not in SUPPORTED_INTEGRATIONS:
        _raise_structured_error(400, "unknown_integration", "Unknown integration", retryable=False)

    raw_body = await request.body()
    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        _raise_structured_error(400, "invalid_json_payload", "Webhook payload must be valid JSON.", retryable=False)

    now_dt = _now_utc()
    now = now_dt.isoformat()
    config_hint = str(
        request.headers.get("X-Integration-Config-Id")
        or body.get("config_id")
        or ""
    ).strip()

    query: dict[str, Any] = {
        "integration_id": integration_id,
        "status": "active",
    }
    if config_hint:
        query["config_id"] = config_hint

    configs = await db.integration_configs.find(query, {"_id": 0}).limit(3).to_list(3)
    if not configs:
        _raise_structured_error(404, "integration_config_not_found", "No active connector config found for webhook.", retryable=False)
    if len(configs) > 1 and not config_hint:
        _raise_structured_error(
            409,
            "ambiguous_webhook_target",
            "Multiple connector configurations found. Provide X-Integration-Config-Id header.",
            retryable=False,
        )

    target_config = configs[0]
    webhook_security = (target_config.get("webhook_security") or {}) if isinstance(target_config.get("webhook_security"), dict) else {}
    encrypted_secret = str(webhook_security.get("webhook_signing_secret") or "")
    webhook_secret = _decrypt_webhook_secret(encrypted_secret)
    if not webhook_secret:
        _raise_structured_error(
            428,
            "webhook_signing_secret_unavailable",
            "Webhook signing secret unavailable for connector.",
            retryable=False,
        )

    raw_signature = str(request.headers.get("X-Integration-Signature") or "")
    signature = _extract_webhook_signature(raw_signature)
    if not signature:
        _raise_structured_error(401, "missing_webhook_signature", "Missing or malformed webhook signature.", retryable=False)

    raw_timestamp = str(request.headers.get("X-Integration-Timestamp") or "").strip()
    if not raw_timestamp or not raw_timestamp.isdigit():
        _raise_structured_error(401, "missing_webhook_timestamp", "Missing webhook timestamp header.", retryable=False)
    timestamp = int(raw_timestamp)
    tolerance = int(webhook_security.get("signature_tolerance_seconds") or WEBHOOK_SIGNATURE_TOLERANCE_SECONDS)
    now_epoch = int(now_dt.timestamp())
    if abs(now_epoch - timestamp) > tolerance:
        _raise_structured_error(
            401,
            "webhook_timestamp_out_of_window",
            "Webhook timestamp is outside signature tolerance window.",
            retryable=False,
        )

    expected_signature = _compute_webhook_signature(webhook_secret, timestamp, raw_body)
    if not hmac.compare_digest(signature, expected_signature):
        _raise_structured_error(401, "invalid_webhook_signature", "Webhook signature verification failed.", retryable=False)

    incoming_event_id = str(
        request.headers.get("X-Integration-Event-Id")
        or body.get("event_id")
        or body.get("id")
        or f"evt_{uuid.uuid4().hex[:10]}"
    ).strip()
    replay_key = f"{target_config.get('config_id','')}::{incoming_event_id}"
    ttl_seconds = int(webhook_security.get("replay_ttl_seconds") or WEBHOOK_REPLAY_TTL_SECONDS)
    replay_doc = await db.integration_webhook_replay_guard.find_one(
        {"replay_key": replay_key},
        {"_id": 0, "expires_at": 1},
    )
    if replay_doc:
        expires_at = _parse_iso_datetime(replay_doc.get("expires_at"))
        if expires_at and expires_at > now_dt:
            _raise_structured_error(409, "webhook_replay_blocked", "Duplicate webhook replay detected.", retryable=False)

    expires_at_iso = (now_dt + timedelta(seconds=ttl_seconds)).isoformat()
    await db.integration_webhook_replay_guard.update_one(
        {"replay_key": replay_key},
        {
            "$set": {
                "replay_key": replay_key,
                "config_id": str(target_config.get("config_id") or ""),
                "integration_id": integration_id,
                "event_id": incoming_event_id,
                "seen_at": now,
                "expires_at": expires_at_iso,
            }
        },
        upsert=True,
    )

    webhook_event = {
        "event_id": incoming_event_id,
        "integration_id": integration_id,
        "config_id": str(target_config.get("config_id") or ""),
        "user_id": str(target_config.get("user_id") or ""),
        "event_type": body.get("event_type", "unknown"),
        "payload": body,
        "signature_verified": True,
        "signature_timestamp": timestamp,
        "replay_guard_key": replay_key,
        "processed": False,
        "created_at": now,
    }
    await db.webhook_events.insert_one(webhook_event)
    webhook_event.pop("_id", None)

    return {
        "success": True,
        "event_id": webhook_event["event_id"],
        "signature_verified": True,
        "replay_guard": "accepted",
    }


@router.delete("/{config_id}")
async def delete_integration(config_id: str, request: Request):
    """Remove an integration configuration and its synced data."""
    user = await require_auth(request)
    config = await db.integration_configs.find_one({"config_id": config_id, "user_id": user.user_id}, {"_id": 0})
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )

    # Clean up synced data
    integration_id = config.get("integration_id", "")
    await db.ats_candidates.delete_many({"user_id": user.user_id, "integration_id": integration_id})
    await db.ats_jobs.delete_many({"user_id": user.user_id, "integration_id": integration_id})
    await db.sync_logs.delete_many({"config_id": config_id})

    result = await db.integration_configs.delete_one({"config_id": config_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )
    return {"success": True, "deleted": config_id}


# ── Queryable Data Endpoints ──


@router.get("/data/candidates")
async def list_synced_candidates(
    request: Request,
    source: str = Query(None, description="Filter by source: greenhouse, lever, workday"),
    stage: str = Query(None, description="Filter by stage"),
    search: str = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List synced candidates with filtering, search, and pagination."""
    user = await require_auth(request)
    query = {"user_id": user.user_id}
    if source:
        query["source"] = source
    if stage:
        query["stage"] = stage
    if search:
        query["$or"] = [
            {"name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"email": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    skip = (page - 1) * limit
    total = await db.ats_candidates.count_documents(query)
    candidates = (
        await db.ats_candidates.find(query, {"_id": 0}).sort("synced_at", -1).skip(skip).limit(limit).to_list(limit)
    )

    return {
        "candidates": candidates,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 0,
    }


@router.get("/data/jobs")
async def list_synced_jobs(
    request: Request,
    source: str = Query(None, description="Filter by source"),
    status: str = Query(None, description="Filter by status: open, closed"),
    search: str = Query(None, description="Search by title"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List synced jobs with filtering and pagination."""
    user = await require_auth(request)
    query = {"user_id": user.user_id}
    if source:
        query["source"] = source
    if status:
        query["status"] = status
    if search:
        query["title"] = {"$regex": re.escape(str(search)), "$options": "i"}

    skip = (page - 1) * limit
    total = await db.ats_jobs.count_documents(query)
    jobs = await db.ats_jobs.find(query, {"_id": 0}).sort("synced_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "jobs": jobs,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 0,
    }


@router.get("/dashboard/stats")
async def get_integration_dashboard(request: Request):
    """Get integration dashboard stats: totals, per-source breakdown, recent syncs."""
    user = await require_auth(request)
    uid = user.user_id

    # Count per source
    candidate_pipeline = [{"$match": {"user_id": uid}}, {"$group": {"_id": "$source", "count": {"$sum": 1}}}]
    job_pipeline = [{"$match": {"user_id": uid}}, {"$group": {"_id": "$source", "count": {"$sum": 1}}}]
    stage_pipeline = [{"$match": {"user_id": uid}}, {"$group": {"_id": "$stage", "count": {"$sum": 1}}}]

    candidate_counts = await db.ats_candidates.aggregate(candidate_pipeline).to_list(10)
    job_counts = await db.ats_jobs.aggregate(job_pipeline).to_list(10)
    stage_counts = await db.ats_candidates.aggregate(stage_pipeline).to_list(20)

    total_candidates = sum(c["count"] for c in candidate_counts)
    total_jobs = sum(j["count"] for j in job_counts)

    # Recent sync logs
    recent_syncs = await db.sync_logs.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(5)

    # Configured integrations
    configs = await db.integration_configs.find({"user_id": uid}, {"_id": 0, "credentials": 0}).to_list(10)

    total_errors = sum(int(item.get("errors") or 0) for item in recent_syncs)
    health_score = 100 if len(configs) == 0 else max(35, 100 - min(total_errors * 5, 60))

    return {
        "total_candidates": total_candidates,
        "total_jobs": total_jobs,
        "candidates_by_source": {c["_id"]: c["count"] for c in candidate_counts if c["_id"]},
        "jobs_by_source": {j["_id"]: j["count"] for j in job_counts if j["_id"]},
        "candidates_by_stage": {s["_id"]: s["count"] for s in stage_counts if s["_id"]},
        "recent_syncs": recent_syncs,
        "active_integrations": len(configs),
        "integrations": [_sanitize_config_for_response(c) for c in configs],
        "health_score": health_score,
        "weekly_summary": {
            "status": "healthy" if health_score >= 85 else "watch" if health_score >= 65 else "critical",
            "total_recent_errors": total_errors,
            "recent_sync_runs": len(recent_syncs),
        },
    }


@router.post("/schedule")
async def update_sync_schedule(request: Request):
    """Set auto-sync interval for an integration (hours)."""
    user = await require_auth(request)
    body = await request.json()
    config_id = body.get("config_id")
    interval_hours = int(body.get("interval_hours", 0))  # 0 = disabled

    if interval_hours not in SCHEDULE_ALLOWED_HOURS:
        _raise_structured_error(
            400,
            "invalid_sync_interval",
            "interval_hours must be one of 0, 1, 6, 12, 24, 48, 72, 168.",
            retryable=False,
        )

    config = await db.integration_configs.find_one({"config_id": config_id, "user_id": user.user_id})
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )

    await db.integration_configs.update_one(
        {"config_id": config_id},
        {
            "$set": {
                "auto_sync_interval_hours": interval_hours,
                "updated_at": _now_iso(),
            }
        },
    )

    return {
        "success": True,
        "config_id": config_id,
        "auto_sync_interval_hours": interval_hours,
    }


@router.get("/{config_id}/health")
async def get_integration_health(config_id: str, request: Request):
    """Connector-level health summary to power lifecycle UX and nudges."""
    user = await require_auth(request)
    config = await db.integration_configs.find_one(
        {"config_id": config_id, "user_id": user.user_id},
        {"_id": 0, "credentials": 0},
    )
    if not config:
        _raise_structured_error(
            404,
            "integration_not_found",
            "Integration not found",
            retryable=False,
        )
    sync_health = _build_sync_health(config)
    return {
        "config_id": config_id,
        "integration_id": config.get("integration_id"),
        "integration_name": config.get("integration_name"),
        "sync_health": sync_health,
        "recommended_action": (
            "Run sync now" if sync_health.get("status") in {"idle", "degraded"} else "Healthy — no action required"
        ),
    }


@router.get("/admin/test-mode-seed-policy")
async def get_test_mode_seed_policy(request: Request):
    admin_user = await require_admin(request)
    policy_doc = await db.integration_runtime_policies.find_one(
        {"key": "test_mode_seed_cleanup_policy"},
        {"_id": 0},
    )
    active_policy = {
        "enabled": True,
        "retention_hours": TEST_MODE_SEED_RETENTION_HOURS,
        "dry_run": False,
        "last_updated_by": str(getattr(admin_user, "user_id", "")),
    }
    if isinstance((policy_doc or {}).get("value"), dict):
        active_policy.update(policy_doc.get("value") or {})

    latest_run = await db.integration_seed_cleanup_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return {
        "success": True,
        "policy": active_policy,
        "latest_run": latest_run or {},
    }


@router.put("/admin/test-mode-seed-policy")
async def update_test_mode_seed_policy(request: Request):
    admin_user = await require_admin(request)
    body = await request.json()
    retention_hours = int(body.get("retention_hours") or TEST_MODE_SEED_RETENTION_HOURS)
    enabled = bool(body.get("enabled", True))
    dry_run = bool(body.get("dry_run", False))

    retention_hours = max(1, min(retention_hours, 24 * 45))
    now_iso = _now_iso()
    policy = {
        "enabled": enabled,
        "retention_hours": retention_hours,
        "dry_run": dry_run,
        "updated_at": now_iso,
        "updated_by": str(getattr(admin_user, "email", "admin")),
    }
    await db.integration_runtime_policies.update_one(
        {"key": "test_mode_seed_cleanup_policy"},
        {
            "$set": {
                "key": "test_mode_seed_cleanup_policy",
                "value": policy,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )
    return {"success": True, "policy": policy}


@router.post("/admin/test-mode-seed-cleanup/run")
async def run_test_mode_seed_cleanup(request: Request):
    admin_user = await require_admin(request)
    body = await request.json()
    retention_hours = int(body.get("retention_hours") or TEST_MODE_SEED_RETENTION_HOURS)
    dry_run = bool(body.get("dry_run", False))
    summary = await _cleanup_test_mode_seed_connectors(
        retention_hours=retention_hours,
        dry_run=dry_run,
        triggered_by=str(getattr(admin_user, "email", "admin")),
    )
    return summary


# ── Scheduled Auto-Sync Function ──


async def run_scheduled_syncs():
    """Background job: auto-sync all integrations with a configured interval."""
    try:
        await _maybe_run_seed_cleanup_from_scheduler()
    except Exception as cleanup_exc:
        logger.error("Test-mode seed cleanup scheduler hook failed: %s", cleanup_exc)

    now = _now_utc()
    configs = await db.integration_configs.find(
        {"status": "active", "auto_sync_interval_hours": {"$gt": 0}}, {"_id": 0}
    ).to_list(100)

    for config in configs:
        interval = config.get("auto_sync_interval_hours", 0)
        last_sync_str = config.get("sync_status", {}).get("last_sync")
        if last_sync_str:
            try:
                last_sync = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00"))
                hours_since = (now - last_sync).total_seconds() / 3600
                if hours_since < interval:
                    continue
            except (ValueError, TypeError):
                pass

        integration_id = config["integration_id"]
        config_id = config["config_id"]
        logger.info(f"Auto-sync triggered for {integration_id} (config: {config_id})")

        lock_token = await _acquire_sync_lock(config_id, config.get("user_id", ""))
        if not lock_token:
            logger.info("Auto-sync skipped for %s: lock already acquired", config_id)
            continue

        try:
            runtime_credentials, found_plain_sensitive = _decrypt_credentials_for_runtime(config.get("credentials") or {})
            runtime_config = {**config, "credentials": runtime_credentials}

            if runtime_config.get("test_mode"):
                result = await _test_mode_sync(runtime_config)
            else:
                engine = SYNC_ENGINES.get(integration_id)
                result = await engine(runtime_config) if engine else await _test_mode_sync(runtime_config)

            sync_time = _now_iso()
            sync_health = _build_sync_health(
                {
                    "sync_status": {
                        "last_sync": sync_time,
                        "records_synced": int(result.get("synced") or 0),
                        "errors": int(result.get("errors") or 0),
                    }
                }
            )
            update_payload: dict[str, Any] = {
                "sync_status.last_sync": sync_time,
                "sync_status.records_synced": int(result.get("synced") or 0),
                "sync_status.errors": int(result.get("errors") or 0),
                "sync_health": sync_health,
                "updated_at": sync_time,
            }
            if found_plain_sensitive:
                update_payload["credentials"] = _encrypt_credentials_for_storage(runtime_credentials)

            await db.integration_configs.update_one(
                {"config_id": config_id},
                {"$set": update_payload},
            )
            await db.sync_logs.insert_one(
                {
                    "log_id": f"sync_{uuid.uuid4().hex[:10]}",
                    "config_id": config_id,
                    "integration_id": integration_id,
                    "user_id": config.get("user_id", ""),
                    "records_synced": result["synced"],
                    "errors": result["errors"],
                    "details": result.get("details", []),
                    "status": "auto_completed" if result["errors"] == 0 else "auto_completed_with_errors",
                    "health_status": sync_health.get("status"),
                    "created_at": sync_time,
                }
            )
            logger.info(f"Auto-sync complete for {integration_id}: {result['synced']} records")
        except Exception as e:
            logger.error(f"Auto-sync failed for {integration_id}: {e}")
        finally:
            await _release_sync_lock(config_id, config.get("user_id", ""), lock_token)
