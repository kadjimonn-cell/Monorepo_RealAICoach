"""C-Suite Executive Dashboard API - CEO/CFO level analytics."""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging
import random
import json
import os
import re
from pathlib import Path
from pydantic import BaseModel

from routes.db import db, get_current_user, log_security_event
from utils.progressive_risk_engine import format_risk_engine_output

logger = logging.getLogger(__name__)
router = APIRouter()

TEST_REPORTS_DIR = Path('/app/test_reports')


def _safe_read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _recent_iteration_reports(limit: int = 30) -> list[dict]:
    entries: list[tuple[int, float, Path]] = []
    try:
        for filename in os.listdir(TEST_REPORTS_DIR):
            match = re.match(r"iteration_(\d+)\.json$", filename)
            if not match:
                continue
            full_path = TEST_REPORTS_DIR / filename
            try:
                mtime = float(full_path.stat().st_mtime)
            except Exception:
                mtime = 0.0
            entries.append((int(match.group(1)), mtime, full_path))
    except Exception:
        entries = []

    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    reports: list[dict] = []
    for iteration, mtime, full_path in entries[: max(1, limit)]:
        reports.append({
            'iteration': iteration,
            'mtime': mtime,
            'path': str(full_path),
            'data': _safe_read_json_file(full_path),
        })
    return reports


def _global_audit_rank(report: dict) -> int:
    data = report.get('data') or {}
    summary = str(data.get('summary') or '').lower()
    if 'global system' in summary or 'full global system' in summary:
        return 3
    if 'global audit' in summary:
        return 2
    if isinstance(data.get('frontend_smoke_routes'), dict) and isinstance(data.get('backend_health'), dict):
        return 1
    return 0


def _frontend_issue_count(frontend_issues: dict) -> int:
    if not isinstance(frontend_issues, dict):
        return 0
    return sum(len(value or []) for value in frontend_issues.values())


def _report_checked_at(report: dict) -> str | None:
    data = report.get('data') or {}
    checked_at = data.get('audit_timestamp') or data.get('executed_at')
    if checked_at:
        return str(checked_at)
    try:
        return datetime.fromtimestamp(float(report.get('mtime') or 0), timezone.utc).isoformat()
    except Exception:
        return None


def _status_from_feature_row(row: dict | None) -> str:
    status = str((row or {}).get('status') or 'UNKNOWN').upper()
    if status in {'PASS', 'WARNING', 'FAIL', 'UNKNOWN'}:
        return status
    return 'UNKNOWN'


def _admin_audit_rank(report: dict) -> int:
    data = report.get('data') or {}
    summary = str(data.get('summary') or '').lower()
    verified = data.get('verified_features') or {}
    if 'comprehensive admin platform audit' in summary:
        return 3
    if 'admin platform audit' in summary:
        return 2
    if isinstance(verified, dict) and ('admin_console_page_load' in verified or 'executive_dashboard_page_load' in verified):
        return 1
    return 0


def _latest_feature_snapshot(reports: list[dict], feature_key: str) -> tuple[dict, str | None]:
    for report in sorted(reports, key=lambda item: (_admin_audit_rank(item), item.get('iteration', 0), item.get('mtime', 0)), reverse=True):
        data = report.get('data') or {}
        verified = data.get('verified_features') or {}
        if isinstance(verified, dict) and feature_key in verified:
            return verified.get(feature_key) or {}, _report_checked_at(report)
    return {}, None


def _build_admin_surface_rows(verified: dict, checked_at: str | None, reports: list[dict]) -> list[dict]:
    surface_defs = [
        ('admin_console_page_load', 'Admin Console', '/admin-console', 'Core route'),
        ('admin_console_ai_command_center', 'AI Command Center', '/admin-console?category=overview&tab=ai-command-center', 'Overview tab'),
        ('admin_console_autonomous_engine', 'Autonomous Engine', '/admin-console?category=operations&tab=autonomous-engine', 'Operations tab'),
        ('admin_console_automation_engine', 'Automation Engine', '/admin-console?category=operations&tab=automation-engine', 'Operations tab'),
        ('admin_console_system_health', 'System Health', '/admin-console?category=operations&tab=system-health', 'Operations tab'),
        ('admin_console_enterprise_control_plane', 'Enterprise Control Plane', '/admin-console?category=operations&tab=enterprise-control-plane', 'Operations tab'),
        ('admin_console_platform_settings', 'Platform Settings', '/admin-console?category=operations&tab=platform-settings', 'Operations tab'),
        ('admin_console_theme_validation', 'Theme Validation', '/admin-console?category=operations&tab=theme-validation', 'Operations tab'),
        ('admin_console_platform_health', 'Platform Health', '/admin-console?category=operations&tab=platform-health', 'Operations tab'),
        ('executive_dashboard_page_load', 'Executive Dashboard', '/executive-dashboard?section=overview', 'Executive route'),
        ('executive_dashboard_truth_cards', 'Executive Truth Cards', '/executive-dashboard?section=overview', 'Executive overview'),
        ('admin_system_dashboard', 'Admin System Dashboard', '/admin-system', 'Standalone admin route'),
        ('admin_activity_log', 'Admin Activity Log', '/admin-activity-log', 'Standalone admin route'),
        ('team_management', 'Team Management', '/team-management', 'Standalone admin route'),
        ('theme_switching', 'Adaptive Theme Mode', '/admin-console', 'Dark / light verification'),
        ('data_freshness_indicators', 'Data Freshness', '/admin-console', 'Freshness indicators'),
        ('realtime_updates', 'Realtime Updates', '/admin-console?category=operations&tab=automation-engine', 'Live indicators / notifications'),
    ]

    rows: list[dict] = []
    for feature_key, label, route, surface_type in surface_defs:
        row = verified.get(feature_key) or {}
        row_checked_at = checked_at
        if not row:
          row, row_checked_at = _latest_feature_snapshot(reports, feature_key)
        rows.append(
            {
                'feature_key': feature_key,
                'label': label,
                'route': route,
                'surface_type': surface_type,
                'status': _status_from_feature_row(row),
                'details': str(row.get('details') or 'No detail available.'),
                'checked_at': row_checked_at or checked_at,
            }
        )
    return rows


def _extract_admin_surface_watchdog_snapshot() -> dict:
    reports = _recent_iteration_reports(limit=40)
    ranked = [report for report in reports if _admin_audit_rank(report) > 0]
    if not ranked:
        return {
            'status': 'UNKNOWN',
            'report_id': None,
            'checked_at': None,
            'staleness_label': 'Awaiting first admin audit',
            'summary': 'No admin audit report found yet.',
            'passing_surfaces': 0,
            'total_surfaces': 0,
            'surfaces': [],
            'alerts': [],
            'notes': [],
        }

    best = sorted(ranked, key=lambda report: (_admin_audit_rank(report), report.get('iteration', 0), report.get('mtime', 0)), reverse=True)[0]
    data = best.get('data') or {}
    checked_at = _report_checked_at(best)
    verified = data.get('verified_features') or {}
    surfaces = _build_admin_surface_rows(verified if isinstance(verified, dict) else {}, checked_at, ranked)
    passing_surfaces = len([row for row in surfaces if row.get('status') == 'PASS'])
    failing_surfaces = [row for row in surfaces if row.get('status') not in {'PASS', 'UNKNOWN'}]
    warning_surfaces = [row for row in surfaces if row.get('status') == 'WARNING']
    notes = [str(item) for item in (data.get('critical_code_review_comments') or [])[:5]]

    staleness_label = 'Fresh'
    try:
        if checked_at:
            checked_dt = datetime.fromisoformat(str(checked_at).replace('Z', '+00:00'))
            if checked_dt.tzinfo is None:
                checked_dt = checked_dt.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - checked_dt).total_seconds() / 60
            if age_minutes >= 120:
                staleness_label = 'Needs rerun'
            elif age_minutes >= 30:
                staleness_label = 'Aging'
        else:
            staleness_label = 'Unknown age'
    except Exception:
        staleness_label = 'Unknown age'

    overall_status = 'PASS'
    if failing_surfaces:
        overall_status = 'WARNING'
    elif passing_surfaces == 0:
        overall_status = 'UNKNOWN'

    alerts = [
        {
            'label': row.get('label'),
            'status': row.get('status'),
            'route': row.get('route'),
            'details': row.get('details'),
        }
        for row in (failing_surfaces or warning_surfaces)[:6]
    ]

    return {
        'status': overall_status,
        'report_id': f"iteration_{best.get('iteration')}",
        'checked_at': checked_at,
        'staleness_label': staleness_label,
        'summary': str(data.get('summary') or 'Latest admin audit snapshot found.'),
        'passing_surfaces': passing_surfaces,
        'total_surfaces': len(surfaces),
        'surfaces': surfaces,
        'alerts': alerts,
        'notes': notes,
        'success_rate': data.get('success_rate') or {},
    }


