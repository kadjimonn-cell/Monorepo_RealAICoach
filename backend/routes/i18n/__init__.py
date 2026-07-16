"""Multilingual Support (i18n).

Language detection, translation management, and locale settings.
Modular package; all submodules register onto the shared router.
"""

from .constants import SUPPORTED_LANGUAGES, COUNTRY_LANGUAGE_HINTS, COUNTRY_CURRENCY_HINTS
from .helpers import router, logger
from .default_translations import DEFAULT_TRANSLATIONS

from . import coverage  # noqa: F401  /fallback-hit, /coverage*
from . import core_routes  # noqa: F401  /locales, /languages, /translations, /user-preference, /email-locale, /health
from . import auto_translate  # noqa: F401  /auto-translate*, /pre-warm-cache*, /safe-auto*
from . import guidance  # noqa: F401  /language-guidance*
from . import global_adaptation  # noqa: F401  /admin/global-adaptation/*
from . import quality  # noqa: F401  /quality-*, /brand-protection, /admin/language-quality-dashboard
from . import smoke_report  # noqa: F401  /admin/multilingual-smoke-report*
from . import glossary  # noqa: F401  /glossary*

from .quality import run_weekly_translation_quality_check

__all__ = [
    "router",
    "logger",
    "SUPPORTED_LANGUAGES",
    "COUNTRY_LANGUAGE_HINTS",
    "COUNTRY_CURRENCY_HINTS",
    "DEFAULT_TRANSLATIONS",
    "run_weekly_translation_quality_check",
]
