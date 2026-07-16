"""
Feature 2 (Personal AI Assistant) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 2 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 2 route code.
"""

from pathlib import Path


def test_feature2_personal_assistant_has_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/personal_assistant.py").read_text(encoding="utf-8")

    disallowed_sender_markers = [
        "send_catalog_template(",
        "send_email(",
        "https://api.resend.com/emails",
        "from utils.email_service import send_catalog_template",
        "from utils.email_service import send_email",
    ]

    for marker in disallowed_sender_markers:
        assert marker not in source, f"Feature 2 should not own outbound sender call marker: {marker}"
