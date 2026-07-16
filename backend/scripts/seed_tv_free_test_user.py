"""Idempotently (re)create the tv.free.test free-tier E2E account.

Safe to run repeatedly: never overwrites an existing password hash.
Usage: cd /app/backend && python3 scripts/seed_tv_free_test_user.py
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_EMAIL = "tv.free.test@realaicoach.app"
TEST_PASSWORD = "TvFree#2026!Aa"
TEST_NAME = "TV Free Test"


async def seed() -> None:
    from routes.db import db, hash_password

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"email": TEST_EMAIL})

    if existing:
        update = {"updated_at": now, "is_admin": False, "subscription_plan": "free", "subscription_status": "active"}
        if not existing.get("password_hash"):
            update["password_hash"] = hash_password(TEST_PASSWORD)
        await db.users.update_one({"_id": existing["_id"]}, {"$set": update})
        print(f"updated existing user {existing.get('user_id')} (password preserved: {bool(existing.get('password_hash'))})")
        return

    doc = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": TEST_EMAIL,
        "password_hash": hash_password(TEST_PASSWORD),
        "name": TEST_NAME,
        "auth_provider": "email",
        "email_verified": True,
        "is_admin": False,
        "role": "user",
        "roles": ["user"],
        "platform_role": "user",
        "subscription_plan": "free",
        "subscription_status": "active",
        "full_access": False,
        "premium_access": False,
        "subscription_permanent": False,
        "token_version": 0,
        "language_preference": "en",
        "theme_preference": "light",
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    print(f"created user {doc['user_id']} ({TEST_EMAIL})")


if __name__ == "__main__":
    asyncio.run(seed())
