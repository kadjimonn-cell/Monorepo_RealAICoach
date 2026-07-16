"""One-time remediation: downgrade all non-admin users holding paid plans/roles/flags to free."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")


def main() -> None:
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now_iso = datetime.now(timezone.utc).isoformat()

    query = {
        "is_admin": {"$ne": True},
        "$or": [
            {"subscription_plan": {"$in": ["basic", "premium"]}},
            {"role": {"$in": ["basic", "premium", "full_users"]}},
            {"roles": {"$in": ["basic", "premium", "full_users"]}},
            {"full_access": True},
            {"premium_access": True},
            {"subscription_permanent": True},
        ],
    }

    targets = list(
        db.users.find(query, {"_id": 0, "user_id": 1, "email": 1, "subscription_plan": 1, "role": 1})
    )
    print(f"Found {len(targets)} non-admin users with paid entitlements")

    audit_entries = []
    for u in targets:
        audit_entries.append(
            {
                "event_type": "preprod_entitlement_remediation",
                "user_id": u.get("user_id"),
                "email": u.get("email"),
                "previous_plan": u.get("subscription_plan"),
                "previous_role": u.get("role"),
                "new_plan": "free",
                "reason": "Pre-production entitlement lock: only admins retain premium until launch",
                "created_at": now_iso,
            }
        )

    result = db.users.update_many(
        query,
        {
            "$set": {
                "subscription_plan": "free",
                "subscription_status": "active",
                "role": "user",
                "roles": ["user"],
                "full_access": False,
                "premium_access": False,
                "subscription_permanent": False,
                "payment_verified": False,
                "subscription_end_date": None,
                "pending_subscription_transition": None,
                "updated_at": now_iso,
            }
        },
    )
    if audit_entries:
        db.subscription_audit_log.insert_many(audit_entries)

    print(f"Downgraded {result.modified_count} users to free; {len(audit_entries)} audit entries written")

    remaining = db.users.count_documents(
        {"is_admin": {"$ne": True}, "subscription_plan": {"$in": ["basic", "premium"]}}
    )
    print(f"Remaining non-admin paid users: {remaining}")


if __name__ == "__main__":
    main()
