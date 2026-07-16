from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict


def run_stale_count_scan(script_path: Path) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["python3", str(script_path), "--json"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        payload = json.loads(result.stdout or "{}")
        payload["exit_code"] = result.returncode
        if result.stderr:
            payload["stderr"] = result.stderr[:2000]
        return payload
    except Exception as exc:
        return {"passed": False, "finding_count": 1, "findings": [], "error": str(exc)}