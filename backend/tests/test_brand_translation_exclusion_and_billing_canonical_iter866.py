"""
Checkpoint D verification — iteration 866
==========================================
Verifies:
  1. GET /api/email-notifications/templates/audit returns
     summary.templates_total == 203, templates_failed == 0,
     broken_links_found == 0, and each result carries a
     brand_translation_exclusion field (spot-check that no result has
     the `brand_translation_exclusion_missing:*` or
     `brand_logo_translate_attr_missing` issue).

  2. Rendered previews for a diverse set of templates contain NO bare
     `RealAICoach` text node outside notranslate protection.
     Body-text occurrences of the brand are wrapped in
     <span translate="no" class="notranslate">RealAICoach</span>
     and the header logo <img alt="RealAICoach ..."> carries
     translate="no".

  3. Python-level: the 4 billing builders
     (build_failed_payment_email, build_recovery_email_day1/day3/day7)
     produce primary CTA hrefs that start with the canonical
     `https://realaicoach.app` — NOT the preview host
     `admin-analytics-80.preview.emergentagent.com`.

  4. Dark/light v7 behaviour: rendered previews contain
     `@media (prefers-color-scheme:dark)`, `[data-ogsc]`
     Outlook dark-mode rules, viewport meta, color-scheme meta, and
     the mobile media query `@media only screen and (max-width:479px)`.

  5. Regression: preview endpoint returns 200 with valid HTML for both
     ?theme=light and ?theme=dark. GET /catalog returns 203 entries.
"""

import os
import re
import sys
from pathlib import Path

import pytest
import requests

# Ensure /app/backend is on sys.path so `from utils.email_templates ...` works
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set for testing"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

CANONICAL_HOST = "https://realaicoach.app"
PREVIEW_HOST_MARKER = "admin-analytics-80.preview.emergentagent.com"

