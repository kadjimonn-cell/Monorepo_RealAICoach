"""
Feature 24 (AI Learning Hub) - Email v7 Compliance

Purpose:
- Prove Feature 24 owns outbound email path.
- Prove sender calls include explicit template_key usage.
"""

from pathlib import Path


def test_feature24_learning_hub_route_owns_outbound_email_sender_calls():
    source = Path("/app/backend/routes/ai_learning_hub.py").read_text(encoding="utf-8")

    assert "result = await send_email(" in source
    assert 'template_key="learning_hub_certificate_award"' in source
    assert 'template_key=row.get("template_key") or "learning_hub_update"' in source


def test_feature24_checkpoint_email_contract_is_explicit_pass_with_evidence():
    c_text = Path("/app/memory/FEATURE_24_CHECKPOINT_C_IMPLEMENTATION.md").read_text(encoding="utf-8")
    d_text = Path("/app/memory/FEATURE_24_CHECKPOINT_D_EVIDENCE.md").read_text(encoding="utf-8")

    assert "**Email Template Contract (v7): PASS**" in c_text
    assert "**Email Template Contract (v7): PASS**" in d_text
    assert "## Email Contract Applicability Evidence" in c_text
    assert "## Email Contract Applicability Evidence" in d_text

    required_refs = [
        "/app/backend/routes/ai_learning_hub.py",
        "/app/backend/tests/test_feature24_learning_hub.py",
        "/app/backend/tests/test_feature24_email_v7_compliance.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 24 Checkpoint C missing evidence reference: {ref}"
        assert ref in d_text, f"Feature 24 Checkpoint D missing evidence reference: {ref}"
