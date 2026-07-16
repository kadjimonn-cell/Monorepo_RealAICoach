"""Watch Videos companion audio hubs: Audio Studio + My Podcasts."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import requests

from emergentintegrations.llm.chat import LlmChat, UserMessage

from .db import EMERGENT_LLM_KEY, JWT_SECRET, User, db, require_admin, require_auth
from utils.access_control_engine import build_session_entitlements, compute_effective_plan
from utils.email_notifications import notify


router = APIRouter(prefix="/videos", tags=["Watch Audio Hub"])


PLAN_LEVEL = {"free": 0, "basic": 1, "premium": 2}
PLAN_DAILY_PLAY_CAPS = {"free": 5, "basic": 120, "premium": -1}

SEED_TARGET_COUNT = 520
DAILY_DROP_COUNT = 6
BEHAVIORAL_AI_CACHE_HOURS = 4
ML_PIPELINE_FLAG_KEY = "ml_pipeline_v1_enabled"
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

SURFACE_CONFIG: dict[str, dict[str, Any]] = {
    "audio_studio": {
        "label": "Audio Studio",
        "feature_id": "watch-videos-audio-studio",
        "route_hint": "/features/watch-videos?tab=scan",
        "catalog_coll": "watch_audio_studio_catalog",
        "usage_coll": "watch_audio_studio_usage",
        "history_coll": "watch_audio_studio_history",
        "runs_coll": "watch_audio_studio_ingest_runs",
        "state_key": "watch_audio_studio_daily_drop_state",
        "id_prefix": "ast",
        "categories": [
            "Focus Flow",
            "Deep Work",
            "Coding Beats",
            "Workout Energy",
            "Calm Piano",
            "Lo-Fi",
            "Morning Boost",
            "Sleep Sound",
            "Meditation",
            "Ambient Nature",
            "Jazz Lounge",
            "Cinematic",
            "Indie Mix",
            "Classical Essentials",
            "Acoustic Calm",
            "Chill House",
        ],
    },
    "podcasts": {
        "label": "My Podcasts",
        "feature_id": "watch-videos-my-podcasts",
        "route_hint": "/features/watch-videos?tab=chat",
        "catalog_coll": "watch_podcast_catalog",
        "usage_coll": "watch_podcast_usage",
        "history_coll": "watch_podcast_history",
        "runs_coll": "watch_podcast_ingest_runs",
        "state_key": "watch_podcast_daily_drop_state",
        "id_prefix": "pod",
        "categories": [
            "Startup Stories",
            "AI & Future",
            "Mindset Mastery",
            "Productivity",
            "Wellness Talks",
            "Career Growth",
            "Marketing",
            "Finance",
            "Leadership",
            "Relationships",
            "Technology",
            "Sports",
            "History",
            "Motivation",
            "Creator Economy",
            "Global News",
        ],
    },
    "sports": {
        "label": "Sports",
        "feature_id": "watch-videos-sports",
        "route_hint": "/features/sports",
        "catalog_coll": "watch_sports_catalog",
        "usage_coll": "watch_sports_usage",
        "history_coll": "watch_sports_history",
        "runs_coll": "watch_sports_ingest_runs",
        "state_key": "watch_sports_weekly_drop_state",
        "id_prefix": "spt",
        "drop_cadence": "weekly",
        "drop_count": 10,
        "categories": [
            "NFL on CBS",
            "UFC Main Card",
            "UEFA Champions League",
            "CBS Sports HQ",
            "Local CBS Station",
            "College Football",
            "College Basketball",
            "NBA",
            "WNBA",
            "NHL",
            "MLB",
            "Cricket",
            "Tennis",
            "Golf",
            "Formula 1",
            "NASCAR",
            "MotoGP",
            "Boxing",
            "Wrestling",
            "MMA",
            "Rugby",
            "Cycling",
            "Athletics",
            "Swimming",
            "Olympics",
            "Esports",
            "Volleyball",
            "Handball",
            "Table Tennis",
            "Badminton",
            "Futsal",
            "Women in Sports",
            "Global Highlights",
        ],
    },
}

MUSIC_AUDIO_URLS = [
    *[f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3" for i in range(1, 17)],
    "https://www.learningcontainer.com/wp-content/uploads/2020/02/Kalimba.mp3",
    "https://www.learningcontainer.com/wp-content/uploads/2020/02/Temple-Of-The-King.mp3",
]

PODCAST_SPOKEN_FALLBACK_URLS = [
    "https://archive.org/download/ifigeniaenaulide_2605_librivox/ifigeniaenaulide_01_euripides.mp3",
    "https://archive.org/download/ifigeniaenaulide_2605_librivox/ifigeniaenaulide_02_euripides.mp3",
    "https://archive.org/download/comentariossegundaparte_2605_librivox/comentariossegundaparte_01_servet.mp3",
    "https://archive.org/download/householdwords3_2605_librivox/householdwords3_01_dickens.mp3",
    "https://archive.org/download/richestman_2604_librivox/richestman_01_clason.mp3",
    "https://archive.org/download/decameron2_2604_librivox/decameron2_01_boccaccio.mp3",
]

OFFICIAL_SPORTS_CHANNELS: list[dict[str, str]] = [
    {
        "league": "NFL on CBS",
        "creator": "NFL",
        "event_stage": "Official Channel Stream",
        "channel_url": "https://www.youtube.com/@NFL",
        "fallback_channel_id": "UCDVYQ4Zhbm3S2dlz7P1GBDg",
        "fallback_video_id": "oeK8KHoLvaw",
        "source_label": "YouTube • NFL Official",
    },
    {
        "league": "UFC Main Card",
        "creator": "UFC",
        "event_stage": "Official Fight Night Stream",
        "channel_url": "https://www.youtube.com/@ufc",
        "fallback_channel_id": "UCvgfXK4nTYKudb0rFR6noLA",
        "fallback_video_id": "_m9jn2c6pTU",
        "source_label": "YouTube • UFC Official",
    },
    {
        "league": "UEFA Champions League",
        "creator": "UEFA",
        "event_stage": "Official Matchday Stream",
        "channel_url": "https://www.youtube.com/@UEFA",
        "fallback_channel_id": "UCyGa1YEx9ST66rYrJTGIKOw",
        "fallback_video_id": "A3nHp0A-_0g",
        "source_label": "YouTube • UEFA Official",
    },
    {
        "league": "CBS Sports HQ",
        "creator": "CBS Sports",
        "event_stage": "Official Sports Desk Live",
        "channel_url": "https://www.youtube.com/@CBSSports",
        "fallback_channel_id": "UCja8sZ2T4ylIqjggA1Zuukg",
        "fallback_video_id": "QHn4rgyKNZg",
        "source_label": "YouTube • CBS Sports Official",
    },
    {
        "league": "Local CBS Station",
        "creator": "CBS Sports HQ",
        "event_stage": "Official Local Sports Wrap",
        "channel_url": "https://www.youtube.com/@CBSSports",
        "fallback_channel_id": "UCja8sZ2T4ylIqjggA1Zuukg",
        "fallback_video_id": "QHn4rgyKNZg",
        "source_label": "YouTube • CBS Sports HQ Official",
    },
]

_PODCAST_SPOKEN_CACHE: list[str] = []
_PODCAST_SPOKEN_CACHE_TS: datetime | None = None
_SPORTS_CHANNEL_CACHE: dict[str, dict[str, Any]] = {}
_SPORTS_CHANNEL_CACHE_TS: dict[str, datetime] = {}
_SPORTS_EMBED_CHECK_CACHE: dict[str, dict[str, Any]] = {}
_SPORTS_EMBED_CHECK_CACHE_TS: dict[str, datetime] = {}

MUSIC_DISCOVERY_QUERIES: list[tuple[str, str]] = [
    ("Focus Flow", "focus instrumental"),
    ("Deep Work", "deep focus music"),
    ("Coding Beats", "coding beats"),
    ("Workout Energy", "workout mix"),
    ("Calm Piano", "calm piano"),
    ("Lo-Fi", "lofi hip hop"),
    ("Morning Boost", "morning motivation music"),
    ("Sleep Sound", "sleep ambient music"),
    ("Meditation", "meditation music"),
    ("Ambient Nature", "nature ambient"),
    ("Jazz Lounge", "jazz lounge"),
    ("Cinematic", "cinematic soundtrack"),
    ("Indie Mix", "indie pop"),
    ("Classical Essentials", "classical essentials"),
    ("Acoustic Calm", "acoustic chill"),
    ("Chill House", "chill house"),
    ("Afrobeats", "afrobeats"),
    ("Pop Hits", "pop hits"),
    ("R&B Soul", "rnb soul"),
    ("Electronic", "electronic dance"),
]

_REAL_ARTIST_POOL_CACHE: list[dict[str, Any]] = []
_REAL_ARTIST_POOL_CACHE_TS: datetime | None = None

CREATORS = [
    "Nova Audio",
    "Pulse Radio",
    "Elevate Studio",
    "Mindset Cast",
    "Focus Labs",
    "Signal Podcast",
    "Zen Waves",
    "Velocity Audio",
]


class AudioPlayRequest(BaseModel):
    item_id: str = Field(min_length=4, max_length=64)
    listen_seconds: int = Field(default=0, ge=0, le=86400)
    completed: bool = False
    source: str | None = None


class InboxMarkListenedRequest(BaseModel):
    item_id: str = Field(min_length=4, max_length=64)


class MlPipelineFlagRequest(BaseModel):
    enabled: bool


class FollowArtistRequest(BaseModel):
    artist_name: str = Field(min_length=2, max_length=120)


class FollowLeagueRequest(BaseModel):
    league_name: str = Field(min_length=2, max_length=120)


class SportsReminderSettingsRequest(BaseModel):
    league_name: str = Field(min_length=2, max_length=120)
    pre_kickoff_15_enabled: bool = False


class SportsBlackoutRulePayload(BaseModel):
    rule_id: str | None = Field(default=None, min_length=4, max_length=80)
    league: str = Field(min_length=2, max_length=120)
    countries: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    reason: str = Field(default="Regional rights restriction.", min_length=8, max_length=220)
    is_active: bool = True


class SportsCategoryCurationPayload(BaseModel):
    ordered_categories: list[str] = Field(default_factory=list)
    pinned_categories: list[str] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _today_key() -> str:
    return _now().strftime("%Y-%m-%d")


def _week_key() -> str:
    return _now().strftime("%G-W%V")


def _period_key(cadence: str) -> str:
    return _week_key() if str(cadence or "daily").lower() == "weekly" else _today_key()




def _stream_token_signature(payload_b64: str) -> str:
    secret = str(JWT_SECRET or "").encode("utf-8")
    return hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue_stream_token(user_id: str, item_id: str, expires_at: int) -> str:
    payload = {
        "u": str(user_id or "").strip(),
        "i": str(item_id or "").strip(),
        "e": int(expires_at),
        "v": 1,
        "s": "sports",
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = _stream_token_signature(payload_b64)
    return f"{payload_b64}.{sig}"


def _verify_stream_token(token: str, item_id: str) -> dict[str, Any] | None:
    text = str(token or "").strip()
    if not text or "." not in text:
        return None
    payload_b64, sig = text.split(".", 1)
    expected = _stream_token_signature(payload_b64)
    if not hmac.compare_digest(str(sig or ""), expected):
        return None
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload_json = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return None

    expires = int(payload.get("e") or 0)
    if expires <= int(_now().timestamp()):
        return None
    if str(payload.get("i") or "") != str(item_id or ""):
        return None
    if str(payload.get("s") or "") != "sports":
        return None
    return payload


def _build_sports_secure_stream_url(request: Request, user_id: str, item_id: str) -> str:
    exp = int((_now() + timedelta(seconds=SPORTS_STREAM_TOKEN_TTL_SECONDS)).timestamp())
    token = _issue_stream_token(user_id=user_id, item_id=item_id, expires_at=exp)
    query = urllib.parse.urlencode({"item_id": item_id, "token": token})
    return f"/api/sports/v2/secure-stream?{query}"


def _prepare_client_item(
    surface: str,
    item: dict[str, Any],
    *,
    request: Request,
    user_id: str,
    issue_secure_stream: bool,
) -> dict[str, Any]:
    row = dict(item or {})
    if surface != "sports":
        return row

    if bool(row.get("blackout_blocked")):
        row["stream_url"] = ""
        row["audio_url"] = ""
        row["youtube_embed_url"] = ""
        row["stream_protection"] = "blackout_locked"
        row["stream_token_ttl_seconds"] = 0
        row["watch_now_mode"] = "none"
        row["is_watchable_now"] = False
        return row

    embeddable = bool(row.get("is_embeddable_playable"))
    raw_stream = str(row.get("stream_url") or row.get("audio_url") or row.get("youtube_embed_url") or "").strip()
    if issue_secure_stream and raw_stream and embeddable:
        secure_url = _build_sports_secure_stream_url(request, user_id=user_id, item_id=str(row.get("item_id") or ""))
        row["stream_url"] = secure_url
        row["audio_url"] = secure_url
        if str(row.get("playback_type") or "") == "youtube":
            row["youtube_embed_url"] = secure_url
        row["stream_protection"] = "signed_stream_token_v1"
        row["stream_token_ttl_seconds"] = int(SPORTS_STREAM_TOKEN_TTL_SECONDS)
        row["watch_now_mode"] = "in_app_embed"
        row["is_watchable_now"] = True
        return row

    row["stream_url"] = ""
    row["audio_url"] = ""
    row["youtube_embed_url"] = ""
    if str(row.get("official_watch_url") or "").startswith("https://www.youtube.com/watch?v="):
        row["stream_protection"] = "external_official_link"
        row["watch_now_mode"] = "external_link"
        row["is_watchable_now"] = True
    else:
        row["stream_protection"] = "entitlement_locked"
        row["watch_now_mode"] = "none"
        row["is_watchable_now"] = False
    row["stream_token_ttl_seconds"] = 0
    return row


def _stable_index(seed: str, size: int) -> int:
    if size <= 0:
        return 0
    value = sum(ord(ch) for ch in str(seed or ""))
    return value % size


def _youtube_channel_id_from_page(html: str) -> str:
    text = str(html or "")
    patterns = [
        r'"externalId":"(UC[\w-]{20,})"',
        r'"channelId":"(UC[\w-]{20,})"',
        r'/channel/(UC[\w-]{20,})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _resolve_youtube_channel_id(channel_url: str) -> str:
    try:
        response = requests.get(
            str(channel_url or "").strip(),
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (RealAICoach Sports Ingest)"},
        )
        if response.status_code != 200:
            return ""
        return _youtube_channel_id_from_page(response.text)
    except Exception:
        return ""


def _youtube_latest_video_from_rss(channel_id: str) -> dict[str, Any]:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={urllib.parse.quote(channel_id)}"
    try:
        response = requests.get(
            feed_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (RealAICoach Sports Ingest)"},
        )
        if response.status_code != 200:
            return {}

        root = ET.fromstring(response.text)
        atom_ns = "{http://www.w3.org/2005/Atom}"
        yt_ns = "{http://www.youtube.com/xml/schemas/2015}"

        entry = root.find(f"{atom_ns}entry")
        if entry is None:
            return {}

        video_id = str((entry.find(f"{yt_ns}videoId") or ET.Element("x")).text or "").strip()
        title = str((entry.find(f"{atom_ns}title") or ET.Element("x")).text or "").strip()
        published = str((entry.find(f"{atom_ns}published") or ET.Element("x")).text or "").strip()
        if not video_id:
            return {}
        return {
            "video_id": video_id,
            "title": title,
            "published": published,
            "embed_url": f"https://www.youtube.com/embed/{video_id}",
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "is_live_hint": bool(re.search(r"\b(live|stream)\b", title.lower())),
        }
    except Exception:
        return {}


def _extract_youtube_video_id(embed_url: str) -> str:
    text = str(embed_url or "").strip()
    if not text:
        return ""
    match = re.search(r"/embed/([A-Za-z0-9_-]{8,})", text)
    if match:
        return str(match.group(1) or "")
    return ""


def _check_youtube_embed_playable(embed_url: str) -> dict[str, Any]:
    key = str(embed_url or "").strip()
    if not key:
        return {"is_playable": False, "score": 0, "reason": "missing_embed_url", "checked_at": _now_iso()}

    cached = _SPORTS_EMBED_CHECK_CACHE.get(key)
    cached_ts = _SPORTS_EMBED_CHECK_CACHE_TS.get(key)
    if cached and cached_ts and (_now() - cached_ts).total_seconds() < 10 * 60:
        return dict(cached)

    video_id = _extract_youtube_video_id(key)
    if not video_id:
        result = {"is_playable": False, "score": 0, "reason": "no_video_id", "checked_at": _now_iso()}
        _SPORTS_EMBED_CHECK_CACHE[key] = result
        _SPORTS_EMBED_CHECK_CACHE_TS[key] = _now()
        return result

    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(watch_url, safe='')}&format=json"
    try:
        response = requests.get(
            oembed_url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (RealAICoach Embeddability Check)"},
        )
        is_playable = response.status_code == 200
        result = {
            "is_playable": bool(is_playable),
            "score": 100 if is_playable else 10,
            "reason": "oembed_ok" if is_playable else f"oembed_{response.status_code}",
            "checked_at": _now_iso(),
        }
        try:
            embed_response = requests.get(
                key,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0 (RealAICoach Embed Probe)"},
            )
            if embed_response.status_code == 200:
                body = str(embed_response.text or "").lower()
                has_ok = (
                    ('"playabilitystatus":{"status":"ok"' in body)
                    or ('\\"playabilitystatus\\":{\\"status\\":\\"ok\\"' in body)
                    or ('"status":"ok"' in body)
                    or ('\\"status\\":\\"ok\\"' in body)
                )
                has_error = (
                    ("video unavailable" in body)
                    or ("video is unavailable" in body)
                    or ("player-unavailable" in body)
                    or ("video player configuration error" in body)
                    or ("error 153" in body)
                    or ('"playabilitystatus":{"status":"error"' in body)
                    or ('\\"playabilitystatus\\":{\\"status\\":\\"error\\"' in body)
                    or ('"status":"error"' in body)
                    or ('\\"status\\":\\"error\\"' in body)
                )
                if has_error:
                    result = {
                        "is_playable": False,
                        "score": 12,
                        "reason": "embed_playability_error",
                        "checked_at": _now_iso(),
                    }
                elif has_ok:
                    result = {
                        "is_playable": True,
                        "score": 78,
                        "reason": "embed_playability_ok",
                        "checked_at": _now_iso(),
                    }
                else:
                    result = {
                        "is_playable": bool(result.get("is_playable")),
                        "score": int(result.get("score") or 62),
                        "reason": str(result.get("reason") or "embed_http_200"),
                        "checked_at": _now_iso(),
                    }
        except Exception:
            pass
    except Exception:
        result = {
            "is_playable": False,
            "score": 5,
            "reason": "oembed_error",
            "checked_at": _now_iso(),
        }

    _SPORTS_EMBED_CHECK_CACHE[key] = result
    _SPORTS_EMBED_CHECK_CACHE_TS[key] = _now()
    return result


def _sports_channel_snapshot(channel: dict[str, Any], *, index: int) -> dict[str, Any]:
    channel_url = str(channel.get("channel_url") or "").strip()
    fallback_channel_id = str(channel.get("fallback_channel_id") or "").strip()
    fallback_video_id = str(channel.get("fallback_video_id") or "").strip()
    cache_key = channel_url or str(channel.get("league") or "")
    cached = _SPORTS_CHANNEL_CACHE.get(cache_key) or {}
    cached_ts = _SPORTS_CHANNEL_CACHE_TS.get(cache_key)
    if (
        cached
        and cached_ts
        and (_now() - cached_ts).total_seconds() < 45 * 60
        and str(cached.get("youtube_embed_url") or "").strip()
        and str(cached.get("latest_video_title") or "").strip()
    ):
        return {
            "league": str(channel.get("league") or "Sports"),
            "creator": str(channel.get("creator") or "Official Sports"),
            "event_stage": str(channel.get("event_stage") or "Official Stream"),
            "source_label": str(channel.get("source_label") or "YouTube Official"),
            **cached,
        }

    channel_id = fallback_channel_id or _resolve_youtube_channel_id(channel_url)
    latest = _youtube_latest_video_from_rss(channel_id) if (channel_id and not fallback_video_id) else {}
    fallback_embed = f"https://www.youtube.com/embed/{fallback_video_id}" if fallback_video_id else ""
    fallback_thumb = f"https://i.ytimg.com/vi/{fallback_video_id}/hqdefault.jpg" if fallback_video_id else ""
    fallback_watch = f"https://www.youtube.com/watch?v={fallback_video_id}" if fallback_video_id else ""
    live_embed = f"https://www.youtube.com/embed/live_stream?channel={channel_id}" if channel_id else ""
    latest_video_id = str(latest.get("video_id") or "").strip()
    latest_watch = f"https://www.youtube.com/watch?v={latest_video_id}" if latest_video_id else ""
    snapshot = {
        "channel_id": channel_id,
        "channel_url": channel_url,
        "youtube_embed_url": str(latest.get("embed_url") or fallback_embed or live_embed),
        "stream_url": str(latest.get("embed_url") or fallback_embed or live_embed),
        "official_watch_url": str(latest_watch or fallback_watch),
        "thumbnail_url": str(latest.get("thumbnail_url") or fallback_thumb),
        "latest_video_title": str(latest.get("title") or channel.get("event_stage") or ""),
        "latest_published_at": str(latest.get("published") or ""),
        "is_live_hint": bool(latest.get("is_live_hint") or (index % 3 == 0)),
    }
    _SPORTS_CHANNEL_CACHE[cache_key] = snapshot
    _SPORTS_CHANNEL_CACHE_TS[cache_key] = _now()

    return {
        "league": str(channel.get("league") or "Sports"),
        "creator": str(channel.get("creator") or "Official Sports"),
        "event_stage": str(channel.get("event_stage") or "Official Stream"),
        "source_label": str(channel.get("source_label") or "YouTube Official"),
        **snapshot,
    }


def _preferred_sports_league_for_category(category_hint: str, index: int) -> str:
    text = str(category_hint or "").strip().lower()
    if any(keyword in text for keyword in ["nfl", "football", "mlb", "nba", "wnba", "nhl", "college"]):
        return "NFL on CBS"
    if any(keyword in text for keyword in ["ufc", "mma", "boxing", "wrestling", "combat"]):
        return "UFC Main Card"
    if any(keyword in text for keyword in ["uefa", "soccer", "futsal", "rugby"]):
        return "UEFA Champions League"
    if any(keyword in text for keyword in ["local", "cbs"]):
        return "Local CBS Station"
    return ["CBS Sports HQ", "NFL on CBS", "UEFA Champions League", "UFC Main Card"][index % 4]


def _official_sports_stream_for_index(index: int, *, category_hint: str = "") -> dict[str, Any]:
    preferred_league = _preferred_sports_league_for_category(category_hint, index)
    primary_channel = next(
        (channel for channel in OFFICIAL_SPORTS_CHANNELS if str(channel.get("league") or "") == preferred_league),
        OFFICIAL_SPORTS_CHANNELS[index % len(OFFICIAL_SPORTS_CHANNELS)],
    )
    primary = _sports_channel_snapshot(primary_channel, index=index)
    primary_check = _check_youtube_embed_playable(str(primary.get("youtube_embed_url") or ""))
    primary["is_embeddable_playable"] = bool(primary_check.get("is_playable"))
    primary["embeddability_score"] = int(primary_check.get("score") or 0)
    primary["embeddability_reason"] = str(primary_check.get("reason") or "")
    primary["embeddability_checked_at"] = str(primary_check.get("checked_at") or _now_iso())
    primary["fallback_applied"] = False
    primary["fallback_from_league"] = ""

    if primary["is_embeddable_playable"]:
        return primary

    same_league_candidates = [
        channel for channel in OFFICIAL_SPORTS_CHANNELS
        if str(channel.get("league") or "").strip().lower() == str(preferred_league).strip().lower()
        and str(channel.get("channel_url") or "") != str(primary_channel.get("channel_url") or "")
    ]
    other_candidates = [
        channel for channel in OFFICIAL_SPORTS_CHANNELS
        if str(channel.get("channel_url") or "") != str(primary_channel.get("channel_url") or "")
        and channel not in same_league_candidates
    ]
    candidate_order = same_league_candidates + other_candidates

    best = dict(primary)
    for offset, candidate in enumerate(candidate_order):
        candidate_snapshot = _sports_channel_snapshot(candidate, index=index + offset + 1)
        check = _check_youtube_embed_playable(str(candidate_snapshot.get("youtube_embed_url") or ""))
        candidate_snapshot["is_embeddable_playable"] = bool(check.get("is_playable"))
        candidate_snapshot["embeddability_score"] = int(check.get("score") or 0)
        candidate_snapshot["embeddability_reason"] = str(check.get("reason") or "")
        candidate_snapshot["embeddability_checked_at"] = str(check.get("checked_at") or _now_iso())
        candidate_snapshot["fallback_applied"] = True
        candidate_snapshot["fallback_from_league"] = str(primary_channel.get("league") or "")

        if candidate_snapshot["is_embeddable_playable"]:
            return candidate_snapshot
        if int(candidate_snapshot.get("embeddability_score") or 0) > int(best.get("embeddability_score") or 0):
            best = candidate_snapshot

    return best


def _podcast_spoken_urls() -> list[str]:
    global _PODCAST_SPOKEN_CACHE, _PODCAST_SPOKEN_CACHE_TS
    if _PODCAST_SPOKEN_CACHE and _PODCAST_SPOKEN_CACHE_TS and (_now() - _PODCAST_SPOKEN_CACHE_TS).total_seconds() < 24 * 3600:
        return list(_PODCAST_SPOKEN_CACHE)

    discovered: list[str] = []
    try:
        search = requests.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": "collection:librivoxaudio AND mediatype:audio",
                "fl[]": "identifier",
                "rows": 24,
                "sort[]": "publicdate desc",
                "output": "json",
            },
            timeout=12,
        )
        docs = ((search.json() or {}).get("response") or {}).get("docs") or []
        identifiers = [str(doc.get("identifier") or "").strip() for doc in docs if str(doc.get("identifier") or "").strip()]
        for identifier in identifiers[:14]:
            meta = requests.get(f"https://archive.org/metadata/{identifier}", timeout=12)
            files = (meta.json() or {}).get("files") or []
            for f in files:
                name = str(f.get("name") or "")
                if not name.lower().endswith(".mp3"):
                    continue
                try:
                    duration = float(f.get("length") or 0)
                except Exception:
                    duration = 0.0
                if duration and duration < 300:
                    continue
                url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(name)}"
                if url not in discovered:
                    discovered.append(url)
                if len(discovered) >= 120:
                    break
            if len(discovered) >= 120:
                break
    except Exception:
        discovered = []

    if not discovered:
        discovered = list(PODCAST_SPOKEN_FALLBACK_URLS)
    _PODCAST_SPOKEN_CACHE = discovered
    _PODCAST_SPOKEN_CACHE_TS = _now()
    return list(_PODCAST_SPOKEN_CACHE)


def _real_artist_music_pool() -> list[dict[str, Any]]:
    global _REAL_ARTIST_POOL_CACHE, _REAL_ARTIST_POOL_CACHE_TS
    if _REAL_ARTIST_POOL_CACHE and _REAL_ARTIST_POOL_CACHE_TS and (_now() - _REAL_ARTIST_POOL_CACHE_TS).total_seconds() < 12 * 3600:
        return list(_REAL_ARTIST_POOL_CACHE)

    discovered: list[dict[str, Any]] = []
    seen_track_ids: set[str] = set()
    try:
        for category, query in MUSIC_DISCOVERY_QUERIES:
            resp = requests.get(
                "https://itunes.apple.com/search",
                params={
                    "term": query,
                    "media": "music",
                    "entity": "song",
                    "limit": 40,
                },
                timeout=10,
            )
            data = resp.json() if resp.status_code == 200 else {}
            for row in (data.get("results") or []):
                preview = str(row.get("previewUrl") or "").strip()
                track_id = str(row.get("trackId") or "").strip()
                if not preview or not track_id or track_id in seen_track_ids:
                    continue
                seen_track_ids.add(track_id)
                discovered.append(
                    {
                        "track_id": track_id,
                        "title": str(row.get("trackName") or "Unknown Track").strip()[:120],
                        "artist": str(row.get("artistName") or "Unknown Artist").strip()[:96],
                        "album": str(row.get("collectionName") or "Single").strip()[:120],
                        "audio_url": preview,
                        "thumbnail_url": str(row.get("artworkUrl100") or row.get("artworkUrl60") or "").strip(),
                        "duration_seconds": int((float(row.get("trackTimeMillis") or 0) / 1000) or 180),
                        "category": category,
                        "source_label": "iTunes Artist Preview",
                    }
                )
    except Exception:
        discovered = []

    if not discovered:
        discovered = [
            {
                "track_id": f"fallback-{idx}",
                "title": f"Studio Track {idx + 1}",
                "artist": "Curated Artist",
                "album": "Curated Sessions",
                "audio_url": MUSIC_AUDIO_URLS[idx % len(MUSIC_AUDIO_URLS)],
                "thumbnail_url": "",
                "duration_seconds": 180,
                "category": MUSIC_DISCOVERY_QUERIES[idx % len(MUSIC_DISCOVERY_QUERIES)][0],
                "source_label": "Fallback Stream",
            }
            for idx in range(24)
        ]

    _REAL_ARTIST_POOL_CACHE = discovered
    _REAL_ARTIST_POOL_CACHE_TS = _now()
    return list(_REAL_ARTIST_POOL_CACHE)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_timezone_name(raw: str | None) -> str:
    candidate = str(raw or "").strip()
    if not candidate:
        return "UTC"
    try:
        ZoneInfo(candidate)
        return candidate
    except Exception:
        return "UTC"


def _extract_timezone(request: Request) -> str:
    return _safe_timezone_name(str(request.query_params.get("tz") or ""))


def _normalize_country_code(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text[:2] if len(text) >= 2 else ""


def _normalize_state_code(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text[:3] if len(text) >= 2 else ""


async def _resolve_user_region(user: User, request: Request) -> dict[str, str]:
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

    country = _normalize_country_code(
        str(user_row.get("country_code") or user_row.get("country") or "")
    )
    state = _normalize_state_code(
        str(user_row.get("state_code") or user_row.get("state") or user_row.get("region") or "")
    )

    if not country:
        country = _normalize_country_code(
            request.headers.get("x-country-code")
            or request.headers.get("cf-ipcountry")
            or request.headers.get("x-vercel-ip-country")
            or request.headers.get("x-appengine-country")
            or request.query_params.get("country")
        )
    if not state:
        state = _normalize_state_code(
            request.headers.get("x-region-code")
            or request.headers.get("x-us-state")
            or request.headers.get("x-vercel-ip-country-region")
            or request.headers.get("x-appengine-region")
            or request.query_params.get("state")
        )

    return {
        "country_code": country,
        "state_code": state,
    }


async def _resolve_region_for_user_id(user_id: str, request: Request) -> dict[str, str]:
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

    country = _normalize_country_code(
        str(user_row.get("country_code") or user_row.get("country") or "")
    )
    state = _normalize_state_code(
        str(user_row.get("state_code") or user_row.get("state") or user_row.get("region") or "")
    )

    if not country:
        country = _normalize_country_code(
            request.headers.get("x-country-code")
            or request.headers.get("cf-ipcountry")
            or request.headers.get("x-vercel-ip-country")
            or request.headers.get("x-appengine-country")
            or request.query_params.get("country")
        )
    if not state:
        state = _normalize_state_code(
            request.headers.get("x-region-code")
            or request.headers.get("x-us-state")
            or request.headers.get("x-vercel-ip-country-region")
            or request.headers.get("x-appengine-region")
            or request.query_params.get("state")
        )

    return {
        "country_code": country,
        "state_code": state,
    }


async def _ensure_default_sports_blackout_rules() -> None:
    existing_count = await db[BLACKOUT_RULES_COLL].count_documents({}, limit=1)
    if existing_count > 0:
        return
    now_iso = _now_iso()
    docs = []
    for row in DEFAULT_SPORTS_BLACKOUT_RULES:
        docs.append(
            {
                "rule_id": str(row.get("rule_id") or f"rule_{uuid.uuid4().hex[:10]}"),
                "league": str(row.get("league") or "").strip()[:120],
                "league_lc": str(row.get("league") or "").strip().lower(),
                "countries": [
                    _normalize_country_code(str(x or ""))
                    for x in (row.get("countries") or [])
                    if _normalize_country_code(str(x or ""))
                ],
                "states": [
                    _normalize_state_code(str(x or ""))
                    for x in (row.get("states") or [])
                    if _normalize_state_code(str(x or ""))
                ],
                "start_at": str(row.get("start_at") or "").strip() or None,
                "end_at": str(row.get("end_at") or "").strip() or None,
                "reason": str(row.get("reason") or "Regional rights restriction.").strip()[:220],
                "is_active": bool(row.get("is_active", True)),
                "created_by": "system_seed",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )
    if docs:
        await db[BLACKOUT_RULES_COLL].insert_many(docs)


async def _active_sports_blackout_rules() -> list[dict[str, Any]]:
    await _ensure_default_sports_blackout_rules()
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


def _is_rule_time_active(rule: dict[str, Any], now_dt: datetime) -> bool:
    start_dt = _parse_iso_datetime(str(rule.get("start_at") or ""))
    end_dt = _parse_iso_datetime(str(rule.get("end_at") or ""))
    if start_dt and now_dt < start_dt:
        return False
    if end_dt and now_dt > end_dt:
        return False
    return True


def _evaluate_sports_blackout(
    item: dict[str, Any],
    region: dict[str, str],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    league_lc = str(item.get("league") or item.get("category") or "").strip().lower()
    country = _normalize_country_code(region.get("country_code"))
    state = _normalize_state_code(region.get("state_code"))
    now_dt = _now()

    for rule in rules:
        if str(rule.get("league_lc") or "").strip().lower() != league_lc:
            continue
        if not _is_rule_time_active(rule, now_dt):
            continue

        rule_countries = {
            _normalize_country_code(str(x or ""))
            for x in (rule.get("countries") or [])
            if _normalize_country_code(str(x or ""))
        }
        rule_states = {
            _normalize_state_code(str(x or ""))
            for x in (rule.get("states") or [])
            if _normalize_state_code(str(x or ""))
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

    return {
        "blocked": False,
        "reason": "",
        "rule_id": "",
    }


def _attach_blackout_metadata(item: dict[str, Any], blackout: dict[str, Any]) -> dict[str, Any]:
    row = dict(item or {})
    row["blackout_blocked"] = bool(blackout.get("blocked"))
    row["blackout_reason"] = str(blackout.get("reason") or "")
    row["blackout_rule_id"] = str(blackout.get("rule_id") or "")
    return row


def _normalize_category_name(value: str) -> str:
    return str(value or "").strip()[:80]


async def _get_sports_category_curation() -> dict[str, Any]:
    doc = await db[SPORTS_CATEGORY_CURATION_COLL].find_one(
        {"key": "global"},
        {"_id": 0, "ordered_categories": 1, "pinned_categories": 1},
    ) or {}
    ordered = [_normalize_category_name(x) for x in (doc.get("ordered_categories") or []) if _normalize_category_name(x)]
    pinned = [_normalize_category_name(x) for x in (doc.get("pinned_categories") or []) if _normalize_category_name(x)]
    return {
        "ordered_categories": ordered,
        "pinned_categories": pinned,
    }


async def _append_sports_source_replacement_history(user_id: str, rows: list[dict[str, Any]]) -> int:
    events: list[dict[str, Any]] = []
    now_iso = _now_iso()
    day_key = _today_key()
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
                "created_at": now_iso,
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


async def _is_ml_pipeline_enabled() -> bool:
    row = await db.system_runtime_flags.find_one({"key": ML_PIPELINE_FLAG_KEY}, {"_id": 0, "value": 1}) or {}
    if not row:
        return True
    value = row.get("value")
    if isinstance(value, dict):
        return bool(value.get("enabled"))
    return bool(value)


def _resolve_surface(surface: str) -> dict[str, Any]:
    cfg = SURFACE_CONFIG.get(str(surface or "").strip().lower())
    if not cfg:
        raise HTTPException(status_code=404, detail="Media surface not found")
    return cfg


def _resolve_plan(user: User) -> str:
    plan = compute_effective_plan(_build_user_doc(user))
    return plan if plan in PLAN_LEVEL else "free"


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


def _build_user_doc(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "full_access": bool(user.full_access),
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "subscription_end_date": user.subscription_end_date,
        "subscription_permanent": bool(user.subscription_permanent),
        "platform_role": user.platform_role,
        "employee_permissions": list(user.employee_permissions or []),
        "pending_subscription_transition": user.pending_subscription_transition,
    }


def _daily_play_limit(user: User) -> int:
    plan = _resolve_plan(user)
    entitlements = build_session_entitlements(_build_user_doc(user)).get("feature_entitlements") or {}
    entitlement_limit = entitlements.get("watch_videos_daily_watch_cap")
    if isinstance(entitlement_limit, int):
        return int(entitlement_limit)
    return int(PLAN_DAILY_PLAY_CAPS.get(plan, 0))


def _visible_plan_values(plan: str) -> list[str]:
    max_level = PLAN_LEVEL.get(plan, 0)
    return [name for name, level in PLAN_LEVEL.items() if level <= max_level]


def _min_plan_for_index(index: int) -> str:
    bucket = index % 10
    if bucket in {0, 1}:
        return "premium"
    if bucket in {2, 3, 4}:
        return "basic"
    return "free"


def _thumbnail_url(surface: str, index: int, category: str) -> str:
    seed = f"{surface}-{category}-{index:04d}".replace(" ", "-").lower()
    return f"https://picsum.photos/seed/{seed}/640/640"


def _build_catalog_item(surface: str, cfg: dict[str, Any], index: int, source_mode: str) -> dict[str, Any]:
    categories = list(cfg.get("categories") or [])
    category = categories[index % len(categories)] if categories else "General"
    creator = CREATORS[index % len(CREATORS)]
    playback_type = "audio"
    stream_url = ""
    youtube_embed_url = ""
    league = ""
    event_stage = ""
    is_live = False
    kickoff_at = _now_iso()
    official_source_url = ""
    official_watch_url = ""
    youtube_channel_id = ""
    is_embeddable_playable = False
    embeddability_score = 0
    embeddability_reason = ""
    embeddability_checked_at = ""
    fallback_applied = False
    fallback_from_league = ""

    if surface == "podcasts":
        spoken_urls = _podcast_spoken_urls()
        audio_url = spoken_urls[index % len(spoken_urls)] if spoken_urls else PODCAST_SPOKEN_FALLBACK_URLS[0]
        stream_url = audio_url
        source_label = "Open Story Podcast"
        artist_pool: list[dict[str, Any]] = []
    elif surface == "sports":
        sport_row = _official_sports_stream_for_index(index, category_hint=category)
        league = str(sport_row.get("league") or category)
        creator = str(sport_row.get("creator") or "CBS Sports")
        event_stage = str(sport_row.get("event_stage") or "Sports Event")
        stream_url = str(sport_row.get("stream_url") or "")
        youtube_embed_url = str(sport_row.get("youtube_embed_url") or stream_url)
        audio_url = stream_url
        source_label = str(sport_row.get("source_label") or "YouTube Official Sports Stream")
        official_source_url = str(sport_row.get("channel_url") or "")
        official_watch_url = str(sport_row.get("official_watch_url") or "")
        youtube_channel_id = str(sport_row.get("channel_id") or "")
        is_embeddable_playable = bool(sport_row.get("is_embeddable_playable"))
        embeddability_score = int(sport_row.get("embeddability_score") or 0)
        embeddability_reason = str(sport_row.get("embeddability_reason") or "")
        embeddability_checked_at = str(sport_row.get("embeddability_checked_at") or _now_iso())
        fallback_applied = bool(sport_row.get("fallback_applied"))
        fallback_from_league = str(sport_row.get("fallback_from_league") or "")
        playback_type = "youtube"
        is_live = bool(sport_row.get("is_live_hint") or (index % 3 == 0))
        if is_live:
            kickoff_at = (_now() - timedelta(minutes=(index % 42) + 3)).isoformat()
        else:
            kickoff_at = (_now() + timedelta(minutes=(index * 31) % (6 * 24 * 60))).isoformat()
        artist_pool = []
    else:
        artist_pool = _real_artist_music_pool()
        artist_row = artist_pool[index % len(artist_pool)] if artist_pool else {}
        category = str(artist_row.get("category") or category)
        creator = str(artist_row.get("artist") or creator)
        audio_url = str(artist_row.get("audio_url") or MUSIC_AUDIO_URLS[index % len(MUSIC_AUDIO_URLS)])
        stream_url = audio_url
        source_label = str(artist_row.get("source_label") or "Open Audio Stream")
    title_prefix = "Episode" if surface == "podcasts" else "Track"
    min_plan = _min_plan_for_index(index)
    item_id = f"{cfg['id_prefix']}_{index:04d}_{source_mode[:1]}"
    series_name = f"{category} Weekly" if surface == "podcasts" else ""
    host_name = f"{creator} Host" if surface == "podcasts" else ""
    artist_name = creator if surface == "audio_studio" else ""
    album_name = (
        str((artist_pool[index % len(artist_pool)] if surface == "audio_studio" and artist_pool else {}).get("album") or f"{category} Sessions")
        if surface == "audio_studio"
        else ""
    )

    if surface == "podcasts":
        title = f"{title_prefix} {index + 1}: {category} Session"
    elif surface == "sports":
        stream_title = str(sport_row.get("latest_video_title") or "").strip()
        title = stream_title[:140] if stream_title else f"{category} • {event_stage} #{index + 1}"
    else:
        title = str((artist_pool[index % len(artist_pool)] if surface == "audio_studio" and artist_pool else {}).get("title") or f"{title_prefix} {index + 1}: {category} Mix")

    thumbnail_url = (
        str((artist_pool[index % len(artist_pool)] if surface == "audio_studio" and artist_pool else {}).get("thumbnail_url") or "")
        if surface == "audio_studio"
        else str(sport_row.get("thumbnail_url") or "") if surface == "sports" else ""
    )
    duration_seconds = int(
        (artist_pool[index % len(artist_pool)] if surface == "audio_studio" and artist_pool else {}).get("duration_seconds")
        or (1800 + ((index * 53) % 3600) if surface == "sports" else (900 + ((index * 37) % 2100)))
    )

    return {
        "item_id": item_id,
        "title": title,
        "description": (
            (
                f"{cfg['label']} official {category.lower()} stream from verified sports channels."
                if surface == "sports"
                else f"{cfg['label']} curated {category.lower()} audio for high-retention listening experiences."
            )
        ),
        "category": category,
        "creator": creator,
        "content_kind": "podcast" if surface == "podcasts" else "sports" if surface == "sports" else "music",
        "series_name": series_name,
        "host_name": host_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "audio_url": audio_url,
        "stream_url": stream_url,
        "playback_type": playback_type,
        "youtube_embed_url": youtube_embed_url,
        "youtube_channel_id": youtube_channel_id,
        "official_source_url": official_source_url,
        "official_watch_url": official_watch_url,
        "league": league,
        "event_stage": event_stage,
        "is_embeddable_playable": bool(is_embeddable_playable),
        "embeddability_score": int(embeddability_score),
        "embeddability_reason": embeddability_reason,
        "embeddability_checked_at": embeddability_checked_at,
        "fallback_applied": bool(fallback_applied),
        "fallback_from_league": fallback_from_league,
        "is_watchable_now": bool(is_embeddable_playable or official_watch_url),
        "watch_now_mode": "in_app_embed" if bool(is_embeddable_playable) else "external_link" if bool(official_watch_url) else "none",
        "is_live": bool(is_live),
        "kickoff_at": kickoff_at,
        "thumbnail_url": thumbnail_url or _thumbnail_url(surface, index, category),
        "duration_seconds": duration_seconds,
        "min_plan": min_plan,
        "source_label": source_label,
        "source_trust_badge": "Official",
        "tags": [
            str(category).lower().replace(" ", "-"),
            str(cfg["label"]).lower().replace(" ", "-"),
            "video" if surface == "sports" else "audio",
            "stream",
            "spoken-word" if surface == "podcasts" else "sports" if surface == "sports" else "music",
        ],
        "is_active": True,
        "released_at": _now_iso(),
        "created_at": _now_iso(),
    }


def _derive_surface_identity_fields(surface: str, category: str, creator: str) -> dict[str, Any]:
    if surface == "podcasts":
        return {
            "content_kind": "podcast",
            "series_name": f"{category} Weekly",
            "host_name": f"{creator} Host",
            "artist_name": "",
            "album_name": "",
        }
    if surface == "sports":
        return {
            "content_kind": "sports",
            "series_name": "",
            "host_name": "",
            "artist_name": "",
            "album_name": "",
            "league": category,
            "event_stage": "Sports Event",
            "playback_type": "youtube",
        }
    return {
        "content_kind": "music",
        "series_name": "",
        "host_name": "",
        "artist_name": creator,
        "album_name": f"{category} Sessions",
    }


async def _backfill_surface_identity(surface: str, cfg: dict[str, Any]) -> int:
    coll = db[str(cfg["catalog_coll"])]
    rows = await coll.find(
        {
            "is_active": {"$ne": False},
            "$or": [
                {"content_kind": {"$exists": False}},
                {"host_name": {"$exists": False}},
                {"artist_name": {"$exists": False}},
            ],
        },
        {"_id": 0, "item_id": 1, "category": 1, "creator": 1},
    ).to_list(2000)

    updated = 0
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue
        category = str(row.get("category") or "General")
        creator = str(row.get("creator") or "Curated Creator")
        fields = _derive_surface_identity_fields(surface, category, creator)
        await coll.update_one({"item_id": item_id}, {"$set": fields})
        updated += 1
    return updated


async def _backfill_podcast_audio_streams(cfg: dict[str, Any]) -> int:
    coll = db[str(cfg["catalog_coll"])]
    spoken_urls = _podcast_spoken_urls()
    if not spoken_urls:
        return 0

    rows = await coll.find(
        {"is_active": {"$ne": False}},
        {"_id": 0, "item_id": 1, "audio_url": 1, "category": 1, "creator": 1},
    ).to_list(3000)

    updated = 0
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue
        current_url = str(row.get("audio_url") or "").strip().lower()
        needs_stream_fix = (
            "soundhelix" in current_url
            or "learningcontainer" in current_url
            or not current_url
        )
        if not needs_stream_fix:
            continue

        idx = _stable_index(item_id, len(spoken_urls))
        category = str(row.get("category") or "General")
        creator = str(row.get("creator") or "Curated Creator")
        identity = _derive_surface_identity_fields("podcasts", category, creator)
        await coll.update_one(
            {"item_id": item_id},
            {
                "$set": {
                    "audio_url": spoken_urls[idx],
                    "source_label": "Open Story Podcast",
                    "tags": [
                        str(category).lower().replace(" ", "-"),
                        "my-podcasts",
                        "spoken-word",
                        "series",
                    ],
                    **identity,
                }
            },
        )
        updated += 1
    return updated


async def _backfill_audio_studio_artist_streams(cfg: dict[str, Any]) -> int:
    coll = db[str(cfg["catalog_coll"])]
    pool = _real_artist_music_pool()
    if not pool:
        return 0

    rows = await coll.find(
        {"is_active": {"$ne": False}},
        {"_id": 0, "item_id": 1, "audio_url": 1},
    ).to_list(4000)
    updated = 0
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue
        idx = _stable_index(item_id, len(pool))
        artist_row = pool[idx]
        needs_refresh = "soundhelix" in str(row.get("audio_url") or "").lower() or "learningcontainer" in str(row.get("audio_url") or "").lower()
        if not needs_refresh:
            continue
        await coll.update_one(
            {"item_id": item_id},
            {
                "$set": {
                    "title": str(artist_row.get("title") or "Studio Track"),
                    "creator": str(artist_row.get("artist") or "Artist"),
                    "artist_name": str(artist_row.get("artist") or "Artist"),
                    "album_name": str(artist_row.get("album") or "Album"),
                    "audio_url": str(artist_row.get("audio_url") or ""),
                    "thumbnail_url": str(artist_row.get("thumbnail_url") or ""),
                    "duration_seconds": int(artist_row.get("duration_seconds") or 180),
                    "category": str(artist_row.get("category") or "Focus Flow"),
                    "source_label": str(artist_row.get("source_label") or "iTunes Artist Preview"),
                    "content_kind": "music",
                    "host_name": "",
                    "series_name": "",
                }
            },
        )
        updated += 1
    return updated


async def _backfill_sports_official_streams(cfg: dict[str, Any]) -> int:
    coll = db[str(cfg["catalog_coll"])]
    state_key = "watch_sports_official_streams_backfill_state_v2"
    state_doc = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0, "value": 1}) or {}
    state = state_doc.get("value") if isinstance(state_doc.get("value"), dict) else {}
    last_checked = _parse_iso_datetime(str(state.get("last_checked_at") or ""))
    if last_checked and (_now() - last_checked).total_seconds() < 15 * 60 and int(state.get("pending_count") or 0) == 0:
        return 0

    pending_filter = {
        "is_active": {"$ne": False},
        "$or": [
            {"stream_url": {"$regex": "mixkit\\.co", "$options": "i"}},
            {"audio_url": {"$regex": "mixkit\\.co", "$options": "i"}},
            {"playback_type": {"$ne": "youtube"}},
            {"youtube_embed_url": {"$exists": False}},
            {"youtube_embed_url": ""},
            {"youtube_embed_url": {"$regex": "live_stream\\?channel=", "$options": "i"}},
            {"official_source_url": {"$exists": False}},
            {"official_source_url": ""},
            {"source_label": {"$not": {"$regex": "^YouTube", "$options": "i"}}},
        ],
    }

    pending_count = int(await coll.count_documents(pending_filter))
    if pending_count == 0:
        await db.system_runtime_flags.update_one(
            {"key": state_key},
            {
                "$set": {
                    "key": state_key,
                    "value": {"pending_count": 0, "last_checked_at": _now_iso(), "updated_at": _now_iso()},
                    "updated_at": _now_iso(),
                }
            },
            upsert=True,
        )
        return 0

    rows = await coll.find(
        pending_filter,
        {
            "_id": 0,
            "item_id": 1,
            "stream_url": 1,
            "audio_url": 1,
            "youtube_embed_url": 1,
            "playback_type": 1,
            "official_source_url": 1,
            "official_watch_url": 1,
            "source_label": 1,
            "is_embeddable_playable": 1,
            "is_watchable_now": 1,
            "embeddability_score": 1,
            "watch_now_mode": 1,
            "category": 1,
            "creator": 1,
        },
    ).limit(180).to_list(180)

    updated = 0
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue

        raw_stream = str(row.get("stream_url") or row.get("audio_url") or "").strip().lower()
        playback_type = str(row.get("playback_type") or "").strip().lower()
        youtube_embed = str(row.get("youtube_embed_url") or "").strip()
        official_source_url = str(row.get("official_source_url") or "").strip()
        official_watch_url = str(row.get("official_watch_url") or "").strip()
        source_label = str(row.get("source_label") or "").strip().lower()
        has_embeddability_flags = row.get("is_embeddable_playable") is not None and row.get("embeddability_score") is not None
        has_watchability_flags = row.get("is_watchable_now") is not None and str(row.get("watch_now_mode") or "")
        needs_refresh = (
            "mixkit.co" in raw_stream
            or playback_type != "youtube"
            or not youtube_embed
            or "youtube.com/embed" not in youtube_embed
            or "live_stream?channel=" in youtube_embed
            or not official_source_url.startswith("https://www.youtube.com/")
            or not official_watch_url.startswith("https://www.youtube.com/watch?v=")
            or not source_label.startswith("youtube")
            or not has_embeddability_flags
            or not has_watchability_flags
        )
        if not needs_refresh:
            continue

        match = re.search(r"spt_(\d{4})_([a-z])", item_id)
        idx = int(match.group(1)) if match else _stable_index(item_id, max(len(OFFICIAL_SPORTS_CHANNELS), 1))
        mode_map = {"s": "seed", "d": "daily", "w": "weekly"}
        source_mode = mode_map.get(str(match.group(2) if match else "s"), "seed")
        fresh = _build_catalog_item("sports", cfg, idx, source_mode)

        category = str(row.get("category") or fresh.get("category") or "Sports")
        creator = str(row.get("creator") or fresh.get("creator") or "Official Sports")
        identity = _derive_surface_identity_fields("sports", category, creator)

        await coll.update_one(
            {"item_id": item_id},
            {
                "$set": {
                    "title": str(fresh.get("title") or item_id),
                    "description": str(fresh.get("description") or "Official sports stream."),
                    "stream_url": str(fresh.get("stream_url") or ""),
                    "audio_url": str(fresh.get("audio_url") or ""),
                    "youtube_embed_url": str(fresh.get("youtube_embed_url") or ""),
                    "youtube_channel_id": str(fresh.get("youtube_channel_id") or ""),
                    "official_source_url": str(fresh.get("official_source_url") or ""),
                    "official_watch_url": str(fresh.get("official_watch_url") or ""),
                    "is_embeddable_playable": bool(fresh.get("is_embeddable_playable")),
                    "embeddability_score": int(fresh.get("embeddability_score") or 0),
                    "embeddability_reason": str(fresh.get("embeddability_reason") or ""),
                    "embeddability_checked_at": str(fresh.get("embeddability_checked_at") or _now_iso()),
                    "fallback_applied": bool(fresh.get("fallback_applied")),
                    "fallback_from_league": str(fresh.get("fallback_from_league") or ""),
                    "is_watchable_now": bool(fresh.get("is_watchable_now")),
                    "watch_now_mode": str(fresh.get("watch_now_mode") or "none"),
                    "playback_type": "youtube",
                    "source_label": str(fresh.get("source_label") or "YouTube Official"),
                    "thumbnail_url": str(fresh.get("thumbnail_url") or ""),
                    "league": str(fresh.get("league") or category),
                    "event_stage": str(fresh.get("event_stage") or "Official Stream"),
                    "is_live": bool(fresh.get("is_live")),
                    "kickoff_at": str(fresh.get("kickoff_at") or _now_iso()),
                    "source_trust_badge": "Official",
                    "updated_at": _now_iso(),
                    **identity,
                }
            },
        )
        updated += 1

    await db.system_runtime_flags.update_one(
        {"key": state_key},
        {
            "$set": {
                "key": state_key,
                "value": {
                    "pending_count": max(int(pending_count - updated), 0),
                    "last_checked_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    return updated


async def _ensure_surface_seed(surface: str) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    coll = db[str(cfg["catalog_coll"])]
    count = await coll.count_documents({"is_active": {"$ne": False}})
    if count >= SEED_TARGET_COUNT:
        backfilled = await _backfill_surface_identity(surface, cfg)
        audio_stream_fixed = await _backfill_audio_studio_artist_streams(cfg) if surface == "audio_studio" else 0
        stream_fixed = await _backfill_podcast_audio_streams(cfg) if surface == "podcasts" else 0
        sports_stream_fixed = 0
        return {
            "status": "ready",
            "count": int(count),
            "backfilled_identity": int(backfilled),
            "backfilled_audio_artist_streams": int(audio_stream_fixed),
            "backfilled_streams": int(stream_fixed),
            "backfilled_sports_official_streams": int(sports_stream_fixed),
        }

    upserted = 0
    for i in range(SEED_TARGET_COUNT):
        item = _build_catalog_item(surface, cfg, i, "seed")
        item_set = {**item}
        item_set.pop("created_at", None)
        result = await coll.update_one(
            {"item_id": item["item_id"]},
            {"$set": item_set, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )
        if result.upserted_id is not None:
            upserted += 1

    backfilled = await _backfill_surface_identity(surface, cfg)
    audio_stream_fixed = await _backfill_audio_studio_artist_streams(cfg) if surface == "audio_studio" else 0
    stream_fixed = await _backfill_podcast_audio_streams(cfg) if surface == "podcasts" else 0
    sports_stream_fixed = 0
    return {
        "status": "seeded",
        "upserted": int(upserted),
        "count": int(await coll.count_documents({"is_active": {"$ne": False}})),
        "backfilled_identity": int(backfilled),
        "backfilled_audio_artist_streams": int(audio_stream_fixed),
        "backfilled_streams": int(stream_fixed),
        "backfilled_sports_official_streams": int(sports_stream_fixed),
    }


async def _active_entitled_users() -> list[dict[str, Any]]:
    rows = await db.users.find(
        {
            "access_locked": {"$ne": True},
            "$or": [
                {"subscription_status": "active"},
                {"subscription_permanent": True},
                {"full_access": True},
                {"is_admin": True},
            ],
        },
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1},
    ).to_list(120000)
    return [
        row for row in rows if str(row.get("user_id") or "").strip() and str(row.get("email") or "").strip()
    ]


async def _emit_daily_drop_notifications(cfg: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    users = await _active_entitled_users()
    if not users or not items:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    now_iso = _now_iso()
    titles = ", ".join([str(item.get("title") or "") for item in items[:3]])
    cadence = str(cfg.get("drop_cadence") or "daily").lower()
    is_weekly = cadence == "weekly"
    drop_type = "weekly_drop" if is_weekly else "daily_drop"
    drop_note = "This week's drop" if is_weekly else "Today's drop"
    reminder_type = "sports_weekly_drop" if is_weekly else "audio_daily_drop"
    verb = "watching" if str(cfg.get("feature_id") or "") == "watch-videos-sports" else "listening"
    docs: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user.get("user_id") or "").strip()
        if not user_id:
            continue
        nid = f"notif_{uuid.uuid4().hex[:12]}"
        docs.append(
            {
                "notification_id": nid,
                "id": nid,
                "user_id": user_id,
                "type": f"{cfg['feature_id']}_{drop_type}",
                "title": f"{len(items)} new releases in {cfg['label']}",
                "message": f"{drop_note}: {titles}",
                "action_url": str(cfg.get("route_hint") or "/features/watch-videos"),
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "feature_id": cfg["feature_id"],
                    "drop_key": _period_key(cadence),
                    "item_ids": [str(item.get("item_id") or "") for item in items],
                },
            }
        )

    if docs:
        await db.notifications.insert_many(docs)

    semaphore = asyncio.Semaphore(20)
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    item_ids = sorted(str(item.get("item_id") or item.get("id") or "") for item in items if str(item.get("item_id") or item.get("id") or ""))
    drop_hash = hashlib.sha256("|".join(item_ids).encode("utf-8", errors="ignore")).hexdigest()[:16] if item_ids else _period_key(cadence)

    async def _send_one(user: dict[str, Any]) -> bool:
        user_id = str(user.get("user_id") or "").strip()
        email = str(user.get("email") or "").strip()
        if not user_id or not email:
            return False
        email_normalized = email.lower()
        dedupe_key = f"{str(cfg.get('feature_id') or 'audio')}:{reminder_type}:{drop_hash}:{email_normalized}"
        try:
            async with semaphore:
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type=reminder_type,
                    channel="email",
                    recipient=email_normalized,
                    payload={"drop_hash": drop_hash, "feature_id": str(cfg.get("feature_id") or "")},
                )
                if not reserved:
                    return False

                result = await notify.reminder(
                    user_id=user_id,
                    email=email,
                    name=str(user.get("full_name") or user.get("name") or "there").strip() or "there",
                    title=f"{len(items)} new releases added in {cfg['label']}",
                    time_str=_now().strftime("%b %d, %Y %H:%M UTC"),
                    reminder_type=reminder_type,
                    details=(
                        f"Fresh {cfg['label']} content is live now: {titles}. "
                        f"Open {cfg['label']} to continue {verb}."
                    ),
                    dedupe_key=dedupe_key,
                )
            ok = bool(result.get("success"))
            await mark_dispatch_status(
                dedupe_key=dedupe_key,
                status="sent" if ok else "failed",
                extra={"sent_at": _now_iso(), "flow": "audio_daily_or_weekly_drop"} if ok else {"error": str(result.get("error") or "send_failed")[:300]},
            )
            return ok
        except Exception:
            try:
                await mark_dispatch_status(
                    dedupe_key=dedupe_key,
                    status="failed",
                    extra={"error": "exception"},
                )
            except Exception:
                pass
            return False

    results = await asyncio.gather(*[_send_one(user) for user in users], return_exceptions=True)
    sent = 0
    failed = 0
    for res in results:
        if isinstance(res, Exception):
            failed += 1
        elif res:
            sent += 1
        else:
            failed += 1
    return {
        "in_app_count": int(len(docs)),
        "email": {"attempted": int(len(users)), "sent": int(sent), "failed": int(failed)},
    }


async def _emit_followed_artist_release_alerts(cfg: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    if str(cfg.get("feature_id") or "") != "watch-videos-audio-studio":
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}
    if not items:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    artist_keys = {
        str(item.get("artist_name") or item.get("creator") or "").strip().lower()
        for item in items
        if str(item.get("artist_name") or item.get("creator") or "").strip()
    }
    if not artist_keys:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    follows = await db.watch_audio_artist_follows.find(
        {"artist_name_lc": {"$in": list(artist_keys)}},
        {"_id": 0, "user_id": 1, "artist_name": 1, "artist_name_lc": 1},
    ).to_list(25000)
    if not follows:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    item_by_artist: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("artist_name") or item.get("creator") or "").strip().lower()
        if key and key not in item_by_artist:
            item_by_artist[key] = item

    user_map: dict[str, list[dict[str, Any]]] = {}
    for follow in follows:
        user_id = str(follow.get("user_id") or "").strip()
        artist_key = str(follow.get("artist_name_lc") or "").strip().lower()
        matched_item = item_by_artist.get(artist_key)
        if not user_id or not matched_item:
            continue
        user_map.setdefault(user_id, []).append(matched_item)

    if not user_map:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    user_rows = await db.users.find(
        {"user_id": {"$in": list(user_map.keys())}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1},
    ).to_list(25000)
    user_index = {str(row.get("user_id") or ""): row for row in user_rows if str(row.get("user_id") or "").strip()}

    now_iso = _now_iso()
    docs: list[dict[str, Any]] = []
    email_jobs: list[dict[str, Any]] = []
    for user_id, matched_items in user_map.items():
        user_row = user_index.get(user_id) or {}
        email = str(user_row.get("email") or "").strip()
        if not email:
            continue
        hero = matched_items[0]
        artist = str(hero.get("artist_name") or hero.get("creator") or "Artist")
        item_id = str(hero.get("item_id") or "")
        item_title = str(hero.get("title") or "New release")
        deep_link = f"/features/audio-studio?playItem={item_id}"
        nid = f"notif_{uuid.uuid4().hex[:12]}"
        docs.append(
            {
                "notification_id": nid,
                "id": nid,
                "user_id": user_id,
                "type": "audio_studio_followed_artist_release",
                "title": f"New release from followed artist: {artist}",
                "message": f"{item_title} is live now. Tap to play instantly.",
                "action_url": deep_link,
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "feature_id": cfg["feature_id"],
                    "artist": artist,
                    "item_id": item_id,
                },
            }
        )
        email_jobs.append(
            {
                "user_id": user_id,
                "email": email,
                "name": str(user_row.get("full_name") or user_row.get("name") or "there").strip() or "there",
                "artist": artist,
                "item_title": item_title,
                "deep_link": deep_link,
            }
        )

    if docs:
        await db.notifications.insert_many(docs)

    semaphore = asyncio.Semaphore(20)
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    async def _dispatch_email_job(job: dict[str, Any]) -> bool:
        dedupe_key = ""
        try:
            async with semaphore:
                email_normalized = str(job.get("email") or "").strip().lower()
                item_key = str(job.get("item_title") or "").strip().lower()
                dedupe_key = f"followed-artist-release:{str(job.get('user_id') or '')}:{item_key}:{email_normalized}"
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type="followed_artist_release",
                    channel="email",
                    recipient=email_normalized,
                    payload={"item": item_key, "artist": str(job.get("artist") or "")},
                )
                if not reserved:
                    return False

                result = await notify.reminder(
                    user_id=str(job.get("user_id") or ""),
                    email=str(job.get("email") or ""),
                    name=str(job.get("name") or "there"),
                    title=f"{job.get('artist')} dropped a new release",
                    time_str=_now().strftime("%b %d, %Y %H:%M UTC"),
                    reminder_type="followed_artist_release",
                    details=(
                        f"Now live: {job.get('item_title')}. "
                        f"Open instantly: {job.get('deep_link')}"
                    ),
                    dedupe_key=dedupe_key,
                )
            ok = bool(result.get("success"))
            await mark_dispatch_status(
                dedupe_key=dedupe_key,
                status="sent" if ok else "failed",
                extra={"sent_at": _now_iso(), "flow": "followed_artist_release"} if ok else {"error": str(result.get("error") or "send_failed")[:300]},
            )
            return ok
        except Exception:
            if dedupe_key:
                try:
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="failed",
                        extra={"error": "exception"},
                    )
                except Exception:
                    pass
            return False

    outcomes = await asyncio.gather(*[_dispatch_email_job(job) for job in email_jobs], return_exceptions=True)
    sent = 0
    failed = 0
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            failed += 1
        elif outcome:
            sent += 1
        else:
            failed += 1

    return {
        "in_app_count": int(len(docs)),
        "email": {"attempted": int(len(email_jobs)), "sent": int(sent), "failed": int(failed)},
    }


async def _emit_followed_sports_league_alerts(cfg: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    if str(cfg.get("feature_id") or "") != "watch-videos-sports":
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}
    if not items:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    league_item_map: dict[str, dict[str, Any]] = {}
    for item in items:
        league_key = str(item.get("league") or item.get("category") or "").strip().lower()
        if league_key and league_key not in league_item_map:
            league_item_map[league_key] = item
    if not league_item_map:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    follows = await db.watch_sports_league_follows.find(
        {"league_name_lc": {"$in": list(league_item_map.keys())}},
        {"_id": 0, "user_id": 1, "league_name": 1, "league_name_lc": 1},
    ).to_list(25000)
    if not follows:
        return {"in_app_count": 0, "email": {"attempted": 0, "sent": 0, "failed": 0}}

    user_rows = await db.users.find(
        {"user_id": {"$in": [str(row.get("user_id") or "") for row in follows if str(row.get("user_id") or "")]}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1},
    ).to_list(25000)
    user_map = {str(row.get("user_id") or ""): row for row in user_rows if str(row.get("user_id") or "")}

    docs: list[dict[str, Any]] = []
    email_jobs: list[dict[str, Any]] = []
    now_iso = _now_iso()

    for follow in follows:
        user_id = str(follow.get("user_id") or "").strip()
        league_lc = str(follow.get("league_name_lc") or "").strip().lower()
        league_name = str(follow.get("league_name") or "").strip() or league_lc
        item = league_item_map.get(league_lc)
        user_row = user_map.get(user_id)
        if not user_id or not item or not user_row:
            continue
        email = str(user_row.get("email") or "").strip()
        if not email:
            continue

        item_id = str(item.get("item_id") or "")
        item_title = str(item.get("title") or "Sports event")
        deep_link = f"/features/sports?playItem={item_id}" if item_id else "/features/sports"
        nid = f"notif_{uuid.uuid4().hex[:12]}"
        docs.append(
            {
                "notification_id": nid,
                "id": nid,
                "user_id": user_id,
                "type": "sports_followed_league_release",
                "title": f"{league_name} weekly event is live",
                "message": f"{item_title} is now available. Tap to watch.",
                "action_url": deep_link,
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "feature_id": cfg["feature_id"],
                    "league": league_name,
                    "item_id": item_id,
                },
            }
        )
        email_jobs.append(
            {
                "user_id": user_id,
                "email": email,
                "name": str(user_row.get("full_name") or user_row.get("name") or "there").strip() or "there",
                "league": league_name,
                "item_title": item_title,
                "deep_link": deep_link,
            }
        )

    if docs:
        await db.notifications.insert_many(docs)

    semaphore = asyncio.Semaphore(20)
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    async def _dispatch_email_job(job: dict[str, Any]) -> bool:
        dedupe_key = ""
        try:
            async with semaphore:
                email_normalized = str(job.get("email") or "").strip().lower()
                item_key = str(job.get("item_title") or "").strip().lower()
                dedupe_key = f"followed-league-release:{str(job.get('user_id') or '')}:{item_key}:{email_normalized}"
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type="sports_league_weekly_release",
                    channel="email",
                    recipient=email_normalized,
                    payload={"item": item_key, "league": str(job.get("league") or "")},
                )
                if not reserved:
                    return False

                result = await notify.reminder(
                    user_id=str(job.get("user_id") or ""),
                    email=str(job.get("email") or ""),
                    name=str(job.get("name") or "there"),
                    title=f"{job.get('league')} weekly event reminder",
                    time_str=_now().strftime("%b %d, %Y %H:%M UTC"),
                    reminder_type="sports_league_weekly_release",
                    details=(
                        f"Now live: {job.get('item_title')}. "
                        f"Open instantly: {job.get('deep_link')}"
                    ),
                    dedupe_key=dedupe_key,
                )
            ok = bool(result.get("success"))
            await mark_dispatch_status(
                dedupe_key=dedupe_key,
                status="sent" if ok else "failed",
                extra={"sent_at": _now_iso(), "flow": "followed_sports_league_release"} if ok else {"error": str(result.get("error") or "send_failed")[:300]},
            )
            return ok
        except Exception:
            if dedupe_key:
                try:
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="failed",
                        extra={"error": "exception"},
                    )
                except Exception:
                    pass
            return False

    outcomes = await asyncio.gather(*[_dispatch_email_job(job) for job in email_jobs], return_exceptions=True)
    sent = 0
    failed = 0
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            failed += 1
        elif outcome:
            sent += 1
        else:
            failed += 1

    return {
        "in_app_count": int(len(docs)),
        "email": {"attempted": int(len(email_jobs)), "sent": int(sent), "failed": int(failed)},
    }


async def _run_surface_daily_drop(surface: str, *, triggered_by: str = "bootstrap") -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    state_doc = await db.system_runtime_flags.find_one({"key": cfg["state_key"]}, {"_id": 0, "value": 1}) or {}
    state = state_doc.get("value") if isinstance(state_doc.get("value"), dict) else {}
    cadence = str(cfg.get("drop_cadence") or "daily").lower()
    period_key = _period_key(cadence)
    if str(state.get("last_success_period") or "") == period_key:
        return {
            "status": "skipped",
            "reason": "already_completed_this_period",
            "day_key": period_key,
            "period_key": period_key,
            "cadence": cadence,
        }

    next_index = int(state.get("next_index") or SEED_TARGET_COUNT)
    coll = db[str(cfg["catalog_coll"])]
    drop_count = int(cfg.get("drop_count") or DAILY_DROP_COUNT)
    inserted_docs: list[dict[str, Any]] = []
    for i in range(drop_count):
        idx = next_index + i
        item = _build_catalog_item(surface, cfg, idx, cadence)
        item["drop_key"] = period_key
        item["drop_cadence"] = cadence
        await coll.insert_one(item)
        inserted_docs.append(item)

    await db.system_runtime_flags.update_one(
        {"key": cfg["state_key"]},
        {
            "$set": {
                "key": cfg["state_key"],
                "value": {
                    "last_success_period": period_key,
                    "next_index": next_index + drop_count,
                    "updated_at": _now_iso(),
                },
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    notify_summary = await _emit_daily_drop_notifications(cfg, inserted_docs)
    followed_artist_alerts = await _emit_followed_artist_release_alerts(cfg, inserted_docs)
    followed_league_alerts = await _emit_followed_sports_league_alerts(cfg, inserted_docs)
    summary = {
        "status": "ok",
        "day_key": period_key,
        "period_key": period_key,
        "cadence": cadence,
        "triggered_by": triggered_by,
        "inserted_count": int(len(inserted_docs)),
        "inserted_item_ids": [str(doc.get("item_id") or "") for doc in inserted_docs],
        "notifications": notify_summary,
        "followed_artist_alerts": followed_artist_alerts,
        "followed_league_alerts": followed_league_alerts,
    }
    await db[str(cfg["runs_coll"])].insert_one(
        {"feature_id": cfg["feature_id"], "day_key": period_key, "summary": summary, "created_at": _now_iso()}
    )
    return summary


def _catalog_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "item_id": 1,
        "title": 1,
        "description": 1,
        "category": 1,
        "creator": 1,
        "content_kind": 1,
        "series_name": 1,
        "host_name": 1,
        "artist_name": 1,
        "album_name": 1,
        "audio_url": 1,
        "stream_url": 1,
        "playback_type": 1,
        "youtube_embed_url": 1,
        "youtube_channel_id": 1,
        "official_source_url": 1,
        "official_watch_url": 1,
        "is_embeddable_playable": 1,
        "embeddability_score": 1,
        "embeddability_reason": 1,
        "embeddability_checked_at": 1,
        "fallback_applied": 1,
        "fallback_from_league": 1,
        "is_watchable_now": 1,
        "watch_now_mode": 1,
        "thumbnail_url": 1,
        "duration_seconds": 1,
        "min_plan": 1,
        "source_label": 1,
        "source_trust_badge": 1,
        "league": 1,
        "event_stage": 1,
        "is_live": 1,
        "kickoff_at": 1,
        "tags": 1,
        "released_at": 1,
        "created_at": 1,
    }


def _inbox_status_collection_name(surface: str) -> str:
    return f"watch_{surface}_daily_drop_inbox_status"


def _taste_profile_collection_name(surface: str) -> str:
    return f"watch_{surface}_taste_profiles"


def _behavioral_ai_collection_name(surface: str) -> str:
    return f"watch_{surface}_behavioral_ai"


async def _refresh_taste_profile(surface: str, user: User) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    history_rows = await db[str(cfg["history_coll"])].find(
        {"user_id": user.user_id},
        {"_id": 0, "category": 1, "listen_seconds": 1, "completed": 1, "duration_seconds": 1, "created_at": 1},
    ).sort([("created_at", -1)]).to_list(400)

    if not history_rows:
        profile = {
            "user_id": user.user_id,
            "preferred_categories": [],
            "skip_intent_by_category": {},
            "completion_rate": 0.0,
            "updated_at": _now_iso(),
        }
        await db[_taste_profile_collection_name(surface)].update_one(
            {"user_id": user.user_id},
            {"$set": profile, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )
        return profile

    category_stats: dict[str, dict[str, float]] = {}
    completed_count = 0
    for row in history_rows:
        category = str(row.get("category") or "General")
        listen_seconds = float(row.get("listen_seconds") or 0)
        duration_seconds = float(row.get("duration_seconds") or 0)
        completed = bool(row.get("completed"))
        if completed:
            completed_count += 1

        threshold = max(30.0, duration_seconds * 0.15)
        skip_flag = 1.0 if (not completed and listen_seconds < threshold) else 0.0

        bucket = category_stats.setdefault(category, {"plays": 0.0, "completion": 0.0, "skips": 0.0})
        bucket["plays"] += 1.0
        bucket["completion"] += 1.0 if completed else 0.0
        bucket["skips"] += skip_flag

    ranked_categories = sorted(
        category_stats.items(),
        key=lambda kv: (kv[1]["completion"] * 2.0 + kv[1]["plays"] - kv[1]["skips"] * 2.5),
        reverse=True,
    )
    preferred_categories = [cat for cat, _ in ranked_categories[:6]]
    skip_intent_by_category = {
        cat: round((stats["skips"] / max(1.0, stats["plays"])), 4)
        for cat, stats in category_stats.items()
    }
    profile = {
        "user_id": user.user_id,
        "preferred_categories": preferred_categories,
        "skip_intent_by_category": skip_intent_by_category,
        "completion_rate": round(completed_count / max(1, len(history_rows)), 4),
        "updated_at": _now_iso(),
    }
    await db[_taste_profile_collection_name(surface)].update_one(
        {"user_id": user.user_id},
        {"$set": profile, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return profile


async def _compute_habit_window(surface: str, user: User, timezone_name: str) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    tz = ZoneInfo(_safe_timezone_name(timezone_name))
    rows = await db[str(cfg["history_coll"])].find(
        {"user_id": user.user_id},
        {"_id": 0, "created_at": 1},
    ).sort([("created_at", -1)]).to_list(500)

    if not rows:
        return {
            "timezone": str(tz),
            "best_hour": 20,
            "label": "8:00 PM",
            "window": "evening",
            "confidence": 0.25,
        }

    hour_counts = [0] * 24
    for row in rows:
        dt = _parse_iso_datetime(str(row.get("created_at") or ""))
        if not dt:
            continue
        local_dt = dt.astimezone(tz)
        hour_counts[int(local_dt.hour)] += 1

    best_hour = max(range(24), key=lambda h: hour_counts[h])
    total = max(1, sum(hour_counts))
    confidence = hour_counts[best_hour] / total
    suffix = "AM" if best_hour < 12 else "PM"
    hour12 = best_hour % 12 or 12
    label = f"{hour12}:00 {suffix}"
    if 5 <= best_hour < 12:
        window = "morning"
    elif 12 <= best_hour < 17:
        window = "afternoon"
    elif 17 <= best_hour < 22:
        window = "evening"
    else:
        window = "night"

    return {
        "timezone": str(tz),
        "best_hour": int(best_hour),
        "label": label,
        "window": window,
        "confidence": round(confidence, 4),
    }


def _advanced_ml_rank(
    visible_rows: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    habit_window: dict[str, Any],
) -> list[dict[str, Any]]:
    preferred = list(profile.get("preferred_categories") or [])
    skip_map = profile.get("skip_intent_by_category") or {}
    best_hour = int(habit_window.get("best_hour") or 20)

    def _score(item: dict[str, Any]) -> float:
        category = str(item.get("category") or "General")
        recency_bonus = 0.0
        released = _parse_iso_datetime(str(item.get("released_at") or ""))
        if released:
            hours_old = max(1.0, (_now() - released).total_seconds() / 3600.0)
            recency_bonus = max(0.0, 4.0 - min(4.0, hours_old / 24.0))

        preference_bonus = 0.0
        if category in preferred:
            preference_bonus = float((len(preferred) - preferred.index(category)) * 2.2)

        skip_penalty = float(skip_map.get(category) or 0.0) * 4.0
        hour_alignment = 0.5 if 18 <= best_hour <= 23 else 0.2
        premium_bonus = 0.7 if str(item.get("min_plan") or "free") == "premium" else 0.1

        return recency_bonus + preference_bonus + hour_alignment + premium_bonus - skip_penalty

    return sorted(visible_rows, key=_score, reverse=True)


async def _adaptive_queue(surface: str, user: User, visible_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profile = await _refresh_taste_profile(surface, user)
    preferred = list(profile.get("preferred_categories") or [])
    skip_map = profile.get("skip_intent_by_category") or {}

    def _rank(item: dict[str, Any]) -> float:
        cat = str(item.get("category") or "General")
        pref_bonus = (len(preferred) - preferred.index(cat)) * 2.0 if cat in preferred else 0.0
        skip_penalty = float(skip_map.get(cat) or 0.0) * 3.0
        premium_bonus = 0.5 if str(item.get("min_plan") or "free") == "premium" else 0.0
        return pref_bonus + premium_bonus - skip_penalty

    ranked = sorted(visible_rows, key=_rank, reverse=True)
    explained: list[dict[str, Any]] = []
    for item in ranked[:18]:
        category = str(item.get("category") or "General")
        skip_intent = float(skip_map.get(category) or 0.0)
        if category in preferred[:3]:
            reason = f"Top category match: {category}"
        elif skip_intent <= 0.15:
            reason = f"Low-skip behavior in {category}"
        else:
            reason = "Fresh pick aligned with your listening pattern"
        explained.append({**item, "why_recommended": reason})
    return explained


def _parse_llm_json(raw_text: str) -> dict[str, Any]:
    clean = str(raw_text or "").strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}


def _fallback_behavioral_ai(visible_rows: list[dict[str, Any]], preferred_categories: list[str]) -> dict[str, Any]:
    follow_up_ids = [str(row.get("item_id") or "") for row in visible_rows[:8] if str(row.get("item_id") or "")]
    rail_title = "Continue your top categories" if preferred_categories else "Keep your momentum"
    return {
        "source": "deterministic",
        "reengagement_nudge": "You are one tap away from your next high-focus session.",
        "follow_up_item_ids": follow_up_ids[:8],
        "dynamic_rails": [{"title": rail_title, "item_ids": follow_up_ids[:10]}],
        "best_time_to_return": {"timezone": "UTC", "label": "8:00 PM", "window": "evening", "confidence": 0.25},
    }


async def _build_behavioral_ai(
    surface: str,
    user: User,
    visible_rows: list[dict[str, Any]],
    *,
    timezone_name: str,
) -> dict[str, Any]:
    profile = await _refresh_taste_profile(surface, user)
    preferred_categories = list(profile.get("preferred_categories") or [])
    habit_window = await _compute_habit_window(surface, user, timezone_name)
    fallback = _fallback_behavioral_ai(visible_rows, preferred_categories)
    fallback["best_time_to_return"] = habit_window
    if not visible_rows:
        return fallback

    ml_enabled = await _is_ml_pipeline_enabled()
    candidate_rows = _advanced_ml_rank(visible_rows, profile=profile, habit_window=habit_window) if ml_enabled else list(visible_rows)

    coll = db[_behavioral_ai_collection_name(surface)]
    cached = await coll.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    cached_snapshot = cached.get("snapshot") if isinstance(cached.get("snapshot"), dict) else {}
    cached_dt = _parse_iso_datetime(str(cached.get("updated_at") or ""))
    if (
        cached_dt
        and (_now() - cached_dt).total_seconds() <= BEHAVIORAL_AI_CACHE_HOURS * 3600
        and cached_snapshot
        and isinstance(cached_snapshot.get("best_time_to_return"), dict)
    ):
        return cached_snapshot

    if not EMERGENT_LLM_KEY:
        return fallback

    candidates = [
        {
            "item_id": str(row.get("item_id") or ""),
            "title": str(row.get("title") or ""),
            "category": str(row.get("category") or ""),
            "creator": str(row.get("creator") or ""),
        }
        for row in candidate_rows[:36]
        if str(row.get("item_id") or "")
    ]
    if not candidates:
        return fallback

    prompt = (
        "Return strict JSON only with keys: reengagement_nudge, follow_up_item_ids, dynamic_rails. "
        "reengagement_nudge <= 120 chars. "
        "follow_up_item_ids must use only provided candidate item_ids (max 8). "
        "dynamic_rails is an array (max 3) of {title, item_ids} using only candidate item_ids. "
        f"Preferred categories: {preferred_categories}. Habit window: {habit_window}. Candidates: {candidates}."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"wah-behavior-{surface}-{user.user_id}-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You are a retention strategist for media apps. "
                "Generate concise addictive-but-safe follow-up sequencing. Return JSON only."
            ),
        ).with_model("openai", "gpt-5.2")
        response = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=8.0)
        raw = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_llm_json(str(raw or ""))

        allowed_ids = {str(item.get("item_id") or "") for item in candidates}
        follow_up_item_ids = [
            item_id
            for item_id in [str(x or "").strip() for x in (parsed.get("follow_up_item_ids") or [])]
            if item_id in allowed_ids
        ][:8]

        dynamic_rails: list[dict[str, Any]] = []
        for rail in (parsed.get("dynamic_rails") or [])[:3]:
            if not isinstance(rail, dict):
                continue
            title = str(rail.get("title") or "").strip()[:72]
            item_ids = [
                item_id
                for item_id in [str(x or "").strip() for x in (rail.get("item_ids") or [])]
                if item_id in allowed_ids
            ][:10]
            if title and item_ids:
                dynamic_rails.append({"title": title, "item_ids": item_ids})

        snapshot = {
            "source": "ml+llm:gpt-5.2" if ml_enabled else "llm:gpt-5.2",
            "reengagement_nudge": str(parsed.get("reengagement_nudge") or "").strip()[:120]
            or fallback["reengagement_nudge"],
            "follow_up_item_ids": follow_up_item_ids or fallback["follow_up_item_ids"],
            "dynamic_rails": dynamic_rails or fallback["dynamic_rails"],
            "best_time_to_return": habit_window,
        }
        await coll.update_one(
            {"user_id": user.user_id},
            {
                "$set": {
                    "user_id": user.user_id,
                    "surface": surface,
                    "snapshot": snapshot,
                    "updated_at": _now_iso(),
                },
                "$setOnInsert": {"created_at": _now_iso()},
            },
            upsert=True,
        )
        return snapshot
    except Exception:
        fallback["source"] = "ml+deterministic" if ml_enabled else "deterministic"
        return fallback


def _materialize_items_by_ids(item_ids: list[str], item_map: dict[str, dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item_id in item_ids:
        item = item_map.get(str(item_id or "").strip())
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


async def _daily_drop_inbox(surface: str, user: User, *, limit: int = 18) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    rows = await db[str(cfg["catalog_coll"])].find(
        {"is_active": {"$ne": False}, "drop_key": {"$exists": True}},
        _catalog_projection(),
    ).sort([("released_at", -1)]).to_list(max(6, min(120, int(limit))))

    status_rows = await db[_inbox_status_collection_name(surface)].find(
        {"user_id": user.user_id},
        {"_id": 0, "item_id": 1, "listened": 1, "updated_at": 1},
    ).to_list(500)
    status_map = {
        str(row.get("item_id") or ""): bool(row.get("listened"))
        for row in status_rows
        if str(row.get("item_id") or "")
    }

    enriched = []
    unread = 0
    for row in rows:
        item_id = str(row.get("item_id") or "")
        listened = bool(status_map.get(item_id))
        if not listened:
            unread += 1
        enriched.append({**row, "listened": listened})

    return {
        "surface": surface,
        "total": int(len(enriched)),
        "unread": int(unread),
        "items": enriched,
    }


async def _followed_artists(user: User) -> list[str]:
    rows = await db.watch_audio_artist_follows.find(
        {"user_id": user.user_id},
        {"_id": 0, "artist_name": 1},
    ).to_list(1000)
    artists = []
    seen = set()
    for row in rows:
        name = str(row.get("artist_name") or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        artists.append(name)
    return artists


async def _followed_sports_leagues(user: User) -> list[str]:
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


async def _sports_league_reminder_settings(user: User) -> list[dict[str, Any]]:
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


async def _emit_user_pre_kickoff_reminders(user: User, rows: list[dict[str, Any]]) -> dict[str, Any]:
    follows = await db.watch_sports_league_follows.find(
        {"user_id": user.user_id, "pre_kickoff_15_enabled": True},
        {"_id": 0, "league_name_lc": 1, "league_name": 1},
    ).to_list(300)
    if not follows:
        return {"in_app_count": 0, "email_sent": 0}

    followed_keys = {str(row.get("league_name_lc") or "").strip().lower() for row in follows if str(row.get("league_name_lc") or "")}
    now_dt = _now()
    reminder_docs: list[dict[str, Any]] = []
    email_jobs: list[dict[str, Any]] = []

    fallback_name = str(getattr(user, "name", "") or "").strip()
    user_name = str(fallback_name or user.email.split("@")[0] or "there").strip() or "there"
    user_email = str(user.email or "").strip()
    if not user_email:
        return {"in_app_count": 0, "email_sent": 0}

    for row in rows[:220]:
        league_key = str(row.get("league") or row.get("category") or "").strip().lower()
        if league_key not in followed_keys:
            continue
        kickoff_dt = _parse_iso_datetime(str(row.get("kickoff_at") or ""))
        if not kickoff_dt:
            continue
        delta_seconds = (kickoff_dt - now_dt).total_seconds()
        if delta_seconds < 0 or delta_seconds > 15 * 60:
            continue
        item_id = str(row.get("item_id") or "")
        if not item_id:
            continue

        existing = await db.watch_sports_pre_kickoff_reminders.find_one(
            {"user_id": user.user_id, "item_id": item_id, "window": "15m"},
            {"_id": 0, "item_id": 1},
        )
        if existing:
            continue

        title = str(row.get("title") or "Sports event")
        deep_link = f"/features/sports?playItem={item_id}"
        nid = f"notif_{uuid.uuid4().hex[:12]}"
        reminder_docs.append(
            {
                "notification_id": nid,
                "id": nid,
                "user_id": user.user_id,
                "type": "sports_pre_kickoff_15",
                "title": "Kickoff in 15 minutes",
                "message": f"{title} starts soon. Join now.",
                "action_url": deep_link,
                "read": False,
                "created_at": _now_iso(),
                "meta": {"item_id": item_id, "window": "15m", "league": str(row.get("league") or row.get("category") or "")},
            }
        )
        email_jobs.append(
            {
                "item_id": item_id,
                "title": title,
                "deep_link": deep_link,
            }
        )
        await db.watch_sports_pre_kickoff_reminders.update_one(
            {"user_id": user.user_id, "item_id": item_id, "window": "15m"},
            {"$set": {"user_id": user.user_id, "item_id": item_id, "window": "15m", "sent_at": _now_iso()}},
            upsert=True,
        )

    if reminder_docs:
        await db.notifications.insert_many(reminder_docs)

    sent = 0
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status
    for job in email_jobs:
        dedupe_key = ""
        try:
            email_normalized = user_email.lower()
            item_key = str(job.get("item_id") or "").strip().lower()
            dedupe_key = f"sports_pre_kickoff_15:{user.user_id}:{item_key}:{email_normalized}"
            reserved = await reserve_dispatch_once(
                dedupe_key=dedupe_key,
                event_type="sports_pre_kickoff_15",
                channel="email",
                recipient=email_normalized,
                payload={"item_id": item_key, "title": str(job.get("title") or "")},
            )
            if not reserved:
                continue

            result = await notify.reminder(
                user_id=user.user_id,
                email=user_email,
                name=user_name,
                title="Kickoff in 15 minutes",
                time_str=_now().strftime("%b %d, %Y %H:%M UTC"),
                reminder_type="sports_pre_kickoff_15",
                details=f"{job.get('title')} starts in 15 minutes. Open now: {job.get('deep_link')}",
                dedupe_key=dedupe_key,
            )
            ok = bool(result.get("success"))
            await mark_dispatch_status(
                dedupe_key=dedupe_key,
                status="sent" if ok else "failed",
                extra={"sent_at": _now_iso(), "flow": "sports_pre_kickoff_15"} if ok else {"error": str(result.get("error") or "send_failed")[:300]},
            )
            if ok:
                sent += 1
        except Exception:
            if dedupe_key:
                try:
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="failed",
                        extra={"error": "exception"},
                    )
                except Exception:
                    pass
            continue

    return {"in_app_count": int(len(reminder_docs)), "email_sent": int(sent)}


def _followed_artist_releases(rows: list[dict[str, Any]], followed_artists: list[str]) -> list[dict[str, Any]]:
    if not followed_artists:
        return []
    keys = {name.lower() for name in followed_artists}
    matched = [
        row
        for row in rows
        if str(row.get("artist_name") or row.get("creator") or "").strip().lower() in keys
    ]
    return matched[:24]


async def _surface_quota_snapshot(surface: str, user: User) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    plan = _resolve_plan(user)
    limit = _daily_play_limit(user)
    day_key = _today_key()
    usage_rows = await db[str(cfg["usage_coll"])].aggregate(
        [
            {"$match": {"user_id": user.user_id, "day_key": day_key}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": {"$ifNull": ["$play_count", 1]}},
                }
            },
        ]
    ).to_list(length=1)
    used = int((usage_rows[0] or {}).get("total") or 0) if usage_rows else 0
    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "daily_play_limit": int(limit),
        "daily_play_used": int(used),
        "daily_play_remaining": -1 if int(limit) < 0 else max(0, int(limit) - int(used)),
    }


def _audio_source_health_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows = rows if isinstance(rows, list) else []
    total_items = int(len(normalized_rows))
    checked_at = _now_iso()

    if total_items <= 0:
        return {
            "status": "UNKNOWN",
            "reason_code": "AUDIO_STUDIO_SOURCE_HEALTH_EMPTY_CATALOG",
            "checked_at": checked_at,
            "total_items": 0,
            "playable_items": 0,
            "degraded_items": 0,
            "unavailable_items": 0,
            "secure_https_ratio": 0.0,
            "insecure_http_items": 0,
            "fallback_items": 0,
            "dominant_hosts": [],
            "auto_retry_recommended": True,
            "contract": {
                "allowed_statuses": ["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"],
                "deterministic": True,
            },
        }

    playable_items = 0
    degraded_items = 0
    unavailable_items = 0
    insecure_http_items = 0
    fallback_items = 0
    host_count: dict[str, int] = {}

    for row in normalized_rows:
        candidate_url = str(row.get("audio_url") or row.get("stream_url") or "").strip()
        if bool(row.get("fallback_applied")):
            fallback_items += 1

        if not candidate_url:
            unavailable_items += 1
            continue

        if candidate_url.startswith("https://"):
            playable_items += 1
        elif candidate_url.startswith("http://"):
            degraded_items += 1
            insecure_http_items += 1
        else:
            unavailable_items += 1

        host = str(urllib.parse.urlparse(candidate_url).netloc or "").strip().lower()
        if host:
            host_count[host] = int(host_count.get(host) or 0) + 1

    secure_https_ratio = round(float(playable_items) / float(max(total_items, 1)), 4)
    unavailable_ratio = float(unavailable_items) / float(max(total_items, 1))

    if playable_items <= 0:
        status = "UNAVAILABLE"
        reason_code = "AUDIO_STUDIO_SOURCE_HEALTH_NO_PLAYABLE_ITEMS"
    elif unavailable_ratio >= 0.25 or insecure_http_items > 0:
        status = "DEGRADED"
        reason_code = "AUDIO_STUDIO_SOURCE_HEALTH_PARTIAL_DEGRADATION"
    else:
        status = "HEALTHY"
        reason_code = "AUDIO_STUDIO_SOURCE_HEALTH_OK"

    dominant_hosts = [
        {"host": host, "count": int(count)}
        for host, count in sorted(host_count.items(), key=lambda x: x[1], reverse=True)[:6]
    ]

    return {
        "status": status,
        "reason_code": reason_code,
        "checked_at": checked_at,
        "total_items": int(total_items),
        "playable_items": int(playable_items),
        "degraded_items": int(degraded_items),
        "unavailable_items": int(unavailable_items),
        "secure_https_ratio": float(secure_https_ratio),
        "insecure_http_items": int(insecure_http_items),
        "fallback_items": int(fallback_items),
        "dominant_hosts": dominant_hosts,
        "auto_retry_recommended": bool(status in {"DEGRADED", "UNAVAILABLE"}),
        "contract": {
            "allowed_statuses": ["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"],
            "deterministic": True,
        },
    }


async def _surface_bootstrap(surface: str, request: Request) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    user = await require_auth(request)
    timezone_name = _extract_timezone(request)
    await db.watch_audio_user_context.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "user_id": user.user_id,
                "timezone": timezone_name,
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )

    await _ensure_surface_seed(surface)
    daily_drop = await _run_surface_daily_drop(surface, triggered_by=f"bootstrap:{surface}")

    quota = await _surface_quota_snapshot(surface, user)
    visible_min_plans = _visible_plan_values(str(quota.get("plan") or "free"))
    rows = await db[str(cfg["catalog_coll"])].find(
        {"is_active": {"$ne": False}, "min_plan": {"$in": visible_min_plans}},
        _catalog_projection(),
    ).sort([("released_at", -1)]).to_list(600)

    locked_premium_picks = await db[str(cfg["catalog_coll"])].find(
        {
            "is_active": {"$ne": False},
            "min_plan": {"$in": ["basic", "premium"]},
        },
        _catalog_projection(),
    ).sort([("released_at", -1)]).to_list(18)

    sports_region = {"country_code": "", "state_code": ""}
    sports_blackout_rules: list[dict[str, Any]] = []
    if surface == "sports":
        sports_region = await _resolve_user_region(user, request)
        sports_blackout_rules = await _active_sports_blackout_rules()

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        blackout = (
            _evaluate_sports_blackout(row, sports_region, sports_blackout_rules)
            if surface == "sports"
            else {"blocked": False, "reason": "", "rule_id": ""}
        )
        enriched = _attach_blackout_metadata(row, blackout)
        normalized_rows.append(
            _prepare_client_item(
                surface,
                enriched,
                request=request,
                user_id=user.user_id,
                issue_secure_stream=not bool(blackout.get("blocked")) if surface == "sports" else True,
            )
        )
    rows = normalized_rows

    normalized_locked_picks: list[dict[str, Any]] = []
    for row in locked_premium_picks:
        blackout = (
            _evaluate_sports_blackout(row, sports_region, sports_blackout_rules)
            if surface == "sports"
            else {"blocked": False, "reason": "", "rule_id": ""}
        )
        enriched = _attach_blackout_metadata(row, blackout)
        normalized_locked_picks.append(
            _prepare_client_item(
                surface,
                enriched,
                request=request,
                user_id=user.user_id,
                issue_secure_stream=False,
            )
        )
    locked_premium_picks = normalized_locked_picks

    sports_curation = {"ordered_categories": [], "pinned_categories": []}
    pinned_set: set[str] = set()
    order_map: dict[str, int] = {}
    if surface == "sports":
        sports_curation = await _get_sports_category_curation()
        pinned_set = {str(x or "") for x in (sports_curation.get("pinned_categories") or []) if str(x or "")}
        order_map = {
            str(cat or ""): idx
            for idx, cat in enumerate(sports_curation.get("ordered_categories") or [])
            if str(cat or "")
        }

    if surface == "sports":
        rows = sorted(
            rows,
            key=lambda row: (
                0 if bool(row.get("blackout_blocked")) else 1,
                1 if bool(row.get("is_watchable_now")) else 0,
                1 if bool(row.get("is_embeddable_playable")) else 0,
                1 if str(row.get("category") or "") in pinned_set else 0,
                -int(order_map.get(str(row.get("category") or ""), 10_000)),
                int(row.get("embeddability_score") or 0),
                str(row.get("released_at") or ""),
            ),
            reverse=True,
        )

    adaptive_next_queue = await _adaptive_queue(surface, user, rows)
    daily_drop_inbox = await _daily_drop_inbox(surface, user, limit=24)
    behavioral_ai = await _build_behavioral_ai(surface, user, rows, timezone_name=timezone_name)
    ml_pipeline_enabled = await _is_ml_pipeline_enabled()

    row_map = {
        str(row.get("item_id") or ""): row
        for row in rows
        if str(row.get("item_id") or "")
    }
    smart_follow_up_items = _materialize_items_by_ids(
        [str(x or "") for x in (behavioral_ai.get("follow_up_item_ids") or [])],
        row_map,
        limit=10,
    )
    behavioral_rails: list[dict[str, Any]] = []
    for rail in (behavioral_ai.get("dynamic_rails") or [])[:3]:
        if not isinstance(rail, dict):
            continue
        title = str(rail.get("title") or "").strip()[:72]
        rail_items = _materialize_items_by_ids(
            [str(x or "") for x in (rail.get("item_ids") or [])],
            row_map,
            limit=10,
        )
        if title and rail_items:
            behavioral_rails.append({"title": title, "items": rail_items})

    featured_item = (
        next((row for row in rows if not bool(row.get("blackout_blocked"))), rows[0])
        if surface == "sports" and rows
        else (rows[0] if rows else None)
    )
    total_catalog = await db[str(cfg["catalog_coll"])].count_documents({"is_active": {"$ne": False}})
    followed_artists = await _followed_artists(user) if surface == "audio_studio" else []
    followed_artist_new_releases = _followed_artist_releases(rows, followed_artists) if surface == "audio_studio" else []
    followed_leagues = await _followed_sports_leagues(user) if surface == "sports" else []
    league_reminder_settings = await _sports_league_reminder_settings(user) if surface == "sports" else []
    pre_kickoff_reminders = await _emit_user_pre_kickoff_reminders(user, rows) if surface == "sports" else {"in_app_count": 0, "email_sent": 0}
    source_history_inserted = await _append_sports_source_replacement_history(user.user_id, rows) if surface == "sports" else 0
    sports_playability_summary = {
        "playable_count": int(sum(1 for row in rows if bool(row.get("is_embeddable_playable")))),
        "watchable_count": int(sum(1 for row in rows if bool(row.get("is_watchable_now")))),
        "total_count": int(len(rows)),
    } if surface == "sports" else {"playable_count": 0, "watchable_count": 0, "total_count": 0}

    categories = sorted({str(row.get("category") or "General") for row in rows})
    if surface == "sports":
        categories = sorted(
            categories,
            key=lambda cat: (
                1 if cat in pinned_set else 0,
                -int(order_map.get(cat, 10_000)),
                cat,
            ),
            reverse=True,
        )

    source_health = (
        _audio_source_health_summary(rows)
        if surface == "audio_studio"
        else {
            "status": "NOT_APPLICABLE",
            "reason_code": "SOURCE_HEALTH_NOT_APPLICABLE_FOR_SURFACE",
            "checked_at": _now_iso(),
            "total_items": int(len(rows)),
            "playable_items": int(len(rows)),
            "degraded_items": 0,
            "unavailable_items": 0,
            "secure_https_ratio": 1.0,
            "insecure_http_items": 0,
            "fallback_items": 0,
            "dominant_hosts": [],
            "auto_retry_recommended": False,
            "contract": {
                "allowed_statuses": ["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "NOT_APPLICABLE"],
                "deterministic": True,
            },
        }
    )

    return {
        "feature_id": cfg["feature_id"],
        "label": cfg["label"],
        "quota": quota,
        "categories": categories,
        "total_catalog": int(total_catalog),
        "total_visible": int(len(rows)),
        "featured_item": featured_item,
        "catalog": rows,
        "locked_premium_picks": locked_premium_picks,
        "adaptive_next_queue": adaptive_next_queue,
        "behavioral_ai": behavioral_ai,
        "ml_pipeline_enabled": bool(ml_pipeline_enabled),
        "smart_follow_up_items": smart_follow_up_items,
        "behavioral_rails": behavioral_rails,
        "source_health": source_health,
        "followed_artists": followed_artists,
        "followed_artist_new_releases": followed_artist_new_releases,
        "followed_leagues": followed_leagues,
        "league_reminder_settings": league_reminder_settings,
        "pre_kickoff_reminders": pre_kickoff_reminders,
        "source_replacement_history_inserted": int(source_history_inserted),
        "sports_playability_summary": sports_playability_summary,
        "category_curation": sports_curation,
        "daily_drop_inbox": daily_drop_inbox,
        "daily_drop": daily_drop,
        "playback_security": {
            "mode": "signed_stream_token_v1" if surface == "sports" else "standard_stream",
            "drm_ready": bool(surface == "sports"),
            "token_ttl_seconds": int(SPORTS_STREAM_TOKEN_TTL_SECONDS) if surface == "sports" else 0,
            "raw_stream_exposed": bool(surface != "sports"),
        },
        "regional_access": {
            "country_code": str(sports_region.get("country_code") or "") if surface == "sports" else "",
            "state_code": str(sports_region.get("state_code") or "") if surface == "sports" else "",
            "active_blackout_rules": int(len(sports_blackout_rules)) if surface == "sports" else 0,
            "blackout_mode": "show_card_lock_playback" if surface == "sports" else "none",
        },
    }


async def _surface_play(surface: str, request: Request, payload: AudioPlayRequest) -> dict[str, Any]:
    cfg = _resolve_surface(surface)
    user = await require_auth(request)
    await _ensure_surface_seed(surface)

    quota = await _surface_quota_snapshot(surface, user)
    plan = str(quota.get("plan") or "free")

    item = await db[str(cfg["catalog_coll"])].find_one(
        {"item_id": payload.item_id, "is_active": {"$ne": False}},
        _catalog_projection(),
    )
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")

    item_plan = str(item.get("min_plan") or "free")
    if PLAN_LEVEL.get(item_plan, 0) > PLAN_LEVEL.get(plan, 0):
        raise HTTPException(
            status_code=403,
            detail=f"{_scope_label(plan)}: this title requires {item_plan.upper()} plan",
        )

    if surface == "sports":
        sports_region = await _resolve_user_region(user, request)
        sports_blackout_rules = await _active_sports_blackout_rules()
        blackout = _evaluate_sports_blackout(item, sports_region, sports_blackout_rules)
        if bool(blackout.get("blocked")):
            raise HTTPException(
                status_code=403,
                detail=str(blackout.get("reason") or "This event is currently unavailable in your region."),
            )

    limit = int(quota.get("daily_play_limit") or 0)
    day_key = _today_key()
    usage_coll = db[str(cfg["usage_coll"])]
    used_count = int(quota.get("daily_play_used") or 0)
    if limit >= 0 and used_count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"{_scope_label(plan)}: daily play cap reached ({used_count}/{limit})",
        )

    now_iso = _now_iso()
    update_doc = {
        "$set": {
            "user_id": user.user_id,
            "item_id": payload.item_id,
            "day_key": day_key,
            "listen_seconds": int(payload.listen_seconds),
            "completed": bool(payload.completed),
            "source": str(payload.source or "catalog").strip()[:48],
            "updated_at": now_iso,
        },
        "$inc": {
            "play_count": 1,
            "listen_seconds_total": int(payload.listen_seconds),
        },
        "$setOnInsert": {"created_at": now_iso},
    }
    await usage_coll.update_one(
        {"user_id": user.user_id, "item_id": payload.item_id, "day_key": day_key},
        update_doc,
        upsert=True,
    )
    await db[str(cfg["history_coll"])].insert_one(
        {
            "user_id": user.user_id,
            "item_id": payload.item_id,
            "category": str(item.get("category") or "General"),
            "duration_seconds": int(item.get("duration_seconds") or 0),
            "listen_seconds": int(payload.listen_seconds),
            "completed": bool(payload.completed),
            "source": str(payload.source or "catalog").strip()[:48],
            "created_at": now_iso,
        }
    )

    await _refresh_taste_profile(surface, user)

    refreshed_quota = await _surface_quota_snapshot(surface, user)
    client_item = _prepare_client_item(
        surface,
        _attach_blackout_metadata(item, {"blocked": False, "reason": "", "rule_id": ""}),
        request=request,
        user_id=user.user_id,
        issue_secure_stream=True,
    )
    return {
        "ok": True,
        "feature_id": cfg["feature_id"],
        "item": client_item,
        "quota": refreshed_quota,
        "playback_security": {
            "mode": "signed_stream_token_v1" if surface == "sports" else "standard_stream",
            "token_ttl_seconds": int(SPORTS_STREAM_TOKEN_TTL_SECONDS) if surface == "sports" else 0,
            "drm_ready": bool(surface == "sports"),
        },
    }


@router.get("/admin/behavioral-ml-flag")
async def get_behavioral_ml_flag(request: Request):
    await require_admin(request)
    row = await db.system_runtime_flags.find_one({"key": ML_PIPELINE_FLAG_KEY}, {"_id": 0, "value": 1, "updated_at": 1}) or {}
    value = row.get("value")
    enabled = bool(value.get("enabled")) if isinstance(value, dict) else bool(value)
    return {
        "key": ML_PIPELINE_FLAG_KEY,
        "enabled": enabled,
        "updated_at": row.get("updated_at"),
    }


@router.post("/admin/behavioral-ml-flag")
async def set_behavioral_ml_flag(request: Request, payload: MlPipelineFlagRequest):
    await require_admin(request)
    now_iso = _now_iso()
    await db.system_runtime_flags.update_one(
        {"key": ML_PIPELINE_FLAG_KEY},
        {
            "$set": {
                "key": ML_PIPELINE_FLAG_KEY,
                "value": {"enabled": bool(payload.enabled)},
                "updated_at": now_iso,
            },
            "$setOnInsert": {"created_at": now_iso},
        },
        upsert=True,
    )
    return {"ok": True, "key": ML_PIPELINE_FLAG_KEY, "enabled": bool(payload.enabled)}



