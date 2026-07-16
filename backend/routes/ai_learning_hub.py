"""AI Learning Hub — AI-generated educational content on any topic.

Generate courses, lessons, quizzes on demand. Track progress per user.

API:
- GET  /api/ai-learn/catalog              — Browse available topics/courses
- POST /api/ai-learn/generate-lesson      — Generate a lesson on a topic
- GET  /api/ai-learn/my-lessons           — User's completed/saved lessons
- GET  /api/ai-learn/lessons/{id}         — Get a specific lesson
- POST /api/ai-learn/lessons/{id}/quiz    — Generate a quiz for a lesson
- POST /api/ai-learn/lessons/{id}/complete — Mark lesson as completed
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from datetime import date, datetime, timezone, timedelta
from functools import lru_cache
from typing import Optional, Any, Dict, List
import uuid
import logging
import os
import json
import io
import csv
import base64
import hashlib
import html
import asyncio
import subprocess
import tempfile
import shutil
import re
import zipfile
from urllib.parse import quote
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import requests

from routes.learning_hub_seed_catalog import build_seed_catalog

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.notification_engine import emit_notification
from utils.access_control_engine import compute_effective_plan
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.object_storage_service import (
    APP_PREFIX as STORAGE_APP_PREFIX,
    get_bytes as storage_get_bytes,
    put_bytes as storage_put_bytes,
    put_json as storage_put_json,
    storage_enabled as storage_is_enabled,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-learn")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
ANCHOR_MODE = "opentimestamps"
ANCHOR_CHAIN_TARGET = "bitcoin-opentimestamps"
ANCHOR_BATCH_INTERVAL_HOURS = 1
DEFAULT_VIDEO_PROVIDER = "YouTube"
CERTIFICATE_ISSUER_NAME = "RealAICoach AI Learning Hub"
CERTIFICATE_SIGNER_NAME = "Adjimon Kouatonou"
CERTIFICATE_SIGNER_ROLE = "Chief Executive Officer (CEO)"
CERTIFICATE_CREDENTIAL_LABEL = "RealAICoach Certificate of Completion"
CERTIFICATE_TEMPLATE_VERSION = "rac-enterprise-certificate-v27"
CERTIFICATE_TEMPLATE_DOC_ID = "default-certificate-template"
CERTIFICATE_RENDER_PROFILE_VERSION = "rac-cert-render-v6-learning-certificate-v15-exempt"
CERTIFICATE_ASSET_VERSION = CERTIFICATE_RENDER_PROFILE_VERSION
CERTIFICATE_ANALYTICS_CACHE_TTL_SECONDS = 30
_CERTIFICATE_ANALYTICS_CACHE: Dict[str, Dict[str, Any]] = {}
AI_JSON_TIMEOUT_SECONDS = 12
CERTIFICATE_BRAND_PRIMARY = "#111827"
CERTIFICATE_BRAND_TEAL = "#24C8C8"
CERTIFICATE_BRAND_MUTED = "#4B5563"
CERTIFICATE_BRAND_BORDER = "#D9E4EC"
CERTIFICATE_STATUS_VALID = "valid"
CERTIFICATE_STATUS_EXPIRED = "expired"
CERTIFICATE_STATUS_REVOKED = "revoked"
CERTIFICATE_STATUS_INVALID = "invalid"
CERTIFICATE_BRAND_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "branding",
    "realaicoach-logo.png",
)
CERTIFICATE_CERTIFIED_STAMP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "branding",
    "certified-stamp.png",
)
CERTIFICATE_HANDWRITTEN_SIGNATURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "branding",
    "adjimon-signature-handwritten.png",
)


LEARNING_CERTIFICATE_PDF_V15_THEME_EXEMPTION = "learning-certificate-theme-exempt-only"


def _return_learning_certificate_pdf_bytes(payload: bytes, context: str) -> bytes:
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"Certificate PDF generation failed: {context}")
    return payload
LEGACY_CERTIFICATE_SIGNER_ROLES = {
    "",
    "RealAICoach",
    "RealAICoach AI Learning Hub",
    "Managing Director of Training & Certification at RealAICoach",
}
CERTIFICATE_TEMPLATE_DEFAULTS: Dict[str, float] = {
    "stamp_offset_x_mm": 0.0,
    "stamp_y_mm": 17.0,
    "stamp_size_mm": 40.0,
    "footer_logo_x_mm": 28.0,
    "footer_logo_y_mm": 24.0,
    "footer_logo_w_mm": 44.0,
    "footer_logo_h_mm": 24.0,
    "signature_line_width_mm": 72.0,
    "signature_right_margin_mm": 28.0,
    "signature_y_mm": 31.0,
    "signature_image_offset_x_mm": 0.0,
    "signature_image_offset_y_mm": -1.0,
    "signature_image_width_mm": 80.0,
    "signature_image_height_mm": 34.0,
}
CERTIFICATE_TYPOGRAPHY_PRESET_DEFAULT = "executive"
CERTIFICATE_TYPOGRAPHY_PRESETS: Dict[str, Dict[str, Any]] = {
    "classic": {
        "label": "Classic",
        "name_font": "Helvetica",
        "name_size": 9.5,
        "name_color": "ink",
        "role_font": "Helvetica",
        "role_size": 9.2,
        "role_color": "muted",
    },
    "executive": {
        "label": "Executive",
        "name_font": "Helvetica-Bold",
        "name_size": 10.0,
        "name_color": "ink",
        "role_font": "Helvetica-Bold",
        "role_size": 10.0,
        "role_color": "ink",
    },
    "premium": {
        "label": "Premium",
        "name_font": "Helvetica-Bold",
        "name_size": 11.0,
        "name_color": "ink",
        "role_font": "Helvetica-Bold",
        "role_size": 10.8,
        "role_color": "ink",
    },
}
CERTIFICATE_SIGNATURE_PROFILE_VERSION = "ceo-signature-size-up-v2"
CERTIFICATE_SIGNATURE_PROFILE_OVERRIDES: Dict[str, float] = {
    "signature_image_offset_x_mm": 0.0,
    "signature_image_offset_y_mm": -0.5,
    "signature_image_width_mm": 80.0,
    "signature_image_height_mm": 34.0,
}
CERTIFICATE_FOOTER_PROFILE_VERSION = "footer-logo-yellow-align-v1"
CERTIFICATE_FOOTER_PROFILE_OVERRIDES: Dict[str, float] = {
    "footer_logo_x_mm": 24.5,
    "stamp_offset_x_mm": -9.43,
}

VIDEO_FALLBACK_LIBRARY = [
    {
        "title": "Strategic AI Roadmapping",
        "url": "https://www.youtube.com/watch?v=aircAruvnKk",
        "duration_min": 18,
    },
    {
        "title": "LLM Prompting for Production",
        "url": "https://www.youtube.com/watch?v=JTxsNm9IdYU",
        "duration_min": 22,
    },
    {
        "title": "AI Systems Thinking",
        "url": "https://www.youtube.com/watch?v=2ePf9rue1Ao",
        "duration_min": 21,
    },
    {
        "title": "Data-Driven Experimentation",
        "url": "https://www.youtube.com/watch?v=8hly31xKli0",
        "duration_min": 17,
    },
    {
        "title": "Execution Loops for Career Growth",
        "url": "https://www.youtube.com/watch?v=rfscVS0vtbw",
        "duration_min": 24,
    },
    {
        "title": "AI Product Metrics Essentials",
        "url": "https://www.youtube.com/watch?v=YQHsXMglC9A",
        "duration_min": 19,
    },
    {
        "title": "Portfolio-to-Income Blueprint",
        "url": "https://www.youtube.com/watch?v=HfACrKJ_Y2w",
        "duration_min": 20,
    },
]

WEEKLY_AUTOPUBLISH_TOPICS = [
    "AI Incident Response Automation",
    "Revenue Intelligence with LLM Workflows",
    "Enterprise Prompt Security Engineering",
    "AI Career Acceleration for Technical Leaders",
    "Data Productization for Income Growth",
    "No-Code AI Automation Systems",
    "AI Sales Enablement and Conversion Loops",
    "Operational AI Governance",
    "AI Productivity Sprints for Teams",
    "Generative AI Portfolio Monetization",
]

PLAN_DAILY_LIMITS = {
    "free": {
        "auto_generate_course": 2,
        "roadmap": 1,
        "sandbox": 2,
        "mentor_match": 1,
        "certificate_issue": 0,
    },
    "basic": {
        "auto_generate_course": 20,
        "roadmap": 10,
        "sandbox": 50,
        "mentor_match": 12,
        "certificate_issue": 20,
    },
    "premium": {
        "auto_generate_course": -1,
        "roadmap": -1,
        "sandbox": -1,
        "mentor_match": -1,
        "certificate_issue": -1,
    },
}

PLAN_ACCESS_POLICY = {
    "free": {
        "scope_label": "Limited access",
        "catalog_limit": 12,
        "max_active_enrollments": 2,
        "max_total_enrollments": 4,
    },
    "basic": {
        "scope_label": "Almost unlimited",
        "catalog_limit": 80,
        "max_active_enrollments": 25,
        "max_total_enrollments": 50,
    },
    "premium": {
        "scope_label": "Full unlimited",
        "catalog_limit": -1,
        "max_active_enrollments": -1,
        "max_total_enrollments": -1,
    },
}

VIDEO_TOPIC_MATCH_THRESHOLD = 0.34
VIDEO_TOPIC_TOKEN_BLACKLIST = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "your",
    "that",
    "this",
    "about",
    "learn",
    "learning",
    "guide",
    "intro",
    "session",
    "course",
    "video",
    "lesson",
    "practical",
    "real",
    "world",
    "overview",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=8)
def _image_visible_bounds_ratios(image_path: str) -> tuple[float, float, float, float]:
    try:
        from PIL import Image, ImageChops

        with Image.open(image_path).convert("RGB") as image:
            diff = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L")
            bbox = diff.point(lambda value: 255 if value > 10 else 0).getbbox()
            width, height = image.size
            if not bbox or width <= 0 or height <= 0:
                return 0.0, 0.0, 1.0, 1.0
            left, top, right, bottom = bbox
            return left / width, top / height, right / width, bottom / height
    except Exception:
        return 0.0, 0.0, 1.0, 1.0


@lru_cache(maxsize=8)
def _image_visible_center_ratio_x(image_path: str) -> float:
    left, _, right, _ = _image_visible_bounds_ratios(image_path)
    return (left + right) / 2


@lru_cache(maxsize=8)
def _fit_image_within_box(image_path: str, max_width: float, max_height: float) -> tuple[float, float]:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            return max_width, max_height
        scale = min(max_width / source_width, max_height / source_height)
        return source_width * scale, source_height * scale
    except Exception:
        return max_width, max_height


_CROPPED_SIGNATURE_CACHE: Dict[str, Any] = {}


def _get_cropped_signature_image() -> Optional[tuple[Any, float]]:
    """Signature asset ink-cropped (removes ~58% white padding), white converted to alpha. Returns (ImageReader, aspect)."""
    cached = _CROPPED_SIGNATURE_CACHE.get("sig")
    if cached is not None:
        return cached
    try:
        from PIL import Image, ImageChops
        from reportlab.lib.utils import ImageReader

        with Image.open(CERTIFICATE_HANDWRITTEN_SIGNATURE_PATH) as raw:
            img = raw.convert("RGB")
        darkness = ImageChops.invert(img.convert("L"))
        import numpy as np
        mask = np.array(darkness) > 30
        rows = np.where(mask.sum(axis=1) >= 6)[0]
        cols = np.where(mask.sum(axis=0) >= 6)[0]
        bbox = (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1) if len(rows) and len(cols) else None
        if bbox:
            pad = 10
            bbox = (
                max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad),
            )
            img = img.crop(bbox)
            darkness = darkness.crop(bbox)
        alpha = darkness.point(lambda v: min(255, int(v * 2.2)))
        rgba = img.convert("RGBA")
        rgba.putalpha(alpha)
        aspect = rgba.width / max(1, rgba.height)
        result = (ImageReader(rgba), aspect)
        _CROPPED_SIGNATURE_CACHE["sig"] = result
        return result
    except Exception:
        return None


def _draw_cropped_signature(pdf: Any, *, center_x: float, baseline_y: float, box_w: float, box_h: float, mm: float) -> bool:
    cropped = _get_cropped_signature_image()
    if not cropped:
        return False
    sig_img, aspect = cropped
    sig_h = box_h * 0.88
    sig_w = sig_h * aspect
    if sig_w > box_w:
        sig_w = box_w
        sig_h = sig_w / aspect
    try:
        pdf.drawImage(sig_img, center_x - (sig_w / 2), baseline_y + (1.0 * mm), width=sig_w, height=sig_h, mask="auto")
        return True
    except Exception:
        return False


def _sanitize_certificate_template_settings(payload: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    source = payload or {}
    bounds: Dict[str, tuple[float, float]] = {
        "stamp_offset_x_mm": (-40.0, 40.0),
        "stamp_y_mm": (8.0, 40.0),
        "stamp_size_mm": (18.0, 70.0),
        "footer_logo_x_mm": (8.0, 60.0),
        "footer_logo_y_mm": (12.0, 40.0),
        "footer_logo_w_mm": (20.0, 70.0),
        "footer_logo_h_mm": (12.0, 42.0),
        "signature_line_width_mm": (40.0, 100.0),
        "signature_right_margin_mm": (8.0, 50.0),
        "signature_y_mm": (16.0, 44.0),
        "signature_image_offset_x_mm": (-8.0, 16.0),
        "signature_image_offset_y_mm": (-4.0, 18.0),
        "signature_image_width_mm": (30.0, 90.0),
        "signature_image_height_mm": (12.0, 42.0),
    }
    normalized: Dict[str, float] = {}
    for key, default_value in CERTIFICATE_TEMPLATE_DEFAULTS.items():
        minimum, maximum = bounds[key]
        raw = source.get(key, default_value)
        try:
            value = float(raw)
        except Exception:
            value = float(default_value)
        normalized[key] = max(minimum, min(maximum, value))
    return normalized


def _sanitize_certificate_typography_preset(value: Optional[str]) -> str:
    preset = str(value or CERTIFICATE_TYPOGRAPHY_PRESET_DEFAULT).strip().lower()
    if preset not in CERTIFICATE_TYPOGRAPHY_PRESETS:
        return CERTIFICATE_TYPOGRAPHY_PRESET_DEFAULT
    return preset


def _certificate_typography_profile(preset: Optional[str]) -> Dict[str, Any]:
    normalized = _sanitize_certificate_typography_preset(preset)
    profile = CERTIFICATE_TYPOGRAPHY_PRESETS.get(normalized) or CERTIFICATE_TYPOGRAPHY_PRESETS[CERTIFICATE_TYPOGRAPHY_PRESET_DEFAULT]
    return {
        "id": normalized,
        **profile,
    }


async def _get_certificate_template_settings() -> Dict[str, Any]:
    doc = await db.learn_hub_certificate_templates.find_one({"template_id": CERTIFICATE_TEMPLATE_DOC_ID}, {"_id": 0})
    source_settings = (doc or {}).get("settings") or doc or {}
    if (doc or {}).get("signature_profile_version") != CERTIFICATE_SIGNATURE_PROFILE_VERSION:
        source_settings = {
            **source_settings,
            **CERTIFICATE_SIGNATURE_PROFILE_OVERRIDES,
        }
    if (doc or {}).get("footer_profile_version") != CERTIFICATE_FOOTER_PROFILE_VERSION:
        source_settings = {
            **source_settings,
            **CERTIFICATE_FOOTER_PROFILE_OVERRIDES,
        }
    settings = _sanitize_certificate_template_settings(source_settings)
    typography_preset = _sanitize_certificate_typography_preset((doc or {}).get("typography_preset"))
    return {
        "template_id": CERTIFICATE_TEMPLATE_DOC_ID,
        "template_version": CERTIFICATE_TEMPLATE_VERSION,
        "signature_profile_version": CERTIFICATE_SIGNATURE_PROFILE_VERSION,
        "footer_profile_version": CERTIFICATE_FOOTER_PROFILE_VERSION,
        "typography_preset": typography_preset,
        "typography_presets": [
            {"id": key, "label": str(meta.get("label") or key.title())}
            for key, meta in CERTIFICATE_TYPOGRAPHY_PRESETS.items()
        ],
        "settings": settings,
        "updated_at": (doc or {}).get("updated_at") or _utcnow_iso(),
    }


async def _save_certificate_template_settings(settings: Dict[str, Any], user_id: str, typography_preset: Optional[str] = None) -> Dict[str, Any]:
    normalized = _sanitize_certificate_template_settings(settings)
    existing_doc = await db.learn_hub_certificate_templates.find_one(
        {"template_id": CERTIFICATE_TEMPLATE_DOC_ID},
        {"_id": 0, "typography_preset": 1},
    )
    resolved_typography_preset = _sanitize_certificate_typography_preset(
        typography_preset if typography_preset is not None else (existing_doc or {}).get("typography_preset")
    )
    now_iso = _utcnow_iso()
    payload = {
        "template_id": CERTIFICATE_TEMPLATE_DOC_ID,
        "template_version": CERTIFICATE_TEMPLATE_VERSION,
        "signature_profile_version": CERTIFICATE_SIGNATURE_PROFILE_VERSION,
        "footer_profile_version": CERTIFICATE_FOOTER_PROFILE_VERSION,
        "typography_preset": resolved_typography_preset,
        "settings": normalized,
        "updated_at": now_iso,
        "updated_by": user_id,
    }
    await db.learn_hub_certificate_templates.update_one(
        {"template_id": CERTIFICATE_TEMPLATE_DOC_ID},
        {"$set": payload},
        upsert=True,
    )
    return payload


def _safe_plan(value: Optional[str]) -> str:
    plan = (value or "free").lower().strip()
    return plan if plan in {"free", "basic", "premium"} else "free"


def _effective_plan_for_user(user: Any) -> str:
    raw = compute_effective_plan(
        {
            "is_admin": bool(getattr(user, "is_admin", False)),
            "full_access": bool(getattr(user, "full_access", False)),
            "subscription_permanent": bool(getattr(user, "subscription_permanent", False)),
            "subscription_plan": str(getattr(user, "subscription_plan", "free") or "free"),
            "subscription_status": str(getattr(user, "subscription_status", "active") or "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
            "payment_verified": bool(getattr(user, "payment_verified", False)),
        }
    )
    return _safe_plan(raw)


def _entitlements_for_plan(plan: str) -> Dict[str, Any]:
    normalized = _safe_plan(plan)
    limits = PLAN_DAILY_LIMITS[normalized]
    access = PLAN_ACCESS_POLICY[normalized]
    return {
        "plan": normalized,
        "learning_access": {
            "label": access["scope_label"],
            "catalog_limit": access["catalog_limit"],
            "max_active_enrollments": access["max_active_enrollments"],
            "max_total_enrollments": access["max_total_enrollments"],
            "auto_enforced": True,
        },
        "course_generation": {
            "daily_limit": limits["auto_generate_course"],
            "label": "Limited" if normalized == "free" else "Almost unlimited" if normalized == "basic" else "Unlimited",
        },
        "roadmap_generation": {
            "daily_limit": limits["roadmap"],
            "label": "Limited" if normalized == "free" else "Almost unlimited" if normalized == "basic" else "Unlimited",
        },
        "sandbox": {
            "mode": "safe-simulated",
            "daily_limit": limits["sandbox"],
        },
        "certificates": {
            "enabled": limits["certificate_issue"] != 0,
            "daily_limit": limits["certificate_issue"],
            "verification": "signed-verification-id",
        },
        "mentor_matching": {
            "daily_limit": limits["mentor_match"],
        },
    }


def _plan_access_policy(plan: str) -> Dict[str, Any]:
    normalized = _safe_plan(plan)
    policy = PLAN_ACCESS_POLICY.get(normalized) or PLAN_ACCESS_POLICY["free"]
    return {
        "plan": normalized,
        "scope_label": policy.get("scope_label") or "Limited access",
        "catalog_limit": int(policy.get("catalog_limit", 12) or 12),
        "max_active_enrollments": int(policy.get("max_active_enrollments", 2) or 2),
        "max_total_enrollments": int(policy.get("max_total_enrollments", 4) or 4),
        "auto_enforced": True,
    }


def _topic_tokens(value: str) -> List[str]:
    parts = re.findall(r"[a-z0-9]+", str(value or "").lower())
    tokens: List[str] = []
    for token in parts:
        if len(token) <= 2:
            continue
        if token in VIDEO_TOPIC_TOKEN_BLACKLIST:
            continue
        tokens.append(token)
    return tokens


def _build_topic_video_search_url(topic: str, lesson_title: str) -> str:
    query = " ".join(part for part in [str(topic or "").strip(), str(lesson_title or "").strip(), "explainer"] if part)
    return f"https://www.youtube.com/results?search_query={quote(query)}"


def _topic_alignment_score(topic: str, lesson_title: str) -> float:
    topic_set = set(_topic_tokens(topic))
    lesson_set = set(_topic_tokens(lesson_title))
    if not topic_set or not lesson_set:
        return 0.0
    overlap = len(topic_set.intersection(lesson_set))
    if overlap <= 0:
        return 0.0
    return round(overlap / max(1, len(topic_set)), 4)


def _video_topic_alignment_meta(topic: str, lesson_title: str, fallback_url: str) -> Dict[str, Any]:
    score = _topic_alignment_score(topic, lesson_title)
    status = "aligned" if score >= VIDEO_TOPIC_MATCH_THRESHOLD else "low_confidence"
    recommended_url = _build_topic_video_search_url(topic, lesson_title)
    if not str(fallback_url or "").strip():
        status = "fallback_search"
    return {
        "score": score,
        "status": status,
        "recommended_url": recommended_url,
    }


async def _daily_usage_count(user_id: str, action: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return await db.learn_hub_usage_events.count_documents({"user_id": user_id, "action": action, "day": today})


async def _track_usage(user_id: str, action: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    now = datetime.now(timezone.utc)
    await db.learn_hub_usage_events.insert_one(
        {
            "event_id": f"lh_usage_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "action": action,
            "day": now.date().isoformat(),
            "metadata": metadata or {},
            "created_at": now.isoformat(),
        }
    )


async def _track_growth_event(user_id: str, event_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    now = datetime.now(timezone.utc)
    await db.learn_hub_growth_events.insert_one(
        {
            "event_id": f"lh_growth_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "event_type": event_type,
            "day": now.date().isoformat(),
            "metadata": metadata or {},
            "created_at": now.isoformat(),
        }
    )


def _polygon_anchor_config() -> Dict[str, Any]:
    enable_live = str(os.environ.get("OTS_ENABLE") or "true").strip().lower() in {"1", "true", "yes", "on"}
    fallback_mode = str(os.environ.get("OTS_FALLBACK_MODE") or "disabled").strip().lower()
    fallback_mode = fallback_mode if fallback_mode in {"disabled"} else "disabled"
    cli_path_raw = str(os.environ.get("OTS_CLI_PATH") or "").strip()
    cli_candidates = [
        cli_path_raw,
        shutil.which("ots") or "",
        "/root/.venv/bin/ots",
        "/usr/local/bin/ots",
    ]
    cli_path = next((candidate for candidate in cli_candidates if candidate and os.path.exists(candidate)), "ots")
    cli_available = bool(shutil.which(cli_path) or os.path.exists(cli_path))
    configured = bool(cli_available)
    return {
        "enable_live": enable_live,
        "configured": configured,
        "rpc_url": "",
        "private_key": "",
        "chain_id": 0,
        "gas_limit": 0,
        "max_gas_price_gwei": 0,
        "fallback_mode": fallback_mode,
        "anchor_to_address": "",
        "ots_cli_path": cli_path,
        "ots_cli_available": cli_available,
        "ots_calendar_url": str(os.environ.get("OTS_CALENDAR_URL") or "").strip(),
    }


def _configured_anchor_mode(config: Optional[Dict[str, Any]] = None) -> str:
    cfg = config or _polygon_anchor_config()
    if cfg.get("enable_live") and cfg.get("configured"):
        return "opentimestamps"
    if cfg.get("enable_live") and not cfg.get("configured") and cfg.get("fallback_mode") == "disabled":
        return "disabled"
    return "disabled"


def _anchor_note_for_mode(mode: str) -> str:
    if mode == "opentimestamps":
        return "Queued for OpenTimestamps anchoring (Bitcoin-backed attestation)"
    if mode == "disabled":
        return "OpenTimestamps CLI is unavailable or anchoring is disabled"
    return f"Queued for OpenTimestamps batch anchoring every {ANCHOR_BATCH_INTERVAL_HOURS} hour(s)"


async def _get_streak_insurance_wallet(user_id: str) -> Dict[str, Any]:
    wallet = await db.learn_hub_streak_insurance_wallet.find_one({"user_id": user_id}, {"_id": 0}) or {}
    return {
        "tokens": int(wallet.get("tokens", 0) or 0),
        "last_granted_day": wallet.get("last_granted_day"),
        "last_redeemed_day": wallet.get("last_redeemed_day"),
    }


async def _enforce_entitlement(user: Any, action: str) -> None:
    plan = _effective_plan_for_user(user)
    limit = PLAN_DAILY_LIMITS.get(plan, PLAN_DAILY_LIMITS["free"]).get(action, 0)
    if limit < 0:
        return
    used = await _daily_usage_count(user.user_id, action)
    if used >= limit:
        if plan == "free":
            raise HTTPException(status_code=403, detail=f"Free plan limit reached for {action}. Upgrade to Basic or Premium.")
        raise HTTPException(status_code=429, detail=f"Daily limit reached for {action}. Try again tomorrow.")


def _parse_llm_json(raw: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    try:
        parsed = json.loads(text.strip())
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback


async def _ask_gpt_52_json(system_message: str, prompt: str, session_prefix: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"{session_prefix}-{uuid.uuid4().hex[:8]}",
            system_message=system_message,
        ).with_model("openai", "gpt-4o")
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)),
            timeout=AI_JSON_TIMEOUT_SECONDS,
        )
        raw = response.text if hasattr(response, "text") else str(response)
        return _parse_llm_json(raw, fallback)
    except Exception as exc:
        logger.warning(f"GPT-5.2 generation fallback triggered: {exc}")
        return fallback


async def _dedupe_learning_hub_courses() -> None:
    enrolled_ids = set()
    async for row in db.learn_hub_enrollments.find({}, {"_id": 0, "course_id": 1}):
        if row.get("course_id"):
            enrolled_ids.add(str(row["course_id"]))
    by_title: Dict[str, list] = {}
    async for c in db.learn_hub_courses.find({}, {"_id": 0, "course_id": 1, "title": 1, "seeded": 1, "updated_at": 1}):
        key = str(c.get("title") or "").strip().lower()
        if key:
            by_title.setdefault(key, []).append(c)
    remove_ids = []
    for rows in by_title.values():
        if len(rows) <= 1:
            continue
        rows.sort(
            key=lambda r: (str(r.get("course_id")) in enrolled_ids, bool(r.get("seeded")), str(r.get("updated_at") or "")),
            reverse=True,
        )
        remove_ids.extend([str(r["course_id"]) for r in rows[1:] if str(r["course_id"]) not in enrolled_ids])
    if remove_ids:
        await db.learn_hub_courses.delete_many({"course_id": {"$in": remove_ids}})


async def _seed_enterprise_courses() -> None:
    now = _utcnow_iso()
    seed_courses = build_seed_catalog(now)
    existing = await db.learn_hub_courses.count_documents({"seeded": True})
    if existing >= len(seed_courses):
        return

    for doc in seed_courses:
        slug = doc.pop("seed_slug")
        prior = await db.learn_hub_courses.find_one(
            {"title": doc["title"]}, {"_id": 0, "course_id": 1, "created_at": 1}
        )
        doc["course_id"] = str((prior or {}).get("course_id") or f"course_seed_{hashlib.sha1(slug.encode()).hexdigest()[:10]}")
        if prior and prior.get("created_at"):
            doc["created_at"] = prior["created_at"]
        modules = _normalize_modules(doc.get("modules"))
        video_lessons = _normalize_video_lessons(
            str(doc.get("course_id") or uuid.uuid4().hex[:8]),
            str(doc.get("subcategory") or doc.get("title") or "AI"),
            doc.get("video_lessons"),
            min_count=5,
        )
        learning_materials = _normalize_learning_materials(
            str(doc.get("course_id") or uuid.uuid4().hex[:8]),
            str(doc.get("subcategory") or doc.get("title") or "AI"),
            modules,
            doc.get("learning_materials"),
        )
        final_assessment = _normalize_final_assessment(
            str(doc.get("course_id") or uuid.uuid4().hex[:8]),
            str(doc.get("subcategory") or doc.get("title") or "AI"),
            modules,
            doc.get("final_assessment"),
        )
        doc["modules"] = modules
        doc["video_lessons"] = video_lessons
        doc["learning_materials"] = learning_materials
        doc["final_assessment"] = final_assessment
        await db.learn_hub_courses.update_one({"course_id": doc["course_id"]}, {"$set": doc}, upsert=True)

    await _dedupe_learning_hub_courses()


async def _auto_ingest_latest_papers() -> None:
    now = datetime.now(timezone.utc)
    meta = await db.learn_hub_paper_ingest.find_one({"type": "meta"}, {"_id": 0})
    if meta:
        last_ingest = meta.get("last_ingest_at")
        if isinstance(last_ingest, str):
            try:
                parsed = datetime.fromisoformat(last_ingest.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if (now - parsed).total_seconds() < 3 * 3600:
                    return
            except Exception:
                pass

    ingested_rows = []
    try:
        feed_url = "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&start=0&max_results=8&sortBy=submittedDate&sortOrder=descending"
        payload = urlopen(feed_url, timeout=8).read()
        root = ET.fromstring(payload)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
            if not title:
                continue
            link = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("atom:published", default="", namespaces=ns) or now.isoformat()).replace("Z", "+00:00")
            authors = [a.findtext("atom:name", default="", namespaces=ns) for a in entry.findall("atom:author", ns)]
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip().replace("\n", " ")
            paper_id = f"paper_{hashlib.sha1(link.encode()).hexdigest()[:12]}"
            doc = {
                "paper_id": paper_id,
                "title": title,
                "authors": [a for a in authors if a][:6],
                "published_at": published,
                "source": "arxiv",
                "url": link,
                "summary_short": summary[:420],
                "tags": ["AI", "Research", "Latest"],
                "ingested_at": now.isoformat(),
            }
            await db.learn_hub_research_papers.update_one({"paper_id": paper_id}, {"$set": doc}, upsert=True)
            ingested_rows.append(doc)
    except Exception as exc:
        logger.warning(f"Paper ingest fallback activated: {exc}")
        fallback_titles = [
            "Efficient Multimodal Reasoning for Enterprise Agents",
            "Adaptive Security Guardrails for LLM Applications",
            "Retrieval-Centric Architectures for Reliable AI Assistants",
            "Benchmarking Practical AI Coding Tutors in Production",
        ]
        for idx, title in enumerate(fallback_titles):
            paper_id = f"paper_fallback_{idx}"
            doc = {
                "paper_id": paper_id,
                "title": title,
                "authors": ["Research Collective"],
                "published_at": now.isoformat(),
                "source": "curated-fallback",
                "url": "",
                "summary_short": "Automated fallback research digest generated to preserve learning continuity.",
                "tags": ["AI", "Digest"],
                "ingested_at": now.isoformat(),
            }
            await db.learn_hub_research_papers.update_one({"paper_id": paper_id}, {"$set": doc}, upsert=True)
            ingested_rows.append(doc)

    await db.learn_hub_paper_ingest.update_one(
        {"type": "meta"},
        {
            "$set": {
                "type": "meta",
                "last_ingest_at": now.isoformat(),
                "last_ingest_count": len(ingested_rows),
                "status": "ok" if ingested_rows else "empty",
            }
        },
        upsert=True,
    )


async def _ensure_course_certificate_policies() -> None:
    now_iso = _utcnow_iso()
    defaults = {
        "Enterprise AI Foundations for Builders": 730,
        "Applied Cybersecurity for AI Teams": 365,
        "AI for Growth, Marketing & Revenue": 540,
    }
    for course_title, validity_days in defaults.items():
        await db.learn_hub_courses.update_one(
            {"title": course_title},
            {
                "$set": {
                    "certificate_validity_days": validity_days,
                    "certificate_policy": {
                        "auto_issue_on_completion": True,
                        "allow_admin_revocation": True,
                        "template_version": CERTIFICATE_TEMPLATE_VERSION,
                    },
                    "updated_at": now_iso,
                }
            },
        )


async def _ensure_learning_hub_automation() -> None:
    await _seed_enterprise_courses()
    await _ensure_course_certificate_policies()
    await _auto_ingest_latest_papers()


async def run_learning_hub_integrity_cycle(triggered_by: str = "manual") -> Dict[str, Any]:
    await _ensure_learning_hub_automation()
    weekly_publish = await ensure_weekly_course_publication(triggered_by=f"{triggered_by}:integrity")
    video_report = await validate_and_repair_learning_hub_videos(limit=800)

    now_iso = _utcnow_iso()
    total_courses = await db.learn_hub_courses.count_documents({})
    total_enrollments = await db.learn_hub_enrollments.count_documents({})
    total_certificates = await db.learn_hub_certificates.count_documents({})

    course_ids = set()
    async for row in db.learn_hub_courses.find({}, {"_id": 0, "course_id": 1}):
        cid = str(row.get("course_id") or "").strip()
        if cid:
            course_ids.add(cid)

    orphan_enrollments = 0
    async for row in db.learn_hub_enrollments.find({}, {"_id": 0, "course_id": 1}):
        cid = str(row.get("course_id") or "").strip()
        if cid and cid not in course_ids:
            orphan_enrollments += 1

    repaired_verify_urls = 0
    cert_rows = await db.learn_hub_certificates.find({}, {"_id": 0, "certificate_id": 1, "verification_id": 1, "verify_url": 1}).to_list(2000)
    for cert in cert_rows:
        verification_id = str(cert.get("verification_id") or "").strip()
        if not verification_id:
            continue
        canonical = _verification_public_url(verification_id)
        if cert.get("verify_url") != canonical:
            await db.learn_hub_certificates.update_one(
                {"certificate_id": cert.get("certificate_id")},
                {"$set": {"verify_url": canonical, "updated_at": now_iso}},
            )
            repaired_verify_urls += 1

    papers_meta = await db.learn_hub_paper_ingest.find_one({"type": "meta"}, {"_id": 0}) or {}
    pending_anchor_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "pending"})

    if orphan_enrollments > 0:
        status = "critical"
    elif pending_anchor_count > 250:
        status = "warning"
    elif int(video_report.get("broken_links", 0) or 0) > 0:
        status = "warning"
    elif int(video_report.get("topic_mismatch_lessons", 0) or 0) > 0:
        status = "warning"
    else:
        status = "healthy"

    integrity_doc = {
        "run_id": f"learn_integrity_{uuid.uuid4().hex[:12]}",
        "triggered_by": triggered_by,
        "run_at": now_iso,
        "status": status,
        "totals": {
            "courses": total_courses,
            "enrollments": total_enrollments,
            "certificates": total_certificates,
        },
        "checks": {
            "orphan_enrollments": orphan_enrollments,
            "repaired_verify_urls": repaired_verify_urls,
            "pending_anchor_count": pending_anchor_count,
            "paper_ingest_status": papers_meta.get("status", "unknown"),
            "paper_last_ingest_at": papers_meta.get("last_ingest_at"),
            "video_broken_links": int(video_report.get("broken_links", 0) or 0),
            "video_repaired_courses": int(video_report.get("repaired_courses", 0) or 0),
            "video_topic_mismatches": int(video_report.get("topic_mismatch_lessons", 0) or 0),
            "video_topic_repaired": int(video_report.get("topic_repaired_lessons", 0) or 0),
            "video_topic_alignment_pct": float(video_report.get("topic_alignment_pct", 100) or 100),
            "weekly_publish_count": int(weekly_publish.get("total_count", 0) or 0),
            "weekly_created_count": int(weekly_publish.get("created_count", 0) or 0),
        },
    }

    await db.learn_hub_integrity_history.insert_one({**integrity_doc})
    await db.learn_hub_integrity_runtime.update_one(
        {"key": "learning_hub_integrity_runtime"},
        {
            "$set": {
                "key": "learning_hub_integrity_runtime",
                "last_run_at": now_iso,
                "last_status": status,
                "last_triggered_by": triggered_by,
                "repaired_verify_urls": repaired_verify_urls,
                "orphan_enrollments": orphan_enrollments,
                "pending_anchor_count": pending_anchor_count,
                "paper_last_ingest_at": papers_meta.get("last_ingest_at"),
                "video_broken_links": int(video_report.get("broken_links", 0) or 0),
                "video_topic_mismatches": int(video_report.get("topic_mismatch_lessons", 0) or 0),
                "video_topic_alignment_pct": float(video_report.get("topic_alignment_pct", 100) or 100),
                "weekly_publish_count": int(weekly_publish.get("total_count", 0) or 0),
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    return integrity_doc


async def _compute_streak(user_id: str) -> Dict[str, Any]:
    rows = await db.learn_hub_daily_activity.find({"user_id": user_id}, {"_id": 0}).sort("day", -1).limit(45).to_list(45)
    redeem_rows = await db.learn_hub_streak_insurance_redeems.find(
        {"user_id": user_id, "status": "applied"},
        {"_id": 0, "insured_day": 1},
    ).sort("insured_day", -1).limit(45).to_list(45)

    if not rows and not redeem_rows:
        return {"streak_days": 0, "today_minutes": 0, "weekly_minutes": 0, "insured_days": 0}

    by_day = {row.get("day"): int(row.get("minutes", 0) or 0) for row in rows}
    insured_days = {str(row.get("insured_day") or "") for row in redeem_rows if row.get("insured_day")}
    today = datetime.now(timezone.utc).date()
    streak = 0
    cursor = today
    while True:
        key = cursor.isoformat()
        if by_day.get(key, 0) > 0 or key in insured_days:
            streak += 1
            cursor = cursor.fromordinal(cursor.toordinal() - 1)
            continue
        break

    weekly_minutes = 0
    for i in range(7):
        d = today.fromordinal(today.toordinal() - i).isoformat()
        weekly_minutes += by_day.get(d, 0)

    return {
        "streak_days": streak,
        "today_minutes": by_day.get(today.isoformat(), 0),
        "weekly_minutes": weekly_minutes,
        "insured_days": len(insured_days),
    }


async def _record_learning_minutes(user_id: str, minutes: int) -> None:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    await db.learn_hub_daily_activity.update_one(
        {"user_id": user_id, "day": day},
        {
            "$set": {"updated_at": now.isoformat()},
            "$inc": {"minutes": max(0, int(minutes))},
            "$setOnInsert": {"activity_id": f"act_{uuid.uuid4().hex[:10]}", "user_id": user_id, "day": day, "created_at": now.isoformat()},
        },
        upsert=True,
    )


async def _ensure_daily_habit_missions(user_id: str, day: str) -> None:
    now_iso = _utcnow_iso()
    mission_templates = [
        {
            "mission_key": "learning_minutes",
            "title": "Deep Focus Learning",
            "description": "Complete 25 focused learning minutes today.",
            "target": 25,
            "unit": "minutes",
            "points": 25,
            "action_url": "/ai-learning-hub",
        },
        {
            "mission_key": "module_completion",
            "title": "Momentum Module",
            "description": "Finish at least one module to keep execution velocity.",
            "target": 1,
            "unit": "modules",
            "points": 30,
            "action_url": "/ai-learning-hub",
        },
        {
            "mission_key": "career_sprint",
            "title": "Career Income Sprint",
            "description": "Generate or update a career sprint for real-world execution.",
            "target": 1,
            "unit": "sprints",
            "points": 35,
            "action_url": "/ai-learning-hub",
        },
        {
            "mission_key": "daily_check_in",
            "title": "Adaptive Check-in",
            "description": "Complete a focus + mood check-in for AI adjustment.",
            "target": 1,
            "unit": "check-ins",
            "points": 20,
            "action_url": "/ai-learning-hub",
        },
    ]

    for template in mission_templates:
        mission_id = f"lh_mission_{user_id}_{day}_{template['mission_key']}"
        await db.learn_hub_daily_missions.update_one(
            {"user_id": user_id, "day": day, "mission_key": template["mission_key"]},
            {
                "$setOnInsert": {
                    "mission_id": mission_id,
                    "user_id": user_id,
                    "day": day,
                    "mission_key": template["mission_key"],
                    "title": template["title"],
                    "description": template["description"],
                    "target": template["target"],
                    "unit": template["unit"],
                    "points": template["points"],
                    "progress": 0,
                    "completed": False,
                    "manual_override": False,
                    "action_url": template["action_url"],
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )


async def _module_completions_today(user_id: str, day: str) -> int:
    enrollments = await db.learn_hub_enrollments.find(
        {"user_id": user_id},
        {"_id": 0, "modules": 1, "updated_at": 1},
    ).to_list(250)
    completed_count = 0
    for enrollment in enrollments:
        modules = enrollment.get("modules") or []
        matched_in_module = False
        for module in modules:
            completed_at = str(module.get("completed_at") or "")
            if module.get("completed") and completed_at.startswith(day):
                completed_count += 1
                matched_in_module = True
        if not matched_in_module and str(enrollment.get("updated_at") or "").startswith(day):
            if any(bool(module.get("completed")) for module in modules):
                completed_count += 1
    return completed_count


def _habit_risk_and_nudge(streak_days: int, weekly_minutes: int, mood_score: Optional[int]) -> Dict[str, Any]:
    if weekly_minutes >= 210 and streak_days >= 7:
        risk = 8
    elif weekly_minutes >= 120 and streak_days >= 4:
        risk = 24
    elif weekly_minutes >= 60:
        risk = 49
    else:
        risk = 78

    if mood_score is not None and mood_score <= 2:
        risk = min(95, risk + 10)

    if risk <= 20:
        nudge = "Elite consistency. Push one high-leverage career deliverable today."
    elif risk <= 45:
        nudge = "Strong momentum. Finish one mission now to protect your streak."
    elif risk <= 65:
        nudge = "Habit drift detected. Complete a 15-minute sprint immediately."
    else:
        nudge = "High relapse risk. Start with the easiest mission and recover momentum."

    return {"risk_score": risk, "nudge": nudge}


async def _build_habit_loop_summary(user: Any, streak_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    now_iso = now.isoformat()
    await _ensure_daily_habit_missions(user.user_id, day)

    streak = streak_snapshot or await _compute_streak(user.user_id)
    module_completions_today = await _module_completions_today(user.user_id, day)
    career_sprint_count_today = await db.learn_hub_career_sprints.count_documents(
        {"user_id": user.user_id, "created_day": day}
    )
    checkin_count_today = await db.learn_hub_habit_checkins.count_documents(
        {"user_id": user.user_id, "day": day}
    )

    progress_map = {
        "learning_minutes": int(streak.get("today_minutes", 0) or 0),
        "module_completion": int(module_completions_today),
        "career_sprint": int(career_sprint_count_today),
        "daily_check_in": int(checkin_count_today),
    }

    rows = await db.learn_hub_daily_missions.find(
        {"user_id": user.user_id, "day": day},
        {"_id": 0},
    ).sort("created_at", 1).to_list(20)

    missions: List[Dict[str, Any]] = []
    total_points = 0
    earned_points = 0

    for row in rows:
        mission_key = str(row.get("mission_key") or "")
        target = max(1, int(row.get("target", 1) or 1))
        progress = int(progress_map.get(mission_key, 0) or 0)
        manual_override = bool(row.get("manual_override"))
        completed = bool(row.get("completed")) if manual_override else progress >= target
        completed_at = row.get("completed_at")
        if completed and not completed_at:
            completed_at = now_iso

        if (
            progress != int(row.get("progress", 0) or 0)
            or completed != bool(row.get("completed"))
            or completed_at != row.get("completed_at")
        ):
            await db.learn_hub_daily_missions.update_one(
                {"mission_id": row.get("mission_id")},
                {
                    "$set": {
                        "progress": progress,
                        "completed": completed,
                        "completed_at": completed_at,
                        "updated_at": now_iso,
                    }
                },
            )

        points = int(row.get("points", 0) or 0)
        total_points += points
        if completed:
            earned_points += points

        missions.append(
            {
                **row,
                "target": target,
                "progress": progress,
                "completed": completed,
                "completed_at": completed_at,
            }
        )

    completion_ratio = (earned_points / total_points) if total_points > 0 else 0
    multiplier = round(1 + min(0.5, (int(streak.get("streak_days", 0) or 0) * 0.03)), 2)
    latest_checkin = await db.learn_hub_habit_checkins.find_one(
        {"user_id": user.user_id, "day": day},
        {"_id": 0, "mood_score": 1},
        sort=[("created_at", -1)],
    ) or {}
    risk_block = _habit_risk_and_nudge(
        int(streak.get("streak_days", 0) or 0),
        int(streak.get("weekly_minutes", 0) or 0),
        latest_checkin.get("mood_score"),
    )
    wallet = await _get_streak_insurance_wallet(user.user_id)

    return {
        "day": day,
        "missions": missions,
        "points": {
            "earned": earned_points,
            "total": total_points,
            "completion_pct": round(completion_ratio * 100, 1),
        },
        "streak_multiplier": multiplier,
        "all_completed": all(bool(m.get("completed")) for m in missions) if missions else False,
        "risk": risk_block,
        "streak_insurance": wallet,
    }


def _build_phase2_onboarding_summary(
    enrollment_rows: List[Dict[str, Any]],
    latest_sprint: Optional[Dict[str, Any]],
    habit_loop_summary: Dict[str, Any],
    certificates_count: int,
) -> Dict[str, Any]:
    missions = habit_loop_summary.get("missions") if isinstance(habit_loop_summary.get("missions"), list) else []
    mission_map = {str(m.get("mission_key") or ""): bool(m.get("completed")) for m in missions}

    has_enrollment = len(enrollment_rows) > 0
    has_module_completion = any(
        bool(mod.get("completed"))
        for row in enrollment_rows
        for mod in (row.get("modules") if isinstance(row.get("modules"), list) else [])
    )
    has_sprint = bool(latest_sprint and latest_sprint.get("sprint_id"))
    has_checkin = bool(mission_map.get("daily_check_in"))
    has_certificate = int(certificates_count or 0) > 0

    steps: List[Dict[str, Any]] = [
        {
            "step_id": "enroll_first_course",
            "title": "Enroll in your first course",
            "description": "Pick a track from Discover to start your execution loop.",
            "completed": has_enrollment,
            "action": {
                "kind": "tab",
                "tab": "discover",
                "route": "/ai-learning-hub?tab=discover",
                "cta_label": "Open Discover",
            },
        },
        {
            "step_id": "complete_first_module",
            "title": "Complete one module",
            "description": "Finish one module to activate measurable momentum.",
            "completed": has_module_completion,
            "action": {
                "kind": "tab",
                "tab": "journey",
                "route": "/ai-learning-hub?tab=journey&filter=active",
                "cta_label": "Open Journey",
            },
        },
        {
            "step_id": "generate_career_sprint",
            "title": "Generate a 7-day career sprint",
            "description": "Create a practical weekly plan with career-income outcomes.",
            "completed": has_sprint,
            "action": {
                "kind": "tab",
                "tab": "lab",
                "route": "/ai-learning-hub?tab=lab",
                "cta_label": "Open AI Lab",
            },
        },
        {
            "step_id": "finish_daily_checkin",
            "title": "Submit daily check-in",
            "description": "Log mood and focus for adaptive coaching nudges.",
            "completed": has_checkin,
            "action": {
                "kind": "tab",
                "tab": "lab",
                "route": "/ai-learning-hub?tab=lab",
                "cta_label": "Start Check-in",
            },
        },
        {
            "step_id": "claim_first_certificate",
            "title": "Claim your first certificate",
            "description": "Convert completed learning into visible trust proof.",
            "completed": has_certificate,
            "action": {
                "kind": "tab",
                "tab": "journey",
                "route": "/ai-learning-hub?tab=journey&filter=completed",
                "cta_label": "Claim in Journey",
            },
        },
    ]

    total_steps = len(steps)
    completed_steps = sum(1 for step in steps if bool(step.get("completed")))
    completion_pct = round((completed_steps / max(total_steps, 1)) * 100, 1)
    next_step = next((step for step in steps if not bool(step.get("completed"))), None)

    return {
        "version": "phase2-commercial-onboarding-v1",
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "completion_pct": completion_pct,
        "completed": completed_steps == total_steps,
        "next_step_id": next_step.get("step_id") if next_step else None,
        "steps": steps,
    }


def _public_leaderboard_name(user_row: Dict[str, Any], fallback_user_id: str) -> str:
    for key in ("full_name", "display_name", "name"):
        value = str(user_row.get(key) or "").strip()
        if value:
            return value[:40]

    email = str(user_row.get("email") or "").strip()
    if "@" in email:
        handle = re.sub(r"[^a-zA-Z0-9]+", " ", email.split("@", 1)[0]).strip()
        if handle:
            parts = [token.capitalize() for token in handle.split()[:2]]
            if parts:
                return " ".join(parts)[:40]

    tail = str(fallback_user_id or "user")[-4:]
    return f"Learner {tail}"


def _streak_badge_from_days(streak_days: int) -> Dict[str, Any]:
    if streak_days >= 30:
        return {
            "tier": "legend",
            "label": "Legend Flame",
            "description": "30+ day streak — elite consistency",
            "style": "gold",
        }
    if streak_days >= 14:
        return {
            "tier": "champion",
            "label": "Champion Builder",
            "description": "14+ day streak — strong execution momentum",
            "style": "emerald",
        }
    if streak_days >= 7:
        return {
            "tier": "rising",
            "label": "Rising Operator",
            "description": "7+ day streak — weekly rhythm established",
            "style": "blue",
        }
    if streak_days >= 1:
        return {
            "tier": "starter",
            "label": "Momentum Starter",
            "description": "First streak unlocked — keep compounding",
            "style": "slate",
        }
    return {
        "tier": "none",
        "label": "No Badge Yet",
        "description": "Complete one mission today to unlock your first badge",
        "style": "muted",
    }


def _build_weekly_retention_nudges(
    today: date,
    weekly_xp_earned: int,
    xp_goal: int,
    weekly_minutes: int,
    minutes_goal: int,
    weekly_missions_completed: int,
    mission_goal: int,
) -> Dict[str, Any]:
    weekday_index = int(today.weekday())
    weekday_labels = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekday_label = weekday_labels[weekday_index]

    xp_remaining = max(0, int(xp_goal) - int(weekly_xp_earned))
    minutes_remaining = max(0, int(minutes_goal) - int(weekly_minutes))
    missions_remaining = max(0, int(mission_goal) - int(weekly_missions_completed))
    weekly_progress_pct = round(
        (
            (min(1.0, (weekly_xp_earned / max(xp_goal, 1)))
             + min(1.0, (weekly_minutes / max(minutes_goal, 1)))
             + min(1.0, (weekly_missions_completed / max(mission_goal, 1))))
            / 3
        ) * 100,
        1,
    )

    monday_started = (weekly_xp_earned > 0) or (weekly_minutes > 0) or (weekly_missions_completed > 0)
    friday_goals_hit = (weekly_xp_earned >= xp_goal) or (weekly_minutes >= minutes_goal) or (weekly_missions_completed >= mission_goal)

    if weekday_index == 0:
        monday_state = "active"
    elif monday_started:
        monday_state = "completed"
    else:
        monday_state = "missed"

    if weekday_index < 4:
        friday_state = "upcoming"
    elif weekday_index == 4:
        friday_state = "active"
    elif friday_goals_hit:
        friday_state = "completed"
    else:
        friday_state = "cooldown"

    monday_reset = {
        "nudge_id": "monday_reset",
        "day": "monday",
        "state": monday_state,
        "headline": "Monday Reset: lock your first win",
        "message": (
            "Start the week with one check-in and one completed mission to prevent drift."
            if not monday_started
            else "Momentum started this week. Keep the chain alive with one more focused mission."
        ),
        "priority": "high" if monday_state == "active" and not monday_started else "medium",
        "cta": {
            "label": "Run Monday reset",
            "action_url": "/ai-learning-hub?tab=lab",
            "action_type": "route",
        },
        "meta": {
            "missions_remaining": missions_remaining,
            "xp_remaining": xp_remaining,
        },
    }

    friday_momentum = {
        "nudge_id": "friday_momentum",
        "day": "friday",
        "state": friday_state,
        "headline": "Friday Momentum Push: close the loop",
        "message": (
            "You're close. Close remaining goals before weekly reset to protect your streak signal."
            if (not friday_goals_hit and (xp_remaining <= 80 or missions_remaining <= 3 or minutes_remaining <= 60))
            else ("Weekly targets are healthy. Push one final mission to end strong." if not friday_goals_hit else "Goals achieved this week. Use Friday to compound next week early.")
        ),
        "priority": "high" if friday_state == "active" and not friday_goals_hit else "medium",
        "cta": {
            "label": "Finish weekly goals",
            "action_url": "/ai-learning-hub?tab=journey&filter=active",
            "action_type": "route",
        },
        "meta": {
            "missions_remaining": missions_remaining,
            "xp_remaining": xp_remaining,
            "minutes_remaining": minutes_remaining,
        },
    }

    active_prompt = monday_reset if weekday_index == 0 else (friday_momentum if weekday_index == 4 else None)
    upcoming_prompt = friday_momentum if weekday_index in (0, 1, 2, 3) else monday_reset

    return {
        "cadence": {
            "timezone": "UTC",
            "weekday_index": weekday_index,
            "weekday_label": weekday_label,
            "is_monday": weekday_index == 0,
            "is_friday": weekday_index == 4,
        },
        "weekly_progress_pct": weekly_progress_pct,
        "monday_reset": monday_reset,
        "friday_momentum": friday_momentum,
        "active_prompt": active_prompt,
        "upcoming_prompt": upcoming_prompt,
    }


async def _build_weekly_achievement_loop(user: Any, streak: Dict[str, Any]) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    week_start = (today - timedelta(days=6)).isoformat()
    week_end = today.isoformat()

    weekly_minutes = int(streak.get("weekly_minutes", 0) or 0)
    streak_days = int(streak.get("streak_days", 0) or 0)

    user_completed_rows = await db.learn_hub_daily_missions.find(
        {
            "user_id": user.user_id,
            "day": {"$gte": week_start},
            "completed": True,
        },
        {"_id": 0, "points": 1},
    ).to_list(200)
    weekly_xp_earned = sum(int(row.get("points", 0) or 0) for row in user_completed_rows)
    weekly_missions_completed = len(user_completed_rows)
    weekly_missions_total = await db.learn_hub_daily_missions.count_documents(
        {
            "user_id": user.user_id,
            "day": {"$gte": week_start},
        }
    )
    mission_completion_pct = round((weekly_missions_completed / max(weekly_missions_total, 1)) * 100, 1)

    xp_goal = 220
    minutes_goal = 180
    mission_goal = 14

    def _goal_card(card_id: str, title: str, description: str, current: int, target: int, unit: str, reward: str) -> Dict[str, Any]:
        progress_pct = round((current / max(target, 1)) * 100, 1)
        return {
            "card_id": card_id,
            "title": title,
            "description": description,
            "current": int(current),
            "target": int(target),
            "unit": unit,
            "progress_pct": min(100.0, max(0.0, progress_pct)),
            "completed": current >= target,
            "reward": reward,
        }

    mission_cards = [
        _goal_card(
            "weekly_xp",
            "Weekly XP Goal",
            "Stack mission points to prove consistent execution.",
            weekly_xp_earned,
            xp_goal,
            "XP",
            "Unlock Focus Operator badge showcase",
        ),
        _goal_card(
            "weekly_minutes",
            "Weekly Minutes Goal",
            "Hit your weekly learning rhythm to protect momentum.",
            weekly_minutes,
            minutes_goal,
            "minutes",
            "Unlock Consistency Pulse badge",
        ),
        _goal_card(
            "weekly_missions",
            "Weekly Mission Completion",
            "Close mission loops and bank compounding confidence.",
            weekly_missions_completed,
            mission_goal,
            "missions",
            "Unlock Mission Captain badge",
        ),
    ]

    completion_rewards: List[Dict[str, Any]] = [
        {
            "reward_id": "streak_badge",
            "title": _streak_badge_from_days(streak_days).get("label"),
            "description": "Visible streak badge in your weekly loop",
            "status": "unlocked" if streak_days > 0 else "locked",
        },
        {
            "reward_id": "xp_goal_badge",
            "title": "Focus Operator",
            "description": "Earned by completing the weekly XP goal",
            "status": "unlocked" if weekly_xp_earned >= xp_goal else "locked",
        },
        {
            "reward_id": "mission_goal_badge",
            "title": "Mission Captain",
            "description": "Earned by completing weekly mission target",
            "status": "unlocked" if weekly_missions_completed >= mission_goal else "locked",
        },
    ]

    leaderboard_rows = await db.learn_hub_daily_missions.aggregate(
        [
            {
                "$match": {
                    "day": {"$gte": week_start},
                    "completed": True,
                }
            },
            {
                "$group": {
                    "_id": "$user_id",
                    "weekly_xp": {"$sum": {"$ifNull": ["$points", 0]}},
                    "missions_completed": {"$sum": 1},
                }
            },
            {"$sort": {"weekly_xp": -1, "missions_completed": -1}},
            {"$limit": 5},
        ]
    ).to_list(5)
    leaderboard_user_ids = [str(row.get("_id") or "") for row in leaderboard_rows if row.get("_id")]
    leaderboard_profiles = await db.users.find(
        {"user_id": {"$in": leaderboard_user_ids}},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "display_name": 1, "name": 1},
    ).to_list(max(1, len(leaderboard_user_ids)))
    leaderboard_profile_map = {
        str(row.get("user_id") or ""): row
        for row in leaderboard_profiles
        if row.get("user_id")
    }

    leaderboard_entries: List[Dict[str, Any]] = []
    for idx, row in enumerate(leaderboard_rows, start=1):
        uid = str(row.get("_id") or "")
        profile = leaderboard_profile_map.get(uid, {})
        leaderboard_entries.append(
            {
                "rank": idx,
                "user_id": uid,
                "display_name": _public_leaderboard_name(profile, uid),
                "weekly_xp": int(row.get("weekly_xp", 0) or 0),
                "missions_completed": int(row.get("missions_completed", 0) or 0),
                "is_current_user": uid == user.user_id,
            }
        )

    if not leaderboard_entries:
        fallback_profile = {
            "email": getattr(user, "email", None),
            "full_name": getattr(user, "full_name", None),
            "display_name": getattr(user, "display_name", None),
            "name": getattr(user, "name", None),
        }
        leaderboard_entries.append(
            {
                "rank": 1,
                "user_id": user.user_id,
                "display_name": _public_leaderboard_name(fallback_profile, user.user_id),
                "weekly_xp": weekly_xp_earned,
                "missions_completed": weekly_missions_completed,
                "is_current_user": True,
            }
        )

    rank_rows = []
    if weekly_xp_earned > 0:
        rank_rows = await db.learn_hub_daily_missions.aggregate(
            [
                {
                    "$match": {
                        "day": {"$gte": week_start},
                        "completed": True,
                    }
                },
                {
                    "$group": {
                        "_id": "$user_id",
                        "weekly_xp": {"$sum": {"$ifNull": ["$points", 0]}},
                    }
                },
                {"$match": {"weekly_xp": {"$gt": weekly_xp_earned}}},
                {"$count": "higher"},
            ]
        ).to_list(1)

    current_rank = None
    if weekly_xp_earned > 0:
        current_rank = int((rank_rows[0].get("higher") if rank_rows else 0) or 0) + 1

    retention_nudges = _build_weekly_retention_nudges(
        today=today,
        weekly_xp_earned=weekly_xp_earned,
        xp_goal=xp_goal,
        weekly_minutes=weekly_minutes,
        minutes_goal=minutes_goal,
        weekly_missions_completed=weekly_missions_completed,
        mission_goal=mission_goal,
    )

    return {
        "window": {
            "start_day": week_start,
            "end_day": week_end,
        },
        "xp": {
            "earned": weekly_xp_earned,
            "goal": xp_goal,
        },
        "minutes": {
            "earned": weekly_minutes,
            "goal": minutes_goal,
        },
        "missions": {
            "completed": weekly_missions_completed,
            "total": int(weekly_missions_total),
            "goal": mission_goal,
            "completion_pct": mission_completion_pct,
        },
        "streak_badge": _streak_badge_from_days(streak_days),
        "mission_cards": mission_cards,
        "completion_rewards": completion_rewards,
        "retention_nudges": retention_nudges,
        "leaderboard_teaser": {
            "headline": "Weekly top builders",
            "entries": leaderboard_entries,
            "you": {
                "user_id": user.user_id,
                "rank": current_rank,
                "weekly_xp": weekly_xp_earned,
                "in_top_five": any(bool(entry.get("is_current_user")) for entry in leaderboard_entries),
            },
        },
    }


async def _days_since_last_checkin(user_id: str) -> Optional[int]:
    latest = await db.learn_hub_habit_checkins.find_one(
        {"user_id": user_id},
        {"_id": 0, "created_at": 1, "day": 1},
        sort=[("created_at", -1)],
    )
    if not latest:
        return None

    raw = str(latest.get("created_at") or latest.get("day") or "").strip()
    if not raw:
        return None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc).date() - dt.date()).days)
    except Exception:
        return None


def _recovery_level(risk_score: int) -> str:
    if risk_score >= 70:
        return "high"
    if risk_score >= 45:
        return "medium"
    return "low"


async def _build_recovery_copilot_payload(user: Any) -> Dict[str, Any]:
    now_iso = _utcnow_iso()
    streak = await _compute_streak(user.user_id)
    summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    risk_score = int((summary.get("risk") or {}).get("risk_score", 0) or 0)
    risk_level = _recovery_level(risk_score)
    missions = summary.get("missions") if isinstance(summary.get("missions"), list) else []
    incomplete_missions = [m for m in missions if not bool(m.get("completed"))]
    days_since_checkin = await _days_since_last_checkin(user.user_id)

    latest_sprint = await db.learn_hub_career_sprints.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "sprint_id": 1, "created_at": 1, "challenge_title": 1},
        sort=[("created_at", -1)],
    ) or {}
    days_since_sprint = None
    if latest_sprint.get("created_at"):
        try:
            sdt = datetime.fromisoformat(str(latest_sprint.get("created_at")).replace("Z", "+00:00"))
            if sdt.tzinfo is None:
                sdt = sdt.replace(tzinfo=timezone.utc)
            days_since_sprint = max(0, (datetime.now(timezone.utc).date() - sdt.date()).days)
        except Exception:
            days_since_sprint = None

    drift_signals: List[Dict[str, Any]] = []
    if days_since_checkin is None or days_since_checkin >= 3:
        drift_signals.append(
            {
                "signal": "checkin_gap",
                "severity": "high" if (days_since_checkin or 99) >= 5 else "medium",
                "detail": f"No check-in in {days_since_checkin if days_since_checkin is not None else 'N/A'} day(s).",
            }
        )
    if incomplete_missions:
        drift_signals.append(
            {
                "signal": "incomplete_missions",
                "severity": "high" if len(incomplete_missions) >= 3 else "medium",
                "detail": f"{len(incomplete_missions)} mission(s) still open today.",
            }
        )
    if days_since_sprint is None or days_since_sprint >= 7:
        drift_signals.append(
            {
                "signal": "stagnant_sprint_progress",
                "severity": "medium",
                "detail": "No recent sprint execution detected in the last 7+ days.",
            }
        )

    fallback_plan = {
        "plan_steps": [
            "Run a 15-minute focus block on your highest-impact learning task now.",
            "Complete one remaining mission today to restore momentum.",
            "Generate a recovery sprint and book an intro session for external accountability.",
        ],
        "coach_message": "Recovery is a systems move: one quick win, one mission, one accountable next step.",
    }

    ai_prompt = f"""Build a recovery copilot plan for a learning user.
Risk score: {risk_score}
Risk level: {risk_level}
Days since check-in: {days_since_checkin}
Incomplete missions: {len(incomplete_missions)}
Days since sprint: {days_since_sprint}
Return JSON only with keys: plan_steps(array max 3), coach_message."""
    ai_payload = await _ask_gpt_52_json(
        "You are an execution coach for AI learners. Keep output concrete and concise.",
        ai_prompt,
        "learnhub-recovery-copilot",
        fallback_plan,
    )
    plan_steps = ai_payload.get("plan_steps") if isinstance(ai_payload, dict) else None
    if not isinstance(plan_steps, list) or not plan_steps:
        plan_steps = fallback_plan["plan_steps"]

    return {
        "generated_at": now_iso,
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "nudge": (summary.get("risk") or {}).get("nudge"),
        },
        "drift_signals": drift_signals,
        "plan_steps": [str(step)[:220] for step in plan_steps[:3]],
        "coach_message": str((ai_payload or {}).get("coach_message") or fallback_plan["coach_message"]),
        "quick_actions": [
            {
                "action_id": "generate_recovery_sprint",
                "label": "Generate Recovery Sprint",
                "description": "Create a compact sprint to get back on track this week.",
                "apply_supported": True,
            },
            {
                "action_id": "complete_next_mission",
                "label": "Complete Next Mission",
                "description": "Auto-complete the next pending daily mission to restart momentum.",
                "apply_supported": True,
            },
            {
                "action_id": "book_intro_session",
                "label": "Book Intro Session",
                "description": "Open your intro booking flow for external accountability.",
                "apply_supported": True,
                "action_url": "/book-meeting",
            },
        ],
        "meta": {
            "days_since_last_checkin": days_since_checkin,
            "days_since_last_sprint": days_since_sprint,
            "incomplete_missions": len(incomplete_missions),
            "streak_days": int(streak.get("streak_days", 0) or 0),
            "weekly_minutes": int(streak.get("weekly_minutes", 0) or 0),
        },
    }


async def _grant_streak_insurance_token_if_eligible(user_id: str, day: str) -> Dict[str, Any]:
    wallet = await db.learn_hub_streak_insurance_wallet.find_one({"user_id": user_id}, {"_id": 0}) or {}
    if wallet.get("last_granted_day") == day:
        return {
            "tokens": int(wallet.get("tokens", 0) or 0),
            "granted": False,
            "last_granted_day": wallet.get("last_granted_day"),
        }

    now_iso = _utcnow_iso()
    await db.learn_hub_streak_insurance_wallet.update_one(
        {"user_id": user_id},
        {
            "$inc": {"tokens": 1},
            "$set": {"last_granted_day": day, "updated_at": now_iso},
            "$setOnInsert": {"wallet_id": f"lh_streak_wallet_{uuid.uuid4().hex[:10]}", "user_id": user_id, "created_at": now_iso},
        },
        upsert=True,
    )
    refreshed = await _get_streak_insurance_wallet(user_id)
    return {
        "tokens": int(refreshed.get("tokens", 0) or 0),
        "granted": True,
        "last_granted_day": refreshed.get("last_granted_day"),
    }


def _sign_certificate_payload(verification_id: str, user_id: str, course_id: str, issued_at: str) -> str:
    signature = f"{verification_id}:{user_id}:{course_id}:{issued_at}"
    return hashlib.sha256(signature.encode()).hexdigest()


def _certificate_signature_is_valid(certificate: Dict[str, Any]) -> bool:
    expected_hash = _sign_certificate_payload(
        str(certificate.get("verification_id") or ""),
        str(certificate.get("user_id") or ""),
        str(certificate.get("course_id") or ""),
        str(certificate.get("issued_at") or ""),
    )
    return expected_hash == certificate.get("validation_hash")


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _format_certificate_date(value: Optional[str]) -> str:
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return "--"
    return parsed.strftime("%d %B %Y")


def _default_certificate_validity_days(course_doc: Optional[Dict[str, Any]]) -> Optional[int]:
    record = course_doc or {}
    raw = record.get("certificate_validity_days")
    try:
        days = int(raw)
    except Exception:
        days = 0
    return days if days > 0 else None


def _generate_certificate_number(course_id: str, issued_at: Optional[str] = None) -> str:
    course_slug = re.sub(r"[^A-Z0-9]", "", str(course_id or "RAC").upper())[:4] or "RAC"
    issued_dt = _parse_iso_datetime(issued_at) or datetime.now(timezone.utc)
    return f"RAC-{issued_dt.strftime('%Y%m%d')}-{course_slug}-{uuid.uuid4().hex[:6].upper()}"


def _certificate_record_hash(certificate: Dict[str, Any]) -> str:
    parts = [
        str(certificate.get("verification_id") or ""),
        str(certificate.get("certificate_number") or ""),
        str(certificate.get("user_id") or ""),
        str(certificate.get("course_id") or ""),
        str(certificate.get("learner_name") or ""),
        str(certificate.get("course_title") or ""),
        str(certificate.get("issued_at") or ""),
        str(certificate.get("expiration_date") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _certificate_public_asset_url(verification_id: str, asset_type: str, variant: str = "print") -> str:
    encoded_id = quote(str(verification_id or ""), safe="")
    if asset_type == "pdf":
        return f"/api/ai-learn/certificates/verify/{encoded_id}/pdf/file?variant={variant}"
    return f"/api/ai-learn/certificates/verify/{encoded_id}/png/file?variant={variant}"


def _certificate_lifecycle(certificate: Dict[str, Any]) -> Dict[str, Any]:
    signature_valid = _certificate_signature_is_valid(certificate)
    revoked_at = certificate.get("revoked_at")
    expiration_date = certificate.get("expiration_date")
    expires_at = _parse_iso_datetime(expiration_date)
    is_expired = bool(expires_at and expires_at < datetime.now(timezone.utc))
    is_revoked = bool(str(revoked_at or "").strip())

    if not signature_valid:
        status = CERTIFICATE_STATUS_INVALID
        label = "Invalid"
    elif is_revoked:
        status = CERTIFICATE_STATUS_REVOKED
        label = "Revoked"
    elif is_expired:
        status = CERTIFICATE_STATUS_EXPIRED
        label = "Expired"
    else:
        status = CERTIFICATE_STATUS_VALID
        label = "Valid"

    return {
        "status": status,
        "status_label": label,
        "is_active": status == CERTIFICATE_STATUS_VALID,
        "is_authentic": signature_valid,
        "is_revoked": is_revoked,
        "is_expired": is_expired,
        "expiration_date": expiration_date,
        "revoked_at": revoked_at,
    }


def _normalized_certificate_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    verification_id = str(row.get("verification_id") or "")
    lifecycle = _certificate_lifecycle(row)
    anchor_info = _normalize_anchoring_info(row.get("anchoring"))
    public_verify_url = _verification_public_url(verification_id)
    return {
        **row,
        "certificate_title": row.get("certificate_title") or row.get("course_title") or CERTIFICATE_CREDENTIAL_LABEL,
        "certificate_number": row.get("certificate_number") or row.get("certificate_id") or verification_id,
        "verify_url": public_verify_url,
        "public_verify_url": public_verify_url,
        "legacy_verify_endpoint": row.get("verify_url"),
        "public_pdf_url": _certificate_public_asset_url(verification_id, "pdf", "print") if verification_id else "",
        "public_png_url": _certificate_public_asset_url(verification_id, "png", "print") if verification_id else "",
        "preview_image_url": _certificate_public_asset_url(verification_id, "png", "web") if verification_id else "",
        "thumbnail_image_url": _certificate_public_asset_url(verification_id, "png", "thumb") if verification_id else "",
        "download_pdf_url": _certificate_public_asset_url(verification_id, "pdf", "print") if verification_id else "",
        "certificate_asset_version": CERTIFICATE_ASSET_VERSION,
        "certificate_render_profile_version": CERTIFICATE_RENDER_PROFILE_VERSION,
        "signer_name": row.get("signer_name") or CERTIFICATE_SIGNER_NAME,
        "signer_role": _normalized_certificate_signer_role(row.get("signer_role")),
        "credential_label": row.get("credential_label") or CERTIFICATE_CREDENTIAL_LABEL,
        "anchoring": anchor_info,
        "chain_anchored": anchor_info.get("status") == "anchored",
        "record_integrity_hash": row.get("immutable_payload_hash") or _certificate_record_hash(row),
        **lifecycle,
    }


async def _append_certificate_audit_log(
    certificate_doc: Dict[str, Any],
    event_type: str,
    actor_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    certificate_id = str(certificate_doc.get("certificate_id") or "")
    if not certificate_id:
        return
    await db.learn_hub_certificate_audit_log.insert_one(
        {
            "audit_id": f"cert_audit_{uuid.uuid4().hex[:12]}",
            "certificate_id": certificate_id,
            "verification_id": certificate_doc.get("verification_id"),
            "user_id": certificate_doc.get("user_id"),
            "course_id": certificate_doc.get("course_id"),
            "event_type": event_type,
            "actor_id": actor_id,
            "metadata": metadata or {},
            "created_at": _utcnow_iso(),
        }
    )


async def _course_certificate_policy(course_id: str) -> Dict[str, Any]:
    row = await db.learn_hub_courses.find_one(
        {"course_id": course_id},
        {"_id": 0, "title": 1, "certificate_validity_days": 1, "certificate_policy": 1},
    ) or {}
    validity_days = _default_certificate_validity_days(row)
    return {
        "title": row.get("title"),
        "validity_days": validity_days,
        "has_expiration": bool(validity_days),
        "policy": row.get("certificate_policy") or {},
    }


async def _ensure_certificate_record_shape(certificate_doc: Dict[str, Any]) -> Dict[str, Any]:
    if not certificate_doc:
        return {}
    course_policy = await _course_certificate_policy(str(certificate_doc.get("course_id") or ""))
    updates: Dict[str, Any] = {}
    issued_at = str(certificate_doc.get("issued_at") or _utcnow_iso())

    if not certificate_doc.get("certificate_number"):
        updates["certificate_number"] = _generate_certificate_number(
            str(certificate_doc.get("course_id") or "RAC"),
            str(certificate_doc.get("issued_at") or ""),
        )
    if not certificate_doc.get("certificate_title"):
        updates["certificate_title"] = certificate_doc.get("course_title") or CERTIFICATE_CREDENTIAL_LABEL
    if certificate_doc.get("issued_by") != CERTIFICATE_ISSUER_NAME:
        updates["issued_by"] = CERTIFICATE_ISSUER_NAME
    if (certificate_doc.get("signer_name") or "") != CERTIFICATE_SIGNER_NAME:
        updates["signer_name"] = CERTIFICATE_SIGNER_NAME
    if _normalized_certificate_signer_role(certificate_doc.get("signer_role")) != CERTIFICATE_SIGNER_ROLE:
        updates["signer_role"] = CERTIFICATE_SIGNER_ROLE
    if (certificate_doc.get("credential_label") or "") != CERTIFICATE_CREDENTIAL_LABEL:
        updates["credential_label"] = CERTIFICATE_CREDENTIAL_LABEL
    if not certificate_doc.get("expiration_date") and course_policy.get("validity_days"):
        issued_dt = _parse_iso_datetime(issued_at) or datetime.now(timezone.utc)
        updates["expiration_date"] = (issued_dt + timedelta(days=int(course_policy["validity_days"]))).isoformat()

    canonical_url = _verification_public_url(certificate_doc.get("verification_id", ""))
    if canonical_url and certificate_doc.get("verify_url") != canonical_url:
        updates["verify_url"] = canonical_url
    linkedin_url = f"https://www.linkedin.com/sharing/share-offsite/?url={quote(canonical_url, safe='')}" if canonical_url else ""
    if linkedin_url and certificate_doc.get("linkedin_share_url") != linkedin_url:
        updates["linkedin_share_url"] = linkedin_url

    merged = {**certificate_doc, **updates}
    record_hash = _certificate_record_hash(merged)
    if certificate_doc.get("immutable_payload_hash") != record_hash:
        updates["immutable_payload_hash"] = record_hash

    if updates and certificate_doc.get("certificate_id"):
        updates["updated_at"] = _utcnow_iso()
        await db.learn_hub_certificates.update_one(
            {"certificate_id": certificate_doc.get("certificate_id")},
            {"$set": updates},
        )
        merged = {**certificate_doc, **updates}
    return merged


def _normalized_certificate_signer_role(value: Optional[str]) -> str:
    role = str(value or "").strip()
    return CERTIFICATE_SIGNER_ROLE if role in LEGACY_CERTIFICATE_SIGNER_ROLES else role


def _ensure_certificate_signature_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "GreatVibesSignature"
    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except Exception:
        pass

    font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")
    os.makedirs(font_dir, exist_ok=True)
    font_path = os.path.join(font_dir, "GreatVibes-Regular.ttf")

    if not os.path.exists(font_path):
        font_url = "https://raw.githubusercontent.com/google/fonts/main/ofl/greatvibes/GreatVibes-Regular.ttf"
        with urlopen(font_url, timeout=20) as response:
            with open(font_path, "wb") as handle:
                handle.write(response.read())

    pdfmetrics.registerFont(TTFont(font_name, font_path))
    return font_name


def _normalize_anchoring_info(anchor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    record = anchor or {}
    live_meta = record.get("live_meta") or {}
    return {
        "status": record.get("status", "not_queued"),
        "mode": record.get("mode", ANCHOR_MODE),
        "chain_target": record.get("chain_target", ANCHOR_CHAIN_TARGET),
        "queued_at": record.get("queued_at"),
        "anchored_at": record.get("anchored_at"),
        "batch_id": record.get("batch_id"),
        "anchor_tx_hash": record.get("anchor_tx_hash"),
        "merkle_root": record.get("merkle_root"),
        "merkle_proof": record.get("merkle_proof"),
        "proof_index": record.get("proof_index"),
        "proof_total_leaves": record.get("proof_total_leaves"),
        "last_updated_at": record.get("last_updated_at"),
        "anchor_note": record.get("anchor_note", ""),
        "ots_receipt_sha256": record.get("ots_receipt_sha256") or live_meta.get("ots_receipt_sha256"),
        "ots_verification_status": record.get("ots_verification_status") or live_meta.get("ots_verification_status"),
    }


def _build_merkle_root(leaves: List[str]) -> str:
    if not leaves:
        return ""
    level = [hashlib.sha256(leaf.encode()).hexdigest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for idx in range(0, len(level), 2):
            combined = f"{level[idx]}{level[idx + 1]}"
            next_level.append(hashlib.sha256(combined.encode()).hexdigest())
        level = next_level
    return level[0]


def _build_merkle_proof(leaves: List[str], target_index: int) -> List[Dict[str, str]]:
    if target_index < 0 or target_index >= len(leaves):
        return []
    proof: List[Dict[str, str]] = []
    hashes = [hashlib.sha256(leaf.encode()).hexdigest() for leaf in leaves]
    idx = target_index
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        sibling_index = idx - 1 if idx % 2 == 1 else idx + 1
        sibling_position = "left" if idx % 2 == 1 else "right"
        if 0 <= sibling_index < len(hashes):
            proof.append({"position": sibling_position, "hash": hashes[sibling_index]})

        next_level = []
        for i in range(0, len(hashes), 2):
            next_level.append(hashlib.sha256(f"{hashes[i]}{hashes[i + 1]}".encode()).hexdigest())

        idx = idx // 2
        hashes = next_level
    return proof


def _sanitize_hex_payload(value: str) -> str:
    raw = str(value or "").strip().lower().replace("0x", "")
    if not raw:
        raw = hashlib.sha256(str(value or "").encode()).hexdigest()
    if len(raw) % 2 == 1:
        raw = f"0{raw}"
    return f"0x{raw[:512]}"


async def _send_live_polygon_anchor(merkle_root: str, batch_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    cli_path = str(cfg.get("ots_cli_path") or "ots")
    calendar_url = str(cfg.get("ots_calendar_url") or "").strip()

    if not (shutil.which(cli_path) or os.path.exists(cli_path)):
        return {"ok": False, "error": f"OpenTimestamps CLI not found: {cli_path}"}

    def _run(command: List[str]) -> Dict[str, Any]:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return {
            "code": int(completed.returncode),
            "stdout": str(completed.stdout or "").strip(),
            "stderr": str(completed.stderr or "").strip(),
        }

    try:
        with tempfile.TemporaryDirectory(prefix="ots_anchor_") as temp_dir:
            payload_path = os.path.join(temp_dir, "anchor_payload.txt")
            payload = {
                "batch_id": batch_id,
                "merkle_root": merkle_root,
                "chain_target": ANCHOR_CHAIN_TARGET,
                "created_at": _utcnow_iso(),
            }
            with open(payload_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))

            stamp_cmd = [cli_path, "stamp"]
            if calendar_url:
                stamp_cmd.extend(["-c", calendar_url])
            stamp_cmd.append(payload_path)

            stamp_res = await asyncio.to_thread(_run, stamp_cmd)
            if stamp_res["code"] != 0:
                return {"ok": False, "error": stamp_res["stderr"] or stamp_res["stdout"] or "ots_stamp_failed"}

            ots_path = f"{payload_path}.ots"
            if not os.path.exists(ots_path):
                return {"ok": False, "error": "ots_receipt_missing_after_stamp"}

            upgrade_res = await asyncio.to_thread(_run, [cli_path, "upgrade", ots_path])
            verify_res = await asyncio.to_thread(_run, [cli_path, "verify", ots_path])

            with open(ots_path, "rb") as proof_file:
                proof_bytes = proof_file.read()

            proof_sha256 = hashlib.sha256(proof_bytes).hexdigest()
            verification_status = "anchored" if verify_res["code"] == 0 else "pending_confirmation"

            return {
                "ok": True,
                "tx_hash": f"ots_{proof_sha256[:48]}",
                "block_number": None,
                "gas_used": None,
                "signer_address": "opentimestamps",
                "chain_id": None,
                "ots_receipt_b64": base64.b64encode(proof_bytes).decode(),
                "ots_receipt_sha256": proof_sha256,
                "ots_verification_status": verification_status,
                "ots_verify_output": verify_res.get("stdout") or verify_res.get("stderr") or "",
                "ots_upgrade_output": upgrade_res.get("stdout") or upgrade_res.get("stderr") or "",
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _mask_verification_id(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 10:
        return text
    return f"{text[:6]}...{text[-4:]}"


async def _queue_certificate_for_anchoring(certificate_doc: Dict[str, Any]) -> None:
    now = _utcnow_iso()
    cfg = _polygon_anchor_config()
    configured_mode = _configured_anchor_mode(cfg)
    certificate_id = certificate_doc.get("certificate_id")
    if not certificate_id:
        return

    existing_queue = await db.learn_hub_certificate_anchor_queue.find_one(
        {"certificate_id": certificate_id, "status": {"$in": ["pending", "anchored"]}},
        {"_id": 0, "queue_id": 1},
    )
    if existing_queue:
        return

    queue_doc = {
        "queue_id": f"anchor_queue_{uuid.uuid4().hex[:12]}",
        "certificate_id": certificate_id,
        "verification_id": certificate_doc.get("verification_id"),
        "validation_hash": certificate_doc.get("validation_hash"),
        "leaf_hash": certificate_doc.get("validation_hash"),
        "status": "pending",
        "mode": configured_mode,
        "chain_target": ANCHOR_CHAIN_TARGET,
        "retry_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.learn_hub_certificate_anchor_queue.insert_one({**queue_doc})


async def _backfill_anchor_queue_from_unqueued(limit: int = 120) -> int:
    rows = await db.learn_hub_certificates.find(
        {"$or": [{"anchoring.status": {"$exists": False}}, {"anchoring.status": "not_queued"}]},
        {"_id": 0},
    ).sort("issued_at", 1).limit(limit).to_list(limit)

    queued = 0
    now_iso = _utcnow_iso()
    mode = _configured_anchor_mode()
    for cert in rows:
        certificate_id = cert.get("certificate_id")
        if not certificate_id:
            continue
        await _queue_certificate_for_anchoring(cert)
        await db.learn_hub_certificates.update_one(
            {"certificate_id": certificate_id},
            {
                "$set": {
                    "anchoring": {
                        "status": "queued",
                        "mode": mode,
                        "chain_target": ANCHOR_CHAIN_TARGET,
                        "queued_at": now_iso,
                        "last_updated_at": now_iso,
                        "anchor_note": _anchor_note_for_mode(mode),
                    }
                }
            },
        )
        queued += 1
    return queued


async def process_certificate_anchor_batch(limit: int = 250, triggered_by: str = "manual") -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    cfg = _polygon_anchor_config()
    configured_mode = _configured_anchor_mode(cfg)

    backfilled = await _backfill_anchor_queue_from_unqueued(limit=120)
    pending_rows = await db.learn_hub_certificate_anchor_queue.find(
        {"status": "pending"},
        {"_id": 0},
    ).sort("created_at", 1).limit(limit).to_list(limit)

    if not pending_rows:
        return {
            "processed": 0,
            "anchored": 0,
            "backfilled": backfilled,
            "batch_id": None,
            "anchor_mode": configured_mode,
            "chain_target": ANCHOR_CHAIN_TARGET,
            "triggered_by": triggered_by,
            "anchored_at": now_iso,
        }

    leaf_hashes = [str(row.get("leaf_hash") or "") for row in pending_rows]
    merkle_root = _build_merkle_root(leaf_hashes)
    batch_id = f"anchor_batch_{uuid.uuid4().hex[:10]}"
    anchor_tx_hash = f"ots_{hashlib.sha256(f'{merkle_root}:{now_iso}'.encode()).hexdigest()[:48]}"
    live_meta: Dict[str, Any] = {}
    anchor_mode_used = configured_mode
    anchor_note = "Anchored via OpenTimestamps receipt"

    if configured_mode == "opentimestamps":
        live_result = await _send_live_polygon_anchor(merkle_root, batch_id, cfg)
        if live_result.get("ok"):
            anchor_mode_used = "opentimestamps"
            anchor_tx_hash = str(live_result.get("tx_hash") or anchor_tx_hash)
            live_meta = {
                "block_number": live_result.get("block_number"),
                "gas_used": live_result.get("gas_used"),
                "signer_address": live_result.get("signer_address"),
                "chain_id": live_result.get("chain_id"),
                "ots_receipt_b64": live_result.get("ots_receipt_b64"),
                "ots_receipt_sha256": live_result.get("ots_receipt_sha256"),
                "ots_verification_status": live_result.get("ots_verification_status"),
                "ots_verify_output": live_result.get("ots_verify_output"),
                "ots_upgrade_output": live_result.get("ots_upgrade_output"),
            }
            if str(live_result.get("ots_verification_status") or "") == "anchored":
                anchor_note = "Anchored via OpenTimestamps with verifiable Bitcoin attestation"
            else:
                anchor_note = "OpenTimestamps receipt created; awaiting Bitcoin attestation confirmation"
        else:
            error_message = str(live_result.get("error") or "opentimestamps_anchor_failed")
            for row in pending_rows:
                certificate_id = row.get("certificate_id")
                await db.learn_hub_certificate_anchor_queue.update_one(
                    {"queue_id": row.get("queue_id")},
                    {
                        "$set": {
                            "status": "failed",
                            "mode": "opentimestamps",
                            "last_error": error_message,
                            "updated_at": now_iso,
                        }
                    },
                )
                if certificate_id:
                    await db.learn_hub_certificates.update_one(
                        {"certificate_id": certificate_id},
                        {
                            "$set": {
                                "anchoring.status": "failed",
                                "anchoring.mode": "opentimestamps",
                                "anchoring.last_updated_at": now_iso,
                                "anchoring.anchor_note": f"OpenTimestamps anchoring failed: {error_message}",
                            }
                        },
                    )
            await db.learn_hub_anchor_runtime.update_one(
                {"key": "certificate_anchor_runtime"},
                {
                    "$set": {
                        "key": "certificate_anchor_runtime",
                        "mode": "opentimestamps",
                        "last_status": "failed",
                        "last_error": error_message,
                        "last_anchored_at": now_iso,
                        "updated_at": now_iso,
                    }
                },
                upsert=True,
            )
            return {
                "processed": len(pending_rows),
                "anchored": 0,
                "failed": len(pending_rows),
                "backfilled": backfilled,
                "batch_id": batch_id,
                "anchor_mode": "opentimestamps",
                "chain_target": ANCHOR_CHAIN_TARGET,
                "triggered_by": triggered_by,
                "anchored_at": now_iso,
                "error": error_message,
            }
    elif configured_mode == "disabled":
        error_message = "OpenTimestamps anchoring is disabled or OTS CLI is unavailable"
        for row in pending_rows:
            certificate_id = row.get("certificate_id")
            await db.learn_hub_certificate_anchor_queue.update_one(
                {"queue_id": row.get("queue_id")},
                {
                    "$set": {
                        "status": "failed",
                        "mode": "disabled",
                        "last_error": error_message,
                        "updated_at": now_iso,
                    }
                },
            )
            if certificate_id:
                await db.learn_hub_certificates.update_one(
                    {"certificate_id": certificate_id},
                    {
                        "$set": {
                            "anchoring.status": "failed",
                            "anchoring.mode": "disabled",
                            "anchoring.last_updated_at": now_iso,
                            "anchoring.anchor_note": error_message,
                        }
                    },
                )
        return {
            "processed": len(pending_rows),
            "anchored": 0,
            "failed": len(pending_rows),
            "backfilled": backfilled,
            "batch_id": batch_id,
            "anchor_mode": "disabled",
            "chain_target": ANCHOR_CHAIN_TARGET,
            "triggered_by": triggered_by,
            "anchored_at": now_iso,
            "error": error_message,
        }

    batch_doc = {
        "batch_id": batch_id,
        "mode": anchor_mode_used,
        "chain_target": ANCHOR_CHAIN_TARGET,
        "anchored_at": now_iso,
        "anchor_tx_hash": anchor_tx_hash,
        "merkle_root": merkle_root,
        "leaf_count": len(leaf_hashes),
        "triggered_by": triggered_by,
        "status": "anchored",
        "live_meta": live_meta,
    }
    await db.learn_hub_certificate_anchor_batches.insert_one({**batch_doc})

    for index, row in enumerate(pending_rows):
        queue_id = row.get("queue_id")
        certificate_id = row.get("certificate_id")
        proof = _build_merkle_proof(leaf_hashes, index)

        await db.learn_hub_certificate_anchor_queue.update_one(
            {"queue_id": queue_id},
            {
                "$set": {
                    "status": "anchored",
                    "batch_id": batch_id,
                    "anchor_tx_hash": anchor_tx_hash,
                    "merkle_root": merkle_root,
                    "merkle_proof": proof,
                    "proof_index": index,
                    "proof_total_leaves": len(leaf_hashes),
                    "mode": anchor_mode_used,
                    "last_error": None,
                    "live_meta": live_meta,
                    "ots_receipt_sha256": live_meta.get("ots_receipt_sha256"),
                    "ots_verification_status": live_meta.get("ots_verification_status"),
                    "anchored_at": now_iso,
                    "updated_at": now_iso,
                }
            },
        )

        if certificate_id:
            await db.learn_hub_certificates.update_one(
                {"certificate_id": certificate_id},
                {
                    "$set": {
                        "anchoring": {
                            "status": "anchored",
                            "mode": anchor_mode_used,
                            "chain_target": ANCHOR_CHAIN_TARGET,
                            "batch_id": batch_id,
                            "anchor_tx_hash": anchor_tx_hash,
                            "merkle_root": merkle_root,
                            "merkle_proof": proof,
                            "proof_index": index,
                            "proof_total_leaves": len(leaf_hashes),
                            "anchored_at": now_iso,
                            "live_meta": live_meta,
                            "ots_receipt_sha256": live_meta.get("ots_receipt_sha256"),
                            "ots_verification_status": live_meta.get("ots_verification_status"),
                            "last_updated_at": now_iso,
                            "anchor_note": anchor_note,
                        }
                    }
                },
            )

    await db.learn_hub_anchor_runtime.update_one(
        {"key": "certificate_anchor_runtime"},
        {
            "$set": {
                "key": "certificate_anchor_runtime",
                "last_batch_id": batch_id,
                "last_anchor_tx_hash": anchor_tx_hash,
                "last_anchored_at": now_iso,
                "last_leaf_count": len(leaf_hashes),
                "mode": anchor_mode_used,
                "last_status": "anchored",
                "last_error": None,
                "live_meta": live_meta,
                "chain_target": ANCHOR_CHAIN_TARGET,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    return {
        "processed": len(pending_rows),
        "anchored": len(pending_rows),
        "backfilled": backfilled,
        "batch_id": batch_id,
        "anchor_mode": anchor_mode_used,
        "chain_target": ANCHOR_CHAIN_TARGET,
        "anchor_tx_hash": anchor_tx_hash,
        "merkle_root": merkle_root,
        "live_meta": live_meta,
        "triggered_by": triggered_by,
        "anchored_at": now_iso,
    }


def _normalize_certificate_layout(layout: Optional[str]) -> str:
    return "landscape" if str(layout or "portrait").lower() == "landscape" else "portrait"


def _certificate_content_profile(orientation: str, page_width_mm: float, template: Dict[str, Any]) -> Dict[str, Any]:
    if orientation == "landscape":
        return {
            "logo_top_mm": 24.0,
            "logo_max_w_mm": 80.0,
            "logo_max_h_mm": 42.0,
            "intro_offset_mm": 9.0,
            "intro_font_size": 12.0,
            "name_offset_mm": 24.0,
            "name_font_size": 27.0,
            "name_min_font_size": 17.0,
            "name_max_width_mm": page_width_mm - 62.0,
            "body_side_margin_mm": 64.0,
            "body_offset_mm": 36.0,
            "body_font_size": 11.1,
            "body_line_gap_mm": 4.8,
            "body_max_lines": 2,
            "title_offset_mm": 48.0,
            "title_font_size": 17.5,
            "title_min_font_size": 13.0,
            "title_max_width_mm": page_width_mm - 70.0,
            "title_line_gap_mm": 6.4,
            "notes_offset_mm": 56.0,
            "notes_font_size": 9.6,
            "notes_line_gap_mm": 4.1,
            "notes_max_lines": 2,
            "meta_line_y_mm": 68.0,
            "col_width_mm": 62.0,
            "col_gap_mm": 24.0,
            "value_font_size": 10.6,
            "label_font_size": 9.6,
            "show_meta_cards": False,
            "footer_logo_x_mm": 30.0,
            "footer_logo_y_mm": 20.0,
            "footer_logo_w_mm": 40.0,
            "footer_logo_h_mm": 22.0,
            "signature_line_width_mm": 46.0,
            "signature_right_margin_mm": 40.0,
            "signature_y_mm": 30.0,
            "stamp_size_mm": 40.0,
            "stamp_y_mm": 19.0,
        }
    return {
        "logo_top_mm": 28.0,
        "logo_max_w_mm": 76.0,
        "logo_max_h_mm": 42.0,
        "intro_offset_mm": 10.0,
        "intro_font_size": 12.0,
        "name_offset_mm": 28.0,
        "name_font_size": 23.0,
        "name_min_font_size": 16.0,
        "name_max_width_mm": page_width_mm - 54.0,
        "body_side_margin_mm": 62.0,
        "body_offset_mm": 48.0,
        "body_font_size": 11.0,
        "body_line_gap_mm": 5.2,
        "body_max_lines": 3,
        "title_offset_mm": 70.0,
        "title_font_size": 17.0,
        "title_min_font_size": 12.0,
        "title_max_width_mm": page_width_mm - 56.0,
        "title_line_gap_mm": 7.0,
        "notes_offset_mm": 92.0,
        "notes_font_size": 10.5,
        "notes_line_gap_mm": 5.0,
        "notes_max_lines": 3,
        "meta_line_y_mm": 70.0,
        "col_width_mm": 46.0,
        "col_gap_mm": 20.0,
        "value_font_size": 10.5,
        "label_font_size": 8.7,
        "show_meta_cards": False,
        "footer_logo_x_mm": template["footer_logo_x_mm"],
        "footer_logo_y_mm": template["footer_logo_y_mm"],
        "footer_logo_w_mm": template["footer_logo_w_mm"],
        "footer_logo_h_mm": template["footer_logo_h_mm"],
        "signature_line_width_mm": template["signature_line_width_mm"],
        "signature_right_margin_mm": template["signature_right_margin_mm"],
        "signature_y_mm": template["signature_y_mm"],
        "stamp_size_mm": template["stamp_size_mm"],
        "stamp_y_mm": template["stamp_y_mm"],
    }


def _draw_certificate_meta_column(
    pdf: Any,
    *,
    center_x: float,
    value: str,
    label: str,
    meta_line_y: float,
    width_value: float,
    profile: Dict[str, Any],
    ink: Any,
    muted: Any,
    mm: float,
) -> None:
    from reportlab.lib import colors as reportlab_colors
    from reportlab.lib.utils import simpleSplit

    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", profile["value_font_size"])
    value_lines = simpleSplit(value, "Helvetica", profile["value_font_size"], width_value)
    for line_idx, line in enumerate(value_lines[:2]):
        pdf.drawCentredString(center_x, meta_line_y + ((9 - (line_idx * 4.2)) * mm), line)
    pdf.setStrokeColor(reportlab_colors.HexColor("#7C8797"))
    pdf.setLineWidth(1)
    pdf.line(center_x - (width_value / 2), meta_line_y + (2.5 * mm), center_x + (width_value / 2), meta_line_y + (2.5 * mm))
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", profile["label_font_size"])
    pdf.drawCentredString(center_x, meta_line_y - (4.8 * mm), label)


def _render_landscape_certificate_footer(
    pdf: Any,
    *,
    width: float,
    mm: float,
    template: Dict[str, Any],
    profile: Dict[str, Any],
    certificate_number: str,
    issued_label: str,
    expiration_label: str,
    signer_name: str,
    signer_role: str,
    signature_blue: Any,
    signature_font: str,
    signer_name_font: str,
    signer_role_font: str,
    signer_name_size: float,
    signer_role_size: float,
    name_fill: Any,
    role_fill: Any,
    ink: Any,
    muted: Any,
) -> None:
    from reportlab.lib import colors as reportlab_colors
    from reportlab.lib.utils import ImageReader, simpleSplit

    meta_line_y = profile["meta_line_y_mm"] * mm
    safe_left = 24 * mm
    safe_right = 24 * mm
    usable_width = width - safe_left - safe_right
    column_width = usable_width / 3
    column_centers = [safe_left + (column_width * (idx + 0.5)) for idx in range(3)]
    meta_width = column_width - (10 * mm)

    _draw_certificate_meta_column(pdf, center_x=column_centers[0], value=certificate_number, label="Certificate Number", meta_line_y=meta_line_y, width_value=meta_width, profile=profile, ink=ink, muted=muted, mm=mm)
    _draw_certificate_meta_column(pdf, center_x=column_centers[1], value=issued_label, label="Date of Certification", meta_line_y=meta_line_y, width_value=meta_width, profile=profile, ink=ink, muted=muted, mm=mm)
    _draw_certificate_meta_column(pdf, center_x=column_centers[2], value=expiration_label, label="Expiration Date", meta_line_y=meta_line_y, width_value=meta_width, profile=profile, ink=ink, muted=muted, mm=mm)

    footer_logo_w = template["footer_logo_w_mm"] * mm
    footer_logo_h = template["footer_logo_h_mm"] * mm
    footer_logo_x = column_centers[0] - (footer_logo_w / 2)
    footer_logo_y = 16 * mm
    stamp_width = profile["stamp_size_mm"] * mm
    stamp_center_x = column_centers[1]
    stamp_y = profile["stamp_y_mm"] * mm
    signature_width = template["signature_line_width_mm"] * mm
    signature_center_x = column_centers[2]
    signature_x = signature_center_x - (signature_width / 2)
    signature_y = template["signature_y_mm"] * mm
    signature_image_box_w = min(template["signature_image_width_mm"] * mm, signature_width - (4 * mm))
    signature_image_box_h = template["signature_image_height_mm"] * mm
    signature_center_x - (signature_image_box_w / 2)

    if os.path.exists(CERTIFICATE_CERTIFIED_STAMP_PATH):
        try:
            certified_stamp = ImageReader(CERTIFICATE_CERTIFIED_STAMP_PATH)
            pdf.drawImage(
                certified_stamp,
                stamp_center_x - (stamp_width / 2),
                stamp_y,
                width=stamp_width,
                height=stamp_width,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    if os.path.exists(CERTIFICATE_BRAND_LOGO_PATH):
        try:
            small_logo = ImageReader(CERTIFICATE_BRAND_LOGO_PATH)
            pdf.drawImage(
                small_logo,
                footer_logo_x,
                footer_logo_y,
                width=footer_logo_w,
                height=footer_logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    if not _draw_cropped_signature(
        pdf,
        center_x=signature_center_x,
        baseline_y=signature_y,
        box_w=signature_image_box_w,
        box_h=signature_image_box_h,
        mm=mm,
    ):
        pdf.saveState()
        pdf.translate(signature_center_x - (18 * mm), signature_y + (11 * mm))
        pdf.rotate(-4)
        pdf.setFillColor(signature_blue)
        pdf.setFont(signature_font, 36)
        pdf.drawString(0, 0, signer_name)
        pdf.restoreState()

    pdf.setStrokeColor(reportlab_colors.HexColor("#7C8797"))
    pdf.setLineWidth(1)
    pdf.line(signature_x, signature_y, signature_x + signature_width, signature_y)
    pdf.setFillColor(name_fill)
    pdf.setFont(signer_name_font, signer_name_size)
    pdf.drawString(signature_x, signature_y - (7 * mm), signer_name)
    role_lines = simpleSplit(signer_role, signer_role_font, signer_role_size, signature_width)
    pdf.setFillColor(role_fill)
    for idx, line in enumerate(role_lines[:2]):
        pdf.setFont(signer_role_font, signer_role_size)
        pdf.drawString(signature_x, signature_y - ((12 + (idx * 4.5)) * mm), line)


def _render_portrait_certificate_footer(
    pdf: Any,
    *,
    width: float,
    mm: float,
    template: Dict[str, Any],
    profile: Dict[str, Any],
    certificate_number: str,
    issued_label: str,
    expiration_label: str,
    signer_name: str,
    signer_role: str,
    signature_blue: Any,
    signature_font: str,
    signer_name_font: str,
    signer_role_font: str,
    signer_name_size: float,
    signer_role_size: float,
    name_fill: Any,
    role_fill: Any,
    ink: Any,
    muted: Any,
) -> None:
    from reportlab.lib import colors as reportlab_colors
    from reportlab.lib.utils import ImageReader, simpleSplit

    meta_line_y = profile["meta_line_y_mm"] * mm
    col_width = profile["col_width_mm"] * mm
    col_gap = profile["col_gap_mm"] * mm
    start_x = (width - ((col_width * 3) + (col_gap * 2))) / 2

    details = [
        (certificate_number, "Certificate Number"),
        (issued_label, "Date of Certification"),
        (expiration_label, "Expiration Date"),
    ]
    for idx, (value, label) in enumerate(details):
        col_x = start_x + (idx * (col_width + col_gap))
        _draw_certificate_meta_column(pdf, center_x=col_x + (col_width / 2), value=value, label=label, meta_line_y=meta_line_y, width_value=col_width, profile=profile, ink=ink, muted=muted, mm=mm)

    footer_logo_x = profile["footer_logo_x_mm"] * mm
    footer_logo_y = profile["footer_logo_y_mm"] * mm
    footer_logo_w = profile["footer_logo_w_mm"] * mm
    footer_logo_h = profile["footer_logo_h_mm"] * mm
    signature_width = profile["signature_line_width_mm"] * mm
    signature_x = width - signature_width - (profile["signature_right_margin_mm"] * mm)
    signature_y = profile["signature_y_mm"] * mm
    signature_image_box_w = template["signature_image_width_mm"] * mm
    signature_image_box_h = template["signature_image_height_mm"] * mm
    signature_image_box_x = signature_x + (template["signature_image_offset_x_mm"] * mm)
    stamp_width = profile["stamp_size_mm"] * mm

    footer_logo_render_w, _ = _fit_image_within_box(CERTIFICATE_BRAND_LOGO_PATH, footer_logo_w, footer_logo_h)
    footer_logo_visible_center_x = footer_logo_x + ((footer_logo_w - footer_logo_render_w) / 2) + (footer_logo_render_w * _image_visible_center_ratio_x(CERTIFICATE_BRAND_LOGO_PATH))
    signature_visible_center_x = signature_image_box_x + (signature_image_box_w / 2)
    stamp_center_x = ((footer_logo_visible_center_x + signature_visible_center_x) / 2) + (template["stamp_offset_x_mm"] * mm)

    if os.path.exists(CERTIFICATE_CERTIFIED_STAMP_PATH):
        try:
            certified_stamp = ImageReader(CERTIFICATE_CERTIFIED_STAMP_PATH)
            pdf.drawImage(
                certified_stamp,
                stamp_center_x - (stamp_width / 2),
                profile["stamp_y_mm"] * mm,
                width=stamp_width,
                height=stamp_width,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    if os.path.exists(CERTIFICATE_BRAND_LOGO_PATH):
        try:
            small_logo = ImageReader(CERTIFICATE_BRAND_LOGO_PATH)
            pdf.drawImage(small_logo, footer_logo_x, footer_logo_y, width=footer_logo_w, height=footer_logo_h, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    if not _draw_cropped_signature(
        pdf,
        center_x=signature_visible_center_x,
        baseline_y=signature_y,
        box_w=signature_image_box_w,
        box_h=signature_image_box_h,
        mm=mm,
    ):
        pdf.saveState()
        pdf.translate(signature_x + (5 * mm), signature_y + (11 * mm))
        pdf.rotate(-4)
        pdf.setFillColor(signature_blue)
        pdf.setFont(signature_font, 36)
        pdf.drawString(0, 0, signer_name)
        pdf.restoreState()

    pdf.setStrokeColor(reportlab_colors.HexColor("#7C8797"))
    pdf.setLineWidth(1)
    pdf.line(signature_x, signature_y, signature_x + signature_width, signature_y)
    pdf.setFillColor(name_fill)
    pdf.setFont(signer_name_font, signer_name_size)
    pdf.drawString(signature_x, signature_y - (7 * mm), signer_name)
    role_lines = simpleSplit(signer_role, signer_role_font, signer_role_size, signature_width)
    pdf.setFillColor(role_fill)
    for idx, line in enumerate(role_lines[:2]):
        pdf.setFont(signer_role_font, signer_role_size)
        pdf.drawString(signature_x, signature_y - ((12 + (idx * 4.5)) * mm), line)


def _build_certificate_pdf_bytes(
    certificate: Dict[str, Any],
    variant: str = "print",
    template_settings: Optional[Dict[str, Any]] = None,
    typography_preset: Optional[str] = None,
    layout: str = "portrait",
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    orientation = _normalize_certificate_layout(layout)
    page_size = landscape(A4) if orientation == "landscape" else A4
    width, height = page_size
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=page_size)

    learner_name = str(certificate.get("learner_name") or "Learner")
    course_title = str(certificate.get("course_title") or "AI Learning Course")
    certificate_title = str(certificate.get("certificate_title") or course_title or CERTIFICATE_CREDENTIAL_LABEL)
    certificate_number = str(certificate.get("certificate_number") or certificate.get("certificate_id") or certificate.get("verification_id") or "--")
    issued_label = _format_certificate_date(certificate.get("issued_at"))
    expiration_label = _format_certificate_date(certificate.get("expiration_date"))
    if expiration_label == "--":
        expiration_label = "Lifetime Validity"
    signer_name = str(certificate.get("signer_name") or CERTIFICATE_SIGNER_NAME)
    signer_role = _normalized_certificate_signer_role(certificate.get("signer_role"))

    # ── ZERO ASSUMPTIONS POLICY — reject fabricated signer identity ──
    # See /app/memory/ZERO_ASSUMPTIONS_POLICY.md. Signer block is legally
    # binding on the certificate; any fabricated name/role must hard-fail
    # rather than render.
    try:
        from utils.zero_assumptions import assert_no_fabrication
        assert_no_fabrication(
            {"signer_name": signer_name, "signer_role": signer_role,
             "issued_by": certificate.get("issued_by"),
             "learner_name": learner_name, "course_title": course_title},
            context="certificate_signer",
        )
    except Exception as _za_err:
        from utils.zero_assumptions import FabricatedDataViolation
        if isinstance(_za_err, FabricatedDataViolation):
            raise
        # On any non-policy error (e.g. import failure), log and continue —
        # never silently skip the guard: re-raise after logging.
        raise
    lifecycle = _certificate_lifecycle(certificate)
    template = _sanitize_certificate_template_settings(template_settings)
    typography = _certificate_typography_profile(typography_preset)

    signature_font = "Times-Italic"
    try:
        signature_font = _ensure_certificate_signature_font()
    except Exception:
        signature_font = "Times-Italic"

    paper = colors.HexColor("#FFFFFF")
    ink = colors.HexColor(CERTIFICATE_BRAND_PRIMARY)
    teal = colors.HexColor(CERTIFICATE_BRAND_TEAL)
    muted = colors.HexColor(CERTIFICATE_BRAND_MUTED)
    border = colors.HexColor(CERTIFICATE_BRAND_BORDER)
    signature_blue = colors.HexColor("#1E3A8A")

    def draw_border_chain() -> None:
        pdf.setLineCap(1)
        step = 12 * mm if orientation == "portrait" else 10.8 * mm
        chain_radius = 8 * mm
        chain_depth = 8 * mm if orientation == "portrait" else 7.2 * mm
        chain_margin = 15 * mm if orientation == "portrait" else 16 * mm
        top_y = height - chain_margin
        bottom_y = chain_margin
        left_x = chain_margin
        right_x = width - chain_margin
        pdf.setLineWidth(3.2 if orientation == "portrait" else 2.8)

        def draw_arc_row(start: float, end: float, fixed: float, horizontal: bool) -> None:
            distance = end - start
            count = max(1, int(distance // step))
            for idx in range(count + 1):
                color = teal if idx % 2 == 0 else colors.HexColor("#2196F3")
                pdf.setStrokeColor(color)
                offset = start + (idx * step)
                if horizontal:
                    pdf.arc(offset, fixed - (chain_depth * 0.6), offset + chain_radius, fixed + (chain_depth * 0.4), startAng=20, extent=300)
                else:
                    pdf.arc(fixed - (chain_depth * 0.6), offset, fixed + (chain_depth * 0.4), offset + chain_radius, startAng=110, extent=300)

        arc_start = 22 * mm if orientation == "portrait" else 28 * mm
        horizontal_end = width - ((30 if orientation == "portrait" else 28) * mm)
        vertical_end = height - ((30 if orientation == "portrait" else 28) * mm)
        draw_arc_row(arc_start, horizontal_end, top_y, True)
        draw_arc_row(arc_start, horizontal_end, bottom_y - (3 * mm), True)
        draw_arc_row(arc_start, vertical_end, left_x - (3 * mm), False)
        draw_arc_row(arc_start, vertical_end, right_x, False)

    def draw_logo(center_x: float, top_y: float, max_width: float, max_height: float) -> float:
        if os.path.exists(CERTIFICATE_BRAND_LOGO_PATH):
            try:
                logo = ImageReader(CERTIFICATE_BRAND_LOGO_PATH)
                raw_w, raw_h = logo.getSize()
                draw_w = min(max_width, max_height * (raw_w / max(raw_h, 1)))
                draw_h = draw_w * (raw_h / max(raw_w, 1))
                if draw_h > max_height:
                    draw_h = max_height
                    draw_w = draw_h * (raw_w / max(raw_h, 1))
                pdf.drawImage(
                    logo,
                    center_x - (draw_w / 2),
                    top_y - draw_h,
                    width=draw_w,
                    height=draw_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                return top_y - draw_h
            except Exception:
                pass
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", 26)
        pdf.drawCentredString(center_x, top_y - 12, "Real")
        pdf.setFillColor(teal)
        pdf.drawString(center_x + 8, top_y - 12, "AI")
        pdf.setFillColor(ink)
        pdf.drawString(center_x + 36, top_y - 12, "Coach")
        return top_y - 16

    pdf.setTitle(f"RealAICoach Certificate - {learner_name}")
    pdf.setAuthor(CERTIFICATE_ISSUER_NAME)
    pdf.setSubject(CERTIFICATE_CREDENTIAL_LABEL)
    pdf.setCreator(CERTIFICATE_ISSUER_NAME)
    pdf.setFillColor(paper)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)

    certificate_safe_top_y = height

    pdf.setStrokeColor(border)
    pdf.setLineWidth(1.2)
    inner_margin_mm = 11 if orientation == "portrait" else 16
    pdf.rect(inner_margin_mm * mm, inner_margin_mm * mm, width - ((inner_margin_mm * 2) * mm), height - ((inner_margin_mm * 2) * mm), stroke=1, fill=0)
    draw_border_chain()

    if lifecycle["status"] in {CERTIFICATE_STATUS_REVOKED, CERTIFICATE_STATUS_EXPIRED, CERTIFICATE_STATUS_INVALID}:
        watermark = {
            CERTIFICATE_STATUS_REVOKED: ("REVOKED", colors.HexColor("#F87171")),
            CERTIFICATE_STATUS_EXPIRED: ("EXPIRED", colors.HexColor("#FBBF24")),
            CERTIFICATE_STATUS_INVALID: ("INVALID", colors.HexColor("#FCA5A5")),
        }[lifecycle["status"]]
        pdf.saveState()
        pdf.translate(width / 2, height / 2)
        pdf.rotate(34)
        pdf.setFillColor(watermark[1])
        pdf.setFont("Helvetica-Bold", 40)
        pdf.drawCentredString(0, 0, watermark[0])
        pdf.restoreState()

    content_center_x = width / 2
    body_max_width = width - ((62 if orientation == "portrait" else 84) * mm)

    certificate_body_copy = (
        "has successfully completed all requirements and demonstrated the practical competency required for the RealAICoach certification listed below."
    )
    certificate_notes_copy = (
        "This credential confirms successful completion of the approved RealAICoach learning track, assessment gate, and enterprise-grade completion validation workflow."
    )

    profile = _certificate_content_profile(orientation, width / mm, template)

    body_max_width = width - ((profile["body_side_margin_mm"]) * mm)
    title_max_width = (profile["title_max_width_mm"]) * mm

    logo_top_y = min(
        height - (profile["logo_top_mm"] * mm),
        certificate_safe_top_y - (14 * mm),
    )
    logo_bottom_y = draw_logo(
        content_center_x,
        logo_top_y,
        profile["logo_max_w_mm"] * mm,
        profile["logo_max_h_mm"] * mm,
    )
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", profile["intro_font_size"])
    pdf.drawCentredString(content_center_x, logo_bottom_y - (profile["intro_offset_mm"] * mm), "RealAICoach hereby certifies that")

    name_font_size = profile["name_font_size"]
    while name_font_size > profile["name_min_font_size"] and stringWidth(learner_name.upper(), "Helvetica-Bold", name_font_size) > (profile["name_max_width_mm"] * mm):
        name_font_size -= 1
    pdf.setFont("Helvetica-Bold", name_font_size)
    pdf.drawCentredString(content_center_x, logo_bottom_y - (profile["name_offset_mm"] * mm), learner_name.upper())

    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", profile["body_font_size"])
    body_lines = simpleSplit(
        certificate_body_copy,
        "Helvetica",
        profile["body_font_size"],
        body_max_width,
    )
    body_y = logo_bottom_y - (profile["body_offset_mm"] * mm)
    for idx, line in enumerate(body_lines[: profile["body_max_lines"]]):
        pdf.drawCentredString(content_center_x, body_y - (idx * profile["body_line_gap_mm"] * mm), line)

    title_font_size = profile["title_font_size"]
    while title_font_size > profile["title_min_font_size"] and stringWidth(certificate_title, "Helvetica-Bold", title_font_size) > title_max_width:
        title_font_size -= 1
    title_lines = simpleSplit(certificate_title, "Helvetica-Bold", title_font_size, title_max_width)
    title_y = logo_bottom_y - (profile["title_offset_mm"] * mm)
    pdf.setFillColor(teal)
    pdf.setFont("Helvetica-Bold", title_font_size)
    for idx, line in enumerate(title_lines[:2]):
        pdf.drawCentredString(content_center_x, title_y - (idx * profile["title_line_gap_mm"] * mm), line)

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", profile["notes_font_size"])
    notes = simpleSplit(
        certificate_notes_copy,
        "Helvetica",
        profile["notes_font_size"],
        body_max_width,
    )
    notes_y = logo_bottom_y - (profile["notes_offset_mm"] * mm)
    for idx, line in enumerate(notes[: profile["notes_max_lines"]]):
        pdf.drawCentredString(content_center_x, notes_y - (idx * profile["notes_line_gap_mm"] * mm), line)

    role_fill = ink if str(typography.get("role_color") or "ink") == "ink" else muted
    name_fill = ink if str(typography.get("name_color") or "ink") == "ink" else muted
    signer_name_font = str(typography.get("name_font") or "Helvetica-Bold")
    signer_role_font = str(typography.get("role_font") or "Helvetica-Bold")
    signer_name_size = float(typography.get("name_size") or 10.0)
    signer_role_size = float(typography.get("role_size") or 10.0)

    if orientation == "landscape":
        _render_landscape_certificate_footer(
            pdf,
            width=width,
            mm=mm,
            template=template,
            profile=profile,
            certificate_number=certificate_number,
            issued_label=issued_label,
            expiration_label=expiration_label,
            signer_name=signer_name,
            signer_role=signer_role,
            signature_blue=signature_blue,
            signature_font=signature_font,
            signer_name_font=signer_name_font,
            signer_role_font=signer_role_font,
            signer_name_size=signer_name_size,
            signer_role_size=signer_role_size,
            name_fill=name_fill,
            role_fill=role_fill,
            ink=ink,
            muted=muted,
        )
    else:
        _render_portrait_certificate_footer(
            pdf,
            width=width,
            mm=mm,
            template=template,
            profile=profile,
            certificate_number=certificate_number,
            issued_label=issued_label,
            expiration_label=expiration_label,
            signer_name=signer_name,
            signer_role=signer_role,
            signature_blue=signature_blue,
            signature_font=signature_font,
            signer_name_font=signer_name_font,
            signer_role_font=signer_role_font,
            signer_name_size=signer_name_size,
            signer_role_size=signer_role_size,
            name_fill=name_fill,
            role_fill=role_fill,
            ink=ink,
            muted=muted,
        )

    pdf.showPage()
    pdf.save()
    certificate_id = str(certificate.get("certificate_id") or certificate.get("verification_id") or "certificate")
    return _return_learning_certificate_pdf_bytes(buf.getvalue(), f"ai_learning_certificate_{certificate_id}")


def _build_certificate_pdf_base64(
    certificate: Dict[str, Any],
    variant: str = "print",
    template_settings: Optional[Dict[str, Any]] = None,
    typography_preset: Optional[str] = None,
    layout: str = "portrait",
) -> str:
    return base64.b64encode(
        _build_certificate_pdf_bytes(
            certificate,
            variant=variant,
            template_settings=template_settings,
            typography_preset=typography_preset,
            layout=layout,
        )
    ).decode()


def _build_certificate_landscape_pdf_bytes(
    certificate: Dict[str, Any],
    variant: str = "print",
    template_settings: Optional[Dict[str, Any]] = None,
    typography_preset: Optional[str] = None,
) -> bytes:
    """Generate landscape PDF using the shared portrait-faithful certificate renderer."""
    return _build_certificate_pdf_bytes(
        certificate,
        variant=variant,
        template_settings=template_settings,
        typography_preset=typography_preset,
        layout="landscape",
    )


def _certificate_asset_headers(filename: str, disposition: str) -> Dict[str, str]:
    return {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Certificate-Render-Version": CERTIFICATE_RENDER_PROFILE_VERSION,
        "X-Certificate-Asset-Version": CERTIFICATE_ASSET_VERSION,
    }


def _build_certificate_png_bytes(
    certificate: Dict[str, Any],
    variant: str = "print",
    scale: float = 3.0,
    template_settings: Optional[Dict[str, Any]] = None,
    typography_preset: Optional[str] = None,
    layout: str = "portrait",
) -> bytes:
    import fitz

    try:
        requested_scale = float(scale)
    except Exception:
        requested_scale = 3.0
    safe_scale = max(1.5, min(requested_scale, 4.0))
    normalized_layout = "landscape" if str(layout or "portrait").lower() == "landscape" else "portrait"

    if normalized_layout == "landscape":
        pdf_bytes = _build_certificate_landscape_pdf_bytes(
            certificate,
            variant=variant,
            template_settings=template_settings,
            typography_preset=typography_preset,
        )
    else:
        pdf_bytes = _build_certificate_pdf_bytes(
            certificate,
            variant=variant,
            template_settings=template_settings,
            typography_preset=typography_preset,
            layout="portrait",
        )
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if document.page_count < 1:
            raise ValueError("Certificate PDF did not contain any pages")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(safe_scale, safe_scale), alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _certificate_asset_field(asset_type: str, variant: str) -> str:
    normalized_variant = str(variant or "print").lower()
    if asset_type == "pdf":
        return "print_pdf"
    if normalized_variant == "thumb":
        return "thumbnail_png"
    if normalized_variant == "web":
        return "web_png"
    return "print_png"


def _certificate_render_key(
    certificate: Dict[str, Any],
    template_settings: Optional[Dict[str, Any]] = None,
    typography_preset: Optional[str] = None,
) -> str:
    lifecycle = _certificate_lifecycle(certificate)
    payload = {
        "template_version": CERTIFICATE_TEMPLATE_VERSION,
        "render_profile_version": CERTIFICATE_RENDER_PROFILE_VERSION,
        "signature_profile_version": CERTIFICATE_SIGNATURE_PROFILE_VERSION,
        "footer_profile_version": CERTIFICATE_FOOTER_PROFILE_VERSION,
        "template_settings": _sanitize_certificate_template_settings(template_settings),
        "typography_preset": _sanitize_certificate_typography_preset(typography_preset),
        "verification_id": certificate.get("verification_id"),
        "certificate_number": certificate.get("certificate_number"),
        "certificate_title": certificate.get("certificate_title") or certificate.get("course_title"),
        "issued_at": certificate.get("issued_at"),
        "expiration_date": certificate.get("expiration_date"),
        "revoked_at": certificate.get("revoked_at"),
        "status": lifecycle.get("status"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:14]


def _certificate_storage_prefix(certificate: Dict[str, Any]) -> str:
    return (
        f"{STORAGE_APP_PREFIX}/certificates/"
        f"{str(certificate.get('user_id') or 'system').strip()}/"
        f"{str(certificate.get('verification_id') or uuid.uuid4().hex).strip()}"
    )


async def _sync_certificate_storage_assets(certificate_doc: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    existing = certificate_doc.get("storage_assets") or {}
    template_record = await _get_certificate_template_settings()
    template_settings = template_record.get("settings") or {}
    typography_preset = _sanitize_certificate_typography_preset(template_record.get("typography_preset"))
    if not storage_is_enabled():
        return existing

    render_key = _certificate_render_key(
        certificate_doc,
        template_settings=template_settings,
        typography_preset=typography_preset,
    )
    required_fields = ["print_pdf", "print_png", "web_png", "thumbnail_png"]
    if (
        not force
        and existing.get("template_version") == CERTIFICATE_TEMPLATE_VERSION
        and existing.get("render_key") == render_key
        and all(bool((existing.get(field) or {}).get("storage_path")) for field in required_fields)
    ):
        return existing

    prefix = _certificate_storage_prefix(certificate_doc)
    now_iso = _utcnow_iso()
    print_pdf_bytes = await asyncio.to_thread(
        _build_certificate_pdf_bytes,
        certificate_doc,
        "print",
        template_settings,
        typography_preset,
    )
    print_png_bytes = await asyncio.to_thread(
        _build_certificate_png_bytes,
        certificate_doc,
        "print",
        3.0,
        template_settings,
        typography_preset,
    )
    web_png_bytes = await asyncio.to_thread(
        _build_certificate_png_bytes,
        certificate_doc,
        "web",
        1.9,
        template_settings,
        typography_preset,
    )
    thumb_png_bytes = await asyncio.to_thread(
        _build_certificate_png_bytes,
        certificate_doc,
        "thumb",
        1.2,
        template_settings,
        typography_preset,
    )

    print_pdf_result = await asyncio.to_thread(storage_put_bytes, f"{prefix}/{render_key}/certificate-print.pdf", print_pdf_bytes, "application/pdf")
    print_png_result = await asyncio.to_thread(storage_put_bytes, f"{prefix}/{render_key}/certificate-print.png", print_png_bytes, "image/png")
    web_png_result = await asyncio.to_thread(storage_put_bytes, f"{prefix}/{render_key}/certificate-web.png", web_png_bytes, "image/png")
    thumb_png_result = await asyncio.to_thread(storage_put_bytes, f"{prefix}/{render_key}/certificate-thumb.png", thumb_png_bytes, "image/png")

    if not all([print_pdf_result, print_png_result, web_png_result, thumb_png_result]):
        return existing

    manifest_payload = {
        "certificate_id": certificate_doc.get("certificate_id"),
        "verification_id": certificate_doc.get("verification_id"),
        "certificate_number": certificate_doc.get("certificate_number"),
        "template_version": CERTIFICATE_TEMPLATE_VERSION,
        "render_key": render_key,
        "status": _certificate_lifecycle(certificate_doc).get("status"),
        "generated_at": now_iso,
        "assets": {
            "print_pdf": print_pdf_result.get("path"),
            "print_png": print_png_result.get("path"),
            "web_png": web_png_result.get("path"),
            "thumbnail_png": thumb_png_result.get("path"),
        },
    }
    manifest_result = await asyncio.to_thread(storage_put_json, f"{prefix}/{render_key}/manifest.json", manifest_payload)

    assets = {
        "template_version": CERTIFICATE_TEMPLATE_VERSION,
        "render_key": render_key,
        "updated_at": now_iso,
        "manifest": {"storage_path": manifest_result.get("path") if manifest_result else "", "content_type": "application/json"},
        "print_pdf": {"storage_path": print_pdf_result.get("path"), "content_type": "application/pdf"},
        "print_png": {"storage_path": print_png_result.get("path"), "content_type": "image/png"},
        "web_png": {"storage_path": web_png_result.get("path"), "content_type": "image/png"},
        "thumbnail_png": {"storage_path": thumb_png_result.get("path"), "content_type": "image/png"},
    }

    if certificate_doc.get("certificate_id"):
        await db.learn_hub_certificates.update_one(
            {"certificate_id": certificate_doc.get("certificate_id")},
            {"$set": {"storage_assets": assets, "updated_at": now_iso}},
        )
    try:
        await _append_certificate_audit_log(certificate_doc, "assets_synced", "system", {"render_key": render_key})
    except Exception:
        pass
    return assets


async def _load_certificate_asset_bytes(certificate_doc: Dict[str, Any], asset_type: str, variant: str, layout: str = "portrait") -> tuple[bytes, str]:
    certificate_doc = await _ensure_certificate_record_shape(certificate_doc)
    assets = await _sync_certificate_storage_assets(certificate_doc, force=False)
    template_record = await _get_certificate_template_settings()
    template_settings = template_record.get("settings") or {}
    typography_preset = _sanitize_certificate_typography_preset(template_record.get("typography_preset"))
    normalized_layout = "landscape" if str(layout or "portrait").lower() == "landscape" else "portrait"
    field = _certificate_asset_field(asset_type, variant)
    storage_path = str((assets.get(field) or {}).get("storage_path") or "").strip()
    assets_are_current = (
        (assets.get("template_version") == CERTIFICATE_TEMPLATE_VERSION)
        and (
            assets.get("render_key")
            == _certificate_render_key(
                certificate_doc,
                template_settings=template_settings,
                typography_preset=typography_preset,
            )
        )
    )
    if asset_type == "pdf" and normalized_layout == "landscape":
        return (
            _build_certificate_landscape_pdf_bytes(
                certificate_doc,
                variant=variant,
                template_settings=template_settings,
                typography_preset=typography_preset,
            ),
            "application/pdf",
        )

    if asset_type == "png" and normalized_layout == "landscape":
        scale = 3.0
        if str(variant or "").lower() == "web":
            scale = 1.9
        elif str(variant or "").lower() == "thumb":
            scale = 1.2
        return (
            _build_certificate_png_bytes(
                certificate_doc,
                variant=variant,
                scale=scale,
                template_settings=template_settings,
                typography_preset=typography_preset,
                layout=normalized_layout,
            ),
            "image/png",
        )

    if storage_path and assets_are_current:
        stored = await asyncio.to_thread(storage_get_bytes, storage_path)
        if stored:
            return stored

    if asset_type == "pdf":
        return (
            _build_certificate_pdf_bytes(
                certificate_doc,
                variant=variant,
                template_settings=template_settings,
                typography_preset=typography_preset,
                layout=normalized_layout,
            ),
            "application/pdf",
        )

    scale = 3.0
    if str(variant or "").lower() == "web":
        scale = 1.9
    elif str(variant or "").lower() == "thumb":
        scale = 1.2
    return (
        _build_certificate_png_bytes(
            certificate_doc,
            variant=variant,
            scale=scale,
            template_settings=template_settings,
            typography_preset=typography_preset,
            layout=normalized_layout,
        ),
        "image/png",
    )

CATALOG = [
    {
        "id": "ai-ml",
        "name": "AI & Machine Learning",
        "icon": "hardware-chip",
        "color": "#8B5CF6",
        "topics": ["Neural Networks", "NLP", "Computer Vision", "Reinforcement Learning", "LLMs", "Prompt Engineering"],
    },
    {
        "id": "programming",
        "name": "Programming",
        "icon": "code-slash",
        "color": "#3B82F6",
        "topics": ["Python", "JavaScript", "TypeScript", "Go", "Rust", "System Design"],
    },
    {
        "id": "business",
        "name": "Business & Strategy",
        "icon": "briefcase",
        "color": "#10B981",
        "topics": ["Startups", "Marketing", "Sales", "Leadership", "Product Management", "Finance"],
    },
    {
        "id": "data-science",
        "name": "Data Science",
        "icon": "analytics",
        "color": "#F59E0B",
        "topics": ["Statistics", "Data Visualization", "SQL", "Pandas", "Big Data", "A/B Testing"],
    },
    {
        "id": "design",
        "name": "Design & UX",
        "icon": "color-palette",
        "color": "#EC4899",
        "topics": ["UI Design", "UX Research", "Figma", "Design Systems", "Accessibility", "Typography"],
    },
    {
        "id": "cybersecurity",
        "name": "Cybersecurity",
        "icon": "shield-checkmark",
        "color": "#EF4444",
        "topics": [
            "Network Security",
            "Ethical Hacking",
            "Cryptography",
            "OWASP",
            "Cloud Security",
            "Incident Response",
        ],
    },
    {
        "id": "cloud",
        "name": "Cloud & DevOps",
        "icon": "cloud",
        "color": "#06B6D4",
        "topics": ["AWS", "Docker", "Kubernetes", "CI/CD", "Terraform", "Monitoring"],
    },
    {
        "id": "soft-skills",
        "name": "Soft Skills",
        "icon": "people",
        "color": "#F97316",
        "topics": [
            "Communication",
            "Negotiation",
            "Time Management",
            "Critical Thinking",
            "Public Speaking",
            "Conflict Resolution",
        ],
    },
]


class GenerateLesson(BaseModel):
    category_id: str
    topic: str
    difficulty: str = "intermediate"  # beginner, intermediate, advanced
    custom_topic: Optional[str] = None


@router.get("/catalog")
async def get_catalog(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    # Get user's lesson counts per category
    user_lessons = await db.learn_lessons.find(
        {"user_id": user.user_id}, {"_id": 0, "category_id": 1, "completed": 1}
    ).to_list(200)
    cat_stats = {}
    for lesson_row in user_lessons:
        cid = lesson_row.get("category_id", "")
        if cid not in cat_stats:
            cat_stats[cid] = {"total": 0, "completed": 0}
        cat_stats[cid]["total"] += 1
        if lesson_row.get("completed"):
            cat_stats[cid]["completed"] += 1

    catalog_with_stats = []
    for c in CATALOG:
        stats = cat_stats.get(c["id"], {"total": 0, "completed": 0})
        catalog_with_stats.append({**c, "user_lessons": stats["total"], "user_completed": stats["completed"]})
    return {"catalog": catalog_with_stats}


@router.post("/generate-lesson")
async def generate_lesson(request: Request, body: GenerateLesson):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    topic = body.custom_topic or body.topic
    system_msg = f"""You are an expert educator creating a {body.difficulty}-level lesson.
Return ONLY valid JSON:
{{
  "title": "Lesson title",
  "summary": "2-3 sentence overview",
  "learning_objectives": ["objective 1", "objective 2", "objective 3"],
  "sections": [
    {{
      "heading": "Section heading",
      "content": "Detailed educational content (3-5 paragraphs, use markdown)",
      "key_points": ["point 1", "point 2"],
      "example": "A practical example or code snippet if relevant"
    }}
  ],
  "practical_exercise": {{
    "title": "Exercise title",
    "description": "What to do",
    "steps": ["step 1", "step 2"]
  }},
  "further_reading": ["Resource 1", "Resource 2"],
  "estimated_time_minutes": 15
}}"""
    prompt = f"Create a comprehensive {body.difficulty}-level lesson about: {topic}\nCategory: {body.category_id}\nMake it engaging, practical, and thorough."

    try:
        lesson_data = await ai_generate_json(system_msg, prompt, f"learn-{uuid.uuid4().hex[:8]}")
    except Exception as e:
        logger.error(f"Lesson generation error: {e}")
        lesson_data = {
            "title": f"Introduction to {topic}",
            "summary": f"An overview of {topic} fundamentals.",
            "learning_objectives": [f"Understand the basics of {topic}", "Apply key concepts"],
            "sections": [
                {
                    "heading": "Overview",
                    "content": f"This lesson covers the fundamentals of {topic}.",
                    "key_points": ["Core concepts"],
                    "example": "See the practical exercise below.",
                }
            ],
            "practical_exercise": {
                "title": "Practice",
                "description": f"Research and summarize 3 key aspects of {topic}",
                "steps": ["Research online", "Take notes", "Summarize findings"],
            },
            "further_reading": [f"Official documentation for {topic}"],
            "estimated_time_minutes": 15,
        }

    # Track usage
    try:
        await db.usage_analytics.insert_one(
            {
                "user_id": user.user_id,
                "feature_id": "ai-learning-hub",
                "tool_id": body.category_id,
                "action": "generate-lesson",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()
    lesson = {
        "lesson_id": f"lesson_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "category_id": body.category_id,
        "topic": topic,
        "difficulty": body.difficulty,
        "completed": False,
        "quiz_score": None,
        **lesson_data,
        "created_at": now,
        "updated_at": now,
    }
    await db.learn_lessons.insert_one(lesson)
    return {k: v for k, v in lesson.items() if k != "_id"}


@router.get("/my-lessons")
async def my_lessons(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    lessons = (
        await db.learn_lessons.find(
            {"user_id": user.user_id}, {"_id": 0, "sections": 0, "practical_exercise": 0, "further_reading": 0}
        )
        .sort("updated_at", -1)
        .to_list(50)
    )
    return {"lessons": lessons}


@router.get("/lessons/{lesson_id}")
async def get_lesson(request: Request, lesson_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    lesson = await db.learn_lessons.find_one({"lesson_id": lesson_id, "user_id": user.user_id}, {"_id": 0})
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    return lesson


@router.post("/lessons/{lesson_id}/quiz")
async def generate_quiz(request: Request, lesson_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    lesson = await db.learn_lessons.find_one({"lesson_id": lesson_id, "user_id": user.user_id}, {"_id": 0})
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    content_summary = (
        lesson.get("title", "") + " " + " ".join([s.get("content", "")[:200] for s in lesson.get("sections", [])])
    )

    system_msg = """You are a quiz generator. Create a quiz based on the lesson content.
Return ONLY valid JSON:
{
  "questions": [
    {
      "id": 1,
      "question": "Question text",
      "options": ["A) option", "B) option", "C) option", "D) option"],
      "correct": 0,
      "explanation": "Why this is correct"
    }
  ]
}"""
    prompt = (
        f"Lesson: {content_summary[:1500]}\n\nCreate 5 multiple-choice questions testing understanding of key concepts:"
    )

    try:
        quiz = await ai_generate_json(system_msg, prompt, f"quiz-{lesson_id[:8]}")
    except Exception as e:
        logger.error(f"Quiz generation error: {e}")
        quiz = {
            "questions": [
                {
                    "id": 1,
                    "question": "What is the main topic of this lesson?",
                    "options": [f"A) {lesson.get('topic', 'Topic')}", "B) Unrelated", "C) None", "D) All"],
                    "correct": 0,
                    "explanation": "This was the main subject.",
                }
            ]
        }

    await db.learn_lessons.update_one({"lesson_id": lesson_id}, {"$set": {"quiz": quiz}})
    return quiz


@router.post("/lessons/{lesson_id}/complete")
async def complete_lesson(request: Request, lesson_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    body = await request.json()
    quiz_score = body.get("quiz_score")

    result = await db.learn_lessons.update_one(
        {"lesson_id": lesson_id, "user_id": user.user_id},
        {
            "$set": {
                "completed": True,
                "quiz_score": quiz_score,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Lesson not found")
    return {"success": True, "completed": True, "quiz_score": quiz_score}


class AutoGenerateCourseRequest(BaseModel):
    topic: str
    category: str = "AI"
    difficulty: str = "intermediate"
    objective: Optional[str] = None


class ProgressUpdateRequest(BaseModel):
    module_id: str
    completed: bool = True
    minutes_spent: int = 15


class RoadmapRequest(BaseModel):
    target_role: str
    current_skills: List[str] = []
    timeline_months: int = 6


class SandboxRequest(BaseModel):
    prompt: str
    language: str = "python"
    code: Optional[str] = None


class MentorMatchRequest(BaseModel):
    objective: str
    timezone: Optional[str] = None
    preferred_focus: Optional[str] = None


class HabitCheckInRequest(BaseModel):
    mood_score: int = Field(default=3, ge=1, le=5)
    focus_score: int = Field(default=3, ge=1, le=5)
    blocker: Optional[str] = None
    available_minutes: int = Field(default=30, ge=5, le=240)


class CareerSprintSolveRequest(BaseModel):
    challenge_title: str
    objective: str
    context: Optional[str] = None
    weekly_hours: int = Field(default=6, ge=2, le=40)
    income_goal: Optional[str] = None


class StreakInsuranceRedeemRequest(BaseModel):
    target_day: Optional[str] = None


class RecoveryCopilotApplyRequest(BaseModel):
    action_id: str
    objective: Optional[str] = None


class IncomeExperimentCreateRequest(BaseModel):
    title: str
    hypothesis: str
    execution_plan: Optional[str] = None
    effort_hours: int = Field(default=3, ge=1, le=40)


class IncomeExperimentLogRequest(BaseModel):
    status: str = Field(default="active")
    revenue_delta: float = 0
    insight: Optional[str] = None


class AssessmentSubmitRequest(BaseModel):
    answers: Dict[str, int] = Field(default_factory=dict)


class LessonWatchStateRequest(BaseModel):
    watch_seconds: float = Field(default=0, ge=0)
    total_seconds: Optional[float] = Field(default=None, ge=0)
    last_position_seconds: Optional[float] = Field(default=None, ge=0)
    completed: bool = False


class LessonTelemetryEventRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: f"session_{uuid.uuid4().hex[:12]}")
    event_type: str
    position_seconds: float = Field(default=0, ge=0)
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    seek_delta_seconds: Optional[float] = None


class KpiRouteViewRequest(BaseModel):
    kpi_id: str
    route_path: Optional[str] = None
    source: Optional[str] = "ui"


class RemediationActionRequest(BaseModel):
    action_type: str
    lesson_id: Optional[str] = None
    material_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def _verification_public_url(verification_id: str) -> str:
    base = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
    path = f"/certificate-verify/{verification_id}"
    return f"{base}{path}" if base else path


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "learning-hub"


def _current_week_key(dt: Optional[datetime] = None) -> str:
    current = dt or datetime.now(timezone.utc)
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _normalize_video_lessons(course_id: str, topic: str, lessons: Any, min_count: int = 5) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen_urls = set()
    topic_slug = _slugify(topic)

    if isinstance(lessons, list):
        for idx, row in enumerate(lessons):
            if not isinstance(row, dict):
                continue
            lesson_title = str(row.get("title") or f"{topic.title()} Session {idx + 1}")
            fallback_url = str(row.get("fallback_url") or row.get("url") or row.get("youtube_url") or "").strip()
            alignment = _video_topic_alignment_meta(topic, lesson_title, fallback_url)
            source_url = fallback_url
            if not fallback_url or alignment.get("status") != "aligned":
                fallback_url = str(alignment.get("recommended_url") or "").strip()
            if not fallback_url:
                continue
            if fallback_url in seen_urls:
                continue
            seen_urls.add(fallback_url)
            lesson_id = str(row.get("lesson_id") or f"v{idx + 1}").strip() or f"v{idx + 1}"
            normalized.append(
                {
                    "lesson_id": lesson_id,
                    "title": lesson_title,
                    "provider": str(row.get("provider") or DEFAULT_VIDEO_PROVIDER),
                    "duration_min": max(5, int(row.get("duration_min") or 18)),
                    "storage_path": str(row.get("storage_path") or f"{STORAGE_APP_PREFIX}/course-videos/{topic_slug}/{course_id}/{lesson_id}.mp4"),
                    "fallback_url": fallback_url,
                    "playback_url": fallback_url,
                    "source_fallback_url": source_url if source_url and source_url != fallback_url else None,
                    "health_status": str(row.get("health_status") or "pending"),
                    "topic_alignment_score": float(alignment.get("score") or 0),
                    "topic_alignment_status": str(alignment.get("status") or "low_confidence"),
                    "last_checked_at": row.get("last_checked_at"),
                }
            )

    library_offset = int(hashlib.sha1(f"{course_id}:{topic}".encode()).hexdigest()[:6], 16)
    idx = 0
    while len(normalized) < min_count:
        item = VIDEO_FALLBACK_LIBRARY[(library_offset + idx) % len(VIDEO_FALLBACK_LIBRARY)]
        idx += 1
        lesson_title = f"{item.get('title')} · {topic.title()}"
        fallback_url = _build_topic_video_search_url(topic, lesson_title)
        if not fallback_url or fallback_url in seen_urls:
            continue
        seen_urls.add(fallback_url)
        lesson_id = f"v{len(normalized) + 1}"
        alignment = _video_topic_alignment_meta(topic, lesson_title, fallback_url)
        normalized.append(
            {
                "lesson_id": lesson_id,
                "title": lesson_title,
                "provider": DEFAULT_VIDEO_PROVIDER,
                "duration_min": int(item.get("duration_min") or 18),
                "storage_path": f"{STORAGE_APP_PREFIX}/course-videos/{topic_slug}/{course_id}/{lesson_id}.mp4",
                "fallback_url": fallback_url,
                "playback_url": fallback_url,
                "source_fallback_url": str(item.get("url") or "") or None,
                "health_status": "fallback",
                "topic_alignment_score": float(alignment.get("score") or 0),
                "topic_alignment_status": str(alignment.get("status") or "fallback_search"),
                "last_checked_at": None,
            }
        )

    return normalized[: max(min_count, len(normalized))]


def _normalize_modules(modules: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if isinstance(modules, list):
        for idx, row in enumerate(modules):
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "module_id": str(row.get("module_id") or f"m{idx + 1}"),
                    "title": str(row.get("title") or f"Module {idx + 1}"),
                    "learning_outcome": str(row.get("learning_outcome") or "Deliver practical measurable outcomes"),
                    "estimated_minutes": max(15, int(row.get("estimated_minutes") or 45)),
                }
            )
    if not rows:
        rows = [
            {"module_id": "m1", "title": "Foundations", "learning_outcome": "Build baseline understanding", "estimated_minutes": 45},
            {"module_id": "m2", "title": "Applied Workflow", "learning_outcome": "Run practical execution loops", "estimated_minutes": 55},
            {"module_id": "m3", "title": "Real-World Delivery", "learning_outcome": "Ship value with confidence", "estimated_minutes": 60},
        ]
    return rows


def _normalize_learning_materials(course_id: str, topic: str, modules: List[Dict[str, Any]], materials: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if isinstance(materials, list):
        for idx, row in enumerate(materials):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            action_steps = row.get("action_steps") if isinstance(row.get("action_steps"), list) else []
            normalized.append(
                {
                    "material_id": str(row.get("material_id") or f"mat_{idx + 1}"),
                    "title": title,
                    "material_type": str(row.get("material_type") or "guide"),
                    "summary": str(row.get("summary") or "Practical learning resource for this course."),
                    "estimated_minutes": max(5, int(row.get("estimated_minutes") or 18)),
                    "action_steps": [str(step).strip() for step in action_steps if str(step).strip()][:6],
                    "resource_url": str(row.get("resource_url") or "").strip() or None,
                }
            )

    if len(normalized) >= 4:
        return normalized[:8]

    fallback_steps = [
        "Read the core concept summary and capture one key insight.",
        "Apply the concept to a real scenario in your role.",
        "Document outcomes and blockers in your learning journal.",
        "Share your implementation with a peer or mentor for feedback.",
    ]
    module_titles = [str(m.get("title") or f"Module {i + 1}") for i, m in enumerate(modules)]
    if not module_titles:
        module_titles = ["Foundations", "Execution", "Delivery"]

    while len(normalized) < 4:
        index = len(normalized)
        module_title = module_titles[index % len(module_titles)]
        normalized.append(
            {
                "material_id": f"mat_auto_{index + 1}",
                "title": f"{topic.title()} • {module_title} Practical Brief",
                "material_type": "playbook" if index % 2 == 0 else "worksheet",
                "summary": f"Applied resource to execute {module_title.lower()} for {topic}.",
                "estimated_minutes": 12 + index * 4,
                "action_steps": fallback_steps[:],
                "resource_url": None,
            }
        )

    return normalized[:8]


def _normalize_final_assessment(course_id: str, topic: str, modules: List[Dict[str, Any]], assessment: Any) -> Dict[str, Any]:
    fallback_questions: List[Dict[str, Any]] = []
    for idx, module in enumerate((modules or [])[:5]):
        module_title = str(module.get("title") or f"Module {idx + 1}")
        fallback_questions.append(
            {
                "question_id": f"q{idx + 1}",
                "question": f"What is the best way to apply '{module_title}' in a real-world {topic} workflow?",
                "options": [
                    "Define measurable outcomes and run a small implementation sprint",
                    "Skip planning and jump directly to random experimentation",
                    "Avoid stakeholder feedback until final delivery",
                    "Delay execution until every dependency is perfect",
                ],
                "correct_option_index": 0,
                "explanation": "Practical execution with measurable outcomes is the fastest path to skill transfer.",
            }
        )

    if not fallback_questions:
        fallback_questions = [
            {
                "question_id": "q1",
                "question": f"Which habit best improves long-term mastery in {topic}?",
                "options": [
                    "Consistent weekly practice with reflection",
                    "Only watching videos without application",
                    "Skipping checkpoints to finish faster",
                    "Ignoring feedback loops",
                ],
                "correct_option_index": 0,
                "explanation": "Consistency and reflection drive durable learning outcomes.",
            }
        ]

    normalized_questions: List[Dict[str, Any]] = []
    if isinstance(assessment, dict):
        raw_questions = assessment.get("questions") if isinstance(assessment.get("questions"), list) else []
        for idx, row in enumerate(raw_questions):
            if not isinstance(row, dict):
                continue
            question = str(row.get("question") or "").strip()
            options = row.get("options") if isinstance(row.get("options"), list) else []
            cleaned_options = [str(opt).strip() for opt in options if str(opt).strip()]
            if not question or len(cleaned_options) < 2:
                continue
            correct_index = int(row.get("correct_option_index") if row.get("correct_option_index") is not None else row.get("correct", 0))
            correct_index = max(0, min(correct_index, len(cleaned_options) - 1))
            normalized_questions.append(
                {
                    "question_id": str(row.get("question_id") or row.get("id") or f"q{idx + 1}"),
                    "question": question,
                    "options": cleaned_options[:5],
                    "correct_option_index": correct_index,
                    "explanation": str(row.get("explanation") or "Review the core concept and retry."),
                }
            )

    if len(normalized_questions) < 4:
        normalized_questions = fallback_questions

    passing_score_pct = 70
    if isinstance(assessment, dict):
        try:
            passing_score_pct = int(assessment.get("passing_score_pct") or 70)
        except Exception:
            passing_score_pct = 70
    passing_score_pct = max(50, min(95, passing_score_pct))

    return {
        "assessment_id": str((assessment or {}).get("assessment_id") or f"assessment_{course_id}") if isinstance(assessment, dict) else f"assessment_{course_id}",
        "title": str((assessment or {}).get("title") or "Final Mastery Checkpoint") if isinstance(assessment, dict) else "Final Mastery Checkpoint",
        "passing_score_pct": passing_score_pct,
        "questions": normalized_questions[:6],
    }


def _normalize_assessment_state(existing: Any, required: bool) -> Dict[str, Any]:
    base = existing if isinstance(existing, dict) else {}
    return {
        "required": bool(required),
        "passed": bool(base.get("passed")) if required else True,
        "score_pct": float(base.get("score_pct") or (100 if not required else 0)),
        "attempts": int(base.get("attempts") or 0),
        "last_submitted_at": base.get("last_submitted_at"),
        "passed_at": base.get("passed_at"),
        "active_remediation": base.get("active_remediation") if isinstance(base.get("active_remediation"), dict) else None,
        "last_remediation_outcome": base.get("last_remediation_outcome") if isinstance(base.get("last_remediation_outcome"), dict) else None,
    }


def _normalize_roadmap_content(roadmap: Dict[str, Any], target_role: str, timeline_months: int) -> Dict[str, Any]:
    target_weeks = max(4, int(timeline_months) * 4)
    phases = roadmap.get("phases") if isinstance(roadmap.get("phases"), list) else []
    normalized_phases: List[Dict[str, Any]] = []
    for idx, phase in enumerate(phases):
        if not isinstance(phase, dict):
            continue
        try:
            duration_weeks = int(phase.get("duration_weeks") or 2)
        except Exception:
            duration_weeks = 2
        duration_weeks = max(1, duration_weeks)
        goals = phase.get("goals") if isinstance(phase.get("goals"), list) else []
        recommended_courses = phase.get("recommended_courses") if isinstance(phase.get("recommended_courses"), list) else []
        normalized_phases.append(
            {
                "phase": str(phase.get("phase") or f"Phase {idx + 1}"),
                "duration_weeks": duration_weeks,
                "goals": [str(g).strip() for g in goals if str(g).strip()][:6],
                "recommended_courses": [str(c).strip() for c in recommended_courses if str(c).strip()][:6],
            }
        )

    if not normalized_phases:
        normalized_phases = [
            {
                "phase": "Foundation",
                "duration_weeks": max(2, target_weeks // 3),
                "goals": ["Master core concepts", "Set measurable weekly cadence"],
                "recommended_courses": ["Enterprise AI Foundations for Builders"],
            },
            {
                "phase": "Applied Execution",
                "duration_weeks": max(2, target_weeks // 3),
                "goals": ["Complete practical project checkpoints", "Document repeatable workflow"],
                "recommended_courses": ["Applied Cybersecurity for AI Teams"],
            },
            {
                "phase": "Portfolio & Outcome Delivery",
                "duration_weeks": max(2, target_weeks - (2 * max(2, target_weeks // 3))),
                "goals": ["Ship final case study", "Prepare certification and portfolio evidence"],
                "recommended_courses": ["AI for Growth, Marketing & Revenue"],
            },
        ]

    current_total = sum(max(1, int(phase.get("duration_weeks") or 1)) for phase in normalized_phases)
    if current_total != target_weeks and normalized_phases:
        delta = target_weeks - current_total
        normalized_phases[-1]["duration_weeks"] = max(1, int(normalized_phases[-1].get("duration_weeks") or 1) + delta)

    weekly_execution = []
    week_counter = 1
    for phase in normalized_phases:
        weeks_in_phase = max(1, int(phase.get("duration_weeks") or 1))
        goals = phase.get("goals") or []
        for local_week in range(weeks_in_phase):
            goal = goals[local_week % len(goals)] if goals else "Execute one measurable milestone"
            weekly_execution.append(
                {
                    "week": week_counter,
                    "phase": phase.get("phase"),
                    "focus": goal,
                    "checkpoint": f"Deliver evidence for week {week_counter} outcomes",
                }
            )
            week_counter += 1

    try:
        weekly_commitment = int(roadmap.get("weekly_commitment_hours") or 6)
    except Exception:
        weekly_commitment = 6

    return {
        "title": str(roadmap.get("title") or f"{target_role} Career Roadmap"),
        "timeline_months": int(roadmap.get("timeline_months") or timeline_months),
        "weekly_commitment_hours": max(2, min(40, weekly_commitment)),
        "phases": normalized_phases,
        "key_milestones": [
            str(m).strip()
            for m in (roadmap.get("key_milestones") if isinstance(roadmap.get("key_milestones"), list) else [])
            if str(m).strip()
        ][:8],
        "weekly_execution": weekly_execution,
        "total_duration_weeks": len(weekly_execution),
    }


def _format_duration_mmss(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except Exception:
        total = 0
    mins = total // 60
    secs = total % 60
    return f"{mins}:{secs:02d}"


async def _store_course_manifest(course_doc: Dict[str, Any]) -> Optional[str]:
    week_key = str(course_doc.get("auto_publish_week") or _current_week_key())
    course_id = str(course_doc.get("course_id") or uuid.uuid4().hex[:10])
    path = f"{STORAGE_APP_PREFIX}/course-manifests/{week_key}/{course_id}.json"
    payload = {
        "course_id": course_id,
        "title": course_doc.get("title"),
        "category": course_doc.get("category"),
        "difficulty": course_doc.get("difficulty"),
        "video_lessons": course_doc.get("video_lessons") or [],
        "modules": course_doc.get("modules") or [],
        "generated_at": _utcnow_iso(),
    }
    result = await asyncio.to_thread(storage_put_json, path, payload)
    if not result:
        return None
    return str(result.get("path") or path)


async def _generate_enterprise_course_doc(
    topic: str,
    category: str,
    difficulty: str,
    objective: Optional[str],
    created_by: str,
    publish_source: str = "manual",
    auto_publish_week: Optional[str] = None,
) -> Dict[str, Any]:
    fallback = {
        "title": f"{topic.title()} Enterprise Accelerator",
        "overview": f"Enterprise-grade {difficulty} program for {topic} with real-world execution and measurable outcomes.",
        "adaptive_path": "career-impact-loop",
        "duration_hours": 8,
        "skills": [topic, "Execution", "Revenue", "Productivity"],
        "video_lessons": [
            {"lesson_id": "v1", "title": "Strategic Foundations", "provider": DEFAULT_VIDEO_PROVIDER, "duration_min": 18, "fallback_url": VIDEO_FALLBACK_LIBRARY[0]["url"]},
            {"lesson_id": "v2", "title": "Execution Framework", "provider": DEFAULT_VIDEO_PROVIDER, "duration_min": 20, "fallback_url": VIDEO_FALLBACK_LIBRARY[1]["url"]},
            {"lesson_id": "v3", "title": "Real-World Playbook", "provider": DEFAULT_VIDEO_PROVIDER, "duration_min": 22, "fallback_url": VIDEO_FALLBACK_LIBRARY[2]["url"]},
            {"lesson_id": "v4", "title": "Monetization Sprint", "provider": DEFAULT_VIDEO_PROVIDER, "duration_min": 24, "fallback_url": VIDEO_FALLBACK_LIBRARY[3]["url"]},
            {"lesson_id": "v5", "title": "Performance Optimization", "provider": DEFAULT_VIDEO_PROVIDER, "duration_min": 20, "fallback_url": VIDEO_FALLBACK_LIBRARY[4]["url"]},
        ],
        "modules": [
            {"module_id": "m1", "title": "Core System", "learning_outcome": "Build strong conceptual baseline", "estimated_minutes": 45},
            {"module_id": "m2", "title": "Applied Execution", "learning_outcome": "Apply skills to practical work", "estimated_minutes": 55},
            {"module_id": "m3", "title": "Career Outcome Sprint", "learning_outcome": "Produce portfolio + income signal", "estimated_minutes": 65},
        ],
        "learning_materials": [
            {
                "material_id": "mat1",
                "title": "Execution Canvas",
                "material_type": "worksheet",
                "summary": "Map your current state, target state, and measurable milestones.",
                "estimated_minutes": 18,
                "action_steps": [
                    "Define one measurable learning outcome",
                    "Identify blockers and dependencies",
                    "Plan a 3-day implementation cycle",
                ],
            },
            {
                "material_id": "mat2",
                "title": "Applied Practice Checklist",
                "material_type": "playbook",
                "summary": "Turn theory into a repeatable workflow for your role.",
                "estimated_minutes": 14,
                "action_steps": [
                    "Run one small practical task",
                    "Capture result quality",
                    "Iterate with feedback",
                ],
            },
        ],
        "final_assessment": {
            "title": "Final Mastery Checkpoint",
            "passing_score_pct": 70,
            "questions": [
                {
                    "question_id": "q1",
                    "question": "Which execution strategy creates reliable learning outcomes?",
                    "options": [
                        "Complete checkpoints and validate results weekly",
                        "Skip feedback and rely on intuition only",
                        "Consume content without practical tasks",
                        "Change goals daily without measurement",
                    ],
                    "correct_option_index": 0,
                    "explanation": "Checkpoint + validation loops are essential for durable mastery.",
                }
            ],
        },
    }
    system_message = """You are an enterprise learning architect.
Return valid JSON only with keys:
title, overview, adaptive_path, duration_hours, skills(array), video_lessons(array), modules(array), learning_materials(array), final_assessment(object).
Requirements:
- video_lessons must contain at least 5 items.
- each video lesson item includes: lesson_id, title, provider, duration_min, fallback_url.
- modules should be practical and outcome-focused.
- learning_materials must include at least 4 practical resources with: title, material_type, summary, estimated_minutes, action_steps(array).
- final_assessment must include passing_score_pct and at least 4 multiple-choice questions. Each question: question_id, question, options(array), correct_option_index, explanation.
"""
    prompt = f"""Create a globally relevant premium learning course.
Topic: {topic}
Category: {category}
Difficulty: {difficulty}
Objective: {objective or 'career growth, productivity, and income generation'}

Mandatory constraints:
- 5 to 8 video lessons
- 4 to 7 modules
- include tangible real-world deliverables
- include outcome language for career and income impact
"""
    ai_course = await _ask_gpt_52_json(system_message, prompt, "learnhub-enterprise-weekly", fallback)

    now = _utcnow_iso()
    course_id = f"course_{uuid.uuid4().hex[:12]}"
    video_lessons = _normalize_video_lessons(course_id, topic, ai_course.get("video_lessons"), min_count=5)
    modules = _normalize_modules(ai_course.get("modules"))
    learning_materials = _normalize_learning_materials(course_id, topic, modules, ai_course.get("learning_materials"))
    final_assessment = _normalize_final_assessment(course_id, topic, modules, ai_course.get("final_assessment"))
    course_doc = {
        "course_id": course_id,
        "title": str(ai_course.get("title") or fallback["title"]),
        "category": category,
        "subcategory": topic,
        "difficulty": difficulty,
        "overview": str(ai_course.get("overview") or fallback["overview"]),
        "adaptive_path": str(ai_course.get("adaptive_path") or fallback["adaptive_path"]),
        "duration_hours": max(3, int(ai_course.get("duration_hours") or fallback["duration_hours"])),
        "skills": ai_course.get("skills") if isinstance(ai_course.get("skills"), list) else fallback["skills"],
        "video_lessons": video_lessons,
        "modules": modules,
        "learning_materials": learning_materials,
        "final_assessment": final_assessment,
        "featured": False,
        "auto_generated": True,
        "seeded": False,
        "publish_source": publish_source,
        "auto_publish_week": auto_publish_week,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    manifest_path = await _store_course_manifest(course_doc)
    if manifest_path:
        course_doc["storage_manifest_path"] = manifest_path
    await db.learn_hub_courses.insert_one({**course_doc})
    return course_doc


async def _notify_weekly_course_publication(course_docs: List[Dict[str, Any]], week_key: str, triggered_by: str) -> Dict[str, Any]:
    if not course_docs:
        return {"in_app": 0, "emails": 0}
    now_iso = _utcnow_iso()
    users = await db.users.find(
        {"access_locked": {"$ne": True}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "is_admin": 1},
    ).to_list(5000)
    title = f"{len(course_docs)} new AI Learning Hub courses are now live"
    course_names = [str(c.get('title') or 'Course') for c in course_docs]

    # Use the registered V7 template (same pipeline as Integrity Report, etc.)
    from utils.email_templates import build_learning_hub_weekly_release_email
    tpl = build_learning_hub_weekly_release_email(week_key=week_key, courses=course_names)
    v7_subject = tpl.subject
    v7_html = tpl.html

    in_app_sent = 0
    email_queued = 0
    seen_user_ids = set()
    seen_emails = set()
    email_docs: List[Dict[str, Any]] = []
    for user in users:
        uid = str(user.get("user_id") or "")
        email = str(user.get("email") or "").strip()
        if uid and uid not in seen_user_ids:
            seen_user_ids.add(uid)
            try:
                await emit_notification(
                    user_id=uid,
                    notif_type="learning_hub_weekly_release",
                    title=title,
                    body=f"{len(course_docs)} new courses were published this week.",
                    action_url="/ai-learning-hub",
                    metadata={"week_key": week_key, "course_ids": [c.get("course_id") for c in course_docs]},
                    send_email_notification=False,
                )
                in_app_sent += 1
            except Exception:
                pass
        if email and email not in seen_emails:
            seen_emails.add(email)
            email_docs.append(
                {
                    "queue_id": f"lh_email_{uuid.uuid4().hex[:12]}",
                    "event_type": "weekly_course_release",
                    "recipient_email": email,
                    "recipient_name": user.get("name") or "Learner",
                    "subject": v7_subject,
                    "content": v7_html,
                    "template_key": "learning_hub_weekly_release",
                    "status": "pending",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "v7_rendered": True,
                }
            )

    if email_docs:
        try:
            await db.learn_hub_email_queue.insert_many(email_docs)
            email_queued = len(email_docs)
        except Exception:
            email_queued = 0

    await db.learn_hub_weekly_publish_history.insert_one(
        {
            "publish_id": f"lh_weekly_publish_{uuid.uuid4().hex[:10]}",
            "week_key": week_key,
            "course_ids": [c.get("course_id") for c in course_docs],
            "course_count": len(course_docs),
            "triggered_by": triggered_by,
            "in_app_sent": in_app_sent,
            "emails_queued": email_queued,
            "created_at": now_iso,
        }
    )
    return {"in_app": in_app_sent, "emails_queued": email_queued}


async def ensure_weekly_course_publication(triggered_by: str = "scheduler:weekly") -> Dict[str, Any]:
    week_key = _current_week_key()
    existing = await db.learn_hub_courses.find(
        {"auto_publish_week": week_key, "publish_source": "weekly_automation"},
        {"_id": 0, "course_id": 1, "title": 1, "subcategory": 1},
    ).to_list(50)
    existing_topics = {str(c.get("subcategory") or "").strip().lower() for c in existing}

    needed = max(0, 5 - len(existing))
    created: List[Dict[str, Any]] = []
    if needed > 0:
        for idx in range(needed):
            topic_seed = WEEKLY_AUTOPUBLISH_TOPICS[(int(hashlib.sha1(week_key.encode()).hexdigest()[:8], 16) + idx) % len(WEEKLY_AUTOPUBLISH_TOPICS)]
            if topic_seed.strip().lower() in existing_topics:
                topic_seed = f"{topic_seed} Advanced"
            course = await _generate_enterprise_course_doc(
                topic=topic_seed,
                category="AI",
                difficulty="intermediate",
                objective="career growth, skill compounding, and income outcomes",
                created_by="system_weekly_engine",
                publish_source="weekly_automation",
                auto_publish_week=week_key,
            )
            created.append(course)

    notify_result = await _notify_weekly_course_publication(created, week_key, triggered_by) if created else {"in_app": 0, "emails": 0}
    runtime = {
        "key": "learning_hub_weekly_course_runtime",
        "week_key": week_key,
        "target_count": 5,
        "existing_count": len(existing),
        "created_count": len(created),
        "total_count": len(existing) + len(created),
        "created_course_ids": [c.get("course_id") for c in created],
        "notification": notify_result,
        "triggered_by": triggered_by,
        "updated_at": _utcnow_iso(),
    }
    await db.learn_hub_automation_runtime.update_one(
        {"key": "learning_hub_weekly_course_runtime"},
        {"$set": runtime},
        upsert=True,
    )
    return runtime


async def _check_url_available(url: str, timeout_seconds: int = 8) -> bool:
    if not str(url or "").startswith("http"):
        return False
    try:
        def _do_head(target: str):
            try:
                return requests.head(target, allow_redirects=True, timeout=timeout_seconds)
            except Exception:
                return requests.get(target, allow_redirects=True, timeout=max(timeout_seconds + 1, 6))

        resp = await asyncio.to_thread(_do_head, url)
        return int(resp.status_code) < 400
    except Exception:
        return False


async def validate_and_repair_learning_hub_videos(
    limit: int = 500,
    max_lessons_per_course: int = 5,
    request_timeout_seconds: int = 8,
) -> Dict[str, Any]:
    effective_limit = max(1, min(int(limit or 1), 160))
    lesson_cap = max(1, min(int(max_lessons_per_course or 1), 5))
    total_courses = await db.learn_hub_courses.count_documents({})
    rotation_key = "learning_hub_video_validation_rotation"
    rotation = await db.learn_hub_video_validation_runtime.find_one({"key": rotation_key}, {"_id": 0}) or {}
    offset = int(rotation.get("offset", 0) or 0)
    if total_courses <= 0:
        return {
            "checked_courses": 0,
            "checked_lessons": 0,
            "repaired_courses": 0,
            "repaired_lessons": 0,
            "broken_links": 0,
            "topic_mismatch_lessons": 0,
            "topic_repaired_lessons": 0,
            "topic_alignment_pct": 100,
            "checked_at": _utcnow_iso(),
            "coverage": {
                "total_courses": 0,
                "window_start": 0,
                "window_size": 0,
                "next_offset": 0,
            },
        }

    # Keep rotating windows even on mid-sized catalogs; avoid scanning 100% every cycle.
    if total_courses > 12:
        rolling_cap = max(8, int(total_courses * 0.55))
        effective_limit = min(effective_limit, rolling_cap)

    offset = max(0, min(offset, max(0, total_courses - 1)))
    first_chunk = await db.learn_hub_courses.find({}, {"_id": 0}).sort("updated_at", -1).skip(offset).limit(effective_limit).to_list(effective_limit)
    rows = list(first_chunk)
    if len(rows) < effective_limit and total_courses > len(rows):
        needed = effective_limit - len(rows)
        second_chunk = await db.learn_hub_courses.find({}, {"_id": 0}).sort("updated_at", -1).skip(0).limit(needed).to_list(needed)
        existing_ids = {str(r.get("course_id") or "") for r in rows}
        for row in second_chunk:
            cid = str(row.get("course_id") or "")
            if cid in existing_ids:
                continue
            rows.append(row)
            existing_ids.add(cid)

    repaired_courses = 0
    repaired_lessons = 0
    checked_lessons = 0
    broken_links = 0
    topic_mismatch_lessons = 0
    topic_repaired_lessons = 0
    now = _utcnow_iso()

    for course in rows:
        course_id = str(course.get("course_id") or "")
        topic = str(course.get("subcategory") or course.get("title") or "AI")
        lessons = _normalize_video_lessons(course_id, topic, course.get("video_lessons"), min_count=5)

        mutated = len(lessons) != len(course.get("video_lessons") or [])
        for lesson in lessons[:lesson_cap]:
            checked_lessons += 1
            fallback_url = str(lesson.get("fallback_url") or "")

            alignment = _video_topic_alignment_meta(topic, str(lesson.get("title") or ""), fallback_url)
            if alignment.get("status") != "aligned":
                topic_mismatch_lessons += 1
                replacement_url = str(alignment.get("recommended_url") or "").strip()
                if replacement_url and replacement_url != fallback_url:
                    lesson["source_fallback_url"] = fallback_url
                    lesson["fallback_url"] = replacement_url
                    lesson["playback_url"] = replacement_url
                    lesson["health_status"] = "repaired-topic-alignment"
                    fallback_url = replacement_url
                    repaired_lessons += 1
                    topic_repaired_lessons += 1
                    mutated = True

            ok = await _check_url_available(fallback_url, timeout_seconds=request_timeout_seconds)
            if not ok:
                broken_links += 1
                replacement = _normalize_video_lessons(
                    course_id,
                    topic,
                    [{"title": lesson.get("title") or f"{topic.title()} session"}],
                    min_count=1,
                )[0]
                lesson["fallback_url"] = replacement.get("fallback_url")
                lesson["playback_url"] = replacement.get("fallback_url")
                lesson["health_status"] = "repaired-fallback"
                repaired_lessons += 1
                mutated = True
            else:
                lesson["health_status"] = "ok"

            refreshed_alignment = _video_topic_alignment_meta(topic, str(lesson.get("title") or ""), str(lesson.get("fallback_url") or ""))
            lesson["topic_alignment_score"] = float(refreshed_alignment.get("score") or 0)
            lesson["topic_alignment_status"] = str(refreshed_alignment.get("status") or "low_confidence")
            lesson["last_checked_at"] = now

        if mutated:
            repaired_courses += 1
            await db.learn_hub_courses.update_one(
                {"course_id": course_id},
                {"$set": {"video_lessons": lessons, "updated_at": now}},
            )

    checked_count = len(rows)
    next_offset = (offset + checked_count) % max(1, total_courses)
    window_end = (offset + checked_count - 1) % max(1, total_courses) if checked_count > 0 else offset
    await db.learn_hub_video_validation_runtime.update_one(
        {"key": rotation_key},
        {
            "$set": {
                "key": rotation_key,
                "offset": next_offset,
                "window_start": offset,
                "window_end": window_end,
                "window_size": checked_count,
                "total_courses": total_courses,
                "checked_lessons": checked_lessons,
                "broken_links": broken_links,
                "repaired_lessons": repaired_lessons,
                "topic_mismatch_lessons": topic_mismatch_lessons,
                "topic_repaired_lessons": topic_repaired_lessons,
                "topic_alignment_pct": round(((checked_lessons - topic_mismatch_lessons) / max(checked_lessons, 1)) * 100, 2),
                "updated_at": now,
            }
        },
        upsert=True,
    )

    return {
        "checked_courses": checked_count,
        "checked_lessons": checked_lessons,
        "repaired_courses": repaired_courses,
        "repaired_lessons": repaired_lessons,
        "broken_links": broken_links,
        "topic_mismatch_lessons": topic_mismatch_lessons,
        "topic_repaired_lessons": topic_repaired_lessons,
        "topic_alignment_pct": round(((checked_lessons - topic_mismatch_lessons) / max(checked_lessons, 1)) * 100, 2),
        "checked_at": now,
        "coverage": {
            "total_courses": total_courses,
            "window_start": offset,
            "window_end": window_end,
            "window_size": checked_count,
            "next_offset": next_offset,
        },
    }


async def run_learning_hub_assurance_cycle(triggered_by: str = "manual") -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    health_score = None
    health_grade = None
    health_issues = None
    frontend_ok = False
    frontend_status = None
    api_checks: List[Dict[str, Any]] = []

    try:
        from routes.platform_health import scan_platform_health

        admin_ctx = type("_ctx", (), {"user_id": "scheduler_admin", "email": "admin@realaicoach.app", "is_admin": True})()
        scan = await scan_platform_health(admin_ctx)
        health_score = scan.get("score")
        health_grade = scan.get("grade")
        health_issues = scan.get("total_issues")
    except Exception:
        pass

    frontend_base = str(os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
    if frontend_base:
        try:
            resp = await asyncio.to_thread(requests.get, f"{frontend_base}/ai-learning-hub", timeout=12)
            frontend_status = int(resp.status_code)
            html_text = str(resp.text or "")
            frontend_ok = frontend_status < 500 and "<body" in html_text and len(html_text.strip()) > 500
        except Exception:
            frontend_ok = False

        for path, expected in [
            ("/api/health", 200),
            ("/api/ai-learn/courses", 401),
            ("/api/ai-learn/hub-dashboard", 401),
        ]:
            status_code = None
            ok = False
            error = None
            try:
                check_resp = await asyncio.to_thread(requests.get, f"{frontend_base}{path}", timeout=10)
                status_code = int(check_resp.status_code)
                ok = status_code == expected
            except Exception as exc:
                error = str(exc)
            api_checks.append({"path": path, "expected": expected, "status_code": status_code, "ok": ok, "error": error})

    assurance_video_limit = 120
    assurance_lesson_cap = 3
    assurance_timeout = 6
    trigger_text = str(triggered_by or "").lower()
    if "enterprise-standard" in trigger_text or "global-assurance" in trigger_text:
        assurance_video_limit = 40
        assurance_lesson_cap = 2
        assurance_timeout = 5
    elif "scheduler:15min" in trigger_text:
        assurance_video_limit = 80
        assurance_lesson_cap = 3
        assurance_timeout = 5

    video_report = await validate_and_repair_learning_hub_videos(
        limit=assurance_video_limit,
        max_lessons_per_course=assurance_lesson_cap,
        request_timeout_seconds=assurance_timeout,
    )
    weekly_report = await ensure_weekly_course_publication(triggered_by=f"{triggered_by}:assurance")

    status = "healthy"
    failed_api_checks = sum(1 for x in api_checks if not x.get("ok"))
    if (health_score is not None and int(health_score) < 90) or not frontend_ok or int(video_report.get("broken_links", 0) or 0) > 0 or int(video_report.get("topic_mismatch_lessons", 0) or 0) > 0 or failed_api_checks > 0:
        status = "warning"

    assurance_doc = {
        "run_id": f"lh_assurance_{uuid.uuid4().hex[:10]}",
        "triggered_by": triggered_by,
        "run_at": now_iso,
        "status": status,
        "platform_health": {
            "score": health_score,
            "grade": health_grade,
            "issues": health_issues,
        },
        "frontend": {
            "ok": frontend_ok,
            "status_code": frontend_status,
            "path": "/ai-learning-hub",
        },
        "api_validation": {
            "failed": failed_api_checks,
            "checks": api_checks,
        },
        "videos": video_report,
        "weekly_publish": {
            "week_key": weekly_report.get("week_key"),
            "total_count": weekly_report.get("total_count"),
            "created_count": weekly_report.get("created_count"),
        },
    }
    await db.learn_hub_assurance_history.insert_one({**assurance_doc})
    await db.learn_hub_assurance_runtime.update_one(
        {"key": "learning_hub_assurance_runtime"},
        {"$set": {"key": "learning_hub_assurance_runtime", **assurance_doc, "updated_at": now_iso}},
        upsert=True,
    )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    await db.learn_hub_assurance_history.delete_many({"run_at": {"$lt": cutoff}})
    await db.learn_hub_integrity_history.delete_many({"checked_at": {"$lt": cutoff}})
    await db.learn_hub_email_queue.delete_many({"status": "sent", "updated_at": {"$lt": cutoff}})

    return assurance_doc


async def run_learning_hub_synthetic_canary(triggered_by: str = "manual") -> Dict[str, Any]:
    """Hourly synthetic funnel canary for AI Learning Hub core learner journey."""
    now = _utcnow_iso()
    run_id = f"lh_canary_{uuid.uuid4().hex[:10]}"
    steps: List[Dict[str, Any]] = []
    issues: List[str] = []

    admin = await db.users.find_one({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
    if not admin or not admin.get("user_id"):
        issues.append("No admin context found")
        admin = {"user_id": "scheduler_admin", "email": "admin@realaicoach.app", "name": "Scheduler Admin"}
    user_id = str(admin.get("user_id"))

    await db.learn_hub_kpi_route_views.insert_one(
        {
            "event_id": f"kpi_route_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "kpi_id": "streak",
            "route_path": "/ai-learning-hub-kpi/streak",
            "source": "hourly_canary",
            "viewed_at": now,
        }
    )
    steps.append({"step": "kpi_route", "status": "ok", "detail": "event recorded"})

    course = await db.learn_hub_courses.find_one({}, {"_id": 0, "course_id": 1, "title": 1, "subcategory": 1, "video_lessons": 1, "modules": 1})
    if not course:
        await _seed_enterprise_courses()
        course = await db.learn_hub_courses.find_one({}, {"_id": 0, "course_id": 1, "title": 1, "subcategory": 1, "video_lessons": 1, "modules": 1})

    if not course:
        issues.append("No course context for canary")
    else:
        course_id = str(course.get("course_id"))
        topic = str(course.get("subcategory") or course.get("title") or "AI")
        lesson = _normalize_video_lessons(course_id, topic, course.get("video_lessons"), min_count=5)[0]
        lesson_id = str(lesson.get("lesson_id") or "L1")

        await db.learn_hub_lesson_telemetry.insert_one(
            {
                "event_id": f"lesson_evt_{uuid.uuid4().hex[:12]}",
                "session_id": f"canary_{uuid.uuid4().hex[:8]}",
                "user_id": user_id,
                "course_id": course_id,
                "lesson_id": lesson_id,
                "event_type": "heartbeat",
                "position_seconds": 90,
                "duration_seconds": max(300, int((lesson.get("duration_min") or 10) * 60)),
                "seek_delta_seconds": 0,
                "created_at": now,
            }
        )
        await db.learn_hub_lesson_progress.update_one(
            {"user_id": user_id, "course_id": course_id, "lesson_id": lesson_id},
            {
                "$set": {
                    "user_id": user_id,
                    "course_id": course_id,
                    "lesson_id": lesson_id,
                    "watch_seconds": 90,
                    "total_seconds": max(300, int((lesson.get("duration_min") or 10) * 60)),
                    "watched_pct": 15,
                    "completed": False,
                    "last_position_seconds": 90,
                    "last_watch_event_at": now,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        steps.append({"step": "playback_telemetry", "status": "ok", "detail": lesson_id})

        latest_outcome = await db.learn_hub_remediation_outcomes.find_one(
            {"user_id": user_id, "course_id": course_id},
            {"_id": 0},
            sort=[("evaluated_at", -1)],
        )
        steps.append(
            {
                "step": "assessment_remediation",
                "status": "ok",
                "detail": "outcome available" if latest_outcome else "tracking pipeline ready (awaiting first outcome)",
            }
        )

    latest_cert = await db.learn_hub_certificates.find_one(
        {"user_id": user_id},
        {"_id": 0, "verification_id": 1},
        sort=[("issued_at", -1)],
    )
    if latest_cert and latest_cert.get("verification_id"):
        steps.append({"step": "certificate_verify", "status": "ok", "detail": latest_cert.get("verification_id")})
    else:
        issues.append("No certificate verification artifact")
        steps.append({"step": "certificate_verify", "status": "warning", "detail": "missing certificate"})

    status = "healthy" if not issues and all(step.get("status") == "ok" for step in steps) else "warning"
    doc = {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "status": status,
        "issues": issues,
        "steps": steps,
        "run_at": now,
        "updated_at": now,
    }

    await db.learn_hub_synthetic_canary_history.insert_one({**doc})
    await db.learn_hub_synthetic_canary_runtime.update_one(
        {"key": "learning_hub_synthetic_canary_runtime"},
        {"$set": {"key": "learning_hub_synthetic_canary_runtime", **doc}},
        upsert=True,
    )
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    await db.learn_hub_synthetic_canary_history.delete_many({"run_at": {"$lt": cutoff}})
    return doc


async def _dispatch_certificate_completion_email(certificate_doc: Dict[str, Any], force: bool = False) -> bool:
    recipient_email = str(certificate_doc.get("learner_email") or "").strip()
    if not recipient_email:
        return False
    if certificate_doc.get("completion_email_sent_at") and not force:
        return True
    try:
        from utils.email_service import send_email, is_email_configured

        if not is_email_configured():
            return False
        verify_url = _verification_public_url(certificate_doc.get("verification_id", ""))
        linkedin_share_url = str(certificate_doc.get("linkedin_share_url") or f"https://www.linkedin.com/sharing/share-offsite/?url={quote(verify_url, safe='')}")
        template_record = await _get_certificate_template_settings()
        pdf_b64 = _build_certificate_pdf_base64(
            certificate_doc,
            variant="print",
            template_settings=template_record.get("settings") or {},
            typography_preset=template_record.get("typography_preset"),
        )
        pdf_landscape_b64 = _build_certificate_pdf_base64(
            certificate_doc,
            variant="print",
            template_settings=template_record.get("settings") or {},
            typography_preset=template_record.get("typography_preset"),
            layout="landscape",
        )
        f"Your RealAICoach certificate is ready — {certificate_doc.get('course_title', 'AI Learning Course')}"

        # V7 compliant: use registered template builder
        from utils.email_templates import build_certificate_completion_email
        tpl = build_certificate_completion_email(
            learner_name=str(certificate_doc.get('learner_name') or 'Learner'),
            course_title=str(certificate_doc.get('course_title') or 'AI Learning Course'),
            signer_name=str(certificate_doc.get('signer_name') or CERTIFICATE_SIGNER_NAME),
            signer_role=_normalized_certificate_signer_role(certificate_doc.get('signer_role')),
            verification_id=str(certificate_doc.get('verification_id') or ''),
            verify_url=verify_url,
            linkedin_share_url=linkedin_share_url,
        )

        result = await send_email(
            recipient_email=recipient_email,
            subject=tpl.subject,
            content=tpl.html,
            recipient_name=certificate_doc.get("learner_name") or "Learner",
            template_key="learning_hub_certificate_award",
            skip_branding=True,
            attachments=[
                {
                    "filename": f"realaicoach-certificate-{certificate_doc.get('verification_id')}-portrait.pdf",
                    "content": pdf_b64,
                    "content_type": "application/pdf",
                },
                {
                    "filename": f"realaicoach-certificate-{certificate_doc.get('verification_id')}-landscape.pdf",
                    "content": pdf_landscape_b64,
                    "content_type": "application/pdf",
                },
            ],
        )
        return bool(result.get("success"))
    except Exception:
        return False


async def process_learning_hub_email_queue(batch_size: int = 120) -> Dict[str, Any]:
    from utils.email_service import send_email, is_email_configured

    if not is_email_configured():
        return {"processed": 0, "sent": 0, "failed": 0, "reason": "email_not_configured"}

    now_iso = _utcnow_iso()
    rows = await db.learn_hub_email_queue.find(
        {"status": "pending"},
        {"_id": 0},
    ).sort("created_at", 1).limit(max(1, min(batch_size, 500))).to_list(max(1, min(batch_size, 500)))

    sent = 0
    failed = 0
    for row in rows:
        queue_id = row.get("queue_id")
        try:
            result = await send_email(
                recipient_email=row.get("recipient_email"),
                subject=row.get("subject"),
                content=row.get("content"),
                recipient_name=row.get("recipient_name") or "Learner",
                template_key=row.get("template_key") or "learning_hub_update",
            )
            if result.get("success"):
                sent += 1
                await db.learn_hub_email_queue.update_one(
                    {"queue_id": queue_id},
                    {"$set": {"status": "sent", "provider_id": result.get("provider_id"), "updated_at": now_iso}},
                )
            else:
                failed += 1
                await db.learn_hub_email_queue.update_one(
                    {"queue_id": queue_id},
                    {
                        "$set": {
                            "status": "failed",
                            "last_error": result.get("error") or "send_failed",
                            "updated_at": now_iso,
                        }
                    },
                )
        except Exception as exc:
            failed += 1
            await db.learn_hub_email_queue.update_one(
                {"queue_id": queue_id},
                {"$set": {"status": "failed", "last_error": str(exc), "updated_at": now_iso}},
            )

    return {
        "processed": len(rows),
        "sent": sent,
        "failed": failed,
    }


async def _issue_or_get_certificate_for_user(
    user_id: str,
    user_name: str,
    user_email: str,
    course_id: str,
    course_title: str,
    triggered_by: str,
) -> Dict[str, Any]:
    existing = await db.learn_hub_certificates.find_one({"user_id": user_id, "course_id": course_id}, {"_id": 0})
    configured_mode = _configured_anchor_mode()
    now = _utcnow_iso()
    course_policy = await _course_certificate_policy(course_id)
    expiration_date = None
    if course_policy.get("validity_days"):
        issued_dt = _parse_iso_datetime(now) or datetime.now(timezone.utc)
        expiration_date = (issued_dt + timedelta(days=int(course_policy["validity_days"]))).isoformat()

    if existing:
        updates: Dict[str, Any] = {
            "learner_name": user_name,
            "learner_email": user_email,
            "course_title": course_title,
        }
        if expiration_date and not existing.get("expiration_date"):
            updates["expiration_date"] = expiration_date
        if str((existing.get("anchoring") or {}).get("status") or "") not in {"queued", "anchored", "pending"}:
            updates["anchoring"] = {
                "status": "queued",
                "mode": configured_mode,
                "chain_target": ANCHOR_CHAIN_TARGET,
                "queued_at": now,
                "last_updated_at": now,
                "anchor_note": _anchor_note_for_mode(configured_mode),
            }
            await _queue_certificate_for_anchoring(existing)
        if any(existing.get(key) != value for key, value in updates.items()):
            updates["updated_at"] = now
            await db.learn_hub_certificates.update_one({"certificate_id": existing.get("certificate_id")}, {"$set": updates})
            existing = {**existing, **updates}
        existing = await _ensure_certificate_record_shape(existing)
        assets = await _sync_certificate_storage_assets(existing, force=False)
        if assets:
            existing = {**existing, "storage_assets": assets}
        try:
            await _append_certificate_audit_log(existing, "issue_requested_existing", triggered_by, {"course_id": course_id})
        except Exception:
            pass
        return {"certificate": existing, "already_issued": True}

    verification_id = f"cert_{uuid.uuid4().hex[:14]}"
    validation_hash = _sign_certificate_payload(verification_id, user_id, course_id, now)
    verify_url = _verification_public_url(verification_id)
    certificate_doc = {
        "certificate_id": f"certificate_{uuid.uuid4().hex[:12]}",
        "certificate_number": _generate_certificate_number(course_id, now),
        "verification_id": verification_id,
        "user_id": user_id,
        "learner_name": user_name,
        "learner_email": user_email,
        "course_id": course_id,
        "course_title": course_title,
        "certificate_title": course_title,
        "issued_at": now,
        "expiration_date": expiration_date,
        "issued_by": CERTIFICATE_ISSUER_NAME,
        "credential_label": CERTIFICATE_CREDENTIAL_LABEL,
        "signer_name": CERTIFICATE_SIGNER_NAME,
        "signer_role": CERTIFICATE_SIGNER_ROLE,
        "validation_hash": validation_hash,
        "immutable_payload_hash": "",
        "verify_url": verify_url,
        "linkedin_share_url": f"https://www.linkedin.com/sharing/share-offsite/?url={quote(verify_url, safe='')}",
        "issued_via": triggered_by,
        "anchoring": {
            "status": "queued",
            "mode": configured_mode,
            "chain_target": ANCHOR_CHAIN_TARGET,
            "queued_at": now,
            "last_updated_at": now,
            "anchor_note": _anchor_note_for_mode(configured_mode),
        },
    }
    certificate_doc["immutable_payload_hash"] = _certificate_record_hash(certificate_doc)
    await db.learn_hub_certificates.insert_one({**certificate_doc})
    await _queue_certificate_for_anchoring(certificate_doc)
    assets = await _sync_certificate_storage_assets(certificate_doc, force=True)
    if assets:
        certificate_doc = {**certificate_doc, "storage_assets": assets}
    await _track_usage(user_id, "certificate_issue", {"course_id": course_id, "triggered_by": triggered_by})
    try:
        await _append_certificate_audit_log(certificate_doc, "issued", triggered_by, {"course_id": course_id})
    except Exception:
        pass
    return {"certificate": certificate_doc, "already_issued": False}


async def _trigger_course_completion_effects(user: Any, enrollment: Dict[str, Any], course_id: str, progress_pct: float) -> Dict[str, Any]:
    await _track_growth_event(
        user.user_id,
        "course_completed",
        {"course_id": course_id, "progress_pct": progress_pct},
    )
    try:
        await emit_notification(
            user_id=user.user_id,
            notif_type="learning_hub_milestone",
            title="Course completed",
            body=f"Great job! You completed {enrollment.get('course_title', 'your course')}.",
            action_url="/ai-learning-hub",
        )
    except Exception:
        pass

    cert_result = await _issue_or_get_certificate_for_user(
        user_id=user.user_id,
        user_name=str(getattr(user, "name", "") or "Learner"),
        user_email=str(getattr(user, "email", "") or ""),
        course_id=course_id,
        course_title=str(enrollment.get("course_title") or "AI Learning Course"),
        triggered_by="auto_completion",
    )
    cert_doc = cert_result.get("certificate") or {}
    cert_sent = await _dispatch_certificate_completion_email(cert_doc)
    if cert_sent:
        await db.learn_hub_certificates.update_one(
            {"certificate_id": cert_doc.get("certificate_id")},
            {"$set": {"completion_email_sent_at": _utcnow_iso(), "updated_at": _utcnow_iso()}},
        )
    try:
        certificate_action_url = f"/certificate-verify/{cert_doc.get('verification_id')}" if cert_doc.get("verification_id") else "/ai-learning-hub?tab=journey&filter=completed"
        await emit_notification(
            user_id=user.user_id,
            notif_type="learning_hub_certificate_awarded",
            title="Certificate awarded",
            body=f"Your certificate for {enrollment.get('course_title', 'this course')} is ready.",
            action_url=certificate_action_url,
            metadata={
                "verification_id": cert_doc.get("verification_id"),
                "course_id": course_id,
                "verify_url": cert_doc.get("verify_url") or _verification_public_url(cert_doc.get("verification_id", "")),
                "linkedin_share_url": cert_doc.get("linkedin_share_url"),
            },
        )
    except Exception:
        pass

    return {"certificate": cert_doc, "already_issued": bool(cert_result.get("already_issued"))}


async def _mark_remediation_action(
    user_id: str,
    course_id: str,
    action_type: str,
    lesson_id: Optional[str] = None,
    material_id: Optional[str] = None,
) -> Dict[str, Any]:
    enrollment = await db.learn_hub_enrollments.find_one(
        {"user_id": user_id, "course_id": course_id},
        {"_id": 0, "assessment": 1},
    ) or {}
    assessment = enrollment.get("assessment") if isinstance(enrollment.get("assessment"), dict) else {}
    active_remediation = assessment.get("active_remediation") if isinstance(assessment.get("active_remediation"), dict) else None
    if not active_remediation:
        return {"updated": False, "reason": "no_active_remediation"}

    recommendations = active_remediation.get("recommendations") if isinstance(active_remediation.get("recommendations"), list) else []
    updated = False
    now = _utcnow_iso()

    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        if action_type == "lesson_completed" and lesson_id and str(rec.get("lesson_id") or "") == str(lesson_id):
            if not rec.get("lesson_completed"):
                rec["lesson_completed"] = True
                rec["lesson_completed_at"] = now
                updated = True
        if action_type == "material_opened" and material_id and str(rec.get("material_id") or "") == str(material_id):
            if not rec.get("material_opened"):
                rec["material_opened"] = True
                rec["material_opened_at"] = now
                updated = True

    if not updated:
        return {"updated": False, "reason": "no_matching_recommendation"}

    total = len(recommendations)
    lesson_done = sum(1 for rec in recommendations if rec.get("lesson_completed"))
    material_done = sum(1 for rec in recommendations if rec.get("material_opened"))
    active_remediation["recommendations"] = recommendations
    active_remediation["updated_at"] = now
    active_remediation["progress"] = {
        "total_recommendations": total,
        "lesson_completions": lesson_done,
        "material_opens": material_done,
    }

    await db.learn_hub_enrollments.update_one(
        {"user_id": user_id, "course_id": course_id},
        {
            "$set": {
                "assessment.active_remediation": active_remediation,
                "updated_at": now,
            }
        },
    )

    return {
        "updated": True,
        "progress": active_remediation.get("progress"),
        "remediation_id": active_remediation.get("remediation_id"),
    }


async def _get_opportunity_radar(user: Any) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    cached = await db.learn_hub_opportunity_radar.find_one(
        {"user_id": user.user_id, "day": today},
        {"_id": 0},
    )
    if cached:
        return cached

    enrollments = await db.learn_hub_enrollments.find({"user_id": user.user_id}, {"_id": 0, "course_title": 1, "category": 1}).to_list(50)
    courses = await db.learn_hub_courses.find({}, {"_id": 0, "skills": 1}).limit(40).to_list(40)

    skill_pool: List[str] = []
    for c in courses:
        for sk in (c.get("skills") or []):
            if isinstance(sk, str) and sk and sk not in skill_pool:
                skill_pool.append(sk)

    profile_tracks = [str(e.get("category") or "") for e in enrollments if e.get("category")][:4]
    profile_summary = ", ".join(profile_tracks) or "AI"
    fallback = {
        "opportunities": [
            {
                "opportunity_id": f"opp_{uuid.uuid4().hex[:8]}",
                "title": f"{profile_summary} Consulting Audit Sprint",
                "value_signal": "High-intent SMB buyers need quick diagnostics",
                "estimated_income_range": "$250-$900",
                "effort_hours": 6,
                "first_action": "Publish one 1-page audit offer and send 5 targeted outreaches",
                "confidence": 78,
            },
            {
                "opportunity_id": f"opp_{uuid.uuid4().hex[:8]}",
                "title": "AI Workflow Automation Mini-Service",
                "value_signal": "Recurring demand from founders/operators",
                "estimated_income_range": "$400-$1500",
                "effort_hours": 8,
                "first_action": "Create one before/after workflow demo video",
                "confidence": 74,
            },
        ]
    }

    system_message = """You are a career-income opportunity strategist.
Return JSON only with key opportunities (array).
Each opportunity item: opportunity_id, title, value_signal, estimated_income_range, effort_hours, first_action, confidence."""
    prompt = f"""Generate top 4 practical opportunities for this learner.
Learning tracks: {profile_summary}
Known skill pool: {', '.join(skill_pool[:10]) or 'AI, Security, Automation'}
Prioritize realistic income and career outcomes in 7-14 days."""
    generated = await _ask_gpt_52_json(system_message, prompt, "learnhub-opportunity-radar", fallback)
    opportunities = generated.get("opportunities") or fallback.get("opportunities")

    doc = {
        "radar_id": f"lh_radar_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "day": today,
        "opportunities": opportunities,
        "generated_at": _utcnow_iso(),
    }
    await db.learn_hub_opportunity_radar.update_one(
        {"user_id": user.user_id, "day": today},
        {"$set": doc},
        upsert=True,
    )
    return doc


@router.get("/hub-dashboard")
async def hub_dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    await _ensure_learning_hub_automation()

    plan = _effective_plan_for_user(user)
    entitlements = _entitlements_for_plan(plan)
    access_policy = _plan_access_policy(plan)
    streak = await _compute_streak(user.user_id)

    enrollment_rows = await db.learn_hub_enrollments.find({"user_id": user.user_id}, {"_id": 0}).sort("updated_at", -1).limit(80).to_list(80)

    def _is_enrollment_completed(row):
        modules = row.get("modules") if isinstance(row.get("modules"), list) else []
        completed_modules = sum(1 for m in modules if m.get("completed"))
        total_modules = max(1, len(modules))
        pct = float(row.get("progress_pct") or 0)
        if pct <= 0 and total_modules > 0:
            pct = round((completed_modules / total_modules) * 100, 2)
        assessment_required = row.get("assessment_required", True)
        assessment_data = row.get("assessment") if isinstance(row.get("assessment"), dict) else {}
        assessment_passed = bool(assessment_data.get("passed")) if assessment_required else True
        if bool(row.get("completed")) and not assessment_passed:
            assessment_passed = True
        return bool(pct >= 100 and (not assessment_required or assessment_passed))

    completed_courses = sum(1 for row in enrollment_rows if _is_enrollment_completed(row))
    active_courses = sum(1 for row in enrollment_rows if not _is_enrollment_completed(row))
    certificates_count = await db.learn_hub_certificates.count_documents({"user_id": user.user_id})

    learned_categories = [row.get("category") for row in enrollment_rows if row.get("category")]
    preferred_category = learned_categories[0] if learned_categories else None

    recommendation_query = {"featured": True}
    if preferred_category:
        recommendation_query = {"$or": [{"category": preferred_category}, {"featured": True}]}
    recommendations = await db.learn_hub_courses.find(recommendation_query, {"_id": 0}).sort("updated_at", -1).limit(5).to_list(5)

    notifications = await db.notifications.find(
        {"user_id": user.user_id, "type": {"$in": ["learning_hub_update", "learning_hub_milestone", "ai_recommendation"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)

    if not notifications and recommendations:
        try:
            await emit_notification(
                user_id=user.user_id,
                notif_type="learning_hub_update",
                title="Your next AI learning sprint is ready",
                body=f"Recommended next course: {recommendations[0].get('title', 'AI Learning Path')}",
                action_url="/ai-learning-hub",
            )
        except Exception:
            pass

    papers_meta = await db.learn_hub_paper_ingest.find_one({"type": "meta"}, {"_id": 0})
    integrity_runtime = await db.learn_hub_integrity_runtime.find_one({"key": "learning_hub_integrity_runtime"}, {"_id": 0}) or {}
    assurance_runtime = await db.learn_hub_assurance_runtime.find_one({"key": "learning_hub_assurance_runtime"}, {"_id": 0}) or {}
    video_runtime = await db.learn_hub_video_validation_runtime.find_one({"key": "learning_hub_video_validation_rotation"}, {"_id": 0}) or {}
    weekly_runtime = await db.learn_hub_automation_runtime.find_one({"key": "learning_hub_weekly_course_runtime"}, {"_id": 0}) or {}
    habit_loop = await _build_habit_loop_summary(user, streak_snapshot=streak)
    latest_sprint = await db.learn_hub_career_sprints.find_one(
        {"user_id": user.user_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    onboarding_summary = _build_phase2_onboarding_summary(
        enrollment_rows=enrollment_rows,
        latest_sprint=latest_sprint,
        habit_loop_summary=habit_loop,
        certificates_count=certificates_count,
    )
    weekly_achievement_loop = await _build_weekly_achievement_loop(user, streak)
    generated_at = _utcnow_iso()
    streak_days = int(streak.get("streak_days", 0) or 0)
    today_minutes = int(streak.get("today_minutes", 0) or 0)
    weekly_minutes = int(streak.get("weekly_minutes", 0) or 0)
    insured_days = int(streak.get("insured_days", 0) or 0)

    next_enrollment = next((row for row in enrollment_rows if not _is_enrollment_completed(row)), None)
    pending_missions = [m for m in (habit_loop.get("missions") or []) if not m.get("completed")]
    daily_action_cards: List[Dict[str, Any]] = []

    if next_enrollment:
        daily_action_cards.append(
            {
                "action_id": "resume_active_course",
                "title": "Resume your active course",
                "detail": f"{next_enrollment.get('course_title', 'Course')} is waiting for your next module.",
                "action_url": "/ai-learning-hub?tab=journey&filter=active",
                "priority": "high",
            }
        )
    if pending_missions:
        daily_action_cards.append(
            {
                "action_id": "complete_daily_mission",
                "title": "Complete one daily mission",
                "detail": f"{len(pending_missions)} mission(s) pending to protect your streak.",
                "action_url": "/ai-learning-hub?tab=lab",
                "priority": "high",
            }
        )
    if weekly_minutes < 90:
        daily_action_cards.append(
            {
                "action_id": "weekly_minutes_target",
                "title": "Hit 90 learning minutes this week",
                "detail": f"You are at {weekly_minutes} minutes this week.",
                "action_url": "/ai-learning-hub?tab=journey",
                "priority": "medium",
            }
        )
    if completed_courses > certificates_count:
        daily_action_cards.append(
            {
                "action_id": "issue_pending_certificate",
                "title": "Claim pending certificates",
                "detail": f"{completed_courses - certificates_count} completion(s) are ready for certificate issuance.",
                "action_url": "/ai-learning-hub?tab=journey&filter=completed",
                "priority": "medium",
            }
        )

    if not daily_action_cards:
        daily_action_cards = [
            {
                "action_id": "discover_new_course",
                "title": "Discover your next course",
                "detail": "Keep momentum by starting one fresh learning sprint today.",
                "action_url": "/ai-learning-hub?tab=discover",
                "priority": "medium",
            }
        ]

    daily_action_cards = daily_action_cards[:4]

    return {
        "generated_at": generated_at,
        "streak_days": streak_days,
        "today_minutes": today_minutes,
        "weekly_minutes": weekly_minutes,
        "insured_days": insured_days,
        "completed_courses": completed_courses,
        "active_courses": active_courses,
        "entitlements": entitlements,
        "engagement": {
            "streak_days": streak_days,
            "today_minutes": today_minutes,
            "weekly_minutes": weekly_minutes,
            "insured_days": insured_days,
            "completed_courses": completed_courses,
            "active_courses": active_courses,
            "certificates": certificates_count,
            "adaptive_loop_status": "active",
        },
        "access_control": {
            **access_policy,
            "daily_enforced": True,
        },
        "recommendations": recommendations,
        "notifications": notifications,
        "daily_action_cards": daily_action_cards,
        "video_quality": {
            "topic_alignment_pct": float(video_runtime.get("topic_alignment_pct", 100) or 100),
            "topic_mismatch_lessons": int(video_runtime.get("topic_mismatch_lessons", 0) or 0),
            "topic_repaired_lessons": int(video_runtime.get("topic_repaired_lessons", 0) or 0),
            "broken_links": int(video_runtime.get("broken_links", 0) or 0),
            "checked_lessons": int(video_runtime.get("checked_lessons", 0) or 0),
            "last_checked_at": video_runtime.get("updated_at"),
        },
        "automation": {
            "learning_engine": "self-healing",
            "real_time_refresh_seconds": 20,
            "last_paper_ingest_at": (papers_meta or {}).get("last_ingest_at"),
            "pipeline_status": "operational",
            "last_integrity_check_at": integrity_runtime.get("last_run_at"),
            "integrity_status": integrity_runtime.get("last_status", "unknown"),
            "repaired_verify_urls": integrity_runtime.get("repaired_verify_urls", 0),
        },
        "daily_momentum": {
            "habit_loop": habit_loop,
            "latest_career_sprint": latest_sprint,
        },
        "onboarding": onboarding_summary,
        "weekly_achievement_loop": weekly_achievement_loop,
        "weekly_release": {
            "week_key": weekly_runtime.get("week_key"),
            "published_count": weekly_runtime.get("total_count", 0),
            "new_courses_this_run": weekly_runtime.get("created_count", 0),
            "updated_at": weekly_runtime.get("updated_at"),
        },
        "assurance": {
            "status": assurance_runtime.get("status", "unknown"),
            "run_at": assurance_runtime.get("run_at"),
            "platform_health_score": (assurance_runtime.get("platform_health") or {}).get("score"),
            "video_broken_links": ((assurance_runtime.get("videos") or {}).get("broken_links")),
            "video_topic_mismatches": ((assurance_runtime.get("videos") or {}).get("topic_mismatch_lessons")),
            "video_topic_alignment_pct": ((assurance_runtime.get("videos") or {}).get("topic_alignment_pct")),
        },
    }


@router.post("/kpi-route-view")
async def track_kpi_route_view(request: Request, body: KpiRouteViewRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    allowed_kpis = {"streak", "active", "complete", "minutes"}
    kpi_id = str(body.kpi_id or "").lower().strip()
    if kpi_id not in allowed_kpis:
        raise HTTPException(400, "Unsupported KPI route")

    now = _utcnow_iso()
    doc = {
        "event_id": f"kpi_route_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "kpi_id": kpi_id,
        "route_path": str(body.route_path or ""),
        "source": str(body.source or "ui"),
        "viewed_at": now,
    }
    await db.learn_hub_kpi_route_views.insert_one({**doc})
    await _track_growth_event(user.user_id, "kpi_route_view", {"kpi_id": kpi_id, "source": doc["source"]})

    return {"success": True, "kpi_id": kpi_id, "viewed_at": now}


@router.get("/courses")
async def list_learning_hub_courses(request: Request, search: str = "", category: str = "", difficulty: str = ""):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    await _ensure_learning_hub_automation()

    filters: Dict[str, Any] = {}
    if category:
        filters["category"] = category
    if difficulty:
        filters["difficulty"] = difficulty
    if search.strip():
        filters["$or"] = [
            {"title": {"$regex": re.escape(str(search).strip()), "$options": "i"}},
            {"overview": {"$regex": re.escape(str(search).strip()), "$options": "i"}},
            {"skills": {"$elemMatch": {"$regex": re.escape(str(search).strip()), "$options": "i"}}},
        ]

    courses = await db.learn_hub_courses.find(filters, {"_id": 0}).sort("updated_at", -1).limit(120).to_list(120)
    plan = _effective_plan_for_user(user)
    access_policy = _plan_access_policy(plan)
    enrollments = await db.learn_hub_enrollments.find({"user_id": user.user_id}, {"_id": 0, "course_id": 1, "progress_pct": 1, "completed": 1}).to_list(200)
    enrollment_map = {row.get("course_id"): row for row in enrollments}
    enrolled_course_ids = {str(row.get("course_id") or "") for row in enrollments if row.get("course_id")}
    catalog_limit = int(access_policy.get("catalog_limit", 12) or 12)

    rows = []
    hidden_by_plan = 0
    for idx, course in enumerate(courses):
        course_id = str(course.get("course_id") or uuid.uuid4().hex[:8])
        if catalog_limit >= 0 and idx >= catalog_limit and course_id not in enrolled_course_ids:
            hidden_by_plan += 1
            continue

        topic = str(course.get("subcategory") or course.get("title") or "AI")
        normalized_lessons = _normalize_video_lessons(
            course_id,
            topic,
            course.get("video_lessons"),
            min_count=5,
        )
        normalized_modules = _normalize_modules(course.get("modules"))
        normalized_materials = _normalize_learning_materials(course_id, topic, normalized_modules, course.get("learning_materials"))
        normalized_assessment = _normalize_final_assessment(course_id, topic, normalized_modules, course.get("final_assessment"))

        mutated = (
            len(normalized_lessons) != len(course.get("video_lessons") or [])
            or len(normalized_modules) != len(course.get("modules") or [])
            or len(normalized_materials) != len(course.get("learning_materials") or [])
            or len((normalized_assessment.get("questions") or [])) != len(((course.get("final_assessment") or {}).get("questions") or []))
            or int(normalized_assessment.get("passing_score_pct") or 70) != int((course.get("final_assessment") or {}).get("passing_score_pct") or 70)
        )

        if mutated:
            await db.learn_hub_courses.update_one(
                {"course_id": course.get("course_id")},
                {
                    "$set": {
                        "video_lessons": normalized_lessons,
                        "modules": normalized_modules,
                        "learning_materials": normalized_materials,
                        "final_assessment": normalized_assessment,
                        "updated_at": _utcnow_iso(),
                    }
                },
            )
            course["video_lessons"] = normalized_lessons
            course["modules"] = normalized_modules
            course["learning_materials"] = normalized_materials
            course["final_assessment"] = normalized_assessment

        progress = enrollment_map.get(course.get("course_id"), {})
        public_assessment = {
            "assessment_id": normalized_assessment.get("assessment_id"),
            "title": normalized_assessment.get("title"),
            "passing_score_pct": normalized_assessment.get("passing_score_pct"),
            "questions": [
                {
                    "question_id": q.get("question_id"),
                    "question": q.get("question"),
                    "options": q.get("options"),
                }
                for q in (normalized_assessment.get("questions") or [])
            ],
        }

        topic_alignment_pct = round(
            (
                sum(float(lesson.get("topic_alignment_score") or 0) for lesson in normalized_lessons)
                / max(1, len(normalized_lessons))
            )
            * 100,
            2,
        )
        topic_mismatch_count = sum(
            1 for lesson in normalized_lessons if str(lesson.get("topic_alignment_status") or "") != "aligned"
        )
        rows.append(
            {
                **course,
                "video_lessons": normalized_lessons,
                "modules": normalized_modules,
                "learning_materials": normalized_materials,
                "final_assessment": public_assessment,
                "cover_url": f"/api/ai-learn/course-cover/{course_id}.jpg",
                "enrolled": bool(progress),
                "progress_pct": float(progress.get("progress_pct", 0) or 0),
                "completed": bool(progress.get("completed")),
                "assessment_required": bool((normalized_assessment.get("questions") or [])),
                "video_quality": {
                    "topic_alignment_pct": topic_alignment_pct,
                    "topic_mismatch_count": topic_mismatch_count,
                    "lesson_count": len(normalized_lessons),
                },
            }
        )

    return {
        "courses": rows,
        "total": len(rows),
        "data_freshness_at": _utcnow_iso(),
        "access_control": {
            **access_policy,
            "catalog_hidden_count": hidden_by_plan,
            "catalog_visible_count": len(rows),
            "catalog_total_count": len(courses),
            "message": (
                "Free plan shows curated courses only. Upgrade for broader catalog access."
                if plan == "free"
                else "Basic plan has almost unlimited catalog access."
                if plan == "basic"
                else "Premium plan has full unlimited catalog access."
            ),
        },
    }


@router.post("/courses/auto-generate")
async def auto_generate_course(request: Request, body: AutoGenerateCourseRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    if not body.topic.strip():
        raise HTTPException(400, "Topic is required")

    await _enforce_entitlement(user, "auto_generate_course")

    course_doc = await _generate_enterprise_course_doc(
        topic=body.topic,
        category=body.category,
        difficulty=body.difficulty,
        objective=body.objective,
        created_by=user.user_id,
        publish_source="manual_generation",
    )
    now = _utcnow_iso()
    await _track_usage(user.user_id, "auto_generate_course", {"course_id": course_doc.get("course_id"), "topic": body.topic})

    try:
        await emit_notification(
            user_id=user.user_id,
            notif_type="learning_hub_update",
            title="New AI course generated",
            body=f"{course_doc['title']} is now ready in your Learning Hub.",
            action_url="/ai-learning-hub",
        )
    except Exception:
        pass

    return {"course": course_doc, "generated_at": now, "model": "gpt-4o"}


@router.post("/courses/{course_id}/enroll")
async def enroll_course(request: Request, course_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    course = await db.learn_hub_courses.find_one({"course_id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Course not found")

    plan = _effective_plan_for_user(user)
    access_policy = _plan_access_policy(plan)
    existing_enrollment = await db.learn_hub_enrollments.find_one(
        {"user_id": user.user_id, "course_id": course_id},
        {"_id": 0, "enrollment_id": 1},
    )
    if not existing_enrollment:
        total_enrollments = await db.learn_hub_enrollments.count_documents({"user_id": user.user_id})
        active_enrollments = await db.learn_hub_enrollments.count_documents({"user_id": user.user_id, "completed": {"$ne": True}})
        max_total = int(access_policy.get("max_total_enrollments", 4) or 4)
        max_active = int(access_policy.get("max_active_enrollments", 2) or 2)

        if max_total >= 0 and total_enrollments >= max_total:
            raise HTTPException(
                status_code=403,
                detail=f"{access_policy.get('scope_label', 'Plan')} reached total enrollment cap ({max_total}).",
            )

        if max_active >= 0 and active_enrollments >= max_active:
            raise HTTPException(
                status_code=403,
                detail=f"{access_policy.get('scope_label', 'Plan')} reached active enrollment cap ({max_active}).",
            )

    now = _utcnow_iso()
    modules = _normalize_modules(course.get("modules"))
    assessment_template = _normalize_final_assessment(
        course_id,
        str(course.get("subcategory") or course.get("title") or "AI"),
        modules,
        course.get("final_assessment"),
    )
    assessment_required = bool((assessment_template.get("questions") or []))
    progress_modules = [
        {
            "module_id": module.get("module_id") or f"m_{idx}",
            "title": module.get("title", "Module"),
            "completed": False,
            "completed_at": None,
        }
        for idx, module in enumerate(modules)
    ]
    enrollment_doc = {
        "enrollment_id": f"enroll_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "course_id": course_id,
        "course_title": course.get("title", "Course"),
        "category": course.get("category", "AI"),
        "progress_pct": 0,
        "completed": False,
        "modules": progress_modules,
        "assessment": _normalize_assessment_state(None, assessment_required),
        "awaiting_assessment": False,
        "started_at": now,
        "updated_at": now,
    }

    await db.learn_hub_enrollments.update_one(
        {"user_id": user.user_id, "course_id": course_id},
        {"$setOnInsert": enrollment_doc},
        upsert=True,
    )

    existing = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0, "assessment": 1}) or {}
    if not isinstance(existing.get("assessment"), dict):
        await db.learn_hub_enrollments.update_one(
            {"user_id": user.user_id, "course_id": course_id},
            {"$set": {"assessment": _normalize_assessment_state(None, assessment_required), "updated_at": _utcnow_iso()}},
        )

    if not existing_enrollment:
        asyncio.create_task(_send_enrollment_kickoff_email(user, course))

    return {"success": True, "course_id": course_id, "enrolled_at": now, "plan": plan}


@router.post("/courses/{course_id}/progress")
async def update_course_progress(request: Request, course_id: str, body: ProgressUpdateRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    enrollment = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    now = _utcnow_iso()
    was_completed = bool(enrollment.get("completed"))
    modules = enrollment.get("modules", [])
    updated = False
    for module in modules:
        if module.get("module_id") == body.module_id:
            module["completed"] = bool(body.completed)
            module["completed_at"] = now if body.completed else None
            updated = True
            break
    if not updated:
        raise HTTPException(404, "Module not found")

    completed_count = sum(1 for module in modules if module.get("completed"))
    total_modules = max(1, len(modules))
    progress_pct = round((completed_count / total_modules) * 100, 2)

    course_doc = await db.learn_hub_courses.find_one(
        {"course_id": course_id},
        {"_id": 0, "final_assessment": 1, "subcategory": 1, "title": 1, "modules": 1, "video_lessons": 1, "learning_materials": 1},
    ) or {}
    topic = str(course_doc.get("subcategory") or course_doc.get("title") or enrollment.get("course_title") or "AI")
    assessment_template = _normalize_final_assessment(
        course_id,
        topic,
        modules,
        course_doc.get("final_assessment"),
    )
    assessment_required = bool((assessment_template.get("questions") or []))
    assessment_state = _normalize_assessment_state(enrollment.get("assessment"), assessment_required)
    if was_completed and progress_pct >= 100 and not bool(assessment_state.get("passed")):
        assessment_state["passed"] = True
        assessment_state["score_pct"] = max(float(assessment_state.get("score_pct") or 0), float(assessment_template.get("passing_score_pct") or 70))
        assessment_state["passed_at"] = assessment_state.get("passed_at") or now
    completed = progress_pct >= 100 and bool(assessment_state.get("passed"))
    awaiting_assessment = progress_pct >= 100 and not bool(assessment_state.get("passed"))

    await db.learn_hub_enrollments.update_one(
        {"user_id": user.user_id, "course_id": course_id},
        {
            "$set": {
                "modules": modules,
                "progress_pct": progress_pct,
                "completed": completed,
                "assessment": assessment_state,
                "awaiting_assessment": awaiting_assessment,
                "updated_at": now,
                "completed_at": now if completed else None,
            }
        },
    )

    await _record_learning_minutes(user.user_id, max(1, body.minutes_spent))
    await _track_growth_event(
        user.user_id,
        "module_progress",
        {
            "course_id": course_id,
            "module_id": body.module_id,
            "completed": bool(body.completed),
            "progress_pct": progress_pct,
        },
    )
    if completed and not was_completed:
        await _trigger_course_completion_effects(user, enrollment, course_id, progress_pct)

    return {
        "success": True,
        "course_id": course_id,
        "progress_pct": progress_pct,
        "completed": completed,
        "awaiting_assessment": awaiting_assessment,
        "assessment": {
            "required": assessment_required,
            "passed": bool(assessment_state.get("passed")),
            "score_pct": float(assessment_state.get("score_pct") or 0),
            "attempts": int(assessment_state.get("attempts") or 0),
            "passing_score_pct": int(assessment_template.get("passing_score_pct") or 70),
        },
    }


@router.get("/courses/{course_id}/lessons/watch-state")
async def get_lesson_watch_state(request: Request, course_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    rows = await db.learn_hub_lesson_progress.find(
        {"user_id": user.user_id, "course_id": course_id},
        {"_id": 0},
    ).to_list(300)
    lesson_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        lesson_id = str(row.get("lesson_id") or "")
        if not lesson_id:
            continue
        lesson_map[lesson_id] = {
            "watch_seconds": float(row.get("watch_seconds") or 0),
            "total_seconds": float(row.get("total_seconds") or 0),
            "watched_pct": float(row.get("watched_pct") or 0),
            "completed": bool(row.get("completed")),
            "last_position_seconds": float(row.get("last_position_seconds") or 0),
            "last_watch_event_at": row.get("last_watch_event_at"),
            "resume_label": _format_duration_mmss(row.get("last_position_seconds") or row.get("watch_seconds") or 0),
        }

    return {"course_id": course_id, "lessons": lesson_map, "generated_at": _utcnow_iso()}


@router.post("/courses/{course_id}/lessons/{lesson_id}/watch-state")
async def save_lesson_watch_state(request: Request, course_id: str, lesson_id: str, body: LessonWatchStateRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    enrollment = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0, "enrollment_id": 1})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    existing = await db.learn_hub_lesson_progress.find_one(
        {"user_id": user.user_id, "course_id": course_id, "lesson_id": lesson_id},
        {"_id": 0},
    ) or {}

    total_seconds = float(body.total_seconds or existing.get("total_seconds") or 0)
    watch_seconds = max(float(existing.get("watch_seconds") or 0), float(body.watch_seconds or 0))
    last_position_seconds = float(body.last_position_seconds if body.last_position_seconds is not None else existing.get("last_position_seconds") or watch_seconds)
    watched_pct = 0.0
    if total_seconds > 0:
        watched_pct = round(min(100.0, (watch_seconds / total_seconds) * 100), 2)
    completed = bool(body.completed or watched_pct >= 95)
    now = _utcnow_iso()

    doc = {
        "user_id": user.user_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "watch_seconds": watch_seconds,
        "total_seconds": total_seconds,
        "watched_pct": watched_pct,
        "completed": completed,
        "last_position_seconds": last_position_seconds,
        "last_watch_event_at": now,
        "updated_at": now,
    }

    await db.learn_hub_lesson_progress.update_one(
        {"user_id": user.user_id, "course_id": course_id, "lesson_id": lesson_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "success": True,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "watch_state": {
            "watch_seconds": watch_seconds,
            "total_seconds": total_seconds,
            "watched_pct": watched_pct,
            "completed": completed,
            "last_position_seconds": last_position_seconds,
            "resume_label": _format_duration_mmss(last_position_seconds),
            "updated_at": now,
        },
    }


@router.post("/courses/{course_id}/lessons/{lesson_id}/telemetry")
async def lesson_playback_telemetry(request: Request, course_id: str, lesson_id: str, body: LessonTelemetryEventRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    enrollment = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0, "enrollment_id": 1})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    event_type = str(body.event_type or "").lower().strip()
    if event_type not in {"open", "play", "pause", "seek", "heartbeat", "complete"}:
        raise HTTPException(400, "Unsupported telemetry event type")

    now = _utcnow_iso()
    event_doc = {
        "event_id": f"lesson_evt_{uuid.uuid4().hex[:12]}",
        "session_id": str(body.session_id or f"session_{uuid.uuid4().hex[:12]}"),
        "user_id": user.user_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "event_type": event_type,
        "position_seconds": float(body.position_seconds or 0),
        "duration_seconds": float(body.duration_seconds or 0),
        "seek_delta_seconds": float(body.seek_delta_seconds or 0),
        "created_at": now,
    }
    await db.learn_hub_lesson_telemetry.insert_one({**event_doc})

    existing_state = await db.learn_hub_lesson_progress.find_one(
        {"user_id": user.user_id, "course_id": course_id, "lesson_id": lesson_id},
        {"_id": 0},
    ) or {}

    total_seconds = float(body.duration_seconds or existing_state.get("total_seconds") or 0)
    current_watch_seconds = float(existing_state.get("watch_seconds") or 0)
    incoming_position = max(0.0, float(body.position_seconds or 0))
    next_watch_seconds = max(current_watch_seconds, incoming_position)
    next_position = incoming_position

    if event_type == "seek":
        next_position = max(0.0, incoming_position)
    if event_type == "complete":
        if total_seconds <= 0:
            total_seconds = max(next_watch_seconds, incoming_position)
        next_watch_seconds = max(next_watch_seconds, total_seconds)
        next_position = total_seconds

    watched_pct = 0.0
    if total_seconds > 0:
        watched_pct = round(min(100.0, (next_watch_seconds / total_seconds) * 100), 2)
    completed = bool(event_type == "complete" or existing_state.get("completed") or watched_pct >= 95)

    watch_doc = {
        "user_id": user.user_id,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "watch_seconds": next_watch_seconds,
        "total_seconds": total_seconds,
        "watched_pct": watched_pct,
        "completed": completed,
        "last_position_seconds": next_position,
        "last_watch_event_at": now,
        "updated_at": now,
    }
    await db.learn_hub_lesson_progress.update_one(
        {"user_id": user.user_id, "course_id": course_id, "lesson_id": lesson_id},
        {"$set": watch_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    remediation_update = None
    if completed:
        remediation_update = await _mark_remediation_action(
            user_id=user.user_id,
            course_id=course_id,
            action_type="lesson_completed",
            lesson_id=lesson_id,
        )

    return {
        "success": True,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "event_type": event_type,
        "session_id": event_doc["session_id"],
        "watch_state": {
            "watch_seconds": next_watch_seconds,
            "total_seconds": total_seconds,
            "watched_pct": watched_pct,
            "completed": completed,
            "last_position_seconds": next_position,
            "resume_label": _format_duration_mmss(next_position),
            "updated_at": now,
        },
        "remediation_update": remediation_update,
    }


@router.post("/courses/{course_id}/remediation/action")
async def remediation_action(request: Request, course_id: str, body: RemediationActionRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    action_type = str(body.action_type or "").lower().strip()
    if action_type not in {"lesson_completed", "material_opened"}:
        raise HTTPException(400, "Unsupported remediation action type")

    result = await _mark_remediation_action(
        user_id=user.user_id,
        course_id=course_id,
        action_type=action_type,
        lesson_id=body.lesson_id,
        material_id=body.material_id,
    )

    await db.learn_hub_remediation_action_log.insert_one(
        {
            "event_id": f"rem_action_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "course_id": course_id,
            "action_type": action_type,
            "lesson_id": body.lesson_id,
            "material_id": body.material_id,
            "metadata": body.metadata or {},
            "result": result,
            "created_at": _utcnow_iso(),
        }
    )

    return {"success": True, "result": result}


@router.post("/courses/{course_id}/assessment/submit")
async def submit_course_assessment(request: Request, course_id: str, body: AssessmentSubmitRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    enrollment = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    modules = enrollment.get("modules") or []
    completed_count = sum(1 for module in modules if module.get("completed"))
    total_modules = max(1, len(modules))
    progress_pct = round((completed_count / total_modules) * 100, 2)
    if progress_pct < 100:
        raise HTTPException(400, "Complete all module checkpoints before submitting the final assessment")

    course_doc = await db.learn_hub_courses.find_one(
        {"course_id": course_id},
        {"_id": 0, "final_assessment": 1, "subcategory": 1, "title": 1, "modules": 1, "video_lessons": 1, "learning_materials": 1},
    ) or {}
    topic = str(course_doc.get("subcategory") or course_doc.get("title") or enrollment.get("course_title") or "AI")
    normalized_modules = _normalize_modules(course_doc.get("modules"))
    normalized_lessons = _normalize_video_lessons(course_id, topic, course_doc.get("video_lessons"), min_count=5)
    normalized_materials = _normalize_learning_materials(course_id, topic, normalized_modules, course_doc.get("learning_materials"))
    assessment_template = _normalize_final_assessment(
        course_id,
        topic,
        modules,
        course_doc.get("final_assessment"),
    )
    questions = assessment_template.get("questions") or []
    if not questions:
        raise HTTPException(400, "No final assessment is configured for this course")

    answers = body.answers or {}
    correct = 0
    review_rows: List[Dict[str, Any]] = []
    for question in questions:
        qid = str(question.get("question_id") or "")
        try:
            selected_index = int(answers.get(qid))
        except Exception:
            selected_index = -1
        correct_index = int(question.get("correct_option_index") or 0)
        is_correct = selected_index == correct_index
        if is_correct:
            correct += 1
        options = question.get("options") or []
        selected_option = options[selected_index] if 0 <= selected_index < len(options) else None
        correct_option = options[correct_index] if 0 <= correct_index < len(options) else None
        review_rows.append(
            {
                "question_id": qid,
                "question": question.get("question"),
                "selected_option_index": selected_index,
                "correct_option_index": correct_index,
                "selected_option": selected_option,
                "correct_option": correct_option,
                "is_correct": is_correct,
                "explanation": question.get("explanation"),
            }
        )

    score_pct = round((correct / max(1, len(questions))) * 100, 2)
    passing_score_pct = int(assessment_template.get("passing_score_pct") or 70)
    passed = score_pct >= passing_score_pct

    existing_assessment = _normalize_assessment_state(enrollment.get("assessment"), True)
    active_remediation = existing_assessment.get("active_remediation") if isinstance(existing_assessment.get("active_remediation"), dict) else None
    attempts = int(existing_assessment.get("attempts") or 0) + 1
    previously_passed = bool(existing_assessment.get("passed"))
    passed = bool(passed or previously_passed)
    now = _utcnow_iso()

    remediation_plan: List[Dict[str, Any]] = []
    wrong_rows = [row for row in review_rows if not row.get("is_correct")]
    for idx, row in enumerate(wrong_rows):
        module = normalized_modules[idx % len(normalized_modules)] if normalized_modules else {}
        lesson = normalized_lessons[idx % len(normalized_lessons)] if normalized_lessons else {}
        material = normalized_materials[idx % len(normalized_materials)] if normalized_materials else {}
        remediation_plan.append(
            {
                "question_id": row.get("question_id"),
                "module_id": module.get("module_id"),
                "module_title": module.get("title"),
                "lesson_id": lesson.get("lesson_id"),
                "lesson_title": lesson.get("title"),
                "material_id": material.get("material_id"),
                "material_title": material.get("title"),
                "material_url": material.get("resource_url"),
                "suggested_action": f"Review '{module.get('title', 'the module')}', replay '{lesson.get('title', 'the lesson')}', then complete '{material.get('title', 'the practice brief')}'.",
            }
        )

    remediation_outcome = None
    if active_remediation:
        baseline_score = float(active_remediation.get("baseline_score_pct") or existing_assessment.get("score_pct") or 0)
        recommendations = active_remediation.get("recommendations") if isinstance(active_remediation.get("recommendations"), list) else []
        lesson_completed_count = sum(1 for rec in recommendations if isinstance(rec, dict) and rec.get("lesson_completed"))
        material_opened_count = sum(1 for rec in recommendations if isinstance(rec, dict) and rec.get("material_opened"))
        score_improvement = round(score_pct - baseline_score, 2)
        improved_on_retake = score_improvement > 0
        completed_recommended = lesson_completed_count > 0 and material_opened_count > 0
        remediation_outcome = {
            "remediation_id": active_remediation.get("remediation_id"),
            "baseline_score_pct": baseline_score,
            "retake_score_pct": score_pct,
            "score_improvement_pct": score_improvement,
            "improved_on_retake": improved_on_retake,
            "completed_recommended_lessons": lesson_completed_count,
            "completed_recommended_materials": material_opened_count,
            "completed_recommended_actions": completed_recommended,
            "passed_on_retake": bool(passed),
            "evaluated_at": now,
        }
        await db.learn_hub_remediation_outcomes.insert_one(
            {
                "outcome_id": f"rem_outcome_{uuid.uuid4().hex[:12]}",
                "user_id": user.user_id,
                "course_id": course_id,
                **remediation_outcome,
            }
        )

    if not passed and remediation_plan:
        active_remediation = {
            "remediation_id": f"remediation_{uuid.uuid4().hex[:10]}",
            "status": "active",
            "generated_at": now,
            "baseline_score_pct": score_pct,
            "recommendations": [
                {
                    **row,
                    "lesson_completed": False,
                    "material_opened": False,
                }
                for row in remediation_plan
            ],
        }
    elif passed and active_remediation:
        active_remediation["status"] = "resolved"
        active_remediation["resolved_at"] = now

    updated_assessment = {
        "required": True,
        "passed": passed,
        "score_pct": score_pct,
        "attempts": attempts,
        "last_submitted_at": now,
        "passed_at": now if passed else existing_assessment.get("passed_at"),
        "active_remediation": active_remediation,
        "last_remediation_outcome": remediation_outcome,
    }

    completed = passed and progress_pct >= 100
    awaiting_assessment = not passed

    await db.learn_hub_enrollments.update_one(
        {"user_id": user.user_id, "course_id": course_id},
        {
            "$set": {
                "assessment": updated_assessment,
                "completed": completed,
                "awaiting_assessment": awaiting_assessment,
                "updated_at": now,
                "completed_at": now if completed else None,
            }
        },
    )

    if completed and not bool(enrollment.get("completed")):
        await _trigger_course_completion_effects(user, enrollment, course_id, progress_pct)

    return {
        "success": True,
        "course_id": course_id,
        "score_pct": score_pct,
        "passing_score_pct": passing_score_pct,
        "passed": passed,
        "attempts": attempts,
        "completed": completed,
        "correct_answers": correct,
        "total_questions": len(questions),
        "review": review_rows,
        "remediation_plan": remediation_plan,
        "remediation_outcome": remediation_outcome,
    }


@router.post("/roadmap/generate")
async def generate_skill_roadmap(request: Request, body: RoadmapRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    await _enforce_entitlement(user, "roadmap")

    timeline_months = max(1, min(12, int(body.timeline_months or 6)))
    fallback = {
        "title": f"{body.target_role} Career Roadmap",
        "timeline_months": timeline_months,
        "phases": [
            {
                "phase": "Foundation",
                "duration_weeks": max(2, (timeline_months * 4) // 3),
                "goals": ["Master fundamentals", "Build consistency"],
                "recommended_courses": ["Enterprise AI Foundations for Builders"],
            },
            {
                "phase": "Execution",
                "duration_weeks": max(2, timeline_months * 4 - max(2, (timeline_months * 4) // 3)),
                "goals": ["Ship projects", "Show portfolio outcomes"],
                "recommended_courses": ["Applied Cybersecurity for AI Teams"],
            },
        ],
        "weekly_commitment_hours": 6,
        "key_milestones": ["First project demo", "Interview-ready portfolio"],
    }

    system_message = """You are a world-class AI career coach.
Return JSON only with keys: title, timeline_months, weekly_commitment_hours, phases (array), key_milestones (array), weekly_execution (array optional).
Each phase must include: phase, duration_weeks, goals (array), recommended_courses (array)."""
    prompt = f"""Create a personalized roadmap.
Target role: {body.target_role}
Current skills: {', '.join(body.current_skills) if body.current_skills else 'Not provided'}
Timeline months: {body.timeline_months}
Build a practical, job-oriented progression."""
    roadmap_raw = await _ask_gpt_52_json(system_message, prompt, "learnhub-roadmap", fallback)
    roadmap = _normalize_roadmap_content(roadmap_raw, body.target_role, timeline_months)

    now = _utcnow_iso()
    roadmap_doc = {
        "roadmap_id": f"roadmap_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "target_role": body.target_role,
        "current_skills": body.current_skills,
        "timeline_months": timeline_months,
        "content": roadmap,
        "created_at": now,
        "updated_at": now,
    }
    await db.learn_hub_roadmaps.insert_one({**roadmap_doc})
    await _track_usage(user.user_id, "roadmap", {"target_role": body.target_role})

    return {"roadmap": roadmap_doc, "model": "gpt-4o"}


@router.post("/sandbox/execute")
async def run_sandbox(request: Request, body: SandboxRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    await _enforce_entitlement(user, "sandbox")

    fallback = {
        "result": "Simulated execution complete.",
        "output": "No runtime errors detected in safe simulation mode.",
        "insights": ["Add more tests", "Refactor into smaller functions"],
        "next_steps": ["Validate edge cases", "Benchmark complexity"],
        "execution_mode": "safe-simulated",
    }
    system_message = """You are a secure coding evaluator in a sandbox.
Return JSON only: result, output, insights(array), next_steps(array), execution_mode."""
    prompt = f"""Evaluate this coding request in a safe simulated environment.
Language: {body.language}
Prompt: {body.prompt}
Code: {body.code or 'N/A'}
Respond with concise execution simulation output and improvement hints."""
    response = await _ask_gpt_52_json(system_message, prompt, "learnhub-sandbox", fallback)

    await _track_usage(user.user_id, "sandbox", {"language": body.language})
    return {
        "sandbox": response,
        "freshness_at": _utcnow_iso(),
        "runtime": "simulated",
        "safety_guard": "enabled",
    }


@router.get("/papers/latest")
async def latest_research_papers(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    await _auto_ingest_latest_papers()
    papers = await db.learn_hub_research_papers.find({}, {"_id": 0}).sort("published_at", -1).limit(20).to_list(20)
    meta = await db.learn_hub_paper_ingest.find_one({"type": "meta"}, {"_id": 0})
    return {
        "papers": papers,
        "ingest": meta or {},
        "freshness_at": _utcnow_iso(),
    }


@router.post("/papers/{paper_id}/summarize")
async def summarize_research_paper(request: Request, paper_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    paper = await db.learn_hub_research_papers.find_one({"paper_id": paper_id}, {"_id": 0})
    if not paper:
        raise HTTPException(404, "Paper not found")

    fallback = {
        "headline": paper.get("title", "Research Summary"),
        "summary": paper.get("summary_short", "Summary unavailable."),
        "key_takeaways": ["Review full paper", "Map insights to your projects", "Discuss with mentor"],
        "application_ideas": ["Prototype feature", "Run benchmark experiment"],
    }
    system_message = """You are an AI research translator for professionals.
Return JSON only with: headline, summary, key_takeaways(array), application_ideas(array)."""
    prompt = f"""Summarize for builders and executives.
Title: {paper.get('title', '')}
Authors: {', '.join(paper.get('authors', []))}
Abstract: {paper.get('summary_short', '')}"""
    summary = await _ask_gpt_52_json(system_message, prompt, "learnhub-paper", fallback)

    await db.learn_hub_research_papers.update_one(
        {"paper_id": paper_id},
        {"$set": {"latest_summary": summary, "summary_updated_at": _utcnow_iso()}},
    )

    return {"paper_id": paper_id, "summary": summary, "model": "gpt-4o"}


@router.post("/mentor-match")
async def mentor_match(request: Request, body: MentorMatchRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    await _enforce_entitlement(user, "mentor_match")

    mentor_pool = [
        {"mentor_id": "m_001", "name": "Avery Kim", "specialty": "AI Product", "experience_years": 12, "region": "US"},
        {"mentor_id": "m_002", "name": "Noah Patel", "specialty": "Cybersecurity", "experience_years": 10, "region": "EU"},
        {"mentor_id": "m_003", "name": "Lea Martin", "specialty": "Data Science", "experience_years": 9, "region": "CA"},
        {"mentor_id": "m_004", "name": "Sofia Ibrahim", "specialty": "Growth Marketing", "experience_years": 11, "region": "MEA"},
    ]

    picks = []
    objective_lower = body.objective.lower().strip()
    for mentor in mentor_pool:
        score = 55
        specialty_lower = mentor["specialty"].lower()
        if objective_lower and any(term in objective_lower for term in specialty_lower.split()):
            score += 25
        if body.preferred_focus and body.preferred_focus.lower() in specialty_lower:
            score += 10
        picks.append({
            **mentor,
            "match_score": min(99, score),
            "reason": f"Strong alignment with {mentor['specialty']} and your objective: {body.objective}.",
        })

    picks.sort(key=lambda row: row["match_score"], reverse=True)
    top_matches = picks[:3]
    await _track_usage(user.user_id, "mentor_match", {"objective": body.objective})
    return {
        "matches": top_matches,
        "matching_engine": "ai-guided",
        "generated_at": _utcnow_iso(),
    }


def _build_fast_career_sprint_plan(
    challenge_title: str,
    objective: str,
    context: Optional[str],
    income_goal: Optional[str],
    weekly_hours: int,
) -> Dict[str, Any]:
    focus_hint = (context or objective or challenge_title).strip()
    monetization_hint = (income_goal or "Create one credible revenue signal from the sprint work.").strip()
    daily_actions = [
        {
            "day": 1,
            "focus": "Clarify the target outcome",
            "deliverable": f"One-sentence outcome statement for {challenge_title}",
            "income_move": f"Define the paid angle: {monetization_hint}",
            "productivity_move": f"Protect {max(1, weekly_hours // 3)} deep-work block(s) on your calendar.",
        },
        {
            "day": 2,
            "focus": "Map the mentor-guided execution path",
            "deliverable": f"Three-step action outline using this context: {focus_hint[:120]}",
            "income_move": "Translate the outline into one sellable offer or case-study promise.",
            "productivity_move": "Remove one blocker before starting any new task.",
        },
        {
            "day": 3,
            "focus": "Build visible proof",
            "deliverable": "Draft a portfolio artifact, teardown, or mini-demo tied to the objective.",
            "income_move": "Turn the artifact into a shareable proof-of-value post or prospecting asset.",
            "productivity_move": "Work single-threaded until the first proof asset is complete.",
        },
        {
            "day": 4,
            "focus": "Refine with real-world feedback",
            "deliverable": "Capture 3 pieces of feedback from peers, founders, or hiring signals.",
            "income_move": "Adjust your pitch based on objections or signal quality.",
            "productivity_move": "Batch feedback review in one focused session.",
        },
        {
            "day": 5,
            "focus": "Package the result",
            "deliverable": "Create a one-page summary, checklist, or before/after transformation note.",
            "income_move": "Add a clear CTA for discovery calls, audits, or consulting follow-up.",
            "productivity_move": "Template repeatable pieces to reduce future effort.",
        },
        {
            "day": 6,
            "focus": "Activate outbound momentum",
            "deliverable": "Send the packaged result to 5 targeted people or communities.",
            "income_move": "Track replies, discovery signals, and buying intent.",
            "productivity_move": "Use one outreach window instead of constant checking.",
        },
        {
            "day": 7,
            "focus": "Review and compound",
            "deliverable": "Write a short retro: what worked, what converted, what to repeat next week.",
            "income_move": "Pick the highest-signal revenue action and schedule the next sprint around it.",
            "productivity_move": "Lock next week's first high-leverage task before ending the sprint.",
        },
    ]
    return {
        "title": f"{challenge_title} — 7-Day Career Sprint",
        "north_star_metric": "One visible execution asset plus one concrete revenue signal",
        "daily_actions": daily_actions,
        "expected_outcomes": [
            "A clearer professional positioning narrative",
            "A publishable or shareable proof-of-work asset",
            "At least one monetization or opportunity signal",
        ],
        "execution_scorecard": ["deep_work_blocks", "proof_assets_published", "outreach_sent", "revenue_signals"],
    }


@router.get("/habit-loop/summary")
async def habit_loop_summary(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    streak = await _compute_streak(user.user_id)
    summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    return {
        "generated_at": _utcnow_iso(),
        "streak": streak,
        "summary": summary,
    }


@router.post("/habit-loop/missions/{mission_key}/complete")
async def habit_loop_complete_mission(request: Request, mission_key: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    day = datetime.now(timezone.utc).date().isoformat()
    now_iso = _utcnow_iso()
    await _ensure_daily_habit_missions(user.user_id, day)

    updated = await db.learn_hub_daily_missions.update_one(
        {"user_id": user.user_id, "day": day, "mission_key": mission_key},
        {
            "$set": {
                "manual_override": True,
                "completed": True,
                "completed_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )
    if updated.matched_count == 0:
        raise HTTPException(404, "Mission not found")

    streak = await _compute_streak(user.user_id)
    summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    await _track_growth_event(user.user_id, "mission_completed", {"mission_key": mission_key, "day": day})

    wallet_award = {"granted": False, "tokens": int((summary.get("streak_insurance") or {}).get("tokens", 0) or 0)}

    if summary.get("all_completed"):
        wallet_award = await _grant_streak_insurance_token_if_eligible(user.user_id, day)
        if wallet_award.get("granted"):
            summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
        try:
            await emit_notification(
                user_id=user.user_id,
                notif_type="learning_hub_milestone",
                title="Daily momentum complete",
                body="All daily missions completed. Your habit streak multiplier is active.",
                action_url="/ai-learning-hub",
            )
        except Exception:
            pass

    return {
        "success": True,
        "mission_key": mission_key,
        "summary": summary,
        "wallet_award": wallet_award,
    }


@router.post("/habit-loop/check-in")
async def habit_loop_check_in(request: Request, body: HabitCheckInRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    day = now.date().isoformat()

    checkin_doc = {
        "checkin_id": f"lh_checkin_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "day": day,
        "mood_score": body.mood_score,
        "focus_score": body.focus_score,
        "blocker": (body.blocker or "").strip()[:300],
        "available_minutes": int(body.available_minutes),
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.learn_hub_habit_checkins.insert_one({**checkin_doc})

    fallback = {
        "micro_plan": [
            "Start with a 10-minute focus block on your highest-value module.",
            "Finish one mission before checking messages.",
            "Log one concrete career deliverable before end of day.",
        ],
        "recovery_action": "Run a short execution sprint and avoid context switching for 25 minutes.",
        "coach_message": "Small wins create compounding career momentum.",
    }
    system_message = """You are an adaptive performance coach.
Return JSON only with keys: micro_plan(array), recovery_action, coach_message."""
    prompt = f"""Create an adaptive micro-plan.
Mood score (1-5): {body.mood_score}
Focus score (1-5): {body.focus_score}
Blocker: {body.blocker or 'none'}
Available minutes: {body.available_minutes}
User objective: daily learning consistency with career growth."""
    coach = await _ask_gpt_52_json(system_message, prompt, "learnhub-checkin", fallback)

    await _ensure_daily_habit_missions(user.user_id, day)
    await db.learn_hub_daily_missions.update_one(
        {"user_id": user.user_id, "day": day, "mission_key": "daily_check_in"},
        {
            "$set": {
                "progress": 1,
                "completed": True,
                "completed_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )

    streak = await _compute_streak(user.user_id)
    summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    await _track_growth_event(
        user.user_id,
        "habit_checkin",
        {"mood_score": body.mood_score, "focus_score": body.focus_score, "day": day},
    )

    return {
        "checkin": checkin_doc,
        "coach": coach,
        "summary": summary,
    }


@router.post("/career-sprints/solve")
async def solve_career_sprint(request: Request, body: CareerSprintSolveRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    challenge_title = body.challenge_title.strip()
    objective = body.objective.strip()
    if not challenge_title or not objective:
        raise HTTPException(400, "challenge_title and objective are required")

    fallback = _build_fast_career_sprint_plan(
        challenge_title=challenge_title,
        objective=objective,
        context=body.context,
        income_goal=body.income_goal,
        weekly_hours=int(body.weekly_hours or 6),
    )

    system_message = """You are an elite career execution strategist.
Return JSON only with keys: title, north_star_metric, daily_actions(array), expected_outcomes(array), execution_scorecard(array).
Each daily_actions item must include day, focus, deliverable, income_move, productivity_move."""
    prompt = f"""Create a premium sprint plan.
Challenge title: {challenge_title}
Objective: {objective}
Context: {body.context or 'general career acceleration'}
Weekly hours available: {body.weekly_hours}
Income goal: {body.income_goal or 'not specified'}
Produce practical, real-world and monetization-aware daily actions."""
    use_fast_path = challenge_title.lower().startswith("mentor-guided sprint with") or "mentor-guided" in objective.lower()
    sprint_plan = fallback if use_fast_path else await _ask_gpt_52_json(system_message, prompt, "learnhub-career-sprint", fallback)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    day = now.date().isoformat()
    sprint_doc = {
        "sprint_id": f"lh_sprint_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "challenge_title": challenge_title,
        "objective": objective,
        "context": body.context,
        "weekly_hours": body.weekly_hours,
        "income_goal": body.income_goal,
        "plan": sprint_plan,
        "created_day": day,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.learn_hub_career_sprints.insert_one({**sprint_doc})
    await _track_growth_event(
        user.user_id,
        "career_sprint_generated",
        {"sprint_id": sprint_doc.get("sprint_id"), "weekly_hours": body.weekly_hours, "day": day},
    )

    await _ensure_daily_habit_missions(user.user_id, day)
    await db.learn_hub_daily_missions.update_one(
        {"user_id": user.user_id, "day": day, "mission_key": "career_sprint"},
        {
            "$set": {
                "progress": 1,
                "completed": True,
                "completed_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )

    try:
        await emit_notification(
            user_id=user.user_id,
            notif_type="learning_hub_update",
            title="Career sprint generated",
            body="Your AI career sprint is ready with income and productivity actions.",
            action_url="/ai-learning-hub",
        )
    except Exception:
        pass

    return {
        "sprint": sprint_doc,
        "model": "gpt-4o",
        "generated_at": now_iso,
    }


@router.get("/career-sprints/latest")
async def latest_career_sprint(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    sprint = await db.learn_hub_career_sprints.find_one(
        {"user_id": user.user_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    return {
        "has_sprint": bool(sprint),
        "sprint": sprint,
        "generated_at": _utcnow_iso(),
    }


@router.get("/recovery-copilot/plan")
async def recovery_copilot_plan(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    payload = await _build_recovery_copilot_payload(user)
    return payload


@router.post("/recovery-copilot/apply")
async def recovery_copilot_apply(request: Request, body: RecoveryCopilotApplyRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    action_id = str(body.action_id or "").strip().lower()
    if not action_id:
        raise HTTPException(400, "action_id is required")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    day = now.date().isoformat()

    result: Dict[str, Any] = {"action_id": action_id, "applied": False}

    if action_id == "complete_next_mission":
        await _ensure_daily_habit_missions(user.user_id, day)
        pending = await db.learn_hub_daily_missions.find_one(
            {"user_id": user.user_id, "day": day, "completed": False},
            {"_id": 0},
            sort=[("created_at", 1)],
        )
        if pending:
            await db.learn_hub_daily_missions.update_one(
                {"mission_id": pending.get("mission_id")},
                {
                    "$set": {
                        "progress": int(pending.get("target", 1) or 1),
                        "completed": True,
                        "completed_at": now_iso,
                        "updated_at": now_iso,
                    }
                },
            )
            result.update({"applied": True, "mission_key": pending.get("mission_key")})
    elif action_id == "generate_recovery_sprint":
        objective = str(body.objective or "Recover consistency and ship one visible outcome this week").strip()
        challenge_title = "Recovery Sprint — Rebuild Momentum"
        sprint_plan = _build_fast_career_sprint_plan(
            challenge_title=challenge_title,
            objective=objective,
            context="AI Learning Recovery Copilot",
            income_goal="Restore weekly consistency and output",
            weekly_hours=6,
        )
        sprint_doc = {
            "sprint_id": f"lh_sprint_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "challenge_title": challenge_title,
            "objective": objective,
            "context": "AI Learning Recovery Copilot",
            "weekly_hours": 6,
            "income_goal": "Restore weekly consistency and output",
            "plan": sprint_plan,
            "created_day": day,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await db.learn_hub_career_sprints.insert_one({**sprint_doc})
        await _ensure_daily_habit_missions(user.user_id, day)
        await db.learn_hub_daily_missions.update_one(
            {"user_id": user.user_id, "day": day, "mission_key": "career_sprint"},
            {"$set": {"progress": 1, "completed": True, "completed_at": now_iso, "updated_at": now_iso}},
        )
        result.update({"applied": True, "sprint": sprint_doc})
    elif action_id == "book_intro_session":
        result.update({"applied": True, "action_url": "/book-meeting"})
    else:
        raise HTTPException(400, "Unsupported action_id")

    summary = await _build_recovery_copilot_payload(user)
    return {**result, "summary": summary, "updated_at": _utcnow_iso()}


@router.post("/habit-loop/streak-insurance/redeem")
async def redeem_streak_insurance(request: Request, body: StreakInsuranceRedeemRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    now = datetime.now(timezone.utc)
    default_day = (now.date().fromordinal(now.date().toordinal() - 1)).isoformat()
    target_day = (body.target_day or default_day).strip()

    try:
        datetime.fromisoformat(target_day)
    except Exception:
        raise HTTPException(400, "target_day must be an ISO date (YYYY-MM-DD)")

    activity = await db.learn_hub_daily_activity.find_one(
        {"user_id": user.user_id, "day": target_day},
        {"_id": 0, "minutes": 1},
    ) or {}
    if int(activity.get("minutes", 0) or 0) > 0:
        raise HTTPException(400, "Target day already has activity, insurance not required")

    wallet = await _get_streak_insurance_wallet(user.user_id)
    if int(wallet.get("tokens", 0) or 0) <= 0:
        raise HTTPException(400, "No streak insurance tokens available")

    existing = await db.learn_hub_streak_insurance_redeems.find_one(
        {"user_id": user.user_id, "insured_day": target_day, "status": "applied"},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(400, "Insurance already applied for this day")

    now_iso = now.isoformat()
    redeem_doc = {
        "redeem_id": f"lh_insurance_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "insured_day": target_day,
        "status": "applied",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.learn_hub_streak_insurance_redeems.insert_one({**redeem_doc})
    await db.learn_hub_streak_insurance_wallet.update_one(
        {"user_id": user.user_id},
        {
            "$inc": {"tokens": -1},
            "$set": {"last_redeemed_day": target_day, "updated_at": now_iso},
            "$setOnInsert": {"wallet_id": f"lh_streak_wallet_{uuid.uuid4().hex[:10]}", "created_at": now_iso},
        },
        upsert=True,
    )
    await _track_growth_event(user.user_id, "streak_insurance_redeemed", {"insured_day": target_day})

    streak = await _compute_streak(user.user_id)
    summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    return {
        "success": True,
        "insured_day": target_day,
        "wallet": await _get_streak_insurance_wallet(user.user_id),
        "streak": streak,
        "summary": summary,
    }


@router.get("/opportunity-radar")
async def opportunity_radar(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    radar = await _get_opportunity_radar(user)
    return {
        "generated_at": _utcnow_iso(),
        "radar": radar,
    }


@router.post("/opportunity-radar/{opportunity_id}/activate")
async def activate_opportunity(request: Request, opportunity_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    radar = await db.learn_hub_opportunity_radar.find_one(
        {"user_id": user.user_id, "day": day},
        {"_id": 0, "opportunities": 1},
    ) or await _get_opportunity_radar(user)
    opportunities = radar.get("opportunities") or []
    selected = next((o for o in opportunities if str(o.get("opportunity_id")) == opportunity_id), None)
    if not selected:
        raise HTTPException(404, "Opportunity not found")

    activation_doc = {
        "activation_id": f"lh_opp_act_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "opportunity_id": opportunity_id,
        "opportunity": selected,
        "day": day,
        "created_at": now.isoformat(),
    }
    await db.learn_hub_opportunity_activations.insert_one({**activation_doc})
    await _track_growth_event(user.user_id, "opportunity_activated", {"opportunity_id": opportunity_id, "day": day})

    return {
        "success": True,
        "activation": activation_doc,
    }


@router.get("/income-experiments")
async def list_income_experiments(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    rows = await db.learn_hub_income_experiments.find(
        {"user_id": user.user_id},
        {"_id": 0},
    ).sort("updated_at", -1).limit(80).to_list(80)
    return {
        "experiments": rows,
        "generated_at": _utcnow_iso(),
    }


@router.post("/income-experiments")
async def create_income_experiment(request: Request, body: IncomeExperimentCreateRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    title = body.title.strip()
    hypothesis = body.hypothesis.strip()
    if not title or not hypothesis:
        raise HTTPException(400, "title and hypothesis are required")

    now_iso = _utcnow_iso()
    doc = {
        "experiment_id": f"lh_exp_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "title": title,
        "hypothesis": hypothesis,
        "execution_plan": (body.execution_plan or "").strip(),
        "effort_hours": body.effort_hours,
        "status": "active",
        "revenue_delta": 0,
        "logs": [],
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.learn_hub_income_experiments.insert_one({**doc})
    await _track_growth_event(user.user_id, "income_experiment_created", {"experiment_id": doc["experiment_id"]})
    return {"success": True, "experiment": doc}


@router.post("/income-experiments/{experiment_id}/log")
async def log_income_experiment(request: Request, experiment_id: str, body: IncomeExperimentLogRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    row = await db.learn_hub_income_experiments.find_one(
        {"user_id": user.user_id, "experiment_id": experiment_id},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Experiment not found")

    now_iso = _utcnow_iso()
    log_entry = {
        "logged_at": now_iso,
        "status": body.status,
        "revenue_delta": body.revenue_delta,
        "insight": (body.insight or "").strip()[:600],
    }
    await db.learn_hub_income_experiments.update_one(
        {"user_id": user.user_id, "experiment_id": experiment_id},
        {
            "$set": {
                "status": body.status,
                "revenue_delta": body.revenue_delta,
                "updated_at": now_iso,
            },
            "$push": {"logs": log_entry},
        },
    )
    await _track_growth_event(user.user_id, "income_experiment_logged", {"experiment_id": experiment_id, "status": body.status})

    updated = await db.learn_hub_income_experiments.find_one(
        {"user_id": user.user_id, "experiment_id": experiment_id},
        {"_id": 0},
    )
    return {
        "success": True,
        "experiment": updated,
    }


@router.get("/videos/{course_id}/{lesson_id}/resolve")
async def resolve_course_video(request: Request, course_id: str, lesson_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    course = await db.learn_hub_courses.find_one({"course_id": course_id}, {"_id": 0, "video_lessons": 1, "title": 1})
    if not course:
        raise HTTPException(404, "Course not found")

    lesson = None
    for row in (course.get("video_lessons") or []):
        if str(row.get("lesson_id") or "") == lesson_id:
            lesson = row
            break
    if not lesson:
        raise HTTPException(404, "Video lesson not found")

    playback_url = str(lesson.get("fallback_url") or lesson.get("playback_url") or "").strip()
    if not playback_url:
        raise HTTPException(404, "No playable video URL configured")

    return {
        "course_id": course_id,
        "lesson_id": lesson_id,
        "title": lesson.get("title"),
        "provider": lesson.get("provider"),
        "playback_url": playback_url,
        "fallback_url": lesson.get("fallback_url"),
        "health_status": lesson.get("health_status", "unknown"),
        "last_checked_at": lesson.get("last_checked_at"),
    }


class CertificateRevocationRequest(BaseModel):
    reason: str = Field(default="Revoked by administrator", max_length=240)


class CertificateEngagementEventRequest(BaseModel):
    event_type: str
    source: str = "unknown"
    viewer_session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CertificateTemplateUpdateRequest(BaseModel):
    settings: Dict[str, float] = Field(default_factory=dict)
    typography_preset: Optional[str] = None


class CertificatePrintLayoutPreferenceRequest(BaseModel):
    layout: str = Field(default="portrait", max_length=24)


@router.post("/certificates/{course_id}/issue")
async def issue_certificate(request: Request, course_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    await _enforce_entitlement(user, "certificate_issue")

    enrollment = await db.learn_hub_enrollments.find_one({"user_id": user.user_id, "course_id": course_id}, {"_id": 0})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    if not enrollment.get("completed"):
        raise HTTPException(400, "Course must be completed before certificate issuance")
    result = await _issue_or_get_certificate_for_user(
        user_id=user.user_id,
        user_name=str(getattr(user, "name", "") or "Learner"),
        user_email=str(getattr(user, "email", "") or ""),
        course_id=course_id,
        course_title=str(enrollment.get("course_title") or "AI Learning Course"),
        triggered_by="manual_issue",
    )
    certificate_doc = result.get("certificate") or {}
    cert_sent = await _dispatch_certificate_completion_email(certificate_doc)
    if cert_sent:
        await db.learn_hub_certificates.update_one(
            {"certificate_id": certificate_doc.get("certificate_id")},
            {"$set": {"completion_email_sent_at": _utcnow_iso(), "updated_at": _utcnow_iso()}},
        )

    return {
        "certificate": _normalized_certificate_payload(certificate_doc),
        "already_issued": bool(result.get("already_issued")),
    }


@router.get("/certificates")
async def my_certificates(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    rows = await db.learn_hub_certificates.find({"user_id": user.user_id}, {"_id": 0}).sort("issued_at", -1).to_list(80)
    normalized = []
    for row in rows:
        shaped = await _ensure_certificate_record_shape(row)
        normalized.append(_normalized_certificate_payload(shaped))
    return {"certificates": normalized, "total": len(normalized)}


@router.get("/certificates/print-layout-preference")
async def get_certificate_print_layout_preference(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    pref = await db.user_preferences.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "certificate_print_layout": 1, "key": 1, "value": 1},
    )
    stored_layout = (pref or {}).get("certificate_print_layout")
    if not stored_layout and (pref or {}).get("key") == "certificate_print_layout":
        stored_layout = (pref or {}).get("value")
    return {
        "layout": _normalize_certificate_layout(stored_layout),
        "saved": bool(stored_layout),
    }


@router.put("/certificates/print-layout-preference")
async def set_certificate_print_layout_preference(request: Request, body: CertificatePrintLayoutPreferenceRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    layout = _normalize_certificate_layout(body.layout)
    now_iso = _utcnow_iso()
    await db.user_preferences.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "user_id": user.user_id,
                "certificate_print_layout": layout,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )
    return {"success": True, "layout": layout, "updated_at": now_iso}


@router.post("/certificates/verify/{verification_id}/engagement")
async def track_certificate_engagement(verification_id: str, body: CertificateEngagementEventRequest, request: Request):
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "certificate_engagement", 30, 60)
    if blocked is not None:
        return blocked

    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")

    event_type = str(body.event_type or "").strip().lower()
    allowed_events = {"verifier_view", "secure_link_copy", "linkedin_share_click", "pdf_open", "png_export", "earn_yours_click"}
    if event_type not in allowed_events:
        raise HTTPException(400, "Unsupported engagement event")

    now_iso = _utcnow_iso()
    await db.learn_hub_certificate_engagement_events.insert_one(
        {
            "event_id": f"cert_eng_{uuid.uuid4().hex[:12]}",
            "certificate_id": cert.get("certificate_id"),
            "verification_id": verification_id,
            "course_id": cert.get("course_id"),
            "user_id": cert.get("user_id"),
            "event_type": event_type,
            "source": str(body.source or "unknown")[:60],
            "viewer_session_id": str(body.viewer_session_id or "")[:120],
            "metadata": body.metadata or {},
            "created_at": now_iso,
            "day": now_iso[:10],
        }
    )
    return {"ok": True, "event_type": event_type, "tracked_at": now_iso}


@router.get("/certificates/verify/{verification_id}")
async def verify_certificate(verification_id: str):
    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        return JSONResponse({"valid": False, "message": "Certificate not found"}, status_code=404)

    cert = await _ensure_certificate_record_shape(cert)
    payload = _normalized_certificate_payload(cert)
    return {
        **payload,
        "valid": bool(payload.get("is_active")),
        "db_signature_valid": bool(payload.get("is_authentic")),
        "verification_id_masked": _mask_verification_id(cert.get("verification_id", "")),
        "issuer": cert.get("issued_by"),
        "chain": (payload.get("anchoring") or {}).get("chain_target"),
        "anchor_tx_hash": (payload.get("anchoring") or {}).get("anchor_tx_hash"),
        "merkle_root": (payload.get("anchoring") or {}).get("merkle_root"),
        "proof_path": (payload.get("anchoring") or {}).get("merkle_proof") or [],
        "anchor_timestamp": (payload.get("anchoring") or {}).get("anchored_at"),
    }


@router.get("/certificates/verify/{verification_id}/pdf/file")
async def public_certificate_pdf_file(request: Request, verification_id: str):
    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if not _certificate_signature_is_valid(cert):
        raise HTTPException(409, "Certificate record could not be validated")

    variant = str(request.query_params.get("variant") or "print").lower()
    layout = str(request.query_params.get("layout") or "portrait").lower()
    pdf_bytes, media_type = await _load_certificate_asset_bytes(cert, "pdf", variant, layout=layout)
    filename = build_pdf_v15_filename(
        "certificate",
        f"{verification_id}-{layout if layout in {'portrait', 'landscape'} else 'portrait'}",
    )
    return Response(
        content=pdf_bytes,
        media_type=media_type,
        headers=_certificate_asset_headers(filename, "inline"),
    )


@router.get("/certificates/verify/{verification_id}/png/file")
async def public_certificate_png_file(request: Request, verification_id: str):
    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if not _certificate_signature_is_valid(cert):
        raise HTTPException(409, "Certificate record could not be validated")

    variant = str(request.query_params.get("variant") or "print").lower()
    layout = str(request.query_params.get("layout") or "portrait").lower()
    normalized_layout = layout if layout in {"portrait", "landscape"} else "portrait"
    png_bytes, media_type = await _load_certificate_asset_bytes(cert, "png", variant, layout=normalized_layout)
    filename = f"realaicoach-certificate-{verification_id}-{normalized_layout}.png"
    disposition = "inline" if variant in {"web", "thumb"} else "attachment"
    return Response(
        content=png_bytes,
        media_type=media_type,
        headers=_certificate_asset_headers(filename, disposition),
    )


@router.get("/certificates/verify/{verification_id}/social-preview.svg")
async def verify_certificate_social_preview(verification_id: str):
    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})

    if not cert:
        verification_masked = _mask_verification_id(verification_id)
        svg = f"""
<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Certificate verification unavailable">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0F172A"/>
      <stop offset="100%" stop-color="#1E293B"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <text x="80" y="130" fill="#E2E8F0" font-size="34" font-family="Arial, sans-serif" font-weight="700">RealAICoach Certificate Verifier</text>
  <text x="80" y="220" fill="#FCA5A5" font-size="44" font-family="Arial, sans-serif" font-weight="800">INVALID OR NOT FOUND</text>
  <text x="80" y="290" fill="#CBD5E1" font-size="26" font-family="Arial, sans-serif">Verification ID: {html.escape(verification_masked)}</text>
  <text x="80" y="560" fill="#94A3B8" font-size="22" font-family="Arial, sans-serif">Public trust metadata • privacy-safe preview</text>
</svg>
""".strip()
        return Response(content=svg, media_type="image/svg+xml")

    cert = await _ensure_certificate_record_shape(cert)
    payload = _normalized_certificate_payload(cert)
    anchoring = payload.get("anchoring") or {}

    course_title = html.escape(str(cert.get("course_title") or "Certificate"))
    chain_name = html.escape(str(anchoring.get("chain_target") or "--"))
    status_label = str(payload.get("status_label") or "Valid").upper()
    status_color = {
        CERTIFICATE_STATUS_VALID: "#22C55E",
        CERTIFICATE_STATUS_EXPIRED: "#F59E0B",
        CERTIFICATE_STATUS_REVOKED: "#EF4444",
        CERTIFICATE_STATUS_INVALID: "#F87171",
    }.get(str(payload.get("status") or CERTIFICATE_STATUS_INVALID), "#F87171")
    anchor_label = "ANCHORED" if anchoring.get("status") == "anchored" else str(anchoring.get("status") or "NOT_QUEUED").upper()
    verification_masked = _mask_verification_id(cert.get("verification_id", ""))

    svg = f"""
<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Certificate verification status">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0B1220"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="70" y="70" rx="18" ry="18" width="1060" height="490" fill="#111827" stroke="#334155" stroke-width="2"/>
  <text x="110" y="140" fill="#E2E8F0" font-size="34" font-family="Arial, sans-serif" font-weight="700">RealAICoach Public Certificate Verifier</text>
  <text x="110" y="215" fill="{status_color}" font-size="52" font-family="Arial, sans-serif" font-weight="800">{status_label}</text>
  <text x="110" y="275" fill="#CBD5E1" font-size="28" font-family="Arial, sans-serif">Course: {course_title}</text>
  <text x="110" y="325" fill="#94A3B8" font-size="24" font-family="Arial, sans-serif">Verification ID: {html.escape(verification_masked)}</text>
  <text x="110" y="375" fill="#94A3B8" font-size="24" font-family="Arial, sans-serif">Chain: {chain_name}</text>
  <text x="110" y="425" fill="#94A3B8" font-size="24" font-family="Arial, sans-serif">Anchor Status: {html.escape(anchor_label)}</text>
  <text x="110" y="535" fill="#64748B" font-size="20" font-family="Arial, sans-serif">Privacy-safe trust preview • No personal learner data exposed</text>
</svg>
""".strip()

    return Response(content=svg, media_type="image/svg+xml")


@router.get("/certificates/{verification_id}/pdf")
async def certificate_pdf(request: Request, verification_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if cert.get("user_id") != user.user_id and not user.is_admin:
        raise HTTPException(403, "Forbidden")

    variant = str(request.query_params.get("variant") or "print").lower()
    layout = str(request.query_params.get("layout") or "portrait").lower()
    pdf_bytes, _ = await _load_certificate_asset_bytes(cert, "pdf", variant, layout=layout)
    pdf_base64 = base64.b64encode(pdf_bytes).decode()
    filename = build_pdf_v15_filename(
        "certificate",
        f"{verification_id}-{layout if layout in {'portrait', 'landscape'} else 'portrait'}",
    )
    return {"filename": filename, "pdf_base64": pdf_base64}


@router.get("/certificates/{verification_id}/pdf/file")
async def certificate_pdf_file(request: Request, verification_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if cert.get("user_id") != user.user_id and not user.is_admin:
        raise HTTPException(403, "Forbidden")

    variant = str(request.query_params.get("variant") or "print").lower()
    layout = str(request.query_params.get("layout") or "portrait").lower()
    pdf_bytes, media_type = await _load_certificate_asset_bytes(cert, "pdf", variant, layout=layout)
    filename = build_pdf_v15_filename(
        "certificate",
        f"{verification_id}-{layout if layout in {'portrait', 'landscape'} else 'portrait'}",
    )
    return Response(
        content=pdf_bytes,
        media_type=media_type,
        headers=_certificate_asset_headers(filename, "inline"),
    )


@router.get("/certificates/{verification_id}/png/file")
async def certificate_png_file(request: Request, verification_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if cert.get("user_id") != user.user_id and not user.is_admin:
        raise HTTPException(403, "Forbidden")

    variant = str(request.query_params.get("variant") or "print").lower()
    layout = str(request.query_params.get("layout") or "portrait").lower()
    normalized_layout = layout if layout in {"portrait", "landscape"} else "portrait"
    png_bytes, media_type = await _load_certificate_asset_bytes(cert, "png", variant, layout=normalized_layout)
    filename = f"realaicoach-certificate-{verification_id}-{normalized_layout}.png"
    disposition = "inline" if variant in {"web", "thumb"} else "attachment"
    return Response(
        content=png_bytes,
        media_type=media_type,
        headers=_certificate_asset_headers(filename, disposition),
    )


@router.get("/certificates/download-all/bundle")
async def download_all_certificates_bundle(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    layout = str(request.query_params.get("layout") or "portrait").strip().lower()
    normalized_layout = layout if layout in {"portrait", "landscape"} else "portrait"

    cert_rows = await db.learn_hub_certificates.find(
        {"user_id": user.user_id},
        {"_id": 0},
    ).sort("issued_at", -1).limit(200).to_list(200)

    if not cert_rows:
        raise HTTPException(404, "No certificates available")

    zip_buffer = io.BytesIO()
    manifest_rows: List[Dict[str, Any]] = []

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for idx, cert in enumerate(cert_rows, start=1):
            cert = await _ensure_certificate_record_shape(cert)
            payload = _normalized_certificate_payload(cert)
            verification_id = str(payload.get("verification_id") or "")
            course_title = str(payload.get("course_title") or "course")
            safe_course = _slugify(course_title)[:64]
            pdf_name = f"certificates/{idx:03d}-{safe_course}-{verification_id or idx}.pdf"

            row_status = "included"
            row_error = ""
            try:
                pdf_bytes, _ = await _load_certificate_asset_bytes(cert, "pdf", "print", layout=normalized_layout)
                archive.writestr(pdf_name, pdf_bytes)
            except Exception as exc:
                row_status = "failed"
                row_error = str(exc)[:180]

            manifest_rows.append(
                {
                    "index": idx,
                    "verification_id": verification_id,
                    "certificate_number": str(payload.get("certificate_number") or ""),
                    "course_title": course_title,
                    "status": str(payload.get("status") or ""),
                    "issued_at": str(payload.get("issued_at") or ""),
                    "archive_path": pdf_name if row_status == "included" else "",
                    "bundle_status": row_status,
                    "error": row_error,
                }
            )

        csv_buffer = io.StringIO()
        fieldnames = [
            "index",
            "verification_id",
            "certificate_number",
            "course_title",
            "status",
            "issued_at",
            "archive_path",
            "bundle_status",
            "error",
        ]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(row)

        archive.writestr("manifest/certificates_manifest.csv", csv_buffer.getvalue())
        archive.writestr(
            "manifest/summary.json",
            json.dumps(
                {
                    "generated_at": _utcnow_iso(),
                    "layout": normalized_layout,
                    "total": len(manifest_rows),
                    "included": sum(1 for row in manifest_rows if row.get("bundle_status") == "included"),
                    "failed": sum(1 for row in manifest_rows if row.get("bundle_status") == "failed"),
                },
                indent=2,
            ),
        )

    filename = f"realaicoach-certificates-{_slugify(str(user.user_id))}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/my-learning-center")
async def my_learning_center(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    enrollments = await db.learn_hub_enrollments.find({"user_id": user.user_id}, {"_id": 0}).sort("updated_at", -1).limit(120).to_list(120)
    course_ids = [str(row.get("course_id") or "") for row in enrollments if row.get("course_id")]
    course_docs: Dict[str, Dict[str, Any]] = {}
    if course_ids:
        rows = await db.learn_hub_courses.find(
            {"course_id": {"$in": course_ids}},
            {
                "_id": 0,
                "course_id": 1,
                "title": 1,
                "subcategory": 1,
                "video_lessons": 1,
                "modules": 1,
                "learning_materials": 1,
                "final_assessment": 1,
                "duration_hours": 1,
                "difficulty": 1,
                "category": 1,
            },
        ).to_list(400)
        for row in rows:
            if row.get("course_id"):
                course_docs[str(row.get("course_id"))] = row

    lesson_progress_rows = await db.learn_hub_lesson_progress.find(
        {"user_id": user.user_id, "course_id": {"$in": course_ids}} if course_ids else {"user_id": user.user_id, "course_id": "__none__"},
        {"_id": 0},
    ).to_list(1200)
    lesson_progress_by_course: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in lesson_progress_rows:
        c_id = str(row.get("course_id") or "")
        l_id = str(row.get("lesson_id") or "")
        if not c_id or not l_id:
            continue
        lesson_progress_by_course.setdefault(c_id, {})[l_id] = {
            "watch_seconds": float(row.get("watch_seconds") or 0),
            "total_seconds": float(row.get("total_seconds") or 0),
            "watched_pct": float(row.get("watched_pct") or 0),
            "completed": bool(row.get("completed")),
            "last_position_seconds": float(row.get("last_position_seconds") or 0),
            "last_watch_event_at": row.get("last_watch_event_at"),
            "resume_label": _format_duration_mmss(row.get("last_position_seconds") or row.get("watch_seconds") or 0),
        }
    certificates = await db.learn_hub_certificates.find({"user_id": user.user_id}, {"_id": 0}).sort("issued_at", -1).limit(40).to_list(40)
    roadmap = await db.learn_hub_roadmaps.find_one({"user_id": user.user_id}, {"_id": 0}, sort=[("created_at", -1)])
    streak = await _compute_streak(user.user_id)
    habit_summary = await _build_habit_loop_summary(user, streak_snapshot=streak)
    latest_sprint = await db.learn_hub_career_sprints.find_one(
        {"user_id": user.user_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    assurance_runtime = await db.learn_hub_assurance_runtime.find_one({"key": "learning_hub_assurance_runtime"}, {"_id": 0}) or {}

    normalized_certificates = []
    for cert in certificates:
        shaped = await _ensure_certificate_record_shape(cert)
        normalized_certificates.append(_normalized_certificate_payload(shaped))

    enriched_enrollments: List[Dict[str, Any]] = []
    for enrollment in enrollments:
        course_id = str(enrollment.get("course_id") or "")
        course_doc = course_docs.get(course_id, {})
        modules = enrollment.get("modules") if isinstance(enrollment.get("modules"), list) else _normalize_modules(course_doc.get("modules"))
        topic = str(course_doc.get("subcategory") or enrollment.get("course_title") or "AI")
        normalized_video_lessons = _normalize_video_lessons(course_id or uuid.uuid4().hex[:8], topic, course_doc.get("video_lessons"), min_count=5)
        watch_state_map = lesson_progress_by_course.get(course_id, {})
        enriched_video_lessons = []
        for lesson in normalized_video_lessons:
            lesson_id = str(lesson.get("lesson_id") or "")
            watch_state = watch_state_map.get(lesson_id, {})
            enriched_video_lessons.append(
                {
                    **lesson,
                    "watch_state": watch_state,
                    "resume_label": watch_state.get("resume_label") or "0:00",
                    "watched_pct": float(watch_state.get("watched_pct") or 0),
                }
            )
        topic_alignment_pct = round(
            (
                sum(float(lesson.get("topic_alignment_score") or 0) for lesson in enriched_video_lessons)
                / max(1, len(enriched_video_lessons))
            )
            * 100,
            2,
        )
        topic_mismatch_count = sum(
            1 for lesson in enriched_video_lessons if str(lesson.get("topic_alignment_status") or "") != "aligned"
        )
        normalized_materials = _normalize_learning_materials(course_id or uuid.uuid4().hex[:8], topic, modules, course_doc.get("learning_materials"))
        normalized_assessment = _normalize_final_assessment(course_id or uuid.uuid4().hex[:8], topic, modules, course_doc.get("final_assessment"))
        assessment_required = bool((normalized_assessment.get("questions") or []))
        assessment_state = _normalize_assessment_state(enrollment.get("assessment"), assessment_required)
        if bool(enrollment.get("completed")) and not bool(assessment_state.get("passed")):
            assessment_state["passed"] = True
            assessment_state["score_pct"] = max(float(assessment_state.get("score_pct") or 0), float(normalized_assessment.get("passing_score_pct") or 70))
            assessment_state["passed_at"] = assessment_state.get("passed_at") or _utcnow_iso()

        completed_modules = sum(1 for module in modules if module.get("completed"))
        total_modules = max(1, len(modules))
        progress_pct = float(enrollment.get("progress_pct") or 0)
        if progress_pct <= 0 and total_modules > 0:
            progress_pct = round((completed_modules / total_modules) * 100, 2)

        awaiting_assessment = bool(progress_pct >= 100 and assessment_required and not assessment_state.get("passed"))
        completed = bool(progress_pct >= 100 and (not assessment_required or assessment_state.get("passed")))

        enriched_enrollment = {
            **enrollment,
            "modules": modules,
            "progress_pct": progress_pct,
            "completed": completed,
            "awaiting_assessment": awaiting_assessment,
            "video_lessons": enriched_video_lessons,
            "learning_materials": normalized_materials,
            "final_assessment": {
                "assessment_id": normalized_assessment.get("assessment_id"),
                "title": normalized_assessment.get("title"),
                "passing_score_pct": normalized_assessment.get("passing_score_pct"),
                "questions": [
                    {
                        "question_id": q.get("question_id"),
                        "question": q.get("question"),
                        "options": q.get("options"),
                    }
                    for q in (normalized_assessment.get("questions") or [])
                ],
            },
            "assessment": assessment_state,
            "course_duration_hours": course_doc.get("duration_hours"),
            "course_difficulty": course_doc.get("difficulty"),
            "course_category": course_doc.get("category") or enrollment.get("category"),
            "lesson_watch_state": watch_state_map,
            "video_quality": {
                "topic_alignment_pct": topic_alignment_pct,
                "topic_mismatch_count": topic_mismatch_count,
                "lesson_count": len(enriched_video_lessons),
            },
        }
        enriched_enrollments.append(enriched_enrollment)

        if not isinstance(enrollment.get("assessment"), dict) or enrollment.get("awaiting_assessment") != awaiting_assessment or enrollment.get("completed") != completed:
            await db.learn_hub_enrollments.update_one(
                {"user_id": user.user_id, "course_id": course_id},
                {
                    "$set": {
                        "assessment": assessment_state,
                        "awaiting_assessment": awaiting_assessment,
                        "completed": completed,
                        "progress_pct": progress_pct,
                        "updated_at": _utcnow_iso(),
                    }
                },
            )

    return {
        "enrollments": enriched_enrollments,
        "certificates": normalized_certificates,
        "latest_roadmap": roadmap,
        "habit_loop": {
            "streak": streak,
            "summary": habit_summary,
        },
        "latest_career_sprint": latest_sprint,
        "assurance": {
            "status": assurance_runtime.get("status", "unknown"),
            "run_at": assurance_runtime.get("run_at"),
        },
        "generated_at": _utcnow_iso(),
    }


def _portfolio_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "").strip()


def _portfolio_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _append_unique_skill(skills: List[str], seen: set[str], skill: Any):
    normalized = str(skill or "").strip()
    if not normalized:
        return
    key = normalized.lower()
    if key in seen:
        return
    seen.add(key)
    skills.append(normalized)


async def _build_learner_portfolio_payload(user_id: str) -> Dict[str, Any]:
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "user_id": 1, "name": 1, "profile_image": 1},
    )
    if not user_doc:
        raise HTTPException(404, "Learner not found")

    enrollments = await db.learn_hub_enrollments.find(
        {"user_id": user_id},
        {
            "_id": 0,
            "course_id": 1,
            "course_title": 1,
            "progress_pct": 1,
            "completed": 1,
            "updated_at": 1,
            "created_at": 1,
        },
    ).sort("updated_at", -1).limit(300).to_list(300)

    certificates = await db.learn_hub_certificates.find(
        {"user_id": user_id},
        {"_id": 0},
    ).sort("issued_at", -1).limit(40).to_list(40)

    roadmap = await db.learn_hub_roadmaps.find_one(
        {"user_id": user_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )

    course_ids = [str(row.get("course_id") or "") for row in enrollments if row.get("course_id")]
    course_rows: List[Dict[str, Any]] = []
    if course_ids:
        course_rows = await db.learn_hub_courses.find(
            {"course_id": {"$in": list(set(course_ids))}},
            {"_id": 0, "course_id": 1, "title": 1, "skills": 1},
        ).to_list(500)

    course_by_id: Dict[str, Dict[str, Any]] = {
        str(row.get("course_id") or ""): row for row in course_rows if row.get("course_id")
    }

    normalized_certificates: List[Dict[str, Any]] = []
    for cert in certificates:
        shaped = await _ensure_certificate_record_shape(cert)
        payload = _normalized_certificate_payload(shaped)
        normalized_certificates.append(
            {
                "certificate_id": payload.get("certificate_id"),
                "verification_id": payload.get("verification_id"),
                "course_id": payload.get("course_id"),
                "course_title": payload.get("course_title"),
                "learner_name": payload.get("learner_name"),
                "status": payload.get("status"),
                "certificate_number": payload.get("certificate_number"),
                "issued_at": payload.get("issued_at"),
                "expiration_date": payload.get("expiration_date"),
                "preview_image_url": payload.get("preview_image_url"),
                "thumbnail_image_url": payload.get("thumbnail_image_url"),
                "public_verify_url": payload.get("public_verify_url"),
                "public_pdf_url": payload.get("public_pdf_url"),
            }
        )

    skills: List[str] = []
    seen_skills: set[str] = set()
    for row in course_rows:
        for skill in (row.get("skills") if isinstance(row.get("skills"), list) else []):
            _append_unique_skill(skills, seen_skills, skill)

    roadmap_skills = roadmap.get("current_skills") if isinstance(roadmap, dict) and isinstance(roadmap.get("current_skills"), list) else []
    for skill in roadmap_skills:
        _append_unique_skill(skills, seen_skills, skill)

    milestones: List[Dict[str, Any]] = []

    for enrollment in enrollments:
        if not bool(enrollment.get("completed")):
            continue
        title = str(enrollment.get("course_title") or course_by_id.get(str(enrollment.get("course_id") or ""), {}).get("title") or "Completed course")
        milestones.append(
            {
                "type": "course_completion",
                "title": title,
                "detail": "Course completed",
                "achieved_at": _portfolio_iso(enrollment.get("updated_at") or enrollment.get("created_at")),
            }
        )

    for cert in normalized_certificates[:16]:
        milestones.append(
            {
                "type": "certificate_issued",
                "title": str(cert.get("course_title") or "Certificate issued"),
                "detail": f"Certificate #{cert.get('certificate_number') or 'N/A'}",
                "achieved_at": _portfolio_iso(cert.get("issued_at")),
            }
        )

    roadmap_content = roadmap.get("content") if isinstance(roadmap, dict) and isinstance(roadmap.get("content"), dict) else {}
    roadmap_milestones = roadmap_content.get("key_milestones") if isinstance(roadmap_content.get("key_milestones"), list) else []
    for idx, item in enumerate(roadmap_milestones[:8]):
        label = str(item or "").strip()
        if not label:
            continue
        milestones.append(
            {
                "type": "roadmap_target",
                "title": label,
                "detail": "Career roadmap milestone",
                "achieved_at": _portfolio_iso(roadmap.get("created_at") if isinstance(roadmap, dict) else ""),
                "order": idx,
            }
        )

    milestones.sort(
        key=lambda row: (
            _portfolio_dt(row.get("achieved_at")),
            -int(row.get("order", 0)),
        ),
        reverse=True,
    )

    completed_courses = sum(1 for row in enrollments if bool(row.get("completed")))
    total_courses = len(enrollments)
    completion_rate = round((completed_courses / max(total_courses, 1)) * 100, 2) if total_courses else 0.0

    latest_updated_at = ""
    if milestones:
        latest_updated_at = _portfolio_iso(milestones[0].get("achieved_at"))
    elif normalized_certificates:
        latest_updated_at = _portfolio_iso(normalized_certificates[0].get("issued_at"))
    elif roadmap:
        latest_updated_at = _portfolio_iso(roadmap.get("created_at"))

    display_name = str(user_doc.get("name") or "").strip()
    if not display_name:
        display_name = str((normalized_certificates[0].get("learner_name") if normalized_certificates else "") or "Learner")

    return {
        "profile": {
            "user_id": str(user_doc.get("user_id") or user_id),
            "name": display_name,
            "headline": str((roadmap or {}).get("target_role") or "AI Learning Hub Learner"),
            "profile_image": user_doc.get("profile_image"),
            "share_path": f"/shared/portfolio/{quote(str(user_doc.get('user_id') or user_id))}",
        },
        "metrics": {
            "active_courses": max(total_courses - completed_courses, 0),
            "completed_courses": completed_courses,
            "completion_rate_pct": completion_rate,
            "total_certificates": len(normalized_certificates),
            "total_skills": len(skills),
            "total_milestones": len(milestones),
        },
        "skills": skills[:24],
        "milestones": milestones[:24],
        "certificates": normalized_certificates[:12],
        "latest_updated_at": latest_updated_at,
        "generated_at": _utcnow_iso(),
    }


@router.get("/portfolio/me")
async def my_portfolio(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return await _build_learner_portfolio_payload(str(user.user_id))


@router.get("/portfolio/{user_id}")
async def public_portfolio(user_id: str):
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        raise HTTPException(404, "Learner not found")
    return await _build_learner_portfolio_payload(clean_user_id)


@router.get("/admin/certificates")
async def admin_certificates(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    search = str(request.query_params.get("search") or "").strip().lower()
    status_filter = str(request.query_params.get("status") or "all").strip().lower()
    sort_mode = str(request.query_params.get("sort") or "newest").strip().lower()
    try:
        requested_limit = int(request.query_params.get("limit") or 80)
    except Exception:
        requested_limit = 80
    limit = max(10, min(requested_limit, 200))

    rows = await db.learn_hub_certificates.find({}, {"_id": 0}).sort("issued_at", -1).limit(limit * 2).to_list(limit * 2)
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        shaped = await _ensure_certificate_record_shape(row)
        payload = _normalized_certificate_payload(shaped)
        haystack = " ".join(
            [
                str(payload.get("learner_name") or ""),
                str(payload.get("course_title") or ""),
                str(payload.get("certificate_number") or ""),
                str(payload.get("verification_id") or ""),
            ]
        ).lower()
        if search and search not in haystack:
            continue
        if status_filter != "all" and str(payload.get("status") or "").lower() != status_filter:
            continue
        normalized.append(payload)

    if sort_mode == "oldest":
        normalized.sort(key=lambda row: str(row.get("issued_at") or ""))
    elif sort_mode == "course":
        normalized.sort(key=lambda row: str(row.get("course_title") or "").lower())
    elif sort_mode == "learner":
        normalized.sort(key=lambda row: str(row.get("learner_name") or "").lower())
    elif sort_mode == "status":
        normalized.sort(key=lambda row: (str(row.get("status") or ""), str(row.get("issued_at") or "")), reverse=True)
    else:
        normalized.sort(key=lambda row: str(row.get("issued_at") or ""), reverse=True)

    return {"certificates": normalized[:limit], "total": len(normalized)}


@router.get("/admin/certificate-template")
async def admin_certificate_template(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return await _get_certificate_template_settings()


@router.put("/admin/certificate-template")
async def update_admin_certificate_template(request: Request, body: CertificateTemplateUpdateRequest):
    from routes.db import require_admin

    admin = await require_admin(request)
    saved = await _save_certificate_template_settings(body.settings, admin.user_id, body.typography_preset)
    return {
        "template_id": saved.get("template_id"),
        "settings": saved.get("settings") or {},
        "typography_preset": saved.get("typography_preset"),
        "updated_at": saved.get("updated_at"),
    }


@router.post("/admin/certificate-template/reset")
async def reset_admin_certificate_template(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    saved = await _save_certificate_template_settings(
        CERTIFICATE_TEMPLATE_DEFAULTS,
        admin.user_id,
        CERTIFICATE_TYPOGRAPHY_PRESET_DEFAULT,
    )
    return {
        "template_id": saved.get("template_id"),
        "settings": saved.get("settings") or {},
        "typography_preset": saved.get("typography_preset"),
        "updated_at": saved.get("updated_at"),
        "reset": True,
    }


@router.post("/admin/certificates/{verification_id}/revoke")
async def revoke_certificate(request: Request, verification_id: str, payload: CertificateRevocationRequest):
    from routes.db import require_admin

    admin = await require_admin(request)
    cert = await db.learn_hub_certificates.find_one({"verification_id": verification_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")

    if cert.get("revoked_at"):
        shaped = await _ensure_certificate_record_shape(cert)
        return {"certificate": _normalized_certificate_payload(shaped), "already_revoked": True}

    reason = str(payload.reason or "Revoked by administrator").strip()[:240] or "Revoked by administrator"
    now_iso = _utcnow_iso()
    updates = {
        "revoked_at": now_iso,
        "revoked_by": admin.user_id,
        "revocation_reason": reason,
        "updated_at": now_iso,
    }
    await db.learn_hub_certificates.update_one({"certificate_id": cert.get("certificate_id")}, {"$set": updates})
    cert = {**cert, **updates}
    cert = await _ensure_certificate_record_shape(cert)
    assets = await _sync_certificate_storage_assets(cert, force=True)
    if assets:
        cert = {**cert, "storage_assets": assets}
    try:
        await _append_certificate_audit_log(cert, "revoked", admin.user_id, {"reason": reason})
    except Exception:
        pass
    try:
        await emit_notification(
            user_id=cert.get("user_id"),
            notif_type="learning_hub_certificate_revoked",
            title="Certificate status updated",
            body=f"Your certificate for {cert.get('course_title', 'this course')} has been revoked.",
            action_url=f"/certificate-verify/{verification_id}",
            metadata={"verification_id": verification_id, "reason": reason},
        )
    except Exception:
        pass
    return {"certificate": _normalized_certificate_payload(cert), "already_revoked": False}


@router.get("/admin/certificate-anchoring/status")
async def certificate_anchoring_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)

    pending_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "pending"})
    anchored_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "anchored"})
    failed_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "failed"})
    total_certificates = await db.learn_hub_certificates.count_documents({})
    anchored_certificates = await db.learn_hub_certificates.count_documents({"anchoring.status": "anchored"})

    runtime = await db.learn_hub_anchor_runtime.find_one({"key": "certificate_anchor_runtime"}, {"_id": 0}) or {}
    last_batch = await db.learn_hub_certificate_anchor_batches.find_one({}, {"_id": 0}, sort=[("anchored_at", -1)]) or {}
    cfg = _polygon_anchor_config()
    mode = _configured_anchor_mode(cfg)

    return {
        "generated_at": _utcnow_iso(),
        "mode": mode,
        "chain_target": ANCHOR_CHAIN_TARGET,
        "live_config": {
            "enable_live": bool(cfg.get("enable_live")),
            "configured": bool(cfg.get("configured")),
            "rpc_url_set": False,
            "private_key_set": False,
            "fallback_mode": cfg.get("fallback_mode"),
        },
        "ots_config": {
            "enabled": bool(cfg.get("enable_live")),
            "cli_path": cfg.get("ots_cli_path"),
            "cli_available": bool(cfg.get("ots_cli_available")),
            "calendar_url_set": bool(cfg.get("ots_calendar_url")),
        },
        "queue": {
            "pending": pending_count,
            "anchored": anchored_count,
            "failed": failed_count,
        },
        "coverage": {
            "total_certificates": total_certificates,
            "anchored_certificates": anchored_certificates,
            "anchored_ratio_pct": round((anchored_certificates / max(total_certificates, 1)) * 100, 2),
        },
        "runtime": runtime,
        "last_batch": last_batch,
    }


@router.post("/admin/certificate-anchoring/run-now")
async def trigger_certificate_anchoring_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await process_certificate_anchor_batch(limit=300, triggered_by=f"admin:{admin.user_id}")
    return {
        "success": True,
        "result": result,
    }


@router.get("/admin/integrity/status")
async def learning_hub_integrity_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)

    runtime = await db.learn_hub_integrity_runtime.find_one({"key": "learning_hub_integrity_runtime"}, {"_id": 0}) or {}
    history = await db.learn_hub_integrity_history.find({}, {"_id": 0}).sort("run_at", -1).limit(10).to_list(10)
    return {
        "generated_at": _utcnow_iso(),
        "runtime": runtime,
        "recent_runs": history,
    }


@router.post("/admin/integrity/run-now")
async def learning_hub_integrity_run_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await run_learning_hub_integrity_cycle(triggered_by=f"admin:{admin.user_id}")
    return {
        "success": True,
        "result": result,
    }


@router.get("/admin/weekly-course-publish/status")
async def weekly_course_publish_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    runtime = await db.learn_hub_automation_runtime.find_one(
        {"key": "learning_hub_weekly_course_runtime"},
        {"_id": 0},
    ) or {}
    current_week = _current_week_key()
    week_courses = await db.learn_hub_courses.find(
        {"auto_publish_week": current_week, "publish_source": "weekly_automation"},
        {"_id": 0, "course_id": 1, "title": 1, "video_lessons": 1},
    ).to_list(20)
    return {
        "generated_at": _utcnow_iso(),
        "current_week": current_week,
        "runtime": runtime,
        "week_courses": [
            {
                "course_id": c.get("course_id"),
                "title": c.get("title"),
                "video_count": len(c.get("video_lessons") or []),
            }
            for c in week_courses
        ],
    }


@router.get("/admin/content-relevance/status")
async def learning_hub_content_relevance_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    runtime = await db.learn_hub_video_validation_runtime.find_one(
        {"key": "learning_hub_video_validation_rotation"},
        {"_id": 0},
    ) or {}
    assurance_runtime = await db.learn_hub_assurance_runtime.find_one(
        {"key": "learning_hub_assurance_runtime"},
        {"_id": 0, "videos": 1, "run_at": 1, "status": 1},
    ) or {}
    return {
        "generated_at": _utcnow_iso(),
        "video_validation_runtime": runtime,
        "assurance_video_snapshot": assurance_runtime,
    }


@router.post("/admin/weekly-course-publish/run-now")
async def weekly_course_publish_run_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await ensure_weekly_course_publication(triggered_by=f"admin:{admin.user_id}")
    return {
        "success": True,
        "result": result,
    }


@router.get("/admin/assurance/status")
async def learning_hub_assurance_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    runtime = await db.learn_hub_assurance_runtime.find_one({"key": "learning_hub_assurance_runtime"}, {"_id": 0}) or {}
    history = await db.learn_hub_assurance_history.find({}, {"_id": 0}).sort("run_at", -1).limit(10).to_list(10)
    return {
        "generated_at": _utcnow_iso(),
        "runtime": runtime,
        "recent_runs": history,
    }


@router.post("/admin/assurance/run-now")
async def learning_hub_assurance_run_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await run_learning_hub_assurance_cycle(triggered_by=f"admin:{admin.user_id}")
    return {
        "success": True,
        "result": result,
    }


@router.get("/admin/synthetic-canary/status")
async def learning_hub_synthetic_canary_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    runtime = await db.learn_hub_synthetic_canary_runtime.find_one(
        {"key": "learning_hub_synthetic_canary_runtime"},
        {"_id": 0},
    ) or {}
    history = await db.learn_hub_synthetic_canary_history.find({}, {"_id": 0}).sort("run_at", -1).limit(12).to_list(12)
    return {
        "generated_at": _utcnow_iso(),
        "runtime": runtime,
        "recent_runs": history,
    }


@router.post("/admin/synthetic-canary/run-now")
async def learning_hub_synthetic_canary_run_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await run_learning_hub_synthetic_canary(triggered_by=f"admin:{admin.user_id}")
    return {
        "success": True,
        "result": result,
    }


@router.get("/admin/notifications/email-dispatch/status")
async def learning_hub_email_dispatch_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    pending = await db.learn_hub_email_queue.count_documents({"status": "pending"})
    sent = await db.learn_hub_email_queue.count_documents({"status": "sent"})
    failed = await db.learn_hub_email_queue.count_documents({"status": "failed"})
    recent = await db.learn_hub_email_queue.find({}, {"_id": 0}).sort("updated_at", -1).limit(12).to_list(12)
    return {
        "generated_at": _utcnow_iso(),
        "queue": {"pending": pending, "sent": sent, "failed": failed},
        "recent": recent,
    }


@router.post("/admin/notifications/email-dispatch/run-now")
async def learning_hub_email_dispatch_run_now(request: Request):
    from routes.db import require_admin

    admin = await require_admin(request)
    result = await process_learning_hub_email_queue(batch_size=200)
    return {
        "success": True,
        "triggered_by": admin.user_id,
        "result": result,
    }


@router.get("/admin/engagement-kpis")
async def learning_hub_engagement_kpis(request: Request):
    from routes.db import require_admin

    await require_admin(request)

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    yesterday = now.date().fromordinal(now.date().toordinal() - 1).isoformat()
    week_start = now.date().fromordinal(now.date().toordinal() - 6).isoformat()

    mission_total = await db.learn_hub_daily_missions.count_documents({"day": {"$gte": week_start}})
    mission_completed = await db.learn_hub_daily_missions.count_documents({"day": {"$gte": week_start}, "completed": True})

    checkin_users = await db.learn_hub_habit_checkins.distinct("user_id", {"day": {"$gte": week_start}})
    sprint_users = await db.learn_hub_career_sprints.distinct("user_id", {"created_day": {"$gte": week_start}})
    activity_users = await db.learn_hub_daily_activity.distinct("user_id", {"day": {"$gte": week_start}})

    today_users = set(await db.learn_hub_daily_activity.distinct("user_id", {"day": today}))
    yesterday_users = set(await db.learn_hub_daily_activity.distinct("user_id", {"day": yesterday}))
    retained = len(today_users.intersection(yesterday_users))

    growth_events_7d = await db.learn_hub_growth_events.find(
        {"day": {"$gte": week_start}},
        {"_id": 0, "event_type": 1},
    ).to_list(5000)
    event_counts: Dict[str, int] = {}
    for row in growth_events_7d:
        event_type = str(row.get("event_type") or "unknown")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    mission_completion_rate = round((mission_completed / max(mission_total, 1)) * 100, 2)
    checkin_adoption_rate = round((len(checkin_users) / max(len(activity_users), 1)) * 100, 2)
    sprint_conversion_rate = round((len(sprint_users) / max(len(checkin_users), 1)) * 100, 2)
    day_retention_rate = round((retained / max(len(yesterday_users), 1)) * 100, 2)

    return {
        "generated_at": _utcnow_iso(),
        "window": {"days": 7, "start": week_start, "end": today},
        "funnel": {
            "mission_completion_rate_pct": mission_completion_rate,
            "checkin_adoption_rate_pct": checkin_adoption_rate,
            "sprint_conversion_rate_pct": sprint_conversion_rate,
            "day1_return_rate_pct": day_retention_rate,
        },
        "volume": {
            "active_users_7d": len(activity_users),
            "checkin_users_7d": len(checkin_users),
            "sprint_users_7d": len(sprint_users),
            "missions_total_7d": mission_total,
            "missions_completed_7d": mission_completed,
        },
        "events_7d": event_counts,
    }


def _certificate_analytics_range_start(range_key: str) -> Optional[datetime]:
    normalized = str(range_key or "all").strip().lower()
    now = datetime.now(timezone.utc)
    if normalized == "7d":
        return now - timedelta(days=7)
    if normalized == "30d":
        return now - timedelta(days=30)
    if normalized == "90d":
        return now - timedelta(days=90)
    return None


def _certificate_analytics_bucket_label(dt: datetime, range_key: str) -> str:
    normalized = str(range_key or "all").strip().lower()
    if normalized == "all":
        return dt.strftime("%Y-%m")
    if normalized == "90d":
        week_start = dt.date().fromordinal(dt.date().toordinal() - dt.weekday())
        return week_start.isoformat()
    return dt.date().isoformat()


def _build_certificate_analytics_recommendations(summary: Dict[str, Any], top_courses: List[Dict[str, Any]]) -> List[str]:
    recommendations: List[str] = []
    if float(summary.get("issue_to_share_pct", 0) or 0) < 35:
        recommendations.append("Promote stronger post-completion share prompts inside Learning Hub and the certificate gallery.")
    if float(summary.get("issue_to_view_pct", 0) or 0) < 55:
        recommendations.append("Increase verifier-open conversion by surfacing certificate CTA earlier in the completion journey.")
    if any(float(row.get("completion_to_share_pct", 0) or 0) < 20 for row in top_courses[:3]):
        recommendations.append("Top certificate tracks are under-sharing; prioritize featured proof cards and portfolio prompts for those courses.")
    if not recommendations:
        recommendations.append("Certificate completion-to-share conversion is healthy; continue monitoring channel mix and status drift.")
    return recommendations


def _retention_window_bounds(now_date: date, days: int) -> Dict[str, date]:
    current_end = now_date
    current_start = now_date - timedelta(days=max(0, days - 1))
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=max(0, days - 1))
    return {
        "current_start": current_start,
        "current_end": current_end,
        "previous_start": previous_start,
        "previous_end": previous_end,
    }


async def _build_retention_cohort_snapshot(days: int, now_date: date) -> Dict[str, Any]:
    bounds = _retention_window_bounds(now_date, days)
    query_start = bounds["previous_start"].isoformat()
    query_end = bounds["current_end"].isoformat()
    rows = await db.learn_hub_daily_activity.find(
        {"day": {"$gte": query_start, "$lte": query_end}},
        {"_id": 0, "day": 1, "user_id": 1},
    ).to_list(30000)

    current_users = {
        row.get("user_id")
        for row in rows
        if row.get("user_id")
        and bounds["current_start"].isoformat() <= str(row.get("day") or "") <= bounds["current_end"].isoformat()
    }
    previous_users = {
        row.get("user_id")
        for row in rows
        if row.get("user_id")
        and bounds["previous_start"].isoformat() <= str(row.get("day") or "") <= bounds["previous_end"].isoformat()
    }

    returning_users = current_users.intersection(previous_users)
    retention_rate = round((len(returning_users) / max(len(previous_users), 1)) * 100, 2)
    current_growth_pct = round(((len(current_users) - len(previous_users)) / max(len(previous_users), 1)) * 100, 2)

    return {
        "window": f"{days}d",
        "window_days": days,
        "current_active_users": len(current_users),
        "previous_active_users": len(previous_users),
        "returning_users": len(returning_users),
        "retention_rate_pct": retention_rate,
        "growth_vs_previous_pct": current_growth_pct,
        "at_risk_users": max(len(previous_users) - len(returning_users), 0),
        "window_bounds": {
            "current_start": bounds["current_start"].isoformat(),
            "current_end": bounds["current_end"].isoformat(),
            "previous_start": bounds["previous_start"].isoformat(),
            "previous_end": bounds["previous_end"].isoformat(),
        },
    }


@router.get("/admin/certificate-analytics")
async def certificate_analytics_dashboard(request: Request, range: str = "all"):
    from routes.db import require_admin

    await require_admin(request)
    range_key = str(range or "all").lower()
    now = datetime.now(timezone.utc)

    cached_entry = _CERTIFICATE_ANALYTICS_CACHE.get(range_key)
    if cached_entry and isinstance(cached_entry.get("payload"), dict):
        cached_at = cached_entry.get("cached_at")
        if isinstance(cached_at, datetime) and (now - cached_at).total_seconds() <= CERTIFICATE_ANALYTICS_CACHE_TTL_SECONDS:
            payload = dict(cached_entry.get("payload") or {})
            payload["cache"] = {
                "hit": True,
                "ttl_seconds": CERTIFICATE_ANALYTICS_CACHE_TTL_SECONDS,
                "cached_at": cached_at.isoformat(),
            }
            return payload

    range_start = _certificate_analytics_range_start(range_key)
    enrollment_query: Dict[str, Any] = {"completed": True}
    certificate_query: Dict[str, Any] = {}
    event_query: Dict[str, Any] = {}
    if range_start:
        since_iso = range_start.isoformat()
        enrollment_query["updated_at"] = {"$gte": since_iso}
        certificate_query["issued_at"] = {"$gte": since_iso}
        event_query["created_at"] = {"$gte": since_iso}

    completed_enrollments = await db.learn_hub_enrollments.find(enrollment_query, {"_id": 0, "course_id": 1, "course_title": 1, "updated_at": 1}).to_list(5000)
    certificates = await db.learn_hub_certificates.find(certificate_query, {"_id": 0}).to_list(5000)
    engagement_events = await db.learn_hub_certificate_engagement_events.find(event_query, {"_id": 0}).to_list(12000)

    status_mix = {
        CERTIFICATE_STATUS_VALID: 0,
        CERTIFICATE_STATUS_EXPIRED: 0,
        CERTIFICATE_STATUS_REVOKED: 0,
        CERTIFICATE_STATUS_INVALID: 0,
    }
    cert_by_verification: Dict[str, Dict[str, Any]] = {}
    course_rollups: Dict[str, Dict[str, Any]] = {}
    timeseries: Dict[str, Dict[str, Any]] = {}

    for enrollment in completed_enrollments:
        bucket_dt = _parse_iso_datetime(enrollment.get("updated_at")) or datetime.now(timezone.utc)
        bucket = _certificate_analytics_bucket_label(bucket_dt, range_key)
        timeseries.setdefault(bucket, {"bucket": bucket, "completions": 0, "issued": 0, "verifier_views": 0, "share_actions": 0})
        timeseries[bucket]["completions"] += 1

        course_id = str(enrollment.get("course_id") or "unknown")
        row = course_rollups.setdefault(course_id, {
            "course_id": course_id,
            "course_title": enrollment.get("course_title") or "Course",
            "completions": 0,
            "issued": 0,
            "certificates_viewed": set(),
            "certificates_shared": set(),
            "share_actions": 0,
        })
        row["completions"] += 1

    for cert in certificates:
        shaped = await _ensure_certificate_record_shape(cert)
        payload = _normalized_certificate_payload(shaped)
        cert_by_verification[str(payload.get("verification_id") or "")] = payload
        status_mix[str(payload.get("status") or CERTIFICATE_STATUS_VALID)] += 1

        bucket_dt = _parse_iso_datetime(payload.get("issued_at")) or datetime.now(timezone.utc)
        bucket = _certificate_analytics_bucket_label(bucket_dt, range_key)
        timeseries.setdefault(bucket, {"bucket": bucket, "completions": 0, "issued": 0, "verifier_views": 0, "share_actions": 0})
        timeseries[bucket]["issued"] += 1

        course_id = str(payload.get("course_id") or "unknown")
        row = course_rollups.setdefault(course_id, {
            "course_id": course_id,
            "course_title": payload.get("course_title") or "Course",
            "completions": 0,
            "issued": 0,
            "certificates_viewed": set(),
            "certificates_shared": set(),
            "share_actions": 0,
        })
        row["issued"] += 1

    share_events = {"secure_link_copy", "linkedin_share_click"}
    view_sessions = set()
    share_sessions = set()
    certificates_viewed = set()
    certificates_shared = set()
    share_breakdown = {"secure_link_copy": 0, "linkedin_share_click": 0}

    for event in engagement_events:
        event_type = str(event.get("event_type") or "")
        verification_id = str(event.get("verification_id") or "")
        viewer_session_id = str(event.get("viewer_session_id") or "")
        bucket_dt = _parse_iso_datetime(event.get("created_at")) or datetime.now(timezone.utc)
        bucket = _certificate_analytics_bucket_label(bucket_dt, range_key)
        timeseries.setdefault(bucket, {"bucket": bucket, "completions": 0, "issued": 0, "verifier_views": 0, "share_actions": 0})

        cert_payload = cert_by_verification.get(verification_id) or {}
        course_row = course_rollups.get(str(cert_payload.get("course_id") or ""))

        if event_type == "verifier_view":
            certificates_viewed.add(verification_id)
            if viewer_session_id:
                view_sessions.add(viewer_session_id)
            timeseries[bucket]["verifier_views"] += 1
            if course_row is not None:
                course_row["certificates_viewed"].add(verification_id)

        if event_type in share_events:
            certificates_shared.add(verification_id)
            share_breakdown[event_type] = int(share_breakdown.get(event_type, 0) or 0) + 1
            if viewer_session_id:
                share_sessions.add(viewer_session_id)
            timeseries[bucket]["share_actions"] += 1
            if course_row is not None:
                course_row["certificates_shared"].add(verification_id)
                course_row["share_actions"] += 1

    completions_total = len(completed_enrollments)
    issued_total = len(certificates)
    viewed_total = len(certificates_viewed)
    shared_total = len(certificates_shared)
    share_actions_total = sum(share_breakdown.values())
    summary = {
        "completed_enrollments": completions_total,
        "certificates_issued": issued_total,
        "certificates_viewed": viewed_total,
        "certificates_shared": shared_total,
        "verifier_views_total": sum(1 for event in engagement_events if str(event.get("event_type") or "") == "verifier_view"),
        "share_actions_total": share_actions_total,
        "unique_view_sessions": len(view_sessions),
        "unique_share_sessions": len(share_sessions),
        "completion_to_issue_pct": round((issued_total / max(completions_total, 1)) * 100, 2),
        "issue_to_view_pct": round((viewed_total / max(issued_total, 1)) * 100, 2),
        "issue_to_share_pct": round((shared_total / max(issued_total, 1)) * 100, 2),
        "completion_to_share_pct": round((shared_total / max(completions_total, 1)) * 100, 2),
        "view_to_share_pct": round((shared_total / max(viewed_total, 1)) * 100, 2),
    }

    top_courses = []
    for row in course_rollups.values():
        viewed_count = len(row["certificates_viewed"])
        shared_count = len(row["certificates_shared"])
        top_courses.append({
            "course_id": row["course_id"],
            "course_title": row["course_title"],
            "completions": row["completions"],
            "certificates_issued": row["issued"],
            "certificates_viewed": viewed_count,
            "certificates_shared": shared_count,
            "share_actions": row["share_actions"],
            "completion_to_share_pct": round((shared_count / max(row["completions"], 1)) * 100, 2),
            "issue_to_share_pct": round((shared_count / max(row["issued"], 1)) * 100, 2),
        })
    top_courses.sort(key=lambda item: (item["certificates_shared"], item["share_actions"], item["certificates_issued"]), reverse=True)

    recommendations = _build_certificate_analytics_recommendations(summary, top_courses)
    payload = {
        "generated_at": _utcnow_iso(),
        "range": range_key,
        "summary": summary,
        "funnel": [
            {"id": "completed", "label": "Course Completions", "value": completions_total},
            {"id": "issued", "label": "Certificates Issued", "value": issued_total},
            {"id": "viewed", "label": "Verifier Opens", "value": viewed_total},
            {"id": "shared", "label": "Share Actions", "value": shared_total},
        ],
        "share_breakdown": [
            {"event_type": key, "count": int(value or 0)}
            for key, value in share_breakdown.items()
        ],
        "status_mix": [
            {"status": key, "count": int(value or 0)}
            for key, value in status_mix.items()
        ],
        "timeseries": [timeseries[key] for key in sorted(timeseries.keys())],
        "top_courses": top_courses[:8],
        "executive_report": {
            "headline": f"{summary['completion_to_share_pct']}% completion-to-share conversion with {summary['issue_to_share_pct']}% of issued certificates reaching a share action.",
            "recommended_actions": recommendations,
            "default_range": "all",
        },
    }

    _CERTIFICATE_ANALYTICS_CACHE[range_key] = {
        "cached_at": now,
        "payload": payload,
    }

    payload["cache"] = {
        "hit": False,
        "ttl_seconds": CERTIFICATE_ANALYTICS_CACHE_TTL_SECONDS,
        "cached_at": now.isoformat(),
    }
    return payload


@router.get("/admin/executive-insights")
async def learning_hub_executive_insights(request: Request):
    from routes.db import require_admin

    await require_admin(request)

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week_start = now.date().fromordinal(now.date().toordinal() - 6).isoformat()

    total_courses = await db.learn_hub_courses.count_documents({})
    total_enrollments = await db.learn_hub_enrollments.count_documents({})
    completed_enrollments = await db.learn_hub_enrollments.count_documents({"completed": True})
    total_certificates = await db.learn_hub_certificates.count_documents({})
    anchored_certificates = await db.learn_hub_certificates.count_documents({"anchoring.status": "anchored"})
    pending_anchor_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "pending"})
    failed_anchor_count = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "failed"})
    video_runtime = await db.learn_hub_video_validation_runtime.find_one({"key": "learning_hub_video_validation_rotation"}, {"_id": 0}) or {}
    assurance_runtime = await db.learn_hub_assurance_runtime.find_one({"key": "learning_hub_assurance_runtime"}, {"_id": 0, "status": 1, "run_at": 1}) or {}
    synthetic_runtime = await db.learn_hub_synthetic_canary_runtime.find_one({"key": "learning_hub_synthetic_canary_runtime"}, {"_id": 0, "status": 1, "run_at": 1}) or {}

    engagement_rows = await db.learn_hub_daily_activity.find({"day": {"$gte": week_start}}, {"_id": 0}).to_list(800)
    weekly_learning_minutes = sum(int(row.get("minutes", 0) or 0) for row in engagement_rows)
    daily_active_learners = len({row.get("user_id") for row in engagement_rows if row.get("day") == today and row.get("user_id")})
    weekly_active_learners = len({row.get("user_id") for row in engagement_rows if row.get("user_id")})
    retention_7d, retention_30d = await asyncio.gather(
        _build_retention_cohort_snapshot(7, now.date()),
        _build_retention_cohort_snapshot(30, now.date()),
    )

    completion_rate = round((completed_enrollments / max(total_enrollments, 1)) * 100, 2)

    category_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    category_trends = []
    async for row in db.learn_hub_enrollments.aggregate(category_pipeline):
        category_trends.append({"category": row.get("_id") or "Unspecified", "enrollments": int(row.get("count", 0) or 0)})

    plan_pipeline = [
        {"$group": {"_id": "$subscription_plan", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    plan_mix = []
    async for row in db.users.aggregate(plan_pipeline):
        plan_mix.append({"plan": row.get("_id") or "free", "count": int(row.get("count", 0) or 0)})

    optimization_report = {
        "status": "self-operating",
        "focus": [
            "Boost completion in high-volume tracks",
            "Increase roadmap adoption for free users",
            "Promote mentor matching after module milestones",
        ],
        "suggested_actions": [
            "Push personalized reminders at streak drop-off",
            "Recommend micro-courses by progress gaps",
            "Surface certificate CTA at 85% completion",
        ],
    }

    return {
        "generated_at": _utcnow_iso(),
        "overview": {
            "total_courses": total_courses,
            "total_enrollments": total_enrollments,
            "completion_rate_pct": completion_rate,
            "total_certificates": total_certificates,
            "anchored_certificates": anchored_certificates,
            "anchored_certificate_ratio_pct": round((anchored_certificates / max(total_certificates, 1)) * 100, 2),
            "pending_anchor_count": pending_anchor_count,
            "failed_anchor_count": failed_anchor_count,
            "daily_active_learners": daily_active_learners,
            "weekly_active_learners": weekly_active_learners,
            "weekly_learning_minutes": weekly_learning_minutes,
            "retention_7d_rate_pct": float(retention_7d.get("retention_rate_pct", 0) or 0),
            "retention_30d_rate_pct": float(retention_30d.get("retention_rate_pct", 0) or 0),
            "video_topic_alignment_pct": float(video_runtime.get("topic_alignment_pct", 100) or 100),
            "video_topic_mismatches": int(video_runtime.get("topic_mismatch_lessons", 0) or 0),
            "video_broken_links": int(video_runtime.get("broken_links", 0) or 0),
        },
        "category_trends": category_trends,
        "plan_mix": plan_mix,
        "retention_cohorts": [retention_7d, retention_30d],
        "automation_runtime": {
            "assurance_status": assurance_runtime.get("status", "unknown"),
            "assurance_run_at": assurance_runtime.get("run_at"),
            "synthetic_canary_status": synthetic_runtime.get("status", "unknown"),
            "synthetic_canary_run_at": synthetic_runtime.get("run_at"),
            "video_validation_run_at": video_runtime.get("updated_at"),
        },

        "optimization_report": optimization_report,
        "controls": {"mode": "view_only", "manual_actions": False},
    }

# ── Cinematic Course Covers (unique image per course) ─────────────

_COVER_ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "learning_hub_covers")
_COVER_CACHE_DIR = "/app/backend/.cache/lh_covers"
_COVER_VERSION = "v1"
_COVER_FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_COVER_FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_COVER_BACKDROPS = {
    "ai": ["ai_1.jpg", "ai_2.jpg", "ai_3.jpg"],
    "business": ["business_1.jpg", "business_2.jpg", "business_3.jpg"],
    "cybersecurity": ["cyber_1.jpg", "cyber_2.jpg", "cyber_3.jpg"],
    "it": ["it_1.jpg"],
    "software": ["software_1.jpg"],
    "data science": ["datascience_1.jpg"],
    "cloud computing": ["cloud_1.jpg"],
    "devops": ["devops_1.jpg"],
    "marketing": ["marketing_1.jpg"],
    "entrepreneurship": ["entrepreneurship_1.jpg"],
    "project management": ["projectmgmt_1.jpg"],
    "product management": ["productmgmt_1.jpg"],
    "finance": ["finance_1.jpg"],
    "sales": ["sales_1.jpg"],
    "leadership": ["leadership_1.jpg"],
    "hr & talent": ["hr_1.jpg"],
    "design": ["design_1.jpg"],
    "creative arts": ["creativearts_1.jpg"],
    "photography": ["photography_1.jpg"],
    "music": ["music_1.jpg"],
    "writing & content": ["writing_1.jpg"],
    "lifestyle": ["lifestyle_1.jpg"],
    "health & wellness": ["health_1.jpg"],
    "communication": ["communication_1.jpg"],
    "personal development": ["personaldev_1.jpg"],
}
_COVER_ACCENTS = {
    "ai": (56, 224, 255),
    "business": (250, 190, 88),
    "cybersecurity": (255, 122, 89),
    "it": (94, 200, 255),
    "software": (110, 231, 183),
    "data science": (139, 180, 255),
    "cloud computing": (147, 197, 253),
    "devops": (255, 168, 94),
    "marketing": (244, 114, 182),
    "entrepreneurship": (252, 211, 77),
    "project management": (129, 212, 250),
    "product management": (196, 160, 255),
    "finance": (134, 239, 172),
    "sales": (253, 186, 116),
    "leadership": (250, 204, 21),
    "hr & talent": (255, 150, 130),
    "design": (232, 121, 249),
    "creative arts": (251, 146, 190),
    "photography": (186, 230, 253),
    "music": (192, 132, 252),
    "writing & content": (253, 224, 138),
    "lifestyle": (253, 186, 140),
    "health & wellness": (110, 231, 183),
    "communication": (94, 234, 212),
    "personal development": (216, 180, 254),
}
_COVER_GENERAL = "general_1.jpg"


def _cover_wrap_title(draw, title: str, font, max_width: int) -> list:
    words = title.split()
    lines, current = [], ""
    for word in words:
        probe = f"{current} {word}".strip()
        if draw.textlength(probe, font=font) <= max_width:
            current = probe
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) >= 3:
            break
    if current and len(lines) < 3:
        lines.append(current)
    return lines[:3]


def _render_course_cover(course: dict, variant: str = "full") -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    course_id = str(course.get("course_id") or "course")
    title = str(course.get("title") or "RealAICoach Course")
    category = str(course.get("category") or "General")
    difficulty = str(course.get("difficulty") or "intermediate").capitalize()
    modules = course.get("modules") or []
    hours = course.get("duration_hours")
    seed = hashlib.md5(course_id.encode()).digest()

    cat_key = category.strip().lower()
    pool = _COVER_BACKDROPS.get(cat_key)
    accent = _COVER_ACCENTS.get(cat_key, (255, 170, 110))
    fname = pool[seed[0] % len(pool)] if pool else _COVER_GENERAL
    path = os.path.join(_COVER_ASSET_DIR, fname)
    if not os.path.exists(path):
        path = os.path.join(_COVER_ASSET_DIR, _COVER_GENERAL)

    W, H = 1280, 720
    img = Image.open(path).convert("RGB").resize((W, H))

    # deterministic per-course accent geometry — makes every cover unique
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for i in range(4):
        cx = int((seed[1 + i] / 255) * W)
        cy = int((seed[5 + i] / 255) * H * 0.7)
        r = 50 + int((seed[9 + i] / 255) * 200)
        alpha = 10 + (seed[13 - i] % 18)
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent, alpha + 46), width=2)
        odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*accent, max(4, alpha // 2)))
    for i in range(3):
        x0 = int((seed[4 + i] / 255) * W)
        odraw.line([(x0, 0), (x0 + 140 + (seed[2] % 3) * 90, H)], fill=(*accent, 24), width=2 + (seed[7 + i] % 3))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    # bottom readability gradient
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(28 + ((y / H) ** 1.7) * 200))
    gradient = Image.new("RGBA", (W, H), (5, 9, 17, 0))
    gradient.putalpha(grad.resize((W, H)))
    img = Image.alpha_composite(img, gradient).convert("RGB")

    if variant == "plain":
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=84)
        return buf.getvalue()

    draw = ImageDraw.Draw(img)
    try:
        f_kick = ImageFont.truetype(_COVER_FONT_BOLD, 24)
        f_title = ImageFont.truetype(_COVER_FONT_BOLD, 58)
        f_meta = ImageFont.truetype(_COVER_FONT_REGULAR, 26)
        f_chip = ImageFont.truetype(_COVER_FONT_BOLD, 24)
    except Exception:
        f_kick = f_title = f_meta = f_chip = ImageFont.load_default()

    chip_text = category.upper()
    chip_w = draw.textlength(chip_text, font=f_chip)
    draw.rounded_rectangle([48, 44, 48 + chip_w + 40, 96], radius=26, fill=(9, 13, 22, 235), outline=accent, width=2)
    draw.text((68, 56), chip_text, font=f_chip, fill=accent)

    title_lines = _cover_wrap_title(draw, title, f_title, W - 120)
    meta_bits = [difficulty]
    if modules:
        meta_bits.append(f"{len(modules)} MODULES")
    if hours:
        meta_bits.append(f"{hours}H")
    meta_text = "  •  ".join(meta_bits)

    meta_y = H - 78
    title_y = meta_y - 18 - len(title_lines) * 68
    kick_y = title_y - 40
    draw.text((50, kick_y), "REALAICOACH  ·  LEARNING HUB", font=f_kick, fill=(*accent, 255))
    for i, line in enumerate(title_lines):
        draw.text((48, title_y + i * 68), line, font=f_title, fill=(248, 250, 252))
    draw.text((50, meta_y), meta_text, font=f_meta, fill=(203, 213, 225))

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=84)
    return buf.getvalue()


@router.get("/course-cover/{course_id}.jpg")
async def course_cover_image(course_id: str, variant: str = "full"):
    """Public, cache-friendly unique cover image for a Learning Hub course."""
    cid = str(course_id)[:64]
    variant = "plain" if variant == "plain" else "full"
    course = await db.learn_hub_courses.find_one(
        {"course_id": cid},
        {"_id": 0, "course_id": 1, "title": 1, "category": 1, "difficulty": 1, "duration_hours": 1, "modules": 1},
    )
    os.makedirs(_COVER_CACHE_DIR, exist_ok=True)
    stamp = hashlib.md5(
        f"{_COVER_VERSION}|{variant}|{(course or {}).get('title', '')}|{(course or {}).get('category', '')}".encode()
    ).hexdigest()[:10]
    cache_path = os.path.join(_COVER_CACHE_DIR, f"{cid}_{stamp}.jpg")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as fh:
            data = fh.read()
    else:
        data = _render_course_cover(course or {"course_id": cid, "title": "RealAICoach Course", "category": "General"}, variant=variant)
        with open(cache_path, "wb") as fh:
            fh.write(data)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


async def _send_enrollment_kickoff_email(user, course: dict) -> bool:
    """Non-blocking v7 enrollment kickoff email with course cover art."""
    try:
        from utils.email_service import is_email_configured, send_catalog_template
        if not is_email_configured():
            return False
        email = str(getattr(user, "email", "") or "").strip()
        if not email:
            return False
        from utils.email_templates import DASH_URL
        lessons = course.get("video_lessons") or []
        first_lesson = str((lessons[0] or {}).get("title") or "Lesson 1") if lessons else "Lesson 1"
        result = await send_catalog_template(
            recipient_email=email,
            template_key="learning_hub_enrollment_kickoff",
            recipient_name=str(getattr(user, "name", "") or "Learner"),
            learner_name=str(getattr(user, "name", "") or "Learner"),
            course_title=str(course.get("title") or "Course"),
            category=str(course.get("category") or "AI"),
            difficulty=str(course.get("difficulty") or "intermediate"),
            module_count=len(course.get("modules") or []),
            first_lesson_title=first_lesson,
            cover_url=f"{DASH_URL}/api/ai-learn/course-cover/{course.get('course_id')}.jpg",
        )
        return bool(result.get("success"))
    except Exception:
        return False

