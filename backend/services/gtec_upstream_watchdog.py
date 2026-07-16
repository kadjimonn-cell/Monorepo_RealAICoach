"""
GTEC Upstream Watchdog — §5 Systemic-Fix Self-Driving Loop

Purpose
-------
The GTEC V2 scanner tracks a set of "blocked upstream" npm packages that
cannot be safely upgraded today because the upstream ecosystem hasn't yet
shipped a compatible release (e.g. `eslint-config-expo` supporting
ESLint 10, `@react-native-async-storage/async-storage` 3.x with the
new-arch migration, Expo SDK 56). These appear every scan as recurring
`node_outdated` findings.

Per the directive's §5 (ANTI-LOOP & DUPLICATION CONTROL):
    "If same issue appears repeatedly: → ESCALATE to SYSTEMIC FIX
     (global correction required)"

This service is that systemic fix. It:
    1. Reads a declarative watchlist from `memory/gtec_upstream_watchlist.json`
       describing every currently-blocked package + the exact condition
       under which the blocker clears.
    2. Queries the npm registry (read-only, unauthenticated) for the
       latest manifests + peerDependencies.
    3. Compares each against the declared `unblock_when` predicate.
    4. When a blocker clears, writes a P-priority ticket into
       `memory/tickets/` (auto-generated, deterministic filename so
       re-runs don't dup-file), records the event in MongoDB, and
       emits a §12-format notice.

Idempotency
-----------
Each watchlist entry has a stable `id`. A MongoDB collection
`gtec_upstream_watchdog` stores one document per id recording its last
observed state. The same "cleared" event will not write a second ticket;
instead it refreshes the last_checked_at timestamp.

Safe by design
--------------
    • Read-only: talks to registry.npmjs.org + pypi.org; never mutates
      package.json / yarn.lock. Only writes ticket files + DB rows.
    • No side-effects on scanner findings — it only augments context.
    • Runs nightly (02:30 UTC) via APScheduler; manual trigger endpoint
      available for on-demand checks.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("gtec.upstream_watchdog")

# ──────────────────────────────────────────────────────────────────────────
# Paths + constants
# ──────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
WATCHLIST_PATH = ROOT / "memory" / "gtec_upstream_watchlist.json"
TICKETS_DIR = ROOT / "memory" / "tickets"
NPM_REGISTRY = "https://registry.npmjs.org"
PYPI_REGISTRY = "https://pypi.org/pypi"
REQUEST_TIMEOUT = 15.0
COLLECTION = "gtec_upstream_watchdog"
PLATFORM_DATA_ONLY = str(os.environ.get("GTEC_PLATFORM_DATA_ONLY", "1")).strip() != "0"
# Email notifications: dispatched ONLY when a blocker newly clears (zero noise
# on "still blocked" runs). Set GTEC_WATCHDOG_EMAIL_ENABLED=0 to disable.
NOTIFY_EMAIL_ENABLED = os.environ.get("GTEC_WATCHDOG_EMAIL_ENABLED", "1") != "0"
NOTIFY_DEFAULT_RECIPIENTS = [
    e.strip().lower()
    for e in (os.environ.get("GTEC_WATCHDOG_EMAIL_TO") or "admin@realaicoach.app").split(",")
    if e.strip()
]


# ──────────────────────────────────────────────────────────────────────────
# Registry helpers
# ──────────────────────────────────────────────────────────────────────────
async def _fetch_npm_manifest(client: httpx.AsyncClient, pkg: str) -> dict[str, Any]:
    """Fetch the latest package manifest from the npm registry."""
    url = f"{NPM_REGISTRY}/{pkg}"
    resp = await client.get(url, headers={"Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    latest = (data.get("dist-tags") or {}).get("latest")
    manifest = (data.get("versions") or {}).get(latest) or {}
    return {
        "latest": latest,
        "peer_dependencies": manifest.get("peerDependencies") or {},
        "dependencies": manifest.get("dependencies") or {},
        "readme": (data.get("readme") or "")[:8000],  # cap for predicate tests
    }


async def _fetch_pypi_manifest(client: httpx.AsyncClient, pkg: str) -> dict[str, Any]:
    """Fetch the latest package manifest from PyPI (JSON API).

    Normalises the response to the same shape as `_fetch_npm_manifest` so
    the downstream predicate evaluator can treat npm + pypi uniformly:
        {latest, peer_dependencies, dependencies, readme}
    PyPI has no `peerDependencies`, but `requires_dist` is the closest
    analogue — we map it into `dependencies` so `peer_dep_of` predicates
    can still be expressed against pypi packages' install requirements.
    """
    url = f"{PYPI_REGISTRY}/{pkg}/json"
    resp = await client.get(url, headers={"Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    info = data.get("info") or {}
    latest = info.get("version")

    # `requires_dist` is a list of strings like "httpx (>=0.25,<1.0) ; extra=='x'".
    # Convert to a dict {pkg_name: version_spec} — good enough for predicate eval.
    requires = info.get("requires_dist") or []
    deps: dict[str, str] = {}
    for line in requires:
        if not line or ";" in line.split(" ", 1)[0]:
            # Skip env-marker-only lines we can't parse crudely; still include
            # the real-package lines below.
            pass
        # Grab leading package name (letters, digits, dashes, dots, underscores).
        import re as _re
        m = _re.match(r"^([A-Za-z0-9._-]+)\s*(\([^)]+\)|[<>=!~].*?)?(?:\s*;|$)", line)
        if m:
            name = m.group(1).strip().lower()
            spec = (m.group(2) or "").strip().strip("()") or "*"
            deps.setdefault(name, spec)

    return {
        "latest": latest,
        "peer_dependencies": deps,   # pypi has no peerDeps; alias requires_dist
        "dependencies": deps,
        "readme": (info.get("description") or "")[:8000],
    }


async def _fetch_manifest(
    client: httpx.AsyncClient, registry: str, pkg: str
) -> dict[str, Any]:
    """Dispatch by registry. Adding new registries = new branch here."""
    if registry == "npm":
        return await _fetch_npm_manifest(client, pkg)
    if registry == "pypi":
        return await _fetch_pypi_manifest(client, pkg)
    raise ValueError(f"unsupported registry: {registry!r}")


# ──────────────────────────────────────────────────────────────────────────
# Predicate evaluation
# ──────────────────────────────────────────────────────────────────────────
def _parse_major(v: str | None) -> int:
    if not v:
        return 0
    v = v.lstrip("^~>=< ")
    try:
        return int(v.split(".", 1)[0])
    except (ValueError, IndexError):
        return 0


def _semver_gte(a: str | None, b: str) -> bool:
    """Simple gte for strings like '3.1.0' vs '3.0.2'."""
    if not a:
        return False
    def _tuple(v: str) -> tuple[int, ...]:
        v = v.lstrip("^~>=< ")
        return tuple(int(x) for x in v.split("-", 1)[0].split(".")[:3] if x.isdigit())
    try:
        return _tuple(a) >= _tuple(b)
    except Exception:
        return False


def _peer_satisfies(peer_range: str | None, version_range: str) -> bool:
    """Check if a peer-dependency range accepts versions matching `version_range`.

    We use a conservative string containment + major-number check; the
    watchlist predicates are coarse enough that this is sufficient (e.g.
    peer=">=10" accepts ">=10.0.0"). Real semver-range intersection would
    need a full semver lib — overkill for this use case.
    """
    if not peer_range:
        return False
    # Normalise
    peer_range = peer_range.replace(" ", "")
    # Collect ORed clauses, splitting on ||
    clauses = [c.strip() for c in peer_range.split("||") if c.strip()]
    target_major = _parse_major(version_range.lstrip(">=").lstrip("^~<"))
    for clause in clauses:
        # Any clause containing the target major satisfies
        for tok in clause.replace(">=", " ").replace("<", " ").replace("^", " ").replace("~", " ").split():
            if not tok:
                continue
            try:
                m = _parse_major(tok)
                if m >= target_major:
                    return True
            except Exception:
                continue
    return False


def _evaluate_unblock(entry: dict[str, Any], manifest: dict[str, Any]) -> tuple[bool, str]:
    """Return (cleared, reason)."""
    cond = entry.get("unblock_when") or {}
    latest = manifest.get("latest")

    if "latest_gte" in cond:
        target = cond["latest_gte"]
        ok = _semver_gte(latest, target)
        reason = (
            f"latest={latest} gte target={target}"
            if ok
            else f"latest={latest} still < target={target}"
        )
        # Optional docs-contains check
        docs_needle = cond.get("docs_contain")
        if ok and docs_needle:
            if docs_needle.lower() not in (manifest.get("readme") or "").lower():
                return False, (
                    f"{reason}, but README does not yet mention '{docs_needle}' "
                    "— migration guide not ready"
                )
        return ok, reason

    if "latest_major_gte" in cond:
        target = int(cond["latest_major_gte"])
        cur_major = _parse_major(latest)
        ok = cur_major >= target
        return ok, f"latest major={cur_major} vs target={target}"

    if "peer_dep_of" in cond:
        peer_pkg = cond["peer_dep_of"]
        required = cond["peer_satisfies"]
        peer_range = (manifest.get("peer_dependencies") or {}).get(peer_pkg)
        ok = _peer_satisfies(peer_range, required)
        return ok, (
            f"peer '{peer_pkg}' on {entry['package']}@{latest} = "
            f"{peer_range!r} (need: {required})"
        )

    return False, "no supported predicate in unblock_when"


# ──────────────────────────────────────────────────────────────────────────
# Notification (Resend, plain-text) — ONLY on newly-cleared blockers.
# ──────────────────────────────────────────────────────────────────────────
async def _notify_cleared(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    reason: str,
    ticket_path: Path,
) -> dict[str, Any]:
    """Send a Resend email announcing the unblock via the registered
    `gtec_upstream_watchdog_cleared` TEMPLATE_CATALOG entry.

    The email goes through the full V7 guardrail (template_key enforced,
    HTML + plain-text alternatives, brand footer, dark-mode safe styling,
    campaign tracking). Plain-text fallback is still produced by the
    template builder — Resend will deliver whichever the recipient's
    client prefers.

    Returns a summary dict {sent: [...], skipped_reason: ...}.
    """
    if not NOTIFY_EMAIL_ENABLED:
        return {"sent": [], "skipped_reason": "GTEC_WATCHDOG_EMAIL_ENABLED=0"}
    if not NOTIFY_DEFAULT_RECIPIENTS:
        return {"sent": [], "skipped_reason": "no recipients configured"}

    try:
        ticket_rel = str(ticket_path.relative_to(ROOT))
    except ValueError:
        ticket_rel = str(ticket_path)
    try:
        ticket_excerpt = ticket_path.read_text(encoding="utf-8")[:2200]
    except Exception:
        ticket_excerpt = "(ticket body could not be read)"

    # Lazy import — decouples this module from email_service at import time.
    from utils.email_service import send_catalog_template

    template_kwargs = {
        "package": entry["package"],
        "latest_version": manifest.get("latest") or "?",
        "registry": entry.get("registry", "npm"),
        "entry_id": entry.get("id", ""),
        "blocker_reason": entry.get("blocker_reason", ""),
        "predicate_reason": reason,
        "unblocks_packages": entry.get("unblocks_packages") or [],
        "ticket_path": ticket_rel,
        "ticket_excerpt": ticket_excerpt,
    }

    sent: list[dict[str, Any]] = []
    for addr in NOTIFY_DEFAULT_RECIPIENTS:
        try:
            res = await send_catalog_template(
                template_key="gtec_upstream_watchdog_cleared",
                recipient_email=addr,
                **template_kwargs,
            )
            sent.append({"email": addr, "ok": bool(res.get("success"))})
        except Exception as exc:
            log.warning("upstream_watchdog: email to %s failed: %s", addr, exc)
            sent.append({"email": addr, "ok": False, "error": str(exc)[:160]})
    return {"sent": sent}


# ──────────────────────────────────────────────────────────────────────────
# Ticket writer
# ──────────────────────────────────────────────────────────────────────────
def _ticket_path(entry: dict[str, Any]) -> Path:
    template = entry.get("ticket_template") or f"P2_AUTO_{entry['id']}.md"
    return TICKETS_DIR / template


def _write_ticket(entry: dict[str, Any], manifest: dict[str, Any], reason: str) -> Path:
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    path = _ticket_path(entry)
    if path.exists():
        # Append a newline-separated notice (preserve human-authored content).
        with path.open("a", encoding="utf-8") as f:
            f.write(
                f"\n\n## 🤖 Upstream Watchdog Notice — {datetime.now(timezone.utc).isoformat()}\n"
                f"**Blocker cleared** for `{entry['package']}` (id=`{entry['id']}`).\n"
                f"- Latest: `{manifest.get('latest')}`\n"
                f"- Reason: {reason}\n"
                f"- Unblocks: {', '.join(entry.get('unblocks_packages') or [])}\n"
                f"- Systemic fix ref: `{entry.get('systemic_fix_ref')}`\n"
                f"- Follow the staged playbook in `P2_REMAINING_MAJOR_DEPS.md` "
                f"or the relevant ticket body above to execute the upgrade.\n"
            )
        return path
    # New file: minimal auto-ticket with everything the engineer needs.
    body = [
        f"# {entry.get('ticket_template','').replace('.md','') or 'P2 Auto-Ticket'} — Upstream Cleared",
        "",
        f"**Created by**: GTEC Upstream Watchdog ({datetime.now(timezone.utc).isoformat()})",
        f"**Trigger**: `{entry['id']}` — blocker cleared upstream",
        "**Priority**: derived from ticket template name (P1/P2/P3)",
        "",
        "## Context",
        f"- Package watched: `{entry['package']}` ({entry.get('registry','npm')})",
        f"- Latest available: `{manifest.get('latest')}`",
        f"- Blocker reason (now resolved): {entry.get('blocker_reason','')}",
        f"- Unblock condition met: {reason}",
        f"- Packages this unblocks: {', '.join(entry.get('unblocks_packages') or [])}",
        "",
        "## Next steps (follow the staged playbook)",
        "1. Create a backup of `package.json` + `yarn.lock` (see earlier tickets for the exact `cp` commands).",
        "2. Bump the unblocked packages one stage at a time, running the build gate + lint gate between stages.",
        "3. Re-run `POST /api/admin/gtec-scan-v2/run` and confirm `node_outdated` count drops.",
        "4. Email the §12 report to `admin@realaicoach.app`.",
        "",
        "## Abort conditions",
        "- `yarn run expo export --platform web` fails.",
        "- `yarn lint` produces > 20 NEW errors (pre-existing errors are acceptable).",
        "- GTEC V2 scan fails with any new HIGH/CRITICAL finding.",
        "",
        "## Notes",
        "This ticket was auto-generated. Engineer review is still required before bumping — the watchdog only",
        "reports that the UPSTREAM blocker has cleared; the internal compatibility test is a separate step.",
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────
def _load_watchlist() -> list[dict[str, Any]]:
    if not WATCHLIST_PATH.exists():
        log.warning("upstream_watchdog: watchlist file missing at %s", WATCHLIST_PATH)
        return []
    data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    return data.get("watchlist") or []


async def run_watchdog(
    db: AsyncIOMotorDatabase | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Run one pass over the watchlist. Idempotent — safe to call hourly.

    Returns a structured report the API layer can surface in §12 format.
    """
    watchlist = _load_watchlist()
    if not watchlist:
        return {"ok": False, "reason": "no watchlist entries", "entries": []}

    if PLATFORM_DATA_ONLY:
        now = datetime.now(timezone.utc)
        report_entries = [
            {
                "id": entry.get("id"),
                "package": entry.get("package"),
                "registry": entry.get("registry", "npm"),
                "status": "skipped_platform_data_only",
                "reason": "external registry probing disabled by platform-data-only policy",
            }
            for entry in watchlist
        ]
        summary = {
            "ok": True,
            "trigger": trigger,
            "checked_at": now.isoformat(),
            "total": len(report_entries),
            "cleared": 0,
            "still_blocked": 0,
            "errors": 0,
            "mode": "platform_data_only",
            "entries": report_entries,
        }
        if db is not None:
            await db["gtec_upstream_watchdog_runs"].insert_one(
                {**{k: v for k, v in summary.items() if k != "entries"}, "entries": report_entries}
            )
        return summary

    now = datetime.now(timezone.utc)
    report_entries: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "gtec-upstream-watchdog/1.0"},
    ) as client:
        for entry in watchlist:
            entry_result: dict[str, Any] = {
                "id": entry.get("id"),
                "package": entry.get("package"),
                "registry": entry.get("registry", "npm"),
            }
            try:
                registry = entry_result["registry"]
                if registry not in ("npm", "pypi"):
                    entry_result["status"] = "skipped_unsupported_registry"
                    report_entries.append(entry_result)
                    continue
                manifest = await _fetch_manifest(client, registry, entry["package"])
                cleared, reason = _evaluate_unblock(entry, manifest)
                entry_result.update(
                    latest=manifest.get("latest"),
                    cleared=cleared,
                    reason=reason,
                )

                # Persist state (idempotency lives here).
                prior = None
                if db is not None:
                    prior = await db[COLLECTION].find_one(
                        {"_id": entry["id"]}, {"_id": 0, "cleared": 1, "ticket_path": 1}
                    )
                already_ticketed = bool(prior and prior.get("cleared") and prior.get("ticket_path"))

                if cleared and not already_ticketed:
                    ticket = _write_ticket(entry, manifest, reason)
                    try:
                        entry_result["ticket_path"] = str(ticket.relative_to(ROOT))
                    except ValueError:
                        # Ticket is outside ROOT (test harness, non-standard
                        # deployment, etc.) — report absolute path.
                        entry_result["ticket_path"] = str(ticket)
                    entry_result["status"] = "cleared_ticket_opened"
                    # Fire the "newly cleared" notification. Failures here
                    # must NOT abort the run — the ticket is already on
                    # disk + DB; the email is a bonus.
                    try:
                        notification = await _notify_cleared(
                            entry, manifest, reason, ticket,
                        )
                        entry_result["notification"] = notification
                    except Exception as exc:
                        log.warning(
                            "upstream_watchdog: notify_cleared failed for %s: %s",
                            entry.get("id"), exc,
                        )
                        entry_result["notification"] = {
                            "sent": [], "skipped_reason": f"notify_error: {exc}"[:200],
                        }
                    log.info(
                        "upstream_watchdog: blocker cleared for %s — ticket at %s",
                        entry["id"], entry_result["ticket_path"],
                    )
                elif cleared and already_ticketed:
                    entry_result["ticket_path"] = prior.get("ticket_path")
                    entry_result["status"] = "cleared_ticket_already_open"
                else:
                    entry_result["status"] = "still_blocked"

                if db is not None:
                    await db[COLLECTION].update_one(
                        {"_id": entry["id"]},
                        {
                            "$set": {
                                "package": entry["package"],
                                "latest": manifest.get("latest"),
                                "cleared": cleared,
                                "reason": reason,
                                "ticket_path": entry_result.get("ticket_path"),
                                "last_checked_at": now.isoformat(),
                                "last_trigger": trigger,
                            },
                            "$inc": {"check_count": 1},
                        },
                        upsert=True,
                    )
            except Exception as exc:
                log.exception("upstream_watchdog: error on entry %s", entry.get("id"))
                entry_result["status"] = "error"
                entry_result["error"] = str(exc)[:200]
            report_entries.append(entry_result)

    cleared_count = sum(1 for e in report_entries if e.get("cleared"))
    summary = {
        "ok": True,
        "trigger": trigger,
        "checked_at": now.isoformat(),
        "total": len(report_entries),
        "cleared": cleared_count,
        "still_blocked": sum(1 for e in report_entries if e.get("status") == "still_blocked"),
        "errors": sum(1 for e in report_entries if e.get("status") == "error"),
        "entries": report_entries,
    }
    if db is not None:
        await db["gtec_upstream_watchdog_runs"].insert_one(
            {**{k: v for k, v in summary.items() if k != "entries"},
             "entries": report_entries}
        )
    return summary


