from pathlib import Path
import re


METRO_CONFIG_PATH = Path("/app/frontend/metro.config.js")


def test_metro_does_not_monkey_patch_write_head_for_status_rewrites() -> None:
    source = METRO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "res.writeHead =" not in source
    assert re.search(r"res\.writeHead\s*=\s*\(", source) is None


def test_metro_cache_version_uses_content_hash_inputs() -> None:
    source = METRO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "const crypto = require('crypto');" in source
    assert "packageJsonRaw" in source
    assert "metroConfigRaw" in source
    assert "createHash('sha256')" in source
    assert "config.cacheVersion = `${packageJson.version}-${cacheVersionHash}`;" in source


def test_only_explicit_asset_fast_path_uses_write_head_200() -> None:
    source = METRO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "res.writeHead(" not in source
    assert "res.statusCode = 200;" in source
    assert "res.setHeader('Content-Type', mime);" in source
    assert "res.setHeader('Cache-Control', 'public, max-age=86400');" in source
    assert "url.startsWith('/assets/?unstable_path=')" in source
