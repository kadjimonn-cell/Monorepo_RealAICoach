"""AI Interview Summary Generator + Candidate Experience Score.

Interview Summary:
- POST /api/interview-summary/{interview_id}/generate  Generate AI summary
- GET  /api/interview-summary/{interview_id}           Get summary

Candidate Experience:
- POST /api/candidate-experience/{interview_id}/rate   Candidate rates experience
- GET  /api/candidate-experience/employer/{employer_id} Employer experience score
- GET  /api/candidate-experience/rankings              Admin: employer experience rankings
- GET  /api/candidate-experience/my-ratings            Candidate: my submitted ratings
"""

from fastapi import APIRouter, HTTPException, Request, Response
from datetime import datetime, timezone, timedelta
import uuid
import os
import json
import logging
import io
import base64
import secrets
import textwrap

import httpx

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, require_admin, create_jwt_token
from middleware_pdf_policy import enforce_pdf_v14_bytes
from utils.email_service import send_catalog_template, is_email_configured
from utils.pdf_v15_filename import build_pdf_v15_filename

router = APIRouter()
logger = logging.getLogger("routes.interview_summary")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")


# ═══════════════════════════════════════════════════════════════
# AI INTERVIEW SUMMARY
# ═══════════════════════════════════════════════════════════════


@router.post("/interview-summary/{interview_id}/generate")
async def generate_summary(interview_id: str, request: Request):
    """Generate AI-powered post-interview summary."""
    user = await require_auth(request)

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Gather data for summary
    room = await db.interview_rooms.find_one({"interview_id": interview_id}, {"_id": 0})
    feedbacks = await db.interview_feedback.find({"interview_id": interview_id}, {"_id": 0}).to_list(10)
    activity = await db.interview_activity_log.find({"interview_id": interview_id}, {"_id": 0}).to_list(50)

    # Check if summary already exists
    existing = await db.interview_summaries.find_one({"interview_id": interview_id}, {"_id": 0})
    if existing:
        return {"summary": existing, "cached": True}

    # Build context
    context = {
        "job_title": interview.get("job_title", ""),
        "candidate_name": interview.get("candidate_name", ""),
        "employer_name": interview.get("employer_name", ""),
        "interview_type": interview.get("interview_type", ""),
        "status": interview.get("status", ""),
        "scheduled_date": interview.get("scheduled_date", ""),
        "duration_seconds": room.get("duration_seconds") if room else None,
        "chat_messages": room.get("chat_messages", []) if room else [],
        "feedback": feedbacks,
        "activity_log": [{"action": a.get("action"), "details": a.get("details", "")} for a in activity],
        "notes": interview.get("notes", ""),
    }

    # Generate AI summary
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"summary-{interview_id}",
            system_message="You are a professional HR assistant generating post-interview summary reports. Respond in valid JSON format only.",
        ).with_model("openai", "gpt-5.2")
        prompt = f"""Generate a professional post-interview summary report based on this data:

Interview Context:
{json.dumps(context, indent=2, default=str)}

Create a comprehensive summary as JSON:
{{
  "executive_summary": "2-3 sentence overview of the interview",
  "key_discussion_points": ["point1", "point2", "point3"],
  "candidate_strengths": ["strength1", "strength2"],
  "candidate_weaknesses": ["area1", "area2"],
  "technical_assessment": "Brief technical evaluation based on available data",
  "communication_assessment": "How well the candidate communicated",
  "hiring_recommendation": "strong_hire | hire | maybe | pass",
  "confidence_level": 75,
  "next_steps": ["step1", "step2"],
  "interviewer_notes_summary": "Summary of any interviewer feedback/notes"
}}"""

        resp = await chat.send_message(UserMessage(text=prompt))
        resp_text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            clean_text = resp_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            ai_summary = json.loads(clean_text.strip())
        except json.JSONDecodeError:
            ai_summary = {
                "executive_summary": resp_text[:500],
                "key_discussion_points": [],
                "candidate_strengths": [],
                "candidate_weaknesses": [],
                "hiring_recommendation": "maybe",
                "confidence_level": 50,
                "next_steps": ["Review interview manually"],
            }
    except Exception as e:
        logger.warning(f"AI summary generation error: {e}")
        ai_summary = {
            "executive_summary": f"Interview for {context['job_title']} with {context['candidate_name']}. Status: {context['status']}.",
            "key_discussion_points": [],
            "candidate_strengths": [],
            "candidate_weaknesses": [],
            "hiring_recommendation": "maybe",
            "confidence_level": 0,
            "next_steps": ["AI summary generation failed — review manually"],
        }

    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "summary_id": f"sum_{uuid.uuid4().hex[:10]}",
        "interview_id": interview_id,
        "job_title": context["job_title"],
        "candidate_name": context["candidate_name"],
        "employer_name": context["employer_name"],
        "interview_type": context["interview_type"],
        "duration_seconds": context["duration_seconds"],
        "chat_message_count": len(context["chat_messages"]),
        "feedback_count": len(feedbacks),
        **ai_summary,
        "generated_by": uid,
        "generated_at": now,
    }

    await db.interview_summaries.insert_one({**summary})
    return {"summary": summary, "cached": False}


