"""Payment reporting, report-preference, and history-export routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional
import io
import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException, Request
from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.receipt_generator import format_payment_method_label, format_payment_status_label

from .db import db
from .payments_branding import get_document_logo_bytes, get_document_logo_public_url
from .payments_catalog import get_plan_name
from utils.access_control_engine import compute_effective_plan
from .payments_export_integrity import (
    PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS,
    build_admin_verifier_prefill_url,
    build_integrity_meta,
    export_theme_palette,
    format_payment_date_label,
    normalize_export_theme,
    parse_created_at,
    resolve_plan_name,
)


router = APIRouter()
logger = logging.getLogger("routes.payments.reporting")
BRAND_NAME = os.environ.get("BRAND_NAME", "RealAICoach")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_expires") or row.get("subscription_end_date"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="Payment reporting routes are not configured")


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver
_format_payment_method_label = format_payment_method_label
_format_payment_status_label = format_payment_status_label
_format_payment_date_label = format_payment_date_label
_parse_created_at = parse_created_at
_resolve_plan_name = resolve_plan_name
_normalize_export_theme = normalize_export_theme
_export_theme_palette = export_theme_palette
_build_integrity_meta = build_integrity_meta
_build_admin_verifier_prefill_url = build_admin_verifier_prefill_url
_get_document_logo_public_url = get_document_logo_public_url
_get_document_logo_bytes = get_document_logo_bytes


def configure_payment_reporting_routes(*, get_user_from_request: Callable[[Request], Awaitable[object | None]], route_logger: Optional[logging.Logger] = None) -> None:
    global _get_user_from_request, logger
    _get_user_from_request = get_user_from_request
    if route_logger is not None:
        logger = route_logger


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")

async def _fetch_payment_history_export_items(user_id: str, limit: int = 600) -> list[dict]:
    payments = (
        await db.payments.find(
            {"user_id": user_id},
            {
                "_id": 0,
                "id": 1,
                "payment_id": 1,
                "transaction_id": 1,
                "plan_id": 1,
                "amount": 1,
                "currency": 1,
                "payment_method": 1,
                "status": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .to_list(limit)
    )

    transactions = (
        await db.payment_transactions.find(
            {"user_id": user_id},
            {
                "_id": 0,
                "id": 1,
                "payment_id": 1,
                "transaction_id": 1,
                "session_id": 1,
                "plan_id": 1,
                "amount": 1,
                "currency": 1,
                "payment_method": 1,
                "payment_status": 1,
                "status": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .to_list(limit)
    )

    items: list[dict] = []

    for item in payments:
        items.append(
            {
                "reference_id": item.get("id") or item.get("payment_id") or item.get("transaction_id") or "",
                "plan_name": _resolve_plan_name(item.get("plan_id", "")),
                "amount": float(item.get("total_amount", item.get("amount_gross", item.get("amount", 0))) or 0),
                "currency": str(item.get("currency", "USD") or "USD").upper(),
                "method": _format_payment_method_label(item.get("payment_method")),
                "status": str(item.get("status", "unknown") or "unknown"),
                "status_label": _format_payment_status_label(item.get("status", "unknown")),
                "created_at": item.get("created_at", ""),
                "source": "Payments",
            }
        )

    for item in transactions:
        status_value = item.get("payment_status") or item.get("status") or "unknown"
        items.append(
            {
                "reference_id": item.get("payment_id") or item.get("id") or item.get("transaction_id") or item.get("session_id") or "",
                "plan_name": _resolve_plan_name(item.get("plan_id", "")),
                "amount": float(item.get("total_amount", item.get("amount_gross", item.get("amount", 0))) or 0),
                "currency": str(item.get("currency", "USD") or "USD").upper(),
                "method": _format_payment_method_label(item.get("payment_method")),
                "status": str(status_value),
                "status_label": _format_payment_status_label(status_value),
                "created_at": item.get("created_at", ""),
                "source": "Transactions",
            }
        )

    items.sort(key=lambda entry: (_parse_created_at(entry.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return items


def _build_payment_history_csv_text(items: list[dict]) -> str:
    import csv

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Date",
        "Reference ID",
        "Plan",
        "Amount",
        "Currency",
        "Payment Method",
        "Status",
        "Source",
    ])

    for item in items:
        writer.writerow(
            [
                _format_payment_date_label(item.get("created_at", ""), with_time=True),
                item.get("reference_id") or "",
                f"{item.get('plan_name', 'Unknown')} Plan",
                f"{float(item.get('amount', 0) or 0):.2f}",
                item.get("currency", "USD"),
                item.get("method", "Unknown"),
                item.get("status_label", _format_payment_status_label(item.get("status", "unknown"))),
                item.get("source", "Payments"),
            ]
        )

    csv_content = buffer.getvalue()
    buffer.close()
    return csv_content


async def _get_payment_history_export_settings() -> dict:
    doc = await db.settings.find_one({"key": "payment_history_export_settings"}, {"_id": 0})
    current = doc.get("value", {}) if doc else {}
    merged = {**PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS, **current}
    merged["theme_profile"] = _normalize_export_theme(merged.get("theme_profile"))
    merged["signature_enabled"] = bool(merged.get("signature_enabled", True))
    merged["signature_label"] = (merged.get("signature_label") or PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS["signature_label"]).strip()
    return merged


@router.get("/payments/report-preferences")
async def get_report_preferences(request: Request):
    """Get user's payment report email preferences."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    prefs = await db.payment_report_prefs.find_one({"user_id": user.user_id}, {"_id": 0})
    # Merge with defaults to ensure all fields are present
    defaults = {
        "user_id": user.user_id,
        "weekly_enabled": False,
        "monthly_enabled": True,
        "renewal_reminders": True,
        "last_weekly_sent": None,
        "last_monthly_sent": None,
    }
    if prefs:
        defaults.update(prefs)
    return defaults


