"""
User Models

Pydantic models for user data structures, profiles, and user-related operations.
"""

from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    """Base user model with common fields."""
    user_id: str
    email: EmailStr
    name: Optional[str] = None
    created_at: Optional[datetime] = None


class User(UserBase):
    """Complete user model."""
    is_active: bool = True
    is_admin: bool = False
    email_verified: bool = False
    two_factor_enabled: bool = False
    platform_role: Optional[str] = None
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None


class UserResponse(BaseModel):
    """User response model for API responses."""
    user_id: str
    email: EmailStr
    name: Optional[str] = None
    is_active: bool
    email_verified: bool
    platform_role: Optional[str] = None


class UserUpdate(BaseModel):
    """User update model for partial updates."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    platform_role: Optional[str] = None
    is_active: Optional[bool] = None


class UserProfile(BaseModel):
    """User profile model with extended information."""
    user_id: str
    email: EmailStr
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    preferences: Optional[dict] = None


class UserListResponse(BaseModel):
    """Paginated user list response."""
    users: List[UserResponse]
    total: int
    page: int
    limit: int
    pages: int
