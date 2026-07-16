"""
Careers ATS — Tier 2 enhancements.

Features shipped in this module:
  6. Structured Interview Scorecards   — CRUD + consensus calc
  7. AI Scorecard from transcript       — Claude fills rubric from pasted text
  8. Candidate Portal (magic link)      — public read-only candidate view
  9. Stalled-Candidate SLA              — admin endpoint + stats
 10. Duplicate Candidate Detection      — fuzzy-match cluster + merge
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

APPS_COL = "careers_applications"
SCORECARDS_COL = "interview_scorecards"

FINAL_STATUSES = {"hired", "rejected", "withdrawn", "on_hold"}


# ─────────────────────────────────────────────────────────────────────────────
# Rubric catalog — snapshot stored on each scorecard for audit integrity.
# ─────────────────────────────────────────────────────────────────────────────

ROLE_RUBRICS: dict[str, dict[str, Any]] = {
    "engineering": {
        "role_key": "engineering",
        "display_name": "Engineering",
        "criteria": [
            {"id": "coding", "label": "Coding & Implementation", "weight": 1.2},
            {"id": "system_design", "label": "System Design", "weight": 1.2},
            {"id": "problem_solving", "label": "Problem-Solving", "weight": 1.0},
            {"id": "communication", "label": "Communication", "weight": 0.8},
            {"id": "ownership", "label": "Ownership & Drive", "weight": 0.8},
        ],
    },
    "sales": {
        "role_key": "sales",
        "display_name": "Sales",
        "criteria": [
            {"id": "discovery", "label": "Discovery & Qualification", "weight": 1.1},
            {"id": "objection_handling", "label": "Objection Handling", "weight": 1.0},
            {"id": "closing", "label": "Closing Ability", "weight": 1.2},
            {"id": "domain", "label": "Domain Knowledge", "weight": 0.9},
            {"id": "coachability", "label": "Coachability", "weight": 0.8},
        ],
    },
    "marketing": {
        "role_key": "marketing",
        "display_name": "Marketing",
        "criteria": [
            {"id": "strategy", "label": "Strategic Thinking", "weight": 1.2},
            {"id": "execution", "label": "Execution & Delivery", "weight": 1.0},
            {"id": "analytics", "label": "Analytics & Measurement", "weight": 1.0},
            {"id": "storytelling", "label": "Storytelling", "weight": 0.9},
            {"id": "collaboration", "label": "Cross-Functional Collaboration", "weight": 0.9},
        ],
    },
    "design": {
        "role_key": "design",
        "display_name": "Design",
        "criteria": [
            {"id": "craft", "label": "Visual & Interaction Craft", "weight": 1.2},
            {"id": "systems_thinking", "label": "Systems Thinking", "weight": 1.0},
            {"id": "user_empathy", "label": "User Empathy", "weight": 1.1},
            {"id": "communication", "label": "Design Communication", "weight": 0.9},
            {"id": "iteration", "label": "Iteration Speed", "weight": 0.8},
        ],
    },
    "operations": {
        "role_key": "operations",
        "display_name": "Operations",
        "criteria": [
            {"id": "process", "label": "Process & Rigor", "weight": 1.1},
            {"id": "ownership", "label": "Ownership", "weight": 1.0},
            {"id": "communication", "label": "Communication", "weight": 0.9},
            {"id": "problem_solving", "label": "Problem-Solving", "weight": 1.0},
            {"id": "stakeholder", "label": "Stakeholder Management", "weight": 1.0},
        ],
    },
    "generic": {
        "role_key": "generic",
        "display_name": "General",
        "criteria": [
            {"id": "domain", "label": "Domain Skill", "weight": 1.0},
            {"id": "communication", "label": "Communication", "weight": 1.0},
            {"id": "problem_solving", "label": "Problem-Solving", "weight": 1.0},
            {"id": "ownership", "label": "Ownership", "weight": 1.0},
            {"id": "culture", "label": "Culture Add", "weight": 1.0},
        ],
    },
}

REJECT_REASONS = [
    {"id": "skill_mismatch", "label": "Skill mismatch"},
    {"id": "experience_gap", "label": "Experience gap"},
    {"id": "comp_mismatch", "label": "Compensation mismatch"},
    {"id": "culture", "label": "Culture fit concern"},
    {"id": "communication", "label": "Communication concern"},
    {"id": "role_closed", "label": "Role no longer open"},
    {"id": "better_fit", "label": "Better fit identified"},
    {"id": "other", "label": "Other"},
]


def _resolve_role_rubric(role_title: str | None) -> dict[str, Any]:
    rt = (role_title or "").lower()
    for key in ("engineering", "engineer", "developer", "software", "backend", "frontend", "devops", "data"):
        if key in rt:
            return ROLE_RUBRICS["engineering"]
    for key in ("sales", "account executive", "bdr", "sdr", "revenue"):
        if key in rt:
            return ROLE_RUBRICS["sales"]
    for key in ("marketing", "growth", "brand", "content", "seo"):
        if key in rt:
            return ROLE_RUBRICS["marketing"]
    for key in ("design", "ux", "ui", "product designer"):
        if key in rt:
            return ROLE_RUBRICS["design"]
    for key in ("operations", "ops", "program", "project manager", "hr", "people"):
        if key in rt:
            return ROLE_RUBRICS["operations"]
    return ROLE_RUBRICS["generic"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Scorecards — CRUD
# ─────────────────────────────────────────────────────────────────────────────


class ScorecardBody(BaseModel):
    interviewer_name: str = Field(..., min_length=1, max_length=120)
    interviewer_email: str = ""
    stage: str = Field("interview", max_length=40)
    ratings: dict[str, int] = Field(default_factory=dict)
    overall: int = Field(3, ge=1, le=5)
    hire_recommendation: str = Field("lean_hire", pattern="^(strong_hire|lean_hire|no_hire|strong_no_hire)$")
    reject_reason: Optional[str] = None
    comments: str = Field("", max_length=4000)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


@router.get("/careers/scorecard-rubrics")
async def admin_list_rubrics(request: Request):
    await require_admin(request)
    return {
        "rubrics": list(ROLE_RUBRICS.values()),
        "reject_reasons": REJECT_REASONS,
    }


@router.get("/careers/applications/{app_id}/scorecards")
async def admin_list_scorecards(request: Request, app_id: str):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[SCORECARDS_COL].find({"application_id": app_id}, {"_id": 0}).sort("created_at", -1):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.post("/careers/applications/{app_id}/scorecards")
async def admin_create_scorecard(request: Request, app_id: str, body: ScorecardBody):
    admin = await require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0, "role_title": 1})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    rubric = _resolve_role_rubric(app_doc.get("role_title"))
    valid_ids = {c["id"] for c in rubric["criteria"]}
    ratings = {k: max(1, min(5, int(v))) for k, v in (body.ratings or {}).items() if k in valid_ids}
    # compute weighted overall if ratings provided
    computed_overall = body.overall
    if ratings:
        total_w = sum(c["weight"] for c in rubric["criteria"] if c["id"] in ratings)
        if total_w > 0:
            weighted = sum(ratings[c["id"]] * c["weight"] for c in rubric["criteria"] if c["id"] in ratings)
            computed_overall = round(weighted / total_w, 2)

    doc = {
        "scorecard_id": f"sc_{uuid.uuid4().hex[:12]}",
        "application_id": app_id,
        "interviewer_name": body.interviewer_name,
        "interviewer_email": body.interviewer_email or getattr(admin, "email", ""),
        "interviewer_user_id": getattr(admin, "user_id", None),
        "stage": body.stage,
        "rubric_snapshot": rubric,
        "ratings": ratings,
        "overall": computed_overall,
        "hire_recommendation": body.hire_recommendation,
        "reject_reason": body.reject_reason,
        "comments": body.comments,
        "strengths": body.strengths[:10],
        "concerns": body.concerns[:10],
        "source": "manual",
        "created_at": _now_iso(),
    }
    await db[SCORECARDS_COL].insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "scorecard": doc}


@router.delete("/careers/applications/{app_id}/scorecards/{scorecard_id}")
async def admin_delete_scorecard(request: Request, app_id: str, scorecard_id: str):
    await require_admin(request)
    res = await db[SCORECARDS_COL].delete_one({"scorecard_id": scorecard_id, "application_id": app_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    return {"ok": True, "deleted": scorecard_id}


@router.get("/careers/applications/{app_id}/scorecards/consensus")
async def admin_scorecard_consensus(request: Request, app_id: str):
    """Aggregate all scorecards for a candidate: mean overall, vote distribution,
    top strengths/concerns frequency, consensus recommendation."""
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[SCORECARDS_COL].find({"application_id": app_id}, {"_id": 0}):
        items.append(d)
    if not items:
        return {"count": 0, "consensus": None}
    overalls = [float(it.get("overall") or 0) for it in items if it.get("overall") is not None]
    mean_overall = round(sum(overalls) / len(overalls), 2) if overalls else 0
    vote_counts: dict[str, int] = {}
    for it in items:
        v = it.get("hire_recommendation") or "lean_hire"
        vote_counts[v] = vote_counts.get(v, 0) + 1
    top_vote = max(vote_counts.items(), key=lambda x: x[1])[0] if vote_counts else "lean_hire"
    strengths_freq: dict[str, int] = {}
    concerns_freq: dict[str, int] = {}
    for it in items:
        for s in (it.get("strengths") or []):
            k = s.strip().lower()
            if k:
                strengths_freq[k] = strengths_freq.get(k, 0) + 1
        for c in (it.get("concerns") or []):
            k = c.strip().lower()
            if k:
                concerns_freq[k] = concerns_freq.get(k, 0) + 1
    return {
        "count": len(items),
        "consensus": {
            "mean_overall": mean_overall,
            "vote_counts": vote_counts,
            "top_recommendation": top_vote,
            "top_strengths": sorted(strengths_freq.items(), key=lambda x: -x[1])[:5],
            "top_concerns": sorted(concerns_freq.items(), key=lambda x: -x[1])[:5],
        },
        "generated_at": _now_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. AI Scorecard from transcript
# ─────────────────────────────────────────────────────────────────────────────


class AiScorecardBody(BaseModel):
    transcript: str = Field(..., min_length=50, max_length=60000, description="Plain-text interview transcript or notes.")
    interviewer_name: str = Field("AI Scorecard", max_length=120)
    stage: str = "interview"
    persist: bool = False


@router.post("/careers/applications/{app_id}/scorecards/ai-score")
async def admin_ai_scorecard(request: Request, app_id: str, body: AiScorecardBody):
    """Run the transcript through Claude and return a suggested, filled scorecard.

    If `persist=true`, the scorecard is also inserted into the collection with
    source='ai'. Otherwise the response is preview-only so the admin can review
    + tweak + click "Save" manually.
    """
    await require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0, "role_title": 1, "name": 1, "email": 1})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    rubric = _resolve_role_rubric(app_doc.get("role_title"))

    criterion_ids = [c["id"] for c in rubric["criteria"]]
    criterion_labels = "; ".join([f"{c['id']}={c['label']}" for c in rubric["criteria"]])
    role_title = app_doc.get("role_title") or "Open role"
    candidate_name = app_doc.get("name") or "the candidate"

    system = (
        "You are a senior hiring manager producing a structured interview scorecard. "
        "Your output MUST be strict JSON matching this schema: "
        '{"ratings": {<criterion_id>: <int 1-5>}, "overall": <int 1-5>, '
        '"hire_recommendation": "strong_hire"|"lean_hire"|"no_hire"|"strong_no_hire", '
        '"strengths": [<short phrase>], "concerns": [<short phrase>], "comments": "<2-4 sentence summary>"} '
        "All criterion_ids listed in the user message MUST appear in ratings. No other fields allowed."
    )
    prompt = (
        f"ROLE: {role_title}\n"
        f"CANDIDATE: {candidate_name}\n"
        f"RUBRIC CRITERIA (id=label, score 1-5): {criterion_labels}\n"
        f"TRANSCRIPT / INTERVIEW NOTES:\n{body.transcript[:60000]}\n\n"
        f"Produce the JSON scorecard. Be critical and specific; base scores on evidence in the transcript."
    )

    try:
        from utils.llm_helper import generate_verified_json
        result = await generate_verified_json(
            prompt=prompt,
            system_message=system,
            session_id=f"ai-scorecard-{app_id[-8:]}",
            model="gpt-4o",
            feature="careers_ai_scorecard",
        )
    except Exception as e:
        logger.warning(f"[careers/ai-scorecard] LLM failed for {app_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI scorecard service unavailable: {str(e)[:100]}")

    # Normalize result shape
    ratings_raw = (result or {}).get("ratings") or {}
    ratings = {cid: max(1, min(5, int(ratings_raw.get(cid, 3) or 3))) for cid in criterion_ids}
    # Weighted overall
    total_w = sum(c["weight"] for c in rubric["criteria"])
    computed_overall = round(sum(ratings[c["id"]] * c["weight"] for c in rubric["criteria"]) / total_w, 2) if total_w else 3
    rec = (result or {}).get("hire_recommendation") or "lean_hire"
    if rec not in ("strong_hire", "lean_hire", "no_hire", "strong_no_hire"):
        rec = "lean_hire"

    scorecard = {
        "scorecard_id": f"sc_{uuid.uuid4().hex[:12]}",
        "application_id": app_id,
        "interviewer_name": body.interviewer_name,
        "interviewer_email": "ai@realaicoach.app",
        "stage": body.stage,
        "rubric_snapshot": rubric,
        "ratings": ratings,
        "overall": computed_overall,
        "hire_recommendation": rec,
        "reject_reason": None,
        "comments": (result or {}).get("comments", "")[:2000],
        "strengths": list(map(str, ((result or {}).get("strengths") or [])))[:8],
        "concerns": list(map(str, ((result or {}).get("concerns") or [])))[:8],
        "source": "ai",
        "transcript_length": len(body.transcript),
        "created_at": _now_iso(),
    }
    if body.persist:
        await db[SCORECARDS_COL].insert_one(scorecard)
        scorecard.pop("_id", None)
    return {"ok": True, "scorecard": scorecard, "persisted": body.persist}


# ─────────────────────────────────────────────────────────────────────────────
# 8. Candidate Portal — magic link
# ─────────────────────────────────────────────────────────────────────────────


def _public_base(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    return f"{scheme}://{host}"


@router.post("/careers/applications/{app_id}/portal-link")
async def admin_generate_portal_link(request: Request, app_id: str):
    """Create (or rotate) the candidate-portal magic-link token for an application."""
    await require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": app_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    token = secrets.token_urlsafe(24)
    await db[APPS_COL].update_one(
        {"application_id": app_id},
        {"$set": {
            "portal_token": token,
            "portal_token_issued_at": _now_iso(),
        }},
    )
    base = _public_base(request)
    return {
        "ok": True,
        "token": token,
        "url": f"{base}/careers/portal/{token}",
    }


@router.get("/careers/portal/{token}")
async def public_portal_view(token: str):
    """PUBLIC — no auth. Returns a candidate-facing status snapshot."""
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="Invalid portal token")
    doc = await db[APPS_COL].find_one({"portal_token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Portal not found")
    iv = doc.get("interview") or {}
    offer = doc.get("offer") or {}
    status = doc.get("status") or "received"
    status_step_map = {
        "received": 1, "screening": 2, "interview": 3, "offer": 4,
        "hired": 5, "rejected": 5, "withdrawn": 5, "on_hold": 2,
    }
    step = status_step_map.get(status, 1)
    # Friendly public copy — never leak admin notes, reject reasons, scorecards.
    return {
        "application_id": doc.get("application_id"),
        "candidate_name": doc.get("name") or doc.get("full_name") or "Candidate",
        "position": doc.get("role_title") or doc.get("position") or "Open Role",
        "submitted_at": doc.get("created_at"),
        "status": status,
        "status_step": step,
        "status_steps_total": 5,
        "status_label": {
            "received": "Application received",
            "screening": "Initial review",
            "interview": "Interview scheduled",
            "offer": "Offer extended",
            "hired": "Welcome aboard",
            "rejected": "Decision sent",
            "withdrawn": "Withdrawn",
            "on_hold": "On hold",
        }.get(status, status.replace("_", " ").title()),
        "interview": {
            "date": iv.get("date") or "",
            "time": iv.get("time") or "",
            "type": iv.get("type") or "",
            "candidate_response": iv.get("candidate_response") or "pending",
            "public_confirm_url": iv.get("public_confirm_url") or "",
            "video_url": iv.get("video_url") if (iv.get("candidate_response") == "accepted") else "",
        } if iv.get("date") else None,
        "offer_summary": {
            "status": offer.get("status") or "",
            "sent_at": offer.get("sent_at") or "",
            "accept_url": offer.get("accept_url") or "",
        } if offer.get("status") else None,
        "generated_at": _now_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Stalled-Candidate SLA
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/careers/applications/stalled")
async def admin_stalled_applications(request: Request, days: int = 5):
    """Admin: list applications whose status hasn't changed in >= `days` days
    AND aren't in a final state. Ranked oldest-first."""
    await require_admin(request)
    days = max(1, min(int(days or 5), 60))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # Match either status_updated_at or fall back to created_at for legacy rows
    q = {
        "status": {"$nin": list(FINAL_STATUSES)},
        "$or": [
            {"status_updated_at": {"$lte": cutoff}},
            {"status_updated_at": {"$exists": False}, "created_at": {"$lte": cutoff}},
        ],
    }
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find(q, {"_id": 0}).sort([("status_updated_at", 1), ("created_at", 1)]).limit(200):
        last = d.get("status_updated_at") or d.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            days_stalled = (datetime.now(timezone.utc) - dt).days
        except Exception:
            days_stalled = days
        items.append({
            "application_id": d.get("application_id"),
            "full_name": d.get("name") or d.get("full_name") or "",
            "email": d.get("email") or "",
            "position": d.get("role_title") or "Open Role",
            "status": d.get("status") or "received",
            "last_activity_at": last,
            "days_stalled": days_stalled,
        })
    # severity buckets
    critical = sum(1 for i in items if i["days_stalled"] >= 10)
    warning = sum(1 for i in items if 5 <= i["days_stalled"] < 10)
    return {
        "items": items,
        "count": len(items),
        "threshold_days": days,
        "severity": {"critical": critical, "warning": warning},
        "generated_at": _now_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. Duplicate Candidate Detection + Merge
# ─────────────────────────────────────────────────────────────────────────────


def _norm_email(e: str) -> str:
    e = (e or "").strip().lower()
    return e


def _norm_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def _norm_name(n: str) -> str:
    n = re.sub(r"\s+", " ", (n or "").strip().lower())
    return n


@router.get("/careers/applications/duplicates")
async def admin_find_duplicates(request: Request, min_group_size: int = 2):
    """Cluster applications by normalized email / phone / name. Return groups
    with size >= min_group_size. Also returns a flat `total_dupes` count."""
    await require_admin(request)
    min_group_size = max(2, min(int(min_group_size or 2), 10))
    email_map: dict[str, list[dict[str, Any]]] = {}
    phone_map: dict[str, list[dict[str, Any]]] = {}
    name_map: dict[str, list[dict[str, Any]]] = {}

    async for d in db[APPS_COL].find({"merged_into": {"$exists": False}}, {"_id": 0}):
        row = {
            "application_id": d.get("application_id"),
            "full_name": d.get("name") or d.get("full_name") or "",
            "email": d.get("email") or "",
            "phone": d.get("phone") or "",
            "position": d.get("role_title") or "",
            "status": d.get("status") or "received",
            "created_at": d.get("created_at") or "",
        }
        em = _norm_email(row["email"])
        ph = _norm_phone(row["phone"])
        nm = _norm_name(row["full_name"])
        if em:
            email_map.setdefault(em, []).append(row)
        if ph and len(ph) >= 7:
            phone_map.setdefault(ph, []).append(row)
        if nm and len(nm) >= 4:
            name_map.setdefault(nm, []).append(row)

    def _clusters(key: str, src: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for k, rows in src.items():
            if len(rows) >= min_group_size:
                out.append({"match_type": key, "match_value": k, "size": len(rows), "rows": rows})
        return out

    groups = _clusters("email", email_map) + _clusters("phone", phone_map) + _clusters("name", name_map)
    # dedupe same-row-pairs across match types (naive but OK for tens-of-thousands)
    seen_ids: set[str] = set()
    total_dupes = 0
    for g in groups:
        for r in g["rows"]:
            if r["application_id"]:
                if r["application_id"] not in seen_ids:
                    seen_ids.add(r["application_id"])
                    total_dupes += 1
    # Sort groups: email > phone > name, then size desc
    type_rank = {"email": 0, "phone": 1, "name": 2}
    groups.sort(key=lambda g: (type_rank.get(g["match_type"], 9), -g["size"]))
    return {
        "groups": groups,
        "group_count": len(groups),
        "total_candidates_with_dupes": total_dupes,
        "generated_at": _now_iso(),
    }


class MergeBody(BaseModel):
    secondary_ids: list[str] = Field(..., min_length=1, max_length=20)
    keep_notes: bool = True


@router.post("/careers/applications/{primary_id}/merge")
async def admin_merge_applications(request: Request, primary_id: str, body: MergeBody):
    """Merge secondary application rows into a primary. Secondaries get
    `merged_into=primary_id` + `merged_at` and are excluded from all lists.
    Notes + admin_notes are concatenated onto the primary."""
    admin = await require_admin(request)
    primary = await db[APPS_COL].find_one({"application_id": primary_id}, {"_id": 0})
    if not primary:
        raise HTTPException(status_code=404, detail="Primary application not found")

    merged_notes = primary.get("admin_notes") or ""
    merged_scorecards = 0
    merged_count = 0
    skipped: list[dict[str, Any]] = []

    for sid in body.secondary_ids:
        if sid == primary_id:
            skipped.append({"application_id": sid, "reason": "same_as_primary"})
            continue
        sec = await db[APPS_COL].find_one({"application_id": sid}, {"_id": 0})
        if not sec:
            skipped.append({"application_id": sid, "reason": "not_found"})
            continue
        if sec.get("merged_into"):
            skipped.append({"application_id": sid, "reason": "already_merged"})
            continue
        if body.keep_notes and sec.get("admin_notes"):
            merged_notes += f"\n\n── Merged from {sid} on {_now_iso()[:10]} ──\n{sec['admin_notes']}"
        # reassign scorecards to primary
        res = await db[SCORECARDS_COL].update_many(
            {"application_id": sid},
            {"$set": {"application_id": primary_id, "merged_from": sid}},
        )
        merged_scorecards += res.modified_count
        await db[APPS_COL].update_one(
            {"application_id": sid},
            {"$set": {
                "merged_into": primary_id,
                "merged_at": _now_iso(),
                "merged_by": getattr(admin, "email", None) or getattr(admin, "user_id", None),
                "status": sec.get("status") or "merged",
            }},
        )
        merged_count += 1

    if merged_count and merged_notes != (primary.get("admin_notes") or ""):
        await db[APPS_COL].update_one(
            {"application_id": primary_id},
            {"$set": {"admin_notes": merged_notes, "status_updated_at": _now_iso()}},
        )

    return {
        "ok": True,
        "primary_id": primary_id,
        "merged_count": merged_count,
        "merged_scorecards": merged_scorecards,
        "skipped": skipped,
        "generated_at": _now_iso(),
    }
