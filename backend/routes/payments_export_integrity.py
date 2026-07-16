"""Payment export integrity helpers extracted from payments routes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import uuid
from urllib.parse import urlencode

from .payments_catalog import get_plan_name

PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS = {
    "theme_profile": "enterprise",
    "signature_enabled": True,
    "signature_label": "RealAICoach Integrity Signature",
}


def format_payment_date_label(created, with_time: bool = False) -> str:
    date_format = "%b %d, %Y %I:%M %p" if with_time else "%b %d, %Y"
    fallback_len = 16 if with_time else 10
    if isinstance(created, datetime):
        return created.strftime(date_format)
    try:
        return datetime.fromisoformat(str(created).replace("Z", "+00:00")).strftime(date_format)
    except Exception:
        return str(created)[:fallback_len]


def resolve_plan_name(plan_id: str) -> str:
    return str(plan_id or "").title()


async def resolve_plan_name_from_gps(plan_id: str) -> str:
    return await get_plan_name(plan_id)


def parse_created_at(created_at) -> datetime | None:
    if isinstance(created_at, datetime):
        dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def normalize_export_theme(theme_profile: str | None) -> str:
    theme = (theme_profile or "enterprise").strip().lower()
    if theme in {"enterprise", "finance", "minimal"}:
        return theme
    return "enterprise"


def export_theme_palette(theme_profile: str | None) -> dict:
    theme = normalize_export_theme(theme_profile)
    palettes = {
        "enterprise": {
            "hero_bg": "#2563EB",
            "hero_border": "#1E40AF",
            "hero_text": "#BFDBFE",
            "table_header": "#2563EB",
            "table_grid": "#D7E3F8",
            "surface": "#F8FAFC",
            "surface_border": "#DBEAFE",
        },
        "finance": {
            "hero_bg": "#065F46",
            "hero_border": "#064E3B",
            "hero_text": "#D1FAE5",
            "table_header": "#047857",
            "table_grid": "#BBF7D0",
            "surface": "#F0FDF4",
            "surface_border": "#BBF7D0",
        },
        "minimal": {
            "hero_bg": "#334155",
            "hero_border": "#1E293B",
            "hero_text": "#E2E8F0",
            "table_header": "#334155",
            "table_grid": "#E2E8F0",
            "surface": "#F8FAFC",
            "surface_border": "#E2E8F0",
        },
    }
    return palettes[theme]


def compute_report_hash(csv_text: str) -> str:
    return hashlib.sha256((csv_text or "").encode("utf-8")).hexdigest()


def build_integrity_payload(report_id: str, generated_at: str, row_count: int, total_spent: float, data_hash: str) -> str:
    payload = {
        "report_id": report_id,
        "generated_at": generated_at,
        "row_count": int(row_count),
        "total_spent": round(float(total_spent), 2),
        "data_hash": data_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_integrity_payload(payload: str) -> str:
    secret = os.environ.get("PAYMENT_EXPORT_SIGNATURE_SECRET") or os.environ.get("JWT_SECRET") or ""
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_integrity_meta(csv_text: str, row_count: int, total_spent: float, signature_enabled: bool = True) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    report_id = f"PH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    data_hash = compute_report_hash(csv_text)
    payload = build_integrity_payload(report_id, generated_at, row_count, total_spent, data_hash)
    signature = sign_integrity_payload(payload) if signature_enabled else ""
    return {
        "report_id": report_id,
        "generated_at": generated_at,
        "row_count": int(row_count),
        "total_spent": round(float(total_spent), 2),
        "data_hash": data_hash,
        "signature": signature,
    }


def build_admin_verifier_prefill_url(base_frontend_url: str, integrity: dict) -> str:
    base = (base_frontend_url or "").rstrip("/")
    query = urlencode(
        {
            "section": "payment-billing",
            "verify_report_id": integrity.get("report_id", ""),
            "verify_generated_at": integrity.get("generated_at", ""),
            "verify_row_count": integrity.get("row_count", 0),
            "verify_total_spent": integrity.get("total_spent", 0),
            "verify_data_hash": integrity.get("data_hash", ""),
            "verify_signature": integrity.get("signature", ""),
        }
    )
    if base:
        return f"{base}/executive-dashboard?{query}"
    return f"/executive-dashboard?{query}"