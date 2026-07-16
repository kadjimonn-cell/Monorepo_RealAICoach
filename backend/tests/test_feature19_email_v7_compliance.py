"""
Feature 19 Bill Generator Email V7 Compliance Tests
Tests:
- Static source verification for v7 sender path + explicit template_key
- Endpoint surface verification for reminder dispatch paths
- Checkpoint C/D explicit contract wording verification
"""

from pathlib import Path


def test_feature19_route_uses_catalog_template_sender():
    source = Path("/app/backend/routes/bill_generator.py").read_text(encoding="utf-8")

    assert "from utils.email_service import send_catalog_template, is_email_configured" in source, (
        "Feature 19 should import send_catalog_template and is_email_configured in reminder email path"
    )
    assert "result = await send_catalog_template(" in source, (
        "Feature 19 reminder email flow should call send_catalog_template"
    )
    assert 'template_key="invoice_past_due"' in source, (
        "Feature 19 reminder email flow must enforce explicit v7 template_key=invoice_past_due"
    )


def test_feature19_dispatch_endpoints_reference_owned_email_path():
    source = Path("/app/backend/routes/bill_generator.py").read_text(encoding="utf-8")

    assert "@router.post(\"/reminders/{bill_id}/dispatch\")" in source
    assert "@router.post(\"/collections/bulk-reminders\")" in source
    assert "email_result = await _send_reminder_email(" in source, (
        "Feature 19 dispatch endpoints should route through owned _send_reminder_email helper"
    )


def test_feature19_checkpoint_email_contract_is_explicit_pass_with_evidence():
    c_text = Path("/app/memory/FEATURE_19_CHECKPOINT_C_IMPLEMENTATION.md").read_text(encoding="utf-8")
    d_text = Path("/app/memory/FEATURE_19_CHECKPOINT_D_EVIDENCE.md").read_text(encoding="utf-8")

    assert "**Email Template Contract (v7): PASS**" in c_text
    assert "**Email Template Contract (v7): PASS**" in d_text

    assert "## Email Contract Applicability Evidence" in c_text
    assert "## Email Contract Applicability Evidence" in d_text

    required_refs = [
        "/app/backend/routes/bill_generator.py",
        "/app/backend/tests/test_feature19_bill_generator.py",
        "/app/backend/tests/test_feature19_3tier_final_verification.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 19 Checkpoint C missing evidence reference: {ref}"
        assert ref in d_text, f"Feature 19 Checkpoint D missing evidence reference: {ref}"
