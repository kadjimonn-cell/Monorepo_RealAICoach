from fastapi import FastAPI

from routes.email_notifications import router as email_notifications_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RealAICoach Communications Service",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": "communications"}

    app.include_router(email_notifications_router, prefix="/api")
    return app


app = create_app()
