"""i18n translation quality: reviews, AI scoring, fixes, config, weekly check."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone, timedelta

from ..db import db, require_auth

from .constants import SUPPORTED_LANGUAGES
from .helpers import router, logger, _load_all_locale_maps, _write_locale_updates
from .coverage import get_translation_coverage
from .smoke_report import _get_or_run_multilingual_smoke_report

@router.get("/brand-protection/audit")
async def get_brand_protection_audit(request: Request, limit: int = 50):
    user = await require_auth(request)
    if not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = await db.brand_protection_audit.find({}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 200))).to_list(limit)
    return {
        "total_recent": len(rows),
        "violations_recent": sum(1 for row in rows if row.get("violations")),
        "rows": rows,
    }


@router.get("/quality-review")
async def get_translation_quality_review(request: Request):
    """Get translation quality review data - shows AI-generated vs human-verified translations."""
    lang_keys = _load_all_locale_maps()
    if not lang_keys.get("en"):
        raise HTTPException(status_code=404, detail="Locale files not found")

    en_keys = lang_keys.get("en", {})

    # Check quality review status from DB
    reviews = {}
    async for doc in db.translation_reviews.find({}, {"_id": 0}):
        key = f"{doc['lang']}:{doc['key']}"
        reviews[key] = doc

    # Build quality data
    languages_quality = []
    for lang in sorted(lang_keys.keys()):
        if lang == "en":
            continue
        lang_data = lang_keys[lang]
        lang_name = SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang)
        
        total = len(lang_data)
        verified = 0
        flagged = 0
        samples = []
        
        for key, value in list(lang_data.items())[:200]:  # Limit to first 200 for performance
            review_key = f"{lang}:{key}"
            review = reviews.get(review_key)
            
            if review:
                if review.get("status") == "verified":
                    verified += 1
                elif review.get("status") == "flagged":
                    flagged += 1
            
            en_value = en_keys.get(key, "")
            if en_value and len(samples) < 10:
                samples.append({
                    "key": key,
                    "en": en_value,
                    "translated": value,
                    "status": review.get("status", "unreviewed") if review else "unreviewed",
                    "notes": review.get("notes", "") if review else "",
                })

        languages_quality.append({
            "code": lang,
            "name": lang_name,
            "total_keys": total,
            "verified": verified,
            "flagged": flagged,
            "unreviewed": total - verified - flagged,
            "samples": samples,
        })

    return {
        "languages": languages_quality,
        "total_reviews": len(reviews),
    }


@router.post("/quality-review")
async def submit_translation_review(request: Request):
    """Submit a quality review for a specific translation."""
    body = await request.json()
    lang = body.get("lang")
    key = body.get("key")
    status = body.get("status")  # "verified", "flagged", "unreviewed"
    notes = body.get("notes", "")

    if not lang or not key or status not in ("verified", "flagged", "unreviewed"):
        raise HTTPException(status_code=400, detail="lang, key, and valid status required")

    user = await require_auth(request)

    await db.translation_reviews.update_one(
        {"lang": lang, "key": key},
        {"$set": {
            "lang": lang,
            "key": key,
            "status": status,
            "notes": notes,
            "reviewed_by": user.user_id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True
    )

    return {"success": True, "lang": lang, "key": key, "status": status}


@router.post("/quality-score")
async def ai_translation_quality_score(request: Request):
    """Use AI to evaluate translation accuracy for each language and return scores."""
    import re
    import json as jsonlib
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from .db import EMERGENT_LLM_KEY

    body = await request.json()
    target_langs = body.get("languages", [])
    sample_size = min(body.get("sample_size", 20), 30)

    lang_keys = _load_all_locale_maps()

    en_keys = lang_keys.get("en", {})
    if not en_keys:
        raise HTTPException(status_code=400, detail="No English keys found")

    non_en_langs = [lang_code for lang_code in lang_keys if lang_code != "en"]
    if target_langs:
        non_en_langs = [lang_code for lang_code in target_langs if lang_code in lang_keys and lang_code != "en"]

    results = []
    import random

    for lang in non_en_langs:
        lang_data = lang_keys[lang]
        lang_name = SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang)

        common_keys = list(set(en_keys.keys()) & set(lang_data.keys()))
        if not common_keys:
            results.append({"code": lang, "name": lang_name, "score": 0, "issues": [], "status": "no_translations"})
            continue

        sample_keys = random.sample(common_keys, min(sample_size, len(common_keys)))
        sample_pairs = {k: {"en": en_keys[k], "translated": lang_data[k]} for k in sample_keys}

        try:
            import uuid as uuid_mod
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"i18n-quality-{lang}-{uuid_mod.uuid4()}",
                system_message=f"""You are a professional translation quality evaluator. Score translations from English to {lang_name}.
