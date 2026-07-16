"""scheduler_jobs.engagement — User engagement / referral / lifecycle jobs.

**Phase 2 batch #15.**

Jobs: weekly engagement emails, referral weekly email, card-expiry check,
welcome-back check. All function bodies are byte-identical to the
originals in `_legacy.py`.
"""

import logging
from datetime import datetime, timedelta, timezone

from utils.pagination import iter_find_paginated
from scheduler_jobs.observability import _record_scheduler_heartbeat
from shared.pricing_policy import get_plan_amount, get_plan_name, get_monthly_price_label

logger = logging.getLogger("scheduler_jobs.engagement")


async def scheduled_weekly_engagement_emails():
    """Send weekly engagement summary emails to active users."""
    logger.info("Running weekly engagement emails...")
    try:
        from utils.email_notifications import notify
        from routes.db import db

        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        active_users = await db.users.find(
            {"subscription_status": {"$in": ["active", "trial"]}, "access_locked": {"$ne": True}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(500)
        sent = 0
        for u in active_users:
            uid = u.get("user_id", "")
            sessions = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": seven_days_ago}})
            progress_doc = await db.user_progress.find_one({"user_id": uid}, {"_id": 0})
            skills = progress_doc.get("skills", {}) if progress_doc else {}
            avg_score = round(sum(skills.values()) / max(len(skills), 1)) if skills else 0
            highlights = []
            if sessions > 0:
                highlights.append(f"You completed {sessions} coaching session{'s' if sessions > 1 else ''}")
            if avg_score > 0:
                highlights.append(f"Your skill score is {avg_score}%")
            highlights.append("Keep the momentum going!")
            stats = [f"{sessions} sessions", f"{avg_score}% skill avg"]
            await notify.weekly_engagement(uid, u["email"], u.get("name", "User"), highlights, stats)
            sent += 1
        logger.info(f"Weekly engagement emails sent: {sent}")
    except Exception as e:
        logger.error(f"Weekly engagement emails failed: {e}")


async def scheduled_smart_weekly_digest():
    """Send the smart weekly digest (coaching progress + streaks) to opted-in users."""
    try:
        from routes.digest import dispatch_smart_weekly_digests

        summary = await dispatch_smart_weekly_digests()
        logger.info(f"Smart weekly digest job complete: {summary}")
    except Exception as e:
        logger.error(f"Smart weekly digest job failed: {e}")
    await _record_scheduler_heartbeat("smart_weekly_digest_dispatch")


async def scheduled_referral_weekly_email():
    """Send weekly referral program digest emails with tier, rank, and progress."""
    from routes.db import db
    from utils.email_templates import _wrap
    from utils.email_service import is_email_configured, send_catalog_template

    try:
        users = []
        async for user_row in iter_find_paginated(
            db.users,
            {"email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
            max_docs=10000,
        ):
            users.append(user_row)

        if not users:
            logger.info("Referral weekly: no users to email")
            return

        # Pre-compute leaderboard rankings
        all_codes = []
        async for code_row in iter_find_paginated(
            db.referral_codes,
            {},
            {"_id": 0, "user_id": 1, "total_signups": 1},
            sort=[("total_signups", -1)],
            max_docs=10000,
        ):
            all_codes.append(code_row)
        rank_map = {}
        for i, c in enumerate(all_codes):
            rank_map[c["user_id"]] = i + 1
        total_participants = len(all_codes)

        # Tier definitions
        TIERS = [
            {"id": "bronze", "name": "Bronze", "min_referrals": 1, "commission": 0.30, "color": "#CD7F32"},
            {"id": "silver", "name": "Silver", "min_referrals": 6, "commission": 0.35, "color": "#C0C0C0"},
            {"id": "gold", "name": "Gold", "min_referrals": 16, "commission": 0.40, "color": "#FFD700"},
        ]
        STARTER = {"id": "starter", "name": "Starter", "min_referrals": 0, "commission": 0.30, "color": "#6B7280"}

        def get_tier(count):
            t = STARTER
            for tier in TIERS:
                if count >= tier["min_referrals"]:
                    t = tier
            return t

        def get_next_tier(count):
            for tier in TIERS:
                if count < tier["min_referrals"]:
                    return tier
            return None

        sent = 0
        for user in users:
            uid = user.get("user_id", "")
            name = user.get("name", "User")
            email = user.get("email", "")
            if not email:
                continue

            import hashlib

            code_hash = hashlib.md5(uid.encode()).hexdigest()[:6].upper()
            code = f"RAC-{code_hash}"

            ref_doc = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0})
            total_refs = ref_doc.get("total_signups", 0) if ref_doc else 0

            events = await db.referral_events.find({"referrer_id": uid}, {"_id": 0}).to_list(500)
            total_earnings = sum(e.get("commission_earned", 0) for e in events)
            active_subs = sum(1 for e in events if e.get("status") == "subscribed")

            tier = get_tier(total_refs)
            next_tier = get_next_tier(total_refs)
            rank = rank_map.get(uid, total_participants)
            commission_pct = int(tier["commission"] * 100)

            # Tier progress bar
            max_refs = 16
            progress_pct = min(int((total_refs / max_refs) * 100), 100)
            basic_price = get_plan_amount("basic", "monthly")
            premium_price = get_plan_amount("premium", "monthly")
            basic_label = f"{get_plan_name('basic')} Plan ({get_monthly_price_label('basic')})"
            premium_label = f"{get_plan_name('premium')} Plan ({get_monthly_price_label('premium')})"

            # Next tier section
            next_tier_html = ""
            if next_tier:
                needed = next_tier["min_referrals"] - total_refs
                next_tier_html = f"""
                <div style="background:#F8FAFC;border:1px solid {next_tier["color"]}33;border-radius:12px;padding:16px;margin-top:12px;">
                  <div style="color:#94A3B8;font-size:11px;font-weight:600;text-transform:uppercase;">Next Tier: {next_tier["name"]}</div>
                  <div style="color:{next_tier["color"]};font-size:18px;font-weight:800;margin-top:4px;">
                    {needed} more referral{"s" if needed != 1 else ""} to unlock {int(next_tier["commission"] * 100)}% commission
                  </div>
                </div>
                """

            body = f"""
            <tr><td style="padding:32px 28px 0;">
              <div style="font-size:24px;font-weight:800;color:#0F172A;letter-spacing:-0.5px;">
                Hi {name}!
              </div>
              <div style="color:#94A3B8;font-size:14px;margin-top:8px;line-height:22px;">
                Your weekly referral digest is here. Here's how you're doing.
              </div>
            </td></tr>

            <!-- Tier & Rank -->
            <tr><td style="padding:24px 28px 0;">
              <div style="background:#F1F5F9;border-radius:14px;padding:24px;border:1px solid {tier["color"]}40;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="width:70px;vertical-align:top;">
                      <div style="width:60px;height:60px;border-radius:30px;background:{tier["color"]}18;border:2px solid {tier["color"]}40;text-align:center;line-height:60px;font-size:28px;">
                        &#x1F6E1;
                      </div>
                    </td>
                    <td style="vertical-align:top;">
                      <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Your Tier</div>
                      <div style="color:{tier["color"]};font-size:26px;font-weight:900;letter-spacing:-0.5px;">{tier["name"]}</div>
                      <div style="color:#94A3B8;font-size:12px;margin-top:2px;">{commission_pct}% commission rate</div>
                    </td>
                    <td style="text-align:right;vertical-align:top;">
                      <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Rank</div>
                      <div style="color:#0F172A;font-size:28px;font-weight:900;">#{rank}</div>
                      <div style="color:#64748B;font-size:10px;">of {total_participants}</div>
                    </td>
                  </tr>
                </table>

                <!-- Progress bar -->
                <div style="margin-top:16px;">
                  <div style="color:#94A3B8;font-size:11px;margin-bottom:6px;">{total_refs} referrals &middot; {progress_pct}% to Gold</div>
                  <div style="height:8px;background:#F8FAFC;border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:{max(progress_pct, 3)}%;background:{tier["color"]};border-radius:4px;"></div>
                  </div>
                </div>

                {next_tier_html}
              </div>
            </td></tr>

            <!-- Stats -->
            <tr><td style="padding:24px 28px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:33%;padding:6px;">
                    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #2563EB;">
                      <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Referrals</div>
                      <div style="color:#0F172A;font-size:28px;font-weight:800;margin-top:4px;">{total_refs}</div>
                    </div>
                  </td>
                  <td style="width:33%;padding:6px;">
                    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #059669;">
                      <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Active Subs</div>
                      <div style="color:#0F172A;font-size:28px;font-weight:800;margin-top:4px;">{active_subs}</div>
                    </div>
                  </td>
                  <td style="width:33%;padding:6px;">
                    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #8B5CF6;">
                      <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Earned</div>
                      <div style="color:#0F172A;font-size:28px;font-weight:800;margin-top:4px;">${total_earnings:.2f}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td></tr>

            <!-- Referral Code -->
            <tr><td style="padding:24px 28px 0;">
              <div style="background:#F1F5F9;border-radius:12px;padding:18px;border:1px solid #CBD5E1;">
                <div style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Your Referral Code</div>
                <div style="color:#2563EB;font-size:22px;font-weight:800;letter-spacing:2px;">{code}</div>
              </div>
            </td></tr>

            <!-- Commission Structure (tier-aware) -->
            <tr><td style="padding:24px 28px 0;">
              <div style="background:#F1F5F9;border-radius:12px;padding:20px;border:1px solid #CBD5E1;">
                <div style="color:#0F172A;font-size:14px;font-weight:700;margin-bottom:12px;">Your Commission ({tier["name"]} Tier - {commission_pct}%)</div>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:8px 0;border-bottom:1px solid #334155;">
                      <span style="color:#94A3B8;font-size:13px;">{basic_label}</span>
                    </td>
                    <td style="padding:8px 0;border-bottom:1px solid #334155;text-align:right;">
                      <span style="color:#059669;font-size:14px;font-weight:700;">${basic_price * tier["commission"]:.2f}/mo per referral</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;">
                      <span style="color:#94A3B8;font-size:13px;">{premium_label}</span>
                    </td>
                    <td style="padding:8px 0;text-align:right;">
                      <span style="color:#8B5CF6;font-size:14px;font-weight:700;">${premium_price * tier["commission"]:.2f}/mo per referral</span>
                    </td>
                  </tr>
                </table>
              </div>
            </td></tr>

            <tr><td style="padding:28px 28px 0;text-align:center;">
              <a href="https://realaicoach.app/referrals" style="display:inline-block;background:{tier["color"]};color:#ffffff;font-size:16px;font-weight:700;padding:16px 40px;border-radius:12px;text-decoration:none;">
                View My Referral Dashboard
              </a>
            </td></tr>

            <tr><td style="padding:24px 28px 0;">
              <div style="color:#475569;font-size:12px;line-height:18px;text-align:center;">
                Share your link to earn more. Upgrade to {next_tier["name"] if next_tier else "Gold"} for higher commissions!
              </div>
            </td></tr>
            """

            _wrap("Your Weekly Referral Digest", "Your referral stats for this week", body)

            if is_email_configured():
                await send_catalog_template(
                    recipient_email=email,
                    template_key="referral_digest",
                    recipient_name=name,
                    user_name=name,
                    rank=rank,
                    total_refs=total_refs,
                    active_subs=active_subs,
                    total_earnings=total_earnings,
                    code=code,
                    tier_name=tier["name"],
                    tier_color=tier["color"],
                    commission_pct=commission_pct,
                    basic_commission=5.99 * tier["commission"],
                    premium_commission=15.99 * tier["commission"],
                    next_tier_name=next_tier["name"] if next_tier else "Gold",
                )

            # Track email send
            await db.referral_email_sends.insert_one(
                {
                    "user_id": uid,
                    "email": email,
                    "type": "weekly_digest",
                    "tier": tier["id"],
                    "rank": rank,
                    "total_refs": total_refs,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            sent += 1

        logger.info(f"Referral weekly digest: sent {sent} emails")
    except Exception as e:
        logger.error(f"Referral weekly email failed: {e}")


async def scheduled_card_expiry_check():
    """Daily check for expiring payment cards. Sends payment_method_expiring emails."""
    job_id = "card_expiry_check"
    try:
        from routes.db import db
        from utils.email_service import send_catalog_template, is_email_configured
        if not is_email_configured():
            await _record_scheduler_heartbeat(job_id, "skipped", "Email not configured")
            return

        now = datetime.now(timezone.utc)
        sent = 0

        async for card in iter_find_paginated(
            db.payment_cards,
            {"is_default": True},
            {"_id": 0},
            max_docs=5000,
        ):
            exp_month = int(card.get("expiry_month", 0) or 0)
            exp_year = int(card.get("expiry_year", 0) or 0)
            if exp_year < 100:
                exp_year += 2000

            if exp_month == 0 or exp_year == 0:
                continue

            from calendar import monthrange
            last_day = monthrange(exp_year, exp_month)[1]
            expiry_date = datetime(exp_year, exp_month, last_day, tzinfo=timezone.utc)
            days_until = (expiry_date - now).days

            # Send at 30 days, 14 days, 7 days, 3 days, 1 day
            if days_until in (30, 14, 7, 3, 1):
                user_id = card.get("user_id", "")
                user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if user and user.get("email"):
                    # Check if already sent for this period
                    already = await db.card_expiry_notifications.find_one(
                        {"user_id": user_id, "days_until": days_until, "exp_month": exp_month, "exp_year": exp_year}
                    )
                    if already:
                        continue

                    await send_catalog_template(
                        recipient_email=user["email"],
                        template_key="payment_method_expiring",
                        recipient_name=user.get("name", ""),
                        user_name=user.get("name", "there"),
                        card_last4=card.get("last_four", card.get("masked_number", "****")[-4:]),
                        card_brand=card.get("card_type", "Card").title(),
                        expiry_month=exp_month,
                        expiry_year=exp_year,
                        days_until_expiry=days_until,
                    )
                    await db.card_expiry_notifications.insert_one(
                        {"user_id": user_id, "days_until": days_until, "exp_month": exp_month, "exp_year": exp_year, "sent_at": now.isoformat()}
                    )
                    sent += 1

        logger.info(f"[card-expiry] Sent {sent} expiry warnings")
        await _record_scheduler_heartbeat(job_id, "healthy", f"Sent {sent} expiry warnings")
    except Exception as exc:
        logger.error(f"Card expiry check failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_welcome_back_check():
    """Weekly check for users returning after 30+ days of inactivity. Sends welcome_back emails."""
    job_id = "welcome_back_check"
    try:
        from routes.db import db
        from utils.email_service import send_catalog_template, is_email_configured
        if not is_email_configured():
            await _record_scheduler_heartbeat(job_id, "skipped", "Email not configured")
            return

        now = datetime.now(timezone.utc)
        cutoff_30d = (now - timedelta(days=30)).isoformat()
        cutoff_7d = (now - timedelta(days=7)).isoformat()
        sent = 0

        # Users who logged in within the last 7 days but whose PREVIOUS login was 30+ days ago
        recent_users = await db.users.find(
            {"last_login_at": {"$gte": cutoff_7d}, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "last_login_at": 1, "previous_login_at": 1},
        ).to_list(1000)

        for u in recent_users:
            prev_login = u.get("previous_login_at", "")
            if not prev_login or prev_login > cutoff_30d:
                continue  # Was not inactive for 30+ days

            days_away = (now - datetime.fromisoformat(prev_login.replace("Z", "+00:00"))).days
            if days_away < 30:
                continue

            # Check if we already sent welcome_back for this return
            already = await db.welcome_back_notifications.find_one(
                {"user_id": u["user_id"], "return_period": u.get("last_login_at", "")[:10]}
            )
            if already:
                continue

            await send_catalog_template(
                recipient_email=u["email"],
                template_key="welcome_back",
                recipient_name=u.get("name", ""),
                user_name=u.get("name", "there"),
                days_away=days_away,
            )
            await db.welcome_back_notifications.insert_one(
                {"user_id": u["user_id"], "return_period": u.get("last_login_at", "")[:10], "sent_at": now.isoformat()}
            )
            sent += 1

        logger.info(f"[welcome-back] Sent {sent} welcome back emails")
        await _record_scheduler_heartbeat(job_id, "healthy", f"Sent {sent} welcome back emails")
    except Exception as exc:
        logger.error(f"Welcome back check failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_blog_v2_weekly_digest_cycle():
    """Generate in-app weekly digest + optional email digest for Blog V2 users."""
    job_id = "blog_v2_weekly_digest_cycle"
    try:
        from routes.db import db
        from services.blog_v2_engagement_service import (
            get_weekly_digest,
            send_weekly_digest_email,
        )

        users = await db.users.find(
            {
                "access_locked": {"$ne": True},
                "user_id": {"$exists": True, "$ne": ""},
            },
            {"_id": 0, "user_id": 1, "subscription_plan": 1},
        ).to_list(1200)

        generated = 0
        emailed = 0
        skipped = 0

        for user in users:
            owner_id = f"auth:{str(user.get('user_id') or '').strip()}"
            if owner_id == "auth:":
                skipped += 1
                continue

            plan = str(user.get("subscription_plan") or "free").strip().lower() or "free"
            digest = await get_weekly_digest(db, owner_id=owner_id, viewer_plan=plan, force_refresh=False)
            if digest:
                generated += 1

            engagement_doc = await db.blog_v2_engagement.find_one({"owner_id": owner_id}, {"_id": 0, "reminder_settings": 1})
            digest_settings = ((engagement_doc or {}).get("reminder_settings") or {}).get("digest") or {}
            email_enabled = bool(digest_settings.get("email_enabled", True))

            if email_enabled:
                result = await send_weekly_digest_email(db, owner_id=owner_id, viewer_plan=plan)
                if result.get("ok"):
                    emailed += 1
            else:
                skipped += 1

        detail = f"generated={generated} emailed={emailed} skipped={skipped}"
        await _record_scheduler_heartbeat(job_id, "healthy", detail)
        logger.info(f"[blog-v2-weekly-digest] {detail}")
    except Exception as exc:
        logger.error(f"blog_v2 weekly digest cycle failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_streak_protection_nudge():
    """Daily 18:00 UTC — warn users whose activity streak dies at UTC midnight."""
    job_id = "streak_protection_nudge"
    try:
        from routes.gamification import run_streak_protection_nudge

        result = await run_streak_protection_nudge()
        detail = f"notified={result.get('notified')} skipped={result.get('skipped')}"
        await _record_scheduler_heartbeat(job_id, "healthy", detail)
        logger.info(f"[streak-nudge] {detail}")
    except Exception as exc:
        logger.error(f"Streak protection nudge failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_weekly_engagement_emails",
    "scheduled_referral_weekly_email",
    "scheduled_streak_protection_nudge",
    "scheduled_card_expiry_check",
    "scheduled_welcome_back_check",
    "scheduled_blog_v2_weekly_digest_cycle",
]
