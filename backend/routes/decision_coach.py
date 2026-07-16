"""Decision Coach — Enterprise-grade decision-making framework API.

Helps users make better decisions using structured frameworks (pros/cons, SWOT, decision matrix),
AI-powered analysis, outcome tracking, and analytics.

Tier Limits:
  Free    → 5 decisions/month, basic frameworks
  Basic   → 20 decisions/month, standard frameworks, outcome tracking
  Premium → Unlimited decisions, all frameworks, collaboration, advanced analytics
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

from models.decision import (
    CreateDecisionRequest,
    UpdateDecisionRequest,
    AnalyzeDecisionRequest,
    DecideRequest,
    UpdateOutcomeRequest,
    CreateFromTemplateRequest,
    DecisionResponse,
)
from routes.db import db, get_current_user, EMERGENT_LLM_KEY, logger


router = APIRouter(prefix="/decision-coach", tags=["Decision Coach"])

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ── Tier Limits ──

TIER_LIMITS = {
    "free": {
        "decisions_per_month": 5,
        "frameworks": ["pros_cons"],
        "ai_analysis": True,
        "outcome_tracking": False,
        "collaboration": False,
        "templates": "basic",
        "export_formats": [],
    },
    "basic": {
        "decisions_per_month": 20,
        "frameworks": ["pros_cons", "swot", "decision_matrix"],
        "ai_analysis": True,
        "outcome_tracking": True,
        "collaboration": False,
        "templates": "standard",
        "export_formats": ["txt"],
    },
    "premium": {
        "decisions_per_month": -1,  # Unlimited
        "frameworks": ["pros_cons", "swot", "decision_matrix", "weighted_scoring"],
        "ai_analysis": True,
        "outcome_tracking": True,
        "collaboration": True,
        "templates": "all",
        "export_formats": ["txt", "pdf", "json"],
    },
}

# ── Decision Templates ──

TEMPLATES = [
    # Free templates
    {
        "template_id": "tmpl_career_change",
        "name": "Career Change Decision",
        "description": "Evaluate whether to switch careers or stay in current role",
        "category": "career",
        "framework_type": "pros_cons",
        "tier_requirement": "free",
        "icon": "briefcase",
        "color": "#3B82F6",
        "usage_count": 0,
        "preset_options": ["Stay in current role", "Switch careers"],
    },
    {
        "template_id": "tmpl_job_offer",
        "name": "Job Offer Evaluation",
        "description": "Compare multiple job offers and decide which to accept",
        "category": "career",
        "framework_type": "pros_cons",
        "tier_requirement": "free",
        "icon": "document-text",
        "color": "#10B981",
        "usage_count": 0,
        "preset_options": ["Current job", "New offer"],
    },
    {
        "template_id": "tmpl_major_purchase",
        "name": "Major Purchase Decision",
        "description": "Decide whether to make a significant purchase (car, house, etc.)",
        "category": "financial",
        "framework_type": "pros_cons",
        "tier_requirement": "free",
        "icon": "cash",
        "color": "#F59E0B",
        "usage_count": 0,
        "preset_options": ["Buy now", "Wait/Don't buy"],
    },
    # Basic templates
    {
        "template_id": "tmpl_business_strategy",
        "name": "Business Strategy Decision",
        "description": "Analyze strategic options using SWOT framework",
        "category": "business",
        "framework_type": "swot",
        "tier_requirement": "basic",
        "icon": "trending-up",
        "color": "#8B5CF6",
        "usage_count": 0,
    },
    {
        "template_id": "tmpl_vendor_selection",
        "name": "Vendor/Supplier Selection",
        "description": "Compare vendors using weighted criteria matrix",
        "category": "business",
        "framework_type": "decision_matrix",
        "tier_requirement": "basic",
        "icon": "people",
        "color": "#EC4899",
        "usage_count": 0,
        "preset_criteria": ["Price", "Quality", "Support", "Reliability"],
    },
    {
        "template_id": "tmpl_relocation",
        "name": "City/Country Relocation",
        "description": "Decide whether to move to a new location",
        "category": "life",
        "framework_type": "decision_matrix",
        "tier_requirement": "basic",
        "icon": "location",
        "color": "#EF4444",
        "usage_count": 0,
        "preset_criteria": ["Cost of living", "Career opportunities", "Quality of life", "Family"],
    },
    # Premium templates
    {
        "template_id": "tmpl_investment",
        "name": "Investment Decision",
        "description": "Evaluate investment opportunities with weighted scoring",
        "category": "financial",
        "framework_type": "weighted_scoring",
        "tier_requirement": "premium",
        "icon": "stats-chart",
        "color": "#06B6D4",
        "usage_count": 0,
        "preset_criteria": ["ROI potential", "Risk level", "Time horizon", "Liquidity"],
    },
    {
        "template_id": "tmpl_product_launch",
        "name": "Product Launch Decision",
        "description": "Decide when and how to launch a new product",
        "category": "business",
        "framework_type": "weighted_scoring",
        "tier_requirement": "premium",
        "icon": "rocket",
        "color": "#F59E0B",
        "usage_count": 0,
        "preset_criteria": ["Market readiness", "Competition", "Resources", "Timing"],
    },
]

TEMPLATE_MAP = {t["template_id"]: t for t in TEMPLATES}


# ── Helper Functions ──


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if not fallback:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "decision_coach_auth_required",
                "message": "Login required or provide fallback_user_id",
            },
        )
    if not GUEST_ID_RE.match(fallback):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "decision_coach_invalid_guest_id",
                "message": "fallback_user_id format is invalid",
            },
        )
    return f"guest:{fallback}"


async def _get_user_tier(owner_id: str) -> str:
    """Determine user's subscription tier (free, basic, premium)."""
    if not owner_id.startswith("auth:"):
        return "free"  # Guest users are always free tier
    
    try:
        user_id = owner_id.replace("auth:", "")
        user_doc = await db.users.find_one(
            {"user_id": user_id},
            {
                "_id": 0,
                "subscription_plan": 1,
                "subscription_status": 1,
                "subscription_end_date": 1,
                "pending_subscription_transition": 1,
                "payment_verified": 1,
                "is_admin": 1,
            },
        )
        if not user_doc:
            return "free"

        effective = compute_effective_plan(user_doc or {})
        return effective if effective in TIER_LIMITS else "free"
    except Exception as e:
        logger.warning(f"Failed to fetch tier for {owner_id}: {e}")
        return "free"


