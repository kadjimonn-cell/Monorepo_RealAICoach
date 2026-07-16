"""Payment admin/maintenance routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import hmac
import io
import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.pagination import iter_find_paginated
from utils.tax_compliance_engine import build_financial_totals, resolve_product_type
from utils.access_control_engine import compute_effective_plan

from .db import db, logger, require_admin
from .payments_catalog import get_plan_name
from .payments_export_integrity import (
    PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS,
    build_admin_verifier_prefill_url,
    build_integrity_payload,
    build_integrity_meta,
    export_theme_palette,
    normalize_export_theme,
    sign_integrity_payload,
)


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_expires_at") or row.get("subscription_end_date"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )
from .payments_history_shared import (
    _format_payment_date_label,
    _format_payment_method_label,
    _format_payment_status_label,
    _parse_created_at,
    _resolve_plan_name,
)
from .payments_reporting_routes import _build_payment_history_csv_text, _get_payment_history_export_settings


router = APIRouter()
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")
BRAND_NAME = os.environ.get("BRAND_NAME", "RealAICoach")


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="Payment admin maintenance routes are not configured")


def _missing_extract_tx_financials(_tx: Dict[str, Any], fee_pass_through_default: bool = False) -> Dict[str, float]:
    raise HTTPException(status_code=503, detail="Payment admin maintenance financial helpers are not configured")


def _default_safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver
_safe_float: Callable[[Any, float], float] = _default_safe_float
_extract_tx_financials: Callable[[Dict[str, Any], bool], Dict[str, float]] = _missing_extract_tx_financials
_normalize_export_theme = normalize_export_theme
_export_theme_palette = export_theme_palette
_build_integrity_meta = build_integrity_meta
_build_integrity_payload = build_integrity_payload
_sign_integrity_payload = sign_integrity_payload
_build_admin_verifier_prefill_url = build_admin_verifier_prefill_url


def configure_payment_admin_maintenance_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
    safe_float: Callable[[Any, float], float],
    extract_tx_financials: Callable[[Dict[str, Any], bool], Dict[str, float]],
) -> None:
    global _get_user_from_request, _safe_float, _extract_tx_financials
    _get_user_from_request = get_user_from_request
    _safe_float = safe_float
    _extract_tx_financials = extract_tx_financials


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")

@router.post("/admin/trigger-renewal-reminders")
async def trigger_renewal_reminders(request: Request):
    """Admin: Manually trigger renewal reminder check."""
    user = await _get_user_from_request(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await run_renewal_reminder_check()
    return result


async def run_renewal_reminder_check() -> dict:
    """Check all users for expiring subscriptions and send reminders (in-app + email)."""
    from utils.email_service import is_email_configured

    now = datetime.now(timezone.utc)
    reminder_days = [7, 1]
    sent_notifications = 0
    sent_emails = 0
    email_available = is_email_configured()

    for days in reminder_days:
        target_date = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        users = await db.users.find(
            {
                "subscription_status": "active",
                "subscription_plan": {"$ne": "free"},
                "subscription_permanent": {"$ne": True},
                "access_locked": {"$ne": True},
                "subscription_expires_at": {"$regex": f"^{target_date}"},
            },
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_expires_at": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
        ).to_list(500)

        for u in users:
            uid = u["user_id"]
            # Skip if already sent today
            existing = await db.notifications.find_one(
                {
                    "user_id": uid,
                    "type": f"renewal_reminder_{days}d",
                    "created_at": {"$gte": (now - timedelta(hours=20)).isoformat()},
                }
            )
            if existing:
                continue

            plan_name = await get_plan_name(_effective_plan_from_user_doc(u))
            expires_str = u.get("subscription_expires_at", target_date)[:10]

            # In-app notification
            await db.notifications.insert_one(
                {
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": uid,
                    "type": f"renewal_reminder_{days}d",
                    "title": f"Subscription expires in {days} day{'s' if days > 1 else ''}",
                    "body": f"Your {plan_name} plan will expire on {expires_str}. Renew now to keep all your premium features.",
                    "action_url": "/subscription/plans",
                    "read": False,
                    "created_at": now.isoformat(),
                }
            )
            sent_notifications += 1

            # Email reminder (if opted in)
            if email_available:
                prefs = await db.payment_report_prefs.find_one({"user_id": uid}, {"_id": 0})
                if prefs and prefs.get("renewal_reminders", True) is False:
                    continue  # User opted out

                # Check if email already sent for this period
                email_exists = await db.email_logs.find_one(
                    {
                        "user_id": uid,
                        "template_key": f"renewal_reminder_{days}d",
                        "created_at": {"$gte": (now - timedelta(hours=20)).isoformat()},
                    }
                )
                if email_exists:
                    continue

                user_name = u.get("name") or u.get("email", "").split("@")[0]


                try:
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=u["email"],
                        template_key="renewal_reminder",
                        recipient_name=user_name,
                        user_name=user_name,
                        plan_name=plan_name,
                        renewal_date=expires_str,
                        amount="",
                        days_remaining=days,
                    )
                    sent_emails += 1
                except Exception as e:
                    logger.error(f"Renewal email failed for {uid}: {e}")

    logger.info(f"Renewal reminders: {sent_notifications} notifications, {sent_emails} emails sent")
    return {"success": True, "reminders_sent": sent_notifications, "emails_sent": sent_emails}


def _resolve_month_window(month: str = "") -> tuple[datetime, datetime, str, str]:
    now = datetime.now(timezone.utc)
    if month:
        try:
            parsed = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    else:
        parsed = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    month_start = parsed.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    month_key = month_start.strftime("%Y-%m")
    month_label = month_start.strftime("%B %Y")
    return month_start, month_end, month_key, month_label


async def _fetch_monthly_executive_items(month_start: datetime, month_end: datetime) -> tuple[list[dict], list[dict], list[dict], set[str]]:
    payment_projection = {
        "_id": 0,
        "id": 1,
        "payment_id": 1,
        "transaction_id": 1,
        "user_id": 1,
        "plan_id": 1,
        "amount": 1,
        "currency": 1,
        "payment_method": 1,
        "status": 1,
        "created_at": 1,
        "subtotal": 1,
        "tax_amount": 1,
        "processing_fee": 1,
        "fee": 1,
        "total_amount": 1,
        "billing_period": 1,
    }
    transaction_projection = {
        "_id": 0,
        "id": 1,
        "payment_id": 1,
        "transaction_id": 1,
        "session_id": 1,
        "user_id": 1,
        "plan_id": 1,
        "amount": 1,
        "currency": 1,
        "payment_method": 1,
        "payment_status": 1,
        "status": 1,
        "created_at": 1,
        "subtotal": 1,
        "tax_amount": 1,
        "processing_fee": 1,
        "fee": 1,
        "total_amount": 1,
        "billing_period": 1,
    }

    def _is_in_month(raw_created_at) -> bool:
        dt = _parse_created_at(raw_created_at)
        if not dt:
            return False
        return month_start <= dt < month_end

    monthly_payments: list[dict] = []
    monthly_transactions: list[dict] = []

    async for payment in iter_find_paginated(
        db.payments,
        {},
        payment_projection,
        sort=[("created_at", -1)],
    ):
        if _is_in_month(payment.get("created_at")):
            monthly_payments.append(payment)

    async for transaction in iter_find_paginated(
        db.payment_transactions,
        {},
        transaction_projection,
        sort=[("created_at", -1)],
    ):
        if _is_in_month(transaction.get("created_at")):
            monthly_transactions.append(transaction)

    items: list[dict] = []
    user_ids: set[str] = set()

    for item in monthly_payments:
        user_id = str(item.get("user_id") or "")
        if user_id:
            user_ids.add(user_id)
        items.append(
            {
                "reference_id": item.get("id") or item.get("payment_id") or item.get("transaction_id") or "",
                "plan_name": _resolve_plan_name(item.get("plan_id", "")),
                "amount": float(item.get("amount", 0) or 0),
                "currency": str(item.get("currency", "USD") or "USD").upper(),
                "method": _format_payment_method_label(item.get("payment_method")),
                "status": str(item.get("status", "unknown") or "unknown"),
                "status_label": _format_payment_status_label(item.get("status", "unknown")),
                "created_at": item.get("created_at", ""),
                "source": "Payments",
            }
        )

    for item in monthly_transactions:
        user_id = str(item.get("user_id") or "")
        if user_id:
            user_ids.add(user_id)
        status_value = item.get("payment_status") or item.get("status") or "unknown"
        items.append(
            {
                "reference_id": item.get("payment_id") or item.get("id") or item.get("transaction_id") or item.get("session_id") or "",
                "plan_name": _resolve_plan_name(item.get("plan_id", "")),
                "amount": float(item.get("amount", 0) or 0),
                "currency": str(item.get("currency", "USD") or "USD").upper(),
                "method": _format_payment_method_label(item.get("payment_method")),
                "status": str(status_value),
                "status_label": _format_payment_status_label(status_value),
                "created_at": item.get("created_at", ""),
                "source": "Transactions",
            }
        )

    items.sort(key=lambda entry: (_parse_created_at(entry.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return items, monthly_payments, monthly_transactions, user_ids


def _build_tax_ready_csv_for_pack(payments: list[dict], transactions: list[dict], user_map: dict[str, dict]) -> str:
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp",
        "Record Type",
        "Document ID",
        "Payment ID",
        "Transaction ID",
        "User ID",
        "Payer Email",
        "Payer Name",
        "Plan",
        "Billing Period",
        "Currency",
        "Subtotal",
        "Tax",
        "Fee",
        "Total",
        "Payment Method",
        "Gateway",
        "Status",
        "Description",
    ])

    for p in payments:
        user = user_map.get(str(p.get("user_id") or ""), {})
        created = p.get("created_at", "")
        if hasattr(created, "isoformat"):
            created = created.isoformat()
        amount_val = float(p.get("amount", 0) or 0)
        tax_val = float(p.get("tax_amount", 0) or 0)
        fee_val = float(p.get("processing_fee", p.get("fee", 0)) or 0)
        subtotal_val = float(p.get("subtotal", amount_val) or amount_val)
        total_val = float(p.get("total_amount", subtotal_val + tax_val + fee_val) or (subtotal_val + tax_val + fee_val))
        doc_id = f"RCT-{str(created)[:10].replace('-', '')}-{str(p.get('payment_id', p.get('id', ''))).upper()[:8]}"
        writer.writerow([
            str(created)[:19],
            "payment",
            doc_id,
            p.get("payment_id", p.get("id", "")),
            p.get("transaction_id", ""),
            p.get("user_id", ""),
            user.get("email", p.get("user_id", "")),
            user.get("name", ""),
            p.get("plan", p.get("subscription_plan", p.get("plan_id", ""))),
            p.get("billing_period", ""),
            p.get("currency", "USD"),
            f"{subtotal_val:.2f}",
            f"{tax_val:.2f}",
            f"{fee_val:.2f}",
            f"{total_val:.2f}",
            p.get("payment_method", ""),
            p.get("gateway", p.get("payment_method", "")),
            p.get("status", ""),
            f"Payment - {p.get('plan', p.get('subscription_plan', p.get('plan_id', 'N/A')))}",
        ])

    payment_ids = {p.get("payment_id") for p in payments}
    for t in transactions:
        if t.get("transaction_id") in payment_ids:
            continue
        user = user_map.get(str(t.get("user_id") or ""), {})
        created = t.get("created_at", "")
        if hasattr(created, "isoformat"):
            created = created.isoformat()
        amount_val = float(t.get("amount", 0) or 0)
        tax_val = float(t.get("tax_amount", 0) or 0)
        fee_val = float(t.get("processing_fee", t.get("fee", 0)) or 0)
        subtotal_val = float(t.get("subtotal", amount_val) or amount_val)
        total_val = float(t.get("total_amount", subtotal_val + tax_val + fee_val) or (subtotal_val + tax_val + fee_val))
        tx_id = t.get("transaction_id", t.get("id", ""))
        doc_id = f"RCT-{str(created)[:10].replace('-', '')}-{str(tx_id).upper()[:8]}"
        writer.writerow([
            str(created)[:19],
            "transaction",
            doc_id,
            t.get("payment_id", ""),
            tx_id,
            t.get("user_id", ""),
            user.get("email", t.get("user_id", "")),
            user.get("name", ""),
            t.get("plan", t.get("plan_id", t.get("type", ""))),
            t.get("billing_period", ""),
            t.get("currency", "USD"),
            f"{subtotal_val:.2f}",
            f"{tax_val:.2f}",
            f"{fee_val:.2f}",
            f"{total_val:.2f}",
            t.get("payment_method", ""),
            t.get("gateway", t.get("provider", "")),
            t.get("payment_status", t.get("status", "")),
            t.get("description", f"Transaction - {t.get('type', 'N/A')}"),
        ])

    csv_content = output.getvalue()
    output.close()
    return csv_content


def _build_executive_billing_pack_pdf(
    items: list[dict],
    month_label: str,
    total_spent: float,
    settings: dict,
    integrity: dict,
    qr_target_url: str,
    generated_label: str,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from services.pdf_v15_theme import PALETTE, draw_callout_card, draw_kv_card, draw_page_chrome

    palette = _export_theme_palette(settings.get("theme_profile"))
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
    title_style = ParagraphStyle("ExecPackTitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=rl_colors.white)
    subtitle_style = ParagraphStyle("ExecPackSubtitle", parent=styles["Normal"], fontSize=10, leading=13, textColor=rl_colors.HexColor(palette["hero_text"]))
    body_style = ParagraphStyle("ExecPackBody", parent=styles["Normal"], fontSize=8.2, leading=10, textColor=rl_colors.HexColor("#111827"))
    body_center = ParagraphStyle("ExecPackBodyCenter", parent=body_style, alignment=1)
    body_right = ParagraphStyle("ExecPackBodyRight", parent=body_style, alignment=2)
    footer_style = ParagraphStyle("ExecPackFooter", parent=styles["Normal"], fontSize=8, leading=11, textColor=rl_colors.HexColor("#64748B"))

    hero = Table(
        [[
            Paragraph(f"Monthly Executive Billing Pack<br/>{month_label}", title_style),
            Paragraph(f"Generated {generated_label}<br/>Theme: {settings.get('theme_profile', 'enterprise').title()}", subtitle_style),
        ]],
        colWidths=[168 * mm],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(palette["hero_bg"])),
                ("BOX", (0, 0), (-1, -1), 0.8, rl_colors.HexColor(palette["hero_border"])),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    summary = Table(
        [["Rows", str(len(items)), "Successful Spend", f"${total_spent:,.2f}"]],
        colWidths=[28 * mm, 40 * mm, 42 * mm, 58 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(palette["surface"])),
                ("BOX", (0, 0), (-1, -1), 0.7, rl_colors.HexColor(palette["surface_border"])),
                ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor(palette["table_grid"])),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    rows = [["Date", "Reference", "Plan", "Method", "Status", "Amount"]]
    display_items = items[:140]
    for item in display_items:
        rows.append([
            Paragraph(_format_payment_date_label(item.get("created_at", ""), with_time=True), body_style),
            Paragraph(str(item.get("reference_id") or "—"), body_style),
            Paragraph(f"{item.get('plan_name', 'Unknown')} Plan", body_style),
            Paragraph(str(item.get("method") or "Unknown"), body_style),
            Paragraph(str(item.get("status_label") or "Unknown"), body_center),
            Paragraph(f"${float(item.get('amount', 0) or 0):,.2f} {item.get('currency', 'USD')}", body_right),
        ])

    if len(rows) == 1:
        rows.append([
            Paragraph("—", body_style),
            Paragraph("—", body_style),
            Paragraph("No records in selected month", body_style),
            Paragraph("—", body_style),
            Paragraph("—", body_center),
            Paragraph("$0.00", body_right),
        ])

    table = Table(rows, colWidths=[26 * mm, 38 * mm, 34 * mm, 26 * mm, 20 * mm, 24 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(palette["table_header"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.2),
                ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor(palette["table_grid"])),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    qr_path = None
    if qr_target_url:
        try:
            import qrcode

            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
            qr.add_data(qr_target_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff").convert("RGB")
            fd, qr_path = tempfile.mkstemp(prefix="exec-pack-qr-", suffix=".png")
            with os.fdopen(fd, "wb") as qr_file:
                qr_img.save(qr_file, format="PNG")
        except Exception:
            qr_path = None

    footer_qr = Table(
        [[RLImage(qr_path, width=20 * mm, height=20 * mm) if qr_path else Paragraph("", footer_style), Paragraph("Scan QR to prefill the admin verifier form.", footer_style)]],
        colWidths=[24 * mm, 142 * mm],
    )
    footer_qr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    elements = [
        hero,
        Spacer(1, 10),
        summary,
        Spacer(1, 10),
        table,
        Spacer(1, 10),
        Paragraph(
            f"<b>{settings.get('signature_label', 'Integrity Signature')}</b><br/>"
            f"Report ID: {integrity['report_id']}<br/>"
            f"Generated ISO: {integrity['generated_at']}<br/>"
            f"Report Hash: {integrity['data_hash']}<br/>"
            f"Signature: {integrity['signature'] or 'DISABLED'}",
            footer_style,
        ),
        Spacer(1, 6),
        footer_qr,
    ]
    if len(items) > len(display_items):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"Display truncated to first {len(display_items)} rows in PDF. Full records are included in CSV files.", footer_style))

    def _draw_pdf_v15_chrome(canv, build_doc):
        y = draw_page_chrome(
            canv,
            width=float(build_doc.pagesize[0]),
            height=float(build_doc.pagesize[1]),
            margin_x=14 * mm,
            page_no=canv.getPageNumber(),
            title="Executive Billing Pack",
            subtitle=f"Monthly overview • {month_label}",
            right_primary=f"Rows: {len(items)}",
            right_secondary=f"Spend ${total_spent:,.2f}",
            badge_text="EXECUTIVE BILLING OPERATIONS",
            badge_status="PASS",
            footer_text="RealAICoach Billing • Enterprise profile",
        )
        if canv.getPageNumber() == 1:
            card_y = draw_kv_card(
                canv,
                margin_x=14 * mm,
                content_w=220,
                y=y - 8,
                title="Pack Summary",
                rows=[
                    ("Rows", str(len(items))),
                    ("Theme", str(settings.get("theme_profile", "enterprise"))),
                    ("Hash", str(integrity.get("data_hash", ""))[:16]),
                ],
                tone=PALETTE["primary"],
            )
            draw_callout_card(
                canv,
                margin_x=(14 * mm) + 228,
                content_w=250,
                y=card_y,
                title="Signature State",
                subtitle="Executive pack verification",
                detail=f"Label: {settings.get('signature_label', 'Integrity Signature')} • Signature {'enabled' if integrity.get('signature') else 'disabled'}",
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

    return _enforce_pdf_v15_enterprise(pdf_bytes, f"executive_billing_pack_{month_label}")


@router.get("/admin/payments/executive-billing-pack")
async def download_monthly_executive_billing_pack(request: Request, month: str = ""):
    import zipfile
    from urllib.parse import urlencode

    await require_admin(request)

    month_start, month_end, month_key, month_label = _resolve_month_window(month)
    items, monthly_payments, monthly_transactions, user_ids = await _fetch_monthly_executive_items(month_start, month_end)
    settings = await _get_payment_history_export_settings()

    completed_aliases = {"completed", "paid", "success", "succeeded"}
    total_spent = sum(float(item.get("amount", 0) or 0) for item in items if str(item.get("status", "")).lower() in completed_aliases)
    enterprise_csv = _build_payment_history_csv_text(items)
    integrity = _build_integrity_meta(enterprise_csv, len(items), total_spent, signature_enabled=settings.get("signature_enabled", True))

    base_frontend_url = (FRONTEND_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
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
    public_verify_url = f"{base_frontend_url}/api/payments/export/verify?{verify_query}"
    admin_prefill_url = _build_admin_verifier_prefill_url(base_frontend_url, integrity)
    qr_target_url = admin_prefill_url or public_verify_url

    generated_dt = _parse_created_at(integrity.get("generated_at")) or datetime.now(timezone.utc)
    generated_label = generated_dt.strftime("%B %d, %Y at %I:%M %p UTC")
    executive_pdf = _build_executive_billing_pack_pdf(
        items=items,
        month_label=month_label,
        total_spent=total_spent,
        settings=settings,
        integrity=integrity,
        qr_target_url=qr_target_url,
        generated_label=generated_label,
    )

    user_map: dict[str, dict] = {}
    if user_ids:
        user_docs = await db.users.find(
            {"user_id": {"$in": list(user_ids)}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(len(user_ids))
        user_map = {str(u.get("user_id")): u for u in user_docs}
    tax_csv = _build_tax_ready_csv_for_pack(monthly_payments, monthly_transactions, user_map)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(build_pdf_v15_filename("executive-billing", month_key), executive_pdf)
        zf.writestr(f"enterprise-billing-{month_key}.csv", enterprise_csv)
        zf.writestr(f"tax-billing-{month_key}.csv", tax_csv)

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="monthly-executive-billing-pack-{month_key}.zip"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


class PaymentHistoryExportSettingsUpdate(BaseModel):
    theme_profile: Optional[str] = None
    signature_enabled: Optional[bool] = None
    signature_label: Optional[str] = None


class PaymentHistoryIntegrityVerifyRequest(BaseModel):
    report_id: str = Field(..., min_length=4)
    generated_at: str = Field(..., min_length=10)
    row_count: int = Field(..., ge=0)
    total_spent: float = Field(..., ge=0)
    data_hash: str = Field(..., min_length=64, max_length=128)
    signature: str = Field(..., min_length=8)


@router.get("/admin/payment-history-export-settings")
async def get_payment_history_export_settings(request: Request):
    """Return global payment-history export theme/signature settings."""
    await require_admin(request)
    settings = await _get_payment_history_export_settings()
    return JSONResponse(content={"settings": settings})


@router.put("/admin/payment-history-export-settings")
async def update_payment_history_export_settings(request: Request, payload: PaymentHistoryExportSettingsUpdate):
    """Update global payment-history export theme/signature settings."""
    await require_admin(request)

    updates = payload.model_dump(exclude_none=True)
    if "theme_profile" in updates:
        updates["theme_profile"] = _normalize_export_theme(updates.get("theme_profile"))
    if "signature_label" in updates:
        updates["signature_label"] = (updates.get("signature_label") or PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS["signature_label"]).strip()

    current = await _get_payment_history_export_settings()
    merged = {**current, **updates}
    merged["theme_profile"] = _normalize_export_theme(merged.get("theme_profile"))
    merged["signature_enabled"] = bool(merged.get("signature_enabled", True))
    merged["signature_label"] = (merged.get("signature_label") or PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS["signature_label"]).strip()

    await db.settings.update_one(
        {"key": "payment_history_export_settings"},
        {
            "$set": {
                "key": "payment_history_export_settings",
                "value": merged,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    return JSONResponse(content={"ok": True, "settings": merged})


@router.post("/admin/payment-history-export-settings/reset")
async def reset_payment_history_export_settings(request: Request):
    """Reset payment-history export settings to defaults."""
    await require_admin(request)
    defaults = dict(PAYMENT_HISTORY_EXPORT_SETTINGS_DEFAULTS)
    await db.settings.update_one(
        {"key": "payment_history_export_settings"},
        {
            "$set": {
                "key": "payment_history_export_settings",
                "value": defaults,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return JSONResponse(content={"ok": True, "settings": defaults})


@router.post("/admin/payment-history-export/verify-integrity")
async def verify_payment_history_export_integrity(request: Request, payload: PaymentHistoryIntegrityVerifyRequest):
    """Verify report hash/signature for payment-history export documents."""
    await require_admin(request)

    try:
        datetime.fromisoformat(payload.generated_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="generated_at must be ISO datetime")

    if len(payload.data_hash) < 64:
        raise HTTPException(status_code=400, detail="Invalid data_hash")

    canonical_hash = payload.data_hash.strip().lower()
    payload_str = _build_integrity_payload(
        payload.report_id.strip(),
        payload.generated_at.strip(),
        payload.row_count,
        payload.total_spent,
        canonical_hash,
    )
    expected_signature = _sign_integrity_payload(payload_str)
    received_signature = payload.signature.strip().lower()

    if not expected_signature:
        return JSONResponse(
            content={
                "valid": False,
                "reason": "Signature secret is not configured",
                "expected_signature": "",
            }
        )

    is_valid = hmac.compare_digest(expected_signature, received_signature)
    return JSONResponse(
        content={
            "valid": is_valid,
            "report_id": payload.report_id,
            "generated_at": payload.generated_at,
            "row_count": payload.row_count,
            "total_spent": round(float(payload.total_spent), 2),
            "data_hash": canonical_hash,
            "expected_signature": expected_signature,
            "provided_signature": received_signature,
            "reason": "Signature verified" if is_valid else "Signature mismatch",
        }
    )


# ─── Receipt Branding Customization ───────────────────────────────────


RECEIPT_BRANDING_DEFAULTS = {
    "brand_name": "RealAICoach",
    "primary_color": "#2563EB",
    "secondary_color": "#3B82F6",   # v7: blue accent (not orange) — PDF v15 compliant
    "footer_text": "Thank you for your business!",
    "company_info": "support@realaicoach.app",
    "show_qr_code": True,
    "custom_logo": None,
}


@router.get("/admin/receipt-branding")
async def get_receipt_branding(request: Request):
    """Return current receipt branding settings."""
    await require_admin(request)
    doc = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
    if doc and "value" in doc:
        merged = {**RECEIPT_BRANDING_DEFAULTS, **doc["value"]}
        return JSONResponse(content={"branding": merged})
    return JSONResponse(content={"branding": RECEIPT_BRANDING_DEFAULTS})


class ReceiptBrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    footer_text: Optional[str] = None
    company_info: Optional[str] = None
    show_qr_code: Optional[bool] = None


@router.put("/admin/receipt-branding")
async def update_receipt_branding(request: Request, body: ReceiptBrandingUpdate):
    """Update receipt branding settings (admin only)."""
    user = await require_admin(request)
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    existing = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
    current = existing.get("value", {}) if existing else {}
    merged = {**RECEIPT_BRANDING_DEFAULTS, **current, **update_data}
    await db.settings.update_one(
        {"key": "receipt_branding"},
        {"$set": {"key": "receipt_branding", "value": merged, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.user_id}},
        upsert=True,
    )
    return JSONResponse(content={"branding": merged, "message": "Receipt branding updated"})


@router.post("/admin/receipt-branding/reset")
async def reset_receipt_branding(request: Request):
    """Reset receipt branding to defaults (admin only)."""
    user = await require_admin(request)
    await db.settings.update_one(
        {"key": "receipt_branding"},
        {"$set": {"key": "receipt_branding", "value": RECEIPT_BRANDING_DEFAULTS, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.user_id}},
        upsert=True,
    )
    return JSONResponse(content={"branding": RECEIPT_BRANDING_DEFAULTS, "message": "Receipt branding reset to defaults"})


@router.post("/admin/receipt-branding/preview")
async def preview_receipt_branding(request: Request):
    """Generate a preview PDF with the provided branding settings (admin only)."""
    user = await require_admin(request)
    body = await request.json()
    branding = {**RECEIPT_BRANDING_DEFAULTS, **body}
    from utils.receipt_generator import generate_pdf_from_payment
    sample_payment = {
        "payment_id": "PREVIEW-SAMPLE-001",
        "plan_id": "premium",
        "amount": 29.99,
        "payment_method": "stripe",
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "billing_period": "monthly",
    }
    pdf_bytes = generate_pdf_from_payment("receipt", sample_payment, getattr(user, "name", "Admin"), user.email, branding_override=branding)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{build_pdf_v15_filename("branding-preview", "admin")}"', "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


CUSTOM_LOGO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "branding")
os.makedirs(CUSTOM_LOGO_DIR, exist_ok=True)


@router.post("/admin/receipt-branding/logo")
async def upload_receipt_logo(request: Request):
    """Upload a custom logo for receipts (admin only). Accepts multipart form with 'logo' file."""
    user = await require_admin(request)
    form = await request.form()
    logo_file = form.get("logo")
    if not logo_file:
        raise HTTPException(status_code=400, detail="No logo file provided")
    content_type = getattr(logo_file, "content_type", "") or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (PNG, JPG, SVG)")
    data = await logo_file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 2MB")
    ext = os.path.splitext(getattr(logo_file, "filename", "logo.png"))[1] or ".png"
    filename = f"custom_receipt_logo{ext}"
    filepath = os.path.join(CUSTOM_LOGO_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    logo_url = f"/api/static/images/branding/{filename}"
    existing = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
    current = existing.get("value", {}) if existing else {}
    merged = {**RECEIPT_BRANDING_DEFAULTS, **current, "custom_logo": logo_url}
    await db.settings.update_one(
        {"key": "receipt_branding"},
        {"$set": {"key": "receipt_branding", "value": merged, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.user_id}},
        upsert=True,
    )
    return JSONResponse(content={"logo_url": logo_url, "branding": merged, "message": "Logo uploaded"})


@router.delete("/admin/receipt-branding/logo")
async def delete_receipt_logo(request: Request):
    """Remove the custom logo (admin only)."""
    user = await require_admin(request)
    for f in os.listdir(CUSTOM_LOGO_DIR):
        if f.startswith("custom_receipt_logo"):
            os.remove(os.path.join(CUSTOM_LOGO_DIR, f))
    existing = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
    current = existing.get("value", {}) if existing else {}
    merged = {**RECEIPT_BRANDING_DEFAULTS, **current, "custom_logo": None}
    await db.settings.update_one(
        {"key": "receipt_branding"},
        {"$set": {"key": "receipt_branding", "value": merged, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.user_id}},
        upsert=True,
    )
    return JSONResponse(content={"branding": merged, "message": "Logo removed"})


@router.get("/subscriptions/recovery-stats")
async def recovery_stats(request: Request):
    """Admin endpoint: Get detailed recovery analytics."""
    user = await _get_user_from_request(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    total = await db.payment_recovery.count_documents({})
    active = await db.payment_recovery.count_documents({"status": "active", "recovered": False})
    recovered = await db.payment_recovery.count_documents({"recovered": True})
    expired = await db.payment_recovery.count_documents({"status": "expired"})

    # Recovery by email stage
    recovered_at_stage1 = await db.payment_recovery.count_documents({"recovered": True, "emails_sent": 1})
    recovered_at_stage2 = await db.payment_recovery.count_documents({"recovered": True, "emails_sent": 2})
    recovered_at_stage3 = await db.payment_recovery.count_documents({"recovered": True, "emails_sent": 3})

    # Recovery by payment method
    pipeline_method = [
        {"$match": {"recovered": True}},
        {"$group": {"_id": "$payment_method", "count": {"$sum": 1}}},
    ]
    method_stats = {}
    async for doc in db.payment_recovery.aggregate(pipeline_method):
        method_stats[doc["_id"] or "unknown"] = doc["count"]

    # Recovery by currency
    pipeline_currency = [
        {"$match": {"recovered": True}},
        {"$group": {"_id": "$currency", "count": {"$sum": 1}, "total_usd": {"$sum": "$amount_usd"}}},
    ]
    currency_stats = []
    async for doc in db.payment_recovery.aggregate(pipeline_currency):
        currency_stats.append({"currency": doc["_id"] or "USD", "count": doc["count"], "total_usd": round(doc["total_usd"], 2)})

    # Revenue saved (sum of recovered amounts in USD)
    pipeline_revenue = [
        {"$match": {"recovered": True}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}},
    ]
    revenue_saved = 0
    async for doc in db.payment_recovery.aggregate(pipeline_revenue):
        revenue_saved = round(doc["total"], 2)

    # Revenue at risk (active unrecovered)
    pipeline_risk = [
        {"$match": {"status": "active", "recovered": False}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}},
    ]
    revenue_at_risk = 0
    async for doc in db.payment_recovery.aggregate(pipeline_risk):
        revenue_at_risk = round(doc["total"], 2)

    # Recent recovery tokens (last 10)
    recent = []
    async for doc in db.payment_recovery.find({}, {"_id": 0}).sort("created_at", -1).limit(10):
        recent.append(doc)

    # Emails sent stats
    total_emails = await db.payment_recovery.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$emails_sent"}}}
    ]).to_list(1)
    total_emails_sent = total_emails[0]["total"] if total_emails else 0

    return JSONResponse(content={
        "overview": {
            "total_tokens": total,
            "active": active,
            "recovered": recovered,
            "expired": expired,
            "recovery_rate": round(recovered / total * 100, 1) if total > 0 else 0,
            "revenue_saved_usd": revenue_saved,
            "revenue_at_risk_usd": revenue_at_risk,
            "total_emails_sent": total_emails_sent,
        },
        "by_stage": {
            "day1": recovered_at_stage1,
            "day3": recovered_at_stage2,
            "day7": recovered_at_stage3,
        },
        "by_method": method_stats,
        "by_currency": currency_stats,
        "recent_tokens": recent,
    })


@router.post("/admin/payments/tax-compliance/audit")
async def run_tax_compliance_audit(request: Request):
    """Enterprise tax/financial audit with safe auto-fix for missing canonical fields."""
    user = await _get_user_from_request(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    sample_size = 600
    docs = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).limit(sample_size).to_list(sample_size)
    scanned = len(docs)
    fixed = 0
    missing = 0
    issues: list[Dict[str, Any]] = []

    for tx in docs:
        missing_fields = []
        tx_id = tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id") or ""
        provider_l = str(tx.get("provider") or tx.get("gateway") or tx.get("payment_method") or "").lower()
        if not tx.get("provider"):
            missing_fields.append("provider")
        for f in ["subtotal", "tax_amount", "processing_fee", "amount_gross", "amount_net", "total_amount", "jurisdiction", "product_type"]:
            if tx.get(f) is None:
                missing_fields.append(f)

        if not missing_fields:
            # Also enforce FedaPay fixed-tax policy even when structural fields exist
            if provider_l in {"fedapay", "mobile_money_fedapay", "fedapay_card"} or "fedapay" in provider_l:
                subtotal = _safe_float(tx.get("subtotal", tx.get("amount_local", tx.get("amount", 0))), 0.0)
                expected_tax = round(subtotal * 0.0825, 2)
                fee_value = _safe_float(tx.get("processing_fee", tx.get("fee", tx.get("fee_local", 0))), 0.0)
                fee_pass_through = bool(tx.get("fee_pass_through", True))
                expected = build_financial_totals(
                    subtotal=subtotal,
                    tax_amount=expected_tax,
                    processing_fee=fee_value,
                    fee_pass_through=fee_pass_through,
                )
                tax_rate = _safe_float(tx.get("tax_rate", 0), 0.0)
                tax_provider = str(tx.get("tax_provider", "")).lower()
                if abs(_safe_float(tx.get("tax_amount", 0), 0.0) - expected_tax) > 0.01 or abs(tax_rate - 0.0825) > 1e-6 or tax_provider != "fedapay_fixed_rate":
                    await db.payment_transactions.update_one(
                        {"transaction_id": tx.get("transaction_id")} if tx.get("transaction_id") else {"session_id": tx.get("session_id")},
                        {
                            "$set": {
                                "tax_provider": "fedapay_fixed_rate",
                                "tax_engine": "provider_policy_override",
                                "tax_rate": 0.0825,
                                "tax_amount": expected_tax,
                                "tax_breakdown": [
                                    {
                                        "jurisdiction": "FEDAPAY_FIXED",
                                        "tax_type": "fixed_transaction_tax",
                                        "rate": 0.0825,
                                        "amount": expected_tax,
                                        "note": "Fixed 8.25% tax applied per transaction",
                                    }
                                ],
                                "subtotal": expected["subtotal"],
                                "amount_gross": expected["amount_gross"],
                                "total_amount": expected["total_amount"],
                                "amount_net": expected["amount_net"],
                                "processing_fee": expected["processing_fee"],
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
                    fixed += 1
                    issues.append({"transaction_id": tx_id, "missing_fields": ["fedapay_fixed_tax_policy"]})
            continue

        missing += 1
        provider = tx.get("provider") or tx.get("gateway") or tx.get("payment_method") or "unknown"
        financials = _extract_tx_financials(tx, fee_pass_through_default=bool(tx.get("fee_pass_through", False)))
        patch = {
            "provider": provider,
            "subtotal": financials["subtotal"],
            "tax_amount": _safe_float(tx.get("tax_amount", 0), 0.0),
            "processing_fee": financials["processing_fee"],
            "amount_gross": financials["amount_gross"],
            "amount_net": financials["amount_net"],
            "total_amount": financials["total_amount"],
            "jurisdiction": tx.get("jurisdiction", {"country": "US", "state": "", "postal_code": ""}),
            "product_type": tx.get("product_type", resolve_product_type(tx.get("plan_id", "free"))),
            "transaction_id": tx_id,
            "status": tx.get("status") or tx.get("payment_status") or "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.payment_transactions.update_one(
            {"session_id": tx.get("session_id")} if tx.get("session_id") else {"payment_id": tx.get("payment_id")},
            {"$set": patch},
        )
        fixed += 1
        issues.append({"transaction_id": tx_id, "missing_fields": missing_fields})

    report = {
        "report_id": f"tax_audit_{int(datetime.now(timezone.utc).timestamp())}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned_transactions": scanned,
        "transactions_with_missing_fields": missing,
        "auto_fixed_transactions": fixed,
        "health_score": int(round(((scanned - max(missing - min(fixed, missing), 0)) / scanned) * 100)) if scanned else 100,
        "status": "healthy" if missing == 0 else ("fixed" if fixed == missing else "warning"),
        "sample_issues": issues[:20],
    }
    await db.tax_compliance_audit_history.insert_one({**report})
    return report
