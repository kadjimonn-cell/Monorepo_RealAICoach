from pathlib import Path
import re


AI_DASHBOARD_PATH = Path('/app/frontend/app/ai-feature-dashboard.tsx')
INTERVIEW_ROOM_PATH = Path('/app/frontend/app/interview-room.tsx')
SUB_ANALYTICS_PATH = Path('/app/backend/routes/admin_subscription_analytics.py')
ADMIN_SESSIONS_PATH = Path('/app/backend/routes/admin_sessions.py')
MIDDLEWARE_PATH = Path('/app/backend/middleware.py')
FRONTEND_APP_DIR = Path('/app/frontend/app')


def _middleware_segment() -> str:
    source = MIDDLEWARE_PATH.read_text(encoding='utf-8')
    start = source.index('async def response_sanitization_middleware')
    end = source.index('async def _safe_call_next', start)
    return source[start:end]


def test_ai_dashboard_replaces_silent_alert_error_catches_with_retryable_handling() -> None:
    source = AI_DASHBOARD_PATH.read_text(encoding='utf-8')

    assert '} catch {}' not in source
    assert 'const [alertsError, setAlertsError] = useState<string>(\'\');' in source
    assert 'for (let attempt = 0; attempt < 3; attempt += 1)' in source
    assert 'data-testid="alerts-error-banner"' in source


def test_interview_room_adds_bounded_retry_for_initialize_and_ws_reconnect() -> None:
    source = INTERVIEW_ROOM_PATH.read_text(encoding='utf-8')

    assert 'const WS_MAX_RECONNECT_ATTEMPTS = 3;' in source
    assert 'const INITIALIZE_MAX_RETRIES = 2;' in source
    assert 'useManagedWebSocket' in source
    assert 'const wsEnabled = Boolean(activeRoomId && wsBase && user?.user_id && room?.status !== \'ended\');' in source
    assert 'for (let attempt = 0; attempt <= INITIALIZE_MAX_RETRIES; attempt += 1)' in source
    assert 'data-testid="interview-room-retry-button"' in source


def test_subscription_analytics_uses_single_roundtrip_facet_counting() -> None:
    source = SUB_ANALYTICS_PATH.read_text(encoding='utf-8')

    assert 'async def _count_many_facet(collection, filters: dict[str, dict]) -> dict[str, int]:' in source
    assert 'collection.aggregate([{"$facet": facet_pipeline}])' in source
    assert 'base_counts = await _count_many_facet(' in source


def test_admin_sessions_avoids_silent_5000_row_truncation() -> None:
    source = ADMIN_SESSIONS_PATH.read_text(encoding='utf-8')

    assert 'async def _collect_cursor_docs(cursor, batch_size: int = 1000):' in source
    assert '.to_list(5000)' not in source
    assert 'all_sessions = await _collect_cursor_docs' in source


def test_auth_response_sanitization_adds_payload_size_guard_before_buffering() -> None:
    source = MIDDLEWARE_PATH.read_text(encoding='utf-8')
    segment = _middleware_segment()

    assert 'MAX_AUTH_SANITIZE_BYTES = 256 * 1024' in source
    assert 'content_length_raw = response.headers.get("content-length")' in segment
    assert 'if int(content_length_raw) > MAX_AUTH_SANITIZE_BYTES:' in segment
    assert segment.index('content_length_raw = response.headers.get("content-length")') < segment.index(
        'async for chunk in response.body_iterator'
    )


def test_issue8_batch3_no_empty_catches_left_in_frontend_app_routes() -> None:
    pattern = re.compile(r'catch\s*\{\s*\}|catch\s*\{\s*/\*|catch \{ //|catch \([^\)]*\) \{\s*\}')
    offenders: list[str] = []

    for path in sorted(FRONTEND_APP_DIR.rglob('*.tsx')) + sorted(FRONTEND_APP_DIR.rglob('*.ts')):
        source = path.read_text(encoding='utf-8')
        if pattern.search(source):
            offenders.append(str(path))

    assert not offenders, f'Found empty/silent catch blocks in frontend app routes: {offenders}'


