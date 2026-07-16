from pathlib import Path


LANGUAGE_CONTEXT_PATH = Path('/app/frontend/src/i18n/LanguageContext.tsx')
TRANSLATION_LOADER_PATH = Path('/app/frontend/src/i18n/translationLoader.ts')
VIDEO_QA_PATH = Path('/app/frontend/app/careers/video-qa/[token].tsx')
EDIT_PROFILE_PATH = Path('/app/frontend/app/edit-profile.tsx')
INTERVIEW_ROOM_PATH = Path('/app/frontend/app/interview-room.tsx')
LOCALES_DIR = Path('/app/frontend/src/i18n/locales')


def test_issue12_language_context_is_stale_while_revalidate_nonblocking() -> None:
    source = LANGUAGE_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'pointerEvents="none"' in source
    assert 'Syncing language… showing previous content meanwhile.' in source
    assert 'setTimeout(() => {' not in source
    assert '}, 90);' not in source


def test_issue12_seed_dom_engine_warns_on_english_echo_keys() -> None:
    source = TRANSLATION_LOADER_PATH.read_text(encoding='utf-8')

    assert 'console.warn(`[i18n][seedDomEngine] untranslated locale echo detected: locale=${code} key=${key}`);' in source
    assert 'if (source === translatedNormalized) {' in source


def test_issue12_scoped_pages_use_translation_keys_for_reported_strings() -> None:
    video_source = VIDEO_QA_PATH.read_text(encoding='utf-8')
    profile_source = EDIT_PROFILE_PATH.read_text(encoding='utf-8')
    interview_source = INTERVIEW_ROOM_PATH.read_text(encoding='utf-8')

    assert "tx('videoQa.states.inviteNotAvailable', 'Invite not available')" in video_source
    assert "tx('videoQa.errors.cameraAccessDenied', 'Camera access denied')" in video_source

    assert "tx('editProfile.alerts.nameRequired', 'Name cannot be empty')" in profile_source
    assert "tx('editProfile.alerts.profileUpdated', 'Profile updated successfully!')" in profile_source

    assert "tx('interviewRoom.errors.reconnecting', 'Reconnecting live channel...')" in interview_source
    assert "tx('interviewRoom.errors.liveUnstable', 'Live connection unstable. Reconnecting...')" in interview_source

    assert "setErr('Invite not available')" not in video_source
    assert "Alert.alert('Name cannot be empty'" not in profile_source
    assert "setError('Reconnecting live channel...')" not in interview_source


def test_issue12_reported_i18n_keys_exist_in_all_23_locale_files() -> None:
    locale_files = sorted(LOCALES_DIR.glob('*.ts'))
    assert len(locale_files) == 23

    required_keys = [
        'videoQa.states.inviteNotAvailable',
        'videoQa.errors.cameraAccessDenied',
        'editProfile.alerts.nameRequired',
        'editProfile.alerts.profileUpdated',
        'interviewRoom.errors.reconnecting',
        'interviewRoom.errors.liveUnstable',
    ]

    for locale_file in locale_files:
        content = locale_file.read_text(encoding='utf-8')
        for key in required_keys:
            assert f"'{key}'" in content or f'"{key}"' in content, f'{key} missing in {locale_file.name}'
