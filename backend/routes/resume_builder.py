"""AI Resume Builder & Interview Training System.

Features: AI resume generation, scoring, ATS optimization, PDF export,
mock interview simulation, performance scoring, feedback coaching.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uuid
import os
import json
import logging
import io

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth

router = APIRouter(prefix="/career-tools")
logger = logging.getLogger("routes.career_tools")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def _ai(system: str, prompt: str, sid: str = None) -> str:
    if not EMERGENT_KEY:
        return "{}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=sid or f"ct_{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("openai", "gpt-4o")
        return await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.warning(f"Career tools AI failed: {e}")
        return "{}"


def _parse_json(text: str):
    clean = text.strip()
    if "```" in clean:
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else parts[0]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    return json.loads(clean)


# ═══════════════════════════════════════════════════════════════
# AI RESUME BUILDER
# ═══════════════════════════════════════════════════════════════


class ResumeGenRequest(BaseModel):
    target_job_title: Optional[str] = None
    target_industry: Optional[str] = None
    style: str = "professional"  # professional, modern, creative


@router.post("/resume/generate")
async def generate_resume(payload: ResumeGenRequest, request: Request):
    """AI Resume Builder: Generate optimized resume from profile data."""
    user = await require_auth(request)
    profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})

    profile_data = json.dumps(
        {
            "name": user.name,
            "email": user.email,
            "skills": (profile or {}).get("skills", []),
            "experience_years": (profile or {}).get("experience_years"),
            "education": (profile or {}).get("education", ""),
            "work_history": (profile or {}).get("work_history", []),
            "certifications": (profile or {}).get("certifications", []),
            "preferred_industry": (profile or {}).get("preferred_industry", ""),
            "bio": (profile or {}).get("bio", ""),
        }
    )

    ai_resp = await _ai(
        "You are an expert resume writer. Generate a complete, ATS-optimized resume. Return ONLY valid JSON.",
        f"""Generate a professional resume for this candidate.
Target: {payload.target_job_title or "General"} in {payload.target_industry or "any industry"}
Style: {payload.style}

PROFILE DATA:
{profile_data}

Return JSON:
{{
  "full_name": "...",
  "contact": {{"email": "...", "phone": "", "location": "", "linkedin": ""}},
  "professional_summary": "3-4 sentence compelling summary",
  "skills": ["skill1", "skill2"],
  "experience": [
    {{"title": "...", "company": "...", "period": "...", "highlights": ["achievement 1", "achievement 2"]}}
  ],
  "education": [
    {{"degree": "...", "institution": "...", "year": "..."}}
  ],
  "certifications": ["..."],
  "ats_score": 0-100,
  "resume_score": 0-100,
  "improvement_tips": ["tip1", "tip2"]
}}""",
    )

    try:
        resume_data = _parse_json(ai_resp)
    except Exception:
        resume_data = {
            "full_name": user.name,
            "contact": {"email": user.email},
            "professional_summary": "Profile data insufficient for AI generation",
            "skills": (profile or {}).get("skills", []),
            "ats_score": 0,
            "resume_score": 0,
        }

    # Save generated resume
    now = datetime.now(timezone.utc).isoformat()
    resume_id = f"res_{uuid.uuid4().hex[:10]}"
    await db.generated_resumes.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "resume_id": resume_id,
                "user_id": user.user_id,
                "resume_data": resume_data,
                "target_job": payload.target_job_title,
                "target_industry": payload.target_industry,
                "style": payload.style,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    return {"resume": resume_data, "resume_id": resume_id}


@router.get("/resume/latest")
async def get_latest_resume(request: Request):
    """Get the latest generated resume."""
    user = await require_auth(request)
    resume = await db.generated_resumes.find_one({"user_id": user.user_id}, {"_id": 0})
    if not resume:
        return {"resume": None}
    return {"resume": resume.get("resume_data"), "resume_id": resume.get("resume_id")}


@router.post("/resume/score")
async def score_resume(request: Request):
    """AI: Score and analyze an existing resume text."""
    user = await require_auth(request)
    body = await request.json()
    resume_text = body.get("resume_text", "")

    if not resume_text:
        profile = await db.employee_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
        resume_text = f"Skills: {', '.join((profile or {}).get('skills', []))}\nExperience: {(profile or {}).get('experience_years', 0)} years"

    ai_resp = await _ai(
        "You are an ATS and resume expert. Score and analyze the resume. Return ONLY valid JSON.",
        f"""Analyze this resume:

{resume_text[:3000]}

