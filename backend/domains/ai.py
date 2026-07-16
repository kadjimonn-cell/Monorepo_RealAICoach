"""AI Domain — All AI copilots, analytics, alerting, and model management."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import ai_lifecoach
    from routes import ai_document_analyzer
    from routes import ai_goals
    from routes import ai_daily_briefing
    from routes import ai_user_insights
    from routes import ai_auto_support
    from routes import ai_problem_solver
    from routes import ai_coaching_team
    from routes import ai_learning_hub
    from routes import ai_learning
    from routes import ai_engine
    from routes import ai_services
    from routes import ai_model_management
    from routes import ai_feature_analytics
    from routes import ai_usage_analytics
    from routes import llm_billing
    from routes import ai_alerting
    from routes import auto_scaling
    from routes import global_ai_marketplace
    from routes import mock_interview
    from routes import phone_call
    from routes import agent_framework
    from routes import agent_framework_ops

    api_router.include_router(ai_lifecoach.router, tags=["AI Life Coach"])
    api_router.include_router(ai_document_analyzer.router, tags=["AI Document Analyzer"])
    api_router.include_router(ai_goals.router, tags=["AI Goal Tracker"])
    api_router.include_router(ai_daily_briefing.router, tags=["AI Daily Briefing"])
    api_router.include_router(ai_user_insights.router, tags=["AI User Insights"])
    api_router.include_router(ai_auto_support.router, tags=["AI Auto Support"])
    api_router.include_router(ai_problem_solver.router, tags=["AI Problem Solver (Retired)"])
    api_router.include_router(ai_problem_solver.compat_router, tags=["AI Problem Solver Compatibility (Retired)"])
    api_router.include_router(ai_coaching_team.router, tags=["AI Coaching Team"])
    api_router.include_router(ai_learning_hub.router, tags=["AI Learning Hub"])
    api_router.include_router(ai_learning.router, tags=["Self-Learning AI"])
    api_router.include_router(ai_engine.router, tags=["AI Engine"])
    api_router.include_router(ai_model_management.router, tags=["AI Model Management"])
    api_router.include_router(ai_feature_analytics.router, tags=["AI Feature Analytics"])
    api_router.include_router(ai_usage_analytics.router, tags=["AI Usage Analytics"])
    api_router.include_router(llm_billing.router, tags=["LLM Billing"])
    api_router.include_router(ai_alerting.router, tags=["AI Alerting"])
    api_router.include_router(auto_scaling.router, tags=["Auto-Scaling"])
    api_router.include_router(global_ai_marketplace.router, tags=["Global AI Marketplace"])
    api_router.include_router(mock_interview.router, tags=["Mock Interview"])
    api_router.include_router(agent_framework.router, tags=["AI Agent Framework"])
    api_router.include_router(agent_framework_ops.router, tags=["AI Operating Layer v2"])

    if app:
        app.include_router(ai_services.router, prefix="/api", tags=["AI Services"])
        app.include_router(phone_call.router, prefix="/api", tags=["AI Phone Call"])
