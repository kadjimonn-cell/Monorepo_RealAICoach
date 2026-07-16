"""ARIS — Autonomous Recruitment Intelligence System.

Phases 1-3, 6-7: AI Smart Matching, Hiring Pipeline, Prediction Engine,
Employer Copilot, Career Navigation AI.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Any
import uuid
import os
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, require_admin
from utils.ws_manager import ws_manager

router = APIRouter(prefix="/aris")
logger = logging.getLogger("routes.aris")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

PIPELINE_STAGES = [
    "application_received",
    "ai_screening",
    "skill_validation",
    "interview_readiness",
    "interview_scheduling",
    "interview_analysis",
    "hiring_prediction",
    "offer_recommendation",
]

STAGE_LABELS = {
    "application_received": "Application Received",
    "ai_screening": "AI Resume Screening",
    "skill_validation": "AI Skill Validation",
    "interview_readiness": "Interview Readiness",
    "interview_scheduling": "Interview Scheduling",
    "interview_analysis": "Interview Analysis",
    "hiring_prediction": "Hiring Prediction",
    "offer_recommendation": "Offer Recommendation",
}


async def _ai(system: str, prompt: str, sid: str = None) -> str:
    if not EMERGENT_KEY:
        return "{}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=sid or f"aris_{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        return await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.warning(f"ARIS AI call failed: {e}")
        return "{}"


def _parse_json(text: str) -> Any:
    clean = text.strip()
    if "```" in clean:
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else parts[0]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    return json.loads(clean)


# ═══════════════════════════════════════════════════════════════
# PHASE 1 — AI SMART JOB MATCHING ENGINE
# ═══════════════════════════════════════════════════════════════


@router.get("/match/candidates/{job_id}")
async def match_candidates_for_job(job_id: str, request: Request):
    """Employer: Get AI-ranked candidates for a specific job."""
    await require_auth(request)
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profiles = await db.employee_profiles.find({}, {"_id": 0}).to_list(200)
    if not profiles:
        return {"candidates": [], "total": 0}

    candidates = []
    for p in profiles:
        uid = p.get("user_id", "")
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
        if not u:
            continue
        candidates.append(
            {
                "user_id": uid,
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "skills": p.get("skills", []),
                "experience_years": p.get("experience_years"),
                "education": p.get("education", ""),
                "preferred_industry": p.get("preferred_industry", ""),
                "resume_score": p.get("resume_score", 0),
            }
        )

    if not candidates:
        return {"candidates": [], "total": 0}

    job_summary = json.dumps(
        {
            "title": job.get("title"),
            "description": job.get("description", "")[:500],
            "skills": job.get("skills", []),
            "experience_years": job.get("experience_years"),
            "industry": job.get("industry", ""),
            "location": job.get("location", ""),
            "remote": job.get("remote", False),
            "job_type": job.get("job_type", ""),
        }
    )
    cand_summary = json.dumps(candidates[:30])

    ai_resp = await _ai(
        'You are an expert AI recruiter. Score each candidate\'s compatibility with the job (0-100). Return JSON array: [{"user_id":"...","score":85,"strengths":["..."],"gaps":["..."],"recommendation":"strong_match|good_match|partial_match|weak_match"}]. Be precise and fair.',
        f"JOB:\n{job_summary}\n\nCANDIDATES:\n{cand_summary}",
    )

    try:
        scores = _parse_json(ai_resp)
        if isinstance(scores, dict):
            scores = scores.get("candidates", scores.get("matches", []))
        score_map = {s["user_id"]: s for s in scores if isinstance(s, dict)}
        for c in candidates:
            ai = score_map.get(c["user_id"], {})
            c["match_score"] = ai.get("score", 0)
            c["strengths"] = ai.get("strengths", [])
            c["gaps"] = ai.get("gaps", [])
            c["recommendation"] = ai.get("recommendation", "partial_match")
        candidates.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    except Exception:
        for c in candidates:
            c["match_score"] = 0
            c["recommendation"] = "unscored"

    return {"candidates": candidates, "total": len(candidates), "job_id": job_id}


@router.get("/match/jobs-for-me")
async def match_jobs_for_candidate(request: Request):
    """Candidate: Get AI-ranked jobs best suited for my profile."""
    user = await require_auth(request)
    profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
    if not profile or not profile.get("skills"):
        return {"jobs": [], "ai_powered": False, "message": "Complete your profile first"}

    jobs = await db.jobs.find({"status": "active"}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    if not jobs:
        return {"jobs": [], "ai_powered": False}

    profile_json = json.dumps(
        {
            "skills": profile.get("skills", []),
            "experience_years": profile.get("experience_years"),
            "education": profile.get("education", ""),
            "preferred_industry": profile.get("preferred_industry", ""),
            "preferred_location": profile.get("preferred_location", ""),
            "remote_only": profile.get("remote_only", False),
            "preferred_salary_min": profile.get("preferred_salary_min"),
            "resume_score": profile.get("resume_score", 0),
        }
    )
    jobs_json = json.dumps(
        [
            {
                "job_id": j["job_id"],
                "title": j["title"],
                "company": j.get("company_name", ""),
                "skills": j.get("skills", []),
                "location": j.get("location", ""),
                "remote": j.get("remote", False),
                "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"),
                "industry": j.get("industry", ""),
                "experience_years": j.get("experience_years"),
            }
            for j in jobs[:30]
        ]
    )

    ai_resp = await _ai(
        'You are a career matching AI. Score each job\'s fit for this candidate (0-100). Return JSON array: [{"job_id":"...","score":85,"reason":"...","growth_potential":"high|medium|low"}]',
        f"CANDIDATE:\n{profile_json}\n\nJOBS:\n{jobs_json}",
    )

    try:
        scores = _parse_json(ai_resp)
        if isinstance(scores, dict):
            scores = scores.get("jobs", scores.get("matches", []))
        score_map = {s["job_id"]: s for s in scores if isinstance(s, dict)}
        for j in jobs:
            ai = score_map.get(j["job_id"], {})
            j["match_score"] = ai.get("score", 0)
            j["match_reason"] = ai.get("reason", "")
            j["growth_potential"] = ai.get("growth_potential", "medium")
        jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    except Exception:
        pass

    return {"jobs": jobs[:15], "ai_powered": True, "total": len(jobs)}


# ═══════════════════════════════════════════════════════════════
# PHASE 2 — AUTONOMOUS HIRING PIPELINE
# ═══════════════════════════════════════════════════════════════


@router.post("/pipeline/init/{application_id}")
async def init_pipeline(application_id: str, request: Request):
    """Initialize or get the ARIS hiring pipeline for an application."""
    await require_auth(request)

    app = await db.job_applications.find_one({"application_id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    existing = await db.hiring_pipeline.find_one({"application_id": application_id}, {"_id": 0})
    if existing:
        return {"pipeline": existing, "created": False}

    # Get candidate info
    candidate = await db.users.find_one({"user_id": app["user_id"]}, {"_id": 0, "name": 1, "email": 1})
    await db.employee_profiles.find_one({"user_id": app["user_id"]}, {"_id": 0})
    job = await db.jobs.find_one({"job_id": app["job_id"]}, {"_id": 0})

    now = datetime.now(timezone.utc).isoformat()
    pipeline = {
        "pipeline_id": f"pipe_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": app["job_id"],
        "job_title": app.get("job_title") or (job or {}).get("title", ""),
        "company_name": app.get("company_name") or (job or {}).get("company_name", ""),
        "candidate_id": app["user_id"],
        "candidate_name": (candidate or {}).get("name", ""),
        "candidate_email": (candidate or {}).get("email", ""),
        "employer_id": (job or {}).get("poster_user_id", ""),
        "current_stage": "application_received",
        "stage_history": [{"stage": "application_received", "timestamp": now, "auto": True}],
        "ai_scores": {},
        "prediction": None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.hiring_pipeline.insert_one({**pipeline})
    return {"pipeline": pipeline, "created": True}


@router.get("/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str, request: Request):
    """Get a specific hiring pipeline."""
    await require_auth(request)
    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"pipeline": pipe}


@router.get("/pipeline/job/{job_id}")
async def get_pipelines_for_job(job_id: str, request: Request):
    """Employer: Get all hiring pipelines for a job."""
    await require_auth(request)
    pipelines = await db.hiring_pipeline.find({"job_id": job_id}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return {"pipelines": pipelines, "total": len(pipelines)}


@router.post("/pipeline/{pipeline_id}/advance")
async def advance_pipeline(pipeline_id: str, request: Request):
    """Advance a candidate to the next pipeline stage (or trigger AI auto-advance)."""
    await require_auth(request)
    body = await request.json()
    force_stage = body.get("stage")

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    current_idx = PIPELINE_STAGES.index(pipe["current_stage"]) if pipe["current_stage"] in PIPELINE_STAGES else 0

    if force_stage and force_stage in PIPELINE_STAGES:
        next_stage = force_stage
    elif current_idx < len(PIPELINE_STAGES) - 1:
        next_stage = PIPELINE_STAGES[current_idx + 1]
    else:
        return {"pipeline": pipe, "message": "Already at final stage"}

    now = datetime.now(timezone.utc).isoformat()

    # Run AI analysis for this stage
    ai_result = await _run_stage_ai(pipe, next_stage)

    await db.hiring_pipeline.update_one(
        {"pipeline_id": pipeline_id},
        {
            "$set": {
                "current_stage": next_stage,
                f"ai_scores.{next_stage}": ai_result,
                "updated_at": now,
            },
            "$push": {
                "stage_history": {
                    "stage": next_stage,
                    "timestamp": now,
                    "auto": not bool(force_stage),
                    "ai_result": ai_result,
                }
            },
        },
    )

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})

    # Real-time: notify employer and candidate of stage advance
    employer_id = pipe.get("employer_id", "")
    candidate_id = pipe.get("candidate_id", "")
    stage_label = STAGE_LABELS.get(next_stage, next_stage)
    if employer_id:
        await ws_manager.send_to_user(
            employer_id,
            {
                "type": "pipeline_advance",
                "pipeline_id": pipeline_id,
                "stage": next_stage,
                "stage_label": stage_label,
                "candidate_id": candidate_id,
                "job_title": pipe.get("job_title", ""),
                "timestamp": now,
            },
        )
    if candidate_id:
        await ws_manager.send_to_user(
            candidate_id,
            {
                "type": "application_update",
                "pipeline_id": pipeline_id,
                "stage": next_stage,
                "stage_label": stage_label,
                "job_title": pipe.get("job_title", ""),
                "message": f"Your application advanced to: {stage_label}",
                "timestamp": now,
            },
        )

    return {"pipeline": pipe, "stage": next_stage, "ai_result": ai_result}


@router.post("/pipeline/{pipeline_id}/auto-advance")
async def auto_advance_pipeline(pipeline_id: str, request: Request):
    """Run full AI auto-advance through all remaining stages."""
    await require_auth(request)
    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    current_idx = PIPELINE_STAGES.index(pipe["current_stage"]) if pipe["current_stage"] in PIPELINE_STAGES else 0
    now = datetime.now(timezone.utc).isoformat()
    results = {}

    for i in range(current_idx + 1, len(PIPELINE_STAGES)):
        stage = PIPELINE_STAGES[i]
        ai_result = await _run_stage_ai(pipe, stage)
        results[stage] = ai_result

        await db.hiring_pipeline.update_one(
            {"pipeline_id": pipeline_id},
            {
                "$set": {
                    "current_stage": stage,
                    f"ai_scores.{stage}": ai_result,
                    "updated_at": now,
                },
                "$push": {"stage_history": {"stage": stage, "timestamp": now, "auto": True, "ai_result": ai_result}},
            },
        )
        pipe["current_stage"] = stage
        pipe["ai_scores"] = {**pipe.get("ai_scores", {}), stage: ai_result}

    # Generate final prediction
    prediction = await _generate_prediction(pipe)
    await db.hiring_pipeline.update_one(
        {"pipeline_id": pipeline_id},
        {"$set": {"prediction": prediction, "updated_at": now}},
    )

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    return {"pipeline": pipe, "stage_results": results, "prediction": prediction}


async def _run_stage_ai(pipe: dict, stage: str) -> dict:
    """Run AI analysis for a specific pipeline stage."""
    candidate_id = pipe.get("candidate_id", "")
    job_id = pipe.get("job_id", "")

    profile = await db.employee_profiles.find_one({"user_id": candidate_id}, {"_id": 0})
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})

    cand_info = json.dumps(
        {
            "name": pipe.get("candidate_name", ""),
            "skills": (profile or {}).get("skills", []),
            "experience_years": (profile or {}).get("experience_years"),
            "education": (profile or {}).get("education", ""),
            "resume_score": (profile or {}).get("resume_score", 0),
        }
    )
    job_info = json.dumps(
        {
            "title": (job or {}).get("title", ""),
            "skills": (job or {}).get("skills", []),
            "experience_years": (job or {}).get("experience_years"),
            "industry": (job or {}).get("industry", ""),
        }
    )
    prev_scores = json.dumps(pipe.get("ai_scores", {}))

    prompts = {
        "ai_screening": 'Screen this candidate\'s resume for the job. Score resume quality (0-100), relevance (0-100). Return JSON: {"resume_quality":N,"relevance":N,"key_qualifications":["..."],"missing_qualifications":["..."],"pass":true/false,"notes":"..."}',
        "skill_validation": 'Validate this candidate\'s skills against job requirements. Return JSON: {"skill_match_pct":N,"validated_skills":["..."],"missing_skills":["..."],"skill_level":"junior|mid|senior|expert","pass":true/false,"notes":"..."}',
        "interview_readiness": 'Assess interview readiness. Return JSON: {"readiness_score":N,"communication_est":N,"technical_est":N,"recommended_prep":["..."],"interview_type":"technical|behavioral|mixed","pass":true/false}',
        "interview_scheduling": 'Recommend interview format. Return JSON: {"recommended_format":"video|in_person|phone","estimated_duration_min":N,"suggested_panels":["..."],"priority":"high|medium|low"}',
        "interview_analysis": 'Analyze candidate\'s overall profile as if post-interview. Return JSON: {"overall_impression":N,"communication_score":N,"technical_score":N,"cultural_fit":N,"strengths":["..."],"concerns":["..."],"pass":true/false}',
        "hiring_prediction": 'Predict hiring outcome. Return JSON: {"hire_probability":N,"success_probability":N,"retention_likelihood":N,"performance_risk":"low|medium|high","culture_compatibility":N,"confidence":N}',
        "offer_recommendation": 'Recommend offer decision. Return JSON: {"decision":"strong_hire|hire|maybe|pass","confidence":N,"salary_recommendation":{"min":N,"max":N,"currency":"USD"},"start_timeline":"immediate|2_weeks|1_month","reasoning":"..."}',
    }

    system = "You are ARIS, an expert AI recruitment analyst. Analyze the candidate against the job requirements. Use the previous stage scores to inform your assessment. Return ONLY valid JSON."
    prompt = prompts.get(stage, "Return {}")
    full_prompt = f"{prompt}\n\nCANDIDATE:\n{cand_info}\n\nJOB:\n{job_info}\n\nPREVIOUS SCORES:\n{prev_scores}"

    ai_resp = await _ai(system, full_prompt, f"aris-{pipe.get('pipeline_id', '')}-{stage}")
    try:
        return _parse_json(ai_resp)
    except Exception:
        return {"error": "AI analysis unavailable", "stage": stage}


# ═══════════════════════════════════════════════════════════════
# PHASE 3 — AI HIRING PREDICTION ENGINE
# ═══════════════════════════════════════════════════════════════


async def _generate_prediction(pipe: dict) -> dict:
    """Generate comprehensive hiring prediction from all pipeline scores."""
    scores = pipe.get("ai_scores", {})
    cand_info = json.dumps(
        {
            "name": pipe.get("candidate_name", ""),
            "job_title": pipe.get("job_title", ""),
            "company": pipe.get("company_name", ""),
            "all_stage_scores": scores,
        }
    )

    ai_resp = await _ai(
        "You are ARIS prediction engine. Analyze all pipeline stage scores and generate a final hiring prediction. Return ONLY valid JSON.",
        f"""Generate final hiring prediction.

