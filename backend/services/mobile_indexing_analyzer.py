"""Mobile-First Indexing Analyzer — Compares mobile vs desktop crawler views"""
import asyncio
import time
import logging
from datetime import datetime, timezone

import httpx
from utils.http_tls import get_httpx_verify

logger = logging.getLogger(__name__)

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
DESKTOP_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

PAGES_TO_CHECK = [
    {"path": "/", "label": "Landing Page"},
    {"path": "/auth/login", "label": "Login"},
    {"path": "/pricing", "label": "Pricing"},
    {"path": "/features", "label": "Features"},
    {"path": "/about", "label": "About"},
    {"path": "/blog", "label": "Blog"},
]


async def _fetch_page(client: httpx.AsyncClient, url: str, ua: str):
    headers = {"User-Agent": ua}
    start = time.monotonic()
    resp = await client.get(url, headers=headers)
    elapsed = round(time.monotonic() - start, 3)
    content = resp.text[:15000]
    return {
        "status": resp.status_code,
        "load_time": elapsed,
        "size_bytes": len(resp.content),
        "has_viewport": 'name="viewport"' in content or "viewport" in content,
        "has_meta_description": 'name="description"' in content,
        "has_og_tags": 'property="og:' in content,
        "has_title": "<title>" in content.lower(),
        "has_structured_data": "application/ld+json" in content,
        "has_canonical": 'rel="canonical"' in content,
        "content_length": len(content),
    }


async def analyze_mobile_indexing(base_url: str) -> dict:
    """Compare mobile vs desktop views for all pages"""
    results = []
    issues = []
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=get_httpx_verify()) as client:
        sem = asyncio.Semaphore(3)

        async def check_page(page):
            async with sem:
                url = f"{base_url}{page['path']}"
                try:
                    mobile = await _fetch_page(client, url, MOBILE_UA)
                    desktop = await _fetch_page(client, url, DESKTOP_UA)

                    page_issues = []
                    if mobile["status"] != desktop["status"]:
                        page_issues.append(f"Status mismatch: mobile={mobile['status']}, desktop={desktop['status']}")
                    if not mobile["has_viewport"]:
                        page_issues.append("Missing viewport meta tag for mobile")
                    if not mobile["has_meta_description"]:
                        page_issues.append("Missing meta description")
                    if not mobile["has_title"]:
                        page_issues.append("Missing <title> tag")
                    size_ratio = mobile["size_bytes"] / max(desktop["size_bytes"], 1)
                    if size_ratio > 1.5:
                        page_issues.append(f"Mobile page is {size_ratio:.1f}x larger than desktop")
                    if mobile["load_time"] > 3.0:
                        page_issues.append(f"Mobile load time too high: {mobile['load_time']}s")

                    score = 100
                    score -= len(page_issues) * 12
                    score = max(0, score)

                    return {
                        "path": page["path"],
                        "label": page["label"],
                        "mobile": mobile,
                        "desktop": desktop,
                        "issues": page_issues,
                        "score": score,
                        "parity": len(page_issues) == 0,
                    }
                except Exception as e:
                    logger.error(f"Mobile indexing check failed for {url}: {e}")
                    return {
                        "path": page["path"],
                        "label": page["label"],
                        "error": str(e)[:200],
                        "score": 0,
                        "parity": False,
                        "issues": [str(e)[:200]],
                    }

        tasks = [check_page(p) for p in PAGES_TO_CHECK]
        results = await asyncio.gather(*tasks)

    for r in results:
        issues.extend([{"page": r["label"], "issue": i} for i in r.get("issues", [])])

    successful = [r for r in results if "error" not in r]
    avg_score = round(sum(r["score"] for r in successful) / max(len(successful), 1))
    parity_count = sum(1 for r in successful if r["parity"])

    return {
        "analysis_id": f"mfi_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration": round(time.monotonic() - start, 2),
        "overall_score": avg_score,
        "pages_checked": len(results),
        "pages_with_parity": parity_count,
        "total_issues": len(issues),
        "issues": issues,
        "page_results": results,
        "recommendations": _generate_recommendations(results, issues),
    }


def _generate_recommendations(results, issues):
    recs = []
    has_viewport_issue = any("viewport" in i["issue"].lower() for i in issues)
    has_size_issue = any("larger" in i["issue"].lower() for i in issues)
    has_speed_issue = any("load time" in i["issue"].lower() for i in issues)
    has_meta_issue = any("meta description" in i["issue"].lower() for i in issues)

    if has_viewport_issue:
        recs.append({
            "priority": "critical",
            "category": "Mobile Viewport",
            "action": "Add <meta name='viewport' content='width=device-width, initial-scale=1'> to all pages",
        })
    if has_size_issue:
        recs.append({
            "priority": "high",
            "category": "Page Size",
            "action": "Optimize mobile page size. Use responsive images, lazy loading, and code splitting.",
        })
    if has_speed_issue:
        recs.append({
            "priority": "high",
            "category": "Load Speed",
            "action": "Reduce mobile page load time below 3s. Enable compression and minimize render-blocking resources.",
        })
    if has_meta_issue:
        recs.append({
            "priority": "medium",
            "category": "SEO Meta",
            "action": "Add meta descriptions to all pages for better search snippets.",
        })
    if not issues:
        recs.append({
            "priority": "info",
            "category": "Status",
            "action": "All pages pass mobile-first indexing checks. Continue monitoring.",
        })
    return recs
