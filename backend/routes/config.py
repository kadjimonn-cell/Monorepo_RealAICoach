from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import hashlib
import json
import copy
import time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateNotification(BaseModel):
    id: str
    title: str
    message: str
    type: str = "info"
    action_link: Optional[str] = None


class AppConfig(BaseModel):
    version: str
    min_supported_version: str
    maintenance_mode: bool
    features: Dict[str, bool]
    limits: Dict[str, Any]
    ui_overrides: Dict[str, Any]
    ai_settings: Dict[str, Any]
    integrations: Dict[str, Any] = Field(default_factory=dict)
    updates: List[UpdateNotification]
    active_integrations: int = 0
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class PlatformSettingsUpdateRequest(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)


DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    "tv_reality_enabled": True,
    "ai_phone_call_enabled": True,
    "content_studio_enabled": True,
    "developer_workplace_enabled": True,
    "advanced_analytics": True,
    "crypto_live_data": True,
    "google_calendar_export": True,
    "ai_dating": True,
    "smart_cars": True,
    "real_estate": True,
    "school_tutor": True,
    "ai_image_generation": True,
    "voice_ai": True,
    "daily_content_drops": True,
    "accessibility_mode": True,
}

DEFAULT_INTEGRATIONS: Dict[str, Dict[str, Any]] = {
    "google_calendar": {"enabled": True, "label": "Google Calendar", "category": "Productivity"},
    "google_drive": {"enabled": True, "label": "Google Drive", "category": "Storage"},
    "slack": {"enabled": True, "label": "Slack", "category": "Communication"},
    "zoom": {"enabled": True, "label": "Zoom", "category": "Communication"},
    "stripe": {"enabled": True, "label": "Stripe", "category": "Payments"},
    "paypal": {"enabled": True, "label": "PayPal", "category": "Payments"},
    "fedapay": {"enabled": True, "label": "FedaPay", "category": "Payments"},
    "sendgrid": {"enabled": True, "label": "SendGrid", "category": "Email"},
    "resend": {"enabled": True, "label": "Resend", "category": "Email"},
    "twilio": {"enabled": True, "label": "Twilio", "category": "SMS"},
    "openai": {"enabled": True, "label": "OpenAI", "category": "AI"},
    "webhook": {"enabled": True, "label": "Webhooks", "category": "Developer"},
}

DEFAULT_GLOBAL_CONFIG: Dict[str, Any] = {
    "version": "2026.02.19",
    "min_supported_version": "1.0.0",
    "maintenance_mode": False,
    "features": copy.deepcopy(DEFAULT_FEATURE_FLAGS),
    "limits": {
        "free_conversations_per_day": 3,
        "max_downloads_daily": 2,
    },
    "ui_overrides": {
        "home_banner_text": "RealAICoach Enterprise Platform",
        "primary_color_override": "#0F766E",
    },
    "ai_settings": {
        "default_model": "gpt-4o",
        "vision_model": "gpt-4o",
        "coach_persona": "friendly_expert",
    },
    "integrations": copy.deepcopy(DEFAULT_INTEGRATIONS),
    "updates": [
        {
            "id": "upd_001",
            "title": "Instant Update Applied",
            "message": "We've just upgraded the AI engine to be 2x faster. No app update needed!",
            "type": "success",
        }
    ],
    "boot_policy": {
        "policy_epoch": "2026-05-02-shell-origin-hotfix-r1",
        "required_cache_schema": "enterprise_perf_v13_2026_04_19_realaicoach_v2_global_theme_lock",
        "force_reload_on_mismatch": True,
        "max_reload_attempts": 2,
    },
}

_CONFIG_CACHE = {"ts": 0.0, "version": "", "data": None}
_CONFIG_TTL_SECONDS = 60
_CONFIG_DOC_KEY = "global"

