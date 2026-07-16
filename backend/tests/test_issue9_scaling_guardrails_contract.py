from pathlib import Path
import re


FRONTEND_APP_ROOT = Path('/app/frontend/app')
FRONTEND_SRC_ROOT = Path('/app/frontend/src')

MANAGED_WS_HOOK = Path('/app/frontend/src/hooks/useManagedWebSocket.ts')
RECOVERABLE_ERROR_UTIL = Path('/app/frontend/src/utils/handleRecoverableError.ts')
WHITEBOARD_COMPONENT = Path('/app/frontend/src/components/WhiteboardCanvas.tsx')
COLLAB_DOCS_COMPONENT = Path('/app/frontend/src/components/CollaborativeDocsContent.tsx')
SYSTEM_MONITOR_PANEL = Path('/app/frontend/src/components/admin/SystemMonitorPanel.tsx')
PERFORMANCE_DASHBOARD_PANEL = Path('/app/frontend/src/components/admin/PerformanceDashboardPanel.tsx')
LIVE_ACTIVITY_FEED_PANEL = Path('/app/frontend/src/components/admin/LiveActivityFeedPanel.tsx')
OPERATIONS_DASHBOARD = Path('/app/frontend/src/components/admin/OperationsDashboard.tsx')
SUPPORT_TICKETS_PANEL = Path('/app/frontend/src/components/admin/SupportTicketsPanel.tsx')
MY_TICKETS_INNER = Path('/app/frontend/src/components/pages/MyTicketsInner.tsx')
EMPLOYER_PIPELINE_BOARD = Path('/app/frontend/src/components/jobs/EmployerPipelineBoard.tsx')
FPS_ARENA = Path('/app/frontend/src/components/fpsGame/FpsArena.tsx')
SIEM_PANEL = Path('/app/frontend/src/components/admin/SIEMPanel.tsx')
COMPETITOR_KEYWORD_PANEL = Path('/app/frontend/src/components/admin/CompetitorKeywordPanel.tsx')
AUTOMATION_ENGINE_PANEL = Path('/app/frontend/src/components/admin/AutomationEnginePanel.tsx')
INTERVIEW_ROOM_PAGE = Path('/app/frontend/app/interview-room.tsx')

# Issue 9 baseline captured after guardrail rollout.
# Core allowlist floor: only RealtimeContext + useManagedWebSocket should own raw constructor calls.
MAX_FRONTEND_RAW_WEBSOCKETS = 3  # +1: FPS Arena gameplay socket (intentionally unmanaged, see fps arena contract test)
MAX_FRONTEND_EMPTY_CATCH_BLOCKS = 0
MAX_FRONTEND_APP_EMPTY_CATCH_BLOCKS = 0
MAX_FRONTEND_SRC_EMPTY_CATCH_BLOCKS = 0


def _count_pattern(paths: list[Path], pattern: str) -> int:
    compiled = re.compile(pattern)
    total = 0
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        total += len(compiled.findall(path.read_text(encoding='utf-8')))
    return total


def _frontend_tsx_ts_files() -> list[Path]:
    files: list[Path] = []
    for root in (FRONTEND_APP_ROOT, FRONTEND_SRC_ROOT):
        files.extend(root.rglob('*.ts'))
        files.extend(root.rglob('*.tsx'))
    return files


def _frontend_app_tsx_ts_files() -> list[Path]:
    files: list[Path] = []
    files.extend(FRONTEND_APP_ROOT.rglob('*.ts'))
    files.extend(FRONTEND_APP_ROOT.rglob('*.tsx'))
    return files


def _frontend_src_tsx_ts_files() -> list[Path]:
    files: list[Path] = []
    files.extend(FRONTEND_SRC_ROOT.rglob('*.ts'))
    files.extend(FRONTEND_SRC_ROOT.rglob('*.tsx'))
    return files


def test_issue9_shared_primitives_exist() -> None:
    hook_source = MANAGED_WS_HOOK.read_text(encoding='utf-8')
    util_source = RECOVERABLE_ERROR_UTIL.read_text(encoding='utf-8')

    assert 'export const useManagedWebSocket' in hook_source
    assert 'maxReconnectAttempts' in hook_source
    assert 'export const handleRecoverableError' in util_source


