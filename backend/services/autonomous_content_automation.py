"""Autonomous weekly blog + newsletter automation (no manual admin input)."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from emergentintegrations.llm.chat import LlmChat, UserMessage

from routes.db import EMERGENT_LLM_KEY
from utils.email_service import send_email

logger = logging.getLogger(__name__)


CONTENT_TOPICS = [
    "AI coaching for enterprise team performance",
    "career growth strategies with AI copilots",
    "productivity frameworks for managers using AI",
    "ethical AI usage for workplace development",
    "data-driven leadership skills in modern teams",
    "building high-retention learning cultures with AI",
]


def _week_key(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", str(text or "").strip().lower())
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or f"weekly-{uuid.uuid4().hex[:8]}"


def _parse_json_response(raw: Any) -> Dict[str, Any]:
    text = raw.text if hasattr(raw, "text") else str(raw)
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _quality_score_blog(payload: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 100
    issues: List[str] = []

    title = str(payload.get("title") or "").strip()
    excerpt = str(payload.get("excerpt") or "").strip()
    tags = payload.get("tags") or []
    content_blocks = payload.get("content") or []

    if len(title) < 32:
        score -= 18
        issues.append("title_too_short")
    if len(title) > 95:
        score -= 8
        issues.append("title_too_long")

    if len(excerpt) < 120:
        score -= 16
        issues.append("excerpt_too_short")

    if not isinstance(tags, list) or len(tags) < 3:
        score -= 14
        issues.append("tags_insufficient")

    if not isinstance(content_blocks, list) or len(content_blocks) < 8:
        score -= 22
        issues.append("content_blocks_insufficient")

    paragraph_count = 0
    for item in content_blocks:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() == "paragraph":
            paragraph_count += 1
    if paragraph_count < 5:
        score -= 12
        issues.append("paragraph_count_low")

    if "realaicoach" not in (title + " " + excerpt).lower():
        score -= 6
        issues.append("brand_context_missing")

    return max(0, score), issues


async def _generate_blog_payload(topic: str, week: str, attempt: int) -> Dict[str, Any]:
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY is required for autonomous content automation")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"auto-content-{week}-{attempt}-{uuid.uuid4().hex[:8]}",
        system_message=(
            "You are a senior B2B SaaS content strategist for RealAICoach. "
            "Return only valid JSON with professional, factual, publish-ready content."
        ),
    ).with_model("openai", "gpt-4o")

    prompt = f"""
Generate a weekly enterprise blog post package for week {week}.
Topic focus: {topic}

Return ONLY valid JSON object with this schema:
{{
  "title": "string",
  "category": "Industry Insights|Product Update|Research|Enterprise|Tips & Tricks",
  "author": "string",
  "author_role": "string",
  "read_time": "e.g. 7 min read",
  "excerpt": "120-220 chars",
  "tags": ["3-6 tags"],
  "content": [
    {{"type":"paragraph","text":"..."}},
    {{"type":"heading","text":"..."}},
    {{"type":"paragraph","text":"..."}},
    {{"type":"quote","text":"...","author":"..."}}
  ],
  "newsletter": {{
    "subject": "<=78 chars",
    "preheader": "<=120 chars",
    "hook": "1-2 lines",
    "highlights": ["exactly 3 concise bullet points"],
    "cta_label": "string"
  }}
}}

