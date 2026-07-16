#!/usr/bin/env python3
"""Archive + tag historical fake-recipient email records.

Default mode matches requested policy:
- archive copy into `email_fake_recipient_archive`
- keep source docs and tag them as fake-recipient artifacts
- scope: email_sends + email_logs + email_events
- range: last 30 days
"""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient


BLOCKED_DOMAINS_DEFAULT = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "invalid.com",
    "fake.com",
    "mailinator.com",
    "tempmail.com",
}


def _load_env(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        row = line.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        k, v = row.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _extract_emails(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [x.strip().lower() for x in value.replace(";", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip().lower())
        return out
    return []


def _is_fake_recipient(email: str, blocked_domains: set[str]) -> bool:
    email = (email or "").strip().lower()
    if "@" not in email:
        return True
    domain = email.rsplit("@", 1)[-1]
    if domain in blocked_domains:
        return True
    return False


def _to_jsonable_doc(doc: dict[str, Any]) -> dict[str, Any]:
    clone = dict(doc)
    if "_id" in clone:
        clone["_id"] = str(clone["_id"])
    return clone


async def run(days: int, apply: bool) -> dict[str, Any]:
    env = _load_env("/app/backend/.env")
    mongo_url = env.get("MONGO_URL")
    db_name = env.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("Missing MONGO_URL/DB_NAME")

    blocked_domains = set(BLOCKED_DOMAINS_DEFAULT)
    extra = env.get("EMAIL_BLOCKED_RECIPIENT_DOMAINS", "")
    for token in extra.split(","):
        t = token.strip().lower()
        if t:
            blocked_domains.add(t)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=days)).isoformat()
    run_id = f"fake_email_cleanup_{uuid.uuid4().hex[:12]}"

    targets = [
        ("email_sends", "recipient", "sent_at"),
        ("email_logs", "email", "created_at"),
        ("email_events", "to", "received_at"),
    ]

    archive_collection = db.email_fake_recipient_archive
    run_collection = db.email_fake_recipient_cleanup_runs

    totals = {
        "scanned": 0,
        "matched": 0,
        "archived": 0,
        "tagged": 0,
    }
    per_collection: list[dict[str, Any]] = []

    for coll_name, email_field, time_field in targets:
        coll = db[coll_name]
        q = {time_field: {"$gte": cutoff_iso}}
        scanned = matched = archived = tagged = 0

        cursor = coll.find(q)
        async for doc in cursor:
            scanned += 1
            totals["scanned"] += 1
            emails = _extract_emails(doc.get(email_field))
            fake_hits = [e for e in emails if _is_fake_recipient(e, blocked_domains)]
            if not fake_hits:
                continue

            matched += 1
            totals["matched"] += 1

            if apply:
                archived_doc = {
                    "archive_id": f"fake_arc_{uuid.uuid4().hex[:12]}",
                    "run_id": run_id,
                    "source_collection": coll_name,
                    "source_id": str(doc.get("_id", "")),
                    "recipient_field": email_field,
                    "fake_recipients": fake_hits,
                    "reason": "blocked_fake_recipient_domain",
                    "archived_at": now.isoformat(),
                    "original_doc": _to_jsonable_doc(doc),
                }
                await archive_collection.insert_one(archived_doc)
                archived += 1
                totals["archived"] += 1

                await coll.update_one(
                    {"_id": doc.get("_id")},
                    {
                        "$set": {
                            "is_fake_recipient": True,
                            "fake_recipient_cleanup_run_id": run_id,
                            "fake_recipient_cleanup_at": now.isoformat(),
                            "fake_recipient_cleanup_reason": "blocked_fake_recipient_domain",
                            "fake_recipient_archived": True,
                            "fake_recipient_hits": fake_hits,
                        }
                    },
                )
                tagged += 1
                totals["tagged"] += 1

        per_collection.append(
            {
                "collection": coll_name,
                "email_field": email_field,
                "time_field": time_field,
                "scanned": scanned,
                "matched": matched,
                "archived": archived,
                "tagged": tagged,
            }
        )

    summary = {
        "run_id": run_id,
        "mode": "apply" if apply else "dry_run",
        "days": days,
        "cutoff_iso": cutoff_iso,
        "blocked_domains": sorted(blocked_domains),
        "totals": totals,
        "collections": per_collection,
        "created_at": now.isoformat(),
    }
    if apply:
        await run_collection.insert_one(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    import asyncio

    summary = asyncio.run(run(days=args.days, apply=args.apply))
    print(summary)


if __name__ == "__main__":
    main()
