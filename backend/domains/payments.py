"""Payments Domain — Subscriptions, payments, FedaPay, Stripe, PayPal, IAP."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import payments
    from routes.iap import router as iap_router

    api_router.include_router(iap_router)

    if app:
        app.include_router(payments.router, prefix="/api", tags=["Payments"])
