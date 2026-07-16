"""A/B Testing for upgrade prompts, modals, and UI elements.
Manages experiments for: upgrade_modal, usage_indicator, daily_email, pricing_page.
Includes automated winner detection via z-test for proportions and auto-rollout.
"""

import math
import uuid
import hashlib
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from routes.db import db, get_current_user, require_admin

logger = logging.getLogger("ab_prompt_testing")
admin_router = APIRouter(prefix="/admin/prompt-experiments", tags=["Prompt A/B Testing"])
public_router = APIRouter(prefix="/prompt-experiment", tags=["Prompt A/B Testing Public"])

TARGETS = ["upgrade_modal", "usage_indicator", "daily_email", "pricing_page"]
DEFAULT_MIN_SAMPLE = 100
DEFAULT_CONFIDENCE = 95.0

# z-scores for common confidence levels
Z_TABLE = {90.0: 1.645, 95.0: 1.960, 99.0: 2.576}


# ── Models ──

class VariantInput(BaseModel):
    id: str = ""
    name: str
    config: dict = Field(default_factory=dict)
    weight: float = 50.0


class CreateExperiment(BaseModel):
    name: str
    description: str = ""
    target: str
    variants: list[VariantInput]
    audience: str = "all"
    traffic_pct: float = 100.0
    min_sample_size: int = DEFAULT_MIN_SAMPLE
    confidence_threshold: float = DEFAULT_CONFIDENCE
    auto_rollout: bool = False
    scheduled_rollout_at: Optional[str] = None  # ISO datetime for scheduled rollout
    traffic_allocation_mode: str = "fixed_split"  # fixed_split | multi_armed_bandit
    exploration_rate: float = 0.15