BOOT_POLICY_TELEMETRY_COLLECTION = "boot_policy_reload_telemetry"
BOOT_POLICY_MONITOR_STATE_COLLECTION = "boot_policy_reload_monitor_state"
BOOT_POLICY_MONITOR_EVENTS_COLLECTION = "boot_policy_reload_monitor_events"
BOOT_POLICY_MONITOR_STATE_KEY = "boot_policy_should_reload_spike_monitor"
BOOT_POLICY_SPIKE_THRESHOLD = 20
BOOT_POLICY_SPIKE_WINDOW_MINUTES = 5
BOOT_POLICY_SPIKE_ALERT_COOLDOWN_MINUTES = 10


class BootPolicyReloadTelemetryIn(BaseModel):
    event_type: str = Field(default="should_reload_true", max_length=64)
    policy_id: Optional[str] = Field(default=None, max_length=120)
    client_policy_id: Optional[str] = Field(default=None, max_length=120)
    client_cache_schema: Optional[str] = Field(default=None, max_length=220)
    route_path: Optional[str] = Field(default=None, max_length=260)
    route_query: Optional[str] = Field(default=None, max_length=260)
    host: Optional[str] = Field(default=None, max_length=120)
    source: str = Field(default="boot_policy_handshake", max_length=80)
    reason: Optional[str] = Field(default=None, max_length=120)
    reload_attempt: int = Field(default=0, ge=0, le=20)


def _parse_iso_datetime_safe(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge_dict(base[key], value)
        else:
            base[key] = value
    return base


def _set_by_path(target: Dict[str, Any], path: str, value: Any) -> None:
    if not path:
        return
    parts = [segment for segment in str(path).split(".") if segment]
    cursor = target
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _normalize_updates(raw_updates: Any) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_updates or []):
        if not isinstance(item, dict):
            continue
        updates.append(
            {
                "id": str(item.get("id") or f"upd_{index + 1}"),
                "title": str(item.get("title") or "System Notice"),
                "message": str(item.get("message") or ""),
                "type": str(item.get("type") or "info"),
                "action_link": item.get("action_link"),
            }
        )
    return updates[:5] or copy.deepcopy(DEFAULT_GLOBAL_CONFIG["updates"])


def _normalize_config(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_GLOBAL_CONFIG)
    if isinstance(raw, dict):
        sanitized = copy.deepcopy(raw)
        sanitized.pop("_id", None)
        sanitized.pop("key", None)
        _deep_merge_dict(config, sanitized)

    config["features"] = {
        **copy.deepcopy(DEFAULT_FEATURE_FLAGS),
        **(config.get("features") or {}),
    }
    config["integrations"] = {
        key: {
            **copy.deepcopy(DEFAULT_INTEGRATIONS.get(key) or {}),
            **(value or {}),
        }
        for key, value in {
            **copy.deepcopy(DEFAULT_INTEGRATIONS),
            **(config.get("integrations") or {}),
        }.items()
    }
    config["limits"] = {
        "free_conversations_per_day": int((config.get("limits") or {}).get("free_conversations_per_day", 3) or 3),
        "max_downloads_daily": int((config.get("limits") or {}).get("max_downloads_daily", 2) or 2),
    }
    config["ui_overrides"] = {
        "home_banner_text": str((config.get("ui_overrides") or {}).get("home_banner_text") or DEFAULT_GLOBAL_CONFIG["ui_overrides"]["home_banner_text"]),
        "primary_color_override": (config.get("ui_overrides") or {}).get("primary_color_override") or DEFAULT_GLOBAL_CONFIG["ui_overrides"]["primary_color_override"],
    }
    config["ai_settings"] = {
        "default_model": str((config.get("ai_settings") or {}).get("default_model") or DEFAULT_GLOBAL_CONFIG["ai_settings"]["default_model"]),
        "vision_model": str((config.get("ai_settings") or {}).get("vision_model") or DEFAULT_GLOBAL_CONFIG["ai_settings"]["vision_model"]),
        "coach_persona": str((config.get("ai_settings") or {}).get("coach_persona") or DEFAULT_GLOBAL_CONFIG["ai_settings"]["coach_persona"]),
    }
    config["version"] = str(config.get("version") or DEFAULT_GLOBAL_CONFIG["version"])
    config["min_supported_version"] = str(config.get("min_supported_version") or DEFAULT_GLOBAL_CONFIG["min_supported_version"])
    config["maintenance_mode"] = bool(config.get("maintenance_mode", False))
    config["updates"] = _normalize_updates(config.get("updates"))
    incoming_boot_policy = config.get("boot_policy") or {}
    config["boot_policy"] = {
        "policy_epoch": str(
            incoming_boot_policy.get("policy_epoch")
            or DEFAULT_GLOBAL_CONFIG["boot_policy"]["policy_epoch"]
        ),
        "required_cache_schema": str(
            incoming_boot_policy.get("required_cache_schema")
            or DEFAULT_GLOBAL_CONFIG["boot_policy"]["required_cache_schema"]
        ),
        "force_reload_on_mismatch": bool(
            incoming_boot_policy.get("force_reload_on_mismatch", True)
        ),
        "max_reload_attempts": int(
            incoming_boot_policy.get("max_reload_attempts")
            or DEFAULT_GLOBAL_CONFIG["boot_policy"]["max_reload_attempts"]
        ),
    }
    config["active_integrations"] = sum(
        1 for value in (config.get("integrations") or {}).values() if bool((value or {}).get("enabled", True))
    )
    return config


