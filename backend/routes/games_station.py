"""Feature 22 — FPS Game.

Web-native re-implementation of Armour/Multiplayer-FPS (MIT licensed,
Unity + Photon PUN2) integrated into the RealAICoach platform:
- Room-based multiplayer (join or create room by name) — Photon replaced
  by FastAPI WebSockets (see ws_endpoints.py -> handle_fps_ws).
- Server-authoritative health / kill / respawn loop.
- Player models: policeman, robotx, roboty (as in the source repository).
Canonical feature_id remains "games-station" (platform registry contract).
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel, Field

from .db import User, db, require_auth
from utils.access_control_engine import compute_effective_plan


router = APIRouter(prefix="/games-station", tags=["FPS Game"])


PLAYER_MODELS = {"policeman", "robotx", "roboty"}
MAX_PLAYERS_PER_ROOM = 8
MAX_HP = 100
HIT_DAMAGE = 10
RESPAWN_SECONDS = 3.0
RECONNECT_GRACE_SECONDS = 20.0
XP_PER_KILL = 100
XP_PER_MATCH = 50
XP_MILESTONE_BONUS = 25
XP_PER_LEVEL = 500
STREAK_MILESTONES = {2: "double_kill", 3: "killing_spree", 5: "rampage", 7: "unstoppable"}


def _level_for(xp: int) -> int:
    return int(max(0, xp) // XP_PER_LEVEL) + 1

SPAWN_POINTS = [
    (-22.0, 1.7, -22.0),
    (22.0, 1.7, -22.0),
    (-22.0, 1.7, 22.0),
    (22.0, 1.7, 22.0),
    (0.0, 1.7, -24.0),
    (0.0, 1.7, 24.0),
    (-24.0, 1.7, 0.0),
    (24.0, 1.7, 0.0),
]

PLAN_CONFIG: dict[str, dict[str, Any]] = {
    "free": {
        "daily_gameplay_limit": 18,
        "max_rooms_created_daily": 3,
        "leaderboard_visibility": 10,
        "scope_label": "Limited access",
    },
    "basic": {
        "daily_gameplay_limit": 220,
        "max_rooms_created_daily": 30,
        "leaderboard_visibility": 50,
        "scope_label": "Almost unlimited access",
    },
    "premium": {
        "daily_gameplay_limit": -1,
        "max_rooms_created_daily": -1,
        "leaderboard_visibility": 250,
        "scope_label": "Full unlimited access",
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _today_key() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _safe_plan(plan: str) -> str:
    candidate = str(plan or "free").strip().lower()
    return candidate if candidate in PLAN_CONFIG else "free"


def _resolve_plan(user: User) -> str:
    payload = {
        "is_admin": bool(user.is_admin),
        "full_access": bool(user.full_access),
        "subscription_permanent": bool(user.subscription_permanent),
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "subscription_end_date": user.subscription_end_date,
        "payment_verified": bool(getattr(user, "payment_verified", False)),
        "pending_subscription_transition": user.pending_subscription_transition,
    }
    return _safe_plan(compute_effective_plan(payload))


def _slugify_room(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug[:48]


async def _get_or_create_profile(user: User) -> dict[str, Any]:
    profile = await db.fps_game_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
    if not profile:
        profile = {
            "user_id": user.user_id,
            "display_name": user.name or user.email.split("@")[0],
            "preferred_model": "policeman",
            "kills": 0,
            "deaths": 0,
            "matches_played": 0,
            "best_kill_streak": 0,
            "daily_plays": {"date": _today_key(), "value": 0},
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
        await db.fps_game_profiles.insert_one({**profile})
    if profile.get("daily_plays", {}).get("date") != _today_key():
        profile["daily_plays"] = {"date": _today_key(), "value": 0}
        await db.fps_game_profiles.update_one(
            {"user_id": user.user_id},
            {"$set": {"daily_plays": profile["daily_plays"], "updated_at": _iso_now()}},
        )
    return profile


def _quota_snapshot(plan: str, profile: dict[str, Any]) -> dict[str, Any]:
    cfg = PLAN_CONFIG.get(plan, PLAN_CONFIG["free"])
    played = int(profile.get("daily_plays", {}).get("value", 0))
    limit = int(cfg["daily_gameplay_limit"])
    return {
        "plan": plan,
        "scope_label": cfg["scope_label"],
        "daily_gameplay_limit": limit,
        "daily_plays_used": played,
        "daily_plays_remaining": -1 if limit < 0 else max(0, limit - played),
        "max_rooms_created_daily": cfg["max_rooms_created_daily"],
        "leaderboard_visibility": cfg["leaderboard_visibility"],
    }


def _effective_quota_plan(user: User, plan: str) -> str:
    if bool(user.is_admin) or bool(getattr(user, "full_access", False)):
        return "premium"
    return plan


# ── In-memory room registry (Photon PUN2 replacement) ────────────────────────

class FpsRoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def public_rooms(self) -> list[dict[str, Any]]:
        now = _utc_now()
        out = []
        for room_id, room in list(self.rooms.items()):
            if not room["players"]:
                try:
                    created = datetime.fromisoformat(room["created_at"])
                    if (now - created) > timedelta(minutes=10):
                        self.rooms.pop(room_id, None)
                        continue
                except Exception:
                    pass
            out.append({
                "room_id": room["room_id"],
                "name": room["name"],
                "players": len(room["players"]),
                "max_players": MAX_PLAYERS_PER_ROOM,
                "created_at": room["created_at"],
            })
        return sorted(out, key=lambda r: r["created_at"])

    async def ensure_room(self, room_id: str, name: str) -> dict[str, Any]:
        async with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                room = {
                    "room_id": room_id,
                    "name": name or room_id,
                    "created_at": _iso_now(),
                    "players": {},
                }
                self.rooms[room_id] = room
            return room

    async def remove_player(self, room_id: str, user_id: str) -> None:
        async with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return
            room["players"].pop(user_id, None)
            if not room["players"]:
                self.rooms.pop(room_id, None)


fps_rooms = FpsRoomManager()


def _player_public(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": p["user_id"],
        "name": p["name"],
        "model": p["model"],
        "hp": p["hp"],
        "kills": p["kills"],
        "deaths": p["deaths"],
        "pos": p["pos"],
        "rot": p["rot"],
        "alive": p["alive"],
    }


async def _broadcast(room: dict[str, Any], payload: dict[str, Any], exclude: str | None = None) -> None:
    message = json.dumps(payload)
    stale: list[str] = []
    for uid, player in list(room["players"].items()):
        if exclude and uid == exclude:
            continue
        ws: WebSocket = player.get("ws")
        if not ws:
            continue
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(uid)
    for uid in stale:
        room["players"].pop(uid, None)


async def _record_match(room_id: str, player: dict[str, Any]) -> None:
    try:
        started = datetime.fromisoformat(player["joined_at"])
        duration_ms = int((_utc_now() - started).total_seconds() * 1000)
    except Exception:
        duration_ms = 0
    kills = int(player.get("kills", 0))
    deaths = int(player.get("deaths", 0))
    await db.fps_game_matches.insert_one({
        "match_id": f"fps_{uuid.uuid4().hex[:12]}",
        "room_id": room_id,
        "user_id": player["user_id"],
        "player_name": player["name"],
        "model": player["model"],
        "kills": kills,
        "deaths": deaths,
        "score": kills * 100,
        "won": kills > deaths,
        "best_streak": int(player.get("best_streak_session", 0)),
        "duration_ms": duration_ms,
        "status": "completed",
        "created_at": _iso_now(),
    })
    updates: dict[str, Any] = {
        "$inc": {"matches_played": 1, "xp": XP_PER_MATCH},
        "$set": {"updated_at": _iso_now()},
    }
    await db.fps_game_profiles.update_one({"user_id": player["user_id"]}, updates)
    streak = int(player.get("best_streak_session", 0))
    if streak > 0:
        await db.fps_game_profiles.update_one(
            {"user_id": player["user_id"], "best_kill_streak": {"$lt": streak}},
            {"$set": {"best_kill_streak": streak}},
        )
    try:
        updated = await db.fps_game_profiles.find_one(
            {"user_id": player["user_id"]}, {"_id": 0, "matches_played": 1},
        )
        if int((updated or {}).get("matches_played", 0)) >= 10:
            from routes.gamification import award_badge

            await award_badge(player["user_id"], "fps_veteran")
    except Exception:
        pass


async def _publish_kill_achievements(room: dict[str, Any], killer: dict[str, Any], milestone: str | None) -> None:
    """Fan out FPS results to the platform gamification feed + home activity pulse."""
    killer_id = killer["user_id"]
    try:
        from routes.gamification import award_badge

        await award_badge(killer_id, "fps_first_blood")
        if milestone:
            await award_badge(killer_id, f"fps_{milestone}")
    except Exception:
        pass
    if not milestone:
        return
    try:
        from routes.notification_engine import emit_notification

        streak = int(killer.get("streak", 0))
        await emit_notification(
            user_id=killer_id,
            notif_type="achievement",
            title="FPS Streak Milestone",
            body=f"\U0001F3C6 {killer['name']} hit a {streak}-kill streak in {room['name']}!",
            action_url="/features/fps-game",
            send_email_notification=False,
        )
    except Exception:
        pass


async def _handle_kill(room: dict[str, Any], killer_id: str, victim_id: str) -> None:
    killer = room["players"].get(killer_id)
    victim = room["players"].get(victim_id)
    if not killer or not victim:
        return
    killer["kills"] += 1
    killer["streak"] = int(killer.get("streak", 0)) + 1
    killer["best_streak_session"] = max(int(killer.get("best_streak_session", 0)), killer["streak"])
    victim["deaths"] += 1
    victim["streak"] = 0
    victim["alive"] = False
    milestone = STREAK_MILESTONES.get(int(killer["streak"]))
    xp_gain = XP_PER_KILL + (XP_MILESTONE_BONUS if milestone else 0)
    await db.fps_game_profiles.update_one({"user_id": killer_id}, {"$inc": {"kills": 1, "xp": xp_gain}})
    await db.fps_game_profiles.update_one({"user_id": victim_id}, {"$inc": {"deaths": 1}})
    await _broadcast(room, {
        "type": "kill",
        "killer_id": killer_id,
        "killer_name": killer["name"],
        "victim_id": victim_id,
        "victim_name": victim["name"],
        "killer_kills": killer["kills"],
        "victim_deaths": victim["deaths"],
        "streak": killer["streak"],
        "milestone": milestone,
        "xp_gain": xp_gain,
    })
    asyncio.create_task(_publish_kill_achievements(room, killer, milestone))

    async def _respawn_later() -> None:
        await asyncio.sleep(RESPAWN_SECONDS)
        current = room["players"].get(victim_id)
        if not current:
            return
        spawn = random.choice(SPAWN_POINTS)
        current["hp"] = MAX_HP
        current["alive"] = True
        current["pos"] = list(spawn)
        await _broadcast(room, {
            "type": "respawn",
            "user_id": victim_id,
            "pos": list(spawn),
            "hp": MAX_HP,
        })

    asyncio.create_task(_respawn_later())


async def handle_fps_ws(websocket: WebSocket, room_id: str, user: User) -> None:
    """Room gameplay socket. Ticket-authenticated in ws_endpoints before entry."""
    room_id = _slugify_room(room_id) or "arena"
    room = await fps_rooms.ensure_room(room_id, room_id)
    if len(room["players"]) >= MAX_PLAYERS_PER_ROOM and user.user_id not in room["players"]:
        await websocket.close(code=4009)
        return

    profile = await _get_or_create_profile(user)
    existing_player = room["players"].get(user.user_id)
    if existing_player is not None:
        # Reconnect within grace period — resume session state (kills/deaths/hp/pos).
        existing_player["ws"] = websocket
        player = existing_player
        resumed = True
    else:
        spawn = random.choice(SPAWN_POINTS)
        player = {
            "user_id": user.user_id,
            "name": profile.get("display_name") or user.name or "Player",
            "model": profile.get("preferred_model", "policeman"),
            "hp": MAX_HP,
            "kills": 0,
            "deaths": 0,
            "streak": 0,
            "best_streak_session": 0,
            "alive": True,
            "pos": list(spawn),
            "rot": [0.0, 0.0],
            "joined_at": _iso_now(),
            "ws": websocket,
        }
        room["players"][user.user_id] = player
        resumed = False

    await websocket.send_text(json.dumps({
        "type": "joined",
        "room_id": room_id,
        "room_name": room["name"],
        "resumed": resumed,
        "self": _player_public(player),
        "players": [_player_public(p) for uid, p in room["players"].items() if uid != user.user_id],
    }))
    if not resumed:
        await _broadcast(room, {"type": "player_joined", "player": _player_public(player)}, exclude=user.user_id)

    try:
        explicit_leave = False
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "leave":
                explicit_leave = True
                break
            if mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif mtype == "state":
                pos = msg.get("pos")
                rot = msg.get("rot")
                if isinstance(pos, list) and len(pos) == 3:
                    player["pos"] = [float(pos[0]), float(pos[1]), float(pos[2])]
                if isinstance(rot, list) and len(rot) == 2:
                    player["rot"] = [float(rot[0]), float(rot[1])]
                await _broadcast(room, {
                    "type": "state",
                    "user_id": user.user_id,
                    "pos": player["pos"],
                    "rot": player["rot"],
                    "anim": str(msg.get("anim") or "idle")[:16],
                }, exclude=user.user_id)
            elif mtype == "shoot":
                if player["alive"]:
                    await _broadcast(room, {
                        "type": "shoot",
                        "user_id": user.user_id,
                    }, exclude=user.user_id)
            elif mtype == "hit":
                target_id = str(msg.get("target_id") or "")
                target = room["players"].get(target_id)
                if not player["alive"] or not target or not target["alive"] or target_id == user.user_id:
                    continue
                target["hp"] = max(0, int(target["hp"]) - HIT_DAMAGE)
                await _broadcast(room, {
                    "type": "damage",
                    "target_id": target_id,
                    "hp": target["hp"],
                    "by": user.user_id,
                })
                if target["hp"] <= 0:
                    await _handle_kill(room, user.user_id, target_id)
            elif mtype == "chat":
                text = str(msg.get("text") or "").strip()[:200]
                if text:
                    await _broadcast(room, {
                        "type": "chat",
                        "user_id": user.user_id,
                        "name": player["name"],
                        "text": text,
                    })
    except Exception:
        pass
    finally:
        if player.get("ws") is websocket:
            player["ws"] = None

            async def _finalize() -> None:
                current_room = fps_rooms.rooms.get(room_id)
                current = current_room["players"].get(user.user_id) if current_room else None
                if current is not player or current.get("ws") is not None:
                    return  # reconnected (or already finalized)
                await _record_match(room_id, current)
                await fps_rooms.remove_player(room_id, user.user_id)
                remaining = fps_rooms.rooms.get(room_id)
                if remaining:
                    await _broadcast(remaining, {
                        "type": "player_left",
                        "user_id": user.user_id,
                        "name": player["name"],
                    })

            if explicit_leave:
                await _finalize()
            else:
                async def _finalize_after_grace() -> None:
                    await asyncio.sleep(RECONNECT_GRACE_SECONDS)
                    await _finalize()

                asyncio.create_task(_finalize_after_grace())


# ── REST API ──────────────────────────────────────────────────────────────────

class JoinRoomRequest(BaseModel):
    room_name: str = Field(min_length=1, max_length=48)
    player_name: str = Field(default="", max_length=32)
    model: str = Field(default="policeman")


async def _leaderboard(limit: int = 20) -> list[dict[str, Any]]:
    rows = await db.fps_game_profiles.find(
        {}, {"_id": 0, "user_id": 1, "display_name": 1, "kills": 1, "deaths": 1,
             "matches_played": 1, "best_kill_streak": 1, "preferred_model": 1, "xp": 1},
    ).sort("kills", -1).limit(limit).to_list(limit)
    for idx, row in enumerate(rows):
        row["rank"] = idx + 1
        deaths = max(1, int(row.get("deaths", 0)))
        row["kd_ratio"] = round(int(row.get("kills", 0)) / deaths, 2)
        row["xp"] = int(row.get("xp", 0))
        row["level"] = _level_for(row["xp"])
    return rows


@router.get("/bootstrap")
async def fps_bootstrap(request: Request):
    user = await require_auth(request)
    plan = _resolve_plan(user)
    quota_plan = _effective_quota_plan(user, plan)
    profile = await _get_or_create_profile(user)
    profile["xp"] = int(profile.get("xp", 0))
    profile["level"] = _level_for(profile["xp"])
    profile["xp_per_level"] = XP_PER_LEVEL
    return {
        "feature_id": "games-station",
        "title": "FPS Game",
        "plan": plan,
        "quota": _quota_snapshot(quota_plan, profile),
        "profile": {k: v for k, v in profile.items() if k != "ws"},
        "player_models": sorted(PLAYER_MODELS),
        "rooms": fps_rooms.public_rooms(),
        "leaderboard": await _leaderboard(10),
        "share_joins": await db.fps_share_joins.count_documents({"owner_user_id": user.user_id}),
        "max_players_per_room": MAX_PLAYERS_PER_ROOM,
        "hit_damage": HIT_DAMAGE,
        "max_hp": MAX_HP,
    }


@router.get("/rooms")
async def fps_rooms_list(request: Request):
    await require_auth(request)
    return {"rooms": fps_rooms.public_rooms(), "max_players_per_room": MAX_PLAYERS_PER_ROOM}


@router.get("/leaderboard")
async def fps_leaderboard(request: Request, limit: int = 20):
    await require_auth(request)
    return {"leaderboard": await _leaderboard(max(1, min(100, limit)))}


@router.get("/profile")
async def fps_profile(request: Request):
    user = await require_auth(request)
    profile = await _get_or_create_profile(user)
    return {"profile": profile}


@router.get("/match-history")
async def fps_match_history(request: Request, limit: int = 20):
    user = await require_auth(request)
    rows = await db.fps_game_matches.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(50, limit))).to_list(50)
    return {"matches": rows}


def _public_match_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Privacy-safe public match summary — no user_id / email exposure."""
    kills = int(row.get("kills", 0))
    deaths = int(row.get("deaths", 0))
    return {
        "match_id": row.get("match_id"),
        "player_name": str(row.get("player_name") or "Player")[:32],
        "model": row.get("model", "policeman"),
        "kills": kills,
        "deaths": deaths,
        "kd_ratio": round(kills / max(1, deaths), 2),
        "best_streak": int(row.get("best_streak", 0)),
        "won": bool(row.get("won", False)),
        "room_name": str(row.get("room_id") or "arena"),
        "duration_ms": int(row.get("duration_ms", 0)),
        "created_at": row.get("created_at", ""),
    }


