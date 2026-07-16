"""i18n shared router and locale-file helpers."""

from fastapi import APIRouter
import re
import os
import json as jsonlib
from datetime import datetime
import logging

from ..db import db

from .constants import SUPPORTED_LANGUAGES

router = APIRouter(prefix="/i18n")
logger = logging.getLogger("routes.i18n")


def _normalize_lang(value: str) -> str:
    raw = (value or "en").strip().lower()
    if "-" in raw:
        raw = raw.split("-")[0]
    return raw if raw in SUPPORTED_LANGUAGES else "en"


def _guidance_copy(lang_code: str, suggested_lang: str, settings_url: str) -> dict:
    messages = {
        "en": {
            "title": "Language guidance available",
            "message": f"We detected a better language match ({suggested_lang.upper()}). Update your language in Settings for a fully localized experience.",
            "cta": "Open language settings",
        },
        "fr": {
            "title": "Suggestion de langue disponible",
            "message": f"Nous avons détecté une meilleure langue ({suggested_lang.upper()}). Mettez à jour votre langue dans les paramètres.",
            "cta": "Ouvrir les paramètres de langue",
        },
        "es": {
            "title": "Sugerencia de idioma disponible",
            "message": f"Detectamos una mejor coincidencia de idioma ({suggested_lang.upper()}). Actualiza tu idioma en Configuración.",
            "cta": "Abrir configuración de idioma",
        },
        "de": {
            "title": "Sprachhinweis verfügbar",
            "message": f"Wir haben eine bessere Sprache erkannt ({suggested_lang.upper()}). Aktualisiere deine Sprache in den Einstellungen.",
            "cta": "Spracheinstellungen öffnen",
        },
        "pt": {
            "title": "Sugestão de idioma disponível",
            "message": f"Detectamos um idioma mais adequado ({suggested_lang.upper()}). Atualize seu idioma nas Configurações.",
            "cta": "Abrir configurações de idioma",
        },
    }
    block = messages.get(lang_code, messages["en"])
    return {
        **block,
        "settings_url": settings_url,
    }


def _safe_parse_iso(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


_LOCALE_ENTRY_RE = re.compile(
    r'^\s*(["\'])([a-zA-Z][a-zA-Z0-9_.]+)\1:\s*(["\'])(.*?)(?<!\\)\3,?\s*$',
    re.MULTILINE,
)


def _i18n_locales_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "..",
        "frontend",
        "src",
        "i18n",
        "locales",
    )


def _i18n_locale_file_path(lang_code: str) -> str:
    return os.path.join(_i18n_locales_dir(), f"{lang_code}.ts")


def _decode_locale_value(raw: str, quote: str) -> str:
    try:
        if quote == '"':
            return str(jsonlib.loads(f'"{raw}"'))
    except Exception:
        pass
    if quote == "'":
        return raw.replace("\\'", "'").replace('\\"', '"')
    return raw


def _parse_locale_content(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _LOCALE_ENTRY_RE.finditer(content):
        quote = str(match.group(3) or '"')
        key = str(match.group(2) or "")
        raw_value = str(match.group(4) or "")
        if not key:
            continue
        out[key] = _decode_locale_value(raw_value, quote)
    return out


def _load_locale_map(lang_code: str) -> dict[str, str]:
    file_path = _i18n_locale_file_path(lang_code)
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as locale_file:
            return _parse_locale_content(locale_file.read())
    except Exception:
        return {}


def _load_all_locale_maps() -> dict[str, dict[str, str]]:
    locales_dir = _i18n_locales_dir()
    if not os.path.isdir(locales_dir):
        return {}

    lang_keys: dict[str, dict[str, str]] = {}
    for file_name in os.listdir(locales_dir):
        if not file_name.endswith(".ts"):
            continue
        lang_code = file_name.replace(".ts", "")
        if len(lang_code) != 2:
            continue
        lang_keys[lang_code] = _load_locale_map(lang_code)
    return lang_keys


def _escape_locale_value(value: str) -> str:
    return jsonlib.dumps(str(value), ensure_ascii=False)[1:-1]


def _write_locale_updates(lang_code: str, updates: dict[str, str], append_missing: bool = True) -> int:
    if not updates:
        return 0

    file_path = _i18n_locale_file_path(lang_code)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Locale file not found: {lang_code}")

    with open(file_path, "r", encoding="utf-8") as locale_file:
        content = locale_file.read()

    original_content = content
    applied = 0
    missing_updates: dict[str, str] = {}

    for key, value in updates.items():
        escaped = _escape_locale_value(value)
        line = f'  "{key}": "{escaped}",'
        pattern = re.compile(
            rf'^\s*["\']{re.escape(key)}["\']\s*:\s*["\'].*?(?<!\\)["\']\s*,?\s*$',
            re.MULTILINE,
        )
        updated_content, count = pattern.subn(line, content, count=1)
        if count > 0:
            content = updated_content
            applied += 1
        elif append_missing:
            missing_updates[key] = value

    if missing_updates:
        lines = content.splitlines(keepends=True)
        close_idx = None
        for idx in range(len(lines) - 1, -1, -1):
            if lines[idx].strip() == "};":
                close_idx = idx
                break

        if close_idx is None:
            close_idx = len(lines)

        prev_idx = close_idx - 1
        while prev_idx >= 0 and not lines[prev_idx].strip():
            prev_idx -= 1

        if prev_idx >= 0:
            prev_line = lines[prev_idx]
            if prev_line.strip() and not prev_line.rstrip().endswith(","):
                if prev_line.endswith("\n"):
                    lines[prev_idx] = prev_line.rstrip("\n") + ",\n"
                else:
                    lines[prev_idx] = prev_line + ","

        insertion_lines = [
            f'  "{key}": "{_escape_locale_value(value)}",\n'
            for key, value in sorted(missing_updates.items())
        ]
        lines[close_idx:close_idx] = insertion_lines
        content = "".join(lines)
        applied += len(missing_updates)

    if content != original_content:
        with open(file_path, "w", encoding="utf-8") as locale_file:
            locale_file.write(content)

    return applied


def _extract_language_from_preference_doc(pref: dict | None) -> str:
    if not pref:
        return "en"

    if str(pref.get("key") or "") == "language" and pref.get("value"):
        return _normalize_lang(str(pref.get("value") or "en"))

    if pref.get("language"):
        return _normalize_lang(str(pref.get("language") or "en"))

    return "en"


def _preference_doc_has_language(pref: dict | None) -> bool:
    if not pref:
        return False
    if str(pref.get("key") or "") == "language" and str(pref.get("value") or "").strip():
        return True
    if str(pref.get("language") or "").strip():
        return True
    return False


async def _get_user_language_code(user_id: str) -> str:
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "language_preference": 1})
    profile_lang = str((user_doc or {}).get("language_preference") or "").strip()
    if profile_lang:
        return _normalize_lang(profile_lang)

    pref = await db.user_preferences.find_one(
        {"user_id": user_id},
        {"_id": 0, "key": 1, "value": 1, "language": 1},
    )
    return _extract_language_from_preference_doc(pref)


