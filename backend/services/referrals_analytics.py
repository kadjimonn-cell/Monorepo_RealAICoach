from typing import Any

from routes.db import db


async def load_user_profiles(user_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(uid).strip() for uid in user_ids if str(uid or "").strip()]
    if not ids:
        return {}

    users = await db.users.find(
        {"user_id": {"$in": ids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "subscription_plan": 1},
    ).to_list(len(ids) + 8)

    return {
        str(user.get("user_id") or ""): user
        for user in users
        if str(user.get("user_id") or "").strip()
    }


def group_rows_by(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field) or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    return grouped