@router.get("/interview-summary/{interview_id}")
async def get_summary(interview_id: str, request: Request):
    """Get interview summary."""
    await require_auth(request)

    summary = await db.interview_summaries.find_one({"interview_id": interview_id}, {"_id": 0})
    if not summary:
        return {"summary": None, "message": "No summary generated yet"}

    return {"summary": summary}


# ═══════════════════════════════════════════════════════════════
# CANDIDATE EXPERIENCE SCORE
# ═══════════════════════════════════════════════════════════════


@router.post("/candidate-experience/{interview_id}/rate")
async def rate_experience(interview_id: str, request: Request):
    """Candidate rates their interview experience."""
    user = await require_auth(request)
    body = await request.json()

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if user.user_id != interview.get("candidate_id") and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only the candidate can rate this experience")

    overall = body.get("overall_rating", 0)
    if not (1 <= overall <= 5):
        raise HTTPException(status_code=400, detail="overall_rating must be 1-5")

    existing = await db.candidate_experience.find_one(
        {"interview_id": interview_id, "candidate_id": user.user_id}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already rated this interview")

    now = datetime.now(timezone.utc).isoformat()
    rating = {
        "rating_id": f"cxr_{uuid.uuid4().hex[:10]}",
        "interview_id": interview_id,
        "candidate_id": user.user_id,
        "candidate_name": user.name,
        "employer_id": interview.get("employer_id", ""),
        "employer_name": interview.get("employer_name", ""),
        "job_title": interview.get("job_title", ""),
        "overall_rating": overall,
        "communication_rating": body.get("communication_rating", overall),
        "professionalism_rating": body.get("professionalism_rating", overall),
        "timeliness_rating": body.get("timeliness_rating", overall),
        "feedback_quality_rating": body.get("feedback_quality_rating", overall),
        "would_recommend": body.get("would_recommend", overall >= 4),
        "comment": body.get("comment", ""),
        "created_at": now,
    }

    await db.candidate_experience.insert_one({**rating})
    return {"success": True, "rating": rating}


# ═══════════════════════════════════════════════════════════════
# VIDEO INTERVIEW PERFORMANCE + BEHAVIORAL ANALYTICS
# ═══════════════════════════════════════════════════════════════


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 3) if den else 0.0


