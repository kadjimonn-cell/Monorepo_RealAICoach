"""Travel Planner Pro - Enterprise-grade AI-powered travel planning platform.

Feature 11 rebuild scope:
- Trip management (create, organize, track)
- Multi-day itinerary builder with activities
- Budget planning and expense tracking
- Travel checklist automation
- AI itinerary generation
- AI destination recommendations
- AI packing list generator
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

from .db import db, get_current_user


logger = logging.getLogger("routes.travel_planner_pro")
router = APIRouter(prefix="/travel-planner-pro", tags=["travel-planner-pro"])
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")


TIER_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "trips_max": 2,
        "activities_per_trip": 10,
        "budgets_max": 2,
        "checklist_items": 20,
        "ai_generations_per_month": 5,
        "features": ["basic_planner", "checklist", "budget_tracking"],
    },
    "basic": {
        "trips_max": 15,
        "activities_per_trip": 50,
        "budgets_max": 15,
        "checklist_items": 100,
        "ai_generations_per_month": 30,
        "features": ["advanced_planner", "ai_recommendations", "multi_currency"],
    },
    "premium": {
        "trips_max": -1,
        "activities_per_trip": -1,
        "budgets_max": -1,
        "checklist_items": -1,
        "ai_generations_per_month": -1,
        "features": ["unlimited", "priority_ai", "advanced_analytics"],
    },
}


# ── Pydantic Models ──────────────────────────────────────────────────────────


class TripCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: str
    destination: str
    start_date: str
    end_date: str
    traveler_count: int = 1
    trip_type: str = "vacation"  # vacation, business, adventure
    budget_total: Optional[float] = None
    currency: str = "USD"
    notes: Optional[str] = None


class TripUpdate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    traveler_count: Optional[int] = None
    trip_type: Optional[str] = None
    budget_total: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ActivityCreate(BaseModel):
    time_slot: str  # morning, afternoon, evening
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    title: str
    location: Optional[str] = None
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    category: str = "activity"  # sightseeing, food, transport, accommodation, activity
    booking_status: str = "planned"
    notes: Optional[str] = None


class ItineraryDayCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    day_number: int
    date: str
    title: str
    activities: List[ActivityCreate] = []


class ActivityUpdate(BaseModel):
    fallback_user_id: Optional[str] = None
    time_slot: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    category: Optional[str] = None
    booking_status: Optional[str] = None
    notes: Optional[str] = None


class BudgetCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    total_budget: float
    currency: str = "USD"
    category_budgets: Optional[Dict[str, float]] = None


class ExpenseCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    amount: float
    currency: str = "USD"
    category: str
    description: str
    date: Optional[str] = None
    merchant: Optional[str] = None
    payment_method: Optional[str] = None


class ChecklistItemCreate(BaseModel):
    category: str  # documents, packing, tasks, misc
    title: str
    description: Optional[str] = None
    priority: str = "medium"  # high, medium, low
    due_date: Optional[str] = None


class ChecklistCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    items: List[ChecklistItemCreate] = []


class AIItineraryRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    destination: str
    num_days: int
    traveler_count: int = 1
    budget: Optional[float] = None
    currency: str = "USD"
    interests: Optional[List[str]] = None
    trip_type: str = "vacation"


class AIDestinationRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    budget: Optional[float] = None
    interests: Optional[List[str]] = None
    season: Optional[str] = None
    preferences: Optional[str] = None


class AIPackingListRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    destination: str
    num_days: int
    season: str
    activities: Optional[List[str]] = None


# ── Helper Functions ─────────────────────────────────────────────────────────


def _resolve_owner_id(user: Optional[dict], fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "travel_planner_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "travel_auth_required",
            "message": "Login required or provide fallback_user_id for guest workspace",
        },
    )


async def _get_user_tier(owner_id: str) -> str:
    """Get user subscription tier."""
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
    return effective if effective in TIER_LIMITS else "free"


async def _check_tier_limit(owner_id: str, tier: str, limit_key: str, current_count: int) -> bool:
    """Check if user has exceeded tier limit."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_limit = limits.get(limit_key, 0)
    if max_limit == -1:  # Unlimited
        return True
    return current_count < max_limit


async def _count_usage(owner_id: str, collection_name: str, filter_query: Optional[Dict] = None) -> int:
    """Count user's usage for a specific collection."""
    query = {"owner_id": owner_id}
    if filter_query:
        query.update(filter_query)
    count = await db[collection_name].count_documents(query)
    return count


