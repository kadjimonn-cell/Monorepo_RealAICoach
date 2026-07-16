from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from .db import JWT_SECRET, User, db


SPORTS_STREAM_TOKEN_TTL_SECONDS = 300
BLACKOUT_RULES_COLL = "watch_sports_blackout_rules"
SPORTS_SOURCE_REPLACEMENT_HISTORY_COLL = "watch_sports_source_replacement_history"
SPORTS_CATEGORY_CURATION_COLL = "watch_sports_category_curation"

DEFAULT_SPORTS_BLACKOUT_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "rule_nfl_cbs_gb_window",
        "league": "NFL on CBS",
        "countries": ["GB"],
        "states": [],
        "start_at": "2026-01-01T00:00:00+00:00",
        "end_at": "2027-01-01T00:00:00+00:00",
        "reason": "Regional rights restriction for this event window.",
        "is_active": True,
    },
    {
        "rule_id": "rule_ufc_main_de_window",
        "league": "UFC Main Card",
        "countries": ["DE"],
        "states": [],
        "start_at": "2026-01-01T00:00:00+00:00",
        "end_at": "2027-01-01T00:00:00+00:00",
        "reason": "Regional rights restriction for this event window.",
        "is_active": True,
    },
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def today_key() -> str:
    return now_utc().strftime("%Y-%m-%d")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_country_code(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text[:2] if len(text) >= 2 else ""


def normalize_state_code(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text[:3] if len(text) >= 2 else ""


def normalize_category_name(value: str) -> str:
    return str(value or "").strip()[:80]


def stream_token_signature(payload_b64: str) -> str:
    secret = str(JWT_SECRET or "").encode("utf-8")
    return hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_stream_token(user_id: str, item_id: str, expires_at: int) -> str:
    payload = {
        "u": str(user_id or "").strip(),
        "i": str(item_id or "").strip(),
        "e": int(expires_at),
        "v": 1,
        "s": "sports",
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = stream_token_signature(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_stream_token(token: str, item_id: str) -> dict[str, Any] | None:
    text = str(token or "").strip()
    if not text or "." not in text:
        return None
    payload_b64, sig = text.split(".", 1)
    expected = stream_token_signature(payload_b64)
    if not hmac.compare_digest(str(sig or ""), expected):
        return None
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload_json = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return None

    expires = int(payload.get("e") or 0)
    if expires <= int(now_utc().timestamp()):
        return None
    if str(payload.get("i") or "") != str(item_id or ""):
        return None
    if str(payload.get("s") or "") != "sports":
        return None
    return payload


def build_secure_stream_path(item_id: str, token: str) -> str:
    return f"/api/sports/v2/secure-stream?item_id={item_id}&token={token}"


def attach_blackout_metadata(item: dict[str, Any], blackout: dict[str, Any]) -> dict[str, Any]:
    row = dict(item or {})
    row["blackout_blocked"] = bool(blackout.get("blocked"))
    row["blackout_reason"] = str(blackout.get("reason") or "")
    row["blackout_rule_id"] = str(blackout.get("rule_id") or "")
    return row


def is_rule_time_active(rule: dict[str, Any], now_dt: datetime) -> bool:
    start_dt = parse_iso_datetime(str(rule.get("start_at") or ""))
    end_dt = parse_iso_datetime(str(rule.get("end_at") or ""))
    if start_dt and now_dt < start_dt:
        return False
    if end_dt and now_dt > end_dt:
        return False
    return True


def evaluate_sports_blackout(
    item: dict[str, Any],
    region: dict[str, str],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    league_lc = str(item.get("league") or item.get("category") or "").strip().lower()
    country = normalize_country_code(region.get("country_code"))
    state = normalize_state_code(region.get("state_code"))
    now_dt = now_utc()

    for rule in rules:
        if str(rule.get("league_lc") or "").strip().lower() != league_lc:
            continue
        if not is_rule_time_active(rule, now_dt):
            continue

        rule_countries = {
            normalize_country_code(str(x or ""))
            for x in (rule.get("countries") or [])
            if normalize_country_code(str(x or ""))
        }
        rule_states = {
            normalize_state_code(str(x or ""))
            for x in (rule.get("states") or [])
            if normalize_state_code(str(x or ""))
        }

        if rule_countries and country not in rule_countries:
            continue
        if rule_states and state not in rule_states:
            continue

        return {
            "blocked": True,
            "reason": str(rule.get("reason") or "Regional rights restriction for this event window.").strip(),
            "rule_id": str(rule.get("rule_id") or ""),
        }

    return {"blocked": False, "reason": "", "rule_id": ""}


async def resolve_user_region(user: User, request: Request) -> dict[str, str]:
    user_row = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "country_code": 1,
            "country": 1,
            "state_code": 1,
            "state": 1,
            "region": 1,
        },
    ) or {}

    country = normalize_country_code(str(user_row.get("country_code") or user_row.get("country") or ""))
    state = normalize_state_code(str(user_row.get("state_code") or user_row.get("state") or user_row.get("region") or ""))

    if not country:
        country = normalize_country_code(
            request.headers.get("x-country-code")
            or request.headers.get("cf-ipcountry")
            or request.headers.get("x-vercel-ip-country")
            or request.headers.get("x-appengine-country")
            or request.query_params.get("country")
        )
    if not state:
        state = normalize_state_code(
            request.headers.get("x-region-code")
            or request.headers.get("x-us-state")
            or request.headers.get("x-vercel-ip-country-region")
            or request.headers.get("x-appengine-region")
            or request.query_params.get("state")
        )

    return {"country_code": country, "state_code": state}


async def resolve_region_for_user_id(user_id: str, request: Request) -> dict[str, str]:
    user_row = await db.users.find_one(
        {"user_id": str(user_id or "")},
        {
            "_id": 0,
            "country_code": 1,
            "country": 1,
            "state_code": 1,
            "state": 1,
            "region": 1,
        },
    ) or {}

    country = normalize_country_code(str(user_row.get("country_code") or user_row.get("country") or ""))
    state = normalize_state_code(str(user_row.get("state_code") or user_row.get("state") or user_row.get("region") or ""))

    if not country:
        country = normalize_country_code(
            request.headers.get("x-country-code")
            or request.headers.get("cf-ipcountry")
            or request.headers.get("x-vercel-ip-country")
            or request.headers.get("x-appengine-country")
            or request.query_params.get("country")
        )
    if not state:
        state = normalize_state_code(
            request.headers.get("x-region-code")
            or request.headers.get("x-us-state")
            or request.headers.get("x-vercel-ip-country-region")
            or request.headers.get("x-appengine-region")
            or request.query_params.get("state")
        )

    return {"country_code": country, "state_code": state}


async def ensure_default_sports_blackout_rules() -> None:
    existing_count = await db[BLACKOUT_RULES_COLL].count_documents({}, limit=1)
    if existing_count > 0:
        return
    now = now_iso()
    docs = []
    for row in DEFAULT_SPORTS_BLACKOUT_RULES:
        docs.append(
            {
                "rule_id": str(row.get("rule_id") or f"rule_{uuid.uuid4().hex[:10]}"),
                "league": str(row.get("league") or "").strip()[:120],
                "league_lc": str(row.get("league") or "").strip().lower(),
                "countries": [
                    normalize_country_code(str(x or ""))
                    for x in (row.get("countries") or [])
                    if normalize_country_code(str(x or ""))
                ],
                "states": [
                    normalize_state_code(str(x or ""))
                    for x in (row.get("states") or [])
                    if normalize_state_code(str(x or ""))
                ],
                "start_at": str(row.get("start_at") or "").strip() or None,
                "end_at": str(row.get("end_at") or "").strip() or None,
                "reason": str(row.get("reason") or "Regional rights restriction.").strip()[:220],
                "is_active": bool(row.get("is_active", True)),
                "created_by": "system_seed",
                "created_at": now,
                "updated_at": now,
            }
        )
    if docs:
        await db[BLACKOUT_RULES_COLL].insert_many(docs)


async def active_sports_blackout_rules() -> list[dict[str, Any]]:
    await ensure_default_sports_blackout_rules()
    return await db[BLACKOUT_RULES_COLL].find(
        {"is_active": True},
        {
            "_id": 0,
            "rule_id": 1,
            "league": 1,
            "league_lc": 1,
            "countries": 1,
            "states": 1,
            "start_at": 1,
            "end_at": 1,
            "reason": 1,
            "is_active": 1,
        },
    ).to_list(500)


async def get_sports_category_curation() -> dict[str, Any]:
    doc = await db[SPORTS_CATEGORY_CURATION_COLL].find_one(
        {"key": "global"},
        {"_id": 0, "ordered_categories": 1, "pinned_categories": 1},
    ) or {}
    ordered = [normalize_category_name(x) for x in (doc.get("ordered_categories") or []) if normalize_category_name(x)]
    pinned = [normalize_category_name(x) for x in (doc.get("pinned_categories") or []) if normalize_category_name(x)]
    return {
        "ordered_categories": ordered,
        "pinned_categories": pinned,
    }


async def append_sports_source_replacement_history(user_id: str, rows: list[dict[str, Any]]) -> int:
    events: list[dict[str, Any]] = []
    now = now_iso()
    day_key = today_key()
    for row in rows[:80]:
        if not bool(row.get("fallback_applied")):
            continue
        item_id = str(row.get("item_id") or "")
        if not item_id:
            continue
        dedupe_key = f"{day_key}:{item_id}:{str(row.get('youtube_channel_id') or '')}"
        events.append(
            {
                "dedupe_key": dedupe_key,
                "item_id": item_id,
                "title": str(row.get("title") or ""),
                "from_league": str(row.get("fallback_from_league") or ""),
                "to_league": str(row.get("league") or ""),
                "source_label": str(row.get("source_label") or ""),
                "embeddability_reason": str(row.get("embeddability_reason") or ""),
                "embeddability_score": int(row.get("embeddability_score") or 0),
                "created_by": str(user_id or ""),
                "created_at": now,
            }
        )

    inserted = 0
    for event in events:
        result = await db[SPORTS_SOURCE_REPLACEMENT_HISTORY_COLL].update_one(
            {"dedupe_key": event["dedupe_key"]},
            {"$setOnInsert": event},
            upsert=True,
        )
        if int(result.upserted_id is not None):
            inserted += 1
    return inserted


async def followed_sports_leagues(user: User) -> list[str]:
    rows = await db.watch_sports_league_follows.find(
        {"user_id": user.user_id},
        {"_id": 0, "league_name": 1},
    ).to_list(300)
    leagues: list[str] = []
    seen: set[str] = set()
    for row in rows:
        league = str(row.get("league_name") or "").strip()
        key = league.lower()
        if not league or key in seen:
            continue
        seen.add(key)
        leagues.append(league)
    return leagues


async def sports_league_reminder_settings(user: User) -> list[dict[str, Any]]:
    rows = await db.watch_sports_league_follows.find(
        {"user_id": user.user_id},
        {"_id": 0, "league_name": 1, "pre_kickoff_15_enabled": 1},
    ).to_list(300)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        league_name = str(row.get("league_name") or "").strip()
        key = league_name.lower()
        if not league_name or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "league_name": league_name,
                "weekly_enabled": True,
                "pre_kickoff_15_enabled": bool(row.get("pre_kickoff_15_enabled")),
            }
        )
    return out
