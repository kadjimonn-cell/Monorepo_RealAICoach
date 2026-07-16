from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TEST_BUNDLE = [
    "/app/backend/tests/test_issue4_realtime_sync_contract.py",
    "/app/backend/tests/test_issue6_realtime_resilience_contract.py",
    "/app/backend/tests/test_issue7_hydration_state_resilience_contract.py",
    "/app/backend/tests/test_issue9_scaling_guardrails_contract.py",
    "/app/backend/tests/test_issue10_dependency_conflict_alignment_contract.py",
    "/app/backend/tests/test_issue10_dependency_drift_guardrails.py",
]


def test_issue9_foundation_bundle_runs_clean_in_single_cycle() -> None:
    for path in TEST_BUNDLE:
        assert Path(path).exists(), f"Missing required foundation guardrail file: {path}"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TEST_BUNDLE],
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, (
        "Critical foundation bundle (Issues 4/6/7/9/10) must stay green together.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
