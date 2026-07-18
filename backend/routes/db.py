"""Shared database, configuration, and auth utilities for all route modules."""

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request
import os
import re
import logging
import bcrypt
import uuid
from jose import jwt, JWTError
from utils.rate_limit import check_rate_limit
from utils.access_control_engine import build_employee_permissions, required_employee_permission, compute_effective_plan

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)

# MongoDB
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Keys
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("FATAL: JWT_SECRET environment variable is not set. Refusing to start with insecure defaults.")
ADMIN_EMAILS = [email.strip().lower() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()]
ADMIN_OVERRIDE_EMAILS_ENV_RAW = os.environ.get("ADMIN_OVERRIDE_EMAILS")
ADMIN_OVERRIDE_EMAILS = [
    email.strip().lower()
    for email in str(ADMIN_OVERRIDE_EMAILS_ENV_RAW or "").split(",")
    if email.strip()
]
ADMIN_SEED_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SUPER_ADMIN_EMAILS: list[str] = []
SUPER_ADMIN_OVERRIDE_EMAILS: list[str] = []
FULL_ACCESS_USERS: list[dict] = []
FULL_ACCESS_EMAILS: list[str] = []

# Users with restricted/locked access
LOCKED_USERS = ["creator@realaicoach.app"]

ROLE_VALUES = {"guest", "user", "basic", "premium", "full_users", "admin"}

logger = logging.getLogger(__name__)

if ADMIN_OVERRIDE_EMAILS_ENV_RAW is None:
    logger.warning(
        "SECURITY: ADMIN_OVERRIDE_EMAILS is unset; admin override allowlist defaults to empty."
    )


# ── Shared User Model ──
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    auth_provider: str = "email"
    password_hash: Optional[str] = None
    subscription_plan: str = "free"
    subscription_status: str = "active"
    role: str = "user"
    role_updated_at: Optional[datetime] = None
    role_updated_by: Optional[str] = None
    token_version: int = 0
    is_admin: bool = False
    full_access: bool = False
    roles: List[str] = Field(default_factory=list)
    email_verified: bool = False
    stripe_customer_id: Optional[str] = None
    subscription_end_date: Optional[datetime] = None
    payment_verified: bool = False
    subscription_permanent: bool = False
    platform_role: Optional[str] = None
    premium_access: bool = False
    feature_access: List[str] = Field(default_factory=list)
    employee_permissions: List[str] = Field(default_factory=list)
    pending_subscription_transition: Optional[Dict[str, Any]] = None
    delegated_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


import hashlib

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")

def _hash_refresh_token(raw: str) -> str:
    """SHA-256 hex hash of a refresh token for safe storage. Returns raw value if already hashed."""
    if not raw or _HEX64_RE.match(raw):
        return raw
    return hashlib.sha256(raw.encode()).hexdigest()

class UserSession(BaseModel):
    user_id: str
    session_token: str
    refresh_token: Optional[str] = None
    token_version: int = 0
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("refresh_token", mode="before")
    @classmethod
    def hash_refresh_token_on_store(cls, v):
        if v and isinstance(v, str):
            return _hash_refresh_token(v)
        return v


def _parse_email_set(raw: str) -> set[str]:
    return {
        email.strip().lower()
        for email in str(raw or "").split(",")
        if str(email or "").strip()
    }


def _is_non_production_runtime() -> bool:
    env_values = [
        str(os.environ.get("ENVIRONMENT") or "").strip().lower(),
        str(os.environ.get("APP_ENV") or "").strip().lower(),
        str(os.environ.get("NODE_ENV") or "").strip().lower(),
    ]

    for value in env_values:
        if value in {"prod", "production", "live"}:
            return False

    for value in env_values:
        if value in {"dev", "development", "test", "testing", "staging", "preview", "local", "localhost"}:
            return True

    frontend_host = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().lower()
    if "localhost" in frontend_host or "127.0.0.1" in frontend_host:
        return True
    if "preview.emergentagent.com" in frontend_host:
        return True

    return False


