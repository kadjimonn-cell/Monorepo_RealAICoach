"""
Common Models and Base Classes

Shared Pydantic models and utilities used across multiple domains.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class TimestampMixin(BaseModel):
    """Mixin for models that need created_at and updated_at timestamps."""
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


class ResponseBase(BaseModel):
    """Base class for API responses."""
    
    success: bool = True
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response format."""
    
    success: bool = False
    error: str
    detail: Optional[str] = None
    status_code: int = 400


class PaginationParams(BaseModel):
    """Standard pagination parameters."""
    
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(default=50, ge=1, le=100, description="Items per page")
    
    @property
    def skip(self) -> int:
        """Calculate skip value for database queries."""
        return (self.page - 1) * self.limit


class PaginatedResponse(ResponseBase):
    """Base class for paginated responses."""
    
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")
    
    @classmethod
    def create(cls, items: list, total: int, page: int, limit: int, **kwargs):
        """Helper to create paginated response."""
        pages = (total + limit - 1) // limit  # Ceiling division
        return cls(
            total=total,
            page=page,
            limit=limit,
            pages=pages,
            items=items,
            **kwargs
        )
