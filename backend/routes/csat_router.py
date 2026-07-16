"""CSAT (Customer Satisfaction) Survey System — Routes & Logic"""

import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/csat", tags=["csat"])

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")

# ── Survey Questions ──
SURVEY_QUESTIONS = [
    {
        "id": "overall_satisfaction",
        "text": "How satisfied are you with the RealAICoach platform overall?",
        "category": "Overall",
    },
    {
        "id": "ai_quality",
        "text": "How would you rate the quality and accuracy of AI coaching responses?",
        "category": "AI Quality",
    },
    {"id": "ui_design", "text": "How would you rate the user interface and visual design?", "category": "UI/UX"},
    {"id": "performance", "text": "How would you rate the platform speed and performance?", "category": "Performance"},
    {
        "id": "feature_completeness",
        "text": "How well does the platform meet your needs with its current features?",
        "category": "Features",
    },
    {"id": "ease_of_use", "text": "How easy is it to navigate and use the platform?", "category": "Usability"},
    {"id": "onboarding", "text": "How would you rate your initial onboarding experience?", "category": "Onboarding"},
    {"id": "value_for_money", "text": "How would you rate the value you get for the price?", "category": "Value"},
    {
        "id": "support_quality",
        "text": "How satisfied are you with the customer support experience?",
        "category": "Support",
    },
    {
        "id": "reliability",
        "text": "How would you rate the platform's reliability and uptime?",
        "category": "Reliability",
    },
    {"id": "recommendation", "text": "How likely are you to recommend RealAICoach to a colleague?", "category": "NPS"},
    {
        "id": "overall_experience",
        "text": "Rate your overall experience with RealAICoach over the past period.",
        "category": "Experience",
    },
]


