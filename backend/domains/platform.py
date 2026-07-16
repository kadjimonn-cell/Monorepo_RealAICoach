"""Platform Domain — Config, health, i18n, accessibility, infra, monitoring, cleanup."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import i18n
    from routes import geo_detection
    from routes import accessibility
    from routes import system_health
    from routes import system_metrics
    from routes import platform_monitor
    from routes import performance_reports
    from routes import user_analytics
    from routes import feature_access
    from routes import access_control
    from routes import photo_upload
    from routes import fraud_engine
    from routes import self_repair_engine
    from routes import infra_engine
    from routes import config
    from routes import smart_schedule_ai
    from routes import analytics
    from routes import integrations
    from routes import cleanup
    from routes import tools_misc
    from routes import digest
    from routes import drip_campaign
    from routes.otp_analytics_engine import router as otp_analytics_router
    from routes.resend_webhooks import router as resend_webhooks_router
    from routes.home_dashboard import router as home_dashboard_router
    from routes.feature_gallery import router as feature_gallery_router

    api_router.include_router(i18n.router, tags=["i18n"])
    api_router.include_router(geo_detection.router, tags=["Geo Detection"])
    api_router.include_router(accessibility.router, tags=["Accessibility"])
    api_router.include_router(system_health.router, tags=["System Health"])
    api_router.include_router(system_metrics.router, tags=["System Metrics"])
    api_router.include_router(platform_monitor.router, tags=["Platform Monitor"])
    api_router.include_router(performance_reports.router, tags=["Performance Reports"])
    api_router.include_router(user_analytics.router, tags=["User Analytics"])
    api_router.include_router(feature_access.router, tags=["Feature Access"])
    api_router.include_router(access_control.router, tags=["Access Control"])
    api_router.include_router(photo_upload.router, tags=["Photo Upload"])
    api_router.include_router(fraud_engine.router, tags=["Fraud Detection"])
    api_router.include_router(self_repair_engine.router, tags=["Self Repair"])
    api_router.include_router(infra_engine.router, tags=["Infrastructure"])
    api_router.include_router(smart_schedule_ai.router, tags=["Smart Schedule AI"])
    api_router.include_router(otp_analytics_router, tags=["OTP Analytics"])
    api_router.include_router(resend_webhooks_router, tags=["Resend Webhooks"])
    api_router.include_router(home_dashboard_router, tags=["Home Dashboard"])
    api_router.include_router(feature_gallery_router, tags=["Feature Gallery"])

    if app:
        app.include_router(config.router, prefix="/api", tags=["Safe Automation"])
        app.include_router(analytics.router, prefix="/api", tags=["Analytics"])
        app.include_router(integrations.router, prefix="/api", tags=["Integrations"])
        app.include_router(cleanup.router, prefix="/api", tags=["Cleanup"])
        app.include_router(tools_misc.router, prefix="/api", tags=["Tools & Misc"])
        app.include_router(digest.router, prefix="/api", tags=["Digest"])
        app.include_router(drip_campaign.router, prefix="/api", tags=["Onboarding Drip"])
