"""
Issue 8 Phase-2 Contract Tests: Recoverable Error Handling
Tests that silent catch handling in high-traffic frontend pages has been replaced
with structured recoverable handling (client error reporting + user-visible state + retry action).
"""
from pathlib import Path
import re


# File paths for the pages being tested
HOME_INDEX_PATH = Path('/app/frontend/app/(tabs)/index.tsx')
PROFILE_PATH = Path('/app/frontend/app/(tabs)/profile.tsx')
INTERVIEW_ROOM_PATH = Path('/app/frontend/app/interview-room.tsx')
CAREERS_PATH = Path('/app/frontend/app/careers.tsx')
JOB_PLATFORM_PATH = Path('/app/frontend/app/job-platform.tsx')
BLOG_INDEX_PATH = Path('/app/frontend/app/blog/index.tsx')
CONTACT_PATH = Path('/app/frontend/app/contact.tsx')
HELP_PATH = Path('/app/frontend/app/help.tsx')
APP_RECOVERABLE_ERROR_PATH = Path('/app/frontend/src/utils/appRecoverableError.ts')


def test_app_recoverable_error_utility_exists_with_correct_structure():
    """Verify the appRecoverableError utility has the correct structure."""
    source = APP_RECOVERABLE_ERROR_PATH.read_text(encoding='utf-8')
    
    # Check for required imports
    assert "import { Alert, Platform } from 'react-native'" in source
    assert "import { reportClientCrash } from '../services/clientErrorReporter'" in source
    
    # Check for RecoverableErrorOptions type
    assert 'type RecoverableErrorOptions = {' in source
    assert 'scope: string;' in source
    assert 'error: any;' in source
    assert 'message: string;' in source
    assert 'onRetry?: () => void;' in source
    assert 'setError?: (message: string) => void;' in source
    
    # Check for deduplication logic
    assert 'DEDUPE_WINDOW_MS' in source
    assert 'shouldNotify' in source
    
    # Check for handleAppRecoverableError export
    assert 'export const handleAppRecoverableError' in source
    
    # Check for reportClientCrash call
    assert 'reportClientCrash({' in source
    
    # Check for web platform handling with retry
    assert "Platform.OS === 'web'" in source
    assert 'window.confirm' in source
    
    # Check for native Alert handling
    assert 'Alert.alert(' in source
    assert "'Retry'" in source


def test_home_index_has_recoverable_error_handling():
    """Home page auxiliary checks now surface recoverable error banner with retry."""
    source = HOME_INDEX_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../../src/utils/appRecoverableError'" in source
    
    # Check for error state
    assert "const [homeRecoverableError, setHomeRecoverableError] = useState" in source
    
    # Check for handleAppRecoverableError usage with proper parameters
    assert "handleAppRecoverableError({" in source
    assert "scope: 'home.index." in source
    assert "setError: setHomeRecoverableError" in source
    assert "onRetry:" in source
    
    # Check for error banner UI with testID
    assert 'data-testid="home-recoverable-error-banner"' in source
    assert 'testID="home-recoverable-error-banner"' in source
    
    # Check for retry button
    assert 'data-testid="home-recoverable-error-retry"' in source


def test_profile_page_has_recoverable_error_handling():
    """Profile page loadData catch now reports and shows retry banner."""
    source = PROFILE_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../../src/utils/appRecoverableError'" in source
    
    # Check for error state
    assert "const [profileDataError, setProfileDataError] = useState" in source
    
    # Check for handleAppRecoverableError usage in loadData
    assert "handleAppRecoverableError({" in source
    assert "scope: 'profile.load-data'" in source
    assert "setError: setProfileDataError" in source
    assert "onRetry: () => { void loadData(); }" in source
    
    # Check for error banner UI with testID
    assert 'data-testid="profile-recoverable-error-banner"' in source
    assert 'testID="profile-recoverable-error-banner"' in source
    
    # Check for retry button
    assert 'data-testid="profile-recoverable-error-retry"' in source


def test_interview_room_has_recoverable_error_handling():
    """Interview room camera/local refresh/performance catches now report + set error + retry."""
    source = INTERVIEW_ROOM_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../src/utils/appRecoverableError'" in source
    
    # Check for handleAppRecoverableError usage in multiple places
    assert "handleAppRecoverableError({" in source
    
    # Check for local preview error handling
    assert "scope: 'interview-room.local-preview'" in source
    
    # Check for room refresh error handling
    assert "scope: 'interview-room.room-refresh-api'" in source
    
    # Check for performance load error handling
    assert "scope: 'interview-room.performance-load'" in source
    
    # Check for error banner UI with testID
    assert 'data-testid="interview-room-error-banner"' in source
    assert 'testID="interview-room-error-banner"' in source
    
    # Check for retry button
    assert 'data-testid="interview-room-retry-button"' in source
    assert 'testID="interview-room-retry-button"' in source


