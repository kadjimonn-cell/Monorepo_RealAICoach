from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict


def notification_title_for_event(event_type: str) -> str:
    return {
        "FeatureAdded": "New Feature Added",
        "FeatureRemoved": "Feature Removed",
        "FeatureUpdated": "Feature Updated",
        "PlanChanged": "Plan Update",
        "ContentUpdated": "Platform Content Updated",
    }.get(event_type, "Platform Update")


async def enqueue_change_notifications(db: Any, event: Dict[str, Any], now_iso, logger):
    title = notification_title_for_event(event.get("event_type", "ContentUpdated"))
    what_changed = str(event.get("what_changed") or "Platform content changed.")
    why = str(event.get("why_changed") or "Product improvement")
    impact = str(event.get("impact") or "Please review updates in dashboard/help pages.")
    message = f"{what_changed}\nWhy: {why}\nImpact: {impact}"
    stamp = now_iso()

    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(5000)
    docs = []
    for user in users:
        uid = user.get("user_id")
        if not uid:
            continue
        docs.append(
            {
                "outbox_id": f"gps_out_{uuid.uuid4().hex[:12]}",
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "user_id": uid,
                "title": title,
                "body": message,
                "metadata": {
                    "gps_event_id": event.get("event_id"),
                    "notification_entity_id": f"gps_event:{event.get('event_id')}",
                    "event_type": event.get("event_type"),
                    "what_changed": what_changed,
                    "why_changed": why,
                    "impact": impact,
                },
                "status": "queued",
                "attempts": 0,
                "next_retry_at": stamp,
                "created_at": stamp,
                "updated_at": stamp,
            }
        )
    if docs:
        try:
            await db.gps_notification_outbox.insert_many(docs, ordered=False)
        except Exception as exc:
            logger.warning("GPS outbox enqueue warning: %s", exc)


async def process_notification_outbox(
    db: Any,
    emit_notification,
    now_iso,
    *,
    max_retries: int,
    batch_size: int = 250,
    max_cycles: int = 1,
) -> Dict[str, Any]:
    limit = max(1, min(batch_size, 2000))
    cycle_cap = max(1, min(max_cycles, 5))

    sent = failed = retrying = processed = 0
    cycles = 0

    for _ in range(cycle_cap):
        stamp = datetime.now(timezone.utc).isoformat()
        docs = await db.gps_notification_outbox.find(
            {"status": {"$in": ["queued", "retrying"]}, "next_retry_at": {"$lte": stamp}},
            {"_id": 0},
        ).sort("created_at", 1).limit(limit).to_list(limit)

        if not docs:
            break

        cycles += 1
        processed += len(docs)

        concurrency = max(1, min(25, limit))
        sem = asyncio.Semaphore(concurrency)

        async def _process_doc(doc: Dict[str, Any]) -> str:
            outbox_id = doc.get("outbox_id")
            async with sem:
                try:
                    await emit_notification(
                        user_id=doc.get("user_id"),
                        notif_type=f"gps_{str(doc.get('event_type', 'content')).lower()}",
                        title=doc.get("title") or "Platform Update",
                        body=doc.get("body") or "Platform content changed",
                        action_url="/notifications",
                        metadata=doc.get("metadata") or {},
                        send_email_notification=True,
                    )
                    await db.gps_notification_outbox.update_one(
                        {"outbox_id": outbox_id},
                        {"$set": {"status": "sent", "sent_at": now_iso(), "updated_at": now_iso()}},
                    )
                    return "sent"
                except Exception as exc:
                    attempts = int(doc.get("attempts", 0)) + 1
                    if attempts >= max_retries:
                        await db.gps_notification_outbox.update_one(
                            {"outbox_id": outbox_id},
                            {"$set": {"status": "failed", "attempts": attempts, "last_error": str(exc), "updated_at": now_iso()}},
                        )
                        return "failed"
                    backoff_seconds = min(3600, 2**attempts * 15)
                    next_retry = datetime.now(timezone.utc).timestamp() + backoff_seconds
                    await db.gps_notification_outbox.update_one(
                        {"outbox_id": outbox_id},
                        {
                            "$set": {
                                "status": "retrying",
                                "attempts": attempts,
                                "next_retry_at": datetime.fromtimestamp(next_retry, tz=timezone.utc).isoformat(),
                                "last_error": str(exc),
                                "updated_at": now_iso(),
                            }
                        },
                    )
                    return "retrying"

        outcomes = await asyncio.gather(*[_process_doc(doc) for doc in docs])
        sent += sum(1 for status in outcomes if status == "sent")
        failed += sum(1 for status in outcomes if status == "failed")
        retrying += sum(1 for status in outcomes if status == "retrying")

        if len(docs) < limit:
            break

    return {
        "processed": processed,
        "sent": sent,
        "failed": failed,
        "retrying": retrying,
        "cycles": cycles,
        "batch_limit": limit,
        "checked_at": now_iso(),
    }


async def reconcile_notification_outbox(db: Any, now_iso, logger, *, limit_events: int = 25) -> Dict[str, Any]:
    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(5000)
    user_ids = [u.get("user_id") for u in users if u.get("user_id")]
    if not user_ids:
        return {"events_checked": 0, "inserted": 0}

    events = await db.global_platform_events.find({}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit_events, 100))).to_list(max(1, min(limit_events, 100)))
    inserted = 0
    stamp = now_iso()
    for event in events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        existing = await db.gps_notification_outbox.find({"event_id": event_id}, {"_id": 0, "user_id": 1}).to_list(10000)
        existing_ids = {item.get("user_id") for item in existing if item.get("user_id")}
        missing_ids = [uid for uid in user_ids if uid not in existing_ids]
        if not missing_ids:
            continue

        title = notification_title_for_event(event.get("event_type", "ContentUpdated"))
        what_changed = str(event.get("what_changed") or "Platform content changed.")
        why = str(event.get("why_changed") or "Product improvement")
        impact = str(event.get("impact") or "Please review updates in dashboard/help pages.")
        message = f"{what_changed}\nWhy: {why}\nImpact: {impact}"
        docs = [
            {
                "outbox_id": f"gps_out_{uuid.uuid4().hex[:12]}",
                "event_id": event_id,
                "event_type": event.get("event_type"),
                "user_id": uid,
                "title": title,
                "body": message,
                "metadata": {
                    "gps_event_id": event_id,
                    "notification_entity_id": f"gps_event:{event_id}",
                    "event_type": event.get("event_type"),
                    "reconciled": True,
                },
                "status": "queued",
                "attempts": 0,
                "next_retry_at": stamp,
                "created_at": stamp,
                "updated_at": stamp,
            }
            for uid in missing_ids
        ]
        if docs:
            try:
                await db.gps_notification_outbox.insert_many(docs, ordered=False)
            except Exception as exc:
                logger.warning("GPS outbox reconcile insert warning: %s", exc)
            inserted += len(docs)

    return {"events_checked": len(events), "inserted": inserted, "checked_at": now_iso()}


async def outbox_stats(db: Any, now_iso) -> Dict[str, Any]:
    queued = await db.gps_notification_outbox.count_documents({"status": "queued"})
    retrying = await db.gps_notification_outbox.count_documents({"status": "retrying"})
    failed = await db.gps_notification_outbox.count_documents({"status": "failed"})
    sent = await db.gps_notification_outbox.count_documents({"status": "sent"})
    return {"queued": queued, "retrying": retrying, "failed": failed, "sent": sent, "checked_at": now_iso()}