_RISK_PREVIEW_BYPASS_DEFAULT_EMAILS: set[str] = set()


def _risk_preview_bypass_email_allowlist() -> set[str]:
    configured = _parse_email_set(os.environ.get("PROGRESSIVE_RISK_PREVIEW_BYPASS_EMAILS", ""))
    combined = set(_RISK_PREVIEW_BYPASS_DEFAULT_EMAILS)
    combined.update(configured)
    return {email for email in combined if email}


def _risk_preview_bypass_enabled() -> bool:
    raw_toggle = str(os.environ.get("PROGRESSIVE_RISK_PREVIEW_BYPASS_ENABLED") or "").strip().lower()
    if raw_toggle:
        return raw_toggle in {"1", "true", "yes", "on", "enabled"}
    return _is_non_production_runtime()


def _should_allow_preview_risk_bypass(user: Optional[User]) -> bool:
    if not user or not bool(getattr(user, "is_admin", False)):
        return False
    if not _is_non_production_runtime() or not _risk_preview_bypass_enabled():
        return False
    email = str(getattr(user, "email", "") or "").strip().lower()
    if not email:
        return False
    return email in _risk_preview_bypass_email_allowlist()


async def _apply_preview_risk_bypass_if_allowed(
    *,
    user: User,
    request: Request,
    active_risk: Dict[str, Any],
    bypass_scope: str,
) -> bool:
    if not _should_allow_preview_risk_bypass(user):
        return False

    level = str(active_risk.get("risk_level") or "high").lower()
    await log_security_event(
        user.user_id,
        "risk_engine_preview_bypass_applied",
        "medium",
        request,
        {
            "bypass_scope": bypass_scope,
            "risk_score": int(active_risk.get("risk_score") or 0),
            "risk_level": level,
            "trigger": active_risk.get("trigger"),
            "session_protection": active_risk.get("session_protection"),
            "mode": "preview",
            "allowlisted_admin": str(getattr(user, "email", "") or "").strip().lower(),
        },
    )
    return True


# ── Auth Helper Functions ──
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_jwt_token(user_id: str, email: str, token_version: int = 0, expires_minutes: int = 300) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "token_version": token_version,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def is_admin_email(email: str) -> bool:
    if not email:
        return False
    lower = email.lower()
    return lower in ADMIN_EMAILS or lower in ADMIN_OVERRIDE_EMAILS


def is_full_access_email(email: str) -> bool:
    return False


def is_super_admin_email(email: str) -> bool:
    return False


def normalize_role_value(role: str) -> str:
    if not role:
        return ""
    cleaned = role.strip().lower().replace(" ", "_")
    if cleaned == "fullusers":
        cleaned = "full_users"
    return cleaned


def resolve_user_role(user: Optional[User]) -> str:
    if not user:
        return "guest"
    if user.is_admin:
        return "admin"
    effective_plan = compute_effective_plan(
        {
            "is_admin": bool(user.is_admin),
            "full_access": False,
            "subscription_permanent": False,
            "subscription_plan": user.subscription_plan,
            "subscription_status": user.subscription_status,
            "subscription_end_date": user.subscription_end_date,
            "pending_subscription_transition": user.pending_subscription_transition,
            "payment_verified": getattr(user, "payment_verified", False),
        }
    )
    if effective_plan == "premium":
        return "premium"
    if effective_plan == "basic":
        return "basic"
    if user.role:
        normalized = normalize_role_value(user.role)
        if normalized in ROLE_VALUES:
            return normalized
    return "user"