async def _track_ai_usage(owner_id: str, query_type: str):
    """Track AI query usage for tier limits."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc).isoformat()
    
    await db.travel_ai_usage.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "month": month_key,
        "query_type": query_type,
        "query_at": now,
    })


# ── API Endpoints ────────────────────────────────────────────────────────────


@router.get("/bootstrap")
async def bootstrap(request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Initialize Travel Planner Pro workspace with tier limits and usage."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Count current usage
    trips_count = await _count_usage(owner_id, "travel_trips")
    budgets_count = await _count_usage(owner_id, "travel_budgets")
    
    # Get current month AI query count
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ai_query_count = await db.travel_ai_usage.count_documents({
        "owner_id": owner_id,
        "month": month_key
    })
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "limits": TIER_LIMITS[tier],
        "usage": {
            "trips_count": trips_count,
            "budgets_count": budgets_count,
            "ai_queries_this_month": ai_query_count,
        },
        "features_available": TIER_LIMITS[tier]["features"],
    }


# ── Trip Management ──────────────────────────────────────────────────────────


@router.post("/trips")
async def create_trip(payload: TripCreate, request: Request):
    """Create a new trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limits
    current_count = await _count_usage(owner_id, "travel_trips")
    if not await _check_tier_limit(owner_id, tier, "trips_max", current_count):
        raise HTTPException(
            status_code=403,
            detail=f"Trip limit reached for {tier} tier. Upgrade to create more trips."
        )
    
    trip_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    trip = {
        "id": trip_id,
        "owner_id": owner_id,
        "name": payload.name,
        "destination": payload.destination,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "traveler_count": payload.traveler_count,
        "trip_type": payload.trip_type,
        "status": "planning",
        "budget_total": payload.budget_total,
        "currency": payload.currency,
        "notes": payload.notes,
        "created_at": now,
        "updated_at": now,
    }
    
    await db.travel_trips.insert_one(trip)
    
    return {"trip_id": trip_id, "message": "Trip created successfully"}