@router.put("/payments/report-preferences")
async def update_report_preferences(request: Request):
    """Update user's payment report email preferences."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    body = await request.json()
    update = {}
    if "weekly_enabled" in body:
        update["weekly_enabled"] = bool(body["weekly_enabled"])
    if "monthly_enabled" in body:
        update["monthly_enabled"] = bool(body["monthly_enabled"])
    if "renewal_reminders" in body:
        update["renewal_reminders"] = bool(body["renewal_reminders"])
    if not update:
        raise HTTPException(400, "No valid fields to update")
    update["user_id"] = user.user_id
    await db.payment_report_prefs.update_one({"user_id": user.user_id}, {"$set": update}, upsert=True)
    return {"success": True, **update}


@router.post("/payments/send-report")
async def send_report_now(request: Request):
    """Manually trigger a payment report email for the current user."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    result = await generate_and_send_payment_report(user.user_id, user.email, "manual")
    return result


async def generate_and_send_payment_report(user_id: str, email: str, report_type: str = "weekly") -> dict:
    """Generate and send a payment analytics email report."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        return {"success": False, "error": "Email service not configured"}

    now = datetime.now(timezone.utc)
    if report_type == "weekly":
        period_start = now - timedelta(days=7)
        period_label = "Weekly"
        period_desc = f"{period_start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        period_start = now - timedelta(days=30)
        period_label = "Monthly"
        period_desc = f"{period_start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
    else:
        period_start = now - timedelta(days=30)
        period_label = "Payment Summary"
        period_desc = f"Last 30 days ({now.strftime('%b %d, %Y')})"

    # Fetch user payment data
    user_doc = await db.users.find_one(
        {"user_id": user_id}, {"_id": 0, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_expires": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1}
    )
    user_name = (user_doc or {}).get("name", "User")
    plan = _effective_plan_from_user_doc(user_doc)
    plan_name = await get_plan_name(plan)
    expires = (user_doc or {}).get("subscription_expires")

    # Recent payments in period
    payments_cursor = db.payments.find(
        {"user_id": user_id, "status": "completed"},
        {"_id": 0, "plan_id": 1, "amount": 1, "currency": 1, "payment_method": 1, "created_at": 1},
    ).sort("created_at", -1)
    all_payments = await payments_cursor.to_list(100)

    period_payments = []
    total_period = 0.0
    total_alltime = 0.0
    for p in all_payments:
        total_alltime += p.get("amount", 0)
        created = p.get("created_at", "")
        if isinstance(created, datetime):
            pdate = created
        else:
            try:
                pdate = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except Exception:
                continue
        # Ensure timezone-aware comparison
        if pdate.tzinfo is None:
            pdate = pdate.replace(tzinfo=timezone.utc)
        if pdate >= period_start:
            period_payments.append(p)
            total_period += p.get("amount", 0)

    # Build renewal info
    renewal_info = ""
    if expires:
        try:
            exp_date = (
                datetime.fromisoformat(str(expires).replace("Z", "+00:00")) if isinstance(expires, str) else expires
            )
            days_left = (exp_date - now).days
            if days_left > 0:
                renewal_info = f'<tr><td style="padding:8px 0;color:#94A3B8;font-size:13px;">Renewal Date</td><td style="padding:8px 0;text-align:right;font-weight:600;font-size:13px;color:#F1F5F9;">{exp_date.strftime("%b %d, %Y")} ({days_left} days)</td></tr>'
        except Exception:
            pass

    # Build payments table rows
    payment_rows = ""
    for p in period_payments[:10]:
        pname = await get_plan_name(p.get("plan_id", ""))
        method = _format_payment_method_label(p.get("payment_method", "card"))
        amount = p.get("amount", 0)
        created = p.get("created_at", "")
        if isinstance(created, datetime):
            date_str = created.strftime("%b %d, %Y")
        else:
            try:
                date_str = datetime.fromisoformat(str(created).replace("Z", "+00:00")).strftime("%b %d, %Y")
            except Exception:
                date_str = str(created)[:10]
        payment_rows += f'<tr><td style="padding:10px 14px;font-size:13px;border-bottom:1px solid #1E293B;color:#CBD5E1;">{date_str}</td><td style="padding:10px 14px;font-size:13px;border-bottom:1px solid #1E293B;color:#CBD5E1;">{pname} Plan</td><td style="padding:10px 14px;font-size:13px;border-bottom:1px solid #1E293B;color:#CBD5E1;">{method}</td><td style="padding:10px 14px;font-size:13px;font-weight:600;border-bottom:1px solid #1E293B;text-align:right;color:#F1F5F9;">${amount:.2f}</td></tr>'

    no_payments_msg = ""
    if not period_payments:
        no_payments_msg = '<tr><td colspan="4" style="padding:24px;text-align:center;color:#9ca3af;font-size:13px;">No payments during this period</td></tr>'

    logo_url = _get_document_logo_public_url()
    logo_html = (
        f'<img src="{logo_url}" alt="{BRAND_NAME} logo" style="width:138px;max-width:100%;height:auto;display:block;" />'
        if logo_url
        else '<div style="width:32px;height:32px;line-height:32px;border-radius:10px;background:#ffffff;color:#1d4ed8;font-size:13px;font-weight:800;text-align:center;">RA</div>'
    )
    f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#0B0F1A;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#111827;">
  <tr><td style="padding:24px 24px 20px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);border-radius:0 0 16px 16px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
      <tr>
        <td style="width:168px;vertical-align:middle;">
          {logo_html}
        </td>
        <td style="vertical-align:middle;">
          <div style="color:#ffffff;font-size:14px;font-weight:700;">RealAICoach</div>
          <div style="color:#dbeafe;font-size:11px;margin-top:2px;">Secure payment activity report</div>
        </td>
        <td style="vertical-align:middle;text-align:right;color:#dbeafe;font-size:11px;">{period_desc}</td>
      </tr>
    </table>
    <h1 style="color:#ffffff;font-size:22px;margin:0 0 4px;">Your {period_label} Payment Report</h1>
    <p style="color:#e0e7ff;font-size:13px;margin:0;">A cleaner summary of your recent payment activity and subscription status.</p>
  </td></tr>
  <tr><td style="padding:24px;">
    <p style="color:#F1F5F9;font-size:14px;margin:0 0 20px;">Hi {user_name},</p>
    <p style="color:#94A3B8;font-size:13px;margin:0 0 24px;line-height:1.5;">Here's a summary of your payment activity and subscription status on RealAICoach.</p>
    <!-- Summary Cards -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="width:33%;padding:4px;">
          <div style="background:#064E3B;border-radius:12px;padding:16px;text-align:center;">
            <div style="color:#94A3B8;font-size:10px;text-transform:uppercase;font-weight:600;">Period Spent</div>
            <div style="color:#10B981;font-size:22px;font-weight:800;margin-top:4px;">${total_period:.2f}</div>
          </div>
        </td>
        <td style="width:33%;padding:4px;">
          <div style="background:#1E3A5F;border-radius:12px;padding:16px;text-align:center;">
            <div style="color:#94A3B8;font-size:10px;text-transform:uppercase;font-weight:600;">All-Time</div>
            <div style="color:#60A5FA;font-size:22px;font-weight:800;margin-top:4px;">${total_alltime:.2f}</div>
          </div>
        </td>
        <td style="width:33%;padding:4px;">
          <div style="background:#2D1B69;border-radius:12px;padding:16px;text-align:center;">
            <div style="color:#94A3B8;font-size:10px;text-transform:uppercase;font-weight:600;">Plan</div>
            <div style="color:#A78BFA;font-size:18px;font-weight:800;margin-top:4px;">{plan_name}</div>
          </div>
        </td>
      </tr>
    </table>
    <!-- Subscription Info -->
    <table width="100%" style="margin-bottom:24px;background:#1E293B;border-radius:10px;padding:4px;">
      <tr><td style="padding:8px 0;color:#94A3B8;font-size:13px;">Subscription Plan</td><td style="padding:8px 0;text-align:right;font-weight:600;font-size:13px;color:#F1F5F9;">{plan_name}</td></tr>
      {renewal_info}
      <tr><td style="padding:8px 0;color:#94A3B8;font-size:13px;">Payments This Period</td><td style="padding:8px 0;text-align:right;font-weight:600;font-size:13px;color:#F1F5F9;">{len(period_payments)}</td></tr>
    </table>
    <!-- Payments Table -->
    <h3 style="color:#F1F5F9;font-size:15px;margin:0 0 12px;">Recent Transactions</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #1E293B;border-radius:10px;overflow:hidden;">
      <thead><tr style="background:#1E293B;">
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#94A3B8;font-weight:600;">Date</th>
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#94A3B8;font-weight:600;">Plan</th>
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#94A3B8;font-weight:600;">Method</th>
        <th style="padding:10px 14px;text-align:right;font-size:11px;color:#94A3B8;font-weight:600;">Amount</th>
      </tr></thead>
      <tbody>{payment_rows}{no_payments_msg}</tbody>
    </table>
    <!-- Footer CTA -->
    <div style="text-align:center;margin-top:28px;">
      <a href="https://realaicoach.app/payment-history" style="display:inline-block;background:#6366f1;color:#ffffff;padding:12px 28px;border-radius:10px;text-decoration:none;font-size:13px;font-weight:700;">View Full Payment History</a>
    </div>
    <p style="color:#64748B;font-size:11px;text-align:center;margin-top:24px;line-height:1.6;">
      RealAICoach &mdash; support@realaicoach.app<br/>
      You're receiving this because you enabled {report_type} payment reports.
      Manage your preferences in Payment History &gt; Report Settings.
    </p>
  </td></tr>
</table>
</body></html>"""

    from utils.email_service import send_catalog_template
    result = await send_catalog_template(
        recipient_email=email,
        template_key="payment_report",
        recipient_name=user_name,
        user_name=user_name,
        report_type=report_type,
        period_desc=period_desc,
        plan_name=plan_name,
        total_period=total_period,
        total_alltime=total_alltime,
        renewal_info=renewal_info,
        payments=[{"date": p.get("date", ""), "plan": p.get("plan", ""), "method": p.get("method", ""), "amount": p.get("amount", 0)} for p in period_payments[:10]],
    )

    # Update last sent timestamp
    await db.payment_report_prefs.update_one(
        {"user_id": user_id},
        {"$set": {f"last_{report_type}_sent": now.isoformat()}},
        upsert=True,
    )

    return {"success": result.get("success", False), "report_type": report_type, "period": period_desc}


