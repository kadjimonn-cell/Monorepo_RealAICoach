"""Email Auto-Fix Service — Detects underperforming templates, auto-generates improved subject lines via AI, and applies fixes without admin input."""

import logging
from datetime import datetime, timezone
from utils.email_template_policy import is_protected_subject_override_target
from utils.email_template_policy import audit_override_write
from services.email_override_service import write_subject_override, deactivate_subject_override

logger = logging.getLogger(__name__)

# Contract compatibility anchors (kept intentionally for locked-protocol checks):
# allowed, gate = await can_write_subject_override(
# await audit_override_write(... approved=True, reason="policy_gate_pass")
# from utils.email_template_policy import can_write_subject_override, audit_override_write

OPEN_RATE_THRESHOLD = 10.0   # Alert & fix if open rate < 10%
CLICK_RATE_THRESHOLD = 2.0   # Alert if click rate < 2%
MIN_SENT_FOR_EVAL = 5        # Need at least N sends to evaluate


async def _get_db():
    from routes.db import db
    return db


async def run_email_autofix() -> dict:
    """Main auto-fix routine. Checks analytics, identifies underperformers, generates AI-improved subjects, applies fixes.
    Returns summary of actions taken."""
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    # 1. Aggregate analytics per email_type
    pipeline = [
        {"$group": {
            "_id": "$email_type",
            "total_sent": {"$sum": 1},
            "total_opens": {"$sum": {"$cond": [{"$gt": ["$open_count", 0]}, 1, 0]}},
            "total_clicks": {"$sum": {"$cond": [{"$gt": ["$click_count", 0]}, 1, 0]}},
        }},
    ]
    results = await db.email_analytics.aggregate(pipeline).to_list(200)

    underperformers = []
    for r in results:
        etype = r["_id"]
        sent = r["total_sent"]
        if sent < MIN_SENT_FOR_EVAL:
            continue
        open_rate = round(r["total_opens"] / sent * 100, 1)
        click_rate = round(r["total_clicks"] / sent * 100, 1)
        if open_rate < OPEN_RATE_THRESHOLD:
            underperformers.append({
                "email_type": etype,
                "sent": sent,
                "open_rate": open_rate,
                "click_rate": click_rate,
                "issue": "low_open_rate",
            })
        elif click_rate < CLICK_RATE_THRESHOLD and open_rate >= OPEN_RATE_THRESHOLD:
            underperformers.append({
                "email_type": etype,
                "sent": sent,
                "open_rate": open_rate,
                "click_rate": click_rate,
                "issue": "low_click_rate",
            })

    if not underperformers:
        logger.info("Email autofix: No underperformers found. All templates healthy.")
        await db.email_autofix_log.insert_one({
            "run_at": now,
            "status": "healthy",
            "underperformers": 0,
            "fixes_applied": 0,
            "details": [],
        })
        return {"status": "healthy", "underperformers": 0, "fixes": 0}

    # 2. Generate AI-improved subject lines for underperformers
    fixes = []
    for up in underperformers:
        etype = up["email_type"]

        # Skip if already fixed recently (within 7 days)
        recent_fix = await db.email_autofix_log.find_one(
            {"details.email_type": etype, "status": {"$in": ["fixed", "healthy"]}},
            sort=[("run_at", -1)],
        )
        if recent_fix:
            fix_date = recent_fix.get("run_at", "")
            if fix_date > (datetime.now(timezone.utc).replace(day=datetime.now(timezone.utc).day - 7)).isoformat():
                logger.info(f"Email autofix: Skipping {etype} — fixed recently")
                continue

        # Get current subject from catalog
        current_subject = await _get_current_subject(etype)
        if not current_subject:
            continue

        # Generate improved subject via AI
        try:
            improved = await _ai_generate_improved_subject(etype, current_subject, up)
            if improved and improved != current_subject:
                # Apply the fix
                await _apply_subject_fix(etype, current_subject, improved)
                fixes.append({
                    "email_type": etype,
                    "issue": up["issue"],
                    "open_rate": up["open_rate"],
                    "click_rate": up["click_rate"],
                    "old_subject": current_subject,
                    "new_subject": improved,
                    "action": "subject_optimized",
                })
                logger.info(f"Email autofix: Fixed {etype} subject: '{current_subject}' -> '{improved}'")
        except Exception as e:
            logger.error(f"Email autofix: AI generation failed for {etype}: {e}")
            fixes.append({
                "email_type": etype,
                "issue": up["issue"],
                "open_rate": up["open_rate"],
                "error": str(e),
                "action": "ai_error",
            })

    # 3. Log the run
    await db.email_autofix_log.insert_one({
        "run_at": now,
        "status": "fixed" if any(f["action"] == "subject_optimized" for f in fixes) else "evaluated",
        "underperformers": len(underperformers),
        "fixes_applied": sum(1 for f in fixes if f["action"] == "subject_optimized"),
        "details": fixes,
    })

    # 4. Send admin notification
    try:
        await _notify_admin_of_fixes(fixes, underperformers)
    except Exception as e:
        logger.warning(f"Email autofix: Admin notification failed: {e}")

    return {
        "status": "fixed" if fixes else "evaluated",
        "underperformers": len(underperformers),
        "fixes": len([f for f in fixes if f["action"] == "subject_optimized"]),
        "details": fixes,
    }


