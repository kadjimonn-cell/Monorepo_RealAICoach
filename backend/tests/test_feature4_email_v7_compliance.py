"""
Feature 4 (Workflow Builder) - Email v7 Compliance Test

Purpose:
- Prove Feature 4 outbound email action routes through centralized v7 email service.
- Prevent regressions to direct raw Resend HTTP calls inside workflow_builder route.
"""

from pathlib import Path


def test_feature4_send_email_action_uses_centralized_v7_service():
    source = Path("/app/backend/routes/workflow_builder.py").read_text(encoding="utf-8")

    assert "async def _execute_send_email" in source
    assert "from utils.email_service import send_template_email" in source
    assert "send_template_email(" in source
    assert "template_key = str(config.get(\"template_key\") or \"workflow_builder_send_email_action_v7\")" in source


def test_feature4_send_email_action_has_no_direct_resend_http_call():
    source = Path("/app/backend/routes/workflow_builder.py").read_text(encoding="utf-8")
    start = source.find("async def _execute_send_email")
    assert start != -1, "_execute_send_email function not found"
    tail = source[start:]
    next_def = tail.find("\n\nasync def ", 1)
    fn_source = tail if next_def == -1 else tail[:next_def]

    disallowed_markers = [
        "https://api.resend.com/emails",
        "Authorization\": f\"Bearer {resend_key}\"",
    ]

    for marker in disallowed_markers:
        assert marker not in fn_source, f"Feature 4 send_email should not directly call Resend marker: {marker}"
