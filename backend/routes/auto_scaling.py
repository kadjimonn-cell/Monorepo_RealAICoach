"""Auto-Scaling Engine — AI-Powered dynamic scaling with GPT-4o analysis.

API:
- GET  /api/admin/scaling/status       — Current scaling status + metrics
- GET  /api/admin/scaling/rules        — List scaling rules
- POST /api/admin/scaling/rules        — Create scaling rule
- PUT  /api/admin/scaling/rules/{id}   — Update scaling rule
- DELETE /api/admin/scaling/rules/{id} — Delete scaling rule
- POST /api/admin/scaling/trigger      — Manually trigger scaling
- GET  /api/admin/scaling/history      — Scaling event history
- POST /api/admin/scaling/ai-analyze   — On-demand AI scaling analysis
"""

import os
import json
import uuid
import asyncio
import logging
import psutil
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

from routes.db import db, get_current_user

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

AI_SYSTEM_PROMPT = """You are an expert infrastructure auto-scaling advisor for a production SaaS platform.
You analyze real-time system metrics and scaling rules to make intelligent scaling decisions.

RESPOND ONLY with valid JSON in this exact format:
{
  "decision": "scale_up" | "scale_down" | "no_action",
  "confidence": 0.0-1.0,
  "amount": <integer, number of instances to add/remove, 0 if no_action>,
  "reasoning": "<2-3 sentence explanation of your decision>",
  "risk_level": "low" | "medium" | "high",
  "predicted_trend": "increasing" | "stable" | "decreasing",
  "recommendation": "<brief actionable recommendation for the ops team>"
}

Decision guidelines:
- Consider CPU, memory, disk usage holistically - not just individual thresholds
- Factor in the number of active sessions and request patterns
- Be conservative: prefer stability over aggressive scaling
- Scale up proactively if metrics show upward trend approaching thresholds
- Scale down only when metrics are consistently low and stable
- Never scale below min_instances or above max_instances
- Consider cooldown: if recent scaling happened, prefer no_action unless critical"""


class ScalingRule(BaseModel):
    name: str
    metric: str
    threshold_up: float
    threshold_down: float
    scale_up_by: int = 1
    scale_down_by: int = 1
    cooldown_seconds: int = 300
    enabled: bool = True


class UpdateScalingRule(BaseModel):
    name: Optional[str] = None
    threshold_up: Optional[float] = None
    threshold_down: Optional[float] = None
    scale_up_by: Optional[int] = None
    scale_down_by: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    enabled: Optional[bool] = None


class ManualScale(BaseModel):
    action: str
    amount: int = 1
    reason: Optional[str] = None


def _collect_metrics() -> dict:
    """Collect real system metrics via psutil."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    load = os.getloadavg()
    return {
        "cpu_percent": round(cpu, 1),
        "memory_percent": round(mem.percent, 1),
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "network_sent_gb": round(net.bytes_sent / (1024**3), 3),
        "network_recv_gb": round(net.bytes_recv / (1024**3), 3),
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "load_15m": round(load[2], 2),
        "process_count": len(psutil.pids()),
    }


async def _ai_scaling_analysis(metrics: dict, state: dict, rules: list, recent_events: list) -> dict:
    """Call GPT-4o to analyze metrics and return a scaling decision."""
    prompt = f"""Analyze these real-time infrastructure metrics and decide on scaling:

## Current System Metrics (REAL from psutil)
- CPU: {metrics["cpu_percent"]}%
- Memory: {metrics["memory_percent"]}% ({metrics["memory_used_gb"]}/{metrics["memory_total_gb"]} GB)
- Disk: {metrics["disk_percent"]}% ({metrics["disk_used_gb"]}/{metrics["disk_total_gb"]} GB)
- Load Average (1m/5m/15m): {metrics["load_1m"]}/{metrics["load_5m"]}/{metrics["load_15m"]}
- Active Processes: {metrics["process_count"]}
- Network Sent: {metrics["network_sent_gb"]} GB, Received: {metrics["network_recv_gb"]} GB

