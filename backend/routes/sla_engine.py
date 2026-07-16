"""SLA Ticket Auto-Escalation Engine — 100% automated.

- Tickets unanswered for 48h auto-escalate to 'escalated' priority
- Senior admins notified via email
- Runs on APScheduler every 6 hours
- Full audit trail with SLA metrics

API:
- GET /api/admin/sla/dashboard — SLA metrics for executive dashboard
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging
import os

from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

SLA_ESCALATION_HOURS = 48
SLA_WARNING_HOURS = 36
SENIOR_ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]


async def run_sla_escalation():
    """Background job: auto-escalate tickets unanswered for >48h. Called by APScheduler."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=SLA_ESCALATION_HOURS)
    cutoff.isoformat()

    # Find open/pending tickets with no admin reply past SLA
    query = {
        "status": {"$in": ["open", "pending", "in_progress", "reopened"]},
        "priority": {"$ne": "escalated"},
        "sla_escalated": {"$ne": True},
    }

    escalated_count = 0
    warned_count = 0
    tickets_cursor = db.support_tickets.find(query, {"_id": 0})
    async for ticket in tickets_cursor:
        created = ticket.get("created_at", "")
        last_admin_reply = ticket.get("last_admin_reply_at")

        # Determine the reference time (last admin reply or ticket creation)
        ref_time_str = last_admin_reply or created
        if not ref_time_str:
            continue

        try:
            if isinstance(ref_time_str, datetime):
                ref_time = ref_time_str if ref_time_str.tzinfo else ref_time_str.replace(tzinfo=timezone.utc)
            else:
                ref_time = datetime.fromisoformat(ref_time_str.replace("Z", "+00:00"))
                if ref_time.tzinfo is None:
                    ref_time = ref_time.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        hours_waiting = (now - ref_time).total_seconds() / 3600

        if hours_waiting >= SLA_ESCALATION_HOURS:
            # Auto-escalate
            await db.support_tickets.update_one(
                {"ticket_id": ticket["ticket_id"]},
                {
                    "$set": {
                        "priority": "escalated",
                        "sla_escalated": True,
                        "sla_escalated_at": now.isoformat(),
                        "sla_hours_waited": round(hours_waiting, 1),
                        "status": "escalated",
                    },
                    "$push": {
                        "audit_log": {
                            "action": "sla_auto_escalate",
                            "timestamp": now.isoformat(),
                            "actor": "system",
                            "details": f"Auto-escalated after {round(hours_waiting, 1)}h without admin response (SLA: {SLA_ESCALATION_HOURS}h)",
                        }
                    },
                },
            )
            escalated_count += 1

            # Notify senior admins
            try:
                from utils.email_notifications import notify

                for admin_email in SENIOR_ADMIN_EMAILS:
                    admin_user = await db.users.find_one({"email": admin_email})
                    if admin_user:
                        await notify.generic(
                            admin_user["user_id"],
                            admin_email,
                            admin_user.get("name", "Admin"),
                            subject=f"SLA Breach: Ticket {ticket.get('ticket_number', ticket['ticket_id'])} Auto-Escalated",
                            body=f"Ticket '{ticket.get('subject', 'N/A')}' has been waiting {round(hours_waiting, 1)} hours without an admin response and was auto-escalated.\n\nPlease review and respond immediately.",
                            template_key="sla_escalation",
                        )
            except Exception as e:
                logger.warning(f"SLA notification failed: {e}")

        elif hours_waiting >= SLA_WARNING_HOURS:
            # SLA warning — mark as at-risk
            if not ticket.get("sla_warning_sent"):
                await db.support_tickets.update_one(
                    {"ticket_id": ticket["ticket_id"]},
                    {"$set": {"sla_warning_sent": True, "sla_warning_at": now.isoformat()}},
                )
                warned_count += 1

    logger.info(f"SLA engine: {escalated_count} escalated, {warned_count} warned")
    return {"escalated": escalated_count, "warned": warned_count}


