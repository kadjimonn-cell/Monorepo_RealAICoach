"""Decision Coach - Pydantic Models."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# ── Request Models ──

class CreateDecisionRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    framework_type: Literal["pros_cons", "swot", "decision_matrix", "weighted_scoring"] = "pros_cons"
    deadline: Optional[str] = None
    fallback_user_id: Optional[str] = None


class UpdateDecisionRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    framework_data: Optional[Dict[str, Any]] = None
    status: Optional[Literal["draft", "analyzing", "decided", "tracked"]] = None
    fallback_user_id: Optional[str] = None


class AnalyzeDecisionRequest(BaseModel):
    fallback_user_id: Optional[str] = None


class DecideRequest(BaseModel):
    final_choice: str = Field(min_length=1, max_length=200)
    confidence_score: int = Field(ge=0, le=100)
    notes: str = Field(default="", max_length=1000)
    fallback_user_id: Optional[str] = None


class UpdateOutcomeRequest(BaseModel):
    satisfaction_score: int = Field(ge=1, le=10)
    lessons_learned: str = Field(default="", max_length=2000)
    would_decide_again: bool
    actual_result: Optional[str] = Field(None, max_length=500)
    fallback_user_id: Optional[str] = None


class CreateFromTemplateRequest(BaseModel):
    template_id: str
    title: Optional[str] = None
    fallback_user_id: Optional[str] = None


# ── Option Models ──

class ProConItem(BaseModel):
    item_id: str
    text: str
    weight: int = Field(default=5, ge=1, le=10)


class DecisionOption(BaseModel):
    option_id: str
    name: str
    pros: List[ProConItem] = []
    cons: List[ProConItem] = []
    score: Optional[float] = None


class SwotQuadrant(BaseModel):
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []


class MatrixCriteria(BaseModel):
    criteria_id: str
    name: str
    weight: int = Field(ge=1, le=10)
    description: Optional[str] = None


class MatrixScore(BaseModel):
    option_name: str
    criteria_scores: Dict[str, int]  # criteria_id -> score (1-5)
    total_weighted_score: float


# ── AI Analysis Models ──

class AIAnalysisResult(BaseModel):
    summary: str
    recommendation: str
    confidence: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    key_insights: List[str]
    bias_warnings: List[str] = []
    risk_factors: Dict[str, str] = {}


# ── Response Models ──

class DecisionResponse(BaseModel):
    decision_id: str
    owner_id: str
    title: str
    description: str
    framework_type: str
    status: str
    created_at: str
    updated_at: str
    decided_at: Optional[str] = None
    deadline: Optional[str] = None
    final_choice: Optional[str] = None
    confidence_score: Optional[int] = None
    framework_data: Dict[str, Any] = {}
    ai_analysis: Optional[Dict[str, Any]] = None
    outcome: Optional[Dict[str, Any]] = None


class UsageStatsResponse(BaseModel):
    decisions_used_this_month: int
    monthly_limit: int
    can_create: bool
    tier: str
    limit_reached: bool
    frameworks_available: List[str]
    templates_available: str


class TemplateResponse(BaseModel):
    template_id: str
    name: str
    description: str
    category: str
    framework_type: str
    tier_requirement: str
    icon: str
    color: str
    usage_count: int


class AnalyticsResponse(BaseModel):
    total_decisions: int
    decisions_this_month: int
    avg_confidence_score: float
    success_rate: float  # % with satisfaction >= 7
    most_used_framework: str
    decision_speed_avg_hours: float
    framework_usage: Dict[str, int]
    recent_decisions: List[Dict[str, Any]]
