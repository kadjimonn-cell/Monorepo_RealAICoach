import requests


def test_admin_only_contracts(
    base_url: str,
    free_session: requests.Session,
    admin_session: requests.Session,
    set_controls_fn,
):
    base = base_url

    free_readiness = free_session.get(f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness", timeout=30)
    assert free_readiness.status_code == 403

    free_controls = free_session.post(
        f"{base}/api/videos/admin/legacy-wrapper-retirement-controls",
        json={"legacy_retirement_enabled": False},
        timeout=30,
    )
    assert free_controls.status_code == 403

    free_removal = free_session.get(f"{base}/api/videos/admin/legacy-wrapper-removal-readiness", timeout=30)
    assert free_removal.status_code == 403

    free_hard_delete = free_session.post(
        f"{base}/api/videos/admin/legacy-wrapper-hard-delete",
        json={"lookback_hours": 168, "route_families": ["audio_studio"]},
        timeout=30,
    )
    assert free_hard_delete.status_code == 403

    admin_readiness = admin_session.get(f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness", timeout=30)
    assert admin_readiness.status_code == 200
    readiness_data = admin_readiness.json()
    assert "retirement_phase" in readiness_data
    assert "family_readiness" in readiness_data

    admin_controls = set_controls_fn(
        admin_session,
        {
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe",
            "retirement_force_apply": False,
        },
    )
    assert admin_controls.status_code == 200
    controls_data = admin_controls.json()
    assert controls_data.get("success") is True


def test_governance_payload_shape(base_url: str, admin_session: requests.Session):
    base = base_url

    readiness = admin_session.get(
        f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness",
        params={"lookback_hours": 168},
        timeout=45,
    )
    assert readiness.status_code == 200
    payload = readiness.json()

    assert payload.get("feature_number") == 28
    assert payload.get("feature_id") == "watch-videos-audio-podcasts"
    assert isinstance(payload.get("family_readiness"), list)

    family_rows = payload.get("family_readiness") or []
    assert len(family_rows) == 2
    for row in family_rows:
        assert "route_family" in row
        assert "gate_thresholds" in row
        assert "operational_gate" in row
        assert "telemetry_scaffold" in row