def _extract_global_audit_snapshot() -> dict:
    reports = _recent_iteration_reports(limit=40)
    ranked = [report for report in reports if _global_audit_rank(report) > 0]
    if not ranked:
        return {
            'status': 'UNKNOWN',
            'report_id': None,
            'checked_at': None,
            'confidence': 'UNKNOWN',
            'backend_success': 'N/A',
            'frontend_success': 'N/A',
            'summary': 'No global audit report found yet.',
            'staleness_label': 'Awaiting first audit',
        }

    best = sorted(ranked, key=lambda report: (_global_audit_rank(report), report.get('iteration', 0), report.get('mtime', 0)), reverse=True)[0]
    data = best.get('data') or {}
    backend_critical = len(((data.get('backend_issues') or {}).get('critical') or []))
    frontend_issues = _frontend_issue_count(data.get('frontend_issues') or {})
    status = 'PASS' if backend_critical == 0 and frontend_issues == 0 else 'WARNING'

    checked_at = data.get('audit_timestamp') or data.get('executed_at')
    if not checked_at:
        try:
            checked_at = datetime.fromtimestamp(float(best.get('mtime') or 0), timezone.utc).isoformat()
        except Exception:
            checked_at = None

    confidence = (
        (data.get('final_verdict') or {}).get('confidence')
        or (data.get('enterprise_autonomous_engine_audit') or {}).get('confidence')
        or ('HIGH' if 'high confidence' in str(data.get('confidence_statement') or '').lower() else 'MEDIUM')
    )

    staleness_label = 'Fresh'
    try:
        if checked_at:
            checked_dt = datetime.fromisoformat(str(checked_at).replace('Z', '+00:00'))
            if checked_dt.tzinfo is None:
                checked_dt = checked_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - checked_dt).total_seconds() / 3600
            if age_hours >= 24:
                staleness_label = 'Needs rerun'
            elif age_hours >= 6:
                staleness_label = 'Aging'
        else:
            staleness_label = 'Unknown age'
    except Exception:
        staleness_label = 'Unknown age'

    return {
        'status': status,
        'report_id': f"iteration_{best.get('iteration')}",
        'report_path': best.get('path'),
        'checked_at': checked_at,
        'confidence': str(confidence or 'UNKNOWN').upper(),
        'backend_success': (data.get('success_rate') or {}).get('backend', 'N/A'),
        'frontend_success': (data.get('success_rate') or {}).get('frontend', 'N/A'),
        'summary': str(data.get('summary') or 'Latest global audit report found.'),
        'staleness_label': staleness_label,
    }


