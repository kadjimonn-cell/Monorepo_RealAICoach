from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
import re
from fpdf import FPDF
from pydantic import BaseModel, Field

from routes.db import db, require_admin, EMERGENT_LLM_KEY
from utils.pdf_v15_filename import build_pdf_v15_filename

# Canonical admin dependency alias for backward compatibility
_require_admin = require_admin

router = APIRouter(prefix="/admin/payments-tax-intelligence", tags=["Admin Payments Tax Intelligence"])


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")
    return themed


SCENARIO_RUNNER_CASES = {
    "san-antonio-paypal-annual-basic": {
        "scenario_id": "san-antonio-paypal-annual-basic",
        "label": "Texas / PayPal — Basic Annual",
        "description": "Replays the San Antonio PayPal annual basic scenario for regression validation.",
        "provider": "PayPal",
        "jurisdiction": "US-TX",
        "plan": "basic-yearly",
        "test_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "test_san_antonio_paypal_annual_basic_scenario_1078.py"),
    },
    "quebec-paypal-annual-premium": {
        "scenario_id": "quebec-paypal-annual-premium",
        "label": "Quebec / PayPal — Premium Annual",
        "description": "Replays the Quebec PayPal annual premium scenario with localization coverage.",
        "provider": "PayPal",
        "jurisdiction": "CA-QC",
        "plan": "premium-yearly",
        "test_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "test_quebec_paypal_annual_premium_scenario_1073.py"),
    },
    "senegal-fedapay-annual-basic": {
        "scenario_id": "senegal-fedapay-annual-basic",
        "label": "Senegal / FedaPay — Basic Annual",
        "description": "Replays the Senegal FedaPay annual basic flow, including receipt + notification validation.",
        "provider": "FedaPay",
        "jurisdiction": "SN",
        "plan": "basic-yearly",
        "test_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "test_senegal_fedapay_annual_basic.py"),
    },
    "benin-fedapay-annual-premium": {
        "scenario_id": "benin-fedapay-annual-premium",
        "label": "Benin / FedaPay — Premium Annual",
        "description": "Replays the Benin FedaPay annual premium flow for payment, notification, and receipt parity.",
        "provider": "FedaPay",
        "jurisdiction": "BJ",
        "plan": "premium-yearly",
        "test_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "test_benin_fedapay_annual_premium_scenario_1067.py"),
    },
    "geo-payment-matrix": {
        "scenario_id": "geo-payment-matrix",
        "label": "West Africa Matrix — FedaPay",
        "description": "Runs the geo payment regression matrix across Benin, Togo, Senegal, Côte d’Ivoire, and Niger.",
        "provider": "FedaPay",
        "jurisdiction": "WA-MATRIX",
        "plan": "matrix",
        "test_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "test_geo_payment_regression_matrix_1061.py"),
    },
}


def _parse_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _period_to_since(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    mapping = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
        "365d": timedelta(days=365),
        "ytd": timedelta(days=365),
    }
    return now - mapping.get(period, timedelta(days=30))


def _provider_label(raw: str) -> str:
    value = str(raw or "unknown").lower()
    if "paypal" in value:
        return "PayPal"
    if "stripe" in value:
        return "Stripe"
    if "fedapay" in value or "mobile_money" in value:
        return "FedaPay"
    if "apple" in value:
        return "Apple IAP"
    if "google" in value:
        return "Google IAP"
    return str(raw or "Unknown")


def _status_label(raw: str) -> str:
    value = str(raw or "unknown").lower()
    if value in {"completed", "paid", "succeeded", "active"}:
        return "completed"
    if value in {"failed", "declined", "expired", "cancelled", "canceled"}:
        return "failed"
    if value in {"refunded", "reversed", "refund"}:
        return "refunded"
    if value in {"chargeback", "disputed", "dispute"}:
        return "disputed"
    return value


def _risk_score(tx: dict, recovery_status: str) -> int:
    score = 8
    status = _status_label(tx.get("payment_status") or tx.get("status"))
    if status == "failed":
        score += 28
    if status == "refunded":
        score += 20
    if status == "disputed":
        score += 35
    if recovery_status == "recovery_pending":
        score += 25
    if not tx.get("jurisdiction"):
        score += 10
    if not (tx.get("locale") or tx.get("preferred_language") or (tx.get("localization_context") or {}).get("resolved_language")):
        score += 8
    gross = float(tx.get("amount_gross") or tx.get("total_amount") or 0)
    fee = float(tx.get("processing_fee") or 0)
    if gross > 0 and (fee / gross) > 0.06:
        score += 8
    return min(score, 100)


async def _recent_recovery_map(transaction_ids: list[str], payment_ids: list[str], session_ids: list[str]) -> dict:
    values = [value for value in set(transaction_ids + payment_ids + session_ids) if value]
    if not values:
        return {}
    rows = await db.notification_recovery_queue.find(
        {
            "$or": [
                {"transaction_id": {"$in": values}},
                {"payment_id": {"$in": values}},
                {"session_id": {"$in": values}},
            ]
        },
        {"_id": 0, "transaction_id": 1, "payment_id": 1, "session_id": 1, "status": 1},
    ).to_list(500)
    mapped: dict[str, str] = {}
    for row in rows:
        status = str(row.get("status") or "pending")
        for key in (row.get("transaction_id"), row.get("payment_id"), row.get("session_id")):
            if key:
                mapped[str(key)] = status
    return mapped


async def _ops_case_map(reference_ids: list[str]) -> dict[str, dict]:
    refs = [str(item) for item in reference_ids if item]
    if not refs:
        return {}
    rows = await db.payment_ops_cases.find({"reference_id": {"$in": refs}}, {"_id": 0}).to_list(500)
    return {str(row.get("reference_id")): row for row in rows if row.get("reference_id")}


