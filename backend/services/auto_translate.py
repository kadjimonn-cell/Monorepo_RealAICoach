"""
On-demand text translation service with MongoDB caching.
Translates any UI string to any supported language, caches results permanently.
LOCKED: Brand names are permanently protected from translation.
"""

import logging
import os
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from utils.brand_protection import protect_brands, restore_brands, enforce_protected_brands, scan_brand_violations, ai_validate_brand_integrity, build_brand_audit_record

logger = logging.getLogger("services.auto_translate")

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


def _safe_batch_chunk_size() -> int:
    raw = os.environ.get("AUTO_TRANSLATE_BATCH_CHUNK_SIZE")
    try:
        parsed = int(str(raw).strip()) if raw is not None else 10
    except Exception:
        parsed = 30
    return max(10, min(parsed, 250))

_db = None

UNRESOLVED_BRAND_TOKEN_PATTERN = re.compile(r"\{\{\s*BRAND(?:_\d+)?\s*\}\}")
EXACT_TRANSLATION_OVERRIDES = {
    "fr": {
        "Reach Out": "Nous contacter",
        "Contact Support": "Contacter le support",
        "Need help?": "Besoin d’aide ?",
    }
}
HTML_LOCK_TOKEN_PREFIX = "__EMAIL_LOCKED_REGION_"
FOOTER_LOGO_TOKEN_PATTERN = re.compile(r"^\s*in\s*$", re.IGNORECASE)


def _normalize_target_lang(target_lang: str) -> str:
    raw = (target_lang or "en").strip().lower()
    return raw if len(raw) <= 3 else raw[:2]


def _get_exact_translation_override(text: str, target_lang: str) -> str | None:
    return EXACT_TRANSLATION_OVERRIDES.get(_normalize_target_lang(target_lang), {}).get(text)


def _has_unresolved_brand_tokens(text: str) -> bool:
    return bool(UNRESOLVED_BRAND_TOKEN_PATTERN.search(str(text or "")))


async def _finalize_translation(source_text: str, candidate_text: str, target_lang: str, brand_map: dict[str, str] | None = None) -> str:
    override = _get_exact_translation_override(source_text, target_lang)
    if override is not None:
        return override

    translated = str(candidate_text or source_text)
    if brand_map:
        translated = restore_brands(translated, brand_map)
        if scan_brand_violations(source_text, translated):
            ai_result = await ai_validate_brand_integrity(source_text, translated, target_lang)
            translated = ai_result.get("corrected_text", translated)
            db = await _get_db()
            await db.brand_protection_audit.insert_one(
                build_brand_audit_record(
                    source_text,
                    translated,
                    target_lang,
                    ai_result.get("status", "corrected"),
                    ai_result.get("violations", []),
                )
            )
        translated = enforce_protected_brands(source_text, translated)

    if _has_unresolved_brand_tokens(translated):
        return source_text

    return translated