def test_issue9_whiteboard_migrated_to_managed_websocket_and_structured_errors() -> None:
    source = WHITEBOARD_COMPONENT.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source


def test_issue9_collab_docs_migrated_to_managed_websocket_and_structured_errors() -> None:
    source = COLLAB_DOCS_COMPONENT.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source


def test_issue9_system_monitor_panel_migrated_to_managed_websocket() -> None:
    source = SYSTEM_MONITOR_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="system-monitor-ws-error"' in source


def test_issue9_performance_dashboard_panel_migrated_to_managed_websocket() -> None:
    source = PERFORMANCE_DASHBOARD_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="perf-ws-error"' in source


def test_issue9_live_activity_feed_panel_migrated_to_managed_websocket() -> None:
    source = LIVE_ACTIVITY_FEED_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="activity-feed-ws-status"' in source


def test_issue9_operations_dashboard_migrated_to_managed_websocket() -> None:
    source = OPERATIONS_DASHBOARD.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="ops-ws-error"' in source


def test_issue9_support_tickets_panel_migrated_to_managed_websocket() -> None:
    source = SUPPORT_TICKETS_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="support-tickets-ws-error"' in source


def test_issue9_my_tickets_inner_migrated_to_managed_websocket() -> None:
    source = MY_TICKETS_INNER.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="my-tickets-ws-error"' in source


def test_issue9_employer_pipeline_board_migrated_to_managed_websocket() -> None:
    source = EMPLOYER_PIPELINE_BOARD.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'window.WebSocket(' not in source
    assert 'catch {}' not in source


def test_issue9_fps_arena_gameplay_socket_contract() -> None:
    """FPS Arena uses an intentionally unmanaged realtime gameplay socket
    (game loop owns lifecycle); the contract is explicit cleanup + surfaced
    connection state instead of useManagedWebSocket."""
    source = FPS_ARENA.read_text(encoding='utf-8')

    assert 'connectWs' in source
    assert 'reconnectAttempts' in source
    assert 'ws.onclose' in source
    assert 'data-testid="fps-arena-connection-state"' in source
    assert 'cleanupRef' in source


def test_issue9_siem_panel_migrated_to_managed_websocket() -> None:
    source = SIEM_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="siem-ws-error"' in source


def test_issue9_competitor_keyword_panel_migrated_to_managed_websocket() -> None:
    source = COMPETITOR_KEYWORD_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="aso-ws-error"' in source


def test_issue9_automation_engine_panel_migrated_to_managed_websocket() -> None:
    source = AUTOMATION_ENGINE_PANEL.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="automation-ws-error"' in source


def test_issue9_interview_room_migrated_to_managed_websocket() -> None:
    source = INTERVIEW_ROOM_PAGE.read_text(encoding='utf-8')

    assert 'useManagedWebSocket' in source
    assert 'handleRecoverableError' in source
    assert 'new WebSocket(' not in source
    assert 'catch {}' not in source
    assert 'data-testid="interview-room-retry-button"' in source


def test_issue9_guardrail_raw_websocket_count_does_not_regress() -> None:
    files = _frontend_tsx_ts_files()
    websocket_count = _count_pattern(files, r'new\s+WebSocket\(|window\.WebSocket\(')
    assert websocket_count <= MAX_FRONTEND_RAW_WEBSOCKETS


def test_issue9_guardrail_empty_catch_count_does_not_regress() -> None:
    files = _frontend_tsx_ts_files()
    empty_catch_count = _count_pattern(files, r'catch\s*\{\s*\}')
    assert empty_catch_count <= MAX_FRONTEND_EMPTY_CATCH_BLOCKS


def test_issue9_guardrail_zero_empty_catch_in_frontend_app() -> None:
    files = _frontend_app_tsx_ts_files()
    empty_catch_count = _count_pattern(files, r'catch\s*\{\s*\}')
    assert empty_catch_count <= MAX_FRONTEND_APP_EMPTY_CATCH_BLOCKS


def test_issue9_guardrail_zero_empty_catch_in_frontend_src() -> None:
    files = _frontend_src_tsx_ts_files()
    empty_catch_count = _count_pattern(files, r'catch\s*\{\s*\}')
    assert empty_catch_count <= MAX_FRONTEND_SRC_EMPTY_CATCH_BLOCKS