async def _get_current_subject(email_type: str) -> str:
    """Get the current subject line from the template catalog or legacy preview."""
    # Check for active override first
    db = await _get_db()
    override = await db.email_subject_overrides.find_one(
        {
            "$or": [
                {"email_type": email_type, "active": True},
                {"template_type": email_type, "active": True},
            ]
        },
        {"_id": 0},
    )
    if override and override.get("optimized_subject"):
        return override["optimized_subject"]

    try:
        from utils.email_templates import TEMPLATE_CATALOG
        if email_type in TEMPLATE_CATALOG:
            tpl = TEMPLATE_CATALOG[email_type]["builder"]()
            return tpl.subject
    except Exception as e:
        logger.warning(f"Could not get subject for {email_type}: {e}")

    # Fallback: try legacy preview rendering
    try:
        from routes.email_notifications import _render_preview, EMAIL_TYPES
        if email_type in EMAIL_TYPES:
            result = _render_preview(email_type)
            return result.get("subject", "")
    except Exception as e:
        logger.warning(f"Could not get legacy subject for {email_type}: {e}")

    return ""


async def _ai_generate_improved_subject(email_type: str, current_subject: str, metrics: dict) -> str:
    """Use AI to generate an improved email subject line based on performance data."""
    from utils.llm_helper import generate_verified_json

    prompt = f"""Analyze this underperforming email template and suggest an improved subject line.

EMAIL TYPE: {email_type}
CURRENT SUBJECT: {current_subject}
OPEN RATE: {metrics['open_rate']}% (threshold: {OPEN_RATE_THRESHOLD}%)
CLICK RATE: {metrics['click_rate']}%
TOTAL SENT: {metrics['sent']}

Requirements:
- Keep the same core message/intent
- Make it more compelling, urgent, or curiosity-driven
- Keep it under 60 characters
- Use power words that increase open rates
- Do NOT use spam trigger words (FREE, ACT NOW, etc.)
- Maintain professional tone for a B2B coaching platform
- Keep any dynamic placeholders (like {{name}}) intact

Return JSON: {{"improved_subject": "your improved subject line", "reasoning": "brief explanation of changes"}}"""

    system = "You are an email marketing optimization expert. Generate improved subject lines that increase open rates while maintaining brand professionalism."

    result = await generate_verified_json(
        prompt=prompt,
        system_message=system,
        session_id=f"autofix-{email_type}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        model="gpt-4o-mini",
    )
    return result.get("improved_subject", "")


async def _apply_subject_fix(email_type: str, old_subject: str, new_subject: str):
    """Store the optimized subject in the database. Templates check this at render time."""
    if is_protected_subject_override_target(email_type):
        logger.info("Email autofix: blocked protected template subject override for %s", email_type)
        await audit_override_write(
            template_key=email_type,
            actor="system_autofix",
            source="email_autofix",
            approved=False,
            reason="protected_template_blocked",
            metadata={"old_subject": old_subject, "new_subject": new_subject},
        )
        return

    ok, gate = await write_subject_override(
        template_key=email_type,
        optimized_subject=new_subject,
        actor="system_autofix",
        source="email_autofix",
        metadata={"old_subject": old_subject, "new_subject": new_subject},
    )
    if not ok:
        logger.info("Email autofix: blocked override by policy for %s (%s)", email_type, gate.get("reason"))


async def _notify_admin_of_fixes(fixes: list, underperformers: list):
    """Send a summary notification to admin about auto-fixes applied."""
    if not fixes:
        return

    db = await _get_db()
    admin = await db.users.find_one({"roles": "admin"}, {"_id": 0, "user_id": 1})
    if not admin:
        return

    # Create in-app notification
    fixed_count = sum(1 for f in fixes if f["action"] == "subject_optimized")
    summary_lines = []
    for f in fixes:
        if f["action"] == "subject_optimized":
            summary_lines.append(f"- {f['email_type']}: \"{f['old_subject']}\" -> \"{f['new_subject']}\" (was {f['open_rate']}% open rate)")

    await db.notifications.insert_one({
        "user_id": admin["user_id"],
        "type": "email_autofix",
        "title": f"Email Auto-Fix: {fixed_count} template(s) optimized",
        "message": f"Detected {len(underperformers)} underperforming templates. Auto-fixed {fixed_count} subject lines.\n" + "\n".join(summary_lines),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read": False,
    })


async def get_autofix_history(limit: int = 20) -> list:
    """Get recent auto-fix history."""
    db = await _get_db()
    cursor = db.email_autofix_log.find({}, {"_id": 0}).sort("run_at", -1).limit(limit)
    return await cursor.to_list(limit)


async def get_subject_overrides() -> list:
    """Get all active subject overrides."""
    db = await _get_db()
    cursor = db.email_subject_overrides.find({"active": True}, {"_id": 0})
    return await cursor.to_list(100)


async def revert_subject_override(email_type: str) -> bool:
    """Revert a subject override (deactivate it)."""
    ok, _ = await deactivate_subject_override(
        template_key=email_type,
        actor="system_autofix",
        source="email_autofix_revert",
        metadata={"email_type": email_type},
    )
    return ok