def _compute_system_roles(user: User) -> List[str]:
    roles = set(user.roles or [])
    base_role = resolve_user_role(user)
    if base_role and base_role != "guest":
        roles.add(base_role)
    roles.add("user")
    effective_plan = compute_effective_plan(
        {
            "is_admin": bool(user.is_admin),
            "subscription_plan": user.subscription_plan,
            "subscription_status": user.subscription_status,
            "subscription_end_date": user.subscription_end_date,
            "pending_subscription_transition": user.pending_subscription_transition,
            "payment_verified": getattr(user, "payment_verified", False),
            "full_access": False,
            "subscription_permanent": False,
        }
    )
    if effective_plan == "basic":
        roles.add("basic")
    if effective_plan == "premium":
        roles.add("premium")
    if user.is_admin:
        roles.add("admin")
    cleaned = {normalize_role_value(r) for r in roles if normalize_role_value(r)}
    return sorted({r for r in cleaned if r in ROLE_VALUES})


async def sync_user_roles(user: User) -> User:
    if not user:
        return user
    computed_role = resolve_user_role(user)
    updated_roles = _compute_system_roles(user)
    updates = {}
    if computed_role and computed_role != user.role:
        user.role = computed_role
        updates["role"] = computed_role
    if updated_roles != (user.roles or []):
        user.roles = updated_roles
        updates["roles"] = updated_roles
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": updates},
        )
    return user


def user_has_role(user: Optional[User], role: str) -> bool:
    if not user:
        return False
    target = normalize_role_value(role)
    if not target:
        return False
    if resolve_user_role(user) == target:
        return True
    return target in {normalize_role_value(r) for r in (user.roles or [])}


def get_user_employee_permissions(user: Optional[User]) -> List[str]:
    if not user:
        return []
    doc = {
        "platform_role": getattr(user, "platform_role", None),
        "employee_permissions": list(getattr(user, "employee_permissions", []) or []),
    }
    return build_employee_permissions(doc)


async def require_roles(request: Request, roles: List[str]) -> User:
    user = await require_auth(request)
    allowed = {normalize_role_value(r) for r in roles if normalize_role_value(r)}
    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if not any(user_has_role(user, role) for role in allowed):
        await log_security_event(user.user_id, "role_denied", "high", request, {"required": list(allowed)})
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


async def require_admin_or_employee_permission(request: Request, permission: str) -> User:
    user = await require_auth(request)
    if user.is_admin:
        active_risk = await _get_active_admin_risk_profile(user.user_id)
        if active_risk:
            bypassed = await _apply_preview_risk_bypass_if_allowed(
                user=user,
                request=request,
                active_risk=active_risk,
                bypass_scope="require_admin_or_employee_permission",
            )
            if bypassed:
                return user
            level = str(active_risk.get("risk_level") or "high").lower()
            await log_security_event(
                user.user_id,
                "risk_engine_admin_blocked",
                "critical" if level == "critical" else "high",
                request,
                {
                    "risk_score": int(active_risk.get("risk_score") or 0),
                    "risk_level": level,
                    "trigger": active_risk.get("trigger"),
                },
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Admin privileged APIs are temporarily blocked by the Progressive Risk Engine.",
                    "code": "risk_engine_admin_api_blocked",
                    "risk_engine": {
                        "risk_level": level,
                        "risk_score": int(active_risk.get("risk_score") or 0),
                        "trigger": active_risk.get("trigger"),
                        "output_block": active_risk.get("output_block"),
                    },
                },
            )
        return user
    perms = set(get_user_employee_permissions(user))
    if permission in perms:
        return user
    await log_security_event(
        user.user_id,
        "employee_permission_denied",
        "medium",
        request,
        {"required_permission": permission, "granted_permissions": sorted(list(perms))},
    )
    raise HTTPException(status_code=403, detail="Insufficient employee permissions")


async def apply_full_access(user: User) -> User:
    return user


async def apply_admin_access(user: User) -> User:
    if not user or not is_admin_email(user.email):
        return user

    user.is_admin = True
    user.full_access = True
    user.subscription_plan = "premium"
    user.subscription_status = "active"
    user.role = "admin"
    user.roles = _compute_system_roles(user)

    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "is_admin": True,
                "full_access": True,
                "role": "admin",
                "roles": user.roles,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return user


async def apply_access_overrides(user: User) -> User:
    user = await apply_full_access(user)
    user = await apply_admin_access(user)
    user = await sync_user_roles(user)
    return user


