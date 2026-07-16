"""Responsiveness Audit Service — Analyzes CSS/layout for responsive design issues across viewports."""
import asyncio
import time
import logging
import re
from datetime import datetime, timezone

import httpx
from utils.http_tls import get_httpx_verify

logger = logging.getLogger(__name__)

VIEWPORTS = [
    {"name": "Mobile S (320px)", "width": 320, "category": "mobile"},
    {"name": "Mobile M (375px)", "width": 375, "category": "mobile"},
    {"name": "Mobile L (425px)", "width": 425, "category": "mobile"},
    {"name": "Tablet (768px)", "width": 768, "category": "tablet"},
    {"name": "Laptop (1024px)", "width": 1024, "category": "desktop"},
    {"name": "Desktop (1440px)", "width": 1440, "category": "desktop"},
    {"name": "4K / Ultra-wide (2560px)", "width": 2560, "category": "ultrawide"},
]

PAGES_TO_AUDIT = [
    {"path": "/", "label": "Landing Page"},
    {"path": "/auth/login", "label": "Login"},
    {"path": "/pricing", "label": "Pricing"},
    {"path": "/features", "label": "Features"},
    {"path": "/about", "label": "About"},
]

CSS_PATTERNS = {
    "fixed_width": {
        "pattern": r"width:\s*\d{3,4}px",
        "issue": "Fixed pixel width may cause overflow on small screens",
        "severity": "high",
    },
    "no_max_width": {
        "pattern": r"(?<!max-)width:\s*100%(?!.*max-width)",
        "issue": "Full width without max-width constraint may stretch on ultra-wide",
        "severity": "medium",
    },
    "small_touch_target": {
        "pattern": r"(padding|height|min-height):\s*(1[0-9]|[0-9])px",
        "issue": "Touch target may be too small (< 44px recommended)",
        "severity": "high",
    },
    "overflow_hidden": {
        "pattern": r"overflow:\s*hidden",
        "issue": "overflow:hidden may clip content on small viewports",
        "severity": "low",
    },
    "small_font": {
        "pattern": r"font-size:\s*([0-9]|1[01])px",
        "issue": "Font size below 12px is difficult to read on mobile",
        "severity": "medium",
    },
}

RESPONSIVE_FEATURES = {
    "viewport_meta": {"pattern": 'name="viewport"', "required": True, "description": "Viewport meta tag"},
    "media_queries": {"pattern": "@media", "required": True, "description": "Responsive media queries"},
    "flex_layout": {"pattern": "display:flex", "required": False, "description": "Flexbox layout"},
    "grid_layout": {"pattern": "display:grid", "required": False, "description": "CSS Grid layout"},
    "responsive_images": {"pattern": "max-width:100%", "required": False, "description": "Responsive images"},
}