def test_careers_page_has_recoverable_error_handling():
    """Careers load and attachment upload catches now report + set user-visible message + retry."""
    source = CAREERS_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../src/utils/appRecoverableError'" in source
    
    # Check for handleAppRecoverableError usage
    assert "handleAppRecoverableError({" in source
    
    # Check for careers load error handling
    assert "scope: 'careers.load'" in source
    assert "onRetry: () => { void load(); }" in source
    
    # Check for attachment upload error handling
    assert "scope: 'careers.attachment-upload'" in source


def test_job_platform_has_recoverable_error_handling():
    """Job platform summary refresh catch now reports + user-visible hint + retry."""
    source = JOB_PLATFORM_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../src/utils/appRecoverableError'" in source
    
    # Check for handleAppRecoverableError usage
    assert "handleAppRecoverableError({" in source
    
    # Check for summary load error handling
    assert "scope: 'job-platform.summary-load'" in source
    assert "setError: setFunnelHint" in source
    assert "onRetry: () => { void loadPortalSummary(); }" in source


def test_blog_index_has_recoverable_error_handling():
    """Blog index newsletter/feed/live setup catches now report + feed retry banner."""
    source = BLOG_INDEX_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../../src/utils/appRecoverableError'" in source
    
    # Check for error state
    assert "const [feedError, setFeedError] = useState" in source
    
    # Check for handleAppRecoverableError usage in multiple places
    assert "handleAppRecoverableError({" in source
    
    # Check for newsletter subscribe error handling
    assert "scope: 'blog.newsletter.subscribe'" in source
    
    # Check for feed fetch error handling
    assert "scope: 'blog.feed.fetch-all'" in source
    assert "setError: setFeedError" in source
    assert "onRetry: () => { void fetchAll(); }" in source
    
    # Check for live SSE error handling
    assert "scope: 'blog.live.sse-setup'" in source
    
    # Check for error banner UI with testID
    assert 'data-testid="blog-recoverable-error-banner"' in source
    assert 'testID="blog-recoverable-error-banner"' in source
    
    # Check for retry button
    assert 'data-testid="blog-recoverable-error-retry"' in source


def test_contact_page_has_recoverable_error_handling():
    """Contact support catches now report and trigger retry action."""
    source = CONTACT_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../src/utils/appRecoverableError'" in source
    
    # Check for handleAppRecoverableError usage in multiple places
    assert "handleAppRecoverableError({" in source
    
    # Check for support email insights error handling
    assert "scope: 'contact.support-email-insights'" in source
    assert "onRetry: () => { void fetchSupportEmailInsights(); }" in source
    
    # Check for AI support suggestion error handling
    assert "scope: 'contact.ai-support-suggestion'" in source
    
    # Check for reuse last context error handling
    assert "scope: 'contact.reuse-last-context'" in source
    
    # Check for submit email error handling
    assert "scope: 'contact.submit-email'" in source


def test_help_page_has_recoverable_error_handling():
    """Help chat/audio/feedback catches now report and provide retry action."""
    source = HELP_PATH.read_text(encoding='utf-8')
    
    # Check for import
    assert "import { handleAppRecoverableError } from '../src/utils/appRecoverableError'" in source
    
    # Check for handleAppRecoverableError usage in multiple places
    assert "handleAppRecoverableError({" in source
    
    # Check for chat attachment error handling
    assert "scope: 'help.chat.attachment-upload'" in source
    
    # Check for audio recording error handling
    assert "scope: 'help.audio.start-recording'" in source
    assert "scope: 'help.audio.process-recording'" in source
    
    # Check for feedback submit error handling
    assert "scope: 'help.feedback.submit'" in source


def test_all_pages_have_no_silent_empty_catches():
    """Verify no silent empty catch blocks remain in the tested files."""
    files_to_check = [
        HOME_INDEX_PATH,
        PROFILE_PATH,
        INTERVIEW_ROOM_PATH,
        CAREERS_PATH,
        JOB_PLATFORM_PATH,
        BLOG_INDEX_PATH,
        CONTACT_PATH,
        HELP_PATH,
    ]
    
    # Pattern for silent empty catches: } catch {} or } catch (e) {}
    silent_catch_pattern = re.compile(r'\}\s*catch\s*\([^)]*\)?\s*\{\s*\}')
    
    for file_path in files_to_check:
        source = file_path.read_text(encoding='utf-8')
        matches = silent_catch_pattern.findall(source)
        assert len(matches) == 0, f"Found silent empty catch in {file_path.name}: {matches}"


def test_all_error_handlers_have_scope_parameter():
    """Verify all handleAppRecoverableError calls have a scope parameter."""
    files_to_check = [
        HOME_INDEX_PATH,
        PROFILE_PATH,
        INTERVIEW_ROOM_PATH,
        CAREERS_PATH,
        JOB_PLATFORM_PATH,
        BLOG_INDEX_PATH,
        CONTACT_PATH,
        HELP_PATH,
    ]
    
    for file_path in files_to_check:
        source = file_path.read_text(encoding='utf-8')
        # Find all handleAppRecoverableError calls
        calls = re.findall(r'handleAppRecoverableError\(\{[^}]+\}', source, re.DOTALL)
        for call in calls:
            assert 'scope:' in call, f"Missing scope in handleAppRecoverableError call in {file_path.name}"