async def _get_monthly_decision_count(owner_id: str) -> int:
    """Get number of decisions created this month by user."""
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = await db.decisions.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": month_start.isoformat()},
    })
    return count


async def _check_decision_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can create more decisions this month. Returns usage info."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    monthly_limit = limits["decisions_per_month"]
    
    # Premium has unlimited (-1)
    if monthly_limit == -1:
        return {
            "can_create": True,
            "decisions_used_this_month": 0,
            "monthly_limit": -1,
            "tier": tier,
            "limit_reached": False,
        }
    
    decisions_used = await _get_monthly_decision_count(owner_id)
    can_create = decisions_used < monthly_limit
    
    return {
        "can_create": can_create,
        "decisions_used_this_month": decisions_used,
        "monthly_limit": monthly_limit,
        "tier": tier,
        "limit_reached": not can_create,
    }


def _has_framework_access(tier: str, framework_type: str) -> bool:
    """Check if user tier has access to requested framework."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    return framework_type in limits["frameworks"]


def _calculate_pros_cons_score(option: Dict[str, Any]) -> float:
    """Calculate weighted score for pros/cons option."""
    pros = option.get("pros", [])
    cons = option.get("cons", [])
    
    pros_score = sum(item.get("weight", 5) for item in pros)
    cons_score = sum(item.get("weight", 5) for item in cons)
    
    # Normalize to 0-100 scale
    total = pros_score + cons_score
    if total == 0:
        return 50.0
    
    return round((pros_score / total) * 100, 1)


# ── API Endpoints ──


@router.get("/bootstrap")
async def bootstrap_decision_coach(request: Request, fallback_user_id: Optional[str] = None):
    """Get initial data: usage stats, recent decisions, templates."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get tier and usage info
    tier = await _get_user_tier(owner_id)
    usage_info = await _check_decision_limit(owner_id, tier)
    
    # Get recent decisions
    recent_decisions = await db.decisions.find(
        {"owner_id": owner_id},
        {"_id": 0, "decision_id": 1, "title": 1, "status": 1, "framework_type": 1, "created_at": 1, "decided_at": 1},
    ).sort("created_at", -1).limit(10).to_list(10)
    
    # Filter templates by tier
    tier_templates = []
    for template in TEMPLATES:
        template_tier = template.get("tier_requirement", "free")
        # Check if user's tier can access this template
        tier_hierarchy = {"free": 0, "basic": 1, "premium": 2}
        user_level = tier_hierarchy.get(tier, 0)
        required_level = tier_hierarchy.get(template_tier, 0)
        if user_level >= required_level:
            tier_templates.append(template)
    
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "usage": {
            **usage_info,
            "frameworks_available": limits["frameworks"],
            "templates_available": limits["templates"],
        },
        "recent_decisions": recent_decisions,
        "templates": tier_templates,
        "stats": {
            "total_decisions": await db.decisions.count_documents({"owner_id": owner_id}),
            "this_month": usage_info["decisions_used_this_month"],
        },
    }


