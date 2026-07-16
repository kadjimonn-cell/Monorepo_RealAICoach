"""Admin Domain — Console, management, analytics, webhooks, A/B testing, safe backend."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import admin_console
    from routes import admin_safe_backend
    from routes import admin_general_analytics
    from routes import admin_management
    from routes import admin_payment_analytics
    from routes import advanced_admin
    from routes import executive_dashboard
    from routes import webhook_replay
    from routes import email_tab
    from routes import revenue_analytics
    from routes import whitelabel
    from routes import email_notifications
    from routes import admin_sessions
    from routes import admin_subscription_analytics
    from routes import admin_session_cleanup
    from routes import admin_session_alerts
    from routes import admin_auto_response
    from routes import admin_ip_blocklist
    from routes import siem_logging
    from routes import uba_analytics
    from routes import session_replay
    from routes import security_recommendations
    from routes import dashboard_layout

    api_router.include_router(admin_payment_analytics.router, tags=["Admin Payment Analytics"])
    api_router.include_router(siem_logging.router, tags=["SIEM Logging"])
    api_router.include_router(uba_analytics.router, tags=["UBA Analytics"])
    api_router.include_router(session_replay.router, tags=["Session Replay"])
    api_router.include_router(security_recommendations.router, tags=["Security Recommendations"])
    api_router.include_router(dashboard_layout.router, tags=["Dashboard Layout"])
    api_router.include_router(executive_dashboard.router, tags=["Executive Dashboard"])
    api_router.include_router(advanced_admin.access_matrix_router, tags=["Access Matrix"])
    api_router.include_router(advanced_admin.ab_testing_router, tags=["A/B Testing"])
    api_router.include_router(advanced_admin.enhanced_analytics_router, tags=["Enhanced Analytics"])
    api_router.include_router(advanced_admin.sse_router, tags=["Webhook SSE"])
    api_router.include_router(webhook_replay.router, tags=["Webhook Replay"])
    api_router.include_router(email_tab.router, tags=["Admin Email"])
    api_router.include_router(revenue_analytics.router, tags=["Revenue Analytics"])
    api_router.include_router(whitelabel.router, tags=["White Label"])
    api_router.include_router(admin_sessions.router, tags=["Admin Sessions"])
    api_router.include_router(admin_subscription_analytics.router, tags=["Subscription Analytics"])
    api_router.include_router(admin_session_cleanup.router, tags=["Session Cleanup"])
    api_router.include_router(admin_session_alerts.router, tags=["Session Alerts"])
    api_router.include_router(admin_auto_response.router, tags=["Auto-Response"])
    api_router.include_router(admin_ip_blocklist.router, tags=["IP Blocklist"])

    if app:
        app.include_router(admin_console.router, prefix="/api", tags=["Admin Console"])
        app.include_router(admin_safe_backend.router, prefix="/api", tags=["Safe Backend"])
        app.include_router(admin_general_analytics.router, prefix="/api", tags=["General Analytics"])
        app.include_router(admin_management.router, prefix="/api", tags=["Admin Management"])
        app.include_router(email_notifications.router, prefix="/api", tags=["Email Notifications"])
