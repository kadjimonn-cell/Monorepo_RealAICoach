"""
Payment Recovery Day1 Email Dark-Mode Contrast Fix Verification Tests

Tests:
- Static source verification: _light_locked_tip_card helper exists and uses force-light classes
- No legacy em-tip-box/title/list markup in day1 template
- Runtime verification: rendered HTML contains em-force-light-card classes
- V7 compliance contracts remain intact
"""

import os
import pytest
from pathlib import Path

# Import the email template builder for runtime verification
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.email_templates import build_recovery_email_day1, _light_locked_tip_card

EMAIL_TEMPLATES_PATH = Path('/app/backend/utils/email_templates.py')


class TestStaticSourceVerification:
    """Static source verification for dark-mode contrast fix"""
    
    def test_light_locked_tip_card_helper_exists(self):
        """Verify _light_locked_tip_card helper function is defined"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        assert 'def _light_locked_tip_card(' in source, \
            "_light_locked_tip_card helper function should be defined"
    
    def test_light_locked_tip_card_uses_em_force_light_card(self):
        """Verify helper uses em-force-light-card class for dark-mode safety"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        # Find the helper function block
        helper_start = source.index('def _light_locked_tip_card(')
        helper_end = source.index('def _alert_panel(')
        helper_block = source[helper_start:helper_end]
        
        assert 'em-force-light-card' in helper_block, \
            "_light_locked_tip_card should use em-force-light-card class"
    
    def test_light_locked_tip_card_uses_em_force_dark_text(self):
        """Verify helper uses em-force-dark-text class for title"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        helper_start = source.index('def _light_locked_tip_card(')
        helper_end = source.index('def _alert_panel(')
        helper_block = source[helper_start:helper_end]
        
        assert 'em-force-dark-text' in helper_block, \
            "_light_locked_tip_card should use em-force-dark-text class for title"
    
    def test_light_locked_tip_card_uses_em_force_muted_text(self):
        """Verify helper uses em-force-muted-text class for list items"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        helper_start = source.index('def _light_locked_tip_card(')
        helper_end = source.index('def _alert_panel(')
        helper_block = source[helper_start:helper_end]
        
        assert 'em-force-muted-text' in helper_block, \
            "_light_locked_tip_card should use em-force-muted-text class for list items"
    
    def test_day1_template_calls_light_locked_tip_card(self):
        """Verify build_recovery_email_day1 calls _light_locked_tip_card"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        # Find the day1 function block
        day1_start = source.index('def build_recovery_email_day1(')
        day1_end = source.index('def build_recovery_email_day3(')
        day1_block = source[day1_start:day1_end]
        
        assert '_light_locked_tip_card(' in day1_block, \
            "build_recovery_email_day1 should call _light_locked_tip_card helper"


class TestNoLegacyMarkup:
    """Verify legacy em-tip-box/title/list markup is NOT used in day1 template"""
    
    def test_no_em_tip_box_class_in_day1(self):
        """Verify day1 template does not use legacy em-tip-box class"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        day1_start = source.index('def build_recovery_email_day1(')
        day1_end = source.index('def build_recovery_email_day3(')
        day1_block = source[day1_start:day1_end]
        
        assert 'class="em-tip-box"' not in day1_block, \
            "day1 template should NOT use legacy em-tip-box class"
    
    def test_no_em_tip_title_class_in_day1(self):
        """Verify day1 template does not use legacy em-tip-title class"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        day1_start = source.index('def build_recovery_email_day1(')
        day1_end = source.index('def build_recovery_email_day3(')
        day1_block = source[day1_start:day1_end]
        
        assert 'class="em-tip-title"' not in day1_block, \
            "day1 template should NOT use legacy em-tip-title class"
    
    def test_no_em_tip_list_class_in_day1(self):
        """Verify day1 template does not use legacy em-tip-list class"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        day1_start = source.index('def build_recovery_email_day1(')
        day1_end = source.index('def build_recovery_email_day3(')
        day1_block = source[day1_start:day1_end]
        
        assert 'class="em-tip-list"' not in day1_block, \
            "day1 template should NOT use legacy em-tip-list class"


