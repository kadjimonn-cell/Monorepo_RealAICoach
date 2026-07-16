from pathlib import Path


def test_google_auth_is_stable_range_not_dev_prerelease() -> None:
    content = Path("/app/backend/requirements.txt").read_text(encoding="utf-8")
    assert "google-auth==2.49.0.dev0" not in content
    assert "google-auth>=2.38.0,<3.0" in content
