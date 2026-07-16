"""Content Domain — Library, streaming, media, creator analytics, sharing."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import content
    from routes import creator_analytics
    from routes import share
    from routes import home_personalized
    from routes import content_studio

    api_router.include_router(creator_analytics.router, tags=["Creator Analytics"])
    api_router.include_router(content_studio.router, tags=["Content Studio"])

    if app:
        app.include_router(content.router, prefix="/api", tags=["Content Automation"])
        app.include_router(share.router, prefix="/api", tags=["Share Links"])
        app.include_router(home_personalized.router, prefix="/api", tags=["Home Personalized"])
