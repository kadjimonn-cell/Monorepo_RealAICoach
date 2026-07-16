"""Workspace routes: live data context + saved workspace items."""

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import uuid
import hashlib
import re
import httpx
from bson import ObjectId

from .db import db, logger, require_auth

router = APIRouter()

DEFAULT_PACK_VERSION = "1.1"
SUPPORTED_PACK_VERSIONS = {"1.0", "1.1"}


class WorkspaceContextRequest(BaseModel):
    feature_key: str
    request: str = ""
    location: Optional[str] = None


class WorkspaceItemCreate(BaseModel):
    feature_key: str
    feature_name: str
    app_name: str
    module: str
    request: str
    output: str
    tags: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    data_context: Optional[str] = None


class WorkspaceFavoriteCreate(BaseModel):
    feature_key: str
    template_id: str
    title: str
    objective: str
    constraints: str
    module: str
    tags: List[str] = Field(default_factory=list)


class TemplatePackItem(BaseModel):
    title: str
    objective: str
    module: str
    constraints: Optional[str] = ""
    tags: List[str] = Field(default_factory=list)
    template_id: Optional[str] = None


class TemplatePack(BaseModel):
    version: str = DEFAULT_PACK_VERSION
    feature_key: Optional[str] = None
    pack_id: Optional[str] = None
    templates: List[TemplatePackItem]


def build_cache_key(feature: str, request: str, location: Optional[str]) -> str:
    raw = f"{feature}:{location or ''}:{request}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


async def fetch_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def get_cached(key: str, ttl_seconds: int = 600) -> Optional[Dict[str, Any]]:
    doc = await db.workspace_cache.find_one({"key": key}, {"_id": 0})
    if not doc:
        return None
    created_at = doc.get("created_at")
    if not created_at:
        return None
    created_dt = datetime.fromisoformat(created_at)
    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - created_dt).total_seconds() > ttl_seconds:
        return None
    return doc.get("data")


async def set_cache(key: str, data: Dict[str, Any]) -> None:
    payload = {
        "key": key,
        "data": data,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.workspace_cache.update_one({"key": key}, {"$set": payload}, upsert=True)


def extract_location(request: str) -> Optional[str]:
    match = re.search(r"\b(?:in|for)\s+([A-Za-z\s]{3,40})", request)
    if match:
        return match.group(1).strip()
    return None


async def get_weather_context(location: str) -> Optional[str]:
    geo = await fetch_json("https://geocoding-api.open-meteo.com/v1/search", params={"name": location, "count": 1})
    if not geo.get("results"):
        return None
    result = geo["results"][0]
    lat = result.get("latitude")
    lon = result.get("longitude")
    if lat is None or lon is None:
        return None
    weather = await fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,wind_speed_10m,weathercode",
            "timezone": "auto",
        },
    )
    current = weather.get("current", {})
    temp = current.get("temperature_2m")
    wind = current.get("wind_speed_10m")
    return f"Weather in {result.get('name')}: {temp}°C, wind {wind} km/h."


