"""AI Digital Bank — Savings accounts, interest simulation, AI financial advisor."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import uuid
import logging
import json

from .db import db, require_auth
from utils.llm_helper import generate_verified_json

router = APIRouter(prefix="/bank")
logger = logging.getLogger(__name__)

INTEREST_RATES = {"standard": 0.02, "high_yield": 0.045, "premium": 0.065}


class SavingsAccountCreate(BaseModel):
    account_type: str = "standard"
    initial_deposit: float = 0


class DepositRequest(BaseModel):
    account_id: str
    amount: float


class WithdrawRequest(BaseModel):
    account_id: str
    amount: float


@router.post("/savings/open")
async def open_savings(payload: SavingsAccountCreate, request: Request):
    user = await require_auth(request)
    if payload.account_type not in INTEREST_RATES:
        raise HTTPException(status_code=400, detail=f"Types: {list(INTEREST_RATES.keys())}")
    existing = await db.bank_savings.count_documents({"user_id": user.user_id, "status": "active"})
    if existing >= 3:
        raise HTTPException(status_code=400, detail="Max 3 savings accounts")
    if payload.initial_deposit > 0:
        wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
        if not wallet or wallet.get("balance", 0) < payload.initial_deposit:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        await db.platform_wallets.update_one(
            {"user_id": user.user_id, "balance": {"$gte": payload.initial_deposit}},
            {
                "$inc": {"balance": -payload.initial_deposit},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
        )
    account = {
        "account_id": f"sav_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "account_type": payload.account_type,
        "balance": payload.initial_deposit,
        "interest_rate": INTEREST_RATES[payload.account_type],
        "interest_earned": 0.0,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bank_savings.insert_one(account)
    account.pop("_id", None)
    return {"account": account}


@router.get("/savings")
async def list_savings(request: Request):
    user = await require_auth(request)
    accounts = await db.bank_savings.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(5)
    total = sum(a.get("balance", 0) for a in accounts)
    total_interest = sum(a.get("interest_earned", 0) for a in accounts)
    return {
        "accounts": accounts,
        "total_balance": round(total, 2),
        "total_interest": round(total_interest, 2),
        "rates": INTEREST_RATES,
    }


@router.post("/savings/deposit")
async def deposit_savings(payload: DepositRequest, request: Request):
    user = await require_auth(request)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    account = await db.bank_savings.find_one(
        {"account_id": payload.account_id, "user_id": user.user_id, "status": "active"}, {"_id": 0}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
    if not wallet or wallet.get("balance", 0) < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.platform_wallets.update_one(
        {"user_id": user.user_id, "balance": {"$gte": payload.amount}},
        {"$inc": {"balance": -payload.amount}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.bank_savings.update_one({"account_id": payload.account_id}, {"$inc": {"balance": payload.amount}})
    return {"success": True}


@router.post("/savings/withdraw")
async def withdraw_savings(payload: WithdrawRequest, request: Request):
    user = await require_auth(request)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    account = await db.bank_savings.find_one(
        {"account_id": payload.account_id, "user_id": user.user_id, "status": "active"}, {"_id": 0}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient savings balance")
    await db.bank_savings.update_one({"account_id": payload.account_id}, {"$inc": {"balance": -payload.amount}})
    await db.platform_wallets.update_one(
        {"user_id": user.user_id},
        {"$inc": {"balance": payload.amount}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}


@router.post("/savings/simulate-interest")
async def simulate_interest(request: Request):
    """Simulate monthly interest accrual for all active savings accounts."""
    user = await require_auth(request)
    accounts = await db.bank_savings.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(5)
    total_interest = 0
    for a in accounts:
        monthly_rate = a["interest_rate"] / 12
        interest = round(a["balance"] * monthly_rate, 2)
        if interest > 0:
            await db.bank_savings.update_one(
                {"account_id": a["account_id"]}, {"$inc": {"balance": interest, "interest_earned": interest}}
            )
            total_interest += interest
    return {"interest_applied": round(total_interest, 2), "accounts_updated": len(accounts)}


@router.get("/advisor")
async def ai_financial_advisor(request: Request):
    """AI financial advisor copilot."""
    user = await require_auth(request)
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
    savings = await db.bank_savings.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(5)
    loans = await db.platform_loans.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(10)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    tx_count = await db.platform_transactions.count_documents(
        {"sender_id": user.user_id, "created_at": {"$gte": cutoff}}
    )

    context = {
        "wallet_balance": wallet.get("balance", 0) if wallet else 0,
        "savings_total": sum(s.get("balance", 0) for s in savings),
        "active_loans": len(loans),
        "loan_debt": sum(loan.get("total_repayment", 0) - loan.get("repaid_amount", 0) for loan in loans),
        "monthly_transactions": tx_count,
    }
    try:
        advice = await generate_verified_json(
            prompt=f'Give personalized financial advice. Return ONLY JSON: {{"advice": [<3-4 tips>], "risk_level": "<low|medium|high>", "priority_action": "<most important thing to do>", "income_stability": "<stable|moderate|unstable>"}}\nData: {json.dumps(context)}',
            system_message="You are a caring AI financial advisor. Be specific and actionable.",
            session_id=f"advisor-{user.user_id[:6]}",
        )
    except Exception:
        advice = {
            "advice": ["Build an emergency fund", "Track spending daily"],
            "risk_level": "medium",
            "priority_action": "Review your budget",
            "income_stability": "moderate",
        }
    return {"financial_data": context, "ai_advice": advice}
