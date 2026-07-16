"""Social Domain — Notifications, gamification, team management, collaborative tools."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import notification_engine
    from routes import gamification
    from routes import games_station
    from routes import flappy_bird
    from routes import team_management
    from routes import team_analytics
    from routes import onboarding_analytics
    from routes import whiteboard
    from routes import collaborative_docs
    from routes import notifications

    api_router.include_router(notification_engine.router, tags=["Notification Engine"])
    api_router.include_router(gamification.router, tags=["Gamification"])
    api_router.include_router(games_station.router, tags=["FPS Game"])
    api_router.include_router(flappy_bird.router, tags=["Flappy Bird Game"])
    api_router.include_router(team_management.router, tags=["Team Management"])
    api_router.include_router(team_analytics.router, tags=["Team Analytics"])
    api_router.include_router(team_analytics.webhook_event_router, tags=["Webhook Events"])
    api_router.include_router(onboarding_analytics.router, tags=["Onboarding Analytics"])
    api_router.include_router(whiteboard.router, tags=["Collaborative Whiteboard"])
    api_router.include_router(collaborative_docs.router, tags=["Collaborative Documents"])

    if app:
        app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
