from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
import uuid
import json

from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db, EMERGENT_LLM_KEY, require_admin
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/admin/general-analytics")


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_end_date") or row.get("subscription_expires_at") or row.get("subscription_end"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def _count(collection: str, query: Dict[str, Any] | None = None) -> int:
    return await db[collection].count_documents(query or {})


async def _sum(collection: str, field: str, query: Dict[str, Any] | None = None) -> float:
    pipeline = [
        {"$match": query or {}},
        {"$group": {"_id": None, "total": {"$sum": f"${field}"}}},
    ]
    results = await db[collection].aggregate(pipeline).to_list(1)
    return float(results[0]["total"]) if results else 0.0


async def _avg(collection: str, field: str, query: Dict[str, Any] | None = None) -> float:
    pipeline = [
        {"$match": query or {}},
        {"$group": {"_id": None, "avg": {"$avg": f"${field}"}}},
    ]
    results = await db[collection].aggregate(pipeline).to_list(1)
    return float(results[0]["avg"]) if results else 0.0


async def _distinct_count(collection: str, field: str, query: Dict[str, Any] | None = None) -> int:
    values = await db[collection].distinct(field, query or {})
    return len(values)


async def _bucket_credit_scores() -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": {"score": {"$exists": True}}},
        {
            "$bucket": {
                "groupBy": "$score",
                "boundaries": [300, 500, 650, 750, 850, 1001],
                "default": "unknown",
                "output": {"count": {"$sum": 1}},
            }
        },
    ]
    results = await db.ai_credit_scores.aggregate(pipeline).to_list(10)
    buckets = {
        "300-499": 0,
        "500-649": 0,
        "650-749": 0,
        "750-849": 0,
        "850-1000": 0,
    }
    for row in results:
        key = row.get("_id")
        if key == 300:
            buckets["300-499"] = row["count"]
        elif key == 500:
            buckets["500-649"] = row["count"]
        elif key == 650:
            buckets["650-749"] = row["count"]
        elif key == 750:
            buckets["750-849"] = row["count"]
        elif key == 850:
            buckets["850-1000"] = row["count"]
    return [{"range": k, "count": v} for k, v in buckets.items()]


