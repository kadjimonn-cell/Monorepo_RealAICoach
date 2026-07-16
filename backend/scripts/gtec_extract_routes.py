#!/usr/bin/env python3
"""
GTEC Route Extractor
--------------------
Walks /app/frontend/app and extracts all Expo Router routes,
converts filesystem paths to URL paths, and categorizes them.

Output: /app/test_reports/gtec_routes.json
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

FRONTEND_APP = Path("/app/frontend/app")
OUTPUT = Path("/app/test_reports/gtec_routes.json")

# Routes that are known to require authentication (matched by prefix)
AUTH_PREFIXES = {
    "/home", "/dashboard", "/profile", "/settings", "/admin",
    "/admin-system", "/admin-activity-log", "/admin-console",
    "/calendar", "/messages", "/notifications", "/my-analytics",
    "/my-tickets", "/scan-history", "/edit-profile", "/payment-history",
    "/payment-history-export-v2", "/payment-document-v2",
    "/certificate-gallery", "/learner-portfolio", "/leaderboard",
    "/achievements", "/progress", "/progress-tracker", "/session-history",
    "/content-library", "/ai-briefing", "/ai-learning-hub",
    "/ai-feature-dashboard", "/ai-coaching-team", "/executive-dashboard",
    "/hiring-hub", "/team-management", "/ops-performance",
    "/ops-route-health", "/policy-console", "/performance-observability",
    "/route-health-report", "/safe-deployment", "/system-status",
    "/email-templates-admin", "/careers", "/feature-gallery",
    "/integrations", "/subscription", "/referrals", "/pricing",
    "/chat", "/practice", "/feedback", "/id-verification",
    "/ai-learning-hub-kpi", "/shared-calendar", "/(tabs)",
}

# Public routes (no auth needed)
PUBLIC_PREFIXES = {
    "/welcome", "/login", "/auth", "/contact", "/about",
    "/faq", "/help", "/press", "/terms", "/privacy-policy",
    "/cookies", "/security", "/gdpr", "/pricing", "/blog",
    "/employer-apply", "/track-application", "/careers/portal",
    "/careers/video-qa", "/careers/schedule", "/careers/interview",
    "/careers/offer", "/book", "/invite-accept",
    "/privacy-verify", "/privacy-request", "/certificate-verify",
    "/language-selector", "/currency-selector", "/onboarding",
    "/id-verify-mobile", "/shared", "/feature-gallery",
    "/feedback", "/career",
}

# Routes that LOOK public by path but have auth-gated behaviour (admin-only
# API calls, or authenticated-user-only logic). Probing them unauthenticated
# returns 401/403 on their primary API call even though the page is reachable.
# Reclassified per GTEC §4 root-cause fix (was false-positive in v1 crawler).
_FORCE_PROTECTED = {
    "/auth/logout",       # calls /api/auth/logout — needs session token
    "/auth/sso-debug",    # admin-only diagnostic page
    "/verify",            # payment verify — needs auth'd user context
    "/logout",            # alias of /auth/logout
}

# Dynamic placeholder samples (these cannot be crawled without concrete tokens)
DYNAMIC_SAMPLES = {
    "[token]": "SAMPLE_TOKEN_gtec_probe",
    "[id]": "gtec_probe",
    "[slug]": "gtec-probe",
    "[kpiId]": "gtec_probe",
    "[userId]": "gtec_probe",
    "[verificationId]": "gtec_probe",
    "[offerId]": "gtec_probe",
}

SKIP_FILES = {
    "_layout.tsx", "+native-intent.tsx", "+html.tsx", "+not-found.tsx",
}


def fs_to_url(relpath: str) -> str:
    """Convert an app-dir-relative path to a URL path."""
    # strip extension
    p = re.sub(r"\.(tsx|ts|jsx|js)$", "", relpath)
    # strip "index" at end or alone
    p = re.sub(r"(^|/)index$", "", p)
    # remove group segments like "(tabs)"
    p = re.sub(r"\([^/]+\)/?", "", p)
    # ensure leading slash
    if not p.startswith("/"):
        p = "/" + p
    # collapse double slashes
    p = re.sub(r"//+", "/", p)
    if p != "/" and p.endswith("/"):
        p = p[:-1]
    if p == "":
        p = "/"
    return p


def classify(url: str) -> str:
    """Return 'public' | 'protected' | 'dynamic'."""
    # Force-protected overrides (auth-gated-by-behaviour).
    if url in _FORCE_PROTECTED:
        return "protected"
    if re.search(r"\[[^\]]+\]", url):
        return "dynamic"
    # Check public prefixes first (more specific public routes)
    for pub in PUBLIC_PREFIXES:
        if url == pub or url.startswith(pub + "/"):
            return "public"
    for auth in AUTH_PREFIXES:
        if url == auth or url.startswith(auth + "/"):
            return "protected"
    return "public"  # Default unknown to public — will be filtered by crawler


def resolve_dynamic(url: str) -> str:
    """Substitute dynamic segments with safe probe tokens."""
    out = url
    for placeholder, sample in DYNAMIC_SAMPLES.items():
        out = out.replace(placeholder, sample)
    return out


def main() -> None:
    routes: list[dict] = []
    for root, _, files in os.walk(FRONTEND_APP):
        for f in files:
            if not f.endswith((".tsx", ".ts", ".jsx", ".js")):
                continue
            if f in SKIP_FILES:
                continue
            full = Path(root) / f
            rel = str(full.relative_to(FRONTEND_APP))
            url = fs_to_url(rel)
            category = classify(url)
            probe_url = resolve_dynamic(url) if category == "dynamic" else url
            routes.append({
                "file": str(full),
                "relpath": rel,
                "url": url,
                "probe_url": probe_url,
                "category": category,
            })

    routes.sort(key=lambda r: r["url"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(routes),
        "counts": {
            "public": sum(1 for r in routes if r["category"] == "public"),
            "protected": sum(1 for r in routes if r["category"] == "protected"),
            "dynamic": sum(1 for r in routes if r["category"] == "dynamic"),
        },
        "routes": routes,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"[gtec] Extracted {len(routes)} routes → {OUTPUT}")
    print(f"[gtec] Counts: {payload['counts']}")


if __name__ == "__main__":
    main()
