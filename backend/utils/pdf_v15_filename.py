"""Canonical PDF v15 filename helpers for enterprise-grade artifacts."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def _slug(value: object, *, max_len: int = 80) -> str:
    raw = str(value or "na").strip().lower()
    token = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not token:
        token = "na"
    return token[:max_len]


def build_pdf_v15_filename(doc_type: str, entity_id: object, *, ts: datetime | None = None) -> str:
    """Return canonical filename: rac-{doc_type}-{entity_id}-{UTC timestamp}.pdf"""
    dt = ts or datetime.now(timezone.utc)
    stamp = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"rac-{_slug(doc_type)}-{_slug(entity_id)}-{stamp}.pdf"
