#!/usr/bin/env python3
"""Architecture Mode hard gate.

Blocks merge/deploy when modular architecture requirements fail:
- module manifest + contracts + deployment specs present
- gateway path mapping present for communications pilot
- architecture test suite pass
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path("/app/backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.architecture_mode import validate_architecture_mode_assets

ARCH_TESTS = [
    "tests/test_architecture_mode_module_apps.py",
    "tests/test_architecture_mode_contracts.py",
    "tests/test_architecture_mode_deployment_specs.py",
    "tests/test_architecture_mode_openapi_contract_alignment.py",
    "tests/test_architecture_mode_gateway_mapping.py",
]


def run_pytest_suite() -> dict:
    existing_tests = [t for t in ARCH_TESTS if (BACKEND_DIR / t).exists()]
    if not existing_tests:
        return {
            "passed": True,
            "returncode": 0,
            "stdout": "No architecture suite files found; skipping.",
            "stderr": "",
        }
    cmd = ["python", "-m", "pytest", "-q", *existing_tests]
    env = {**dict(**__import__("os").environ), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True, env=env)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "suite": existing_tests,
    }


def run_ops_template_key_lint() -> dict:
    cmd = ["python", "backend/scripts/ops_template_key_lint.py"]
    result = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def run_id_checker_wording_guard() -> dict:
    cmd = ["python", "backend/scripts/id_checker_wording_guard.py"]
    result = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def run_translation_semantic_qa() -> dict:
    cmd = ["python", "backend/scripts/translation_semantic_qa.py"]
    result = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def run_pdf_v15_logo_tile_guard() -> dict:
    cmd = ["python", "backend/scripts/pdf_v15_logo_tile_guard.py"]
    result = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def run_nav_key_lock_guard() -> dict:
    cmd = ["python", "backend/scripts/nav_key_lock_guard.py", "--strict-governance"]
    result = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def main():
    output_json = "--json" in sys.argv
    architecture = validate_architecture_mode_assets()
    tests = run_pytest_suite()
    ops_lint = run_ops_template_key_lint()
    wording_guard = run_id_checker_wording_guard()
    translation_qa = run_translation_semantic_qa()
    pdf_logo_guard = run_pdf_v15_logo_tile_guard()
    nav_key_lock_guard = run_nav_key_lock_guard()

    passed = (
        architecture.get("overall_status") == "PASS"
        and tests.get("passed")
        and ops_lint.get("passed")
        and wording_guard.get("passed")
        and translation_qa.get("passed")
        and pdf_logo_guard.get("passed")
        and nav_key_lock_guard.get("passed")
    )
    payload = {
        "architecture": architecture,
        "tests": {
            "suite": tests.get("suite") or ARCH_TESTS,
            **tests,
        },
        "ops_template_key_lint": ops_lint,
        "id_checker_wording_guard": wording_guard,
        "translation_semantic_qa": translation_qa,
        "pdf_v15_logo_tile_guard": pdf_logo_guard,
        "nav_key_lock_guard": nav_key_lock_guard,
        "passed": passed,
    }

    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        print("=" * 56)
        print("Architecture Mode Hard Gate")
        print("=" * 56)
        print(f"Architecture status: {architecture.get('overall_status')}")
        print(f"Architecture tests: {'PASS' if tests.get('passed') else 'FAIL'}")
        print(f"Ops template-key lint: {'PASS' if ops_lint.get('passed') else 'FAIL'}")
        print(f"ID Checker wording guard: {'PASS' if wording_guard.get('passed') else 'FAIL'}")
        print(f"Translation semantic QA: {'PASS' if translation_qa.get('passed') else 'FAIL'}")
        print(f"PDF v15 logo-tile guard: {'PASS' if pdf_logo_guard.get('passed') else 'FAIL'}")
        print(f"Nav key lock metadata guard: {'PASS' if nav_key_lock_guard.get('passed') else 'FAIL'}")
        if not tests.get("passed"):
            print("\n--- pytest stdout ---")
            print(tests.get("stdout") or "")
            print("\n--- pytest stderr ---")
            print(tests.get("stderr") or "")
        if not ops_lint.get("passed"):
            print("\n--- ops lint stdout ---")
            print(ops_lint.get("stdout") or "")
            print("\n--- ops lint stderr ---")
            print(ops_lint.get("stderr") or "")
        if not wording_guard.get("passed"):
            print("\n--- wording guard stdout ---")
            print(wording_guard.get("stdout") or "")
            print("\n--- wording guard stderr ---")
            print(wording_guard.get("stderr") or "")
        if not translation_qa.get("passed"):
            print("\n--- translation semantic QA stdout ---")
            print(translation_qa.get("stdout") or "")
            print("\n--- translation semantic QA stderr ---")
            print(translation_qa.get("stderr") or "")
        if not pdf_logo_guard.get("passed"):
            print("\n--- PDF v15 logo-tile guard stdout ---")
            print(pdf_logo_guard.get("stdout") or "")
            print("\n--- PDF v15 logo-tile guard stderr ---")
            print(pdf_logo_guard.get("stderr") or "")
        if not nav_key_lock_guard.get("passed"):
            print("\n--- Nav key lock metadata guard stdout ---")
            print(nav_key_lock_guard.get("stdout") or "")
            print("\n--- Nav key lock metadata guard stderr ---")
            print(nav_key_lock_guard.get("stderr") or "")
        print("=" * 56)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