For each translation pair, evaluate: accuracy, naturalness, consistency, completeness.
Return ONLY a JSON object with this exact structure:
{{"overall_score": <1-100>, "issues": [{{"key": "<key>", "severity": "high|medium|low", "issue": "<brief description>", "suggestion": "<improved translation>"}}], "summary": "<1 sentence summary>"}}
Only flag actual errors. If translations are good, return an empty issues array with a high score.""",
            ).with_model("openai", "gpt-4o-mini")

            prompt = jsonlib.dumps(sample_pairs, ensure_ascii=False)
            response = await chat.send_message(UserMessage(text=f"Evaluate these {lang_name} translations:\n{prompt}"))

            response_text = str(response).strip()
            if response_text.startswith("```"):
                response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
                response_text = re.sub(r"\s*```$", "", response_text)

            ai_result = jsonlib.loads(response_text)
            results.append({
                "code": lang,
                "name": lang_name,
                "score": ai_result.get("overall_score", 0),
                "issues": ai_result.get("issues", [])[:10],
                "summary": ai_result.get("summary", ""),
                "sample_size": len(sample_keys),
                "total_keys": len(lang_data),
                "status": "scored",
            })
        except Exception as e:
            logger.error(f"AI quality score failed for {lang}: {e}")
            results.append({"code": lang, "name": lang_name, "score": -1, "issues": [], "status": "error", "error": str(e)})

    # Store results in DB
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        if r["status"] == "scored":
            await db.translation_quality_scores.update_one(
                {"lang": r["code"]},
                {"$set": {**r, "evaluated_at": now}},
                upsert=True,
            )

    return {"scores": results, "evaluated_at": now}


@router.post("/fix-translations")
async def ai_fix_translations(request: Request):
    """Use AI to automatically correct low-quality translations."""
    import re
    import json as jsonlib
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from .db import EMERGENT_LLM_KEY

    body = await request.json()
    lang = body.get("language")
    keys_to_fix = body.get("keys", [])

    if not lang or lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Valid language code required")

    lang_keys = _load_all_locale_maps()
    if not lang_keys.get("en"):
        raise HTTPException(status_code=404, detail="Locale files not found")

    en_keys = lang_keys.get("en", {})
    target_data = lang_keys.get(lang, {})
    lang_name = SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang)

    if keys_to_fix:
        to_fix = {k: {"en": en_keys.get(k, ""), "current": target_data.get(k, "")} for k in keys_to_fix if k in en_keys}
    else:
        # Get issues from the latest quality score
        score_doc = await db.translation_quality_scores.find_one({"lang": lang}, {"_id": 0})
        if score_doc and score_doc.get("issues"):
            issue_keys = [i["key"] for i in score_doc["issues"]]
            to_fix = {k: {"en": en_keys.get(k, ""), "current": target_data.get(k, "")} for k in issue_keys if k in en_keys}
        else:
            return {"success": True, "fixed": 0, "message": "No issues to fix"}

    if not to_fix:
        return {"success": True, "fixed": 0, "message": "No valid keys to fix"}

    try:
        import uuid as uuid_mod
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"i18n-fix-{lang}-{uuid_mod.uuid4()}",
            system_message=f"""You are a professional translator correcting {lang_name} translations.
