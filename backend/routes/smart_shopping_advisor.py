"""Smart Shopping Advisor - Enterprise-grade shopping intelligence platform.

Feature 10 rebuild scope:
- Wishlist management with price tracking
- Price alert engine
- AI product comparison and recommendations
- Shopping budget tracker with analytics
- Deal and coupon finder
- Carbon footprint calculator
- Purchase history and insights
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

from .db import db, get_current_user


logger = logging.getLogger("routes.smart_shopping_advisor")
router = APIRouter(prefix="/smart-shopping-advisor", tags=["smart-shopping-advisor"])
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")


TIER_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "wishlists_max": 3,
        "wishlist_items_max": 10,
        "price_alerts_max": 5,
        "budgets_max": 2,
        "ai_queries_per_month": 10,
        "features": ["basic_wishlist", "price_tracking", "basic_budget"],
    },
    "basic": {
        "wishlists_max": 15,
        "wishlist_items_max": 100,
        "price_alerts_max": 30,
        "budgets_max": 10,
        "ai_queries_per_month": 50,
        "features": ["advanced_wishlist", "deal_finder", "carbon_tracking"],
    },
    "premium": {
        "wishlists_max": -1,
        "wishlist_items_max": -1,
        "price_alerts_max": -1,
        "budgets_max": -1,
        "ai_queries_per_month": -1,
        "features": ["unlimited", "priority_alerts", "advanced_analytics", "ai_advisor"],
    },
}


# ── Pydantic Models ──────────────────────────────────────────────────────────


class WishlistItemCreate(BaseModel):
    product_name: str
    product_url: Optional[str] = None
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None
    priority: str = "medium"  # high, medium, low


class WishlistItemUpdate(BaseModel):
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None


class WishlistCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    items: List[WishlistItemCreate] = []


class WishlistUpdate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class PriceAlertCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    wishlist_id: str
    item_id: str
    product_name: str
    target_price: float
    current_price: float
    alert_threshold_pct: float = 10.0


class PriceAlertUpdate(BaseModel):
    fallback_user_id: Optional[str] = None
    target_price: Optional[float] = None
    alert_threshold_pct: Optional[float] = None


class PriceHistoryLog(BaseModel):
    fallback_user_id: Optional[str] = None
    item_id: str
    product_name: str
    price: float
    currency: str = "USD"
    source: str = "user"


class ProductCompareRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    products: List[Dict[str, Any]]
    comparison_criteria: Optional[List[str]] = None


class AIRecommendationRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    query: str
    budget: Optional[float] = None
    preferences: Optional[Dict[str, Any]] = None


class ReviewAnalysisRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    product_name: str
    reviews: Optional[List[str]] = None
    review_url: Optional[str] = None


class ShoppingBudgetCreate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: str
    category: str = "general"  # electronics, clothing, food, general
    monthly_limit: float
    currency: str = "USD"
    alert_threshold_pct: float = 80.0


class ShoppingBudgetUpdate(BaseModel):
    fallback_user_id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    monthly_limit: Optional[float] = None
    alert_threshold_pct: Optional[float] = None


class PurchaseLog(BaseModel):
    fallback_user_id: Optional[str] = None
    budget_id: Optional[str] = None
    wishlist_id: Optional[str] = None
    item_id: Optional[str] = None
    product_name: str
    amount: float
    currency: str = "USD"
    merchant: Optional[str] = None
    category: str = "general"
    purchase_date: Optional[str] = None
    notes: Optional[str] = None


class DealSearch(BaseModel):
    fallback_user_id: Optional[str] = None
    query: str
    category: Optional[str] = None
    max_price: Optional[float] = None


class CouponValidate(BaseModel):
    fallback_user_id: Optional[str] = None
    coupon_code: str
    merchant: Optional[str] = None


class CarbonFootprintRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    product_name: str
    category: str
    quantity: int = 1


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
                    "error_code": "shopping_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "shopping_auth_required",
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
    if user_doc:
        effective = compute_effective_plan(user_doc or {})
        return effective if effective in TIER_LIMITS else "free"
    return "free"


async def _check_tier_limit(owner_id: str, tier: str, limit_key: str, current_count: int) -> bool:
    """Check if user has exceeded tier limit."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_limit = limits.get(limit_key, 0)
    if max_limit == -1:  # Unlimited
        return True
    return current_count < max_limit


