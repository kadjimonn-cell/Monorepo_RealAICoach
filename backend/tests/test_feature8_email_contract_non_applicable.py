"""
Feature 8 (Fitness Planner Pro) - Email Contract Applicability Test

Purpose:
- Prove whether Feature 8 owns any outbound email path.
- Locked protocol result should justify Email Template Contract (v7)
  as non-applicable when no outbound sender calls exist in Feature 8 route code.
"""

from pathlib import Path


def test_feature8_fitness_routes_have_no_outbound_email_sender_calls():
    route_files = [
        Path("/app/backend/routes/fitness_planner.py"),
        Path("/app/backend/routes/fitness.py"),
    ]

    disallowed_sender_markers = [
        "send_catalog_template(",
        "send_template_email(",
        "send_email(",
        "https://api.resend.com/emails",
        "from utils.email_service import send_catalog_template",
        "from utils.email_service import send_template_email",
        "from utils.email_service import send_email",
    ]

    for route_path in route_files:
        source = route_path.read_text(encoding="utf-8")
        for marker in disallowed_sender_markers:
            assert marker not in source, f"Feature 8 route {route_path.name} should not own outbound sender call marker: {marker}"