async def run_scheduled_payment_reports(report_type: str = "weekly"):
    """Scheduled job: send payment reports to opted-in users."""
    try:
        query = {f"{report_type}_enabled": True}
        prefs_cursor = db.payment_report_prefs.find(query, {"_id": 0})
        prefs_list = await prefs_cursor.to_list(1000)
        sent = 0
        for pref in prefs_list:
            uid = pref.get("user_id")
            user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1})
            if not user_doc:
                continue
            try:
                await generate_and_send_payment_report(uid, user_doc["email"], report_type)
                sent += 1
            except Exception as e:
                logger.error(f"Payment report failed for {uid}: {e}")
        logger.info(f"Payment {report_type} reports: sent {sent}/{len(prefs_list)}")
    except Exception as e:
        logger.error(f"Scheduled payment reports ({report_type}) failed: {e}")


@router.get("/payments/export-pdf")
async def export_payment_history_pdf(request: Request, token: str = None, inline: str = None):
    """Generate and return a commercial-grade PDF of payment history."""
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from services.pdf_v15_theme import PALETTE, draw_callout_card, draw_kv_card, draw_page_chrome

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")

    items = await _fetch_payment_history_export_items(user.user_id, limit=600)
    settings = await _get_payment_history_export_settings()
    palette = _export_theme_palette(settings.get("theme_profile"))

    completed_aliases = {"completed", "paid", "success", "succeeded"}
    pending_aliases = {"pending", "processing", "initiated", "in progress"}
    total_spent = sum(item.get("amount", 0) for item in items if str(item.get("status", "")).lower() in completed_aliases)
    completed_count = sum(1 for item in items if str(item.get("status", "")).lower() in completed_aliases)
    pending_count = sum(1 for item in items if str(item.get("status", "")).lower() in pending_aliases)
    failed_count = max(len(items) - completed_count - pending_count, 0)
    csv_text = _build_payment_history_csv_text(items)
    integrity = _build_integrity_meta(csv_text, len(items), total_spent, signature_enabled=settings.get("signature_enabled", True))
    from urllib.parse import urlencode

    base_verify_url = (FRONTEND_BASE_URL or str(request.base_url).rstrip("/"))
    verify_query = urlencode(
        {
            "report_id": integrity["report_id"],
            "generated_at": integrity["generated_at"],
            "row_count": integrity["row_count"],
            "total_spent": integrity["total_spent"],
            "data_hash": integrity["data_hash"],
            "signature": integrity["signature"],
        }
    )
    public_verify_url = f"{base_verify_url.rstrip('/')}/api/payments/export/verify?{verify_query}"
    admin_prefill_url = _build_admin_verifier_prefill_url(base_verify_url, integrity)
    qr_target_url = admin_prefill_url or public_verify_url

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=50 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    hero_title = ParagraphStyle(
        "PaymentHistoryHeroTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=rl_colors.white,
    )
    hero_subtitle = ParagraphStyle(
        "PaymentHistoryHeroSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=rl_colors.HexColor(palette["hero_text"]),
    )
    hero_meta = ParagraphStyle(
        "PaymentHistoryHeroMeta",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=rl_colors.HexColor(palette["hero_text"]),
    )
    hero_tile_fallback = ParagraphStyle(
        "PaymentHistoryHeroTileFallback",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=10,
        alignment=1,
        textColor=rl_colors.HexColor("#0F766E"),
    )

    # v7 "PDF v15 for attachment" badge style
    v7_badge_style = ParagraphStyle(
        "PaymentHistoryV7Badge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=rl_colors.white,
        alignment=1,
    )
    metric_label = ParagraphStyle(
        "PaymentHistoryMetricLabel",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=rl_colors.HexColor("#475569"),
    )
    metric_value = ParagraphStyle(
        "PaymentHistoryMetricValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=rl_colors.HexColor("#0F172A"),
    )
    section_title = ParagraphStyle(
        "PaymentHistorySectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=rl_colors.HexColor("#1E293B"),
    )
    header_cell = ParagraphStyle(
        "PaymentHistoryHeaderCell",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.8,
        leading=11,
        textColor=rl_colors.white,
    )
    body_cell = ParagraphStyle(
        "PaymentHistoryBodyCell",
        parent=styles["Normal"],
        fontSize=8.4,
        leading=10,
        textColor=rl_colors.HexColor("#111827"),
    )
    body_cell_right = ParagraphStyle("PaymentHistoryBodyCellRight", parent=body_cell, alignment=2)
    body_cell_center = ParagraphStyle("PaymentHistoryBodyCellCenter", parent=body_cell, alignment=1)
    footer_style = ParagraphStyle(
        "PaymentHistoryFooter",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=rl_colors.HexColor("#64748B"),
    )

    generated_dt = _parse_created_at(integrity.get("generated_at")) or datetime.now(timezone.utc)
    generated_label = generated_dt.strftime("%B %d, %Y at %I:%M %p UTC")

    qr_path = None
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
        qr.add_data(qr_target_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff").convert("RGB")
        fd, qr_path = tempfile.mkstemp(prefix="ph-export-qr-", suffix=".png")
        qr_img.save(os.fdopen(fd, "wb"), format="PNG")
    except Exception:
        qr_path = None
    logo_bytes = _get_document_logo_bytes()
    if logo_bytes:
        logo_block = RLImage(io.BytesIO(logo_bytes), width=16 * mm, height=16 * mm)
    else:
        logo_block = Paragraph("RAI", hero_tile_fallback)

    hero = Table(
        [
            [
                Table(
                    [
                        [logo_block],
                        [Paragraph("Payment History Statement", hero_title)],
                        [Paragraph("Enterprise-grade billing report with complete transaction visibility.", hero_subtitle)],
                        [Paragraph("Official document  |  v7 brand compliant  |  %PDF-1.4", v7_badge_style)],
                    ],
                    colWidths=[110 * mm],
                ),
                Paragraph(f"ACCOUNT<br/>{getattr(user, 'email', '')}<br/><br/>GENERATED<br/>{generated_label}", hero_meta),
            ]
        ],
        colWidths=[120 * mm, 48 * mm],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(palette["hero_bg"])),
                ("BOX", (0, 0), (-1, -1), 0.8, rl_colors.HexColor(palette["hero_border"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    # v7 signature colorful stripe (blue → purple → pink → teal) — inserted after hero
    _v7_stripe_seg = 42 * mm   # 4 segments × 42mm = 168mm total (A4 width minus margins)
    v7_colorful_stripe = Table(
        [["", "", "", ""]],
        colWidths=[_v7_stripe_seg] * 4,
        rowHeights=[3.5 * mm],
    )
    v7_colorful_stripe.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), rl_colors.HexColor("#3B82F6")),  # blue
                ("BACKGROUND", (1, 0), (1, 0), rl_colors.HexColor("#8B5CF6")),  # purple
                ("BACKGROUND", (2, 0), (2, 0), rl_colors.HexColor("#EC4899")),  # pink
                ("BACKGROUND", (3, 0), (3, 0), rl_colors.HexColor("#06D6A0")),  # teal
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    def metric_card(title: str, value: str):
        card = Table(
            [[Paragraph(title, metric_label)], [Paragraph(value, metric_value)]],
            colWidths=[40 * mm],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(palette["surface"])),
                    ("BOX", (0, 0), (-1, -1), 0.8, rl_colors.HexColor(palette["surface_border"])),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return card

    metrics = Table(
        [
            [
                metric_card("Total You Paid", f"${total_spent:,.2f}"),
                metric_card("Transactions", str(len(items))),
                metric_card("Successful", str(completed_count)),
                metric_card("Pending / Failed", f"{pending_count} / {failed_count}"),
            ]
        ],
        colWidths=[42 * mm, 42 * mm, 42 * mm, 42 * mm],
    )
    metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    def status_color_hex(raw_status: str) -> str:
        status = str(raw_status or "").lower()
        if status in completed_aliases:
            return "#059669"
        if status in pending_aliases:
            return "#F59E0B"   # v7 amber (was #D97706)
        return "#DC2626"

    table_rows = [[
        Paragraph("Date", header_cell),
        Paragraph("Reference", header_cell),
        Paragraph("Plan", header_cell),
        Paragraph("Method", header_cell),
        Paragraph("Status", header_cell),
        Paragraph("Amount", header_cell),
    ]]

    for item in items:
        status_label = item.get("status_label", _format_payment_status_label(item.get("status", "unknown")))
        table_rows.append(
            [
                Paragraph(_format_payment_date_label(item.get("created_at", ""), with_time=True), body_cell),
                Paragraph(str(item.get("reference_id") or "—"), body_cell),
                Paragraph(f"{item.get('plan_name', 'Unknown')} Plan", body_cell),
                Paragraph(str(item.get("method") or "Unknown"), body_cell),
                Paragraph(f'<font color="{status_color_hex(item.get("status", ""))}"><b>{status_label}</b></font>', body_cell_center),
                Paragraph(f"${float(item.get('amount', 0) or 0):,.2f} {item.get('currency', 'USD')}", body_cell_right),
            ]
        )

    if len(table_rows) == 1:
        table_rows.append([
            Paragraph("—", body_cell),
            Paragraph("—", body_cell),
            Paragraph("No payment history found", body_cell),
            Paragraph("—", body_cell),
            Paragraph("—", body_cell_center),
            Paragraph("$0.00", body_cell_right),
        ])

    transactions_table = Table(table_rows, colWidths=[28 * mm, 34 * mm, 34 * mm, 28 * mm, 22 * mm, 24 * mm], repeatRows=1)
    transactions_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(palette["table_header"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.55, rl_colors.HexColor(palette["table_grid"])),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F8FAFC")]),
                ("ALIGN", (4, 0), (4, -1), "CENTER"),
                ("ALIGN", (5, 0), (5, -1), "RIGHT"),
            ]
        )
    )

    breakdown_rows = [
        [Paragraph("Subtotal", body_cell), Paragraph(f"${total_spent:,.2f}", body_cell_right)],
        [Paragraph("Tax", body_cell), Paragraph("$0.00", body_cell_right)],
        [Paragraph("Fees", body_cell), Paragraph("$0.00", body_cell_right)],
        [Paragraph("Grand Total", body_cell), Paragraph(f"${total_spent:,.2f}", body_cell_right)],
    ]
    breakdown_table = Table(breakdown_rows, colWidths=[120 * mm, 48 * mm])
    breakdown_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(palette["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.7, rl_colors.HexColor(palette["surface_border"])),
                ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor(palette["table_grid"])),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
            ]
        )
    )

    footer_blocks = []
    if qr_path:
        try:
            footer_blocks.append([RLImage(qr_path, width=20 * mm, height=20 * mm), Paragraph("Scan QR to open a prefilled admin verifier form.", footer_style)])
        except Exception:
            footer_blocks.append([Paragraph("", footer_style), Paragraph("QR verification unavailable in this build.", footer_style)])
    else:
        footer_blocks.append([Paragraph("", footer_style), Paragraph("QR verification unavailable in this build.", footer_style)])

    integrity_table = Table(footer_blocks, colWidths=[24 * mm, 140 * mm])
    integrity_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    elements = [
        hero,
        v7_colorful_stripe,
        Spacer(1, 10),
        metrics,
        Spacer(1, 12),
        Paragraph("Transaction Ledger", section_title),
        Spacer(1, 6),
        transactions_table,
        Spacer(1, 10),
        Paragraph("Itemized Summary", section_title),
        Spacer(1, 5),
        breakdown_table,
        Spacer(1, 12),
        Paragraph(
            f"<b>{BRAND_NAME}</b> &mdash; Enterprise Billing Export<br/>"
            f"Theme: {settings.get('theme_profile', 'enterprise').title()} - support@realaicoach.app - Keep this report for accounting and compliance records.",
            footer_style,
        ),
        Spacer(1, 4),
        Paragraph(
            (
                f"<b>{settings.get('signature_label', 'Integrity Signature')}</b><br/>"
                f"Report ID: {integrity['report_id']} - Generated: {generated_label}<br/>"
                f"Generated ISO: {integrity['generated_at']}<br/>"
                f"Report Hash: {integrity['data_hash']}<br/>"
                f"Signature: {(integrity['signature'] or 'DISABLED')}"
            ),
            footer_style,
        ),
        Spacer(1, 6),
        integrity_table,
    ]

    def _draw_pdf_v15_chrome(canv, build_doc):
        y = draw_page_chrome(
            canv,
            width=float(build_doc.pagesize[0]),
            height=float(build_doc.pagesize[1]),
            margin_x=14 * mm,
            page_no=canv.getPageNumber(),
            title="Payment History Statement",
            subtitle="Enterprise billing export",
            right_primary=f"Rows: {len(items)}",
            right_secondary=f"Total ${total_spent:,.2f}",
            badge_text="PAYMENTS LEDGER COMPLIANCE",
            badge_status="PASS" if failed_count == 0 else "WARNING",
            footer_text="RealAICoach Billing • Enterprise profile",
        )
        if canv.getPageNumber() == 1:
            card_y = draw_kv_card(
                canv,
                margin_x=14 * mm,
                content_w=220,
                y=y - 8,
                title="Export Snapshot",
                rows=[
                    ("Completed", str(completed_count)),
                    ("Pending", str(pending_count)),
                    ("Failed", str(failed_count)),
                ],
                tone=PALETTE["primary"],
            )
            draw_callout_card(
                canv,
                margin_x=(14 * mm) + 228,
                content_w=250,
                y=card_y,
                title="Integrity",
                subtitle="Billing report trust envelope",
                detail=f"Report ID {integrity['report_id']} • Signature {'enabled' if integrity.get('signature') else 'disabled'}",
                status="PASS" if integrity.get("signature") else "INFO",
            )

    doc.build(elements, onFirstPage=_draw_pdf_v15_chrome, onLaterPages=_draw_pdf_v15_chrome)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if qr_path:
        try:
            os.remove(qr_path)
        except Exception:
            pass

    pdf_bytes = _enforce_pdf_v15_enterprise(pdf_bytes, f"payment_history_{getattr(user, 'user_id', 'user')}")

    filename = build_pdf_v15_filename("payment-history", getattr(user, "user_id", "user"))
    disposition = "inline" if str(inline).lower() in {"1", "true", "yes", "inline"} else f'attachment; filename="{filename}"'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition, "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@router.get("/payments/export-csv")
async def export_payment_history_csv(request: Request, token: str = None):
    """Generate and return enterprise-structured CSV for payment history."""
    from fastapi.responses import Response

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Not authenticated")

    items = await _fetch_payment_history_export_items(user.user_id, limit=1000)
    csv_content = _build_payment_history_csv_text(items)

    filename = f"payment-history-enterprise-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
