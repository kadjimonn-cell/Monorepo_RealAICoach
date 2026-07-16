"""Email Service — Resend-only transactional email provider."""

import os
import asyncio
import logging
import base64
import hashlib
import time
from functools import wraps, lru_cache
from typing import Optional, Dict, Any, List
import re
import html as html_lib

import resend
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

_EMAIL_SEND_LOCK = asyncio.Lock()
_EMAIL_LAST_SEND_AT = 0.0
_EMAIL_MIN_INTERVAL_SECONDS = 0.25
_RESEND_RATE_LIMIT_MARKERS = ("too many requests", "rate limit")
_EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_BLOCKED_RECIPIENT_DOMAINS_DEFAULT = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "invalid.com",
    "fake.com",
    "mailinator.com",
    "tempmail.com",
}
_AUTO_DEDUPE_TEMPLATE_KEYS = {
    "user_notification_alert",
    "login_alert",
    "server_anomaly_alert",
    "anomaly_digest",
    "integrity_cycle_report",
}
_EMAIL_DEDUPE_WINDOW_SECONDS = int(os.environ.get("EMAIL_DEDUPE_WINDOW_SECONDS", "300"))
_EMAIL_GLOBAL_NOTIFICATION_DEDUPE_WINDOW_SECONDS = int(
    os.environ.get("EMAIL_GLOBAL_NOTIFICATION_DEDUPE_WINDOW_SECONDS", "1800")
)
_EMAIL_DEDUPE_INDEX_READY = False
_EMAIL_DEDUPE_INDEX_LOCK = asyncio.Lock()
_EMAIL_IDEMPOTENCY_INDEX_READY = False
_EMAIL_IDEMPOTENCY_INDEX_LOCK = asyncio.Lock()
_EMAIL_IDEMPOTENCY_COLLECTION = "email_delivery_idempotency"
_EMAIL_NOTIFICATION_CAP_COLLECTION = "email_notification_send_caps"
_EMAIL_NOTIFICATION_CAP_EVENTS_COLLECTION = "email_notification_guardrail_events"
_EMAIL_NOTIFICATION_CAP_POLICIES_COLLECTION = "email_notification_template_policies"
_EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT = int(
    os.environ.get("EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT", "1")
)
_EMAIL_NOTIFICATION_CAP_INDEX_READY = False
_EMAIL_NOTIFICATION_CAP_INDEX_LOCK = asyncio.Lock()
_TEMPLATE_CAP_POLICY_CACHE: dict[str, tuple[float, int]] = {}
_TEMPLATE_CAP_POLICY_CACHE_TTL_SECONDS = 60.0

_ADMIN_ONLY_TEMPLATE_KEYS = {
    "system_alert_admin",
    "admin_detailed_system_alert",
    "automation_alert",
    "gtec_regression_alert",
    "performance_degradation_alert",
    "aso_keyword_alert",
    "i18n_quality_alert",
    "perf_autofix_alert",
    "cwv_degradation",
}
_ADMIN_ROLE_VALUES = {"admin", "super_admin", "superadmin"}


def _is_non_production_runtime() -> bool:
    """Return True for preview/dev/test-like runtimes.

    Keep production strict by default.
    """
    env_candidates = [
        str(os.environ.get("ENV") or "").strip().lower(),
        str(os.environ.get("ENVIRONMENT") or "").strip().lower(),
        str(os.environ.get("APP_ENV") or "").strip().lower(),
        str(os.environ.get("RUNTIME_ENV") or "").strip().lower(),
        str(os.environ.get("NODE_ENV") or "").strip().lower(),
    ]
    if any(v in {"prod", "production"} for v in env_candidates if v):
        return False

    frontend_base = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().lower()
    if "preview.emergentagent.com" in frontend_base or "localhost" in frontend_base or "127.0.0.1" in frontend_base:
        return True

    # Default-safe: if runtime env is missing/ambiguous, treat as non-prod in preview pods.
    return True


def _auth_email_test_domain_allowlist() -> set[str]:
    """Domains that can be used in non-production auth email flows.

    This is intentionally scoped to auth testing safety and does not weaken
    production guardrails.
    """
    raw = str(os.environ.get("AUTH_EMAIL_TEST_ALLOWLIST_DOMAINS") or "").strip()
    configured = {
        str(item).strip().lower()
        for item in raw.split(",")
        if str(item).strip()
    }
    if configured:
        return configured
    return {"example.com"}


def _nonprod_suppressed_email_templates() -> set[str]:
    """Template keys to suppress in non-production for noisy test domains."""
    raw = str(os.environ.get("NONPROD_EMAIL_SUPPRESS_TEMPLATES") or "").strip()
    configured = {
        str(item).strip().lower()
        for item in raw.split(",")
        if str(item).strip()
    }
    if configured:
        return configured
    return {"risk_engine_status_v7"}


def _should_suppress_nonprod_template_for_test_domain(
    template_key: str,
    recipient_email: str,
) -> bool:
    if not _is_non_production_runtime():
        return False
    normalized_template = str(template_key or "").strip().lower()
    if not normalized_template or normalized_template not in _nonprod_suppressed_email_templates():
        return False
    _, domain = _parse_email_parts(recipient_email)
    if not domain:
        return False
    return domain in _auth_email_test_domain_allowlist()


async def _ensure_email_notification_cap_indexes() -> None:
    global _EMAIL_NOTIFICATION_CAP_INDEX_READY
    if _EMAIL_NOTIFICATION_CAP_INDEX_READY:
        return
    async with _EMAIL_NOTIFICATION_CAP_INDEX_LOCK:
        if _EMAIL_NOTIFICATION_CAP_INDEX_READY:
            return
        try:
            from routes.db import db

            await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].create_index(
                "cap_key",
                unique=True,
            )
            await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].create_index(
                [("canonical_recipient", 1), ("template_key", 1), ("updated_at", -1)]
            )
            await db[_EMAIL_NOTIFICATION_CAP_EVENTS_COLLECTION].create_index(
                [("created_at", -1)]
            )
            await db[_EMAIL_NOTIFICATION_CAP_POLICIES_COLLECTION].create_index(
                "template_key",
                unique=True,
            )
            await db[_EMAIL_NOTIFICATION_CAP_POLICIES_COLLECTION].create_index(
                [("active", 1), ("updated_at", -1)]
            )
            _EMAIL_NOTIFICATION_CAP_INDEX_READY = True
        except Exception:
            _EMAIL_NOTIFICATION_CAP_INDEX_READY = True


async def _resolve_notification_cap_limit(template_key: str) -> int:
    """Resolve max-per-fingerprint cap for template, with short TTL cache."""
    normalized_template = str(template_key or "(unknown)").strip().lower()
    if not normalized_template:
        normalized_template = "(unknown)"

    now = time.monotonic()
    cached = _TEMPLATE_CAP_POLICY_CACHE.get(normalized_template)
    if cached and (now - cached[0]) <= _TEMPLATE_CAP_POLICY_CACHE_TTL_SECONDS:
        return cached[1]

    default_cap = max(1, int(_EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT or 1))
    resolved = default_cap
    try:
        from routes.db import db

        policy = await db[_EMAIL_NOTIFICATION_CAP_POLICIES_COLLECTION].find_one(
            {
                "template_key": normalized_template,
                "active": {"$ne": False},
            },
            {"_id": 0, "max_per_fingerprint": 1},
        )
        if policy and policy.get("max_per_fingerprint") is not None:
            resolved = max(1, min(20, int(policy.get("max_per_fingerprint") or default_cap)))
    except Exception:
        resolved = default_cap

    _TEMPLATE_CAP_POLICY_CACHE[normalized_template] = (now, resolved)
    return resolved


def clear_template_cap_policy_cache(template_key: Optional[str] = None) -> None:
    """Clear cap policy cache globally or for one template key."""
    if template_key is None:
        _TEMPLATE_CAP_POLICY_CACHE.clear()
        return
    normalized = str(template_key or "").strip().lower()
    if normalized in _TEMPLATE_CAP_POLICY_CACHE:
        _TEMPLATE_CAP_POLICY_CACHE.pop(normalized, None)


@lru_cache(maxsize=1)
def _discover_admin_only_template_keys() -> set[str]:
    """Infer additional admin-only template keys from catalog metadata.

    This protects future additions where developers register new admin-focused
    templates but forget to update the hardcoded guardrail set.
    """
    discovered: set[str] = set()
    try:
        from utils.email_templates import TEMPLATE_CATALOG

        for key, meta in (TEMPLATE_CATALOG or {}).items():
            k = str(key or "").strip().lower()
            label = str((meta or {}).get("label") or "").strip().lower()
            description = str((meta or {}).get("description") or "").strip().lower()

            key_is_admin_like = (
                k.startswith("admin_")
                or k.endswith("_admin")
                or "_admin_" in k
                or "admin" in label
                or "admin" in description
                or "for admins" in description
            )
            if key_is_admin_like:
                discovered.add(k)
    except Exception:
        return set()
    return discovered


def get_admin_only_template_keys_effective() -> set[str]:
    """Effective admin-only template guard set (static + inferred)."""
    return set(_ADMIN_ONLY_TEMPLATE_KEYS) | set(_discover_admin_only_template_keys())

# ─── Resend Configuration ───
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
RESEND_FROM_NAME = os.environ.get("RESEND_FROM_NAME", "RealAICoach")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def is_email_configured() -> bool:
    return bool(RESEND_API_KEY)


def _blocked_recipient_domains() -> set[str]:
    extra = {
        str(item).strip().lower()
        for item in str(os.environ.get("EMAIL_BLOCKED_RECIPIENT_DOMAINS", "")).split(",")
        if str(item).strip()
    }
    return set(_BLOCKED_RECIPIENT_DOMAINS_DEFAULT) | extra


def _parse_email_parts(email: str) -> tuple[str, str]:
    value = str(email or "").strip().lower()
    if "@" not in value:
        return value, ""
    local, domain = value.rsplit("@", 1)
    return local, domain


def is_nonprod_test_domain_recipient(email: str) -> bool:
    """True when recipient is from auth test-domain allowlist in non-production."""
    _, domain = _parse_email_parts(email)
    if not domain:
        return False
    return bool(_is_non_production_runtime() and domain in _auth_email_test_domain_allowlist())


def canonicalize_recipient_email(email: str) -> str:
    """Canonicalize recipient email for strict dedupe/security checks."""
    value = str(email or "").strip().lower()
    if "@" not in value:
        return value

    local, domain = _parse_email_parts(value)
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def _build_permanent_idempotency_key(dedupe_key: str, recipient_email: str, template_key: str) -> str:
    tenant = str(os.environ.get("DB_NAME") or "").strip().lower()
    canonical = canonicalize_recipient_email(recipient_email)
    normalized_template = str(template_key or "").strip().lower()
    normalized_seed = str(dedupe_key or "").strip().lower()
    raw = f"{tenant}|{canonical}|{normalized_template}|{normalized_seed}"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"perm:{digest}"