## Current Scaling State
- Running Instances: {state.get("current_instances", 1)}
- Desired Instances: {state.get("desired_instances", 1)}
- Min Instances: {state.get("min_instances", 1)}
- Max Instances: {state.get("max_instances", 20)}

## Active Scaling Rules
{json.dumps(rules, indent=2) if rules else "No rules configured"}

## Recent Scaling Events (last hour)
{json.dumps(recent_events[-5:], indent=2) if recent_events else "No recent events"}

Based on all this data, what scaling action should be taken right now?"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"scaling-{uuid.uuid4().hex[:8]}",
            system_message=AI_SYSTEM_PROMPT,
        ).with_model("openai", "gpt-4o")

        # Hard ceiling so upstream LLM 502/backoff doesn't stall the scheduler event loop
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)),
            timeout=15.0,
        )

        # Parse JSON from response
        resp_text = response.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(resp_text)

        # Validate required fields
        for field in ["decision", "confidence", "amount", "reasoning"]:
            if field not in result:
                raise ValueError(f"Missing field: {field}")

        result.setdefault("risk_level", "low")
        result.setdefault("predicted_trend", "stable")
        result.setdefault("recommendation", "")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"AI response not valid JSON: {e}")
        return {
            "decision": "no_action",
            "confidence": 0.0,
            "amount": 0,
            "reasoning": f"AI response parsing failed: {e}",
            "risk_level": "low",
            "predicted_trend": "stable",
            "recommendation": "Falling back to rule-based evaluation",
        }
    except asyncio.TimeoutError:
        logger.warning("AI scaling analysis timed out after 15s — falling back to rule-based")
        return {
            "decision": "no_action",
            "confidence": 0.0,
            "amount": 0,
            "reasoning": "AI timeout — upstream LLM unavailable",
            "risk_level": "low",
            "predicted_trend": "stable",
            "recommendation": "Falling back to rule-based evaluation",
        }
    except Exception as e:
        logger.error(f"AI scaling analysis error: {e}")
        return {
            "decision": "no_action",
            "confidence": 0.0,
            "amount": 0,
            "reasoning": f"AI analysis unavailable: {str(e)[:100]}",
            "risk_level": "low",
            "predicted_trend": "stable",
            "recommendation": "Check LLM API key and connectivity",
        }


