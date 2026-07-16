"""i18n coverage: translation coverage reports, trends, fallback tracking."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone

from ..db import db

from .constants import SUPPORTED_LANGUAGES
from .helpers import router, _normalize_lang

async def _track_translation_fallback_events(events: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    day_bucket = now.date().isoformat()
    tracked = 0

    for body in events:
        language = _normalize_lang(str((body or {}).get("language") or "en"))
        key = str((body or {}).get("key") or "").strip()[:160]
        route = str((body or {}).get("route") or "unknown").strip()[:200]
        source = str((body or {}).get("source") or "runtime_fallback").strip()[:80]
        if language == "en" or not key:
            continue

        await db.translation_fallback_hits.update_one(
            {
                "day_bucket": day_bucket,
                "language": language,
                "key": key,
                "route": route,
            },
            {
                "$inc": {"hits": 1},
                "$set": {"last_hit_at": created_at, "source": source},
                "$setOnInsert": {
                    "day_bucket": day_bucket,
                    "language": language,
                    "key": key,
                    "route": route,
                    "created_at": created_at,
                },
            },
            upsert=True,
        )
        tracked += 1

    return {"success": True, "tracked": tracked > 0, "tracked_count": tracked}


@router.post("/fallback-hit")
async def track_translation_fallback_hit(request: Request):
    """Track a runtime translation fallback hit for language quality analytics."""
    body = await request.json()
    return await _track_translation_fallback_events([body])


@router.post("/fallback-hit/batch")
async def track_translation_fallback_hit_batch(request: Request):
    """Batch track runtime translation fallback hits to reduce frontend request chatter."""
    body = await request.json()
    events = body.get("hits") if isinstance(body, dict) else None
    if not isinstance(events, list):
        return {"success": True, "tracked": False, "tracked_count": 0}
    trimmed_events = [event for event in events[:50] if isinstance(event, dict)]
    return await _track_translation_fallback_events(trimmed_events)


@router.get("/coverage")
async def get_translation_coverage(request: Request):
    """Analyze frontend translation coverage across all languages and pages."""
    import re
    import os

    locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "frontend", "src", "i18n", "locales")
    if not os.path.exists(locales_dir):
        raise HTTPException(status_code=404, detail="locale files folder not found")

    lang_keys: dict[str, set[str]] = {}
    inherits_english: set[str] = set()
    for fn in os.listdir(locales_dir):
        if not fn.endswith(".ts"):
            continue
        lang = fn.replace(".ts", "")
        fp = os.path.join(locales_dir, fn)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        keys = set(re.findall(r'^\s*"([a-zA-Z][a-zA-Z0-9_.]+)":', content, flags=re.MULTILINE))
        lang_keys[lang] = keys
        if re.search(r"\.\.\.en\b", content):
            inherits_english.add(lang)

    en_keys = lang_keys.get("en", set())
    if not en_keys:
        return {"error": "No English keys found"}

    for lang in inherits_english:
        if lang != "en":
            lang_keys[lang] = set(lang_keys.get(lang, set())) | set(en_keys)

    # Group keys by page/component prefix
    PAGE_MAP = {
        "home.hero": "Home Hero",
        "home.charts": "Home Charts",
        "home.features": "Home Features",
        "home.social": "Home Social Proof",
        "home.cta": "Home CTA",
        "home.checklist": "Home Checklist",
        "home.trophy": "Home Trophy Case",
        "home.dashboard": "Home Dashboard",
        "home.greeting": "Home Greetings",
        "about": "About Page",
        "achievements": "Achievements Page",
        "pricing": "Pricing Page",
        "notifications": "Notifications Page",
        "nav": "Navigation",
        "common": "Common/Shared",
        "auth": "Authentication",
        "footer": "Footer",
        "settings": "Settings",
        "interview": "Interview",
        "docs": "Documents",
        "team": "Teams",
        "integ": "Integrations",
        "onboard": "Onboarding",
        "analytics": "Analytics",
        "help": "Help Page",
        "banner": "Banners",
    }

    def get_page(key: str) -> str:
        # Try longest prefix match first
        parts = key.split(".")
        for length in range(min(3, len(parts)), 0, -1):
            prefix = ".".join(parts[:length])
            if prefix in PAGE_MAP:
                return PAGE_MAP[prefix]
        # Fallback to first segment
        first = parts[0]
        return PAGE_MAP.get(first, f"Other ({first})")

    # Build per-page key lists
    page_keys: dict[str, list[str]] = {}
    for key in sorted(en_keys):
        page = get_page(key)
        page_keys.setdefault(page, []).append(key)

    # Calculate coverage for each language
    languages_data = []
    for lang in sorted(lang_keys.keys()):
        if lang == "en":
            continue
        keys = lang_keys[lang]
        total = len(en_keys)
        translated = len(keys & en_keys)
        missing = sorted(en_keys - keys)

        # Per-page coverage
        pages = []
        for page_name, pkeys in sorted(page_keys.items()):
            page_total = len(pkeys)
            page_translated = len(set(pkeys) & keys)
            page_missing = sorted(set(pkeys) - keys)
            pct = round((page_translated / page_total * 100)) if page_total > 0 else 0
            pages.append({
                "name": page_name,
                "total": page_total,
                "translated": page_translated,
                "missing_count": page_total - page_translated,
                "coverage_pct": pct,
                "status": "complete" if pct == 100 else ("partial" if pct > 0 else "missing"),
                "missing_keys": page_missing[:5],  # First 5 missing keys as sample
            })

        lang_info = SUPPORTED_LANGUAGES.get(lang, {"name": lang})
        languages_data.append({
            "code": lang,
            "name": lang_info.get("name", lang),
            "total_keys": total,
            "translated_keys": translated,
            "missing_keys": len(missing),
            "coverage_pct": round((translated / total * 100)) if total > 0 else 0,
            "pages": pages,
        })

    # Overall stats
    total_en_keys = len(en_keys)
    total_pages = len(page_keys)
    avg_coverage = round(sum(lang_item["coverage_pct"] for lang_item in languages_data) / len(languages_data)) if languages_data else 0

    return {
        "total_keys": total_en_keys,
        "total_pages": total_pages,
        "total_languages": len(languages_data),
        "avg_coverage": avg_coverage,
        "pages_summary": [{"name": k, "key_count": len(v)} for k, v in sorted(page_keys.items())],
        "languages": languages_data,
    }


@router.get("/coverage-v2")
async def get_translation_coverage_v2(request: Request):
    return await get_translation_coverage(request)


@router.get("/coverage/trend")
async def get_coverage_trend():
    """Return historical coverage snapshots for trend charts."""
    snapshots = await db.translation_coverage_snapshots.find(
        {}, sort=[("timestamp", -1)], projection={"_id": 0}
    ).to_list(90)  # Last 90 data points
    snapshots.reverse()
    return {"snapshots": snapshots}


@router.get("/coverage/api-data")
async def get_api_data_coverage():
    """Check coverage of API-sourced dynamic strings (chart labels, activity text, etc.)."""
    from .home_dashboard import (
        _CATEGORY_TRANSLATIONS,
        _ACTIVITY_TRANSLATIONS,
        _CHECKLIST_TRANSLATIONS,
        _DAY_TRANSLATIONS,
    )

    def _coverage_for_table(table: dict, label: str) -> dict:
        all_langs: set[str] = set()
        for entry in table.values():
            all_langs.update(entry.keys())
        total_cells = len(table) * len(all_langs) if all_langs else 0
        filled = sum(len(v) for v in table.values())
        pct = round(filled / total_cells * 100) if total_cells else 100
        return {
            "label": label,
            "strings": len(table),
            "languages": len(all_langs),
            "filled": filled,
            "total_cells": total_cells,
            "coverage_pct": pct,
        }

    tables = [
        _coverage_for_table(_CATEGORY_TRANSLATIONS, "Chart Categories"),
        _coverage_for_table(_ACTIVITY_TRANSLATIONS, "Activity Feed"),
        _coverage_for_table(_CHECKLIST_TRANSLATIONS, "Onboarding Checklist"),
        _coverage_for_table(_DAY_TRANSLATIONS, "Day Labels"),
    ]

    overall = round(sum(t["coverage_pct"] for t in tables) / len(tables)) if tables else 100

    # DOM engine cache stats
    dom_cache_count = await db.translation_cache.count_documents({})
    dom_langs = await db.translation_cache.distinct("lang")

    return {
        "api_tables": tables,
        "api_overall_pct": overall,
        "dom_engine": {
            "version": "v2-global",
            "scope": "all-routes",
            "cache_entries": dom_cache_count,
            "cached_languages": len(dom_langs),
            "mode": "adaptive",
            "public_debounce_ms": 70,
            "auth_debounce_ms": 120,
        },
    }
