from pathlib import Path


HOME_TABS_INDEX_PATH = Path('/app/frontend/app/(tabs)/index.tsx')
AI_DASHBOARD_PATH = Path('/app/frontend/app/ai-feature-dashboard.tsx')
ADMIN_ACTIVITY_PATH = Path('/app/frontend/app/admin-activity-log.tsx')
INTERVIEW_ROOM_PATH = Path('/app/frontend/app/interview-room.tsx')
USE_LIVE_DATA_PATH = Path('/app/frontend/src/hooks/useLiveData.ts')
USE_LIVE_QUERY_PATH = Path('/app/frontend/src/hooks/useLiveQuery.ts')
SUB_ANALYTICS_PATH = Path('/app/backend/routes/admin_subscription_analytics.py')


def test_issue13_home_tab_uses_flatlist_virtualization_not_root_scrollview() -> None:
    source = HOME_TABS_INDEX_PATH.read_text(encoding='utf-8')

    assert 'FlatList' in source
    assert 'renderHomeSection' in source
    assert '<FlatList' in source
    assert 'ScrollView' not in source


def test_issue13_ai_dashboard_avoids_polling_when_realtime_subscription_exists() -> None:
    source = AI_DASHBOARD_PATH.read_text(encoding='utf-8')

    assert 'useAutoRefresh(' not in source
    assert "subscribeType('ai_alert'" in source
    assert "subscribeType('data_change'" in source


def test_issue13_admin_activity_log_avoids_polling_when_realtime_subscription_exists() -> None:
    source = ADMIN_ACTIVITY_PATH.read_text(encoding='utf-8')

    assert 'useAutoRefresh(' not in source
    assert "subscribeType('admin_alert'" in source
    assert "subscribeType('data_change'" in source


def test_issue13_interview_room_remains_realtime_and_no_interval_polling() -> None:
    source = INTERVIEW_ROOM_PATH.read_text(encoding='utf-8')

    assert 'setInterval(() => {' not in source
    assert "payload.type === 'data_change'" in source
    assert 'useManagedWebSocket' in source


def test_issue13_use_live_data_stays_realtime_context_based_and_no_raw_ws() -> None:
    source = USE_LIVE_DATA_PATH.read_text(encoding='utf-8')

    assert 'useRealtime' in source
    assert 'subscribe(' in source
    assert 'new WebSocket(' not in source


def test_issue13_use_live_query_avoids_localstorage_and_keeps_ttl_eviction() -> None:
    source = USE_LIVE_QUERY_PATH.read_text(encoding='utf-8')

    assert 'LIVE_QUERY_CACHE_TTL_MS' in source
    assert 'window.localStorage.setItem' not in source
    assert 'window.sessionStorage.setItem' in source
    assert 'window.sessionStorage.removeItem(cacheKey)' in source


def test_issue13_subscription_analytics_uses_facet_for_multi_counter_fetches() -> None:
    source = SUB_ANALYTICS_PATH.read_text(encoding='utf-8')

    assert 'async def _count_many_facet(collection, filters: dict[str, dict]) -> dict[str, int]:' in source
    assert 'collection.aggregate([{"$facet": facet_pipeline}])' in source
    assert 'base_counts = await _count_many_facet(' in source
    assert 'transaction_counts = await _count_many_facet(' in source
