"""
GTEC Regression Detector + Alerter
==================================

Compares the latest GTEC scan to the previous persisted scan and fires a
Slack and/or Resend email alert when:

  - Pass rate drops ≥ `pass_rate_drop_pct` points (default 10)
  - Total failing scans increases by ≥ `absolute_fail_delta` (default 5)
  - A new white-screen route appears that wasn't failing before
  - A new route starts throwing `ReferenceError` / `TypeError`

Cool-down: suppresses duplicate alerts for the same fingerprint within
`cooldown_hours` (default 6).

Persistence
-----------
- Settings live at `gtec_crawler_settings._id == "alerts"` (MongoDB).
- Sent-alert fingerprints live at `gtec_crawler_alerts`.

Wired into `scheduled_auto_run` in `routes/gtec_crawler_api.py` so only
auto-runs trigger alerts (manual runs never paginate ops-on-call).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

ROOT = Path("/app")
LATEST = ROOT / "test_reports" / "gtec_scan_latest.json"
SETTINGS_COL = "gtec_crawler_settings"
ALERTS_COL = "gtec_crawler_alerts"
HISTORY_COL = "gtec_crawler_runs"
ALERT_DOC_ID = "alerts"

DEFAULT_SETTINGS = {
    "email_enabled": True,
    "email_recipients": [os.environ.get("GTEC_ALERT_EMAIL", "admin@realaicoach.app")],
    "slack_webhook_url": os.environ.get("GTEC_SLACK_WEBHOOK_URL", ""),
    "pass_rate_drop_pct": 10,
    "absolute_fail_delta": 5,
    "cooldown_hours": 6,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_alert_settings(db) -> dict[str, Any]:
    doc = await db[SETTINGS_COL].find_one({"_id": ALERT_DOC_ID}, {"_id": 0})
    if not doc:
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in doc.items() if v is not None and v != ""})
    return merged


async def save_alert_settings(db, settings: dict[str, Any], actor: str) -> dict[str, Any]:
    payload = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
    # sanity-clamp thresholds
    payload["pass_rate_drop_pct"] = max(1, min(100, int(payload["pass_rate_drop_pct"])))
    payload["absolute_fail_delta"] = max(1, min(100, int(payload["absolute_fail_delta"])))
    payload["cooldown_hours"] = max(1, min(72, int(payload["cooldown_hours"])))
    payload["email_enabled"] = bool(payload["email_enabled"])
    payload["updated_by"] = actor
    payload["updated_at"] = _now().isoformat()
    await db[SETTINGS_COL].update_one(
        {"_id": ALERT_DOC_ID},
        {"$set": payload},
        upsert=True,
    )
    return {k: v for k, v in payload.items() if k not in ("updated_by", "updated_at")}


def _extract_fingerprint_set(report: dict[str, Any], kind: str) -> set[str]:
    """Return the set of `url[viewport]` strings matching the failure kind."""
    results = report.get("results") or []
    out: set[str] = set()
    for r in results:
        if r.get("healthy"):
            continue
        key = f"{r.get('url')}|{r.get('viewport')}"
        if kind == "white_screen" and r.get("white_screen"):
            out.add(key)
        elif kind == "runtime_error":
            joined = " ".join(r.get("page_errors") or []) + " " + " ".join(r.get("console_errors") or [])
            low = joined.lower()
            if "referenceerror" in low or "typeerror" in low or "is not defined" in low:
                out.add(key)
        elif kind == "any_fail":
            out.add(key)
    return out


def _totals(report: dict[str, Any]) -> tuple[int, int, float]:
    t = report.get("totals") or {}
    scans = int(t.get("scans") or 0)
    failing = int(t.get("failing") or 0)
    passing = int(t.get("passing") or 0)
    rate = (passing / scans * 100) if scans else 100.0
    return scans, failing, rate


async def _load_previous_report(db, current_job_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Find the most recent *complete* prior run (before this one) and try to
    reconstruct a minimal report from stored totals + any cached snapshot.

    We keep only the totals per historical run to save space; regression
    detection therefore uses total/fail-rate deltas (reliable) plus the
    *current* report's failure-set against the in-memory previous snapshot
    held on disk at `gtec_scan_prev.json` (written each successful run).
    """
    query: dict[str, Any] = {"status": "complete"}
    if current_job_id:
        query["job_id"] = {"$ne": current_job_id}
    cursor = db[HISTORY_COL].find(query, {"_id": 0}).sort("finished_at", -1).limit(1)
    docs = [d async for d in cursor]
    if not docs:
        return None
    return docs[0]


