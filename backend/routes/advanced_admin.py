"""Access Matrix & Experimentation / A-B Testing APIs."""

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone, timedelta
import hashlib
import logging
import math
import uuid
from utils.pagination import iter_find_paginated

from .db import db, require_auth

logger = logging.getLogger("routes.advanced_admin")

# ──────────────────── ACCESS MATRIX ────────────────────
access_matrix_router = APIRouter(prefix="/access-matrix", tags=["Access Matrix"])

BUILTIN_ROLES = {
    "owner": {"level": 100, "label": "Owner", "color": "#F59E0B", "permissions": ["*"]},
    "admin": {
        "level": 80,
        "label": "Admin",
        "color": "#EF4444",
        "permissions": [
            "manage_members",
            "manage_settings",
            "view_analytics",
            "edit_docs",
            "manage_interviews",
            "manage_jobs",
        ],
    },
    "manager": {
        "level": 60,
        "label": "Manager",
        "color": "#8B5CF6",
        "permissions": ["view_analytics", "edit_docs", "manage_interviews", "manage_jobs"],
    },
    "member": {"level": 40, "label": "Member", "color": "#3B82F6", "permissions": ["edit_docs", "manage_interviews"]},
    "viewer": {"level": 20, "label": "Viewer", "color": "#6B7280", "permissions": ["view_docs", "view_interviews"]},
}

ALL_PERMISSIONS = [
    {"id": "manage_members", "label": "Manage Members", "category": "team"},
    {"id": "manage_settings", "label": "Manage Settings", "category": "team"},
    {"id": "view_analytics", "label": "View Analytics", "category": "analytics"},
    {"id": "edit_docs", "label": "Edit Documents", "category": "content"},
    {"id": "manage_interviews", "label": "Manage Interviews", "category": "hiring"},
    {"id": "manage_jobs", "label": "Manage Jobs", "category": "hiring"},
    {"id": "view_docs", "label": "View Documents", "category": "content"},
    {"id": "view_interviews", "label": "View Interviews", "category": "hiring"},
]


