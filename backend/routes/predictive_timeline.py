"""Predictive Hiring Timeline — AI-driven stage duration predictions.

Endpoints:
- GET /api/aris/predict-timeline/{job_id}  Predict time-to-hire for a job's pipelines
- GET /api/aris/predict-timeline/global     Global average stage durations
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import logging

from .db import db, require_auth
from .hiring_intelligence import PIPELINE_STAGES, STAGE_LABELS

router = APIRouter(prefix="/aris/predict-timeline")
logger = logging.getLogger("routes.predictive_timeline")

# Default baseline durations (hours) per stage when no historical data
BASELINE_HOURS = {
    "application_received": 1,
    "ai_screening": 2,
    "skill_validation": 4,
    "interview_readiness": 24,
    "interview_scheduling": 48,
    "interview_analysis": 6,
    "hiring_prediction": 2,
    "offer_recommendation": 72,
}


async def _compute_stage_durations():
    """Compute average duration per stage from historical pipeline data."""
    pipelines = await db.hiring_pipeline.find(
        {"stage_history": {"$exists": True, "$ne": []}},
        {"_id": 0, "stage_history": 1, "current_stage": 1, "created_at": 1, "updated_at": 1},
    ).to_list(500)

    stage_durations = {s: [] for s in PIPELINE_STAGES}

    for pipe in pipelines:
        history = pipe.get("stage_history", [])
        if not history:
            continue
        for i in range(len(history)):
            entry = history[i]
            stage = entry.get("stage", "")
            entered = entry.get("entered_at") or entry.get("timestamp", "")
            if not entered or stage not in stage_durations:
                continue
            # Duration = time until next stage (or until now if it's the current stage)
            if i + 1 < len(history):
                exited = history[i + 1].get("entered_at") or history[i + 1].get("timestamp", "")
            else:
                exited = pipe.get("updated_at", datetime.now(timezone.utc).isoformat())
            try:
                t_in = datetime.fromisoformat(entered.replace("Z", "+00:00"))
                t_out = datetime.fromisoformat(exited.replace("Z", "+00:00"))
                if t_in.tzinfo is None:
                    t_in = t_in.replace(tzinfo=timezone.utc)
                if t_out.tzinfo is None:
                    t_out = t_out.replace(tzinfo=timezone.utc)
                hours = max((t_out - t_in).total_seconds() / 3600, 0.1)
                stage_durations[stage].append(hours)
            except Exception:
                continue

    # Compute averages, fall back to baseline
    averages = {}
    for stage in PIPELINE_STAGES:
        vals = stage_durations[stage]
        if vals:
            averages[stage] = round(sum(vals) / len(vals), 1)
        else:
            averages[stage] = BASELINE_HOURS.get(stage, 24)

    return averages, len(pipelines)


def _hours_to_label(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)}min"
    if hours < 24:
        return f"{round(hours, 1)}h"
    days = hours / 24
    if days < 7:
        return f"{round(days, 1)}d"
    return f"{round(days / 7, 1)}w"


@router.get("/global")
async def global_timeline(request: Request):
    """Global average stage durations across all pipelines."""
    await require_auth(request)
    averages, sample_size = await _compute_stage_durations()

    total_hours = sum(averages.values())
    stages = []
    cumulative = 0
    for stage in PIPELINE_STAGES:
        dur = averages[stage]
        cumulative += dur
        stages.append(
            {
                "stage": stage,
                "label": STAGE_LABELS.get(stage, stage),
                "avg_hours": dur,
                "duration_label": _hours_to_label(dur),
                "cumulative_hours": round(cumulative, 1),
                "cumulative_label": _hours_to_label(cumulative),
                "pct_of_total": round(dur / max(total_hours, 1) * 100, 1),
            }
        )

    return {
        "stages": stages,
        "total_hours": round(total_hours, 1),
        "total_label": _hours_to_label(total_hours),
        "sample_size": sample_size,
        "confidence": "high" if sample_size >= 20 else "medium" if sample_size >= 5 else "low",
    }


@router.get("/{job_id}")
async def job_timeline(job_id: str, request: Request):
    """Predict timeline for a specific job's pipelines."""
    await require_auth(request)

    # Get global averages for baseline
    averages, sample_size = await _compute_stage_durations()
    total_baseline = sum(averages.values())

    # Get this job's pipelines
    pipelines = await db.hiring_pipeline.find(
        {"job_id": job_id},
        {
            "_id": 0,
            "pipeline_id": 1,
            "candidate_name": 1,
            "candidate_email": 1,
            "current_stage": 1,
            "stage_history": 1,
            "created_at": 1,
            "updated_at": 1,
            "prediction": 1,
        },
    ).to_list(100)

    now = datetime.now(timezone.utc)
    candidates = []

    for pipe in pipelines:
        current = pipe.get("current_stage", "application_received")
        current_idx = PIPELINE_STAGES.index(current) if current in PIPELINE_STAGES else 0
        history = pipe.get("stage_history", [])

        # Compute actual durations for completed stages
        actual_stages = []
        for i, entry in enumerate(history):
            stage = entry.get("stage", "")
            entered = entry.get("entered_at") or entry.get("timestamp", "")
            if not entered or stage not in PIPELINE_STAGES:
                continue
            if i + 1 < len(history):
                exited = history[i + 1].get("entered_at") or history[i + 1].get("timestamp", "")
            else:
                exited = pipe.get("updated_at", now.isoformat())
            try:
                t_in = datetime.fromisoformat(entered.replace("Z", "+00:00"))
                t_out = datetime.fromisoformat(exited.replace("Z", "+00:00"))
                if t_in.tzinfo is None:
                    t_in = t_in.replace(tzinfo=timezone.utc)
                if t_out.tzinfo is None:
                    t_out = t_out.replace(tzinfo=timezone.utc)
                hours = max((t_out - t_in).total_seconds() / 3600, 0.1)
                actual_stages.append({"stage": stage, "hours": round(hours, 1), "status": "completed"})
            except Exception:
                continue

        # Build full timeline: actual + predicted
        timeline = []
        actual_total = 0
        predicted_total = 0
        completed_set = {a["stage"] for a in actual_stages}

        for stage in PIPELINE_STAGES:
            stage_idx = PIPELINE_STAGES.index(stage)
            actual = next((a for a in actual_stages if a["stage"] == stage), None)

            if actual:
                hours = actual["hours"]
                status = "completed" if stage_idx < current_idx else "in_progress"
                actual_total += hours
            else:
                hours = averages.get(stage, 24)
                status = "in_progress" if stage == current else "predicted"
                if stage_idx <= current_idx and stage not in completed_set:
                    status = "in_progress"
                predicted_total += hours

            timeline.append(
                {
                    "stage": stage,
                    "label": STAGE_LABELS.get(stage, stage),
                    "hours": hours,
                    "duration_label": _hours_to_label(hours),
                    "status": status,
                }
            )

        # Compute ETA
        remaining_hours = sum(t["hours"] for t in timeline if t["status"] == "predicted")
        eta = (now + timedelta(hours=remaining_hours)).isoformat()

        # Created date
        created = pipe.get("created_at", now.isoformat())
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            elapsed_hours = (now - created_dt).total_seconds() / 3600
        except Exception:
            elapsed_hours = 0

        pred = pipe.get("prediction") or {}
        candidates.append(
            {
                "pipeline_id": pipe["pipeline_id"],
                "candidate_name": pipe.get("candidate_name", "Unknown"),
                "candidate_email": pipe.get("candidate_email", ""),
                "current_stage": current,
                "current_stage_label": STAGE_LABELS.get(current, current),
                "progress_pct": round((current_idx + 1) / len(PIPELINE_STAGES) * 100),
                "elapsed_hours": round(elapsed_hours, 1),
                "elapsed_label": _hours_to_label(elapsed_hours),
                "remaining_hours": round(remaining_hours, 1),
                "remaining_label": _hours_to_label(remaining_hours),
                "estimated_total_hours": round(actual_total + predicted_total, 1),
                "estimated_total_label": _hours_to_label(actual_total + predicted_total),
                "eta": eta,
                "hire_confidence": pred.get("hire_confidence"),
                "decision": pred.get("decision"),
                "timeline": timeline,
            }
        )

    # Sort by progress (most advanced first)
    candidates.sort(key=lambda c: c["progress_pct"], reverse=True)

    return {
        "job_id": job_id,
        "candidates": candidates,
        "global_avg_hours": round(total_baseline, 1),
        "global_avg_label": _hours_to_label(total_baseline),
        "sample_size": sample_size,
    }
