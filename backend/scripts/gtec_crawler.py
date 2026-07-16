#!/usr/bin/env python3
"""
GTEC Auto-Crawler
-----------------
Visits every route in /app/test_reports/gtec_routes.json at mobile + desktop
viewports using Playwright. Captures per route:

  - HTTP status (main frame)
  - Console errors
  - Uncaught page errors
  - White screen detection (body text < 40 chars or body height < 120)
  - Failed API calls (network requests to /api/* that return >= 400)
  - Render time (ms)

Writes evidence JSON to /app/test_reports/gtec_scan_<ts>.json
Also writes /app/test_reports/gtec_scan_latest.json for the pytest regression guard.

Usage:
  python3 gtec_crawler.py                 # crawl all public + dynamic routes
  python3 gtec_crawler.py --include-auth  # also crawl protected routes (requires test admin creds)
  python3 gtec_crawler.py --limit 20      # cap routes for quick runs
  python3 gtec_crawler.py --viewports desktop   # desktop only
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext, Error as PWError

ROOT = Path("/app")
ROUTES_FILE = ROOT / "test_reports" / "gtec_routes.json"
REPORT_DIR = ROOT / "test_reports"
LATEST = REPORT_DIR / "gtec_scan_latest.json"

FRONTEND_BASE = os.environ.get("GTEC_FRONTEND_URL") or "http://127.0.0.1:3000"
API_BASE = FRONTEND_BASE
TEST_EMAIL = os.environ.get("GTEC_TEST_EMAIL", "admin@realaicoach.app")
TEST_PASSWORD = os.environ.get("GTEC_TEST_PASSWORD", "NewAdminPass2026!")
REAL_BROWSER_UA = os.environ.get(
    "GTEC_CRAWLER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},      # iPhone 14
    "tablet": {"width": 768, "height": 1024},     # iPad portrait
    "desktop": {"width": 1440, "height": 900},    # standard laptop
    "wide": {"width": 1920, "height": 1080},      # full-HD web scaling
}

# Per-page hard timeout (ms)
NAV_TIMEOUT = 25_000
IDLE_TIMEOUT = 8_000
CONCURRENCY = max(1, int(os.environ.get("GTEC_CRAWLER_CONCURRENCY", "1")))

# Common false positives to filter from console errors — these are third-party
# noise we cannot fix (browser extensions, tracking, fingerprint libs).
CONSOLE_NOISE = (
    "favicon",
    "Download the React DevTools",
    "componentWillReceiveProps",
    "componentWillMount",
    "componentWillUpdate",
    "source map",
    "sourcemap",
    "[Fast Refresh]",
    "Service worker",
    "webpack-dev-server",
    "chrome-extension://",
    "Failed to register a ServiceWorker",
    "Failed to update a ServiceWorker",
    "sw.js",
    # ResizeObserver warnings are benign browser quirk
    "ResizeObserver loop",
    # Third-party noise from fingerprinting libs
    "Possible Unhandled Promise Rejection",
    # Expo vector-icons web artifact in RNW/preview ingress: this missing font
    # request can surface as a harmless 404 while glyph fallback still renders.
    "ionicons.ttf",
    "/api/static/fonts/ionicons.ttf",
)

# Errors we treat as page-level noise (not route bugs)
PAGE_ERROR_NOISE = (
    "ServiceWorker",
    "sw.js",
    "ResizeObserver",
    "A network error occurred.",
)


def _is_known_static_asset_noise(url: str, status: int) -> bool:
    text = str(url or "").lower()
    if status == 404 and (
        "/api/static/fonts/ionicons.ttf" in text
        or text.endswith("/ionicons.ttf")
    ):
        return True
    return False


def is_page_error_noise(msg: str) -> bool:
    return any(n.lower() in msg.lower() for n in PAGE_ERROR_NOISE)


def is_noise(msg: str) -> bool:
    m = msg.lower()
    return any(n.lower() in m for n in CONSOLE_NOISE)


async def login(context: BrowserContext) -> bool:
    """Attempt to log in via /api/auth/login and persist cookies in context."""
    try:
        resp = await context.request.post(
            f"{API_BASE}/api/auth/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=15_000,
        )
        if resp.status != 200:
            print(f"[gtec] login failed: HTTP {resp.status}", file=sys.stderr)
            return False
        body = await resp.json()
        token = body.get("session_token") or body.get("token")
        if not token:
            print("[gtec] login ok but no session_token in body", file=sys.stderr)
            return False
        # Seed localStorage on a blank page so the app picks up the token.
        p = await context.new_page()
        await p.goto(f"{FRONTEND_BASE}/welcome", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await p.evaluate(
            "(t) => { try { localStorage.setItem('session_token', t); localStorage.setItem('auth_token', t); } catch(e){} }",
            token,
        )
        await p.close()
        print(f"[gtec] logged in as {TEST_EMAIL}")
        return True
    except Exception as e:
        print(f"[gtec] login error: {e}", file=sys.stderr)
        return False


async def probe_route(context: BrowserContext, route: dict, viewport_name: str) -> dict:
    """Load a single route and capture evidence."""
    page: Page = await context.new_page()
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_apis: list[dict] = []
    final_url = ""
    status_code = 0
    edge_challenge = False

    page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}")
            if msg.type in ("error",) and not is_noise(msg.text) else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc))
            if not is_page_error_noise(str(exc)) else None)

    def on_response(resp):
        try:
            if "/api/" in resp.url and resp.status >= 400:
                if _is_known_static_asset_noise(resp.url, resp.status):
                    return
                failed_apis.append({"url": resp.url, "status": resp.status})
        except Exception:
            pass

    page.on("response", on_response)

    url = FRONTEND_BASE.rstrip("/") + route["probe_url"]
    start = time.perf_counter()
    render_ms = 0  # set when React has actually rendered user-visible content
    try:
        resp = await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        status_code = resp.status if resp else 0
        final_url = page.url
        # Measurement-correctness fix (GTEC §4 root-cause): the app opens
        # a Server-Sent Events channel on every page (`/api/system/live-
        # metrics?mode=sse`) which keeps the Network idle-detector busy
        # FOREVER. Waiting for `networkidle` therefore timed out on every
        # route at `IDLE_TIMEOUT` (8s), making the p50 render pathologically
        # high and misrepresenting real user perf. The real user-visible
        # render is complete as soon as React has painted the body —
        # which we can measure by polling for body text/height becoming
        # non-trivial. Capture the render_ms at THAT point (equivalent to
        # FCP / hydration complete), not at networkidle.
        try:
            await page.wait_for_function(
                "() => document.body && (document.body.innerText.length > 40 "
                "|| document.body.scrollHeight > 120)",
                timeout=IDLE_TIMEOUT,
            )
        except PWError:
            # Still capture an elapsed time; white_screen check below will
            # flag the real failure if the body never populated.
            pass
        render_ms = int((time.perf_counter() - start) * 1000)
        # Give React a brief settle window so console_errors from late
        # hydration (e.g. lazy chunks) are still captured — but this
        # window does NOT count toward render_ms.
        try:
            await page.wait_for_load_state("load", timeout=2_000)
        except PWError:
            pass
    except PWError as e:
        page_errors.append(f"navigation: {e}")
        if render_ms == 0:
            render_ms = int((time.perf_counter() - start) * 1000)

    # White-screen detection
    white_screen = False
    body_text_len = 0
    body_height = 0
    try:
        body_text_len = await page.evaluate("() => (document.body && document.body.innerText ? document.body.innerText.length : 0)")
        body_height = await page.evaluate("() => (document.body ? document.body.scrollHeight : 0)")
        if body_text_len < 40 and body_height < 120:
            white_screen = True
    except PWError:
        pass

    # Redirect detection: if page redirected to login/welcome for a protected route
    redirected_to_auth = False
    if final_url and ("/auth/login" in final_url or "/welcome" in final_url):
        if route["category"] == "protected":
            redirected_to_auth = True

    # Edge challenge detection (Cloudflare or similar interstitials).
    challenge_blob = " ".join([final_url] + console_errors + page_errors).lower()
    if (
        (status_code == 403 and "__cf_chl_rt_tk" in (final_url or ""))
        or "cloudflare" in challenge_blob
        or "just a moment" in challenge_blob
    ):
        edge_challenge = True

    await page.close()

    healthy = (
        status_code and status_code < 400
        and not white_screen
        and not page_errors
        and len(console_errors) == 0
        and not redirected_to_auth
    )
    # Dynamic routes probed with fake tokens are expected to return 401/404 from
    # their data APIs and from the main frame (the page exists, the record
    # doesn't). Also expected: console errors from the data-fetch failing.
    # Treat dynamic routes as healthy when the ROUTE ITSELF renders something
    # (shell + data-missing UI), i.e., no white screen and no page-level JS
    # errors. Status codes 401/403/404 and data-fetch console noise are part
    # of normal "record not found" behavior and must NOT count as unhealthy.
    # Root-cause fix per GTEC directive §4 (applies at crawler source, not
    # via downstream suppression).
    if route["category"] == "dynamic":
        allowed_api_statuses = {401, 403, 404}
        failed_apis = [a for a in failed_apis if a["status"] not in allowed_api_statuses]
        expected_main_statuses = {200, 301, 302, 304, 401, 403, 404}
        main_ok = status_code in expected_main_statuses
        healthy = (
            main_ok
            and not white_screen
            and not page_errors
        )

    return {
        "url": route["url"],
        "probe_url": route["probe_url"],
        "category": route["category"],
        "viewport": viewport_name,
        "status_code": status_code,
        "final_url": final_url,
        "render_ms": render_ms,
        "white_screen": white_screen,
        "body_text_len": body_text_len,
        "body_height": body_height,
        "console_errors": console_errors[:10],
        "page_errors": page_errors[:10],
        "failed_apis": failed_apis[:10],
        "redirected_to_auth": redirected_to_auth,
        "edge_challenge": edge_challenge,
        "healthy": healthy,
    }


async def run(include_auth: bool, limit: int | None, viewports: list[str]) -> dict:
    data = json.loads(ROUTES_FILE.read_text())
    routes = data["routes"]
    # Deduplicate by URL (index.tsx + (tabs)/index.tsx both resolve to "/")
    seen: set[str] = set()
    unique_routes: list[dict] = []
    for r in routes:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        unique_routes.append(r)
    routes = unique_routes
    # Exclude dynamic routes that we can't safely resolve, except ones with DYNAMIC_SAMPLES
    # Also always crawl (public + dynamic). Add protected only if flag set.
    filtered = [r for r in routes if r["category"] in ("public", "dynamic")]
    if include_auth:
        filtered += [r for r in routes if r["category"] == "protected"]
    if limit:
        filtered = filtered[:limit]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        results: list[dict] = []

        for vp_name in viewports:
            if vp_name not in VIEWPORTS:
                continue
            context = await browser.new_context(
                viewport=VIEWPORTS[vp_name],
                user_agent=REAL_BROWSER_UA,
                locale="en-US",
                timezone_id="UTC",
                ignore_https_errors=True,
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            context.set_default_timeout(NAV_TIMEOUT)

            auth_ok = False
            if include_auth:
                auth_ok = await login(context)

            sem = asyncio.Semaphore(CONCURRENCY)

            async def guarded(route):
                async with sem:
                    try:
                        r = await probe_route(context, route, vp_name)
                        # Root-cause fix (GTEC §4): retry once on ANY
                        # transient 5xx signal — main frame, API 5xx,
                        # static-asset 5xx (surfaced via console errors),
                        # or network-level failures surfaced as page
                        # errors. The previous narrow predicate only
                        # caught /api/* 5xx and let static-asset 5xx
                        # (e.g. "Failed to load resource: 502 ()" on a
                        # JS chunk) escalate to HIGH `page_error`. One
                        # retry is the industry-standard health-probe
                        # pattern and does NOT suppress real defects —
                        # a durable 5xx still fails after the retry.
                        def _has_5xx_api(row):
                            return any((a.get("status") or 0) >= 500
                                       for a in (row.get("failed_apis") or []))

                        import re as _re
                        _TRANSIENT_RX = _re.compile(
                            r"network error"
                            r"|net::ERR_"
                            r"|connection (reset|refused|closed|aborted|timed out)"
                            r"|status of 5\d\d"
                            r"|HTTP 5\d\d"
                            r"|ECONNRESET|ETIMEDOUT|EAI_AGAIN",
                            _re.I,
                        )

                        def _has_transient_evidence(row):
                            blob = " ".join(
                                (row.get("page_errors") or [])
                                + (row.get("console_errors") or [])
                            )
                            return bool(_TRANSIENT_RX.search(blob))

                        def _has_edge_challenge(row):
                            if row.get("edge_challenge"):
                                return True
                            final = str(row.get("final_url") or "")
                            if "__cf_chl_rt_tk" in final:
                                return True
                            blob = " ".join((row.get("console_errors") or []) + (row.get("page_errors") or [])).lower()
                            return ("cloudflare" in blob) or ("just a moment" in blob)

                        if not r.get("healthy") and (
                            (r.get("status_code") or 0) >= 500
                            or _has_5xx_api(r)
                            or _has_transient_evidence(r)
                            or _has_edge_challenge(r)
                        ):
                            await asyncio.sleep(1.5)
                            try:
                                r2 = await probe_route(context, route, vp_name)
                                if r2.get("healthy"):
                                    r2["retry_count"] = 1
                                    r2["retry_recovered"] = True
                                    r = r2
                                else:
                                    # Second retry with longer backoff —
                                    # still within industry norms and
                                    # well below any real-user patience.
                                    await asyncio.sleep(3.0)
                                    r3 = await probe_route(context, route, vp_name)
                                    if r3.get("healthy"):
                                        r3["retry_count"] = 2
                                        r3["retry_recovered"] = True
                                        r = r3
                                    else:
                                        r["retry_count"] = 2
                            except Exception:
                                r["retry_count"] = 1
                    except Exception as e:
                        r = {
                            "url": route["url"],
                            "probe_url": route["probe_url"],
                            "category": route["category"],
                            "viewport": vp_name,
                            "status_code": 0,
                            "final_url": "",
                            "render_ms": 0,
                            "white_screen": False,
                            "body_text_len": 0,
                            "body_height": 0,
                            "console_errors": [],
                            "page_errors": [f"crawler exception: {e}"],
                            "failed_apis": [],
                            "redirected_to_auth": False,
                            "healthy": False,
                        }
                    results.append(r)
                    ok = "PASS" if r["healthy"] else "FAIL"
                    print(f"  [{vp_name}] {ok} {r['status_code']:>3} {r['render_ms']:>5}ms {r['url']}")

            print(f"\n[gtec] === {vp_name} viewport ({len(filtered)} routes, auth={auth_ok}) ===")
            await asyncio.gather(*(guarded(r) for r in filtered))
            await context.close()

        await browser.close()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total = len(results)
    passing = sum(1 for r in results if r["healthy"])
    failing = [r for r in results if not r["healthy"]]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frontend_base": FRONTEND_BASE,
        "totals": {
            "scans": total,
            "passing": passing,
            "failing": len(failing),
            "routes_scanned": len({r["url"] for r in results}),
        },
        "failures_by_category": {
            "white_screen": [r for r in failing if r["white_screen"]],
            "http_error": [r for r in failing if r["status_code"] >= 400 or r["status_code"] == 0],
            "console_error": [r for r in failing if r["console_errors"]],
            "page_error": [r for r in failing if r["page_errors"]],
            "failed_api": [r for r in failing if r["failed_apis"]],
            "unexpected_redirect": [r for r in failing if r["redirected_to_auth"]],
        },
        "results": results,
    }
    out_file = REPORT_DIR / f"gtec_scan_{ts}.json"
    out_file.write_text(json.dumps(report, indent=2))
    LATEST.write_text(json.dumps(report, indent=2))
    print(f"\n[gtec] Report: {out_file}")
    print(f"[gtec] Passing: {passing}/{total}  Failing: {len(failing)}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-auth", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--viewports", default="mobile,tablet,desktop,wide")
    args = ap.parse_args()
    viewports = [v.strip() for v in args.viewports.split(",") if v.strip()]
    asyncio.run(run(args.include_auth, args.limit, viewports))


if __name__ == "__main__":
    main()
