from pathlib import Path


ROOT_LAYOUT_PATH = Path("/app/frontend/app/_layout.tsx")


def test_boot_policy_handshake_listener_and_timeout_fallback_exist() -> None:
    source = ROOT_LAYOUT_PATH.read_text(encoding="utf-8")

    assert "function useBootPolicyHandshakeState()" in source
    assert "window.addEventListener('rac:boot-policy-ready'" in source
    assert "setTimeout(() =>" in source
    assert "}, 6500);" in source


def test_boot_policy_gate_blocks_stack_until_ready_or_blocked() -> None:
    source = ROOT_LAYOUT_PATH.read_text(encoding="utf-8")

    assert "if (!bootPolicyState.ready && !bootPolicyState.blocked)" in source
    assert "return <RootLoadingFallback />;" in source


def test_blocked_boot_policy_emits_reload_telemetry() -> None:
    source = ROOT_LAYOUT_PATH.read_text(encoding="utf-8")

    assert "max_reload_attempts_exceeded" in source
    assert "/api/config/boot-policy/telemetry" in source
    assert "event_type: 'should_reload_true'" in source
