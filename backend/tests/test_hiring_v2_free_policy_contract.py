from pathlib import Path


def test_hiring_v2_in_free_patterns_access_control_engine() -> None:
    source = Path('/app/backend/utils/access_control_engine.py').read_text(encoding='utf-8')
    assert 'r"^/api/hiring/v2/"' in source
