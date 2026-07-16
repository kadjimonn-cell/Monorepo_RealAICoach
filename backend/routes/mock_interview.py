"""AI-Powered Mock Interview Simulator.

Practice interviews with AI personas (Technical, Behavioral, HR).
Real-time Q&A with scoring and feedback. PDF report generation.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from typing import Dict
import uuid
import os
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, EMERGENT_LLM_KEY
from utils.pdf_v15_filename import build_pdf_v15_filename

router = APIRouter(prefix="/mock-interview")
logger = logging.getLogger("routes.mock_interview")


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise RuntimeError(f"pdf-v15-enforcement-failed:{context}:{mode}")
    return themed

# Active LLM chat sessions: session_id -> LlmChat
_active_chats: Dict[str, LlmChat] = {}

PERSONAS = {
    "technical": {
        "name": "Alex Chen",
        "role": "Senior Technical Interviewer",
        "icon": "code-slash",
        "color": "#3B82F6",
        "system": """You are Alex Chen, a senior technical interviewer at a top tech company. You conduct rigorous but fair technical interviews.

RULES:
- Ask ONE question at a time. Wait for the candidate's answer before proceeding.
- Start with a brief introduction and ask what role they're interviewing for.
- Cover: data structures, algorithms, system design, coding patterns, and role-specific technical topics.
- After each answer, briefly evaluate it (1-2 sentences) then ask the next question.
- Adjust difficulty based on the candidate's level.
- After 5-8 questions, summarize performance.
- Be encouraging but honest. Note areas for improvement.
- Format: Use markdown for code blocks if discussing code.""",
    },
    "behavioral": {
        "name": "Sarah Mitchell",
        "role": "Behavioral Interview Coach",
        "icon": "people",
        "color": "#8B5CF6",
        "system": """You are Sarah Mitchell, an experienced behavioral interview specialist. You evaluate soft skills, leadership, and cultural fit.

RULES:
- Ask ONE question at a time using the STAR method framework.
- Start with a warm introduction and ask about their target role/company.
- Cover: leadership, teamwork, conflict resolution, problem-solving, adaptability, and communication.
- After each answer, provide brief feedback on their STAR technique (1-2 sentences), then ask the next question.
- Look for specific examples, not generic answers.
- After 5-8 questions, provide a summary with strengths and areas to improve.
- Be supportive and constructive in your feedback.""",
    },
    "hr": {
        "name": "David Park",
        "role": "HR Screening Specialist",
        "icon": "briefcase",
        "color": "#10B981",
        "system": """You are David Park, a professional HR screening interviewer. You assess culture fit, motivation, and career alignment.

RULES:
- Ask ONE question at a time.
- Start with a friendly introduction and ask about their background.
- Cover: career goals, salary expectations, availability, work preferences, why this company, strengths/weaknesses, and culture fit.
- After each answer, acknowledge their response briefly, then move to the next topic.
- Be professional, warm, and informative about what companies typically look for.
- After 5-8 questions, provide a summary of how they presented themselves.
- Give tips on how to better answer HR screening questions.""",
    },
    "case": {
        "name": "Maria Torres",
        "role": "Case Interview Expert",
        "icon": "analytics",
        "color": "#F59E0B",
        "system": """You are Maria Torres, a management consulting case interview expert. You present business cases and evaluate analytical thinking.

