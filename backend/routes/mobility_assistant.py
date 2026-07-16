"""
Feature 13: Mobility Assistant
Route prefix: /mobility-assistant
Feature ID:   smart-cars

18 endpoints across 12 feature domains:
  Bootstrap, Vehicle Search, Trade-In, Finance, Saved Vehicles,
  Maintenance Schedule, Cost Calculator, Trip Planner, Comparison,
  EV Advisor, Service History, Sessions, Analytics
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .db import db, get_current_user
from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/mobility-assistant", tags=["Mobility Assistant"])

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ── Tier limits ───────────────────────────────────────────────────────────────

TIER_LIMITS = {
    "free": {
        "searches_per_month": 5,
        "ai_calls_per_month": 3,
        "saved_vehicles": 3,
        "service_records": 5,
    },
    "basic": {
        "searches_per_month": 30,
        "ai_calls_per_month": 20,
        "saved_vehicles": 20,
        "service_records": 50,
    },
    "premium": {
        "searches_per_month": -1,
        "ai_calls_per_month": -1,
        "saved_vehicles": -1,
        "service_records": -1,
    },
}

# ── Pydantic models ───────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    max_mileage: Optional[int] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    vehicle_type: Optional[str] = "any"
    fallback_user_id: Optional[str] = None


class TradeInRequest(BaseModel):
    make: str
    model: str
    year: int
    mileage: int
    condition: str
    zip_code: Optional[str] = None
    fallback_user_id: Optional[str] = None


class FinanceRequest(BaseModel):
    vehicle_price: float
    down_payment: float
    loan_term_months: int = 60
    credit_score_range: str = "good"
    fallback_user_id: Optional[str] = None


class SaveVehicleRequest(BaseModel):
    listing_id: str
    make: str
    model: str
    year: int
    price: int
    mileage: Optional[int] = None
    trim: Optional[str] = None
    dealer_rating: Optional[float] = None
    notes: Optional[str] = None
    fallback_user_id: Optional[str] = None


class MaintenanceRequest(BaseModel):
    make: str
    model: str
    year: int
    current_mileage: int
    last_service_mileage: Optional[int] = None
    fallback_user_id: Optional[str] = None


class CostCalculatorRequest(BaseModel):
    make: str
    model: str
    year: int
    purchase_price: int
    annual_mileage: int = 12000
    fuel_type: str = "gasoline"
    mpg: Optional[float] = None
    fallback_user_id: Optional[str] = None


class TripPlannerRequest(BaseModel):
    origin: str
    destination: str
    make: str
    model: str
    year: int
    fuel_type: str = "gasoline"
    mpg: Optional[float] = None
    fallback_user_id: Optional[str] = None


class CompareRequest(BaseModel):
    vehicle_a: str
    vehicle_b: str
    priorities: Optional[List[str]] = None
    fallback_user_id: Optional[str] = None


class EvAdvisorRequest(BaseModel):
    current_vehicle: str
    annual_mileage: int = 12000
    daily_commute_miles: Optional[int] = None
    home_charging: bool = True
    budget: Optional[int] = None
    fallback_user_id: Optional[str] = None


class DrivingInsightsRequest(BaseModel):
    vehicle: str
    driving_habits: str
    annual_mileage: Optional[int] = None
    concerns: Optional[str] = None
    fallback_user_id: Optional[str] = None


class ServiceRecordRequest(BaseModel):
    make: str
    model: str
    year: int
    service_type: str
    mileage_at_service: int
    cost: Optional[float] = None
    shop_name: Optional[str] = None
    notes: Optional[str] = None
    service_date: Optional[str] = None
    fallback_user_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"
    if not fallback_user_id:
        raise HTTPException(status_code=401, detail={"error": "auth_required", "message": "Login required or provide fallback_user_id"})
    if not GUEST_ID_RE.match(fallback_user_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_guest_id", "message": "fallback_user_id must match ^user_[a-zA-Z0-9_-]{12,80}$"})
    return f"guest:{fallback_user_id}"


async def _get_tier(owner_id: str) -> str:
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
    effective = compute_effective_plan(user_doc or {})
    if effective in TIER_LIMITS:
        return effective
    return "free"


async def _check_limit(owner_id: str, tier: str, action: str) -> None:
    limit = TIER_LIMITS[tier].get(action, 0)
    if limit == -1:
        return
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.mobility_usage_log.count_documents({"owner_id": owner_id, "action": action, "created_at": {"$gte": month_start}})
    if used >= limit:
        raise HTTPException(status_code=403, detail={"error": "tier_limit_reached", "message": f"Monthly {action} limit ({limit}) reached. Upgrade to continue."})


async def _log_usage(owner_id: str, action: str) -> None:
    await db.mobility_usage_log.insert_one({"owner_id": owner_id, "action": action, "created_at": datetime.now(timezone.utc).isoformat()})


def _llm(session_id: str, system_msg: str) -> LlmChat:
    return LlmChat(api_key=EMERGENT_KEY, session_id=session_id, system_message=system_msg).with_model("openai", "gpt-4o")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/bootstrap")
async def bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_tier(owner_id)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    searches_used = await db.mobility_usage_log.count_documents({"owner_id": owner_id, "action": "searches_per_month", "created_at": {"$gte": month_start}})
    ai_used = await db.mobility_usage_log.count_documents({"owner_id": owner_id, "action": "ai_calls_per_month", "created_at": {"$gte": month_start}})
    saved_count = await db.mobility_saved_vehicles.count_documents({"owner_id": owner_id})
    service_count = await db.mobility_service_records.count_documents({"owner_id": owner_id})

    return {
        "owner_id": owner_id,
        "tier": tier,
        "limits": TIER_LIMITS[tier],
        "usage": {
            "searches_this_month": searches_used,
            "ai_calls_this_month": ai_used,
            "saved_vehicles": saved_count,
            "service_records": service_count,
        },
    }


# ── Vehicle Search ─────────────────────────────────────────────────────────────

@router.post("/search")
async def search_vehicles(payload: SearchRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "searches_per_month")

    filters = []
    if payload.make:
        filters.append(f"Make: {payload.make}")
    if payload.model:
        filters.append(f"Model: {payload.model}")
    if payload.min_price:
        filters.append(f"Min price: ${payload.min_price:,}")
    if payload.max_price:
        filters.append(f"Max price: ${payload.max_price:,}")
    if payload.max_mileage:
        filters.append(f"Max mileage: {payload.max_mileage:,} miles")
    if payload.year_from or payload.year_to:
        filters.append(f"Year range: {payload.year_from or 2015}–{payload.year_to or 2025}")
    if payload.vehicle_type and payload.vehicle_type != "any":
        filters.append(f"Type: {payload.vehicle_type}")

    filter_str = "\n".join(filters) if filters else "No specific filters (show popular options)"

    prompt = f"""Generate 8 realistic used vehicle listings matching these criteria:
{filter_str}

