from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from shared.pricing_policy import get_yearly_price_map


REQUIRED_STRICT_SURFACE_LABEL_KEYS: List[str] = [
    "home.metrics.refresh_note",
    "home.stale.title",
    "home.stale.subtitle",
    "home.stale.retry",
    "home.gps.version_prefix",
    "home.gps.syncing",
    "home.tour.title",
    "home.nova.fab.template",
    "home.nova.panel.title",
    "home.nova.panel.subtitle",
    "home.nova.input.placeholder",
    "home.nova.send",
    "home.nova.close",
    "home.nova.welcome",
    "home.nova.error.unauthorized",
    "home.nova.error.generic",
    "home.nova.context.summary",
    "home.nova.launcher.aria",
    "home.nova.search.prefill",
    "home.nova.context.title",
    "home.nova.loading",
    "home.nova.search.accessibility",
    "home.nova.close.accessibility",
    "home.nova.send.accessibility",
    "help.surface.ready",
    "features.header.title",
    "features.header.count_label",
    "features.header.subtitle",
    "features.search.placeholder",
    "features.category.all",
    "features.results.label",
    "features.empty.description",
    "features.empty.title",
    "features.empty.subtitle",
    "notifications.pref.push.label",
    "notifications.pref.push.desc",
    "notifications.pref.email.label",
    "notifications.pref.email.desc",
    "notifications.pref.daily.label",
    "notifications.pref.daily.desc",
    "notifications.pref.weekly.label",
    "notifications.pref.weekly.desc",
    "notifications.pref.team.label",
    "notifications.pref.team.desc",
    "notifications.pref.goal.label",
    "notifications.pref.goal.desc",
    "notifications.pref.practice.label",
    "notifications.pref.practice.desc",
    "notifications.pref.achievement.label",
    "notifications.pref.achievement.desc",
    "notifications.pref.coaching.label",
    "notifications.pref.coaching.desc",
    "notifications.pref.quiet_hours.title",
    "notifications.pref.quiet_hours.desc",
    "notifications.pref.quiet_hours.start",
    "notifications.pref.quiet_hours.end",
    "notifications.pref.save",
    "common.close",
    "common.saving",
]

# Default seed values for required strict-surface label keys.
# These are injected when a key is missing from the GPS state to prevent
# the GpsLabelBlocker from blocking critical surfaces on fresh installs.
STRICT_SURFACE_LABEL_DEFAULTS: Dict[str, str] = {
    "home.metrics.refresh_note": "Live metrics refresh automatically",
    "home.stale.title": "Data may be outdated",
    "home.stale.subtitle": "We could not refresh your dashboard. Please try again.",
    "home.stale.retry": "Retry",
    "home.gps.version_prefix": "GPS v",
    "home.gps.syncing": "Syncing...",
    "home.tour.title": "Take a Tour",
    "home.nova.fab.template": "{count} Features \u00B7 Nova",
    "home.nova.panel.title": "Nova",
    "home.nova.panel.subtitle": "AI Assistant",
    "home.nova.input.placeholder": "Ask Nova anything...",
    "home.nova.send": "Send",
    "home.nova.close": "Close",
    "home.nova.welcome": "Hi! I'm Nova, your AI assistant. How can I help you today?",
    "home.nova.error.unauthorized": "Please sign in to chat with Nova.",
    "home.nova.error.generic": "Something went wrong. Please try again.",
    "home.nova.context.summary": "Platform context loaded",
    "home.nova.launcher.aria": "Open Nova AI assistant",
    "home.nova.search.prefill": "Search features...",
    "home.nova.context.title": "Context",
    "home.nova.loading": "Thinking...",
    "home.nova.search.accessibility": "Search",
    "home.nova.close.accessibility": "Close Nova",
    "home.nova.send.accessibility": "Send message",
    "help.surface.ready": "ready",
    "features.header.title": "AI Feature Gallery",
    "features.header.count_label": "features",
    "features.header.subtitle": "Explore our full suite of AI-powered tools",
    "features.search.placeholder": "Search features...",
    "features.category.all": "All",
    "features.results.label": "results",
    "features.empty.description": "No features match your search criteria.",
    "features.empty.title": "No features found",
    "features.empty.subtitle": "Try a different search term or category.",
    "notifications.pref.push.label": "Push Notifications",
    "notifications.pref.push.desc": "Receive push notifications on your device",
    "notifications.pref.email.label": "Email Notifications",
    "notifications.pref.email.desc": "Receive notifications via email",
    "notifications.pref.daily.label": "Daily Digest",
    "notifications.pref.daily.desc": "Get a daily summary of activity",
    "notifications.pref.weekly.label": "Weekly Report",
    "notifications.pref.weekly.desc": "Get a weekly progress report",
    "notifications.pref.team.label": "Team Updates",
    "notifications.pref.team.desc": "Notifications about team activity",
    "notifications.pref.goal.label": "Goal Reminders",
    "notifications.pref.goal.desc": "Reminders about your goals and milestones",
    "notifications.pref.practice.label": "Practice Reminders",
    "notifications.pref.practice.desc": "Reminders to practice and stay on track",
    "notifications.pref.achievement.label": "Achievement Alerts",
    "notifications.pref.achievement.desc": "Notifications when you earn achievements",
    "notifications.pref.coaching.label": "Coaching Insights",
    "notifications.pref.coaching.desc": "AI-powered coaching tips and insights",
    "notifications.pref.quiet_hours.title": "Quiet Hours",
    "notifications.pref.quiet_hours.desc": "Pause notifications during specified hours",
    "notifications.pref.quiet_hours.start": "Start Time",
    "notifications.pref.quiet_hours.end": "End Time",
    "notifications.pref.save": "Save Preferences",
    "common.close": "Close",
    "common.saving": "Saving...",
}