# Templates spot-checked for brand translation exclusion via preview endpoint
BRAND_SPOT_CHECK_KEYS = [
    "welcome",
    "referral_invite",
    "gdpr_export_ready",
    "magic_link",
    "newsletter_weekly",
    "failed_payment",
]


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def admin_session():
    """Cookie-jar session authenticated as admin."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:400]}"
    # session_token cookie must be present
    cookie_names = {c.name for c in s.cookies}
    assert "session_token" in cookie_names, (
        f"session_token cookie not set. cookies={cookie_names}"
    )
    return s


# ─── 1. Full audit endpoint ──────────────────────────────────────────────


class TestAuditEndpoint:
    """Full audit endpoint spec — 203 pass, 0 broken links, brand fields."""

    def test_audit_endpoint_summary(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/templates/audit",
            timeout=180,
        )
        assert r.status_code == 200, f"audit endpoint status {r.status_code}: {r.text[:400]}"
        payload = r.json()

        # Summary block
        assert "summary" in payload
        summary = payload["summary"]
        assert summary["templates_total"] == 203, (
            f"expected 203 templates in catalog, got {summary['templates_total']}"
        )
        assert summary["templates_failed"] == 0, (
            f"expected 0 failed templates, got {summary['templates_failed']} — "
            f"failed_templates: {[t['key'] for t in payload.get('failed_templates', [])][:20]}"
        )
        assert summary["broken_links_found"] == 0, (
            f"expected 0 broken links, got {summary['broken_links_found']}"
        )
        assert summary["templates_passed"] == 203

        # Stash for other tests in the class
        TestAuditEndpoint._results = payload["results"]
        TestAuditEndpoint._summary = summary

    def test_audit_results_expose_brand_translation_exclusion_field(self, admin_session):
        # Use the cached results from previous test
        results = getattr(TestAuditEndpoint, "_results", None)
        if results is None:
            r = admin_session.get(
                f"{BASE_URL}/api/email-notifications/templates/audit",
                timeout=180,
            )
            results = r.json()["results"]
            TestAuditEndpoint._results = results

        # The audit endpoint merges light+dark issues in top-level `issues`.
        # It does NOT expose brand_translation_exclusion counts directly at
        # top level (that is inside _audit_rendered_template's return),
        # but the presence of failure-related issues must be zero.
        offenders = []
        for entry in results:
            for issue in entry.get("issues", []):
                if issue.startswith("brand_translation_exclusion_missing") or issue == "brand_logo_translate_attr_missing":
                    offenders.append((entry["key"], issue))
        assert not offenders, (
            f"Templates with brand translation exclusion misses: {offenders[:10]}"
        )


# ─── 2. Rendered preview brand protection ────────────────────────────────


BARE_BRAND_RE = re.compile(r"RealAICoach")


def _iter_text_nodes(html: str):
    """Yield (text, protected) — protected=True when text is inside a
    <span translate="no" ...> or ancestor with translate="no".
    Extremely simple ancestor tracker (mirrors backend logic)."""
    stack = []  # list of (tagname, protected_bool)
    pos = 0
    _tag_re = re.compile(r"<[^>]+>")
    _translate_marker_re = re.compile(
        r'(?:class="[^"]*notranslate[^"]*"|translate="no")', re.IGNORECASE
    )
    void_tags = {"br", "img", "hr", "meta", "input", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
    skip_containers = {"style", "script", "title"}
    for m in _tag_re.finditer(html):
        text = html[pos : m.start()]
        if text:
            protected = any(p for _, p in stack)
            skip = any(n in skip_containers for n, _ in stack)
            yield text, protected, skip
        tag = m.group(0)
        name_m = re.match(r"</?\s*([a-zA-Z0-9-]+)", tag)
        name = name_m.group(1).lower() if name_m else ""
        if tag.startswith("</"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        elif name and name not in void_tags and not tag.endswith("/>") and not tag.startswith("<!"):
            stack.append((name, bool(_translate_marker_re.search(tag))))
        pos = m.end()
    tail = html[pos:]
    if tail:
        yield tail, any(p for _, p in stack), False


class TestBrandTranslationExclusionInPreview:
    """Spot-check that rendered previews protect the brand name."""

    @pytest.mark.parametrize("template_key", BRAND_SPOT_CHECK_KEYS)
    def test_brand_wrapped_in_notranslate_span(self, admin_session, template_key):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/{template_key}",
            timeout=30,
        )
        assert r.status_code == 200, f"preview {template_key}: {r.status_code} {r.text[:200]}"
        payload = r.json()
        html = payload.get("html") or ""
        assert html, f"no html in preview payload for {template_key}"
        # Brand must appear somewhere
        assert "RealAICoach" in html, f"brand missing from {template_key}"
        # No bare brand text nodes outside protection
        offenders = []
        for text, protected, skip in _iter_text_nodes(html):
            if protected or skip:
                continue
            if BARE_BRAND_RE.search(text):
                offenders.append(text.strip()[:120])
        assert not offenders, (
            f"{template_key}: unprotected brand text nodes: {offenders[:5]}"
        )

    @pytest.mark.parametrize("template_key", BRAND_SPOT_CHECK_KEYS)
    def test_brand_logo_img_has_translate_no(self, admin_session, template_key):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/{template_key}",
            timeout=30,
        )
        assert r.status_code == 200
        html = r.json().get("html") or ""
        # Any <img> whose alt contains RealAICoach must have translate="no"
        brand_imgs = re.findall(
            r'<img[^>]*alt="[^"]*RealAICoach[^"]*"[^>]*/?>', html, re.IGNORECASE
        )
        assert brand_imgs, (
            f"{template_key}: expected at least one brand <img> with alt containing brand"
        )
        for tag in brand_imgs:
            assert 'translate="no"' in tag, (
                f"{template_key}: brand <img> missing translate=\"no\": {tag[:200]}"
            )


# ─── 3. Billing builders → canonical CTA links ───────────────────────────


class TestBillingBuildersCanonicalLinks:
    """The 4 billing recovery builders MUST build primary CTA via canonical."""

    def test_failed_payment_uses_canonical(self):
        from utils.email_templates import build_failed_payment_email

        tpl = build_failed_payment_email(update_link="/subscription")
        cta_href = self._extract_primary_cta(tpl.html)
        assert cta_href.startswith(CANONICAL_HOST), (
            f"failed_payment CTA not canonical: {cta_href}"
        )
        assert PREVIEW_HOST_MARKER not in cta_href, (
            f"failed_payment CTA leaked preview host: {cta_href}"
        )

    def test_recovery_day1_uses_canonical(self):
        from utils.email_templates import build_recovery_email_day1

        tpl = build_recovery_email_day1(recovery_link="/subscription/plans")
        cta_href = self._extract_primary_cta(tpl.html)
        assert cta_href.startswith(CANONICAL_HOST), (
            f"recovery_day1 CTA not canonical: {cta_href}"
        )
        assert PREVIEW_HOST_MARKER not in cta_href

    def test_recovery_day3_uses_canonical(self):
        from utils.email_templates import build_recovery_email_day3

        tpl = build_recovery_email_day3(recovery_link="/subscription/plans")
        cta_href = self._extract_primary_cta(tpl.html)
        assert cta_href.startswith(CANONICAL_HOST), (
            f"recovery_day3 CTA not canonical: {cta_href}"
        )
        assert PREVIEW_HOST_MARKER not in cta_href

    def test_recovery_day7_uses_canonical(self):
        from utils.email_templates import build_recovery_email_day7

        tpl = build_recovery_email_day7(recovery_link="/subscription/plans")
        cta_href = self._extract_primary_cta(tpl.html)
        assert cta_href.startswith(CANONICAL_HOST), (
            f"recovery_day7 CTA not canonical: {cta_href}"
        )
        assert PREVIEW_HOST_MARKER not in cta_href

    # Helper
    @staticmethod
    def _extract_primary_cta(html: str) -> str:
        """Return the first navigation-style href in the primary CTA area.
        The primary CTA in _wrap() uses data-primary-cta or is the first
        anchor after the body; but a simpler robust approach: pick the
        first https://realaicoach.app or preview-host href we find outside
        of asset paths / mailto / tel. That href is either canonical (pass)
        or preview (fail)."""
        candidates = re.findall(r'href="([^"]+)"', html, re.IGNORECASE)
        for href in candidates:
            l = href.lower()
            if l.startswith(("mailto:", "tel:", "#")):
                continue
            # skip asset paths under /api/static/
            if "/api/static/" in href:
                continue
            # skip social/store badge urls (google, apple, twitter, etc.)
            if any(dom in l for dom in ("play.google.com", "apps.apple.com", "twitter.com", "x.com", "linkedin.com", "facebook.com", "instagram.com", "youtube.com", "youtu.be")):
                continue
            return href
        raise AssertionError(f"no navigation CTA href found in template HTML (first 400 chars): {html[:400]}")


# ─── 4. Dark/light v7 rendering signatures ───────────────────────────────


DARK_LIGHT_SIGNATURES = [
    "@media (prefers-color-scheme:dark)",
    "[data-ogsc]",
    'name="viewport"',
    "color-scheme",
    "@media only screen and (max-width:479px)",
]


class TestDarkLightV7Signatures:
    def test_preview_light_contains_all_signatures(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/welcome?theme=light",
            timeout=30,
        )
        assert r.status_code == 200
        html = r.json().get("html") or ""
        for sig in DARK_LIGHT_SIGNATURES:
            assert sig in html, f"welcome (light) missing signature: {sig}"

    def test_preview_dark_contains_all_signatures(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/welcome?theme=dark",
            timeout=30,
        )
        assert r.status_code == 200
        html = r.json().get("html") or ""
        for sig in DARK_LIGHT_SIGNATURES:
            assert sig in html, f"welcome (dark) missing signature: {sig}"


# ─── 5. Regression — preview + catalog endpoints ─────────────────────────


class TestRegressionEndpoints:
    def test_preview_welcome_light(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/welcome?theme=light",
            timeout=30,
        )
        assert r.status_code == 200
        assert "<html" in (r.json().get("html") or "").lower()

    def test_preview_welcome_dark(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/preview/welcome?theme=dark",
            timeout=30,
        )
        assert r.status_code == 200
        assert "<html" in (r.json().get("html") or "").lower()

    def test_catalog_has_203_entries(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/email-notifications/catalog",
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        # Catalog may be dict {key: info} or list — normalize:
        if isinstance(data, dict) and "templates" in data:
            entries = data["templates"]
        elif isinstance(data, dict) and "catalog" in data:
            entries = data["catalog"]
        elif isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            # Assume mapping-of-keys
            entries = list(data.keys())
        else:
            entries = data
        assert len(entries) == 203, f"expected 203 catalog entries, got {len(entries)}"
