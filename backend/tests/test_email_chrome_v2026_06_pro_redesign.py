"""
Backend tests for Email Chrome Pro Redesign (GLOBAL_EMAIL_FOOTER_VERSION = gef_v2026_06_pro_chrome_redesign)

Covers:
 - Admin login (cookie-session) + preview endpoint access
 - Preview HTML contains new header chrome markers
 - Preview HTML contains new footer chrome markers (single footer version marker, chips, squircle socials, LinkedIn 'in' glyph)
 - Store badges present (google-play + app-store)
 - v7 theme hooks (light/dark, prefers-color-scheme, [data-ogsc], mobile media query, meta color-scheme)
 - Template catalog returns without render errors
 - Compact footer variant python-level render
"""

import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
LOCAL_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

TEMPLATE_TYPES = ["welcome", "subscription_confirmation", "failed_payment", "ticket_created"]


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return a cookie-jar session; falls back to localhost if external URL blocked."""
    for base in (BASE_URL, LOCAL_URL):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        try:
            r = s.post(f"{base}/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                       timeout=15)
        except Exception as e:
            print(f"login attempt on {base} failed: {e}")
            continue
        if r.status_code == 200 and (s.cookies or "session" in r.text.lower() or r.json().get("user")):
            # verify /api/auth/me works
            me = s.get(f"{base}/api/auth/me", timeout=10)
            if me.status_code == 200:
                s._base = base  # attach base for reuse
                return s
        print(f"login on {base} => {r.status_code} {r.text[:200]}")
    pytest.skip("Admin login failed on both external and localhost URLs")


# ---------- Header chrome markers ----------

HEADER_MARKERS = [
    "email-header-wordmark",
    "email-header-trust",
    "email-header-pill",
    "email-header-title",
]

FOOTER_MARKERS_MUST_APPEAR = [
    "em-footer-chip",
    "Encrypted",
    "24/7 Support",
    "GDPR-ready",
    "Take your coach everywhere",
    "email-secondary-cta",
    "Verified sender",
]

V7_THEME_MARKERS = [
    "data-theme-light",
    "data-theme-dark",
    "prefers-color-scheme:dark",
    "[data-ogsc]",
    "max-width:479px",
    "color-scheme",
]


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_email_preview_returns_200(admin_session, template_type, theme):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme={theme}", timeout=20)
    assert r.status_code == 200, f"preview {template_type} theme={theme} -> {r.status_code} {r.text[:400]}"
    data = r.json()
    assert isinstance(data, dict)
    assert "html" in data, f"missing html: keys={list(data.keys())}"
    html = data["html"]
    assert isinstance(html, str) and len(html) > 500, f"html too small: {len(html)}"
    # subject sanity: not an error
    subj = data.get("subject", "")
    assert not subj.startswith("Error:"), f"render error subject: {subj}"


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_email_preview_header_markers_present(admin_session, template_type):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme=light", timeout=20)
    assert r.status_code == 200
    html = r.json()["html"]
    missing = [m for m in HEADER_MARKERS if m not in html]
    assert not missing, f"[{template_type}] missing header markers: {missing}"


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_email_preview_footer_markers_present(admin_session, template_type):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme=light", timeout=20)
    assert r.status_code == 200
    html = r.json()["html"]

    # Exactly one global footer component marker
    comp_count = html.count("data-global-footer-component")
    assert comp_count == 1, f"[{template_type}] expected exactly 1 data-global-footer-component, got {comp_count}"

    # Exactly one footer version marker with expected value
    ver_count = html.count("gef_v2026_06_pro_chrome_redesign")
    assert ver_count == 1, f"[{template_type}] expected exactly 1 gef_v2026_06_pro_chrome_redesign marker, got {ver_count}"

    missing = [m for m in FOOTER_MARKERS_MUST_APPEAR if m not in html]
    assert not missing, f"[{template_type}] missing footer markers: {missing}"


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_squircle_social_buttons_and_linkedin_glyph(admin_session, template_type):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme=light", timeout=20)
    assert r.status_code == 200
    html = r.json()["html"]

    # Squircle social buttons: border-radius:12px on data-social-logo tables
    social_slugs = ["x", "linkedin", "facebook", "instagram", "youtube"]
    for slug in social_slugs:
        assert f'data-social-logo="{slug}"' in html, f"[{template_type}] missing data-social-logo=\"{slug}\""

    # Border radius 12px present near social area (squircle)
    assert "border-radius:12px" in html or "border-radius: 12px" in html, \
        f"[{template_type}] no 12px border-radius (squircle) in html"

    # LinkedIn glyph is literal 'in' (lowercase, standalone). Look for typical pattern like >in<
    # Guard: must exist within a data-social-logo="linkedin" block
    li_match = re.search(r'data-social-logo="linkedin".*?</table>', html, re.DOTALL)
    assert li_match, f"[{template_type}] no linkedin social block"
    li_block = li_match.group(0)
    assert re.search(r">\s*in\s*<", li_block), f"[{template_type}] LinkedIn 'in' glyph not literal text: {li_block[:400]}"


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_store_badges_present(admin_session, template_type):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme=light", timeout=20)
    assert r.status_code == 200
    html = r.json()["html"]
    assert 'data-footer-badge="google-play"' in html, f"[{template_type}] google-play badge missing"
    assert 'data-footer-badge="app-store"' in html, f"[{template_type}] app-store badge missing"
    # Only ONE 'Take your coach everywhere' heading
    heading_count = html.count("Take your coach everywhere")
    assert heading_count == 1, f"[{template_type}] expected 1 'Take your coach everywhere' heading, got {heading_count}"


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_v7_theme_hooks_present(admin_session, template_type, theme):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/preview/{template_type}?theme={theme}", timeout=20)
    assert r.status_code == 200
    html = r.json()["html"]
    missing = [m for m in V7_THEME_MARKERS if m not in html]
    assert not missing, f"[{template_type}/{theme}] missing v7 theme hooks: {missing}"


# ---------- Catalog contract ----------

def test_template_catalog_no_render_errors(admin_session):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/email-notifications/catalog", timeout=30)
    assert r.status_code == 200, f"catalog -> {r.status_code} {r.text[:400]}"
    data = r.json()
    # Extract entries – shape may be list or {"templates": [...]} or {"items": [...]}
    entries = None
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for key in ("templates", "items", "data", "results", "catalog"):
            if isinstance(data.get(key), list):
                entries = data[key]
                break
    assert entries is not None, f"catalog no list found: keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
    assert len(entries) > 0, "catalog empty"

    err_subjects = [
        e for e in entries
        if isinstance(e, dict) and isinstance(e.get("subject"), str) and e["subject"].startswith("Error:")
    ]
    assert not err_subjects, f"{len(err_subjects)} templates have render error subjects. Sample: {err_subjects[:3]}"


# ---------- Compact footer variant (python-level) ----------

def test_compact_footer_variant_renders():
    """Direct python import to verify compact footer variant contains required markers."""
    import sys
    sys.path.insert(0, "/app/backend")
    try:
        from utils.email_templates import render_global_email_footer
    except Exception as e:
        pytest.fail(f"import render_global_email_footer failed: {e}")

    try:
        html = render_global_email_footer(variant="compact")
    except TypeError:
        # Fallback signature
        html = render_global_email_footer("compact")
    except Exception as e:
        pytest.fail(f"render_global_email_footer(variant='compact') raised: {e}")

    assert isinstance(html, str) and len(html) > 100, f"compact footer too small ({len(html)})"
    for marker in ("compact-footer-shell", "em-footer-chip", "Verified sender"):
        assert marker in html, f"compact footer missing marker '{marker}'"


# ---------- Sanity: basic auth flow untouched ----------

def test_admin_auth_me_ok(admin_session):
    base = admin_session._base
    r = admin_session.get(f"{base}/api/auth/me", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # user obj can be nested
    user = body.get("user", body)
    email = user.get("email") or (user.get("data") or {}).get("email")
    assert email == ADMIN_EMAIL, f"unexpected auth/me: {body}"
