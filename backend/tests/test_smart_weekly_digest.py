"""Smart Weekly Digest — template render + aggregation contract tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.email_templates import TEMPLATE_CATALOG, build_smart_weekly_digest_email


def test_template_registered_in_catalog():
    assert "smart_weekly_digest" in TEMPLATE_CATALOG
    entry = TEMPLATE_CATALOG["smart_weekly_digest"]
    assert entry["category"] == "Engagement"


def test_default_render_has_chrome_and_v7_markers():
    tpl = build_smart_weekly_digest_email()
    html = tpl.html
    assert "data-theme-light" in html and "data-theme-dark" in html
    assert "email-header-wordmark" in html
    assert "email-header-trust" in html
    assert 'data-global-footer-component="realaicoach-global-email-footer"' in html
    assert "prefers-color-scheme:dark" in html
    assert "[data-ogsc]" in html
    assert "@media only screen and (max-width:479px)" in html


def test_streak_and_stats_render():
    tpl = build_smart_weekly_digest_email(
        user_name="Jordan",
        streak_days=9,
        longest_streak=14,
        active_day_map=[True, False, True, True, True, False, True],
        sessions=6,
        active_days=5,
        xp_earned=480,
        total_xp=3210,
        highlights=["Did a mock interview", "Improved leadership score"],
        smart_tip="Book a mock interview before Thursday.",
        week_label="Week of Jul 06 – Jul 12, 2026",
    )
    html = tpl.html
    assert "9-DAY STREAK" in html
    assert "Personal best: 14 days" in html
    assert "Coaching Sessions" in html and ">6<" in html
    assert "+480" in html
    assert "3,210" in html
    assert "Did a mock interview" in html
    assert "Book a mock interview before Thursday." in html
    assert "Keep Your Streak Alive" in html
    assert "Week of Jul 06" in html
    assert "Jordan, your 9-day streak" in tpl.subject
    # 5 filled ✓ dots for 5 active days
    assert html.count("&#10003;") >= 5 or html.count("\u2713") >= 5


def test_zero_streak_fallback_copy():
    tpl = build_smart_weekly_digest_email(user_name="Sam", streak_days=0, active_day_map=[False] * 7, sessions=0, active_days=0, xp_earned=0)
    assert "START A NEW STREAK" in tpl.html
    assert "Sam, your week in review" in tpl.subject


def test_text_fallback_contains_stats():
    tpl = build_smart_weekly_digest_email(streak_days=3, sessions=2, xp_earned=100)
    assert "Streak: 3 days" in tpl.text
    assert "Sessions: 2" in tpl.text
