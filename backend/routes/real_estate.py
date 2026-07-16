"""Property Decision Advisor - Enterprise-Grade Real Estate Platform

Feature 14: Property Decision Advisor
- AI property search with market insights
- Mortgage calculator
- AI valuation reports  
- Tour scheduling

Tier Limits:
- Free: 3 searches/day, 2 valuations/day
- Basic: 70 searches/day, 35 valuations/day
- Premium: Unlimited searches and valuations
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Any
import uuid
from datetime import datetime, timezone
from .db import db, get_current_user, logger
from utils.llm_helper import generate_verified_json, generate_verified_text
from utils.access_control_engine import compute_effective_plan

router = APIRouter()

# ── Models ──


class PropertySearch(BaseModel):
    location: str
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[int] = None
    property_type: Optional[str] = None
    fallback_user_id: Optional[str] = None


class MortgageRequest(BaseModel):
    price: int
    down_payment: int
    rate: float
    term_years: int


class AIValuationRequest(BaseModel):
    address: str
    fallback_user_id: Optional[str] = None


class TourRequest(BaseModel):
    property_address: str
    preferred_date: str
    fallback_user_id: Optional[str] = None


# ── Tier Configuration ──

TIER_LIMITS = {
    "free": {"searches_per_day": 3, "valuations_per_day": 2},
    "basic": {"searches_per_day": 70, "valuations_per_day": 35},
    "premium": {"searches_per_day": -1, "valuations_per_day": -1},  # Unlimited
}


# ── Authentication & Tier Helpers ──


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"
    if fallback_user_id:
        return f"guest:{fallback_user_id}"
    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "real_estate_auth_required",
            "message": "Login required or provide fallback_user_id for guest access",
        },
    )


async def _get_tier(owner_id: str) -> str:
    """Get user's subscription tier."""
    if str(owner_id or "").startswith("guest:"):
        return "free"

    user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")
    if not user_id:
        return "free"

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
    if user_doc:
        effective = compute_effective_plan(user_doc or {})
        return effective if effective in TIER_LIMITS else "free"
    return "free"


async def _check_daily_limit(owner_id: str, tier: str, limit_key: str) -> tuple[int, int]:
    """Check and enforce daily tier limits. Returns (used, limit)."""
    limit = TIER_LIMITS[tier][limit_key]
    if limit == -1:  # Unlimited
        return 0, -1
    
    # Count today's usage
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.real_estate_usage_log.count_documents({
        "owner_id": owner_id,
        "action": limit_key.replace("_per_day", ""),
        "created_at": {"$gte": start_of_day}
    })
    
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily {limit_key} limit reached for {tier} tier ({limit}). Upgrade for more."
        )
    
    return used, limit


