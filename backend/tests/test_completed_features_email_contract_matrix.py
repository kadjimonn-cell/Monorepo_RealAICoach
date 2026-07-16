"""
Consolidated v7 email-contract compliance suite for completed features.

Locked protocol intent:
- Every completed feature must expose explicit Email Template Contract status
  in Checkpoint C and Checkpoint D evidence files.
- Known feature-specific expectations (where issue closures were implemented)
  must remain pinned and regression-safe.
"""

from pathlib import Path
import re


TRACKER_PATH = Path("/app/memory/FEATURES_REBUILD_TRACKER.md")


def _done_feature_numbers() -> list[int]:
    text = TRACKER_PATH.read_text(encoding="utf-8")
    done: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.count("|") > 10):
            continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        if len(parts) < 2:
            continue
        if not parts[0].isdigit():
            continue
        status = parts[-1]
        if status == "Done":
            done.append(int(parts[0]))
    return done


def _extract_email_contract_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"\*\*Email Template Contract \(v7[^)]*\):\s*(.+?)\*\*", text)
    assert match, f"Missing Email Template Contract line in {path}"
    return match.group(1).strip()


def test_done_features_have_email_contract_status_in_checkpoint_d():
    done = _done_feature_numbers()
    assert done, "No completed features found in tracker"

    allowed_prefixes = (
        "PASS",
        "N/A",
        "FAIL",
        "PENDING",
    )

    for feature_number in done:
        path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_D_EVIDENCE.md")
        assert path.exists(), f"Missing Checkpoint D file for completed Feature {feature_number}: {path}"
        status = _extract_email_contract_status(path)
        assert status.upper().startswith(allowed_prefixes), (
            f"Unexpected Email Template Contract status for Feature {feature_number}: '{status}'"
        )


def test_done_features_have_email_contract_status_in_checkpoint_c():
    done = _done_feature_numbers()
    assert done, "No completed features found in tracker"

    for feature_number in done:
        path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_C_IMPLEMENTATION.md")
        assert path.exists(), f"Missing Checkpoint C file for completed Feature {feature_number}: {path}"
        _ = _extract_email_contract_status(path)


def test_features_26_to_36_have_explicit_email_contract_status_in_c_and_d():
    for feature_number in range(26, 37):
        c_path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_C_IMPLEMENTATION.md")
        d_path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_D_EVIDENCE.md")

        assert c_path.exists(), f"Missing Checkpoint C file for Feature {feature_number}"
        assert d_path.exists(), f"Missing Checkpoint D file for Feature {feature_number}"

        c_status = _extract_email_contract_status(c_path)
        d_status = _extract_email_contract_status(d_path)

        assert c_status.upper().startswith(("PENDING", "PASS", "N/A", "FAIL")), (
            f"Feature {feature_number} C email contract status invalid: {c_status}"
        )
        assert d_status.upper().startswith(("PENDING", "PASS", "N/A", "FAIL")), (
            f"Feature {feature_number} D email contract status invalid: {d_status}"
        )


def test_known_feature_email_contract_expectations_remain_pinned():
    expectations = {
        1: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 1 OUTBOUND FLOW)",
        2: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 2 OUTBOUND FLOW)",
        3: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 3 OUTBOUND FLOW)",
        4: "PASS",
        5: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 5 OUTBOUND FLOW)",
        6: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 6 OUTBOUND FLOW)",
        7: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 7 OUTBOUND FLOW)",
        8: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 8 OUTBOUND FLOW)",
        9: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 9 OUTBOUND FLOW)",
        10: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 10 OUTBOUND FLOW)",
        11: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 11 OUTBOUND FLOW)",
        12: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 12 OUTBOUND FLOW)",
        13: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 13 OUTBOUND FLOW)",
        14: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 14 OUTBOUND FLOW)",
        15: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 15 OUTBOUND FLOW)",
        16: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 16 OUTBOUND FLOW)",
        17: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 17 OUTBOUND FLOW)",
        18: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 18 OUTBOUND FLOW)",
        19: "PASS",
        20: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 20 OUTBOUND FLOW)",
        21: "PASS",
        22: "N/A (VALIDATED NON-APPLICABLE FOR FEATURE 22 OUTBOUND FLOW)",
        23: "PASS",
        24: "PASS",
        25: "PASS",
    }

    for feature_number, expected_prefix in expectations.items():
        d_path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_D_EVIDENCE.md")
        c_path = Path(f"/app/memory/FEATURE_{feature_number}_CHECKPOINT_C_IMPLEMENTATION.md")
        assert d_path.exists(), f"Missing D evidence file for Feature {feature_number}"
        assert c_path.exists(), f"Missing C implementation file for Feature {feature_number}"

        d_status = _extract_email_contract_status(d_path)
        c_status = _extract_email_contract_status(c_path)

        assert d_status.startswith(expected_prefix), (
            f"Feature {feature_number} Checkpoint D status mismatch. Expected prefix '{expected_prefix}', got '{d_status}'"
        )
        assert c_status.startswith(expected_prefix), (
            f"Feature {feature_number} Checkpoint C status mismatch. Expected prefix '{expected_prefix}', got '{c_status}'"
        )


