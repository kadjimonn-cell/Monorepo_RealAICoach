from pathlib import Path


HOME_TABS_INDEX_PATH = Path('/app/frontend/app/(tabs)/index.tsx')
SESSION_HISTORY_PATH = Path('/app/frontend/app/session-history.tsx')
GLS_PATH = Path('/app/frontend/src/components/layout/GlobalLayoutSystem.tsx')
AI_DASHBOARD_PATH = Path('/app/frontend/app/ai-feature-dashboard.tsx')
ADMIN_ACTIVITY_PATH = Path('/app/frontend/app/admin-activity-log.tsx')


def test_home_tabs_index_uses_flatlist_virtualization_for_heavy_sections() -> None:
    source = HOME_TABS_INDEX_PATH.read_text(encoding='utf-8')

    assert 'const HOME_SECTION_VIRTUAL_ITEMS' in source
    assert '<FlatList' in source
    assert 'getItemLayout={getHomeSectionLayout}' in source
    assert 'initialNumToRender={2}' in source
    assert 'maxToRenderPerBatch={2}' in source


def test_session_history_uses_flatlist_for_dynamic_conversation_rows() -> None:
    source = SESSION_HISTORY_PATH.read_text(encoding='utf-8')

    assert '<FlatList' in source
    assert 'getItemLayout={getSessionItemLayout}' in source
    assert 'SESSION_CARD_ESTIMATED_HEIGHT' in source


def test_ai_dashboard_virtualizes_dynamic_tab_lists() -> None:
    source = AI_DASHBOARD_PATH.read_text(encoding='utf-8')

    assert 'ai-dashboard-features-virtual-list' in source
    assert 'ai-dashboard-power-users-virtual-list' in source
    assert 'ai-dashboard-alerts-virtual-list' in source
    assert source.count('getItemLayout={(_, index) => ({ length:') >= 3


def test_admin_activity_virtualizes_dynamic_event_rows() -> None:
    source = ADMIN_ACTIVITY_PATH.read_text(encoding='utf-8')

    assert 'activity-events-virtual-list' in source
    assert 'const getEventItemLayout = useCallback' in source
    assert 'const renderEventItem = useCallback' in source
    assert '<FlatList' in source


def test_gls_uses_single_window_dimensions_source_and_theme_colors() -> None:
    source = GLS_PATH.read_text(encoding='utf-8')

    assert source.count('useWindowDimensions(') == 1
    assert source.count('useGLSBreakpoint()') >= 3
    assert "backgroundColor: colors.surface" in source
    assert "backgroundColor: colors.primary" in source
    assert "color: colors.primaryText" in source
    assert "'var(--app-surface)'" not in source
    assert "'var(--app-primary)'" not in source
    assert "'var(--app-primary-text)'" not in source