@router.get("/match-card/{match_id}")
async def fps_public_match_card(match_id: str):
    """Public read-only match card (mirrors certificate-verifier trust pattern)."""
    row = await db.fps_game_matches.find_one({"match_id": str(match_id)[:32]}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    payload = _public_match_payload(row)
    payload["share_joins"] = await db.fps_share_joins.count_documents({"match_id": str(match_id)[:32]})
    return payload


@router.get("/match-card/{match_id}/social-preview.svg")
async def fps_match_card_social_preview(match_id: str):
    import html as _html

    row = await db.fps_game_matches.find_one({"match_id": str(match_id)[:32]}, {"_id": 0})
    if not row:
        svg = """
<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="FPS match card unavailable">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#0B1420"/><stop offset="100%" stop-color="#1E293B"/>
  </linearGradient></defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <text x="80" y="130" fill="#E2E8F0" font-size="34" font-family="Arial, sans-serif" font-weight="700">RealAICoach FPS Arena</text>
  <text x="80" y="220" fill="#FCA5A5" font-size="44" font-family="Arial, sans-serif" font-weight="800">MATCH NOT FOUND</text>
  <text x="80" y="560" fill="#94A3B8" font-size="22" font-family="Arial, sans-serif">Public match preview • privacy-safe</text>
</svg>
""".strip()
        return Response(content=svg, media_type="image/svg+xml")

    p = _public_match_payload(row)
    name = _html.escape(p["player_name"])
    room = _html.escape(p["room_name"][:32])
    outcome = "VICTORY" if p["won"] else "DEFEAT"
    outcome_color = "#22C55E" if p["won"] else "#F87171"
    svg = f"""
<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="FPS match result">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#0B1420"/><stop offset="100%" stop-color="#111827"/>
  </linearGradient></defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="70" y="70" rx="18" ry="18" width="1060" height="490" fill="#111827" stroke="#334155" stroke-width="2"/>
  <text x="110" y="140" fill="#E2E8F0" font-size="34" font-family="Arial, sans-serif" font-weight="700">RealAICoach FPS Arena — Match Card</text>
  <text x="110" y="215" fill="{outcome_color}" font-size="52" font-family="Arial, sans-serif" font-weight="800">{outcome}</text>
  <text x="110" y="280" fill="#CBD5E1" font-size="30" font-family="Arial, sans-serif">Player: {name}</text>
  <text x="110" y="335" fill="#94A3B8" font-size="26" font-family="Arial, sans-serif">Kills: {p["kills"]}   Deaths: {p["deaths"]}   K/D: {p["kd_ratio"]}</text>
  <text x="110" y="390" fill="#FBBF24" font-size="26" font-family="Arial, sans-serif">Best streak: {p["best_streak"]}</text>
  <text x="110" y="445" fill="#94A3B8" font-size="24" font-family="Arial, sans-serif">Room: {room}</text>
  <text x="110" y="535" fill="#64748B" font-size="20" font-family="Arial, sans-serif">Privacy-safe public preview • Sign in to play at RealAICoach</text>
</svg>
""".strip()
    return Response(content=svg, media_type="image/svg+xml")


_FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def _render_match_card_png(p: dict[str, Any] | None) -> bytes:
    """1200x630 PNG for social crawlers (og:image rejects SVG on most platforms)."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    def load_font(path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    img = Image.new("RGB", (1200, 630), (11, 20, 32))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([70, 70, 1130, 560], radius=18, fill=(17, 24, 39), outline=(51, 65, 85), width=2)
    d.text((110, 105), "RealAICoach FPS Arena — Match Card", font=load_font(_FONT_BOLD, 34), fill=(226, 232, 240))

    if not p:
        d.text((110, 190), "MATCH NOT FOUND", font=load_font(_FONT_BOLD, 52), fill=(252, 165, 165))
        d.text((110, 500), "Public match preview • privacy-safe", font=load_font(_FONT_REGULAR, 22), fill=(148, 163, 184))
    else:
        outcome = "VICTORY" if p["won"] else "DEFEAT"
        outcome_color = (34, 197, 94) if p["won"] else (248, 113, 113)
        d.text((110, 180), outcome, font=load_font(_FONT_BOLD, 56), fill=outcome_color)
        d.text((110, 265), f"Player: {p['player_name']}", font=load_font(_FONT_REGULAR, 32), fill=(203, 213, 225))
        d.text(
            (110, 325),
            f"Kills: {p['kills']}    Deaths: {p['deaths']}    K/D: {p['kd_ratio']}",
            font=load_font(_FONT_REGULAR, 28), fill=(148, 163, 184),
        )
        d.text((110, 380), f"Best streak: {p['best_streak']}", font=load_font(_FONT_BOLD, 28), fill=(251, 191, 36))
        d.text((110, 435), f"Room: {p['room_name'][:32]}", font=load_font(_FONT_REGULAR, 26), fill=(148, 163, 184))
        d.text(
            (110, 505),
            "Privacy-safe public preview • Sign in to play at RealAICoach",
            font=load_font(_FONT_REGULAR, 21), fill=(100, 116, 139),
        )

    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@router.get("/match-card/{match_id}/social-preview.png")
async def fps_match_card_social_png(match_id: str):
    row = await db.fps_game_matches.find_one({"match_id": str(match_id)[:32]}, {"_id": 0})
    payload = _public_match_payload(row) if row else None
    png = _render_match_card_png(payload)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.post("/rooms/join")
async def fps_join_room(request: Request, payload: JoinRoomRequest):
    """Join-or-create room (repo 'Join or Create Room' flow). Enforces daily quota."""
    user = await require_auth(request)
    plan = _resolve_plan(user)
    quota_plan = _effective_quota_plan(user, plan)
    profile = await _get_or_create_profile(user)
    quota = _quota_snapshot(quota_plan, profile)
    if quota["daily_gameplay_limit"] >= 0 and quota["daily_plays_remaining"] <= 0:
        raise HTTPException(status_code=429, detail="Daily gameplay limit reached for your plan")

    room_id = _slugify_room(payload.room_name)
    if not room_id:
        raise HTTPException(status_code=400, detail="Invalid room name")
    existing = fps_rooms.rooms.get(room_id)
    if existing and len(existing["players"]) >= MAX_PLAYERS_PER_ROOM:
        raise HTTPException(status_code=409, detail="Room is full")

    model = payload.model if payload.model in PLAYER_MODELS else "policeman"
    display_name = payload.player_name.strip() or profile.get("display_name") or "Player"
    await db.fps_game_profiles.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "display_name": display_name[:32],
            "preferred_model": model,
            "updated_at": _iso_now(),
        },
         "$inc": {"daily_plays.value": 1}},
    )
    await fps_rooms.ensure_room(room_id, payload.room_name.strip())
    return {
        "room_id": room_id,
        "room_name": payload.room_name.strip(),
        "ws_path": f"/api/ws/fps/{room_id}/{user.user_id}",
        "model": model,
        "player_name": display_name[:32],
        "max_players": MAX_PLAYERS_PER_ROOM,
    }



class ShareJoinRequest(BaseModel):
    match_id: str = Field(..., min_length=1, max_length=64)


@router.post("/share-join")
async def fps_record_share_join(request: Request, payload: ShareJoinRequest):
    """Attribute a player joining the FPS Game from a shared public match card."""
    user = await require_auth(request)
    match = await db.fps_game_matches.find_one(
        {"match_id": payload.match_id.strip()[:32]},
        {"_id": 0, "match_id": 1, "user_id": 1},
    )
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    owner_id = str(match.get("user_id") or "")
    if not owner_id or owner_id == user.user_id:
        return {"recorded": False, "reason": "own_match"}
    existing = await db.fps_share_joins.find_one(
        {"owner_user_id": owner_id, "joiner_user_id": user.user_id}, {"_id": 0},
    )
    if existing:
        return {"recorded": False, "reason": "already_recorded"}
    await db.fps_share_joins.insert_one({
        "share_join_id": f"fsj_{uuid.uuid4().hex[:12]}",
        "match_id": match["match_id"],
        "owner_user_id": owner_id,
        "joiner_user_id": user.user_id,
        "created_at": _iso_now(),
    })
    total = await db.fps_share_joins.count_documents({"owner_user_id": owner_id})
    try:
        from utils.notification_helper import create_notification
        await create_notification(
            owner_id,
            "New recruit from your share",
            f"A player just joined the FPS Arena from your shared match card — {total} player{'s have' if total != 1 else ' has'} joined from your shares so far.",
            notif_type="fps_share_join",
            data={"match_id": match["match_id"], "total_share_joins": total, "route": "/features/fps-game"},
        )
    except Exception:
        pass
    return {"recorded": True, "owner_share_joins": total}
