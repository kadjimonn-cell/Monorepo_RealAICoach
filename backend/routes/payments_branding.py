"""Shared branding and logo helpers for payments exports."""

from __future__ import annotations

from functools import lru_cache
import logging
import os
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen

logger = logging.getLogger("routes.payments.branding")

BRAND_LOGO_URL = os.environ.get("BRAND_LOGO_URL", "")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")
STATIC_BRAND_LOGO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "images", "brand-logo-full.png")
)
STATIC_DOCUMENT_LOGO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "images", "brand-logo-chip.png")
)


def get_brand_logo_public_url() -> str:
    if FRONTEND_BASE_URL:
        return f"{FRONTEND_BASE_URL}/api/static/images/brand-logo-full.png"
    return BRAND_LOGO_URL


def get_document_logo_public_url() -> str:
    if FRONTEND_BASE_URL:
        return f"{FRONTEND_BASE_URL}/api/static/images/brand-logo-chip.png"
    return get_brand_logo_public_url()


@lru_cache(maxsize=1)
def get_brand_logo_bytes() -> bytes | None:
    if os.path.exists(STATIC_BRAND_LOGO_PATH):
        try:
            with open(STATIC_BRAND_LOGO_PATH, "rb") as local_logo:
                return local_logo.read()
        except Exception as exc:
            logger.warning("Unable to read local brand logo for PDF rendering: %s", exc)
    if not BRAND_LOGO_URL:
        return None
    try:
        with urlopen(BRAND_LOGO_URL, timeout=10) as response:
            return response.read()
    except Exception as exc:
        logger.warning("Unable to fetch brand logo for PDF rendering: %s", exc)
        return None


@lru_cache(maxsize=1)
def get_document_logo_bytes() -> bytes | None:
    if os.path.exists(STATIC_DOCUMENT_LOGO_PATH):
        try:
            with open(STATIC_DOCUMENT_LOGO_PATH, "rb") as local_logo:
                return local_logo.read()
        except Exception as exc:
            logger.warning("Unable to read document logo for PDF rendering: %s", exc)
    return get_brand_logo_bytes()


@lru_cache(maxsize=1)
def get_brand_logo_temp_path() -> str | None:
    logo_bytes = get_document_logo_bytes()
    if not logo_bytes:
        return None
    suffix = os.path.splitext(urlparse(get_document_logo_public_url() or BRAND_LOGO_URL).path)[1] or ".png"
    fd, path = tempfile.mkstemp(prefix="realaicoach-logo-", suffix=suffix)
    with os.fdopen(fd, "wb") as logo_file:
        logo_file.write(logo_bytes)
    return path


@lru_cache(maxsize=1)
def get_document_logo_temp_path() -> str | None:
    logo_bytes = get_document_logo_bytes()
    if not logo_bytes:
        return None
    suffix = os.path.splitext(urlparse(get_document_logo_public_url() or BRAND_LOGO_URL).path)[1] or ".png"
    fd, path = tempfile.mkstemp(prefix="realaicoach-document-logo-", suffix=suffix)
    with os.fdopen(fd, "wb") as logo_file:
        logo_file.write(logo_bytes)
    return path