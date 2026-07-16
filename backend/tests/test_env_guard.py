"""Shared test env guards for live endpoint suites."""

from __future__ import annotations

import os


def require_backend_base_url() -> str:
    base_url = (os.environ.get("REACT_APP_BACKEND_URL") or "").strip()
    if not base_url:
        raise RuntimeError(
            "REACT_APP_BACKEND_URL is required for live API tests. "
            "Fail-fast enforced: remove fallback/empty BASE_URL patterns."
        )
    return base_url.rstrip("/")
