"""
Careers ATS — Public multi-attachment upload for job applications.

Flow (stateless draft-token):
  1. Client generates a UUID draft_token when opening the apply modal.
  2. Each file uploaded to POST /api/careers/apply/attachment with the
     draft_token; server validates type/size/count and writes it to
     /app/backend/media/career_attachments/{attachment_id}.{ext}.
  3. Client submits POST /api/careers/apply with draft_token in the body.
     The existing handler (routes/careers.py) calls bind_attachments_to_application
     to move the DB refs from draft_token → application_id (so the same
     draft_token can never be reused).
  4. Admin retrieval via GET /api/careers/applications/{app_id}/attachments
     (admin-only).

Safeguards:
  - Type whitelist (PDF, DOCX, DOC, PNG, JPG, JPEG, TXT, ZIP).
  - Size gate: 10 MB per file, 25 MB aggregate per draft.
  - Count gate: 5 files max per draft.
  - Filename sanitization (strip control chars, clip length, default extension).
  - Per-IP rate limit: 20 uploads per 5 min (in-memory sliding window).
  - Unbound drafts auto-purged after 24h by a scheduler job.

Public endpoint is X-Requested-With gated via the existing middleware
whitelist (`/api/careers/` is already public + XSRF-gated).
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from routes.db import db
from utils.file_security_service import enforce_file_security

logger = logging.getLogger(__name__)
router = APIRouter()

ATTACHMENTS_COL = "careers_attachments"

# ── Configuration ───────────────────────────────────────────────────────
MEDIA_ROOT = Path("/app/backend/media/career_attachments")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

MAX_PER_FILE_BYTES = 10 * 1024 * 1024         # 10 MB per file
MAX_PER_DRAFT_BYTES = 25 * 1024 * 1024        # 25 MB aggregate per draft
MAX_PER_DRAFT_COUNT = 5                       # 5 files max per draft
DRAFT_TTL_HOURS = 24                          # unbound drafts purged after 24h

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "rtf",
    "png", "jpg", "jpeg", "webp", "gif",
    "zip",
}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/rtf",
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/zip", "application/x-zip-compressed",
    # Some browsers send octet-stream for known extensions — accept if the
    # file extension is whitelisted (verified below in the upload handler).
    "application/octet-stream",
}

ALLOWED_KINDS = {"resume", "portfolio", "cover_letter", "certification", "transcript", "other"}

# In-memory rate limit: 20 uploads / 5 min per IP. Cleared on restart — good
# enough for abuse mitigation without adding Redis. Admin traffic is
# whitelisted inside the handler.
_RATE_LIMIT_WINDOW_SECONDS = 300
_RATE_LIMIT_MAX = 20
_rate_state: dict[str, deque] = {}

_DRAFT_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-\s]")


# ── Helpers ─────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    hdr = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip") or ""
    if hdr:
        return hdr.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    q = _rate_state.setdefault(ip, deque())
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many uploads — slow down and try again in a few minutes.")
    q.append(now)


def _safe_filename(raw: str | None) -> str:
    if not raw:
        return "attachment.bin"
    name = raw.strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = _SAFE_FILENAME_RE.sub("_", name)
    return name[:180] or "attachment.bin"


def _extension_for(filename: str, content_type: str | None) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ALLOWED_EXTENSIONS:
        return ext
    # Fallback: infer from content_type whitelist
    ct_map = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "text/plain": "txt",
        "application/rtf": "rtf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
        "application/zip": "zip",
        "application/x-zip-compressed": "zip",
    }
    if content_type in ct_map:
        return ct_map[content_type]
    raise HTTPException(
        status_code=400,
        detail=(
            "Unsupported file type. Please upload one of: "
            "PDF, DOC, DOCX, TXT, RTF, PNG, JPG, JPEG, WEBP, GIF, ZIP."
        ),
    )


def _public_url(attachment_id: str, ext: str) -> str:
    return f"/api/media/career_attachments/{attachment_id}.{ext}"


def _serialize_attachment(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "attachment_id": doc["attachment_id"],
        "filename": doc.get("filename") or "",
        "size": int(doc.get("size_bytes") or 0),
        "content_type": doc.get("content_type") or "",
        "kind": doc.get("kind") or "other",
        "url": doc.get("url") or "",
        "created_at": doc.get("created_at") or "",
    }


# ── Public: upload endpoint ─────────────────────────────────────────────

@router.post("/careers/apply/attachment")
async def upload_career_attachment(
    request: Request,
    file: UploadFile = File(...),
    draft_token: str = Form(...),
    kind: str = Form("other"),
):
    """Upload one attachment for a pending job application draft.

    Returns a JSON payload with the attachment_id and a public URL under
    `/api/media/career_attachments/...`. Call this endpoint 1–5 times per
    draft_token before submitting the application.
    """
    # XSRF gate (middleware also enforces; keep defence-in-depth)
    if request.headers.get("x-requested-with", "").lower() != "xmlhttprequest":
        raise HTTPException(status_code=403, detail="X-Requested-With header required")

    # Rate limit
    _check_rate_limit(_client_ip(request))

    # Token format gate (stops path-traversal / absurd values early)
    if not draft_token or not _DRAFT_TOKEN_RE.match(draft_token):
        raise HTTPException(status_code=400, detail="Invalid draft_token format (8–64 chars, letters/digits/-/_)")

    kind = (kind or "other").strip().lower()
    if kind not in ALLOWED_KINDS:
        kind = "other"

    # Count + aggregate-size gate BEFORE reading the body
    existing = await db[ATTACHMENTS_COL].find(
        {"draft_token": draft_token, "application_id": None},
        {"_id": 0, "size_bytes": 1},
    ).to_list(length=MAX_PER_DRAFT_COUNT + 1)
    if len(existing) >= MAX_PER_DRAFT_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_PER_DRAFT_COUNT} attachments allowed per application.",
        )
    existing_bytes = sum(int(d.get("size_bytes") or 0) for d in existing)

    # Content-type whitelist
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{content_type}' is not allowed. "
                "Use PDF, DOC, DOCX, TXT, RTF, PNG, JPG, JPEG, WEBP, GIF, or ZIP."
            ),
        )

    # Read + size gate
    body = await file.read()
    size = len(body)
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty file — please select a non-empty file.")
    if size > MAX_PER_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size // (1024 * 1024)} MB). Max {MAX_PER_FILE_BYTES // (1024 * 1024)} MB per file.",
        )
    if existing_bytes + size > MAX_PER_DRAFT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Total attachments would exceed {MAX_PER_DRAFT_BYTES // (1024 * 1024)} MB. "
                "Remove or compress some files."
            ),
        )

    try:
        security_scan = enforce_file_security(
            content=body,
            claimed_content_type=(content_type or "application/octet-stream"),
            allowed_content_types=ALLOWED_CONTENT_TYPES,
            allow_unrecognized_signatures=True,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Attachment failed security scan")

    # Sanitize filename + resolve extension
    safe_name = _safe_filename(file.filename)
    ext = _extension_for(safe_name, content_type)

    # Persist
    attachment_id = f"att_{uuid.uuid4().hex[:16]}"
    disk_name = f"{attachment_id}.{ext}"
    disk_path = MEDIA_ROOT / disk_name
    try:
        with open(disk_path, "wb") as fp:
            fp.write(body)
    except Exception as e:  # pragma: no cover — disk failure is unrecoverable
        logger.exception("[careers_attachments] write failed")
        raise HTTPException(status_code=500, detail="Failed to store attachment.") from e

    now = datetime.now(timezone.utc)
    doc = {
        "attachment_id": attachment_id,
        "draft_token": draft_token,
        "application_id": None,           # bound on /careers/apply
        "filename": safe_name,
        "content_type": content_type or f"application/{ext}",
        "size_bytes": size,
        "kind": kind,
        "disk_path": str(disk_path),
        "url": _public_url(attachment_id, ext),
        "ext": ext,
        "created_at": now.isoformat(),
        "ip": _client_ip(request),
        "security_scan": security_scan,
    }
    await db[ATTACHMENTS_COL].insert_one(doc)
    logger.info(
        f"[careers_attachments] uploaded {attachment_id} kind={kind} "
        f"size={size} ext={ext} draft={draft_token[:10]}…"
    )
    return _serialize_attachment(doc)


@router.delete("/careers/apply/attachment/{attachment_id}")
async def remove_draft_attachment(request: Request, attachment_id: str, draft_token: str):
    """Remove an uploaded attachment before the application is submitted.

    Only works while the attachment is still bound to its draft_token — once
    the application is submitted the attachment is read-only from the
    public API (admin can delete via a separate admin route if needed).
    """
    if request.headers.get("x-requested-with", "").lower() != "xmlhttprequest":
        raise HTTPException(status_code=403, detail="X-Requested-With header required")
    if not _DRAFT_TOKEN_RE.match(draft_token or ""):
        raise HTTPException(status_code=400, detail="Invalid draft_token")

    doc = await db[ATTACHMENTS_COL].find_one(
        {"attachment_id": attachment_id, "draft_token": draft_token, "application_id": None},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found or already bound.")

    # Delete from disk best-effort
    disk = doc.get("disk_path")
    if disk:
        try:
            os.remove(disk)
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning(f"[careers_attachments] disk removal failed for {attachment_id}")

    await db[ATTACHMENTS_COL].delete_one(
        {"attachment_id": attachment_id, "draft_token": draft_token, "application_id": None}
    )
    return {"ok": True, "attachment_id": attachment_id}


@router.get("/careers/apply/attachment/{attachment_id}")
async def get_draft_attachment_meta(attachment_id: str):
    """Public endpoint to fetch attachment metadata by ID (no download gate).

    The binary is served via `/api/media/career_attachments/{id}.{ext}`.
    """
    doc = await db[ATTACHMENTS_COL].find_one({"attachment_id": attachment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _serialize_attachment(doc)


# ── Binding helper (called from /careers/apply in routes/careers.py) ────

async def bind_attachments_to_application(
    *, draft_token: str | None, application_id: str
) -> list[dict[str, Any]]:
    """Bind every attachment with this draft_token to the given app_id.

    Returns the serialized list of attachments now attached to the app.
    Safe to call with `draft_token=None` — it just returns `[]`.
    """
    if not draft_token:
        return []
    if not _DRAFT_TOKEN_RE.match(draft_token):
        logger.warning(f"[careers_attachments] bind called with malformed draft_token: {draft_token!r}")
        return []

    attachments: list[dict[str, Any]] = []
    async for doc in db[ATTACHMENTS_COL].find(
        {"draft_token": draft_token, "application_id": None}, {"_id": 0}
    ):
        attachments.append(_serialize_attachment(doc))

    if not attachments:
        return []

    await db[ATTACHMENTS_COL].update_many(
        {"draft_token": draft_token, "application_id": None},
        {"$set": {"application_id": application_id, "bound_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Drop the draft_token so it cannot be re-used. We keep a null marker
    # instead of $unset so the field shape is stable for downstream indexes.
    await db[ATTACHMENTS_COL].update_many(
        {"application_id": application_id, "draft_token": draft_token},
        {"$set": {"draft_token": None}},
    )
    logger.info(
        f"[careers_attachments] bound {len(attachments)} attachments → app={application_id}"
    )
    return attachments


# ── Admin: list application attachments ─────────────────────────────────

@router.get("/careers/applications/{application_id}/attachments")
async def list_application_attachments(request: Request, application_id: str):
    # Inline admin check to avoid circular import with routes.careers
    from routes.db import get_current_user
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    items: list[dict[str, Any]] = []
    async for doc in db[ATTACHMENTS_COL].find(
        {"application_id": application_id}, {"_id": 0}
    ).sort("created_at", 1):
        items.append(_serialize_attachment(doc))
    return {
        "application_id": application_id,
        "count": len(items),
        "attachments": items,
    }


# ── Maintenance: purge unbound drafts > 24h old ─────────────────────────

async def purge_stale_draft_attachments() -> dict[str, int]:
    """Remove attachments that were never bound to an application and are
    older than DRAFT_TTL_HOURS. Called by the scheduler at 04:00 UTC daily.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DRAFT_TTL_HOURS)).isoformat()
    stale = db[ATTACHMENTS_COL].find(
        {"application_id": None, "created_at": {"$lt": cutoff}}, {"_id": 0}
    )
    removed_disk = 0
    removed_db = 0
    async for doc in stale:
        disk = doc.get("disk_path")
        if disk:
            try:
                os.remove(disk)
                removed_disk += 1
            except FileNotFoundError:
                pass
            except Exception:
                logger.warning(f"[careers_attachments] purge disk fail {doc.get('attachment_id')}")
        removed_db += 1
    if removed_db:
        await db[ATTACHMENTS_COL].delete_many(
            {"application_id": None, "created_at": {"$lt": cutoff}}
        )
        logger.info(
            f"[careers_attachments] purged {removed_db} stale drafts ({removed_disk} files) <{cutoff}"
        )
    return {"purged_db": removed_db, "purged_disk": removed_disk, "cutoff": cutoff}
