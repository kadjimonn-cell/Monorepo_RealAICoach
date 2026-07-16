"""Workflow Builder - Pydantic Models for Enterprise-Grade Workflow Automation."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ── Node Models ──


class NodeConfig(BaseModel):
    """Base configuration for all node types."""

    model_config = {"extra": "allow"}


class WorkflowNode(BaseModel):
    """Represents a single node in a workflow."""

    node_id: str = Field(..., description="Unique node identifier")
    type: Literal["trigger", "action", "condition", "loop"] = Field(
        ..., description="Node type"
    )
    action: str = Field(..., description="Action identifier (e.g., 'ai_completion', 'http_request')")
    label: Optional[str] = Field(None, description="Human-readable node label")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node-specific configuration")
    position: Optional[Dict[str, float]] = Field(
        None, description="UI position {x, y} for visual canvas"
    )


class WorkflowEdge(BaseModel):
    """Represents a connection between two nodes."""

    from_node: str = Field(..., description="Source node ID", alias="from")
    to_node: str = Field(..., description="Target node ID", alias="to")
    condition: Optional[str] = Field(None, description="Conditional edge (e.g., 'if success')")

    class Config:
        populate_by_name = True


# ── Workflow Models ──


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)
    enabled: bool = Field(default=False, description="Whether workflow is active")
    fallback_user_id: Optional[str] = None


class UpdateWorkflowRequest(BaseModel):
    """Request to update an existing workflow."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    nodes: Optional[List[WorkflowNode]] = None
    edges: Optional[List[WorkflowEdge]] = None
    enabled: Optional[bool] = None


class ExecuteWorkflowRequest(BaseModel):
    """Request to manually execute a workflow."""

    input_data: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Initial input variables"
    )
    fallback_user_id: Optional[str] = None


# ── Execution Models ──


class NodeExecutionResult(BaseModel):
    """Result of a single node execution."""

    node_id: str
    status: Literal["success", "failed", "skipped"]
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: int = 0
    executed_at: str


class WorkflowExecution(BaseModel):
    """Complete workflow execution record."""

    execution_id: str
    workflow_id: str
    owner_id: str
    status: Literal["running", "completed", "failed"]
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: int = 0
    node_results: Dict[str, NodeExecutionResult] = Field(default_factory=dict)
    error: Optional[str] = None
    trigger_type: str = Field(default="manual", description="How workflow was triggered")


# ── Response Models ──


class WorkflowResponse(BaseModel):
    """API response for a workflow."""

    workflow_id: str
    owner_id: str
    name: str
    description: Optional[str]
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
    enabled: bool
    created_at: str
    updated_at: str
    execution_count: int = 0


class WorkflowUsageResponse(BaseModel):
    """Usage statistics for tier enforcement."""

    workflow_count: int
    workflow_limit: int
    executions_this_month: int
    execution_limit: int
    tier: str
    can_create_workflow: bool
    can_execute: bool
    limit_reached: bool


__all__ = [
    "WorkflowNode",
    "WorkflowEdge",
    "CreateWorkflowRequest",
    "UpdateWorkflowRequest",
    "ExecuteWorkflowRequest",
    "NodeExecutionResult",
    "WorkflowExecution",
    "WorkflowResponse",
    "WorkflowUsageResponse",
]
