"""Payment localization + jurisdiction resolution for checkout, receipts, and notifications."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from utils.ip_geolocation import lookup_ip


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


SUPPORTED_LANGUAGES = {
    "en", "fr", "es", "de", "pt", "ja", "zh", "ar", "hi", "ko", "it", "ru", "tr", "nl", "sv", "pl", "th", "vi", "id", "ms", "sw", "uk", "ro",
}

COUNTRY_LANGUAGE_CANDIDATES: Dict[str, list[str]] = {
    "US": ["en", "es"],
    "CA": ["en", "fr"],
    "BE": ["fr", "nl", "de"],
    "CH": ["de", "fr", "it"],
    "GB": ["en"],
    "AU": ["en"],
    "NZ": ["en"],
    "FR": ["fr"],
    "ES": ["es"],
    "MX": ["es"],
    "BR": ["pt"],
    "PT": ["pt"],
    "DE": ["de"],
    "IT": ["it"],
    "JP": ["ja"],
    "CN": ["zh"],
    "TW": ["zh"],
    "KR": ["ko"],
    "SA": ["ar"],
    "AE": ["ar", "en"],
    "EG": ["ar"],
    "MA": ["ar", "fr"],
    "BJ": ["fr"],
    "TG": ["fr"],
    "SN": ["fr"],
    "CI": ["fr"],
    "NE": ["fr"],
    "CM": ["fr", "en"],
    "NG": ["en"],
    "ZA": ["en"],
    "GH": ["en"],
}

COUNTRY_DEFAULT_CURRENCY: Dict[str, str] = {
    "US": "USD",
    "CA": "CAD",
    "GB": "GBP",
    "FR": "EUR",
    "DE": "EUR",
    "ES": "EUR",
    "IT": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "PT": "EUR",
    "IE": "EUR",
    "BR": "BRL",
    "MX": "MXN",
    "JP": "JPY",
    "CN": "CNY",
    "IN": "INR",
    "NG": "NGN",
    "GH": "GHS",
    "BJ": "XOF",
    "TG": "XOF",
    "SN": "XOF",
    "CI": "XOF",
    "NE": "XOF",
    "CM": "XAF",
    "GA": "XAF",
    "TD": "XAF",
    "ZA": "ZAR",
    "AU": "AUD",
    "CH": "CHF",
    "SE": "SEK",
    "PL": "PLN",
    "TH": "THB",
    "AE": "AED",
    "SA": "SAR",
    "TR": "TRY",
}

FRENCH_COUNTRIES = frozenset({
    "FR", "BE", "MC", "LU", "HT", "SN", "CI", "CM", "BF", "ML", "NE", "TD",
    "GN", "CG", "CD", "GA", "TG", "BJ", "MG", "DJ", "CF", "KM", "MU", "SC", "RW", "BI",
})
SPANISH_COUNTRIES = frozenset({
    "ES", "MX", "AR", "CO", "PE", "VE", "CL", "EC", "GT", "CU", "BO", "DO",
    "HN", "PY", "SV", "NI", "CR", "PA", "UY", "PR", "GQ",
})
PORTUGUESE_COUNTRIES = frozenset({"BR", "PT", "AO", "MZ", "GW", "CV", "ST", "TL"})
ARABIC_COUNTRIES = frozenset({
    "SA", "AE", "EG", "IQ", "MA", "DZ", "TN", "LY", "SD", "JO", "LB", "SY",
    "YE", "OM", "KW", "QA", "BH", "MR", "PS", "SO",
})
FRENCH_CANADA_STATES = frozenset({"QC"})
FRENCH_SWISS_CANTONS = frozenset({"GE", "VD", "NE", "JU", "FR", "VS"})

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def normalize_language_code(value: str) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    lang = raw.split("-")[0]
    return lang if lang in SUPPORTED_LANGUAGES else ""


def detect_payment_locale(payment_or_tx: Optional[Dict[str, Any]] = None, default: str = "en") -> str:
    """Shared payment document/checkout locale detection from explicit language, jurisdiction, then currency."""
    tx = payment_or_tx or {}
    localization_ctx = tx.get("localization_context", {}) if isinstance(tx.get("localization_context"), dict) else {}
    for candidate in (
        localization_ctx.get("resolved_language", ""),
        tx.get("preferred_language", ""),
        str(tx.get("locale", tx.get("language", ""))).lower().strip()[:5],
    ):
        lang = normalize_language_code(candidate or "")
        if lang:
            return lang

    jurisdiction = tx.get("jurisdiction", {}) if isinstance(tx.get("jurisdiction"), dict) else {}
    country = str(jurisdiction.get("country", "")).upper().strip()
    state = str(jurisdiction.get("state", "")).upper().strip()

    if country in FRENCH_COUNTRIES or (country == "CA" and state in FRENCH_CANADA_STATES) or (country == "CH" and state in FRENCH_SWISS_CANTONS):
        return "fr"
    if country in SPANISH_COUNTRIES:
        return "es"
    if country in PORTUGUESE_COUNTRIES:
        return "pt"
    if country in ARABIC_COUNTRIES:
        return "ar"

    if not country and str(tx.get("currency", "")).upper() in {"XOF", "XAF"}:
        return "fr"

    return normalize_language_code(default) or "en"


def coerce_confidence_score(value: Any) -> float:
    """Normalize confidence values from LLM JSON into a safe 0.0..1.0 float."""
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        raw = str(value).strip().lower()
        alias_map = {
            "high": 0.9,
            "very_high": 0.95,
            "medium": 0.6,
            "moderate": 0.6,
            "low": 0.3,
            "very_low": 0.1,
        }
        if raw in alias_map:
            return alias_map[raw]

        if raw.endswith("%"):
            raw = raw[:-1].strip()
            try:
                return max(0.0, min(1.0, float(raw) / 100.0))
            except Exception:
                return 0.0

        try:
            numeric = float(raw)
        except Exception:
            return 0.0

    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.0, min(1.0, numeric))


def extract_region_code(value: str) -> str:
    raw = str(value or "").strip().replace("_", "-")
    parts = [part for part in raw.split("-") if part]
    if len(parts) >= 2 and len(parts[1]) in {2, 3}:
        return parts[1].upper()
    return ""


def parse_browser_languages(value: str) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for chunk in re.split(r"[,;]", value):
        lang = normalize_language_code(chunk)
        if lang and lang not in items:
            items.append(lang)
    return items


def extract_client_ip(request) -> str:
    if not request:
        return ""
    headers = request.headers
    forwarded_for = headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    for key in ("x-real-ip", "cf-connecting-ip", "x-client-ip"):
        value = headers.get(key, "").strip()
        if value:
            return value
    return ""


def _majority_value(values: list[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    if not cleaned:
        return ""
    return Counter(cleaned).most_common(1)[0][0]


async def _get_behavior_signals(db, user_id: str) -> dict:
    if not user_id:
        return {"language": "", "currency": ""}

    recent = await db.payment_transactions.find(
        {"user_id": user_id},
        {"_id": 0, "locale": 1, "language": 1, "currency": 1, "localization_context.resolved_language": 1},
    ).sort("created_at", -1).limit(8).to_list(8)

    language_candidates: list[str] = []
    currency_candidates: list[str] = []
    for row in recent:
        ctx = row.get("localization_context", {}) if isinstance(row.get("localization_context"), dict) else {}
        lang = normalize_language_code(
            row.get("locale") or row.get("language") or ctx.get("resolved_language") or ""
        )
        if lang:
            language_candidates.append(lang)
        currency = str(row.get("currency") or "").upper().strip()
        if currency:
            currency_candidates.append(currency)

    return {
        "language": _majority_value(language_candidates),
        "currency": _majority_value(currency_candidates),
    }


async def _get_user_language_preference(db, user_id: str) -> str:
    if not user_id:
        return ""
    pref = await db.user_preferences.find_one(
        {"user_id": user_id, "key": "language"},
        {"_id": 0, "value": 1},
    )
    return normalize_language_code((pref or {}).get("value", ""))


def _build_country_language_default(country: str, state: str, browser_languages: list[str]) -> tuple[str, str]:
    candidates = COUNTRY_LANGUAGE_CANDIDATES.get(country, ["en"])
    if country == "CA" and state in FRENCH_CANADA_STATES:
        return "fr", "country_state"
    if country == "CA" and "fr" in browser_languages:
        return "fr", "browser_country_match"
    for lang in browser_languages:
        if lang in candidates:
            return lang, "browser_country_match"
    return candidates[0], "country_default"


def _needs_ai_validation(*, country: str, state: str, user_pref_lang: str, behavior_lang: str, browser_primary: str, country_lang: str) -> bool:
    if user_pref_lang:
        return False
    distinct = {lang for lang in [behavior_lang, browser_primary, country_lang] if lang}
    if len(distinct) >= 2:
        return True
    if country in {"CA", "BE", "CH", "US", "AE", "MA", "CM"} and not state:
        return True
    return False


def _extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


async def _run_ai_secondary_validation(db, context: dict) -> dict:
    if not EMERGENT_LLM_KEY:
        return {
            "status": "skipped",
            "reason": "missing_key",
        }

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    fingerprint = hashlib.sha1(
        json.dumps(
            {
                "country": context.get("jurisdiction", {}).get("country"),
                "state": context.get("jurisdiction", {}).get("state"),
                "browser_languages": context.get("signals", {}).get("browser_languages", []),
                "user_preference_language": context.get("signals", {}).get("user_preference_language"),
                "behavior_language": context.get("signals", {}).get("behavior_language"),
                "resolved_language": context.get("resolved_language"),
                "resolved_currency": context.get("resolved_currency"),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    cached = await db.payment_localization_ai_cache.find_one(
        {"fingerprint": fingerprint},
        {"_id": 0},
    )
    if cached:
        return cached

    session_id = f"payment-locale-{uuid.uuid4().hex[:12]}"
    prompt = {
        "jurisdiction": context.get("jurisdiction", {}),
        "signals": context.get("signals", {}),
        "resolved_language": context.get("resolved_language"),
        "resolved_currency": context.get("resolved_currency"),
        "rules": {
            "user_preference_language_wins": True,
            "do_not_change_currency_if_user_explicitly_requested_one": True,
            "return_json_only": True,
        },
    }

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=(
            "You validate payment localization decisions. Keep deterministic preference priority intact. "
            "If user preference language exists, never override it. Return JSON only with keys: "
            "resolved_language, resolved_currency, confidence, should_override, reason."
        ),
    ).with_model("openai", "gpt-4o")

    response_text = await chat.send_message(UserMessage(text=json.dumps(prompt, ensure_ascii=False)))
    parsed = _extract_json_object(response_text)
    result = {
        "fingerprint": fingerprint,
        "session_id": session_id,
        "status": "validated" if parsed else "fallback",
        "raw_response": response_text,
        "resolved_language": normalize_language_code(parsed.get("resolved_language", "")) or context.get("resolved_language"),
        "resolved_currency": str(parsed.get("resolved_currency") or context.get("resolved_currency") or "USD").upper(),
        "confidence": coerce_confidence_score(parsed.get("confidence")),
        "should_override": bool(parsed.get("should_override")),
        "reason": str(parsed.get("reason") or ""),
    }

    await db.payment_localization_ai_cache.update_one(
        {"fingerprint": fingerprint},
        {"$set": result},
        upsert=True,
    )
    await db.payment_localization_ai_runs.insert_one(
        {
            "run_id": f"ploc_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "fingerprint": fingerprint,
            "prompt": prompt,
            "result": result,
        }
    )
    return result


async def resolve_payment_localization_context(
    *,
    db,
    request=None,
    user=None,
    country_code: Optional[str] = None,
    state_code: Optional[str] = None,
    postal_code: Optional[str] = None,
    requested_currency: Optional[str] = None,
    requested_language: Optional[str] = None,
    browser_language: Optional[str] = None,
    browser_languages: Optional[str] = None,
) -> Dict[str, Any]:
    headers = request.headers if request else {}

    user_id = getattr(user, "user_id", "") if user else ""
    user_pref_lang = await _get_user_language_preference(db, user_id)
    behavior = await _get_behavior_signals(db, user_id)

    browser_lang_header = browser_languages or headers.get("x-browser-languages") or headers.get("accept-language") or ""
    browser_langs = parse_browser_languages(browser_lang_header)
    browser_primary = normalize_language_code(browser_language or headers.get("x-browser-language") or "") or (browser_langs[0] if browser_langs else "")

    explicit_country = str(country_code or "").upper().strip()
    explicit_state = str(state_code or "").upper().strip()
    explicit_postal = str(postal_code or "").strip()

    locale_region = extract_region_code(headers.get("x-user-locale") or browser_language or "")
    ip = extract_client_ip(request)
    geo = await lookup_ip(db, ip) if ip else None

    country = (
        explicit_country
        or headers.get("x-country-code", "")
        or headers.get("cf-ipcountry", "")
        or headers.get("x-vercel-ip-country", "")
        or str((geo or {}).get("country_code") or "")
        or str(getattr(user, "country", "") or "")
        or locale_region
        or "US"
    ).upper().strip()
    state = (
        explicit_state
        or headers.get("x-state-code", "")
        or headers.get("x-vercel-ip-country-region", "")
        or str(getattr(user, "state", "") or "")
    ).upper().strip()
    postal = explicit_postal or headers.get("x-postal-code", "") or str(getattr(user, "postal_code", "") or "")

    country_lang, country_lang_source = _build_country_language_default(country, state, browser_langs)

    resolved_language = "en"
    language_source = "country_default"
    if user_pref_lang:
        resolved_language = user_pref_lang
        language_source = "user_preference"
    elif normalize_language_code(requested_language or ""):
        resolved_language = normalize_language_code(requested_language or "")
        language_source = "request"
    elif behavior.get("language"):
        resolved_language = normalize_language_code(behavior.get("language") or "") or country_lang
        language_source = "behavior"
    elif browser_primary:
        resolved_language = browser_primary
        language_source = "browser"
    else:
        resolved_language = country_lang
        language_source = country_lang_source

    requested_currency_code = str(requested_currency or "").upper().strip()
    user_currency = str(getattr(user, "currency_preference", "") or "").upper().strip() if user else ""
    behavior_currency = str(behavior.get("currency") or "").upper().strip()
    country_currency = COUNTRY_DEFAULT_CURRENCY.get(country, "USD")

    if requested_currency_code:
        resolved_currency = requested_currency_code
        currency_source = "request"
    elif user_currency:
        resolved_currency = user_currency
        currency_source = "user_preference"
    elif behavior_currency:
        resolved_currency = behavior_currency
        currency_source = "behavior"
    else:
        resolved_currency = country_currency
        currency_source = "country_default"

    confidence = {
        "user_preference": 0.99,
        "request": 0.96,
        "behavior": 0.88,
        "browser": 0.82,
        "browser_country_match": 0.78,
        "country_state": 0.87,
        "country_default": 0.72,
    }.get(language_source, 0.7)

    context: Dict[str, Any] = {
        "resolved_language": resolved_language,
        "resolved_currency": resolved_currency,
        "jurisdiction": {
            "country": country,
            "state": state,
            "postal_code": postal,
        },
        "signals": {
            "user_preference_language": user_pref_lang,
            "browser_primary_language": browser_primary,
            "browser_languages": browser_langs,
            "behavior_language": behavior.get("language", ""),
            "behavior_currency": behavior_currency,
            "country_language_default": country_lang,
            "country_currency_default": country_currency,
            "ip_country_code": str((geo or {}).get("country_code") or "").upper(),
            "ip_region": str((geo or {}).get("region") or ""),
            "user_locale_header": headers.get("x-user-locale", ""),
        },
        "source_priority": {
            "language": language_source,
            "currency": currency_source,
            "jurisdiction": "request_or_edge_headers",
        },
        "confidence": confidence,
        "requires_ai_validation": _needs_ai_validation(
            country=country,
            state=state,
            user_pref_lang=user_pref_lang,
            behavior_lang=normalize_language_code(behavior.get("language") or ""),
            browser_primary=browser_primary,
            country_lang=country_lang,
        ),
        "validation_status": "deterministic_only",
        "client_ip_present": bool(ip),
        "ip_geo_resolved": bool(geo),
    }

    if context["requires_ai_validation"]:
        ai_result = await _run_ai_secondary_validation(db, context)
        context["ai_validation"] = ai_result
        context["validation_status"] = ai_result.get("status", "fallback")
        if (
            ai_result.get("status") == "validated"
            and ai_result.get("should_override")
            and not user_pref_lang
            and ai_result.get("resolved_language") in SUPPORTED_LANGUAGES
        ):
            context["resolved_language"] = ai_result.get("resolved_language")
            context["source_priority"]["language"] = "ai_secondary_validation"

    return context