@router.get("/admin/sla/dashboard")
async def sla_dashboard(request: Request):
    """Executive SLA dashboard — metrics, at-risk tickets, escalation history."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    (now - timedelta(days=30)).isoformat()

    # Overall SLA metrics
    total_open = await db.support_tickets.count_documents(
        {"status": {"$in": ["open", "pending", "in_progress", "reopened"]}}
    )
    total_escalated = await db.support_tickets.count_documents({"sla_escalated": True})
    escalated_7d = await db.support_tickets.count_documents(
        {"sla_escalated": True, "sla_escalated_at": {"$gte": seven_days_ago}}
    )
    at_risk = await db.support_tickets.count_documents(
        {
            "sla_warning_sent": True,
            "sla_escalated": {"$ne": True},
            "status": {"$in": ["open", "pending", "in_progress"]},
        }
    )
    total_resolved = await db.support_tickets.count_documents({"status": {"$in": ["resolved", "closed"]}})

    # Average response time (tickets with admin replies)
    pipeline_resp = [
        {"$match": {"last_admin_reply_at": {"$exists": True}, "created_at": {"$exists": True}}},
        {"$limit": 200},
    ]
    response_times = []
    async for t in db.support_tickets.aggregate(pipeline_resp):
        try:
            created = t["created_at"]
            replied = t["last_admin_reply_at"]
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(replied, str):
                replied = datetime.fromisoformat(replied.replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if replied.tzinfo is None:
                replied = replied.replace(tzinfo=timezone.utc)
            diff_h = (replied - created).total_seconds() / 3600
            if diff_h > 0:
                response_times.append(diff_h)
        except Exception:
            pass

    avg_response_h = round(sum(response_times) / max(len(response_times), 1), 1) if response_times else 0
    sla_compliance = (
        round(((len([r for r in response_times if r <= SLA_ESCALATION_HOURS]) / max(len(response_times), 1)) * 100), 1)
        if response_times
        else 100.0
    )

    # At-risk tickets list
    at_risk_tickets = []
    cursor = (
        db.support_tickets.find(
            {"status": {"$in": ["open", "pending", "in_progress", "reopened"]}, "sla_escalated": {"$ne": True}},
            {
                "_id": 0,
                "ticket_id": 1,
                "ticket_number": 1,
                "subject": 1,
                "status": 1,
                "priority": 1,
                "created_at": 1,
                "last_admin_reply_at": 1,
                "user_id": 1,
                "sla_warning_sent": 1,
            },
        )
        .sort("created_at", 1)
        .limit(20)
    )
    async for t in cursor:
        ref = t.get("last_admin_reply_at") or t.get("created_at", "")
        try:
            if isinstance(ref, str):
                ref_dt = datetime.fromisoformat(ref.replace("Z", "+00:00"))
            else:
                ref_dt = ref
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
            hours_waiting = round((now - ref_dt).total_seconds() / 3600, 1)
        except Exception:
            hours_waiting = 0
        t["hours_waiting"] = hours_waiting
        t["sla_pct"] = min(100, round((hours_waiting / SLA_ESCALATION_HOURS) * 100, 1))
        at_risk_tickets.append(t)

    at_risk_tickets.sort(key=lambda x: x.get("hours_waiting", 0), reverse=True)

    # Escalated tickets
    escalated_tickets = []
    esc_cursor = (
        db.support_tickets.find(
            {"sla_escalated": True},
            {
                "_id": 0,
                "ticket_id": 1,
                "ticket_number": 1,
                "subject": 1,
                "status": 1,
                "sla_escalated_at": 1,
                "sla_hours_waited": 1,
                "user_id": 1,
            },
        )
        .sort("sla_escalated_at", -1)
        .limit(15)
    )
    async for t in esc_cursor:
        escalated_tickets.append(t)

    return {
        "sla_config": {"escalation_hours": SLA_ESCALATION_HOURS, "warning_hours": SLA_WARNING_HOURS},
        "overview": {
            "total_open": total_open,
            "total_escalated": total_escalated,
            "escalated_7d": escalated_7d,
            "at_risk": at_risk,
            "total_resolved": total_resolved,
            "avg_response_hours": avg_response_h,
            "sla_compliance_pct": sla_compliance,
        },
        "at_risk_tickets": at_risk_tickets,
        "escalated_tickets": escalated_tickets,
    }
