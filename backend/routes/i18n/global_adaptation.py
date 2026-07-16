"""i18n global adaptation: mismatch overview, remediation, effectiveness analytics."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone, timedelta

from ..db import db, require_auth

from .constants import COUNTRY_LANGUAGE_HINTS, COUNTRY_CURRENCY_HINTS
from .helpers import router, _extract_language_from_preference_doc, _guidance_copy, _safe_parse_iso

async def _build_global_adaptation_overview(limit: int = 5000) -> dict:
    users = await db.users.find(
        {},
        {"_id": 0, "user_id": 1, "email": 1, "country": 1, "currency_preference": 1, "name": 1},
    ).to_list(limit)
    pref_docs = await db.user_preferences.find(
        {},
        {"_id": 0, "user_id": 1, "value": 1, "key": 1, "language": 1},
    ).to_list(limit)
    pref_map = {}
    for doc in pref_docs:
        user_id = str(doc.get("user_id") or "")
        if not user_id:
            continue
        lang = _extract_language_from_preference_doc(doc)
        if lang != "en" or user_id not in pref_map:
            pref_map[user_id] = lang

    mismatches = []
    by_country = {}
    language_mismatch_count = 0
    currency_mismatch_count = 0

    for user in users:
        user_id = str(user.get("user_id") or "")
        if not user_id:
            continue
        country = str(user.get("country") or "US").upper()
        expected_language = COUNTRY_LANGUAGE_HINTS.get(country, "en")
        expected_currency = COUNTRY_CURRENCY_HINTS.get(country, "USD")
        preferred_language = pref_map.get(user_id, "en")
        preferred_currency = str(user.get("currency_preference") or "USD").upper()

        language_mismatch = preferred_language != expected_language
        currency_mismatch = preferred_currency != expected_currency
        if language_mismatch:
            language_mismatch_count += 1
        if currency_mismatch:
            currency_mismatch_count += 1

        if language_mismatch or currency_mismatch:
            mismatches.append({
                "user_id": user_id,
                "email": str(user.get("email") or ""),
                "name": str(user.get("name") or ""),
                "country": country,
                "preferred_language": preferred_language,
                "expected_language": expected_language,
                "preferred_currency": preferred_currency,
                "expected_currency": expected_currency,
                "language_mismatch": language_mismatch,
                "currency_mismatch": currency_mismatch,
                "has_manual_currency": bool(user.get("currency_preference")),
            })
            by_country[country] = by_country.get(country, 0) + 1

    by_country_summary = [{"country": k, "mismatch_count": v} for k, v in sorted(by_country.items(), key=lambda x: x[1], reverse=True)]
    return {
        "total_users": len(users),
        "language_mismatch_count": language_mismatch_count,
        "currency_mismatch_count": currency_mismatch_count,
        "combined_mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "by_country": by_country_summary,
    }

@router.get("/admin/global-adaptation/overview")
async def admin_global_adaptation_overview(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    data = await _build_global_adaptation_overview(limit=7000)
    return {
        "summary": {
            "total_users": data["total_users"],
            "language_mismatch_count": data["language_mismatch_count"],
            "currency_mismatch_count": data["currency_mismatch_count"],
            "combined_mismatch_count": data["combined_mismatch_count"],
        },
        "countries": data["by_country"][:20],
        "mismatches": data["mismatches"][:120],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/admin/global-adaptation/remediate")
async def admin_global_adaptation_remediate(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json() if request else {}
    auto_align_currency = bool(body.get("auto_align_currency", False))
    data = await _build_global_adaptation_overview(limit=7000)

    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    batch_id = f"adapt-{int(now.timestamp())}"
    notifications_created = 0
    currencies_auto_aligned = 0

    for mismatch in data["mismatches"]:
        user_id = mismatch["user_id"]
        expected_language = mismatch["expected_language"]
        preferred_language = mismatch["preferred_language"]
        guidance = _guidance_copy(preferred_language, expected_language, "/language-selector")

        dedupe_key = f"adapt-batch-{batch_id}-{user_id}"
        existing = await db.system_events.find_one({"event_key": dedupe_key}, {"_id": 0, "event_key": 1})
        if existing:
            continue

        await db.notifications.insert_one({
            "id": f"adapt_{user_id}_{notifications_created + 1}_{int(now.timestamp())}",
            "user_id": user_id,
            "type": "language_guidance",
            "title": guidance["title"],
            "message": guidance["message"],
            "read": False,
            "created_at": created_at,
            "metadata": {
                "suggested_language": expected_language,
                "settings_url": "/language-selector",
                "batch_id": batch_id,
            },
        })
        notifications_created += 1
        await db.system_events.insert_one({
            "event_key": dedupe_key,
            "event_type": "global_adaptation_remediation",
            "user_id": user_id,
            "created_at": created_at,
            "batch_id": batch_id,
        })

        if auto_align_currency and mismatch.get("currency_mismatch") and not mismatch.get("has_manual_currency"):
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"currency_preference": mismatch["expected_currency"], "updated_at": created_at}},
            )
            currencies_auto_aligned += 1

    return {
        "success": True,
        "batch_id": batch_id,
        "notifications_created": notifications_created,
        "currencies_auto_aligned": currencies_auto_aligned,
        "mismatch_count": data["combined_mismatch_count"],
    }


@router.get("/admin/global-adaptation/effectiveness")
async def admin_global_adaptation_effectiveness(request: Request, days: int = 7, include_country_breakdown: bool = True):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    days = 7 if days <= 0 else min(days, 30)
    now = datetime.now(timezone.utc)
    trend_start_day = (now - timedelta(days=days - 1)).date()
    trend_dates = [(trend_start_day + timedelta(days=i)).isoformat() for i in range(days)]
    window_iso = datetime.combine(trend_start_day, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    events = await db.language_guidance_events.find(
        {"created_at": {"$gte": window_iso}},
        {"_id": 0},
    ).to_list(20000)

    open_count = 0
    dismiss_count = 0
    switch_count = 0
    remediation_success_count = 0
    by_country: dict[str, dict] = {}
    first_open_by_user: dict[str, datetime] = {}
    align_deltas: list[float] = []
    daily_stats: dict[str, dict] = {
        d: {
            "open": 0,
            "dismiss": 0,
            "switch": 0,
            "remediation_success": 0,
            "remediation": 0,
            "align_deltas": [],
        }
        for d in trend_dates
    }

    parsed_events = []
    for evt in events:
        created_dt = _safe_parse_iso(str(evt.get("created_at") or ""))
        if not created_dt:
            continue
        parsed_events.append((created_dt, evt))
    parsed_events.sort(key=lambda x: x[0])

    for created_dt, evt in parsed_events:
        evt_type = str(evt.get("event_type") or "")
        user_id = str(evt.get("user_id") or "")
        country = str(evt.get("country") or "UNKNOWN").upper()
        created_day = created_dt.astimezone(timezone.utc).date().isoformat()
        if country not in by_country:
            by_country[country] = {"country": country, "open": 0, "dismiss": 0, "switch": 0}

        if evt_type == "open":
            open_count += 1
            by_country[country]["open"] += 1
            if created_day in daily_stats:
                daily_stats[created_day]["open"] += 1
            if user_id and created_dt and user_id not in first_open_by_user:
                first_open_by_user[user_id] = created_dt
        elif evt_type == "dismiss":
            dismiss_count += 1
            by_country[country]["dismiss"] += 1
            if created_day in daily_stats:
                daily_stats[created_day]["dismiss"] += 1
        elif evt_type == "switch":
            switch_count += 1
            by_country[country]["switch"] += 1
            if created_day in daily_stats:
                daily_stats[created_day]["switch"] += 1
            if user_id and created_dt and user_id in first_open_by_user:
                delta_min = (created_dt - first_open_by_user[user_id]).total_seconds() / 60.0
                if delta_min >= 0:
                    align_deltas.append(delta_min)
                    if created_day in daily_stats:
                        daily_stats[created_day]["align_deltas"].append(delta_min)
        elif evt_type == "remediation_success":
            remediation_success_count += 1
            if created_day in daily_stats:
                daily_stats[created_day]["remediation_success"] += 1

    remediation_events = await db.system_events.find(
        {"event_type": "global_adaptation_remediation", "created_at": {"$gte": window_iso}},
        {"_id": 0, "user_id": 1, "created_at": 1},
    ).to_list(20000)
    remediation_count = len(remediation_events)
    for remediation_evt in remediation_events:
        created_dt = _safe_parse_iso(str(remediation_evt.get("created_at") or ""))
        if not created_dt:
            continue
        created_day = created_dt.astimezone(timezone.utc).date().isoformat()
        if created_day in daily_stats:
            daily_stats[created_day]["remediation"] += 1

    dismiss_rate = round((dismiss_count / open_count) * 100, 2) if open_count else 0.0
    switch_conversion_rate = round((switch_count / open_count) * 100, 2) if open_count else 0.0
    remediation_success_rate = round((remediation_success_count / remediation_count) * 100, 2) if remediation_count else 0.0
    avg_time_to_align_minutes = round(sum(align_deltas) / len(align_deltas), 2) if align_deltas else 0.0

    country_breakdown = []
    if include_country_breakdown:
        for country, stat in by_country.items():
            opens = stat["open"]
            country_breakdown.append({
                "country": country,
                "open": stat["open"],
                "dismiss": stat["dismiss"],
                "switch": stat["switch"],
                "dismiss_rate": round((stat["dismiss"] / opens) * 100, 2) if opens else 0.0,
                "switch_conversion_rate": round((stat["switch"] / opens) * 100, 2) if opens else 0.0,
            })
        country_breakdown.sort(key=lambda x: x["open"], reverse=True)

    daily_trend = []
    for date_key in trend_dates:
        daily = daily_stats.get(date_key, {})
        opens = int(daily.get("open", 0) or 0)
        dismisses = int(daily.get("dismiss", 0) or 0)
        switches = int(daily.get("switch", 0) or 0)
        remediations = int(daily.get("remediation", 0) or 0)
        remediation_successes = int(daily.get("remediation_success", 0) or 0)
        daily_align = daily.get("align_deltas") or []

        daily_trend.append({
            "date": date_key,
            "open_count": opens,
            "dismiss_rate": round((dismisses / opens) * 100, 2) if opens else 0.0,
            "switch_conversion_rate": round((switches / opens) * 100, 2) if opens else 0.0,
            "remediation_success_rate": round((remediation_successes / remediations) * 100, 2) if remediations else 0.0,
            "avg_time_to_align_minutes": round(sum(daily_align) / len(daily_align), 2) if daily_align else 0.0,
        })

    trend = {
        "labels": [day["date"] for day in daily_trend],
        "dismiss_rate": [day["dismiss_rate"] for day in daily_trend],
        "switch_conversion_rate": [day["switch_conversion_rate"] for day in daily_trend],
        "remediation_success_rate": [day["remediation_success_rate"] for day in daily_trend],
        "avg_time_to_align_minutes": [day["avg_time_to_align_minutes"] for day in daily_trend],
    }

    return {
        "window_days": days,
        "window_start": window_iso,
        "window_end": now.isoformat(),
        "metrics": {
            "open_rate": open_count,
            "dismiss_rate": dismiss_rate,
            "switch_conversion_rate": switch_conversion_rate,
            "remediation_success_rate": remediation_success_rate,
            "avg_time_to_align_minutes": avg_time_to_align_minutes,
            "open_count": open_count,
            "dismiss_count": dismiss_count,
            "switch_count": switch_count,
            "remediation_count": remediation_count,
            "remediation_success_count": remediation_success_count,
        },
        "trend": trend,
        "daily_trend": daily_trend,
        "country_breakdown": country_breakdown[:20],
    }