@router.post("/decisions", response_model=DecisionResponse)
async def create_decision(payload: CreateDecisionRequest, request: Request):
    """Create a new decision."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check tier and decision limits
    tier = await _get_user_tier(owner_id)
    usage_check = await _check_decision_limit(owner_id, tier)
    
    if not usage_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "decision_coach_limit_reached",
                "message": f"Monthly decision limit reached ({usage_check['monthly_limit']}/month for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "decisions_used_this_month": usage_check["decisions_used_this_month"],
                "monthly_limit": usage_check["monthly_limit"],
            },
        )
    
    # Check framework access
    if not _has_framework_access(tier, payload.framework_type):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "decision_coach_framework_access_denied",
                "message": f"Framework '{payload.framework_type}' requires {tier == 'free' and 'Basic' or 'Premium'} tier.",
                "upgrade_prompt": True,
            },
        )
    
    now = _now_iso()
    decision = {
        "decision_id": f"dec_{uuid.uuid4().hex[:14]}",
        "owner_id": owner_id,
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "framework_type": payload.framework_type,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "deadline": payload.deadline,
        "final_choice": None,
        "confidence_score": None,
        "framework_data": {},
        "ai_analysis": None,
        "outcome": None,
    }
    
    await db.decisions.insert_one(dict(decision))
    decision.pop("_id", None)
    return decision


@router.get("/decisions")
async def list_decisions(request: Request, fallback_user_id: Optional[str] = None, status: Optional[str] = None):
    """List user's decisions with optional status filter."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    filter_query = {"owner_id": owner_id}
    if status:
        filter_query["status"] = status
    
    decisions = await db.decisions.find(
        filter_query,
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    
    return {"decisions": decisions}


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(decision_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Get decision details by ID."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    decision = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    
    if not decision:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    return decision


@router.put("/decisions/{decision_id}", response_model=DecisionResponse)
async def update_decision(decision_id: str, payload: UpdateDecisionRequest, request: Request):
    """Update decision data (title, description, framework_data, status)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    decision = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    
    if not decision:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    # Build update document
    update_doc = {"updated_at": _now_iso()}
    if payload.title is not None:
        update_doc["title"] = payload.title.strip()
    if payload.description is not None:
        update_doc["description"] = payload.description.strip()
    if payload.framework_data is not None:
        update_doc["framework_data"] = payload.framework_data
        
        # Auto-calculate scores for pros/cons
        if decision["framework_type"] == "pros_cons" and "options" in payload.framework_data:
            for option in payload.framework_data["options"]:
                option["score"] = _calculate_pros_cons_score(option)
    
    if payload.status is not None:
        update_doc["status"] = payload.status
    
    await db.decisions.update_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"$set": update_doc},
    )
    
    # Return updated decision
    updated = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    return updated


@router.delete("/decisions/{decision_id}")
async def delete_decision(decision_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete a decision."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.decisions.delete_one({"owner_id": owner_id, "decision_id": decision_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    return {"success": True, "message": "Decision deleted"}


@router.post("/decisions/{decision_id}/analyze")
async def analyze_decision(decision_id: str, payload: AnalyzeDecisionRequest, request: Request):
    """Generate AI-powered analysis for the decision."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    decision = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    
    if not decision:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    # Update status to analyzing
    await db.decisions.update_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"$set": {"status": "analyzing", "updated_at": _now_iso()}},
    )
    
    # Generate AI analysis using LLM
    try:
        framework_type = decision["framework_type"]
        framework_data = decision.get("framework_data", {})
        
        # Build prompt based on framework type
        if framework_type == "pros_cons":
            options = framework_data.get("options", [])
            prompt = f"""Analyze this decision: "{decision['title']}"

Description: {decision['description']}

Options being compared:
{chr(10).join([f"Option {i+1}: {opt['name']} (Score: {opt.get('score', 50)})" for i, opt in enumerate(options)])}

Provide a structured analysis:
1. Summary (2-3 sentences)
2. Recommendation (which option and why)
3. Confidence level (0-100)
4. Risk level (low/medium/high)
5. 3-5 key insights
6. Potential cognitive biases to watch for
7. Risk factors to consider

Format as JSON."""
        
        elif framework_type == "swot":
            quadrants = framework_data
            prompt = f"""Analyze this SWOT decision: "{decision['title']}"

Description: {decision['description']}

SWOT Analysis:
- Strengths: {', '.join(quadrants.get('strengths', []))}
- Weaknesses: {', '.join(quadrants.get('weaknesses', []))}
- Opportunities: {', '.join(quadrants.get('opportunities', []))}
- Threats: {', '.join(quadrants.get('threats', []))}

Provide strategic analysis as JSON with: summary, recommendation, confidence, risk_level, key_insights (list), bias_warnings (list), risk_factors (dict)."""
        
        elif framework_type == "decision_matrix":
            prompt = f"""Analyze this decision matrix: "{decision['title']}"

Description: {decision['description']}

Matrix Data: {str(framework_data)[:500]}

Provide analysis as JSON with: summary, recommendation, confidence, risk_level, key_insights, bias_warnings, risk_factors."""
        
        else:
            prompt = f"""Analyze this decision: "{decision['title']}"

Description: {decision['description']}

Provide analysis as JSON with: summary, recommendation, confidence (0-100), risk_level (low/medium/high), key_insights (list), bias_warnings (list), risk_factors (dict)."""
        
        # Call LLM using correct pattern
        chat = (
            LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"dc-analyze-{decision_id[:10]}",
                system_message="You are an expert decision analysis AI. Always respond with valid JSON only.",
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        analysis_text = response

        # Parse JSON from LLM response (may be wrapped in markdown code blocks)
        import json as _json
        
        # Try to extract JSON from markdown code block if present
        if "```json" in analysis_text:
            analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
        elif "```" in analysis_text:
            analysis_text = analysis_text.split("```")[1].split("```")[0].strip()

        ai_analysis = _json.loads(analysis_text)
        
        # Ensure required fields exist
        if "summary" not in ai_analysis:
            ai_analysis["summary"] = "Analysis completed"
        if "recommendation" not in ai_analysis:
            ai_analysis["recommendation"] = "Review all options carefully"
        if "confidence" not in ai_analysis:
            ai_analysis["confidence"] = 70
        if "risk_level" not in ai_analysis:
            ai_analysis["risk_level"] = "medium"
        if "key_insights" not in ai_analysis:
            ai_analysis["key_insights"] = []
        if "bias_warnings" not in ai_analysis:
            ai_analysis["bias_warnings"] = []
        if "risk_factors" not in ai_analysis:
            ai_analysis["risk_factors"] = {}
        
        # Update decision with AI analysis
        await db.decisions.update_one(
            {"owner_id": owner_id, "decision_id": decision_id},
            {"$set": {
                "ai_analysis": ai_analysis,
                "status": "draft",
                "updated_at": _now_iso(),
            }},
        )
        
        return {"success": True, "ai_analysis": ai_analysis}
    
    except Exception as e:
        logger.error(f"AI analysis failed for decision {decision_id}: {str(e)}")
        # Revert status
        await db.decisions.update_one(
            {"owner_id": owner_id, "decision_id": decision_id},
            {"$set": {"status": "draft", "updated_at": _now_iso()}},
        )
        raise HTTPException(
            status_code=500,
            detail={"error_code": "ai_analysis_failed", "message": "AI analysis failed. Please try again."},
        )


@router.post("/decisions/{decision_id}/decide")
async def mark_as_decided(decision_id: str, payload: DecideRequest, request: Request):
    """Mark decision as decided with final choice."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    decision = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    
    if not decision:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    now = _now_iso()
    await db.decisions.update_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"$set": {
            "status": "decided",
            "final_choice": payload.final_choice,
            "confidence_score": payload.confidence_score,
            "decided_at": now,
            "updated_at": now,
        }},
    )
    
    return {"success": True, "message": "Decision marked as decided"}


@router.put("/decisions/{decision_id}/outcome")
async def update_outcome(decision_id: str, payload: UpdateOutcomeRequest, request: Request):
    """Update decision outcome after it's been decided (for tracking)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check tier - outcome tracking requires basic or premium
    tier = await _get_user_tier(owner_id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    if not limits["outcome_tracking"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "outcome_tracking_access_denied",
                "message": "Outcome tracking requires Basic tier or higher.",
                "upgrade_prompt": True,
            },
        )
    
    decision = await db.decisions.find_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"_id": 0},
    )
    
    if not decision:
        raise HTTPException(status_code=404, detail={"error_code": "decision_not_found", "message": "Decision not found"})
    
    outcome = {
        "satisfaction_score": payload.satisfaction_score,
        "lessons_learned": payload.lessons_learned,
        "would_decide_again": payload.would_decide_again,
        "actual_result": payload.actual_result,
        "updated_at": _now_iso(),
    }
    
    await db.decisions.update_one(
        {"owner_id": owner_id, "decision_id": decision_id},
        {"$set": {
            "outcome": outcome,
            "status": "tracked",
            "updated_at": _now_iso(),
        }},
    )
    
    return {"success": True, "message": "Outcome updated"}


