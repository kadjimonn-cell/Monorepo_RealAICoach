from pathlib import Path


RATE_LIMITER_PATH = Path('/app/backend/utils/api_rate_limiter.py')


def test_rate_limiter_uses_redis_backed_state() -> None:
    source = RATE_LIMITER_PATH.read_text(encoding='utf-8')

    assert 'import redis.asyncio as aioredis' in source
    assert 'REDIS_URL = os.environ.get("REDIS_URL")' in source
    assert 'redis_client.evalsha' in source
    assert '_SLIDING_WINDOW_LUA' in source
    assert 'self._windows: Dict[str, list] = defaultdict(list)' not in source


def test_auth_token_caches_no_longer_use_in_memory_dicts() -> None:
    source = RATE_LIMITER_PATH.read_text(encoding='utf-8')

    assert '_admin_token_cache' not in source
    assert '_e2e_token_cache' not in source
    assert '_cache_get_bool' in source
    assert '_cache_set_bool' in source
