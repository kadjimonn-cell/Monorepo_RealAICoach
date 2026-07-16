from __future__ import annotations

from typing import Any, Callable, Awaitable
import uuid


class WatchVideosPlaybackService:
    """Phase-1 modular playback interaction service."""

    def __init__(
        self,
        *,
        quota_snapshot: Callable[..., Awaitable[dict[str, Any]]],
        daily_watch_limit: Callable[[Any, str], int],
        today_key: Callable[[], str],
        now_iso: Callable[[], str],
        sanitize_video: Callable[..., dict[str, Any]],
        catalog_projection: Callable[[], dict[str, int]],
        resolve_plan: Callable[[Any], str],
        visibility_filter: Callable[[str], dict[str, Any]],
        db: Any,
        coll_catalog: str,
        coll_watch_usage: str,
        coll_watch_history: str,
        coll_feedback: str,
        coll_watchlist: str,
    ) -> None:
        self._quota_snapshot = quota_snapshot
        self._daily_watch_limit = daily_watch_limit
        self._today_key = today_key
        self._now_iso = now_iso
        self._sanitize_video = sanitize_video
        self._catalog_projection = catalog_projection
        self._resolve_plan = resolve_plan
        self._visibility_filter = visibility_filter
        self._db = db
        self._coll_catalog = coll_catalog
        self._coll_watch_usage = coll_watch_usage
        self._coll_watch_history = coll_watch_history
        self._coll_feedback = coll_feedback
        self._coll_watchlist = coll_watchlist

    async def track_watch(self, *, user: Any, payload: Any) -> dict[str, Any]:
        plan = self._resolve_plan(user)
        day_key = self._today_key()
        now_iso = self._now_iso()
        limit = self._daily_watch_limit(user, plan)
        usage_coll = self._db[self._coll_watch_usage]
        history_coll = self._db[self._coll_watch_history]

        usage_query = {"user_id": user.user_id, "video_id": payload.video_id, "day_key": day_key}
        existing_usage = await usage_coll.find_one(usage_query, {"_id": 0, "usage_id": 1})
        quota = await self._quota_snapshot(user)

        if not existing_usage:
            if int(limit) >= 0 and int(quota.get("used") or 0) >= int(limit):
                return {
                    "success": False,
                    "error": "daily_watch_cap_reached",
                    "message": f"Daily watch cap reached for {plan} plan.",
                    "quota": quota,
                }

            await usage_coll.insert_one(
                {
                    "usage_id": f"wv_use_{uuid.uuid4().hex[:12]}",
                    "user_id": user.user_id,
                    "video_id": payload.video_id,
                    "day_key": day_key,
                    "plan": plan,
                    "source": str(payload.source or "player")[:40],
                    "created_at": now_iso,
                }
            )
            quota["used"] = int(quota.get("used") or 0) + 1
            quota["remaining"] = -1 if int(limit) < 0 else max(0, int(limit) - int(quota["used"]))
            await self._db[self._coll_catalog].update_one(
                {"video_id": payload.video_id},
                {"$inc": {"view_count": 1}, "$set": {"updated_at": now_iso}},
            )

        safe_duration = max(0, int(payload.duration_seconds or 0))
        safe_progress = max(0, int(payload.progress_seconds or 0))
        if safe_duration > 0:
            safe_progress = min(safe_progress, safe_duration)
        completion_ratio = 0.0
        if safe_duration > 0:
            completion_ratio = round(min(1.0, safe_progress / safe_duration), 4)
        completed = bool(payload.completed or (safe_duration > 0 and completion_ratio >= 0.98))

        await history_coll.update_one(
            {"user_id": user.user_id, "video_id": payload.video_id},
            {
                "$set": {
                    "user_id": user.user_id,
                    "video_id": payload.video_id,
                    "plan": plan,
                    "progress_seconds": safe_progress,
                    "duration_seconds": safe_duration,
                    "completion_ratio": completion_ratio,
                    "completed": completed,
                    "last_watched_at": now_iso,
                    "source": str(payload.source or "player")[:40],
                    "updated_at": now_iso,
                },
                "$setOnInsert": {
                    "watch_id": f"wv_hist_{uuid.uuid4().hex[:12]}",
                    "created_at": now_iso,
                    "first_watched_at": now_iso,
                },
            },
            upsert=True,
        )

        history_row = await history_coll.find_one(
            {"user_id": user.user_id, "video_id": payload.video_id},
            {
                "_id": 0,
                "watch_id": 1,
                "video_id": 1,
                "progress_seconds": 1,
                "duration_seconds": 1,
                "completion_ratio": 1,
                "completed": 1,
                "last_watched_at": 1,
                "first_watched_at": 1,
            },
        ) or {}

        return {
            "success": True,
            "video_id": payload.video_id,
            "quota": quota,
            "history": history_row,
        }

    async def set_feedback(self, *, user: Any, payload: Any) -> dict[str, Any]:
        now_iso = self._now_iso()
        feedback_coll = self._db[self._coll_feedback]

        previous_doc = await feedback_coll.find_one(
            {"user_id": user.user_id, "video_id": payload.video_id},
            {"_id": 0, "feedback": 1},
        ) or {}
        previous_feedback = str(previous_doc.get("feedback") or "")

        if payload.feedback == "clear":
            await feedback_coll.delete_many({"user_id": user.user_id, "video_id": payload.video_id})
        else:
            await feedback_coll.update_one(
                {"user_id": user.user_id, "video_id": payload.video_id},
                {
                    "$set": {
                        "user_id": user.user_id,
                        "video_id": payload.video_id,
                        "feedback": payload.feedback,
                        "updated_at": now_iso,
                    },
                    "$setOnInsert": {
                        "feedback_id": f"wv_fb_{uuid.uuid4().hex[:12]}",
                        "created_at": now_iso,
                    },
                },
                upsert=True,
            )

        like_delta = 0
        if previous_feedback == "like" and payload.feedback != "like":
            like_delta -= 1
        if previous_feedback != "like" and payload.feedback == "like":
            like_delta += 1
        if like_delta != 0:
            await self._db[self._coll_catalog].update_one(
                {"video_id": payload.video_id},
                {"$inc": {"like_count": like_delta}, "$set": {"updated_at": now_iso}},
            )

        return {
            "success": True,
            "video_id": payload.video_id,
            "feedback": payload.feedback,
            "updated_at": now_iso,
        }

    async def toggle_watchlist(self, *, user: Any, payload: Any) -> dict[str, Any]:
        watchlist_coll = self._db[self._coll_watchlist]
        now_iso = self._now_iso()
        existing = await watchlist_coll.find_one(
            {"user_id": user.user_id, "video_id": payload.video_id},
            {"_id": 0, "video_id": 1},
        )
        in_watchlist = bool(existing)

        action = str(payload.action or "toggle")
        target_watchlisted = in_watchlist
        if action == "add":
            target_watchlisted = True
        elif action == "remove":
            target_watchlisted = False
        else:
            target_watchlisted = not in_watchlist

        if target_watchlisted:
            await watchlist_coll.update_one(
                {"user_id": user.user_id, "video_id": payload.video_id},
                {
                    "$set": {
                        "user_id": user.user_id,
                        "video_id": payload.video_id,
                        "updated_at": now_iso,
                    },
                    "$setOnInsert": {"added_at": now_iso},
                },
                upsert=True,
            )
        else:
            await watchlist_coll.delete_many({"user_id": user.user_id, "video_id": payload.video_id})

        count = await watchlist_coll.count_documents({"user_id": user.user_id})
        return {
            "success": True,
            "video_id": payload.video_id,
            "watchlisted": bool(target_watchlisted),
            "watchlist_count": int(count),
        }