@router.get("/templates")
async def list_templates(request: Request, fallback_user_id: Optional[str] = None):
    """Get decision templates filtered by user's tier."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    tier = await _get_user_tier(owner_id)
    
    # Filter templates by tier
    tier_templates = []
    tier_hierarchy = {"free": 0, "basic": 1, "premium": 2}
    user_level = tier_hierarchy.get(tier, 0)
    
    for template in TEMPLATES:
        template_tier = template.get("tier_requirement", "free")
        required_level = tier_hierarchy.get(template_tier, 0)
        if user_level >= required_level:
            tier_templates.append(template)
    
    return {"templates": tier_templates, "tier": tier}


@router.post("/decisions/from-template")
async def create_from_template(payload: CreateFromTemplateRequest, request: Request):
    """Create a decision from a template."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check tier and decision limits
    tier = await _get_user_tier(owner_id)
    usage_check = await _check_decision_limit(owner_id, tier)
    
    if not usage_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "decision_coach_limit_reached",
                "message": f"Monthly decision limit reached ({usage_check['monthly_limit']}/month).",
                "upgrade_prompt": True,
            },
        )
    
    # Get template
    template = TEMPLATE_MAP.get(payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail={"error_code": "template_not_found", "message": "Template not found"})
    
    # Check tier access to template
    tier_hierarchy = {"free": 0, "basic": 1, "premium": 2}
    user_level = tier_hierarchy.get(tier, 0)
    template_tier = template.get("tier_requirement", "free")
    required_level = tier_hierarchy.get(template_tier, 0)
    
    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "template_access_denied",
                "message": f"This template requires {template_tier} tier.",
                "upgrade_prompt": True,
            },
        )
    
    # Check framework access
    if not _has_framework_access(tier, template["framework_type"]):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "framework_access_denied",
                "message": f"Framework '{template['framework_type']}' requires higher tier.",
                "upgrade_prompt": True,
            },
        )
    
    # Create decision from template
    now = _now_iso()
    decision = {
        "decision_id": f"dec_{uuid.uuid4().hex[:14]}",
        "owner_id": owner_id,
        "title": payload.title or template["name"],
        "description": template["description"],
        "framework_type": template["framework_type"],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "deadline": None,
        "final_choice": None,
        "confidence_score": None,
        "framework_data": {},
        "ai_analysis": None,
        "outcome": None,
    }
    
    # Pre-populate framework_data from template
    if template["framework_type"] == "pros_cons" and "preset_options" in template:
        decision["framework_data"] = {
            "options": [
                {
                    "option_id": f"opt_{i}",
                    "name": opt,
                    "pros": [],
                    "cons": [],
                    "score": 50.0,
                }
                for i, opt in enumerate(template["preset_options"])
            ]
        }
    
    elif template["framework_type"] == "decision_matrix" and "preset_criteria" in template:
        decision["framework_data"] = {
            "criteria": [
                {
                    "criteria_id": f"crit_{i}",
                    "name": crit,
                    "weight": 5,
                    "description": "",
                }
                for i, crit in enumerate(template["preset_criteria"])
            ],
            "options": [],
        }
    
    await db.decisions.insert_one(dict(decision))
    
    # Increment template usage count
    await db.decision_templates.update_one(
        {"template_id": payload.template_id},
        {"$inc": {"usage_count": 1}},
        upsert=True,
    )
    
    decision.pop("_id", None)
    return {"decision": decision}