class UpdateExperiment(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    variants: Optional[list[VariantInput]] = None
    traffic_pct: Optional[float] = None
    audience: Optional[str] = None
    min_sample_size: Optional[int] = None
    confidence_threshold: Optional[float] = None
    auto_rollout: Optional[bool] = None
    scheduled_rollout_at: Optional[str] = None
    traffic_allocation_mode: Optional[str] = None
    exploration_rate: Optional[float] = None


class TrackEventInput(BaseModel):
    experiment_id: str
    variant_id: str
    event: str  # impression, click, upgrade, dismiss
    metadata: dict = Field(default_factory=dict)


class ManualEvaluateInput(BaseModel):
    experiment_id: str


class RolloutInput(BaseModel):
    experiment_id: str


# ── Helpers ──

def _deterministic_variant(user_id: str, experiment_id: str, variants: list[dict]) -> dict:
    """Deterministic variant assignment based on user+experiment hash."""
    seed = hashlib.md5(f"{user_id}:{experiment_id}".encode()).hexdigest()
    hash_val = int(seed[:8], 16) / 0xFFFFFFFF
    total_weight = sum(v.get("weight", 50) for v in variants)
    cumulative = 0.0
    for v in variants:
        cumulative += v.get("weight", 50) / total_weight
        if hash_val <= cumulative:
            return v
    return variants[-1]


def _conversion_rate(impressions: int, conversions: int) -> float:
    return round(conversions / max(impressions, 1) * 100, 2)


def _normalize_traffic_allocation_mode(mode: Optional[str]) -> str:
    normalized = str(mode or "fixed_split").strip().lower()
    if normalized in {"bandit", "multi-armed-bandit", "multi_armed_bandit", "mab"}:
        return "multi_armed_bandit"
    return "fixed_split"


def _sanitize_exploration_rate(value: Optional[float]) -> float:
    try:
        return round(max(0.0, min(0.5, float(value if value is not None else 0.15))), 3)
    except Exception:
        return 0.15


async def _fetch_variant_event_stats(experiment_id: str) -> dict:
    pipeline = [
        {"$match": {"experiment_id": experiment_id}},
        {"$group": {
            "_id": {"variant_id": "$variant_id", "event": "$event"},
            "count": {"$sum": 1},
        }},
    ]
    agg = await db.prompt_experiment_events.aggregate(pipeline).to_list(500)
    stats: dict = {}
    for row in agg:
        vid = row["_id"]["variant_id"]
        evt = row["_id"]["event"]
        if vid not in stats:
            stats[vid] = {"impressions": 0, "clicks": 0, "upgrades": 0, "dismisses": 0}
        if evt == "impression":
            stats[vid]["impressions"] = row["count"]
        elif evt == "click":
            stats[vid]["clicks"] = row["count"]
        elif evt == "upgrade":
            stats[vid]["upgrades"] = row["count"]
        elif evt == "dismiss":
            stats[vid]["dismisses"] = row["count"]
    return stats


def _build_bandit_scores(variants: list[dict], stats: dict, user_id: str, experiment_id: str) -> list[dict]:
    scored: list[dict] = []
    for variant in variants:
        variant_id = variant.get("id")
        vstats = stats.get(variant_id, {})
        impressions = int(vstats.get("impressions", 0))
        clicks = int(vstats.get("clicks", 0))
        upgrades = int(vstats.get("upgrades", 0))
        weighted_conversions = float(upgrades) + (float(clicks) * 0.35)
        alpha = 1.0 + max(weighted_conversions, 0.0)
        beta = 1.0 + max(float(impressions) - weighted_conversions, 0.0)
        sample_seed = hashlib.md5(
            f"{user_id}:{experiment_id}:{variant_id}:{impressions}:{clicks}:{upgrades}".encode()
        ).hexdigest()
        seeded_rng = random.Random(int(sample_seed[:12], 16))
        thompson_draw = seeded_rng.betavariate(alpha, beta)
        scored.append({
            "variant_id": variant_id,
            "variant_name": variant.get("name", variant_id),
            "impressions": impressions,
            "clicks": clicks,
            "upgrades": upgrades,
            "weighted_conversions": round(weighted_conversions, 3),
            "alpha": round(alpha, 3),
            "beta": round(beta, 3),
            "thompson_draw": round(float(thompson_draw), 6),
        })
    return scored


async def _assign_multi_armed_bandit_variant(user_id: str, exp: dict) -> tuple[dict, dict]:
    variants = exp.get("variants", [])
    if not variants:
        return {}, {"reason": "no_variants"}

    stats = await _fetch_variant_event_stats(exp.get("experiment_id"))
    exploration_rate = _sanitize_exploration_rate(exp.get("exploration_rate", 0.15))
    warmup_floor = 15
    sampled_counts = [int((stats.get(v.get("id"), {}) or {}).get("impressions", 0)) for v in variants]
    min_impressions = min(sampled_counts) if sampled_counts else 0

    if min_impressions < warmup_floor:
        chosen = _deterministic_variant(user_id, exp.get("experiment_id", ""), variants)
        return chosen, {
            "mode": "multi_armed_bandit",
            "strategy": "warmup_fixed_split",
            "exploration_rate": exploration_rate,
            "warmup_floor": warmup_floor,
            "min_variant_impressions": min_impressions,
        }

    gate_seed = hashlib.md5(f"{user_id}:bandit:gate:{exp.get('experiment_id', '')}".encode()).hexdigest()
    gate_draw = int(gate_seed[:8], 16) / 0xFFFFFFFF
    if gate_draw < exploration_rate:
        explore_seed = hashlib.md5(f"{user_id}:bandit:explore:{exp.get('experiment_id', '')}".encode()).hexdigest()
        explore_rng = random.Random(int(explore_seed[:12], 16))
        chosen = variants[explore_rng.randrange(len(variants))]
        return chosen, {
            "mode": "multi_armed_bandit",
            "strategy": "exploration",
            "exploration_rate": exploration_rate,
            "warmup_floor": warmup_floor,
            "gate_draw": round(gate_draw, 6),
        }

    scores = _build_bandit_scores(variants, stats, user_id, exp.get("experiment_id", ""))
    if not scores:
        chosen = _deterministic_variant(user_id, exp.get("experiment_id", ""), variants)
        return chosen, {
            "mode": "multi_armed_bandit",
            "strategy": "fallback_fixed_split",
            "exploration_rate": exploration_rate,
            "warmup_floor": warmup_floor,
        }
    winner = max(scores, key=lambda row: row.get("thompson_draw", 0.0))
    chosen = next((v for v in variants if v.get("id") == winner.get("variant_id")), variants[0])
    return chosen, {
        "mode": "multi_armed_bandit",
        "strategy": "thompson_sampling",
        "exploration_rate": exploration_rate,
        "warmup_floor": warmup_floor,
        "winner": winner,
        "scoreboard": sorted(scores, key=lambda row: row.get("thompson_draw", 0.0), reverse=True),
    }


def _z_test_two_proportions(n1: int, c1: int, n2: int, c2: int) -> tuple[float, float]:
    """Two-proportion z-test. Returns (z_score, confidence_pct).
    n1/n2 = sample sizes, c1/c2 = conversions (clicks or upgrades).
    """
    if n1 < 1 or n2 < 1:
        return 0.0, 0.0
    p1 = c1 / n1
    p2 = c2 / n2
    p_pool = (c1 + c2) / (n1 + n2)
    if p_pool == 0 or p_pool == 1:
        return 0.0, 0.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 0.0
    z = abs(p1 - p2) / se
    # Approximate confidence from z-score using error function
    confidence = _z_to_confidence(z)
    return round(z, 4), round(confidence, 2)


def _z_to_confidence(z: float) -> float:
    """Convert z-score to confidence % using the complementary error function."""
    # P(|Z| > z) = 2 * (1 - Phi(z)), confidence = 1 - p_value
    # Using math.erfc for the normal CDF approximation
    p_value = math.erfc(z / math.sqrt(2))
    return max(0, min(100, (1 - p_value) * 100))


async def _evaluate_winner(experiment_id: str) -> dict | None:
    """Check if an experiment has a statistically significant winner.
    Returns winner info dict or None if no winner yet.
    """
    exp = await db.prompt_experiments.find_one(
        {"experiment_id": experiment_id}, {"_id": 0}
    )
    if not exp or exp.get("status") != "running":
        return None
    if exp.get("winner"):
        return exp["winner"]

    variants = exp.get("variants", [])
    if len(variants) < 2:
        return None

    min_sample = exp.get("min_sample_size", DEFAULT_MIN_SAMPLE)
    threshold = exp.get("confidence_threshold", DEFAULT_CONFIDENCE)

    variant_stats = await _fetch_variant_event_stats(experiment_id)

    # Need at least 2 variants with enough samples
    valid = {vid: s for vid, s in variant_stats.items() if s["impressions"] >= min_sample}
    if len(valid) < 2:
        return None

    # Compare all pairs, find the best performer
    vids = list(valid.keys())
    best_winner = None
    best_confidence = 0.0

    for i in range(len(vids)):
        for j in range(i + 1, len(vids)):
            v1, v2 = vids[i], vids[j]
            s1, s2 = valid[v1], valid[v2]

            # Use clicks as primary conversion metric
            z_score, confidence = _z_test_two_proportions(
                s1["impressions"], s1["clicks"],
                s2["impressions"], s2["clicks"],
            )

            if confidence >= threshold and confidence > best_confidence:
                # Determine which variant wins
                cr1 = s1["clicks"] / max(s1["impressions"], 1)
                cr2 = s2["clicks"] / max(s2["impressions"], 1)
                winner_vid = v1 if cr1 > cr2 else v2
                loser_vid = v2 if cr1 > cr2 else v1
                winner_stats = valid[winner_vid]
                loser_stats = valid[loser_vid]

                best_winner = {
                    "variant_id": winner_vid,
                    "variant_name": next(
                        (v["name"] for v in variants if v["id"] == winner_vid), winner_vid
                    ),
                    "confidence_pct": confidence,
                    "z_score": z_score,
                    "winner_cr": round(winner_stats["clicks"] / max(winner_stats["impressions"], 1) * 100, 2),
                    "loser_id": loser_vid,
                    "loser_cr": round(loser_stats["clicks"] / max(loser_stats["impressions"], 1) * 100, 2),
                    "sample_sizes": {vid: valid[vid]["impressions"] for vid in vids},
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "metric": "click_through_rate",
                }
                best_confidence = confidence

    if best_winner:
        # Auto-pause and record winner
        new_status = "winner_detected"
        await db.prompt_experiments.update_one(
            {"experiment_id": experiment_id},
            {"$set": {
                "winner": best_winner,
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(
            f"[AB] Winner detected for {experiment_id}: "
            f"variant={best_winner['variant_id']} "
            f"confidence={best_winner['confidence_pct']}%"
        )

        # Auto-rollout if enabled
        if exp.get("auto_rollout"):
            scheduled = exp.get("scheduled_rollout_at")
            if scheduled:
                # Scheduled rollout: mark as pending_rollout, don't roll out yet
                await db.prompt_experiments.update_one(
                    {"experiment_id": experiment_id},
                    {"$set": {
                        "status": "pending_rollout",
                        "scheduled_rollout_at": scheduled,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                logger.info(f"[AB] Winner found for {experiment_id}, rollout scheduled at {scheduled}")
            else:
                await _perform_rollout(experiment_id, best_winner, exp)

        return best_winner

    return None


async def _perform_rollout(experiment_id: str, winner: dict, exp: dict):
    """Roll out the winning variant as the default for the target surface."""
    target = exp.get("target")
    winning_variant = next(
        (v for v in exp.get("variants", []) if v["id"] == winner["variant_id"]), None
    )
    if not winning_variant or not target:
        return

    rollout_doc = {
        "target": target,
        "experiment_id": experiment_id,
        "variant_id": winner["variant_id"],
        "variant_name": winner["variant_name"],
        "config": winning_variant.get("config", {}),
        "confidence_pct": winner["confidence_pct"],
        "rolled_out_at": datetime.now(timezone.utc).isoformat(),
        "rolled_out_by": "auto",
    }

    await db.prompt_defaults.update_one(
        {"target": target},
        {"$set": rollout_doc},
        upsert=True,
    )
    await db.prompt_experiments.update_one(
        {"experiment_id": experiment_id},
        {"$set": {"status": "rolled_out", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    logger.info(f"[AB] Auto-rollout for {target}: variant={winner['variant_id']} from experiment {experiment_id}")


# ── Admin CRUD ──

@admin_router.post("")
async def create_experiment(body: CreateExperiment, request: Request):
    user = await require_admin(request)
    if body.target not in TARGETS:
        raise HTTPException(400, f"Invalid target. Must be one of: {TARGETS}")

    exp_id = f"pexp_{uuid.uuid4().hex[:10]}"
    variants = []
    for i, v in enumerate(body.variants):
        variants.append({
            "id": v.id or f"var_{chr(65 + i)}",
            "name": v.name,
            "config": v.config,
            "weight": v.weight,
        })

    doc = {
        "experiment_id": exp_id,
        "name": body.name,
        "description": body.description,
        "target": body.target,
        "variants": variants,
        "audience": body.audience,
        "traffic_pct": body.traffic_pct,
        "traffic_allocation_mode": _normalize_traffic_allocation_mode(body.traffic_allocation_mode),
        "exploration_rate": _sanitize_exploration_rate(body.exploration_rate),
        "min_sample_size": body.min_sample_size,
        "confidence_threshold": body.confidence_threshold,
        "auto_rollout": body.auto_rollout,
        "scheduled_rollout_at": body.scheduled_rollout_at,
        "status": "draft",
        "winner": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.email,
    }
    await db.prompt_experiments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@admin_router.get("")
async def list_experiments(request: Request, status: Optional[str] = None):
    await require_admin(request)
    query = {}
    if status:
        query["status"] = status
    experiments = await db.prompt_experiments.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    # Attach summary metrics per experiment
    for exp in experiments:
        eid = exp["experiment_id"]
        pipeline = [
            {"$match": {"experiment_id": eid}},
            {"$group": {
                "_id": {"variant_id": "$variant_id", "event": "$event"},
                "count": {"$sum": 1},
                "unique_users": {"$addToSet": "$user_id"},
            }},
        ]
        agg = await db.prompt_experiment_events.aggregate(pipeline).to_list(500)

        metrics = {}
        for row in agg:
            vid = row["_id"]["variant_id"]
            evt = row["_id"]["event"]
            if vid not in metrics:
                metrics[vid] = {"impressions": 0, "clicks": 0, "upgrades": 0, "dismisses": 0}
            key = f"{evt}s" if not evt.endswith("s") else evt
            if key in metrics[vid]:
                metrics[vid][key] = row["count"]
        exp["metrics"] = metrics

    return {"experiments": experiments}


@admin_router.get("/{experiment_id}")
async def get_experiment(experiment_id: str, request: Request):
    await require_admin(request)
    exp = await db.prompt_experiments.find_one({"experiment_id": experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Experiment not found")

    # Detailed per-variant metrics
    pipeline = [
        {"$match": {"experiment_id": experiment_id}},
        {"$group": {
            "_id": {"variant_id": "$variant_id", "event": "$event"},
            "count": {"$sum": 1},
            "unique_users": {"$addToSet": "$user_id"},
        }},
    ]
    agg = await db.prompt_experiment_events.aggregate(pipeline).to_list(500)

    variant_metrics = {}
    for row in agg:
        vid = row["_id"]["variant_id"]
        evt = row["_id"]["event"]
        if vid not in variant_metrics:
            variant_metrics[vid] = {}
        variant_metrics[vid][evt] = {"total": row["count"], "unique": len(row["unique_users"])}
    exp["variant_metrics"] = variant_metrics

    # Daily trend last 14d
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    daily = await db.prompt_experiment_events.aggregate([
        {"$match": {"experiment_id": experiment_id, "created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"date": {"$substr": ["$created_at", 0, 10]}, "variant_id": "$variant_id", "event": "$event"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.date": 1}},
    ]).to_list(1000)
    exp["daily_trend"] = [
        {"date": d["_id"]["date"], "variant_id": d["_id"]["variant_id"], "event": d["_id"]["event"], "count": d["count"]}
        for d in daily
    ]

    if _normalize_traffic_allocation_mode(exp.get("traffic_allocation_mode")) == "multi_armed_bandit":
        stats = await _fetch_variant_event_stats(experiment_id)
        scores = _build_bandit_scores(exp.get("variants", []), stats, "system_preview", experiment_id)
        exp["allocation_insights"] = {
            "mode": "multi_armed_bandit",
            "exploration_rate": _sanitize_exploration_rate(exp.get("exploration_rate", 0.15)),
            "scoreboard": sorted(scores, key=lambda row: row.get("thompson_draw", 0.0), reverse=True),
        }
    else:
        exp["allocation_insights"] = {
            "mode": "fixed_split",
            "exploration_rate": _sanitize_exploration_rate(exp.get("exploration_rate", 0.15)),
            "scoreboard": [],
        }

    return exp


@admin_router.patch("/{experiment_id}")
async def update_experiment(experiment_id: str, body: UpdateExperiment, request: Request):
    await require_admin(request)

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ["name", "description", "status", "traffic_pct", "audience",
                   "min_sample_size", "confidence_threshold", "auto_rollout",
                   "scheduled_rollout_at"]:
        val = getattr(body, field, None)
        if val is not None:
            update[field] = val
    if body.variants is not None:
        update["variants"] = [v.dict() for v in body.variants]
    if body.traffic_allocation_mode is not None:
        update["traffic_allocation_mode"] = _normalize_traffic_allocation_mode(body.traffic_allocation_mode)
    if body.exploration_rate is not None:
        update["exploration_rate"] = _sanitize_exploration_rate(body.exploration_rate)
    if body.status and body.status in ("running", "draft"):
        update["winner"] = None

    result = await db.prompt_experiments.update_one({"experiment_id": experiment_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Experiment not found")
    return {"updated": True, "experiment_id": experiment_id}


@admin_router.delete("/{experiment_id}")
async def delete_experiment(experiment_id: str, request: Request):
    await require_admin(request)
    result = await db.prompt_experiments.delete_one({"experiment_id": experiment_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Experiment not found")
    await db.prompt_experiment_events.delete_many({"experiment_id": experiment_id})
    return {"deleted": True}


# ── Public: variant assignment + event tracking ──

@public_router.get("/variant")
async def get_user_variant(target: str, request: Request):
    """Get the active variant for the current user for a given target surface."""
    user = await get_current_user(request)
    if not user:
        return {"variant": None, "experiment_id": None}

    # Check for rolled-out default first
    default = await db.prompt_defaults.find_one({"target": target}, {"_id": 0})
    if default:
        return {
            "experiment_id": default.get("experiment_id"),
            "variant_id": default.get("variant_id"),
            "variant_name": default.get("variant_name"),
            "config": default.get("config", {}),
            "is_default": True,
        }

    plan = getattr(user, "subscription_plan", "free") or "free"
    experiments = await db.prompt_experiments.find(
        {"target": target, "status": "running"}, {"_id": 0}
    ).to_list(10)

    for exp in experiments:
        audience = exp.get("audience", "all")
        if audience == "free" and plan != "free":
            continue
        if audience == "basic" and plan != "basic":
            continue
        if audience == "free_basic" and plan not in ("free", "basic"):
            continue

        # Traffic gate
        traffic = exp.get("traffic_pct", 100)
        seed = hashlib.md5(f"{user.user_id}:gate:{exp['experiment_id']}".encode()).hexdigest()
        if (int(seed[:8], 16) / 0xFFFFFFFF * 100) > traffic:
            continue

        allocation_mode = _normalize_traffic_allocation_mode(exp.get("traffic_allocation_mode"))
        if allocation_mode == "multi_armed_bandit":
            variant, allocation_meta = await _assign_multi_armed_bandit_variant(user.user_id, exp)
        else:
            variant = _deterministic_variant(user.user_id, exp["experiment_id"], exp.get("variants", []))
            allocation_meta = {
                "mode": "fixed_split",
                "strategy": "deterministic_weighted",
                "exploration_rate": _sanitize_exploration_rate(exp.get("exploration_rate", 0.15)),
            }
        if not variant or not variant.get("id"):
            continue
        return {
            "experiment_id": exp["experiment_id"],
            "variant_id": variant["id"],
            "variant_name": variant["name"],
            "config": variant.get("config", {}),
            "allocation_mode": allocation_mode,
            "allocation_meta": allocation_meta,
        }

    return {"variant": None, "experiment_id": None}


@public_router.post("/track")
async def track_event(body: TrackEventInput, request: Request):
    """Track an event for a prompt experiment."""
    user = await get_current_user(request)
    user_id = user.user_id if user else "anonymous"

    await db.prompt_experiment_events.insert_one({
        "event_id": f"pevt_{uuid.uuid4().hex[:10]}",
        "experiment_id": body.experiment_id,
        "variant_id": body.variant_id,
        "user_id": user_id,
        "event": body.event,
        "metadata": body.metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Auto-evaluate for winner after each impression or click event
    winner = None
    if body.event in ("impression", "click"):
        try:
            winner = await _evaluate_winner(body.experiment_id)
        except Exception as e:
            logger.warning(f"[AB] Winner eval failed for {body.experiment_id}: {e}")

    return {"tracked": True, "winner_detected": winner is not None}


class EvaluateInput(BaseModel):
    experiment_id: str


@public_router.post("/evaluate")
async def manual_evaluate(body: ManualEvaluateInput, request: Request):
    """Manually trigger winner evaluation for an experiment (admin only)."""
    await require_admin(request)
    exp = await db.prompt_experiments.find_one({"experiment_id": body.experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp.get("winner"):
        return {"already_detected": True, "winner": exp["winner"], "experiment_id": body.experiment_id}
    original_status = exp.get("status")
    if original_status != "running":
        await db.prompt_experiments.update_one(
            {"experiment_id": body.experiment_id}, {"$set": {"status": "running"}}
        )
    winner = await _evaluate_winner(body.experiment_id)
    if not winner and original_status != "running":
        await db.prompt_experiments.update_one(
            {"experiment_id": body.experiment_id}, {"$set": {"status": original_status}}
        )
    if winner:
        return {"winner_detected": True, "winner": winner, "experiment_id": body.experiment_id}
    pipeline = [
        {"$match": {"experiment_id": body.experiment_id}},
        {"$group": {"_id": {"variant_id": "$variant_id", "event": "$event"}, "count": {"$sum": 1}}},
    ]
    agg = await db.prompt_experiment_events.aggregate(pipeline).to_list(500)
    stats = {}
    for row in agg:
        vid = row["_id"]["variant_id"]
        if vid not in stats:
            stats[vid] = {}
        stats[vid][row["_id"]["event"]] = row["count"]
    return {
        "winner_detected": False, "experiment_id": body.experiment_id,
        "min_sample_size": exp.get("min_sample_size", DEFAULT_MIN_SAMPLE),
        "confidence_threshold": exp.get("confidence_threshold", DEFAULT_CONFIDENCE),
        "current_stats": stats,
        "message": "Not enough data or no significant difference found yet.",
    }



@public_router.post("/rollout")
async def manual_rollout(body: RolloutInput, request: Request):
    """Manually roll out the winning variant as the default (admin only)."""
    await require_admin(request)
    exp = await db.prompt_experiments.find_one({"experiment_id": body.experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if not exp.get("winner"):
        raise HTTPException(400, "No winner detected for this experiment. Evaluate first.")
    await _perform_rollout(body.experiment_id, exp["winner"], exp)
    return {
        "rolled_out": True,
        "experiment_id": body.experiment_id,
        "target": exp["target"],
        "variant_id": exp["winner"]["variant_id"],
    }


@public_router.post("/revert-rollout")
async def revert_rollout(body: RolloutInput, request: Request):
    """Revert a rolled-out default, restoring experiment-based assignment (admin only)."""
    await require_admin(request)
    exp = await db.prompt_experiments.find_one({"experiment_id": body.experiment_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Experiment not found")
    target = exp.get("target")
    result = await db.prompt_defaults.delete_one({"target": target, "experiment_id": body.experiment_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "No active rollout found for this experiment's target")
    # Move experiment back to winner_detected
    await db.prompt_experiments.update_one(
        {"experiment_id": body.experiment_id},
        {"$set": {"status": "winner_detected", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    logger.info(f"[AB] Rollout reverted for {target}: experiment {body.experiment_id}")
    return {"reverted": True, "experiment_id": body.experiment_id, "target": target}


@public_router.get("/defaults")
async def list_defaults(request: Request):
    """List all active rolled-out defaults (admin only)."""
    await require_admin(request)
    defaults = await db.prompt_defaults.find({}, {"_id": 0}).to_list(50)
    return {"defaults": defaults}


# ── Scheduled Rollout ──

@admin_router.post("/execute-scheduled-rollout/{experiment_id}")
async def execute_scheduled_rollout(experiment_id: str, request: Request):
    """Manually trigger a scheduled rollout immediately (admin only)."""
    await require_admin(request)
    exp = await db.prompt_experiments.find_one(
        {"experiment_id": experiment_id}, {"_id": 0}
    )
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp.get("status") != "pending_rollout":
        raise HTTPException(400, f"Experiment is not pending rollout (status={exp.get('status')})")

    winner = exp.get("winner")
    if not winner or not isinstance(winner, dict):
        raise HTTPException(400, "No winner detected for this experiment")

    await _perform_rollout(experiment_id, winner, exp)
    return {"rolled_out": True, "experiment_id": experiment_id, "winner": winner}


async def check_scheduled_rollouts():
    """Background task: execute rollouts whose scheduled time has passed."""
    now = datetime.now(timezone.utc).isoformat()
    pending = await db.prompt_experiments.find(
        {"status": "pending_rollout", "scheduled_rollout_at": {"$lte": now}},
        {"_id": 0},
    ).to_list(50)

    for exp in pending:
        experiment_id = exp["experiment_id"]
        winner = exp.get("winner")
        if not winner or not isinstance(winner, dict):
            continue
        try:
            await _perform_rollout(experiment_id, winner, exp)
            logger.info(f"[AB-SCHEDULED] Executed scheduled rollout for {experiment_id}")
        except Exception as e:
            logger.error(f"[AB-SCHEDULED] Failed rollout for {experiment_id}: {e}")

    return len(pending)
