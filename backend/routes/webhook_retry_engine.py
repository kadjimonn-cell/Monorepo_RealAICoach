"""Webhook Auto-Retry Engine – Fully automated retry with configurable rules.

Runs every 30 seconds via APScheduler. Picks up failed events, applies
per-integration retry rules (exponential/linear/fixed backoff), and
re-processes them automatically.

Collections:
  webhook_retry_rules  – per-integration retry configuration
  webhook_retry_queue  – events queued for automatic retry
"""

import logging
from datetime import datetime, timezone, timedelta
from routes.db import db

logger = logging.getLogger(__name__)

RULES_COL = "webhook_retry_rules"
QUEUE_COL = "webhook_retry_queue"
EVENTS_COL = "webhook_events"

# Default rules applied when no per-integration rule exists
DEFAULT_RULE = {
    "enabled": True,
    "max_retries": 3,
    "backoff_strategy": "exponential",
    "initial_delay_seconds": 60,
    "max_delay_seconds": 3600,
    "backoff_multiplier": 2.0,
    "retry_on_statuses": ["failed", "error"],
}


async def get_rule_for_integration(integration_id: str) -> dict:
    """Fetch the retry rule for a specific integration, falling back to defaults."""
    rule = await db[RULES_COL].find_one({"integration_id": integration_id}, {"_id": 0})
    if rule and rule.get("enabled"):
        return rule
    # Check for a wildcard/global rule
    global_rule = await db[RULES_COL].find_one({"integration_id": "*"}, {"_id": 0})
    if global_rule and global_rule.get("enabled"):
        return global_rule
    return DEFAULT_RULE


def calculate_next_retry(attempt: int, rule: dict) -> datetime:
    """Calculate the next retry time based on the backoff strategy."""
    strategy = rule.get("backoff_strategy", "exponential")
    initial = rule.get("initial_delay_seconds", 60)
    multiplier = rule.get("backoff_multiplier", 2.0)
    max_delay = rule.get("max_delay_seconds", 3600)

    if strategy == "fixed":
        delay = initial
    elif strategy == "linear":
        delay = initial * attempt
    else:  # exponential
        delay = initial * (multiplier ** (attempt - 1))

    delay = min(delay, max_delay)
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


async def enqueue_failed_event(event_id: str, integration_id: str):
    """Add a failed event to the retry queue if not already queued."""
    existing = await db[QUEUE_COL].find_one({"event_id": event_id, "status": {"$in": ["pending", "processing"]}})
    if existing:
        return  # Already in queue

    rule = await get_rule_for_integration(integration_id)
    if not rule.get("enabled"):
        return

    retry_statuses = rule.get("retry_on_statuses", ["failed", "error"])
    event = await db[EVENTS_COL].find_one({"event_id": event_id}, {"_id": 0})
    if not event or event.get("status") not in retry_statuses:
        return
    if event.get("resolution_status") == "resolved":
        return

    now = datetime.now(timezone.utc)
    next_retry = calculate_next_retry(1, rule)

    await db[QUEUE_COL].insert_one(
        {
            "event_id": event_id,
            "integration_id": integration_id,
            "attempt": 0,
            "max_retries": rule.get("max_retries", 3),
            "next_retry_at": next_retry.isoformat(),
            "status": "pending",
            "rule_snapshot": {
                "backoff_strategy": rule.get("backoff_strategy"),
                "initial_delay_seconds": rule.get("initial_delay_seconds"),
                "backoff_multiplier": rule.get("backoff_multiplier"),
                "max_delay_seconds": rule.get("max_delay_seconds"),
            },
            "created_at": now.isoformat(),
            "last_attempt_at": None,
            "error": None,
        }
    )
    logger.info(f"Retry queued: {event_id} (integration={integration_id}, next_retry={next_retry.isoformat()})")


async def scan_and_enqueue_failed_events():
    """Scan webhook_events for newly failed events and enqueue them for retry."""
    # Find failed events that are NOT already in the retry queue and NOT resolved
    pipeline = [
        {
            "$match": {
                "status": {"$in": ["failed", "error"]},
                "resolution_status": {"$ne": "resolved"},
            }
        },
        {
            "$lookup": {
                "from": QUEUE_COL,
                "localField": "event_id",
                "foreignField": "event_id",
                "as": "queue_entries",
            }
        },
        {
            "$match": {
                "$or": [
                    {"queue_entries": {"$size": 0}},
                    {"queue_entries": {"$not": {"$elemMatch": {"status": {"$in": ["pending", "processing"]}}}}},
                ]
            }
        },
        {"$limit": 50},
    ]
    candidates = await db[EVENTS_COL].aggregate(pipeline).to_list(50)
    enqueued = 0
    for event in candidates:
        # Check if exhausted already
        exhausted = await db[QUEUE_COL].find_one({"event_id": event["event_id"], "status": "exhausted"})
        if exhausted:
            continue
        await enqueue_failed_event(event["event_id"], event.get("integration_id", "unknown"))
        enqueued += 1
    if enqueued > 0:
        logger.info(f"Auto-enqueued {enqueued} failed events for retry")


