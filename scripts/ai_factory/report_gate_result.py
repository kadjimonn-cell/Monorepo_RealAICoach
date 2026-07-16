#!/usr/bin/env python3
"""Report orchestrator gate result to the Factory Gate Health API."""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    import urllib.request
    import urllib.error

    class _FallbackRequests:
        """Minimal requests-like interface using urllib."""
        @staticmethod
        def post(url, json=None, headers=None, timeout=15):
            data = json.dumps(json).encode() if json else None
            req = urllib.request.Request(url, data=data, headers={**(headers or {}), "Content-Type": "application/json"})
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                return type("R", (), {"status_code": resp.status, "json": lambda: json.loads(resp.read())})()
            except urllib.error.HTTPError as e:
                return type("R", (), {"status_code": e.code, "json": lambda: {}})()

    requests = _FallbackRequests()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--pipeline", default="ai-software-factory")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--report-path", default="test_reports/ai_factory_orchestrator_report.json")
    args = parser.parse_args()

    # Read orchestrator report
    report_path = Path(args.report_path)
    status = "fail"
    test_pass = 0
    test_fail = 0
    duration = 0
    perf_score = None
    stages = []

    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            status = "pass" if report.get("status") == "PASS" else "fail"
            for result in report.get("final_results", []):
                if result.get("status") == "PASS":
                    test_pass += 1
                else:
                    test_fail += 1
                duration += result.get("duration_seconds", 0)
                stages.append({"id": result.get("step_id"), "status": result.get("status")})
        except Exception as e:
            print(f"Warning: Could not parse report: {e}")

    # Login
    try:
        login_resp = requests.post(
            f"{args.api_base_url}/api/auth/login",
            json={"email": args.admin_email, "password": args.admin_password},
            timeout=15,
        )
        if login_resp.status_code != 200:
            print(f"Login failed: {login_resp.status_code}")
            return 0
        token = login_resp.json().get("session_token", "")
    except Exception as e:
        print(f"Login error: {e}")
        return 0

    # Record result
    try:
        record_resp = requests.post(
            f"{args.api_base_url}/api/admin/platform-health/factory-gate/record",
            json={
                "status": status,
                "pipeline": args.pipeline,
                "trigger": args.trigger,
                "branch": args.branch,
                "commit_sha": args.commit_sha,
                "stages": stages,
                "performance_score": perf_score,
                "test_pass_count": test_pass,
                "test_fail_count": test_fail,
                "duration_seconds": round(duration),
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        print(f"Gate result reported: {record_resp.status_code} (status={status}, pass={test_pass}, fail={test_fail})")
    except Exception as e:
        print(f"Report error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