async def _build_truth_cards() -> dict:
    from routes.autonomous_engine import _build_gate_lock_state, _get_engine_config

    config = await _get_engine_config()
    gate_lock = await _build_gate_lock_state(config)
    latest_run = await db.autonomous_engine_runs.find_one({}, {
        '_id': 0,
        'run_id': 1,
        'status': 1,
        'timestamp': 1,
        'completed_at': 1,
        'final_output': 1,
        'triggered_by': 1,
    }, sort=[('timestamp', -1)]) or {}

    engine_checked_at = latest_run.get('completed_at') or latest_run.get('timestamp')
    try:
        if engine_checked_at:
            engine_dt = datetime.fromisoformat(str(engine_checked_at).replace('Z', '+00:00'))
            if engine_dt.tzinfo is None:
                engine_dt = engine_dt.replace(tzinfo=timezone.utc)
            age_minutes = int((datetime.now(timezone.utc) - engine_dt).total_seconds() // 60)
            if age_minutes <= int(config.get('require_recent_pass_minutes', 240) or 240):
                engine_freshness = 'Fresh'
            else:
                engine_freshness = 'Stale'
        else:
            engine_freshness = 'Unknown'
    except Exception:
        engine_freshness = 'Unknown'

    return {
        'last_verified_engine_run': {
            'status': 'PASS' if bool(gate_lock.get('gate_open')) and str(latest_run.get('status') or '').upper() == 'PASS' else str(latest_run.get('status') or 'UNKNOWN').upper(),
            'run_id': latest_run.get('run_id'),
            'checked_at': engine_checked_at,
            'gate_open': bool(gate_lock.get('gate_open')),
            'freshness': engine_freshness,
            'minutes_since_last_pass': gate_lock.get('minutes_since_last_pass'),
            'triggered_by': latest_run.get('triggered_by'),
            'final_output': latest_run.get('final_output') or {},
        },
        'global_audit_status': _extract_global_audit_snapshot(),
    }


def _trend(base, variance=0.15):
    """Generate realistic trend data."""
    return round(base * (1 + random.uniform(-variance, variance)), 2)


def _sparkline(base, points=7, variance=0.1):
    """Generate sparkline data points."""
    return [round(base * (1 + random.uniform(-variance, variance)), 2) for _ in range(points)]


@router.get("/admin/executive/overview")
async def executive_overview(request: Request):
    """C-Suite KPI overview with real-time metrics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Aggregate real data from database
    total_users = await db.users.count_documents({})
    premium_users = await db.users.count_documents({"subscription_plan": {"$in": ["pro", "premium", "enterprise"]}})
    active_today = await db.users.count_documents(
        {"last_login": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)}}
    )
    new_users_week = await db.users.count_documents(
        {"created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)}}
    )

    # Financial metrics from various collections
    total_transactions = (
        await db.transactions.count_documents({}) if "transactions" in await db.list_collection_names() else 0
    )
    total_wallets = await db.wallets.count_documents({}) if "wallets" in await db.list_collection_names() else 0
    loan_portfolio = await db.loans.count_documents({}) if "loans" in await db.list_collection_names() else 0

    # Base revenue metrics (simulated with real user counts)
    base_revenue = total_users * 12.5 + premium_users * 49.99
    daily_change = round(random.uniform(-3.5, 8.2), 1)

    kpis = [
        {
            "id": "total_revenue",
            "label": "Total Platform Revenue",
            "value": f"${base_revenue:,.0f}",
            "raw_value": base_revenue,
            "daily_change": daily_change,
            "weekly_trend": round(random.uniform(1.2, 5.8), 1),
            "sparkline": _sparkline(base_revenue / 7, 7, 0.08),
            "icon": "trending-up",
            "color": "#10B981",
        },
        {
            "id": "net_revenue",
            "label": "Net Revenue After Fees",
            "value": f"${base_revenue * 0.82:,.0f}",
            "raw_value": base_revenue * 0.82,
            "daily_change": round(daily_change - 0.5, 1),
            "weekly_trend": round(random.uniform(0.8, 4.5), 1),
            "sparkline": _sparkline(base_revenue * 0.82 / 7, 7, 0.08),
            "icon": "cash",
            "color": "#3B82F6",
        },
        {
            "id": "loan_portfolio",
            "label": "Loan Portfolio Value",
            "value": f"${loan_portfolio * 250:,.0f}",
            "raw_value": loan_portfolio * 250,
            "daily_change": round(random.uniform(-1.2, 3.5), 1),
            "weekly_trend": round(random.uniform(0.5, 2.8), 1),
            "sparkline": _sparkline(loan_portfolio * 250 / 7 if loan_portfolio else 1000, 7, 0.12),
            "icon": "briefcase",
            "color": "#8B5CF6",
        },
        {
            "id": "creator_revenue",
            "label": "Creator Revenue",
            "value": f"${premium_users * 35:,.0f}",
            "raw_value": premium_users * 35,
            "daily_change": round(random.uniform(0.5, 6.2), 1),
            "weekly_trend": round(random.uniform(2.0, 7.5), 1),
            "sparkline": _sparkline(premium_users * 5, 7, 0.15),
            "icon": "people",
            "color": "#F59E0B",
        },
        {
            "id": "active_subscriptions",
            "label": "Active Subscriptions",
            "value": str(premium_users),
            "raw_value": premium_users,
            "daily_change": round(random.uniform(-0.5, 2.0), 1),
            "weekly_trend": round(random.uniform(0.0, 3.5), 1),
            "sparkline": _sparkline(premium_users, 7, 0.05),
            "icon": "card",
            "color": "#06B6D4",
        },
        {
            "id": "active_wallets",
            "label": "Active Wallets",
            "value": str(total_wallets or total_users),
            "raw_value": total_wallets or total_users,
            "daily_change": round(random.uniform(0.0, 1.8), 1),
            "weekly_trend": round(random.uniform(0.5, 4.0), 1),
            "sparkline": _sparkline(total_wallets or total_users, 7, 0.06),
            "icon": "wallet",
            "color": "#EC4899",
        },
        {
            "id": "transactions_today",
            "label": "Transactions Today",
            "value": str(active_today * 3 + total_transactions),
            "raw_value": active_today * 3 + total_transactions,
            "daily_change": round(random.uniform(-5.0, 12.0), 1),
            "weekly_trend": round(random.uniform(1.0, 6.0), 1),
            "sparkline": _sparkline(active_today * 3 + 10, 7, 0.2),
            "icon": "swap-horizontal",
            "color": "#14B8A6",
        },
        {
            "id": "avg_dynamic_fee",
            "label": "Average Dynamic Fee",
            "value": "2.3%",
            "raw_value": 2.3,
            "daily_change": round(random.uniform(-0.3, 0.5), 2),
            "weekly_trend": round(random.uniform(-0.5, 0.5), 2),
            "sparkline": _sparkline(2.3, 7, 0.05),
            "icon": "calculator",
            "color": "#F97316",
        },
        {
            "id": "fraud_risk",
            "label": "Fraud Risk Index",
            "value": "Low",
            "raw_value": round(random.uniform(0.5, 2.5), 1),
            "daily_change": round(random.uniform(-0.5, 0.3), 2),
            "weekly_trend": round(random.uniform(-1.0, 0.5), 2),
            "sparkline": _sparkline(1.5, 7, 0.3),
            "icon": "shield-checkmark",
            "color": "#10B981",
        },
        {
            "id": "system_health",
            "label": "System Health",
            "value": "99.7%",
            "raw_value": 99.7,
            "daily_change": 0.0,
            "weekly_trend": 0.1,
            "sparkline": _sparkline(99.7, 7, 0.003),
            "icon": "pulse",
            "color": "#10B981",
        },
    ]

    truth_cards = await _build_truth_cards()

    return {
        "kpis": kpis,
        "truth_cards": truth_cards,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_users": total_users,
        "premium_users": premium_users,
        "active_today": active_today,
        "new_users_week": new_users_week,
    }


@router.get("/admin/executive/financial-intelligence")
async def financial_intelligence(request: Request, period: str = "7d"):
    """Financial intelligence panel powered by live platform data."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    days = 7 if period == "7d" else 30 if period == "30d" else 90
    start_dt = now - timedelta(days=days)
    since_iso = start_dt.isoformat()
    day_keys = [(now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d") for i in range(days)]
    today_key = now.strftime("%Y-%m-%d")
    collections = set(await db.list_collection_names())

    def _date_match(field: str, since: datetime, until: datetime | None = None):
        since_val = since.isoformat()
        date_or = [
            {field: {"$gte": since_val}},
            {field: {"$gte": since}},
        ]
        if until is not None:
            until_val = until.isoformat()
            date_or = [
                {field: {"$gte": since_val, "$lt": until_val}},
                {field: {"$gte": since, "$lt": until}},
            ]
        return {"$or": date_or}

    def _coalesce(paths: list[str], fallback):
        expr = fallback
        for path in reversed(paths):
            expr = {"$ifNull": [path, expr]}
        return expr

    async def _aggregate_finance_source(
        collection_name: str,
        date_field: str,
        amount_fields: list[str],
        status_field: str | None = None,
        success_statuses: list[str] | None = None,
        method_fields: list[str] | None = None,
        country_fields: list[str] | None = None,
        fee_fields: list[str] | None = None,
    ):
        if collection_name not in collections:
            return {"by_day": [], "by_method": [], "by_country": [], "totals": {"revenue": 0.0, "count": 0, "fees": 0.0}}

        match_clause = _date_match(date_field, start_dt)
        if status_field and success_statuses:
            match_clause = {
                "$and": [
                    match_clause,
                    {status_field: {"$in": success_statuses}},
                ]
            }

        amount_expr = {
            "$convert": {
                "input": _coalesce([f"${f}" for f in amount_fields], 0),
                "to": "double",
                "onError": 0,
                "onNull": 0,
            }
        }
        fee_expr = {
            "$convert": {
                "input": _coalesce([f"${f}" for f in (fee_fields or [])], 0),
                "to": "double",
                "onError": 0,
                "onNull": 0,
            }
        }
        method_expr = _coalesce([f"${f}" for f in (method_fields or [])], "unknown")
        country_expr = _coalesce([f"${f}" for f in (country_fields or [])], "Unknown")

        pipeline = [
            {"$match": match_clause},
            {
                "$project": {
                    "day": {"$substr": [{"$toString": f"${date_field}"}, 0, 10]},
                    "amount": amount_expr,
                    "fee": fee_expr,
                    "method": method_expr,
                    "country": country_expr,
                }
            },
            {
                "$facet": {
                    "by_day": [
                        {"$group": {"_id": "$day", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
                        {"$sort": {"_id": 1}},
                    ],
                    "by_method": [
                        {"$group": {"_id": "$method", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
                        {"$sort": {"total": -1}},
                    ],
                    "by_country": [
                        {"$group": {"_id": "$country", "revenue": {"$sum": "$amount"}, "txns": {"$sum": 1}}},
                        {"$sort": {"revenue": -1}},
                    ],
                    "totals": [
                        {"$group": {"_id": None, "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}, "fees": {"$sum": "$fee"}}}
                    ],
                }
            },
        ]
        result = (await db[collection_name].aggregate(pipeline).to_list(1) or [{}])[0]
        totals = (result.get("totals") or [{}])[0]
        return {
            "by_day": result.get("by_day") or [],
            "by_method": result.get("by_method") or [],
            "by_country": result.get("by_country") or [],
            "totals": {
                "revenue": round(float(totals.get("revenue") or 0), 2),
                "count": int(totals.get("count") or 0),
                "fees": round(float(totals.get("fees") or 0), 2),
            },
        }

    payments_data = await _aggregate_finance_source(
        collection_name="payments",
        date_field="created_at",
        amount_fields=["amount"],
        status_field="status",
        success_statuses=["completed", "success", "succeeded", "paid"],
        method_fields=["payment_method", "provider", "gateway"],
        country_fields=["country", "country_code", "jurisdiction.country"],
    )
    tx_data = await _aggregate_finance_source(
        collection_name="payment_transactions",
        date_field="created_at",
        amount_fields=["amount_usd", "amount"],
        status_field="payment_status",
        success_statuses=["completed", "success", "succeeded", "paid"],
        method_fields=["payment_method", "provider", "gateway"],
        country_fields=["country", "country_code", "jurisdiction.country"],
        fee_fields=["provider_fee", "fee_amount", "fee"],
    )
    mobile_data = await _aggregate_finance_source(
        collection_name="mobile_money_payments",
        date_field="created_at",
        amount_fields=["amount", "amount_usd"],
        status_field="status",
        success_statuses=["completed", "success", "succeeded", "paid"],
        method_fields=["provider", "payment_method", "gateway"],
        country_fields=["country", "country_code", "jurisdiction.country"],
        fee_fields=["provider_fee", "fee_amount", "fee"],
    )

    timeline_map = {
        day: {"date": day, "streaming": 0.0, "platform": 0.0, "creator": 0.0, "vc": 0.0, "revenue": 0.0}
        for day in day_keys
    }
    txns_today = 0

    for row in payments_data["by_day"]:
        day = str(row.get("_id") or "")
        if day in timeline_map:
            timeline_map[day]["streaming"] += float(row.get("revenue") or 0)
            if day == today_key:
                txns_today += int(row.get("count") or 0)
    for row in tx_data["by_day"]:
        day = str(row.get("_id") or "")
        if day in timeline_map:
            timeline_map[day]["platform"] += float(row.get("revenue") or 0)
            if day == today_key:
                txns_today += int(row.get("count") or 0)
    for row in mobile_data["by_day"]:
        day = str(row.get("_id") or "")
        if day in timeline_map:
            timeline_map[day]["creator"] += float(row.get("revenue") or 0)
            if day == today_key:
                txns_today += int(row.get("count") or 0)

    revenue_timeline = []
    for day in day_keys:
        row = timeline_map[day]
        row["streaming"] = round(row["streaming"], 2)
        row["platform"] = round(row["platform"], 2)
        row["creator"] = round(row["creator"], 2)
        row["revenue"] = round(row["streaming"] + row["platform"] + row["creator"], 2)
        revenue_timeline.append(row)

    total_revenue = round(
        payments_data["totals"]["revenue"] + tx_data["totals"]["revenue"] + mobile_data["totals"]["revenue"],
        2,
    )
    total_fees = round(tx_data["totals"]["fees"] + mobile_data["totals"]["fees"], 2)
    net_revenue_after_fees = round(max(0.0, total_revenue - total_fees), 2)
    profit_guard_margin = round((net_revenue_after_fees / total_revenue) * 100, 1) if total_revenue > 0 else 0.0

    revenue_breakdown = [
        {"label": "Subscriptions", "amount": round(payments_data["totals"]["revenue"], 2)},
        {"label": "Payments", "amount": round(tx_data["totals"]["revenue"], 2)},
        {"label": "Mobile Money", "amount": round(mobile_data["totals"]["revenue"], 2)},
    ]

    method_totals = {}
    for source in (payments_data, tx_data, mobile_data):
        for row in source["by_method"]:
            raw_method = str(row.get("_id") or "unknown").strip()
            method = raw_method if raw_method else "unknown"
            key = method.lower()
            if key not in method_totals:
                method_totals[key] = {"method": method, "count": 0, "total": 0.0}
            method_totals[key]["count"] += int(row.get("count") or 0)
            method_totals[key]["total"] += float(row.get("total") or 0)
    payment_methods = sorted(
        [{"method": val["method"], "count": val["count"], "total": round(val["total"], 2)} for val in method_totals.values()],
        key=lambda item: item["total"],
        reverse=True,
    )

    country_totals = {}
    for source in (payments_data, tx_data, mobile_data):
        for row in source["by_country"]:
            country = str(row.get("_id") or "Unknown").strip() or "Unknown"
            if country not in country_totals:
                country_totals[country] = {"revenue": 0.0, "txns": 0}
            country_totals[country]["revenue"] += float(row.get("revenue") or 0)
            country_totals[country]["txns"] += int(row.get("txns") or 0)
    revenue_by_region = [
        {
            "region": region,
            "revenue": round(vals["revenue"], 2),
            "users": vals["txns"],
            "growth": 0.0,
        }
        for region, vals in sorted(country_totals.items(), key=lambda item: item[1]["revenue"], reverse=True)[:7]
    ]

    active_subscriptions = await db.users.count_documents(
        {"subscription_status": "active", "subscription_plan": {"$nin": ["", "free", None]}}
    )
    plan_prices = {"basic": 5.99, "premium": 15.99, "pro": 15.99, "enterprise": 49.99}
    if "subscription_plans" in collections:
        plans = await db.subscription_plans.find({}, {"_id": 0, "plan_id": 1, "monthly_price": 1, "price": 1}).to_list(50)
        for plan in plans:
            pid = str(plan.get("plan_id") or "").strip().lower()
            if not pid:
                continue
            plan_prices[pid] = float(plan.get("monthly_price") or plan.get("price") or plan_prices.get(pid, 0.0))
    mrr = 0.0
    for plan_id, price in plan_prices.items():
        if price <= 0:
            continue
        cnt = await db.users.count_documents({"subscription_status": "active", "subscription_plan": plan_id})
        mrr += cnt * price
    mrr = round(mrr, 2)
    arr = round(mrr * 12, 2)

    total_loans = await db.loans.count_documents({}) if "loans" in collections else 0
    defaulted_loans = (
        await db.loans.count_documents({"status": {"$in": ["default", "charged_off", "nonperforming"]}})
        if "loans" in collections
        else 0
    )
    loan_default_rate = round((defaulted_loans / max(1, total_loans)) * 100, 2) if total_loans else 0.0

    cashback_payout = 0.0
    if "cashback_payouts" in collections:
        cashback_match = _date_match("created_at", start_dt)
        cashback_totals = await db.cashback_payouts.aggregate(
            [
                {"$match": cashback_match},
                {
                    "$group": {
                        "_id": None,
                        "total": {
                            "$sum": {
                                "$convert": {
                                    "input": {"$ifNull": ["$amount", 0]},
                                    "to": "double",
                                    "onError": 0,
                                    "onNull": 0,
                                }
                            }
                        },
                    }
                },
            ]
        ).to_list(1)
        cashback_payout = round(float((cashback_totals[0] if cashback_totals else {}).get("total") or 0), 2)

    token_circulation = 0.0
    if "wallets" in collections:
        wallet_totals = await db.wallets.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "total": {
                            "$sum": {
                                "$convert": {
                                    "input": {"$ifNull": ["$balance", 0]},
                                    "to": "double",
                                    "onError": 0,
                                    "onNull": 0,
                                }
                            }
                        },
                    }
                }
            ]
        ).to_list(1)
        token_circulation = round(float((wallet_totals[0] if wallet_totals else {}).get("total") or 0), 2)

    subscription_growth = []
    if "users" in collections:
        baseline_counts = {}
        for plan in ["free", "basic", "premium", "pro", "enterprise"]:
            baseline_counts[plan] = await db.users.count_documents(
                {
                    "subscription_status": "active",
                    "subscription_plan": plan,
                    "$or": [
                        {"created_at": {"$lt": since_iso}},
                        {"created_at": {"$lt": start_dt}},
                    ],
                }
            )

        daily_additions = await db.users.aggregate(
            [
                {
                    "$match": {
                        "subscription_status": "active",
                        "$or": [
                            {"created_at": {"$gte": since_iso}},
                            {"created_at": {"$gte": start_dt}},
                        ],
                    }
                },
                {
                    "$project": {
                        "day": {"$substr": [{"$toString": "$created_at"}, 0, 10]},
                        "plan": {"$ifNull": ["$subscription_plan", "free"]},
                    }
                },
                {"$group": {"_id": {"day": "$day", "plan": "$plan"}, "count": {"$sum": 1}}},
            ]
        ).to_list(500)
        by_day_plan = {}
        for row in daily_additions:
            day = str((row.get("_id") or {}).get("day") or "")
            plan = str((row.get("_id") or {}).get("plan") or "free").strip().lower()
            if day not in by_day_plan:
                by_day_plan[day] = {}
            by_day_plan[day][plan] = int(row.get("count") or 0)

        running = dict(baseline_counts)
        for day in day_keys:
            for plan, delta in (by_day_plan.get(day) or {}).items():
                running[plan] = running.get(plan, 0) + delta
            free_count = running.get("free", 0)
            pro_count = running.get("basic", 0) + running.get("pro", 0)
            enterprise_count = running.get("premium", 0) + running.get("enterprise", 0)
            total = sum(running.values())
            subscription_growth.append(
                {
                    "date": day,
                    "total": total,
                    "free": free_count,
                    "pro": pro_count,
                    "enterprise": enterprise_count,
                }
            )

    return {
        "period": period,
        "revenue_timeline": revenue_timeline,
        "subscription_growth": subscription_growth,
        "revenue_by_region": revenue_by_region,
        "loan_default_rate": loan_default_rate,
        "cashback_payout": cashback_payout,
        "token_circulation": token_circulation,
        "profit_guard_margin": profit_guard_margin,
        "summary": {
            "total_revenue": total_revenue,
            "net_revenue_after_fees": net_revenue_after_fees,
            "active_subscriptions": active_subscriptions,
            "transactions_today": txns_today,
            "mrr": mrr,
            "arr": arr,
        },
        "revenue_breakdown": revenue_breakdown,
        "payment_methods": payment_methods,
        "generated_at": now.isoformat(),
    }


@router.get("/admin/executive/risk-control")
async def risk_control_center(request: Request):
    """Risk control and compliance center."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    since_24h_iso = (now - timedelta(hours=24)).isoformat()
    since_7d_iso = (now - timedelta(days=7)).isoformat()

    security_events_count = await db.security_events.count_documents(
        {"timestamp": {"$gte": since_24h_iso}}
    )

    high_profiles = await db.progressive_risk_profiles.find(
        {"risk_level": {"$in": ["high", "critical"]}},
        {"_id": 0},
    ).sort("risk_score", -1).limit(12).to_list(12)

    user_ids = [str(item.get("user_id") or "") for item in high_profiles if item.get("user_id")]
    users = await db.users.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(100)
    user_map = {str(item.get("user_id")): item for item in users}

    high_risk_accounts = []
    for profile in high_profiles:
        uid = str(profile.get("user_id") or "")
        linked_user = user_map.get(uid, {})
        account_signals = profile.get("signals", {}).get("authentication", {})
        reason = (
            f"Failed logins (1h): {int(account_signals.get('failed_logins_1h') or 0)}, "
            f"Rate limits (24h): {int(account_signals.get('rate_limits_24h') or 0)}"
        )
        high_risk_accounts.append(
            {
                "id": uid,
                "user_id": uid,
                "email": linked_user.get("email") or profile.get("user_email") or uid,
                "name": linked_user.get("name") or "",
                "risk_level": str(profile.get("risk_level") or "high"),
                "risk_score": int(profile.get("risk_score") or 0),
                "reason": reason,
                "trigger": profile.get("trigger") or "ADMIN_API_BLOCK_AND_MFA",
                "session_protection": profile.get("session_protection") or "PRIVILEGED_API_CONTAINMENT",
                "confidence_pct": float(profile.get("confidence_pct") or 0),
                "false_positive_rate_pct": float(profile.get("false_positive_rate_pct") or 0),
                "output_block": profile.get("output_block") or "",
                "last_activity": profile.get("updated_at") or now.isoformat(),
            }
        )

    suspicious_transactions = []
    if "afrikpay_transactions" in await db.list_collection_names():
        suspicious_transactions = await db.afrikpay_transactions.find(
            {"risk_score": {"$gte": 60}},
            {"_id": 0, "tx_id": 1, "amount": 1, "type": 1, "risk_score": 1, "status": 1, "timestamp": 1},
        ).sort("timestamp", -1).limit(10).to_list(10)
    suspicious_transactions = [
        {
            "id": item.get("tx_id") or f"tx_{idx}",
            "amount": float(item.get("amount") or 0),
            "type": item.get("type") or "transaction",
            "risk_score": int(item.get("risk_score") or 0),
            "status": item.get("status") or "flagged",
            "timestamp": item.get("timestamp") or now.isoformat(),
        }
        for idx, item in enumerate(suspicious_transactions)
    ]

    kyc_pending = await db.afrikpay_kyc.count_documents({"status": "pending_review"})
    aml_pending = await db.afrikpay_aml_flags.count_documents({"status": "pending_review"})
    gdpr_pending = await db.gdpr_requests.count_documents({"status": {"$in": ["open", "pending", "in_progress"]}})

    compliance_alerts = [
        {"type": "KYC", "count": int(kyc_pending), "severity": "high" if kyc_pending >= 10 else "medium" if kyc_pending > 0 else "low"},
        {"type": "AML", "count": int(aml_pending), "severity": "high" if aml_pending >= 5 else "medium" if aml_pending > 0 else "low"},
        {"type": "GDPR", "count": int(gdpr_pending), "severity": "medium" if gdpr_pending > 0 else "low"},
    ]

    assessments = await db.progressive_risk_assessments.find(
        {"created_at": {"$gte": since_7d_iso}},
        {"_id": 0, "created_at": 1, "risk_level": 1, "false_positive_rate_pct": 1},
    ).sort("created_at", 1).to_list(600)

    by_day = {}
    for item in assessments:
        day_key = str(item.get("created_at") or now.isoformat())[:10]
        slot = by_day.setdefault(day_key, {"attempts": 0, "blocked": 0, "false_positives": 0})
        slot["attempts"] += 1
        if str(item.get("risk_level") or "low").lower() in {"high", "critical"}:
            slot["blocked"] += 1
        if float(item.get("false_positive_rate_pct") or 0) >= 10:
            slot["false_positives"] += 1

    fraud_trend = []
    for offset in range(6, -1, -1):
        date_key = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        slot = by_day.get(date_key, {"attempts": 0, "blocked": 0, "false_positives": 0})
        fraud_trend.append({"date": date_key, **slot})

    all_profiles = await db.progressive_risk_profiles.find({}, {"_id": 0, "risk_score": 1}).to_list(400)
    avg_risk_score = 0.0
    if all_profiles:
        avg_risk_score = round(
            sum(float(item.get("risk_score") or 0) for item in all_profiles) / max(len(all_profiles), 1),
            1,
        )

    overall_level = "Low"
    if avg_risk_score > 80:
        overall_level = "Critical"
    elif avg_risk_score > 60:
        overall_level = "High"
    elif avg_risk_score > 30:
        overall_level = "Medium"

    top_account = high_risk_accounts[0] if high_risk_accounts else None
    output_block = (
        top_account.get("output_block")
        if top_account and top_account.get("output_block")
        else format_risk_engine_output(
            risk_score=int(round(avg_risk_score)),
            risk_level=overall_level.lower(),
            trigger="NO_FRICTION" if avg_risk_score <= 30 else "STEP_UP_MFA" if avg_risk_score <= 60 else "ADMIN_API_BLOCK_AND_MFA" if avg_risk_score <= 80 else "SESSION_LOCK_AND_ID_VERIFICATION",
            false_positive_rate_pct=round(sum(float(item.get("false_positive_rate_pct") or 0) for item in high_risk_accounts) / max(len(high_risk_accounts), 1), 2) if high_risk_accounts else 1.0,
            session_protection="STANDARD_MONITORING" if avg_risk_score <= 30 else "MFA_CHALLENGE" if avg_risk_score <= 60 else "PRIVILEGED_API_CONTAINMENT" if avg_risk_score <= 80 else "SESSION_LOCKDOWN",
            confidence_pct=round(sum(float(item.get("confidence_pct") or 0) for item in high_risk_accounts) / max(len(high_risk_accounts), 1), 1) if high_risk_accounts else 70.0,
        )
    )

    return {
        "security_events_24h": security_events_count,
        "high_risk_accounts": high_risk_accounts,
        "suspicious_transactions": suspicious_transactions,
        "compliance_alerts": compliance_alerts,
        "fraud_trend": fraud_trend,
        "aml_summary": {
            "total_screened": int(await db.afrikpay_aml_flags.count_documents({})),
            "flagged": int(await db.afrikpay_aml_flags.count_documents({"status": {"$in": ["pending_review", "blocked", "flagged"]}})),
            "cleared": int(await db.afrikpay_aml_flags.count_documents({"status": "cleared"})),
            "pending_review": int(aml_pending),
        },
        "overall_risk_score": avg_risk_score,
        "risk_level": overall_level,
        "risk_engine": {
            "status": "ACTIVE",
            "thresholds": {
                "low": "0-30",
                "medium": "31-60",
                "high": "61-80",
                "critical": "81-100",
            },
            "output_block": output_block,
            "last_assessed_at": top_account.get("last_activity") if top_account else now.isoformat(),
            "high_or_critical_accounts": len(high_risk_accounts),
            "security_events_24h": security_events_count,
            "progressive_actions": [
                "LOW (0-30): No friction",
                "MEDIUM (31-60): Step-up MFA",
                "HIGH (61-80): Block admin/privileged APIs + require MFA",
                "CRITICAL (81-100): Lock session + require ID verification",
            ],
        },
    }


class RiskActionRequest(BaseModel):
    user_id: str
    action: str
    reason: str | None = None


@router.post("/admin/executive/risk-actions")
async def run_risk_action(payload: RiskActionRequest, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    target_user_id = str(payload.user_id or "").strip()
    action = str(payload.action or "").strip().lower()
    reason = str(payload.reason or "").strip() or "Action executed from executive risk control"
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    now_iso = datetime.now(timezone.utc).isoformat()
    result_payload = {"action": action, "target_user_id": target_user_id}

    if action == "force_id_verification":
        from routes.id_verification import trigger_risk_based_id_verification

        profile = await db.progressive_risk_profiles.find_one({"user_id": target_user_id}, {"_id": 0}) or {}
        if not profile:
            profile = {
                "risk_engine_status": "ACTIVE",
                "risk_score": 85,
                "risk_level": "critical",
                "trigger": "SESSION_LOCK_AND_ID_VERIFICATION",
                "session_protection": "SESSION_LOCKDOWN",
                "false_positive_rate_pct": 2.0,
                "confidence": 0.88,
                "output_block": format_risk_engine_output(
                    risk_score=85,
                    risk_level="critical",
                    trigger="SESSION_LOCK_AND_ID_VERIFICATION",
                    false_positive_rate_pct=2.0,
                    session_protection="SESSION_LOCKDOWN",
                    confidence_pct=88.0,
                ),
            }
        trigger_result = await trigger_risk_based_id_verification(
            target_user_id,
            profile,
            triggered_by=f"admin:{user.user_id}",
        )
        result_payload["id_verification"] = trigger_result
    elif action == "lock_session":
        deleted = await db.user_sessions.delete_many({"user_id": target_user_id})
        await db.progressive_risk_profiles.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "risk_engine_status": "ACTIVE",
                    "risk_level": "critical",
                    "trigger": "SESSION_LOCK_AND_ID_VERIFICATION",
                    "session_protection": "SESSION_LOCKDOWN",
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        result_payload["sessions_locked"] = int(getattr(deleted, "deleted_count", 0) or 0)
    elif action == "clear_admin_block":
        await db.progressive_risk_profiles.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "manual_override": "allow_admin",
                    "manual_override_reason": reason,
                    "manual_override_by": user.user_id,
                    "manual_override_at": now_iso,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        result_payload["override"] = "allow_admin"
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")

    await log_security_event(
        user.user_id,
        "risk_action_executed",
        "high",
        request,
        {
            "target_user_id": target_user_id,
            "action": action,
            "reason": reason,
        },
    )

    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"risk_action_{os.urandom(4).hex()}",
            "user_id": user.user_id,
            "action": "risk_control_action",
            "metadata": {
                "target_user_id": target_user_id,
                "action": action,
                "reason": reason,
                "path": request.url.path,
                "method": request.method,
            },
            "created_at": now_iso,
        }
    )

    return {"success": True, **result_payload}


@router.get("/admin/executive/global-heatmap")
async def global_heatmap(request: Request):
    """Global heatmap data for world map visualization."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    regions = [
        {
            "code": "NG",
            "name": "Nigeria",
            "lat": 9.08,
            "lng": 7.49,
            "revenue": _trend(35000),
            "users": random.randint(500, 800),
            "fraud_alerts": random.randint(0, 3),
            "trending": "Platform",
        },
        {
            "code": "CM",
            "name": "Cameroon",
            "lat": 3.85,
            "lng": 11.50,
            "revenue": _trend(28000),
            "users": random.randint(400, 600),
            "fraud_alerts": random.randint(0, 2),
            "trending": "Streaming",
        },
        {
            "code": "GH",
            "name": "Ghana",
            "lat": 5.60,
            "lng": -0.19,
            "revenue": _trend(18000),
            "users": random.randint(200, 400),
            "fraud_alerts": random.randint(0, 1),
            "trending": "Creator Exchange",
        },
        {
            "code": "KE",
            "name": "Kenya",
            "lat": -1.29,
            "lng": 36.82,
            "revenue": _trend(22000),
            "users": random.randint(300, 500),
            "fraud_alerts": random.randint(0, 2),
            "trending": "VC Engine",
        },
        {
            "code": "ZA",
            "name": "South Africa",
            "lat": -33.92,
            "lng": 18.42,
            "revenue": _trend(20000),
            "users": random.randint(250, 450),
            "fraud_alerts": random.randint(0, 1),
            "trending": "Digital Bank",
        },
        {
            "code": "SN",
            "name": "Senegal",
            "lat": 14.69,
            "lng": -17.44,
            "revenue": _trend(12000),
            "users": random.randint(150, 300),
            "fraud_alerts": 0,
            "trending": "P2P Lending",
        },
        {
            "code": "CI",
            "name": "Ivory Coast",
            "lat": 5.35,
            "lng": -4.01,
            "revenue": _trend(15000),
            "users": random.randint(200, 350),
            "fraud_alerts": random.randint(0, 1),
            "trending": "Platform",
        },
        {
            "code": "FR",
            "name": "France",
            "lat": 48.86,
            "lng": 2.35,
            "revenue": _trend(8000),
            "users": random.randint(80, 150),
            "fraud_alerts": 0,
            "trending": "Streaming",
        },
        {
            "code": "US",
            "name": "United States",
            "lat": 40.71,
            "lng": -74.01,
            "revenue": _trend(5000),
            "users": random.randint(50, 100),
            "fraud_alerts": 0,
            "trending": "Creator Exchange",
        },
        {
            "code": "GB",
            "name": "United Kingdom",
            "lat": 51.51,
            "lng": -0.13,
            "revenue": _trend(6000),
            "users": random.randint(60, 120),
            "fraud_alerts": 0,
            "trending": "VC Engine",
        },
    ]

    return {
        "regions": regions,
        "total_countries": len(regions),
        "top_revenue_country": max(regions, key=lambda r: r["revenue"])["name"],
        "total_global_revenue": sum(r["revenue"] for r in regions),
    }


@router.get("/admin/executive/user-management")
async def executive_user_management(request: Request, page: int = 1, limit: int = 20, search: str = ""):
    """User management for admin console."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = {}
    if search:
        query["$or"] = [
            {"email": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"name": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    total = await db.users.count_documents(query)
    users_cursor = (
        db.users.find(query, {"_id": 0, "password_hash": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    users_list = []
    async for u in users_cursor:
        u.pop("_id", None)
        u.pop("password_hash", None)
        if "created_at" in u and hasattr(u["created_at"], "isoformat"):
            u["created_at"] = u["created_at"].isoformat()
        if "updated_at" in u and hasattr(u["updated_at"], "isoformat"):
            u["updated_at"] = u["updated_at"].isoformat()
        if "last_login" in u and hasattr(u["last_login"], "isoformat"):
            u["last_login"] = u["last_login"].isoformat()
        users_list.append(u)

    return {
        "users": users_list,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/admin/executive/templates")
async def get_template_previews(request: Request):
    """Admin-only: Return all email template previews with sample data."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import get_all_template_previews, get_editable_fields

    # Load saved overrides from DB
    overrides_cursor = db.template_overrides.find({}, {"_id": 0})
    saved = {doc["key"]: doc for doc in await overrides_cursor.to_list(100)}

    templates = get_all_template_previews(saved)

    categories = {}
    for t in templates:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t)

    return {
        "total": len(templates),
        "categories": categories,
        "templates": templates,
        "editable_fields": get_editable_fields(),
    }


@router.get("/admin/executive/templates/analytics/summary")
async def get_template_analytics(request: Request, period: str = "all"):
    """Admin-only: Get email delivery analytics aggregated per template with optional date filter."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import TEMPLATE_CATALOG
    from datetime import datetime, timedelta, timezone

    date_filter = {}
    period_days = {"7d": 7, "30d": 30, "90d": 90}
    if period in period_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days[period])
        cutoff_iso = cutoff.isoformat()
        date_filter = {"sent_at": {"$gte": cutoff_iso}}

    sends_pipeline = []
    if date_filter:
        sends_pipeline.append({"$match": date_filter})
    sends_pipeline.append({"$group": {"_id": "$template_key", "sent": {"$sum": 1}, "last_sent": {"$max": "$sent_at"}}})
    sends_agg = {doc["_id"]: doc async for doc in db.email_sends.aggregate(sends_pipeline) if doc["_id"]}

    events_match = {"template_key": {"$exists": True, "$ne": ""}}
    if period in period_days:
        events_match["received_at"] = {"$gte": cutoff_iso}

    events_pipeline = [
        {"$match": events_match},
        {"$group": {"_id": {"template_key": "$template_key", "event": "$event"}, "count": {"$sum": 1}}},
    ]
    events_raw = [doc async for doc in db.email_events.aggregate(events_pipeline)]

    events_agg: dict = {}
    for doc in events_raw:
        eid = doc.get("_id", {})
        tk = eid.get("template_key", "")
        ev = eid.get("event", "")
        if not tk or not ev:
            continue
        if tk not in events_agg:
            events_agg[tk] = {}
        ev_short = ev.replace("email.", "") if ev.startswith("email.") else ev
        events_agg[tk][ev_short] = doc["count"]

    total_match = {}
    if period in period_days:
        total_match = {"received_at": {"$gte": cutoff_iso}}
    total_pipeline = []
    if total_match:
        total_pipeline.append({"$match": total_match})
    total_pipeline.append({"$group": {"_id": "$event", "count": {"$sum": 1}}})
    total_events = {}
    async for doc in db.email_events.aggregate(total_pipeline):
        ev = doc["_id"].replace("email.", "") if doc["_id"].startswith("email.") else doc["_id"]
        total_events[ev] = doc["count"]

    total_sends = (
        await db.email_sends.count_documents(date_filter) if date_filter else await db.email_sends.count_documents({})
    )

    per_template = []
    for tpl_key, info in TEMPLATE_CATALOG.items():
        s = sends_agg.get(tpl_key, {})
        e = events_agg.get(tpl_key, {})
        sent = s.get("sent", 0)
        delivered = e.get("delivered", 0)
        opened = e.get("opened", 0)
        clicked = e.get("clicked", 0)
        bounced = e.get("bounced", 0)
        complained = e.get("complained", 0)
        per_template.append(
            {
                "key": tpl_key,
                "label": info["label"],
                "category": info["category"],
                "sent": sent,
                "delivered": delivered,
                "opened": opened,
                "clicked": clicked,
                "bounced": bounced,
                "complained": complained,
                "open_rate": round((opened / delivered * 100), 1) if delivered > 0 else 0,
                "click_rate": round((clicked / delivered * 100), 1) if delivered > 0 else 0,
                "bounce_rate": round((bounced / sent * 100), 1) if sent > 0 else 0,
                "last_sent": s.get("last_sent", ""),
            }
        )
    per_template.sort(key=lambda x: x["sent"], reverse=True)

    return {"total_sends": total_sends, "total_events": total_events, "per_template": per_template, "period": period}


@router.get("/admin/executive/templates/{key}")
async def get_single_template(request: Request, key: str):
    """Admin-only: Get a single template with its override."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import render_template_with_overrides, TEMPLATE_CATALOG, get_editable_fields

    if key not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail="Template not found")

    override = await db.template_overrides.find_one({"key": key}, {"_id": 0})
    result = render_template_with_overrides(key, override or {})
    result["overrides"] = override or {}
    result["has_override"] = bool(override)
    result["editable_fields"] = get_editable_fields()
    return result


@router.put("/admin/executive/templates/{key}")
async def save_template_override(request: Request, key: str):
    """Admin-only: Save customizations for a template."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import TEMPLATE_CATALOG

    if key not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail="Template not found")

    body = await request.json()
    allowed_keys = {"subject", "header_title", "accent_color", "cta_label", "cta_url", "footer_text"}
    overrides = {k: v for k, v in body.items() if k in allowed_keys and v}

    if not overrides:
        raise HTTPException(status_code=400, detail="No valid override fields provided")

    now = datetime.now(timezone.utc).isoformat()
    await db.template_overrides.update_one(
        {"key": key},
        {"$set": {**overrides, "key": key, "updated_at": now, "updated_by": user.user_id}},
        upsert=True,
    )
    return {"success": True, "key": key, "overrides": overrides}


@router.delete("/admin/executive/templates/{key}")
async def reset_template_override(request: Request, key: str):
    """Admin-only: Reset a template to default (remove overrides)."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.template_overrides.delete_one({"key": key})
    return {"success": True, "key": key, "deleted": result.deleted_count > 0}


@router.post("/admin/executive/templates/{key}/preview")
async def preview_template_with_overrides(request: Request, key: str):
    """Admin-only: Live preview — render template with provided overrides without saving."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import render_template_with_overrides, TEMPLATE_CATALOG

    if key not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail="Template not found")

    body = await request.json()
    result = render_template_with_overrides(key, body)
    return result


@router.post("/admin/executive/templates/{key}/send-test")
async def send_test_email(request: Request, key: str):
    """Admin-only: Send a test email of the template to the admin's own email."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from utils.email_templates import render_template_with_overrides, TEMPLATE_CATALOG
    from utils.email_service import send_email, is_email_configured

    if key not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail="Template not found")
    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service not configured")

    body = await request.json()
    overrides = {
        k: v
        for k, v in body.items()
        if k in {"subject", "header_title", "accent_color", "cta_label", "cta_url", "footer_text"} and v
    }
    result = render_template_with_overrides(key, overrides)

    admin_email = getattr(user, "email", "")
    if not admin_email:
        raise HTTPException(status_code=400, detail="No email on admin account")

    send_result = await send_email(
        recipient_email=admin_email,
        subject=f"[TEST] {result['subject']}",
        content=result["html"],
        recipient_name=getattr(user, "name", "Admin"),
        template_key=key,
    )

    if send_result.get("success"):
        return {"success": True, "sent_to": admin_email, "subject": result["subject"]}
    return {"success": False, "error": send_result.get("error", "Unknown error")}


@router.get("/admin/executive/security-score")
async def security_score(request: Request):
    """Compute a 0-100 security health score from SIEM data."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    day_str = (now - timedelta(days=1)).isoformat()
    week_str = (now - timedelta(days=7)).isoformat()

    # Gather raw metrics
    critical_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}, "risk_level": "critical"})
    high_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}, "risk_level": "high"})
    medium_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}, "risk_level": "medium"})
    failed_logins_24h = await db.security_events.count_documents(
        {"timestamp": {"$gte": day_str}, "event_type": "login_failed"}
    )
    active_alerts = await db.security_alerts.count_documents({"status": {"$in": ["active", "open", "pending"]}})
    events_7d = await db.security_events.count_documents({"timestamp": {"$gte": week_str}})

    # Previous week for trend comparison
    prev_week_str = (now - timedelta(days=14)).isoformat()
    events_prev_7d = await db.security_events.count_documents({"timestamp": {"$gte": prev_week_str, "$lt": week_str}})

    # Score calculation: start at 100, deduct for issues
    score = 100
    score -= min(critical_24h * 15, 40)  # Critical events: -15 each, max -40
    score -= min(high_24h * 5, 20)  # High events: -5 each, max -20
    score -= min(medium_24h * 1, 10)  # Medium events: -1 each, max -10
    score -= min(failed_logins_24h * 2, 15)  # Failed logins: -2 each, max -15
    score -= min(active_alerts * 5, 15)  # Active alerts: -5 each, max -15
    score = max(score, 0)

    # Determine grade and status
    if score >= 90:
        grade, status = "A", "Excellent"
    elif score >= 75:
        grade, status = "B", "Good"
    elif score >= 60:
        grade, status = "C", "Fair"
    elif score >= 40:
        grade, status = "D", "At Risk"
    else:
        grade, status = "F", "Critical"

    # Trend: compare this week vs last week
    trend_pct = round(((events_7d - events_prev_7d) / max(events_prev_7d, 1)) * 100, 1)

    # Breakdown factors
    factors = [
        {
            "label": "Critical Events (24h)",
            "value": critical_24h,
            "impact": min(critical_24h * 15, 40),
            "severity": "critical",
        },
        {"label": "High Events (24h)", "value": high_24h, "impact": min(high_24h * 5, 20), "severity": "high"},
        {"label": "Medium Events (24h)", "value": medium_24h, "impact": min(medium_24h * 1, 10), "severity": "medium"},
        {
            "label": "Failed Logins (24h)",
            "value": failed_logins_24h,
            "impact": min(failed_logins_24h * 2, 15),
            "severity": "medium",
        },
        {"label": "Active Alerts", "value": active_alerts, "impact": min(active_alerts * 5, 15), "severity": "high"},
    ]

    return {
        "score": score,
        "grade": grade,
        "status": status,
        "trend_pct": trend_pct,
        "events_7d": events_7d,
        "events_prev_7d": events_prev_7d,
        "factors": factors,
    }


@router.get("/admin/executive/admin-surface-watchdog")
async def admin_surface_watchdog(request: Request):
    """Latest in-app watchdog snapshot for admin-only route/tab health."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return _extract_admin_surface_watchdog_snapshot()




# ════════════════════════════════════════════════════════════
# FEEDBACK HEATMAP & ROUTE-BY-ROUTE FRICTION LEADERBOARD
# ════════════════════════════════════════════════════════════

@router.get("/admin/executive/feedback-heatmap")
async def feedback_heatmap(request: Request):
    """Admin-only: Return a route-by-route feedback heatmap with friction scores
    computed from error rates, session replays, vitals, and user feedback signals."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    days = int(request.query_params.get("days", "7"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    # Aggregate errors per route from vitals/session replays
    vitals_pipeline = [
        {"$match": {"created_at": {"$gte": cutoff_iso}}},
        {"$group": {
            "_id": "$route",
            "visits": {"$sum": 1},
            "errors": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$error_count", 0]}, 0]}, 1, 0]}},
            "avg_lcp": {"$avg": {"$ifNull": ["$lcp", None]}},
            "avg_fid": {"$avg": {"$ifNull": ["$fid", None]}},
            "avg_cls": {"$avg": {"$ifNull": ["$cls", None]}},
            "bounce_count": {"$sum": {"$cond": [{"$lte": [{"$ifNull": ["$session_duration", 999]}, 5]}, 1, 0]}},
        }},
        {"$sort": {"visits": -1}},
        {"$limit": 50},
    ]

    try:
        vitals_data = await db.web_vitals.aggregate(vitals_pipeline).to_list(50)
    except Exception:
        vitals_data = []

    # Aggregate AI feedback per route
    feedback_pipeline = [
        {"$match": {"created_at": {"$gte": cutoff_iso}}},
        {"$group": {
            "_id": "$route",
            "total_feedback": {"$sum": 1},
            "negative": {"$sum": {"$cond": [{"$in": ["$sentiment", ["negative", "bad", "frustrated"]]}, 1, 0]}},
            "positive": {"$sum": {"$cond": [{"$in": ["$sentiment", ["positive", "good", "happy"]]}, 1, 0]}},
            "avg_rating": {"$avg": {"$ifNull": ["$rating", None]}},
        }},
    ]
    try:
        feedback_data = await db.ai_feedback.aggregate(feedback_pipeline).to_list(50)
    except Exception:
        feedback_data = []
    feedback_map = {r["_id"]: r for r in feedback_data if r["_id"]}

    # Aggregate contact submissions (friction signal) per context/route
    support_pipeline = [
        {"$match": {"created_at": {"$gte": cutoff_iso}}},
        {"$group": {
            "_id": {"$ifNull": ["$context", "unknown"]},
            "ticket_count": {"$sum": 1},
            "high_priority": {"$sum": {"$cond": [{"$eq": ["$priority", "high"]}, 1, 0]}},
        }},
    ]
    try:
        support_data = await db.contact_submissions.aggregate(support_pipeline).to_list(50)
    except Exception:
        support_data = []
    support_map = {r["_id"]: r for r in support_data if r["_id"]}

    # Build friction leaderboard
    heatmap = []
    for v in vitals_data:
        route = v["_id"] or "/"
        visits = v.get("visits", 0)
        errors = v.get("errors", 0)
        fb = feedback_map.get(route, {})
        sp = support_map.get(route, {})

        # Friction score: higher is worse (0-100)
        error_rate = (errors / max(visits, 1)) * 100
        bounce_rate = (v.get("bounce_count", 0) / max(visits, 1)) * 100
        neg_rate = (fb.get("negative", 0) / max(fb.get("total_feedback", 1), 1)) * 100
        ticket_pressure = min(sp.get("ticket_count", 0) * 10, 30)

        friction = round(min(
            error_rate * 0.35 +
            bounce_rate * 0.25 +
            neg_rate * 0.25 +
            ticket_pressure * 0.15,
            100
        ), 1)

        heatmap.append({
            "route": route,
            "visits": visits,
            "errors": errors,
            "error_rate": round(error_rate, 1),
            "bounce_rate": round(bounce_rate, 1),
            "avg_lcp_ms": round(v.get("avg_lcp") or 0, 0),
            "avg_fid_ms": round(v.get("avg_fid") or 0, 0),
            "avg_cls": round(v.get("avg_cls") or 0, 3),
            "feedback_count": fb.get("total_feedback", 0),
            "negative_feedback": fb.get("negative", 0),
            "positive_feedback": fb.get("positive", 0),
            "avg_rating": round(fb.get("avg_rating") or 0, 1) if fb.get("avg_rating") else None,
            "support_tickets": sp.get("ticket_count", 0),
            "high_priority_tickets": sp.get("high_priority", 0),
            "friction_score": friction,
            "friction_grade": "A" if friction < 10 else "B" if friction < 25 else "C" if friction < 50 else "D" if friction < 75 else "F",
        })

    heatmap.sort(key=lambda r: r["friction_score"], reverse=True)

    # Top friction routes
    top_friction = heatmap[:10]

    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_routes": len(heatmap),
        "top_friction_routes": top_friction,
        "heatmap": heatmap,
        "summary": {
            "avg_friction": round(sum(r["friction_score"] for r in heatmap) / max(len(heatmap), 1), 1),
            "routes_grade_a": sum(1 for r in heatmap if r["friction_grade"] == "A"),
            "routes_grade_f": sum(1 for r in heatmap if r["friction_grade"] == "F"),
            "total_errors": sum(r["errors"] for r in heatmap),
            "total_negative_feedback": sum(r["negative_feedback"] for r in heatmap),
            "total_support_tickets": sum(r["support_tickets"] for r in heatmap),
        },
    }
