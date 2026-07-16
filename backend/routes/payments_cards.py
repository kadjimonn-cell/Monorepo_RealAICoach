"""Saved-card helper functions extracted from payments routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from .db import db


def mask_card(number: str) -> str:
    clean = number.replace(" ", "").replace("-", "")
    return f"**** **** **** {clean[-4:]}" if len(clean) >= 4 else "****"


def normalize_expiry_year(year: int) -> int:
    return year + 2000 if 0 < year < 100 else year


def is_card_expired(expiry_month: int, expiry_year: int) -> bool:
    month = int(expiry_month or 0)
    year = normalize_expiry_year(int(expiry_year or 0))
    if month < 1 or month > 12:
        return True
    now = datetime.now(timezone.utc)
    return year < now.year or (year == now.year and month < now.month)


def is_card_expiring_soon(expiry_month: int, expiry_year: int, within_days: int = 60) -> bool:
    if is_card_expired(expiry_month, expiry_year):
        return False
    year = normalize_expiry_year(int(expiry_year))
    month = int(expiry_month)
    now = datetime.now(timezone.utc)
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    next_month = month_start + timedelta(days=32)
    expiry_end = datetime(next_month.year, next_month.month, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    return expiry_end <= now + timedelta(days=within_days)


def payment_card_surface(card: dict) -> dict:
    expiry_month = int(card.get("expiry_month", 0) or 0)
    expiry_year = normalize_expiry_year(int(card.get("expiry_year", 0) or 0))
    expired = is_card_expired(expiry_month, expiry_year)
    status = "expired" if expired else "expiring_soon" if is_card_expiring_soon(expiry_month, expiry_year) else "valid"
    return {
        "card_id": card.get("card_id"),
        "card_type": card.get("card_type", "other"),
        "masked_number": card.get("masked_number", "****"),
        "cardholder_name": card.get("cardholder_name", ""),
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "is_default": bool(card.get("is_default", False)),
        "last_four": card.get("last_four", ""),
        "status": "expired" if expired else str(card.get("status", "active")),
        "valid_for_checkout": not expired and str(card.get("status", "active")) == "active",
        "validity_status": status,
        "usable_gateways": ["stripe", "paypal", "fedapay", "iap_apple", "iap_google"],
    }


async def normalize_stored_card_year(card: dict) -> dict:
    year = int(card.get("expiry_year", 0) or 0)
    normalized_year = normalize_expiry_year(year)
    if normalized_year != year and card.get("card_id"):
        await db.payment_cards.update_one(
            {"card_id": card["card_id"]},
            {"$set": {"expiry_year": normalized_year, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        card = {**card, "expiry_year": normalized_year}
    return card


async def expire_stale_cards_for_user(user_id: str) -> int:
    now = datetime.now(timezone.utc)
    result = await db.payment_cards.update_many(
        {
            "user_id": user_id,
            "status": "active",
            "$or": [
                {"expiry_year": {"$lt": now.year}},
                {"expiry_year": now.year, "expiry_month": {"$lt": now.month}},
            ],
        },
        {"$set": {"status": "expired", "updated_at": now.isoformat()}},
    )
    return int(result.modified_count or 0)


async def ensure_default_active_card(user_id: str) -> None:
    default_card = await db.payment_cards.find_one({"user_id": user_id, "status": "active", "is_default": True}, {"_id": 0, "card_id": 1})
    if default_card:
        return
    fallback = await db.payment_cards.find_one({"user_id": user_id, "status": "active"}, {"_id": 0, "card_id": 1}, sort=[("created_at", 1)])
    if fallback and fallback.get("card_id"):
        await db.payment_cards.update_one(
            {"card_id": fallback["card_id"]},
            {"$set": {"is_default": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )


async def resolve_saved_card_for_checkout(user_id: str, card_id: Optional[str]) -> Optional[dict]:
    await expire_stale_cards_for_user(user_id)
    await ensure_default_active_card(user_id)
    if card_id:
        selected = await db.payment_cards.find_one({"card_id": card_id, "user_id": user_id}, {"_id": 0})
        if not selected:
            raise HTTPException(status_code=404, detail="Selected saved card was not found")
        selected = await normalize_stored_card_year(selected)
        if selected.get("status") != "active":
            raise HTTPException(status_code=400, detail="Selected saved card is not active")
        if is_card_expired(int(selected.get("expiry_month", 0) or 0), int(selected.get("expiry_year", 0) or 0)):
            await db.payment_cards.update_one(
                {"card_id": selected.get("card_id")},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            raise HTTPException(status_code=400, detail="Selected saved card is expired. Please update or add a valid card.")
        return payment_card_surface(selected)
    candidates = await db.payment_cards.find({"user_id": user_id, "status": "active"}, {"_id": 0}).sort([("is_default", -1), ("created_at", -1)]).to_list(20)
    for candidate in candidates:
        normalized = await normalize_stored_card_year(candidate)
        if is_card_expired(int(normalized.get("expiry_month", 0) or 0), int(normalized.get("expiry_year", 0) or 0)):
            await db.payment_cards.update_one(
                {"card_id": normalized.get("card_id")},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            continue
        return payment_card_surface(normalized)
    return None


def build_saved_card_metadata(saved_card: Optional[dict]) -> dict:
    if not saved_card:
        return {}
    return {
        "saved_card_id": str(saved_card.get("card_id") or ""),
        "saved_card_last4": str(saved_card.get("last_four") or ""),
        "saved_card_type": str(saved_card.get("card_type") or ""),
    }