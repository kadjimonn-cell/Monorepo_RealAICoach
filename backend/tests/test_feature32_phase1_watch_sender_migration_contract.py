from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_watch_videos_drop_sender_uses_dispatch_reservation_before_reminder() -> None:
    source = _read("/app/backend/routes/watch_videos.py")
    assert "from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status" in source
    assert "dedupe_key = f\"watch-videos-drop:{drop_hash}:{email_normalized}\"" in source
    assert "reserved = await reserve_dispatch_once(" in source
    assert "dedupe_key=dedupe_key," in source
    assert "result = await notify.reminder(" in source
    assert "await mark_dispatch_status(" in source


def test_watch_audio_drop_and_followed_release_senders_use_dispatch_reservation() -> None:
    source = _read("/app/backend/routes/watch_audio_shared.py")
    assert "from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status" in source
    assert "dedupe_key = f\"{str(cfg.get('feature_id') or 'audio')}:{reminder_type}:{drop_hash}:{email_normalized}\"" in source
    assert "dedupe_key = f\"followed-artist-release:{str(job.get('user_id') or '')}:{item_key}:{email_normalized}\"" in source
    assert "dedupe_key = f\"followed-league-release:{str(job.get('user_id') or '')}:{item_key}:{email_normalized}\"" in source
    assert "dedupe_key = f\"sports_pre_kickoff_15:{user.user_id}:{item_key}:{email_normalized}\"" in source
    assert "reserved = await reserve_dispatch_once(" in source
    assert "await mark_dispatch_status(" in source