"""Image Optimization Utility — Compress images in static/assets directories using Pillow."""

import os
import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_QUALITY = 80
MAX_DIMENSION = 1920  # Max width or height


def optimize_image(filepath: str, quality: int = DEFAULT_QUALITY, max_dim: int = MAX_DIMENSION) -> dict:
    """Optimize a single image file. Returns stats dict."""
    path = Path(filepath)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {"file": str(path), "status": "skipped", "reason": "unsupported format"}

    original_size = path.stat().st_size

    try:
        with Image.open(path) as img:
            # Resize if larger than max dimension
            w, h = img.size
            resized = False
            if w > max_dim or h > max_dim:
                ratio = min(max_dim / w, max_dim / h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                resized = True

            # Convert RGBA to RGB for JPEG
            if img.mode == "RGBA" and path.suffix.lower() in (".jpg", ".jpeg"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg

            # Save with optimization
            save_kwargs = {"optimize": True}
            if path.suffix.lower() in (".jpg", ".jpeg"):
                save_kwargs["quality"] = quality
            elif path.suffix.lower() == ".webp":
                save_kwargs["quality"] = quality
            elif path.suffix.lower() == ".png":
                save_kwargs["compress_level"] = 9

            img.save(path, **save_kwargs)

        new_size_bytes = path.stat().st_size
        saved = original_size - new_size_bytes
        pct = round(saved / original_size * 100, 1) if original_size > 0 else 0

        return {
            "file": str(path),
            "status": "optimized",
            "original_bytes": original_size,
            "new_bytes": new_size_bytes,
            "saved_bytes": saved,
            "saved_pct": pct,
            "resized": resized,
        }
    except Exception as e:
        return {"file": str(path), "status": "error", "error": str(e)}


def optimize_directory(directory: str, quality: int = DEFAULT_QUALITY, max_dim: int = MAX_DIMENSION) -> dict:
    """Optimize all images in a directory recursively."""
    results = []
    total_saved = 0
    total_original = 0
    optimized_count = 0
    error_count = 0

    for root, _, files in os.walk(directory):
        for fname in files:
            fpath = os.path.join(root, fname)
            if Path(fpath).suffix.lower() in SUPPORTED_EXTENSIONS:
                result = optimize_image(fpath, quality, max_dim)
                results.append(result)
                if result["status"] == "optimized":
                    total_saved += result["saved_bytes"]
                    total_original += result["original_bytes"]
                    optimized_count += 1
                elif result["status"] == "error":
                    error_count += 1

    return {
        "directory": directory,
        "files_processed": len(results),
        "optimized": optimized_count,
        "errors": error_count,
        "total_original_bytes": total_original,
        "total_saved_bytes": total_saved,
        "total_saved_pct": round(total_saved / total_original * 100, 1) if total_original > 0 else 0,
        "details": results,
    }


if __name__ == "__main__":

    target_dirs = [
        "/app/frontend/assets",
        "/app/frontend/public",
    ]

    print("Image Optimization Utility")
    print("=" * 50)

    for d in target_dirs:
        if os.path.isdir(d):
            print(f"\nOptimizing: {d}")
            result = optimize_directory(d)
            print(f"  Files: {result['files_processed']}, Optimized: {result['optimized']}, Errors: {result['errors']}")
            print(f"  Saved: {result['total_saved_bytes']:,} bytes ({result['total_saved_pct']}%)")
        else:
            print(f"\nSkipping (not found): {d}")

    print("\nDone.")