@access_matrix_router.get("/overview")
async def get_access_matrix(request: Request):
    """Executive-grade access matrix with all roles and permissions."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Builtin roles
    builtin = []
    for rid, r in BUILTIN_ROLES.items():
        perm_map = {}
        for p in ALL_PERMISSIONS:
            perm_map[p["id"]] = "*" in r["permissions"] or p["id"] in r["permissions"]
        builtin.append(
            {
                "role_id": rid,
                "name": r["label"],
                "level": r["level"],
                "color": r["color"],
                "type": "builtin",
                "permissions": perm_map,
            }
        )

    # Custom roles from all teams
    custom_roles = await db.custom_roles.find({}, {"_id": 0}).to_list(100)
    custom = []
    for cr in custom_roles:
        perm_map = {}
        for p in ALL_PERMISSIONS:
            perm_map[p["id"]] = p["id"] in (cr.get("permissions") or [])
        team = await db.teams.find_one({"team_id": cr.get("team_id")}, {"_id": 0, "name": 1})
        custom.append(
            {
                "role_id": cr.get("role_id"),
                "name": cr.get("name", "Unnamed"),
                "level": cr.get("level", 50),
                "color": cr.get("color", "#6B7280"),
                "type": "custom",
                "team_name": team.get("name", "Unknown") if team else "N/A",
                "permissions": perm_map,
            }
        )

    # Member counts per role
    role_pipeline = [{"$unwind": "$members"}, {"$group": {"_id": "$members.role", "count": {"$sum": 1}}}]
    role_counts = {r["_id"]: r["count"] for r in await db.teams.aggregate(role_pipeline).to_list(20)}

    # Permission usage stats
    perm_usage = []
    for p in ALL_PERMISSIONS:
        granted = sum(1 for r in builtin + custom if r["permissions"].get(p["id"]))
        perm_usage.append(
            {
                "permission_id": p["id"],
                "label": p["label"],
                "category": p["category"],
                "granted_to": granted,
                "total_roles": len(builtin) + len(custom),
            }
        )

    return {
        "permissions": ALL_PERMISSIONS,
        "builtin_roles": builtin,
        "custom_roles": custom,
        "role_member_counts": role_counts,
        "permission_usage": perm_usage,
        "total_roles": len(builtin) + len(custom),
        "total_permissions": len(ALL_PERMISSIONS),
    }


# ──────────────────── ONBOARDING A/B TESTING ────────────────────
ab_testing_router = APIRouter(prefix="/onboarding-ab", tags=["A/B Testing"])

ONBOARDING_STEPS = [
    {"id": "welcome", "label": "Welcome Tour"},
    {"id": "discover", "label": "Job Discovery"},
    {"id": "hiring", "label": "AI Hiring"},
    {"id": "employer", "label": "Jobs Portal"},
    {"id": "coach", "label": "Interview Coach"},
    {"id": "mock", "label": "Mock Interview"},
    {"id": "docs", "label": "Collab Docs"},
    {"id": "profile", "label": "Complete Profile"},
    {"id": "first_search", "label": "First Job Search"},
]

EXPERIMENT_TARGET_TYPES = [
    {"id": "frontend_feature", "label": "Frontend Feature"},
    {"id": "api_response", "label": "API Response"},
]

EXPERIMENT_SCOPES = [
    {"id": "frontend_only", "label": "Frontend Only"},
    {"id": "frontend_api", "label": "Frontend + API"},
    {"id": "api_only", "label": "API Only"},
]


def _normalize_variants(variants: list[dict] | None) -> list[dict]:
    raw_variants = variants or []
    if len(raw_variants) < 2:
        raw_variants = [
            {"id": "control", "label": "Control", "config": {}, "allocation_pct": 50},
            {"id": "variant_a", "label": "Variant A", "config": {}, "allocation_pct": 50},
        ]

    normalized = []
    for index, variant in enumerate(raw_variants):
        allocation_pct = variant.get("allocation_pct")
        try:
            allocation_pct = float(allocation_pct) if allocation_pct is not None else None
        except Exception:
            allocation_pct = None
        normalized.append(
            {
                "id": variant.get("id") or f"variant_{uuid.uuid4().hex[:6]}",
                "label": variant.get("label") or f"Variant {chr(65 + index)}",
                "config": variant.get("config") or {},
                "allocation_pct": allocation_pct,
                "is_paused": bool(variant.get("is_paused", False)),
                "is_retired": bool(variant.get("is_retired", False)),
                "promoted": bool(variant.get("promoted", False)),
            }
        )

    valid_allocations = [v["allocation_pct"] for v in normalized if v["allocation_pct"] is not None and v["allocation_pct"] > 0]
    if len(valid_allocations) != len(normalized):
        even_split = round(100 / len(normalized), 2)
        for variant in normalized:
            variant["allocation_pct"] = even_split
    else:
        total = sum(valid_allocations)
        if total <= 0:
            even_split = round(100 / len(normalized), 2)
            for variant in normalized:
                variant["allocation_pct"] = even_split
        else:
            for variant in normalized:
                variant["allocation_pct"] = round((float(variant["allocation_pct"]) / total) * 100, 2)

    rounding_gap = round(100 - sum(v["allocation_pct"] for v in normalized), 2)
    if normalized and rounding_gap != 0:
        normalized[0]["allocation_pct"] = round(normalized[0]["allocation_pct"] + rounding_gap, 2)
    return normalized


def _pick_weighted_variant(identity_key: str, experiment_id: str, variants: list[dict]) -> dict:
    active_variants = [variant for variant in variants if not variant.get("is_paused") and not variant.get("is_retired")]
    if not active_variants:
        raise HTTPException(status_code=400, detail="No active variants available")

    seed = hashlib.md5(f"{identity_key}:{experiment_id}".encode()).hexdigest()
    bucket = (int(seed[:8], 16) / 0xFFFFFFFF) * 100
    cumulative = 0.0
    for variant in active_variants:
        cumulative += float(variant.get("allocation_pct", 0) or 0)
        if bucket <= cumulative:
            return variant
    return active_variants[-1]


def _build_variant_results(exp: dict, assignments: list[dict], events: list[dict]) -> list[dict]:
    best_perf = None
    rows = []
    for variant in exp.get("variants", []):
        vid = variant["id"]
        assigned = [item for item in assignments if item.get("variant_id") == vid]
        variant_events = [item for item in events if item.get("variant_id") == vid]
        converted = [item for item in assigned if item.get("converted")]
        engagement_events = [item for item in variant_events if item.get("event_type") == "engagement"]
        impression_events = [item for item in variant_events if item.get("event_type") == "impression"]
        error_events = [item for item in variant_events if item.get("event_type") == "error"]
        performance_events = [item for item in variant_events if item.get("event_type") == "performance"]

        engaged_users = {item.get("identity_key") or item.get("user_id") for item in engagement_events + [*variant_events] if item.get("event_type") in {"engagement", "conversion"}}
        error_users = {item.get("identity_key") or item.get("user_id") for item in error_events}
        perf_samples = [float(item.get("metric_value") or 0) for item in performance_events if float(item.get("metric_value") or 0) > 0]
        avg_perf = round(sum(perf_samples) / len(perf_samples), 1) if perf_samples else None
        if avg_perf and (best_perf is None or avg_perf < best_perf):
            best_perf = avg_perf

        assigned_count = len(assigned)
        converted_count = len(converted)
        engagement_rate = round((len(engaged_users) / max(assigned_count, 1)) * 100, 1)
        conversion_rate = round((converted_count / max(assigned_count, 1)) * 100, 1)
        error_rate = round((len(error_users) / max(assigned_count, 1)) * 100, 1)

        rows.append(
            {
                "variant_id": vid,
                "label": variant.get("label", vid),
                "assigned": assigned_count,
                "converted": converted_count,
                "conversion_rate": conversion_rate,
                "engagement_events": len(engagement_events),
                "engaged_users": len([user for user in engaged_users if user]),
                "engagement_rate": engagement_rate,
                "impressions": len(impression_events),
                "errors": len(error_events),
                "error_users": len([user for user in error_users if user]),
                "error_rate": error_rate,
                "avg_performance_ms": avg_perf,
                "performance_samples": len(perf_samples),
                "allocation_pct": variant.get("allocation_pct", 0),
                "is_paused": bool(variant.get("is_paused", False)),
                "is_retired": bool(variant.get("is_retired", False)),
                "success_count": max(converted_count, len([user for user in engaged_users if user])),
            }
        )

    for row in rows:
        avg_perf = row.get("avg_performance_ms")
        if best_perf and avg_perf:
            perf_gap_pct = max(0.0, ((avg_perf - best_perf) / best_perf) * 100)
            performance_score = max(0.0, round(100 - perf_gap_pct, 1))
        else:
            performance_score = 100.0
        reliability_score = max(0.0, round(100 - (row.get("error_rate", 0) * 4), 1))
        row["performance_score"] = performance_score
        row["reliability_score"] = reliability_score
        row["composite_score"] = round(
            row.get("engagement_rate", 0) * 0.4
            + row.get("conversion_rate", 0) * 0.25
            + performance_score * 0.25
            + reliability_score * 0.10,
            1,
        )
    return rows


def _compute_confidence(sorted_variants: list) -> float:
    """Compute statistical confidence using z-test between top two variants."""
    if len(sorted_variants) < 2:
        return 0
    best = sorted_variants[0]
    second = sorted_variants[1]
    n1, n2 = best["assigned"], second["assigned"]
    if n1 < 5 or n2 < 5:
        return 0
    s1 = best.get("success_count", best.get("converted", 0))
    s2 = second.get("success_count", second.get("converted", 0))
    p1 = s1 / max(n1, 1)
    p2 = s2 / max(n2, 1)
    p_pool = (s1 + s2) / max(n1 + n2, 1)
    if p_pool <= 0 or p_pool >= 1:
        return 0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0
    z = abs(p1 - p2) / se
    if z >= 2.576:
        return 99.0
    if z >= 1.96:
        return 95.0 + (z - 1.96) / (2.576 - 1.96) * 4
    if z >= 1.645:
        return 90.0 + (z - 1.645) / (1.96 - 1.645) * 5
    if z >= 1.28:
        return 80.0 + (z - 1.28) / (1.645 - 1.28) * 10
    return min(80, z / 1.28 * 80)


async def _evaluate_experiment_core(exp: dict) -> dict:
    experiment_id = exp["experiment_id"]
    assignments: list[dict] = []
    async for assignment in iter_find_paginated(db.ab_assignments, {"experiment_id": experiment_id}, {"_id": 0}):
        assignments.append(assignment)

    events: list[dict] = []
    async for event in iter_find_paginated(db.ab_conversions, {"experiment_id": experiment_id}, {"_id": 0}):
        events.append(event)
    variant_results = _build_variant_results(exp, assignments, events)
    sorted_variants = sorted(variant_results, key=lambda item: (item.get("composite_score", 0), item.get("engagement_rate", 0)), reverse=True)
    confidence = _compute_confidence(sorted_variants)
    total_participants = len(assignments)
    min_participants = exp.get("min_participants", 30)
    significance_reached = confidence >= exp.get("confidence_threshold", 95) and total_participants >= min_participants and len(sorted_variants) >= 2
    winner = sorted_variants[0]["variant_id"] if significance_reached and sorted_variants else None
    return {
        "experiment": exp,
        "variant_results": variant_results,
        "total_participants": total_participants,
        "winner": winner,
        "winner_detected_at": exp.get("winner_detected_at"),
        "auto_winner_enabled": exp.get("auto_winner", True),
        "confidence": confidence,
        "significance_reached": significance_reached,
        "performance_goal": exp.get("performance_goal", "lower_is_better"),
        "engagement_goal": exp.get("engagement_goal", "higher_is_better"),
        "error_goal": exp.get("error_goal", "lower_is_better"),
    }


async def _promote_experiment_winner(exp: dict, results: dict) -> dict | None:
    winner_id = results.get("winner")
    if not winner_id:
        return None
    now = datetime.now(timezone.utc).isoformat()
    updated_variants = []
    winner_variant = None
    retired_variant_ids = []
    for variant in exp.get("variants", []):
        variant_copy = {**variant}
        if variant["id"] == winner_id:
            variant_copy["promoted"] = True
            variant_copy["promoted_at"] = now
            winner_variant = variant_copy
        else:
            variant_copy["is_paused"] = True
            variant_copy["is_retired"] = True
            variant_copy["paused_at"] = now
            variant_copy["retired_at"] = now
            variant_copy["paused_reason"] = "auto_promoted_winner"
            retired_variant_ids.append(variant["id"])
        updated_variants.append(variant_copy)

    await db.ab_experiments.update_one(
        {"experiment_id": exp["experiment_id"]},
        {
            "$set": {
                "winner_variant_id": winner_id,
                "winner_detected_at": now,
                "promoted_at": now,
                "status": "promoted",
                "variants": updated_variants,
                "retired_variant_ids": retired_variant_ids,
                "updated_at": now,
                "promoted_config": (winner_variant or {}).get("config", {}),
            }
        },
    )

    winner_row = next((row for row in results.get("variant_results", []) if row["variant_id"] == winner_id), None)
    winner_event = {
        "event_id": f"awe_{uuid.uuid4().hex[:10]}",
        "experiment_id": exp["experiment_id"],
        "experiment_name": exp.get("name"),
        "winner_variant_id": winner_id,
        "winner_label": (winner_variant or {}).get("label", winner_id),
        "confidence": results.get("confidence", 0),
        "total_participants": results.get("total_participants", 0),
        "variant_results": results.get("variant_results", []),
        "detected_at": now,
        "target_key": exp.get("target_key", exp.get("step_id")),
        "target_type": exp.get("target_type", "frontend_feature"),
        "scope": exp.get("scope", "frontend_api"),
        "composite_score": (winner_row or {}).get("composite_score", 0),
    }
    await db.ab_winner_events.insert_one({**winner_event})
    return winner_event


@ab_testing_router.get("/experiments")
async def list_experiments(request: Request):
    """List all A/B experiments."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    experiments = await db.ab_experiments.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {
        "experiments": experiments,
        "onboarding_steps": ONBOARDING_STEPS,
        "target_types": EXPERIMENT_TARGET_TYPES,
        "scopes": EXPERIMENT_SCOPES,
    }