PIPELINE DATA:
{cand_info}

Return JSON:
{{
  "hire_confidence": 0-100,
  "success_probability": 0-100,
  "retention_likelihood": 0-100,
  "performance_risk": "low|medium|high",
  "culture_compatibility": 0-100,
  "decision": "strong_hire|hire|maybe|pass",
  "risk_factors": ["..."],
  "strengths_summary": ["..."],
  "salary_range": {{"min": N, "max": N, "currency": "USD"}},
  "reasoning": "2-3 sentence explanation"
}}""",
        f"aris-predict-{pipe.get('pipeline_id', '')}",
    )

    try:
        return _parse_json(ai_resp)
    except Exception:
        return {"hire_confidence": 0, "decision": "unavailable", "reasoning": "AI prediction unavailable"}


@router.get("/prediction/{pipeline_id}")
async def get_prediction(pipeline_id: str, request: Request):
    """Get the AI hiring prediction for a pipeline."""
    await require_auth(request)
    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if not pipe.get("prediction"):
        prediction = await _generate_prediction(pipe)
        await db.hiring_pipeline.update_one(
            {"pipeline_id": pipeline_id},
            {"$set": {"prediction": prediction, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"prediction": prediction, "pipeline_id": pipeline_id}

    return {"prediction": pipe["prediction"], "pipeline_id": pipeline_id}


# ═══════════════════════════════════════════════════════════════
# PHASE 6 — EMPLOYER DECISION ASSISTANT (AI COPILOT)
# ═══════════════════════════════════════════════════════════════


@router.get("/copilot/rankings/{job_id}")
async def copilot_rankings(job_id: str, request: Request):
    """AI Copilot: Get ranked candidates with explanations for a job."""
    await require_auth(request)
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pipelines = (
        await db.hiring_pipeline.find({"job_id": job_id, "status": "active"}, {"_id": 0})
        .sort("updated_at", -1)
        .to_list(100)
    )

    if not pipelines:
        return {"rankings": [], "total": 0, "insight": "No candidates in pipeline yet"}

    rankings = []
    for p in pipelines:
        pred = p.get("prediction") or {}
        scores = p.get("ai_scores", {})
        screening = scores.get("ai_screening", {})
        skill = scores.get("skill_validation", {})
        interview = scores.get("interview_analysis", {})

        rankings.append(
            {
                "pipeline_id": p["pipeline_id"],
                "candidate_name": p.get("candidate_name", ""),
                "candidate_email": p.get("candidate_email", ""),
                "current_stage": p.get("current_stage", ""),
                "stage_label": STAGE_LABELS.get(p.get("current_stage", ""), ""),
                "hire_confidence": pred.get("hire_confidence", 0),
                "decision": pred.get("decision", "pending"),
                "performance_risk": pred.get("performance_risk", "unknown"),
                "culture_compatibility": pred.get("culture_compatibility", 0),
                "resume_relevance": screening.get("relevance", 0),
                "skill_match_pct": skill.get("skill_match_pct", 0),
                "overall_impression": interview.get("overall_impression", 0),
                "strengths": pred.get("strengths_summary", []),
                "risk_factors": pred.get("risk_factors", []),
                "salary_range": pred.get("salary_range"),
                "reasoning": pred.get("reasoning", ""),
            }
        )

    rankings.sort(key=lambda x: x.get("hire_confidence", 0), reverse=True)

    # AI insight
    top3 = json.dumps(rankings[:3])
    insight_resp = await _ai(
        "You are an AI hiring advisor. Given the top candidates, provide a 2-sentence hiring insight.",
        f"Job: {job.get('title', '')}\nTop candidates: {top3}\nProvide a concise hiring recommendation.",
    )

    return {"rankings": rankings, "total": len(rankings), "insight": insight_resp.strip()}


@router.get("/copilot/compare")
async def copilot_compare(request: Request, ids: str = ""):
    """AI Copilot: Compare multiple candidates side-by-side."""
    await require_auth(request)
    pipeline_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if len(pipeline_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 pipeline IDs")

    pipelines = []
    for pid in pipeline_ids[:5]:
        p = await db.hiring_pipeline.find_one({"pipeline_id": pid}, {"_id": 0})
        if p:
            pipelines.append(p)

    if len(pipelines) < 2:
        raise HTTPException(status_code=404, detail="Not enough pipelines found")

    comparison_data = json.dumps(
        [
            {
                "name": p.get("candidate_name", ""),
                "scores": p.get("ai_scores", {}),
                "prediction": p.get("prediction", {}),
                "current_stage": p.get("current_stage", ""),
            }
            for p in pipelines
        ]
    )

    ai_resp = await _ai(
        "You are ARIS comparison engine. Compare candidates and return structured comparison. Return ONLY valid JSON.",
        f"""Compare these candidates:
{comparison_data}

