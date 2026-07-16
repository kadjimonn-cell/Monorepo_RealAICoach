"""Fraud and AML helpers for ID verification routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import uuid

from .db import db
from utils.llm_helper import generate_verified_json


async def check_aml(user_id: str, amount: float, tx_type: str, currency: str = "USD") -> dict:
    flags = []
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent_count = await db.afrikpay_transactions.count_documents({"sender_id": user_id, "created_at": {"$gte": one_hour_ago}})
    if recent_count > 5:
        flags.append("velocity_limit_exceeded")
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    daily_pipeline = [{"$match": {"sender_id": user_id, "created_at": {"$gte": today_start}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    daily = await db.afrikpay_transactions.aggregate(daily_pipeline).to_list(1)
    daily_total = daily[0]["total"] if daily else 0
    if daily_total + amount > 10000:
        flags.append("daily_limit_warning")
    recent_small = await db.afrikpay_transactions.count_documents({"sender_id": user_id, "amount": {"$gte": 900, "$lte": 1000}, "created_at": {"$gte": one_hour_ago}})
    if recent_small >= 3:
        flags.append("potential_structuring")
    if amount > 5000:
        flags.append("high_value_transaction")
    risk_level = "low"
    if len(flags) >= 3:
        risk_level = "critical"
    elif len(flags) >= 2:
        risk_level = "high"
    elif len(flags) >= 1:
        risk_level = "medium"
    if flags:
        await db.afrikpay_aml_flags.insert_one(
            {
                "aml_id": f"aml_{uuid.uuid4().hex[:10]}",
                "user_id": user_id,
                "amount": amount,
                "currency": currency,
                "tx_type": tx_type,
                "flags": flags,
                "risk_level": risk_level,
                "status": "pending_review",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return {"flags": flags, "risk_level": risk_level, "passed": len(flags) == 0}


async def enhanced_fraud_check(user_id: str, tx_data: dict) -> dict:
    amount = tx_data.get("amount", 0)
    device_token = tx_data.get("device_token", "")
    if device_token:
        device_hash = hashlib.sha256(device_token.encode()).hexdigest()[:16]
        known_device = await db.afrikpay_device_profiles.find_one({"user_id": user_id, "device_hash": device_hash}, {"_id": 0})
        if not known_device:
            await db.afrikpay_device_profiles.insert_one(
                {
                    "user_id": user_id,
                    "device_hash": device_hash,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "tx_count": 1,
                }
            )
    wallet = await db.afrikpay_wallets.find_one({"user_id": user_id}, {"_id": 0})
    recent_txs = await db.afrikpay_transactions.find({"sender_id": user_id}, {"_id": 0, "amount": 1, "type": 1, "created_at": 1}).sort("created_at", -1).to_list(20)
    avg_amount = sum(t["amount"] for t in recent_txs) / max(len(recent_txs), 1)
    risk_factors = []
    if amount > avg_amount * 5 and len(recent_txs) > 3:
        risk_factors.append("amount_anomaly")
    if wallet and amount > wallet.get("balance", 0) * 0.8:
        risk_factors.append("high_balance_ratio")
    base_risk = 0.1
    if "amount_anomaly" in risk_factors:
        base_risk += 0.3
    if "high_balance_ratio" in risk_factors:
        base_risk += 0.15
    return {"risk_score": round(min(base_risk, 1.0), 3), "risk_factors": risk_factors, "device_known": bool(device_token)}


async def ai_fraud_analysis(user_id: str, tx_data: dict, *, kyc_lookup, logger) -> dict:
    try:
        llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not llm_key:
            return {"ai_risk": "unavailable", "reason": "LLM not configured"}
        recent_txs = await db.afrikpay_transactions.find({"sender_id": user_id}, {"_id": 0, "amount": 1, "type": 1, "created_at": 1, "currency": 1}).sort("created_at", -1).to_list(10)
        wallet = await db.afrikpay_wallets.find_one({"user_id": user_id}, {"_id": 0, "balance": 1, "created_at": 1})
        kyc = await kyc_lookup({"user_id": user_id}, {"_id": 0, "status": 1, "tier": 1})
        context = {
            "current_tx": {"amount": tx_data.get("amount"), "type": tx_data.get("type"), "currency": tx_data.get("currency")},
            "recent_tx_count": len(recent_txs),
            "avg_tx_amount": round(sum(t["amount"] for t in recent_txs) / max(len(recent_txs), 1), 2),
            "wallet_balance": wallet.get("balance", 0) if wallet else 0,
            "kyc_status": kyc.get("status") if kyc else "none",
            "account_age_days": 30,
        }
        prompt = f"""Analyze this financial transaction for fraud risk. Return ONLY valid JSON.
Transaction: {json.dumps(context['current_tx'])}
User Context: {len(recent_txs)} recent transactions, avg amount ${context['avg_tx_amount']}, balance ${context['wallet_balance']}, KYC: {context['kyc_status']}

Return JSON: {{\"risk_level\": \"low|medium|high|critical\", \"risk_score\": 0.0-1.0, \"flags\": [\"list of concerns\"], \"recommendation\": \"approve|review|block\"}}"""
        result = await generate_verified_json(prompt, llm_key, f"fraud_{user_id[:8]}")
        if result:
            return {
                "ai_risk": result.get("risk_level", "low"),
                "ai_score": result.get("risk_score", 0.1),
                "ai_flags": result.get("flags", []),
                "ai_recommendation": result.get("recommendation", "approve"),
            }
    except Exception as exc:
        logger.warning(f"AI fraud analysis error: {exc}")
    return {"ai_risk": "low", "ai_score": 0.1, "ai_flags": [], "ai_recommendation": "approve"}