@router.post("/workspace/context")
async def workspace_context(payload: WorkspaceContextRequest):
    feature = payload.feature_key
    location = (payload.location or "").strip()
    if not location:
        location = extract_location(payload.request) or ""

    cache_key = build_cache_key(feature, payload.request, location)
    cached = await get_cached(cache_key)
    if cached:
        return cached

    sources: List[str] = []
    data_context = ""

    try:
        if feature == "medimate":
            country = location or "United States"
            try:
                stats = await fetch_json(f"https://disease.sh/v3/covid-19/countries/{country}")
                sources.append("Disease.sh")
                data_context = (
                    f"Health stats for {country}: cases {stats.get('cases')}, "
                    f"today {stats.get('todayCases')}, deaths {stats.get('deaths')}, "
                    f"recovered {stats.get('recovered')}."
                )
            except Exception:
                stats = await fetch_json("https://disease.sh/v3/covid-19/all")
                sources.append("Disease.sh")
                data_context = (
                    f"Global health stats: cases {stats.get('cases')}, today {stats.get('todayCases')}, "
                    f"deaths {stats.get('deaths')}, recovered {stats.get('recovered')}."
                )

        elif feature == "pennypilot":
            rates = await fetch_json("https://open.er-api.com/v6/latest/USD")
            sources.append("ER API")
            rate_data = rates.get("rates", {})
            fx = {"EUR": rate_data.get("EUR"), "GBP": rate_data.get("GBP"), "JPY": rate_data.get("JPY")}
            crypto = await fetch_json(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,solana",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
            )
            sources.append("CoinGecko")

            def fmt(value: Optional[float]) -> str:
                return f"{value:.2f}" if isinstance(value, (int, float)) else "N/A"

            data_context = (
                f"FX rates (USD base): EUR {fx.get('EUR')}, GBP {fx.get('GBP')}, JPY {fx.get('JPY')}. "
                f"Crypto: BTC ${crypto.get('bitcoin', {}).get('usd')} (24h {fmt(crypto.get('bitcoin', {}).get('usd_24h_change'))}%), "
                f"ETH ${crypto.get('ethereum', {}).get('usd')} (24h {fmt(crypto.get('ethereum', {}).get('usd_24h_change'))}%), "
                f"SOL ${crypto.get('solana', {}).get('usd')} (24h {fmt(crypto.get('solana', {}).get('usd_24h_change'))}%)."
            )

        elif feature == "smartbuy":
            query = payload.request.strip()
            if len(query) >= 3:
                products = await fetch_json("https://dummyjson.com/products/search", params={"q": query})
            else:
                products = await fetch_json("https://dummyjson.com/products", params={"limit": 5})
            sources.append("DummyJSON")
            items = products.get("products", [])[:5]
            summary = "; ".join([f"{p.get('title')} ${p.get('price')} ({p.get('rating')}/5)" for p in items])
            data_context = f"Sample product deals: {summary}."

        elif feature == "travelpal":
            country = location or "United States"
            try:
                country_data = await fetch_json(
                    f"https://restcountries.com/v3.1/name/{country}", params={"fullText": "true"}
                )
            except Exception:
                country_data = await fetch_json(f"https://restcountries.com/v3.1/name/{country}")
            sources.append("RestCountries")
            entry = country_data[0] if isinstance(country_data, list) and country_data else {}
            capital = (entry.get("capital") or ["Capital"])[0]
            region = entry.get("region")
            currencies = entry.get("currencies", {})
            currency_code = list(currencies.keys())[0] if currencies else ""
            weather_context = await get_weather_context(capital) if capital else None
            if weather_context:
                sources.append("Open-Meteo")
            data_context = (
                f"Destination info: {entry.get('name', {}).get('common', country)} in {region}. "
                f"Capital {capital}. Currency {currency_code}. "
                f"{weather_context or ''}"
            )

        elif feature == "fitness":
            city = location or "San Francisco"
            weather_context = await get_weather_context(city)
            if weather_context:
                sources.append("Open-Meteo")
                data_context = f"Outdoor workout conditions: {weather_context}"
            else:
                data_context = "No weather data available for workout planning."

        else:
            data_context = "No external live data required for this workflow."

    except Exception as exc:
        logger.error(f"Workspace context error ({feature}): {exc}")
        data_context = "Live data unavailable (free API limit or network error)."

    response = {"data_context": data_context, "sources": sources}
    await set_cache(cache_key, response)
    return response


def _serialize(doc: dict) -> dict:
    doc = {**doc}
    doc["workspace_id"] = str(doc.get("_id"))
    doc.pop("_id", None)
    return doc


def _serialize_favorite(doc: dict) -> dict:
    doc = {**doc}
    doc["favorite_id"] = str(doc.get("_id"))
    doc.pop("_id", None)
    return doc


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _normalize_pack(payload: TemplatePack, feature_key: str) -> List[dict]:
    if payload.version not in SUPPORTED_PACK_VERSIONS:
        raise HTTPException(status_code=400, detail="Unsupported template pack version")
    if len(payload.templates) > 200:
        raise HTTPException(status_code=400, detail="Template packs cannot exceed 200 items")
    if not payload.templates:
        raise HTTPException(status_code=400, detail="Template pack is empty")
    normalized = []
    for item in payload.templates:
        title = item.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Template title required")
        module = item.module.strip()
        if not module:
            raise HTTPException(status_code=400, detail="Template module required")
        template_id = item.template_id or f"{feature_key}-{_slugify(title)}-{uuid4().hex[:6]}"
        normalized.append(
            {
                "template_id": template_id,
                "title": title,
                "objective": item.objective.strip(),
                "constraints": (item.constraints or "").strip(),
                "module": module,
                "tags": item.tags or [],
            }
        )
    return normalized


