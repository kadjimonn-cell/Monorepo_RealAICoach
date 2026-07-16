from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re
import uuid

from routes.payments_catalog import CANONICAL_PLAN_ORDER, DEFAULT_CANONICAL_PLANS
from utils.public_api_contract import is_public_api_path


DEFAULT_GPS_FAQ = [
    {
        "faq_id": "billing-cancel-anytime",
        "question": "Can I cancel anytime?",
        "answer": "Yes. You can cancel your subscription at any time from billing settings.",
        "category": "billing",
        "active": True,
        "lang": "en",
        "order": 10,
    },
    {
        "faq_id": "billing-annual-discount",
        "question": "Do you offer annual discounts?",
        "answer": "Yes. Annual billing includes a discount compared to monthly billing.",
        "category": "pricing",
        "active": True,
        "lang": "en",
        "order": 20,
    },
    {
        "faq_id": "billing-free-plan",
        "question": "Is there a free plan?",
        "answer": "Yes. The Free plan is available for getting started.",
        "category": "plans",
        "active": True,
        "lang": "en",
        "order": 30,
    },
]

INTEGRITY_ARTIFACT_DIR = Path("/app/test_reports/platform_integrity")
INTEGRITY_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

GPS_MIN_PLANS = 3
GPS_MIN_FAQ = 3
GPS_MIN_FEATURES = 25
GPS_MIN_TESTIMONIALS = 3
GPS_MIN_ACTIVITIES = 3
GPS_MAX_STATE_STALE_SECONDS = 15 * 60


def _slug_to_title(slug: str) -> str:
    return " ".join(part.capitalize() for part in str(slug or "").replace("_", "-").split("-") if part)


CANONICAL_FEATURE_IDS = [
    "ai-writer", "ai-chatbot", "ai-search", "ai-automations", "ai-cognitive",
    "medimate", "fitness", "pennypilot", "smartbuy", "travelpal",
    "ai-found-love", "smart-cars", "buy-smart-home", "ai-video", "ai-photo",
    "ai-speech", "ai-enterprise", "school-tutor", "bill-generator",
    "lexicon-intelligence", "watch-videos", "games-station", "travel-visa",
    "daily-meditation", "ai-learning-hub",
]


