"""Auth Domain — Authentication, security, ID checker, sessions."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import auth
    from routes import auth_compliance
    from routes import id_verification
    from routes import coaching
    from routes import advanced_coaching
    from routes import mfa

    api_router.include_router(id_verification.router, prefix="/id-checker", tags=["ID Checker"])
    # Backward-compatible alias to avoid breaking old clients during migration
    api_router.include_router(id_verification.router, prefix="/id-verification", tags=["ID Checker (Legacy Alias)"])
    api_router.include_router(mfa.router, tags=["MFA"])

    if app:
        app.include_router(auth.router, prefix="/api", tags=["Authentication"])
        app.include_router(auth_compliance.router, prefix="/api", tags=["Auth Compliance"])
        app.include_router(coaching.router, prefix="/api", tags=["Coaching"])
        app.include_router(advanced_coaching.router, prefix="/api", tags=["Advanced Coaching"])
