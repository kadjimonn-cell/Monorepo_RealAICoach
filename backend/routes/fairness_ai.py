"""Trust & Fairness AI — Bias detection, fairness scoring, and oversight.

Endpoints:
- GET  /api/fairness/bias-audit          Full bias audit across all hiring decisions
- GET  /api/fairness/pipeline/{id}/score Fairness score for a specific pipeline
- GET  /api/fairness/flagged             Get auto-flagged potentially biased decisions
- POST /api/fairness/flag/{pipeline_id}/review   Mark flagged decision as reviewed
- GET  /api/fairness/report              Admin bias report with recommendations
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import os
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, require_admin

router = APIRouter(prefix="/fairness")
logger = logging.getLogger("routes.fairness")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


@router.get("/bias-audit")
async def bias_audit(request: Request):
    """Full bias audit across all hiring pipelines — analyze decision patterns."""
    await require_admin(request)

    pipelines = await db.hiring_pipeline.find({}, {"_id": 0}).to_list(500)
    if not pipelines:
        return {
            "total_pipelines": 0,
            "audit_summary": "No pipelines to audit",
            "risk_level": "none",
            "patterns": [],
            "recommendations": [],
        }

    # Gather stats
    total = len(pipelines)
    decisions = {}
    stage_durations = {}
    employer_decisions = {}
    rejection_reasons = []

    for p in pipelines:
        pred = p.get("prediction") or {}
        decision = pred.get("recommendation", "pending")
        decisions[decision] = decisions.get(decision, 0) + 1

        eid = p.get("employer_id", "unknown")
        if eid not in employer_decisions:
            employer_decisions[eid] = {"hire": 0, "reject": 0, "total": 0}
        employer_decisions[eid]["total"] += 1
        if decision in ("strong_hire", "hire"):
            employer_decisions[eid]["hire"] += 1
        elif decision in ("no_hire", "strong_no_hire"):
            employer_decisions[eid]["reject"] += 1

        history = p.get("stage_history", [])
        if len(history) >= 2:
            for i in range(1, len(history)):
                prev_t = history[i - 1].get("timestamp", "")
                curr_t = history[i].get("timestamp", "")
                stage = history[i].get("stage", "")
                if prev_t and curr_t:
                    try:
                        delta = (
                            datetime.fromisoformat(curr_t.replace("Z", "+00:00"))
                            - datetime.fromisoformat(prev_t.replace("Z", "+00:00"))
                        ).total_seconds()
                        if stage not in stage_durations:
                            stage_durations[stage] = []
                        stage_durations[stage].append(delta)
                    except Exception:
                        pass

        if decision in ("no_hire", "strong_no_hire"):
            rejection_reasons.append(
                {
                    "pipeline_id": p.get("pipeline_id"),
                    "reason": pred.get("reasoning", "No reason provided"),
                    "confidence": pred.get("hire_confidence", 0),
                }
            )

    # Detect anomalies
    patterns = []
    flagged = []

    # 1. Employer rejection rate anomaly
    for eid, stats in employer_decisions.items():
        if stats["total"] >= 3:
            reject_rate = stats["reject"] / stats["total"]
            if reject_rate > 0.8:
                patterns.append(
                    {
                        "type": "high_rejection_rate",
                        "employer_id": eid,
                        "rejection_rate": round(reject_rate * 100, 1),
                        "total_decisions": stats["total"],
                        "severity": "high",
                        "description": f"Employer {eid} has {reject_rate * 100:.0f}% rejection rate across {stats['total']} candidates",
                    }
                )

    # 2. Stage duration variance
    for stage, durations in stage_durations.items():
        if len(durations) >= 3:
            avg = sum(durations) / len(durations)
            variance = sum((d - avg) ** 2 for d in durations) / len(durations)
            std = variance**0.5
            if std > avg * 2:
                patterns.append(
                    {
                        "type": "inconsistent_processing_time",
                        "stage": stage,
                        "avg_seconds": round(avg),
                        "std_dev": round(std),
                        "severity": "medium",
                        "description": f"Stage '{stage}' has highly inconsistent processing times (avg: {avg:.0f}s, std: {std:.0f}s)",
                    }
                )

    # 3. Decision distribution balance
    hire_count = decisions.get("strong_hire", 0) + decisions.get("hire", 0)
    reject_count = decisions.get("no_hire", 0) + decisions.get("strong_no_hire", 0)
    if total >= 5:
        if reject_count > hire_count * 3:
            patterns.append(
                {
                    "type": "disproportionate_rejections",
                    "hire_count": hire_count,
                    "reject_count": reject_count,
                    "ratio": round(reject_count / max(hire_count, 1), 1),
                    "severity": "high",
                    "description": f"Rejections outnumber hires by {reject_count / max(hire_count, 1):.1f}x — review AI calibration",
                }
            )
        elif hire_count > reject_count * 3 and total >= 10:
            patterns.append(
                {
                    "type": "disproportionate_approvals",
                    "hire_count": hire_count,
                    "reject_count": reject_count,
                    "severity": "medium",
                    "description": "Approvals significantly outnumber rejections — may indicate loose screening",
                }
            )

    # 4. Low-confidence decisions
    low_confidence_decisions = []
    for p in pipelines:
        pred = p.get("prediction") or {}
        conf = pred.get("hire_confidence", 100)
        if conf < 40 and pred.get("recommendation") in ("hire", "strong_hire"):
            low_confidence_decisions.append(p.get("pipeline_id"))
            flagged.append(
                {
                    "pipeline_id": p.get("pipeline_id"),
                    "candidate_id": p.get("candidate_id"),
                    "job_id": p.get("job_id"),
                    "decision": pred.get("recommendation"),
                    "confidence": conf,
                    "reason": "Low confidence positive decision — requires human review",
                    "flagged_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    if low_confidence_decisions:
        patterns.append(
            {
                "type": "low_confidence_hires",
                "count": len(low_confidence_decisions),
                "pipeline_ids": low_confidence_decisions[:5],
                "severity": "high",
                "description": f"{len(low_confidence_decisions)} hire decisions with <40% confidence",
            }
        )

    # Store flagged items
    now = datetime.now(timezone.utc).isoformat()
    for f in flagged:
        existing = await db.fairness_flags.find_one({"pipeline_id": f["pipeline_id"]}, {"_id": 0})
        if not existing:
            await db.fairness_flags.insert_one(
                {
                    **f,
                    "flag_id": f"flag_{uuid.uuid4().hex[:10]}",
                    "status": "pending",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": now,
                }
            )

    risk_level = "high" if any(p["severity"] == "high" for p in patterns) else ("medium" if patterns else "low")

    # AI-powered recommendations
    recommendations = []
    if patterns:
        try:
            chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id="bias-audit",
                system_message="You are a hiring fairness expert. Respond in valid JSON format only.",
            ).with_model("openai", "gpt-4o")
            prompt = f"""As a hiring fairness expert, analyze these bias patterns and provide 3-5 actionable recommendations:

Patterns detected:
{json.dumps(patterns, indent=2)}

Decision distribution: {json.dumps(decisions)}
Total pipelines: {total}

Respond as JSON array of objects: [{{"recommendation": "...", "priority": "high|medium|low", "impact": "..."}}]"""
            resp = await chat.send_message(UserMessage(text=prompt))
            resp_text = resp.text if hasattr(resp, "text") else str(resp)
            try:
                clean = resp_text.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                if clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                recommendations = json.loads(clean.strip())
            except json.JSONDecodeError:
                recommendations = [{"recommendation": resp_text[:300], "priority": "medium", "impact": "Review needed"}]
        except Exception as e:
            logger.warning(f"AI recommendation error: {e}")
            recommendations = [
                {
                    "recommendation": "Review detected patterns manually",
                    "priority": "high",
                    "impact": "Ensure fair hiring practices",
                }
            ]

    return {
        "total_pipelines": total,
        "decision_distribution": decisions,
        "risk_level": risk_level,
        "patterns": patterns,
        "flagged_count": len(flagged),
        "recommendations": recommendations,
        "employer_stats": {eid: s for eid, s in employer_decisions.items() if s["total"] >= 2},
        "stage_avg_durations": {s: round(sum(d) / len(d)) for s, d in stage_durations.items() if d},
        "audited_at": now,
    }


@router.get("/pipeline/{pipeline_id}/score")
async def pipeline_fairness_score(pipeline_id: str, request: Request):
    """Get fairness score for a specific pipeline."""
    await require_auth(request)

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pred = pipe.get("prediction") or {}
    score_components = {
        "confidence_score": min(pred.get("hire_confidence", 50), 100),
        "consistency_score": 80,
        "transparency_score": 90 if pred.get("reasoning") else 40,
    }

    # Check stage progression consistency
    history = pipe.get("stage_history", [])
    if len(history) >= 2:
        durations = []
        for i in range(1, len(history)):
            try:
                t1 = datetime.fromisoformat(history[i - 1]["timestamp"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(history[i]["timestamp"].replace("Z", "+00:00"))
                durations.append((t2 - t1).total_seconds())
            except Exception:
                pass
        if durations:
            avg = sum(durations) / len(durations)
            variance = sum((d - avg) ** 2 for d in durations) / len(durations)
            score_components["consistency_score"] = max(30, min(100, int(100 - (variance**0.5 / max(avg, 1)) * 50)))

    overall = round(sum(score_components.values()) / len(score_components))

    # Check for flags
    flag = await db.fairness_flags.find_one({"pipeline_id": pipeline_id}, {"_id": 0})

    return {
        "pipeline_id": pipeline_id,
        "overall_fairness_score": overall,
        "components": score_components,
        "has_flag": flag is not None,
        "flag_status": flag.get("status") if flag else None,
        "decision": pred.get("recommendation", "pending"),
        "confidence": pred.get("hire_confidence", 0),
    }


@router.get("/flagged")
async def get_flagged_decisions(request: Request):
    """Get all auto-flagged potentially biased decisions."""
    await require_admin(request)
    status = request.query_params.get("status", "")

    query = {}
    if status:
        query["status"] = status

    flags = await db.fairness_flags.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    stats = {
        "total": len(flags),
        "pending": sum(1 for f in flags if f.get("status") == "pending"),
        "reviewed": sum(1 for f in flags if f.get("status") == "reviewed"),
        "dismissed": sum(1 for f in flags if f.get("status") == "dismissed"),
    }

    return {"flags": flags, "stats": stats}


@router.post("/flag/{pipeline_id}/review")
async def review_flag(pipeline_id: str, request: Request):
    """Mark a flagged decision as reviewed."""
    user = await require_admin(request)
    body = await request.json()
    action = body.get("action", "reviewed")  # reviewed | dismissed | escalated
    notes = body.get("notes", "")

    if action not in ("reviewed", "dismissed", "escalated"):
        raise HTTPException(status_code=400, detail="Invalid action. Use: reviewed, dismissed, escalated")

    flag = await db.fairness_flags.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not flag:
        raise HTTPException(status_code=404, detail="No flag found for this pipeline")

    now = datetime.now(timezone.utc).isoformat()
    await db.fairness_flags.update_one(
        {"pipeline_id": pipeline_id},
        {
            "$set": {
                "status": action,
                "reviewed_by": user.user_id,
                "reviewer_name": user.name,
                "review_notes": notes,
                "reviewed_at": now,
            }
        },
    )

    return {
        "success": True,
        "pipeline_id": pipeline_id,
        "action": action,
        "reviewed_by": user.name,
    }


@router.get("/report")
async def fairness_report(request: Request):
    """Comprehensive admin bias report with AI-generated recommendations."""
    await require_admin(request)

    pipelines = await db.hiring_pipeline.find({}, {"_id": 0}).to_list(500)
    flags = await db.fairness_flags.find({}, {"_id": 0}).to_list(200)
    interviews = await db.interview_bookings.find({}, {"_id": 0}).to_list(500)

    total_pipes = len(pipelines)
    total_flags = len(flags)
    pending_flags = sum(1 for f in flags if f.get("status") == "pending")

    # Decision distribution
    decisions = {}
    for p in pipelines:
        dec = (p.get("prediction") or {}).get("recommendation", "pending")
        decisions[dec] = decisions.get(dec, 0) + 1

    # Confidence distribution
    confidence_buckets = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for p in pipelines:
        conf = (p.get("prediction") or {}).get("hire_confidence", 50)
        if conf <= 25:
            confidence_buckets["0-25"] += 1
        elif conf <= 50:
            confidence_buckets["26-50"] += 1
        elif conf <= 75:
            confidence_buckets["51-75"] += 1
        else:
            confidence_buckets["76-100"] += 1

    # Interview completion rate
    completed = sum(1 for iv in interviews if iv.get("status") == "completed")
    cancelled = sum(1 for iv in interviews if iv.get("status") == "cancelled")
    iv_total = len(interviews)

    # Equal opportunity metrics
    hire_count = decisions.get("strong_hire", 0) + decisions.get("hire", 0)
    reject_count = decisions.get("no_hire", 0) + decisions.get("strong_no_hire", 0)
    maybe_count = decisions.get("maybe", 0)
    pending_count = decisions.get("pending", 0)

    equal_opportunity = {
        "hire_rate": round(hire_count / max(total_pipes, 1) * 100, 1),
        "reject_rate": round(reject_count / max(total_pipes, 1) * 100, 1),
        "undecided_rate": round((maybe_count + pending_count) / max(total_pipes, 1) * 100, 1),
        "interview_completion_rate": round(completed / max(iv_total, 1) * 100, 1),
        "interview_cancellation_rate": round(cancelled / max(iv_total, 1) * 100, 1),
    }

    # Overall fairness grade
    flag_rate = total_flags / max(total_pipes, 1)
    if flag_rate < 0.05 and pending_flags == 0:
        grade = "A"
    elif flag_rate < 0.1:
        grade = "B"
    elif flag_rate < 0.2:
        grade = "C"
    elif flag_rate < 0.4:
        grade = "D"
    else:
        grade = "F"

    return {
        "grade": grade,
        "total_pipelines": total_pipes,
        "decision_distribution": decisions,
        "confidence_distribution": confidence_buckets,
        "equal_opportunity": equal_opportunity,
        "flags": {
            "total": total_flags,
            "pending": pending_flags,
            "reviewed": sum(1 for f in flags if f.get("status") == "reviewed"),
            "dismissed": sum(1 for f in flags if f.get("status") == "dismissed"),
            "escalated": sum(1 for f in flags if f.get("status") == "escalated"),
        },
        "interview_stats": {
            "total": iv_total,
            "completed": completed,
            "cancelled": cancelled,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
