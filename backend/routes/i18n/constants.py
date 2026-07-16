"""i18n constants: supported languages and country hints."""

SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "flag": "us", "rtl": False},
    "fr": {"name": "French", "native": "Français", "flag": "fr", "rtl": False},
    "es": {"name": "Spanish", "native": "Español", "flag": "es", "rtl": False},
    "de": {"name": "German", "native": "Deutsch", "flag": "de", "rtl": False},
    "pt": {"name": "Portuguese", "native": "Português", "flag": "br", "rtl": False},
    "ja": {"name": "Japanese", "native": "\u65e5\u672c\u8a9e", "flag": "jp", "rtl": False},
    "zh": {"name": "Chinese", "native": "\u4e2d\u6587", "flag": "cn", "rtl": False},
    "ar": {"name": "Arabic", "native": "\u0627\u0644\u0639\u0631\u0628\u064a\u0629", "flag": "sa", "rtl": True},
    "hi": {"name": "Hindi", "native": "\u0939\u093f\u0928\u094d\u0926\u0940", "flag": "in", "rtl": False},
    "ko": {"name": "Korean", "native": "\ud55c\uad6d\uc5b4", "flag": "kr", "rtl": False},
    "it": {"name": "Italian", "native": "Italiano", "flag": "it", "rtl": False},
    "ru": {"name": "Russian", "native": "Русский", "flag": "ru", "rtl": False},
    "tr": {"name": "Turkish", "native": "Türkçe", "flag": "tr", "rtl": False},
    "nl": {"name": "Dutch", "native": "Nederlands", "flag": "nl", "rtl": False},
    "sv": {"name": "Swedish", "native": "Svenska", "flag": "se", "rtl": False},
    "pl": {"name": "Polish", "native": "Polski", "flag": "pl", "rtl": False},
    "th": {"name": "Thai", "native": "ไทย", "flag": "th", "rtl": False},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "flag": "vn", "rtl": False},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "flag": "id", "rtl": False},
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "flag": "my", "rtl": False},
    "sw": {"name": "Swahili", "native": "Kiswahili", "flag": "ke", "rtl": False},
    "uk": {"name": "Ukrainian", "native": "Українська", "flag": "ua", "rtl": False},
    "ro": {"name": "Romanian", "native": "Română", "flag": "ro", "rtl": False},
}

COUNTRY_LANGUAGE_HINTS = {
    "US": "en", "CA": "en", "GB": "en", "FR": "fr", "DE": "de", "ES": "es", "IT": "it", "NL": "nl", "SE": "sv",
    "BR": "pt", "MX": "es", "JP": "ja", "CN": "zh", "IN": "hi", "ZA": "en", "KE": "sw", "NG": "en", "GH": "en",
    "MA": "ar", "EG": "ar", "CH": "de", "BE": "fr", "AU": "en",
}

COUNTRY_CURRENCY_HINTS = {
    "US": "USD", "CA": "CAD", "GB": "GBP", "FR": "EUR", "DE": "EUR", "ES": "EUR", "IT": "EUR", "NL": "EUR", "SE": "SEK",
    "BR": "BRL", "MX": "MXN", "JP": "JPY", "CN": "CNY", "IN": "INR", "ZA": "ZAR", "KE": "KES", "NG": "NGN", "GH": "GHS",
    "MA": "MAD", "EG": "EGP", "CH": "CHF", "BE": "EUR", "AU": "AUD",
}

