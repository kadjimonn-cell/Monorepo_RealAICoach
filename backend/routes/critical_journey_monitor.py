"""Critical Journey Monitor — always-on admin journey validation with safe auto-heal.

Monitors these platform-critical journeys:
- login
- dashboard
- executive dashboard
- ID verification exports

Creates incidents and realtime admin alerts before regressions become user-visible.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from routes.db import create_jwt_token, db, require_admin

router = APIRouter(prefix="/admin/critical-journeys", tags=["Critical Journey Monitor"])

CONFIG_COLLECTION = "critical_journey_monitor_config"
RUNS_COLLECTION = "critical_journey_monitor_runs"
INCIDENTS_COLLECTION = "critical_journey_monitor_incidents"
STATE_KEY = "critical_journey_monitor_state"

DEFAULT_CONFIG = {
    "enabled": True,
    "auto_heal_enabled": True,
    "notify_admins": True,
    "incident_cooldown_minutes": 20,
    "check_interval_minutes": 5,
    "request_timeout_seconds": 12,
    "base_url_override": "",
}


class MonitorConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_heal_enabled: Optional[bool] = None
    notify_admins: Optional[bool] = None
    incident_cooldown_minutes: Optional[int] = None
    request_timeout_seconds: Optional[float] = None
    base_url_override: Optional[str] = None


class IncidentResolveBody(BaseModel):
    incident_id: str
    resolution_note: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    return (
        os.environ.get("REACT_APP_BACKEND_URL")
        or os.environ.get("FRONTEND_BASE_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or "http://localhost:3000"
    ).strip().rstrip("/")


def _normalize_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    if value.endswith("/api"):
        value = value[:-4]
    return value.rstrip("/")


def _request_base_url(request: Optional[Request]) -> str:
    if request is None:
        return ""
    scheme = (
        (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        or request.url.scheme
        or "https"
    )
    host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host") or "")
        .split(",")[0]
        .strip()
    )
    if not host:
        return ""
    return _normalize_base_url(f"{scheme}://{host}")


def _is_preview_url(url: str) -> bool:
    return ".preview.emergentagent.com" in (url or "")


def _frontend_env_base_url() -> str:
    frontend_env_path = "/app/frontend/.env"
    if not os.path.exists(frontend_env_path):
        return ""
    try:
        with open(frontend_env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "REACT_APP_BACKEND_URL":
                    return _normalize_base_url(value.strip().strip('"').strip("'"))
    except Exception:
        return ""
    return ""


async def _resolve_base_url(config: Dict[str, Any], request: Optional[Request] = None) -> str:
    request_base = _request_base_url(request)
    configured_base = _normalize_base_url(str(config.get("base_url_override") or ""))
    frontend_env_base = _frontend_env_base_url()
    env_base = _normalize_base_url(_base_url())
    candidate = configured_base or frontend_env_base or env_base

    if request_base and _is_preview_url(request_base):
        if (not candidate) or (not _is_preview_url(candidate)) or (candidate != request_base):
            return request_base

    if candidate:
        return candidate
    if request_base:
        return request_base
    return "http://localhost:3000"


def _default_admin_email() -> str:
    return os.environ.get("TEST_ADMIN_EMAIL", "admin@realaicoach.app")


def _default_admin_password() -> str:
    return os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")


async def _mint_synthetic_admin_session() -> str:
    user = await db.users.find_one(
        {"email": _default_admin_email()},
        {"_id": 0, "user_id": 1, "email": 1, "token_version": 1},
    )
    if not user:
        return ""
    token = create_jwt_token(
        user["user_id"],
        user["email"],
        int(user.get("token_version", 0) or 0),
        30,
    )
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=30)
    await db.user_sessions.update_one(
        {"session_token": token},
        {
            "$set": {
                "session_token": token,
                "user_id": user["user_id"],
                "email": user["email"],
                "issued_at": now,
                "expires_at": expires_at,
                "created_at": now.isoformat(),
                "auth_provider": "critical_journey_monitor",
                "synthetic_monitor": True,
            }
        },
        upsert=True,
    )
    await db.user_sessions.delete_many({"synthetic_monitor": True, "expires_at": {"$lt": now}})
    return token


def _isoify(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_isoify(item) for item in value]
    if isinstance(value, dict):
        return {key: _isoify(val) for key, val in value.items()}
    return value


async def _get_config() -> Dict[str, Any]:
    doc = await db[CONFIG_COLLECTION].find_one({"_id": "config"}, {"_id": 0})
    if not doc:
        doc = {**DEFAULT_CONFIG}
        await db[CONFIG_COLLECTION].insert_one({"_id": "config", **doc, "updated_at": _now_iso()})
    return {**DEFAULT_CONFIG, **doc}


def _journey_status(steps: List[Dict[str, Any]]) -> str:
    if all(step.get("healthy") for step in steps):
        return "healthy"
    if any(step.get("healthy") for step in steps):
        return "degraded"
    return "failing"


def _build_journey(journey_id: str, label: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed_steps = [step["id"] for step in steps if not step.get("healthy")]
    return {
        "journey_id": journey_id,
        "label": label,
        "status": _journey_status(steps),
        "latency_ms": round(sum(float(step.get("latency_ms", 0) or 0) for step in steps), 1),
        "failed_steps": failed_steps,
        "steps": steps,
    }


async def _probe(
    client: httpx.AsyncClient,
    *,
    step_id: str,
    label: str,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    validator=None,
) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        response = await client.request(method, url, headers=headers, json=json_body, params=params)
        latency = round((time.monotonic() - started) * 1000, 1)
        text_sample = response.text[:400] if "text" in response.headers.get("content-type", "") or "html" in response.headers.get("content-type", "") else ""
        payload = None
        try:
            payload = response.json()
        except Exception:
            payload = None
        healthy = response.status_code < 400
        if healthy and validator:
            healthy = bool(validator(response, payload, text_sample))
        return {
            "id": step_id,
            "label": label,
            "method": method,
            "path": url,
            "status_code": response.status_code,
            "latency_ms": latency,
            "healthy": healthy,
            "content_type": response.headers.get("content-type", ""),
            "details": {
                "content_length": len(response.content or b""),
                "text_sample": text_sample,
            },
            "payload": payload if isinstance(payload, dict) else None,
        }
    except Exception as exc:
        return {
            "id": step_id,
            "label": label,
            "method": method,
            "path": url,
            "status_code": 0,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "healthy": False,
            "content_type": "",
            "details": {"error": str(exc)[:220]},
            "payload": None,
        }


def _severity_for_failures(failed_steps: List[str]) -> str:
    critical_tokens = {"login-api", "dashboard-api", "executive-api", "export-csv", "export-pdf"}
    return "critical" if any(step in critical_tokens for step in failed_steps) else "warning"


async def _execute_checks(base_url: str, request_timeout_seconds: float = 12.0) -> Dict[str, Any]:
    def html_shell_validator(resp, payload, text):
        body = (resp.text or "")[:4000].lower()
        return resp.status_code < 400 and len(resp.text or "") > 20000 and "server error" not in body and "cannot get /" not in body

    def login_page_validator(resp, payload, text):
        return html_shell_validator(resp, payload, text)

    def login_session_validator(resp, payload, text):
        return isinstance(payload, dict) and bool((payload or {}).get("user_id"))

    def login_api_validator(resp, payload, text):
        if not isinstance(payload, dict):
            return False
        if bool(payload.get("requires_2fa")):
            return False
        return bool(payload.get("session_token") or payload.get("token") or payload.get("access_token"))

    def dashboard_validator(resp, payload, text):
        return isinstance(payload, dict) and bool(payload)

    def exec_validator(resp, payload, text):
        return isinstance(payload, dict) and bool(payload)

    def idv_validator(resp, payload, text):
        return isinstance(payload, dict) and bool(payload.get("overview"))

    def learning_center_validator(resp, payload, text):
        return isinstance(payload, dict) and isinstance(payload.get("enrollments"), list)

    def certificates_validator(resp, payload, text):
        return isinstance(payload, dict) and isinstance(payload.get("certificates"), list)

    def csv_validator(resp, payload, text):
        return resp.status_code == 200 and ("csv" in resp.headers.get("content-type", "") or len(resp.text) > 120)

    def pdf_validator(resp, payload, text):
        return resp.status_code == 200 and ("pdf" in resp.headers.get("content-type", "") or resp.content[:4] == b"%PDF")

    timeout_seconds = max(4.0, min(20.0, float(request_timeout_seconds or 12.0)))
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        login_page = await _probe(
            client,
            step_id="login-page",
            label="Login Page",
            method="GET",
            url=f"{base_url}/auth/login",
            validator=login_page_validator,
        )
        admin_password = _default_admin_password()
        login_api = {
            "id": "login-api",
            "label": "Admin Login API",
            "method": "POST",
            "path": f"{base_url}/api/auth/login",
            "status_code": 0,
            "latency_ms": 0,
            "healthy": False,
            "content_type": "",
            "details": {"error": "Missing TEST_ADMIN_PASSWORD/ADMIN_PASSWORD for monitor."},
            "payload": None,
        }

        token = ""
        if admin_password:
            login_api = await _probe(
                client,
                step_id="login-api",
                label="Admin Login API",
                method="POST",
                url=f"{base_url}/api/auth/login",
                json_body={"email": _default_admin_email(), "password": admin_password},
                validator=login_api_validator,
            )
            payload = login_api.get("payload") if isinstance(login_api, dict) else {}
            if isinstance(payload, dict):
                token = str(payload.get("session_token") or payload.get("token") or payload.get("access_token") or "")

        if not token:
            token = await _mint_synthetic_admin_session()
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

        login_session = await _probe(
            client,
            step_id="login-session",
            label="Synthetic Admin Session",
            method="GET",
            url=f"{base_url}/api/auth/me",
            headers=auth_headers,
            validator=login_session_validator,
        )
        probe_coroutines = {
            "dashboard_shell": _probe(
                client,
                step_id="dashboard-shell",
                label="Dashboard Route",
                method="GET",
                url=f"{base_url}/dashboard",
                validator=html_shell_validator,
            ),
            "dashboard_api": _probe(
                client,
                step_id="dashboard-api",
                label="Dashboard Stats",
                method="GET",
                url=f"{base_url}/api/home/dashboard-stats",
                headers=auth_headers,
                validator=dashboard_validator,
            ),
            "executive_shell": _probe(
                client,
                step_id="executive-shell",
                label="Executive Dashboard Route",
                method="GET",
                url=f"{base_url}/executive-dashboard?section=id-checker",
                validator=html_shell_validator,
            ),
            "executive_alias_shell": _probe(
                client,
                step_id="executive-shell-tab-alias",
                label="Executive Dashboard Alias Route",
                method="GET",
                url=f"{base_url}/executive-dashboard?tab=email-templates",
                validator=html_shell_validator,
            ),
            "executive_api": _probe(
                client,
                step_id="executive-api",
                label="Executive Overview",
                method="GET",
                url=f"{base_url}/api/admin/executive/overview",
                headers=auth_headers,
                validator=exec_validator,
            ),
            "idv_api": _probe(
                client,
                step_id="idv-api",
                label="ID Checker Dashboard",
                method="GET",
                url=f"{base_url}/api/id-checker/admin/dashboard",
                headers=auth_headers,
                validator=idv_validator,
            ),
            "export_csv": _probe(
                client,
                step_id="export-csv",
                label="IDV CSV Export",
                method="GET",
                url=f"{base_url}/api/id-checker/admin/export/csv",
                params={"token": token},
                validator=csv_validator,
            ),
            "export_pdf": _probe(
                client,
                step_id="export-pdf",
                label="IDV PDF Export",
                method="GET",
                url=f"{base_url}/api/id-checker/admin/export/pdf",
                params={"token": token},
                validator=pdf_validator,
            ),
            "learning_hub_shell": _probe(
                client,
                step_id="learning-hub-shell",
                label="AI Learning Hub Route",
                method="GET",
                url=f"{base_url}/ai-learning-hub?tab=journey&filter=all",
                validator=html_shell_validator,
            ),
            "learning_center_api": _probe(
                client,
                step_id="learning-center-api",
                label="Learning Center API",
                method="GET",
                url=f"{base_url}/api/ai-learn/my-learning-center",
                headers=auth_headers,
                validator=learning_center_validator,
            ),
            "certificate_gallery_shell": _probe(
                client,
                step_id="certificate-gallery-shell",
                label="Certificate Gallery Route",
                method="GET",
                url=f"{base_url}/certificate-gallery",
                validator=html_shell_validator,
            ),
            "certificates_api": _probe(
                client,
                step_id="certificates-api",
                label="Certificates API",
                method="GET",
                url=f"{base_url}/api/ai-learn/certificates",
                headers=auth_headers,
                validator=certificates_validator,
            ),
        }
        probe_results = await asyncio.gather(*probe_coroutines.values())
        result_map = dict(zip(probe_coroutines.keys(), probe_results))

        dashboard_shell = result_map["dashboard_shell"]
        dashboard_api = result_map["dashboard_api"]
        executive_shell = result_map["executive_shell"]
        executive_alias_shell = result_map["executive_alias_shell"]
        executive_api = result_map["executive_api"]
        idv_api = result_map["idv_api"]
        export_csv = result_map["export_csv"]
        export_pdf = result_map["export_pdf"]
        learning_hub_shell = result_map["learning_hub_shell"]
        learning_center_api = result_map["learning_center_api"]
        certificate_gallery_shell = result_map["certificate_gallery_shell"]
        certificates_api = result_map["certificates_api"]

        verifier_steps = []
        cert_payload = certificates_api.get("payload") if isinstance(certificates_api, dict) else None
        certificates = cert_payload.get("certificates") if isinstance(cert_payload, dict) else []
        if certificates:
            verification_id = str((certificates[0] or {}).get("verification_id") or "")
            if verification_id:
                certificate_verifier_shell = await _probe(
                    client,
                    step_id="certificate-verifier-shell",
                    label="Certificate Detail Route",
                    method="GET",
                    url=f"{base_url}/certificate-verify/{verification_id}",
                    validator=html_shell_validator,
                )
                verifier_steps.append(certificate_verifier_shell)

    journeys = [
        _build_journey("login", "Login", [login_page, login_api, login_session]),
        _build_journey("dashboard", "Dashboard", [dashboard_shell, dashboard_api]),
        _build_journey("executive-dashboard", "Executive Dashboard", [executive_shell, executive_alias_shell, executive_api, idv_api]),
        _build_journey("exports", "Exports", [export_csv, export_pdf]),
        _build_journey("learning-hub", "AI Learning Hub", [learning_hub_shell, learning_center_api]),
        _build_journey("certificates", "Certificates", [certificate_gallery_shell, certificates_api, *verifier_steps]),
    ]

    failed_journeys = [journey["journey_id"] for journey in journeys if journey["status"] != "healthy"]
    failed_steps = [step["id"] for journey in journeys for step in journey["steps"] if not step.get("healthy")]
    return {
        "journeys": journeys,
        "summary": {
            "journey_count": len(journeys),
            "healthy_journeys": sum(1 for journey in journeys if journey["status"] == "healthy"),
            "failed_journeys": failed_journeys,
            "failed_steps": failed_steps,
            "final_status": "healthy" if not failed_journeys else "failing",
            "severity": _severity_for_failures(failed_steps) if failed_steps else "info",
        },
    }


async def _attempt_auto_heal(failed_journeys: List[str]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []

    if not failed_journeys:
        return actions

    if "login" in failed_journeys:
        try:
            from scheduler_jobs import scheduled_auth_fallback_link_guardian

            await scheduled_auth_fallback_link_guardian()
            actions.append({
                "action": "auth_fallback_link_guardian",
                "status": "applied",
                "scope": "login",
                "message": "Canonical auth fallback guardian revalidated login resilience.",
            })
        except Exception as exc:
            actions.append({
                "action": "auth_fallback_link_guardian",
                "status": "failed",
                "scope": "login",
                "message": str(exc)[:180],
            })

    if any(journey in failed_journeys for journey in ["dashboard", "executive-dashboard", "exports", "learning-hub", "certificates"]):
        try:
            from scheduler_jobs import scheduled_platform_cache_freshness_guard

            await scheduled_platform_cache_freshness_guard()
            state = await db.system_runtime_flags.find_one({"key": "platform_cache_freshness_state"}, {"_id": 0}) or {}
            value = state.get("value") or {}
            actions.append({
                "action": "platform_cache_freshness_guard",
                "status": "applied",
                "scope": "shell-and-exports",
                "message": f"Frontend freshness guard ran. rebuilt={value.get('frontend_rebuilt', False)} issues={value.get('active_issue_count', 0)}",
            })
        except Exception as exc:
            actions.append({
                "action": "platform_cache_freshness_guard",
                "status": "failed",
                "scope": "shell-and-exports",
                "message": str(exc)[:180],
            })

    return actions


async def _notify_admins(alert_type: str, severity: str, title: str, message: str, metadata: Dict[str, Any]):
    try:
        from routes.admin_push_notifications import emit_realtime_alert

        await emit_realtime_alert(alert_type=alert_type, severity=severity, title=title, message=message)
    except Exception:
        pass

    admin_users = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
    now_iso = _now_iso()
    for admin in admin_users:
        user_id = str(admin.get("user_id") or "")
        if not user_id:
            continue
        await db.notifications.insert_one({
            "id": f"{alert_type}_{user_id}_{int(datetime.now(timezone.utc).timestamp())}",
            "user_id": user_id,
            "type": alert_type,
            "title": title,
            "message": message,
            "read": False,
            "created_at": now_iso,
            "metadata": _isoify(metadata),
        })


async def _sync_incident_state(run_doc: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    summary = run_doc.get("summary") or {}
    failed_steps = summary.get("failed_steps") or []
    failed_journeys = summary.get("failed_journeys") or []
    final_status = summary.get("final_status") or "healthy"
    failure_signature = "|".join(sorted(failed_steps))
    state = await db.system_runtime_flags.find_one({"key": STATE_KEY}, {"_id": 0}) or {}
    previous_status = str((state.get("value") or {}).get("status") or "unknown")

    open_incidents = await db[INCIDENTS_COLLECTION].find(
        {"status": {"$in": ["open", "acknowledged"]}},
        {"_id": 0},
    ).sort("detected_at", -1).to_list(20)

    latest_incident: Optional[Dict[str, Any]] = None
    if final_status == "healthy":
        for incident in open_incidents:
            await db[INCIDENTS_COLLECTION].update_one(
                {"incident_id": incident["incident_id"]},
                {"$set": {"status": "resolved", "resolved_at": now_iso, "resolution_note": "Recovered by monitor validation."}},
            )
        if previous_status in {"failing", "healed"}:
            await _notify_admins(
                alert_type="critical_journey_monitor_recovered",
                severity="info",
                title="Critical Journey Monitor Recovered",
                message="Login, dashboard, executive dashboard, and export journeys are healthy again.",
                metadata={"run_id": run_doc.get("run_id")},
            )
    else:
        cooldown_cutoff = now - timedelta(minutes=int(config.get("incident_cooldown_minutes", 20) or 20))
        latest_incident = await db[INCIDENTS_COLLECTION].find_one(
            {
                "failure_signature": failure_signature,
                "status": {"$in": ["open", "acknowledged"]},
                "detected_at": {"$gte": cooldown_cutoff.isoformat()},
            },
            {"_id": 0},
        )
        if latest_incident:
            await db[INCIDENTS_COLLECTION].update_one(
                {"incident_id": latest_incident["incident_id"]},
                {
                    "$set": {
                        "last_seen_at": now_iso,
                        "latest_run_id": run_doc.get("run_id"),
                        "failed_steps": failed_steps,
                        "failed_journeys": failed_journeys,
                        "auto_heal_actions": run_doc.get("auto_heal_actions") or [],
                    },
                    "$inc": {"occurrence_count": 1},
                },
            )
        else:
            incident_id = f"cjm_{uuid.uuid4().hex[:10]}"
            latest_incident = {
                "incident_id": incident_id,
                "status": "open",
                "severity": summary.get("severity", "warning"),
                "failure_signature": failure_signature,
                "failed_steps": failed_steps,
                "failed_journeys": failed_journeys,
                "detected_at": now_iso,
                "last_seen_at": now_iso,
                "latest_run_id": run_doc.get("run_id"),
                "auto_heal_actions": run_doc.get("auto_heal_actions") or [],
                "occurrence_count": 1,
                "title": "Critical journey regression detected",
                "message": f"Failed journeys: {', '.join(failed_journeys) if failed_journeys else 'unknown'}",
            }
            await db[INCIDENTS_COLLECTION].insert_one({**latest_incident})
            if config.get("notify_admins", True):
                await _notify_admins(
                    alert_type="critical_journey_monitor_incident",
                    severity=latest_incident["severity"],
                    title="Critical Journey Regression Detected",
                    message=latest_incident["message"],
                    metadata={"incident_id": incident_id, "failed_steps": failed_steps, "failed_journeys": failed_journeys},
                )

    state_value = {
        "status": final_status,
        "previous_status": previous_status,
        "last_run_at": now_iso,
        "failed_steps": failed_steps,
        "failed_journeys": failed_journeys,
        "latest_run_id": run_doc.get("run_id"),
        "latest_incident_id": (latest_incident or {}).get("incident_id"),
    }
    await db.system_runtime_flags.update_one(
        {"key": STATE_KEY},
        {"$set": {"key": STATE_KEY, "value": state_value, "updated_at": now_iso}},
        upsert=True,
    )
    return state_value


async def run_critical_journey_monitor_cycle(triggered_by: str = "manual", base_url_override: Optional[str] = None) -> Dict[str, Any]:
    config = await _get_config()
    if not config.get("enabled", True):
        return {
            "triggered_by": triggered_by,
            "status": "disabled",
            "config": config,
            "timestamp": _now_iso(),
        }

    run_id = f"cjm_run_{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc)
    resolved_base_url = _normalize_base_url(str(base_url_override or "")) or await _resolve_base_url(config)
    timeout_seconds = float(config.get("request_timeout_seconds") or 12)
    initial_result = await _execute_checks(resolved_base_url, request_timeout_seconds=timeout_seconds)
    auto_heal_actions: List[Dict[str, Any]] = []
    final_result = initial_result

    if initial_result["summary"]["failed_journeys"] and config.get("auto_heal_enabled", True):
        auto_heal_actions = await _attempt_auto_heal(initial_result["summary"]["failed_journeys"])
        if auto_heal_actions:
            await asyncio.sleep(1.0)
            final_result = await _execute_checks(resolved_base_url, request_timeout_seconds=timeout_seconds)
            if initial_result["summary"]["failed_journeys"] and not final_result["summary"]["failed_journeys"]:
                final_result["summary"]["final_status"] = "healed"

    completed_at = datetime.now(timezone.utc)
    run_doc = {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "base_url": resolved_base_url,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000, 1),
        "summary": final_result["summary"],
        "journeys": final_result["journeys"],
        "initial_summary": initial_result["summary"],
        "auto_heal_actions": auto_heal_actions,
        "config_snapshot": {key: config[key] for key in DEFAULT_CONFIG.keys()},
    }
    await db[RUNS_COLLECTION].insert_one({**run_doc})
    await db[RUNS_COLLECTION].delete_many({"started_at": {"$lt": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()}})
    await _sync_incident_state(run_doc, config)
    return run_doc


@router.get("/status")
async def get_monitor_status(request: Request):
    await require_admin(request)
    config = await _get_config()
    resolved_base_url = await _resolve_base_url(config, request)
    latest_run = await db[RUNS_COLLECTION].find_one({}, {"_id": 0})
    if latest_run is None:
        latest_run = await db[RUNS_COLLECTION].find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    else:
        latest_run = await db[RUNS_COLLECTION].find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    open_incidents = await db[INCIDENTS_COLLECTION].find({"status": {"$in": ["open", "acknowledged"]}}, {"_id": 0}).sort("detected_at", -1).limit(5).to_list(5)
    counts = {
        "total_runs": await db[RUNS_COLLECTION].count_documents({}),
        "open_incidents": await db[INCIDENTS_COLLECTION].count_documents({"status": {"$in": ["open", "acknowledged"]}}),
        "resolved_incidents": await db[INCIDENTS_COLLECTION].count_documents({"status": "resolved"}),
    }
    state = await db.system_runtime_flags.find_one({"key": STATE_KEY}, {"_id": 0}) or {}
    return {
        "config": config,
        "resolved_base_url": resolved_base_url,
        "counts": counts,
        "current_state": _isoify(state.get("value") or {}),
        "latest_run": _isoify(latest_run or {}),
        "open_incidents": _isoify(open_incidents),
        "timestamp": _now_iso(),
    }


@router.get("/runs")
async def list_runs(request: Request, limit: int = 20):
    await require_admin(request)
    docs = await db[RUNS_COLLECTION].find({}, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)
    return {"runs": _isoify(docs), "count": len(docs)}


@router.get("/incidents")
async def list_incidents(request: Request, limit: int = 20, status: Optional[str] = None):
    await require_admin(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    docs = await db[INCIDENTS_COLLECTION].find(query, {"_id": 0}).sort("detected_at", -1).limit(limit).to_list(limit)
    return {"incidents": _isoify(docs), "count": len(docs)}


@router.get("/config")
async def get_config(request: Request):
    await require_admin(request)
    return await _get_config()


@router.post("/config")
async def update_config(request: Request, body: MonitorConfigUpdate):
    await require_admin(request)
    await _get_config()
    updates = {key: value for key, value in body.model_dump().items() if value is not None}
    if "base_url_override" in updates:
        updates["base_url_override"] = _normalize_base_url(str(updates.get("base_url_override") or ""))
    if "request_timeout_seconds" in updates:
        try:
            timeout_val = float(updates.get("request_timeout_seconds") or 12)
        except Exception:
            timeout_val = 12
        updates["request_timeout_seconds"] = max(4.0, min(20.0, round(timeout_val, 1)))
    if updates:
        updates["updated_at"] = _now_iso()
        await db[CONFIG_COLLECTION].update_one({"_id": "config"}, {"$set": updates}, upsert=True)
    return await _get_config()


@router.post("/run-now")
async def run_now(request: Request):
    await require_admin(request)
    config = await _get_config()
    request_base_url = _request_base_url(request)
    should_override_from_request = bool(request_base_url and _is_preview_url(request_base_url))
    if should_override_from_request and request_base_url != str(config.get("base_url_override") or ""):
        await db[CONFIG_COLLECTION].update_one(
            {"_id": "config"},
            {
                "$set": {
                    "base_url_override": request_base_url,
                    "updated_at": _now_iso(),
                }
            },
            upsert=True,
        )
    return await run_critical_journey_monitor_cycle(
        triggered_by="admin:run-now",
        base_url_override=request_base_url if should_override_from_request else None,
    )


@router.post("/incidents/resolve")
async def resolve_incident(request: Request, body: IncidentResolveBody):
    await require_admin(request)
    result = await db[INCIDENTS_COLLECTION].update_one(
        {"incident_id": body.incident_id},
        {"$set": {"status": "resolved", "resolved_at": _now_iso(), "resolution_note": body.resolution_note or "Resolved by admin."}},
    )
    if result.matched_count == 0:
        return {"detail": "Incident not found", "status": "missing"}
    return {"status": "resolved", "incident_id": body.incident_id}
