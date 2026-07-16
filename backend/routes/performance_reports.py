"""Automated Performance Reports — Daily & weekly email summaries to admin.

Background Jobs:
- Daily at 07:00 UTC: Summarizes last 24h API health, errors, scaling, image gen
- Weekly on Monday at 07:00 UTC: Full weekly digest with trends

API:
- POST /api/admin/platform/send-report   — Send report on-demand
- GET  /api/admin/platform/report-preview — Preview next report as JSON
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from routes.db import db, get_current_user
from routes.platform_monitor import _request_stats, _server_start, _format_uptime

logger = logging.getLogger(__name__)
router = APIRouter()


async def _collect_report_data(period: str = "daily") -> dict:
    """Collect all platform metrics for the report."""
    import time
    import psutil

    now = datetime.now(timezone.utc)
    if period == "weekly":
        since = (now - timedelta(days=7)).isoformat()
        label = "Weekly"
    else:
        since = (now - timedelta(days=1)).isoformat()
        label = "Daily"

    # Uptime
    uptime_s = time.time() - _server_start
    uptime_str = _format_uptime(uptime_s)

    # API Performance
    total_req = _request_stats["total_requests"]
    total_err = _request_stats["total_errors"]
    error_rate = round((total_err / max(total_req, 1)) * 100, 2)
    rpm = round(total_req / max(uptime_s / 60, 1), 1)
    _all_times = [t for times in _request_stats["endpoint_times"].values() for t in times]
    avg_response_ms = round(sum(_all_times) / len(_all_times), 1) if _all_times else None

    # Top 5 slowest endpoints
    top_endpoints = []
    for path, times in _request_stats["endpoint_times"].items():
        if times:
            top_endpoints.append(
                {
                    "path": path,
                    "avg_ms": round(sum(times) / len(times), 1),
                    "count": len(times),
                }
            )
    top_endpoints.sort(key=lambda x: x["avg_ms"], reverse=True)
    top_5 = top_endpoints[:5]

    # Slow requests
    slow_count = len(_request_stats["slow_requests"])

    # Status distribution
    status_dist = dict(_request_stats["status_counts"])

    # System resources
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # AI Scaling
    ai_analyses = await db.ai_scaling_analyses.count_documents({"timestamp": {"$gte": since}})
    scale_events = (
        await db.scaling_events.find({"timestamp": {"$gte": since}}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    )
    scale_ups = sum(1 for e in scale_events if e.get("action") == "scale_up")
    scale_downs = sum(1 for e in scale_events if e.get("action") == "scale_down")
    ai_triggered = sum(1 for e in scale_events if e.get("trigger") == "ai")

    state = await db.scaling_state.find_one({"type": "global"}, {"_id": 0}) or {}
    current_instances = state.get("current_instances", 1)

    # Image Generation
    img_total = await db.image_gen_logs.count_documents({"timestamp": {"$gte": since}})
    img_success = await db.image_gen_logs.count_documents({"timestamp": {"$gte": since}, "status": "success"})
    img_failed = await db.image_gen_logs.count_documents({"timestamp": {"$gte": since}, "status": "failed"})
    img_retried = await db.image_gen_logs.count_documents({"timestamp": {"$gte": since}, "retries": {"$gt": 0}})
    img_rate = round((img_success / max(img_total, 1)) * 100, 1)

    # Recent errors
    recent_errors = list(reversed(_request_stats["recent_errors"][-10:]))

    # Users
    total_users = await db.users.count_documents({})

    return {
        "period": label,
        "generated_at": now.isoformat(),
        "since": since,
        "uptime": uptime_str,
        "api": {
            "total_requests": total_req,
            "total_errors": total_err,
            "error_rate_pct": error_rate,
            "avg_response_ms": avg_response_ms,
            "rpm": rpm,
            "slow_requests": slow_count,
            "status_distribution": status_dist,
            "top_endpoints": top_5,
        },
        "system": {
            "cpu_pct": round(cpu, 1),
            "memory_pct": round(mem.percent, 1),
            "disk_pct": round(disk.percent, 1),
        },
        "scaling": {
            "ai_analyses": ai_analyses,
            "scale_ups": scale_ups,
            "scale_downs": scale_downs,
            "ai_triggered": ai_triggered,
            "current_instances": current_instances,
        },
        "image_gen": {
            "total": img_total,
            "success": img_success,
            "failed": img_failed,
            "retried": img_retried,
            "success_rate": img_rate,
        },
        "errors": recent_errors[:5],
        "total_users": total_users,
    }


def _build_report_html(data: dict) -> str:
    """Build a professional HTML email for the performance report."""
    from utils.email_service import render_email_header_panel
    from utils.email_templates import _enterprise_footer

    period = data["period"]
    gen_at = data["generated_at"][:16].replace("T", " ")
    api = data["api"]
    sys = data["system"]
    sc = data["scaling"]
    img = data["image_gen"]
    errors = data.get("errors", [])

    # Health indicator
    is_healthy = api["error_rate_pct"] < 5 and sys["cpu_pct"] < 90 and sys["memory_pct"] < 95
    health_color = "#10B981" if is_healthy else "#F59E0B"
    health_label = "Operational" if is_healthy else "Needs Attention"

    # Slowest endpoints rows
    ep_rows = ""
    for ep in api.get("top_endpoints", []):
        ep_rows += f'<tr><td style="padding:6px 12px;font-size:13px;color:#374151;border-bottom:1px solid #E5E7EB;">{ep["path"]}</td><td style="padding:6px 12px;font-size:13px;color:#6B7280;border-bottom:1px solid #E5E7EB;text-align:right;">{ep["avg_ms"]}ms</td><td style="padding:6px 12px;font-size:13px;color:#6B7280;border-bottom:1px solid #E5E7EB;text-align:right;">{ep["count"]}x</td></tr>'

    # Error rows
    err_rows = ""
    for err in errors[:5]:
        err_rows += f'<tr><td style="padding:4px 8px;font-size:12px;color:#374151;">{err.get("method", "")} {err.get("path", "")}</td><td style="padding:4px 8px;font-size:12px;color:#EF4444;text-align:right;">{err.get("status", "")}</td></tr>'

    header_html = render_email_header_panel(
        title=f"RealAICoach {period} Report",
        subtitle="Automated platform performance summary for leadership review.",
        variant="report",
        accent="#1D4ED8",
        meta_label="Generated",
        meta_value=f"{gen_at} UTC",
    )

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#F3F4F6;">
<div style="max-width:640px;margin:0 auto;padding:24px;">

  <!-- Header -->
  <div style="border-radius:20px;overflow:hidden;margin-bottom:20px;">
    {header_html}
    <div style="padding:14px 24px;background:#0F172A;">
      <div style="display:inline-block;background:{health_color}22;border:1px solid {health_color};border-radius:20px;padding:4px 14px;">
      <span style="color:{health_color};font-size:12px;font-weight:700;">{health_label}</span>
    </div>
  </div>
  </div>

  <!-- Quick Stats -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
    <tr>
      <td width="24%" style="background:#FFF;border-radius:10px;padding:16px;border:1px solid #E5E7EB;">
        <div style="font-size:11px;color:#6B7280;margin-bottom:4px;">Uptime</div>
        <div style="font-size:20px;font-weight:800;color:#10B981;">{data["uptime"]}</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="background:#FFF;border-radius:10px;padding:16px;border:1px solid #E5E7EB;">
        <div style="font-size:11px;color:#6B7280;margin-bottom:4px;">Requests</div>
        <div style="font-size:20px;font-weight:800;color:#3B82F6;">{api["total_requests"]}</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="background:#FFF;border-radius:10px;padding:16px;border:1px solid #E5E7EB;">
        <div style="font-size:11px;color:#6B7280;margin-bottom:4px;">Error Rate</div>
        <div style="font-size:20px;font-weight:800;color:{"#EF4444" if api["error_rate_pct"] > 5 else "#10B981"};">{api["error_rate_pct"]}%</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="background:#FFF;border-radius:10px;padding:16px;border:1px solid #E5E7EB;">
        <div style="font-size:11px;color:#6B7280;margin-bottom:4px;">Users</div>
        <div style="font-size:20px;font-weight:800;color:#8B5CF6;">{data["total_users"]}</div>
      </td>
    </tr>
  </table>

  <!-- System Resources -->
  <div style="background:#FFF;border-radius:10px;padding:20px;border:1px solid #E5E7EB;margin-bottom:16px;">
    <h2 style="font-size:14px;color:#111827;margin:0 0 14px;">System Resources</h2>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
        <tr><td style="font-size:12px;color:#6B7280;">CPU</td><td style="font-size:12px;color:#111827;font-weight:600;text-align:right;">{sys["cpu_pct"]}%</td></tr>
      </table>
      <div style="height:6px;background:#E5E7EB;border-radius:3px;overflow:hidden;margin-bottom:10px;"><div style="height:100%;width:{sys["cpu_pct"]}%;background:{"#EF4444" if sys["cpu_pct"] > 80 else "#10B981"};border-radius:3px;"></div></div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
        <tr><td style="font-size:12px;color:#6B7280;">Memory</td><td style="font-size:12px;color:#111827;font-weight:600;text-align:right;">{sys["memory_pct"]}%</td></tr>
      </table>
      <div style="height:6px;background:#E5E7EB;border-radius:3px;overflow:hidden;margin-bottom:10px;"><div style="height:100%;width:{sys["memory_pct"]}%;background:{"#EF4444" if sys["memory_pct"] > 80 else "#3B82F6"};border-radius:3px;"></div></div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td style="font-size:12px;color:#6B7280;">Disk</td><td style="font-size:12px;color:#111827;font-weight:600;text-align:right;">{sys["disk_pct"]}%</td></tr>
      </table>
      <div style="height:6px;background:#E5E7EB;border-radius:3px;overflow:hidden;"><div style="height:100%;width:{sys["disk_pct"]}%;background:{"#EF4444" if sys["disk_pct"] > 80 else "#8B5CF6"};border-radius:3px;"></div></div>
    </div>
  </div>

  <!-- AI Scaling -->
  <div style="background:#FFF;border-radius:10px;padding:20px;border:1px solid #E5E7EB;margin-bottom:16px;">
    <h2 style="font-size:14px;color:#111827;margin:0 0 14px;">AI Auto-Scaling <span style="font-size:10px;color:#3B82F6;background:#EFF6FF;padding:2px 8px;border-radius:8px;margin-left:6px;">GPT-4o</span></h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#8B5CF6;">{sc["current_instances"]}</span><br><span style="font-size:11px;color:#6B7280;">Instances</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#3B82F6;">{sc["ai_analyses"]}</span><br><span style="font-size:11px;color:#6B7280;">AI Analyses</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#10B981;">{sc["scale_ups"]}</span><br><span style="font-size:11px;color:#6B7280;">Scale Ups</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#F59E0B;">{sc["scale_downs"]}</span><br><span style="font-size:11px;color:#6B7280;">Scale Downs</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#06B6D4;">{sc["ai_triggered"]}</span><br><span style="font-size:11px;color:#6B7280;">AI-Triggered</span></td>
      </tr>
    </table>
  </div>

  <!-- Image Generation -->
  <div style="background:#FFF;border-radius:10px;padding:20px;border:1px solid #E5E7EB;margin-bottom:16px;">
    <h2 style="font-size:14px;color:#111827;margin:0 0 14px;">Image Generation</h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#3B82F6;">{img["total"]}</span><br><span style="font-size:11px;color:#6B7280;">Total</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#10B981;">{img["success"]}</span><br><span style="font-size:11px;color:#6B7280;">Success</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#EF4444;">{img["failed"]}</span><br><span style="font-size:11px;color:#6B7280;">Failed</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:#F59E0B;">{img["retried"]}</span><br><span style="font-size:11px;color:#6B7280;">Retried</span></td>
        <td style="text-align:center;padding:4px 8px;"><span style="font-size:24px;font-weight:800;color:{"#10B981" if img["success_rate"] >= 90 else "#F59E0B"};">{img["success_rate"]}%</span><br><span style="font-size:11px;color:#6B7280;">Success Rate</span></td>
      </tr>
    </table>
  </div>

  <!-- Slowest Endpoints -->
  {'<div style="background:#FFF;border-radius:10px;padding:20px;border:1px solid #E5E7EB;margin-bottom:16px;"><h2 style="font-size:14px;color:#111827;margin:0 0 14px;">Slowest Endpoints</h2><table style="width:100%;border-collapse:collapse;"><tr><th style="text-align:left;padding:6px 12px;font-size:11px;color:#6B7280;border-bottom:2px solid #E5E7EB;">Path</th><th style="text-align:right;padding:6px 12px;font-size:11px;color:#6B7280;border-bottom:2px solid #E5E7EB;">Avg</th><th style="text-align:right;padding:6px 12px;font-size:11px;color:#6B7280;border-bottom:2px solid #E5E7EB;">Count</th></tr>' + ep_rows + "</table></div>" if ep_rows else ""}

  <!-- Recent Errors -->
  {'<div style="background:#FFF;border-radius:10px;padding:20px;border:1px solid #FCA5A5;margin-bottom:16px;"><h2 style="font-size:14px;color:#DC2626;margin:0 0 14px;">Recent Errors</h2><table style="width:100%;border-collapse:collapse;">' + err_rows + "</table></div>" if err_rows else '<div style="background:#FFF;border-radius:10px;padding:16px;border:1px solid #A7F3D0;margin-bottom:16px;text-align:center;"><span style="color:#10B981;font-size:13px;font-weight:600;">No errors detected</span></div>'}

  <!-- Enterprise Footer -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{_enterprise_footer("light")}</table>

</div>
</body>
</html>"""


