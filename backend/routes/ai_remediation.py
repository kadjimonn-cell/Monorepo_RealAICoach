"""Advanced AI Auto-Remediation — GPT-4o multi-step incident analysis and execution.

Admin-only. Analyzes system failures, generates multi-step fix plans, executes them.

Endpoints:
- POST /api/admin/ai-remediation/analyze   — Analyze an incident with AI
- POST /api/admin/ai-remediation/execute    — Execute a remediation plan
- GET  /api/admin/ai-remediation/history    — Remediation history
- GET  /api/admin/ai-remediation/dashboard  — Dashboard with stats
"""

import os
import uuid
import logging
import psutil
import shlex
import subprocess
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/ai-remediation", tags=["AI Auto-Remediation"])

_BLOCKED_COMMAND_TOKENS = [";", "&&", "||", "|", "`", "$(", ">", "<"]


def _run_safe_command(command: str, timeout_seconds: int) -> subprocess.CompletedProcess:
    if not command or not isinstance(command, str):
        raise ValueError("Missing command")

    for token in _BLOCKED_COMMAND_TOKENS:
        if token in command:
            raise ValueError(f"Blocked unsafe token in command: {token}")

    argv = shlex.split(command)
    if not argv:
        raise ValueError("Empty command after parsing")

    return subprocess.run(
        argv,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


class IncidentReport(BaseModel):
    title: str
    description: str
    severity: str = "medium"  # critical, high, medium, low
    affected_services: list = []
    error_logs: Optional[str] = None


class ExecutePlan(BaseModel):
    remediation_id: str
    steps_to_execute: list = []  # list of step indices to execute, empty = all


async def _collect_system_state() -> dict:
    """Collect current system state for AI context."""
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()

    # Recent errors from DB
    recent_errors = await db.error_logs.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(5).to_list(5)
    for e in recent_errors:
        if hasattr(e.get("timestamp"), "isoformat"):
            e["timestamp"] = e["timestamp"].isoformat()

    # Recent security events
    recent_threats = await db.security_events.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(5).to_list(5)
    for t in recent_threats:
        if hasattr(t.get("timestamp"), "isoformat"):
            t["timestamp"] = t["timestamp"].isoformat()

    # Repair history
    recent_repairs = await db.repair_history.find(
        {}, {"_id": 0}
    ).sort("started_at", -1).limit(3).to_list(3)
    for r in recent_repairs:
        for k in ["started_at", "completed_at"]:
            if hasattr(r.get(k), "isoformat"):
                r[k] = r[k].isoformat()

    return {
        "cpu_percent": cpu,
        "memory_percent": round(mem.percent, 1),
        "recent_errors": recent_errors,
        "recent_threats": recent_threats,
        "recent_repairs": recent_repairs,
    }


@router.post("/analyze")
async def analyze_incident(request: Request, incident: IncidentReport):
    """AI analyzes an incident and generates a multi-step remediation plan."""
    system_state = await _collect_system_state()
    remediation_id = f"rem_{uuid.uuid4().hex[:12]}"

    prompt = f"""You are a senior Site Reliability Engineer. Analyze this production incident and create a detailed multi-step remediation plan.

## Incident
- Title: {incident.title}
- Description: {incident.description}
- Severity: {incident.severity}
- Affected Services: {', '.join(incident.affected_services) or 'unknown'}
{f'- Error Logs: {incident.error_logs[:500]}' if incident.error_logs else ''}

## Current System State
- CPU: {system_state['cpu_percent']}%
- Memory: {system_state['memory_percent']}%
- Recent errors: {len(system_state['recent_errors'])}
- Recent security events: {len(system_state['recent_threats'])}

Provide your response as JSON:
{{
  "root_cause": "Brief root cause analysis",
  "impact_assessment": "Who/what is affected and how",
  "risk_level": "critical|high|medium|low",
  "steps": [
    {{
      "order": 1,
      "action": "Step title",
      "description": "What to do",
      "type": "automated|manual|verification",
      "estimated_duration_min": 5,
      "rollback_possible": true,
      "command": "optional CLI command or null"
    }}
  ],
  "estimated_total_duration_min": 30,
  "prevention_measures": ["Future prevention tips"]
}}

Return ONLY valid JSON."""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import asyncio as _asyncio
        emergent_key = os.environ.get("EMERGENT_LLM_KEY")

        chat = LlmChat(
            api_key=emergent_key,
            session_id=f"rem-{uuid.uuid4().hex[:8]}",
            system_message="You are a senior Site Reliability Engineer. Return only valid JSON.",
        ).with_model("openai", "gpt-4o")
        # 15s ceiling — upstream LLM 502s must not stall the incident loop
        response = await _asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)),
            timeout=15.0,
        )

        import json
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        plan = json.loads(text)

    except Exception as e:
        logger.error(f"AI remediation analysis failed: {e}")
        plan = {
            "root_cause": "Unable to determine — AI analysis unavailable",
            "impact_assessment": incident.description,
            "risk_level": incident.severity,
            "steps": [
                {"order": 1, "action": "Check service health", "description": "Verify all backend services are running", "type": "verification", "estimated_duration_min": 2, "rollback_possible": False, "command": "sudo supervisorctl status"},
                {"order": 2, "action": "Check error logs", "description": "Review recent backend error logs", "type": "verification", "estimated_duration_min": 3, "rollback_possible": False, "command": "tail -100 /var/log/supervisor/backend.err.log"},
                {"order": 3, "action": "Restart affected service", "description": "Restart the backend service", "type": "automated", "estimated_duration_min": 1, "rollback_possible": True, "command": "sudo supervisorctl restart backend"},
                {"order": 4, "action": "Verify recovery", "description": "Confirm the service is healthy", "type": "verification", "estimated_duration_min": 2, "rollback_possible": False, "command": "curl -s http://127.0.0.1:8001/api/health"},
            ],
            "estimated_total_duration_min": 10,
            "prevention_measures": ["Set up automated monitoring", "Add circuit breakers"],
        }

    # Store the remediation plan
    doc = {
        "remediation_id": remediation_id,
        "incident": {
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "affected_services": incident.affected_services,
        },
        "plan": plan,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "executed_steps": [],
    }
    await db.ai_remediations.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/execute")
