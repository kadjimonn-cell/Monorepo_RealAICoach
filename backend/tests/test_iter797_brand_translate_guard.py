"""Iteration 797 - FIX 4 backend: /api/i18n/auto-translate must NOT emit '{BRAND}' tokens for fr locale.

The widened UNRESOLVED_BRAND_TOKEN_PATTERN in /app/backend/services/auto_translate.py (line 32)
should cause any LLM output that contains a raw '{BRAND}' (numbered or unnumbered) to fall back
to the source text.
"""
import os
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')


def test_auto_translate_preserves_nova_and_no_brand_token():
    """FIX 4: fr translation of Nova/feedback subtitle must contain 'Nova' and NOT contain '{BRAND}'."""
    payload = {
        "texts": [
            "Nova",
            "Help us improve Nova by rating this conversation",
        ],
        "lang": "fr",
    }
    r = requests.post(
        f"{BASE_URL}/api/i18n/auto-translate",
        json=payload,
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=60,
    )
    assert r.status_code == 200, f"auto-translate failed: {r.status_code} {r.text[:600]}"
    body = r.json()
    # Response may be {"translations": [...]} or {"results": [...]} — inspect all string values
    flat_texts = []

    def _walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
        elif isinstance(obj, str):
            flat_texts.append(obj)

    _walk(body)
    combined = " || ".join(flat_texts)
    print(f"auto-translate response strings: {flat_texts}")
    assert "{BRAND}" not in combined, f"Response still contains raw '{{BRAND}}' token: {combined!r}"
    # Should preserve the literal word 'Nova' somewhere in the response
    assert "Nova" in combined, f"Response does not preserve brand name 'Nova': {combined!r}"


def test_locale_files_free_of_brand_token():
    """FIX 4 static assurance: no '{BRAND}' left inside any /app/frontend/src/i18n/locales/*.ts."""
    import glob
    hits = []
    for path in glob.glob('/app/frontend/src/i18n/locales/*.ts'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            if '{BRAND}' in content:
                hits.append(path)
        except Exception as e:
            print(f"could not read {path}: {e}")
    assert hits == [], f"Locale files still contain '{{BRAND}}': {hits}"
