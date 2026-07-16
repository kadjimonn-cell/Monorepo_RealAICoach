"""Enterprise Ticket Escalation Engine.

Monitors ticket response times against SLA policies. Automatically escalates
through configurable levels (L1→L2→L3) using WebSocket alerts, email
notifications, and in-app banners.  Tracks all escalation events for audit
and analytics.
"""

import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request

from routes.db import db
from routes.admin_management import _require_admin

logger = logging.getLogger("routes.escalation_engine")
router = APIRouter(prefix="/escalation", tags=["Escalation Engine"])

# ──────────────────────────────────────────────────────────────
# Default SLA thresholds (minutes) by ticket priority
# ──────────────────────────────────────────────────────────────
DEFAULT_SLA = {
    "critical": {"l1": 10, "l2": 20, "l3": 30},
    "high": {"l1": 30, "l2": 60, "l3": 120},
    "medium": {"l1": 60, "l2": 180, "l3": 360},
    "low": {"l1": 240, "l2": 480, "l3": 1440},
}

DEFAULT_POLICY = {
    "_type": "escalation_policy",
    "enabled": False,
    "sla_thresholds": DEFAULT_SLA,
    "business_hours_only": False,
    "business_hours": {"start": 9, "end": 18, "timezone": "UTC"},
    "notifications": {
        "l1": {"websocket": True, "email": False},
        "l2": {"websocket": True, "email": True},
        "l3": {"websocket": True, "email": True},
    },
    "auto_reassign_on_l3": False,
}


# ══════════════════════════════════════════════════════════════
# ── API Endpoints ──
# ══════════════════════════════════════════════════════════════


@router.get("/policy")
async def get_escalation_policy(request: Request):
    """Return current escalation policy."""
    await _require_admin(request)
    policy = await db.escalation_config.find_one({"_type": "escalation_policy"}, {"_id": 0})
    return policy or DEFAULT_POLICY