@router.get("/analytics")
async def get_analytics(request: Request, fallback_user_id: Optional[str] = None):
    """Get analytics for user's decisions."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get all decisions
    all_decisions = await db.decisions.find(
        {"owner_id": owner_id},
        {"_id": 0},
    ).to_list(1000)
    
    # Calculate stats
    total_decisions = len(all_decisions)
    
    # This month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    decisions_this_month = sum(1 for d in all_decisions if d.get("created_at", "") >= month_start.isoformat())
    
    # Average confidence
    decided = [d for d in all_decisions if d.get("status") == "decided" and d.get("confidence_score")]
    avg_confidence = round(sum(d["confidence_score"] for d in decided) / len(decided), 1) if decided else 0.0
    
    # Success rate (satisfaction >= 7)
    tracked = [d for d in all_decisions if d.get("outcome") and d["outcome"].get("satisfaction_score")]
    success_rate = round(
        (sum(1 for d in tracked if d["outcome"]["satisfaction_score"] >= 7) / len(tracked)) * 100, 1
    ) if tracked else 0.0
    
    # Most used framework
    framework_usage = {}
    for d in all_decisions:
        fw = d.get("framework_type", "unknown")
        framework_usage[fw] = framework_usage.get(fw, 0) + 1
    most_used = max(framework_usage.items(), key=lambda x: x[1])[0] if framework_usage else "none"
    
    # Decision speed (avg hours from created to decided)
    speed_data = []
    for d in all_decisions:
        if d.get("decided_at") and d.get("created_at"):
            created = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
            decided = datetime.fromisoformat(d["decided_at"].replace("Z", "+00:00"))
            hours = (decided - created).total_seconds() / 3600
            speed_data.append(hours)
    avg_speed = round(sum(speed_data) / len(speed_data), 1) if speed_data else 0.0
    
    # Recent decisions
    recent = all_decisions[:5]
    
    return {
        "total_decisions": total_decisions,
        "decisions_this_month": decisions_this_month,
        "avg_confidence_score": avg_confidence,
        "success_rate": success_rate,
        "most_used_framework": most_used,
        "decision_speed_avg_hours": avg_speed,
        "framework_usage": framework_usage,
        "recent_decisions": recent,
    }

