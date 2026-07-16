from __future__ import annotations

from typing import Any, Callable, Awaitable


class WatchVideosRecommendationService:
    """Phase-1 modular recommendation/reasons service."""

    def __init__(
        self,
        *,
        build_recommendations: Callable[..., Awaitable[list[dict[str, Any]]]],
        feedback_map_for_user: Callable[[str], Awaitable[dict[str, str]]],
    ) -> None:
        self._build_recommendations = build_recommendations
        self._feedback_map_for_user = feedback_map_for_user

    async def recommendation_reasons(
        self,
        *,
        user_id: str,
        plan: str,
        limit: int,
    ) -> dict[str, Any]:
        feedback_map = await self._feedback_map_for_user(user_id)
        rows = await self._build_recommendations(
            user_id,
            plan=plan,
            feedback_map=feedback_map,
            limit=max(1, int(limit)),
        )
        reasons = [
            {
                "video_id": str(row.get("video_id") or ""),
                "title": str(row.get("title") or ""),
                "reasons": [str(x) for x in (row.get("recommendation_reason") or []) if str(x)],
            }
            for row in rows
            if str(row.get("video_id") or "")
        ]
        return {"count": len(reasons), "items": reasons}
