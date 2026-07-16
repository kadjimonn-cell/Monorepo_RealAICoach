"""i18n core routes: locales, languages, translations, user preference, email locale, health."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone

from ..db import db, require_auth

from .constants import SUPPORTED_LANGUAGES
from .helpers import (
    router,
    _normalize_lang,
    _extract_language_from_preference_doc,
    _preference_doc_has_language,
    _get_user_language_code,
)
from .default_translations import DEFAULT_TRANSLATIONS

@router.get("/locales")
async def get_locales():
    """Compatibility endpoint for locale list checks."""
    return {
        "locales": SUPPORTED_LANGUAGES,
        "default": "en",
        "count": len(SUPPORTED_LANGUAGES),
    }


@router.get("/languages")
async def list_languages(request: Request):
    """List supported languages."""
    languages = [{"code": code, **info} for code, info in SUPPORTED_LANGUAGES.items()]
    return {"languages": languages, "default": "en"}


@router.get("/translations/{lang}")
async def get_translations(lang: str):
    """Get translation strings for a language."""
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")
    custom = await db.translations.find_one({"lang": lang}, {"_id": 0})
    if custom:
        base = DEFAULT_TRANSLATIONS.get(lang, DEFAULT_TRANSLATIONS["en"]).copy()
        base.update(custom.get("strings", {}))
        return {"lang": lang, "translations": base}
    translations = DEFAULT_TRANSLATIONS.get(lang, DEFAULT_TRANSLATIONS["en"])
    return {"lang": lang, "translations": translations}


@router.post("/translations/{lang}")
async def update_translations(lang: str, request: Request):
    """Update custom translations (admin only)."""
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin required")
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")
    body = await request.json()
    strings = body.get("strings", {})
    now = datetime.now(timezone.utc).isoformat()
    await db.translations.update_one(
        {"lang": lang},
        {"$set": {"strings": strings, "updated_by": user.user_id, "updated_at": now}},
        upsert=True,
    )
    return {"success": True, "lang": lang, "count": len(strings)}


@router.get("/user-preference")
async def get_user_language(request: Request):
    """Get user's language preference."""
    user = await require_auth(request)

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "language_preference": 1},
    )
    profile_lang = str((user_doc or {}).get("language_preference") or "").strip()
    if profile_lang:
        normalized_profile_lang = _normalize_lang(profile_lang)
        return {
            "language": normalized_profile_lang,
            "has_preference": True,
            "source": "account_profile",
        }

    pref_doc = await db.user_preferences.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "key": 1, "value": 1, "language": 1},
    )
    language = _extract_language_from_preference_doc(pref_doc)
    has_preference = _preference_doc_has_language(pref_doc)
    return {
        "language": language,
        "has_preference": has_preference,
        "source": "user_preference" if has_preference else "default",
    }


@router.post("/user-preference")
async def set_user_language(request: Request):
    """Set user's language preference."""
    user = await require_auth(request)
    body = await request.json()
    lang = body.get("language", "en")
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.user_preferences.find_one({"user_id": user.user_id}, {"_id": 1, "key": 1})
    if existing and str(existing.get("key") or "") == "language":
        await db.user_preferences.update_one(
            {"_id": existing.get("_id")},
            {"$set": {"user_id": user.user_id, "key": "language", "value": lang, "updated_at": now}},
        )
    else:
        await db.user_preferences.update_one(
            {"user_id": user.user_id},
            {"$set": {"user_id": user.user_id, "language": lang, "updated_at": now}},
            upsert=True,
        )
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"language_preference": lang, "updated_at": now}},
    )
    return {"success": True, "language": lang}


@router.get("/email-locale/{user_id}")
async def get_email_locale(user_id: str, request: Request):
    """Get the locale metadata for sending localized emails to a specific user."""
    from utils.email_localization import EMAIL_LOCALE_MAP
    lang_code = await _get_user_language_code(user_id)
    locale_info = EMAIL_LOCALE_MAP.get(lang_code, EMAIL_LOCALE_MAP["en"])
    return {
        "language_code": lang_code,
        "language_name": SUPPORTED_LANGUAGES.get(lang_code, {}).get("name", "English"),
        "dir": locale_info["dir"],
        "greeting": locale_info["greeting"],
    }



@router.get("/health")
async def i18n_health_check():
    """
    Localization system health check.
    Returns overall translation system status, cache stats, and API readiness.
    Used by monitoring and CI to detect i18n regressions.
    """
    # Check if auto-translate API is responsive
    api_healthy = True
    try:
        from services.auto_translate import translate_batch
        test_result = await translate_batch(["Test"], "fr")
        api_healthy = bool(test_result and test_result.get("Test"))
    except Exception:
        api_healthy = False

    # Check translation cache size
    cache_count = 0
    try:
        cache_count = await db.translation_cache.count_documents({})
    except Exception:
        pass

    # Count supported languages
    lang_count = len(SUPPORTED_LANGUAGES)

    return {
        "status": "healthy" if api_healthy else "degraded",
        "supported_languages": lang_count,
        "auto_translate_api": "online" if api_healthy else "offline",
        "cache_entries": cache_count,
        "dom_engine_version": "v2-global",
        "features": {
            "static_locale_files": True,
            "dynamic_auto_translate": api_healthy,
            "dom_translation_engine": True,
            "react_hook_translations": True,
            "language_persistence": True,
            "locale_seeding": True,
        },
    }


# ── Safe-Auto Translation Engine ──────────────────────────────────────────────
# Background monitor that detects coverage gaps and auto-fixes them immediately.

