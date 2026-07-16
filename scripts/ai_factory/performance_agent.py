#!/usr/bin/env python3
"""Performance Agent: Lighthouse gate for CI/CD."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


REPORT_PATH = Path("/app/test_reports/ai_factory_performance_report.json")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def _run_lighthouse(url: str) -> dict:
    command = [
        "npx",
        "-y",
        "lighthouse",
        url,
        "--quiet",
        "--output=json",
        "--output-path=stdout",
        "--chrome-flags=--headless --no-sandbox",
        "--only-categories=performance,accessibility,best-practices,seo",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"lighthouse failed: {result.stderr[-400:]}")

    stdout = result.stdout.strip()
    json_start = stdout.find("{")
    if json_start == -1:
        raise RuntimeError("Unable to parse Lighthouse JSON output")
    return json.loads(stdout[json_start:])


def _run_pagespeed_fallback(url: str) -> dict:
    response = requests.get(
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        params={
            "url": url,
            "category": ["performance", "accessibility", "best-practices", "seo"],
            "strategy": "desktop",
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"pagespeed fallback failed: {response.status_code}")
    payload = response.json().get("lighthouseResult")
    if not isinstance(payload, dict):
        raise RuntimeError("pagespeed fallback missing lighthouseResult")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Lighthouse performance gate")
    parser.add_argument("--url", help="Page URL to audit (defaults to PERFORMANCE_BASE_URL env)")
    parser.add_argument("--min-performance", type=float, default=90.0)
    parser.add_argument("--max-fcp-ms", type=float, default=2000.0)
    parser.add_argument("--max-lcp-ms", type=float, default=2500.0)
    parser.add_argument("--allow-pagespeed-fallback", action="store_true")
    args = parser.parse_args()

    try:
        url = args.url or _require_env("PERFORMANCE_BASE_URL")
        try:
            report = _run_lighthouse(url)
        except Exception as lighthouse_error:
            local_target = "localhost" in url or "127.0.0.1" in url
            if not args.allow_pagespeed_fallback or local_target:
                raise
            report = _run_pagespeed_fallback(url)
            report["_lighthouse_fallback_error"] = str(lighthouse_error)
        categories = report.get("categories", {})
        audits = report.get("audits", {})

        performance_score = float((categories.get("performance", {}) or {}).get("score", 0)) * 100
        accessibility_score = float((categories.get("accessibility", {}) or {}).get("score", 0)) * 100
        best_practices_score = float((categories.get("best-practices", {}) or {}).get("score", 0)) * 100
        seo_score = float((categories.get("seo", {}) or {}).get("score", 0)) * 100

        fcp = float((audits.get("first-contentful-paint", {}) or {}).get("numericValue", 0))
        lcp = float((audits.get("largest-contentful-paint", {}) or {}).get("numericValue", 0))

        failures = []
        if performance_score < args.min_performance:
            failures.append(f"performance score {performance_score:.1f} < {args.min_performance:.1f}")
        if fcp > args.max_fcp_ms:
            failures.append(f"FCP {fcp:.0f}ms > {args.max_fcp_ms:.0f}ms")
        if lcp > args.max_lcp_ms:
            failures.append(f"LCP {lcp:.0f}ms > {args.max_lcp_ms:.0f}ms")

        confidence = "HIGH" if not failures else "LOW"
        hard_fail = confidence != "HIGH"

        output = {
            "agent": "performance",
            "status": "PASS" if not hard_fail else "FAIL",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "confidence": confidence,
            "hard_completion_rule": {
                "rule": "IF CONFIDENCE != HIGH => AUTOMATIC FAIL => CONTINUE ITERATION",
                "triggered": hard_fail,
            },
            "scores": {
                "performance": round(performance_score, 1),
                "accessibility": round(accessibility_score, 1),
                "best_practices": round(best_practices_score, 1),
                "seo": round(seo_score, 1),
            },
            "metrics_ms": {
                "first_contentful_paint": round(fcp, 1),
                "largest_contentful_paint": round(lcp, 1),
            },
            "thresholds": {
                "min_performance": args.min_performance,
                "max_fcp_ms": args.max_fcp_ms,
                "max_lcp_ms": args.max_lcp_ms,
            },
            "failures": failures,
            "fallback_used": bool(report.get("_lighthouse_fallback_error")),
            "fallback_reason": report.get("_lighthouse_fallback_error"),
        }

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
        return 0 if not hard_fail else 1
    except Exception as exc:
        output = {
            "agent": "performance",
            "status": "FAIL",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "confidence": "LOW",
            "hard_completion_rule": {
                "rule": "IF CONFIDENCE != HIGH => AUTOMATIC FAIL => CONTINUE ITERATION",
                "triggered": True,
            },
            "error": str(exc),
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())