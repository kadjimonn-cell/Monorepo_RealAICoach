"""i18n auto-translate: batch translate, jobs, pre-warm cache, safe-auto."""

from fastapi import HTTPException, Request, BackgroundTasks
from datetime import datetime, timezone
import hashlib

from ..db import db, require_auth

from .constants import SUPPORTED_LANGUAGES
from .helpers import (
    router,
    logger,
    _parse_locale_content,
    _i18n_locale_file_path,
    _load_all_locale_maps,
    _write_locale_updates,
)

_AUTO_TRANSLATE_BURST_CACHE: dict[str, dict] = {}
_AUTO_TRANSLATE_BURST_WINDOW_SEC = 3.0
_AUTO_TRANSLATE_BURST_TTL_SEC = 30
_AUTO_TRANSLATE_BURST_MAX_KEYS = 500

def _auto_translate_cache_key(request: Request, lang: str, texts: list[str]) -> str:
    client_ip = ""
    try:
        client_ip = str((request.client.host if request.client else "") or "")
    except Exception:
        client_ip = ""
    normalized_texts = [str(t or "").strip() for t in texts[:100]]
    payload = f"{client_ip}|{lang}|" + "\u241f".join(normalized_texts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _prune_auto_translate_burst_cache(now_ts: float) -> None:
    stale_keys = [
        key
        for key, item in _AUTO_TRANSLATE_BURST_CACHE.items()
        if now_ts - float(item.get("ts") or 0) > _AUTO_TRANSLATE_BURST_TTL_SEC
    ]
    for key in stale_keys:
        _AUTO_TRANSLATE_BURST_CACHE.pop(key, None)

    if len(_AUTO_TRANSLATE_BURST_CACHE) <= _AUTO_TRANSLATE_BURST_MAX_KEYS:
        return

    ordered = sorted(_AUTO_TRANSLATE_BURST_CACHE.items(), key=lambda kv: float(kv[1].get("ts") or 0))
    overflow = len(_AUTO_TRANSLATE_BURST_CACHE) - _AUTO_TRANSLATE_BURST_MAX_KEYS
    for idx in range(max(0, overflow)):
        _AUTO_TRANSLATE_BURST_CACHE.pop(ordered[idx][0], None)


@router.post("/auto-translate")
async def auto_translate_batch(request: Request):
    """
    Batch translate UI strings on-demand with caching.
    Body: { "texts": ["Hello", "Support Center", ...], "lang": "fr" }
    Returns: { "translations": {"Hello": "Bonjour", ...} }
    """
    body = await request.json()
    texts = body.get("texts", [])
    lang = body.get("lang", "en")

    if not texts or lang == "en":
        return {"translations": {t: t for t in texts}}

    if lang not in SUPPORTED_LANGUAGES:
        return {"translations": {t: t for t in texts}}

    # Limit batch size
    texts = texts[:100]

    now_ts = datetime.now(timezone.utc).timestamp()
    _prune_auto_translate_burst_cache(now_ts)
    cache_key = _auto_translate_cache_key(request, lang, texts)
    cached_entry = _AUTO_TRANSLATE_BURST_CACHE.get(cache_key)
    if cached_entry and now_ts - float(cached_entry.get("ts") or 0) <= _AUTO_TRANSLATE_BURST_WINDOW_SEC:
        cached_payload = cached_entry.get("translations") or {}
        return {"translations": cached_payload, "deduped": True}

    try:
        from services.auto_translate import translate_batch
        result = await translate_batch(texts, lang)
        _AUTO_TRANSLATE_BURST_CACHE[cache_key] = {"ts": now_ts, "translations": result}
        return {"translations": result}
    except Exception as e:
        logger.error(f"Auto-translate batch failed: {e}")
        return {"translations": {t: t for t in texts}}


_PREWARM_ALLOWED_LANGS = {"fr", "es", "de", "it", "pt", "zh", "ja", "ko", "hi", "ar", "ru", "tr", "nl", "sv", "pl", "th", "vi", "id", "ms", "sw", "uk", "ro"}


def _collect_prewarm_candidates(lang: str) -> list[str]:
    """English seed values whose locale entry still equals the English source (fall back to auto-translate at runtime)."""
    en = _parse_locale_content(open(_i18n_locale_file_path("en"), encoding="utf-8").read())
    loc = _parse_locale_content(open(_i18n_locale_file_path(lang), encoding="utf-8").read())
    return sorted({v for k, v in en.items() if loc.get(k, "") == v and v.strip()})


async def _run_prewarm_sweep(run_id: str, langs: list[str]):
    from services.auto_translate import translate_batch, get_cached_translations_bulk
    for lang in langs:
        started = datetime.now(timezone.utc).isoformat()
        try:
            candidates = _collect_prewarm_candidates(lang)
            cached = await get_cached_translations_bulk(lang, candidates)
            to_warm = [t for t in candidates if t not in cached]
            result = await translate_batch(to_warm, lang)
            warmed = sum(1 for k, v in result.items() if v != k)
            # Cache identity results too (numbers, prices, code snippets the LLM
            # correctly leaves unchanged) so they are never re-attempted.
            identity = {k: v for k, v in result.items() if v == k and k.strip()}
            if identity:
                from services.auto_translate import cache_translations_bulk
                await cache_translations_bulk(lang, identity)
            await db.i18n_prewarm_runs.update_one(
                {"run_id": run_id},
                {"$set": {f"langs.{lang}": {
                    "status": "done", "started_at": started,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "candidates": len(candidates), "already_cached": len(cached),
                    "attempted": len(to_warm), "warmed": warmed,
                }}},
            )
        except Exception as e:
            logger.error(f"Pre-warm sweep failed for {lang}: {e}")
            await db.i18n_prewarm_runs.update_one(
                {"run_id": run_id},
                {"$set": {f"langs.{lang}": {"status": "failed", "error": str(e)[:200], "started_at": started}}},
            )
    await db.i18n_prewarm_runs.update_one(
        {"run_id": run_id},
        {"$set": {"status": "done", "finished_at": datetime.now(timezone.utc).isoformat()}},
    )


@router.post("/pre-warm-cache")
async def pre_warm_translation_cache(request: Request, background_tasks: BackgroundTasks):
    """Admin-only: pre-warm the auto-translate cache for the given languages (background sweep)."""
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin required")
    body = await request.json()
    langs = [str(l).strip().lower() for l in (body.get("langs") or ["fr", "es", "de"])]
    invalid = [l for l in langs if l not in _PREWARM_ALLOWED_LANGS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported languages: {invalid}")

    running = await db.i18n_prewarm_runs.find_one({"status": "running"}, {"_id": 0, "run_id": 1})
    if running:
        raise HTTPException(status_code=409, detail=f"A pre-warm run is already in progress: {running['run_id']}")

    import uuid as uuid_mod
    run_id = f"prewarm-{uuid_mod.uuid4().hex[:10]}"
    preview = {}
    from services.auto_translate import get_cached_translations_bulk
    for lang in langs:
        candidates = _collect_prewarm_candidates(lang)
        cached = await get_cached_translations_bulk(lang, candidates)
        preview[lang] = {"candidates": len(candidates), "already_cached": len(cached), "to_warm": len(candidates) - len(cached)}

    await db.i18n_prewarm_runs.insert_one({
        "run_id": run_id, "status": "running", "langs": {},
        "requested_langs": langs, "preview": preview,
        "requested_by": getattr(user, "user_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    background_tasks.add_task(_run_prewarm_sweep, run_id, langs)
    return {"success": True, "run_id": run_id, "preview": preview}


@router.get("/pre-warm-cache/status")
async def pre_warm_cache_status(request: Request):
    """Admin-only: status of the latest pre-warm run."""
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin required")
    latest = await db.i18n_prewarm_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return {"latest_run": latest}


@router.post("/auto-translate/jobs")
async def auto_translate_missing_keys(request: Request, background_tasks: BackgroundTasks):
    """Queue async AI translation of missing keys. Returns immediately with a job ID."""
    import uuid as uuid_mod

    body = await request.json()
    target_langs = body.get("languages", [])
    job_id = str(uuid_mod.uuid4())[:12]

    # Store initial job status
    now = datetime.now(timezone.utc).isoformat()
    await db.translation_jobs.insert_one({
        "job_id": job_id,
        "status": "queued",
        "target_langs": target_langs,
        "created_at": now,
        "progress": 0,
        "results": {},
    })

    background_tasks.add_task(_run_auto_translate, job_id, target_langs)
    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "message": "Translation job queued. Poll /api/i18n/auto-translate/jobs/status/{job_id} for progress.",
    }


@router.get("/auto-translate/jobs/status/{job_id}")
async def auto_translate_status(job_id: str):
    """Check the status of an async auto-translate job."""
    doc = await db.translation_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc


async def _run_auto_translate(job_id: str, target_langs: list):
    """Background worker: translate all missing keys for specified languages."""
    import re
    import json as jsonlib
    import uuid as uuid_mod
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.db import db as _db, EMERGENT_LLM_KEY
    from utils.brand_protection import enforce_protected_brands, scan_brand_violations, build_brand_audit_record

    try:
        await _db.translation_jobs.update_one({"job_id": job_id}, {"$set": {"status": "running"}})

        lang_keys = _load_all_locale_maps()
        if not lang_keys.get("en"):
            await _db.translation_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"status": "error", "error": "en locale not found"}},
            )
            return

        en_keys = lang_keys.get("en", {})
        non_en = [lang_code for lang_code in lang_keys if lang_code != "en"]
        if target_langs:
            non_en = [lang_code for lang_code in target_langs if lang_code in lang_keys and lang_code != "en"]

        results = {}
        total_translated = 0
        total_langs = len(non_en)

        for lang_idx, lang in enumerate(non_en):
            existing = set(lang_keys[lang].keys())
            missing = {k: v for k, v in en_keys.items() if k not in existing}
            if not missing:
                results[lang] = {"translated": 0, "status": "already_complete"}
                await _db.translation_jobs.update_one({"job_id": job_id}, {"$set": {"progress": int((lang_idx + 1) / total_langs * 100), f"results.{lang}": results[lang]}})
                continue

            lang_name = SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang)
            all_translations = {}
            missing_items = list(missing.items())

            for batch_start in range(0, len(missing_items), 40):
                batch = missing_items[batch_start:batch_start + 40]
                keys_json = jsonlib.dumps({k: v for k, v in batch}, ensure_ascii=False)
                try:
                    chat = LlmChat(
                        api_key=EMERGENT_LLM_KEY,
                        session_id=f"i18n-bg-{lang}-{uuid_mod.uuid4().hex[:6]}",
                        system_message=f"""You are a professional translator. Translate JSON values from English to {lang_name}.
Return ONLY valid JSON. Keep {{placeholders}} and brand names unchanged. No markdown.""",
                    ).with_model("openai", "gpt-4o-mini")
                    response = await chat.send_message(UserMessage(text=f"Translate to {lang_name}:\n{keys_json}"))
                    text = str(response).strip()
                    if text.startswith("```"):
                        text = re.sub(r"^```(?:json)?\s*", "", text)
                        text = re.sub(r"\s*```$", "", text)
                    translated = jsonlib.loads(text)
                    sanitized_translated = {}
                    for k, v in translated.items():
                        source_value = dict(batch).get(k, "")
                        corrected_value = enforce_protected_brands(source_value, str(v))
                        if scan_brand_violations(source_value, str(v)):
                            await _db.brand_protection_audit.insert_one(build_brand_audit_record(source_value, corrected_value, lang, "background_auto_translate_corrected", scan_brand_violations(source_value, str(v))))
                        sanitized_translated[k] = corrected_value
                    translated = sanitized_translated
                    all_translations.update(translated)

                    # Store in glossary for translation memory
                    for k, v in translated.items():
                        await _db.translation_glossary.update_one(
                            {"key": k, "lang": lang},
                            {"$set": {"key": k, "lang": lang, "value": v, "source": "auto-translate", "updated_at": datetime.now(timezone.utc).isoformat()}},
                            upsert=True,
                        )
                except Exception as e:
                    logger.error(f"[auto-translate bg] {lang} batch {batch_start}: {e}")

            if all_translations:
                try:
                    applied_count = _write_locale_updates(lang, all_translations, append_missing=True)
                    if applied_count > 0:
                        lang_keys[lang].update(all_translations)
                except Exception as file_err:
                    logger.error(f"[auto-translate bg] failed writing locale file for {lang}: {file_err}")

            total_translated += len(all_translations)
            results[lang] = {"translated": len(all_translations), "total_missing": len(missing), "status": "success" if all_translations else "ai_error"}
            await _db.translation_jobs.update_one({"job_id": job_id}, {"$set": {"progress": int((lang_idx + 1) / total_langs * 100), f"results.{lang}": results[lang]}})

        await _db.translation_jobs.update_one({"job_id": job_id}, {"$set": {
            "status": "completed",
            "progress": 100,
            "total_translated": total_translated,
            "results": results,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }})
        logger.info(f"[auto-translate bg] Job {job_id} done: {total_translated} keys translated")

    except Exception as e:
        logger.error(f"[auto-translate bg] Job {job_id} failed: {e}")
        await _db.translation_jobs.update_one({"job_id": job_id}, {"$set": {"status": "error", "error": str(e)}})