@router.get("/summary")
async def general_analytics_summary(req: Request):
    admin = await require_admin(req)
    now = _now()
    last_30 = now - timedelta(days=30)
    prev_30 = now - timedelta(days=60)

    total_users = await _count("users")
    new_users = await _count("users", {"created_at": {"$gte": last_30}})
    prev_new_users = await _count("users", {"created_at": {"$gte": prev_30, "$lt": last_30}})
    active_users = await _distinct_count("user_sessions", "user_id", {"expires_at": {"$gt": now}})

    paid_user_rows = await db.users.find(
        {},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_end": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    paid_users = sum(1 for row in paid_user_rows if _effective_plan_from_user_doc(row) in {"basic", "premium"})
    conversion_rate = (paid_users / total_users * 100) if total_users else 0
    growth_rate = ((new_users - prev_new_users) / prev_new_users * 100) if prev_new_users else 0

    inactive_users = await _count("users", {"updated_at": {"$lt": last_30}})
    churn_rate = (inactive_users / total_users * 100) if total_users else 0

    subscription_revenue = await _sum("payments", "amount", {"status": "success"})
    momo_revenue = await _sum("mobile_money_payments", "amount", {"status": "success"})
    total_revenue = subscription_revenue + momo_revenue

    monthly_recurring = await _sum("subscriptions", "amount", {"status": "active"})
    platform_volume = await _sum("platform_transactions", "amount", {})
    merchant_volume = await _sum("merchant_transactions", "amount", {})

    loan_portfolio = await _sum("loan_portfolio", "outstanding_balance", {})
    loan_defaults = await _count("loan_portfolio", {"status": "defaulted"})

    ai_usage = await _count("conversations")
    job_matches = await _count("job_matches")
    job_match_success = await _count("job_matches", {"status": "accepted"})
    job_match_accuracy = (job_match_success / job_matches * 100) if job_matches else 0

    fraud_alerts = await _count("fraud_alerts")
    fraud_rate = (fraud_alerts / total_revenue * 100) if total_revenue else 0

    credit_distribution = await _bucket_credit_scores()

    mini_app_usage = await db.usage_analytics.aggregate(
        [{"$group": {"_id": "$feature_id", "count": {"$sum": 1}}}]
    ).to_list(50)
    mini_app_map = {item["_id"]: item["count"] for item in mini_app_usage if item.get("_id")}

    api_latency = await _avg("api_metrics", "latency_ms", {})
    queue_depth = await _count("job_queue")

    summary = {
        "platform": {
            "total_users": total_users,
            "active_users": active_users,
            "growth_rate": growth_rate,
            "subscription_conversion_rate": conversion_rate,
            "churn_rate": churn_rate,
        },
        "financial": {
            "total_revenue": total_revenue,
            "monthly_recurring_revenue": monthly_recurring,
            "subscription_revenue": subscription_revenue,
            "platform_volume": platform_volume,
            "loan_portfolio": {
                "outstanding_balance": loan_portfolio,
                "defaulted_loans": loan_defaults,
            },
            "merchant_volume": merchant_volume,
        },
        "ai": {
            "ai_usage_rate": ai_usage,
            "job_matching_accuracy": job_match_accuracy,
            "fraud_detection_rate": fraud_rate,
            "ai_credit_score_distribution": credit_distribution,
        },
        "mini_apps": {
            "job_mini_app_usage": mini_app_map.get("job-mini", 0),
            "platform_transactions": mini_app_map.get("platform", 0),
            "invoice_generator_usage": mini_app_map.get("invoice-generator", 0),
            "music_streaming_usage": mini_app_map.get("music-streaming", 0),
            "drama_box_engagement": mini_app_map.get("drama-box", 0),
        },
        "risk": {
            "fraud_alerts": fraud_alerts,
            "blocked_transactions": await _count("blocked_transactions"),
            "suspicious_accounts": await _count("suspicious_accounts"),
            "aml_flags": await _count("aml_flags"),
        },
        "infrastructure": {
            "api_response_time_ms": api_latency,
            "server_health": "healthy",
            "queue_depth": queue_depth,
            "automation_status": "active",
        },
        "communication": {
            "total_conversations": await _count("direct_conversations"),
            "total_messages": await _count("direct_messages"),
            "messages_today": await _count("direct_messages", {"created_at": {"$gte": last_30}}),
            "active_senders": await _distinct_count("direct_messages", "sender_id", {"created_at": {"$gte": last_30}}),
        },
        "support": {
            "total_tickets": await _count("support_submissions"),
            "open_tickets": await _count("support_submissions", {"status": "open"}),
            "resolved_tickets": await _count("support_submissions", {"status": "resolved"}),
            "tickets_this_month": await _count("support_submissions", {"created_at": {"$gte": last_30}}),
        },
        "subscriptions": {
            "cancellations_this_month": await _count(
                "support_tickets", {"type": "cancellation", "created_at": {"$gte": last_30}}
            ),
            "total_cancellations": await _count("support_tickets", {"type": "cancellation"}),
            "active_subscribers": paid_users,
        },
        "generated_at": _now_iso(),
    }

    await db.system_metrics.insert_one(
        {
            "metric_id": f"sys_{uuid.uuid4().hex[:8]}",
            "summary": summary,
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )
    await db.usage_metrics.insert_one(
        {
            "metric_id": f"use_{uuid.uuid4().hex[:8]}",
            "platform": summary["platform"],
            "ai": summary["ai"],
            "mini_apps": summary["mini_apps"],
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )
    await db.revenue_metrics.insert_one(
        {
            "metric_id": f"rev_{uuid.uuid4().hex[:8]}",
            "financial": summary["financial"],
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )
    await db.risk_metrics.insert_one(
        {
            "metric_id": f"risk_{uuid.uuid4().hex[:8]}",
            "risk": summary["risk"],
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )
    await db.infrastructure_metrics.insert_one(
        {
            "metric_id": f"infra_{uuid.uuid4().hex[:8]}",
            "infrastructure": summary["infrastructure"],
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"log_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "general_analytics_summary",
            "metadata": {"path": req.url.path},
            "created_at": _now_iso(),
        }
    )

    return summary


@router.post("/insights")
async def generate_ai_insights(req: Request):
    admin = await require_admin(req)

    summary = await general_analytics_summary(req)
    prompt = (
        "You are the RealAICoach AI Insight Engine. Analyze the following JSON metrics and produce: "
        "1) Trend detection 2) Revenue prediction 3) Risk prediction 4) User behavior clustering "
        "5) Fraud pattern heatmaps summary 6) Loan default prediction. "
        "Return concise bullet points per section. Metrics JSON: "
        f"{json.dumps(summary)}"
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"admin-insights-{uuid.uuid4().hex[:8]}",
            system_message="You are a precise enterprise analytics assistant.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        insight_text = response.strip()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Insight generation failed: {exc}")

    insight_record = {
        "insight_id": f"ins_{uuid.uuid4().hex[:10]}",
        "summary_snapshot": summary,
        "content": insight_text,
        "created_at": _now_iso(),
        "created_by": admin.user_id,
    }
    await db.ai_insight_logs.insert_one(insight_record)

    return {"insight": insight_text, "generated_at": insight_record["created_at"]}


@router.get("/charts")
async def analytics_charts(req: Request):
    """Return time-series and breakdown data for dashboard charts."""
    await require_admin(req)
    now = _now()

    # 1. User growth: daily registrations over last 30 days
    user_growth = []
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = await db.users.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}})
        user_growth.append({"date": day_start.strftime("%m/%d"), "users": count})

    # 2. Subscription distribution
    dist_rows = await db.users.find(
        {},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_end": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    subscription_counts: Dict[str, int] = {}
    for row in dist_rows:
        plan = _effective_plan_from_user_doc(row)
        subscription_counts[plan] = subscription_counts.get(plan, 0) + 1
    subscription_dist = [{"plan": plan, "count": count} for plan, count in subscription_counts.items()]

    # 3. Daily active users (DAU) last 14 days from sessions
    dau_data = []
    for i in range(13, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        dau_pipeline = [
            {"$match": {"issued_at": {"$gte": day_start, "$lt": day_end}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"},
        ]
        result = await db.user_sessions.aggregate(dau_pipeline).to_list(1)
        dau_data.append({"date": day_start.strftime("%m/%d"), "dau": result[0]["count"] if result else 0})

    # 4. Security events by type (last 7 days)
    sec_pipeline = [
        {"$match": {"timestamp": {"$gte": (now - timedelta(days=7)).isoformat()}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6},
    ]
    sec_breakdown = await db.security_events.aggregate(sec_pipeline).to_list(6)
    security_by_type = [{"type": r["_id"] or "unknown", "count": r["count"]} for r in sec_breakdown]

    # 5. Feature usage (top 10 most used features)
    feature_pipeline = [
        {"$group": {"_id": "$feature_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    feature_results = await db.usage_analytics.aggregate(feature_pipeline).to_list(10)
    top_features = [{"feature": r["_id"] or "unknown", "count": r["count"]} for r in feature_results]

    # 6. AI feedback sentiment (thumbs up vs down)
    feedback_pipeline = [
        {
            "$group": {
                "_id": None,
                "positive": {"$sum": {"$cond": [{"$in": ["$rating", [1, "up"]]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$in": ["$rating", [-1, "down"]]}, 1, 0]}},
                "total": {"$sum": 1},
            }
        },
    ]
    feedback_result = await db.ai_feedback.aggregate(feedback_pipeline).to_list(1)
    sentiment = feedback_result[0] if feedback_result else {"positive": 0, "negative": 0, "total": 0}
    if "_id" in sentiment:
        del sentiment["_id"]

    return {
        "user_growth": user_growth,
        "subscription_distribution": subscription_dist,
        "daily_active_users": dau_data,
        "security_by_type": security_by_type,
        "top_features": top_features,
        "ai_sentiment": sentiment,
    }


# ── AI-Powered Analytics ──


@router.post("/trend-detection")
async def ai_trend_detection(req: Request):
    """Use AI to detect trends in user growth, revenue, and engagement."""
    admin = await require_admin(req)

    now = _now()
    # Gather 30-day time-series data
    growth_data = []
    for i in range(29, -1, -1):
        d = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        count = await db.users.count_documents({"created_at": {"$gte": d, "$lt": d + timedelta(days=1)}})
        growth_data.append({"day": i, "registrations": count})

    # Session activity
    session_data = []
    for i in range(13, -1, -1):
        d = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        pipeline = [
            {"$match": {"issued_at": {"$gte": d, "$lt": d + timedelta(days=1)}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"},
        ]
        result = await db.user_sessions.aggregate(pipeline).to_list(1)
        session_data.append({"day": i, "dau": result[0]["count"] if result else 0})

    # Revenue data
    total_revenue = await _sum("payments", "amount", {"status": "success"})
    wallet_volume_pipeline = [
        {"$match": {"type": {"$in": ["transfer", "subscription"]}, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    wallet_vol = await db.platform_transactions.aggregate(wallet_volume_pipeline).to_list(1)
    wallet_volume = wallet_vol[0]["total"] if wallet_vol else 0

    total_users = await _count("users")
    paid_rows = await db.users.find(
        {},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_end": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    paid_users = sum(1 for row in paid_rows if _effective_plan_from_user_doc(row) in {"basic", "premium"})
    total_wallets = await db.platform_wallets.count_documents({})

    context = {
        "user_growth_30d": growth_data,
        "dau_14d": session_data,
        "total_users": total_users,
        "paid_users": paid_users,
        "total_revenue_usd": total_revenue,
        "platform_volume": wallet_volume,
        "total_wallets": total_wallets,
    }

    prompt = (
        "Analyze these platform metrics and provide:\n"
        "1. TREND DETECTION: Identify growth/decline patterns in registrations and DAU\n"
        "2. REVENUE PREDICTION: Estimate next 30-day revenue based on current trajectory\n"
        "3. RISK ANALYSIS: Flag any concerning patterns (churn risk, engagement drops)\n"
        "4. RECOMMENDATIONS: 3 actionable items to improve growth\n\n"
        "Return ONLY valid JSON with keys: trends, revenue_prediction, risks, recommendations\n"
        "Each should be an array of objects with 'title' and 'description' fields.\n\n"
        f"Metrics: {json.dumps(context)}"
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"trends-{uuid.uuid4().hex[:8]}",
            system_message="You are a FinTech analytics AI. Provide data-driven insights with specific numbers and percentages.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        result = {
            "trends": [{"title": "Analysis Complete", "description": text[:500]}],
            "revenue_prediction": [],
            "risks": [],
            "recommendations": [],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {exc}")

    # Store the analysis
    await db.ai_analytics_reports.insert_one(
        {
            "report_id": f"rpt_{uuid.uuid4().hex[:10]}",
            "type": "trend_detection",
            "context": context,
            "result": result,
            "created_at": _now_iso(),
            "created_by": admin.user_id,
        }
    )

    return {
        "analysis": result,
        "context_summary": {
            "total_users": total_users,
            "paid_users": paid_users,
            "revenue": total_revenue,
            "wallets": total_wallets,
        },
        "generated_at": _now_iso(),
    }


# ── AI Intrusion Detection ──


@router.get("/intrusion-detection")
async def ai_intrusion_detection(req: Request):
    """AI-based behavioral anomaly detection using security events."""
    await require_admin(req)

    now = _now()
    last_24h = (now - timedelta(hours=24)).isoformat()
    last_7d = (now - timedelta(days=7)).isoformat()

    # Gather security signals
    failed_logins = await db.security_events.count_documents(
        {"event_type": "login_failed", "timestamp": {"$gte": last_24h}}
    )
    blocked_ips = await db.security_blocks.count_documents({"blocked_until": {"$gt": now}})
    jwt_invalids = await db.security_events.count_documents(
        {"event_type": "jwt_invalid", "timestamp": {"$gte": last_24h}}
    )
    admin_denials = await db.security_events.count_documents(
        {"event_type": "admin_access_denied", "timestamp": {"$gte": last_24h}}
    )
    rate_limits = await db.security_events.count_documents(
        {"event_type": "login_rate_limit", "timestamp": {"$gte": last_24h}}
    )

    # IP analysis - most active IPs
    ip_pipeline = [
        {"$match": {"timestamp": {"$gte": last_24h}, "ip_address": {"$ne": None}}},
        {"$group": {"_id": "$ip_address", "count": {"$sum": 1}, "types": {"$addToSet": "$event_type"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_ips = await db.security_events.aggregate(ip_pipeline).to_list(10)

    # Fraud flags from Platform
    fraud_flags = await db.platform_fraud_flags.count_documents({"status": "pending_review"})
    high_risk_txs = await db.platform_transactions.count_documents(
        {"risk_score": {"$gt": 0.7}, "created_at": {"$gte": last_7d}}
    )

    # Security alerts sent
    alerts_sent = await db.security_alerts.count_documents({"sent_at": {"$gte": last_24h}})

    # Threat level calculation
    threat_score = min(
        100,
        (failed_logins * 2)
        + (blocked_ips * 10)
        + (jwt_invalids * 5)
        + (admin_denials * 15)
        + (rate_limits * 3)
        + (fraud_flags * 20)
        + (high_risk_txs * 8),
    )
    threat_level = (
        "critical"
        if threat_score >= 80
        else "high"
        if threat_score >= 50
        else "medium"
        if threat_score >= 20
        else "low"
    )

    # Suspicious IPs (those with multiple event types including failures)
    suspicious_ips = [
        ip
        for ip in top_ips
        if len(ip.get("types", [])) >= 2
        and any(t in ip.get("types", []) for t in ["login_failed", "jwt_invalid", "admin_access_denied"])
    ]

    return {
        "threat_level": threat_level,
        "threat_score": threat_score,
        "signals": {
            "failed_logins_24h": failed_logins,
            "blocked_ips": blocked_ips,
            "jwt_invalid_24h": jwt_invalids,
            "admin_denials_24h": admin_denials,
            "rate_limits_24h": rate_limits,
            "fraud_flags_pending": fraud_flags,
            "high_risk_transactions_7d": high_risk_txs,
            "alerts_sent_24h": alerts_sent,
        },
        "top_ips": [{"ip": ip["_id"], "events": ip["count"], "types": ip["types"]} for ip in top_ips],
        "suspicious_ips": [{"ip": ip["_id"], "events": ip["count"], "types": ip["types"]} for ip in suspicious_ips],
        "checked_at": _now_iso(),
    }
