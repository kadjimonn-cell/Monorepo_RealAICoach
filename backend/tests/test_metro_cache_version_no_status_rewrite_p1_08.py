from pathlib import Path


METRO_CONFIG_PATH = Path('/app/frontend/metro.config.js')


def test_metro_config_sets_cache_version_from_package_version() -> None:
    source = METRO_CONFIG_PATH.read_text(encoding='utf-8')

    assert "const packageJson = require('./package.json');" in source
    assert "const packageJsonRaw = fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8');" in source
    assert "const metroConfigRaw = fs.readFileSync(path.join(__dirname, 'metro.config.js'), 'utf8');" in source
    assert "createHash('sha256')" in source
    assert "config.cacheVersion = `${packageJson.version}-${cacheVersionHash}`;" in source


def test_metro_config_does_not_rewrite_500_to_200() -> None:
    source = METRO_CONFIG_PATH.read_text(encoding='utf-8')

    assert 'statusCode >= 500 && url === \'/\'' not in source
    assert 'res.writeHead = function(statusCode, ...args)' not in source