RULES:
- Ask ONE question at a time.
- Start by presenting a business case scenario (e.g., market entry, profitability, M&A).
- Guide the candidate through the case with follow-up questions.
- Evaluate their framework, structure, quantitative reasoning, and creativity.
- After each response, provide brief feedback and guide them deeper.
- After the case is complete (5-8 exchanges), give a detailed assessment.
- Be encouraging but push for structured thinking.""",
    },
}


@router.get("/personas")
async def list_personas(request: Request):
    """List available interview personas."""
    personas = []
    for pid, p in PERSONAS.items():
        personas.append(
            {
                "id": pid,
                "name": p["name"],
                "role": p["role"],
                "icon": p["icon"],
                "color": p["color"],
            }
        )
    return {"personas": personas}


@router.post("/start")
async def start_interview(request: Request):
    """Start a new mock interview session."""
    user = await require_auth(request)
    body = await request.json()
    persona_id = body.get("persona", "technical")
    job_role = body.get("job_role", "Software Engineer")

    if persona_id not in PERSONAS:
        raise HTTPException(status_code=400, detail=f"Invalid persona. Choose from: {list(PERSONAS.keys())}")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI service not configured")

    persona = PERSONAS[persona_id]
    session_id = f"mock_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    # Create LLM chat session
    system_msg = persona["system"] + f"\n\nThe candidate is interviewing for: {job_role}"
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_msg,
    ).with_model("openai", "gpt-4o")

    # Get the opening question
    opening = await chat.send_message(
        UserMessage(
            text=f"Start the interview. The candidate's name is {user.name}. Begin with your introduction and first question."
        )
    )
    opening_text = opening.text if hasattr(opening, "text") else str(opening)

    _active_chats[session_id] = chat

    # Save session to DB
    session = {
        "session_id": session_id,
        "user_id": user.user_id,
        "user_name": user.name,
        "persona_id": persona_id,
        "persona_name": persona["name"],
        "persona_role": persona["role"],
        "job_role": job_role,
        "messages": [{"role": "interviewer", "content": opening_text, "timestamp": now}],
        "scores": [],
        "status": "active",
        "question_count": 1,
        "created_at": now,
        "updated_at": now,
    }
    await db.mock_interviews.insert_one(session)
    session.pop("_id", None)

    return {"success": True, "session": session}


@router.post("/{session_id}/answer")
async def submit_answer(session_id: str, request: Request):
    """Submit an answer and get the next question with scoring."""
    user = await require_auth(request)
    body = await request.json()
    answer = body.get("answer", "").strip()

    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=400, detail="Session is no longer active")

    now = datetime.now(timezone.utc).isoformat()

    # Get or recreate chat
    chat = _active_chats.get(session_id)
    if not chat:
        persona = PERSONAS.get(session["persona_id"], PERSONAS["technical"])
        system_msg = persona["system"] + f"\n\nThe candidate is interviewing for: {session['job_role']}"
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_msg,
        ).with_model("openai", "gpt-4o")
        # Replay history
        for msg in session["messages"]:
            if msg["role"] == "interviewer":
                pass  # System already has context
            elif msg["role"] == "candidate":
                pass  # Will be part of conversation flow
        _active_chats[session_id] = chat

    prompt = f"""The candidate answered: "{answer}"

Provide:
1. Brief evaluation of their answer (2-3 sentences). Rate it: Excellent/Good/Needs Improvement.
2. Then ask your next interview question.

Format your response as:
**Feedback:** [your evaluation]
**Rating:** [Excellent/Good/Needs Improvement]

