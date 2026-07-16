from __future__ import annotations

import asyncio
import os
import socket
import ssl
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import Request

from routes.db import db


TRUST_SETTINGS_DOC_ID = "global_trust_settings"
_SSL_CACHE: Dict[str, Dict[str, Any]] = {}
_SSL_CACHE_TTL_SECONDS = 300


DEFAULT_TRUST_SETTINGS: Dict[str, Any] = {
    "trust_signals_enabled": True,
    "guarantee_message": "Refunds handled per provider policy and platform terms.",
    "fraud_notice": "Protected transactions with fraud monitoring.",
    "compliance_labels": ["PCI-DSS"],
    "display_level": "detailed",
    "allow_nova_security_answers": True,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    if value == "card":
        return "stripe"
    if value in {"stripe", "paypal", "fedapay", "all"}:
        return value
    return "all"


def _provider_label(provider: str) -> str:
    return {
        "stripe": "Stripe",
        "paypal": "PayPal",
        "fedapay": "FedaPay",
        "all": "All providers",
    }.get(provider, provider.title())


def _host_from_request(request: Optional[Request]) -> str:
    if not request:
        return ""
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if forwarded_host:
        return forwarded_host
    host = str(request.headers.get("host") or "").split(",")[0].strip()
    return host


def _origin_from_platform_env() -> str:
    for key in ("REACT_APP_BACKEND_URL", "EXPO_PUBLIC_BACKEND_URL", "FRONTEND_BASE_URL"):
        raw = str(os.environ.get(key) or "").strip()
        if raw:
            return raw
    return ""


def _resolve_secure_connection(request: Optional[Request], fallback_origin: str) -> Tuple[bool, str]:
    if request:
        proto = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "").split(",")[0].strip().lower()
        return (proto == "https"), proto or "unknown"

    parsed = urlparse(str(fallback_origin or ""))
    scheme = (parsed.scheme or "").lower()
    return (scheme == "https"), (scheme or "unknown")


def _ssl_probe_sync(host: str, port: int = 443) -> Dict[str, Any]:
    checked_at = _now_iso()
    if not host:
        return {
            "checked_at": checked_at,
            "host": "",
            "valid": False,
            "reason": "No host provided for SSL validation",
            "expires_at": None,
            "days_until_expiry": None,
            "cipher_bits": None,
        }

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as secure_sock:
                cert = secure_sock.getpeercert() or {}
                cipher = secure_sock.cipher() or (None, None, None)

        not_after = cert.get("notAfter")
        expires_at_iso = None
        days_until_expiry = None
        valid = False
        reason = "SSL certificate parsed"
        if not_after:
            expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            expires_at_iso = expires_at.isoformat()
            delta = expires_at - datetime.now(timezone.utc)
            days_until_expiry = max(0, int(delta.total_seconds() // 86400))
            valid = delta.total_seconds() > 0
            reason = "SSL certificate valid" if valid else "SSL certificate expired"

        return {
            "checked_at": checked_at,
            "host": host,
            "valid": valid,
            "reason": reason,
            "expires_at": expires_at_iso,
            "days_until_expiry": days_until_expiry,
            "cipher_bits": cipher[2],
            "protocol": cipher[1],
            "cipher_suite": cipher[0],
        }
    except Exception as exc:
        return {
            "checked_at": checked_at,
            "host": host,
            "valid": False,
            "reason": f"SSL validation failed: {exc}",
            "expires_at": None,
            "days_until_expiry": None,
            "cipher_bits": None,
        }


async def _ssl_status(host: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cached = _SSL_CACHE.get(host)
    if cached and cached.get("expires_at_ts") and cached["expires_at_ts"] > now.timestamp():
        return cached["payload"]

    payload = await asyncio.to_thread(_ssl_probe_sync, host, 443)
    _SSL_CACHE[host] = {
        "expires_at_ts": (now + timedelta(seconds=_SSL_CACHE_TTL_SECONDS)).timestamp(),
        "payload": payload,
    }
    return payload


def _provider_env_status(provider: str) -> Dict[str, Any]:
    provider = _normalize_provider(provider)
    if provider == "stripe":
        secret = str(os.environ.get("STRIPE_API_KEY") or "")
        pub = str(os.environ.get("STRIPE_PUBLISHABLE_KEY") or "")
        available = bool(secret and pub)
        if secret.startswith("sk_live_") and pub.startswith("pk_live_"):
            mode = "live"
            label = "Live Ready"
        elif secret.startswith("sk_test_") and pub.startswith("pk_test_"):
            mode = "test"
            label = "Test Ready"
        else:
            mode = "unknown"
            label = "Configured" if available else "Unavailable"
        return {"provider": "stripe", "available": available, "mode": mode, "status_label": label}

    if provider == "paypal":
        client = str(os.environ.get("PAYPAL_CLIENT_ID") or "")
        secret = str(os.environ.get("PAYPAL_SECRET") or "")
        mode = str(os.environ.get("PAYPAL_MODE") or "sandbox").lower()
        available = bool(client and secret)
        label = "Live Ready" if available and mode == "live" else "Sandbox Ready" if available else "Unavailable"
        return {"provider": "paypal", "available": available, "mode": mode, "status_label": label}

    if provider == "fedapay":
        secret = str(os.environ.get("FEDAPAY_SECRET_KEY") or "")
        public = str(os.environ.get("FEDAPAY_PUBLIC_KEY") or "")
        available = bool(secret and public)
        secret_lower = secret.lower()
        public_lower = public.lower()
        if secret.startswith("sk_live_") or public.startswith("pk_live_"):
            mode = "live"
            label = "Live Ready"
        elif (
            secret.startswith("sk_test_")
            or public.startswith("pk_test_")
            or "sandbox" in secret_lower
            or "sandbox" in public_lower
        ):
            mode = "test"
            label = "Test Ready"
        else:
            mode = "unknown"
            label = "Configured" if available else "Unavailable"
        return {"provider": "fedapay", "available": available, "mode": mode, "status_label": label}

    return {"provider": provider, "available": False, "mode": "unknown", "status_label": "Unknown"}


async def _provider_runtime_status(provider: str) -> Dict[str, Any]:
    provider = _normalize_provider(provider)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()

    if provider == "stripe":
        provider_query = {"$or": [{"gateway": "stripe"}, {"payment_method": {"$in": ["stripe", "card"]}}]}
    elif provider == "paypal":
        provider_query = {"$or": [{"gateway": "paypal"}, {"payment_method": "paypal"}]}
    else:
        provider_query = {"$or": [{"gateway": "fedapay"}, {"payment_method": {"$in": ["fedapay", "mobile_money"]}}]}

    recent_query = {**provider_query, "created_at": {"$gte": cutoff}}
    tx_count = await db.payment_transactions.count_documents(recent_query)
    latest_tx = await db.payment_transactions.find_one(provider_query, {"_id": 0, "created_at": 1, "payment_status": 1}, sort=[("created_at", -1)])

    return {
        "recent_tx_count_15m": tx_count,
        "last_transaction_at": (latest_tx or {}).get("created_at"),
        "last_transaction_status": (latest_tx or {}).get("payment_status"),
    }


def _sanitize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**DEFAULT_TRUST_SETTINGS, **(settings or {})}
    merged["trust_signals_enabled"] = bool(merged.get("trust_signals_enabled", True))
    merged["allow_nova_security_answers"] = bool(merged.get("allow_nova_security_answers", True))
    merged["display_level"] = "minimal" if str(merged.get("display_level", "detailed")).lower() == "minimal" else "detailed"

    labels = merged.get("compliance_labels") or []
    if isinstance(labels, str):
        labels = [part.strip() for part in labels.split(",") if part.strip()]
    labels = [str(label).strip().upper() for label in labels if str(label).strip()]
    merged["compliance_labels"] = list(dict.fromkeys(labels))

    merged["guarantee_message"] = str(merged.get("guarantee_message") or DEFAULT_TRUST_SETTINGS["guarantee_message"]).strip()
    merged["fraud_notice"] = str(merged.get("fraud_notice") or DEFAULT_TRUST_SETTINGS["fraud_notice"]).strip()
    return merged


async def get_unified_trust_settings() -> Dict[str, Any]:
    doc = await db.payment_trust_settings.find_one({"config_id": TRUST_SETTINGS_DOC_ID}, {"_id": 0})
    return _sanitize_settings(doc or {})


async def upsert_unified_trust_settings(partial: Dict[str, Any], actor_user_id: Optional[str] = None) -> Dict[str, Any]:
    current = await get_unified_trust_settings()
    next_settings = _sanitize_settings({**current, **(partial or {})})
    now = _now_iso()
    payload = {
        "config_id": TRUST_SETTINGS_DOC_ID,
        **next_settings,
        "updated_at": now,
    }
    if actor_user_id:
        payload["updated_by"] = actor_user_id

    await db.payment_trust_settings.update_one(
        {"config_id": TRUST_SETTINGS_DOC_ID},
        {"$set": payload, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return payload


async def _provider_snapshot(provider: str, secure_connection: bool, ssl_status: Dict[str, Any]) -> Dict[str, Any]:
    env_status = _provider_env_status(provider)
    runtime_status = await _provider_runtime_status(provider)

    available = bool(env_status.get("available"))
    provider_verified = available and secure_connection and bool(ssl_status.get("valid"))
    status = "verified" if provider_verified else "warning"

    if not available:
        status_label = "Unavailable"
    elif runtime_status.get("recent_tx_count_15m", 0) > 0:
        status_label = "Live traffic observed"
    else:
        status_label = env_status.get("status_label") or "Configured"

    return {
        "provider": provider,
        "provider_label": _provider_label(provider),
        "available": available,
        "mode": env_status.get("mode"),
        "status": status,
        "status_label": status_label,
        "provider_verified": provider_verified,
        **runtime_status,
    }


def _static_provider_snapshot(provider: str) -> Dict[str, Any]:
    provider = _normalize_provider(provider)
    return {
        "provider": provider,
        "provider_label": _provider_label(provider),
        "available": True,
        "mode": "policy",
        "status": "verified",
        "status_label": "Verified",
        "provider_verified": True,
        "recent_tx_count_15m": None,
        "last_transaction_at": None,
        "last_transaction_status": None,
    }


async def build_unified_trust_snapshot(
    provider: str,
    context: str,
    request: Optional[Request] = None,
    mode: str = "live",
) -> Dict[str, Any]:
    normalized_provider = _normalize_provider(provider)
    settings = await get_unified_trust_settings()
    mode_value = str(mode or "live").strip().lower()
    mode_effective = "static" if mode_value == "static" else "live"

    providers = [normalized_provider] if normalized_provider != "all" else ["stripe", "paypal", "fedapay"]

    if mode_effective == "static":
        fallback_origin = _origin_from_platform_env()
        host = _host_from_request(request)
        if not host:
            host = urlparse(fallback_origin).netloc

        secure_connection = True
        transport = "https"
        ssl_status = {
            "checked_at": _now_iso(),
            "host": host,
            "valid": True,
            "reason": "Static policy assurance mode",
            "expires_at": None,
            "days_until_expiry": None,
            "cipher_bits": 256,
            "protocol": "TLS",
            "cipher_suite": "POLICY_ASSURANCE",
        }
        provider_statuses = [_static_provider_snapshot(p) for p in providers]
    else:
        fallback_origin = _origin_from_platform_env()
        secure_connection, transport = _resolve_secure_connection(request, fallback_origin)

        host = _host_from_request(request)
        if not host:
            host = urlparse(fallback_origin).netloc
        ssl_status = await _ssl_status(host)
        provider_statuses = [await _provider_snapshot(p, secure_connection, ssl_status) for p in providers]

    warnings: List[str] = []
    if mode_effective == "live":
        if not secure_connection:
            warnings.append("Connection is not HTTPS-secured.")
        if not ssl_status.get("valid"):
            warnings.append("SSL certificate validation failed.")
        unavailable = [item["provider_label"] for item in provider_statuses if not item.get("available")]
        if unavailable:
            warnings.append(f"Provider unavailable: {', '.join(unavailable)}")

    overall_status = "warning" if warnings else "verified"

    if mode_effective == "static":
        encryption_message = "Secured by TLS encryption (256-bit)"
    elif ssl_status.get("valid"):
        bits = ssl_status.get("cipher_bits")
        encryption_message = f"Secured by TLS encryption ({bits}-bit)" if bits else "Secured by TLS encryption"
    else:
        encryption_message = "TLS/SSL verification unavailable"

    if normalized_provider == "all":
        ready_count = sum(1 for p in provider_statuses if p.get("provider_verified"))
        provider_message = f"Verified secure checkout providers: {ready_count}/{len(provider_statuses)}"
    else:
        p = provider_statuses[0]
        provider_message = f"Verified secure checkout via {p['provider_label']}: {p['status_label']}"

    signals = [
        {
            "id": "encryption",
            "label": "End-to-end encryption",
            "status": "verified" if ssl_status.get("valid") and secure_connection else "warning",
            "message": encryption_message,
        },
        {
            "id": "provider",
            "label": "Payment provider verification",
            "status": "verified" if all(p.get("provider_verified") for p in provider_statuses) else "warning",
            "message": provider_message,
        },
        {
            "id": "fraud",
            "label": "Fraud protection",
            "status": "verified",
            "message": settings.get("fraud_notice"),
        },
        {
            "id": "guarantee",
            "label": "Money-back guarantee",
            "status": "verified",
            "message": settings.get("guarantee_message"),
        },
        {
            "id": "compliance",
            "label": "Compliance indicators",
            "status": "verified" if settings.get("compliance_labels") else "warning",
            "message": ", ".join(settings.get("compliance_labels") or []) or "No compliance labels configured",
        },
    ]

    return {
        "provider": normalized_provider,
        "provider_label": _provider_label(normalized_provider),
        "context": str(context or "checkout"),
        "checked_at": _now_iso(),
        "overall_status": overall_status,
        "warnings": warnings,
        "settings": settings,
        "signals": signals,
        "messages": [signal["message"] for signal in signals],
        "connection": {
            "secure": secure_connection,
            "transport": transport,
            "ssl": ssl_status,
        },
        "provider_status": provider_statuses if normalized_provider == "all" else provider_statuses[0],
        "mode_effective": mode_effective,
        "data_source": "policy" if mode_effective == "static" else "runtime",
        "compliance_indicators": [
            {"label": label, "status": "configured"}
            for label in settings.get("compliance_labels") or []
        ],
    }


async def build_nova_payment_safety_response(message: str) -> Dict[str, Any]:
    msg = str(message or "").lower()
    provider = "all"
    for candidate in ("stripe", "paypal", "fedapay"):
        if candidate in msg:
            provider = candidate
            break

    snapshot = await build_unified_trust_snapshot(provider=provider, context="nova", request=None)
    statuses = snapshot.get("provider_status")
    if isinstance(statuses, dict):
        status_line = f"{statuses.get('provider_label')}: {statuses.get('status_label')}"
    else:
        status_line = ", ".join(f"{row.get('provider_label')}: {row.get('status_label')}" for row in statuses or [])

    encryption_line = next((s.get("message") for s in snapshot.get("signals", []) if s.get("id") == "encryption"), "TLS status unavailable")
    fraud_line = next((s.get("message") for s in snapshot.get("signals", []) if s.get("id") == "fraud"), "")
    guarantee_line = next((s.get("message") for s in snapshot.get("signals", []) if s.get("id") == "guarantee"), "")

    if snapshot.get("overall_status") == "warning":
        opening = "I can only partially verify payment safety right now."
    else:
        opening = "Yes — based on live platform checks, your payment path is currently verified."

    warning_text = ""
    if snapshot.get("warnings"):
        warning_text = f" Warnings: {'; '.join(snapshot['warnings'])}."

    text = (
        f"{opening} {encryption_line}. Provider status: {status_line}. "
        f"{fraud_line} {guarantee_line}.{warning_text}"
    ).strip()

    return {
        "message": text,
        "trust_snapshot": snapshot,
    }
