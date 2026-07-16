"""Workflow Builder - Enterprise-grade workflow automation API."""

from __future__ import annotations

import time
import uuid
import ast
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from models.workflow import (
    CreateWorkflowRequest,
    ExecuteWorkflowRequest,
    NodeExecutionResult,
    UpdateWorkflowRequest,
    WorkflowExecution,
    WorkflowResponse,
    WorkflowUsageResponse,
)
from routes.db import db, get_current_user
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/workflows", tags=["Workflow Builder"])


# ── Tier Configuration ──

TIER_LIMITS = {
    "free": {
        "max_workflows": 10,
        "max_executions_per_month": 100,
    },
    "basic": {
        "max_workflows": 50,
        "max_executions_per_month": 500,
    },
    "premium": {
        "max_workflows": -1,  # Unlimited
        "max_executions_per_month": -1,  # Unlimited
    },
}


# ── Helper Functions ──


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


_SAFE_EXPR_BUILTINS: Dict[str, Any] = {
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
}

_SAFE_STR_METHODS = {"lower", "upper", "strip", "startswith", "endswith", "split", "replace", "title"}
_SAFE_LIST_METHODS = {"count", "index"}
_SAFE_DICT_METHODS = {"get", "keys", "values", "items"}


def _safe_ast_run(node: ast.AST, local_ctx: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _safe_ast_run(node.body, local_ctx)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in {"True", "False", "None"}:
            return {"True": True, "False": False, "None": None}[node.id]
        if node.id in local_ctx:
            return local_ctx[node.id]
        if node.id in _SAFE_EXPR_BUILTINS:
            return _SAFE_EXPR_BUILTINS[node.id]
        raise ValueError(f"Unknown variable/function: {node.id}")

    if isinstance(node, ast.List):
        return [_safe_ast_run(elt, local_ctx) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_ast_run(elt, local_ctx) for elt in node.elts)
    if isinstance(node, ast.Set):
        return {_safe_ast_run(elt, local_ctx) for elt in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _safe_ast_run(k, local_ctx): _safe_ast_run(v, local_ctx)
            for k, v in zip(node.keys, node.values)
        }

    if isinstance(node, ast.BinOp):
        left = _safe_ast_run(node.left, local_ctx)
        right = _safe_ast_run(node.right, local_ctx)
        ops = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b,
            ast.FloorDiv: lambda a, b: a // b,
            ast.Mod: lambda a, b: a % b,
            ast.Pow: lambda a, b: a ** b,
        }
        fn = ops.get(type(node.op))
        if not fn:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        return fn(left, right)

    if isinstance(node, ast.UnaryOp):
        value = _safe_ast_run(node.operand, local_ctx)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.USub):
            return -value
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_safe_ast_run(v, local_ctx) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_safe_ast_run(v, local_ctx) for v in node.values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        left = _safe_ast_run(node.left, local_ctx)
        cmp_ops = {
            ast.Eq: lambda a, b: a == b,
            ast.NotEq: lambda a, b: a != b,
            ast.Lt: lambda a, b: a < b,
            ast.LtE: lambda a, b: a <= b,
            ast.Gt: lambda a, b: a > b,
            ast.GtE: lambda a, b: a >= b,
            ast.In: lambda a, b: a in b,
            ast.NotIn: lambda a, b: a not in b,
            ast.Is: lambda a, b: a is b,
            ast.IsNot: lambda a, b: a is not b,
        }
        for op, comparator in zip(node.ops, node.comparators):
            right = _safe_ast_run(comparator, local_ctx)
            fn = cmp_ops.get(type(op))
            if not fn:
                raise ValueError(f"Unsupported comparator: {type(op).__name__}")
            if not fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.IfExp):
        return _safe_ast_run(node.body if _safe_ast_run(node.test, local_ctx) else node.orelse, local_ctx)

    if isinstance(node, ast.Subscript):
        value = _safe_ast_run(node.value, local_ctx)
        index_node = node.slice.value if isinstance(node.slice, ast.Index) else node.slice
        key = _safe_ast_run(index_node, local_ctx)
        return value[key]

    if isinstance(node, ast.Attribute):
        attr = str(node.attr)
        if attr.startswith("__"):
            raise ValueError("Dunder attribute access is not allowed")
        value = _safe_ast_run(node.value, local_ctx)
        return getattr(value, attr)

    if isinstance(node, ast.Call):
        args = [_safe_ast_run(arg, local_ctx) for arg in node.args]
        kwargs = {kw.arg: _safe_ast_run(kw.value, local_ctx) for kw in node.keywords if kw.arg}

        if isinstance(node.func, ast.Name):
            fn_name = node.func.id
            if fn_name not in _SAFE_EXPR_BUILTINS:
                raise ValueError("Only safe builtin calls are allowed")
            return _SAFE_EXPR_BUILTINS[fn_name](*args, **kwargs)

        if isinstance(node.func, ast.Attribute):
            attr = str(node.func.attr)
            target = _safe_ast_run(node.func.value, local_ctx)
            if attr.startswith("__"):
                raise ValueError("Dunder attribute call is not allowed")
            if isinstance(target, str) and attr in _SAFE_STR_METHODS:
                return getattr(target, attr)(*args, **kwargs)
            if isinstance(target, list) and attr in _SAFE_LIST_METHODS:
                return getattr(target, attr)(*args, **kwargs)
            if isinstance(target, dict) and attr in _SAFE_DICT_METHODS:
                return getattr(target, attr)(*args, **kwargs)
            raise ValueError(f"Unsupported method call: {type(target).__name__}.{attr}")

        raise ValueError("Unsupported call target")

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def _safe_eval_expression(expr: Any, local_ctx: Dict[str, Any], *, default: Any = None) -> Any:
    """Evaluate simple expressions safely for workflow transforms/conditions."""
    text = str(expr or "").strip()
    if not text:
        return default

    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.Lambda,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.With,
        ast.AsyncWith,
        ast.Global,
        ast.Nonlocal,
        ast.Try,
        ast.Raise,
        ast.Delete,
        ast.Yield,
        ast.YieldFrom,
    )
    allowed_calls = set(_SAFE_EXPR_BUILTINS.keys())

    tree = ast.parse(text, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError(f"Unsupported expression node: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id not in local_ctx and node.id not in allowed_calls and node.id not in {"True", "False", "None"}:
                raise ValueError(f"Unknown variable/function: {node.id}")
        if isinstance(node, ast.Attribute):
            if str(node.attr).startswith("__"):
                raise ValueError("Dunder attribute access is not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls:
                raise ValueError("Only safe builtin calls are allowed")

    return _safe_ast_run(tree, {**_SAFE_EXPR_BUILTINS, **local_ctx})


def _resolve_owner_id(user: Optional[Any], fallback: Optional[str]) -> str:
    """Resolve owner ID from authenticated user or fallback."""
    if user and hasattr(user, "user_id"):
        return f"auth:{str(user.user_id)}"
    if fallback and len(fallback) >= 12:
        return f"guest:{fallback}"
    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "workflow_auth_required",
            "message": "Login required or provide fallback_user_id (min 12 chars)",
        },
    )


async def _get_user_tier(owner_id: str) -> str:
    """Get user's subscription tier."""
    user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")
    if not user_id:
        return "free"

    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


async def _get_workflow_count(owner_id: str) -> int:
    """Count total workflows for a user."""
    return await db.workflows.count_documents({"owner_id": owner_id})


async def _get_monthly_execution_count(owner_id: str) -> int:
    """Count executions in current month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return await db.workflow_executions.count_documents({
        "owner_id": owner_id,
        "started_at": {"$gte": month_start.isoformat()},
    })


async def _check_workflow_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can create workflows."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    workflow_count = await _get_workflow_count(owner_id)
    max_workflows = limits["max_workflows"]
    
    can_create = max_workflows == -1 or workflow_count < max_workflows
    
    return {
        "can_create": can_create,
        "workflow_count": workflow_count,
        "workflow_limit": max_workflows,
        "tier": tier,
    }


async def _check_execution_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can execute workflows."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    executions_count = await _get_monthly_execution_count(owner_id)
    max_executions = limits["max_executions_per_month"]
    
    can_execute = max_executions == -1 or executions_count < max_executions
    
    return {
        "can_execute": can_execute,
        "executions_this_month": executions_count,
        "execution_limit": max_executions,
        "tier": tier,
    }



# ── Workflow Templates ──

WORKFLOW_TEMPLATES = [
    {
        "template_id": "template_email_summarizer",
        "name": "Daily Email Summarizer",
        "description": "Fetch emails via HTTP and generate AI summary daily",
        "category": "email",
        "icon": "mail-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_fetch_emails",
                "type": "action",
                "action": "http_request",
                "label": "Fetch Emails",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com/emails",
                    "headers": {"Authorization": "Bearer YOUR_TOKEN"}
                }
            },
            {
                "node_id": "node_summarize",
                "type": "action",
                "action": "ai_completion",
                "label": "Generate Summary",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Summarize these emails: {{node_fetch_emails.response}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Email management", "Daily briefings", "Inbox automation"]
    },
    {
        "template_id": "template_content_publisher",
        "name": "Content Publisher",
        "description": "Generate blog content with AI and publish via API",
        "category": "content",
        "icon": "newspaper-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_generate_content",
                "type": "action",
                "action": "ai_completion",
                "label": "Generate Content",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Write a blog post about: {{input.topic}}"
                }
            },
            {
                "node_id": "node_generate_image",
                "type": "action",
                "action": "ai_image",
                "label": "Generate Hero Image",
                "config": {
                    "prompt": "Hero image for: {{input.topic}}"
                }
            },
            {
                "node_id": "node_publish",
                "type": "action",
                "action": "http_request",
                "label": "Publish to CMS",
                "config": {
                    "method": "POST",
                    "url": "https://api.example.com/posts",
                    "body": {
                        "title": "{{input.topic}}",
                        "content": "{{node_generate_content.response}}",
                        "image_url": "{{node_generate_image.url}}"
                    }
                }
            }
        ],
        "edges": [],
        "use_cases": ["Blog automation", "Content marketing", "Social media"]
    },
    {
        "template_id": "template_data_processor",
        "name": "Data Processor",
        "description": "Fetch, transform, and store data with JSON operations",
        "category": "data",
        "icon": "server-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_fetch_data",
                "type": "action",
                "action": "http_request",
                "label": "Fetch Data",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com/data"
                }
            },
            {
                "node_id": "node_transform",
                "type": "action",
                "action": "transform_json",
                "label": "Transform Data",
                "config": {
                    "path": "$.items[*]",
                    "mapping": {
                        "id": "$.id",
                        "value": "$.amount"
                    }
                }
            },
            {
                "node_id": "node_filter",
                "type": "action",
                "action": "filter_array",
                "label": "Filter Results",
                "config": {
                    "condition": "item.value > 100"
                }
            },
            {
                "node_id": "node_store",
                "type": "action",
                "action": "http_request",
                "label": "Store to Database",
                "config": {
                    "method": "POST",
                    "url": "https://api.example.com/store",
                    "body": "{{node_filter.result}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Data pipelines", "ETL processes", "API integration"]
    },
    {
        "template_id": "template_ai_assistant",
        "name": "AI Research Assistant",
        "description": "Multi-step AI research with web search and synthesis",
        "category": "ai",
        "icon": "bulb-outline",
        "tier_requirement": "basic",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_research",
                "type": "action",
                "action": "ai_chat",
                "label": "Research Topic",
                "config": {
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": "You are a research assistant"},
                        {"role": "user", "content": "Research: {{input.query}}"}
                    ]
                }
            },
            {
                "node_id": "node_synthesize",
                "type": "action",
                "action": "ai_completion",
                "label": "Synthesize Report",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Create a research report from: {{node_research.response}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Research automation", "Knowledge synthesis", "Report generation"]
    },
    {
        "template_id": "template_lead_enrichment",
        "name": "Lead Enrichment Pipeline",
        "description": "Enrich lead data with external APIs and AI",
        "category": "sales",
        "icon": "people-outline",
        "tier_requirement": "basic",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_fetch_lead",
                "type": "action",
                "action": "http_request",
                "label": "Fetch Lead Data",
                "config": {
                    "method": "GET",
                    "url": "https://crm.example.com/leads/{{input.lead_id}}"
                }
            },
            {
                "node_id": "node_enrich",
                "type": "action",
                "action": "http_request",
                "label": "Enrich with Clearbit",
                "config": {
                    "method": "GET",
                    "url": "https://person.clearbit.com/v2/combined/find?email={{node_fetch_lead.email}}"
                }
            },
            {
                "node_id": "node_score",
                "type": "action",
                "action": "ai_completion",
                "label": "AI Lead Scoring",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Score this lead (1-10): {{node_enrich.response}}"
                }
            },
            {
                "node_id": "node_update_crm",
                "type": "action",
                "action": "http_request",
                "label": "Update CRM",
                "config": {
                    "method": "PUT",
                    "url": "https://crm.example.com/leads/{{input.lead_id}}",
                    "body": {"score": "{{node_score.response}}"}
                }
            }
        ],
        "edges": [],
        "use_cases": ["Sales automation", "Lead qualification", "CRM enrichment"]
    },
    {
        "template_id": "template_social_poster",
        "name": "Social Media Auto-Poster",
        "description": "Generate and post social content across platforms",
        "category": "content",
        "icon": "share-social-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_generate_post",
                "type": "action",
                "action": "ai_completion",
                "label": "Generate Post",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Create an engaging social media post about: {{input.topic}}"
                }
            },
            {
                "node_id": "node_post_twitter",
                "type": "action",
                "action": "http_request",
                "label": "Post to Twitter",
                "config": {
                    "method": "POST",
                    "url": "https://api.twitter.com/2/tweets",
                    "body": {"text": "{{node_generate_post.response}}"}
                }
            },
            {
                "node_id": "node_post_linkedin",
                "type": "action",
                "action": "http_request",
                "label": "Post to LinkedIn",
                "config": {
                    "method": "POST",
                    "url": "https://api.linkedin.com/v2/shares",
                    "body": {"text": "{{node_generate_post.response}}"}
                }
            }
        ],
        "edges": [],
        "use_cases": ["Social media", "Content distribution", "Marketing automation"]
    },
    {
        "template_id": "template_alert_system",
        "name": "Real-Time Alert System",
        "description": "Monitor conditions and send alerts via email/SMS",
        "category": "monitoring",
        "icon": "notifications-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_check_status",
                "type": "action",
                "action": "http_request",
                "label": "Check System Status",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com/status"
                }
            },
            {
                "node_id": "node_condition",
                "type": "condition",
                "action": "condition",
                "label": "Check if Down",
                "config": {
                    "condition": "{{node_check_status.status}} != 'healthy'"
                }
            },
            {
                "node_id": "node_send_alert",
                "type": "action",
                "action": "send_email",
                "label": "Send Alert Email",
                "config": {
                    "to": "admin@example.com",
                    "subject": "System Down Alert",
                    "body": "System status: {{node_check_status.status}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["System monitoring", "Alerting", "DevOps automation"]
    },
    {
        "template_id": "template_document_ai",
        "name": "Document AI Processor",
        "description": "Extract text from documents and analyze with AI",
        "category": "ai",
        "icon": "document-text-outline",
        "tier_requirement": "basic",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_parse_doc",
                "type": "action",
                "action": "parse_text",
                "label": "Extract Text",
                "config": {
                    "source": "{{input.document_url}}"
                }
            },
            {
                "node_id": "node_analyze",
                "type": "action",
                "action": "ai_completion",
                "label": "Analyze Document",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Analyze this document: {{node_parse_doc.text}}"
                }
            },
            {
                "node_id": "node_summarize",
                "type": "action",
                "action": "ai_completion",
                "label": "Generate Summary",
                "config": {
                    "model": "gpt-4o",
                    "prompt": "Summarize: {{node_analyze.response}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Document processing", "Contract analysis", "Content extraction"]
    },
    {
        "template_id": "template_ecommerce_sync",
        "name": "E-Commerce Inventory Sync",
        "description": "Sync inventory across multiple e-commerce platforms",
        "category": "ecommerce",
        "icon": "cart-outline",
        "tier_requirement": "basic",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_fetch_shopify",
                "type": "action",
                "action": "http_request",
                "label": "Fetch Shopify Inventory",
                "config": {
                    "method": "GET",
                    "url": "https://{{shop}}.myshopify.com/admin/api/2023-01/products.json"
                }
            },
            {
                "node_id": "node_transform_data",
                "type": "action",
                "action": "transform_json",
                "label": "Transform to WooCommerce Format",
                "config": {
                    "path": "$.products[*]",
                    "mapping": {"sku": "$.variants[0].sku", "stock": "$.variants[0].inventory_quantity"}
                }
            },
            {
                "node_id": "node_update_woo",
                "type": "action",
                "action": "http_request",
                "label": "Update WooCommerce",
                "config": {
                    "method": "POST",
                    "url": "https://example.com/wp-json/wc/v3/products/batch",
                    "body": "{{node_transform_data.result}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Inventory management", "Multi-platform sync", "E-commerce automation"]
    },
    {
        "template_id": "template_data_backup",
        "name": "Automated Data Backup",
        "description": "Backup data from APIs to cloud storage daily",
        "category": "data",
        "icon": "cloud-upload-outline",
        "tier_requirement": "free",
        "nodes": [
            {
                "node_id": "node_trigger",
                "type": "trigger",
                "action": "manual",
                "label": "Manual Trigger",
                "config": {}
            },
            {
                "node_id": "node_fetch_data",
                "type": "action",
                "action": "http_request",
                "label": "Fetch Data",
                "config": {
                    "method": "GET",
                    "url": "https://api.example.com/data/export"
                }
            },
            {
                "node_id": "node_transform",
                "type": "action",
                "action": "transform_json",
                "label": "Format Data",
                "config": {
                    "path": "$",
                    "mapping": {"timestamp": "{{now}}", "data": "{{node_fetch_data.response}}"}
                }
            },
            {
                "node_id": "node_upload",
                "type": "action",
                "action": "http_request",
                "label": "Upload to S3",
                "config": {
                    "method": "PUT",
                    "url": "https://s3.amazonaws.com/backups/{{now}}.json",
                    "body": "{{node_transform.result}}"
                }
            }
        ],
        "edges": [],
        "use_cases": ["Data backup", "Disaster recovery", "Compliance"]
    }
]


@router.get("/templates")
async def get_workflow_templates(request: Request, category: Optional[str] = None):
    """Get available workflow templates."""
    user = await get_current_user(request)
    user_tier = "free"
    
    if user and hasattr(user, "user_id"):
        user_tier = await _get_user_tier(user.user_id)
    
    # Filter templates by tier and category
    filtered_templates = []
    for template in WORKFLOW_TEMPLATES:
        # Check tier access
        template_tier = template.get("tier_requirement", "free")
        if not _has_tier_access(user_tier, template_tier):
            continue
        
        # Check category filter
        if category and template.get("category") != category:
            continue
        
        filtered_templates.append(template)
    
    return {"templates": filtered_templates}


def _has_tier_access(user_tier: str, required_tier: str) -> bool:
    """Check if user tier has access to required tier."""
    tier_hierarchy = {"free": 0, "basic": 1, "premium": 2}
    user_level = tier_hierarchy.get(user_tier, 0)
    required_level = tier_hierarchy.get(required_tier, 0)
    return user_level >= required_level


@router.post("/from-template")
async def create_workflow_from_template(
    request: Request,
    template_id: str,
    custom_name: Optional[str] = None,
    fallback_user_id: Optional[str] = None
):
    """Create a new workflow from a template."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Find template
    template = next((t for t in WORKFLOW_TEMPLATES if t["template_id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check tier access
    user_tier = await _get_user_tier(owner_id)
    if not _has_tier_access(user_tier, template.get("tier_requirement", "free")):
        raise HTTPException(
            status_code=403,
            detail=f"This template requires {template['tier_requirement']} tier or higher"
        )
    
    # Check workflow limit
    limit_check = await _check_workflow_limit(owner_id, user_tier)
    if not limit_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "workflow_limit_reached",
                "message": f"Workflow limit reached ({limit_check['workflow_count']}/{limit_check['workflow_limit']} for {user_tier} tier)",
                "upgrade_prompt": True,
            },
        )
    
    # Create workflow from template
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    workflow_name = custom_name or template["name"]
    
    workflow_doc = {
        "workflow_id": workflow_id,
        "name": workflow_name,
        "description": template["description"],
        "owner_id": owner_id,
        "enabled": False,
        "nodes": template["nodes"],
        "edges": template.get("edges", []),
        "tier_requirement": template.get("tier_requirement", "free"),
        "created_from_template": template_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "execution_count": 0,
    }
    
    await db.workflows.insert_one(workflow_doc)
    
    return {
        "workflow_id": workflow_id,
        "name": workflow_name,
        "description": template["description"],
        "nodes": template["nodes"],
        "edges": template.get("edges", []),
        "enabled": False,
        "created_from_template": template_id,
        "message": f"Workflow created from template: {template['name']}"
    }


# ── Basic Execution Engine ──


async def _execute_node(node: Dict[str, Any], context: Dict[str, Any]) -> NodeExecutionResult:
    """Execute a single workflow node."""
    start_time = time.time()
    node_id = node["node_id"]
    action = node["action"]
    config = node.get("config", {})
    
    try:
        # Route to appropriate executor
        if action == "ai_completion":
            output = await _execute_ai_completion(config, context)
        elif action == "ai_chat":
            output = await _execute_ai_chat(config, context)
        elif action == "ai_image_gen":
            output = await _execute_ai_image_gen(config, context)
        elif action == "http_request":
            output = await _execute_http_request(config, context)
        elif action == "transform_json":
            output = await _execute_transform_json(config, context)
        elif action == "filter_array":
            output = await _execute_filter_array(config, context)
        elif action == "parse_text":
            output = await _execute_parse_text(config, context)
        elif action == "send_email":
            output = await _execute_send_email(config, context)
        elif action == "condition":
            output = await _execute_condition(config, context)
        elif action == "loop":
            output = await _execute_loop(config, context)
        elif action == "delay":
            output = await _execute_delay(config, context)
        else:
            raise ValueError(f"Unknown action type: {action}")
        
        duration_ms = int((time.time() - start_time) * 1000)
        return NodeExecutionResult(
            node_id=node_id,
            status="success",
            output=output,
            duration_ms=duration_ms,
            executed_at=_now_iso(),
        )
    
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return NodeExecutionResult(
            node_id=node_id,
            status="failed",
            error=str(e),
            duration_ms=duration_ms,
            executed_at=_now_iso(),
        )


# ── Workflow Scheduling (Cron-based) ──

@router.put("/{workflow_id}/schedule")
async def set_workflow_schedule(
    workflow_id: str,
    request: Request,
    cron_expression: str,
    timezone: str = "UTC",
    enabled: bool = True,
    fallback_user_id: Optional[str] = None
):
    """Set or update cron schedule for a workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Validate cron expression (basic validation)
    if not _validate_cron_expression(cron_expression):
        raise HTTPException(
            status_code=400,
            detail="Invalid cron expression. Use format: '* * * * *' (minute hour day month weekday)"
        )
    
    # Calculate next run time
    next_run = _calculate_next_run(cron_expression, timezone)
    
    # Update workflow with schedule
    schedule_config = {
        "cron_expression": cron_expression,
        "timezone": timezone,
        "enabled": enabled,
        "next_run": next_run,
        "last_run": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso()
    }
    
    await db.workflows.update_one(
        {"workflow_id": workflow_id},
        {
            "$set": {
                "schedule": schedule_config,
                "updated_at": _now_iso()
            }
        }
    )
    
    return {
        "workflow_id": workflow_id,
        "schedule": schedule_config,
        "message": f"Workflow scheduled: {cron_expression} ({timezone})"
    }


@router.delete("/{workflow_id}/schedule")
async def remove_workflow_schedule(
    workflow_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Remove cron schedule from a workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if not workflow.get("schedule"):
        raise HTTPException(status_code=404, detail="Workflow has no schedule")
    
    # Remove schedule
    await db.workflows.update_one(
        {"workflow_id": workflow_id},
        {
            "$unset": {"schedule": ""},
            "$set": {"updated_at": _now_iso()}
        }
    )
    
    return {
        "workflow_id": workflow_id,
        "message": "Schedule removed successfully"
    }


@router.get("/scheduled/list")
async def get_scheduled_workflows(
    request: Request,
    fallback_user_id: Optional[str] = None,
    enabled_only: bool = True
):
    """Get all scheduled workflows for the current user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Build query
    query = {"owner_id": owner_id, "schedule": {"$exists": True}}
    
    if enabled_only:
        query["schedule.enabled"] = True
    
    # Fetch workflows
    workflows = await db.workflows.find(query, {"_id": 0}).to_list(1000)
    
    # Sort by next_run
    workflows.sort(key=lambda w: w.get("schedule", {}).get("next_run", ""))
    
    return {
        "scheduled_workflows": workflows,
        "count": len(workflows)
    }


def _validate_cron_expression(cron_expr: str) -> bool:
    """Basic validation of cron expression format."""
    parts = cron_expr.strip().split()
    
    # Should have 5 parts: minute hour day month weekday
    if len(parts) != 5:
        return False
    
    # Each part should be valid (*, number, range, or list)
    for part in parts:
        if part == "*":
            continue
        # Check if it's a number, range (1-5), or list (1,2,3)
        if not (part.replace("-", "").replace(",", "").replace("/", "").isdigit()):
            return False
    
    return True


def _calculate_next_run(cron_expr: str, tz: str) -> str:
    """Calculate next run time for a cron expression."""
    # Simplified: just return a timestamp 1 hour from now
    # In production, use croniter or APScheduler for accurate calculation
    from datetime import timedelta
    
    next_run = datetime.now(timezone.utc) + timedelta(hours=1)
    return next_run.isoformat()


@router.post("/{workflow_id}/schedule/trigger")
async def manually_trigger_scheduled_workflow(
    workflow_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Manually trigger a scheduled workflow (testing purposes)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if not workflow.get("schedule"):
        raise HTTPException(status_code=400, detail="Workflow is not scheduled")
    
    # Execute workflow
    execution = await _execute_workflow(workflow, {})
    
    # Update last_run and calculate next_run
    schedule = workflow.get("schedule", {})
    next_run = _calculate_next_run(schedule.get("cron_expression", ""), schedule.get("timezone", "UTC"))
    
    await db.workflows.update_one(
        {"workflow_id": workflow_id},
        {
            "$set": {
                "schedule.last_run": _now_iso(),
                "schedule.next_run": next_run
            },
            "$inc": {"execution_count": 1}
        }
    )
    
    return {
        "workflow_id": workflow_id,
        "execution": execution,
        "next_run": next_run,
        "message": "Scheduled workflow triggered manually"
    }


async def _execute_ai_completion(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute AI completion action."""
    import uuid
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.db import EMERGENT_LLM_KEY
    
    prompt = config.get("prompt", "").format(**context)
    model = config.get("model", "gpt-4o")
    
    # Map model names to provider and model
    model_map = {
        "claude-sonnet-4": ("anthropic", "claude-sonnet-4-6"),
        "claude-sonnet-4-6": ("anthropic", "claude-sonnet-4-6"),
        "gpt-4o": ("openai", "gpt-4o"),
        "gpt-4o-mini": ("openai", "gpt-4o-mini"),
        "gpt-5.2": ("openai", "gpt-5.2"),
    }
    
    provider, model_id = model_map.get(model, ("openai", "gpt-4o"))
    
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"workflow-{uuid.uuid4().hex[:8]}",
        system_message="You are a helpful AI assistant.",
    ).with_model(provider, model_id)
    
    try:
        response = await llm.send_message(UserMessage(text=prompt))
    except Exception as exc:
        if "Invalid model name" not in str(exc):
            raise
        fallback = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"workflow-{uuid.uuid4().hex[:8]}",
            system_message="You are a helpful AI assistant.",
        ).with_model("openai", "gpt-4o")
        response = await fallback.send_message(UserMessage(text=prompt))
    
    return {
        "text": str(getattr(response, "text", None) or response),
        "model": model,
    }


def _normalize_chat_model(provider: Optional[str], model: Optional[str]) -> tuple[str, str]:
    """Normalize chat provider/model aliases to supported runtime values."""
    raw_provider = str(provider or "").strip().lower()
    raw_model = str(model or "").strip().lower()

    if "/" in raw_model:
        pref_provider, pref_model = raw_model.split("/", 1)
        if pref_provider:
            raw_provider = pref_provider
        raw_model = pref_model

    provider_alias = {
        "openai": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
    }
    normalized_provider = provider_alias.get(raw_provider, "openai")

    model_aliases: dict[str, tuple[str, str]] = {
        "claude-sonnet-4": ("anthropic", "claude-sonnet-4-6"),
        "claude-sonnet-4-20250514": ("anthropic", "claude-sonnet-4-6"),
        "claude-4-sonnet-20250514": ("anthropic", "claude-sonnet-4-6"),
        "claude-sonnet-4-6": ("anthropic", "claude-sonnet-4-6"),
        "gpt-4o": ("openai", "gpt-4o"),
        "gpt-4o-mini": ("openai", "gpt-4o-mini"),
        "gpt-5.2": ("openai", "gpt-5.2"),
        "gpt-5.4": ("openai", "gpt-5.4"),
    }

    if raw_model in model_aliases:
        return model_aliases[raw_model]

    if not raw_model:
        return "openai", "gpt-4o"

    return normalized_provider, raw_model


def _normalize_image_model(model: Optional[str]) -> str:
    """Normalize image model aliases for OpenAI image generation runtime."""
    raw_model = str(model or "").strip().lower()
    aliases = {
        "nano-banana": "gpt-image-1",
        "gemini-nano-banana": "gpt-image-1",
        "gpt-image-1": "gpt-image-1",
    }
    return aliases.get(raw_model, raw_model or "gpt-image-1")


async def _execute_http_request(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute HTTP request action."""
    import httpx
    
    url = config.get("url", "").format(**context)
    method = config.get("method", "GET").upper()
    headers = config.get("headers", {})
    body = config.get("body", {})
    
    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=body)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        return {
            "status_code": response.status_code,
            "body": response.text,
            "headers": dict(response.headers),
        }


async def _execute_delay(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute delay action."""
    import asyncio
    
    seconds = config.get("seconds", 1)
    await asyncio.sleep(seconds)
    
    return {
        "delayed_seconds": seconds,
    }


async def _execute_ai_chat(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute AI chat action (multi-turn conversation)."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.db import EMERGENT_LLM_KEY
    
    messages = config.get("messages", [])
    system_message = config.get("system_message", "")
    
    # Format messages with context
    formatted_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "").format(**context)
        if role == "user":
            formatted_messages.append(UserMessage(text=content))
    
    requested_provider = config.get("provider", "openai")
    requested_model = config.get("model", "gpt-4o")
    provider, model_id = _normalize_chat_model(requested_provider, requested_model)
    
    # Create session ID for this workflow execution
    session_id = f"workflow-{uuid.uuid4().hex[:8]}"
    
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_message,
    ).with_model(provider, model_id)

    response_text = ""
    for msg in formatted_messages:
        try:
            response = await llm.send_message(msg)
        except Exception as exc:
            invalid_model_err = "Invalid model name" in str(exc) or "model=" in str(exc)
            if not invalid_model_err:
                raise
            fallback_llm = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"{session_id}-fallback",
                system_message=system_message,
            ).with_model("openai", "gpt-4o")
            response = await fallback_llm.send_message(msg)
        response_text = str(getattr(response, "text", None) or response)
    
    return {
        "response": response_text,
        "model": f"{provider}/{model_id}",
    }


async def _execute_ai_image_gen(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute AI image generation action."""
    import base64

    from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
    from routes.db import EMERGENT_LLM_KEY
    
    prompt = config.get("prompt", "").format(**context)
    requested_model = config.get("model", "gpt-image-1")
    model = _normalize_image_model(requested_model)
    
    # Initialize image generator
    image_gen = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
    
    # Generate image - returns list of image URLs
    try:
        images = await image_gen.generate_images(
            prompt=prompt,
            model=model,
            number_of_images=1,
        )
    except Exception as exc:
        invalid_model_err = "Invalid model name" in str(exc) or "model=" in str(exc)
        if not invalid_model_err:
            raise
        model = "gpt-image-1"
        images = await image_gen.generate_images(
            prompt=prompt,
            model=model,
            number_of_images=1,
        )
    
    normalized_images: list[str] = []
    for item in images or []:
        if item is None:
            continue
        if isinstance(item, str):
            normalized_images.append(item)
            continue
        if isinstance(item, bytes):
            normalized_images.append(
                f"data:image/png;base64,{base64.b64encode(item).decode('ascii')}"
            )
            continue
        if isinstance(item, dict):
            if isinstance(item.get("url"), str) and item.get("url"):
                normalized_images.append(item["url"])
                continue
            b64_val = item.get("b64_json")
            if isinstance(b64_val, str) and b64_val:
                normalized_images.append(f"data:image/png;base64,{b64_val}")
                continue
        normalized_images.append(str(item))

    return {
        "image_url": normalized_images[0] if normalized_images else "",
        "prompt": prompt,
        "model": model,
        "images": normalized_images,
    }


async def _execute_transform_json(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute JSON transformation action using JSONPath."""
    import jsonpath_ng.ext as jp
    
    source_key = config.get("source_key", "data")
    json_path = config.get("json_path", "$")
    output_key = config.get("output_key", "result")
    
    # Get source data from context
    source_data = context.get(source_key, {})
    
    # Parse and apply JSONPath
    parser = jp.parse(json_path)
    matches = parser.find(source_data)
    
    # Extract matched values
    result = [match.value for match in matches]
    
    return {
        output_key: result[0] if len(result) == 1 else result,
        "matched_count": len(result),
    }


async def _execute_filter_array(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute array filter/map/reduce action."""
    source_key = config.get("source_key", "items")
    operation = config.get("operation", "filter")  # filter, map, reduce
    condition = config.get("condition", "")
    output_key = config.get("output_key", "result")
    
    # Get source array from context
    source_array = context.get(source_key, [])
    if not isinstance(source_array, list):
        source_array = [source_array]
    
    result = []
    
    if operation == "filter":
        # Simple condition evaluation
        for item in source_array:
            try:
                # Create local context with item
                local_ctx = {**context, "item": item}
                if bool(_safe_eval_expression(condition, local_ctx, default=False)):
                    result.append(item)
            except Exception:
                pass
    
    elif operation == "map":
        # Transform each item
        transform = config.get("transform", "item")
        for item in source_array:
            try:
                local_ctx = {**context, "item": item}
                transformed = _safe_eval_expression(transform, local_ctx, default=item)
                result.append(transformed)
            except Exception:
                result.append(item)
    
    elif operation == "reduce":
        # Reduce to single value
        accumulator = config.get("initial_value", 0)
        reducer = config.get("reducer", "acc + item")
        for item in source_array:
            try:
                local_ctx = {**context, "acc": accumulator, "item": item}
                accumulator = _safe_eval_expression(reducer, local_ctx, default=accumulator)
            except Exception:
                pass
        result = accumulator
    
    return {
        output_key: result,
        "operation": operation,
        "count": len(result) if isinstance(result, list) else 1,
    }


async def _execute_parse_text(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute text parsing action using regex."""
    import re
    
    source_key = config.get("source_key", "text")
    pattern = config.get("pattern", r".*")
    output_key = config.get("output_key", "matches")
    
    # Get source text from context
    source_text = str(context.get(source_key, ""))
    
    # Apply regex
    matches = re.findall(pattern, source_text)
    
    return {
        output_key: matches[0] if len(matches) == 1 else matches,
        "match_count": len(matches),
        "pattern": pattern,
    }


async def _execute_send_email(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute send email action via centralized v7-guarded email service."""
    from utils.email_service import send_template_email

    to_email = str(config.get("to", "")).format(**context).strip().lower()
    subject = str(config.get("subject", "")).format(**context).strip() or "Workflow Notification"
    body = str(config.get("body", "")).format(**context)
    template_key = str(config.get("template_key") or "workflow_builder_send_email_action_v7").strip().lower()

    if not to_email:
        raise ValueError("send_email action requires non-empty 'to'")

    send_result = await send_template_email(
        recipient_email=to_email,
        template_key=template_key,
        subject=subject,
        data={
            "message": body,
            "workflow_action": "send_email",
            "workflow_channel": "workflow_builder",
        },
    )
    if not bool(send_result.get("success")):
        raise ValueError(str(send_result.get("error") or "workflow send_email failed"))

    return {
        "email_id": str(send_result.get("message_id") or send_result.get("email_id") or ""),
        "to": to_email,
        "subject": subject,
        "template_key": template_key,
        "status": "sent",
    }


async def _execute_condition(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute conditional branching action."""
    condition = config.get("condition", "True")
    then_value = config.get("then", None)
    else_value = config.get("else", None)
    
    try:
        # Evaluate condition
        result = _safe_eval_expression(condition, context, default=False)
        branch_taken = "then" if result else "else"
        output_value = then_value if result else else_value
    except Exception:
        branch_taken = "error"
        output_value = None
        result = False
    
    return {
        "condition_result": bool(result),
        "branch_taken": branch_taken,
        "output": output_value,
    }


async def _execute_loop(config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute loop iteration action."""
    source_key = config.get("source_key", "items")
    max_iterations = config.get("max_iterations", 100)
    
    # Get items to iterate
    items = context.get(source_key, [])
    if not isinstance(items, list):
        items = [items]
    
    iterations = []
    for i, item in enumerate(items[:max_iterations]):
        iterations.append({
            "index": i,
            "item": item,
        })
    
    return {
        "iterations": iterations,
        "total_iterations": len(iterations),
        "items": items,
    }


async def _execute_workflow(workflow: Dict[str, Any], input_data: Dict[str, Any]) -> WorkflowExecution:
    """Execute a complete workflow."""
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    workflow_id = workflow["workflow_id"]
    owner_id = workflow["owner_id"]
    start_time = time.time()
    
    execution = WorkflowExecution(
        execution_id=execution_id,
        workflow_id=workflow_id,
        owner_id=owner_id,
        status="running",
        started_at=_now_iso(),
        trigger_type="manual",
    )
    
    try:
        context = input_data.copy()
        node_results = {}
        
        # Simple sequential execution (no branching yet)
        for node in workflow.get("nodes", []):
            if node["type"] == "trigger":
                continue  # Skip trigger nodes in manual execution
            
            result = await _execute_node(node, context)
            node_results[node["node_id"]] = result
            
            if result.status == "success" and result.output:
                context.update(result.output)
            elif result.status == "failed":
                execution.status = "failed"
                execution.error = result.error
                break
        
        if execution.status == "running":
            execution.status = "completed"
        
        execution.node_results = node_results
        execution.completed_at = _now_iso()
        execution.duration_ms = int((time.time() - start_time) * 1000)
        
    except Exception as e:
        execution.status = "failed"
        execution.error = str(e)
        execution.completed_at = _now_iso()
        execution.duration_ms = int((time.time() - start_time) * 1000)
    
    # Save execution to database
    await db.workflow_executions.insert_one(execution.model_dump(by_alias=True))
    
    return execution


# ── API Endpoints ──


@router.post("", response_model=WorkflowResponse)
async def create_workflow(payload: CreateWorkflowRequest, request: Request):
    """Create a new workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check tier limits
    tier = await _get_user_tier(owner_id)
    limit_check = await _check_workflow_limit(owner_id, tier)
    
    if not limit_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "workflow_limit_reached",
                "message": f"Workflow limit reached ({limit_check['workflow_count']}/{limit_check['workflow_limit']} for {tier} tier). Upgrade to create more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "workflow_count": limit_check["workflow_count"],
                "workflow_limit": limit_check["workflow_limit"],
            },
        )
    
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    
    workflow = {
        "workflow_id": workflow_id,
        "owner_id": owner_id,
        "name": payload.name,
        "description": payload.description,
        "nodes": [node.model_dump(by_alias=True) for node in payload.nodes],
        "edges": [edge.model_dump(by_alias=True) for edge in payload.edges],
        "enabled": payload.enabled,
        "created_at": now,
        "updated_at": now,
        "execution_count": 0,
    }
    
    await db.workflows.insert_one(workflow)
    workflow.pop("_id", None)
    
    return WorkflowResponse(**workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(request: Request, fallback_user_id: Optional[str] = None):
    """List all workflows for the current user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    workflows = await db.workflows.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(100)
    
    return [WorkflowResponse(**wf) for wf in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Get a specific workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return WorkflowResponse(**workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, payload: UpdateWorkflowRequest, request: Request, fallback_user_id: Optional[str] = None):
    """Update an existing workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    update_data = payload.model_dump(exclude_unset=True)
    if "nodes" in update_data:
        update_data["nodes"] = [node.model_dump(by_alias=True) for node in payload.nodes]
    if "edges" in update_data:
        update_data["edges"] = [edge.model_dump(by_alias=True) for edge in payload.edges]
    
    update_data["updated_at"] = _now_iso()
    
    await db.workflows.update_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    updated_workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    return WorkflowResponse(**updated_workflow)


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete a workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.workflows.delete_one({
        "workflow_id": workflow_id,
        "owner_id": owner_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {"success": True, "workflow_id": workflow_id}


@router.post("/{workflow_id}/execute", response_model=WorkflowExecution)
async def execute_workflow(workflow_id: str, payload: ExecuteWorkflowRequest, request: Request):
    """Manually execute a workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check execution limits
    tier = await _get_user_tier(owner_id)
    limit_check = await _check_execution_limit(owner_id, tier)
    
    if not limit_check["can_execute"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "workflow_execution_limit_reached",
                "message": f"Monthly execution limit reached ({limit_check['executions_this_month']}/{limit_check['execution_limit']} for {tier} tier). Upgrade to continue.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "executions_this_month": limit_check["executions_this_month"],
                "execution_limit": limit_check["execution_limit"],
            },
        )
    
    # Get workflow
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if not workflow.get("enabled"):
        raise HTTPException(status_code=400, detail="Workflow is disabled")
    
    # Execute workflow
    execution = await _execute_workflow(workflow, payload.input_data or {})
    
    # Update execution count
    await db.workflows.update_one(
        {"workflow_id": workflow_id},
        {"$inc": {"execution_count": 1}}
    )
    
    return execution


@router.get("/{workflow_id}/executions", response_model=list[WorkflowExecution])
async def get_workflow_executions(
    workflow_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None,
    limit: int = 50
):
    """Get execution history for a workflow."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0, "workflow_id": 1}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    executions = await db.workflow_executions.find(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    return [WorkflowExecution(**ex) for ex in executions]



@router.get("/{workflow_id}/executions/{execution_id}")
async def get_execution_detail(
    workflow_id: str,
    execution_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Get detailed execution information including step-by-step logs."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Fetch execution
    execution = await db.workflow_executions.find_one(
        {"execution_id": execution_id, "workflow_id": workflow_id},
        {"_id": 0}
    )
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    # Calculate detailed metrics
    step_results = execution.get("step_results", [])
    total_steps = len(step_results)
    successful_steps = sum(1 for step in step_results if step.get("status") == "success")
    failed_steps = sum(1 for step in step_results if step.get("status") == "error")
    
    # Calculate duration breakdown per node
    duration_breakdown = {}
    for step in step_results:
        node_id = step.get("node_id")
        duration_ms = step.get("duration_ms", 0)
        duration_breakdown[node_id] = {
            "duration_ms": duration_ms,
            "duration_seconds": round(duration_ms / 1000, 2),
            "status": step.get("status")
        }
    
    # Get workflow info for context
    workflow_info = {
        "workflow_id": workflow.get("workflow_id"),
        "name": workflow.get("name"),
        "description": workflow.get("description")
    }
    
    return {
        "execution": execution,
        "workflow": workflow_info,
        "metrics": {
            "total_steps": total_steps,
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "success_rate": round((successful_steps / total_steps * 100) if total_steps > 0 else 0, 2)
        },
        "duration_breakdown": duration_breakdown,
        "timeline": _build_execution_timeline(step_results)
    }


def _build_execution_timeline(step_results: list) -> list:
    """Build a human-readable execution timeline."""
    timeline = []
    
    for idx, step in enumerate(step_results, 1):
        timeline_entry = {
            "step_number": idx,
            "node_id": step.get("node_id"),
            "node_label": step.get("node_label", step.get("node_id")),
            "status": step.get("status"),
            "executed_at": step.get("executed_at"),
            "duration_ms": step.get("duration_ms"),
            "has_output": bool(step.get("output")),
            "has_error": bool(step.get("error"))
        }
        
        # Add error details if present
        if step.get("error"):
            timeline_entry["error_message"] = step.get("error")
        
        # Add output preview (first 100 chars)
        if step.get("output"):
            output = str(step.get("output"))
            timeline_entry["output_preview"] = output[:100] + "..." if len(output) > 100 else output
        
        timeline.append(timeline_entry)
    
    return timeline


@router.get("/executions/recent")
async def get_recent_executions(
    request: Request,
    fallback_user_id: Optional[str] = None,
    limit: int = 20,
    status: Optional[str] = None
):
    """Get recent executions across all workflows for the user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Build query
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    # Fetch recent executions
    executions = await db.workflow_executions.find(
        query,
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    # Enrich with workflow names
    workflow_ids = list(set(e["workflow_id"] for e in executions))
    workflows = await db.workflows.find(
        {"workflow_id": {"$in": workflow_ids}},
        {"_id": 0, "workflow_id": 1, "name": 1}
    ).to_list(len(workflow_ids))
    
    workflow_map = {w["workflow_id"]: w["name"] for w in workflows}
    
    for execution in executions:
        execution["workflow_name"] = workflow_map.get(execution["workflow_id"], "Unknown")
    
    return {
        "executions": executions,
        "count": len(executions)
    }


@router.delete("/{workflow_id}/executions/{execution_id}")
async def delete_execution(
    workflow_id: str,
    execution_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Delete an execution record."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Delete execution
    result = await db.workflow_executions.delete_one({
        "execution_id": execution_id,
        "workflow_id": workflow_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {
        "execution_id": execution_id,
        "message": "Execution deleted successfully"
    }


@router.post("/{workflow_id}/executions/clear")
async def clear_execution_history(
    workflow_id: str,
    request: Request,
    keep_recent: int = 10,
    fallback_user_id: Optional[str] = None
):
    """Clear old execution history, optionally keeping recent N executions."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify workflow ownership
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if keep_recent > 0:
        # Find most recent N executions to keep
        recent_executions = await db.workflow_executions.find(
            {"workflow_id": workflow_id},
            {"_id": 0, "execution_id": 1}
        ).sort("started_at", -1).limit(keep_recent).to_list(keep_recent)
        
        recent_ids = [e["execution_id"] for e in recent_executions]
        
        # Delete all except recent
        result = await db.workflow_executions.delete_many({
            "workflow_id": workflow_id,
            "execution_id": {"$nin": recent_ids}
        })
    else:
        # Delete all
        result = await db.workflow_executions.delete_many({
            "workflow_id": workflow_id
        })
    
    return {
        "workflow_id": workflow_id,
        "deleted_count": result.deleted_count,
        "kept_recent": keep_recent,
        "message": f"Cleared {result.deleted_count} execution(s), kept {keep_recent} most recent"
    }



@router.get("/usage/stats", response_model=WorkflowUsageResponse)
async def get_workflow_usage(request: Request, fallback_user_id: Optional[str] = None):
    """Get workflow usage statistics for tier enforcement."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    tier = await _get_user_tier(owner_id)
    workflow_check = await _check_workflow_limit(owner_id, tier)
    execution_check = await _check_execution_limit(owner_id, tier)
    
    return WorkflowUsageResponse(
        workflow_count=workflow_check["workflow_count"],
        workflow_limit=workflow_check["workflow_limit"],
        executions_this_month=execution_check["executions_this_month"],
        execution_limit=execution_check["execution_limit"],
        can_create_workflow=workflow_check["can_create"],
        can_execute=execution_check["can_execute"],
        tier=tier,
        limit_reached=not workflow_check["can_create"]
    )


# ── Workflow Analytics ──

@router.get("/analytics/overview")
async def get_workflow_analytics(
    request: Request,
    fallback_user_id: Optional[str] = None,
    days: int = 30
):
    """Get workflow analytics and performance metrics."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    from datetime import timedelta
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Get all workflows
    workflows = await db.workflows.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(1000)
    
    # Get executions in date range
    executions = await db.workflow_executions.find(
        {
            "owner_id": owner_id,
            "started_at": {"$gte": start_date.isoformat()}
        },
        {"_id": 0}
    ).to_list(10000)
    
    # Calculate metrics
    total_workflows = len(workflows)
    total_executions = len(executions)
    successful_executions = sum(1 for e in executions if e.get("status") == "completed")
    failed_executions = sum(1 for e in executions if e.get("status") == "failed")
    
    success_rate = round((successful_executions / total_executions * 100) if total_executions > 0 else 0, 2)
    
    # Calculate average execution time
    completed_executions = [e for e in executions if e.get("status") == "completed" and e.get("duration_ms")]
    avg_duration_ms = sum(e.get("duration_ms", 0) for e in completed_executions) / len(completed_executions) if completed_executions else 0
    
    # Most used workflows
    workflow_execution_counts = {}
    for execution in executions:
        wf_id = execution.get("workflow_id")
        workflow_execution_counts[wf_id] = workflow_execution_counts.get(wf_id, 0) + 1
    
    most_used_workflows = []
    for wf_id, count in sorted(workflow_execution_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        wf = next((w for w in workflows if w.get("workflow_id") == wf_id), None)
        if wf:
            most_used_workflows.append({
                "workflow_id": wf_id,
                "name": wf.get("name"),
                "execution_count": count
            })
    
    # Node type usage statistics
    node_type_usage = {}
    for execution in executions:
        for step in execution.get("step_results", []):
            action = step.get("action", "unknown")
            node_type_usage[action] = node_type_usage.get(action, 0) + 1
    
    # Execution trend (daily)
    daily_executions = {}
    for execution in executions:
        started_at = execution.get("started_at", "")
        if started_at:
            date_key = started_at[:10]  # YYYY-MM-DD
            if date_key not in daily_executions:
                daily_executions[date_key] = {"total": 0, "successful": 0, "failed": 0}
            daily_executions[date_key]["total"] += 1
            if execution.get("status") == "completed":
                daily_executions[date_key]["successful"] += 1
            elif execution.get("status") == "failed":
                daily_executions[date_key]["failed"] += 1
    
    # Recent failures
    recent_failures = [
        {
            "execution_id": e.get("execution_id"),
            "workflow_id": e.get("workflow_id"),
            "workflow_name": next((w.get("name") for w in workflows if w.get("workflow_id") == e.get("workflow_id")), "Unknown"),
            "error": e.get("error", "Unknown error"),
            "started_at": e.get("started_at")
        }
        for e in executions 
        if e.get("status") == "failed"
    ][:10]
    
    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "total_workflows": total_workflows,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": success_rate,
            "average_duration_ms": round(avg_duration_ms, 2),
            "average_duration_seconds": round(avg_duration_ms / 1000, 2)
        },
        "most_used_workflows": most_used_workflows,
        "node_type_usage": node_type_usage,
        "daily_trend": daily_executions,
        "recent_failures": recent_failures
    }




# ── Import/Export Workflows ──

@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Export workflow as JSON for backup or sharing."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get workflow
    workflow = await db.workflows.find_one(
        {"workflow_id": workflow_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Prepare export data
    export_data = {
        "export_version": "1.0",
        "exported_at": _now_iso(),
        "workflow": {
            "name": workflow.get("name"),
            "description": workflow.get("description"),
            "nodes": workflow.get("nodes", []),
            "edges": workflow.get("edges", []),
            "tier_requirement": workflow.get("tier_requirement", "free"),
            "enabled": workflow.get("enabled", False)
        },
        "metadata": {
            "original_workflow_id": workflow_id,
            "execution_count": workflow.get("execution_count", 0),
            "created_at": workflow.get("created_at")
        }
    }
    
    return export_data


@router.post("/import")
async def import_workflow(
    request: Request,
    workflow_data: Dict[str, Any],
    custom_name: Optional[str] = None,
    fallback_user_id: Optional[str] = None
):
    """Import workflow from exported JSON."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Validate import data
    if "workflow" not in workflow_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid import format: missing 'workflow' field"
        )
    
    workflow_def = workflow_data["workflow"]
    
    # Validate required fields
    if not workflow_def.get("name"):
        raise HTTPException(
            status_code=400,
            detail="Invalid workflow: missing 'name' field"
        )
    
    if not isinstance(workflow_def.get("nodes"), list):
        raise HTTPException(
            status_code=400,
            detail="Invalid workflow: 'nodes' must be an array"
        )
    
    # Check tier access
    tier_requirement = workflow_def.get("tier_requirement", "free")
    user_tier = await _get_user_tier(owner_id)
    
    if not _has_tier_access(user_tier, tier_requirement):
        raise HTTPException(
            status_code=403,
            detail=f"This workflow requires {tier_requirement} tier or higher"
        )
    
    # Check workflow limit
    limit_check = await _check_workflow_limit(owner_id, user_tier)
    if not limit_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "workflow_limit_reached",
                "message": f"Workflow limit reached ({limit_check['workflow_count']}/{limit_check['workflow_limit']} for {user_tier} tier)",
                "upgrade_prompt": True,
            },
        )
    
    # Create new workflow
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    workflow_name = custom_name or workflow_def.get("name")
    
    new_workflow = {
        "workflow_id": workflow_id,
        "name": workflow_name,
        "description": workflow_def.get("description", ""),
        "owner_id": owner_id,
        "enabled": False,  # Always start disabled for safety
        "nodes": workflow_def.get("nodes", []),
        "edges": workflow_def.get("edges", []),
        "tier_requirement": tier_requirement,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "execution_count": 0,
        "imported_from": workflow_data.get("metadata", {}).get("original_workflow_id")
    }
    
    await db.workflows.insert_one(new_workflow)
    
    return {
        "workflow_id": workflow_id,
        "name": workflow_name,
        "description": new_workflow["description"],
        "nodes": len(new_workflow["nodes"]),
        "message": f"Workflow imported successfully: {workflow_name}"
    }


@router.post("/export/batch")
async def export_workflows_batch(
    request: Request,
    workflow_ids: list[str] = None,
    fallback_user_id: Optional[str] = None
):
    """Export multiple workflows as a single JSON bundle."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # If no IDs provided, export all workflows
    query = {"owner_id": owner_id}
    if workflow_ids:
        query["workflow_id"] = {"$in": workflow_ids}
    
    workflows = await db.workflows.find(query, {"_id": 0}).to_list(1000)
    
    if not workflows:
        raise HTTPException(status_code=404, detail="No workflows found to export")
    
    # Prepare bundle
    export_bundle = {
        "export_version": "1.0",
        "export_type": "bundle",
        "exported_at": _now_iso(),
        "workflow_count": len(workflows),
        "workflows": [
            {
                "name": wf.get("name"),
                "description": wf.get("description"),
                "nodes": wf.get("nodes", []),
                "edges": wf.get("edges", []),
                "tier_requirement": wf.get("tier_requirement", "free"),
                "metadata": {
                    "original_workflow_id": wf.get("workflow_id"),
                    "execution_count": wf.get("execution_count", 0)
                }
            }
            for wf in workflows
        ]
    }
    
    return export_bundle
