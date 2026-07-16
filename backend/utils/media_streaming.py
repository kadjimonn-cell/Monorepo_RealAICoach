"""Media storage utilities for internal streaming."""

from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, Response
import os
import mimetypes
import re

MEDIA_ROOT = Path(__file__).parent.parent / "media"
VIDEO_DIR = MEDIA_ROOT / "videos"
AUDIO_DIR = MEDIA_ROOT / "audio"
THUMB_DIR = MEDIA_ROOT / "thumbnails"

DEFAULT_CHUNK_SIZE = 1024 * 1024


def ensure_media_dirs() -> None:
    for directory in (MEDIA_ROOT, VIDEO_DIR, AUDIO_DIR, THUMB_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def get_media_path(kind: str, filename: str) -> Path:
    ensure_media_dirs()
    safe_name = os.path.basename(filename)
    if kind == "video":
        return VIDEO_DIR / safe_name
    if kind == "audio":
        return AUDIO_DIR / safe_name
    if kind == "thumb":
        return THUMB_DIR / safe_name
    raise HTTPException(status_code=400, detail="Unknown media type")


def guess_mime_type(file_path: Path, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or fallback


def _file_iterator(file_path: Path, start: int, end: int, chunk_size: int = DEFAULT_CHUNK_SIZE):
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def stream_with_range(request: Request, file_path: Path, content_type: str | None = None) -> Response:
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")

    file_size = file_path.stat().st_size
    content_type = content_type or guess_mime_type(file_path)
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(file_path, media_type=content_type)

    match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        return FileResponse(file_path, media_type=content_type)

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start >= file_size:
        raise HTTPException(status_code=416, detail="Requested range not satisfiable")

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }

    return StreamingResponse(
        _file_iterator(file_path, start, end),
        status_code=206,
        media_type=content_type,
        headers=headers,
    )


def build_hls_manifest(stream_url: str, duration: int | float | None = None) -> str:
    safe_duration = int(duration or 60)
    if safe_duration <= 0:
        safe_duration = 60
    # Multi-quality master playlist (simulated adaptive bitrate)
    return "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{safe_duration}",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            f"#EXTINF:{safe_duration}.0,",
            stream_url,
            "#EXT-X-ENDLIST",
        ]
    )


def build_hls_master_playlist(video_id: str, token: str = "") -> str:
    """Build an HLS master playlist with multiple quality levels (simulated)."""
    token_qs = f"?token={token}" if token else ""
    base = f"/api/video/hls/{video_id}"
    return "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "",
            "# Auto quality",
            '#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,NAME="360p"',
            f"{base}.m3u8{token_qs}&quality=low",
            "",
            '#EXT-X-STREAM-INF:BANDWIDTH=1400000,RESOLUTION=854x480,NAME="480p"',
            f"{base}.m3u8{token_qs}&quality=medium",
            "",
            '#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720,NAME="720p"',
            f"{base}.m3u8{token_qs}&quality=high",
            "",
            '#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,NAME="1080p"',
            f"{base}.m3u8{token_qs}&quality=auto",
        ]
    )
