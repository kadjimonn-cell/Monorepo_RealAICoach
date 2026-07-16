"""Careers ATS — shared constants.

Single source of truth for Mongo collection names, public-token field
conventions, and shared default policy values used across the Tier 1/2/3
routers. Centralising these avoids the token-field-mismatch class of bug
(e.g. careers_offers persisting `candidate_token` while careers_tier3 queries
`public_token`) that surfaced in iteration_332.

Import from here instead of hard-coding names:

    from routes.careers_common import (
        OFFERS_COL, OFFERS_PUBLIC_TOKEN_FIELDS, offer_public_token_query,
    )
"""
from __future__ import annotations

from typing import Any

# ── Mongo collection names ──────────────────────────────────────────────────
APPS_COL = "careers_applications"
OFFERS_COL = "careers_offers"
GDPR_AUDIT_COL = "careers_gdpr_audit"
GDPR_POLICY_COL = "careers_gdpr_policy"
GDPR_POLICY_KEY = "default"
COMPLIANCE_DIGEST_FEED_COL = "compliance_digest_feed"


# ── Public-token field aliases ──────────────────────────────────────────────
# `careers_offers.py` persists new offers with `candidate_token` after /send.
# `careers_tier3.py` historically queried `public_token`. Both are valid
# lookup keys — always query via `offer_public_token_query(token)` so any
# future refactor picks up both aliases automatically.
OFFERS_PUBLIC_TOKEN_FIELDS: tuple[str, ...] = ("candidate_token", "public_token")


def offer_public_token_query(token: str) -> dict[str, Any]:
    """Build a Mongo query that matches either canonical public-token field
    for an offer. Use everywhere a public candidate-facing token is looked
    up on the offers collection."""
    return {"$or": [{field: token} for field in OFFERS_PUBLIC_TOKEN_FIELDS]}


__all__ = [
    "APPS_COL",
    "OFFERS_COL",
    "GDPR_AUDIT_COL",
    "GDPR_POLICY_COL",
    "GDPR_POLICY_KEY",
    "COMPLIANCE_DIGEST_FEED_COL",
    "OFFERS_PUBLIC_TOKEN_FIELDS",
    "offer_public_token_query",
]
