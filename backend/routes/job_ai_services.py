"""Job AI Services - Translation, Interview Simulation, Salary Benchmarking."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

from routes.db import db, get_current_user, require_auth, EMERGENT_LLM_KEY
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORTED_LANGS = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "ar": "Arabic",
    "pt": "Portuguese",
    "sw": "Swahili",
}


# ── AI Translation ──


class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "en"
    target_lang: str = "fr"


@router.post("/translate")
async def translate_text(payload: TranslateRequest, request: Request):
    """AI-powered translation for job content."""
    await require_auth(request)

    if payload.target_lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {payload.target_lang}")
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    src = SUPPORTED_LANGS.get(payload.source_lang, "English")
    tgt = SUPPORTED_LANGS.get(payload.target_lang, "French")

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"translate_{uuid.uuid4().hex[:8]}",
            system_message=f"You are a professional translator. Translate the following text from {src} to {tgt}. Return ONLY the translated text, no explanations.",
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=payload.text))
        translated = response.text if hasattr(response, "text") else str(response)
        return {
            "translated_text": translated.strip(),
            "source_lang": payload.source_lang,
            "target_lang": payload.target_lang,
        }
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail="Translation service unavailable")


@router.get("/languages")
async def list_supported_languages():
    """List supported languages for translation."""
    return {"languages": [{"code": k, "name": v} for k, v in SUPPORTED_LANGS.items()]}


# ── Interview Simulation AI ──


class InterviewSimRequest(BaseModel):
    job_title: str
    industry: Optional[str] = "technology"
    experience_level: Optional[str] = "mid"
    num_questions: int = 5


@router.post("/interview-sim")
async def interview_simulation(payload: InterviewSimRequest, request: Request):
    """Generate AI-powered interview questions for a job role."""
    await require_auth(request)

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"interview_{uuid.uuid4().hex[:8]}",
            system_message="You are an expert HR interviewer. Generate realistic interview questions. Return a JSON array of objects with fields: question, type (behavioral/technical/situational), difficulty (easy/medium/hard), tips (string with answer tips).",
        ).with_model("openai", "gpt-5.2")

        prompt = f"Generate {payload.num_questions} interview questions for a {payload.experience_level}-level {payload.job_title} position in the {payload.industry} industry. Mix behavioral, technical, and situational questions."
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.text if hasattr(response, "text") else str(response)

        # Parse JSON
        import json

        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        questions = json.loads(clean.strip())

        # Log the simulation
        await db.interview_simulations.insert_one(
            {
                "user_id": (await get_current_user(request)).user_id,
                "job_title": payload.job_title,
                "industry": payload.industry,
                "num_questions": len(questions),
                "created_at": datetime.now(timezone.utc),
            }
        )

        return {"questions": questions, "job_title": payload.job_title, "industry": payload.industry}
    except json.JSONDecodeError:
        return {
            "questions": [
                {
                    "question": text.strip(),
                    "type": "general",
                    "difficulty": "medium",
                    "tips": "Think through your answer carefully",
                }
            ],
            "job_title": payload.job_title,
        }
    except Exception as e:
        logger.warning(f"Interview sim failed: {e}")
        raise HTTPException(status_code=500, detail="Interview simulation unavailable")


# ── Salary Benchmarking AI ──


class SalaryBenchmarkRequest(BaseModel):
    job_title: str
    location: str
    experience_years: int = 3
    industry: Optional[str] = "technology"


@router.post("/salary-benchmark")
async def salary_benchmark(payload: SalaryBenchmarkRequest, request: Request):
    """AI-powered salary benchmarking by role and location."""
    await require_auth(request)

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"salary_{uuid.uuid4().hex[:8]}",
            system_message="You are a compensation analyst. Provide salary benchmarks. Return a JSON object with fields: currency (string), min_salary (number), median_salary (number), max_salary (number), percentile_25 (number), percentile_75 (number), market_trend (string: rising/stable/declining), insights (string with 2-3 sentences), comparable_roles (array of strings).",
        ).with_model("openai", "gpt-5.2")

        prompt = f"Provide salary benchmark for a {payload.job_title} with {payload.experience_years} years of experience in {payload.location}, {payload.industry} industry. Use realistic market data for 2025-2026."
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.text if hasattr(response, "text") else str(response)

        import json

        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        benchmark = json.loads(clean.strip())

        return {
            "benchmark": benchmark,
            "job_title": payload.job_title,
            "location": payload.location,
            "experience_years": payload.experience_years,
        }
    except Exception as e:
        logger.warning(f"Salary benchmark failed: {e}")
        raise HTTPException(status_code=500, detail="Salary benchmarking unavailable")
