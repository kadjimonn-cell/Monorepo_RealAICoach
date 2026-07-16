"""Profile photo upload and media serving routes."""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime, timezone
import uuid
import os
import logging
from PIL import Image as PILImage
import io

from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MEDIA_DIR = Path(__file__).parent.parent / "media"
PROFILES_DIR = MEDIA_DIR / "profiles"
THUMBNAILS_DIR = PROFILES_DIR / "thumbnails"

PROFILES_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
THUMBNAIL_SIZE = (150, 150)
PROFILE_MAX_SIZE = (800, 800)


def _get_base_url(request: Request) -> str:
    """Get the base URL from request headers (handles proxy)."""
    forwarded = request.headers.get("x-forwarded-host") or request.headers.get("host")
    scheme = request.headers.get("x-forwarded-proto", "https")
    if forwarded:
        return f"{scheme}://{forwarded}"
    return str(request.base_url).rstrip("/")


@router.post("/auth/upload-photo")
async def upload_profile_photo(request: Request, file: UploadFile = File(...)):
    """Upload profile photo with validation, compression, and thumbnail generation."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Validate content type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}. Allowed: JPG, PNG, WEBP")

    # Validate extension
    ext = Path(file.filename or "photo.jpg").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid file extension: {ext}")

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, detail=f"File too large. Maximum size: 5MB, got: {len(content) / (1024 * 1024):.1f}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        img = PILImage.open(io.BytesIO(content))
        img.verify()
        img = PILImage.open(io.BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or corrupted image file")

    # Generate unique filename
    file_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    safe_ext = ".webp"  # Always save as webp for optimization
    filename = f"{user.user_id}_{timestamp}_{file_id}{safe_ext}"
    thumb_filename = f"thumb_{filename}"

    # Resize main image
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail(PROFILE_MAX_SIZE, PILImage.LANCZOS)
    main_path = PROFILES_DIR / filename
    img.save(str(main_path), "WEBP", quality=85, optimize=True)

    # Generate thumbnail
    thumb_img = img.copy()
    thumb_img.thumbnail(THUMBNAIL_SIZE, PILImage.LANCZOS)
    thumb_path = THUMBNAILS_DIR / thumb_filename
    thumb_img.save(str(thumb_path), "WEBP", quality=75, optimize=True)

    # Build URLs
    base_url = _get_base_url(request)
    image_url = f"{base_url}/api/media/profiles/{filename}"
    thumbnail_url = f"{base_url}/api/media/profiles/thumbnails/{thumb_filename}"

    # Delete old profile image files
    old_user = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "profile_storage_path": 1, "thumbnail_storage_path": 1}
    )
    if old_user:
        for key in ("profile_storage_path", "thumbnail_storage_path"):
            old_path = old_user.get(key)
            if old_path and Path(old_path).exists():
                try:
                    Path(old_path).unlink()
                except Exception:
                    pass

    # Update database
    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "profile_image": image_url,
                "profile_image_thumbnail": thumbnail_url,
                "profile_storage_path": str(main_path),
                "thumbnail_storage_path": str(thumb_path),
                "last_image_update": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    file_size_kb = os.path.getsize(str(main_path)) / 1024
    thumb_size_kb = os.path.getsize(str(thumb_path)) / 1024

    return {
        "message": "Photo uploaded successfully",
        "profile_image_url": image_url,
        "profile_image_thumbnail": thumbnail_url,
        "file_size_kb": round(file_size_kb, 1),
        "thumbnail_size_kb": round(thumb_size_kb, 1),
        "dimensions": {"width": img.width, "height": img.height},
    }


@router.delete("/auth/delete-photo")
async def delete_profile_photo(request: Request):
    """Delete user's profile photo."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if user_doc:
        for key in ("profile_storage_path", "thumbnail_storage_path"):
            path = user_doc.get(key)
            if path and Path(path).exists():
                try:
                    Path(path).unlink()
                except Exception:
                    pass

    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "profile_image": "",
                "profile_image_thumbnail": "",
                "profile_storage_path": "",
                "thumbnail_storage_path": "",
                "last_image_update": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return {"message": "Profile photo deleted successfully"}


@router.get("/media/profiles/{filename}")
async def serve_profile_image(filename: str):
    """Serve profile images."""
    file_path = PROFILES_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    # Security: prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return FileResponse(
        str(file_path),
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/media/profiles/thumbnails/{filename}")
async def serve_thumbnail(filename: str):
    """Serve profile thumbnails."""
    file_path = THUMBNAILS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return FileResponse(
        str(file_path),
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/admin/media-storage/stats")
async def admin_media_storage_stats(request: Request):
    """Admin endpoint to view storage usage statistics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    total_profiles = len(list(PROFILES_DIR.glob("*.webp")))
    total_thumbs = len(list(THUMBNAILS_DIR.glob("*.webp")))
    profile_size = sum(f.stat().st_size for f in PROFILES_DIR.glob("*.webp"))
    thumb_size = sum(f.stat().st_size for f in THUMBNAILS_DIR.glob("*.webp"))

    users_with_photos = await db.users.count_documents({"profile_image": {"$ne": "", "$exists": True}})

    return {
        "total_profile_images": total_profiles,
        "total_thumbnails": total_thumbs,
        "profile_storage_mb": round(profile_size / (1024 * 1024), 2),
        "thumbnail_storage_mb": round(thumb_size / (1024 * 1024), 2),
        "total_storage_mb": round((profile_size + thumb_size) / (1024 * 1024), 2),
        "users_with_photos": users_with_photos,
    }
