"""Feature 26 legacy read services (phase-safe decomposition).

These functions hold read-path business logic extracted from `routes/jobs.py`
to keep legacy contracts stable while reducing route-module size.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .db import db


async def search_jobs_read(
    q: str = "",
    location: str = "",
    country: str = "",
    job_type: str = "",
    remote: str = "",
    industry: str = "",
    salary_min: float = 0,
    visa: str = "",
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"status": "active"}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"company_name": {"$regex": q, "$options": "i"}},
        ]
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if country:
        query["country"] = {"$regex": country, "$options": "i"}
    if job_type:
        query["job_type"] = job_type
    if remote.lower() == "true":
        query["remote"] = True
    if industry:
        query["industry"] = {"$regex": industry, "$options": "i"}
    if salary_min > 0:
        query["salary_min"] = {"$gte": salary_min}
    if visa.lower() == "true":
        query["visa_sponsorship"] = True

    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 20), 100))
    skip = (safe_page - 1) * safe_limit
    total = await db.jobs.count_documents(query)
    jobs = (
        await db.jobs.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(safe_limit)
    )
    pages = (total + safe_limit - 1) // safe_limit if total > 0 else 0
    return {"jobs": jobs, "total": total, "page": safe_page, "pages": pages}


async def get_job_recommendations_read(user_id: str) -> Dict[str, Any]:
    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0})
    query: Dict[str, Any] = {"status": "active"}
    if profile:
        skills = profile.get("skills", [])
        if skills:
            query["skills"] = {"$in": skills}
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"recommendations": jobs, "jobs": jobs, "total": len(jobs)}


async def get_my_applications_read(user_id: str, status: str = "all") -> Dict[str, Any]:
    query: Dict[str, Any] = {"user_id": user_id}
    if status != "all":
        query["status"] = status
    apps = await db.job_applications.find(query, {"_id": 0}).sort("applied_at", -1).to_list(100)
    return {"applications": apps, "total": len(apps)}


async def get_saved_jobs_read(user_id: str) -> Dict[str, Any]:
    saved = await db.saved_jobs.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    job_ids = [s.get("job_id") for s in saved if s.get("job_id")]
    jobs = await db.jobs.find({"job_id": {"$in": job_ids}}, {"_id": 0}).to_list(100) if job_ids else []
    return {"saved_jobs": jobs, "total": len(jobs)}


async def get_employee_profile_read(user_id: str) -> Dict[str, Any]:
    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return {"profile": profile or {}}


async def get_resume_score_read(user_id: str) -> Dict[str, Any]:
    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0})
    resume = await db.resumes.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "score": profile.get("resume_score", 0) if profile else 0,
        "resume": resume,
        "profile": profile or {},
    }


async def employee_analytics_read(user_id: str) -> Dict[str, Any]:
    apps = await db.job_applications.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    saved = await db.saved_jobs.count_documents({"user_id": user_id})
    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0})

    status_counts: Dict[str, int] = {}
    for app in apps:
        status = app.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "total_applications": len(apps),
        "saved_jobs": saved,
        "status_breakdown": status_counts,
        "resume_score": profile.get("resume_score", 0) if profile else 0,
    }


async def get_jobs_portal_summary_read(user_id: str) -> Dict[str, Any]:
    total_jobs = await db.jobs.count_documents({"status": "active"})
    my_apps = await db.job_applications.count_documents({"user_id": user_id})
    saved = await db.saved_jobs.count_documents({"user_id": user_id})
    interview_apps = await db.job_applications.count_documents({"user_id": user_id, "status": "interview"})
    offer_apps = await db.job_applications.count_documents({"user_id": user_id, "status": "offer"})
    now_iso = datetime.now(timezone.utc).isoformat()

    candidate_summary = {
        "applications": my_apps,
        "saved_jobs": saved,
        "interviews": interview_apps,
        "offers": offer_apps,
    }
    employer_summary = {
        "open_roles": total_jobs,
        "pipeline_candidates": 0,
        "offers_sent": 0,
    }

    return {
        "open_roles": total_jobs,
        "candidate": candidate_summary,
        "employer": employer_summary,
        "last_sync": now_iso,
        "last_sync_at": now_iso,
        "candidate_applications": my_apps,
        "total_active_jobs": total_jobs,
        "my_applications": my_apps,
        "saved_jobs": saved,
        "interview_applications": interview_apps,
        "offer_applications": offer_apps,
    }


async def get_smart_alerts_read(user_id: str, unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
    query = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    safe_limit = max(1, min(int(limit or 50), 200))
    alerts = await db.smart_alerts.find(query, {"_id": 0}).sort("created_at", -1).to_list(safe_limit)
    unread = await db.smart_alerts.count_documents({"user_id": user_id, "read": False})
    return {"alerts": alerts, "total": len(alerts), "unread_count": unread}


async def get_alert_preferences_read(user_id: str) -> Dict[str, Any]:
    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0, "alert_preferences": 1})
    defaults = {"enabled": True, "min_match_score": 20, "alert_types": ["job_match", "application_update"]}
    return {"preferences": profile.get("alert_preferences", defaults) if profile else defaults}


async def build_alert_preferences_update(user_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    prefs = {
        "enabled": body.get("enabled", True),
        "min_match_score": max(0, min(100, body.get("min_match_score", 20))),
        "alert_types": body.get("alert_types", ["job_match", "application_update"]),
    }
    await db.employee_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"alert_preferences": prefs, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return prefs
