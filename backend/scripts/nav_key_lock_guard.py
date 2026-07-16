#!/usr/bin/env python3
"""Navigation key lock metadata guard.

Blocks CI when AppShell navigation keys change without a corresponding
metadata lock update in `.nav-key-lock-metadata.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path("/app")
APP_SHELL_FILE = REPO_ROOT / "frontend/src/components/AppShell.tsx"
DEFAULT_METADATA_FILE = REPO_ROOT / ".nav-key-lock-metadata.json"
DEFAULT_HISTORY_FILE = REPO_ROOT / ".nav-key-lock-history.jsonl"
LOCK_SCHEMA_VERSION = 1
LOCK_POLICY_NAME = "nav_key_lock_metadata"


def _extract_string_set(raw: str, marker: str) -> set[str]:
    idx = raw.find(marker)
    if idx == -1:
        return set()
    start = raw.find("[", idx)
    end = raw.find("]", start)
    if start == -1 or end == -1:
        return set()
    block = raw[start : end + 1]
    return set(re.findall(r"'([^']+)'", block))


def _extract_nav_item_keys(raw: str, marker: str) -> set[str]:
    idx = raw.find(marker)
    if idx == -1:
        return set()
    start = raw.find("[", idx)
    if start == -1:
        return set()

    depth = 0
    end = start
    for i, char in enumerate(raw[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == start:
        return set()

    block = raw[start : end + 1]
    keys = set(re.findall(r"key:\s*'([^']+)'", block))
    if "...ADMIN_ITEM" in block:
        keys.add("admin")
    if "ADMIN_CONSOLE_ITEM" in block:
        keys.add("admin-console")
    return keys


def _load_current_nav_snapshot() -> dict:
    if not APP_SHELL_FILE.exists():
        raise FileNotFoundError(f"Missing AppShell file: {APP_SHELL_FILE}")

    raw = APP_SHELL_FILE.read_text(encoding="utf-8")
    snapshot = {
        "locked_user_nav_keys": sorted(_extract_string_set(raw, "const LOCKED_USER_NAV_KEYS")),
        "locked_admin_nav_keys": sorted(_extract_string_set(raw, "const LOCKED_ADMIN_NAV_KEYS")),
        "base_nav_item_keys": sorted(_extract_nav_item_keys(raw, "const BASE_NAV_ITEMS")),
        "active_admin_nav_keys": sorted(_extract_nav_item_keys(raw, "const adminNavDefinitions")),
    }
    return snapshot


def _compute_snapshot_hash(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_lock_payload(snapshot: dict, *, approved_by: str, approval_note: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": LOCK_SCHEMA_VERSION,
        "policy_name": LOCK_POLICY_NAME,
        "approved_by": approved_by,
        "approved_at": now,
        "approval_note": approval_note,
        "locked_via": "backend/scripts/nav_key_lock_guard.py --update-lock",
        "app_shell_path": str(APP_SHELL_FILE),
        "nav_snapshot_hash": _compute_snapshot_hash(snapshot),
        "nav_snapshot": snapshot,
    }


def _load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_history_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _append_history_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _parse_iso_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_strict_governance(enabled_by_flag: bool) -> bool:
    return enabled_by_flag or _truthy(os.environ.get("NAV_KEY_LOCK_STRICT_GOVERNANCE"))


def _write_markdown_artifact(path: Path, result: dict) -> None:
    lines = [
        "# Nav Key Lock Guard Report",
        "",
        f"- Status: **{result.get('status', 'unknown').upper()}**",
        f"- Reason: `{result.get('reason', 'unknown')}`",
        f"- Message: {result.get('message', '')}",
    ]
    if result.get("snapshot_hash"):
        lines.append(f"- Snapshot hash: `{result.get('snapshot_hash')}`")
    if result.get("current_snapshot_hash"):
        lines.append(f"- Current snapshot hash: `{result.get('current_snapshot_hash')}`")
    if result.get("stored_snapshot_hash"):
        lines.append(f"- Stored snapshot hash: `{result.get('stored_snapshot_hash')}`")
    diff = result.get("diff") if isinstance(result.get("diff"), dict) else {}
    if diff:
        lines.extend(["", "## Nav-key delta"])
        for section, delta in diff.items():
            added = ", ".join((delta or {}).get("added") or []) or "-"
            removed = ", ".join((delta or {}).get("removed") or []) or "-"
            lines.append(f"- **{section}**: added [{added}] | removed [{removed}]")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _diff_snapshot(prev: dict, curr: dict) -> dict:
    keys = {
        "locked_user_nav_keys",
        "locked_admin_nav_keys",
        "base_nav_item_keys",
        "active_admin_nav_keys",
    }
    diff: dict[str, dict[str, list[str]]] = {}
    for key in sorted(keys):
        before = set(prev.get(key) or [])
        after = set(curr.get(key) or [])
        added = sorted(after - before)
        removed = sorted(before - after)
        if added or removed:
            diff[key] = {"added": added, "removed": removed}
    return diff


def _validate_lock(
    metadata_file: Path,
    *,
    strict_governance: bool,
    history_file: Path,
) -> tuple[bool, dict]:
    current_snapshot = _load_current_nav_snapshot()
    current_hash = _compute_snapshot_hash(current_snapshot)
    metadata = _load_metadata(metadata_file)

    if not metadata:
        return False, {
            "status": "failed",
            "reason": "missing_or_invalid_metadata",
            "message": (
                f"Missing or invalid nav lock metadata file: {metadata_file}. "
                "Run nav_key_lock_guard.py --update-lock with approval context and commit it."
            ),
            "current_snapshot_hash": current_hash,
            "current_snapshot": current_snapshot,
            "diff": {},
        }

    schema_version = metadata.get("schema_version")
    policy_name = str(metadata.get("policy_name") or "").strip()
    approved_by = str(metadata.get("approved_by") or "").strip()
    approved_at = str(metadata.get("approved_at") or "").strip()
    approval_note = str(metadata.get("approval_note") or "").strip()
    governance = metadata.get("governance") if isinstance(metadata.get("governance"), dict) else {}
    change_ticket = str(governance.get("change_ticket") or "").strip()
    reviewed_by = str(governance.get("reviewed_by") or "").strip()
    stored_snapshot = metadata.get("nav_snapshot") if isinstance(metadata.get("nav_snapshot"), dict) else {}
    stored_hash = str(metadata.get("nav_snapshot_hash") or "").strip()
    computed_stored_hash = _compute_snapshot_hash(stored_snapshot) if stored_snapshot else ""

    if schema_version != LOCK_SCHEMA_VERSION or policy_name != LOCK_POLICY_NAME:
        return False, {
            "status": "failed",
            "reason": "metadata_policy_mismatch",
            "message": (
                f"Metadata policy mismatch. Expected schema_version={LOCK_SCHEMA_VERSION} "
                f"and policy_name={LOCK_POLICY_NAME}."
            ),
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": stored_hash,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    if not approved_by or not approved_at or not approval_note:
        return False, {
            "status": "failed",
            "reason": "metadata_missing_approval_fields",
            "message": "Metadata must include non-empty approved_by, approved_at, and approval_note fields.",
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": stored_hash,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    if _parse_iso_dt(approved_at) is None:
        return False, {
            "status": "failed",
            "reason": "metadata_invalid_timestamp",
            "message": "Metadata approved_at must be a valid ISO timestamp.",
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": stored_hash,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    if strict_governance and (not change_ticket or not reviewed_by):
        return False, {
            "status": "failed",
            "reason": "metadata_missing_governance_fields",
            "message": (
                "Strict governance is enabled. Metadata must include governance.change_ticket "
                "and governance.reviewed_by."
            ),
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": stored_hash,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    if stored_hash and computed_stored_hash and stored_hash != computed_stored_hash:
        return False, {
            "status": "failed",
            "reason": "metadata_hash_mismatch",
            "message": "Metadata nav_snapshot_hash does not match metadata nav_snapshot payload.",
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": stored_hash,
            "computed_stored_snapshot_hash": computed_stored_hash,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    locked_hash = stored_hash or computed_stored_hash

    if strict_governance:
        history_hashes = {
            str(entry.get("snapshot_hash") or "").strip()
            for entry in _load_history_entries(history_file)
            if isinstance(entry, dict)
        }
        if not history_hashes:
            return False, {
                "status": "failed",
                "reason": "history_missing",
                "message": (
                    f"Strict governance is enabled. Missing nav-key lock history file or entries: {history_file}."
                ),
                "current_snapshot_hash": current_hash,
                "stored_snapshot_hash": locked_hash,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "diff": _diff_snapshot(stored_snapshot, current_snapshot),
            }
        if locked_hash not in history_hashes:
            return False, {
                "status": "failed",
                "reason": "history_hash_missing",
                "message": (
                    "Strict governance is enabled. Locked snapshot hash is not recorded in nav-key history."
                ),
                "current_snapshot_hash": current_hash,
                "stored_snapshot_hash": locked_hash,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "diff": _diff_snapshot(stored_snapshot, current_snapshot),
            }

    if locked_hash != current_hash:
        return False, {
            "status": "failed",
            "reason": "nav_keys_changed_without_lock_update",
            "message": (
                "Navigation keys changed but approved lock metadata was not updated. "
                "Update lock metadata in the same change using --update-lock with an approval note."
            ),
            "current_snapshot_hash": current_hash,
            "stored_snapshot_hash": locked_hash,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "diff": _diff_snapshot(stored_snapshot, current_snapshot),
        }

    return True, {
        "status": "passed",
        "reason": "lock_aligned",
        "message": "Navigation key lock metadata is aligned with AppShell nav definitions.",
        "snapshot_hash": current_hash,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "governance": {
            "change_ticket": change_ticket,
            "reviewed_by": reviewed_by,
            "strict_mode": strict_governance,
            "history_file": str(history_file),
        },
        "diff": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard nav-key changes using approved lock metadata.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    parser.add_argument("--update-lock", action="store_true", help="Update metadata lock with current nav snapshot")
    parser.add_argument("--metadata-file", default=str(DEFAULT_METADATA_FILE), help="Path to nav lock metadata file")
    parser.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE), help="Path to nav lock history file")
    parser.add_argument("--approval-note", default=os.environ.get("NAV_KEY_LOCK_APPROVAL_NOTE", "Approved nav lock update"))
    parser.add_argument("--change-ticket", default=os.environ.get("NAV_KEY_LOCK_CHANGE_TICKET", ""), help="Change ticket ID (for strict governance mode)")
    parser.add_argument("--reviewed-by", default=os.environ.get("NAV_KEY_LOCK_REVIEWED_BY", ""), help="Reviewer identity (for strict governance mode)")
    parser.add_argument("--strict-governance", action="store_true", help="Enforce governance metadata fields and history audit trail")
    parser.add_argument("--artifact-file", default=os.environ.get("NAV_KEY_LOCK_GUARD_ARTIFACT", ""), help="Optional markdown artifact output path")
    args = parser.parse_args()

    metadata_file = Path(args.metadata_file)
    history_file = Path(args.history_file)
    strict_governance = _is_strict_governance(args.strict_governance)

    if args.update_lock:
        snapshot = _load_current_nav_snapshot()
        approved_by = (
            os.environ.get("GITHUB_ACTOR")
            or os.environ.get("USER")
            or os.environ.get("USERNAME")
            or "manual"
        )
        change_ticket = str(args.change_ticket or "").strip()
        reviewed_by = str(args.reviewed_by or "").strip()
        if strict_governance and (not change_ticket or not reviewed_by):
            message = (
                "Strict governance update requires both --change-ticket and --reviewed-by. "
                "Provide values and retry."
            )
            if args.json:
                print(json.dumps({"status": "failed", "reason": "missing_governance_update_fields", "message": message}, indent=2))
            else:
                print(message)
            return 1

        payload = _build_lock_payload(snapshot, approved_by=approved_by, approval_note=args.approval_note)
        payload["governance"] = {
            "change_ticket": change_ticket,
            "reviewed_by": reviewed_by,
            "strict_mode": strict_governance,
        }
        metadata_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        _append_history_entry(
            history_file,
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "snapshot_hash": payload.get("nav_snapshot_hash"),
                "approved_by": payload.get("approved_by"),
                "approved_at": payload.get("approved_at"),
                "approval_note": payload.get("approval_note"),
                "change_ticket": change_ticket,
                "reviewed_by": reviewed_by,
                "metadata_file": str(metadata_file),
            },
        )

        if args.json:
            print(
                json.dumps(
                    {
                        "status": "updated",
                        "metadata_file": str(metadata_file),
                        "history_file": str(history_file),
                        **payload,
                    },
                    indent=2,
                )
            )
        else:
            print(f"[nav-lock] updated: {metadata_file}")
            print(f"[nav-lock] history: {history_file}")
            print(f"[nav-lock] snapshot_hash={payload['nav_snapshot_hash']}")
            print(f"[nav-lock] approved_by={payload['approved_by']}")
        return 0

    passed, result = _validate_lock(
        metadata_file,
        strict_governance=strict_governance,
        history_file=history_file,
    )

    artifact_file = str(args.artifact_file or "").strip()
    if artifact_file:
        _write_markdown_artifact(Path(artifact_file), result)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 56)
        print("Navigation Key Lock Metadata Guard")
        print("=" * 56)
        print(result.get("message", ""))
        if result.get("diff"):
            print("\nDetected nav-key delta:")
            for section, delta in result["diff"].items():
                added = ", ".join(delta.get("added") or []) or "-"
                removed = ", ".join(delta.get("removed") or []) or "-"
                print(f" - {section}: added=[{added}] removed=[{removed}]")
        print("=" * 56)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