def test_feature6_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_6_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_6_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 6 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 6 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/learning_coach.py",
        "/app/backend/tests/test_feature6_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 6 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 6 Checkpoint D missing evidence ref: {ref}"


def test_feature7_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_7_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_7_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 7 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 7 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/health_guide.py",
        "/app/backend/tests/test_feature7_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 7 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 7 Checkpoint D missing evidence ref: {ref}"


def test_feature7_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_7_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_7_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 7 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 7 Checkpoint D regressed to generic N/A wording"


def test_feature8_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_8_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_8_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 8 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 8 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/fitness_planner.py",
        "/app/backend/routes/fitness.py",
        "/app/backend/tests/test_feature8_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 8 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 8 Checkpoint D missing evidence ref: {ref}"


def test_feature8_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_8_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_8_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 8 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 8 Checkpoint D regressed to generic N/A wording"


def test_feature9_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_9_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_9_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 9 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 9 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/money_strategy_hub.py",
        "/app/backend/tests/test_feature9_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 9 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 9 Checkpoint D missing evidence ref: {ref}"


def test_feature9_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_9_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_9_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 9 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 9 Checkpoint D regressed to generic N/A wording"


def test_feature9_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_9_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_9_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/money_strategy_hub.py",
        "/app/backend/tests/test_money_strategy_hub.py",
        "/app/backend/tests/test_money_strategy_hub_deep.py",
        "/app/backend/tests/test_money_strategy_hub_feature9.py",
        "/app/backend/tests/test_feature9_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 9 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 9 Checkpoint D missing required reference: {ref}"


def test_feature9_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_9_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_9_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 9 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 9 Checkpoint D lost applicability section header"


def test_feature10_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_10_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_10_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 10 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 10 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_services.py",
        "/app/backend/tests/test_feature10_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 10 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 10 Checkpoint D missing evidence ref: {ref}"


def test_feature10_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_10_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_10_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 10 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 10 Checkpoint D regressed to generic N/A wording"


def test_feature10_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_10_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_10_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/ai_services.py",
        "/app/backend/tests/test_canonical_feature_order_integrity.py",
        "/app/backend/tests/test_issue8_delayed_integration_contract.py",
        "/app/backend/tests/test_feature10_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 10 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 10 Checkpoint D missing required reference: {ref}"


def test_feature10_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_10_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_10_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 10 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 10 Checkpoint D lost applicability section header"


def test_feature11_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_11_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_11_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 11 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 11 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_services.py",
        "/app/backend/tests/test_feature11_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 11 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 11 Checkpoint D missing evidence ref: {ref}"


def test_feature11_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_11_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_11_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 11 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 11 Checkpoint D regressed to generic N/A wording"


def test_feature12_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_12_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_12_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 12 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 12 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/relationship_coach.py",
        "/app/backend/tests/test_feature12_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 12 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 12 Checkpoint D missing evidence ref: {ref}"


def test_feature12_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_12_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_12_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 12 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 12 Checkpoint D regressed to generic N/A wording"


def test_feature13_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_13_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_13_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 13 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 13 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_services.py",
        "/app/backend/tests/test_feature13_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 13 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 13 Checkpoint D missing evidence ref: {ref}"


def test_feature13_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_13_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_13_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 13 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 13 Checkpoint D regressed to generic N/A wording"


def test_feature13_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_13_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_13_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/ai_services.py",
        "/app/backend/tests/test_mobility_assistant_feature13.py",
        "/app/backend/tests/test_mobility_assistant_deep.py",
        "/app/backend/tests/test_feature13_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 13 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 13 Checkpoint D missing required reference: {ref}"


def test_feature13_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_13_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_13_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 13 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 13 Checkpoint D lost applicability section header"


def test_feature14_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_14_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_14_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 14 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 14 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/real_estate.py",
        "/app/backend/tests/test_feature14_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 14 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 14 Checkpoint D missing evidence ref: {ref}"


def test_feature14_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_14_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_14_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 14 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 14 Checkpoint D regressed to generic N/A wording"