def _render_interview_performance_pdf(report: dict) -> bytes:
    """Render candidate interview performance PDF and enforce v1.4."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pdfVersion=(1, 4))
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Interview Performance Summary")
    y -= 24

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Interview ID: {report.get('interview_id', '')}")
    y -= 14
    c.drawString(40, y, f"Generated: {report.get('generated_at', '')}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Scorecard")
    y -= 16

    c.setFont("Helvetica", 11)
    lines = [
        f"Communication Score: {report.get('communication_score', 0)}/100",
        f"Confidence Score: {report.get('confidence_score', 0)}/100",
        f"Relevance Score: {report.get('relevance_score', 0)}/100",
        f"Overall Score: {report.get('overall_score', 0)}/100",
        f"Talk-time Balance Estimate: {report.get('talk_time_balance_est', 0)}%",
        f"Duration: {report.get('duration_minutes', 0)} minutes",
        f"Recommendation: {str(report.get('hiring_recommendation', '')).replace('_', ' ').title()}",
    ]
    for line in lines:
        c.drawString(44, y, line)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Behavioral Insights")
    y -= 16
    c.setFont("Helvetica", 10)
    for insight in (report.get("behavioral_insights") or [])[:10]:
        text = f"- {insight}"
        for chunk in [text[i : i + 112] for i in range(0, len(text), 112)]:
            c.drawString(44, y, chunk)
            y -= 12
            if y < 72:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 10)

    c.showPage()
    c.save()
    raw = buf.getvalue()
    normalized, _policy_mode = enforce_pdf_v14_bytes(raw)
    return normalized


def _render_interview_content_pdf(content: dict) -> bytes:
    """Render interview report in global PDF v15 enterprise theme."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from services.pdf_v15_theme import PALETTE, draw_page_chrome, draw_kv_card, draw_callout_card

    generated_at = datetime.now(timezone.utc).isoformat()
    interview_id = str(content.get("interview_id") or "")
    status_now = str(content.get("status") or "in_progress").upper()

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4, pdfVersion=(1, 4))
    width, height = A4
    margin_x = 40
    content_w = width - (2 * margin_x)
    page_no = 1
    y = 0.0

    def _draw_page() -> None:
        nonlocal y
        y = draw_page_chrome(
            pdf,
            width=width,
            height=height,
            margin_x=margin_x,
            page_no=page_no,
            title="RealAICoach Interview Intelligence",
            subtitle="Interview Replay & Evaluation  •  Enterprise Artifact",
            right_primary="noreply@realaicoach.app",
            right_secondary=generated_at[:19].replace("T", " "),
            badge_text=f"[INTERVIEW REPLAY • {status_now}] id={interview_id}",
            badge_status="PASS" if status_now in {"COMPLETED", "VERIFIED"} else "WARNING" if status_now in {"IN_PROGRESS", "SCHEDULED"} else "FAIL",
            footer_text="RealAICoach  •  Interview Intelligence",
        )

    def _new_page() -> None:
        nonlocal page_no
        pdf.showPage()
        page_no += 1
        _draw_page()

    def _ensure_space(points_needed: float) -> None:
        nonlocal y
        if y - points_needed < 52:
            _new_page()

    def _draw_text_block_card(title: str, lines: list[str], tone) -> None:
        nonlocal y
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(textwrap.wrap(str(line), width=98) or [""])
        wrapped = wrapped or ["No details available."]
        body_h = 15 + (len(wrapped) * 10.5)
        header_h = 17
        total_h = header_h + 4 + body_h + 10
        _ensure_space(total_h)

        pdf.setFillColor(tone)
        pdf.roundRect(margin_x, y - header_h, content_w, header_h, 5, stroke=0, fill=1)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(margin_x + 8, y - 11.5, title)

        body_top = y - header_h - 4
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setStrokeColor(PALETTE["border_soft"])
        pdf.roundRect(margin_x, body_top - body_h, content_w, body_h, 7, stroke=1, fill=1)
        cursor = body_top - 11
        for line in wrapped:
            pdf.setFillColor(PALETTE["slate"])
            pdf.setFont("Helvetica", 8.8)
            pdf.drawString(margin_x + 8, cursor, line)
            cursor -= 10.5
        y -= total_h

    _draw_page()
    _ensure_space(75)
    y = draw_callout_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="Interview Replay & Evaluation Report",
        subtitle=f"Interview ID {interview_id} • Generated {generated_at}",
        detail=f"Status: {str(content.get('status') or 'in_progress').replace('_', ' ').title()}",
        status="PASS" if status_now in {"COMPLETED", "VERIFIED"} else "WARNING",
    )

    _ensure_space(140)
    y = draw_kv_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="Interview Context",
        rows=[
            ("Job Title", content.get("job_title") or "—"),
            ("Candidate", content.get("candidate_name") or "—"),
            ("Interviewer", content.get("interviewer_name") or content.get("employer_name") or "—"),
            ("Status", str(content.get("status") or "in_progress").replace("_", " ").title()),
            ("Scheduled Start", content.get("scheduled_start") or "—"),
            ("Duration", f"{content.get('duration_minutes') or 0} minutes"),
        ],
        tone=PALETTE["primary"],
    )

    perf = content.get("performance") or {}
    summary = content.get("summary") or {}
    _ensure_space(120)
    y = draw_kv_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="Performance Snapshot",
        rows=[
            ("Overall Score", perf.get("overall_score") or summary.get("overall_score") or "N/A"),
            ("Communication", perf.get("communication_score") or "N/A"),
            ("Relevance", perf.get("relevance_score") or "N/A"),
            (
                "Recommendation",
                str(perf.get("hiring_recommendation") or summary.get("recommendation") or "N/A").replace("_", " ").title(),
            ),
        ],
        tone=PALETTE["teal"],
    )

    timeline_events = content.get("timeline_events") or []
    timeline_lines = []
    if timeline_events:
        for event in timeline_events[:40]:
            timeline_lines.append(
                f"• {event.get('at') or 't+0'} | {str(event.get('event_type') or 'event').replace('_', ' ').title()} — {event.get('message') or ''}"
            )
    else:
        timeline_lines.append("No timeline events recorded for this interview.")
    _draw_text_block_card("Replay Timeline Highlights", timeline_lines, PALETTE["indigo"])

    annotations = content.get("annotations") or []
    annotation_lines = []
    if annotations:
        for ann in annotations[:40]:
            annotation_lines.append(
                f"• T+{ann.get('second_offset', 0)}s [{str(ann.get('severity') or 'low').upper()}] {str(ann.get('category') or 'general').replace('_', ' ').title()} — {ann.get('note') or ''}"
            )
    else:
        annotation_lines.append("No evaluator annotations available.")
    _draw_text_block_card("Evaluator Annotations", annotation_lines, PALETTE["primary"])

    notes = str(content.get("notes") or "").strip()
    if notes:
        _draw_text_block_card("Interview Notes", [notes], PALETTE["teal"])

    _ensure_space(40)
    pdf.setFillColor(PALETTE["slate_soft"])
    pdf.setStrokeColor(PALETTE["border_soft"])
    pdf.roundRect(margin_x, y - 30, content_w, 24, 6, stroke=1, fill=1)
    pdf.setFillColor(PALETTE["slate"])
    pdf.setFont("Helvetica-Oblique", 8.5)
    pdf.drawString(margin_x + 8, y - 20, "This PDF follows the RealAICoach enterprise design system.")

    pdf.save()
    raw = buf.getvalue()
    normalized, _policy_mode = enforce_pdf_v14_bytes(raw)
    return normalized