Return JSON:
{{
  "overall_score": 0-100,
  "ats_score": 0-100,
  "content_score": 0-100,
  "format_score": 0-100,
  "keyword_density": 0-100,
  "missing_keywords": ["keyword1"],
  "strengths": ["..."],
  "improvements": [{{"section": "...", "issue": "...", "fix": "..."}}],
  "grade": "A|B|C|D|F",
  "summary": "2-3 sentence overall assessment"
}}""",
    )

    try:
        return {"analysis": _parse_json(ai_resp)}
    except Exception:
        return {"analysis": {"overall_score": 0, "grade": "N/A", "summary": "Unable to analyze"}}


@router.get("/resume/export/{format}")
async def export_resume(format: str, request: Request):
    """Export resume as text (PDF requires client-side rendering)."""
    user = await require_auth(request)
    resume = await db.generated_resumes.find_one({"user_id": user.user_id}, {"_id": 0})
    if not resume or not resume.get("resume_data"):
        raise HTTPException(status_code=404, detail="No resume found. Generate one first.")

    rd = resume["resume_data"]

    if format == "txt":
        lines = []
        lines.append(rd.get("full_name", ""))
        c = rd.get("contact", {})
        lines.append(f"{c.get('email', '')} | {c.get('phone', '')} | {c.get('location', '')}")
        lines.append("")
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(rd.get("professional_summary", ""))
        lines.append("")
        lines.append("SKILLS")
        lines.append(", ".join(rd.get("skills", [])))
        lines.append("")
        lines.append("EXPERIENCE")
        for exp in rd.get("experience", []):
            lines.append(f"{exp.get('title', '')} | {exp.get('company', '')} | {exp.get('period', '')}")
            for h in exp.get("highlights", []):
                lines.append(f"  - {h}")
            lines.append("")
        lines.append("EDUCATION")
        for edu in rd.get("education", []):
            lines.append(f"{edu.get('degree', '')} | {edu.get('institution', '')} | {edu.get('year', '')}")
        if rd.get("certifications"):
            lines.append("")
            lines.append("CERTIFICATIONS")
            lines.append(", ".join(rd.get("certifications", [])))

        content = "\n".join(lines)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={rd.get('full_name', 'resume').replace(' ', '_')}_resume.txt"
            },
        )

    # Return JSON for client-side PDF rendering
    return {"resume_data": rd, "format": "json"}


# ═══════════════════════════════════════════════════════════════
# AI INTERVIEW TRAINING (MOCK INTERVIEWS)
# ═══════════════════════════════════════════════════════════════


class MockInterviewStart(BaseModel):
    job_title: str = "Software Engineer"
    company: str = ""
    industry: str = "technology"
    mode: str = "mixed"  # behavioral, technical, mixed
    difficulty: str = "medium"  # easy, medium, hard


@router.post("/mock-interview/start")
async def start_mock_interview(payload: MockInterviewStart, request: Request):
    """Start an AI mock interview session."""
    user = await require_auth(request)
    session_id = f"mock_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    ai_resp = await _ai(
        "You are an expert interviewer. Generate a structured mock interview plan. Return ONLY valid JSON.",
        f"""Create a mock interview plan for:
Job: {payload.job_title}
Company: {payload.company or "Generic"}
Industry: {payload.industry}
Mode: {payload.mode}
Difficulty: {payload.difficulty}

Return JSON:
{{
  "total_questions": 8,
  "estimated_time_minutes": 25,
  "questions": [
    {{"id": 1, "question": "...", "type": "behavioral|technical|situational", "difficulty": "easy|medium|hard", "evaluation_criteria": ["..."], "ideal_points": ["key points to cover"]}}
  ],
  "opening_message": "Welcome to your mock interview...",
  "tips_before_start": ["tip1", "tip2"]
}}""",
        session_id,
    )

    try:
        plan = _parse_json(ai_resp)
    except Exception:
        plan = {
            "total_questions": 5,
            "questions": [
                {
                    "id": 1,
                    "question": f"Tell me about yourself and why you're interested in the {payload.job_title} role.",
                    "type": "behavioral",
                    "difficulty": "easy",
                },
                {
                    "id": 2,
                    "question": "Describe a challenging project you worked on.",
                    "type": "behavioral",
                    "difficulty": "medium",
                },
                {
                    "id": 3,
                    "question": f"What technical skills make you a good fit for this {payload.job_title} position?",
                    "type": "technical",
                    "difficulty": "medium",
                },
                {
                    "id": 4,
                    "question": "How do you handle conflict in a team?",
                    "type": "situational",
                    "difficulty": "medium",
                },
                {
                    "id": 5,
                    "question": "Where do you see yourself in 5 years?",
                    "type": "behavioral",
                    "difficulty": "easy",
                },
            ],
            "opening_message": f"Welcome to your mock interview for {payload.job_title}. Let's begin!",
        }

    session = {
        "session_id": session_id,
        "user_id": user.user_id,
        "job_title": payload.job_title,
        "company": payload.company,
        "mode": payload.mode,
        "difficulty": payload.difficulty,
        "plan": plan,
        "answers": [],
        "scores": [],
        "overall_score": None,
        "status": "in_progress",
        "created_at": now,
        "updated_at": now,
    }

    await db.mock_interviews.insert_one({**session})
    return {"session": {**session, "plan": plan}}


@router.post("/mock-interview/{session_id}/answer")
async def submit_answer(session_id: str, request: Request):
    """Submit an answer for a mock interview question."""
    user = await require_auth(request)
    body = await request.json()
    question_id = body.get("question_id", 1)
    answer_text = body.get("answer", "")

    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    questions = session.get("plan", {}).get("questions", [])
    question = next((q for q in questions if q.get("id") == question_id), None)

    if not question:
        raise HTTPException(status_code=400, detail="Question not found")

    # AI evaluate the answer
    ai_resp = await _ai(
        "You are an expert interview evaluator. Score the candidate's answer. Return ONLY valid JSON.",
        f"""Evaluate this interview answer:

Question: {question["question"]}
Type: {question.get("type", "general")}
Candidate's Answer: {answer_text}

Return JSON:
{{
  "score": 0-100,
  "clarity": 0-100,
  "relevance": 0-100,
  "depth": 0-100,
  "confidence_est": 0-100,
  "feedback": "specific constructive feedback",
  "ideal_answer_points": ["what they should have mentioned"],
  "improvement_tip": "one key tip to improve"
}}""",
        f"{session_id}-q{question_id}",
    )

    try:
        evaluation = _parse_json(ai_resp)
    except Exception:
        evaluation = {"score": 50, "feedback": "Unable to evaluate", "improvement_tip": "Try to be more specific"}

    now = datetime.now(timezone.utc).isoformat()
    answer_entry = {
        "question_id": question_id,
        "question": question["question"],
        "answer": answer_text,
        "evaluation": evaluation,
        "submitted_at": now,
    }

    await db.mock_interviews.update_one(
        {"session_id": session_id},
        {
            "$push": {"answers": answer_entry, "scores": evaluation.get("score", 0)},
            "$set": {"updated_at": now},
        },
    )

    # Check if this is the last question
    total_q = len(questions)
    answered = len(session.get("answers", [])) + 1
    is_complete = answered >= total_q

    return {
        "evaluation": evaluation,
        "question_id": question_id,
        "progress": f"{answered}/{total_q}",
        "is_complete": is_complete,
    }


@router.post("/mock-interview/{session_id}/finish")
async def finish_mock_interview(session_id: str, request: Request):
    """Finish mock interview and get overall performance report."""
    user = await require_auth(request)
    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.get("answers", [])
    scores = [a.get("evaluation", {}).get("score", 0) for a in answers]
    avg_score = round(sum(scores) / max(len(scores), 1), 1)

    # AI generate overall report
    answers_summary = json.dumps(
        [
            {
                "q": a["question"],
                "score": a.get("evaluation", {}).get("score", 0),
                "feedback": a.get("evaluation", {}).get("feedback", ""),
            }
            for a in answers
        ]
    )

    ai_resp = await _ai(
        "You are an expert interview coach. Generate a comprehensive performance report. Return ONLY valid JSON.",
        f"""Generate interview performance report.
Job: {session.get("job_title", "")}
Answers & Scores: {answers_summary}
Average Score: {avg_score}

Return JSON:
{{
  "overall_score": {avg_score},
  "grade": "A|B|C|D|F",
  "confidence_level": "high|medium|low",
  "communication_rating": 0-100,
  "technical_rating": 0-100,
  "behavioral_rating": 0-100,
  "top_strengths": ["..."],
  "areas_to_improve": ["..."],
  "detailed_feedback": "3-4 sentence comprehensive feedback",
  "next_steps": ["actionable next steps"],
  "interview_readiness": "ready|almost_ready|needs_practice"
}}""",
        f"{session_id}-report",
    )

    try:
        report = _parse_json(ai_resp)
    except Exception:
        report = {
            "overall_score": avg_score,
            "grade": "B" if avg_score >= 60 else "C",
            "detailed_feedback": "Complete more questions for a detailed analysis.",
            "interview_readiness": "needs_practice",
        }

    now = datetime.now(timezone.utc).isoformat()
    await db.mock_interviews.update_one(
        {"session_id": session_id},
        {"$set": {"status": "completed", "overall_score": report, "updated_at": now}},
    )

    return {"report": report, "session_id": session_id, "total_questions": len(answers)}


@router.get("/mock-interview/history")
async def mock_interview_history(request: Request):
    """Get user's mock interview history."""
    user = await require_auth(request)
    sessions = (
        await db.mock_interviews.find({"user_id": user.user_id}, {"_id": 0, "plan": 0, "answers": 0})
        .sort("created_at", -1)
        .to_list(20)
    )
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/mock-interview/{session_id}")
async def get_mock_interview(session_id: str, request: Request):
    """Get a specific mock interview session with all answers."""
    user = await require_auth(request)
    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}
