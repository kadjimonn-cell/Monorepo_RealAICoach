"""
scheduler_jobs.audit_gates — Platform-wide audit & regression-gate jobs.

**Phase 2 incremental domain split — nineteenth batch.**

Owns the recurring audit, regression-gate, and full-system-audit cadence
that keeps the platform release pipeline honest. Each job records a
structured heartbeat through ``scheduler_jobs.observability`` so the
admin observability surface stays in sync.

Jobs in this module
===================
- ``scheduled_acceptance_report_refresh`` — nightly cross-provider
  acceptance-report regeneration with branding + signatures + admin
  email/notification fanout.
- ``scheduled_logo_render_probe`` — nightly inline-CID + CDN logo
  rendering probe with admin notification fanout.
- ``scheduled_full_system_auto_audit`` — continuous safe full-system
  audit + history snapshot.
- ``scheduled_e2e_regression_gate`` — lightweight continuous regression
  gate covering scan score, localization freshness, performance
  guardian status, and budget violations.
- ``scheduled_preview_browser_e2e_wake_and_run`` — nightly Playwright
  browser E2E across critical preview routes with screenshot evidence
  and transition-event alerts.
- ``scheduled_critical_journey_monitor`` — always-on monitor cycle for
  login / dashboard / executive-dashboard / export journeys.
- ``scheduled_perf_audit`` — periodic background performance audit
  covering API latency, bundle size, resource usage.

The ``_get_scheduler_admin_context`` helper currently still lives in
``scheduler_jobs._legacy`` and is imported lazily inside each function
to avoid a circular import at module load time. External callers
continue to import via the package facade::

    from scheduler_jobs import scheduled_full_system_auto_audit
"""

from __future__ import annotations

import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.audit_gates")


PREVIEW_CHALLENGE_GUARD_VERSION = "v2_deterministic"


def _extract_html_title(raw_html: str) -> str:
    text = str(raw_html or "")
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


def _markers_present(text: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker in text]


def _classify_external_preview_block(
    raw_html: str,
    preview_block_cloudflare_code: str,
    preview_block_wake_layer_code: str,
) -> tuple[str, Dict[str, Any]]:
    """
    Deterministic classification guard against Cloudflare false positives.

    BLOCK cloudflare only when challenge evidence is strong and app-shell evidence is weak.
    """
    text = str(raw_html or "").lower()
    title = _extract_html_title(raw_html)

    wake_markers = [
        "ready to start your preview",
        "wake up servers",
        "no available adapters",
    ]
    wake_hits = _markers_present(text, wake_markers)
    if wake_hits:
        return preview_block_wake_layer_code, {
            "guard_version": PREVIEW_CHALLENGE_GUARD_VERSION,
            "classification": "wake_layer",
            "wake_hits": wake_hits,
            "title": title,
        }

    app_shell_markers = [
        "realaicoach - ai-powered coaching",
        "id=\"root\"",
        "/_expo/static/js/web",
        "data-rh=\"true\"",
        "<meta name=\"description\" content=\"realaicoach",
    ]
    app_shell_hits = _markers_present(text, app_shell_markers)

    title_challenge_markers = [
        "just a moment",
        "attention required",
        "checking your browser",
    ]
    title_has_challenge = any(marker in title for marker in title_challenge_markers)

    # Strict markers are highly indicative of an active challenge page.
    strict_cloudflare_markers = [
        "challenges.cloudflare.com",
        "__cf_chl",
        "cf-browser-verification",
        "/cdn-cgi/challenge-platform/h/",
        "/cdn-cgi/challenge-platform/scripts",
        "enable javascript and cookies to continue",
        "please stand by, while we are checking your browser",
        "cf-challenge-running",
        "ray id",
        "cf_clearance",
    ]
    strict_hits = _markers_present(text, strict_cloudflare_markers)

    # Soft markers can appear in normal app HTML (false-positive prone).
    soft_cloudflare_markers = [
        "cloudflare",
        "verify you are human",
        "/cdn-cgi/challenge-platform",
    ]
    soft_hits = _markers_present(text, soft_cloudflare_markers)

    cloudflare_blocked = False
    if title_has_challenge and (len(strict_hits) >= 1 or len(soft_hits) >= 2) and len(app_shell_hits) <= 1:
        cloudflare_blocked = True
    elif len(strict_hits) >= 2 and len(app_shell_hits) == 0:
        cloudflare_blocked = True
    elif len(strict_hits) >= 3:
        cloudflare_blocked = True

    classification = {
        "guard_version": PREVIEW_CHALLENGE_GUARD_VERSION,
        "classification": "cloudflare" if cloudflare_blocked else "none",
        "title": title,
        "title_has_challenge": title_has_challenge,
        "strict_hits": strict_hits,
        "soft_hits": soft_hits,
        "app_shell_hits": app_shell_hits,
        "strict_marker_count": len(strict_hits),
        "soft_marker_count": len(soft_hits),
        "app_shell_marker_count": len(app_shell_hits),
    }

    if cloudflare_blocked:
        return preview_block_cloudflare_code, classification
    return "", classification


