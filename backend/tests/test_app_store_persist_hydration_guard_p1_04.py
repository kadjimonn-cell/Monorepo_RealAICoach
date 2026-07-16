from pathlib import Path


STORE_PATH = Path("/app/frontend/src/store/appStore.ts")
ROOT_LAYOUT_PATH = Path("/app/frontend/app/_layout.tsx")
PROFILE_PATH = Path("/app/frontend/app/(tabs)/profile.tsx")
ACHIEVEMENTS_PATH = Path("/app/frontend/app/achievements.tsx")
CHAT_PATH = Path("/app/frontend/app/chat/[id].tsx")
SCENARIO_PATH = Path("/app/frontend/app/scenario/[id].tsx")
SESSION_HISTORY_PATH = Path("/app/frontend/app/session-history.tsx")


def test_app_store_uses_persist_with_async_storage_and_hydration_flag() -> None:
    source = STORE_PATH.read_text(encoding="utf-8")

    assert "persist(" in source
    assert "createJSONStorage(() => AsyncStorage)" in source
    assert "hasHydrated" in source
    assert "_hasHydrated" in source
    assert "onRehydrateStorage" in source
    assert "setHasHydrated(true)" in source


def test_app_store_persists_expected_fields() -> None:
    source = STORE_PATH.read_text(encoding="utf-8")

    assert "partialize" in source
    assert "userId: state.userId" in source
    assert "currentConversationId: state.currentConversationId" in source
    assert "currentScenario: state.currentScenario" in source


def test_app_store_has_schema_version_and_migrate_contract() -> None:
    source = STORE_PATH.read_text(encoding="utf-8")

    assert "const APP_STORE_VERSION = 3;" in source
    assert "version: APP_STORE_VERSION" in source
    assert "migrate:" in source
    assert "hasHydrated: false" in source
    assert "_hasHydrated: false" in source


def test_root_layout_waits_for_store_hydration_before_main_render() -> None:
    layout = ROOT_LAYOUT_PATH.read_text(encoding="utf-8")

    assert "const storeHydrated = useAppStore((state) => state._hasHydrated || state.hasHydrated);" in layout
    assert "if (!fontsReady || !hydrated || !storeHydrated)" in layout


def test_key_screens_reference_hydration_guard() -> None:
    profile = PROFILE_PATH.read_text(encoding="utf-8")
    achievements = ACHIEVEMENTS_PATH.read_text(encoding="utf-8")
    chat = CHAT_PATH.read_text(encoding="utf-8")
    scenario = SCENARIO_PATH.read_text(encoding="utf-8")
    session_history = SESSION_HISTORY_PATH.read_text(encoding="utf-8")

    assert "hasHydrated" in profile and "!hasHydrated || !pageReady" in profile
    assert "hasHydrated" in achievements and "if (!hasHydrated || loading)" in achievements
    assert "hasHydrated" in chat and "if (!hasHydrated || loading)" in chat
    assert "hasHydrated" in scenario and "if (!hasHydrated || loading)" in scenario
    assert "hasHydrated" in session_history and "if (!hasHydrated || loading)" in session_history
