from fastapi import FastAPI

from routes.analytics import router as analytics_router
from routes.platform_analytics import router as platform_analytics_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RealAICoach Analytics Service",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": "analytics"}

    app.include_router(analytics_router, prefix="/api")
    app.include_router(platform_analytics_router, prefix="/api")
    return app


app = create_app()
