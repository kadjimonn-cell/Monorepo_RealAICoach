"""Global Performance Analyzer — Simulates multi-region page load analysis"""
import time
import logging
from datetime import datetime, timezone

import httpx
from utils.http_tls import get_httpx_verify

logger = logging.getLogger(__name__)

SIMULATED_REGIONS = [
    {"id": "us-east", "name": "US East (Virginia)", "flag": "US", "latency_offset": 0},
    {"id": "us-west", "name": "US West (Oregon)", "flag": "US", "latency_offset": 0.05},
    {"id": "eu-west", "name": "Europe (Ireland)", "flag": "EU", "latency_offset": 0.12},
    {"id": "eu-central", "name": "Europe (Frankfurt)", "flag": "EU", "latency_offset": 0.15},
    {"id": "ap-south", "name": "Asia Pacific (Mumbai)", "flag": "IN", "latency_offset": 0.25},
    {"id": "ap-east", "name": "Asia Pacific (Tokyo)", "flag": "JP", "latency_offset": 0.20},
    {"id": "af-south", "name": "Africa (Cape Town)", "flag": "ZA", "latency_offset": 0.30},
    {"id": "sa-east", "name": "South America (Sao Paulo)", "flag": "BR", "latency_offset": 0.22},
]

CDN_RECOMMENDATIONS = [
    {
        "provider": "Cloudflare",
        "tier": "Free / Pro",
        "features": ["Global CDN", "DDoS Protection", "SSL", "Edge Caching", "HTTP/3"],
        "estimated_improvement": "40-60%",
        "setup_complexity": "Low",
    },
    {
        "provider": "AWS CloudFront",
        "tier": "Pay-as-you-go",
        "features": ["Global Edge Locations", "Lambda@Edge", "Origin Shield", "Real-time Logs"],
        "estimated_improvement": "35-55%",
        "setup_complexity": "Medium",
    },
    {
        "provider": "Fastly",
        "tier": "Enterprise",
        "features": ["Instant Purge", "Edge Computing", "Real-time Analytics", "DDoS"],
        "estimated_improvement": "45-65%",
        "setup_complexity": "Medium",
    },
]

PAGES_TO_TEST = [
    {"path": "/", "label": "Landing Page"},
    {"path": "/auth/login", "label": "Login"},
    {"path": "/pricing", "label": "Pricing"},
]


async def analyze_global_performance(base_url: str) -> dict:
    """Analyze page load times from simulated global regions"""
    start = time.monotonic()
    region_results = []

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=get_httpx_verify()) as client:
        for region in SIMULATED_REGIONS:
            page_results = []
            for page in PAGES_TO_TEST:
                url = f"{base_url}{page['path']}"
                try:
                    t0 = time.monotonic()
                    resp = await client.get(url)
                    base_time = time.monotonic() - t0

                    simulated_time = round(base_time + region["latency_offset"], 3)
                    size_kb = round(len(resp.content) / 1024, 1)

                    rating = "fast"
                    if simulated_time > 3.0:
                        rating = "slow"
                    elif simulated_time > 1.5:
                        rating = "moderate"

                    page_results.append({
                        "page": page["label"],
                        "path": page["path"],
                        "load_time": simulated_time,
                        "size_kb": size_kb,
                        "status": resp.status_code,
                        "rating": rating,
                    })
                except Exception as e:
                    page_results.append({
                        "page": page["label"],
                        "path": page["path"],
                        "load_time": None,
                        "error": str(e)[:100],
                        "rating": "error",
                    })

            avg_time = round(
                sum(p["load_time"] for p in page_results if p.get("load_time"))
                / max(sum(1 for p in page_results if p.get("load_time")), 1), 3
            )
            slow_count = sum(1 for p in page_results if p.get("rating") == "slow")

            region_results.append({
                "region_id": region["id"],
                "region_name": region["name"],
                "flag": region["flag"],
                "avg_load_time": avg_time,
                "slow_pages": slow_count,
                "pages": page_results,
                "status": "slow" if avg_time > 3.0 else "moderate" if avg_time > 1.5 else "fast",
            })

    all_times = [r["avg_load_time"] for r in region_results if r["avg_load_time"]]
    global_avg = round(sum(all_times) / max(len(all_times), 1), 3)
    fastest = min(region_results, key=lambda r: r["avg_load_time"]) if region_results else None
    slowest = max(region_results, key=lambda r: r["avg_load_time"]) if region_results else None

    has_cdn = False
    cdn_status = {
        "detected": False,
        "provider": None,
        "recommendation": "No CDN detected. Consider adding one to improve global load times by 40-60%.",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=get_httpx_verify()) as client:
            resp = await client.get(base_url)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            if "cf-ray" in headers or "cf-cache-status" in headers:
                has_cdn = True
                cdn_status = {"detected": True, "provider": "Cloudflare", "recommendation": "Cloudflare CDN detected. Ensure caching rules are optimized."}
            elif "x-amz-cf-id" in headers or "x-cache" in headers:
                has_cdn = True
                cdn_status = {"detected": True, "provider": "AWS CloudFront", "recommendation": "CloudFront CDN detected. Enable origin shield for better cache hit rates."}
            elif "fastly" in headers.get("server", "").lower() or "x-served-by" in headers:
                has_cdn = True
                cdn_status = {"detected": True, "provider": "Fastly", "recommendation": "Fastly CDN detected. Enable instant purge for dynamic content."}
    except Exception:
        pass

    optimization_tips = []
    if global_avg > 2.0:
        optimization_tips.append({"tip": "Enable HTTP/2 or HTTP/3 for multiplexed connections", "impact": "high"})
    if not has_cdn:
        optimization_tips.append({"tip": "Deploy a CDN (Cloudflare recommended) for edge caching", "impact": "critical"})
    if any(r["slow_pages"] > 0 for r in region_results):
        optimization_tips.append({"tip": "Optimize images with WebP/AVIF and implement lazy loading", "impact": "high"})
        optimization_tips.append({"tip": "Enable Brotli/Gzip compression on all responses", "impact": "medium"})
    optimization_tips.append({"tip": "Use preconnect/dns-prefetch hints for third-party domains", "impact": "medium"})
    optimization_tips.append({"tip": "Implement cache-first strategy for static assets (1yr max-age)", "impact": "medium"})

    return {
        "analysis_id": f"gpa_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration": round(time.monotonic() - start, 2),
        "global_avg_load_time": global_avg,
        "regions_tested": len(region_results),
        "fastest_region": {"name": fastest["region_name"], "time": fastest["avg_load_time"]} if fastest else None,
        "slowest_region": {"name": slowest["region_name"], "time": slowest["avg_load_time"]} if slowest else None,
        "cdn_status": cdn_status,
        "cdn_recommendations": CDN_RECOMMENDATIONS,
        "region_results": region_results,
        "optimization_tips": optimization_tips,
    }
