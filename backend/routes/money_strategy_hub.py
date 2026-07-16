"""Money Strategy Hub - Enterprise-grade personal finance operating system.

Feature 9 rebuild scope:
- Budget planning and tracking
- Expense ledger + analytics
- Savings goals
- Bill reminders
- Portfolio positions + analytics
- Receipt scan (AI extraction)
- AI money strategy advisor
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

from .db import db, get_current_user


logger = logging.getLogger("routes.money_strategy_hub")
router = APIRouter(prefix="/money-strategy-hub", tags=["money-strategy-hub"])
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")


TIER_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "budgets_per_month": 3,
        "expenses_per_day": 40,
        "savings_goals_per_month": 2,
        "bill_reminders_active": 5,
        "portfolio_positions": 10,
        "receipt_scans_per_month": 10,
        "advisor_runs_per_month": 10,
        "features": ["budgeting", "expense_tracking", "basic_savings"],
    },
    "basic": {
        "budgets_per_month": 20,
        "expenses_per_day": 250,
        "savings_goals_per_month": 12,
        "bill_reminders_active": 40,
        "portfolio_positions": 80,
        "receipt_scans_per_month": 120,
        "advisor_runs_per_month": 120,
        "features": ["cashflow_analytics", "bill_reminders", "portfolio_tracking", "ocr_receipts"],
    },
    "premium": {
        "budgets_per_month": -1,
        "expenses_per_day": -1,
        "savings_goals_per_month": -1,
        "bill_reminders_active": -1,
        "portfolio_positions": -1,
        "receipt_scans_per_month": -1,
        "advisor_runs_per_month": -1,
        "features": ["unlimited_planning", "ai_money_advisor", "advanced_insights", "investment_strategy"],
    },
}


class MoneyProfileRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    currency: str = "USD"
    monthly_income: float = 0.0
    fixed_monthly_expenses: float = 0.0
    savings_target_monthly: float = 0.0
    risk_tolerance: str = "moderate"  # conservative, moderate, aggressive
    investment_horizon_years: int = 3
    financial_goals: List[str] = []


class MoneyProfileUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    currency: Optional[str] = None
    monthly_income: Optional[float] = None
    fixed_monthly_expenses: Optional[float] = None
    savings_target_monthly: Optional[float] = None
    risk_tolerance: Optional[str] = None
    investment_horizon_years: Optional[int] = None
    financial_goals: Optional[List[str]] = None


class BudgetCreateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    name: str
    category: str
    monthly_limit: float
    alert_threshold_pct: float = 80.0
    notes: Optional[str] = None


class BudgetUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    monthly_limit: Optional[float] = None
    alert_threshold_pct: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ExpenseCreateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    amount: float
    category: str
    merchant: Optional[str] = None
    budget_id: Optional[str] = None
    currency: str = "USD"
    transaction_date: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"
    receipt_scan_id: Optional[str] = None


class SavingsGoalCreateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    title: str
    target_amount: float
    current_amount: float = 0.0
    deadline: Optional[str] = None
    priority: str = "medium"


class SavingsGoalUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    title: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class BillReminderCreateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    title: str
    amount_due: float
    due_date: str
    category: str = "general"
    autopay_enabled: bool = False
    notes: Optional[str] = None


class BillReminderUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    title: Optional[str] = None
    amount_due: Optional[float] = None
    due_date: Optional[str] = None
    category: Optional[str] = None
    autopay_enabled: Optional[bool] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # upcoming, paid, skipped


class PortfolioPositionCreateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    asset_type: str  # stock, crypto, etf, mutual_fund, bond
    symbol: str
    quantity: float
    average_cost: float
    current_price: float
    currency: str = "USD"
    notes: Optional[str] = None


class PortfolioPositionUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    asset_type: Optional[str] = None
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    average_cost: Optional[float] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None


class ReceiptScanRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    image_base64: str
    notes: Optional[str] = None


class AdvisorRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    question: Optional[str] = None
    planning_horizon_months: int = 6
    include_investment: bool = True


def _resolve_owner_id(user: Optional[dict], fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "money_strategy_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "money_strategy_auth_required",
            "message": "Login required or provide fallback_user_id for guest workspace",
        },
    )


async def _get_user_tier(owner_id: str) -> str:
    user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")
    if not user_id:
        return "free"

    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _day_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _to_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _extract_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _limit_reached_error(error_code: str, message: str, tier: str, used: int, limit: Any) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error_code": error_code,
            "message": message,
            "upgrade_prompt": True,
            "current_tier": tier,
            "used": used,
            "limit": limit,
        },
    )


async def _check_monthly_limit(
    collection_name: str,
    owner_id: str,
    field_name: str,
    limit: int,
) -> Dict[str, Any]:
    since = _month_start_iso()
    used = await db[collection_name].count_documents({"owner_id": owner_id, field_name: {"$gte": since}})
    return {
        "can_proceed": limit == -1 or used < limit,
        "used": used,
        "limit": "unlimited" if limit == -1 else limit,
    }


async def _check_daily_limit(
    collection_name: str,
    owner_id: str,
    field_name: str,
    limit: int,
) -> Dict[str, Any]:
    since = _day_start_iso()
    used = await db[collection_name].count_documents({"owner_id": owner_id, field_name: {"$gte": since}})
    return {
        "can_proceed": limit == -1 or used < limit,
        "used": used,
        "limit": "unlimited" if limit == -1 else limit,
    }


async def _generate_receipt_extraction(image_base64: str) -> Dict[str, Any]:
    fallback = {
        "merchant": "Unknown merchant",
        "total_amount": 0,
        "currency": "USD",
        "transaction_date": _now_iso()[:10],
        "category_suggestion": "general",
        "payment_method": "card",
        "confidence": 0.3,
        "line_items": [],
    }

    if not EMERGENT_KEY:
        return fallback

    prompt = """Extract receipt data. Return JSON only:
{
  "merchant": "string",
  "total_amount": number,
  "currency": "USD",
  "transaction_date": "YYYY-MM-DD",
  "category_suggestion": "food|transport|shopping|housing|utilities|health|entertainment|general",
  "payment_method": "cash|card|upi|bank_transfer|unknown",
  "confidence": number,
  "line_items": [{"name": "string", "amount": number}]
}
If unknown, use sensible defaults without nulls."""

    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"money-receipt-{uuid.uuid4().hex[:10]}",
                system_message="You are a receipt OCR extraction assistant. Return strict JSON only.",
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_base64)])
        )
        parsed = _extract_json_payload(response)
        if not parsed:
            return fallback
        return {
            "merchant": str(parsed.get("merchant") or fallback["merchant"]),
            "total_amount": _to_float(parsed.get("total_amount"), 0.0),
            "currency": str(parsed.get("currency") or "USD").upper(),
            "transaction_date": str(parsed.get("transaction_date") or fallback["transaction_date"]),
            "category_suggestion": str(parsed.get("category_suggestion") or "general").lower(),
            "payment_method": str(parsed.get("payment_method") or "unknown").lower(),
            "confidence": max(0.0, min(1.0, _to_float(parsed.get("confidence"), 0.3))),
            "line_items": parsed.get("line_items") if isinstance(parsed.get("line_items"), list) else [],
        }
    except Exception as exc:
        logger.warning("money_strategy_hub receipt extraction fallback: %s", exc)
        return fallback


async def _generate_ai_advice(context: Dict[str, Any], question: str, planning_horizon: int, include_investment: bool) -> Dict[str, Any]:
    fallback = {
        "summary": "Focus on consistent saving, tighter discretionary spending, and emergency fund discipline.",
        "risk_score": 50,
        "monthly_action_plan": [
            "Set one budget cap for top overspend category.",
            "Automate transfer to savings on salary day.",
            "Review recurring subscriptions and cut low-value ones.",
        ],
        "savings_moves": ["Use 50/30/20 baseline and raise savings by 5% over 3 months."],
        "debt_moves": ["Pay highest-interest debt first while maintaining minimums elsewhere."],
        "investment_notes": ["Diversify gradually and avoid concentrated risk."],
        "warnings": ["This is educational guidance, not regulated financial advice."],
    }

    if not EMERGENT_KEY:
        return fallback

    prompt = f"""You are an enterprise personal finance strategist.
