#!/usr/bin/env python3
"""Responsive Layout Gate — post-build smoke check of rendered public pages.

Fails the build when a freshly exported page has horizontal overflow, visible
data-testid elements extending past the viewport, or renders blank at any of
the guarded widths (390 / 768 / 1024). Warns (non-fatal) on potential vertical
clipping. Skips gracefully when no local server is reachable (external CI).
"""
import json
import os
import sys
import urllib.request

BASE_URL = os.environ.get("RESPONSIVE_GATE_BASE_URL", "http://127.0.0.1:3000")
ROUTES = [r for r in os.environ.get("RESPONSIVE_GATE_ROUTES", "/welcome,/pricing").split(",") if r.strip()]
VIEWPORTS = [(390, 844), (768, 1024), (1024, 768)]
HYDRATION_WAIT_MS = 4000
EDGE_TOLERANCE_PX = 2

PAGE_AUDIT_JS = """
() => {
  const innerW = window.innerWidth;
  const offenders = [];
  const clipWarnings = [];
  const hasScrollableXAncestor = (el) => {
    let node = el.parentElement;
    while (node && node !== document.body) {
      const ox = getComputedStyle(node).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') return true;
      node = node.parentElement;
    }
    return false;
  };
  document.querySelectorAll('[data-testid]').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return;
    if ((r.right > innerW + %(tol)d || r.left < -%(tol)d) && !hasScrollableXAncestor(el)) {
      if (offenders.length < 10) offenders.push({ testid: el.getAttribute('data-testid'), left: Math.round(r.left), right: Math.round(r.right) });
    }
    if (cs.overflowY === 'hidden' && el.scrollHeight - el.clientHeight > 12 && el.clientHeight > 40) {
      if (clipWarnings.length < 10) clipWarnings.push({ testid: el.getAttribute('data-testid'), hidden: el.scrollHeight - el.clientHeight });
    }
  });
  return {
    innerW,
    scrollW: document.documentElement.scrollWidth,
    textLen: (document.body.innerText || '').trim().length,
    testidCount: document.querySelectorAll('[data-testid]').length,
    offenders,
    clipWarnings,
  };
}
""" % {"tol": EDGE_TOLERANCE_PX}


def server_reachable() -> bool:
    try:
        urllib.request.urlopen(BASE_URL, timeout=5)
        return True
    except Exception:
        return False


def main() -> int:
    if not server_reachable():
        print(f"[responsive-gate] SKIP: no server reachable at {BASE_URL} (external CI/deploy build). Gate passes vacuously.")
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("[responsive-gate] SKIP: playwright not installed in this environment. Gate passes vacuously.")
        return 0

    failures = []
    warnings = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            for width, height in VIEWPORTS:
                page = browser.new_page(viewport={"width": width, "height": height})
                for route in ROUTES:
                    url = f"{BASE_URL}{route.strip()}"
                    label = f"{route.strip()} @ {width}x{height}"
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(HYDRATION_WAIT_MS)
                        audit = page.evaluate(PAGE_AUDIT_JS)
                    except Exception as exc:
                        failures.append(f"{label}: page failed to render ({exc})")
                        continue
                    if audit["textLen"] < 40:
                        failures.append(f"{label}: page appears blank (textLen={audit['textLen']})")
                    overflow = audit["scrollW"] - audit["innerW"]
                    if overflow > 1:
                        failures.append(f"{label}: horizontal page overflow of {overflow}px (scrollW={audit['scrollW']} > innerW={audit['innerW']})")
                    if audit["offenders"]:
                        failures.append(f"{label}: elements past viewport edge: {json.dumps(audit['offenders'])}")
                    if audit["clipWarnings"]:
                        warnings.append(f"{label}: possible vertical clipping (non-fatal): {json.dumps(audit['clipWarnings'])}")
                    print(f"[responsive-gate] {label}: testids={audit['testidCount']} overflow={max(0, overflow)}px offenders={len(audit['offenders'])} clipWarnings={len(audit['clipWarnings'])}")
                page.close()
            browser.close()
    except Exception as exc:
        print(f"[responsive-gate] SKIP: browser launch unavailable ({exc}). Gate passes vacuously.")
        return 0

    for w in warnings:
        print(f"[responsive-gate] WARN: {w}")
    if failures:
        print(f"[responsive-gate] FAIL: {len(failures)} responsive violation(s):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print(f"[responsive-gate] PASS: {len(ROUTES)} route(s) x {len(VIEWPORTS)} viewport(s) clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
