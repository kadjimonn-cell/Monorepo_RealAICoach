from pathlib import Path


THEME_CONTEXT_PATH = Path('/app/frontend/src/context/ThemeContext.tsx')


def test_web_system_dark_initialized_from_match_media_synchronously() -> None:
    source = THEME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert "const [webSystemDark, setWebSystemDark] = useState(() =>" in source
    assert "window.matchMedia('(prefers-color-scheme: dark)').matches" in source
    assert "const [webSystemDark, setWebSystemDark] = useState(false);" not in source
