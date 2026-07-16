from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def _safe_iso_to_datetime(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


async def build_library_affinity_profile(db: Any, user_id: str, window_days: int = 30) -> dict[str, Any]:
    if not user_id:
        return {"category": {}, "type": {}}

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(1, min(window_days, 90)))
    rows = await db.action_history.find(
        {
            "user_id": user_id,
            "feature_key": "content-library",
            "action": {"$in": ["open", "bookmark_toggle", "search"]},
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "action": 1, "details": 1},
    ).to_list(1200)

    category_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()

    for row in rows:
        action = str(row.get("action") or "").lower()
        weight = 3 if action == "bookmark_toggle" else 2 if action == "open" else 1
        details = row.get("details") or {}

        category = str(details.get("category") or "").strip().lower()
        if category:
            category_counter[category] += weight

        content_type = str(details.get("type") or "").strip().lower()
        if content_type:
            type_counter[content_type] += weight

    return {
        "category": dict(category_counter),
        "type": dict(type_counter),
    }


def _score_breakdown(item: dict[str, Any], bookmarked_ids: set[str], affinity_profile: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    added_at = _safe_iso_to_datetime(item.get("added_date"))
    age_days = max((now - added_at).total_seconds() / 86400.0, 0)
    recency_score = max(0.0, 30.0 - age_days) * 1.2

    category = str(item.get("category") or "").strip().lower()
    content_type = str(item.get("type") or "").strip().lower()

    category_affinity = float((affinity_profile.get("category") or {}).get(category, 0))
    type_affinity = float((affinity_profile.get("type") or {}).get(content_type, 0))
    affinity_score = (category_affinity * 3.0) + (type_affinity * 2.2)

    bookmark_boost = 35.0 if str(item.get("url") or "") in bookmarked_ids else 0.0
    generated_boost = 4.0 if str(item.get("source") or "").strip().lower() == "generated" else 0.0
    total_score = recency_score + affinity_score + bookmark_boost + generated_boost

    reasons: list[str] = []
    if recency_score >= 8:
        reasons.append("fresh")
    if affinity_score >= 3:
        reasons.append("matches_activity")
    if bookmark_boost > 0:
        reasons.append("bookmarked")
    if generated_boost > 0:
        reasons.append("saved_generated")

    return {
        "total": total_score,
        "recency": recency_score,
        "affinity": affinity_score,
        "bookmark": bookmark_boost,
        "reasons": reasons,
    }


def merge_library_items_for_page(
    *,
    curated_items: list[dict[str, Any]],
    generated_items: list[dict[str, Any]],
    sort: str,
    skip: int,
    per_page: int,
    bookmarked_ids: set[str],
    affinity_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    all_items = [*generated_items, *curated_items]

    for item in all_items:
        item["bookmarked"] = str(item.get("url", "")) in bookmarked_ids

    if sort == "recommended":
        profile = affinity_profile or {"category": {}, "type": {}}
        for item in all_items:
            breakdown = _score_breakdown(item, bookmarked_ids, profile)
            item["score"] = round(float(breakdown["total"]), 2)
            item["recency_rank"] = round(float(breakdown["recency"]), 2)
            item["affinity_rank"] = round(float(breakdown["affinity"]), 2)
            item["bookmark_rank"] = round(float(breakdown["bookmark"]), 2)
            item["recommendation_reasons"] = list(breakdown.get("reasons") or [])[:3]

        all_items.sort(
            key=lambda item: (
                float(item.get("score") or 0.0),
                _safe_iso_to_datetime(item.get("added_date")),
            ),
            reverse=True,
        )
    else:
        reverse = sort != "oldest"
        all_items.sort(key=lambda item: _safe_iso_to_datetime(item.get("added_date")), reverse=reverse)

    return all_items[skip : skip + per_page]