async def _count_usage(owner_id: str, collection_name: str) -> int:
    """Count user's usage for a specific collection."""
    count = await db[collection_name].count_documents({"owner_id": owner_id})
    return count


def _estimate_carbon_footprint(category: str, quantity: int = 1) -> float:
    """Simple carbon footprint estimation based on product category (kg CO2)."""
    CARBON_ESTIMATES = {
        "electronics": 50.0,  # kg CO2 per unit
        "clothing": 15.0,
        "food": 2.5,
        "furniture": 100.0,
        "toys": 5.0,
        "books": 1.5,
        "general": 10.0,
    }
    base_carbon = CARBON_ESTIMATES.get(category.lower(), CARBON_ESTIMATES["general"])
    return base_carbon * quantity


# ── API Endpoints ────────────────────────────────────────────────────────────


@router.get("/bootstrap")
async def bootstrap(request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Initialize Smart Shopping Advisor workspace with tier limits and usage."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Count current usage
    wishlists_count = await _count_usage(owner_id, "shopping_wishlists")
    alerts_count = await _count_usage(owner_id, "shopping_price_alerts")
    budgets_count = await _count_usage(owner_id, "shopping_budgets")
    
    # Get current month AI query count
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ai_query_count = await db.shopping_ai_usage.count_documents({
        "owner_id": owner_id,
        "month": month_key
    })
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "limits": TIER_LIMITS[tier],
        "usage": {
            "wishlists_count": wishlists_count,
            "price_alerts_count": alerts_count,
            "budgets_count": budgets_count,
            "ai_queries_this_month": ai_query_count,
        },
        "features_available": TIER_LIMITS[tier]["features"],
    }


# ── Wishlist Management ──────────────────────────────────────────────────────