async def process_retry_queue():
    """Process the retry queue – called by APScheduler every 30 seconds."""
    now = datetime.now(timezone.utc).isoformat()

    # Find pending items whose next_retry_at has passed
    pending = (
        await db[QUEUE_COL]
        .find(
            {
                "status": "pending",
                "next_retry_at": {"$lte": now},
            }
        )
        .sort("next_retry_at", 1)
        .limit(10)
        .to_list(10)
    )

    if not pending:
        return

    from routes.webhook_replay import _process_webhook_event

    processed = 0
    succeeded = 0
    failed = 0
    exhausted_count = 0

    for item in pending:
        event_id = item["event_id"]
        attempt = item.get("attempt", 0) + 1
        max_retries = item.get("max_retries", 3)

        # Mark as processing
        await db[QUEUE_COL].update_one(
            {"event_id": event_id, "status": "pending"},
            {"$set": {"status": "processing"}},
        )

        event = await db[EVENTS_COL].find_one({"event_id": event_id}, {"_id": 0})
        if not event:
            await db[QUEUE_COL].update_one({"event_id": event_id}, {"$set": {"status": "not_found"}})
            continue

        # Skip resolved events
        if event.get("resolution_status") == "resolved":
            await db[QUEUE_COL].update_one({"event_id": event_id}, {"$set": {"status": "resolved_skip"}})
            continue

        retry_now = datetime.now(timezone.utc).isoformat()
        replay_entry = {
            "replayed_at": retry_now,
            "replayed_by": "auto-retry-engine",
            "previous_status": event.get("status", "unknown"),
            "attempt": attempt,
        }

        try:
            await _process_webhook_event(event)
            replay_entry["result"] = "success"
            new_status = "replayed"
            succeeded += 1

            # Update event
            await db[EVENTS_COL].update_one(
                {"event_id": event_id},
                {
                    "$set": {"status": new_status, "last_replayed_at": retry_now},
                    "$inc": {"replay_count": 1},
                    "$push": {"replay_history": replay_entry},
                },
            )
            # Mark queue item as success
            await db[QUEUE_COL].update_one(
                {"event_id": event_id, "status": "processing"},
                {"$set": {"status": "success", "last_attempt_at": retry_now, "attempt": attempt}},
            )
            logger.info(f"Auto-retry SUCCESS: {event_id} (attempt {attempt})")

        except Exception as e:
            replay_entry["result"] = "failed"
            replay_entry["error"] = str(e)
            failed += 1

            await db[EVENTS_COL].update_one(
                {"event_id": event_id},
                {
                    "$set": {"status": "retry_failed", "last_replayed_at": retry_now},
                    "$inc": {"replay_count": 1},
                    "$push": {"replay_history": replay_entry},
                },
            )

            if attempt >= max_retries:
                # Exhausted all retries
                await db[QUEUE_COL].update_one(
                    {"event_id": event_id, "status": "processing"},
                    {
                        "$set": {
                            "status": "exhausted",
                            "last_attempt_at": retry_now,
                            "attempt": attempt,
                            "error": str(e),
                        }
                    },
                )
                await db[EVENTS_COL].update_one(
                    {"event_id": event_id},
                    {"$set": {"status": "exhausted"}},
                )
                exhausted_count += 1
                logger.warning(f"Auto-retry EXHAUSTED: {event_id} after {attempt} attempts")

                # Send admin notification
                try:
                    from utils.ws_manager import push_admin_alert

                    await push_admin_alert(
                        "webhook_retry_exhausted",
                        f"Retry Exhausted: {event_id}",
                        f"{event.get('event_type')} from {event.get('integration_id')} failed after {attempt} attempts. Manual intervention required.",
                        "error",
                        {"event_id": event_id},
                    )
                except Exception:
                    pass
            else:
                # Schedule next retry with backoff
                rule_snapshot = item.get("rule_snapshot", DEFAULT_RULE)
                next_retry = calculate_next_retry(attempt + 1, rule_snapshot)
                await db[QUEUE_COL].update_one(
                    {"event_id": event_id, "status": "processing"},
                    {
                        "$set": {
                            "status": "pending",
                            "next_retry_at": next_retry.isoformat(),
                            "last_attempt_at": retry_now,
                            "attempt": attempt,
                            "error": str(e),
                        }
                    },
                )
                logger.info(
                    f"Auto-retry FAILED: {event_id} (attempt {attempt}/{max_retries}, next at {next_retry.isoformat()})"
                )

        processed += 1

    if processed > 0:
        logger.info(
            f"Retry engine: processed={processed}, succeeded={succeeded}, failed={failed}, exhausted={exhausted_count}"
        )


async def run_retry_cycle():
    """Full retry cycle: scan for new failures + process queue. Called by scheduler."""
    try:
        await scan_and_enqueue_failed_events()
        await process_retry_queue()
    except Exception as e:
        logger.error(f"Retry engine error: {e}", exc_info=True)


async def get_retry_queue_stats() -> dict:
    """Get retry queue statistics for the dashboard."""
    col = db[QUEUE_COL]
    total = await col.count_documents({})
    pending = await col.count_documents({"status": "pending"})
    processing = await col.count_documents({"status": "processing"})
    succeeded = await col.count_documents({"status": "success"})
    exhausted = await col.count_documents({"status": "exhausted"})

    # Next retry time
    next_item = await col.find_one({"status": "pending"}, {"_id": 0, "next_retry_at": 1}, sort=[("next_retry_at", 1)])
    next_retry = next_item.get("next_retry_at") if next_item else None

    # Recent activity (last 24h)
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_success = await col.count_documents({"status": "success", "last_attempt_at": {"$gte": day_ago}})
    recent_exhausted = await col.count_documents({"status": "exhausted", "last_attempt_at": {"$gte": day_ago}})

    return {
        "total": total,
        "pending": pending,
        "processing": processing,
        "succeeded": succeeded,
        "exhausted": exhausted,
        "next_retry_at": next_retry,
        "recent_24h": {"succeeded": recent_success, "exhausted": recent_exhausted},
    }