@router.post("/policy")
async def update_escalation_policy(request: Request):
    """Create or update the escalation policy."""
    await _require_admin(request)
    body = await request.json()

    policy = {
        "_type": "escalation_policy",
        "enabled": bool(body.get("enabled", False)),
        "sla_thresholds": body.get("sla_thresholds", DEFAULT_SLA),
        "business_hours_only": bool(body.get("business_hours_only", False)),
        "business_hours": body.get("business_hours", DEFAULT_POLICY["business_hours"]),
        "notifications": body.get("notifications", DEFAULT_POLICY["notifications"]),
        "auto_reassign_on_l3": bool(body.get("auto_reassign_on_l3", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.escalation_config.update_one({"_type": "escalation_policy"}, {"$set": policy}, upsert=True)
    return {"ok": True, "policy": policy}


@router.get("/active")
async def get_active_escalations(request: Request):
    """Return all tickets with active (un-resolved) escalations."""
    await _require_admin(request)

    tickets = (
        await db.support_submissions.find(
            {
                "escalation_level": {"$gte": 1},
                "status": {"$nin": ["resolved", "closed"]},
            },
            {
                "_id": 0,
                "submission_id": 1,
                "ticket_number": 1,
                "subject": 1,
                "status": 1,
                "priority": 1,
                "category": 1,
                "created_at": 1,
                "last_admin_reply_at": 1,
                "escalation_level": 1,
                "escalation_history": 1,
                "assigned_to": 1,
                "assigned_agent_name": 1,
                "user_id": 1,
                "ai_classification": 1,
            },
        )
        .sort("escalation_level", -1)
        .to_list(200)
    )

    return {"escalations": tickets, "total": len(tickets)}


@router.get("/history")
async def get_escalation_history(request: Request):
    """Return the audit trail of all escalation events."""
    await _require_admin(request)
    limit = int(request.query_params.get("limit", "100"))
    events = await db.escalation_events.find({}, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    return {"events": events, "total": len(events)}


@router.get("/analytics")
async def get_escalation_analytics(request: Request):
    """Return escalation metrics."""
    await _require_admin(request)

    total_escalated = await db.support_submissions.count_documents({"escalation_level": {"$gte": 1}})
    active_escalated = await db.support_submissions.count_documents(
        {"escalation_level": {"$gte": 1}, "status": {"$nin": ["resolved", "closed"]}}
    )

    # By level
    by_level = {}
    for level in [1, 2, 3]:
        by_level[f"l{level}"] = await db.support_submissions.count_documents(
            {"escalation_level": level, "status": {"$nin": ["resolved", "closed"]}}
        )

    # Recent events (last 24h)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_events = await db.escalation_events.count_documents({"at": {"$gte": cutoff}})

    # Avg time to escalation (from recent events)
    avg_minutes = 0
    recent = await db.escalation_events.find({"at": {"$gte": cutoff}}, {"_id": 0, "minutes_elapsed": 1}).to_list(200)
    if recent:
        avg_minutes = round(sum(e.get("minutes_elapsed", 0) for e in recent) / len(recent), 1)

    # Breach rate: tickets that reached L3 / total escalated
    l3_count = await db.support_submissions.count_documents({"escalation_level": 3})
    breach_rate = round(l3_count / max(1, total_escalated) * 100, 1)

    # De-escalated (resolved after escalation)
    de_escalated = await db.support_submissions.count_documents(
        {"escalation_level": {"$gte": 1}, "status": {"$in": ["resolved", "closed"]}}
    )

    return {
        "total_escalated": total_escalated,
        "active_escalated": active_escalated,
        "de_escalated": de_escalated,
        "by_level": by_level,
        "recent_events_24h": recent_events,
        "avg_minutes_to_escalation": avg_minutes,
        "sla_breach_rate": breach_rate,
    }


@router.post("/snooze/{ticket_id}")
async def snooze_escalation(ticket_id: str, request: Request):
    """Snooze escalation for a ticket (reset timer, add grace minutes)."""
    admin = await _require_admin(request)
    body = await request.json()
    snooze_minutes = min(1440, max(5, int(body.get("minutes", 30))))

    now = datetime.now(timezone.utc)
    snooze_until = (now + timedelta(minutes=snooze_minutes)).isoformat()

    result = await db.support_submissions.update_one(
        {"submission_id": ticket_id},
        {
            "$set": {
                "escalation_snoozed_until": snooze_until,
                "updated_at": now.isoformat(),
            },
            "$push": {
                "escalation_history": {
                    "action": "snoozed",
                    "by": admin.user_id,
                    "by_name": admin.name,
                    "minutes": snooze_minutes,
                    "until": snooze_until,
                    "at": now.isoformat(),
                }
            },
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Audit event
    await db.escalation_events.insert_one(
        {
            "event_id": f"esc_{secrets.token_hex(6)}",
            "ticket_id": ticket_id,
            "action": "snoozed",
            "by": admin.user_id,
            "by_name": admin.name,
            "minutes": snooze_minutes,
            "at": now.isoformat(),
        }
    )

    return {"ok": True, "snoozed_until": snooze_until}


@router.post("/override/{ticket_id}")
async def override_escalation(ticket_id: str, request: Request):
    """Override/clear escalation for a ticket."""
    admin = await _require_admin(request)
    body = await request.json()
    reason = body.get("reason", "Manual override").strip()

    now = datetime.now(timezone.utc).isoformat()
    result = await db.support_submissions.update_one(
        {"submission_id": ticket_id},
        {
            "$set": {
                "escalation_level": 0,
                "escalation_snoozed_until": None,
                "updated_at": now,
            },
            "$push": {
                "escalation_history": {
                    "action": "overridden",
                    "by": admin.user_id,
                    "by_name": admin.name,
                    "reason": reason,
                    "at": now,
                }
            },
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await db.escalation_events.insert_one(
        {
            "event_id": f"esc_{secrets.token_hex(6)}",
            "ticket_id": ticket_id,
            "action": "overridden",
            "by": admin.user_id,
            "by_name": admin.name,
            "reason": reason,
            "at": now,
        }
    )

    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# ── Scheduler: Core Escalation Check ──
# ══════════════════════════════════════════════════════════════


async def run_escalation_check():
    """Called every 2 minutes by APScheduler.

    For each open ticket, computes how long since the last admin reply
    (or since creation if none). Compares against SLA thresholds to
    determine the correct escalation level. If the level has increased,
    fires notifications and records an audit event.
    """
    try:
        policy = await db.escalation_config.find_one({"_type": "escalation_policy"}, {"_id": 0})
        if not policy or not policy.get("enabled"):
            return

        sla = policy.get("sla_thresholds", DEFAULT_SLA)
        notif_cfg = policy.get("notifications", DEFAULT_POLICY["notifications"])

        # Business hours check
        now = datetime.now(timezone.utc)
        if policy.get("business_hours_only"):
            bh = policy.get("business_hours", {})
            current_hour = now.hour
            if current_hour < bh.get("start", 9) or current_hour >= bh.get("end", 18):
                return

        # Open tickets not resolved/closed
        open_tickets = await db.support_submissions.find(
            {"status": {"$nin": ["resolved", "closed"]}},
            {
                "_id": 0,
                "submission_id": 1,
                "ticket_number": 1,
                "subject": 1,
                "priority": 1,
                "category": 1,
                "created_at": 1,
                "last_admin_reply_at": 1,
                "escalation_level": 1,
                "escalation_snoozed_until": 1,
                "assigned_to": 1,
                "assigned_agent_name": 1,
                "user_id": 1,
                "ai_classification": 1,
            },
        ).to_list(500)

        escalated_count = 0
        for ticket in open_tickets:
            ticket_id = ticket["submission_id"]

            # Check snooze
            snooze_until = ticket.get("escalation_snoozed_until")
            if snooze_until:
                try:
                    if now < datetime.fromisoformat(snooze_until):
                        continue
                except Exception:
                    pass

            # Determine priority key
            prio = (ticket.get("ai_classification", {}).get("priority") or ticket.get("priority") or "medium").lower()
            if prio not in sla:
                prio = "medium"

            thresholds = sla[prio]

            # How long since last admin reply (or creation)
            ref_time_str = ticket.get("last_admin_reply_at") or ticket.get("created_at")
            if not ref_time_str:
                continue
            try:
                ref_time = datetime.fromisoformat(ref_time_str.replace("Z", "+00:00"))
                if ref_time.tzinfo is None:
                    ref_time = ref_time.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            elapsed_min = (now - ref_time).total_seconds() / 60
            current_level = ticket.get("escalation_level", 0)

            # Determine target level
            target_level = 0
            if elapsed_min >= thresholds.get("l3", 9999):
                target_level = 3
            elif elapsed_min >= thresholds.get("l2", 9999):
                target_level = 2
            elif elapsed_min >= thresholds.get("l1", 9999):
                target_level = 1

            if target_level > current_level:
                # ── ESCALATE ──
                now_iso = now.isoformat()
                level_key = f"l{target_level}"

                await db.support_submissions.update_one(
                    {"submission_id": ticket_id},
                    {
                        "$set": {
                            "escalation_level": target_level,
                            "escalation_snoozed_until": None,
                            "updated_at": now_iso,
                        },
                        "$push": {
                            "escalation_history": {
                                "action": f"escalated_to_l{target_level}",
                                "from_level": current_level,
                                "to_level": target_level,
                                "elapsed_minutes": round(elapsed_min, 1),
                                "threshold_minutes": thresholds.get(level_key, 0),
                                "priority": prio,
                                "by": "system",
                                "by_name": "Escalation Engine",
                                "at": now_iso,
                            },
                            "history": {
                                "action": f"escalated_to_l{target_level}",
                                "note": f"Auto-escalated to Level {target_level} ({prio} priority, {round(elapsed_min)}min without response)",
                                "by": "system",
                                "by_name": "Escalation Engine",
                                "at": now_iso,
                            },
                        },
                    },
                )

                # Audit event
                event = {
                    "event_id": f"esc_{secrets.token_hex(6)}",
                    "ticket_id": ticket_id,
                    "ticket_number": ticket.get("ticket_number"),
                    "subject": (ticket.get("subject") or "")[:80],
                    "action": f"escalated_to_l{target_level}",
                    "from_level": current_level,
                    "to_level": target_level,
                    "elapsed_minutes": round(elapsed_min, 1),
                    "threshold_minutes": thresholds.get(level_key, 0),
                    "priority": prio,
                    "assigned_to": ticket.get("assigned_to"),
                    "assigned_agent_name": ticket.get("assigned_agent_name"),
                    "at": now_iso,
                    "minutes_elapsed": round(elapsed_min, 1),
                }
                await db.escalation_events.insert_one(event)
                event.pop("_id", None)

                escalated_count += 1

                # ── Notifications ──
                level_notifs = notif_cfg.get(level_key, {})

                # WebSocket
                if level_notifs.get("websocket"):
                    await _ws_escalation_alert(ticket, target_level, elapsed_min, prio)

                # Email
                if level_notifs.get("email"):
                    await _email_escalation_alert(ticket, target_level, elapsed_min, prio)

                # Auto-reassign on L3
                if target_level == 3 and policy.get("auto_reassign_on_l3"):
                    await _attempt_reassign(ticket)

        if escalated_count:
            logger.info(f"Escalation engine: escalated {escalated_count} ticket(s)")

    except Exception as e:
        logger.error(f"Escalation engine error: {e}")


# ── De-escalation: called when admin replies ──
async def de_escalate_ticket(ticket_id: str, admin_name: str = "Admin"):
    """Reset escalation when admin responds to a ticket."""
    try:
        ticket = await db.support_submissions.find_one({"submission_id": ticket_id}, {"_id": 0, "escalation_level": 1})
        if not ticket or ticket.get("escalation_level", 0) == 0:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.support_submissions.update_one(
            {"submission_id": ticket_id},
            {
                "$set": {
                    "escalation_level": 0,
                    "escalation_snoozed_until": None,
                    "last_admin_reply_at": now_iso,
                    "updated_at": now_iso,
                },
                "$push": {
                    "escalation_history": {
                        "action": "de_escalated",
                        "by_name": admin_name,
                        "reason": "Admin replied",
                        "at": now_iso,
                    }
                },
            },
        )

        await db.escalation_events.insert_one(
            {
                "event_id": f"esc_{secrets.token_hex(6)}",
                "ticket_id": ticket_id,
                "action": "de_escalated",
                "reason": "Admin replied",
                "by_name": admin_name,
                "at": now_iso,
            }
        )
    except Exception as e:
        logger.error(f"De-escalation error for {ticket_id}: {e}")


# ── Notification helpers ──


async def _ws_escalation_alert(ticket: dict, level: int, elapsed: float, prio: str):
    """Push escalation alert via WebSocket to all admins."""
    try:
        from utils.ws_manager import ws_manager

        payload = {
            "type": "escalation_alert",
            "level": level,
            "ticket_id": ticket.get("submission_id"),
            "ticket_number": ticket.get("ticket_number"),
            "subject": (ticket.get("subject") or "")[:60],
            "priority": prio,
            "elapsed_minutes": round(elapsed),
            "assigned_to": ticket.get("assigned_agent_name") or ticket.get("assigned_to") or "Unassigned",
        }
        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(20)
        admin_ids = [a["user_id"] for a in admins]
        if admin_ids:
            await ws_manager.send_to_admins(payload, admin_ids)
    except Exception as e:
        logger.error(f"WS escalation alert failed: {e}")


async def _email_escalation_alert(ticket: dict, level: int, elapsed: float, prio: str):
    """Send escalation email to assigned agent and/or all admins."""
    try:
        from utils.email_service import is_email_configured, render_email_logo

        if not is_email_configured():
            return

        ticket_num = ticket.get("ticket_number", ticket.get("submission_id", ""))
        subject_text = (ticket.get("subject") or "Support Ticket")[:60]
        agent_name = ticket.get("assigned_agent_name") or "Unassigned"

        level_labels = {1: "Warning", 2: "Urgent", 3: "Critical SLA Breach"}
        level_colors = {1: "#F59E0B", 2: "#F97316", 3: "#EF4444"}

        logo_html = render_email_logo(variant="security")
        f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;padding:24px;">
          <div style="background:#0F172A;border-radius:16px;padding:28px;border:2px solid {level_colors.get(level, "#EF4444")};">
            {logo_html}
            <div style="text-align:center;margin-bottom:20px;">
              <span style="display:inline-block;padding:6px 16px;background:{level_colors.get(level, "#EF4444")};color:#fff;font-size:11px;font-weight:800;letter-spacing:1px;border-radius:20px;text-transform:uppercase;">
                Level {level} Escalation — {level_labels.get(level, "Alert")}
              </span>
            </div>
            <h2 style="color:#F9FAFB;font-size:16px;text-align:center;margin:0 0 16px;">Ticket {ticket_num} Requires Attention</h2>
            <div style="background:#1E293B;border-radius:12px;padding:18px;margin-bottom:16px;">
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="color:#9CA3AF;font-size:12px;padding:4px 0;">Subject</td><td style="color:#F9FAFB;font-size:12px;font-weight:600;text-align:right;">{subject_text}</td></tr>
                <tr><td style="color:#9CA3AF;font-size:12px;padding:4px 0;">Priority</td><td style="color:{level_colors.get(level, "#EF4444")};font-size:12px;font-weight:700;text-align:right;text-transform:uppercase;">{prio}</td></tr>
                <tr><td style="color:#9CA3AF;font-size:12px;padding:4px 0;">Assigned To</td><td style="color:#F9FAFB;font-size:12px;font-weight:600;text-align:right;">{agent_name}</td></tr>
                <tr><td style="color:#9CA3AF;font-size:12px;padding:4px 0;">Time Without Response</td><td style="color:{level_colors.get(level, "#EF4444")};font-size:12px;font-weight:700;text-align:right;">{round(elapsed)} minutes</td></tr>
              </table>
            </div>
            <p style="color:#94A3B8;font-size:12px;text-align:center;margin:0;">Please respond to this ticket immediately to de-escalate.</p>
          </div>
          <p style="text-align:center;color:#475569;font-size:10px;margin-top:12px;">RealAICoach Escalation Engine</p>
        </div>"""

        recipients = []

        # Assigned agent email
        agent_email = ticket.get("assigned_to")
        if agent_email and "@" in str(agent_email):
            recipients.append(agent_email)

        # On L3, email all admins
        if level >= 3:
            admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).to_list(20)
            for a in admins:
                if a.get("email") and a["email"] not in recipients:
                    recipients.append(a["email"])

        f"[L{level} Escalation] Ticket {ticket_num} — {prio.upper()} priority ({round(elapsed)}min)"
        for r in recipients:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=r,
                template_key="ticket_escalated",
                ticket_id=ticket_num,
                subject_line=ticket.get("subject", "Support Ticket"),
                escalated_to=f"L{level} Support",
                reason=f"{prio.upper()} priority, {round(elapsed)}min elapsed",
            )

    except Exception as e:
        logger.error(f"Email escalation alert failed: {e}")


async def _attempt_reassign(ticket: dict):
    """On L3, try to find another available agent and reassign."""
    try:
        ticket_id = ticket.get("submission_id")
        current_agent = ticket.get("assigned_to", "")
        topic = ticket.get("ai_classification", {}).get("topic") or ticket.get("category", "general")

        agents = await db.support_agents.find(
            {"is_available": True, "email": {"$ne": current_agent}},
            {"_id": 0},
        ).to_list(50)

        if not agents:
            return

        from routes.admin_management import _find_best_agent

        best = await _find_best_agent(agents, topic, "least_loaded")
        if not best:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.support_submissions.update_one(
            {"submission_id": ticket_id},
            {
                "$set": {
                    "assigned_to": best["email"],
                    "assigned_agent_name": best.get("name", ""),
                    "assignment_type": "escalation_reassign",
                    "assigned_at": now_iso,
                    "updated_at": now_iso,
                },
                "$push": {
                    "history": {
                        "action": "escalation_reassign",
                        "note": f"L3 auto-reassigned from {current_agent or 'unassigned'} to {best.get('name', best['email'])}",
                        "by": "system",
                        "by_name": "Escalation Engine",
                        "at": now_iso,
                    }
                },
            },
        )
        logger.info(f"L3 auto-reassign: {ticket_id} → {best['email']}")
    except Exception as e:
        logger.error(f"L3 auto-reassign failed: {e}")
