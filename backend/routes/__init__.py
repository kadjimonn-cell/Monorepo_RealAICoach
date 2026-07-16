"""
Backend Router Architecture
===========================
This module provides a clean router-based architecture for the RealAICoach backend.
The monolithic server.py is being incrementally refactored into separate route modules.

Usage in server.py:
    from routes import auth_router, ai_router, tools_router, security_router
    app.include_router(auth_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    ...
"""
