from pathlib import Path


SOURCE_PATH = Path("/app/backend/middleware.py")


def _middleware_segment() -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    start = source.index("async def response_sanitization_middleware")
    end = source.index("async def _safe_call_next", start)
    return source[start:end]


def test_trusted_binary_content_types_are_explicitly_bypassed() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    segment = _middleware_segment()

    assert "def _is_trusted_binary_content_type" in source
    assert "application/octet-stream" in source
    assert "image/" in source
    assert "video/" in source
    assert "if _is_trusted_binary_content_type(content_type):" in segment


def test_body_buffering_happens_only_after_json_guard() -> None:
    segment = _middleware_segment()

    assert "not _is_auth_sanitization_path(path)" in segment
    json_guard = segment.index('"application/json" not in content_type_lower')
    trusted_guard = segment.index("if _is_trusted_binary_content_type(content_type):")
    body_iter = segment.index("async for chunk in response.body_iterator")

    assert trusted_guard < body_iter
    assert json_guard < body_iter
