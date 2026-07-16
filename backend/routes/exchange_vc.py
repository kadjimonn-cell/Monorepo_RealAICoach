"""AI Creator Stock Exchange + Venture Capital Funding Engine."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List
import uuid
import logging
import json

from .db import db, require_auth
from utils.llm_helper import generate_verified_json

router = APIRouter(prefix="/exchange")
logger = logging.getLogger(__name__)


# ── Creator Stock Exchange ──


class ShareIssue(BaseModel):
    shares_total: int = 1000
    price_per_share: float = 1.0
    revenue_share_pct: float = 5.0  # % of creator revenue shared with shareholders


class SharePurchase(BaseModel):
    creator_id: str
    shares: int


class VCCampaignCreate(BaseModel):
    title: str
    description: str
    funding_goal: float
    category: str = "startup"  # startup, film, tech, creator, social
    milestones: List[str] = []


class VCInvest(BaseModel):
    campaign_id: str
    amount: float


@router.post("/shares/issue")
async def issue_shares(payload: ShareIssue, request: Request):
    user = await require_auth(request)
    existing = await db.creator_shares.find_one({"creator_id": user.user_id}, {"_id": 0})
    if existing:
        return {"shares": existing, "message": "Already issued"}
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0, "handle": 1, "user_name": 1})
    shares = {
        "stock_id": f"stk_{uuid.uuid4().hex[:10]}",
        "creator_id": user.user_id,
        "creator_name": wallet.get("user_name", "") if wallet else "",
        "shares_total": payload.shares_total,
        "shares_available": payload.shares_total,
        "price_per_share": payload.price_per_share,
        "revenue_share_pct": payload.revenue_share_pct,
        "market_cap": round(payload.shares_total * payload.price_per_share, 2),
        "total_raised": 0.0,
        "investor_count": 0,
        "ai_valuation": 0,
        "volatility": "low",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.creator_shares.insert_one(shares)
    shares.pop("_id", None)
    return {"shares": shares}


@router.get("/shares")
async def list_creator_shares(request: Request, limit: int = 20):
    await require_auth(request)
    shares = await db.creator_shares.find({}, {"_id": 0}).sort("total_raised", -1).limit(limit).to_list(limit)
    return {"shares": shares}


@router.post("/shares/buy")
async def buy_shares(payload: SharePurchase, request: Request):
    user = await require_auth(request)
    if payload.shares <= 0:
        raise HTTPException(status_code=400, detail="Shares must be positive")
    stock = await db.creator_shares.find_one({"creator_id": payload.creator_id}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Creator shares not found")
    if stock["creator_id"] == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot buy your own shares")
    if stock["shares_available"] < payload.shares:
        raise HTTPException(status_code=400, detail="Not enough shares available")
    cost = round(payload.shares * stock["price_per_share"], 2)
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
    if not wallet or wallet.get("balance", 0) < cost:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    # Transfer
    await db.platform_wallets.update_one(
        {"user_id": user.user_id, "balance": {"$gte": cost}},
        {"$inc": {"balance": -cost}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.platform_wallets.update_one(
        {"user_id": payload.creator_id},
        {"$inc": {"balance": cost}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.creator_shares.update_one(
        {"creator_id": payload.creator_id},
        {"$inc": {"shares_available": -payload.shares, "total_raised": cost, "investor_count": 1}},
    )
    # Record holding
    await db.share_holdings.update_one(
        {"investor_id": user.user_id, "creator_id": payload.creator_id},
        {
            "$inc": {"shares": payload.shares, "total_invested": cost},
            "$setOnInsert": {
                "investor_id": user.user_id,
                "creator_id": payload.creator_id,
                "first_purchase": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )
    await db.platform_transactions.insert_one(
        {
            "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
            "type": "share_purchase",
            "sender_id": user.user_id,
            "recipient_id": payload.creator_id,
            "amount": cost,
            "currency": "USD",
            "description": f"Bought {payload.shares} creator shares",
            "status": "completed",
            "risk_score": 0,
            "fraud_checked": False,
            "meta": {"shares": payload.shares, "price_per_share": stock["price_per_share"]},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "shares_bought": payload.shares, "cost": cost}


@router.get("/shares/my-holdings")
async def my_holdings(request: Request):
    user = await require_auth(request)
    holdings = await db.share_holdings.find({"investor_id": user.user_id}, {"_id": 0}).to_list(20)
    for h in holdings:
        stock = await db.creator_shares.find_one(
            {"creator_id": h["creator_id"]}, {"_id": 0, "creator_name": 1, "price_per_share": 1}
        )
        if stock:
            h["creator_name"] = stock.get("creator_name", "")
            h["current_value"] = round(h["shares"] * stock["price_per_share"], 2)
    return {"holdings": holdings}


@router.get("/shares/valuation/{creator_id}")
async def ai_valuation(creator_id: str, request: Request):
    await require_auth(request)
    stock = await db.creator_shares.find_one({"creator_id": creator_id}, {"_id": 0})
    if not stock:
        raise HTTPException(status_code=404, detail="Not found")
    streams = await db.live_streams.count_documents({"streamer_id": creator_id})
    subs = await db.live_subscriptions.count_documents({"streamer_id": creator_id, "status": "active"})
    tips = await db.live_tips.aggregate(
        [{"$match": {"streamer_id": creator_id}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    ).to_list(1)
    context = {
        "shares_issued": stock["shares_total"],
        "shares_sold": stock["shares_total"] - stock["shares_available"],
        "total_raised": stock["total_raised"],
        "streams": streams,
        "subscribers": subs,
        "tips_earned": tips[0]["total"] if tips else 0,
    }
    try:
        val = await generate_verified_json(
            prompt=f'Evaluate this creator\'s stock. Return JSON: {{"valuation_score": 0-100, "risk_index": "<low|medium|high>", "growth_potential": "<strong|moderate|weak>", "recommendation": "<buy|hold|sell>"}}\nData: {json.dumps(context)}',
            system_message="You are a stock analyst AI. Be data-driven.",
            session_id=f"val-{creator_id[:6]}",
        )
    except Exception:
        val = {"valuation_score": 50, "risk_index": "medium", "growth_potential": "moderate", "recommendation": "hold"}
    await db.creator_shares.update_one(
        {"creator_id": creator_id}, {"$set": {"ai_valuation": val.get("valuation_score", 50)}}
    )
    return {"stock": stock, "valuation": val}


# ── Venture Capital Engine ──


@router.post("/vc/campaigns/create")
async def create_vc_campaign(payload: VCCampaignCreate, request: Request):
    user = await require_auth(request)
    if payload.funding_goal <= 0:
        raise HTTPException(status_code=400, detail="Goal must be positive")
    campaign = {
        "campaign_id": f"vc_{uuid.uuid4().hex[:12]}",
        "creator_id": user.user_id,
        "title": payload.title,
        "description": payload.description,
        "funding_goal": payload.funding_goal,
        "raised": 0.0,
        "category": payload.category,
        "milestones": payload.milestones,
        "investor_count": 0,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.vc_campaigns.insert_one(campaign)
    campaign.pop("_id", None)
    return {"campaign": campaign}


@router.get("/vc/campaigns")
async def list_vc_campaigns(request: Request, limit: int = 20):
    await require_auth(request)
    campaigns = (
        await db.vc_campaigns.find({"status": "active"}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    return {"campaigns": campaigns}


@router.post("/vc/invest")
async def invest_in_campaign(payload: VCInvest, request: Request):
    user = await require_auth(request)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    campaign = await db.vc_campaigns.find_one({"campaign_id": payload.campaign_id, "status": "active"}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["creator_id"] == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot invest in own campaign")
    wallet = await db.platform_wallets.find_one({"user_id": user.user_id}, {"_id": 0})
    if not wallet or wallet.get("balance", 0) < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.platform_wallets.update_one(
        {"user_id": user.user_id, "balance": {"$gte": payload.amount}},
        {"$inc": {"balance": -payload.amount}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.platform_wallets.update_one(
        {"user_id": campaign["creator_id"]},
        {"$inc": {"balance": payload.amount}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    new_raised = campaign["raised"] + payload.amount
    new_status = "funded" if new_raised >= campaign["funding_goal"] else "active"
    await db.vc_campaigns.update_one(
        {"campaign_id": payload.campaign_id},
        {"$inc": {"raised": payload.amount, "investor_count": 1}, "$set": {"status": new_status}},
    )
    await db.vc_investments.insert_one(
        {
            "investment_id": f"inv_{uuid.uuid4().hex[:10]}",
            "campaign_id": payload.campaign_id,
            "investor_id": user.user_id,
            "amount": payload.amount,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await db.platform_transactions.insert_one(
        {
            "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
            "type": "vc_investment",
            "sender_id": user.user_id,
            "recipient_id": campaign["creator_id"],
            "amount": payload.amount,
            "currency": "USD",
            "description": f"VC: {campaign['title']}",
            "status": "completed",
            "risk_score": 0,
            "fraud_checked": False,
            "meta": {"campaign_id": payload.campaign_id},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "amount_invested": payload.amount, "campaign_status": new_status}


@router.get("/vc/my-investments")
async def my_investments(request: Request):
    user = await require_auth(request)
    investments = await db.vc_investments.find({"investor_id": user.user_id}, {"_id": 0}).to_list(20)
    for i in investments:
        c = await db.vc_campaigns.find_one(
            {"campaign_id": i["campaign_id"]}, {"_id": 0, "title": 1, "status": 1, "raised": 1, "funding_goal": 1}
        )
        if c:
            i.update(c)
    return {"investments": investments}


# ── Token Governance ──


class StakeRequest(BaseModel):
    points: int


class VoteRequest(BaseModel):
    proposal_id: str
    vote: str  # yes, no


@router.post("/tokens/stake")
async def stake_tokens(payload: StakeRequest, request: Request):
    user = await require_auth(request)
    if payload.points <= 0:
        raise HTTPException(status_code=400, detail="Must stake positive amount")
    points_doc = await db.platform_points.find_one({"user_id": user.user_id}, {"_id": 0})
    if not points_doc or points_doc.get("balance", 0) < payload.points:
        raise HTTPException(status_code=400, detail="Insufficient AFRIKPOINTS")
    await db.platform_points.update_one({"user_id": user.user_id}, {"$inc": {"balance": -payload.points}})
    await db.token_stakes.update_one(
        {"user_id": user.user_id},
        {
            "$inc": {"staked": payload.points},
            "$setOnInsert": {"user_id": user.user_id, "created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )
    return {"success": True, "staked": payload.points}


@router.get("/tokens/my-stake")
async def my_stake(request: Request):
    user = await require_auth(request)
    stake = await db.token_stakes.find_one({"user_id": user.user_id}, {"_id": 0})
    return {"staked": stake.get("staked", 0) if stake else 0}


@router.post("/governance/vote")
async def cast_vote(payload: VoteRequest, request: Request):
    user = await require_auth(request)
    stake = await db.token_stakes.find_one({"user_id": user.user_id}, {"_id": 0})
    voting_power = stake.get("staked", 0) if stake else 0
    if voting_power <= 0:
        raise HTTPException(status_code=400, detail="Must stake AFRIKPOINTS to vote")
    existing = await db.governance_votes.find_one(
        {"proposal_id": payload.proposal_id, "user_id": user.user_id}, {"_id": 0}
    )
    if existing:
        return {"success": True, "message": "Already voted"}
    await db.governance_votes.insert_one(
        {
            "proposal_id": payload.proposal_id,
            "user_id": user.user_id,
            "vote": payload.vote,
            "voting_power": voting_power,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"success": True, "vote": payload.vote, "voting_power": voting_power}


@router.get("/governance/proposals")
async def list_proposals(request: Request):
    await require_auth(request)
    proposals = await db.governance_proposals.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    if not proposals:
        # Seed sample proposals
        samples = [
            {
                "proposal_id": "prop_001",
                "title": "Reduce platform fee to 12%",
                "status": "active",
                "yes_votes": 0,
                "no_votes": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "proposal_id": "prop_002",
                "title": "Launch creator grants program",
                "status": "active",
                "yes_votes": 0,
                "no_votes": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await db.governance_proposals.insert_many(samples)
        proposals = samples
    for p in proposals:
        p.pop("_id", None)
    return {"proposals": proposals}
