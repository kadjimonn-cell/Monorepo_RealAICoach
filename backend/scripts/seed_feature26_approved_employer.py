"""Seed approved employer fixture for Feature 26 E2E testing.

Usage:
    python /app/backend/scripts/seed_feature26_approved_employer.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


EMAIL = "feature26.approved.employer.e2e@realaicoach.app"
PASSWORD = "Feature26Approved#2026!"
USER_ID = "user_feature26_employer_fixture"


async def main() -> None:
    load_dotenv('/app/backend/.env')
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL or DB_NAME missing")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    now = datetime.now(timezone.utc).isoformat()
    hashed = bcrypt.hashpw(PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    await db.users.update_one(
        {"email": EMAIL},
        {
            "$set": {
                "user_id": USER_ID,
                "email": EMAIL,
                "password_hash": hashed,
                "name": "Feature 26 Approved Employer E2E",
                "is_employer": True,
                "roles": ["employer"],
                "is_admin": False,
                "subscription_plan": "premium",
                "subscription_status": "active",
                "payment_verified": True,
                "country": "Singapore",
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
                "registration_method": "email",
            },
        },
        upsert=True,
    )

    await db.employer_profiles.update_one(
        {"user_id": USER_ID},
        {
            "$set": {
                "user_id": USER_ID,
                "employer_id": "emp_feature26_fixture",
                "company_name": "Feature 26 Approved E2E Labs",
                "company_email": EMAIL,
                "verification_status": "approved",
                "approval_status": "approved",
                "onboarding_completed": True,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    # Create employer_applications record (required by require_employer check)
    await db.employer_applications.update_one(
        {"user_id": USER_ID},
        {
            "$set": {
                "user_id": USER_ID,
                "employer_id": "emp_feature26_fixture",
                "business_name": "Feature 26 Approved E2E Labs",
                "status": "approved",
                "permissions": ["post_job", "view_applicants", "manage_offers"],
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    print("OK: Feature 26 approved employer fixture seeded")
    print(f"EMAIL={EMAIL}")
    print(f"PASSWORD={PASSWORD}")
    print(f"USER_ID={USER_ID}")


if __name__ == "__main__":
    asyncio.run(main())
