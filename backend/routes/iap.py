"""
In-App Purchase (IAP) — Server-side receipt validation & subscription management
for Apple App Store (Server API v2) and Google Play Store.

Product ID mapping:
  - com.realaicoach.basic.monthly  -> Basic plan, monthly
  - com.realaicoach.basic.yearly   -> Basic plan, yearly
  - com.realaicoach.premium.monthly -> Premium plan, monthly
  - com.realaicoach.premium.yearly  -> Premium plan, yearly
"""
import os
import json
import html
import base64
import time
import uuid
import asyncio
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from shared.pricing_policy import get_plan_amount

import httpx
import jwt as pyjwt
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.db import db, get_current_user
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.tax_compliance_engine import (
    append_financial_ledger_entry,
    build_financial_totals,
    calculate_tax_quote,
    estimate_processing_fee,
    log_tax_calculation,
    resolve_product_type,
)
from utils.email_notifications import send_fraud_alert_email
from utils.iap_secret_runtime import (
    hydrate_iap_runtime_secrets,
    compute_iap_provider_readiness,
    get_iap_secret_diagnostics,
)
from .subscription_enforcement import dispatch_subscription_expiry_notification

logger = logging.getLogger("iap")

router = APIRouter(prefix="/iap", tags=["In-App Purchases"])

# Ensure runtime secret hydration is attempted on module load.
_IAP_RUNTIME_HYDRATION_BOOT = hydrate_iap_runtime_secrets()

# ── Product ID -> Plan mapping ──
PRODUCT_MAP = {
    "com.realaicoach.basic.monthly":   {"plan": "basic",   "period": "monthly"},
    "com.realaicoach.basic.yearly":    {"plan": "basic",   "period": "yearly"},
    "com.realaicoach.premium.monthly": {"plan": "premium", "period": "monthly"},
    "com.realaicoach.premium.yearly":  {"plan": "premium", "period": "yearly"},
}

PLAN_PRICES = {
    "basic":   {"monthly": get_plan_amount("basic", "monthly"),  "yearly": get_plan_amount("basic", "yearly")},
    "premium": {"monthly": get_plan_amount("premium", "monthly"), "yearly": get_plan_amount("premium", "yearly")},
}

IAP_COMMISSION_REDUCED_RATE = 0.15
IAP_COMMISSION_STANDARD_RATE = 0.30

DEFAULT_COMMISSION_POLICY = {
    "policy_id": "global_iap_commission_policy",
    "providers": {
        "apple": {"default_tier": "standard", "reduced_rate": IAP_COMMISSION_REDUCED_RATE, "standard_rate": IAP_COMMISSION_STANDARD_RATE},
        "google": {"default_tier": "standard", "reduced_rate": IAP_COMMISSION_REDUCED_RATE, "standard_rate": IAP_COMMISSION_STANDARD_RATE},
    },
    "segment_rules": [
        {"segment": "small_business", "provider": "all", "tier": "reduced", "enabled": True},
        {"segment": "enterprise", "provider": "all", "tier": "standard", "enabled": True},
    ],
    "updated_at": None,
}


def _resolve_iap_provider_readiness() -> dict:
    hydrate_iap_runtime_secrets(force=True)
    return compute_iap_provider_readiness()


async def _record_iap_readiness_audit(readiness: dict) -> None:
    try:
        providers = readiness.get("providers") or {}
        apple_state = str((providers.get("apple") or {}).get("readiness_state") or "unavailable")
        google_state = str((providers.get("google") or {}).get("readiness_state") or "unavailable")
        now_iso = datetime.now(timezone.utc).isoformat()

        prev = await db.system_state.find_one({"key": "iap_readiness_state"}, {"_id": 0, "value": 1})
        prev_val = (prev or {}).get("value") or {}
        prev_apple = str(prev_val.get("apple_state") or "")
        prev_google = str(prev_val.get("google_state") or "")

        await db.system_state.update_one(
            {"key": "iap_readiness_state"},
            {
                "$set": {
                    "value": {
                        "apple_state": apple_state,
                        "google_state": google_state,
                        "updated_at": now_iso,
                    },
                    "updated_at": now_iso,
                },
                "$setOnInsert": {
                    "created_at": now_iso,
                },
            },
            upsert=True,
        )

        regressions = []
        if prev_apple == "live_ready" and apple_state == "unavailable":
            regressions.append("apple")
        if prev_google == "live_ready" and google_state == "unavailable":
            regressions.append("google")
        if regressions:
            await db.iap_readiness_alerts.insert_one(
                {
                    "alert_id": f"iap_alert_{uuid.uuid4().hex[:12]}",
                    "type": "readiness_regression",
                    "providers": regressions,
                    "from": {"apple": prev_apple, "google": prev_google},
                    "to": {"apple": apple_state, "google": google_state},
                    "created_at": now_iso,
                }
            )
            logger.warning("IAP readiness regression detected: %s", regressions)
    except Exception as exc:
        logger.error("Failed to persist IAP readiness audit: %s", exc)


def _should_suppress_iap_notifications(parsed: Optional[dict]) -> bool:
    parsed = parsed or {}
    environment = str(parsed.get("environment") or "").strip().lower()
    return bool(parsed.get("suppress_notifications")) or environment == "health_drill"


def _coerce_commission_rate(value: Any, fallback: float) -> float:
    try:
        v = float(value)
    except Exception:
        return fallback
    if v <= 0:
        return fallback
    if v > 1:
        v = v / 100.0
    if v <= IAP_COMMISSION_REDUCED_RATE + 0.001:
        return IAP_COMMISSION_REDUCED_RATE
    return IAP_COMMISSION_STANDARD_RATE


def _resolve_iap_commission_rate(platform: str, user_doc: Optional[dict], parsed: dict, policy: Optional[dict] = None) -> dict:
    provider_key = "apple" if platform == "apple" else "google"
    tier_raw = str((user_doc or {}).get("iap_commission_tier") or "").strip().lower()
    provider_override = (user_doc or {}).get(f"{provider_key}_iap_commission_rate")
    payload_override = parsed.get("commission_rate") or parsed.get("store_fee_rate")
    is_small_business = bool((user_doc or {}).get("iap_small_business_eligible"))
    provider_policy = (policy or {}).get("providers", {}).get(provider_key, {}) if isinstance(policy, dict) else {}
    default_tier = _normalized_tier(str(provider_policy.get("default_tier", "standard")))
    segment_tier = _resolve_segment_policy_tier(policy or {}, user_doc, provider_key)

    if payload_override is not None:
        rate = _coerce_commission_rate(payload_override, IAP_COMMISSION_STANDARD_RATE)
        return {"rate": rate, "tier": "reduced" if rate <= IAP_COMMISSION_REDUCED_RATE else "standard", "source": "payload_override"}

    if provider_override is not None:
        rate = _coerce_commission_rate(provider_override, IAP_COMMISSION_STANDARD_RATE)
        return {"rate": rate, "tier": "reduced" if rate <= IAP_COMMISSION_REDUCED_RATE else "standard", "source": "provider_override"}

    if tier_raw in {"reduced", "small_business", "15", "15%"} or is_small_business:
        return {"rate": IAP_COMMISSION_REDUCED_RATE, "tier": "reduced", "source": "small_business_or_tier"}

    if segment_tier:
        rate = _rate_from_tier(segment_tier)
        return {"rate": rate, "tier": segment_tier, "source": "segment_policy"}

    rate = _rate_from_tier(default_tier)
    return {"rate": rate, "tier": default_tier, "source": "provider_default_policy"}


def _build_checkout_breakdown(financials: dict, commission_rate: float) -> dict:
    return {
        "base_plan_price": round(float(financials.get("subtotal", 0) or 0), 2),
        "platform_fee": round(float(financials.get("processing_fee", 0) or 0), 2),
        "platform_fee_rate_pct": round(float(commission_rate) * 100, 2),
        "taxes": round(float(financials.get("tax_amount", 0) or 0), 2),
        "final_total": round(float(financials.get("total_amount", 0) or 0), 2),
        "currency": "USD",
    }


def _normalized_tier(tier: str) -> str:
    t = str(tier or "standard").strip().lower()
    return "reduced" if t in {"reduced", "small_business", "15", "15%"} else "standard"


def _rate_from_tier(tier: str) -> float:
    return IAP_COMMISSION_REDUCED_RATE if _normalized_tier(tier) == "reduced" else IAP_COMMISSION_STANDARD_RATE


async def _get_commission_policy() -> dict:
    stored = await db.iap_commission_policies.find_one(
        {"policy_id": DEFAULT_COMMISSION_POLICY["policy_id"]},
        {"_id": 0},
    ) or {}
    providers = {
        "apple": {
            **DEFAULT_COMMISSION_POLICY["providers"]["apple"],
            **(stored.get("providers", {}).get("apple", {}) if stored.get("providers") else {}),
        },
        "google": {
            **DEFAULT_COMMISSION_POLICY["providers"]["google"],
            **(stored.get("providers", {}).get("google", {}) if stored.get("providers") else {}),
        },
    }
    return {
        "policy_id": DEFAULT_COMMISSION_POLICY["policy_id"],
        "providers": providers,
        "segment_rules": stored.get("segment_rules", DEFAULT_COMMISSION_POLICY["segment_rules"]),
        "updated_at": stored.get("updated_at"),
    }