def test_issue8_batch4_no_weak_catch_only_console_or_plain_error_setters() -> None:
    weak_patterns = [
        re.compile(r'catch \([^\)]*\) \{\s*console\.(error|warn)'),
        re.compile(r'catch \([^\)]*\) \{\s*setErr\('),
        re.compile(r'catch \([^\)]*\) \{\s*setError\('),
        re.compile(r'catch \([^\)]*\) \{\s*Alert\.alert'),
        re.compile(r'catch \([^\)]*\) \{\s*window\.alert'),
    ]
    offenders: list[str] = []
    batch4_targets = [
        Path('/app/frontend/app/admin-system.tsx'),
        Path('/app/frontend/app/messages.tsx'),
        Path('/app/frontend/app/employer-apply.tsx'),
        Path('/app/frontend/app/executive-dashboard.tsx'),
        Path('/app/frontend/app/admin/mobile-money-dashboard.tsx'),
        Path('/app/frontend/app/admin/subscription-dashboard.tsx'),
        Path('/app/frontend/app/subscription/plans.tsx'),
        Path('/app/frontend/app/book/[token].tsx'),
        Path('/app/frontend/app/features/fitness.tsx'),
        Path('/app/frontend/app/features/medimate.tsx'),
        Path('/app/frontend/app/features/smartbuy.tsx'),
        Path('/app/frontend/app/careers.tsx'),
    ]

    for path in batch4_targets:
        source = path.read_text(encoding='utf-8')
        if any(pattern.search(source) for pattern in weak_patterns):
            offenders.append(str(path))

    assert not offenders, (
        'Found weak catch handlers (console/error-only setter/alert-only) in frontend app routes: '
        f'{offenders}'
    )


def test_issue8_batch5_no_weak_catches_in_auth_policy_privacy_scan_payment_routes() -> None:
    weak_patterns = [
        re.compile(r'catch \([^\)]*\) \{\s*console\.(error|warn)'),
        re.compile(r'catch \([^\)]*\) \{\s*setErr\('),
        re.compile(r'catch \([^\)]*\) \{\s*setError\('),
        re.compile(r'catch \([^\)]*\) \{\s*Alert\.alert'),
        re.compile(r'catch \([^\)]*\) \{\s*window\.alert'),
        re.compile(r'catch\s*\{'),
        re.compile(r'\.catch\(\(\) => \{\}\)'),
        re.compile(r'\.catch\(\(\) => \(\{ data: null \}\)\)'),
    ]
    offenders: list[str] = []
    batch5_targets = [
        Path('/app/frontend/app/auth/register.tsx'),
        Path('/app/frontend/app/auth/qr-approve.tsx'),
        Path('/app/frontend/app/auth/forgot-password.tsx'),
        Path('/app/frontend/app/auth/sso-debug.tsx'),
        Path('/app/frontend/app/policy-console.tsx'),
        Path('/app/frontend/app/privacy-request.tsx'),
        Path('/app/frontend/app/privacy-security.tsx'),
        Path('/app/frontend/app/scan-history.tsx'),
        Path('/app/frontend/app/payment-document-v2.tsx'),
        Path('/app/frontend/app/payment-history-export-v2.tsx'),
        Path('/app/frontend/app/subscription/payment.tsx'),
        Path('/app/frontend/app/subscription/mobile-money.tsx'),
        Path('/app/frontend/app/subscription/kyc.tsx'),
    ]

    for path in batch5_targets:
        source = path.read_text(encoding='utf-8')
        if any(pattern.search(source) for pattern in weak_patterns):
            offenders.append(str(path))

    assert not offenders, f'Found weak catches in Batch-5 targets: {offenders}'
