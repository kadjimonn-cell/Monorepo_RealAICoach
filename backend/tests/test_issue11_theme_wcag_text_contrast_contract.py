from pathlib import Path
import re


V2_THEME_PATH = Path('/app/frontend/src/theme/v2.ts')
AA_MIN_CONTRAST = 4.5


def _extract_v2_dark_tokens() -> dict[str, str]:
    source = V2_THEME_PATH.read_text(encoding='utf-8')
    match = re.search(r"export const V2_DARK\s*=\s*\{(?P<body>.*?)\}\s*as const;", source, re.DOTALL)
    assert match, 'Unable to parse V2_DARK object from theme/v2.ts'
    body = match.group('body')

    token_pairs = re.findall(r"^\s*([A-Za-z0-9_]+):\s*'([^']+)'\s*,?\s*$", body, re.MULTILINE)
    return {key: value for key, value in token_pairs}


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) == 8:
        value = value[:6]
    assert len(value) == 6, f'Unsupported color format for WCAG contract: {color}'
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def convert(channel: int) -> float:
        normalized = channel / 255.0
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    r, g, b = (convert(channel) for channel in rgb)
    return (0.2126 * r) + (0.7152 * g) + (0.0722 * b)


def _contrast_ratio(foreground: str, background: str) -> float:
    fg = _relative_luminance(_hex_to_rgb(foreground))
    bg = _relative_luminance(_hex_to_rgb(background))
    light = max(fg, bg)
    dark = min(fg, bg)
    return (light + 0.05) / (dark + 0.05)


def test_issue11_all_v2_dark_text_tokens_meet_wcag_aa_against_paired_backgrounds() -> None:
    tokens = _extract_v2_dark_tokens()
    text_tokens = sorted([key for key in tokens.keys() if 'text' in key.lower()])

    pair_overrides = {
        'inputText': 'input',
        'badgeText': 'badge',
    }
    default_background_token = 'bg'

    # Contract intent: every dark theme text token must be AA-compliant
    # against an explicit background pairing.
    assert text_tokens, 'No text tokens found in V2_DARK for WCAG validation.'
    for text_key in text_tokens:
        assert text_key in tokens, f'Missing text token in V2_DARK: {text_key}'

        background_key = pair_overrides.get(text_key, default_background_token)
        assert background_key in tokens, f'Missing background token for {text_key}: {background_key}'

        ratio = _contrast_ratio(tokens[text_key], tokens[background_key])
        assert ratio >= AA_MIN_CONTRAST, (
            f'{text_key} contrast failed AA in V2_DARK: '
            f'{tokens[text_key]} vs {background_key}={tokens[background_key]} (ratio={ratio:.2f})'
        )
