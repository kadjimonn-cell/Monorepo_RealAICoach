from pathlib import Path


def test_feature30_route_points_to_dedicated_component():
    source = Path('/app/frontend/app/features/sports.tsx').read_text(encoding='utf-8')
    assert 'import SportsFeature30 from' in source
    assert '<SportsFeature30 />' in source
    assert 'AudioCatalogTab mode="sports"' not in source


def test_feature30_dedicated_component_has_no_manual_text_or_upload():
    source = Path('/app/frontend/src/components/feature30/SportsFeature30.tsx').read_text(encoding='utf-8')
    assert 'TextInput' not in source
    assert 'input type="file"' not in source
    assert '/upload' not in source
    assert 'no uploads' in source.lower()
    assert 'sports-v2-matchday-streak-card' in source
    assert 'sports-v2-prediction-challenges-card' in source


def test_feature30_bootstrap_contract_enforces_no_manual_and_no_upload():
    source = Path('/app/backend/routes/sports_v2_bootstrap_service.py').read_text(encoding='utf-8')
    assert '"no_manual_input": True' in source
    assert '"no_upload": True' in source
