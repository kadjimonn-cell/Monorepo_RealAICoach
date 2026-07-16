from pathlib import Path


BACKEND_SOURCE = Path("/app/backend/routes/admin_subscription_analytics.py")
HOME_HERO_SOURCE = Path("/app/frontend/src/components/home/HomeHero.tsx")
WELCOME_METRICS_SOURCE = Path("/app/frontend/src/components/welcome/WelcomeMetrics.tsx")
EXEC_REVENUE_SOURCE = Path("/app/frontend/src/components/executive/RevenueBillingEnterpriseWorkspace.tsx")


def test_admin_subscription_analytics_exposes_live_online_users_kpi() -> None:
    source = BACKEND_SOURCE.read_text(encoding="utf-8")

    assert 'online_user_ids = await db.user_sessions.distinct("user_id", active_session_filter)' in source
    assert '"online_users_live": online_users_live' in source


def test_public_surfaces_keep_existing_active_total_metric_sources() -> None:
    home_source = HOME_HERO_SOURCE.read_text(encoding="utf-8")
    welcome_source = WELCOME_METRICS_SOURCE.read_text(encoding="utf-8")

    assert "stats.active_users" in home_source
    assert "vanity?.active_users" in welcome_source


def test_executive_revenue_renders_live_online_users_card() -> None:
    source = EXEC_REVENUE_SOURCE.read_text(encoding="utf-8")

    assert 'label="Online Users (Live)"' in source
    assert "kpis.online_users_live" in source
    assert 'testId="kpi-online-users-live"' in source
