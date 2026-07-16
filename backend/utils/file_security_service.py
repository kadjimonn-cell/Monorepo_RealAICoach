"""File security hardening helpers.

Provides:
- MIME sniffing by magic bytes
- SHA-256 checksum generation
- Antivirus scan (ClamAV when available) with strict EICAR fallback checks
"""

from __future__ import annotations

import hashlib
import subprocess
from typing import Iterable, Dict, Any


EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_content_type(value: str) -> str:
    ct = str(value or "").strip().lower()
    aliases = {
        "image/jpg": "image/jpeg",
        "application/x-zip-compressed": "application/zip",
    }
    return aliases.get(ct, ct)


def _is_probable_text(content: bytes) -> bool:
    if not content:
        return False
    sample = content[:4096]
    if b"\x00" in sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False

    printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
    return printable / max(1, len(decoded)) >= 0.9


def sniff_mime_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "application/zip"
    if content.startswith(b"{\\rtf"):
        return "application/rtf"
    if content.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if _is_probable_text(content):
        return "text/plain"
    raise ValueError("Unsupported or suspicious file signature")


def _scan_with_clamav(content: bytes) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["clamscan", "--no-summary", "--stdout", "-"],
            input=content,
            capture_output=True,
            timeout=20,
        )
    except FileNotFoundError:
        return {"engine": "clamav", "status": "unavailable", "details": "clamscan not installed"}
    except subprocess.TimeoutExpired:
        return {"engine": "clamav", "status": "unavailable", "details": "scan timeout"}

    output = (result.stdout or b"").decode(errors="ignore").strip()
    if result.returncode == 0:
        return {"engine": "clamav", "status": "clean", "details": output or "OK"}
    if result.returncode == 1:
        return {"engine": "clamav", "status": "infected", "details": output or "Infected"}
    return {
        "engine": "clamav",
        "status": "unavailable",
        "details": output or (result.stderr or b"").decode(errors="ignore").strip() or f"return_code={result.returncode}",
    }


def _fallback_signature_scan(content: bytes) -> Dict[str, Any]:
    if EICAR_SIGNATURE in content:
        return {"engine": "fallback", "status": "infected", "details": "EICAR signature detected"}
    return {"engine": "fallback", "status": "clean", "details": "fallback signature checks passed"}


def enforce_antivirus_scan(content: bytes) -> Dict[str, Any]:
    """Run antivirus checks independent of MIME validation.

    Returns scan details and raises ValueError when malware signatures are detected.
    """
    clam = _scan_with_clamav(content)
    if clam.get("status") == "infected":
        raise ValueError("Antivirus scan failed")

    fallback = _fallback_signature_scan(content)
    if fallback.get("status") == "infected":
        raise ValueError("Fallback signature scan failed")

    return {
        "clamav": clam,
        "fallback": fallback,
    }


def enforce_file_security(
    *,
    content: bytes,
    claimed_content_type: str,
    allowed_content_types: Iterable[str],
    allow_unrecognized_signatures: bool = False,
) -> Dict[str, Any]:
    claimed = _normalize_content_type(claimed_content_type)
    allowed = {_normalize_content_type(x) for x in allowed_content_types}
    if claimed not in allowed:
        raise ValueError("Invalid declared content type")

    sniffing_mode = "strict"
    try:
        sniffed = _normalize_content_type(sniff_mime_type(content))
    except ValueError:
        if not allow_unrecognized_signatures:
            raise
        sniffed = claimed
        sniffing_mode = "declared-only"

    zip_compatible_claims = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    mismatch_is_allowed = (
        (claimed == "application/octet-stream" and sniffed in allowed)
        or (claimed in zip_compatible_claims and sniffed == "application/zip")
    )

    if sniffed not in allowed and not mismatch_is_allowed:
        raise ValueError("Sniffed MIME type is not allowed")
    if sniffed != claimed and not mismatch_is_allowed:
        raise ValueError(f"Declared MIME ({claimed}) does not match sniffed MIME ({sniffed})")

    antivirus = enforce_antivirus_scan(content)

    checksum = compute_sha256(content)
    return {
        "checksum_sha256": checksum,
        "sniffed_content_type": sniffed,
        "sniffing_mode": sniffing_mode,
        "antivirus": {
            "clamav": antivirus.get("clamav"),
            "fallback": antivirus.get("fallback"),
        },
    }