_SAFE_AUTO_RUNNING = False
_SAFE_AUTO_LAST_RUN = None
_SAFE_AUTO_FIXES = 0


@router.get("/safe-auto/status")
async def safe_auto_status():
    """Return the current Safe-Auto engine status and recent fixes."""
    last_snapshot = await db.translation_coverage_snapshots.find_one(
        {}, sort=[("timestamp", -1)], projection={"_id": 0}
    )
    recent_fixes = await db.safe_auto_fixes.find(
        {}, sort=[("timestamp", -1)], projection={"_id": 0}
    ).to_list(20)

    return {
        "engine_active": True,
        "mode": "real-time",
        "last_scan": _SAFE_AUTO_LAST_RUN,
        "total_auto_fixes": _SAFE_AUTO_FIXES,
        "last_snapshot": last_snapshot,
        "recent_fixes": recent_fixes,
    }


@router.post("/safe-auto/run")
async def safe_auto_run_now(request: Request):
    """Manually trigger a Safe-Auto scan and fix cycle."""
    global _SAFE_AUTO_LAST_RUN, _SAFE_AUTO_FIXES
    import os
    import re

    locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "frontend", "src", "i18n", "locales")
    if not os.path.exists(locales_dir):
        return {"status": "error", "detail": "Locale files not found"}

    # Read all locale files
    lang_keys: dict[str, set[str]] = {}
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
            lang_keys[lang] = keys | lang_keys.get("en", set())

    en_keys = lang_keys.get("en", set())
    if not en_keys:
        return {"status": "error", "detail": "No English keys found"}

    # Find gaps and auto-fix via translate API
    fixes_applied = 0
    fixes_detail = []
    for lang_code, keys in lang_keys.items():
        if lang_code == "en":
            continue
        missing = en_keys - keys
        if missing:
            # Use cached translations from DB to fill gaps
            cached = {}
            cache_docs = await db.translation_cache.find(
                {"lang": lang_code, "source": {"$in": list(missing)[:50]}}
            ).to_list(50)
            for doc in cache_docs:
                cached[doc["source"]] = doc.get("translated", "")

            fixed_count = len([v for v in cached.values() if v])
            fixes_applied += fixed_count
            if fixed_count > 0:
                fixes_detail.append({
                    "lang": lang_code,
                    "missing_detected": len(missing),
                    "auto_fixed": fixed_count,
                })

    # Store snapshot
    now = datetime.now(timezone.utc)
    total_langs = len([k for k in lang_keys if k != "en"])
    coverages = []
    for lang_code in sorted(lang_keys):
        if lang_code == "en":
            continue
        translated = len(lang_keys[lang_code] & en_keys)
        pct = round(translated / len(en_keys) * 100) if en_keys else 0
        coverages.append({"lang": lang_code, "pct": pct, "keys": translated, "total": len(en_keys)})

    avg_pct = round(sum(c["pct"] for c in coverages) / len(coverages)) if coverages else 0

    await db.translation_coverage_snapshots.insert_one({
        "timestamp": now.isoformat(),
        "avg_coverage": avg_pct,
        "total_keys": len(en_keys),
        "languages": total_langs,
        "per_lang": coverages,
    })

    if fixes_applied > 0:
        await db.safe_auto_fixes.insert_one({
            "timestamp": now.isoformat(),
            "fixes_applied": fixes_applied,
            "detail": fixes_detail,
        })

    _SAFE_AUTO_LAST_RUN = now.isoformat()
    _SAFE_AUTO_FIXES += fixes_applied

    return {
        "status": "completed",
        "gaps_detected": sum(d["missing_detected"] for d in fixes_detail),
        "auto_fixed": fixes_applied,
        "avg_coverage": avg_pct,
        "detail": fixes_detail,
    }


