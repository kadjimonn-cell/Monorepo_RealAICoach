"""
scheduler_jobs.compliance — Financial / tax compliance + daily usage summary jobs.

**Phase 2 incremental domain split — batch #21.**

Owns scheduled jobs that touch financial-compliance integrity and
user-facing daily-summary email engagement for free/basic users.

Jobs in this module
===================
- ``scheduled_tax_compliance_audit`` — sampled payment-transaction
  integrity sweep with safe autofix for canonical financial fields.
- ``scheduled_daily_usage_summary`` — daily summary email to active
  free/basic users with usage stats + upgrade nudges.
"""

import logging
from datetime import datetime, timedelta, timezone

from scheduler_jobs.observability import _record_scheduler_heartbeat  # noqa: F401
from utils.pagination import iter_find_paginated
from shared.pricing_policy import get_monthly_price_label, get_plan_name


logger = logging.getLogger("scheduler_jobs.compliance")


async def scheduled_tax_compliance_audit():
    """Scheduled financial/tax integrity audit with safe autofix for missing canonical fields."""
    try:
        from routes.db import db

        sample_size = 400
        docs = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).limit(sample_size).to_list(sample_size)
        scanned = len(docs)
        fixed = 0
        for tx in docs:
            update = {}
            provider_l = str(tx.get("provider") or tx.get("gateway") or tx.get("payment_method") or "").lower()
            if tx.get("provider") is None:
                update["provider"] = tx.get("gateway") or tx.get("payment_method") or "unknown"
            if tx.get("subtotal") is None:
                update["subtotal"] = float(tx.get("amount", tx.get("amount_usd", 0)) or 0)
            if tx.get("tax_amount") is None:
                update["tax_amount"] = 0.0
            if tx.get("processing_fee") is None:
                update["processing_fee"] = float(tx.get("fee", tx.get("fee_local", 0)) or 0)
            subtotal = float(tx.get("subtotal", tx.get("amount", tx.get("amount_usd", 0)) or 0) or 0)
            tax_amount = float(tx.get("tax_amount", 0) or 0)
            fee = float(tx.get("processing_fee", tx.get("fee", tx.get("fee_local", 0)) or 0) or 0)
            if tx.get("amount_gross") is None:
                update["amount_gross"] = round(subtotal + tax_amount, 2)
            if tx.get("total_amount") is None:
                update["total_amount"] = round(subtotal + tax_amount, 2)
            if tx.get("amount_net") is None:
                update["amount_net"] = round(max((subtotal + tax_amount) - fee, 0), 2)
            if tx.get("jurisdiction") is None:
                update["jurisdiction"] = {"country": "US", "state": "", "postal_code": ""}
            if tx.get("product_type") is None:
                update["product_type"] = "education_digital_service"

            if provider_l in {"fedapay", "mobile_money_fedapay"}:
                subtotal = float(tx.get("subtotal", tx.get("amount", tx.get("amount_local", 0)) or 0) or 0)
                expected_tax = round(subtotal * 0.0825, 2)
                fee = float(tx.get("processing_fee", tx.get("fee", tx.get("fee_local", 0)) or 0) or 0)
                fee_pass_through = bool(tx.get("fee_pass_through", True))
                gross = round(subtotal + expected_tax, 2)
                total = round(gross + fee, 2) if fee_pass_through else gross
                net = round(max(total - fee, 0), 2)
                if abs(float(tx.get("tax_amount", 0) or 0) - expected_tax) > 0.01 or abs(float(tx.get("tax_rate", 0) or 0) - 0.0825) > 1e-6 or str(tx.get("tax_provider", "")).lower() != "fedapay_fixed_rate":
                    update.update(
                        {
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
                                }
                            ],
                            "subtotal": subtotal,
                            "amount_gross": gross,
                            "total_amount": total,
                            "amount_net": net,
                            "processing_fee": fee,
                        }
                    )

            if not update:
                continue

            await db.payment_transactions.update_one(
                {"transaction_id": tx.get("transaction_id")} if tx.get("transaction_id") else {"session_id": tx.get("session_id")},
                {"$set": {**update, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            fixed += 1

        await db.tax_compliance_audit_history.insert_one(
            {
                "report_id": f"tax_sched_{int(datetime.now(timezone.utc).timestamp())}",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "scheduled_tax_compliance_audit",
                "scanned_transactions": scanned,
                "auto_fixed_transactions": fixed,
                "health_score": int(round(((scanned - fixed) / scanned) * 100)) if scanned else 100,
            }
        )
        logger.info("Scheduled tax compliance audit complete: scanned=%s fixed=%s", scanned, fixed)
    except Exception as e:
        logger.error(f"scheduled_tax_compliance_audit failed: {e}")


async def scheduled_daily_usage_summary():
    """Send daily usage summary email to active free/basic users at end of day."""
    logger.info("Running daily usage summary email job...")
    try:
        from routes.db import db
        from routes.payments_catalog import get_subscription_plan_from_gps
        from utils.email_service import is_email_configured, render_email_logo, send_catalog_template

        if not is_email_configured():
            logger.info("Email not configured, skipping daily usage summary.")
            return

        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        active_progress = []
        async for progress_row in iter_find_paginated(
            db.progress,
            {"last_conversation_date": today, "daily_conversations": {"$gt": 0}},
            {"_id": 0, "user_id": 1, "daily_conversations": 1, "total_conversations": 1},
            max_docs=5000,
        ):
            active_progress.append(progress_row)

        if not active_progress:
            logger.info("No active users today, skipping daily summary.")
            return

        user_ids = [p["user_id"] for p in active_progress]
        progress_map = {p["user_id"]: p for p in active_progress}

        users = []
        async for user_row in iter_find_paginated(
            db.users,
            {
                "user_id": {"$in": user_ids},
                "subscription_plan": {"$in": ["free", "basic", None]},
                "is_active": True,
            },
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1},
            max_docs=5000,
        ):
            users.append(user_row)

        unsubs = set()
        async for u in iter_find_paginated(
            db.email_unsubscribes,
            {"type": "daily_summary"},
            {"_id": 0, "email": 1},
            max_docs=5000,
        ):
            unsubs.add(u.get("email", ""))

        sent = 0
        for user in users:
            email = user.get("email")
            if not email or email in unsubs:
                continue

            uid = user["user_id"]
            prog = progress_map.get(uid, {})
            plan = user.get("subscription_plan") or "free"
            plan_config = await get_subscription_plan_from_gps(plan, default_plan_id="free") or {}
            daily_used = prog.get("daily_conversations", 0)
            daily_limit = plan_config.get("daily_conversation_limit", 3)
            total = prog.get("total_conversations", 0)
            name = user.get("name", "there")
            name.split()[0] if name else "there"

            streak = 1
            try:
                (now - timedelta(days=1)).strftime("%Y-%m-%d")
                prev_progress = await db.progress.find_one(
                    {"user_id": uid}, {"_id": 0, "streak_count": 1}
                )
                streak = (prev_progress or {}).get("streak_count", 1)
            except Exception:
                pass

            if plan == "free":
                upgrade_plan = get_plan_name("basic")
                upgrade_price = get_monthly_price_label("basic")
                upgrade_features = [
                    "10 conversations per day (vs 3)",
                    "All practice scenarios",
                    "Progress tracking & insights",
                    "PDF session exports",
                ]
            else:
                upgrade_plan = get_plan_name("premium")
                upgrade_price = get_monthly_price_label("premium")
                upgrade_features = [
                    "Unlimited conversations",
                    "Advanced analytics & AI insights",
                    "Personalized improvement plans",
                    "Priority support",
                ]

            limit_display = str(daily_limit) if daily_limit > 0 else "Unlimited"
            pct = round(daily_used / max(daily_limit, 1) * 100) if daily_limit > 0 else 0
            bar_color = "#10B981" if pct < 50 else ("#F59E0B" if pct < 80 else "#EF4444")
            bar_width = min(pct, 100) if daily_limit > 0 else 15

            render_email_logo(variant="compact")

            try:
                await send_catalog_template(
                    recipient_email=email,
                    template_key="daily_usage_summary",
                    recipient_name=name,
                    user_name=name,
                    daily_used=daily_used,
                    streak=streak,
                    total=total,
                    limit_display=str(limit_display),
                    bar_width=bar_width,
                    bar_color=bar_color,
                    upgrade_plan=upgrade_plan,
                    upgrade_price=upgrade_price,
                    features=upgrade_features,
                )
                sent += 1
            except Exception as e:
                logger.warning(f"Daily summary email failed for {email}: {e}")

        logger.info(f"Daily usage summary: sent {sent} emails to {len(users)} eligible users")
    except Exception as e:
        logger.error(f"Daily usage summary job failed: {e}")


__all__ = [
    "scheduled_tax_compliance_audit",
    "scheduled_daily_usage_summary",
]