async def _save_commission_policy(payload: dict) -> dict:
    providers = payload.get("providers", {})
    segment_rules = payload.get("segment_rules", [])
    normalized = {
        "policy_id": DEFAULT_COMMISSION_POLICY["policy_id"],
        "providers": {
            "apple": {
                "default_tier": _normalized_tier(providers.get("apple", {}).get("default_tier", "standard")),
                "reduced_rate": IAP_COMMISSION_REDUCED_RATE,
                "standard_rate": IAP_COMMISSION_STANDARD_RATE,
            },
            "google": {
                "default_tier": _normalized_tier(providers.get("google", {}).get("default_tier", "standard")),
                "reduced_rate": IAP_COMMISSION_REDUCED_RATE,
                "standard_rate": IAP_COMMISSION_STANDARD_RATE,
            },
        },
        "segment_rules": [
            {
                "segment": str(rule.get("segment", "default")).strip().lower(),
                "provider": str(rule.get("provider", "all")).strip().lower(),
                "tier": _normalized_tier(str(rule.get("tier", "standard"))),
                "enabled": bool(rule.get("enabled", True)),
            }
            for rule in segment_rules
            if str(rule.get("segment", "")).strip()
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.iap_commission_policies.update_one(
        {"policy_id": DEFAULT_COMMISSION_POLICY["policy_id"]},
        {"$set": normalized},
        upsert=True,
    )
    return normalized


def _resolve_segment_policy_tier(policy: dict, user_doc: Optional[dict], platform: str) -> Optional[str]:
    segment = str((user_doc or {}).get("account_segment") or "").strip().lower()
    if not segment:
        return None
    rules = policy.get("segment_rules", []) if isinstance(policy, dict) else []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if str(rule.get("segment", "")).strip().lower() != segment:
            continue
        provider = str(rule.get("provider", "all")).strip().lower()
        if provider not in {"all", platform}:
            continue
        return _normalized_tier(str(rule.get("tier", "standard")))
    return None


def _infer_transition_type(previous_plan: str, new_plan: str) -> str:
    prev = str(previous_plan or "free").lower()
    new = str(new_plan or "free").lower()
    if prev == "free" and new != "free":
        return "activation"
    if prev != "free" and new == "free":
        return "cancellation"
    if prev == new:
        return "renewal"
    prev_price = PLAN_PRICES.get(prev, {}).get("monthly", 0)
    new_price = PLAN_PRICES.get(new, {}).get("monthly", 0)
    return "upgrade" if new_price > prev_price else "downgrade"


async def _append_subscription_timeline_event(
    *,
    user_id: str,
    platform: str,
    event_type: str,
    from_plan: str,
    to_plan: str,
    status: str,
    effective_at: str,
    metadata: Optional[dict] = None,
) -> None:
    await db.iap_subscription_timeline.insert_one(
        {
            "event_id": f"iapevt_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "platform": platform,
            "event_type": event_type,
            "from_plan": from_plan,
            "to_plan": to_plan,
            "status": status,
            "effective_at": effective_at,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _archive_iap_compliance_bundle(
    *,
    transaction_id: str,
    user_id: str,
    user_email: str,
    plan: str,
    period: str,
    platform: str,
    pricing_breakdown: dict,
    tax_quote: dict,
    parsed: dict,
    compliance_result: dict,
    fraud_result: dict,
    jurisdiction: dict,
) -> dict:
    from routes.payments import _generate_pdf_from_payment

    receipt_number = f"IAP-{transaction_id[:12].upper()}"
    payment_for_pdf = {
        "payment_id": transaction_id,
        "transaction_id": transaction_id,
        "plan_id": plan,
        "billing_period": period,
        "provider": "iap_google" if platform == "google" else "iap_apple",
        "payment_method": "iap_google" if platform == "google" else "iap_apple",
        "status": "completed" if parsed.get("active") else "expired",
        "created_at": datetime.now(timezone.utc),
        "amount": pricing_breakdown.get("base_plan_price", 0),
        "subtotal": pricing_breakdown.get("base_plan_price", 0),
        "tax_amount": pricing_breakdown.get("taxes", 0),
        "processing_fee": pricing_breakdown.get("platform_fee", 0),
        "total_amount": pricing_breakdown.get("final_total", 0),
        "currency": pricing_breakdown.get("currency", "USD"),
        "jurisdiction": jurisdiction,
        "fee_pass_through": True,
        "receipt_number": receipt_number,
    }
    receipt_pdf = await _generate_pdf_from_payment(
        "receipt",
        payment_for_pdf,
        user_email,
        user_email,
    )
    signed_payload_hash = hashlib.sha256(json.dumps(parsed, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    bundle = {
        "bundle_id": f"iapbundle_{uuid.uuid4().hex[:12]}",
        "transaction_id": transaction_id,
        "user_id": user_id,
        "user_email": user_email,
        "plan": plan,
        "period": period,
        "platform": platform,
        "receipt_number": receipt_number,
        "pricing_breakdown": pricing_breakdown,
        "tax_snapshot": {
            "tax_rate": tax_quote.get("tax_rate", 0),
            "tax_amount": tax_quote.get("tax_amount", 0),
            "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
            "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
            "tax_breakdown": tax_quote.get("tax_breakdown", []),
            "jurisdiction": jurisdiction,
        },
        "compliance_audit_id": compliance_result.get("audit_id"),
        "fraud_audit_id": fraud_result.get("audit_id"),
        "signed_payload_hash": signed_payload_hash,
        "receipt_pdf_b64": base64.b64encode(receipt_pdf).decode("utf-8"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.iap_compliance_bundles.update_one(
        {"transaction_id": transaction_id},
        {"$set": bundle},
        upsert=True,
    )
    return {k: v for k, v in bundle.items() if k != "receipt_pdf_b64"}


async def _enqueue_webhook_retry(platform: str, payload: dict, reason: str) -> None:
    await db.iap_webhook_retry_queue.insert_one(
        {
            "retry_id": f"iapretry_{uuid.uuid4().hex[:12]}",
            "platform": platform,
            "payload": payload,
            "reason": reason,
            "attempts": 0,
            "status": "pending",
            "last_error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _log_webhook_delivery(
    *,
    platform: str,
    notification_type: str,
    started_at: float,
    status: str,
    source: str,
    error: Optional[str] = None,
):
    latency_ms = int((time.time() - started_at) * 1000)
    await db.iap_webhook_delivery_logs.insert_one(
        {
            "delivery_id": f"iapwh_{uuid.uuid4().hex[:12]}",
            "platform": platform,
            "notification_type": str(notification_type),
            "status": status,
            "latency_ms": latency_ms,
            "source": source,
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def run_iap_webhook_retry_cycle(batch_size: int = 15) -> dict:
    pending = await db.iap_webhook_retry_queue.find(
        {"status": "pending", "attempts": {"$lt": 5}},
        {"_id": 0},
    ).sort("created_at", 1).limit(batch_size).to_list(batch_size)

    if not pending:
        return {"processed": 0, "succeeded": 0, "failed": 0}

    processed = 0
    succeeded = 0
    failed = 0
    async with httpx.AsyncClient(timeout=25.0) as client:
        for item in pending:
            processed += 1
            retry_id = item.get("retry_id")
            platform = item.get("platform")
            endpoint = "/api/iap/apple/webhook" if platform == "apple" else "/api/iap/google/webhook"
            try:
                response = await client.post(f"http://127.0.0.1:8001{endpoint}", json=item.get("payload", {}))
                if response.status_code == 200:
                    succeeded += 1
                    await db.iap_webhook_retry_queue.update_one(
                        {"retry_id": retry_id},
                        {"$set": {"status": "succeeded", "updated_at": datetime.now(timezone.utc).isoformat()}},
                    )
                else:
                    raise RuntimeError(f"retry_status_{response.status_code}")
            except Exception as exc:
                failed += 1
                new_attempts = int(item.get("attempts", 0) or 0) + 1
                await db.iap_webhook_retry_queue.update_one(
                    {"retry_id": retry_id},
                    {
                        "$set": {
                            "attempts": new_attempts,
                            "status": "failed" if new_attempts >= 5 else "pending",
                            "last_error": str(exc)[:200],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )

    backlog = await db.iap_webhook_retry_queue.count_documents({"status": "pending"})
    if backlog >= 10:
        from utils.email_service import send_catalog_template

        admin_targets = await db.users.find(
            {"full_access": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ).to_list(20)
        for admin in admin_targets:
            try:
                await send_catalog_template(
                    recipient_email=admin.get("email"),
                    template_key="system_alert_admin",
                    alert_type="IAP Webhook Retry Backlog",
                    severity="HIGH",
                    description=f"Pending webhook retries: {backlog}. Please inspect IAP SLO dashboard.",
                    component="IAP Webhook Engine",
                )
            except Exception as exc:
                logger.warning(f"Failed sending webhook retry alert email: {exc}")

    return {"processed": processed, "succeeded": succeeded, "failed": failed, "pending_backlog": backlog}


async def _compute_iap_slo_snapshot(hours: int = 24) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    logs = await db.iap_webhook_delivery_logs.find(
        {"created_at": {"$gte": since}},
        {"_id": 0, "status": 1, "latency_ms": 1, "platform": 1},
    ).to_list(5000)
    total = len(logs)
    errors = sum(1 for row in logs if row.get("status") != "success")
    latencies = sorted(int(row.get("latency_ms", 0) or 0) for row in logs)
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0
    retry_pending = await db.iap_webhook_retry_queue.count_documents({"status": "pending"})
    retry_failed = await db.iap_webhook_retry_queue.count_documents({"status": "failed"})
    return {
        "window_hours": hours,
        "total_webhooks": total,
        "error_count": errors,
        "error_rate_pct": round((errors / total) * 100, 2) if total else 0,
        "latency_avg_ms": avg_latency,
        "latency_p95_ms": p95,
        "retry_queue_pending": retry_pending,
        "retry_queue_failed": retry_failed,
    }


async def run_iap_nightly_health_drill() -> dict:
    drill_email = os.environ.get("IAP_HEALTH_DRILL_EMAIL") or "entitlement.test@example.com"
    user_doc = await db.users.find_one({"email": drill_email}, {"_id": 0})
    if not user_doc:
        user_doc = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": drill_email,
            "name": "IAP Health Drill",
            "subscription_plan": "free",
            "subscription_status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "password_hash": "SIMULATED_EXTERNAL_IDENTITY",
        }
        await db.users.insert_one({**user_doc})

    user_id = user_doc["user_id"]
    started_at = datetime.now(timezone.utc)
    results = []
    for platform in ("google", "apple"):
        tx_id = f"drill_{platform}_{uuid.uuid4().hex[:10]}"
        parsed = {
            "valid": True,
            "active": True,
            "plan": "basic",
            "period": "monthly",
            "product_id": "com.realaicoach.basic.monthly",
            "transaction_id": tx_id,
            "original_transaction_id": f"orig_{tx_id}",
            "purchase_token": f"token_{uuid.uuid4().hex[:18]}" if platform == "google" else "",
            "auto_renewing": True,
            "expires_at": (started_at + timedelta(days=30)).isoformat(),
            "country_code": "US",
            "state_code": "OK",
            "postal_code": "73102",
            "city": "Oklahoma City",
            "environment": "health_drill",
            "suppress_notifications": True,
        }
        update = await _apply_iap_subscription(
            user_id=user_id,
            parsed=parsed,
            platform=platform,
            notify_async=False,
            custom_receipt_subject="IAP Health Drill — Receipt Validation",
        )
        results.append({
            "platform": platform,
            "transaction_id": tx_id,
            "checks": {
                "subscription_active": update.get("subscription_status") == "active",
                "fee_accuracy": round(float(update.get("pricing_breakdown", {}).get("base_plan_price", 0)) + float(update.get("pricing_breakdown", {}).get("platform_fee", 0)) + float(update.get("pricing_breakdown", {}).get("taxes", 0)), 2)
                == round(float(update.get("pricing_breakdown", {}).get("final_total", 0)), 2),
                "notifications_suppressed": bool(update.get("notification_suppressed")),
            },
            "pricing_breakdown": update.get("pricing_breakdown", {}),
        })

    slo = await _compute_iap_slo_snapshot(24)
    report = {
        "report_id": f"iapdrill_{uuid.uuid4().hex[:12]}",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "target_email": drill_email,
        "results": results,
        "slo_snapshot": slo,
    }
    await db.iap_health_drill_reports.insert_one({**report})

    from utils.email_service import send_catalog_template

    # Build summary for v7 template
    results = report.get("results", {})
    result_items = []
    for k, v in results.items():
        if isinstance(v, dict):
            result_items.append(f"{k}: {v.get('status', 'unknown')}")
        else:
            result_items.append(f"{k}: {v}")
    results_summary = "; ".join(result_items) if result_items else "All checks completed"

    slo = report.get("slo_snapshot", {})
    slo_status = "Healthy" if slo.get("compliant", True) else "Degraded"

    admin_targets = await db.users.find(
        {"full_access": True, "email": {"$exists": True, "$ne": ""}},
        {"_id": 0, "email": 1, "name": 1},
    ).to_list(20)
    for admin in admin_targets:
        try:
            await send_catalog_template(
                recipient_email=admin.get("email"),
                template_key="iap_nightly_drill",
                recipient_name=admin.get("name", ""),
                report_id=str(report.get("report_id", "")),
                started_at=str(report.get("started_at", "")),
                completed_at=str(report.get("completed_at", "")),
                results_summary=results_summary,
                slo_status=slo_status,
            )
        except Exception as exc:
            logger.warning(f"Failed to send nightly IAP drill email: {exc}")

    return report


def _render_iap_nightly_drill_report_email(report: dict) -> str:
    report_json = html.escape(json.dumps(report, indent=2))
    report_id = str(report.get("report_id") or "unknown")
    started_at = str(report.get("started_at") or "-")
    completed_at = str(report.get("completed_at") or "-")
    return f"""
<div data-testid="iap-nightly-drill-email-body" style="max-width:620px;margin:0 auto;background:#0B1220;border:1px solid #24324A;border-radius:16px;padding:20px;">
  <h2 style="margin:0 0 8px;color:#F8FAFC;font-size:20px;font-weight:800;letter-spacing:-0.2px;">IAP Compliance & Reliability Report</h2>
  <p style="margin:0 0 14px;color:#94A3B8;font-size:12px;line-height:1.45;">
    Report ID: <span style="color:#E2E8F0;font-weight:700;">{report_id}</span><br>
    Started: <span style="color:#CBD5E1;">{started_at}</span> &middot;
    Completed: <span style="color:#CBD5E1;">{completed_at}</span>
  </p>
  <pre data-testid="iap-nightly-drill-report-json" style="margin:0;padding:14px;border-radius:12px;border:1px solid #334155;background:#0F172A;color:#E2E8F0;font-size:12px;line-height:1.55;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;">{report_json}</pre>
</div>
"""


async def _evaluate_iap_compliance(user_id: str, platform: str, jurisdiction: dict, parsed: dict, financials: dict, commission_rate: float) -> dict:
    issues: list[str] = []
    country = str(jurisdiction.get("country") or "").upper()
    state = str(jurisdiction.get("state") or "").upper()
    if country == "US" and not state:
        issues.append("missing_state_for_us_tax_jurisdiction")
    if commission_rate < IAP_COMMISSION_REDUCED_RATE or commission_rate > IAP_COMMISSION_STANDARD_RATE:
        issues.append("commission_rate_out_of_policy_range")
    if float(financials.get("total_amount", 0) or 0) < float(financials.get("amount_gross", 0) or 0):
        issues.append("total_less_than_gross")

    result = {
        "audit_id": f"iapcmp_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "platform": platform,
        "transaction_id": parsed.get("transaction_id") or parsed.get("order_id"),
        "jurisdiction": jurisdiction,
        "commission_rate": commission_rate,
        "status": "pass" if not issues else "warning",
        "issues": issues,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.iap_compliance_audit.insert_one({**result})
    return result


async def _run_iap_fraud_check(user_id: str, platform: str, parsed: dict) -> dict:
    risk_score = 5
    signals: list[str] = []
    tx_id = parsed.get("transaction_id") or parsed.get("order_id")
    if not tx_id:
        risk_score += 20
        signals.append("missing_transaction_id")

    if tx_id:
        duplicate = await db.iap_transactions.find_one(
            {"transaction_id": tx_id, "user_id": {"$ne": user_id}},
            {"_id": 0, "user_id": 1},
        )
        if duplicate:
            risk_score += 75
            signals.append("transaction_id_seen_for_different_user")

    if not parsed.get("active", False):
        risk_score += 15
        signals.append("inactive_purchase_state")

    if str(parsed.get("environment") or "").lower() == "production" and str(parsed.get("purchase_token") or "") == "":
        risk_score += 10
        signals.append("missing_purchase_token_production")

    risk_score = min(100, risk_score)
    risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 35 else "low"

    result = {
        "audit_id": f"iapfrd_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "platform": platform,
        "transaction_id": tx_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "signals": signals,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.iap_fraud_audit.insert_one({**result})

    if risk_score >= 70:
        admin_targets = await db.users.find(
            {"full_access": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ).to_list(20)
        for admin in admin_targets:
            try:
                await send_fraud_alert_email(
                    admin_email=admin.get("email", ""),
                    user_email=str(parsed.get("user_email") or user_id),
                    risk_score=risk_score,
                    risk_level=risk_level,
                    signals=", ".join(signals) if signals else "none",
                    scan_time=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as exc:
                logger.warning(f"IAP fraud alert email failed for {admin.get('email')}: {exc}")

    return result


# ── Request Models ──
class AppleReceiptRequest(BaseModel):
    transaction_id: str
    receipt_data: Optional[str] = None
    saved_card_id: Optional[str] = None


class GoogleReceiptRequest(BaseModel):
    purchase_token: str
    product_id: str
    subscription_id: Optional[str] = None
    saved_card_id: Optional[str] = None


class IAPCheckoutPreviewRequest(BaseModel):
    product_id: str
    platform: str
    country_code: Optional[str] = None
    state_code: Optional[str] = None
    postal_code: Optional[str] = None


class IAPSimulationRequest(BaseModel):
    email: str
    name: Optional[str] = None
    address_line: Optional[str] = None
    plan: str = "basic"
    period: str = "monthly"
    platform: str = "google"
    city: str = "Oklahoma City"
    state_code: str = "OK"
    country_code: str = "US"
    postal_code: str = "73102"
    simulate_failure_case: bool = False


class IAPSandboxValidationRequest(BaseModel):
    apple_transaction_id: Optional[str] = None
    google_product_id: Optional[str] = None
    google_purchase_token: Optional[str] = None


class IAPCommissionPolicyUpdate(BaseModel):
    providers: dict
    segment_rules: list[dict] = []


def _pick_first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _resolve_iap_jurisdiction_context(
    request: Optional[Request] = None,
    user_doc: Optional[dict] = None,
    *,
    country_code: Optional[str] = None,
    state_code: Optional[str] = None,
    postal_code: Optional[str] = None,
) -> dict:
    user_doc = user_doc or {}
    headers = request.headers if request else {}

    country = _pick_first_non_empty(
        country_code,
        user_doc.get("billing_country_code"),
        user_doc.get("billing_country"),
        user_doc.get("country_code"),
        user_doc.get("country"),
        headers.get("x-country-code"),
        headers.get("cf-ipcountry"),
        headers.get("x-vercel-ip-country"),
        headers.get("x-geo-country"),
        "US",
    ).upper()

    state = _pick_first_non_empty(
        state_code,
        user_doc.get("billing_state_code"),
        user_doc.get("billing_state"),
        user_doc.get("state_code"),
        user_doc.get("state"),
        headers.get("x-state-code"),
        headers.get("x-vercel-ip-country-region"),
        headers.get("x-geo-region"),
    ).upper()

    postal = _pick_first_non_empty(
        postal_code,
        user_doc.get("billing_postal_code"),
        user_doc.get("postal_code"),
        headers.get("x-postal-code"),
    )

    country_source = (
        "request_override"
        if country_code
        else "user_profile"
        if _pick_first_non_empty(user_doc.get("billing_country_code"), user_doc.get("billing_country"), user_doc.get("country_code"), user_doc.get("country"))
        else "request_header"
        if _pick_first_non_empty(headers.get("x-country-code"), headers.get("cf-ipcountry"), headers.get("x-vercel-ip-country"), headers.get("x-geo-country"))
        else "default"
    )

    state_source = (
        "request_override"
        if state_code
        else "user_profile"
        if _pick_first_non_empty(user_doc.get("billing_state_code"), user_doc.get("billing_state"), user_doc.get("state_code"), user_doc.get("state"))
        else "request_header"
        if _pick_first_non_empty(headers.get("x-state-code"), headers.get("x-vercel-ip-country-region"), headers.get("x-geo-region"))
        else "none"
    )

    return {
        "country": country,
        "state": state,
        "postal_code": postal,
        "source": {
            "country": country_source,
            "state": state_source,
            "postal_code": "request_override" if postal_code else "user_profile" if _pick_first_non_empty(user_doc.get("billing_postal_code"), user_doc.get("postal_code")) else "request_header",
        },
        "label": f"{country}-{state}".strip("-"),
    }


def _normalize_card_year(year: int) -> int:
    return year + 2000 if 0 < year < 100 else year


def _iap_card_expired(expiry_month: int, expiry_year: int) -> bool:
    month = int(expiry_month or 0)
    year = _normalize_card_year(int(expiry_year or 0))
    if month < 1 or month > 12:
        return True
    now = datetime.now(timezone.utc)
    return year < now.year or (year == now.year and month < now.month)


async def _resolve_iap_saved_card(user_id: str, saved_card_id: Optional[str]) -> Optional[dict]:
    if saved_card_id:
        card = await db.payment_cards.find_one({"card_id": saved_card_id, "user_id": user_id}, {"_id": 0})
        if not card:
            raise HTTPException(status_code=404, detail="Selected saved card was not found")
        if card.get("status") != "active":
            raise HTTPException(status_code=400, detail="Selected saved card is not active")
        expiry_month = int(card.get("expiry_month", 0) or 0)
        expiry_year = _normalize_card_year(int(card.get("expiry_year", 0) or 0))
        if _iap_card_expired(expiry_month, expiry_year):
            await db.payment_cards.update_one(
                {"card_id": saved_card_id},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            raise HTTPException(status_code=400, detail="Selected saved card is expired. Please update your card.")
        return {
            "card_id": card.get("card_id"),
            "card_type": card.get("card_type", "other"),
            "last_four": card.get("last_four", ""),
            "cardholder_name": card.get("cardholder_name", ""),
            "expiry_month": expiry_month,
            "expiry_year": expiry_year,
        }

    candidates = await db.payment_cards.find(
        {"user_id": user_id, "status": "active"},
        {"_id": 0},
    ).sort([("is_default", -1), ("created_at", -1)]).to_list(20)
    for card in candidates:
        expiry_month = int(card.get("expiry_month", 0) or 0)
        expiry_year = _normalize_card_year(int(card.get("expiry_year", 0) or 0))
        if _iap_card_expired(expiry_month, expiry_year):
            await db.payment_cards.update_one(
                {"card_id": card.get("card_id")},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            continue
        return {
            "card_id": card.get("card_id"),
            "card_type": card.get("card_type", "other"),
            "last_four": card.get("last_four", ""),
            "cardholder_name": card.get("cardholder_name", ""),
            "expiry_month": expiry_month,
            "expiry_year": expiry_year,
        }
    return None


# ── Apple App Store Server API v2 ──
APPLE_PRODUCTION_URL = "https://api.storekit.itunes.apple.com"
APPLE_SANDBOX_URL = "https://api.storekit-sandbox.itunes.apple.com"


def _get_apple_jwt() -> str:
    """Generate a JWT for Apple App Store Server API v2 authentication."""
    key_path = os.environ.get("APPLE_IAP_PRIVATE_KEY_PATH", "")
    key_id = os.environ.get("APPLE_IAP_KEY_ID", "")
    issuer_id = os.environ.get("APPLE_IAP_ISSUER_ID", "")
    bundle_id = os.environ.get("APPLE_BUNDLE_ID", "com.realaicoach.app")

    if not key_path or not os.path.exists(key_path):
        raise HTTPException(status_code=500, detail="Apple IAP key not configured")

    with open(key_path, "r") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": now + 3600,
        "aud": "appstoreconnect-v1",
        "bid": bundle_id,
    }
    headers = {"kid": key_id, "typ": "JWT"}
    token = pyjwt.encode(payload, private_key, algorithm="ES256", headers=headers)
    return token


async def _apple_api_request(path: str, method: str = "GET", sandbox: bool = False) -> dict:
    """Make an authenticated request to the Apple App Store Server API v2."""
    base_url = APPLE_SANDBOX_URL if sandbox else APPLE_PRODUCTION_URL
    token = _get_apple_jwt()

    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            resp = await client.get(f"{base_url}{path}", headers=headers)
        else:
            resp = await client.post(f"{base_url}{path}", headers=headers)

        if resp.status_code == 404 and not sandbox:
            return await _apple_api_request(path, method, sandbox=True)

        if resp.status_code == 401:
            return {"error": "Apple API authentication failed", "status_code": 401}

        if resp.status_code >= 400:
            return {"error": f"Apple API error {resp.status_code}", "status_code": resp.status_code}

        return resp.json()


def _decode_jws_payload(signed_payload: str) -> dict:
    """Decode a JWS signed payload from Apple (without full verification for now).
    In production, verify the x5c certificate chain against Apple's root CA."""
    try:
        parts = signed_payload.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"JWS decode error: {e}")
        return {}


async def _verify_apple_transaction(transaction_id: str) -> dict:
    """Look up a transaction using App Store Server API v2."""
    result = await _apple_api_request(f"/inApps/v1/transactions/{transaction_id}")

    if result.get("error"):
        return {"valid": False, "error": result["error"]}

    signed_transactions = result.get("signedTransactions", [])
    if not signed_transactions:
        return {"valid": False, "error": "No transaction found"}

    tx_info = _decode_jws_payload(signed_transactions[0])
    if not tx_info:
        return {"valid": False, "error": "Failed to decode transaction"}

    return _parse_apple_transaction(tx_info)


async def _get_apple_subscription_status(transaction_id: str) -> dict:
    """Get subscription status using App Store Server API v2."""
    result = await _apple_api_request(f"/inApps/v1/subscriptions/{transaction_id}")

    if result.get("error"):
        return {"valid": False, "error": result["error"]}

    data = result.get("data", [])
    if not data:
        return {"valid": False, "error": "No subscription data"}

    # Get the latest subscription status
    latest_item = data[0]
    last_transactions = latest_item.get("lastTransactions", [])
    if not last_transactions:
        return {"valid": False, "error": "No transactions in subscription"}

    latest_tx = last_transactions[0]
    status = latest_tx.get("status", 0)
    signed_tx = latest_tx.get("signedTransactionInfo", "")
    signed_renewal = latest_tx.get("signedRenewalInfo", "")

    tx_info = _decode_jws_payload(signed_tx) if signed_tx else {}
    renewal_info = _decode_jws_payload(signed_renewal) if signed_renewal else {}

    parsed = _parse_apple_transaction(tx_info)
    parsed["auto_renewing"] = renewal_info.get("autoRenewStatus", 0) == 1
    parsed["subscription_status_code"] = status
    # Status: 1=active, 2=expired, 3=billing_retry, 4=billing_grace, 5=revoked
    parsed["active"] = status == 1

    return parsed


def _parse_apple_transaction(tx_info: dict) -> dict:
    """Parse an Apple StoreKit 2 transaction info payload."""
    product_id = tx_info.get("productId", "")
    expires_ms = tx_info.get("expiresDate", 0)
    expires_at = datetime.fromtimestamp(expires_ms / 1000, tz=timezone.utc) if expires_ms else None
    is_active = expires_at and expires_at > datetime.now(timezone.utc)

    mapping = PRODUCT_MAP.get(product_id, {})
    environment = tx_info.get("environment", "Production")

    return {
        "valid": True,
        "active": is_active,
        "product_id": product_id,
        "plan": mapping.get("plan", "free"),
        "period": mapping.get("period", "monthly"),
        "original_transaction_id": tx_info.get("originalTransactionId"),
        "transaction_id": tx_info.get("transactionId"),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "auto_renewing": True,
        "environment": environment.lower() if environment else "production",
        "purchase_date": tx_info.get("purchaseDate"),
        "bundle_id": tx_info.get("bundleId"),
    }


# ── Google Play Validation ──
async def _verify_google_receipt(product_id: str, purchase_token: str) -> dict:
    """Validate subscription purchase with Google Play Developer API."""
    package_name = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", "com.realaicoach.app")
    gcp_key_path = os.environ.get("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH", "")

    if not gcp_key_path:
        gcp_key_path = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "")

    if not gcp_key_path or not os.path.exists(gcp_key_path):
        return {"valid": False, "error": "Google Play service account not configured"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            gcp_key_path,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        service = build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)

        result = service.purchases().subscriptions().get(
            packageName=package_name,
            subscriptionId=product_id,
            token=purchase_token,
        ).execute()

        return result
    except Exception as e:
        logger.error(f"Google Play verification error: {e}")
        return {"valid": False, "error": str(e)}


def _parse_google_receipt(result: dict, product_id: str) -> dict:
    """Extract subscription info from Google Play API response."""
    if result.get("valid") is False:
        return result

    expires_ms = int(result.get("expiryTimeMillis", "0"))
    expires_at = datetime.fromtimestamp(expires_ms / 1000, tz=timezone.utc) if expires_ms else None
    is_active = expires_at and expires_at > datetime.now(timezone.utc)

    payment_state = result.get("paymentState", 0)
    cancel_reason = result.get("cancelReason")
    auto_renewing = result.get("autoRenewing", False)

    mapping = PRODUCT_MAP.get(product_id, {})

    return {
        "valid": True,
        "active": is_active,
        "product_id": product_id,
        "plan": mapping.get("plan", "free"),
        "period": mapping.get("period", "monthly"),
        "order_id": result.get("orderId"),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "auto_renewing": auto_renewing,
        "payment_state": payment_state,
        "cancel_reason": cancel_reason,
        "environment": "sandbox" if result.get("purchaseType") == 0 else "production",
    }


# ── Helper: Update user subscription from IAP ──
async def _send_iap_notification(
    user_id: str,
    plan_name: str,
    amount: float,
    platform: str,
    period: str,
    expires_at: str,
    is_renewal: bool = False,
    transaction_context: Optional[dict] = None,
    custom_receipt_subject: Optional[str] = None,
):
    """Send email + in-app notification for IAP payment."""
    try:
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user_doc or not user_doc.get("email"):
            return
        email = user_doc["email"]
        name = user_doc.get("name", "")
        platform_label = "App Store" if platform == "apple" else "Google Play"
        ticket_id = f"IAP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Use unified payment notification pipeline only (single in-app + single receipt/admin email flow).
        from routes.payments import _send_payment_notification
        renewal_date = expires_at[:10] if expires_at else ""
        tx_ctx = {**(transaction_context or {})}
        if custom_receipt_subject:
            tx_ctx["custom_receipt_subject"] = custom_receipt_subject
            tx_ctx.setdefault(
                "custom_receipt_text",
                f"Subscription confirmed. Receipt enclosed for {plan_name} via {platform_label}.",
            )
        await _send_payment_notification(
            user_id=user_id, email=email, user_name=name,
            plan_name=plan_name, amount=amount,
            payment_method=platform_label, ticket_id=ticket_id,
            billing_cycle=period, renewal_date=renewal_date,
            transaction_context=tx_ctx,
        )
        logger.info(f"IAP notification sent: user={user_id}, plan={plan_name}, platform={platform}")
    except Exception as e:
        logger.error(f"IAP notification error: {e}")


async def _send_iap_failure_notification(user_id: str, plan_name: str, amount: float, platform: str, reason: str):
    """Send email + in-app notification for IAP failure/expiration/refund."""
    try:
        normalized_reason = str(reason or "failed").strip().lower()
        if normalized_reason in {"expired", "canceled", "cancelled"}:
            await dispatch_subscription_expiry_notification(
                user_id,
                source_provider=f"{platform}_iap",
                reason="expired" if normalized_reason == "expired" else normalized_reason,
                plan_name_override=plan_name,
                transaction_filter={"user_id": user_id, "provider": f"iap_{platform}", "plan_id": plan_name.lower()},
            )
            if normalized_reason == "expired":
                return

        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user_doc or not user_doc.get("email"):
            return
        email = user_doc["email"]
        name = user_doc.get("name", "")
        platform_label = "App Store" if platform == "apple" else "Google Play"
        if normalized_reason in {"canceled", "cancelled"}:
            title = "Checkout cancelled"
            message = f"{platform_label} checkout was cancelled before payment completed. No charge was completed."
        elif normalized_reason in {"refunded", "revoked"}:
            title = "Payment refunded"
            message = f"Your {plan_name} payment via {platform_label} was refunded. Review your billing status in payment history."
        elif normalized_reason == "expired":
            title = "Checkout expired"
            message = f"{platform_label} checkout expired before payment completed. Please start again from your plan selection."
        else:
            title = "Payment not completed"
            message = f"{platform_label} could not complete your payment. No charge was completed. Try again or choose a different method."

        # In-app notification
        await db.notifications.insert_one({
            "id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "payment_failed",
            "title": title,
            "message": message,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"plan": plan_name, "platform": platform, "reason": reason},
        })

        # Send failure email
        from utils.email_service import send_catalog_template, is_email_configured
        if is_email_configured():
            base_url = os.environ.get("FRONTEND_BASE_URL", "") or os.environ.get("DASHBOARD_LINK_URL", "")
            await send_catalog_template(
                recipient_email=email,
                template_key="failed_payment",
                recipient_name=name,
                user_name=name,
                plan_name=plan_name,
                amount=f"${amount:.2f}",
                update_link=f"{base_url}/subscription/plans",
            )

        # Admin alert for failed IAP events (in-app + email)
        try:
            from routes.payments import _send_admin_payment_failure_alert

            await _send_admin_payment_failure_alert(
                customer_email=email,
                plan_name=plan_name,
                payment_method=f"iap_{platform}",
                reason=reason,
                amount=amount,
                amount_local=0,
                currency="USD",
                reference_id=f"iap-{platform}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            )
        except Exception as e:
            logger.warning(f"IAP admin failure alert error: {e}")

        logger.info(f"IAP failure notification sent: user={user_id}, plan={plan_name}, reason={reason}")
    except Exception as e:
        logger.error(f"IAP failure notification error: {e}")


async def _apply_iap_subscription(
    user_id: str,
    parsed: dict,
    platform: str,
    saved_card: Optional[dict] = None,
    notify_async: bool = True,
    custom_receipt_subject: Optional[str] = None,
    fallback_jurisdiction: Optional[dict] = None,
):
    """Update user subscription and store IAP transaction."""
    plan = parsed.get("plan", "free")
    is_active = parsed.get("active", False)
    suppress_notifications = _should_suppress_iap_notifications(parsed)
    previous_user = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "iap_platform": 1, "email": 1},
    ) or {}

    update = {
        "subscription_plan": plan if is_active else "free",
        "subscription_status": "active" if is_active else "expired",
        "subscription_end_date": parsed.get("expires_at"),  # Matches enforcement module field
        "payment_verified": is_active,  # Matches enforcement module check
        "iap_platform": platform,
        "iap_product_id": parsed.get("product_id"),
        "iap_expires_at": parsed.get("expires_at"),
        "iap_auto_renewing": parsed.get("auto_renewing", False),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.users.update_one({"user_id": user_id}, {"$set": update})

    period = parsed.get("period", "monthly")
    base_price = PLAN_PRICES.get(plan, {}).get(period, 0)
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "email": 1,
            "name": 1,
            "iap_commission_tier": 1,
            "iap_small_business_eligible": 1,
            "apple_iap_commission_rate": 1,
            "google_iap_commission_rate": 1,
            "billing_country_code": 1,
            "billing_country": 1,
            "billing_state_code": 1,
            "billing_state": 1,
            "billing_postal_code": 1,
            "country": 1,
            "country_code": 1,
            "state": 1,
            "state_code": 1,
            "postal_code": 1,
        },
    ) or {}
    fallback_jurisdiction = fallback_jurisdiction or {}
    jurisdiction_context = _resolve_iap_jurisdiction_context(
        request=None,
        user_doc=user_doc,
        country_code=parsed.get("country_code") or parsed.get("country") or fallback_jurisdiction.get("country"),
        state_code=parsed.get("state_code") or fallback_jurisdiction.get("state"),
        postal_code=parsed.get("postal_code") or fallback_jurisdiction.get("postal_code"),
    )
    country_code = str(jurisdiction_context.get("country") or "US").upper()
    state_code = str(jurisdiction_context.get("state") or "").upper()
    postal_code = str(jurisdiction_context.get("postal_code") or "")
    product_type = resolve_product_type(plan)
    provider_name = "iap_apple" if platform == "apple" else "iap_google"
    commission_policy = await _get_commission_policy()
    commission = _resolve_iap_commission_rate(platform, user_doc, parsed, policy=commission_policy)
    commission_rate = float(commission.get("rate", IAP_COMMISSION_STANDARD_RATE))
    parsed["user_email"] = user_doc.get("email", "")
    parsed["country_code"] = country_code
    parsed["state_code"] = state_code
    parsed["postal_code"] = postal_code

    tax_quote = await calculate_tax_quote(
        provider=provider_name,
        subtotal=float(base_price),
        currency="USD",
        country_code=country_code,
        state_code=state_code,
        postal_code=postal_code,
        product_type=product_type,
    )
    processing_fee = estimate_processing_fee(
        provider_name,
        tax_quote.get("amount_gross", base_price),
        "USD",
        context={"store_fee_rate": commission_rate},
    )
    financials = build_financial_totals(
        subtotal=tax_quote.get("subtotal", base_price),
        tax_amount=tax_quote.get("tax_amount", 0.0),
        processing_fee=processing_fee,
        fee_pass_through=True,
    )

    transaction_id = parsed.get("transaction_id") or parsed.get("order_id") or f"iap_{platform}_{uuid.uuid4().hex[:16]}"
    jurisdiction = tax_quote.get("jurisdiction", {"country": country_code, "state": state_code, "postal_code": postal_code})
    jurisdiction_source = jurisdiction_context.get("source", {})
    if parsed.get("city"):
        jurisdiction = {**jurisdiction, "city": parsed.get("city")}
    if parsed.get("address_line"):
        jurisdiction = {**jurisdiction, "address_line": parsed.get("address_line")}
    if not saved_card:
        saved_card = await _resolve_iap_saved_card(user_id, None)

    tx = {
        "user_id": user_id,
        "platform": platform,
        "product_id": parsed.get("product_id"),
        "plan": plan,
        "period": parsed.get("period"),
        "status": "active" if is_active else "expired",
        "auto_renewing": parsed.get("auto_renewing", False),
        "expires_at": parsed.get("expires_at"),
        "transaction_id": transaction_id,
        "original_transaction_id": parsed.get("original_transaction_id"),
        "provider": provider_name,
        "subtotal": financials["subtotal"],
        "tax_amount": financials["tax_amount"],
        "processing_fee": financials["processing_fee"],
        "platform_fee": financials["processing_fee"],
        "platform_fee_rate": commission_rate,
        "platform_fee_rate_pct": round(commission_rate * 100, 2),
        "commission_tier": commission.get("tier"),
        "commission_source": commission.get("source"),
        "amount_gross": financials["amount_gross"],
        "amount_net": financials["amount_net"],
        "total_amount": financials["total_amount"],
        "tax_rate": tax_quote.get("tax_rate", 0),
        "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "tax_breakdown": tax_quote.get("tax_breakdown", []),
        "jurisdiction": jurisdiction,
        "jurisdiction_source": jurisdiction_source,
        "product_type": tax_quote.get("product_type", product_type),
        "fee_pass_through": True,
        "environment": parsed.get("environment"),
        "saved_card_id": saved_card.get("card_id") if saved_card else None,
        "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
        "saved_card_type": saved_card.get("card_type") if saved_card else None,
        "raw_response": {k: v for k, v in parsed.items() if k not in ("valid",)},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.iap_transactions.update_one(
        {"transaction_id": transaction_id, "platform": platform},
        {"$set": tx},
        upsert=True,
    )
    await db.payment_transactions.update_one(
        {"transaction_id": transaction_id},
        {
            "$set": {
                "transaction_id": transaction_id,
                "session_id": transaction_id,
                "user_id": user_id,
                "plan_id": plan,
                "billing_period": period,
                "provider": provider_name,
                "gateway": provider_name,
                "payment_method": provider_name,
                "payment_id": transaction_id,
                "payment_status": "completed" if is_active else "expired",
                "status": "completed" if is_active else "expired",
                "currency": "USD",
                "amount": float(base_price),
                "amount_usd": float(base_price),
                "base_plan_price": float(base_price),
                "subtotal": financials["subtotal"],
                "tax_amount": financials["tax_amount"],
                "processing_fee": financials["processing_fee"],
                "platform_fee": financials["processing_fee"],
                "platform_fee_rate": commission_rate,
                "platform_fee_rate_pct": round(commission_rate * 100, 2),
                "commission_tier": commission.get("tier"),
                "commission_source": commission.get("source"),
                "amount_gross": financials["amount_gross"],
                "amount_net": financials["amount_net"],
                "total_amount": financials["total_amount"],
                "tax_rate": tax_quote.get("tax_rate", 0),
                "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
                "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
                "tax_breakdown": tax_quote.get("tax_breakdown", []),
                "jurisdiction": jurisdiction,
                "jurisdiction_source": jurisdiction_source,
                "product_type": tax_quote.get("product_type", product_type),
                "fee_pass_through": True,
                "platform": platform,
                "auto_renewing": parsed.get("auto_renewing", False),
                "expires_at": parsed.get("expires_at"),
                "environment": parsed.get("environment"),
                "notification_suppressed": bool(suppress_notifications and is_active),
                "notification_suppression_reason": (
                    "health_drill_synthetic_transaction" if suppress_notifications and is_active else None
                ),
                "notification_sent": bool(suppress_notifications and is_active),
                "notification_sent_at": (
                    datetime.now(timezone.utc).isoformat() if suppress_notifications and is_active else None
                ),
                "saved_card_id": saved_card.get("card_id") if saved_card else None,
                "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                "saved_card_type": saved_card.get("card_type") if saved_card else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "created_at": tx["created_at"],
            }
        },
        upsert=True,
    )

    if is_active:
        existing_payment = await db.payments.find_one({"payment_id": transaction_id}, {"_id": 0, "payment_id": 1})
        if not existing_payment:
            await db.payments.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "plan_id": plan,
                    "amount": financials["amount_gross"],
                    "currency": "USD",
                    "payment_method": provider_name,
                    "payment_id": transaction_id,
                    "status": "completed",
                    "subtotal": financials["subtotal"],
                    "tax_amount": financials["tax_amount"],
                    "processing_fee": financials["processing_fee"],
                    "platform_fee": financials["processing_fee"],
                    "platform_fee_rate": commission_rate,
                    "platform_fee_rate_pct": round(commission_rate * 100, 2),
                    "commission_tier": commission.get("tier"),
                    "commission_source": commission.get("source"),
                    "amount_gross": financials["amount_gross"],
                    "amount_net": financials["amount_net"],
                    "total_amount": financials["total_amount"],
                    "provider": provider_name,
                    "transaction_id": transaction_id,
                    "saved_card_id": saved_card.get("card_id") if saved_card else None,
                    "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                    "saved_card_type": saved_card.get("card_type") if saved_card else None,
                    "jurisdiction": jurisdiction,
                    "jurisdiction_source": jurisdiction_source,
                    "product_type": tax_quote.get("product_type", product_type),
                    "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
                    "tax_rate": tax_quote.get("tax_rate", 0),
                    "tax_breakdown": tax_quote.get("tax_breakdown", []),
                    "created_at": datetime.now(timezone.utc),
                    "fee_pass_through": True,
                }
            )

    await log_tax_calculation(
        db,
        transaction_id=transaction_id,
        provider=provider_name,
        user_id=user_id,
        payload={"phase": "iap_validation", "tax_quote": tax_quote, "financials": financials, "platform": platform},
    )
    await append_financial_ledger_entry(
        db,
        event_type="provider_validation",
        transaction_id=transaction_id,
        provider=provider_name,
        user_id=user_id,
        payload={"status": "completed" if is_active else "expired", "financials": financials, "platform": platform},
    )

    compliance_result = await _evaluate_iap_compliance(
        user_id=user_id,
        platform=platform,
        jurisdiction=jurisdiction,
        parsed=parsed,
        financials=financials,
        commission_rate=commission_rate,
    )
    fraud_result = await _run_iap_fraud_check(user_id=user_id, platform=platform, parsed=parsed)
    pricing_breakdown = _build_checkout_breakdown(financials, commission_rate)
    bundle_summary = await _archive_iap_compliance_bundle(
        transaction_id=transaction_id,
        user_id=user_id,
        user_email=user_doc.get("email", ""),
        plan=plan,
        period=period,
        platform=platform,
        pricing_breakdown=pricing_breakdown,
        tax_quote=tax_quote,
        parsed=parsed,
        compliance_result=compliance_result,
        fraud_result=fraud_result,
        jurisdiction=jurisdiction,
    )

    transition = _infer_transition_type(
        str(previous_user.get("subscription_plan", "free")),
        str(update.get("subscription_plan", "free")),
    )
    await _append_subscription_timeline_event(
        user_id=user_id,
        platform=platform,
        event_type=transition,
        from_plan=str(previous_user.get("subscription_plan", "free")),
        to_plan=str(update.get("subscription_plan", "free")),
        status=str(update.get("subscription_status", "active")),
        effective_at=parsed.get("expires_at") or datetime.now(timezone.utc).isoformat(),
        metadata={
            "transaction_id": transaction_id,
            "auto_renewing": parsed.get("auto_renewing", False),
            "source": "verify_or_webhook",
        },
    )

    await append_financial_ledger_entry(
        db,
        event_type="iap_commission_applied",
        transaction_id=transaction_id,
        provider=provider_name,
        user_id=user_id,
        payload={
            "commission_rate": commission_rate,
            "commission_tier": commission.get("tier"),
            "commission_source": commission.get("source"),
            "base_plan_price": financials.get("subtotal", 0),
            "platform_fee": financials.get("processing_fee", 0),
            "taxes": financials.get("tax_amount", 0),
            "final_total": financials.get("total_amount", 0),
            "compliance_status": compliance_result.get("status"),
            "fraud_risk": fraud_result.get("risk_level"),
        },
    )
    logger.info(f"IAP subscription applied: user={user_id}, plan={plan}, platform={platform}, active={is_active}")

    duplicate_notification_suppressed = False
    duplicate_notification_source_tx = ""

    if is_active and not suppress_notifications:
        recent_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        duplicate_recent_tx = await db.payment_transactions.find_one(
            {
                "user_id": user_id,
                "provider": provider_name,
                "plan_id": plan,
                "billing_period": period,
                "payment_status": "completed",
                "notification_sent": True,
                "created_at": {"$gte": recent_cutoff},
                "transaction_id": {"$ne": transaction_id},
            },
            {"_id": 0, "transaction_id": 1, "created_at": 1},
            sort=[("created_at", -1)],
        )
        if duplicate_recent_tx:
            duplicate_notification_suppressed = True
            duplicate_notification_source_tx = str(duplicate_recent_tx.get("transaction_id") or "")
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.payment_transactions.update_one(
                {"transaction_id": transaction_id},
                {
                    "$set": {
                        "notification_sent": True,
                        "notification_sent_at": now_iso,
                        "notification_suppressed": True,
                        "notification_suppression_reason": "iap_duplicate_recent_transaction",
                        "duplicate_of_transaction_id": duplicate_notification_source_tx,
                        "notification_dispatch_lock_until": 0,
                    }
                },
            )

    # Send payment notification email + in-app notification
    if is_active and not suppress_notifications and not duplicate_notification_suppressed:
        price = float(base_price)
        tx_context = {
            "transaction_id": transaction_id,
            "payment_id": transaction_id,
            "session_id": transaction_id,
            "plan_id": plan,
            "billing_period": period,
            "payment_method": provider_name,
            "provider": provider_name,
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "subtotal": financials.get("subtotal", 0),
            "base_plan_price": float(base_price),
            "tax_amount": financials.get("tax_amount", 0),
            "processing_fee": financials.get("processing_fee", 0),
            "amount_gross": financials.get("amount_gross", 0),
            "amount_net": financials.get("amount_net", 0),
            "total_amount": financials.get("total_amount", 0),
            "tax_rate": tax_quote.get("tax_rate", 0),
            "tax_breakdown": tax_quote.get("tax_breakdown", []),
            "jurisdiction": jurisdiction,
            "currency": "USD",
            "amount_local": financials.get("amount_gross", 0),
            "custom_receipt_subject": custom_receipt_subject,
            "custom_receipt_text": "Subscription confirmed — receipt enclosed with commission and tax breakdown.",
            "custom_admin_receipt_subject": "New Subscription Payment Received",
            "custom_notification_title": f"Payment Successful — {plan.title()} Plan Activated",
            "custom_confirmation_subject": custom_receipt_subject,
            "custom_confirmation_text": "Your subscription is active. Receipt enclosed with full IAP commission and tax breakdown.",
            "previous_subscription_plan": str(previous_user.get("subscription_plan", "free")),
            "previous_subscription_status": str(previous_user.get("subscription_status", "free")),
            "subscription_restored": str(previous_user.get("subscription_status", "")).lower() in {"expired", "cancelled"},
        }
        notify_coro = _send_iap_notification(
            user_id=user_id,
            plan_name=plan.title(),
            amount=price,
            platform=platform,
            period=parsed.get("period", "monthly"),
            expires_at=parsed.get("expires_at", ""),
            is_renewal=False,
            transaction_context=tx_context,
            custom_receipt_subject=custom_receipt_subject,
        )
        if notify_async:
            asyncio.create_task(notify_coro)
        else:
            await notify_coro

    return {
        **update,
        "notification_suppressed": bool((suppress_notifications and is_active) or duplicate_notification_suppressed),
        "notification_suppression_reason": (
            "iap_duplicate_recent_transaction"
            if duplicate_notification_suppressed
            else "health_drill_synthetic_transaction"
            if (suppress_notifications and is_active)
            else None
        ),
        "duplicate_of_transaction_id": duplicate_notification_source_tx,
        "commission_rate": commission_rate,
        "commission_tier": commission.get("tier"),
        "commission_source": commission.get("source"),
        "pricing_breakdown": pricing_breakdown,
        "compliance": compliance_result,
        "fraud": fraud_result,
        "compliance_bundle": bundle_summary,
    }


# ── API Endpoints ──

@router.get("/products")
async def get_iap_products(request: Request):
    """Return available IAP product IDs + pre-checkout fee estimates (Apple/Google)."""
    user = await get_current_user(request)
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "iap_commission_tier": 1,
            "iap_small_business_eligible": 1,
            "apple_iap_commission_rate": 1,
            "google_iap_commission_rate": 1,
            "billing_country_code": 1,
            "billing_country": 1,
            "billing_state_code": 1,
            "billing_state": 1,
            "billing_postal_code": 1,
            "country": 1,
            "country_code": 1,
            "state": 1,
            "state_code": 1,
            "postal_code": 1,
        },
    ) if user else {}
    jurisdiction_context = _resolve_iap_jurisdiction_context(
        request=request,
        user_doc=user_doc or {},
        country_code=request.query_params.get("country_code"),
        state_code=request.query_params.get("state_code"),
        postal_code=request.query_params.get("postal_code"),
    )
    country_code = str(jurisdiction_context.get("country") or "US").upper()
    state_code = str(jurisdiction_context.get("state") or "").upper()
    postal_code = str(jurisdiction_context.get("postal_code") or "")
    commission_policy = await _get_commission_policy()

    async def _estimate_for_provider(provider_name: str, platform_key: str, base_price: float, product_type: str) -> dict:
        commission = _resolve_iap_commission_rate(platform_key, user_doc or {}, {"country_code": country_code, "state_code": state_code}, policy=commission_policy)
        commission_rate = float(commission.get("rate", IAP_COMMISSION_STANDARD_RATE))
        tax_quote = await calculate_tax_quote(
            provider=provider_name,
            subtotal=float(base_price),
            currency="USD",
            country_code=country_code,
            state_code=state_code,
            postal_code=postal_code,
            product_type=product_type,
        )
        processing_fee = estimate_processing_fee(
            provider_name,
            tax_quote.get("amount_gross", base_price),
            "USD",
            context={"store_fee_rate": commission_rate},
        )
        financials = build_financial_totals(
            subtotal=tax_quote.get("subtotal", base_price),
            tax_amount=tax_quote.get("tax_amount", 0.0),
            processing_fee=processing_fee,
            fee_pass_through=True,
        )
        breakdown = _build_checkout_breakdown(financials, commission_rate)
        return {
            "subtotal": round(float(financials.get("subtotal", 0)), 2),
            "tax_fee": round(float(financials.get("tax_amount", 0)), 2),
            "processing_fee": round(float(financials.get("processing_fee", 0)), 2),
            "total_amount": round(float(financials.get("total_amount", 0)), 2),
            "base_plan_price": breakdown["base_plan_price"],
            "platform_fee": breakdown["platform_fee"],
            "platform_fee_rate_pct": breakdown["platform_fee_rate_pct"],
            "final_total": breakdown["final_total"],
            "tax_rate_pct": round(float(tax_quote.get("tax_rate", 0)) * 100, 2),
            "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
            "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
            "tax_breakdown": tax_quote.get("tax_breakdown", []),
            "jurisdiction": tax_quote.get("jurisdiction", {"country": country_code, "state": state_code, "postal_code": postal_code}),
            "jurisdiction_context": jurisdiction_context,
            "commission_tier": commission.get("tier"),
            "commission_source": commission.get("source"),
            "fee_visibility_note": "Base Plan Price + Platform Fee (IAP Commission) + Applicable Jurisdiction Taxes = Final Total.",
            "tax_disclosure": "Taxes are auto-calculated from your billing jurisdiction (country/state/postal where available) before final payment.",
            "requires_explicit_confirmation": True,
        }

    products = []
    for product_id, mapping in PRODUCT_MAP.items():
        plan = mapping["plan"]
        period = mapping["period"]
        price = PLAN_PRICES.get(plan, {}).get(period, 0)
        product_type = resolve_product_type(plan)
        apple_estimate = await _estimate_for_provider("iap_apple", "apple", float(price), product_type)
        google_estimate = await _estimate_for_provider("iap_google", "google", float(price), product_type)
        products.append({
            "product_id": product_id,
            "plan": plan,
            "period": period,
            "price": price,
            "currency": "USD",
            "display_name": f"{plan.title()} ({period.title()})",
            "checkout_estimates": {
                "apple": apple_estimate,
                "google": google_estimate,
            },
        })
    return {
        "products": products,
        "jurisdiction_context": jurisdiction_context,
        "tax_transparency_note": "Applicable taxes are estimated and shown before final payment using your jurisdiction.",
    }


@router.post("/checkout-preview")
async def get_iap_checkout_preview(body: IAPCheckoutPreviewRequest, request: Request):
    user = await get_current_user(request)
    platform = str(body.platform or "").strip().lower()
    if platform not in {"apple", "google"}:
        raise HTTPException(status_code=400, detail="platform must be apple or google")

    mapping = PRODUCT_MAP.get(body.product_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Unknown product_id")

    plan = mapping["plan"]
    period = mapping["period"]
    base_price = float(PLAN_PRICES.get(plan, {}).get(period, 0))
    provider_name = "iap_apple" if platform == "apple" else "iap_google"

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "iap_commission_tier": 1,
            "iap_small_business_eligible": 1,
            "apple_iap_commission_rate": 1,
            "google_iap_commission_rate": 1,
            "billing_country_code": 1,
            "billing_country": 1,
            "billing_state_code": 1,
            "billing_state": 1,
            "billing_postal_code": 1,
            "country": 1,
            "country_code": 1,
            "state": 1,
            "state_code": 1,
            "postal_code": 1,
        },
    ) if user else {}
    jurisdiction_context = _resolve_iap_jurisdiction_context(
        request=request,
        user_doc=user_doc or {},
        country_code=body.country_code,
        state_code=body.state_code,
        postal_code=body.postal_code,
    )
    commission_policy = await _get_commission_policy()
    commission = _resolve_iap_commission_rate(platform, user_doc or {}, body.model_dump(), policy=commission_policy)
    commission_rate = float(commission.get("rate", IAP_COMMISSION_STANDARD_RATE))

    tax_quote = await calculate_tax_quote(
        provider=provider_name,
        subtotal=base_price,
        currency="USD",
        country_code=str(jurisdiction_context.get("country") or "US").upper(),
        state_code=str(jurisdiction_context.get("state") or "").upper(),
        postal_code=str(jurisdiction_context.get("postal_code") or ""),
        product_type=resolve_product_type(plan),
    )
    processing_fee = estimate_processing_fee(
        provider_name,
        tax_quote.get("amount_gross", base_price),
        "USD",
        context={"store_fee_rate": commission_rate},
    )
    financials = build_financial_totals(
        subtotal=tax_quote.get("subtotal", base_price),
        tax_amount=tax_quote.get("tax_amount", 0.0),
        processing_fee=processing_fee,
        fee_pass_through=True,
    )

    return {
        "product_id": body.product_id,
        "plan": plan,
        "period": period,
        "platform": platform,
        "pricing_breakdown": _build_checkout_breakdown(financials, commission_rate),
        "tax_rate_pct": round(float(tax_quote.get("tax_rate", 0)) * 100, 2),
        "tax_breakdown": tax_quote.get("tax_breakdown", []),
        "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "jurisdiction": tax_quote.get("jurisdiction", {}),
        "jurisdiction_context": jurisdiction_context,
        "commission": {
            "rate": commission_rate,
            "rate_pct": round(commission_rate * 100, 2),
            "tier": commission.get("tier"),
            "source": commission.get("source"),
        },
        "requires_explicit_confirmation": True,
        "tax_disclosure": "Taxes are automatically calculated from your jurisdiction and shown before final payment.",
        "confirmation_copy": "I confirm the Base Plan Price, Platform Fee (IAP Commission), Taxes, and Final Total before purchase.",
    }


@router.get("/manage-links")
async def get_iap_manage_links(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "apple": "https://apps.apple.com/account/subscriptions",
        "google": "https://play.google.com/store/account/subscriptions",
        "note": "Upgrade, downgrade, and cancellation actions must be completed in the originating app store.",
    }


@router.post("/admin/simulate-production-e2e")
async def simulate_iap_production_e2e(body: IAPSimulationRequest, request: Request):
    admin = await get_current_user(request)
    if not admin or not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    plan = str(body.plan or "basic").lower()
    period = str(body.period or "monthly").lower()
    platform = str(body.platform or "google").lower()
    if plan not in PLAN_PRICES or period not in PLAN_PRICES.get(plan, {}):
        raise HTTPException(status_code=400, detail="Invalid plan or period")
    if platform not in {"apple", "google"}:
        raise HTTPException(status_code=400, detail="platform must be apple or google")

    product_id = next(
        (pid for pid, mapping in PRODUCT_MAP.items() if mapping.get("plan") == plan and mapping.get("period") == period),
        None,
    )
    if not product_id:
        raise HTTPException(status_code=404, detail="No product mapping found for requested plan/period")

    address_line = (body.address_line or "").strip() or None
    user_doc = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user_doc:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": body.email,
            "name": (body.name or "").strip() or "IAP Simulation User",
            "subscription_plan": "free",
            "subscription_status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "password_hash": "SIMULATED_EXTERNAL_IDENTITY",
        }
        if address_line:
            user_doc["billing_address_line"] = address_line
        await db.users.insert_one({**user_doc})
    else:
        user_id = user_doc["user_id"]
        profile_updates = {}
        if body.name and body.name.strip():
            profile_updates["name"] = body.name.strip()
        if address_line:
            profile_updates["billing_address_line"] = address_line
        if profile_updates:
            profile_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.users.update_one({"user_id": user_id}, {"$set": profile_updates})

    now = datetime.now(timezone.utc)
    tx_id = f"sim_{platform}_{uuid.uuid4().hex[:14]}"
    parsed_success = {
        "valid": True,
        "active": True,
        "plan": plan,
        "period": period,
        "product_id": product_id,
        "transaction_id": tx_id,
        "original_transaction_id": f"orig_{tx_id}",
        "purchase_token": f"token_{uuid.uuid4().hex[:20]}" if platform == "google" else "",
        "auto_renewing": True,
        "expires_at": (now + timedelta(days=30 if period == "monthly" else 365)).isoformat(),
        "country_code": body.country_code,
        "state_code": body.state_code,
        "postal_code": body.postal_code,
        "city": body.city,
        "address_line": address_line,
        "environment": "production_simulated",
    }

    previous_notification = await db.notifications.find_one(
        {"user_id": user_id, "type": "payment_confirmation"},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    ) or {}
    previous_created_at = str(previous_notification.get("created_at") or "")

    simulation_start = time.time()
    update = await _apply_iap_subscription(
        user_id=user_id,
        parsed=parsed_success,
        platform=platform,
        saved_card=None,
        notify_async=True,
        custom_receipt_subject="Subscription Confirmed — Receipt Enclosed",
    )
    latest_notification = {}
    notification_latency_ms = None
    for _ in range(25):
        latest_notification = await db.notifications.find_one(
            {
                "user_id": user_id,
                "type": "payment_confirmation",
                "metadata.ticket_id": {"$regex": "^IAP-"},
            },
            {"_id": 0},
            sort=[("created_at", -1)],
        ) or {}
        if latest_notification and str(latest_notification.get("created_at") or "") != previous_created_at:
            notification_latency_ms = int((time.time() - simulation_start) * 1000)
            break
        await asyncio.sleep(0.1)

    simulation_latency_ms = int((time.time() - simulation_start) * 1000)
    latest_tx = await db.payment_transactions.find_one(
        {"transaction_id": tx_id},
        {"_id": 0},
    ) or {}

    failure_case = None
    if body.simulate_failure_case:
        await _send_iap_failure_notification(
            user_id=user_id,
            plan_name=plan.title(),
            amount=float(PLAN_PRICES.get(plan, {}).get(period, 0)),
            platform=platform,
            reason="failed",
        )
        failure_case = {
            "simulated": True,
            "status": "processed",
            "reason": "failed",
        }

    pricing_breakdown = update.get("pricing_breakdown", {})
    checks = {
        "fee_accuracy": round(float(pricing_breakdown.get("base_plan_price", 0)) + float(pricing_breakdown.get("platform_fee", 0)) + float(pricing_breakdown.get("taxes", 0)), 2) == round(float(pricing_breakdown.get("final_total", 0)), 2),
        "notification_latency_under_2s": bool(notification_latency_ms is not None and notification_latency_ms <= 2000),
        "subscription_active": update.get("subscription_status") == "active",
        "api_integrity": bool(latest_tx.get("transaction_id")),
    }

    return {
        "success": True,
        "scenario": {
            "location": body.city,
            "state_code": body.state_code,
            "country_code": body.country_code,
            "email": body.email,
            "plan": plan,
            "period": period,
            "platform": platform,
            "transaction_id": tx_id,
        },
        "pricing_breakdown": pricing_breakdown,
        "subscription_update": update,
        "latest_payment_transaction": latest_tx,
        "latest_notification": {
            "title": latest_notification.get("title"),
            "message": latest_notification.get("message"),
            "created_at": latest_notification.get("created_at"),
        },
        "checks": checks,
        "notification_latency_ms": notification_latency_ms if notification_latency_ms is not None else simulation_latency_ms,
        "simulation_runtime_ms": simulation_latency_ms,
        "failure_case": failure_case,
    }


@router.get("/status")
async def get_iap_status(request: Request):
    """Get current IAP subscription status for the authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    jurisdiction_context = _resolve_iap_jurisdiction_context(request=request, user_doc=user_doc)

    latest_tx = await db.iap_transactions.find_one(
        {"user_id": user.user_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )

    return {
        "plan": user_doc.get("subscription_plan", "free"),
        "status": user_doc.get("subscription_status", "active"),
        "platform": user_doc.get("iap_platform"),
        "product_id": user_doc.get("iap_product_id"),
        "expires_at": user_doc.get("iap_expires_at"),
        "auto_renewing": user_doc.get("iap_auto_renewing", False),
        "latest_transaction": {
            "transaction_id": latest_tx.get("transaction_id"),
            "platform": latest_tx.get("platform"),
            "created_at": latest_tx.get("created_at"),
        } if latest_tx else None,
        "jurisdiction_context": jurisdiction_context,
    }


@router.get("/readiness")
async def get_iap_readiness(request: Request):
    """Return Apple/Google IAP readiness matrix with explicit Live/Test/Sandbox status."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    hydrate_iap_runtime_secrets(force=True)
    readiness = _resolve_iap_provider_readiness()
    await _record_iap_readiness_audit(readiness)
    return JSONResponse(
        content=readiness,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/admin/secret-diagnostics")
async def get_iap_secret_diagnostics_admin(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    hydrate_iap_runtime_secrets(force=True)
    diagnostics = get_iap_secret_diagnostics()
    return diagnostics


@router.get("/readiness-matrix")
async def get_iap_readiness_matrix(request: Request):
    """Alias endpoint for readiness matrix compatibility with admin audit checks."""
    return await get_iap_readiness(request)


@router.get("/history")
async def get_iap_history(request: Request, limit: int = 50):
    """Get IAP transaction history for the authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    transactions = await db.iap_transactions.find(
        {"user_id": user.user_id},
        {"_id": 0, "raw_response": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    return {"transactions": transactions}


@router.get("/timeline")
async def get_iap_timeline(request: Request, limit: int = 100):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    events = await db.iap_subscription_timeline.find(
        {"user_id": user.user_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"events": events}


@router.post("/apple/verify")
async def verify_apple_receipt(body: AppleReceiptRequest, request: Request):
    """Validate an Apple App Store transaction and update subscription."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    parsed = await _get_apple_subscription_status(body.transaction_id)

    if not parsed.get("valid"):
        parsed = await _verify_apple_transaction(body.transaction_id)

    if not parsed.get("valid"):
        raise HTTPException(status_code=400, detail=parsed.get("error", "Invalid receipt"))

    saved_card = await _resolve_iap_saved_card(user.user_id, body.saved_card_id)
    fallback_jurisdiction = _resolve_iap_jurisdiction_context(request=request, user_doc=None)
    update = await _apply_iap_subscription(
        user.user_id,
        parsed,
        "apple",
        saved_card=saved_card,
        fallback_jurisdiction=fallback_jurisdiction,
    )

    return {
        "success": True,
        "plan": parsed["plan"],
        "active": parsed["active"],
        "expires_at": parsed["expires_at"],
        "auto_renewing": parsed.get("auto_renewing", False),
        "subscription_update": update,
    }


@router.post("/google/verify")
async def verify_google_receipt(body: GoogleReceiptRequest, request: Request):
    """Validate a Google Play purchase token and update subscription."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await _verify_google_receipt(body.product_id, body.purchase_token)
    parsed = _parse_google_receipt(result, body.product_id)
    parsed["purchase_token"] = body.purchase_token  # Store for webhook lookup

    if not parsed.get("valid"):
        raise HTTPException(status_code=400, detail=parsed.get("error", "Invalid purchase"))

    saved_card = await _resolve_iap_saved_card(user.user_id, body.saved_card_id)
    fallback_jurisdiction = _resolve_iap_jurisdiction_context(request=request, user_doc=None)
    update = await _apply_iap_subscription(
        user.user_id,
        parsed,
        "google",
        saved_card=saved_card,
        fallback_jurisdiction=fallback_jurisdiction,
    )

    return {
        "success": True,
        "plan": parsed["plan"],
        "active": parsed["active"],
        "expires_at": parsed["expires_at"],
        "auto_renewing": parsed.get("auto_renewing", False),
        "subscription_update": update,
    }


# ── Webhook Endpoints (Server-to-Server Notifications) ──

@router.post("/apple/webhook")
async def apple_s2s_notification(request: Request):
    """Handle Apple App Store Server Notifications V2 (signed JWS payloads)."""
    started_at = time.time()
    body = {}
    notification_type = "unknown"
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}

        signed_payload = body.get("signedPayload", "")
        notification = _decode_jws_payload(signed_payload) if signed_payload else body

        notification_type = notification.get("notificationType", "")
        subtype = notification.get("subtype", "")

        logger.info(f"Apple S2S v2: type={notification_type}, subtype={subtype}")

        await db.iap_webhooks.insert_one({
            "platform": "apple",
            "notification_type": notification_type,
            "subtype": subtype,
            "processed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        tx_info = {}
        signed_tx = notification.get("data", {}).get("signedTransactionInfo", "")
        signed_renewal = notification.get("data", {}).get("signedRenewalInfo", "")
        if signed_tx:
            tx_info = _decode_jws_payload(signed_tx)
        renewal_info = _decode_jws_payload(signed_renewal) if signed_renewal else {}

        original_tx_id = tx_info.get("originalTransactionId", "")

        if notification_type in ("DID_RENEW", "SUBSCRIBED", "DID_CHANGE_RENEWAL_PREF", "OFFER_REDEEMED"):
            if original_tx_id:
                parsed = _parse_apple_transaction(tx_info)
                parsed["auto_renewing"] = renewal_info.get("autoRenewStatus", 0) == 1
                existing_tx = await db.iap_transactions.find_one(
                    {"original_transaction_id": original_tx_id, "platform": "apple"},
                    {"_id": 0},
                )
                if existing_tx:
                    await _apply_iap_subscription(existing_tx["user_id"], parsed, "apple")
                    await db.iap_webhooks.update_one(
                        {"platform": "apple", "notification_type": notification_type},
                        {"$set": {"processed": True}},
                    )

        elif notification_type in ("EXPIRED", "REFUND", "REVOKE", "DID_FAIL_TO_RENEW"):
            if original_tx_id:
                existing_tx = await db.iap_transactions.find_one(
                    {"original_transaction_id": original_tx_id, "platform": "apple"},
                    {"_id": 0},
                )
                if existing_tx:
                    user_id = existing_tx["user_id"]
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$set": {
                            "subscription_plan": "free",
                            "subscription_status": "expired",
                            "payment_verified": False,
                            "iap_auto_renewing": False,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }},
                    )
                    await _append_subscription_timeline_event(
                        user_id=user_id,
                        platform="apple",
                        event_type="cancellation",
                        from_plan=existing_tx.get("plan", "free"),
                        to_plan="free",
                        status="expired",
                        effective_at=datetime.now(timezone.utc).isoformat(),
                        metadata={"reason": notification_type},
                    )
                    await db.iap_webhooks.update_one(
                        {"platform": "apple", "notification_type": notification_type},
                        {"$set": {"processed": True}},
                    )

                    plan = existing_tx.get("plan", "free")
                    period = existing_tx.get("period", "monthly")
                    price = PLAN_PRICES.get(plan, {}).get(period, 0)
                    reason_map = {"EXPIRED": "expired", "REFUND": "refunded", "REVOKE": "revoked", "DID_FAIL_TO_RENEW": "failed to renew"}
                    asyncio.create_task(_send_iap_failure_notification(
                        user_id=user_id, plan_name=plan.title(),
                        amount=price, platform="apple",
                        reason=reason_map.get(notification_type, "expired"),
                    ))

        await _log_webhook_delivery(
            platform="apple",
            notification_type=str(notification_type),
            started_at=started_at,
            status="success",
            source="live",
        )
        return {"status": "ok"}
    except Exception as exc:
        await _enqueue_webhook_retry("apple", body or {}, str(exc)[:160])
        await _log_webhook_delivery(
            platform="apple",
            notification_type=str(notification_type),
            started_at=started_at,
            status="error",
            source="live",
            error=str(exc)[:200],
        )
        logger.exception("Apple webhook processing failed")
        return {"status": "error", "queued_for_retry": True}


@router.post("/google/webhook")
async def google_rtdn_notification(request: Request):
    """Handle Google Play Real-Time Developer Notifications (RTDN)."""
    started_at = time.time()
    body = {}
    notification_type = 0
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}

        message = body.get("message", {})
        encoded_data = message.get("data", "")

        notification_data = {}
        if encoded_data:
            try:
                decoded = base64.b64decode(encoded_data).decode("utf-8")
                notification_data = json.loads(decoded)
            except Exception as e:
                logger.error(f"Failed to decode Google RTDN: {e}")

        sub_notification = notification_data.get("subscriptionNotification", {})
        notification_type = sub_notification.get("notificationType", 0)
        purchase_token = sub_notification.get("purchaseToken", "")
        subscription_id = sub_notification.get("subscriptionId", "")

        logger.info(f"Google RTDN: type={notification_type}, sub_id={subscription_id}")

        await db.iap_webhooks.insert_one({
            "platform": "google",
            "notification_type": notification_type,
            "subscription_id": subscription_id,
            "processed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        if notification_type in (1, 2, 4, 7) and purchase_token and subscription_id:
            result = await _verify_google_receipt(subscription_id, purchase_token)
            parsed = _parse_google_receipt(result, subscription_id)
            if parsed.get("valid"):
                tx = await db.iap_transactions.find_one(
                    {"platform": "google", "product_id": subscription_id},
                    {"_id": 0},
                    sort=[("created_at", -1)],
                )
                if tx:
                    await _apply_iap_subscription(tx["user_id"], parsed, "google")

        elif notification_type in (3, 12, 13) and purchase_token:
            tx = await db.iap_transactions.find_one(
                {"platform": "google", "product_id": subscription_id},
                {"_id": 0},
                sort=[("created_at", -1)],
            )
            if not tx and purchase_token:
                tx = await db.iap_transactions.find_one(
                    {"platform": "google", "raw_response.purchase_token": purchase_token},
                    {"_id": 0},
                )
            if tx:
                user_id = tx["user_id"]
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "subscription_plan": "free",
                        "subscription_status": "expired",
                        "payment_verified": False,
                        "iap_auto_renewing": False,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                await _append_subscription_timeline_event(
                    user_id=user_id,
                    platform="google",
                    event_type="cancellation",
                    from_plan=tx.get("plan", "free"),
                    to_plan="free",
                    status="expired",
                    effective_at=datetime.now(timezone.utc).isoformat(),
                    metadata={"reason": notification_type},
                )

                plan = tx.get("plan", "free")
                period = tx.get("period", "monthly")
                price = PLAN_PRICES.get(plan, {}).get(period, 0)
                reason_map = {3: "canceled", 12: "revoked", 13: "expired"}
                asyncio.create_task(_send_iap_failure_notification(
                    user_id=user_id, plan_name=plan.title(),
                    amount=price, platform="google",
                    reason=reason_map.get(notification_type, "expired"),
                ))

        await _log_webhook_delivery(
            platform="google",
            notification_type=str(notification_type),
            started_at=started_at,
            status="success",
            source="live",
        )
        return {"status": "ok"}
    except Exception as exc:
        await _enqueue_webhook_retry("google", body or {}, str(exc)[:160])
        await _log_webhook_delivery(
            platform="google",
            notification_type=str(notification_type),
            started_at=started_at,
            status="error",
            source="live",
            error=str(exc)[:200],
        )
        logger.exception("Google webhook processing failed")
        return {"status": "error", "queued_for_retry": True}


# ── Admin Endpoints ──

@router.get("/admin/stats")
async def get_iap_admin_stats(request: Request):
    """Admin dashboard: IAP subscription statistics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    pipeline = [
        {"$match": {"iap_platform": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": {"platform": "$iap_platform", "plan": "$subscription_plan"}, "count": {"$sum": 1}}},
    ]
    platform_stats = await db.users.aggregate(pipeline).to_list(100)

    total_transactions = await db.iap_transactions.count_documents({})
    active_apple = await db.users.count_documents({"iap_platform": "apple", "subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    active_google = await db.users.count_documents({"iap_platform": "google", "subscription_status": "active", "subscription_plan": {"$ne": "free"}})

    recent_txs = await db.iap_transactions.find(
        {}, {"_id": 0, "raw_response": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    recent_hooks = await db.iap_webhooks.find(
        {}, {"_id": 0, "payload": 0, "decoded_data": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    revenue_pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {
            "_id": {"plan": "$plan", "period": "$period"},
            "count": {"$sum": 1},
        }},
    ]
    revenue_groups = await db.iap_transactions.aggregate(revenue_pipeline).to_list(100)

    estimated_mrr = 0
    for g in revenue_groups:
        plan = g["_id"].get("plan", "free")
        period = g["_id"].get("period", "monthly")
        price = PLAN_PRICES.get(plan, {}).get(period, 0)
        monthly_price = price if period == "monthly" else price / 12
        estimated_mrr += monthly_price * g["count"]

    slo_snapshot = await _compute_iap_slo_snapshot(24)

    return {
        "active_apple_subscribers": active_apple,
        "active_google_subscribers": active_google,
        "total_transactions": total_transactions,
        "estimated_mrr": round(estimated_mrr, 2),
        "platform_breakdown": [
            {"platform": s["_id"]["platform"], "plan": s["_id"]["plan"], "count": s["count"]}
            for s in platform_stats
        ],
        "recent_transactions": recent_txs,
        "recent_webhooks": recent_hooks,
        "slo_snapshot": slo_snapshot,
    }


@router.get("/admin/config")
async def get_iap_config(request: Request):
    """Admin endpoint: Check IAP configuration status."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    apple_key_path = os.environ.get("APPLE_IAP_PRIVATE_KEY_PATH", "")
    google_key_path = os.environ.get("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH", "") or os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "")

    commission_policy = await _get_commission_policy()
    readiness = _resolve_iap_provider_readiness()

    return {
        "apple": {
            "configured": bool(apple_key_path and os.path.exists(apple_key_path)),
            "key_id": os.environ.get("APPLE_IAP_KEY_ID", "")[:6] + "..." if os.environ.get("APPLE_IAP_KEY_ID") else None,
            "issuer_id": os.environ.get("APPLE_IAP_ISSUER_ID", "")[:8] + "..." if os.environ.get("APPLE_IAP_ISSUER_ID") else None,
            "bundle_id": os.environ.get("APPLE_BUNDLE_ID", ""),
        },
        "google": {
            "configured": bool(google_key_path and os.path.exists(google_key_path)),
            "package_name": os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", ""),
            "service_account": "configured" if google_key_path and os.path.exists(google_key_path) else "missing",
        },
        "products": list(PRODUCT_MAP.keys()),
        "webhook_urls": {
            "apple": "/api/iap/apple/webhook",
            "google": "/api/iap/google/webhook",
        },
        "commission_policy": commission_policy,
        "readiness": readiness,
    }


@router.get("/admin/commission-policy")
async def get_iap_commission_policy(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _get_commission_policy()


@router.put("/admin/commission-policy")
async def update_iap_commission_policy(body: IAPCommissionPolicyUpdate, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    payload = body.model_dump()
    return await _save_commission_policy(payload)


@router.get("/admin/slo")
async def get_iap_slo_dashboard(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    snapshot = await _compute_iap_slo_snapshot(24)
    latest_drill = await db.iap_health_drill_reports.find_one({}, {"_id": 0}, sort=[("completed_at", -1)]) or {}
    return {
        "slo": snapshot,
        "latest_health_drill": latest_drill,
    }


@router.post("/admin/retry-webhooks")
async def retry_iap_webhooks(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await run_iap_webhook_retry_cycle(25)


@router.post("/admin/run-live-sandbox-validation")
async def run_live_sandbox_validation(body: IAPSandboxValidationRequest, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    started = datetime.now(timezone.utc)
    apple_tx = body.apple_transaction_id or os.environ.get("APPLE_SANDBOX_TEST_TRANSACTION_ID")
    google_product = body.google_product_id or os.environ.get("GOOGLE_SANDBOX_TEST_PRODUCT_ID")
    google_token = body.google_purchase_token or os.environ.get("GOOGLE_SANDBOX_TEST_PURCHASE_TOKEN")

    apple_result = {"executed": False, "valid": False, "detail": "missing transaction id"}
    google_result = {"executed": False, "valid": False, "detail": "missing product/token"}

    if apple_tx:
        parsed = await _verify_apple_transaction(apple_tx)
        apple_result = {
            "executed": True,
            "valid": bool(parsed.get("valid")),
            "detail": parsed.get("error") or "ok",
            "transaction_id": parsed.get("transaction_id") or apple_tx,
            "active": parsed.get("active"),
        }

    if google_product and google_token:
        parsed = await _verify_google_receipt(google_product, google_token)
        google_result = {
            "executed": True,
            "valid": bool(parsed.get("valid")),
            "detail": parsed.get("error") or "ok",
            "expiry_time": parsed.get("expiryTimeMillis"),
        }

    callback_probe = {"apple": {"status": "not_run"}, "google": {"status": "not_run"}}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            apple_probe = await client.post(
                "http://127.0.0.1:8001/api/iap/apple/webhook",
                json={"notificationType": "DID_RENEW", "subtype": "INITIAL_BUY", "data": {}},
            )
            google_probe_payload = {
                "message": {
                    "data": base64.b64encode(
                        json.dumps(
                            {
                                "subscriptionNotification": {
                                    "notificationType": 2,
                                    "purchaseToken": google_token or "sandbox_probe_token",
                                    "subscriptionId": google_product or "com.realaicoach.basic.monthly",
                                }
                            }
                        ).encode("utf-8")
                    ).decode("utf-8")
                }
            }
            google_probe = await client.post(
                "http://127.0.0.1:8001/api/iap/google/webhook",
                json=google_probe_payload,
            )
            callback_probe = {
                "apple": {"status": apple_probe.status_code, "ok": apple_probe.status_code == 200},
                "google": {"status": google_probe.status_code, "ok": google_probe.status_code == 200},
            }
    except Exception as exc:
        callback_probe = {
            "apple": {"status": "error", "detail": str(exc)[:120]},
            "google": {"status": "error", "detail": str(exc)[:120]},
        }

    delivery_logs = await db.iap_webhook_delivery_logs.find(
        {"created_at": {"$gte": started.isoformat()}},
        {"_id": 0},
    ).to_list(50)

    run_doc = {
        "run_id": f"iapsbx_{uuid.uuid4().hex[:12]}",
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "apple": apple_result,
        "google": google_result,
        "callback_probe": callback_probe,
        "delivery_logs": delivery_logs,
        "credentials_detected": {
            "apple_key_path": bool(os.environ.get("APPLE_IAP_PRIVATE_KEY_PATH")),
            "google_service_account": bool(os.environ.get("GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH") or os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")),
        },
    }
    await db.iap_sandbox_validation_runs.insert_one({**run_doc})
    return run_doc


@router.get("/admin/compliance-bundles")
async def list_iap_compliance_bundles(request: Request, limit: int = 50):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = await db.iap_compliance_bundles.find(
        {},
        {"_id": 0, "receipt_pdf_b64": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"bundles": rows}


@router.get("/admin/compliance-bundles/{transaction_id}")
async def get_iap_compliance_bundle_detail(transaction_id: str, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    bundle = await db.iap_compliance_bundles.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0, "receipt_pdf_b64": 0},
    )
    if not bundle:
        raise HTTPException(status_code=404, detail="Compliance bundle not found")
    return bundle


@router.get("/admin/compliance-bundles/{transaction_id}/receipt.pdf")
async def download_iap_compliance_bundle_pdf(transaction_id: str, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    bundle = await db.iap_compliance_bundles.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0, "receipt_pdf_b64": 1, "receipt_number": 1},
    )
    if not bundle:
        raise HTTPException(status_code=404, detail="Compliance bundle not found")
    pdf_b64 = bundle.get("receipt_pdf_b64")
    if not pdf_b64:
        raise HTTPException(status_code=404, detail="Receipt PDF not archived")
    pdf_bytes = base64.b64decode(pdf_b64)
    filename = build_pdf_v15_filename("receipt", bundle.get("receipt_number", transaction_id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/run-health-drill")
async def run_iap_health_drill_now(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await run_iap_nightly_health_drill()


async def scheduled_iap_webhook_retry_cycle() -> None:
    try:
        result = await run_iap_webhook_retry_cycle(25)
        logger.info(f"IAP webhook retry cycle complete: {result}")
    except Exception as exc:
        logger.error(f"IAP webhook retry cycle failed: {exc}")


async def scheduled_iap_nightly_health_drill() -> None:
    try:
        report = await run_iap_nightly_health_drill()
        logger.info(f"IAP nightly health drill complete: {report.get('report_id')}")
    except Exception as exc:
        logger.error(f"IAP nightly health drill failed: {exc}")


async def scheduled_iap_tax_freshness_guard() -> None:
    """Continuously validates IAP tax transparency across key jurisdictions."""
    started_at = datetime.now(timezone.utc)
    try:
        scenarios = [
            {"country": "US", "state": "CA", "postal_code": "94016"},
            {"country": "CA", "state": "ON", "postal_code": "M5V"},
            {"country": "FR", "state": "", "postal_code": "75001"},
        ]
        probes = []
        issues: list[str] = []

        for provider in ("iap_apple", "iap_google"):
            for scenario in scenarios:
                quote = await calculate_tax_quote(
                    provider=provider,
                    subtotal=float(PLAN_PRICES["basic"]["monthly"]),
                    currency="USD",
                    country_code=scenario["country"],
                    state_code=scenario["state"],
                    postal_code=scenario["postal_code"],
                    product_type=resolve_product_type("basic"),
                )
                rate_pct = round(float(quote.get("tax_rate", 0)) * 100, 2)
                amount = round(float(quote.get("tax_amount", 0)), 2)
                probes.append(
                    {
                        "provider": provider,
                        "jurisdiction": scenario,
                        "tax_rate_pct": rate_pct,
                        "tax_amount": amount,
                        "tax_engine": quote.get("tax_engine"),
                    }
                )
                if scenario["country"] in {"CA", "FR"} and amount <= 0:
                    issues.append(f"unexpected_zero_tax:{provider}:{scenario['country']}-{scenario['state']}")

        status = "pass" if not issues else "warning"
        run_doc = {
            "run_id": f"iaptax_{uuid.uuid4().hex[:12]}",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "issues": issues,
            "probes": probes,
        }
        await db.iap_tax_freshness_runs.insert_one({**run_doc})
        await db.system_runtime_flags.update_one(
            {"key": "iap_tax_freshness_state"},
            {
                "$set": {
                    "key": "iap_tax_freshness_state",
                    "state": status,
                    "last_run_at": run_doc["completed_at"],
                    "issues": issues,
                }
            },
            upsert=True,
        )

        if issues:
            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(40)
            for admin in admins:
                uid = str(admin.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"iap_tax_guard_{uid}_{int(time.time())}",
                        "user_id": uid,
                        "type": "iap_tax_freshness_warning",
                        "title": "IAP Tax Freshness Guard Warning",
                        "message": "IAP tax probe detected potential stale/zero tax anomalies. Review tax engine and jurisdiction mapping.",
                        "read": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "metadata": {"issues": issues[:10]},
                    }
                )

        logger.info(f"IAP tax freshness guard complete: status={status}, issues={len(issues)}")
    except Exception as exc:
        logger.error(f"IAP tax freshness guard failed: {exc}")
