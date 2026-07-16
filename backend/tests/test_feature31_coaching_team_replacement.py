"""Feature 31 replacement contract — Problem Solver retired, AI Coaching Team live.

Pure logic checks (no HTTP): entitlement catalog, retirement payload,
feature registry slot, and coach curation.
"""

from routes.ai_problem_solver import RETIREMENT_PAYLOAD
from routes.ai_coaching_team import COACH_KEYS, FREE_TIER_COACHES


def test_retirement_payload_contract():
    assert RETIREMENT_PAYLOAD["retired"] is True
    assert RETIREMENT_PAYLOAD["feature"] == "ai-problem-solver"
    assert RETIREMENT_PAYLOAD["feature_number"] == 31
    assert RETIREMENT_PAYLOAD["replacement_feature"] == "ai-coaching-team"
    assert RETIREMENT_PAYLOAD["replacement_route"] == "/ai-coaching-team"
    assert RETIREMENT_PAYLOAD["replacement_api"] == "/api/ai-coaching-team"


def test_coach_curation():
    assert COACH_KEYS == ["career_coach", "interview_coach", "resume_specialist", "negotiation_coach"]
    assert FREE_TIER_COACHES == {"career_coach"}


def test_entitlements_catalog_swapped():
    import utils.access_control_engine as ace

    catalog_src = open(ace.__file__).read()
    assert "coaching_team_daily_messages" in catalog_src
    assert "problem_solver_daily_runs" not in catalog_src
    ent_free = ace.build_feature_entitlements("free")
    assert ent_free.get("coaching_team_daily_messages") == 5
    assert ent_free.get("coaching_team_all_coaches") is False
    ent_premium = ace.build_feature_entitlements("premium")
    assert ent_premium.get("coaching_team_daily_messages") == -1
    assert ent_premium.get("coaching_team_all_coaches") is True


def test_feature_registry_slot_31():
    from routes.feature_registry import LOCKED_CANONICAL_FEATURE_ORDER, CORE_SIDENAV_FEATURE_DEFAULTS

    slot = next(f for f in LOCKED_CANONICAL_FEATURE_ORDER if int(f["feature_number"]) == 31)
    assert slot["feature_id"] == "ai-coaching-team"
    card = next(f for f in CORE_SIDENAV_FEATURE_DEFAULTS if f["feature_id"] == "ai-coaching-team")
    assert card["route"] == "/ai-coaching-team"
    assert card["premium"] is True
    assert not any(f["feature_id"] == "ai-problem-solver" for f in CORE_SIDENAV_FEATURE_DEFAULTS)


def test_scheduler_job_removed():
    scheduler_src = open("/app/backend/scheduler.py").read()
    assert "feature31_playbook_auto_run_loop" not in scheduler_src
    assert "run_scheduled_playbook_auto_loops" not in scheduler_src