@router.get("/trips")
async def get_trips(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Get all user trips."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    trips = await db.travel_trips.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    return {"trips": trips}


@router.get("/trips/{trip_id}")
async def get_trip(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get specific trip details."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    trip = await db.travel_trips.find_one(
        {"id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    return trip


@router.put("/trips/{trip_id}")
async def update_trip(trip_id: str, payload: TripUpdate, request: Request):
    """Update trip details."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.destination is not None:
        update_data["destination"] = payload.destination
    if payload.start_date is not None:
        update_data["start_date"] = payload.start_date
    if payload.end_date is not None:
        update_data["end_date"] = payload.end_date
    if payload.traveler_count is not None:
        update_data["traveler_count"] = payload.traveler_count
    if payload.trip_type is not None:
        update_data["trip_type"] = payload.trip_type
    if payload.budget_total is not None:
        update_data["budget_total"] = payload.budget_total
    if payload.currency is not None:
        update_data["currency"] = payload.currency
    if payload.notes is not None:
        update_data["notes"] = payload.notes
    if payload.status is not None:
        update_data["status"] = payload.status
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.travel_trips.update_one(
        {"id": trip_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    return {"message": "Trip updated successfully"}


@router.delete("/trips/{trip_id}")
async def delete_trip(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Delete a trip and all associated data."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.travel_trips.delete_one(
        {"id": trip_id, "owner_id": owner_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Clean up associated data
    await db.travel_itineraries.delete_many({"trip_id": trip_id})
    await db.travel_budgets.delete_many({"trip_id": trip_id})
    await db.travel_expenses.delete_many({"trip_id": trip_id})
    await db.travel_checklists.delete_many({"trip_id": trip_id})
    
    return {"message": "Trip deleted successfully"}


# ── Itinerary & Activities ───────────────────────────────────────────────────


@router.post("/trips/{trip_id}/itinerary")
async def create_itinerary_day(trip_id: str, payload: ItineraryDayCreate, request: Request):
    """Create a new day in the itinerary."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip exists and belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    day_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Process activities
    activities = []
    for act_data in payload.activities:
        activity = {
            "activity_id": str(uuid.uuid4()),
            "time_slot": act_data.time_slot,
            "start_time": act_data.start_time,
            "end_time": act_data.end_time,
            "title": act_data.title,
            "location": act_data.location,
            "description": act_data.description,
            "estimated_cost": act_data.estimated_cost,
            "category": act_data.category,
            "booking_status": act_data.booking_status,
            "notes": act_data.notes,
            "created_at": now,
        }
        activities.append(activity)
    
    itinerary_day = {
        "id": day_id,
        "trip_id": trip_id,
        "day_number": payload.day_number,
        "date": payload.date,
        "title": payload.title,
        "activities": activities,
        "created_at": now,
        "updated_at": now,
    }
    
    await db.travel_itineraries.insert_one(itinerary_day)
    
    return {"day_id": day_id, "message": "Itinerary day created successfully"}


@router.get("/trips/{trip_id}/itinerary")
async def get_itinerary(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get full itinerary for a trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    itinerary = await db.travel_itineraries.find(
        {"trip_id": trip_id},
        {"_id": 0}
    ).sort("day_number", 1).to_list(100)
    
    return {"trip_id": trip_id, "itinerary": itinerary}


@router.put("/trips/{trip_id}/itinerary/{day_id}")
async def update_itinerary_day(
    trip_id: str,
    day_id: str,
    payload: ItineraryDayCreate,
    request: Request
):
    """Update an itinerary day."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    update_data = {
        "title": payload.title,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.travel_itineraries.update_one(
        {"id": day_id, "trip_id": trip_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Itinerary day not found")
    
    return {"message": "Itinerary day updated successfully"}


@router.delete("/trips/{trip_id}/itinerary/{day_id}")
async def delete_itinerary_day(
    trip_id: str,
    day_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Delete an itinerary day."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    result = await db.travel_itineraries.delete_one(
        {"id": day_id, "trip_id": trip_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Itinerary day not found")
    
    return {"message": "Itinerary day deleted successfully"}


@router.post("/trips/{trip_id}/itinerary/{day_id}/activities")
async def add_activity(
    trip_id: str,
    day_id: str,
    activity: ActivityCreate,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Add an activity to an itinerary day."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Get itinerary day
    day = await db.travel_itineraries.find_one({"id": day_id, "trip_id": trip_id}, {"_id": 0})
    if not day:
        raise HTTPException(status_code=404, detail="Itinerary day not found")
    
    # Check tier limits for activities per trip
    total_activities = await db.travel_itineraries.aggregate([
        {"$match": {"trip_id": trip_id}},
        {"$unwind": "$activities"},
        {"$count": "total"}
    ]).to_list(1)
    
    current_activity_count = total_activities[0]["total"] if total_activities else 0
    if not await _check_tier_limit(owner_id, tier, "activities_per_trip", current_activity_count):
        raise HTTPException(
            status_code=403,
            detail=f"Activity limit reached for {tier} tier. Upgrade for more activities."
        )
    
    activity_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    new_activity = {
        "activity_id": activity_id,
        "time_slot": activity.time_slot,
        "start_time": activity.start_time,
        "end_time": activity.end_time,
        "title": activity.title,
        "location": activity.location,
        "description": activity.description,
        "estimated_cost": activity.estimated_cost,
        "category": activity.category,
        "booking_status": activity.booking_status,
        "notes": activity.notes,
        "created_at": now,
    }
    
    await db.travel_itineraries.update_one(
        {"id": day_id, "trip_id": trip_id},
        {
            "$push": {"activities": new_activity},
            "$set": {"updated_at": now}
        }
    )
    
    return {"activity_id": activity_id, "message": "Activity added successfully"}


@router.put("/trips/{trip_id}/activities/{activity_id}")
async def update_activity(
    trip_id: str,
    activity_id: str,
    payload: ActivityUpdate,
    request: Request
):
    """Update an activity."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Build update for array element
    update_fields = {}
    if payload.time_slot is not None:
        update_fields["activities.$.time_slot"] = payload.time_slot
    if payload.start_time is not None:
        update_fields["activities.$.start_time"] = payload.start_time
    if payload.end_time is not None:
        update_fields["activities.$.end_time"] = payload.end_time
    if payload.title is not None:
        update_fields["activities.$.title"] = payload.title
    if payload.location is not None:
        update_fields["activities.$.location"] = payload.location
    if payload.description is not None:
        update_fields["activities.$.description"] = payload.description
    if payload.estimated_cost is not None:
        update_fields["activities.$.estimated_cost"] = payload.estimated_cost
    if payload.category is not None:
        update_fields["activities.$.category"] = payload.category
    if payload.booking_status is not None:
        update_fields["activities.$.booking_status"] = payload.booking_status
    if payload.notes is not None:
        update_fields["activities.$.notes"] = payload.notes
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.travel_itineraries.update_one(
        {"trip_id": trip_id, "activities.activity_id": activity_id},
        {"$set": update_fields}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    return {"message": "Activity updated successfully"}


@router.delete("/trips/{trip_id}/activities/{activity_id}")
async def delete_activity(
    trip_id: str,
    activity_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Delete an activity."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    result = await db.travel_itineraries.update_one(
        {"trip_id": trip_id},
        {
            "$pull": {"activities": {"activity_id": activity_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    return {"message": "Activity deleted successfully"}


# ── Budget Management ────────────────────────────────────────────────────────


@router.post("/trips/{trip_id}/budget")
async def create_budget(trip_id: str, payload: BudgetCreate, request: Request):
    """Create a budget for a trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Check tier limits
    current_count = await _count_usage(owner_id, "travel_budgets")
    if not await _check_tier_limit(owner_id, tier, "budgets_max", current_count):
        raise HTTPException(
            status_code=403,
            detail=f"Budget limit reached for {tier} tier. Upgrade to create more budgets."
        )
    
    budget_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Default category budgets if not provided
    category_budgets = payload.category_budgets or {
        "accommodation": payload.total_budget * 0.4,
        "food": payload.total_budget * 0.25,
        "transport": payload.total_budget * 0.15,
        "activities": payload.total_budget * 0.15,
        "shopping": payload.total_budget * 0.05,
    }
    
    budget = {
        "id": budget_id,
        "trip_id": trip_id,
        "owner_id": owner_id,
        "total_budget": payload.total_budget,
        "currency": payload.currency,
        "category_budgets": category_budgets,
        "spent_total": 0.0,
        "remaining": payload.total_budget,
        "created_at": now,
        "updated_at": now,
    }
    
    await db.travel_budgets.insert_one(budget)
    
    return {"budget_id": budget_id, "message": "Budget created successfully"}


@router.get("/trips/{trip_id}/budget")
async def get_budget(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get budget for a trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    budget = await db.travel_budgets.find_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not budget:
        return {"budget": None, "message": "No budget created for this trip"}
    
    return {"budget": budget}


@router.put("/trips/{trip_id}/budget")
async def update_budget(trip_id: str, payload: BudgetCreate, request: Request):
    """Update trip budget."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    update_data = {
        "total_budget": payload.total_budget,
        "currency": payload.currency,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if payload.category_budgets:
        update_data["category_budgets"] = payload.category_budgets
    
    result = await db.travel_budgets.update_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    return {"message": "Budget updated successfully"}


@router.post("/trips/{trip_id}/expenses")
async def log_expense(trip_id: str, payload: ExpenseCreate, request: Request):
    """Log an expense for a trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Get budget
    budget = await db.travel_budgets.find_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    expense_id = str(uuid.uuid4())
    expense_date = payload.date or datetime.now(timezone.utc).isoformat()
    
    expense = {
        "id": expense_id,
        "trip_id": trip_id,
        "budget_id": budget["id"] if budget else None,
        "owner_id": owner_id,
        "amount": payload.amount,
        "currency": payload.currency,
        "category": payload.category,
        "description": payload.description,
        "date": expense_date,
        "merchant": payload.merchant,
        "payment_method": payload.payment_method,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.travel_expenses.insert_one(expense)
    
    # Update budget spent amount
    if budget:
        await db.travel_budgets.update_one(
            {"id": budget["id"]},
            {
                "$inc": {"spent_total": payload.amount},
                "$set": {
                    "remaining": budget["total_budget"] - (budget["spent_total"] + payload.amount),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    
    return {
        "expense_id": expense_id,
        "message": "Expense logged successfully"
    }


@router.get("/trips/{trip_id}/expenses")
async def get_expenses(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get all expenses for a trip."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    expenses = await db.travel_expenses.find(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    ).sort("date", -1).to_list(1000)
    
    # Calculate category totals
    category_totals = {}
    for expense in expenses:
        cat = expense["category"]
        category_totals[cat] = category_totals.get(cat, 0) + expense["amount"]
    
    return {
        "trip_id": trip_id,
        "expenses": expenses,
        "category_totals": category_totals,
        "total_spent": sum(e["amount"] for e in expenses)
    }


# ── Travel Checklist ─────────────────────────────────────────────────────────


@router.post("/trips/{trip_id}/checklist")
async def create_checklist(trip_id: str, payload: ChecklistCreate, request: Request):
    """Create or add items to trip checklist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Check if checklist already exists
    existing = await db.travel_checklists.find_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    now = datetime.now(timezone.utc).isoformat()
    
    if existing:
        # Add items to existing checklist
        new_items = []
        for item_data in payload.items:
            item = {
                "item_id": str(uuid.uuid4()),
                "category": item_data.category,
                "title": item_data.title,
                "description": item_data.description,
                "completed": False,
                "priority": item_data.priority,
                "due_date": item_data.due_date,
                "created_at": now,
            }
            new_items.append(item)
        
        await db.travel_checklists.update_one(
            {"trip_id": trip_id, "owner_id": owner_id},
            {
                "$push": {"items": {"$each": new_items}},
                "$set": {"updated_at": now}
            }
        )
        
        return {"message": "Checklist items added successfully"}
    
    else:
        # Create new checklist
        checklist_id = str(uuid.uuid4())
        
        items = []
        for item_data in payload.items:
            item = {
                "item_id": str(uuid.uuid4()),
                "category": item_data.category,
                "title": item_data.title,
                "description": item_data.description,
                "completed": False,
                "priority": item_data.priority,
                "due_date": item_data.due_date,
                "created_at": now,
            }
            items.append(item)
        
        checklist = {
            "id": checklist_id,
            "trip_id": trip_id,
            "owner_id": owner_id,
            "items": items,
            "created_at": now,
            "updated_at": now,
        }
        
        await db.travel_checklists.insert_one(checklist)
        
        return {"checklist_id": checklist_id, "message": "Checklist created successfully"}


@router.get("/trips/{trip_id}/checklist")
async def get_checklist(
    trip_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get trip checklist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    checklist = await db.travel_checklists.find_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not checklist:
        return {"checklist": None, "message": "No checklist created for this trip"}
    
    # Calculate completion stats
    total_items = len(checklist.get("items", []))
    completed_items = sum(1 for item in checklist.get("items", []) if item.get("completed"))
    
    return {
        "checklist": checklist,
        "stats": {
            "total_items": total_items,
            "completed_items": completed_items,
            "completion_pct": (completed_items / total_items * 100) if total_items > 0 else 0
        }
    }


@router.put("/trips/{trip_id}/checklist/{item_id}")
async def toggle_checklist_item(
    trip_id: str,
    item_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Toggle checklist item completion status."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Get current item status
    checklist = await db.travel_checklists.find_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist not found")
    
    # Find item and toggle
    item = next((i for i in checklist.get("items", []) if i["item_id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    
    new_status = not item.get("completed", False)
    
    result = await db.travel_checklists.update_one(
        {"trip_id": trip_id, "owner_id": owner_id, "items.item_id": item_id},
        {
            "$set": {
                "items.$.completed": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    
    return {"message": "Checklist item updated", "completed": new_status}


@router.delete("/trips/{trip_id}/checklist/{item_id}")
async def delete_checklist_item(
    trip_id: str,
    item_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Delete a checklist item."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify trip belongs to user
    trip = await db.travel_trips.find_one({"id": trip_id, "owner_id": owner_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    result = await db.travel_checklists.update_one(
        {"trip_id": trip_id, "owner_id": owner_id},
        {
            "$pull": {"items": {"item_id": item_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    
    return {"message": "Checklist item deleted"}


# ── AI Features ──────────────────────────────────────────────────────────────


@router.post("/ai/generate-itinerary")
async def ai_generate_itinerary(payload: AIItineraryRequest, request: Request):
    """Generate AI-powered trip itinerary."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check AI usage limit
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    current_usage = await db.travel_ai_usage.count_documents({
        "owner_id": owner_id,
        "month": month_key
    })
    
    if not await _check_tier_limit(owner_id, tier, "ai_generations_per_month", current_usage):
        raise HTTPException(
            status_code=403,
            detail=f"AI generation limit reached for {tier} tier. Upgrade for more queries."
        )
    
    # Track usage
    await _track_ai_usage(owner_id, "itinerary")
    
    interests_text = ", ".join(payload.interests) if payload.interests else "general sightseeing"
    budget_text = f"${payload.budget} {payload.currency}" if payload.budget else "flexible budget"
    
    prompt = f"""You are a travel planning expert. Generate a detailed {payload.num_days}-day itinerary for:

Destination: {payload.destination}
Travelers: {payload.traveler_count} people
Budget: {budget_text}
Interests: {interests_text}
Trip Type: {payload.trip_type}

For each day, provide:
1. Day title and theme
2. Morning activity (9 AM - 12 PM) with location and estimated cost
3. Afternoon activity (1 PM - 5 PM) with location and estimated cost
4. Evening activity (6 PM - 9 PM) with location and estimated cost
5. Daily budget breakdown
6. Travel tips for that day

Format as a clear, structured itinerary with specific recommendations."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"travel-itinerary-{uuid.uuid4().hex[:10]}",
                system_message="You are a professional travel planning assistant. Create detailed, practical itineraries."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "itinerary": response,
            "destination": payload.destination,
            "num_days": payload.num_days
        }
    except Exception as e:
        logger.error(f"AI itinerary generation failed: {e}")
        raise HTTPException(status_code=500, detail="AI generation failed")


@router.post("/ai/destination-recommend")
async def ai_destination_recommend(payload: AIDestinationRequest, request: Request):
    """Get AI destination recommendations."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check AI usage limit
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    current_usage = await db.travel_ai_usage.count_documents({
        "owner_id": owner_id,
        "month": month_key
    })
    
    if not await _check_tier_limit(owner_id, tier, "ai_generations_per_month", current_usage):
        raise HTTPException(
            status_code=403,
            detail=f"AI generation limit reached for {tier} tier. Upgrade for more queries."
        )
    
    # Track usage
    await _track_ai_usage(owner_id, "destination")
    
    interests_text = ", ".join(payload.interests) if payload.interests else "diverse experiences"
    budget_text = f"Budget: ${payload.budget}" if payload.budget else "Flexible budget"
    season_text = f"Season: {payload.season}" if payload.season else "Any season"
    
    prompt = f"""Recommend 5 amazing travel destinations based on:

{budget_text}
Interests: {interests_text}
{season_text}
{payload.preferences or ''}

For each destination provide:
- Name and country
- Why it's a perfect match for these preferences
- Best time to visit
- Estimated trip budget
- Top 3 must-see attractions
- Unique travel tip

Be specific and practical with your recommendations."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"travel-destination-{uuid.uuid4().hex[:10]}",
                system_message="You are a destination recommendation expert. Provide specific, actionable travel suggestions."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "recommendations": response,
            "query": {
                "budget": payload.budget,
                "interests": payload.interests,
                "season": payload.season
            }
        }
    except Exception as e:
        logger.error(f"AI destination recommendation failed: {e}")
        raise HTTPException(status_code=500, detail="AI recommendation failed")


@router.post("/ai/packing-list")
async def ai_packing_list(payload: AIPackingListRequest, request: Request):
    """Generate AI-powered packing list."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check AI usage limit
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    current_usage = await db.travel_ai_usage.count_documents({
        "owner_id": owner_id,
        "month": month_key
    })
    
    if not await _check_tier_limit(owner_id, tier, "ai_generations_per_month", current_usage):
        raise HTTPException(
            status_code=403,
            detail=f"AI generation limit reached for {tier} tier. Upgrade for more queries."
        )
    
    # Track usage
    await _track_ai_usage(owner_id, "packing")
    
    activities_text = ", ".join(payload.activities) if payload.activities else "general tourism"
    
    prompt = f"""Generate a comprehensive packing list for:

Destination: {payload.destination}
Duration: {payload.num_days} days
Season/Weather: {payload.season}
Activities planned: {activities_text}

Categorize items into:
1. **Documents** (passport, tickets, insurance, etc.)
2. **Clothing** (weather-appropriate, activity-specific)
3. **Toiletries** (essentials and travel-sized items)
4. **Electronics** (chargers, adapters, devices)
5. **Miscellaneous** (medications, first aid, etc.)

Mark essential items as **HIGH PRIORITY**.
Include destination-specific items (e.g., plug adapters for Europe).
Be practical and comprehensive."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"travel-packing-{uuid.uuid4().hex[:10]}",
                system_message="You are a packing list specialist. Create comprehensive, organized packing lists."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "packing_list": response,
            "destination": payload.destination,
            "num_days": payload.num_days
        }
    except Exception as e:
        logger.error(f"AI packing list generation failed: {e}")
        raise HTTPException(status_code=500, detail="AI generation failed")
