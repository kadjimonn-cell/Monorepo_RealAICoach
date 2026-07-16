"""
Feature 23 (Travel Visa) - Email v7 Compliance

Purpose:
- Prove Feature 23 has owned outbound email path.
- Prove outbound paths use centralized v7 sender with explicit template_key.
"""

from pathlib import Path


def test_feature23_route_group_uses_v7_sender_path_without_raw_resend_dispatch():
    source = Path("/app/backend/routes/travel_visa_ext.py").read_text(encoding="utf-8")

    assert "async def _send_email(" in source
    assert "from utils.email_service import send_template_email" in source
    assert "result = await send_template_email(" in source
    assert "template_key = _resolve_feature23_template_key(email_type)" in source
    assert "resend.Emails.send" not in source


def test_feature23_notification_helper_delegates_to_v7_sender_with_template_mapping():
    source = Path("/app/backend/routes/travel_visa_ext.py").read_text(encoding="utf-8")

    assert "async def send_notification_email(" in source
    assert "return await _send_email(db, user[\"email\"], subject, body_html, email_type)" in source
    assert "TV_EMAIL_TEMPLATE_MAP" in source
    assert "_resolve_feature23_template_key" in source


def test_feature23_checkpoint_email_contract_is_explicit_pass_with_evidence():
    c_text = Path("/app/memory/FEATURE_23_CHECKPOINT_C_IMPLEMENTATION.md").read_text(encoding="utf-8")
    d_text = Path("/app/memory/FEATURE_23_CHECKPOINT_D_EVIDENCE.md").read_text(encoding="utf-8")

    assert "**Email Template Contract (v7): PASS**" in c_text
    assert "**Email Template Contract (v7): PASS**" in d_text
    assert "## Email Contract Applicability Evidence" in c_text
    assert "## Email Contract Applicability Evidence" in d_text

    required_refs = [
        "/app/backend/routes/travel_visa_ext.py",
        "/app/backend/tests/test_feature23_travel_visa.py",
        "/app/backend/tests/test_feature23_email_v7_contract_gap.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 23 Checkpoint C missing evidence reference: {ref}"
        assert ref in d_text, f"Feature 23 Checkpoint D missing evidence reference: {ref}"
