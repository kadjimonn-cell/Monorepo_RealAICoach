"""GET /api/admin/i18n/coverage — per-locale i18n coverage telemetry.

Reads `frontend/src/i18n/locales/en.ts` as the source of truth and
compares every other locale file against it. Returns:

  - total_locales / total_keys (en)
  - per-locale counts: total_keys, translated, echoed, missing, coverage_pct
  - aggregate coverage_pct across all non-source locales
  - manifest hash + timestamp of `/app/.i18n_seed_cache.json`
  - "drift" flag if any locale is < 100 % coverage

Designed for the executive dashboard's i18n coverage badge.

Why this is read-only and cheap:
  - No LLM calls.
  - No DB writes.
  - Pure regex parse of locale .ts files (~50 ms total for 23 files).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from routes.db import require_admin

router = APIRouter()

LOCALES_DIR = Path("/app/frontend/src/i18n/locales")
EN_FILE = LOCALES_DIR / "en.ts"
CACHE_FILE = Path("/app/.i18n_seed_cache.json")
SOURCE_LOCALES = {"en"}
KNOWN_DYNAMIC_RUNTIME_KEYS = {"language.syncing"}


def _read_locale(file: Path) -> dict[str, str]:
    """Pure regex parse — same shape as the seed script."""
    try:
        text = file.read_text(encoding="utf-8")
    except Exception:
        return {}
    body = re.search(r"=\s*\{([\s\S]*?)\};", text)
    if not body:
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(
        r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', body.group(1)
    ):
        key = m.group(1)
        value = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        out[key] = value
    return out


def _compute_locale_stats(en_dict: dict[str, str], target: dict[str, str]) -> dict[str, Any]:
    """Stats for a single non-English locale relative to en.ts."""
    total = len(en_dict)
    if total == 0:
        return {"total_keys": 0, "translated": 0, "echoed": 0, "missing": 0, "coverage_pct": 100.0}
    translated = 0
    echoed = 0
    missing = 0
    for key, en_val in en_dict.items():
        if key in KNOWN_DYNAMIC_RUNTIME_KEYS:
            continue
        cur = target.get(key)
        if cur is None:
            missing += 1
        elif cur == en_val:
            echoed += 1
        else:
            translated += 1
    coverage_pct = round(translated / total * 100.0, 1)
    return {
        "total_keys": total,
        "translated": translated,
        "echoed": echoed,
        "missing": missing,
        "coverage_pct": coverage_pct,
    }


@router.get("/admin/i18n/coverage")
async def get_i18n_coverage(request: Request) -> dict[str, Any]:
    """Return per-locale + aggregate coverage. Admin-only (no PII; just
    counts — but admin-gated so attackers can't fingerprint untranslated
    strings to predict default-locale fallback paths)."""
    await require_admin(request)

    en_dict = _read_locale(EN_FILE)
    en_keys = len(en_dict)
    en_hash = hashlib.sha256(EN_FILE.read_bytes()).hexdigest() if EN_FILE.exists() else None

    locales: dict[str, dict[str, Any]] = {}
    locale_files = sorted(LOCALES_DIR.glob("*.ts"))
    drift_locales: list[str] = []
    full_locales: list[str] = []

    total_translated = 0
    total_echoed = 0
    total_missing = 0
    total_expected = 0

    for f in locale_files:
        code = f.stem
        if code in SOURCE_LOCALES:
            locales[code] = {
                "total_keys": en_keys,
                "translated": en_keys,
                "echoed": 0,
                "missing": 0,
                "coverage_pct": 100.0,
                "is_source": True,
            }
            continue
        target = _read_locale(f)
        stats = _compute_locale_stats(en_dict, target)
        locales[code] = stats
        total_translated += stats["translated"]
        total_echoed += stats["echoed"]
        total_missing += stats["missing"]
        total_expected += stats["total_keys"]
        if stats["coverage_pct"] >= 100.0:
            full_locales.append(code)
        else:
            drift_locales.append(code)

    aggregate_pct = (
        round(total_translated / total_expected * 100.0, 1)
        if total_expected else 100.0
    )
    structural_pct = (
        round(((total_expected - total_missing) / total_expected) * 100.0, 1)
        if total_expected else 100.0
    )

    # Manifest cache (from seed script) — surfaces last successful seed run.
    manifest: dict[str, Any] = {}
    if CACHE_FILE.exists():
        try:
            manifest = json.loads(CACHE_FILE.read_text())
        except Exception:
            manifest = {}

    # Health pill colour used by the dashboard:
    #   GREEN  ≥ 99 %        (≤ 1 % drift across all locales)
    #   AMBER  90 % – 98.9 % (visible drift, build still passes)
    #   RED    < 90 %        (significant drift; likely failing translate_batch)
    if aggregate_pct >= 99.0 and not drift_locales:
        health = "green"
    elif aggregate_pct >= 90.0:
        health = "amber"
    else:
        health = "red"

    # Structural parity health (for release gating):
    #   GREEN  = no missing keys + >= 99%
    #   AMBER  = low missing-key drift but still recoverable
    #   RED    = meaningful missing-key risk (broken fallback chains)
    if total_missing == 0 and structural_pct >= 99.0:
        structural_health = "green"
    elif structural_pct >= 95.0:
        structural_health = "amber"
    else:
        structural_health = "red"

    return {
        "ok": True,
        "source_locale": "en",
        "source_keys": en_keys,
        "source_hash": en_hash,
        "total_locales": len(locale_files),
        "non_source_locales": len(locale_files) - len(SOURCE_LOCALES),
        "aggregate_coverage_pct": aggregate_pct,
        "translation_coverage_pct": aggregate_pct,
        "structural_coverage_pct": structural_pct,
        "missing_keys_total": total_missing,
        "echoed_keys_total": total_echoed,
        "drift_locales": sorted(drift_locales),
        "full_locales": sorted(full_locales),
        "health": health,
        "structural_health": structural_health,
        "manifest": {
            "en_hash": manifest.get("en_hash"),
            "en_keys": manifest.get("en_keys"),
            "in_sync_with_source": (
                manifest.get("en_hash") == en_hash and en_hash is not None
            ),
        },
        "locales": locales,
    }
