"""
Feature 13 (Mobility Assistant / Smart Cars) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 13 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 13 route code.
"""

from pathlib import Path


def test_feature13_mobility_assistant_block_has_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/ai_services.py").read_text(encoding="utf-8")

    # Feature 13 maps to Mobility Assistant (smart-cars) via AutoGenie endpoint block
    start = source.find("# ── AutoGenie ──")
    assert start != -1, "AutoGenie section not found in ai_services.py"
    tail = source[start:]
    next_section = tail.find("# ── DisasterGuard ──")
    block = tail if next_section == -1 else tail[:next_section]

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
        assert marker not in block, f"Feature 13 AutoGenie block should not own outbound sender call marker: {marker}"