async def get_state(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Return the latest state per watchlist entry + last run summary."""
    entries: list[dict[str, Any]] = []
    async for row in db[COLLECTION].find({}, {"_id": 1, "package": 1, "latest": 1,
                                              "cleared": 1, "reason": 1,
                                              "ticket_path": 1,
                                              "last_checked_at": 1,
                                              "check_count": 1}):
        entries.append({"id": row.get("_id"), **{k: v for k, v in row.items() if k != "_id"}})
    last_run = await db["gtec_upstream_watchdog_runs"].find_one(
        {}, {"_id": 0}, sort=[("checked_at", -1)]
    )
    return {
        "watchlist_size": len(_load_watchlist()),
        "tracked": entries,
        "last_run": last_run,
    }


# ──────────────────────────────────────────────────────────────────────────
# Scheduler entrypoint
# ──────────────────────────────────────────────────────────────────────────
async def scheduled_upstream_watchdog() -> dict[str, Any]:
    """APScheduler entrypoint — grabs a db handle and runs the check."""
    try:
        # Import locally to avoid hard dependency at module load.
        from routes.db import db as _db
        return await run_watchdog(_db, trigger="apscheduler_nightly")
    except Exception:
        log.exception("upstream_watchdog scheduled run failed")
        return {"ok": False, "error": "scheduled_run_failed"}


if __name__ == "__main__":
    # CLI: `python -m services.gtec_upstream_watchdog`
    async def _main():
        result = await run_watchdog(db=None, trigger="cli")
        print(json.dumps(result, indent=2, default=str))

    asyncio.run(_main())
