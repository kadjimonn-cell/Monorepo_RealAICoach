# ruff: noqa
"""Google Play Console API Service — Real integration using service account auth."""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_service_cache = {"svc": None}


def _get_service():
    """Build or return cached androidpublisher v3 service."""
    if _service_cache["svc"]:
        return _service_cache["svc"]

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_path = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")
    if not sa_path:
        raise ValueError("Missing GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")

    credentials = service_account.Credentials.from_service_account_file(
        sa_path,
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )
    svc = build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)
    _service_cache["svc"] = svc
    return svc


async def get_connection_status() -> dict:
    """Test the Google Play Developer API connection."""
    try:
        _get_service()
        return {
            "connected": True,
            "service_account": os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "").split("/")[-1],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def list_reviews(package_name: str, max_results: int = 20) -> dict:
    """Fetch reviews for an app."""
    try:
        svc = _get_service()
        result = svc.reviews().list(
            packageName=package_name, maxResults=max_results
        ).execute()
        reviews = []
        for r in result.get("reviews", []):
            user_comment = {}
            dev_comment = {}
            for c in r.get("comments", []):
                if "userComment" in c:
                    uc = c["userComment"]
                    user_comment = {
                        "text": uc.get("text", ""),
                        "star_rating": uc.get("starRating", 0),
                        "device": uc.get("device", ""),
                        "android_version": uc.get("androidOsVersion", ""),
                        "app_version": uc.get("appVersionName", ""),
                        "timestamp": uc.get("lastModified", {}).get("seconds"),
                    }
                if "developerComment" in c:
                    dc = c["developerComment"]
                    dev_comment = {
                        "text": dc.get("text", ""),
                        "timestamp": dc.get("lastModified", {}).get("seconds"),
                    }
            reviews.append({
                "review_id": r.get("reviewId"),
                "author": r.get("authorName", "Anonymous"),
                "user_comment": user_comment,
                "developer_comment": dev_comment,
            })
        return {"status": "ok", "reviews": reviews, "count": len(reviews), "token": result.get("tokenPagination")}
    except Exception as e:
        logger.error(f"Google Play list_reviews failed: {e}")
        return {"status": "error", "detail": str(e), "reviews": []}


async def reply_to_review(package_name: str, review_id: str, reply_text: str) -> dict:
    """Reply to a user review."""
    try:
        svc = _get_service()
        result = svc.reviews().reply(
            packageName=package_name,
            reviewId=review_id,
            body={"replyText": reply_text},
        ).execute()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Google Play reply_to_review failed: {e}")
        return {"status": "error", "detail": str(e)}


async def get_app_details(package_name: str) -> dict:
    """Get app details via the API."""
    try:
        svc = _get_service()
        # Use edits API to get app details
        edit = svc.edits().insert(packageName=package_name, body={}).execute()
        edit_id = edit["id"]

        details = svc.edits().details().get(
            packageName=package_name, editId=edit_id
        ).execute()

        listings = svc.edits().listings().list(
            packageName=package_name, editId=edit_id
        ).execute()

        # Clean up the edit
        svc.edits().delete(packageName=package_name, editId=edit_id).execute()

        listing_data = []
        for l in listings.get("listings", []):
            listing_data.append({
                "language": l.get("language"),
                "title": l.get("title"),
                "short_description": l.get("shortDescription", "")[:100],
                "full_description": l.get("fullDescription", "")[:200] + "...",
            })

        return {
            "status": "ok",
            "package_name": package_name,
            "contact_email": details.get("contactEmail"),
            "contact_phone": details.get("contactPhone"),
            "contact_website": details.get("contactWebsite"),
            "default_language": details.get("defaultLanguage"),
            "listings": listing_data,
        }
    except Exception as e:
        logger.error(f"Google Play get_app_details failed: {e}")
        return {"status": "error", "package_name": package_name, "detail": str(e)}