def _protect_html_regions(html: str) -> tuple[str, dict[str, str]]:
    protected_regions: dict[str, str] = {}
    region_index = 0
    patterns = [
        re.compile(r"<!--.*?-->", re.IGNORECASE | re.DOTALL),
        re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL),
        re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
        re.compile(
            r"<(?P<tag>[a-z0-9]+)(?=[^>]*(?:translate=['\"]no['\"]|data-notranslate=['\"]true['\"]|class=['\"][^'\"]*\bnotranslate\b[^'\"]*['\"]))[^>]*>.*?</(?P=tag)>",
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    def _stash(match: re.Match) -> str:
        nonlocal region_index
        token = f"{HTML_LOCK_TOKEN_PREFIX}{region_index}__"
        protected_regions[token] = match.group(0)
        region_index += 1
        return token

    protected_html = html
    for pattern in patterns:
        protected_html = pattern.sub(_stash, protected_html)
    return protected_html, protected_regions


def _restore_html_regions(html: str, protected_regions: dict[str, str]) -> str:
    restored_html = html
    for token, raw_html in protected_regions.items():
        restored_html = restored_html.replace(token, raw_html)
    return restored_html


def _is_translatable_html_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or stripped.startswith(HTML_LOCK_TOKEN_PREFIX):
        return False

    visible = re.sub(r"&[a-zA-Z0-9#]+;", " ", stripped)
    visible = re.sub(r"\s+", " ", visible).strip()
    return len(visible) >= 2 and bool(re.search(r"\w", visible, re.UNICODE))

async def _get_db():
    global _db
    if _db is None:
        client = AsyncIOMotorClient(MONGO_URL)
        _db = client[DB_NAME]
        await _db.translation_cache.create_index(
            [("lang", 1), ("hash", 1)], unique=True, background=True
        )
    return _db


def _hash_text(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


async def get_cached_translation(lang: str, text: str) -> str | None:
    """Check MongoDB cache for a translation."""
    db = await _get_db()
    doc = await db.translation_cache.find_one(
        {"lang": lang, "hash": _hash_text(text)},
        {"_id": 0, "translated": 1},
    )
    if not doc:
        return None

    translated = str(doc.get("translated") or "")
    if not translated:
        return None
    if _has_unresolved_brand_tokens(translated):
        return None
    if scan_brand_violations(text, translated):
        return None
    return translated


async def get_cached_translations_bulk(lang: str, texts: list[str]) -> dict[str, str]:
    """Bulk cache lookup: one $in query for all texts. Same validation as get_cached_translation."""
    db = await _get_db()
    hash_to_texts: dict[str, list[str]] = {}
    for text in texts:
        hash_to_texts.setdefault(_hash_text(text), []).append(text)
    if not hash_to_texts:
        return {}
    cursor = db.translation_cache.find(
        {"lang": lang, "hash": {"$in": list(hash_to_texts.keys())}},
        {"_id": 0, "hash": 1, "translated": 1},
    )
    hits: dict[str, str] = {}
    async for doc in cursor:
        translated = str(doc.get("translated") or "")
        if not translated or _has_unresolved_brand_tokens(translated):
            continue
        for text in hash_to_texts.get(str(doc.get("hash") or ""), []):
            if scan_brand_violations(text, translated):
                continue
            hits[text] = translated
    return hits


async def cache_translations_bulk(lang: str, pairs: dict[str, str]):
    """Bulk upsert translations into MongoDB cache."""
    if not pairs:
        return
    db = await _get_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    ops = [
        UpdateOne(
            {"lang": lang, "hash": _hash_text(text)},
            {"$set": {
                "lang": lang,
                "hash": _hash_text(text),
                "original": text,
                "translated": translated,
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        for text, translated in pairs.items()
    ]
    await db.translation_cache.bulk_write(ops, ordered=False)


async def cache_translation(lang: str, text: str, translated: str):
    """Store a translation in MongoDB cache."""
    db = await _get_db()
    await db.translation_cache.update_one(
        {"lang": lang, "hash": _hash_text(text)},
        {
            "$set": {
                "lang": lang,
                "hash": _hash_text(text),
                "original": text,
                "translated": translated,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )


async def purge_invalid_translation_cache(lang: str | None = None, limit: int = 5000) -> dict:
    """Remove cached translations that contain leaked placeholders or protected-brand corruption."""
    db = await _get_db()
    query = {}
    if lang:
        query["lang"] = _normalize_target_lang(lang)

    rows = await db.translation_cache.find(
        query,
        {"original": 1, "translated": 1, "lang": 1},
    ).to_list(limit)

    invalid_ids = []
    invalid_samples = []
    for row in rows:
        original = str(row.get("original") or "")
        translated = str(row.get("translated") or "")
        has_invalid_placeholder = _has_unresolved_brand_tokens(translated)
        has_brand_violation = bool(scan_brand_violations(original, translated)) if original and translated else False
        if not translated or has_invalid_placeholder or has_brand_violation:
            invalid_ids.append(row.get("_id"))
            if len(invalid_samples) < 20:
                invalid_samples.append(
                    {
                        "lang": row.get("lang"),
                        "original": original[:160],
                        "translated": translated[:160],
                        "reason": "placeholder_leak" if has_invalid_placeholder else "brand_violation" if has_brand_violation else "empty_translation",
                    }
                )

    deleted_count = 0
    if invalid_ids:
        result = await db.translation_cache.delete_many({"_id": {"$in": invalid_ids}})
        deleted_count = int(result.deleted_count or 0)

    logo_query: dict = {"original": {"$regex": FOOTER_LOGO_TOKEN_PATTERN.pattern, "$options": "i"}}
    if lang:
        logo_query["lang"] = _normalize_target_lang(lang)
    logo_token_cache_deleted = int((await db.translation_cache.delete_many(logo_query)).deleted_count or 0)

    return {
        "lang": query.get("lang") or "all",
        "scanned": len(rows),
        "deleted": deleted_count + logo_token_cache_deleted,
        "deleted_invalid": deleted_count,
        "deleted_footer_logo_tokens": logo_token_cache_deleted,
        "invalid_samples": invalid_samples,
    }


async def translate_text(text: str, target_lang: str) -> str:
    """Translate a single text string. Returns cached version if available.
    LOCKED: Brand names are always preserved untranslated."""
    if not text or not text.strip():
        return text
    target_lang = _normalize_target_lang(target_lang)
    if target_lang == "en":
        return text

    override = _get_exact_translation_override(text, target_lang)
    if override is not None:
        return override

    # Check cache first
    cached = await get_cached_translation(target_lang, text)
    if cached:
        return cached

    # Protect brand names before LLM translation
    protected_text, brand_map = protect_brands(text)

    # Use LLM for translation
    try:
        import uuid as uuid_mod
        from utils.llm_helper import generate_verified_json

        LANG_NAMES = {
            "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
            "pt": "Portuguese", "zh": "Chinese (Simplified)", "ja": "Japanese",
            "ko": "Korean", "hi": "Hindi", "ar": "Arabic", "ru": "Russian",
            "tr": "Turkish", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
            "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
            "sw": "Swahili", "uk": "Ukrainian", "ro": "Romanian",
        }
        lang_name = LANG_NAMES.get(target_lang, target_lang)

        result = await generate_verified_json(
            system_message=f"You are a professional UI translator. Translate the given text to {lang_name}. Keep it concise and natural for a software interface. CRITICAL: Keep all {{{{BRAND}}}} placeholders exactly as they are. Do NOT translate or modify any {{{{BRANDn}}}} tokens. Return ONLY a JSON object.",
            prompt=f'Translate this UI text to {lang_name}: "{protected_text}"\n\nReturn: {{"translated": "..."}}',
            session_id=f"auto-tr-{uuid_mod.uuid4().hex[:8]}",
            model="gpt-4o-mini",
        )
        translated = await _finalize_translation(
            text,
            result.get("translated", text),
            target_lang,
            brand_map,
        )
        if translated and translated != text:
            await cache_translation(target_lang, text, translated)
            return translated
    except Exception as e:
        logger.warning(f"Translation failed for '{text[:40]}' -> {target_lang}: {e}")

    return text


async def translate_batch(texts: list[str], target_lang: str) -> dict[str, str]:
    """Translate multiple texts at once. Uses cache + LLM for uncached ones.
    LOCKED: Brand names are always preserved untranslated."""
    target_lang = _normalize_target_lang(target_lang)
    if target_lang == "en":
        return {t: t for t in texts}

    results = {}
    lookup_candidates = []

    for text in texts:
        if not text or not text.strip():
            results[text] = text
            continue
        override = _get_exact_translation_override(text, target_lang)
        if override is not None:
            results[text] = override
            continue
        lookup_candidates.append(text)

    # Bulk cache lookup: single $in query instead of one find_one per text
    cached_hits = await get_cached_translations_bulk(target_lang, lookup_candidates)
    results.update(cached_hits)
    uncached = [t for t in lookup_candidates if t not in cached_hits]

    if not uncached:
        return results

    # Batch translate uncached texts via LLM with brand protection.
    # Chunks are processed concurrently (bounded) instead of serially.
    try:
        import uuid as uuid_mod
        from utils.llm_helper import generate_verified_json

        LANG_NAMES = {
            "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
            "pt": "Portuguese", "zh": "Chinese (Simplified)", "ja": "Japanese",
            "ko": "Korean", "hi": "Hindi", "ar": "Arabic", "ru": "Russian",
            "tr": "Turkish", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
            "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
            "sw": "Swahili", "uk": "Ukrainian", "ro": "Romanian",
        }
        lang_name = LANG_NAMES.get(target_lang, target_lang)

        chunk_size = _safe_batch_chunk_size()
        chunks = [uncached[i : i + chunk_size] for i in range(0, len(uncached), chunk_size)]
        semaphore = asyncio.Semaphore(6)

        async def translate_chunk(chunk: list[str]) -> dict[str, str]:
            async with semaphore:
                brand_maps = {}
                protected_chunk = []
                for text in chunk:
                    protected, bmap = protect_brands(text)
                    protected_chunk.append(protected)
                    if bmap:
                        brand_maps[text] = bmap

                keyed_payload = {f"t{j}": protected_text for j, protected_text in enumerate(protected_chunk)}

                result = await generate_verified_json(
                    system_message=(
                        f"You are a professional UI translator. Translate ALL values in the given JSON object to {lang_name}. "
                        "Keep translations concise and natural. CRITICAL: Preserve every JSON key exactly as provided. "
                        "Never reorder, rename, drop, or invent keys. Keep all {{BRAND}} placeholders exactly as they are — "
                        "do NOT translate, modify, or remove any {{BRANDn}} tokens. Return ONLY a JSON object with the same keys and translated string values."
                    ),
                    prompt=(
                        f"Translate the values of this JSON object to {lang_name}.\n"
                        f"Input JSON:\n{json.dumps(keyed_payload, ensure_ascii=False)}"
                    ),
                    session_id=f"auto-tr-batch-{uuid_mod.uuid4().hex[:8]}",
                    model="gpt-4o-mini",
                )
                translated_payload = result.get("translations") if isinstance(result, dict) else None
                if not isinstance(translated_payload, dict):
                    translated_payload = result if isinstance(result, dict) else {}
                chunk_results: dict[str, str] = {}
                for j, text in enumerate(chunk):
                    response_key = f"t{j}"
                    tr = await _finalize_translation(
                        text,
                        translated_payload.get(response_key, text),
                        target_lang,
                        brand_maps.get(text),
                    )
                    chunk_results[text] = tr
                return chunk_results

        chunk_outputs = await asyncio.gather(*(translate_chunk(c) for c in chunks), return_exceptions=True)
        to_cache: dict[str, str] = {}
        for output in chunk_outputs:
            if isinstance(output, Exception):
                logger.warning(f"Batch translation chunk failed: {output}")
                continue
            for text, tr in output.items():
                results[text] = tr
                if tr and tr != text:
                    to_cache[text] = tr
        if to_cache:
            await cache_translations_bulk(target_lang, to_cache)
        for text in uncached:
            if text not in results:
                results[text] = text
    except Exception as e:
        logger.warning(f"Batch translation failed: {e}")
        for text in uncached:
            if text not in results:
                results[text] = text

    return results



async def translate_email_html(html: str, subject: str, target_lang: str) -> tuple[str, str]:
    """Translate an email's subject and HTML body.

    Uses the LLM to translate the full HTML in one pass (preserving structure)
    and the subject as a simple string.

    Returns (translated_subject, translated_html).
    """
    if target_lang in ("en", "English", "", None):
        return subject, html

    # Normalise lang code
    lang_code = _normalize_target_lang(target_lang)

    # Translate subject
    translated_subject = subject
    try:
        subj_result = await translate_batch([subject], lang_code)
        translated_subject = subj_result.get(subject, subject)
    except Exception:
        pass

    # Translate HTML body (extract visible text, translate, re-inject)
    translated_html = html
    try:
        protected_html, protected_regions = _protect_html_regions(html)
        # Extract text between > and < (visible text in HTML)
        text_segments = re.findall(r'>([^<>]+)<', protected_html)
        # Filter out segments that are just whitespace or HTML entities
        visible_texts = [
            t.strip()
            for t in text_segments
            if _is_translatable_html_text(t)
        ]
        # Remove duplicates while preserving order
        seen = set()
        unique_texts = []
        for t in visible_texts:
            if t not in seen:
                seen.add(t)
                unique_texts.append(t)

        if unique_texts:
            translations = await translate_batch(unique_texts, lang_code)
            # Replace in HTML (original text only, preserving HTML structure)
            translated_html = protected_html
            for original, translated in translations.items():
                if translated != original and len(original) >= 2:
                    pattern = re.compile(
                        rf">(\s*){re.escape(original)}(\s*)<",
                        re.UNICODE,
                    )
                    translated_html = pattern.sub(
                        lambda match: f">{match.group(1)}{translated}{match.group(2)}<",
                        translated_html,
                    )
            translated_html = _restore_html_regions(translated_html, protected_regions)
    except Exception as e:
        logger.warning(f"Email HTML translation failed: {e}")

    return translated_subject, translated_html


async def get_user_language(user_id: str) -> str:
    """Get a user's preferred language code from their profile."""
    try:
        db = await _get_db()
        # Check user_preferences collection first (set by language selector)
        pref = await db.user_preferences.find_one(
            {"user_id": user_id, "key": "language"},
            {"_id": 0, "value": 1},
        )
        if pref and pref.get("value") and pref["value"] != "en":
            return pref["value"]

        # Fallback: check user's theme_preference in users collection
        user = await db.users.find_one(
            {"user_id": user_id},
            {"_id": 0, "theme_preference": 1},
        )
        if user:
            theme = user.get("theme_preference", {})
            if isinstance(theme, dict) and theme.get("language"):
                lang_name = theme["language"]
                code_map = {
                    "French": "fr", "Spanish": "es", "German": "de",
                    "Italian": "it", "Portuguese": "pt", "Chinese": "zh",
                    "Japanese": "ja", "Korean": "ko", "Hindi": "hi",
                    "Arabic": "ar", "Russian": "ru", "Turkish": "tr",
                    "Dutch": "nl", "Swedish": "sv", "Polish": "pl",
                    "Thai": "th", "Vietnamese": "vi", "Indonesian": "id",
                    "Malay": "ms", "Swahili": "sw", "Ukrainian": "uk",
                    "Romanian": "ro", "English": "en",
                }
                return code_map.get(lang_name, "en")
    except Exception as e:
        logger.warning(f"Failed to get user language: {e}")
    return "en"