def test_feature15_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_15_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_15_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 15 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 15 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/video_creator_studio.py",
        "/app/backend/tests/test_feature15_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 15 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 15 Checkpoint D missing evidence ref: {ref}"


def test_feature15_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_15_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_15_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 15 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 15 Checkpoint D regressed to generic N/A wording"


def test_feature16_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_16_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_16_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 16 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 16 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_photo_studio.py",
        "/app/backend/tests/test_feature16_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 16 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 16 Checkpoint D missing evidence ref: {ref}"


def test_feature16_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_16_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_16_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 16 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 16 Checkpoint D regressed to generic N/A wording"


def test_feature17_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_17_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_17_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 17 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 17 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_speech_studio.py",
        "/app/backend/tests/test_feature17_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 17 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 17 Checkpoint D missing evidence ref: {ref}"


def test_feature17_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_17_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_17_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 17 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 17 Checkpoint D regressed to generic N/A wording"


def test_feature18_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_18_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_18_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 18 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 18 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_enterprise_copilot.py",
        "/app/backend/tests/test_feature18_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 18 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 18 Checkpoint D missing evidence ref: {ref}"


def test_feature18_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_18_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_18_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 18 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 18 Checkpoint D regressed to generic N/A wording"


def test_feature18_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_18_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_18_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/ai_enterprise_copilot.py",
        "/app/backend/tests/test_ai_enterprise_copilot.py",
        "/app/backend/tests/test_feature18_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 18 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 18 Checkpoint D missing required reference: {ref}"


def test_feature18_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_18_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_18_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 18 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 18 Checkpoint D lost applicability section header"


def test_feature19_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_19_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_19_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 19 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 19 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/bill_generator.py",
        "/app/backend/tests/test_feature19_bill_generator.py",
        "/app/backend/tests/test_feature19_3tier_final_verification.py",
        "/app/backend/tests/test_feature19_email_v7_compliance.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 19 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 19 Checkpoint D missing evidence ref: {ref}"


def test_feature19_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_19_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_19_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 19 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 19 Checkpoint D regressed to generic N/A wording"


def test_feature19_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_19_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_19_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/bill_generator.py",
        "/app/backend/tests/test_feature19_bill_generator.py",
        "/app/backend/tests/test_feature19_3tier_final_verification.py",
        "/app/backend/tests/test_feature19_email_v7_compliance.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 19 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 19 Checkpoint D missing required reference: {ref}"


def test_feature19_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_19_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_19_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 19 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 19 Checkpoint D lost applicability section header"


def test_feature20_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_20_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_20_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 20 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 20 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/word_forge.py",
        "/app/backend/tests/test_feature20_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 20 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 20 Checkpoint D missing evidence ref: {ref}"


def test_feature20_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_20_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_20_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 20 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 20 Checkpoint D regressed to generic N/A wording"


def test_feature20_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_20_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_20_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/word_forge.py",
        "/app/backend/tests/test_feature20_lexicon_intelligence.py",
        "/app/backend/tests/test_lexicon_intelligence_feature20.py",
        "/app/backend/tests/test_feature20_3tier_entitlement.py",
        "/app/backend/tests/test_feature20_3tier_verification.py",
        "/app/backend/tests/test_feature20_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 20 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 20 Checkpoint D missing required reference: {ref}"


def test_feature20_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_20_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_20_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 20 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 20 Checkpoint D lost applicability section header"


def test_feature21_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_21_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_21_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 21 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 21 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/watch_videos.py",
        "/app/backend/utils/email_notifications.py",
        "/app/backend/utils/email_service.py",
        "/app/backend/tests/test_feature21_email_v7_compliance.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 21 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 21 Checkpoint D missing evidence ref: {ref}"


def test_feature21_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_21_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_21_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 21 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 21 Checkpoint D regressed to generic N/A wording"


def test_feature21_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_21_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_21_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/watch_videos.py",
        "/app/backend/utils/email_notifications.py",
        "/app/backend/utils/email_service.py",
        "/app/backend/tests/test_feature21_entitlement.py",
        "/app/backend/tests/test_watch_videos_feature21_contract.py",
        "/app/backend/tests/test_feature21_email_v7_compliance.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 21 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 21 Checkpoint D missing required reference: {ref}"


def test_feature21_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_21_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_21_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 21 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 21 Checkpoint D lost applicability section header"


def test_feature22_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_22_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_22_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 22 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 22 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/games_station.py",
        "/app/backend/tests/test_feature22_email_contract_non_applicable.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 22 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 22 Checkpoint D missing evidence ref: {ref}"