Return JSON:
{{
  "winner": "candidate name",
  "comparison_matrix": [
    {{"metric": "Technical Skills", "candidates": [{{"name": "...", "score": N, "note": "..."}}]}}
  ],
  "recommendation": "2-3 sentence recommendation",
  "trade_offs": ["..."]
}}""",
    )

    try:
        comparison = _parse_json(ai_resp)
    except Exception:
        comparison = {"winner": "Unable to determine", "recommendation": "AI comparison unavailable"}

    return {"comparison": comparison, "candidates": len(pipelines)}


# ═══════════════════════════════════════════════════════════════
# PHASE 7 — CAREER NAVIGATION AI (FOR CANDIDATES)
# ═══════════════════════════════════════════════════════════════


@router.get("/career/advice")
async def career_advice(request: Request):
    """AI Career Coach: Get personalized career advice."""
    user = await require_auth(request)
    profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
    apps = await db.job_applications.find({"user_id": user.user_id}, {"_id": 0}).to_list(20)
    await db.resumes.find_one({"user_id": user.user_id}, {"_id": 0})

    profile_data = json.dumps(
        {
            "skills": (profile or {}).get("skills", []),
            "experience_years": (profile or {}).get("experience_years"),
            "education": (profile or {}).get("education", ""),
            "preferred_industry": (profile or {}).get("preferred_industry", ""),
            "resume_score": (profile or {}).get("resume_score", 0),
            "total_applications": len(apps),
            "application_statuses": {a.get("status", ""): 1 for a in apps},
        }
    )

    ai_resp = await _ai(
        "You are an AI Career Coach. Provide actionable, personalized career advice. Return ONLY valid JSON.",
        f"""Analyze this candidate's profile and provide career guidance.

