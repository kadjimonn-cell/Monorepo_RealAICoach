#!/usr/bin/env python3
"""Orchestrator Agent: runs validator/testing/performance agents with auto-repair loops."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


CONFIG_PATH = Path("/app/scripts/ai_factory/factory_config.json")
REPORT_PATH = Path("/app/test_reports/ai_factory_orchestrator_report.json")
VALIDATOR_REPORT = Path("/app/test_reports/ai_factory_validator_report.json")
PERFORMANCE_REPORT = Path("/app/test_reports/ai_factory_performance_report.json")


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_command(command: List[str], env_overrides: Dict[str, str] | None = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    start = time.time()
    result = subprocess.run(command, cwd="/app", capture_output=True, text=True, env=env, check=False)
    duration = round(time.time() - start, 2)
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "duration_seconds": duration,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def _build_step_command(step: Dict[str, Any], args: argparse.Namespace) -> List[str]:
    command = list(step["command"])
    if step["id"] == "validator-runtime":
        command.extend(
            [
                "--base-url",
                args.api_base_url,
                "--admin-email",
                args.admin_email,
                "--admin-password",
                args.admin_password,
            ]
        )
    if step["id"] == "performance-lighthouse":
        command.extend(
            [
                "--url",
                args.performance_base_url,
                "--min-performance",
                str(args.min_performance),
                "--max-fcp-ms",
                str(args.max_fcp_ms),
                "--max-lcp-ms",
                str(args.max_lcp_ms),
            ]
        )
    return command


def _run_once(steps: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for step in steps:
        command = _build_step_command(step, args)
        outcome = _run_command(command, step.get("env"))
        results.append(
            {
                "step_id": step["id"],
                "agent": step["agent"],
                "command": command,
                **outcome,
            }
        )
    return results


def _apply_fixer(last_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [result["step_id"] for result in last_results if result["status"] == "FAIL"]
    return {
        "agent": "fixer",
        "status": "APPLIED" if failed else "SKIPPED",
        "action": "retry_failed_steps",
        "failed_steps": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AI software factory orchestrator")
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--performance-base-url", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--min-performance", type=float, default=90.0)
    parser.add_argument("--max-fcp-ms", type=float, default=2000.0)
    parser.add_argument("--max-lcp-ms", type=float, default=2500.0)
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    steps = config.get("steps", [])
    max_loops = int(config.get("max_repair_loops", 1))

    history: List[Dict[str, Any]] = []
    final_results: List[Dict[str, Any]] = []
    status = "FAIL"
    confidence = "LOW"

    for loop in range(max_loops + 1):
        run_results = _run_once(steps, args)
        loop_summary = {
            "loop": loop,
            "results": run_results,
            "fixer": _apply_fixer(run_results),
        }
        history.append(loop_summary)

        failed = [result for result in run_results if result["status"] == "FAIL"]
        final_results = run_results
        if not failed:
            validator_report = _safe_read_json(VALIDATOR_REPORT)
            performance_report = _safe_read_json(PERFORMANCE_REPORT)
            validator_conf = str(validator_report.get("confidence") or "LOW").upper()
            performance_conf = str(performance_report.get("confidence") or "LOW").upper()

            confidence = "HIGH" if (validator_conf == "HIGH" and performance_conf == "HIGH") else "MEDIUM"
            status = "PASS" if confidence == "HIGH" else "FAIL"
            break

        if loop < max_loops:
            time.sleep(1)

    report = {
        "agent": "orchestrator",
        "status": status,
        "confidence": confidence,
        "hard_completion_rule": {
            "rule": "IF CONFIDENCE != HIGH => AUTOMATIC FAIL => CONTINUE ITERATION",
            "triggered": confidence != "HIGH",
        },
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "max_repair_loops": max_loops,
        "confidence_sources": {
            "validator_report": str(VALIDATOR_REPORT),
            "performance_report": str(PERFORMANCE_REPORT),
            "validator_confidence": (_safe_read_json(VALIDATOR_REPORT).get("confidence") or "LOW"),
            "performance_confidence": (_safe_read_json(PERFORMANCE_REPORT).get("confidence") or "LOW"),
        },
        "history": history,
        "final_results": final_results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())