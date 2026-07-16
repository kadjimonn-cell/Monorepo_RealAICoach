import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import middleware


def test_non_api_csp_removes_unsafe_script_directives() -> None:
    csp = middleware._build_non_api_csp("test_nonce")

    assert "script-src 'self' 'nonce-test_nonce'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]
    assert "'unsafe-eval'" not in csp.split("script-src", 1)[1].split(";", 1)[0]


def test_non_api_csp_keeps_expected_script_allowlist_hosts() -> None:
    csp = middleware._build_non_api_csp("abc123")

    assert "https://cdn.jsdelivr.net" in csp
    assert "https://cdnjs.cloudflare.com" in csp


def test_csp_nonce_generation_is_non_empty_and_unique_per_call() -> None:
    nonce_one = middleware._generate_csp_nonce()
    nonce_two = middleware._generate_csp_nonce()

    assert nonce_one
    assert nonce_two
    assert nonce_one != nonce_two