def _build_default_features() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for idx, feature_id in enumerate(CANONICAL_FEATURE_IDS):
        route = f"/features/{feature_id}"
        if feature_id == "ai-learning-hub":
            route = "/ai-learning-hub"
        elif feature_id == "lexicon-intelligence":
            route = "/features/lexicon-intelligence"
        rows.append(
            {
                "feature_id": feature_id,
                "title": _slug_to_title(feature_id),
                "description": f"{_slug_to_title(feature_id)} capability.",
                "icon": "sparkles",
                "route": route,
                "category": "platform",
                "color": "#14B8A6",
                "is_new": False,
                "premium": False,
                "enabled": True,
                "sort_order": idx,
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


DEFAULT_GPS_FEATURES = _build_default_features()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_plan_id(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _parse_iso_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


async def assess_gps_catalog_completeness(db, *, freshness_reference_iso: Any | None = None) -> dict[str, Any]:
    state = await db.global_platform_state.find_one(
        {"state_id": "global-platform-state"},
        {"_id": 0, "features": 1, "plans": 1, "faq": 1, "messaging": 1, "updated_at": 1},
    ) or {}

    features = [row for row in (state.get("features") or []) if bool(row.get("enabled", True))]
    plans = list(state.get("plans") or [])
    faq = [row for row in (state.get("faq") or []) if bool(row.get("active", True))]
    messaging = state.get("messaging") or {}
    testimonials = list(messaging.get("welcome_testimonials") or [])
    activities = list(messaging.get("welcome_activities") or [])

    plan_ids = {_normalize_plan_id(row.get("plan_id") or row.get("id")) for row in plans}
    plan_ids.discard("")

    missing_plan_ids = [plan_id for plan_id in CANONICAL_PLAN_ORDER if plan_id not in plan_ids]
    required_feature_ids = set(CANONICAL_FEATURE_IDS)
    feature_ids = {str(row.get("feature_id") or "").strip() for row in features if str(row.get("feature_id") or "").strip()}
    missing_feature_ids = sorted(required_feature_ids - feature_ids)

    state_updated_at = _parse_iso_ts(state.get("updated_at"))
    freshness_reference_at = _parse_iso_ts(freshness_reference_iso)
    effective_freshness_at = freshness_reference_at or state_updated_at
    age_seconds = None
    if effective_freshness_at:
        age_seconds = int((datetime.now(timezone.utc) - effective_freshness_at).total_seconds())

    failed_checks: list[str] = []
    if len(missing_plan_ids) > 0 or len(plans) < GPS_MIN_PLANS:
        failed_checks.append("plans_contract")
    if len(faq) < GPS_MIN_FAQ:
        failed_checks.append("faq_contract")
    if len(features) < GPS_MIN_FEATURES or len(missing_feature_ids) > 0:
        failed_checks.append("features_contract")
    if len(testimonials) < GPS_MIN_TESTIMONIALS:
        failed_checks.append("testimonials_contract")
    if len(activities) < GPS_MIN_ACTIVITIES:
        failed_checks.append("activities_contract")
    if age_seconds is None or age_seconds > GPS_MAX_STATE_STALE_SECONDS:
        failed_checks.append("freshness_contract")

    return {
        "features_count": len(features),
        "plans_count": len(plans),
        "faq_count": len(faq),
        "testimonials_count": len(testimonials),
        "activities_count": len(activities),
        "state_updated_at": state.get("updated_at"),
        "freshness_reference_at": freshness_reference_at.isoformat() if freshness_reference_at else None,
        "state_age_seconds": age_seconds,
        "missing_plan_ids": missing_plan_ids,
        "missing_feature_ids": missing_feature_ids,
        "feature_ids": sorted(feature_ids),
        "plan_ids": sorted(plan_ids),
        "thresholds": {
            "min_features": GPS_MIN_FEATURES,
            "min_plans": GPS_MIN_PLANS,
            "min_faq": GPS_MIN_FAQ,
            "min_testimonials": GPS_MIN_TESTIMONIALS,
            "min_activities": GPS_MIN_ACTIVITIES,
            "max_state_stale_seconds": GPS_MAX_STATE_STALE_SECONDS,
        },
        "failed_checks": failed_checks,
        "is_complete": len(failed_checks) == 0,
    }


async def ensure_gps_catalog_integrity(db, *, actor_user_id: str) -> dict[str, Any]:
    now = _now_iso()
    inserted_features: list[str] = []
    inserted_plans: list[str] = []
    inserted_faq: list[str] = []

    existing_features = await db.feature_registry.find({}, {"_id": 0, "feature_id": 1}).to_list(500)
    existing_feature_ids = {
        str(row.get("feature_id") or "").strip()
        for row in existing_features
        if str(row.get("feature_id") or "").strip()
    }

    max_sort_row = await db.feature_registry.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    next_sort = int((max_sort_row or {}).get("sort_order") or 0) + 1

    for feature in DEFAULT_GPS_FEATURES:
        feature_id = str(feature.get("feature_id") or "").strip()
        if not feature_id or feature_id in existing_feature_ids:
            continue
        payload = {
            **feature,
            "sort_order": next_sort,
            "created_at": now,
            "updated_at": now,
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
            "enabled": True,
        }
        next_sort += 1
        await db.feature_registry.update_one(
            {"feature_id": feature_id},
            {"$set": payload},
            upsert=True,
        )
        inserted_features.append(feature_id)

    if inserted_features:
        try:
            from routes import feature_registry as feature_registry_route

            if isinstance(getattr(feature_registry_route, "_registry_cache", None), dict):
                feature_registry_route._registry_cache["ts"] = 0
                feature_registry_route._registry_cache["data"] = None
        except Exception:
            pass

    existing_plans = await db.subscription_plans.find({}, {"_id": 0, "plan_id": 1, "id": 1}).to_list(200)
    existing_plan_ids = {
        _normalize_plan_id(row.get("plan_id") or row.get("id"))
        for row in existing_plans
    }
    existing_plan_ids.discard("")

    for plan_id in CANONICAL_PLAN_ORDER:
        if plan_id in existing_plan_ids:
            continue
        payload = {
            **DEFAULT_CANONICAL_PLANS[plan_id],
            "plan_id": plan_id,
            "id": plan_id,
            "created_at": now,
            "updated_at": now,
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
        }
        await db.subscription_plans.update_one(
            {"plan_id": plan_id},
            {"$set": payload},
            upsert=True,
        )
        inserted_plans.append(plan_id)

    existing_faq = await db.faq_content.find({"active": True}, {"_id": 0, "faq_id": 1, "question": 1}).to_list(200)
    existing_faq_ids = {
        str(row.get("faq_id") or "").strip().lower()
        for row in existing_faq
        if str(row.get("faq_id") or "").strip()
    }
    existing_questions = {
        str(row.get("question") or "").strip().lower()
        for row in existing_faq
        if str(row.get("question") or "").strip()
    }

    for idx, row in enumerate(DEFAULT_GPS_FAQ):
        faq_id = str(row.get("faq_id") or "").strip().lower()
        question_key = str(row.get("question") or "").strip().lower()
        if faq_id in existing_faq_ids or question_key in existing_questions:
            continue
        payload = {
            **row,
            "faq_id": faq_id,
            "order": int(row.get("order") or (idx + 1) * 10),
            "created_at": now,
            "updated_at": now,
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
        }
        await db.faq_content.update_one(
            {"faq_id": faq_id},
            {"$set": payload},
            upsert=True,
        )
        inserted_faq.append(faq_id)

    if inserted_features or inserted_plans or inserted_faq:
        from routes.global_platform_state import sync_global_faq, sync_global_plans
        from routes.global_platform_state import sync_global_features

        await sync_global_features(reason="Catalog guard canonicalized features", actor_user_id=actor_user_id)

        await sync_global_plans(reason="Catalog guard canonicalized plans", actor_user_id=actor_user_id)
        await sync_global_faq(reason="Catalog guard canonicalized FAQ", actor_user_id=actor_user_id)

    after = await assess_gps_catalog_completeness(db)
    return {
        "timestamp": now,
        "actor_user_id": actor_user_id,
        "inserted_features": inserted_features,
        "inserted_plans": inserted_plans,
        "inserted_faq": inserted_faq,
        "repaired": bool(inserted_features or inserted_plans or inserted_faq),
        "completeness": after,
    }


def _parse_theme_gate(stdout: str) -> dict[str, Any]:
    text = str(stdout or "")
    grade = "UNKNOWN"
    warns = 0
    fails = 0
    files = 0
    match = re.search(r"Grade:\s*([A-Z?])\s*\|\s*Warns:\s*(\d+)\s*\|\s*Fails:\s*(\d+)\s*\|.*?Files:\s*(\d+)", text)
    if match:
        grade = str(match.group(1))
        warns = int(match.group(2))
        fails = int(match.group(3))
        files = int(match.group(4))
    return {
        "grade": grade,
        "warns": warns,
        "fails": fails,
        "files_scanned": files,
        "raw_excerpt": text[-500:],
    }


async def generate_platform_integrity_artifact(
    db,
    *,
    source: str,
) -> dict[str, Any]:
    from routes.payments_catalog import get_subscription_plan_catalog
    from services.gtec_scan_v2 import get_latest_matrix64_pipeline_run
    import subprocess

    gps = await db.global_platform_state.find_one({"state_id": "global-platform-state"}, {"_id": 0}) or {}
    completeness = await assess_gps_catalog_completeness(db)
    plans = await get_subscription_plan_catalog(include_deprecated=False)
    matrix64 = await get_latest_matrix64_pipeline_run(db)
    messaging = gps.get("messaging") or {}
    testimonials = list(messaging.get("welcome_testimonials") or [])
    activities = list(messaging.get("welcome_activities") or [])
    seeded_testimonials = sum(1 for row in testimonials if bool((row or {}).get("seeded")))
    seeded_activities = sum(1 for row in activities if bool((row or {}).get("seeded")))

    try:
        proc = subprocess.run(
            ["node", "/app/frontend/scripts/theme-build-gate.js"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        theme_gate = _parse_theme_gate(proc.stdout)
        theme_gate["exit_code"] = int(proc.returncode)
    except Exception as exc:
        theme_gate = {
            "grade": "UNKNOWN",
            "warns": 0,
            "fails": 1,
            "files_scanned": 0,
            "exit_code": 1,
            "error": str(exc),
        }

    run_id = f"platform_integrity_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    artifact = {
        "run_id": run_id,
        "generated_at": _now_iso(),
        "source": source,
        "gps_counts": {
            "features": len(gps.get("features") or []),
            "plans": len(gps.get("plans") or []),
            "faq": len(gps.get("faq") or []),
        },
        "catalog_completeness": completeness,
        "subscription_catalog": {
            "count": len(plans),
            "plan_ids": [str(row.get("plan_id") or row.get("id") or "") for row in plans],
        },
        "public_endpoint_contract": {
            "subscriptions_plans_public": is_public_api_path("/api/subscriptions/plans"),
            "gps_state_public": is_public_api_path("/api/gps/state"),
            "features_registry_public": is_public_api_path("/api/features/registry"),
            "live_metrics_public": is_public_api_path("/api/system/live-metrics"),
        },
        "social_proof_integrity": {
            "testimonials_total": len(testimonials),
            "testimonials_seeded": seeded_testimonials,
            "activities_total": len(activities),
            "activities_seeded": seeded_activities,
        },
        "theme_gate": theme_gate,
        "matrix64": {
            "run_id": matrix64.get("run_id"),
            "status": matrix64.get("status"),
            "strict_passed": bool(matrix64.get("strict_passed")),
            "failed_checks": ((matrix64.get("counts") or {}).get("failed_checks")) or 0,
        },
        "rollback_criteria": {
            "trigger_when": [
                "catalog_completeness.is_complete == false",
                "theme_gate.fails > 0",
                "matrix64.strict_passed == false",
            ],
            "action": "mark_degraded_and_require_operator_review",
        },
    }

    path = INTEGRITY_ARTIFACT_DIR / f"{run_id}.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    artifact["artifact_path"] = str(path)

    await db.platform_integrity_artifacts.update_one(
        {"run_id": run_id},
        {"$set": artifact},
        upsert=True,
    )
    return artifact