async def scheduled_acceptance_report_refresh():
    """Regenerate cross-provider acceptance reports with branding + signatures."""
    job_id = "cross_provider_acceptance_report_refresh"
    try:
        from routes.db import db
        from utils.acceptance_report_generator import generate_acceptance_reports

        result = await generate_acceptance_reports(db)
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.system_runtime_flags.update_one(
            {"key": "cross_provider_acceptance_report_meta"},
            {
                "$set": {
                    "key": "cross_provider_acceptance_report_meta",
                    "value": result,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        pdf_path = Path(result.get("pdf") or "/app/memory/ACCEPTANCE_REPORT.pdf")
        pdf_attachment = None
        if pdf_path.exists():
            pdf_attachment = {
                "filename": pdf_path.name,
                "content": base64.b64encode(pdf_path.read_bytes()).decode("utf-8"),
                "type": "application/pdf",
            }

        admin_users = await db.users.find(
            {"is_admin": True},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(50)
        fallback_admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
        recipient_pool = []
        for admin in admin_users:
            email = str(admin.get("email") or "").strip().lower()
            if email:
                recipient_pool.append((str(admin.get("user_id") or ""), str(admin.get("name") or "Admin"), email))
        if fallback_admin_email and all(fallback_admin_email.lower() != x[2] for x in recipient_pool):
            recipient_pool.append(("", "Admin", fallback_admin_email.lower()))

        if recipient_pool:
            from utils.email_service import send_email, get_logo_inline_attachment
            from utils.email_templates import TEMPLATE_CATALOG

            inline_logo_attachment = get_logo_inline_attachment()

            # Build v7 template for nightly acceptance report
            tpl_entry = TEMPLATE_CATALOG.get("nightly_acceptance_report")
            tpl = tpl_entry["builder"](
                version=str(result.get("version", "")),
                passed=result.get("passed", 0),
                total=result.get("total", 0),
                generated_at=str(result.get("generated_at", "")),
            )

            for admin_user_id, admin_name, admin_email in recipient_pool:
                await send_email(
                    recipient_email=admin_email,
                    subject=tpl.subject,
                    content=tpl.html,
                    recipient_name=admin_name,
                    template_key="nightly_acceptance_report",
                    content_text=tpl.text if hasattr(tpl, "text") else None,
                    attachments=[
                        *([pdf_attachment] if pdf_attachment else []),
                        *([inline_logo_attachment] if inline_logo_attachment else []),
                    ]
                    or None,
                )
                if admin_user_id:
                    await db.notifications.insert_one(
                        {
                            "id": f"acceptance_report_{admin_user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                            "user_id": admin_user_id,
                            "type": "acceptance_report_nightly",
                            "title": "Nightly Acceptance Report Ready",
                            "message": f"Version {result.get('version')} generated ({result.get('passed')}/{result.get('total')} PASS).",
                            "read": False,
                            "created_at": now_iso,
                            "metadata": result,
                        }
                    )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            f"version={result.get('version')} pass={result.get('passed')} total={result.get('total')}",
        )
    except Exception as e:
        logger.error(f"scheduled_acceptance_report_refresh failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_logo_render_probe():
    """Nightly logo rendering probe: validates CID/CDN inputs and dispatches probe email."""
    job_id = "logo_render_probe"
    try:
        from routes.db import db
        from utils.email_service import get_logo_inline_attachment, CDN_APP_LOGO

        now_iso = datetime.now(timezone.utc).isoformat()
        inline_logo = get_logo_inline_attachment()
        inline_ok = bool(inline_logo)
        cdn_ok = False
        cdn_status = "unknown"
        try:
            resp = requests.get(CDN_APP_LOGO, timeout=20)
            cdn_status = str(resp.status_code)
            cdn_ok = resp.status_code == 200
        except Exception as e:
            cdn_status = f"ERR: {e}"

        admins = await db.users.find(
            {"is_admin": True},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(50)
        fallback_admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        recipients = []
        for admin in admins:
            email = str(admin.get("email") or "").strip().lower()
            if email:
                recipients.append((str(admin.get("user_id") or ""), str(admin.get("name") or "Admin"), email))
        if fallback_admin_email and all(fallback_admin_email != x[2] for x in recipients):
            recipients.append(("", "Admin", fallback_admin_email))

        f"[Logo Render Probe] {now_iso[:16]} UTC"

        sent_count = 0
        for admin_user_id, admin_name, admin_email in recipients:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin_email,
                template_key="logo_render_probe",
                recipient_name=admin_name,
                probe_time=now_iso,
                inline_status=str(inline_ok),
                cdn_status=str(cdn_status),
                cdn_url=CDN_APP_LOGO,
            )
            sent_count += 1
            if admin_user_id:
                await db.notifications.insert_one(
                    {
                        "id": f"logo_probe_{admin_user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": admin_user_id,
                        "type": "logo_render_probe",
                        "title": "Logo Render Probe Sent",
                        "message": f"Inline={inline_ok}, CDN={cdn_status}",
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "inline_ok": inline_ok,
                            "cdn_status": cdn_status,
                            "cdn_url": CDN_APP_LOGO,
                            "recipients": sent_count,
                        },
                    }
                )

        run_status = "healthy" if inline_ok and cdn_ok else "warning"
        await db.logo_render_probe_history.insert_one(
            {
                "run_at": now_iso,
                "status": run_status,
                "inline_ok": inline_ok,
                "cdn_ok": cdn_ok,
                "cdn_status": cdn_status,
                "recipients": sent_count,
                "cdn_url": CDN_APP_LOGO,
            }
        )
        await _record_scheduler_heartbeat(
            job_id,
            run_status,
            f"inline_ok={inline_ok} cdn_status={cdn_status} recipients={sent_count}",
        )
    except Exception as e:
        logger.error(f"scheduled_logo_render_probe failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_full_system_auto_audit():
    """Continuous safe auto-audit cadence: runs global full-system audit and stores snapshots."""
    job_id = "platform_full_auto_audit"
    try:
        from routes.db import db
        from routes.platform_health import run_full_system_audit
        from scheduler_jobs.admin_context import _get_scheduler_admin_context

        admin_ctx = await _get_scheduler_admin_context()
        result = await run_full_system_audit(
            safe_auto_fix=True,
            run_domain_autofix=True,
            user=admin_ctx,
        )
        snapshot = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "composite_health": result.get("composite_health", {}),
            "final_scan": result.get("final_scan", {}),
            "drift": result.get("subscription_enforcement_drift", {}),
            "domain_autofix_summary": result.get("domain_autofix_summary", {}),
            "email_template_localization_audit": (result.get("email_template_localization_multilingual_audit") or {}).get("summary", {}),
        }
        await db.platform_auto_audit_history.insert_one(snapshot)
        logger.info(
            "Platform full auto-audit completed: score=%s, grade=%s",
            snapshot["composite_health"].get("score"),
            snapshot["composite_health"].get("grade"),
        )
        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            f"score={snapshot['composite_health'].get('score', 0)} grade={snapshot['composite_health'].get('grade', 'N/A')}",
        )
    except Exception as e:
        logger.error(f"scheduled_full_system_auto_audit failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_e2e_regression_gate():
    """Lightweight continuous regression gate for critical app health signals."""
    job_id = "platform_e2e_regression_gate"
    try:
        from routes.db import db
        from routes.platform_health import scan_platform_health
        from routes.performance_guardian import build_budget_violations_snapshot, guardian_status
        from scheduler_jobs.admin_context import _get_scheduler_admin_context

        admin_ctx = await _get_scheduler_admin_context()
        scan = await scan_platform_health(admin_ctx)
        guardian = await guardian_status(None)
        budget_snapshot = await build_budget_violations_snapshot(db)
        latest_localization = await db.email_template_multilingual_localization_audits.find_one(
            {},
            {"_id": 0, "run_at": 1, "summary": 1, "status": 1},
            sort=[("run_at", -1)],
        ) or {}

        localization_failed = int(((latest_localization.get("summary") or {}).get("languages_failed", 0) or 0))
        localization_run_at = latest_localization.get("run_at")
        localization_fresh = False
        if localization_run_at:
            try:
                localization_dt = datetime.fromisoformat(str(localization_run_at).replace("Z", "+00:00"))
                localization_fresh = (datetime.now(timezone.utc) - localization_dt).total_seconds() <= 6 * 3600
            except Exception:
                localization_fresh = False

        gate_passed = bool(
            (scan.get("score") or 0) >= 95
            and (scan.get("total_issues") or 0) == 0
            and localization_failed == 0
            and localization_fresh
            and str(guardian.get("status") or "unknown") == "healthy"
            and int(budget_snapshot.get("total_violations", 0) or 0) == 0
            and len(budget_snapshot.get("stale_insufficient_routes") or []) == 0
        )

        record = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "gate_passed": gate_passed,
            "score": scan.get("score", 0),
            "grade": scan.get("grade", "F"),
            "total_issues": scan.get("total_issues", 0),
            "critical_issues": scan.get("critical_issues", 0),
            "high_issues": scan.get("high_issues", 0),
            "email_localization": {
                "languages_failed": localization_failed,
                "fresh": localization_fresh,
                "status": latest_localization.get("status") or "unknown",
            },
            "core_web_vitals": {
                "status": guardian.get("status") or "unknown",
                "release_version": guardian.get("release_version"),
                "issues": guardian.get("issues") or [],
            },
            "performance_budgets": {
                "release_version": budget_snapshot.get("release_version"),
                "total_budgets": budget_snapshot.get("total_budgets", 0),
                "total_violations": budget_snapshot.get("total_violations", 0),
                "insufficient_data_routes": budget_snapshot.get("insufficient_data_routes") or [],
                "stale_insufficient_routes": budget_snapshot.get("stale_insufficient_routes") or [],
            },
        }
        await db.platform_regression_gate_history.insert_one(record)

        if not gate_passed:
            admins = await db.users.find(
                {"is_admin": True},
                {"_id": 0, "user_id": 1},
            ).to_list(100)
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"reg_gate_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "platform_regression_gate",
                        "title": "Platform Regression Gate Alert",
                        "message": f"Health score dropped to {record['score']} with {record['total_issues']} issues.",
                        "read": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "metadata": record,
                    }
                )
        logger.info("E2E regression gate completed: passed=%s score=%s", gate_passed, record["score"])
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if gate_passed else "warning",
            f"score={record['score']} issues={record['total_issues']} cwv={record['core_web_vitals']['status']} budget_violations={record['performance_budgets']['total_violations']} stale_budget_coverage={len(record['performance_budgets']['stale_insufficient_routes'])}",
        )
    except Exception as e:
        logger.error(f"scheduled_e2e_regression_gate failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_preview_browser_e2e_wake_and_run():
    """Nightly browser E2E wake-and-run against preview host with evidence snapshots."""
    job_id = "preview_browser_e2e_wake_and_run_nightly"
    run_id = f"preview_e2e_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert
        from utils.email_service import is_email_configured, send_catalog_template

        base_url = (os.environ.get("FRONTEND_BASE_URL") or "http://127.0.0.1:3000").strip().rstrip("/")
        admin_email = str(os.environ.get("TEST_ADMIN_EMAIL") or "").strip()
        admin_password = str(os.environ.get("TEST_ADMIN_PASSWORD") or "").strip()

        wake_wait_seconds = int(os.environ.get("PREVIEW_BROWSER_E2E_WAKE_WAIT_SECONDS", "240") or 240)
        route_wait_ms = int(os.environ.get("PREVIEW_BROWSER_E2E_ROUTE_WAIT_MS", "3000") or 3000)

        checks: list[dict[str, Any]] = []
        screenshots: list[str] = []
        blocking_reason = ""
        status_reason_code = "NO_RUN_DECISION"
        external_lane_status = "unknown"
        localhost_fallback_status = "not_run"
        localhost_fallback: Dict[str, Any] = {
            "executed": False,
            "base_url": "http://127.0.0.1:3000",
            "pass": False,
            "pass_count": 0,
            "fail_count": 0,
            "checks_count": 0,
        }

        preview_block_cloudflare_code = "BLOCKED_EXTERNAL_PREVIEW_CLOUDFLARE"
        preview_block_wake_layer_code = "BLOCKED_EXTERNAL_PREVIEW_WAKE_LAYER"

        critical_routes = [
            ("home", "/"),
            ("careers", "/careers"),
            ("id_checker", "/id-checker"),
            ("executive_dashboard", "/executive-dashboard"),
            ("admin_console", "/admin-console"),
        ]

        challenge_guard_evidence: Dict[str, Any] = {
            "guard_version": PREVIEW_CHALLENGE_GUARD_VERSION,
            "initial": {},
            "post_wake": {},
        }

        async def _save_page_shot(page, slug: str) -> str:
            path = f"/app/test_reports/{run_id}_{slug}.jpeg"
            try:
                await page.screenshot(path=path, quality=20, full_page=False)
                screenshots.append(path)
            except Exception:
                pass
            return path

        async def _check_nonfatal_render(page) -> bool:
            try:
                html = (await page.content() or "").lower()
            except Exception:
                return False
            fatal_markers = [
                "something went wrong",
                "application error",
                "uncaught",
                "chunkloaderror",
                "cannot read properties of undefined",
            ]
            if any(marker in html for marker in fatal_markers):
                return False
            return len(html) > 1200

        async def _run_route_suite(page, target_base: str, route_prefix: str) -> list[dict[str, Any]]:
            lane_checks: list[dict[str, Any]] = []
            for slug, route in critical_routes:
                url = f"{target_base}{route}"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
                    await page.wait_for_timeout(route_wait_ms)
                    ok = await _check_nonfatal_render(page)
                except Exception:
                    ok = False
                await _save_page_shot(page, f"{route_prefix}_{slug}")
                lane_checks.append({"name": f"{route_prefix}_{slug}", "ok": ok, "url": url})
            return lane_checks

        async_playwright = None
        try:
            from playwright.async_api import async_playwright as _async_playwright  # type: ignore

            async_playwright = _async_playwright
        except Exception as playwright_exc:
            blocking_reason = "playwright_runtime_unavailable"
            checks.append(
                {
                    "name": "playwright_runtime_available",
                    "ok": False,
                    "reason": str(playwright_exc)[:220],
                }
            )
            checks.append({"name": "wake_layer_cleared", "ok": False, "reason": blocking_reason})

        if async_playwright is not None:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"],
                )
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 800},
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                await page.goto(base_url, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(5000)
                await _save_page_shot(page, "t0_landing")

                first_html = (await page.content() or "").lower()
                initial_block_code, initial_classification = _classify_external_preview_block(
                    first_html,
                    preview_block_cloudflare_code,
                    preview_block_wake_layer_code,
                )
                challenge_guard_evidence["initial"] = initial_classification
                wake_present = initial_block_code == preview_block_wake_layer_code
                checks.append(
                    {
                        "name": "preview_initial_load",
                        "ok": initial_block_code != preview_block_cloudflare_code,
                        "wake_present": wake_present,
                        "block_code": initial_block_code or "none",
                        "challenge_guard": initial_classification,
                    }
                )

                if initial_block_code == preview_block_cloudflare_code:
                    blocking_reason = preview_block_cloudflare_code
                    external_lane_status = "blocked"
                    checks.append({"name": "wake_layer_cleared", "ok": False, "reason": blocking_reason})
                elif wake_present:
                    wake_clicked = False
                    try:
                        btn = page.get_by_text("Wake up servers", exact=True)
                        await btn.click(force=True)
                        wake_clicked = True
                    except Exception:
                        wake_clicked = False
                    checks.append({"name": "wake_button_click", "ok": wake_clicked})

                    await page.wait_for_timeout(max(120, wake_wait_seconds) * 1000)
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=120000)
                    await page.wait_for_timeout(5000)
                    await _save_page_shot(page, "t1_after_wake")
                    wake_html = (await page.content() or "").lower()
                    wake_block_code, wake_classification = _classify_external_preview_block(
                        wake_html,
                        preview_block_cloudflare_code,
                        preview_block_wake_layer_code,
                    )
                    challenge_guard_evidence["post_wake"] = wake_classification
                    wake_present = wake_block_code == preview_block_wake_layer_code
                    if wake_block_code == preview_block_cloudflare_code:
                        blocking_reason = preview_block_cloudflare_code
                        external_lane_status = "blocked"

                if wake_present:
                    blocking_reason = preview_block_wake_layer_code
                    external_lane_status = "blocked"
                    checks.append({"name": "wake_layer_cleared", "ok": False, "reason": blocking_reason})
                elif not blocking_reason:
                    checks.append({"name": "wake_layer_cleared", "ok": True})
                    external_route_checks = await _run_route_suite(page, base_url, "route")
                    checks.extend(external_route_checks)

                    external_mandatory = [
                        c for c in external_route_checks if str(c.get("name") or "").startswith("route_")
                    ]
                    external_lane_status = "pass" if external_mandatory and all(bool(c.get("ok")) for c in external_mandatory) else "fail"

                    if admin_email and admin_password:
                        login_ok = False
                        details = ""
                        try:
                            await page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=120000)
                            await page.wait_for_timeout(3000)
                            email_selector = page.locator(
                                "input[type='email'], input[name='email'], [data-testid='login-email-input']"
                            ).first
                            password_selector = page.locator(
                                "input[type='password'], input[name='password'], [data-testid='login-password-input']"
                            ).first
                            email_count = await email_selector.count()
                            password_count = await password_selector.count()
                            if email_count > 0 and password_count > 0:
                                await email_selector.fill(admin_email)
                                await password_selector.fill(admin_password)
                                submit_btn = page.locator(
                                    "button[type='submit'], [data-testid='login-submit-button'], text=Sign In, text=Login"
                                ).first
                                submit_count = await submit_btn.count()
                                if submit_count > 0:
                                    await submit_btn.click(force=True)
                                    await page.wait_for_timeout(6000)
                                    login_ok = "login" not in page.url.lower()
                                    details = page.url
                                else:
                                    details = "submit_button_missing"
                            else:
                                details = "login_form_inputs_missing"
                        except Exception as exc:
                            details = str(exc)[:160]
                        await _save_page_shot(page, "login_attempt")
                        checks.append({"name": "browser_admin_login", "ok": login_ok, "detail": details})

                if (
                    ".preview.emergentagent.com" in base_url
                    and blocking_reason in {preview_block_cloudflare_code, preview_block_wake_layer_code}
                ):
                    fallback_base = "http://127.0.0.1:3000"
                    localhost_fallback["executed"] = True
                    checks.append(
                        {
                            "name": "localhost_fallback_triggered",
                            "ok": True,
                            "reason": blocking_reason,
                            "fallback_base_url": fallback_base,
                        }
                    )
                    try:
                        await page.goto(fallback_base, wait_until="domcontentloaded", timeout=120000)
                        await page.wait_for_timeout(3500)
                        fallback_checks = await _run_route_suite(page, fallback_base, "fallback_route")
                        checks.extend(fallback_checks)
                        fallback_pass_count = sum(1 for item in fallback_checks if bool(item.get("ok")))
                        fallback_fail_count = len(fallback_checks) - fallback_pass_count
                        fallback_pass = bool(fallback_checks) and fallback_fail_count == 0
                        localhost_fallback_status = "pass" if fallback_pass else "fail"
                        localhost_fallback.update(
                            {
                                "pass": fallback_pass,
                                "pass_count": fallback_pass_count,
                                "fail_count": fallback_fail_count,
                                "checks_count": len(fallback_checks),
                            }
                        )
                        checks.append(
                            {
                                "name": "localhost_fallback_summary",
                                "ok": fallback_pass,
                                "pass_count": fallback_pass_count,
                                "fail_count": fallback_fail_count,
                            }
                        )
                    except Exception as fallback_exc:
                        localhost_fallback_status = "fail"
                        localhost_fallback.update(
                            {
                                "pass": False,
                                "pass_count": 0,
                                "fail_count": len(critical_routes),
                                "checks_count": 0,
                                "error": str(fallback_exc)[:220],
                            }
                        )
                        checks.append(
                            {
                                "name": "localhost_fallback_summary",
                                "ok": False,
                                "reason": "localhost_fallback_execution_failed",
                                "error": str(fallback_exc)[:220],
                            }
                        )

                await context.close()
                await browser.close()

        mandatory_checks = [c for c in checks if c.get("name") in {
            "wake_layer_cleared",
            "route_home",
            "route_careers",
            "route_id_checker",
            "route_executive_dashboard",
            "route_admin_console",
        }]
        external_checks_present = bool(mandatory_checks)
        external_mandatory_pass = external_checks_present and all(bool(c.get("ok")) for c in mandatory_checks)

        if external_lane_status == "unknown":
            if blocking_reason:
                external_lane_status = "blocked"
            elif external_mandatory_pass:
                external_lane_status = "pass"
            elif external_checks_present:
                external_lane_status = "fail"

        if not checks:
            status = "blocked"
            gate_status = "fail"
            blocking_reason = "NO_PREVIEW_RUN_DATA"
            status_reason_code = "NO_PREVIEW_RUN_DATA"
            external_lane_status = "blocked"
        elif external_lane_status == "pass":
            status = "pass"
            gate_status = "pass"
            status_reason_code = "PASS_EXTERNAL_PREVIEW_E2E"
        elif external_lane_status == "blocked":
            if localhost_fallback_status == "pass":
                status = "blocked"
                gate_status = "fail"
                status_reason_code = blocking_reason or "BLOCKED_EXTERNAL_PREVIEW"
            elif localhost_fallback_status == "fail":
                status = "fail"
                gate_status = "fail"
                base_reason = blocking_reason or "BLOCKED_EXTERNAL_PREVIEW"
                status_reason_code = f"{base_reason}_AND_LOCALHOST_FALLBACK_FAILED"
            else:
                status = "blocked"
                gate_status = "fail"
                status_reason_code = blocking_reason or "BLOCKED_EXTERNAL_PREVIEW"
        else:
            status = "fail"
            gate_status = "fail"
            status_reason_code = "FAIL_EXTERNAL_PREVIEW_CHECKS"

        alert_flag_key = "preview_browser_e2e_alert_state"
        previous_state_doc = await db.system_runtime_flags.find_one({"key": alert_flag_key}, {"_id": 0}) or {}
        previous_gate = str(previous_state_doc.get("gate_status") or "").strip().lower()
        gate_changed = bool(previous_gate) and previous_gate != gate_status

        transition_event: Dict[str, Any] = {
            "changed": gate_changed,
            "previous_gate_status": previous_gate or None,
            "current_gate_status": gate_status,
            "transition": f"{(previous_gate or 'none').upper()}→{gate_status.upper()}" if previous_gate else "FIRST_RUN",
            "at": now_iso,
            "notified": False,
            "emails_sent": 0,
        }

        if gate_changed:
            fail_transition = gate_status == "fail"
            severity = "critical" if fail_transition else "info"
            title = "Nightly Preview Browser E2E State Change"
            message = (
                f"Preview browser E2E transitioned {previous_gate.upper()} → {gate_status.upper()} "
                f"(raw status: {status.upper()}, run {run_id})."
            )

            try:
                await emit_realtime_alert(
                    alert_type="preview_browser_e2e_state_change",
                    severity=severity,
                    title=title,
                    message=message,
                )
            except Exception:
                pass

            admins = await db.users.find(
                {"is_admin": True},
                {"_id": 0, "user_id": 1, "email": 1, "name": 1},
            ).to_list(200)

            now_ts = int(datetime.now(timezone.utc).timestamp())
            fallback_email = str(os.environ.get("ADMIN_EMAIL") or "").strip().lower()
            seen_emails = set()

            for adm in admins:
                uid = str(adm.get("user_id") or "").strip()
                email = str(adm.get("email") or "").strip().lower()
                name = str(adm.get("name") or "Admin")
                if uid:
                    await db.notifications.insert_one(
                        {
                            "id": f"preview_browser_e2e_state_change_{uid}_{now_ts}_{uuid.uuid4().hex[:6]}",
                            "user_id": uid,
                            "type": "preview_browser_e2e_state_change",
                            "title": title,
                            "message": message,
                            "read": False,
                            "created_at": now_iso,
                            "metadata": {
                                "run_id": run_id,
                                "raw_status": status,
                                "previous_gate": previous_gate,
                                "current_gate": gate_status,
                                "blocking_reason": blocking_reason,
                            },
                        }
                    )

                if email and email not in seen_emails and is_email_configured():
                    seen_emails.add(email)
                    try:
                        await send_catalog_template(
                            recipient_email=email,
                            template_key="admin_detailed_system_alert",
                            recipient_name=name,
                            title=title,
                            intro=message,
                            rows=[
                                ("Transition", f"{previous_gate.upper()} → {gate_status.upper()}"),
                                ("Raw Status", status.upper()),
                                ("Run ID", run_id),
                                ("Blocking Reason", blocking_reason or "none"),
                                ("Checks", str(len(checks))),
                            ],
                            accent="#EF4444" if fail_transition else "#10B981",
                            status_label=("DEGRADED" if fail_transition else "RECOVERED"),
                            footer_note="Nightly Preview Browser E2E Monitor",
                        )
                        transition_event["emails_sent"] = int(transition_event.get("emails_sent", 0)) + 1
                    except Exception:
                        pass

            if fallback_email and fallback_email not in seen_emails and is_email_configured():
                try:
                    await send_catalog_template(
                        recipient_email=fallback_email,
                        template_key="admin_detailed_system_alert",
                        recipient_name="Admin",
                        title=title,
                        intro=message,
                        rows=[
                            ("Transition", f"{previous_gate.upper()} → {gate_status.upper()}"),
                            ("Raw Status", status.upper()),
                            ("Run ID", run_id),
                            ("Blocking Reason", blocking_reason or "none"),
                            ("Checks", str(len(checks))),
                        ],
                        accent="#EF4444" if fail_transition else "#10B981",
                        status_label=("DEGRADED" if fail_transition else "RECOVERED"),
                        footer_note="Nightly Preview Browser E2E Monitor",
                    )
                    transition_event["emails_sent"] = int(transition_event.get("emails_sent", 0)) + 1
                except Exception:
                    pass

            transition_event["notified"] = True

        run_doc = {
            "run_id": run_id,
            "job_id": job_id,
            "ran_at": now_iso,
            "status": status,
            "gate_status": gate_status,
            "status_reason_code": status_reason_code,
            "challenge_detection_guard": challenge_guard_evidence,
            "base_url": base_url,
            "blocking_reason": blocking_reason,
            "external_lane_status": external_lane_status,
            "localhost_fallback_status": localhost_fallback_status,
            "localhost_fallback": localhost_fallback,
            "availability_contract": {
                "status": status.upper(),
                "status_reason_code": status_reason_code,
                "external_probe": external_lane_status,
                "localhost_fallback_executed": bool(localhost_fallback.get("executed")),
                "deterministic_outcome": True,
                "allowed_statuses": ["PASS", "FAIL", "BLOCKED"],
            },
            "checks": checks,
            "screenshots": screenshots,
            "transition_event": transition_event,
        }
        await db.preview_browser_e2e_runs.insert_one({**run_doc})
        await db.preview_browser_e2e_state.update_one(
            {"key": "global"},
            {
                "$set": {
                    "key": "global",
                    "updated_at": now_iso,
                    "last_run": run_doc,
                    "last_gate_status": gate_status,
                    "last_transition_event": transition_event,
                }
            },
            upsert=True,
        )

        await db.system_runtime_flags.update_one(
            {"key": alert_flag_key},
            {
                "$set": {
                    "key": alert_flag_key,
                    "updated_at": now_iso,
                    "last_run_at": now_iso,
                    "run_id": run_id,
                    "raw_status": status,
                    "gate_status": gate_status,
                    "previous_gate_status": previous_gate or None,
                    "changed": gate_changed,
                    "transition": transition_event.get("transition"),
                    "transition_event": transition_event,
                }
            },
            upsert=True,
        )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "pass" else "warning",
            f"status={status} checks={len(checks)} screenshots={len(screenshots)} blocking={blocking_reason or 'none'} run_id={run_id}",
        )
    except Exception as e:
        runtime_error = str(e)[:280]
        runtime_error_lower = runtime_error.lower()
        runtime_reason_code = "FAIL_PREVIEW_E2E_RUNTIME_UNAVAILABLE"
        if "playwright" in runtime_error_lower or "executable doesn't exist" in runtime_error_lower:
            runtime_reason_code = "FAIL_PREVIEW_E2E_PLAYWRIGHT_RUNTIME_MISSING"

        logger.error(f"scheduled_preview_browser_e2e_wake_and_run failed: {e}")

        try:
            from routes.db import db

            failure_at = datetime.now(timezone.utc).isoformat()
            failure_base_url = str(locals().get("base_url") or os.environ.get("FRONTEND_BASE_URL") or "http://127.0.0.1:3000").strip().rstrip("/")
            failure_run_id = str(locals().get("run_id") or f"preview_e2e_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}")

            alert_flag_key = "preview_browser_e2e_alert_state"
            previous_state_doc = await db.system_runtime_flags.find_one({"key": alert_flag_key}, {"_id": 0}) or {}
            previous_gate = str(previous_state_doc.get("gate_status") or "").strip().lower()
            gate_status = "fail"
            gate_changed = bool(previous_gate) and previous_gate != gate_status

            transition_event: Dict[str, Any] = {
                "changed": gate_changed,
                "previous_gate_status": previous_gate or None,
                "current_gate_status": gate_status,
                "transition": f"{(previous_gate or 'none').upper()}→{gate_status.upper()}" if previous_gate else "FIRST_RUN",
                "at": failure_at,
                "notified": False,
                "emails_sent": 0,
            }

            failure_doc = {
                "run_id": failure_run_id,
                "job_id": job_id,
                "ran_at": failure_at,
                "status": "fail",
                "gate_status": "fail",
                "status_reason_code": runtime_reason_code,
                "base_url": failure_base_url,
                "blocking_reason": runtime_error,
                "external_lane_status": "blocked",
                "localhost_fallback_status": "not_run",
                "localhost_fallback": {
                    "executed": False,
                    "base_url": "http://127.0.0.1:3000",
                    "pass": False,
                    "pass_count": 0,
                    "fail_count": 0,
                    "checks_count": 0,
                    "error": runtime_error,
                },
                "availability_contract": {
                    "status": "FAIL",
                    "status_reason_code": runtime_reason_code,
                    "external_probe": "blocked",
                    "localhost_fallback_executed": False,
                    "deterministic_outcome": True,
                    "allowed_statuses": ["PASS", "FAIL", "BLOCKED"],
                },
                "checks": [
                    {
                        "name": "preview_e2e_runtime_guard",
                        "ok": False,
                        "reason": runtime_error,
                    }
                ],
                "screenshots": [],
                "transition_event": transition_event,
            }

            await db.preview_browser_e2e_runs.insert_one({**failure_doc})
            await db.preview_browser_e2e_state.update_one(
                {"key": "global"},
                {
                    "$set": {
                        "key": "global",
                        "updated_at": failure_at,
                        "last_run": failure_doc,
                        "last_gate_status": "fail",
                        "last_transition_event": transition_event,
                    }
                },
                upsert=True,
            )
            await db.system_runtime_flags.update_one(
                {"key": alert_flag_key},
                {
                    "$set": {
                        "key": alert_flag_key,
                        "updated_at": failure_at,
                        "last_run_at": failure_at,
                        "run_id": failure_run_id,
                        "raw_status": "fail",
                        "gate_status": "fail",
                        "previous_gate_status": previous_gate or None,
                        "changed": gate_changed,
                        "transition": transition_event.get("transition"),
                        "transition_event": transition_event,
                    }
                },
                upsert=True,
            )
        except Exception as persist_exc:
            logger.error(f"scheduled_preview_browser_e2e_wake_and_run persist-failure-record failed: {persist_exc}")

        await _record_scheduler_heartbeat(job_id, "error", runtime_error[:180])