class SurveySubmission(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    token: str
    responses: dict = Field(..., description="Map of question_id -> score (1-10)")
    feedback: Optional[str] = None


class ManualTriggerRequest(BaseModel):
    target: str = "all"


@router.get("/questions")
async def get_survey_questions():
    return {"questions": SURVEY_QUESTIONS, "scale_min": 1, "scale_max": 10}


@router.post("/submit")
async def submit_survey(submission: SurveySubmission, request: Request):
    from routes.db import db

    # Validate token
    survey_token = await db.csat_tokens.find_one({"token": submission.token}, {"_id": 0})
    if not survey_token:
        raise HTTPException(status_code=400, detail="Invalid or expired survey token")
    if survey_token.get("used"):
        raise HTTPException(status_code=400, detail="This survey has already been completed")

    # Check 30-day token expiry
    token_created = survey_token.get("created_at", "")
    if token_created:
        expiry_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        if token_created < expiry_cutoff:
            raise HTTPException(status_code=400, detail="This survey link has expired. Please wait for a new survey.")

    # Validate responses
    valid_ids = {q["id"] for q in SURVEY_QUESTIONS}
    for qid, score in submission.responses.items():
        if qid not in valid_ids:
            raise HTTPException(status_code=400, detail=f"Unknown question: {qid}")
        if not isinstance(score, (int, float)) or score < 1 or score > 10:
            raise HTTPException(status_code=400, detail=f"Score must be 1-10 for {qid}")

    user_id = survey_token.get("user_id", submission.user_id)
    email = survey_token.get("email", submission.email)

    # Calculate scores
    scores = list(submission.responses.values())
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    nps_score = submission.responses.get("recommendation", 0)

    # Categorize scores
    category_scores = {}
    for q in SURVEY_QUESTIONS:
        if q["id"] in submission.responses:
            category_scores[q["category"]] = submission.responses[q["id"]]

    record = {
        "survey_id": str(uuid.uuid4()),
        "user_id": user_id,
        "email": email,
        "token": submission.token,
        "responses": submission.responses,
        "category_scores": category_scores,
        "average_score": avg_score,
        "nps_score": nps_score,
        "feedback": submission.feedback,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "survey_period": survey_token.get("period", ""),
    }

    await db.csat_responses.insert_one(record)
    await db.csat_tokens.update_one(
        {"token": submission.token}, {"$set": {"used": True, "submitted_at": record["submitted_at"]}}
    )

    # Send CSAT thank-you email
    try:
        from utils.email_service import send_catalog_template, is_email_configured
        if is_email_configured() and email:
            await send_catalog_template(
                recipient_email=email,
                template_key="csat_thank_you",
                user_name=survey_token.get("user_name", email.split("@")[0]),
                rating="positive" if avg_score >= 7 else "neutral" if avg_score >= 4 else "negative",
            )
    except Exception:
        pass

    return {"ok": True, "average_score": avg_score, "message": "Thank you for your feedback!"}


@router.get("/analytics")
async def get_csat_analytics(request: Request):
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    ninety_days_ago = (now - timedelta(days=90)).isoformat()

    all_responses = await db.csat_responses.find({}, {"_id": 0}).sort("submitted_at", -1).to_list(10000)
    recent_responses = [r for r in all_responses if r.get("submitted_at", "") >= thirty_days_ago]
    older_responses = [
        r
        for r in all_responses
        if r.get("submitted_at", "") >= ninety_days_ago and r.get("submitted_at", "") < thirty_days_ago
    ]

    total_users = await db.users.count_documents({})
    total_sent = await db.csat_tokens.count_documents({})
    total_completed = await db.csat_tokens.count_documents({"used": True})

    # Overall metrics
    all_avg = (
        round(sum(r.get("average_score", 0) for r in all_responses) / len(all_responses), 2) if all_responses else 0
    )
    recent_avg = (
        round(sum(r.get("average_score", 0) for r in recent_responses) / len(recent_responses), 2)
        if recent_responses
        else 0
    )
    older_avg = (
        round(sum(r.get("average_score", 0) for r in older_responses) / len(older_responses), 2)
        if older_responses
        else 0
    )
    trend = round(recent_avg - older_avg, 2) if older_responses else 0

    # NPS calculation
    nps_scores = [r.get("nps_score", 0) for r in all_responses if r.get("nps_score")]
    promoters = sum(1 for s in nps_scores if s >= 9) if nps_scores else 0
    detractors = sum(1 for s in nps_scores if s <= 6) if nps_scores else 0
    nps = round(((promoters - detractors) / len(nps_scores)) * 100) if nps_scores else 0

    # Category breakdown
    category_totals = {}
    category_counts = {}
    for r in all_responses:
        for cat, score in r.get("category_scores", {}).items():
            category_totals[cat] = category_totals.get(cat, 0) + score
            category_counts[cat] = category_counts.get(cat, 0) + 1
    category_averages = {cat: round(category_totals[cat] / category_counts[cat], 2) for cat in category_totals}

    # Question breakdown
    question_totals = {}
    question_counts = {}
    for r in all_responses:
        for qid, score in r.get("responses", {}).items():
            question_totals[qid] = question_totals.get(qid, 0) + score
            question_counts[qid] = question_counts.get(qid, 0) + 1
    question_averages = []
    for q in SURVEY_QUESTIONS:
        qid = q["id"]
        avg = round(question_totals.get(qid, 0) / question_counts[qid], 2) if question_counts.get(qid) else 0
        question_averages.append(
            {
                "id": qid,
                "text": q["text"],
                "category": q["category"],
                "average": avg,
                "count": question_counts.get(qid, 0),
            }
        )

    # Score distribution
    distribution = {str(i): 0 for i in range(1, 11)}
    for r in all_responses:
        for score in r.get("responses", {}).values():
            distribution[str(round(score))] = distribution.get(str(round(score)), 0) + 1

    # Monthly trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        month_start = (now - timedelta(days=30 * (i + 1))).isoformat()
        month_end = (now - timedelta(days=30 * i)).isoformat()
        month_responses = [r for r in all_responses if month_start <= r.get("submitted_at", "") < month_end]
        month_avg = (
            round(sum(r.get("average_score", 0) for r in month_responses) / len(month_responses), 2)
            if month_responses
            else 0
        )
        label = (now - timedelta(days=30 * i)).strftime("%b")
        monthly_trend.append({"label": label, "score": month_avg, "count": len(month_responses)})

    # Response rate
    response_rate = round((total_completed / total_sent * 100), 1) if total_sent > 0 else 0

    # Recent responses (last 10)
    recent_list = []
    for r in all_responses[:10]:
        recent_list.append(
            {
                "email": r.get("email", "Anonymous"),
                "average_score": r.get("average_score", 0),
                "nps_score": r.get("nps_score", 0),
                "feedback": r.get("feedback", ""),
                "submitted_at": r.get("submitted_at", ""),
            }
        )

    return {
        "overall_score": all_avg,
        "recent_score": recent_avg,
        "trend": trend,
        "nps": nps,
        "total_responses": len(all_responses),
        "total_sent": total_sent,
        "response_rate": response_rate,
        "category_averages": category_averages,
        "question_averages": question_averages,
        "distribution": distribution,
        "monthly_trend": monthly_trend,
        "recent_responses": recent_list,
        "total_users": total_users,
    }


@router.get("/suggestions")
async def get_improvement_suggestions(request: Request):
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    all_responses = await db.csat_responses.find({}, {"_id": 0}).to_list(10000)
    if not all_responses:
        return {
            "suggestions": [
                {
                    "category": "No Data",
                    "score": 0,
                    "priority": "info",
                    "suggestion": "No survey responses yet. Send your first CSAT survey to start collecting feedback.",
                }
            ]
        }

    # Calculate category averages
    cat_totals = {}
    cat_counts = {}
    for r in all_responses:
        for cat, score in r.get("category_scores", {}).items():
            cat_totals[cat] = cat_totals.get(cat, 0) + score
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    cat_avgs = {cat: round(cat_totals[cat] / cat_counts[cat], 2) for cat in cat_totals}

    # Generate suggestions based on scores
    suggestions = []
    suggestion_map = {
        "AI Quality": {
            "low": "Invest in AI model fine-tuning and prompt engineering. Consider adding more domain-specific training data.",
            "mid": "AI quality is decent. Focus on edge cases and user-reported inaccuracies to push quality higher.",
        },
        "UI/UX": {
            "low": "Redesign key user flows. Conduct usability testing sessions and address the most common friction points.",
            "mid": "Good UI foundation. Consider micro-interactions, animations, and accessibility improvements.",
        },
        "Performance": {
            "low": "Critical: Optimize database queries, implement caching, and review CDN configuration. Users are experiencing slowness.",
            "mid": "Performance is acceptable. Focus on lazy loading, code splitting, and image optimization.",
        },
        "Features": {
            "low": "Users feel the platform lacks key features. Survey users for most-wanted features and prioritize the top 3.",
            "mid": "Feature set is growing well. Focus on polishing existing features before adding new ones.",
        },
        "Usability": {
            "low": "Navigation is confusing for users. Simplify menu structure, add better onboarding tooltips, and improve search.",
            "mid": "Usability is good. Add keyboard shortcuts, breadcrumbs, and contextual help to improve further.",
        },
        "Onboarding": {
            "low": "New users are struggling to get started. Create interactive tutorials, video walkthroughs, and a getting started checklist.",
            "mid": "Onboarding works but can be smoother. Add personalized setup flows based on user goals.",
        },
        "Value": {
            "low": "Users don't feel they're getting enough value. Review pricing tiers, add more features to lower tiers, or improve core functionality.",
            "mid": "Perceived value is reasonable. Highlight ROI metrics and success stories to reinforce value.",
        },
        "Support": {
            "low": "Support experience needs immediate attention. Reduce response times, add live chat, and improve documentation.",
            "mid": "Support is adequate. Add a comprehensive knowledge base and in-app help center.",
        },
        "Reliability": {
            "low": "Users are experiencing downtime or bugs. Implement better monitoring, alerting, and automated testing.",
            "mid": "Platform is mostly stable. Focus on error handling, graceful degradation, and status page transparency.",
        },
        "NPS": {
            "low": "Very few users would recommend the platform. Focus on the top 3 pain points from this survey.",
            "mid": "Users are somewhat likely to recommend. Create a referral program and address common concerns.",
        },
        "Experience": {
            "low": "Overall experience needs significant improvement across multiple areas. Prioritize quick wins.",
            "mid": "Overall experience is positive. Focus on delight moments and exceeding expectations.",
        },
        "Overall": {
            "low": "Overall satisfaction is below target. Create an action plan addressing the 3 lowest-scoring categories.",
            "mid": "Good overall satisfaction. Continue iterating and aim for 8+ across all categories.",
        },
    }

    for cat, avg in sorted(cat_avgs.items(), key=lambda x: x[1]):
        priority = "critical" if avg < 5 else "warning" if avg < 7 else "success"
        level = "low" if avg < 6 else "mid"
        default_suggestion = f"Score is {'below target' if avg < 7 else 'on track'}. {'Investigate root causes and create improvement plan.' if avg < 7 else 'Maintain current quality and aim higher.'}"
        suggestion = suggestion_map.get(cat, {}).get(level, default_suggestion)
        suggestions.append({"category": cat, "score": avg, "priority": priority, "suggestion": suggestion})

    return {"suggestions": suggestions}


@router.post("/send-manual")
async def trigger_manual_send(body: ManualTriggerRequest, request: Request):
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    sent_count = await _send_csat_surveys(db, target=body.target)
    return {"ok": True, "sent_count": sent_count}


async def _send_csat_surveys(db, target: str = "all") -> int:
    """Core function to send CSAT survey emails to eligible users."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        logger.warning("CSAT: Email not configured, skipping send")
        return 0

    now = datetime.now(timezone.utc)
    base_url = os.environ.get("FRONTEND_BASE_URL", "")

    # Find users eligible for survey (signed up > 45 days ago, no recent survey)
    forty_five_days_ago = (now - timedelta(days=45)).isoformat()
    query = {"created_at": {"$lte": forty_five_days_ago}} if target == "all" else {"email": target}
    users = await db.users.find(query, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(10000)

    sent = 0
    for u in users:
        email = u.get("email")
        if not email:
            continue

        # Check if user already has ANY token (used or unused) within 45 days
        recent_token = await db.csat_tokens.find_one(
            {
                "email": email,
                "created_at": {"$gte": forty_five_days_ago},
            }
        )
        if recent_token:
            continue

        token = str(uuid.uuid4())
        await db.csat_tokens.insert_one(
            {
                "token": token,
                "user_id": u.get("user_id"),
                "email": email,
                "used": False,
                "created_at": now.isoformat(),
                "period": now.strftime("%B %Y"),
            }
        )

        survey_url = f"{base_url}/survey?token={token}"
        _build_csat_email_html(u.get("name", ""), survey_url, base_url)

        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="csat_survey",
                user_name=u.get("name", "there"),
                survey_url=survey_url,
            )
            sent += 1
        except Exception as e:
            logger.error(f"CSAT email failed for {email}: {e}")

    logger.info(f"CSAT: Sent {sent} surveys")
    return sent


def _build_csat_email_html(name: str, survey_url: str, base_url: str) -> str:
    greeting = f"Hi {name}," if name else "Hi there,"
    from utils.email_templates import _get_inline_logo
    logo_uri = _get_inline_logo()
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body {{ margin:0; padding:0; background:#f0f4f8; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
.wrap {{ max-width:640px; margin:0 auto; padding:20px; }}
.card {{ background:#ffffff; border-radius:16px; padding:40px 32px; box-shadow:0 4px 24px rgba(0,0,0,0.06); }}
.logo {{ text-align:center; margin-bottom:24px; }}
.logo img {{ height:40px; }}
h1 {{ color:#0f172a; font-size:24px; font-weight:700; margin:0 0 8px; text-align:center; }}
.subtitle {{ color:#64748b; font-size:15px; text-align:center; margin:0 0 32px; line-height:1.5; }}
.divider {{ height:1px; background:linear-gradient(90deg,transparent,#e2e8f0,transparent); margin:24px 0; }}
.question {{ margin-bottom:28px; }}
.q-text {{ color:#1e293b; font-size:14px; font-weight:600; margin-bottom:10px; line-height:1.4; }}
.q-num {{ display:inline-block; width:22px; height:22px; border-radius:50%; background:#059669; color:#fff; font-size:11px; font-weight:700; text-align:center; line-height:22px; margin-right:8px; }}
.scale {{ display:flex; gap:4px; }}
.scale a {{ display:inline-block; width:42px; height:36px; border-radius:8px; background:#f1f5f9; color:#475569; font-size:13px; font-weight:600; text-align:center; line-height:36px; text-decoration:none; transition:all 0.2s; }}
.scale a:hover {{ background:#059669; color:#fff; transform:scale(1.1); }}
.labels {{ display:flex; justify-content:space-between; margin-top:4px; }}
.labels span {{ color:#94a3b8; font-size:11px; }}
.cta-wrap {{ text-align:center; margin:32px 0 16px; }}
.cta {{ display:inline-block; padding:14px 48px; background:linear-gradient(135deg,#059669,#10b981); color:#ffffff; font-size:15px; font-weight:700; text-decoration:none; border-radius:12px; letter-spacing:0.3px; }}
.footer {{ text-align:center; color:#94a3b8; font-size:12px; margin-top:24px; line-height:1.6; padding-top:24px; border-top:3px solid; border-image:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0) 1; }}
.footer a {{ color:#3B82F6; text-decoration:none; font-weight:600; }}
.footer .brand {{ font-size:18px; font-weight:900; letter-spacing:-0.5px; margin-bottom:8px; }}
.footer .brand .ai {{ color:#06D6A0; }}
@media (max-width:480px) {{
  .card {{ padding:24px 16px; }}
  .scale a {{ width:28px; height:30px; font-size:11px; line-height:30px; }}
  h1 {{ font-size:20px; }}
}}
</style>
</head>
<body>
<div class="wrap">
<div class="card">
  <div class="logo"><img src="{logo_uri}" alt="RealAICoach" style="height:40px;"></div>
  <h1>Your Feedback Matters</h1>
  <p class="subtitle">{greeting}<br>Help us improve RealAICoach by sharing your experience. This quick survey takes about 2 minutes.</p>
  <div class="divider"></div>

  <p style="color:#475569;font-size:13px;text-align:center;margin-bottom:24px;">Click any number below to start your survey (1 = Poor, 10 = Excellent)</p>

  <div class="question">
    <div class="q-text"><span class="q-num">1</span> Overall Platform Satisfaction</div>
    <div class="scale">
      {"".join(f'<a href="{survey_url}&q=overall_satisfaction&v={i}">{i}</a>' for i in range(1, 11))}
    </div>
    <div class="labels"><span>Poor</span><span>Excellent</span></div>
  </div>

  <div class="question">
    <div class="q-text"><span class="q-num">2</span> AI Coaching Quality & Accuracy</div>
    <div class="scale">
      {"".join(f'<a href="{survey_url}&q=ai_quality&v={i}">{i}</a>' for i in range(1, 11))}
    </div>
    <div class="labels"><span>Poor</span><span>Excellent</span></div>
  </div>

  <div class="question">
    <div class="q-text"><span class="q-num">3</span> Likelihood to Recommend (NPS)</div>
    <div class="scale">
      {"".join(f'<a href="{survey_url}&q=recommendation&v={i}">{i}</a>' for i in range(1, 11))}
    </div>
    <div class="labels"><span>Not likely</span><span>Very likely</span></div>
  </div>

  <div class="divider"></div>

  <div class="cta-wrap">
    <a href="{survey_url}" class="cta">Complete Full Survey</a>
  </div>
  <p style="color:#94a3b8;font-size:12px;text-align:center;">Complete all 12 questions for a comprehensive review</p>

</div>
<div class="footer">
  <p class="brand">Real<span class="ai">AI</span>Coach</p>
  <p>This survey was sent by <a href="{base_url}">RealAICoach</a><br>
  Your responses are confidential and help us improve the platform for everyone.</p>
</div>
</div>
</body>
</html>"""


# ── Fix #2: Reminder for non-responders ──


async def _send_csat_reminders(db) -> int:
    """Send a gentle reminder to users who received a survey 7+ days ago but haven't completed it."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        return 0

    now = datetime.now(timezone.utc)
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Find tokens: unused, created 7-30 days ago, no reminder sent yet
    pending = await db.csat_tokens.find(
        {
            "used": False,
            "created_at": {"$lte": seven_days_ago, "$gte": thirty_days_ago},
            "reminder_sent": {"$ne": True},
        },
        {"_id": 0},
    ).to_list(10000)

    sent = 0
    for tok in pending:
        email = tok.get("email")
        if not email:
            continue
        survey_url = f"{base_url}/survey?token={tok['token']}"
        _build_csat_reminder_html(survey_url, base_url)
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="csat_reminder",
                survey_url=survey_url,
            )
            await db.csat_tokens.update_one(
                {"token": tok["token"]},
                {"$set": {"reminder_sent": True, "reminder_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as e:
            logger.error(f"CSAT reminder failed for {email}: {e}")

    if sent > 0:
        logger.info(f"CSAT: Sent {sent} reminder(s)")
    return sent


def _build_csat_reminder_html(survey_url: str, base_url: str) -> str:
    from utils.email_templates import _get_inline_logo
    logo_uri = _get_inline_logo()
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body {{ margin:0; padding:0; background:#f0f4f8; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
.wrap {{ max-width:560px; margin:0 auto; padding:20px; }}
.card {{ background:#ffffff; border-radius:16px; padding:36px 28px; box-shadow:0 4px 24px rgba(0,0,0,0.06); text-align:center; }}
.logo img {{ height:36px; margin-bottom:20px; }}
h1 {{ color:#0f172a; font-size:20px; font-weight:700; margin:0 0 12px; }}
p {{ color:#64748b; font-size:14px; line-height:1.6; margin:0 0 24px; }}
.cta {{ display:inline-block; padding:14px 40px; background:linear-gradient(135deg,#059669,#10b981); color:#ffffff; font-size:15px; font-weight:700; text-decoration:none; border-radius:12px; }}
.footer {{ text-align:center; color:#94a3b8; font-size:11px; margin-top:20px; line-height:1.5; padding-top:20px; border-top:3px solid; border-image:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0) 1; }}
.footer a {{ color:#3B82F6; text-decoration:none; font-weight:600; }}
.footer .brand {{ font-size:18px; font-weight:900; letter-spacing:-0.5px; margin-bottom:6px; color:#0f172a; }}
.footer .brand .ai {{ color:#06D6A0; }}
</style>
</head>
<body>
<div class="wrap">
<div class="card">
  <div><img src="{logo_uri}" alt="RealAICoach" style="height:36px;"></div>
  <h1>We'd still love your feedback</h1>
  <p>We sent you a satisfaction survey recently and noticed you haven't had a chance to complete it yet. It only takes 2 minutes and helps us improve the platform for everyone.</p>
  <a href="{survey_url}" class="cta">Take the Survey</a>
  <p style="color:#94a3b8;font-size:12px;margin-top:20px;">This is a one-time reminder. We won't send another.</p>
</div>
<div class="footer">
  <p class="brand">Real<span class="ai">AI</span>Coach</p>
  <p>Sent by <a href="{base_url}">RealAICoach</a></p>
</div>
</div>
</body>
</html>"""


# ── Fix #4: Automation status endpoint ──


@router.get("/automation-status")
async def get_automation_status(request: Request):
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)

    # Last survey send run
    last_token = await db.csat_tokens.find_one({}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    last_run = last_token.get("created_at") if last_token else None

    # Last reminder run
    last_reminder_tok = await db.csat_tokens.find_one(
        {"reminder_sent": True}, {"_id": 0, "reminder_sent_at": 1}, sort=[("reminder_sent_at", -1)]
    )
    last_reminder_run = last_reminder_tok.get("reminder_sent_at") if last_reminder_tok else None

    # Pending surveys (sent but not completed, not expired)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    pending_count = await db.csat_tokens.count_documents(
        {
            "used": False,
            "created_at": {"$gte": thirty_days_ago},
        }
    )

    # Expired tokens
    expired_count = await db.csat_tokens.count_documents(
        {
            "used": False,
            "created_at": {"$lt": thirty_days_ago},
        }
    )

    # Total stats
    total_sent = await db.csat_tokens.count_documents({})
    total_completed = await db.csat_tokens.count_documents({"used": True})
    total_reminders = await db.csat_tokens.count_documents({"reminder_sent": True})

    # Next scheduled run (daily at 9:00 UTC)
    next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)

    return {
        "automation_enabled": True,
        "schedule": "Daily at 09:00 UTC (sends to eligible users every 45 days)",
        "reminder_schedule": "Daily at 09:30 UTC (7 days after initial send, max 1 reminder)",
        "next_survey_run": next_run.isoformat(),
        "last_survey_run": last_run,
        "last_reminder_run": last_reminder_run,
        "token_expiry_days": 30,
        "survey_interval_days": 45,
        "pending_surveys": pending_count,
        "expired_tokens": expired_count,
        "total_sent": total_sent,
        "total_completed": total_completed,
        "total_reminders_sent": total_reminders,
        "completion_rate": round(total_completed / total_sent * 100, 1) if total_sent > 0 else 0,
    }


