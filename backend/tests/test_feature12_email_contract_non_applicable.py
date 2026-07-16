"""
Feature 12 (Relationship Coach) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 12 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 12 route code.
"""

from pathlib import Path


def test_feature12_relationship_coach_route_has_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/relationship_coach.py").read_text(encoding="utf-8")

    disallowed_sender_markers = [
        "send_catalog_template(",
        "send_template_email(",
        "send_email(",
        "https://api.resend.com/emails",
        "from utils.email_service import send_catalog_template",
        "from utils.email_service import send_template_email",
        "from utils.email_service import send_email",
    ]

    for marker in disallowed_sender_markers:
        assert marker not in source, f"Feature 12 route should not own outbound sender call marker: {marker}"