class TestRuntimeRenderedHTML:
    """Runtime verification: rendered HTML contains correct classes"""
    
    def test_rendered_day1_contains_em_force_light_card(self):
        """Verify rendered day1 HTML contains em-force-light-card class"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert 'em-force-light-card' in template.html, \
            "Rendered day1 HTML should contain em-force-light-card class"
    
    def test_rendered_day1_contains_em_force_dark_text(self):
        """Verify rendered day1 HTML contains em-force-dark-text class"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert 'em-force-dark-text' in template.html, \
            "Rendered day1 HTML should contain em-force-dark-text class"
    
    def test_rendered_day1_contains_em_force_muted_text(self):
        """Verify rendered day1 HTML contains em-force-muted-text class"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert 'em-force-muted-text' in template.html, \
            "Rendered day1 HTML should contain em-force-muted-text class"
    
    def test_rendered_day1_contains_how_to_fix_title(self):
        """Verify rendered day1 HTML contains 'How to fix this quickly' tip title"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert 'How to fix this quickly' in template.html, \
            "Rendered day1 HTML should contain 'How to fix this quickly' tip title"
    
    def test_rendered_day1_no_legacy_em_tip_box(self):
        """Verify rendered day1 HTML does NOT contain legacy em-tip-box class"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert 'class="em-tip-box"' not in template.html, \
            "Rendered day1 HTML should NOT contain legacy em-tip-box class"


class TestLightLockedTipCardHelper:
    """Direct tests for _light_locked_tip_card helper function"""
    
    def test_helper_returns_html_with_force_light_card(self):
        """Verify helper returns HTML with em-force-light-card class"""
        html = _light_locked_tip_card(
            title="Test Title",
            bullets=["Item 1", "Item 2"],
            accent="#991B1B"
        )
        
        assert 'em-force-light-card' in html, \
            "Helper should return HTML with em-force-light-card class"
    
    def test_helper_returns_html_with_force_dark_text(self):
        """Verify helper returns HTML with em-force-dark-text class"""
        html = _light_locked_tip_card(
            title="Test Title",
            bullets=["Item 1", "Item 2"],
            accent="#991B1B"
        )
        
        assert 'em-force-dark-text' in html, \
            "Helper should return HTML with em-force-dark-text class"
    
    def test_helper_returns_html_with_force_muted_text(self):
        """Verify helper returns HTML with em-force-muted-text class"""
        html = _light_locked_tip_card(
            title="Test Title",
            bullets=["Item 1", "Item 2"],
            accent="#991B1B"
        )
        
        assert 'em-force-muted-text' in html, \
            "Helper should return HTML with em-force-muted-text class"
    
    def test_helper_renders_title(self):
        """Verify helper renders the title correctly"""
        html = _light_locked_tip_card(
            title="My Custom Title",
            bullets=["Item 1"],
            accent="#991B1B"
        )
        
        assert 'My Custom Title' in html, \
            "Helper should render the title"
    
    def test_helper_renders_all_bullets(self):
        """Verify helper renders all bullet items"""
        bullets = ["First item", "Second item", "Third item"]
        html = _light_locked_tip_card(
            title="Test",
            bullets=bullets,
            accent="#991B1B"
        )
        
        for bullet in bullets:
            assert bullet in html, f"Helper should render bullet: {bullet}"
    
    def test_helper_uses_accent_color(self):
        """Verify helper uses the provided accent color"""
        accent = "#DC2626"
        html = _light_locked_tip_card(
            title="Test",
            bullets=["Item"],
            accent=accent
        )
        
        assert accent in html, \
            f"Helper should use accent color {accent}"


class TestCSSForceClassesExist:
    """Verify CSS force classes are defined in responsive styles"""
    
    def test_em_force_light_card_css_defined(self):
        """Verify em-force-light-card CSS is defined in responsive styles"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        assert '.em-force-light-card{' in source or '.em-force-light-card {' in source, \
            "em-force-light-card CSS class should be defined"
    
    def test_em_force_dark_text_css_defined(self):
        """Verify em-force-dark-text CSS is defined in responsive styles"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        assert '.em-force-dark-text{' in source or '.em-force-dark-text {' in source, \
            "em-force-dark-text CSS class should be defined"
    
    def test_em_force_muted_text_css_defined(self):
        """Verify em-force-muted-text CSS is defined in responsive styles"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        assert '.em-force-muted-text{' in source or '.em-force-muted-text {' in source, \
            "em-force-muted-text CSS class should be defined"
    
    def test_dark_mode_override_for_force_light_card(self):
        """Verify dark mode CSS override exists for em-force-light-card"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        # Check for prefers-color-scheme dark mode override
        assert '@media (prefers-color-scheme:dark)' in source, \
            "Dark mode media query should exist"
        
        # Check that em-force-light-card has dark mode override
        dark_mode_start = source.index('@media (prefers-color-scheme:dark)')
        # Find the closing brace of the media query (simplified check)
        assert '.em-force-light-card' in source[dark_mode_start:dark_mode_start+5000], \
            "em-force-light-card should have dark mode override"


class TestV7ComplianceNotRegressed:
    """Verify V7 compliance contracts are not regressed by the fix"""
    
    def test_day1_template_uses_wrap_function(self):
        """Verify day1 template still uses _wrap for V7 compliance"""
        source = EMAIL_TEMPLATES_PATH.read_text(encoding='utf-8')
        
        day1_start = source.index('def build_recovery_email_day1(')
        day1_end = source.index('def build_recovery_email_day3(')
        day1_block = source[day1_start:day1_end]
        
        assert '_wrap(' in day1_block, \
            "day1 template should use _wrap function for V7 compliance"
    
    def test_rendered_day1_has_v7_fingerprints(self):
        """Verify rendered day1 HTML has V7 template fingerprints"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        v7_fingerprints = ["em-outer", "em-card", "em-body", "email-outer", "email-card"]
        found = [fp for fp in v7_fingerprints if fp in template.html]
        
        assert len(found) >= 2, \
            f"Rendered day1 HTML should have V7 fingerprints. Found: {found}"
    
    def test_rendered_day1_has_valid_subject(self):
        """Verify rendered day1 template has valid subject line"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert template.subject, "Template should have a subject"
        assert "payment" in template.subject.lower() or "action" in template.subject.lower(), \
            "Subject should mention payment or action"
    
    def test_rendered_day1_has_text_version(self):
        """Verify rendered day1 template has text version"""
        template = build_recovery_email_day1(
            user_name="TestUser",
            plan_name="Premium",
            amount="$15.99",
            recovery_link="/subscription/plans"
        )
        
        assert template.text, "Template should have a text version"
        assert "TestUser" in template.text, "Text version should contain user name"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
