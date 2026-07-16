"""Saved-card route handlers extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from utils.email_service import is_email_configured, send_catalog_template

from .db import db
from .payments_cards import (
    ensure_default_active_card,
    expire_stale_cards_for_user,
    is_card_expired,
    normalize_expiry_year,
    normalize_stored_card_year,
    payment_card_surface,
)


router = APIRouter()
_logger = logging.getLogger("routes.payments.cards_routes")
_get_user_from_request: Optional[Callable[[Request], Awaitable[object | None]]] = None
_stripe_api_key = os.environ.get("STRIPE_API_KEY")


class SaveCardRequest(BaseModel):
    stripe_token: Optional[str] = None
    cardholder_name: str


class UpdateCardRequest(BaseModel):
    card_id: str
    cardholder_name: Optional[str] = None
    expiry_month: Optional[int] = None
    expiry_year: Optional[int] = None
    is_default: Optional[bool] = None


def configure_payment_card_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
    stripe_api_key: Optional[str],
    logger: logging.Logger,
) -> None:
    global _get_user_from_request, _stripe_api_key, _logger
    _get_user_from_request = get_user_from_request
    _stripe_api_key = stripe_api_key
    _logger = logger


async def require_auth_payment(request: Request):
    if _get_user_from_request is None:
        raise HTTPException(status_code=503, detail="Payment card routes are not configured")
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/payments/cards/add")
async def add_payment_card(payload: SaveCardRequest, request: Request):
    user = await require_auth_payment(request)

    if not str(payload.cardholder_name or "").strip():
        raise HTTPException(status_code=400, detail="Cardholder name is required")

    import stripe as _stripe

    stripe_key = _stripe_api_key or ""
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Payment processing is temporarily unavailable. Please try again later.")

    stripe_token = str(payload.stripe_token or "").strip()
    if not stripe_token:
        raise HTTPException(status_code=400, detail="Card verification token is required. Please try again.")

    try:
        pm = _stripe.PaymentMethod.create(
            type="card",
            card={"token": stripe_token},
            billing_details={"name": payload.cardholder_name.strip()},
            api_key=stripe_key,
        )
        stripe_pm_id = pm.get("id", "")
        stripe_card = pm.get("card") or {}
        verified_brand = str(stripe_card.get("brand") or "other").lower()
        verified_last_four = str(stripe_card.get("last4") or "0000")
        verified_funding = str(stripe_card.get("funding") or "unknown")
        verified_exp_month = int(stripe_card.get("exp_month") or 0)
        verified_exp_year = int(stripe_card.get("exp_year") or 0)
    except _stripe.error.CardError as e:
        err_body = e.json_body or {}
        err_detail = (err_body.get("error") or {}).get("message") or str(e.user_message or e)
        raise HTTPException(status_code=400, detail=f"Card declined: {err_detail}")
    except _stripe.error.InvalidRequestError as e:
        err_msg = str(e)
        if "token" in err_msg.lower() and ("used" in err_msg.lower() or "invalid" in err_msg.lower()):
            raise HTTPException(status_code=400, detail="Card verification expired. Please re-enter your card details and try again.")
        raise HTTPException(status_code=400, detail="Invalid card details. Please double-check your card number, expiry, and CVC.")
    except Exception as e:
        _logger.warning(f"Stripe PaymentMethod creation failed: {e}")
        raise HTTPException(status_code=400, detail="Card verification failed. Please check your card details and try again.")

    if is_card_expired(verified_exp_month, verified_exp_year):
        raise HTTPException(status_code=400, detail="Card is expired. Please add a non-expired card.")

    now = datetime.now(timezone.utc)
    existing = await db.payment_cards.count_documents({"user_id": user.user_id, "status": "active"})
    card_id = f"card_{uuid.uuid4().hex[:12]}"
    card = {
        "card_id": card_id,
        "user_id": user.user_id,
        "last_four": verified_last_four,
        "masked_number": f"**** **** **** {verified_last_four}",
        "card_type": verified_brand,
        "cardholder_name": payload.cardholder_name.strip(),
        "expiry_month": verified_exp_month,
        "expiry_year": verified_exp_year,
        "is_default": existing == 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "status": "active",
        "stripe_pm_id": stripe_pm_id,
        "funding_type": verified_funding,
        "verified_by_stripe": True,
    }
    await db.payment_cards.insert_one(card)
    card.pop("_id", None)
    return {"message": "Card added and verified successfully", "card": payment_card_surface(card)}


@router.get("/payments/cards")
async def list_payment_cards(request: Request):
    user = await require_auth_payment(request)
    await expire_stale_cards_for_user(user.user_id)
    await ensure_default_active_card(user.user_id)
    cursor = db.payment_cards.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).sort([("is_default", -1), ("created_at", -1)])
    cards_raw = await cursor.to_list(20)
    cards: list[dict] = []
    for card in cards_raw:
        normalized = await normalize_stored_card_year(card)
        if is_card_expired(int(normalized.get("expiry_month", 0) or 0), int(normalized.get("expiry_year", 0) or 0)):
            await db.payment_cards.update_one(
                {"card_id": normalized.get("card_id")},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            continue
        cards.append(payment_card_surface(normalized))
    return {"cards": cards}


@router.get("/payments/cards/checkout-ready")
async def list_checkout_ready_cards(request: Request):
    await require_auth_payment(request)
    list_resp = await list_payment_cards(request)
    cards = list_resp.get("cards", [])
    default_card = next((card for card in cards if card.get("is_default")), cards[0] if cards else None)
    return {"cards": cards, "default_card": default_card}


@router.put("/payments/cards/update")
async def update_payment_card(payload: UpdateCardRequest, request: Request):
    user = await require_auth_payment(request)
    card = await db.payment_cards.find_one({"card_id": payload.card_id, "user_id": user.user_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    card = await normalize_stored_card_year(card)
    if card.get("status") != "active":
        raise HTTPException(status_code=400, detail="Only active cards can be updated")

    updates = {}
    if payload.cardholder_name:
        updates["cardholder_name"] = payload.cardholder_name.strip()

    next_month = payload.expiry_month if payload.expiry_month is not None else int(card.get("expiry_month", 0) or 0)
    next_year_raw = payload.expiry_year if payload.expiry_year is not None else int(card.get("expiry_year", 0) or 0)
    next_year = normalize_expiry_year(int(next_year_raw or 0))

    if payload.expiry_month is not None and (next_month < 1 or next_month > 12):
        raise HTTPException(status_code=400, detail="Invalid expiry month")
    if payload.expiry_month is not None:
        updates["expiry_month"] = next_month
    if payload.expiry_year is not None:
        updates["expiry_year"] = next_year

    if (payload.expiry_month is not None or payload.expiry_year is not None) and is_card_expired(next_month, next_year):
        raise HTTPException(status_code=400, detail="Cannot save expired card. Please provide a valid expiry date.")

    if payload.is_default is True:
        await db.payment_cards.update_many({"user_id": user.user_id}, {"$set": {"is_default": False}})
        updates["is_default"] = True

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if updates:
        await db.payment_cards.update_one({"card_id": payload.card_id}, {"$set": updates})

    updated = await db.payment_cards.find_one({"card_id": payload.card_id}, {"_id": 0})
    updated = await normalize_stored_card_year(updated or {})

    try:
        if is_email_configured():
            await send_catalog_template(
                recipient_email=user.email,
                template_key="payment_method_updated",
                recipient_name=user.name or user.email,
                user_name=user.name or user.email,
                card_last4=updated.get("last_four", updated.get("masked_number", "")[-4:]),
                card_brand=updated.get("card_type", "Card").title(),
                updated_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC"),
            )
    except Exception as e:
        _logger.warning(f"Payment method update email failed: {e}")

    return {"message": "Card updated", "card": payment_card_surface(updated)}


@router.delete("/payments/cards/{card_id}")
async def delete_payment_card(card_id: str, request: Request):
    user = await require_auth_payment(request)
    card = await db.payment_cards.find_one({"card_id": card_id, "user_id": user.user_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.get("is_default"):
        other = await db.payment_cards.find_one({"user_id": user.user_id, "card_id": {"$ne": card_id}, "status": "active"})
        if other:
            await db.payment_cards.update_one({"card_id": other["card_id"]}, {"$set": {"is_default": True}})

    await db.payment_cards.update_one({"card_id": card_id}, {"$set": {"status": "removed"}})
    await ensure_default_active_card(user.user_id)
    return {"message": "Card removed"}


@router.post("/payments/cards/set-default")
async def set_default_card(request: Request):
    user = await require_auth_payment(request)
    body = await request.json()
    card_id = body.get("card_id")
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id required")
    card = await db.payment_cards.find_one({"card_id": card_id, "user_id": user.user_id, "status": "active"})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    card = await normalize_stored_card_year(card)
    if is_card_expired(int(card.get("expiry_month", 0) or 0), int(card.get("expiry_year", 0) or 0)):
        await db.payment_cards.update_one(
            {"card_id": card_id},
            {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        raise HTTPException(status_code=400, detail="Cannot set an expired card as default")
    await db.payment_cards.update_many({"user_id": user.user_id}, {"$set": {"is_default": False}})
    await db.payment_cards.update_one({"card_id": card_id}, {"$set": {"is_default": True, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Default card updated"}