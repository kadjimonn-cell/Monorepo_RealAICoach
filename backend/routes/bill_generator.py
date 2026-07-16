"""Bill Generator — enterprise invoicing workspace for AI Feature Gallery.

Plan enforcement:
  Free    → Limited access
  Basic   → Almost unlimited
  Premium → Full unlimited
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import logging
import uuid
import re

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .db import db, require_auth, User
from utils.llm_helper import generate_verified_json
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.access_control_engine import compute_effective_plan


router = APIRouter(prefix="/bill-generator", tags=["Bill Generator"])
logger = logging.getLogger("routes.bill_generator")

PDF_DIR = Path(__file__).parent.parent / "media" / "bill_generator"
PDF_DIR.mkdir(parents=True, exist_ok=True)

PLAN_ACTION_LIMITS = {
    "ai_draft": {"free": 3, "basic": 120, "premium": -1},
    "create_bill": {"free": 5, "basic": 220, "premium": -1},
    "pdf_export": {"free": 3, "basic": 120, "premium": -1},
    "status_update": {"free": 20, "basic": 500, "premium": -1},
    "catalog_manage": {"free": 25, "basic": 500, "premium": -1},
    "create_schedule": {"free": 2, "basic": 80, "premium": -1},
    "run_schedule": {"free": 4, "basic": 300, "premium": -1},
    "reminder_message": {"free": 20, "basic": 600, "premium": -1},
    "approval_action": {"free": 20, "basic": 600, "premium": -1},
}

WORKSPACE_ROLE_PERMISSIONS = {
    "owner": {"manage_workspace", "approve_bill", "create_bill", "send_bill", "view_dashboard"},
    "manager": {"approve_bill", "create_bill", "send_bill", "view_dashboard"},
    "finance": {"approve_bill", "create_bill", "send_bill", "view_dashboard"},
    "viewer": {"view_dashboard"},
}

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=280)


class BillLineItem(BaseModel):
    description: str = Field(min_length=2, max_length=220)
    quantity: float = Field(ge=0.01, le=100000)
    unit_price: float = Field(ge=0, le=1_000_000)
    tax_rate: float = Field(default=0, ge=0, le=100)


class BillCreateRequest(BaseModel):
    bill_type: str = Field(default="invoice", pattern="^(invoice|receipt|proforma)$")
    client_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=8)
    items: list[BillLineItem] = Field(default_factory=list)
    issue_date: str | None = None
    due_date: str | None = None
    notes: str = Field(default="", max_length=1000)
    discount_pct: float = Field(default=0, ge=0, le=100)
    recurring: bool = False
    recurrence_frequency: str | None = Field(default=None, pattern="^(daily|weekly|monthly|quarterly|yearly)?$")
    ai_context: str = Field(default="", max_length=1200)


class BillAIDraftRequest(BaseModel):
    client_name: str = Field(default="", max_length=120)
    industry: str = Field(default="general", max_length=80)
    scope: str = Field(min_length=8, max_length=1500)
    amount_target: float = Field(default=0, ge=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=8)


class BillStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(draft|sent|paid|overdue|cancelled)$")
    note: str = Field(default="", max_length=500)


class ProductCatalogRequest(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    description: str = Field(default="", max_length=320)
    unit_price: float = Field(ge=0, le=1_000_000)
    tax_rate: float = Field(default=0, ge=0, le=100)
    unit: str = Field(default="item", max_length=30)


class RecurringScheduleRequest(BaseModel):
    schedule_name: str = Field(min_length=2, max_length=160)
    frequency: str = Field(pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    template: BillCreateRequest
    start_at: str | None = None


class RecurringToggleRequest(BaseModel):
    active: bool = True


class ReminderMessageRequest(BaseModel):
    tone: str = Field(default="friendly", pattern="^(friendly|firm|final)$")


class ChannelSettingsRequest(BaseModel):
    in_app_enabled: bool = True
    email_enabled: bool = True


class ReminderDispatchRequest(BaseModel):
    tone: str = Field(default="friendly", pattern="^(friendly|firm|final)$")
    channel_in_app: bool = True
    channel_email: bool = True


class BulkReminderRequest(BaseModel):
    bill_ids: list[str] = Field(default_factory=list)
    tone: str = Field(default="friendly", pattern="^(friendly|firm|final)$")
    channel_in_app: bool = True
    channel_email: bool = True


class WorkspaceMemberRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    role: str = Field(default="viewer", pattern="^(owner|manager|finance|viewer)$")


class WorkspaceRoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(owner|manager|finance|viewer)$")


class WorkflowDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=400)


class WorkflowSettingsRequest(BaseModel):
    approval_required_for_send: bool = True


def _resolve_plan(user: User) -> str:
    plan = compute_effective_plan(
        {
            "is_admin": bool(user.is_admin),
            "full_access": bool(user.full_access),
            "subscription_permanent": bool(user.subscription_permanent),
            "subscription_plan": user.subscription_plan,
            "subscription_status": user.subscription_status,
            "payment_verified": bool(getattr(user, "payment_verified", False)),
            "subscription_end_date": user.subscription_end_date,
            "pending_subscription_transition": user.pending_subscription_transition,
        }
    )
    return plan if plan in {"free", "basic", "premium"} else "free"


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


async def _resolve_owner_id(request: Request, fallback_user_id: str | None = None) -> str:
    """Resolve owner ID from authenticated user or validated guest fallback."""
    try:
        from .db import get_current_user
        user = await get_current_user(request)
        if user and user.user_id:
            return user.user_id
    except Exception:
        pass
    
    if fallback_user_id:
        if not GUEST_ID_RE.match(fallback_user_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid guest ID format. Expected pattern: user_<12-80 chars>"
            )
        return fallback_user_id
    
    raise HTTPException(
        status_code=401,
        detail="Authentication required or valid fallback_user_id needed"
    )


def _today_start_iso() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


async def _enforce_action_limit(user: User, action: str) -> dict[str, Any]:
    plan = _resolve_plan(user)
    limits = PLAN_ACTION_LIMITS.get(action) or {}
    limit = int(limits.get(plan, 0))
    used = await db.bill_generator_usage_log.count_documents(
        {
            "user_id": user.user_id,
            "action": action,
            "created_at": {"$gte": _today_start_iso()},
        }
    )
    if limit >= 0 and used >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"{_scope_label(plan)}: daily {action.replace('_', ' ')} limit reached "
                f"({limit}). Upgrade plan for more capacity."
            ),
        )
    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "used": int(used),
        "limit": int(limit),
        "remaining": -1 if limit < 0 else max(0, int(limit - used)),
    }


async def _log_usage(user_id: str, action: str, plan: str, metadata: dict[str, Any] | None = None) -> None:
    await db.bill_generator_usage_log.insert_one(
        {
            "usage_id": f"bgu_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _normalize_money(value: float) -> float:
    return round(float(value or 0), 2)


def _compute_totals(items: list[BillLineItem], discount_pct: float) -> dict[str, Any]:
    normalized_items = []
    subtotal = 0.0
    tax_total = 0.0

    for item in items:
        line_subtotal = float(item.quantity) * float(item.unit_price)
        line_tax = line_subtotal * (float(item.tax_rate) / 100.0)
        line_total = line_subtotal + line_tax
        subtotal += line_subtotal
        tax_total += line_tax

        normalized_items.append(
            {
                "item_id": f"bit_{uuid.uuid4().hex[:10]}",
                "description": str(item.description).strip(),
                "quantity": _normalize_money(item.quantity),
                "unit_price": _normalize_money(item.unit_price),
                "tax_rate": _normalize_money(item.tax_rate),
                "line_subtotal": _normalize_money(line_subtotal),
                "line_tax": _normalize_money(line_tax),
                "line_total": _normalize_money(line_total),
            }
        )

    discount_total = (subtotal + tax_total) * (float(discount_pct or 0) / 100.0)
    total = max(0.0, (subtotal + tax_total) - discount_total)
    return {
        "items": normalized_items,
        "subtotal": _normalize_money(subtotal),
        "tax_total": _normalize_money(tax_total),
        "discount_pct": _normalize_money(discount_pct),
        "discount_total": _normalize_money(discount_total),
        "total": _normalize_money(total),
    }


def _timeline_event(event: str, note: str = "") -> dict[str, str]:
    return {
        "event": event,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _advance_next_run(current: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return current + timedelta(days=1)
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "monthly":
        return current + timedelta(days=30)
    if frequency == "quarterly":
        return current + timedelta(days=90)
    return current + timedelta(days=365)


async def _build_bill_document(user: User, payload: BillCreateRequest, source: str = "manual") -> dict[str, Any]:
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one line item is required")

    client = None
    customer_name = (payload.customer_name or "").strip()
    customer_email = (payload.customer_email or "").strip()
    if payload.client_id:
        client = await db.bill_generator_clients.find_one(
            {"client_id": payload.client_id, "user_id": user.user_id}, {"_id": 0}
        )
        if not client:
            raise HTTPException(status_code=404, detail="Selected client not found")
        customer_name = customer_name or str(client.get("name") or "")
        customer_email = customer_email or str(client.get("email") or "")

    if not customer_name:
        raise HTTPException(status_code=400, detail="Customer name is required")

    totals = _compute_totals(payload.items, payload.discount_pct)
    now = datetime.now(timezone.utc).isoformat()
    due_date = payload.due_date or (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

    return {
        "bill_id": f"bill_{uuid.uuid4().hex[:12]}",
        "bill_number": f"BL-{datetime.now(timezone.utc).strftime('%Y%m')}-{uuid.uuid4().hex[:5].upper()}",
        "user_id": user.user_id,
        "bill_type": payload.bill_type,
        "client_id": payload.client_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "currency": payload.currency.upper(),
        "items": totals["items"],
        "subtotal": totals["subtotal"],
        "tax_total": totals["tax_total"],
        "discount_pct": totals["discount_pct"],
        "discount_total": totals["discount_total"],
        "total": totals["total"],
        "status": "draft",
        "issue_date": payload.issue_date or now,
        "due_date": due_date,
        "notes": payload.notes,
        "ai_context": payload.ai_context,
        "recurring": bool(payload.recurring),
        "recurrence_frequency": payload.recurrence_frequency if payload.recurring else None,
        "source": source,
        "approval_required": True,
        "approval_status": "draft",
        "approval_submitted_at": None,
        "approved_by": None,
        "approved_at": None,
        "approval_note": "",
        "timeline": [_timeline_event("created", "Bill draft created")],
        "created_at": now,
        "updated_at": now,
    }


async def _build_reminders_preview(user_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    reminders = []
    bills = await db.bill_generator_bills.find(
        {"user_id": user_id, "status": {"$in": ["draft", "sent", "overdue"]}},
        {"_id": 0},
    ).to_list(800)

    for bill in bills:
        due_dt = _parse_iso(str(bill.get("due_date") or ""))
        if not due_dt:
            continue
        days = (due_dt.date() - now.date()).days
        if days > 5:
            continue
        reminder_type = "overdue" if days < 0 else ("due_today" if days == 0 else "due_soon")
        reminders.append(
            {
                "bill_id": bill.get("bill_id"),
                "bill_number": bill.get("bill_number"),
                "customer_name": bill.get("customer_name"),
                "status": bill.get("status"),
                "due_date": bill.get("due_date"),
                "days_to_due": days,
                "amount": bill.get("total"),
                "currency": bill.get("currency"),
                "reminder_type": reminder_type,
            }
        )

    reminders.sort(key=lambda row: row.get("days_to_due", 9999))
    return reminders[:30]


async def _build_client_insights(user_id: str) -> list[dict[str, Any]]:
    bills = await db.bill_generator_bills.find({"user_id": user_id}, {"_id": 0}).to_list(1200)
    grouped: dict[str, dict[str, Any]] = {}

    for bill in bills:
        name = str(bill.get("customer_name") or "Unknown").strip() or "Unknown"
        node = grouped.setdefault(
            name,
            {
                "customer_name": name,
                "bill_count": 0,
                "paid_count": 0,
                "overdue_count": 0,
                "total_billed": 0.0,
                "paid_total": 0.0,
                "overdue_total": 0.0,
                "avg_days_to_pay": 0.0,
                "on_time_rate": 0.0,
                "_days_paid": [],
                "_on_time_paid": 0,
            },
        )

        total = float(bill.get("total") or 0)
        node["bill_count"] += 1
        node["total_billed"] += total

        status = str(bill.get("status") or "draft")
        if status == "paid":
            node["paid_count"] += 1
            node["paid_total"] += total
            issue_dt = _parse_iso(str(bill.get("issue_date") or ""))
            paid_dt = _parse_iso(str(bill.get("paid_at") or bill.get("updated_at") or ""))
            due_dt = _parse_iso(str(bill.get("due_date") or ""))
            if issue_dt and paid_dt:
                days_to_pay = max(0, (paid_dt.date() - issue_dt.date()).days)
                node["_days_paid"].append(days_to_pay)
                if due_dt and paid_dt.date() <= due_dt.date():
                    node["_on_time_paid"] += 1
        if status == "overdue":
            node["overdue_count"] += 1
            node["overdue_total"] += total

    insights = []
    for node in grouped.values():
        days_paid = node.pop("_days_paid", [])
        on_time_paid = int(node.pop("_on_time_paid", 0))
        node["total_billed"] = _normalize_money(float(node.get("total_billed") or 0))
        node["paid_total"] = _normalize_money(float(node.get("paid_total") or 0))
        node["overdue_total"] = _normalize_money(float(node.get("overdue_total") or 0))
        node["avg_days_to_pay"] = _normalize_money(sum(days_paid) / max(1, len(days_paid)))
        node["on_time_rate"] = _normalize_money((on_time_paid / max(1, int(node.get("paid_count") or 0))) * 100.0)
        insights.append(node)

    insights.sort(key=lambda row: float(row.get("total_billed") or 0), reverse=True)
    return insights[:50]


def _default_channel_settings(user_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "settings_id": f"bg_channel_{user_id}",
        "user_id": user_id,
        "in_app_enabled": True,
        "email_enabled": True,
        "updated_at": now,
        "created_at": now,
    }


async def _get_channel_settings(user_id: str) -> dict[str, Any]:
    settings = await db.bill_generator_channel_settings.find_one({"user_id": user_id}, {"_id": 0})
    if settings:
        return settings
    defaults = _default_channel_settings(user_id)
    await db.bill_generator_channel_settings.insert_one(defaults)
    defaults.pop("_id", None)
    return defaults


async def _queue_in_app_reminder(user_id: str, bill: dict, tone: str, message: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    queue_item = {
        "queue_id": f"bg_reminder_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "bill_id": bill.get("bill_id"),
        "bill_number": bill.get("bill_number"),
        "customer_name": bill.get("customer_name"),
        "tone": tone,
        "message": message,
        "status": "queued",
        "created_at": now,
    }
    await db.bill_generator_reminder_queue.insert_one(queue_item)
    queue_item.pop("_id", None)
    return queue_item


async def _send_reminder_email(user_id: str, bill: dict, tone: str) -> dict[str, Any]:
    recipient = str(bill.get("customer_email") or "").strip()
    if not recipient:
        return {"success": False, "error": "missing customer email", "skipped": True}

    from utils.email_service import send_catalog_template, is_email_configured

    if not is_email_configured():
        return {"success": False, "error": "email service not configured", "skipped": True}

    due_dt = _parse_iso(str(bill.get("due_date") or ""))
    days_overdue = 0
    if due_dt:
        days_overdue = max(0, (datetime.now(timezone.utc).date() - due_dt.date()).days)
    if tone == "final":
        days_overdue = max(days_overdue, 14)
    elif tone == "firm":
        days_overdue = max(days_overdue, 7)
    else:
        days_overdue = max(days_overdue, 1)

    action_link = f"/features/bill-generator?bill={bill.get('bill_id')}"
    result = await send_catalog_template(
        recipient_email=recipient,
        template_key="invoice_past_due",
        user_name=str(bill.get("customer_name") or "there"),
        plan_name="Business Billing",
        amount=f"{bill.get('currency') or 'USD'} {float(bill.get('total') or 0):.2f}",
        days_overdue=int(days_overdue),
        update_url=action_link,
    )
    return result


async def _get_workspace_role(owner_user_id: str, actor_user: User) -> str:
    if actor_user.user_id == owner_user_id:
        return "owner"
    row = await db.bill_generator_workspace_members.find_one(
        {
            "owner_user_id": owner_user_id,
            "member_user_id": actor_user.user_id,
            "active": True,
        },
        {"_id": 0, "role": 1},
    )
    return str((row or {}).get("role") or "viewer")


def _has_workspace_permission(role: str, permission: str) -> bool:
    return permission in (WORKSPACE_ROLE_PERMISSIONS.get(role) or set())


async def _build_collections_dashboard(user_id: str) -> dict[str, Any]:
    bills = await db.bill_generator_bills.find({"user_id": user_id}, {"_id": 0}).to_list(1200)
    now = datetime.now(timezone.utc)

    aging_buckets = {
        "0_7": 0.0,
        "8_15": 0.0,
        "16_30": 0.0,
        "31_plus": 0.0,
    }
    actionable = []
    paid_last_30 = 0.0
    paid_count_last_30 = 0

    for bill in bills:
        status = str(bill.get("status") or "draft")
        total = float(bill.get("total") or 0)
        due_dt = _parse_iso(str(bill.get("due_date") or ""))

        if status == "paid":
            paid_dt = _parse_iso(str(bill.get("paid_at") or bill.get("updated_at") or ""))
            if paid_dt and (now - paid_dt).days <= 30:
                paid_last_30 += total
                paid_count_last_30 += 1

        if status in {"sent", "overdue", "draft"} and due_dt:
            days_overdue = max(0, (now.date() - due_dt.date()).days)
            if days_overdue <= 7:
                aging_buckets["0_7"] += total
            elif days_overdue <= 15:
                aging_buckets["8_15"] += total
            elif days_overdue <= 30:
                aging_buckets["16_30"] += total
            else:
                aging_buckets["31_plus"] += total

            actionable.append(
                {
                    "bill_id": bill.get("bill_id"),
                    "bill_number": bill.get("bill_number"),
                    "customer_name": bill.get("customer_name"),
                    "status": status,
                    "currency": bill.get("currency"),
                    "amount": _normalize_money(total),
                    "days_overdue": days_overdue,
                    "due_date": bill.get("due_date"),
                }
            )

    actionable.sort(key=lambda row: (-int(row.get("days_overdue") or 0), -float(row.get("amount") or 0)))
    forecast_14d = sum(
        float(row.get("amount") or 0)
        for row in actionable
        if int(row.get("days_overdue") or 0) <= 14
    )

    return {
        "aging_buckets": {k: _normalize_money(v) for k, v in aging_buckets.items()},
        "paid_velocity_30d": _normalize_money(paid_last_30 / 30.0),
        "paid_volume_30d": _normalize_money(paid_last_30),
        "paid_count_30d": int(paid_count_last_30),
        "forecast_cash_in_14d": _normalize_money(forecast_14d),
        "actionable_collections": actionable[:50],
    }


def _render_reminder_text(bill: dict, tone: str) -> str:
    due_date = str(bill.get("due_date") or "")[:10]
    amount = f"{bill.get('currency') or 'USD'} {float(bill.get('total') or 0):.2f}"
    customer = str(bill.get("customer_name") or "Customer")
    base_ref = str(bill.get("bill_number") or bill.get("bill_id") or "Bill")

    if tone == "firm":
        return (
            f"Hello {customer}, this is a firm reminder that bill {base_ref} for {amount} is pending. "
            f"Please complete payment by {due_date} to avoid service interruption."
        )
    if tone == "final":
        return (
            f"Final notice: bill {base_ref} for {amount} remains unpaid beyond the expected date ({due_date}). "
            "Please process payment immediately and share confirmation today."
        )
    return (
        f"Hi {customer}, quick reminder that bill {base_ref} for {amount} is due on {due_date}. "
        "Let us know once payment is scheduled. Thank you!"
    )


async def run_bill_generator_hourly_scheduler(triggered_by: str = "scheduler_hourly") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    hour_window = now.replace(minute=0, second=0, microsecond=0).isoformat()
    existing = await db.bill_generator_scheduler_runs.find_one(
        {"window": hour_window, "job": "bill_generator_hourly_scheduler", "status": "success"},
        {"_id": 0},
    )
    if existing:
        return {"status": "skipped", "reason": "already_executed_this_hour", "window": hour_window}

    due = await db.bill_generator_recurring_schedules.find(
        {"active": True, "next_run_at": {"$lte": now.isoformat()}},
        {"_id": 0},
    ).sort("next_run_at", 1).to_list(200)

    generated = 0
    failures = []
    for schedule in due:
        user_stub = type("BillUser", (), {"user_id": str(schedule.get("user_id") or "")})()
        if not getattr(user_stub, "user_id", ""):
            continue
        try:
            await _run_schedule_once(user_stub, schedule, source="recurring_hourly_daemon")
            generated += 1
        except Exception as exc:
            failures.append({"schedule_id": schedule.get("schedule_id"), "error": str(exc)[:180]})

    now_iso = datetime.now(timezone.utc).isoformat()
    run_doc = {
        "run_id": f"bg_scheduler_{uuid.uuid4().hex[:12]}",
        "job": "bill_generator_hourly_scheduler",
        "triggered_by": triggered_by,
        "window": hour_window,
        "generated": generated,
        "failed": len(failures),
        "failures": failures[:40],
        "status": "success",
        "created_at": now_iso,
    }
    await db.bill_generator_scheduler_runs.insert_one(run_doc)
    run_doc.pop("_id", None)
    return run_doc


async def _build_insights(user_id: str) -> dict[str, Any]:
    bills = await db.bill_generator_bills.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    month_bills = [b for b in bills if str(b.get("created_at") or "").startswith(current_month)]

    paid_total = sum(float(b.get("total") or 0) for b in bills if b.get("status") == "paid")
    outstanding_total = sum(float(b.get("total") or 0) for b in bills if b.get("status") in {"sent", "overdue"})

    status_counts = {
        "draft": len([b for b in bills if b.get("status") == "draft"]),
        "sent": len([b for b in bills if b.get("status") == "sent"]),
        "paid": len([b for b in bills if b.get("status") == "paid"]),
        "overdue": len([b for b in bills if b.get("status") == "overdue"]),
        "cancelled": len([b for b in bills if b.get("status") == "cancelled"]),
    }

    overdue = sorted(
        [b for b in bills if b.get("status") == "overdue"],
        key=lambda row: str(row.get("due_date") or ""),
    )[:6]

    return {
        "total_bills": len(bills),
        "current_month_bills": len(month_bills),
        "paid_total": _normalize_money(paid_total),
        "outstanding_total": _normalize_money(outstanding_total),
        "status_counts": status_counts,
        "overdue_preview": overdue,
    }


def _render_bill_pdf(bill: dict, client: dict | None):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    file_path = PDF_DIR / f"{bill['bill_id']}.pdf"
    c = canvas.Canvas(str(file_path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 40, "RealAICoach Bill Generator")
    c.setFont("Helvetica", 11)
    c.drawString(40, height - 70, f"Bill Number: {bill.get('bill_number')}")
    c.drawString(40, height - 90, f"Type: {str(bill.get('bill_type') or 'invoice').upper()}")
    c.drawString(40, height - 110, f"Issued: {str(bill.get('issue_date') or '')[:10]}")
    c.drawString(40, height - 130, f"Due: {str(bill.get('due_date') or '')[:10]}")

    if client:
        c.drawString(40, height - 160, f"Client: {client.get('name')}")
        c.drawString(40, height - 178, f"Email: {client.get('email') or '-'}")
    else:
        c.drawString(40, height - 160, f"Customer: {bill.get('customer_name') or '-'}")
        c.drawString(40, height - 178, f"Email: {bill.get('customer_email') or '-'}")

    y = height - 215
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(350, y, "Unit")
    c.drawString(420, y, "Tax")
    c.drawString(500, y, "Total")
    y -= 20
    c.setFont("Helvetica", 10)

    for item in bill.get("items", []):
        c.drawString(40, y, str(item.get("description") or "")[:42])
        c.drawString(300, y, str(item.get("quantity") or 0))
        c.drawString(350, y, f"{float(item.get('unit_price') or 0):.2f}")
        c.drawString(420, y, f"{float(item.get('tax_rate') or 0):.1f}%")
        c.drawString(500, y, f"{float(item.get('line_total') or 0):.2f}")
        y -= 16
        if y < 100:
            c.showPage()
            y = height - 80
            c.setFont("Helvetica", 10)

    c.setFont("Helvetica-Bold", 11)
    y -= 8
    c.drawString(350, y, "Subtotal:")
    c.drawString(500, y, f"{float(bill.get('subtotal') or 0):.2f}")
    y -= 16
    c.drawString(350, y, "Tax:")
    c.drawString(500, y, f"{float(bill.get('tax_total') or 0):.2f}")
    y -= 16
    c.drawString(350, y, "Discount:")
    c.drawString(500, y, f"-{float(bill.get('discount_total') or 0):.2f}")
    y -= 16
    c.drawString(350, y, f"Total ({bill.get('currency') or 'USD'}):")
    c.drawString(500, y, f"{float(bill.get('total') or 0):.2f}")
    c.save()

    raw = file_path.read_bytes()
    composed = compose_pdf_v15_helper_layout(
        raw,
        title="Bill Generator Document",
        subtitle="Enterprise billing package",
        right_primary=f"Bill: {bill.get('bill_number')}",
        right_secondary=f"Total {bill.get('currency')} {bill.get('total')}",
        badge_text="BILL GENERATOR",
        badge_status="PASS",
        footer_text="RealAICoach • Bill Generator",
        summary_title="Bill Summary",
        summary_rows=[
            ("Status", str(bill.get("status") or "draft").upper()),
            ("Line Items", str(len(bill.get("items") or []))),
            ("Due Date", str(bill.get("due_date") or "")[:10]),
        ],
        callout_title="Operations Context",
        callout_subtitle="Revenue-safe billing workflow",
        callout_detail="Document includes taxable line-level totals, lifecycle status, and plan-compliant generator traces.",
        callout_status="PASS",
    )
    themed, mode = enforce_pdf_v15_theme_bytes(composed)
    if mode in {"theme_passthrough_error", "non_pdf"}:
        raise HTTPException(status_code=500, detail="PDF export validation failed")
    file_path.write_bytes(themed)
    return file_path


@router.get("/health")
async def get_bill_generator_health():
    """Health check endpoint for Bill Generator feature."""
    return {
        "status": "healthy",
        "feature": "bill-generator",
        "feature_number": 19,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/bootstrap")
async def get_bill_generator_bootstrap(request: Request, fallback_user_id: str | None = Query(default=None)):
    """
    Bootstrap Bill Generator workspace.
    
    Supports:
    - Authenticated users (via session)
    - Guest users (via fallback_user_id query param with pattern: user_<12-80 chars>)
    """
    owner_id = await _resolve_owner_id(request, fallback_user_id)
    
    # Try to get authenticated user for plan resolution, fallback to free plan for guests
    try:
        user = await require_auth(request)
        plan = _resolve_plan(user)
    except Exception:
        # Guest mode: use free plan
        plan = "free"
    
    channel_settings = await _get_channel_settings(owner_id)
    workspace_settings = await db.bill_generator_workspace_settings.find_one({"owner_user_id": owner_id}, {"_id": 0})
    if not workspace_settings:
        workspace_settings = {
            "settings_id": f"bg_workspace_{owner_id}",
            "owner_user_id": owner_id,
            "approval_required_for_send": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.bill_generator_workspace_settings.insert_one(workspace_settings)
        workspace_settings.pop("_id", None)
    workspace_members = await db.bill_generator_workspace_members.find(
        {"owner_user_id": owner_id, "active": True},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)

    clients = await db.bill_generator_clients.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(300)
    bills = await db.bill_generator_bills.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(150)
    catalog_items = await db.bill_generator_catalog.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    recurring_schedules = await db.bill_generator_recurring_schedules.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(120)
    insights = await _build_insights(owner_id)
    reminders = await _build_reminders_preview(owner_id)
    client_insights = await _build_client_insights(owner_id)
    collections_dashboard = await _build_collections_dashboard(owner_id)

    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": {
            action: int((PLAN_ACTION_LIMITS.get(action) or {}).get(plan, 0))
            for action in PLAN_ACTION_LIMITS
        },
        "clients": clients,
        "bills": bills,
        "catalog_items": catalog_items,
        "recurring_schedules": recurring_schedules,
        "reminders": reminders,
        "client_insights": client_insights,
        "collections_dashboard": collections_dashboard,
        "channel_settings": channel_settings,
        "workspace_settings": workspace_settings,
        "workspace_members": workspace_members,
        "insights": insights,
    }


@router.post("/clients")
async def create_client(payload: ClientCreateRequest, request: Request):
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    client = {
        "client_id": f"bg_client_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "name": payload.name.strip(),
        "email": payload.email.strip(),
        "phone": payload.phone.strip(),
        "address": payload.address.strip(),
        "created_at": now,
        "updated_at": now,
    }
    await db.bill_generator_clients.insert_one(client)
    client.pop("_id", None)
    return {"client": client}


@router.get("/clients")
async def list_clients(request: Request):
    user = await require_auth(request)
    clients = await db.bill_generator_clients.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"clients": clients}


@router.post("/catalog/items")
async def create_catalog_item(payload: ProductCatalogRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "catalog_manage")
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "catalog_item_id": f"bg_catalog_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "unit_price": _normalize_money(payload.unit_price),
        "tax_rate": _normalize_money(payload.tax_rate),
        "unit": payload.unit.strip() or "item",
        "created_at": now,
        "updated_at": now,
    }
    await db.bill_generator_catalog.insert_one(item)
    item.pop("_id", None)
    await _log_usage(user.user_id, "catalog_manage", quota["plan"], {"catalog_item_id": item["catalog_item_id"]})
    return {"catalog_item": item}


@router.get("/catalog/items")
async def list_catalog_items(request: Request):
    user = await require_auth(request)
    items = await db.bill_generator_catalog.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(600)
    return {"catalog_items": items}


@router.post("/recurring-schedules")
async def create_recurring_schedule(payload: RecurringScheduleRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "create_schedule")

    if not payload.template.items:
        raise HTTPException(status_code=400, detail="Recurring schedule needs at least one template item")

    start_at = _parse_iso(payload.start_at) or datetime.now(timezone.utc)
    now = datetime.now(timezone.utc).isoformat()

    schedule = {
        "schedule_id": f"bg_schedule_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "schedule_name": payload.schedule_name.strip(),
        "frequency": payload.frequency,
        "active": True,
        "next_run_at": start_at.isoformat(),
        "last_run_at": None,
        "run_count": 0,
        "template": payload.template.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    await db.bill_generator_recurring_schedules.insert_one(schedule)
    schedule.pop("_id", None)
    await _log_usage(user.user_id, "create_schedule", quota["plan"], {"schedule_id": schedule["schedule_id"]})
    return {"schedule": schedule}


@router.get("/recurring-schedules")
async def list_recurring_schedules(request: Request):
    user = await require_auth(request)
    schedules = await db.bill_generator_recurring_schedules.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"recurring_schedules": schedules}


@router.post("/recurring-schedules/{schedule_id}/toggle")
async def toggle_recurring_schedule(schedule_id: str, payload: RecurringToggleRequest, request: Request):
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.bill_generator_recurring_schedules.update_one(
        {"schedule_id": schedule_id, "user_id": user.user_id},
        {"$set": {"active": bool(payload.active), "updated_at": now}},
    )
    updated = await db.bill_generator_recurring_schedules.find_one(
        {"schedule_id": schedule_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Recurring schedule not found")
    return {"schedule": updated}


async def _run_schedule_once(user: User, schedule: dict, source: str = "recurring") -> dict[str, Any]:
    try:
        template_payload = BillCreateRequest(**(schedule.get("template") or {}))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid recurring template: {exc}")

    bill = await _build_bill_document(user, template_payload, source=source)
    bill["recurring"] = True
    bill["recurrence_frequency"] = schedule.get("frequency")
    bill["recurring_schedule_id"] = schedule.get("schedule_id")
    bill["timeline"] = [_timeline_event("created", f"Generated from schedule {schedule.get('schedule_name')}")]
    await db.bill_generator_bills.insert_one(bill)
    bill.pop("_id", None)

    now_dt = datetime.now(timezone.utc)
    next_run_at = _advance_next_run(now_dt, str(schedule.get("frequency") or "monthly"))
    await db.bill_generator_recurring_schedules.update_one(
        {"schedule_id": schedule.get("schedule_id"), "user_id": user.user_id},
        {
            "$set": {"last_run_at": now_dt.isoformat(), "next_run_at": next_run_at.isoformat(), "updated_at": now_dt.isoformat()},
            "$inc": {"run_count": 1},
        },
    )
    return bill


@router.post("/recurring-schedules/{schedule_id}/run")
async def run_recurring_schedule(schedule_id: str, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "run_schedule")
    schedule = await db.bill_generator_recurring_schedules.find_one(
        {"schedule_id": schedule_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Recurring schedule not found")

    bill = await _run_schedule_once(user, schedule, source="recurring_manual_run")
    updated_schedule = await db.bill_generator_recurring_schedules.find_one(
        {"schedule_id": schedule_id, "user_id": user.user_id}, {"_id": 0}
    )
    await _log_usage(user.user_id, "run_schedule", quota["plan"], {"schedule_id": schedule_id, "bill_id": bill.get("bill_id")})
    return {"bill": bill, "schedule": updated_schedule}


@router.post("/recurring-schedules/run-due")
async def run_due_recurring_schedules(request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "run_schedule")
    now = datetime.now(timezone.utc).isoformat()
    due = await db.bill_generator_recurring_schedules.find(
        {"user_id": user.user_id, "active": True, "next_run_at": {"$lte": now}},
        {"_id": 0},
    ).sort("next_run_at", 1).to_list(8)

    generated = []
    for schedule in due:
        generated.append(await _run_schedule_once(user, schedule, source="recurring_due_run"))

    await _log_usage(user.user_id, "run_schedule", quota["plan"], {"generated_count": len(generated)})
    return {"generated_bills": generated, "generated_count": len(generated)}


@router.post("/ai-draft")
async def generate_bill_draft(payload: BillAIDraftRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "ai_draft")

    prompt = f"""Generate bill-ready line items and terms.
