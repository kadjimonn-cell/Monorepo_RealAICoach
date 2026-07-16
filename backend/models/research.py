"""Pydantic models for Deep Research Navigator feature.

Extracted from routes/research_navigator.py as part of Phase 1 model migration.
Centralizes request/response models for the research workspace APIs.
"""

from typing import Optional

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    """Request model for creating a new research project."""

    title: str = Field(min_length=2, max_length=160)
    topic: str = Field(default="", max_length=260)
    fallback_user_id: Optional[str] = None


class RunResearchRequest(BaseModel):
    """Request model for executing a research run within a project."""

    query: str = Field(min_length=3, max_length=800)
    fallback_user_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=120)


class AddInsightRequest(BaseModel):
    """Request model for saving a research insight."""

    title: str = Field(min_length=2, max_length=180)
    content: str = Field(min_length=3, max_length=5000)
    fallback_user_id: Optional[str] = None