async def send_performance_report(period: str = "daily") -> dict:
    """Collect data and send the performance report email to all admin users."""
    from utils.email_service import send_catalog_template

    data = await _collect_report_data(period)
    api_data = data.get("api", {})
    sys_data = data.get("system", {})
    is_healthy = api_data.get("error_rate_pct", 0) < 5 and sys_data.get("cpu_pct", 0) < 90
    health_status = "Operational" if is_healthy else "Needs Attention"

    # Find all admin users
    admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1}).to_list(50)
    if not admins:
        admins = [{"email": "admin@realaicoach.app", "name": "Admin"}]

    sent_to = []
    _avg_ms = api_data.get("avg_response_ms")
    _avg_display = f"{_avg_ms}ms" if _avg_ms is not None else "n/a (no samples yet)"
    _gen_raw = data.get("generated_at", "")
    try:
        _gen_display = datetime.fromisoformat(_gen_raw).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        _gen_display = _gen_raw
    for admin in admins:
        result = await send_catalog_template(
            recipient_email=admin["email"],
            template_key="performance_report_v7",
            recipient_name=admin.get("name", "Admin"),
            period=data.get("period", period.title()),
            health_status=health_status,
            avg_response=_avg_display,
            error_rate=f"{api_data.get('error_rate_pct', 0)}%",
            cpu=f"{sys_data.get('cpu_pct', 0)}%",
            memory=f"{sys_data.get('memory_pct', 0)}%",
            generated_at=_gen_display,
        )
        if result.get("success"):
            sent_to.append(admin["email"])
            logger.info(f"Performance report ({period}) sent to {admin['email']}")
        else:
            logger.warning(f"Failed to send report to {admin['email']}: {result.get('error')}")

    return {
        "period": data["period"],
        "sent_to": sent_to,
        "data_summary": {
            "uptime": data["uptime"],
            "total_requests": data["api"]["total_requests"],
            "error_rate": data["api"]["error_rate_pct"],
            "ai_analyses": data["scaling"]["ai_analyses"],
            "instances": data["scaling"]["current_instances"],
        },
        "timestamp": data["generated_at"],
    }


# ── API Endpoints ──


@router.post("/admin/platform/send-report")
async def send_report_now(request: Request):
    """Send a performance report on-demand."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    period = body.get("period", "daily")

    result = await send_performance_report(period)
    return {"message": f"Report sent to {len(result['sent_to'])} admin(s)", **result}


@router.get("/admin/platform/report-preview")
async def preview_report(request: Request, period: str = "daily"):
    """Preview the next report data (without sending email)."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    data = await _collect_report_data(period)
    return data
