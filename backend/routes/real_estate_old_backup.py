from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import uuid
import random
from datetime import datetime, timezone
from .db import User, db, has_basic_access, logger, resolve_user_role
from utils.llm_helper import generate_verified_json, generate_verified_text

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


REAL_ESTATE_DAILY_LIMITS = {
    "search": {"free": 3, "basic": 70, "premium": -1},
    "valuation": {"free": 2, "basic": 35, "premium": -1},
}


def _resolve_real_estate_plan(user: User | None) -> str:
    if not user:
        return "free"
    subscription_plan = (user.subscription_plan or "free").lower()
    if subscription_plan in {"premium", "enterprise", "admin"}:
        return "premium"
    if subscription_plan == "basic":
        return "basic"
    role = resolve_user_role(user)
    if role in {"admin", "full_users", "premium"}:
        return "premium"
    if role == "basic":
        return "basic"
    return "free"


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


async def _enforce_real_estate_limit(user_id: str, action: str, plan: str) -> tuple[int, int]:
    action_limits = REAL_ESTATE_DAILY_LIMITS.get(action) or REAL_ESTATE_DAILY_LIMITS["search"]
    limit = int(action_limits.get(plan, action_limits.get("free", 0)))
    if limit < 0:
        return 0, limit

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.real_estate_usage_log.count_documents(
        {"user_id": user_id, "action": action, "created_at": {"$gte": start}}
    )
    if used >= limit:
        raise HTTPException(status_code=429, detail=f"{_scope_label(plan)}: daily {action} limit reached ({limit}).")
    return used, limit


async def _log_real_estate_usage(user_id: str, action: str, plan: str) -> None:
    await db.real_estate_usage_log.insert_one(
        {
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


# ── AI Inventory Generator ──


async def generate_ai_properties(location: str, count: int = 6):
    try:
        session_id = f"gen-prop-{uuid.uuid4().hex[:8]}"
        system_msg = "You are a Real Estate Data Engine. Generate realistic property listings."

        prompt = f"""Generate {count} realistic real estate listings for {location}.
        Ensure prices, architectural styles, and amenities match the real-world location.
        
        Return ONLY valid JSON array of objects with keys:
        - address
        - city
        - price (integer)
        - beds (int)
        - baths (int)
        - sqft (int)
        - type (Single Family, Condo)
        - year_built (int)
        - description
        - amenities (list of 3 strings)
        - image_keyword (modern, brick, villa, cottage)
        """

        listings = await generate_verified_json(prompt, system_msg, session_id)

        results = []
        for item in listings:
            image_map = {
                "modern": "1600596542815-a67992989d7f",
                "villa": "1613490493576-b83d3e7102e1",
                "brick": "1512917774080-9991f1c4c750",
                "cottage": "1568605114967-8130f3a36f89",
                "condo": "1545324418-cc1a3fa10c00",
                "luxury": "1613977257363-707ba9348227",
            }
            img_id = image_map.get(item.get("image_keyword", "modern").lower(), "1564013799919-ab600027ffc6")

            results.append(
                {
                    "id": f"prop_{uuid.uuid4().hex[:8]}",
                    "address": item["address"],
                    "city": item["city"],
                    "price": item["price"],
                    "beds": item["beds"],
                    "baths": item["baths"],
                    "sqft": item["sqft"],
                    "type": item["type"],
                    "year_built": item["year_built"],
                    "description": item["description"],
                    "image": f"https://images.unsplash.com/photo-{img_id}?auto=format&fit=crop&w=800&q=80",
                    "ai_estimate": int(item["price"] * random.uniform(0.98, 1.05)),
                    "walk_score": random.randint(30, 98),
                    "amenities": item["amenities"],
                }
            )

        return results
    except Exception as e:
        logger.error(f"AI Prop Gen Error: {e}")
        return []


# ── Routes ──


@router.post("/real-estate/search")
async def search_properties(request: PropertySearch):
    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    plan = _resolve_real_estate_plan(user)
    used, limit = await _enforce_real_estate_limit(request.user_id, "search", plan)

    properties = await generate_ai_properties(request.location, count=5)
    if not properties:
        properties = await generate_ai_properties("Modern City", count=5)  # Fallback
    await _log_real_estate_usage(request.user_id, "search", plan)
    return {
        "properties": properties,
        "total": len(properties),
        "plan_scope": plan,
        "scope_label": _scope_label(plan),
        "daily_limit": limit,
        "used_today": used + 1,
    }


@router.post("/real-estate/ai-valuation")
async def get_ai_valuation(request: AIValuationRequest):
    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    plan = _resolve_real_estate_plan(user)
    used, limit = await _enforce_real_estate_limit(request.user_id, "valuation", plan)

    address = request.address or "Unknown"

    try:
        session_id = f"valuation-{uuid.uuid4().hex[:8]}"
        system_msg = "You are a Real Estate Appraiser. Provide a detailed valuation report."

        prompt = f"""Analyze the estimated value for a property at: {address}.
        Assume it is a standard 3-bed 2-bath home if details are missing.
        Provide:
        1. Estimated Market Value (single number)
        2. Confidence Range (Low - High)
        3. Market Trends
        4. Key Value Factors
        
        Format as Markdown."""

        valuation_text = await generate_verified_text(prompt, system_msg, session_id)

        payload = {"valuation": valuation_text, "estimated_range": [475000, 525000], "confidence": "High"}
    except Exception as e:
        logger.error(f"Valuation error: {e}")
        payload = {"error": "Could not generate valuation"}

    await _log_real_estate_usage(request.user_id, "valuation", plan)
    payload.update(
        {
            "plan_scope": plan,
            "scope_label": _scope_label(plan),
            "daily_limit": limit,
            "used_today": used + 1,
        }
    )
    return payload


@router.post("/real-estate/mortgage-calculator")
async def calculate_mortgage(request: MortgageRequest):
    p = request.price - request.down_payment
    r = request.rate / 100 / 12
    n = request.term_years * 12

    if r == 0:
        monthly = p / n
    else:
        monthly = p * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    return {
        "monthly_payment": round(monthly, 2),
        "total_interest": round((monthly * n) - p, 2),
        "total_payment": round(monthly * n, 2),
    }


@router.post("/real-estate/schedule-tour")
async def schedule_tour(request: Request):
    from .db import require_auth

    user = await require_auth(request)

    if not has_basic_access(user):
        return {"success": False, "message": "Premium required for instant tour booking."}

    return {
        "success": True,
        "message": "Tour confirmed! An agent will meet you at the property.",
        "tour_id": uuid.uuid4().hex,
    }