def _extract_request_session_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return (request.cookies.get("session_token") or "").strip()


@router.post("/interview-performance/{interview_id}/analyze")
async def analyze_interview_performance(interview_id: str, request: Request):
    """Generate AI interview performance scoring + behavioral analytics report."""
    user = await require_auth(request)

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    room = await db.interview_rooms.find_one({"interview_id": interview_id}, {"_id": 0})
    feedback = await db.interview_feedback.find_one({"interview_id": interview_id}, {"_id": 0})

    if not room:
        raise HTTPException(status_code=400, detail="Interview room data missing")

    chat_messages = room.get("chat_messages", [])
    duration_seconds = room.get("duration_seconds") or 0
    duration_minutes = round(duration_seconds / 60, 1) if duration_seconds else 0

    by_speaker = {}
    for m in chat_messages:
        speaker = m.get("user_id") or "unknown"
        by_speaker[speaker] = by_speaker.get(speaker, 0) + 1

    candidate_msgs = by_speaker.get(interview.get("candidate_id"), 0)
    employer_msgs = by_speaker.get(interview.get("employer_id"), 0)
    total_msgs = max(1, candidate_msgs + employer_msgs)
    talk_time_balance_est = round(_safe_div(min(candidate_msgs, employer_msgs), max(candidate_msgs, employer_msgs, 1)) * 100, 1)

    communication_score = int(
        max(
            0,
            min(
                100,
                feedback.get("communication_score") if feedback else 45 + min(25, total_msgs * 3),
            ),
        )
    )
    confidence_score = int(
        max(
            0,
            min(
                100,
                (feedback.get("overall_rating", 3) * 20) if feedback else 50 + min(20, int(duration_minutes // 5) * 5),
            ),
        )
    )
    relevance_score = int(
        max(
            0,
            min(
                100,
                feedback.get("technical_score") if feedback and feedback.get("technical_score") is not None else 48 + min(22, total_msgs * 2),
            ),
        )
    )

    overall_score = int(round((communication_score * 0.35) + (confidence_score * 0.25) + (relevance_score * 0.40)))
    recommendation = "strong_hire" if overall_score >= 80 else "hire" if overall_score >= 65 else "maybe" if overall_score >= 50 else "pass"

    behavioral_insights = [
        f"Engagement level estimated from {total_msgs} chat interactions.",
        f"Talk-time balance estimate: {talk_time_balance_est}%.",
        f"Interview duration: {duration_minutes} minutes.",
    ]

    ai_summary = None
    if EMERGENT_KEY:
        ai_prompt_payload = {
            "job_title": interview.get("job_title"),
            "interview_type": interview.get("interview_type"),
            "duration_minutes": duration_minutes,
            "candidate_messages": candidate_msgs,
            "employer_messages": employer_msgs,
            "computed_scores": {
                "communication": communication_score,
                "confidence": confidence_score,
                "relevance": relevance_score,
                "overall": overall_score,
            },
            "feedback": feedback or {},
        }
        prompt = (
            "Return strict JSON with keys: behavioral_insights(array), interview_performance_summary(string), "
            "hiring_recommendation(string), confidence_level(number). Use this payload: "
            + json.dumps(ai_prompt_payload)
        )
        try:
            chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"interview-performance-{interview_id}",
                system_message="You are an enterprise interview performance analyst. Return JSON only.",
            ).with_model("openai", "gpt-5.2")
            raw = await chat.send_message(UserMessage(text=prompt))
            raw_text = raw.text if hasattr(raw, "text") else str(raw)
            clean = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
            ai_summary = json.loads(clean)
            if isinstance(ai_summary, dict) and ai_summary.get("behavioral_insights"):
                behavioral_insights = ai_summary.get("behavioral_insights")
                recommendation = ai_summary.get("hiring_recommendation", recommendation)
        except Exception as e:
            logger.warning(f"Interview AI performance analysis failed: {e}")

    now = datetime.now(timezone.utc).isoformat()
    report = {
        "report_id": f"ipr_{uuid.uuid4().hex[:10]}",
        "interview_id": interview_id,
        "candidate_id": interview.get("candidate_id"),
        "employer_id": interview.get("employer_id"),
        "job_title": interview.get("job_title", ""),
        "communication_score": communication_score,
        "confidence_score": confidence_score,
        "relevance_score": relevance_score,
        "overall_score": overall_score,
        "talk_time_balance_est": talk_time_balance_est,
        "duration_minutes": duration_minutes,
        "behavioral_insights": behavioral_insights,
        "hiring_recommendation": recommendation,
        "ai_summary": ai_summary,
        "generated_by": uid,
        "generated_at": now,
    }

    await db.interview_performance_reports.update_one(
        {"interview_id": interview_id},
        {"$set": report, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {"success": True, "report": report}


@router.get("/interview-performance/{interview_id}")
async def get_interview_performance(interview_id: str, request: Request):
    """Get latest interview performance report."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    report = await db.interview_performance_reports.find_one({"interview_id": interview_id}, {"_id": 0})
    return {"report": report}


@router.get("/interview-performance/{interview_id}/export/pdf")
async def export_interview_performance_pdf(interview_id: str, request: Request):
    """Download interview performance summary PDF (policy-enforced v1.4)."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    report = await db.interview_performance_reports.find_one({"interview_id": interview_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Performance report not found. Run analysis first.")

    pdf_bytes = _render_interview_performance_pdf(report)
    filename = build_pdf_v15_filename("interview-performance", interview_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.post("/interview-performance/{interview_id}/email-admin-verification")
async def email_admin_interview_performance_verification(interview_id: str, request: Request):
    """Send interview performance PDF v1.4 attachment to all admins for verification."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    report = await db.interview_performance_reports.find_one({"interview_id": interview_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Performance report not found. Run analysis first.")

    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service is not configured")

    pdf_bytes = _render_interview_performance_pdf(report)
    attachment = {
        "filename": build_pdf_v15_filename("interview-performance", interview_id),
        "content": base64.b64encode(pdf_bytes).decode("utf-8"),
        "content_type": "application/pdf",
    }

    admins = await db.users.find({"is_admin": True, "email": {"$exists": True, "$ne": ""}}, {"_id": 0, "email": 1, "name": 1}).to_list(50)
    if not admins:
        raise HTTPException(status_code=404, detail="No admin recipients configured")

    summary_text = (
        f"Candidate {report.get('candidate_id')} | Role {report.get('job_title')} | "
        f"Overall {report.get('overall_score', 0)}/100 | Recommendation {report.get('hiring_recommendation', '')}"
    )

    sent = 0
    failed = []
    for admin in admins:
        res = await send_catalog_template(
            recipient_email=admin.get("email"),
            template_key="employer_notification_v7",
            recipient_name=admin.get("name") or "Admin",
            event_type="interview_performance_verification",
            summary=summary_text,
            attachments=[attachment],
        )
        if res.get("success"):
            sent += 1
        else:
            failed.append({"email": admin.get("email"), "error": res.get("error", "unknown")})

    await db.interview_performance_email_log.insert_one(
        {
            "event_id": f"ipe_{uuid.uuid4().hex[:12]}",
            "interview_id": interview_id,
            "triggered_by": uid,
            "sent_count": sent,
            "failed": failed,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "attachment": {
                "filename": attachment["filename"],
                "content_type": attachment["content_type"],
                "pdf_header": pdf_bytes[:8].decode("latin1", errors="ignore"),
            },
        }
    )

    return {"success": True, "sent_count": sent, "failed": failed}


@router.get("/interview-content/{interview_id}/export/pdf")
async def export_interview_content_pdf(interview_id: str, request: Request):
    """Download interview content PDF (timeline + annotations) as v1.4."""
    logger.info(f"[interview-content-pdf] Request for interview_id={interview_id}")
    user = await require_auth(request)
    logger.info(f"[interview-content-pdf] User authenticated: {user.user_id}, is_admin={user.is_admin}")
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    logger.info(f"[interview-content-pdf] Interview found: {interview is not None}")
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    room = await db.interview_rooms.find_one({"interview_id": interview_id}, {"_id": 0})
    summary = await db.interview_summaries.find_one({"interview_id": interview_id}, {"_id": 0})
    performance = await db.interview_performance_reports.find_one({"interview_id": interview_id}, {"_id": 0})
    annotations = (
        await db.interview_replay_annotations.find({"interview_id": interview_id}, {"_id": 0})
        .sort("created_at", 1)
        .limit(200)
        .to_list(200)
    )

    timeline_events = []
    replay_events = (
        await db.interview_replay_events.find({"interview_id": interview_id}, {"_id": 0})
        .sort("created_at", 1)
        .limit(300)
        .to_list(300)
    )
    for ev in replay_events:
        timeline_events.append(
            {
                "at": ev.get("created_at", ""),
                "event_type": ev.get("event_type", "event"),
                "message": ev.get("message", ""),
            }
        )

    duration_seconds = int((room or {}).get("duration_seconds") or 0)
    content = {
        "interview_id": interview_id,
        "job_title": interview.get("job_title", ""),
        "candidate_name": interview.get("candidate_name", ""),
        "interviewer_name": interview.get("interviewer_name", ""),
        "employer_name": interview.get("employer_name", ""),
        "status": interview.get("status", ""),
        "scheduled_start": interview.get("scheduled_start", ""),
        "duration_minutes": duration_seconds // 60 if duration_seconds else int(interview.get("duration_minutes") or 0),
        "notes": interview.get("notes", ""),
        "timeline_events": timeline_events,
        "annotations": annotations,
        "summary": summary or {},
        "performance": performance or {},
    }
    pdf_bytes = _render_interview_content_pdf(content)
    filename = build_pdf_v15_filename("interview-content", interview_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.post("/admin/pdf-v15/email-verification-suite")
async def email_admin_pdf_v15_verification_suite(request: Request):
    """Send real user-facing PDF verification bundle to all admins."""
    admin = await require_admin(request)
    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service is not configured")

    admin_token = _extract_request_session_token(request)
    if not admin_token:
        raise HTTPException(status_code=401, detail="Missing admin session token")

    payment = await db.payments.find_one(
        {"user_id": {"$exists": True, "$ne": None}},
        {"_id": 0, "payment_id": 1, "id": 1, "user_id": 1},
        sort=[("created_at", -1)],
    )
    if not payment:
        raise HTTPException(status_code=404, detail="No payment record found for verification suite")

    payment_id = payment.get("payment_id") or payment.get("id")
    if not payment_id:
        raise HTTPException(status_code=404, detail="No payment identifier available")

    payment_user = await db.users.find_one(
        {"user_id": payment.get("user_id")},
        {"_id": 0, "user_id": 1, "email": 1, "token_version": 1},
    )
    if not payment_user:
        raise HTTPException(status_code=404, detail="Payment user not found")

    offer = await db.career_offers.find_one(
        {"offer_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "offer_id": 1, "role_title": 1},
        sort=[("updated_at", -1)],
    )
    if not offer:
        raise HTTPException(status_code=404, detail="No job offer found for verification suite")

    latest_gtec = await db.gtec_scan_c5_reports.find_one(
        {"task_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "task_id": 1},
        sort=[("generated_at", -1)],
    )
    if not latest_gtec:
        latest_gtec = await db.gtec_scan_v2_reports.find_one(
            {"task_id": {"$exists": True, "$ne": ""}},
            {"_id": 0, "task_id": 1},
            sort=[("generated_at", -1)],
        )
    if not latest_gtec:
        raise HTTPException(status_code=404, detail="No GTEC compliance report found for verification suite")

    interview = await db.interview_bookings.find_one(
        {"interview_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "interview_id": 1, "job_title": 1},
        sort=[("updated_at", -1)],
    )
    if not interview:
        raise HTTPException(status_code=404, detail="No interview record found for verification suite")

    user_token = create_jwt_token(
        payment_user.get("user_id"),
        payment_user.get("email") or "",
        int(payment_user.get("token_version", 0) or 0),
        20,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    await db.user_sessions.insert_one(
        {
            "user_id": payment_user.get("user_id"),
            "session_token": user_token,
            "refresh_token": secrets.token_urlsafe(32),
            "token_version": int(payment_user.get("token_version", 0) or 0),
            "issued_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "ip_address": "127.0.0.1",
        }
    )

    base_url = (os.environ.get("FRONTEND_BASE_URL") or str(request.base_url).rstrip("/")).rstrip("/")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    async def _fetch_pdf(client: httpx.AsyncClient, url: str, *, params: dict | None = None, headers: dict | None = None):
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"PDF fetch failed ({resp.status_code}) for {url}")
        if "application/pdf" not in (resp.headers.get("content-type") or "").lower():
            raise HTTPException(status_code=502, detail=f"Non-PDF response from {url}")
        return resp.content

    try:
        async with httpx.AsyncClient(timeout=80.0, follow_redirects=True) as client:
            receipt_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/payments/receipt/{payment_id}/pdf",
                params={"token": user_token},
            )
            invoice_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/payments/invoice/{payment_id}/pdf",
                params={"token": user_token},
            )
            payment_history_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/payments/export-pdf",
                params={"token": user_token},
            )
            compliance_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/admin/gtec-scan-v2/report-pdf/{latest_gtec.get('task_id')}",
                headers=admin_headers,
            )
            job_offer_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/careers/offers/{offer.get('offer_id')}/pdf",
                headers=admin_headers,
            )
            interview_content_pdf = await _fetch_pdf(
                client,
                f"{base_url}/api/interview-content/{interview.get('interview_id')}/export/pdf",
                headers=admin_headers,
            )
    finally:
        await db.user_sessions.delete_one({"session_token": user_token})

    now_ts = datetime.now(timezone.utc)
    attachments = [
        {
            "filename": build_pdf_v15_filename("receipt", payment_id, ts=now_ts),
            "content": base64.b64encode(receipt_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
        {
            "filename": build_pdf_v15_filename("invoice", payment_id, ts=now_ts),
            "content": base64.b64encode(invoice_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
        {
            "filename": build_pdf_v15_filename("payment-history", payment_id, ts=now_ts),
            "content": base64.b64encode(payment_history_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
        {
            "filename": build_pdf_v15_filename("compliance", latest_gtec.get("task_id"), ts=now_ts),
            "content": base64.b64encode(compliance_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
        {
            "filename": build_pdf_v15_filename("job-offer", offer.get("offer_id"), ts=now_ts),
            "content": base64.b64encode(job_offer_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
        {
            "filename": build_pdf_v15_filename("interview-content", interview.get("interview_id"), ts=now_ts),
            "content": base64.b64encode(interview_content_pdf).decode("utf-8"),
            "content_type": "application/pdf",
        },
    ]

    admins = await db.users.find(
        {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
        {"_id": 0, "email": 1, "name": 1},
    ).to_list(50)
    if not admins:
        raise HTTPException(status_code=404, detail="No admin recipients configured")

    summary = (
        f"PDF verification bundle attached. "
        f"Payment={payment_id}, Offer={offer.get('offer_id')}, ComplianceTask={latest_gtec.get('task_id')}, "
        f"Interview={interview.get('interview_id')}."
    )

    sent = 0
    failed = []
    for target in admins:
        res = await send_catalog_template(
            recipient_email=target.get("email"),
            template_key="system_alert_admin",
            recipient_name=target.get("name") or "Admin",
            alert_type="PDF Verification Suite",
            severity="INFO",
            description=summary,
            component="Admin PDF Pipeline",
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            attachments=attachments,
        )
        if res.get("success"):
            sent += 1
        else:
            failed.append({"email": target.get("email"), "error": res.get("error", "unknown")})

    await db.admin_pdf_v15_verification_log.insert_one(
        {
            "event_id": f"pdfv15_{uuid.uuid4().hex[:12]}",
            "triggered_by": admin.user_id,
            "triggered_by_email": admin.email,
            "sent_count": sent,
            "failed": failed,
            "attachment_count": len(attachments),
            "categories": [
                "receipt",
                "invoice",
                "payment_history",
                "compliance",
                "job_offer",
                "interview_content",
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {
        "success": True,
        "sent_count": sent,
        "failed": failed,
        "categories": [
            "receipt",
            "invoice",
            "payment_history",
            "compliance",
            "job_offer",
            "interview_content",
        ],
    }


@router.get("/candidate-experience/employer/{employer_id}")
async def employer_experience_score(employer_id: str, request: Request):
    """Get employer's candidate experience score."""
    await require_auth(request)

    ratings = await db.candidate_experience.find({"employer_id": employer_id}, {"_id": 0}).to_list(200)
    if not ratings:
        return {
            "employer_id": employer_id,
            "score": None,
            "total_ratings": 0,
            "message": "No ratings yet",
        }

    total = len(ratings)
    avg_overall = round(sum(r.get("overall_rating", 0) for r in ratings) / total, 1)
    avg_comm = round(sum(r.get("communication_rating", 0) for r in ratings) / total, 1)
    avg_prof = round(sum(r.get("professionalism_rating", 0) for r in ratings) / total, 1)
    avg_time = round(sum(r.get("timeliness_rating", 0) for r in ratings) / total, 1)
    avg_feedback = round(sum(r.get("feedback_quality_rating", 0) for r in ratings) / total, 1)
    recommend_pct = round(sum(1 for r in ratings if r.get("would_recommend")) / total * 100, 1)

    # Compute responsiveness metrics
    employer_interviews = await db.interview_bookings.find({"employer_id": employer_id}, {"_id": 0}).to_list(200)

    schedule_times = []
    feedback_times = []
    for iv in employer_interviews:
        created = iv.get("created_at", "")
        scheduled = iv.get("scheduled_date", "")
        if created and scheduled:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                s = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                schedule_times.append((s - c).total_seconds() / 3600)
            except Exception:
                pass
        completed = iv.get("completed_at", "")
        fb = (iv.get("feedback") or {}).get("submitted_at", "")
        if completed and fb:
            try:
                co = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                f = datetime.fromisoformat(fb.replace("Z", "+00:00"))
                feedback_times.append((f - co).total_seconds() / 3600)
            except Exception:
                pass

    # Overall score (1-100)
    score = round(avg_overall * 20)

    return {
        "employer_id": employer_id,
        "score": score,
        "total_ratings": total,
        "averages": {
            "overall": avg_overall,
            "communication": avg_comm,
            "professionalism": avg_prof,
            "timeliness": avg_time,
            "feedback_quality": avg_feedback,
        },
        "recommend_percentage": recommend_pct,
        "responsiveness": {
            "avg_schedule_hours": round(sum(schedule_times) / len(schedule_times), 1) if schedule_times else None,
            "avg_feedback_hours": round(sum(feedback_times) / len(feedback_times), 1) if feedback_times else None,
        },
        "recent_comments": [r.get("comment", "") for r in ratings[-5:] if r.get("comment")],
    }


@router.get("/candidate-experience/rankings")
async def experience_rankings(request: Request):
    """Admin: Employer experience rankings."""
    await require_admin(request)

    ratings = await db.candidate_experience.find({}, {"_id": 0}).to_list(500)
    if not ratings:
        return {"rankings": [], "total_employers": 0}

    # Group by employer
    by_employer = {}
    for r in ratings:
        eid = r.get("employer_id", "")
        if eid not in by_employer:
            by_employer[eid] = {"name": r.get("employer_name", ""), "ratings": []}
        by_employer[eid]["ratings"].append(r)

    rankings = []
    for eid, data in by_employer.items():
        rats = data["ratings"]
        total = len(rats)
        avg = round(sum(r.get("overall_rating", 0) for r in rats) / total, 1)
        recommend = round(sum(1 for r in rats if r.get("would_recommend")) / total * 100, 1)
        rankings.append(
            {
                "employer_id": eid,
                "employer_name": data["name"],
                "score": round(avg * 20),
                "avg_rating": avg,
                "total_ratings": total,
                "recommend_pct": recommend,
            }
        )

    rankings.sort(key=lambda x: x["score"], reverse=True)

    return {
        "rankings": rankings,
        "total_employers": len(rankings),
        "total_ratings": len(ratings),
    }


@router.get("/candidate-experience/my-ratings")
async def my_ratings(request: Request):
    """Candidate: Get my submitted experience ratings."""
    user = await require_auth(request)
    ratings = (
        await db.candidate_experience.find({"candidate_id": user.user_id}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(50)
    )
    return {"ratings": ratings, "total": len(ratings)}
