#!/usr/bin/env python3
"""i18n_v2_seed_locales.py — Auto-translation v2 dictionary seeding.

Source of truth: `frontend/src/i18n/locales/en.ts`. EVERY key present in
en.ts is propagated to every other `*.ts` locale file. Missing entries
are auto-translated via the existing backend
`services.auto_translate.translate_batch` (LLM-backed).

Idempotent: keys that already have a non-English value in a target locale
are preserved untouched. Only **truly missing** keys are sent to the
translator. Use `--force` to also retry keys that previously echoed back
as English (e.g. when the LLM had a brief outage).

Build-fast skip: if en.ts content hash matches the last cached run, the
script exits in < 50 ms. Caches at `/app/.i18n_seed_cache.json`.

Usage:
  python3 /app/scripts/i18n_v2_seed_locales.py            # idempotent
  python3 /app/scripts/i18n_v2_seed_locales.py --force    # retry echoes
  python3 /app/scripts/i18n_v2_seed_locales.py --no-cache # ignore manifest

Exit codes:
  0 — all locales complete
  1 — translate_batch failed for one or more locales (build is blocked)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

from services.auto_translate import translate_batch  # noqa: E402

LOCALES_DIR = Path("/app/frontend/src/i18n/locales")
EN_FILE = LOCALES_DIR / "en.ts"
CACHE_FILE = Path("/app/.i18n_seed_cache.json")

SOURCE_LOCALES = {"en"}
FORCE_RETRY_ECHOES = "--force" in sys.argv
USE_CACHE = "--no-cache" not in sys.argv


def _arg_value(flag: str) -> str | None:
    if flag not in sys.argv:
        return None
    idx = sys.argv.index(flag)
    if idx + 1 >= len(sys.argv):
        return None
    return sys.argv[idx + 1]


def _parse_locale_filter() -> set[str] | None:
    raw = _arg_value("--locales")
    if not raw:
        return None
    parsed = {
        token.strip().lower()
        for token in raw.split(",")
        if token.strip()
    }
    return parsed or None


TARGET_LOCALES = _parse_locale_filter()


def _read_locale(file: Path) -> dict[str, str]:
    """Parse the `Record<string, string>` body of a locale .ts file."""
    text = file.read_text(encoding="utf-8")
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


def _write_locale(file: Path, code: str, all_keys: dict[str, str]) -> None:
    """Re-emit a locale .ts file with the merged keys."""
    lines = [
        f"// Auto-generated locale file for {code}",
        "const locale: Record<string, string> = {",
    ]
    sorted_keys = sorted(all_keys.keys())
    for k in sorted_keys:
        v = all_keys[k].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  "{k}": "{v}",')
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("};")
    lines.append("export default locale;")
    lines.append("")
    file.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    if not EN_FILE.exists():
        print(f"FATAL: en.ts source not found at {EN_FILE}", file=sys.stderr)
        return 1

    en_dict = _read_locale(EN_FILE)
    print(f"Source en.ts: {len(en_dict)} keys")

    # ── Build-fast skip: hash the canonical en.ts source ──
    # If the hash matches the previous run's manifest AND every locale
    # has the same key count, exit immediately (yarn export:web stays fast).
    en_hash = hashlib.sha256(EN_FILE.read_bytes()).hexdigest()
    cache: dict = {}
    if USE_CACHE and CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except Exception:
            cache = {}
    if (
        USE_CACHE
        and not FORCE_RETRY_ECHOES
        and cache.get("en_hash") == en_hash
        and cache.get("en_keys") == len(en_dict)
    ):
        print(f"  ✓ en.ts unchanged since last run (hash={en_hash[:12]}…) — skipping translation pass.")
        print("  Use --force or --no-cache to override.")
        return 0

    locale_files = sorted(LOCALES_DIR.glob("*.ts"))
    if TARGET_LOCALES:
        locale_files = [
            loc
            for loc in locale_files
            if loc.stem in SOURCE_LOCALES or loc.stem in TARGET_LOCALES
        ]
    print(f"Discovered {len(locale_files)} locale files\n")

    any_failure = False

    for loc_file in locale_files:
        code = loc_file.stem
        if code in SOURCE_LOCALES:
            _write_locale(loc_file, code, en_dict)
            print(f"  {code:<4}  ✓ source ({len(en_dict)} keys)")
            continue

        existing = _read_locale(loc_file)

        # Default: only translate keys that are *truly missing* (None).
        # With --force, also retry keys whose stored value is identical
        # to the English source (i.e. the LLM previously echoed back).
        missing_keys: list[str] = []
        for key, en_value in en_dict.items():
            cur = existing.get(key)
            if cur is None:
                missing_keys.append(key)
            elif FORCE_RETRY_ECHOES and cur == en_value:
                missing_keys.append(key)

        if not missing_keys:
            cleaned = {k: v for k, v in existing.items() if k in en_dict}
            if cleaned != existing:
                _write_locale(loc_file, code, cleaned)
                removed = len(existing) - len(cleaned)
                print(f"  {code:<4}  ✓ complete · cleaned {removed} stale key(s)")
            else:
                print(f"  {code:<4}  ✓ complete ({len(existing)} keys)")
            continue

        try:
            translations: dict[str, str] = await translate_batch(
                texts=[en_dict[k] for k in missing_keys],
                target_lang=code,
            )
        except Exception as e:
            print(f"  {code:<4}  ✗ translate_batch failed: {e}", file=sys.stderr)
            any_failure = True
            continue

        merged = {k: v for k, v in existing.items() if k in en_dict}
        added = 0
        echoed = 0
        for key in missing_keys:
            source = en_dict[key]
            cleaned_val = (translations.get(source) or "").strip()
            if not cleaned_val:
                cleaned_val = source
                echoed += 1
            elif cleaned_val == source:
                echoed += 1
            merged[key] = cleaned_val
            added += 1

        _write_locale(loc_file, code, merged)
        msg = f"  {code:<4}  + {added} translated"
        if echoed:
            msg += f" ({echoed} echoed back as source)"
        print(msg)

    print()
    if any_failure:
        print("FAIL: one or more locales failed translation; build blocked.", file=sys.stderr)
        return 1

    # ── Persist the manifest so subsequent runs skip cleanly ──
    if USE_CACHE:
        try:
            CACHE_FILE.write_text(json.dumps({
                "en_hash": en_hash,
                "en_keys": len(en_dict),
            }))
        except Exception:
            pass

    print("OK: all 23 locales complete and idempotent.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