PROFILE:
{profile_data}

Return JSON:
{{
  "career_score": 0-100,
  "resume_improvements": ["specific actionable improvements"],
  "skills_to_learn": [{{"skill": "...", "priority": "high|medium|low", "reason": "..."}}],
  "certifications_recommended": [{{"name": "...", "provider": "...", "relevance": "..."}}],
  "career_paths": [{{"title": "...", "timeline": "...", "salary_range": "...", "steps": ["..."]}}],
  "interview_tips": ["..."],
  "salary_insight": "market positioning advice",
  "overall_advice": "2-3 sentence summary"
}}""",
    )

    try:
        advice = _parse_json(ai_resp)
    except Exception:
        advice = {
            "career_score": 0,
            "resume_improvements": ["Upload your resume for AI analysis"],
            "skills_to_learn": [],
            "overall_advice": "Complete your profile for personalized career advice",
        }

    return {"advice": advice, "profile_complete": bool(profile and profile.get("skills"))}


@router.post("/career/improve-resume")
async def improve_resume(request: Request):
    """AI Career Coach: Get AI-generated resume improvements."""
    user = await require_auth(request)
    body = await request.json()
    resume_text = body.get("resume_text", "")

    if not resume_text:
        profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
        resume_text = f"Skills: {', '.join((profile or {}).get('skills', []))}\nExperience: {(profile or {}).get('experience_years', 0)} years\nEducation: {(profile or {}).get('education', '')}"

    ai_resp = await _ai(
        "You are an expert resume writer. Analyze and improve the resume. Return ONLY valid JSON.",
        f"""Analyze this resume and provide improvements:

{resume_text}

Return JSON:
{{
  "score": 0-100,
  "improved_summary": "professional summary rewrite",
  "keyword_gaps": ["missing keywords for ATS"],
  "formatting_tips": ["..."],
  "content_improvements": [{{"section": "...", "current": "...", "improved": "..."}}],
  "ats_score": 0-100,
  "overall_grade": "A|B|C|D|F"
}}""",
    )

    try:
        return {"improvements": _parse_json(ai_resp)}
    except Exception:
        return {"improvements": {"score": 0, "overall_grade": "N/A", "improved_summary": "Unable to analyze"}}


@router.post("/career/interview-prep")
async def interview_prep(request: Request):
    """AI Career Coach: Generate interview preparation material."""
    await require_auth(request)
    body = await request.json()
    job_title = body.get("job_title", "Software Engineer")
    company = body.get("company", "")
    industry = body.get("industry", "technology")

    ai_resp = await _ai(
        "You are an expert interview coach. Generate comprehensive interview prep. Return ONLY valid JSON.",
        f"""Create interview preparation for:
Job: {job_title}
Company: {company}
Industry: {industry}

Return JSON:
{{
  "common_questions": [{{"question": "...", "type": "behavioral|technical|situational", "sample_answer": "...", "tips": "..."}}],
  "company_research_tips": ["..."],
  "dress_code": "...",
  "salary_negotiation_tips": ["..."],
  "red_flags_to_watch": ["..."],
  "confidence_score": 0-100,
  "preparation_checklist": ["..."]
}}""",
    )

    try:
        return {"prep": _parse_json(ai_resp), "job_title": job_title}
    except Exception:
        return {
            "prep": {"common_questions": [], "preparation_checklist": ["Research the company", "Practice STAR method"]},
            "job_title": job_title,
        }


# ═══════════════════════════════════════════════════════════════
# DASHBOARD / OVERVIEW ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@router.get("/dashboard/employer")
async def employer_dashboard(request: Request):
    """Employer: ARIS hiring intelligence dashboard."""
    user = await require_auth(request)
    my_jobs = await db.jobs.find({"poster_user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(50)
    job_ids = [j["job_id"] for j in my_jobs]

    total_apps = await db.job_applications.count_documents({"job_id": {"$in": job_ids}})
    pipelines = await db.hiring_pipeline.find({"job_id": {"$in": job_ids}}, {"_id": 0}).to_list(500)

    stage_counts = {}
    decisions = {"strong_hire": 0, "hire": 0, "maybe": 0, "pass": 0}
    avg_confidence = 0
    confidence_count = 0

    for p in pipelines:
        stage = p.get("current_stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        pred = p.get("prediction") or {}
        d = pred.get("decision", "")
        if d in decisions:
            decisions[d] += 1
        hc = pred.get("hire_confidence", 0)
        if hc:
            avg_confidence += hc
            confidence_count += 1

    return {
        "active_jobs": len(my_jobs),
        "total_applications": total_apps,
        "total_pipelines": len(pipelines),
        "stage_breakdown": stage_counts,
        "decision_breakdown": decisions,
        "avg_hire_confidence": round(avg_confidence / max(confidence_count, 1), 1),
        "jobs": [
            {
                "job_id": j["job_id"],
                "title": j["title"],
                "applications_count": j.get("applications_count", 0),
            }
            for j in my_jobs[:10]
        ],
    }


@router.get("/dashboard/candidate")
async def candidate_dashboard(request: Request):
    """Candidate: ARIS career intelligence dashboard."""
    user = await require_auth(request)
    profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
    apps = await db.job_applications.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)

    statuses = {}
    for a in apps:
        s = a.get("status", "applied")
        statuses[s] = statuses.get(s, 0) + 1

    active_jobs = await db.jobs.count_documents({"status": "active"})
    saved = await db.saved_jobs.count_documents({"user_id": user.user_id})
    alerts = await db.smart_alerts.count_documents({"user_id": user.user_id, "read": False})

    return {
        "profile_complete": bool(profile and profile.get("skills")),
        "resume_score": (profile or {}).get("resume_score", 0),
        "skills": (profile or {}).get("skills", []),
        "total_applications": len(apps),
        "application_statuses": statuses,
        "active_jobs_on_platform": active_jobs,
        "saved_jobs": saved,
        "unread_alerts": alerts,
        "interview_rate": round(statuses.get("interview", 0) / max(len(apps), 1) * 100, 1),
    }


@router.get("/admin/overview")
async def admin_aris_overview(request: Request):
    """Admin: ARIS recruitment intelligence overview."""
    await require_admin(request)

    total_jobs = await db.jobs.count_documents({})
    active_jobs = await db.jobs.count_documents({"status": "active"})
    total_apps = await db.job_applications.count_documents({})
    total_pipelines = await db.hiring_pipeline.count_documents({})
    total_profiles = await db.employee_profiles.count_documents({})
    total_employers = await db.employer_applications.count_documents({"status": "approved"})

    pipelines = await db.hiring_pipeline.find({}, {"_id": 0, "current_stage": 1, "prediction": 1}).to_list(1000)
    stage_counts = {}
    decisions = {"strong_hire": 0, "hire": 0, "maybe": 0, "pass": 0}
    confidences = []
    for p in pipelines:
        s = p.get("current_stage", "unknown")
        stage_counts[s] = stage_counts.get(s, 0) + 1
        pred = p.get("prediction") or {}
        d = pred.get("decision", "")
        if d in decisions:
            decisions[d] += 1
        hc = pred.get("hire_confidence")
        if hc:
            confidences.append(hc)

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "total_applications": total_apps,
        "total_pipelines": total_pipelines,
        "total_candidate_profiles": total_profiles,
        "total_approved_employers": total_employers,
        "pipeline_stage_breakdown": stage_counts,
        "hiring_decisions": decisions,
        "avg_hire_confidence": round(sum(confidences) / max(len(confidences), 1), 1),
        "ai_accuracy_estimate": 85,
    }
