"""Dynamic FedaPay country/fee policy service (API-first with remote-config fallback)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import os
import json
import hashlib
import httpx


DEFAULT_FEDAPAY_POLICY: Dict[str, Any] = {
    "version": "contract-seed-v1",
    "source": "contract_seed",
    "channels": {
        "card": {
            "supported_cards": ["mastercard", "visa"],
            "fee_pct": 3.6,
        }
    },
    "countries": {
        "BJ": {
            "name": "Benin",
            "mobile_money_fees": {
                "mtn mobile money": 2.9,
                "moov money": 2.9,
            },
            "default_mobile_fee_pct": 2.9,
            "card_fee_pct": 3.6,
        },
        "CI": {
            "name": "Cote d'Ivoire",
            "mobile_money_fees": {
                "mtn mobile money": 4.0,
                "orange": 3.3,
            },
            "default_mobile_fee_pct": 3.3,
            "card_fee_pct": 3.6,
        },
        "TG": {
            "name": "Togo",
            "mobile_money_fees": {
                "moov money": 4.0,
            },
            "default_mobile_fee_pct": 4.0,
            "card_fee_pct": 3.6,
        },
        "SN": {
            "name": "Senegal",
            "mobile_money_fees": {
                "orange": 2.9,
                "free money": 2.0,
            },
            "default_mobile_fee_pct": 2.9,
            "card_fee_pct": 3.6,
        },
        "NE": {
            "name": "Niger",
            "mobile_money_fees": {
                "airtel": 4.0,
            },
            "default_mobile_fee_pct": 4.0,
            "card_fee_pct": 3.6,
        },
    },
}


DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY: Dict[str, Any] = {
    "version": "checkout-fee-visibility-v1",
    "scope": "customer_checkout_summary",
    "apply_to_admin": True,
    "providers": ["stripe", "paypal", "fedapay"],
    "hidden_summary_row_keys": ["processing-fee", "processing-formula", "fee-policy-source"],
    "hidden_provider_meta_keys": ["tax-provider", "jurisdiction-source", "policy-source"],
    "hide_provider_formula": True,
    "hide_policy_text": True,
    "hide_provider_card": True,
    "hide_jurisdiction_card": True,
}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_country(code: Optional[str]) -> str:
    return str(code or "").strip().upper()


def _normalize_provider(provider: Optional[str]) -> str:
    return str(provider or "").strip().lower()


def resolve_checkout_fee_visibility_policy(payment_method: Optional[str], *, is_admin: bool = False) -> Dict[str, Any]:
    provider = _normalize_provider(payment_method)
    if provider == "card":
        provider = "stripe"

    providers = {
        _normalize_provider(item)
        for item in (DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY.get("providers") or [])
        if str(item or "").strip()
    }
    apply_to_admin = bool(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY.get("apply_to_admin", False))
    hide_for_customer = (provider in providers) and (apply_to_admin or not is_admin)

    return {
        "version": DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["version"],
        "scope": DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["scope"],
        "provider": provider,
        "hide_customer_provider_fee_lines": hide_for_customer,
        "hidden_summary_row_keys": list(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hidden_summary_row_keys"]) if hide_for_customer else [],
        "hidden_provider_meta_keys": list(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hidden_provider_meta_keys"]) if hide_for_customer else [],
        "hide_provider_formula": bool(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hide_provider_formula"] and hide_for_customer),
        "hide_policy_text": bool(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hide_policy_text"] and hide_for_customer),
        "hide_provider_card": bool(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hide_provider_card"] and hide_for_customer),
        "hide_jurisdiction_card": bool(DEFAULT_CHECKOUT_FEE_VISIBILITY_POLICY["hide_jurisdiction_card"] and hide_for_customer),
    }


def _policy_refresh_minutes() -> int:
    try:
        val = int(os.environ.get("FEDAPAY_POLICY_REFRESH_MINUTES", "30"))
        return max(5, min(1440, val))
    except Exception:
        return 30


async def _fetch_json(url: str, *, headers: Optional[dict] = None, timeout: float = 12.0) -> Optional[Dict[str, Any]]:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers or {})
            if resp.status_code != 200:
                return None
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
            return None
    except Exception:
        return None


async def _post_json(url: str, payload: Dict[str, Any], *, timeout: float = 10.0) -> bool:
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code < 300
    except Exception:
        return False


def _extract_country_codes(payload: Dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    candidates = []
    for key in ("items", "data", "countries", "records", "payment_methods", "paymentMethods"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif isinstance(value, dict):
            candidates.extend(value.values())
    if not candidates and isinstance(payload, list):
        candidates = payload

    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("country_code", "countryCode", "country", "iso2", "iso"):
            code = item.get(key)
            if isinstance(code, str) and len(code.strip()) >= 2:
                codes.add(_normalize_country(code)[:2])
    return {c for c in codes if c}


def _extract_card_support(payload: Dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    blob = json.dumps(payload).lower()
    if "mastercard" in blob:
        cards.add("mastercard")
    if "visa" in blob:
        cards.add("visa")
    return cards


def _policy_hash(policy: Dict[str, Any]) -> str:
    core = {
        "version": policy.get("version"),
        "countries": policy.get("countries", {}),
        "channels": policy.get("channels", {}),
    }
    serialized = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _policy_change_summary(old_policy: Optional[Dict[str, Any]], new_policy: Dict[str, Any]) -> Dict[str, Any]:
    if not old_policy:
        return {
            "country_added": len(new_policy.get("countries", {}) or {}),
            "country_removed": 0,
            "fee_updates": 0,
            "card_support_changed": False,
        }

    old_countries = old_policy.get("countries", {}) or {}
    new_countries = new_policy.get("countries", {}) or {}
    old_keys = set(old_countries.keys())
    new_keys = set(new_countries.keys())
    added = sorted(list(new_keys - old_keys))
    removed = sorted(list(old_keys - new_keys))

    fee_updates = 0
    for cc in old_keys.intersection(new_keys):
        old_cfg = old_countries.get(cc, {}) or {}
        new_cfg = new_countries.get(cc, {}) or {}
        if old_cfg.get("default_mobile_fee_pct") != new_cfg.get("default_mobile_fee_pct"):
            fee_updates += 1
            continue
        if (old_cfg.get("mobile_money_fees") or {}) != (new_cfg.get("mobile_money_fees") or {}):
            fee_updates += 1
            continue
        if old_cfg.get("card_fee_pct") != new_cfg.get("card_fee_pct"):
            fee_updates += 1

    old_cards = set(old_policy.get("channels", {}).get("card", {}).get("supported_cards", []))
    new_cards = set(new_policy.get("channels", {}).get("card", {}).get("supported_cards", []))

    return {
        "country_added": len(added),
        "country_removed": len(removed),
        "added_countries": added,
        "removed_countries": removed,
        "fee_updates": fee_updates,
        "card_support_changed": old_cards != new_cards,
    }


def _normalize_policy(raw: Dict[str, Any], source: str) -> Dict[str, Any]:
    countries = raw.get("countries") if isinstance(raw.get("countries"), dict) else {}
    normalized_countries: Dict[str, Any] = {}
    for code, cfg in countries.items():
        country_code = _normalize_country(code)
        if not country_code or not isinstance(cfg, dict):
            continue
        mobile_raw = cfg.get("mobile_money_fees") if isinstance(cfg.get("mobile_money_fees"), dict) else {}
        mobile_fees: Dict[str, float] = {}
        for provider, pct in mobile_raw.items():
            p = _normalize_provider(provider)
            try:
                mobile_fees[p] = round(float(pct), 4)
            except Exception:
                continue

        default_fee = cfg.get("default_mobile_fee_pct")
        if default_fee is None:
            default_fee = min(mobile_fees.values()) if mobile_fees else 0.0

        try:
            card_fee_pct = round(float(cfg.get("card_fee_pct", raw.get("channels", {}).get("card", {}).get("fee_pct", 3.6))), 4)
        except Exception:
            card_fee_pct = 3.6

        normalized_countries[country_code] = {
            "name": str(cfg.get("name") or country_code),
            "mobile_money_fees": mobile_fees,
            "default_mobile_fee_pct": round(float(default_fee), 4),
            "card_fee_pct": card_fee_pct,
        }

    card_cfg = raw.get("channels", {}).get("card", {}) if isinstance(raw.get("channels"), dict) else {}
    cards = card_cfg.get("supported_cards") if isinstance(card_cfg.get("supported_cards"), list) else ["mastercard", "visa"]
    try:
        card_fee = round(float(card_cfg.get("fee_pct", 3.6)), 4)
    except Exception:
        card_fee = 3.6

    now = datetime.now(timezone.utc)
    return {
        "version": str(raw.get("version") or "dynamic-v1"),
        "source": source,
        "channels": {
            "card": {
                "supported_cards": sorted(list({str(c).strip().lower() for c in cards if str(c).strip()})),
                "fee_pct": card_fee,
            }
        },
        "countries": normalized_countries,
        "updated_at": _utc_iso_now(),
        "expires_at": (now + timedelta(minutes=_policy_refresh_minutes())).isoformat(),
    }


async def _fetch_official_policy() -> Optional[Dict[str, Any]]:
    pricing_url = os.environ.get("FEDAPAY_PRICING_API_URL", "").strip()
    secret = os.environ.get("FEDAPAY_SECRET_KEY", "").strip()
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}

    if pricing_url:
        data = await _fetch_json(pricing_url, headers=headers)
        if data:
            return _normalize_policy(data, source="official_api")

    # Fallback to live capability discovery from official API (countries + card support)
    api_base = os.environ.get("FEDAPAY_API_URL", "https://api.fedapay.com/v1").rstrip("/")
    candidate_paths = [
        f"{api_base}/payment_methods",
        f"{api_base}/payment-methods",
        f"{api_base}/countries",
    ]
    aggregated: Dict[str, Any] = {}
    countries: set[str] = set()
    cards: set[str] = set()

    for url in candidate_paths:
        payload = await _fetch_json(url, headers=headers)
        if not payload:
            continue
        aggregated[url] = payload
        countries.update(_extract_country_codes(payload))
        cards.update(_extract_card_support(payload))

    if not aggregated:
        return None

    seeded = _normalize_policy(DEFAULT_FEDAPAY_POLICY, source="official_api")
    if countries:
        for cc in countries:
            if cc not in seeded["countries"]:
                seeded["countries"][cc] = {
                    "name": cc,
                    "mobile_money_fees": {},
                    "default_mobile_fee_pct": 0.0,
                    "card_fee_pct": 3.6,
                }
    if cards:
        seeded["channels"]["card"]["supported_cards"] = sorted(list(cards))
    seeded["source"] = "official_api"
    seeded["version"] = "official-capability-sync"
    return seeded


async def _fetch_remote_policy() -> Optional[Dict[str, Any]]:
    remote_url = os.environ.get("FEDAPAY_FEE_CONFIG_URL", "").strip()
    data = await _fetch_json(remote_url)
    if not data:
        return None
    return _normalize_policy(data, source="remote_config")


def _is_expired(policy_doc: Dict[str, Any]) -> bool:
    expiry = policy_doc.get("expires_at")
    if not expiry:
        return True
    try:
        exp = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= datetime.now(timezone.utc)
    except Exception:
        return True


async def refresh_fedapay_policy(db, *, force: bool = False) -> Dict[str, Any]:
    existing = await db.fedapay_policy_cache.find_one({"policy_id": "active"}, {"_id": 0})
    if existing and not force and not _is_expired(existing):
        return existing

    official_policy = await _fetch_official_policy()
    remote_policy = await _fetch_remote_policy()

    if official_policy and remote_policy:
        # Merge remote fee detail into official country/channel footprint.
        merged = _normalize_policy(remote_policy, source="official_api")
        for cc, cfg in (official_policy.get("countries", {}) or {}).items():
            merged["countries"].setdefault(cc, cfg)
        official_cards = set((official_policy.get("channels", {}).get("card", {}).get("supported_cards", [])))
        remote_cards = set((merged.get("channels", {}).get("card", {}).get("supported_cards", [])))
        merged["channels"]["card"]["supported_cards"] = sorted(list(official_cards.union(remote_cards)))
        policy = merged
    elif official_policy:
        policy = official_policy
    elif remote_policy:
        policy = remote_policy
    else:
        policy = _normalize_policy(DEFAULT_FEDAPAY_POLICY, source="contract_seed")

    now = datetime.now(timezone.utc)
    new_hash = _policy_hash(policy)
    previous_hash = existing.get("policy_hash") if existing else None
    previous_source = existing.get("source") if existing else None

    stored = {
        "policy_id": "active",
        **policy,
        "policy_hash": new_hash,
        "last_refresh_at": now.isoformat(),
    }
    await db.fedapay_policy_cache.update_one({"policy_id": "active"}, {"$set": stored}, upsert=True)

    # Audit timeline: append only when policy actually changes
    if previous_hash != new_hash:
        await db.fedapay_policy_history.insert_one(
            {
                "history_id": f"fph_{now.strftime('%Y%m%d%H%M%S%f')}",
                "policy_hash": new_hash,
                "source": stored.get("source"),
                "version": stored.get("version"),
                "change_summary": _policy_change_summary(existing, stored),
                "countries": stored.get("countries", {}),
                "channels": stored.get("channels", {}),
                "created_at": now.isoformat(),
            }
        )

    # Source switch notifications (webhook + audit stream)
    if previous_source and previous_source != stored.get("source"):
        event_payload = {
            "event": "fedapay_policy_source_switched",
            "from_source": previous_source,
            "to_source": stored.get("source"),
            "policy_hash": new_hash,
            "country_count": len(stored.get("countries", {}) or {}),
            "changed_at": now.isoformat(),
        }
        await db.fedapay_policy_source_events.insert_one(event_payload)
        webhook_url = os.environ.get("FEDAPAY_POLICY_SOURCE_WEBHOOK_URL", "").strip()
        await _post_json(webhook_url, event_payload)

    return stored


async def get_fedapay_policy(db) -> Dict[str, Any]:
    return await refresh_fedapay_policy(db, force=False)


async def clear_fedapay_policy_cache(db) -> None:
    await db.fedapay_policy_cache.delete_many({"policy_id": "active"})


def resolve_mobile_money_fee_pct(policy: Dict[str, Any], country_code: Optional[str], mobile_provider: Optional[str] = None) -> float:
    countries = policy.get("countries", {}) if isinstance(policy, dict) else {}
    cc = _normalize_country(country_code)
    cfg = countries.get(cc) if isinstance(countries, dict) else None
    if not cfg:
        return 0.0

    provider_key = _normalize_provider(mobile_provider)
    aliases = {
        "mtn": "mtn mobile money",
        "mtn momo": "mtn mobile money",
        "mtn mobile": "mtn mobile money",
        "moov": "moov money",
        "flooz": "moov money",
        "orange money": "orange",
        "orange": "orange",
        "free": "free money",
        "free money": "free money",
        "airtel money": "airtel",
        "airtel": "airtel",
    }
    provider_key = aliases.get(provider_key, provider_key)
    provider_fees = cfg.get("mobile_money_fees", {}) if isinstance(cfg.get("mobile_money_fees"), dict) else {}
    if provider_key and provider_key in provider_fees:
        return round(float(provider_fees[provider_key]), 4)

    # fuzzy match provider names
    if provider_key:
        for k, v in provider_fees.items():
            if provider_key in k or k in provider_key:
                return round(float(v), 4)

    try:
        return round(float(cfg.get("default_mobile_fee_pct", 0.0)), 4)
    except Exception:
        return 0.0


def resolve_card_fee_pct(policy: Dict[str, Any], country_code: Optional[str]) -> float:
    cc = _normalize_country(country_code)
    countries = policy.get("countries", {}) if isinstance(policy, dict) else {}
    cfg = countries.get(cc) if isinstance(countries, dict) else None
    if cfg and cfg.get("card_fee_pct") is not None:
        try:
            return round(float(cfg.get("card_fee_pct")), 4)
        except Exception:
            pass
    try:
        return round(float(policy.get("channels", {}).get("card", {}).get("fee_pct", 3.6)), 4)
    except Exception:
        return 3.6


def list_policy_country_codes(policy: Dict[str, Any]) -> list[str]:
    countries = policy.get("countries", {}) if isinstance(policy, dict) else {}
    return sorted(list(countries.keys())) if isinstance(countries, dict) else []
