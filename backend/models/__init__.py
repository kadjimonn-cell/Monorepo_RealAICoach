"""
RealAICoach Backend Models

This package contains Pydantic models and data schemas organized by domain.

Structure:
- auth.py: Authentication and user models
- user.py: User data models and profiles
- jobs.py: Job platform and application models
- payments.py: Payment, invoice, and subscription models
- common.py: Shared base models and utilities

Usage:
    from models.auth import LoginRequest, RegisterRequest
    from models.user import User, UserResponse
    from models.jobs import JobPost, JobApplication, ResumeProfile
    from models.payments import CreateCheckoutRequest, PaymentRecord
    from models.common import ResponseBase, PaginatedResponse
"""

# Auth models
from models.auth import (
    RegisterRequest,
    LoginRequest,
    Verify2FARequest,
    OtpLoginRequest,
    OtpVerifyRequest,
    AdminE2EOtpIssueRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    AuthLookupResponse,
    SetPinRequest,
    RefreshTokenRequest,
    ChangePasswordRequest,
    Enable2FARequest,
    Disable2FARequest,
)

# User models
from models.user import (
    User,
    UserBase,
    UserResponse,
    UserUpdate,
    UserProfile,
    UserListResponse,
)

# Jobs models
from models.jobs import (
    JobPost,
    JobApplication,
    ResumeProfile,
)

# Payments models
from models.payments import (
    CreateCheckoutRequest,
    ConfirmPaymentRequest,
    CheckoutPreviewRequest,
    PaymentRecord,
)

# Research Navigator models (Phase 1 extraction)
from models.research import (
    CreateProjectRequest,
    RunResearchRequest,
    AddInsightRequest,
)

# Common models
from models.common import (
    ResponseBase,
    ErrorResponse,
    PaginationParams,
    PaginatedResponse,
    TimestampMixin,
)

__all__ = [
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "Verify2FARequest",
    "OtpLoginRequest",
    "OtpVerifyRequest",
    "AdminE2EOtpIssueRequest",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "AuthLookupResponse",
    "SetPinRequest",
    "RefreshTokenRequest",
    "ChangePasswordRequest",
    "Enable2FARequest",
    "Disable2FARequest",
    # User
    "User",
    "UserBase",
    "UserResponse",
    "UserUpdate",
    "UserProfile",
    "UserListResponse",
    # Jobs
    "JobPost",
    "JobApplication",
    "ResumeProfile",
    # Payments
    "CreateCheckoutRequest",
    "ConfirmPaymentRequest",
    "CheckoutPreviewRequest",
    "PaymentRecord",
    # Research Navigator
    "CreateProjectRequest",
    "RunResearchRequest",
    "AddInsightRequest",
    # Common
    "ResponseBase",
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
    "TimestampMixin",
]