@ab_testing_router.post("/experiments")
async def create_experiment(request: Request):
    """Create a new A/B experiment with multi-variate support."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    target_key = body.get("target_key") or body.get("step_id", "welcome")
    target_type = body.get("target_type", "frontend_feature")
    scope = body.get("scope", "frontend_api")
    variants = _normalize_variants(body.get("variants"))

    existing = await db.ab_experiments.find_one(
        {"target_key": target_key, "target_type": target_type, "status": {"$in": ["active", "promoted"]}},
        {"_id": 0, "experiment_id": 1},
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Active experiment already exists for {target_type}:{target_key}")

    experiment = {
        "experiment_id": f"exp_{uuid.uuid4().hex[:10]}",
        "name": body.get("name", "Untitled Experiment"),
        "step_id": target_key,
        "target_key": target_key,
        "target_type": target_type,
        "scope": scope,
        "variants": variants,
        "status": "active",
        "traffic_split": body.get("traffic_split", "custom" if any(v.get("allocation_pct") != round(100 / len(variants), 2) for v in variants) else round(100 / len(variants))),
        "auto_winner": body.get("auto_promote", body.get("auto_winner", True)),
        "min_participants": body.get("min_participants", 30),
        "confidence_threshold": body.get("confidence_threshold", 95),
        "performance_goal": body.get("performance_goal", "lower_is_better"),
        "engagement_goal": body.get("engagement_goal", "higher_is_better"),
        "error_goal": body.get("error_goal", "lower_is_better"),
        "winner_variant_id": None,
        "winner_detected_at": None,
        "promoted_at": None,
        "retired_variant_ids": [],
        "promoted_config": None,
        "created_at": now,
        "updated_at": now,
        "created_by": user.user_id,
    }
    await db.ab_experiments.insert_one({**experiment})
    return {"success": True, "experiment": experiment}


@ab_testing_router.put("/experiments/{experiment_id}")
async def update_experiment(experiment_id: str, request: Request):
    """Update experiment status, config, or variants."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    updates = {"updated_at": now}
    for field in (
        "status",
        "traffic_split",
        "name",
        "auto_winner",
        "min_participants",
        "confidence_threshold",
        "variants",
        "target_key",
        "target_type",
        "scope",
        "performance_goal",
        "engagement_goal",
        "error_goal",
    ):
        if field in body:
            updates[field] = _normalize_variants(body[field]) if field == "variants" else body[field]
    result = await db.ab_experiments.update_one({"experiment_id": experiment_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"success": True}


@ab_testing_router.delete("/experiments/{experiment_id}")
async def delete_experiment(experiment_id: str, request: Request):
    """Delete an experiment."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    await db.ab_experiments.delete_one({"experiment_id": experiment_id})
    return {"success": True}


@ab_testing_router.get("/experiments/{experiment_id}/results")
async def get_experiment_results(experiment_id: str, request: Request):
    """Get variant performance results with statistical significance."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    exp = await db.ab_experiments.find_one({"experiment_id": experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return await _evaluate_experiment_core(exp)


@ab_testing_router.post("/assign")
async def assign_user_to_variant(request: Request):
    """Auto-assign a user to an experiment variant (supports multi-variate)."""
    user = await require_auth(request)
    body = await request.json()
    target_key = body.get("target_key") or body.get("step_id")
    target_type = body.get("target_type", "frontend_feature")
    identity_key = body.get("identity_key") or user.user_id
    if not target_key:
        raise HTTPException(status_code=400, detail="target_key or step_id required")

    exp = await db.ab_experiments.find_one(
        {"target_key": target_key, "target_type": target_type, "status": {"$in": ["active", "promoted"]}},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )
    if not exp:
        exp = await db.ab_experiments.find_one({"step_id": target_key, "status": {"$in": ["active", "promoted"]}}, {"_id": 0})
    if not exp:
        return {"assigned": False, "variant_id": None}

    existing = await db.ab_assignments.find_one(
        {"identity_key": identity_key, "experiment_id": exp["experiment_id"]}, {"_id": 0}
    )
    if existing:
        return {
            "assigned": True,
            "variant_id": existing["variant_id"],
            "variant_name": existing.get("variant_name"),
            "config": existing.get("config", {}),
            "experiment_id": exp["experiment_id"],
            "target_key": exp.get("target_key", exp.get("step_id")),
            "target_type": exp.get("target_type", "frontend_feature"),
            "promoted": exp.get("status") == "promoted",
        }

    if exp.get("status") == "promoted" and exp.get("winner_variant_id"):
        promoted_variant = next((variant for variant in exp.get("variants", []) if variant["id"] == exp.get("winner_variant_id")), None)
        if not promoted_variant:
            return {"assigned": False, "variant_id": None}
        return {
            "assigned": True,
            "variant_id": promoted_variant["id"],
            "variant_name": promoted_variant.get("label", promoted_variant["id"]),
            "config": promoted_variant.get("config", {}),
            "experiment_id": exp["experiment_id"],
            "target_key": exp.get("target_key", exp.get("step_id")),
            "target_type": exp.get("target_type", "frontend_feature"),
            "promoted": True,
        }

    variants = [v for v in exp.get("variants", []) if not v.get("is_paused") and not v.get("is_retired")]
    if not variants:
        return {"assigned": False, "variant_id": None}
    variant = _pick_weighted_variant(identity_key, exp["experiment_id"], variants)

    now = datetime.now(timezone.utc).isoformat()
    assignment = {
        "assignment_id": f"asgn_{uuid.uuid4().hex[:10]}",
        "experiment_id": exp["experiment_id"],
        "user_id": user.user_id,
        "identity_key": identity_key,
        "variant_id": variant["id"],
        "variant_name": variant.get("label", variant["id"]),
        "config": variant.get("config", {}),
        "step_id": exp.get("step_id", target_key),
        "target_key": exp.get("target_key", target_key),
        "target_type": exp.get("target_type", target_type),
        "scope": exp.get("scope", "frontend_api"),
        "converted": False,
        "assigned_at": now,
    }
    await db.ab_assignments.insert_one({**assignment})
    await db.ab_conversions.insert_one(
        {
            "event_id": f"abe_{uuid.uuid4().hex[:10]}",
            "experiment_id": exp["experiment_id"],
            "variant_id": variant["id"],
            "user_id": user.user_id,
            "identity_key": identity_key,
            "target_key": exp.get("target_key", target_key),
            "event_type": "impression",
            "metric_value": None,
            "metadata": body.get("metadata") or {},
            "created_at": now,
        }
    )
    return {
        "assigned": True,
        "variant_id": variant["id"],
        "variant_name": variant.get("label", variant["id"]),
        "config": variant.get("config", {}),
        "experiment_id": exp["experiment_id"],
        "target_key": exp.get("target_key", target_key),
        "target_type": exp.get("target_type", target_type),
        "promoted": False,
    }


@ab_testing_router.post("/convert")
async def mark_conversion(request: Request):
    """Mark a user as converted in their assigned experiment."""
    user = await require_auth(request)
    body = await request.json()
    experiment_id = body.get("experiment_id")
    identity_key = body.get("identity_key") or user.user_id
    if not experiment_id:
        raise HTTPException(status_code=400, detail="experiment_id required")
    now = datetime.now(timezone.utc).isoformat()
    assignment = await db.ab_assignments.find_one({"identity_key": identity_key, "experiment_id": experiment_id}, {"_id": 0})
    result = await db.ab_assignments.update_one(
        {"identity_key": identity_key, "experiment_id": experiment_id}, {"$set": {"converted": True, "converted_at": now}}
    )
    if result.matched_count > 0 and assignment:
        await db.ab_conversions.insert_one(
            {
                "event_id": f"abe_{uuid.uuid4().hex[:10]}",
                "experiment_id": experiment_id,
                "variant_id": assignment.get("variant_id"),
                "user_id": user.user_id,
                "identity_key": identity_key,
                "target_key": assignment.get("target_key"),
                "event_type": "conversion",
                "metric_value": 1,
                "metadata": body.get("metadata") or {},
                "created_at": now,
            }
        )
    return {"success": result.matched_count > 0}


@ab_testing_router.post("/track")
async def track_experiment_metric(request: Request):
    """Track performance, engagement, error, or impression events for an experiment variant."""
    user = await require_auth(request)
    body = await request.json()
    experiment_id = body.get("experiment_id")
    event_type = str(body.get("event_type") or "").strip().lower()
    identity_key = body.get("identity_key") or user.user_id
    if not experiment_id or not event_type:
        raise HTTPException(status_code=400, detail="experiment_id and event_type required")
    if event_type not in {"impression", "engagement", "error", "performance", "conversion"}:
        raise HTTPException(status_code=400, detail="Unsupported event_type")

    assignment = await db.ab_assignments.find_one({"identity_key": identity_key, "experiment_id": experiment_id}, {"_id": 0})
    variant_id = body.get("variant_id") or (assignment or {}).get("variant_id")
    if not variant_id:
        raise HTTPException(status_code=404, detail="Variant assignment not found")

    metric_value = body.get("metric_value")
    try:
        metric_value = float(metric_value) if metric_value is not None else None
    except Exception:
        metric_value = None

    now = datetime.now(timezone.utc).isoformat()
    await db.ab_conversions.insert_one(
        {
            "event_id": f"abe_{uuid.uuid4().hex[:10]}",
            "experiment_id": experiment_id,
            "variant_id": variant_id,
            "user_id": user.user_id,
            "identity_key": identity_key,
            "target_key": body.get("target_key") or (assignment or {}).get("target_key"),
            "event_type": event_type,
            "metric_value": metric_value,
            "metadata": body.get("metadata") or {},
            "created_at": now,
        }
    )
    return {"success": True, "experiment_id": experiment_id, "variant_id": variant_id, "event_type": event_type}

async def auto_winner_check():
    """Scheduled job: detect winners and automatically promote the best variant."""
    try:
        active_exps = await db.ab_experiments.find(
            {"status": "active", "auto_winner": True, "winner_variant_id": None}, {"_id": 0}
        ).to_list(100)

        for exp in active_exps:
            results = await _evaluate_experiment_core(exp)
            if results.get("significance_reached") and results.get("winner"):
                winner_event = await _promote_experiment_winner(exp, results)

                # Send email alert to admins
                try:
                    from utils.email_notifications import _send_and_log

                    admins = await db.users.find(
                        {"is_admin": True}, {"_id": 0, "email": 1, "name": 1, "user_id": 1}
                    ).to_list(10)
                    for admin in admins:
                        subject = f"A/B Winner Detected: {exp.get('name', 'Experiment')}"
                        html = f"""
                        <div class="em-force-light-card" style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:20px;">
                          <div style="background:#0f172a;padding:20px;border-radius:12px;">
                            <h2 style="color:#10B981;margin:0;">Winner Detected</h2>
                            <p style="color:#94a3b8;margin:4px 0 0 0;">Experiment: {exp.get("name")}</p>
                          </div>
                          <div class="em-force-light-card" style="background:#FFFFFF;padding:20px 0 0 0;">
                            <p class="em-force-muted-text" style="color:#475569;margin:0 0 12px 0;">
                              <strong class="em-force-dark-text" style="color:#10B981;">{winner_event.get('winner_label') if winner_event else results['winner']}</strong> has won with 
                              <strong class="em-force-dark-text">{(next((v for v in results['variant_results'] if v['variant_id'] == results['winner']), {}) or {}).get('composite_score', 0)}</strong> composite score 
                              ({results['confidence']:.0f}% confidence).
                            </p>
                            <table class="em-force-light-card" style="width:100%;border-collapse:collapse;background:#FFFFFF;">
                              {"".join(f'<tr><td style="padding:6px;color:#64748B;border-bottom:1px solid #E2E8F0;">{v["label"]}</td><td style="padding:6px;color:#0F172A;text-align:right;border-bottom:1px solid #E2E8F0;">eng {v["engagement_rate"]}% • perf {v.get("avg_performance_ms") or 0}ms • err {v["error_rate"]}%</td></tr>' for v in sorted(results['variant_results'], key=lambda x: x['composite_score'], reverse=True))}
                            </table>
                            <p class="em-force-muted-text" style="color:#64748b;font-size:12px;margin:12px 0 0 0;">
                              Losing variants were automatically retired. Total participants: {results['total_participants']}
                            </p>
                          </div>
                        </div>
                        """
                        await _send_and_log(
                            user_id=admin["user_id"],
                            email=admin["email"],
                            subject=subject,
                            html=html,
                            email_type="ab_winner_alert",
                        )
                except Exception as e:
                    logger.warning(f"Failed to send AB winner email: {e}")

                logger.info(f"Auto-winner: {exp.get('name')} -> {results['winner']} ({results['confidence']:.1f}% confidence)")

    except Exception as e:
        logger.error(f"Auto-winner check failed: {e}")


@ab_testing_router.post("/experiments/{experiment_id}/evaluate")
async def evaluate_experiment(experiment_id: str, request: Request):
    """Manually evaluate an experiment and auto-promote if thresholds are met."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    exp = await db.ab_experiments.find_one({"experiment_id": experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    results = await _evaluate_experiment_core(exp)
    promoted = None
    if exp.get("auto_winner", True) and results.get("significance_reached") and results.get("winner") and exp.get("status") == "active":
        promoted = await _promote_experiment_winner(exp, results)
        refreshed = await db.ab_experiments.find_one({"experiment_id": experiment_id}, {"_id": 0})
        if refreshed:
            results["experiment"] = refreshed
            results["winner_detected_at"] = refreshed.get("winner_detected_at")
    return {**results, "promoted": bool(promoted), "promotion_event": promoted}


@ab_testing_router.get("/winner-events")
async def get_winner_events(request: Request):
    """Get history of auto-detected winners."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    events = await db.ab_winner_events.find({}, {"_id": 0}).sort("detected_at", -1).to_list(50)
    return {"winner_events": events}


# ──────────────────── ENHANCED TEAM ANALYTICS ────────────────────
enhanced_analytics_router = APIRouter(prefix="/team-analytics-enhanced", tags=["Enhanced Team Analytics"])


@enhanced_analytics_router.get("/enhanced")
async def get_enhanced_team_analytics(request: Request):
    """Enhanced executive analytics: growth trend, heatmap, engagement scores."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Member growth over 30 days
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    growth_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$project": {"day": {"$substr": ["$created_at", 0, 10]}, "action": 1}},
        {"$group": {"_id": {"day": "$day", "action": "$action"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.day": 1}},
    ]
    growth_raw = await db.team_audit_logs.aggregate(growth_pipeline).to_list(300)
    daily_map = {}
    for g in growth_raw:
        day = g["_id"]["day"]
        if day not in daily_map:
            daily_map[day] = {"date": day, "joins": 0, "leaves": 0, "actions": 0}
        action = g["_id"].get("action", "")
        if "invited" in action or "created" in action:
            daily_map[day]["joins"] += g["count"]
        elif "removed" in action or "deleted" in action:
            daily_map[day]["leaves"] += g["count"]
        daily_map[day]["actions"] += g["count"]
    member_growth = sorted(daily_map.values(), key=lambda x: x["date"])

    # Activity heatmap (hour x day_of_week)
    heatmap_pipeline = [
        {"$project": {"hour": {"$substr": ["$created_at", 11, 2]}, "day_str": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": {"hour": "$hour"}, "count": {"$sum": 1}}},
    ]
    heatmap_raw = await db.team_audit_logs.aggregate(heatmap_pipeline).to_list(24)
    heatmap = [
        {"hour": int(h["_id"]["hour"]) if h["_id"]["hour"].isdigit() else 0, "count": h["count"]} for h in heatmap_raw
    ]

    # Team engagement scores
    teams = await db.teams.find({}, {"_id": 0, "team_id": 1, "name": 1, "members": 1, "created_at": 1}).to_list(50)
    engagement = []
    for t in teams:
        tid = t.get("team_id")
        member_count = len(t.get("members", []))
        recent_actions = await db.team_audit_logs.count_documents(
            {"team_id": tid, "created_at": {"$gte": thirty_days_ago}}
        )
        custom_role_count = await db.custom_roles.count_documents({"team_id": tid})
        # Score: weighted formula
        score = min(100, (recent_actions * 5) + (member_count * 10) + (custom_role_count * 15))
        engagement.append(
            {
                "team_id": tid,
                "name": t.get("name", "Unknown"),
                "members": member_count,
                "actions_30d": recent_actions,
                "custom_roles": custom_role_count,
                "engagement_score": score,
            }
        )
    engagement.sort(key=lambda x: x["engagement_score"], reverse=True)

    # Top active users
    active_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$group": {"_id": "$actor_id", "actions": {"$sum": 1}, "last_action": {"$max": "$created_at"}}},
        {"$sort": {"actions": -1}},
        {"$limit": 10},
    ]
    active_users_raw = await db.team_audit_logs.aggregate(active_pipeline).to_list(10)
    active_users = []
    for au in active_users_raw:
        uid = au["_id"]
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
        active_users.append(
            {
                "user_id": uid,
                "name": (u or {}).get("name", "Unknown"),
                "email": (u or {}).get("email", ""),
                "actions": au["actions"],
                "last_action": au.get("last_action"),
            }
        )

    return {
        "member_growth": member_growth,
        "activity_heatmap": heatmap,
        "team_engagement": engagement,
        "top_active_users": active_users,
    }


# ──────────────────── SSE WEBHOOK STREAM ────────────────────
from fastapi.responses import StreamingResponse
import asyncio
import json

sse_router = APIRouter(prefix="/webhook-events", tags=["Webhook SSE"])


@sse_router.get("/sse")
async def webhook_sse_stream(request: Request, integration_id: str = None, token: str = None):
    """Server-Sent Events stream for real-time webhook events."""
    # Auth via query param 'token' is handled by get_current_user/require_auth
    await require_auth(request)

    async def event_generator():
        last_id = None
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            query = {}
            if integration_id:
                query["integration_id"] = integration_id
            if last_id:
                query["created_at"] = {"$gt": last_id}

            events = await db.webhook_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(10)
            if events:
                last_id = events[0].get("created_at")
                for evt in reversed(events):
                    data = json.dumps(evt)
                    yield f"data: {data}\n\n"

            # Also send a heartbeat
            yield ": heartbeat\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
