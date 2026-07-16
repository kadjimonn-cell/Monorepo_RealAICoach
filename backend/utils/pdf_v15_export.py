"""Shared PDF export helpers.

Global PDF v15 visual policy RETIRED (2026-07, platform owner directive):
this helper is now a validated passthrough — it only guards that call sites
actually produced PDF bytes, and never applies any global overlay or stamp.
"""

from __future__ import annotations


def enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    if not isinstance(payload, (bytes, bytearray)) or not bytes(payload).startswith(b"%PDF-"):
        raise RuntimeError(f"pdf-export-invalid-bytes:{context}")
    return bytes(payload)