def _build_case_history_event(*, action: str, actor_email: str, owner_email: Optional[str], status: str, note: str) -> dict:
    return {
        "event_id": f"oph_{uuid.uuid4().hex[:10]}",
        "action": action,
        "actor_email": actor_email,
        "owner_email": owner_email,
        "status": status,
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _derive_queue_type(row: dict) -> str:
    if row.get("status") in {"failed", "refunded", "disputed"}:
        return "dispute"
    return "reconciliation"


def _derive_priority(row: dict) -> str:
    status = str(row.get("status") or "").lower()
    risk = int(row.get("risk_score") or 0)
    if status == "disputed" or risk >= 85:
        return "critical"
    if status in {"failed", "refunded"} or row.get("notification_status") == "recovery_pending":
        return "high"
    if not row.get("jurisdiction") or not row.get("resolved_language"):
        return "medium"
    return "low"


def _sla_target_minutes(queue_type: str, priority: str) -> int:
    matrix = {
        "dispute": {"critical": 120, "high": 240, "medium": 480, "low": 720},
        "reconciliation": {"critical": 240, "high": 360, "medium": 720, "low": 1440},
    }
    return matrix.get(queue_type, matrix["reconciliation"]).get(priority, 720)


def _compute_sla_metrics(*, opened_at: Any, queue_type: str, priority: str, case_status: str) -> dict:
    now = datetime.now(timezone.utc)
    opened_dt = _parse_iso(opened_at) or now
    target_minutes = _sla_target_minutes(queue_type, priority)
    due_at = opened_dt + timedelta(minutes=target_minutes)
    minutes_open = max(int((now - opened_dt).total_seconds() // 60), 0)
    if case_status == "resolved":
        sla_status = "resolved"
    elif now >= due_at:
        sla_status = "breached"
    elif now >= due_at - timedelta(minutes=min(60, max(target_minutes // 4, 15))):
        sla_status = "due_soon"
    else:
        sla_status = "healthy"
    return {
        "opened_at": opened_dt.isoformat(),
        "due_at": due_at.isoformat(),
        "target_minutes": target_minutes,
        "minutes_open": minutes_open,
        "minutes_overdue": max(int((now - due_at).total_seconds() // 60), 0) if now >= due_at else 0,
        "sla_status": sla_status,
    }


def _ops_issue_summary(row: dict, queue_type: str) -> str:
    if queue_type == "dispute":
        status = str(row.get("status") or "issue").replace("_", " ").title()
        return f"{row.get('provider')} {status} requires operator review."
    issues = []
    if row.get("notification_status") == "recovery_pending":
        issues.append("notification recovery pending")
    if not row.get("jurisdiction"):
        issues.append("jurisdiction metadata missing")
    if not row.get("resolved_language"):
        issues.append("language resolution missing")
    if not issues:
        issues.append("operator follow-up required")
    return f"{row.get('provider')} reconciliation: {', '.join(issues)}."


def _normalize_transaction(tx: dict, recovery_map: dict[str, str]) -> dict:
    transaction_id = str(tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id") or tx.get("original_transaction_id") or "")
    payment_id = str(tx.get("payment_id") or tx.get("original_transaction_id") or tx.get("order_id") or "")
    session_id = str(tx.get("session_id") or "")
    provider = _provider_label(tx.get("provider") or tx.get("payment_method") or tx.get("platform") or "")
    status = _status_label(tx.get("payment_status") or tx.get("status"))
    localization_context = tx.get("localization_context", {}) if isinstance(tx.get("localization_context"), dict) else {}
    jurisdiction = tx.get("jurisdiction", {}) if isinstance(tx.get("jurisdiction"), dict) else {}
    recovery_status = "sent" if tx.get("notification_sent") else "recovery_pending" if recovery_map.get(transaction_id) or recovery_map.get(payment_id) or recovery_map.get(session_id) else "pending"
    resolved_language = str(
        localization_context.get("resolved_language")
        or tx.get("preferred_language")
        or tx.get("locale")
        or tx.get("language")
        or "en"
    ).lower()
    return {
        "transaction_id": transaction_id,
        "payment_id": payment_id,
        "session_id": session_id,
        "provider": provider,
        "provider_key": str(tx.get("provider") or tx.get("payment_method") or tx.get("platform") or "").lower(),
        "status": status,
        "created_at": tx.get("created_at") or tx.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "user_id": str(tx.get("user_id") or ""),
        "plan_id": str(tx.get("plan_id") or tx.get("subscription_plan") or ""),
        "billing_period": str(tx.get("billing_period") or ""),
        "subtotal": float(tx.get("subtotal") or 0),
        "tax_amount": float(tx.get("tax_amount") or 0),
        "processing_fee": float(tx.get("processing_fee") or 0),
        "amount_gross": float(tx.get("amount_gross") or tx.get("total_amount") or tx.get("amount_local") or tx.get("amount") or 0),
        "amount_net": float(tx.get("amount_net") or tx.get("amount_gross") or tx.get("total_amount") or tx.get("amount_local") or tx.get("amount") or 0),
        "total_amount": float(tx.get("total_amount") or tx.get("amount_gross") or tx.get("amount_local") or tx.get("amount") or 0),
        "amount_usd": float(tx.get("amount_usd") or tx.get("original_usd_amount") or tx.get("amount") or 0),
        "currency": str(tx.get("currency") or "USD").upper(),
        "fx_rate": float(tx.get("fx_rate") or 1.0),
        "fx_base_currency": str(tx.get("fx_base_currency") or "USD").upper(),
        "jurisdiction": jurisdiction,
        "resolved_language": resolved_language,
        "tax_source": str(tx.get("tax_provider") or tx.get("tax_engine") or "internal_rules_engine"),
        "notification_status": recovery_status,
        "notification_sent": bool(tx.get("notification_sent")),
        "risk_score": _risk_score(tx, recovery_status),
    }


async def _load_transactions(*, period: str, provider: str = "all", search: str = "", limit: int = 120) -> list[dict]:
    since = _period_to_since(period).isoformat()
    query: Dict[str, Any] = {"created_at": {"$gte": since}}
    provider_filter = provider.strip().lower()
    if provider_filter and provider_filter != "all":
        if provider_filter == "apple":
            query["provider"] = {"$in": ["iap_apple", "apple", "apple_iap"]}
        elif provider_filter == "google":
            query["provider"] = {"$in": ["iap_google", "google", "google_iap"]}
        else:
            query["provider"] = {"$regex": re.escape(str(provider_filter))}

    if search.strip():
        value = search.strip()
        query["$or"] = [
            {"transaction_id": {"$regex": re.escape(str(value)), "$options": "i"}},
            {"payment_id": {"$regex": re.escape(str(value)), "$options": "i"}},
            {"session_id": {"$regex": re.escape(str(value)), "$options": "i"}},
            {"user_id": {"$regex": re.escape(str(value)), "$options": "i"}},
            {"provider": {"$regex": re.escape(str(value)), "$options": "i"}},
        ]

    payment_rows = await db.payment_transactions.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    iap_rows = await db.iap_transactions.find({"created_at": {"$gte": since}}, {"_id": 0}).sort("created_at", -1).limit(40).to_list(40)

    normalized_iap = []
    for row in iap_rows:
        provider_key = f"iap_{str(row.get('platform') or '').lower()}"
        normalized_iap.append(
            {
                "transaction_id": row.get("transaction_id") or row.get("order_id") or row.get("original_transaction_id"),
                "payment_id": row.get("transaction_id") or row.get("order_id"),
                "session_id": row.get("original_transaction_id") or row.get("order_id"),
                "user_id": row.get("user_id"),
                "plan_id": row.get("plan") or "",
                "billing_period": row.get("period") or "",
                "provider": provider_key,
                "payment_method": provider_key,
                "payment_status": "completed" if row.get("active") else "pending",
                "subtotal": row.get("amount") or 0,
                "tax_amount": row.get("tax_amount") or 0,
                "processing_fee": row.get("processing_fee") or 0,
                "amount_gross": row.get("amount") or 0,
                "amount_net": row.get("amount") or 0,
                "total_amount": row.get("amount") or 0,
                "currency": row.get("currency") or "USD",
                "jurisdiction": row.get("jurisdiction") or {},
                "preferred_language": row.get("preferred_language") or row.get("locale") or "en",
                "localization_context": row.get("localization_context") or {},
                "created_at": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
        )

    combined = payment_rows + normalized_iap
    tx_ids = [str(row.get("transaction_id") or "") for row in combined]
    payment_ids = [str(row.get("payment_id") or "") for row in combined]
    session_ids = [str(row.get("session_id") or row.get("original_transaction_id") or "") for row in combined]
    recovery_map = await _recent_recovery_map(tx_ids, payment_ids, session_ids)

    rows = [_normalize_transaction(row, recovery_map) for row in combined]
    case_map = await _ops_case_map([row.get("transaction_id") or row.get("payment_id") or row.get("session_id") for row in rows])
    for row in rows:
        ref = row.get("transaction_id") or row.get("payment_id") or row.get("session_id")
        row["ops_case"] = case_map.get(str(ref), {})
    rows.sort(key=lambda row: _parse_iso(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if provider_filter and provider_filter != "all":
        rows = [row for row in rows if provider_filter in row.get("provider_key", "") or provider_filter in row.get("provider", "").lower()]
    if search.strip():
        value = search.strip().lower()
        rows = [row for row in rows if value in json.dumps(row, default=str).lower()]
    return rows[:limit]


class BulkPaymentOpsActionRequest(BaseModel):
    action: Literal["retry_notifications", "replay_webhook", "assign_owner", "resolve_case"]
    reference_ids: list[str] = Field(default_factory=list)
    owner_email: Optional[str] = None
    note: Optional[str] = None


class PaymentAuditAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


class DeadLetterAutoTriggerPolicyRequest(BaseModel):
    enabled: bool = False
    dead_threshold: int = 5
    replay_limit: int = 30


async def _upsert_payment_ops_case(reference_id: str, update_fields: dict, history_event: Optional[dict] = None) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    update_doc: dict[str, Any] = {
        "$set": {**update_fields, "reference_id": reference_id, "updated_at": now_iso},
        "$setOnInsert": {"created_at": now_iso},
    }
    if history_event:
        update_doc["$push"] = {"history": {"$each": [history_event], "$slice": -50}}
    await db.payment_ops_cases.update_one({"reference_id": reference_id}, update_doc, upsert=True)
    return await db.payment_ops_cases.find_one({"reference_id": reference_id}, {"_id": 0}) or {}


async def _run_bulk_payment_ops_action(*, actor_email: str, body: BulkPaymentOpsActionRequest) -> dict:
    refs = [str(item).strip() for item in body.reference_ids if str(item).strip()]
    if not refs:
        raise HTTPException(status_code=400, detail="reference_ids required")

    results = []
    fedapay_refs = []
    for ref in refs:
        tx = await _find_transaction_by_reference(ref)
        provider_key = str(tx.get("provider") or tx.get("payment_method") or "").lower()
        action_status = "recorded"
        note = body.note or ""

        if body.action == "retry_notifications":
            tx_ref = tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id") or ref
            existing = await db.notification_recovery_queue.find_one({"$or": [{"transaction_id": tx_ref}, {"payment_id": tx.get("payment_id")}, {"session_id": tx.get("session_id")}]}, {"_id": 0})
            if existing:
                await db.notification_recovery_queue.update_one(
                    {"queue_id": existing.get("queue_id")},
                    {"$set": {"status": "pending", "updated_at": datetime.now(timezone.utc).isoformat(), "reason": note or "manual_retry_requested"}},
                )
            else:
                await db.notification_recovery_queue.insert_one(
                    {
                        "queue_id": f"notifq_{uuid.uuid4().hex[:12]}",
                        "transaction_id": tx.get("transaction_id"),
                        "payment_id": tx.get("payment_id"),
                        "session_id": tx.get("session_id"),
                        "user_id": tx.get("user_id"),
                        "provider": tx.get("provider") or tx.get("payment_method"),
                        "status": "pending",
                        "retry_count": 0,
                        "reason": note or "manual_retry_requested",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            await db.payment_transactions.update_one({"transaction_id": tx.get("transaction_id")}, {"$set": {"notification_sent": False}})
            await _upsert_payment_ops_case(
                ref,
                {"status": "retry_requested", "owner_email": body.owner_email or actor_email, "last_action": body.action, "last_note": note},
                _build_case_history_event(action=body.action, actor_email=actor_email, owner_email=body.owner_email or actor_email, status="retry_requested", note=note),
            )

        elif body.action == "replay_webhook":
            if "fedapay" in provider_key or "mobile_money" in provider_key:
                fedapay_refs.append(ref)
                action_status = "queued"
            else:
                action_status = "unsupported_provider"
            await _upsert_payment_ops_case(
                ref,
                {"status": "webhook_replay_requested", "owner_email": body.owner_email or actor_email, "last_action": body.action, "last_note": note},
                _build_case_history_event(action=body.action, actor_email=actor_email, owner_email=body.owner_email or actor_email, status="webhook_replay_requested", note=note),
            )

        elif body.action == "assign_owner":
            owner = body.owner_email or actor_email
            await _upsert_payment_ops_case(
                ref,
                {"status": "assigned", "owner_email": owner, "last_action": body.action, "last_note": note},
                _build_case_history_event(action=body.action, actor_email=actor_email, owner_email=owner, status="assigned", note=note),
            )

        elif body.action == "resolve_case":
            await _upsert_payment_ops_case(
                ref,
                {"status": "resolved", "owner_email": body.owner_email or actor_email, "resolved_by": actor_email, "resolved_at": datetime.now(timezone.utc).isoformat(), "last_action": body.action, "last_note": note},
                _build_case_history_event(action=body.action, actor_email=actor_email, owner_email=body.owner_email or actor_email, status="resolved", note=note),
            )

        await db.payment_ops_action_log.insert_one(
            {
                "action_id": f"poa_{uuid.uuid4().hex[:12]}",
                "reference_id": ref,
                "action": body.action,
                "actor_email": actor_email,
                "owner_email": body.owner_email,
                "note": note,
                "status": action_status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        results.append({"reference_id": ref, "status": action_status})

    if fedapay_refs:
        try:
            from routes.fedapay_client import sync_webhook_url
            from routes.payments import run_fedapay_webhook_retry_cycle, run_fedapay_webhook_dead_replay_cycle
            await sync_webhook_url()
            await run_fedapay_webhook_retry_cycle(limit=max(1, len(fedapay_refs)))
            await run_fedapay_webhook_dead_replay_cycle(limit=max(1, len(fedapay_refs)))
            for item in results:
                if item["reference_id"] in fedapay_refs:
                    item["status"] = "replayed"
        except Exception as exc:
            for item in results:
                if item["reference_id"] in fedapay_refs:
                    item["status"] = f"replay_failed: {exc}"

    return {
        "success": True,
        "action": body.action,
        "total": len(refs),
        "results": results,
    }


async def _compute_overview(period: str) -> dict:
    transactions = await _load_transactions(period=period, limit=180)
    since = _period_to_since(period)
    previous_since = since - (datetime.now(timezone.utc) - since)
    previous_rows = await _load_transactions(period="90d" if period == "365d" else period, limit=360)
    current_revenue = sum(row["total_amount"] for row in transactions if row["status"] == "completed")
    previous_revenue = sum(
        row["total_amount"]
        for row in previous_rows
        if row["status"] == "completed" and (_parse_iso(row.get("created_at")) or since) < since and (_parse_iso(row.get("created_at")) or previous_since) >= previous_since
    )
    total_tax = sum(row["tax_amount"] for row in transactions if row["status"] == "completed")
    total_fees = sum(row["processing_fee"] for row in transactions if row["status"] == "completed")
    refunds = sum(1 for row in transactions if row["status"] == "refunded")
    disputes = sum(1 for row in transactions if row["status"] == "disputed")
    completed = [row for row in transactions if row["status"] == "completed"]
    failures = [row for row in transactions if row["status"] == "failed"]
    recovery_pending = [row for row in transactions if row["notification_status"] == "recovery_pending"]

    active_users = await db.users.count_documents({"subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    canceled_recent = await db.users.count_documents({"subscription_status": "cancelled", "updated_at": {"$gte": since.isoformat()}})
    mrr = 0.0
    from routes.payments_catalog import get_subscription_plans_from_gps
    gps_plans = await get_subscription_plans_from_gps()
    for plan_id, cfg in gps_plans.items():
        if plan_id == "free":
            continue
        active_count = await db.users.count_documents({"subscription_status": "active", "subscription_plan": plan_id})
        mrr += active_count * float(cfg.get("monthly_price", 0))
    arr = round(mrr * 12, 2)
    arpu = round(mrr / max(active_users, 1), 2)
    churn_rate = round((canceled_recent / max(active_users + canceled_recent, 1)) * 100, 1)
    ltv = round(arpu / max(churn_rate / 100 or 0.05, 0.05), 2)

    provider_buckets: dict[str, dict] = {}
    for row in transactions:
        key = row["provider"]
        provider_buckets.setdefault(key, {
            "provider": key,
            "count": 0,
            "completed": 0,
            "failed": 0,
            "refunded": 0,
            "gross": 0.0,
            "tax": 0.0,
            "fees": 0.0,
            "recovery_pending": 0,
        })
        bucket = provider_buckets[key]
        bucket["count"] += 1
        bucket["gross"] += row["total_amount"]
        bucket["tax"] += row["tax_amount"]
        bucket["fees"] += row["processing_fee"]
        if row["status"] == "completed":
            bucket["completed"] += 1
        if row["status"] == "failed":
            bucket["failed"] += 1
        if row["status"] == "refunded":
            bucket["refunded"] += 1
        if row["notification_status"] == "recovery_pending":
            bucket["recovery_pending"] += 1

    provider_summaries = []
    for bucket in provider_buckets.values():
        success_rate = round((bucket["completed"] / max(bucket["count"], 1)) * 100, 1)
        provider_summaries.append({
            **bucket,
            "success_rate": success_rate,
            "status": "healthy" if success_rate >= 85 and bucket["recovery_pending"] == 0 else "warning" if success_rate >= 65 else "critical",
        })
    provider_summaries.sort(key=lambda item: item["gross"], reverse=True)

    fedapay_fallback_rows = await db.payment_transactions.find(
        {"fallback_from": "fedapay", "created_at": {"$gte": since.isoformat()}},
        {"_id": 0, "total_amount": 1, "payment_status": 1, "fedapay_error": 1, "created_at": 1, "payment_id": 1, "transaction_id": 1},
    ).to_list(50)
    fallback_total = len(fedapay_fallback_rows)
    fallback_completed = sum(1 for row in fedapay_fallback_rows if _status_label(row.get("payment_status") or row.get("status")) == "completed")
    fallback_revenue = round(sum(float(row.get("total_amount") or 0) for row in fedapay_fallback_rows if _status_label(row.get("payment_status") or row.get("status")) == "completed"), 2)
    fallback_reasons = [{"fedapay_error": row.get("fedapay_error"), "created_at": row.get("created_at"), "payment_id": row.get("payment_id"), "transaction_id": row.get("transaction_id")} for row in fedapay_fallback_rows[:12]]

    trend_buckets: dict[str, dict] = {}
    for row in completed:
        dt = _parse_iso(row.get("created_at")) or datetime.now(timezone.utc)
        key = dt.strftime("%Y-%m-%d")
        trend_buckets.setdefault(key, {"date": key, "revenue": 0.0, "tax": 0.0, "fees": 0.0, "count": 0})
        trend_buckets[key]["revenue"] += row["total_amount"]
        trend_buckets[key]["tax"] += row["tax_amount"]
        trend_buckets[key]["fees"] += row["processing_fee"]
        trend_buckets[key]["count"] += 1
    trend = [trend_buckets[key] for key in sorted(trend_buckets.keys())][-30:]

    alerts = []
    if failures and len(failures) / max(len(transactions), 1) > 0.15:
        alerts.append({"severity": "high", "title": "Failure spike", "message": f"{len(failures)} failed transactions detected in {period}."})
    if recovery_pending:
        alerts.append({"severity": "medium", "title": "Notification recovery backlog", "message": f"{len(recovery_pending)} transactions still need notification recovery."})
    if previous_revenue > 0 and current_revenue < previous_revenue * 0.8:
        alerts.append({"severity": "high", "title": "Revenue drop", "message": f"Revenue is down {round(((previous_revenue - current_revenue) / previous_revenue) * 100, 1)}% versus the previous window."})
    if refunds > 0:
        alerts.append({"severity": "medium", "title": "Refund activity", "message": f"{refunds} refunded transactions detected."})
    if disputes > 0:
        alerts.append({"severity": "high", "title": "Dispute activity", "message": f"{disputes} disputed transactions require review."})

    fedapay_dead = await db.fedapay_webhook_events.count_documents({"status": "dead"})
    finance_health_score = max(40, 100 - (len(failures) * 2) - (len(recovery_pending) * 4) - (refunds * 3) - (disputes * 5) - (fedapay_dead * 2))

    ai_brief = await _generate_ai_brief(
        period=period,
        summary={
            "current_revenue": round(current_revenue, 2),
            "tax": round(total_tax, 2),
            "fees": round(total_fees, 2),
            "mrr": round(mrr, 2),
            "arr": arr,
            "ltv": ltv,
            "churn_rate": churn_rate,
            "alerts": alerts,
            "providers": provider_summaries[:5],
        },
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "kpis": {
            "mrr": round(mrr, 2),
            "arr": arr,
            "ltv": ltv,
            "churn_rate": churn_rate,
            "net_revenue": round(current_revenue - total_fees, 2),
            "tax_liability": round(total_tax, 2),
            "active_disputes": disputes,
            "avg_processing_fee_pct": round((total_fees / max(current_revenue, 1)) * 100, 2),
            "active_subscribers": active_users,
            "finance_health_score": round(finance_health_score, 1),
        },
        "trend": trend,
        "provider_summaries": provider_summaries,
        "alerts": alerts,
        "webhook_ops": {
            "fedapay_dead": fedapay_dead,
            "notification_recovery_pending": len(recovery_pending),
            "immutable_ledger_entries": await db.financial_ledger_entries.count_documents({}),
        },
        "fallback_analytics": {
            "fallback_total": fallback_total,
            "fallback_completed": fallback_completed,
            "fallback_conversion_rate": round((fallback_completed / max(fallback_total, 1)) * 100, 1) if fallback_total else 0.0,
            "fallback_revenue": fallback_revenue,
            "recent_reasons": fallback_reasons,
        },
        "recent_transactions": transactions[:40],
        "ai_brief": ai_brief,
    }


async def _generate_ai_brief(*, period: str, summary: dict) -> dict:
    if not EMERGENT_LLM_KEY:
        return {
            "status": "deterministic_only",
            "headline": "AI brief unavailable — using deterministic alerts.",
            "highlights": [alert["message"] for alert in summary.get("alerts", [])[:3]],
        }

    fingerprint = json.dumps({"period": period, "summary": summary}, sort_keys=True)
    cache_key = str(hash(fingerprint))
    cached = await db.payments_tax_ai_briefs.find_one({"cache_key": cache_key}, {"_id": 0}, sort=[("generated_at", -1)])
    if cached:
        return cached

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"payments-tax-brief-{uuid.uuid4().hex[:10]}",
            system_message=(
                "You are an enterprise finance copilot. Return JSON only with keys headline, highlights, risk_level, forecast. "
                "Keep it concise, factual, and admin-safe."
            ),
        ).with_model("openai", "gpt-4o")
        raw = await chat.send_message(UserMessage(text=json.dumps(summary, ensure_ascii=False)))
        parsed = {}
        try:
            parsed = json.loads(raw)
        except Exception:
            start = str(raw).find("{")
            end = str(raw).rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(str(raw)[start : end + 1])
        result = {
            "cache_key": cache_key,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "ai_generated",
            "headline": parsed.get("headline") or "AI finance brief generated.",
            "highlights": parsed.get("highlights") or [],
            "risk_level": parsed.get("risk_level") or "medium",
            "forecast": parsed.get("forecast") or "Monitor next window.",
        }
        await db.payments_tax_ai_briefs.insert_one({**result})
        return result
    except Exception:
        return {
            "status": "deterministic_fallback",
            "headline": "Deterministic finance brief",
            "highlights": [alert["message"] for alert in summary.get("alerts", [])[:3]],
            "risk_level": "medium" if summary.get("alerts") else "low",
            "forecast": "Stable unless failure/refund volume increases.",
        }


async def _generate_ai_forecast(summary: dict) -> dict:
    if not EMERGENT_LLM_KEY:
        return {
            "status": "deterministic_only",
            "headline": "AI forecast unavailable — using deterministic projection.",
            "commentary": summary.get("deterministic_commentary", "Projection generated from historical averages."),
        }

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"payments-tax-forecast-{uuid.uuid4().hex[:10]}",
            system_message=(
                "You are an enterprise finance forecasting assistant. Return JSON only with keys headline, commentary, risk_level."
            ),
        ).with_model("openai", "gpt-4o")
        raw = await chat.send_message(UserMessage(text=json.dumps(summary, ensure_ascii=False)))
        parsed = json.loads(raw) if str(raw).strip().startswith("{") else {}
        return {
            "status": "ai_generated",
            "headline": parsed.get("headline") or "AI forecast generated.",
            "commentary": parsed.get("commentary") or summary.get("deterministic_commentary", ""),
            "risk_level": parsed.get("risk_level") or "medium",
        }
    except Exception:
        return {
            "status": "deterministic_fallback",
            "headline": "Deterministic forecast",
            "commentary": summary.get("deterministic_commentary", "Projection generated from historical averages."),
            "risk_level": "medium",
        }


async def _collect_ops_queue(*, actor_email: str, period: str, owner: str, status: str, limit: int) -> dict:
    rows = await _load_transactions(period=period, limit=max(limit * 3, 160))
    owner_filter = str(owner or "all").strip().lower()
    status_filter = str(status or "open").strip().lower()
    normalized_actor = str(actor_email or "admin@realaicoach.app").lower()

    queue_items = []
    for row in rows:
        ops_case = row.get("ops_case") or {}
        queue_type = _derive_queue_type(row)
        has_issue = bool(ops_case) or queue_type == "dispute" or row.get("notification_status") == "recovery_pending" or not row.get("jurisdiction") or not row.get("resolved_language")
        if not has_issue:
            continue

        case_status = str(ops_case.get("status") or "open").lower()
        priority = _derive_priority(row)
        sla = _compute_sla_metrics(
            opened_at=ops_case.get("created_at") or row.get("created_at"),
            queue_type=queue_type,
            priority=priority,
            case_status=case_status,
        )
        owner_email = str(ops_case.get("owner_email") or "")
        owner_normalized = owner_email.lower()
        if owner_filter == "me" and owner_normalized != normalized_actor:
            continue
        if owner_filter == "unassigned" and owner_normalized:
            continue
        if owner_filter not in {"all", "me", "unassigned"} and owner_normalized != owner_filter:
            continue
        if status_filter == "open" and case_status == "resolved":
            continue
        if status_filter == "resolved" and case_status != "resolved":
            continue
        if status_filter == "breached" and sla["sla_status"] != "breached":
            continue

        queue_items.append({
            "reference_id": row.get("transaction_id") or row.get("payment_id") or row.get("session_id"),
            "queue_type": queue_type,
            "priority": priority,
            "provider": row.get("provider"),
            "status": row.get("status"),
            "owner_email": owner_email,
            "case_status": case_status,
            "issue_summary": _ops_issue_summary(row, queue_type),
            "amount": row.get("total_amount"),
            "currency": row.get("currency"),
            "risk_score": row.get("risk_score"),
            "notification_status": row.get("notification_status"),
            "history": ops_case.get("history", [])[-5:],
            "created_at": row.get("created_at"),
            **sla,
        })

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sla_order = {"breached": 0, "due_soon": 1, "healthy": 2, "resolved": 3}
    queue_items.sort(key=lambda item: (
        sla_order.get(item.get("sla_status"), 4),
        priority_order.get(item.get("priority"), 4),
        -int(item.get("minutes_open") or 0),
    ))

    owner_summary: dict[str, dict[str, Any]] = {}
    for item in queue_items:
        owner_key = item.get("owner_email") or "Unassigned"
        owner_summary.setdefault(owner_key, {"owner_email": owner_key, "open_cases": 0, "breached": 0, "due_soon": 0})
        if item.get("case_status") != "resolved":
            owner_summary[owner_key]["open_cases"] += 1
        if item.get("sla_status") == "breached":
            owner_summary[owner_key]["breached"] += 1
        if item.get("sla_status") == "due_soon":
            owner_summary[owner_key]["due_soon"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "owner_filter": owner_filter,
        "status_filter": status_filter,
        "summary": {
            "open_cases": sum(1 for item in queue_items if item.get("case_status") != "resolved"),
            "assigned_to_me": sum(1 for item in queue_items if str(item.get("owner_email") or "").lower() == normalized_actor and item.get("case_status") != "resolved"),
            "unassigned": sum(1 for item in queue_items if not item.get("owner_email") and item.get("case_status") != "resolved"),
            "breached": sum(1 for item in queue_items if item.get("sla_status") == "breached"),
            "due_soon": sum(1 for item in queue_items if item.get("sla_status") == "due_soon"),
            "resolved": sum(1 for item in queue_items if item.get("case_status") == "resolved"),
        },
        "owner_summary": sorted(owner_summary.values(), key=lambda item: (-item["breached"], -item["open_cases"], item["owner_email"])),
        "items": queue_items[:limit],
    }


async def _collect_fallback_drilldown(period: str, limit: int) -> dict:
    since = _period_to_since(period).isoformat()
    rows = await db.payment_transactions.find(
        {
            "$or": [
                {"fallback_from": "fedapay"},
                {"fallback_from_provider": "fedapay"},
            ],
            "created_at": {"$gte": since},
        },
        {
            "_id": 0,
            "transaction_id": 1,
            "payment_id": 1,
            "user_id": 1,
            "plan_id": 1,
            "billing_period": 1,
            "created_at": 1,
            "provider": 1,
            "payment_status": 1,
            "status": 1,
            "total_amount": 1,
            "currency": 1,
            "fedapay_error": 1,
            "fallback_reason": 1,
            "fallback_from": 1,
            "fallback_from_provider": 1,
        },
    ).sort("created_at", -1).limit(max(1, min(limit, 200))).to_list(limit)

    reason_map: dict[str, int] = {}
    outcome_map: dict[str, int] = {}
    cases = []
    for row in rows:
        reason = str(row.get("fallback_reason") or row.get("fedapay_error") or "FedaPay unavailable")
        final_status = _status_label(row.get("payment_status") or row.get("status"))
        final_provider = _provider_label(row.get("provider") or "stripe")
        reason_map[reason] = reason_map.get(reason, 0) + 1
        outcome_map[final_status] = outcome_map.get(final_status, 0) + 1
        cases.append({
            "reference_id": row.get("transaction_id") or row.get("payment_id"),
            "payment_id": row.get("payment_id"),
            "transaction_id": row.get("transaction_id"),
            "created_at": row.get("created_at"),
            "user_id": row.get("user_id"),
            "plan_id": row.get("plan_id"),
            "billing_period": row.get("billing_period"),
            "reason": reason,
            "fallback_from": row.get("fallback_from") or row.get("fallback_from_provider") or "fedapay",
            "final_provider": final_provider,
            "final_status": final_status,
            "converted": final_status == "completed",
            "total_amount": float(row.get("total_amount") or 0),
            "currency": str(row.get("currency") or "USD").upper(),
        })

    top_reasons = [{"reason": reason, "count": count} for reason, count in sorted(reason_map.items(), key=lambda item: item[1], reverse=True)[:6]]
    outcomes = [{"status": status, "count": count} for status, count in sorted(outcome_map.items(), key=lambda item: item[1], reverse=True)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "summary": {
            "total_cases": len(cases),
            "converted_cases": sum(1 for item in cases if item["converted"]),
            "converted_revenue": round(sum(item["total_amount"] for item in cases if item["converted"]), 2),
        },
        "top_reasons": top_reasons,
        "outcomes": outcomes,
        "cases": cases,
    }


async def _latest_scenario_runs() -> dict[str, dict]:
    rows = await db.payments_tax_scenario_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(50).to_list(50)
    latest: dict[str, dict] = {}
    for row in rows:
        scenario_id = str(row.get("scenario_id") or "")
        if scenario_id and scenario_id not in latest:
            latest[scenario_id] = row
    return latest


def _scenario_payload(config: dict, latest_run: Optional[dict] = None) -> dict:
    return {
        "scenario_id": config["scenario_id"],
        "label": config["label"],
        "description": config["description"],
        "provider": config["provider"],
        "jurisdiction": config["jurisdiction"],
        "plan": config["plan"],
        "latest_run": latest_run,
    }


async def _run_payment_scenario(*, actor_email: str, scenario_id: str) -> dict:
    config = SCENARIO_RUNNER_CASES.get(scenario_id)
    if not config:
        raise HTTPException(status_code=404, detail="Scenario not found")
    test_file = config["test_file"]
    if not os.path.exists(test_file):
        raise HTTPException(status_code=404, detail="Scenario test file missing")

    run_id = f"psr_{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc).isoformat()
    pytest_bin = shutil.which("pytest") or "/root/.venv/bin/pytest"
    command = [pytest_bin, test_file, "-q"]
    base_record = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "actor_email": actor_email,
        "started_at": started_at,
        "status": "running",
        "command": " ".join(command),
    }
    await db.payments_tax_scenario_runs.insert_one({**base_record})

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=240)
        output = ((stdout or b"") + b"\n" + (stderr or b"")).decode("utf-8", errors="ignore").strip()
        status = "passed" if process.returncode == 0 else "failed"
        result = {
            **base_record,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "return_code": process.returncode,
            "output": output[-12000:],
        }
    except asyncio.TimeoutError:
        if process:
            process.kill()
            await process.communicate()
        result = {
            **base_record,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "timeout",
            "return_code": 124,
            "output": "Scenario timed out after 240 seconds.",
        }

    await db.payments_tax_scenario_runs.update_one({"run_id": run_id}, {"$set": result}, upsert=True)
    return result


async def _find_transaction_by_reference(reference_id: str) -> dict:
    ref = str(reference_id or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="reference_id required")

    tx = await db.payment_transactions.find_one(
        {
            "$or": [
                {"transaction_id": ref},
                {"payment_id": ref},
                {"session_id": ref},
                {"ticket_id": ref},
                {"receipt_number": ref},
            ]
        },
        {"_id": 0},
    )
    if tx:
        return tx

    iap = await db.iap_transactions.find_one(
        {
            "$or": [
                {"transaction_id": ref},
                {"original_transaction_id": ref},
                {"order_id": ref},
            ]
        },
        {"_id": 0},
    )
    if iap:
        return {
            **iap,
            "provider": f"iap_{str(iap.get('platform') or '').lower()}",
            "payment_id": iap.get("transaction_id") or iap.get("order_id"),
            "session_id": iap.get("original_transaction_id") or iap.get("order_id"),
            "payment_status": "completed" if iap.get("status") in {"active", "completed"} or iap.get("active") else iap.get("status", "pending"),
        }
    raise HTTPException(status_code=404, detail="Payment reference not found")


async def _collect_notifications_for_transaction(tx: dict) -> list[dict]:
    identifiers = [
        str(tx.get("transaction_id") or ""),
        str(tx.get("payment_id") or ""),
        str(tx.get("session_id") or ""),
        str(tx.get("ticket_id") or ""),
    ]
    identifiers = [item for item in identifiers if item]
    if not identifiers:
        return []
    return await db.notifications.find(
        {
            "$or": [
                {"metadata.transaction_id": {"$in": identifiers}},
                {"metadata.ticket_id": {"$in": identifiers}},
                {"id": {"$in": identifiers}},
                {"notification_id": {"$in": identifiers}},
            ]
        },
        {"_id": 0},
    ).to_list(50)


async def _collect_payment_audit_snapshot(reference_id: str) -> dict:
    tx = await _find_transaction_by_reference(reference_id)
    normalized = _normalize_transaction(tx, await _recent_recovery_map([str(tx.get("transaction_id") or "")], [str(tx.get("payment_id") or "")], [str(tx.get("session_id") or "")]))
    notifications = await _collect_notifications_for_transaction(tx)
    notification_ids = [row.get("notification_id") or row.get("id") for row in notifications if row.get("notification_id") or row.get("id")]
    user_notifs = [row for row in notifications if row.get("type") == "payment_confirmation"]
    admin_notifs = [row for row in notifications if row.get("type") in {"admin_payment_alert", "admin_payment_failure_alert"}]

    identifiers = [item for item in [tx.get("transaction_id"), tx.get("payment_id"), tx.get("session_id")] if item]
    recovery_rows = await db.notification_recovery_queue.find(
        {"$or": [{"transaction_id": {"$in": identifiers}}, {"payment_id": {"$in": identifiers}}, {"session_id": {"$in": identifiers}}]},
        {"_id": 0},
    ).to_list(20)
    ledger_rows = await db.financial_ledger_entries.find(
        {"transaction_id": tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id")},
        {"_id": 0},
    ).sort("sequence", 1).to_list(50)
    audit_events = await db.payment_audit_timeline_events.find(
        {"transaction_id": tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id")},
        {"_id": 0},
    ).sort("created_at", 1).to_list(100)

    report = {
        "report_id": f"pca_{uuid.uuid4().hex[:12]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_id": reference_id,
        "transaction": normalized,
        "receipt_number": tx.get("receipt_number") or "N/A",
        "ticket_id": tx.get("ticket_id") or "N/A",
        "provider_references": {
            "provider": normalized.get("provider"),
            "payment_id": tx.get("payment_id"),
            "transaction_id": tx.get("transaction_id"),
            "session_id": tx.get("session_id"),
        },
        "customer_charge_total": normalized.get("total_amount"),
        "provider_processing_fee": normalized.get("processing_fee"),
        "net_settlement_after_fee": normalized.get("amount_net"),
        "receipt_delivery": {
            "user_receipt_sent": bool(tx.get("user_receipt_sent")),
            "user_receipt_sent_at": tx.get("user_receipt_sent_at"),
            "admin_receipt_sent": bool(tx.get("admin_receipt_sent")),
            "admin_receipt_sent_at": tx.get("admin_receipt_sent_at"),
            "admin_receipt_events": tx.get("admin_receipt_events", []),
            "confirmation_email_sent": bool(tx.get("confirmation_email_sent")),
            "receipt_delivery_ok": bool(tx.get("receipt_delivery_ok")),
        },
        "notifications": {
            "all_notification_ids": notification_ids,
            "user_notification_ids": [row.get("notification_id") or row.get("id") for row in user_notifs],
            "admin_notification_ids": [row.get("notification_id") or row.get("id") for row in admin_notifs],
            "notification_sent_at": tx.get("notification_sent_at"),
            "status": normalized.get("notification_status"),
        },
        "recovery_queue": recovery_rows,
        "ledger": {
            "count": len(ledger_rows),
            "sequence_min": ledger_rows[0].get("sequence") if ledger_rows else None,
            "sequence_max": ledger_rows[-1].get("sequence") if ledger_rows else None,
            "entries": ledger_rows,
        },
        "audit_events": audit_events,
    }

    await db.payment_confirmation_audit_reports.insert_one({**report})
    return report


async def _collect_payment_audit_timeline(reference_id: str) -> dict:
    report = await _collect_payment_audit_snapshot(reference_id)
    tx = report["transaction"]
    events: list[dict] = []
    acknowledgements = await db.payment_audit_timeline_acknowledgements.find(
        {"reference_id": reference_id},
        {"_id": 0},
    ).sort("created_at", 1).to_list(100)

    def add_event(ts: Any, event_type: str, title: str, detail: str, source: str, immutable: bool = True, metadata: Optional[dict] = None):
        dt = _parse_iso(ts) or datetime.now(timezone.utc)
        events.append({
            "timestamp": dt.isoformat(),
            "event_type": event_type,
            "title": title,
            "detail": detail,
            "source": source,
            "immutable": immutable,
            "metadata": metadata or {},
        })

    add_event(tx.get("created_at"), "payment_recorded", "Payment recorded", f"{tx.get('provider')} transaction recorded for {tx.get('currency')} {tx.get('total_amount')}", "payment_transactions")
    add_event(tx.get("notification_sent_at") or tx.get("created_at"), "payment_status", f"Payment status: {tx.get('status')}", f"Payment moved to {tx.get('status')} status", "payment_transactions")

    if report.get("receipt_number") and report.get("receipt_number") != "N/A":
        add_event(report["generated_at"], "receipt_identified", "Receipt reference available", f"Receipt {report.get('receipt_number')} with ticket {report.get('ticket_id')}", "payment_confirmation_audit_reports")

    for item in report.get("audit_events", []):
        add_event(item.get("created_at"), item.get("event_type"), item.get("title"), item.get("detail"), item.get("source"), True, item.get("metadata"))

    for row in report.get("ledger", {}).get("entries", []):
        add_event(row.get("created_at") or report["generated_at"], "ledger_entry", "Immutable ledger entry", f"Sequence {row.get('sequence')} hash {row.get('entry_hash', 'N/A')}", "financial_ledger_entries", True, row)

    for row in report.get("recovery_queue", []):
        add_event(row.get("created_at") or row.get("updated_at"), "notification_recovery", "Notification recovery queue", f"Recovery status {row.get('status')} — {row.get('reason', 'N/A')}", "notification_recovery_queue", True, row)

    events.sort(key=lambda item: item["timestamp"])
    timeline = {
        "timeline_id": f"pat_{uuid.uuid4().hex[:12]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_id": reference_id,
        "transaction_id": tx.get("transaction_id"),
        "events": events,
        "acknowledgements": acknowledgements,
    }
    await db.payment_audit_timeline_snapshots.insert_one({**timeline})
    return timeline


def _categorize_webhook_error(message: str) -> str:
    text = str(message or "").lower()
    if any(term in text for term in ["timeout", "timed out"]):
        return "timeout"
    if any(term in text for term in ["dns", "resolve", "name or service"]):
        return "dns"
    if any(term in text for term in ["ssl", "tls", "certificate"]):
        return "tls"
    if any(term in text for term in ["signature", "hmac", "auth"]):
        return "signature"
    if any(term in text for term in ["404", "not found", "missing"]):
        return "not_found"
    return "other"


@router.get("/overview")
async def get_payments_tax_overview(request: Request, period: str = Query("30d")):
    await _require_admin(request)
    return await _compute_overview(period)


@router.get("/transactions")
async def get_payments_tax_transactions(
    request: Request,
    period: str = Query("30d"),
    provider: str = Query("all"),
    search: str = Query(""),
    limit: int = Query(120, ge=10, le=300),
):
    await _require_admin(request)
    rows = await _load_transactions(period=period, provider=provider, search=search, limit=limit)
    return {"transactions": rows, "count": len(rows), "period": period, "provider": provider, "search": search}


@router.get("/reconciliation")
async def get_payments_tax_reconciliation(request: Request, period: str = Query("30d")):
    await _require_admin(request)
    rows = await _load_transactions(period=period, limit=240)
    tx_ids = [row.get("transaction_id") for row in rows if row.get("transaction_id")]
    ledger_rows = await db.financial_ledger_entries.find({"transaction_id": {"$in": tx_ids}}, {"_id": 0, "transaction_id": 1}).to_list(500)
    ledger_ids = {str(row.get("transaction_id")) for row in ledger_rows if row.get("transaction_id")}

    exceptions = []
    provider_matrix: dict[str, dict] = {}
    for row in rows:
        provider = row.get("provider", "Unknown")
        provider_matrix.setdefault(provider, {
            "provider": provider,
            "count": 0,
            "ledger_gaps": 0,
            "recovery_pending": 0,
            "localization_gaps": 0,
            "tax_gaps": 0,
        })
        provider_matrix[provider]["count"] += 1
        has_ledger = row.get("transaction_id") in ledger_ids
        if not has_ledger:
            provider_matrix[provider]["ledger_gaps"] += 1
        if row.get("notification_status") == "recovery_pending":
            provider_matrix[provider]["recovery_pending"] += 1
        if not row.get("resolved_language"):
            provider_matrix[provider]["localization_gaps"] += 1
        if not row.get("tax_source"):
            provider_matrix[provider]["tax_gaps"] += 1

        if (not has_ledger or row.get("notification_status") == "recovery_pending" or not row.get("jurisdiction") or not row.get("resolved_language")) and len(exceptions) < 50:
            exceptions.append({
                "transaction_id": row.get("transaction_id"),
                "provider": provider,
                "status": row.get("status"),
                "ledger_gap": not has_ledger,
                "notification_status": row.get("notification_status"),
                "jurisdiction": row.get("jurisdiction"),
                "resolved_language": row.get("resolved_language"),
                "ops_case": row.get("ops_case", {}),
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "summary": {
            "transactions_scanned": len(rows),
            "ledger_gaps": sum(1 for row in rows if row.get("transaction_id") not in ledger_ids),
            "notification_recovery_pending": sum(1 for row in rows if row.get("notification_status") == "recovery_pending"),
            "localization_gaps": sum(1 for row in rows if not row.get("resolved_language")),
            "tax_metadata_gaps": sum(1 for row in rows if not row.get("tax_source")),
            "fedapay_dead_webhooks": await db.fedapay_webhook_events.count_documents({"status": "dead"}),
        },
        "providers": list(provider_matrix.values()),
        "exceptions": exceptions,
    }


@router.get("/disputes")
async def get_payments_tax_disputes(request: Request, period: str = Query("90d")):
    await _require_admin(request)
    rows = await _load_transactions(period=period, limit=220)
    issues = [row for row in rows if row.get("status") in {"failed", "refunded", "disputed"}]

    def _diagnostic(row: dict) -> str:
        if row.get("status") == "failed":
            return f"{row.get('provider')} failure. Check webhook + gateway logs, then retry or guide user to new checkout."
        if row.get("status") == "refunded":
            return f"{row.get('provider')} refund detected. Confirm ledger reversal and customer notification."
        return f"{row.get('provider')} dispute candidate. Review payment reference, receipt, and notification history."

    items = []
    for row in issues[:80]:
        items.append({
            **row,
            "diagnostic": _diagnostic(row),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "summary": {
            "failed": sum(1 for row in rows if row.get("status") == "failed"),
            "refunded": sum(1 for row in rows if row.get("status") == "refunded"),
            "disputed": sum(1 for row in rows if row.get("status") == "disputed"),
            "high_risk": sum(1 for row in rows if row.get("risk_score", 0) >= 70),
        },
        "items": items,
    }


@router.post("/ops/actions")
async def run_payments_tax_ops_action(request: Request, body: BulkPaymentOpsActionRequest):
    user = await _require_admin(request)
    return await _run_bulk_payment_ops_action(actor_email=getattr(user, "email", "admin@realaicoach.app"), body=body)


@router.get("/ops-queue")
async def get_payments_tax_ops_queue(
    request: Request,
    period: str = Query("30d"),
    owner: str = Query("all"),
    status: str = Query("open"),
    limit: int = Query(80, ge=10, le=200),
):
    user = await _require_admin(request)
    return await _collect_ops_queue(actor_email=getattr(user, "email", "admin@realaicoach.app"), period=period, owner=owner, status=status, limit=limit)


@router.get("/forecast")
async def get_payments_tax_forecast(request: Request, period: str = Query("90d")):
    await _require_admin(request)
    overview = await _compute_overview(period)
    trend = overview.get("trend", [])
    revenue_values = [float(row.get("revenue") or 0) for row in trend if row.get("revenue") is not None]
    tax_values = [float(row.get("tax") or 0) for row in trend if row.get("tax") is not None]
    fee_values = [float(row.get("fees") or 0) for row in trend if row.get("fees") is not None]
    avg_revenue = sum(revenue_values) / max(len(revenue_values), 1)
    avg_tax = sum(tax_values) / max(len(tax_values), 1)
    avg_fees = sum(fee_values) / max(len(fee_values), 1)
    last_revenue = revenue_values[-1] if revenue_values else 0
    first_revenue = revenue_values[0] if revenue_values else 0
    slope = (last_revenue - first_revenue) / max(len(revenue_values) - 1, 1) if revenue_values else 0

    scenarios = {
        "conservative": {"projected_30d_revenue": round(max(avg_revenue * 0.9, 0) * 30, 2), "projected_30d_tax": round(max(avg_tax * 0.9, 0) * 30, 2), "projected_30d_fees": round(max(avg_fees * 0.9, 0) * 30, 2)},
        "base": {"projected_30d_revenue": round(max(avg_revenue + slope, 0) * 30, 2), "projected_30d_tax": round(max(avg_tax, 0) * 30, 2), "projected_30d_fees": round(max(avg_fees, 0) * 30, 2)},
        "aggressive": {"projected_30d_revenue": round(max(avg_revenue * 1.1 + slope, 0) * 30, 2), "projected_30d_tax": round(max(avg_tax * 1.05, 0) * 30, 2), "projected_30d_fees": round(max(avg_fees * 1.05, 0) * 30, 2)},
    }
    deterministic_commentary = (
        f"Average daily revenue is {avg_revenue:.2f}. Trend slope is {slope:.2f} per day with projected 30-day base revenue {scenarios['base']['projected_30d_revenue']:.2f}."
    )
    ai_forecast = await _generate_ai_forecast({
        "period": period,
        "avg_daily_revenue": round(avg_revenue, 2),
        "avg_daily_tax": round(avg_tax, 2),
        "avg_daily_fees": round(avg_fees, 2),
        "slope": round(slope, 2),
        "scenarios": scenarios,
        "deterministic_commentary": deterministic_commentary,
    })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "scenarios": scenarios,
        "deterministic_commentary": deterministic_commentary,
        "ai_forecast": ai_forecast,
    }


@router.get("/transaction/{reference_id}/explain")
async def explain_transaction(reference_id: str, request: Request):
    await _require_admin(request)
    rows = await _load_transactions(period="365d", search=reference_id, limit=20)
    target = next((row for row in rows if reference_id in {row.get("transaction_id"), row.get("payment_id"), row.get("session_id")}), None)
    if not target:
        raise HTTPException(status_code=404, detail="Transaction not found")

    jurisdiction = target.get("jurisdiction", {}) or {}
    explanation = {
        "reference_id": reference_id,
        "provider": target.get("provider"),
        "customer_charge_total": target.get("total_amount"),
        "provider_processing_fee": target.get("processing_fee"),
        "net_settlement_after_fee": target.get("amount_net"),
        "summary": (
            f"{target.get('provider')} charged the customer {target.get('total_amount', 0):.2f} {target.get('currency')} including tax {target.get('tax_amount', 0):.2f} "
            f"and processing fee {target.get('processing_fee', 0):.2f}. Net settlement after fee is {target.get('amount_net', 0):.2f}."
        ),
        "tax_basis": f"{target.get('tax_source')} @ {jurisdiction.get('country', 'N/A')}-{jurisdiction.get('state', '')}",
        "localization": f"Language {str(target.get('resolved_language') or 'en').upper()} via payment localization pipeline.",
        "notification_status": target.get("notification_status"),
        "risk_score": target.get("risk_score"),
        "jurisdiction": jurisdiction,
    }
    return explanation


@router.get("/audit-report/{reference_id}")
async def get_payment_confirmation_audit_report(reference_id: str, request: Request):
    await _require_admin(request)
    return await _collect_payment_audit_snapshot(reference_id)


@router.get("/audit-report/{reference_id}/csv")
async def export_payment_confirmation_audit_report_csv(reference_id: str, request: Request):
    await _require_admin(request)
    report = await _collect_payment_audit_snapshot(reference_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Report ID", report.get("report_id")])
    writer.writerow(["Generated At", report.get("generated_at")])
    writer.writerow(["Reference ID", report.get("reference_id")])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Receipt Number", report.get("receipt_number")])
    writer.writerow(["Ticket ID", report.get("ticket_id")])
    writer.writerow(["Provider", report.get("transaction", {}).get("provider")])
    writer.writerow(["Customer Charge Total", report.get("customer_charge_total")])
    writer.writerow(["Provider Processing Fee", report.get("provider_processing_fee")])
    writer.writerow(["Net Settlement After Fee", report.get("net_settlement_after_fee")])
    writer.writerow(["Notification Status", report.get("notifications", {}).get("status")])
    writer.writerow(["User Notification IDs", " | ".join(report.get("notifications", {}).get("user_notification_ids", []))])
    writer.writerow(["Admin Notification IDs", " | ".join(report.get("notifications", {}).get("admin_notification_ids", []))])
    writer.writerow(["User Receipt Sent", report.get("receipt_delivery", {}).get("user_receipt_sent")])
    writer.writerow(["Admin Receipt Sent", report.get("receipt_delivery", {}).get("admin_receipt_sent")])
    writer.writerow(["Confirmation Email Sent", report.get("receipt_delivery", {}).get("confirmation_email_sent")])
    writer.writerow(["Ledger Count", report.get("ledger", {}).get("count")])
    content = output.getvalue()
    output.close()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payment_confirmation_audit_{reference_id}.csv"'},
    )


@router.get("/audit-report/{reference_id}/pdf")
async def export_payment_confirmation_audit_report_pdf(reference_id: str, request: Request):
    await _require_admin(request)
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    report = await _collect_payment_audit_snapshot(reference_id)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Payment Confirmation Audit Report", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, f"Report ID: {report.get('report_id')}", ln=True)
    pdf.cell(0, 6, f"Reference ID: {reference_id}", ln=True)
    pdf.cell(0, 6, f"Generated: {report.get('generated_at')}", ln=True)
    pdf.ln(4)
    tx = report.get("transaction", {})
    def _wrap_value(value: Any, width: int = 56) -> str:
        raw = str(value or "N/A")
        if len(raw) <= width:
            return raw
        return "\n".join(raw[i:i + width] for i in range(0, len(raw), width))

    lines = [
        f"Provider: {tx.get('provider')}",
        f"Customer Charge Total: {tx.get('currency')} {report.get('customer_charge_total')}",
        f"Provider Processing Fee: {tx.get('currency')} {report.get('provider_processing_fee')}",
        f"Net Settlement After Fee: {tx.get('currency')} {report.get('net_settlement_after_fee')}",
        f"Receipt Number: {report.get('receipt_number')}",
        f"Ticket ID: {report.get('ticket_id')}",
        f"Notification Status: {report.get('notifications', {}).get('status')}",
        f"User Notifications: {_wrap_value(' | '.join(report.get('notifications', {}).get('user_notification_ids', [])) or 'N/A')}",
        f"Admin Notifications: {_wrap_value(' | '.join(report.get('notifications', {}).get('admin_notification_ids', [])) or 'N/A')}",
        f"Ledger Entries: {report.get('ledger', {}).get('count')}",
    ]
    for line in lines:
        pdf.set_x(10)
        pdf.multi_cell(190, 6, line)
    raw_pdf = pdf.output(dest="S")
    data = bytes(raw_pdf) if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin1", errors="ignore")
    data = compose_pdf_v15_helper_layout(
        data,
        title="Payment Confirmation Audit",
        subtitle="Operations trace for transaction confirmation",
        right_primary=f"Reference: {reference_id}",
        right_secondary=f"Status: {str(report.get('status') or 'unknown').upper()}",
        badge_text="PAYMENT AUDIT GOVERNANCE",
        badge_status="PASS" if str(report.get("status") or "").lower() in {"success", "completed", "paid"} else "WARNING",
        footer_text="RealAICoach Payments & Tax Ops • Enterprise profile",
        summary_title="Audit Snapshot",
        summary_rows=[
            ("Provider", tx.get("provider") or "N/A"),
            ("Currency", tx.get("currency") or "N/A"),
            ("Ledger Entries", str(report.get("ledger", {}).get("count") or 0)),
        ],
        callout_title="Notification State",
        callout_subtitle="User and admin delivery",
        callout_detail=f"Notification status: {report.get('notifications', {}).get('status') or 'unknown'}.",
        callout_status="INFO",
    )
    data = _enforce_pdf_v15_enterprise(data, f"payment_confirmation_audit_{reference_id}")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("payment-confirmation-audit", reference_id)}"'},
    )


@router.get("/audit-timeline/{reference_id}")
async def get_payment_audit_timeline(reference_id: str, request: Request):
    await _require_admin(request)
    return await _collect_payment_audit_timeline(reference_id)


@router.get("/fallback-analytics/drilldown")
async def get_fallback_analytics_drilldown(request: Request, period: str = Query("30d"), limit: int = Query(60, ge=5, le=200)):
    await _require_admin(request)
    return await _collect_fallback_drilldown(period, limit)


@router.post("/audit-timeline/{reference_id}/acknowledge")
async def acknowledge_payment_audit_timeline(reference_id: str, request: Request, body: PaymentAuditAcknowledgeRequest):
    user = await _require_admin(request)
    ack = {
        "ack_id": f"ack_{uuid.uuid4().hex[:12]}",
        "reference_id": reference_id,
        "actor_email": getattr(user, "email", "admin@realaicoach.app"),
        "note": body.note or "Acknowledged in Payments & Tax timeline",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.payment_audit_timeline_acknowledgements.insert_one({**ack})
    return {"success": True, "acknowledgement": ack}


@router.get("/webhook-taxonomy")
async def get_webhook_error_taxonomy(request: Request):
    await _require_admin(request)
    rows = await db.fedapay_webhook_events.find(
        {"status": {"$in": ["retry", "dead"]}},
        {"_id": 0, "event_key": 1, "last_error": 1, "status": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(100).to_list(100)

    buckets: dict[str, dict] = {}
    for row in rows:
        category = _categorize_webhook_error(row.get("last_error", ""))
        buckets.setdefault(category, {"category": category, "count": 0, "events": []})
        buckets[category]["count"] += 1
        if len(buckets[category]["events"]) < 10:
            buckets[category]["events"].append(row)

    policy = await db.payments_tax_ops_config.find_one({"key": "dead_letter_auto_trigger_policy"}, {"_id": 0}) or {
        "key": "dead_letter_auto_trigger_policy",
        "enabled": False,
        "dead_threshold": 5,
        "replay_limit": 30,
    }
    dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dead_total": dead_total,
        "categories": list(buckets.values()),
        "auto_trigger_policy": policy,
    }


@router.put("/webhook-auto-trigger-policy")
async def update_dead_letter_auto_trigger_policy(request: Request, body: DeadLetterAutoTriggerPolicyRequest):
    user = await _require_admin(request)
    doc = {
        "key": "dead_letter_auto_trigger_policy",
        "enabled": body.enabled,
        "dead_threshold": max(1, int(body.dead_threshold)),
        "replay_limit": max(1, min(int(body.replay_limit), 100)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": getattr(user, "email", "admin@realaicoach.app"),
    }
    await db.payments_tax_ops_config.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    return {"success": True, "policy": doc}


@router.post("/webhook-auto-trigger-policy/evaluate")
async def evaluate_dead_letter_auto_trigger_policy(request: Request):
    await _require_admin(request)
    policy = await db.payments_tax_ops_config.find_one({"key": "dead_letter_auto_trigger_policy"}, {"_id": 0}) or {}
    dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})
    should_trigger = bool(policy.get("enabled")) and dead_total >= int(policy.get("dead_threshold", 5))
    result = {"success": True, "triggered": False, "dead_total": dead_total, "policy": policy}
    if should_trigger:
        from routes.fedapay_client import sync_webhook_url
        from routes.payments import run_fedapay_webhook_retry_cycle, run_fedapay_webhook_dead_replay_cycle

        await sync_webhook_url()
        await run_fedapay_webhook_retry_cycle(limit=int(policy.get("replay_limit", 30)))
        await run_fedapay_webhook_dead_replay_cycle(limit=int(policy.get("replay_limit", 30)))
        result["triggered"] = True
    return result


@router.get("/scenario-runner")
async def get_payment_scenario_runner(request: Request):
    await _require_admin(request)
    latest_runs = await _latest_scenario_runs()
    scenarios = [_scenario_payload(config, latest_runs.get(scenario_id)) for scenario_id, config in SCENARIO_RUNNER_CASES.items()]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenarios,
    }


@router.post("/scenario-runner/{scenario_id}/run")
async def run_payment_scenario_runner(scenario_id: str, request: Request):
    user = await _require_admin(request)
    result = await _run_payment_scenario(actor_email=getattr(user, "email", "admin@realaicoach.app"), scenario_id=scenario_id)
    return {"success": result.get("status") == "passed", "run": result}


def _rows_to_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Created At", "Provider", "Status", "Transaction ID", "Payment ID", "User ID", "Plan", "Currency", "Subtotal", "Tax", "Processing Fee", "Total", "Country", "State", "Resolved Language", "Tax Source", "FX Rate", "Notification Status", "Risk Score",
    ])
    for row in rows:
        jurisdiction = row.get("jurisdiction", {}) or {}
        writer.writerow([
            row.get("created_at"), row.get("provider"), row.get("status"), row.get("transaction_id"), row.get("payment_id"), row.get("user_id"), row.get("plan_id"), row.get("currency"),
            row.get("subtotal"), row.get("tax_amount"), row.get("processing_fee"), row.get("total_amount"), jurisdiction.get("country", ""), jurisdiction.get("state", ""), row.get("resolved_language"), row.get("tax_source"), row.get("fx_rate"), row.get("notification_status"), row.get("risk_score"),
        ])
    value = output.getvalue()
    output.close()
    return value


@router.get("/export/csv")
async def export_payments_tax_csv(request: Request, period: str = Query("30d"), provider: str = Query("all"), search: str = Query("")):
    await _require_admin(request)
    rows = await _load_transactions(period=period, provider=provider, search=search, limit=250)
    csv_text = _rows_to_csv(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payments_tax_intelligence_{stamp}.csv"'},
    )


@router.get("/export/pdf")
async def export_payments_tax_pdf(request: Request, period: str = Query("30d"), provider: str = Query("all"), search: str = Query("")):
    await _require_admin(request)
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    overview = await _compute_overview(period)
    rows = await _load_transactions(period=period, provider=provider, search=search, limit=40)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Payments & Tax Intelligence Report", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, f"Generated: {overview['generated_at']}", ln=True)
    pdf.cell(0, 6, f"Period: {period}", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    kpi_items = [
        ("MRR", overview["kpis"]["mrr"]),
        ("ARR", overview["kpis"]["arr"]),
        ("Net Revenue", overview["kpis"]["net_revenue"]),
        ("Tax Liability", overview["kpis"]["tax_liability"]),
        ("Finance Health Score", overview["kpis"]["finance_health_score"]),
    ]
    # Display KPIs in 2 columns
    for i, (label, value) in enumerate(kpi_items):
        pdf.cell(90, 8, f"{label}: {value}", ln=(i % 2 == 1))
    if len(kpi_items) % 2 == 1:
        pdf.ln(8)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 8, "Top Transactions", ln=True)
    pdf.set_font("Arial", size=8)
    for row in rows[:20]:
        jurisdiction = row.get("jurisdiction", {}) or {}
        # Use explicit width to avoid cursor position issues
        text = f"{row.get('created_at')} | {row.get('provider')} | {row.get('status')} | {row.get('transaction_id')} | {row.get('currency')} {row.get('total_amount')} | {jurisdiction.get('country', '')}-{jurisdiction.get('state', '')} | {row.get('resolved_language', 'en').upper()} | notif={row.get('notification_status')}"
        # Truncate text if too long
        if len(text) > 150:
            text = text[:147] + "..."
        pdf.multi_cell(
            190,  # Use explicit width instead of 0
            5,
            text,
        )
    data = bytes(pdf.output(dest="S"))
    data = compose_pdf_v15_helper_layout(
        data,
        title="Payments & Tax Intelligence",
        subtitle="Enterprise finance operations export",
        right_primary=f"Period: {period}",
        right_secondary=f"Provider: {provider}",
        badge_text="PAYMENTS TAX INTELLIGENCE",
        badge_status="INFO",
        footer_text="RealAICoach Payments Intelligence • Enterprise profile",
        summary_title="KPI Snapshot",
        summary_rows=[
            ("MRR", str(overview["kpis"].get("mrr"))),
            ("ARR", str(overview["kpis"].get("arr"))),
            ("Health", str(overview["kpis"].get("finance_health_score"))),
        ],
        callout_title="Scope",
        callout_subtitle="Transaction sample",
        callout_detail=f"Top {min(len(rows), 20)} transactions are rendered for board-level review.",
        callout_status="INFO",
    )
    data = _enforce_pdf_v15_enterprise(data, f"payments_tax_intelligence_{period}_{provider}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("payments-tax-intelligence", stamp)}"'},
    )