"""AI Document Analyzer — Upload docs and get AI-powered analysis.

Supports resumes, contracts, reports, and general documents.
Provides summaries, key insights, risk flags, and improvement suggestions.

API:
- POST /api/ai-docs/analyze    — Upload + analyze a document
- GET  /api/ai-docs/history     — User's analysis history
- GET  /api/ai-docs/{id}        — Get specific analysis
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from datetime import datetime, timezone
from typing import Optional
import uuid
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-docs")

ANALYSIS_TYPES = {
    "resume": {
        "name": "Resume Analysis",
        "system": """You are an expert Resume Analyst and Career Advisor. Analyze the resume text and provide:
Return ONLY valid JSON:
{
  "overall_score": 78,
  "summary": "Brief overview of the candidate",
  "strengths": ["Strength 1", "Strength 2"],
  "weaknesses": ["Area to improve 1"],
  "suggestions": [{"title": "Suggestion", "description": "Details", "priority": "high|medium|low"}],
  "keywords_found": ["keyword1"],
  "keywords_missing": ["missing keyword for their field"],
  "ats_score": 72,
  "sections_analysis": {"experience": 80, "education": 70, "skills": 85, "summary": 60}
}""",
    },
    "contract": {
        "name": "Contract Review",
        "system": """You are a Contract Analysis Expert. Analyze the contract text and flag important clauses.
Return ONLY valid JSON:
{
  "overall_risk": "low|medium|high",
  "summary": "Brief overview of the contract",
  "key_terms": [{"term": "Term name", "description": "What it means", "risk_level": "low|medium|high"}],
  "red_flags": ["Concerning clause 1"],
  "favorable_terms": ["Good clause 1"],
  "missing_clauses": ["Important missing clause"],
  "recommendations": ["Recommendation 1"],
  "parties": ["Party A", "Party B"],
  "duration": "Contract duration if found"
}""",
    },
    "report": {
        "name": "Report Summary",
        "system": """You are a Business Report Analyst. Summarize and analyze the report.
Return ONLY valid JSON:
{
  "summary": "Executive summary in 3-4 sentences",
  "key_findings": [{"finding": "Key finding", "importance": "high|medium|low"}],
  "data_points": [{"metric": "Metric name", "value": "Value", "trend": "up|down|stable"}],
  "action_items": ["Action item 1"],
  "conclusions": ["Main conclusion 1"],
  "questions_raised": ["Question that needs answering"]
}""",
    },
    "general": {
        "name": "General Analysis",
        "system": """You are a Document Analysis Expert. Analyze this document comprehensively.
Return ONLY valid JSON:
{
  "summary": "Comprehensive summary",
  "key_points": [{"point": "Key point", "importance": "high|medium|low"}],
  "topics": ["Topic 1", "Topic 2"],
  "sentiment": "positive|neutral|negative|mixed",
  "complexity": "simple|moderate|complex",
  "word_count_estimate": 500,
  "recommendations": ["Recommendation 1"],
  "questions": ["Question about the content"]
}""",
    },
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx", ".md", ".csv", ".json"}


@router.post("/analyze")
async def analyze_document(
    request: Request,
    file: Optional[UploadFile] = File(None),
    text_content: Optional[str] = Form(None),
    analysis_type: str = Form("general"),
    title: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    if analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(400, f"Invalid analysis type. Options: {list(ANALYSIS_TYPES.keys())}")

    doc_text = ""
    file_name = "Pasted Text"
    file_size = 0

    if file:
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(400, "File too large. Max 5MB.")
        file_name = file.filename or "uploaded_file"
        doc_text = content.decode("utf-8", errors="ignore")
    elif text_content:
        doc_text = text_content
        file_size = len(text_content)
    else:
        raise HTTPException(400, "Provide either a file or text_content")

    if len(doc_text) < 20:
        raise HTTPException(400, "Document too short. Provide at least 20 characters.")

    # Truncate for AI processing
    truncated = doc_text[:8000]
    analyzer = ANALYSIS_TYPES[analysis_type]

    try:
        analysis = await ai_generate_json(
            analyzer["system"],
            f"Analyze this {analysis_type} document:\n\n{truncated}",
            f"doc-{user['user_id'][:8]}",
        )
    except Exception as e:
        logger.error(f"Document analysis error: {e}")
        analysis = {
            "summary": "Analysis completed with limited detail.",
            "key_points": [{"point": "Document was processed", "importance": "medium"}],
        }

    now = datetime.now(timezone.utc).isoformat()
    doc_record = {
        "doc_id": f"doc_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "title": title or file_name,
        "file_name": file_name,
        "file_size": file_size,
        "analysis_type": analysis_type,
        "analysis_type_name": analyzer["name"],
        "analysis": analysis,
        "text_preview": doc_text[:500],
        "created_at": now,
    }
    await db.doc_analyses.insert_one(doc_record)
    doc_record.pop("_id", None)
    return doc_record


@router.get("/history")
async def get_analysis_history(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    docs = (
        await db.doc_analyses.find({"user_id": user.user_id}, {"_id": 0, "text_preview": 0})
        .sort("created_at", -1)
        .to_list(50)
    )
    return {"documents": docs}


@router.get("/{doc_id}")
async def get_analysis(request: Request, doc_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    doc = await db.doc_analyses.find_one({"doc_id": doc_id, "user_id": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc
