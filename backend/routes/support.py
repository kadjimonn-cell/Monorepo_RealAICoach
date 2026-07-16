"""Support routes: FAQ, Feedback, Support Chat, Attachments, Audio, Nova Analytics, Export."""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
import os
import io
import tempfile
import csv
import json
import base64
import re
from .db import db, EMERGENT_LLM_KEY, logger, get_current_user
from utils.email_service import (
    send_catalog_template,
    is_email_configured,
)
from utils.field_encryption import encrypt_field, hash_lookup, decrypt_doc
from utils.file_security_service import enforce_file_security
from utils.pagination import iter_find_paginated
from utils.pdf_v15_filename import build_pdf_v15_filename
from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter()


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")
    return themed

# Encrypted PII fields
_TICKET_ENC_FIELDS = ("name", "email", "message")
_FEEDBACK_ENC_FIELDS = ("email", "message")

SUPPORT_EMAIL_ALLOWED_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "application/pdf",
    "application/octet-stream",
    "text/plain",
    "text/csv",
    "application/json",
}
SUPPORT_EMAIL_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
SUPPORT_EMAIL_MAX_ATTACHMENTS = 3
SUPPORT_EMAIL_ALLOWED_CATEGORIES = {"general", "billing", "technical", "account", "feature_request", "bug", "other"}
SUPPORT_EMAIL_ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}


# GPS-only FAQ/content policy: no hardcoded FAQ catalogs or UI label dictionaries are allowed.


async def _get_live_gps_state() -> Dict[str, Any]:
    from routes.global_platform_state import get_global_platform_state

    return await get_global_platform_state()


def _gps_label(ui_labels: Dict[str, Any], key: str) -> str:
    value = ui_labels.get(key)
    return str(value).strip() if value is not None else ""


@router.get("/support/faq")
async def get_faq(lang: str = "en"):
    """Get FAQs from GlobalPlatformState (GPS) and DB-backed FAQ content."""
    lang = lang.lower()[:2]

    gps_state = await _get_live_gps_state()

    gps_faq = []
    if gps_state:
        rows = gps_state.get("faq") or []
        gps_faq = [
            {"q": f.get("question", ""), "a": f.get("answer", ""), "category": f.get("category", "general")}
            for f in rows
            if f.get("active", True) and str(f.get("lang", "en"))[:2] == lang and f.get("question") and f.get("answer")
        ]

    if gps_faq:
        faqs = gps_faq
    else:
        db_faqs = await db.faq_content.find({"lang": lang, "active": True}, {"_id": 0}).sort("order", 1).to_list(200)
        faqs = [{"q": f["question"], "a": f["answer"], "category": f.get("category", "general")} for f in db_faqs]

    ui_labels = (gps_state or {}).get("ui_labels") or {}
    labels = {
        "faq_title": _gps_label(ui_labels, "help.faq_title"),
        "faq_subtitle": _gps_label(ui_labels, "help.faq_subtitle"),
        "nova_help": _gps_label(ui_labels, "help.nova_help"),
        "online": _gps_label(ui_labels, "common.online"),
        "all": _gps_label(ui_labels, "help.category.all"),
        "general": _gps_label(ui_labels, "help.category.general"),
        "features": _gps_label(ui_labels, "help.category.features"),
        "plans_billing": _gps_label(ui_labels, "help.category.plans"),
        "privacy_security": _gps_label(ui_labels, "help.category.security"),
    }
    return {"faqs": faqs, "labels": labels, "lang": lang}


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def _find_did_you_mean(query: str, all_faqs: list) -> Optional[str]:
    """Find a spelling correction by fuzzy-matching query words against FAQ keywords."""
    # Extract unique keywords (3+ chars) from all FAQ questions
    keywords = set()
    for faq in all_faqs:
        for word in faq["q"].lower().split():
            cleaned = word.strip("?.,!:;\"'()[]")
            if len(cleaned) >= 3:
                keywords.add(cleaned)

    # For each query word, find the closest keyword
    query_words = query.lower().split()
    corrections = []
    changed = False
    for qw in query_words:
        if len(qw) < 3:
            corrections.append(qw)
            continue
        # Skip if exact match exists
        if qw in keywords:
            corrections.append(qw)
            continue
        # Find closest keyword by edit distance
        best_word, best_dist = qw, 999
        for kw in keywords:
            # Only consider words of similar length
            if abs(len(kw) - len(qw)) > 3:
                continue
            dist = _levenshtein(qw, kw)
            # Prefer longer words at same distance (more specific matches)
            if dist < best_dist or (dist == best_dist and len(kw) > len(best_word)):
                best_dist = dist
                best_word = kw
        # Accept correction if distance is small enough (max 2 edits for short words, 3 for longer)
        max_dist = 2 if len(qw) <= 6 else 3
        if best_dist <= max_dist and best_word != qw:
            corrections.append(best_word)
            changed = True
        else:
            corrections.append(qw)

    if changed:
        return " ".join(corrections)
    return None


class SmartSearchRequest(BaseModel):
    query: str
    lang: str = "en"
    generate_ai: bool = False


@router.post("/support/faq/smart-search")
async def smart_search_faq(request: SmartSearchRequest):
    """Search FAQs with optional AI-generated answer when no results match."""
    query = request.query.strip().lower()
    lang = request.lang.lower()[:2]
    if not query or len(query) < 2:
        return {"suggestions": [], "ai_answer": None}

    gps_state = await _get_live_gps_state()
    gps_rows = (gps_state or {}).get("faq") or []
    all_faqs = [
        {"q": f.get("question", ""), "a": f.get("answer", ""), "category": f.get("category", "general")}
        for f in gps_rows
        if f.get("active", True) and str(f.get("lang", "en"))[:2] == lang and f.get("question") and f.get("answer")
    ]

    if not all_faqs:
        db_faqs = await db.faq_content.find({"lang": lang, "active": True}, {"_id": 0}).sort("order", 1).to_list(200)
        all_faqs = [{"q": f["question"], "a": f["answer"], "category": f.get("category", "general")} for f in db_faqs]

    # Score and rank matches
    scored = []
    for faq in all_faqs:
        q_lower = faq["q"].lower()
        a_lower = faq["a"].lower()
        score = 0
        if query in q_lower:
            score += 10
        if query in a_lower:
            score += 5
        # Word-level matching
        words = query.split()
        for w in words:
            if len(w) >= 3:
                if w in q_lower:
                    score += 3
                if w in a_lower:
                    score += 1
        if score > 0:
            scored.append({**faq, "_score": score})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    suggestions = [{"q": s["q"], "a": s["a"], "category": s["category"]} for s in scored[:5]]

    # "Did you mean?" — fuzzy match when few/no results
    did_you_mean = None
    if len(suggestions) < 2:
        did_you_mean = _find_did_you_mean(query, all_faqs)

    # Generate AI answer if requested and no/few suggestions
    ai_answer = None
    if request.generate_ai and len(suggestions) < 2:
        try:
            from services.nova_service import build_platform_context
            import uuid as uuid_mod

            context = await build_platform_context()
            system_prompt = """You are Nova, a friendly AI assistant for RealAICoach. Answer user questions concisely (2-4 sentences max). Be warm and helpful. If you're not sure, suggest contacting support@realaicoach.app."""
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"smart-search-{uuid_mod.uuid4().hex[:8]}",
                system_message=system_prompt,
            ).with_model("openai", "gpt-4o")
            user_message = f"""Platform context:
{context[:3000]}

User question: {request.query}

Provide a direct, helpful answer."""
            response = await chat.send_message(UserMessage(text=user_message))
            ai_answer = response.strip() if response else None
        except Exception as e:
            logger.error(f"Smart search AI generation failed: {e}")

    # Log search query for trending analytics (fire-and-forget)
    try:
        await db.faq_search_logs.insert_one(
            {
                "query": query,
                "lang": lang,
                "results_count": len(suggestions),
                "used_ai": request.generate_ai,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        pass

    return {"suggestions": suggestions, "ai_answer": ai_answer, "did_you_mean": did_you_mean, "query": request.query}


@router.post("/support/faq/voice-search")
async def voice_search_faq(audio: UploadFile = File(...)):
    """Transcribe audio for FAQ voice search (transcription only, no AI response)."""
    content = await audio.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio too large. Max 25MB.")
    if len(content) < 100:
        return {"transcription": "", "error": "Recording too short"}

    try:
        from emergentintegrations.llm.openai import OpenAISpeechToText

        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        ext = "webm"
        if audio.filename and "." in audio.filename:
            ext = audio.filename.rsplit(".", 1)[-1]
        tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
        tmp.write(content)
        tmp.close()
        with open(tmp.name, "rb") as af:
            response = await stt.transcribe(file=af, model="whisper-1", response_format="json")
            text = response.text.strip()
        os.unlink(tmp.name)
        return {"transcription": text}
    except Exception as e:
        logger.error(f"Voice search transcription error: {e}")
        return {"transcription": "", "error": "Could not transcribe audio"}


@router.get("/support/faq/trending")
async def get_trending_searches(days: int = 30, limit: int = 5):
    """Return the most popular FAQ search queries from the last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$query", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit + 5},  # fetch extra to deduplicate similar terms
    ]
    results = await db.faq_search_logs.aggregate(pipeline).to_list(limit + 5)

    # Deduplicate: if "subscription" and "subscriptions" both appear, keep the more popular one
    seen_roots = {}
    trending = []
    for r in results:
        term = r["_id"]
        root = term[:4] if len(term) >= 4 else term
        if root not in seen_roots:
            seen_roots[root] = True
            trending.append({"term": term, "count": r["count"]})
        if len(trending) >= limit:
            break

    return {"trending": trending}


class FAQFeedbackRequest(BaseModel):
    question: str
    helpful: bool


@router.post("/support/faq/feedback")
async def submit_faq_feedback(request: FAQFeedbackRequest):
    feedback_id = str(uuid.uuid4().hex[:12])
    await db.faq_feedback.insert_one(
        {
            "feedback_id": feedback_id,
            "question": request.question,
            "helpful": request.helpful,
            "status": "open",
            "admin_notes": [],
            "resolved_at": None,
            "responded_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "feedback_id": feedback_id}


# ── Admin FAQ CRUD ──


class FAQCreate(BaseModel):
    question: str
    answer: str
    category: str = "general"
    lang: str = "en"
    order: int = 0


FAQ_ADMIN_LANGS: tuple[str, ...] = ("en", "fr", "es", "de", "it", "pt")
FAQ_ADMIN_CATEGORIES: tuple[str, ...] = (
    "general",
    "account",
    "billing",
    "features",
    "security",
    "employer",
    "technical",
)


@router.post("/support/faq/admin/create")
async def admin_create_faq(payload: FAQCreate, request: Request):
    """Admin: Create a new FAQ entry in the database."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    faq_id = f"faq_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "faq_id": faq_id,
        "question": payload.question,
        "answer": payload.answer,
        "category": payload.category,
        "lang": payload.lang,
        "order": payload.order,
        "active": True,
        "created_by": user.user_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.faq_content.insert_one(doc)
    try:
        from routes.global_platform_state import sync_global_faq
        await sync_global_faq(reason="FAQ created by admin", actor_user_id=user.user_id)
    except Exception as exc:
        logger.warning(f"GPS FAQ sync warning (create): {exc}")
    doc.pop("_id", None)
    return {"success": True, "faq": doc}


@router.put("/support/faq/admin/{faq_id}")
async def admin_update_faq(faq_id: str, payload: FAQCreate, request: Request):
    """Admin: Update an existing FAQ entry."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.faq_content.update_one(
        {"faq_id": faq_id},
        {
            "$set": {
                "question": payload.question,
                "answer": payload.answer,
                "category": payload.category,
                "lang": payload.lang,
                "order": payload.order,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="FAQ not found")
    try:
        from routes.global_platform_state import sync_global_faq
        await sync_global_faq(reason="FAQ updated by admin", actor_user_id=user.user_id)
    except Exception as exc:
        logger.warning(f"GPS FAQ sync warning (update): {exc}")
    return {"success": True}


@router.delete("/support/faq/admin/{faq_id}")
async def admin_delete_faq(faq_id: str, request: Request):
    """Admin: Soft-delete a FAQ entry."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    await db.faq_content.update_one(
        {"faq_id": faq_id}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    try:
        from routes.global_platform_state import sync_global_faq
        await sync_global_faq(reason="FAQ deleted by admin", actor_user_id=user.user_id)
    except Exception as exc:
        logger.warning(f"GPS FAQ sync warning (delete): {exc}")
    return {"success": True}


@router.get("/support/faq/admin/list")
async def admin_list_faqs(
    request: Request,
    lang: str = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """Admin: List all FAQ entries (including inactive)."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    query = {} if lang == "all" else {"lang": lang}
    total_count = await db.faq_content.count_documents(query)
    skip = (page - 1) * page_size
    faqs = (
        await db.faq_content.find(query, {"_id": 0})
        .sort("order", 1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )
    return {
        "data": faqs,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "faqs": faqs,
        "total": total_count,
    }


@router.get("/support/faq/admin/language-completeness")
async def admin_faq_language_completeness(request: Request, persist: bool = False):
    """Admin checker for FAQ language coverage across required categories."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    matrix: dict[str, dict[str, int]] = {
        lang: {cat: 0 for cat in FAQ_ADMIN_CATEGORIES}
        for lang in FAQ_ADMIN_LANGS
    }
    uncategorized_by_lang: dict[str, int] = {lang: 0 for lang in FAQ_ADMIN_LANGS}
    active_faq_count = 0

    async for row in iter_find_paginated(
        db.faq_content,
        {"active": {"$ne": False}},
        {"_id": 0, "faq_id": 1, "lang": 1, "category": 1, "question": 1},
        max_docs=5000,
    ):
        active_faq_count += 1
        lang = str(row.get("lang") or "en").strip().lower()[:2]
        cat = str(row.get("category") or "general").strip().lower()
        if lang not in matrix:
            continue
        if cat in matrix[lang]:
            matrix[lang][cat] += 1
        else:
            uncategorized_by_lang[lang] += 1

    language_rows: list[dict] = []
    missing_pairs: list[dict] = []
    for lang in FAQ_ADMIN_LANGS:
        category_counts = matrix[lang]
        covered = sum(1 for cat in FAQ_ADMIN_CATEGORIES if category_counts.get(cat, 0) > 0)
        missing_categories = [cat for cat in FAQ_ADMIN_CATEGORIES if category_counts.get(cat, 0) <= 0]
        completeness_pct = round((covered / max(1, len(FAQ_ADMIN_CATEGORIES))) * 100, 1)
        for cat in missing_categories:
            missing_pairs.append({"lang": lang, "category": cat})
        language_rows.append(
            {
                "lang": lang,
                "total_entries": int(sum(category_counts.values())),
                "category_counts": category_counts,
                "categories_covered": covered,
                "categories_total": len(FAQ_ADMIN_CATEGORIES),
                "missing_categories": missing_categories,
                "missing_count": len(missing_categories),
                "uncategorized_count": int(uncategorized_by_lang.get(lang, 0)),
                "completeness_pct": completeness_pct,
                "is_complete": len(missing_categories) == 0,
            }
        )

    complete_langs = sum(1 for r in language_rows if r.get("is_complete"))
    avg_completeness = round(
        sum(float(r.get("completeness_pct") or 0) for r in language_rows) / max(1, len(language_rows)),
        1,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_languages": list(FAQ_ADMIN_LANGS),
        "required_categories": list(FAQ_ADMIN_CATEGORIES),
        "total_active_faqs": active_faq_count,
        "languages": language_rows,
        "summary": {
            "languages_total": len(FAQ_ADMIN_LANGS),
            "languages_complete": complete_langs,
            "languages_incomplete": len(FAQ_ADMIN_LANGS) - complete_langs,
            "average_completeness_pct": avg_completeness,
            "missing_pairs_total": len(missing_pairs),
        },
        "missing_pairs": missing_pairs,
    }

    if persist:
        await db.faq_language_completeness_snapshots.insert_one({
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
            "languages": payload["languages"],
            "missing_pairs": payload["missing_pairs"],
        })

    return payload


@router.post("/support/faq/admin/seed")
async def admin_seed_faqs(request: Request):
    """Admin: Seed FAQ DB from GPS state (no hardcoded FAQ seed)."""
    from .db import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    existing = await db.faq_content.count_documents({})
    if existing > 0:
        return {"success": True, "message": f"Database already has {existing} FAQs. Skipping seed.", "seeded": 0}

    gps = await _get_live_gps_state()
    gps_faq = (gps or {}).get("faq") or []
    if not gps_faq:
        return {"success": False, "message": "GPS FAQ is empty. Add FAQ entries to GlobalPlatformState first.", "seeded": 0}

    all_faqs: dict[str, list[dict]] = {}
    for item in gps_faq:
        if not item.get("question") or not item.get("answer"):
            continue
        lang = str(item.get("lang") or "en")[:2]
        all_faqs.setdefault(lang, []).append(
            {"q": item.get("question"), "a": item.get("answer"), "category": item.get("category", "general")}
        )
    seeded = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for lang, faqs in all_faqs.items():
        for idx, faq in enumerate(faqs):
            await db.faq_content.insert_one(
                {
                    "faq_id": f"faq_{uuid.uuid4().hex[:12]}",
                    "question": faq["q"],
                    "answer": faq["a"],
                    "category": faq.get("category", "general"),
                    "lang": lang,
                    "order": idx,
                    "active": True,
                    "created_by": "system",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            )
            seeded += 1

    try:
        from routes.global_platform_state import sync_global_faq
        await sync_global_faq(reason="FAQ seeded from GPS", actor_user_id=user.user_id)
    except Exception as exc:
        logger.warning(f"GPS FAQ sync warning (seed): {exc}")

    return {"success": True, "message": f"Seeded {seeded} FAQs across {len(all_faqs)} languages.", "seeded": seeded}


# ── Support Chat ──
class SupportChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/support/chat")
async def support_chat(request: Request, payload: SupportChatRequest):
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id
    conv_id = payload.conversation_id or str(uuid.uuid4().hex[:12])
    try:
        from services.nova_service import build_nova_gps_live_context, ensure_nova_conversation_access, get_nova_response

        if not await ensure_nova_conversation_access(conv_id, user_id):
            raise HTTPException(status_code=403, detail="Conversation access denied")

        result = await get_nova_response(
            message=payload.message,
            conversation_id=conv_id,
            user_id=user_id,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Support chat error: {e}")
        gps_context = await build_nova_gps_live_context()
        return {
            "message": "I'm so sorry — I'm having a little trouble right now. Please try again in a moment, or reach our team at support@realaicoach.app. They'll take great care of you!",
            "conversation_id": conv_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gps_context": gps_context,
        }


# ── Attachment Upload for Chat ──
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "chat_attachments")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/support/chat/attachment")
async def upload_chat_attachment(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: str = Form(""),
    user_id: str = Form(""),
    message: str = Form(""),
):
    """Upload an image/file attachment and get Nova's analysis. Requires authentication."""
    from services.nova_service import build_nova_gps_live_context, ensure_nova_conversation_access, get_nova_response

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Override user_id with authenticated user to prevent spoofing
    user_id = auth_user.user_id
    conv_id = conversation_id or str(uuid.uuid4().hex[:12])
    if not await ensure_nova_conversation_access(conv_id, user_id):
        raise HTTPException(status_code=403, detail="Conversation access denied")
    now = datetime.now(timezone.utc)

    # Validate file
    allowed = {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type {file.content_type} not supported. "
                "Use PNG, JPEG, WebP, GIF, PDF, TXT, or DOCX."
            ),
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")

    try:
        security_scan = enforce_file_security(
            content=content,
            claimed_content_type=str(file.content_type or "application/octet-stream"),
            allowed_content_types=allowed,
            allow_unrecognized_signatures=True,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Attachment failed security scan")

    # Save file
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
    file_id = f"att_{uuid.uuid4().hex[:12]}"
    filename = f"{file_id}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # Store attachment record
    att_doc = {
        "file_id": file_id,
        "conversation_id": conv_id,
        "user_id": user_id,
        "filename": file.filename or filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "path": f"/api/media/chat_attachments/{filename}",
        "security_scan": security_scan,
        "created_at": now.isoformat(),
    }
    await db.chat_attachments.insert_one(att_doc)

    # Build message with attachment context
    user_msg = message.strip() if message.strip() else "I've attached a file. Can you help me with this?"
    attach_note = f"\n[User attached: {file.filename or 'image'} ({file.content_type}, {len(content) // 1024}KB)]"
    if file.content_type == "text/plain":
        try:
            preview = content.decode("utf-8", errors="ignore")[:1500].strip()
            if preview:
                attach_note += f"\n[Attachment text preview]\n{preview}"
        except Exception:
            pass
    full_msg = user_msg + attach_note

    # Get Nova response
    try:
        result = await get_nova_response(message=full_msg, conversation_id=conv_id, user_id=user_id)
        result["attachment"] = {
            "file_id": file_id,
            "url": att_doc["path"],
            "filename": att_doc["filename"],
            "content_type": file.content_type,
        }

        # Log for analytics
        await db.nova_analytics_events.insert_one(
            {
                "event": "attachment_sent",
                "conversation_id": conv_id,
                "user_id": user_id,
                "content_type": file.content_type,
                "size_bytes": len(content),
                "timestamp": now.isoformat(),
            }
        )
        return result
    except Exception as e:
        logger.error(f"Attachment chat error: {e}")
        gps_context = await build_nova_gps_live_context()
        return {
            "message": "I received your file! However, I'm having a bit of trouble analyzing it right now. Could you describe what you need help with?",
            "conversation_id": conv_id,
            "timestamp": now.isoformat(),
            "gps_context": gps_context,
            "attachment": {
                "file_id": file_id,
                "url": att_doc["path"],
                "filename": att_doc["filename"],
                "content_type": file.content_type,
            },
        }


# ── Audio Message Transcription ──
@router.post("/support/chat/audio")
async def transcribe_audio_message(
    request: Request,
    audio: UploadFile = File(...),
    conversation_id: str = Form(""),
    user_id: str = Form(""),
):
    """Transcribe audio using Whisper, then get Nova's response."""
    from services.nova_service import build_nova_gps_live_context, ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id
    conv_id = conversation_id or str(uuid.uuid4().hex[:12])
    if not await ensure_nova_conversation_access(conv_id, user_id):
        raise HTTPException(status_code=403, detail="Conversation access denied")
    now = datetime.now(timezone.utc)

    # Be lenient with content type — browsers often send odd types
    content = await audio.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio too large. Max 25MB.")
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Audio file appears empty.")

    # Transcribe using Whisper
    transcribed_text = ""
    try:
        from emergentintegrations.llm.openai import OpenAISpeechToText

        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)

        # Write to temp file
        ext = "webm"
        if audio.filename and "." in audio.filename:
            ext = audio.filename.rsplit(".", 1)[-1]
        tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
        tmp.write(content)
        tmp.close()

        with open(tmp.name, "rb") as af:
            response = await stt.transcribe(file=af, model="whisper-1", response_format="json")
            transcribed_text = response.text.strip()

        os.unlink(tmp.name)
    except Exception as e:
        logger.error(f"Audio transcription error: {e}")
        gps_context = await build_nova_gps_live_context()
        return {
            "message": "I couldn't quite catch that audio. Could you try typing your question instead?",
            "conversation_id": conv_id,
            "timestamp": now.isoformat(),
            "transcription": "",
            "gps_context": gps_context,
        }

    if not transcribed_text:
        return {
            "message": "I couldn't detect any speech in that recording. Could you try again or type your question?",
            "conversation_id": conv_id,
            "timestamp": now.isoformat(),
            "transcription": "",
            "gps_context": await build_nova_gps_live_context(),
        }

    # Log for analytics
    await db.nova_analytics_events.insert_one(
        {
            "event": "audio_message",
            "conversation_id": conv_id,
            "user_id": user_id,
            "duration_bytes": len(content),
            "transcription_length": len(transcribed_text),
            "timestamp": now.isoformat(),
        }
    )

    # Get Nova response using transcribed text
    try:
        from services.nova_service import get_nova_response

        result = await get_nova_response(message=transcribed_text, conversation_id=conv_id, user_id=user_id)
        result["transcription"] = transcribed_text
        return result
    except Exception as e:
        logger.error(f"Audio chat error: {e}")
        gps_context = await build_nova_gps_live_context()
        return {
            "message": 'I heard you say: "'
            + transcribed_text[:200]
            + "\". I'm having trouble responding right now — please try again!",
            "conversation_id": conv_id,
            "timestamp": now.isoformat(),
            "transcription": transcribed_text,
            "gps_context": gps_context,
        }


# ── Post-Chat Feedback ──
class ChatFeedbackRequest(BaseModel):
    conversation_id: str
    user_id: str = ""
    rating: int  # 1-5 stars
    comment: str = ""
    helpful: bool = True


class NovaMessageFavoriteRequest(BaseModel):
    conversation_id: str
    message_id: str


class NovaConversationPinRequest(BaseModel):
    conversation_id: str


@router.post("/support/chat/feedback")
async def submit_chat_feedback(request: Request, req: ChatFeedbackRequest):
    """Submit post-chat satisfaction feedback."""
    from services.nova_service import ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id
    if not await ensure_nova_conversation_access(req.conversation_id, user_id, allow_new=False):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    now = datetime.now(timezone.utc)
    feedback_id = f"cf_{uuid.uuid4().hex[:12]}"
    doc = {
        "feedback_id": feedback_id,
        "conversation_id": req.conversation_id,
        "user_id": user_id,
        "rating": req.rating,
        "comment": req.comment,
        "helpful": req.helpful,
        "created_at": now.isoformat(),
    }
    await db.nova_chat_feedback.insert_one(doc)

    # Log for analytics
    await db.nova_analytics_events.insert_one(
        {
            "event": "feedback_submitted",
            "conversation_id": req.conversation_id,
            "user_id": user_id,
            "rating": req.rating,
            "timestamp": now.isoformat(),
        }
    )

    return {"success": True, "feedback_id": feedback_id, "message": "Thank you for your feedback!"}


@router.get("/support/chat/history")
async def get_chat_history(request: Request, conversation_id: str = Query(...)):
    """Return chat history for authenticated conversation owner."""
    from services.nova_service import ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    if not await ensure_nova_conversation_access(conversation_id, user_id, allow_new=False):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    history = (
        await db.nova_conversations.find(
            {"conversation_id": conversation_id, "user_id": user_id},
            {"_id": 0, "message_id": 1, "role": 1, "content": 1, "timestamp": 1, "gps_context": 1},
        )
        .sort("timestamp", 1)
        .to_list(200)
    )
    return {"conversation_id": conversation_id, "messages": history}


@router.post("/support/chat/messages/favorite")
async def favorite_chat_message(request: Request, payload: NovaMessageFavoriteRequest):
    """Favorite an assistant message for quick reuse."""
    from services.nova_service import ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    if not await ensure_nova_conversation_access(payload.conversation_id, user_id, allow_new=False):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    message_doc = await db.nova_conversations.find_one(
        {
            "conversation_id": payload.conversation_id,
            "user_id": user_id,
            "role": "assistant",
            "message_id": payload.message_id,
        },
        {"_id": 0, "message_id": 1, "content": 1, "timestamp": 1},
    )
    if not message_doc:
        raise HTTPException(status_code=404, detail="Assistant message not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.nova_message_favorites.update_one(
        {
            "user_id": user_id,
            "conversation_id": payload.conversation_id,
            "message_id": payload.message_id,
        },
        {
            "$set": {
                "content": message_doc.get("content", ""),
                "message_timestamp": message_doc.get("timestamp"),
                "updated_at": now,
            },
            "$setOnInsert": {
                "favorite_id": f"nf_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "conversation_id": payload.conversation_id,
                "message_id": payload.message_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    favorite = await db.nova_message_favorites.find_one(
        {
            "user_id": user_id,
            "conversation_id": payload.conversation_id,
            "message_id": payload.message_id,
        },
        {"_id": 0},
    )
    return {"success": True, "favorite": favorite}


@router.delete("/support/chat/messages/favorite")
async def unfavorite_chat_message(request: Request, payload: NovaMessageFavoriteRequest):
    """Remove an assistant message from favorites."""
    from services.nova_service import ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    if not await ensure_nova_conversation_access(payload.conversation_id, user_id, allow_new=False):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    await db.nova_message_favorites.delete_one(
        {
            "user_id": user_id,
            "conversation_id": payload.conversation_id,
            "message_id": payload.message_id,
        }
    )
    return {"success": True}


@router.get("/support/chat/messages/favorites")
async def list_favorite_chat_messages(request: Request, conversation_id: str = Query(""), limit: int = Query(20, ge=1, le=100)):
    """List user's favorite assistant messages."""
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    query: Dict[str, Any] = {"user_id": user_id}
    if conversation_id:
        query["conversation_id"] = conversation_id

    favorites = (
        await db.nova_message_favorites.find(query, {"_id": 0})
        .sort("updated_at", -1)
        .to_list(limit)
    )
    return {"favorites": favorites}


@router.post("/support/chat/conversations/pin")
async def pin_chat_conversation(request: Request, payload: NovaConversationPinRequest):
    """Pin a conversation for quick access."""
    from services.nova_service import ensure_nova_conversation_access

    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    if not await ensure_nova_conversation_access(payload.conversation_id, user_id, allow_new=False):
        raise HTTPException(status_code=403, detail="Conversation access denied")

    now = datetime.now(timezone.utc).isoformat()
    await db.nova_conversation_pins.update_one(
        {
            "user_id": user_id,
            "conversation_id": payload.conversation_id,
        },
        {
            "$set": {"updated_at": now},
            "$setOnInsert": {
                "pin_id": f"np_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "conversation_id": payload.conversation_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return {"success": True}


@router.delete("/support/chat/conversations/pin")
async def unpin_chat_conversation(request: Request, payload: NovaConversationPinRequest):
    """Unpin a conversation."""
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    await db.nova_conversation_pins.delete_one(
        {
            "user_id": user_id,
            "conversation_id": payload.conversation_id,
        }
    )
    return {"success": True}


@router.get("/support/chat/conversations/pins")
async def list_pinned_chat_conversations(request: Request, limit: int = Query(12, ge=1, le=100)):
    """List pinned conversations with latest-message preview."""
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_user.user_id

    pins = (
        await db.nova_conversation_pins.find({"user_id": user_id}, {"_id": 0})
        .sort("updated_at", -1)
        .to_list(limit)
    )

    enriched: List[Dict[str, Any]] = []
    for pin in pins:
        cid = str(pin.get("conversation_id") or "")
        latest = await db.nova_conversations.find_one(
            {"conversation_id": cid, "user_id": user_id},
            {"_id": 0, "content": 1, "role": 1, "timestamp": 1},
            sort=[("timestamp", -1)],
        )
        enriched.append(
            {
                **pin,
                "preview": str((latest or {}).get("content") or "")[:140],
                "latest_role": (latest or {}).get("role"),
                "latest_timestamp": (latest or {}).get("timestamp"),
            }
        )

    return {"pins": enriched}


# ── Nova Analytics Dashboard (Admin) ──
@router.get("/support/nova/analytics")
async def nova_analytics_dashboard(request: Request):
    """Admin: Nova AI Assistant analytics — conversations, satisfaction, topics, performance."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    (now - timedelta(days=30)).isoformat()
    (now - timedelta(days=7)).isoformat()

    topic_keywords = {
        "Subscription & Billing": [
            "subscription",
            "billing",
            "payment",
            "upgrade",
            "cancel",
            "plan",
            "price",
            "premium",
            "free",
        ],
        "AI Features": ["feature", "copilot", "tool", "ai writer", "chatbot", "search", "automation"],
        "Referral Program": ["referral", "refer", "commission", "share", "invite", "friend", "code"],
        "Account & Security": ["account", "password", "security", "login", "2fa", "delete", "profile", "settings"],
        "Technical Issues": ["error", "bug", "broken", "not working", "issue", "problem", "crash", "slow"],
        "Getting Started": ["how to", "start", "begin", "new", "tutorial", "guide", "help"],
        "Health & Wellness": ["health", "fitness", "medimate", "workout", "sleep", "diet"],
        "Finance": ["budget", "finance", "money", "pennypilot", "savings", "salary"],
    }

    # Unique conversations
    conv_ids = set()
    conv_by_day = {}
    user_convos = {}
    total_messages = 0
    user_messages = 0
    nova_messages = 0
    topic_counts: Dict[str, int] = {}
    five_min_ago = (now - timedelta(minutes=5)).isoformat()
    active_session_ids: set[str] = set()

    async for m in iter_find_paginated(
        db.nova_conversations,
        {},
        {"_id": 0, "conversation_id": 1, "role": 1, "timestamp": 1, "user_id": 1, "content": 1},
        sort=[("timestamp", -1)],
    ):
        total_messages += 1
        cid = str(m.get("conversation_id") or "")
        if cid:
            conv_ids.add(cid)
        ts = str(m.get("timestamp") or "")
        role = str(m.get("role") or "")
        if role == "user":
            user_messages += 1
            msg_text = str(m.get("content") or "").lower()
            for topic, kws in topic_keywords.items():
                if any(kw in msg_text for kw in kws):
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1
        else:
            nova_messages += 1
        uid = str(m.get("user_id") or "anonymous")
        user_convos.setdefault(uid, set()).add(cid)
        if ts and len(ts) >= 10:
            day = ts[:10]
            conv_by_day.setdefault(day, set()).add(cid)
        if cid and ts >= five_min_ago:
            active_session_ids.add(cid)

    total_conversations = len(conv_ids)
    unique_users = len(user_convos)

    # Daily conversation trend (last 30 days)
    daily_trend = []
    for i in range(30):
        d = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        daily_trend.append({"date": d, "conversations": len(conv_by_day.get(d, set()))})

    # Feedback/Satisfaction
    total_feedback = 0
    rating_sum = 0.0
    rating_count = 0
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    helpful_count = 0
    recent_feedback = []
    async for feedback_row in iter_find_paginated(
        db.nova_chat_feedback,
        {},
        {"_id": 0},
        sort=[("created_at", -1)],
        max_docs=5000,
    ):
        total_feedback += 1
        rating_value = feedback_row.get("rating")
        if isinstance(rating_value, (int, float)):
            normalized_rating = int(rating_value)
            rating_sum += float(rating_value)
            rating_count += 1
            rating_dist[normalized_rating] = rating_dist.get(normalized_rating, 0) + 1
        if feedback_row.get("helpful", False):
            helpful_count += 1
        if len(recent_feedback) < 20:
            recent_feedback.append(feedback_row)

    avg_rating = round(rating_sum / max(rating_count, 1), 1)
    satisfaction_rate = round(helpful_count / max(total_feedback, 1) * 100, 1)

    # Analytics events
    attachment_count = 0
    audio_count = 0
    async for event_row in iter_find_paginated(
        db.nova_analytics_events,
        {},
        {"_id": 0, "event": 1},
        max_docs=10000,
    ):
        event_name = event_row.get("event")
        if event_name == "attachment_sent":
            attachment_count += 1
        if event_name == "audio_message":
            audio_count += 1

    # Topic analysis (simple keyword frequency from user messages)
    topic_sorted = sorted(topic_counts.items(), key=lambda x: -x[1])

    # Avg messages per conversation
    avg_msgs_per_conv = round(total_messages / max(total_conversations, 1), 1)

    # Active sessions (conversations in last 5 min)
    active_sessions = len(active_session_ids)

    return {
        "overview": {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "nova_messages": nova_messages,
            "unique_users": unique_users,
            "active_sessions": active_sessions,
            "avg_rating": avg_rating,
            "satisfaction_rate": satisfaction_rate,
            "total_feedback": total_feedback,
            "avg_msgs_per_conv": avg_msgs_per_conv,
            "attachments_sent": attachment_count,
            "audio_messages": audio_count,
        },
        "daily_trend": daily_trend,
        "rating_distribution": rating_dist,
        "top_topics": [{"topic": t, "count": c} for t, c in topic_sorted[:10]],
        "recent_feedback": recent_feedback,
        "generated_at": now.isoformat(),
    }


@router.get("/support/nova/uptime")
async def nova_uptime_telemetry(request: Request, hours: int = 24):
    """Admin: lightweight Nova reliability telemetry for proactive monitoring."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    bounded_hours = max(1, min(int(hours or 24), 168))
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=bounded_hours)).isoformat()
    since_dt = now - timedelta(hours=bounded_hours)

    user_msgs = await db.nova_conversations.count_documents(
        {
            "role": "user",
            "timestamp": {"$gte": since_iso},
        }
    )
    assistant_msgs = await db.nova_conversations.count_documents(
        {
            "role": "assistant",
            "timestamp": {"$gte": since_iso},
        }
    )

    nova_errors = await db.client_errors.count_documents(
        {
            "created_at": {"$gte": since_dt},
            "$or": [
                {"panel_id": {"$regex": "nova", "$options": "i"}},
                {"panel_name": {"$regex": "nova", "$options": "i"}},
            ],
        }
    )

    success_ratio = round(min(100.0, (assistant_msgs / max(user_msgs, 1)) * 100), 1)
    error_ratio = round((nova_errors / max(user_msgs, 1)) * 100, 2)
    uptime_ratio = round(max(0.0, 100.0 - error_ratio), 2)

    return {
        "window_hours": bounded_hours,
        "user_messages": user_msgs,
        "assistant_messages": assistant_msgs,
        "error_events": nova_errors,
        "success_ratio": success_ratio,
        "error_ratio": error_ratio,
        "uptime_ratio": uptime_ratio,
        "generated_at": now.isoformat(),
    }


@router.get("/support/nova/health")
async def nova_health_status(hours: int = 1):
    """Lightweight Nova health signal for chat input micro-indicators."""
    from services.nova_service import build_nova_gps_live_context

    bounded_hours = max(1, min(int(hours or 1), 24))
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=bounded_hours)).isoformat()
    since_dt = now - timedelta(hours=bounded_hours)
    gps_context = await build_nova_gps_live_context()

    user_msgs = await db.nova_conversations.count_documents(
        {
            "role": "user",
            "timestamp": {"$gte": since_iso},
        }
    )
    assistant_msgs = await db.nova_conversations.count_documents(
        {
            "role": "assistant",
            "timestamp": {"$gte": since_iso},
        }
    )
    nova_errors = await db.client_errors.count_documents(
        {
            "created_at": {"$gte": since_dt},
            "$or": [
                {"panel_id": {"$regex": "nova", "$options": "i"}},
                {"panel_name": {"$regex": "nova", "$options": "i"}},
            ],
        }
    )

    success_ratio = round(min(100.0, (assistant_msgs / max(user_msgs, 1)) * 100), 1)
    error_ratio = round((nova_errors / max(user_msgs, 1)) * 100, 2)
    has_key = bool(EMERGENT_LLM_KEY)
    gps_live = bool(gps_context.get("gps_live"))
    if user_msgs == 0 and nova_errors == 0:
        healthy = has_key and gps_live
    else:
        healthy = has_key and gps_live and success_ratio >= 85 and error_ratio < 30

    return {
        "status": "healthy" if healthy else "degraded",
        "signal_scope": "global-service-readiness",
        "window_hours": bounded_hours,
        "success_ratio": success_ratio,
        "error_ratio": error_ratio,
        "user_messages": user_msgs,
        "assistant_messages": assistant_msgs,
        "error_events": nova_errors,
        "gps_live": gps_live,
        "gps_source": gps_context.get("gps_source"),
        "gps_failed_checks": gps_context.get("gps_failed_checks") or [],
        "generated_at": now.isoformat(),
    }


# ── Nova Conversation Export (CSV) ──
@router.get("/support/nova/export/csv")
async def export_nova_conversations_csv(request: Request, days: int = 30):
    """Admin: Export all Nova conversations as CSV."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get feedback map
    fb_map = {}
    async for f in iter_find_paginated(
        db.nova_chat_feedback,
        {},
        {"_id": 0},
        max_docs=10000,
    ):
        fb_map[f.get("conversation_id", "")] = {"rating": f.get("rating", ""), "comment": f.get("comment", "")}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Timestamp", "Conversation ID", "User ID", "Role", "Message", "Feedback Rating", "Feedback Comment"]
    )
    async for m in iter_find_paginated(
        db.nova_conversations,
        {"timestamp": {"$gte": cutoff}},
        {"_id": 0},
        sort=[("timestamp", 1)],
        max_docs=100000,
    ):
        cid = m.get("conversation_id", "")
        fb = fb_map.get(cid, {})
        writer.writerow(
            [
                m.get("timestamp", ""),
                cid,
                m.get("user_id", ""),
                m.get("role", ""),
                m.get("content", "")[:2000],
                fb.get("rating", ""),
                fb.get("comment", ""),
            ]
        )
    output.seek(0)
    fname = f"nova_conversations_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ── Nova Single Conversation PDF Export ──
@router.get("/support/nova/export/pdf/{conversation_id}")
async def export_nova_conversation_pdf(conversation_id: str, request: Request):
    """Admin: Export a single conversation as PDF."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    msgs = (
        await db.nova_conversations.find({"conversation_id": conversation_id}, {"_id": 0})
        .sort("timestamp", 1)
        .to_list(1000)
    )

    if not msgs:
        raise HTTPException(status_code=404, detail="Conversation not found")

    fb = await db.nova_chat_feedback.find_one({"conversation_id": conversation_id}, {"_id": 0})

    from fpdf import FPDF
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pw = pdf.w - pdf.l_margin - pdf.r_margin  # printable width

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(pw, 10, "Nova AI - Conversation Transcript", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(pw, 5, f"Conversation: {conversation_id}", ln=True)
    uid = msgs[0].get("user_id", "anonymous") if msgs else "unknown"
    pdf.cell(pw, 5, f"User: {uid}  |  Messages: {len(msgs)}", ln=True)
    ts_start = msgs[0].get("timestamp", "")[:19] if msgs else ""
    ts_end = msgs[-1].get("timestamp", "")[:19] if msgs else ""
    pdf.cell(pw, 5, f"Period: {ts_start} to {ts_end}", ln=True)
    pdf.cell(pw, 5, f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.ln(4)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + pw, pdf.get_y())
    pdf.ln(4)

    # Messages
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        ts = m.get("timestamp", "")[:19]

        if role == "user":
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(37, 99, 235)
            pdf.cell(pw, 5, f"User  [{ts}]", ln=True)
        else:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(16, 185, 129)
            pdf.cell(pw, 5, f"Nova  [{ts}]", ln=True)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 41, 59)
        safe = content.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(pw, 4, safe)
        pdf.ln(2)

    # Feedback section
    if fb:
        pdf.ln(3)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + pw, pdf.get_y())
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(245, 158, 11)
        rating_val = fb.get("rating", 0)
        pdf.cell(pw, 7, f"User Feedback: {rating_val}/5 stars", ln=True)
        if fb.get("comment"):
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(100, 116, 139)
            safe_comment = fb["comment"].encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(pw, 4, safe_comment)

    raw_pdf = pdf.output(dest="S")
    pdf_bytes = bytes(raw_pdf) if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin1", errors="ignore")
    composed_pdf = compose_pdf_v15_helper_layout(
        pdf_bytes,
        title="Nova Conversation Transcript",
        subtitle="Support operations export",
        right_primary=f"Messages: {len(msgs)}",
        right_secondary=f"Conversation: {conversation_id[:18]}",
        badge_text="SUPPORT CHAT AUDIT",
        badge_status="INFO",
        footer_text="RealAICoach Support • Enterprise profile",
        summary_title="Conversation Context",
        summary_rows=[
            ("User", uid),
            ("Feedback", f"{fb.get('rating', 0)}/5" if fb else "Not rated"),
            ("Window", f"{ts_start} to {ts_end}"),
        ],
        callout_title="Transcript Integrity",
        callout_subtitle="Moderator-ready export",
        callout_detail="Transcript rows are rendered chronologically and include role/time labels for support governance.",
        callout_status="INFO",
    )
    buf = io.BytesIO(_enforce_pdf_v15_enterprise(composed_pdf, "nova_conversation_export"))
    fname = build_pdf_v15_filename("nova-transcript", conversation_id)
    return StreamingResponse(
        buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


# ── Nova Conversations List (for export UI) ──
@router.get("/support/nova/conversations")
async def list_nova_conversations(request: Request, limit: int = 50):
    """Admin: List unique conversations with summary info."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fb_map = {}
    async for feedback_row in iter_find_paginated(
        db.nova_chat_feedback,
        {},
        {"_id": 0},
        max_docs=5000,
    ):
        fb_map[feedback_row.get("conversation_id")] = feedback_row

    conv_map: Dict[str, Dict] = {}
    async for m in iter_find_paginated(db.nova_conversations, {}, {"_id": 0}, sort=[("timestamp", -1)]):
        cid = m.get("conversation_id", "")
        if cid not in conv_map:
            conv_map[cid] = {
                "conversation_id": cid,
                "user_id": m.get("user_id", "anonymous"),
                "message_count": 0,
                "first_message": "",
                "last_timestamp": "",
                "first_timestamp": m.get("timestamp", ""),
            }
        c = conv_map[cid]
        c["message_count"] += 1
        c["last_timestamp"] = m.get("timestamp", c["last_timestamp"])
        if m.get("role") == "user" and not c["first_message"]:
            c["first_message"] = m.get("content", "")[:120]

    # Sort by most recent
    convos = sorted(conv_map.values(), key=lambda x: x.get("last_timestamp", ""), reverse=True)[:limit]

    # Attach feedback
    for c in convos:
        fb = fb_map.get(c["conversation_id"])
        c["rating"] = fb.get("rating") if fb else None
        c["feedback_comment"] = fb.get("comment", "") if fb else ""

    return {"conversations": convos, "total": len(conv_map)}


# ── Auto-Generate FAQs from Conversations ──
@router.post("/support/nova/auto-faq")
async def auto_generate_faqs(request: Request):
    """Admin: Analyze conversation data and auto-generate FAQ entries using GPT-5.2."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get recent user messages
    recent_msgs = (
        await db.nova_conversations.find({"role": "user"}, {"_id": 0, "content": 1}).sort("timestamp", -1).to_list(500)
    )

    if len(recent_msgs) < 5:
        return {
            "success": False,
            "message": "Not enough conversation data yet. Need at least 5 user messages.",
            "generated": 0,
        }

    questions_text = "\n".join([f"- {m['content'][:200]}" for m in recent_msgs[:100]])

    # Get existing FAQs to avoid duplicates
    existing_faqs = await db.faqs.find({"lang": "en"}, {"_id": 0, "q": 1}).to_list(200)
    existing_qs = [f["q"] for f in existing_faqs]
    existing_text = "\n".join([f"- {q}" for q in existing_qs[:50]]) if existing_qs else "None yet."

    prompt = f"""Analyze these recent user support questions and generate 3-5 NEW FAQ entries that would help future users.

## Recent User Questions:
{questions_text}

## Existing FAQs (DO NOT duplicate these):
{existing_text}

## Instructions:
- Generate FAQ entries that address the MOST COMMON themes from the questions above
- Each FAQ should have a clear, searchable question and a helpful, complete answer
- Categorize each: general, features, billing, or security
- Format as JSON array: [{{"q": "question", "a": "answer", "category": "category"}}]
- Only output the JSON array, no other text
- Answers should be 2-4 sentences, professional and helpful"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"auto-faq-{uuid.uuid4().hex[:8]}",
            system_message="You are a FAQ generator. Analyze user questions and create clear, helpful FAQ entries. Output only valid JSON.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        import json

        # Response is a string directly
        text = response.strip() if isinstance(response, str) else str(response)
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        new_faqs = json.loads(text.strip())

        if not isinstance(new_faqs, list):
            return {"success": False, "message": "AI returned invalid format", "generated": 0}

        inserted = 0
        for faq in new_faqs[:5]:
            q = faq.get("q", "").strip()
            a = faq.get("a", "").strip()
            cat = faq.get("category", "general")
            if not q or not a:
                continue
            # Check for near-duplicates
            is_dup = any(eq.lower().strip() == q.lower().strip() for eq in existing_qs)
            if is_dup:
                continue
            await db.faqs.insert_one(
                {
                    "q": q,
                    "a": a,
                    "category": cat,
                    "lang": "en",
                    "auto_generated": True,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "helpful_count": 0,
                    "not_helpful_count": 0,
                }
            )
            inserted += 1
            existing_qs.append(q)

        return {
            "success": True,
            "generated": inserted,
            "message": f"Generated {inserted} new FAQ entries from conversation analysis.",
        }
    except Exception as e:
        logger.error(f"Auto-FAQ generation error: {e}")
        return {"success": False, "message": f"Failed to generate FAQs: {str(e)}", "generated": 0}


# ── Support Email ──


def _parse_iso_dt_support(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _normalize_support_category(value: Any) -> str:
    normalized = str(value or "general").strip().lower().replace(" ", "_")
    if normalized in SUPPORT_EMAIL_ALLOWED_CATEGORIES:
        return normalized
    if normalized in {"feature", "feature-request", "featurerequest"}:
        return "feature_request"
    return "general"


def _normalize_support_priority(value: Any) -> str:
    normalized = str(value or "medium").strip().lower()
    if normalized in SUPPORT_EMAIL_ALLOWED_PRIORITIES:
        return normalized
    return "medium"


def _support_token_set(value: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]{3,}", (value or "").lower())}


def _support_similarity(a: str, b: str) -> float:
    ta = _support_token_set(a)
    tb = _support_token_set(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta.intersection(tb))
    union = len(ta.union(tb))
    return round(inter / max(union, 1), 3)


def _recommend_support_category(subject: str, message: str, fallback: str = "general") -> str:
    text = f"{subject} {message}".lower()
    if any(k in text for k in ["payment", "billing", "invoice", "charge", "refund", "card", "subscription"]):
        return "billing"
    if any(k in text for k in ["login", "password", "account", "2fa", "locked", "signin"]):
        return "account"
    if any(k in text for k in ["bug", "error", "crash", "failed", "issue", "stack", "exception"]):
        return "technical"
    if any(k in text for k in ["feature", "enhancement", "request", "improve"]):
        return "feature_request"
    return _normalize_support_category(fallback)


def _recommend_support_priority(subject: str, message: str, fallback: str = "medium") -> str:
    text = f"{subject} {message}".lower()
    if any(k in text for k in ["production down", "outage", "security breach", "critical", "data loss", "blocked"]):
        return "critical"
    if any(k in text for k in ["urgent", "cannot", "can't", "failed payment", "locked out", "error"]):
        return "high"
    if any(k in text for k in ["question", "clarify", "how to", "suggestion"]):
        return "low"
    return _normalize_support_priority(fallback)


async def _collect_recent_support_tickets(email_hash: str, limit: int = 6) -> List[Dict[str, Any]]:
    if not email_hash:
        return []
    docs = (
        await db.support_tickets.find(
            {"email_hash": email_hash},
            {
                "_id": 0,
                "ticket_id": 1,
                "subject": 1,
                "message": 1,
                "status": 1,
                "created_at": 1,
                "responded_at": 1,
                "priority": 1,
                "category": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    for doc in docs:
        decrypt_doc(doc, _TICKET_ENC_FIELDS)
    return docs


async def _build_support_email_insights(email_hash: str) -> Dict[str, Any]:
    recent = await _collect_recent_support_tickets(email_hash=email_hash, limit=20)
    if not recent:
        return {
            "total_tickets": 0,
            "open_tickets": 0,
            "avg_response_hours": None,
            "last_ticket": None,
        }

    open_count = sum(1 for t in recent if str(t.get("status") or "open").lower() in {"open", "pending", "new"})
    response_hours: List[float] = []
    for row in recent:
        created_at = _parse_iso_dt_support(row.get("created_at"))
        responded_at = _parse_iso_dt_support(row.get("responded_at"))
        if created_at and responded_at and responded_at >= created_at:
            response_hours.append((responded_at - created_at).total_seconds() / 3600)

    latest = recent[0]
    return {
        "total_tickets": len(recent),
        "open_tickets": int(open_count),
        "avg_response_hours": round(sum(response_hours) / len(response_hours), 1) if response_hours else None,
        "last_ticket": {
            "ticket_id": latest.get("ticket_id"),
            "status": latest.get("status") or "open",
            "created_at": latest.get("created_at"),
        },
    }


async def _support_faq_hints(query: str, lang: str = "en", limit: int = 3) -> List[Dict[str, Any]]:
    payload = await get_faq(lang=lang)
    rows = payload.get("faqs") or []
    tokens = _support_token_set(query)
    scored: List[Dict[str, Any]] = []
    for row in rows:
        combined = f"{row.get('q', '')} {row.get('a', '')}".lower()
        score = sum(1 for token in tokens if token in combined)
        if score > 0:
            scored.append({"score": score, **row})
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return [
        {"question": item.get("q", ""), "answer": item.get("a", ""), "category": item.get("category", "general")}
        for item in scored[:limit]
    ]


def _safe_json_obj(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
    return None


async def _send_support_confirmation_email(name: str, email: str, ticket_id: str, subject: str, message: str) -> bool:
    email_sent = False
    if is_email_configured():
        try:
            result = await send_catalog_template(
                recipient_email=email,
                template_key="ticket_created",
                recipient_name=name,
                user_name=name,
                ticket_id=ticket_id,
                subject=subject,
                message=message,
            )
            email_sent = result.get("success", False)
            if email_sent:
                logger.info(f"Support confirmation email sent to {email}")
            else:
                logger.error(f"Support email failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Failed to send support email: {e}")
    return email_sent


async def _create_support_ticket(
    *,
    name: str,
    email: str,
    subject: str,
    message: str,
    category: str,
    priority: str,
    ai_suggested: bool,
    ai_confidence: Optional[float],
    suggestion_intent: Optional[str],
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    ticket_id = f"TKT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4().hex[:8]).upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.support_tickets.insert_one(
        {
            "ticket_id": ticket_id,
            "name": encrypt_field(name),
            "email": encrypt_field(email),
            "email_hash": hash_lookup(email),
            "subject": subject,
            "message": encrypt_field(message),
            "status": "open",
            "category": _normalize_support_category(category),
            "priority": _normalize_support_priority(priority),
            "ai_suggested": bool(ai_suggested),
            "ai_confidence": float(ai_confidence) if ai_confidence is not None else None,
            "suggestion_intent": str(suggestion_intent or "draft").strip().lower(),
            "attachments": attachments or [],
            "admin_notes": [],
            "reply_logs": [],
            "resolved_at": None,
            "responded_at": None,
            "created_at": now_iso,
        }
    )
    return ticket_id


class SupportTicketAttachmentMeta(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size_bytes: int = 0


class SupportEmailRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str = "Support Request"
    message: str
    category: Optional[str] = "general"
    priority: Optional[str] = "medium"
    ai_suggested: bool = False
    ai_confidence: Optional[float] = None
    suggestion_intent: Optional[str] = "draft"
    attachments: List[SupportTicketAttachmentMeta] = Field(default_factory=list)


class SupportEmailAssistRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    subject: Optional[str] = ""
    message: str
    category: Optional[str] = "general"
    priority: Optional[str] = "medium"
    intent: Optional[str] = "draft"
    lang: Optional[str] = "en"


@router.get("/support/email/insights")
async def get_support_email_insights(request: Request, email: Optional[EmailStr] = None):
    auth_user = await get_current_user(request)
    resolved_email = str(email or "").strip().lower()
    if auth_user:
        user_email = str(auth_user.email or "").strip().lower()
        if not resolved_email:
            resolved_email = user_email
        elif resolved_email != user_email and not bool(getattr(auth_user, "is_admin", False)):
            resolved_email = user_email
    else:
        # Public callers should not be able to introspect historical support data
        # for arbitrary email addresses.
        resolved_email = ""

    if not resolved_email:
        return {
            "success": True,
            "insights": {
                "total_tickets": 0,
                "open_tickets": 0,
                "avg_response_hours": None,
                "last_ticket": None,
            },
        }

    insights = await _build_support_email_insights(hash_lookup(resolved_email))
    return {"success": True, "insights": insights}


@router.get("/support/latest-context")
async def get_support_latest_context(request: Request):
    """Return latest resolved support-ticket context for authenticated user prefill."""
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_email = str(getattr(auth_user, "email", "") or "").strip().lower()
    if not user_email:
        return {"success": True, "context": None}

    email_hash = hash_lookup(user_email)
    latest = await db.support_tickets.find_one(
        {
            "email_hash": email_hash,
            "status": {"$in": ["resolved", "closed"]},
        },
        {
            "_id": 0,
            "ticket_id": 1,
            "subject": 1,
            "message": 1,
            "category": 1,
            "priority": 1,
            "created_at": 1,
            "resolved_at": 1,
            "responded_at": 1,
        },
        sort=[("resolved_at", -1), ("created_at", -1)],
    )

    if not latest:
        return {"success": True, "context": None}

    decrypt_doc(latest, _TICKET_ENC_FIELDS)
    context = {
        "ticket_id": latest.get("ticket_id"),
        "subject": str(latest.get("subject") or "").strip()[:180],
        "message": str(latest.get("message") or "").strip()[:4000],
        "category": _normalize_support_category(latest.get("category") or "general"),
        "priority": _normalize_support_priority(latest.get("priority") or "medium"),
        "created_at": latest.get("created_at"),
        "resolved_at": latest.get("resolved_at") or latest.get("responded_at"),
    }
    return {"success": True, "context": context}


@router.get("/support/attachment/{attachment_id}")
async def download_support_attachment(
    attachment_id: str,
    request: Request,
    download: bool = Query(default=False),
):
    """Serve support email attachments for admins and the owning authenticated user."""
    auth_user = await get_current_user(request)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    attachment = await db.support_ticket_attachments.find_one(
        {"attachment_id": attachment_id},
        {
            "_id": 0,
            "attachment_id": 1,
            "ticket_id": 1,
            "filename": 1,
            "content_type": 1,
            "content_base64": 1,
        },
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    ticket_id = str(attachment.get("ticket_id") or "").strip()
    if not bool(getattr(auth_user, "is_admin", False)):
        user_email = str(getattr(auth_user, "email", "") or "").strip().lower()
        if not user_email:
            raise HTTPException(status_code=403, detail="Access denied")

        owner_ticket = await db.support_tickets.find_one(
            {
                "ticket_id": ticket_id,
                "email_hash": hash_lookup(user_email),
            },
            {"_id": 0, "ticket_id": 1},
        )
        if not owner_ticket:
            raise HTTPException(status_code=403, detail="Access denied")

    try:
        payload = base64.b64decode(str(attachment.get("content_base64") or ""), validate=True)
    except Exception:
        raise HTTPException(status_code=500, detail="Attachment payload is invalid")

    filename = str(attachment.get("filename") or "attachment.bin").replace('"', "")[:180]
    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=str(attachment.get("content_type") or "application/octet-stream"),
        headers=headers,
    )


@router.post("/support/email/assist")
async def suggest_support_email(payload: SupportEmailAssistRequest, request: Request):
    message = str(payload.message or "").strip()
    if len(message) < 8:
        raise HTTPException(status_code=400, detail="Please provide more details for AI suggestion")

    auth_user = await get_current_user(request)
    resolved_email = ""
    if auth_user:
        user_email = str(auth_user.email or "").strip().lower()
        requested_email = str(payload.email or "").strip().lower()
        if not requested_email:
            resolved_email = user_email
        elif requested_email != user_email and not bool(getattr(auth_user, "is_admin", False)):
            resolved_email = user_email
        else:
            resolved_email = requested_email

    email_hash = hash_lookup(resolved_email) if resolved_email else ""
    recent_tickets = await _collect_recent_support_tickets(email_hash=email_hash, limit=8)
    insights = await _build_support_email_insights(email_hash=email_hash) if email_hash else {
        "total_tickets": 0,
        "open_tickets": 0,
        "avg_response_hours": None,
        "last_ticket": None,
    }
    query_seed = f"{payload.subject or ''} {message}".strip()
    faq_hints = await _support_faq_hints(query=query_seed, lang=str(payload.lang or "en")[:2], limit=3)

    suggested_category = _recommend_support_category(payload.subject or "", message, payload.category or "general")
    suggested_priority = _recommend_support_priority(payload.subject or "", message, payload.priority or "medium")
    suggested_subject = str(payload.subject or "").strip() or f"{suggested_category.replace('_', ' ').title()} support request"
    suggested_message = message
    confidence = 0.58
    source = "deterministic"
    intent = str(payload.intent or "draft").strip().lower()

    if EMERGENT_LLM_KEY:
        try:
            def _safe_str(val: Any) -> Any:
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val.isoformat()
                return val

            safe_insights = {
                "total_tickets": insights.get("total_tickets", 0),
                "open_tickets": insights.get("open_tickets", 0),
                "avg_response_hours": insights.get("avg_response_hours"),
                "last_ticket": {
                    "ticket_id": _safe_str(insights.get("last_ticket", {}).get("ticket_id")) if insights.get("last_ticket") else None,
                    "status": _safe_str(insights.get("last_ticket", {}).get("status")) if insights.get("last_ticket") else None,
                    "created_at": _safe_str(insights.get("last_ticket", {}).get("created_at")) if insights.get("last_ticket") else None,
                } if insights.get("last_ticket") else None,
            }
            model_context = {
                "intent": intent,
                "input": {
                    "name": str(payload.name or ""),
                    "subject": str(payload.subject or ""),
                    "message": message,
                    "category": suggested_category,
                    "priority": suggested_priority,
                },
                "insights": safe_insights,
                "faq_hints": [{"question": f.get("question"), "answer": f.get("answer"), "category": f.get("category")} for f in faq_hints],
                "recent_tickets": [
                    {
                        "ticket_id": row.get("ticket_id"),
                        "subject": row.get("subject"),
                        "status": row.get("status"),
                        "priority": row.get("priority"),
                        "category": row.get("category"),
                        "created_at": _safe_str(row.get("created_at")),
                    }
                    for row in recent_tickets[:5]
                ],
            }
            system_prompt = (
                "You are Nova enterprise support drafting assistant.\n"
                "Only use facts from INPUT and PLATFORM_CONTEXT. Never invent product behavior, timelines, or outcomes.\n"
                "Return strict JSON: {subject, message, category, priority, confidence, next_actions}."
            )
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"support-draft-{uuid.uuid4().hex[:10]}",
                system_message=system_prompt,
            ).with_model("openai", "gpt-4o")
            llm_response = await chat.send_message(
                UserMessage(
                    text=(
                        "Generate a user-side support ticket draft aligned to intent."
                        f"\nINTENT: {intent}"
                        f"\nPLATFORM_CONTEXT:\n{json.dumps(model_context, ensure_ascii=False)}"
                    )
                )
            )
            parsed = _safe_json_obj(llm_response or "")
            if parsed:
                suggested_subject = str(parsed.get("subject") or suggested_subject).strip()[:180]
                suggested_message = str(parsed.get("message") or suggested_message).strip()[:4000]
                suggested_category = _normalize_support_category(parsed.get("category") or suggested_category)
                suggested_priority = _normalize_support_priority(parsed.get("priority") or suggested_priority)
                try:
                    confidence = max(0.0, min(float(parsed.get("confidence") or confidence), 1.0))
                except Exception:
                    confidence = 0.64
                source = "openai:gpt-4o"
        except Exception as llm_exc:
            logger.warning(f"Support email AI assist fallback used: {llm_exc}")

    duplicate_hints: List[Dict[str, Any]] = []
    for row in recent_tickets[:6]:
        score = _support_similarity(query_seed, f"{row.get('subject', '')} {row.get('message', '')}")
        if score >= 0.28:
            duplicate_hints.append(
                {
                    "ticket_id": row.get("ticket_id"),
                    "subject": row.get("subject", ""),
                    "status": row.get("status", "open"),
                    "created_at": row.get("created_at"),
                    "similarity": score,
                }
            )

    return {
        "success": True,
        "suggestion": {
            "subject": suggested_subject,
            "message": suggested_message,
            "category": suggested_category,
            "priority": suggested_priority,
            "confidence": round(confidence, 2),
            "source": source,
            "intent": intent,
        },
        "duplicate_hints": duplicate_hints[:3],
        "faq_hints": faq_hints,
        "insights": insights,
    }


@router.post("/support/email")
async def submit_support_email(request: SupportEmailRequest):
    subject = str(request.subject or "Support Request").strip()[:180] or "Support Request"
    message = str(request.message or "").strip()[:4000]
    if len(message) < 8:
        raise HTTPException(status_code=400, detail="Message is too short")

    attachments_meta = [
        {
            "filename": str(att.filename or "").strip()[:180],
            "content_type": str(att.content_type or "").strip()[:100],
            "size_bytes": int(att.size_bytes or 0),
        }
        for att in request.attachments
        if str(att.filename or "").strip()
    ]
    ticket_id = await _create_support_ticket(
        name=request.name,
        email=str(request.email),
        subject=subject,
        message=message,
        category=request.category or "general",
        priority=request.priority or "medium",
        ai_suggested=request.ai_suggested,
        ai_confidence=request.ai_confidence,
        suggestion_intent=request.suggestion_intent,
        attachments=attachments_meta,
    )
    email_sent = await _send_support_confirmation_email(
        name=request.name,
        email=str(request.email),
        ticket_id=ticket_id,
        subject=subject,
        message=message,
    )

    return {
        "success": True,
        "ticket_id": ticket_id,
        "email_sent": email_sent,
        "attachments_count": len(attachments_meta),
        "message": f"Ticket {ticket_id} created. We'll respond as soon as possible.",
    }


@router.post("/support/email/submit")
async def submit_support_email_form(
    name: str = Form(...),
    email: EmailStr = Form(...),
    subject: str = Form("Support Request"),
    message: str = Form(...),
    category: str = Form("general"),
    priority: str = Form("medium"),
    ai_suggested: bool = Form(False),
    ai_confidence: Optional[float] = Form(None),
    suggestion_intent: Optional[str] = Form("draft"),
    attachments: List[UploadFile] = File(default=[]),
):
    normalized_subject = str(subject or "Support Request").strip()[:180] or "Support Request"
    normalized_message = str(message or "").strip()[:4000]
    if len(normalized_message) < 8:
        normalized_message = f"Support request details: {normalized_message or 'No details provided.'}"[:4000]

    if len(attachments) > SUPPORT_EMAIL_MAX_ATTACHMENTS:
        attachments = attachments[:SUPPORT_EMAIL_MAX_ATTACHMENTS]

    attachment_rows: List[Dict[str, Any]] = []
    for upload in attachments:
        if not upload.filename:
            continue
        content_type = str(upload.content_type or "").strip().lower()
        if content_type not in SUPPORT_EMAIL_ALLOWED_ATTACHMENT_TYPES:
            logger.warning("Skipping unsupported support attachment type: %s", content_type)
            continue
        payload = await upload.read()
        if len(payload) > SUPPORT_EMAIL_MAX_ATTACHMENT_BYTES:
            logger.warning("Skipping oversized support attachment: %s", upload.filename)
            continue

        try:
            security_scan = enforce_file_security(
                content=payload,
                claimed_content_type=content_type,
                allowed_content_types=SUPPORT_EMAIL_ALLOWED_ATTACHMENT_TYPES,
                allow_unrecognized_signatures=True,
            )
        except ValueError:
            logger.warning("Skipping attachment that failed security scan: %s", upload.filename)
            continue

        attachment_id = f"satt_{uuid.uuid4().hex[:12]}"
        await db.support_ticket_attachments.insert_one(
            {
                "attachment_id": attachment_id,
                "filename": upload.filename,
                "content_type": content_type,
                "size_bytes": len(payload),
                "content_base64": base64.b64encode(payload).decode("utf-8"),
                "security_scan": security_scan,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        attachment_rows.append(
            {
                "attachment_id": attachment_id,
                "filename": upload.filename,
                "content_type": content_type,
                "size_bytes": len(payload),
                "url": f"/api/support/attachment/{attachment_id}",
                "download_url": f"/api/support/attachment/{attachment_id}?download=1",
            }
        )

    ticket_id = await _create_support_ticket(
        name=name,
        email=str(email),
        subject=normalized_subject,
        message=normalized_message,
        category=category,
        priority=priority,
        ai_suggested=ai_suggested,
        ai_confidence=ai_confidence,
        suggestion_intent=suggestion_intent,
        attachments=attachment_rows,
    )
    if attachment_rows:
        await db.support_ticket_attachments.update_many(
            {"attachment_id": {"$in": [row["attachment_id"] for row in attachment_rows]}},
            {"$set": {"ticket_id": ticket_id}},
        )

    email_sent = await _send_support_confirmation_email(
        name=name,
        email=str(email),
        ticket_id=ticket_id,
        subject=normalized_subject,
        message=normalized_message,
    )

    return {
        "success": True,
        "ticket_id": ticket_id,
        "email_sent": email_sent,
        "attachments_count": len(attachment_rows),
        "message": f"Ticket {ticket_id} created. We'll respond as soon as possible.",
    }


# ── Feedback ──
class FeedbackRequest(BaseModel):
    user_id: str
    email: Optional[str] = None
    type: str = "feedback"
    message: str
    rating: int = None


@router.post("/support/feedback")
async def submit_feedback(request: FeedbackRequest):
    email_plain = request.email or ""
    feedback = {
        "feedback_id": str(uuid.uuid4().hex[:12]),
        "user_id": request.user_id,
        "email": encrypt_field(email_plain) if email_plain else None,
        "email_hash": hash_lookup(email_plain) if email_plain else None,
        "type": request.type,
        "message": encrypt_field(request.message),
        "rating": request.rating,
        "status": "open",
        "admin_notes": [],
        "reply_logs": [],
        "resolved_at": None,
        "responded_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.feedback.insert_one({**feedback})
    return {"message": "Thank you for your feedback!", "feedback_id": feedback["feedback_id"]}


# ── Admin Submissions ──
class AdminSubmissionUpdateRequest(BaseModel):
    submission_id: str
    submission_type: str
    status: Optional[str] = None
    note: Optional[str] = None
    admin_user: Optional[str] = None


class AdminSubmissionReplyRequest(BaseModel):
    submission_id: str
    submission_type: str
    to_email: str
    subject: str
    message: str
    admin_user: Optional[str] = None


def normalize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now(timezone.utc).isoformat()


async def require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def map_user_emails(user_ids: List[str]) -> Dict[str, str]:
    if not user_ids:
        return {}
    email_map = {uid: uid for uid in user_ids if isinstance(uid, str) and "@" in uid}
    lookup_ids = [uid for uid in user_ids if uid not in email_map]
    if lookup_ids:
        users = await db.users.find({"user_id": {"$in": lookup_ids}}).to_list(len(lookup_ids))
        email_map.update({u.get("user_id"): u.get("email") for u in users if u.get("user_id")})
    return email_map


@router.get("/admin/submissions")
async def get_admin_submissions(
    request: Request,
    type: str = "all",
    status: str = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    await require_admin(request)

    submissions: List[Dict[str, Any]] = []
    support_tickets: List[Dict[str, Any]] = []
    async for ticket in iter_find_paginated(db.support_tickets, {}, max_docs=5000):
        support_tickets.append(ticket)
    for t in support_tickets:
        decrypt_doc(t, _TICKET_ENC_FIELDS)

    feedback_entries: List[Dict[str, Any]] = []
    async for feedback in iter_find_paginated(db.feedback, {}, max_docs=5000):
        feedback_entries.append(feedback)
    for f in feedback_entries:
        decrypt_doc(f, _FEEDBACK_ENC_FIELDS)

    ai_feedback_entries: List[Dict[str, Any]] = []
    async for ai_feedback in iter_find_paginated(db.ai_feedback, {}, max_docs=5000):
        ai_feedback_entries.append(ai_feedback)

    faq_feedback_entries: List[Dict[str, Any]] = []
    async for faq_feedback in iter_find_paginated(db.faq_feedback, {}, max_docs=5000):
        faq_feedback_entries.append(faq_feedback)

    user_ids = list(
        {
            *(f.get("user_id") for f in feedback_entries if f.get("user_id")),
            *(a.get("user_id") for a in ai_feedback_entries if a.get("user_id")),
        }
    )
    email_lookup = await map_user_emails(user_ids)

    for ticket in support_tickets:
        submissions.append(
            {
                "id": ticket.get("ticket_id") or str(ticket.get("_id")),
                "type": "support_ticket",
                "status": ticket.get("status", "open"),
                "name": ticket.get("name"),
                "email": ticket.get("email"),
                "subject": ticket.get("subject"),
                "message": ticket.get("message"),
                "category": ticket.get("category"),
                "priority": ticket.get("priority"),
                "attachments": ticket.get("attachments", []),
                "admin_notes": ticket.get("admin_notes", []),
                "reply_logs": ticket.get("reply_logs", []),
                "resolved_at": ticket.get("resolved_at"),
                "responded_at": ticket.get("responded_at"),
                "created_at": normalize_timestamp(ticket.get("created_at")),
            }
        )

    for feedback in feedback_entries:
        submissions.append(
            {
                "id": feedback.get("feedback_id") or str(feedback.get("_id")),
                "type": "feedback",
                "status": feedback.get("status", "open"),
                "user_id": feedback.get("user_id"),
                "email": feedback.get("email") or email_lookup.get(feedback.get("user_id")),
                "message": feedback.get("message"),
                "rating": feedback.get("rating"),
                "admin_notes": feedback.get("admin_notes", []),
                "reply_logs": feedback.get("reply_logs", []),
                "resolved_at": feedback.get("resolved_at"),
                "responded_at": feedback.get("responded_at"),
                "created_at": normalize_timestamp(feedback.get("created_at")),
            }
        )

    for entry in ai_feedback_entries:
        submissions.append(
            {
                "id": entry.get("id") or str(entry.get("_id")),
                "type": "ai_feedback",
                "status": entry.get("status", "open"),
                "user_id": entry.get("user_id"),
                "email": email_lookup.get(entry.get("user_id")),
                "feature_key": entry.get("feature_key"),
                "rating": entry.get("rating"),
                "comment": entry.get("comment"),
                "response_excerpt": entry.get("response_excerpt"),
                "session_id": entry.get("session_id"),
                "admin_notes": entry.get("admin_notes", []),
                "reply_logs": entry.get("reply_logs", []),
                "resolved_at": entry.get("resolved_at"),
                "responded_at": entry.get("responded_at"),
                "created_at": normalize_timestamp(entry.get("created_at")),
            }
        )

    for faq in faq_feedback_entries:
        submissions.append(
            {
                "id": faq.get("feedback_id") or str(faq.get("_id")),
                "type": "faq_feedback",
                "status": faq.get("status", "open"),
                "question": faq.get("question"),
                "helpful": faq.get("helpful"),
                "admin_notes": faq.get("admin_notes", []),
                "resolved_at": faq.get("resolved_at"),
                "responded_at": faq.get("responded_at"),
                "created_at": normalize_timestamp(faq.get("created_at")),
            }
        )

    if type != "all":
        submissions = [s for s in submissions if s.get("type") == type]
    if status != "all":
        submissions = [s for s in submissions if s.get("status") == status]

    submissions.sort(key=lambda s: s.get("created_at") or "", reverse=True)

    counts = {
        "total": len(submissions),
        "open": len([s for s in submissions if s.get("status") == "open"]),
        "resolved": len([s for s in submissions if s.get("status") == "resolved"]),
        "responded": len([s for s in submissions if s.get("status") == "responded"]),
    }

    total_count = len(submissions)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged = submissions[start_idx:end_idx]

    return {
        "data": paged,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "submissions": paged,
        "counts": counts,
    }


@router.post("/admin/submissions/update")
async def update_admin_submission(request: AdminSubmissionUpdateRequest, req: Request):
    await require_admin(req)

    mapping = {
        "support_ticket": (db.support_tickets, "ticket_id"),
        "feedback": (db.feedback, "feedback_id"),
        "ai_feedback": (db.ai_feedback, "id"),
        "faq_feedback": (db.faq_feedback, "feedback_id"),
    }
    if request.submission_type not in mapping:
        raise HTTPException(status_code=400, detail="Unknown submission type")
    collection, key_field = mapping[request.submission_type]
    update_doc: Dict[str, Any] = {}
    if request.status:
        update_doc.setdefault("$set", {})["status"] = request.status
        update_doc.setdefault("$set", {})["updated_at"] = datetime.now(timezone.utc).isoformat()
        if request.status == "resolved":
            update_doc.setdefault("$set", {})["resolved_at"] = datetime.now(timezone.utc).isoformat()
        if request.status == "responded":
            update_doc.setdefault("$set", {})["responded_at"] = datetime.now(timezone.utc).isoformat()
    if request.note:
        update_doc.setdefault("$push", {})["admin_notes"] = {
            "id": str(uuid.uuid4().hex[:8]),
            "note": request.note,
            "author": request.admin_user or "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    if not update_doc:
        raise HTTPException(status_code=400, detail="No updates provided")

    result = await collection.update_one({key_field: request.submission_id}, update_doc)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {"success": True}


@router.post("/admin/submissions/reply")
async def reply_admin_submission(request: AdminSubmissionReplyRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")

    mapping = {
        "support_ticket": (db.support_tickets, "ticket_id"),
        "feedback": (db.feedback, "feedback_id"),
        "ai_feedback": (db.ai_feedback, "id"),
        "faq_feedback": (db.faq_feedback, "feedback_id"),
    }
    if request.submission_type not in mapping:
        raise HTTPException(status_code=400, detail="Unknown submission type")
    collection, key_field = mapping[request.submission_type]

    try:
        result = await send_catalog_template(
            recipient_email=request.to_email,
            template_key="admin_reply",
            ticket_id=request.subject,
            subject=request.message,
        )
        if not result.get("success"):
            logger.error(f"Admin reply email failed: {result.get('error')}")
            raise HTTPException(status_code=500, detail="Failed to send email")

        # Log the email for tracking
        try:
            from utils.email_notifications import notify

            await notify.ticket_response(
                request.submission_id,
                request.to_email,
                "",
                request.submission_id,
                request.subject,
                request.message[:200],
            )
        except Exception:
            pass
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin reply email failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")

    await collection.update_one(
        {key_field: request.submission_id},
        {
            "$set": {
                "status": "responded",
                "responded_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$push": {
                "reply_logs": {
                    "id": str(uuid.uuid4().hex[:8]),
                    "to": request.to_email,
                    "subject": request.subject,
                    "message": request.message[:5000],
                    "author": request.admin_user or "admin",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        },
    )

    return {"success": True}


class AdminSmsRequest(BaseModel):
    to_phone: str
    message: str
    admin_user: Optional[str] = None


class AdminWhatsAppRequest(BaseModel):
    to_phone: str
    message: str
    media_url: Optional[str] = None
    admin_user: Optional[str] = None


@router.post("/admin/messages/sms")
async def send_admin_sms(request: AdminSmsRequest, req: Request):
    await require_admin(req)
    mock_id = f"mock_sms_{uuid.uuid4().hex[:8]}"
    logger.info("SMS send requested (MOCKED)", extra={"to_phone": request.to_phone, "admin_user": request.admin_user})
    return {
        "success": True,
        "mocked": True,
        "message_id": mock_id,
        "status": "SMS sending is pending approval and currently mocked.",
    }


@router.post("/admin/messages/whatsapp")
async def send_admin_whatsapp(request: AdminWhatsAppRequest, req: Request):
    await require_admin(req)
    raise HTTPException(status_code=400, detail="WhatsApp messaging is not supported in this application")


class AdminAiReportRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    report_summary: str
    report_link: str
    feedback_link: str


class AdminFeatureUpdateRequest(BaseModel):
    to_email: EmailStr
    title: str
    summary: str
    features: List[str]
    learn_more_link: str


class AdminRenewalReminderRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    plan_name: str
    renewal_date: str
    amount: str


class AdminFailedPaymentRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    plan_name: str
    amount: str
    update_link: str


class AdminTrialExpirationRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    trial_end_date: str
    upgrade_link: str


@router.post("/admin/messages/ai-report")
async def send_ai_report(request: AdminAiReportRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="ai_report",
        user_name=request.user_name,
        report_summary=request.report_summary,
        report_link=request.report_link,
        feedback_link=request.feedback_link,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send AI report email")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/feature-update")
async def send_feature_update(request: AdminFeatureUpdateRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="feature_update",
        title=request.title,
        summary=request.summary,
        features=request.features,
        learn_more_link=request.learn_more_link,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send feature update")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/renewal-reminder")
async def send_renewal_reminder(request: AdminRenewalReminderRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="renewal_reminder",
        user_name=request.user_name,
        plan_name=request.plan_name,
        renewal_date=request.renewal_date,
        amount=request.amount,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send renewal reminder")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/failed-payment")
async def send_failed_payment(request: AdminFailedPaymentRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="failed_payment",
        user_name=request.user_name,
        plan_name=request.plan_name,
        amount=request.amount,
        update_link=request.update_link,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send failed payment email")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/trial-expiration")
async def send_trial_expiration(request: AdminTrialExpirationRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="trial_expiration",
        user_name=request.user_name,
        trial_end_date=request.trial_end_date,
        upgrade_link=request.upgrade_link,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send trial expiration email")
    return {"success": True, "message_id": result.get("message_id")}


class AdminPlanChangeRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    old_plan: str
    new_plan: str
    effective_date: str


class AdminSubscriptionCancelledRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    plan_name: str
    end_date: str


class AdminUsageAlertRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    usage_metric: str
    limit: str
    reset_date: str


class AdminSecurityAlertRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    location: str
    device: str
    event_time: str


class AdminWeeklyDigestRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    highlights: List[str]
    stats: List[str]


class AdminInvitationRequest(BaseModel):
    to_email: EmailStr
    inviter_name: str
    team_name: str
    invite_link: str


class AdminOnboardingNudgeRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    next_steps: List[str]


class AdminPasswordChangedRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    changed_at: str


class AdminAccountDeletedRequest(BaseModel):
    to_email: EmailStr
    user_name: str
    deleted_at: str


@router.post("/admin/messages/plan-change")
async def send_plan_change(request: AdminPlanChangeRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="plan_changed",
        user_name=request.user_name,
        old_plan=request.old_plan,
        new_plan=request.new_plan,
        effective_date=request.effective_date,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send plan change email")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/subscription-cancelled")
async def send_subscription_cancelled(request: AdminSubscriptionCancelledRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="subscription_cancelled",
        user_name=request.user_name,
        plan_name=request.plan_name,
        end_date=request.end_date,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send cancellation email")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/usage-alert")
async def send_usage_alert(request: AdminUsageAlertRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="usage_alert",
        user_name=request.user_name,
        usage_metric=request.usage_metric,
        limit=request.limit,
        reset_date=request.reset_date,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send usage alert")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/security-alert")
async def send_security_alert(request: AdminSecurityAlertRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="security_alert",
        user_name=request.user_name,
        location=request.location,
        device=request.device,
        event_time=request.event_time,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send security alert")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/weekly-digest")
async def send_weekly_digest(request: AdminWeeklyDigestRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="weekly_digest",
        user_name=request.user_name,
        highlights=request.highlights,
        stats=request.stats,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send weekly digest")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/invitation")
async def send_invitation(request: AdminInvitationRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="invitation",
        inviter_name=request.inviter_name,
        team_name=request.team_name,
        invite_link=request.invite_link,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send invitation")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/onboarding-nudge")
async def send_onboarding_nudge(request: AdminOnboardingNudgeRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="onboarding_nudge",
        user_name=request.user_name,
        next_steps=request.next_steps,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send onboarding nudge")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/password-changed")
async def send_password_changed(request: AdminPasswordChangedRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="password_changed",
        user_name=request.user_name,
        changed_at=request.changed_at,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send password change email")
    return {"success": True, "message_id": result.get("message_id")}


@router.post("/admin/messages/account-deleted")
async def send_account_deleted(request: AdminAccountDeletedRequest, req: Request):
    await require_admin(req)
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="Email service not configured")
    result = await send_catalog_template(
        recipient_email=request.to_email,
        template_key="account_deleted",
        user_name=request.user_name,
        deleted_at=request.deleted_at,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to send account deletion email")
    return {"success": True, "message_id": result.get("message_id")}



# ════════════════════════════════════════════════════════════
# REPLY TEMPLATES FOR CONTACT SUBMISSIONS
# ════════════════════════════════════════════════════════════

REPLY_TEMPLATES = [
    {
        "id": "lockout_support",
        "label": "Lockout Support",
        "icon": "shield-checkmark",
        "category": "Support",
        "body": (
            "Hi {name},\n\n"
            "Thank you for reaching out. We understand how frustrating it can be to lose access to your account.\n\n"
            "We've reviewed your account and taken the following steps:\n"
            "- Cleared any temporary IP blocks associated with your login attempts\n"
            "- Reset your failed login counter\n\n"
            "You should now be able to log in normally. If you're still having trouble, please try:\n"
            "1. Clearing your browser cache and cookies\n"
            "2. Using the 'Forgot Password' link on the login page\n"
            "3. Trying a different browser or device\n\n"
            "If the issue persists, please reply to this email and we'll escalate the matter immediately.\n\n"
            "Best regards,\n{brand} Support Team"
        ),
    },
    {
        "id": "billing_help",
        "label": "Billing Help",
        "icon": "card",
        "category": "Billing",
        "body": (
            "Hi {name},\n\n"
            "Thank you for contacting us about your billing concern.\n\n"
            "Here's what I can help with:\n"
            "- **Payment issues**: If a charge failed, please verify your card details in Settings > Payment Cards\n"
            "- **Plan changes**: You can upgrade or downgrade from Settings > Subscription\n"
            "- **Refund requests**: Please provide your transaction ID and we'll review within 24 hours\n"
            "- **Invoice questions**: All invoices are available in Settings > Payment History\n\n"
            "If you need further assistance, please don't hesitate to reply with more details about your specific concern.\n\n"
            "Best regards,\n{brand} Support Team"
        ),
    },
    {
        "id": "general_support",
        "label": "General Support",
        "icon": "chatbubbles",
        "category": "General",
        "body": (
            "Hi {name},\n\n"
            "Thank you for reaching out to {brand} support. We appreciate you taking the time to contact us.\n\n"
            "We've received your message and are looking into it. Here's what to expect:\n"
            "- We typically respond within 24 hours for standard inquiries\n"
            "- High-priority issues are escalated immediately\n"
            "- You'll receive email updates as your ticket progresses\n\n"
            "In the meantime, you might find our Help Center useful: check the FAQ section in your dashboard.\n\n"
            "Best regards,\n{brand} Support Team"
        ),
    },
    {
        "id": "feature_request",
        "label": "Feature Request",
        "icon": "bulb",
        "category": "Product",
        "body": (
            "Hi {name},\n\n"
            "Thank you for sharing your feature suggestion with us! We love hearing from users who are invested in making {brand} better.\n\n"
            "Your request has been logged and shared with our product team. While we can't guarantee a timeline, we prioritize features based on:\n"
            "- Number of users requesting similar functionality\n"
            "- Alignment with our product roadmap\n"
            "- Technical feasibility\n\n"
            "We'll keep you updated if and when this feature moves into development.\n\n"
            "Best regards,\n{brand} Product Team"
        ),
    },
    {
        "id": "technical_issue",
        "label": "Technical Issue",
        "icon": "construct",
        "category": "Technical",
        "body": (
            "Hi {name},\n\n"
            "Thank you for reporting this technical issue. We take platform reliability seriously.\n\n"
            "To help us resolve this quickly, could you please provide:\n"
            "1. The browser and device you're using\n"
            "2. Steps to reproduce the issue\n"
            "3. Any error messages you see\n"
            "4. Screenshots if possible\n\n"
            "Our engineering team is already investigating. We'll update you as soon as we have a resolution.\n\n"
            "Best regards,\n{brand} Technical Support"
        ),
    },
]


@router.get("/contact/reply-templates")
async def get_reply_templates(request: Request):
    """Return available reply templates for contact submissions. Admin only."""
    from routes.db import get_current_user
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    brand = os.environ.get("BRAND_NAME", "RealAICoach")
    return {
        "templates": [
            {
                "id": t["id"],
                "label": t["label"],
                "icon": t["icon"],
                "category": t["category"],
                "body": t["body"].replace("{brand}", brand),
            }
            for t in REPLY_TEMPLATES
        ]
    }


@router.post("/contact/reply-templates/apply")
async def apply_reply_template(request: Request):
    """Apply a reply template with name substitution. Admin only."""
    from routes.db import get_current_user
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    template_id = body.get("template_id", "")
    contact_name = body.get("contact_name", "there")
    brand = os.environ.get("BRAND_NAME", "RealAICoach")

    tpl = next((t for t in REPLY_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    rendered = tpl["body"].replace("{name}", contact_name).replace("{brand}", brand)
    return {"template_id": template_id, "rendered_body": rendered}

