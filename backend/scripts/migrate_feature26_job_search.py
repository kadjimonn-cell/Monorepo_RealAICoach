#!/usr/bin/env python3
"""One-time migration: Feature 26 Jobs Portal -> Job Search.

Updates feature_registry and global_platform_state entries in-place
(feature_id 'jobs-portal' stays canonical; user-facing surface becomes Job Search).
Idempotent — safe to re-run.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

NEW_FIELDS = {
    "title": "Job Search",
    "description": "AI-powered job search: profile evaluation, fit scoring, tailored CV and cover letters, ATS validation.",
    "icon": "search",
    "route": "/job-search",
}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    res1 = await db.feature_registry.update_one(
        {"feature_id": "jobs-portal"}, {"$set": {**NEW_FIELDS, "updated_at": now}}
    )
    print(f"feature_registry updated: matched={res1.matched_count} modified={res1.modified_count}")

    gps = await db.global_platform_state.find_one({}, {"_id": 1, "features": 1})
    if gps and gps.get("features"):
        features = gps["features"]
        changed = False
        for f in features:
            if f.get("feature_id") == "jobs-portal":
                f.update(NEW_FIELDS)
                f["updated_at"] = now
                changed = True
        if changed:
            await db.global_platform_state.update_one({"_id": gps["_id"]}, {"$set": {"features": features}})
            print("global_platform_state features updated")
        else:
            print("global_platform_state: jobs-portal feature not found")
    else:
        print("global_platform_state: no features array")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
