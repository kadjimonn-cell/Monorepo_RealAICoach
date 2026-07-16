"""
Travel Visa — Extended Features Module
Admin CMS, Object Storage, Email Notifications, Achievement Auto-Grant, Certificate PDF
"""
import os
import uuid
import io
import base64
import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File
from fastapi.responses import StreamingResponse
from routes.db import db as _singleton_db

router = APIRouter(prefix="/travel-visa", tags=["travel-visa-ext"])

def get_db():
    return _singleton_db

# ══════════════════════════════════════
# ADMIN CMS (Auto-managed, no manual input)
# ══════════════════════════════════════

@router.get("/admin/cms/overview")
async def cms_overview():
    db = get_db()
    stats = {
        "categories": await db.tv_categories.count_documents({}),
        "lessons": await db.tv_lessons.count_documents({}),
        "video_lessons": await db.tv_lessons.count_documents({"type": "video"}),
        "audio_lessons": await db.tv_lessons.count_documents({"type": "audio"}),
        "reading_lessons": await db.tv_lessons.count_documents({"type": "reading"}),
        "interactive_lessons": await db.tv_lessons.count_documents({"type": "interactive"}),
        "quizzes": await db.tv_quizzes.count_documents({}),
        "countries": await db.tv_countries.count_documents({}),
        "embassies": await db.tv_embassies.count_documents({}),
        "achievements": await db.tv_achievements_catalog.count_documents({}),
        "active_users": await db.tv_user_stats.count_documents({}),
        "total_coaching_sessions": await db.tv_coaching_sessions.count_documents({}),
        "total_simulations": await db.tv_interview_sessions.count_documents({}),
        "total_challenges": await db.tv_challenges.count_documents({}),
        "total_quiz_submissions": await db.tv_quiz_results.count_documents({}),
        "total_notifications": await db.tv_notifications.count_documents({}),
    }
    # Top categories by lesson count
    pipeline = [
        {"$group": {"_id": "$group", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10},
    ]
    top_groups = await db.tv_categories.aggregate(pipeline).to_list(10)
    stats["top_groups"] = [{"group": g["_id"], "count": g["count"]} for g in top_groups]
    # Lesson type distribution
    type_pipeline = [
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    type_dist = await db.tv_lessons.aggregate(type_pipeline).to_list(10)
    stats["lesson_types"] = [{"type": t["_id"], "count": t["count"]} for t in type_dist]
    return stats

@router.get("/admin/cms/content-health")
async def cms_content_health():
    db = get_db()
    # Categories without lessons
    all_cat_ids = [c["id"] async for c in db.tv_categories.find({}, {"_id": 0, "id": 1})]
    lessons_by_cat = {}
    async for lesson_doc in db.tv_lessons.find({}, {"_id": 0, "category_id": 1}):
        cid = lesson_doc.get("category_id", "")
        lessons_by_cat[cid] = lessons_by_cat.get(cid, 0) + 1
    empty_cats = [cid for cid in all_cat_ids if cid not in lessons_by_cat]
    # Recent content (last 7 days)
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_lessons = await db.tv_lessons.count_documents({"created_at": {"$gte": week_ago}})
    return {
        "total_categories": len(all_cat_ids),
        "categories_with_lessons": len(all_cat_ids) - len(empty_cats),
        "empty_categories": len(empty_cats),
        "empty_category_ids": empty_cats[:20],
        "recent_lessons_7d": recent_lessons,
        "health_score": round((1 - len(empty_cats) / max(len(all_cat_ids), 1)) * 100),
    }

@router.get("/admin/cms/user-engagement")
async def cms_user_engagement():
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Daily active users
    dau = await db.tv_daily_usage.distinct("user_id", {"date": today})
    # Top lessons by completion
    top_completed = await db.tv_user_progress.aggregate([
        {"$match": {"completed": True}},
        {"$group": {"_id": "$lesson_id", "completions": {"$sum": 1}}},
        {"$sort": {"completions": -1}}, {"$limit": 10},
    ]).to_list(10)
    # Enrich with lesson titles
    for tc in top_completed:
        lesson = await db.tv_lessons.find_one({"lesson_id": tc["_id"]}, {"_id": 0, "title": 1})
        tc["title"] = lesson.get("title", "Unknown") if lesson else "Unknown"
    # Quiz pass rate
    total_quizzes = await db.tv_quiz_results.count_documents({})
    passed_quizzes = await db.tv_quiz_results.count_documents({"passed": True})
    return {
        "daily_active_users": len(dau),
        "total_quiz_submissions": total_quizzes,
        "quiz_pass_rate": round(passed_quizzes / max(total_quizzes, 1) * 100, 1),
        "top_completed_lessons": top_completed,
    }

@router.post("/admin/cms/bulk-update-tier")
async def bulk_update_category_tier(group: str = Body(...), new_tier: str = Body(...)):
    db = get_db()
    if new_tier not in ("free", "basic", "premium"):
        raise HTTPException(status_code=400, detail="Invalid tier")
    result = await db.tv_categories.update_many({"group": group}, {"$set": {"tier": new_tier}})
    return {"updated": result.modified_count, "group": group, "new_tier": new_tier}

# ══════════════════════════════════════
# OBJECT STORAGE (MongoDB GridFS-like via binary docs)
# ══════════════════════════════════════

@router.post("/storage/upload")
async def upload_media_file(
    file: UploadFile = File(...),
    user_id: str = Query(...),
    file_type: str = Query(default="media"),
    lesson_id: Optional[str] = Query(default=None),
):
    db = get_db()
    content = await file.read()
    max_size = 50 * 1024 * 1024  # 50MB
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    allowed_types = ["video/mp4", "audio/mpeg", "audio/wav", "audio/mp4", "application/pdf", "image/jpeg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed")
    file_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "")
    s3_bucket = os.environ.get("S3_BUCKET", "")
    s3_key_id = os.environ.get("S3_ACCESS_KEY_ID", "")
    s3_secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    s3_url = None

    if s3_endpoint and s3_bucket and s3_key_id and s3_secret:
        # ── External S3/MinIO storage ──
        try:
            import boto3
            s3_client = boto3.client(
                "s3", endpoint_url=s3_endpoint,
                aws_access_key_id=s3_key_id, aws_secret_access_key=s3_secret,
            )
            s3_object_key = f"travel-visa/{file_type}/{file_id}/{file.filename}"
            await asyncio.to_thread(
                s3_client.put_object, Bucket=s3_bucket, Key=s3_object_key,
                Body=content, ContentType=file.content_type,
            )
            s3_url = f"{s3_endpoint}/{s3_bucket}/{s3_object_key}"
            await db.tv_storage.insert_one({
                "file_id": file_id, "filename": file.filename,
                "content_type": file.content_type, "size_bytes": len(content),
                "file_type": file_type, "storage": "s3",
                "s3_bucket": s3_bucket, "s3_key": s3_object_key, "s3_url": s3_url,
                "uploaded_by": user_id, "lesson_id": lesson_id, "created_at": now,
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")
    else:
        # ── MongoDB fallback storage ──
        chunk_size = 10 * 1024 * 1024
        chunks = []
        for i in range(0, len(content), chunk_size):
            chunk = base64.b64encode(content[i:i+chunk_size]).decode('ascii')
            chunks.append(chunk)
        await db.tv_storage.insert_one({
            "file_id": file_id, "filename": file.filename,
            "content_type": file.content_type, "size_bytes": len(content),
            "file_type": file_type, "storage": "mongodb",
            "chunks": chunks, "chunk_count": len(chunks),
            "uploaded_by": user_id, "lesson_id": lesson_id, "created_at": now,
        })

    if lesson_id:
        media_url = s3_url or f"/api/travel-visa/storage/stream/{file_id}"
        await db.tv_lessons.update_one(
            {"lesson_id": lesson_id},
            {"$set": {"media_url": media_url, "storage_file_id": file_id}},
        )
    return {"file_id": file_id, "filename": file.filename, "size_bytes": len(content), "content_type": file.content_type, "storage": "s3" if s3_url else "mongodb"}

@router.get("/storage/stream/{file_id}")
async def stream_media_file(file_id: str):
    db = get_db()
    doc = await db.tv_storage.find_one({"file_id": file_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    if doc.get("storage") == "s3":
        # Stream from S3/MinIO
        s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "")
        s3_key_id = os.environ.get("S3_ACCESS_KEY_ID", "")
        s3_secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
        try:
            import boto3
            s3_client = boto3.client(
                "s3", endpoint_url=s3_endpoint,
                aws_access_key_id=s3_key_id, aws_secret_access_key=s3_secret,
            )
            response = await asyncio.to_thread(
                s3_client.get_object, Bucket=doc["s3_bucket"], Key=doc["s3_key"],
            )
            content = await asyncio.to_thread(response["Body"].read)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 read failed: {str(e)}")
    else:
        # Read from MongoDB chunks
        content = b""
        for chunk in doc.get("chunks", []):
            content += base64.b64decode(chunk)

    return StreamingResponse(
        io.BytesIO(content),
        media_type=doc["content_type"],
        headers={"Content-Disposition": f'inline; filename="{doc["filename"]}"'},
    )

@router.get("/storage/list")
async def list_stored_files(file_type: Optional[str] = None, user_id: Optional[str] = None):
    db = get_db()
    query = {}
    if file_type:
        query["file_type"] = file_type
    if user_id:
        query["uploaded_by"] = user_id
    files = await db.tv_storage.find(query, {"_id": 0, "chunks": 0}).sort("created_at", -1).to_list(100)
    return {"files": files, "total": len(files)}

@router.delete("/storage/{file_id}")
async def delete_stored_file(file_id: str):
    db = get_db()
    result = await db.tv_storage.delete_one({"file_id": file_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted", "file_id": file_id}

# ══════════════════════════════════════
# EMAIL NOTIFICATION DELIVERY
# ══════════════════════════════════════

TV_EMAIL_TEMPLATE_MAP = {
    "test": "travel_visa_test_notification",
    "achievement": "travel_visa_achievement_notification",
    "notification": "travel_visa_general_notification",
}


def _resolve_feature23_template_key(email_type: str) -> str:
    normalized = str(email_type or "notification").strip().lower().replace("-", "_").replace(" ", "_")
    return TV_EMAIL_TEMPLATE_MAP.get(normalized, f"travel_visa_{normalized}_notification")


def _html_to_plain_text(html_content: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", str(html_content or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:1500]

async def _send_email(db, to_email: str, subject: str, html_content: str, email_type: str = "notification"):
    """Send email through centralized v7 template sender with explicit template_key."""
    from utils.email_service import send_template_email

    now = datetime.now(timezone.utc).isoformat()
    template_key = _resolve_feature23_template_key(email_type)
    plain_message = _html_to_plain_text(html_content)

    email_record = {
        "email_id": str(uuid.uuid4())[:12],
        "to": to_email,
        "subject": subject,
        "html_content": html_content,
        "email_type": email_type,
        "template_key": template_key,
        "status": "pending",
        "created_at": now,
    }

    result = await send_template_email(
        recipient_email=to_email,
        template_key=template_key,
        data={
            "subject": subject,
            "message": plain_message,
            "email_type": str(email_type or "notification"),
            "sent_at": now,
        },
        subject=subject,
    )

    if result.get("success"):
        email_record["status"] = "sent"
        message_id = result.get("message_id")
        if message_id:
            email_record["resend_id"] = message_id
    else:
        error_message = str(result.get("error") or "unknown email failure")
        if "not configured" in error_message.lower():
            email_record["status"] = "queued_no_provider"
        else:
            email_record["status"] = "failed"
        email_record["error"] = error_message

    await db.tv_email_log.insert_one(email_record)
    return email_record["status"]

@router.post("/email/send-test")
async def send_test_email(to: str = Body(...), subject: str = Body(default="Travel Visa Test Email")):
    db = get_db()
    body_html = (
        "<p>This is a test email from your <strong>Travel Visa</strong> notification system.</p>"
        f"<p>Sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.</p>"
    )
    status = await _send_email(db, to, subject, body_html, "test")
    return {
        "status": status,
        "to": to,
        "template_key": _resolve_feature23_template_key("test"),
    }

@router.get("/email/log")
async def get_email_log(limit: int = Query(default=50)):
    db = get_db()
    emails = await db.tv_email_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    stats = {
        "total": await db.tv_email_log.count_documents({}),
        "sent": await db.tv_email_log.count_documents({"status": "sent"}),
        "failed": await db.tv_email_log.count_documents({"status": "failed"}),
        "queued": await db.tv_email_log.count_documents({"status": "queued_no_provider"}),
    }
    return {"emails": emails, "stats": stats}

async def send_notification_email(db, user_id: str, subject: str, body_html: str, email_type: str):
    """Send notification via centralized v7 template sender when prefs allow."""
    prefs = await db.tv_notification_prefs.find_one({"user_id": user_id}, {"_id": 0})
    if not prefs or not prefs.get("email_notifications", False):
        return "skipped_prefs"
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    if not user or not user.get("email"):
        return "no_email"

    return await _send_email(db, user["email"], subject, body_html, email_type)

# ══════════════════════════════════════
# ACHIEVEMENT AUTO-GRANT SYSTEM
# ══════════════════════════════════════

ACHIEVEMENT_RULES = [
    {"id": "first-lesson", "field": "lessons_completed", "threshold": 1},
    {"id": "five-lessons", "field": "lessons_completed", "threshold": 5},
    {"id": "ten-lessons", "field": "lessons_completed", "threshold": 10},
    {"id": "first-quiz", "field": "quizzes_passed", "threshold": 1},
    {"id": "five-quizzes", "field": "quizzes_passed", "threshold": 5},
    {"id": "first-simulation", "field": "simulations_completed", "threshold": 1},
    {"id": "five-simulations", "field": "simulations_completed", "threshold": 5},
    {"id": "first-coaching", "field": "coaching_sessions", "threshold": 1},
    {"id": "streak-3", "field": "streak", "threshold": 3},
    {"id": "streak-7", "field": "streak", "threshold": 7},
    {"id": "streak-30", "field": "streak", "threshold": 30},
    {"id": "country-explorer", "field": "countries_explored", "threshold": 5},
    {"id": "readiness-50", "field": "readiness_score", "threshold": 50},
    {"id": "readiness-80", "field": "readiness_score", "threshold": 80},
    {"id": "readiness-100", "field": "readiness_score", "threshold": 100},
]

async def check_and_grant_achievements(db, user_id: str):
    """Check all achievement rules and grant any newly earned"""
    stats = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        return []
    earned_ids = set()
    earned_docs = await db.tv_user_achievements.find({"user_id": user_id}, {"_id": 0, "achievement_id": 1}).to_list(50)
    for e in earned_docs:
        earned_ids.add(e["achievement_id"])
    # Calculate readiness
    total_lessons = await db.tv_lessons.count_documents({})
    completed = stats.get("lessons_completed", 0)
    quizzes = stats.get("quizzes_passed", 0)
    sims = stats.get("simulations_completed", 0)
    coaching = stats.get("coaching_sessions", 0)
    readiness = min(100, round((completed * 2 + quizzes * 5 + sims * 10 + coaching * 3) / max(1, total_lessons * 0.5) * 100))
    stats["readiness_score"] = readiness
    newly_earned = []
    now = datetime.now(timezone.utc).isoformat()
    for rule in ACHIEVEMENT_RULES:
        if rule["id"] in earned_ids:
            continue
        value = stats.get(rule["field"], 0)
        if value >= rule["threshold"]:
            # Grant achievement
            catalog = await db.tv_achievements_catalog.find_one({"id": rule["id"]}, {"_id": 0})
            if catalog:
                await db.tv_user_achievements.insert_one({
                    "user_id": user_id, "achievement_id": rule["id"],
                    "name": catalog.get("name", ""), "description": catalog.get("description", ""),
                    "icon": catalog.get("icon", ""), "xp_reward": catalog.get("xp_reward", 0),
                    "earned_at": now,
                })
                # Award XP
                xp = catalog.get("xp_reward", 0)
                if xp > 0:
                    await db.tv_user_stats.update_one({"user_id": user_id}, {"$inc": {"total_xp": xp}})
                newly_earned.append({"id": rule["id"], "name": catalog.get("name"), "xp": xp})
                # Send notification
                await db.tv_notifications.insert_one({
                    "user_id": user_id, "type": "achievement",
                    "title": f"Achievement Unlocked: {catalog.get('name', '')}!",
                    "message": f"{catalog.get('description', '')} (+{xp} XP)",
                    "data": {"achievement_id": rule["id"]},
                    "read": False, "created_at": now,
                })
                # Send email notification
                html = f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
                    <h2 style="color:#1a73e8;">Achievement Unlocked!</h2>
                    <div style="background:#f0f7ff;padding:20px;border-radius:12px;text-align:center;">
                        <h3>{catalog.get('name', '')}</h3>
                        <p>{catalog.get('description', '')}</p>
                        <p style="font-size:24px;font-weight:bold;color:#1a73e8;">+{xp} XP</p>
                    </div>
                    <p style="color:#666;font-size:12px;margin-top:16px;">Keep learning on Travel Visa Academy!</p>
                </div>"""
                await send_notification_email(db, user_id, f"Achievement: {catalog.get('name')}", html, "achievement")
    return newly_earned

@router.post("/achievements/check/{user_id}")
async def trigger_achievement_check(user_id: str):
    db = get_db()
    newly_earned = await check_and_grant_achievements(db, user_id)
    return {"newly_earned": newly_earned, "count": len(newly_earned)}

# ══════════════════════════════════════
# CERTIFICATE / BADGE PDF GENERATION
# ══════════════════════════════════════

def _format_cert_date(value: Optional[str]) -> str:
    """Normalize a stored ISO timestamp (or preformatted date) to 'Month DD, YYYY'."""
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%B %d, %Y")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except ValueError:
        return raw


def _certificate_verify_url(cert_id: str) -> str:
    base = os.environ.get('FRONTEND_BASE_URL', 'https://realaicoach.app')
    return f"{base}/api/travel-visa/certificate/verify/{cert_id}"


def _generate_certificate_pdf(user_name: str, course_title: str, completion_date: str, cert_id: str, score: Optional[int] = None) -> bytes:
    """Premium enterprise certificate — canonical v15 palette, certificate-grade composition."""
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from services.pdf_v15_theme import PALETTE, get_canonical_logo_tile_path

    buffer = io.BytesIO()
    W, H = landscape(A4)
    c = pdf_canvas.Canvas(buffer, pagesize=landscape(A4))
    cx = W / 2
    verify_url = _certificate_verify_url(cert_id)

    def _spaced(text: str) -> str:
        return "  ".join(list(text))

    # ── Ornamental double border ──
    c.setStrokeColor(PALETTE["primary"])
    c.setLineWidth(3)
    c.rect(22, 22, W - 44, H - 44)
    c.setStrokeColor(PALETTE["teal"])
    c.setLineWidth(0.9)
    c.rect(31, 31, W - 62, H - 62)
    # Corner diamonds on the inner rule
    c.setFillColor(PALETTE["teal"])
    for dx, dy in [(31, 31), (W - 31, 31), (31, H - 31), (W - 31, H - 31)]:
        p = c.beginPath()
        p.moveTo(dx, dy + 5); p.lineTo(dx + 5, dy); p.lineTo(dx, dy - 5); p.lineTo(dx - 5, dy); p.close()
        c.drawPath(p, fill=1, stroke=0)

    # ── Brand masthead ──
    y = H - 74
    logo_path = get_canonical_logo_tile_path()
    brand = "RealAICoach"
    c.setFont("Helvetica-Bold", 17)
    brand_w = c.stringWidth(brand, "Helvetica-Bold", 17)
    if logo_path:
        try:
            from reportlab.lib.utils import ImageReader
            tile = 26
            total_w = tile + 10 + brand_w
            c.drawImage(ImageReader(logo_path), cx - total_w / 2, y - 7, width=tile, height=tile, preserveAspectRatio=True, mask="auto")
            c.setFillColor(PALETTE["primary"])
            c.drawString(cx - total_w / 2 + tile + 10, y, brand)
        except Exception:
            c.setFillColor(PALETTE["primary"])
            c.drawCentredString(cx, y, brand)
    else:
        c.setFillColor(PALETTE["primary"])
        c.drawCentredString(cx, y, brand)
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(cx, y - 26, _spaced("TRAVEL VISA ACADEMY"))

    # ── Eyebrow title ──
    y -= 64
    c.setFillColor(PALETTE["ink"])
    c.setFont("Helvetica-Bold", 21)
    c.drawCentredString(cx, y, _spaced("CERTIFICATE OF COMPLETION"))
    c.setStrokeColor(PALETTE["teal"])
    c.setLineWidth(1.4)
    c.line(cx - 60, y - 12, cx + 60, y - 12)

    # ── Presentation line ──
    y -= 44
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, y, "This certificate is proudly presented to")

    # ── Recipient name ──
    y -= 42
    name_size = 34
    while c.stringWidth(user_name, "Helvetica-Bold", name_size) > W - 220 and name_size > 18:
        name_size -= 2
    c.setFillColor(PALETTE["primary"])
    c.setFont("Helvetica-Bold", name_size)
    c.drawCentredString(cx, y, user_name)
    name_w = c.stringWidth(user_name, "Helvetica-Bold", name_size)
    c.setStrokeColor(PALETTE["teal"])
    c.setLineWidth(1.5)
    c.line(cx - name_w / 2 - 22, y - 10, cx + name_w / 2 + 22, y - 10)

    # ── Course line ──
    y -= 38
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, y, "for successfully completing the course")
    y -= 30
    course_size = 20
    while c.stringWidth(course_title, "Helvetica-Bold", course_size) > W - 200 and course_size > 13:
        course_size -= 1
    c.setFillColor(PALETTE["ink"])
    c.setFont("Helvetica-Bold", course_size)
    c.drawCentredString(cx, y, course_title)

    # ── Score medallion (or issue-date line) ──
    y -= 66
    if score is not None:
        ring_ok = score >= 70
        ring_color = PALETTE["success"] if ring_ok else PALETTE["warning"]
        c.setStrokeColor(ring_color)
        c.setLineWidth(3)
        c.circle(cx, y, 30, stroke=1, fill=0)
        c.setStrokeColor(PALETTE["border_soft"])
        c.setLineWidth(0.8)
        c.circle(cx, y, 24, stroke=1, fill=0)
        c.setFillColor(PALETTE["primary"])
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(cx, y - 5, f"{score}%")
        c.setFillColor(PALETTE["slate"])
        c.setFont("Helvetica", 6.5)
        c.drawCentredString(cx, y - 42, _spaced("FINAL SCORE"))
    else:
        c.setFillColor(PALETTE["slate"])
        c.setFont("Helvetica", 10)
        c.drawCentredString(cx, y, f"Issued {completion_date}")

    # ── Bottom row: signature | certified stamp | verification panel ──
    base_y = 74
    branding_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "branding")
    # Signature block (left) — professional handwritten signature
    sig_x = 78
    try:
        from reportlab.lib.utils import ImageReader
        sig_path = os.path.join(branding_dir, "adjimon-signature-handwritten.png")
        if os.path.exists(sig_path):
            from PIL import Image as PILImage, ImageChops
            sig_img = PILImage.open(sig_path).convert("RGB")
            bg = PILImage.new("RGB", sig_img.size, (255, 255, 255))
            bbox = ImageChops.difference(sig_img, bg).getbbox()
            if bbox:
                pad = 10
                bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                        min(sig_img.width, bbox[2] + pad), min(sig_img.height, bbox[3] + pad))
                sig_img = sig_img.crop(bbox)
            sig_h = 64
            sig_w = min(150, sig_h * sig_img.width / max(1, sig_img.height))
            c.drawImage(ImageReader(sig_img), sig_x + 8, base_y + 36, width=sig_w, height=sig_h, preserveAspectRatio=True, mask="auto")
    except Exception:
        pass
    c.setStrokeColor(PALETTE["ink"])
    c.setLineWidth(0.9)
    c.line(sig_x, base_y + 34, sig_x + 150, base_y + 34)
    c.setFillColor(PALETTE["ink"])
    c.setFont("Helvetica-Bold", 10)
    c.drawString(sig_x, base_y + 21, "Adjimon Kouatonou — Program Director")
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 8)
    c.drawString(sig_x, base_y + 9, "RealAICoach Travel Visa Academy")
    c.drawString(sig_x, base_y - 3, f"Issued {completion_date}")

    # Certified stamp (center) — same official stamp as the Learning Hub certificate
    stamp_drawn = False
    try:
        from reportlab.lib.utils import ImageReader
        stamp_path = os.path.join(branding_dir, "certified-stamp.png")
        if os.path.exists(stamp_path):
            stamp_size = 74
            c.drawImage(ImageReader(stamp_path), cx - stamp_size / 2, base_y - 12, width=stamp_size, height=stamp_size, preserveAspectRatio=True, mask="auto")
            stamp_drawn = True
    except Exception:
        pass
    if not stamp_drawn:
        seal_y = base_y + 22
        c.setStrokeColor(PALETTE["primary"])
        c.setLineWidth(2)
        c.circle(cx, seal_y, 27, stroke=1, fill=0)
        c.setFillColor(PALETTE["primary"])
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(cx, seal_y - 4, "RAC")
        c.setFillColor(PALETTE["slate"])
        c.setFont("Helvetica", 6)
        c.drawCentredString(cx, seal_y - 37, _spaced("CERTIFIED"))

    # Verification panel (right)
    panel_w, panel_h = 208, 84
    panel_x = W - 72 - panel_w
    panel_y = base_y - 12
    c.setFillColor(PALETTE["slate_soft"])
    c.setStrokeColor(PALETTE["border_soft"])
    c.setLineWidth(0.9)
    c.roundRect(panel_x, panel_y, panel_w, panel_h, 8, stroke=1, fill=1)
    qr_drawn = False
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=1)
        qr.add_data(verify_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0F766E", back_color="#FFFFFF")
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        c.drawImage(ImageReader(qr_buf), panel_x + 11, panel_y + 11, width=62, height=62, preserveAspectRatio=True, mask="auto")
        qr_drawn = True
    except Exception:
        pass
    tx0 = panel_x + (84 if qr_drawn else 14)
    label_max_w = panel_x + panel_w - 12 - tx0
    c.setFillColor(PALETTE["primary"])
    label = " ".join(list("VERIFY AUTHENTICITY"))
    label_size = 7.0
    while c.stringWidth(label, "Helvetica-Bold", label_size) > label_max_w and label_size > 5.5:
        label_size -= 0.25
    if c.stringWidth(label, "Helvetica-Bold", label_size) > label_max_w:
        label = "VERIFY AUTHENTICITY"
        label_size = 7.0
        while c.stringWidth(label, "Helvetica-Bold", label_size) > label_max_w and label_size > 5.5:
            label_size -= 0.25
    c.setFont("Helvetica-Bold", label_size)
    c.drawString(tx0, panel_y + 64, label)
    c.setFillColor(PALETTE["ink"])
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(tx0, panel_y + 49, cert_id)
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 7)
    c.drawString(tx0, panel_y + 37, "Scan the QR code or visit the")
    c.drawString(tx0, panel_y + 27, "verification link in the footer to")
    c.drawString(tx0, panel_y + 17, "confirm this credential instantly.")

    # ── Footer rule + verify link ──
    c.setStrokeColor(PALETTE["border_soft"])
    c.setLineWidth(0.7)
    c.line(60, 48, W - 60, 48)
    c.setFillColor(PALETTE["slate"])
    c.setFont("Helvetica", 7)
    c.drawCentredString(cx, 37, f"Certificate {cert_id}  •  Issued {completion_date}  •  Verify: {verify_url}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

@router.post("/certificate/generate")
async def generate_certificate(
    user_id: str = Body(...),
    course_title: str = Body(...),
    score: Optional[int] = Body(default=None),
):
    db = get_db()
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1})
    user_name = user.get("name", user.get("email", "Learner")) if user else "Learner"
    cert_id = f"TV-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.now(timezone.utc)
    completion_date = now.strftime("%B %d, %Y")
    pdf_bytes = _generate_certificate_pdf(user_name, course_title, completion_date, cert_id, score)
    # Store certificate in DB
    cert_doc = {
        "cert_id": cert_id, "user_id": user_id, "user_name": user_name,
        "course_title": course_title, "score": score,
        "pdf_base64": base64.b64encode(pdf_bytes).decode('ascii'),
        "created_at": now.isoformat(),
    }
    await db.tv_certificates.insert_one(dict(cert_doc))
    email_status = "skipped"
    try:
        email_status = await _send_certificate_award_email(db, cert_doc)
    except Exception:
        email_status = "failed"
    return {"cert_id": cert_id, "user_name": user_name, "course_title": course_title, "completion_date": completion_date, "email_status": email_status}

@router.get("/certificate/download/{cert_id}")
async def download_certificate(cert_id: str):
    db = get_db()
    cert = await db.tv_certificates.find_one({"cert_id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    pdf_bytes = base64.b64decode(cert["pdf_base64"])
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="certificate_{cert_id}.pdf"'},
    )

@router.get("/certificate/verify/{cert_id}")
async def verify_certificate(cert_id: str, format: Optional[str] = Query(default=None)):
    """Public certificate verification — branded HTML page (QR target) or JSON."""
    from fastapi.responses import HTMLResponse, JSONResponse
    db = get_db()
    normalized = str(cert_id or "").strip().upper()
    cert = await db.tv_certificates.find_one({"cert_id": normalized}, {"_id": 0, "pdf_base64": 0})
    payload = {
        "cert_id": normalized,
        "valid": bool(cert),
        "recipient": cert.get("user_name") if cert else None,
        "course_title": cert.get("course_title") if cert else None,
        "score": cert.get("score") if cert else None,
        "issued_at": cert.get("created_at") if cert else None,
        "issuer": "RealAICoach Travel Visa Academy",
    }
    if format == "json":
        if not payload["valid"]:
            return JSONResponse(status_code=404, content=payload)
        return payload
    ok = payload["valid"]
    tone = "#0F766E" if ok else "#B91C1C"
    tone_soft = "#F0FDFA" if ok else "#FEF2F2"
    status_label = "VALID CERTIFICATE" if ok else "NOT FOUND"
    detail_rows = ""
    if ok:
        issued = str(payload["issued_at"] or "")[:10]
        score_row = f'<tr><td>Score</td><td><strong>{payload["score"]}%</strong></td></tr>' if payload.get("score") is not None else ""
        detail_rows = f"""
        <tr><td>Recipient</td><td><strong>{payload['recipient']}</strong></td></tr>
        <tr><td>Course</td><td><strong>{payload['course_title']}</strong></td></tr>
        {score_row}
        <tr><td>Issued</td><td><strong>{issued}</strong></td></tr>
        <tr><td>Issuer</td><td><strong>{payload['issuer']}</strong></td></tr>"""
    body_note = (
        "This credential was issued by RealAICoach and is authentic."
        if ok else
        "No certificate matches this ID. The credential may have been revoked or the ID mistyped."
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Certificate Verification — {normalized}</title>
<style>
  body {{ margin:0; font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; background:#F1F5F9; color:#0F172A; }}
  .card {{ max-width:520px; margin:48px auto; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:16px; overflow:hidden; box-shadow:0 10px 40px rgba(15,23,42,.08); }}
  .head {{ background:{tone}; color:#FFFFFF; padding:26px 28px; }}
  .head .brand {{ font-size:13px; font-weight:800; letter-spacing:2px; opacity:.85; }}
  .head h1 {{ margin:8px 0 0; font-size:22px; }}
  .badge {{ display:inline-block; margin-top:12px; background:{tone_soft}; color:{tone}; font-size:11px; font-weight:800; letter-spacing:1.5px; padding:6px 14px; border-radius:999px; }}
  .body {{ padding:26px 28px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  td {{ padding:9px 0; border-bottom:1px solid #F1F5F9; color:#475569; }}
  td+td {{ text-align:right; color:#0F172A; }}
  .note {{ margin-top:18px; font-size:12.5px; color:#475569; line-height:1.6; }}
  .cert-id {{ font-family: ui-monospace, Menlo, monospace; font-size:15px; font-weight:700; color:{tone}; }}
  .foot {{ padding:16px 28px; background:#F8FAFC; border-top:1px solid #E2E8F0; font-size:11px; color:#94A3B8; }}
</style></head><body>
<div class="card" data-testid="tv-cert-verify-card">
  <div class="head"><div class="brand">REALAICOACH · TRAVEL VISA ACADEMY</div>
    <h1>Certificate Verification</h1>
    <div class="badge" data-testid="tv-cert-verify-status">{status_label}</div></div>
  <div class="body">
    <p class="cert-id">{normalized}</p>
    <table>{detail_rows}</table>
    <p class="note">{body_note}</p>
  </div>
  <div class="foot">RealAICoach enterprise credential verification · Educational &amp; coaching purposes only</div>
</div></body></html>"""
    return HTMLResponse(content=html, status_code=200 if ok else 404)

async def _send_certificate_award_email(db, cert: dict) -> str:
    """Send the v7 certificate award email with the PDF attached."""
    from utils.email_service import send_email, is_email_configured
    from utils.email_templates import build_travel_visa_certificate_email

    if not is_email_configured():
        return "queued_no_provider"
    user = await db.users.find_one({"user_id": cert.get("user_id")}, {"_id": 0, "email": 1, "name": 1})
    if not user or not user.get("email"):
        return "no_recipient"
    cert_id = cert["cert_id"]
    verify_url = _certificate_verify_url(cert_id)
    download_url = f"{os.environ.get('FRONTEND_BASE_URL', 'https://realaicoach.app')}/api/travel-visa/certificate/download/{cert_id}"
    tpl = build_travel_visa_certificate_email(
        learner_name=cert.get("user_name") or user.get("name") or "Learner",
        course_title=cert.get("course_title") or "Travel Visa Course",
        cert_id=cert_id,
        score=cert.get("score"),
        issued_date=str(cert.get("created_at") or "")[:10],
        verify_url=verify_url,
        download_url=download_url,
    )
    result = await send_email(
        recipient_email=user["email"],
        subject=tpl.subject,
        content=tpl.html,
        recipient_name=cert.get("user_name") or "Learner",
        template_key="travel_visa_certificate_award",
        skip_branding=True,
        attachments=[{
            "filename": f"realaicoach-travel-visa-certificate-{cert_id}.pdf",
            "content": cert["pdf_base64"],
            "content_type": "application/pdf",
        }],
    )
    status = "sent" if result.get("success") else "failed"
    await db.tv_email_log.insert_one({
        "email_id": str(uuid.uuid4())[:12],
        "to": user["email"],
        "subject": tpl.subject,
        "email_type": "certificate_award",
        "template_key": "travel_visa_certificate_award",
        "cert_id": cert_id,
        "status": status,
        "error": None if result.get("success") else str(result.get("error") or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return status

@router.post("/certificate/email/{cert_id}")
async def email_certificate(cert_id: str, user_id: str = Body(..., embed=True)):
    """Send (or resend) the certificate award email with the PDF attached."""
    db = get_db()
    cert = await db.tv_certificates.find_one({"cert_id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your certificate")
    status = await _send_certificate_award_email(db, cert)
    return {"cert_id": cert_id, "email_status": status}

@router.get("/certificate/list/{user_id}")
async def list_certificates(user_id: str):
    db = get_db()
    certs = await db.tv_certificates.find({"user_id": user_id}, {"_id": 0, "pdf_base64": 0}).sort("created_at", -1).to_list(50)
    return {"certificates": certs, "total": len(certs)}

@router.post("/certificate/regenerate/{cert_id}")
async def regenerate_certificate(cert_id: str, user_id: str = Body(..., embed=True)):
    """Regenerate an existing certificate PDF with current FRONTEND_BASE_URL."""
    db = get_db()
    cert = await db.tv_certificates.find_one({"cert_id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your certificate")
    pdf_bytes = _generate_certificate_pdf(
        cert["user_name"], cert["course_title"],
        _format_cert_date(cert.get("created_at")),
        cert_id, cert.get("score"),
    )
    await db.tv_certificates.update_one(
        {"cert_id": cert_id},
        {"$set": {"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"), "regenerated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"cert_id": cert_id, "regenerated": True}

@router.post("/certificate/regenerate-all")
async def regenerate_all_certificates(user_id: str = Body(..., embed=True)):
    """Regenerate all certificates for a user with current FRONTEND_BASE_URL."""
    db = get_db()
    certs = await db.tv_certificates.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    if not certs:
        return {"regenerated": 0, "total": 0}
    now_iso = datetime.now(timezone.utc).isoformat()
    regenerated = 0
    for cert in certs:
        try:
            pdf_bytes = _generate_certificate_pdf(
                cert["user_name"],
                cert["course_title"],
                _format_cert_date(cert.get("created_at")),
                cert.get("cert_id"),
                cert.get("score"),
            )
            await db.tv_certificates.update_one(
                {"cert_id": cert.get("cert_id")},
                {
                    "$set": {
                        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                        "regenerated_at": now_iso,
                    }
                },
            )
            regenerated += 1
        except Exception:
            continue

    return {"regenerated": regenerated, "total": len(certs)}