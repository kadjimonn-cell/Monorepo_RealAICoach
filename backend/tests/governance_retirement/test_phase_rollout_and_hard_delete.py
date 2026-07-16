import requests


def test_phase_promotions_without_force_and_hard_delete(
    base_url: str,
    free_session: requests.Session,
    admin_session: requests.Session,
    set_controls_fn,
    current_user_id_fn,
):
    base = base_url
    override_user = current_user_id_fn(free_session)
    assert override_user

    # Generate telemetry from known test user
    free_session.get(f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45)
    free_session.get(f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45)

    observe = set_controls_fn(
        admin_session,
        {
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe",
            "retirement_force_apply": False,
            "retirement_gate_lookback_hours": 168,
            "retirement_gate_max_events": 0,
            "retirement_gate_max_active_users": 0,
            "retirement_override_user_ids": [override_user],
        },
    )
    assert observe.status_code == 200

    phase1 = set_controls_fn(
        admin_session,
        {
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase1_audio_wrappers",
            "retirement_force_apply": False,
            "retirement_gate_lookback_hours": 168,
            "retirement_gate_max_events": 0,
            "retirement_gate_max_active_users": 0,
            "retirement_override_user_ids": [override_user],
        },
    )
    assert phase1.status_code == 200

    phase2 = set_controls_fn(
        admin_session,
        {
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase2_audio_podcasts_wrappers",
            "retirement_force_apply": False,
            "retirement_gate_lookback_hours": 168,
            "retirement_gate_max_events": 0,
            "retirement_gate_max_active_users": 0,
            "retirement_override_user_ids": [override_user],
        },
    )
    assert phase2.status_code == 200

    removal_readiness = admin_session.get(
        f"{base}/api/videos/admin/legacy-wrapper-removal-readiness",
        params={"lookback_hours": 168},
        timeout=45,
    )
    assert removal_readiness.status_code == 200
    readiness_payload = removal_readiness.json()
    assert readiness_payload.get("strict_zero_operational_ready") is True

    hard_delete = admin_session.post(
        f"{base}/api/videos/admin/legacy-wrapper-hard-delete",
        json={"lookback_hours": 168, "route_families": ["audio_studio", "podcasts"]},
        timeout=45,
    )
    assert hard_delete.status_code == 200
    hard_payload = hard_delete.json()
    assert hard_payload.get("hard_delete_ready") is True
    assert set(hard_payload.get("hard_deleted_families") or []) == {"audio_studio", "podcasts"}


def test_post_hard_delete_runtime_contract(base_url: str, free_session: requests.Session):
    base = base_url

    assert free_session.get(f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45).status_code == 404
    assert free_session.get(f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45).status_code == 404
    assert free_session.get(f"{base}/api/videos/sports/bootstrap", params={"tz": "UTC"}, timeout=45).status_code in {404, 403, 410}

    assert free_session.get(f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45).status_code == 200
    assert free_session.get(f"{base}/api/podcasts/v2/bootstrap", params={"tz": "UTC"}, timeout=45).status_code == 200
    assert free_session.get(f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45).status_code == 200
