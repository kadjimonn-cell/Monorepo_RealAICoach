"""
Global System Directive — Runtime Enforcement Middleware
---------------------------------------------------------
Applies §12 of /app/memory/GTEC_DIRECTIVE.md at the HTTP layer:

1. Fails the boot if the canonical directive file is missing or empty
   (so the platform cannot start in a non-compliant state).
2. Stamps every admin API response with:
       X-GTEC-Directive-Version     — SHA-256 hex[:16] of the directive body
       X-GTEC-Directive-Status      — ALWAYS-ACTIVE
3. Exposes a public read-only state endpoint so the status is observable
   across the whole platform (not just admin surfaces).

The directive body is read once at startup and cached in-process. A file
mtime watchdog reloads it if the canonical file is edited live.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

DIRECTIVE_FILE = Path("/app/memory/GTEC_DIRECTIVE.md")
PACKAGED_DIRECTIVE_FILE = Path(__file__).resolve().parent / "assets" / "gtec_directive_canonical.md"

_STATE: dict = {
    "loaded": False,
    "version": None,
    "loaded_at": None,
    "mtime": None,
    "byte_size": 0,
}


def _hash16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _read_packaged_directive() -> str:
    try:
        if PACKAGED_DIRECTIVE_FILE.exists():
            text = PACKAGED_DIRECTIVE_FILE.read_text(encoding="utf-8")
            if len(text.strip()) >= 200:
                return text
    except Exception:
        pass
    try:
        from gtec_directive_embedded import DIRECTIVE_TEXT

        if len(str(DIRECTIVE_TEXT).strip()) >= 200:
            return str(DIRECTIVE_TEXT)
    except Exception:
        pass
    return ""


def _restore_directive_from_package() -> bool:
    """Self-heal: restore canonical directive from the packaged copy.

    Production containers may not ship /app/memory. The packaged md copy and
    the embedded .py fallback always ship with backend code.
    """
    try:
        text = _read_packaged_directive()
        if not text:
            return False
        DIRECTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        DIRECTIVE_FILE.write_text(text, encoding="utf-8")
        logger.warning("GTEC directive restored from packaged copy -> %s", DIRECTIVE_FILE)
        return True
    except Exception as exc:
        logger.error("GTEC directive self-heal failed: %s", exc)
        return False


def enforce_directive_on_boot() -> dict:
    """Called from server startup. Refuses to boot on missing/empty file."""
    if not DIRECTIVE_FILE.exists() and not _restore_directive_from_package():
        raise RuntimeError(
            f"FATAL: Global System Directive missing at {DIRECTIVE_FILE}. "
            "Refusing to start — the platform must not run in a non-compliant state."
        )
    try:
        text = DIRECTIVE_FILE.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"FATAL: cannot read directive: {exc}") from exc
    if len(text.strip()) < 200:
        if _restore_directive_from_package():
            text = DIRECTIVE_FILE.read_text(encoding="utf-8")
        if len(text.strip()) < 200:
            raise RuntimeError(
                "FATAL: Global System Directive file is truncated (<200 chars). "
                "Refusing to start."
            )
    import time as _t
    _STATE.update({
        "loaded": True,
        "version": _hash16(text[:4000]),
        "loaded_at": _t.time(),
        "mtime": DIRECTIVE_FILE.stat().st_mtime,
        "byte_size": len(text),
    })
    logger.info(
        "GTEC directive loaded: version=%s bytes=%s path=%s",
        _STATE["version"], _STATE["byte_size"], DIRECTIVE_FILE,
    )
    return dict(_STATE)


def _maybe_reload() -> None:
    """Cheap mtime check — reloads version if the file changed on disk."""
    try:
        m = DIRECTIVE_FILE.stat().st_mtime
    except FileNotFoundError:
        return  # startup guard would have prevented this; no-op
    if m != _STATE.get("mtime"):
        try:
            text = DIRECTIVE_FILE.read_text(encoding="utf-8")
            _STATE["version"] = _hash16(text[:4000])
            _STATE["mtime"] = m
            _STATE["byte_size"] = len(text)
            logger.info("GTEC directive reloaded: version=%s", _STATE["version"])
        except Exception as exc:  # pragma: no cover
            logger.warning("GTEC directive reload failed: %s", exc)


def get_directive_state() -> dict:
    return {
        "loaded": _STATE.get("loaded", False),
        "version": _STATE.get("version"),
        "byte_size": _STATE.get("byte_size", 0),
        "always_active": True,
        "non_disableable": True,
        "source": str(DIRECTIVE_FILE),
    }


class GtecDirectiveMiddleware(BaseHTTPMiddleware):
    """Stamp every API response with the directive version + status."""

    async def dispatch(self, request: Request, call_next) -> Response:
        _maybe_reload()
        response = await call_next(request)
        try:
            response.headers["X-GTEC-Directive-Version"] = str(_STATE.get("version") or "unknown")
            response.headers["X-GTEC-Directive-Status"] = "ALWAYS-ACTIVE"
        except Exception:
            pass
        return response


# Public read-only state endpoint (no auth — visibility is the point)
public_router = APIRouter()


@public_router.get("/gtec/directive/state")
async def gtec_directive_state_public():
    state = get_directive_state()
    if not state.get("loaded"):
        raise HTTPException(status_code=503, detail="Directive not loaded")
    return state
