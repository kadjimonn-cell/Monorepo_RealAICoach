#!/usr/bin/env python3
"""GTEC C5 white-screen sentry + responsive viewport matrix artifact generator.

Captures a stratified route matrix across mobile/tablet/desktop/web viewports,
stores screenshots, and flags failures when a route stays loader-only,
blank, 404, or fatal error surface for >5s.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error as PWError, async_playwright


ROOT = Path("/app")
REPORT_DIR = ROOT / "test_reports"
ROUTES_FILE = REPORT_DIR / "gtec_routes.json"
ARTIFACT_BASE = REPORT_DIR / "gtec_c5_viewport_matrix"
EXTRACTOR_SCRIPT = ROOT / "backend" / "scripts" / "gtec_extract_routes.py"

VIEWPORTS: dict[str, dict[str, int]] = {
    "mobile_compact": {"width": 320, "height": 740},
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 768, "height": 1024},
    "laptop": {"width": 1024, "height": 800},
    "desktop": {"width": 1440, "height": 900},
    "webwide": {"width": 1920, "height": 1080},
}

SUPPORTED_LANGUAGES = ["en", "fr", "es", "ar"]

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "ar": "Arabic",
}

FALLBACK_TOP_ROUTES = [
    "/",
    "/welcome",
    "/auth/login",
    "/features/travel-visa",
    "/features/daily-meditation",
    "/executive-dashboard",
    "/route-health-report",
    "/system-status",
    "/pricing",
    "/contact",
    "/about",
    "/faq",
    "/security",
    "/feature-gallery",
    "/integrations",
    "/careers",
    "/home",
    "/dashboard",
    "/notifications",
    "/profile",
]

PRIORITY_ROUTE_PREFIXES = [
    "/",
    "/welcome",
    "/auth/login",
    "/features/travel-visa",
    "/features/daily-meditation",
    "/executive-dashboard",
    "/route-health-report",
    "/system-status",
    "/pricing",
    "/contact",
    "/about",
    "/careers",
]

LOADER_SELECTORS_JS = (
    "[data-testid*='loader'],"
    "[data-testid*='loading'],"
    "[aria-busy='true'],"
    ".spinner,.loading,.skeleton,"  # common classes
    "[class*='spinner'],[class*='loading'],[class*='skeleton']"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_route(route: str) -> str:
    clean = route.strip() or "root"
    if clean == "/":
        return "root"
    clean = clean.lstrip("/")
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean or "route"


async def _refresh_route_inventory() -> None:
    if not EXTRACTOR_SCRIPT.exists():
        return
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(EXTRACTOR_SCRIPT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(proc.communicate(), timeout=90)


def _route_rank(route: dict[str, Any]) -> tuple[int, int, str]:
    probe = str(route.get("probe_url") or route.get("url") or "")
    category = str(route.get("category") or "public")
    score = 999
    for idx, pref in enumerate(PRIORITY_ROUTE_PREFIXES):
        if probe == pref or probe.startswith(pref + "/"):
            score = idx
            break
    cat_score = {"public": 0, "protected": 1, "dynamic": 2}.get(category, 3)
    return score, cat_score, probe


def _pick_stratified_routes(ranked: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not ranked:
        return []

    target = max(1, int(limit))
    admin_routes = [r for r in ranked if str(r.get("probe_url") or "").startswith("/admin")]
    protected_routes = [
        r for r in ranked if str(r.get("category") or "") == "protected" and r not in admin_routes
    ]
    dynamic_routes = [r for r in ranked if str(r.get("category") or "") == "dynamic"]
    public_routes = [r for r in ranked if str(r.get("category") or "") == "public"]

    admin_quota = min(len(admin_routes), max(3, target // 5))
    protected_quota = min(len(protected_routes), max(5, target // 4))
    dynamic_quota = min(len(dynamic_routes), max(3, target // 8))

    selected: list[dict[str, Any]] = []
    selected.extend(admin_routes[:admin_quota])
    selected.extend(protected_routes[:protected_quota])
    selected.extend(dynamic_routes[:dynamic_quota])

    seen = {str(r.get("probe_url") or "") for r in selected}
    for bucket in (public_routes, protected_routes, admin_routes, dynamic_routes, ranked):
        for route in bucket:
            probe = str(route.get("probe_url") or "")
            if not probe or probe in seen:
                continue
            selected.append(route)
            seen.add(probe)
            if len(selected) >= target:
                return selected

    return selected[:target]


def _normalize_languages(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        code = str(item or "").strip().lower()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out or ["en"]


def _build_language_seed_payload(language_code: str) -> dict[str, Any]:
    code = str(language_code or "en").strip().lower() or "en"
    return {
        "language": LANGUAGE_NAMES.get(code, code.upper()),
        "languageCode": code,
        "fontSize": "Medium",
    }


def _append_language_query(path: str, language_code: str) -> str:
    raw = str(path or "/").strip() or "/"
    parts = urlsplit(raw)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("lang", language_code)
    q.setdefault("locale", language_code)
    q.setdefault("hl", language_code)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(q), parts.fragment))


async def _load_top_routes(
    limit: int,
    exact_routes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    normalized_exact = [str(r or "").strip() for r in (exact_routes or []) if str(r or "").strip()]
    if normalized_exact:
        deduped: list[str] = []
        seen: set[str] = set()
        for route in normalized_exact:
            if route in seen:
                continue
            seen.add(route)
            deduped.append(route)
        selected = deduped[: max(1, int(limit))]
        return [
            {"url": r, "probe_url": r, "category": "explicit"}
            for r in selected
        ], "explicit_input"

    try:
        await _refresh_route_inventory()
    except Exception:
        pass

    if ROUTES_FILE.exists():
        try:
            payload = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))
            raw_routes = payload.get("routes") or []
            dedup: dict[str, dict[str, Any]] = {}
            for r in raw_routes:
                probe = str(r.get("probe_url") or r.get("url") or "").strip()
                if not probe:
                    continue
                # Skip unresolved dynamic placeholders (e.g. /careers/portal/[token]).
                # These are not stable user-entry routes without a concrete runtime token.
                if "[" in probe or "]" in probe:
                    continue
                if probe not in dedup:
                    dedup[probe] = {
                        "url": str(r.get("url") or probe),
                        "probe_url": probe,
                        "category": str(r.get("category") or "public"),
                    }
            ranked = sorted(dedup.values(), key=_route_rank)
            selected = _pick_stratified_routes(ranked, max(1, int(limit)))
            if selected:
                return selected, "dynamic_inventory"
        except Exception:
            pass

    return [
        {"url": r, "probe_url": r, "category": "fallback"}
        for r in FALLBACK_TOP_ROUTES[: max(1, int(limit))]
    ], "fixed_fallback"


async def _seed_auth(context, base_url: str, email: str, password: str, language_code: str = "en") -> bool:
    try:
        resp = await context.request.post(
            f"{base_url}/api/auth/login",
            data=json.dumps({"email": email, "password": password}),
            headers={"Content-Type": "application/json"},
            timeout=15_000,
        )
        if resp.status != 200:
            return False
        body = await resp.json()
        token = body.get("session_token") or body.get("token")
        if not token:
            return False
        page = await context.new_page()
        await page.goto(f"{base_url}/welcome", timeout=20_000, wait_until="domcontentloaded")
        locale_payload = _build_language_seed_payload(language_code)
        await page.evaluate(
            "({ t, locale }) => {"
            "localStorage.setItem('session_token', t);"
            "localStorage.setItem('auth_token', t);"
            "localStorage.setItem('app_theme', JSON.stringify(locale));"
            "localStorage.setItem('i18n_locale', locale.languageCode);"
            "localStorage.setItem('preferred_language', locale.languageCode);"
            "document.documentElement.setAttribute('lang', locale.languageCode);"
            "document.documentElement.setAttribute('dir', locale.languageCode === 'ar' ? 'rtl' : 'ltr');"
            "}",
            {"t": token, "locale": locale_payload},
        )
        await page.close()
        return True
    except Exception:
        return False


async def _probe_route(
    context,
    *,
    base_url: str,
    route: dict[str, Any],
    viewport_name: str,
    language_code: str,
    shot_dir: Path,
) -> dict[str, Any]:
    page = await context.new_page()
    probe_path = str(route.get("probe_url") or route.get("url") or "/")
    probe_path_with_lang = _append_language_query(probe_path, language_code)
    target_url = f"{base_url.rstrip('/')}{probe_path_with_lang}"
    screenshot_rel = ""
    status = "pass"
    reason = ""
    status_code = 0
    final_url = ""
    has_loader = False
    has_fatal = False
    blank_like = False
    text_len = 0
    body_height = 0

    nav_started = time.perf_counter()

    try:
        response = await page.goto(target_url, timeout=20_000, wait_until="domcontentloaded")
        status_code = int(response.status if response else 0)
        final_url = page.url

        if status_code >= 500:
            status = "fail"
            reason = f"http_{status_code}_error"

        if status == "pass":
            try:
                await page.wait_for_function(
                    """
                    (loaderSel) => {
                        const body = document.body;
                        if (!body) return false;
                        const textLen = (body.innerText || '').replace(/\s+/g, ' ').trim().length;
                        const height = body.scrollHeight || 0;
                        const hasLoader = Boolean(document.querySelector(loaderSel));
                        const bodyText = ((body && body.innerText) || '').toLowerCase();
                        const hasFatal = bodyText.includes('something went wrong') || bodyText.includes('page not found');
                        return !hasLoader && !hasFatal && (textLen > 40 || height > 160);
                    }
                    """,
                    arg=LOADER_SELECTORS_JS,
                    timeout=5_000,
                )
            except PWError:
                snap = await page.evaluate(
                    """
                    (loaderSel) => {
                        const body = document.body;
                        const textLen = body ? ((body.innerText || '').replace(/\s+/g, ' ').trim().length) : 0;
                        const height = body ? (body.scrollHeight || 0) : 0;
                        const hasLoader = Boolean(document.querySelector(loaderSel));
                        const bodyText = ((body && body.innerText) || '').toLowerCase();
                        const hasFatal = bodyText.includes('something went wrong') || bodyText.includes('page not found');
                        return { text_len: textLen, body_height: height, has_loader: hasLoader, has_fatal: hasFatal };
                    }
                    """,
                    LOADER_SELECTORS_JS,
                )
                text_len = int(snap.get("text_len") or 0)
                body_height = int(snap.get("body_height") or 0)
                has_loader = bool(snap.get("has_loader"))
                has_fatal = bool(snap.get("has_fatal"))
                blank_like = text_len < 40 and body_height < 120
                status = "fail"
                if has_loader:
                    reason = "loader_persisted_over_5s"
                elif has_fatal:
                    reason = "fatal_ui_surface_detected"
                elif blank_like:
                    reason = "blank_screen_over_5s"
                else:
                    reason = "render_not_ready_after_5s"

    except Exception as exc:
        status = "fail"
        reason = f"navigation_error: {str(exc)[:160]}"
        final_url = page.url or final_url

    try:
        if text_len == 0 and body_height == 0:
            snap2 = await page.evaluate(
                """
                () => {
                    const body = document.body;
                    return {
                        text_len: body ? ((body.innerText || '').replace(/\s+/g, ' ').trim().length) : 0,
                        body_height: body ? (body.scrollHeight || 0) : 0,
                    };
                }
                """
            )
            text_len = int(snap2.get("text_len") or text_len)
            body_height = int(snap2.get("body_height") or body_height)
    except Exception:
        pass

    route_slug = _slug_route(probe_path)
    file_name = f"{route_slug}__{viewport_name}__{language_code}.png"
    shot_path = shot_dir / file_name
    try:
        await page.screenshot(path=str(shot_path), full_page=False)
        screenshot_rel = str(shot_path.relative_to(ROOT))
    except Exception:
        screenshot_rel = ""

    await page.close()

    render_ms = int((time.perf_counter() - nav_started) * 1000)
    return {
        "route": str(route.get("url") or probe_path),
        "probe_url": probe_path,
        "viewport": viewport_name,
        "language": language_code,
        "status": status,
        "reason": reason or None,
        "screenshot": screenshot_rel or None,
        "status_code": status_code,
        "final_url": final_url,
        "text_len": text_len,
        "body_height": body_height,
        "loader_detected": has_loader,
        "blank_like": blank_like,
        "render_ms": render_ms,
    }


async def run(
    base_url: str,
    routes_limit: int,
    viewport_names: list[str],
    languages: list[str],
    exact_routes: list[str] | None = None,
) -> dict[str, Any]:
    run_id = f"wss_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    started = time.perf_counter()
    routes, source = await _load_top_routes(routes_limit, exact_routes=exact_routes)
    selected_viewports = [v for v in viewport_names if v in VIEWPORTS]
    if not selected_viewports:
        selected_viewports = ["mobile", "tablet", "desktop"]
    selected_languages = _normalize_languages(languages)

    shot_dir = ARTIFACT_BASE / run_id
    shot_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []
    email = "admin@realaicoach.app"
    password = "NewAdminPass2026!"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        for vp_name in selected_viewports:
            context = await browser.new_context(
                viewport=VIEWPORTS[vp_name],
                ignore_https_errors=True,
            )
            context.set_default_timeout(20_000)
            for lang_code in selected_languages:
                await _seed_auth(context, base_url, email, password, language_code=lang_code)
                for route in routes:
                    artifacts.append(
                        await _probe_route(
                            context,
                            base_url=base_url,
                            route=route,
                            viewport_name=vp_name,
                            language_code=lang_code,
                            shot_dir=shot_dir,
                        )
                    )

            await context.close()

        await browser.close()

    total = len(artifacts)
    failed = [a for a in artifacts if str(a.get("status") or "").lower() != "pass"]
    matrix_summary: dict[str, dict[str, int]] = {}
    matrix_summary_by_language: dict[str, dict[str, dict[str, int]]] = {}
    for vp in selected_viewports:
        vp_rows = [a for a in artifacts if a.get("viewport") == vp]
        vp_fail = sum(1 for a in vp_rows if str(a.get("status") or "").lower() != "pass")
        matrix_summary[vp] = {
            "pass": max(0, len(vp_rows) - vp_fail),
            "fail": vp_fail,
            "total": len(vp_rows),
        }
        matrix_summary_by_language[vp] = {}
        for lang_code in selected_languages:
            lane_rows = [
                a
                for a in vp_rows
                if str(a.get("language") or "").lower() == lang_code
            ]
            lane_fail = sum(1 for a in lane_rows if str(a.get("status") or "").lower() != "pass")
            matrix_summary_by_language[vp][lang_code] = {
                "pass": max(0, len(lane_rows) - lane_fail),
                "fail": lane_fail,
                "total": len(lane_rows),
            }

    return {
        "run_id": run_id,
        "generated_at": _now_iso(),
        "base_url": base_url,
        "route_source": source,
        "routes_tested": [str(r.get("url") or r.get("probe_url") or "") for r in routes],
        "viewports": selected_viewports,
        "languages": selected_languages,
        "total_checks": total,
        "failed_checks": len(failed),
        "white_screen_gate_passed": len(failed) == 0 and total > 0,
        "failure_reason": None if len(failed) == 0 else "blank_loader_or_fatal_surface_detected_over_5s",
        "matrix_summary": matrix_summary,
        "matrix_summary_by_language": matrix_summary_by_language,
        "strict_matrix_dimensions": {
            "viewports": len(selected_viewports),
            "languages": len(selected_languages),
            "routes": len(routes),
            "expected_checks": len(selected_viewports) * len(selected_languages) * len(routes),
        },
        "artifacts": artifacts,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _prune_artifact_runs(keep: int = 10) -> None:
    """Retention: keep only the newest `keep` run dirs to prevent disk exhaustion."""
    try:
        runs = sorted(d for d in ARTIFACT_BASE.iterdir() if d.is_dir())
        for old in runs[:-keep] if len(runs) > keep else []:
            shutil.rmtree(old, ignore_errors=True)
    except FileNotFoundError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="GTEC C5 white-screen sentry")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--routes-limit", type=int, default=48)
    parser.add_argument("--viewports", default="mobile_compact,mobile,tablet,laptop,desktop,webwide")
    parser.add_argument("--languages", default="en")
    parser.add_argument("--exact-routes", default="")
    parser.add_argument(
        "--output-json",
        default=str(REPORT_DIR / "gtec_white_screen_sentry_latest.json"),
    )
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args()

    viewports = [v.strip() for v in str(args.viewports or "").split(",") if v.strip()]
    languages = _normalize_languages([v.strip() for v in str(args.languages or "").split(",") if v.strip()])
    exact_routes = [r.strip() for r in str(args.exact_routes or "").split(",") if r.strip()]
    base_url = str(args.base_url or "").rstrip("/")
    if not base_url:
        print("[gtec-white-screen-sentry] missing --base-url", file=sys.stderr)
        raise SystemExit(2)

    out_path = Path(str(args.output_json))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any]
    try:
        payload = asyncio.run(
            run(
                base_url,
                max(1, int(args.routes_limit)),
                viewports,
                languages,
                exact_routes=exact_routes,
            )
        )
    except Exception as exc:
        payload = {
            "run_id": f"wss_error_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "generated_at": _now_iso(),
            "base_url": base_url,
            "route_source": "error",
            "routes_tested": [],
            "viewports": viewports,
            "languages": languages,
            "total_checks": 0,
            "failed_checks": 0,
            "white_screen_gate_passed": False,
            "failure_reason": f"sentry_runtime_error: {str(exc)[:200]}",
            "matrix_summary": {},
            "artifacts": [],
            "duration_ms": 0,
        }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    _prune_artifact_runs(keep=10)

    if args.strict_exit and not bool(payload.get("white_screen_gate_passed")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