def _build_boot_policy_payload(config: Dict[str, Any]) -> Dict[str, Any]:
    boot_policy = config.get("boot_policy") or {}
    payload = {
        "policy_epoch": str(boot_policy.get("policy_epoch") or "default"),
        "required_cache_schema": str(boot_policy.get("required_cache_schema") or ""),
        "force_reload_on_mismatch": bool(boot_policy.get("force_reload_on_mismatch", True)),
        "max_reload_attempts": int(boot_policy.get("max_reload_attempts") or 2),
        "config_version": str(config.get("version") or ""),
        "min_supported_version": str(config.get("min_supported_version") or ""),
    }

    fingerprint_base = {
        "policy_epoch": payload["policy_epoch"],
        "required_cache_schema": payload["required_cache_schema"],
        "config_version": payload["config_version"],
        "min_supported_version": payload["min_supported_version"],
    }
    serialized = json.dumps(fingerprint_base, sort_keys=True, separators=(",", ":"))
    payload["policy_id"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]
    return payload


async def _load_persisted_config() -> Dict[str, Any]:
    from .db import db

    doc = await db.platform_runtime_config.find_one({"key": _CONFIG_DOC_KEY}, {"_id": 0})
    return _normalize_config(doc or {})


async def _save_persisted_config(config: Dict[str, Any], updated_by: Optional[str] = None) -> Dict[str, Any]:
    from .db import db

    normalized = _normalize_config(config)
    payload = {
        "key": _CONFIG_DOC_KEY,
        **normalized,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": updated_by,
    }
    await db.platform_runtime_config.update_one(
        {"key": _CONFIG_DOC_KEY},
        {"$set": payload},
        upsert=True,
    )
    payload.pop("key", None)
    _CONFIG_CACHE["ts"] = 0.0
    _CONFIG_CACHE["data"] = None
    return _normalize_config(payload)


def _build_platform_settings_summary(config: Dict[str, Any]) -> Dict[str, Any]:
    features = config.get("features") or {}
    integrations = config.get("integrations") or {}
    return {
        "version": config.get("version"),
        "maintenance_mode": bool(config.get("maintenance_mode", False)),
        "enabled_feature_count": sum(1 for value in features.values() if bool(value)),
        "total_feature_count": len(features),
        "enabled_integration_count": sum(1 for value in integrations.values() if bool((value or {}).get("enabled", True))),
        "total_integration_count": len(integrations),
        "free_conversations_per_day": int((config.get("limits") or {}).get("free_conversations_per_day", 0) or 0),
        "max_downloads_daily": int((config.get("limits") or {}).get("max_downloads_daily", 0) or 0),
        "updated_at": config.get("updated_at"),
        "updated_by": config.get("updated_by"),
    }


