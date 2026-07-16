"""
Feature 11 (Travel Planner Pro / TravelPal) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 11 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 11 route code.
"""

from pathlib import Path


def test_feature11_travelpal_routes_have_no_outbound_email_sender_calls():
    source = Path("/app/backend/routes/ai_services.py").read_text(encoding="utf-8")

    # isolate TravelPal endpoint block for feature-owned assertion
    start = source.find("# ── TravelPal ──")
    assert start != -1, "TravelPal section not found in ai_services.py"
    tail = source[start:]
    next_section = tail.find("# ── GlobeCoach ──")
    travelpal_block = tail if next_section == -1 else tail[:next_section]

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
        assert marker not in travelpal_block, f"Feature 11 TravelPal block should not own outbound sender call marker: {marker}"