**Next Question:** [your next question]"""

    response = await chat.send_message(UserMessage(text=prompt))
    response_text = response.text if hasattr(response, "text") else str(response)

    # Parse rating
    rating = "Good"
    for r in ["Excellent", "Needs Improvement"]:
        if r.lower() in response_text.lower():
            rating = r
            break

    score_map = {"Excellent": 9, "Good": 7, "Needs Improvement": 4}
    score = score_map.get(rating, 7)

    # Update session
    new_messages = [
        {"role": "candidate", "content": answer, "timestamp": now},
        {"role": "interviewer", "content": response_text, "timestamp": now, "rating": rating, "score": score},
    ]
    q_count = session["question_count"] + 1

    await db.mock_interviews.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"$each": new_messages}, "scores": score},
            "$set": {"question_count": q_count, "updated_at": now},
        },
    )

    return {
        "success": True,
        "response": response_text,
        "rating": rating,
        "score": score,
        "question_count": q_count,
    }


@router.post("/{session_id}/end")
async def end_interview(session_id: str, request: Request):
    """End interview session and get final feedback."""
    user = await require_auth(request)

    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc).isoformat()

    # Get final feedback from AI
    chat = _active_chats.get(session_id)
    if chat:
        final = await chat.send_message(
            UserMessage(
                text="The interview is now complete. Provide a comprehensive final assessment including: 1) Overall performance rating (out of 10), 2) Top 3 strengths, 3) Top 3 areas for improvement, 4) Specific tips for their next interview. Be constructive and encouraging."
            )
        )
        final_text = final.text if hasattr(final, "text") else str(final)
        _active_chats.pop(session_id, None)
    else:
        final_text = "Session feedback unavailable. Please start a new interview for detailed feedback."

    scores = session.get("scores", [])
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    await db.mock_interviews.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": "completed",
                "final_feedback": final_text,
                "average_score": avg_score,
                "updated_at": now,
                "completed_at": now,
            },
            "$push": {"messages": {"role": "interviewer", "content": final_text, "timestamp": now, "is_final": True}},
        },
    )

    # Send coaching session recap email
    import asyncio
    asyncio.ensure_future(_send_coaching_recap_email(user, session, final_text, avg_score))

    return {
        "success": True,
        "final_feedback": final_text,
        "average_score": avg_score,
        "question_count": session["question_count"],
    }


async def _send_coaching_recap_email(user, session, final_text: str, avg_score: float):
    """Send coaching session recap email after interview/coaching session ends."""
    try:
        from utils.email_service import send_catalog_template, is_email_configured
        if not is_email_configured():
            return
        # Extract takeaways from AI feedback
        lines = [line.strip() for line in final_text.split("\n") if line.strip() and len(line.strip()) > 10]
        takeaways = lines[:3] if lines else ["Review your session feedback for detailed insights"]
        actions = ["Practice areas identified for improvement", "Schedule your next mock interview"]

        await send_catalog_template(
            recipient_email=user.email,
            template_key="coaching_session_recap",
            recipient_name=user.name or user.email,
            user_name=user.name or user.email,
            session_topic=session.get("job_role", session.get("role", "Mock Interview")),
            key_takeaways=takeaways,
            action_items=actions,
            session_duration=f"{session.get('question_count', 0)} questions",
        )
    except Exception as e:
        logger.warning(f"Coaching recap email failed: {e}")


@router.get("/sessions")
async def list_sessions(request: Request):
    """List user's mock interview sessions."""
    user = await require_auth(request)
    sessions = (
        await db.mock_interviews.find(
            {"user_id": user.user_id},
            {"_id": 0, "messages": 0, "final_feedback": 0},
        )
        .sort("created_at", -1)
        .to_list(30)
    )
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """Get full session details including messages."""
    user = await require_auth(request)
    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a mock interview session."""
    user = await require_auth(request)
    result = await db.mock_interviews.delete_one({"session_id": session_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    _active_chats.pop(session_id, None)
    return {"success": True}


REPORTS_DIR = "/app/backend/media/reports"
os.makedirs(REPORTS_DIR, exist_ok=True)


@router.post("/{session_id}/report")
async def generate_report(session_id: str, request: Request):
    """Generate a comprehensive PDF report for a completed interview."""
    user = await require_auth(request)

    session = await db.mock_interviews.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Interview must be completed first")

    # Generate AI analysis
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI service not configured")

    messages = session.get("messages", [])
    qa_pairs = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "candidate":
            interviewer_resp = (
                messages[i + 1] if i + 1 < len(messages) and messages[i + 1].get("role") == "interviewer" else None
            )
            qa_pairs.append(
                {
                    "answer": msg["content"],
                    "feedback": interviewer_resp["content"] if interviewer_resp else "",
                    "rating": interviewer_resp.get("rating", "N/A") if interviewer_resp else "N/A",
                    "score": interviewer_resp.get("score", 0) if interviewer_resp else 0,
                }
            )

    qa_text = "\n".join(
        [
            f"Q{i + 1} Answer: {qa['answer']}\nFeedback: {qa['feedback']}\nRating: {qa['rating']}"
            for i, qa in enumerate(qa_pairs)
        ]
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"report-{uuid.uuid4().hex[:8]}",
        system_message="You are an expert interview performance analyst. Generate structured interview reports.",
    ).with_model("openai", "gpt-4o")

    analysis_prompt = f"""Analyze this mock interview and provide a structured report:

Candidate: {session.get("user_name", "Unknown")}
Role: {session.get("job_role", "N/A")}
Interviewer: {session.get("persona_name", "N/A")} ({session.get("persona_role", "")})
Questions Asked: {session.get("question_count", 0)}
Average Score: {session.get("average_score", 0)}/10

Q&A Transcript:
{qa_text}