For each listing return a JSON object with:
- listing_id (unique string like "car_abc123")
- make, model, year (int), trim
- price (int, realistic market value)
- mileage (int)
- vehicle_type (sedan/suv/truck/sport/luxury/ev)
- deal_rating (Great Deal / Good Deal / Fair Deal)
- dealer_rating (float 3.5–5.0)
- location (US city, state)
- history_clean (bool)
- key_features (list of 3 strings)

Return a JSON array of exactly 8 objects. No markdown."""

    try:
        chat = _llm(f"ma-search-{uuid4().hex[:10]}", "You are an automotive inventory expert. Return ONLY valid JSON arrays.")
        response = await chat.send_message(UserMessage(text=prompt))
        text = str(response).strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        import json as _json
        listings = _json.loads(text)
        if not isinstance(listings, list):
            listings = []
    except Exception:
        listings = []

    # Save search to history
    search_id = f"srch_{uuid4().hex[:12]}"
    await db.mobility_search_history.insert_one({
        "search_id": search_id,
        "owner_id": owner_id,
        "filters": {k: v for k, v in payload.dict().items() if v and k != "fallback_user_id"},
        "results_count": len(listings),
        "created_at": _now(),
    })
    await _log_usage(owner_id, "searches_per_month")

    return {"search_id": search_id, "listings": listings, "count": len(listings), "tier": tier}


@router.get("/search/history")
async def get_search_history(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    history = await db.mobility_search_history.find({"owner_id": owner_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"history": history}


# ── Trade-In ───────────────────────────────────────────────────────────────────

@router.post("/trade-in")
async def estimate_trade_in(payload: TradeInRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Provide a detailed trade-in valuation for:
{payload.year} {payload.make} {payload.model}
Mileage: {payload.mileage:,} miles
Condition: {payload.condition}
Location: {payload.zip_code or "US average"}

Return a detailed professional appraisal covering:
1. Trade-In Value range (low/mid/high estimates)
2. Private Party Value
3. Dealer Retail Value
4. Factors affecting this valuation (mileage, condition, market demand, depreciation)
5. Tips to increase trade-in value
6. Best time/place to trade in

Be specific with dollar amounts based on real market knowledge."""

    try:
        chat = _llm(f"ma-tradein-{uuid4().hex[:10]}", "You are a senior auto appraiser with 20 years of market expertise.")
        valuation = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Valuation failed: {str(e)}")

    record = {
        "valuation_id": f"val_{uuid4().hex[:12]}",
        "owner_id": owner_id,
        "make": payload.make,
        "model": payload.model,
        "year": payload.year,
        "mileage": payload.mileage,
        "condition": payload.condition,
        "valuation": valuation,
        "created_at": _now(),
    }
    rec_copy = {**record}
    await db.mobility_trade_ins.insert_one(rec_copy)
    await _log_usage(owner_id, "ai_calls_per_month")
    return record


