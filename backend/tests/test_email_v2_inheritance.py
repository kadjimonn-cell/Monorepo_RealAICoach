"""V2 email pipeline inheritance — every outbound email inherits the V2 light-card baseline.

Offline, fast (<5s). Required by the Autonomous Engine deployment gate
(EMAIL_V2_INHERITANCE_TEST_PATH).
"""

import inspect
import sys

sys.path.insert(0, "/app/backend")

from utils.email_service import _ensure_darkmode_safe_autonomous_card


class TestV2BaselineWrapper:
    def test_wraps_plain_fragment(self):
        out = _ensure_darkmode_safe_autonomous_card("<p>Hello</p>", "any_template")
        assert "em-force-light-card" in out
        assert "<p>Hello</p>" in out

    def test_idempotent_no_double_wrap(self):
        once = _ensure_darkmode_safe_autonomous_card("<p>Hi</p>", None)
        twice = _ensure_darkmode_safe_autonomous_card(once, None)
        assert twice == once
        assert twice.count("em-force-light-card") == 1

    def test_wraps_full_document_body_inner(self):
        html = "<html><body><h1>Report</h1><p>Body</p></body></html>"
        out = _ensure_darkmode_safe_autonomous_card(html, "autonomous_engine_report")
        assert "em-force-light-card" in out
        assert out.index("<body") < out.index("em-force-light-card")
        assert "<h1>Report</h1>" in out

    def test_empty_html_passthrough(self):
        assert _ensure_darkmode_safe_autonomous_card("", None) == ""

    def test_wrapper_uses_light_card_styles(self):
        out = _ensure_darkmode_safe_autonomous_card("<p>x</p>", None)
        assert "background:#FFFFFF" in out
        assert "border-radius:12px" in out


class TestSendPipelineInheritance:
    def test_send_pipeline_applies_v2_wrapper(self):
        import utils.email_service as es

        src = inspect.getsource(es)
        assert "content = _ensure_darkmode_safe_autonomous_card(content, template_key)" in src

    def test_send_pipeline_applies_contrast_and_meta_guards(self):
        import utils.email_service as es

        src = inspect.getsource(es)
        assert "content = ensure_email_color_scheme_meta(content)" in src
        assert "content = apply_adaptive_email_contrast_guard(content)" in src

    def test_critical_catalog_templates_registered(self):
        from utils.email_templates import TEMPLATE_CATALOG

        for key in ("autonomous_engine_report", "security_runbook_monitor_report", "admin_outbound"):
            assert key in TEMPLATE_CATALOG, f"{key} missing from TEMPLATE_CATALOG"
