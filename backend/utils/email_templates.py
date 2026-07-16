"""Commercial-grade email templates for RealAICoach.

Self-contained, dark-themed, responsive HTML email templates.
Every template renders correctly even without env vars configured.
"""

import os
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from dataclasses import dataclass
from functools import wraps
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
from shared.pricing_policy import get_plan_amount, get_monthly_price_label, get_plan_name

# ─── Jinja2 Template Engine ───
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=False,  # Email templates contain pre-sanitized HTML
)
_jinja_env.globals["brand"] = lambda: BRAND  # deferred so env var is read at render time

# ─── Brand Config (safe defaults) ───
BRAND = os.environ.get("BRAND_NAME", "RealAICoach")
# LOCKED: Brand name wrapped in notranslate for HTML email body contexts
BRAND_NT = f'<span translate="no" class="notranslate">{BRAND}</span>'
CANONICAL_FRONTEND_BASE = "https://realaicoach.app"


def _normalize_base_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return CANONICAL_FRONTEND_BASE
    if raw.startswith("http://"):
        raw = "https://" + raw[len("http://"):]
    elif not raw.startswith(("https://", "http://")):
        raw = f"https://{raw.lstrip('/')}"
    return raw.rstrip("/")


FRONTEND_BASE = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL", ""))
_PLATFORM_NETLOC = urlparse(FRONTEND_BASE).netloc
_CANONICAL_NETLOC = urlparse(CANONICAL_FRONTEND_BASE).netloc


def _is_platform_netloc(netloc: str) -> bool:
    """A URL counts as 'platform-internal' if it points at either the
    preview FRONTEND_BASE or the canonical realaicoach.app host. UTM
    stamping + auto-rewrites apply to both."""
    n = (netloc or "").strip().lower()
    return n in (_PLATFORM_NETLOC.lower(), _CANONICAL_NETLOC.lower())

# ─────────────────────────────────────────────────────────────────────
# Email link mode (Option A — Canonical-host mode with mode switch)
# ─────────────────────────────────────────────────────────────────────
# Why this exists:
#   The Emergent preview pod's hostname is ephemeral. Stamping that host
#   into emails means a future cluster reassignment (e.g. the proxy 502
#   we saw on `theme-governance.cluster-9.preview.emergentcf.cloud`) can
#   break every previously-sent email link.
#
# Modes:
#   `canonical` (DEFAULT) — navigation/CTA links use CANONICAL_FRONTEND_BASE
#                           (`https://realaicoach.app`), the stable production
#                           host. Survives preview cluster churn.
#   `preview`             — navigation/CTA links use FRONTEND_BASE_URL (the
#                           live preview hostname). Useful when an admin
#                           wants email links to deep-link into the active
#                           preview pod for in-pod testing.
#
# Static-asset URLs (anything under `/api/static/...`) ALWAYS use
# FRONTEND_BASE — the canonical production domain doesn't serve `/api/...`
# yet, and we'd rather keep email images rendering than save one cluster
# hop on a logo. This mirrors how Stripe / GitHub split their email URLs
# (CTAs to stripe.com, images on a CDN host).
EMAIL_LINK_MODE = (os.environ.get("EMAIL_LINK_MODE") or "canonical").strip().lower()
if EMAIL_LINK_MODE not in ("canonical", "preview"):
    EMAIL_LINK_MODE = "canonical"


def _email_link_base(*, asset: bool = False) -> str:
    """Return the correct base host for an email-embedded URL.

    asset=True forces FRONTEND_BASE (preview host) regardless of mode,
    because canonical (`realaicoach.app`) does not currently serve
    `/api/static/...`. Navigation URLs honour EMAIL_LINK_MODE.
    """
    if asset:
        return FRONTEND_BASE
    if EMAIL_LINK_MODE == "canonical":
        return CANONICAL_FRONTEND_BASE
    return FRONTEND_BASE


def _is_asset_path(path_or_url: str) -> bool:
    """Heuristic: URLs under `/api/static/` (logos, badge images, fonts)
    are treated as assets and never canonicalised."""
    s = (path_or_url or "").strip()
    if not s:
        return False
    # Either a relative `/api/static/...` path or an absolute URL whose
    # path component starts with `/api/static/`.
    try:
        parsed = urlparse(s)
        path = parsed.path or ""
    except Exception:
        path = s
    return path.startswith("/api/static/") or "/api/static/" in s

# ─── Category Color Palette for Email Headers ───
_CATEGORY_PALETTE = {
    "onboarding":       {"gf": "#059669", "gt": "#10B981", "bd": "#6EE7B7", "kk": "#A7F3D0", "pb": "#047857", "ct": "#F0FDF4", "cb": "#BBF7D0", "sb": "#DCFCE7", "ba": "#ECFDF5"},
    "onboarding drip":  {"gf": "#0D9488", "gt": "#14B8A6", "bd": "#5EEAD4", "kk": "#99F6E4", "pb": "#0F766E", "ct": "#F0FDFA", "cb": "#99F6E4", "sb": "#CCFBF1", "ba": "#F0FDFA"},
    "security":         {"gf": "#DC2626", "gt": "#EF4444", "bd": "#FCA5A5", "kk": "#FECACA", "pb": "#991B1B", "ct": "#FEF2F2", "cb": "#FECACA", "sb": "#FEE2E2", "ba": "#FFF1F2"},
    "billing":          {"gf": "#059669", "gt": "#34D399", "bd": "#6EE7B7", "kk": "#A7F3D0", "pb": "#047857", "ct": "#ECFDF5", "cb": "#A7F3D0", "sb": "#D1FAE5", "ba": "#ECFDF5"},
    "support":          {"gf": "#7C3AED", "gt": "#8B5CF6", "bd": "#C4B5FD", "kk": "#DDD6FE", "pb": "#6D28D9", "ct": "#F5F3FF", "cb": "#DDD6FE", "sb": "#EDE9FE", "ba": "#F5F3FF"},
    "calendar":         {"gf": "#2563EB", "gt": "#3B82F6", "bd": "#93C5FD", "kk": "#BFDBFE", "pb": "#1D4ED8", "ct": "#EFF6FF", "cb": "#BFDBFE", "sb": "#DBEAFE", "ba": "#EFF6FF"},
    "employer":         {"gf": "#0891B2", "gt": "#06B6D4", "bd": "#67E8F9", "kk": "#A5F3FC", "pb": "#0E7490", "ct": "#ECFEFF", "cb": "#A5F3FC", "sb": "#CFFAFE", "ba": "#ECFEFF"},
    "verification":     {"gf": "#4F46E5", "gt": "#6366F1", "bd": "#A5B4FC", "kk": "#C7D2FE", "pb": "#4338CA", "ct": "#EEF2FF", "cb": "#C7D2FE", "sb": "#E0E7FF", "ba": "#EEF2FF"},
    "ai":               {"gf": "#7C3AED", "gt": "#A855F7", "bd": "#D8B4FE", "kk": "#E9D5FF", "pb": "#6D28D9", "ct": "#FAF5FF", "cb": "#E9D5FF", "sb": "#F3E8FF", "ba": "#FAF5FF"},
    "engagement":       {"gf": "#EA580C", "gt": "#F97316", "bd": "#FDBA74", "kk": "#FED7AA", "pb": "#C2410C", "ct": "#FFF7ED", "cb": "#FED7AA", "sb": "#FFEDD5", "ba": "#FFF7ED"},
    "communication":    {"gf": "#0284C7", "gt": "#0EA5E9", "bd": "#7DD3FC", "kk": "#BAE6FD", "pb": "#0369A1", "ct": "#F0F9FF", "cb": "#BAE6FD", "sb": "#E0F2FE", "ba": "#F0F9FF"},
    "account":          {"gf": "#475569", "gt": "#64748B", "bd": "#CBD5E1", "kk": "#E2E8F0", "pb": "#334155", "ct": "#F8FAFC", "cb": "#E2E8F0", "sb": "#F1F5F9", "ba": "#F8FAFC"},
    "hiring":           {"gf": "#0891B2", "gt": "#06B6D4", "bd": "#67E8F9", "kk": "#A5F3FC", "pb": "#0E7490", "ct": "#ECFEFF", "cb": "#A5F3FC", "sb": "#CFFAFE", "ba": "#ECFEFF"},
    "notifications":    {"gf": "#2563EB", "gt": "#3B82F6", "bd": "#93C5FD", "kk": "#BFDBFE", "pb": "#1D4ED8", "ct": "#EFF6FF", "cb": "#BFDBFE", "sb": "#DBEAFE", "ba": "#EFF6FF"},
    "jobs":             {"gf": "#0891B2", "gt": "#22D3EE", "bd": "#67E8F9", "kk": "#A5F3FC", "pb": "#0E7490", "ct": "#ECFEFF", "cb": "#A5F3FC", "sb": "#CFFAFE", "ba": "#ECFEFF"},
    # ── V7 Template Palette (Cobalt Blue) — used for ALL template-domain emails ──
    "v7_template":      {"gf": "#2B6CB0", "gt": "#4C6EF5", "bd": "#90CDF4", "kk": "#BEE3F8", "pb": "#2C5282", "ct": "#EBF8FF", "cb": "#BEE3F8", "sb": "#E2F0FE", "ba": "#EBF4FF"},
}
_DEFAULT_CAT = {"gf": "#0ea5e9", "gt": "#6366f1", "bd": "#93C5FD", "kk": "#BFDBFE", "pb": "#1E40AF", "ct": "#EFF6FF", "cb": "#BFDBFE", "sb": "#DBEAFE", "ba": "#EFF6FF"}

def _cat_colors(category: str) -> dict:
    return _CATEGORY_PALETTE.get((category or "").strip().lower(), _DEFAULT_CAT)

# Mutable list used as a thread-local-ish context for the active category during template building
_ACTIVE_CATEGORY = [""]


def _append_query_params(url: str, params: dict) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update({k: v for k, v in params.items() if v is not None and v != ""})
    return urlunparse(parsed._replace(query=urlencode(existing, doseq=True)))


def _to_absolute_https(url: str, fallback_path: str = "/") -> str:
    raw = (url or "").strip()
    if not raw or raw == "#":
        raw = fallback_path

    # Choose the base host based on whether this is a static asset
    # (always FRONTEND_BASE — canonical doesn't serve `/api/static/`) or a
    # navigation URL (mode-dependent).
    base = _email_link_base(asset=_is_asset_path(raw))

    if raw.startswith("/"):
        raw = f"{base}{raw}"
    elif not raw.startswith(("https://", "http://", "mailto:", "tel:")):
        raw = f"{base}/{raw.lstrip('/')}"

    if raw.startswith("http://"):
        raw = "https://" + raw[len("http://"):]

    return raw


def _platform_url(path: str, campaign: str = "notifications", content: str = "link") -> str:
    absolute = _to_absolute_https(path, "/")
    parsed = urlparse(absolute)
    if _is_platform_netloc(parsed.netloc):
        absolute = _append_query_params(
            absolute,
            {
                "utm_source": "email_notification",
                "utm_medium": "email",
                "utm_campaign": campaign,
                "utm_content": content,
            },
        )
    return absolute


# ─── Brand auto-translation exclusion guard (platform-locked) ───
_VOID_TAGS = frozenset({"br", "img", "hr", "meta", "input", "link", "area", "base", "col", "embed", "source", "track", "wbr"})
_TRANSLATE_SKIP_CONTAINERS = frozenset({"style", "script", "title"})
_TAG_TOKEN_RE = re.compile(r"<[^>]+>")
_TRANSLATE_EXCLUSION_MARK_RE = re.compile(r'(?:class="[^"]*notranslate[^"]*"|translate="no")', re.IGNORECASE)


def _tag_name(tag: str) -> str:
    m = re.match(r"</?\s*([a-zA-Z0-9-]+)", tag)
    return m.group(1).lower() if m else ""


def _scan_brand_text_nodes(html: str):
    """Yield (start, end, text, protected, skip) for each HTML text node."""
    stack: list[tuple[str, bool]] = []
    pos = 0
    for m in _TAG_TOKEN_RE.finditer(html or ""):
        text = html[pos:m.start()]
        if text:
            protected = any(p for _, p in stack)
            skip = any(n in _TRANSLATE_SKIP_CONTAINERS for n, _ in stack)
            yield pos, m.start(), text, protected, skip
        tag = m.group(0)
        name = _tag_name(tag)
        if tag.startswith("</"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        elif name and name not in _VOID_TAGS and not tag.endswith("/>") and not tag.startswith("<!"):
            stack.append((name, bool(_TRANSLATE_EXCLUSION_MARK_RE.search(tag))))
        pos = m.end()
    tail = html[pos:]
    if tail:
        yield pos, len(html or ""), tail, any(p for _, p in stack), False


def find_unprotected_brand_text(html: str) -> list[str]:
    """Return text-node snippets where the brand name lacks translation exclusion."""
    if not html or BRAND not in html:
        return []
    brand_re = re.compile(re.escape(BRAND))
    hits = []
    for _s, _e, text, protected, skip in _scan_brand_text_nodes(html):
        if protected or skip:
            continue
        if brand_re.search(text):
            hits.append(text.strip()[:120])
    return hits


def find_brand_imgs_missing_translate_attr(html: str) -> list[str]:
    """Return <img> tags whose alt contains the brand but lack translate="no"."""
    tags = re.findall(rf'<img[^>]*alt="[^"]*{re.escape(BRAND)}[^"]*"[^>]*/?>', html or "", re.IGNORECASE)
    return [t[:160] for t in tags if 'translate="no"' not in t]


def enforce_brand_translation_exclusion(html: str) -> str:
    """Wrap bare brand-name text nodes in notranslate spans and stamp
    translate="no" on brand-alt images. Idempotent; applied to every
    rendered email so auto-translation never mutates the brand."""
    if not html or BRAND not in html:
        return html
    brand_re = re.compile(re.escape(BRAND))
    replacement = f'<span translate="no" class="notranslate">{BRAND}</span>'
    pieces = []
    cursor = 0
    for start, end, text, protected, skip in _scan_brand_text_nodes(html):
        if protected or skip or BRAND not in text:
            continue
        pieces.append(html[cursor:start])
        pieces.append(brand_re.sub(replacement, text))
        cursor = end
    pieces.append(html[cursor:])
    out = "".join(pieces)

    def _img_fix(m: re.Match) -> str:
        tag = m.group(0)
        if 'translate="no"' in tag:
            return tag
        if tag.endswith("/>"):
            return tag[:-2].rstrip() + ' translate="no" />'
        return tag[:-1] + ' translate="no">'

    return re.sub(rf'<img[^>]*alt="[^"]*{re.escape(BRAND)}[^"]*"[^>]*/?>', _img_fix, out, flags=re.IGNORECASE)


def _normalize_email_links(html: str) -> str:
    """Ensure all href links are HTTPS absolute and internal links carry standardized UTM params."""
    def _replace(match: re.Match) -> str:
        href = match.group(1)
        if not href:
            normalized = _platform_url("/", "notifications", "fallback")
            return f'href="{normalized}"'
        raw = href.strip()
        if raw.startswith(("mailto:", "tel:")):
            return f'href="{raw}"'

        normalized = _to_absolute_https(raw, "/")
        parsed = urlparse(normalized)
        if _is_platform_netloc(parsed.netloc):
            existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
            if not existing.get("utm_campaign"):
                normalized = _append_query_params(
                    normalized,
                    {
                        "utm_source": "email_notification",
                        "utm_medium": "email",
                        "utm_campaign": "notifications",
                    },
                )
        return f'href="{normalized}"'

    return re.sub(r'href="([^"]*)"', _replace, html, flags=re.IGNORECASE)


def _apply_template_campaign(html: str, template_key: str) -> str:
    """Force per-template utm_campaign on all internal platform links."""
    campaign = template_key

    def _replace(match: re.Match) -> str:
        href = (match.group(1) or "").strip()
        if not href:
            return f"href=\"{_platform_url('/', campaign, 'fallback')}\""
        if href.startswith(("mailto:", "tel:")):
            return f'href="{href}"'

        normalized = _to_absolute_https(href, "/")
        parsed = urlparse(normalized)
        if _is_platform_netloc(parsed.netloc):
            normalized = _append_query_params(
                normalized,
                {
                    "utm_source": "email_notification",
                    "utm_medium": "email",
                    "utm_campaign": campaign,
                },
            )
        return f'href="{normalized}"'

    return re.sub(r'href="([^"]*)"', _replace, html, flags=re.IGNORECASE)


def _campaign_name_for_template(template_key: str, category: str) -> str:
    """Generate standardized campaign naming for cleaner analytics slices by category."""
    category_map = {
        "onboarding": "onboarding",
        "onboarding drip": "onboarding",
        "security": "security",
        "billing": "billing",
        "support": "support",
        "calendar": "calendar",
        "employer": "employer",
        "verification": "verification",
        "ai": "ai",
        "engagement": "engagement",
        "communication": "communication",
        "account": "account",
        "hiring": "hiring",
        "notifications": "notifications",
        "jobs": "jobs",
    }
    normalized_category = category_map.get((category or "").strip().lower(), (category or "general").strip().lower())
    normalized_category = re.sub(r"[^a-z0-9]+", "_", normalized_category).strip("_") or "general"
    normalized_key = re.sub(r"[^a-z0-9]+", "_", (template_key or "template").strip().lower()).strip("_") or "template"
    return f"email_{normalized_category}_{normalized_key}"


STATIC_LOGO = f"{FRONTEND_BASE}/api/static/images/brand-logo-full.png"
LOGO = STATIC_LOGO or os.environ.get("BRAND_LOGO_URL", "")
PRIMARY = os.environ.get("BRAND_PRIMARY_COLOR", "#3B82F6")
DASH_URL = _normalize_base_url(os.environ.get("DASHBOARD_LINK_URL", FRONTEND_BASE))
SUPPORT_URL = os.environ.get("SUPPORT_LINK_URL", _platform_url("/my-tickets", "support", "footer"))
GOOGLE_PLAY_URL = os.environ.get("GOOGLE_PLAY_URL", "https://play.google.com/store/search?q=RealAICoach&c=apps")

def _get_subscription_plans() -> dict:
    return {}


def get_plan_defaults(plan_id: str = "premium", cycle: str = "Monthly") -> dict:
    """Return a dict of plan-aware default values for billing email templates.
    
    Returns: {plan_name, amount, billing_summary, billing_cycle, monthly_price, yearly_price}
    """
    plans = _get_subscription_plans()
    plan = plans.get(plan_id, plans.get("premium", {}))
    price = plan.get("monthly_price", get_plan_amount("premium", "monthly")) if cycle.lower() == "monthly" else plan.get("yearly_price", get_plan_amount("premium", "yearly"))
    return {
        "plan_name": plan.get("name", plan_id.title()),
        "amount": f"${price:.2f}",
        "billing_summary": f"{plan.get('name', plan_id.title())} {cycle}",
        "billing_cycle": cycle,
        "monthly_price": plan.get("monthly_price", 0),
        "yearly_price": plan.get("yearly_price", 0),
    }


APP_STORE_URL = os.environ.get("APP_STORE_URL", "https://apps.apple.com/us/search?term=RealAICoach")
DEFAULT_GOOGLE_PLAY_BADGE_IMAGE_URL = _to_absolute_https("/api/static/images/email/google_play_exact_trimmed.png")
DEFAULT_APP_STORE_BADGE_IMAGE_URL = _to_absolute_https("/api/static/images/email/app_store_exact_trimmed.png")
GOOGLE_PLAY_BADGE_IMAGE_URL = _to_absolute_https(
    os.environ.get("GOOGLE_PLAY_BADGE_IMAGE_URL", DEFAULT_GOOGLE_PLAY_BADGE_IMAGE_URL)
)
APP_STORE_BADGE_IMAGE_URL = _to_absolute_https(
    os.environ.get("APP_STORE_BADGE_IMAGE_URL", DEFAULT_APP_STORE_BADGE_IMAGE_URL)
)

GOOGLE_PLAY_BADGE_RATIO = 646 / 250
APP_STORE_BADGE_RATIO = 119.66407 / 40
GLOBAL_EMAIL_FOOTER_COMPONENT_ID = "realaicoach-global-email-footer"
GLOBAL_EMAIL_FOOTER_VERSION = "gef_v2026_06_pro_chrome_redesign"
GLOBAL_EMAIL_FOOTER_LAST_UPDATED = "2026-06-20T00:00:00Z"
GLOBAL_EMAIL_FOOTER_TEMPLATE = "partials/global_email_footer.html"
GLOBAL_STORE_BADGE_BASELINE_WIDTH = 142
GLOBAL_STORE_BADGE_BASELINE_HEIGHT = 43
STORE_BADGE_REGULAR_HEIGHT = GLOBAL_STORE_BADGE_BASELINE_HEIGHT
STORE_BADGE_COMPACT_HEIGHT = GLOBAL_STORE_BADGE_BASELINE_HEIGHT
STORE_BADGE_MOBILE_REGULAR_HEIGHT = GLOBAL_STORE_BADGE_BASELINE_HEIGHT
STORE_BADGE_MOBILE_COMPACT_HEIGHT = GLOBAL_STORE_BADGE_BASELINE_HEIGHT
def _store_badge_dimensions(compact: bool = False) -> dict:
    height = STORE_BADGE_COMPACT_HEIGHT if compact else STORE_BADGE_REGULAR_HEIGHT
    variant = "compact" if compact else "regular"
    google_width = GLOBAL_STORE_BADGE_BASELINE_WIDTH if not compact else 120
    return {
        "variant": variant,
        "height": height,
        "frame_width": google_width,
        "google": {
            "width": google_width,
            "render_width": google_width,
            "render_height": height,
            "ratio": GOOGLE_PLAY_BADGE_RATIO,
        },
        "app": {
            "width": google_width,
            "render_width": google_width,
            "render_height": height,
            "ratio": APP_STORE_BADGE_RATIO,
        },
    }


def _official_store_badges(compact: bool = False) -> str:
    """Official Google Play + App Store badges with email-safe markup."""
    dims = _store_badge_dimensions(compact)
    badge_height = dims["height"]
    frame_width = dims["frame_width"]
    badge_variant = dims["variant"]
    td_spacing = "6px" if compact else "8px"
    # Hosted HTTPS badge assets are Gmail-safe (Gmail blocks/strips data:image URIs).
    google_play_src = GOOGLE_PLAY_BADGE_IMAGE_URL
    app_store_src = APP_STORE_BADGE_IMAGE_URL
    return f"""
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;" class="footer-badge-row footer-badge-row-{badge_variant}" data-footer-badges="official" data-footer-badge-variant="{badge_variant}">
        <tr>
          <td style="padding-right:{td_spacing};text-align:center;vertical-align:middle;">
            <a href="{GOOGLE_PLAY_URL}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:inline-block;" class="footer-badge-link footer-badge-link-google" data-footer-badge="google-play" data-footer-badge-lock-height="{badge_height}" data-footer-badge-lock-width="{frame_width}" data-notranslate="true" translate="no" aria-label="Get RealAICoach on Google Play">
              <table role="presentation" cellpadding="0" cellspacing="0" class="footer-badge-frame footer-badge-frame-google footer-badge-frame-{badge_variant}" style="width:{frame_width}px;height:{badge_height}px;margin:0 auto;">
                <tr>
                  <td align="center" valign="middle" style="width:{frame_width}px;height:{badge_height}px;padding:0;vertical-align:middle;">
                    <img src="{google_play_src}" alt="Get it on Google Play" width="{frame_width}" height="{badge_height}" class="footer-store-badge footer-store-badge-{badge_variant} footer-store-badge-google notranslate" data-notranslate="true" translate="no" data-footer-badge-render-height="{badge_height}" data-footer-badge-render-width="{frame_width}" data-footer-badge-label="Get it on Google Play" style="display:block;width:{frame_width}px;max-width:100%;height:{badge_height}px;border:0;outline:none;text-decoration:none;border-radius:8px;" />
                  </td>
                </tr>
              </table>
            </a>
          </td>
          <td style="padding-left:{td_spacing};text-align:center;vertical-align:middle;">
            <a href="{APP_STORE_URL}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:inline-block;" class="footer-badge-link footer-badge-link-app" data-footer-badge="app-store" data-footer-badge-lock-height="{badge_height}" data-footer-badge-lock-width="{frame_width}" data-notranslate="true" translate="no" aria-label="Download RealAICoach on the App Store">
              <table role="presentation" cellpadding="0" cellspacing="0" class="footer-badge-frame footer-badge-frame-app footer-badge-frame-{badge_variant}" style="width:{frame_width}px;height:{badge_height}px;margin:0 auto;">
                <tr>
                  <td align="center" valign="middle" style="width:{frame_width}px;height:{badge_height}px;padding:0;vertical-align:middle;">
                    <img src="{app_store_src}" alt="Download on the App Store" width="{frame_width}" height="{badge_height}" class="footer-store-badge footer-store-badge-{badge_variant} footer-store-badge-app notranslate" data-notranslate="true" translate="no" data-footer-badge-render-height="{badge_height}" data-footer-badge-render-width="{frame_width}" data-footer-badge-label="Download on the App Store" style="display:block;width:{frame_width}px;max-width:100%;height:{badge_height}px;border:0;outline:none;text-decoration:none;border-radius:8px;" />
                  </td>
                </tr>
              </table>
            </a>
          </td>
        </tr>
      </table>"""


def _build_global_email_footer_context(
    *,
    theme: str = "dark",
    variant: str = "full",
    recipient_email: str = "",
    reason: str = "you have an account with RealAICoach",
    show_unsub: bool = False,
    unsub_url: str = "",
    prefs_url: str = "",
) -> dict:
    support_url = _platform_url("/my-tickets", "support", "footer_support")
    contact_url = _platform_url("/contact", "support", "footer_contact")
    privacy_url = _platform_url("/privacy-policy", "legal", "footer_privacy")
    terms_url = _platform_url("/terms", "legal", "footer_terms")
    dashboard_url = _platform_url("/", "navigation", "footer_dashboard")
    settings_url = prefs_url or _platform_url("/settings?tab=notifications", "notifications", "footer_preferences")
    unsubscribe_url = unsub_url or _platform_url("/settings?tab=notifications&unsub=all", "notifications", "footer_unsubscribe")
    help_url = _platform_url("/help", "support", "footer_help")
    is_dark = theme == "dark"
    bg_main = "#060B18" if is_dark else "#F8FAFC"
    bg_card = "#0D1425" if is_dark else "#FFFFFF"
    border_c = "#1A2744" if is_dark else "#E2E8F0"
    t_primary = "#F1F5F9" if is_dark else "#0F172A"
    t_secondary = "#94A3B8" if is_dark else "#64748B"
    t_muted = "#475569" if is_dark else "#94A3B8"
    accent = "#3B82F6"
    teal = "#06D6A0"
    purple = "#8B5CF6"
    chip_bg = "#111A2E" if is_dark else "#F1F5F9"
    chip_border = "#1A2744" if is_dark else "#E2E8F0"
    chip_text = "#94A3B8" if is_dark else "#475569"
    chip_check = "#06D6A0" if is_dark else "#059669"
    year_str = __import__("datetime").datetime.now().year
    email_line = f" to <strong>{recipient_email}</strong>" if recipient_email else ""
    show_account_reason = bool(recipient_email) or variant == "compact"
    reason_copy = f"This email was sent{email_line} because {reason}." if show_account_reason else ""

    return {
        "footer_component_id": GLOBAL_EMAIL_FOOTER_COMPONENT_ID,
        "footer_version": GLOBAL_EMAIL_FOOTER_VERSION,
        "footer_last_updated": GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
        "footer_variant": variant,
        "show_full_footer": variant == "full",
        "show_compact_footer": variant == "compact",
        "show_badges_only": variant == "badges_only",
        "show_account_reason": show_account_reason,
        "show_preferences_copy": variant == "full",
        "show_unsubscribe_link": bool(show_unsub and unsubscribe_url),
        "bg_main": bg_main,
        "bg_card": bg_card,
        "border_c": border_c,
        "t_primary": t_primary,
        "t_secondary": t_secondary,
        "t_muted": t_muted,
        "accent": accent,
        "teal": teal,
        "purple": purple,
        "chip_bg": chip_bg,
        "chip_border": chip_border,
        "chip_text": chip_text,
        "chip_check": chip_check,
        "year_str": year_str,
        "brand": BRAND,
        "reason_copy": reason_copy,
        "support_url": support_url,
        "contact_url": contact_url,
        "privacy_url": privacy_url,
        "terms_url": terms_url,
        "dashboard_url": dashboard_url,
        "settings_url": settings_url,
        "unsubscribe_url": unsubscribe_url,
        "help_url": help_url,
        "store_badges_html": _official_store_badges(compact=False),
    }


def render_global_email_footer(
    *,
    theme: str = "dark",
    variant: str = "full",
    recipient_email: str = "",
    reason: str = "you have an account with RealAICoach",
    show_unsub: bool = False,
    unsub_url: str = "",
    prefs_url: str = "",
) -> str:
    template = _jinja_env.get_template(GLOBAL_EMAIL_FOOTER_TEMPLATE)
    return template.render(
        **_build_global_email_footer_context(
            theme=theme,
            variant=variant,
            recipient_email=recipient_email,
            reason=reason,
            show_unsub=show_unsub,
            unsub_url=unsub_url,
            prefs_url=prefs_url,
        )
    )


def _app_download_section() -> str:
    """Compact app download section used in newsletters (delegates to enterprise footer style)."""
    return _enterprise_footer_app_badges()


def _enterprise_footer_app_badges() -> str:
    """Standalone app badges row for newsletters — official App Store + Google Play assets."""
    return render_global_email_footer(theme="light", variant="badges_only")


def _enterprise_footer(theme: str = "dark") -> str:
    """Unified enterprise footer shared by all templates."""
    return render_global_email_footer(theme=theme, variant="full")


def _premium_mini_footer(recipient_email: str = "", reason: str = "you have an account with RealAICoach",
                          show_unsub: bool = False, unsub_url: str = "", prefs_url: str = "") -> str:
    """Premium light-themed mini footer for newsletters and transactional emails.
    Matches the enterprise footer's visual quality in a compact form."""
    return render_global_email_footer(
        theme="light",
        variant="compact",
        recipient_email=recipient_email,
        reason=reason,
        show_unsub=show_unsub,
        unsub_url=unsub_url,
        prefs_url=prefs_url,
    )
@dataclass
class EmailTemplate:
    subject: str
    html: str
    text: str


# ═══════════════════════════════════════════════════════════
#  Base layout — dark, modern, inline-styled for email clients
# ═══════════════════════════════════════════════════════════


def _responsive_styles() -> str:
    """Responsive CSS for email templates — Mobile/Tablet/Desktop + Dark Mode.
    LOCKED: Enterprise-grade responsive styles applied to all 42+ templates."""
    return (
        """<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style type="text/css">
    :root{color-scheme:light dark;supported-color-schemes:light dark}
    body,table,td,p,a,li{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}
    table,td{mso-table-lspace:0pt;mso-table-rspace:0pt}
    img{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none}
    .email-card{width:100%!important;max-width:560px!important}
    .email-cta-stack{width:100%!important}
    .email-primary-cta{display:inline-block!important}
    .email-secondary-cta{display:inline-block!important;background:transparent!important;border:1px solid #3B82F6!important;color:#3B82F6!important;border-radius:99px!important}
    .email-header-shell{border-bottom:1px solid #93C5FD}
    .email-header-logo-fallback{background:rgba(255,255,255,0.15);color:#ffffff}
    .email-header-kicker{color:#BFDBFE}
    .email-header-pill{background-color:#1E40AF;border:1px solid #3B82F6;color:#FFFFFF}
    .email-header-wordmark{color:#FFFFFF}
    .email-header-trust{background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.24);color:#FFFFFF}
    .em-footer-chip{background:#F1F5F9;border:1px solid #E2E8F0;color:#475569}
    .footer-store-badge{display:block!important;width:auto!important;max-width:100%;height:auto;border:0;outline:none;text-decoration:none}
    .footer-store-badge-regular{height:__REGULAR_HEIGHT__px!important;max-height:__REGULAR_HEIGHT__px!important}
    .footer-store-badge-compact{height:__COMPACT_HEIGHT__px!important;max-height:__COMPACT_HEIGHT__px!important}
    @media only screen and (max-width:479px){
      .email-outer{padding:12px 4px!important}
      .email-card{border-radius:14px!important}
      .email-header{padding:22px 16px 18px!important}
      .email-header-title{font-size:18px!important}
      .email-header-wordmark{font-size:16px!important}
      .email-header-trust{font-size:9px!important;letter-spacing:0.5px!important;padding:4px 10px!important}
      .email-body{padding:18px 16px!important}
      .email-cta td{border-radius:14px!important}
      .email-cta a{padding:16px 48px!important;font-size:15px!important}
      .email-cta-stack td{display:block!important;width:100%!important;padding:0!important;text-align:center!important}
      .email-primary-cta{padding:15px 36px!important;font-size:15px!important}
      .email-secondary-cta{margin-top:10px!important;padding:12px 24px!important;font-size:13px!important}
      .footer-app-section{padding:22px 14px 16px!important}
      .footer-app-title{font-size:17px!important}
      .footer-badge-row td{display:block!important;padding:4px 0!important;text-align:center!important}
      .footer-badge-row a{display:inline-block!important}
      .footer-store-badge-regular{height:__MOBILE_REGULAR_HEIGHT__px!important;max-height:__MOBILE_REGULAR_HEIGHT__px!important}
      .footer-store-badge-compact{height:__MOBILE_COMPACT_HEIGHT__px!important;max-height:__MOBILE_COMPACT_HEIGHT__px!important}
      .footer-nav-section{padding:10px 14px!important}
      .footer-nav-section a{font-size:11px!important;padding:4px 6px!important}
      .footer-brand-section{padding:24px 14px 12px!important}
      .footer-brand-name{font-size:21px!important}
      .footer-address{font-size:10px!important}
      .footer-trust-row td{padding:0 2px!important}
      .em-footer-chip{font-size:9px!important;padding:5px 8px!important}
      .footer-social-row td{padding:0 3px!important}
      .footer-support-row td{padding:0 3px!important}
      .footer-support-row a{padding:7px 14px!important;font-size:11px!important}
      .footer-legal-section{padding:12px 14px 18px!important}
      .footer-legal-text{font-size:9px!important;line-height:1.6!important}
    }
    @media only screen and (min-width:480px) and (max-width:599px){
      .email-outer{padding:20px 8px!important}
      .email-header{padding:28px 22px 22px!important}
      .email-header-title{font-size:20px!important}
      .email-body{padding:22px 20px!important}
    }
    @media (prefers-color-scheme:dark){
      .email-outer{background-color:#0B0F1A!important}
      .email-card{background-color:#111827!important;border-color:#1E293B!important}
      .email-body{background-color:transparent!important;color:#E2E8F0!important}
      .em-outer{background-color:#0B0F1A!important}
      .em-card{background-color:#111827!important;border-color:#1E293B!important;border-style:solid!important}
      .em-body{background-color:transparent!important;color:#E2E8F0!important}
      .em-body p,.em-body li,.em-body div,.email-body p,.email-body li,.email-body div{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
      .em-title{color:#F1F5F9!important}
      .em-text{color:#CBD5E1!important}
      .em-text-secondary{color:#94A3B8!important}
      .em-text-muted{color:#94A3B8!important}
      .em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
      .em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
      .em-info-val{color:#0F172A!important}
      .em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
      .em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
      .em-tip-box{background:#1E293B!important;border-color:#334155!important}
      .em-tip-title{color:#F1F5F9!important}
      .em-tip-list,.em-tip-list li{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
      .em-alert{background:#FFFFFF!important;border-color:#E2E8F0!important}
      .em-alert-title{color:#0F172A!important}
      .em-alert-text{color:#475569!important}
      .em-lead{color:#F1F5F9!important}
      .em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-step-title{color:#0F172A!important}
      .em-strong{color:#F1F5F9!important}
      .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-force-dark-text{color:#0F172A!important}
      .em-force-muted-text{color:#64748B!important}
      .em-force-light-card p,.em-force-light-card div,.em-force-light-card span,.em-force-light-card td,.em-force-light-card th,.em-force-light-card li{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-force-light-card .em-force-muted-text{color:#475569!important;-webkit-text-fill-color:#475569!important}
      .em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;mix-blend-mode:normal!important}
      .em-info-tbl{border-color:#E2E8F0!important}
      .em-info-tbl td{border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-callout{border-color:#E2E8F0!important;color:#374151!important;-webkit-text-fill-color:#374151!important}
      .em-step-td{border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .email-header-kicker,.em-header-kicker{color:rgba(255,255,255,0.75)!important;-webkit-text-fill-color:rgba(255,255,255,0.75)!important}
      .email-header-pill,.em-header-pill{background:rgba(0,0,0,0.25)!important;border-color:rgba(255,255,255,0.2)!important;color:#FFFFFF!important}
      .email-header-logo-fallback,.em-header-logo-fallback{background:rgba(255,255,255,0.15)!important;color:#FFFFFF!important}
      .email-header-wordmark{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
      .email-header-trust{background:rgba(0,0,0,0.25)!important;border-color:rgba(255,255,255,0.18)!important;color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
      .em-footer-chip{background:#111A2E!important;border-color:#1A2744!important;color:#94A3B8!important;-webkit-text-fill-color:#94A3B8!important}
      .em-footer-chip-check{color:#06D6A0!important;-webkit-text-fill-color:#06D6A0!important}
      .em-footer-bg{background:#060B18!important}
      .em-footer-card{background:#0D1425!important;border-color:#1A2744!important}
      .em-footer-t1{color:#F1F5F9!important}
      .em-footer-t2{color:#94A3B8!important}
      .em-footer-t3{color:#475569!important}
      .compact-footer-shell{background:#0D1425!important;border-color:#1A2744!important}
      .compact-footer-copy,.compact-footer-copy *{color:#94A3B8!important;-webkit-text-fill-color:#94A3B8!important}
      .compact-footer-link{color:#93C5FD!important;-webkit-text-fill-color:#93C5FD!important}
      .compact-footer-link-secondary{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
      .email-secondary-cta{background:rgba(255,255,255,0.06)!important;border-color:#334155!important;color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
      .em-badge{border-style:solid!important}
      .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
      .em-body .email-primary-cta,.email-body .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
      .em-info-val:not(.em-info-val-accent){color:#E2E8F0!important}
      .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-force-light-card *{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
      .em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;mix-blend-mode:normal!important}
      a{color:#93C5FD!important}
      .em-body a,.email-body a{-webkit-text-fill-color:#93C5FD!important}
      .footer-store-badge{background:transparent!important}
    }
    /* ── Outlook Desktop Dark Mode: Preserve v7 Colorful Design ── */
    /* Desktop Outlook ignores @media(prefers-color-scheme) — uses [data-ogsc]/[data-ogsb] instead */
    /* We force LIGHT backgrounds so colorful gradient headers remain vibrant */
    [data-ogsc] .em-outer{background:#F1F5F9!important}
    [data-ogsc] .em-card{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .em-body{color:#374151!important}
    [data-ogsc] .email-outer{background:#F1F5F9!important}
    [data-ogsc] .email-card{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .email-body{color:#374151!important}
    [data-ogsc] .em-body p,[data-ogsc] .em-body li,[data-ogsc] .em-body div,[data-ogsc] .email-body p,[data-ogsc] .email-body li,[data-ogsc] .email-body div{color:#374151!important;-webkit-text-fill-color:#374151!important}
    [data-ogsc] .em-title{color:#0F172A!important}
    [data-ogsc] .em-text{color:#374151!important}
    [data-ogsc] .em-text-secondary{color:#64748B!important}
    [data-ogsc] .em-text-muted{color:#94A3B8!important}
    [data-ogsc] .em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
    [data-ogsc] .em-info-val{color:#0F172A!important}
    [data-ogsc] .email-header-kicker,[data-ogsc] .em-header-kicker{color:rgba(255,255,255,0.75)!important;-webkit-text-fill-color:rgba(255,255,255,0.75)!important}
    [data-ogsc] .email-header-pill,[data-ogsc] .em-header-pill{background:rgba(255,255,255,0.2)!important;border-color:rgba(255,255,255,0.35)!important;color:#FFFFFF!important}
    [data-ogsc] .email-header-logo-fallback,[data-ogsc] .em-header-logo-fallback{background:rgba(255,255,255,0.15)!important;color:#FFFFFF!important}
    [data-ogsc] .email-header-wordmark{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
    [data-ogsc] .email-header-trust{background:rgba(255,255,255,0.18)!important;border-color:rgba(255,255,255,0.3)!important;color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
    [data-ogsc] .em-footer-chip{background:#F1F5F9!important;border-color:#E2E8F0!important;color:#475569!important;-webkit-text-fill-color:#475569!important}
    [data-ogsc] .em-footer-chip-check{color:#059669!important;-webkit-text-fill-color:#059669!important}
    [data-ogsc] .em-footer-bg{background:#F8FAFC!important}
    [data-ogsc] .em-footer-card{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .em-footer-t1{color:#0F172A!important}
    [data-ogsc] .em-footer-t2{color:#64748B!important}
    [data-ogsc] .em-footer-t3{color:#94A3B8!important}
    [data-ogsc] .compact-footer-shell{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .compact-footer-copy,[data-ogsc] .compact-footer-copy *{color:#64748B!important;-webkit-text-fill-color:#64748B!important}
    [data-ogsc] .compact-footer-link{color:#2563EB!important;-webkit-text-fill-color:#2563EB!important}
    [data-ogsc] .compact-footer-link-secondary{color:#64748B!important;-webkit-text-fill-color:#64748B!important}
    [data-ogsc] .em-badge{border-style:solid!important;color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
    [data-ogsc] .em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
    [data-ogsc] .em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
    [data-ogsc] .em-tip-box{background:#F8FAFC!important;border-color:#E2E8F0!important}
    [data-ogsc] .em-tip-title{color:#0F172A!important}
    [data-ogsc] .em-tip-list,[data-ogsc] .em-tip-list li{color:#374151!important;-webkit-text-fill-color:#374151!important}
    [data-ogsc] .em-alert{background:#FFFFFF!important;border-color:#E2E8F0!important}
    [data-ogsc] .em-alert-title{color:#0F172A!important}
    [data-ogsc] .em-alert-text{color:#475569!important}
    [data-ogsc] .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
    [data-ogsc] .em-body .email-primary-cta,[data-ogsc] .email-body .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
    [data-ogsc] .em-info-val:not(.em-info-val-accent){color:#0F172A!important}
    [data-ogsc] .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
    [data-ogsc] .em-force-light-card *{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
    [data-ogsc] .em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;mix-blend-mode:normal!important}
    [data-ogsc] .em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
    [data-ogsc] .footer-store-badge{background:transparent!important}
    </style>"""
        .replace("__REGULAR_HEIGHT__", str(STORE_BADGE_REGULAR_HEIGHT))
        .replace("__COMPACT_HEIGHT__", str(STORE_BADGE_COMPACT_HEIGHT))
        .replace("__MOBILE_REGULAR_HEIGHT__", str(STORE_BADGE_MOBILE_REGULAR_HEIGHT))
        .replace("__MOBILE_COMPACT_HEIGHT__", str(STORE_BADGE_MOBILE_COMPACT_HEIGHT))
    )


def _get_inline_logo() -> str:
    """Return CDN-hosted app logo URL for maximum email client compatibility."""
    from utils.email_service import CDN_APP_LOGO
    return CDN_APP_LOGO


def _wrap(
    title: str,
    preheader: str,
    inner_html: str,
    cta_label: str = "",
    cta_url: str = "",
    accent: str = "",
    footer: str = "",
    secondary_cta_label: str = "",
    secondary_cta_url: str = "",
    category: str = "",
) -> str:
    """Render the base email layout using Jinja2 template engine."""
    if (footer or "").strip():
        raise ValueError("Custom footer overrides are prohibited. Use render_global_email_footer().")

    c = accent or PRIMARY
    resolved_category = category or _ACTIVE_CATEGORY[0]
    cc = _cat_colors(resolved_category)
    # Keep primary CTA legible with white text. If provided accent is too light,
    # switch to category button-primary fallback (or global primary fallback).
    if cta_label and _badge_contrast_text(c) != "#FFFFFF":
        c = cc.get("pb") or PRIMARY
    normalized_cta_url = _to_absolute_https(cta_url, "/") if cta_label else ""
    resolved_secondary_label = (secondary_cta_label or "").strip()
    resolved_secondary_url = ""
    # Auto-add "Need help?" secondary CTA unless primary CTA is already support-related
    support_cta_labels = {"contact support", "get help", "need help", "talk to us", "reach out"}
    primary_is_support = cta_label and cta_label.strip().lower() in support_cta_labels
    if cta_label and not resolved_secondary_label and not primary_is_support:
        resolved_secondary_label = "Need help?"
        resolved_secondary_url = _to_absolute_https(SUPPORT_URL, "/my-tickets")
    elif resolved_secondary_label:
        resolved_secondary_url = _to_absolute_https(secondary_cta_url or SUPPORT_URL, "/my-tickets")

    _logo_src = _get_inline_logo()
    _logo_cell = (
        f'<img src="{_logo_src}" alt="{BRAND}" width="40" height="40" style="width:40px;height:40px;border-radius:12px;display:block;border:1px solid rgba(255,255,255,0.35);" />'
        if _logo_src
        else '<div class="email-header-logo-fallback em-header-logo-fallback" style="width:40px;height:40px;border-radius:12px;background:rgba(255,255,255,0.18);color:#FFFFFF;font-size:16px;font-weight:800;line-height:40px;text-align:center;">RA</div>'
    )
    logo_html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" class="email-header-lockup"><tr>'
        f'<td style="vertical-align:middle;">{_logo_cell}</td>'
        '<td style="vertical-align:middle;padding-left:11px;">'
        '<span class="email-header-wordmark notranslate" translate="no" style="font-size:18px;font-weight:900;letter-spacing:-0.4px;color:#FFFFFF;font-family:-apple-system,Helvetica,Arial,sans-serif;">'
        f'Real<span style="color:{cc["kk"]};">AI</span>Coach</span>'
        '</td></tr></table>'
    )
    footer_html = render_global_email_footer(theme="light", variant="full")

    cat_label = (resolved_category or "").replace("_", " ").strip().upper()

    try:
        template = _jinja_env.get_template("email_base.html")
        html = template.render(
            title=title,
            preheader=preheader,
            inner_html=inner_html,
            cta_label=cta_label,
            cta_url=normalized_cta_url,
            secondary_cta_label=resolved_secondary_label,
            secondary_cta_url=resolved_secondary_url,
            accent=c,
            brand=BRAND,
            logo_html=logo_html,
            footer_html=footer_html,
            header_grad_from=cc["gf"],
            header_grad_to=cc["gt"],
            header_border=cc["bd"],
            header_kicker=cc["kk"],
            header_pill_bg=cc["pb"],
            header_pill_label=cat_label or BRAND,
            card_tint=cc.get("ct", "#FFFFFF"),
            card_border=cc.get("cb", "#E2E8F0"),
            store_badge_regular_height=STORE_BADGE_REGULAR_HEIGHT,
            store_badge_compact_height=STORE_BADGE_COMPACT_HEIGHT,
            store_badge_mobile_regular_height=STORE_BADGE_MOBILE_REGULAR_HEIGHT,
            store_badge_mobile_compact_height=STORE_BADGE_MOBILE_COMPACT_HEIGHT,
        )
        return enforce_brand_translation_exclusion(_normalize_email_links(html))
    except Exception:
        # Fallback to inline rendering if Jinja2 template fails
        html = _wrap_inline(
            title,
            preheader,
            inner_html,
            cta_label,
            normalized_cta_url,
            resolved_secondary_label,
            resolved_secondary_url,
            c,
            logo_html,
            footer_html,
            cc,
            cat_label,
        )
        return enforce_brand_translation_exclusion(_normalize_email_links(html))


def _wrap_inline(
    title: str, preheader: str, inner_html: str,
    cta_label: str, cta_url: str,
    secondary_cta_label: str, secondary_cta_url: str,
    accent: str,
    logo_html: str, footer_html: str,
    cc: dict = None, cat_label: str = "",
) -> str:
    """Inline fallback renderer — auto-adaptive light/dark mode via CSS classes."""
    if cc is None:
        cc = _DEFAULT_CAT
    grad_from, grad_to, _hdr_border, _kicker_color, _pill_bg = cc["gf"], cc["gt"], cc["bd"], cc["kk"], cc["pb"]
    brand_mark_html = (
        logo_html
        or '<div class="email-header-logo-fallback em-header-logo-fallback" style="width:40px;height:40px;border-radius:12px;background:rgba(255,255,255,0.18);color:#ffffff;font-size:16px;font-weight:800;line-height:40px;text-align:center;">RA</div>'
    )
    cta = ""
    if cta_label and cta_url:
        secondary_cta = ""
        if secondary_cta_label and secondary_cta_url:
            secondary_cta = f'''<tr><td align="center" style="padding-top:12px;">
              <a href="{secondary_cta_url}" target="_blank" rel="noopener noreferrer" class="email-secondary-cta" style="background:transparent;border:1px solid {accent};border-radius:99px;display:inline-block;padding:11px 26px;color:{accent};font-size:13px;font-weight:700;text-decoration:none;letter-spacing:0.2px;mso-line-height-rule:exactly;line-height:1.2;text-align:center;">{secondary_cta_label}</a>
            </td></tr>'''

        cta = f'''<table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px auto 0;" class="email-cta email-cta-stack">
          <tr><td align="center" bgcolor="{accent}" style="border-radius:14px;background:{accent};text-align:center;">
            <a href="{cta_url}" target="_blank" rel="noopener noreferrer" class="email-primary-cta" style="background:{accent};border-radius:14px;display:inline-block;padding:20px 72px;color:#FFFFFF;font-size:17px;font-weight:800;text-decoration:none;letter-spacing:0.5px;mso-line-height-rule:exactly;line-height:1.2;text-align:center;">{cta_label}</a>
          </td></tr>{secondary_cta}</table>'''

    return f"""<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/><title>{title}</title>{_responsive_styles()}</head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;" class="em-outer">
<span style="display:none;max-height:0;overflow:hidden;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F1F5F9;padding:40px 16px;" class="email-outer em-outer">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border-radius:20px;border:1px solid #E2E8F0;overflow:hidden;" class="email-card em-card" data-theme-light="v7" data-theme-dark="v7">
  <tr><td class="email-header email-header-shell em-header" style="background-color:{grad_from};background-image:linear-gradient(135deg,{grad_from},{grad_to});padding:30px 32px 26px;border-bottom:none;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;">{brand_mark_html}</td>
      <td align="right" style="vertical-align:middle;"><span class="email-header-pill em-header-pill notranslate" translate="no" style="display:inline-block;padding:7px 15px;background-color:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.35);color:#FFFFFF;font-size:10px;font-weight:800;border-radius:99px;letter-spacing:1.1px;text-transform:uppercase;">{cat_label or BRAND}</span></td>
    </tr></table>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:20px 0 12px;">
      <span class="email-header-trust" style="display:inline-block;padding:5px 12px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.24);border-radius:99px;color:#FFFFFF;font-size:10px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;"><span style="font-weight:900;">&#10003;</span>&nbsp;Verified sender&nbsp;&nbsp;&middot;&nbsp;&nbsp;Secure communication</span>
    </td></tr></table>
    <div class="email-header-title" style="font-size:24px;font-weight:800;color:#FFFFFF;letter-spacing:-0.4px;line-height:1.25;">{title}</div>
  </td></tr>
  <tr><td class="email-body em-body" style="padding:0 32px 28px;color:#374151;font-size:14px;line-height:1.75;background-color:{grad_from};background-image:linear-gradient(to bottom,{grad_to},{cc.get('ct','#FFFFFF')} 60px);">
    <div class="email-content-shell em-force-light-card" style="background:{cc.get('ct','#FFFFFF')};border:1px solid {cc.get('cb','#E2E8F0')};border-radius:16px;padding:18px 20px;color:#0F172A;box-sizing:border-box;">
      {inner_html}
    </div>
    {cta}
  </td></tr>
  {footer_html}
</table>
</td></tr></table>
</body></html>"""


def _txt(title: str, body: str, cta_label: str = "", cta_url: str = "") -> str:
    t = f"{title}\n{'─' * 40}\n\n{body}\n"
    if cta_label and cta_url:
        t += f"\n{cta_label}: {cta_url}\n"
    t += f"\n— {BRAND}"
    return t


def _color_tint(hex_color: str, alpha_byte: int = 0x18, bg: str = "#F1F5F9") -> str:
    """Blend a hex color with a background at given alpha to produce a solid color.
    Replaces 8-digit hex (unsupported by email clients) with a solid equivalent."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    br = int(bg[1:3], 16)
    bg_ = int(bg[3:5], 16)
    bb = int(bg[5:7], 16)
    a = alpha_byte / 255
    nr = int(a * r + (1 - a) * br)
    ng = int(a * g + (1 - a) * bg_)
    nb = int(a * b + (1 - a) * bb)
    return f"#{nr:02X}{ng:02X}{nb:02X}"


def _badge_contrast_text(background_hex: str) -> str:
    background = (background_hex or "").strip().upper()
    if not (background.startswith("#") and len(background) == 7):
        return "#FFFFFF"
    try:
        bg_rgb = (
            int(background[1:3], 16),
            int(background[3:5], 16),
            int(background[5:7], 16),
        )
    except Exception:
        return "#FFFFFF"

    def _rel(rgb: tuple[int, int, int]) -> float:
        def _channel(c: int) -> float:
            x = c / 255.0
            return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

        r, g, b = rgb
        return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)

    def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
        l1, l2 = _rel(a), _rel(b)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    candidates = [
        ("#FFFFFF", (255, 255, 255)),
        ("#0F172A", (15, 23, 42)),
        ("#000000", (0, 0, 0)),
    ]
    best = max(candidates, key=lambda item: _contrast(item[1], bg_rgb))
    return best[0]


def _badge(text: str, color: str) -> str:
    border = _color_tint(color, 0x60)
    text_color = _badge_contrast_text(color)
    return f'<span class="em-badge" style="display:inline-block;padding:5px 16px;background:{color};color:{text_color};border:1px solid {border};font-size:11px;font-weight:800;border-radius:99px;letter-spacing:0.5px;-webkit-text-fill-color:{text_color};">{text}</span>'


def _info_row(label: str, value: str, val_color: str = "#0F172A") -> str:
    # Use em-info-val-accent class for colored values to preserve color in dark mode
    val_cls = "em-info-val em-info-val-accent" if val_color != "#0F172A" else "em-info-val"
    return f'<tr><td class="em-info-td" style="padding:10px 14px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;">{label}</td><td class="{val_cls}" style="padding:10px 14px;text-align:right;font-weight:600;color:{val_color};font-size:13px;border-bottom:1px solid #E2E8F0;">{value}</td></tr>'


def _info_table(rows: list) -> str:
    inner = "".join(rows)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl em-force-light-card" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;margin:20px 0;overflow:hidden;">{inner}</table>'


def _callout(text: str, color: str = "") -> str:
    c = color or PRIMARY
    return f'<div class="em-callout em-force-light-card" style="background:#FFFFFF;border:1px solid {_color_tint(c, 0x35)};border-left:3px solid {c};border-radius:12px;padding:14px 18px;margin:18px 0;font-size:13px;color:#374151;line-height:1.7;">{text}</div>'


def _light_locked_tip_card(title: str, bullets: list[str], accent: str = "#991B1B") -> str:
    """Render a dark-mode-safe tip card.

    Uses `em-force-light-card` to prevent client dark-mode color inversions that
    can make warning copy unreadable (especially in Gmail/Outlook variants).
    """
    bullet_items = "".join(
        [
            f'<li class="em-force-muted-text" style="margin:0 0 4px;color:#475569;">{item}</li>'
            for item in bullets
        ]
    )
    return f"""<div class="em-force-light-card" style="margin:14px 0 0;padding:12px 14px;border:1px solid #FCA5A5;background:#FFFFFF;border-radius:10px;">
      <p class="em-force-dark-text" style="margin:0 0 8px;font-size:12px;font-weight:700;color:{accent};">{title}</p>
      <ul style="margin:0;padding-left:18px;font-size:12px;line-height:1.6;color:#475569;">
        {bullet_items}
      </ul>
    </div>"""


def _alert_panel(title: str, subtitle: str, color: str, badge_text: str = "") -> str:
    badge_html = _badge(badge_text, color) + "<br/>" if badge_text else ""
    return f"""<div class="em-alert" style="background:{_color_tint(color, 0x18)};border:1px solid {_color_tint(color, 0x35)};border-radius:14px;padding:16px 20px;margin:0 0 20px;text-align:center;">
      {badge_html}
      <p class="em-alert-title" style="color:{color};font-weight:800;font-size:16px;margin:8px 0 4px;-webkit-text-fill-color:{color};">{title}</p>
      <p class="em-alert-text em-text" style="color:#374151;font-size:13px;line-height:1.6;margin:0;-webkit-text-fill-color:#374151;">{subtitle}</p>
    </div>"""


def _lead(title: str, body: str) -> str:
    return f'<p class="em-lead em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">{title}</p><p class="em-text" style="margin:0 0 16px;">{body}</p>'


# ═══════════════════════════════════════════════════════════
#  TEMPLATE CATALOG — used by admin preview + real sends
# ═══════════════════════════════════════════════════════════

# Registry for admin preview
TEMPLATE_CATALOG = {}


def _register(key: str, label: str, category: str, description: str):
    """Decorator to register a template builder in the catalog."""

    def decorator(fn):
        wrapped_builder = fn
        if not getattr(fn, "_template_campaign_wrapped", False):
            @wraps(fn)
            def wrapped_builder(*args, **kwargs):
                _ACTIVE_CATEGORY[0] = category
                result = fn(*args, **kwargs)
                _ACTIVE_CATEGORY[0] = ""
                if isinstance(result, EmailTemplate):
                    campaign = _campaign_name_for_template(key, category)
                    return EmailTemplate(
                        subject=result.subject,
                        html=_apply_template_campaign(result.html, campaign),
                        text=result.text,
                    )
                return result

            setattr(wrapped_builder, "_template_campaign_wrapped", True)

        TEMPLATE_CATALOG[key] = {
            "key": key,
            "label": label,
            "category": category,
            "description": description,
            "builder": wrapped_builder,
        }
        return wrapped_builder

    return decorator


# ── 1. Welcome ──────────────────────────────────────────


@_register("welcome", "Welcome Email", "Onboarding", "Sent when a new user registers")
def build_welcome_email(user_name: str = "Alex", onboarding_steps: List[str] = None) -> EmailTemplate:
    steps = onboarding_steps or [
        "Complete your profile",
        "Start your first coaching session",
        "Explore the resource library",
    ]
    steps_html = "".join(
        [
            f'<tr><td class="em-info-td" style="padding:10px 14px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><span style="display:inline-block;width:22px;height:22px;background:{PRIMARY};color:#fff;border-radius:50%;text-align:center;line-height:22px;font-size:11px;font-weight:700;margin-right:10px;">{i + 1}</span>{s}</td></tr>'
            for i, s in enumerate(steps)
        ]
    )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Welcome aboard, {user_name}!</p>
    <p style="margin:0 0 16px;">Your account has been created successfully. Please check your email inbox to confirm your account.</p>
    {_callout("Check your email to confirm your account. Look for a verification email from us and click the link inside to activate your account.", "#10B981")}
    <p class="em-strong" style="margin:16px 0 6px;color:#0F172A;font-weight:600;">Here are your first steps:</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">{steps_html}</table>"""
    return EmailTemplate(
        subject=f"Welcome to {BRAND}, {user_name} — Confirm Your Account",
        html=_wrap(
            "Welcome to " + BRAND,
            "Check your email to confirm your account",
            body,
            "Start Using Our Platform",
            DASH_URL,
        ),
        text=_txt(
            "Welcome",
            f"Hi {user_name}, your account has been created.\n\nCheck your email to confirm your account.\n\n"
            + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps)),
            "Start Using Our Platform",
            DASH_URL,
        ),
    )


# ── 2. Account Verification ────────────────────────────


@_register("account_verification", "Account Verification", "Onboarding", "Email verification link for new accounts")
def build_account_verification_email(
    user_name: str = "Alex", verify_link: str = "", expiry_hours: int = 24
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Verify your email, {user_name}</p>
    <p style="margin:0 0 16px;">Click the button below to confirm your email address and activate your account.</p>
    {_callout(f"This link expires in <strong>{expiry_hours} hours</strong>. If you didn't create this account, ignore this email.")}"""
    return EmailTemplate(
        subject=f"Verify your {BRAND} email",
        html=_wrap("Verify Your Email", "Confirm your email address", body, "Verify Email", verify_link or f"{DASH_URL}/auth/login", "#10B981"),
        text=_txt(
            "Verify Email", f"Hi {user_name}, verify your email: {verify_link}\nExpires in {expiry_hours} hours."
        ),
    )


# ── 3. Password Reset ──────────────────────────────────


@_register("gdpr_export_ready", "GDPR Export Ready", "Compliance", "1-click data export download link for GDPR/CCPA self-service")
def build_gdpr_export_ready_email(
    download_link: str = "",
    review_link: str = "",
    request_id: str = "",
    expiry_minutes: int = 15,
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your data export is ready</p>
    <p style="margin:0 0 14px;">We received a request to export all data associated with this email address on {BRAND} — your contact form submissions, support tickets, and feedback entries.</p>
    <p style="margin:0 0 16px;">Click the button below to download everything as a single JSON file.</p>
    {_info_table([
        _info_row("Expires in", f"{expiry_minutes} minutes", "#F59E0B"),
        _info_row("Format", "JSON download"),
        _info_row("Request ID", request_id or "—"),
    ])}
    {_callout("If you didn't request this, ignore this email — the link will expire and no data will leave our systems.", "#F59E0B")}
    <p style="margin:20px 0 0;font-size:13px;color:#475569;">Prefer to review a summary first? <a href="{review_link}" style="color:#4F46E5;text-decoration:underline;">Open the review page</a> to see per-collection record counts before downloading.</p>"""
    return EmailTemplate(
        subject="Your data export is ready — click to download",
        html=_wrap(
            "Data Export Ready",
            "Download your data",
            body,
            "Download My Data",
            download_link or f"{DASH_URL}",
            "#4F46E5",
        ),
        text=_txt(
            "Data Export Ready",
            f"Your data export is ready. Click to download (expires in {expiry_minutes} minutes): {download_link}\n\n"
            f"Prefer to review first? {review_link}\nRequest ID: {request_id}",
            "Download My Data",
            download_link,
        ),
    )


@_register("gdpr_delete_verify", "GDPR Delete Verify", "Compliance", "Email verification for data deletion under GDPR/CCPA")
def build_gdpr_delete_verify_email(
    verify_link: str = "",
    request_id: str = "",
    expiry_minutes: int = 15,
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Confirm permanent deletion</p>
    <p style="margin:0 0 14px;">We received a request to <strong style="color:#DC2626;">permanently delete</strong> all data associated with this email address on {BRAND} — your contact form submissions, support tickets, and feedback entries.</p>
    <p style="margin:0 0 16px;">This cannot be undone. To confirm and execute the deletion, click the button below within <strong>{expiry_minutes} minutes</strong>.</p>
    {_info_table([
        _info_row("Expires in", f"{expiry_minutes} minutes", "#F59E0B"),
        _info_row("Action", "Permanent deletion", "#DC2626"),
        _info_row("Request ID", request_id or "—"),
    ])}
    {_callout("If you didn't request this, ignore this email — the link will expire and no changes will be made.", "#F59E0B")}"""
    return EmailTemplate(
        subject="Verify your data deletion request",
        html=_wrap(
            "Deletion Verification",
            "Confirm permanent deletion",
            body,
            "Confirm Delete Request",
            verify_link or f"{DASH_URL}",
            "#EF4444",
        ),
        text=_txt(
            "Deletion Verification",
            f"Confirm permanent deletion of your data (expires in {expiry_minutes} minutes): {verify_link}\n\n"
            f"Request ID: {request_id}\n\nIf you didn't request this, ignore this email.",
            "Confirm Delete Request",
            verify_link,
        ),
    )


@_register("gdpr_weekly_digest", "GDPR Weekly Digest", "Compliance", "Weekly compliance pulse of GDPR self-service activity")
def build_gdpr_weekly_digest_email(
    window_days: int = 7,
    total_requests: int = 0,
    export_requests: int = 0,
    delete_requests: int = 0,
    completed: int = 0,
    pending: int = 0,
    unverified_abandoned: int = 0,
    exported_records: int = 0,
    deleted_records: int = 0,
    dashboard_link: str = "",
) -> EmailTemplate:
    abandon_callout = (
        _callout(
            f"<strong>{unverified_abandoned}</strong> request(s) expired without email-link verification in this window.",
            "#F59E0B",
        )
        if unverified_abandoned
        else ""
    )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">GDPR Weekly Compliance Digest</p>
    <p style="margin:0 0 14px;color:#475569;">Window: last <strong>{window_days}</strong> days · {BRAND}</p>
    {_info_table([
        _info_row("Total requests", str(total_requests)),
        _info_row("Exports completed", str(export_requests), "#10B981"),
        _info_row("Deletions completed", str(delete_requests), "#DC2626"),
        _info_row("Pending email verification", str(pending), "#F59E0B"),
        _info_row("Records exported (total)", str(exported_records)),
        _info_row("Records deleted permanently", str(deleted_records), "#DC2626"),
    ])}
    {abandon_callout}
    <p style="margin:16px 0 0;font-size:13px;color:#475569;">All activity is logged in the permanent audit trail.</p>"""
    return EmailTemplate(
        subject=f"[GDPR] Weekly compliance digest — {total_requests} request(s)",
        html=_wrap(
            "Weekly Compliance Digest",
            "GDPR self-service activity",
            body,
            "Open Compliance Dashboard",
            dashboard_link or f"{DASH_URL}/admin/gdpr-requests",
            "#4F46E5",
        ),
        text=_txt(
            "GDPR Weekly Compliance Digest",
            f"Last {window_days} days on {BRAND}:\n"
            f"- Total requests: {total_requests}\n"
            f"- Exports completed: {export_requests}\n"
            f"- Deletions completed: {delete_requests}\n"
            f"- Pending verify: {pending}\n"
            f"- Records exported: {exported_records}\n"
            f"- Records deleted: {deleted_records}\n"
            f"- Unverified abandoned: {unverified_abandoned}",
            "Open Compliance Dashboard",
            dashboard_link,
        ),
    )


@_register(
    "platform_compliance_daily_digest",
    "Platform Compliance Daily Digest",
    "Compliance",
    "Daily platform compliance digest with support/security/FAQ governance metrics",
)
def build_platform_compliance_daily_digest_email(
    severity: str = "low",
    support_open_nudges: int = 0,
    support_escalated_open: int = 0,
    security_high_critical_24h: int = 0,
    faq_languages_missing: str = "none",
    dashboard_link: str = "",
) -> EmailTemplate:
    sev = (severity or "low").upper()
    sev_color = "#EF4444" if sev in {"HIGH", "CRITICAL"} else ("#F59E0B" if sev == "MEDIUM" else "#10B981")
    body = f"""{_alert_panel(
        "Platform Compliance Daily Digest",
        f"Severity {sev} · compliance control summary",
        sev_color,
        sev,
    )}
    {_info_table([
        _info_row("Open support nudges", str(support_open_nudges), "#2563EB"),
        _info_row("Escalated support tickets", str(support_escalated_open), "#F59E0B"),
        _info_row("Security high/critical (24h)", str(security_high_critical_24h), "#EF4444"),
        _info_row("FAQ language gaps", faq_languages_missing or "none", "#64748B"),
    ])}
    {_callout("Generated by the compliance digest hub with V7 template enforcement enabled.", "#2563EB")}"""

    return EmailTemplate(
        subject=f"Platform Compliance Daily · {sev} · {support_open_nudges} open nudges",
        html=_wrap(
            "Compliance Daily Digest",
            f"Severity {sev}",
            body,
            "Open Compliance Console",
            dashboard_link or f"{DASH_URL}/admin-console?tab=compliance-digest",
            sev_color,
            category="compliance",
        ),
        text=_txt(
            "Platform Compliance Daily Digest",
            f"Severity: {sev}\n"
            f"Open support nudges: {support_open_nudges}\n"
            f"Escalated tickets: {support_escalated_open}\n"
            f"Security high/critical (24h): {security_high_critical_24h}\n"
            f"FAQ language gaps: {faq_languages_missing or 'none'}",
            "Open Compliance Console",
            dashboard_link,
        ),
    )


@_register("password_reset", "Password Reset", "Security", "Password reset link email")
def build_password_reset_email(reset_link: str = "", expiry_minutes: int = 15) -> EmailTemplate:
    body = f"""<p style="margin:0 0 16px;">We received a request to reset your password. Use the button below to create a new one.</p>
    {_info_table([_info_row("Expires in", f"{expiry_minutes} minutes", "#F59E0B"), _info_row("Request type", "Password Reset")])}
    {_callout("If you didn't request this, you can safely ignore this email. Your password will remain unchanged.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Reset your {BRAND} password",
        html=_wrap("Password Reset", "Reset link inside", body, "Reset Password", reset_link or f"{DASH_URL}/auth/reset-password", "#F59E0B"),
        text=_txt("Password Reset", f"Reset your password: {reset_link}\nExpires in {expiry_minutes} minutes."),
    )


# ── 4. Password Changed ────────────────────────────────


@_register("password_changed", "Password Changed", "Security", "Confirmation that password was updated")
def build_password_changed_email(
    user_name: str = "Alex", changed_at: str = "Mar 1, 2026 at 12:00 UTC"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Password Updated</p>
    <p style="margin:0 0 16px;">Hi {user_name}, your password was successfully changed.</p>
    {_info_table([_info_row("Changed at", changed_at), _info_row("Status", "Confirmed", "#10B981")])}
    {_callout("If you didn't make this change, <strong>secure your account immediately</strong> by resetting your password and enabling 2FA.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"Your {BRAND} password was changed",
        html=_wrap("Password Changed", "Your password was updated", body, "Review Security", f"{DASH_URL}/security"),
        text=_txt(
            "Password Changed", f"Hi {user_name}, password changed on {changed_at}. If not you, secure your account."
        ),
    )


# ── 5. Security Alert ──────────────────────────────────


@_register("security_alert", "Security Alert", "Security", "New sign-in from unrecognized device/location")
def build_security_alert_email(
    user_name: str = "Alex",
    location: str = "New York, US",
    device: str = "Chrome on Windows",
    event_time: str = "Mar 1, 2026 at 12:00 UTC",
) -> EmailTemplate:
    body = f"""{_alert_panel("New Sign-in Detected", "Review the sign-in details below and secure your account if anything looks unfamiliar.", "#F59E0B", "SECURITY CHECK")}
    <p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">New Sign-in Detected</p>
    <p style="margin:0 0 16px;">Hi {user_name}, we detected a new login to your account.</p>
    {_info_table([_info_row("Time", event_time), _info_row("Location", location), _info_row("Device", device)])}
    {_callout("If this wasn't you, reset your password and enable 2FA immediately.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"New sign-in to your {BRAND} account",
        html=_wrap("Security Alert", "New login detected", body, "Secure Account", f"{DASH_URL}/security", "#EF4444"),
        text=_txt("Security Alert", f"Hi {user_name}, new login at {event_time} from {location} ({device})."),
    )


# ── 6. Suspicious Login ────────────────────────────────


@_register("suspicious_login", "Suspicious Login", "Security", "Flagged login attempt from unusual IP/location")
def build_suspicious_login_email(
    user_name: str = "Alex",
    ip: str = "185.220.101.1",
    location: str = "Unknown",
    reason: str = "Unrecognized IP",
    event_time: str = "Mar 1, 2026 at 12:00 UTC",
    device: str = "Unknown Device",
) -> EmailTemplate:
    body = f"""{_alert_panel("Suspicious Activity Detected", "We blocked this attempt because it matched suspicious behavior. Review the details below.", "#EF4444", "HIGH RISK")}
    <p style="margin:0 0 16px;">Hi {user_name}, we blocked a suspicious login attempt on your account.</p>
    {_info_table([_info_row("Time", event_time), _info_row("IP Address", ip), _info_row("Location", location), _info_row("Device", device), _info_row("Reason", reason, "#EF4444")])}"""
    return EmailTemplate(
        subject=f"ALERT: Suspicious login attempt — {BRAND}",
        html=_wrap(
            "Suspicious Login",
            "Unusual activity detected",
            body,
            "Secure My Account",
            f"{DASH_URL}/security",
            "#EF4444",
        ),
        text=_txt("Suspicious Login", f"Hi {user_name}, suspicious login from {ip} ({location}) via {device}. Reason: {reason}."),
    )


# ── 6b. Admin Fraud Alert ────────────────────────────────


@_register("fraud_alert_admin", "Fraud Alert (Admin)", "Security", "Admin notification when fraud is detected")
def build_fraud_alert_admin_email(
    user_email: str = "user@example.com",
    risk_score: int = 85,
    risk_level: str = "critical",
    signals: str = "rapid_login_failures, multiple_ips",
    scan_time: str = "Mar 1, 2026 at 12:00 UTC",
) -> EmailTemplate:
    level_color = "#EF4444" if risk_level == "critical" else "#F59E0B" if risk_level == "high" else "#3B82F6"
    body = f"""{_alert_panel(f"Fraud Alert — {risk_level.upper()}", "This user was flagged by the fraud detection engine. Review immediately if the risk looks actionable.", level_color, f"{risk_level.upper()} RISK")}
    <p style="margin:0 0 16px;">A user has been flagged by the fraud detection engine.</p>
    {_info_table([_info_row("User", user_email), _info_row("Risk Score", f"{risk_score}/100", level_color), _info_row("Risk Level", risk_level.upper(), level_color), _info_row("Signals", signals), _info_row("Detected At", scan_time)])}
    {_callout("Review this user in the Admin Console immediately. Take action if necessary.", level_color)}"""
    return EmailTemplate(
        subject=f"FRAUD ALERT [{risk_level.upper()}]: {user_email} — {BRAND}",
        html=_wrap(
            "Fraud Alert",
            f"{risk_level.upper()} risk detected",
            body,
            "Review in Admin Console",
            f"{DASH_URL}/admin-console",
            level_color,
        ),
        text=_txt(
            "Fraud Alert",
            f"User: {user_email}\nRisk: {risk_score}/100 ({risk_level})\nSignals: {signals}\nTime: {scan_time}",
        ),
    )


# ── 7. OTP Code ─────────────────────────────────────────


@_register("otp_code", "OTP Verification Code", "Security", "One-time verification code sent via email")
def build_otp_email(code: str = "48291624", user_name: str = "Alex", expiry_minutes: int = 10) -> EmailTemplate:
    digits = "".join(
        [
            f'<td class="em-force-light-card" style="width:44px;height:52px;background:#FFFFFF;border:1px solid #CBD5E1;border-radius:12px;text-align:center;font-size:24px;font-weight:900;color:#0F172A;letter-spacing:1px;box-shadow:inset 0 0 0 1px rgba(59,130,246,0.06);">{d}</td><td style="width:6px;"></td>'
            for d in str(code)
        ]
    )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Verification Code</p>
    <p style="margin:0 0 24px;">Hi {user_name}, use this code to verify your identity:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 24px;"><tr>{digits}</tr></table>
    <p class="em-force-muted-text" style="margin:0 0 16px;text-align:center;font-size:12px;letter-spacing:0.6px;text-transform:uppercase;color:#64748B;">Copy this code: <strong style="color:#0F172A;letter-spacing:1.2px;">{code}</strong></p>
    {_callout(f"This code expires in <strong>{expiry_minutes} minutes</strong>. Never share this code with anyone.")}"""
    return EmailTemplate(
        subject=f"Your {BRAND} verification code: {code}",
        html=_wrap("Verification Code", f"Your code is {code}", body),
        text=_txt("Verification Code", f"Hi {user_name}, your code: {code}. Expires in {expiry_minutes} min."),
    )


# ── 8. Subscription Confirmation ────────────────────────


@_register("subscription_confirmed", "Subscription Confirmed", "Billing", "Plan activation confirmation")
def build_subscription_confirmation_email(
    user_name: str = "Alex", plan_name: str = "", billing_cycle: str = "Monthly", renewal_date: str = "Apr 1, 2026"
) -> EmailTemplate:
    if not plan_name:
        plan_name = get_plan_defaults("premium")["plan_name"]
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Subscription Activated!</p>
    <p style="margin:0 0 16px;">Hi {user_name}, your plan is now active. Here are the details:</p>
    {_info_table([_info_row("Plan", plan_name, PRIMARY), _info_row("Billing Cycle", billing_cycle), _info_row("Renewal Date", renewal_date), _info_row("Status", "Active", "#10B981")])}
    <p style="margin:16px 0 0;font-size:13px;">You now have full access to all {plan_name} features.</p>"""
    return EmailTemplate(
        subject=f"{plan_name} plan activated — {BRAND}",
        html=_wrap("Subscription Confirmed", "Your plan is active", body, "Go to Dashboard", DASH_URL, "#10B981"),
        text=_txt(
            "Subscription Confirmed", f"Hi {user_name}, {plan_name} ({billing_cycle}) active. Renewal: {renewal_date}."
        ),
    )


# ── 9. Subscription Renewal Reminder ────────────────────


@_register("renewal_reminder", "Renewal Reminder", "Billing", "Subscription expiring soon notification")
def build_subscription_renewal_reminder(
    user_name: str = "Alex",
    plan_name: str = "",
    renewal_date: str = "Apr 1, 2026",
    amount: str = "",
    days_remaining: int = 3,
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not plan_name:
        plan_name = _d["plan_name"]
    if not amount:
        amount = _d["amount"]
    uc = "#EF4444" if days_remaining <= 1 else "#F59E0B" if days_remaining <= 3 else PRIMARY
    ul = "FINAL NOTICE" if days_remaining <= 1 else "EXPIRING SOON" if days_remaining <= 3 else "REMINDER"
    body = f"""<div style="background:{_color_tint(uc, 0x18)};border-radius:12px;padding:14px 20px;margin:0 0 20px;text-align:center;">
      {_badge(ul, uc)}
      <p class="em-text-secondary" style="color:#64748B;font-size:13px;margin:10px 0 0;">Your <strong>{plan_name}</strong> subscription expires in <strong style="color:{uc};">{days_remaining} day{"s" if days_remaining != 1 else ""}</strong></p>
    </div>
    {_info_table([_info_row("Plan", plan_name), _info_row("Renewal Date", renewal_date), _info_row("Amount", amount, uc), _info_row("Days Left", str(days_remaining), uc)])}"""
    return EmailTemplate(
        subject=f"{'FINAL: ' if days_remaining <= 1 else ''}{plan_name} expires in {days_remaining} day{'s' if days_remaining != 1 else ''}",
        html=_wrap(
            "Renewal Reminder",
            f"Your plan expires in {days_remaining} days",
            body,
            "Renew Now",
            f"{DASH_URL}/subscription/mobile-money",
            uc,
        ),
        text=_txt("Renewal Reminder", f"Hi {user_name}, {plan_name} expires on {renewal_date}. Amount: {amount}."),
    )


# ── 10. Plan Changed ────────────────────────────────────


@_register("plan_changed", "Plan Changed", "Billing", "Subscription upgrade or downgrade confirmation")
def build_plan_changed_email(
    user_name: str = "Alex", old_plan: str = "", new_plan: str = "", effective_date: str = "Mar 1, 2026"
) -> EmailTemplate:
    if not old_plan:
        old_plan = get_plan_defaults("basic")["plan_name"]
    if not new_plan:
        new_plan = get_plan_defaults("premium")["plan_name"]
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Plan Updated</p>
    {_info_table([_info_row("Previous Plan", old_plan, "#64748B"), _info_row("New Plan", new_plan, "#10B981"), _info_row("Effective", effective_date)])}"""
    return EmailTemplate(
        subject=f"Plan changed to {new_plan} — {BRAND}",
        html=_wrap(
            "Plan Updated", "Your subscription was updated", body, "Manage Subscription", f"{DASH_URL}/subscription"
        ),
        text=_txt(
            "Plan Updated", f"Hi {user_name}, plan changed: {old_plan} -> {new_plan}. Effective: {effective_date}."
        ),
    )


# ── 11. Subscription Cancelled ───────────────────────────


@_register("subscription_cancelled", "Subscription Cancelled", "Billing", "Cancellation confirmation with end date")
def build_subscription_cancelled_email(
    user_name: str = "Alex", plan_name: str = "", end_date: str = "Apr 1, 2026"
) -> EmailTemplate:
    if not plan_name:
        plan_name = get_plan_defaults("premium")["plan_name"]
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Subscription Cancelled</p>
    <p style="margin:0 0 16px;">Hi {user_name}, your {plan_name} subscription has been cancelled.</p>
    {_info_table([_info_row("Plan", plan_name), _info_row("Access Until", end_date, "#F59E0B"), _info_row("Status", "Cancelled", "#EF4444")])}
    {_callout("You can reactivate your subscription at any time from your dashboard.")}"""
    return EmailTemplate(
        subject=f"Subscription cancelled — {BRAND}",
        html=_wrap(
            "Subscription Cancelled",
            "Your plan has been cancelled",
            body,
            "Reactivate",
            f"{DASH_URL}/subscription",
            "#F59E0B",
        ),
        text=_txt("Subscription Cancelled", f"Hi {user_name}, {plan_name} cancelled. Access until {end_date}."),
    )


# ── 11A. Subscription Expired ───────────────────────────


@_register("subscription_expired", "Subscription Expired", "Billing", "Official post-expiry notification with restore CTA")
def build_subscription_expired_email(
    user_name: str = "Alex", plan_name: str = "Premium", expired_on: str = "Apr 1, 2026"
) -> EmailTemplate:
    if not plan_name:
        plan_name = get_plan_defaults("premium")["plan_name"]

    body = f"""
    <div style="background:{_color_tint('#EF4444', 0x15)};border-radius:14px;padding:16px 20px;margin:0 0 22px;text-align:center;">
      {_badge("ACCESS ENDED", "#EF4444")}
      <p class="em-text-secondary" style="color:#64748B;font-size:13px;margin:10px 0 0;line-height:1.7;">
        Your <strong style="color:#0F172A;">{plan_name}</strong> subscription has officially expired and your premium access has ended.
      </p>
    </div>
    <p class="em-title" style="color:#0F172A;font-size:18px;font-weight:700;margin:0 0 10px;">Your Subscription Has Expired</p>
    <p style="margin:0 0 18px;line-height:1.8;">
      Hi {user_name}, we’re sorry to see you go. If you change your mind, just click the button below to subscribe again and restore your access.
    </p>
    {_info_table([
        _info_row("Previous Plan", plan_name),
        _info_row("Expired On", expired_on, "#EF4444"),
        _info_row("Current Access", "Free Plan", "#F59E0B"),
        _info_row("Status", "Expired", "#EF4444"),
    ])}
    {_callout("Your account is still active, but premium features are no longer available until you subscribe again. You can resume access instantly at any time.", "#3B82F6")}
    """

    return EmailTemplate(
        subject=f"Your subscription has expired — {BRAND}",
        html=_wrap(
            "Subscription Expired",
            "Your paid access has officially ended",
            body,
            "Subscribe Now",
            f"{DASH_URL}/subscription/plans",
            "#EF4444",
        ),
        text=_txt(
            "Subscription Expired",
            f"Hi {user_name}, your {plan_name} subscription expired on {expired_on}. We're sorry to see you go, but you can subscribe again at any time to restore your access.",
        ),
    )


# ── 11B. Subscription Restored ───────────────────────────


@_register("subscription_restored", "Subscription Restored", "Billing", "Confirmation that premium access has been restored")
def build_subscription_restored_email(
    user_name: str = "Alex", plan_name: str = "Premium", renewal_date: str = "May 10, 2026"
) -> EmailTemplate:
    if not plan_name:
        plan_name = get_plan_defaults("premium")["plan_name"]

    body = f"""
    <div style="background:{_color_tint('#10B981', 0x15)};border-radius:14px;padding:16px 20px;margin:0 0 22px;text-align:center;">
      {_badge("WELCOME BACK", "#10B981")}
      <p class="em-text-secondary" style="color:#64748B;font-size:13px;margin:10px 0 0;line-height:1.7;">
        Your <strong style="color:#0F172A;">{plan_name}</strong> access is active again and all premium features are available.
      </p>
    </div>
    <p class="em-title" style="color:#0F172A;font-size:18px;font-weight:700;margin:0 0 10px;">Your Subscription Has Been Restored</p>
    <p style="margin:0 0 18px;line-height:1.8;">
      Welcome back, {user_name}. We’re glad to have you with us again. Your subscription has been successfully restored, and you can jump right back into your dashboard.
    </p>
    {_info_table([
        _info_row("Active Plan", plan_name, "#10B981"),
        _info_row("Status", "Restored", "#10B981"),
        _info_row("Next Renewal", renewal_date),
        _info_row("Access", "Premium Features Enabled", "#3B82F6"),
    ])}
    {_callout("Your coaching history, saved content, and premium tools are available again right away. If you need anything, our support team is here to help.", "#10B981")}
    """

    return EmailTemplate(
        subject=f"Welcome back — your subscription is active again — {BRAND}",
        html=_wrap(
            "Subscription Restored",
            "Your premium access is back",
            body,
            "Go to Dashboard",
            f"{DASH_URL}/dashboard",
            "#10B981",
        ),
        text=_txt(
            "Subscription Restored",
            f"Welcome back, {user_name}. Your {plan_name} subscription is active again. Next renewal: {renewal_date}. Open your dashboard to continue.",
        ),
    )


# ── 12. Payment Receipt ─────────────────────────────────


@_register("payment_receipt", "Payment Receipt", "Billing", "Transaction receipt after successful payment")
def build_payment_receipt_email(
    user_name: str = "Alex",
    transaction_id: str = "TXN-2026-A1B2",
    amount: str = "",
    payment_method: str = "Visa ****4242",
    billing_summary: str = "",
    payment_date: str = "Mar 1, 2026",
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not amount:
        amount = _d["amount"]
    if not billing_summary:
        billing_summary = _d["billing_summary"]
    body = f"""{_alert_panel("Payment Received", "Your payment completed successfully and the receipt details are below.", "#10B981", "PAID")}
    <p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Payment Received</p>
    <p style="margin:0 0 16px;">Hi {user_name}, here's your receipt:</p>
    {_info_table([_info_row("Transaction ID", transaction_id), _info_row("Date", payment_date), _info_row("Amount", amount, "#059669"), _info_row("Method", payment_method), _info_row("Description", billing_summary)])}
    {_callout("Keep this receipt for your records. You can also view it any time from your payment history.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Payment receipt — {amount} — {BRAND}",
        html=_wrap("Payment Receipt", "Your payment is confirmed", body),
        text=_txt(
            "Payment Receipt", f"Hi {user_name}, payment of {amount} on {payment_date}. Transaction: {transaction_id}."
        ),
    )


# ── 13. Failed Payment ──────────────────────────────────


@_register("failed_payment", "Failed Payment", "Billing", "Payment failed, action required")
def build_failed_payment_email(
    user_name: str = "Alex", plan_name: str = "Premium", amount: str = "$15.99", update_link: str = "#"
) -> EmailTemplate:
    # Ensure CTA link is absolute HTTPS and honours canonical email link mode
    final_link = _to_absolute_https(update_link if update_link != "#" else "", "/subscription")
    body = f"""{_alert_panel("Payment Failed", "We couldn't process this charge. Review the amount below and update billing to avoid interruption.", "#EF4444", "PAYMENT FAILED")}
    <p style="margin:0 0 16px;">Hi {user_name}, we couldn't process your payment.</p>
    {_info_table([_info_row("Plan", plan_name), _info_row("Amount Due", amount, "#EF4444")])}
    {_callout("Update your billing information to avoid service interruption.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"Payment failed — action required — {BRAND}",
        html=_wrap(
            "Payment Failed",
            "Action required",
            body,
            "Update Billing",
            final_link,
            "#EF4444",
        ),
        text=_txt("Payment Failed", f"Hi {user_name}, payment failed for {plan_name}. Amount: {amount}."),
    )



# ── 13b. Payment Recovery — Day 1 (Immediate) ────────────


@_register("recovery_day1", "Recovery Day 1", "Billing", "Immediate one-click recovery email after payment failure")
def build_recovery_email_day1(
    user_name: str = "Alex",
    plan_name: str = "",
    amount: str = "",
    recovery_link: str = "#",
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not plan_name:
        plan_name = _d["plan_name"]
    if not amount:
        amount = _d["amount"]
    final_link = _to_absolute_https(recovery_link if recovery_link != "#" else "", "/subscription/plans")
    body = f"""{_alert_panel("Payment Failed", "Your payment needs attention, but recovery is one click away.", "#EF4444", "PAYMENT FAILED")}
    <p style="margin:0 0 16px;">Hi {user_name}, we couldn't process your payment of <strong>{amount}</strong> for the <strong>{plan_name}</strong> plan.</p>
    <p style="margin:0 0 14px;">Common reasons include bank decline, insufficient balance, expired card, or incomplete 3DS verification.</p>
    {_info_table([_info_row("Plan", plan_name), _info_row("Amount", amount, "#EF4444"), _info_row("Status", "Payment Failed", "#EF4444")])}
    {_light_locked_tip_card(
      "How to fix this quickly",
      [
        "Check available balance or card spending limits.",
        "Confirm your billing address and card expiry/CVC details.",
        "Retry payment and complete any bank authentication prompt.",
        "If it still fails, switch payment method in checkout.",
      ],
      "#991B1B",
    )}
    {_callout("Click the button below to retry securely. Your subscription features restore immediately after successful payment.", "#EF4444")}
    <p style="margin:16px 0 0;font-size:12px;color:#64748B;">You will receive at most one recovery email per day while this issue remains unresolved.</p>"""
    return EmailTemplate(
        subject=f"Action needed: Update your payment — {BRAND}",
        html=_wrap("Payment Failed", "One-click recovery", body, "Recover My Subscription", final_link, "#EF4444"),
        text=_txt(
            "Payment Failed",
            (
                f"Hi {user_name}, payment of {amount} for {plan_name} failed. "
                "Common reasons: bank decline, insufficient funds, expired card, or incomplete authentication. "
                "Fix: verify balance and card details, retry payment, complete bank auth, or switch payment method. "
                f"Recover here: {final_link}"
            ),
        ),
    )


# ── 13c. Payment Recovery — Day 3 (Reminder) ─────────────


@_register("recovery_day3", "Recovery Day 3", "Billing", "3-day follow-up recovery email")
def build_recovery_email_day3(
    user_name: str = "Alex",
    plan_name: str = "",
    amount: str = "",
    recovery_link: str = "#",
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not plan_name:
        plan_name = _d["plan_name"]
    if not amount:
        amount = _d["amount"]
    final_link = _to_absolute_https(recovery_link if recovery_link != "#" else "", "/subscription/plans")
    body = f"""{_alert_panel("Payment Reminder", "Your subscription is still waiting for payment. Update it now to keep your features active.", "#F59E0B", "REMINDER")}
    <p style="margin:0 0 16px;">Hi {user_name}, your <strong>{plan_name}</strong> subscription payment of <strong>{amount}</strong> is still pending.</p>
    <p style="margin:0 0 16px;">You're missing out on your premium features. It only takes a moment to get back on track:</p>
    {_info_table([_info_row("Plan", plan_name), _info_row("Amount", amount, "#F59E0B"), _info_row("Days Overdue", "3 days", "#F59E0B")])}
    {_callout("Your account features are limited until payment is resolved. Click below to update your payment method instantly.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Reminder: Your {plan_name} subscription needs attention — {BRAND}",
        html=_wrap("Payment Reminder", "Your features are waiting", body, "Update Payment Now", final_link, "#F59E0B"),
        text=_txt("Payment Reminder", f"Hi {user_name}, your {plan_name} payment ({amount}) is 3 days overdue. Update: {final_link}"),
    )


# ── 13d. Payment Recovery — Day 7 (Final Warning) ────────


@_register("recovery_day7", "Recovery Day 7", "Billing", "7-day final warning recovery email before account downgrade")
def build_recovery_email_day7(
    user_name: str = "Alex",
    plan_name: str = "",
    amount: str = "",
    recovery_link: str = "#",
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not plan_name:
        plan_name = _d["plan_name"]
    if not amount:
        amount = _d["amount"]
    final_link = _to_absolute_https(recovery_link if recovery_link != "#" else "", "/subscription/plans")
    body = f"""{_alert_panel("Final Notice", "Your subscription is about to be downgraded unless payment is resolved soon.", "#DC2626", "FINAL NOTICE")}
    <p style="margin:0 0 16px;">Hi {user_name}, this is your <strong>final reminder</strong> about your <strong>{plan_name}</strong> subscription.</p>
    <p style="margin:0 0 16px;">Your payment of <strong>{amount}</strong> is now <strong>7 days overdue</strong>. If not resolved soon, your account will be downgraded to the free plan and you'll lose access to premium features.</p>
    {_info_table([_info_row("Plan", plan_name), _info_row("Amount", amount, "#DC2626"), _info_row("Status", "Final Warning", "#DC2626"), _info_row("Action Deadline", "48 hours", "#DC2626")])}
    {_callout("This is your last chance to keep your premium features. One click is all it takes.", "#DC2626")}"""
    return EmailTemplate(
        subject=f"Final notice: {plan_name} subscription expiring — {BRAND}",
        html=_wrap("Final Warning", "Last chance to keep your plan", body, "Save My Subscription", final_link, "#DC2626"),
        text=_txt("Final Warning", f"Hi {user_name}, final notice: {plan_name} ({amount}) 7 days overdue. Save now: {final_link}"),
    )


# ── 13e. Payment Recovery Success ─────────────────────────


@_register("recovery_success", "Payment Recovery Success", "Billing", "Reassurance email when access is restored after a failed-payment retry")
def build_payment_recovery_success_email(
    user_name: str = "Alex",
    plan_name: str = "",
    amount: str = "",
    transaction_id: str = "TXN-REC-2026",
    recovery_date: str = "Apr 11, 2026",
) -> EmailTemplate:
    _d = get_plan_defaults("premium")
    if not plan_name:
        plan_name = _d["plan_name"]
    if not amount:
        amount = _d["amount"]
    body = f"""
    <div style="background:{_color_tint('#10B981', 0x15)};border-radius:14px;padding:16px 20px;margin:0 0 22px;text-align:center;">
      {_badge("PAYMENT RECOVERED", "#10B981")}
      <p class="em-text-secondary" style="color:#64748B;font-size:13px;margin:10px 0 0;line-height:1.7;">
        Your payment has been successfully processed. No further action is needed.
      </p>
    </div>
    <p class="em-title" style="color:#0F172A;font-size:18px;font-weight:700;margin:0 0 10px;">Your Access Has Been Restored</p>
    <p style="margin:0 0 18px;line-height:1.8;">
      Great news, {user_name}! Your payment issue has been resolved. Your <strong>{plan_name}</strong> subscription is fully active again, and all premium features are available.
    </p>
    {_info_table([
        _info_row("Plan", plan_name, "#10B981"),
        _info_row("Amount Paid", amount, "#10B981"),
        _info_row("Transaction", transaction_id),
        _info_row("Recovery Date", recovery_date),
        _info_row("Status", "Active — All Features Restored", "#10B981"),
    ])}
    {_callout("You're all set! Your billing is back on track and your next renewal will proceed as normal. If you have any questions, our support team is always here.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Payment recovered — your {plan_name} is active — {BRAND}",
        html=_wrap(
            "Payment Recovered",
            "Your access is fully restored",
            body,
            "Go to Dashboard",
            f"{DASH_URL}/dashboard",
            "#10B981",
        ),
        text=_txt(
            "Payment Recovered",
            f"Hi {user_name}, your payment of {amount} for {plan_name} was successfully recovered on {recovery_date}. Transaction: {transaction_id}. Your access is fully restored.",
        ),
    )


# ── 14. Support Ticket Created ───────────────────────────


@_register("ticket_created", "Ticket Created", "Support", "Confirmation that support ticket was received")
def build_support_ticket_email(
    user_name: str = "Alex",
    ticket_id: str = "TKT-20260301-A1B2",
    subject: str = "Help with billing",
    message: str = "I need help with my subscription...",
) -> EmailTemplate:
    body = f"""{_alert_panel("Ticket Received", "Your request is safely queued with our support team. We'll keep you updated here.", PRIMARY, "SUPPORT")}
    {_lead("Ticket Received", f"Hi {user_name}, we've received your request and created a ticket.")}
    {_info_table([_info_row("Ticket ID", ticket_id, PRIMARY), _info_row("Subject", subject), _info_row("Status", "Open", "#10B981")])}
    {_callout(message[:300])}
    <p class="em-text-secondary" style="font-size:12px;color:#64748B;margin:16px 0 0;">Our team typically responds within 24 hours.</p>"""
    return EmailTemplate(
        subject=f"Ticket {ticket_id} received — {BRAND}",
        html=_wrap("Ticket Received", "Your request is being processed", body, "View Ticket", f"{DASH_URL}/my-tickets"),
        text=_txt("Ticket Received", f"Hi {user_name}, ticket {ticket_id} created. Subject: {subject}."),
    )


# ── 15. Admin Reply to Ticket ────────────────────────────


@_register("admin_reply", "Admin Reply", "Support", "Support team replied to a user ticket")
def build_admin_reply_email(
    ticket_id: str = "TKT-20260301-A1B2",
    subject: str = "Help with billing",
    message: str = "Hi, I've looked into your issue and here's what I found...",
) -> EmailTemplate:
    body = f"""{_alert_panel("New Reply on Your Ticket", "A support team member has replied. Review the response below and continue the conversation if needed.", PRIMARY, "SUPPORT REPLY")}
    {_lead("New Reply on Your Ticket", f"Ticket #{ticket_id} - {subject}")}
    {_callout(message[:500])}"""
    return EmailTemplate(
        subject=f"Re: {subject} [{ticket_id}]",
        html=_wrap("Support Reply", "You have a new reply", body, "Reply to This Message", f"{DASH_URL}/my-tickets"),
        text=_txt("Support Reply", f"Ticket #{ticket_id}: {message[:500]}", "Reply", f"{DASH_URL}/my-tickets"),
    )


# ── 16. Ticket Resolved ─────────────────────────────────


@_register("ticket_resolved", "Ticket Resolved", "Support", "Ticket marked as resolved with optional CSAT")
def build_ticket_resolved_email(
    user_name: str = "Alex",
    ticket_id: str = "TKT-20260301-A1B2",
    subject: str = "Help with billing",
    rating_url: str = "",
) -> EmailTemplate:
    rating_base = rating_url or f"{DASH_URL}/my-tickets?ticket={ticket_id}"
    rating_positive = _append_query_params(_to_absolute_https(rating_base, "/my-tickets"), {"rating": "positive"})
    rating_negative = _append_query_params(_to_absolute_https(rating_base, "/my-tickets"), {"rating": "negative"})

    body = f'''{_alert_panel("Ticket Resolved", "Your support request has been marked resolved. Let us know how the experience felt.", "#10B981", "RESOLVED")}
    {_lead("Ticket Resolved", f"Hi {user_name}, your support ticket has been resolved.")}
    {_info_table([_info_row("Ticket", ticket_id), _info_row("Subject", subject), _info_row("Status", "Resolved", "#10B981")])}
    <p class="em-text-secondary" style="margin:20px 0 10px;text-align:center;font-size:14px;color:#64748B;">How was your experience?</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
    <tr>
      <td style="padding:0 8px;"><a href="{rating_positive}" style="display:inline-block;width:48px;height:48px;line-height:48px;text-align:center;font-size:24px;background:#0F1A17;border-radius:12px;text-decoration:none;border:1px solid #1E3530;">&#128077;</a></td>
      <td style="padding:0 8px;"><a href="{rating_negative}" style="display:inline-block;width:48px;height:48px;line-height:48px;text-align:center;font-size:24px;background:#1C1012;border-radius:12px;text-decoration:none;border:1px solid #3D1B22;">&#128078;</a></td>
    </tr></table>'''
    return EmailTemplate(
        subject=f"Ticket {ticket_id} resolved — {BRAND}",
        html=_wrap("Ticket Resolved", "Your issue has been resolved", body),
        text=_txt("Ticket Resolved", f"Hi {user_name}, ticket {ticket_id} resolved."),
    )


# ── 17. Booking Created ─────────────────────────────────


@_register("booking_created", "Meeting Booked", "Calendar", "New meeting booked notification")
def build_booking_email(
    guest_name: str = "Jane Doe",
    guest_email: str = "jane@example.com",
    meeting_time: str = "Mar 5, 2026 at 10:00 AM",
    duration: str = "30 min",
) -> EmailTemplate:
    body = f"""{_alert_panel("New Meeting Booked", "A calendar booking just landed. Review the meeting details below.", PRIMARY, "CALENDAR")}
    {_lead("New Meeting Booked", "Review the scheduled guest, time, and duration below.")}
    {_info_table([_info_row("Guest", guest_name), _info_row("Email", guest_email), _info_row("When", meeting_time, PRIMARY), _info_row("Duration", duration)])}"""
    return EmailTemplate(
        subject=f"Meeting booked with {guest_name}",
        html=_wrap("Meeting Booked", "You have a new meeting", body, "View Calendar", f"{DASH_URL}/book-meeting"),
        text=_txt("Meeting Booked", f"Meeting with {guest_name} on {meeting_time} ({duration})."),
    )


# ── 18. Booking Cancelled ────────────────────────────────


@_register("booking_cancelled", "Meeting Cancelled", "Calendar", "Meeting cancellation notification")
def build_booking_cancelled_email(
    guest_name: str = "Jane Doe", meeting_time: str = "Mar 5, 2026 at 10:00 AM", cancelled_by: str = "guest"
) -> EmailTemplate:
    body = f"""{_alert_panel("Meeting Cancelled", "This meeting was cancelled. Review the details and reschedule if needed.", "#F59E0B", "CALENDAR UPDATE")}
    {_lead("Meeting Cancelled", "Review who cancelled the meeting and decide whether to reschedule.")}
    {_info_table([_info_row("Guest", guest_name), _info_row("Was Scheduled", meeting_time), _info_row("Cancelled By", cancelled_by.title(), "#EF4444")])}"""
    return EmailTemplate(
        subject=f"Meeting with {guest_name} cancelled",
        html=_wrap(
            "Meeting Cancelled", "A meeting was cancelled", body, "Reschedule", f"{DASH_URL}/book-meeting", "#F59E0B"
        ),
        text=_txt("Meeting Cancelled", f"Meeting with {guest_name} on {meeting_time} cancelled by {cancelled_by}."),
    )


# ── 19. Meeting Reminder ────────────────────────────────


@_register("meeting_reminder_calendar", "Meeting Reminder", "Calendar", "Upcoming meeting reminder")
def build_meeting_reminder_email(
    guest_name: str = "Jane Doe", meeting_time: str = "10:00 AM", minutes_until: int = 15
) -> EmailTemplate:
    body = f"""{_alert_panel("Meeting Reminder", f"Your meeting starts in {minutes_until} minutes. Join on time and review the details below.", PRIMARY, "UPCOMING")}
    <div style="background:{_color_tint(PRIMARY, 0x18)};border-radius:12px;padding:14px 20px;margin:0 0 20px;text-align:center;">
      <p style="color:{PRIMARY};font-weight:800;font-size:24px;margin:0;">{minutes_until} min</p>
      <p class="em-text-secondary" style="color:#64748B;font-size:12px;margin:4px 0 0;">until your meeting</p>
    </div>
    {_info_table([_info_row("With", guest_name), _info_row("Starts at", meeting_time, PRIMARY)])}"""
    return EmailTemplate(
        subject=f"Meeting in {minutes_until} min with {guest_name}",
        html=_wrap(
            "Meeting Reminder", f"Meeting in {minutes_until} minutes", body, "Join Now", f"{DASH_URL}/book-meeting"
        ),
        text=_txt("Meeting Reminder", f"Meeting with {guest_name} starts at {meeting_time} ({minutes_until} min)."),
    )


# ── 20. Employer Application Submitted ───────────────────


@_register("employer_submitted", "Employer App Submitted", "Employer", "Employer application submitted confirmation")
def build_employer_submitted_email(user_name: str = "Alex", company_name: str = "Acme Corp") -> EmailTemplate:
    intro = f'Hi {user_name}, your employer application for <strong class="em-strong" style="color:#0F172A;">{company_name}</strong> has been submitted.'
    body = f"""{_alert_panel("Application Submitted", "Your employer onboarding request is now under review. We'll update you when a decision is made.", PRIMARY, "EMPLOYER")}
    {_lead("Application Submitted", intro)}
    {_info_table([_info_row("Company", company_name), _info_row("Status", "Under Review", "#F59E0B"), _info_row("Review Time", "1-3 business days")])}"""
    return EmailTemplate(
        subject=f"Employer Application Submitted — {company_name}",
        html=_wrap(
            "Application Submitted",
            "Your application is under review",
            body,
            "Check Status",
            f"{DASH_URL}/mini-apps/job-platform",
        ),
        text=_txt(
            "Application Submitted", f"Hi {user_name}, employer app for {company_name} submitted. Review: 1-3 days."
        ),
    )


# ── 21. Employer Approved ────────────────────────────────


@_register("employer_approved", "Employer Approved", "Employer", "Employer application approved")
def build_employer_approved_email(
    user_name: str = "Alex", company_name: str = "Acme Corp", reviewer_notes: str = ""
) -> EmailTemplate:
    notes = f"{_callout(reviewer_notes)}" if reviewer_notes else ""
    body = f"""{_alert_panel("Employer Approved", "Your employer workspace is now active. You can start posting jobs and managing hiring workflows.", "#10B981", "APPROVED")}
    <p style="margin:0 0 16px;">Hi {user_name}, congratulations! Your employer application has been approved.</p>
    {notes}
    <p class="em-text-secondary" style="font-size:13px;color:#64748B;">You can now post jobs, manage listings, and use AI hiring tools.</p>"""
    return EmailTemplate(
        subject=f"Employer Approved — {company_name}",
        html=_wrap(
            "Application Approved",
            "Your employer account is active",
            body,
            "Post Your First Job",
            f"{DASH_URL}/mini-apps/job-platform",
            "#10B981",
        ),
        text=_txt("Application Approved", f"Hi {user_name}, {company_name} employer approved. Start posting jobs!"),
    )


# ── 21b. Job Search Kit Ready ────────────────────────────


@_register("job_search_kit_ready", "Job Search Kit Ready", "Jobs", "AI application kit (CV + cover letter) generated")
def build_job_search_kit_ready_email(
    user_name: str = "Alex", job_title: str = "Software Engineer"
) -> EmailTemplate:
    body = f"""{_alert_panel("Application Kit Ready", "Your tailored CV and cover letter have been drafted, reviewed, and finalized by AI.", "#14B8A6", "READY")}
    <p style="margin:0 0 16px;">Hi {user_name}, your AI application kit for <strong>{job_title}</strong> is ready in your Job Search workspace.</p>
    <p class="em-text-secondary" style="font-size:13px;color:#64748B;">Open the workspace to review your documents, run the ATS keyword check, and track your application.</p>"""
    return EmailTemplate(
        subject=f"Your application kit is ready — {job_title}",
        html=_wrap(
            "Application Kit Ready",
            "Tailored CV and cover letter generated",
            body,
            "Open Job Search",
            f"{DASH_URL}/job-search",
            "#14B8A6",
        ),
        text=_txt("Application Kit Ready", f"Hi {user_name}, your AI application kit for {job_title} is ready in Job Search.", "Open Job Search", f"{DASH_URL}/job-search"),
    )


# ── 21c. Job Search Weekly Digest ────────────────────────


@_register("job_search_weekly_digest", "Job Search Weekly Digest", "Jobs", "Weekly digest of new matching roles and fit-score highlights")
def build_job_search_weekly_digest_email(
    user_name: str = "Alex",
    week_label: str = "This week",
    new_roles_count: int = 0,
    top_roles: list = None,
    best_fit_score: int = 0,
    best_fit_job_title: str = "",
    kits_generated: int = 0,
    apps_tracked: int = 0,
    show_upgrade_hint: bool = False,
) -> EmailTemplate:
    top_roles = top_roles or []
    roles_html = ""
    if top_roles:
        items = "".join(
            f'<li style="margin:0 0 8px;"><strong>{r.get("title", "")}</strong>'
            f'<span class="em-text-secondary" style="color:#64748B;"> — {r.get("department", "")} · {r.get("location", "")}</span></li>'
            for r in top_roles[:3]
        )
        roles_html = f"""<p style="margin:16px 0 8px;font-weight:700;">Top matches for your profile:</p>
    <ul style="margin:0 0 16px;padding-left:20px;">{items}</ul>"""
    best_fit_html = ""
    if best_fit_score and best_fit_job_title:
        best_fit_html = _callout(f"Best fit score this week: {best_fit_score}/100 — {best_fit_job_title}", "#14B8A6")
    activity_html = f"""<p class="em-text-secondary" style="font-size:13px;color:#64748B;margin:0 0 16px;">Your week: {kits_generated} AI application kit(s) generated · {apps_tracked} application(s) tracked.</p>"""
    upgrade_html = ""
    if show_upgrade_hint:
        upgrade_html = _callout("Tip: upgrade your plan for faster, unlimited AI kit generation and priority fit scoring.", "#0891B2")
    body = f"""{_alert_panel("Your Job Search Week", f"{new_roles_count} new role(s) matching your profile were posted {week_label.lower()}.", "#14B8A6", "DIGEST")}
    <p style="margin:0 0 16px;">Hi {user_name}, here is your weekly Job Search pulse.</p>
    {roles_html}{best_fit_html}{activity_html}{upgrade_html}"""
    return EmailTemplate(
        subject=f"Your Job Search digest — {new_roles_count} new matching role(s)",
        html=_wrap(
            "Job Search Weekly Digest",
            "New matching roles and your fit-score highlights",
            body,
            "Open Job Search",
            f"{DASH_URL}/job-search",
            "#14B8A6",
        ),
        text=_txt(
            "Job Search Weekly Digest",
            f"Hi {user_name}, {new_roles_count} new matching role(s) this week. Best fit: {best_fit_score}/100 {best_fit_job_title}.",
            "Open Job Search",
            f"{DASH_URL}/job-search",
        ),
    )


# ── 21d. Job Search Kit Email (attachments) ──────────────


@_register("job_search_kit_email", "Job Search Kit Email", "Jobs", "Application kit (CV + cover letter PDFs) delivered as attachments")
def build_job_search_kit_email(
    user_name: str = "Alex", job_title: str = "Software Engineer"
) -> EmailTemplate:
    body = f"""{_alert_panel("Application Kit Attached", "Your tailored CV and cover letter are attached as clean, employer-ready PDF and Word (.docx) versions.", "#14B8A6", "ATTACHED")}
    <p style="margin:0 0 16px;">Hi {user_name}, your AI application kit for <strong>{job_title}</strong> is attached to this email.</p>
    <p style="margin:0 0 16px;">Each document comes in both PDF and Word (.docx) format — many employers and ATS portals ask specifically for .docx. All files are unbranded and ATS-friendly, ready to forward straight to employers.</p>
    <p class="em-text-secondary" style="font-size:13px;color:#64748B;">Want to tweak them first? Open your Job Search workspace to regenerate or run another ATS check.</p>"""
    return EmailTemplate(
        subject=f"Your application kit (attached) — {job_title}",
        html=_wrap(
            "Application Kit Attached",
            "CV and cover letter PDFs, ready to forward",
            body,
            "Open Job Search",
            f"{DASH_URL}/job-search",
            "#14B8A6",
        ),
        text=_txt("Application Kit Attached", f"Hi {user_name}, your CV and cover letter for {job_title} are attached in both PDF and Word (.docx) format — clean and ready to forward to employers.", "Open Job Search", f"{DASH_URL}/job-search"),
    )


# ── 22. Employer Denied ──────────────────────────────────
@_register("employer_denied", "Employer Denied", "Employer", "Employer application denied")
def build_employer_denied_email(
    user_name: str = "Alex", company_name: str = "Acme Corp", reason: str = "Insufficient documentation"
) -> EmailTemplate:
    body = f"""{_alert_panel("Application Denied", "We couldn't approve this employer application yet. Review the reason below and contact support if needed.", "#EF4444", "ACTION NEEDED")}
    <p style="margin:0 0 16px;">Hi {user_name}, unfortunately your employer application for <strong>{company_name}</strong> was not approved.</p>
    {_callout(f"<strong>Reason:</strong> {reason}", "#EF4444")}"""
    return EmailTemplate(
        subject=f"Employer Application Update — {company_name}",
        html=_wrap(
            "Application Denied", "Your application was not approved", body, "Get Help Now", SUPPORT_URL, "#EF4444"
        ),
        text=_txt("Application Denied", f"Hi {user_name}, {company_name} employer denied. Reason: {reason}."),
    )


# ── 23. Employer More Info ───────────────────────────────


@_register("employer_more_info", "More Info Required", "Employer", "Additional information needed for employer app")
def build_employer_more_info_email(
    user_name: str = "Alex",
    company_name: str = "Acme Corp",
    notes: str = "Please provide proof of business registration",
) -> EmailTemplate:
    body = f"""{_alert_panel("More Info Needed", "We need a bit more information before we can finish reviewing this employer application.", "#F59E0B", "ACTION REQUIRED")}
    <p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Action Required</p>
    <p style="margin:0 0 16px;">Hi {user_name}, we need more information for your <strong>{company_name}</strong> application.</p>
    {_callout(f"<strong>What we need:</strong> {notes}", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Action Required: {company_name} Application",
        html=_wrap(
            "More Info Needed",
            "Additional information required",
            body,
            "Update Application",
            f"{DASH_URL}/mini-apps/job-platform",
            "#F59E0B",
        ),
        text=_txt("More Info Needed", f"Hi {user_name}, more info needed for {company_name}: {notes}"),
    )


# ── 24. ID Checker Approved ─────────────────────────


@_register("idv_approved", "ID Verified", "Verification", "ID Checker approved")
def build_idv_approved_email(
    user_name: str = "Alex",
    tier: str = "enhanced",
    checks_passed: int = 5,
    total_checks: int = 5,
    confidence: float = 0.97,
) -> EmailTemplate:
    pct = round(confidence * 100)
    support_email = "support@realaicoach.app"
    body = f"""{_alert_panel("Identity Verified", "Your verification cleared successfully. Review the details below for confidence and tier status.", "#10B981", "VERIFIED")}
    <p style="margin:0 0 16px;">Hi {user_name}, your identity has been verified.</p>
    {_info_table([_info_row("Decision", "Approved", "#10B981"), _info_row("What happens next", "Your account remains active with full access."), _info_row("Tier", tier.replace("_", " ").title()), _info_row("AI Checks", f"{checks_passed}/{total_checks}", "#10B981"), _info_row("Confidence", f"{pct}%"), _info_row("Support", support_email)])}
    {_callout(f"Need help or have questions? Contact {support_email}.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Identity Verified — {BRAND}",
        html=_wrap("Identity Verified", "Full access granted", body, "Go to Dashboard", DASH_URL, "#10B981"),
        text=_txt("Identity Verified", f"Hi {user_name}, ID verified. Tier: {tier}, Confidence: {pct}%. Support: {support_email}"),
    )


# ── 25. ID Checker Rejected ─────────────────────────


@_register("idv_rejected", "ID Rejected", "Verification", "ID Checker declined")
def build_idv_rejected_email(
    user_name: str = "Alex", reasons: List[str] = None, flags: List[str] = None, retry_date: str = "Mar 8, 2026"
) -> EmailTemplate:
    reasons = reasons or ["Document quality insufficient"]
    support_email = "support@realaicoach.app"
    r_html = "".join([
        f'<li class="em-text-secondary" style="color:#0F172A;-webkit-text-fill-color:#0F172A;font-size:13px;line-height:1.6;margin:6px 0;font-weight:600;">{r}</li>'
        for r in reasons
    ])
    body = f"""{_alert_panel("Verification Declined", "We couldn't verify this submission yet. Review the reasons below before retrying.", "#EF4444", "DECLINED")}
    <p style="margin:0 0 16px;">Hi {user_name}, your ID Checker was declined.</p>
    <div class="em-force-light-card" style="background:#FFF7F7;border:1px solid #FECACA;border-left:4px solid #EF4444;border-radius:10px;padding:14px 18px;margin:18px 0;color:#0F172A;">
      <p style="color:#B91C1C;-webkit-text-fill-color:#B91C1C;font-weight:700;font-size:12px;letter-spacing:.5px;margin:0 0 8px;">REASONS</p>
      <ul style="margin:0;padding-left:18px;">{r_html}</ul>
    </div>
    {_info_table([_info_row("Decision", "Rejected", "#EF4444"), _info_row("What happens next", "Please correct the listed issues and resubmit when ready."), _info_row("Retry After", retry_date, "#F59E0B"), _info_row("Support", support_email)])}
    {_callout(f"If you believe this decision is incorrect, contact {support_email} and include your submission reference.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"ID Checker Declined — {BRAND}",
        html=_wrap(
            "Verification Declined",
            "Your verification needs attention",
            body,
            "Get Help Now",
            SUPPORT_URL,
            "#EF4444",
        ),
        text=_txt(
            "Verification Declined", f"Hi {user_name}, ID declined. Reasons: {'; '.join(reasons)}. Retry: {retry_date}. Support: {support_email}"
        ),
    )


@_register("idv_admin_approved", "IDV Admin Alert — Approved", "Verification", "Admin notification for approved ID Checker")
def build_idv_admin_approved_email(
    recipient_name: str = "Admin",
    user_name: str = "User",
    user_email: str = "user@example.com",
    user_id: str = "",
    confidence: float = 0.0,
    reviewed_by: str = "system",
) -> EmailTemplate:
    support_email = "support@realaicoach.app"
    body = f"""{_alert_panel("ID Checker Approved", "A user verification was approved and account access is active.", "#10B981", "APPROVED")}
    <p style="margin:0 0 14px;">Hi {recipient_name}, an ID Checker decision has been finalized.</p>
    {_info_table([_info_row("Decision", "Approved", "#10B981"), _info_row("User", user_name), _info_row("User Email", user_email), _info_row("User ID", user_id or "—"), _info_row("AI Confidence", f"{round(confidence * 100)}%"), _info_row("Reviewed By", reviewed_by or "system"), _info_row("Support", support_email)])}
    {_callout("Audit this decision if needed from the ID Checker admin dashboard.", "#10B981")}"""
    return EmailTemplate(
        subject=f"[Admin] ID Checker Approved — {user_email}",
        html=_wrap("IDV Admin Alert", "Verification approved", body, "Open ID Checker Dashboard", f"{DASH_URL}/id-checker", "#10B981"),
        text=_txt("IDV Admin Approved", f"User {user_name} ({user_email}) approved. Confidence: {round(confidence * 100)}%. Reviewed by: {reviewed_by}. Support: {support_email}"),
    )


@_register("idv_admin_rejected", "IDV Admin Alert — Rejected", "Verification", "Admin notification for rejected ID Checker")
def build_idv_admin_rejected_email(
    recipient_name: str = "Admin",
    user_name: str = "User",
    user_email: str = "user@example.com",
    user_id: str = "",
    reasons: List[str] = None,
    reviewed_by: str = "system",
) -> EmailTemplate:
    support_email = "support@realaicoach.app"
    reasons = reasons or ["No rejection reason provided"]
    reason_html = "".join([
        f'<li style="color:#0F172A;-webkit-text-fill-color:#0F172A;font-size:13px;line-height:1.6;margin:6px 0;font-weight:600;">{r}</li>'
        for r in reasons
    ])
    body = f"""{_alert_panel("ID Checker Rejected", "A user verification was rejected and follow-up may be required.", "#EF4444", "REJECTED")}
    <p style="margin:0 0 14px;">Hi {recipient_name}, an ID Checker decision has been finalized.</p>
    {_info_table([_info_row("Decision", "Rejected", "#EF4444"), _info_row("User", user_name), _info_row("User Email", user_email), _info_row("User ID", user_id or "—"), _info_row("Reviewed By", reviewed_by or "system"), _info_row("Support", support_email)])}
    <div class="em-force-light-card" style="background:#FFF7F7;border:1px solid #FECACA;border-left:4px solid #EF4444;border-radius:10px;padding:14px 18px;margin:18px 0;color:#0F172A;">
      <p style="color:#B91C1C;-webkit-text-fill-color:#B91C1C;font-weight:700;font-size:12px;letter-spacing:.5px;margin:0 0 8px;">REJECTION REASONS</p>
      <ul style="margin:0;padding-left:18px;">{reason_html}</ul>
    </div>
    {_callout("If escalation is needed, coordinate with support@realaicoach.app.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"[Admin] ID Checker Rejected — {user_email}",
        html=_wrap("IDV Admin Alert", "Verification rejected", body, "Open ID Checker Dashboard", f"{DASH_URL}/id-checker", "#EF4444"),
        text=_txt("IDV Admin Rejected", f"User {user_name} ({user_email}) rejected. Reasons: {'; '.join(reasons)}. Reviewed by: {reviewed_by}. Support: {support_email}"),
    )


# ── 26. ID Pending Review ────────────────────────────────


@_register("idv_pending", "ID Pending Review", "Verification", "ID Checker under manual review")
def build_idv_pending_review_email(
    user_name: str = "Alex", ai_confidence: float = 0.82, flags: List[str] = None
) -> EmailTemplate:
    support_email = "support@realaicoach.app"
    body = f"""{_alert_panel("Verification Under Review", "Your submission is in manual review. No action is needed while we complete verification.", "#F59E0B", "UNDER REVIEW")}
    {_lead("Verification Under Review", f"Hi {user_name}, your ID is under manual review.")}
    {_info_table([_info_row("Decision", "Under Review", "#F59E0B"), _info_row("What happens next", "You'll receive a follow-up decision email: Approved, Rejected, or More Info Needed."), _info_row("AI Confidence", f"{round(ai_confidence * 100)}%"), _info_row("Est. Time", "1-2 business days"), _info_row("Support", support_email)])}
    {_callout(f"No action needed right now. If you need help, contact {support_email}.")}"""
    return EmailTemplate(
        subject=f"ID Checker Under Review — {BRAND}",
        html=_wrap("Under Review", "Your verification is being reviewed", body),
        text=_txt("Under Review", f"Hi {user_name}, ID under review. Confidence: {round(ai_confidence * 100)}%. Support: {support_email}"),
    )


@_register("idv_more_info_needed", "ID Checker — More Info Needed", "Verification", "ID Checker needs additional information")
def build_idv_more_info_needed_email(
    user_name: str = "Alex",
    notes: str = "Please provide a clearer photo of your ID and a matching selfie.",
) -> EmailTemplate:
    support_email = "support@realaicoach.app"
    body = f"""{_alert_panel("More Information Needed", "We need additional information before finalizing your verification decision.", "#F59E0B", "ACTION REQUIRED")}
    {_lead("Additional details required", f"Hi {user_name}, please review the requested items below.")}
    {_info_table([_info_row("Decision", "More Info Needed", "#F59E0B"), _info_row("What happens next", "Submit the requested information and we will continue your verification review."), _info_row("Requested Details", notes), _info_row("Support", support_email)])}
    {_callout(f"If anything is unclear, contact {support_email} and our team will guide you.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"More Information Needed for ID Checker — {BRAND}",
        html=_wrap("More Info Needed", "Additional details required to continue review", body, "Open ID Checker", f"{DASH_URL}/id-checker", "#F59E0B"),
        text=_txt("More Information Needed", f"Hi {user_name}, more information is needed: {notes}. Support: {support_email}", "Open ID Checker", f"{DASH_URL}/id-checker"),
    )


# ── 27. AI Report Ready ─────────────────────────────────


@_register("ai_report", "AI Report Ready", "AI", "AI-generated coaching report delivered")
def build_ai_report_email(
    user_name: str = "Alex",
    report_summary: str = "Your career analysis reveals strong growth in technical skills...",
    report_link: str = "",
    feedback_link: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Your AI Report is Ready", "Your latest AI-generated insight is complete and ready to review.", PRIMARY, "AI READY")}
    {_lead("Your AI Report is Ready", f"Hi {user_name}, your coaching report has been generated.")}
    {_callout(report_summary[:300])}
    <p class="em-text-secondary" style="font-size:11px;color:#64748B;margin:12px 0 0;">AI Disclaimer: This report is generated by AI and should be reviewed before decisions.</p>"""
    return EmailTemplate(
        subject=f"Your AI Report is Ready — {BRAND}",
        html=_wrap("AI Report", "Your report is ready", body, "View Report", report_link or f"{DASH_URL}/features/ai-coaching"),
        text=_txt("AI Report", f"Hi {user_name}, AI report ready. Summary: {report_summary[:200]}"),
    )


# ── 28. Weekly Digest ────────────────────────────────────


@_register("weekly_digest", "Weekly Digest", "Engagement", "Weekly platform activity summary")
def build_weekly_digest_email(
    user_name: str = "Alex", highlights: List[str] = None, stats: List[str] = None
) -> EmailTemplate:
    highlights = highlights or ["Completed 3 coaching sessions", "Career score improved by 12%"]
    stats = stats or ["Active days: 5/7", "Goals completed: 3"]
    hl_html = "".join([f'<li style="color:#0F172A;-webkit-text-fill-color:#0F172A;font-size:14px;margin:6px 0;font-weight:700;">{h}</li>' for h in highlights])
    st_html = "".join([_info_row(s.split(":")[0].strip(), s.split(":")[-1].strip()) for s in stats if ":" in s])
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Your Weekly Summary</p>
    <p style="margin:0 0 16px;">Hi {user_name}, here's what you accomplished this week:</p>
    <div style="margin:0 0 16px;"><p style="color:#64748B;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;">Highlights</p>
    <ul style="margin:0;padding-left:18px;">{hl_html}</ul></div>
    {_info_table([st_html]) if st_html else ""}"""
    return EmailTemplate(
        subject=f"Your Weekly {BRAND} Digest",
        html=_wrap("Weekly Digest", "Your weekly summary", body, "View Dashboard", DASH_URL),
        text=_txt("Weekly Digest", f"Hi {user_name}.\nHighlights: {', '.join(highlights)}"),
    )


# ── 28b. Smart Weekly Digest (premium coaching progress + streaks) ──


@_register("smart_weekly_digest", "Smart Weekly Digest", "Engagement", "Premium per-user weekly coaching progress + streak digest")
def build_smart_weekly_digest_email(
    user_name: str = "Alex",
    streak_days: int = 5,
    longest_streak: int = 12,
    active_day_map: List[bool] = None,
    day_labels: List[str] = None,
    sessions: int = 4,
    active_days: int = 5,
    xp_earned: int = 320,
    total_xp: int = 2140,
    highlights: List[str] = None,
    smart_tip: str = "",
    week_label: str = "",
) -> EmailTemplate:
    active_day_map = active_day_map if active_day_map is not None else [True, True, False, True, True, True, False]
    day_labels = day_labels or ["M", "T", "W", "T", "F", "S", "S"]
    highlights = highlights or [
        "Completed 4 coaching sessions",
        "Earned 320 XP — your best week this month",
        "Practiced interview answers 3 days in a row",
    ]
    smart_tip = smart_tip or "Consistency beats intensity: one 15-minute practice session tomorrow keeps your streak alive and compounds your interview confidence."
    orange = "#EA580C"

    dot_cells = ""
    for i, is_active in enumerate(active_day_map[:7]):
        label = day_labels[i] if i < len(day_labels) else ""
        if is_active:
            circle = f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;background:{orange};border-radius:50%;border:1px solid {orange};"><tr><td class="em-badge" style="width:26px;height:26px;text-align:center;vertical-align:middle;padding:0;color:#FFFFFF;font-size:13px;font-weight:900;line-height:26px;">&#10003;</td></tr></table>'
        else:
            circle = '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;background:#F8FAFC;border-radius:50%;border:1px solid #E2E8F0;"><tr><td style="width:26px;height:26px;text-align:center;vertical-align:middle;padding:0;color:#CBD5E1;font-size:11px;font-weight:700;line-height:26px;">&middot;</td></tr></table>'
        dot_cells += f'<td style="padding:0 4px;text-align:center;">{circle}<div class="em-force-muted-text" style="color:#94A3B8;font-size:9px;font-weight:800;margin-top:5px;letter-spacing:0.5px;">{label}</div></td>'

    streak_headline = f"{streak_days}-day streak" if streak_days > 0 else "Start a new streak"
    hl_html = "".join(
        f'<li style="color:#0F172A;-webkit-text-fill-color:#0F172A;font-size:13px;margin:6px 0;font-weight:600;line-height:1.6;">{h}</li>'
        for h in highlights
    )
    week_line = f'<p class="em-force-muted-text" style="color:#64748B;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 4px;text-align:center;">{week_label}</p>' if week_label else ""

    body = f"""{week_line}
    <div style="border:1px solid #FED7AA;border-radius:14px;background:#FFF7ED;padding:18px 16px 14px;margin:0 0 16px;text-align:center;">
      <p style="color:#0F172A;font-size:42px;font-weight:900;letter-spacing:-1.5px;margin:0;line-height:1;">{streak_days}</p>
      <div style="margin:8px 0 14px;">{_badge(streak_headline.upper(), orange)}</div>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;"><tr>{dot_cells}</tr></table>
      <p class="em-force-muted-text" style="color:#64748B;font-size:11px;margin:12px 0 0;font-weight:600;">Personal best: {longest_streak} day{'s' if longest_streak != 1 else ''}</p>
    </div>
    <p style="margin:0 0 14px;">Hi <strong style="color:#0F172A;">{user_name}</strong>, here's your smart coaching recap for the week:</p>
    {_info_table([
        _info_row("Coaching Sessions", str(sessions)),
        _info_row("Active Days", f"{active_days}/7"),
        _info_row("XP Earned This Week", f"+{xp_earned}", orange),
        _info_row("Total XP", f"{total_xp:,}"),
    ])}
    <div style="margin:16px 0;"><p class="em-force-muted-text" style="color:#64748B;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;">Week Highlights</p>
    <ul style="margin:0;padding-left:18px;">{hl_html}</ul></div>
    <div style="border:1px solid #E2E8F0;border-left:3px solid {orange};border-radius:10px;background:#FFFFFF;padding:12px 14px;margin:0 0 4px;">
      <p class="em-force-muted-text" style="color:#64748B;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1.2px;margin:0 0 6px;">Your Coach's Smart Tip</p>
      <p style="color:#0F172A;font-size:13px;line-height:1.7;margin:0;font-weight:500;">{smart_tip}</p>
    </div>"""

    subject = (
        f"{user_name}, your {streak_days}-day streak & week in review — {BRAND}"
        if streak_days > 0
        else f"{user_name}, your week in review — {BRAND}"
    )
    return EmailTemplate(
        subject=subject,
        html=_wrap(
            "Your Smart Weekly Digest",
            f"{sessions} sessions, {active_days} active days, +{xp_earned} XP this week",
            body,
            "Keep Your Streak Alive",
            DASH_URL,
            category="engagement",
        ),
        text=_txt(
            "Smart Weekly Digest",
            f"Hi {user_name}.\nStreak: {streak_days} days (best {longest_streak}).\nSessions: {sessions} | Active days: {active_days}/7 | XP: +{xp_earned} (total {total_xp}).\nHighlights: {'; '.join(highlights)}\nSmart tip: {smart_tip}",
            "Keep Your Streak Alive",
            DASH_URL,
        ),
    )


# ── 29. Direct Message ───────────────────────────────────


@_register("direct_message", "Direct Message", "Communication", "New direct message notification")
def build_direct_message_email(
    sender_name: str = "Jane Doe",
    message_preview: str = "Hey, I wanted to discuss the coaching plan...",
    thread_url: str = "",
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">New Message</p>
    <p class="em-text-secondary" style="margin:0 0 8px;font-size:12px;color:#64748B;">From <strong class="em-strong" style="color:#0F172A;">{sender_name}</strong></p>
    {_callout(message_preview[:300])}"""
    return EmailTemplate(
        subject=f"New message from {sender_name}",
        html=_wrap(
            "New Message", f"Message from {sender_name}", body, "Reply", thread_url or f"{DASH_URL}/my-tickets"
        ),
        text=_txt("New Message", f"From {sender_name}: {message_preview[:200]}"),
    )


# ── 30. Usage Alert ──────────────────────────────────────


@_register("usage_alert", "Usage Alert", "Billing", "Approaching plan usage limit")
def build_usage_alert_email(
    user_name: str = "Alex",
    usage_metric: str = "85% of AI sessions",
    limit: str = "100 sessions/month",
    reset_date: str = "Apr 1, 2026",
) -> EmailTemplate:
    body = f"""<div style="background:#1C1710;border-radius:12px;padding:14px 20px;margin:0 0 20px;text-align:center;">
      {_badge("USAGE WARNING", "#F59E0B")}
    </div>
    <p style="margin:0 0 16px;">Hi {user_name}, you're approaching your plan limit.</p>
    {_info_table([_info_row("Usage", usage_metric, "#F59E0B"), _info_row("Limit", limit), _info_row("Resets On", reset_date)])}"""
    return EmailTemplate(
        subject=f"Usage alert — {BRAND}",
        html=_wrap(
            "Usage Alert", "You're near your plan limit", body, "Upgrade Plan", f"{DASH_URL}/subscription", "#F59E0B"
        ),
        text=_txt("Usage Alert", f"Hi {user_name}, {usage_metric}. Limit: {limit}. Resets: {reset_date}."),
    )


# ── 31. Feature Update ───────────────────────────────────


@_register("feature_update", "Feature Update", "Engagement", "New platform feature announcement")
def build_feature_update_email(
    title: str = "New AI Career Coach",
    summary: str = "We've launched a powerful new career coaching feature.",
    features: List[str] = None,
    learn_more_link: str = "",
) -> EmailTemplate:
    features = features or ["AI-powered career analysis", "Personalized growth roadmap", "Interview preparation"]
    f_html = "".join([f'<li class="em-text-secondary" style="color:#64748B;font-size:13px;margin:4px 0;">{f}</li>' for f in features])
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">{title}</p>
    <p style="margin:0 0 16px;">{summary}</p>
    <ul style="padding-left:18px;margin:0 0 16px;">{f_html}</ul>"""
    return EmailTemplate(
        subject=f"{title} — {BRAND}",
        html=_wrap(title, "New product update", body, "Learn More", learn_more_link or f"{DASH_URL}/features"),
        text=_txt(title, f"{summary}\n" + "\n".join(f"- {f}" for f in features)),
    )


# ── 32. Team Invitation ──────────────────────────────────


@_register("invitation", "Team Invitation", "Onboarding", "Invitation to join a workspace")
def build_invitation_email(
    inviter_name: str = "Admin", team_name: str = "Growth Team", invite_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">You're Invited!</p>
    <p style="margin:0 0 16px;"><strong class="em-strong" style="color:#0F172A;">{inviter_name}</strong> invited you to join <strong style="color:{PRIMARY};">{team_name}</strong> on <span translate="no" class="notranslate">{BRAND}</span>.</p>
    {_callout("Accept the invitation to access shared coaching insights, reports, and collaboration tools.")}"""
    return EmailTemplate(
        subject=f"Invitation to join {team_name} on {BRAND}",
        html=_wrap("Team Invitation", "You're invited", body, "Accept Invitation", invite_link or f"{DASH_URL}/auth/register", "#10B981"),
        text=_txt("Team Invitation", f"{inviter_name} invited you to join {team_name}."),
    )


# ── 33. Onboarding Nudge ─────────────────────────────────


@_register("onboarding_nudge", "Onboarding Nudge", "Onboarding", "Reminder to complete account setup")
def build_onboarding_nudge_email(user_name: str = "Alex", next_steps: List[str] = None) -> EmailTemplate:
    steps = next_steps or ["Complete your profile", "Upload your resume", "Take the career assessment"]
    s_html = "".join(
        [
            f'<tr><td class="em-info-td" style="padding:10px 14px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><span style="display:inline-block;width:8px;height:8px;background:{PRIMARY};border-radius:50%;margin-right:10px;"></span>{s}</td></tr>'
            for s in steps
        ]
    )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Almost There, {user_name}!</p>
    <p style="margin:0 0 16px;">Complete these steps to unlock your full coaching experience:</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">{s_html}</table>"""
    return EmailTemplate(
        subject=f"Complete your {BRAND} setup",
        html=_wrap("Complete Setup", "Finish your onboarding", body, "Continue Setup", DASH_URL),
        text=_txt("Complete Setup", f"Hi {user_name}, steps: " + ", ".join(steps)),
    )


# ── 34. Account Deleted ──────────────────────────────────


@_register("account_deleted", "Account Deleted", "Account", "Account deletion confirmation")
def build_account_deleted_email(user_name: str = "Alex", deleted_at: str = "Mar 1, 2026") -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Account Deleted</p>
    <p style="margin:0 0 16px;">Hi {user_name}, your account was deleted on {deleted_at}.</p>
    {_callout("If you did not request this, contact support immediately.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"Account deleted — {BRAND}",
        html=_wrap("Account Deleted", "Your account has been removed", body, "Get Help Now", SUPPORT_URL, "#EF4444"),
        text=_txt("Account Deleted", f"Hi {user_name}, account deleted on {deleted_at}."),
    )


# ── 35. Interview Scheduled ──────────────────────────────


@_register("interview_scheduled", "Interview Scheduled", "Hiring", "Candidate interview scheduled notification")
def build_interview_scheduled_email(
    candidate_name: str = "Alex", job_title: str = "Senior Developer", interview_time: str = "Mar 5, 2026 at 2:00 PM"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Interview Scheduled</p>
    <p style="margin:0 0 16px;">Hi {candidate_name}, your interview has been confirmed.</p>
    {_info_table([_info_row("Position", job_title, PRIMARY), _info_row("When", interview_time)])}
    {_callout("Prepare by reviewing the job description and practicing common interview questions.")}"""
    return EmailTemplate(
        subject=f"Interview Scheduled: {job_title}",
        html=_wrap(
            "Interview Scheduled", "Your interview is confirmed", body, "View Details", f"{DASH_URL}/hiring-hub"
        ),
        text=_txt("Interview Scheduled", f"Hi {candidate_name}, interview for {job_title} at {interview_time}."),
    )


# ── 36. Trial Expiration ─────────────────────────────────


@_register("trial_expiration", "Trial Expiring", "Billing", "Free trial ending notification")
def build_trial_expiration_email(
    user_name: str = "Alex", trial_end_date: str = "Mar 7, 2026", upgrade_link: str = ""
) -> EmailTemplate:
    body = f"""<div style="background:#1C1710;border-radius:12px;padding:14px 20px;margin:0 0 20px;text-align:center;">
      {_badge("TRIAL ENDING", "#F59E0B")}
    </div>
    <p style="margin:0 0 16px;">Hi {user_name}, your free trial ends on <strong style="color:#F59E0B;">{trial_end_date}</strong>.</p>
    {_callout("Upgrade now to keep uninterrupted access to all features.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Trial ending — {BRAND}",
        html=_wrap(
            "Trial Ending",
            "Your trial is ending soon",
            body,
            "Upgrade Now",
            upgrade_link or f"{DASH_URL}/subscription/plans",
            "#F59E0B",
        ),
        text=_txt("Trial Ending", f"Hi {user_name}, trial ends {trial_end_date}. Upgrade now."),
    )


# ── Daily Digest Email ────────────────────────────────────


@_register("daily_digest", "Daily Digest", "Notifications", "Daily summary of unread notifications")
def build_daily_digest_email(
    user_name: str = "Alex",
    unread_count: int = 5,
    notifications: list = None,
    date_str: str = "",
) -> str:
    """Build a daily digest email summarising unread notifications from the past 24h."""
    if not date_str:
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    notifications = notifications or [
        {"type": "coaching", "title": "New coaching session available", "body": "Your AI coach has prepared a personalized session based on your recent activity."},
        {"type": "goal", "title": "Goal milestone reached", "body": "You've completed 3 out of 5 weekly targets. Keep up the momentum!"},
        {"type": "system", "title": "New feature: Daily Briefing", "body": "Start your day with an AI-curated summary of what matters most."},
    ]

    # Group by type
    groups: dict = {}
    for n in notifications:
        ntype = n.get("type", "general")
        label = ntype.replace("_", " ").title()
        groups.setdefault(label, []).append(n)

    rows_html = ""
    for label, items in groups.items():
        items_html = "".join(
            f'<li class="em-text-secondary" style="color:#64748B;font-size:13px;margin:4px 0;line-height:1.5;">{i.get("title", "")}: {i.get("body", "")[:120]}</li>'
            for i in items[:5]
        )
        extra = (
            f'<li class="em-text-secondary" style="color:#64748B;font-size:12px;margin:4px 0;">…and {len(items) - 5} more</li>'
            if len(items) > 5
            else ""
        )
        rows_html += f"""<div style="margin:0 0 16px;">
          <p style="color:#64748B;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">{label} ({len(items)})</p>
          <ul style="margin:0;padding-left:18px;">{items_html}{extra}</ul>
        </div>"""

    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 16px;">Daily Digest — {date_str}</p>
    <p style="margin:0 0 16px;">Hi {user_name}, you have <strong style="color:#22D3EE;">{unread_count}</strong> unread notification{"s" if unread_count != 1 else ""} from the past 24 hours.</p>
    {rows_html}"""

    return EmailTemplate(
        subject=f"Your {BRAND} Daily Digest — {unread_count} unread",
        html=_wrap(
            "Daily Digest",
            f"{unread_count} unread notifications",
            body,
            "View All Notifications",
            f"{DASH_URL}/notifications",
        ),
        text=_txt("Daily Digest", f"Hi {user_name}, you have {unread_count} unread notifications."),
    )


# ── Generic notification email for real-time engine ──────


def build_notification_email(title: str, body_text: str, action_url: str = "", accent: str = "") -> str:
    """Build a generic notification email HTML for the notification engine."""
    inner = f'<p class="em-text-secondary" style="color:#64748B;font-size:14px;line-height:1.75;">{body_text}</p>'
    return _wrap(title, title, inner, "View Details" if action_url else "", action_url, accent)


def build_admin_system_alert_email(
    title: str,
    intro: str,
    rows: list[tuple[str, str]],
    *,
    accent: str = "#F59E0B",
    status_label: str = "NOTICE",
    footer_note: str = "",
    cta_label: str = "",
    cta_url: str = "",
) -> str:
    """Reusable enterprise-safe alert email for integrity/performance/admin system summaries."""
    row_html = "".join(
        f"""
        <tr>
          <td class="em-force-muted-text" style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;font-weight:600;color:#64748B;">{label}</td>
          <td class="em-force-dark-text" style="padding:10px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;font-weight:700;color:#0F172A;">{value}</td>
        </tr>
        """
        for label, value in rows
    )
    footer_block = (
        f'<p class="em-text-secondary" style="margin:16px 0 0;font-size:12px;color:#64748B;">{footer_note}</p>'
        if footer_note else ""
    )
    inner = f"""
    <p class="em-title" style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 10px;">{intro}</p>
    <div style="display:inline-block;padding:5px 10px;border-radius:999px;background:{accent}18;border:1px solid {accent}35;margin:0 0 16px;">
      <span style="color:{accent};font-size:11px;font-weight:800;letter-spacing:0.6px;text-transform:uppercase;">{status_label}</span>
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-force-light-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden;">
      {row_html}
    </table>
    {footer_block}
    """
    return _wrap(title, title, inner, cta_label, cta_url, accent)


def brand_email(body_html: str, theme: str = "light", category: str = "general") -> str:
    """Universal wrapper that adds app logo header + enterprise footer to ANY email body HTML.

    Accepts raw HTML body content and wraps it with:
      - Colorful gradient header with app logo (category-specific)
      - The provided body HTML (untouched)
      - Enterprise footer (app download, quick links, social, address, legal)
    
    Auto-adaptive: includes prefers-color-scheme CSS for dark/light mode.
    """
    from utils.email_service import CDN_APP_LOGO
    is_dark = theme == "dark"
    bg = "#0B0F1A" if is_dark else "#F8FAFC"
    card_bg = "#111827" if is_dark else "#FFFFFF"
    card_text = "#E2E8F0" if is_dark else "#0F172A"
    border = "#1E293B" if is_dark else "#E2E8F0"
    footer = _enterprise_footer(theme)
    cc = _cat_colors(category)

    card_class = "em-card" if is_dark else "em-card em-force-light-card"
    card_attrs = ' data-keep-dark="1"' if is_dark else ''

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{_responsive_styles()}</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:{bg};-webkit-font-smoothing:antialiased;" class="em-outer">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-outer em-outer"><tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;" class="email-card em-card">
  <!-- Gradient Header -->
  <tr><td style="background-image:linear-gradient(135deg,{cc['gf']},{cc['gt']});border-radius:16px 16px 0 0;text-align:center;padding:28px 24px 20px;">
    <img src="{CDN_APP_LOGO}" alt="{BRAND}" style="width:56px;height:56px;border-radius:14px;display:block;margin:0 auto 12px;border:2px solid rgba(255,255,255,0.2);" />
    <span style="display:inline-block;padding:5px 14px;background:rgba(255,255,255,0.18);border-radius:99px;color:#FFFFFF;font-size:11px;font-weight:700;letter-spacing:0.5px;">{BRAND}</span>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:0 4px;">
    <div class="{card_class}" style="background:{card_bg};border-radius:0 0 16px 16px;border:1px solid {border};border-top:none;overflow:hidden;color:{card_text};"{card_attrs}>
      {body_html}
    </div>
  </td></tr>
  <!-- Enterprise Footer -->
  {footer}
</table>
</td></tr></table>
</body></html>"""


# ═══════════════════════════════════════════════════════════
#  ADMIN PREVIEW — Generate all templates with sample data
# ═══════════════════════════════════════════════════════════


def get_all_template_previews(overrides: dict = None) -> list:
    """Return all templates with sample HTML for admin preview.
    If overrides dict is provided {key: {accent, cta_label, cta_url, footer, subject, header}},
    apply them to matching templates.
    """
    overrides = overrides or {}
    previews = []
    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            ovr = overrides.get(key, {})
            html = tpl.html
            subject = ovr.get("subject") or tpl.subject
            if ovr:
                html = apply_overrides_to_html(html, ovr)
            from utils.email_service import apply_adaptive_email_contrast_guard
            html = apply_adaptive_email_contrast_guard(html)
            previews.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "description": info["description"],
                    "subject": subject,
                    "html": html,
                    "has_override": bool(ovr),
                    "overrides": ovr if ovr else None,
                }
            )
        except Exception as e:
            previews.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "description": info["description"],
                    "subject": f"Error: {e}",
                    "html": f"<p>Template rendering error: {e}</p>",
                    "has_override": False,
                    "overrides": None,
                }
            )
    return previews


def render_template_with_overrides(key: str, overrides: dict) -> Optional[dict]:
    """Render a single template with overrides applied. Returns {subject, html, text} or None."""
    info = TEMPLATE_CATALOG.get(key)
    if not info:
        return None
    try:
        tpl = info["builder"]()
        html = apply_overrides_to_html(tpl.html, overrides) if overrides else tpl.html
        from utils.email_service import apply_adaptive_email_contrast_guard
        html = apply_adaptive_email_contrast_guard(html)
        subject = overrides.get("subject") or tpl.subject
        return {"subject": subject, "html": html, "text": tpl.text, "key": key, "label": info["label"]}
    except Exception as e:
        return {
            "subject": f"Error: {e}",
            "html": f"<p>{e}</p>",
            "text": str(e),
            "key": key,
            "label": info.get("label", key),
        }


def apply_overrides_to_html(html: str, ovr: dict) -> str:
    """Apply admin overrides to rendered HTML."""
    import re

    result = html

    # Override accent color — replace the primary color throughout
    accent = ovr.get("accent_color", "").strip()
    if accent and len(accent) == 7 and accent.startswith("#"):
        result = result.replace(PRIMARY, accent)

    # Override CTA button label
    cta_label = ovr.get("cta_label", "").strip()
    if cta_label:
        result = re.sub(
            r'(<a[^>]*class="[^"]*email-primary-cta[^"]*"[^>]*>)[^<]*(</a>)',
            rf"\g<1>{cta_label}\2",
            result,
            count=1,
        )

    # Override CTA URL
    cta_url = ovr.get("cta_url", "").strip()
    if cta_url:
        result = re.sub(
            r'(<a href=")[^"]*("[^>]*class="[^"]*email-primary-cta[^"]*")',
            rf"\g<1>{cta_url}\2",
            result,
            count=1,
        )

    # Override footer text
    footer = ovr.get("footer_text", "").strip()
    if footer:
        result = re.sub(
            r'(<p class="footer-legal-text"[^>]*>)(.*?)(<br\s*/?>)',
            rf"\1{footer}\3",
            result,
            flags=re.DOTALL,
            count=1,
        )

    # Override header title
    header = ovr.get("header_title", "").strip()
    if header:
        result = re.sub(
            r'(<div class="email-header-title"[^>]*>)[^<]*(</div>)',
            rf"\g<1>{header}\2",
            result,
            count=1,
        )

    return result


# ═══════════════════════════════════════════════════════════
#  5-Day Onboarding Drip Campaign
# ═══════════════════════════════════════════════════════════


@_register("drip_day1", "Drip Day 1 - Quick Start", "Onboarding Drip", "Day 1: Welcome + quick start guide")
def build_drip_day1(user_name: str = "Alex") -> EmailTemplate:
    body = f"""{_lead(f"Welcome to {BRAND_NT}, {user_name}!", "Your AI coaching journey starts now. Here are 3 things to do in your first 5 minutes:")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><span style="color:#10B981;font-weight:700;margin-right:10px;">1.</span> Complete your profile &mdash; helps the AI personalize your coaching</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><span style="color:#10B981;font-weight:700;margin-right:10px;">2.</span> Start your first conversation &mdash; ask anything about your career</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;"><span style="color:#10B981;font-weight:700;margin-right:10px;">3.</span> Explore AI Features &mdash; try speech, writing, or document analysis</td></tr>
    </table>
    {_callout("Pro tip: The more you interact with the AI, the better it understands your goals and coaching needs.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Your first 5 minutes with {BRAND}",
        html=_wrap("Quick Start Guide", "3 things to do in your first 5 minutes", body, "Start Now", DASH_URL, "#10B981"),
        text=_txt("Quick Start Guide", f"Welcome {user_name}! 1) Complete profile 2) Start conversation 3) Explore AI features"),
    )


@_register("drip_day2", "Drip Day 2 - AI Coaching", "Onboarding Drip", "Day 2: AI coaching tips and best practices")
def build_drip_day2(user_name: str = "Alex") -> EmailTemplate:
    body = f"""{_lead("Get More from AI Coaching", f"{user_name}, here's how top performers use {BRAND_NT}:")}
    {_alert_panel("Smart Prompting", "Be specific with your goals. Instead of 'help with my career', try 'I want to negotiate a 20% raise at my next review'.", "#6366F1", "AI TIP")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><strong style="color:#6366F1;">Role Reversal</strong> &mdash; Practice tough conversations with AI playing your boss, client, or interviewer</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><strong style="color:#6366F1;">Tone Analysis</strong> &mdash; Get real-time feedback on how your messages sound</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;"><strong style="color:#6366F1;">Action Plans</strong> &mdash; Turn coaching insights into actionable step-by-step plans</td></tr>
    </table>"""
    return EmailTemplate(
        subject="AI coaching secrets top performers use",
        html=_wrap("AI Coaching Tips", "How top performers use AI coaching", body, "Try AI Coaching", f"{DASH_URL}/features/ai-coaching", "#6366F1"),
        text=_txt("AI Coaching Tips", f"Hi {user_name}, try: Role Reversal, Tone Analysis, Action Plans"),
    )


@_register("drip_day3", "Drip Day 3 - Features", "Onboarding Drip", "Day 3: Feature highlights and tools")
def build_drip_day3(user_name: str = "Alex") -> EmailTemplate:
    body = f"""{_lead("Unlock Your Full Toolkit", f"{user_name}, did you know {BRAND_NT} has 30+ AI-powered tools?")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
      <tr><td class="em-info-td" style="padding:14px 18px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><span style="font-size:18px;margin-right:8px;">&#x1f4dd;</span> <strong class="em-strong" style="color:#0F172A;">AI Writer</strong> &mdash; Draft emails, reports, and documents in seconds</td></tr>
      <tr><td class="em-info-td" style="padding:14px 18px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><span style="font-size:18px;margin-right:8px;">&#x1f4ca;</span> <strong class="em-strong" style="color:#0F172A;">Analytics</strong> &mdash; Track your progress with AI-powered insights</td></tr>
      <tr><td class="em-info-td" style="padding:14px 18px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><span style="font-size:18px;margin-right:8px;">&#x1f3a4;</span> <strong class="em-strong" style="color:#0F172A;">Speech & Vision</strong> &mdash; Analyze images, extract text, translate languages</td></tr>
      <tr><td class="em-info-td" style="padding:14px 18px;color:#64748B;font-size:13px;"><span style="font-size:18px;margin-right:8px;">&#x1f4f1;</span> <strong class="em-strong" style="color:#0F172A;">Mobile Ready</strong> &mdash; Full experience on any device, anywhere</td></tr>
    </table>
    {_callout("Each tool is designed to save you time and help you make better decisions faster.", PRIMARY)}"""
    return EmailTemplate(
        subject="30+ AI tools you haven't tried yet",
        html=_wrap("Feature Highlights", "Discover your full AI toolkit", body, "Explore Features", f"{DASH_URL}/features", PRIMARY),
        text=_txt("Feature Highlights", f"Hi {user_name}, try: AI Writer, Analytics, Speech & Vision, Mobile app"),
    )


@_register("drip_day4", "Drip Day 4 - Power User", "Onboarding Drip", "Day 4: Power user tips and automations")
def build_drip_day4(user_name: str = "Alex") -> EmailTemplate:
    body = f"""{_lead("Become a Power User", f"{user_name}, here are advanced tips to 10x your productivity:")}
    {_alert_panel("Automation", "Set up AI automations to handle routine tasks. Get daily briefings, auto-generated reports, and smart scheduling.", "#F59E0B", "POWER")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><strong style="color:#F59E0B;">Export Everything</strong> &mdash; Download coaching sessions as PDF, DOCX, or CSV</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;border-bottom:1px solid #E2E8F0;"><strong style="color:#F59E0B;">Daily Digest</strong> &mdash; Get an AI-curated summary of your progress every morning</td></tr>
      <tr><td class="em-step-td" style="padding:14px 18px;color:#0F172A;font-size:14px;"><strong style="color:#F59E0B;">API Access</strong> &mdash; Integrate {BRAND_NT} into your existing workflow tools</td></tr>
    </table>"""
    return EmailTemplate(
        subject="Power user secrets: automations & exports",
        html=_wrap("Power User Tips", "10x your productivity with these tips", body, "Try Automations", f"{DASH_URL}/features/ai-automations", "#F59E0B"),
        text=_txt("Power User Tips", f"Hi {user_name}, try: Automation, Export to PDF/DOCX, Daily Digest, API access"),
    )


@_register("drip_day5", "Drip Day 5 - Upgrade Offer", "Onboarding Drip", "Day 5: Limited-time upgrade offer")
def build_drip_day5(user_name: str = "Alex", discount_pct: int = 30) -> EmailTemplate:
    body = f"""{_lead("Special Offer Just for You", f"{user_name}, you've been exploring {BRAND_NT} for 5 days. Here's an exclusive upgrade offer:")}
    {_alert_panel(f"{discount_pct}% Off Your First Month", f"Upgrade to Basic or Premium in the next 48 hours and save {discount_pct}% on your first month. No commitment &mdash; cancel anytime.", "#10B981", "LIMITED OFFER")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;overflow:hidden;">
      {_info_row("Basic Plan", f"<s style='color:#64748B;'>$5.99</s> <strong style='color:#10B981;'>${5.99 * (100 - discount_pct) / 100:.2f}/mo</strong>", "#10B981")}
      {_info_row("Premium Plan", f"<s style='color:#64748B;'>$15.99</s> <strong style='color:#F59E0B;'>${15.99 * (100 - discount_pct) / 100:.2f}/mo</strong>", "#F59E0B")}
      {_info_row("Offer Expires", "48 hours from now", "#EF4444")}
    </table>
    {_callout("This offer is exclusive to new members during their first week. Upgrade now to lock in your discount.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Exclusive: {discount_pct}% off your upgrade (48h only)",
        html=_wrap("Exclusive Offer", f"{discount_pct}% off — 48 hours only", body, "Upgrade Now", f"{DASH_URL}/subscription/plans", "#10B981"),
        text=_txt("Exclusive Offer", f"Hi {user_name}, get {discount_pct}% off Basic ($4.19/mo) or Premium ($11.19/mo). 48h only."),
    )


DRIP_CAMPAIGN_DAYS = {
    1: {"builder": "build_drip_day1", "template_key": "drip_day1"},
    2: {"builder": "build_drip_day2", "template_key": "drip_day2"},
    3: {"builder": "build_drip_day3", "template_key": "drip_day3"},
    4: {"builder": "build_drip_day4", "template_key": "drip_day4"},
    5: {"builder": "build_drip_day5", "template_key": "drip_day5"},
}


# ═══════════════════════════════════════════════════════════
#  Daily Job Alerts — Enterprise-grade (LinkedIn/Indeed level)
# ═══════════════════════════════════════════════════════════


def _job_card(job: dict, is_authenticated: bool = True, index: int = 0) -> str:
    """Render a single job listing card for the job alert email."""
    title = job.get("title", "Untitled Position")
    company = job.get("company_name", "Company")
    location = job.get("location", "Remote")
    loc_type = job.get("location_type", "remote")
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    currency = job.get("salary_currency", "USD")
    period = job.get("salary_period", "year")
    easy_apply = job.get("easy_apply", False)
    actively_recruiting = job.get("actively_recruiting", False)
    job_id = job.get("job_id", "")
    job.get("industry", "")
    exp_level = job.get("experience_level", "")
    job.get("employment_type", "full_time")
    job.get("posted_at", "")
    match_score = job.get("match_score")
    match_reason = job.get("match_reason", "")

    # Currency symbols
    cur_map = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "CAD": "CA$", "AUD": "A$"}
    cur_sym = cur_map.get(currency, currency + " ")

    # Salary display
    salary_html = ""
    if salary_min and salary_max:
        def _fmt_sal(v):
            if v >= 1000:
                return f"{v/1000:.0f}K"
            return str(v)
        salary_html = f'<p class="em-text" style="color:#10B981;font-size:13px;font-weight:700;margin:4px 0 0;">{cur_sym}{_fmt_sal(salary_min)} &ndash; {cur_sym}{_fmt_sal(salary_max)} / {period}</p>'

    # Location type badge
    loc_colors = {"remote": "#8B5CF6", "hybrid": "#3B82F6", "onsite": "#F59E0B"}
    loc_labels = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}
    loc_color = loc_colors.get(loc_type, "#64748B")
    loc_label = loc_labels.get(loc_type, loc_type.capitalize())

    # Badges — use _color_tint() for email-safe solid colors (8-digit hex unsupported by email clients)
    badges_html = ""
    badge_parts = []
    badge_parts.append(f'<span style="display:inline-block;padding:3px 10px;background:{_color_tint(loc_color, 0x18)};color:{loc_color};font-size:10px;font-weight:700;border-radius:99px;letter-spacing:0.3px;margin-right:6px;">{loc_label}</span>')
    if easy_apply:
        badge_parts.append(f'<span style="display:inline-block;padding:3px 10px;background:{_color_tint("#10B981", 0x18)};color:#10B981;font-size:10px;font-weight:700;border-radius:99px;letter-spacing:0.3px;margin-right:6px;">&#x26A1; Easy Apply</span>')
    if actively_recruiting:
        badge_parts.append(f'<span style="display:inline-block;padding:3px 10px;background:{_color_tint("#F59E0B", 0x18)};color:#F59E0B;font-size:10px;font-weight:700;border-radius:99px;letter-spacing:0.3px;">Actively Recruiting</span>')
    if exp_level:
        exp_map = {"entry": "Entry Level", "mid": "Mid Level", "senior": "Senior", "lead": "Lead", "executive": "Executive"}
        exp_label = exp_map.get(exp_level, exp_level.capitalize())
        badge_parts.append(f'<span style="display:inline-block;padding:3px 10px;background:{_color_tint("#64748B", 0x18)};color:#64748B;font-size:10px;font-weight:700;border-radius:99px;letter-spacing:0.3px;">{exp_label}</span>')
    badges_html = '<div style="margin-top:8px;line-height:2;">' + "".join(badge_parts) + '</div>'

    # Company initial avatar (enterprise-grade fallback when no logo URL)
    initial = company[0].upper() if company else "C"
    avatar_colors = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444", "#EC4899"]
    av_color = avatar_colors[index % len(avatar_colors)]
    avatar_html = f'<div style="width:44px;height:44px;border-radius:10px;background:{_color_tint(av_color, 0x18)};border:1px solid {_color_tint(av_color, 0x30)};color:{av_color};font-size:18px;font-weight:800;line-height:44px;text-align:center;flex-shrink:0;">{initial}</div>'

    # Match score badge
    match_html = ""
    if match_score is not None and is_authenticated:
        sc = int(match_score)
        mc = "#10B981" if sc >= 80 else "#F59E0B" if sc >= 60 else "#64748B"
        match_html = f'<div style="display:inline-block;padding:3px 8px;background:{_color_tint(mc, 0x15)};border:1px solid {_color_tint(mc, 0x30)};border-radius:6px;margin-bottom:4px;"><span style="color:{mc};font-size:10px;font-weight:800;">{sc}% match</span></div>'
        if match_reason:
            match_html += f'<p class="em-text-muted" style="color:#94A3B8;font-size:10px;margin:2px 0 0;line-height:1.4;">{match_reason}</p>'

    # CTA button
    job_url = f"{DASH_URL}/careers?job={job_id}"
    if is_authenticated:
        cta_html = f'<a href="{job_url}" style="display:inline-block;padding:8px 20px;background:{PRIMARY};color:#FFFFFF;font-size:12px;font-weight:700;text-decoration:none;border-radius:8px;letter-spacing:0.3px;">View &amp; Apply</a>'
    else:
        signup_url = f"{DASH_URL}/register?ref=job_alert&job={job_id}"
        cta_html = f'<a href="{signup_url}" style="display:inline-block;padding:8px 20px;background:#10B981;color:#FFFFFF;font-size:12px;font-weight:700;text-decoration:none;border-radius:8px;letter-spacing:0.3px;">Sign Up to Apply</a>'

    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="em-info-tbl" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;margin:0 0 12px;overflow:hidden;">
      <tr><td class="em-step-td" style="padding:16px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="width:44px;vertical-align:top;padding-right:14px;">{avatar_html}</td>
          <td style="vertical-align:top;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
              <td>
                <p class="em-title" style="color:#0F172A;font-size:15px;font-weight:700;margin:0;line-height:1.3;">{title}</p>
                <p class="em-text" style="color:#64748B;font-size:12px;margin:2px 0 0;">{company} &middot; {location}</p>
                {salary_html}
                {badges_html}
              </td>
              <td style="vertical-align:top;text-align:right;white-space:nowrap;padding-left:12px;">
                {match_html}
                <div style="margin-top:6px;">{cta_html}</div>
              </td>
            </tr></table>
          </td>
        </tr></table>
      </td></tr>
    </table>'''


def _build_job_alerts_body(
    user_name: str = "there",
    jobs: list = None,
    is_authenticated: bool = True,
    job_count: int = 0,
    unsubscribe_url: str = "",
) -> str:
    """Build the inner HTML body for daily job alerts."""
    if jobs is None:
        jobs = []

    # Header greeting
    greeting = f"Hi {user_name}," if user_name != "there" else "Hi there,"
    count = job_count or len(jobs)
    plural = "s" if count != 1 else ""

    body = f'''{_lead("Your Daily Job Alerts", f"{greeting} <strong>{count} new job{plural}</strong> matching your profile were posted today.")}'''

    if not is_authenticated:
        body += f'''<div class="em-alert" style="background:{_color_tint("#10B981", 0x12)};border:1px solid {_color_tint("#10B981", 0x30)};border-radius:12px;padding:14px 18px;margin:0 0 18px;">
          <p class="em-alert-title" style="color:#10B981;font-weight:700;font-size:13px;margin:0 0 4px;">Create a free account to apply</p>
          <p class="em-alert-text em-text" style="color:#374151;font-size:12px;line-height:1.6;margin:0;">Sign up in 30 seconds to access all jobs, get AI-powered matching, and apply with one click.</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 0;">
            <tr><td align="center" bgcolor="#10B981" style="border-radius:10px;background:#10B981;text-align:center;">
              <a href="{DASH_URL}/register?ref=job_alert" target="_blank" style="background:#10B981;border-radius:10px;display:inline-block;padding:14px 40px;color:#FFFFFF;font-size:14px;font-weight:800;text-decoration:none;letter-spacing:0.3px;">Create Free Account</a>
            </td></tr>
          </table>
        </div>'''

    # Job cards
    for i, job in enumerate(jobs[:8]):
        body += _job_card(job, is_authenticated=is_authenticated, index=i)

    # "See all jobs" CTA
    if count > len(jobs[:8]):
        body += f'<p style="text-align:center;margin:16px 0 0;"><a href="{DASH_URL}/careers" style="color:{PRIMARY};font-size:13px;font-weight:600;text-decoration:none;">See all {count} jobs &rarr;</a></p>'

    # How to apply instructions
    if is_authenticated:
        body += f'''<div class="em-callout" style="background:{_color_tint("#3B82F6", 0x10)};border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#374151;line-height:1.7;">
          <strong class="em-title" style="color:#0F172A;">How to apply:</strong> Click &ldquo;View &amp; Apply&rdquo; on any job &rarr; Review the full description &rarr; Submit your application with one click from your {BRAND_NT} profile.
        </div>'''
    else:
        body += f'''<div class="em-callout" style="background:{_color_tint("#10B981", 0x10)};border-left:3px solid #10B981;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#374151;line-height:1.7;">
          <strong class="em-title" style="color:#0F172A;">How to get started:</strong> <a href="{DASH_URL}/register?ref=job_alert" style="color:#10B981;font-weight:600;">Create your free account</a> &rarr; Build your profile &rarr; Apply to jobs with one click. It takes less than 30 seconds.
        </div>'''

    # Unsubscribe + preferences (both links, as requested)
    prefs_url = _platform_url("/settings?tab=notifications", "job_alerts", "preferences")
    unsub_url = _to_absolute_https(
        unsubscribe_url or _platform_url("/settings?tab=notifications&unsub=job_alerts", "job_alerts", "unsubscribe"),
        "/settings?tab=notifications&unsub=job_alerts",
    )
    body += f'''<div style="text-align:center;margin:24px 0 0;padding-top:16px;border-top:1px solid #E2E8F0;">
      <p class="em-text-muted" style="color:#94A3B8;font-size:11px;margin:0;">You received this because you&rsquo;re subscribed to daily job alerts.</p>
      <p style="margin:6px 0 0;"><a href="{prefs_url}" style="color:#64748B;font-size:11px;text-decoration:underline;" data-testid="preferences-link">Manage preferences</a> &middot; <a href="{unsub_url}" style="color:#64748B;font-size:11px;text-decoration:underline;" data-testid="unsubscribe-link">Unsubscribe from job alerts</a></p>
    </div>'''

    return body


# Sample jobs for template preview
_SAMPLE_JOBS = [
    {"job_id": "preview_1", "title": "Senior AI/ML Engineer", "company_name": "NovaTech Solutions", "location": "San Francisco, CA", "location_type": "hybrid", "salary_min": 180000, "salary_max": 260000, "salary_currency": "USD", "salary_period": "year", "easy_apply": True, "actively_recruiting": True, "experience_level": "senior", "industry": "Technology", "posted_at": "2026-03-19T10:00:00Z", "match_score": 95, "match_reason": "Strong ML/AI skills match"},
    {"job_id": "preview_2", "title": "Product Manager - Growth", "company_name": "CloudScale Inc.", "location": "New York, NY", "location_type": "remote", "salary_min": 140000, "salary_max": 200000, "salary_currency": "USD", "salary_period": "year", "easy_apply": True, "actively_recruiting": False, "experience_level": "mid", "industry": "SaaS", "posted_at": "2026-03-19T06:00:00Z", "match_score": 82, "match_reason": "SaaS experience aligns"},
    {"job_id": "preview_3", "title": "Full Stack Developer", "company_name": "FinEdge Technologies", "location": "London, UK", "location_type": "hybrid", "salary_min": 85000, "salary_max": 120000, "salary_currency": "GBP", "salary_period": "year", "easy_apply": False, "actively_recruiting": True, "experience_level": "mid", "industry": "Finance", "posted_at": "2026-03-19T14:00:00Z", "match_score": 78, "match_reason": "Full stack skills relevant"},
    {"job_id": "preview_4", "title": "UX Designer - Enterprise", "company_name": "DesignHub Global", "location": "Berlin, Germany", "location_type": "remote", "salary_min": 70000, "salary_max": 95000, "salary_currency": "EUR", "salary_period": "year", "easy_apply": True, "actively_recruiting": False, "experience_level": "senior", "industry": "Design", "posted_at": "2026-03-19T04:00:00Z", "match_score": 65, "match_reason": "Design background partial match"},
    {"job_id": "preview_5", "title": "DevOps Engineer", "company_name": "InfraCore Systems", "location": "Austin, TX", "location_type": "onsite", "salary_min": 130000, "salary_max": 175000, "salary_currency": "USD", "salary_period": "year", "easy_apply": False, "actively_recruiting": True, "experience_level": "senior", "industry": "Infrastructure", "posted_at": "2026-03-19T16:00:00Z", "match_score": 88, "match_reason": "Infrastructure & DevOps match"},
]


@_register("daily_job_alerts", "Daily Job Alerts", "Jobs", "Daily digest of new job postings for subscribed users")
def build_daily_job_alerts_email(
    user_name: str = "Alex",
    jobs: list = None,
    is_authenticated: bool = True,
    job_count: int = 0,
    unsub_url: str = "",
) -> EmailTemplate:
    """Enterprise-grade daily job alerts email — LinkedIn/Indeed level."""
    sample_jobs = jobs or _SAMPLE_JOBS
    count = job_count or len(sample_jobs)
    plural = "s" if count != 1 else ""

    body = _build_job_alerts_body(
        user_name=user_name,
        jobs=sample_jobs,
        is_authenticated=is_authenticated,
        job_count=count,
        unsubscribe_url=unsub_url,
    )

    accent = PRIMARY if is_authenticated else "#10B981"
    cta_label = "Browse All Jobs" if is_authenticated else "Sign Up & Apply"
    cta_url = f"{DASH_URL}/careers" if is_authenticated else f"{DASH_URL}/register?ref=job_alert"

    return EmailTemplate(
        subject=f"{count} new job{plural} matching your profile — {BRAND}",
        html=_wrap(
            "Daily Job Alerts",
            f"{count} new job{plural} were posted today",
            body,
            cta_label,
            cta_url,
            accent,
        ),
        text=_txt("Daily Job Alerts", f"Hi {user_name}, {count} new jobs posted: " + ", ".join(j.get("title", "") for j in sample_jobs[:5])),
    )


@_register("search_alert_instant", "Search Alert — Instant Matches", "Jobs", "Instant notification when new roles match a saved job-search alert")
def build_search_alert_instant_email(
    user_name: str = "Alex",
    alert_sections: list = None,
    total_new: int = 0,
    unsub_url: str = "",
) -> EmailTemplate:
    """Instant '⚡ N new roles match your alert' email for saved job searches."""
    sections = alert_sections or [
        {"label": "engineer", "roles": [
            {"title": "Senior Platform Engineer", "meta": "Engineering · Remote"},
            {"title": "AI Infrastructure Engineer", "meta": "AI Lab · Paris, FR"},
        ]},
    ]
    total = total_new or sum(len(s.get("roles") or []) for s in sections)
    plural = "s" if total != 1 else ""

    parts = [
        f'<p style="margin:0 0 14px;color:#334155;font-size:14px;line-height:1.6;">'
        f'Hi {user_name}, your saved search alert{"s" if len(sections) != 1 else ""} just matched '
        f'<strong>{total} new role{plural}</strong>. Be an early applicant.</p>'
    ]
    for section in sections:
        label = str(section.get("label") or "Saved search")
        roles = list(section.get("roles") or [])
        parts.append(
            f'<p style="margin:18px 0 8px;font-size:13px;font-weight:700;color:#0F172A;">'
            f'&#9889; &ldquo;{label}&rdquo; &mdash; {len(roles)} new match{"es" if len(roles) != 1 else ""}</p>'
        )
        for role in roles[:5]:
            title = str(role.get("title") or "New role")
            meta = str(role.get("meta") or "")
            parts.append(
                f'<div style="border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;margin:0 0 8px;background:#F8FAFC;">'
                f'<div style="font-size:14px;font-weight:700;color:#0F172A;">{title}</div>'
                + (f'<div style="font-size:12px;color:#64748B;margin-top:3px;">{meta}</div>' if meta else "")
                + "</div>"
            )
        if len(roles) > 5:
            parts.append(f'<p style="margin:2px 0 0;font-size:12px;color:#64748B;">+ {len(roles) - 5} more matching roles</p>')

    if unsub_url:
        parts.append(
            f'<p style="margin:20px 0 0;font-size:11px;color:#94A3B8;">Too many emails? '
            f'<a href="{unsub_url}" style="color:#64748B;">Unsubscribe from job alerts</a>.</p>'
        )

    return EmailTemplate(
        subject=f"\u26a1 {total} new role{plural} match{'es' if total == 1 else ''} your search alert{'s' if len(sections) != 1 else ''} \u2014 {BRAND}",
        html=_wrap(
            "Search Alert Matches",
            f"{total} new matching role{plural} just landed",
            "".join(parts),
            "Review matches",
            f"{DASH_URL}/job-search",
            PRIMARY,
        ),
        text=_txt(
            "Search Alert Matches",
            f"Hi {user_name}, {total} new role{plural} match your saved search alert{'s' if len(sections) != 1 else ''}: "
            + ", ".join(r.get("title", "") for s in sections for r in (s.get("roles") or [])[:3]),
            "Review matches",
            f"{DASH_URL}/job-search",
        ),
    )


@_register("daily_job_alerts_guest", "Daily Job Alerts (Guest)", "Jobs", "Job alerts for non-authenticated users with signup CTA")
def build_daily_job_alerts_guest_email(
    jobs: list = None,
    job_count: int = 0,
) -> EmailTemplate:
    """Job alerts for non-authenticated/guest users — includes signup CTA."""
    sample_jobs = jobs or _SAMPLE_JOBS
    count = job_count or len(sample_jobs)

    body = _build_job_alerts_body(
        user_name="there",
        jobs=sample_jobs,
        is_authenticated=False,
        job_count=count,
    )

    return EmailTemplate(
        subject=f"{count} new job {'opportunities' if count != 1 else 'opportunity'} on {BRAND} — Don't miss out!",
        html=_wrap(
            "New Job Opportunities",
            f"{count} new jobs you might be interested in",
            body,
            "Create Free Account & Apply",
            f"{DASH_URL}/register?ref=job_alert",
            "#10B981",
        ),
        text=_txt("New Job Opportunities", f"{count} new jobs posted. Sign up to apply: {DASH_URL}/register"),
    )


@_register(
    "weekly_careers_job_announcement",
    "Weekly Careers Job Announcement",
    "Jobs",
    "Weekly automated careers role announcement with apply CTA",
)
def build_weekly_careers_job_announcement_email(
    user_name: str = "there",
    job_title: str = "AI Career Growth Engineer",
    department: str = "AI Platform",
    location: str = "Remote",
    role_type: str = "Full-time",
    apply_url: str = "",
    careers_url: str = "",
) -> EmailTemplate:
    first_name = (user_name or "there").strip() or "there"
    safe_apply_url = _to_absolute_https(apply_url, f"{DASH_URL}/careers")
    safe_careers_url = _to_absolute_https(careers_url, f"{DASH_URL}/careers")

    body = f"""
    {_lead("New Weekly Careers Opening", f"Hi {first_name}, a new job has been added this week in Careers.")}
    {_alert_panel("Now Open", f"<strong>{job_title}</strong>", "#0EA5E9", "CAREERS")}
    <table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border:1px solid #E2E8F0;border-radius:12px;background:#F8FAFC;margin:0 0 16px;'>
      <tr>
        <td style='padding:16px 18px;'>
          <p class='em-title' style='margin:0 0 8px;color:#0F172A;font-size:15px;font-weight:700;'>{job_title}</p>
          <p class='em-text' style='margin:0 0 4px;color:#475569;font-size:13px;'><strong>Department:</strong> {department}</p>
          <p class='em-text' style='margin:0 0 4px;color:#475569;font-size:13px;'><strong>Location:</strong> {location}</p>
          <p class='em-text' style='margin:0;color:#475569;font-size:13px;'><strong>Type:</strong> {role_type}</p>
        </td>
      </tr>
    </table>
    <div class='em-callout' style='background:{_color_tint("#0EA5E9", 0x12)};border-left:3px solid #0EA5E9;border-radius:0 10px 10px 0;padding:14px 18px;margin:0 0 16px;font-size:13px;color:#334155;line-height:1.7;'>
      From the Welcome page, open <strong>Careers</strong> to view this job and apply.
    </div>
    <p style='margin:0 0 8px;font-size:13px;color:#334155;'>If this role is not the right fit, browse all open opportunities here:</p>
    <p style='margin:0;'><a href='{safe_careers_url}' style='color:#0EA5E9;font-size:13px;font-weight:700;text-decoration:none;'>Browse all careers roles &rarr;</a></p>
    """

    return EmailTemplate(
        subject=f"New career opening this week: {job_title} — Apply now",
        html=_wrap(
            "Careers Update",
            "A new role is now live in Careers",
            body,
            "View & Apply",
            safe_apply_url,
            "#0EA5E9",
        ),
        text=_txt(
            "Weekly Careers Job Announcement",
            f"Hi {first_name}, new job this week: {job_title} ({department}, {location}, {role_type}). Apply: {safe_apply_url}",
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# PRODUCTION-CRITICAL TEMPLATES (19 new — v7 enforced)
# ══════════════════════════════════════════════════════════════════════════


# ── P0-1. Referral Invite ────────────────────────────────

@_register("referral_invite", "Referral Invite", "Engagement", "Sent when a user shares a referral link with a friend")
def build_referral_invite_email(
    referrer_name: str = "Alex", referral_link: str = "", reward_description: str = "1 month free Premium"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">You've been invited!</p>
    <p style="margin:0 0 16px;">{referrer_name} thinks you'd love {BRAND} — an AI-powered career coaching platform that helps you grow faster.</p>
    {_alert_panel("Exclusive Reward", f"Sign up using this invite and both you and {referrer_name} get <strong>{reward_description}</strong>.", "#8B5CF6", "INVITE")}
    <p style="margin:16px 0 8px;">{_badge("REFERRAL BONUS", "#8B5CF6")} When you join, your reward is activated instantly.</p>"""
    return EmailTemplate(
        subject=f"{referrer_name} invited you to join {BRAND} — Get {reward_description}",
        html=_wrap("You're Invited", f"{referrer_name} invited you to {BRAND}", body, "Accept Invite", referral_link or f"{DASH_URL}/register", "#8B5CF6", category="engagement"),
        text=_txt("Referral Invite", f"{referrer_name} invited you to {BRAND}. Sign up: {referral_link}\nReward: {reward_description}"),
    )


# ── P0-2. Contact Form Confirmation ─────────────────────

@_register("contact_form_confirmation", "Contact Form Confirmation", "Support", "Sent when a user submits a contact form")
def build_contact_form_confirmation_email(
    user_name: str = "Alex", ticket_id: str = "CNT-0001", subject_line: str = "General Inquiry"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">We received your message, {user_name}</p>
    <p style="margin:0 0 16px;">Thank you for reaching out. Our team will review your inquiry and get back to you within 24 hours.</p>
    {_info_table([_info_row("Reference", ticket_id), _info_row("Subject", subject_line), _info_row("Response Time", "Within 24 hours")])}
    {_callout("You'll receive an email notification when our team responds. You can also track your inquiry from your dashboard.")}"""
    return EmailTemplate(
        subject=f"We received your message — Ref #{ticket_id}",
        html=_wrap("Message Received", "We'll get back to you within 24 hours", body, "Track My Inquiry", f"{DASH_URL}/my-tickets", category="support"),
        text=_txt("Contact Confirmation", f"Hi {user_name}, we received your message (Ref: {ticket_id}). We'll respond within 24 hours."),
    )









# ── AI Platform Integrity Report ─────────────────────────

@_register("integrity_cycle_report", "Integrity Cycle Report", "Communication", "AI Platform Integrity cycle report with score gauge and fix stats")
def build_integrity_cycle_report_email(
    status: str = "healthy",
    trigger: str = "scheduled",
    final_score: int = 95,
    platform_fixes: int = 0,
    domain_fixes: int = 0,
    ai_applied: int = 0,
    review_queue: int = 0,
) -> EmailTemplate:
    score_color = "#10B981" if final_score >= 90 else "#F59E0B" if final_score >= 70 else "#EF4444"
    status_color = {"healthy": "#10B981", "warning": "#F59E0B", "critical": "#EF4444"}.get(status, "#3B82F6")

    # Score gauge
    bar_pct = min(final_score, 100)
    gauge_html = f"""<div style="text-align:center;margin:20px 0;">
      <div style="display:inline-block;width:120px;height:120px;border-radius:60px;border:6px solid #E2E8F0;position:relative;background:conic-gradient({score_color} {bar_pct * 3.6}deg, #E2E8F0 0deg);">
        <div style="position:absolute;top:6px;left:6px;width:108px;height:108px;border-radius:54px;background:#FFFFFF;display:flex;align-items:center;justify-content:center;">
          <span style="font-size:32px;font-weight:900;color:{score_color};line-height:1;">{final_score}</span>
        </div>
      </div>
      <p style="color:#64748B;font-size:11px;font-weight:700;margin:8px 0 0;">PLATFORM SCORE</p>
    </div>"""

    # Stats cards
    total_fixes = platform_fixes + domain_fixes + ai_applied
    stats_html = f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:25%;padding:4px;">
        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;padding:12px 8px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Platform</p>
          <p style="color:#059669;font-size:20px;font-weight:800;margin:3px 0 0;">{platform_fixes}</p>
        </div>
      </td>
      <td style="width:25%;padding:4px;">
        <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:12px 8px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Domain</p>
          <p style="color:#2563EB;font-size:20px;font-weight:800;margin:3px 0 0;">{domain_fixes}</p>
        </div>
      </td>
      <td style="width:25%;padding:4px;">
        <div style="background:#F5F3FF;border:1px solid #DDD6FE;border-radius:10px;padding:12px 8px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">AI Fixes</p>
          <p style="color:#7C3AED;font-size:20px;font-weight:800;margin:3px 0 0;">{ai_applied}</p>
        </div>
      </td>
      <td style="width:25%;padding:4px;">
        <div style="background:#FFF7ED;border:1px solid #FED7AA;border-radius:10px;padding:12px 8px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Review Q</p>
          <p style="color:#EA580C;font-size:20px;font-weight:800;margin:3px 0 0;">{review_queue}</p>
        </div>
      </td>
    </tr></table>"""

    body = f"""{_alert_panel(f"Integrity Cycle: {status.upper()}", f"Trigger: {trigger}. Total fixes: {total_fixes}. Review queue: {review_queue}.", status_color, f"Integrity {status}")}
    {gauge_html}
    {stats_html}
    {_info_table([_info_row("Status", status.upper(), status_color), _info_row("Trigger", trigger), _info_row("Total Fixes", str(total_fixes), "#10B981"), _info_row("Review Queue", str(review_queue), "#EA580C" if review_queue > 0 else "#64748B")])}"""

    return EmailTemplate(
        subject=f"Integrity Cycle: {status.upper()} — Score {final_score}/100",
        html=_wrap("Integrity Report", f"Score {final_score}/100 — {status}", body, "Open Integrity Engine", f"{DASH_URL}/admin-console?category=operations&tab=ai-platform-integrity", status_color, category="communication"),
        text=_txt("Integrity Report", f"Status: {status}. Score: {final_score}/100. Platform: {platform_fixes}, Domain: {domain_fixes}, AI: {ai_applied}. Review queue: {review_queue}."),
    )


# ── Performance Guardian Alert ───────────────────────────

@_register("perf_guardian_alert", "Perf Guardian Alert", "Communication", "Performance guardian alert with color-coded metric cards")
def build_perf_guardian_alert_email(
    level: str = "WARNING",
    critical_count: int = 0,
    warning_count: int = 0,
    alerts: list = None,
    timestamp: str = "",
) -> EmailTemplate:
    accent = "#EF4444" if level == "CRITICAL" else "#F59E0B"

    # Metric cards
    cards_html = ""
    for a in (alerts or []):
        metric = a.get("metric", "")
        value = a.get("value", 0)
        unit = a.get("unit", "")
        thresh = a.get("threshold", 0)
        lvl = a.get("level", "warning")
        c = "#EF4444" if lvl == "critical" else "#F59E0B"
        bar_pct = min(int(value / max(thresh, 1) * 100), 150) if thresh else 50
        cards_html += f"""<tr><td style="padding-bottom:12px;">
          <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;border-left:4px solid {c};">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="vertical-align:top;">
                <span style="color:#0F172A;font-size:14px;font-weight:700;">{metric}</span>
                <span style="display:inline-block;background:{c}18;color:{c};font-size:9px;font-weight:800;padding:2px 8px;border-radius:8px;margin-left:8px;">{lvl.upper()}</span>
                <div style="margin-top:8px;">
                  <span style="color:{c};font-size:22px;font-weight:900;">{value}{unit}</span>
                  <span style="color:#94A3B8;font-size:12px;margin-left:8px;">threshold: {thresh}{unit}</span>
                </div>
                <div style="background:#E2E8F0;border-radius:3px;height:4px;margin-top:8px;overflow:hidden;">
                  <div style="background:{c};height:100%;width:{min(bar_pct, 100)}%;border-radius:3px;"></div>
                </div>
              </td>
            </tr></table>
          </div>
        </td></tr>"""

    body = f"""{_alert_panel(f"Performance {level}", f"{critical_count} critical and {warning_count} warning metrics detected{(' at ' + timestamp) if timestamp else ''}.", accent, level)}
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">{cards_html}</table>"""

    return EmailTemplate(
        subject=f"Performance {level}: {critical_count + warning_count} metric(s) degraded",
        html=_wrap("Performance Alert", f"{level}: {critical_count + warning_count} metrics", body, "View Performance", f"{DASH_URL}/admin-console?tab=performance", accent, category="communication"),
        text=_txt("Performance Alert", f"{level}: {critical_count} critical, {warning_count} warning metrics. {', '.join(a.get('metric','') for a in (alerts or [])[:5])}."),
    )


# ── Payment E2E Report ───────────────────────────────────

@_register("payment_e2e_report", "Payment E2E Report", "Billing", "Payment E2E check report with pass rate gauge and check results table")
def build_payment_e2e_report_email(
    report_id: str = "",
    severity: str = "low",
    passed: int = 0,
    total: int = 0,
    pass_rate: float = 100.0,
    failed_checks: list = None,
    is_immediate: bool = False,
    digest_type: str = "daily",
) -> EmailTemplate:
    rate_color = "#10B981" if pass_rate >= 95 else "#F59E0B" if pass_rate >= 80 else "#EF4444"
    accent = "#EF4444" if is_immediate else "#3B82F6"
    label = "ALERT" if is_immediate else digest_type.upper()

    # Pass rate gauge
    bar_pct = min(pass_rate, 100)
    gauge_html = f"""<div style="text-align:center;margin:20px 0;">
      <div style="display:inline-block;width:100px;height:100px;border-radius:50px;border:5px solid #E2E8F0;position:relative;background:conic-gradient({rate_color} {bar_pct * 3.6}deg, #E2E8F0 0deg);">
        <div style="position:absolute;top:5px;left:5px;width:90px;height:90px;border-radius:45px;background:#FFFFFF;display:flex;align-items:center;justify-content:center;">
          <span style="font-size:24px;font-weight:900;color:{rate_color};line-height:1;">{pass_rate:.0f}%</span>
        </div>
      </div>
      <p style="color:#64748B;font-size:11px;font-weight:700;margin:8px 0 0;">PASS RATE</p>
    </div>"""

    # Stats
    stats_html = f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin:12px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;padding:12px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Passed</p>
          <p style="color:#059669;font-size:22px;font-weight:800;margin:3px 0 0;">{passed}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;padding:12px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Failed</p>
          <p style="color:#DC2626;font-size:22px;font-weight:800;margin:3px 0 0;">{total - passed}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:12px;text-align:center;">
          <p style="color:#64748B;font-size:9px;margin:0;text-transform:uppercase;font-weight:700;">Total</p>
          <p style="color:#0F172A;font-size:22px;font-weight:800;margin:3px 0 0;">{total}</p>
        </div>
      </td>
    </tr></table>"""

    # Failed checks table
    checks_html = ""
    for c in (failed_checks or [])[:15]:
        checks_html += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#0F172A;font-weight:600;">{c.get("name","Check")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#64748B;">{c.get("detail","")[:80]}</td>
        </tr>"""
    checks_table = ""
    if checks_html:
        checks_table = f"""<h3 style="color:#0F172A;font-size:14px;font-weight:700;margin:16px 0 8px;">Failed Checks</h3>
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;">
          <thead><tr style="background:#F8FAFC;">
            <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;">Check</th>
            <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;">Detail</th>
          </tr></thead>
          <tbody>{checks_html}</tbody>
        </table>"""

    body = f"""{_alert_panel(f"Payment E2E {'Failure Alert' if is_immediate else 'Digest'}", f"Report {report_id}: {severity.upper()} severity. {passed}/{total} checks passed ({pass_rate:.1f}%).", accent, label)}
    {gauge_html}
    {stats_html}
    {checks_table}
    <p style="color:#64748B;font-size:11px;margin:16px 0 0;">Enterprise payment regression digest generated by the Payments E2E control center.</p>"""

    return EmailTemplate(
        subject=f"Payment E2E {label}: {pass_rate:.0f}% pass rate ({passed}/{total})",
        html=_wrap("Payment E2E", f"{label}: {pass_rate:.0f}% pass rate", body, "View Payment Dashboard", f"{DASH_URL}/admin-console?tab=payments", accent, category="billing"),
        text=_txt("Payment E2E", f"{label} — Report {report_id}: {passed}/{total} passed ({pass_rate:.1f}%). Severity: {severity}."),
    )


# ── Automation Alert (metric breach + recovery) ─────────

@_register("automation_alert", "Automation Alert", "Notifications", "Alert when a monitored metric breaches threshold, with auto-fix action")
def build_automation_alert_email(
    rule_name: str = "API Response Time",
    metric_name: str = "response_time_p95",
    current_value: str = "2500ms",
    condition: str = ">",
    threshold: str = "1000ms",
    action_taken: str = "Scaled up 2 replicas",
    is_recovery: bool = False,
    downtime: str = "",
    fix_applied: str = "",
) -> EmailTemplate:
    if is_recovery:
        accent = "#10B981"
        badge = "RECOVERED"
        intro = f"Service restored after {downtime}. {metric_name}={current_value}."
        if fix_applied:
            intro += f" Fix: {fix_applied}"
        rows = [_info_row("Rule", rule_name), _info_row("Metric", metric_name), _info_row("Current", current_value, "#10B981"), _info_row("Downtime", downtime, "#F59E0B")]
        if fix_applied:
            rows.append(_info_row("Fix Applied", fix_applied))
    else:
        accent = "#EF4444"
        badge = "BREACH"
        intro = f"{metric_name}={current_value} ({condition} {threshold}). Action: {action_taken}"
        rows = [_info_row("Rule", rule_name), _info_row("Metric", metric_name), _info_row("Current", current_value, "#EF4444"), _info_row("Threshold", f"{condition} {threshold}"), _info_row("Action", action_taken, "#F59E0B")]

    body = f"""{_alert_panel(f"{'RECOVERED: ' if is_recovery else ''}{rule_name}", intro, accent, badge)}
    {_info_table(rows)}"""
    prefix = "[RECOVERED]" if is_recovery else "[ALERT]"
    return EmailTemplate(
        subject=f"{prefix} {rule_name} — {metric_name}={current_value}",
        html=_wrap("Automation Alert", f"{rule_name}: {metric_name}={current_value}", body, "View Dashboard", f"{DASH_URL}/admin-console?tab=automation", accent, category="notifications"),
        text=_txt("Automation Alert", f"{prefix} {rule_name}. {intro}"),
    )


# ── CWV Degradation Alert ───────────────────────────────

@_register("cwv_degradation", "CWV Degradation", "Notifications", "Core Web Vitals degradation alert with metric breakdown table")
def build_cwv_degradation_email(
    degraded: list = None,
    sample_count: int = 0,
) -> EmailTemplate:
    metrics = degraded or []
    rows_html = ""
    for d in metrics:
        status_color = "#EF4444"
        rows_html += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#0F172A;font-weight:600;">{d.get("metric","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:{status_color};font-weight:700;">{d.get("value","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#64748B;">{d.get("threshold","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:{status_color};font-weight:600;">DEGRADED</td>
        </tr>"""

    body = f"""{_alert_panel("Core Web Vitals Degradation", f"{len(metrics)} metric(s) fell below Google's 'Good' threshold ({sample_count} samples).", "#EF4444", "CWV ALERT")}
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin:16px 0;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Metric</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Current</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Threshold</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Status</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="color:#64748B;font-size:12px;margin:8px 0 0;">Alert sent at most once every 6 hours.</p>"""
    return EmailTemplate(
        subject=f"CWV Alert: {len(metrics)} metric(s) degraded",
        html=_wrap("Web Vitals Alert", f"{len(metrics)} metrics below threshold", body, "View Web Vitals", f"{DASH_URL}/admin-console?tab=analytics", "#EF4444", category="notifications"),
        text=_txt("CWV Alert", f"{len(metrics)} metric(s) degraded: {', '.join(d.get('metric','') for d in metrics)}."),
    )


# ── i18n Quality Alert ───────────────────────────────────

@_register("i18n_quality_alert", "i18n Quality Alert", "Notifications", "Translation quality alert with language breakdown")
def build_i18n_quality_alert_email(
    below_threshold: list = None,
    threshold: int = 80,
    avg_score: float = 0,
) -> EmailTemplate:
    langs = below_threshold or []
    rows_html = ""
    for lang in langs:
        if isinstance(lang, dict):
            score = lang.get("score", 0)
            color = "#EF4444" if score < 50 else "#F59E0B" if score < threshold else "#10B981"
            rows_html += f"""<tr>
              <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#0F172A;">{lang.get("language","")}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:{color};font-weight:700;">{score}%</td>
              <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#64748B;">{threshold}%</td>
            </tr>"""
        elif isinstance(lang, str):
            rows_html += f'<tr><td colspan="3" style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#EF4444;">{lang}</td></tr>'

    body = f"""{_alert_panel("Translation Quality Alert", f"{len(langs)} language(s) below {threshold}% threshold. Average: {avg_score:.1f}%.", "#F59E0B", "i18n ALERT")}
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin:16px 0;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Language</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Score</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Threshold</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    return EmailTemplate(
        subject=f"i18n Alert: {len(langs)} language(s) below {threshold}% quality",
        html=_wrap("Translation Quality", f"{len(langs)} languages below threshold", body, "View i18n Dashboard", f"{DASH_URL}/admin-console?tab=i18n", "#F59E0B", category="notifications"),
        text=_txt("i18n Quality", f"{len(langs)} language(s) below {threshold}% threshold."),
    )


# ── Session Security Alert ───────────────────────────────

@_register("session_security_alert", "Session Security Alert", "Security", "High-risk session alert with flagged session details table")
def build_session_security_alert_email(
    sessions: list = None,
    scanned_sessions: int = 0,
    scanned_users: int = 0,
) -> EmailTemplate:
    flagged = sessions or []
    rows_html = ""
    for s in flagged[:10]:
        risk_color = "#EF4444" if s.get("risk_score", 0) >= 80 else "#F59E0B"
        rows_html += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#0F172A;">{s.get("user","unknown")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:{risk_color};font-weight:700;">{s.get("risk_score",0)}%</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#334155;">{s.get("activity","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#64748B;">{", ".join(s.get("flags",[])) if isinstance(s.get("flags"), list) else s.get("flags","")}</td>
        </tr>"""

    body = f"""{_alert_panel(f"{len(flagged)} High-Risk Session(s)", f"Scanned {scanned_sessions} sessions across {scanned_users} users.", "#EF4444", "SECURITY ALERT")}
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin:16px 0;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">User</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Risk</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Activity</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Flags</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    return EmailTemplate(
        subject=f"Security Alert: {len(flagged)} high-risk session(s) flagged",
        html=_wrap("Session Security", f"{len(flagged)} sessions flagged", body, "Review Sessions", f"{DASH_URL}/admin-console?tab=sessions", "#EF4444", category="security"),
        text=_txt("Session Security", f"{len(flagged)} high-risk session(s) flagged. Scanned {scanned_sessions} sessions across {scanned_users} users."),
    )


# ── ASO Keyword Alert ────────────────────────────────────

@_register("aso_keyword_alert", "ASO Keyword Alert", "Notifications", "ASO keyword ranking change alert with keyword table")
def build_aso_keyword_alert_email(
    changes: list = None,
    threshold: int = 5,
) -> EmailTemplate:
    kw_list = changes or []
    rows_html = ""
    for c in kw_list[:15]:
        delta = c.get("delta", 0)
        color = "#10B981" if delta > 0 else "#EF4444"
        arrow = "+" if delta > 0 else ""
        rows_html += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#0F172A;font-weight:600;">{c.get("keyword","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#64748B;">{c.get("old_rank","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#64748B;">{c.get("new_rank","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:{color};font-weight:700;">{arrow}{delta}</td>
        </tr>"""

    body = f"""{_alert_panel("ASO Keyword Ranking Changes", f"{len(kw_list)} keyword(s) changed beyond {threshold}-position threshold.", "#F59E0B", "ASO ALERT")}
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin:16px 0;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Keyword</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Old Rank</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">New Rank</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Change</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    return EmailTemplate(
        subject=f"ASO Alert: {len(kw_list)} keyword ranking change(s)",
        html=_wrap("ASO Keywords", f"{len(kw_list)} ranking changes detected", body, "View ASO Dashboard", f"{DASH_URL}/admin-console?tab=aso", "#F59E0B", category="notifications"),
        text=_txt("ASO Alert", f"{len(kw_list)} keyword ranking change(s) detected (threshold: {threshold})."),
    )


# ── Performance Auto-Fix Alert ───────────────────────────

@_register("perf_autofix_alert", "Perf Auto-Fix Alert", "Notifications", "Performance regression auto-fix alert with fix details")
def build_perf_autofix_alert_email(
    regression_count: int = 0,
    fix_count: int = 0,
    regressions: list = None,
) -> EmailTemplate:
    rows_html = ""
    for r in (regressions or [])[:10]:
        page = r.get("page", "unknown")
        fixes = r.get("fixes", [])
        rows_html += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#0F172A;">{page}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;color:#64748B;">{len(fixes)}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#334155;">{", ".join(fixes[:3])}</td>
        </tr>"""

    body = f"""{_alert_panel("Performance Auto-Fix Applied", f"Detected {regression_count} page regression(s). Applied {fix_count} auto-fixes.", "#F59E0B", "AUTO-FIX")}
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin:16px 0;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Page</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Fixes</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Applied</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    return EmailTemplate(
        subject=f"Auto-Fix: {fix_count} fixes applied across {regression_count} page(s)",
        html=_wrap("Performance Fix", f"{fix_count} fixes across {regression_count} pages", body, "View Performance", f"{DASH_URL}/admin-console?tab=performance", "#F59E0B", category="notifications"),
        text=_txt("Perf Auto-Fix", f"Detected {regression_count} regressions. Applied {fix_count} auto-fixes."),
    )



# ═══════════════════════════════════════════════════════════
# PRODUCTION-CRITICAL TEMPLATES (P0 / P1 / P2)
# ═══════════════════════════════════════════════════════════


# ── P0-1. Refund Notification ────────────────────────────

@_register("refund_notification", "Refund Notification", "Billing", "Sent when a payment refund is processed for the user")
def build_refund_notification_email(
    user_name: str = "Alex",
    amount: str = "$15.99",
    plan_name: str = "Premium",
    refund_reason: str = "Subscription cancellation",
    refund_id: str = "REF-001",
    original_date: str = "",
    processing_days: int = 5,
) -> EmailTemplate:
    body = f"""{_alert_panel("Refund Processed", f"A refund of <strong>{amount}</strong> has been issued to your original payment method.", "#10B981", "REFUNDED")}
    {_lead(f"Hi {user_name},", f"We have processed a refund for your {plan_name} subscription. The funds will appear in your account within {processing_days} business days.")}
    {_info_table([_info_row("Amount", amount, "#10B981"), _info_row("Plan", plan_name), _info_row("Reason", refund_reason), _info_row("Refund ID", refund_id, PRIMARY)])}
    {_callout(f"Please allow up to {processing_days} business days for the refund to appear on your statement. If you do not see it after this period, please contact your bank or reach out to our support team.")}"""
    return EmailTemplate(
        subject=f"Refund Processed: {amount} — {plan_name}",
        html=_wrap("Refund Processed", f"{amount} refund for {plan_name}", body, "View Payment History", f"{DASH_URL}/payment-history", "#10B981", category="billing"),
        text=_txt("Refund", f"Hi {user_name}, a refund of {amount} for {plan_name} has been processed (ID: {refund_id}). Allow {processing_days} days."),
    )


# ── P0-2. Payment Method Expiring ────────────────────────

@_register("payment_method_expiring", "Payment Method Expiring", "Billing", "Warning when a saved payment method is about to expire")
def build_payment_method_expiring_email(
    user_name: str = "Alex",
    card_last4: str = "4242",
    card_brand: str = "Visa",
    expiry_month: int = 3,
    expiry_year: int = 2026,
    days_until_expiry: int = 30,
) -> EmailTemplate:
    urgency = "URGENT" if days_until_expiry <= 7 else "REMINDER"
    accent = "#EF4444" if days_until_expiry <= 7 else "#F59E0B"
    body = f"""{_alert_panel("Payment Method Expiring", f"Your {card_brand} ending in {card_last4} expires in <strong>{days_until_expiry} days</strong>.", accent, urgency)}
    {_lead(f"Hi {user_name},", "Your payment method on file is about to expire. Please update it to avoid any interruption to your subscription.")}
    {_info_table([_info_row("Card", f"{card_brand} ****{card_last4}"), _info_row("Expires", f"{expiry_month:02d}/{expiry_year}", accent), _info_row("Days Remaining", str(days_until_expiry), accent)])}
    {_callout("Update your payment method now to ensure uninterrupted access to all features.")}"""
    return EmailTemplate(
        subject=f"{'URGENT: ' if days_until_expiry <= 7 else ''}Your {card_brand} ****{card_last4} expires in {days_until_expiry} days",
        html=_wrap("Card Expiring", f"{card_brand} ****{card_last4} expires soon", body, "Update Payment Method", f"{DASH_URL}/subscription/plans", accent, category="billing"),
        text=_txt("Card Expiring", f"Hi {user_name}, your {card_brand} ****{card_last4} expires {expiry_month:02d}/{expiry_year} ({days_until_expiry} days). Update now."),
    )


# ── P0-3. Terms / Privacy Policy Update ─────────────────

@_register("terms_policy_update", "Terms/Policy Update", "Communication", "Legal notice when Terms of Service or Privacy Policy changes")
def build_terms_policy_update_email(
    user_name: str = "Alex",
    policy_type: str = "Terms of Service",
    effective_date: str = "May 1, 2026",
    summary_of_changes: str = "Updated data retention policy and clarified third-party sharing provisions.",
    review_url: str = "",
    contact_email: str = "privacy@realaicoach.app",
) -> EmailTemplate:
    accent = "#2B6CB0"
    soft_panel = "#EBF4FF"
    muted_text = "#475569"
    cta = review_url or _platform_url("/privacy-policy" if policy_type == "Privacy Policy" else "/terms", "legal_update", "review_policy")
    manage_data_url = _platform_url("/privacy-request", "legal_update", "manage_data")
    body = f"""{_alert_panel(f"{policy_type} Updated", f"Changes take effect on <strong>{effective_date}</strong>.", accent, "LEGAL NOTICE")}
    {_lead(f"Hi {user_name},", f"We have refreshed our {policy_type} to make our privacy and legal commitments clearer, more transparent, and easier to act on.")}
    <div style="background:{soft_panel};border:1px solid #BEE3F8;border-radius:18px;padding:18px;margin:18px 0;">
      <p style="font-size:11px;font-weight:800;letter-spacing:.08em;color:{accent};text-transform:uppercase;margin:0 0 10px;">What changed</p>
      <p style="font-size:14px;color:#1E293B;line-height:1.75;margin:0;">{summary_of_changes}</p>
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;border-collapse:separate;border-spacing:0 10px;">
      <tr>
        <td style="width:50%;padding-right:6px;vertical-align:top;">
          <div style="background:#FFFFFF;border:1px solid #DBEAFE;border-radius:16px;padding:16px;height:100%;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:800;letter-spacing:.08em;color:{accent};text-transform:uppercase;">Document</p>
            <p style="margin:0;font-size:16px;font-weight:800;color:#0F172A;">{policy_type}</p>
          </div>
        </td>
        <td style="width:50%;padding-left:6px;vertical-align:top;">
          <div style="background:#FFFFFF;border:1px solid #DBEAFE;border-radius:16px;padding:16px;height:100%;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:800;letter-spacing:.08em;color:{accent};text-transform:uppercase;">Effective date</p>
            <p style="margin:0;font-size:16px;font-weight:800;color:#0F172A;">{effective_date}</p>
          </div>
        </td>
      </tr>
      <tr>
        <td style="width:50%;padding-right:6px;vertical-align:top;">
          <div style="background:#FFFFFF;border:1px solid #DBEAFE;border-radius:16px;padding:16px;height:100%;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:800;letter-spacing:.08em;color:{accent};text-transform:uppercase;">What this means</p>
            <p style="margin:0;font-size:13px;line-height:1.65;color:#334155;">Review the updated policy, understand your rights, and use the self-service privacy path if you want to export or delete your data.</p>
          </div>
        </td>
        <td style="width:50%;padding-left:6px;vertical-align:top;">
          <div style="background:#FFFFFF;border:1px solid #DBEAFE;border-radius:16px;padding:16px;height:100%;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:800;letter-spacing:.08em;color:{accent};text-transform:uppercase;">Need action?</p>
            <p style="margin:0;font-size:13px;line-height:1.65;color:#334155;">Open the Manage My Data portal to request export or deletion, or reply to this email for a privacy-team escalation.</p>
          </div>
        </td>
      </tr>
    </table>
    <p style="font-size:13px;color:{muted_text};line-height:1.7;margin:0 0 18px;">By continuing to use {BRAND} after {effective_date}, you agree to the updated {policy_type}. If you have questions or a data-subject request, email <a href="mailto:{contact_email}" style="color:{accent};font-weight:700;text-decoration:underline;">{contact_email}</a>. Our privacy operations team targets a first response within 72 hours.</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0;">
      <tr>
        <td align="left" style="padding:0 0 12px;">
          <a href="{cta}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:{accent};color:#FFFFFF;text-decoration:none;font-size:14px;font-weight:800;padding:12px 18px;border-radius:999px;">Review {policy_type}</a>
          <a href="{manage_data_url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-left:10px;background:#FFFFFF;border:1px solid #90CDF4;color:{accent};text-decoration:none;font-size:14px;font-weight:800;padding:12px 18px;border-radius:999px;">Manage My Data</a>
        </td>
      </tr>
    </table>"""
    return EmailTemplate(
        subject=f"Important: {policy_type} Updated — Effective {effective_date}",
        html=_wrap("Policy Update", f"{policy_type} changes effective {effective_date}", body, f"Review {policy_type}", cta, accent, category="v7_template"),
        text=_txt("Policy Update", f"Hi {user_name}, our {policy_type} has been updated effective {effective_date}. Changes: {summary_of_changes} Review: {cta} Manage data: {manage_data_url} Contact: {contact_email}"),
    )


# ── P0-3a. Cookie Notice Update ─────────────────────────────────────────
# Dedicated Cookie-scoped template — deliberately distinct visual identity
# from the Terms/Privacy update so recipients can tell at a glance what
# they're being asked to review. Uses an amber / biscuit accent, a
# cookie-category breakdown card (Essential / Functional / Analytics /
# Marketing), an explicit opt-out CTA, and routes all user questions to
# cookie@realaicoach.app.

@_register("cookie_notice_update", "Cookie Notice Update", "Communication", "Cookie policy change or new cookie category disclosure")
def build_cookie_notice_update_email(
    user_name: str = "Alex",
    effective_date: str = "May 1, 2026",
    summary_of_changes: str = "We added a new 'Analytics' cookie category and clarified retention windows for functional cookies.",
    essential_note: str = "Always active — required for login, security, and checkout.",
    functional_note: str = "Remembers your preferences (language, theme, timezone). 12 months.",
    analytics_note: str = "Aggregated, non-identifying usage metrics. 24 months. Opt-out any time.",
    marketing_note: str = "Off by default. Only enabled if you explicitly opt in.",
    preferences_url: str = "",
    contact_email: str = "cookie@realaicoach.app",
) -> EmailTemplate:
    # Amber/biscuit palette chosen to distinguish from the blue Legal/Terms
    # template. The circular biscuit hero dot + category breakdown grid is
    # the visual signature.
    amber = "#D97706"
    amber_soft = "#FEF3C7"
    amber_bg = "#FFFBEB"
    _row_style = (
        "display:table;width:100%;border-collapse:collapse;margin:0 0 10px;"
        "border-radius:10px;overflow:hidden;border:1px solid #FDE68A;"
    )
    def _cat(label: str, note: str, status: str, status_color: str) -> str:
        return f"""
        <div style="{_row_style}">
          <div style="display:table-row;">
            <div style="display:table-cell;width:32%;padding:12px 14px;background:{amber_soft};vertical-align:middle;">
              <p style="margin:0;font-size:12px;font-weight:800;color:{amber};text-transform:uppercase;letter-spacing:.04em;">{label}</p>
              <p style="margin:4px 0 0;font-size:10px;font-weight:700;color:{status_color};text-transform:uppercase;">{status}</p>
            </div>
            <div style="display:table-cell;padding:12px 14px;background:#FFFFFF;vertical-align:middle;">
              <p style="margin:0;font-size:13px;color:#334155;line-height:1.55;">{note}</p>
            </div>
          </div>
        </div>"""

    hero = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:{amber_bg};border:1px solid #FDE68A;border-radius:14px;padding:18px 18px 14px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="width:48px;vertical-align:top;">
                <div style="width:44px;height:44px;border-radius:22px;background:{amber};color:#FFFFFF;text-align:center;line-height:44px;font-size:22px;font-weight:800;">🍪</div>
              </td>
              <td style="vertical-align:middle;padding-left:12px;">
                <p style="margin:0;font-size:11px;font-weight:800;letter-spacing:.06em;color:{amber};text-transform:uppercase;">Cookie Notice</p>
                <p style="margin:4px 0 0;font-size:17px;font-weight:800;color:#78350F;">Our cookie policy has changed</p>
                <p style="margin:4px 0 0;font-size:13px;color:#92400E;">Effective <strong>{effective_date}</strong></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>"""

    body = f"""{hero}
    {_lead(f"Hi {user_name},", "We are updating our Cookie Notice. Here is exactly what changes — and how you can control every category we set on your device.")}
    <div style="background:#F8FAFC;border-left:4px solid {amber};border-radius:0 10px 10px 0;padding:14px 16px;margin:0 0 18px;">
      <p style="font-size:12px;font-weight:700;color:{amber};text-transform:uppercase;margin:0 0 6px;letter-spacing:.03em;">What's changing</p>
      <p style="font-size:14px;color:#334155;line-height:1.65;margin:0;">{summary_of_changes}</p>
    </div>

    <p style="font-size:13px;font-weight:800;color:#78350F;text-transform:uppercase;letter-spacing:.04em;margin:20px 0 10px;">Cookie categories</p>
    {_cat("Essential", essential_note, "Required", "#047857")}
    {_cat("Functional", functional_note, "On by default", amber)}
    {_cat("Analytics", analytics_note, "Opt-out anytime", "#2563EB")}
    {_cat("Marketing", marketing_note, "Off unless opted in", "#64748B")}

    <p style="font-size:13px;color:#64748B;margin:20px 0 0;line-height:1.6;">Use the <strong>Cookie Preferences</strong> button below to toggle each category. Questions about a specific cookie or our retention windows? Email <a href="mailto:{contact_email}" style="color:{amber};font-weight:700;text-decoration:underline;">{contact_email}</a> — our Cookie Compliance team owns that inbox and responds within 48 hours.</p>"""

    cta = preferences_url or f"{DASH_URL}/cookies"
    return EmailTemplate(
        subject=f"Your Cookie Preferences — Policy Update Effective {effective_date}",
        html=_wrap("Cookie Notice", f"Cookie policy update effective {effective_date}", body, "Manage Cookie Preferences", cta, amber, category="communication"),
        text=_txt(
            "Cookie Notice Update",
            f"Hi {user_name}, our Cookie Notice has been updated, effective {effective_date}. "
            f"What changed: {summary_of_changes} "
            f"Essential: {essential_note} "
            f"Functional: {functional_note} "
            f"Analytics: {analytics_note} "
            f"Marketing: {marketing_note} "
            f"Manage preferences: {cta} — Contact: {contact_email}"
        ),
    )


# ── P0-3b. Security Incident Notice (breach / cyberattack) ─────────────────
# Regulatory-grade notification template. Tone is calm + direct; structure
# mirrors GDPR Art. 34 / CCPA §1798.82 disclosure expectations so the raw
# email itself is defensible evidence in a post-incident investigation.

@_register("security_incident_notice", "Security Incident Notice", "Security", "Breach / cyberattack notification to affected users")
def build_security_incident_notice_email(
    user_name: str = "Alex",
    incident_type: str = "Data Breach",
    severity: str = "high",
    incident_date: str = "April 20, 2026",
    discovered_date: str = "April 21, 2026",
    what_happened: str = "On the dates above, we detected unauthorized access to a subset of our user authentication database.",
    data_affected: str = "Email addresses and hashed (bcrypt) passwords.",
    user_action_required: str = "Please reset your password immediately and enable two-factor authentication.",
    remediation_steps: str = "We have rotated all affected credentials, closed the access vector, and engaged an independent security firm.",
    contact_email: str = "security@realaicoach.app",
    action_url: str = "",
) -> EmailTemplate:
    # Colour the alert banner by severity so the visual cue matches the
    # written severity claim (regulators look for this kind of alignment).
    sev_color_map = {
        "critical": "#991B1B",
        "high": "#DC2626",
        "medium": "#F59E0B",
        "informational": "#3B82F6",
    }
    sev_norm = (severity or "high").lower()
    color = sev_color_map.get(sev_norm, "#DC2626")
    badge = f"SECURITY NOTICE · {sev_norm.upper()}"

    body = f"""{_alert_panel(f"{incident_type} — Action May Be Required", f"Discovered on <strong>{discovered_date}</strong>. We are contacting you directly as required by our incident-response policy.", color, badge)}
    {_lead(f"Hi {user_name},", "We are writing to inform you about a security incident that may have affected your account. We believe transparency is critical, and we are sharing what we know right now — not after the investigation concludes.")}
    <div style="background:#FEF2F2;border-left:4px solid {color};border-radius:0 10px 10px 0;padding:16px;margin:16px 0;">
      <p style="font-size:12px;font-weight:700;color:{color};text-transform:uppercase;margin:0 0 8px;">What Happened</p>
      <p style="font-size:14px;color:#334155;line-height:1.7;margin:0;">{what_happened}</p>
    </div>
    <div style="background:#FFFBEB;border-left:4px solid #F59E0B;border-radius:0 10px 10px 0;padding:16px;margin:16px 0;">
      <p style="font-size:12px;font-weight:700;color:#B45309;text-transform:uppercase;margin:0 0 8px;">Data Potentially Affected</p>
      <p style="font-size:14px;color:#334155;line-height:1.7;margin:0;">{data_affected}</p>
    </div>
    <div style="background:#F0FDF4;border-left:4px solid #10B981;border-radius:0 10px 10px 0;padding:16px;margin:16px 0;">
      <p style="font-size:12px;font-weight:700;color:#065F46;text-transform:uppercase;margin:0 0 8px;">What We Are Doing</p>
      <p style="font-size:14px;color:#334155;line-height:1.7;margin:0;">{remediation_steps}</p>
    </div>
    <div style="background:#EFF6FF;border-left:4px solid #2563EB;border-radius:0 10px 10px 0;padding:16px;margin:16px 0;">
      <p style="font-size:12px;font-weight:700;color:#1E40AF;text-transform:uppercase;margin:0 0 8px;">What You Should Do Now</p>
      <p style="font-size:14px;color:#334155;line-height:1.7;margin:0;">{user_action_required}</p>
    </div>
    {_info_table([
        _info_row("Incident Type", incident_type, color),
        _info_row("Severity", sev_norm.title(), color),
        _info_row("Incident Date", incident_date),
        _info_row("Discovered", discovered_date),
    ])}
    <p style="font-size:13px;color:#64748B;margin:16px 0 0;">If you have any questions or believe your account has been misused, please email <a href="mailto:{contact_email}" style="color:{color};font-weight:700;">{contact_email}</a>. We will respond within 24 hours.</p>
    <p style="font-size:12px;color:#94A3B8;margin:12px 0 0;font-style:italic;">This email is a mandatory security notification. We will never ask for your password or payment information in an email.</p>"""
    cta = action_url or f"{DASH_URL}/account/security"
    return EmailTemplate(
        subject=f"Important Security Notice — {incident_type} ({sev_norm.title()})",
        html=_wrap("Security Notice", f"{incident_type} — {sev_norm.title()} severity", body, "Secure My Account", cta, color, category="security"),
        text=_txt(
            "Security Notice",
            f"Hi {user_name}, we are notifying you of a {sev_norm} severity {incident_type.lower()} discovered on {discovered_date}. "
            f"Data potentially affected: {data_affected} What happened: {what_happened} "
            f"Action required: {user_action_required} What we've done: {remediation_steps} Questions: {contact_email}",
        ),
    )


# ── P0-4. MFA Enabled ───────────────────────────────────

@_register("mfa_enabled", "MFA Enabled", "Security", "Confirmation when two-factor authentication is enabled")
def build_mfa_enabled_email(
    user_name: str = "Alex",
    method: str = "Authenticator App",
    enabled_at: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Two-Factor Authentication Enabled", "Your account is now protected with an additional layer of security.", "#10B981", "2FA ACTIVE")}
    {_lead(f"Hi {user_name},", "Two-factor authentication has been successfully enabled on your account. You will now need to provide a verification code in addition to your password when signing in.")}
    {_info_table([_info_row("Method", method, "#10B981"), _info_row("Status", "Enabled", "#10B981")])}
    {_callout("Keep your backup codes in a safe place. If you lose access to your authenticator, backup codes are the only way to recover your account.")}
    <p style="font-size:12px;color:#EF4444;margin:16px 0 0;">If you did not enable 2FA, your account may be compromised. Change your password immediately and contact support.</p>"""
    return EmailTemplate(
        subject=f"2FA Enabled — Your {BRAND} account is now more secure",
        html=_wrap("2FA Enabled", "Two-factor authentication is active", body, "View Security Settings", f"{DASH_URL}/settings?tab=security", "#10B981", category="security"),
        text=_txt("2FA Enabled", f"Hi {user_name}, 2FA has been enabled on your account using {method}. Keep your backup codes safe."),
    )


# ── P0-5. MFA Disabled ──────────────────────────────────

@_register("mfa_disabled", "MFA Disabled", "Security", "Alert when two-factor authentication is disabled")
def build_mfa_disabled_email(
    user_name: str = "Alex",
    disabled_at: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Two-Factor Authentication Disabled", "Your account is no longer protected by 2FA.", "#EF4444", "2FA REMOVED")}
    {_lead(f"Hi {user_name},", "Two-factor authentication has been disabled on your account. Your account is now less secure.")}
    {_info_table([_info_row("Status", "Disabled", "#EF4444"), _info_row("Previous", "Enabled", "#10B981")])}
    <p style="font-size:13px;color:#EF4444;font-weight:600;margin:16px 0 0;">If you did not disable 2FA, your account may be compromised. Re-enable 2FA and change your password immediately.</p>"""
    return EmailTemplate(
        subject=f"Security Alert: 2FA Disabled on your {BRAND} account",
        html=_wrap("2FA Disabled", "Two-factor authentication removed", body, "Re-enable 2FA", f"{DASH_URL}/settings?tab=security", "#EF4444", category="security"),
        text=_txt("2FA Disabled", f"Hi {user_name}, 2FA has been disabled. If this was not you, re-enable it immediately."),
    )


# ── P0-6. Invoice Past Due (Dunning) ────────────────────

@_register("invoice_past_due", "Invoice Past Due", "Billing", "Escalating dunning notice for overdue invoices")
def build_invoice_past_due_email(
    user_name: str = "Alex",
    amount: str = "$15.99",
    plan_name: str = "Premium",
    days_overdue: int = 3,
    grace_period_ends: str = "",
    update_url: str = "",
) -> EmailTemplate:
    if days_overdue >= 14:
        accent, badge, urgency_text = "#EF4444", "FINAL NOTICE", "This is your final notice. Your account will be downgraded if payment is not received."
    elif days_overdue >= 7:
        accent, badge, urgency_text = "#EF4444", "URGENT", "Your subscription is at risk of being suspended."
    else:
        accent, badge, urgency_text = "#F59E0B", "PAST DUE", "Please update your payment method to continue your subscription."
    body = f"""{_alert_panel(f"Invoice Past Due — {days_overdue} Days", urgency_text, accent, badge)}
    {_lead(f"Hi {user_name},", f"Your {plan_name} subscription payment of <strong>{amount}</strong> is <strong>{days_overdue} days overdue</strong>.")}
    {_info_table([_info_row("Amount Due", amount, accent), _info_row("Plan", plan_name), _info_row("Days Overdue", str(days_overdue), accent)])}"""
    if grace_period_ends:
        body += f'<p style="font-size:13px;color:#EF4444;font-weight:600;margin:12px 0;">Grace period ends: {grace_period_ends}</p>'
    body += _callout("Update your payment method now to avoid service interruption and retain access to all premium features.")
    cta = update_url or f"{DASH_URL}/subscription/plans"
    return EmailTemplate(
        subject=f"{'FINAL NOTICE: ' if days_overdue >= 14 else 'URGENT: ' if days_overdue >= 7 else ''}Payment overdue ({days_overdue} days) — {amount}",
        html=_wrap("Payment Overdue", f"{amount} overdue by {days_overdue} days", body, "Update Payment Now", cta, accent, category="billing"),
        text=_txt("Past Due", f"Hi {user_name}, your {plan_name} payment of {amount} is {days_overdue} days overdue. Update your payment method."),
    )


# ── P1-1. Payment Method Updated ────────────────────────

@_register("payment_method_updated", "Payment Method Updated", "Billing", "Confirmation when a user updates their payment method")
def build_payment_method_updated_email(
    user_name: str = "Alex",
    card_last4: str = "4242",
    card_brand: str = "Visa",
    updated_at: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Payment Method Updated", "Your billing information has been successfully updated.", "#10B981", "CONFIRMED")}
    {_lead(f"Hi {user_name},", "Your payment method on file has been updated. All future charges will be applied to the new payment method.")}
    {_info_table([_info_row("New Card", f"{card_brand} ****{card_last4}", "#10B981"), _info_row("Status", "Active", "#10B981")])}
    <p style="font-size:12px;color:#EF4444;margin:16px 0 0;">If you did not make this change, please contact support immediately.</p>"""
    return EmailTemplate(
        subject=f"Payment Method Updated — {card_brand} ****{card_last4}",
        html=_wrap("Billing Updated", "Payment method changed successfully", body, "View Billing", f"{DASH_URL}/subscription/plans", "#10B981", category="billing"),
        text=_txt("Payment Updated", f"Hi {user_name}, your payment method has been updated to {card_brand} ****{card_last4}."),
    )


# ── P1-2. Employer Suspended ────────────────────────────

@_register("employer_suspended", "Employer Suspended", "Employer", "Notification when an employer account is suspended")
def build_employer_suspended_email(
    employer_name: str = "Acme Corp",
    reason: str = "Policy violation review",
    suspended_at: str = "",
    appeal_url: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Account Suspended", "Your employer account has been temporarily suspended pending review.", "#EF4444", "SUSPENDED")}
    {_lead(f"Hi {employer_name},", "We have temporarily suspended your employer account. During this time, your job listings and interview scheduling features will be unavailable.")}
    {_info_table([_info_row("Status", "Suspended", "#EF4444"), _info_row("Reason", reason)])}
    {_callout("If you believe this was a mistake, please submit an appeal or contact our support team.")}"""
    cta = appeal_url or f"{DASH_URL}/support"
    return EmailTemplate(
        subject=f"Account Suspended — {employer_name}",
        html=_wrap("Account Suspended", "Employer account suspended", body, "Submit an Appeal", cta, "#EF4444", category="employer"),
        text=_txt("Account Suspended", f"{employer_name}, your employer account has been suspended. Reason: {reason}. Contact support to appeal."),
    )


# ── P1-3. Interview Reminder ────────────────────────────

@_register("interview_reminder", "Interview Reminder", "Employer", "Upcoming interview reminder with prep tips")
def build_interview_reminder_email(
    candidate_name: str = "Alex",
    job_title: str = "Software Engineer",
    interviewer_name: str = "Sarah",
    interview_time: str = "10:00 AM",
    interview_date: str = "April 20, 2026",
    minutes_until: int = 60,
    prep_tips: list = None,
) -> EmailTemplate:
    if minutes_until <= 15:
        accent, badge = "#EF4444", "STARTING SOON"
    elif minutes_until <= 60:
        accent, badge = "#F59E0B", "1 HOUR"
    else:
        accent, badge = "#3B82F6", "TOMORROW"

    tips = prep_tips or ["Review the job description and company values", "Prepare 2-3 questions to ask the interviewer", "Test your camera and microphone if virtual", "Have a copy of your resume nearby"]
    tips_html = "".join(f'<li style="color:#475569;font-size:13px;line-height:1.8;margin-bottom:2px;">{t}</li>' for t in tips)

    body = f"""{_alert_panel(f"Interview {badge}", f"Your interview for <strong>{job_title}</strong> is coming up.", accent, badge)}
    {_lead(f"Hi {candidate_name},", "This is a reminder about your upcoming interview.")}
    {_info_table([_info_row("Position", job_title), _info_row("Interviewer", interviewer_name), _info_row("Date", interview_date), _info_row("Time", interview_time, accent)])}
    <h3 style="color:#0F172A;font-size:14px;font-weight:700;margin:16px 0 8px;">Quick Prep Tips</h3>
    <ul style="padding-left:18px;margin:0;">{tips_html}</ul>"""
    return EmailTemplate(
        subject=f"Interview {'Starting Soon' if minutes_until <= 15 else 'in 1 Hour' if minutes_until <= 60 else 'Tomorrow'}: {job_title}",
        html=_wrap("Interview Reminder", f"{job_title} — {interview_date} at {interview_time}", body, "View Interview Details", f"{DASH_URL}/interviews", accent, category="employer"),
        text=_txt("Interview Reminder", f"Hi {candidate_name}, interview for {job_title} with {interviewer_name} on {interview_date} at {interview_time}."),
    )


# ── P1-4. Platform Announcement ─────────────────────────

@_register("platform_announcement", "Platform Announcement", "Communication", "Admin broadcast for major platform updates or maintenance")
def build_platform_announcement_email(
    user_name: str = "Alex",
    title: str = "Platform Update",
    message: str = "We have exciting news to share.",
    category_label: str = "announcement",
    cta_label: str = "",
    cta_url: str = "",
) -> EmailTemplate:
    cat_colors = {"announcement": "#3B82F6", "maintenance": "#F59E0B", "feature": "#8B5CF6", "security": "#EF4444", "celebration": "#10B981"}
    accent = cat_colors.get(category_label.lower(), "#3B82F6")
    body = f"""{_alert_panel(title, category_label.upper(), accent, category_label.upper())}
    {_lead(f"Hi {user_name},", message)}"""
    cta_link = cta_url or f"{DASH_URL}"
    cta_text = cta_label or "Open Platform"
    return EmailTemplate(
        subject=f"[{BRAND}] {title}",
        html=_wrap("Announcement", title, body, cta_text, cta_link, accent, category="communication"),
        text=_txt("Announcement", f"Hi {user_name}, {title}: {message}"),
    )


# ── P1-5. Welcome Back ──────────────────────────────────

@_register("welcome_back", "Welcome Back", "Engagement", "Re-engagement email for users returning after inactivity")
def build_welcome_back_email(
    user_name: str = "Alex",
    days_away: int = 30,
    new_features: list = None,
) -> EmailTemplate:
    first = user_name.strip().split()[0] if user_name.strip() else "there"
    feat_html = ""
    for f in (new_features or ["Enhanced AI coaching", "New Learning Hub courses", "Improved dashboard analytics"]):
        feat_html += f"""<tr><td style="padding-bottom:10px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:28px;height:28px;background:#10B98112;border-radius:8px;text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:14px;">&#10003;</span></td>
            <td style="padding-left:10px;font-size:13px;color:#334155;">{f}</td>
          </tr></table>
        </td></tr>"""
    body = f"""{_alert_panel(f"Welcome Back, {first}!", f"We missed you! A lot has happened in {days_away} days.", "#8B5CF6", "WELCOME BACK")}
    {_lead(f"Hi {first},", f"It has been {days_away} days since your last visit. We have been busy making {BRAND} even better for you.")}
    <h3 style="color:#0F172A;font-size:14px;font-weight:700;margin:16px 0 10px;">What You Missed</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{feat_html}</table>"""
    return EmailTemplate(
        subject=f"Welcome Back, {first} — See What's New at {BRAND}",
        html=_wrap("Welcome Back", f"We missed you, {first}!", body, "Jump Back In", f"{DASH_URL}/auth/login", "#8B5CF6", category="engagement"),
        text=_txt("Welcome Back", f"Hi {first}, it has been {days_away} days. New features: {', '.join(new_features or ['AI coaching updates'])}."),
    )


# ── P2-1. Goal Completed ────────────────────────────────

@_register("goal_completed", "Goal Completed", "Engagement", "Celebration email when a user completes an AI goal")
def build_goal_completed_email(
    user_name: str = "Alex",
    goal_title: str = "Complete 30 coaching sessions",
    completed_at: str = "",
    next_suggestion: str = "",
) -> EmailTemplate:
    first = user_name.strip().split()[0] if user_name.strip() else "there"
    body = f"""{_alert_panel("Goal Achieved!", f"You completed: <strong>{goal_title}</strong>", "#10B981", "COMPLETED")}
    <div style="text-align:center;margin:20px 0;">
      <div style="display:inline-block;width:80px;height:80px;border-radius:40px;background:linear-gradient(135deg,#10B981,#059669);text-align:center;line-height:80px;">
        <span style="font-size:36px;color:#FFF;">&#10003;</span>
      </div>
    </div>
    {_lead(f"Congratulations, {first}!", "You have successfully completed your goal. This is a significant achievement and a testament to your dedication.")}
    {_info_table([_info_row("Goal", goal_title, "#10B981"), _info_row("Status", "Completed", "#10B981")])}"""
    if next_suggestion:
        body += _callout(f"Ready for your next challenge? We suggest: {next_suggestion}")
    return EmailTemplate(
        subject=f"Goal Achieved: {goal_title}",
        html=_wrap("Goal Achieved", f"Completed: {goal_title}", body, "Set Next Goal", f"{DASH_URL}/goals", "#10B981", category="engagement"),
        text=_txt("Goal Achieved", f"Congratulations {first}! You completed: {goal_title}."),
    )


# ── P2-2. Coaching Session Recap ─────────────────────────

@_register("coaching_session_recap", "Coaching Session Recap", "Engagement", "Summary email after an AI coaching session")
def build_coaching_session_recap_email(
    user_name: str = "Alex",
    session_topic: str = "Career Planning",
    key_takeaways: list = None,
    action_items: list = None,
    session_duration: str = "15 min",
    next_session_url: str = "",
) -> EmailTemplate:
    first = user_name.strip().split()[0] if user_name.strip() else "there"
    takeaways = key_takeaways or ["Identified key strengths and areas for growth", "Discussed actionable next steps"]
    actions = action_items or ["Review session notes", "Practice key techniques discussed"]
    tk_html = "".join(f'<li style="color:#334155;font-size:13px;line-height:1.8;margin-bottom:2px;">{t}</li>' for t in takeaways)
    act_html = "".join(f'<li style="color:#334155;font-size:13px;line-height:1.8;margin-bottom:2px;">{a}</li>' for a in actions)
    body = f"""{_alert_panel("Session Complete", f"Your coaching session on <strong>{session_topic}</strong> is complete.", "#8B5CF6", "RECAP")}
    {_info_table([_info_row("Topic", session_topic, "#8B5CF6"), _info_row("Duration", session_duration)])}
    <h3 style="color:#0F172A;font-size:14px;font-weight:700;margin:16px 0 8px;">Key Takeaways</h3>
    <ul style="padding-left:18px;margin:0 0 16px;">{tk_html}</ul>
    <h3 style="color:#0F172A;font-size:14px;font-weight:700;margin:0 0 8px;">Action Items</h3>
    <ul style="padding-left:18px;margin:0;">{act_html}</ul>"""
    cta = next_session_url or f"{DASH_URL}/coaching"
    return EmailTemplate(
        subject=f"Session Recap: {session_topic}",
        html=_wrap("Session Recap", f"{session_topic} — {session_duration}", body, "Start Next Session", cta, "#8B5CF6", category="engagement"),
        text=_txt("Session Recap", f"Hi {first}, your {session_topic} session recap. Takeaways: {'; '.join(takeaways)}."),
    )


# ── P2-3. CSAT Thank You ────────────────────────────────

@_register("csat_thank_you", "CSAT Thank You", "Engagement", "Acknowledgment after completing a satisfaction survey")
def build_csat_thank_you_email(
    user_name: str = "Alex",
    rating: str = "positive",
) -> EmailTemplate:
    first = user_name.strip().split()[0] if user_name.strip() else "there"
    body = f"""{_alert_panel("Thank You for Your Feedback", "Your response has been recorded and will help us improve.", "#10B981", "RECEIVED")}
    {_lead(f"Thank you, {first}!", f"We appreciate you taking the time to share your experience with {BRAND}. Every piece of feedback helps us build a better product.")}
    {_callout("Your feedback is reviewed by our team and directly influences our product roadmap. Thank you for being part of our community!")}"""
    return EmailTemplate(
        subject=f"Thank You for Your Feedback — {BRAND}",
        html=_wrap("Feedback Received", "Your feedback matters", body, "Explore New Features", f"{DASH_URL}", "#10B981", category="engagement"),
        text=_txt("Feedback Thanks", f"Thank you {first} for your feedback! Your response helps us improve {BRAND}."),
    )


# ── P2-4. Data Export Ready ──────────────────────────────

@_register("data_export_ready", "Data Export Ready", "Communication", "Notification when a requested data export file is ready for download")
def build_data_export_ready_email(
    user_name: str = "Alex",
    export_type: str = "Account Data",
    file_format: str = "CSV",
    download_url: str = "",
    expires_in: str = "7 days",
) -> EmailTemplate:
    body = f"""{_alert_panel("Your Export Is Ready", f"Your <strong>{export_type}</strong> export ({file_format}) is ready for download.", "#3B82F6", "READY")}
    {_lead(f"Hi {user_name},", "The data export you requested is now available.")}
    {_info_table([_info_row("Export Type", export_type), _info_row("Format", file_format, "#3B82F6"), _info_row("Expires In", expires_in, "#F59E0B")])}
    {_callout(f"This download link will expire in {expires_in}. Please download your file before then.")}"""
    cta = download_url or f"{DASH_URL}/settings?tab=data"
    return EmailTemplate(
        subject=f"Your {export_type} Export Is Ready — Download Now",
        html=_wrap("Export Ready", f"{export_type} ({file_format}) available", body, "Download Now", cta, "#3B82F6", category="communication"),
        text=_txt("Export Ready", f"Hi {user_name}, your {export_type} export ({file_format}) is ready. Expires in {expires_in}."),
    )


# ── P2-5. Admin Account Action ───────────────────────────

@_register("admin_account_action", "Admin Account Action", "Security", "User notification when an admin performs an action on their account")
def build_admin_account_action_email(
    user_name: str = "Alex",
    action: str = "role change",
    action_details: str = "Your account role has been updated.",
    performed_by: str = "Platform Admin",
) -> EmailTemplate:
    action_colors = {"role change": "#3B82F6", "password reset": "#F59E0B", "account restore": "#10B981", "account suspend": "#EF4444", "data modification": "#8B5CF6"}
    accent = action_colors.get(action.lower(), "#3B82F6")
    body = f"""{_alert_panel(f"Account Action: {action.title()}", action_details, accent, "ADMIN ACTION")}
    {_lead(f"Hi {user_name},", "An administrator has performed an action on your account.")}
    {_info_table([_info_row("Action", action.title(), accent), _info_row("Performed By", performed_by)])}
    <p style="font-size:12px;color:#EF4444;margin:16px 0 0;">If you did not expect this change, please contact support immediately.</p>"""
    return EmailTemplate(
        subject=f"Admin Action on Your Account: {action.title()}",
        html=_wrap("Account Action", f"Admin: {action.title()}", body, "View Account Settings", f"{DASH_URL}/settings", accent, category="security"),
        text=_txt("Account Action", f"Hi {user_name}, an admin ({performed_by}) performed: {action}. Details: {action_details}"),
    )


# ── Referral Weekly Digest ───────────────────────────────

@_register("referral_digest", "Referral Digest", "Engagement", "Weekly referral stats digest with tier, rank, earnings, and commission structure")
def build_referral_digest_email(
    user_name: str = "Alex",
    rank: int = 1,
    total_refs: int = 0,
    active_subs: int = 0,
    total_earnings: float = 0.0,
    code: str = "REF-ABC123",
    tier_name: str = "Silver",
    tier_color: str = "#64748B",
    commission_pct: int = 10,
    basic_commission: float = 0.60,
    premium_commission: float = 1.60,
    next_tier_name: str = "Gold",
) -> EmailTemplate:
    body = f"""{_alert_panel(f"Referral Digest — {tier_name} Tier", f"Rank #{rank} this week. Keep sharing to climb higher!", tier_color, f"RANK #{rank}")}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;border-left:3px solid #2563EB;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Referrals</p>
          <p style="color:#0F172A;font-size:26px;font-weight:800;margin:4px 0 0;">{total_refs}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;border-left:3px solid #059669;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Active Subs</p>
          <p style="color:#0F172A;font-size:26px;font-weight:800;margin:4px 0 0;">{active_subs}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;border-left:3px solid #8B5CF6;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Earned</p>
          <p style="color:#0F172A;font-size:26px;font-weight:800;margin:4px 0 0;">${total_earnings:.2f}</p>
        </div>
      </td>
    </tr></table>

    <div style="background:#F1F5F9;border-radius:10px;padding:16px;border:1px solid #E2E8F0;margin:12px 0;">
      <p style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 6px;">Your Referral Code</p>
      <p style="color:#2563EB;font-size:20px;font-weight:800;letter-spacing:2px;margin:0;">{code}</p>
    </div>

    {_info_table([_info_row("Tier", f"{tier_name} ({commission_pct}%)", tier_color), _info_row("Basic Plan Commission", f"${basic_commission:.2f}/mo per referral", "#059669"), _info_row("Premium Plan Commission", f"${premium_commission:.2f}/mo per referral", "#8B5CF6")])}

    <p style="color:#64748B;font-size:12px;text-align:center;margin:16px 0 0;">Share your link to earn more. Upgrade to {next_tier_name} for higher commissions!</p>"""

    return EmailTemplate(
        subject=f"Your Referral Digest: Rank #{rank} | {tier_name} Tier",
        html=_wrap("Referral Digest", f"Rank #{rank} — {tier_name} Tier", body, "View Referral Dashboard", f"{DASH_URL}/referrals", tier_color, category="engagement"),
        text=_txt("Referral Digest", f"Rank #{rank}, {tier_name} Tier. Referrals: {total_refs}, Active subs: {active_subs}, Earned: ${total_earnings:.2f}. Code: {code}."),
    )


# ── Daily Usage Summary ──────────────────────────────────

@_register("daily_usage_summary", "Daily Usage Summary", "Engagement", "Daily practice recap with conversations, streak, and upgrade prompt")
def build_daily_usage_summary_email(
    user_name: str = "Alex",
    daily_used: int = 5,
    streak: int = 3,
    total: int = 42,
    limit_display: str = "10",
    bar_width: int = 50,
    bar_color: str = "#0ea5e9",
    upgrade_plan: str = get_plan_name("premium"),
    upgrade_price: str = get_monthly_price_label("premium"),
    features: list = None,
) -> EmailTemplate:
    first_name = user_name.strip().split()[0] if user_name.strip() else "there"

    feat_html = ""
    for f in (features or ["Unlimited AI coaching", "Problem Solver access", "Advanced analytics"]):
        feat_html += f'<li style="color:#475569;font-size:13px;line-height:1.8;margin-bottom:2px;">{f}</li>'

    body = f"""{_alert_panel(f"Great work today, {first_name}!", f"{daily_used} conversations completed. Streak: {streak} days.", "#0ea5e9", "DAILY RECAP")}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Conversations</p>
          <p style="color:#0284C7;font-size:26px;font-weight:800;margin:4px 0 0;">{daily_used}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Day Streak</p>
          <p style="color:#D97706;font-size:26px;font-weight:800;margin:4px 0 0;">{streak}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">All Time</p>
          <p style="color:#059669;font-size:26px;font-weight:800;margin:4px 0 0;">{total}</p>
        </div>
      </td>
    </tr></table>

    <div style="margin:16px 0 20px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="color:#94A3B8;font-size:12px;">Daily Usage</td>
        <td style="text-align:right;color:#334155;font-size:12px;font-weight:600;">{daily_used}/{limit_display}</td>
      </tr></table>
      <div style="background:#F1F5F9;border-radius:4px;height:6px;overflow:hidden;margin-top:6px;">
        <div style="background:{bar_color};height:100%;width:{bar_width}%;border-radius:4px;"></div>
      </div>
    </div>

    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:18px;margin-top:8px;">
      <p style="color:#F59E0B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">Unlock More with {upgrade_plan}</p>
      <p style="color:#334155;font-size:14px;font-weight:700;margin:0 0 8px;">{upgrade_plan} Plan — {upgrade_price}</p>
      <ul style="margin:0;padding-left:18px;">{feat_html}</ul>
    </div>

    <p style="color:#64748B;font-size:11px;text-align:center;margin:16px 0 0;">Keep practicing tomorrow to maintain your streak!</p>"""

    return EmailTemplate(
        subject=f"Your daily practice: {daily_used} conversations today!",
        html=_wrap("Daily Recap", f"{daily_used} conversations, {streak}-day streak", body, "View Plans & Upgrade", f"{DASH_URL}/subscription/plans", "#0ea5e9", category="engagement"),
        text=_txt("Daily Usage", f"Great work, {first_name}! {daily_used} conversations today, {streak}-day streak, {total} all-time. {daily_used}/{limit_display} used."),
    )


# ── Payment Analytics Report ─────────────────────────────

@_register("payment_report", "Payment Report", "Billing", "Periodic payment activity and subscription summary report")
def build_payment_report_email(
    user_name: str = "Alex",
    report_type: str = "monthly",
    period_desc: str = "Mar 2026",
    plan_name: str = "Premium",
    total_period: float = 0.0,
    total_alltime: float = 0.0,
    renewal_info: str = "",
    payments: list = None,
) -> EmailTemplate:
    period_label = report_type.replace("_", " ").title()

    # Stats cards
    stats_html = f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F0FDF4;border:1px solid #D1FAE5;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Period Spent</p>
          <p style="color:#059669;font-size:22px;font-weight:800;margin:4px 0 0;">${total_period:.2f}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">All-Time</p>
          <p style="color:#2563EB;font-size:22px;font-weight:800;margin:4px 0 0;">${total_alltime:.2f}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F5F3FF;border:1px solid #DDD6FE;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Plan</p>
          <p style="color:#7C3AED;font-size:18px;font-weight:800;margin:4px 0 0;">{plan_name}</p>
        </div>
      </td>
    </tr></table>"""

    # Transactions table
    tx_rows = ""
    for p in (payments or [])[:10]:
        tx_rows += f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#334155;">{p.get("date","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#334155;">{p.get("plan","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#334155;">{p.get("method","")}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:right;font-size:12px;font-weight:700;color:#059669;">${p.get("amount",0):.2f}</td>
        </tr>"""
    if not tx_rows:
        tx_rows = '<tr><td colspan="4" style="padding:16px;color:#94A3B8;text-align:center;font-size:13px;">No transactions this period</td></tr>'

    tx_table = f"""<h3 style="color:#0F172A;font-size:15px;font-weight:700;margin:20px 0 10px;">Recent Transactions</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;">
      <thead><tr style="background:#F8FAFC;">
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Date</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Plan</th>
        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748B;font-weight:600;">Method</th>
        <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748B;font-weight:600;">Amount</th>
      </tr></thead>
      <tbody>{tx_rows}</tbody>
    </table>"""

    renewal_row = f"<p style='color:#64748B;font-size:13px;margin:8px 0;'>{renewal_info}</p>" if renewal_info else ""

    body = f"""{_alert_panel(f"Your {period_label} Payment Report", f"Payment activity summary for {period_desc}.", "#6366F1", period_label.upper())}
    {_lead(f"Hi {user_name},", f"Here is a summary of your payment activity and subscription status on {BRAND}.")}
    {stats_html}
    {_info_table([_info_row("Subscription", plan_name, "#7C3AED"), _info_row("Payments This Period", str(len(payments or [])))])}
    {renewal_row}
    {tx_table}"""

    return EmailTemplate(
        subject=f"Your {period_label} Payment Report — {period_desc}",
        html=_wrap("Payment Report", f"{period_label} summary for {period_desc}", body, "View Full History", f"{DASH_URL}/payment-history", "#6366F1", category="billing"),
        text=_txt("Payment Report", f"{period_label} — Period: ${total_period:.2f}, All-time: ${total_alltime:.2f}, Plan: {plan_name}."),
    )


# ── Ticket Status Notification ───────────────────────────

@_register("ticket_status_update", "Ticket Status Update", "Support", "Sent when a support ticket status changes, with optional CSAT rating")
def build_ticket_status_update_email(
    user_name: str = "Alex",
    ticket_id: str = "TKT-001",
    subject_line: str = "Support Request",
    new_status: str = "in_progress",
    status_label: str = "In Progress",
    email_body: str = "",
    rate_positive_url: str = "",
    rate_negative_url: str = "",
    reply_url: str = "",
) -> EmailTemplate:
    color_map = {"open": "#3B82F6", "in_progress": "#F59E0B", "awaiting_reply": "#8B5CF6", "resolved": "#10B981", "closed": "#64748B"}
    accent = color_map.get(new_status, "#3B82F6")

    body_content = email_body or f"Hi {user_name}, your support ticket {ticket_id} has been updated to: {status_label}."

    # CSAT rating for resolved/closed
    rating_html = ""
    if new_status in ("resolved", "closed") and rate_positive_url:
        rating_html = f"""<div style="margin-top:20px;padding-top:20px;border-top:1px solid #E2E8F0;text-align:center;">
          <p style="color:#64748B;font-size:13px;margin:0 0 14px;">How was your support experience?</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;"><tr>
            <td style="padding:0 8px;"><a href="{rate_positive_url}" style="display:inline-block;padding:12px 28px;background:#10B981;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Satisfied</a></td>
            <td style="padding:0 8px;"><a href="{rate_negative_url}" style="display:inline-block;padding:12px 28px;background:#EF4444;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Not Satisfied</a></td>
          </tr></table>
          <p style="color:#94A3B8;font-size:10px;margin:14px 0 0;">Your feedback helps us improve</p>
        </div>"""

    # Reply CTA for active statuses
    reply_cta = ""
    if new_status not in ("resolved", "closed") and reply_url:
        reply_cta = f"""<div style="text-align:center;margin-top:20px;padding-top:20px;border-top:1px solid #E2E8F0;">
          <a href="{reply_url}" style="display:inline-block;padding:12px 32px;background:#3B82F6;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Reply to this ticket</a>
          <p style="color:#94A3B8;font-size:11px;margin-top:10px;">Need to provide more details? Click above to reply</p>
        </div>"""

    body = f"""{_alert_panel(f"Ticket {status_label}", f"Your ticket <strong>#{ticket_id}</strong> regarding <strong>{subject_line}</strong> has been updated.", accent, status_label.upper())}
    {_info_table([_info_row("Ticket", f"#{ticket_id}"), _info_row("Subject", subject_line), _info_row("Status", status_label, accent)])}
    <div style="white-space:pre-line;color:#334155;font-size:14px;line-height:1.7;margin:16px 0;">{body_content}</div>
    {rating_html}
    {reply_cta}"""

    return EmailTemplate(
        subject=f"Ticket {ticket_id} — {status_label}",
        html=_wrap("Ticket Update", f"Ticket #{ticket_id} — {status_label}", body, "View My Tickets", f"{DASH_URL}/my-tickets", accent, category="support"),
        text=_txt("Ticket Update", f"Ticket #{ticket_id} — {status_label}. {body_content[:300]}"),
    )


# ── Newsletter Welcome ───────────────────────────────────

@_register("newsletter_welcome", "Newsletter Welcome", "Engagement", "Sent when a visitor subscribes to the newsletter")
def build_newsletter_welcome_email(
    login_url: str = "",
) -> EmailTemplate:
    perks = [
        ("#10B981", "&#10003;", "Early Access", "Be first to try new AI coaching features"),
        ("#3B82F6", "&#9733;", "Expert Insights", "Curated tips from top AI and coaching professionals"),
        ("#F97316", "&#9889;", "Exclusive Content", "Industry reports, webinar invites, and more"),
    ]
    perks_html = ""
    for color, icon, title, desc in perks:
        perks_html += f"""<tr><td style="padding-bottom:16px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:36px;height:36px;background:{color}12;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:{color};font-size:16px;">{icon}</span></td>
            <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:14px;">{title}</strong><br><span style="color:#64748B;font-size:13px;">{desc}</span></td>
          </tr></table>
        </td></tr>"""

    body = f"""{_alert_panel("Welcome to the Inner Circle", "You are now part of a select group shaping the future of AI coaching.", "#10B981", "SUBSCRIBED")}
    <h3 style="color:#0F172A;font-size:16px;font-weight:700;margin:20px 0 14px;">Here is what you will get:</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{perks_html}</table>"""
    cta = login_url or f"{DASH_URL}/auth/login"
    return EmailTemplate(
        subject=f"Welcome to {BRAND} — You're In!",
        html=_wrap("Welcome", "You are now part of the inner circle", body, "Explore the Platform", cta, "#10B981", category="engagement"),
        text=_txt("Newsletter Welcome", "Welcome! You will receive early access, expert insights, and exclusive content."),
    )


# ── Newsletter Blog Digest ───────────────────────────────

@_register("newsletter_blog_digest", "Blog Digest", "Engagement", "Bi-weekly blog digest with latest articles")
def build_newsletter_blog_digest_email(
    posts: list = None,
    unsub_url: str = "",
    prefs_url: str = "",
    open_pixel_url: str = "",
) -> EmailTemplate:
    posts_html = ""
    for p in (posts or [])[:5]:
        cat_colors = {"Industry Insights": "#3B82F6", "Product Update": "#10B981", "Tips & Tricks": "#F59E0B", "Research": "#8B5CF6", "Company News": "#EC4899", "Enterprise": "#06B6D4"}
        color = cat_colors.get(p.get("category", ""), "#3B82F6")
        url = p.get("url", p.get("post_url", "#"))
        img = p.get("image", "")
        img_td = f'<td style="width:140px;vertical-align:top;"><img src="{img}" alt="" style="width:140px;height:100px;object-fit:cover;border-radius:8px 0 0 8px;" /></td>' if img else ""
        posts_html += f"""<tr><td style="padding-bottom:16px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
            <tr>{img_td}
              <td style="padding:14px 16px;vertical-align:top;">
                <span style="display:inline-block;background:{color}18;color:{color};font-size:10px;font-weight:700;padding:3px 8px;border-radius:8px;margin-bottom:6px;">{p.get("category", "")}</span>
                <a href="{url}" style="display:block;color:#0F172A;font-size:15px;font-weight:700;text-decoration:none;line-height:1.3;margin-bottom:4px;">{p.get("title", "")}</a>
                <span style="color:#64748B;font-size:12px;">{p.get("author", "")} &middot; {p.get("read_time", "")}</span>
              </td>
            </tr>
          </table>
        </td></tr>"""
    if not posts_html:
        posts_html = '<tr><td style="color:#64748B;font-size:14px;padding:20px;text-align:center;">No articles this period.</td></tr>'

    pixel = f'<img src="{open_pixel_url}" width="1" height="1" style="display:none;" alt="" />' if open_pixel_url else ""
    unsub = f'<p style="text-align:center;margin:12px 0 0;font-size:12px;color:#94A3B8;"><a href="{unsub_url}" style="color:#94A3B8;">Unsubscribe</a> | <a href="{prefs_url}" style="color:#94A3B8;">Preferences</a></p>' if unsub_url else ""

    body = f"""{_alert_panel("Your Bi-Weekly Blog Digest", "The latest insights in AI coaching and career development.", "#8B5CF6", "NEW ARTICLES")}
    <h3 style="color:#0F172A;font-size:16px;font-weight:700;margin:20px 0 14px;">Latest Articles</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{posts_html}</table>
    {unsub}{pixel}"""
    return EmailTemplate(
        subject=f"Your {BRAND} Blog Digest — New Articles Inside",
        html=_wrap("Blog Digest", "Latest insights in AI coaching", body, "View All Articles", f"{DASH_URL}/blog", "#8B5CF6", category="engagement"),
        text=_txt("Blog Digest", "New articles are available on the blog."),
    )


# ── Newsletter Weekly ────────────────────────────────────

@_register("newsletter_weekly", "Weekly Newsletter", "Engagement", "Weekly platform highlights and roadmap newsletter")
def build_newsletter_weekly_email(
    features: list = None,
    coming_soon: list = None,
    testimonials: list = None,
    impact_stats: list = None,
    week_date: str = "",
    signup_url: str = "",
    unsub_url: str = "",
    prefs_url: str = "",
    open_pixel_url: str = "",
) -> EmailTemplate:
    # Features section
    features_html = ""
    for f in (features or []):
        color = f.get("color", "#3B82F6")
        features_html += f"""<tr><td style="padding-bottom:14px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;">
            <tr><td style="padding:16px 18px;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:42px;vertical-align:top;"><div style="width:38px;height:38px;border-radius:10px;background:{color}12;text-align:center;line-height:38px;font-size:18px;">{f.get("icon", "")}</div></td>
                <td style="padding-left:14px;vertical-align:top;">
                  <span style="color:#0F172A;font-size:14px;font-weight:700;">{f.get("title", "")}</span>
                  <span style="display:inline-block;background:{color}18;color:{color};font-size:9px;font-weight:800;padding:2px 8px;border-radius:10px;margin-left:8px;">{f.get("status", "")}</span>
                  <p style="color:#64748B;font-size:13px;line-height:1.5;margin:6px 0 0;">{f.get("desc", "")}</p>
                </td>
              </tr></table>
            </td></tr>
          </table>
        </td></tr>"""

    # Coming Soon section
    coming_html = ""
    for c in (coming_soon or []):
        coming_html += f"""<tr><td style="padding-bottom:8px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:8px;"><div style="width:6px;height:6px;border-radius:3px;background:{c.get('color','#3B82F6')};"></div></td>
            <td style="padding-left:10px;"><span style="color:#0F172A;font-size:14px;font-weight:600;">{c.get("title","")}</span><span style="color:#64748B;font-size:12px;"> — {c.get("desc","")}</span></td>
          </tr></table>
        </td></tr>"""
    coming_section = f"""<div style="background:#F8FAFC;border-top:1px solid #E2E8F0;border-bottom:1px solid #E2E8F0;padding:24px;">
      <h3 style="color:#0F172A;font-size:16px;font-weight:800;margin:0 0 14px;">Coming Soon</h3>
      <table width="100%" cellpadding="0" cellspacing="0">{coming_html}</table>
    </div>""" if coming_html else ""

    # Testimonials section
    test_html = ""
    for t in (testimonials or []):
        stars = "".join('<span style="color:#F59E0B;font-size:14px;">&#9733;</span>' for _ in range(t.get("stars", 5)))
        initial = t.get("name", "A")[0]
        test_html += f"""<tr><td style="padding-bottom:14px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;">
            <tr><td style="padding:18px;">
              <div style="margin-bottom:10px;">{stars}</div>
              <p style="color:#334155;font-size:13px;line-height:1.6;margin:0 0 12px;font-style:italic;">"{t.get("text","")}"</p>
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:30px;"><div style="width:28px;height:28px;border-radius:14px;background:{t.get('avatar_color','#3B82F6')};text-align:center;line-height:28px;color:#FFF;font-size:12px;font-weight:700;">{initial}</div></td>
                <td style="padding-left:8px;"><span style="color:#0F172A;font-size:12px;font-weight:700;">{t.get("name","")}</span><br><span style="color:#64748B;font-size:10px;">{t.get("title","")}</span></td>
              </tr></table>
            </td></tr>
          </table>
        </td></tr>"""
    test_section = f"""<h3 style="color:#0F172A;font-size:16px;font-weight:800;margin:20px 0 14px;">What People Are Saying</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{test_html}</table>""" if test_html else ""

    # Impact stats
    stats_tds = ""
    for s in (impact_stats or []):
        stats_tds += f'<td style="text-align:center;padding:14px 8px;"><div style="color:{s.get("color","#3B82F6")};font-size:22px;font-weight:900;">{s.get("value","")}</div><div style="color:#64748B;font-size:10px;font-weight:600;margin-top:4px;">{s.get("label","")}</div></td>'
    stats_section = f"""<div style="background:#F8FAFC;border-top:1px solid #E2E8F0;padding:20px;">
      <h3 style="color:#0F172A;font-size:16px;font-weight:800;text-align:center;margin:0 0 8px;">Platform Impact</h3>
      <table width="100%" cellpadding="0" cellspacing="0"><tr>{stats_tds}</tr></table>
    </div>""" if stats_tds else ""

    pixel = f'<img src="{open_pixel_url}" width="1" height="1" style="display:none;" alt="" />' if open_pixel_url else ""
    unsub_html = f'<p style="text-align:center;margin:12px 0 0;font-size:12px;color:#94A3B8;"><a href="{unsub_url}" style="color:#94A3B8;">Unsubscribe</a> | <a href="{prefs_url}" style="color:#94A3B8;">Preferences</a></p>' if unsub_url else ""
    date_label = week_date or ""

    body = f"""{_alert_panel("Your Week in AI Coaching", f"Features, insights, and what is next at {BRAND}. {date_label}", "#059669", "WEEKLY")}
    <h3 style="color:#0F172A;font-size:16px;font-weight:800;margin:20px 0 14px;">Platform Highlights</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{features_html}</table>
    {coming_section}
    {test_section}
    {stats_section}
    {unsub_html}{pixel}"""
    cta = signup_url or f"{DASH_URL}/auth/register"
    return EmailTemplate(
        subject=f"Your Week in AI Coaching — {BRAND} Weekly ({date_label})",
        html=_wrap("Weekly Newsletter", "Features, insights, and what is next", body, "Start Your Free Journey", cta, "#059669", category="engagement"),
        text=_txt("Weekly Newsletter", f"Your Week in AI Coaching — {date_label}. Check out the latest platform highlights."),
    )


# ── Newsletter Monthly Campaign ──────────────────────────

@_register("newsletter_monthly_campaign", "Monthly Campaign", "Engagement", "Monthly AI coaching digest with platform stats")
def build_newsletter_monthly_campaign_email(
    month_label: str = "April 2026",
    total_users: int = 0,
    new_subscribers: int = 0,
    ai_requests: int = 0,
    top_features: list = None,
    tips: list = None,
) -> EmailTemplate:
    # Stats cards
    stats_html = f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Active Users</p>
          <p style="color:#00D4AA;font-size:22px;font-weight:800;margin:4px 0 0;">{total_users:,}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">New Members</p>
          <p style="color:#3B82F6;font-size:22px;font-weight:800;margin:4px 0 0;">+{new_subscribers}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">AI Requests</p>
          <p style="color:#8B5CF6;font-size:22px;font-weight:800;margin:4px 0 0;">{ai_requests:,}</p>
        </div>
      </td>
    </tr></table>"""

    # Trending features
    feat_icons = ["&#128640;", "&#9889;", "&#127891;", "&#128161;", "&#127775;"]
    feat_html = ""
    for i, feat in enumerate((top_features or ["AI Coaching", "Problem Solver", "Learning Hub"])[:5]):
        icon = feat_icons[i % len(feat_icons)]
        feat_html += f"""<tr><td style="padding:6px 0;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:34px;height:34px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;font-size:15px;">{icon}</td>
            <td style="padding-left:12px;"><strong style="color:#1E293B;font-size:13px;">{feat}</strong></td>
          </tr></table>
        </td></tr>"""

    # Tips
    tips_html = ""
    for tip in (tips or [
        "Use the AI Problem Solver for complex scenarios.",
        "Check your Learning Hub weekly for personalized courses.",
        "Review your My Analytics dashboard to track progression.",
    ]):
        tips_html += f'<li style="color:#475569;font-size:13px;line-height:1.8;margin-bottom:4px;">{tip}</li>'

    body = f"""{_alert_panel("Monthly AI Coaching Digest", f"{month_label} — Platform growth and highlights.", "#3B82F6", month_label.upper())}
    {stats_html}
    <h3 style="color:#0F172A;font-size:15px;font-weight:700;margin:16px 0 10px;">Trending This Month</h3>
    <table width="100%" cellpadding="0" cellspacing="0">{feat_html}</table>
    <h3 style="color:#0F172A;font-size:15px;font-weight:700;margin:20px 0 10px;">Pro Tips</h3>
    <ul style="padding-left:20px;margin:0;">{tips_html}</ul>"""
    return EmailTemplate(
        subject=f"Monthly AI Coaching Digest — {month_label}",
        html=_wrap("Monthly Digest", f"{month_label} platform highlights", body, "Explore the Platform", f"{DASH_URL}/auth/login", "#3B82F6", category="engagement"),
        text=_txt("Monthly Digest", f"{month_label} — Active users: {total_users:,}, New: +{new_subscribers}, AI Requests: {ai_requests:,}."),
    )


# ── Contact Team Notification (admin receives new submission) ────

@_register("contact_team_notify", "Contact Team Notification", "Support", "Internal notification when a visitor submits a contact form")
def build_contact_team_notify_email(
    sender_name: str = "Alex Johnson",
    sender_email: str = "alex@example.com",
    subject: str = "General Inquiry",
    message: str = "I'd like to know more about your platform...",
    category: str = "",
) -> EmailTemplate:
    rows = [_info_row("Name", sender_name, PRIMARY), _info_row("Email", sender_email, "#0D9488"), _info_row("Subject", subject)]
    if category:
        rows.append(_info_row("Category", category, "#F59E0B"))
    body = f"""{_alert_panel("New Contact Form Submission", "A website visitor has submitted a contact inquiry. Review and respond promptly.", PRIMARY, "NEW INQUIRY")}
    {_info_table(rows)}
    {_callout(message[:500])}
    <p class="em-text-secondary" style="font-size:12px;color:#64748B;margin:16px 0 0;">Reply directly to this email to respond to the sender.</p>"""
    return EmailTemplate(
        subject=f"[Contact] {subject or 'General Inquiry'} — {sender_name}",
        html=_wrap("New Contact Inquiry", f"Message from {sender_name}", body, "View in Dashboard", f"{DASH_URL}/admin-console?tab=contact", category="support"),
        text=_txt("New Contact Form", f"From: {sender_name} ({sender_email})\nSubject: {subject}\n\n{message[:500]}"),
    )


# ── Contact Follow-Up (user gets a status update) ───────

@_register("contact_followup", "Contact Follow-Up", "Support", "Automated follow-up sent to users whose inquiry is still pending")
def build_contact_followup_email(
    user_name: str = "Alex",
    subject: str = "General Inquiry",
    submitted_date: str = "2026-04-14",
    priority: str = "Elevated",
    signup_url: str = "",
) -> EmailTemplate:
    first_name = user_name.strip().split()[0] if user_name.strip() else "there"
    q = '"'
    body = f"""{_alert_panel("Your Inquiry Is Being Prioritized", "Our team is actively reviewing your message. You will hear from us soon.", "#F59E0B", "IN REVIEW")}
    {_lead("We have not forgotten about you", f"Hi {first_name}, we wanted to let you know that your message about <strong>{q}{subject}{q}</strong> is still in our queue and being actively reviewed by our team. We understand your time is valuable, and we are working to get you a thorough response.")}
    {_info_table([_info_row("Status", "In Review", "#F59E0B"), _info_row("Submitted", submitted_date), _info_row("Subject", subject), _info_row("Priority", priority, "#10B981")])}
    <p style="margin:16px 0 0;font-size:14px;">Our support team will reach out to you shortly. In the meantime, you can explore everything {BRAND} has to offer.</p>
    <p class="em-text-secondary" style="font-size:13px;color:#64748B;margin:12px 0 0;">Need urgent help? Reply directly to this email and we will fast-track your request.</p>"""
    cta = signup_url or f"{DASH_URL}/auth/register"
    return EmailTemplate(
        subject=f"Update on your inquiry, {first_name} — We're on it",
        html=_wrap("Inquiry Update", f"Your message about {q}{subject}{q} is being reviewed", body, f"Explore {BRAND} Free", cta, "#3B82F6", category="support"),
        text=_txt("Inquiry Update", f"Hi {first_name}, your message about {q}{subject}{q} is being reviewed (submitted {submitted_date}, priority: {priority}). We will respond shortly.\n\nExplore {BRAND}: {cta}"),
    )


# ── Contact Admin Reply (admin responds to user) ────────

@_register("contact_admin_reply", "Contact Admin Reply", "Support", "Sent when an admin replies to a contact form submission")
def build_contact_admin_reply_email(
    user_name: str = "Alex",
    original_subject: str = "General Inquiry",
    reply_message: str = "Thank you for reaching out. Here's what we found...",
    custom_subject: str = "",
    signup_url: str = "",
) -> EmailTemplate:
    first_name = user_name.strip().split()[0] if user_name.strip() else "there"
    q = '"'
    body = f"""{_alert_panel(f"{BRAND} Support Response", f"Regarding your inquiry about: <strong>{original_subject}</strong>", "#059669", "SUPPORT REPLY")}
    {_lead("Hi " + first_name + ",", "Our team has reviewed your inquiry and here is our response:")}
    {_callout(reply_message[:800])}
    <p class="em-text-secondary" style="font-size:13px;color:#64748B;margin:16px 0 0;">You can reply directly to this email to continue the conversation.</p>"""
    cta = signup_url or f"{DASH_URL}/auth/register"
    subj = custom_subject or f"Re: {original_subject} — {BRAND} Support"
    return EmailTemplate(
        subject=subj,
        html=_wrap("Support Response", f"Reply to your inquiry about {q}{original_subject}{q}", body, f"Get Started with {BRAND}", cta, "#059669", category="support"),
        text=_txt("Support Response", f"Hi {first_name},\n\nRegarding your inquiry about {q}{original_subject}{q}:\n\n{reply_message[:800]}\n\nReply to this email to continue the conversation."),
    )



# ── Anomaly Digest (rich stats + domain table) ──────────

@_register("anomaly_digest", "Anomaly Digest", "Notifications", "Anomaly detection digest with stats cards and domain breakdown")
def build_anomaly_digest_email(
    period: str = "Daily",
    total_issues: int = 0,
    total_fixes: int = 0,
    top_domains: list = None,
    auto_fix_triggered: bool = False,
) -> EmailTemplate:
    fix_rate = round(total_fixes / max(total_issues, 1) * 100, 1)
    severity = "CRITICAL" if period.upper().startswith("SPIKE") else "INFO"
    badge_color = "#EF4444" if severity == "CRITICAL" else "#3B82F6"
    fix_badge = ' <span style="background:#10B981;color:#fff;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;vertical-align:middle;">AUTO-FIX ACTIVE</span>' if auto_fix_triggered else ""

    # Stats cards row
    rate_color = "#059669" if fix_rate >= 90 else "#D97706" if fix_rate >= 50 else "#DC2626"
    stats_html = f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
    <tr>
      <td style="width:33%;padding:4px;">
        <div style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Issues</p>
          <p style="color:#D97706;font-size:26px;font-weight:800;margin:4px 0 0;">{total_issues}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Fixes</p>
          <p style="color:#059669;font-size:26px;font-weight:800;margin:4px 0 0;">{total_fixes}</p>
        </div>
      </td>
      <td style="width:33%;padding:4px;">
        <div style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:14px;text-align:center;">
          <p style="color:#64748B;font-size:10px;margin:0;text-transform:uppercase;font-weight:700;">Fix Rate</p>
          <p style="color:{rate_color};font-size:26px;font-weight:800;margin:4px 0 0;">{fix_rate}%</p>
        </div>
      </td>
    </tr></table>"""

    # Domain table
    domain_rows = ""
    for d in (top_domains or []):
        if isinstance(d, dict):
            dname = d.get("domain", "unknown").replace("_", " ").title()
            di = d.get("issues", 0)
            df = d.get("fixes", 0)
            dr = round(df / max(di, 1) * 100, 1)
            rc = "#059669" if dr >= 90 else "#D97706" if dr >= 50 else "#EF4444"
            domain_rows += f'<tr><td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:13px;">{dname}</td><td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:center;color:#D97706;font-size:13px;">{di}</td><td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:center;color:#059669;font-size:13px;">{df}</td><td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:center;color:{rc};font-size:13px;">{dr}%</td></tr>'
    if not domain_rows:
        domain_rows = '<tr><td colspan="4" style="padding:16px;color:#94A3B8;text-align:center;">No domain data available</td></tr>'

    domain_table = f"""<p style="color:#0F172A;font-size:14px;font-weight:700;margin:16px 0 8px;">Top Affected Domains</p>
    <table width="100%" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;border-collapse:collapse;">
      <tr>
        <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:left;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Domain</th>
        <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Issues</th>
        <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Fixes</th>
        <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Fix Rate</th>
      </tr>
      {domain_rows}
    </table>"""

    body = f"""{_alert_panel(f"Anomaly Detection — {period} Digest", f"{total_issues} anomalies detected. Fix rate: {fix_rate}%.{fix_badge}", badge_color, severity)}
    {stats_html}
    {domain_table}"""

    return EmailTemplate(
        subject=f"[{period.upper()}] {total_issues} anomalies detected" + (" in the last hour" if "spike" in period.lower() else ""),
        html=_wrap("Anomaly Detection", f"{period} digest — {total_issues} issues, {total_fixes} fixes", body, "Open Dashboard", f"{DASH_URL}/admin-console?tab=anomaly", badge_color, category="notifications"),
        text=_txt("Anomaly Digest", f"{period} — Issues: {total_issues}, Fixes: {total_fixes}, Fix Rate: {fix_rate}%. Auto-fix: {'Active' if auto_fix_triggered else 'Inactive'}."),
    )



# ── Career Application Confirmation ─────────────────────

@_register("career_confirmation", "Career Confirmation", "Employer", "Sent when a user applies for a position")
def build_career_confirmation_email(
    applicant_name: str = "Alex Johnson",
    position: str = "Software Engineer",
    application_id: str = "APP-001",
    hiring_contact_email: str = "hiring@realaicoach.app",
    response_window_days: int = 7,
) -> EmailTemplate:
    # Redesigned Apr 22 2026: warmer applicant-facing identity distinct
    # from internal admin-notify template. Adds:
    #   • Emerald accent + celebratory hero card with applicant's first name
    #   • "What happens next" 3-step timeline (Review → Screening → Response)
    #   • Application snapshot card with ID + position + status
    #   • Explicit hiring@realaicoach.app mailto CTA so applicants can
    #     update their application, ask questions, or withdraw
    # Apr 23 2026: added an "Application Tracker" primary CTA that deep-links
    # to the bookmarkable /careers/track/{id} status page — dramatically cuts
    # "where is my application?" pings to the hiring inbox.
    first_name = applicant_name.strip().split()[0] if applicant_name.strip() else "there"
    emerald = "#10B981"
    emerald_soft = "#D1FAE5"
    emerald_bg = "#ECFDF5"
    tracker_url = f"{DASH_URL}/careers/track/{application_id}"

    hero = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:{emerald_bg};border:1px solid {emerald_soft};border-radius:14px;padding:20px 18px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="width:52px;vertical-align:middle;">
                <div style="width:48px;height:48px;border-radius:24px;background:{emerald};color:#FFFFFF;text-align:center;line-height:48px;font-size:22px;font-weight:800;">✓</div>
              </td>
              <td style="vertical-align:middle;padding-left:14px;">
                <p style="margin:0;font-size:11px;font-weight:800;letter-spacing:.06em;color:{emerald};text-transform:uppercase;">Application Received</p>
                <p style="margin:4px 0 0;font-size:18px;font-weight:800;color:#065F46;">Thanks for applying, {first_name}!</p>
                <p style="margin:4px 0 0;font-size:13px;color:#047857;">Our team has your application for <strong>{position}</strong> and we're reviewing it now.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>"""

    def _step(num: int, title: str, subtitle: str, active: bool) -> str:
        dot_bg = emerald if active else "#CBD5E1"
        dot_fg = "#FFFFFF"
        title_color = "#0F172A" if active else "#64748B"
        return f"""
        <tr>
          <td style="width:34px;vertical-align:top;padding:6px 10px 6px 0;">
            <div style="width:28px;height:28px;border-radius:14px;background:{dot_bg};color:{dot_fg};text-align:center;line-height:28px;font-size:12px;font-weight:800;">{num}</div>
          </td>
          <td style="vertical-align:top;padding:4px 0 12px;">
            <p style="margin:0;font-size:14px;font-weight:700;color:{title_color};">{title}</p>
            <p style="margin:2px 0 0;font-size:12px;color:#64748B;line-height:1.55;">{subtitle}</p>
          </td>
        </tr>"""

    timeline = f"""
    <p style="font-size:13px;font-weight:800;color:#065F46;text-transform:uppercase;letter-spacing:.04em;margin:22px 0 10px;">What happens next</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px;">
      {_step(1, "Initial review", "A recruiter reviews your application against the role requirements. Typically within 2 business days.", True)}
      {_step(2, "Screening", "If there's a match, we'll reach out to schedule an introductory call.", False)}
      {_step(3, "Response", f"Whether or not we move forward, you'll hear back from us within {response_window_days} business days.", False)}
    </table>"""

    snapshot = _info_table([
        _info_row("Position", position),
        _info_row("Application ID", application_id, PRIMARY),
        _info_row("Status", "Under Review", emerald),
    ])

    tracker_cta = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0 0;">
      <tr>
        <td align="center" style="padding:0;">
          <a href="{tracker_url}" style="display:inline-block;background:{emerald};color:#FFFFFF;text-decoration:none;padding:14px 26px;border-radius:12px;font-weight:800;font-size:15px;letter-spacing:.02em;">Track your application →</a>
        </td>
      </tr>
      <tr>
        <td align="center" style="padding:10px 0 0;">
          <p style="margin:0;font-size:12px;color:#64748B;">Bookmark this link — we update it live as your status changes.</p>
        </td>
      </tr>
    </table>"""

    contact_card = f"""
    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;margin:20px 0 0;">
      <p style="margin:0 0 6px;font-size:12px;font-weight:800;color:#475569;text-transform:uppercase;letter-spacing:.04em;">Need to reach us?</p>
      <p style="margin:0;font-size:14px;color:#334155;line-height:1.6;">Want to update your application, add a portfolio link, ask a question, or withdraw? Email us at <a href="mailto:{hiring_contact_email}" style="color:{emerald};font-weight:700;text-decoration:underline;">{hiring_contact_email}</a> and include your Application ID above. Our recruiting team owns this inbox and replies within 1 business day.</p>
    </div>"""

    body = f"""{hero}
    {_lead(f"Hi {first_name},", f"We appreciate you taking the time to apply for the <strong>{position}</strong> role at {BRAND}. Your application is now in our review queue, and a member of our recruiting team will personally review it.")}
    {snapshot}
    {tracker_cta}
    {timeline}
    {contact_card}"""

    return EmailTemplate(
        subject=f"Application Received — {position} at {BRAND} [{application_id}]",
        html=_wrap(
            "Application Received",
            f"Your application for {position} is confirmed",
            body,
            "Track application",
            tracker_url,
            emerald,
            category="employer",
        ),
        text=_txt(
            "Application Received",
            (
                f"Hi {first_name},\n\n"
                f"Thank you for applying for {position} at {BRAND}. "
                f"Your application (ID: {application_id}) is under review.\n\n"
                f"Track your application status live at:\n{tracker_url}\n\n"
                "What happens next:\n"
                "1) Initial review (within 2 business days)\n"
                "2) Screening call if there's a match\n"
                f"3) Response from us within {response_window_days} business days either way\n\n"
                f"Need to update, ask, or withdraw? Email {hiring_contact_email} "
                f"and include your Application ID ({application_id}). "
                "Our recruiting team replies within 1 business day."
            ),
        ),
    )


@_register("career_admin_notify", "Career Admin Notification", "Employer", "Internal notification for new career applications")
def build_career_admin_notify_email(
    applicant_name: str = "Alex Johnson",
    position: str = "Software Engineer",
    application_id: str = "APP-001",
    email: str = "alex@example.com",
    experience: str = "",
) -> EmailTemplate:
    rows = [_info_row("Applicant", applicant_name, PRIMARY), _info_row("Position", position), _info_row("Application ID", application_id)]
    if email:
        rows.append(_info_row("Email", email, "#0D9488"))
    if experience:
        rows.append(_info_row("Experience", experience))
    body = f"""{_alert_panel("New Career Application", f"A new application has been submitted for <strong>{position}</strong>.", "#3B82F6", "NEW")}
    {_info_table(rows)}"""
    return EmailTemplate(
        subject=f"New Application: {position} — {applicant_name}",
        html=_wrap("New Application", f"Review application from {applicant_name}", body, "Review Applications", f"{DASH_URL}/admin-console?tab=careers", category="employer"),
        text=_txt("New Application", f"New application from {applicant_name} for {position} (ID: {application_id})."),
    )


@_register("career_recruiter_reply", "Career Recruiter Reply", "Employer", "Recruiter outbound reply on the applicant thread")
def build_career_recruiter_reply_email(
    applicant_name: str = "Alex Johnson",
    position: str = "Software Engineer",
    application_id: str = "APP-001",
    body_text: str = "",
    subject: str = "",
    hiring_contact_email: str = "hiring@realaicoach.app",
) -> EmailTemplate:
    """Recruiter-side outbound reply, wrapped in the V7 email layout so
    it carries the required ``em-outer`` fingerprint and passes the v7
    HTML guardrail in ``utils.email_service.send_email``. The reply body
    (plain text typed by the recruiter) is escaped and rendered inside a
    simple left-border card. The subject auto-carries ``[APP-XXX]`` so
    the applicant's reply auto-correlates via the thread webhook.
    """
    import html as _html

    safe_body = _html.escape(body_text or "").replace("\n", "<br>")
    first = applicant_name.split()[0] if applicant_name else "there"
    inner = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 6px;">Hi {_html.escape(first)},</p>
<p style="margin:0 0 16px;color:#475569;font-size:14px;line-height:1.6;">A message from the <strong>{BRAND}</strong> hiring team regarding your application for <strong>{_html.escape(position)}</strong> (Application ID: <code style="background:#F1F5F9;padding:1px 6px;border-radius:4px;font-family:ui-monospace,Menlo,Monaco,monospace;font-size:12px;">{_html.escape(application_id)}</code>).</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;border:1px solid #E2E8F0;border-left:3px solid {PRIMARY};margin:12px 0 18px;">
  <tr><td style="padding:16px 18px;color:#0F172A;font-size:14px;line-height:1.6;">{safe_body}</td></tr>
</table>
<p style="margin:0 0 6px;color:#64748B;font-size:13px;">Reply directly to this email (or write to <a href="mailto:{hiring_contact_email}" style="color:{PRIMARY};font-weight:600;text-decoration:none;">{hiring_contact_email}</a>) — your reply will be routed back to your recruiter automatically.</p>"""

    resolved_subject = (subject or "").strip() or f"Re: Your application for {position}"
    if f"[{application_id}]" not in resolved_subject:
        resolved_subject = f"{resolved_subject} [{application_id}]"

    return EmailTemplate(
        subject=resolved_subject,
        html=_wrap(
            title="Message from the Hiring Team",
            preheader=f"{BRAND} hiring team update for {application_id}",
            inner_html=inner,
            cta_label="",
            cta_url="",
            accent=PRIMARY,
            category="employer",
        ),
        text=_txt(
            "Message from the Hiring Team",
            f"Hi {first},\n\n"
            + (body_text or "")
            + f"\n\nReply to {hiring_contact_email} and reference {application_id}.",
        ),
    )


@_register("career_status_update", "Career Status Update", "Employer", "Sent when application status changes")
def build_career_status_update_email(
    applicant_name: str = "Alex Johnson",
    position: str = "Software Engineer",
    application_id: str = "APP-001",
    status: str = "interview_scheduled",
    status_label: str = "Interview Scheduled",
    interview_date: str = "",
    interview_type: str = "",
    notes: str = "",
) -> EmailTemplate:
    color_map = {"reviewing": "#3B82F6", "interview_scheduled": "#8B5CF6", "offer_extended": "#10B981", "hired": "#10B981", "rejected": "#EF4444", "waitlisted": "#F59E0B"}
    accent = color_map.get(status, "#3B82F6")
    tracker_url = f"{DASH_URL}/careers/track/{application_id}"
    rows = [_info_row("Position", position), _info_row("Application ID", application_id), _info_row("Status", status_label, accent)]
    if interview_date:
        rows.append(_info_row("Interview Date", interview_date))
    if interview_type:
        rows.append(_info_row("Interview Type", interview_type))
    tracker_cta = f"""
    <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:18px 0 0;\">
      <tr>
        <td align=\"center\" style=\"padding:0;\">
          <a href=\"{tracker_url}\" style=\"display:inline-block;background:{accent};color:#FFFFFF;text-decoration:none;padding:12px 22px;border-radius:10px;font-weight:800;font-size:14px;letter-spacing:.02em;\">View live status →</a>
        </td>
      </tr>
      <tr>
        <td align=\"center\" style=\"padding:8px 0 0;\">
          <p style=\"margin:0;font-size:11px;color:#64748B;\">We update this page the moment anything moves.</p>
        </td>
      </tr>
    </table>"""
    body = f"""{_alert_panel(f"Application Update: {status_label}", f"Your application for <strong>{position}</strong> has been updated.", accent, status_label.upper())}
    {_lead(f"Hi {applicant_name},", "We have an update on your application.")}
    {_info_table(rows)}
    {tracker_cta}"""
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"Application Update — {status_label}",
        html=_wrap("Application Update", f"Status: {status_label}", body, "View live status", tracker_url, accent, category="employer"),
        text=_txt("Application Update", f"Hi {applicant_name}, your application for {position} status: {status_label}.\n\nTrack live at: {tracker_url}"),
    )



# ── Per-status templates (one polished V7 template for each Application status) ──

@_register("career_status_received", "Career — Application Received", "Employer",
           "Warm acknowledgement that the candidate's application has been received")
def build_career_status_received_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    application_id: str = "APP-001",
    notes: str = "",
) -> EmailTemplate:
    accent = "#0F766E"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("Application received", f"We received your application for <strong>{role_title}</strong>.", accent, "RECEIVED")
        + _lead(f"Hi {first},",
                f"Thanks for applying to the <strong>{role_title}</strong> role at {BRAND}. "
                "Our talent team has received everything and will take a careful look. "
                "We typically respond within 5–7 business days — we'll be in touch the moment we have an update.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Application ID", application_id),
            _info_row("Status", "Received", accent),
        ])
    )
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"Application received — {role_title} at {BRAND}",
        html=_wrap("Application Received", f"Thanks for applying to {role_title}", body,
                   "View Careers", f"{DASH_URL}/careers", accent, category="employer"),
        text=_txt("Application Received",
                  f"Hi {first}, thanks for applying to {role_title} at {BRAND}. We have received your application (ID {application_id}) and will respond within 5–7 business days."),
    )


@_register("career_status_under_review", "Career — Under Review", "Employer",
           "Notifies the candidate that their application is now actively being reviewed")
def build_career_status_under_review_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    application_id: str = "APP-001",
    notes: str = "",
) -> EmailTemplate:
    accent = "#B45309"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("Your application is under review", "The hiring team is actively reviewing your profile.", accent, "UNDER REVIEW")
        + _lead(f"Hi {first},",
                f"Good news — your application for <strong>{role_title}</strong> has moved to the review stage. "
                "Our hiring panel is now looking at your cover letter, experience, and portfolio. "
                "You don't need to do anything right now; we'll follow up with next steps (or a decision) shortly.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Application ID", application_id),
            _info_row("Status", "Under Review", accent),
        ])
    )
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"Your application is under review — {role_title}",
        html=_wrap("Under Review", f"Your application for {role_title}", body,
                   "View Careers", f"{DASH_URL}/careers", accent, category="employer"),
        text=_txt("Under Review",
                  f"Hi {first}, your application for {role_title} at {BRAND} is now under review by our hiring panel."),
    )


@_register("career_status_interview", "Career — Interview Stage", "Employer",
           "Announces that the candidate has advanced to the interview stage")
def build_career_status_interview_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    application_id: str = "APP-001",
    notes: str = "",
) -> EmailTemplate:
    accent = "#14B8A6"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("You're moving to interviews!", "We loved what we saw and want to chat.", accent, "INTERVIEW STAGE")
        + _lead(f"Hi {first},",
                f"Congratulations — your application for <strong>{role_title}</strong> has advanced to the interview stage! "
                "A separate calendar invite with the date, time, and join link is on its way (or has already landed in your inbox). "
                "If you don't see it within an hour, please check your spam folder or reply to this email.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Application ID", application_id),
            _info_row("Status", "Interview", accent),
        ])
    )
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"You're moving to interviews — {role_title}",
        html=_wrap("Interview Stage", f"Next step: interview for {role_title}", body,
                   "View Careers", f"{DASH_URL}/careers", accent, category="employer"),
        text=_txt("Interview Stage",
                  f"Hi {first}, congratulations — your application for {role_title} has advanced to the interview stage. Calendar invite coming separately."),
    )


@_register("career_status_offer", "Career — Offer Extended", "Employer",
           "Celebratory note letting the candidate know an offer is on its way")
def build_career_status_offer_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    application_id: str = "APP-001",
    notes: str = "",
) -> EmailTemplate:
    accent = "#047857"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("🎉 We'd love for you to join us", f"An offer for <strong>{role_title}</strong> is on its way.", accent, "OFFER")
        + _lead(f"Hi {first},",
                f"We're thrilled to let you know that we'd like to extend an offer for the <strong>{role_title}</strong> role at {BRAND}. "
                "A formal offer letter with compensation, start date, and next-step instructions will arrive shortly from our People Ops team. "
                "In the meantime, feel free to reply to this email with any immediate questions — we're here for you.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Application ID", application_id),
            _info_row("Status", "Offer", accent),
        ])
    )
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"🎉 Offer incoming — {role_title} at {BRAND}",
        html=_wrap("Offer Extended", "We'd love for you to join us", body,
                   "View Careers", f"{DASH_URL}/careers", accent, category="employer"),
        text=_txt("Offer Extended",
                  f"Hi {first}, great news — we are extending an offer for the {role_title} role at {BRAND}. A formal offer letter is on its way."),
    )


@_register("career_status_rejected", "Career — Respectful Decline", "Employer",
           "Warm, respectful note letting the candidate know we've decided not to move forward")
def build_career_status_rejected_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    application_id: str = "APP-001",
    notes: str = "",
) -> EmailTemplate:
    accent = "#64748B"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("Thanks for applying",
                     f"We won't be moving forward with your application for <strong>{role_title}</strong> at this time.",
                     accent, "DECISION")
        + _lead(f"Hi {first},",
                f"Thank you for taking the time to apply for the <strong>{role_title}</strong> role at {BRAND} — and for trusting us with your story. "
                "After careful review, we've decided not to move forward at this time. This decision is never easy, and it doesn't diminish the work you've put into your career. "
                "We'd love to stay in touch — we'll hold your details on file and reach out when roles open that better match your experience.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Application ID", application_id),
            _info_row("Status", "Not proceeding", accent),
        ])
    )
    if notes:
        body += _callout(notes[:500])
    return EmailTemplate(
        subject=f"Update on your application — {role_title}",
        html=_wrap("Thank you for applying", f"An update on your {role_title} application", body,
                   "View open roles", f"{DASH_URL}/careers", accent, category="employer"),
        text=_txt("Thank you for applying",
                  f"Hi {first}, thank you for applying for the {role_title} role at {BRAND}. After careful review we've decided not to move forward at this time."),
    )




@_register("career_interview_invite", "Career Interview Invite", "Employer",
           "One-click interview invitation sent to a candidate with ICS attachment and Accept/Reschedule CTA")
def build_career_interview_invite_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    interview_date: str = "2026-05-15",
    interview_time: str = "14:30",
    duration_minutes: int = 45,
    interview_type: str = "video",
    timezone_label: str = "UTC",
    confirm_url: str = "",
    message: str = "",
) -> EmailTemplate:
    # Pretty date string
    pretty_when = interview_date
    try:
        from datetime import datetime as _dt
        pretty_when = _dt.strptime(interview_date, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    except Exception:
        pass
    type_label = (interview_type or "video").title()
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    rows = [
        _info_row("Role", role_title, PRIMARY),
        _info_row("Date", pretty_when),
        _info_row("Time", f"{interview_time} {timezone_label}"),
        _info_row("Duration", f"{duration_minutes} minutes"),
        _info_row("Format", type_label, "#14B8A6"),
    ]
    body = (
        _alert_panel(
            "You're invited to interview",
            f"We'd love to chat with you about the <strong>{role_title}</strong> role.",
            "#0F766E", "INTERVIEW INVITE",
        )
        + _lead(f"Hi {first},",
                f"Thanks for applying. We'd like to invite you to a {type_label.lower()} interview. "
                "Use the button below to confirm this time or propose a different one — no password required.")
        + _info_table(rows)
    )
    if message:
        body += _callout(message[:500])
    return EmailTemplate(
        subject=f"Interview invite: {role_title} at {BRAND}",
        html=_wrap(
            "Interview invite",
            f"{type_label} on {pretty_when} at {interview_time} {timezone_label}",
            body,
            "Confirm or reschedule",
            confirm_url or f"{DASH_URL}/careers/interview/confirm",
            "#0F766E",
        ),
        text=_txt(
            "Interview invite",
            f"Hi {first}, you're invited to a {type_label.lower()} interview for {role_title} on "
            f"{pretty_when} at {interview_time} {timezone_label}. Duration {duration_minutes} minutes. "
            f"Confirm or reschedule: {confirm_url or DASH_URL}",
        ),
    )


# ── Offer Studio — 5 templates (sent / accepted / declined / rescinded / expired) ──

@_register("career_offer_sent", "Career — Offer Sent", "Employer",
           "Enterprise offer letter email with Accept/Decline CTA and attached PDF")
def build_career_offer_sent_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    base_salary_usd: int = 120000,
    start_date: str = "2026-06-01",
    expires_at: str = "2026-05-20",
    confirm_url: str = "",
    personal_message: str = "",
    tracking_pixel_url: str = "",
) -> EmailTemplate:
    accent = "#0F766E"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("We'd love for you to join us",
                     f"Your offer for <strong>{role_title}</strong> at {BRAND} is attached.",
                     accent, "OFFER ENCLOSED")
        + _lead(f"Hi {first},",
                (personal_message or
                 f"On behalf of the team, it is my pleasure to extend you this offer for the <strong>{role_title}</strong> role at {BRAND}. "
                 "The full terms are detailed in the attached PDF offer letter — please review and respond using the button below."))
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Base salary", f"${int(base_salary_usd):,} USD"),
            _info_row("Start date", start_date or "TBD"),
            _info_row("Offer expires", expires_at, "#B45309"),
        ])
        + _callout(
            "Tap the button below to accept or request to decline. "
            "Your decision is securely recorded with a timestamped e-signature — no password required.")
    )
    # Invisible tracking pixel appended at end (allowed inside _wrap body content)
    if tracking_pixel_url:
        body += f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:block;width:1px;height:1px;border:0;opacity:0"/>'
    return EmailTemplate(
        subject=f"Your offer from {BRAND} — {role_title}",
        html=_wrap("Your Offer Letter", f"{role_title} at {BRAND}", body,
                   "Accept or request to decline", confirm_url or f"{DASH_URL}/careers",
                   accent, category="employer"),
        text=_txt("Offer Letter",
                  f"Hi {first}, your offer for {role_title} at {BRAND} is attached. Respond at {confirm_url}. Expires {expires_at}."),
    )


@_register("career_offer_accepted", "Career — Offer Accepted", "Employer",
           "Congratulatory confirmation sent after the candidate signs the offer")
def build_career_offer_accepted_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    start_date: str = "2026-06-01",
) -> EmailTemplate:
    accent = "#10B981"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("🎉 Welcome aboard!",
                     "Thank you for accepting — we cannot wait to have you on the team.",
                     accent, "ACCEPTED & COUNTERSIGNED")
        + _lead(f"Hi {first},",
                f"We've officially recorded your acceptance of the <strong>{role_title}</strong> role at {BRAND}. "
                "A countersigned copy of your offer letter is attached for your records. "
                "Our People Ops team will reach out shortly with onboarding details, paperwork, and your first-week schedule.")
        + _info_table([
            _info_row("Role", role_title, accent),
            _info_row("Start date", start_date or "TBD", accent),
            _info_row("Status", "Accepted & Countersigned", accent),
        ])
        + _callout("Save the attached PDF — it includes your digital signature, timestamp, and hash for your records.")
    )
    return EmailTemplate(
        subject=f"🎉 Welcome to {BRAND}, {first}! — Your signed offer",
        html=_wrap("Offer Accepted", "We're so glad to have you", body,
                   "View your careers dashboard", f"{DASH_URL}/careers",
                   accent, category="employer"),
        text=_txt("Offer Accepted",
                  f"Hi {first}, thank you for accepting the {role_title} role at {BRAND}. Countersigned offer attached."),
    )


@_register("career_offer_declined", "Career — Offer Declined", "Employer",
           "Respectful acknowledgement after a candidate declines the offer")
def build_career_offer_declined_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    reason: str = "",
) -> EmailTemplate:
    accent = "#64748B"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("We've recorded your decision",
                     "Thank you for taking the time to review our offer.",
                     accent, "OFFER DECLINED")
        + _lead(f"Hi {first},",
                f"We've recorded your decision to decline the offer for the <strong>{role_title}</strong> role at {BRAND}. "
                "We genuinely appreciate the time you invested in our process, and we wish you every success in what comes next. "
                "A copy of the offer letter for your records is attached.")
    )
    if reason:
        body += _callout(f"<em>Your note to us:</em> {reason[:500]}")
    body += _callout("If your situation changes in the future, we'd love to stay in touch — please feel free to reach out directly.")
    return EmailTemplate(
        subject=f"Your response on the {role_title} offer — confirmed",
        html=_wrap("Decision recorded", f"{role_title} at {BRAND}", body,
                   "View open roles", f"{DASH_URL}/careers",
                   accent, category="employer"),
        text=_txt("Decision recorded",
                  f"Hi {first}, we've recorded your decision to decline the {role_title} offer at {BRAND}. Thank you and best of luck."),
    )


@_register("career_offer_rescinded", "Career — Offer Rescinded", "Employer",
           "Notification that the company has rescinded the offer")
def build_career_offer_rescinded_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
    reason: str = "",
) -> EmailTemplate:
    accent = "#EF4444"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("Your offer has been rescinded",
                     f"We need to withdraw our offer for <strong>{role_title}</strong> at this time.",
                     accent, "RESCINDED")
        + _lead(f"Hi {first},",
                f"After further consideration, we're writing to inform you that we must rescind the offer for the <strong>{role_title}</strong> role at {BRAND}. "
                "We know this is unwelcome news and we are genuinely sorry for the disappointment this causes.")
    )
    if reason:
        body += _callout(f"<strong>Reason:</strong> {reason[:500]}")
    body += _callout("A copy of the rescission letter is attached for your records. If you'd like to speak with us directly, please reply to this email.")
    return EmailTemplate(
        subject=f"Important update on your {role_title} offer",
        html=_wrap("Offer Rescinded", f"{role_title} at {BRAND}", body,
                   "View open roles", f"{DASH_URL}/careers",
                   accent, category="employer"),
        text=_txt("Offer Rescinded",
                  f"Hi {first}, we must rescind our offer for the {role_title} role at {BRAND}. Rescission letter attached."),
    )


@_register("career_offer_expired", "Career — Offer Expired", "Employer",
           "Automatic notification when a sent offer expires without response")
def build_career_offer_expired_email(
    applicant_name: str = "Alex Johnson",
    role_title: str = "Software Engineer",
) -> EmailTemplate:
    accent = "#B45309"
    first = (applicant_name.strip().split()[0] if applicant_name.strip() else "there")
    body = (
        _alert_panel("Your offer has expired",
                     f"We didn't receive a response to your offer for <strong>{role_title}</strong>.",
                     accent, "EXPIRED")
        + _lead(f"Hi {first},",
                f"The response window on your offer for the <strong>{role_title}</strong> role at {BRAND} has closed. "
                "If you're still interested, or if something got in the way of responding, please reply to this email — "
                "we'd love to hear from you and can re-issue the offer if it's still a good fit on both sides.")
    )
    return EmailTemplate(
        subject=f"Your {role_title} offer has expired — we'd still love to talk",
        html=_wrap("Offer Expired", f"{role_title} at {BRAND}", body,
                   "Reply to re-engage", "mailto:talent@realaicoach.app",
                   accent, category="employer"),
        text=_txt("Offer Expired",
                  f"Hi {first}, your offer for {role_title} at {BRAND} has expired. Reply if you'd like to re-engage."),
    )


@_register("career_offer_letters_review", "Career — Offer Letter Review Pack", "Employer",
           "Admin design-review email carrying all 4 offer letter PDF variants")
def build_career_offer_letters_review_email(
    admin_name: str = "Admin",
    sample_candidate: str = "Alex Johnson",
    sample_role: str = "Senior AI Engineer",
) -> EmailTemplate:
    accent = "#0F766E"
    first = (admin_name.strip().split()[0] if admin_name.strip() else "there")
    letters = [
        ("Offer letter", "original", "Full offer with compensation hero, countdown ribbon and portal QR"),
        ("Rescinded letter", "rescinded", "Formal rescission notice, red watermark and legal-effect clause"),
        ("Expired letter", "expired", "Expiration notice, amber watermark and re-engagement goodwill clause"),
        ("Rejected letter", "declined", "Respectfully-declined closure card with talent-network goodwill"),
    ]
    rows = "".join(
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;white-space:nowrap;'>{i + 1}. {name}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#475569;font-size:13px;'>{desc}</td></tr>"
        for i, (name, _variant, desc) in enumerate(letters)
    )
    body = (
        _alert_panel("Letter Design Review Pack",
                     "All 4 job offer letter PDF variants are attached to this email.",
                     accent, "4 PDFs ATTACHED")
        + _lead(f"Hi {first},",
                f"Attached are the four offer letter variants generated by the live pdf-v15 letter engine using sample "
                f"candidate data (<strong>{sample_candidate} — {sample_role}</strong>) and your current offer branding.")
        + f"<table style='border-collapse:collapse;width:100%;margin:6px 0 4px;'>{rows}</table>"
        + _callout("These are sample documents for design review only — no offer records were created or modified.")
    )
    return EmailTemplate(
        subject=f"Offer Letter Design Review Pack — 4 Letter Variants (PDF) — {BRAND}",
        html=_wrap("Offer Letter Review Pack", f"pdf-v15 letter engine — {BRAND}", body,
                   "Open Offer Studio", f"{DASH_URL}/admin/offer-studio",
                   accent, category="employer"),
        text=_txt("Offer Letter Design Review Pack",
                  f"Hi {first}, attached are the 4 offer letter PDF variants (offer, rescinded, expired, rejected) "
                  f"generated from sample data ({sample_candidate} - {sample_role}). Design review only."),
    )
# ── CSAT Survey Templates ───────────────────────────────

@_register("csat_survey", "CSAT Survey", "Engagement", "Customer satisfaction survey invitation")
def build_csat_survey_email(
    user_name: str = "Alex",
    survey_url: str = "",
) -> EmailTemplate:
    first = user_name.strip().split()[0] if user_name.strip() else "there"
    body = f"""{_alert_panel("We Value Your Feedback", "Help us improve by sharing your experience.", "#8B5CF6", "FEEDBACK")}
    {_lead(f"Hi {first},", "Your opinion matters to us! Please take a moment to complete our satisfaction survey. It only takes 2 minutes.")}
    {_callout("Your responses are anonymous and help us deliver a better experience for everyone.")}"""
    return EmailTemplate(
        subject=f"We Value Your Feedback — {BRAND} Satisfaction Survey",
        html=_wrap("Share Your Feedback", "Help us improve your experience", body, "Take the Survey", survey_url or f"{DASH_URL}/survey", "#8B5CF6", category="engagement"),
        text=_txt("CSAT Survey", f"Hi {first}, please take 2 minutes to complete our satisfaction survey: {survey_url}"),
    )


@_register("csat_reminder", "CSAT Reminder", "Engagement", "Reminder for incomplete CSAT survey")
def build_csat_reminder_email(
    survey_url: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Quick Reminder", "Your feedback still matters — the survey only takes 2 minutes.", "#F59E0B", "REMINDER")}
    {_lead("Your feedback still matters", "We noticed you have not completed the satisfaction survey yet. We would love to hear from you!")}
    {_callout("Every response helps us improve. The survey is short and your answers are anonymous.")}"""
    return EmailTemplate(
        subject="Quick Reminder — Your Feedback Still Matters",
        html=_wrap("Survey Reminder", "Complete your satisfaction survey", body, "Complete Survey Now", survey_url or f"{DASH_URL}/survey", "#F59E0B", category="engagement"),
        text=_txt("CSAT Reminder", f"Quick reminder: please complete our satisfaction survey. {survey_url}"),
    )


# ── Auth Magic Link ──────────────────────────────────────

@_register("magic_link", "Magic Login Link", "Security", "Passwordless magic link login email")
def build_magic_link_email(
    magic_url: str = "",
    expiry_minutes: int = 15,
) -> EmailTemplate:
    body = f"""{_alert_panel("Magic Login Link", f"Click the button below to sign in instantly. This link expires in {expiry_minutes} minutes.", "#3B82F6", "SECURE LOGIN")}
    {_lead("Sign in with one click", f"You requested a passwordless login link for your {BRAND} account. Click below to sign in securely.")}
    {_callout(f"This link will expire in {expiry_minutes} minutes. If you did not request this, you can safely ignore this email.")}"""
    return EmailTemplate(
        subject=f"Your Magic Login Link — {BRAND}",
        html=_wrap("Magic Login", "Sign in with one click", body, "Sign In Now", magic_url or f"{DASH_URL}/auth/login", "#3B82F6", category="security"),
        text=_txt("Magic Login", f"Sign in with this link (expires in {expiry_minutes}min): {magic_url}"),
    )


# ── IDV Re-Verification Available ────────────────────────

@_register("idv_reverification", "IDV Re-Verification", "Security", "Sent when the 14-day re-verification waiting period ends")
def build_idv_reverification_email(
    user_name: str = "Alex",
) -> EmailTemplate:
    body = f"""{_alert_panel("Re-Verification Available", "Your 14-day waiting period has passed. You can now resubmit your identity documents.", "#3B82F6", "ID CHECKER")}
    {_lead(f"Hi {user_name},", f"Your 14-day waiting period has passed. You can now resubmit your identity documents for verification on {BRAND}.")}
    {_callout("Please ensure your documents are clear and readable for the best chance of approval.")}"""
    return EmailTemplate(
        subject=f"ID Re-Verification Now Available — {BRAND}",
        html=_wrap("Re-Verification", "Submit your documents again", body, "Verify Now", f"{DASH_URL}/settings?tab=verification", "#3B82F6", category="security"),
        text=_txt("IDV Re-Verification", f"Hi {user_name}, your 14-day waiting period has passed. You can now resubmit your identity documents."),
    )


# ── Calendar Event Emails ────────────────────────────────

@_register("calendar_event_cancelled", "Event Cancelled", "Notifications", "Sent when a calendar event is cancelled")
def build_calendar_event_cancelled_email(
    event_title: str = "Team Sync",
    event_date: str = "March 15, 2026",
    user_name: str = "Alex",
) -> EmailTemplate:
    body = f"""{_alert_panel("Event Cancelled", f"<strong>{event_title}</strong> scheduled for {event_date} has been cancelled.", "#EF4444", "CANCELLED")}
    {_lead(f"Hi {user_name},", f"The event <strong>{event_title}</strong> has been cancelled by the organizer.")}
    {_info_table([_info_row("Event", event_title), _info_row("Date", event_date), _info_row("Status", "Cancelled", "#EF4444")])}"""
    return EmailTemplate(
        subject=f"Cancelled: {event_title} on {event_date}",
        html=_wrap("Event Cancelled", f"{event_title} has been cancelled", body, "View Calendar", f"{DASH_URL}/calendar", "#EF4444", category="notifications"),
        text=_txt("Event Cancelled", f"Hi {user_name}, {event_title} on {event_date} has been cancelled."),
    )


@_register("calendar_event_rescheduled", "Event Rescheduled", "Notifications", "Sent when a calendar event is rescheduled")
def build_calendar_event_rescheduled_email(
    event_title: str = "Team Sync",
    new_date: str = "March 20, 2026",
    user_name: str = "Alex",
) -> EmailTemplate:
    body = f"""{_alert_panel("Event Rescheduled", f"<strong>{event_title}</strong> has been moved to a new date.", "#F59E0B", "RESCHEDULED")}
    {_lead(f"Hi {user_name},", f"The event <strong>{event_title}</strong> has been rescheduled.")}
    {_info_table([_info_row("Event", event_title), _info_row("New Date", new_date, "#10B981"), _info_row("Status", "Rescheduled", "#F59E0B")])}"""
    return EmailTemplate(
        subject=f"Rescheduled: {event_title} moved to {new_date}",
        html=_wrap("Event Rescheduled", f"{event_title} new date: {new_date}", body, "View Calendar", f"{DASH_URL}/calendar", "#F59E0B", category="notifications"),
        text=_txt("Event Rescheduled", f"Hi {user_name}, {event_title} rescheduled to {new_date}."),
    )


@_register("meeting_reminder", "Meeting Reminder", "Notifications", "Sent as a reminder before a scheduled meeting")
def build_meeting_reminder_email_notifications(
    participant_name: str = "Alex",
    other_name: str = "Sarah",
    event_time: str = "10:00 AM",
    event_date: str = "March 15, 2026",
    is_host: bool = False,
    cancel_url: str = "",
) -> EmailTemplate:
    role = "hosting" if is_host else "attending"
    body = f"""{_alert_panel("Meeting Reminder", f"You have an upcoming meeting with <strong>{other_name}</strong>.", "#3B82F6", "REMINDER")}
    {_lead(f"Hi {participant_name},", f"Reminder: you are {role} a meeting with <strong>{other_name}</strong>.")}
    {_info_table([_info_row("With", other_name), _info_row("Date", event_date), _info_row("Time", event_time)])}"""
    cta_url = cancel_url or f"{DASH_URL}/calendar"
    return EmailTemplate(
        subject=f"Reminder: Meeting with {other_name}",
        html=_wrap("Meeting Reminder", f"Meeting with {other_name} at {event_time}", body, "View Details", cta_url, category="notifications"),
        text=_txt("Meeting Reminder", f"Hi {participant_name}, reminder: meeting with {other_name} on {event_date} at {event_time}."),
    )


# ── Admin Payment Failure Alert ──────────────────────────

@_register("admin_payment_failure", "Admin Payment Failure", "Billing", "Internal alert when a customer payment fails")
def build_admin_payment_failure_alert_email(
    user_email: str = "user@example.com",
    plan: str = "Premium",
    amount: str = "$15.99",
    error: str = "Card declined",
    provider: str = "Stripe",
) -> EmailTemplate:
    body = f"""{_alert_panel("Payment Failure Alert", "A customer payment has failed. Review and take action.", "#EF4444", "PAYMENT ALERT")}
    {_info_table([_info_row("Customer", user_email), _info_row("Plan", plan), _info_row("Amount", amount, "#EF4444"), _info_row("Error", error), _info_row("Provider", provider)])}"""
    return EmailTemplate(
        subject=f"Payment Failure: {user_email} — {plan} ({amount})",
        html=_wrap("Payment Failure", f"Customer payment failed: {amount}", body, "View Payment Dashboard", f"{DASH_URL}/admin-console?tab=payments", "#EF4444", category="billing"),
        text=_txt("Payment Failure", f"Customer {user_email} payment failed. Plan: {plan}, Amount: {amount}, Error: {error}."),
    )


# ── Security Scan Alert ──────────────────────────────────

@_register("security_scan_alert", "Security Scan Alert", "Security", "Nightly security posture scan degradation alert")
def build_security_scan_alert_email(
    score: int = 85,
    grade: str = "B",
    degraded_count: int = 2,
    degraded_checks: list = None,
) -> EmailTemplate:
    accent = "#EF4444" if score < 70 else "#F59E0B" if score < 90 else "#10B981"
    rows = [_info_row("Security Score", f"{score}%", accent), _info_row("Grade", grade, accent), _info_row("Degraded Checks", str(degraded_count), "#EF4444")]
    for check in (degraded_checks or [])[:5]:
        if isinstance(check, dict):
            rows.append(_info_row(check.get("name", "Check"), check.get("status", "FAIL"), "#EF4444"))
        elif isinstance(check, str):
            rows.append(_info_row("Issue", check, "#EF4444"))
    body = f"""{_alert_panel(f"Security Score: {score}% ({grade})", f"{degraded_count} check(s) have degraded since the last scan.", accent, "SECURITY SCAN")}
    {_info_table(rows)}"""
    return EmailTemplate(
        subject=f"Security Alert: {degraded_count} issue(s) detected — Score {score}% ({grade})",
        html=_wrap("Security Alert", f"Score {score}% — {degraded_count} degraded checks", body, "View Security Dashboard", f"{DASH_URL}/admin-console?tab=security", accent, category="security"),
        text=_txt("Security Alert", f"Score: {score}% ({grade}). {degraded_count} degraded checks detected."),
    )


# ── Server Anomaly Alert ─────────────────────────────────

@_register("server_anomaly_alert", "Server Anomaly Alert", "Security", "Real-time anomaly detection alert to admins")
def build_server_anomaly_alert_email(
    anomaly_count: int = 1,
    anomaly_details: str = "Unusual traffic pattern detected",
) -> EmailTemplate:
    body = f"""{_alert_panel(f"{anomaly_count} Anomaly Detected", "The real-time monitoring system has flagged unusual activity.", "#EF4444", "ANOMALY")}
    {_lead("Immediate attention required", anomaly_details[:500])}"""
    return EmailTemplate(
        subject=f"Security Alert: {anomaly_count} Anomal{'y' if anomaly_count == 1 else 'ies'} Detected",
        html=_wrap("Anomaly Alert", f"{anomaly_count} anomalies flagged", body, "View Dashboard", f"{DASH_URL}/admin-console?tab=security", "#EF4444", category="security"),
        text=_txt("Anomaly Alert", f"{anomaly_count} anomalies detected. {anomaly_details[:300]}"),
    )


# ── P0-3. Team Invite ───────────────────────────────────

@_register("team_invite", "Team Invite", "Employer", "Sent when an employer invites a team member to join")
def build_team_invite_email(
    inviter_name: str = "Sarah", company_name: str = "Acme Corp", role: str = "Team Member", invite_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">You've been invited to join a team!</p>
    <p style="margin:0 0 16px;">{inviter_name} has invited you to join <strong>{company_name}</strong> on {BRAND} as a <strong>{role}</strong>.</p>
    {_info_table([_info_row("Invited by", inviter_name), _info_row("Organization", company_name), _info_row("Role", role)])}
    {_callout("Accept this invitation to access your team's coaching dashboard, shared goals, and collaborative tools.")}"""
    return EmailTemplate(
        subject=f"{inviter_name} invited you to join {company_name} on {BRAND}",
        html=_wrap("Team Invitation", f"Join {company_name} on {BRAND}", body, "Accept Invitation", invite_link or f"{DASH_URL}/register", "#0EA5E9", category="employer"),
        text=_txt("Team Invite", f"{inviter_name} invited you to join {company_name} as {role}. Accept: {invite_link}"),
    )


# ── P0-4. Churn Winback ─────────────────────────────────

@_register("churn_winback", "Churn Winback", "Engagement", "Sent to churned/inactive users to win them back")
def build_churn_winback_email(
    user_name: str = "Alex", days_inactive: int = 30, special_offer: str = "50% off your next month"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">We miss you, {user_name}</p>
    <p style="margin:0 0 16px;">It's been {days_inactive} days since your last visit. Your coaching journey is waiting — and we've added new features since you left.</p>
    {_alert_panel("Welcome Back Offer", f"Come back today and get <strong>{special_offer}</strong>. This offer expires in 7 days.", "#F59E0B", "LIMITED")}
    <p style="margin:16px 0 6px;"><strong>What's new since you left:</strong></p>
    {_info_table([_info_row("AI Coaching", "Smarter, more personalized sessions"), _info_row("Goal Tracking", "New milestone celebrations"), _info_row("Team Features", "Collaborate with your network")])}"""
    return EmailTemplate(
        subject=f"We miss you, {user_name} — {special_offer} waiting for you",
        html=_wrap("We Miss You", f"Come back and get {special_offer}", body, "Come Back Now", f"{DASH_URL}/pricing", "#F59E0B", category="engagement"),
        text=_txt("We Miss You", f"Hi {user_name}, it's been {days_inactive} days. Come back: {special_offer}. {DASH_URL}/pricing"),
    )


# ── P0-5. Re-engagement Nudge ───────────────────────────

@_register("reengagement_nudge", "Re-engagement Nudge", "Engagement", "Periodic nudge to bring back inactive users")
def build_reengagement_nudge_email(
    user_name: str = "Alex", last_activity: str = "2 weeks ago", streak_count: int = 5
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your progress is waiting, {user_name}</p>
    <p style="margin:0 0 16px;">Your last session was <strong>{last_activity}</strong>. You were on a {streak_count}-day streak — don't let it slip!</p>
    {_callout("Just 10 minutes today can keep your momentum going. Your AI coach has a new session ready for you.", "#3B82F6")}
    <p style="margin:16px 0 6px;">{_badge("YOUR STATS", "#10B981")}</p>
    {_info_table([_info_row("Current Streak", f"{streak_count} days"), _info_row("Last Active", last_activity), _info_row("Goals in Progress", "3 active")])}"""
    return EmailTemplate(
        subject=f"Don't lose your {streak_count}-day streak, {user_name}",
        html=_wrap("Keep Going", "Your AI coach has a session ready", body, "Continue My Journey", DASH_URL, "#3B82F6", category="engagement"),
        text=_txt("Re-engagement", f"Hi {user_name}, last active {last_activity}. You had a {streak_count}-day streak. Continue: {DASH_URL}"),
    )


# ── P0-6. Invoice Document ──────────────────────────────

@_register("invoice_document", "Invoice Document", "Billing", "Branded invoice/receipt email with document reference")
def build_invoice_document_email(
    user_name: str = "Alex", invoice_number: str = "INV-2026-0001", amount: str = "$15.99",
    period: str = "Apr 2026", plan_name: str = "Premium", download_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your invoice is ready</p>
    <p style="margin:0 0 16px;">Here's your invoice for {period}. You can download a PDF copy for your records.</p>
    {_info_table([_info_row("Invoice #", invoice_number), _info_row("Period", period), _info_row("Plan", plan_name), _info_row("Amount", amount), _info_row("Status", "Paid")])}
    {_callout("This invoice is available in your billing dashboard. For tax purposes, download the PDF version using the button below.")}"""
    return EmailTemplate(
        subject=f"Invoice {invoice_number} — {amount} for {period}",
        html=_wrap("Your Invoice", f"Invoice {invoice_number} for {period}", body, "Download Invoice PDF", download_link or f"{DASH_URL}/settings/billing", "#10B981", category="billing"),
        text=_txt("Invoice", f"Invoice {invoice_number}: {amount} for {period} ({plan_name}). Download: {download_link or DASH_URL}"),
    )


# ── P1-7. Referral Reward ───────────────────────────────

@_register("referral_reward", "Referral Reward", "Engagement", "Sent when a referral converts and referrer earns a reward")
def build_referral_reward_email(
    user_name: str = "Alex", friend_name: str = "Jordan", reward: str = "1 month free Premium"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your reward is here!</p>
    <p style="margin:0 0 16px;"><strong>{friend_name}</strong> just joined {BRAND} using your referral link. Your reward has been automatically applied to your account.</p>
    {_alert_panel("Reward Activated", f"<strong>{reward}</strong> has been added to your account.", "#10B981", "EARNED")}
    {_callout("Keep sharing your referral link to earn more rewards. There's no limit to how many friends you can invite!")}"""
    return EmailTemplate(
        subject=f"You earned {reward} — {friend_name} joined {BRAND}!",
        html=_wrap("Reward Earned", f"You earned {reward}!", body, "Invite More Friends", f"{DASH_URL}/referrals", "#10B981", category="engagement"),
        text=_txt("Referral Reward", f"Hi {user_name}, {friend_name} joined! You earned {reward}."),
    )


# ── P1-8. Team Member Removed ───────────────────────────

@_register("team_member_removed", "Team Member Removed", "Employer", "Notification when an employee is removed from a team")
def build_team_member_removed_email(
    user_name: str = "Alex", company_name: str = "Acme Corp", removed_by: str = "HR Admin"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Team membership update</p>
    <p style="margin:0 0 16px;">You have been removed from <strong>{company_name}</strong>'s team on {BRAND}.</p>
    {_info_table([_info_row("Organization", company_name), _info_row("Action", "Membership ended"), _info_row("Updated by", removed_by)])}
    {_callout("Your personal account and progress remain intact. You can continue using your individual coaching features. If you believe this was an error, contact your organization's admin.")}"""
    return EmailTemplate(
        subject=f"Team membership update — {company_name}",
        html=_wrap("Team Update", f"Your membership in {company_name} has ended", body, "Go to Dashboard", DASH_URL, category="employer"),
        text=_txt("Team Removed", f"Hi {user_name}, you've been removed from {company_name}'s team by {removed_by}. Your personal account is unaffected."),
    )


# ── P1-9. Daily AI Briefing ─────────────────────────────

@_register("daily_ai_briefing", "Daily AI Briefing", "AI", "Daily AI coaching summary with progress and next steps")
def build_daily_ai_briefing_email(
    user_name: str = "Alex", date_str: str = "Apr 15, 2026", summary: str = "Great progress on communication goals",
    goals_progress: int = 3, sessions_today: int = 2, streak: int = 12
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your daily briefing — {date_str}</p>
    <p style="margin:0 0 16px;">{summary}</p>
    {_info_table([_info_row("AI Sessions Today", str(sessions_today)), _info_row("Goals in Progress", str(goals_progress)), _info_row("Current Streak", f"{streak} days")])}
    <p style="margin:16px 0 6px;">{_badge("AI INSIGHT", "#8B5CF6")}</p>
    {_callout("Your AI coach noticed you're making strong progress on leadership skills. Consider scheduling a mock interview to practice.", "#8B5CF6")}"""
    return EmailTemplate(
        subject=f"Daily Briefing: {summary[:40]} — {date_str}",
        html=_wrap("Daily AI Briefing", f"Your coaching summary for {date_str}", body, "Start Today's Session", DASH_URL, "#8B5CF6", category="ai"),
        text=_txt("Daily Briefing", f"Hi {user_name}, {date_str}: {summary}. Sessions: {sessions_today}, Streak: {streak} days."),
    )


# ── P1-10. Certificate Earned ────────────────────────────

@_register("certificate_earned", "Certificate Earned", "AI", "Celebration email when a user earns a certificate")
def build_certificate_earned_email(
    user_name: str = "Alex", course_name: str = "Leadership Foundations", certificate_id: str = "CERT-2026-001",
    completion_date: str = "Apr 15, 2026"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Congratulations, {user_name}!</p>
    <p style="margin:0 0 16px;">You've earned a certificate for completing <strong>{course_name}</strong>. This is a significant achievement — well done!</p>
    {_alert_panel("Certificate Issued", f"Certificate ID: <strong>{certificate_id}</strong><br/>Completed: {completion_date}", "#F59E0B", "ACHIEVED")}
    {_callout("Your certificate is now available in your Learning Hub. You can download it as a PDF or share it on LinkedIn.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Certificate Earned: {course_name}",
        html=_wrap("Certificate Earned", f"You completed {course_name}!", body, "View Certificate", f"{DASH_URL}/certificates", "#F59E0B", category="ai"),
        text=_txt("Certificate", f"Congrats {user_name}! Certificate for {course_name} (ID: {certificate_id}, {completion_date})."),
    )


# ── P1-11. Booking Rescheduled ───────────────────────────

@_register("booking_rescheduled", "Booking Rescheduled", "Calendar", "Sent when a meeting is rescheduled")
def build_booking_rescheduled_email(
    user_name: str = "Alex", host_name: str = "Coach Sarah", old_date: str = "Apr 15, 2026 at 2:00 PM",
    new_date: str = "Apr 17, 2026 at 3:00 PM", meeting_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Meeting rescheduled</p>
    <p style="margin:0 0 16px;">Your meeting with <strong>{host_name}</strong> has been rescheduled.</p>
    {_info_table([_info_row("Previous Time", f"<s>{old_date}</s>"), _info_row("New Time", f"<strong>{new_date}</strong>"), _info_row("Host", host_name)])}
    {_callout("The new time has been updated on your calendar. If this doesn't work for you, you can reschedule again from your dashboard.")}"""
    return EmailTemplate(
        subject=f"Meeting rescheduled with {host_name} — {new_date}",
        html=_wrap("Meeting Rescheduled", f"New time: {new_date}", body, "View Meeting Details", meeting_link or f"{DASH_URL}/calendar", category="calendar"),
        text=_txt("Rescheduled", f"Meeting with {host_name} moved from {old_date} to {new_date}."),
    )


# ── P1-12. System Alert Admin ────────────────────────────

@_register("system_alert_admin", "System Alert (Admin)", "Notifications", "Unified admin alert for system events and anomalies")
def build_system_alert_admin_email(
    alert_type: str = "Performance Degradation", severity: str = "HIGH", description: str = "API response time exceeded 500ms threshold",
    component: str = "API Gateway", timestamp: str = "2026-04-15 14:30 UTC"
) -> EmailTemplate:
    sev_color = "#EF4444" if severity == "CRITICAL" else "#F59E0B" if severity == "HIGH" else "#3B82F6"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">System Alert: {alert_type}</p>
    <p style="margin:0 0 16px;">{_badge(severity, sev_color)} A system event requires your attention.</p>
    {_info_table([_info_row("Alert", alert_type), _info_row("Severity", severity), _info_row("Component", component), _info_row("Time", timestamp)])}
    <p style="margin:16px 0 8px;"><strong>Details:</strong></p>
    {_callout(description, sev_color)}"""
    return EmailTemplate(
        subject=f"[{severity}] {alert_type} — {component}",
        html=_wrap("System Alert", f"{severity}: {alert_type}", body, "View Admin Console", f"{DASH_URL}/admin-console", sev_color, category="notifications"),
        text=_txt("System Alert", f"[{severity}] {alert_type}\nComponent: {component}\nTime: {timestamp}\n{description}"),
    )


@_register("user_notification_alert", "User Notification Alert", "Notifications", "User-facing notification email with notification-center CTA")
def build_user_notification_alert_email(
    alert_title: str = "New Notification",
    message: str = "You have a new update.",
    context_type: str = "notification",
    action_url: str = "",
    timestamp: str = "",
) -> EmailTemplate:
    action_raw = (action_url or "").strip()
    if not action_raw:
        safe_action = f"{DASH_URL}/notifications"
    elif action_raw.startswith(("http://", "https://")):
        safe_action = action_raw
    else:
        safe_action = f"{DASH_URL}{action_raw if action_raw.startswith('/') else '/' + action_raw}"
    event_time = (timestamp or "").strip() or "Just now"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">{alert_title}</p>
    <p style="margin:0 0 16px;">{_badge("INFO", "#2563EB")} Here's an update from your account activity.</p>
    {_info_table([_info_row("Type", context_type), _info_row("Time", event_time)])}
    {_callout(message, "#2563EB")}"""
    return EmailTemplate(
        subject=alert_title,
        html=_wrap(
            "Notification",
            alert_title,
            body,
            "View Notifications",
            safe_action,
            "#2563EB",
            category="notifications",
        ),
        text=_txt("Notification", f"{alert_title}\nType: {context_type}\nTime: {event_time}\n{message}"),
    )


# ── GTEC Regression Alert (dedicated V7 template) ─────────
# Fired by utils/gtec_alerts.py after the scheduled Safe-Auto-Run scan
# detects a pass-rate drop, new white-screen route, or new runtime error.
# Historically used raw inline HTML via `system_alert_admin`, producing a
# white inner card on the dark V7 chrome — this dedicated builder renders
# the body through V7 primitives so the card theme matches the shell.

@_register("gtec_regression_alert", "GTEC Regression Alert", "Notifications", "Ops alert when GTEC Safe-Auto-Run detects a regression (pass-rate drop, new white-screen, or new runtime error)")
def build_gtec_regression_alert_email(
    reasons: list | None = None,
    pass_rate: float = 100.0,
    failing: int = 0,
    scans: int = 0,
    new_white_screens: list | None = None,
    new_runtime_errors: list | None = None,
    report_url: str = "",
) -> EmailTemplate:
    reasons = reasons or ["Test alert triggered manually by admin@realaicoach.app"]
    new_white_screens = new_white_screens or []
    new_runtime_errors = new_runtime_errors or []
    report_url = (report_url or f"{DASH_URL}/ops-route-health").rstrip("/")
    if not report_url.endswith("/ops-route-health"):
        report_url = report_url.rstrip("/") + "/ops-route-health"

    severity_color = "#EF4444" if any("drop" in r.lower() or "new" in r.lower() for r in reasons) else "#F59E0B"

    reasons_items = "".join(
        f'<li style="margin:0 0 6px;color:#374151;font-size:13px;line-height:1.7;">{r}</li>' for r in reasons
    )
    reasons_block = (
        f'<ul class="em-list" style="margin:0 0 16px 20px;padding:0;">{reasons_items}</ul>'
    )

    def _route_list(title: str, routes: list, color: str) -> str:
        if not routes:
            return ""
        items = "".join(
            f'<li style="margin:0 0 4px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#0F172A;word-break:break-all;">{r}</li>'
            for r in routes[:20]
        )
        more = (
            f'<p style="margin:6px 0 0;color:#64748B;font-size:11px;">…and {len(routes) - 20} more</p>'
            if len(routes) > 20 else ""
        )
        return (
            f'<p style="margin:16px 0 6px;"><strong style="color:{color};">{title}</strong></p>'
            f'<div class="em-callout em-force-light-card" style="background:#FFFFFF;border:1px solid {_color_tint(color, 0x35)};border-left:3px solid {color};border-radius:12px;padding:14px 18px;margin:0 0 14px;">'
            f'<ul style="margin:0 0 0 18px;padding:0;">{items}</ul>{more}</div>'
        )

    body = f"""{_lead("GTEC regression detected", "The Safe-Auto-Run scan just completed and flagged one or more regressions. Please review below and open the Route Health report for details.")}
    <p style="margin:0 0 12px;">{_badge("REGRESSION", severity_color)}</p>
    {reasons_block}
    {_info_table([
        _info_row("Pass rate", f"{pass_rate:.1f}%", "#10B981" if pass_rate >= 95 else severity_color),
        _info_row("Failing scans", str(failing), severity_color if failing else "#0F172A"),
        _info_row("Total scans", str(scans)),
    ])}
    {_route_list("New white-screen routes", new_white_screens, "#EF4444")}
    {_route_list("New runtime-error routes", new_runtime_errors, "#F59E0B")}
    {_callout("Review the full scan output in the Route Health dashboard. Rollback or hotfix the affected build before the next auto-run window.", severity_color)}"""

    return EmailTemplate(
        subject="GTEC regression detected — action required",
        html=_wrap(
            "GTEC Regression",
            f"{pass_rate:.1f}% pass · {failing} failing / {scans} scans",
            body,
            "Open Route Health report",
            report_url,
            severity_color,
            category="notifications",
        ),
        text=_txt(
            "GTEC Regression Detected",
            "The Safe-Auto-Run scan flagged regressions:\n"
            + "\n".join(f"- {r}" for r in reasons)
            + f"\n\nPass rate: {pass_rate:.1f}% · Failing: {failing} / Scans: {scans}",
            "Open Route Health",
            report_url,
        ),
    )


# ── P1-13. Weekly Performance Report ─────────────────────

@_register("weekly_performance_report", "Weekly Performance Report", "Engagement", "Weekly coaching progress report with stats and milestones")
def build_weekly_performance_report_email(
    user_name: str = "Alex", week_label: str = "Apr 7–13, 2026", sessions_count: int = 8,
    goals_completed: int = 2, streak: int = 14, improvement: str = "+15%"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your week in review</p>
    <p style="margin:0 0 16px;">Here's your coaching progress for <strong>{week_label}</strong>.</p>
    {_info_table([_info_row("AI Sessions", str(sessions_count)), _info_row("Goals Completed", str(goals_completed)), _info_row("Streak", f"{streak} days"), _info_row("Improvement", improvement)])}
    <p style="margin:16px 0 6px;">{_badge("WEEKLY INSIGHT", "#10B981")}</p>
    {_callout("You're in the top 20% of active users this week. Keep up the momentum — consistency is the key to lasting growth.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Weekly Report: {sessions_count} sessions, {goals_completed} goals completed — {week_label}",
        html=_wrap("Weekly Report", f"Your progress for {week_label}", body, "View Full Report", f"{DASH_URL}/progress", "#10B981", category="engagement"),
        text=_txt("Weekly Report", f"Hi {user_name}, {week_label}: {sessions_count} sessions, {goals_completed} goals, {streak}-day streak, {improvement} improvement."),
    )


# ── P1-14. Data Export Ready ─────────────────────────────

@_register("data_export_ready", "Data Export Ready", "Account", "GDPR notification when user data export is ready for download")
def build_data_export_ready_email_account(
    user_name: str = "Alex", export_type: str = "Full Account Data", download_link: str = "",
    expiry: str = "7 days"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your data export is ready</p>
    <p style="margin:0 0 16px;">Your requested data export (<strong>{export_type}</strong>) has been generated and is ready for download.</p>
    {_info_table([_info_row("Export Type", export_type), _info_row("Format", "ZIP (JSON + CSV)"), _info_row("Available For", expiry)])}
    {_callout(f"This download link expires in <strong>{expiry}</strong>. For security, the file is encrypted and requires your account credentials to access.", "#3B82F6")}"""
    return EmailTemplate(
        subject=f"Your data export is ready — Download within {expiry}",
        html=_wrap("Data Export Ready", "Your data is ready for download", body, "Download My Data", download_link or f"{DASH_URL}/settings/data", "#3B82F6", category="account"),
        text=_txt("Data Export", f"Hi {user_name}, your {export_type} export is ready. Download within {expiry}: {download_link or DASH_URL}"),
    )


# ── P1-15. Ticket Escalated ──────────────────────────────

@_register("ticket_escalated", "Ticket Escalated", "Support", "Notification when a support ticket is escalated to a higher tier")
def build_ticket_escalated_email(
    user_name: str = "Alex", ticket_id: str = "TKT-0042", subject_line: str = "Billing Issue",
    escalated_to: str = "Senior Support", reason: str = "Requires specialist attention"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your ticket has been escalated</p>
    <p style="margin:0 0 16px;">To ensure you get the best help, your ticket has been escalated to <strong>{escalated_to}</strong>.</p>
    {_info_table([_info_row("Ticket", f"#{ticket_id}"), _info_row("Subject", subject_line), _info_row("Escalated To", escalated_to), _info_row("Reason", reason)])}
    {_callout("A specialist will review your ticket and respond as soon as possible. You'll receive a notification when there's an update.")}"""
    return EmailTemplate(
        subject=f"Ticket #{ticket_id} escalated to {escalated_to}",
        html=_wrap("Ticket Escalated", f"Your ticket is now with {escalated_to}", body, "View Ticket", f"{DASH_URL}/my-tickets", category="support"),
        text=_txt("Escalated", f"Ticket #{ticket_id} ({subject_line}) escalated to {escalated_to}. Reason: {reason}."),
    )


# ── P2-16. Team Role Changed ─────────────────────────────

@_register("team_role_changed", "Team Role Changed", "Employer", "Notification when an employee's role is changed")
def build_team_role_changed_email(
    user_name: str = "Alex", company_name: str = "Acme Corp", old_role: str = "Team Member",
    new_role: str = "Team Lead", changed_by: str = "HR Admin"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your role has been updated</p>
    <p style="margin:0 0 16px;">Your role in <strong>{company_name}</strong> has been changed.</p>
    {_info_table([_info_row("Organization", company_name), _info_row("Previous Role", old_role), _info_row("New Role", new_role), _info_row("Updated by", changed_by)])}
    {_callout("Your access permissions have been updated to match your new role. If you have questions, contact your organization's admin.")}"""
    return EmailTemplate(
        subject=f"Role updated: {new_role} at {company_name}",
        html=_wrap("Role Updated", f"You're now {new_role} at {company_name}", body, "View Team Dashboard", f"{DASH_URL}/team", category="employer"),
        text=_txt("Role Changed", f"Hi {user_name}, your role at {company_name} changed from {old_role} to {new_role} by {changed_by}."),
    )


# ── P2-17. Session Expired ──────────────────────────────

@_register("session_expired", "Session Expired", "Security", "Notification when a user's session is terminated due to security policy")
def build_session_expired_email(
    user_name: str = "Alex", reason: str = "Security policy timeout", device: str = "Chrome on Windows",
    timestamp: str = "Apr 15, 2026 at 2:30 PM UTC"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Session ended for security</p>
    <p style="margin:0 0 16px;">Your session was terminated as part of our security protocols. Please sign in again to continue.</p>
    {_info_table([_info_row("Reason", reason), _info_row("Device", device), _info_row("Time", timestamp)])}
    {_callout("If you didn't expect this, someone may have accessed your account. Change your password immediately and enable two-factor authentication.", "#EF4444")}"""
    return EmailTemplate(
        subject="Session ended — Please sign in again",
        html=_wrap("Session Expired", "Your session was terminated for security", body, "Sign In Again", f"{DASH_URL}/auth/login", "#EF4444", category="security"),
        text=_txt("Session Expired", f"Hi {user_name}, session ended ({reason}) on {device} at {timestamp}. Sign in: {DASH_URL}/auth/login"),
    )


# ── P2-18. Goal Achieved ────────────────────────────────

@_register("goal_achieved", "Goal Achieved", "AI", "Celebration email when a user achieves a coaching goal")
def build_goal_achieved_email(
    user_name: str = "Alex", goal_name: str = "Complete 10 AI Coaching Sessions", category_name: str = "Professional Growth",
    days_to_complete: int = 14
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Goal achieved!</p>
    <p style="margin:0 0 16px;">Congratulations, {user_name}! You've completed your goal:</p>
    {_alert_panel(goal_name, f"Category: {category_name} — Completed in {days_to_complete} days", "#10B981", "COMPLETED")}
    {_callout("This is a real achievement. Your consistency and dedication are paying off. Ready to set your next goal?", "#10B981")}"""
    return EmailTemplate(
        subject=f"Goal Achieved: {goal_name}",
        html=_wrap("Goal Achieved", f"You completed: {goal_name}", body, "Set Next Goal", f"{DASH_URL}/goals", "#10B981", category="ai"),
        text=_txt("Goal Achieved", f"Congrats {user_name}! You completed '{goal_name}' in {days_to_complete} days. Set next: {DASH_URL}/goals"),
    )


# ── P2-19. Weekly Hiring Report ──────────────────────────

@_register("weekly_hiring_report", "Weekly Hiring Report", "Hiring", "Weekly hiring pipeline summary for employers")
def build_weekly_hiring_report_email(
    user_name: str = "HR Admin", week_label: str = "Apr 7–13, 2026", new_applicants: int = 24,
    interviews_scheduled: int = 8, offers_sent: int = 2, pipeline_total: int = 45
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Hiring Report — {week_label}</p>
    <p style="margin:0 0 16px;">Here's your weekly hiring pipeline summary.</p>
    {_info_table([_info_row("New Applicants", str(new_applicants)), _info_row("Interviews Scheduled", str(interviews_scheduled)), _info_row("Offers Sent", str(offers_sent)), _info_row("Total in Pipeline", str(pipeline_total))])}
    <p style="margin:16px 0 6px;">{_badge("HIRING INSIGHT", "#0EA5E9")}</p>
    {_callout(f"Your pipeline has {pipeline_total} active candidates. Consider reviewing applicants who've been waiting more than 7 days for a response.", "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"Weekly Hiring Report: {new_applicants} new applicants, {interviews_scheduled} interviews — {week_label}",
        html=_wrap("Hiring Report", f"Pipeline summary for {week_label}", body, "View Hiring Dashboard", f"{DASH_URL}/hiring", "#0EA5E9", category="hiring"),
        text=_txt("Hiring Report", f"{week_label}: {new_applicants} applicants, {interviews_scheduled} interviews, {offers_sent} offers, {pipeline_total} total pipeline."),
    )




# ══════════════════════════════════════════════════════════════════════════
# PRODUCTION-CRITICAL TEMPLATES — BATCH 2 (15 new — v7 enforced)
# ══════════════════════════════════════════════════════════════════════════


# ── P0-2. Booking Confirmed (Host) ──────────────────────

@_register("booking_confirmed_host", "Booking Confirmed (Host)", "Calendar", "Sent to the host when a guest books a meeting")
def build_booking_confirmed_host_email(
    host_name: str = "Coach Sarah", guest_name: str = "Alex", guest_email: str = "alex@example.com",
    date_str: str = "Apr 17, 2026 at 3:00 PM", meeting_type: str = "Coaching Session", meeting_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">New booking received!</p>
    <p style="margin:0 0 16px;"><strong>{guest_name}</strong> has booked a session with you.</p>
    {_info_table([_info_row("Guest", guest_name), _info_row("Email", guest_email), _info_row("Date & Time", date_str), _info_row("Type", meeting_type)])}
    {_callout("This meeting has been added to your calendar. You'll receive a reminder before the session starts.")}"""
    return EmailTemplate(
        subject=f"New booking: {guest_name} — {date_str}",
        html=_wrap("New Booking", f"{guest_name} booked a session with you", body, "View Booking", meeting_link or f"{DASH_URL}/calendar", category="calendar"),
        text=_txt("New Booking", f"{guest_name} ({guest_email}) booked {meeting_type} on {date_str}."),
    )


# ── P0-3. Annual Receipt Summary ─────────────────────────

@_register("annual_receipt_summary", "Annual Receipt Summary", "Billing", "Year-end receipt summary for tax purposes")
def build_annual_receipt_summary_email(
    user_name: str = "Alex", year: str = "2025", total_amount: str = "$191.88",
    receipt_count: int = 12, download_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your {year} receipt summary is ready</p>
    <p style="margin:0 0 16px;">Here's your annual payment summary for tax and accounting purposes.</p>
    {_info_table([_info_row("Tax Year", year), _info_row("Total Paid", total_amount, "#10B981"), _info_row("Receipts", str(receipt_count)), _info_row("Format", "PDF + CSV")])}
    {_callout(f"This summary includes all {receipt_count} payments made during {year}. Download the PDF for your tax records.", "#10B981")}"""
    return EmailTemplate(
        subject=f"Your {year} Annual Receipt Summary — {receipt_count} Receipts ({total_amount})",
        html=_wrap("Annual Receipts", f"Your {year} payment summary", body, "Download Summary", download_link or f"{DASH_URL}/settings/billing", "#10B981", category="billing"),
        text=_txt("Annual Receipts", f"{year} summary: {receipt_count} receipts, {total_amount} total. Download: {download_link or DASH_URL}"),
    )


# ── P0-4. Ticket Reply (Agent) ───────────────────────────

@_register("ticket_reply_agent", "Ticket Reply (Agent)", "Support", "Sent when a support agent replies to a user ticket")
def build_ticket_reply_agent_email(
    user_name: str = "Alex", ticket_id: str = "TKT-0042", ticket_subject: str = "Billing Issue",
    agent_name: str = "Support Team", reply_preview: str = "Thank you for reaching out. We've reviewed your issue and..."
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">New reply on your ticket</p>
    <p style="margin:0 0 16px;"><strong>{agent_name}</strong> responded to your ticket.</p>
    {_info_table([_info_row("Ticket", f"#{ticket_id}"), _info_row("Subject", ticket_subject), _info_row("From", agent_name)])}
    <div class="em-force-light-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:16px 18px;margin:18px 0;">
      <p style="margin:0;color:#374151;font-size:13px;line-height:1.7;">{reply_preview}</p>
    </div>
    {_callout("Reply directly to continue the conversation, or view the full thread in your dashboard.")}"""
    return EmailTemplate(
        subject=f"Re: {ticket_subject} [#{ticket_id}]",
        html=_wrap("Ticket Reply", f"{agent_name} replied to #{ticket_id}", body, "View Full Thread", f"{DASH_URL}/my-tickets", category="support"),
        text=_txt("Ticket Reply", f"Re: {ticket_subject} [#{ticket_id}]\nFrom: {agent_name}\n{reply_preview}"),
    )


# ── P0-5. Security Spike Alert ──────────────────────────

@_register("security_spike_alert", "Security Spike Alert", "Security", "Real-time alert for anomaly spikes or service recovery")
def build_security_spike_alert_email(
    alert_type: str = "SPIKE", description: str = "560 anomalies detected in the last hour",
    severity: str = "CRITICAL", timestamp: str = "2026-04-15 14:30 UTC", status: str = "Active"
) -> EmailTemplate:
    sev_color = "#EF4444" if severity == "CRITICAL" else "#F59E0B" if severity == "HIGH" else "#10B981"
    is_recovery = alert_type == "RECOVERED"
    badge_text = "RESOLVED" if is_recovery else alert_type
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Security {alert_type.title()}</p>
    {_alert_panel(description, f"Status: {status} — Detected at {timestamp}", sev_color, badge_text)}
    {_info_table([_info_row("Type", alert_type), _info_row("Severity", severity, sev_color), _info_row("Status", status), _info_row("Time", timestamp)])}
    {_callout("Review the security dashboard for full details and recommended actions.", sev_color)}"""
    return EmailTemplate(
        subject=f"[{alert_type}] {description[:60]}",
        html=_wrap("Security Alert", f"{severity}: {alert_type}", body, "View Security Dashboard", f"{DASH_URL}/admin-console", sev_color, category="security"),
        text=_txt("Security Alert", f"[{alert_type}] {description}\nSeverity: {severity}, Status: {status}, Time: {timestamp}"),
    )


# ── P0-6. Direct Message Notification ────────────────────

@_register("direct_message_notification", "Direct Message", "Communication", "Notification when a user receives a direct message")
def build_direct_message_notification_email(
    recipient_name: str = "Alex", sender_name: str = "Jordan", message_preview: str = "Hey, I wanted to discuss the coaching plan we talked about...",
    thread_link: str = ""
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">New message from {sender_name}</p>
    <div class="em-force-light-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:16px 18px;margin:14px 0;">
      <p style="margin:0 0 6px;font-weight:600;color:#0F172A;font-size:13px;">{sender_name}</p>
      <p style="margin:0;color:#374151;font-size:13px;line-height:1.7;">{message_preview}</p>
    </div>
    {_callout("Reply directly from your dashboard to continue the conversation.")}"""
    return EmailTemplate(
        subject=f"{sender_name} sent you a message",
        html=_wrap("New Message", f"Message from {sender_name}", body, "Reply Now", thread_link or f"{DASH_URL}/messages", category="communication"),
        text=_txt("Direct Message", f"From {sender_name}: {message_preview}"),
    )


# ── P1-7. Payment Admin Alert ────────────────────────────

@_register("payment_admin_alert", "Payment Admin Alert", "Billing", "Admin notification when a payment is confirmed")
def build_payment_admin_alert_email(
    method: str = "Stripe", amount: str = "$15.99", receipt_number: str = "PAY-20260415-001",
    user_email: str = "alex@example.com", plan: str = "Premium"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Payment confirmed</p>
    <p style="margin:0 0 16px;">{_badge("ADMIN ALERT", "#10B981")} A new payment has been processed.</p>
    {_info_table([_info_row("Amount", amount, "#10B981"), _info_row("Method", method), _info_row("Receipt", receipt_number), _info_row("User", user_email), _info_row("Plan", plan)])}"""
    return EmailTemplate(
        subject=f"[Admin] Payment Confirmed via {method} — {receipt_number}",
        html=_wrap("Payment Alert", f"{amount} via {method}", body, "View Payment Details", f"{DASH_URL}/admin-console", "#10B981", category="billing"),
        text=_txt("Payment Alert", f"[Admin] {amount} via {method}, Receipt: {receipt_number}, User: {user_email}, Plan: {plan}"),
    )


# ── P1-8. Ticket Feedback Digest ─────────────────────────

@_register("ticket_feedback_digest", "Ticket Feedback Digest", "Support", "Weekly support satisfaction summary for admins")
def build_ticket_feedback_digest_email(
    period: str = "Apr 7–13, 2026", total_responses: int = 45, avg_rating: float = 4.2,
    positive_pct: int = 85, negative_count: int = 3
) -> EmailTemplate:
    rating_color = "#10B981" if avg_rating >= 4.0 else "#F59E0B" if avg_rating >= 3.0 else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Support Feedback — {period}</p>
    <p style="margin:0 0 16px;">Weekly digest of customer satisfaction across all support tickets.</p>
    {_info_table([_info_row("Period", period), _info_row("Total Responses", str(total_responses)), _info_row("Avg Rating", f"{avg_rating}/5", rating_color), _info_row("Positive", f"{positive_pct}%", "#10B981"), _info_row("Negative Flags", str(negative_count), "#EF4444" if negative_count > 0 else "#10B981")])}
    {_callout("Review flagged tickets in the Support dashboard to address negative feedback promptly.")}"""
    return EmailTemplate(
        subject=f"Ticket Feedback Digest — {period} | {total_responses} responses, {avg_rating}/5 avg",
        html=_wrap("Feedback Digest", f"Support satisfaction for {period}", body, "View Support Dashboard", f"{DASH_URL}/admin-console", category="support"),
        text=_txt("Feedback Digest", f"{period}: {total_responses} responses, {avg_rating}/5 avg, {positive_pct}% positive, {negative_count} negative."),
    )


# ── P1-9. Ticket Sentiment Alert ─────────────────────────

@_register("ticket_sentiment_alert", "Sentiment Alert", "Support", "Real-time alert when negative sentiment is detected in tickets")
def build_ticket_sentiment_alert_email(
    categories: str = "Billing, Onboarding", alert_count: int = 5, health_score: int = 72,
    period: str = "Last 24 hours"
) -> EmailTemplate:
    health_color = "#10B981" if health_score >= 80 else "#F59E0B" if health_score >= 60 else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Sentiment Alert</p>
    <p style="margin:0 0 16px;">{_badge("ATTENTION", "#F59E0B")} Negative sentiment detected across support tickets.</p>
    {_info_table([_info_row("Categories", categories), _info_row("Flagged Tickets", str(alert_count), "#EF4444"), _info_row("Health Score", f"{health_score}/100", health_color), _info_row("Period", period)])}
    {_callout("Review flagged tickets to identify patterns and take corrective action before customer satisfaction drops further.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Sentiment Alert — {categories} ({alert_count} flagged)",
        html=_wrap("Sentiment Alert", f"{alert_count} negative flags in {categories}", body, "Review Flagged Tickets", f"{DASH_URL}/admin-console", "#F59E0B", category="support"),
        text=_txt("Sentiment Alert", f"Categories: {categories}, Flagged: {alert_count}, Health: {health_score}/100, Period: {period}"),
    )


# ── P1-10. Security Nightly Report ───────────────────────

@_register("security_nightly_report", "Security Nightly Report", "Security", "Nightly Active Defense summary for admins")
def build_security_nightly_report_email(
    status: str = "SECURE", threat_level: str = "Low", checks_passed: int = 28, checks_total: int = 29,
    score: int = 98, anomalies_24h: int = 3, blocked_ips: int = 12
) -> EmailTemplate:
    status_color = "#10B981" if status == "SECURE" else "#F59E0B" if status == "ELEVATED" else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Nightly Security Report</p>
    <p style="margin:0 0 16px;">{_badge(status, status_color)} Active Defense nightly summary.</p>
    {_info_table([_info_row("Status", status, status_color), _info_row("Threat Level", threat_level), _info_row("Security Score", f"{score}%"), _info_row("Checks", f"{checks_passed}/{checks_total} pass"), _info_row("Anomalies (24h)", str(anomalies_24h)), _info_row("Blocked IPs", str(blocked_ips))])}
    {_callout("Full details available in the Security Posture dashboard. Anomalies are auto-investigated by the Active Defense engine.")}"""
    return EmailTemplate(
        subject=f"[Active Defense Nightly] {status} | Threat: {threat_level} | {checks_passed}/{checks_total} pass",
        html=_wrap("Security Report", f"Nightly: {status} — {score}%", body, "View Security Dashboard", f"{DASH_URL}/admin-console", status_color, category="security"),
        text=_txt("Security Nightly", f"{status} | Threat: {threat_level} | {checks_passed}/{checks_total} | Anomalies: {anomalies_24h} | Blocked: {blocked_ips}"),
    )


# ── P1-11. Weekly Audit Log ──────────────────────────────

@_register("weekly_audit_log", "Weekly Audit Log", "Notifications", "Weekly compliance audit trail for admins")
def build_weekly_audit_log_email(
    period: str = "Apr 7–13, 2026", log_count: int = 156, critical_events: int = 2,
    top_actions: str = "Login (42), Data Export (8), Role Change (5)"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Weekly Audit Log — {period}</p>
    <p style="margin:0 0 16px;">Compliance audit trail summary for the reporting period.</p>
    {_info_table([_info_row("Period", period), _info_row("Total Events", str(log_count)), _info_row("Critical Events", str(critical_events), "#EF4444" if critical_events > 0 else "#10B981"), _info_row("Top Actions", top_actions)])}
    {_callout("Full audit log is available for download in the Admin Console. Retain for compliance records.", "#3B82F6")}"""
    return EmailTemplate(
        subject=f"Weekly Audit Log — {log_count} entries | {period}",
        html=_wrap("Audit Log", f"Compliance summary for {period}", body, "Download Full Log", f"{DASH_URL}/admin-console", "#3B82F6", category="notifications"),
        text=_txt("Audit Log", f"{period}: {log_count} events, {critical_events} critical. Top: {top_actions}"),
    )


# ── P1-12. Compliance Report ─────────────────────────────

@_register("compliance_report", "Compliance Report", "Notifications", "Enterprise integrity compliance report")
def build_compliance_report_email(
    report_date: str = "Apr 15, 2026", overall_score: int = 96, grade: str = "A",
    checks_passed: int = 48, checks_total: int = 50, next_audit: str = "May 15, 2026"
) -> EmailTemplate:
    grade_color = "#10B981" if grade in ("A", "A+") else "#F59E0B" if grade in ("B", "C") else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Enterprise Compliance Report</p>
    <p style="margin:0 0 16px;">{_badge(f"GRADE {grade}", grade_color)} Platform compliance assessment completed.</p>
    {_info_table([_info_row("Date", report_date), _info_row("Score", f"{overall_score}%", grade_color), _info_row("Grade", grade, grade_color), _info_row("Checks", f"{checks_passed}/{checks_total} pass"), _info_row("Next Audit", next_audit)])}
    {_callout("This report covers GDPR, SOC 2, and ISO 27001 compliance controls. Download the full report from the Admin Console.", "#3B82F6")}"""
    return EmailTemplate(
        subject=f"Compliance Report — {overall_score}% (Grade {grade}) | {report_date}",
        html=_wrap("Compliance Report", f"Score: {overall_score}% — Grade {grade}", body, "Download Full Report", f"{DASH_URL}/admin-console", grade_color, category="notifications"),
        text=_txt("Compliance", f"{report_date}: {overall_score}% (Grade {grade}), {checks_passed}/{checks_total} pass. Next: {next_audit}"),
    )


# ── P1-13. Employee Risk Alert ───────────────────────────

@_register("employee_risk_alert", "Employee Risk Alert", "Employer", "HR alert for at-risk team members")
def build_employee_risk_alert_email(
    admin_name: str = "HR Admin", alert_count: int = 3, company_name: str = "Acme Corp",
    top_risks: str = "Disengagement (2), Performance decline (1)"
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Employee Risk Alert</p>
    <p style="margin:0 0 16px;">{_badge(f"{alert_count} ALERTS", "#F59E0B")} High-risk employee signals detected in <strong>{company_name}</strong>.</p>
    {_info_table([_info_row("Organization", company_name), _info_row("Alerts", str(alert_count), "#F59E0B"), _info_row("Risk Types", top_risks)])}
    {_callout("Review individual risk profiles in the Team Intelligence dashboard. Early intervention can prevent turnover.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"{alert_count} high-risk employee alert(s) — {company_name}",
        html=_wrap("Risk Alert", f"{alert_count} alerts in {company_name}", body, "View Team Dashboard", f"{DASH_URL}/team", "#F59E0B", category="employer"),
        text=_txt("Employee Risk", f"{alert_count} alerts in {company_name}. Risks: {top_risks}"),
    )


# ── P2-14. Autonomous Engine Report ──────────────────────

@_register("autonomous_engine_report", "Autonomous Engine Report", "AI", "AI engine run status report for admins")
def build_autonomous_engine_report_email(
    run_id: str = "RUN-2026-0415-001", status: str = "Completed", duration: str = "4m 32s",
    content_generated: int = 12, errors: int = 0,
    gates: dict | None = None, root_cause: str = "",
) -> EmailTemplate:
    status_color = "#10B981" if status == "Completed" else "#F59E0B" if status == "Partial" else "#EF4444"
    rows = [_info_row("Run ID", run_id), _info_row("Status", status, status_color),
            _info_row("Duration", duration), _info_row("Content Generated", str(content_generated)),
            _info_row("Errors", str(errors), "#EF4444" if errors > 0 else "#10B981")]
    for gate_name, gate_status in (gates or {}).items():
        ok = str(gate_status).upper() == "PASS"
        rows.append(_info_row(f"Gate — {gate_name}", str(gate_status).upper(), "#10B981" if ok else "#EF4444"))
    root_cause_html = ""
    if root_cause:
        import html as _html

        root_cause_html = (
            '<div style="margin:14px 0 0;padding:12px 14px;background:#FEF2F2;border-left:3px solid #EF4444;'
            'border-radius:8px;"><p style="margin:0;color:#991B1B;font-size:12px;font-weight:700;">ROOT CAUSE</p>'
            f'<p style="margin:4px 0 0;color:#7F1D1D;font-size:12px;line-height:1.6;">{_html.escape(root_cause[:500])}</p></div>'
        )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Autonomous Engine Report</p>
    <p style="margin:0 0 16px;">{_badge(status.upper(), status_color)} Engine run completed.</p>
    {_info_table(rows)}{root_cause_html}"""
    return EmailTemplate(
        subject=f"Autonomous Engine: {status} — {run_id}",
        html=_wrap("Engine Report", f"{status}: {run_id}", body, "View Run Details", f"{DASH_URL}/admin-console", status_color, category="ai"),
        text=_txt("Engine Report", f"{run_id}: {status}, Duration: {duration}, Generated: {content_generated}, Errors: {errors}"),
    )


# ── P2-15. Performance Degradation Alert ─────────────────

@_register("performance_degradation_alert", "Performance Alert", "Notifications", "Web vitals degradation alert for admins")
def build_performance_degradation_alert_email(
    level: str = "WARNING", metric: str = "LCP", current_value: str = "3.2s",
    threshold: str = "2.5s", page: str = "/dashboard", timestamp: str = "2026-04-15 14:30 UTC"
) -> EmailTemplate:
    level_color = "#EF4444" if level == "CRITICAL" else "#F59E0B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Performance {level.title()}</p>
    <p style="margin:0 0 16px;">{_badge(level, level_color)} Web vitals degradation detected.</p>
    {_info_table([_info_row("Metric", metric), _info_row("Current", current_value, level_color), _info_row("Threshold", threshold), _info_row("Page", page), _info_row("Time", timestamp)])}
    {_callout("Check the Performance dashboard for detailed metrics and auto-remediation status.", level_color)}"""
    return EmailTemplate(
        subject=f"Performance {level}: {metric} degradation on {page}",
        html=_wrap("Performance Alert", f"{level}: {metric} at {current_value}", body, "View Performance Dashboard", f"{DASH_URL}/admin-console", level_color, category="notifications"),
        text=_txt("Performance Alert", f"[{level}] {metric}: {current_value} (threshold: {threshold}) on {page} at {timestamp}"),
    )



def get_editable_fields() -> list:
    """Return the list of editable fields with metadata for the editor UI."""
    return [
        {"key": "subject", "label": "Subject Line", "type": "text", "placeholder": "Custom email subject..."},
        {"key": "header_title", "label": "Header Title", "type": "text", "placeholder": "Override the header title..."},
        {"key": "accent_color", "label": "Accent Color", "type": "color", "placeholder": "#3B82F6"},
        {"key": "cta_label", "label": "CTA Button Text", "type": "text", "placeholder": "e.g. View Dashboard"},
        {"key": "cta_url", "label": "CTA Button URL", "type": "url", "placeholder": "https://..."},
        {"key": "footer_text", "label": "Footer Text", "type": "text", "placeholder": "Custom footer message..."},
    ]


# ── P2-16. Admin Detailed System Alert (catalog wrapper) ──

@_register("admin_detailed_system_alert", "Admin Detailed Alert", "Notifications", "Detailed admin system alert with data rows")
def build_admin_detailed_system_alert_catalog(
    title: str = "System Alert",
    intro: str = "A system event requires your attention.",
    rows: list = None,
    accent: str = "#F59E0B",
    status_label: str = "NOTICE",
    footer_note: str = "",
    cta_label: str = "",
    cta_url: str = "",
) -> EmailTemplate:
    """Catalog-registered wrapper around build_admin_system_alert_email."""
    parsed_rows = []
    for r in (rows or [("Status", "OK")]):
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            parsed_rows.append((str(r[0]), str(r[1])))
        elif isinstance(r, dict):
            parsed_rows.append((str(r.get("label", "")), str(r.get("value", ""))))
        else:
            parsed_rows.append((str(r), ""))
    html = build_admin_system_alert_email(
        title, intro, parsed_rows,
        accent=accent, status_label=status_label,
        footer_note=footer_note, cta_label=cta_label, cta_url=cta_url,
    )
    rows_text = "\n".join(f"  {label}: {value}" for label, value in parsed_rows)
    return EmailTemplate(
        subject=f"[{status_label}] {title}",
        html=html,
        text=f"{title}\n{status_label}\n\n{intro}\n\n{rows_text}\n\n{footer_note}",
    )


# ── Nightly Acceptance Report ─────────────────────────────

@_register("nightly_acceptance_report", "Nightly Acceptance Report", "Notifications", "Cross-provider acceptance test results")
def build_nightly_acceptance_report_email(
    version: str = "v2026.04.16.0330",
    passed: int = 0,
    total: int = 0,
    generated_at: str = "",
) -> EmailTemplate:
    status = "PASS" if passed >= total and total > 0 else "REPORT"
    score_color = "#10B981" if passed >= total else "#F59E0B" if passed > 0 else "#64748B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Nightly Cross-Provider Acceptance Report</p>
    <p style="margin:0 0 16px;">{_badge(status, score_color)} Automated acceptance tests completed.</p>
    {_info_table([_info_row("Version", version), _info_row("Tests Passed", f"{passed}/{total}", score_color), _info_row("Generated", generated_at or "—")])}
    {_callout("The branded PDF acceptance report is attached to this email. Review results in the Admin Console for detailed breakdowns.", "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"[Nightly Acceptance Report] {version} {status} {passed}/{total}",
        html=_wrap("Acceptance Report", f"{version} — {passed}/{total} Pass", body, "View in Console", f"{DASH_URL}/admin-console", score_color, category="notifications"),
        text=_txt("Nightly Acceptance Report", f"Version: {version}\nPassed: {passed}/{total}\nGenerated: {generated_at}"),
    )


# ── IAP Nightly Drill Report ─────────────────────────────

@_register("iap_nightly_drill", "IAP Nightly Drill", "Notifications", "IAP compliance & reliability drill report")
def build_iap_nightly_drill_email(
    report_id: str = "",
    started_at: str = "",
    completed_at: str = "",
    results_summary: str = "All checks passed",
    slo_status: str = "Healthy",
) -> EmailTemplate:
    slo_color = "#10B981" if "healthy" in slo_status.lower() else "#F59E0B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">IAP Compliance & Reliability Report</p>
    <p style="margin:0 0 16px;">{_badge("DRILL COMPLETE", slo_color)} Nightly IAP health drill has finished.</p>
    {_info_table([_info_row("Report ID", report_id or "—"), _info_row("Started", started_at or "—"), _info_row("Completed", completed_at or "—"), _info_row("SLO Status", slo_status, slo_color), _info_row("Summary", results_summary)])}
    {_callout("This automated drill verifies purchase flow, receipt validation, and subscription lifecycle across Apple and Google providers. View full results in the Admin Console.", "#8B5CF6")}"""
    return EmailTemplate(
        subject="[IAP Nightly Drill] Compliance & Reliability Report",
        html=_wrap("IAP Nightly Drill", "Compliance & Reliability", body, "View Full Report", f"{DASH_URL}/admin-console", slo_color, category="notifications"),
        text=_txt("IAP Nightly Drill", f"Report: {report_id}\nStarted: {started_at}\nCompleted: {completed_at}\nSLO: {slo_status}\n{results_summary}"),
    )

# ── Logo Render Probe ─────────────────────────────────────

@_register("logo_render_probe", "Logo Render Probe", "Notifications", "Logo rendering diagnostic probe email")
def build_logo_render_probe_email(
    probe_time: str = "", inline_status: str = "OK", cdn_status: str = "OK", cdn_url: str = "",
) -> EmailTemplate:
    inline_color = "#10B981" if inline_status == "OK" else "#EF4444"
    cdn_color = "#10B981" if cdn_status == "OK" else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Logo Render Probe</p>
    <p style="margin:0 0 16px;">{_badge("DIAGNOSTIC", "#6366F1")} Automated logo rendering check.</p>
    {_info_table([_info_row("Probe Time", probe_time or "—"), _info_row("Inline Attachment", inline_status, inline_color), _info_row("CDN Status", cdn_status, cdn_color), _info_row("CDN URL", cdn_url[:60] if cdn_url else "—")])}
    {_callout("This probe verifies that the RealAICoach logo renders correctly via both CID inline attachment and CDN fallback across email clients.", "#6366F1")}"""
    return EmailTemplate(
        subject=f"[Logo Render Probe] {probe_time[:16] if probe_time else ''}",
        html=_wrap("Logo Render Probe", "Logo rendering diagnostic", body, "View Admin Console", f"{DASH_URL}/admin-console", "#6366F1", category="notifications"),
        text=_txt("Logo Render Probe", f"Inline: {inline_status} | CDN: {cdn_status} | URL: {cdn_url}"),
    )

@_register("csat_ai_report_v7", "CSAT AI Report", "AI", "AI-powered CSAT analysis report for admins")
def build_csat_ai_report_v7_email(
    health: int = 85, health_label: str = "Good", total_responses: int = 0, avg_score: str = "4.2",
    nps: str = "+42", top_themes: str = "", risk_categories: str = "", top_actions: str = "",
) -> EmailTemplate:
    h_color = "#10B981" if health >= 80 else "#F59E0B" if health >= 60 else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">CSAT AI Intelligence Report</p>
    <p style="margin:0 0 16px;">{_badge(f"HEALTH {health}/100", h_color)} {_badge(health_label, h_color)} AI-analyzed customer satisfaction.</p>
    {_info_table([_info_row("Health Score", f"{health}/100", h_color), _info_row("Total Responses", str(total_responses)), _info_row("Average Score", avg_score), _info_row("NPS", nps), _info_row("Top Themes", top_themes or "—"), _info_row("At-Risk", risk_categories or "None"), _info_row("Recommended Actions", top_actions or "—")])}
    {_callout("This report is generated by GPT-4o analysis of all CSAT responses. View detailed breakdowns in the AI Dashboard.", "#8B5CF6")}"""
    return EmailTemplate(
        subject=f"CSAT AI Report — Health {health}/100 | {health_label} | {total_responses} responses",
        html=_wrap("CSAT AI Report", f"Health {health}/100 — {health_label}", body, "View AI Dashboard", f"{DASH_URL}/executive-dashboard", h_color, category="ai"),
        text=_txt("CSAT AI Report", f"Health: {health}/100 ({health_label})\nResponses: {total_responses}\nAvg: {avg_score}\nNPS: {nps}"),
    )

@_register("sentiment_summary_v7", "Sentiment Summary", "AI", "Weekly ticket sentiment analysis summary")
def build_sentiment_summary_v7_email(
    health: int = 78, ticket_count: int = 0, avg_rating: str = "4.1",
    positive_pct: str = "65%", neutral_pct: str = "20%", negative_pct: str = "15%",
    improving: str = "", declining: str = "",
) -> EmailTemplate:
    h_color = "#10B981" if health >= 80 else "#F59E0B" if health >= 60 else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Weekly Sentiment Summary</p>
    <p style="margin:0 0 16px;">{_badge(f"HEALTH {health}/100", h_color)} Ticket sentiment pulse.</p>
    {_info_table([_info_row("Health Score", f"{health}/100", h_color), _info_row("Tickets", str(ticket_count)), _info_row("Avg Rating", f"{avg_rating}/5"), _info_row("Positive", positive_pct, "#10B981"), _info_row("Neutral", neutral_pct, "#F59E0B"), _info_row("Negative", negative_pct, "#EF4444"), _info_row("Improving", improving or "—", "#10B981"), _info_row("Declining", declining or "—", "#EF4444")])}
    {_callout("Sentiment analysis runs weekly across all support tickets. View heatmaps in the Executive Dashboard.", "#8B5CF6")}"""
    return EmailTemplate(
        subject=f"Sentiment Summary — Health {health}/100 | {ticket_count} tickets, {avg_rating}/5 avg",
        html=_wrap("Sentiment Summary", f"Health {health}/100", body, "View Heatmaps", f"{DASH_URL}/executive-dashboard", h_color, category="ai"),
        text=_txt("Sentiment Summary", f"Health: {health}/100\nTickets: {ticket_count}\nAvg: {avg_rating}/5"),
    )

@_register("zero_trust_daily_v7", "Zero Trust Daily", "Security", "Zero-trust daily security status")
def build_zero_trust_daily_v7_email(
    threat_level: str = "LOW", risk_score: int = 12, pending: int = 0, high_pending: int = 0, report_date: str = "",
) -> EmailTemplate:
    t_color = "#10B981" if threat_level == "LOW" else "#F59E0B" if threat_level == "MEDIUM" else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Zero-Trust Daily Status</p>
    <p style="margin:0 0 16px;">{_badge(f"{threat_level} RISK", t_color)} Daily zero-trust posture report.</p>
    {_info_table([_info_row("Threat Level", threat_level, t_color), _info_row("Risk Score", str(risk_score), t_color), _info_row("Pending Approvals", str(pending)), _info_row("High Priority", str(high_pending), "#EF4444" if high_pending > 0 else "#10B981"), _info_row("Report Date", report_date or "—")])}
    {_callout("Zero-trust policies continuously evaluate access and behavioral signals. Review in Security Console.", "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"[Zero-Trust Daily] {threat_level} risk ({risk_score}) · pending {pending}/{high_pending} · {report_date}",
        html=_wrap("Zero-Trust Daily", f"{threat_level} Risk — Score {risk_score}", body, "Security Console", f"{DASH_URL}/admin-console", t_color, category="security"),
        text=_txt("Zero-Trust Daily", f"Threat: {threat_level} (score {risk_score})\nPending: {pending} ({high_pending} high)"),
    )


@_register(
    "risk_engine_status_v7",
    "Progressive Risk Engine Status",
    "Security",
    "Admin risk engine event with required output block (RISK_ENGINE_STATUS...)",
)
def build_risk_engine_status_v7_email(
    user_id: str = "",
    user_email: str = "",
    risk_score: int = 0,
    risk_level: str = "LOW",
    trigger: str = "NO_FRICTION",
    false_positive_rate: str = "0%",
    session_protection: str = "STANDARD_MONITORING",
    confidence: str = "0%",
    output_block: str = "",
    source: str = "runtime",
    scored_at: str = "",
) -> EmailTemplate:
    band = str(risk_level or "LOW").upper()
    color = "#10B981" if band == "LOW" else "#F59E0B" if band == "MEDIUM" else "#F97316" if band == "HIGH" else "#EF4444"
    block = output_block or "\n".join(
        [
            "RISK_ENGINE_STATUS: ACTIVE",
            f"RISK_SCORE: {int(risk_score)}",
            f"RISK_LEVEL: {band}",
            f"TRIGGER: {trigger}",
            f"FALSE_POSITIVE_RATE: {false_positive_rate}",
            f"SESSION_PROTECTION: {session_protection}",
            f"CONFIDENCE: {confidence}",
        ]
    )

    info_rows = _info_table(
        [
            _info_row("User ID", user_id or "—"),
            _info_row("User Email", user_email or "—"),
            _info_row("Risk Score", str(int(risk_score)), color),
            _info_row("Risk Level", band, color),
            _info_row("Trigger", trigger or "—"),
            _info_row("False Positive Rate", false_positive_rate or "0%"),
            _info_row("Session Protection", session_protection or "STANDARD_MONITORING"),
            _info_row("Confidence", confidence or "0%"),
            _info_row("Source", source or "runtime"),
            _info_row("Scored At", scored_at or "—"),
        ]
    )
    badge = _badge(f"{band} RISK", color)
    action_callout = _callout(
        "Use Admin Executive Risk Actions for lock session, force ID Checker, and containment handling.",
        color,
    )

    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Progressive Risk Engine Alert</p>
    <p style="margin:0 0 16px;">{badge} Real-time risk posture update generated by Progressive Risk Engine.</p>
    {info_rows}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:14px 0 0;">
      <tr>
        <td class="em-force-light-card" style="background:#F8FAFC;border:1px solid #D1D5DB;border-radius:12px;padding:14px 16px;color:#0F172A;">
          <pre style="margin:0;color:#0F172A;font-size:12px;line-height:1.65;font-family:SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;word-break:break-word;">{block}</pre>
        </td>
      </tr>
    </table>
    {action_callout}"""

    return EmailTemplate(
        subject=f"[Risk Engine] {band} risk ({int(risk_score)}) · {user_email or user_id}",
        html=_wrap(
            "Progressive Risk Engine",
            f"{band} Risk — Score {int(risk_score)}",
            body,
            "Open Executive Dashboard",
            f"{DASH_URL}/executive-dashboard?section=risk",
            color,
            category="security",
        ),
        text=_txt(
            "Progressive Risk Engine",
            block,
            "Open Executive Dashboard",
            f"{DASH_URL}/executive-dashboard?section=risk",
        ),
    )


@_register(
    "risk_engine_user_guidance_v7",
    "Risk Engine User Guidance",
    "Security",
    "User-facing risk guidance with step-by-step actions",
)
def build_risk_engine_user_guidance_v7_email(
    recipient_name: str = "there",
    risk_level: str = "MEDIUM",
    risk_score: int = 0,
    trigger: str = "STEP_UP_MFA",
    message: str = "We detected unusual activity and added temporary protection to your account.",
    next_steps: list | None = None,
    support_url: str = "",
    idv_url: str = "",
) -> EmailTemplate:
    level = str(risk_level or "MEDIUM").upper()
    accent = "#F59E0B" if level == "MEDIUM" else "#F97316" if level == "HIGH" else "#EF4444"
    steps = next_steps or [
        "Optional: Open ID Checker from your security prompt.",
        "Optional: Upload identification documents if you choose verification.",
        "Alternative recovery: Reset Password or use One-Time Code sign-in to continue without mandatory ID Checker.",
    ]

    step_rows = "".join(
        [
            f'<tr><td class="em-step-td" style="padding:14px 16px;color:#0F172A;font-size:13px;line-height:1.6;border-bottom:{"1px solid #E2E8F0" if idx < len(steps) - 1 else "none"};"><span style="display:inline-block;min-width:20px;color:{accent};font-weight:800;">{idx+1}.</span> {item}</td></tr>'
            for idx, item in enumerate(steps)
        ]
    )

    links_row = _info_table(
        [
            _info_row("Risk Level", level, accent),
            _info_row("Risk Score", str(int(risk_score)), accent),
            _info_row("Trigger", trigger or "STEP_UP_MFA"),
            _info_row("Security Support", support_url or "security@realaicoach.app"),
        ]
    )

    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 6px;">Security protection activated</p>
    <p style="margin:0 0 14px;color:#334155;font-size:14px;line-height:1.7;">Hi {recipient_name}, {message}</p>
    {links_row}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:14px 0 0;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
      {step_rows}
    </table>
    {_callout("If this alert was unexpected, contact security@realaicoach.app and include your latest sign-in timestamp for rapid review.", accent)}"""

    action_url = idv_url or f"{DASH_URL}/id-checker"
    action_label = "Open recovery options" if level in {"HIGH", "CRITICAL"} else "Review security steps"

    return EmailTemplate(
        subject=f"[Security Action Needed] {level} risk protection on your account",
        html=_wrap(
            "Account Security Guidance",
            f"{level} risk detected — follow the next steps",
            body,
            action_label,
            action_url,
            accent,
            category="security",
        ),
        text=_txt(
            "Account Security Guidance",
            f"Risk level: {level}\nRisk score: {int(risk_score)}\nTrigger: {trigger}\n\n" + "\n".join([f"{idx+1}. {step}" for idx, step in enumerate(steps)]),
            action_label,
            action_url,
        ),
    )


@_register("gps_runtime_incident", "GPS Runtime Incident", "Security", "Critical GPS runtime degradation incident alert")
def build_gps_runtime_incident_email(
    component: str = "gps_service",
    lifecycle_stage: str = "state_resolution_exception",
    error_message: str = "runtime_unavailable",
    timestamp: str = "",
) -> EmailTemplate:
    accent = "#DC2626"
    ts_value = timestamp or "—"
    body = f"""{_alert_panel("GPS Runtime Incident", "GlobalPlatformState entered degraded runtime mode.", accent, "CRITICAL")}
    {_info_table([
        _info_row("Component", component or "gps_service", accent),
        _info_row("Lifecycle stage", lifecycle_stage or "state_resolution_exception"),
        _info_row("Error", error_message or "runtime_unavailable"),
        _info_row("Timestamp", ts_value),
    ])}
    {_callout("Fallback state serving is active. Review GPS health and incident logs to validate recovery.", accent)}"""
    return EmailTemplate(
        subject="[CRITICAL] GPS runtime degraded",
        html=_wrap(
            "GPS Runtime Incident",
            "GlobalPlatformState degraded mode active",
            body,
            "Open GPS Control Center",
            f"{DASH_URL}/admin-console?category=operations&tab=gps-state-management",
            accent,
            category="security",
        ),
        text=_txt(
            "GPS Runtime Incident",
            (
                f"Component: {component or 'gps_service'}\n"
                f"Lifecycle stage: {lifecycle_stage or 'state_resolution_exception'}\n"
                f"Error: {error_message or 'runtime_unavailable'}\n"
                f"Timestamp: {ts_value}"
            ),
            "Open GPS Control Center",
            f"{DASH_URL}/admin-console?category=operations&tab=gps-state-management",
        ),
    )


@_register("security_incident_spike_v7", "Security Incident Spike Alert", "Security", "Alert when 401/403 incident rate exceeds threshold")
def build_security_incident_spike_v7_email(
    total_incidents: int = 0, incidents_401: int = 0, incidents_403: int = 0,
    window_minutes: int = 60, threshold: int = 100,
    top_ips: str = "", top_paths: str = "", idor_blocked: int = 0,
) -> EmailTemplate:
    c = "#EF4444" if total_incidents >= threshold * 2 else "#F59E0B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Security Incident Spike Detected</p>
    <p style="margin:0 0 16px;">{_badge("INCIDENT SPIKE", c)} {total_incidents} unauthorized access attempts in the last {window_minutes} minutes (threshold: {threshold}).</p>
    {_info_table([_info_row("Total Incidents", str(total_incidents), c), _info_row("401 Unauthorized", str(incidents_401)), _info_row("403 Forbidden", str(incidents_403)), _info_row("IDOR Blocked", str(idor_blocked), "#8B5CF6"), _info_row("Window", f"Last {window_minutes} min"), _info_row("Threshold", str(threshold)), _info_row("Top IPs", top_ips or "—"), _info_row("Top Paths", top_paths or "—")])}
    {_callout("Review the Security Incident Dashboard for full details. Consider blocking repeat offender IPs.", c)}"""
    return EmailTemplate(
        subject=f"[SECURITY SPIKE] {total_incidents} incidents in {window_minutes}min (threshold: {threshold})",
        html=_wrap("Incident Spike", f"{total_incidents} incidents", body, "View Incident Dashboard", f"{DASH_URL}/admin-console", c, category="security"),
        text=_txt("Incident Spike", f"Total: {total_incidents} (401: {incidents_401}, 403: {incidents_403})\nWindow: {window_minutes}min\nTop IPs: {top_ips}\nTop Paths: {top_paths}"),
    )

@_register("ip_auto_blocked_v7", "IP Auto-Blocked Alert", "Security", "Alert when IPs are automatically blocked for exceeding incident threshold")
def build_ip_auto_blocked_v7_email(
    blocked_count: int = 0, ip_list: str = "", threshold: int = 100,
    window_minutes: int = 60, block_duration_hours: int = 24,
) -> EmailTemplate:
    c = "#EF4444" if blocked_count >= 5 else "#F59E0B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">IPs Auto-Blocked</p>
    <p style="margin:0 0 16px;">{_badge(f"{blocked_count} BLOCKED", c)} Automated blocking triggered for IPs exceeding {threshold} incidents in {window_minutes} minutes.</p>
    {_info_table([_info_row("IPs Blocked", str(blocked_count), c), _info_row("Threshold", f"{threshold} incidents/{window_minutes}min"), _info_row("Block Duration", f"{block_duration_hours} hours"), _info_row("Blocked IPs", ip_list or "—")])}
    {_callout("Review blocked IPs in the IP Blocklist dashboard. Whitelisted IPs are never auto-blocked.", c)}"""
    return EmailTemplate(
        subject=f"[AUTO-BLOCK] {blocked_count} IPs blocked (>{threshold} incidents/{window_minutes}min)",
        html=_wrap("IP Auto-Block", f"{blocked_count} IPs blocked", body, "View IP Blocklist", f"{DASH_URL}/admin-console", c, category="security"),
        text=_txt("IP Auto-Block", f"Blocked: {blocked_count}\nThreshold: {threshold}/{window_minutes}min\nDuration: {block_duration_hours}h\nIPs: {ip_list}"),
    )


@_register("anomaly_spike_v7", "Anomaly Spike Alert", "Security", "Anomaly spike detection alert")
def build_anomaly_spike_v7_email(
    total_anomalies: int = 0, period: str = "last hour", top_domains: str = "", auto_fix: bool = False,
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Anomaly Spike Detected</p>
    <p style="margin:0 0 16px;">{_badge("SPIKE ALERT", "#EF4444")} Elevated anomaly rate in {period}.</p>
    {_info_table([_info_row("Total Anomalies", str(total_anomalies), "#EF4444"), _info_row("Period", period), _info_row("Top Domains", top_domains or "—"), _info_row("Auto-Fix", "Triggered" if auto_fix else "Not triggered")])}
    {_callout("Investigate the anomaly cluster in the Security Console.", "#EF4444")}"""
    return EmailTemplate(
        subject=f"[SPIKE ALERT] {total_anomalies} anomalies detected in the {period}",
        html=_wrap("Anomaly Spike", f"{total_anomalies} anomalies", body, "Investigate Now", f"{DASH_URL}/admin-console", "#EF4444", category="security"),
        text=_txt("Anomaly Spike", f"{total_anomalies} anomalies in {period}\nDomains: {top_domains}"),
    )

@_register("alert_recovery_v7", "Alert Recovery", "Notifications", "Service recovery notification")
def build_alert_recovery_v7_email(
    rule_name: str = "", metric: str = "", current_value: str = "", downtime: str = "", fix_applied: str = "",
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Service Recovered</p>
    <p style="margin:0 0 16px;">{_badge("RECOVERED", "#10B981")} Alert resolved — service restored.</p>
    {_info_table([_info_row("Alert", rule_name or "—"), _info_row("Metric", metric or "—"), _info_row("Current", current_value or "—", "#10B981"), _info_row("Downtime", downtime or "—"), _info_row("Fix Applied", fix_applied or "None")])}
    {_callout("The alert has been automatically cleared. Monitor ongoing performance in the Admin Console.", "#10B981")}"""
    return EmailTemplate(
        subject=f"[RECOVERED] {rule_name} — Service restored after {downtime}",
        html=_wrap("Alert Recovery", f"{rule_name} — Restored", body, "View Dashboard", f"{DASH_URL}/admin-console", "#10B981", category="notifications"),
        text=_txt("Alert Recovery", f"Alert: {rule_name}\nDowntime: {downtime}\nFix: {fix_applied}"),
    )

@_register("weekly_heatmap_v7", "Weekly Email Heatmap", "Notifications", "Weekly email engagement heatmap")
def build_weekly_heatmap_v7_email(
    total_clicks: int = 0, template_count: int = 0, top_templates: str = "", top_urls: str = "",
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Weekly Email Heatmap Digest</p>
    <p style="margin:0 0 16px;">{_badge(f"{total_clicks} CLICKS", "#3B82F6")} Email engagement summary.</p>
    {_info_table([_info_row("Total Clicks", str(total_clicks), "#3B82F6"), _info_row("Templates Tracked", str(template_count)), _info_row("Top Templates", top_templates or "—"), _info_row("Top URLs", top_urls or "—")])}
    {_callout("Click heatmaps help optimize email CTAs. View detailed breakdowns in Email Analytics.", "#3B82F6")}"""
    return EmailTemplate(
        subject=f"Weekly Email Heatmap: {total_clicks} clicks across {template_count} templates",
        html=_wrap("Email Heatmap", f"{total_clicks} clicks", body, "View Heatmap", f"{DASH_URL}/admin-console", "#3B82F6", category="notifications"),
        text=_txt("Weekly Heatmap", f"Clicks: {total_clicks}\nTemplates: {template_count}"),
    )

@_register("nightly_blocked_export_v7", "Nightly Blocked Export", "Security", "Autonomous engine blocked attempt export")
def build_nightly_blocked_export_v7_email(
    blocked_count: int = 0, window_start: str = "", window_end: str = "",
) -> EmailTemplate:
    c = "#F59E0B" if blocked_count > 0 else "#10B981"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Nightly Blocked Attempt Export</p>
    <p style="margin:0 0 16px;">{_badge(f"{blocked_count} BLOCKED", c)} Autonomous engine export ready.</p>
    {_info_table([_info_row("Blocked Attempts", str(blocked_count), c), _info_row("Window Start", window_start or "—"), _info_row("Window End", window_end or "—")])}
    {_callout("Attached: CSV + JSON export files + Release Readiness Certificate (if available).", "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"[Nightly Export] Autonomous Blocked Attempts — {window_end[:10] if window_end else ''}",
        html=_wrap("Blocked Export", f"{blocked_count} blocked", body, "View Console", f"{DASH_URL}/admin-console", c, category="security"),
        text=_txt("Nightly Export", f"Blocked: {blocked_count}\nWindow: {window_start} → {window_end}"),
    )

@_register("flappy_streak_saver_v7", "Arcade Streak Saver", "Engagement", "Reminder when a Flappy Bird daily-challenge streak is about to expire")
def build_flappy_streak_saver_v7_email(
    user_name: str = "there", streak: int = 1, target: int = 10, personal_best: int = 0,
) -> EmailTemplate:
    streak_label = f"{streak}-day" if streak != 1 else "1-day"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Don't let the flame go out, {user_name}!</p>
    <p style="margin:0 0 16px;">{_badge(f"{streak_label} STREAK AT RISK", "#F59E0B")} Your arcade streak expires at midnight (UTC).</p>
    {_info_table([_info_row("Current streak", f"{streak} day{'s' if streak != 1 else ''}", "#F59E0B"), _info_row("Today's challenge", f"Score {target}+ in one run"), _info_row("Bonus", "+20 XP on completion"), _info_row("Your best", str(personal_best) if personal_best else "—")])}
    {_callout("One quick run is all it takes — beat today's target and your streak lives on.", "#F59E0B")}"""
    return EmailTemplate(
        subject=f"Your {streak_label} arcade streak expires at midnight",
        html=_wrap("Streak Saver", f"{streak_label} streak at risk", body, "Play one quick run", f"{DASH_URL}/features/flappy-bird", "#F59E0B", category="engagement"),
        text=_txt("Streak Saver", f"Hey {user_name}! Your {streak_label} Flappy Bird streak expires at midnight UTC. Score {target}+ in one run to keep it alive (+20 XP bonus): {DASH_URL}/features/flappy-bird"),
    )


@_register("winback_reminder_v7", "Winback Reminder", "Marketing", "Churn recovery winback email with discount")
def build_winback_reminder_v7_email(
    user_name: str = "there", discount_pct: int = 30, discount_code: str = "", discount_expiry: str = "", reminder_number: int = 1,
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">We Miss You, {user_name}!</p>
    <p style="margin:0 0 16px;">{_badge(f"{discount_pct}% OFF", "#8B5CF6")} Your exclusive comeback discount is waiting.</p>
    {_info_table([_info_row("Discount", f"{discount_pct}% Off", "#8B5CF6"), _info_row("Code", discount_code or "—"), _info_row("Expires", discount_expiry or "—"), _info_row("Reminder", f"#{reminder_number}")])}
    {_callout("We've been improving RealAICoach with new features. Come see what's new!", "#8B5CF6")}"""
    subjects = [f"We Miss You, {user_name}! Your {discount_pct}% Discount Awaits", f"Your Spot is Waiting - {discount_pct}% Off Inside", f"Don't Forget Your {discount_pct}% Comeback Discount", f"Last Chance: {discount_pct}% Discount Expires Soon", "We've Been Improving - Come See What's New", f"Final Reminder: {discount_pct}% Off Expiring"]
    return EmailTemplate(
        subject=subjects[min(reminder_number - 1, len(subjects) - 1)],
        html=_wrap("Welcome Back", f"{discount_pct}% Off", body, "Claim Discount", f"{DASH_URL}/pricing", "#8B5CF6", category="marketing"),
        text=_txt("Winback", f"Hey {user_name}! Use code {discount_code} for {discount_pct}% off. Expires: {discount_expiry}"),
    )

@_register("performance_report_v7", "Performance Report", "Notifications", "Platform performance report")
def build_performance_report_v7_email(
    period: str = "Weekly", health_status: str = "Operational", avg_response: str = "45ms",
    error_rate: str = "0.2%", cpu: str = "34%", memory: str = "52%", generated_at: str = "",
) -> EmailTemplate:
    h_color = "#10B981" if "operational" in health_status.lower() else "#F59E0B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">RealAICoach {period} Performance Report</p>
    <p style="margin:0 0 16px;">{_badge(health_status.upper(), h_color)} Automated performance summary.</p>
    {_info_table([_info_row("Status", health_status, h_color), _info_row("Avg Response", avg_response), _info_row("Error Rate", error_rate), _info_row("CPU", cpu), _info_row("Memory", memory), _info_row("Generated", generated_at or "—")])}
    {_callout("Full endpoint-level metrics and scaling events available in the Admin Console.", "#1D4ED8")}"""
    return EmailTemplate(
        subject=f"RealAICoach {period} Performance Report — {generated_at[:10] if generated_at else ''}",
        html=_wrap("Performance Report", f"{period} — {health_status}", body, "View Full Report", f"{DASH_URL}/admin-console", h_color, category="notifications"),
        text=_txt("Performance Report", f"Period: {period}\nStatus: {health_status}\nResponse: {avg_response}\nErrors: {error_rate}"),
    )

@_register("employer_notification_v7", "Employer Notification", "Employer", "Employer event notification")
def build_employer_notification_v7_email(event_type: str = "update", summary: str = "") -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Employer Notification</p>
    <p style="margin:0 0 16px;">{_badge(event_type.upper(), "#0EA5E9")} {summary or "An employer event requires your attention."}</p>
    {_callout("View full details in the Team Intelligence dashboard.", "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"Employer Update: {event_type.title()}",
        html=_wrap("Employer Update", event_type.title(), body, "View Dashboard", f"{DASH_URL}/admin-console", "#0EA5E9", category="employer"),
        text=_txt("Employer Notification", f"Event: {event_type}\n{summary}"),
    )


@_register("ai_health_digest_v7", "AI Health Digest", "AI", "AI platform health digest with engine scores")
def build_ai_health_digest_v7_email(
    platform_score: int = 85, platform_label: str = "Good", analyzed: int = 8,
    scores_summary: str = "", top_actions: str = "", delta: str = "",
) -> EmailTemplate:
    c = "#10B981" if platform_score >= 80 else "#F59E0B" if platform_score >= 60 else "#EF4444"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">AI Platform Health Digest</p>
    <p style="margin:0 0 16px;">{_badge(f"SCORE {platform_score}/100", c)} {_badge(platform_label, c)} {analyzed}/8 AI engines analyzed.{f' {_badge(delta, "#64748B")}' if delta else ''}</p>
    {_info_table([_info_row("Platform Score", f"{platform_score}/100", c), _info_row("Status", platform_label, c), _info_row("Engines Analyzed", f"{analyzed}/8"), _info_row("Scores", scores_summary or "—"), _info_row("Top Actions", top_actions or "All systems healthy")])}
    {_callout("This digest is generated by 8 GPT-4o AI engines: SLA, Conversion, Onboarding, Newsletter, Security, Churn, Performance, and Fraud. View details in the AI Command Center.", "#A855F7")}"""
    return EmailTemplate(
        subject=f"AI Health Digest — Platform Score {platform_score}/100 ({platform_label})",
        html=_wrap("AI Health Digest", f"Score {platform_score}/100 — {platform_label}", body, "Open AI Command Center", f"{DASH_URL}/executive-dashboard", c, category="ai"),
        text=_txt("AI Health Digest", f"Score: {platform_score}/100 ({platform_label})\nEngines: {analyzed}/8\n{scores_summary}\nActions: {top_actions}"),
    )



# ── Daily Meditation (Feature 25) v7 Templates ───────────

@_register(
    "daily_meditation_reminder",
    "Daily Meditation Reminder",
    "Communication",
    "Feature 25 reminder email (v7 enforced)",
)
def build_daily_meditation_reminder_email(
    title: str = "Daily Meditation Reminder",
    message: str = "Take a gentle moment to check in and continue your journey.",
) -> EmailTemplate:
    safe_title = (title or "Daily Meditation Reminder").strip()
    safe_message = (message or "Take a gentle moment to check in and continue your journey.").strip()
    body = f"""{_alert_panel(safe_title, safe_message, "#0F766E", "Reminder")}
    {_callout("Your Daily Meditation space is ready. Open the app to complete one calm, focused step.", "#0F766E")}"""

    return EmailTemplate(
        subject=safe_title,
        html=_wrap(
            "Daily Meditation Reminder",
            safe_message[:120],
            body,
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
            "#0F766E",
            category="communication",
        ),
        text=_txt(
            "Daily Meditation Reminder",
            f"{safe_title}\n{safe_message}",
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
        ),
    )


@_register(
    "daily_meditation_prayer_audio_drop",
    "Daily Meditation Prayer Audio Drop",
    "Communication",
    "Feature 25 prayer audio daily-drop email (v7 enforced)",
)
def build_daily_meditation_prayer_audio_drop_email(
    date_key: str = "",
    title: str = "3 new animated prayer audios are ready",
    message: str = "Today's drop is live. Tap to listen in Daily Meditation.",
    categories: Optional[List[str]] = None,
    items: Optional[List[dict]] = None,
) -> EmailTemplate:
    categories = categories or []
    items = items or []
    safe_title = (title or "3 new animated prayer audios are ready").strip()
    safe_message = (message or "Today's drop is live. Tap to listen in Daily Meditation.").strip()
    cat_line = ", ".join([str(c) for c in categories[:3] if str(c).strip()]) or "Prayer"
    rows = "".join(
        f'<tr><td style="padding:6px 0;border-bottom:1px solid #E2E8F0;">'
        f'<span style="color:#0F172A;font-size:13px;font-weight:600;">{str(it.get("title") or "Prayer Audio")}</span>'
        f'<div style="color:#475569;font-size:12px;">{str(it.get("scripture") or "")}</div></td></tr>'
        for it in items[:3]
    )
    if not rows:
        rows = '<tr><td style="padding:6px 0;color:#475569;font-size:13px;">New audio reflections are now available.</td></tr>'

    date_label = str(date_key or "today").strip() or "today"
    body = f"""{_alert_panel(safe_title, safe_message, "#0F766E", "Prayer Audio Drop")}
    {_info_table([_info_row("Published", date_label), _info_row("Categories", cat_line, "#0F766E")])}
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">{rows}</table>
    {_callout("Open Daily Meditation to listen, save favorites, and continue your prayer journey.", "#0F766E")}"""

    subject = f"Daily Meditation · 3 new prayer audios ({date_label})"
    return EmailTemplate(
        subject=subject,
        html=_wrap(
            "Daily Meditation Prayer Audio Drop",
            safe_message[:120],
            body,
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
            "#0F766E",
            category="communication",
        ),
        text=_txt(
            "Daily Meditation Prayer Audio Drop",
            f"{safe_title}\n{safe_message}\nCategories: {cat_line}",
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
        ),
    )


@_register(
    "daily_meditation_weekly_digest",
    "Daily Meditation Weekly Digest",
    "Communication",
    "Feature 25 weekly digest email (v7 enforced)",
)
def build_daily_meditation_weekly_digest_email(
    days: int = 7,
    dominant_theme: str = "steady",
    headline: str = "",
    encouragement: str = "",
    snippets: Optional[List[dict]] = None,
    checkins: int = 0,
    journal_entries: int = 0,
    somatic_sessions: int = 0,
) -> EmailTemplate:
    snippets = snippets or []
    safe_days = max(1, int(days or 7))
    safe_theme = str(dominant_theme or "steady").strip() or "steady"
    safe_headline = (headline or f"In the last {safe_days} days, your reflection activity stayed active.").strip()
    safe_encouragement = (encouragement or "Presence and honesty matter more than perfect consistency.").strip()

    snippet_rows = "".join(
        f'<li><strong>{str(sn.get("title") or "Scripture")}</strong> — {str(sn.get("scripture") or "")}</li>'
        for sn in snippets[:3]
    )
    if not snippet_rows:
        snippet_rows = "<li><strong>Guided Light</strong> — Psalm 119:105</li>"

    body = f"""{_alert_panel(
        f"Your {safe_days}-day Daily Meditation Digest",
        safe_headline,
        "#0F766E",
        "Weekly Digest"
    )}
    {_info_table([
        _info_row("Dominant Theme", safe_theme.title(), "#0F766E"),
        _info_row("Check-ins", str(int(checkins or 0))),
        _info_row("Journal Entries", str(int(journal_entries or 0))),
        _info_row("Somatic Sessions", str(int(somatic_sessions or 0))),
    ])}
    <p style="margin:0 0 12px;color:#334155;">{safe_encouragement}</p>
    <h3 style="margin:0 0 8px;font-size:15px;color:#0F172A;">Dynamic scripture snippets</h3>
    <ul style="padding-left:18px;margin:0 0 14px;color:#0F172A;">{snippet_rows}</ul>
    {_callout("Suggested next step: complete one Heart Check-In and one somatic invitation today.", "#0F766E")}"""

    subject = f"Your {safe_days}-day Daily Meditation digest · theme: {safe_theme.title()}"
    return EmailTemplate(
        subject=subject,
        html=_wrap(
            "Daily Meditation Weekly Digest",
            f"Theme: {safe_theme.title()} · {safe_days}-day summary",
            body,
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
            "#0F766E",
            category="communication",
        ),
        text=_txt(
            "Daily Meditation Weekly Digest",
            f"Theme: {safe_theme.title()}\n{safe_headline}\nCheck-ins: {int(checkins or 0)}\nJournal: {int(journal_entries or 0)}\nSomatic: {int(somatic_sessions or 0)}",
            "Open Daily Meditation",
            f"{DASH_URL}/features/daily-meditation",
        ),
    )


# ── AI Learning Hub Weekly Release ────────────────────────

@_register("learning_hub_weekly_release", "Weekly Learning Release", "AI", "AI Learning Hub weekly course publication notification")
def build_learning_hub_weekly_release_email(
    week_key: str = "2026-W17",
    courses: list = None,
) -> EmailTemplate:
    if courses is None:
        courses = [
            "AI Career Acceleration for Technical Leaders",
            "Data Productization for Income Growth",
            "Mastering No-Code AI Automation Systems",
            "AI Sales Enablement and Conversion Loops",
            "Operational AI Governance for Career Enhancement",
        ]
    course_items = "".join(
        f'<tr><td style="padding:6px 0;border-bottom:1px solid #F1F5F9;">'
        f'<span style="display:inline-block;width:6px;height:6px;border-radius:3px;background:#7C3AED;margin-right:8px;vertical-align:middle;"></span>'
        f'<span style="color:#0F172A;font-size:13px;">{c}</span></td></tr>'
        for c in courses
    )
    body = f"""{_alert_panel(
        f"Weekly Learning Release · {week_key}",
        f"{len(courses)} new enterprise courses generated and published automatically.",
        "#7C3AED",
        "New Courses"
    )}
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
      {course_items}
    </table>
    {_callout("These courses are AI-generated by the Learning Hub engine. Enroll now to start your next execution sprint.", "#7C3AED")}"""

    return EmailTemplate(
        subject=f"Weekly Learning Release — {week_key} ({len(courses)} new courses)",
        html=_wrap(
            "Weekly Learning Release",
            f"{len(courses)} new courses published — {week_key}",
            body,
            "Open Learning Hub",
            f"{DASH_URL}/features/ai-learning-hub",
            "#7C3AED",
            category="ai",
        ),
        text=_txt(
            "Weekly Learning Release",
            f"{len(courses)} new courses for {week_key}:\n" + "\n".join(f"  - {c}" for c in courses),
            "Open Learning Hub",
            f"{DASH_URL}/features/ai-learning-hub",
        ),
    )


# ── Enrollment Kickoff Email ──────────────────────────

@_register("learning_hub_enrollment_kickoff", "Course Enrollment Kickoff", "AI", "AI Learning Hub enrollment welcome with course cover art and first-lesson CTA")
def build_learning_hub_enrollment_kickoff_email(
    learner_name: str = "Learner",
    course_title: str = "AI Career Acceleration",
    category: str = "AI",
    difficulty: str = "intermediate",
    module_count: int = 5,
    first_lesson_title: str = "Introduction",
    cover_url: str = "",
) -> EmailTemplate:
    cover_block = (
        f'<img src="{cover_url}" alt="{course_title}" width="100%" '
        f'style="display:block;width:100%;max-width:560px;border-radius:12px;margin:0 0 18px;" />'
        if cover_url else ""
    )
    body = f"""{cover_block}{_alert_panel(
        f"You're enrolled — {course_title}",
        f"{category} · {str(difficulty).capitalize()} · {module_count} modules. Your seat is locked in, {learner_name}.",
        "#7C3AED",
        "Enrollment Confirmed"
    )}
    <p style="color:#0F172A;font-size:14px;line-height:1.6;margin:0 0 14px;">Momentum starts with the first lesson. Play <strong>{first_lesson_title}</strong> today to activate your learning streak and today's missions.</p>
    {_callout("Learners who start within 24 hours of enrolling are 3x more likely to finish and earn the verified certificate.", "#7C3AED")}"""

    return EmailTemplate(
        subject=f"You're enrolled: {course_title}",
        html=_wrap(
            "Enrollment Confirmed",
            f"{course_title} — start your first lesson",
            body,
            "Start First Lesson",
            f"{DASH_URL}/ai-learning-hub?tab=journey",
            "#7C3AED",
            category="ai",
        ),
        text=_txt(
            "Enrollment Confirmed",
            f"You're enrolled in {course_title} ({category}, {module_count} modules). Start '{first_lesson_title}' today to activate your streak.",
            "Start First Lesson",
            f"{DASH_URL}/ai-learning-hub?tab=journey",
        ),
    )


# ── Certificate Completion Email ──────────────────────────

@_register("learning_hub_certificate_award", "Certificate Completion", "AI", "AI Learning Hub certificate award notification with PDF attachment")
def build_certificate_completion_email(
    learner_name: str = "Learner",
    course_title: str = "AI Learning Course",
    signer_name: str = "RealAICoach",
    signer_role: str = "Platform",
    verification_id: str = "",
    verify_url: str = "",
    linkedin_share_url: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel("Certificate Awarded", f"Congratulations, {learner_name}! You completed {course_title}.", "#2563EB", "Certified")}
    {_info_table([
        _info_row("Course", course_title, "#2563EB"),
        _info_row("Recipient", learner_name),
        _info_row("Signed By", signer_name),
        _info_row("Role", signer_role),
        _info_row("Certificate Ref", verification_id or "--"),
    ])}
    {_callout("Your signed certificate is attached as a PDF. Use the links below to view your certificate page or share on LinkedIn.", "#2563EB")}"""

    return EmailTemplate(
        subject=f"Your RealAICoach certificate is ready — {course_title}",
        html=_wrap(
            "Certificate Awarded",
            f"{learner_name} completed {course_title}",
            body,
            "Open Certificate Page",
            verify_url or f"{DASH_URL}/features/ai-learning-hub",
            "#2563EB",
            secondary_cta_label="Share on LinkedIn",
            secondary_cta_url=linkedin_share_url or "#",
            category="ai",
        ),
        text=_txt(
            "Certificate Awarded",
            f"Congratulations {learner_name}! You completed {course_title}.\nSigned by: {signer_name}\nRef: {verification_id}",
            "Open Certificate",
            verify_url or f"{DASH_URL}/features/ai-learning-hub",
        ),
    )


@_register("travel_visa_certificate_award", "Travel Visa Certificate", "travel", "Travel Visa Academy certificate award notification with premium PDF attachment")
def build_travel_visa_certificate_email(
    learner_name: str = "Learner",
    course_title: str = "Travel Visa Course",
    cert_id: str = "",
    score: "Optional[int]" = None,
    issued_date: str = "",
    verify_url: str = "",
    download_url: str = "",
) -> EmailTemplate:
    score_row = _info_row("Final Score", f"{score}%", "#0F766E") if score is not None else ""
    body = f"""{_alert_panel("Certificate Awarded", f"Congratulations, {learner_name}! You completed {course_title}.", "#0F766E", "Certified")}
    {_info_table([
        _info_row("Course", course_title, "#0F766E"),
        _info_row("Recipient", learner_name),
        score_row,
        _info_row("Certificate ID", cert_id or "--"),
        _info_row("Issued", issued_date or "--"),
        _info_row("Issuer", "RealAICoach Travel Visa Academy"),
    ])}
    {_callout("Your premium certificate is attached as a PDF. It includes a QR code and verification link so anyone can confirm its authenticity instantly.", "#0F766E")}"""

    return EmailTemplate(
        subject=f"Your Travel Visa certificate is ready — {course_title}",
        html=_wrap(
            "Certificate Awarded",
            f"{learner_name} completed {course_title}",
            body,
            "Verify Certificate",
            verify_url or f"{DASH_URL}/features/travel-visa",
            "#0F766E",
            secondary_cta_label="Download PDF",
            secondary_cta_url=download_url or "#",
            category="travel",
        ),
        text=_txt(
            "Certificate Awarded",
            f"Congratulations {learner_name}! You completed {course_title}.\nCertificate: {cert_id}\nVerify: {verify_url}",
            "Verify Certificate",
            verify_url or f"{DASH_URL}/features/travel-visa",
        ),
    )


# ── Accessibility Audit Alert ─────────────────────────────@_register("accessibility_audit_alert", "Accessibility Audit Alert", "Communication", "WCAG 2.1 AA accessibility audit results")
def build_accessibility_audit_alert_email(
    score: int = 100,
    total_issues: int = 0,
    critical_count: int = 0,
    category_breakdown: str = "",
) -> EmailTemplate:
    if critical_count > 0 or score < 50:
        status = "CRITICAL"
    elif score >= 90:
        status = "PASSED"
    else:
        status = "WARNING"
    sc = "#10B981" if status == "PASSED" else "#F59E0B" if status == "WARNING" else "#EF4444"

    body = f"""{_alert_panel(f"Accessibility Score: {score}/100", f"WCAG 2.1 AA — {total_issues} issue(s) found, {critical_count} critical.", sc, status)}
    {_info_table([
        _info_row("Score", f"{score}/100", sc),
        _info_row("Status", status, sc),
        _info_row("Total Issues", str(total_issues), "#EF4444" if total_issues > 0 else "#10B981"),
        _info_row("Critical", str(critical_count), "#EF4444" if critical_count > 0 else "#10B981"),
    ])}
    {_callout(category_breakdown or "Automated WCAG 2.1 AA audit completed. View full report in the admin console.", sc)}"""

    return EmailTemplate(
        subject=f"Accessibility Audit: {status} — Score {score}/100",
        html=_wrap("Accessibility Report", f"Score {score}/100 — {status}", body, "Open Accessibility Panel", f"{DASH_URL}/admin-console", sc, category="communication"),
        text=_txt("Accessibility Report", f"Score: {score}/100. Status: {status}. Issues: {total_issues}, Critical: {critical_count}."),
    )


# ── Code Health Alert ─────────────────────────────────────

@_register("code_health_alert", "Code Health Alert", "Communication", "Code health scan results with before/after comparison")
def build_code_health_alert_email(
    score_before: int = 0,
    score_after: int = 0,
    critical_passed: bool = True,
    critical_issues: int = 0,
    fixes_applied: int = 0,
    gate_status: str = "PASSED",
) -> EmailTemplate:
    sc = "#10B981" if critical_passed else "#EF4444"
    delta = score_after - score_before
    delta_label = f"+{delta}" if delta > 0 else str(delta)

    body = f"""{_alert_panel(f"Code Health: {gate_status}", f"Score: {score_before} → {score_after} ({delta_label}). {fixes_applied} fixes applied.", sc, gate_status)}
    {_info_table([
        _info_row("Score Before", str(score_before)),
        _info_row("Score After", str(score_after), "#10B981" if score_after > score_before else "#EF4444"),
        _info_row("Delta", delta_label, "#10B981" if delta >= 0 else "#EF4444"),
        _info_row("Critical Gate", "PASSED" if critical_passed else f"FAILED ({critical_issues} issues)", sc),
        _info_row("Fixes Applied", str(fixes_applied), "#2563EB"),
    ])}"""

    return EmailTemplate(
        subject=f"Code Health: {gate_status} — Score {score_after}/100",
        html=_wrap("Code Health Report", f"Score {score_after}/100 — {gate_status}", body, "Open Code Health", f"{DASH_URL}/admin-console", sc, category="communication"),
        text=_txt("Code Health Report", f"Score: {score_before} → {score_after}. Gate: {gate_status}. Fixes: {fixes_applied}. Critical: {'Passed' if critical_passed else f'Failed ({critical_issues})'}"),
    )


# ── Admin Health Digest ───────────────────────────────────

@_register("admin_health_digest", "Admin Health Digest", "Communication", "Daily one-line admin console health ping (sentinel state + top crashing panels)")
def build_admin_health_digest_email(
    severity: str = "warning",
    title: str = "Admin console all-clear",
    summary: str = "All admin routes healthy and zero panel crashes reported in the last 24 hours.",
    total_errors_24h: int = 0,
    healthy_routes: int = 3,
    total_routes: int = 3,
    unhealthy_routes: Optional[list] = None,
    top_panels: Optional[list] = None,
    generated_at: str = "",
) -> EmailTemplate:
    unhealthy_routes = unhealthy_routes or []
    top_panels = top_panels or []

    sev_color = "#EF4444" if severity == "critical" else ("#F59E0B" if unhealthy_routes or total_errors_24h > 0 else "#10B981")
    badge = severity.upper() if severity != "warning" or unhealthy_routes or total_errors_24h > 0 else "ALL CLEAR"

    rows = [
        _info_row("Healthy routes", f"{healthy_routes} / {total_routes}", "#10B981" if healthy_routes == total_routes else "#F59E0B"),
        _info_row("Panel crashes (24h)", str(total_errors_24h), "#10B981" if total_errors_24h == 0 else "#EF4444"),
    ]
    if unhealthy_routes:
        rows.append(_info_row("Unhealthy routes", ", ".join(unhealthy_routes), "#EF4444"))
    for i, p in enumerate(top_panels[:3], 1):
        label = p.get("panel_name") or p.get("panel_id") or "unknown"
        rows.append(_info_row(
            f"#{i} {label}",
            f"{p.get('count', 0)} crash(es) · {p.get('unique_clients', 0)} user(s)",
            "#EF4444",
        ))
    if generated_at:
        rows.append(_info_row("Generated at", generated_at, "#64748B"))

    if not unhealthy_routes and total_errors_24h == 0:
        callout_text = "All 94 admin panels rendered without crashes in the last 24 hours. ✓"
        callout_color = "#10B981"
    elif unhealthy_routes:
        callout_text = (
            f"<strong>{len(unhealthy_routes)} admin route(s) flipped to unhealthy.</strong> "
            "The sentinel auto-fix hook has already run once; if the route stays unhealthy, "
            "investigate the linked code_health report for remediation details."
        )
        callout_color = "#EF4444"
    else:
        callout_text = (
            f"<strong>{total_errors_24h} panel crash event(s)</strong> reported by the "
            "client ErrorBoundary. No sentinel route is unhealthy, so triage at your own pace."
        )
        callout_color = "#F59E0B"

    body = f"""{_alert_panel(title, summary, sev_color, badge)}
    {_info_table(rows)}
    {_callout(callout_text, callout_color)}"""

    text_lines = [
        f"Admin Health Digest — {severity.upper()}",
        "",
        title,
        summary,
        "",
        f"Healthy routes: {healthy_routes}/{total_routes}",
        f"Panel crashes (24h): {total_errors_24h}",
    ]
    if unhealthy_routes:
        text_lines.append(f"Unhealthy routes: {', '.join(unhealthy_routes)}")
    for i, p in enumerate(top_panels[:3], 1):
        label = p.get("panel_name") or p.get("panel_id") or "unknown"
        text_lines.append(
            f"  #{i} {label}: {p.get('count', 0)} crashes, {p.get('unique_clients', 0)} users"
        )

    subject_tag = "ALL-CLEAR" if not unhealthy_routes and total_errors_24h == 0 else severity.upper()
    return EmailTemplate(
        subject=f"[{subject_tag}] {title}",
        html=_wrap(
            "Admin Health Digest",
            title,
            body,
            "Open Admin Console",
            f"{DASH_URL}/admin-console?category=dev&tab=code-health",
            sev_color,
            category="communication",
        ),
        text=_txt("Admin Health Digest", "\n".join(text_lines)),
    )


# ── Production Anomaly Alert ──────────────────────────────

@_register("production_anomaly_alert", "Production Anomaly Alert", "Security", "Production anomaly detection alert from monitoring pipeline")
def build_production_anomaly_alert_email(
    anomaly_count: int = 0,
    anomalies: list = None,
    auto_heal_triggered: bool = False,
) -> EmailTemplate:
    if anomalies is None:
        anomalies = [{"type": "metric_spike", "severity": "high", "detail": "Sample anomaly"}]

    anomaly_rows = "".join(
        _info_row(a.get("type", "unknown"), f"{a.get('severity', '?')} — {a.get('detail', '')}", "#EF4444" if a.get("severity") == "critical" else "#F59E0B")
        for a in anomalies
    )
    heal_text = "Auto-heal pipeline triggered." if auto_heal_triggered else "No auto-heal action taken."

    body = f"""{_alert_panel("Production Anomaly Detected", f"{len(anomalies)} anomalie(s) detected. {heal_text}", "#EF4444", "Alert")}
    {_info_table([anomaly_rows, _info_row("Auto-Heal", "Triggered" if auto_heal_triggered else "Not triggered", "#059669" if auto_heal_triggered else "#64748B")])}"""

    severity_list = ", ".join(a.get("type", "?") for a in anomalies)
    return EmailTemplate(
        subject=f"[ALERT] Production Anomaly Detected: {severity_list}",
        html=_wrap("Anomaly Alert", f"{len(anomalies)} anomalies detected", body, "Open Monitoring", f"{DASH_URL}/admin-console", "#EF4444", category="security"),
        text=_txt("Anomaly Alert", f"{len(anomalies)} anomalies: {severity_list}. {heal_text}"),
    )


# ── Integrity Preview Alert ──────────────────────────────

@_register("integrity_preview_alert", "Integrity Preview Alert", "Communication", "Preview/demo alert for integrity system")
def build_integrity_preview_alert_email(
    preview_type: str = "integrity",
    preview_html: str = "",
) -> EmailTemplate:
    body = f"""{_alert_panel(f"Preview: {preview_type.replace('_', ' ').title()}", "This is a preview/demo alert from the integrity system.", "#3B82F6", "Preview")}
    <div class="em-force-light-card" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;margin:16px 0;">
      {preview_html or '<p class="em-text" style="color:#475569;font-size:13px;margin:0;">No preview content available.</p>'}
    </div>"""

    return EmailTemplate(
        subject=f"Preview — {preview_type.replace('_', ' ').title()} Alert",
        html=_wrap("System Preview", f"Preview: {preview_type}", body, "Open Admin Console", f"{DASH_URL}/admin-console", "#3B82F6", category="communication"),
        text=_txt("System Preview", f"Preview type: {preview_type}"),
    )


# ── Admin Outbound Reply ──────────────────────────────────

@_register("security_runbook_monitor_report", "Security — Runbook Monitor Report", "Security",
           "Automated security key-rotation runbook monitor report (RAG status, metrics, risks, milestones)")
def build_security_runbook_monitor_report_email(
    rag: str = "AMBER",
    monitor_run_id: str = "",
    trigger_source: str = "",
    executed_at: str = "",
    mode: str = "SAFE_AUTO",
    metrics: dict | None = None,
    top_risks: list | None = None,
    milestones: dict | None = None,
    bundle_id: str = "N/A",
    bundle_generated_at: str = "N/A",
    send_reason: str = "",
) -> EmailTemplate:
    import html as _html

    rag = (rag or "AMBER").strip().upper()
    rag_colors = {"RED": "#DC2626", "AMBER": "#D97706", "GREEN": "#059669"}
    accent = rag_colors.get(rag, "#D97706")
    metrics = metrics or {}
    top_risks = top_risks or []
    milestones = milestones or {}
    reason_labels = {
        "rag_change": "Status change alert",
        "daily_summary": "Daily summary",
        "manual": "Manually triggered run",
    }
    reason_text = reason_labels.get(send_reason, "Automated monitor report")

    def _row(label: str, value) -> str:
        return (f"<tr><td style='padding:7px 12px;border-bottom:1px solid #E2E8F0;color:#475569;font-size:13px;'>{_html.escape(str(label))}</td>"
                f"<td style='padding:7px 12px;border-bottom:1px solid #E2E8F0;font-weight:700;color:#0F172A;font-size:13px;'>{_html.escape(str(value))}</td></tr>")

    snapshot_rows = "".join([
        _row("Run ID", monitor_run_id or "—"),
        _row("Trigger Source", trigger_source or "—"),
        _row("Executed At", executed_at or "—"),
        _row("Mode", mode),
    ])
    metric_rows = "".join(_row(label, value) for label, value in [
        ("API Rotate Ready", metrics.get("api_rotate_ready", 0)),
        ("API Probe Ready", metrics.get("api_probe_only_ready", 0)),
        ("Manual By Constraint", metrics.get("manual_by_constraint", 0)),
        ("Rotate Contract Hard Blocked", metrics.get("rotate_contract_hard_blocked", 0)),
        ("Policy Gate Passed", metrics.get("policy_gate_passed")),
        ("SIEM Webhook Configured", metrics.get("siem_webhook_configured")),
        ("SIEM Webhook Validated (this run)", metrics.get("siem_webhook_validated")),
    ])
    risks_html = "".join(
        f"<li style='color:#475569;font-size:13px;line-height:1.7;margin-bottom:4px;'>{_html.escape(str(r))}</li>"
        for r in top_risks[:5]
    )
    milestone_rows = "".join(_row(label, milestones.get(key) or "—") for key, label in
                             [("d30", "30-day"), ("d60", "60-day"), ("d90", "90-day")])

    def _section(title: str) -> str:
        return f"<h3 style='color:#0F172A;font-size:14px;margin:18px 0 8px;'>{_html.escape(title)}</h3>"

    body = (
        _alert_panel("Security Runbook Monitor",
                     f"Automated Go-Live runbook monitoring cycle completed — overall status {rag}. {reason_text}. "
                     "This is a scheduled system report, not a support conversation.",
                     accent, rag)
        + _section("Continuous Monitoring Snapshot (Safe Auto)")
        + f"<table style='border-collapse:collapse;width:100%;'>{snapshot_rows}</table>"
        + _section("Key Metrics")
        + f"<table style='border-collapse:collapse;width:100%;'>{metric_rows}</table>"
        + _section("Top Risks")
        + f"<ul style='margin:0;padding-left:18px;'>{risks_html}</ul>"
        + _section("30 / 60 / 90 Day Closure Milestones")
        + f"<table style='border-collapse:collapse;width:100%;'>{milestone_rows}</table>"
        + _section("Latest Compliance Reference")
        + f"<table style='border-collapse:collapse;width:100%;'>{_row('Bundle ID', bundle_id or 'N/A')}{_row('Generated At', bundle_generated_at or 'N/A')}</table>"
        + _callout("Automated report from the Security Key-Rotation Runbook Monitor. "
                   "Manage cadence and recipients in the Operations Console → Security.", accent)
    )
    return EmailTemplate(
        subject=f"[Security Runbook Monitor] {rag} — Go-Live Runbook Status ({(executed_at or '')[:16] or 'latest run'})",
        html=_wrap("Security Runbook Monitor", f"Overall status: {rag} — {reason_text}", body,
                   "Open Operations Console", f"{DASH_URL}/admin/operations",
                   accent, category="security"),
        text=_txt(f"Security Runbook Monitor — {rag}",
                  f"{reason_text}. Run {monitor_run_id} at {executed_at} ({mode}, trigger: {trigger_source}). "
                  f"Overall RAG: {rag}. Top risks: " + "; ".join(str(r) for r in top_risks[:5])),
    )


@_register("admin_outbound", "Admin Outbound Reply", "Support", "Admin reply to user inquiries from email console")
def build_admin_outbound_email(
    body: str = "",
    original_subject: str = "",
) -> EmailTemplate:
    import html as _html
    safe_body = _html.escape(body).replace("\n", "<br/>")
    ref_text = f' regarding <strong>"{_html.escape(original_subject)}"</strong>' if original_subject else ""

    body_html = f"""{_alert_panel("Support Reply", f"The RealAICoach team has responded to your inquiry{ref_text}.", "#1D4ED8", "Support")}
    <div style="padding:16px 0;">
      <p class="em-text" style="color:#374151;font-size:14px;line-height:1.7;white-space:pre-wrap;margin:0;">{safe_body}</p>
    </div>
    {_callout("If you have additional questions, reply to this email or visit the help center.", "#1D4ED8")}"""

    return EmailTemplate(
        subject=f"Re: {original_subject}" if original_subject else "RealAICoach Support Reply",
        html=_wrap("Support Reply", "Response to your inquiry", body_html, "Open Dashboard", f"{DASH_URL}/", "#1D4ED8", category="support"),
        text=_txt("Support Reply", f"{body}\n\nBest regards,\nRealAICoach Support Team"),
    )



# ── Admin LLM Daily Digest ────────────────────────────────

@_register("admin_llm_daily_digest", "Admin LLM Daily Digest", "AI", "Daily digest of yesterday's LLM spend + month-to-date budget burn")
def build_admin_llm_daily_digest_email(
    date_label: str = "",
    yesterday_cost_usd: float = 0.0,
    yesterday_calls: int = 0,
    yesterday_tokens: int = 0,
    mtd_cost_usd: float = 0.0,
    monthly_budget_usd: float = 0.0,
    burn_pct: float = 0.0,
    projected_month_end_usd: float = 0.0,
    top_model: str = "—",
    top_model_cost_usd: float = 0.0,
    top_feature: str = "—",
    top_feature_cost_usd: float = 0.0,
    error_rate_pct: float = 0.0,
    avg_latency_ms: int = 0,
) -> EmailTemplate:
    # Burn color
    if burn_pct >= 90:
        burn_color = "#EF4444"
        burn_label = "OVER"
    elif burn_pct >= 70:
        burn_color = "#F59E0B"
        burn_label = "WARN"
    else:
        burn_color = "#10B981"
        burn_label = "OK"

    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">LLM Daily Digest — {date_label}</p>
    <p style="margin:0 0 16px;">{_badge(f"BUDGET {burn_label}", burn_color)} {_badge(f"{burn_pct:.1f}% BURN", burn_color)} Yesterday: <strong>${yesterday_cost_usd:,.2f}</strong> · MTD: <strong>${mtd_cost_usd:,.2f}</strong> of ${monthly_budget_usd:,.2f}.</p>
    {_info_table([
        _info_row("Yesterday Spend", f"${yesterday_cost_usd:,.4f}"),
        _info_row("Yesterday Calls", f"{yesterday_calls:,}"),
        _info_row("Yesterday Tokens", f"{yesterday_tokens:,}"),
        _info_row("Month-to-Date Spend", f"${mtd_cost_usd:,.2f}"),
        _info_row("Monthly Budget", f"${monthly_budget_usd:,.2f}"),
        _info_row("Budget Burn", f"{burn_pct:.1f}%", burn_color),
        _info_row("Projected Month-End", f"${projected_month_end_usd:,.2f}", "#EF4444" if projected_month_end_usd > monthly_budget_usd else "#10B981"),
        _info_row("Top Model (30d)", f"{top_model} · ${top_model_cost_usd:,.2f}"),
        _info_row("Top Feature (30d)", f"{top_feature} · ${top_feature_cost_usd:,.2f}"),
        _info_row("Error Rate (30d)", f"{error_rate_pct:.2f}%"),
        _info_row("Avg Latency (30d)", f"{avg_latency_ms} ms"),
    ])}
    {_callout("Open the LLM Usage & Billing dashboard to drill into per-user, per-feature, and per-model trends.", burn_color)}"""
    return EmailTemplate(
        subject=f"LLM Daily Digest — ${yesterday_cost_usd:,.2f} yesterday · {burn_pct:.0f}% MTD burn",
        html=_wrap("LLM Daily Digest", f"{date_label} · {burn_label}", body, "Open LLM Billing", f"{DASH_URL}/admin/llm-billing", burn_color, category="ai"),
        text=_txt(
            "LLM Daily Digest",
            f"Date: {date_label}\nYesterday: ${yesterday_cost_usd:,.4f} ({yesterday_calls:,} calls, {yesterday_tokens:,} tokens)\n"
            f"MTD: ${mtd_cost_usd:,.2f} / ${monthly_budget_usd:,.2f} ({burn_pct:.1f}% burn) · {burn_label}\n"
            f"Projected: ${projected_month_end_usd:,.2f}\n"
            f"Top model: {top_model} (${top_model_cost_usd:,.2f})\nTop feature: {top_feature} (${top_feature_cost_usd:,.2f})\n"
            f"Error rate: {error_rate_pct:.2f}%  Latency: {avg_latency_ms}ms"
        ),
    )


# ── GDPR Auto-Purge Daily Digest ────────────────────────────────────
@_register(
    "careers_gdpr_purge_daily_digest",
    "Careers GDPR Auto-Purge Daily Digest",
    "Compliance",
    "Daily admin email summarising yesterday's GDPR auto-purge run for the ATS."
)
def build_careers_gdpr_purge_daily_digest(
    run_date_label: str = "",
    purged_count: int = 0,
    retention_days: int = 0,
    oldest_purged_days: int = 0,
    newest_purged_days: int = 0,
    audit_rows_written: int = 0,
    run_trigger: str = "apscheduler_daily",
    ran_at: str = "",
    auto_purge_enabled: bool = True,
    policy_actor: str = "scheduler",
    dashboard_url: str = "",
) -> EmailTemplate:
    """Daily compliance email: yesterday's GDPR auto-purge stats."""
    if not dashboard_url:
        dashboard_url = f"{DASH_URL}/executive-dashboard?tab=careers"

    status_label = "Ran"
    status_color = "#10B981"
    if not auto_purge_enabled:
        status_label = "Skipped (disabled)"
        status_color = "#F59E0B"
    elif purged_count == 0:
        status_label = "No-op"
        status_color = "#64748B"

    headline = (
        f"GDPR Auto-Purge — {run_date_label or 'yesterday'}"
        if purged_count else
        f"GDPR Auto-Purge — clean ({run_date_label or 'yesterday'})"
    )
    lead_line = (
        f"Retention window <strong>{retention_days}d</strong> · "
        f"<strong>{purged_count}</strong> candidate record(s) redacted · "
        f"<strong>{audit_rows_written}</strong> audit row(s) written."
        if purged_count else
        f"No candidate records hit the <strong>{retention_days}d</strong> retention window. "
        "Policy verified, no action taken."
    )
    rows = [
        _info_row("Status", status_label, status_color),
        _info_row("Run trigger", run_trigger),
        _info_row("Ran at (UTC)", ran_at or "—"),
        _info_row("Retention window", f"{retention_days} day(s)"),
        _info_row("Records purged", f"{purged_count}"),
        _info_row("Audit rows written", f"{audit_rows_written}"),
    ]
    if purged_count:
        rows.append(_info_row("Oldest purged (age)", f"{oldest_purged_days} day(s)"))
        rows.append(_info_row("Newest purged (age)", f"{newest_purged_days} day(s)"))
    rows.append(_info_row("Policy actor", policy_actor))

    callout_color = "#10B981" if purged_count else "#64748B"
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">{headline}</p>
<p style="margin:0 0 16px;">{_badge(f"PURGED {purged_count}", status_color)} {_badge(f"WINDOW {retention_days}d", "#0EA5E9")} {lead_line}</p>
{_info_table(rows)}
{_callout("Compliance audit trail updated. Open the Careers → GDPR tab for the full log and retention policy.", callout_color)}"""

    subject = (
        f"GDPR auto-purge: {purged_count} candidate(s) purged ({run_date_label})"
        if purged_count else
        f"GDPR auto-purge clean: 0 purged ({run_date_label})"
    )
    return EmailTemplate(
        subject=subject,
        html=_wrap(
            "GDPR Auto-Purge",
            f"{run_date_label or 'Daily'} · {status_label}",
            body,
            "Open Careers GDPR",
            dashboard_url,
            status_color,
            category="security",
        ),
        text=_txt(
            "GDPR Auto-Purge Daily Digest",
            f"Date: {run_date_label}\n"
            f"Status: {status_label}\n"
            f"Retention window: {retention_days}d\n"
            f"Purged: {purged_count} record(s)\n"
            f"Audit rows: {audit_rows_written}\n"
            f"Run trigger: {run_trigger}\n"
            f"Ran at: {ran_at}\n"
            + (f"Oldest purged: {oldest_purged_days}d old\nNewest purged: {newest_purged_days}d old\n" if purged_count else ""),
            "Open Careers GDPR",
            dashboard_url,
        ),
    )


# ── Careers scheduling invite (to applicant) ─────────────────────
@_register(
    "careers_scheduling_invite",
    "Careers Scheduling Invite (Applicant)",
    "Careers",
    "Magic-link email inviting the applicant to self-serve pick an interview slot."
)
def build_careers_scheduling_invite(
    applicant_name: str = "",
    role_title: str = "",
    interviewer_name: str = "",
    schedule_link: str = "",
    duration_minutes: int = 45,
) -> EmailTemplate:
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Pick a time that works for you</p>
<p style="margin:0 0 12px;">Hi {applicant_name or 'there'}, we'd love to meet about the <strong>{role_title or 'role'}</strong> opportunity. Open the link below to pick a {duration_minutes}-minute slot — times are shown in <strong>your</strong> time zone automatically.</p>
{_callout(f'Interviewer: {interviewer_name or "our team"} · Duration: {duration_minutes} min · Choose any slot.', "#0EA5E9")}"""
    return EmailTemplate(
        subject=f"Pick an interview time · {role_title or 'RealAICoach'}",
        html=_wrap(
            "Schedule your interview",
            "Tap a slot that works for you.",
            body,
            "Open scheduler",
            schedule_link or DASH_URL,
            "#0EA5E9",
            category="careers",
        ),
        text=_txt(
            "Schedule your interview",
            f"Hi {applicant_name or 'there'}, we'd love to meet about {role_title or 'the role'}. "
            f"Open this link to pick a {duration_minutes}-minute slot in YOUR time zone:",
            "Open scheduler",
            schedule_link or DASH_URL,
        ),
    )


# ── Careers scheduling confirmation (to applicant) ────────────────
@_register(
    "careers_scheduling_confirmation_applicant",
    "Careers Scheduling Confirmation (Applicant)",
    "Careers",
    "Sent to the applicant after self-serve booking. Includes TZ-aware ICS + GCal/Outlook deep-links."
)
def build_careers_scheduling_confirmation_applicant(
    applicant_name: str = "",
    interviewer_name: str = "",
    role_title: str = "",
    slot_utc_iso: str = "",
    applicant_local_str: str = "",
    interviewer_local_str: str = "",
    duration_minutes: int = 45,
    google_calendar_url: str = "",
    outlook_calendar_url: str = "",
    video_url: str = "",
    interview_type: str = "video",
) -> EmailTemplate:
    rows = [
        _info_row("When (your time)", applicant_local_str),
        _info_row("When (interviewer's time)", interviewer_local_str),
        _info_row("Duration", f"{duration_minutes} min"),
        _info_row("Format", (interview_type or "video").title()),
        _info_row("With", interviewer_name or "our team"),
    ]
    if video_url:
        rows.append(_info_row("Join link", video_url))
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">You're booked</p>
<p style="margin:0 0 12px;">See you on <strong>{applicant_local_str}</strong> (your time) for the <strong>{role_title or 'interview'}</strong>. We've attached a calendar invite; below are one-tap add buttons as backup.</p>
{_info_table(rows)}
<p style="margin:12px 0 6px;">
<a href="{google_calendar_url}" style="display:inline-block;background:#0EA5E9;color:#FFF;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:700;margin-right:6px;">Add to Google Calendar</a>
<a href="{outlook_calendar_url}" style="display:inline-block;background:#0F766E;color:#FFF;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:700;">Add to Outlook</a>
</p>"""
    return EmailTemplate(
        subject=f"Interview confirmed · {applicant_local_str}",
        html=_wrap(
            "Interview confirmed",
            applicant_local_str,
            body,
            "",
            "",
            "#0EA5E9",
            category="careers",
        ),
        text=_txt(
            "Interview confirmed",
            f"Hi {applicant_name or 'there'}, your interview for {role_title or 'the role'} is booked.\n"
            f"When (your time): {applicant_local_str}\n"
            f"When (interviewer's time): {interviewer_local_str}\n"
            f"Duration: {duration_minutes} min\nWith: {interviewer_name}\n"
            + (f"Join link: {video_url}\n" if video_url else ""),
            "",
            "",
        ),
    )


# ── Careers scheduling confirmation (to interviewer) ──────────────
@_register(
    "careers_scheduling_confirmation_interviewer",
    "Careers Scheduling Confirmation (Interviewer)",
    "Careers",
    "Sent to the interviewer after the applicant self-books. Includes interviewer-TZ ICS."
)
def build_careers_scheduling_confirmation_interviewer(
    applicant_name: str = "",
    interviewer_name: str = "",
    role_title: str = "",
    slot_utc_iso: str = "",
    applicant_local_str: str = "",
    interviewer_local_str: str = "",
    duration_minutes: int = 45,
    google_calendar_url: str = "",
    outlook_calendar_url: str = "",
    video_url: str = "",
    interview_type: str = "video",
) -> EmailTemplate:
    rows = [
        _info_row("Candidate", applicant_name or "Applicant"),
        _info_row("Role", role_title or "—"),
        _info_row("When (your time)", interviewer_local_str),
        _info_row("When (their time)", applicant_local_str),
        _info_row("Duration", f"{duration_minutes} min"),
        _info_row("Format", (interview_type or "video").title()),
    ]
    if video_url:
        rows.append(_info_row("Join link", video_url))
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">New interview booked</p>
<p style="margin:0 0 12px;">{applicant_name or 'A candidate'} just self-booked an interview via the scheduler. Times are shown below in <strong>both</strong> time zones so there's zero ambiguity.</p>
{_info_table(rows)}
<p style="margin:12px 0 6px;">
<a href="{google_calendar_url}" style="display:inline-block;background:#0EA5E9;color:#FFF;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:700;margin-right:6px;">Add to Google Calendar</a>
<a href="{outlook_calendar_url}" style="display:inline-block;background:#0F766E;color:#FFF;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:700;">Add to Outlook</a>
</p>"""
    return EmailTemplate(
        subject=f"Interview booked: {applicant_name or 'candidate'} · {interviewer_local_str}",
        html=_wrap(
            "Interview booked",
            interviewer_local_str,
            body,
            "",
            "",
            "#0F766E",
            category="careers",
        ),
        text=_txt(
            "Interview booked",
            f"{applicant_name or 'A candidate'} self-booked via the scheduler.\n"
            f"When (your time): {interviewer_local_str}\n"
            f"When (their time): {applicant_local_str}\n"
            f"Duration: {duration_minutes} min\nRole: {role_title}\n"
            + (f"Join link: {video_url}\n" if video_url else ""),
            "",
            "",
        ),
    )


@_register(
    "career_applicant_withdraw_notice",
    "Career Applicant Withdraw Notice",
    "Employer",
    "Internal notice to recruiters when an applicant self-withdraws via the tracker page",
)
def build_career_applicant_withdraw_notice_email(
    applicant_name: str = "Alex Johnson",
    applicant_email: str = "alex@example.com",
    position: str = "Software Engineer",
    application_id: str = "app_abc123",
    reason: str = "(no reason provided)",
) -> EmailTemplate:
    """Fires to the hiring inbox whenever a candidate clicks "Withdraw" on
    their public tracker page. Not user-facing."""
    accent = "#64748B"
    tracker_url = f"{DASH_URL}/careers/track/{application_id}"
    rows = [
        _info_row("Applicant", applicant_name),
        _info_row("Contact", applicant_email),
        _info_row("Position", position),
        _info_row("Application ID", application_id),
        _info_row("Reason", reason or "—"),
    ]
    body = f"""{_alert_panel("Applicant Self-Withdrew", f"<strong>{applicant_name}</strong> withdrew their application for <strong>{position}</strong>.", accent, "WITHDRAW")}
    {_info_table(rows)}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0 0;">
      <tr><td align="center"><a href="{tracker_url}" style="display:inline-block;background:{accent};color:#FFFFFF;text-decoration:none;padding:10px 18px;border-radius:10px;font-weight:700;font-size:13px;">Open tracker view</a></td></tr>
    </table>"""
    return EmailTemplate(
        subject=f"Applicant Withdrew — {applicant_name} ({position}) [{application_id}]",
        html=_wrap(
            "Applicant Withdrew",
            f"{applicant_name} · {position}",
            body,
            "Open tracker",
            tracker_url,
            accent,
            category="employer",
        ),
        text=_txt(
            "Applicant Withdrew",
            (
                f"{applicant_name} ({applicant_email}) withdrew their "
                f"application for {position} (ID: {application_id}).\n\n"
                f"Reason: {reason or '(none provided)'}\n\n"
                f"Tracker: {tracker_url}"
            ),
        ),
    )



# ═══════════════════════════════════════════════════════════
# GTEC C5 — §12 Final Output (Global System Directive)
# ═══════════════════════════════════════════════════════════

def _sev_tone(value) -> tuple:
    """(bg, fg) for a PASS/FAIL/YES/NO pill."""
    s = str(value or "").upper()
    if s in ("PASS", "YES"):
        return ("#DCFCE7", "#047857")
    if s in ("FAIL", "NO"):
        return ("#FEE2E2", "#B91C1C")
    return ("#F1F5F9", "#475569")


def _pillar_row(label: str, value: str) -> str:
    bg, fg = _sev_tone(value)
    return f"""
    <tr>
      <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-size:12px;color:#475569;font-family:SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.04em;">{label}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;text-align:right;">
        <span style="display:inline-block;padding:3px 10px;border-radius:999px;background:{bg};color:{fg};font-size:11px;font-weight:800;letter-spacing:.05em;">{value or '—'}</span>
      </td>
    </tr>"""


def _sev_card(label: str, value, color: str) -> str:
    return f"""
    <td style="width:25%;padding:4px;">
      <div style="border-radius:10px;border:1px solid {color}3A;background:{color}14;padding:10px 8px;text-align:center;">
        <div style="font-size:9px;font-weight:800;color:{color};letter-spacing:.08em;">{label}</div>
        <div style="font-size:22px;font-weight:900;color:{color};margin-top:4px;">{value}</div>
      </div>
    </td>"""


@_register(
    "gtec_scan_v2_report",
    "GTEC C5 — §12 Directive Report",
    "Security",
    "Sent to admin after every GTEC C5 run (manual or scheduled).",
)
def build_gtec_scan_v2_report_email(
    task_id: str = "task_gtec_c5_sample",
    internal_task_id: str = "",
    execution_hash: str = "abc123def456",
    status: str = "PASS",
    critical_vulns: int = 0,
    high_vulns: int = 0,
    medium_vulns: int = 0,
    low_vulns: int = 0,
    regressions: str = "NO",
    security_scan: str = "PASS",
    e2e_tests: str = "PASS",
    responsiveness: str = "PASS",
    performance: str = "PASS",
    rbac_status: str = "PASS",
    subscription_enforcement: str = "PASS",
    learning_memory_updated: str = "YES",
    summary: str = "All validation pillars passed.",
    triggered_by: str = "manual",
    actor: str = "system",
    generated_at: str = "",
    elapsed_ms: int = 0,
    directive_version: str = "",
    recurring_findings: int = 0,
    severity_counts: dict = None,
    report_url: str = "",
    v3_output: dict = None,
    pdf_attachment_name: str = "",
    pdf_sha256: str = "",
    pdf_policy_mode: str = "",
    pdf_source_header: str = "",
    pdf_normalized_header: str = "",
    pdf_guardrail_passed: bool = False,
    pdf_guardrail_failures: str = "",
    c5_trust_score_percent: float = 0.0,
    c5_trust_passed_gates: int = 0,
    c5_trust_total_gates: int = 0,
    c5_white_screen_status: str = "UNKNOWN",
    c5_white_screen_run_id: str = "",
    c5_white_screen_failed_checks: int = 0,
    c5_white_screen_total_checks: int = 0,
    c5_white_screen_routes_tested: int = 0,
    c5_white_screen_route_source: str = "",
    c5_viewport_artifact_count: int = 0,
    c5_viewports: str = "",
    c5_external_cert_status: str = "not_run",
    c5_external_cert_id: str = "",
    c5_external_cert_reason: str = "",
    c5_external_cert_retry_needed: str = "NO",
    c5_external_cert_retry_reasons: str = "",
    c5_incidents_evaluated: int = 0,
    c5_incidents_transitioned_pending: int = 0,
    c5_incidents_auto_closed: int = 0,
    c5_incidents_reopened: int = 0,
    c5_incidents_streak_resets: int = 0,
    c5_incident_policy_clean_rescans: int = 3,
    c5_incident_policy_pending_hours: int = 24,
    c5_snapshot_version: str = "c5-notification-snapshot.v2",
    c5_snapshot_status: str = "INCOMPLETE",
    c5_data_freshness: str = "STALE_OR_PARTIAL",
    c5_consistency_passed: str = "NO",
    c5_consistency_issues: str = "",
    c5_fail_reason_summary: str = "",
    c5_scan_mode: str = "STRICT_GLOBAL",
    c5_strict_global_mode: str = "YES",
    c5_transient_artifact_count: int = 0,
    c5_strict_gate_passed: str = "NO",
    c5_preflight_require_external_preview: str = "YES",
    c5_preflight_require_local_backend: str = "YES",
) -> EmailTemplate:
    """v2 §12 + v3 §13 execution report — the mandatory output format.

    Sent to every admin after each C5 scan (manual or scheduled).
    Design:
      1. Hero status pill
      2. Literal v2 §12 monospace block (preserved verbatim — directive-locked)
      3. Literal v3 §13 monospace block (additive; GTEC SCAN v3 UPGRADE)
      4. Visual severity counters + pillar table + summary line
    """
    severity_counts = severity_counts or {}
    v3_output = v3_output or {}
    status_bg, status_fg = _sev_tone(status)
    elapsed_s = round((elapsed_ms or 0) / 1000, 1)
    generated_label = generated_at or "just now"
    cta_url = report_url or f"{DASH_URL}/executive-dashboard?section=security"

    # v3 §13 fields (with safe fallbacks if upstream skipped the block)
    v3_system_status   = (v3_output.get("SYSTEM_STATUS") or status or "—").upper()
    v3_security_status = (v3_output.get("SECURITY_STATUS") or security_scan or "—").upper()
    v3_perf_status     = (v3_output.get("PERFORMANCE_STATUS") or performance or "—").upper()
    v3_i18n_status     = (v3_output.get("I18N_STATUS") or "—").upper()
    v3_rbac_status     = (v3_output.get("RBAC_STATUS") or rbac_status or "—").upper()
    v3_regression      = (v3_output.get("REGRESSION_STATUS")
                          or ("FAIL" if str(regressions).upper() == "YES" else "PASS")).upper()
    v3_error_count     = str(v3_output.get("ERROR_COUNT")
                              if v3_output.get("ERROR_COUNT") is not None
                              else int(critical_vulns or 0) + int(high_vulns or 0)
                                   + int(medium_vulns or 0) + int(low_vulns or 0))
    v3_active_fixes    = (v3_output.get("ACTIVE_FIXES") or "NO").upper()
    v3_monitoring      = (v3_output.get("MONITORING") or "ACTIVE").upper()
    v3_learning_memory = (v3_output.get("LEARNING_MEMORY")
                           or ("UPDATED" if str(learning_memory_updated).upper() == "YES"
                               else "NOT UPDATED")).upper()
    v3_confidence      = (v3_output.get("CONFIDENCE_LEVEL") or "—").upper()

    # ── v7 SECURITY PALETTE — light theme tokens (Gmail/Outlook safe) ──
    # Per `_CATEGORY_PALETTE["security"]`:
    #   ct=#FEF2F2 (rose-50 card tint)  cb=#FECACA (rose-200 border)
    #   pb=#991B1B (red-900 strong)     sb=#FEE2E2 (rose-100 secondary)
    # Body text uses slate-900 (#0F172A) on light — never dark-bg + light-text
    # which gets flipped unpredictably by Gmail "force light theme" heuristics.
    V7_CARD_BG     = "#FEF2F2"
    V7_CARD_BORDER = "#FECACA"
    V7_TEXT_BODY   = "#0F172A"
    V7_TEXT_LABEL  = "#64748B"
    V7_TEXT_STRONG = "#991B1B"
    V7_PASS_FG     = "#047857"   # emerald-700 — accessible on V7_CARD_BG
    V7_FAIL_FG     = "#B91C1C"   # red-700 — accessible on V7_CARD_BG
    V7_WARN_FG     = "#B45309"   # amber-700

    # Literal §12 block (monospace, v7 LIGHT) — preserves the directive
    # field set verbatim; only the wrapper styling is now v7-compliant.
    literal_block = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:{V7_CARD_BG};border:1px solid {V7_CARD_BORDER};border-radius:12px;padding:16px 18px;font-family:SFMono-Regular,Menlo,Consolas,monospace;color:{V7_TEXT_BODY};font-size:12px;line-height:1.7;">
          <div style="color:{V7_TEXT_STRONG};font-size:10px;letter-spacing:.1em;font-weight:800;margin-bottom:8px;">§12 FINAL OUTPUT — GLOBAL SYSTEM DIRECTIVE</div>
          <div><span style="color:{V7_TEXT_LABEL};">TASK_ID:</span> {task_id}</div>
          <div><span style="color:{V7_TEXT_LABEL};">EXECUTION_HASH:</span> {execution_hash}</div>
          <div><span style="color:{V7_TEXT_LABEL};">STATUS:</span> <strong style="color:{V7_PASS_FG if str(status).upper()=='PASS' else V7_FAIL_FG};">{status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">CRITICAL_VULNS:</span> {critical_vulns}</div>
          <div><span style="color:{V7_TEXT_LABEL};">HIGH_VULNS:</span> {high_vulns}</div>
          <div><span style="color:{V7_TEXT_LABEL};">MEDIUM_VULNS:</span> {medium_vulns}</div>
          <div><span style="color:{V7_TEXT_LABEL};">LOW_VULNS:</span> {low_vulns}</div>
          <div><span style="color:{V7_TEXT_LABEL};">REGRESSIONS:</span> {regressions}</div>
          <div><span style="color:{V7_TEXT_LABEL};">SECURITY_SCAN:</span> {security_scan}</div>
          <div><span style="color:{V7_TEXT_LABEL};">E2E_TESTS:</span> {e2e_tests}</div>
          <div><span style="color:{V7_TEXT_LABEL};">RESPONSIVENESS:</span> {responsiveness}</div>
          <div><span style="color:{V7_TEXT_LABEL};">PERFORMANCE:</span> {performance}</div>
          <div><span style="color:{V7_TEXT_LABEL};">RBAC_STATUS:</span> {rbac_status}</div>
          <div><span style="color:{V7_TEXT_LABEL};">SUBSCRIPTION_ENFORCEMENT:</span> {subscription_enforcement}</div>
          <div><span style="color:{V7_TEXT_LABEL};">LEARNING_MEMORY_UPDATED:</span> {learning_memory_updated}</div>
          <div><span style="color:{V7_TEXT_LABEL};">DIRECTIVE_VERSION:</span> {directive_version or '—'}</div>
          <div style="margin-top:8px;"><span style="color:{V7_TEXT_LABEL};">SUMMARY:</span></div>
          <div style="color:{V7_TEXT_BODY};white-space:pre-wrap;word-break:break-word;">{summary}</div>
        </td>
      </tr>
    </table>"""

    # ── v3 §13 LITERAL BLOCK (additive · GTEC SCAN v3 UPGRADE · v7 LIGHT) ──
    # Same v7 security palette as §12. Color accents are PASS/FAIL/WARN
    # accessible on light card; never light-on-dark.
    def _v3_color(val: str) -> str:
        v = (val or "").upper()
        if v in ("PASS", "YES", "ACTIVE", "UPDATED", "HIGH"):
            return V7_PASS_FG
        if v in ("FAIL", "INACTIVE", "NOT UPDATED", "LOW"):
            return V7_FAIL_FG
        if v in ("MEDIUM",):
            return V7_WARN_FG
        return V7_TEXT_BODY

    v3_literal_block = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:{V7_CARD_BG};border:1px solid {V7_CARD_BORDER};border-radius:12px;padding:16px 18px;font-family:SFMono-Regular,Menlo,Consolas,monospace;color:{V7_TEXT_BODY};font-size:12px;line-height:1.7;">
          <div style="color:{V7_TEXT_STRONG};font-size:10px;letter-spacing:.1em;font-weight:800;margin-bottom:8px;">§13 v3 FINAL OUTPUT — GTEC SCAN v3 UPGRADE (ADDITIVE)</div>
          <div><span style="color:{V7_TEXT_LABEL};">SYSTEM_STATUS:</span> <strong style="color:{_v3_color(v3_system_status)};">{v3_system_status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">SECURITY_STATUS:</span> <strong style="color:{_v3_color(v3_security_status)};">{v3_security_status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">PERFORMANCE_STATUS:</span> <strong style="color:{_v3_color(v3_perf_status)};">{v3_perf_status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">I18N_STATUS:</span> <strong style="color:{_v3_color(v3_i18n_status)};">{v3_i18n_status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">RBAC_STATUS:</span> <strong style="color:{_v3_color(v3_rbac_status)};">{v3_rbac_status}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">REGRESSION_STATUS:</span> <strong style="color:{_v3_color(v3_regression)};">{v3_regression}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">ERROR_COUNT:</span> {v3_error_count}</div>
          <div><span style="color:{V7_TEXT_LABEL};">ACTIVE_FIXES:</span> <strong style="color:{_v3_color(v3_active_fixes)};">{v3_active_fixes}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">MONITORING:</span> <strong style="color:{_v3_color(v3_monitoring)};">{v3_monitoring}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">LEARNING_MEMORY:</span> <strong style="color:{_v3_color(v3_learning_memory)};">{v3_learning_memory}</strong></div>
          <div><span style="color:{V7_TEXT_LABEL};">CONFIDENCE_LEVEL:</span> <strong style="color:{_v3_color(v3_confidence)};">{v3_confidence}</strong></div>
        </td>
      </tr>
    </table>"""

    # Hero status pill
    hero = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:{status_bg};border:1px solid {status_fg}33;border-radius:14px;padding:18px;">
          <p style="margin:0;font-size:10px;font-weight:800;color:{status_fg};letter-spacing:.1em;">GTEC C5 · DIRECTIVE VERSION {directive_version or '—'}</p>
          <p style="margin:6px 0 0;font-size:22px;font-weight:900;color:{status_fg};">Scan {status} · triggered by {triggered_by}</p>
          <p style="margin:4px 0 0;font-size:12px;color:#475569;">{generated_label} · completed in {elapsed_s}s · actor {actor}</p>
          <p style="margin:6px 0 0;font-size:12px;color:#7F1D1D;font-weight:700;">{c5_fail_reason_summary or 'Fail reason summary unavailable.'}</p>
        </td>
      </tr>
    </table>"""

    # Severity counter row
    crit_color = "#EF4444" if (critical_vulns or 0) else "#10B981"
    high_color = "#F59E0B" if (high_vulns or 0) else "#10B981"
    med = severity_counts.get("medium", 0)
    low = severity_counts.get("low", 0)
    severity_row = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        {_sev_card("CRITICAL", critical_vulns, crit_color)}
        {_sev_card("HIGH", high_vulns, high_color)}
        {_sev_card("MEDIUM", med, "#64748B")}
        {_sev_card("LOW", low, "#94A3B8")}
      </tr>
    </table>"""

    # Pillar pass/fail table
    pillar_table = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 16px;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
      {_pillar_row("SECURITY_SCAN", security_scan)}
      {_pillar_row("E2E_TESTS", e2e_tests)}
      {_pillar_row("RESPONSIVENESS", responsiveness)}
      {_pillar_row("PERFORMANCE", performance)}
      {_pillar_row("RBAC_STATUS", rbac_status)}
      {_pillar_row("SUBSCRIPTION_ENFORCEMENT", subscription_enforcement)}
      {_pillar_row("REGRESSIONS", regressions)}
      {_pillar_row("LEARNING_MEMORY_UPDATED", learning_memory_updated)}
    </table>"""

    recurring_callout = ""
    if recurring_findings and recurring_findings > 0:
        recurring_callout = _callout(
            f"⚠️ {recurring_findings} recurring finding(s) detected in learning memory — "
            "escalate to systemic fix (directive §5).",
            "#F59E0B",
        )

    attachment_callout = ""
    if pdf_attachment_name:
        meta_rows = []
        if pdf_sha256:
            meta_rows.append(f"SHA-256: <code>{pdf_sha256}</code>")
        if pdf_normalized_header:
            meta_rows.append(f"Normalized header: <code>{pdf_normalized_header}</code>")
        if pdf_source_header and pdf_source_header != pdf_normalized_header:
            meta_rows.append(f"Source header: <code>{pdf_source_header}</code>")
        if pdf_policy_mode:
            meta_rows.append(f"Policy mode: <code>{pdf_policy_mode}</code>")
        meta_rows.append(f"Guardrail passed: <code>{'YES' if pdf_guardrail_passed else 'NO'}</code>")
        if pdf_guardrail_failures:
            meta_rows.append(f"Guardrail failures: <code>{pdf_guardrail_failures}</code>")
        meta_block = "<br/>".join(meta_rows)
        attachment_callout = _callout(
            f"📎 Attached PDF report: <strong>{pdf_attachment_name}</strong><br/>"
            "Includes the literal §12 and §13 final output blocks for audit archival."
            + (f"<br/>{meta_block}" if meta_block else ""),
            "#0F766E",
        )

    c5_quality_tone = "#047857" if str(c5_snapshot_status).upper() == "COMPLETE" else "#B91C1C"
    c5_quality_copy = (
        "CERTIFICATION DATA INCOMPLETE — DO NOT USE FOR GO/NO-GO."
        if str(c5_snapshot_status).upper() != "COMPLETE"
        else "Certification data complete and consistent for this run."
    )

    c5_runtime_block = f"""
    <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 0 18px;border:1px solid #DBEAFE;border-radius:12px;overflow:hidden;\">
      <tr><td style=\"padding:10px 12px;background:#EFF6FF;color:#1E3A8A;font-size:11px;font-weight:800;letter-spacing:.07em;\">C5 RUNTIME SUMMARY — ENFORCEMENT + CERTIFICATION</td></tr>
      <tr><td style=\"padding:12px;background:#FFFFFF;\">
        <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">
          {_pillar_row("SNAPSHOT_STATUS", f"{c5_snapshot_status} · freshness={c5_data_freshness}")}
          {_pillar_row("CONSISTENCY", f"{c5_consistency_passed} {('· ' + c5_consistency_issues) if c5_consistency_issues else ''}")}
          {_pillar_row("RUN_POLICY", f"mode={c5_scan_mode} · strict={c5_strict_global_mode} · strict_gate={c5_strict_gate_passed}")}
          {_pillar_row("PREFLIGHT_POLICY", f"external_preview={c5_preflight_require_external_preview} · local_backend={c5_preflight_require_local_backend}")}
          {_pillar_row("TRANSIENT_ARTIFACT_COUNT", str(c5_transient_artifact_count))}
          {_pillar_row("FAIL_REASON_SUMMARY", c5_fail_reason_summary or '—')}
          {_pillar_row("TRUST_GATES", f"{c5_trust_passed_gates}/{c5_trust_total_gates} ({float(c5_trust_score_percent or 0.0):.2f}%)")}
          {_pillar_row("WHITE_SCREEN_SENTRY", f"{c5_white_screen_status} · {c5_white_screen_failed_checks}/{c5_white_screen_total_checks} failed")}
          {_pillar_row("VIEWPORT_MATRIX", f"artifacts={c5_viewport_artifact_count} · viewports={c5_viewports or 'mobile,tablet,desktop'}")}
          {_pillar_row("EXTERNAL_HOST_CERT", f"{c5_external_cert_status} · retry={c5_external_cert_retry_needed}")}
          {_pillar_row("INCIDENT_AUTO_CLOSE", f"evaluated={c5_incidents_evaluated} pending={c5_incidents_transitioned_pending} closed={c5_incidents_auto_closed} reopened={c5_incidents_reopened}")}
        </table>
        <p style=\"margin:10px 0 0;color:#475569;font-size:11px;line-height:1.6;\">
          White-screen run: <code>{c5_white_screen_run_id or '—'}</code>
          {f" · source={c5_white_screen_route_source}" if c5_white_screen_route_source else ""}
          {f" · routes={c5_white_screen_routes_tested}" if c5_white_screen_routes_tested else ""}<br/>
          External certification: <code>{c5_external_cert_id or '—'}</code>
          {f" · reason={c5_external_cert_reason}" if c5_external_cert_reason else ""}
          {f" · retry_reasons={c5_external_cert_retry_reasons}" if c5_external_cert_retry_reasons else ""}<br/>
          Incident policy: {c5_incident_policy_clean_rescans} clean rescans + {c5_incident_policy_pending_hours}h pending hold
          {f" · streak_resets={c5_incidents_streak_resets}" if c5_incidents_streak_resets else ""}
        </p>
        <p style=\"margin:8px 0 0;color:{c5_quality_tone};font-size:11px;font-weight:800;\">{c5_quality_copy}</p>
      </td></tr>
    </table>"""

    body = hero + c5_runtime_block + attachment_callout + literal_block + v3_literal_block + severity_row + pillar_table + recurring_callout

    subject_tag = "PASS" if str(status).upper() == "PASS" else "FAIL"
    subject = (
        f"[GTEC C5 · {subject_tag}] {task_id} — "
        f"crit={critical_vulns} high={high_vulns} med={medium_vulns} low={low_vulns}"
    )

    return EmailTemplate(
        subject=subject,
        html=_wrap(
            subject,
            (
                f"GTEC C5 runtime summary — {status} · crit={critical_vulns} high={high_vulns} med={medium_vulns} low={low_vulns} "
                f"· sentry={c5_white_screen_status} · ext-cert={c5_external_cert_status}"
            ),
            body,
            "Open Security Dashboard →",
            cta_url,
            # v7 security palette (pb = red-900). PASS = emerald-700;
            # FAIL = red-700. Never #0F172A (dark navy bypasses v7).
            V7_PASS_FG if str(status).upper() == "PASS" else V7_FAIL_FG,
            category="security",
        ),
        text=_txt(
            f"GTEC C5 — {status}",
            (
                f"TASK_ID: {task_id}\n"
                f"EXECUTION_HASH: {execution_hash}\n"
                f"STATUS: {status}\n"
                f"CRITICAL_VULNS: {critical_vulns}\n"
                f"HIGH_VULNS: {high_vulns}\n"
                f"MEDIUM_VULNS: {medium_vulns}\n"
                f"LOW_VULNS: {low_vulns}\n"
                f"REGRESSIONS: {regressions}\n"
                f"SECURITY_SCAN: {security_scan}\n"
                f"E2E_TESTS: {e2e_tests}\n"
                f"RESPONSIVENESS: {responsiveness}\n"
                f"PERFORMANCE: {performance}\n"
                f"RBAC_STATUS: {rbac_status}\n"
                f"SUBSCRIPTION_ENFORCEMENT: {subscription_enforcement}\n"
                f"LEARNING_MEMORY_UPDATED: {learning_memory_updated}\n"
                f"DIRECTIVE_VERSION: {directive_version}\n\n"
                f"--- §13 v3 FINAL OUTPUT (GTEC SCAN v3 UPGRADE — ADDITIVE) ---\n"
                f"SYSTEM_STATUS: {v3_system_status}\n"
                f"SECURITY_STATUS: {v3_security_status}\n"
                f"PERFORMANCE_STATUS: {v3_perf_status}\n"
                f"I18N_STATUS: {v3_i18n_status}\n"
                f"RBAC_STATUS: {v3_rbac_status}\n"
                f"REGRESSION_STATUS: {v3_regression}\n"
                f"ERROR_COUNT: {v3_error_count}\n"
                f"ACTIVE_FIXES: {v3_active_fixes}\n"
                f"MONITORING: {v3_monitoring}\n"
                f"LEARNING_MEMORY: {v3_learning_memory}\n"
                f"CONFIDENCE_LEVEL: {v3_confidence}\n\n"
                f"ATTACHED_PDF_REPORT: {pdf_attachment_name or 'NONE'}\n\n"
                f"ATTACHED_PDF_SHA256: {pdf_sha256 or 'NONE'}\n"
                f"ATTACHED_PDF_POLICY_MODE: {pdf_policy_mode or 'NONE'}\n"
                f"ATTACHED_PDF_SOURCE_HEADER: {pdf_source_header or 'NONE'}\n"
                f"ATTACHED_PDF_NORMALIZED_HEADER: {pdf_normalized_header or 'NONE'}\n\n"
                f"ATTACHED_PDF_GUARDRAIL_PASSED: {'YES' if pdf_guardrail_passed else 'NO'}\n"
                f"ATTACHED_PDF_GUARDRAIL_FAILURES: {pdf_guardrail_failures or 'NONE'}\n\n"
                f"--- C5 RUNTIME SUMMARY ---\n"
                f"SNAPSHOT_VERSION: {c5_snapshot_version}\n"
                f"SNAPSHOT_STATUS: {c5_snapshot_status}\n"
                f"DATA_FRESHNESS: {c5_data_freshness}\n"
                f"CONSISTENCY_PASSED: {c5_consistency_passed}\n"
                f"CONSISTENCY_ISSUES: {c5_consistency_issues or 'NONE'}\n"
                f"SCAN_MODE: {c5_scan_mode}\n"
                f"STRICT_GLOBAL_MODE: {c5_strict_global_mode}\n"
                f"STRICT_GATE_PASSED: {c5_strict_gate_passed}\n"
                f"PREFLIGHT_REQUIRE_EXTERNAL_PREVIEW: {c5_preflight_require_external_preview}\n"
                f"PREFLIGHT_REQUIRE_LOCAL_BACKEND: {c5_preflight_require_local_backend}\n"
                f"TRANSIENT_ARTIFACT_COUNT: {c5_transient_artifact_count}\n"
                f"FAIL_REASON_SUMMARY: {c5_fail_reason_summary or 'NONE'}\n"
                f"TRUST_SCORE_PERCENT: {float(c5_trust_score_percent or 0.0):.2f}\n"
                f"TRUST_GATES: {c5_trust_passed_gates}/{c5_trust_total_gates}\n"
                f"WHITE_SCREEN_SENTRY_STATUS: {c5_white_screen_status}\n"
                f"WHITE_SCREEN_SENTRY_RUN_ID: {c5_white_screen_run_id or 'NONE'}\n"
                f"WHITE_SCREEN_SENTRY_FAILED_CHECKS: {c5_white_screen_failed_checks}/{c5_white_screen_total_checks}\n"
                f"WHITE_SCREEN_SENTRY_ROUTES_TESTED: {c5_white_screen_routes_tested}\n"
                f"WHITE_SCREEN_SENTRY_ROUTE_SOURCE: {c5_white_screen_route_source or 'NONE'}\n"
                f"VIEWPORT_MATRIX_ARTIFACT_COUNT: {c5_viewport_artifact_count}\n"
                f"VIEWPORTS: {c5_viewports or 'mobile,tablet,desktop'}\n"
                f"EXTERNAL_HOST_CERT_STATUS: {c5_external_cert_status}\n"
                f"EXTERNAL_HOST_CERT_ID: {c5_external_cert_id or 'NONE'}\n"
                f"EXTERNAL_HOST_CERT_REASON: {c5_external_cert_reason or 'NONE'}\n"
                f"EXTERNAL_HOST_CERT_RETRY_NEEDED: {c5_external_cert_retry_needed}\n"
                f"EXTERNAL_HOST_CERT_RETRY_REASONS: {c5_external_cert_retry_reasons or 'NONE'}\n"
                f"INCIDENTS_EVALUATED: {c5_incidents_evaluated}\n"
                f"INCIDENTS_PENDING_VERIFICATION: {c5_incidents_transitioned_pending}\n"
                f"INCIDENTS_AUTO_CLOSED: {c5_incidents_auto_closed}\n"
                f"INCIDENTS_REOPENED: {c5_incidents_reopened}\n"
                f"INCIDENTS_STREAK_RESETS: {c5_incidents_streak_resets}\n"
                f"INCIDENT_POLICY: {c5_incident_policy_clean_rescans} clean rescans + {c5_incident_policy_pending_hours}h hold\n\n"
                f"SUMMARY:\n{summary}\n\n"
                f"Triggered by {triggered_by} · actor {actor} · "
                f"duration {elapsed_s}s\n\n"
                f"Report: {cta_url}"
            ),
            "Open Security Dashboard",
            cta_url,
        ),
    )



@_register(
    "gtec_upstream_watchdog_cleared",
    "GTEC Upstream Watchdog — Blocker Cleared",
    "Security",
    "Sent to admin when a declared upstream dependency blocker clears. "
    "Fires ONCE per cleared transition; idempotent on re-runs.",
)
def build_gtec_upstream_watchdog_cleared_email(
    package: str = "example-pkg",
    latest_version: str = "1.0.0",
    registry: str = "npm",
    entry_id: str = "example_entry",
    blocker_reason: str = "",
    predicate_reason: str = "",
    unblocks_packages: list = None,
    ticket_path: str = "",
    ticket_excerpt: str = "",
    dashboard_url: str = "",
) -> EmailTemplate:
    """§5 systemic-fix email — renders through the V7 guardrail.

    Composition: hero + info table + unblocks badges + ticket-excerpt card.
    No raw-text run-on paragraph — every field gets its own semantic row.
    """
    unblocks_packages = unblocks_packages or []
    cta_url = dashboard_url or f"{DASH_URL}/executive-dashboard?section=security"
    reg_label = "npm" if registry == "npm" else "PyPI" if registry == "pypi" else registry

    # Hero — green "cleared" banner.
    hero = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">
      <tr>
        <td style="background:#ECFDF5;border:1px solid #10B98133;border-radius:14px;padding:18px;">
          <p style="margin:0;font-size:10px;font-weight:800;color:#047857;letter-spacing:.1em;">GTEC UPSTREAM WATCHDOG · {reg_label.upper()}</p>
          <p style="margin:6px 0 0;font-size:20px;font-weight:900;color:#047857;">Blocker cleared: {package} @ {latest_version}</p>
          <p style="margin:4px 0 0;font-size:12px;color:#065F46;">Watchlist entry <code style="background:#D1FAE5;padding:1px 6px;border-radius:4px;">{entry_id}</code> · §5 systemic-fix loop</p>
        </td>
      </tr>
    </table>"""

    # Info table — one row per field (no run-on text).
    info_rows = _info_table([
        _info_row("Package", f"{package} ({reg_label})"),
        _info_row("Latest version", latest_version, "#10B981"),
        _info_row("Entry id", entry_id),
        _info_row("Ticket file", ticket_path or "—"),
    ])

    # Unblocks list (badge row).
    unblocks_html = ""
    if unblocks_packages:
        badges = "".join(
            f'<span style="display:inline-block;background:#EEF2FF;color:#3730A3;'
            f'border:1px solid #C7D2FE;border-radius:999px;padding:4px 10px;'
            f'font-size:12px;font-weight:600;margin:0 6px 6px 0;">{p}</span>'
            for p in unblocks_packages
        )
        unblocks_html = f"""
        <p style="margin:14px 0 6px;font-weight:600;color:#0F172A;">This unblocks:</p>
        <div style="margin:0 0 14px;">{badges}</div>"""

    # Reason/predicate callouts.
    reason_block = ""
    if blocker_reason:
        reason_block += '<p style="margin:12px 0 4px;font-weight:600;color:#0F172A;">Original blocker reason</p>'
        reason_block += f'<p style="margin:0 0 12px;color:#475569;font-size:13px;">{blocker_reason}</p>'
    if predicate_reason:
        reason_block += _callout(
            f"<strong>Unblock condition met:</strong> {predicate_reason}",
            "#10B981",
        )

    # Ticket excerpt — preformatted block so the engineer sees the real ticket body.
    excerpt_html = ""
    if ticket_excerpt:
        # Trim + escape the tiniest subset. The ticket body is markdown; we
        # render it as monospace preformatted so indentation/bullets survive.
        safe = (
            (ticket_excerpt or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )[:2200]
        excerpt_html = f"""
        <p style="margin:16px 0 6px;font-weight:600;color:#0F172A;">Ticket body (excerpt)</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 6px;">
          <tr>
            <td style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;font-family:SFMono-Regular,Menlo,Consolas,monospace;color:#0F172A;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;">{safe}</td>
          </tr>
        </table>"""

    body = f"""
    {hero}
    <p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">A declared upstream blocker has cleared</p>
    <p style="margin:0 0 14px;">The GTEC Upstream Watchdog detected that an upstream package now satisfies the predicate that was blocking an internal upgrade. A P-priority ticket has been auto-generated and saved under <code style="background:#F1F5F9;padding:1px 6px;border-radius:4px;">memory/tickets/</code>.</p>
    {info_rows}
    {unblocks_html}
    {reason_block}
    {excerpt_html}
    <p style="margin:18px 0 0;font-size:12px;color:#64748B;">This email is sent <strong>once</strong> per cleared transition — you will not receive follow-ups on the same blocker.</p>"""

    subject = f"[GTEC Upstream Watchdog] Blocker cleared: {package} @ {latest_version}"
    return EmailTemplate(
        subject=subject,
        html=_wrap(
            "Upstream Blocker Cleared",
            f"{package} @ {latest_version} is now available — ticket opened",
            body,
            "Open Security Dashboard",
            cta_url,
            "#10B981",
        ),
        text=_txt(
            "GTEC Upstream Watchdog — Blocker Cleared",
            (
                f"Package: {package} ({reg_label})\n"
                f"Latest version: {latest_version}\n"
                f"Entry id: {entry_id}\n"
                f"Ticket: {ticket_path}\n\n"
                f"Original blocker reason:\n{blocker_reason}\n\n"
                f"Unblock condition met:\n{predicate_reason}\n\n"
                f"This unblocks: {', '.join(unblocks_packages) or '(see ticket)'}\n\n"
                f"Ticket excerpt:\n{ticket_excerpt[:1200]}\n\n"
                "This email is sent ONCE per cleared transition."
            ),
            "Open Security Dashboard",
            cta_url,
        ),
    )


@_register(
    "coaching_team_weekly_digest",
    "Coaching Team Weekly Digest",
    "Engagement",
    "Weekly AI Coaching Team activity recap with coach spotlight and re-engagement CTA",
)
def build_coaching_team_weekly_digest_email(
    user_name: str = "Alex",
    sessions_this_week: int = 2,
    messages_this_week: int = 7,
    coaches_used: list = None,
    spotlight_coach_name: str = "Interview Coach",
    spotlight_coach_tagline: str = "Mock interviews & STAR feedback",
    spotlight_preview_available: bool = True,
    coaching_tip: str = "Book 15 minutes this week to practice one STAR story out loud — spoken rehearsal doubles recall in real interviews.",
) -> EmailTemplate:
    coaches_used = coaches_used if coaches_used is not None else ["Career Coach"]
    coaches_line = ", ".join(coaches_used) if coaches_used else "None yet — your coaches are ready when you are"
    stats_rows = "".join(
        f'<tr><td class="em-info-td" style="padding:10px 14px;color:#64748B;font-size:13px;border-bottom:1px solid #E2E8F0;"><strong style="color:#0F172A;">{value}</strong>&nbsp; {label}</td></tr>'
        for label, value in [
            ("coaching sessions this week", sessions_this_week),
            ("messages exchanged", messages_this_week),
            ("coaches on your team", coaches_line),
        ]
    )
    spotlight_cta_hint = (
        "Your first message with this coach is <strong>free</strong> — try a preview."
        if spotlight_preview_available
        else "Continue the conversation any time."
    )
    body = f"""<p class="em-title" style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Your coaching week, {user_name}</p>
    <p style="margin:0 0 16px;">Here's what you and your {BRAND_NT} AI Coaching Team accomplished:</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E2E8F0;border-radius:10px;border-collapse:separate;overflow:hidden;margin:0 0 18px;">{stats_rows}</table>
    <p class="em-title" style="color:#0F172A;font-size:15px;font-weight:600;margin:0 0 6px;">Coach spotlight: {spotlight_coach_name}</p>
    <p style="margin:0 0 10px;">{spotlight_coach_tagline}. {spotlight_cta_hint}</p>
    {_callout(f"<strong>This week's tip:</strong> {coaching_tip}", "#0F766E")}"""
    return EmailTemplate(
        subject=f"Your AI Coaching Team weekly recap — meet your {spotlight_coach_name}",
        html=_wrap(
            "Your Coaching Week",
            "Weekly recap from your AI Coaching Team",
            body,
            "Continue Coaching",
            _platform_url("/ai-coaching-team", campaign="coaching_digest", content="primary_cta"),
            "#0F766E",
        ),
        text=_txt(
            "Your Coaching Week",
            f"Hi {user_name},\n\nSessions this week: {sessions_this_week}\nMessages: {messages_this_week}\nCoaches used: {coaches_line}\n\nCoach spotlight: {spotlight_coach_name} — {spotlight_coach_tagline}\nTip: {coaching_tip}",
            "Continue Coaching",
            _platform_url("/ai-coaching-team", campaign="coaching_digest", content="text_cta"),
        ),
    )
