"""Idempotent curation of placeholder feature_registry entries + GPS state sync (iter801)."""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient

CURATED = {
    "ai-writer": ("create", "#8B5CF6", "Draft emails, reports, and polished content in seconds with an AI writing copilot tuned to your voice."),
    "ai-chatbot": ("chatbubbles", "#3B82F6", "Converse with a context-aware AI assistant that understands your goals and workspace."),
    "ai-search": ("search", "#F59E0B", "Ask in plain language and get instant, sourced answers across your knowledge base."),
    "ai-automations": ("flash", "#10B981", "Automate repetitive workflows with AI triggers, schedules, and smart actions."),
    "ai-cognitive": ("bulb", "#EC4899", "Advanced reasoning engines for analysis, planning, and confident decision support."),
    "medimate": ("medkit", "#EF4444", "Your AI health companion for symptom guidance, wellness plans, and medication reminders."),
    "fitness": ("barbell", "#F97316", "Personalized AI training programs, form coaching, and progress analytics."),
    "pennypilot": ("wallet", "#22C55E", "Smart budgeting and money coaching that turns spending data into savings wins."),
    "smartbuy": ("cart", "#06B6D4", "AI shopping intelligence that compares, tracks prices, and finds the best value."),
    "travelpal": ("map", "#0EA5E9", "Plan smarter trips with AI itineraries, local insights, and real-time travel guidance."),
    "ai-found-love": ("heart", "#F43F5E", "AI-guided relationship coaching and meaningful connection insights."),
    "smart-cars": ("car-sport", "#64748B", "Vehicle intelligence for buying, maintenance schedules, and cost-of-ownership clarity."),
    "buy-smart-home": ("home", "#A855F7", "Navigate property decisions with AI valuation, checklists, and negotiation prep."),
    "ai-video": ("videocam", "#8B5CF6", "Generate and edit professional video content with AI scene and script assistance."),
    "ai-photo": ("image", "#14B8A6", "Create studio-grade images and brand visuals with AI generation and retouching."),
    "ai-speech": ("mic", "#3B82F6", "Natural text-to-speech and voice tools for narration, dubbing, and accessibility."),
    "ai-enterprise": ("business", "#6366F1", "Enterprise controls, analytics, and governance for teams scaling with AI."),
    "school-tutor": ("school", "#F59E0B", "Personalized AI tutoring with step-by-step explanations across every subject."),
    "bill-generator": ("receipt", "#10B981", "Create branded invoices and bills in seconds with smart templates and tax handling."),
}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    updated_registry = 0
    for fid, (icon, color, desc) in CURATED.items():
        doc = await db.feature_registry.find_one({"feature_id": fid})
        if not doc:
            continue
        is_placeholder = str(doc.get("description", "")).endswith(" capability.") or doc.get("icon") in ("sparkles", "apps", None, "")
        if not is_placeholder:
            continue
        await db.feature_registry.update_one(
            {"feature_id": fid},
            {"$set": {"icon": icon, "color": color, "description": desc, "updated_at": now, "updated_by": "iter801_feature_curation"}},
        )
        updated_registry += 1

    state = await db.global_platform_state.find_one({"state_id": "global-platform-state"})
    updated_gps = 0
    if state and isinstance(state.get("features"), list):
        features = state["features"]
        for f in features:
            fid = f.get("feature_id")
            if fid in CURATED:
                icon, color, desc = CURATED[fid]
                is_placeholder = str(f.get("description", "")).endswith(" capability.") or f.get("icon") in ("sparkles", "apps", None, "")
                if is_placeholder:
                    f["icon"] = icon
                    f["color"] = color
                    f["description"] = desc
                    f["updated_at"] = now
                    updated_gps += 1
        if updated_gps:
            await db.global_platform_state.update_one(
                {"state_id": "global-platform-state"},
                {"$set": {"features": features, "updated_at": now}},
            )
    print(f"registry updated: {updated_registry}, gps features updated: {updated_gps}")


asyncio.run(main())