@router.get("/config/v2-compliance/runtime")
async def get_v2_compliance_runtime(_: Request):
    from routes.platform_perf import _get_or_build_v2_compliance_report

    report = await _get_or_build_v2_compliance_report(force_refresh=False, persist=False)
    return {
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "score": report.get("score"),
        "enforcement_mode": report.get("enforcement_mode"),
        "theme_policy": report.get("theme_policy", {}),
        "global_block": report.get("global_block"),
        "blocking_routes": report.get("blocking_routes", []),
        "global_blockers": [row.get("file") for row in report.get("global_blockers", [])[:8]],
        "scanned_at": report.get("scanned_at"),
        "summary": report.get("summary", {}),
    }


@router.get("/config/global-production-gate")
async def get_global_production_gate(request: Request):
    """Unified release gate to prevent false-green compliance reporting.

    Combines:
      - V2 runtime compliance status
      - i18n coverage health
      - i18n route adoption/hardcoded copy signals
      - runtime stability error budget (UIEM critical events)
    """

    from routes.db import require_admin, db
    from routes.platform_perf import _get_or_build_v2_compliance_report
    from routes.admin_i18n_coverage import get_i18n_coverage
    from routes.admin_i18n_adoption import _scan_adoption, _route_status_summary
    uiem_violations_collection = "uiem_violations"

    await require_admin(request)

    v2_report = await _get_or_build_v2_compliance_report(force_refresh=False, persist=False)
    i18n_coverage = await get_i18n_coverage(request)
    i18n_adoption = _scan_adoption()

    aggregate_i18n_pct = float(i18n_coverage.get("aggregate_coverage_pct") or 0.0)
    i18n_health = str(i18n_coverage.get("health") or "unknown")
    structural_i18n_pct = float(i18n_coverage.get("structural_coverage_pct") or 0.0)
    structural_i18n_health = str(i18n_coverage.get("structural_health") or "unknown")
    missing_keys_total = int(i18n_coverage.get("missing_keys_total") or 0)

    adoption_summary = i18n_adoption.get("summary") or {}
    hardcoded_copy_files = int(adoption_summary.get("files_with_hardcoded_copy_without_t") or 0)
    route_report_card = list(i18n_adoption.get("route_report_card") or [])
    status_summary = _route_status_summary(route_report_card)
    action_required_routes = int(status_summary.get("action_required") or 0)

    runtime_window_start = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    runtime_budget = {
        "window_hours": 6,
        "max_open_critical_events": 0,
    }
    open_runtime_critical_events = int(
        await db[uiem_violations_collection].count_documents(
            {
                "resolved": {"$ne": True},
                "severity": {"$in": ["critical", "fatal"]},
                "detected_at": {"$gte": runtime_window_start},
            }
        )
    )

    blockers: list[dict[str, Any]] = []

    v2_status = str(v2_report.get("status") or "").lower()
    v2_allowed = {"healthy", "critical"}
    if bool(v2_report.get("global_block")) or v2_status not in v2_allowed:
        blockers.append(
            {
                "domain": "v2_theme_runtime",
                "reason": "v2 compliance runtime not healthy or global_block active",
                "status": v2_report.get("status"),
            }
        )

    if missing_keys_total > 0 or structural_i18n_health == "red":
        blockers.append(
            {
                "domain": "i18n_coverage",
                "reason": "i18n locale structural parity below production threshold",
                "structural_coverage_pct": structural_i18n_pct,
                "structural_health": structural_i18n_health,
                "missing_keys_total": missing_keys_total,
            }
        )

    if aggregate_i18n_pct < 15.0:
        blockers.append(
            {
                "domain": "i18n_translation_depth",
                "reason": "i18n translated-depth critically low for safe release",
                "aggregate_coverage_pct": aggregate_i18n_pct,
                "health": i18n_health,
            }
        )

    if hardcoded_copy_files > 0:
        blockers.append(
            {
                "domain": "i18n_hardcoded_copy",
                "reason": "Hardcoded user-facing copy without translation hooks detected",
                "files_with_hardcoded_copy_without_t": hardcoded_copy_files,
            }
        )

    if action_required_routes > 0:
        blockers.append(
            {
                "domain": "i18n_route_report_card",
                "reason": "Routes flagged action_required in i18n report card",
                "action_required_routes": action_required_routes,
            }
        )

    if open_runtime_critical_events > runtime_budget["max_open_critical_events"]:
        blockers.append(
            {
                "domain": "runtime_error_budget",
                "reason": "Open critical runtime stability events exceed budget",
                "window_hours": runtime_budget["window_hours"],
                "max_open_critical_events": runtime_budget["max_open_critical_events"],
                "open_runtime_critical_events": open_runtime_critical_events,
            }
        )

    gate_status = "pass" if not blockers else "block"
    return {
        "status": gate_status,
        "blockers": blockers,
        "signals": {
            "v2": {
                "status": v2_report.get("status"),
                "score": v2_report.get("score"),
                "global_block": bool(v2_report.get("global_block")),
            },
            "i18n_coverage": {
                "aggregate_coverage_pct": aggregate_i18n_pct,
                "health": i18n_health,
                "structural_coverage_pct": structural_i18n_pct,
                "structural_health": structural_i18n_health,
                "missing_keys_total": missing_keys_total,
            },
            "i18n_adoption": {
                "files_with_hardcoded_copy_without_t": hardcoded_copy_files,
                "status_summary": status_summary,
            },
            "runtime_error_budget": {
                "window_hours": runtime_budget["window_hours"],
                "max_open_critical_events": runtime_budget["max_open_critical_events"],
                "open_runtime_critical_events": open_runtime_critical_events,
                "status": "pass"
                if open_runtime_critical_events <= runtime_budget["max_open_critical_events"]
                else "block",
            },
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _apply_updates(config: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    next_config = copy.deepcopy(config)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and "." not in str(key):
            current_value = next_config.get(key)
            if isinstance(current_value, dict):
                _deep_merge_dict(current_value, value)
            else:
                next_config[key] = copy.deepcopy(value)
            continue
        _set_by_path(next_config, str(key), value)
    return _normalize_config(next_config)


@router.get("/config/global")
async def get_app_config(version: Optional[str] = None, request: Request = None):
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "config_global", 300, 60)
    if blocked:
        return blocked

    cache_version = version or "default"
    now = time.time()
    if (
        _CONFIG_CACHE["data"] is not None
        and _CONFIG_CACHE["version"] == cache_version
        and (now - float(_CONFIG_CACHE["ts"] or 0.0)) < _CONFIG_TTL_SECONDS
    ):
        config = copy.deepcopy(_CONFIG_CACHE["data"])
    else:
        try:
            config = await _load_persisted_config()
            if version and version < "1.0.0":
                config["features"]["tv_reality_enabled"] = False
                config["features"]["ai_phone_call_enabled"] = False
                config["updates"] = [
                    *config["updates"],
                    {
                        "id": "force_update",
                        "title": "Update Required",
                        "message": "Please update your app from the App Store to access new features.",
                        "type": "warning",
                    },
                ][:5]

            _CONFIG_CACHE["ts"] = now
            _CONFIG_CACHE["version"] = cache_version
            _CONFIG_CACHE["data"] = copy.deepcopy(config)
        except Exception:
            if _CONFIG_CACHE["data"]:
                config = copy.deepcopy(_CONFIG_CACHE["data"])
                config["cache_fallback"] = "stale"
            else:
                return {"error": "Failed to load config", "features": {}, "limits": {}, "updates": []}

    # Strip sensitive internal fields from public response
    config.pop("updated_by", None)
    config.pop("updated_at", None)
    config.pop("ai_settings", None)
    # Only expose integration names/categories (not internal config)
    if "integrations" in config:
        config["integrations"] = {
            k: {"label": v.get("label", k), "category": v.get("category", ""), "enabled": v.get("enabled", True)}
            for k, v in (config.get("integrations") or {}).items()
        }
    return config


@router.get("/config/boot-policy")
async def get_boot_policy(
    request: Request,
    client_policy_id: Optional[str] = None,
    client_cache_schema: Optional[str] = None,
):
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "config_boot_policy", 600, 60)
    if blocked:
        return blocked

    config = await _load_persisted_config()
    policy = _build_boot_policy_payload(config)

    policy_match = bool(client_policy_id and str(client_policy_id) == policy["policy_id"])
    required_cache_schema = str(policy.get("required_cache_schema") or "")
    client_cache_raw = str(client_cache_schema or "")
    cache_schema_match = True
    if required_cache_schema:
        cache_schema_match = bool(client_cache_raw and client_cache_raw.startswith(required_cache_schema))

    # Only enforce cache-schema mismatch when client actually reports a schema.
    cache_schema_enforced = bool(client_cache_raw)
    should_reload = bool(
        policy.get("force_reload_on_mismatch")
        and (
            (not policy_match)
            or (cache_schema_enforced and not cache_schema_match)
        )
    )

    return {
        "status": "ok",
        "policy": policy,
        "handshake": {
            "policy_match": policy_match,
            "cache_schema_match": cache_schema_match,
            "should_reload": should_reload,
        },
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/config/boot-policy/telemetry")
async def ingest_boot_policy_reload_telemetry(payload: BootPolicyReloadTelemetryIn, request: Request):
    from .db import db
    from routes.admin_push_notifications import emit_realtime_alert
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "config_boot_policy_telemetry", 1200, 60)
    if blocked:
        return blocked

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    event_type = str(payload.event_type or "should_reload_true")[:64]

    forwarded_ip = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    client_ip = forwarded_ip or (request.client.host if request.client else "unknown")

    doc = {
        "event_type": event_type,
        "policy_id": (str(payload.policy_id or "")[:120] or None),
        "client_policy_id": (str(payload.client_policy_id or "")[:120] or None),
        "client_cache_schema": (str(payload.client_cache_schema or "")[:220] or None),
        "route_path": (str(payload.route_path or "")[:260] or None),
        "route_query": (str(payload.route_query or "")[:260] or None),
        "host": (str(payload.host or "")[:120] or None),
        "source": str(payload.source or "boot_policy_handshake")[:80],
        "reason": (str(payload.reason or "")[:120] or None),
        "reload_attempt": int(payload.reload_attempt or 0),
        "user_agent": str(request.headers.get("user-agent") or "")[:260],
        "ip": str(client_ip)[:120],
        "created_at": now_iso,
    }
    await db[BOOT_POLICY_TELEMETRY_COLLECTION].insert_one(doc)

    window_start_iso = (now - timedelta(minutes=BOOT_POLICY_SPIKE_WINDOW_MINUTES)).isoformat()

    window_count = int(
        await db[BOOT_POLICY_TELEMETRY_COLLECTION].count_documents(
            {
                "event_type": "should_reload_true",
                "created_at": {"$gte": window_start_iso},
            }
        )
    )
    spike_detected = bool(window_count >= BOOT_POLICY_SPIKE_THRESHOLD)

    state = await db[BOOT_POLICY_MONITOR_STATE_COLLECTION].find_one(
        {"key": BOOT_POLICY_MONITOR_STATE_KEY},
        {"_id": 0},
    ) or {}
    last_alert_raw = state.get("last_alert_at")
    last_alert_dt = _parse_iso_datetime_safe(str(last_alert_raw)) if last_alert_raw else None
    cooldown_active = bool(
        last_alert_dt
        and (now - last_alert_dt).total_seconds() < (BOOT_POLICY_SPIKE_ALERT_COOLDOWN_MINUTES * 60)
    )

    alert_sent = False
    if spike_detected and not cooldown_active:
        title = "Boot-policy stale-session wave detected"
        message = (
            f"{window_count} handshake.should_reload=true signals observed in the last "
            f"{BOOT_POLICY_SPIKE_WINDOW_MINUTES} minutes."
        )
        try:
            await emit_realtime_alert(
                alert_type="boot_policy_should_reload_spike",
                severity="high",
                title=title,
                message=message,
            )
            alert_sent = True
        except Exception as exc:
            logger.warning("boot-policy reload spike alert emit failed: %s", exc)

        await db[BOOT_POLICY_MONITOR_EVENTS_COLLECTION].insert_one(
            {
                "alerted_at": now_iso,
                "event_type": "should_reload_true",
                "severity": "high",
                "window_minutes": BOOT_POLICY_SPIKE_WINDOW_MINUTES,
                "threshold": BOOT_POLICY_SPIKE_THRESHOLD,
                "window_count": window_count,
                "policy_id": doc.get("policy_id"),
                "host": doc.get("host"),
                "source": doc.get("source"),
                "reason": "should_reload_spike",
            }
        )

    state_payload = {
        "key": BOOT_POLICY_MONITOR_STATE_KEY,
        "updated_at": now_iso,
        "window_minutes": BOOT_POLICY_SPIKE_WINDOW_MINUTES,
        "threshold": BOOT_POLICY_SPIKE_THRESHOLD,
        "cooldown_minutes": BOOT_POLICY_SPIKE_ALERT_COOLDOWN_MINUTES,
        "current_window_count": window_count,
        "spike_detected": spike_detected,
        "cooldown_active": cooldown_active,
        "last_event": {
            "event_type": doc.get("event_type"),
            "host": doc.get("host"),
            "policy_id": doc.get("policy_id"),
            "source": doc.get("source"),
            "created_at": now_iso,
        },
    }
    if alert_sent:
        state_payload["last_alert_at"] = now_iso
        state_payload["last_alert_window_count"] = window_count
    elif state.get("last_alert_at"):
        state_payload["last_alert_at"] = state.get("last_alert_at")
        state_payload["last_alert_window_count"] = int(state.get("last_alert_window_count") or 0)

    await db[BOOT_POLICY_MONITOR_STATE_COLLECTION].update_one(
        {"key": BOOT_POLICY_MONITOR_STATE_KEY},
        {"$set": state_payload},
        upsert=True,
    )

    return {
        "ok": True,
        "event_type": event_type,
        "spike_detected": spike_detected,
        "current_window_count": window_count,
        "window_minutes": BOOT_POLICY_SPIKE_WINDOW_MINUTES,
        "threshold": BOOT_POLICY_SPIKE_THRESHOLD,
        "cooldown_minutes": BOOT_POLICY_SPIKE_ALERT_COOLDOWN_MINUTES,
        "alert_sent": alert_sent,
    }


@router.get("/config/admin/platform-settings")
async def get_platform_settings(request: Request):
    from .db import require_admin

    await require_admin(request)
    config = await _load_persisted_config()
    return {
        "config": config,
        "summary": _build_platform_settings_summary(config),
    }


@router.put("/config/admin/platform-settings")
async def update_platform_settings(body: PlatformSettingsUpdateRequest, request: Request):
    from .db import require_admin
    from utils.ws_manager import broadcast_data_change

    admin = await require_admin(request)
    current = await _load_persisted_config()
    updated = _apply_updates(current, body.updates)
    saved = await _save_persisted_config(updated, updated_by=getattr(admin, "email", "admin"))
    await broadcast_data_change("config", "updated")
    return {
        "status": "saved",
        "config": saved,
        "summary": _build_platform_settings_summary(saved),
    }


@router.post("/config/admin/update")
async def update_config(updates: Dict[str, Any], req: Request):
    from .db import require_admin
    from utils.ws_manager import broadcast_data_change

    admin = await require_admin(req)
    current = await _load_persisted_config()
    updated = _apply_updates(current, updates or {})
    saved = await _save_persisted_config(updated, updated_by=getattr(admin, "email", "admin"))
    await broadcast_data_change("config", "updated")
    return {"status": "saved", "current_config": saved}