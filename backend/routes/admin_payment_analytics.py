"""Admin Payment Analytics — Subscription (Stripe/PayPal) & Mobile Money (FedaPay) dashboards."""

import csv
import io
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query, Request, Response
import re
from .db import db, get_current_user, create_jwt_token
import uuid
import httpx
import json
import time
import hmac
import hashlib
from typing import Any, Dict, List
from pydantic import BaseModel
from utils.pagination import iter_find_paginated, list_aggregate_paginated
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/admin/payment-analytics")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PAYMENT_E2E_RETENTION_DAYS = 30
PAYMENT_E2E_DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@realaicoach.app").strip().lower()


def _parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


async def _run_subscription_integrity_check(auto_fix: bool, source: str = "manual"):
    now = datetime.now(timezone.utc)
    user_projection = {
        "_id": 0,
        "user_id": 1,
        "email": 1,
        "subscription_plan": 1,
        "subscription_status": 1,
        "subscription_end_date": 1,
        "subscription_permanent": 1,
        "payment_verified": 1,
        "pending_subscription_transition": 1,
        "is_admin": 1,
        "full_access": 1,
        "updated_at": 1,
    }

    tx_pipeline = [
        {"$match": {"payment_status": {"$in": ["completed", "paid", "succeeded"]}}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$user_id",
                "latest_created_at": {"$first": "$created_at"},
                "latest_plan_id": {"$first": "$plan_id"},
                "latest_billing_period": {"$first": "$billing_period"},
                "latest_payment_id": {"$first": "$payment_id"},
                "latest_session_id": {"$first": "$session_id"},
            }
        },
    ]
    tx_rows = await list_aggregate_paginated(db.payment_transactions, tx_pipeline)
    tx_by_user = {row.get("_id"): row for row in tx_rows if row.get("_id")}

    duplicate_pipeline = [
        {"$match": {"payment_id": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$payment_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    duplicate_payments = await db.payments.aggregate(duplicate_pipeline).to_list(2000)

    stats = {
        "total_users": 0,
        "active_paid_users": 0,
        "entitlement_drift_count": 0,
        "missing_end_date_count": 0,
        "expired_but_active_count": 0,
        "duplicate_payment_count": len(duplicate_payments),
        "autofix_applied": 0,
    }
    sample_anomalies = []

    def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
        row = user_doc or {}
        return compute_effective_plan(
            {
                "subscription_plan": row.get("subscription_plan", "free"),
                "subscription_status": row.get("subscription_status", "active"),
                "subscription_end_date": row.get("subscription_end_date"),
                "subscription_permanent": row.get("subscription_permanent", False),
                "payment_verified": row.get("payment_verified", False),
                "pending_subscription_transition": row.get("pending_subscription_transition"),
                "is_admin": row.get("is_admin", False),
                "full_access": row.get("full_access", False),
            }
        )

    async for user in iter_find_paginated(db.users, {}, user_projection):
        stats["total_users"] += 1
        user_id = user.get("user_id")
        plan = _effective_plan_from_user_doc(user)
        status = (user.get("subscription_status") or "active").lower()
        end_dt = _parse_iso_datetime(user.get("subscription_end_date"))
        latest_tx = tx_by_user.get(user_id)

        if plan != "free" and status == "active":
            stats["active_paid_users"] += 1

        # Entitlement drift: completed payment exists but user is still free
        if plan == "free" and latest_tx and (latest_tx.get("latest_plan_id") or "") != "free":
            stats["entitlement_drift_count"] += 1
            if len(sample_anomalies) < 20:
                sample_anomalies.append({
                    "type": "entitlement_drift",
                    "user_id": user_id,
                    "email": user.get("email"),
                    "latest_plan": latest_tx.get("latest_plan_id"),
                    "latest_payment_id": latest_tx.get("latest_payment_id"),
                })
            if auto_fix:
                tx_plan = (latest_tx.get("latest_plan_id") or "free").lower()
                if tx_plan != "free":
                    billing_period = (latest_tx.get("latest_billing_period") or "monthly").lower()
                    tx_dt = _parse_iso_datetime(latest_tx.get("latest_created_at")) or now
                    new_end = tx_dt + timedelta(days=365 if billing_period == "yearly" else 30)
                    await db.users.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "subscription_plan": tx_plan,
                                "subscription_status": "active",
                                "subscription_end_date": new_end,
                                "payment_verified": True,
                                "last_payment_id": latest_tx.get("latest_payment_id") or latest_tx.get("latest_session_id"),
                                "updated_at": now,
                            }
                        },
                    )
                    stats["autofix_applied"] += 1

        # Paid active users must have an end date
        if plan != "free" and status == "active" and not end_dt:
            stats["missing_end_date_count"] += 1
            if len(sample_anomalies) < 20:
                sample_anomalies.append({
                    "type": "missing_end_date",
                    "user_id": user_id,
                    "email": user.get("email"),
                    "plan": plan,
                })
            if auto_fix:
                billing_period = (latest_tx.get("latest_billing_period") if latest_tx else "monthly") or "monthly"
                base_dt = _parse_iso_datetime(latest_tx.get("latest_created_at")) if latest_tx else now
                new_end = base_dt + timedelta(days=365 if billing_period == "yearly" else 30)
                await db.users.update_one({"user_id": user_id}, {"$set": {"subscription_end_date": new_end, "updated_at": now}})
                stats["autofix_applied"] += 1

        # Expired subscriptions marked active
        if plan != "free" and status == "active" and end_dt and end_dt < now:
            stats["expired_but_active_count"] += 1
            if len(sample_anomalies) < 20:
                sample_anomalies.append({
                    "type": "expired_but_active",
                    "user_id": user_id,
                    "email": user.get("email"),
                    "plan": plan,
                    "subscription_end_date": end_dt.isoformat(),
                })
            if auto_fix:
                await db.users.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "subscription_status": "expired",
                            "payment_verified": False,
                            "updated_at": now,
                        }
                    },
                )
                stats["autofix_applied"] += 1

    severity = "healthy"
    if stats["entitlement_drift_count"] > 0 or stats["expired_but_active_count"] > 0:
        severity = "high"
    elif stats["missing_end_date_count"] > 0 or stats["duplicate_payment_count"] > 0:
        severity = "medium"

    report = {
        "report_id": f"subint_{uuid.uuid4().hex[:10]}",
        "generated_at": now.isoformat(),
        "source": source,
        "auto_fix": auto_fix,
        "severity": severity,
        "stats": stats,
        "sample_anomalies": sample_anomalies,
        "recommendations": [
            "Review high-severity entitlement drift records first.",
            "Monitor checkout/webhook flows for delayed payment status transitions.",
            "Run this integrity check nightly and before release windows.",
        ],
    }

    await db.subscription_integrity_reports.insert_one({**report})
    return report


