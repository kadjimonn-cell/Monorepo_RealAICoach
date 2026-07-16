from __future__ import annotations

from typing import Any, Callable, Awaitable


class WatchVideosCatalogService:
    """Phase-1 modular catalog service while keeping route contracts unchanged."""

    def __init__(
        self,
        *,
        fetch_catalog: Callable[..., Awaitable[tuple[list[dict[str, Any]], int]]],
        sanitize_video: Callable[..., dict[str, Any]],
        watchlist_ids_for_user: Callable[[str], Awaitable[set[str]]],
        feedback_map_for_user: Callable[[str], Awaitable[dict[str, str]]],
    ) -> None:
        self._fetch_catalog = fetch_catalog
        self._sanitize_video = sanitize_video
        self._watchlist_ids_for_user = watchlist_ids_for_user
        self._feedback_map_for_user = feedback_map_for_user

    async def catalog_response(
        self,
        *,
        user_id: str,
        plan: str,
        query: str,
        category: str,
        limit: int,
        offset: int,
        sort_by: str,
    ) -> dict[str, Any]:
        feedback_map = await self._feedback_map_for_user(user_id)
        watchlist_ids = await self._watchlist_ids_for_user(user_id)
        rows, total = await self._fetch_catalog(
            plan=plan,
            query=query,
            category=category,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
        )
        items = [
            self._sanitize_video(
                row,
                feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
                watchlisted=str(row.get("video_id") or "") in watchlist_ids,
            )
            for row in rows
        ]
        return {
            "items": items,
            "total": int(total),
            "count": len(items),
            "has_more": int(offset) + len(items) < int(total),
        }