For each key, you'll receive the English original and the current (possibly incorrect) translation.
Provide improved translations. Return ONLY a valid JSON object mapping keys to corrected translations.
Keep {{placeholders}} unchanged. Keep brand names unchanged. Use natural, professional language.""",
        ).with_model("openai", "gpt-4o-mini")

        prompt = jsonlib.dumps(to_fix, ensure_ascii=False)
        response = await chat.send_message(UserMessage(text=f"Fix these {lang_name} translations:\n{prompt}"))

        response_text = str(response).strip()
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
            response_text = re.sub(r"\s*```$", "", response_text)

        fixes = jsonlib.loads(response_text)
    except Exception as e:
        logger.error(f"AI fix translations failed for {lang}: {e}")
        raise HTTPException(status_code=500, detail=f"AI translation fix failed: {str(e)}")

    # Apply fixes to locale file
    effective_updates: dict[str, str] = {}
    for key, new_value in fixes.items():
        if key not in target_data:
            continue
        effective_updates[key] = str(new_value)

    fixed_count = 0
    if effective_updates:
        fixed_count = _write_locale_updates(lang, effective_updates, append_missing=False)

    # Update quality score with fixes
    now = datetime.now(timezone.utc).isoformat()
    await db.translation_fixes.insert_one({
        "lang": lang,
        "fixes": {k: v for k, v in fixes.items()},
        "fixed_count": fixed_count,
        "fixed_at": now,
    })

    return {"success": True, "fixed": fixed_count, "total_attempted": len(fixes), "language": lang}


@router.get("/quality-scores")
async def get_cached_quality_scores():
    """Get cached quality scores for all languages."""
    scores = []
    async for doc in db.translation_quality_scores.find({}, {"_id": 0}):
        scores.append(doc)
    return {"scores": scores}


@router.get("/quality-history")
async def get_quality_score_history():
    """Get quality score history for trend visualization."""
    history = []
    async for doc in db.translation_quality_history.find({}, {"_id": 0}).sort("evaluated_at", -1).limit(100):
        history.append(doc)
    return {"history": list(reversed(history))}


@router.get("/admin/language-quality-dashboard")
async def get_admin_language_quality_dashboard(request: Request, days: int = 7):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    days = 7 if days <= 0 else min(days, 30)
    coverage = await get_translation_coverage(request)
    score_rows = await db.translation_quality_scores.find({}, {"_id": 0}).to_list(200)
    history_rows = await db.translation_quality_history.find({}, {"_id": 0}).sort("evaluated_at", -1).limit(12).to_list(12)
    review_rows = await db.translation_reviews.find({}, {"_id": 0, "lang": 1, "status": 1}).to_list(5000)

    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    fallback_rows = await db.translation_fallback_hits.find(
        {"created_at": {"$gte": since_iso}},
        {"_id": 0},
    ).to_list(10000)

    scores_by_lang = {str(row.get("lang") or row.get("code") or ""): row for row in score_rows}
    reviews_by_lang: dict[str, dict[str, int]] = {}
    for row in review_rows:
        lang = str(row.get("lang") or "")
        if not lang:
            continue
        bucket = reviews_by_lang.setdefault(lang, {"verified": 0, "flagged": 0, "unreviewed": 0})
        status = str(row.get("status") or "unreviewed")
        if status not in bucket:
            status = "unreviewed"
        bucket[status] += 1

    fallback_hits_by_lang: dict[str, int] = {}
    fallback_routes: dict[str, int] = {}
    fallback_keys: dict[str, int] = {}
    for row in fallback_rows:
        lang = str(row.get("language") or "")
        hits = int(row.get("hits") or 0)
        route = str(row.get("route") or "unknown")
        key = str(row.get("key") or "")
        if lang:
            fallback_hits_by_lang[lang] = fallback_hits_by_lang.get(lang, 0) + hits
        fallback_routes[route] = fallback_routes.get(route, 0) + hits
        if key:
            fallback_keys[key] = fallback_keys.get(key, 0) + hits

    languages = []
    for lang in coverage.get("languages", []):
        code = str(lang.get("code") or "")
        translated_keys = int(lang.get("translated_keys") or 0)
        fallback_hits = int(fallback_hits_by_lang.get(code, 0))
        hits_per_1k_keys = round((fallback_hits / max(translated_keys, 1)) * 1000, 2)
        score_doc = scores_by_lang.get(code, {})
        review_doc = reviews_by_lang.get(code, {"verified": 0, "flagged": 0, "unreviewed": 0})
        quality_score = int(score_doc.get("score") or 0) if score_doc.get("score") not in (None, -1) else None
        languages.append({
            "code": code,
            "name": lang.get("name"),
            "coverage_pct": lang.get("coverage_pct", 0),
            "translated_keys": translated_keys,
            "missing_keys": int(lang.get("missing_keys") or 0),
            "quality_score": quality_score,
            "quality_summary": score_doc.get("summary") or "",
            "fallback_hits": fallback_hits,
            "fallback_hits_per_1k_keys": hits_per_1k_keys,
            "review_counts": review_doc,
            "needs_attention": bool((lang.get("coverage_pct", 0) < 100) or (quality_score is not None and quality_score < 80) or fallback_hits > 0),
        })

    languages.sort(key=lambda row: (0 if row["needs_attention"] else 1, row.get("coverage_pct", 0), row.get("quality_score") or 999))
    avg_quality_score = round(sum((row.get("quality_score") or 0) for row in languages if row.get("quality_score") is not None) / max(len([row for row in languages if row.get("quality_score") is not None]), 1), 1) if languages else 0.0
    total_fallback_hits = sum(fallback_hits_by_lang.values())

    hotspot_routes = [
        {"route": route, "hits": hits}
        for route, hits in sorted(fallback_routes.items(), key=lambda item: item[1], reverse=True)[:8]
    ]
    hotspot_keys = [
        {"key": key, "hits": hits}
        for key, hits in sorted(fallback_keys.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    smoke_report = await _get_or_run_multilingual_smoke_report(request)

    return {
        "window_days": days,
        "summary": {
            "avg_coverage": coverage.get("avg_coverage", 0),
            "avg_quality_score": avg_quality_score,
            "total_languages": coverage.get("total_languages", 0),
            "total_missing_keys": sum(int(lang.get("missing_keys") or 0) for lang in coverage.get("languages", [])),
            "total_fallback_hits": total_fallback_hits,
            "languages_needing_attention": sum(1 for row in languages if row.get("needs_attention")),
        },
        "languages": languages,
        "hotspot_routes": hotspot_routes,
        "hotspot_keys": hotspot_keys,
        "quality_history": list(reversed(history_rows)),
        "smoke_report": smoke_report,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

@router.get("/quality-config")
async def get_quality_config():
    """Get translation health monitoring configuration."""
    config = await db.translation_health_config.find_one({"key": "config"}, {"_id": 0})
    if not config:
        config = {
            "key": "config",
            "enabled": True,
            "frequency": "weekly",
            "threshold": 70,
            "email_alerts": True,
            "alert_recipients": [],
            "last_run": None,
        }
        await db.translation_health_config.insert_one({**config})
    return dict(config)


@router.post("/quality-config")
async def update_quality_config(request: Request):
    """Update translation health monitoring configuration."""
    body = await request.json()
    allowed = {"enabled", "frequency", "threshold", "email_alerts", "alert_recipients"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.translation_health_config.update_one(
        {"key": "config"}, {"$set": update}, upsert=True
    )
    return {"success": True, **update}


async def run_weekly_translation_quality_check():
    """Scheduled job: run AI quality scoring and send email alerts if quality drops."""
    import re
    import json as jsonlib
    import random
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.db import db as _db, EMERGENT_LLM_KEY

    config = await _db.translation_health_config.find_one({"key": "config"})
    if config and not config.get("enabled", True):
        logger.info("[i18n-health] Disabled, skipping weekly scan")
        return

    threshold = (config or {}).get("threshold", 70)
    logger.info(f"[i18n-health] Starting weekly translation quality check (threshold={threshold}%)")

    lang_keys = _load_all_locale_maps()
    if not lang_keys.get("en"):
        logger.error("[i18n-health] locale files not found")
        return

    en_keys = lang_keys.get("en", {})
    non_en = [lang_code for lang_code in lang_keys if lang_code != "en"]
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for lang in non_en:
        lang_data = lang_keys[lang]
        lang_name = SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang)
        common = list(set(en_keys.keys()) & set(lang_data.keys()))
        if not common:
            results.append({"code": lang, "name": lang_name, "score": 0, "status": "no_translations"})
            continue

        sample = random.sample(common, min(15, len(common)))
        pairs = {k: {"en": en_keys[k], "translated": lang_data[k]} for k in sample}

        try:
            import uuid as uuid_mod
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"i18n-weekly-{lang}-{uuid_mod.uuid4().hex[:6]}",
                system_message=f"""You are a translation quality evaluator. Score translations from English to {lang_name}.
