"""Daily Job Alerts — backend routes for preferences, unsubscribe, and send.

Provides:
  - GET  /api/jobs/alerts/preferences   — get alert preferences for current user
  - POST /api/jobs/alerts/preferences   — update alert preferences
  - POST /api/jobs/alerts/unsubscribe   — one-click unsubscribe (token-based, no auth)
  - POST /api/jobs/alerts/send-daily    — admin: manually trigger daily job alert batch
"""

import logging
import hashlib
import hmac
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs/alerts", tags=["job-alerts"])

# DB will be set by server.py
db = None


def set_db(database):
    global db
    db = database


# ── Helpers ──

def _unsub_token(email: str) -> str:
    """Generate expiring unsubscribe token (email + expiry + HMAC)."""
    secret = str(os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET missing/weak: cannot issue unsubscribe token")
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    exp_ts = int(expires_at.timestamp())
    payload = f"{email.strip().lower()}:{exp_ts}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{exp_ts}.{sig}"


def _verify_unsub_token(email: str, token: str) -> bool:
    try:
        exp_raw, sig = str(token or "").split(".", 1)
        exp_ts = int(exp_raw)
    except Exception:
        return False

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp_ts < now_ts:
        return False

    secret = str(os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        return False

    payload = f"{email.strip().lower()}:{exp_ts}"
    expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(expected_sig, sig)


async def _require_auth(request: Request):
    """Lightweight auth check — returns user dict or raises."""
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


# ── Endpoints ──

@router.get("/unsubscribe")
async def unsubscribe_job_alerts(email: str = Query(...), token: str = Query(...)):
    """One-click unsubscribe — no auth needed, uses token verification."""
    if not _verify_unsub_token(email, token):
        raise HTTPException(400, "Invalid unsubscribe link")

    now = datetime.now(timezone.utc).isoformat()
    await db.job_alert_preferences.update_one(
        {"email": email},
        {"$set": {"subscribed": False, "unsubscribed_at": now, "updated_at": now},
         "$setOnInsert": {"email": email, "created_at": now}},
        upsert=True,
    )
    logger.info(f"[JOB-ALERTS] User unsubscribed: {email}")
    return {"unsubscribed": True, "email": email}


@router.post("/send-daily")
async def send_daily_job_alerts(request: Request):
    """Admin: Manually trigger daily job alert emails. Sends to all subscribed users."""
    user = await _require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin only")

    result = await _execute_daily_job_alerts()
    return result


# ── Core send logic ──

async def _execute_daily_job_alerts():
    """Send daily job alert emails with AI-powered matching.

    - Users with profiles: AI-ranked jobs with match scores
    - Users without profiles: all recent jobs by recency
    - Unsubscribed users: skipped
    """
    frontend_base = os.environ.get("FRONTEND_BASE_URL", "")

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()

    new_jobs = await db.job_listings.find(
        {"status": "active", "posted_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("posted_at", -1).to_list(20)

    if not new_jobs:
        logger.info("[JOB-ALERTS] No new jobs in last 24h")
        return {"sent": 0, "skipped": 0, "jobs_count": 0, "message": "No new jobs to alert about"}

    job_count = len(new_jobs)

    all_users = await db.users.find(
        {"email": {"$exists": True, "$ne": ""}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1},
    ).to_list(10000)

    unsub_docs = await db.job_alert_preferences.find(
        {"subscribed": False}, {"_id": 0, "email": 1, "user_id": 1},
    ).to_list(10000)
    unsub_emails = {d.get("email", "").lower() for d in unsub_docs}
    unsub_user_ids = {d.get("user_id", "") for d in unsub_docs}

    # Pre-fetch profiles for AI matching
    all_profiles = {}
    async for p in db.employee_profiles.find({}, {"_id": 0}):
        uid = p.get("user_id")
        if uid and p.get("skills"):
            all_profiles[uid] = p

    sent = 0
    skipped = 0
    ai_matched = 0

    for u in all_users:
        email = u.get("email", "").strip()
        user_id = u.get("user_id", "")
        name = u.get("full_name") or u.get("name") or "there"

        if not email or email.lower() in unsub_emails or user_id in unsub_user_ids:
            skipped += 1
            continue

        # AI-rank if user has a profile
        user_jobs = new_jobs
        profile = all_profiles.get(user_id)
        if profile:
            user_jobs = await _ai_rank_jobs(new_jobs, profile)
            ai_matched += 1

        token = _unsub_token(email)
        unsub_url = f"{frontend_base}/api/jobs/alerts/unsubscribe?email={email}&token={token}"

        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="daily_job_alerts",
                recipient_name=name,
                user_name=name,
                jobs=user_jobs,
                is_authenticated=True,
                job_count=job_count,
                unsub_url=unsub_url,
            )
            sent += 1
        except Exception as e:
            logger.error(f"[JOB-ALERTS] Failed to send to {email}: {e}")
            skipped += 1

    logger.info(f"[JOB-ALERTS] Daily batch: sent={sent}, skipped={skipped}, jobs={job_count}, ai={ai_matched}")
    return {
        "sent": sent, "skipped": skipped, "jobs_count": job_count,
        "ai_matched_users": ai_matched,
        "message": f"Sent {sent} alerts ({job_count} jobs, {ai_matched} AI-matched)",
    }


async def _ai_rank_jobs(jobs: list, profile: dict) -> list:
    """AI-powered job ranking with deterministic fallback."""
    try:
        return await _ai_rank_jobs_llm(jobs, profile)
    except Exception as e:
        logger.warning(f"[JOB-ALERTS] LLM ranking failed, using deterministic: {e}")
        return _deterministic_rank(jobs, profile)


async def _ai_rank_jobs_llm(jobs: list, profile: dict) -> list:
    """LLM-powered job ranking."""
    import json as json_mod
    from utils.llm_helper import generate_verified_json

    jobs_summary = json_mod.dumps([{
        "job_id": j.get("job_id"), "title": j.get("title"),
        "company": j.get("company_name"), "skills": j.get("requirements", j.get("skills", [])),
        "location": j.get("location"), "location_type": j.get("location_type"),
        "salary_min": j.get("salary_min"), "salary_max": j.get("salary_max"),
        "industry": j.get("industry"), "experience_level": j.get("experience_level"),
    } for j in jobs[:12]])

    profile_summary = json_mod.dumps({
        "skills": profile.get("skills", []),
        "experience_years": profile.get("experience_years"),
        "preferred_location": profile.get("preferred_location"),
        "preferred_job_type": profile.get("preferred_job_type"),
        "preferred_industry": profile.get("preferred_industry"),
        "remote_only": profile.get("remote_only", False),
        "preferred_salary_min": profile.get("preferred_salary_min"),
    })

    result = await generate_verified_json(
        prompt=f"Candidate:\n{profile_summary}\n\nJobs:\n{jobs_summary}\n\nRank ALL jobs by relevance.",
        system_message=(
            "You are a job matching AI. Return a JSON array ranking ALL jobs by match score (0-100) "
            'with a brief reason (max 8 words). Format: [{"job_id":"...","score":85,"reason":"Strong Python & ML match"}].'
        ),
        session_id=f"job_alert_{profile.get('user_id', 'anon')}",
    )

    if not result or not isinstance(result, list):
        return _deterministic_rank(jobs, profile)

    score_map = {m.get("job_id"): m for m in result if isinstance(m, dict)}
    scored = []
    for j in jobs:
        j_copy = {**j}
        info = score_map.get(j.get("job_id"))
        if info:
            j_copy["match_score"] = info.get("score", 50)
            j_copy["match_reason"] = info.get("reason", "")
        scored.append(j_copy)

    scored.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return scored


def _deterministic_rank(jobs: list, profile: dict) -> list:
    """Fast deterministic scoring when LLM is unavailable."""
    user_skills = {s.lower() for s in profile.get("skills", [])}
    pref_industry = (profile.get("preferred_industry") or "").lower()
    pref_location = (profile.get("preferred_location") or "").lower()
    remote_only = profile.get("remote_only", False)
    pref_salary = profile.get("preferred_salary_min", 0)

    scored = []
    for j in jobs:
        score = 50
        j_copy = {**j}

        # Skills overlap (+30 max)
        job_skills_raw = j.get("requirements", j.get("skills", []))
        job_text = " ".join(str(s).lower() for s in job_skills_raw) if isinstance(job_skills_raw, list) else str(job_skills_raw).lower()
        title_lower = j.get("title", "").lower()
        matches = sum(1 for s in user_skills if s in job_text or s in title_lower)
        score += min(30, matches * 10)

        if pref_industry and pref_industry in j.get("industry", "").lower():
            score += 15
        if pref_location and pref_location in j.get("location", "").lower():
            score += 10
        if remote_only and j.get("location_type") == "remote":
            score += 10
        elif remote_only and j.get("location_type") == "onsite":
            score -= 10
        if pref_salary and j.get("salary_min") and j.get("salary_min") >= pref_salary:
            score += 5
        if j.get("easy_apply"):
            score += 3

        j_copy["match_score"] = min(100, max(0, score))
        reasons = []
        if matches > 0:
            reasons.append(f"{matches} skill{'s' if matches > 1 else ''} match")
        if pref_industry and pref_industry in j.get("industry", "").lower():
            reasons.append("industry fit")
        j_copy["match_reason"] = ", ".join(reasons[:2]).capitalize() if reasons else "New listing"
        scored.append(j_copy)

    scored.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return scored
