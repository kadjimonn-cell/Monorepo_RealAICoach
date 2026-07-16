"""Email localization utility.

Provides helpers to localize outbound emails based on user's language preference.
Adds proper lang/dir attributes and localized subject prefixes.
"""


# Map language codes to email-friendly locale info
EMAIL_LOCALE_MAP = {
    "en": {"dir": "ltr", "lang": "en", "greeting": "Hello"},
    "fr": {"dir": "ltr", "lang": "fr", "greeting": "Bonjour"},
    "es": {"dir": "ltr", "lang": "es", "greeting": "Hola"},
    "de": {"dir": "ltr", "lang": "de", "greeting": "Hallo"},
    "pt": {"dir": "ltr", "lang": "pt", "greeting": "Olá"},
    "ja": {"dir": "ltr", "lang": "ja", "greeting": "こんにちは"},
    "zh": {"dir": "ltr", "lang": "zh", "greeting": "你好"},
    "ar": {"dir": "rtl", "lang": "ar", "greeting": "مرحبًا"},
    "hi": {"dir": "ltr", "lang": "hi", "greeting": "नमस्ते"},
    "ko": {"dir": "ltr", "lang": "ko", "greeting": "안녕하세요"},
    "it": {"dir": "ltr", "lang": "it", "greeting": "Ciao"},
    "ru": {"dir": "ltr", "lang": "ru", "greeting": "Здравствуйте"},
    "tr": {"dir": "ltr", "lang": "tr", "greeting": "Merhaba"},
    "nl": {"dir": "ltr", "lang": "nl", "greeting": "Hallo"},
    "sv": {"dir": "ltr", "lang": "sv", "greeting": "Hej"},
    "pl": {"dir": "ltr", "lang": "pl", "greeting": "Cześć"},
    "th": {"dir": "ltr", "lang": "th", "greeting": "สวัสดี"},
    "vi": {"dir": "ltr", "lang": "vi", "greeting": "Xin chào"},
    "id": {"dir": "ltr", "lang": "id", "greeting": "Halo"},
    "ms": {"dir": "ltr", "lang": "ms", "greeting": "Hai"},
    "sw": {"dir": "ltr", "lang": "sw", "greeting": "Hujambo"},
    "uk": {"dir": "ltr", "lang": "uk", "greeting": "Вітаю"},
    "ro": {"dir": "ltr", "lang": "ro", "greeting": "Bună"},
}


async def get_user_email_locale(db, user_id: str) -> dict:
    """Fetch user's language preference and return locale info for email rendering."""
    pref = await db.user_preferences.find_one(
        {"user_id": user_id, "key": "language"}, {"_id": 0}
    )
    lang_code = pref.get("value", "en") if pref else "en"
    return EMAIL_LOCALE_MAP.get(lang_code, EMAIL_LOCALE_MAP["en"])


def localize_email_html(html: str, lang_code: str = "en") -> str:
    """Inject lang and dir attributes into email HTML for proper rendering.
    
    Modifies the root <html> tag (or wraps the content) to include
    the correct lang and dir attributes for the user's language.
    """
    locale = EMAIL_LOCALE_MAP.get(lang_code, EMAIL_LOCALE_MAP["en"])
    direction = locale["dir"]
    lang = locale["lang"]

    # If the HTML has an <html tag, inject lang and dir
    if "<html" in html.lower():
        import re
        # Replace or add lang/dir to existing <html> tag
        html = re.sub(
            r"<html([^>]*)>",
            f'<html lang="{lang}" dir="{direction}"\\1>',
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        # Wrap in html/body with proper lang/dir
        html = f'<html lang="{lang}" dir="{direction}"><body>{html}</body></html>'

    return html


def get_localized_greeting(user_name: str, lang_code: str = "en") -> str:
    """Return a localized greeting string."""
    locale = EMAIL_LOCALE_MAP.get(lang_code, EMAIL_LOCALE_MAP["en"])
    return f"{locale['greeting']}, {user_name}"