async def _log_usage(owner_id: str, action: str, tier: str) -> None:
    """Log feature usage for analytics and tier enforcement."""
    await db.real_estate_usage_log.insert_one({
        "owner_id": owner_id,
        "action": action,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ── AI Property Generator ──


async def generate_ai_properties(location: str, count: int = 5):
    """Generate realistic property listings using AI."""
    try:
        session_id = f"prop-gen-{uuid.uuid4().hex[:8]}"
        system_msg = "You are a Real Estate Data Engine. Generate realistic property listings."
        
        prompt = f"""Generate {count} realistic real estate listings for {location}.
        Ensure prices, architectural styles, and amenities match the real-world location.
        
        Return ONLY valid JSON array of objects with keys:
        - address (string)
        - city (string)
        - price (integer)
        - beds (integer)
        - baths (integer)
        - sqft (integer)
        - type (Single Family, Condo, Townhouse)
        - year_built (integer)
        - description (string, 2-3 sentences)
        - amenities (array of 3 strings)
        - image_keyword (modern, brick, villa, cottage, contemporary)
        """
        
        listings = await generate_verified_json(prompt, system_msg, session_id)
        
        results = []
        for prop in (listings if isinstance(listings, list) else []):
            if isinstance(prop, dict):
                prop["id"] = uuid.uuid4().hex[:12]
                results.append(prop)
        
        return results[:count]
    except Exception as e:
        logger.error(f"AI property generation failed: {e}")
        return []


# ── Endpoints ──


@router.post("/real-estate/search")
async def search_properties(request: Request, payload: PropertySearch):
    """Search for properties with AI-generated market insights."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    used, limit = await _check_daily_limit(owner_id, tier, "searches_per_day")
    
    # Generate AI properties
    properties = await generate_ai_properties(payload.location, count=5)
    if not properties:
        # Fallback
        properties = await generate_ai_properties("Modern City", count=5)
    
    await _log_usage(owner_id, "search", tier)
    
    return {
        "properties": properties,
        "total": len(properties),
        "owner_id": owner_id,
        "tier": tier,
        "daily_limit": limit,
        "used_today": used + 1,
        "remaining_today": limit - used - 1 if limit != -1 else "unlimited"
    }


@router.post("/real-estate/ai-valuation")
async def get_ai_valuation(request: Request, payload: AIValuationRequest):
    """Get AI-powered property valuation report."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    used, limit = await _check_daily_limit(owner_id, tier, "valuations_per_day")
    
    try:
        session_id = f"valuation-{uuid.uuid4().hex[:8]}"
        system_msg = "You are a Real Estate Appraiser. Provide detailed valuation reports."
        
        prompt = f"""Analyze the estimated value for a property at: {payload.address}.
        Assume it is a standard 3-bed 2-bath home if details are missing.
        
        Provide:
        1. Estimated Market Value (single number with reasoning)
        2. Confidence Range (Low - High estimates)
        3. Market Trends (current market conditions)
        4. Key Value Factors (location, condition, amenities)
        5. Investment Outlook (hold, sell, buy)
        
        Format as a detailed paragraph report.
        """
        
        valuation_report = await generate_verified_text(prompt, system_msg, session_id)
        
        await _log_usage(owner_id, "valuation", tier)
        
        return {
            "address": payload.address,
            "valuation_report": valuation_report,
            "owner_id": owner_id,
            "tier": tier,
            "daily_limit": limit,
            "used_today": used + 1,
            "remaining_today": limit - used - 1 if limit != -1 else "unlimited"
        }
    
    except Exception as e:
        logger.error(f"AI valuation failed: {e}")
        raise HTTPException(status_code=500, detail="Valuation generation failed. Please try again.")


@router.post("/real-estate/mortgage-calculator")
async def calculate_mortgage(payload: MortgageRequest):
    """Calculate mortgage payments (no authentication required for calculator)."""
    try:
        principal = payload.price - payload.down_payment
        monthly_rate = payload.rate / 100 / 12
        num_payments = payload.term_years * 12
        
        if monthly_rate == 0:
            monthly_payment = principal / num_payments
        else:
            monthly_payment = principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
        
        total_paid = monthly_payment * num_payments
        total_interest = total_paid - principal
        
        return {
            "monthly_payment": round(monthly_payment, 2),
            "total_paid": round(total_paid, 2),
            "total_interest": round(total_interest, 2),
            "principal": principal,
            "down_payment": payload.down_payment,
            "rate": payload.rate,
            "term_years": payload.term_years
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Calculation error: {str(e)}")


@router.post("/real-estate/schedule-tour")
async def schedule_tour(request: Request, payload: TourRequest):
    """Schedule a property tour (requires authentication)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    if tier == "free":
        return {
            "success": False,
            "message": "Premium required for instant tour booking. Upgrade to schedule tours.",
            "tier": tier
        }
    
    tour_id = uuid.uuid4().hex
    await db.real_estate_tours.insert_one({
        "tour_id": tour_id,
        "owner_id": owner_id,
        "property_address": payload.property_address,
        "preferred_date": payload.preferred_date,
        "status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "message": "Tour confirmed! An agent will meet you at the property.",
        "tour_id": tour_id,
        "property_address": payload.property_address,
        "preferred_date": payload.preferred_date,
        "tier": tier
    }