# ─── AI Intelligence Suite ─────────────────────────────────────────────────────

@router.post("/ai-analysis")
async def run_ai_analysis(request: Request):
    """Run a comprehensive AI-powered analysis of all CSAT data using GPT-4o."""
    import json as _json
    from routes.db import db, EMERGENT_LLM_KEY
    from routes.auth import get_current_user
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check if we have a recent cached analysis (< 1 hour)
    cached = await db.csat_ai_analysis.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if cached:
        cache_age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["created_at"])).total_seconds()
        if cache_age < 3600:
            return cached

    # Gather all CSAT data
    now = datetime.now(timezone.utc)
    all_responses = await db.csat_responses.find({}, {"_id": 0}).sort("submitted_at", -1).to_list(10000)

    if not all_responses:
        return {
            "ok": True,
            "created_at": now.isoformat(),
            "health_score": 0,
            "predicted_csat": 0,
            "risk_level": "no_data",
            "feedback_themes": [],
            "at_risk_categories": [],
            "root_causes": [],
            "action_plan": [],
            "executive_summary": "No CSAT survey responses yet. Send your first survey to start collecting feedback and enable AI analysis.",
            "prediction_reasoning": "",
        }

    # Calculate current metrics for the AI prompt
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    recent = [r for r in all_responses if r.get("submitted_at", "") >= thirty_days_ago]

    cat_totals = {}
    cat_counts = {}
    feedbacks = []
    for r in all_responses:
        for cat, score in r.get("category_scores", {}).items():
            cat_totals[cat] = cat_totals.get(cat, 0) + score
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if r.get("feedback"):
            feedbacks.append({"feedback": r["feedback"], "score": r.get("average_score", 0), "date": r.get("submitted_at", "")[:10]})

    cat_avgs = {cat: round(cat_totals[cat] / cat_counts[cat], 2) for cat in cat_totals}
    all_avg = round(sum(r.get("average_score", 0) for r in all_responses) / len(all_responses), 2)
    recent_avg = round(sum(r.get("average_score", 0) for r in recent) / len(recent), 2) if recent else 0

    # NPS
    nps_scores = [r.get("nps_score", 0) for r in all_responses if r.get("nps_score")]
    promoters = sum(1 for s in nps_scores if s >= 9)
    detractors = sum(1 for s in nps_scores if s <= 6)
    nps = round(((promoters - detractors) / len(nps_scores)) * 100) if nps_scores else 0

    # Monthly trends
    monthly = []
    for i in range(3, -1, -1):
        ms = (now - timedelta(days=30 * (i + 1))).isoformat()
        me = (now - timedelta(days=30 * i)).isoformat()
        mr = [r for r in all_responses if ms <= r.get("submitted_at", "") < me]
        mavg = round(sum(r.get("average_score", 0) for r in mr) / len(mr), 2) if mr else 0
        monthly.append({"period": f"Month-{3-i}", "avg": mavg, "count": len(mr)})

    # Build the AI prompt
    feedback_sample = feedbacks[:25]
    prompt = f"""You are a world-class Customer Experience AI analyst. Analyze this CSAT data for a SaaS AI coaching platform and return a JSON response.

DATA:
- Total responses: {len(all_responses)}
- Overall CSAT: {all_avg}/10
- Recent 30-day CSAT: {recent_avg}/10
- NPS: {nps}
- Monthly trend: {_json.dumps(monthly)}
- Category scores: {_json.dumps(cat_avgs)}
- User feedback ({len(feedback_sample)} samples): {_json.dumps(feedback_sample)}

Return EXACTLY this JSON structure (no markdown, no backticks):
{{
  "health_score": <0-100 integer>,
  "predicted_csat": <predicted score for next month, 0.0-10.0>,
  "risk_level": <"low"|"medium"|"high"|"critical">,
  "prediction_reasoning": "<1-2 sentences explaining the prediction>",
  "executive_summary": "<3-4 sentence executive summary of overall satisfaction health>",
  "feedback_themes": [
    {{"theme": "<theme name>", "sentiment": "<positive|neutral|negative>", "frequency": "<high|medium|low>", "summary": "<1 sentence>"}}
  ],
  "at_risk_categories": [
    {{"category": "<name>", "score": <current score>, "risk": "<declining|stagnant|watch>", "reason": "<why this is at risk>"}}
  ],
  "root_causes": [
    {{"issue": "<root cause>", "impact": "<high|medium|low>", "affected_categories": ["<cat1>"], "evidence": "<data point>"}}
  ],
  "action_plan": [
    {{"priority": <1-5>, "action": "<specific action>", "category": "<target category>", "expected_impact": "<+X.X points>", "effort": "<low|medium|high>", "timeline": "<1 week|2 weeks|1 month>"}}
  ]
}}

RULES:
- Return 3-6 feedback_themes
- Return top 3 at_risk_categories (or fewer if data is limited)
- Return 3-5 root_causes
- Return 5-8 action_plan items sorted by priority
- Be specific and data-driven — reference actual scores and trends
- predicted_csat should account for current trajectory"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"csat-ai-{uuid.uuid4().hex[:8]}",
            system_message="You are a precise CSAT analytics AI. Always return valid JSON only.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = _json.loads(text.strip())
    except _json.JSONDecodeError:
        logger.error(f"AI CSAT: JSON parse failed, raw response: {text[:500]}")
        result = _fallback_analysis(cat_avgs, all_avg, recent_avg, nps, feedbacks)
    except Exception as e:
        logger.error(f"AI CSAT: LLM call failed: {e}")
        result = _fallback_analysis(cat_avgs, all_avg, recent_avg, nps, feedbacks)

    # Store result
    record = {
        "ok": True,
        "created_at": now.isoformat(),
        **result,
        "data_snapshot": {
            "total_responses": len(all_responses),
            "overall_avg": all_avg,
            "recent_avg": recent_avg,
            "nps": nps,
            "category_avgs": cat_avgs,
        },
    }
    await db.csat_ai_analysis.insert_one({**record})

    return record


@router.get("/ai-analysis/latest")
async def get_latest_ai_analysis(request: Request):
    """Get the most recent AI analysis (cached)."""
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    cached = await db.csat_ai_analysis.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if cached:
        return cached
    return {"ok": False, "message": "No AI analysis available yet. Click 'Run AI Analysis' to generate one."}


@router.get("/ai-analysis/history")
async def get_ai_analysis_history(request: Request, limit: int = 10):
    """Get history of AI analyses for trend comparison."""
    from routes.db import db
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    items = await db.csat_ai_analysis.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"analyses": items, "total": len(items)}


def _fallback_analysis(cat_avgs, all_avg, recent_avg, nps, feedbacks):
    """Rule-based fallback if AI fails."""
    at_risk = [{"category": c, "score": s, "risk": "declining" if s < 6 else "watch", "reason": f"Score below threshold ({s}/10)"} for c, s in sorted(cat_avgs.items(), key=lambda x: x[1]) if s < 7][:3]
    actions = []
    for i, (cat, score) in enumerate(sorted(cat_avgs.items(), key=lambda x: x[1])):
        if score < 7:
            actions.append({"priority": i + 1, "action": f"Investigate and improve {cat} (currently {score}/10)", "category": cat, "expected_impact": f"+{round(7 - score, 1)} points", "effort": "medium", "timeline": "2 weeks"})
    return {
        "health_score": max(0, min(100, int(all_avg * 10))),
        "predicted_csat": round(recent_avg * 0.9 + all_avg * 0.1, 1) if recent_avg else all_avg,
        "risk_level": "critical" if all_avg < 5 else "high" if all_avg < 6 else "medium" if all_avg < 7 else "low",
        "prediction_reasoning": f"Based on current CSAT of {all_avg}/10 and recent trend of {recent_avg}/10.",
        "executive_summary": f"Overall CSAT is {all_avg}/10 with NPS of {nps}. {'Urgent attention needed.' if all_avg < 6 else 'On track but improvement areas exist.' if all_avg < 8 else 'Strong satisfaction scores.'}",
        "feedback_themes": [{"theme": "General Feedback", "sentiment": "neutral", "frequency": "medium", "summary": f"{len(feedbacks)} feedback entries collected."}],
        "at_risk_categories": at_risk,
        "root_causes": [{"issue": "Low scoring categories", "impact": "high", "affected_categories": [c for c, s in cat_avgs.items() if s < 7], "evidence": "Multiple categories below 7.0 threshold"}] if any(s < 7 for s in cat_avgs.values()) else [],
        "action_plan": actions[:8],
    }


# ─── Weekly CSAT AI Report Email ───────────────────────────────────────────────

@router.get("/ai-report/config")
async def get_ai_report_config(request: Request):
    """Get weekly CSAT AI report email configuration."""
    from routes.db import db
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    config = await db.system_config.find_one({"key": "csat_ai_report"}, {"_id": 0})
    if not config:
        config = {"key": "csat_ai_report", "enabled": True, "day": "monday", "hour": 8}
    return {
        "enabled": config.get("enabled", True),
        "day": config.get("day", "monday"),
        "hour": config.get("hour", 8),
        "last_sent": config.get("last_sent"),
    }


@router.put("/ai-report/config")
async def update_ai_report_config(request: Request):
    """Update weekly CSAT AI report email settings."""
    from routes.db import db
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    enabled = body.get("enabled", True)
    day = body.get("day", "monday")
    if day not in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        raise HTTPException(status_code=400, detail="Invalid day")
    hour = max(0, min(23, int(body.get("hour", 8))))
    await db.system_config.update_one(
        {"key": "csat_ai_report"},
        {"$set": {"enabled": enabled, "day": day, "hour": hour, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "enabled": enabled, "day": day, "hour": hour}


@router.post("/ai-report/send-now")
async def send_ai_report_now(request: Request):
    """Manually trigger a CSAT AI report email."""
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await generate_and_send_csat_ai_report(force=True)
    return result


async def generate_and_send_csat_ai_report(force: bool = False):
    """Generate AI analysis and send a formatted report email to all admins."""
    import logging
    logger = logging.getLogger(__name__)
    from routes.db import db
    from utils.email_service import render_email_header_panel

    config = await db.system_config.find_one({"key": "csat_ai_report"}, {"_id": 0})
    if not config:
        config = {"enabled": True}
    if not config.get("enabled", True) and not force:
        return {"sent": False, "reason": "CSAT AI report emails disabled"}

    # Get or run the AI analysis
    cached = await db.csat_ai_analysis.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    now = datetime.now(timezone.utc)

    if not cached or (now - datetime.fromisoformat(cached["created_at"])).total_seconds() > 3600:
        # Need fresh analysis — call the analysis function directly
        try:
            import json as _json
            from routes.db import EMERGENT_LLM_KEY
            from emergentintegrations.llm.chat import LlmChat, UserMessage

            all_responses = await db.csat_responses.find({}, {"_id": 0}).sort("submitted_at", -1).to_list(10000)
            if not all_responses:
                return {"sent": False, "reason": "No CSAT data available"}

            # Quick metrics
            cat_totals, cat_counts, feedbacks = {}, {}, []
            for r in all_responses:
                for cat, score in r.get("category_scores", {}).items():
                    cat_totals[cat] = cat_totals.get(cat, 0) + score
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1
                if r.get("feedback"):
                    feedbacks.append({"feedback": r["feedback"], "score": r.get("average_score", 0)})

            cat_avgs = {cat: round(cat_totals[cat] / cat_counts[cat], 2) for cat in cat_totals}
            all_avg = round(sum(r.get("average_score", 0) for r in all_responses) / len(all_responses), 2)

            prompt = f"""Analyze this CSAT data and return JSON: Overall avg: {all_avg}/10, Categories: {_json.dumps(cat_avgs)}, Feedback samples: {_json.dumps(feedbacks[:15])}. Return: {{"health_score": <0-100>, "predicted_csat": <0-10>, "risk_level": "<low|medium|high>", "executive_summary": "<3 sentences>", "feedback_themes": [{{"theme":"","sentiment":"","summary":""}}], "at_risk_categories": [{{"category":"","score":0,"risk":"","reason":""}}], "action_plan": [{{"priority":1,"action":"","expected_impact":"","effort":"","timeline":""}}]}}"""

            chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"csat-report-{uuid.uuid4().hex[:8]}", system_message="Return valid JSON only.").with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=prompt))
            text = response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            analysis = _json.loads(text)
            analysis["created_at"] = now.isoformat()
            analysis["ok"] = True
            analysis["data_snapshot"] = {"total_responses": len(all_responses), "overall_avg": all_avg, "category_avgs": cat_avgs}
            await db.csat_ai_analysis.insert_one({**analysis})
            cached = analysis
        except Exception as e:
            logger.error(f"CSAT AI report: analysis failed: {e}")
            if cached:
                pass  # Use stale cache
            else:
                return {"sent": False, "reason": f"Analysis failed: {str(e)[:100]}"}

    a = cached  # The analysis data
    health = a.get("health_score", 0)
    health_color = "#22c55e" if health >= 70 else "#eab308" if health >= 50 else "#ef4444"
    health_label = "Excellent" if health >= 80 else "Good" if health >= 70 else "Fair" if health >= 50 else "Needs Attention"
    risk = a.get("risk_level", "medium")
    snap = a.get("data_snapshot", {})

    # Get previous report health score for comparison
    prev_analyses = await db.csat_ai_analysis.find({}, {"_id": 0, "health_score": 1, "created_at": 1}).sort("created_at", -1).limit(2).to_list(2)
    prev_health = prev_analyses[1]["health_score"] if len(prev_analyses) > 1 else None
    delta_html = ""
    if prev_health is not None:
        delta = health - prev_health
        delta_color = "#22c55e" if delta > 0 else "#ef4444" if delta < 0 else "#8B9DC3"
        delta_arrow = "+" if delta > 0 else ""
        delta_html = f'<div style="color:{delta_color};font-size:12px;font-weight:700;margin-top:2px;">{delta_arrow}{delta} vs last</div>'

    header = render_email_header_panel(
        title="Weekly CSAT AI Report",
        subtitle=f"Health: {health}/100 ({health_label}) | {snap.get('total_responses', 0)} responses analyzed",
        variant="report",
        accent=health_color,
        meta_label="AI Model",
        meta_value="GPT-4o",
    )

    # Themes HTML
    themes_html = ""
    for t in (a.get("feedback_themes") or [])[:5]:
        sc = "#22c55e" if t.get("sentiment") == "positive" else "#ef4444" if t.get("sentiment") == "negative" else "#eab308"
        themes_html += f'<div style="padding:8px 0;border-bottom:1px solid #1E2D4A;"><span style="display:inline-block;width:8px;height:8px;border-radius:4px;background:{sc};vertical-align:middle;margin-right:8px;"></span><strong style="color:#E8ECF4;font-size:13px;">{t.get("theme","")}</strong> <span style="color:{sc};font-size:11px;margin-left:6px;">{t.get("sentiment","")}</span><br/><span style="color:#8B9DC3;font-size:11px;">{t.get("summary","")}</span></div>'

    # At-risk HTML
    risk_html = ""
    for r in (a.get("at_risk_categories") or [])[:3]:
        rc = "#ef4444" if r.get("risk") == "declining" else "#eab308"
        risk_html += f'<div style="padding:8px 0;border-bottom:1px solid #1E2D4A;"><strong style="color:#E8ECF4;font-size:13px;text-transform:capitalize;">{r.get("category","")}</strong> <span style="color:{rc};font-size:12px;font-weight:700;">{r.get("score",0)}/10</span> <span style="background:{rc}20;color:{rc};font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700;margin-left:4px;">{r.get("risk","")}</span><br/><span style="color:#8B9DC3;font-size:11px;">{r.get("reason","")}</span></div>'

    # Action plan HTML (top 3)
    actions_html = ""
    for i, ap in enumerate((a.get("action_plan") or [])[:3]):
        pc = "#ef4444" if ap.get("priority", 5) <= 2 else "#f97316" if ap.get("priority", 5) <= 3 else "#3b82f6"
        actions_html += f"""<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #1E2D4A;">
          <div style="width:28px;height:28px;border-radius:14px;background:{pc}20;text-align:center;line-height:28px;color:{pc};font-weight:800;font-size:14px;flex-shrink:0;">{ap.get("priority",i+1)}</div>
          <div><strong style="color:#E8ECF4;font-size:12px;">{ap.get("action","")}</strong><br/><span style="color:#22c55e;font-size:11px;font-weight:700;">{ap.get("expected_impact","")}</span> <span style="color:#8B9DC3;font-size:10px;margin-left:8px;">{ap.get("effort","medium")} effort | {ap.get("timeline","")}</span></div>
        </div>"""

    dashboard_url = f"{(FRONTEND_BASE_URL or '').rstrip('/')}/executive-dashboard"

    f"""{header}
