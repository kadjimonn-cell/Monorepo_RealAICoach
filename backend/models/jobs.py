"""
Job platform Pydantic models.

Extracted from `routes/jobs.py` as part of the Phase 2 model migration
(see /app/backend/models/README.md). These are the canonical schemas for
job posts, applications and resume profiles used across the careers/jobs
modules.
"""

from typing import List, Optional

from pydantic import BaseModel


class JobPost(BaseModel):
    """Employer-facing job listing payload."""

    title: str
    company_name: Optional[str] = None
    description: str
    requirements: Optional[str] = None
    location: str
    country: str
    job_type: str = "full_time"  # full_time, part_time, contract, freelance, internship
    remote: bool = False
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    industry: str = ""
    skills: List[str] = []
    experience_years: Optional[int] = None
    visa_sponsorship: bool = False
    application_deadline: Optional[str] = None


class JobApplication(BaseModel):
    """Candidate application to a specific job."""

    job_id: str
    cover_letter: Optional[str] = None


class ResumeProfile(BaseModel):
    """Candidate searchable resume / preferences profile."""

    skills: List[str] = []
    experience_years: Optional[int] = None
    education: Optional[str] = None
    preferred_location: Optional[str] = None
    preferred_job_type: Optional[str] = None
    preferred_salary_min: Optional[float] = None
    preferred_industry: Optional[str] = None
    remote_only: bool = False


__all__ = ["JobPost", "JobApplication", "ResumeProfile"]