@router.post("/wishlists")
async def create_wishlist(payload: WishlistCreate, request: Request):
    """Create a new wishlist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limits
    current_count = await _count_usage(owner_id, "shopping_wishlists")
    if not await _check_tier_limit(owner_id, tier, "wishlists_max", current_count):
        raise HTTPException(
            status_code=403,
            detail=f"Wishlist limit reached for {tier} tier. Upgrade to create more."
        )
    
    wishlist_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Process items
    items = []
    for item_data in payload.items:
        item = {
            "item_id": str(uuid.uuid4()),
            "product_name": item_data.product_name,
            "product_url": item_data.product_url,
            "target_price": item_data.target_price,
            "current_price": item_data.current_price,
            "price_alert_enabled": bool(item_data.target_price),
            "image_url": item_data.image_url,
            "notes": item_data.notes,
            "priority": item_data.priority,
            "added_at": now,
            "updated_at": now,
        }
        items.append(item)
    
    wishlist = {
        "id": wishlist_id,
        "owner_id": owner_id,
        "name": payload.name,
        "description": payload.description,
        "items": items,
        "created_at": now,
        "updated_at": now,
    }
    
    await db.shopping_wishlists.insert_one(wishlist)
    
    return {"wishlist_id": wishlist_id, "message": "Wishlist created successfully"}


@router.get("/wishlists")
async def get_wishlists(request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Get all user wishlists."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    wishlists = await db.shopping_wishlists.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(100)
    
    return {"wishlists": wishlists}


@router.get("/wishlists/{wishlist_id}")
async def get_wishlist(wishlist_id: str, request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Get specific wishlist by ID."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    wishlist = await db.shopping_wishlists.find_one(
        {"id": wishlist_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    return wishlist


@router.put("/wishlists/{wishlist_id}")
async def update_wishlist(wishlist_id: str, payload: WishlistUpdate, request: Request):
    """Update wishlist details."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.description is not None:
        update_data["description"] = payload.description
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.shopping_wishlists.update_one(
        {"id": wishlist_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    return {"message": "Wishlist updated successfully"}


@router.delete("/wishlists/{wishlist_id}")
async def delete_wishlist(wishlist_id: str, request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Delete a wishlist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.shopping_wishlists.delete_one(
        {"id": wishlist_id, "owner_id": owner_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    # Also delete associated price alerts
    await db.shopping_price_alerts.delete_many(
        {"wishlist_id": wishlist_id, "owner_id": owner_id}
    )
    
    return {"message": "Wishlist deleted successfully"}


@router.post("/wishlists/{wishlist_id}/items")
async def add_wishlist_item(wishlist_id: str, payload: WishlistItemCreate, request: Request, fallback_user_id: Optional[str] = Query(None)):
    """Add an item to a wishlist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Check if wishlist exists
    wishlist = await db.shopping_wishlists.find_one(
        {"id": wishlist_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    new_item = {
        "item_id": item_id,
        "product_name": payload.product_name,
        "product_url": payload.product_url,
        "target_price": payload.target_price,
        "current_price": payload.current_price,
        "price_alert_enabled": bool(payload.target_price),
        "image_url": payload.image_url,
        "notes": payload.notes,
        "priority": payload.priority,
        "added_at": now,
        "updated_at": now,
    }
    
    await db.shopping_wishlists.update_one(
        {"id": wishlist_id, "owner_id": owner_id},
        {
            "$push": {"items": new_item},
            "$set": {"updated_at": now}
        }
    )
    
    # Create price alert if target price is set
    if payload.target_price and payload.current_price:
        alert = {
            "id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "product_name": payload.product_name,
            "target_price": payload.target_price,
            "current_price": payload.current_price,
            "alert_threshold_pct": 10.0,
            "status": "active",
            "last_checked_at": now,
            "created_at": now,
        }
        await db.shopping_price_alerts.insert_one(alert)
    
    return {"item_id": item_id, "message": "Item added to wishlist"}


@router.put("/wishlists/{wishlist_id}/items/{item_id}")
async def update_wishlist_item(
    wishlist_id: str,
    item_id: str,
    payload: WishlistItemUpdate,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Update a wishlist item."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Build update for array element
    update_fields = {}
    if payload.product_name is not None:
        update_fields["items.$.product_name"] = payload.product_name
    if payload.product_url is not None:
        update_fields["items.$.product_url"] = payload.product_url
    if payload.target_price is not None:
        update_fields["items.$.target_price"] = payload.target_price
    if payload.current_price is not None:
        update_fields["items.$.current_price"] = payload.current_price
    if payload.image_url is not None:
        update_fields["items.$.image_url"] = payload.image_url
    if payload.notes is not None:
        update_fields["items.$.notes"] = payload.notes
    if payload.priority is not None:
        update_fields["items.$.priority"] = payload.priority
    
    update_fields["items.$.updated_at"] = datetime.now(timezone.utc).isoformat()
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.shopping_wishlists.update_one(
        {"id": wishlist_id, "owner_id": owner_id, "items.item_id": item_id},
        {"$set": update_fields}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found in wishlist")
    
    return {"message": "Item updated successfully"}


@router.delete("/wishlists/{wishlist_id}/items/{item_id}")
async def delete_wishlist_item(
    wishlist_id: str,
    item_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Remove an item from a wishlist."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.shopping_wishlists.update_one(
        {"id": wishlist_id, "owner_id": owner_id},
        {
            "$pull": {"items": {"item_id": item_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    # Delete associated price alert
    await db.shopping_price_alerts.delete_many(
        {"item_id": item_id, "owner_id": owner_id}
    )
    
    return {"message": "Item removed from wishlist"}


# ── Price Tracking Engine ────────────────────────────────────────────────────


@router.post("/price-alerts")
async def create_price_alert(payload: PriceAlertCreate, request: Request):
    """Create a price alert for a wishlist item."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limits
    current_count = await _count_usage(owner_id, "shopping_price_alerts")
    if not await _check_tier_limit(owner_id, tier, "price_alerts_max", current_count):
        raise HTTPException(
            status_code=403,
            detail=f"Price alert limit reached for {tier} tier. Upgrade to create more."
        )
    
    alert_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    alert = {
        "id": alert_id,
        "owner_id": owner_id,
        "wishlist_id": payload.wishlist_id,
        "item_id": payload.item_id,
        "product_name": payload.product_name,
        "target_price": payload.target_price,
        "current_price": payload.current_price,
        "alert_threshold_pct": payload.alert_threshold_pct,
        "status": "active",
        "last_checked_at": now,
        "triggered_at": None,
        "created_at": now,
    }
    
    await db.shopping_price_alerts.insert_one(alert)
    
    return {"alert_id": alert_id, "message": "Price alert created successfully"}


@router.get("/price-alerts")
async def get_price_alerts(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Get user's price alerts."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    alerts = await db.shopping_price_alerts.find(query, {"_id": 0}).to_list(100)
    
    return {"alerts": alerts}


@router.put("/price-alerts/{alert_id}")
async def update_price_alert(alert_id: str, payload: PriceAlertUpdate, request: Request):
    """Update price alert settings."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {}
    if payload.target_price is not None:
        update_data["target_price"] = payload.target_price
    if payload.alert_threshold_pct is not None:
        update_data["alert_threshold_pct"] = payload.alert_threshold_pct
    
    result = await db.shopping_price_alerts.update_one(
        {"id": alert_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Price alert not found")
    
    return {"message": "Price alert updated successfully"}


@router.delete("/price-alerts/{alert_id}")
async def delete_price_alert(
    alert_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Delete a price alert."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.shopping_price_alerts.delete_one(
        {"id": alert_id, "owner_id": owner_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Price alert not found")
    
    return {"message": "Price alert deleted successfully"}


@router.get("/price-history/{item_id}")
async def get_price_history(
    item_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    days: int = Query(30)
):
    """Get price history for an item."""
    
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    history = await db.shopping_price_history.find(
        {
            "item_id": item_id,
            "recorded_at": {"$gte": since.isoformat()}
        },
        {"_id": 0}
    ).sort("recorded_at", 1).to_list(1000)
    
    return {"item_id": item_id, "history": history}


@router.post("/price-history")
async def log_price_history(payload: PriceHistoryLog, request: Request):
    """Log a price data point for tracking."""
    
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    log_entry = {
        "id": log_id,
        "item_id": payload.item_id,
        "product_name": payload.product_name,
        "price": payload.price,
        "currency": payload.currency,
        "source": payload.source,
        "recorded_at": now,
    }
    
    await db.shopping_price_history.insert_one(log_entry)
    
    # Check if this triggers any price alerts
    alerts = await db.shopping_price_alerts.find(
        {"item_id": payload.item_id, "status": "active"},
        {"_id": 0}
    ).to_list(100)
    
    triggered_alerts = []
    for alert in alerts:
        price_drop_pct = ((alert["current_price"] - payload.price) / alert["current_price"]) * 100
        if price_drop_pct >= alert["alert_threshold_pct"]:
            # Trigger alert
            await db.shopping_price_alerts.update_one(
                {"id": alert["id"]},
                {
                    "$set": {
                        "status": "triggered",
                        "triggered_at": now,
                        "current_price": payload.price
                    }
                }
            )
            triggered_alerts.append(alert["id"])
    
    return {
        "log_id": log_id,
        "message": "Price logged successfully",
        "triggered_alerts": triggered_alerts
    }


# ── AI Product Advisor ───────────────────────────────────────────────────────


@router.post("/product-compare")
async def compare_products(payload: ProductCompareRequest, request: Request):
    """AI-powered product comparison."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Track AI usage
    await _track_ai_usage(owner_id)
    
    products_text = "\n\n".join([
        f"Product {i+1}: {json.dumps(p, indent=2)}"
        for i, p in enumerate(payload.products)
    ])
    
    criteria = payload.comparison_criteria or ["price", "features", "quality", "reviews"]
    criteria_text = ", ".join(criteria)
    
    prompt = f"""You are a shopping advisor. Compare the following products and provide a detailed analysis:

{products_text}

Comparison criteria: {criteria_text}

Provide:
1. Side-by-side comparison table
2. Pros and cons for each product
3. Best value recommendation
4. Which product is best for different use cases

Be concise but thorough."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"shopping-compare-{uuid.uuid4().hex[:10]}",
                system_message="You are a smart shopping advisor helping users compare products objectively."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "comparison": response,
            "products_analyzed": len(payload.products)
        }
    except Exception as e:
        logger.error(f"AI product comparison failed: {e}")
        raise HTTPException(status_code=500, detail="AI comparison failed")


@router.post("/ai-recommendation")
async def ai_recommendation(payload: AIRecommendationRequest, request: Request):
    """Get AI purchase recommendations based on query and preferences."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Track AI usage
    await _track_ai_usage(owner_id)
    
    budget_text = f"Budget: ${payload.budget}" if payload.budget else "No specific budget"
    prefs_text = json.dumps(payload.preferences, indent=2) if payload.preferences else "No specific preferences"
    
    prompt = f"""You are a smart shopping advisor. A user is looking for: "{payload.query}"

{budget_text}
User preferences: {prefs_text}

Provide:
1. Top 3-5 product recommendations with specific models/brands
2. Price ranges for each recommendation
3. Why each product is a good fit
4. Where to buy (online retailers)
5. Any deals or savings tips

Be specific and practical."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"shopping-recommend-{uuid.uuid4().hex[:10]}",
                system_message="You are a smart shopping advisor providing personalized product recommendations."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "recommendation": response,
            "query": payload.query
        }
    except Exception as e:
        logger.error(f"AI recommendation failed: {e}")
        raise HTTPException(status_code=500, detail="AI recommendation failed")


@router.post("/review-analysis")
async def analyze_reviews(payload: ReviewAnalysisRequest, request: Request):
    """AI-powered review analysis and sentiment summary."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Track AI usage
    await _track_ai_usage(owner_id)
    
    if payload.reviews:
        reviews_text = "\n\n".join([f"Review {i+1}: {r}" for i, r in enumerate(payload.reviews)])
    else:
        reviews_text = f"Please analyze reviews for: {payload.product_name}\n(Note: No reviews provided, provide general guidance)"
    
    prompt = f"""You are a product review analyzer. Analyze reviews for: {payload.product_name}

{reviews_text}

Provide:
1. Overall sentiment (Positive/Mixed/Negative)
2. Key strengths mentioned
3. Common complaints or issues
4. Overall recommendation (Buy/Consider/Avoid)
5. Summary in 2-3 sentences

Be objective and balanced."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"shopping-reviews-{uuid.uuid4().hex[:10]}",
                system_message="You are a product review analyzer providing objective sentiment analysis."
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        
        return {
            "analysis": response,
            "product_name": payload.product_name,
            "reviews_analyzed": len(payload.reviews) if payload.reviews else 0
        }
    except Exception as e:
        logger.error(f"Review analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Review analysis failed")


async def _track_ai_usage(owner_id: str):
    """Track AI query usage for tier limits."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc).isoformat()
    
    await db.shopping_ai_usage.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "month": month_key,
        "query_at": now,
    })


# ── Shopping Budget Tracker ──────────────────────────────────────────────────


@router.post("/budgets")
async def create_shopping_budget(payload: ShoppingBudgetCreate, request: Request):
    """Create a shopping budget."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limits
    current_count = await _count_usage(owner_id, "shopping_budgets")
    if not await _check_tier_limit(owner_id, tier, "budgets_max", current_count):
        raise HTTPException(
            status_code=403,
            detail=f"Budget limit reached for {tier} tier. Upgrade to create more."
        )
    
    budget_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    budget = {
        "id": budget_id,
        "owner_id": owner_id,
        "name": payload.name,
        "category": payload.category,
        "monthly_limit": payload.monthly_limit,
        "currency": payload.currency,
        "alert_threshold_pct": payload.alert_threshold_pct,
        "spent_this_month": 0.0,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    
    await db.shopping_budgets.insert_one(budget)
    
    return {"budget_id": budget_id, "message": "Shopping budget created successfully"}


@router.get("/budgets")
async def get_shopping_budgets(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Get user's shopping budgets."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    budgets = await db.shopping_budgets.find(query, {"_id": 0}).to_list(100)
    
    # Calculate remaining for each budget
    for budget in budgets:
        budget["remaining"] = budget["monthly_limit"] - budget["spent_this_month"]
        budget["spent_pct"] = (budget["spent_this_month"] / budget["monthly_limit"] * 100) if budget["monthly_limit"] > 0 else 0
    
    return {"budgets": budgets}


@router.put("/budgets/{budget_id}")
async def update_shopping_budget(budget_id: str, payload: ShoppingBudgetUpdate, request: Request):
    """Update shopping budget details."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.category is not None:
        update_data["category"] = payload.category
    if payload.monthly_limit is not None:
        update_data["monthly_limit"] = payload.monthly_limit
    if payload.alert_threshold_pct is not None:
        update_data["alert_threshold_pct"] = payload.alert_threshold_pct
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.shopping_budgets.update_one(
        {"id": budget_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    return {"message": "Budget updated successfully"}


@router.delete("/budgets/{budget_id}")
async def delete_shopping_budget(
    budget_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Archive a shopping budget."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.shopping_budgets.update_one(
        {"id": budget_id, "owner_id": owner_id},
        {"$set": {"status": "archived", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    return {"message": "Budget archived successfully"}


@router.post("/purchases")
async def log_purchase(payload: PurchaseLog, request: Request):
    """Log a purchase and update budget."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    purchase_id = str(uuid.uuid4())
    purchase_date = payload.purchase_date or datetime.now(timezone.utc).isoformat()
    
    # Calculate carbon footprint
    carbon_kg = _estimate_carbon_footprint(payload.category, 1)
    
    purchase = {
        "id": purchase_id,
        "owner_id": owner_id,
        "budget_id": payload.budget_id,
        "wishlist_id": payload.wishlist_id,
        "item_id": payload.item_id,
        "product_name": payload.product_name,
        "amount": payload.amount,
        "currency": payload.currency,
        "merchant": payload.merchant,
        "category": payload.category,
        "purchase_date": purchase_date,
        "notes": payload.notes,
        "carbon_footprint_kg": carbon_kg,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.shopping_purchases.insert_one(purchase)
    
    # Update budget spent amount if budget_id provided
    if payload.budget_id:
        await db.shopping_budgets.update_one(
            {"id": payload.budget_id, "owner_id": owner_id},
            {"$inc": {"spent_this_month": payload.amount}}
        )
    
    return {
        "purchase_id": purchase_id,
        "carbon_footprint_kg": carbon_kg,
        "message": "Purchase logged successfully"
    }


@router.get("/purchases")
async def get_purchases(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    budget_id: Optional[str] = Query(None),
    limit: int = Query(50)
):
    """Get purchase history."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if budget_id:
        query["budget_id"] = budget_id
    
    purchases = await db.shopping_purchases.find(
        query,
        {"_id": 0}
    ).sort("purchase_date", -1).limit(limit).to_list(limit)
    
    return {"purchases": purchases}


@router.get("/budget-analytics")
async def get_budget_analytics(
    request: Request,
    fallback_user_id: Optional[str] = Query(None)
):
    """Get shopping budget analytics and insights."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get current month key
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all active budgets
    budgets = await db.shopping_budgets.find(
        {"owner_id": owner_id, "status": "active"},
        {"_id": 0}
    ).to_list(100)
    
    # Get this month's purchases
    purchases = await db.shopping_purchases.find(
        {
            "owner_id": owner_id,
            "purchase_date": {"$gte": month_start.isoformat()}
        },
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate analytics
    total_budget = sum(b["monthly_limit"] for b in budgets)
    total_spent = sum(p["amount"] for p in purchases)
    total_remaining = total_budget - total_spent
    
    # Category breakdown
    category_spending = {}
    for purchase in purchases:
        cat = purchase["category"]
        category_spending[cat] = category_spending.get(cat, 0) + purchase["amount"]
    
    top_categories = sorted(
        category_spending.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    return {
        "month": month_key,
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
        "spent_pct": (total_spent / total_budget * 100) if total_budget > 0 else 0,
        "purchase_count": len(purchases),
        "top_categories": [{"category": cat, "amount": amt} for cat, amt in top_categories],
        "budgets": budgets,
    }


# ── Deal & Coupon Finder ─────────────────────────────────────────────────────


@router.get("/deals")
async def get_deals(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(20)
):
    """Get available deals."""
    user = await get_current_user(request)
    _ = _resolve_owner_id(user, fallback_user_id)
    
    query = {"expires_at": {"$gte": datetime.now(timezone.utc).isoformat()}}
    if category:
        query["category"] = category
    
    deals = await db.shopping_deals.find(
        query,
        {"_id": 0}
    ).sort("discount_pct", -1).limit(limit).to_list(limit)
    
    return {"deals": deals}


@router.post("/deals/search")
async def search_deals(payload: DealSearch, request: Request):
    """AI-powered deal search."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Track AI usage
    await _track_ai_usage(owner_id)
    
    category_text = f"Category: {payload.category}" if payload.category else "Any category"
    price_text = f"Max price: ${payload.max_price}" if payload.max_price else "Any price"
    
    prompt = f"""You are a deal finder. Search for deals on: "{payload.query}"

{category_text}
{price_text}

Provide:
1. Top 5 current deals/discounts
2. Specific retailers and prices
3. Coupon codes if available
4. Deal expiration dates
5. Tips for finding better deals

Be specific with retailer names and prices."""
    
    try:
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_KEY)
        response = await llm.ainvoke([UserMessage(prompt)])
        
        return {
            "deals": response.content,
            "query": payload.query
        }
    except Exception as e:
        logger.error(f"Deal search failed: {e}")
        raise HTTPException(status_code=500, detail="Deal search failed")


@router.post("/coupons/validate")
async def validate_coupon(payload: CouponValidate, request: Request):
    """Validate a coupon code (mock implementation for MVP)."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Track AI usage
    await _track_ai_usage(owner_id)
    
    merchant_text = f"for {payload.merchant}" if payload.merchant else ""
    
    prompt = f"""Check if this coupon code is valid: "{payload.coupon_code}" {merchant_text}

Provide:
1. Likely validity (Valid/Expired/Invalid/Unknown)
2. What discount it typically offers
3. Any restrictions or terms
4. Alternative coupon codes if this one is expired

Be practical and realistic."""
    
    try:
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_KEY)
        response = await llm.ainvoke([UserMessage(prompt)])
        
        return {
            "validation": response.content,
            "coupon_code": payload.coupon_code
        }
    except Exception as e:
        logger.error(f"Coupon validation failed: {e}")
        raise HTTPException(status_code=500, detail="Coupon validation failed")


# ── Carbon Footprint Calculator ──────────────────────────────────────────────


@router.post("/carbon-footprint")
async def calculate_carbon_footprint(payload: CarbonFootprintRequest, request: Request):
    """Calculate carbon footprint for a purchase."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    carbon_kg = _estimate_carbon_footprint(payload.category, payload.quantity)
    
    # Track AI usage for detailed analysis
    await _track_ai_usage(owner_id)
    
    prompt = f"""Calculate environmental impact for: {payload.product_name}
Category: {payload.category}
Quantity: {payload.quantity}

Estimated CO2: {carbon_kg} kg

Provide:
1. What this carbon footprint means (equivalent to X miles driven, etc.)
2. Environmental impact summary
3. Tips to reduce impact
4. Eco-friendly alternatives if available

Be educational and practical."""
    
    try:
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_KEY)
        response = await llm.ainvoke([UserMessage(prompt)])
        
        return {
            "carbon_kg": carbon_kg,
            "analysis": response.content,
            "product": payload.product_name
        }
    except Exception as e:
        logger.error(f"Carbon analysis failed: {e}")
        return {
            "carbon_kg": carbon_kg,
            "analysis": f"Estimated carbon footprint: {carbon_kg} kg CO2",
            "product": payload.product_name
        }


@router.get("/carbon-report")
async def get_carbon_report(
    request: Request,
    fallback_user_id: Optional[str] = Query(None),
    month: Optional[str] = Query(None)
):
    """Get user's carbon footprint report."""
    user = await get_current_user(request)

    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Default to current month
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    
    # Get purchases for the month
    month_start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    
    purchases = await db.shopping_purchases.find(
        {
            "owner_id": owner_id,
            "purchase_date": {
                "$gte": month_start.isoformat(),
                "$lt": month_end.isoformat()
            }
        },
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate totals
    total_carbon = sum(p.get("carbon_footprint_kg", 0) for p in purchases)
    total_purchases = len(purchases)
    
    # Category breakdown
    category_carbon = {}
    for purchase in purchases:
        cat = purchase["category"]
        carbon = purchase.get("carbon_footprint_kg", 0)
        category_carbon[cat] = category_carbon.get(cat, 0) + carbon
    
    return {
        "month": month,
        "total_purchases": total_purchases,
        "total_carbon_kg": round(total_carbon, 2),
        "category_breakdown": category_carbon,
        "avg_carbon_per_purchase": round(total_carbon / total_purchases, 2) if total_purchases > 0 else 0,
    }