User question: {question or 'Generate a proactive strategy for better financial health.'}
Planning horizon (months): {planning_horizon}
Include investment ideas: {include_investment}

Context JSON:
{json.dumps(context, default=str)}

Return STRICT JSON only:
{{
  "summary": "short executive summary",
  "risk_score": number,
  "monthly_action_plan": ["action1", "action2", "action3"],
  "savings_moves": ["move1", "move2"],
  "debt_moves": ["move1", "move2"],
  "investment_notes": ["note1", "note2"],
  "warnings": ["warning1", "warning2"]
}}
"""

    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"money-advisor-{uuid.uuid4().hex[:10]}",
                system_message="Return practical, structured, conservative financial guidance in JSON.",
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(UserMessage(text=prompt))
        parsed = _extract_json_payload(response)
        if not parsed:
            return fallback
        return {
            "summary": str(parsed.get("summary") or fallback["summary"]),
            "risk_score": int(max(0, min(100, _to_float(parsed.get("risk_score"), 50)))),
            "monthly_action_plan": parsed.get("monthly_action_plan") if isinstance(parsed.get("monthly_action_plan"), list) else fallback["monthly_action_plan"],
            "savings_moves": parsed.get("savings_moves") if isinstance(parsed.get("savings_moves"), list) else fallback["savings_moves"],
            "debt_moves": parsed.get("debt_moves") if isinstance(parsed.get("debt_moves"), list) else fallback["debt_moves"],
            "investment_notes": parsed.get("investment_notes") if isinstance(parsed.get("investment_notes"), list) else fallback["investment_notes"],
            "warnings": parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else fallback["warnings"],
        }
    except Exception as exc:
        logger.warning("money_strategy_hub ai advisor fallback: %s", exc)
        return fallback


@router.get("/bootstrap")
async def money_strategy_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)

    month_start = _month_start_iso()
    day_start = _day_start_iso()

    budgets_this_month = await db.money_budgets.count_documents({"owner_id": owner_id, "created_at": {"$gte": month_start}})
    expenses_today = await db.money_expenses.count_documents({"owner_id": owner_id, "created_at": {"$gte": day_start}})
    goals_this_month = await db.money_savings_goals.count_documents({"owner_id": owner_id, "created_at": {"$gte": month_start}})
    receipt_scans_this_month = await db.money_receipt_scans.count_documents({"owner_id": owner_id, "created_at": {"$gte": month_start}})
    advisor_runs_this_month = await db.money_ai_advice_runs.count_documents({"owner_id": owner_id, "created_at": {"$gte": month_start}})
    active_goals = await db.money_savings_goals.count_documents({"owner_id": owner_id, "status": "active"})
    active_bill_reminders = await db.money_bill_reminders.count_documents({"owner_id": owner_id, "status": "upcoming"})
    portfolio_positions = await db.money_portfolio_positions.count_documents({"owner_id": owner_id, "status": "active"})

    return {
        "owner_id": owner_id,
        "tier": tier,
        "usage": {
            "budgets_this_month": budgets_this_month,
            "expenses_today": expenses_today,
            "goals_this_month": goals_this_month,
            "receipt_scans_this_month": receipt_scans_this_month,
            "advisor_runs_this_month": advisor_runs_this_month,
        },
        "active": {
            "goals": active_goals,
            "bill_reminders": active_bill_reminders,
            "portfolio_positions": portfolio_positions,
        },
        "features": TIER_LIMITS[tier]["features"],
        "tier_limits": TIER_LIMITS[tier],
    }


@router.post("/profile")
async def upsert_money_profile(payload: MoneyProfileRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    existing = await db.money_profiles.find_one({"owner_id": owner_id}, {"_id": 0, "created_at": 1})
    profile_doc = {
        "owner_id": owner_id,
        "currency": payload.currency.upper(),
        "monthly_income": max(0.0, _to_float(payload.monthly_income)),
        "fixed_monthly_expenses": max(0.0, _to_float(payload.fixed_monthly_expenses)),
        "savings_target_monthly": max(0.0, _to_float(payload.savings_target_monthly)),
        "risk_tolerance": str(payload.risk_tolerance or "moderate").lower(),
        "investment_horizon_years": max(1, int(payload.investment_horizon_years)),
        "financial_goals": payload.financial_goals,
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }

    await db.money_profiles.update_one({"owner_id": owner_id}, {"$set": profile_doc}, upsert=True)
    return {"message": "Profile saved", "profile": profile_doc}


@router.get("/profile")
async def get_money_profile(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    profile = await db.money_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    return {"has_profile": bool(profile), "profile": profile}


@router.put("/profile")
async def update_money_profile(payload: MoneyProfileUpdateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    updates = payload.model_dump(exclude_none=True, exclude={"fallback_user_id"})
    if not updates:
        raise HTTPException(status_code=400, detail="No profile fields provided")

    if "currency" in updates:
        updates["currency"] = str(updates["currency"]).upper()
    if "risk_tolerance" in updates:
        updates["risk_tolerance"] = str(updates["risk_tolerance"]).lower()
    if "investment_horizon_years" in updates:
        updates["investment_horizon_years"] = max(1, int(updates["investment_horizon_years"]))
    for numeric_key in ("monthly_income", "fixed_monthly_expenses", "savings_target_monthly"):
        if numeric_key in updates:
            updates[numeric_key] = max(0.0, _to_float(updates[numeric_key]))

    updates["updated_at"] = _now_iso()
    result = await db.money_profiles.update_one({"owner_id": owner_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = await db.money_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    return {"message": "Profile updated", "profile": profile}


@router.post("/budgets")
async def create_budget(payload: BudgetCreateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    if payload.monthly_limit <= 0:
        raise HTTPException(status_code=400, detail="monthly_limit must be greater than 0")

    usage = await _check_monthly_limit(
        "money_budgets",
        owner_id,
        "created_at",
        TIER_LIMITS[tier]["budgets_per_month"],
    )
    if not usage["can_proceed"]:
        raise _limit_reached_error(
            "money_budget_limit_reached",
            f"Monthly budget creation limit reached ({usage['limit']} for {tier}).",
            tier,
            usage["used"],
            usage["limit"],
        )

    now = _now_iso()
    budget = {
        "budget_id": f"bgt_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "name": payload.name,
        "category": payload.category.lower(),
        "monthly_limit": round(_to_float(payload.monthly_limit), 2),
        "alert_threshold_pct": max(1.0, min(100.0, _to_float(payload.alert_threshold_pct, 80.0))),
        "spent_amount": 0.0,
        "remaining_amount": round(_to_float(payload.monthly_limit), 2),
        "notes": payload.notes,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.money_budgets.insert_one(budget)
    budget.pop("_id", None)
    return {"budget": budget}


@router.get("/budgets")
async def list_budgets(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = Query(default="active"),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if status != "all":
        query["status"] = status

    budgets = await db.money_budgets.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"count": len(budgets), "budgets": budgets}


@router.put("/budgets/{budget_id}")
async def update_budget(budget_id: str, payload: BudgetUpdateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    updates = payload.model_dump(exclude_none=True, exclude={"fallback_user_id"})
    if not updates:
        raise HTTPException(status_code=400, detail="No budget fields provided")

    if "monthly_limit" in updates:
        if _to_float(updates["monthly_limit"]) <= 0:
            raise HTTPException(status_code=400, detail="monthly_limit must be greater than 0")
        updates["monthly_limit"] = round(_to_float(updates["monthly_limit"]), 2)
    if "alert_threshold_pct" in updates:
        updates["alert_threshold_pct"] = max(1.0, min(100.0, _to_float(updates["alert_threshold_pct"])))
    if "category" in updates:
        updates["category"] = str(updates["category"]).lower()

    updates["updated_at"] = _now_iso()

    current = await db.money_budgets.find_one(
        {"budget_id": budget_id, "owner_id": owner_id},
        {"_id": 0, "spent_amount": 1, "monthly_limit": 1},
    )
    if not current:
        raise HTTPException(status_code=404, detail="Budget not found")

    if "monthly_limit" in updates:
        spent = _to_float(current.get("spent_amount"), 0.0)
        updates["remaining_amount"] = round(updates["monthly_limit"] - spent, 2)

    result = await db.money_budgets.update_one({"budget_id": budget_id, "owner_id": owner_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")

    budget = await db.money_budgets.find_one({"budget_id": budget_id, "owner_id": owner_id}, {"_id": 0})
    return {"message": "Budget updated", "budget": budget}


@router.delete("/budgets/{budget_id}")
async def archive_budget(budget_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    result = await db.money_budgets.update_one(
        {"budget_id": budget_id, "owner_id": owner_id},
        {"$set": {"status": "archived", "updated_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"success": True, "budget_id": budget_id}


@router.post("/expenses")
async def create_expense(payload: ExpenseCreateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")

    usage = await _check_daily_limit(
        "money_expenses",
        owner_id,
        "created_at",
        TIER_LIMITS[tier]["expenses_per_day"],
    )
    if not usage["can_proceed"]:
        raise _limit_reached_error(
            "money_expense_limit_reached",
            f"Daily expense logging limit reached ({usage['limit']} for {tier}).",
            tier,
            usage["used"],
            usage["limit"],
        )

    now = _now_iso()
    expense = {
        "expense_id": f"exp_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "amount": round(_to_float(payload.amount), 2),
        "category": payload.category.lower(),
        "merchant": payload.merchant or "Unknown",
        "budget_id": payload.budget_id,
        "currency": payload.currency.upper(),
        "transaction_date": payload.transaction_date or now,
        "payment_method": payload.payment_method or "unknown",
        "notes": payload.notes,
        "source": payload.source,
        "receipt_scan_id": payload.receipt_scan_id,
        "created_at": now,
    }
    await db.money_expenses.insert_one(expense)
    expense.pop("_id", None)

    if payload.budget_id:
        budget = await db.money_budgets.find_one(
            {"budget_id": payload.budget_id, "owner_id": owner_id, "status": "active"},
            {"_id": 0, "spent_amount": 1, "monthly_limit": 1},
        )
        if budget:
            new_spent = round(_to_float(budget.get("spent_amount"), 0.0) + expense["amount"], 2)
            monthly_limit = round(_to_float(budget.get("monthly_limit"), 0.0), 2)
            await db.money_budgets.update_one(
                {"budget_id": payload.budget_id, "owner_id": owner_id},
                {
                    "$set": {
                        "spent_amount": new_spent,
                        "remaining_amount": round(monthly_limit - new_spent, 2),
                        "updated_at": now,
                    }
                },
            )

    return {"expense": expense}


@router.get("/expenses")
async def list_expenses(
    request: Request,
    fallback_user_id: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if category:
        query["category"] = category.lower()

    if start_date or end_date:
        date_query: Dict[str, Any] = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
        query["transaction_date"] = date_query

    expenses = await db.money_expenses.find(query, {"_id": 0}).sort("transaction_date", -1).to_list(limit)
    total_spent = round(sum(_to_float(item.get("amount"), 0.0) for item in expenses), 2)
    return {"count": len(expenses), "total_spent": total_spent, "expenses": expenses}


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    expense = await db.money_expenses.find_one(
        {"expense_id": expense_id, "owner_id": owner_id},
        {"_id": 0, "budget_id": 1, "amount": 1},
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    await db.money_expenses.delete_one({"expense_id": expense_id, "owner_id": owner_id})

    budget_id = expense.get("budget_id")
    if budget_id:
        budget = await db.money_budgets.find_one(
            {"budget_id": budget_id, "owner_id": owner_id},
            {"_id": 0, "spent_amount": 1, "monthly_limit": 1},
        )
        if budget:
            new_spent = round(max(0.0, _to_float(budget.get("spent_amount"), 0.0) - _to_float(expense.get("amount"), 0.0)), 2)
            monthly_limit = round(_to_float(budget.get("monthly_limit"), 0.0), 2)
            await db.money_budgets.update_one(
                {"budget_id": budget_id, "owner_id": owner_id},
                {
                    "$set": {
                        "spent_amount": new_spent,
                        "remaining_amount": round(monthly_limit - new_spent, 2),
                        "updated_at": _now_iso(),
                    }
                },
            )

    return {"success": True, "expense_id": expense_id}


@router.get("/expenses/analytics")
async def expense_analytics(
    request: Request,
    fallback_user_id: Optional[str] = None,
    period_days: int = Query(default=30, ge=7, le=365),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    match_query = {"owner_id": owner_id, "created_at": {"$gte": cutoff}}

    summary_pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": None,
                "total_spent": {"$sum": "$amount"},
                "transaction_count": {"$sum": 1},
                "avg_ticket": {"$avg": "$amount"},
            }
        },
    ]
    summary_result = await db.money_expenses.aggregate(summary_pipeline).to_list(1)
    summary = summary_result[0] if summary_result else {}

    category_pipeline = [
        {"$match": match_query},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 10},
    ]
    categories_raw = await db.money_expenses.aggregate(category_pipeline).to_list(10)
    categories = [
        {
            "category": str(item.get("_id") or "uncategorized"),
            "total": round(_to_float(item.get("total"), 0.0), 2),
            "count": int(item.get("count") or 0),
        }
        for item in categories_raw
    ]

    trend_pipeline = [
        {"$match": match_query},
        {"$group": {"_id": {"$substr": ["$transaction_date", 0, 10]}, "total": {"$sum": "$amount"}}},
        {"$sort": {"_id": 1}},
    ]
    trend_raw = await db.money_expenses.aggregate(trend_pipeline).to_list(200)
    trend = [{"date": str(item.get("_id")), "total": round(_to_float(item.get("total"), 0.0), 2)} for item in trend_raw]

    return {
        "period_days": period_days,
        "summary": {
            "total_spent": round(_to_float(summary.get("total_spent"), 0.0), 2),
            "transaction_count": int(summary.get("transaction_count") or 0),
            "avg_ticket": round(_to_float(summary.get("avg_ticket"), 0.0), 2),
        },
        "top_categories": categories,
        "daily_trend": trend,
    }


@router.post("/savings-goals")
async def create_savings_goal(payload: SavingsGoalCreateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    if payload.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount must be greater than 0")

    usage = await _check_monthly_limit(
        "money_savings_goals",
        owner_id,
        "created_at",
        TIER_LIMITS[tier]["savings_goals_per_month"],
    )
    if not usage["can_proceed"]:
        raise _limit_reached_error(
            "money_savings_goal_limit_reached",
            f"Monthly savings goal limit reached ({usage['limit']} for {tier}).",
            tier,
            usage["used"],
            usage["limit"],
        )

    now = _now_iso()
    goal = {
        "goal_id": f"goal_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "title": payload.title,
        "target_amount": round(_to_float(payload.target_amount), 2),
        "current_amount": round(max(0.0, _to_float(payload.current_amount)), 2),
        "deadline": payload.deadline,
        "priority": payload.priority,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.money_savings_goals.insert_one(goal)
    goal.pop("_id", None)
    return {"goal": goal}


@router.get("/savings-goals")
async def list_savings_goals(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = Query(default="active"),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if status != "all":
        query["status"] = status

    goals = await db.money_savings_goals.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    total_target = round(sum(_to_float(item.get("target_amount"), 0.0) for item in goals), 2)
    total_current = round(sum(_to_float(item.get("current_amount"), 0.0) for item in goals), 2)
    progress_pct = round((total_current / total_target * 100) if total_target > 0 else 0.0, 2)
    return {
        "count": len(goals),
        "goals": goals,
        "summary": {
            "total_target": total_target,
            "total_current": total_current,
            "progress_pct": progress_pct,
        },
    }


@router.put("/savings-goals/{goal_id}")
async def update_savings_goal(goal_id: str, payload: SavingsGoalUpdateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    updates = payload.model_dump(exclude_none=True, exclude={"fallback_user_id"})
    if not updates:
        raise HTTPException(status_code=400, detail="No savings goal fields provided")

    if "target_amount" in updates:
        updates["target_amount"] = round(max(0.0, _to_float(updates["target_amount"])), 2)
    if "current_amount" in updates:
        updates["current_amount"] = round(max(0.0, _to_float(updates["current_amount"])), 2)

    current_goal = await db.money_savings_goals.find_one(
        {"goal_id": goal_id, "owner_id": owner_id},
        {"_id": 0, "target_amount": 1, "current_amount": 1, "status": 1},
    )
    if not current_goal:
        raise HTTPException(status_code=404, detail="Savings goal not found")

    target_amount = updates.get("target_amount", _to_float(current_goal.get("target_amount"), 0.0))
    current_amount = updates.get("current_amount", _to_float(current_goal.get("current_amount"), 0.0))

    if "status" not in updates and target_amount > 0 and current_amount >= target_amount:
        updates["status"] = "completed"

    updates["updated_at"] = _now_iso()
    result = await db.money_savings_goals.update_one({"goal_id": goal_id, "owner_id": owner_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Savings goal not found")

    goal = await db.money_savings_goals.find_one({"goal_id": goal_id, "owner_id": owner_id}, {"_id": 0})
    return {"message": "Savings goal updated", "goal": goal}


@router.post("/bill-reminders")
async def create_bill_reminder(payload: BillReminderCreateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    if payload.amount_due <= 0:
        raise HTTPException(status_code=400, detail="amount_due must be greater than 0")

    active_count = await db.money_bill_reminders.count_documents({"owner_id": owner_id, "status": "upcoming"})
    limit = TIER_LIMITS[tier]["bill_reminders_active"]
    if limit != -1 and active_count >= limit:
        raise _limit_reached_error(
            "money_bill_reminder_limit_reached",
            f"Active bill reminder limit reached ({limit} for {tier}).",
            tier,
            active_count,
            limit,
        )

    now = _now_iso()
    reminder = {
        "reminder_id": f"bill_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "title": payload.title,
        "amount_due": round(_to_float(payload.amount_due), 2),
        "due_date": payload.due_date,
        "category": payload.category.lower(),
        "autopay_enabled": bool(payload.autopay_enabled),
        "notes": payload.notes,
        "status": "upcoming",
        "created_at": now,
        "updated_at": now,
        "last_paid_at": None,
    }
    await db.money_bill_reminders.insert_one(reminder)
    reminder.pop("_id", None)
    return {"bill_reminder": reminder}


@router.get("/bill-reminders")
async def list_bill_reminders(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = Query(default="upcoming"),
    upcoming_days: int = Query(default=45, ge=1, le=365),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    query: Dict[str, Any] = {"owner_id": owner_id}
    if status != "all":
        query["status"] = status

    if status in {"upcoming", "all"}:
        now_iso = _now_iso()
        horizon = (datetime.now(timezone.utc) + timedelta(days=upcoming_days)).isoformat()
        query["due_date"] = {"$gte": now_iso, "$lte": horizon}

    reminders = await db.money_bill_reminders.find(query, {"_id": 0}).sort("due_date", 1).to_list(400)
    return {"count": len(reminders), "bill_reminders": reminders}


@router.put("/bill-reminders/{reminder_id}")
async def update_bill_reminder(reminder_id: str, payload: BillReminderUpdateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    updates = payload.model_dump(exclude_none=True, exclude={"fallback_user_id"})
    if not updates:
        raise HTTPException(status_code=400, detail="No bill reminder fields provided")

    if "amount_due" in updates:
        updates["amount_due"] = round(max(0.0, _to_float(updates["amount_due"])), 2)
    if "category" in updates:
        updates["category"] = str(updates["category"]).lower()
    if updates.get("status") == "paid":
        updates["last_paid_at"] = _now_iso()

    updates["updated_at"] = _now_iso()
    result = await db.money_bill_reminders.update_one(
        {"reminder_id": reminder_id, "owner_id": owner_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bill reminder not found")

    reminder = await db.money_bill_reminders.find_one({"reminder_id": reminder_id, "owner_id": owner_id}, {"_id": 0})
    return {"message": "Bill reminder updated", "bill_reminder": reminder}


@router.post("/portfolio/positions")
async def create_portfolio_position(payload: PortfolioPositionCreateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    if payload.quantity <= 0 or payload.average_cost < 0 or payload.current_price < 0:
        raise HTTPException(status_code=400, detail="Invalid portfolio values")

    active_count = await db.money_portfolio_positions.count_documents({"owner_id": owner_id, "status": "active"})
    limit = TIER_LIMITS[tier]["portfolio_positions"]
    if limit != -1 and active_count >= limit:
        raise _limit_reached_error(
            "money_portfolio_position_limit_reached",
            f"Portfolio position limit reached ({limit} for {tier}).",
            tier,
            active_count,
            limit,
        )

    now = _now_iso()
    position = {
        "position_id": f"pos_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "asset_type": payload.asset_type.lower(),
        "symbol": payload.symbol.upper(),
        "quantity": _to_float(payload.quantity),
        "average_cost": round(_to_float(payload.average_cost), 4),
        "current_price": round(_to_float(payload.current_price), 4),
        "currency": payload.currency.upper(),
        "notes": payload.notes,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.money_portfolio_positions.insert_one(position)
    position.pop("_id", None)
    return {"position": position}


@router.get("/portfolio/positions")
async def list_portfolio_positions(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = Query(default="active"),
):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    query: Dict[str, Any] = {"owner_id": owner_id}
    if status != "all":
        query["status"] = status
    positions = await db.money_portfolio_positions.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"count": len(positions), "positions": positions}


@router.put("/portfolio/positions/{position_id}")
async def update_portfolio_position(position_id: str, payload: PortfolioPositionUpdateRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    updates = payload.model_dump(exclude_none=True, exclude={"fallback_user_id"})
    if not updates:
        raise HTTPException(status_code=400, detail="No portfolio position fields provided")

    for field_name in ("quantity", "average_cost", "current_price"):
        if field_name in updates:
            updates[field_name] = _to_float(updates[field_name])
    if "asset_type" in updates:
        updates["asset_type"] = str(updates["asset_type"]).lower()
    if "symbol" in updates:
        updates["symbol"] = str(updates["symbol"]).upper()
    if "currency" in updates:
        updates["currency"] = str(updates["currency"]).upper()

    updates["updated_at"] = _now_iso()
    result = await db.money_portfolio_positions.update_one(
        {"position_id": position_id, "owner_id": owner_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Portfolio position not found")

    position = await db.money_portfolio_positions.find_one(
        {"position_id": position_id, "owner_id": owner_id},
        {"_id": 0},
    )
    return {"message": "Portfolio position updated", "position": position}


@router.get("/portfolio/analytics")
async def portfolio_analytics(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    positions = await db.money_portfolio_positions.find(
        {"owner_id": owner_id, "status": "active"},
        {"_id": 0},
    ).to_list(500)

    total_market_value = 0.0
    total_cost_basis = 0.0
    allocation: Dict[str, float] = {}

    for item in positions:
        quantity = _to_float(item.get("quantity"), 0.0)
        current_price = _to_float(item.get("current_price"), 0.0)
        avg_cost = _to_float(item.get("average_cost"), 0.0)
        asset_type = str(item.get("asset_type") or "other")

        market_value = quantity * current_price
        cost_value = quantity * avg_cost
        total_market_value += market_value
        total_cost_basis += cost_value
        allocation[asset_type] = allocation.get(asset_type, 0.0) + market_value

    unrealized_pnl = total_market_value - total_cost_basis
    roi_pct = (unrealized_pnl / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0

    allocation_list = []
    for key, value in sorted(allocation.items(), key=lambda kv: kv[1], reverse=True):
        pct = (value / total_market_value * 100.0) if total_market_value > 0 else 0.0
        allocation_list.append({"asset_type": key, "market_value": round(value, 2), "allocation_pct": round(pct, 2)})

    return {
        "summary": {
            "positions_count": len(positions),
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost_basis, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "roi_pct": round(roi_pct, 2),
        },
        "allocation": allocation_list,
    }


@router.post("/receipt-scan")
async def receipt_scan(payload: ReceiptScanRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    image_raw = str(payload.image_base64 or "").strip()
    if not image_raw:
        raise HTTPException(status_code=400, detail="image_base64 is required")

    usage = await _check_monthly_limit(
        "money_receipt_scans",
        owner_id,
        "created_at",
        TIER_LIMITS[tier]["receipt_scans_per_month"],
    )
    if not usage["can_proceed"]:
        raise _limit_reached_error(
            "money_receipt_scan_limit_reached",
            f"Monthly receipt scan limit reached ({usage['limit']} for {tier}).",
            tier,
            usage["used"],
            usage["limit"],
        )

    extracted_data = await _generate_receipt_extraction(image_raw)
    now = _now_iso()
    scan = {
        "scan_id": f"scan_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "image_sha256": hashlib.sha256(image_raw.encode("utf-8")).hexdigest(),
        "notes": payload.notes,
        "extracted_data": extracted_data,
        "created_at": now,
    }
    await db.money_receipt_scans.insert_one(scan)
    scan.pop("_id", None)

    draft = {
        "amount": round(_to_float(extracted_data.get("total_amount"), 0.0), 2),
        "category": str(extracted_data.get("category_suggestion") or "general"),
        "merchant": str(extracted_data.get("merchant") or "Unknown merchant"),
        "transaction_date": str(extracted_data.get("transaction_date") or now[:10]),
        "payment_method": str(extracted_data.get("payment_method") or "unknown"),
        "currency": str(extracted_data.get("currency") or "USD").upper(),
        "source": "receipt_scan",
        "receipt_scan_id": scan["scan_id"],
    }

    return {"scan": scan, "expense_draft": draft}


@router.post("/ai-advisor")
async def ai_advisor(payload: AdvisorRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)

    usage = await _check_monthly_limit(
        "money_ai_advice_runs",
        owner_id,
        "created_at",
        TIER_LIMITS[tier]["advisor_runs_per_month"],
    )
    if not usage["can_proceed"]:
        raise _limit_reached_error(
            "money_advisor_limit_reached",
            f"Monthly advisor run limit reached ({usage['limit']} for {tier}).",
            tier,
            usage["used"],
            usage["limit"],
        )

    profile = await db.money_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    budgets = await db.money_budgets.find({"owner_id": owner_id, "status": "active"}, {"_id": 0}).to_list(200)
    goals = await db.money_savings_goals.find({"owner_id": owner_id, "status": "active"}, {"_id": 0}).to_list(200)
    reminders = await db.money_bill_reminders.find({"owner_id": owner_id, "status": "upcoming"}, {"_id": 0}).to_list(200)
    positions = await db.money_portfolio_positions.find({"owner_id": owner_id, "status": "active"}, {"_id": 0}).to_list(300)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    expenses = await db.money_expenses.find(
        {"owner_id": owner_id, "created_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)

    spent_30d = 0.0
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for item in expenses:
        if str(item.get("created_at") or "") >= thirty_days_ago:
            spent_30d += _to_float(item.get("amount"), 0.0)

    total_budget = sum(_to_float(item.get("monthly_limit"), 0.0) for item in budgets)
    total_budget_spent = sum(_to_float(item.get("spent_amount"), 0.0) for item in budgets)
    budget_usage_pct = (total_budget_spent / total_budget * 100.0) if total_budget > 0 else 0.0

    portfolio_market = 0.0
    for item in positions:
        portfolio_market += _to_float(item.get("quantity"), 0.0) * _to_float(item.get("current_price"), 0.0)

    context = {
        "tier": tier,
        "profile": profile or {},
        "totals": {
            "spent_last_30d": round(spent_30d, 2),
            "total_budget": round(total_budget, 2),
            "budget_usage_pct": round(budget_usage_pct, 2),
            "active_savings_goals": len(goals),
            "upcoming_bill_count": len(reminders),
            "portfolio_market_value": round(portfolio_market, 2),
        },
        "budgets": budgets[:20],
        "goals": goals[:20],
        "upcoming_bills": reminders[:20],
        "portfolio": positions[:20],
        "recent_expenses_sample": expenses[:40],
    }

    advice = await _generate_ai_advice(
        context=context,
        question=payload.question or "",
        planning_horizon=max(1, min(24, int(payload.planning_horizon_months))),
        include_investment=bool(payload.include_investment),
    )

    run = {
        "run_id": f"adv_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "question": payload.question,
        "planning_horizon_months": max(1, min(24, int(payload.planning_horizon_months))),
        "include_investment": bool(payload.include_investment),
        "advice": advice,
        "created_at": _now_iso(),
    }
    await db.money_ai_advice_runs.insert_one(run)
    run.pop("_id", None)

    return {"run": run, "context_snapshot": context["totals"]}
