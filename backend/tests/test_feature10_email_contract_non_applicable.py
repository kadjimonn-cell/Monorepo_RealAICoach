"""
Feature 10 (Smart Shopping Advisor / SmartBuy) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 10 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 10 route code.
"""

from pathlib import Path


def test_feature10_smartbuy_route_has_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/ai_services.py").read_text(encoding="utf-8")

    # isolate SmartBuy endpoint block for feature-owned assertion
    start = source.find("# ── SmartBuy ──")
    assert start != -1, "SmartBuy section not found in ai_services.py"
    tail = source[start:]
    next_section = tail.find("# ── HomeMate ──")
    smartbuy_block = tail if next_section == -1 else tail[:next_section]

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
        assert marker not in smartbuy_block, f"Feature 10 SmartBuy block should not own outbound sender call marker: {marker}"
