"""Career application endpoints."""

import os
import logging
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, UploadFile, File, Form
from routes.db import db
from utils.email_service import send_email, is_email_configured, render_email_logo
from utils.field_encryption import encrypt_field, decrypt_field, is_encrypted
from utils.pdf_v15_filename import build_pdf_v15_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/careers", tags=["careers"])

# Fields encrypted in career_applications for PII compliance
_CA_PII_FIELDS = ("full_name",)


def _decrypt_career_doc(doc: dict | None) -> dict | None:
    """Decrypt PII fields in a career application document. Handles lazy migration."""
    if not doc:
        return doc
    for field in _CA_PII_FIELDS:
        val = doc.get(field)
        if val and is_encrypted(val):
            doc[field] = decrypt_field(val)
    return doc

UPLOAD_DIR = "/app/uploads/career_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)
RECORDING_DIR = "/app/uploads/interview_recordings"
os.makedirs(RECORDING_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_RECORDING_SIZE = 500 * 1024 * 1024  # 500MB


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document (resume, cover letter, etc.) for a career application."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {"success": False, "message": f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return {"success": False, "message": "File too large. Maximum size is 10MB."}

    file_id = f"{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(UPLOAD_DIR, file_id)
    with open(path, "wb") as f:
        f.write(content)

    return {
        "success": True,
        "file_id": file_id,
        "filename": file.filename,
        "size": len(content),
        "url": f"/api/careers/files/{file_id}",
    }


@router.get("/files/{file_id}")
async def get_file(file_id: str):
    """Serve uploaded career document."""
    from fastapi.responses import FileResponse
    safe_id = os.path.basename(file_id)
    path = os.path.join(UPLOAD_DIR, safe_id)
    if not os.path.exists(path):
        return {"error": "File not found"}
    return FileResponse(path, filename=safe_id)


@router.post("/interview/upload-recording")
async def upload_recording(
    file: UploadFile = File(...),
    room_id: str = Form(...),
    recorded_by: str = Form(""),
    application_id: str = Form(""),
):
    """Upload an interview recording (WebM/MP4)."""
    ext = os.path.splitext(file.filename or ".webm")[1].lower()
    if ext not in {".webm", ".mp4", ".ogg", ".mkv"}:
        return {"success": False, "message": "Invalid recording format."}

    content = await file.read()
    if len(content) > MAX_RECORDING_SIZE:
        return {"success": False, "message": "Recording too large. Maximum 500MB."}

    rec_id = f"rec-{uuid.uuid4().hex[:10]}{ext}"
    path = os.path.join(RECORDING_DIR, rec_id)
    with open(path, "wb") as f:
        f.write(content)

    duration_sec = 0  # Approximate from file size (rough estimate for webm ~50kB/s)
    if len(content) > 0:
        duration_sec = max(1, len(content) // 50000)

    rec_meta = {
        "recording_id": rec_id,
        "room_id": room_id,
        "application_id": application_id,
        "recorded_by": recorded_by,
        "filename": file.filename,
        "size": len(content),
        "duration_estimate_sec": duration_sec,
        "url": f"/api/careers/interview/recordings/{rec_id}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.interview_recordings.insert_one(dict(rec_meta))

    # Link recording to application if provided
    if application_id:
        await db.career_applications.update_one(
            {"application_id": application_id},
            {"$push": {"recordings": {"recording_id": rec_id, "url": rec_meta["url"], "recorded_by": recorded_by, "created_at": rec_meta["created_at"], "duration_sec": duration_sec}}}
        )

    return {"success": True, **{k: v for k, v in rec_meta.items() if k != "_id"}}


@router.get("/interview/recordings/{rec_id}")
async def get_recording(rec_id: str):
    """Serve interview recording."""
    from fastapi.responses import FileResponse
    safe_id = os.path.basename(rec_id)
    path = os.path.join(RECORDING_DIR, safe_id)
    if not os.path.exists(path):
        return {"error": "Recording not found"}
    return FileResponse(path, filename=safe_id, media_type="video/webm")


@router.get("/interview/recordings-for/{application_id}")
async def get_recordings_for_application(application_id: str):
    """Get all recordings for a specific application."""
    recs = await db.interview_recordings.find(
        {"application_id": application_id.strip().upper()},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"recordings": recs}


@router.post("/interview/analyze/{application_id}")
async def analyze_interview(application_id: str):
    """AI-powered interview analysis: transcribe recording + GPT analysis."""
    from dotenv import load_dotenv
    load_dotenv()

    app = await db.career_applications.find_one(
        {"application_id": application_id.strip().upper()},
        {"_id": 0}
    )
    if not app:
        return {"success": False, "message": "Application not found."}
    _decrypt_career_doc(app)

    recordings = app.get("recordings", [])
    if not recordings:
        return {"success": False, "message": "No recordings found for this application."}

    # Get the latest recording
    rec = recordings[-1]
    rec_path = os.path.join(RECORDING_DIR, os.path.basename(rec["recording_id"]))
    if not os.path.exists(rec_path):
        return {"success": False, "message": "Recording file not found."}

    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        return {"success": False, "message": "AI API key not configured."}

    # Step 1: Transcribe with Whisper
    transcript = ""
    try:
        from emergentintegrations.llm.openai import OpenAISpeechToText
        stt = OpenAISpeechToText(api_key=api_key)
        with open(rec_path, "rb") as audio_file:
            response = await stt.transcribe(
                file=audio_file,
                model="whisper-1",
                response_format="json",
                language="en",
                prompt="This is a job interview for a technology company."
            )
        transcript = response.text
        logger.info(f"Transcription complete: {len(transcript)} chars")
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return {"success": False, "message": f"Transcription failed: {str(e)}"}

    if not transcript or len(transcript.strip()) < 10:
        return {"success": False, "message": "Recording is too short or silent to analyze."}

    # Step 2: Analyze with GPT
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"interview-analysis-{application_id}",
            system_message="""You are an expert HR interview analyst. Analyze the interview transcript and return a JSON object with these exact keys:
{
  "summary": "2-3 sentence overview of the interview",
  "key_points": ["list of 3-5 key discussion topics"],
  "strengths": ["list of 3-5 candidate strengths observed"],
  "weaknesses": ["list of 1-3 areas for improvement"],
  "communication_score": 8,
  "technical_score": 7,
  "cultural_fit_score": 8,
  "overall_score": 8,
  "recommendation": "strong_hire|hire|maybe|no_hire",
  "recommendation_reason": "1-2 sentence explanation"
}
Scores are 1-10. Return ONLY valid JSON, no markdown."""
        )
        chat.with_model("openai", "gpt-4o")

        msg = UserMessage(text=f"""Analyze this interview transcript for the position of "{app.get('position', 'Unknown')}":

Candidate: {app.get('full_name', 'Unknown')}

TRANSCRIPT:
{transcript[:8000]}""")

        raw_response = await chat.send_message(msg)

        # Parse JSON from response
        import json
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            clean = clean.rsplit("```", 1)[0]
        analysis = json.loads(clean)
    except json.JSONDecodeError:
        analysis = {
            "summary": raw_response[:500] if raw_response else "Analysis could not be parsed.",
            "key_points": [], "strengths": [], "weaknesses": [],
            "communication_score": 0, "technical_score": 0, "cultural_fit_score": 0,
            "overall_score": 0, "recommendation": "maybe",
            "recommendation_reason": "AI response could not be parsed as structured data."
        }
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {"success": False, "message": f"AI analysis failed: {str(e)}"}

    # Save analysis
    analysis_doc = {
        "transcript": transcript[:10000],
        "analysis": analysis,
        "recording_id": rec["recording_id"],
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.career_applications.update_one(
        {"application_id": application_id.strip().upper()},
        {"$set": {"ai_analysis": analysis_doc}}
    )

    return {"success": True, "analysis": analysis_doc}


class CompareExportRequest(BaseModel):
    application_ids: list[str]


class ShareEmailRequest(BaseModel):
    application_ids: list[str]
    recipients: list[str]
    message: str = ""


async def _fetch_analyzed_candidates(application_ids: list[str]):
    candidates = []
    for aid in application_ids:
        app = await db.career_applications.find_one(
            {"application_id": aid.strip().upper()}, {"_id": 0}
        )
        if app and app.get("ai_analysis"):
            _decrypt_career_doc(app)
            candidates.append(app)
    return candidates


def _generate_comparison_pdf(candidates: list) -> bytes:
    import math
    from fpdf import FPDF

    COLORS = [(59, 130, 246), (16, 185, 129), (245, 158, 11), (139, 92, 246)]
    AXES = [("communication_score", "Communication"), ("technical_score", "Technical"), ("cultural_fit_score", "Cultural Fit"), ("overall_score", "Overall")]
    rec_colors = {"strong_hire": (16, 185, 129), "hire": (59, 130, 246), "maybe": (245, 158, 11), "no_hire": (239, 68, 68)}

    class PDF(FPDF):
        def header(self):
            self.set_fill_color(15, 23, 42)
            self.rect(0, 0, 210, 32, "F")
            self.set_font("Helvetica", "B", 16)
            self.set_text_color(248, 250, 252)
            self.set_xy(10, 8)
            self.cell(0, 8, "RealAICoach", new_x="LMARGIN")
            self.set_font("Helvetica", "", 10)
            self.set_text_color(148, 163, 184)
            self.set_xy(10, 18)
            self.cell(0, 6, "Candidate Comparison Report", new_x="LMARGIN")
            self.set_font("Helvetica", "", 8)
            self.set_xy(150, 18)
            self.cell(0, 6, datetime.now(timezone.utc).strftime("%B %d, %Y"), new_x="LMARGIN")
            self.ln(20)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 10, f"Page {self.page_no()} | Confidential - RealAICoach Hiring", align="C")

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_y(38)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, f"Comparing {len(candidates)} Candidates", new_x="LMARGIN", new_y="NEXT")
    for i, c in enumerate(candidates):
        r, g, b = COLORS[i % len(COLORS)]
        pdf.set_fill_color(r, g, b)
        pdf.rect(pdf.get_x(), pdf.get_y() + 2, 4, 4, "F")
        pdf.set_x(pdf.get_x() + 7)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(r, g, b)
        pdf.cell(60, 8, c.get("full_name", "Unknown"), new_x="LEFT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.set_x(pdf.get_x() + 60)
        pdf.cell(0, 8, c.get("position", ""), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    cx, cy = 105, pdf.get_y() + 55
    max_r, num_axes = 40, len(AXES)
    angle_step = 2 * math.pi / num_axes
    start_angle = -math.pi / 2

    def get_pt(axis_idx, value):
        angle = start_angle + axis_idx * angle_step
        r = (value / 10) * max_r
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    for level in [2, 4, 6, 8, 10]:
        pts = [get_pt(i, level) for i in range(num_axes)]
        pdf.set_draw_color(200, 210, 220)
        pdf.set_line_width(0.2)
        for j in range(num_axes):
            pdf.line(pts[j][0], pts[j][1], pts[(j + 1) % num_axes][0], pts[(j + 1) % num_axes][1])
    for i in range(num_axes):
        ex, ey = get_pt(i, 10)
        pdf.set_draw_color(200, 210, 220)
        pdf.line(cx, cy, ex, ey)
    for i, (_, label) in enumerate(AXES):
        lx, ly = get_pt(i, 12.5)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(100, 116, 139)
        tw = pdf.get_string_width(label)
        pdf.text(lx - tw / 2, ly + 3, label)
    for ci, c in enumerate(candidates):
        analysis = c.get("ai_analysis", {}).get("analysis", {})
        r, g, b = COLORS[ci % len(COLORS)]
        pts = [get_pt(i, analysis.get(key, 0)) for i, (key, _) in enumerate(AXES)]
        pdf.set_draw_color(r, g, b)
        pdf.set_line_width(0.6)
        for j in range(num_axes):
            pdf.line(pts[j][0], pts[j][1], pts[(j + 1) % num_axes][0], pts[(j + 1) % num_axes][1])
        for px, py in pts:
            pdf.set_fill_color(r, g, b)
            pdf.circle(px, py, 1.5, "F")
    pdf.set_y(cy + max_r + 15)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "Score Comparison", new_x="LMARGIN", new_y="NEXT")
    col_w_label = 40
    col_w_score = (170 - col_w_label) / len(candidates)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w_label, 8, "Metric", border=1, fill=True)
    for i, c in enumerate(candidates):
        pdf.cell(col_w_score, 8, c.get("full_name", "?").split()[0], border=1, fill=True, align="C")
    pdf.ln()
    for key, label in AXES:
        scores = [c.get("ai_analysis", {}).get("analysis", {}).get(key, 0) for c in candidates]
        max_score = max(scores)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(col_w_label, 8, label, border=1)
        for i, sc in enumerate(scores):
            if sc == max_score and len(candidates) > 1:
                pdf.set_text_color(*COLORS[i % len(COLORS)])
                pdf.set_font("Helvetica", "B", 10)
            else:
                pdf.set_text_color(30, 41, 59)
                pdf.set_font("Helvetica", "", 9)
            pdf.cell(col_w_score, 8, f"{sc}/10", border=1, align="C")
        pdf.ln()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(col_w_label, 8, "Recommendation", border=1)
    for c in candidates:
        rec = c.get("ai_analysis", {}).get("analysis", {}).get("recommendation", "N/A")
        pdf.set_text_color(*rec_colors.get(rec, (100, 116, 139)))
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_w_score, 8, rec.replace("_", " ").upper(), border=1, align="C")
    pdf.ln(12)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "Candidate Summaries", new_x="LMARGIN", new_y="NEXT")
    for i, c in enumerate(candidates):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*COLORS[i % len(COLORS)])
        pdf.cell(0, 7, c.get("full_name", "Unknown"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(190, 5, c.get("ai_analysis", {}).get("analysis", {}).get("summary", "No summary."))
        pdf.ln(2)

    pdf.add_page()
    pdf.set_y(38)
    for section, section_label, color in [("strengths", "Strengths", (16, 185, 129)), ("weaknesses", "Areas for Improvement", (245, 158, 11))]:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*color)
        pdf.cell(190, 8, section_label, new_x="LMARGIN", new_y="NEXT")
        for i, c in enumerate(candidates):
            items = c.get("ai_analysis", {}).get("analysis", {}).get(section, [])
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*COLORS[i % len(COLORS)])
            pdf.cell(190, 6, c.get("full_name", "Unknown"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(71, 85, 105)
            for item in items:
                pdf.set_x(10)
                pdf.multi_cell(190, 5, f"  - {item}")
            pdf.ln(2)
        pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "Recommendation Reasoning", new_x="LMARGIN", new_y="NEXT")
    for i, c in enumerate(candidates):
        analysis = c.get("ai_analysis", {}).get("analysis", {})
        rec = analysis.get("recommendation", "N/A")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*COLORS[i % len(COLORS)])
        pdf.cell(60, 7, c.get("full_name", "Unknown"))
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*rec_colors.get(rec, (100, 116, 139)))
        pdf.cell(0, 7, f"[{rec.replace('_', ' ').upper()}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(190, 5, analysis.get("recommendation_reason", "No reason provided."))
        pdf.ln(3)

    return bytes(pdf.output())


@router.post("/comparison/export-pdf")
async def export_comparison_pdf(body: CompareExportRequest):
    """Generate a PDF comparison report for selected candidates."""
    from fastapi.responses import Response

    if len(body.application_ids) < 2 or len(body.application_ids) > 4:
        return {"success": False, "message": "Select 2-4 candidates to compare."}
    candidates = await _fetch_analyzed_candidates(body.application_ids)
    if len(candidates) < 2:
        return {"success": False, "message": "At least 2 candidates with AI analysis are required."}

    pdf_bytes = _generate_comparison_pdf(candidates)
    filename = build_pdf_v15_filename("candidate-comparison", datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/comparison/share-email")
async def share_comparison_email(body: ShareEmailRequest):
    """Generate PDF and email it to recipients."""
    import base64

    if len(body.application_ids) < 2 or len(body.application_ids) > 4:
        return {"success": False, "message": "Select 2-4 candidates to compare."}
    if not body.recipients or len(body.recipients) > 10:
        return {"success": False, "message": "Provide 1-10 recipient email addresses."}
    candidates = await _fetch_analyzed_candidates(body.application_ids)
    if len(candidates) < 2:
        return {"success": False, "message": "At least 2 candidates with AI analysis are required."}

    pdf_bytes = _generate_comparison_pdf(candidates)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    filename = build_pdf_v15_filename("candidate-comparison", datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))

    rec_labels = {"strong_hire": "Strong Hire", "hire": "Hire", "maybe": "Maybe", "no_hire": "No Hire"}
    rec_hex = {"strong_hire": "#10B981", "hire": "#3B82F6", "maybe": "#F59E0B", "no_hire": "#EF4444"}
    color_hex = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6"]

    rows = ""
    for i, c in enumerate(candidates):
        a = c.get("ai_analysis", {}).get("analysis", {})
        rec = a.get("recommendation", "N/A")
        rows += f"""<tr>
            <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:{color_hex[i%4]};font-weight:700">{c.get('full_name','Unknown')}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:#CBD5E1">{c.get('position','')}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #1E293B;color:#F8FAFC;text-align:center;font-weight:700">{a.get('overall_score',0)}/10</td>
            <td style="padding:10px 14px;border-bottom:1px solid #1E293B;text-align:center"><span style="background:{rec_hex.get(rec,'#64748B')}22;color:{rec_hex.get(rec,'#64748B')};padding:4px 12px;border-radius:12px;font-size:12px;font-weight:700">{rec_labels.get(rec,rec).upper()}</span></td>
        </tr>"""

    personal_msg = ""
    if body.message.strip():
        personal_msg = f'<div style="background:#1E293B;border-radius:8px;padding:16px;margin-bottom:18px;border-left:3px solid #3B82F6"><p style="color:#94A3B8;font-size:12px;margin:0 0 6px">Message from sender:</p><p style="color:#F8FAFC;font-size:14px;margin:0;line-height:1.6">{body.message.strip()}</p></div>'

    # V7 shell — produces the `em-outer` fingerprint required by the runtime
    # guardrail in utils/email_service.py. Historical raw `<table>` email
    # was auto-wrapped + theme-mismatched; now the inner card shares the
    # same dark-teal theme as the V7 outer chrome.
    from utils.email_templates import _wrap, _lead, _callout, DASH_URL
    inner = _lead(
        "Candidate Comparison Report",
        f"RealAICoach Hiring Team · {len(candidates)} candidates compared",
    ) + personal_msg + f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl em-force-light-card" style="background:#0F172A;border-radius:12px;border:1px solid #1E293B;margin:16px 0 18px;overflow:hidden;">
      <thead>
        <tr style="background:#0F172A">
          <th style="padding:10px 14px;text-align:left;color:#64748B;font-size:11px;font-weight:700;border-bottom:1px solid #334155">CANDIDATE</th>
          <th style="padding:10px 14px;text-align:left;color:#64748B;font-size:11px;font-weight:700;border-bottom:1px solid #334155">POSITION</th>
          <th style="padding:10px 14px;text-align:center;color:#64748B;font-size:11px;font-weight:700;border-bottom:1px solid #334155">SCORE</th>
          <th style="padding:10px 14px;text-align:center;color:#64748B;font-size:11px;font-weight:700;border-bottom:1px solid #334155">RECOMMENDATION</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """ + _callout(
        f"The full comparison report with detailed scores, strengths, weaknesses, and recommendation reasoning is attached as a PDF: <strong>{filename}</strong>."
    ) + _callout(
        "This is a confidential document from RealAICoach. Please do not share outside your hiring team.",
        "#64748B",
    )

    html = _wrap(
        "Candidate Comparison",
        f"{len(candidates)} candidates scored and ranked",
        inner,
        "Open Careers Console",
        f"{DASH_URL}/admin-console?tab=career-applications",
        "#3B82F6",
        category="careers",
    )

    sent, failed = [], []
    for email_addr in body.recipients:
        email_addr = email_addr.strip()
        if not email_addr:
            continue
        result = await send_email(
            recipient_email=email_addr,
            subject=f"Candidate Comparison Report - {len(candidates)} Candidates",
            content=html,
            template_key="career_comparison_report",
            attachments=[{"filename": filename, "content": pdf_b64}],
        )
        if result.get("success", False) or result.get("id"):
            sent.append(email_addr)
        else:
            failed.append(email_addr)

    return {"success": len(sent) > 0, "sent": sent, "failed": failed, "message": f"Report sent to {len(sent)} recipient(s)." if sent else "Failed to send emails."}


class CareerApplicationRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str = ""
    position: str = "Open Application"
    department: str = ""
    cover_letter: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    experience_years: str = ""
    how_heard: str = ""
    documents: list = []  # [{file_id, filename, type}]


class CareerApplicationResponse(BaseModel):
    success: bool
    message: str
    application_id: str = ""


@router.post("/apply", response_model=CareerApplicationResponse)
async def submit_application(req: CareerApplicationRequest):
    email = req.email.strip().lower()

    existing = await db.career_applications.find_one(
        {"email": email, "position": req.position},
        {"_id": 0, "email": 1}
    )
    if existing:
        return CareerApplicationResponse(
            success=False,
            message=f"You've already applied for {req.position}. We'll be in touch!",
        )

    app_id = f"APP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{email[:4].upper()}"

    doc = {
        "application_id": app_id,
        "full_name": encrypt_field(req.full_name.strip()),
        "email": email,
        "phone": req.phone.strip(),
        "position": req.position,
        "department": req.department,
        "cover_letter": req.cover_letter.strip(),
        "linkedin_url": req.linkedin_url.strip(),
        "portfolio_url": req.portfolio_url.strip(),
        "experience_years": req.experience_years,
        "how_heard": req.how_heard,
        "documents": req.documents,
        "status": "received",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.career_applications.insert_one(doc)

    if is_email_configured():
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="career_confirmation",
                recipient_name=req.full_name.strip(),
                applicant_name=req.full_name.strip(),
                position=req.position,
                application_id=app_id,
            )
        except Exception as e:
            logger.warning(f"Career confirmation email failed: {e}")

    admin_emails = os.environ.get("ADMIN_EMAILS", "")
    if is_email_configured() and admin_emails:
        try:
            _build_admin_notification(req, app_id)
            for ae in admin_emails.split(","):
                ae = ae.strip()
                if ae:
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=ae,
                        template_key="career_admin_notify",
                        applicant_name=req.full_name,
                        position=req.position,
                        application_id=app_id,
                        email=email,
                        experience=getattr(req, "experience_years", ""),
                    )
        except Exception as e:
            logger.warning(f"Career admin notification failed: {e}")

    return CareerApplicationResponse(
        success=True,
        message="Your application has been received! Check your email for confirmation.",
        application_id=app_id,
    )


@router.get("/track/{application_id}")
async def track_application(application_id: str):
    """Public: Track application status by ID."""
    app = await db.career_applications.find_one(
        {"application_id": application_id.strip().upper()},
        {"_id": 0, "full_name": 1, "position": 1, "department": 1, "status": 1, "submitted_at": 1, "application_id": 1, "interview": 1}
    )
    if not app:
        return {"found": False, "message": "No application found with that ID. Please check and try again."}
    _decrypt_career_doc(app)

    status_timeline = [
        {"step": "received", "label": "Application Received", "description": "Your application has been submitted and is in our system."},
        {"step": "under_review", "label": "Under Review", "description": "Our hiring team is carefully reviewing your application."},
        {"step": "interview", "label": "Interview Stage", "description": "You've been selected for an interview. We'll reach out to schedule."},
        {"step": "offer", "label": "Offer Extended", "description": "Congratulations! An offer has been sent to you."},
    ]

    current_status = app.get("status", "received")
    status_order = ["received", "under_review", "interview", "offer", "rejected"]
    current_idx = status_order.index(current_status) if current_status in status_order else 0

    return {
        "found": True,
        "application": app,
        "timeline": status_timeline,
        "current_step_index": current_idx,
        "is_rejected": current_status == "rejected",
    }


@router.get("/applications")
async def list_applications():
    """Admin: List all career applications."""
    apps = await db.career_applications.find(
        {}, {"_id": 0}
    ).sort("submitted_at", -1).to_list(500)
    apps = [_decrypt_career_doc(a) for a in apps]
    return {"applications": apps, "total": len(apps)}


@router.get("/applications/stats")
async def application_stats():
    """Admin: Get career application statistics."""
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts = {}
    async for doc in db.career_applications.aggregate(pipeline):
        status_counts[doc["_id"]] = doc["count"]

    total = sum(status_counts.values())

    # Recent applications (last 7 days)
    from datetime import datetime, timezone, timedelta
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = await db.career_applications.count_documents({"submitted_at": {"$gte": week_ago}})

    # Position breakdown
    pos_pipeline = [
        {"$group": {"_id": "$position", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    positions = {}
    async for doc in db.career_applications.aggregate(pos_pipeline):
        positions[doc["_id"]] = doc["count"]

    return {
        "total": total,
        "by_status": status_counts,
        "recent_7d": recent,
        "by_position": positions,
    }


class StatusUpdateRequest(BaseModel):
    status: str
    send_email: bool = False
    admin_notes: str = ""
    interview_date: str = ""
    interview_time: str = ""
    interview_type: str = ""  # video, phone, in-person, in-app-video
    interview_notes: str = ""


@router.patch("/applications/{application_id}/status")
async def update_application_status(application_id: str, body: StatusUpdateRequest):
    """Admin: Update application status and optionally notify the applicant."""
    valid_statuses = ["received", "under_review", "interview", "offer", "rejected"]
    if body.status not in valid_statuses:
        return {"success": False, "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

    app = await db.career_applications.find_one(
        {"application_id": application_id.strip().upper()},
        {"_id": 0}
    )
    if not app:
        return {"success": False, "message": "Application not found."}
    _decrypt_career_doc(app)

    old_status = app.get("status", "received")
    if old_status == body.status and not body.admin_notes and not body.interview_date:
        return {"success": False, "message": f"Application is already in '{body.status}' status."}

    update_fields = {
        "status": body.status,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.admin_notes:
        update_fields["admin_notes"] = body.admin_notes

    # Interview scheduling
    interview_details = None
    if body.status == "interview" and body.interview_date:
        import uuid
        room_id = f"interview-{application_id.lower()}-{uuid.uuid4().hex[:8]}"
        base_url = os.environ.get("FRONTEND_BASE_URL", "")
        video_url = f"{base_url}/interview-room?room={room_id}&name={app.get('full_name', 'Candidate').replace(' ', '+')}"
        interview_details = {
            "date": body.interview_date,
            "time": body.interview_time,
            "type": body.interview_type or "video",
            "notes": body.interview_notes,
            "room_id": room_id,
            "video_url": video_url,
        }
        update_fields["interview"] = interview_details

    await db.career_applications.update_one(
        {"application_id": application_id.strip().upper()},
        {"$set": update_fields}
    )

    email_sent = False
    if body.send_email and app.get("email"):
        try:
            from utils.email_service import send_catalog_template
            interview_details_for_email = interview_details or {}
            result = await send_catalog_template(
                recipient_email=app["email"],
                template_key="career_status_update",
                recipient_name=app.get("full_name", "Applicant"),
                applicant_name=app.get("full_name", "Applicant"),
                position=app.get("position", ""),
                application_id=application_id,
                status=body.status,
                status_label=_status_label(body.status),
                interview_date=interview_details_for_email.get("date", ""),
                interview_type=interview_details_for_email.get("type", ""),
                notes=body.notes or "",
            )
            email_sent = result.get("success", False)
        except Exception as e:
            logger.error(f"Failed to send status update email: {e}")

    return {
        "success": True,
        "message": f"Status updated to '{body.status}'." + (" Notification email sent." if email_sent else ""),
        "old_status": old_status,
        "new_status": body.status,
        "email_sent": email_sent,
        "interview": interview_details,
    }


def _build_confirmation_email(name: str, position: str, app_id: str) -> str:
    logo = render_email_logo("default")
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    signup_url = f"{base_url}/auth/register"
    first_name = name.split()[0] if name else "there"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:40px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">

        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);padding:40px 32px 32px;text-align:center;">
          {logo}
          <h1 style="color:#F8FAFC;font-size:24px;font-weight:800;margin:16px 0 8px;letter-spacing:-0.3px;">
            Application Received!
          </h1>
          <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">
            Thank you for your interest in joining RealAICoach
          </p>
        </td></tr>

        <!-- Body -->
        <tr><td style="padding:32px;">
          <p style="color:#1E293B;font-size:16px;font-weight:600;margin:0 0 16px;">
            Hi {first_name},
          </p>
          <p style="color:#475569;font-size:14px;line-height:1.7;margin:0 0 20px;">
            We're excited that you've applied for the <strong style="color:#0F172A;">{position}</strong> role at RealAICoach. Your application has been received and is now being reviewed by our team.
          </p>

          <!-- Application Details Card -->
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;overflow:hidden;margin-bottom:24px;">
            <tr><td style="padding:20px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding-bottom:12px;">
                    <span style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Application ID</span><br>
                    <span style="color:#0F172A;font-size:14px;font-weight:700;font-family:monospace;">{app_id}</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding-bottom:12px;">
                    <span style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Position</span><br>
                    <span style="color:#0F172A;font-size:14px;font-weight:600;">{position}</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <span style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Status</span><br>
                    <span style="display:inline-block;background:#10B98118;color:#10B981;font-size:12px;font-weight:700;padding:4px 12px;border-radius:20px;margin-top:4px;">Under Review</span>
                  </td>
                </tr>
              </table>
            </td></tr>
          </table>

          <!-- What to Expect -->
          <h2 style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 14px;">What Happens Next?</h2>

          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding-bottom:14px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#EFF6FF;border-radius:10px;text-align:center;vertical-align:middle;">
                  <span style="color:#3B82F6;font-size:14px;font-weight:800;">1</span>
                </td>
                <td style="padding-left:14px;">
                  <strong style="color:#1E293B;font-size:13px;">Application Review</strong><br>
                  <span style="color:#64748B;font-size:12px;">Our hiring team reviews every application personally within 5-7 business days.</span>
                </td>
              </tr></table>
            </td></tr>
            <tr><td style="padding-bottom:14px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;">
                  <span style="color:#10B981;font-size:14px;font-weight:800;">2</span>
                </td>
                <td style="padding-left:14px;">
                  <strong style="color:#1E293B;font-size:13px;">Initial Conversation</strong><br>
                  <span style="color:#64748B;font-size:12px;">If there's a match, we'll schedule a casual conversation to learn more about you.</span>
                </td>
              </tr></table>
            </td></tr>
            <tr><td style="padding-bottom:14px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#FFF7ED;border-radius:10px;text-align:center;vertical-align:middle;">
                  <span style="color:#F97316;font-size:14px;font-weight:800;">3</span>
                </td>
                <td style="padding-left:14px;">
                  <strong style="color:#1E293B;font-size:13px;">Decision & Offer</strong><br>
                  <span style="color:#64748B;font-size:12px;">We move fast. You'll hear from us with a decision or next steps soon after.</span>
                </td>
              </tr></table>
            </td></tr>
          </table>

          <!-- Track Application CTA -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
            <tr><td style="padding:20px;text-align:center;">
              <p style="color:#1E293B;font-size:14px;font-weight:700;margin:0 0 6px;">
                Track Your Application
              </p>
              <p style="color:#64748B;font-size:12px;margin:0 0 14px;line-height:1.5;">
                Check your application status anytime using your Application ID.
              </p>
              <a href="{base_url}/track-application?id={app_id}" style="display:inline-block;background:#3B82F6;color:#FFFFFF;font-size:13px;font-weight:700;padding:11px 28px;border-radius:8px;text-decoration:none;">
                Check Status
              </a>
            </td></tr>
          </table>

          <!-- CTA: Explore Platform -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);border-radius:14px;overflow:hidden;">
            <tr><td style="padding:24px;text-align:center;">
              <p style="color:#F8FAFC;font-size:15px;font-weight:700;margin:0 0 6px;">
                While You Wait...
              </p>
              <p style="color:#94A3B8;font-size:13px;margin:0 0 16px;line-height:1.5;">
                Explore RealAICoach and see the platform you could help build. Create a free account to experience our AI coaching firsthand.
              </p>
              <a href="{signup_url}" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:14px;font-weight:700;padding:14px 36px;border-radius:10px;text-decoration:none;letter-spacing:0.3px;">
                Create Your Free Account
              </a>
            </td></tr>
          </table>
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding:0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
            <td style="height:3px;background:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0);font-size:0;line-height:0;">&nbsp;</td>
          </tr></table>
        </td></tr>
        <tr><td style="background:#F8FAFC;padding:24px 32px;text-align:center;">
          <p style="font-size:18px;font-weight:900;letter-spacing:-0.5px;margin:0 0 8px;line-height:1;font-family:-apple-system,Helvetica,Arial,sans-serif;">
            <span style="color:#0F172A;">Real</span><span style="color:#06D6A0;">AI</span><span style="color:#0F172A;">Coach</span>
          </p>
          <p style="color:#64748B;font-size:11px;margin:0;line-height:1.8;font-family:-apple-system,Helvetica,Arial,sans-serif;">
            Questions about your application? Reply to this email or reach us at
            <a href="mailto:careers@realaicoach.app" style="color:#3B82F6;font-weight:600;text-decoration:none;">careers@realaicoach.app</a><br>
            RealAICoach LLC &bull; 11501 Domain Dr, Suite 200, Austin, TX 78758, USA<br>
            &copy; {datetime.now().year} RealAICoach LLC. All rights reserved.
          </p>
        </td></tr>
      </table>
    </body>
    </html>
    """


def _build_admin_notification(req: CareerApplicationRequest, app_id: str) -> str:
    logo = render_email_logo("default")
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:40px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">
        <tr><td style="background:#0F172A;padding:24px 32px;text-align:center;">
          {logo}
          <h1 style="color:#F8FAFC;font-size:18px;font-weight:700;margin:12px 0 0;">New Career Application</h1>
        </td></tr>
        <tr><td style="padding:24px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;padding:16px;">
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">NAME</strong><br><span style="color:#0F172A;font-size:14px;">{req.full_name}</span></td></tr>
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">EMAIL</strong><br><span style="color:#0F172A;font-size:14px;">{req.email}</span></td></tr>
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">POSITION</strong><br><span style="color:#0F172A;font-size:14px;">{req.position}</span></td></tr>
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">PHONE</strong><br><span style="color:#0F172A;font-size:14px;">{req.phone or 'Not provided'}</span></td></tr>
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">EXPERIENCE</strong><br><span style="color:#0F172A;font-size:14px;">{req.experience_years or 'Not provided'}</span></td></tr>
            <tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">APPLICATION ID</strong><br><span style="color:#0F172A;font-size:14px;font-family:monospace;">{app_id}</span></td></tr>
            {f'<tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">LINKEDIN</strong><br><a href="{req.linkedin_url}" style="color:#3B82F6;font-size:14px;">{req.linkedin_url}</a></td></tr>' if req.linkedin_url else ''}
            {f'<tr><td style="padding:8px 16px;"><strong style="color:#64748B;font-size:11px;">COVER LETTER</strong><br><span style="color:#475569;font-size:13px;line-height:1.5;">{req.cover_letter[:500]}</span></td></tr>' if req.cover_letter else ''}
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """


STATUS_CONFIG = {
    "received": {"label": "Application Received", "color": "#3B82F6", "icon": "inbox"},
    "under_review": {"label": "Under Review", "color": "#F59E0B", "icon": "search"},
    "interview": {"label": "Interview Stage", "color": "#8B5CF6", "icon": "video"},
    "offer": {"label": "Offer Extended", "color": "#10B981", "icon": "trophy"},
    "rejected": {"label": "Not Selected", "color": "#EF4444", "icon": "x"},
}


def _status_label(status: str) -> str:
    return STATUS_CONFIG.get(status, {}).get("label", status.replace("_", " ").title())


def _build_interview_email_section(interview: dict) -> str:
    itype_labels = {"video": "Video Call", "phone": "Phone Call", "in-person": "In Person", "in-app-video": "In-App Video Interview"}
    itype = itype_labels.get(interview.get("type", "video"), "Video Call")
    video_btn = ""
    if interview.get("type") == "in-app-video" and interview.get("video_url"):
        video_btn = f"""<tr><td style="padding-top:14px;text-align:center;">
                <a href="{interview['video_url']}" style="display:inline-block;background:#8B5CF6;color:#FFFFFF;font-size:13px;font-weight:700;padding:11px 24px;border-radius:8px;text-decoration:none;">Join Video Interview</a>
              </td></tr>"""
    notes_row = f'<tr><td colspan="2" style="padding-top:8px;"><span style="color:#64748B;font-size:10px;font-weight:700;">NOTES</span><br><span style="color:#475569;font-size:13px;line-height:1.5;">{interview.get("notes", "")}</span></td></tr>' if interview.get("notes") else ''
    return f"""<table width="100%" cellpadding="0" cellspacing="0" style="background:#8B5CF610;border:1px solid #8B5CF630;border-radius:12px;overflow:hidden;margin-bottom:20px;">
                <tr><td style="padding:20px;">
                  <p style="color:#8B5CF6;font-size:12px;font-weight:700;letter-spacing:0.5px;margin:0 0 12px;">INTERVIEW SCHEDULED</p>
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding-bottom:8px;width:50%;"><span style="color:#64748B;font-size:10px;font-weight:700;">DATE</span><br><span style="color:#0F172A;font-size:14px;font-weight:700;">{interview.get('date', '')}</span></td>
                      <td style="padding-bottom:8px;"><span style="color:#64748B;font-size:10px;font-weight:700;">TIME</span><br><span style="color:#0F172A;font-size:14px;font-weight:700;">{interview.get('time', 'TBD')}</span></td>
                    </tr>
                    <tr><td colspan="2"><span style="color:#64748B;font-size:10px;font-weight:700;">FORMAT</span><br><span style="color:#0F172A;font-size:14px;font-weight:600;">{itype}</span></td></tr>
                    {notes_row}
                    {video_btn}
                  </table>
                </td></tr>
              </table>"""


def _build_status_update_email(name: str, position: str, app_id: str, new_status: str, interview: dict = None) -> str:
    logo = render_email_logo("default")
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    tracker_url = f"{base_url}/track-application?id={app_id}"
    signup_url = f"{base_url}/auth/register"
    first_name = name.split()[0] if name else "there"
    cfg = STATUS_CONFIG.get(new_status, STATUS_CONFIG["received"])
    label = cfg["label"]
    color = cfg["color"]

    if new_status == "under_review":
        body_text = f"Great news! Our hiring team has started reviewing your application for the <strong>{position}</strong> position. We're carefully evaluating your qualifications and experience."
        next_step = "We'll be in touch within 5-7 business days with an update. In the meantime, feel free to track your application status anytime."
    elif new_status == "interview":
        body_text = f"Exciting news! We've reviewed your application for the <strong>{position}</strong> position and would love to learn more about you. You've been selected for an interview!"
        if interview and interview.get("date"):
            next_step = "Your interview has been scheduled. Please review the details below and prepare accordingly."
        else:
            next_step = "A member of our team will reach out shortly to schedule a convenient time. Please keep an eye on your email for scheduling details."
    elif new_status == "offer":
        body_text = f"Congratulations! After careful consideration, we're thrilled to extend an offer for the <strong>{position}</strong> position at RealAICoach. Welcome to the team!"
        next_step = "You'll receive a formal offer letter with all the details via email shortly. We're excited to have you on board!"
    elif new_status == "rejected":
        body_text = f"Thank you for your interest in the <strong>{position}</strong> position at RealAICoach. After careful review, we've decided to move forward with other candidates at this time."
        next_step = "We encourage you to apply again in the future as new opportunities arise. Your talent and interest in our mission are valued."
    else:
        body_text = f"There's an update on your application for the <strong>{position}</strong> position."
        next_step = "You can track your application status anytime using the link below."

    return f"""<!DOCTYPE html>
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#F1F5F9;padding:32px 16px;">
        <tr><td align="center">
          <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">
            <!-- Header -->
            <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);padding:28px 32px;text-align:center;">
              {logo}
              <p style="color:#94A3B8;font-size:12px;font-weight:500;margin:8px 0 0;">Application Status Update</p>
            </td></tr>
            <!-- Body -->
            <tr><td style="padding:32px;">
              <!-- Status Badge -->
              <div style="text-align:center;margin-bottom:24px;">
                <span style="display:inline-block;background:{color}15;color:{color};font-size:13px;font-weight:700;padding:8px 20px;border-radius:24px;border:1px solid {color}30;">{label}</span>
              </div>

              <p style="color:#1E293B;font-size:16px;font-weight:700;margin:0 0 6px;">Hi {first_name},</p>
              <p style="color:#475569;font-size:14px;line-height:1.7;margin:0 0 20px;">{body_text}</p>

              {_build_interview_email_section(interview) if interview and interview.get('date') and new_status == 'interview' else ''}

              <!-- App Details -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;overflow:hidden;margin-bottom:20px;">
                <tr><td style="padding:16px;">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding-bottom:8px;">
                        <span style="color:#64748B;font-size:10px;font-weight:700;letter-spacing:0.5px;">APPLICATION ID</span><br>
                        <span style="color:#0F172A;font-size:13px;font-weight:700;font-family:monospace;">{app_id}</span>
                      </td>
                    </tr>
                    <tr>
                      <td>
                        <span style="color:#64748B;font-size:10px;font-weight:700;letter-spacing:0.5px;">POSITION</span><br>
                        <span style="color:#0F172A;font-size:13px;font-weight:600;">{position}</span>
                      </td>
                    </tr>
                  </table>
                </td></tr>
              </table>

              <!-- Next Step -->
              <p style="color:#1E293B;font-size:14px;font-weight:700;margin:0 0 6px;">What's Next?</p>
              <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 24px;">{next_step}</p>

              <!-- Track CTA -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
                <tr><td align="center">
                  <a href="{tracker_url}" style="display:inline-block;background:#3B82F6;color:#FFFFFF;font-size:14px;font-weight:700;padding:13px 32px;border-radius:10px;text-decoration:none;">
                    Track Your Application
                  </a>
                </td></tr>
              </table>

              <!-- Explore CTA -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#0F172A,#1E293B);border-radius:12px;overflow:hidden;">
                <tr><td style="padding:20px;text-align:center;">
                  <p style="color:#F8FAFC;font-size:14px;font-weight:700;margin:0 0 6px;">Explore RealAICoach</p>
                  <p style="color:#94A3B8;font-size:12px;margin:0 0 14px;">Create a free account to experience our AI coaching platform.</p>
                  <a href="{signup_url}" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:13px;font-weight:700;padding:11px 28px;border-radius:8px;text-decoration:none;">
                    Create Your Free Account
                  </a>
                </td></tr>
              </table>
            </td></tr>
            <!-- Footer -->
            <tr><td style="padding:20px 32px;border-top:1px solid #E2E8F0;text-align:center;">
              <p style="color:#94A3B8;font-size:11px;margin:0;">RealAICoach Talent Team</p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>"""