async def run_responsiveness_audit(base_url: str) -> dict:
    """Run comprehensive responsiveness audit across all viewports and pages"""
    start = time.monotonic()
    page_results = []
    all_issues = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=get_httpx_verify()) as client:
        sem = asyncio.Semaphore(3)

        async def audit_page(page):
            async with sem:
                url = f"{base_url}{page['path']}"
                try:
                    resp = await client.get(url)
                    content = resp.text[:50000]
                    resp.elapsed.total_seconds() if hasattr(resp, 'elapsed') else 0

                    issues = []
                    features = {}

                    # Check responsive features
                    for feat_id, feat in RESPONSIVE_FEATURES.items():
                        found = feat["pattern"].lower() in content.lower()
                        features[feat_id] = {
                            "name": feat["description"],
                            "present": found,
                            "required": feat["required"],
                        }
                        if feat["required"] and not found:
                            issues.append({
                                "type": "missing_feature",
                                "severity": "critical",
                                "description": f"Missing required: {feat['description']}",
                                "viewport": "all",
                            })

                    # Check CSS patterns
                    for pattern_id, pattern_config in CSS_PATTERNS.items():
                        matches = re.findall(pattern_config["pattern"], content, re.IGNORECASE)
                        if matches and len(matches) > 2:
                            issues.append({
                                "type": pattern_id,
                                "severity": pattern_config["severity"],
                                "description": f"{pattern_config['issue']} ({len(matches)} occurrences)",
                                "viewport": "varies",
                            })

                    # Viewport-specific checks
                    viewport_scores = {}
                    for vp in VIEWPORTS:
                        vp_issues = []
                        vp_score = 100

                        if vp["width"] < 768:
                            if "width:" in content and "px" in content:
                                fixed_widths = re.findall(r'width:\s*(\d+)px', content)
                                large_fixed = [w for w in fixed_widths if int(w) > vp["width"]]
                                if large_fixed:
                                    vp_issues.append(f"Elements wider than viewport ({len(large_fixed)} found)")
                                    vp_score -= 15

                        if vp["width"] > 2000:
                            if "max-width" not in content.lower():
                                vp_issues.append("No max-width constraints for ultra-wide displays")
                                vp_score -= 10

                        vp_score = max(0, vp_score - len(issues) * 5)
                        viewport_scores[vp["name"]] = {
                            "score": max(0, vp_score),
                            "category": vp["category"],
                            "issues": vp_issues,
                            "width": vp["width"],
                        }

                    page_score = round(sum(v["score"] for v in viewport_scores.values()) / len(viewport_scores))

                    return {
                        "path": page["path"],
                        "label": page["label"],
                        "score": page_score,
                        "issues": issues,
                        "features": features,
                        "viewport_scores": viewport_scores,
                        "content_size_kb": round(len(resp.content) / 1024, 1),
                    }
                except Exception as e:
                    return {
                        "path": page["path"],
                        "label": page["label"],
                        "score": 0,
                        "error": str(e)[:200],
                        "issues": [{"type": "error", "severity": "critical", "description": str(e)[:200], "viewport": "all"}],
                        "features": {},
                        "viewport_scores": {},
                    }

        tasks = [audit_page(p) for p in PAGES_TO_AUDIT]
        page_results = await asyncio.gather(*tasks)

    for pr in page_results:
        for issue in pr.get("issues", []):
            all_issues.append({**issue, "page": pr["label"]})

    successful = [r for r in page_results if "error" not in r]
    overall_score = round(sum(r["score"] for r in successful) / max(len(successful), 1))

    # Category scores
    category_scores = {}
    for cat in ["mobile", "tablet", "desktop", "ultrawide"]:
        cat_scores = []
        for pr in successful:
            for vp_name, vp_data in pr.get("viewport_scores", {}).items():
                if vp_data.get("category") == cat:
                    cat_scores.append(vp_data["score"])
        if cat_scores:
            category_scores[cat] = round(sum(cat_scores) / len(cat_scores))

    return {
        "audit_id": f"resp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration": round(time.monotonic() - start, 2),
        "overall_score": overall_score,
        "pages_audited": len(page_results),
        "total_issues": len(all_issues),
        "category_scores": category_scores,
        "page_results": page_results,
        "issues": all_issues,
        "viewports_tested": [v["name"] for v in VIEWPORTS],
        "recommendations": _generate_responsive_recs(all_issues, category_scores),
    }


def _generate_responsive_recs(issues, category_scores):
    recs = []
    mobile_score = category_scores.get("mobile", 100)
    if mobile_score < 70:
        recs.append({"priority": "critical", "category": "Mobile", "action": "Mobile responsiveness needs urgent attention. Review fixed widths and touch targets."})
    ultrawide_score = category_scores.get("ultrawide", 100)
    if ultrawide_score < 80:
        recs.append({"priority": "high", "category": "Ultra-wide", "action": "Add max-width constraints and centered layouts for ultra-wide displays."})

    severity_counts = {}
    for i in issues:
        sev = i.get("severity", "low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    if severity_counts.get("critical", 0) > 0:
        recs.append({"priority": "critical", "category": "Critical Issues", "action": f"{severity_counts['critical']} critical responsiveness issues found. Fix immediately."})
    if severity_counts.get("high", 0) > 0:
        recs.append({"priority": "high", "category": "High Priority", "action": f"{severity_counts['high']} high-priority layout issues detected across viewports."})

    if not recs:
        recs.append({"priority": "info", "category": "Status", "action": "All viewport tests passed. Continue monitoring across new devices."})

    return recs
