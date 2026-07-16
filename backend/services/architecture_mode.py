import json
from pathlib import Path
from typing import Dict, List


ROOT = Path("/app")
MANIFEST_PATH = ROOT / "backend/architecture/modules_manifest.json"
COMMUNICATIONS_GATEWAY_MAP = ROOT / "backend/deploy/gateway/communications_pilot_ingress.yaml"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_modules_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"mode": "ARCHITECTURE_MODE", "version": "v1", "modules": []}
    return _load_json(MANIFEST_PATH)


def validate_architecture_mode_assets() -> dict:
    manifest = load_modules_manifest()
    modules = manifest.get("modules", [])
    results: List[Dict] = []

    for module in modules:
        contracts_file = ROOT / str(module.get("contracts_file", ""))
        deployment_manifest = ROOT / str(module.get("deployment_manifest", ""))
        test_files = [ROOT / str(path) for path in module.get("test_files", [])]

        contracts_ok = contracts_file.exists()
        deployment_ok = deployment_manifest.exists()
        tests_ok = bool(test_files) and all(path.exists() for path in test_files)

        endpoint_count = 0
        contract_errors: List[str] = []
        if contracts_ok:
            try:
                contract_payload = _load_json(contracts_file)
                endpoints = contract_payload.get("endpoints", [])
                endpoint_count = len(endpoints)
                if endpoint_count == 0:
                    contract_errors.append("contract_has_no_endpoints")
                for idx, endpoint in enumerate(endpoints):
                    if not endpoint.get("path"):
                        contract_errors.append(f"missing_path_at_{idx}")
                    if not endpoint.get("method"):
                        contract_errors.append(f"missing_method_at_{idx}")
            except Exception as exc:
                contract_errors.append(f"contract_parse_error:{str(exc)[:120]}")

        status = "PASS" if contracts_ok and deployment_ok and tests_ok and not contract_errors else "FAIL"
        results.append(
            {
                "module_id": module.get("id"),
                "status": status,
                "checks": {
                    "contracts_file": contracts_ok,
                    "deployment_manifest": deployment_ok,
                    "independent_tests": tests_ok,
                    "contract_endpoint_count": endpoint_count,
                },
                "errors": contract_errors,
            }
        )

    pass_count = sum(1 for row in results if row.get("status") == "PASS")
    gateway_mapping = {
        "communications_pilot": {
            "path": str(COMMUNICATIONS_GATEWAY_MAP).replace("/app/", ""),
            "exists": COMMUNICATIONS_GATEWAY_MAP.exists(),
            "path_mapping_verified": False,
        }
    }
    if COMMUNICATIONS_GATEWAY_MAP.exists():
        text = COMMUNICATIONS_GATEWAY_MAP.read_text(encoding="utf-8")
        gateway_mapping["communications_pilot"]["path_mapping_verified"] = (
            "/api/email-notifications" in text and "communications-service" in text
        )

    overall_pass = pass_count == len(results) and gateway_mapping["communications_pilot"]["path_mapping_verified"]
    return {
        "mode": manifest.get("mode", "ARCHITECTURE_MODE"),
        "version": manifest.get("version", "v1"),
        "overall_status": "PASS" if overall_pass else "FAIL",
        "summary": {
            "total_modules": len(results),
            "pass_modules": pass_count,
            "fail_modules": len(results) - pass_count,
        },
        "modules": results,
        "gateway_path_mapping": gateway_mapping,
    }
