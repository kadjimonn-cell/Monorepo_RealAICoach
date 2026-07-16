"""
iter818 — Public FPS match-card social sharing regression.

Validates:
- GET /api/games-station/match-card/{id}/social-preview.png returns 200 image/png (1200x630) without auth
- Invalid id returns 200 placeholder PNG (OG-friendly), matching SVG/certificate pattern
- Existing JSON endpoint still 404s on invalid id and 200s on valid id
- Existing SVG endpoint unchanged
- serve-production.js injects per-match OG tags on /fps-match/{id} and STRIPS the default og:image
- /welcome (regression) still contains the default og:image
"""
import io
import os
import re
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://coach-web-preview.preview.emergentagent.com",
).rstrip("/")

VALID_MATCH_ID = "fps_debb2b560228"
INVALID_MATCH_ID = "fps_nope"
DEFAULT_OG_IMAGE = "https://realaicoach.app/og-image.png"


def _get(path: str) -> requests.Response:
    # Plain session — no cookies/auth
    return requests.get(f"{BASE_URL}{path}", timeout=20)


class TestPNGSocialPreview:
    """1200x630 Pillow-rendered PNG for FPS match cards."""

    def test_valid_id_returns_200_png(self):
        r = _get(f"/api/games-station/match-card/{VALID_MATCH_ID}/social-preview.png")
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 1000  # non-empty PNG

    def test_valid_png_dimensions_1200x630(self):
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("PIL not installed in test env")
        r = _get(f"/api/games-station/match-card/{VALID_MATCH_ID}/social-preview.png")
        assert r.status_code == 200
        im = Image.open(io.BytesIO(r.content))
        assert im.size == (1200, 630), f"Expected 1200x630, got {im.size}"
        assert im.format == "PNG"

    def test_invalid_id_returns_200_placeholder_png(self):
        r = _get(f"/api/games-station/match-card/{INVALID_MATCH_ID}/social-preview.png")
        # Matches SVG/certificate placeholder pattern — OG must always render
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")

    def test_invalid_png_dimensions_still_1200x630(self):
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("PIL not installed in test env")
        r = _get(f"/api/games-station/match-card/{INVALID_MATCH_ID}/social-preview.png")
        im = Image.open(io.BytesIO(r.content))
        assert im.size == (1200, 630)

    def test_no_auth_required(self):
        # Explicitly send no cookies/auth headers
        s = requests.Session()
        r = s.get(
            f"{BASE_URL}/api/games-station/match-card/{VALID_MATCH_ID}/social-preview.png",
            timeout=15,
        )
        assert r.status_code == 200


class TestExistingEndpointsRegression:
    def test_json_valid_still_200(self):
        r = _get(f"/api/games-station/match-card/{VALID_MATCH_ID}")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_json_invalid_still_404(self):
        r = _get(f"/api/games-station/match-card/{INVALID_MATCH_ID}")
        assert r.status_code == 404

    def test_svg_valid_still_200(self):
        r = _get(f"/api/games-station/match-card/{VALID_MATCH_ID}/social-preview.svg")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/svg+xml")


class TestOgMetaInjection:
    """serve-production.js should inject per-match OG tags and strip defaults on /fps-match/{id}."""

    def test_fps_match_has_injected_og_title(self):
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        assert r.status_code == 200
        assert 'og:title" content="FPS Match Card — RealAICoach Arena"' in r.text

    def test_fps_match_has_injected_og_image_pointing_to_png(self):
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        expected = f"{BASE_URL}/api/games-station/match-card/{VALID_MATCH_ID}/social-preview.png"
        assert expected in r.text, "og:image not pointing to PNG endpoint"

    def test_fps_match_has_og_image_dimensions_1200_630(self):
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        assert 'og:image:width" content="1200"' in r.text
        assert 'og:image:height" content="630"' in r.text

    def test_fps_match_has_twitter_summary_large_image(self):
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        assert 'twitter:card" content="summary_large_image"' in r.text

    def test_fps_match_has_og_url(self):
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        expected_url = f"{BASE_URL}/fps-match/{VALID_MATCH_ID}"
        assert expected_url in r.text

    def test_fps_match_strips_default_og_image(self):
        """The static-site default og:image should be REMOVED for /fps-match/{id}."""
        r = _get(f"/fps-match/{VALID_MATCH_ID}")
        assert DEFAULT_OG_IMAGE not in r.text, "Default og:image should be stripped on fps-match pages"


class TestOgRegressionOtherRoutes:
    """Stripping must not affect other routes."""

    def test_welcome_still_has_default_og_image(self):
        r = _get("/welcome")
        assert r.status_code == 200
        assert DEFAULT_OG_IMAGE in r.text, "Default og:image should REMAIN on /welcome"

    def test_welcome_still_has_default_og_title(self):
        r = _get("/welcome")
        # Original site og:title contains 'RealAICoach' and Coaching (not the FPS Match one)
        assert "FPS Match Card — RealAICoach Arena" not in r.text