Return ONLY JSON: {{"overall_score": <1-100>, "issues_count": <number>, "summary": "<1 sentence>"}}""",
            ).with_model("openai", "gpt-4o-mini")

            response = await chat.send_message(UserMessage(text=f"Evaluate:\n{jsonlib.dumps(pairs, ensure_ascii=False)}"))
            text = str(response).strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            ai = jsonlib.loads(text)
            results.append({
                "code": lang, "name": lang_name,
                "score": ai.get("overall_score", 0),
                "issues_count": ai.get("issues_count", 0),
                "summary": ai.get("summary", ""),
                "status": "scored",
            })
        except Exception as e:
            logger.error(f"[i18n-health] Score failed for {lang}: {e}")
            results.append({"code": lang, "name": lang_name, "score": -1, "status": "error"})

    # Save to history for trend tracking
    avg_score = 0
    scored = [r for r in results if r.get("score", -1) > 0]
    if scored:
        avg_score = round(sum(r["score"] for r in scored) / len(scored))

    history_entry = {
        "evaluated_at": now,
        "avg_score": avg_score,
        "languages_scored": len(scored),
        "languages_below_threshold": len([r for r in scored if r["score"] < threshold]),
        "scores": {r["code"]: r["score"] for r in results if r.get("score", -1) >= 0},
    }
    await _db.translation_quality_history.insert_one(history_entry)

    # Update per-language cached scores
    for r in results:
        if r["status"] == "scored":
            await _db.translation_quality_scores.update_one(
                {"lang": r["code"]},
                {"$set": {**r, "evaluated_at": now}},
                upsert=True,
            )

    # Update config with last run
    await _db.translation_health_config.update_one(
        {"key": "config"},
        {"$set": {"last_run": now, "last_avg_score": avg_score}},
        upsert=True,
    )

    # Send email alert if quality is below threshold
    below_threshold = [r for r in scored if r["score"] < threshold]
    if below_threshold:
        email_alerts = (config or {}).get("email_alerts", True)
        if email_alerts:
            try:
                from utils.email_service import is_email_configured
                if is_email_configured():
                    recipients = (config or {}).get("alert_recipients", [])
                    if not recipients:
                        admins = await _db.users.find({"role": "admin"}, {"_id": 0, "email": 1}).to_list(10)
                        recipients = [a["email"] for a in admins if a.get("email")]

                    if recipients:
                        langs_html = "".join(
                            f"<tr><td style='padding:8px 12px;border-bottom:1px solid #eee;font-weight:600'>{r['code'].upper()}</td>"
                            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{r['name']}</td>"
                            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:{'#EF4444' if r['score']<60 else '#F59E0B'};font-weight:700'>{r['score']}%</td>"
                            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-size:12px;color:#666'>{r.get('summary','')}</td></tr>"
                            for r in below_threshold
                        )
                        f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:12px;padding:20px;margin-bottom:20px">
    <h2 style="color:#991B1B;margin:0 0 8px">Translation Quality Alert</h2>
    <p style="color:#7F1D1D;margin:0;font-size:14px">
      {len(below_threshold)} language(s) scored below the {threshold}% quality threshold in this week's automated scan.
    </p>
  </div>
  <table style="width:100%;border-collapse:collapse;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden">
    <thead>
      <tr style="background:#F9FAFB">
        <th style="padding:10px 12px;text-align:left;font-size:12px;color:#6B7280">Code</th>
        <th style="padding:10px 12px;text-align:left;font-size:12px;color:#6B7280">Language</th>
        <th style="padding:10px 12px;text-align:left;font-size:12px;color:#6B7280">Score</th>
        <th style="padding:10px 12px;text-align:left;font-size:12px;color:#6B7280">Summary</th>
      </tr>
    </thead>
    <tbody>{langs_html}</tbody>
  </table>
  <p style="color:#6B7280;font-size:13px;margin-top:16px">
    Average quality score: <strong>{avg_score}%</strong> | Languages scored: {len(scored)}
  </p>
  <p style="color:#6B7280;font-size:12px;margin-top:8px">
    Fix low-quality translations in Admin Console &rarr; Communications &rarr; Languages &rarr; AI Translation Quality Score.
  </p>
</div>"""
                        from utils.email_service import send_catalog_template
                        for email in recipients:
                            await send_catalog_template(
                                recipient_email=email,
                                template_key="i18n_quality_alert",
                                below_threshold=below_threshold,
                                threshold=threshold,
                                avg_score=avg_score,
                            )
                        logger.info(f"[i18n-health] Alert sent to {len(recipients)} recipients")
            except Exception as e:
                logger.error(f"[i18n-health] Email alert failed: {e}")

    logger.info(f"[i18n-health] Weekly check complete. Avg={avg_score}%, below threshold={len(below_threshold)}")
    return {"avg_score": avg_score, "languages_scored": len(scored), "below_threshold": len(below_threshold)}


# ── Translation Memory / Glossary System ──

