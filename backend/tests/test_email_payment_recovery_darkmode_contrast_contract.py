from pathlib import Path


EMAIL_TEMPLATES_PATH = Path('/app/backend/utils/email_templates.py')


def test_payment_recovery_tip_uses_light_locked_card_helper() -> None:
    source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')

    assert 'def _light_locked_tip_card(' in source
    assert 'build_recovery_email_day1' in source
    assert '_light_locked_tip_card(' in source


def test_payment_recovery_no_legacy_em_tip_box_markup_in_day1_template() -> None:
    source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')

    start = source.index('def build_recovery_email_day1(')
    end = source.index('def build_recovery_email_day3(')
    day1_block = source[start:end]

    assert 'class="em-tip-box"' not in day1_block
    assert 'class="em-tip-title"' not in day1_block
    assert 'class="em-tip-list"' not in day1_block


def test_light_locked_tip_card_uses_force_light_classes() -> None:
    source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')

    helper_start = source.index('def _light_locked_tip_card(')
    helper_end = source.index('def _alert_panel(')
    helper_block = source[helper_start:helper_end]

    assert 'em-force-light-card' in helper_block
    assert 'em-force-dark-text' in helper_block
    assert 'em-force-muted-text' in helper_block
