from fastapi import APIRouter, Request
from .db import db, get_current_user

router = APIRouter()

FEATURE_META = {
    "ai-writer": {"title": "AI Writer", "icon": "create", "color": "#10B981"},
    "fitness": {"title": "Fitness", "icon": "barbell", "color": "#F59E0B"},
    "pennypilot": {"title": "PennyPilot", "icon": "wallet", "color": "#6366F1"},
    "smart-cars": {"title": "Smart Cars", "icon": "car", "color": "#EF4444"},
    "buy-smart-home": {"title": "Real Estate", "icon": "home", "color": "#3B82F6"},
    "school-tutor": {"title": "Tutor", "icon": "school", "color": "#8B5CF6"},
    "ai-found-love": {"title": "Dating", "icon": "heart", "color": "#EC4899"},
    "travelpal": {"title": "TravelPal", "icon": "airplane", "color": "#0EA5E9"},
    "smartbuy": {"title": "SmartBuy", "icon": "cart", "color": "#F97316"},
    "medimate": {"title": "MediMate", "icon": "medkit", "color": "#10B981"},
    "phone-call": {"title": "AI Call", "icon": "call", "color": "#10B981"},
    "ai-chat": {"title": "AI Chat", "icon": "chatbubbles", "color": "#3B82F6"},
    "ai-scanner": {"title": "Scanner", "icon": "scan", "color": "#0EA5E9"},
    "ai-translate": {"title": "Translate", "icon": "language", "color": "#8B5CF6"},
    "ai-code": {"title": "AI Code", "icon": "code-slash", "color": "#F59E0B"},
    "ai-image": {"title": "AI Image", "icon": "image", "color": "#EC4899"},
    "health-dashboard": {"title": "Health", "icon": "pulse", "color": "#10B981"},
}

ALL_FEATURE_KEYS = list(FEATURE_META.keys())


@router.get("/home/personalized")
async def get_personalized_home(request: Request):
    """Get personalized home data: recently used, recommendations, notifications."""
    user = await get_current_user(request)
    uid = user.user_id if user else None

    recently_used = []
    recommendations = []
    notifications_preview = []
    continue_item = None

    if uid:
        # Recently used features (from action log)
        pipeline = [
            {"$match": {"user_id": uid}},
            {"$sort": {"timestamp": -1}},
            {"$group": {"_id": "$feature_key", "last_used": {"$first": "$timestamp"}, "count": {"$sum": 1}}},
            {"$sort": {"last_used": -1}},
            {"$limit": 8},
        ]
        recent_raw = await db.action_history.aggregate(pipeline).to_list(8)

        used_keys = set()
        for r in recent_raw:
            fk = r["_id"]
            if fk and fk in FEATURE_META:
                meta = FEATURE_META[fk]
                recently_used.append(
                    {
                        "feature_key": fk,
                        "title": meta["title"],
                        "icon": meta["icon"],
                        "color": meta["color"],
                        "last_used": r["last_used"],
                        "use_count": r["count"],
                    }
                )
                used_keys.add(fk)

        # Continue where you left off = most recent
        if recently_used:
            continue_item = recently_used[0]

        # Smart recommendations = features NOT used yet
        unused = [k for k in ALL_FEATURE_KEYS if k not in used_keys]
        import random

        random.shuffle(unused)
        for fk in unused[:4]:
            meta = FEATURE_META[fk]
            recommendations.append(
                {
                    "feature_key": fk,
                    "title": meta["title"],
                    "icon": meta["icon"],
                    "color": meta["color"],
                    "reason": "New for you",
                }
            )

        # If not enough recs, add popular ones
        if len(recommendations) < 4:
            popular = [
                k
                for k in ["ai-writer", "fitness", "pennypilot", "school-tutor", "phone-call"]
                if k not in used_keys and k not in [r["feature_key"] for r in recommendations]
            ]
            for fk in popular[: 4 - len(recommendations)]:
                meta = FEATURE_META[fk]
                recommendations.append(
                    {
                        "feature_key": fk,
                        "title": meta["title"],
                        "icon": meta["icon"],
                        "color": meta["color"],
                        "reason": "Popular",
                    }
                )

        # Notifications preview (last 5)
        notifs = (
            await db.notifications.find(
                {"user_id": uid}, {"_id": 0, "title": 1, "message": 1, "type": 1, "created_at": 1, "read": 1}
            )
            .sort("created_at", -1)
            .to_list(5)
        )
        notifications_preview = notifs

    return {
        "continue_item": continue_item,
        "recently_used": recently_used[:6],
        "recommendations": recommendations[:4],
        "notifications_preview": notifications_preview,
    }
