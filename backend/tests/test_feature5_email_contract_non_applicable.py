"""
Feature 5 (Decision Coach) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 5 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 5 route code.
"""

from pathlib import Path


def test_feature5_decision_coach_has_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/decision_coach.py").read_text(encoding="utf-8")

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
        assert marker not in source, f"Feature 5 should not own outbound sender call marker: {marker}"
