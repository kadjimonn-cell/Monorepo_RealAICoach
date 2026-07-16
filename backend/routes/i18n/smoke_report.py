"""i18n multilingual smoke report."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone, timedelta

from ..db import db, require_auth

from .helpers import router, _safe_parse_iso
from .core_routes import i18n_health_check
from .auto_translate import safe_auto_status
from .coverage import get_api_data_coverage


def _i18n_request_origin(request: Request) -> str:
    proto = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").split(",")[0].strip()
    if not host:
        return str(request.base_url).rstrip("/")
    return f"{proto}://{host}".rstrip("/")


async def _build_multilingual_smoke_report(request: Request) -> dict:
    import httpx
    from services.auto_translate import translate_batch

    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    origin = _i18n_request_origin(request)
    monitored_routes = [
        "/welcome",
        "/auth/login",
        "/language-selector",
        "/notifications",
        "/dashboard",
    ]
    smoke_languages = ["es", "fr", "de"]
    sample_texts = ["Dashboard", "Settings", "Notifications", "Language"]

    health = await i18n_health_check()
    safe_auto = await safe_auto_status()
    api_data = await get_api_data_coverage()

    route_results = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for route in monitored_routes:
            url = f"{origin}{route}"
            status_code = 0
            ok = False
            detail = ""
            try:
                response = await client.get(url)
                status_code = response.status_code
                ok = 200 <= status_code < 400
                detail = "ok" if ok else f"status_{status_code}"
            except Exception as exc:
                detail = str(exc)[:160]
            route_results.append({
                "route": route,
                "url": url,
                "status_code": status_code,
                "ok": ok,
                "detail": detail,
            })

    language_results = []
    for code in smoke_languages:
        translated = await translate_batch(sample_texts, code)
        changed = sum(
            1
            for text in sample_texts
            if str((translated or {}).get(text) or "").strip() and str((translated or {}).get(text) or "").strip() != text
        )
        language_results.append({
            "code": code,
            "ok": changed >= 2,
            "changed_count": changed,
            "sample": {text: (translated or {}).get(text, "") for text in sample_texts[:3]},
        })

    monitored_route_set = set(monitored_routes)
    fallback_since = (now - timedelta(hours=24)).isoformat()
    fallback_rows = await db.translation_fallback_hits.find(
        {"created_at": {"$gte": fallback_since}, "route": {"$in": list(monitored_route_set)}},
        {"_id": 0, "route": 1, "hits": 1, "language": 1},
    ).to_list(2000)

    fallback_by_route = {}
    fallback_total = 0
    for row in fallback_rows:
        route = str(row.get("route") or "unknown")
        hits = int(row.get("hits") or 0)
        fallback_by_route[route] = fallback_by_route.get(route, 0) + hits
        fallback_total += hits

    route_health_count = sum(1 for row in route_results if row.get("ok"))
    language_health_count = sum(1 for row in language_results if row.get("ok"))
    api_overall_pct = int((api_data or {}).get("api_overall_pct") or 0)
    safe_auto_last_scan = str((safe_auto or {}).get("last_scan") or "")
    safe_auto_recent = bool(_safe_parse_iso(safe_auto_last_scan) and (_safe_parse_iso(safe_auto_last_scan) > now - timedelta(hours=30)))
    broken_links = [row for row in route_results if not row.get("ok")]

    score = 100
    score -= max(0, (len(broken_links) * 20))
    score -= max(0, ((len(language_results) - language_health_count) * 15))
    score -= 15 if health.get("status") != "healthy" else 0
    score -= 10 if not safe_auto_recent else 0
    score -= 10 if api_overall_pct < 95 else 0
    score -= min(20, fallback_total // 25)
    score = max(0, score)

    if score >= 90:
        overall_status = "healthy"
    elif score >= 70:
        overall_status = "watch"
    else:
        overall_status = "critical"

    return {
        "report_type": "nightly_multilingual_smoke",
        "generated_at": generated_at,
        "window_hours": 24,
        "origin": origin,
        "overall_status": overall_status,
        "score": score,
        "summary": {
            "routes_ok": route_health_count,
            "routes_total": len(route_results),
            "languages_ok": language_health_count,
            "languages_total": len(language_results),
            "broken_links": len(broken_links),
            "fallback_hits_24h": fallback_total,
            "api_overall_pct": api_overall_pct,
            "engine_active": bool((safe_auto or {}).get("engine_active")),
            "engine_recent_scan": safe_auto_recent,
            "cache_entries": int(health.get("cache_entries") or 0),
        },
        "route_results": [
            {**row, "fallback_hits_24h": int(fallback_by_route.get(row.get("route") or "", 0))}
            for row in route_results
        ],
        "language_results": language_results,
        "api_tables": (api_data or {}).get("api_tables") or [],
        "top_route_fallbacks": [
            {"route": route, "hits": hits}
            for route, hits in sorted(fallback_by_route.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
    }


async def _get_or_run_multilingual_smoke_report(request: Request, force: bool = False) -> dict:
    latest = await db.translation_smoke_reports.find_one({}, sort=[("generated_at", -1)], projection={"_id": 0})
    latest_generated = _safe_parse_iso(str((latest or {}).get("generated_at") or ""))
    if latest and latest_generated and latest_generated > (datetime.now(timezone.utc) - timedelta(hours=20)) and not force:
        return latest

    report = await _build_multilingual_smoke_report(request)
    await db.translation_smoke_reports.insert_one({**report})
    return report


@router.get("/admin/multilingual-smoke-report")
async def get_admin_multilingual_smoke_report(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _get_or_run_multilingual_smoke_report(request)


@router.post("/admin/multilingual-smoke-report/run")
async def run_admin_multilingual_smoke_report(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _get_or_run_multilingual_smoke_report(request, force=True)


