import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def resolve_external_base_url() -> Optional[str]:
    direct = (os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("FRONTEND_BASE_URL") or "").strip()
    if direct:
        return direct.rstrip("/")

    env_path = "/app/frontend/.env"
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return None


def classify_failure_type(trace: str) -> str:
    text = (trace or "").lower()
    if "assertionerror" in text or "assert " in text:
        return "assertion_failure"
    if "modulenotfounderror" in text or "importerror" in text:
        return "import_module_error"
    if "serverselectiontimeouterror" in text or "connectionrefusederror" in text or "operationalerror" in text:
        return "db_connection_failure"
    if "responsevalidationerror" in text or "http" in text and "status" in text and "expected" in text:
        return "api_contract_mismatch"
    if "asyncio.timeouterror" in text or "timeout" in text or "event loop" in text:
        return "async_timing_issue"
    if "traceback" in text or "error" in text or "exception" in text:
        return "exception_crash"
    return "unknown_failure"


def extract_pytest_root_cause(trace: str) -> dict:
    combined = trace or ""

    failed_summary = re.search(r"FAILED\s+([^\s]+)::([^\s]+)\s+-\s+(.+)", combined)
    failing_test_name = None
    failure_message = None
    if failed_summary:
        failing_test_name = f"{failed_summary.group(1)}::{failed_summary.group(2)}"
        failure_message = failed_summary.group(3)

    line_hit = re.search(r"([\w/\-.]+\.py):(\d+):\s*(.+)", combined)
    failing_line = None
    failing_file = None
    if line_hit:
        failing_file = line_hit.group(1)
        try:
            failing_line = int(line_hit.group(2))
        except Exception:
            failing_line = None
        if not failure_message:
            failure_message = line_hit.group(3)

    return {
        "failure_type": classify_failure_type(combined),
        "failing_test_name": failing_test_name,
        "failing_file": failing_file,
        "failing_line": failing_line,
        "failure_message": failure_message,
        "stack_trace": combined[-4000:],
    }


def compute_certificate_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_certificate_qr_hash(certificate_id: str, certificate_hash: str) -> str:
    raw = f"{certificate_id}:{certificate_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
