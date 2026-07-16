"""
Payment domain Pydantic models.

Extracted from `routes/payments_checkout_core.py` as part of the Phase 2
model migration (see /app/backend/models/README.md). These canonical
checkout request/response schemas are now imported back into the route
module via a one-line re-export so the public API surface is unchanged.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


class CreateCheckoutRequest(BaseModel):
    """Payload for initiating a checkout session."""

    plan_id: str
    billing_period: str = "monthly"
    payment_method: str = "stripe"
    saved_card_id: Optional[str] = None
    currency: str = "usd"
    country_code: Optional[str] = None
    state_code: Optional[str] = None
    postal_code: Optional[str] = None
    product_type: Optional[str] = None
    preferred_language: Optional[str] = None
    browser_language: Optional[str] = None
    browser_languages: Optional[str] = None
    mobile_provider: Optional[str] = None
    phone_number: Optional[str] = None


class ConfirmPaymentRequest(BaseModel):
    """Payload for confirming a completed payment session."""

    session_id: Optional[str] = None
    payment_id: Optional[str] = None
    payment_method: Optional[str] = "stripe"
    plan_id: Optional[str] = None
    billing_period: Optional[str] = None


class CheckoutPreviewRequest(BaseModel):
    """Payload for previewing checkout totals (no charge)."""

    plan_id: str
    billing_period: str = "monthly"
    payment_method: str = "stripe"  # stripe | paypal | fedapay
    currency: str = "usd"
    country_code: Optional[str] = None
    state_code: Optional[str] = None
    postal_code: Optional[str] = None
    product_type: Optional[str] = None
    preferred_language: Optional[str] = None
    browser_language: Optional[str] = None
    browser_languages: Optional[str] = None
    mobile_provider: Optional[str] = None


class PaymentRecord(BaseModel):
    """Canonical persisted payment record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    plan_id: str
    amount: float
    currency: str = "usd"
    payment_method: str
    payment_id: str
    status: str
    subtotal: float = 0.0
    tax_amount: float = 0.0
    processing_fee: float = 0.0
    amount_gross: float = 0.0
    amount_net: float = 0.0
    total_amount: float = 0.0
    provider: str = ""
    transaction_id: str = ""
    jurisdiction: Dict[str, Any] = Field(default_factory=dict)
    product_type: str = "education_digital_service"
    tax_provider: str = ""
    tax_rate: float = 0.0
    tax_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    locale: str = "en"
    preferred_language: str = "en"
    localization_context: Dict[str, Any] = Field(default_factory=dict)
    fx_rate: float = 1.0
    fx_base_currency: str = "USD"
    original_usd_amount: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "CreateCheckoutRequest",
    "ConfirmPaymentRequest",
    "CheckoutPreviewRequest",
    "PaymentRecord",
]
