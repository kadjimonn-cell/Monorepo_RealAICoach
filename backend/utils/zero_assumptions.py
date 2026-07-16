"""Zero-Assumptions Policy — shared runtime enforcement helpers.

Single source of truth for the forbidden fabricated-identity tokens and the
runtime assertion / scan helpers. All PDF generators (offers, receipts,
invoices, certificates) and the email transport layer import from here so
that any future regression (fabricated branding slipping into a payment PDF,
certificate signer, or transactional email) is blocked at send-time — not
after the fact.

Rule source: /app/memory/ZERO_ASSUMPTIONS_POLICY.md
Rule: "Never fabricate, guess, infer, or placeholder any data that represents
       a real business identity. Load from verified source-of-truth locations
       only."

CI guard: /app/backend/tests/test_zero_assumptions_guard.py scans the entire
backend for these tokens AND extends into email templates + receipt/
certificate generator files so no future agent (or LLM-drafted template) can
re-introduce a placeholder.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# ── Canonical forbidden-token list ──────────────────────────────────────────
# Any extension MUST also be appended to /app/memory/ZERO_ASSUMPTIONS_POLICY.md
# — the CI test parameterises over FORBIDDEN_TOKENS and asserts each one is
# documented in the policy markdown.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "Samir Patel",
    "2261 Market Street",
    "2261 Market St,",
    "San Francisco, CA 94114",
    "RealAICoach, Inc.",  # real entity is "RealAICoach LLC" — note the comma
)


class FabricatedDataViolation(Exception):
    """Raised the instant a fabricated business-identity token is detected
    in a branding dict, outbound email, PDF render context, or certificate
    signer block. NEVER silently swallow — this is a hard compliance failure.
    """


def _coerce_to_blob(payload: Any) -> str:
    """Flatten any dict / list / tuple / str / bytes into a single scannable
    string. None-valued dict fields are skipped. Byte strings are decoded
    best-effort (replace-on-error) so we can also scan raw PDF bytes."""
    if payload is None:
        return ""
    if isinstance(payload, (bytes, bytearray)):
        try:
            return bytes(payload).decode("utf-8", errors="replace")
        except Exception:
            return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " \u0000 ".join(
            _coerce_to_blob(v) for v in payload.values() if v is not None
        )
    if isinstance(payload, (list, tuple, set)):
        return " \u0000 ".join(_coerce_to_blob(v) for v in payload if v is not None)
    return str(payload)


def scan_for_fabrications(
    payload: Any, *, extra_tokens: Iterable[str] = ()
) -> list[str]:
    """Return a list of forbidden tokens found inside `payload`. Empty list
    means clean. `extra_tokens` lets a call-site add stricter ad-hoc checks
    (e.g. a user-configurable deny-list) without mutating the global list."""
    blob = _coerce_to_blob(payload)
    all_tokens = tuple(FORBIDDEN_TOKENS) + tuple(extra_tokens)
    return [t for t in all_tokens if t and t in blob]


def assert_no_fabrication(
    payload: Any,
    *,
    context: str,
    extra_tokens: Iterable[str] = (),
) -> None:
    """Hard-block variant. Raises FabricatedDataViolation on first hit.

    `context` is a short label included in the exception + log line
    (e.g. "receipt_pdf", "certificate_signer", "outbound_email").
    """
    hits = scan_for_fabrications(payload, extra_tokens=extra_tokens)
    if hits:
        logger.error(
            "[ZERO-ASSUMPTIONS] Fabricated tokens detected in %s: %s. "
            "Refusing to proceed. See /app/memory/ZERO_ASSUMPTIONS_POLICY.md.",
            context,
            hits,
        )
        raise FabricatedDataViolation(
            f"[{context}] Fabricated business-identity tokens detected: {hits}. "
            "Policy: /app/memory/ZERO_ASSUMPTIONS_POLICY.md"
        )


__all__ = [
    "FORBIDDEN_TOKENS",
    "FabricatedDataViolation",
    "scan_for_fabrications",
    "assert_no_fabrication",
]