Provide your analysis in this EXACT format (use these headers):
EXECUTIVE_SUMMARY: (2-3 sentences overview)
OVERALL_SCORE: (number out of 10)
STRENGTHS: (3-5 bullet points, one per line starting with -)
IMPROVEMENTS: (3-5 bullet points, one per line starting with -)
TIPS: (3-5 actionable tips, one per line starting with -)
READINESS: (one of: Not Ready / Needs Practice / Almost Ready / Interview Ready)"""

    response = await chat.send_message(UserMessage(text=analysis_prompt))
    analysis = response.text if hasattr(response, "text") else str(response)

    # Parse AI analysis
    sections = _parse_report(analysis)

    # Generate PDF
    pdf_path = os.path.join(REPORTS_DIR, f"{session_id}_report.pdf")
    _build_pdf(pdf_path, session, qa_pairs, sections)

    # Save report metadata
    now = datetime.now(timezone.utc).isoformat()
    report_data = {
        "session_id": session_id,
        "user_id": user.user_id,
        "analysis": sections,
        "pdf_path": pdf_path,
        "generated_at": now,
    }
    await db.interview_reports.update_one(
        {"session_id": session_id},
        {"$set": report_data},
        upsert=True,
    )

    return {
        "success": True,
        "report": {
            "session_id": session_id,
            "executive_summary": sections.get("executive_summary", ""),
            "overall_score": sections.get("overall_score", ""),
            "strengths": sections.get("strengths", []),
            "improvements": sections.get("improvements", []),
            "tips": sections.get("tips", []),
            "readiness": sections.get("readiness", ""),
            "generated_at": now,
        },
    }


@router.get("/{session_id}/report/download")
async def download_report(session_id: str, request: Request, token: str = None):
    """Download the generated PDF report."""
    # Support token via query param for browser downloads
    if token and not request.headers.get("Authorization"):
        request._headers = {**dict(request.headers), "authorization": f"Bearer {token}"}
    user = await require_auth(request)

    report = await db.interview_reports.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet")

    pdf_path = report.get("pdf_path", "")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=build_pdf_v15_filename("interview-report", session_id),
    )


@router.get("/{session_id}/report")
async def get_report(session_id: str, request: Request):
    """Get the report analysis (without PDF)."""
    user = await require_auth(request)
    report = await db.interview_reports.find_one({"session_id": session_id, "user_id": user.user_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    report.pop("pdf_path", None)
    return report


def _parse_report(text: str) -> dict:
    """Parse AI analysis into structured sections."""
    sections = {
        "executive_summary": "",
        "overall_score": "",
        "strengths": [],
        "improvements": [],
        "tips": [],
        "readiness": "",
    }
    current = None
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if "EXECUTIVE_SUMMARY:" in upper:
            current = "executive_summary"
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            if val:
                sections["executive_summary"] = val
        elif "OVERALL_SCORE:" in upper:
            current = "overall_score"
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            sections["overall_score"] = val
        elif "STRENGTHS:" in upper:
            current = "strengths"
        elif "IMPROVEMENTS:" in upper:
            current = "improvements"
        elif "TIPS:" in upper:
            current = "tips"
        elif "READINESS:" in upper:
            current = "readiness"
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            sections["readiness"] = val
        elif current == "executive_summary":
            sections["executive_summary"] += " " + line
        elif current in ("strengths", "improvements", "tips"):
            item = line.lstrip("- ").strip()
            if item:
                sections[current].append(item)
        elif current == "readiness" and not sections["readiness"]:
            sections["readiness"] = line
    return sections


def _build_pdf(path: str, session: dict, qa_pairs: list, sections: dict):
    """Build a professional PDF report using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    doc = SimpleDocTemplate(
        path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "Title2", parent=styles["Title"], fontSize=22, textColor=HexColor("#1E293B"), spaceAfter=4 * mm
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=11, textColor=HexColor("#64748B"), spaceAfter=8 * mm
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=HexColor("#3B82F6"),
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=10, textColor=HexColor("#334155"), leading=14, spaceAfter=2 * mm
    )
    bullet_style = ParagraphStyle(
        "Bullet", parent=body_style, leftIndent=10 * mm, bulletIndent=5 * mm, spaceAfter=1.5 * mm
    )
    score_style = ParagraphStyle(
        "Score",
        parent=styles["Normal"],
        fontSize=28,
        textColor=HexColor("#3B82F6"),
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )
    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontSize=12,
        textColor=HexColor("#10B981"),
        alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )

    elements = []

    # Header
    elements.append(Paragraph("Interview Performance Report", title_style))
    elements.append(
        Paragraph(
            f"{session.get('user_name', 'Candidate')} | {session.get('job_role', 'N/A')} | "
            f"Interviewer: {session.get('persona_name', 'AI')} | "
            f"{session.get('completed_at', session.get('created_at', ''))[:10]}",
            subtitle_style,
        )
    )

    # Score
    elements.append(Paragraph("Overall Score", h2_style))
    score_text = sections.get("overall_score", str(session.get("average_score", "N/A")))
    elements.append(Paragraph(f"<b>{score_text}</b> / 10", score_style))
    readiness = sections.get("readiness", "N/A")
    elements.append(Paragraph(f"Readiness: <b>{readiness}</b>", badge_style))

    # Executive Summary
    elements.append(Paragraph("Executive Summary", h2_style))
    elements.append(Paragraph(sections.get("executive_summary", "No summary available."), body_style))

    # Strengths
    if sections.get("strengths"):
        elements.append(Paragraph("Key Strengths", h2_style))
        for s in sections["strengths"]:
            elements.append(Paragraph(f"<bullet>&bull;</bullet> {s}", bullet_style))

    # Areas for Improvement
    if sections.get("improvements"):
        elements.append(Paragraph("Areas for Improvement", h2_style))
        for s in sections["improvements"]:
            elements.append(Paragraph(f"<bullet>&bull;</bullet> {s}", bullet_style))

    # Q&A Breakdown
    if qa_pairs:
        elements.append(Paragraph("Question-by-Question Breakdown", h2_style))
        for i, qa in enumerate(qa_pairs):
            rating_color = (
                "#10B981"
                if qa["rating"] == "Excellent"
                else "#F59E0B"
                if qa["rating"] == "Needs Improvement"
                else "#3B82F6"
            )
            elements.append(
                Paragraph(
                    f"<b>Q{i + 1}</b> | Rating: <font color='{rating_color}'><b>{qa['rating']}</b></font> | Score: {qa['score']}/10",
                    ParagraphStyle(
                        "QH", parent=body_style, fontSize=10, textColor=HexColor("#1E293B"), spaceBefore=3 * mm
                    ),
                )
            )
            answer_text = qa["answer"][:300] + ("..." if len(qa["answer"]) > 300 else "")
            elements.append(
                Paragraph(
                    f"<i>Your answer:</i> {answer_text}",
                    ParagraphStyle(
                        "QA", parent=body_style, textColor=HexColor("#64748B"), fontSize=9, leftIndent=5 * mm
                    ),
                )
            )
            elements.append(Spacer(1, 2 * mm))

    # Actionable Tips
    if sections.get("tips"):
        elements.append(Paragraph("Actionable Tips for Next Interview", h2_style))
        for i, tip in enumerate(sections["tips"]):
            elements.append(Paragraph(f"<b>{i + 1}.</b> {tip}", bullet_style))

    # Footer
    elements.append(Spacer(1, 10 * mm))
    elements.append(
        Paragraph(
            f"Generated by RealAICoach | {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
            ParagraphStyle(
                "Footer", parent=styles["Normal"], fontSize=8, textColor=HexColor("#94A3B8"), alignment=TA_CENTER
            ),
        )
    )

    doc.build(elements)
    raw_pdf = open(path, "rb").read()
    composed_pdf = compose_pdf_v15_helper_layout(
        raw_pdf,
        title="Interview Performance Report",
        subtitle="Mock interview evaluation artifact",
        right_primary=f"Candidate: {session.get('user_name', 'N/A')[:20]}",
        right_secondary=f"Role: {session.get('job_role', 'N/A')[:20]}",
        badge_text="INTERVIEW EVALUATION",
        badge_status="INFO",
        footer_text="RealAICoach Interview Practice • Enterprise profile",
        summary_title="Performance Snapshot",
        summary_rows=[
            ("Overall Score", sections.get("overall_score", str(session.get("average_score", "N/A")))),
            ("Readiness", sections.get("readiness", "N/A")),
            ("Questions", str(len(qa_pairs))),
        ],
        callout_title="Coaching Guidance",
        callout_subtitle="Actionability",
        callout_detail=(sections.get("executive_summary", "No summary available.") or "No summary available.")[:120],
        callout_status="INFO",
    )
    with open(path, "wb") as f:
        f.write(_enforce_pdf_v15_enterprise(composed_pdf, f"mock_interview_report_{session.get('session_id', 'unknown')}"))
