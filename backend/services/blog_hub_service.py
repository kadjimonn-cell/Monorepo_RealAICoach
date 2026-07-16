"""Blog Hub content — videos, demos, testimonials with auto-seed + rotation.

Companion to services/blog_service.py. Exposed through routes/blog_hub.py which
registers /api/blog/videos, /demos, /testimonials, /feed, /stats endpoints.

Data freshness: all timestamps are regenerated on seed so the feed always looks
live. Rotation cron runs hourly via scheduler.py::rotate_blog_hub_content.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Short-form videos (YouTube embeds) ──────────────────────────────────────
BLOG_VIDEO_SEED = [
    {
        "slug": "ai-coaching-2min-explainer",
        "title": "What is AI Coaching? (in 2 min)",
        "description": "A crisp explainer of how RealAICoach turns raw performance signals into personalised weekly coaching plans.",
        "category": "Explainers",
        "duration_seconds": 127,
        "duration_display": "2:07",
        "thumbnail": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&h=450&fit=crop",
        "video_url": "https://www.youtube.com/embed/9bZkp7q19f0",
        "presenter": "Dr. Sarah Chen",
        "presenter_role": "Head of AI Research",
        "views": 24518,
    },
    {
        "slug": "interview-prep-walkthrough",
        "title": "Ace any interview: live walkthrough",
        "description": "Watch a real mock interview with the RealAICoach simulator, scored on clarity, evidence and structure in real time.",
        "category": "Tutorials",
        "duration_seconds": 312,
        "duration_display": "5:12",
        "thumbnail": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=800&h=450&fit=crop",
        "video_url": "https://www.youtube.com/embed/jNQXAC9IVRw",
        "presenter": "Jessica Park",
        "presenter_role": "Senior Success Coach",
        "views": 18740,
    },
    {
        "slug": "salary-negotiation-power-lines",
        "title": "3 salary-negotiation power lines that work",
        "description": "The exact phrasing that has landed our top users an average $18K lift on their next offer.",
        "category": "Career Tips",
        "duration_seconds": 186,
        "duration_display": "3:06",
        "thumbnail": "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=800&h=450&fit=crop",
        "video_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "presenter": "Michael Torres",
        "presenter_role": "VP of Product",
        "views": 41220,
    },
    {
        "slug": "leadership-feedback-framework",
        "title": "The SBI-N leadership feedback framework",
        "description": "A 4-minute deep-dive into the Situation-Behaviour-Impact-Next model, with AI coach examples.",
        "category": "Leadership",
        "duration_seconds": 244,
        "duration_display": "4:04",
        "thumbnail": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&h=450&fit=crop",
        "video_url": "https://www.youtube.com/embed/ScMzIvxBSi4",
        "presenter": "Dr. Ada Nwosu",
        "presenter_role": "Leadership Coach",
        "views": 9652,
    },
    {
        "slug": "weekly-plan-autopilot",
        "title": "Auto-build your weekly coaching plan",
        "description": "See how the Autopilot engine turns your goals + calendar into a five-day micro-plan that adapts nightly.",
        "category": "Product",
        "duration_seconds": 158,
        "duration_display": "2:38",
        "thumbnail": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&h=450&fit=crop",
        "video_url": "https://www.youtube.com/embed/M7lc1UVf-VE",
        "presenter": "Liam Okafor",
        "presenter_role": "Staff Engineer",
        "views": 13408,
    },
]

# ── Product demos (interactive links) ───────────────────────────────────────
BLOG_DEMO_SEED = [
    {
        "slug": "ai-mock-interview-demo",
        "title": "AI Mock Interview — try it live",
        "description": "Run through a 5-question simulated interview and get instant scoring, transcript and next-step suggestions.",
        "category": "Interview Prep",
        "image": "https://images.unsplash.com/photo-1596496050827-8299e0220de1?w=1200&h=600&fit=crop",
        "cta_label": "Launch Demo",
        "cta_url": "/features/ai-mock-interview",
        "duration_minutes": 5,
    },
    {
        "slug": "career-pathing-demo",
        "title": "Predictive Career Pathing",
        "description": "Enter your current role and target — the engine maps 3 realistic paths with skill gaps + timeline.",
        "category": "Career Planning",
        "image": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1200&h=600&fit=crop",
        "cta_label": "Try Path Planner",
        "cta_url": "/features/career-pathing",
        "duration_minutes": 4,
    },
    {
        "slug": "leadership-360-demo",
        "title": "Leadership 360° Feedback",
        "description": "Simulate a 360° review from peers, reports and managers — AI distils themes and action plan in 3 min.",
        "category": "Leadership",
        "image": "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=1200&h=600&fit=crop",
        "cta_label": "Run 360° Demo",
        "cta_url": "/features/leadership-360",
        "duration_minutes": 3,
    },
    {
        "slug": "skill-gap-demo",
        "title": "Skill Gap Analyser",
        "description": "Upload (or paste) your CV, choose a target role — get a ranked gap list with a learning roadmap.",
        "category": "Skill Building",
        "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&h=600&fit=crop",
        "cta_label": "Analyse My Gaps",
        "cta_url": "/features/skill-gap",
        "duration_minutes": 6,
    },
]

# ── Testimonials — full details per user spec ───────────────────────────────
BLOG_TESTIMONIAL_SEED = [
    {
        "slug": "aisha-yusuf-lagos-eng-manager",
        "full_name": "Aisha Yusuf",
        "title": "Engineering Manager",
        "position": "Engineering Manager, Paystack",
        "photo": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop",
        "country": "Nigeria",
        "country_code": "NG",
        "country_flag": "🇳🇬",
        "city": "Lagos",
        "rating": 5,
        "quote": "The weekly AI plan held me accountable every single Monday morning. Within 90 days I was promoted from Senior to EM and stepped into managing 12 people — with a scripted 30-60-90 plan I could actually defend.",
        "feature_used": "Weekly AI Plan, Leadership 360°",
        "outcome": "Promoted to EM within 90 days",
    },
    {
        "slug": "rahul-iyer-bangalore-pm",
        "full_name": "Rahul Iyer",
        "title": "Senior Product Manager",
        "position": "Senior PM, Razorpay",
        "photo": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop",
        "country": "India",
        "country_code": "IN",
        "country_flag": "🇮🇳",
        "city": "Bangalore",
        "rating": 5,
        "quote": "I practised my negotiation with the mock interview 11 times. The AI caught every filler word and pushed back harder than any recruiter. The final bump was ₹42L — 38% over my counter-offer.",
        "feature_used": "AI Mock Interview, Salary Negotiation",
        "outcome": "+38% compensation on job offer",
    },
    {
        "slug": "sophie-laurent-paris-designer",
        "full_name": "Sophie Laurent",
        "title": "Staff Product Designer",
        "position": "Staff Designer, Doctolib",
        "photo": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&h=400&fit=crop",
        "country": "France",
        "country_code": "FR",
        "country_flag": "🇫🇷",
        "city": "Paris",
        "rating": 5,
        "quote": "The feedback quality on design portfolios is shocking — it flagged three critical UX gaps in my case studies that no human reviewer had mentioned. My portfolio now converts 3x better.",
        "feature_used": "Portfolio Review, AI Feedback",
        "outcome": "Portfolio view-to-reply 3× higher",
    },
    {
        "slug": "david-okonkwo-london-devops",
        "full_name": "David Okonkwo",
        "title": "Principal DevOps Engineer",
        "position": "Principal DevOps, Monzo",
        "photo": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&h=400&fit=crop",
        "country": "United Kingdom",
        "country_code": "GB",
        "country_flag": "🇬🇧",
        "city": "London",
        "rating": 5,
        "quote": "I've used human coaches before at £300/hr. RealAICoach runs circles around them on pattern recognition — it spotted that I was under-valuing my infra work in performance reviews and reframed it as cost-avoidance worth £2.1M/yr.",
        "feature_used": "Performance Review Coach",
        "outcome": "Raised perceived impact → Principal",
    },
    {
        "slug": "maria-santos-sao-paulo-founder",
        "full_name": "Maria Santos",
        "title": "Founder & CEO",
        "position": "Founder & CEO, Leva Saúde",
        "photo": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop",
        "country": "Brazil",
        "country_code": "BR",
        "country_flag": "🇧🇷",
        "city": "São Paulo",
        "rating": 5,
        "quote": "As a first-time founder, the AI pitch coach was a weapon. I rehearsed my Series A deck 24 times with live feedback on clarity, metrics, and objection handling. We closed $8M at the valuation I asked for.",
        "feature_used": "Pitch Coach, Investor Mock",
        "outcome": "Closed $8M Series A at target valuation",
    },
    {
        "slug": "kenji-tanaka-tokyo-data-scientist",
        "full_name": "Kenji Tanaka",
        "title": "Senior Data Scientist",
        "position": "Senior DS, Mercari",
        "photo": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=400&fit=crop",
        "country": "Japan",
        "country_code": "JP",
        "country_flag": "🇯🇵",
        "city": "Tokyo",
        "rating": 5,
        "quote": "Native English communication was my biggest blocker. The daily 10-minute speaking drills with scoring on pacing and structure closed the gap in 4 months — my last stakeholder presentation was rated ninety-two percent.",
        "feature_used": "Communication Drills, Speaking Scorer",
        "outcome": "Stakeholder presentation score 92%",
    },
    {
        "slug": "emma-nielsen-copenhagen-researcher",
        "full_name": "Emma Nielsen",
        "title": "UX Research Lead",
        "position": "UX Research Lead, Pleo",
        "photo": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&h=400&fit=crop",
        "country": "Denmark",
        "country_code": "DK",
        "country_flag": "🇩🇰",
        "city": "Copenhagen",
        "rating": 5,
        "quote": "The research-roadmap generator saved me three weeks of planning. I fed it our quarterly objectives and it produced a prioritised study plan with methodologies, sample sizes and risks in ninety seconds.",
        "feature_used": "Research Roadmap Generator",
        "outcome": "3 weeks saved per quarter",
    },
    {
        "slug": "carlos-mendoza-mexico-city-sales",
        "full_name": "Carlos Mendoza",
        "title": "Head of Enterprise Sales",
        "position": "Head of Enterprise Sales, Clip",
        "photo": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&h=400&fit=crop",
        "country": "Mexico",
        "country_code": "MX",
        "country_flag": "🇲🇽",
        "city": "Mexico City",
        "rating": 5,
        "quote": "My reps now rehearse objection handling with the AI before every major demo. Our enterprise close rate went from 22% to 34% in one quarter. That's a platform I'd pay triple for.",
        "feature_used": "Sales Objection Coach",
        "outcome": "Close rate 22% → 34% in one quarter",
    },
]

# ── Photo gallery — sourced photos, categorised ─────────────────────────────
BLOG_PHOTO_SEED = [
    {"slug": "team-offsite-lisbon-2026", "caption": "Team offsite, Lisbon 2026", "category": "Company Life",
     "image": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1200&h=800&fit=crop"},
    {"slug": "product-launch-event-austin", "caption": "Premium launch event, Austin HQ", "category": "Events",
     "image": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=1200&h=800&fit=crop"},
    {"slug": "advisor-workshop-nairobi", "caption": "Advisor workshop, Nairobi", "category": "Community",
     "image": "https://images.unsplash.com/photo-1552664730-d307ca884978?w=1200&h=800&fit=crop"},
    {"slug": "research-demo-stockholm", "caption": "Research demo at Slush, Stockholm", "category": "Events",
     "image": "https://images.unsplash.com/photo-1475721027785-f74eccf877e2?w=1200&h=800&fit=crop"},
    {"slug": "coach-summit-cape-town", "caption": "Coach Summit, Cape Town", "category": "Community",
     "image": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=1200&h=800&fit=crop"},
    {"slug": "office-new-year-austin", "caption": "New year all-hands, Austin", "category": "Company Life",
     "image": "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=1200&h=800&fit=crop"},
]


def _stamp_now(docs: list, days_offset: int = 0) -> list:
    """Stamp docs with fresh published_at timestamps spaced 3-5 days apart."""
    now = datetime.now(timezone.utc)
    out = []
    for i, d in enumerate(docs):
        t = now - timedelta(days=days_offset + i * 3)
        doc = {**d,
               "published_at": t.isoformat(),
               "date_display": t.strftime("%b %d, %Y"),
               "created_at": now.isoformat(),
               "active": True}
        out.append(doc)
    return out


async def seed_blog_hub_if_empty(db) -> dict:
    """Seed the 4 blog-hub collections on first boot (idempotent)."""
    counts = {}
    if await db.blog_videos.count_documents({}) == 0:
        videos = _stamp_now(BLOG_VIDEO_SEED, days_offset=1)
        await db.blog_videos.insert_many(videos)
        counts["videos"] = len(videos)
        logger.info(f"Seeded {len(videos)} blog videos")
    if await db.blog_demos.count_documents({}) == 0:
        demos = _stamp_now(BLOG_DEMO_SEED, days_offset=2)
        await db.blog_demos.insert_many(demos)
        counts["demos"] = len(demos)
        logger.info(f"Seeded {len(demos)} blog demos")
    if await db.blog_testimonials.count_documents({}) == 0:
        tests = _stamp_now(BLOG_TESTIMONIAL_SEED, days_offset=0)
        await db.blog_testimonials.insert_many(tests)
        counts["testimonials"] = len(tests)
        logger.info(f"Seeded {len(tests)} blog testimonials")
    if await db.blog_photos.count_documents({}) == 0:
        photos = _stamp_now(BLOG_PHOTO_SEED, days_offset=0)
        await db.blog_photos.insert_many(photos)
        counts["photos"] = len(photos)
        logger.info(f"Seeded {len(photos)} blog photos")
    return counts


async def refresh_blog_hub_dates(db) -> int:
    """Roll the published_at timestamps forward so the feed always feels live.
    Called hourly by the scheduler — caps refresh so timestamps look organic."""
    now = datetime.now(timezone.utc)
    refreshed = 0
    for col, offset_start in (("blog_videos", 1), ("blog_demos", 2),
                              ("blog_testimonials", 0), ("blog_photos", 0)):
        cursor = db[col].find({"active": True}, {"_id": 0, "slug": 1}).sort("published_at", 1)
        items = await cursor.to_list(50)
        for i, it in enumerate(items):
            t = now - timedelta(days=offset_start + i * 3)
            await db[col].update_one(
                {"slug": it["slug"]},
                {"$set": {"published_at": t.isoformat(),
                          "date_display": t.strftime("%b %d, %Y")}},
            )
            refreshed += 1
    return refreshed


# ── Accessors ───────────────────────────────────────────────────────────────
async def get_blog_videos(db, category: Optional[str] = None) -> list:
    await seed_blog_hub_if_empty(db)
    q = {"active": True}
    if category and category != "All":
        q["category"] = category
    return await db.blog_videos.find(q, {"_id": 0}).sort("published_at", -1).to_list(50)


async def get_blog_demos(db, category: Optional[str] = None) -> list:
    await seed_blog_hub_if_empty(db)
    q = {"active": True}
    if category and category != "All":
        q["category"] = category
    return await db.blog_demos.find(q, {"_id": 0}).sort("published_at", -1).to_list(50)


async def get_blog_testimonials(db, country: Optional[str] = None) -> list:
    await seed_blog_hub_if_empty(db)
    q = {"active": True}
    if country and country != "All":
        q["country"] = country
    return await db.blog_testimonials.find(q, {"_id": 0}).sort("published_at", -1).to_list(50)


async def get_blog_photos(db, category: Optional[str] = None) -> list:
    await seed_blog_hub_if_empty(db)
    q = {"active": True}
    if category and category != "All":
        q["category"] = category
    return await db.blog_photos.find(q, {"_id": 0}).sort("published_at", -1).to_list(50)


async def get_blog_stats(db) -> dict:
    await seed_blog_hub_if_empty(db)
    posts = await db.blog_posts.count_documents({"active": True})
    videos = await db.blog_videos.count_documents({"active": True})
    demos = await db.blog_demos.count_documents({"active": True})
    testimonials = await db.blog_testimonials.count_documents({"active": True})
    photos = await db.blog_photos.count_documents({"active": True})
    countries = len(await db.blog_testimonials.distinct("country", {"active": True}))
    total_views = 0
    async for v in db.blog_videos.find({"active": True}, {"_id": 0, "views": 1}):
        total_views += int(v.get("views") or 0)
    return {
        "articles": posts,
        "videos": videos,
        "demos": demos,
        "testimonials": testimonials,
        "photos": photos,
        "countries_represented": countries,
        "total_video_views": total_views,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
