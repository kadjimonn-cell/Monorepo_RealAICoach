"""Self-Learning AI — Outcome tracking, feedback loops, prediction calibration.

Tracks hiring outcomes, measures AI prediction accuracy, and auto-adjusts
matching weights based on historical patterns.

Endpoints:
- POST /api/ai-learning/record-outcome          Record actual hiring outcome
- GET  /api/ai-learning/accuracy                 AI prediction accuracy dashboard
- GET  /api/ai-learning/calibration              Prediction calibration analysis
- POST /api/ai-learning/recalibrate              Trigger recalibration of AI weights
- GET  /api/ai-learning/pipeline/{id}/feedback   Get learning feedback for a pipeline
- GET  /api/ai-learning/insights                 AI-generated learning insights
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import os
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, require_admin

router = APIRouter(prefix="/ai-learning")
logger = logging.getLogger("routes.ai_learning")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


@router.post("/record-outcome")
async def record_outcome(request: Request):
    """Record the actual hiring outcome for a pipeline (hired/rejected/withdrew)."""
    user = await require_auth(request)
    body = await request.json()

    pipeline_id = body.get("pipeline_id", "")
    outcome = body.get("outcome", "")  # hired | rejected | withdrew | no_show
    performance_rating = body.get("performance_rating")  # 1-10 (optional, post-hire)
    retention_months = body.get("retention_months")  # how long they stayed (optional)
    notes = body.get("notes", "")

    if not pipeline_id or not outcome:
        raise HTTPException(status_code=400, detail="pipeline_id and outcome required")
    if outcome not in ("hired", "rejected", "withdrew", "no_show"):
        raise HTTPException(status_code=400, detail="outcome must be: hired, rejected, withdrew, no_show")

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    prediction = pipe.get("prediction") or {}
    ai_decision = prediction.get("decision", "unknown")
    ai_confidence = prediction.get("hire_confidence", 0)

    # Determine if AI was correct
    ai_correct = None
    if outcome == "hired" and ai_decision in ("strong_hire", "hire"):
        ai_correct = True
    elif outcome == "rejected" and ai_decision in ("pass", "no_hire"):
        ai_correct = True
    elif outcome == "hired" and ai_decision in ("pass", "no_hire"):
        ai_correct = False
    elif outcome == "rejected" and ai_decision in ("strong_hire", "hire"):
        ai_correct = False
    # "maybe", "withdrew", "no_show" are neutral

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "outcome_id": f"out_{uuid.uuid4().hex[:10]}",
        "pipeline_id": pipeline_id,
        "candidate_id": pipe.get("candidate_id", ""),
        "employer_id": pipe.get("employer_id", ""),
        "job_id": pipe.get("job_id", ""),
        "job_title": pipe.get("job_title", ""),
        "outcome": outcome,
        "ai_decision": ai_decision,
        "ai_confidence": ai_confidence,
        "ai_correct": ai_correct,
        "performance_rating": performance_rating,
        "retention_months": retention_months,
        "notes": notes,
        "recorded_by": user.user_id,
        "recorded_at": now,
        "prediction_snapshot": prediction,
        "ai_scores_snapshot": pipe.get("ai_scores", {}),
    }

    await db.ai_outcomes.insert_one({**record})

    # Update pipeline with outcome
    await db.hiring_pipeline.update_one(
        {"pipeline_id": pipeline_id}, {"$set": {"outcome": outcome, "outcome_recorded_at": now, "updated_at": now}}
    )

    return {"success": True, "outcome": record}


@router.get("/accuracy")
async def ai_accuracy_dashboard(request: Request):
    """AI prediction accuracy metrics and trends."""
    await require_admin(request)

    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(500)
    if not outcomes:
        return {
            "total_outcomes": 0,
            "accuracy": None,
            "message": "No outcomes recorded yet. Record hiring outcomes to start tracking AI accuracy.",
            "by_decision": {},
            "confidence_calibration": [],
            "trends": [],
        }

    total = len(outcomes)
    correct = sum(1 for o in outcomes if o.get("ai_correct") is True)
    incorrect = sum(1 for o in outcomes if o.get("ai_correct") is False)
    neutral = total - correct - incorrect

    # Accuracy by AI decision
    by_decision = {}
    for o in outcomes:
        dec = o.get("ai_decision", "unknown")
        if dec not in by_decision:
            by_decision[dec] = {"total": 0, "correct": 0, "incorrect": 0}
        by_decision[dec]["total"] += 1
        if o.get("ai_correct") is True:
            by_decision[dec]["correct"] += 1
        elif o.get("ai_correct") is False:
            by_decision[dec]["incorrect"] += 1

    for dec, stats in by_decision.items():
        evaluated = stats["correct"] + stats["incorrect"]
        stats["accuracy"] = round(stats["correct"] / evaluated * 100, 1) if evaluated > 0 else None

    # Confidence calibration buckets
    buckets = {"0-25": [], "26-50": [], "51-75": [], "76-100": []}
    for o in outcomes:
        conf = o.get("ai_confidence", 50)
        if conf <= 25:
            buckets["0-25"].append(o)
        elif conf <= 50:
            buckets["26-50"].append(o)
        elif conf <= 75:
            buckets["51-75"].append(o)
        else:
            buckets["76-100"].append(o)

    calibration = []
    for bucket, items in buckets.items():
        if items:
            positive = sum(1 for i in items if i.get("outcome") == "hired")
            calibration.append(
                {
                    "confidence_range": bucket,
                    "total": len(items),
                    "actual_hire_rate": round(positive / len(items) * 100, 1),
                    "expected_midpoint": int(bucket.split("-")[0]) + 12,
                }
            )

    # Outcome distribution
    outcome_dist = {}
    for o in outcomes:
        oc = o.get("outcome", "unknown")
        outcome_dist[oc] = outcome_dist.get(oc, 0) + 1

    # Performance ratings of hired candidates
    perf_ratings = [o.get("performance_rating") for o in outcomes if o.get("performance_rating") is not None]
    avg_perf = round(sum(perf_ratings) / len(perf_ratings), 1) if perf_ratings else None

    # Retention data
    retention_data = [o.get("retention_months") for o in outcomes if o.get("retention_months") is not None]
    avg_retention = round(sum(retention_data) / len(retention_data), 1) if retention_data else None

    evaluated = correct + incorrect
    accuracy = round(correct / evaluated * 100, 1) if evaluated > 0 else None

    return {
        "total_outcomes": total,
        "evaluated": evaluated,
        "accuracy": accuracy,
        "correct": correct,
        "incorrect": incorrect,
        "neutral": neutral,
        "by_decision": by_decision,
        "confidence_calibration": calibration,
        "outcome_distribution": outcome_dist,
        "performance": {
            "avg_rating": avg_perf,
            "total_rated": len(perf_ratings),
        },
        "retention": {
            "avg_months": avg_retention,
            "total_tracked": len(retention_data),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/calibration")
async def calibration_analysis(request: Request):
    """Detailed prediction calibration — are confident predictions more accurate?"""
    await require_admin(request)

    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(500)
    if not outcomes:
        return {"calibration_score": None, "message": "No outcomes to calibrate", "buckets": []}

    # Fine-grained calibration (10% buckets)
    buckets = {}
    for o in outcomes:
        conf = o.get("ai_confidence", 50)
        bucket_key = f"{(conf // 10) * 10}-{(conf // 10) * 10 + 9}"
        if bucket_key not in buckets:
            buckets[bucket_key] = {"predictions": 0, "correct": 0, "avg_confidence": 0}
        buckets[bucket_key]["predictions"] += 1
        if o.get("ai_correct") is True:
            buckets[bucket_key]["correct"] += 1
        buckets[bucket_key]["avg_confidence"] += conf

    result_buckets = []
    total_calibration_error = 0
    n_buckets = 0
    for key, data in sorted(buckets.items()):
        if data["predictions"] > 0:
            avg_conf = data["avg_confidence"] / data["predictions"]
            actual_accuracy = data["correct"] / data["predictions"] * 100
            calibration_error = abs(avg_conf - actual_accuracy)
            total_calibration_error += calibration_error
            n_buckets += 1
            result_buckets.append(
                {
                    "range": key,
                    "predictions": data["predictions"],
                    "correct": data["correct"],
                    "avg_confidence": round(avg_conf, 1),
                    "actual_accuracy": round(actual_accuracy, 1),
                    "calibration_error": round(calibration_error, 1),
                    "status": "well_calibrated"
                    if calibration_error < 15
                    else "needs_adjustment"
                    if calibration_error < 30
                    else "poorly_calibrated",
                }
            )

    avg_error = round(total_calibration_error / n_buckets, 1) if n_buckets > 0 else None
    score = max(0, round(100 - (avg_error or 0))) if avg_error is not None else None

    return {
        "calibration_score": score,
        "avg_calibration_error": avg_error,
        "health": "excellent"
        if (score or 0) >= 85
        else "good"
        if (score or 0) >= 70
        else "needs_attention"
        if (score or 0) >= 50
        else "critical",
        "buckets": result_buckets,
        "total_outcomes": len(outcomes),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/recalibrate")
async def recalibrate(request: Request):
    """Trigger AI recalibration based on collected outcomes."""
    user = await require_admin(request)

    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(500)
    if len(outcomes) < 5:
        raise HTTPException(status_code=400, detail="Need at least 5 recorded outcomes to recalibrate")

    # Analyze patterns
    stage_accuracy = {}
    for o in outcomes:
        scores = o.get("ai_scores_snapshot", {})
        was_hired = o.get("outcome") == "hired"
        for stage, score_data in scores.items():
            if stage not in stage_accuracy:
                stage_accuracy[stage] = {"total": 0, "correlates_with_hire": 0}
            stage_accuracy[stage]["total"] += 1
            if isinstance(score_data, dict):
                passed = score_data.get("pass", False)
                if (passed and was_hired) or (not passed and not was_hired):
                    stage_accuracy[stage]["correlates_with_hire"] += 1

    # Compute weights
    weights = {}
    for stage, data in stage_accuracy.items():
        if data["total"] >= 3:
            weights[stage] = round(data["correlates_with_hire"] / data["total"], 3)
        else:
            weights[stage] = 0.5  # default

    now = datetime.now(timezone.utc).isoformat()
    calibration_record = {
        "calibration_id": f"cal_{uuid.uuid4().hex[:10]}",
        "stage_weights": weights,
        "stage_accuracy": stage_accuracy,
        "total_outcomes_used": len(outcomes),
        "calibrated_by": user.user_id,
        "calibrated_at": now,
    }

    await db.ai_calibrations.insert_one({**calibration_record})

    return {
        "success": True,
        "calibration": {
            "calibration_id": calibration_record["calibration_id"],
            "stage_weights": weights,
            "outcomes_used": len(outcomes),
            "calibrated_at": now,
        },
    }


@router.get("/pipeline/{pipeline_id}/feedback")
async def pipeline_feedback(pipeline_id: str, request: Request):
    """Get learning feedback for a specific pipeline — was AI right?"""
    await require_auth(request)

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    outcome = await db.ai_outcomes.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    prediction = pipe.get("prediction") or {}

    return {
        "pipeline_id": pipeline_id,
        "ai_prediction": prediction,
        "has_outcome": outcome is not None,
        "outcome": outcome.get("outcome") if outcome else None,
        "ai_correct": outcome.get("ai_correct") if outcome else None,
        "performance_rating": outcome.get("performance_rating") if outcome else None,
        "retention_months": outcome.get("retention_months") if outcome else None,
    }


@router.get("/insights")
async def learning_insights(request: Request):
    """AI-generated learning insights from outcome data."""
    await require_admin(request)

    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(200)
    if len(outcomes) < 3:
        return {"insights": [], "message": "Need at least 3 outcomes for insights"}

    calibrations = await db.ai_calibrations.find({}, {"_id": 0}).sort("calibrated_at", -1).to_list(1)
    latest_cal = calibrations[0] if calibrations else None

    # Summarize for AI
    summary = {
        "total_outcomes": len(outcomes),
        "outcomes": {
            o.get("outcome", "?"): sum(1 for x in outcomes if x.get("outcome") == o.get("outcome")) for o in outcomes
        },
        "accuracy_correct": sum(1 for o in outcomes if o.get("ai_correct") is True),
        "accuracy_incorrect": sum(1 for o in outcomes if o.get("ai_correct") is False),
        "avg_confidence": round(sum(o.get("ai_confidence", 50) for o in outcomes) / len(outcomes), 1),
        "latest_calibration": latest_cal.get("stage_weights") if latest_cal else None,
    }

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id="ai-learning-insights",
            system_message="You are an AI hiring system analyst. Respond in valid JSON format only.",
        ).with_model("openai", "gpt-4o")
        resp = await chat.send_message(
            UserMessage(
                text=f"""As an AI hiring system analyst, provide 3-5 actionable insights from this outcome data:

{json.dumps(summary, indent=2)}

Return JSON array: [{{"insight": "...", "category": "accuracy|calibration|pattern|improvement", "priority": "high|medium|low", "action": "specific recommendation"}}]"""
            )
        )
        resp_text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            clean = resp_text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            insights = json.loads(clean.strip())
        except Exception:
            insights = [
                {
                    "insight": resp.text[:300],
                    "category": "general",
                    "priority": "medium",
                    "action": "Review data manually",
                }
            ]
    except Exception as e:
        logger.warning(f"AI insights error: {e}")
        insights = [
            {
                "insight": "Collect more outcome data for better insights",
                "category": "improvement",
                "priority": "high",
                "action": "Record at least 10 outcomes",
            }
        ]

    return {
        "insights": insights,
        "data_summary": summary,
        "latest_calibration": latest_cal.get("calibrated_at") if latest_cal else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