def _is_valid_recipient_email(email: str) -> tuple[bool, str]:
    value = str(email or "").strip().lower()
    if not value:
        return False, "missing recipient email"
    if not _EMAIL_REGEX.match(value):
        return False, "invalid recipient email format"
    local, domain = _parse_email_parts(value)

    # Non-production auth-flow test override.
    # Allows controlled synthetic domains (e.g., example.com) only when explicitly
    # permitted for testing in preview/dev runtimes.
    if _is_non_production_runtime() and domain in _auth_email_test_domain_allowlist():
        if not local or len(local) < 2:
            return False, "invalid recipient local-part"
        return True, ""

    if domain in _blocked_recipient_domains():
        return False, f"blocked recipient domain: {domain}"
    if value.endswith("@example.com"):
        return False, "blocked synthetic recipient domain"
    if not local or len(local) < 2:
        return False, "invalid recipient local-part"
    return True, ""


async def _get_recipient_block_record(
    recipient_email: str,
    canonical_recipient: str,
) -> Optional[dict]:
    """Return active blocklist record for recipient if present."""
    try:
        from routes.db import db

        record = await db.email_recipient_blocklist.find_one(
            {
                "active": {"$ne": False},
                "$or": [
                    {"recipient_email": str(recipient_email or "").strip().lower()},
                    {
                        "apply_to_canonical": True,
                        "canonical_recipient": str(canonical_recipient or "").strip().lower(),
                    },
                ],
            },
            {"_id": 0},
        )
        return record
    except Exception:
        return None


async def _ensure_email_dedupe_indexes() -> None:
    global _EMAIL_DEDUPE_INDEX_READY
    if _EMAIL_DEDUPE_INDEX_READY:
        return
    async with _EMAIL_DEDUPE_INDEX_LOCK:
        if _EMAIL_DEDUPE_INDEX_READY:
            return
        try:
            from routes.db import db

            await db.email_send_dedupe.create_index("dedupe_key", unique=True)
            await db.email_send_dedupe.create_index("expires_at", expireAfterSeconds=0)
            _EMAIL_DEDUPE_INDEX_READY = True
        except Exception:
            # Non-fatal: dedupe still works best-effort without index lock safety.
            _EMAIL_DEDUPE_INDEX_READY = True


async def _ensure_email_idempotency_indexes() -> None:
    global _EMAIL_IDEMPOTENCY_INDEX_READY
    if _EMAIL_IDEMPOTENCY_INDEX_READY:
        return
    async with _EMAIL_IDEMPOTENCY_INDEX_LOCK:
        if _EMAIL_IDEMPOTENCY_INDEX_READY:
            return
        try:
            from routes.db import db

            await db[_EMAIL_IDEMPOTENCY_COLLECTION].create_index("idempotency_key", unique=True)
            await db[_EMAIL_IDEMPOTENCY_COLLECTION].create_index([("canonical_recipient", 1), ("created_at", -1)])
            _EMAIL_IDEMPOTENCY_INDEX_READY = True
        except Exception:
            _EMAIL_IDEMPOTENCY_INDEX_READY = True


def _build_auto_dedupe_key(recipient_email: str, template_key: str, subject: str) -> str:
    raw = f"{recipient_email.strip().lower()}|{template_key.strip().lower()}|{subject.strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:32]
    return f"auto:{digest}"


_DEDUPE_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?\b", re.IGNORECASE)
_DEDUPE_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DEDUPE_HUMAN_TS_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2},\s+\d{4}(?:\s+at\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:utc|am|pm)?)?\b",
    re.IGNORECASE,
)
_DEDUPE_GUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_DEDUPE_TRACKING_ID_RE = re.compile(r"\betrk_[0-9a-z]{8,64}\b", re.IGNORECASE)


def _normalize_notification_payload_for_dedupe(payload: str) -> str:
    value = str(payload or "").strip().lower()
    if not value:
        return ""
    value = _DEDUPE_ISO_TS_RE.sub("<ts>", value)
    value = _DEDUPE_HUMAN_TS_RE.sub("<ts>", value)
    value = _DEDUPE_DATE_RE.sub("<date>", value)
    value = _DEDUPE_GUID_RE.sub("<id>", value)
    value = _DEDUPE_TRACKING_ID_RE.sub("<trackid>", value)
    # Collapse noisy counters/ids that typically appear in scheduler-generated content.
    value = re.sub(r"\b\d{10,}\b", "<num>", value)
    # Normalize whitespace so formatting differences don't bypass dedupe.
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _build_global_notification_dedupe_key(
    recipient_email: str,
    template_key: str,
    subject: str,
    content_html: str,
    content_text: Optional[str],
) -> str:
    canonical = canonicalize_recipient_email(recipient_email)
    normalized_template = str(template_key or "").strip().lower()
    normalized_subject = _normalize_notification_payload_for_dedupe(subject)
    normalized_html = _normalize_notification_payload_for_dedupe(content_html)
    normalized_text = _normalize_notification_payload_for_dedupe(content_text or "")
    raw = f"{canonical}|{normalized_template}|{normalized_subject}|{normalized_html}|{normalized_text}"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:40]
    return f"global:{digest}"


async def _reserve_email_dedupe_slot(dedupe_key: str, window_seconds: int) -> bool:
    try:
        from datetime import datetime, timezone, timedelta
        from routes.db import db

        await _ensure_email_dedupe_indexes()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(30, int(window_seconds or _EMAIL_DEDUPE_WINDOW_SECONDS)))

        try:
            # Atomic path: only updates existing expired row, otherwise upsert insert.
            prev = await db.email_send_dedupe.find_one_and_update(
                {
                    "dedupe_key": dedupe_key,
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"expires_at": {"$exists": False}},
                    ],
                },
                {
                    "$set": {
                        "dedupe_key": dedupe_key,
                        "updated_at": now,
                        "expires_at": expires_at,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                    },
                },
                upsert=True,
                return_document=ReturnDocument.BEFORE,
            )
            if prev:
                # Existing but expired was refreshed successfully.
                return True
            return True
        except DuplicateKeyError:
            return False
    except Exception:
        logger.warning(
            "[email-dedupe] FAIL-OPEN: dedupe storage unavailable, send proceeding without duplicate protection (key=%s)",
            dedupe_key,
            exc_info=True,
        )
        return True


async def _reserve_permanent_email_idempotency_slot(
    *,
    idempotency_key: str,
    recipient_email: str,
    template_key: str,
    dedupe_seed: str,
) -> tuple[bool, Optional[str]]:
    try:
        from datetime import datetime, timezone
        from routes.db import db

        await _ensure_email_idempotency_indexes()
        now = datetime.now(timezone.utc)
        await db[_EMAIL_IDEMPOTENCY_COLLECTION].insert_one(
            {
                "idempotency_key": idempotency_key,
                "canonical_recipient": canonicalize_recipient_email(recipient_email),
                "recipient": str(recipient_email or "").strip().lower(),
                "template_key": str(template_key or "").strip().lower(),
                "dedupe_seed": str(dedupe_seed or "").strip().lower(),
                "created_at": now,
            }
        )
        return True, None
    except DuplicateKeyError:
        return False, None
    except Exception as exc:
        return False, str(exc)


def _build_notification_cap_key(
    *,
    canonical_recipient: str,
    template_key: str,
    fingerprint_seed: str,
) -> str:
    raw = f"{canonical_recipient}|{template_key}|{str(fingerprint_seed or '').strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"cap:{digest}"


async def _reserve_notification_cap_slot(
    *,
    cap_key: str,
    canonical_recipient: str,
    template_key: str,
    fingerprint_seed: str,
    max_allowed: int,
) -> tuple[bool, int]:
    """Reserve one send slot for notification cap enforcement.

    Returns (allowed, current_count_after_reservation_when_allowed_else_existing_count).
    """
    try:
        from datetime import datetime, timezone
        from routes.db import db

        await _ensure_email_notification_cap_indexes()
        now = datetime.now(timezone.utc)
        max_allowed = max(1, int(max_allowed or 2))

        updated = await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].find_one_and_update(
            {
                "cap_key": cap_key,
                "send_count": {"$lt": max_allowed},
            },
            {
                "$set": {
                    "canonical_recipient": canonical_recipient,
                    "template_key": template_key,
                    "fingerprint_seed": str(fingerprint_seed or "")[:1000],
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                    "first_sent_at": now,
                },
                "$inc": {
                    "send_count": 1,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if updated:
            return True, int(updated.get("send_count") or 0)

        existing = await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].find_one(
            {"cap_key": cap_key},
            {"_id": 0, "send_count": 1},
        )
        return False, int((existing or {}).get("send_count") or max_allowed)
    except DuplicateKeyError:
        return False, max(1, int(max_allowed or 2))
    except Exception:
        logger.warning(
            "[email-cap-guardrail] FAIL-OPEN: cap storage unavailable, send proceeding without exactly-once protection (cap_key=%s recipient=%s template=%s)",
            cap_key,
            canonical_recipient,
            template_key,
            exc_info=True,
        )
        return True, 0


async def _release_notification_cap_slot(cap_key: str) -> None:
    """Rollback one reserved cap slot when provider send fails."""
    try:
        from routes.db import db

        row = await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].find_one(
            {"cap_key": cap_key},
            {"_id": 0, "send_count": 1},
        )
        count = int((row or {}).get("send_count") or 0)
        if count <= 1:
            await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].delete_one({"cap_key": cap_key})
            return
        await db[_EMAIL_NOTIFICATION_CAP_COLLECTION].update_one(
            {"cap_key": cap_key},
            {"$inc": {"send_count": -1}},
        )
    except Exception:
        pass


async def _emit_notification_cap_alert(
    *,
    cap_key: str,
    canonical_recipient: str,
    template_key: str,
    current_count: int,
    max_allowed: int,
    subject: str,
):
    """Raise admin-visible in-app alert + immutable event when cap blocks a send."""
    try:
        from datetime import datetime, timezone
        from routes.db import db

        now_iso = datetime.now(timezone.utc).isoformat()
        event = {
            "event_id": f"email_cap_{hashlib.sha256((cap_key + now_iso).encode()).hexdigest()[:12]}",
            "cap_key": cap_key,
            "canonical_recipient": canonical_recipient,
            "template_key": template_key,
            "subject": str(subject or "")[:180],
            "current_count": int(current_count),
            "max_allowed": int(max_allowed),
            "created_at": now_iso,
        }
        await db[_EMAIL_NOTIFICATION_CAP_EVENTS_COLLECTION].insert_one(event)

        admins = await db.users.find(
            {
                "$or": [
                    {"is_admin": True},
                    {"role": {"$in": list(_ADMIN_ROLE_VALUES)}},
                ]
            },
            {"_id": 0, "user_id": 1},
        ).to_list(50)
        if not admins:
            return

        alert_title = "Email Notification Cap Blocked"
        alert_body = (
            f"Blocked >{max_allowed} sends for template '{template_key}' to '{canonical_recipient}'. "
            f"count={current_count}"
        )
        docs = []
        for admin in admins:
            uid = str(admin.get("user_id") or "").strip()
            if not uid:
                continue
            docs.append(
                {
                    "notification_id": f"notif_{hashlib.sha256((uid + cap_key + now_iso).encode()).hexdigest()[:12]}",
                    "user_id": uid,
                    "type": "email_guardrail_block",
                    "title": alert_title,
                    "body": alert_body,
                    "message": alert_body,
                    "action_url": "/executive-dashboard?section=exec-legal-update-hub",
                    "read": False,
                    "archived": False,
                    "metadata": {
                        "cap_key": cap_key,
                        "template_key": template_key,
                        "recipient": canonical_recipient,
                    },
                    "created_at": now_iso,
                }
            )
        if docs:
            await db.notifications.insert_many(docs, ordered=False)
    except Exception:
        pass


