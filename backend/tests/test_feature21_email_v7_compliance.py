"""
Feature 21 (Watch Videos) - Email Contract (v7) Compliance Test

Purpose:
- Prove that Feature 21 owned outbound email flow exists.
- Prove dispatch path goes through centralized sender with explicit template-key tagging.
"""

from pathlib import Path


def test_feature21_watch_videos_route_owns_outbound_email_dispatch_path():
    source = Path("/app/backend/routes/watch_videos.py").read_text(encoding="utf-8")

    assert "async def _send_new_video_emails(" in source
    assert "result = await notify.reminder(" in source
    assert "email_summary = await _send_new_video_emails(users, inserted_docs)" in source


def test_feature21_dispatch_path_enforces_template_key_sender_path():
    notifications_source = Path("/app/backend/utils/email_notifications.py").read_text(encoding="utf-8")

    assert "return await _send_and_log(user_id, email, \"reminder\", subject, html, name)" in notifications_source, (
        "Feature 21 reminder dispatch should route through _send_and_log with explicit email_type='reminder'"
    )
    assert "template_key=email_type" in notifications_source, (
        "Central reminder notify path must pass explicit template_key=email_type into send_email transport path"
    )


def test_feature21_checkpoint_contract_is_explicit_pass_with_evidence():
    c_text = Path("/app/memory/FEATURE_21_CHECKPOINT_C_IMPLEMENTATION.md").read_text(encoding="utf-8")
    d_text = Path("/app/memory/FEATURE_21_CHECKPOINT_D_EVIDENCE.md").read_text(encoding="utf-8")

    assert "**Email Template Contract (v7): PASS**" in c_text
    assert "**Email Template Contract (v7): PASS**" in d_text
    assert "## Email Contract Applicability Evidence" in c_text
    assert "## Email Contract Applicability Evidence" in d_text

    required_refs = [
        "/app/backend/routes/watch_videos.py",
        "/app/backend/utils/email_notifications.py",
        "/app/backend/utils/email_service.py",
        "/app/backend/tests/test_feature21_entitlement.py",
        "/app/backend/tests/test_watch_videos_feature21_contract.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 21 Checkpoint C missing evidence reference: {ref}"
        assert ref in d_text, f"Feature 21 Checkpoint D missing evidence reference: {ref}"