WELCOME_MESSAGING_DEFAULTS: Dict[str, Any] = {
    "quick_questions": [
        "What can you help me with?",
        "How does AI coaching work?",
        "How do I upgrade or manage my plan?",
    ],
    "trust_names": [
        "Google",
        "Microsoft",
        "Amazon",
        "Meta",
        "Stripe",
    ],
    "welcome_testimonials": [
        {
            "name": "Sarah Chen",
            "role": "VP of Engineering",
            "company": "TechCorp",
            "quote": "RealAICoach transformed how our engineering leaders develop. The AI coaching is incredibly personalized — it feels like having a world-class mentor available 24/7.",
            "rating": 5,
            "outcome": "42% faster onboarding readiness",
            "segment": "Engineering",
            "seeded": True,
        },
        {
            "name": "Marcus Johnson",
            "role": "Founder & CEO",
            "company": "GrowthLab",
            "quote": "The strategic clarity and execution confidence we gained in one quarter surpassed what we expected in a full year.",
            "rating": 5,
            "outcome": "35% uplift in ramp consistency",
            "segment": "Executive",
            "seeded": True,
        },
        {
            "name": "Priya Patel",
            "role": "Director of L&D",
            "company": "Fortune 500",
            "quote": "Our teams now operate with clear weekly priorities and measurable outcomes. Coaching quality stayed consistent at scale.",
            "rating": 5,
            "outcome": "31% improvement in manager follow-through",
            "segment": "L&D",
            "seeded": True,
        },
        {
            "name": "Sophia Bennett",
            "role": "Director of L&D",
            "company": "Northbridge Financial",
            "quote": "RealAICoach helped us standardize coaching quality across regions without slowing team execution.",
            "rating": 5,
            "outcome": "42% faster onboarding readiness",
            "segment": "L&D",
            "seeded": True,
        },
        {
            "name": "Daniel Kim",
            "role": "VP People Operations",
            "company": "Vertex Systems",
            "quote": "The platform turned coaching from an ad-hoc activity into a repeatable operating rhythm.",
            "rating": 5,
            "outcome": "31% improvement in manager follow-through",
            "segment": "People Ops",
            "seeded": True,
        },
        {
            "name": "Amelia Rivera",
            "role": "Chief Operating Officer",
            "company": "Aquila Commerce",
            "quote": "We finally have visibility into behavior change, not just completion metrics.",
            "rating": 5,
            "outcome": "28% increase in team execution velocity",
            "segment": "Executive",
            "seeded": True,
        },
        {
            "name": "Noah Alvarez",
            "role": "Head of Customer Success",
            "company": "Brightwell Cloud",
            "quote": "Our CSM teams now get practical prompts tied directly to business outcomes.",
            "rating": 5,
            "outcome": "24% improvement in retention-focused coaching",
            "segment": "Customer Success",
            "seeded": True,
        },
        {
            "name": "Elena Novak",
            "role": "Chief Compliance Officer",
            "company": "Stratos Health",
            "quote": "The governance and diagnostics layer gave our risk team confidence from day one.",
            "rating": 5,
            "outcome": "Audit prep time reduced by 33%",
            "segment": "Compliance",
            "seeded": True,
        },
        {
            "name": "Jared Collins",
            "role": "Engineering Director",
            "company": "SignalForge",
            "quote": "The coaching workflows improved decision clarity across technical leads.",
            "rating": 5,
            "outcome": "26% faster project handoff quality",
            "segment": "Engineering",
            "seeded": True,
        },
        {
            "name": "Mina Park",
            "role": "Head of Talent Strategy",
            "company": "Silverline Retail Group",
            "quote": "Employees actually return to the platform because the guidance feels timely and relevant.",
            "rating": 5,
            "outcome": "39% increase in growth-path engagement",
            "segment": "Talent",
            "seeded": True,
        },
    ],
    "welcome_activities": [
        {"user": "Sarah M.", "action": "completed a leadership coaching session", "time": "2m ago", "icon": "chatbubble", "color": "#14B8A6", "seeded": True},
        {"user": "James K.", "action": "achieved this week’s strategic goal", "time": "5m ago", "icon": "trophy", "color": "#F59E0B", "seeded": True},
        {"user": "Emily R.", "action": "started a 7-day productivity streak", "time": "8m ago", "icon": "flash", "color": "#6366F1", "seeded": True},
        {"user": "Michael D.", "action": "earned a leadership excellence badge", "time": "12m ago", "icon": "medal", "color": "#10B981", "seeded": True},
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_features(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for i, raw in enumerate(items or []):
        feature_id = str(raw.get("feature_id") or raw.get("id") or "").strip()
        if not feature_id:
            continue
        cleaned.append(
            {
                "feature_id": feature_id,
                "title": str(raw.get("title") or feature_id),
                "description": str(raw.get("description") or ""),
                "status": str(raw.get("status") or ("active" if raw.get("enabled", True) else "inactive")),
                "availability": str(raw.get("availability") or ("premium" if raw.get("premium") else "all")),
                "category": str(raw.get("category") or "general"),
                "icon": str(raw.get("icon") or "apps"),
                "route": str(raw.get("route") or f"/features/{feature_id}"),
                "color": str(raw.get("color") or "#14B8A6"),
                "is_new": bool(raw.get("is_new") or raw.get("isNew") or False),
                "enabled": bool(raw.get("enabled", True)),
                "soft_deactivated": bool(raw.get("soft_deactivated", False)),
                "soft_deactivation_phase": str(raw.get("soft_deactivation_phase") or ""),
                "soft_deactivated_at": str(raw.get("soft_deactivated_at") or ""),
                "soft_deactivation_reason": str(raw.get("soft_deactivation_reason") or ""),
                "sort_order": int(raw.get("sort_order", i)),
                "updated_at": str(raw.get("updated_at") or now_iso()),
            }
        )
    cleaned.sort(key=lambda item: item.get("sort_order", 0))
    return cleaned


def sanitize_plans(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    canonical_yearly_prices = get_yearly_price_map()
    for raw in items or []:
        plan_id = str(raw.get("plan_id") or raw.get("id") or raw.get("name") or "").strip().lower().replace(" ", "-")
        if not plan_id:
            continue
        monthly = raw.get("monthly_price")
        yearly = raw.get("yearly_price")
        resolved_yearly = canonical_yearly_prices.get(plan_id)
        if resolved_yearly is None:
            resolved_yearly = float(yearly if yearly is not None else 0)
        plans.append(
            {
                "plan_id": plan_id,
                "name": str(raw.get("name") or plan_id.title()),
                "description": str(raw.get("description") or ""),
                "status": str(raw.get("status") or "active"),
                "currency": str(raw.get("currency") or "USD"),
                "monthly_price": float(monthly if monthly is not None else 0),
                "yearly_price": float(resolved_yearly),
                "features": [str(v) for v in (raw.get("features") or [])],
                "limitations": [str(v) for v in (raw.get("limitations") or [])],
                "updated_at": str(raw.get("updated_at") or now_iso()),
            }
        )
    return plans


def sanitize_faq(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    faq: List[Dict[str, Any]] = []
    for i, raw in enumerate(items or []):
        question = str(raw.get("question") or raw.get("q") or "").strip()
        answer = str(raw.get("answer") or raw.get("a") or "").strip()
        if not question or not answer:
            continue
        faq.append(
            {
                "faq_id": str(raw.get("faq_id") or f"faq_{i}_{uuid.uuid4().hex[:8]}"),
                "lang": str(raw.get("lang") or "en")[:2],
                "question": question,
                "answer": answer,
                "category": str(raw.get("category") or "general"),
                "active": bool(raw.get("active", True)),
                "order": int(raw.get("order", i)),
                "updated_at": str(raw.get("updated_at") or now_iso()),
            }
        )
    faq.sort(key=lambda item: item.get("order", 0))
    return faq


def derive_categories(features: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cats = sorted({str(f.get("category") or "general") for f in features if f.get("enabled", True)})
    return [{"id": "all", "label": "All"}] + [{"id": c, "label": c.replace("-", " ").title()} for c in cats]


def build_meta(state: Dict[str, Any]) -> Dict[str, Any]:
    features = [f for f in (state.get("features") or []) if f.get("enabled", True)]
    plans = [p for p in (state.get("plans") or []) if p.get("status") != "deprecated"]
    faq = [f for f in (state.get("faq") or []) if f.get("active", True)]
    return {
        "counts": {
            "features": len(features),
            "plans": len(plans),
            "faq": len(faq),
            "knowledge_docs": len((state.get("assistant_knowledge") or {}).get("documents") or []),
        },
        "categories": derive_categories(features),
        "updated_at": str(state.get("updated_at") or now_iso()),
    }


def ensure_strict_surface_label_pack(labels: Dict[str, str]) -> tuple[Dict[str, str], bool]:
    merged: Dict[str, str] = {}
    changed = False
    for raw_key, raw_value in (labels or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            changed = True
            continue
        value = str(raw_value or "").strip()
        if not value:
            changed = True
            continue
        if merged.get(key) != value:
            merged[key] = value
    # Seed any missing required keys with defaults to prevent surface blockers
    for key in REQUIRED_STRICT_SURFACE_LABEL_KEYS:
        if key not in merged:
            default_value = STRICT_SURFACE_LABEL_DEFAULTS.get(key, key)
            merged[key] = default_value
            changed = True
    return merged, changed


def ensure_welcome_messaging_pack(messaging: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    merged: Dict[str, Any] = dict(messaging or {})
    changed = False

    trust_names = merged.get("trust_names")
    if not isinstance(trust_names, list) or len([n for n in trust_names if str(n).strip()]) < 4:
        merged["trust_names"] = list(WELCOME_MESSAGING_DEFAULTS["trust_names"])
        changed = True

    testimonials_raw = merged.get("welcome_testimonials")
    valid_testimonials: List[Dict[str, Any]] = []
    if isinstance(testimonials_raw, list):
        for raw in testimonials_raw:
            if not isinstance(raw, dict):
                continue
            quote = str(raw.get("quote") or raw.get("text") or "").strip()
            name = str(raw.get("name") or "").strip()
            role = str(raw.get("role") or "").strip()
            company = str(raw.get("company") or "").strip()
            if not quote or not name:
                continue
            rating_raw = raw.get("rating")
            try:
                rating = int(rating_raw if rating_raw is not None else 5)
            except Exception:
                rating = 5
            rating = max(1, min(5, rating))
            valid_testimonials.append(
                {
                    "name": name,
                    "role": role,
                    "company": company,
                    "quote": quote,
                    "rating": rating,
                    "outcome": str(raw.get("outcome") or "Improved team consistency and execution quality").strip(),
                    "segment": str(raw.get("segment") or raw.get("persona") or role or "General").strip(),
                    "seeded": True,
                }
            )
    # Frontend requires minimum 10 testimonials for welcome page
    if len(valid_testimonials) < 10:
        merged["welcome_testimonials"] = list(WELCOME_MESSAGING_DEFAULTS["welcome_testimonials"])
        changed = True
    else:
        trimmed = valid_testimonials[:12]
        if trimmed != testimonials_raw:
            merged["welcome_testimonials"] = trimmed
            changed = True

    activities_raw = merged.get("welcome_activities")
    valid_activities: List[Dict[str, str]] = []
    if isinstance(activities_raw, list):
        for raw in activities_raw:
            if not isinstance(raw, dict):
                continue
            user = str(raw.get("user") or "").strip()
            action = str(raw.get("action") or "").strip()
            if not user or not action:
                continue
            valid_activities.append(
                {
                    "user": user,
                    "action": action,
                    "time": str(raw.get("time") or "").strip() or "now",
                    "icon": str(raw.get("icon") or "chatbubble").strip() or "chatbubble",
                    "color": str(raw.get("color") or "#14B8A6").strip() or "#14B8A6",
                    "seeded": True,
                }
            )
    if len(valid_activities) < 4:
        merged["welcome_activities"] = list(WELCOME_MESSAGING_DEFAULTS["welcome_activities"])
        changed = True
    else:
        trimmed_activities = valid_activities[:8]
        if trimmed_activities != activities_raw:
            merged["welcome_activities"] = trimmed_activities
            changed = True

    merged.setdefault("announcements", [])

    quick_raw = merged.get("quick_questions")
    valid_quick = (
        [str(q).strip() for q in quick_raw if isinstance(q, str) and str(q).strip()]
        if isinstance(quick_raw, list)
        else []
    )
    if len(valid_quick) < 1:
        merged["quick_questions"] = list(WELCOME_MESSAGING_DEFAULTS["quick_questions"])
        changed = True
    elif valid_quick != quick_raw:
        merged["quick_questions"] = valid_quick
        changed = True

    return merged, changed