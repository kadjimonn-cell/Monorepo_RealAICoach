"""
Authentication Models

Pydantic models for authentication, registration, password reset, and 2FA operations.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class Verify2FARequest(BaseModel):
    """Two-factor authentication verification."""
    user_id: str
    code: str = Field(..., min_length=6, max_length=6)


class OtpLoginRequest(BaseModel):
    """OTP-based login request."""
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    """OTP verification request."""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class AdminE2EOtpIssueRequest(BaseModel):
    """Admin E2E OTP issuance request."""
    email: EmailStr


class PasswordResetRequest(BaseModel):
    """Password reset initiation request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation with token."""
    token: str
    new_password: str = Field(..., min_length=8)


class AuthLookupResponse(BaseModel):
    """Authentication lookup response."""
    user_id: Optional[str] = None
    email: Optional[str] = None
    authenticated: bool = False
    admin: bool = False


class SetPinRequest(BaseModel):
    """Security PIN setup request."""
    pin: str = Field(..., min_length=4, max_length=6)
    confirm_pin: str = Field(..., min_length=4, max_length=6)


class RefreshTokenRequest(BaseModel):
    """JWT refresh token request."""
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class Enable2FARequest(BaseModel):
    """Enable two-factor authentication request."""
    method: str = Field(..., pattern="^(totp|sms|email)$")


class Disable2FARequest(BaseModel):
    """Disable two-factor authentication request."""
    password: str
    code: Optional[str] = None