def is_privileged_user(user: Optional[User]) -> bool:
    if not user:
        return False
    return resolve_user_role(user) in {"admin"}


def has_basic_access(user: Optional[User]) -> bool:
    if is_privileged_user(user):
        return True
    from utils.preprod_entitlement_lock import is_preprod_lock_active

    if is_preprod_lock_active():
        return False
    return bool(user and resolve_user_role(user) in {"basic", "premium"})


def has_premium_access(user: Optional[User]) -> bool:
    if is_privileged_user(user):
        return True
    from utils.preprod_entitlement_lock import is_preprod_lock_active

    if is_preprod_lock_active():
        return False
    return bool(user and resolve_user_role(user) == "premium")


async def ensure_full_access_users() -> None:
    # Enforce locked users
    for locked_email in LOCKED_USERS:
        await db.users.update_one(
            {"email": locked_email.lower()},
            {
                "$set": {
                    "access_locked": True,
                    "subscription_permanent": False,
                    "full_access": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    logger.info(f"Locked users enforced: {LOCKED_USERS}")


async def ensure_admin_users() -> None:
    """Promote existing admin-email accounts to admin role. Does NOT create accounts — admins self-register."""
    admin_emails = sorted(set([*ADMIN_EMAILS, *ADMIN_OVERRIDE_EMAILS]))
    for email in admin_emails:
        if not email:
            continue
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if not existing:
            logger.info(f"Admin email {email} not yet registered — will be auto-promoted on registration.")
            continue
        roles = ["user", "premium", "admin"]
        update_payload = {
            "subscription_plan": "premium",
            "subscription_status": "active",
            "subscription_permanent": True,
            "is_admin": True,
            "full_access": True,
            "role": "admin",
            "roles": roles,
            "updated_at": datetime.now(timezone.utc),
        }
        password_matches_seed = False
        existing_hash = str(existing.get("password_hash") or "")
        if ADMIN_SEED_PASSWORD and existing_hash:
            try:
                password_matches_seed = verify_password(ADMIN_SEED_PASSWORD, existing_hash)
            except Exception:
                password_matches_seed = False
        if ADMIN_SEED_PASSWORD and not existing_hash:
            # Initial seed: account has no password yet (e.g. SSO-registered) — safe, not a rewrite.
            update_payload["password_hash"] = hash_password(ADMIN_SEED_PASSWORD)
            update_payload["admin_seed_password_rotated_at"] = datetime.now(timezone.utc)
            logger.info(f"Admin password for {email} initially seeded from ADMIN_PASSWORD env.")
        elif ADMIN_SEED_PASSWORD and not password_matches_seed:
            # Opt-in only: rewriting an EXISTING credential from env must be explicit,
            # otherwise in-app password changes are silently reverted on every restart.
            enforce_sync = os.environ.get("ADMIN_PASSWORD_ENFORCE_SYNC", "").strip().lower() in {"1", "true", "yes"}
            if enforce_sync:
                update_payload["password_hash"] = hash_password(ADMIN_SEED_PASSWORD)
                update_payload["admin_seed_password_rotated_at"] = datetime.now(timezone.utc)
                logger.info(
                    f"Admin password for {email} rotated from ADMIN_PASSWORD env (ADMIN_PASSWORD_ENFORCE_SYNC enabled)."
                )
            else:
                logger.info(
                    f"Admin password for {email} differs from ADMIN_PASSWORD env; sync SKIPPED "
                    "(set ADMIN_PASSWORD_ENFORCE_SYNC=true to enforce rotation from env)."
                )
        await db.users.update_one({"email": email}, {"$set": update_payload})
        logger.info(f"Admin privileges ensured for {email}.")
    return None


async def log_security_event(
    user_id: Optional[str],
    event_type: str,
    risk_level: str,
    request: Optional[Request] = None,
    details: Optional[Dict[str, Any]] = None,
):
    payload = details.copy() if details else {}
    ip_address = None
    if request:
        ip_address = request.client.host if request.client else None
        payload.update(
            {
                "path": request.url.path,
                "method": request.method,
                "user_agent": request.headers.get("user-agent"),
            }
        )
    await db.security_events.insert_one(
        {
            "event_id": f"sec_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "ip_address": ip_address,
            "event_type": event_type,
            "risk_level": risk_level,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": payload,
        }
    )
    # Broadcast to public activity stream (login page live feed)
    try:
        from utils.ws_manager import broadcast_security_event
        import asyncio

        asyncio.ensure_future(broadcast_security_event(event_type, risk_level))
    except Exception:
        pass


async def log_authorization_audit(
    actor_user_id: Optional[str],
    actor_email: Optional[str],
    action: str,
    outcome: str,
    request: Optional[Request] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    payload = metadata.copy() if metadata else {}
    if request:
        payload.update(
            {
                "path": request.url.path,
                "method": request.method,
                "ip": request.client.host if request.client else None,
            }
        )
    await db.authorization_audit_log.insert_one(
        {
            "audit_id": f"authz_{uuid.uuid4().hex[:12]}",
            "actor_user_id": actor_user_id,
            "actor_email": actor_email,
            "action": action,
            "outcome": outcome,
            "metadata": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def is_security_blocked(user_id: Optional[str], ip_address: Optional[str]) -> Optional[dict]:
    # Never block internal Kubernetes/ingress proxy IPs — they are infrastructure, not users
    if ip_address and (ip_address.startswith("10.") or ip_address.startswith("172.") or ip_address in ("127.0.0.1", "::1", "localhost")):
        return None
    now = datetime.now(timezone.utc)
    query = {
        "blocked_until": {"$gt": now},
        "$or": [],
    }
    if user_id:
        query["$or"].append({"user_id": user_id})
    if ip_address:
        query["$or"].append({"ip_address": ip_address})
    if not query["$or"]:
        return None
    return await db.security_blocks.find_one(query, {"_id": 0})


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_active_admin_risk_profile(user_id: str) -> Optional[Dict[str, Any]]:
    profile = await db.progressive_risk_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        return None

    if profile.get("manual_override") == "allow_admin":
        return None

    level = str(profile.get("risk_level") or "low").lower()
    if level not in {"high", "critical"}:
        return None

    updated_at = _parse_iso_datetime(profile.get("updated_at") or profile.get("assessed_at"))
    if not updated_at:
        return None
    if datetime.now(timezone.utc) - updated_at > timedelta(hours=24):
        return None

    return profile


async def apply_security_block(
    user_id: Optional[str],
    ip_address: Optional[str],
    reason: str,
    risk_level: str = "high",
    duration_minutes: int = 30,
):
    # Never block internal Kubernetes/ingress proxy IPs
    if ip_address and (ip_address.startswith("10.") or ip_address.startswith("172.") or ip_address in ("127.0.0.1", "::1", "localhost")):
        return
    blocked_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    await db.security_blocks.insert_one(
        {
            "block_id": f"block_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "ip_address": ip_address,
            "reason": reason,
            "risk_level": risk_level,
            "blocked_until": blocked_until,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def require_recent_admin_session(request: Request, max_age_minutes: int = 10) -> User:
    user = await require_admin(request)
    session_token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header[7:]
    if not session_token:
        session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Re-authentication required")
    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Re-authentication required")
    issued_at = session.get("issued_at")
    if issued_at and issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    if not issued_at or datetime.now(timezone.utc) - issued_at > timedelta(minutes=max_age_minutes):
        await log_security_event(user.user_id, "admin_reauth_required", "medium", request)
        raise HTTPException(status_code=401, detail="Re-authentication required")
    return user


async def get_current_user(request: Request) -> Optional[User]:
    """Get current user from Authorization header or HttpOnly session cookie."""
    session_token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header[7:]
    if not session_token:
        session_token = request.cookies.get("session_token")
    if not session_token:
        return None

    ip_address = request.client.host if request.client else None
    if await is_security_blocked(None, ip_address):
        await log_security_event(None, "blocked_ip", "high", request)
        return None

    try:
        payload = jwt.decode(session_token, JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        await log_security_event(None, "jwt_invalid", "high", request)
        return None

    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        await log_security_event(payload.get("user_id"), "invalid_session", "medium", request)
        return None

    expires_at = session.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= datetime.now(timezone.utc):
        await db.user_sessions.delete_one({"session_token": session_token})
        return None

    user_doc = await db.users.find_one({"user_id": session.get("user_id")}, {"_id": 0})
    if not user_doc:
        return None

    if request.url.path.startswith("/api/admin") and not user_doc.get("is_admin"):
        needed = required_employee_permission(request.url.path)
        granted = set(build_employee_permissions(user_doc))
        if needed and needed in granted:
            user_doc["is_admin"] = True
            user_doc["delegated_admin"] = True
            user_doc["role"] = "admin"
            role_list = set(user_doc.get("roles") or [])
            role_list.add("admin")
            user_doc["roles"] = sorted(role_list)

    if payload.get("token_version", 0) != user_doc.get("token_version", 0):
        await log_security_event(user_doc.get("user_id"), "token_version_mismatch", "high", request)
        return None

    if await is_security_blocked(user_doc.get("user_id"), ip_address):
        await log_security_event(user_doc.get("user_id"), "blocked_user", "high", request)
        return None

    user = User(**user_doc)
    if user.delegated_admin:
        return user
    return await apply_access_overrides(user)


async def require_auth(request: Request) -> User:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(request: Request) -> User:
    user = await require_auth(request)
    if resolve_user_role(user) != "admin":
        await log_security_event(user.user_id, "admin_access_denied", "high", request)
        raise HTTPException(status_code=403, detail="Admin access required")

    active_risk = await _get_active_admin_risk_profile(user.user_id)
    if active_risk:
        bypassed = await _apply_preview_risk_bypass_if_allowed(
            user=user,
            request=request,
            active_risk=active_risk,
            bypass_scope="require_admin",
        )
        if bypassed:
            active_risk = None

    if active_risk:
        level = str(active_risk.get("risk_level") or "high").lower()
        session_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
        if not session_token:
            session_token = request.cookies.get("session_token")
        if level == "critical" and session_token:
            await db.user_sessions.delete_one({"session_token": session_token})

        await log_security_event(
            user.user_id,
            "risk_engine_admin_blocked",
            "critical" if level == "critical" else "high",
            request,
            {
                "risk_score": int(active_risk.get("risk_score") or 0),
                "risk_level": level,
                "trigger": active_risk.get("trigger"),
                "session_protection": active_risk.get("session_protection"),
            },
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message": "Admin access blocked by the Progressive Risk Engine.",
                "code": "risk_engine_admin_api_blocked" if level == "high" else "risk_engine_id_verification_required",
                "session_locked": level == "critical",
                "risk_engine": {
                    "risk_level": level,
                    "risk_score": int(active_risk.get("risk_score") or 0),
                    "trigger": active_risk.get("trigger"),
                    "session_protection": active_risk.get("session_protection"),
                    "output_block": active_risk.get("output_block"),
                },
            },
        )

    ip_address = request.client.host if request.client else "unknown"
    internal_route_health_probe = (
        request.headers.get("x-route-health-probe") == "internal"
        and ip_address in {"127.0.0.1", "::1", "localhost"}
    )
    if not internal_route_health_probe and not check_rate_limit(f"admin:{user.user_id}:{ip_address}", 200, 60):
        await log_security_event(user.user_id, "admin_rate_limit", "medium", request)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"log_{uuid.uuid4().hex[:10]}",
            "user_id": user.user_id,
            "action": "admin_access",
            "metadata": {
                "ip": ip_address,
                "user_agent": request.headers.get("user-agent"),
                "path": request.url.path,
                "method": request.method,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return user