async def execute_remediation(request: Request, body: ExecutePlan):
    """Execute steps from a remediation plan."""
    rem = await db.ai_remediations.find_one(
        {"remediation_id": body.remediation_id}, {"_id": 0}
    )
    if not rem:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Remediation plan not found"}, status_code=404)

    steps = rem.get("plan", {}).get("steps", [])
    indices = body.steps_to_execute if body.steps_to_execute else list(range(len(steps)))
    executed = []

    for idx in indices:
        if idx >= len(steps):
            continue
        step = steps[idx]
        result = {"step_order": step.get("order", idx + 1), "action": step["action"], "started_at": datetime.now(timezone.utc).isoformat()}

        if step.get("type") == "automated" and step.get("command"):
            # Execute automated commands safely
            try:
                proc = _run_safe_command(step["command"], timeout_seconds=30)
                result["status"] = "success" if proc.returncode == 0 else "failed"
                result["output"] = proc.stdout[:500] if proc.stdout else proc.stderr[:500]
                result["exit_code"] = proc.returncode
            except subprocess.TimeoutExpired:
                result["status"] = "timeout"
                result["output"] = "Command timed out after 30s"
            except Exception as e:
                result["status"] = "error"
                result["output"] = str(e)
        elif step.get("type") == "verification" and step.get("command"):
            try:
                proc = _run_safe_command(step["command"], timeout_seconds=15)
                result["status"] = "verified" if proc.returncode == 0 else "failed"
                result["output"] = proc.stdout[:500] if proc.stdout else proc.stderr[:500]
            except Exception as e:
                result["status"] = "error"
                result["output"] = str(e)
        else:
            result["status"] = "manual_required"
            result["output"] = f"Manual step: {step['description']}"

        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        executed.append(result)

    # Update the remediation record
    all_success = all(r["status"] in ("success", "verified", "manual_required") for r in executed)
    new_status = "completed" if all_success else "partial"

    await db.ai_remediations.update_one(
        {"remediation_id": body.remediation_id},
        {"$set": {"status": new_status, "executed_steps": executed, "executed_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {
        "remediation_id": body.remediation_id,
        "status": new_status,
        "executed_steps": executed,
        "total_steps": len(steps),
        "executed_count": len(executed),
    }


@router.get("/history")
async def remediation_history(request: Request, limit: int = 20):
    """Get remediation history."""
    docs = await db.ai_remediations.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"remediations": docs, "count": len(docs)}


@router.get("/dashboard")
async def remediation_dashboard(request: Request):
    """Dashboard with remediation stats."""
    total = await db.ai_remediations.count_documents({})
    completed = await db.ai_remediations.count_documents({"status": "completed"})
    partial = await db.ai_remediations.count_documents({"status": "partial"})
    pending = await db.ai_remediations.count_documents({"status": "pending"})

    # Recent remediations
    recent = await db.ai_remediations.find(
        {}, {"_id": 0, "plan": 0, "executed_steps": 0}
    ).sort("created_at", -1).limit(5).to_list(5)

    # Severity breakdown
    pipeline = [
        {"$group": {"_id": "$incident.severity", "count": {"$sum": 1}}}
    ]
    severity_counts = {}
    async for doc in db.ai_remediations.aggregate(pipeline):
        severity_counts[doc["_id"]] = doc["count"]

    return {
        "total_remediations": total,
        "completed": completed,
        "partial": partial,
        "pending": pending,
        "success_rate": round((completed / total * 100) if total > 0 else 0, 1),
        "severity_breakdown": severity_counts,
        "recent": recent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