async def scheduled_critical_journey_monitor():
    """Always-on monitor for login, dashboard, executive dashboard, and export journeys."""
    job_id = "critical_journey_monitor"
    try:
        from routes.critical_journey_monitor import run_critical_journey_monitor_cycle

        result = await run_critical_journey_monitor_cycle(triggered_by="scheduler:5m")
        status = str((result.get("summary") or {}).get("final_status") or result.get("status") or "healthy")
        failed = ",".join((result.get("summary") or {}).get("failed_journeys") or []) or "none"
        heartbeat = "healthy" if status in {"healthy", "healed"} else "warning"
        await _record_scheduler_heartbeat(job_id, heartbeat, f"status={status} failed={failed}")
    except Exception as e:
        logger.error(f"Critical journey monitor scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_perf_audit():
    """Periodic background performance audit — API latency, bundle size, resource usage."""
    job_id = "periodic_perf_audit"
    try:
        from routes.autonomous_engine import run_perf_audit
        audit = await run_perf_audit(triggered_by="scheduler")
        status = "healthy" if audit.get("status") == "HEALTHY" else "warning"
        await _record_scheduler_heartbeat(
            job_id, status,
            f"avg_latency={audit.get('api_overall_avg_ms')}ms bundle={audit.get('bundle_size_mb')}MB alerts={audit.get('alert_count')}",
        )
        logger.info(
            "Perf audit: latency=%sms, bundle=%sMB, memory=%sMB, alerts=%s",
            audit.get("api_overall_avg_ms"), audit.get("bundle_size_mb"),
            audit.get("memory_usage_mb"), audit.get("alert_count"),
        )
    except Exception as exc:
        logger.error(f"scheduled_perf_audit failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_acceptance_report_refresh",
    "scheduled_logo_render_probe",
    "scheduled_full_system_auto_audit",
    "scheduled_e2e_regression_gate",
    "scheduled_preview_browser_e2e_wake_and_run",
    "scheduled_critical_journey_monitor",
    "scheduled_perf_audit",
]
