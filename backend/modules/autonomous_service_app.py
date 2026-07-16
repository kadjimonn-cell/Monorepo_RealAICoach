from fastapi import FastAPI

from routes.autonomous_engine import router as autonomous_engine_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RealAICoach Autonomous Engine Service",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": "autonomous_engine"}

    app.include_router(autonomous_engine_router, prefix="/api")
    return app


app = create_app()
