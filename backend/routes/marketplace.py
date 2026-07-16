"""Digital Marketplace — Buy/sell products, courses, services via Platform wallet."""

from fastapi import APIRouter, HTTPException, Request
import re
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import logging

from .db import db, require_auth

router = APIRouter(prefix="/marketplace")
logger = logging.getLogger(__name__)

CATEGORIES = [
    "courses",
    "ebooks",
    "templates",
    "software",
    "design",
    "music",
    "video",
    "consulting",
    "coaching",
    "other",
]


class ProductCreate(BaseModel):
    title: str
    description: str
    price: float
    category: str = "other"
    tags: List[str] = []


class ProductPurchase(BaseModel):
    product_id: str


class ReviewCreate(BaseModel):
    product_id: str
    rating: int  # 1-5
    comment: str = ""


@router.post("/products/create")
async def create_product(payload: ProductCreate, request: Request):
    user = await require_auth(request)
    if payload.price < 0:
        raise HTTPException(status_code=400, detail="Price must be non-negative")
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0, "handle": 1, "user_name": 1})
    product = {
        "product_id": f"prod_{uuid.uuid4().hex[:12]}",
        "seller_id": user.user_id,
        "seller_handle": wallet.get("handle", "") if wallet else "",
        "seller_name": wallet.get("user_name", "") if wallet else "",
        "title": payload.title,
        "description": payload.description,
        "price": payload.price,
        "category": payload.category if payload.category in CATEGORIES else "other",
        "tags": payload.tags,
        "status": "active",
        "sales_count": 0,
        "total_revenue": 0.0,
        "avg_rating": 0,
        "review_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.marketplace_products.insert_one(product)
    product.pop("_id", None)
    return {"product": product}


@router.get("/products")
async def list_products(
    request: Request, category: Optional[str] = None, search: Optional[str] = None, limit: int = 30
):
    await require_auth(request)
    query: dict = {"status": "active"}
    if category and category in CATEGORIES:
        query["category"] = category
    if search:
        query["$or"] = [{"title": {"$regex": re.escape(str(search)), "$options": "i"}}, {"tags": {"$in": [search.lower()]}}]
    products = await db.marketplace_products.find(query, {"_id": 0}).sort("sales_count", -1).limit(limit).to_list(limit)
    return {"products": products, "categories": CATEGORIES}


@router.get("/products/{product_id}")
async def get_product(product_id: str, request: Request):
    await require_auth(request)
    product = await db.marketplace_products.find_one({"product_id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    reviews = (
        await db.marketplace_reviews.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(10)
    )
    return {"product": product, "reviews": reviews}


@router.post("/products/purchase")
async def purchase_product(payload: ProductPurchase, request: Request):
    user = await require_auth(request)
    product = await db.marketplace_products.find_one({"product_id": payload.product_id, "status": "active"}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product["seller_id"] == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot buy your own product")
    # Check existing purchase
    existing = await db.marketplace_purchases.find_one(
        {"product_id": payload.product_id, "buyer_id": user.user_id}, {"_id": 0}
    )
    if existing:
        return {"success": True, "already_owned": True}
    price = product["price"]
    if price > 0:
        wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
        if not wallet or wallet.get("balance", 0) < price:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        await db.platform_wallets.update_one(
            {"user_id": user.user_id, "balance": {"$gte": price}},
            {"$inc": {"balance": -price}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        net = round(price * 0.85, 2)  # 15% platform fee
        await db.platform_wallets.update_one(
            {"user_id": product["seller_id"]},
            {"$inc": {"balance": net}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    purchase = {
        "purchase_id": f"mpur_{uuid.uuid4().hex[:10]}",
        "product_id": payload.product_id,
        "buyer_id": user.user_id,
        "seller_id": product["seller_id"],
        "amount": price,
        "platform_fee": round(price * 0.15, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.marketplace_purchases.insert_one(purchase)
    await db.marketplace_products.update_one(
        {"product_id": payload.product_id}, {"$inc": {"sales_count": 1, "total_revenue": price}}
    )
    await db.platform_transactions.insert_one(
        {
            "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
            "type": "marketplace_purchase",
            "sender_id": user.user_id,
            "recipient_id": product["seller_id"],
            "amount": price,
            "currency": "USD",
            "description": f"Marketplace: {product['title']}",
            "status": "completed",
            "risk_score": 0,
            "fraud_checked": False,
            "meta": {"product_id": payload.product_id},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "amount_paid": price}


@router.post("/reviews/create")
async def create_review(payload: ReviewCreate, request: Request):
    user = await require_auth(request)
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    purchased = await db.marketplace_purchases.find_one(
        {"product_id": payload.product_id, "buyer_id": user.user_id}, {"_id": 0}
    )
    if not purchased:
        raise HTTPException(status_code=400, detail="Must purchase before reviewing")
    review = {
        "review_id": f"rev_{uuid.uuid4().hex[:10]}",
        "product_id": payload.product_id,
        "user_id": user.user_id,
        "rating": payload.rating,
        "comment": payload.comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.marketplace_reviews.insert_one(review)
    # Update avg rating
    reviews = await db.marketplace_reviews.find({"product_id": payload.product_id}, {"_id": 0, "rating": 1}).to_list(
        100
    )
    avg = round(sum(r["rating"] for r in reviews) / len(reviews), 1)
    await db.marketplace_products.update_one(
        {"product_id": payload.product_id}, {"$set": {"avg_rating": avg, "review_count": len(reviews)}}
    )
    return {"success": True}


@router.get("/recommendations")
async def ai_recommendations(request: Request):
    user = await require_auth(request)
    purchases = await db.marketplace_purchases.find({"buyer_id": user.user_id}, {"_id": 0, "product_id": 1}).to_list(20)
    bought_ids = [p["product_id"] for p in purchases]
    bought_cats = set()
    for pid in bought_ids:
        p = await db.marketplace_products.find_one({"product_id": pid}, {"_id": 0, "category": 1})
        if p:
            bought_cats.add(p.get("category"))
    preferred = list(bought_cats)[:3] if bought_cats else CATEGORIES[:3]
    recs = (
        await db.marketplace_products.find(
            {"status": "active", "category": {"$in": preferred}, "product_id": {"$nin": bought_ids}}, {"_id": 0}
        )
        .sort("sales_count", -1)
        .limit(10)
        .to_list(10)
    )
    if len(recs) < 5:
        filler = (
            await db.marketplace_products.find(
                {"status": "active", "product_id": {"$nin": bought_ids + [r["product_id"] for r in recs]}}, {"_id": 0}
            )
            .sort("sales_count", -1)
            .limit(5)
            .to_list(5)
        )
        recs.extend(filler)
    return {"recommendations": recs}


@router.get("/my-store")
async def my_store(request: Request):
    user = await require_auth(request)
    products = (
        await db.marketplace_products.find({"seller_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    )
    total_rev = sum(p.get("total_revenue", 0) for p in products)
    total_sales = sum(p.get("sales_count", 0) for p in products)
    return {"products": products, "total_revenue": round(total_rev, 2), "total_sales": total_sales}


@router.get("/my-purchases")
async def my_purchases(request: Request):
    user = await require_auth(request)
    purchases = (
        await db.marketplace_purchases.find({"buyer_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    )
    for p in purchases:
        prod = await db.marketplace_products.find_one(
            {"product_id": p["product_id"]}, {"_id": 0, "title": 1, "category": 1, "seller_name": 1}
        )
        if prod:
            p.update(prod)
    return {"purchases": purchases}