@router.get("/admin/scaling/status")
async def scaling_status(request: Request):
    """Current scaling status with real-time metrics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    metrics = _collect_metrics()

    state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0})
    if not state:
        state = {
            "type": "global",
            "current_instances": 1,
            "min_instances": 1,
            "max_instances": 20,
            "desired_instances": 1,
        }
        await db.scaling_state.insert_one(state)
        state.pop("_id", None)

    now = datetime.now(timezone.utc)
    one_hour = (now - timedelta(hours=1)).isoformat()
    recent_events = (
        await db.scaling_events.find({"timestamp": {"$gte": one_hour}}, {"_id": 0}).sort("timestamp", -1).to_list(10)
    )

    active_sessions = await db.user_sessions.count_documents({})
    rules_active = await db.scaling_rules.count_documents({"enabled": True})

    # Get last AI analysis
    last_analysis = await db.ai_scaling_analyses.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])

    return {
        "instances": {
            "current": state.get("current_instances", 1),
            "desired": state.get("desired_instances", 1),
            "min": state.get("min_instances", 1),
            "max": state.get("max_instances", 20),
        },
        "metrics": {
            "cpu_pct": metrics["cpu_percent"],
            "memory_pct": metrics["memory_percent"],
            "memory_used_gb": metrics["memory_used_gb"],
            "memory_total_gb": metrics["memory_total_gb"],
            "disk_pct": metrics["disk_percent"],
            "active_sessions": active_sessions,
            "load_1m": metrics["load_1m"],
            "load_5m": metrics["load_5m"],
            "process_count": metrics["process_count"],
        },
        "recent_events": recent_events,
        "scaling_mode": "ai-powered",
        "rules_active": rules_active,
        "last_ai_analysis": last_analysis,
    }


@router.get("/admin/scaling/rules")
async def list_rules(request: Request):
    """List all scaling rules."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")
    rules = await db.scaling_rules.find({}, {"_id": 0}).to_list(50)
    if not rules:
        defaults = [
            {
                "rule_id": f"rule_{uuid.uuid4().hex[:8]}",
                "name": "CPU High",
                "metric": "cpu",
                "threshold_up": 75,
                "threshold_down": 30,
                "scale_up_by": 2,
                "scale_down_by": 1,
                "cooldown_seconds": 300,
                "enabled": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "rule_id": f"rule_{uuid.uuid4().hex[:8]}",
                "name": "Memory Pressure",
                "metric": "memory",
                "threshold_up": 85,
                "threshold_down": 40,
                "scale_up_by": 1,
                "scale_down_by": 1,
                "cooldown_seconds": 300,
                "enabled": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "rule_id": f"rule_{uuid.uuid4().hex[:8]}",
                "name": "High Load",
                "metric": "load",
                "threshold_up": 4.0,
                "threshold_down": 0.5,
                "scale_up_by": 2,
                "scale_down_by": 1,
                "cooldown_seconds": 300,
                "enabled": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await db.scaling_rules.insert_many(defaults)
        for d in defaults:
            d.pop("_id", None)
        rules = defaults
    return {"rules": rules}


@router.post("/admin/scaling/rules")
async def create_rule(request: Request, body: ScalingRule):
    """Create a new scaling rule."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")
    rule = {
        "rule_id": f"rule_{uuid.uuid4().hex[:8]}",
        **body.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.scaling_rules.insert_one(rule)
    rule.pop("_id", None)
    return {"message": "Rule created", "rule": rule}


@router.put("/admin/scaling/rules/{rule_id}")
async def update_rule(request: Request, rule_id: str, body: UpdateScalingRule):
    """Update a scaling rule."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No updates")
    result = await db.scaling_rules.update_one({"rule_id": rule_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Rule not found")
    return {"message": "Rule updated"}


@router.delete("/admin/scaling/rules/{rule_id}")
async def delete_rule(request: Request, rule_id: str):
    """Delete a scaling rule."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")
    result = await db.scaling_rules.delete_one({"rule_id": rule_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Rule not found")
    return {"message": "Rule deleted"}


@router.post("/admin/scaling/trigger")
async def manual_scale(request: Request, body: ManualScale):
    """Manually trigger scaling."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0})
    if not state:
        state = {
            "type": "global",
            "current_instances": 1,
            "min_instances": 1,
            "max_instances": 20,
            "desired_instances": 1,
        }

    current = state.get("current_instances", 1)
    if body.action == "scale_up":
        new_count = min(current + body.amount, state.get("max_instances", 20))
    else:
        new_count = max(current - body.amount, state.get("min_instances", 1))

    now = datetime.now(timezone.utc).isoformat()
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "action": body.action,
        "trigger": "manual",
        "from_instances": current,
        "to_instances": new_count,
        "reason": body.reason or f"Manual {body.action} by admin",
        "triggered_by": user.user_id,
        "status": "completed",
        "timestamp": now,
    }
    await db.scaling_events.insert_one(event)
    event.pop("_id", None)

    await db.scaling_state.update_one(
        {"type": "global"},
        {"$set": {"current_instances": new_count, "desired_instances": new_count, "updated_at": now}},
        upsert=True,
    )
    logger.info(f"Manual scale: {current} -> {new_count} ({body.action})")
    return {"message": f"Scaled from {current} to {new_count}", "event": event}


@router.get("/admin/scaling/history")
async def scaling_history(request: Request, limit: int = 30):
    """Get scaling event history."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    events = await db.scaling_events.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0})

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    events_24h = await db.scaling_events.count_documents({"timestamp": {"$gte": day_ago}})
    events_7d = await db.scaling_events.count_documents({"timestamp": {"$gte": week_ago}})
    scale_ups = await db.scaling_events.count_documents({"action": "scale_up", "timestamp": {"$gte": week_ago}})
    scale_downs = await db.scaling_events.count_documents({"action": "scale_down", "timestamp": {"$gte": week_ago}})

    return {
        "events": events,
        "state": state or {},
        "stats": {
            "events_24h": events_24h,
            "events_7d": events_7d,
            "scale_ups_7d": scale_ups,
            "scale_downs_7d": scale_downs,
        },
    }


@router.get("/admin/scaling/ai-history")
async def ai_scaling_history(request: Request, limit: int = 50):
    """Get AI scaling analysis history with metrics snapshots for timeline visualization."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    analyses = await db.ai_scaling_analyses.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)

    # Build timeline data points
    timeline = []
    for a in reversed(analyses):
        m = a.get("metrics_snapshot", {})
        d = a.get("ai_decision", {})
        s = a.get("state_snapshot", {})
        timeline.append(
            {
                "timestamp": a.get("timestamp", ""),
                "cpu": m.get("cpu_percent", 0),
                "memory": m.get("memory_percent", 0),
                "disk": m.get("disk_percent", 0),
                "load_1m": m.get("load_1m", 0),
                "processes": m.get("process_count", 0),
                "instances": s.get("current_instances", 1),
                "decision": d.get("decision", "no_action"),
                "confidence": d.get("confidence", 0),
                "risk_level": d.get("risk_level", "low"),
                "predicted_trend": d.get("predicted_trend", "stable"),
                "amount": d.get("amount", 0),
                "reasoning": d.get("reasoning", ""),
                "recommendation": d.get("recommendation", ""),
                "triggered_by": a.get("triggered_by", ""),
            }
        )

    # Summary stats
    total = len(analyses)
    scale_ups = sum(1 for a in analyses if a.get("ai_decision", {}).get("decision") == "scale_up")
    scale_downs = sum(1 for a in analyses if a.get("ai_decision", {}).get("decision") == "scale_down")
    holds = total - scale_ups - scale_downs
    avg_confidence = round(sum(a.get("ai_decision", {}).get("confidence", 0) for a in analyses) / max(total, 1), 2)

    return {
        "timeline": timeline,
        "summary": {
            "total_analyses": total,
            "scale_ups": scale_ups,
            "scale_downs": scale_downs,
            "holds": holds,
            "avg_confidence": avg_confidence,
        },
    }


@router.post("/admin/scaling/ai-analyze")
async def ai_analyze(request: Request):
    """On-demand AI scaling analysis — sends real metrics to GPT-4o."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    metrics = _collect_metrics()
    state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0}) or {
        "current_instances": 1,
        "min_instances": 1,
        "max_instances": 20,
        "desired_instances": 1,
    }
    rules = await db.scaling_rules.find({"enabled": True}, {"_id": 0}).to_list(50)
    now = datetime.now(timezone.utc)
    one_hour = (now - timedelta(hours=1)).isoformat()
    recent = (
        await db.scaling_events.find({"timestamp": {"$gte": one_hour}}, {"_id": 0}).sort("timestamp", -1).to_list(5)
    )

    analysis = await _ai_scaling_analysis(metrics, state, rules, recent)

    # Store the analysis
    record = {
        "analysis_id": f"ai_{uuid.uuid4().hex[:10]}",
        "metrics_snapshot": metrics,
        "state_snapshot": {
            "current_instances": state.get("current_instances", 1),
            "min_instances": state.get("min_instances", 1),
            "max_instances": state.get("max_instances", 20),
        },
        "ai_decision": analysis,
        "triggered_by": user.user_id,
        "timestamp": now.isoformat(),
    }
    await db.ai_scaling_analyses.insert_one(record)
    record.pop("_id", None)

    # Execute the scaling decision if AI is confident enough
    executed = False
    if analysis["decision"] != "no_action" and analysis["confidence"] >= 0.6 and analysis["amount"] > 0:
        current = state.get("current_instances", 1)
        if analysis["decision"] == "scale_up":
            new_count = min(current + analysis["amount"], state.get("max_instances", 20))
        else:
            new_count = max(current - analysis["amount"], state.get("min_instances", 1))

        if new_count != current:
            event = {
                "event_id": f"evt_{uuid.uuid4().hex[:10]}",
                "action": analysis["decision"],
                "trigger": "ai",
                "from_instances": current,
                "to_instances": new_count,
                "reason": f"AI ({analysis['confidence']:.0%} confidence): {analysis['reasoning']}",
                "ai_analysis_id": record["analysis_id"],
                "risk_level": analysis.get("risk_level", "low"),
                "triggered_by": "gpt-4o",
                "status": "completed",
                "timestamp": now.isoformat(),
            }
            await db.scaling_events.insert_one(event)
            event.pop("_id", None)
            await db.scaling_state.update_one(
                {"type": "global"},
                {
                    "$set": {
                        "current_instances": new_count,
                        "desired_instances": new_count,
                        "updated_at": now.isoformat(),
                    }
                },
                upsert=True,
            )
            executed = True
            logger.info(
                f"AI scaling: {analysis['decision']} {current} -> {new_count} (confidence: {analysis['confidence']:.0%})"
            )
            record["executed_event"] = event

    record["action_executed"] = executed
    return record


# ── AI-Powered Automatic Scaling Evaluation (Background Job) ──


async def evaluate_scaling_rules():
    """Background task: AI-powered evaluation of scaling needs using GPT-4o."""
    try:
        metrics = _collect_metrics()

        state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0})
        if not state:
            state = {
                "type": "global",
                "current_instances": 1,
                "min_instances": 1,
                "max_instances": 20,
                "desired_instances": 1,
            }
            await db.scaling_state.insert_one(state)
            state.pop("_id", None)

        rules = await db.scaling_rules.find({"enabled": True}, {"_id": 0}).to_list(50)
        now = datetime.now(timezone.utc)
        one_hour = (now - timedelta(hours=1)).isoformat()
        recent = (
            await db.scaling_events.find({"timestamp": {"$gte": one_hour}}, {"_id": 0}).sort("timestamp", -1).to_list(5)
        )

        analysis = await _ai_scaling_analysis(metrics, state, rules, recent)

        # Store analysis
        record = {
            "analysis_id": f"ai_{uuid.uuid4().hex[:10]}",
            "metrics_snapshot": metrics,
            "state_snapshot": {
                "current_instances": state.get("current_instances", 1),
                "min_instances": state.get("min_instances", 1),
                "max_instances": state.get("max_instances", 20),
            },
            "ai_decision": analysis,
            "triggered_by": "background_job",
            "timestamp": now.isoformat(),
        }
        await db.ai_scaling_analyses.insert_one(record)
        record.pop("_id", None)

        # Execute if confident
        if analysis["decision"] != "no_action" and analysis["confidence"] >= 0.7 and analysis["amount"] > 0:
            current = state.get("current_instances", 1)
            if analysis["decision"] == "scale_up":
                new_count = min(current + analysis["amount"], state.get("max_instances", 20))
            else:
                new_count = max(current - analysis["amount"], state.get("min_instances", 1))

            if new_count != current:
                event = {
                    "event_id": f"evt_{uuid.uuid4().hex[:10]}",
                    "action": analysis["decision"],
                    "trigger": "ai",
                    "from_instances": current,
                    "to_instances": new_count,
                    "reason": f"AI auto ({analysis['confidence']:.0%}): {analysis['reasoning']}",
                    "ai_analysis_id": record["analysis_id"],
                    "risk_level": analysis.get("risk_level", "low"),
                    "triggered_by": "gpt-4o",
                    "status": "completed",
                    "timestamp": now.isoformat(),
                }
                await db.scaling_events.insert_one(event)
                event.pop("_id", None)
                await db.scaling_state.update_one(
                    {"type": "global"},
                    {
                        "$set": {
                            "current_instances": new_count,
                            "desired_instances": new_count,
                            "updated_at": now.isoformat(),
                        }
                    },
                    upsert=True,
                )
                logger.info(
                    f"AI auto-scaling: {analysis['decision']} {current} -> {new_count} (confidence: {analysis['confidence']:.0%})"
                )

        logger.info(
            f"AI scaling eval: decision={analysis['decision']}, confidence={analysis['confidence']:.0%}, trend={analysis.get('predicted_trend', 'unknown')}"
        )

    except Exception as e:
        logger.error(f"AI scaling evaluation error: {e}")