<div style="background-color:#0F172A;padding:24px 28px;border-radius:0 0 20px 20px;">

  <!-- Health Score + Prediction -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
    <tr>
      <td width="33%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:16px;padding:20px;text-align:center;border:2px solid {health_color};">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Sentiment Health</div>
          <div style="color:{health_color};font-size:44px;font-weight:900;margin:4px 0;">{health}</div>
          <div style="color:{health_color};font-size:12px;font-weight:700;">{health_label}</div>
          {delta_html}
        </div>
      </td>
      <td width="33%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:16px;padding:20px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Predicted CSAT</div>
          <div style="color:#3b82f6;font-size:44px;font-weight:900;margin:4px 0;">{a.get('predicted_csat', 0)}</div>
          <div style="color:#8B9DC3;font-size:11px;">Next month forecast</div>
        </div>
      </td>
      <td width="33%" style="padding:6px;">
        <div style="background-color:#1E293B;border-radius:16px;padding:20px;text-align:center;border:1px solid #334155;">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Risk Level</div>
          <div style="color:{'#22c55e' if risk == 'low' else '#eab308' if risk == 'medium' else '#ef4444'};font-size:32px;font-weight:900;margin:8px 0;text-transform:uppercase;">{risk}</div>
          <div style="color:#8B9DC3;font-size:11px;">{snap.get('total_responses', 0)} responses</div>
        </div>
      </td>
    </tr>
  </table>

  <!-- Executive Summary -->
  <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #334155;margin-bottom:16px;">
    <div style="color:#8B5CF6;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">AI Executive Summary</div>
    <div style="color:#E8ECF4;font-size:13px;line-height:20px;">{a.get('executive_summary', '')}</div>
  </div>

  <!-- Two columns: Themes + At-Risk -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
    <tr>
      <td width="50%" style="padding:0 6px 0 0;vertical-align:top;">
        <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #334155;">
          <div style="color:#8B5CF6;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Feedback Themes</div>
          {themes_html or '<div style="color:#8B9DC3;font-size:12px;">No themes identified</div>'}
        </div>
      </td>
      <td width="50%" style="padding:0 0 0 6px;vertical-align:top;">
        <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #7F1D1D40;">
          <div style="color:#ef4444;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">At-Risk Categories</div>
          {risk_html or '<div style="color:#22c55e;font-size:12px;">All categories healthy</div>'}
        </div>
      </td>
    </tr>
  </table>

  <!-- Top Actions -->
  <div style="background-color:#1E293B;border-radius:12px;padding:16px;border:1px solid #3b82f620;margin-bottom:16px;">
    <div style="color:#3b82f6;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Top AI-Recommended Actions</div>
    {actions_html or '<div style="color:#8B9DC3;font-size:12px;">No actions recommended</div>'}
  </div>

  <!-- CTA -->
  <div style="text-align:center;margin-top:24px;">
    <a href="{dashboard_url}" style="display:inline-block;background-color:#8B5CF6;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;padding:12px 28px;border-radius:10px;">View Full AI Dashboard</a>
  </div>
  <div style="color:#5B6F92;font-size:11px;text-align:center;margin-top:20px;">
    Powered by GPT-4o | RealAICoach CSAT Intelligence<br/>
    <a href="{dashboard_url}" style="color:#3B82F6;text-decoration:none;">Manage report settings</a>
  </div>
