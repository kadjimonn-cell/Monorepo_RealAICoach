"""Payment notification recovery and reconciliation routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request

from .db import db
from .payments_catalog import get_subscription_plan_from_gps


router = APIRouter()
logger = logging.getLogger("routes.payments.recovery")


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="Payment recovery routes are not configured")


async def _missing_notification_sender(**_kwargs):
    raise HTTPException(status_code=503, detail="Payment notification sender is not configured")


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver
_send_payment_notification_cb: Callable[..., Awaitable[dict]] = _missing_notification_sender


def configure_payment_recovery_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
    send_payment_notification: Callable[..., Awaitable[dict]],
    route_logger: Optional[logging.Logger] = None,
) -> None:
    global _get_user_from_request, _send_payment_notification_cb, logger
    _get_user_from_request = get_user_from_request
    _send_payment_notification_cb = send_payment_notification
    if route_logger is not None:
        logger = route_logger


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _payment_audit_tx_filter(tx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    tx = tx or {}
    if tx.get("transaction_id"):
        return {"transaction_id": tx.get("transaction_id")}
    if tx.get("payment_id"):
        return {"payment_id": tx.get("payment_id")}
    if tx.get("session_id"):
        return {"session_id": tx.get("session_id")}
    return {}


async def queue_payment_notification_recovery(tx: Optional[Dict[str, Any]], reason: str) -> None:
    """Persist notification failures so silent drops are always recoverable."""
    tx = tx or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    queue_filter: Dict[str, Any] = {}
    if tx.get("payment_id"):
        queue_filter["payment_id"] = tx.get("payment_id")
    if tx.get("session_id"):
        queue_filter["session_id"] = tx.get("session_id")
    if not queue_filter:
        queue_filter["queue_id"] = f"notifq_{uuid.uuid4().hex[:12]}"

    update_doc = {
        "$set": {
            "provider": tx.get("provider") or tx.get("payment_method") or "payment",
            "payment_id": tx.get("payment_id"),
            "session_id": tx.get("session_id"),
            "transaction_id": tx.get("transaction_id"),
            "tx_id": tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id"),
            "user_id": tx.get("user_id"),
            "status": "pending",
            "reason": str(reason),
            "updated_at": now_iso,
        },
        "$setOnInsert": {
            "queue_id": queue_filter.get("queue_id") or f"notifq_{uuid.uuid4().hex[:12]}",
            "retry_count": 0,
            "created_at": now_iso,
        },
    }

    try:
        await db.notification_recovery_queue.update_one(queue_filter, update_doc, upsert=True)
    except Exception as exc:
        logger.error(f"Failed to persist payment notification recovery record: {exc}")


async def mark_payment_notification_sent(tx_filter: Dict[str, Any]) -> None:
    if not tx_filter:
        return
    await db.payment_transactions.update_one(
        tx_filter,
        {
            "$set": {
                "notification_sent": True,
                "notification_sent_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )


_INTERNAL_NOTIFICATION_SUPPRESSION_ENVIRONMENTS = frozenset({"health_drill", "ops_drill", "synthetic"})
_INTERNAL_NOTIFICATION_SUPPRESSION_USER_IDS = frozenset({"ops_user"})
_INTERNAL_NOTIFICATION_SUPPRESSION_PREFIXES = (
    "ops_tx_",
    "ops_pay_",
    "ops_sess_",
)


def should_suppress_payment_notifications(tx: Optional[Dict[str, Any]]) -> bool:
    tx = tx or {}
    if bool(tx.get("notification_suppressed")):
        return True

    environment = str(tx.get("environment") or "").strip().lower()
    if environment in _INTERNAL_NOTIFICATION_SUPPRESSION_ENVIRONMENTS:
        return True

    user_id = str(tx.get("user_id") or "").strip().lower()
    if user_id in _INTERNAL_NOTIFICATION_SUPPRESSION_USER_IDS:
        return True

    for field_name in ("transaction_id", "payment_id", "session_id"):
        field_value = str(tx.get(field_name) or "").strip().lower()
        if field_value.startswith(_INTERNAL_NOTIFICATION_SUPPRESSION_PREFIXES):
            return True

    return False


def build_missed_notification_recovery_query(provider: str = "") -> Dict[str, Any]:
    query: Dict[str, Any] = {
        "payment_status": "completed",
        "notification_suppressed": {"$ne": True},
        "environment": {"$nin": list(_INTERNAL_NOTIFICATION_SUPPRESSION_ENVIRONMENTS)},
        "user_id": {"$nin": list(_INTERNAL_NOTIFICATION_SUPPRESSION_USER_IDS)},
        "$or": [{"notification_sent": {"$exists": False}}, {"notification_sent": False}],
    }
    if provider:
        query["provider"] = provider
    return query


async def recover_missed_notification_for_transaction(tx: Dict[str, Any]) -> Dict[str, Any]:
    """Recover missed post-payment notifications for a completed transaction."""
    if should_suppress_payment_notifications(tx):
        tx_filter = _payment_audit_tx_filter(tx)
        if tx_filter:
            await db.payment_transactions.update_one(
                tx_filter,
                {
                    "$set": {
                        "notification_sent": True,
                        "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                        "notification_suppressed": True,
                        "notification_suppression_reason": str(
                            tx.get("notification_suppression_reason") or "synthetic_internal_transaction"
                        ),
                    }
                },
            )
        return {
            "status": "skipped",
            "reason": "suppressed_synthetic_transaction",
            "transaction_id": tx.get("transaction_id"),
            "payment_id": tx.get("payment_id"),
            "session_id": tx.get("session_id"),
        }

    user_id = tx.get("user_id")
    if not user_id:
        return {"status": "skipped", "reason": "missing_user_id"}

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1, "subscription_end_date": 1})
    if not user_doc or not user_doc.get("email"):
        return {"status": "skipped", "reason": "missing_user_email", "user_id": user_id}

    plan_id = tx.get("plan_id", "free")
    plan = await get_subscription_plan_from_gps(plan_id) or {"name": str(plan_id).title()}
    billing_period = tx.get("billing_period", "monthly")

    renewal_source = user_doc.get("subscription_end_date")
    if hasattr(renewal_source, "strftime"):
        renewal_date = renewal_source.strftime("%b %d, %Y")
    elif isinstance(renewal_source, str) and renewal_source:
        renewal_date = renewal_source[:10]
    else:
        renewal_date = (datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)).strftime("%b %d, %Y")

    ticket_suffix = tx.get("session_id") or tx.get("payment_id") or uuid.uuid4().hex[:6]
    ticket_id = f"RCV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(ticket_suffix)[-6:].upper()}"

    amount_gross = _safe_float(tx.get("amount_gross", tx.get("amount_usd", tx.get("amount", 0))), 0.0)
    amount_local = _safe_float(tx.get("amount_local", tx.get("total_amount", amount_gross)), amount_gross)
    currency = str(tx.get("currency", "USD")).upper()
    method_label = str(tx.get("provider") or tx.get("payment_method") or "payment")

    await _send_payment_notification_cb(
        user_id=user_id,
        email=user_doc.get("email", ""),
        user_name=user_doc.get("name", ""),
        plan_name=plan.get("name", str(plan_id).title()),
        amount=amount_gross,
        payment_method=method_label,
        ticket_id=ticket_id,
        billing_cycle=billing_period,
        renewal_date=renewal_date,
        currency=currency,
        amount_local=amount_local,
        transaction_context=tx,
    )

    tx_filter = {"session_id": tx.get("session_id")} if tx.get("session_id") else {"payment_id": tx.get("payment_id")}
    await db.payment_transactions.update_one(
        tx_filter,
        {
            "$set": {
                "notification_sent": True,
                "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                "notification_recovered": True,
            }
        },
    )

    return {
        "status": "recovered",
        "user_id": user_id,
        "ticket_id": ticket_id,
        "session_id": tx.get("session_id"),
        "payment_id": tx.get("payment_id"),
    }


@router.post("/admin/payments/recover-missed-notifications")
async def recover_missed_payment_notifications(request: Request):
    """Admin action: replay notifications for completed transactions missing notification_sent."""
    user = await _get_user_from_request(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    limit = max(1, min(int(body.get("limit", 50)), 200))
    provider = str(body.get("provider", "")).strip().lower()
    query = build_missed_notification_recovery_query(provider)
    txs = await db.payment_transactions.find(query, {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)

    recovered = 0
    skipped = 0
    failed = 0
    details: list[Dict[str, Any]] = []

    for tx in txs:
        try:
            outcome = await recover_missed_notification_for_transaction(tx)
            details.append(outcome)
            if outcome.get("status") == "recovered":
                recovered += 1
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            details.append(
                {
                    "status": "failed",
                    "error": str(exc),
                    "session_id": tx.get("session_id"),
                    "payment_id": tx.get("payment_id"),
                }
            )

    return {
        "success": True,
        "scanned": len(txs),
        "recovered": recovered,
        "skipped": skipped,
        "failed": failed,
        "provider_filter": provider or "all",
        "details": details[:30],
    }