Client: {payload.client_name}
Industry: {payload.industry}
Scope: {payload.scope}
Target Budget: {payload.amount_target} {payload.currency}

Return ONLY valid JSON:
{{
  "recommended_bill_type": "invoice",
  "payment_terms": "Net 14",
  "notes": "short billing notes",
  "items": [
    {{"description": "", "quantity": 1, "unit_price": 0, "tax_rate": 0}}
  ]
}}
"""

    draft = await generate_verified_json(
        prompt,
        "You are an enterprise billing assistant. Generate practical, tax-aware bill line-items.",
        f"bill-draft-{user.user_id}-{uuid.uuid4().hex[:8]}",
    )

    items = []
    for row in (draft or {}).get("items") or []:
        try:
            items.append(
                {
                    "description": str(row.get("description") or "Service").strip()[:220],
                    "quantity": _normalize_money(float(row.get("quantity") or 1)),
                    "unit_price": _normalize_money(float(row.get("unit_price") or 0)),
                    "tax_rate": _normalize_money(float(row.get("tax_rate") or 0)),
                }
            )
        except Exception:
            continue

    if not items:
        items = [{"description": "Service", "quantity": 1.0, "unit_price": max(0.0, float(payload.amount_target or 0)), "tax_rate": 0.0}]

    await _log_usage(user.user_id, "ai_draft", quota["plan"], {"items_count": len(items)})

    return {
        "draft": {
            "recommended_bill_type": str((draft or {}).get("recommended_bill_type") or "invoice"),
            "payment_terms": str((draft or {}).get("payment_terms") or "Net 14"),
            "notes": str((draft or {}).get("notes") or ""),
            "items": items,
        },
        "plan": quota["plan"],
        "scope_label": quota["scope_label"],
        "daily_limit": quota["limit"],
    }


@router.post("/bills")
async def create_bill(payload: BillCreateRequest, request: Request):
    user = await require_auth(request)
    role = await _get_workspace_role(user.user_id, user)
    if not _has_workspace_permission(role, "create_bill"):
        raise HTTPException(status_code=403, detail="Permission denied to create bills")
    quota = await _enforce_action_limit(user, "create_bill")
    bill = await _build_bill_document(user, payload, source="manual")
    await db.bill_generator_bills.insert_one(bill)
    bill.pop("_id", None)
    await _log_usage(user.user_id, "create_bill", quota["plan"], {"bill_id": bill["bill_id"], "bill_type": bill["bill_type"]})
    return {"bill": bill}


@router.get("/bills")
async def list_bills(request: Request, status: str | None = None):
    user = await require_auth(request)
    query: dict[str, Any] = {"user_id": user.user_id}
    if status:
        query["status"] = status
    bills = await db.bill_generator_bills.find(query, {"_id": 0}).sort("created_at", -1).to_list(400)
    return {"bills": bills}


@router.get("/bills/{bill_id}")
async def get_bill(bill_id: str, request: Request):
    user = await require_auth(request)
    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return {"bill": bill}


@router.patch("/bills/{bill_id}/status")
async def update_bill_status(bill_id: str, payload: BillStatusUpdateRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "status_update")
    role = await _get_workspace_role(user.user_id, user)
    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if not _has_workspace_permission(role, "create_bill"):
        raise HTTPException(status_code=403, detail="Permission denied for bill status update")

    if payload.status == "sent":
        if not _has_workspace_permission(role, "send_bill"):
            raise HTTPException(status_code=403, detail="Permission denied to send bills")
        if bool(bill.get("approval_required", True)) and str(bill.get("approval_status") or "") != "approved":
            raise HTTPException(status_code=409, detail="Bill approval required before sending")

    now = datetime.now(timezone.utc).isoformat()
    timeline = list(bill.get("timeline") or [])
    timeline.append(_timeline_event(f"status:{payload.status}", payload.note or "Status changed"))

    updates: dict[str, Any] = {
        "status": payload.status,
        "timeline": timeline,
        "updated_at": now,
    }
    if payload.status == "paid":
        updates["paid_at"] = now

    await db.bill_generator_bills.update_one(
        {"bill_id": bill_id, "user_id": user.user_id},
        {"$set": updates},
    )
    updated = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    await _log_usage(user.user_id, "status_update", quota["plan"], {"bill_id": bill_id, "status": payload.status})
    return {"bill": updated}


@router.post("/bills/{bill_id}/duplicate")
async def duplicate_bill(bill_id: str, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "create_bill")
    source = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Bill not found")

    now = datetime.now(timezone.utc).isoformat()
    clone = {
        **source,
        "bill_id": f"bill_{uuid.uuid4().hex[:12]}",
        "bill_number": f"BL-{datetime.now(timezone.utc).strftime('%Y%m')}-{uuid.uuid4().hex[:5].upper()}",
        "status": "draft",
        "timeline": [_timeline_event("duplicated", f"Duplicated from {source.get('bill_number')}")],
        "created_at": now,
        "updated_at": now,
    }
    clone.pop("paid_at", None)
    await db.bill_generator_bills.insert_one(clone)
    clone.pop("_id", None)
    await _log_usage(user.user_id, "create_bill", quota["plan"], {"source_bill_id": bill_id, "new_bill_id": clone["bill_id"]})
    return {"bill": clone}


@router.get("/bills/{bill_id}/pdf")
async def download_bill_pdf(bill_id: str, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "pdf_export")
    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    client = None
    if bill.get("client_id"):
        client = await db.bill_generator_clients.find_one({"client_id": bill.get("client_id")}, {"_id": 0})

    file_path = _render_bill_pdf(bill, client)
    await _log_usage(user.user_id, "pdf_export", quota["plan"], {"bill_id": bill_id})
    return FileResponse(file_path, media_type="application/pdf", filename=build_pdf_v15_filename("bill", bill_id))


@router.get("/reminders")
async def get_bill_reminders(request: Request):
    user = await require_auth(request)
    reminders = await _build_reminders_preview(user.user_id)
    return {"reminders": reminders}


@router.post("/reminders/{bill_id}/message")
async def generate_reminder_message(bill_id: str, payload: ReminderMessageRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "reminder_message")
    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    text = _render_reminder_text(bill, payload.tone)

    await _log_usage(user.user_id, "reminder_message", quota["plan"], {"bill_id": bill_id, "tone": payload.tone})
    return {"message": text, "tone": payload.tone}


@router.get("/channels/settings")
async def get_channel_settings(request: Request):
    user = await require_auth(request)
    return {"settings": await _get_channel_settings(user.user_id)}


@router.post("/channels/settings")
async def update_channel_settings(payload: ChannelSettingsRequest, request: Request):
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.bill_generator_channel_settings.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "in_app_enabled": bool(payload.in_app_enabled),
                "email_enabled": bool(payload.email_enabled),
                "updated_at": now,
            },
            "$setOnInsert": {
                "settings_id": f"bg_channel_{user.user_id}",
                "created_at": now,
            },
        },
        upsert=True,
    )
    settings = await _get_channel_settings(user.user_id)
    return {"settings": settings}


@router.post("/reminders/{bill_id}/dispatch")
async def dispatch_single_reminder(bill_id: str, payload: ReminderDispatchRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "reminder_message")
    settings = await _get_channel_settings(user.user_id)

    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    message = _render_reminder_text(bill, payload.tone)
    dispatch = {
        "bill_id": bill_id,
        "tone": payload.tone,
        "in_app": {"queued": False},
        "email": {"sent": False, "skipped": False},
    }

    if payload.channel_in_app and settings.get("in_app_enabled", True):
        queue_item = await _queue_in_app_reminder(user.user_id, bill, payload.tone, message)
        dispatch["in_app"] = {"queued": True, "queue_id": queue_item.get("queue_id")}

    if payload.channel_email and settings.get("email_enabled", False):
        try:
            email_result = await _send_reminder_email(user.user_id, bill, payload.tone)
        except Exception as exc:
            email_result = {"success": False, "error": str(exc)[:180], "skipped": False}
        dispatch["email"] = {
            "sent": bool(email_result.get("success")),
            "skipped": bool(email_result.get("skipped")),
            "error": email_result.get("error"),
        }

    await _log_usage(user.user_id, "reminder_message", quota["plan"], {"bill_id": bill_id, "tone": payload.tone})
    return {"dispatch": dispatch, "message": message}


@router.post("/collections/bulk-reminders")
async def dispatch_bulk_reminders(payload: BulkReminderRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "reminder_message")
    settings = await _get_channel_settings(user.user_id)

    query: dict[str, Any] = {"user_id": user.user_id, "status": {"$in": ["draft", "sent", "overdue"]}}
    if payload.bill_ids:
        query["bill_id"] = {"$in": [str(bid) for bid in payload.bill_ids if str(bid).strip()]}

    bills = await db.bill_generator_bills.find(query, {"_id": 0}).sort("due_date", 1).to_list(200)
    sent = 0
    queued = 0
    failures = []

    for bill in bills:
        try:
            message = _render_reminder_text(bill, payload.tone)
            if payload.channel_in_app and settings.get("in_app_enabled", True):
                await _queue_in_app_reminder(user.user_id, bill, payload.tone, message)
                queued += 1
            if payload.channel_email and settings.get("email_enabled", False):
                try:
                    email_result = await _send_reminder_email(user.user_id, bill, payload.tone)
                except Exception as exc:
                    email_result = {"success": False, "error": str(exc)[:180]}
                if email_result.get("success"):
                    sent += 1
            await _log_usage(user.user_id, "reminder_message", quota["plan"], {"bill_id": bill.get("bill_id"), "tone": payload.tone})
        except Exception as exc:
            failures.append({"bill_id": bill.get("bill_id"), "error": str(exc)[:160]})

    return {
        "processed": len(bills),
        "in_app_queued": queued,
        "email_sent": sent,
        "failures": failures[:30],
    }


@router.get("/collections/dashboard")
async def get_collections_dashboard(request: Request):
    user = await require_auth(request)
    dashboard = await _build_collections_dashboard(user.user_id)
    return {"dashboard": dashboard}


@router.get("/workspace/members")
async def list_workspace_members(request: Request):
    user = await require_auth(request)
    members = await db.bill_generator_workspace_members.find(
        {"owner_user_id": user.user_id, "active": True},
        {"_id": 0},
    ).sort("created_at", -1).to_list(300)
    return {"members": members}


@router.post("/workspace/members")
async def add_workspace_member(payload: WorkspaceMemberRequest, request: Request):
    user = await require_auth(request)
    if payload.role == "owner":
        raise HTTPException(status_code=400, detail="Owner role cannot be assigned via invite")

    target_email = payload.email.strip().lower()
    target_user = await db.users.find_one({"email": target_email}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    now = datetime.now(timezone.utc).isoformat()
    member = {
        "member_id": f"bg_member_{uuid.uuid4().hex[:12]}",
        "owner_user_id": user.user_id,
        "member_user_id": target_user.get("user_id"),
        "member_email": target_email,
        "member_name": target_user.get("name") or "",
        "role": payload.role,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.bill_generator_workspace_members.update_one(
        {"owner_user_id": user.user_id, "member_user_id": target_user.get("user_id")},
        {
            "$set": {
                "owner_user_id": user.user_id,
                "member_user_id": target_user.get("user_id"),
                "member_email": target_email,
                "member_name": target_user.get("name") or "",
                "role": payload.role,
                "active": True,
                "updated_at": now,
            },
            "$setOnInsert": {
                "member_id": member["member_id"],
                "created_at": now,
            },
        },
        upsert=True,
    )
    saved = await db.bill_generator_workspace_members.find_one(
        {"owner_user_id": user.user_id, "member_user_id": target_user.get("user_id")},
        {"_id": 0},
    )
    return {"member": saved}


@router.patch("/workspace/members/{member_user_id}")
async def update_workspace_member_role(member_user_id: str, payload: WorkspaceRoleUpdateRequest, request: Request):
    user = await require_auth(request)
    await db.bill_generator_workspace_members.update_one(
        {"owner_user_id": user.user_id, "member_user_id": member_user_id, "active": True},
        {"$set": {"role": payload.role, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await db.bill_generator_workspace_members.find_one(
        {"owner_user_id": user.user_id, "member_user_id": member_user_id, "active": True},
        {"_id": 0},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Workspace member not found")
    return {"member": updated}


@router.get("/workflow/settings")
async def get_workflow_settings(request: Request):
    user = await require_auth(request)
    settings = await db.bill_generator_workspace_settings.find_one({"owner_user_id": user.user_id}, {"_id": 0})
    if not settings:
        settings = {
            "settings_id": f"bg_workspace_{user.user_id}",
            "owner_user_id": user.user_id,
            "approval_required_for_send": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.bill_generator_workspace_settings.insert_one(settings)
        settings.pop("_id", None)
    return {"settings": settings}


@router.post("/workflow/settings")
async def update_workflow_settings(payload: WorkflowSettingsRequest, request: Request):
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.bill_generator_workspace_settings.update_one(
        {"owner_user_id": user.user_id},
        {
            "$set": {
                "approval_required_for_send": bool(payload.approval_required_for_send),
                "updated_at": now,
            },
            "$setOnInsert": {
                "settings_id": f"bg_workspace_{user.user_id}",
                "owner_user_id": user.user_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    settings = await db.bill_generator_workspace_settings.find_one({"owner_user_id": user.user_id}, {"_id": 0})
    return {"settings": settings}


@router.post("/workflow/{bill_id}/submit")
async def submit_bill_for_approval(bill_id: str, payload: WorkflowDecisionRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "approval_action")
    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    timeline = list(bill.get("timeline") or [])
    timeline.append(_timeline_event("approval:submitted", payload.note or "Submitted for approval"))
    await db.bill_generator_bills.update_one(
        {"bill_id": bill_id, "user_id": user.user_id},
        {
            "$set": {
                "approval_status": "pending",
                "approval_submitted_at": datetime.now(timezone.utc).isoformat(),
                "approval_note": payload.note or "",
                "timeline": timeline,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await _log_usage(user.user_id, "approval_action", quota["plan"], {"bill_id": bill_id, "action": "submit"})
    updated = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    return {"bill": updated}


@router.post("/workflow/{bill_id}/approve")
async def approve_bill_workflow(bill_id: str, payload: WorkflowDecisionRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "approval_action")
    role = await _get_workspace_role(user.user_id, user)
    if not _has_workspace_permission(role, "approve_bill"):
        raise HTTPException(status_code=403, detail="Permission denied for approval action")

    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    timeline = list(bill.get("timeline") or [])
    timeline.append(_timeline_event("approval:approved", payload.note or "Approved"))
    await db.bill_generator_bills.update_one(
        {"bill_id": bill_id, "user_id": user.user_id},
        {
            "$set": {
                "approval_status": "approved",
                "approved_by": user.user_id,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "approval_note": payload.note or "",
                "timeline": timeline,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await _log_usage(user.user_id, "approval_action", quota["plan"], {"bill_id": bill_id, "action": "approve"})
    updated = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    return {"bill": updated}


@router.post("/workflow/{bill_id}/reject")
async def reject_bill_workflow(bill_id: str, payload: WorkflowDecisionRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "approval_action")
    role = await _get_workspace_role(user.user_id, user)
    if not _has_workspace_permission(role, "approve_bill"):
        raise HTTPException(status_code=403, detail="Permission denied for rejection action")

    bill = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    timeline = list(bill.get("timeline") or [])
    timeline.append(_timeline_event("approval:rejected", payload.note or "Rejected"))
    await db.bill_generator_bills.update_one(
        {"bill_id": bill_id, "user_id": user.user_id},
        {
            "$set": {
                "approval_status": "rejected",
                "rejected_by": user.user_id,
                "rejected_at": datetime.now(timezone.utc).isoformat(),
                "approval_note": payload.note or "",
                "timeline": timeline,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await _log_usage(user.user_id, "approval_action", quota["plan"], {"bill_id": bill_id, "action": "reject"})
    updated = await db.bill_generator_bills.find_one({"bill_id": bill_id, "user_id": user.user_id}, {"_id": 0})
    return {"bill": updated}


@router.get("/export")
async def export_bill_generator_data(
    request: Request,
    format: str = Query(default="payload", pattern="^(payload|json|csv)$"),
    fallback_user_id: str | None = Query(default=None),
):
    """
    Export Bill Generator data in multiple formats.
    
    Supported formats:
    - payload: Full nested structure with all relationships
    - json: Simplified JSON format for external systems
    - csv: Flat CSV format for spreadsheet import
    
    Supports authenticated users + guest mode.
    """
    owner_id = await _resolve_owner_id(request, fallback_user_id)
    
    bills = await db.bill_generator_bills.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    clients = await db.bill_generator_clients.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    catalog_items = await db.bill_generator_catalog.find({"user_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    if format == "payload":
        return {
            "export_format": "payload",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "owner_id": owner_id,
            "bills": bills,
            "clients": clients,
            "catalog_items": catalog_items,
            "total_bills": len(bills),
            "total_clients": len(clients),
            "total_catalog_items": len(catalog_items),
        }
    
    elif format == "json":
        simplified_bills = [
            {
                "bill_id": b.get("bill_id"),
                "bill_number": b.get("bill_number"),
                "customer_name": b.get("customer_name"),
                "customer_email": b.get("customer_email"),
                "status": b.get("status"),
                "currency": b.get("currency"),
                "total": b.get("total"),
                "due_date": b.get("due_date"),
                "created_at": b.get("created_at"),
            }
            for b in bills
        ]
        return {
            "export_format": "json",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bills": simplified_bills,
        }
    
    else:  # csv
        import io
        import csv
        from fastapi.responses import StreamingResponse
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["bill_id", "bill_number", "customer_name", "customer_email", "status", "currency", "total", "due_date", "created_at"])
        
        for b in bills:
            writer.writerow([
                b.get("bill_id", ""),
                b.get("bill_number", ""),
                b.get("customer_name", ""),
                b.get("customer_email", ""),
                b.get("status", ""),
                b.get("currency", ""),
                b.get("total", 0),
                b.get("due_date", ""),
                b.get("created_at", ""),
            ])
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=bill_generator_export_{owner_id}.csv"}
        )

@router.post("/admin/run-hourly-daemon")
async def run_hourly_daemon_manual(request: Request):
    user = await require_auth(request)
    plan = _resolve_plan(user)
    if plan != "premium":
        raise HTTPException(status_code=403, detail="Only premium/admin context can trigger daemon manually")
    summary = await run_bill_generator_hourly_scheduler(triggered_by=f"manual:{user.user_id}")
    return {"summary": summary}


@router.get("/client-insights")
async def get_client_insights(request: Request):
    user = await require_auth(request)
    insights = await _build_client_insights(user.user_id)
    return {"client_insights": insights}


@router.get("/insights")
async def get_bill_insights(request: Request):
    user = await require_auth(request)
    insights = await _build_insights(user.user_id)
    recurring_active = await db.bill_generator_recurring_schedules.count_documents({"user_id": user.user_id, "active": True})
    reminders_open = len(await _build_reminders_preview(user.user_id))
    insights["recurring_active"] = int(recurring_active)
    insights["reminders_open"] = int(reminders_open)
    return {"insights": insights}
