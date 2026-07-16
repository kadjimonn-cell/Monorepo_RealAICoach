"""Global PDF v15 policy middleware.

Enforces runtime outbound PDF v15 theme policy across pre-existing/current/
future PDF responses without endpoint-by-endpoint edits.

Note: PDF 1.4 normalization is intentionally disabled by platform policy.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from reportlab.pdfgen import canvas
from services.pdf_v15_theme import draw_page_chrome

try:
    from dotenv import dotenv_values
except Exception:  # pragma: no cover
    dotenv_values = None

logger = logging.getLogger("pdf_policy")

PDF_THEME_SIGNATURE = "pdf-v15-global-runtime-visual-stamp-v2"
PDF_THEME_METADATA_KEY = "/RACPDFTheme"
PDF_THEME_VISUAL_MODE_KEY = "/RACPDFThemeVisualMode"
LEARNING_CERTIFICATE_THEME_EXEMPT_MODE = "learning_certificate_exempt"

_MONGO_CLIENT: AsyncIOMotorClient | None = None
_MONGO_DB = None
_ALERT_COOLDOWN_SECONDS = int(os.environ.get("PDF_THEME_BLOCK_ALERT_COOLDOWN_SECONDS", "600"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _get_pdf_policy_db():
    """Lazy DB handle used by telemetry (best effort, never blocking policy)."""
    global _MONGO_CLIENT, _MONGO_DB
    if _MONGO_DB is not None:
        return _MONGO_DB

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if (not mongo_url or not db_name) and dotenv_values is not None:
        try:
            cfg = dotenv_values("/app/backend/.env")
            mongo_url = mongo_url or cfg.get("MONGO_URL")
            db_name = db_name or cfg.get("DB_NAME")
        except Exception:
            pass
    if not mongo_url or not db_name:
        return None

    try:
        _MONGO_CLIENT = AsyncIOMotorClient(mongo_url)
        _MONGO_DB = _MONGO_CLIENT[db_name]
    except Exception:
        logger.exception("pdf-policy: failed to initialize telemetry DB")
        return None
    return _MONGO_DB


def _header_value(headers: Iterable[tuple[bytes, bytes]], key: str) -> str:
    key_b = key.lower().encode("latin1")
    for k, v in headers:
        if k.lower() == key_b:
            return v.decode("latin1", errors="ignore")
    return ""


def _replace_header(headers: list[tuple[bytes, bytes]], key: str, value: str) -> list[tuple[bytes, bytes]]:
    key_b = key.lower().encode("latin1")
    out: list[tuple[bytes, bytes]] = []
    replaced = False
    for k, v in headers:
        if k.lower() == key_b:
            if not replaced:
                out.append((key_b, value.encode("latin1")))
                replaced = True
            continue
        out.append((k, v))
    if not replaced:
        out.append((key_b, value.encode("latin1")))
    return out


def _drop_header(headers: list[tuple[bytes, bytes]], key: str) -> list[tuple[bytes, bytes]]:
    key_b = key.lower().encode("latin1")
    return [(k, v) for (k, v) in headers if k.lower() != key_b]


def _is_learning_certificate_pdf_theme_exempt_path(path: str) -> bool:
    normalized = f"/{str(path or '').strip('/').lower()}"
    return "/ai-learn/certificates/" in normalized and normalized.endswith("/pdf/file")


JOB_SEARCH_DOCUMENT_THEME_EXEMPT_MODE = "job_search_document_exempt"


def _is_job_search_document_pdf_theme_exempt_path(path: str) -> bool:
    """Job Search CV/cover-letter PDFs go to external employers — no platform chrome."""
    normalized = f"/{str(path or '').strip('/').lower()}"
    return "/job-search/documents/" in normalized and normalized.endswith("/pdf")


TRAVEL_VISA_CERTIFICATE_THEME_EXEMPT_MODE = "travel_visa_certificate_exempt"


def _is_travel_visa_certificate_pdf_theme_exempt_path(path: str) -> bool:
    """Travel Visa certificates carry their own certificate-grade chrome — no v15 overlay."""
    normalized = f"/{str(path or '').strip('/').lower()}"
    return "/travel-visa/certificate/download/" in normalized


def _build_pdf_v15_visual_overlay(page_w: float, page_h: float, page_no: int) -> bytes:
    """Create a canonical v15 visual chrome overlay for one PDF page."""
    width = float(max(page_w, 160.0))
    height = float(max(page_h, 160.0))
    margin_x = max(16.0, min(30.0, width * 0.04))
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(width, height))

    draw_page_chrome(
        pdf,
        width=width,
        height=height,
        margin_x=margin_x,
        page_no=page_no,
        title="RealAICoach PDF v15",
        subtitle="Global runtime enterprise visual standard",
        right_primary="Policy: PDF v15",
        right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        badge_text="GLOBAL PDF V15 POLICY ACTIVE",
        badge_status="INFO",
        footer_text="RealAICoach • Global PDF v15 enterprise runtime stamp",
    )

    pdf.showPage()
    pdf.save()
    return out.getvalue()


def enforce_pdf_v14_bytes(payload: bytes) -> Tuple[bytes, str]:
    """Global no-op for deprecated version normalization policy.

    Runtime platform policy now enforces only PDF v15 theme. This helper is
    intentionally kept for backward compatibility with older call sites.
    """
    if not payload.startswith(b"%PDF-"):
        return payload, "non_pdf"
    return payload, "disabled_noop"


def enforce_pdf_v15_theme_bytes(payload: bytes) -> Tuple[bytes, str]:
    """RETIRED (2026-07, platform owner directive): global visual policy removed.

    PDFs are returned exactly as generated — no overlay, no metadata stamping.
    Signature kept for the 20+ existing call sites and legacy contracts.
    """
    if not payload.startswith(b"%PDF-"):
        return payload, "non_pdf"
    return payload, "policy_retired"


async def _record_pdf_policy_event(
    scope: dict,
    status: int,
    mode: str,
    theme_mode: str,
    content_type: str,
    original_header: str,
    normalized_header: str,
) -> None:
    db = _get_pdf_policy_db()
    if db is None:
        return

    route_path = str(scope.get("path") or "")
    method = str(scope.get("method") or "")
    ts = _now_iso()

    try:
        await db.pdf_policy_events.insert_one(
            {
                "route_path": route_path,
                "method": method,
                "status": int(status),
                "mode": mode,
                "theme_mode": theme_mode,
                "content_type": content_type,
                "original_header": original_header,
                "normalized_header": normalized_header,
                "enforced_at": ts,
            }
        )
        await db.pdf_policy_counters.update_one(
            {"route_path": route_path, "method": method},
            {
                "$setOnInsert": {
                    "route_path": route_path,
                    "method": method,
                    "created_at": ts,
                },
                "$set": {
                    "last_seen_at": ts,
                    "last_mode": mode,
                    "last_theme_mode": theme_mode,
                    "last_status": int(status),
                    "last_content_type": content_type,
                },
                "$inc": {
                    "total": 1,
                    f"mode_counts.{mode}": 1,
                    f"theme_mode_counts.{theme_mode}": 1,
                    f"status_counts.{int(status)}": 1,
                },
            },
            upsert=True,
        )
    except Exception:
        logger.exception("pdf-policy: telemetry write failed")


async def _emit_blocked_theme_alert(scope: dict, blocked_mode: str, detail: str = "") -> None:
    """Emit admin alert when blocked_* theme modes occur (cooldown protected)."""
    db = _get_pdf_policy_db()
    if db is None:
        logger.error("pdf-policy: blocked mode without DB telemetry: %s", blocked_mode)
        return

    route_path = str(scope.get("path") or "")
    method = str(scope.get("method") or "")
    ts = datetime.now(timezone.utc)
    ts_iso = ts.isoformat()
    alert_key = f"{method}:{route_path}:{blocked_mode}"

    should_notify = True
    try:
        state = await db.pdf_policy_alert_state.find_one({"alert_key": alert_key}, {"_id": 0, "last_sent_at": 1})
        last_sent_at = _parse_iso((state or {}).get("last_sent_at"))
        if last_sent_at and (ts - last_sent_at) < timedelta(seconds=max(60, _ALERT_COOLDOWN_SECONDS)):
            should_notify = False

        await db.pdf_policy_alert_events.insert_one(
            {
                "alert_key": alert_key,
                "route_path": route_path,
                "method": method,
                "blocked_mode": blocked_mode,
                "detail": detail,
                "triggered_at": ts_iso,
                "notified": should_notify,
            }
        )
    except Exception:
        logger.exception("pdf-policy: failed writing blocked alert events")
        return

    if not should_notify:
        try:
            await db.pdf_policy_alert_state.update_one(
                {"alert_key": alert_key},
                {
                    "$setOnInsert": {"alert_key": alert_key, "created_at": ts_iso},
                    "$set": {"last_seen_at": ts_iso, "last_mode": blocked_mode},
                    "$inc": {"suppressed_count": 1, "total": 1},
                },
                upsert=True,
            )
        except Exception:
            logger.exception("pdf-policy: failed updating suppressed alert state")
        return

    try:
        from utils.email_service import send_catalog_template, is_email_configured

        notify_result = {"attempted": 0, "sent": 0, "failed": 0}
        if is_email_configured():
            admins = await db.users.find(
                {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
                {"_id": 0, "email": 1, "name": 1},
            ).limit(12).to_list(12)

            for admin in admins:
                email = admin.get("email")
                if not email:
                    continue
                notify_result["attempted"] += 1
                res = await send_catalog_template(
                    recipient_email=email,
                    template_key="system_alert_admin",
                    recipient_name=admin.get("name") or "Admin",
                    alert_type="PDF v15 Theme Policy Blocked",
                    severity="CRITICAL",
                    description=(
                        f"A PDF response was blocked by strict policy mode. "
                        f"mode={blocked_mode}, route={method} {route_path}. {detail}".strip()
                    ),
                    component="PDF Policy Middleware",
                    timestamp=ts.strftime("%Y-%m-%d %H:%M UTC"),
                )
                if res.get("success"):
                    notify_result["sent"] += 1
                else:
                    notify_result["failed"] += 1

        await db.pdf_policy_alert_state.update_one(
            {"alert_key": alert_key},
            {
                "$setOnInsert": {"alert_key": alert_key, "created_at": ts_iso},
                "$set": {
                    "last_seen_at": ts_iso,
                    "last_mode": blocked_mode,
                    "last_sent_at": ts_iso,
                    "last_notify_result": notify_result,
                },
                "$inc": {"notify_count": 1, "total": 1},
            },
            upsert=True,
        )
    except Exception:
        logger.exception("pdf-policy: failed to notify blocked alert")


class PdfVersionPolicyMiddleware:
    """ASGI middleware that enforces global PDF v15 policy on PDF responses."""

    def __init__(self, app: Any):
        self.app = app
        self.strict_theme_enforcement = str(os.environ.get("PDF_THEME_STRICT_MODE", "true")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self.telemetry_enabled = str(os.environ.get("PDF_POLICY_TELEMETRY_ENABLED", "true")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

    async def __call__(self, scope: dict, receive: Any, send: Any):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start_message: dict | None = None
        captured_chunks: list[bytes] = []
        should_capture_pdf = False

        async def send_wrapper(message: dict):
            nonlocal start_message, should_capture_pdf

            msg_type = message.get("type")

            if msg_type == "http.response.start":
                headers = list(message.get("headers") or [])
                content_type = _header_value(headers, "content-type").lower()
                if "application/pdf" in content_type:
                    if _is_learning_certificate_pdf_theme_exempt_path(str(scope.get("path") or "")):
                        headers = _replace_header(headers, "x-pdf-theme-policy", "exempt-learning-certificate")
                        headers = _replace_header(headers, "x-pdf-theme-policy-mode", LEARNING_CERTIFICATE_THEME_EXEMPT_MODE)
                        message["headers"] = headers
                        await send(message)
                        return

                    if _is_job_search_document_pdf_theme_exempt_path(str(scope.get("path") or "")):
                        headers = _replace_header(headers, "x-pdf-theme-policy", "exempt-job-search-document")
                        headers = _replace_header(headers, "x-pdf-theme-policy-mode", JOB_SEARCH_DOCUMENT_THEME_EXEMPT_MODE)
                        message["headers"] = headers
                        await send(message)
                        return

                    if _is_travel_visa_certificate_pdf_theme_exempt_path(str(scope.get("path") or "")):
                        headers = _replace_header(headers, "x-pdf-theme-policy", "exempt-travel-visa-certificate")
                        headers = _replace_header(headers, "x-pdf-theme-policy-mode", TRAVEL_VISA_CERTIFICATE_THEME_EXEMPT_MODE)
                        message["headers"] = headers
                        await send(message)
                        return

                    should_capture_pdf = True
                    start_message = {
                        "type": "http.response.start",
                        "status": message.get("status", 200),
                        "headers": headers,
                    }
                    return

                await send(message)
                return

            if msg_type == "http.response.body" and should_capture_pdf:
                captured_chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return

                payload = b"".join(captured_chunks)
                themed, theme_mode = enforce_pdf_v15_theme_bytes(payload)
                mode = "theme_only"
                original_header = payload.splitlines()[0].decode("latin1", errors="ignore") if payload.startswith(b"%PDF-") else ""
                normalized_header = themed.splitlines()[0].decode("latin1", errors="ignore") if themed.startswith(b"%PDF-") else ""

                if start_message is None:
                    # Shouldn't happen, but fail safe.
                    await send({"type": "http.response.body", "body": themed, "more_body": False})
                    return

                if self.strict_theme_enforcement and theme_mode in {"theme_passthrough_error", "non_pdf"}:
                    blocked_mode = f"blocked_{theme_mode}"
                    fail_body = b'{"detail":"PDF v15 theme policy enforcement failed"}'
                    fail_headers = [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(fail_body)).encode("latin1")),
                        (b"x-pdf-theme-policy", b"enforced-v15"),
                        (b"x-pdf-theme-policy-mode", blocked_mode.encode("latin1")),
                    ]
                    await send({"type": "http.response.start", "status": 500, "headers": fail_headers})
                    await send({"type": "http.response.body", "body": fail_body, "more_body": False})
                    await _emit_blocked_theme_alert(
                        scope=scope,
                        blocked_mode=blocked_mode,
                        detail=f"content_type=application/pdf theme_mode={theme_mode}",
                    )
                    if self.telemetry_enabled:
                        await _record_pdf_policy_event(
                            scope=scope,
                            status=500,
                            mode=mode,
                            theme_mode=blocked_mode,
                            content_type="application/pdf",
                            original_header=original_header,
                            normalized_header=normalized_header,
                        )
                    return

                headers = list(start_message.get("headers") or [])
                content_type = _header_value(headers, "content-type")
                headers = _drop_header(headers, "content-length")
                headers = _replace_header(headers, "content-length", str(len(themed)))
                headers = _replace_header(headers, "x-pdf-theme-policy", "enforced-v15")
                headers = _replace_header(headers, "x-pdf-theme-policy-mode", theme_mode)

                start_message["headers"] = headers
                await send(start_message)
                await send({"type": "http.response.body", "body": themed, "more_body": False})
                if self.telemetry_enabled:
                    await _record_pdf_policy_event(
                        scope=scope,
                        status=int(start_message.get("status", 200)),
                        mode=mode,
                        theme_mode=theme_mode,
                        content_type=content_type,
                        original_header=original_header,
                        normalized_header=normalized_header,
                    )
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)