# ── Finance Calculator ─────────────────────────────────────────────────────────

@router.post("/finance")
async def finance_calculator(payload: FinanceRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    # Local calculation
    credit_rates = {"excellent": 4.5, "good": 6.5, "fair": 10.5, "poor": 16.5}
    apr = credit_rates.get(payload.credit_score_range.lower(), 6.5)
    principal = payload.vehicle_price - payload.down_payment
    monthly_rate = apr / 100 / 12
    n = payload.loan_term_months
    if monthly_rate > 0:
        monthly_payment = round(principal * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1), 2)
    else:
        monthly_payment = round(principal / n, 2)
    total_paid = round(monthly_payment * n, 2)
    total_interest = round(total_paid - principal, 2)

    prompt = f"""A buyer is financing a vehicle at:
- Vehicle price: ${payload.vehicle_price:,.0f}
- Down payment: ${payload.down_payment:,.0f}
- Loan term: {payload.loan_term_months} months
- Credit score range: {payload.credit_score_range}
- Estimated APR: {apr}%
- Calculated monthly payment: ${monthly_payment:,.2f}

Provide:
1. Assessment of this financing deal (is it good/average/expensive?)
2. Tips to lower the monthly payment
3. Whether to extend or shorten the term
4. Any hidden costs to watch for (gap insurance, dealer fees, extended warranty upsells)
5. When to consider leasing instead"""

    try:
        chat = _llm(f"ma-finance-{uuid4().hex[:10]}", "You are an expert automotive finance advisor.")
        ai_advice = await chat.send_message(UserMessage(text=prompt))
    except Exception:
        ai_advice = "AI advice unavailable. Review the calculated figures above."

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "vehicle_price": payload.vehicle_price,
        "down_payment": payload.down_payment,
        "loan_amount": principal,
        "apr_percent": apr,
        "loan_term_months": n,
        "monthly_payment": monthly_payment,
        "total_paid": total_paid,
        "total_interest": total_interest,
        "ai_advice": ai_advice,
    }


