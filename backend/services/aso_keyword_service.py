"""Real ASO Keyword Ranking Service — Fetches actual search rankings from App Store & Google Play.

Uses:
- iTunes Search API (free, no auth) for App Store rankings
- google-play-scraper for Google Play rankings
"""

import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Configure your app identifiers here
OUR_APP_BUNDLE_ID = "app.realaicoach.ios"
OUR_APP_PACKAGE = "app.realaicoach.android"
OUR_APP_NAME = "RealAICoach"

# Known competitors to track
COMPETITORS = [
    {"name": "BetterUp", "apple_bundle": "com.betterup.connect", "google_package": "com.betterup.connect"},
    {"name": "CoachHub", "apple_bundle": "com.coachhub.app", "google_package": "com.coachhub.app"},
    {"name": "Torch", "apple_bundle": "com.torch.app", "google_package": "com.torch.app"},
]


async def search_apple_store(keyword: str, country: str = "us", limit: int = 200) -> list:
    """Search the App Store via iTunes Search API. Returns ranked results."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://itunes.apple.com/search", params={
                "term": keyword,
                "entity": "software",
                "limit": limit,
                "country": country,
            })
            if resp.status_code != 200:
                logger.warning(f"iTunes Search API returned {resp.status_code}")
                return []
            data = resp.json()
            results = []
            for i, app in enumerate(data.get("results", [])):
                results.append({
                    "rank": i + 1,
                    "name": app.get("trackName", ""),
                    "bundle_id": app.get("bundleId", ""),
                    "developer": app.get("sellerName", ""),
                    "rating": round(app.get("averageUserRating", 0), 1),
                    "rating_count": app.get("userRatingCount", 0),
                    "icon_url": app.get("artworkUrl60", ""),
                    "price": app.get("price", 0),
                    "genre": app.get("primaryGenreName", ""),
                })
            return results
    except Exception as e:
        logger.error(f"Apple Store search failed for '{keyword}': {e}")
        return []


def search_google_play(keyword: str, country: str = "us", limit: int = 50) -> list:
    """Search Google Play Store. Returns ranked results."""
    try:
        from google_play_scraper import search
        raw_results = search(keyword, lang="en", country=country, n_hits=min(limit, 50))
        results = []
        for i, app in enumerate(raw_results):
            results.append({
                "rank": i + 1,
                "name": app.get("title", ""),
                "package": app.get("appId", ""),
                "developer": app.get("developer", ""),
                "rating": round(app.get("score", 0) or 0, 1),
                "rating_count": app.get("ratings", 0),
                "icon_url": app.get("icon", ""),
                "price": app.get("price", "Free"),
                "installs": app.get("installs", ""),
            })
        return results
    except Exception as e:
        logger.error(f"Google Play search failed for '{keyword}': {e}")
        return []


def _find_app_rank(results: list, identifiers: list, name_hint: str = "") -> Optional[int]:
    """Find our app's rank in search results by bundle_id/package or name match."""
    for r in results:
        app_id = r.get("bundle_id", "") or r.get("package", "")
        app_name = r.get("name", "").lower()
        for ident in identifiers:
            if ident and ident.lower() in app_id.lower():
                return r["rank"]
        if name_hint and name_hint.lower() in app_name:
            return r["rank"]
    return None


def _find_competitor_ranks(apple_results: list, google_results: list) -> list:
    """Find competitor rankings in search results."""
    comp_data = []
    for comp in COMPETITORS:
        apple_rank = _find_app_rank(apple_results, [comp["apple_bundle"]], comp["name"])
        google_rank = _find_app_rank(google_results, [comp["google_package"]], comp["name"])
        comp_data.append({
            "name": comp["name"],
            "apple_rank": apple_rank or 0,
            "google_rank": google_rank or 0,
        })
    return comp_data


def _estimate_difficulty(apple_results: list, google_results: list) -> int:
    """Estimate keyword difficulty based on competition quality."""
    if not apple_results and not google_results:
        return 0
    total_ratings = 0
    high_rated = 0
    sample = (apple_results[:10] if apple_results else []) + (google_results[:10] if google_results else [])
    for app in sample:
        rc = app.get("rating_count", 0) or 0
        total_ratings += rc
        if (app.get("rating", 0) or 0) >= 4.5:
            high_rated += 1
    avg_ratings = total_ratings / max(len(sample), 1)
    difficulty = min(99, int(
        (high_rated / max(len(sample), 1)) * 40 +
        min(avg_ratings / 10000, 1) * 40 +
        min(len(apple_results), 50) / 50 * 20
    ))
    return max(5, difficulty)


def _estimate_volume(apple_count: int, google_count: int) -> str:
    """Estimate search volume based on result count."""
    total = apple_count + google_count
    if total >= 300:
        return "high"
    elif total >= 100:
        return "medium"
    return "low"


async def get_real_keyword_data(keyword: str) -> dict:
    """Get real keyword ranking data from both stores."""
    import asyncio

    # Search Apple Store (async)
    apple_results = await search_apple_store(keyword)

    # Search Google Play (sync, run in executor)
    loop = asyncio.get_event_loop()
    google_results = await loop.run_in_executor(None, search_google_play, keyword)

    # Find our app's rank
    our_apple_rank = _find_app_rank(
        apple_results,
        [OUR_APP_BUNDLE_ID],
        OUR_APP_NAME
    )
    our_google_rank = _find_app_rank(
        google_results,
        [OUR_APP_PACKAGE],
        OUR_APP_NAME
    )

    # Get competitor data
    competitors = _find_competitor_ranks(apple_results, google_results)

    # Estimate difficulty and volume
    difficulty = _estimate_difficulty(apple_results, google_results)
    volume = _estimate_volume(len(apple_results), len(google_results))

    # Top results for context
    apple_top5 = apple_results[:5] if apple_results else []
    google_top5 = google_results[:5] if google_results else []

    return {
        "apple": {
            "rank": our_apple_rank or 0,
            "total_results": len(apple_results),
            "difficulty": difficulty,
            "search_volume": volume,
            "top_results": apple_top5,
        },
        "google": {
            "rank": our_google_rank or 0,
            "total_results": len(google_results),
            "difficulty": difficulty,
            "search_volume": volume,
            "top_results": google_top5,
        },
        "competitors": competitors,
        "data_source": "live",
    }