async def _resolve_verified_primary_email_for_user(user_id: str) -> tuple[Optional[str], Optional[str]]:
    uid = str(user_id or "").strip()
    if not uid:
        return None, "missing expected_user_id"
    try:
        from routes.db import db

        user_row = await db.users.find_one(
            {"user_id": uid},
            {"_id": 0, "email": 1, "email_verified": 1},
        )
        if not user_row or not user_row.get("email"):
            return None, "user primary email not found"
        if not bool(user_row.get("email_verified")):
            return None, "user primary email is not verified"
        return str(user_row.get("email") or "").strip().lower(), None
    except Exception as exc:
        return None, f"user lookup failed: {exc}"


async def _is_known_non_admin_recipient(email: str) -> bool:
    """Return True only when recipient resolves to a known non-admin user.

    If the email is not found in users (aliases/distribution lists), we do not
    block at this layer.
    """
    value = str(email or "").strip().lower()
    if not value or "@" not in value:
        return False
    try:
        from routes.db import db

        row = await db.users.find_one(
            {"email": {"$regex": f"^{re.escape(value)}$", "$options": "i"}},
            {"_id": 0, "is_admin": 1, "role": 1},
        )
        if not row:
            return False
        role = str(row.get("role") or "").strip().lower()
        is_admin = bool(row.get("is_admin")) or role in _ADMIN_ROLE_VALUES
        return not is_admin
    except Exception:
        return False


def _contains_existing_enterprise_branding(html: str) -> bool:
    """Detect if HTML already includes RealAICoach enterprise email wrapper/footer.

    Prevents double-branding (duplicate footers/headers) when templates are already wrapped.
    """
    if not html:
        return False

    markers = (
        "BRANDED_FOOTER_V2",
        "ENTERPRISE_FOOTER_V",
        'data-footer-badge="google-play"',
        'data-footer-badge="app-store"',
        "footer-legal-text",
        "em-footer-bg",
        "Take your coach everywhere",
    )
    return any(marker in html for marker in markers)


def _dedupe_enterprise_footer_components(html: str) -> str:
    """Remove duplicate enterprise footer components while keeping the first valid block."""
    if not html:
        return html

    def _dedupe_block(pattern: str, src: str) -> str:
        first_seen = False

        def _replace(match: re.Match) -> str:
            nonlocal first_seen
            if not first_seen:
                first_seen = True
                return match.group(0)
            return ""

        return re.sub(pattern, _replace, src, flags=re.IGNORECASE | re.DOTALL)

    deduped = html
    # Keep only one official Google Play badge anchor
    deduped = _dedupe_block(r'<a[^>]*data-footer-badge="google-play"[^>]*>.*?</a>', deduped)
    # Keep only one official App Store badge anchor
    deduped = _dedupe_block(r'<a[^>]*data-footer-badge="app-store"[^>]*>.*?</a>', deduped)
    # Keep only one primary mobile app footer heading
    deduped = _dedupe_block(r'<p[^>]*>\s*Take your coach everywhere\s*</p>', deduped)
    return deduped


def _load_inline_store_badge_attachments() -> List[dict]:
    """Load Outlook-safe inline store badge attachments from static assets."""
    static_email_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "email")
    assets = [
        ("google_play_exact_trimmed.png", "store-badge-google", "image/png"),
        ("app_store_exact_trimmed.png", "store-badge-app", "image/png"),
    ]
    attachments: List[dict] = []
    for filename, content_id, content_type in assets:
        path = os.path.join(static_email_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            attachments.append(
                {
                    "content": list(f.read()),
                    "filename": filename,
                    "content_type": content_type,
                    "content_id": content_id,
                    "disposition": "inline",
                }
            )
    return attachments


def _replace_img_src_by_alt(html: str, alt_phrase: str, cid: str) -> str:
    if not html:
        return html

    def _replace_tag(match: re.Match) -> str:
        tag = match.group(0)
        lower_tag = tag.lower()
        if alt_phrase.lower() not in lower_tag:
            return tag
        if re.search(r'src="cid:[^"]+"', tag, flags=re.IGNORECASE):
            return tag
        return re.sub(r'src="[^"]*"', f'src="cid:{cid}"', tag, count=1, flags=re.IGNORECASE)

    return re.sub(r"<img[^>]*>", _replace_tag, html, flags=re.IGNORECASE | re.DOTALL)


def _apply_outlook_inline_store_badges(html: str, attachments: Optional[list]) -> tuple[str, Optional[list]]:
    """Inject CID-based badge sources for Outlook compatibility and append inline attachments."""
    if not html:
        return html, attachments

    lower_html = html.lower()
    if "get it on google play" not in lower_html and "download on the app store" not in lower_html:
        return html, attachments

    merged_attachments = list(attachments or [])
    existing_cids = {
        str(item.get("content_id") or "").strip().lower()
        for item in merged_attachments
        if isinstance(item, dict)
    }

    for badge_attachment in _load_inline_store_badge_attachments():
        cid = str(badge_attachment.get("content_id") or "").strip().lower()
        if cid and cid not in existing_cids:
            merged_attachments.append(badge_attachment)
            existing_cids.add(cid)

    if "store-badge-google" in existing_cids:
        html = _replace_img_src_by_alt(html, "Get it on Google Play", "store-badge-google")
    if "store-badge-app" in existing_cids:
        html = _replace_img_src_by_alt(html, "Download on the App Store", "store-badge-app")

    return html, merged_attachments


def _hex_to_rgb(hex_color: str) -> Optional[tuple]:
    value = (hex_color or "").strip()
    if not value.startswith("#"):
        return None
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def _extract_hex_color(value: str) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})", value)
    return match.group(0) if match else None


