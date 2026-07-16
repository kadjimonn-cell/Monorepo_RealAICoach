from pathlib import Path


APP_STORE_PATH = Path('/app/frontend/src/store/appStore.ts')
THEME_CONTEXT_PATH = Path('/app/frontend/src/context/ThemeContext.tsx')
LIVE_QUERY_PATH = Path('/app/frontend/src/hooks/useLiveQuery.ts')


def test_app_store_uses_typed_scenario_and_uuid_user_id_generation() -> None:
    source = APP_STORE_PATH.read_text(encoding='utf-8')

    assert 'export interface AppScenario {' in source
    assert 'currentScenario: AppScenario | null;' in source
    assert "import { v4 as uuidv4 } from 'uuid';" in source
    assert 'const generateUserId = () => `user_${uuidv4().replace(/-/g, \'\')}`;' in source
    assert 'Date.now()' not in source
    assert 'Math.random()' not in source


def test_app_store_set_user_id_persists_with_await_and_error_handling() -> None:
    source = APP_STORE_PATH.read_text(encoding='utf-8')

    assert 'setUserId: async (id: string) => {' in source
    assert "await AsyncStorage.setItem('realtalk_user_id', id);" in source
    assert "console.warn('appStore.setUserId persistence failed:'" in source


def test_theme_context_moves_db_sync_into_load_theme_flow() -> None:
    source = THEME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'const loadTheme = useCallback(async () => {' in source
    assert "const dbPrefRaw = (user as any)?.theme_preference;" in source
    assert "if (user?.user_id && !dbSyncedRef.current && ['system', 'light', 'dark'].includes(dbPref)) {" in source
    assert 'eslint-disable-next-line react-hooks/exhaustive-deps' not in source


def test_live_query_snapshot_storage_is_session_only_with_ttl_eviction() -> None:
    source = LIVE_QUERY_PATH.read_text(encoding='utf-8')

    assert 'window.localStorage.setItem' not in source
    assert 'window.localStorage.getItem' not in source
    assert 'window.sessionStorage.setItem(cacheKey, payload);' in source
    assert 'if (Date.now() - parsed.cachedAt > LIVE_QUERY_CACHE_TTL_MS) {' in source
    assert 'window.sessionStorage.removeItem(cacheKey);' in source