Requirements:
- Minimum 8 content blocks with at least 5 paragraphs.
- Tone: enterprise, actionable, specific.
- Mention RealAICoach naturally.
- Avoid markdown fences, avoid placeholders.
"""

    raw = await chat.send_message(UserMessage(text=prompt))
    return _parse_json_response(raw)


def _build_blog_document(payload: Dict[str, Any], week: str, triggered_by: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    title = str(payload.get("title") or "Weekly AI Coaching Insights").strip()
    slug = f"{_slugify(title)}-{week.lower().replace('w', 'w')}"
    slug = slug[:96].rstrip("-")
    content = payload.get("content") if isinstance(payload.get("content"), list) else []

    return {
        "slug": slug,
        "title": title,
        "category": str(payload.get("category") or "Industry Insights"),
        "author": str(payload.get("author") or "RealAICoach Editorial"),
        "author_role": str(payload.get("author_role") or "AI Content Team"),
        "read_time": str(payload.get("read_time") or "7 min read"),
        "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&h=600&fit=crop",
        "image_alt": "Enterprise analytics dashboard",
        "excerpt": str(payload.get("excerpt") or "Weekly expert insights from RealAICoach."),
        "content": content,
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else ["AI Coaching", "Enterprise"],
        "published_at": now.isoformat(),
        "date_display": now.strftime("%b %d, %Y"),
        "created_at": now.isoformat(),
        "active": True,
        "source": "autonomous_weekly",
        "auto_week_key": week,
        "created_by": triggered_by,
        "newsletter": payload.get("newsletter") if isinstance(payload.get("newsletter"), dict) else {},
    }


def _build_autonomous_newsletter_html(base_url: str, email: str, blog_doc: Dict[str, Any]) -> Tuple[str, str]:
    # Use the V7 `_wrap()` shell so the email passes the runtime guardrail
    # (requires `em-outer` fingerprint — see utils/email_service.py).
    from utils.email_templates import _wrap, _lead, _callout
    week_label = datetime.now(timezone.utc).strftime("%B %d, %Y")
    newsletter = blog_doc.get("newsletter") or {}
    subject = str(newsletter.get("subject") or f"Weekly Insights: {blog_doc.get('title')}")
    preheader = str(newsletter.get("preheader") or blog_doc.get("excerpt") or "Latest insights from RealAICoach")
    hook = str(newsletter.get("hook") or blog_doc.get("excerpt") or "")
    highlights = newsletter.get("highlights") if isinstance(newsletter.get("highlights"), list) else []
    highlights = [str(h) for h in highlights[:3]]
    cta_label = str(newsletter.get("cta_label") or "Read the full article")
    blog_url = f"{base_url}/blog/{blog_doc.get('slug')}"

    highlight_html = "".join(
        f'<li style="margin-bottom:8px;color:#334155;font-size:14px;line-height:1.5">{h}</li>' for h in highlights
    )

    inner = (
        _lead(blog_doc.get("title") or "Weekly Insights", f"{week_label} · {preheader}")
        + f'<p class="em-text" style="margin:0 0 14px;color:#0F172A;font-size:15px;line-height:1.6;">{hook}</p>'
        + (f'<ul style="padding-left:20px;margin:0 0 18px;">{highlight_html}</ul>' if highlight_html else "")
        + _callout(f'You are receiving this because <strong>{email}</strong> is subscribed to RealAICoach weekly updates.')
    )

    html = _wrap(
        "RealAICoach Weekly",
        preheader,
        inner,
        cta_label,
        blog_url,
        category="engagement",
    )
    return subject, html


async def run_weekly_autonomous_content_cycle(db, triggered_by: str = "scheduler", subscriber_limit: int | None = None) -> Dict[str, Any]:
    """Generate weekly blog + newsletter automatically with retries and quality gate."""
    now = datetime.now(timezone.utc)
    week = _week_key(now)
    run_id = f"auto_content_{uuid.uuid4().hex[:10]}"
    run_started_at = now.isoformat()

    async def _update_run(status: str, **extra: Any) -> None:
        payload = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        await db.autonomous_content_runs.update_one({"run_id": run_id}, {"$set": payload}, upsert=False)

    existing_run = await db.autonomous_content_runs.find_one(
        {"week_key": week, "status": "completed"}, {"_id": 0, "run_id": 1}
    )
    if existing_run:
        existing_digest = await db.newsletter_digests.find_one({"digest_id": f"autoweekly-{week}"}, {"_id": 0})
        return {
            "run_id": run_id,
            "week_key": week,
            "status": "skipped",
            "reason": "already_completed",
            "existing_run_id": existing_run.get("run_id"),
            "newsletter_digest_id": f"autoweekly-{week}",
            "newsletter_sent": int((existing_digest or {}).get("total_recipients") or 0),
            "newsletter_failed": int((existing_digest or {}).get("failed_recipients") or 0),
        }

    await db.autonomous_content_runs.insert_one(
        {
            "run_id": run_id,
            "week_key": week,
            "status": "running",
            "triggered_by": triggered_by,
            "created_at": run_started_at,
            "updated_at": run_started_at,
        }
    )

    base_url = str(os.environ.get("FRONTEND_BASE_URL") or "").strip()
    if not base_url:
        await _update_run("failed", last_error="FRONTEND_BASE_URL is required for autonomous content automation")
        raise RuntimeError("FRONTEND_BASE_URL is required for autonomous content automation")

    topic = CONTENT_TOPICS[now.isocalendar().week % len(CONTENT_TOPICS)]
    selected_payload: Dict[str, Any] | None = None
    selected_score = 0
    selected_issues: List[str] = []

    for attempt in range(1, 4):
        try:
            payload = await _generate_blog_payload(topic=topic, week=week, attempt=attempt)
            score, issues = _quality_score_blog(payload)
            if score >= 78:
                selected_payload = payload
                selected_score = score
                selected_issues = issues
                break
            selected_payload = payload
            selected_score = score
            selected_issues = issues
        except Exception as exc:
            logger.warning(f"Autonomous content generation attempt {attempt} failed: {exc}")

    if not selected_payload or selected_score < 78:
        await _update_run(
            "failed",
            quality_score=selected_score,
            quality_issues=selected_issues,
            topic=topic,
        )
        raise RuntimeError(f"Autonomous content quality gate failed (score={selected_score})")

    blog_doc = _build_blog_document(selected_payload, week=week, triggered_by=triggered_by)

    existing_blog = await db.blog_posts.find_one(
        {"auto_week_key": week, "source": "autonomous_weekly"}, {"_id": 0, "slug": 1}
    )
    if not existing_blog:
        await db.blog_posts.insert_one({**blog_doc})
    else:
        await db.blog_posts.update_one(
            {"auto_week_key": week, "source": "autonomous_weekly"},
            {"$set": {**blog_doc, "updated_at": now.isoformat()}},
            upsert=False,
        )

    # ── Autonomous Blog Hub content (video + demo + testimonial + photo) ──
    # Runs alongside the weekly article. Idempotent per week_key — skips if already
    # generated for this ISO week. Failures are logged but never fail the cycle.
    hub_result: Dict[str, Any] = {}
    try:
        from services.autonomous_hub_content import run_weekly_hub_content
        hub_result = await run_weekly_hub_content(db, week)
        logger.info(f"[autonomous-cycle] hub content: {hub_result}")
    except Exception as exc:
        logger.error(f"[autonomous-cycle] hub content generation failed: {exc}")
        hub_result = {"error": str(exc)[:200]}

    digest_id = f"autoweekly-{week}"
    existing_digest = await db.newsletter_digests.find_one({"digest_id": digest_id}, {"_id": 0, "digest_id": 1})
    subscribers_query = {
        "status": "active",
        "subscription_type": {"$in": ["platform", "blog", "all"]},
    }
    subscribers = []
    if subscriber_limit != 0:
        subscribers = await db.newsletter_subscribers.find(subscribers_query, {"_id": 0, "email": 1}).to_list(
            subscriber_limit or 50000
        )

    delivered_emails = set(
        await db.autonomous_content_deliveries.distinct(
            "recipient",
            {"digest_id": digest_id, "status": "sent"},
        )
    )

    sent = 0
    failed = 0
    skipped_existing = 0

    if not existing_digest:
        await db.newsletter_digests.insert_one(
            {
                "digest_id": digest_id,
                "type": "autonomous_weekly_newsletter",
                "week_key": week,
                "blog_slug": blog_doc.get("slug"),
                "sent_at": now.isoformat(),
                "total_recipients": 0,
                "failed_recipients": 0,
                "skipped_recipients": 0,
                "status": "running",
            }
        )
    else:
        await db.newsletter_digests.update_one(
            {"digest_id": digest_id},
            {
                "$set": {
                    "type": "autonomous_weekly_newsletter",
                    "week_key": week,
                    "blog_slug": blog_doc.get("slug"),
                    "status": "running",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    for sub in subscribers:
        email = str(sub.get("email") or "").strip().lower()
        if not email:
            continue
        if email in delivered_emails:
            skipped_existing += 1
            continue

        subject, html = _build_autonomous_newsletter_html(base_url, email, blog_doc)
        delivered = False
        last_error = ""

        for attempt in range(1, 4):
            try:
                response = await send_email(
                    recipient_email=email,
                    subject=subject,
                    content=html,
                    template_key="auto-weekly-newsletter-v2",
                )
                if not response.get("success"):
                    last_error = str(response.get("error") or "Email send failed")
                    raise RuntimeError(last_error)

                await db.autonomous_content_deliveries.update_one(
                    {"digest_id": digest_id, "recipient": email},
                    {
                        "$set": {
                            "digest_id": digest_id,
                            "recipient": email,
                            "subject": subject,
                            "blog_slug": blog_doc.get("slug"),
                            "status": "sent",
                            "sent_at": datetime.now(timezone.utc).isoformat(),
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "template_key": "auto-weekly-newsletter-v2",
                        },
                        "$inc": {"attempt_count": 1},
                    },
                    upsert=True,
                )
                delivered = True
                delivered_emails.add(email)
                break
            except Exception as exc:
                last_error = str(exc)
                await db.autonomous_content_deliveries.update_one(
                    {"digest_id": digest_id, "recipient": email},
                    {
                        "$set": {
                            "digest_id": digest_id,
                            "recipient": email,
                            "subject": subject,
                            "blog_slug": blog_doc.get("slug"),
                            "status": "failed",
                            "last_error": last_error[:400],
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "template_key": "auto-weekly-newsletter-v2",
                        },
                        "$inc": {"attempt_count": 1},
                    },
                    upsert=True,
                )
                logger.warning(f"Newsletter send retry {attempt}/3 failed for {email}: {exc}")

        if delivered:
            sent += 1
        else:
            failed += 1

    digest_status = "completed" if failed == 0 else "completed_with_failures"
    overall_status = "completed" if failed == 0 else "completed_with_failures"
    await db.newsletter_digests.update_one(
        {"digest_id": digest_id},
        {
            "$set": {
                "total_recipients": sent,
                "failed_recipients": failed,
                "skipped_recipients": skipped_existing,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": digest_status,
            }
        },
    )

    result = {
        "run_id": run_id,
        "week_key": week,
        "status": overall_status,
        "triggered_by": triggered_by,
        "topic": topic,
        "quality_score": selected_score,
        "quality_issues": selected_issues,
        "blog_slug": blog_doc.get("slug"),
        "newsletter_digest_id": digest_id,
        "subscribers_total": len(subscribers),
        "newsletter_sent": sent,
        "newsletter_failed": failed,
        "newsletter_skipped_existing": skipped_existing,
        "hub_content": hub_result,
        "created_at": now.isoformat(),
    }
    await _update_run(
        overall_status,
        topic=topic,
        quality_score=selected_score,
        quality_issues=selected_issues,
        blog_slug=blog_doc.get("slug"),
        newsletter_digest_id=digest_id,
        subscribers_total=len(subscribers),
        newsletter_sent=sent,
        newsletter_failed=failed,
        newsletter_skipped_existing=skipped_existing,
        digest_status=digest_status,
    )
    return result