# ── Saved Vehicles ─────────────────────────────────────────────────────────────

@router.post("/saved-vehicles")
async def save_vehicle(payload: SaveVehicleRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    limit = TIER_LIMITS[tier]["saved_vehicles"]
    if limit != -1:
        current = await db.mobility_saved_vehicles.count_documents({"owner_id": owner_id})
        if current >= limit:
            raise HTTPException(status_code=403, detail={"error": "tier_limit_reached", "message": f"Saved vehicle limit ({limit}) reached. Upgrade to save more."})

    vehicle_id = f"sv_{uuid4().hex[:12]}"
    doc = {
        "vehicle_id": vehicle_id,
        "owner_id": owner_id,
        "listing_id": payload.listing_id,
        "make": payload.make,
        "model": payload.model,
        "year": payload.year,
        "price": payload.price,
        "mileage": payload.mileage,
        "trim": payload.trim,
        "dealer_rating": payload.dealer_rating,
        "notes": payload.notes,
        "saved_at": _now(),
    }
    doc_copy = {**doc}
    await db.mobility_saved_vehicles.insert_one(doc_copy)
    return {"vehicle_id": vehicle_id, "message": "Vehicle saved successfully"}


@router.get("/saved-vehicles")
async def list_saved_vehicles(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    vehicles = await db.mobility_saved_vehicles.find({"owner_id": owner_id}, {"_id": 0}).sort("saved_at", -1).to_list(50)
    return {"vehicles": vehicles, "count": len(vehicles)}


@router.delete("/saved-vehicles/{vehicle_id}")
async def delete_saved_vehicle(vehicle_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    result = await db.mobility_saved_vehicles.delete_one({"vehicle_id": vehicle_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {"message": "Vehicle removed", "vehicle_id": vehicle_id}


# ── Maintenance Schedule ───────────────────────────────────────────────────────

@router.post("/maintenance-schedule")
async def get_maintenance_schedule(payload: MaintenanceRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Create a complete maintenance schedule for:
{payload.year} {payload.make} {payload.model}
Current mileage: {payload.current_mileage:,} miles
Last service at: {f"{payload.last_service_mileage:,} miles" if payload.last_service_mileage else "Unknown"}

Include:
1. Immediate needs (overdue maintenance)
2. Due soon (within next 3,000 miles)
3. Upcoming schedule (next 12 months)
4. Long-term milestones (30k, 60k, 90k, 100k mile services)
5. Estimated costs for each service
6. DIY vs shop recommendations for each item
7. Brand-specific reliability notes for this model"""

    try:
        chat = _llm(f"ma-maint-{uuid4().hex[:10]}", "You are a master automotive technician and maintenance planner.")
        schedule = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Maintenance schedule failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "vehicle": f"{payload.year} {payload.make} {payload.model}",
        "current_mileage": payload.current_mileage,
        "maintenance_schedule": schedule,
    }


# ── Cost & Fuel Calculator ─────────────────────────────────────────────────────

@router.post("/cost-calculator")
async def calculate_ownership_cost(payload: CostCalculatorRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Calculate the total 5-year cost of ownership for:
{payload.year} {payload.make} {payload.model}
Purchase price: ${payload.purchase_price:,}
Annual mileage: {payload.annual_mileage:,} miles
Fuel type: {payload.fuel_type}
{f"Fuel economy: {payload.mpg} MPG" if payload.mpg else ""}

Provide a detailed breakdown including:
1. Depreciation (year-by-year value loss)
2. Fuel costs (use current average fuel prices)
3. Insurance estimate (national average for this vehicle class)
4. Maintenance & repairs (scheduled + unexpected)
5. Registration/taxes
6. Total 5-year cost of ownership
7. Monthly average all-in cost
8. Cost per mile
9. How this compares to similar vehicles in its class"""

    try:
        chat = _llm(f"ma-cost-{uuid4().hex[:10]}", "You are an automotive financial analyst specializing in total cost of ownership.")
        analysis = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cost calculation failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "vehicle": f"{payload.year} {payload.make} {payload.model}",
        "purchase_price": payload.purchase_price,
        "annual_mileage": payload.annual_mileage,
        "cost_analysis": analysis,
    }


# ── Trip Planner ───────────────────────────────────────────────────────────────

@router.post("/trip-planner")
async def plan_trip(payload: TripPlannerRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Plan a road trip:
From: {payload.origin}
To: {payload.destination}
Vehicle: {payload.year} {payload.make} {payload.model}
Fuel type: {payload.fuel_type}
{f"Fuel economy: {payload.mpg} MPG" if payload.mpg else ""}

Provide:
1. Estimated distance and driving time
2. Fuel cost estimate (use current average prices)
3. Recommended fuel stops and rest breaks
4. Route options (scenic vs fastest vs most fuel-efficient)
5. Vehicle-specific tips for this trip length
6. Weather/season considerations
7. Emergency preparedness checklist
8. Total trip cost estimate including food/lodging if overnight"""

    try:
        chat = _llm(f"ma-trip-{uuid4().hex[:10]}", "You are an expert road trip planner and automotive advisor.")
        plan = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trip planning failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "origin": payload.origin,
        "destination": payload.destination,
        "vehicle": f"{payload.year} {payload.make} {payload.model}",
        "trip_plan": plan,
    }


# ── Vehicle Comparison ─────────────────────────────────────────────────────────

@router.post("/compare")
async def compare_vehicles(payload: CompareRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    priorities_str = ", ".join(payload.priorities) if payload.priorities else "reliability, value, fuel economy, safety"

    prompt = f"""Compare these two vehicles head-to-head:
Vehicle A: {payload.vehicle_a}
Vehicle B: {payload.vehicle_b}
Buyer priorities: {priorities_str}

Provide a structured comparison covering:
1. Overall recommendation (which to buy and why)
2. Score card (rate each 1-10): Reliability, Value for Money, Fuel Economy, Safety, Comfort, Performance, Cargo Space, Technology
3. Vehicle A strengths and weaknesses
4. Vehicle B strengths and weaknesses
5. Who Vehicle A is best for (buyer persona)
6. Who Vehicle B is best for (buyer persona)
7. Long-term ownership considerations (reliability history, parts cost, resale value)
8. Final verdict based on stated priorities"""

    try:
        chat = _llm(f"ma-compare-{uuid4().hex[:10]}", "You are a professional automotive journalist and consumer advisor.")
        comparison = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "vehicle_a": payload.vehicle_a,
        "vehicle_b": payload.vehicle_b,
        "priorities": payload.priorities,
        "comparison": comparison,
    }


# ── EV Advisor ─────────────────────────────────────────────────────────────────

@router.post("/ev-advisor")
async def ev_advisor(payload: EvAdvisorRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Advise this driver on switching to an EV:
Current vehicle: {payload.current_vehicle}
Annual mileage: {payload.annual_mileage:,} miles
Daily commute: {f"{payload.daily_commute_miles} miles" if payload.daily_commute_miles else "Not specified"}
Home charging available: {"Yes" if payload.home_charging else "No"}
Budget: {f"${payload.budget:,}" if payload.budget else "Not specified"}

Provide:
1. Should they switch to EV? (clear yes/no/maybe with reasoning)
2. Annual fuel savings estimate vs their current vehicle
3. Upfront cost difference and payback period
4. Top 3 EV recommendations that fit their profile and budget
5. Range anxiety assessment for their driving pattern
6. Charging infrastructure considerations in their use case
7. Federal/state incentives currently available
8. Best time to make the switch (market timing)"""

    try:
        chat = _llm(f"ma-ev-{uuid4().hex[:10]}", "You are an EV adoption expert and automotive sustainability consultant.")
        advice = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EV advisory failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "current_vehicle": payload.current_vehicle,
        "annual_mileage": payload.annual_mileage,
        "ev_advice": advice,
    }


# ── Driving Insights ───────────────────────────────────────────────────────────

@router.post("/driving-insights")
async def get_driving_insights(payload: DrivingInsightsRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    await _check_limit(owner_id, tier, "ai_calls_per_month")

    prompt = f"""Analyze driving habits and provide efficiency recommendations:
Vehicle: {payload.vehicle}
Driving habits: {payload.driving_habits}
Annual mileage: {f"{payload.annual_mileage:,} miles" if payload.annual_mileage else "Not specified"}
Main concerns: {payload.concerns or "General efficiency improvement"}

Provide:
1. Top 5 fuel-saving driving techniques for this vehicle
2. Habit changes with estimated fuel savings (% improvement)
3. Optimal tire pressure and its impact on efficiency
4. Acceleration and braking patterns to improve
5. Highway vs city driving optimization tips
6. Seasonal driving adjustments
7. Estimated annual savings if all tips are followed
8. Vehicle-specific eco mode or efficiency features to use"""

    try:
        chat = _llm(f"ma-insights-{uuid4().hex[:10]}", "You are a driving efficiency coach and automotive performance expert.")
        insights = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Driving insights failed: {str(e)}")

    await _log_usage(owner_id, "ai_calls_per_month")
    return {
        "vehicle": payload.vehicle,
        "driving_habits": payload.driving_habits,
        "insights": insights,
    }


# ── Service History ────────────────────────────────────────────────────────────

@router.post("/service-history")
async def add_service_record(payload: ServiceRecordRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    limit = TIER_LIMITS[tier]["service_records"]
    if limit != -1:
        current = await db.mobility_service_records.count_documents({"owner_id": owner_id})
        if current >= limit:
            raise HTTPException(status_code=403, detail={"error": "tier_limit_reached", "message": f"Service record limit ({limit}) reached. Upgrade to log more."})

    record_id = f"sr_{uuid4().hex[:12]}"
    doc = {
        "record_id": record_id,
        "owner_id": owner_id,
        "make": payload.make,
        "model": payload.model,
        "year": payload.year,
        "service_type": payload.service_type,
        "mileage_at_service": payload.mileage_at_service,
        "cost": payload.cost,
        "shop_name": payload.shop_name,
        "notes": payload.notes,
        "service_date": payload.service_date or _now()[:10],
        "logged_at": _now(),
    }
    doc_copy = {**doc}
    await db.mobility_service_records.insert_one(doc_copy)
    return {"record_id": record_id, "message": "Service record added"}


@router.get("/service-history")
async def list_service_history(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    records = await db.mobility_service_records.find({"owner_id": owner_id}, {"_id": 0}).sort("service_date", -1).to_list(100)
    return {"records": records, "count": len(records)}


# ── Sessions & Analytics ───────────────────────────────────────────────────────

@router.get("/sessions")
async def get_sessions(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    sessions = await db.mobility_usage_log.find(
        {"owner_id": owner_id},
        {"_id": 0, "action": 1, "created_at": 1}
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/analytics")
async def get_analytics(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    saved_count = await db.mobility_saved_vehicles.count_documents({"owner_id": owner_id})
    service_count = await db.mobility_service_records.count_documents({"owner_id": owner_id})
    search_count = await db.mobility_search_history.count_documents({"owner_id": owner_id})
    tradein_count = await db.mobility_trade_ins.count_documents({"owner_id": owner_id})

    ai_actions = ["ai_calls_per_month"]
    total_ai = await db.mobility_usage_log.count_documents({"owner_id": owner_id, "action": {"$in": ai_actions}})

    return {
        "total_searches": search_count,
        "total_trade_in_requests": tradein_count,
        "total_ai_calls": total_ai,
        "saved_vehicles": saved_count,
        "service_records": service_count,
    }