def _relative_luminance(rgb: tuple) -> float:
    def _channel(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast_ratio(foreground_hex: str, background_hex: str) -> Optional[float]:
    fg = _hex_to_rgb(foreground_hex)
    bg = _hex_to_rgb(background_hex)
    if not fg or not bg:
        return None
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _best_contrast_text_color(background_hex: str) -> str:
    candidates = ["#000000", "#0F172A", "#F8FAFC"]
    scored = []
    for candidate in candidates:
        ratio = _contrast_ratio(candidate, background_hex)
        if ratio is not None:
            scored.append((ratio, candidate))
    if not scored:
        return "#0F172A"
    scored.sort(reverse=True)
    return scored[0][1]


def _parse_inline_style(style_text: str) -> Dict[str, str]:
    parts = [segment.strip() for segment in (style_text or "").split(";") if segment.strip()]
    out: Dict[str, str] = {}
    for part in parts:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        out[key.strip().lower()] = value.strip()
    return out


def _serialize_inline_style(style_map: Dict[str, str]) -> str:
    return ";".join(f"{k}: {v}" for k, v in style_map.items() if v).strip(";")


def _replace_common_template_placeholders(value: str, recipient_name: Optional[str]) -> str:
    if not value:
        return value
    safe_name = (recipient_name or RESEND_FROM_NAME or "there").strip() or "there"
    replacements = {
        "{name}": safe_name,
        "{{name}}": safe_name,
        "{user_name}": safe_name,
        "{{user_name}}": safe_name,
    }
    result = value
    for needle, replacement in replacements.items():
        result = result.replace(needle, replacement)
    return result


def _promote_dark_notification_cards(html: str) -> str:
    if not html:
        return html

    pattern = re.compile(
        r'<(?P<tag>div|table|td)(?P<before>[^>]*)style="(?P<style>[^"]*(?:background(?:-color)?\s*:\s*#(?:0F172A|111827|1E293B|0B1120|1C1710|182233)[^\"]*))"(?P<after>[^>]*)>',
        flags=re.IGNORECASE,
    )

    def _rewrite(match: re.Match) -> str:
        tag = match.group('tag')
        before = match.group('before') or ''
        style = match.group('style') or ''
        after = match.group('after') or ''
        attrs_blob = f"{before}{after}"
        style_lower = style.lower()
        if (
            'em-force-light-card' in attrs_blob
            or 'data-keep-dark' in attrs_blob
            or 'linear-gradient' in style_lower
            or ('max-width' in style_lower and 'margin' in style_lower)
            or ('font-family' in style_lower and 'max-width' in style_lower)
        ):
            return match.group(0)

        class_match = re.search(r'class="([^"]*)"', attrs_blob, flags=re.IGNORECASE)
        replacement = match.group(0)
        if class_match:
            existing = class_match.group(1)
            updated = f'class="{existing} em-force-light-card"'
            replacement = replacement.replace(class_match.group(0), updated, 1)
        else:
            replacement = replacement.replace(f'<{tag}', f'<{tag} class="em-force-light-card"', 1)
        return replacement

    return pattern.sub(_rewrite, html)


def apply_adaptive_email_contrast_guard(html: str) -> str:
    """Global adaptive contrast guard for all current and future email HTML.

    Ensures minimum readability for inline color/background combinations.
    """
    if not html:
        return html

    html = _promote_dark_notification_cards(html)

    def _adjust_tag(match: re.Match) -> str:
        full_tag = match.group(0)
        # Skip intentionally styled elements: badges, CTAs, gradient headers
        if 'em-badge' in full_tag or 'email-primary-cta' in full_tag or 'email-secondary-cta' in full_tag or 'linear-gradient' in full_tag:
            return full_tag
        style_content = match.group(1)
        style_map = _parse_inline_style(style_content)

        fg_hex = _extract_hex_color(style_map.get("color", ""))
        bg_hex = _extract_hex_color(style_map.get("background-color", "") or style_map.get("background", ""))

        if bg_hex and not fg_hex:
            style_map["color"] = _best_contrast_text_color(bg_hex)
        elif bg_hex and fg_hex:
            ratio = _contrast_ratio(fg_hex, bg_hex)
            if ratio is not None and ratio < 4.5:
                style_map["color"] = _best_contrast_text_color(bg_hex)

        updated_style = _serialize_inline_style(style_map)
        return full_tag.replace(f'style="{style_content}"', f'style="{updated_style}"', 1)

    adjusted_html = re.sub(r'style="([^"]*)"', lambda m: f'style="{_serialize_inline_style(_parse_inline_style(m.group(1)))}"', html)
    adjusted_html = re.sub(r"<[^>]*style=\"([^\"]*)\"[^>]*>", _adjust_tag, adjusted_html, flags=re.IGNORECASE | re.DOTALL)

    guard_css = """
<style data-adaptive-contrast-guard="v2">
a[style*="background"], button[style*="background"] {
  text-decoration: none !important;
  font-weight: 800 !important;
}
.em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
.em-force-light-card p,.em-force-light-card div,.em-force-light-card span,.em-force-light-card td,.em-force-light-card th,.em-force-light-card strong,.em-force-light-card b,.em-force-light-card a,.em-force-light-card li,.em-force-light-card small,.em-force-light-card h1,.em-force-light-card h2,.em-force-light-card h3,.em-force-light-card h4,.em-force-light-card h5,.em-force-light-card h6{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
.em-force-muted-text{color:#475569!important;-webkit-text-fill-color:#475569!important}
.em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;mix-blend-mode:normal!important}
.em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
.em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
.em-info-val:not(.em-info-val-accent){color:#0F172A!important}
.em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
.em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
.em-alert-title{color:#0F172A!important}
.em-alert-text{color:#475569!important}
.em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important}
.email-primary-cta,.email-secondary-cta,.em-badge{mix-blend-mode:normal!important}
@media (prefers-color-scheme:dark){
  .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
  .em-force-light-card p,.em-force-light-card div,.em-force-light-card span,.em-force-light-card td,.em-force-light-card th,.em-force-light-card strong,.em-force-light-card b,.em-force-light-card a,.em-force-light-card li,.em-force-light-card small,.em-force-light-card h1,.em-force-light-card h2,.em-force-light-card h3,.em-force-light-card h4,.em-force-light-card h5,.em-force-light-card h6{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
  .em-force-light-card .em-force-muted-text{color:#475569!important;-webkit-text-fill-color:#475569!important}
  .em-force-light-card .em-badge{mix-blend-mode:normal!important}
  .em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
  .em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
  .em-info-val:not(.em-info-val-accent){color:#0F172A!important}
  .em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
  .em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
  .em-alert-title{color:#0F172A!important}
  .em-alert-text{color:#475569!important}
  .em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important}
  .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
  .email-secondary-cta{background:#FFFFFF!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important;border-color:#475569!important}
  .em-badge{mix-blend-mode:normal!important}
}
[data-ogsc] .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
[data-ogsc] .em-force-light-card p,[data-ogsc] .em-force-light-card div,[data-ogsc] .em-force-light-card span,[data-ogsc] .em-force-light-card td,[data-ogsc] .em-force-light-card th,[data-ogsc] .em-force-light-card strong,[data-ogsc] .em-force-light-card b,[data-ogsc] .em-force-light-card a,[data-ogsc] .em-force-light-card li,[data-ogsc] .em-force-light-card small,[data-ogsc] .em-force-light-card h1,[data-ogsc] .em-force-light-card h2,[data-ogsc] .em-force-light-card h3,[data-ogsc] .em-force-light-card h4,[data-ogsc] .em-force-light-card h5,[data-ogsc] .em-force-light-card h6{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
[data-ogsc] .em-force-light-card .em-force-muted-text{color:#475569!important;-webkit-text-fill-color:#475569!important}
[data-ogsc] .em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;mix-blend-mode:normal!important}
[data-ogsc] .em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
[data-ogsc] .em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
[data-ogsc] .em-info-val:not(.em-info-val-accent){color:#0F172A!important}
[data-ogsc] .em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
[data-ogsc] .em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
[data-ogsc] .em-alert-title{color:#0F172A!important}
[data-ogsc] .em-alert-text{color:#475569!important}
[data-ogsc] .em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important}
[data-ogsc] .email-secondary-cta{background:#FFFFFF!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important;border-color:#475569!important}
[data-ogsc] .em-badge{mix-blend-mode:normal!important}
</style>
"""
    if "data-adaptive-contrast-guard" not in adjusted_html:
        if "</head>" in adjusted_html:
            adjusted_html = adjusted_html.replace("</head>", guard_css + "</head>", 1)
        else:
            adjusted_html = guard_css + adjusted_html

    return adjusted_html


def ensure_email_color_scheme_meta(html: str) -> str:
    """Ensure all outbound emails include dark-mode safety meta tags.

    This is applied globally from send_email() so every template benefits,
    including newly added templates that may not define <head> explicitly.
    """
    if not html:
        return html

    lower = html.lower()
    has_color_scheme = 'name="color-scheme"' in lower
    has_supported = 'name="supported-color-schemes"' in lower
    if has_color_scheme and has_supported:
        return html

    meta_inserts = []
    if not has_color_scheme:
        meta_inserts.append('<meta name="color-scheme" content="light">')
    if not has_supported:
        meta_inserts.append('<meta name="supported-color-schemes" content="light">')
    meta_blob = "\n".join(meta_inserts)

    if "</head>" in lower:
        return re.sub(r"</head>", meta_blob + "\n</head>", html, count=1, flags=re.IGNORECASE)

    if "<html" in lower:
        return re.sub(r"(<html[^>]*>)", r"\1<head>" + meta_blob + "</head>", html, count=1, flags=re.IGNORECASE)

    return f"<!doctype html><html><head>{meta_blob}</head><body>{html}</body></html>"


# ─── CDN-Hosted Logo URLs (permanent, fast, trusted CloudFront domain) ───
# The actual RealAICoach app logo - hosted on customer-assets CDN
CDN_APP_LOGO = "https://customer-assets.emergentagent.com/job_d355dc88-11c6-414c-934e-ec9411611b7f/artifacts/nhyei82g_IMG_0525.PNG"


def get_brand_logo_url(variant: str = "dark") -> str:
    """Return CDN-hosted app logo URL."""
    return CDN_APP_LOGO


def get_brand_logo_data_uri() -> str:
    """Return a base64 data URI of the email-optimized logo (works in all email clients)."""
    import base64 as _b64
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "brand-logo-email.jpeg")
    try:
        with open(logo_path, "rb") as f:
            b64 = _b64.b64encode(f.read()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except FileNotFoundError:
        return ""


EMAIL_LOGO_PRESETS = {
    "default": {"width": 180, "margin": "0 0 16px"},
    "support": {"width": 180, "margin": "0 0 16px"},
    "security": {"width": 180, "margin": "0 0 16px"},
    "calendar": {"width": 180, "margin": "0 0 16px"},
    "report": {"width": 180, "margin": "0 0 16px"},
    "admin": {"width": 180, "margin": "0 0 16px"},
    "compact": {"width": 160, "margin": "0 0 14px"},
}


def render_email_logo(variant: str = "default", width: Optional[int] = None, margin: Optional[str] = None) -> str:
    """Render the actual RealAICoach app logo using CDN URL for guaranteed visibility."""
    preset = EMAIL_LOGO_PRESETS.get(variant, EMAIL_LOGO_PRESETS["default"])
    logo_width = width if width is not None else preset["width"]
    logo_margin = margin if margin is not None else preset["margin"]
    return f'<img src="{CDN_APP_LOGO}" alt="RealAICoach" style="width:{logo_width}px;max-width:100%;height:auto;display:block;margin:{logo_margin};border-radius:10px;" />'


def get_logo_inline_attachment() -> Optional[dict]:
    """Return a Resend-compatible inline attachment dict for the brand logo.
    Uses the small email-optimized PNG for fast loading."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images")
    # Try small email logo first, then full logo
    for fname, ctype in [("brand-logo-email-small.png", "image/png"), ("brand-logo-email.jpeg", "image/jpeg"), ("brand-logo-full.png", "image/png")]:
        fpath = os.path.join(static_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                content = list(f.read())
            return {
                "content": content,
                "filename": fname,
                "content_type": ctype,
                "content_id": "brand-logo",
            }
    return None


def render_email_header_panel(
    title: str,
    subtitle: str,
    variant: str = "report",
    accent: str = "#2563EB",
    meta_label: str = "",
    meta_value: str = "",
) -> str:
    logo_img = f'<img src="{CDN_APP_LOGO}" alt="RealAICoach" width="40" height="40" style="width:40px;height:40px;border-radius:12px;display:block;border:1px solid rgba(255,255,255,0.35);" />'
    lockup_html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" class="email-header-lockup"><tr>'
        f'<td style="vertical-align:middle;">{logo_img}</td>'
        '<td style="vertical-align:middle;padding-left:11px;">'
        '<span class="email-header-wordmark notranslate" translate="no" style="font-size:18px;font-weight:900;letter-spacing:-0.4px;color:#FFFFFF;font-family:-apple-system,Helvetica,Arial,sans-serif;">'
        'Real<span style="color:#06D6A0;">AI</span>Coach</span>'
        '</td></tr></table>'
    )
    meta_html = ""
    if meta_label and meta_value:
        meta_html = f"""<div class="email-header-pill em-header-pill" style="display:inline-block;padding:8px 14px;border-radius:14px;background-color:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.35);text-align:left;min-width:140px;">
  <div style="color:#FFFFFF;font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase;opacity:0.85;">{meta_label}</div>
  <div style="color:#FFFFFF;font-size:12px;font-weight:700;margin-top:4px;">{meta_value}</div>
</div>"""
    subtitle_html = f'<div style="color:#E0E7FF;font-size:13px;line-height:1.6;margin-top:8px;">{subtitle}</div>' if subtitle else ""
    return f"""<div class="email-header email-header-shell em-header" style="background-color:#1D4ED8;background-image:linear-gradient(135deg,#0ea5e9,#6366f1);padding:30px 28px 26px;border-radius:20px 20px 0 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:middle;">{lockup_html}</td>
    <td align="right" style="vertical-align:middle;">{meta_html}</td>
  </tr></table>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:20px 0 12px;">
    <span class="email-header-trust" style="display:inline-block;padding:5px 12px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.24);border-radius:99px;color:#FFFFFF;font-size:10px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;"><span style="font-weight:900;">&#10003;</span>&nbsp;Verified sender&nbsp;&nbsp;&middot;&nbsp;&nbsp;Secure communication</span>
  </td></tr></table>
  <div class="email-header-title" style="color:#FFFFFF;font-size:24px;font-weight:800;line-height:1.25;letter-spacing:-0.4px;">{title}</div>{subtitle_html}
</div>"""


def render_email_timestamp_pill(timestamp_text: str) -> str:
    safe_text = html_lib.escape(str(timestamp_text or ""))
    return (
        '<p class="em-force-light-card em-force-muted-text" '
        'style="display:inline-block;margin:6px 0 0;padding:5px 10px;border-radius:999px;'
        'border:1px solid #E2E8F0;background:#FFFFFF;color:#0F172A;font-size:12px;font-weight:700;white-space:nowrap;">'
        f"{safe_text}</p>"
    )


# Keep old name as alias for backward compat during transition
is_resend_configured = is_email_configured


async def _send_via_resend_with_throttle(params: Dict[str, Any]):
    global _EMAIL_LAST_SEND_AT

    loop = asyncio.get_running_loop()
    async with _EMAIL_SEND_LOCK:
        now = loop.time()
        wait_for = max(0.0, _EMAIL_MIN_INTERVAL_SECONDS - (now - _EMAIL_LAST_SEND_AT))
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        _EMAIL_LAST_SEND_AT = loop.time()

    return await asyncio.to_thread(resend.Emails.send, params)


def ops_alert_template_enforcer(category: str, default_template_key: Optional[str] = None):
    """Decorator to enforce template_key on ops alert senders and avoid drift."""

    normalized = str(category or "ops").strip().lower() or "ops"
    fallback = str(default_template_key or f"{normalized}_alert").strip()

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not kwargs.get("template_key"):
                kwargs["template_key"] = fallback
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def _ensure_darkmode_safe_autonomous_card(html: str, template_key: Optional[str]) -> str:
    """Mandatory V2 baseline wrapper for ALL outgoing email content.

    Every email type (template/non-template/notification) inherits readable
    light-card content automatically.
    """
    if not html:
        return html
    if "em-force-light-card" in html:
        return html

    wrapper_open = "<div class='em-force-light-card' style='font-family:Inter,Segoe UI,Arial,sans-serif;padding:18px;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px'>"
    wrapper_close = "</div>"

    body_match = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    if body_match:
        inner = body_match.group(1)
        wrapped = f"{wrapper_open}{inner}{wrapper_close}"
        return html.replace(inner, wrapped, 1)

    return f"{wrapper_open}{html}{wrapper_close}"


LEARNING_CERTIFICATE_ATTACHMENT_EXEMPT_TEMPLATE_KEYS = {"learning_hub_certificate_award"}


def _is_learning_certificate_attachment_exempt(item: dict, template_key: Optional[str]) -> bool:
    normalized_template = str(template_key or "").strip().lower()
    if normalized_template not in LEARNING_CERTIFICATE_ATTACHMENT_EXEMPT_TEMPLATE_KEYS:
        return False
    filename = str(item.get("filename") or "").strip().lower()
    return filename.startswith("realaicoach-certificate-") and filename.endswith(".pdf")


JOB_SEARCH_KIT_ATTACHMENT_EXEMPT_TEMPLATE_KEYS = {"job_search_kit_email"}


TRAVEL_VISA_CERTIFICATE_ATTACHMENT_EXEMPT_TEMPLATE_KEYS = {"travel_visa_certificate_award"}


def _is_travel_visa_certificate_attachment_exempt(item: dict, template_key: Optional[str]) -> bool:
    """Travel Visa certificate PDFs carry their own certificate-grade chrome — no v15 overlay."""
    normalized_template = str(template_key or "").strip().lower()
    if normalized_template not in TRAVEL_VISA_CERTIFICATE_ATTACHMENT_EXEMPT_TEMPLATE_KEYS:
        return False
    filename = str(item.get("filename") or "").strip().lower()
    return filename.startswith("realaicoach-travel-visa-certificate-") and filename.endswith(".pdf")


def _is_job_search_kit_attachment_exempt(item: dict, template_key: Optional[str]) -> bool:
    """Job Search CV/cover-letter PDFs go to external employers — no v15 chrome on attachments."""
    normalized_template = str(template_key or "").strip().lower()
    if normalized_template not in JOB_SEARCH_KIT_ATTACHMENT_EXEMPT_TEMPLATE_KEYS:
        return False
    filename = str(item.get("filename") or "").strip().lower()
    return (filename.startswith("cv-") or filename.startswith("cover-letter-")) and filename.endswith(".pdf")


def _apply_pdf_theme_policy_to_attachments(attachments: Optional[list], template_key: Optional[str] = None) -> tuple[Optional[list], Optional[str]]:
    """Enforce PDF v15 theme policy for outbound email PDF attachments.

    This closes non-HTTP bypass paths (email attachments do not pass through
    HTTP middleware).
    """
    if not attachments:
        return attachments, None

    strict = os.environ.get("PDF_THEME_STRICT_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}

    try:
        from middleware_pdf_policy import enforce_pdf_v15_theme_bytes
    except Exception as exc:
        if strict:
            return None, f"pdf-theme-attachment-enforcement-unavailable: {exc}"
        return attachments, None

    normalized: list = []
    for item in attachments:
        if not isinstance(item, dict):
            normalized.append(item)
            continue

        content_type = str(item.get("content_type") or "").lower()
        filename = str(item.get("filename") or "").lower()
        is_pdf = content_type == "application/pdf" or filename.endswith(".pdf")
        if not is_pdf:
            normalized.append(item)
            continue

        if _is_learning_certificate_attachment_exempt(item, template_key):
            normalized.append(item)
            continue

        if _is_travel_visa_certificate_attachment_exempt(item, template_key):
            normalized.append(item)
            continue

        if _is_job_search_kit_attachment_exempt(item, template_key):
            normalized.append(item)
            continue

        content = item.get("content")
        if content is None:
            if strict:
                return None, f"pdf-theme-attachment-missing-content: {filename or 'unnamed.pdf'}"
            normalized.append(item)
            continue

        original_kind = "bytes"
        payload: bytes
        try:
            if isinstance(content, (bytes, bytearray)):
                payload = bytes(content)
                original_kind = "bytes"
            elif isinstance(content, list):
                payload = bytes(content)
                original_kind = "list"
            elif isinstance(content, str):
                blob = content
                if blob.startswith("data:") and "," in blob:
                    blob = blob.split(",", 1)[1]
                payload = base64.b64decode(blob)
                original_kind = "base64"
            else:
                raise TypeError(f"unsupported content type: {type(content)}")
        except Exception as exc:
            if strict:
                return None, f"pdf-theme-attachment-decode-failed: {filename or 'unnamed.pdf'} ({exc})"
            normalized.append(item)
            continue

        themed, theme_mode = enforce_pdf_v15_theme_bytes(payload)
        if strict and theme_mode in {"theme_passthrough_error", "non_pdf"}:
            return None, f"pdf-theme-attachment-enforcement-failed: {filename or 'unnamed.pdf'} mode={theme_mode}"

        patched = dict(item)
        patched["content_type"] = "application/pdf"
        if original_kind == "list":
            patched["content"] = list(themed)
        elif original_kind == "base64":
            patched["content"] = base64.b64encode(themed).decode("utf-8")
        else:
            patched["content"] = themed
        normalized.append(patched)

    return normalized, None


async def send_email(
    recipient_email: str,
    subject: str,
    content: str,
    recipient_name: Optional[str] = None,
    contact_external_id: Optional[str] = None,
    content_text: Optional[str] = None,
    template_key: Optional[str] = None,
    attachments: Optional[list] = None,
    skip_branding: bool = False,
    reply_to: Optional[list] = None,
    headers: Optional[Dict[str, str]] = None,
    dedupe_key: Optional[str] = None,
    expected_user_id: Optional[str] = None,
    enforce_verified_primary: bool = False,
) -> Dict[str, Any]:
    """Send email via Resend. Auto-brands with app logo + enterprise footer unless already branded.

    v7 Enforcement:
    - All emails are auto-branded with the v7 colorful design (gradient header, rounded logo, footer)
    - Category is detected from template_key or subject line for correct gradient colors
    - skip_branding only respected for whitelisted brand probes; all others get v7
    - Missing template_key triggers a runtime warning for developer visibility
    """
    # ── v7 Guardrail: HARD BLOCK raw HTML bypass ─────────────────────
    # Run this FIRST (before Resend config / template_key checks) so that
    # a programming bug (raw HTML) always surfaces with v7_violation=True
    # even when the email environment is not configured (tests, local dev).
    # V7-rendered emails from _wrap() contain the `em-outer` fingerprint.
    # Anything else (raw <div>, <table>, <p>, <h*>) is a bypass. As of the
    # Apr 22 2026 "NO BYPASSES" ruling, mode `block` is the default and
    # refuses to send. Setting V7_ENFORCEMENT_MODE=permissive reverts to
    # the legacy warn+auto-wrap path — use only for emergency hotfixes.
    _V7_FINGERPRINT = 'class="em-outer"'
    _has_v7_fingerprint = _V7_FINGERPRINT in (content or "")
    _has_raw_html_body = bool(
        re.search(r'<(?:div|table|p|h[1-6])(?:\s|>)', content or "", re.IGNORECASE)
    ) and not _has_v7_fingerprint

    if _has_raw_html_body and not skip_branding:
        _v7_mode = os.environ.get("V7_ENFORCEMENT_MODE", "block").lower()
        logger.warning(
            f"[v7-guardrail] RAW HTML BYPASS DETECTED for template_key='{template_key}', "
            f"subject='{subject[:60]}'. Content lacks V7 _wrap() fingerprint "
            f"(class=\"em-outer\"). Mode={_v7_mode}."
        )
        if _v7_mode in ("block", "strict_block"):
            return {
                "success": False,
                "error": (
                    "v7-guardrail: raw HTML bypass blocked. "
                    "Wrap your content via utils.email_templates._wrap() or "
                    "a registered TEMPLATE_CATALOG builder so it carries the "
                    "'em-outer' fingerprint. Set V7_ENFORCEMENT_MODE=permissive "
                    "only for emergency hotfixes."
                ),
                "v7_violation": True,
                "v7_mode": _v7_mode,
                "template_key": template_key,
                "subject": subject,
            }
        # permissive mode falls through to the downstream auto-brand
        logger.info(
            f"[v7-guardrail] permissive mode: auto-wrapping raw HTML for '{template_key}'"
        )

    if not is_email_configured():
        return {"success": False, "error": "Email service not configured (missing RESEND_API_KEY)"}

    # ── v7 Guardrail: ENFORCE template_key ──
    # Set V7_ENFORCEMENT_MODE=warn in .env to temporarily downgrade to warning only.
    if not template_key:
        _v7_warn_missing_template_key(subject, recipient_email)
        if os.environ.get("V7_ENFORCEMENT_MODE", "strict").lower() == "strict":
            return {
                "success": False,
                "error": "v7-guardrail: template_key is required. All emails must go through a registered catalog template.",
                "v7_violation": True,
                "subject": subject,
            }

    normalized_template = str(template_key or "").strip().lower()
    recipient_email = str(recipient_email or "").strip().lower()
    canonical_recipient = canonicalize_recipient_email(recipient_email)
    test_domain_recipient = is_nonprod_test_domain_recipient(recipient_email)

    if test_domain_recipient:
        logger.warning(
            "[email-guardrail] non-production test-domain recipient accepted (template=%s recipient=%s). Inbox delivery may not occur.",
            normalized_template,
            recipient_email,
        )

    # Suppress noisy risk/status templates for test domains in non-production.
    # This avoids log/notification flooding during preview E2E runs while keeping
    # production behavior strict and unchanged.
    if _should_suppress_nonprod_template_for_test_domain(normalized_template, recipient_email):
        logger.info(
            "[email-guardrail] non-production template suppressed (template=%s recipient=%s)",
            normalized_template,
            recipient_email,
        )
        return {
            "success": True,
            "skipped": True,
            "error": "email-guardrail: non-production template suppressed for test-domain recipient",
            "template_key": normalized_template,
            "recipient": recipient_email,
        }

    if enforce_verified_primary:
        primary_email, primary_error = await _resolve_verified_primary_email_for_user(expected_user_id or "")
        if primary_error:
            logger.warning(
                "[email-guardrail] blocked verified-primary policy (template=%s expected_user_id=%s reason=%s)",
                normalized_template,
                expected_user_id,
                primary_error,
            )
            return {
                "success": False,
                "skipped": True,
                "error": f"email-guardrail: verified-primary policy failed ({primary_error})",
                "template_key": normalized_template,
                "expected_user_id": expected_user_id,
                "recipient": recipient_email,
            }

        primary_canonical = canonicalize_recipient_email(primary_email or "")
        if canonical_recipient != primary_canonical:
            logger.warning(
                "[email-guardrail] blocked non-primary recipient (template=%s expected_user_id=%s provided=%s primary=%s)",
                normalized_template,
                expected_user_id,
                recipient_email,
                primary_email,
            )
            return {
                "success": False,
                "skipped": True,
                "error": "email-guardrail: non-primary or alias recipient blocked",
                "template_key": normalized_template,
                "expected_user_id": expected_user_id,
                "recipient": recipient_email,
                "primary_email": primary_email,
            }

        recipient_email = str(primary_email or "").strip().lower()
        canonical_recipient = primary_canonical

    valid_email, email_error = _is_valid_recipient_email(recipient_email)
    if not valid_email:
        logger.warning(
            "[email-guardrail] blocked outbound email to '%s' (template=%s): %s",
            recipient_email,
            normalized_template,
            email_error,
        )
        return {
            "success": False,
            "skipped": True,
            "error": f"email-guardrail: {email_error}",
            "template_key": normalized_template,
            "recipient": recipient_email,
        }

    block_rec = await _get_recipient_block_record(recipient_email, canonical_recipient)
    if block_rec:
        reason = str(block_rec.get("reason") or "recipient is blocked by hygiene policy")
        logger.warning(
            "[email-guardrail] blocked recipient by blocklist (template=%s recipient=%s reason=%s)",
            normalized_template,
            recipient_email,
            reason,
        )
        return {
            "success": False,
            "skipped": True,
            "error": f"email-guardrail: blocked recipient ({reason})",
            "template_key": normalized_template,
            "recipient": recipient_email,
            "blocklist_reason": reason,
        }

    effective_admin_templates = get_admin_only_template_keys_effective()
    if normalized_template in effective_admin_templates:
        if await _is_known_non_admin_recipient(recipient_email):
            logger.error(
                "[email-guardrail] blocked admin-only template '%s' for non-admin recipient '%s'",
                normalized_template,
                recipient_email,
            )
            return {
                "success": False,
                "error": "email-guardrail: admin-only template blocked for non-admin recipient",
                "template_key": normalized_template,
                "blocked_recipient": recipient_email,
            }

    # ── v7 Enforcement: override skip_branding unless whitelisted ──
    if skip_branding and not _is_whitelisted_skip_branding(template_key, subject):
        logger.info(f"[v7-enforce] Overriding skip_branding for subject='{subject[:60]}' (not whitelisted)")
        skip_branding = False

    subject = _replace_common_template_placeholders(subject, recipient_name)
    content = _replace_common_template_placeholders(content, recipient_name)
    if content_text:
        content_text = _replace_common_template_placeholders(content_text, recipient_name)

    explicit_dedupe_seed = str(dedupe_key or "").strip()
    fingerprint_seed = ""
    if explicit_dedupe_seed:
        fingerprint_seed = f"seed:{explicit_dedupe_seed.lower()}"
        permanent_key = _build_permanent_idempotency_key(
            explicit_dedupe_seed,
            canonical_recipient,
            normalized_template,
        )
        reserved_perm, perm_error = await _reserve_permanent_email_idempotency_slot(
            idempotency_key=permanent_key,
            recipient_email=canonical_recipient,
            template_key=normalized_template,
            dedupe_seed=explicit_dedupe_seed,
        )
        if perm_error:
            logger.error(
                "[email-idempotency] reservation failed (template=%s recipient=%s key=%s): %s",
                normalized_template,
                recipient_email,
                permanent_key,
                perm_error,
            )
            return {
                "success": False,
                "skipped": True,
                "error": "email-idempotency: reservation failed",
                "template_key": normalized_template,
                "recipient": recipient_email,
                "idempotency_key": permanent_key,
            }
        if not reserved_perm:
            logger.warning(
                "[email-idempotency] duplicate suppressed (template=%s recipient=%s key=%s)",
                normalized_template,
                recipient_email,
                permanent_key,
            )
            return {
                "success": True,
                "skipped": True,
                "error": "email-idempotency: duplicate suppressed",
                "template_key": normalized_template,
                "recipient": recipient_email,
                "idempotency_key": permanent_key,
            }
    else:
        # Global platform-level duplicate suppression for all notifications that
        # do not provide an explicit permanent dedupe key.
        dedupe_candidate = _build_global_notification_dedupe_key(
            canonical_recipient,
            normalized_template,
            subject,
            content,
            content_text,
        )
        dedupe_window = max(_EMAIL_DEDUPE_WINDOW_SECONDS, _EMAIL_GLOBAL_NOTIFICATION_DEDUPE_WINDOW_SECONDS)
        reserved = await _reserve_email_dedupe_slot(dedupe_candidate, dedupe_window)
        if not reserved:
            logger.warning(
                "[email-dedupe] duplicate suppressed (template=%s recipient=%s key=%s)",
                normalized_template,
                recipient_email,
                dedupe_candidate,
            )
            return {
                "success": True,
                "skipped": True,
                "error": "email-dedupe: duplicate suppressed",
                "template_key": normalized_template,
                "recipient": recipient_email,
                "dedupe_key": dedupe_candidate,
            }
        fingerprint_seed = f"global:{dedupe_candidate}"

    # ── Mandatory global cap: never send more than N emails for the same
    # notification fingerprint to the same canonical recipient.
    # Default N=2 (EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT).
    resolved_cap_max = await _resolve_notification_cap_limit(normalized_template)
    notification_cap_key = _build_notification_cap_key(
        canonical_recipient=canonical_recipient,
        template_key=normalized_template,
        fingerprint_seed=fingerprint_seed,
    )
    cap_allowed, cap_count = await _reserve_notification_cap_slot(
        cap_key=notification_cap_key,
        canonical_recipient=canonical_recipient,
        template_key=normalized_template,
        fingerprint_seed=fingerprint_seed,
        max_allowed=resolved_cap_max,
    )
    cap_slot_reserved = bool(cap_allowed)
    if not cap_allowed:
        await _emit_notification_cap_alert(
            cap_key=notification_cap_key,
            canonical_recipient=canonical_recipient,
            template_key=normalized_template,
            current_count=cap_count,
            max_allowed=resolved_cap_max,
            subject=subject,
        )
        logger.warning(
            "[email-cap-guardrail] blocked send (template=%s recipient=%s key=%s count=%s max=%s)",
            normalized_template,
            canonical_recipient,
            notification_cap_key,
            cap_count,
            resolved_cap_max,
        )
        return {
            "success": True,
            "skipped": True,
            "error": "email-cap-guardrail: max sends reached for notification fingerprint",
            "template_key": normalized_template,
            "recipient": recipient_email,
            "cap_key": notification_cap_key,
            "cap_count": cap_count,
            "cap_max": resolved_cap_max,
        }

    # Global dark-mode safety hints for all email templates.
    content = ensure_email_color_scheme_meta(content)

    content = _ensure_darkmode_safe_autonomous_card(content, template_key)

    # Auto-brand only if template content is not already enterprise branded
    if not skip_branding and not _contains_existing_enterprise_branding(content):
        content = _auto_brand_email(content, template_key=template_key, subject=subject)

    # Permanent global adaptive contrast guard for all current/future email templates.
    content = apply_adaptive_email_contrast_guard(content)

    # Safety net: prevent duplicate enterprise footer sections in outbound email HTML.
    content = _dedupe_enterprise_footer_components(content)

    # Outlook-safe inline badge fallback (CID) for footer store badges.
    content, attachments = _apply_outlook_inline_store_badges(content, attachments)

    attachments, attachment_policy_error = _apply_pdf_theme_policy_to_attachments(attachments, template_key=template_key)
    if attachment_policy_error:
        logger.error("[pdf-theme-guard] blocked outbound email attachment: %s", attachment_policy_error)
        if cap_slot_reserved:
            await _release_notification_cap_slot(notification_cap_key)
        return {
            "success": False,
            "error": attachment_policy_error,
            "pdf_theme_violation": True,
            "template_key": template_key,
            "subject": subject,
        }

    from_addr = f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"
    params: Dict[str, Any] = {
        "from": from_addr,
        "to": [recipient_email],
        "subject": subject,
        "html": content,
    }
    if content_text:
        params["text"] = content_text
    if template_key:
        # Primary tag: the template name. When the email is a careers
        # event we also attach the application_id so the Resend webhook
        # can correlate open/click events back to the applicant without
        # needing to parse the subject line.
        params["tags"] = [{"name": "template", "value": template_key}]
        _app_id = (headers or {}).get("X-Application-ID") if headers else None
        if _app_id:
            params["tags"].append({"name": "application_id", "value": str(_app_id)})
    if attachments:
        params["attachments"] = attachments
    # Optional thread-correlation extras (pass-through to Resend).
    if reply_to:
        # Resend SDK accepts either a string or list. Normalize to list for
        # deterministic downstream behaviour; strip blanks.
        _rt = [r.strip() for r in reply_to if isinstance(r, str) and r.strip()]
        if _rt:
            params["reply_to"] = _rt
    if headers:
        _hdrs = {str(k): str(v) for k, v in headers.items() if v is not None}
        if _hdrs:
            params["headers"] = _hdrs

    # ── ZERO ASSUMPTIONS POLICY — outbound content scan ──
    # Scan the final rendered email (subject + html + text) for fabricated
    # business-identity tokens. If any are present — hard-block the send and
    # return a structured error. This is the LAST LINE OF DEFENSE against
    # any LLM-drafted template, footer injection, or unsanitised database
    # variable that could leak a placeholder into a real customer inbox.
    # See /app/memory/ZERO_ASSUMPTIONS_POLICY.md.
    try:
        from utils.zero_assumptions import scan_for_fabrications
        za_hits = scan_for_fabrications({
            "subject": subject,
            "html": content,
            "text": content_text or "",
        })
    except Exception:
        za_hits = []
    if za_hits:
        logger.error(
            "[ZERO-ASSUMPTIONS] BLOCKED outbound email to %s — fabricated "
            "tokens in rendered content: %s. template_key=%s subject=%r",
            recipient_email, za_hits, template_key, subject[:80],
        )
        if cap_slot_reserved:
            await _release_notification_cap_slot(notification_cap_key)
        return {
            "success": False,
            "error": "zero-assumptions: fabricated business-identity token in rendered email; send blocked.",
            "zero_assumptions_violation": True,
            "hits": za_hits,
            "template_key": template_key,
            "subject": subject,
        }

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = await _send_via_resend_with_throttle(params)
            email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", str(result))
            logger.info(f"[Resend] Email sent to {recipient_email}: subject='{subject[:80]}', id={email_id}")

            # Track send for analytics
            if template_key:
                try:
                    await _track_send(email_id, template_key, recipient_email, subject)
                except Exception:
                    pass

            return {
                "success": True,
                "message_id": email_id,
                "provider": "resend",
                "cap_key": notification_cap_key,
                "cap_count": cap_count,
                "delivery_notice": (
                    "Test-domain recipient accepted in non-production. "
                    "Provider accepted the send, but inbox delivery may not occur for synthetic/test domains."
                )
                if test_domain_recipient
                else "",
                "nonprod_test_domain": bool(test_domain_recipient),
            }
        except Exception as exc:
            error_message = str(exc)
            is_rate_limited = any(marker in error_message.lower() for marker in _RESEND_RATE_LIMIT_MARKERS)
            if is_rate_limited and attempt < max_attempts:
                await asyncio.sleep(0.6 * attempt)
                continue
            logger.error(f"[Resend] Failed to send to {recipient_email}: {exc}")
            if cap_slot_reserved:
                await _release_notification_cap_slot(notification_cap_key)
            return {"success": False, "error": error_message, "provider": "resend"}


def _auto_brand_email(html: str, template_key: Optional[str] = None, subject: str = "") -> str:
    """Auto-brand any email HTML with the v7 colorful header + enterprise footer.

    Detects the email's theme and category from template_key (primary) or subject (fallback),
    then wraps with:
    - Category-specific gradient header (v7 design standard)
    - Enterprise footer at the bottom
    """
    from utils.email_templates import brand_email

    # If already branded, do not wrap again.
    if _contains_existing_enterprise_branding(html):
        return html

    tpl = str(template_key or "").strip().lower()

    # Detect category from template_key (primary) or subject (fallback)
    category = _detect_category_from_key(tpl)
    if category == "general" and subject:
        category = _detect_category_from_subject(subject)

    if "learning_hub" in tpl or "weekly_course_release" in tpl:
        theme = "dark" if "_dark" in tpl else "light"
    else:
        # Detect theme from background color in body or outer div
        is_dark = bool(re.search(r'background[:\s]*#0[0-9a-fA-F]{5}|background[:\s]*#1[0-9a-fA-F]{5}', html))
        theme = "dark" if is_dark else "light"

    # Extract inner body content
    body_match = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL | re.IGNORECASE)
    if body_match:
        inner = body_match.group(1).strip()
    else:
        inner = html

    # Remove outer wrapper divs that set their own max-width/margin centering
    outer_div_match = re.match(
        r'^\s*<(?:div|table)[^>]*max-width[^>]*>\s*(.*)\s*</(?:div|table)>\s*$',
        inner, re.DOTALL | re.IGNORECASE,
    )
    if outer_div_match:
        inner = outer_div_match.group(1).strip()

    # Remove any duplicate app logo images already in the inner content
    inner = re.sub(
        r'<img[^>]*' + re.escape(CDN_APP_LOGO) + r'[^>]*/?\s*>',
        '', inner, flags=re.IGNORECASE
    )

    branded = brand_email(inner, theme, category=category)
    if ("learning_hub" in tpl or "weekly_course_release" in tpl) and theme != "dark":
        branded = _lock_light_email_rendering(branded)
    return branded


# v7 category detection from template_key for non-template emails
# Order matters: more specific domain keywords BEFORE generic ones like session/schedule/reminder
_KEY_CATEGORY_MAP = [
    # --- Highly specific (multi-word / unique) ---
    ("self_repair", "communication"), ("integrity", "communication"), ("autofix", "communication"),
    ("magic_link", "security"), ("lockout", "security"), ("suspicious", "security"),
    ("fraud", "security"), ("password", "security"), ("otp", "security"), ("siem", "security"),
    ("block", "security"), ("ban", "security"), ("threat", "security"),
    ("security", "security"),
    # --- Jobs (before hiring/calendar — "job_alert" etc.) ---
    ("job_alert", "jobs"), ("job_match", "jobs"), ("job_recommend", "jobs"),
    # --- Hiring (before calendar — "interview"/"career" are domain-specific) ---
    ("applicant", "hiring"), ("interview", "hiring"), ("career", "hiring"),
    ("recruit", "hiring"), ("hiring", "hiring"),
    # --- Employer ---
    ("employer", "employer"), ("company", "employer"), ("job_post", "employer"),
    # --- Verification ---
    ("verif", "verification"), ("kyc", "verification"), ("idv", "verification"), ("identity", "verification"),
    # --- Communication (before AI — "performance"/"webhook" must not fall into AI's "report") ---
    ("performance", "communication"), ("webhook", "communication"), ("integration", "communication"),
    ("ops", "communication"), ("system", "communication"), ("monitor", "communication"),
    ("health", "communication"), ("status", "communication"),
    # --- AI (specific keywords; bare "ai" handled separately in _detect_category_from_key) ---
    ("coaching", "ai"), ("learning", "ai"), ("course", "ai"),
    ("report", "ai"), ("analytics", "ai"), ("insight", "ai"), ("gpt", "ai"),
    # --- Onboarding (before engagement — "welcome" is domain-specific) ---
    ("welcome", "onboarding"), ("onboard", "onboarding"), ("signup", "onboarding"), ("register", "onboarding"),
    ("drip", "onboarding drip"),
    # --- Engagement (before calendar — "streak"/"digest" are domain-specific) ---
    ("streak", "engagement"), ("nudge", "engagement"), ("activity", "engagement"),
    ("feature_update", "engagement"), ("newsletter", "engagement"),
    # --- Notifications (before engagement's "digest" to avoid misroute) ---
    ("notification", "notifications"), ("push", "notifications"), ("broadcast", "notifications"),
    # --- Remaining engagement ---
    ("digest", "engagement"), ("weekly", "engagement"),
    # --- Calendar (generic words go late) ---
    ("booking", "calendar"), ("meeting", "calendar"), ("calendar", "calendar"),
    ("session", "calendar"), ("schedule", "calendar"), ("reminder", "calendar"), ("agenda", "calendar"),
    # --- Billing ---
    ("invoice", "billing"), ("receipt", "billing"), ("billing", "billing"),
    ("subscription", "billing"), ("renewal", "billing"), ("refund", "billing"),
    ("charge", "billing"), ("revenue", "billing"), ("payout", "billing"), ("payment", "billing"),
    # --- Support ---
    ("escalat", "support"), ("feedback", "support"), ("csat", "support"),
    ("contact", "support"), ("ticket", "support"), ("support", "support"),
    # --- Account ---
    ("account", "account"),
    # --- Generic alert (last) ---
    ("alert", "security"),
]


def _detect_category_from_key(key: str) -> str:
    """Detect email category from template_key for v7 color assignment."""
    if not key:
        return "general"
    for keyword, cat in _KEY_CATEGORY_MAP:
        if keyword in key:
            return cat
    # Special handling for "ai" — only match as a word boundary to avoid false positives
    # (e.g., "email" contains "ai" but is NOT an AI email)
    if re.search(r'(?:^|_)ai(?:_|$)', key):
        return "ai"
    return "general"


# ── v7 Enforcement Guardrails ────────────────────────────

# Whitelisted template_key patterns that legitimately need skip_branding
_SKIP_BRANDING_WHITELIST = [
    "brand_acceptance",       # Brand acceptance reports with inline logos
    "logo_probe",             # Logo probe images with inline attachments
    "nightly_export",         # Nightly export with raw data attachments
]


def _is_whitelisted_skip_branding(template_key: Optional[str], subject: str) -> bool:
    """Check if this email is whitelisted to legitimately bypass v7 branding."""
    key = (template_key or "").lower()
    subj = subject.lower()
    for wl in _SKIP_BRANDING_WHITELIST:
        if wl in key or wl in subj:
            return True
    # Brand integrity reports with logos
    if "brand" in subj and ("acceptance" in subj or "integrity" in subj or "probe" in subj):
        return True
    return False


def _v7_warn_missing_template_key(subject: str, recipient: str):
    """Log a warning AND persist a row in v7_violations for the admin email-health dashboard."""
    logger.warning(
        f"[v7-guardrail] send_email called without template_key. "
        f"subject='{subject[:80]}', to={recipient}. "
        f"Consider using send_catalog_template() for full v7 design."
    )
    # Best-effort async persist — don't let a DB hiccup break the caller
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio
        async def _persist():
            mongo_url = os.environ.get("MONGO_URL")
            db_name = os.environ.get("DB_NAME")
            if not mongo_url or not db_name:
                return
            db = AsyncIOMotorClient(mongo_url)[db_name]
            await db.v7_violations.insert_one({
                "subject": (subject or "")[:200],
                "recipient": recipient,
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            })
            # Slack/Teams alert for V7 violation (rate-limited — only if not already alerted in last hour)
            try:
                from datetime import timedelta
                cutoff = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - timedelta(hours=1)).isoformat()
                recent = await db.webhook_alerts_log.find_one({
                    "event_type": "v7_violation",
                    "created_at": {"$gte": cutoff},
                    "dispatched": True,
                })
                if not recent:
                    from services.webhook_alerts import send_alert as _send_wh
                    await _send_wh(
                        event_type="v7_violation",
                        severity="warning",
                        title="V7 guardrail violation — email sent without template_key",
                        summary="`send_email()` was called without a `template_key` argument, bypassing the V7 branded layout.",
                        fields={
                            "Subject": (subject or "")[:120],
                            "Recipient": recipient,
                            "Guidance": "Migrate caller to `send_catalog_template(key, ...)`.",
                        },
                        url=None,
                    )
            except Exception:
                pass
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_persist())
    except Exception:
        pass


def _detect_category_from_subject(subject: str) -> str:
    """Fallback category detection from email subject line when template_key is missing."""
    if not subject:
        return "general"
    subj = subject.lower()
    for keyword, cat in _KEY_CATEGORY_MAP:
        if keyword in subj:
            return cat
    if re.search(r'\bai\b', subj):
        return "ai"
    return "general"


def _lock_light_email_rendering(html: str) -> str:
    """Force light rendering for Outlook/Gmail dark mode on newsletter-style templates."""
    if not html:
        return html

    # Ensure body has light-lock class
    if re.search(r"<body[^>]*class=", html, flags=re.IGNORECASE):
        html = re.sub(
            r'(<body[^>]*class=")([^"]*)(")',
            lambda m: f'{m.group(1)}{m.group(2)} em-lock-light{m.group(3)}',
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        html = re.sub(r"<body", '<body class="em-lock-light"', html, count=1, flags=re.IGNORECASE)

    # Pin color-scheme meta to light
    html = re.sub(
        r'<meta\s+name="color-scheme"\s+content="[^"]*"\s*/?>',
        '<meta name="color-scheme" content="light" />',
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<meta\s+name="supported-color-schemes"\s+content="[^"]*"\s*/?>',
        '<meta name="supported-color-schemes" content="light" />',
        html,
        flags=re.IGNORECASE,
    )

    lock_css = """
<style data-light-lock="learning-hub-v2">
body.em-lock-light, body.em-lock-light .email-outer, body.em-lock-light .em-outer { background:#F8FAFC !important; }
body.em-lock-light .email-card, body.em-lock-light .em-card { background:#FFFFFF !important; border-color:#334155 !important; }
body.em-lock-light .email-body, body.em-lock-light .em-body, body.em-lock-light .em-force-light-card {
  background:#FFFFFF !important; border-color:#334155 !important; color:#0F172A !important; -webkit-text-fill-color:#0F172A !important;
}
body.em-lock-light .email-body *, body.em-lock-light .em-body *, body.em-lock-light .em-force-light-card * {
  color:#0F172A !important; -webkit-text-fill-color:#0F172A !important;
}
body.em-lock-light .em-force-muted-text { color:#475569 !important; -webkit-text-fill-color:#475569 !important; }
body.em-lock-light .em-footer-bg { background:#F8FAFC !important; }
body.em-lock-light .em-footer-card { background:#FFFFFF !important; border-color:#334155 !important; }
body.em-lock-light .em-footer-t1 { color:#0F172A !important; }
body.em-lock-light .em-footer-t2 { color:#475569 !important; }
body.em-lock-light .em-footer-t3 { color:#64748B !important; }
body.em-lock-light a { color:#2563EB !important; }
[data-ogsc] body.em-lock-light .email-card,
[data-ogsc] body.em-lock-light .em-card,
[data-ogsc] body.em-lock-light .email-body,
[data-ogsc] body.em-lock-light .em-body,
[data-ogsc] body.em-lock-light .em-force-light-card {
  background:#FFFFFF !important; border-color:#334155 !important; color:#0F172A !important; -webkit-text-fill-color:#0F172A !important;
}
body[data-ogsc].em-lock-light .email-card,
body[data-ogsc].em-lock-light .em-card,
body[data-ogsc].em-lock-light .email-body,
body[data-ogsc].em-lock-light .em-body,
body[data-ogsc].em-lock-light .em-force-light-card {
  background:#FFFFFF !important; border-color:#334155 !important; color:#0F172A !important; -webkit-text-fill-color:#0F172A !important;
}
</style>
"""

    if "</head>" in html.lower():
        html = re.sub(r"</head>", lock_css + "\n</head>", html, count=1, flags=re.IGNORECASE)
    else:
        html = lock_css + html
    return html


async def _track_send(email_id: str, template_key: str, recipient: str, subject: str):
    """Store send record for analytics matching."""
    from datetime import datetime, timezone

    try:
        from routes.db import db

        await db.email_sends.insert_one(
            {
                "email_id": email_id,
                "template_key": template_key,
                "recipient": recipient,
                "subject": subject[:100],
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        pass


async def send_template_email(
    recipient_email: str,
    template_key: str,
    data: Dict[str, Any],
    subject: Optional[str] = None,
    contact_external_id: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    expected_user_id: Optional[str] = None,
    enforce_verified_primary: bool = False,
) -> Dict[str, Any]:
    """Render a template and send via Resend."""
    if not is_email_configured():
        return {"success": False, "error": "Email service not configured"}

    rendered_subject = subject or f"Your {template_key.replace('-', ' ').title()}"
    html = _render_template_html(template_key, data, rendered_subject)
    return await send_email(
        recipient_email,
        rendered_subject,
        html,
        template_key=template_key,
        dedupe_key=dedupe_key,
        expected_user_id=expected_user_id,
        enforce_verified_primary=enforce_verified_primary,
    )


async def send_catalog_template(
    recipient_email: str,
    template_key: str,
    recipient_name: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Send an email using a registered TEMPLATE_CATALOG builder.
    
    Usage:
        await send_catalog_template(
            "user@example.com", "referral_invite",
            referrer_name="Alex", referral_link="https://..."
        )
    """
    from utils.email_templates import TEMPLATE_CATALOG
    
    entry = TEMPLATE_CATALOG.get(template_key)
    if not entry:
        return {"success": False, "error": f"Template '{template_key}' not found in catalog"}

    # Pop transport-level kwargs out of the builder payload so builders don't
    # need to declare them. `attachments` is the primary case (ICS invites,
    # inline images, PDFs). `reply_to` and `headers` are used by the careers
    # thread feature to correlate applicant replies. `subject_override`
    # lets the caller (e.g. newsletter TZ dispatcher running an A/B test by
    # local-hour cohort) replace the template's default subject line
    # without having to fork the template builder.
    attachments = kwargs.pop("attachments", None)
    reply_to = kwargs.pop("reply_to", None)
    extra_headers = kwargs.pop("headers", None)
    subject_override = kwargs.pop("subject_override", None)
    dedupe_key = kwargs.pop("dedupe_key", None)
    expected_user_id = kwargs.pop("expected_user_id", None)
    enforce_verified_primary = bool(kwargs.pop("enforce_verified_primary", False))

    tpl = entry["builder"](**kwargs)
    return await send_email(
        recipient_email=recipient_email,
        subject=subject_override or tpl.subject,
        content=tpl.html,
        recipient_name=recipient_name,
        template_key=template_key,
        content_text=tpl.text if hasattr(tpl, "text") and tpl.text else None,
        attachments=attachments,
        reply_to=reply_to,
        headers=extra_headers,
        dedupe_key=dedupe_key,
        expected_user_id=expected_user_id,
        enforce_verified_primary=enforce_verified_primary,
    )


def _language_guidance_footer_html(lang_hint: str = "en", template_key: str = "") -> str:
    lang = (lang_hint or "en").split("-")[0].lower()
    template_ctx = (template_key or "").lower()
    settings_url = f"{FRONTEND_BASE_URL.rstrip('/')}/language-selector" if FRONTEND_BASE_URL else "/language-selector"

    default_copy = {
        "en": ("Prefer another language?", "Update language preferences in Settings.", "Open Language Settings"),
        "fr": ("Vous préférez une autre langue ?", "Mettez à jour vos préférences dans les paramètres.", "Ouvrir les paramètres de langue"),
        "es": ("¿Prefieres otro idioma?", "Actualiza tus preferencias en Configuración.", "Abrir configuración de idioma"),
        "de": ("Bevorzugen Sie eine andere Sprache?", "Aktualisieren Sie Ihre Sprache in den Einstellungen.", "Spracheinstellungen öffnen"),
        "pt": ("Prefere outro idioma?", "Atualize o idioma nas Configurações.", "Abrir configurações de idioma"),
    }
    welcome_copy = {
        "en": ("Want onboarding in your language?", "Switch your account language to personalize welcome journeys and help content.", "Set My Language"),
        "fr": ("Vous voulez l'accueil dans votre langue ?", "Changez la langue du compte pour personnaliser l'onboarding et l'aide.", "Définir ma langue"),
        "es": ("¿Quieres el onboarding en tu idioma?", "Cambia el idioma de la cuenta para personalizar la bienvenida y la ayuda.", "Definir mi idioma"),
        "de": ("Möchten Sie das Onboarding in Ihrer Sprache?", "Ändern Sie die Kontosprache für personalisierte Inhalte.", "Meine Sprache festlegen"),
        "pt": ("Quer onboarding no seu idioma?", "Altere o idioma da conta para personalizar o conteúdo inicial.", "Definir meu idioma"),
    }
    security_copy = {
        "en": ("Security alerts in your language", "For faster response during security events, set your preferred language now.", "Update Security Language"),
        "fr": ("Alertes de sécurité dans votre langue", "Pour réagir plus vite en cas d'alerte, définissez votre langue préférée.", "Mettre à jour la langue de sécurité"),
        "es": ("Alertas de seguridad en tu idioma", "Para reaccionar más rápido ante eventos de seguridad, ajusta tu idioma.", "Actualizar idioma de seguridad"),
        "de": ("Sicherheitswarnungen in Ihrer Sprache", "Für schnellere Reaktionen bei Vorfällen: Sprache jetzt einstellen.", "Sicherheitssprache aktualisieren"),
        "pt": ("Alertas de segurança no seu idioma", "Para responder mais rápido a incidentes, ajuste seu idioma.", "Atualizar idioma de segurança"),
    }
    payment_copy = {
        "en": ("Billing updates in your language", "Keep payment confirmations and invoice notices aligned with your preferred language.", "Update Billing Language"),
        "fr": ("Facturation dans votre langue", "Alignez confirmations de paiement et factures avec votre langue préférée.", "Mettre à jour la langue de facturation"),
        "es": ("Facturación en tu idioma", "Mantén pagos y facturas alineados con tu idioma preferido.", "Actualizar idioma de facturación"),
        "de": ("Abrechnung in Ihrer Sprache", "Zahlungs- und Rechnungsinfos auf Ihre Sprache abstimmen.", "Abrechnungssprache aktualisieren"),
        "pt": ("Cobrança no seu idioma", "Mantenha confirmações de pagamento e faturas no idioma preferido.", "Atualizar idioma de cobrança"),
    }

    copy = default_copy
    if any(k in template_ctx for k in ["welcome", "onboarding"]):
        copy = welcome_copy
    elif any(k in template_ctx for k in ["security", "password", "otp", "2fa"]):
        copy = security_copy
    elif any(k in template_ctx for k in ["payment", "invoice", "receipt", "billing", "subscription"]):
        copy = payment_copy

    title, msg, cta = copy.get(lang, copy["en"])
    return f"""
<div style=\"margin-top:14px;padding:12px;border-radius:10px;background:#F8FAFC;border:1px solid #CBD5E1;\">
  <div style=\"color:#334155;font-size:12px;font-weight:700;\">{title}</div>
  <div style=\"color:#94A3B8;font-size:12px;margin-top:4px;\">{msg}</div>
  <a href=\"{settings_url}\" style=\"display:inline-block;margin-top:8px;color:#7DD3FC;font-size:12px;font-weight:700;text-decoration:none;\">{cta}</a>
</div>
"""


def _render_template_html(template_key: str, data: Dict[str, Any], subject: str) -> str:
    """Legacy generic fallback renderer. Routes through `_wrap()` so the
    output carries the V7 `em-outer` fingerprint (required by the runtime
    guardrail below)."""
    from utils.email_templates import _wrap, _lead, DASH_URL
    code = data.get("code", data.get("otp_code", ""))
    user_name = data.get("user_name", data.get("name", ""))
    expiry = data.get("expiry_minutes", 10)

    if "otp" in template_key.lower() or code:
        from utils.email_templates import build_otp_email

        return build_otp_email(str(code), user_name or "there", int(expiry)).html

    body_parts: list[str] = []
    for k, v in data.items():
        if k in ("code", "otp_code"):
            continue
        body_parts.append(
            f'<p class="em-text" style="color:#334155;font-size:14px;margin:0 0 10px;"><strong>{k.replace("_", " ").title()}</strong>: {v}</p>'
        )
    body_inner = "".join(body_parts) or f'<p class="em-text" style="color:#334155;font-size:14px;">{subject}</p>'
    lang_hint = str(data.get("language") or data.get("preferred_language") or "en")
    guidance_html = _language_guidance_footer_html(lang_hint, template_key)
    inner = _lead(subject, "Enterprise account notification") + body_inner + (guidance_html or "")
    return _wrap(subject, "Enterprise account notification", inner, "Open Account", f"{DASH_URL}/account", category="account")


async def notify_export_ready(
    user_email: str,
    user_name: str = "",
    export_type: str = "Data Export",
    file_format: str = "CSV",
    download_url: str = "",
    expires_in: str = "7 days",
):
    """Reusable helper to send a data_export_ready email after any export completes."""
    if not is_email_configured():
        return
    try:
        await send_catalog_template(
            recipient_email=user_email,
            template_key="data_export_ready",
            recipient_name=user_name,
            user_name=user_name or "there",
            export_type=export_type,
            file_format=file_format,
            download_url=download_url,
            expires_in=expires_in,
        )
    except Exception:
        pass