async def _maybe_run_nightly_integrity_check():
    """Run nightly integrity check once per UTC day (auto-fix enabled)."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    marker = await db.system_state.find_one({"key": "subscription_integrity_last_run"}, {"_id": 0, "value": 1})
    if marker and marker.get("value") == today:
        return None

    report = await _run_subscription_integrity_check(auto_fix=True, source="nightly_auto")
    await db.system_state.update_one(
        {"key": "subscription_integrity_last_run"},
        {"$set": {"value": today, "updated_at": now.isoformat()}},
        upsert=True,
    )
    return report


def _parse_period(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "7d":
        return now - timedelta(days=7)
    elif period == "30d":
        return now - timedelta(days=30)
    elif period == "90d":
        return now - timedelta(days=90)
    elif period == "1y":
        return now - timedelta(days=365)
    return now - timedelta(days=30)


async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ────────────────────────────────────────────
# DASHBOARD 1: Subscription Analytics (Stripe + PayPal)
# ────────────────────────────────────────────


@router.get("/subscriptions/overview")
async def subscription_overview(request: Request, period: str = Query("30d")):
    await _require_admin(request)
    await _maybe_run_nightly_integrity_check()
    since = _parse_period(period)
    since_iso = since.isoformat()

    # Total active subscriptions (from users collection — source of truth)
    active_subs = await db.users.count_documents({"subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    total_subs = await db.users.count_documents({"subscription_plan": {"$ne": "free"}})
    canceled_subs = await db.users.count_documents({"subscription_status": "cancelled"})

    # New subscriptions in period
    new_subs = await db.users.count_documents({
        "subscription_status": "active", "subscription_plan": {"$ne": "free"},
        "created_at": {"$gte": since_iso}
    })

    # Revenue from payments (payments collection uses status "completed")
    pipeline = [
        {"$match": {"status": {"$in": ["completed", "succeeded"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    rev_result = await db.payments.aggregate(pipeline).to_list(1)
    total_revenue = rev_result[0]["total_revenue"] if rev_result else 0
    payment_count = rev_result[0]["count"] if rev_result else 0

    # Also include payment_transactions with status completed/succeeded
    pt_pipeline = [
        {"$match": {"payment_status": {"$in": ["completed", "succeeded", "paid"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    pt_result = await db.payment_transactions.aggregate(pt_pipeline).to_list(1)
    if pt_result:
        total_revenue += pt_result[0]["total_revenue"]
        payment_count += pt_result[0]["count"]

    # Revenue by provider
    provider_pipeline = [
        {"$match": {"status": {"$in": ["completed", "succeeded"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$payment_method", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    provider_results = await db.payments.aggregate(provider_pipeline).to_list(20)
    pt_prov_pipeline = [
        {"$match": {"payment_status": {"$in": ["completed", "succeeded", "paid"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$payment_method", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    pt_prov_results = await db.payment_transactions.aggregate(pt_prov_pipeline).to_list(20)
    all_providers = provider_results + pt_prov_results

    stripe_rev = sum(p["revenue"] for p in all_providers if p["_id"] and "stripe" in str(p["_id"]).lower())
    paypal_rev = sum(p["revenue"] for p in all_providers if p["_id"] and "paypal" in str(p["_id"]).lower())
    stripe_count = sum(p["count"] for p in all_providers if p["_id"] and "stripe" in str(p["_id"]).lower())
    paypal_count = sum(p["count"] for p in all_providers if p["_id"] and "paypal" in str(p["_id"]).lower())

    # Revenue by currency
    currency_pipeline = [
        {"$match": {"status": {"$in": ["completed", "succeeded"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$currency", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    currency_results = await db.payments.aggregate(currency_pipeline).to_list(50)
    revenue_by_currency = {
        r["_id"]: {"revenue": r["revenue"], "count": r["count"]} for r in currency_results if r["_id"]
    }

    # Revenue by country
    country_pipeline = [
        {"$match": {"status": {"$in": ["completed", "succeeded"]}, "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$country", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    country_results = await db.payments.aggregate(country_pipeline).to_list(200)
    revenue_by_country = {r["_id"]: {"revenue": r["revenue"], "count": r["count"]} for r in country_results if r["_id"]}

    # Revenue trend (daily for last N days)
    days = min((datetime.now(timezone.utc) - since).days, 90)
    trend = []
    for i in range(days):
        day_start = (since + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_rev = await db.payments.aggregate(
            [
                {
                    "$match": {
                        "status": {"$in": ["completed", "succeeded"]},
                        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()},
                    }
                },
                {"$group": {"_id": None, "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            ]
        ).to_list(1)
        trend.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "revenue": day_rev[0]["revenue"] if day_rev else 0,
                "count": day_rev[0]["count"] if day_rev else 0,
            }
        )

    # MRR / ARR / ARPU
    mrr = total_revenue / max(days / 30, 1)
    arr = mrr * 12
    arpu = total_revenue / max(active_subs, 1)

    # Churn rate
    churn_rate = (canceled_subs / max(total_subs, 1)) * 100

    return {
        "active_subscribers": active_subs,
        "total_subscribers": total_subs,
        "new_subscribers": new_subs,
        "canceled_subscribers": canceled_subs,
        "total_revenue": round(total_revenue, 2),
        "payment_count": payment_count,
        "mrr": round(mrr, 2),
        "arr": round(arr, 2),
        "arpu": round(arpu, 2),
        "churn_rate": round(churn_rate, 1),
        "stripe": {"revenue": round(stripe_rev, 2), "count": stripe_count},
        "paypal": {"revenue": round(paypal_rev, 2), "count": paypal_count},
        "revenue_by_currency": revenue_by_currency,
        "revenue_by_country": revenue_by_country,
        "revenue_trend": trend,
        "period": period,
    }


@router.post("/subscriptions/integrity-check")
async def run_subscription_integrity_check(request: Request, auto_fix: bool = Query(True)):
    await _require_admin(request)
    return await _run_subscription_integrity_check(auto_fix=auto_fix, source="manual")


@router.get("/subscriptions/integrity-report/latest")
async def get_latest_subscription_integrity_report(request: Request):
    await _require_admin(request)
    doc = await db.subscription_integrity_reports.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    return doc or {
        "report_id": None,
        "generated_at": None,
        "severity": "unknown",
        "stats": {},
        "sample_anomalies": [],
    }


@router.get("/subscriptions/integrity-report/history")
async def get_subscription_integrity_report_history(request: Request, limit: int = Query(10, ge=1, le=60)):
    await _require_admin(request)
    reports = await db.subscription_integrity_reports.find({}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return {
        "reports": reports,
        "count": len(reports),
    }


def _internal_base_url(request: Request) -> str:
    origin = request.headers.get("origin", "").strip()
    if origin.startswith("http"):
        return origin.rstrip("/")
    front = (os.environ.get("FRONTEND_BASE_URL", "") or "").strip().rstrip("/")
    if front:
        return front.replace("http://", "https://")
    host = request.headers.get("host", "")
    return f"https://{host}" if host else ""


def _stripe_signature(payload: str, webhook_secret: str) -> str:
    ts = str(int(time.time()))
    signed = f"{ts}.{payload}".encode("utf-8")
    digest = hmac.new(webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


async def _get_admin_users_for_alerts() -> list:
    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(100)

    if not admins and PAYMENT_E2E_DEFAULT_ADMIN_EMAIL:
        return [{"user_id": "admin", "email": PAYMENT_E2E_DEFAULT_ADMIN_EMAIL, "name": "Admin"}]

    normalized = []
    for a in admins:
        email = (a.get("email") or "").strip().lower()
        if email:
            normalized.append({
                "user_id": a.get("user_id") or "admin",
                "email": email,
                "name": a.get("name") or "Admin",
            })
    if not normalized and PAYMENT_E2E_DEFAULT_ADMIN_EMAIL:
        normalized.append({"user_id": "admin", "email": PAYMENT_E2E_DEFAULT_ADMIN_EMAIL, "name": "Admin"})
    return normalized


async def _prune_payment_e2e_reports(retention_days: int = PAYMENT_E2E_RETENTION_DAYS):
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    await db.payment_e2e_reports.delete_many({"generated_at": {"$lt": cutoff_iso}})


async def _send_payment_e2e_admin_digest(report: dict, digest_type: str = "daily", is_immediate_alert: bool = False):
    admins = await _get_admin_users_for_alerts()
    if not admins:
        return

    summary = report.get("summary", {})
    checks = report.get("checks", [])
    failed = [c for c in checks if not c.get("passed")]

    badge = "ALERT" if is_immediate_alert else digest_type.upper()
    subject = f"[{badge}] Payment E2E {'Failure Alert' if is_immediate_alert else 'Digest'} — {summary.get('passed', 0)}/{summary.get('total', 0)} checks"
    from utils.email_service import send_catalog_template

    now_iso = datetime.now(timezone.utc).isoformat()
    for admin in admins:
        email = admin.get("email")
        if not email:
            continue
        result = await send_catalog_template(
            recipient_email=email,
            template_key="payment_e2e_report",
            report_id=report.get("report_id", ""),
            severity=report.get("severity", "unknown"),
            passed=summary.get("passed", 0),
            total=summary.get("total", 0),
            pass_rate=summary.get("pass_rate", 0),
            failed_checks=failed[:20],
            is_immediate=is_immediate_alert,
            digest_type=digest_type,
        )
        await db.email_logs.insert_one(
            {
                "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                "user_id": admin.get("user_id") or "admin",
                "email": email,
                "email_type": "payment_e2e_alert" if is_immediate_alert else "payment_e2e_digest",
                "subject": subject,
                "status": "sent" if result.get("success") else "failed",
                "created_at": now_iso,
                "metadata": {
                    "report_id": report.get("report_id"),
                    "severity": report.get("severity"),
                    "digest_type": digest_type,
                    "is_immediate_alert": is_immediate_alert,
                },
            }
        )

        await db.notifications.insert_one(
            {
                "id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": admin.get("user_id") or "admin",
                "type": "payment_e2e_alert" if is_immediate_alert else "payment_e2e_digest",
                "title": "Payment E2E Failure Alert" if is_immediate_alert else "Payment E2E Daily Digest",
                "message": f"{summary.get('passed', 0)}/{summary.get('total', 0)} checks passed · severity {(report.get('severity') or 'unknown').upper()}",
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "report_id": report.get("report_id"),
                    "severity": report.get("severity"),
                    "pass_rate": summary.get("pass_rate", 0),
                },
            }
        )


async def _handle_first_failure_alert_state(report: dict):
    marker = await db.system_state.find_one({"key": "payment_e2e_failure_active"}, {"_id": 0, "value": 1})
    active = bool(marker and marker.get("value"))
    failed = (report.get("severity") or "").lower() != "healthy"

    if failed and not active:
        await _send_payment_e2e_admin_digest(report, digest_type="immediate", is_immediate_alert=True)
        await db.system_state.update_one(
            {"key": "payment_e2e_failure_active"},
            {"$set": {"value": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    elif (not failed) and active:
        await db.system_state.update_one(
            {"key": "payment_e2e_failure_active"},
            {"$set": {"value": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )


async def _run_payment_e2e_control(
    request: Request = None,
    full_suite: bool = False,
    *,
    base_override: str | None = None,
    frontend_base_override: str | None = None,
    auth_header_override: str | None = None,
    admin_user_override: dict | None = None,
    source: str = "manual",
):
    admin_user = admin_user_override or await _require_admin(request)
    auth_header = auth_header_override or (request.headers.get("authorization", "") if request else "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    base = base_override or (_internal_base_url(request) if request else "")
    if not base:
        raise HTTPException(status_code=500, detail="Unable to resolve base URL for E2E control center")
    frontend_base = frontend_base_override or base

    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    checks = []

    async def _record(name: str, passed: bool, detail: str = ""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    now = datetime.now(timezone.utc)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # Gateway config alias
        cfg = await client.get(f"{base}/api/subscriptions/gateway-config", headers=headers)
        await _record("gateway_config_alias", cfg.status_code == 200, f"http={cfg.status_code}")

        # Notifications convenience endpoint
        notif = await client.get(f"{base}/api/notifications", headers=headers)
        await _record("notifications_endpoint", notif.status_code == 200, f"http={notif.status_code}")

        # Stripe
        stripe_session = None
        stripe_create = await client.post(
            f"{base}/api/subscriptions/create-checkout",
            headers=headers,
            json={"plan_id": "basic", "billing_period": "monthly", "payment_method": "stripe", "currency": "usd"},
        )
        if stripe_create.status_code == 200:
            stripe_session = stripe_create.json().get("session_id")
        await _record("stripe_checkout_create", stripe_create.status_code == 200 and bool(stripe_session), f"http={stripe_create.status_code}")

        if stripe_session:
            stripe_status = await client.get(f"{base}/api/subscriptions/checkout-status/{stripe_session}", headers=headers)
            await _record("stripe_checkout_status", stripe_status.status_code == 200, f"http={stripe_status.status_code}")

            if full_suite and STRIPE_WEBHOOK_SECRET:
                payload_ok = {
                    "id": f"evt_{uuid.uuid4().hex[:14]}",
                    "object": "event",
                    "type": "checkout.session.completed",
                    "data": {"object": {"id": stripe_session, "object": "checkout.session", "payment_status": "paid"}},
                }
                ps = json.dumps(payload_ok, separators=(",", ":"))
                stripe_ok = await client.post(
                    f"{base}/api/webhook/stripe",
                    content=ps,
                    headers={"Content-Type": "application/json", "stripe-signature": _stripe_signature(ps, STRIPE_WEBHOOK_SECRET)},
                )
                await _record("stripe_webhook_success", stripe_ok.status_code == 200, f"http={stripe_ok.status_code}")

                payload_fail = {
                    "id": f"evt_{uuid.uuid4().hex[:14]}",
                    "object": "event",
                    "type": "checkout.session.expired",
                    "data": {"object": {"id": stripe_session, "object": "checkout.session", "payment_status": "expired"}},
                }
                pf = json.dumps(payload_fail, separators=(",", ":"))
                stripe_fail = await client.post(
                    f"{base}/api/webhook/stripe",
                    content=pf,
                    headers={"Content-Type": "application/json", "stripe-signature": _stripe_signature(pf, STRIPE_WEBHOOK_SECRET)},
                )
                await _record("stripe_webhook_failure", stripe_fail.status_code == 200, f"http={stripe_fail.status_code}")

        # PayPal
        paypal_order = None
        pp_create = await client.post(
            f"{base}/api/subscriptions/create-checkout",
            headers=headers,
            json={"plan_id": "basic", "billing_period": "monthly", "payment_method": "paypal"},
        )
        if pp_create.status_code == 200:
            paypal_order = pp_create.json().get("order_id")
        await _record("paypal_checkout_create", pp_create.status_code == 200 and bool(paypal_order), f"http={pp_create.status_code}")

        pp_js = await client.post(f"{base}/api/paypal/create-order", headers=headers, json={"plan_id": "basic", "billing_period": "monthly"})
        await _record("paypal_js_create_order", pp_js.status_code == 200, f"http={pp_js.status_code}")

        if full_suite and paypal_order:
            pp_ok = await client.post(
                f"{base}/api/payments/paypal/webhook",
                json={
                    "id": f"WH-{uuid.uuid4().hex[:10]}",
                    "event_type": "PAYMENT.CAPTURE.COMPLETED",
                    "resource": {
                        "id": f"CAP-{uuid.uuid4().hex[:8]}",
                        "status": "COMPLETED",
                        "amount": {"value": "5.99", "currency_code": "USD"},
                        "supplementary_data": {"related_ids": {"order_id": paypal_order}},
                    },
                },
            )
            await _record("paypal_webhook_success", pp_ok.status_code == 200, f"http={pp_ok.status_code}")

            pp_fail = await client.post(
                f"{base}/api/payments/paypal/webhook",
                json={
                    "id": f"WH-{uuid.uuid4().hex[:10]}",
                    "event_type": "PAYMENT.CAPTURE.DENIED",
                    "resource": {
                        "id": f"CAP-{uuid.uuid4().hex[:8]}",
                        "status": "DENIED",
                        "supplementary_data": {"related_ids": {"order_id": paypal_order}},
                    },
                },
            )
            await _record("paypal_webhook_failure", pp_fail.status_code == 200, f"http={pp_fail.status_code}")

        # FedaPay
        fedapay_payment_id = None
        fedapay_pay = await client.post(
            f"{base}/api/subscriptions/mobile-money/pay",
            headers=headers,
            json={
                "plan_id": "basic",
                "billing_period": "monthly",
                "gateway": "fedapay",
                "phone_number": "0166123456",
                "currency": "XOF",
            },
        )
        if fedapay_pay.status_code == 200:
            fedapay_payment_id = fedapay_pay.json().get("payment_id")
        await _record("fedapay_pay_initiate", fedapay_pay.status_code == 200 and bool(fedapay_payment_id), f"http={fedapay_pay.status_code}")

        if full_suite and fedapay_payment_id:
            tx = await db.payment_transactions.find_one(
                {"payment_id": fedapay_payment_id},
                {"_id": 0, "fedapay_tx_id": 1, "fedapay_reference": 1},
            )
            txid = tx.get("fedapay_tx_id") if tx else None
            ref = tx.get("fedapay_reference", "") if tx else ""
            if txid:
                fd_ok = await client.post(
                    f"{base}/api/payments/fedapay/webhook",
                    json={"name": "transaction.approved", "entity": {"id": txid, "status": "approved", "reference": ref}},
                )
                await _record("fedapay_webhook_success", fd_ok.status_code == 200, f"http={fd_ok.status_code}")

                fd_fail = await client.post(
                    f"{base}/api/payments/fedapay/webhook",
                    json={"name": "transaction.declined", "entity": {"id": txid, "status": "declined", "reference": ref}},
                )
                await _record("fedapay_webhook_failure", fd_fail.status_code == 200, f"http={fd_fail.status_code}")

        # IAP backend/webhook mode
        iap_products = await client.get(f"{base}/api/iap/products")
        await _record("iap_products", iap_products.status_code == 200, f"http={iap_products.status_code}")

        iap_status = await client.get(f"{base}/api/iap/status", headers=headers)
        await _record("iap_status", iap_status.status_code == 200, f"http={iap_status.status_code}")

        iap_aw = await client.post(f"{base}/api/iap/apple/webhook", json={"notificationType": "TEST"})
        iap_gw = await client.post(f"{base}/api/iap/google/webhook", json={"message": {"data": ""}})
        await _record("iap_webhooks", iap_aw.status_code == 200 and iap_gw.status_code == 200, f"apple={iap_aw.status_code},google={iap_gw.status_code}")

        # Result pages
        if full_suite:
            for gateway, status in [("stripe", "success"), ("paypal", "success"), ("fedapay", "failed")]:
                page = await client.get(f"{frontend_base}/subscription/payment-result?gateway={gateway}&status={status}")
                await _record(f"result_page_{gateway}_{status}", page.status_code == 200, f"http={page.status_code}")

    # Email delivery summary (last 2 hours)
    since_iso = (now - timedelta(hours=2)).isoformat()
    admin_email = admin_user.get("email") if isinstance(admin_user, dict) else getattr(admin_user, "email", "")
    email_logs = await db.email_logs.find(
        {
            "email": admin_email,
            "created_at": {"$gte": since_iso},
            "email_type": {"$in": ["subscription_confirmation", "payment_failed", "support_ticket", "security_alert"]},
        },
        {"_id": 0, "log_id": 1, "email_type": 1, "subject": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).limit(20).to_list(20)

    passed = sum(1 for c in checks if c.get("passed"))
    total = len(checks)
    severity = "healthy" if passed == total else ("degraded" if passed >= int(total * 0.7) else "high")

    report = {
        "report_id": f"paye2e_{uuid.uuid4().hex[:10]}",
        "generated_at": now.isoformat(),
        "mode": "non_charge",
        "source": source,
        "full_suite": bool(full_suite),
        "severity": severity,
        "summary": {
            "passed": passed,
            "total": total,
            "pass_rate": round((passed / total) * 100, 1) if total else 0,
        },
        "checks": checks,
        "email_delivery_logs": email_logs,
        "notes": [
            "Control center runs non-charge checks only.",
            "For Apple/Google IAP full purchase closure, native store test environments are required.",
        ],
    }

    await db.payment_e2e_reports.insert_one({**report})
    await _prune_payment_e2e_reports()
    return report


@router.post("/subscriptions/payment-e2e/run")
async def run_payment_e2e_control_center(request: Request, full_suite: bool = Query(False)):
    return await _run_payment_e2e_control(request, full_suite=full_suite, source="manual")


async def _resolve_admin_session_context() -> tuple[dict, str] | tuple[None, None]:
    admin = await db.users.find_one({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "token_version": 1})
    if not admin:
        return None, None
    session = await db.user_sessions.find_one(
        {"user_id": admin.get("user_id")},
        {"_id": 0, "session_token": 1, "expires_at": 1, "issued_at": 1},
        sort=[("issued_at", -1)],
    )
    session_token = (session or {}).get("session_token", "")
    is_jwt_like = isinstance(session_token, str) and session_token.count(".") == 2 and len(session_token) > 80

    if not session or not session_token or not is_jwt_like:
        service_token = create_jwt_token(
            admin.get("user_id"),
            admin.get("email") or PAYMENT_E2E_DEFAULT_ADMIN_EMAIL,
            token_version=int(admin.get("token_version") or 0),
            expires_minutes=8 * 60,
        )
        now = datetime.now(timezone.utc)
        await db.user_sessions.insert_one(
            {
                "user_id": admin.get("user_id"),
                "session_token": service_token,
                "issued_at": now,
                "expires_at": now + timedelta(hours=8),
                "ip_address": "scheduler",
                "created_at": now,
            }
        )
        return admin, f"Bearer {service_token}"
    expires_at = _parse_iso_datetime(session.get("expires_at"))
    if expires_at and expires_at < datetime.now(timezone.utc):
        service_token = create_jwt_token(
            admin.get("user_id"),
            admin.get("email") or PAYMENT_E2E_DEFAULT_ADMIN_EMAIL,
            token_version=int(admin.get("token_version") or 0),
            expires_minutes=8 * 60,
        )
        now = datetime.now(timezone.utc)
        await db.user_sessions.insert_one(
            {
                "user_id": admin.get("user_id"),
                "session_token": service_token,
                "issued_at": now,
                "expires_at": now + timedelta(hours=8),
                "ip_address": "scheduler",
                "created_at": now,
            }
        )
        return admin, f"Bearer {service_token}"
    return admin, f"Bearer {session_token}"


async def run_payment_e2e_scheduled(full_suite: bool = False, trigger: str = "scheduled_daily_quick"):
    admin, auth_header = await _resolve_admin_session_context()
    if not admin or not auth_header:
        report = {
            "report_id": f"paye2e_{uuid.uuid4().hex[:10]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "non_charge",
            "source": trigger,
            "full_suite": bool(full_suite),
            "severity": "high",
            "summary": {"passed": 0, "total": 1, "pass_rate": 0},
            "checks": [{"name": "admin_session_context", "passed": False, "detail": "No valid admin session token available for scheduled run"}],
            "email_delivery_logs": [],
            "notes": ["Scheduled run skipped due to missing admin session context."],
        }
        await db.payment_e2e_reports.insert_one({**report})
        await _prune_payment_e2e_reports()
        await _handle_first_failure_alert_state(report)
        await _send_payment_e2e_admin_digest(report, digest_type="daily", is_immediate_alert=False)
        return report

    api_base = (os.environ.get("SCHEDULER_PAYMENT_E2E_API_BASE_URL", "") or "http://127.0.0.1:8001").strip().rstrip("/")
    frontend_base = (os.environ.get("SCHEDULER_PAYMENT_E2E_FRONTEND_BASE_URL", "") or "http://127.0.0.1:3000").strip().rstrip("/")
    base = api_base
    if not base:
        return {
            "report_id": None,
            "severity": "high",
            "summary": {"passed": 0, "total": 1, "pass_rate": 0},
            "checks": [{"name": "base_url", "passed": False, "detail": "FRONTEND_BASE_URL is not configured"}],
        }

    try:
        report = await _run_payment_e2e_control(
            full_suite=full_suite,
            base_override=base,
            frontend_base_override=frontend_base,
            auth_header_override=auth_header,
            admin_user_override=admin,
            source=trigger,
        )
    except Exception as e:
        report = {
            "report_id": f"paye2e_{uuid.uuid4().hex[:10]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "non_charge",
            "source": trigger,
            "full_suite": bool(full_suite),
            "severity": "high",
            "summary": {"passed": 0, "total": 1, "pass_rate": 0},
            "checks": [{"name": "scheduler_runtime", "passed": False, "detail": f"Runtime error: {e}"}],
            "email_delivery_logs": [],
            "notes": ["Scheduled run failed before checks completed."],
        }
        await db.payment_e2e_reports.insert_one({**report})
        await _prune_payment_e2e_reports()

    await _handle_first_failure_alert_state(report)
    await _send_payment_e2e_admin_digest(
        report,
        digest_type="weekly_full" if full_suite else "daily",
        is_immediate_alert=False,
    )
    return report


@router.get("/subscriptions/payment-e2e/latest")
async def get_payment_e2e_latest(request: Request):
    await _require_admin(request)
    doc = await db.payment_e2e_reports.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    return doc or {
        "report_id": None,
        "generated_at": None,
        "severity": "unknown",
        "summary": {"passed": 0, "total": 0, "pass_rate": 0},
        "checks": [],
        "email_delivery_logs": [],
    }


@router.get("/subscriptions/payment-e2e/export")
async def export_payment_e2e_latest(request: Request, format: str = Query("json")):
    await _require_admin(request)
    doc = await db.payment_e2e_reports.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="No payment E2E report available")

    fmt = (format or "json").lower()
    if fmt == "json":
        return doc

    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["check", "passed", "detail"])
        for c in doc.get("checks", []):
            writer.writerow([c.get("name"), "PASS" if c.get("passed") else "FAIL", c.get("detail", "")])
        writer.writerow([])
        writer.writerow(["email_log_id", "email_type", "subject", "status", "created_at"])
        for e in doc.get("email_delivery_logs", []):
            writer.writerow([e.get("log_id"), e.get("email_type"), e.get("subject"), e.get("status"), e.get("created_at")])
        csv_content = out.getvalue()
        return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=payment_e2e_latest.csv"})

    raise HTTPException(status_code=400, detail="format must be json or csv")


@router.get("/subscriptions/subscribers")
async def list_subscribers(request: Request, page: int = 1, search: str = "", status: str = ""):
    await _require_admin(request)
    query = {"subscription_plan": {"$ne": "free"}}
    if status:
        query["subscription_status"] = status
    if search:
        query["$or"] = [
            {"user_id": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"email": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"subscription_plan": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]
    per_page = 20
    skip = (page - 1) * per_page
    total = await db.users.count_documents(query)
    subs = (
        await db.users.find(query, {"_id": 0, "password_hash": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
        .to_list(per_page)
    )
    return {
        "subscribers": subs,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/subscriptions/export")
async def export_subscriptions(request: Request, period: str = "30d", format: str = "csv"):
    await _require_admin(request)
    since = _parse_period(period)
    subs = []
    async for row in iter_find_paginated(
        db.subscriptions,
        {"created_at": {"$gte": since.isoformat()}},
        {"_id": 0},
        sort=[("created_at", -1)],
        max_docs=10000,
    ):
        subs.append(row)

    if format == "csv":
        output = io.StringIO()
        if subs:
            writer = csv.DictWriter(output, fieldnames=subs[0].keys())
            writer.writeheader()
            writer.writerows(subs)
        return {"csv_data": output.getvalue(), "count": len(subs)}
    return {"data": subs, "count": len(subs)}


# ────────────────────────────────────────────
# DASHBOARD 2: Mobile Money Analytics (FedaPay)
# ────────────────────────────────────────────


@router.get("/mobile-money/overview")
async def mobile_money_overview(request: Request, period: str = Query("30d")):
    await _require_admin(request)
    since = _parse_period(period)
    since_iso = since.isoformat()

    # Total mobile money payments
    total_payments = await db.mobile_money_payments.count_documents({})
    success_payments = await db.mobile_money_payments.count_documents({"status": "success"})
    failed_payments = await db.mobile_money_payments.count_documents({"status": {"$in": ["failed", "error"]}})
    pending_payments = await db.mobile_money_payments.count_documents({"status": "pending"})

    # Active in-app purchase subscriptions
    active_subs = await db.mobile_money_subscriptions.count_documents({"status": "active"})
    new_subs = await db.mobile_money_subscriptions.count_documents({"created_at": {"$gte": since_iso}})

    # Revenue pipeline
    rev_pipeline = [
        {"$match": {"status": "success", "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    rev_result = await db.mobile_money_payments.aggregate(rev_pipeline).to_list(1)
    total_revenue = rev_result[0]["total"] if rev_result else 0
    payment_count = rev_result[0]["count"] if rev_result else 0

    # Revenue by gateway
    gw_pipeline = [
        {"$match": {"status": "success", "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$provider", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    gw_results = await db.mobile_money_payments.aggregate(gw_pipeline).to_list(20)
    # All mobile money goes through FedaPay gateway — aggregate all providers
    fedapay_rev = sum(g["revenue"] for g in gw_results)
    fedapay_count = sum(g["count"] for g in gw_results)

    # Revenue by country
    country_pipeline = [
        {"$match": {"status": "success", "created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$country", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    country_results = await db.mobile_money_payments.aggregate(country_pipeline).to_list(200)
    revenue_by_country = {r["_id"]: {"revenue": r["revenue"], "count": r["count"]} for r in country_results if r["_id"]}

    # Transaction success rate
    total_period = await db.mobile_money_payments.count_documents({"created_at": {"$gte": since_iso}})
    success_period = await db.mobile_money_payments.count_documents(
        {"status": "success", "created_at": {"$gte": since_iso}}
    )
    success_rate = (success_period / max(total_period, 1)) * 100

    # Daily revenue trend
    days = min((datetime.now(timezone.utc) - since).days, 90)
    trend = []
    for i in range(days):
        day_start = (since + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_rev = await db.mobile_money_payments.aggregate(
            [
                {
                    "$match": {
                        "status": "success",
                        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()},
                    }
                },
                {"$group": {"_id": None, "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            ]
        ).to_list(1)
        trend.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "revenue": day_rev[0]["revenue"] if day_rev else 0,
                "count": day_rev[0]["count"] if day_rev else 0,
            }
        )

    # Growth rate
    prev_since = since - (datetime.now(timezone.utc) - since)
    prev_rev = await db.mobile_money_payments.aggregate(
        [
            {"$match": {"status": "success", "created_at": {"$gte": prev_since.isoformat(), "$lt": since_iso}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
    ).to_list(1)
    prev_total = prev_rev[0]["total"] if prev_rev else 0
    growth_rate = ((total_revenue - prev_total) / max(prev_total, 1)) * 100 if prev_total > 0 else 0

    return {
        "total_payments": total_payments,
        "success_payments": success_payments,
        "failed_payments": failed_payments,
        "pending_payments": pending_payments,
        "active_subscribers": active_subs,
        "new_subscribers": new_subs,
        "total_revenue": round(total_revenue, 2),
        "payment_count": payment_count,
        "success_rate": round(success_rate, 1),
        "growth_rate": round(growth_rate, 1),
        "fedapay": {"revenue": round(fedapay_rev, 2), "count": fedapay_count},
        "revenue_by_country": revenue_by_country,
        "revenue_trend": trend,
        "period": period,
    }


@router.get("/mobile-money/transactions")
async def list_mobile_money_transactions(request: Request, page: int = 1, status: str = "", provider: str = ""):
    await _require_admin(request)
    query = {}
    if status:
        query["status"] = status
    if provider:
        query["provider"] = provider
    per_page = 20
    skip = (page - 1) * per_page
    total = await db.mobile_money_payments.count_documents(query)
    txns = (
        await db.mobile_money_payments.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
        .to_list(per_page)
    )
    return {
        "transactions": txns,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/mobile-money/export")
async def export_mobile_money(request: Request, period: str = "30d"):
    await _require_admin(request)
    since = _parse_period(period)
    txns = []
    async for row in iter_find_paginated(
        db.mobile_money_payments,
        {"created_at": {"$gte": since.isoformat()}},
        {"_id": 0},
        sort=[("created_at", -1)],
        max_docs=10000,
    ):
        txns.append(row)

    output = io.StringIO()
    if txns:
        writer = csv.DictWriter(output, fieldnames=txns[0].keys())
        writer.writeheader()
        writer.writerows(txns)
    return {"csv_data": output.getvalue(), "count": len(txns)}


@router.get("/recent-transactions")
async def recent_transactions(request: Request, limit: int = 20):
    """Recent payment transactions across all providers."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)

    # Get recent subscription payments
    sub_txns = await db.payments.find(
        {"created_at": {"$gte": since.isoformat()}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)

    # Get recent mobile money transactions
    mm_txns = await db.mobile_money_transactions.find(
        {"created_at": {"$gte": since.isoformat()}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)

    # Combine and sort
    all_txns = []
    for t in sub_txns:
        t["source"] = "subscription"
        all_txns.append(t)
    for t in mm_txns:
        t["source"] = "mobile_money"
        all_txns.append(t)

    all_txns.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "transactions": all_txns[:limit],
        "total": len(all_txns),
        "period": "30d"
    }


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if isinstance(value, str):
        return value
    return ""


def _incident_severity(status: str) -> str:
    s = str(status or "").strip().lower()
    if s in {"exhausted", "dead", "critical"}:
        return "critical"
    if s in {"failed", "error", "declined", "replay_failed", "retry_failed"}:
        return "high"
    if s in {"retry", "processing", "pending"}:
        return "medium"
    return "low"


def _provider_name(raw: str, fallback: str = "unknown") -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return fallback
    aliases = {
        "mm": "fedapay",
        "mobile_money": "fedapay",
        "apple_iap": "apple",
        "google_iap": "google",
    }
    return aliases.get(value, value)


@router.get("/provider-incidents/drilldown")
async def provider_incidents_drilldown(
    request: Request,
    hours: int = Query(72, ge=1, le=24 * 30),
    provider: str = Query("all"),
    limit: int = Query(200, ge=20, le=500),
):
    await _require_admin(request)

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).isoformat()
    provider_filter = _provider_name(provider, fallback="all")
    incidents: List[Dict[str, Any]] = []

    payment_statuses = ["failed", "error", "declined", "canceled", "cancelled"]
    payment_rows = (
        await db.payments.find(
            {
                "$or": [
                    {"payment_status": {"$in": payment_statuses}},
                    {"status": {"$in": payment_statuses}},
                ],
                "created_at": {"$gte": since},
            },
            {
                "_id": 0,
                "payment_id": 1,
                "session_id": 1,
                "user_id": 1,
                "provider": 1,
                "gateway": 1,
                "payment_provider": 1,
                "payment_status": 1,
                "status": 1,
                "amount": 1,
                "currency": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    for row in payment_rows:
        status = str(row.get("payment_status") or row.get("status") or "failed").lower()
        incident_provider = _provider_name(
            str(row.get("provider") or row.get("gateway") or row.get("payment_provider") or "stripe"),
            fallback="stripe",
        )
        incidents.append(
            {
                "source": "subscription_checkout",
                "provider": incident_provider,
                "status": status,
                "severity": _incident_severity(status),
                "incident_id": str(row.get("payment_id") or row.get("session_id") or f"pay_{len(incidents)+1}"),
                "user_id": str(row.get("user_id") or ""),
                "amount": row.get("amount"),
                "currency": row.get("currency") or "USD",
                "created_at": _to_iso(row.get("created_at")),
                "meta": {
                    "payment_id": row.get("payment_id"),
                    "session_id": row.get("session_id"),
                },
            }
        )

    mm_statuses = ["failed", "error", "retry", "dead"]
    mm_rows = (
        await db.mobile_money_payments.find(
            {
                "status": {"$in": mm_statuses},
                "created_at": {"$gte": since},
            },
            {
                "_id": 0,
                "payment_id": 1,
                "transaction_id": 1,
                "user_id": 1,
                "provider": 1,
                "status": 1,
                "amount": 1,
                "currency": 1,
                "country": 1,
                "created_at": 1,
                "updated_at": 1,
                "last_error": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    for row in mm_rows:
        status = str(row.get("status") or "failed").lower()
        incidents.append(
            {
                "source": "mobile_money_checkout",
                "provider": _provider_name(str(row.get("provider") or "fedapay"), fallback="fedapay"),
                "status": status,
                "severity": _incident_severity(status),
                "incident_id": str(row.get("payment_id") or row.get("transaction_id") or f"mm_{len(incidents)+1}"),
                "user_id": str(row.get("user_id") or ""),
                "amount": row.get("amount"),
                "currency": row.get("currency") or "XOF",
                "created_at": _to_iso(row.get("created_at") or row.get("updated_at")),
                "meta": {
                    "country": row.get("country"),
                    "last_error": row.get("last_error"),
                },
            }
        )

    webhook_statuses = ["failed", "error", "replay_failed", "retry_failed", "exhausted"]
    webhook_rows = (
        await db.webhook_events.find(
            {
                "status": {"$in": webhook_statuses},
                "created_at": {"$gte": since},
            },
            {
                "_id": 0,
                "event_id": 1,
                "integration_id": 1,
                "event_type": 1,
                "status": 1,
                "replay_count": 1,
                "resolution_status": 1,
                "created_at": 1,
                "last_replayed_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    for row in webhook_rows:
        status = str(row.get("status") or "failed").lower()
        incidents.append(
            {
                "source": "provider_webhook",
                "provider": _provider_name(str(row.get("integration_id") or "unknown")),
                "status": status,
                "severity": _incident_severity(status),
                "incident_id": str(row.get("event_id") or f"wh_{len(incidents)+1}"),
                "user_id": "",
                "amount": None,
                "currency": None,
                "created_at": _to_iso(row.get("created_at") or row.get("last_replayed_at")),
                "meta": {
                    "event_type": row.get("event_type"),
                    "replay_count": int(row.get("replay_count") or 0),
                    "resolution_status": row.get("resolution_status") or "open",
                },
            }
        )

    if provider_filter != "all":
        incidents = [item for item in incidents if item.get("provider") == provider_filter]

    incidents.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    incidents = incidents[:limit]

    provider_summary: Dict[str, Dict[str, Any]] = {}
    for item in incidents:
        provider_key = str(item.get("provider") or "unknown")
        bucket = provider_summary.setdefault(
            provider_key,
            {
                "provider": provider_key,
                "incidents": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "last_incident_at": "",
                "sources": {},
            },
        )
        bucket["incidents"] += 1
        sev = str(item.get("severity") or "low")
        if sev in {"critical", "high", "medium"}:
            bucket[sev] += 1
        src = str(item.get("source") or "unknown")
        bucket["sources"][src] = int(bucket["sources"].get(src, 0)) + 1
        current_ts = str(item.get("created_at") or "")
        if current_ts and current_ts > str(bucket.get("last_incident_at") or ""):
            bucket["last_incident_at"] = current_ts

    summary_rows = sorted(provider_summary.values(), key=lambda row: row.get("incidents", 0), reverse=True)

    retry_queue_pipeline = [
        {
            "$group": {
                "_id": {
                    "integration": {"$ifNull": ["$integration_id", "unknown"]},
                    "status": {"$ifNull": ["$status", "unknown"]},
                },
                "count": {"$sum": 1},
            }
        }
    ]
    queue_rows = await db.webhook_retry_queue.aggregate(retry_queue_pipeline).to_list(500)
    queue_by_provider: Dict[str, Dict[str, Any]] = {}
    for row in queue_rows:
        key = row.get("_id") or {}
        integration = _provider_name(str(key.get("integration") or "unknown"))
        status = str(key.get("status") or "unknown")
        bucket = queue_by_provider.setdefault(
            integration,
            {
                "provider": integration,
                "pending": 0,
                "processing": 0,
                "exhausted": 0,
                "success": 0,
                "other": 0,
                "total": 0,
            },
        )
        count = int(row.get("count") or 0)
        bucket["total"] += count
        if status in {"pending", "processing", "exhausted", "success"}:
            bucket[status] += count
        else:
            bucket["other"] += count

    queue_snapshot = sorted(queue_by_provider.values(), key=lambda row: row.get("total", 0), reverse=True)
    if provider_filter != "all":
        queue_snapshot = [row for row in queue_snapshot if row.get("provider") == provider_filter]

    return {
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "provider_filter": provider_filter,
        "summary": {
            "total_incidents": len(incidents),
            "providers_impacted": len(summary_rows),
            "critical_incidents": sum(int(row.get("critical") or 0) for row in summary_rows),
            "high_incidents": sum(int(row.get("high") or 0) for row in summary_rows),
        },
        "provider_rollup": summary_rows,
        "incident_timeline": incidents,
        "webhook_retry_queue": queue_snapshot,
    }


@router.get("/provider-incidents/canary-status")
async def provider_incident_canary_status(request: Request):
    await _require_admin(request)

    now = datetime.now(timezone.utc)
    jobs = [
        ("critical_journey_monitor", "Critical Journey Monitor", 30),
        ("admin_routes_sentinel", "Admin Routes Sentinel", 30),
        ("preview_browser_e2e_wake_and_run_nightly", "Nightly Preview Browser E2E", 24 * 60 + 90),
        ("global_parity_audit_nightly", "Global Parity Nightly", 24 * 60 + 120),
        ("platform_e2e_regression_gate", "E2E Regression Gate", 60),
        ("growth_integrity_monitor", "Growth Integrity Monitor", 60),
        ("fedapay_webhook_self_heal", "FedaPay Webhook Self-Heal", 20),
    ]
    rows = await db.scheduler_heartbeats.find(
        {"job_id": {"$in": [job[0] for job in jobs]}},
        {"_id": 0},
    ).to_list(200)
    row_map = {str(row.get("job_id") or ""): row for row in rows}

    items = []
    for job_id, label, stale_minutes in jobs:
        row = row_map.get(job_id, {})
        status = str(row.get("status") or "unknown").lower()
        last_run = _parse_iso_datetime(row.get("last_run"))
        age_minutes = int((now - last_run).total_seconds() // 60) if last_run else None
        stale = bool(age_minutes is not None and age_minutes > stale_minutes)
        health = "healthy"
        if status in {"error", "critical"}:
            health = "critical"
        elif status in {"warning", "degraded", "skipped"}:
            health = "warning"
        if stale:
            health = "warning" if health == "healthy" else health
        items.append(
            {
                "job_id": job_id,
                "label": label,
                "status": status,
                "health": health,
                "last_run": row.get("last_run"),
                "detail": row.get("detail") or "",
                "age_minutes": age_minutes,
                "stale": stale,
            }
        )

    route_states = await db.admin_routes_sentinel_state.find({}, {"_id": 0, "route_key": 1, "status": 1, "updated_at": 1}).to_list(20)
    unhealthy_routes = [r for r in route_states if str(r.get("status") or "").lower() == "unhealthy"]
    preview_state = await db.preview_browser_e2e_state.find_one({"key": "global"}, {"_id": 0, "last_run": 1, "last_gate_status": 1}) or {}
    admin_gate = await db.system_runtime_flags.find_one(
        {"key": "admin_e2e_health_gate_state"},
        {"_id": 0, "state": 1, "last_run_at": 1},
    ) or {}

    return {
        "generated_at": now.isoformat(),
        "summary": {
            "healthy": sum(1 for item in items if item.get("health") == "healthy"),
            "warning": sum(1 for item in items if item.get("health") == "warning"),
            "critical": sum(1 for item in items if item.get("health") == "critical"),
            "unhealthy_admin_routes": len(unhealthy_routes),
            "preview_gate_status": str(preview_state.get("last_gate_status") or "unknown"),
            "admin_e2e_gate_status": str(admin_gate.get("state") or "unknown"),
        },
        "jobs": items,
        "admin_route_states": route_states,
        "preview_browser_e2e": preview_state,
        "admin_e2e_gate": admin_gate,
    }


class ProviderIncidentCanaryRunRequest(BaseModel):
    canary_id: str


@router.post("/provider-incidents/canary-run-now")
async def provider_incident_canary_run_now(request: Request, body: ProviderIncidentCanaryRunRequest):
    await _require_admin(request)

    canary_id = str(body.canary_id or "").strip().lower()
    if not canary_id:
        raise HTTPException(status_code=400, detail="canary_id is required")

    from scheduler_jobs import (
        scheduled_critical_journey_monitor,
        scheduled_e2e_regression_gate,
        scheduled_growth_integrity_monitor,
    )

    handlers = {
        "critical_journey_monitor": scheduled_critical_journey_monitor,
        "platform_e2e_regression_gate": scheduled_e2e_regression_gate,
        "growth_integrity_monitor": scheduled_growth_integrity_monitor,
    }
    handler = handlers.get(canary_id)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail="Unsupported canary_id. Use critical_journey_monitor, platform_e2e_regression_gate, or growth_integrity_monitor.",
        )

    started_at = datetime.now(timezone.utc).isoformat()
    result = await handler()
    return {
        "ok": True,
        "canary_id": canary_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