</div>
<!-- BRANDED_FOOTER_V2 -->"""

    # Send to all admins
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    if not admins:
        return {"sent": False, "reason": "No admin users found"}

    sent_to = []
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin["email"],
                template_key="csat_ai_report_v7",
                recipient_name=admin.get("name", ""),
                health=health,
                health_label=health_label,
                total_responses=snap.get("total_responses", 0),
                avg_score=str(round(snap.get("avg_score", 0), 1)),
                nps=str(snap.get("nps", "N/A")),
                top_themes=", ".join(t.get("theme", "") for t in (snap.get("top_themes") or [])[:3]),
                risk_categories=", ".join(r.get("category", "") for r in (snap.get("at_risk_categories") or [])[:3]) or "None",
                top_actions="; ".join(a.get("action", "") for a in (snap.get("top_actions") or [])[:2]),
            )
            sent_to.append(admin["email"])
        except Exception as e:
            logger.error(f"Failed to send CSAT AI report to {admin['email']}: {e}")

    await db.system_config.update_one(
        {"key": "csat_ai_report"},
        {"$set": {"last_sent": now.isoformat()}},
        upsert=True,
    )

    logger.info(f"CSAT AI report sent to {len(sent_to)} admins")
    return {"sent": True, "recipients": sent_to, "health_score": health, "predicted_csat": a.get("predicted_csat"), "risk_level": risk}
