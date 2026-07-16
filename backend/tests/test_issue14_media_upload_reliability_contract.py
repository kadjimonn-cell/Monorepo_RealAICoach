from pathlib import Path


VIDEO_QA_FRONTEND_PATH = Path('/app/frontend/app/careers/video-qa/[token].tsx')
CAREERS_TIER3_PATH = Path('/app/backend/routes/careers_tier3.py')
MIDDLEWARE_PATH = Path('/app/backend/middleware.py')
CAREERS_ATTACHMENTS_PATH = Path('/app/backend/routes/careers_attachments.py')
SUPPORT_PATH = Path('/app/backend/routes/support.py')
TICKETS_PATH = Path('/app/backend/routes/tickets.py')
IDV_PATH = Path('/app/backend/routes/id_verification.py')


def test_issue14_video_qa_frontend_uses_formdata_xhr_and_cleanup_refs() -> None:
    source = VIDEO_QA_FRONTEND_PATH.read_text(encoding='utf-8')

    assert 'readAsDataURL(' not in source
    assert 'new FormData()' in source
    assert 'new XMLHttpRequest()' in source
    assert 'xhr.upload.onprogress' in source
    assert 'previewObjectUrlRef' in source
    assert 'URL.revokeObjectURL(' in source
    assert 'autoStopTimerRef' in source
    assert 'clearTimeout(autoStopTimerRef.current)' in source


def test_issue14_video_qa_backend_accepts_multipart_and_enforces_size_security() -> None:
    source = CAREERS_TIER3_PATH.read_text(encoding='utf-8')

    assert 'video_file: UploadFile | None = File(default=None)' in source
    assert '"multipart/form-data" in content_type_header' in source
    assert 'VIDEO_QA_MAX_FILE_BYTES = 50 * 1024 * 1024' in source
    assert 'enforce_file_security(' in source


def test_issue14_middleware_has_route_specific_content_length_enforcement() -> None:
    source = MIDDLEWARE_PATH.read_text(encoding='utf-8')

    assert 'UPLOAD_CONTENT_LIMITS' in source
    assert '/api/careers/video-qa/' in source
    assert '/api/careers/apply/attachment' in source
    assert '/api/support/chat/attachment' in source
    assert '/api/tickets/upload-attachment' in source
    assert '/api/id-verification/kyc/upload-file' in source
    assert 'upload_content_length_guard_middleware' in source
    assert 'UPLOAD_CONTENT_TOO_LARGE' in source
    assert 'status_code=413' in source


def test_issue14_file_security_enforced_on_upload_routes() -> None:
    careers_source = CAREERS_ATTACHMENTS_PATH.read_text(encoding='utf-8')
    support_source = SUPPORT_PATH.read_text(encoding='utf-8')
    tickets_source = TICKETS_PATH.read_text(encoding='utf-8')
    idv_source = IDV_PATH.read_text(encoding='utf-8')

    assert 'enforce_file_security' in careers_source
    assert 'enforce_file_security' in support_source
    assert 'enforce_file_security' in tickets_source
    assert 'enforce_file_security' in idv_source