def test_feature22_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_22_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_22_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 22 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 22 Checkpoint D regressed to generic N/A wording"


def test_feature22_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_22_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_22_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/games_station.py",
        "/app/backend/tests/test_feature22_games_station.py",
        "/app/backend/tests/test_feature22_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 22 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 22 Checkpoint D missing required reference: {ref}"


def test_feature22_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_22_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_22_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 22 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 22 Checkpoint D lost applicability section header"


def test_feature23_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_23_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_23_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 23 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 23 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/travel_visa_ext.py",
        "/app/backend/tests/test_feature23_email_v7_contract_gap.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 23 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 23 Checkpoint D missing evidence ref: {ref}"


def test_feature23_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_23_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_23_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 23 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 23 Checkpoint D regressed to generic N/A wording"


def test_feature23_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_23_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_23_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/travel_visa_ext.py",
        "/app/backend/tests/test_feature23_travel_visa.py",
        "/app/backend/tests/test_feature23_email_v7_contract_gap.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 23 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 23 Checkpoint D missing required reference: {ref}"


def test_feature23_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_23_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_23_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 23 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 23 Checkpoint D lost applicability section header"


def test_feature24_applicability_evidence_sections_exist_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_24_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_24_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    assert "## Email Contract Applicability Evidence" in c_text, "Feature 24 Checkpoint C missing applicability evidence section"
    assert "## Email Contract Applicability Evidence" in d_text, "Feature 24 Checkpoint D missing applicability evidence section"

    expected_refs = [
        "/app/backend/routes/ai_learning_hub.py",
        "/app/backend/tests/test_feature24_email_v7_compliance.py",
    ]

    for ref in expected_refs:
        assert ref in c_text, f"Feature 24 Checkpoint C missing evidence ref: {ref}"
        assert ref in d_text, f"Feature 24 Checkpoint D missing evidence ref: {ref}"


def test_feature24_contract_wording_does_not_regress_to_generic_na():
    c_path = Path("/app/memory/FEATURE_24_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_24_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    generic_phrase = "N/A / NOT EXPLICITLY VERIFIED IN THIS FILE"
    assert generic_phrase not in c_text, "Feature 24 Checkpoint C regressed to generic N/A wording"
    assert generic_phrase not in d_text, "Feature 24 Checkpoint D regressed to generic N/A wording"


def test_feature24_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_24_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_24_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/ai_learning_hub.py",
        "/app/backend/tests/test_feature24_learning_hub.py",
        "/app/backend/tests/test_feature24_email_v7_compliance.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 24 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 24 Checkpoint D missing required reference: {ref}"


def test_feature24_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_24_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_24_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 24 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 24 Checkpoint D lost applicability section header"


def test_feature16_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_16_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_16_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/ai_photo_studio.py",
        "/app/backend/tests/test_ai_photo_studio.py",
        "/app/backend/tests/test_feature16_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 16 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 16 Checkpoint D missing required reference: {ref}"


def test_feature16_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_16_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_16_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 16 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 16 Checkpoint D lost applicability section header"


def test_feature14_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_14_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_14_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/real_estate.py",
        "/app/backend/tests/test_real_estate_feature14.py",
        "/app/backend/tests/test_feature14_auth_fix.py",
        "/app/backend/tests/test_feature14_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 14 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 14 Checkpoint D missing required reference: {ref}"


def test_feature14_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_14_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_14_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 14 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 14 Checkpoint D lost applicability section header"


def test_feature15_required_reference_completeness_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_15_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_15_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    required_refs = [
        "/app/backend/routes/video_creator_studio.py",
        "/app/backend/tests/test_feature15_video_creator_studio.py",
        "/app/backend/tests/test_feature15_email_contract_non_applicable.py",
    ]

    for ref in required_refs:
        assert ref in c_text, f"Feature 15 Checkpoint C missing required reference: {ref}"
        assert ref in d_text, f"Feature 15 Checkpoint D missing required reference: {ref}"


def test_feature15_applicability_section_header_persists_in_c_and_d():
    c_path = Path("/app/memory/FEATURE_15_CHECKPOINT_C_IMPLEMENTATION.md")
    d_path = Path("/app/memory/FEATURE_15_CHECKPOINT_D_EVIDENCE.md")

    c_text = c_path.read_text(encoding="utf-8")
    d_text = d_path.read_text(encoding="utf-8")

    header = "## Email Contract Applicability Evidence"
    assert header in c_text, "Feature 15 Checkpoint C lost applicability section header"
    assert header in d_text, "Feature 15 Checkpoint D lost applicability section header"