def _fingerprint(payload: dict[str, Any]) -> str:
    """Stable fingerprint over the regression summary used to suppress dupes."""
    h = hashlib.sha256()
    h.update(json.dumps(payload.get("reasons", []), sort_keys=True).encode())
    h.update(json.dumps(sorted(payload.get("new_white_screens", [])), sort_keys=True).encode())
    h.update(json.dumps(sorted(payload.get("new_runtime_errors", [])), sort_keys=True).encode())
    return h.hexdigest()[:16]


async def detect_regression(db, current_report: dict[str, Any], current_job_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Return an alert payload if the latest report regressed against history.

    None means "no alert to fire" — either no prior baseline, no change big
    enough to matter, or a cool-down is active.
    """
    settings = await get_alert_settings(db)
    scans, failing, rate = _totals(current_report)
    if not scans:
        return None

    prev = await _load_previous_report(db, current_job_id=current_job_id)
    prev_totals = (prev or {}).get("totals") or None
    reasons: list[str] = []
    if prev_totals:
        p_scans = int(prev_totals.get("scans") or 0)
        p_pass = int(prev_totals.get("passing") or 0)
        p_fail = int(prev_totals.get("failing") or 0)
        p_rate = (p_pass / p_scans * 100) if p_scans else 100.0
        rate_delta = round(p_rate - rate, 2)
        fail_delta = failing - p_fail
        if rate_delta >= settings["pass_rate_drop_pct"]:
            reasons.append(f"pass rate dropped {rate_delta:.1f} points ({p_rate:.1f}% → {rate:.1f}%)")
        if fail_delta >= settings["absolute_fail_delta"]:
            reasons.append(f"failing scans increased by {fail_delta} ({p_fail} → {failing})")

    # Compare against the cached previous snapshot for set-level deltas.
    snapshot_file = ROOT / "test_reports" / "gtec_scan_prev.json"
    prev_snapshot: Optional[dict[str, Any]] = None
    if snapshot_file.exists():
        try:
            prev_snapshot = json.loads(snapshot_file.read_text())
        except Exception:
            prev_snapshot = None

    current_white = _extract_fingerprint_set(current_report, "white_screen")
    prev_white = _extract_fingerprint_set(prev_snapshot or {}, "white_screen") if prev_snapshot else set()
    new_white = sorted(current_white - prev_white)
    if new_white:
        reasons.append(f"{len(new_white)} new white-screen route(s)")

    current_err = _extract_fingerprint_set(current_report, "runtime_error")
    prev_err = _extract_fingerprint_set(prev_snapshot or {}, "runtime_error") if prev_snapshot else set()
    new_err = sorted(current_err - prev_err)
    if new_err:
        reasons.append(f"{len(new_err)} new runtime-error route(s)")

    # Save current as next-run baseline (best-effort).
    try:
        snapshot_file.write_text(json.dumps(current_report)[:8_000_000])
    except Exception:
        pass

    if not reasons:
        return None

    payload = {
        "reasons": reasons,
        "new_white_screens": new_white,
        "new_runtime_errors": new_err,
        "current_totals": {"scans": scans, "failing": failing, "pass_rate": round(rate, 2)},
        "previous_totals": (prev or {}).get("totals"),
        "generated_at": current_report.get("generated_at"),
        "frontend_base": current_report.get("frontend_base"),
        "job_id": current_job_id,
    }
    payload["fingerprint"] = _fingerprint(payload)

    # Cool-down gate
    cutoff = _now() - timedelta(hours=settings["cooldown_hours"])
    recent = await db[ALERTS_COL].find_one({
        "fingerprint": payload["fingerprint"],
        "sent_at": {"$gte": cutoff.isoformat()},
    })
    if recent:
        logger.info("gtec_alerts: cool-down active for fingerprint %s — skipping", payload["fingerprint"])
        return None

    return payload


# ── Transport helpers ──────────────────────────────────────────────────

async def _send_slack(webhook_url: str, payload: dict[str, Any]) -> bool:
    if not webhook_url:
        return False
    title = ":rotating_light: GTEC regression detected"
    lines = [f"• {r}" for r in payload["reasons"]]
    current = payload.get("current_totals") or {}
    lines.append(
        f"Current: {current.get('passing' if False else 'pass_rate')}% pass • "
        f"{current.get('failing')} failing / {current.get('scans')} scans"
    )
    if payload.get("frontend_base"):
        lines.append(f"<{payload['frontend_base']}/ops-route-health|Open Route Health →>")
    body = {
        "text": title,
        "attachments": [{
            "color": "#EF4444",
            "title": title,
            "text": "\n".join(lines),
            "ts": int(_now().timestamp()),
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=body)
        return 200 <= resp.status_code < 300
    except Exception as exc:
        logger.warning("gtec_alerts: slack send failed: %s", exc)
        return False


async def _dispatch_email_alert(recipients: list[str], payload: dict[str, Any]) -> bool:
    if not recipients:
        return False
    try:
        from utils.email_service import send_email  # lazy import to avoid cycles
        from utils.email_templates import build_gtec_regression_alert_email
    except Exception as exc:
        logger.warning("gtec_alerts: email_service unavailable: %s", exc)
        return False

    # Build body through the registered V7 catalog entry so the inner card
    # matches the outer chrome (dark theme, teal accents, V7 primitives).
    # Before this refactor we built raw inline HTML here and handed it to
    # send_email() with template_key="system_alert_admin" — that triggered
    # the V7 guardrail "RAW HTML BYPASS DETECTED" auto-brand fallback, which
    # wrapped our raw snippet in V7 chrome but left the body as a white
    # <div> with <h2>/<ul>/<a> (visible mismatch in the admin screenshot).
    current = payload.get("current_totals") or {}
    template = build_gtec_regression_alert_email(
        reasons=list(payload.get("reasons") or []),
        pass_rate=float(current.get("pass_rate") or 0.0),
        failing=int(current.get("failing") or 0),
        scans=int(current.get("scans") or 0),
        new_white_screens=list(payload.get("new_white_screens") or []),
        new_runtime_errors=list(payload.get("new_runtime_errors") or []),
        report_url=(payload.get("frontend_base") or ""),
    )

    all_ok = True
    for addr in recipients:
        try:
            result = await send_email(
                recipient_email=addr,
                subject=template.subject,
                content=template.html,
                content_text=template.text,
                template_key="gtec_regression_alert",
                skip_branding=True,  # V7 chrome already applied by _wrap() inside the builder
            )
            if not (result or {}).get("success"):
                logger.warning("gtec_alerts: email to %s failed: %s", addr, (result or {}).get("error"))
                all_ok = False
        except Exception as exc:
            logger.warning("gtec_alerts: email send crashed for %s: %s", addr, exc)
            all_ok = False
    return all_ok


async def send_regression_alert(db, payload: dict[str, Any]) -> dict[str, Any]:
    settings = await get_alert_settings(db)
    channels_sent: list[str] = []
    if settings.get("email_enabled") and settings.get("email_recipients"):
        ok = await _dispatch_email_alert(list(settings["email_recipients"]), payload)
        if ok:
            channels_sent.append("email")
    if settings.get("slack_webhook_url"):
        ok = await _send_slack(settings["slack_webhook_url"], payload)
        if ok:
            channels_sent.append("slack")

    record = {
        "fingerprint": payload["fingerprint"],
        "job_id": payload.get("job_id"),
        "reasons": payload["reasons"],
        "current_totals": payload.get("current_totals"),
        "previous_totals": payload.get("previous_totals"),
        "new_white_screens": payload.get("new_white_screens", []),
        "new_runtime_errors": payload.get("new_runtime_errors", []),
        "channels_sent": channels_sent,
        "sent_at": _now().isoformat(),
    }
    await db[ALERTS_COL].insert_one(record)
    return {"alerted": bool(channels_sent), "channels": channels_sent, "fingerprint": payload["fingerprint"]}


async def maybe_fire_regression_alert(db, report: dict[str, Any], job_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Public helper wired by scheduled_auto_run: detect + fire in one call."""
    payload = await detect_regression(db, report, job_id)
    if not payload:
        return None
    try:
        return await send_regression_alert(db, payload)
    except Exception as exc:
        logger.exception("gtec_alerts: send_regression_alert crashed: %s", exc)
        return None