def _parse_object_id(item_id: str) -> ObjectId:
    try:
        return ObjectId(item_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace id") from exc


@router.post("/workspace/items")
async def save_workspace_item(payload: WorkspaceItemCreate, req: Request):
    user = await require_auth(req)
    tags = sorted({tag.strip() for tag in payload.tags if tag.strip()})
    now = datetime.now(timezone.utc).isoformat()
    data = payload.dict()
    data.update(
        {
            "user_id": user.user_id,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
        }
    )
    result = await db.workspace_items.insert_one(data)
    data["_id"] = result.inserted_id
    return {"success": True, "item": _serialize(data)}


@router.get("/workspace/items")
async def list_workspace_items(
    req: Request,
    feature_key: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
):
    user = await require_auth(req)
    query: Dict[str, Any] = {"user_id": user.user_id}
    if feature_key:
        query["feature_key"] = feature_key
    if search:
        query["$or"] = [
            {"app_name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"module": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"request": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]
    if tag:
        query["tags"] = tag

    cursor = db.workspace_items.find(query).sort("created_at", -1)
    items = [_serialize(doc) async for doc in cursor]
    return {"items": items}


@router.delete("/workspace/items/{item_id}")
async def delete_workspace_item(item_id: str, req: Request):
    user = await require_auth(req)
    object_id = _parse_object_id(item_id)
    result = await db.workspace_items.delete_one({"_id": object_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workspace item not found")
    return {"success": True}


@router.get("/workspace/analytics")
async def workspace_analytics(req: Request, feature_key: Optional[str] = Query(default=None)):
    user = await require_auth(req)
    query: Dict[str, Any] = {"user_id": user.user_id}
    if feature_key:
        query["feature_key"] = feature_key

    total = await db.workspace_items.count_documents(query)

    top_apps: List[Dict[str, Any]] = []
    pipeline_apps = [
        {"$match": query},
        {"$group": {"_id": "$app_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    async for doc in db.workspace_items.aggregate(pipeline_apps):
        top_apps.append({"name": doc.get("_id"), "count": doc.get("count", 0)})

    top_tags: List[Dict[str, Any]] = []
    pipeline_tags = [
        {"$match": query},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6},
    ]
    async for doc in db.workspace_items.aggregate(pipeline_tags):
        top_tags.append({"tag": doc.get("_id"), "count": doc.get("count", 0)})

    return {
        "total": total,
        "top_apps": top_apps,
        "top_tags": top_tags,
    }


@router.post("/workspace/favorites")
async def save_workspace_favorite(payload: WorkspaceFavoriteCreate, req: Request):
    user = await require_auth(req)
    now = datetime.now(timezone.utc).isoformat()
    record = payload.dict()
    record.update(
        {
            "user_id": user.user_id,
            "created_at": now,
        }
    )
    existing = await db.workspace_favorites.find_one(
        {
            "user_id": user.user_id,
            "feature_key": payload.feature_key,
            "template_id": payload.template_id,
        }
    )
    if existing:
        return {"success": True, "favorite": _serialize_favorite(existing)}
    result = await db.workspace_favorites.insert_one(record)
    record["_id"] = result.inserted_id
    return {"success": True, "favorite": _serialize_favorite(record)}


@router.get("/workspace/favorites")
async def list_workspace_favorites(req: Request, feature_key: Optional[str] = Query(default=None)):
    user = await require_auth(req)
    query: Dict[str, Any] = {"user_id": user.user_id}
    if feature_key:
        query["feature_key"] = feature_key
    cursor = db.workspace_favorites.find(query).sort("created_at", -1)
    favorites = [_serialize_favorite(doc) async for doc in cursor]
    return {"favorites": favorites}


@router.delete("/workspace/favorites/{favorite_id}")
async def delete_workspace_favorite(favorite_id: str, req: Request):
    user = await require_auth(req)
    object_id = _parse_object_id(favorite_id)
    result = await db.workspace_favorites.delete_one({"_id": object_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"success": True}


@router.post("/workspace/template-packs/validate")
async def validate_template_pack(payload: TemplatePack):
    feature_key = payload.feature_key or "workspace"
    pack_id = payload.pack_id or str(uuid.uuid4())
    normalized = _normalize_pack(payload, feature_key)
    return {
        "valid": True,
        "version": payload.version,
        "pack_id": pack_id,
        "feature_key": feature_key,
        "templates": normalized,
    }


@router.post("/workspace/template-packs/import")
async def import_template_pack(payload: TemplatePack, req: Request):
    user = await require_auth(req)
    feature_key = payload.feature_key
    if not feature_key:
        raise HTTPException(status_code=400, detail="feature_key is required")
    pack_id = payload.pack_id or str(uuid.uuid4())
    normalized = _normalize_pack(payload, feature_key)
    now = datetime.now(timezone.utc).isoformat()
    pack_record = {
        "user_id": user.user_id,
        "feature_key": feature_key,
        "version": payload.version,
        "pack_id": pack_id,
        "templates": normalized,
        "created_at": now,
    }
    result = await db.workspace_template_packs.insert_one(pack_record)
    favorites = []
    for template in normalized:
        existing = await db.workspace_favorites.find_one(
            {
                "user_id": user.user_id,
                "feature_key": feature_key,
                "template_id": template["template_id"],
            }
        )
        if existing:
            favorites.append(_serialize_favorite(existing))
            continue
        record = {
            **template,
            "user_id": user.user_id,
            "feature_key": feature_key,
            "created_at": now,
        }
        insert_result = await db.workspace_favorites.insert_one(record)
        record["_id"] = insert_result.inserted_id
        favorites.append(_serialize_favorite(record))
    return {
        "success": True,
        "record_id": str(result.inserted_id),
        "pack_id": pack_id,
        "version": payload.version,
        "favorites": favorites,
        "templates": normalized,
    }
