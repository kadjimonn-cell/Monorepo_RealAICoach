import ast
from pathlib import Path


TICKET_CHAT_BACKEND_FILE = Path("/app/backend/routes/ticket_chat.py")
AUTH_FILE = Path("/app/backend/routes/auth.py")
FRONTEND_TICKET_CHAT_FILES = [
    Path("/app/frontend/src/components/pages/MyTicketsInner.tsx"),
    Path("/app/frontend/src/components/admin/SupportTicketsPanel.tsx"),
]


def _extract_set_constant(source: str, constant_name: str) -> set[str]:
    module = ast.parse(source)
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == constant_name:
                value = ast.literal_eval(node.value)
                return set(value)
    raise AssertionError(f"Constant {constant_name} not found")


def test_ticket_chat_backend_uses_one_time_ws_ticket_pattern() -> None:
    source = TICKET_CHAT_BACKEND_FILE.read_text(encoding="utf-8")

    assert "consume_ws_ticket(" in source
    assert 'ws.query_params.get("ticket", "")' in source
    assert 'ws.query_params.get("token", "")' not in source
    assert "jwt.decode(" not in source


def test_auth_ws_ticket_allowlist_includes_ticket_chat_channel() -> None:
    source = AUTH_FILE.read_text(encoding="utf-8")
    allowed_channels = _extract_set_constant(source, "WS_TICKET_ALLOWED_CHANNELS")
    admin_channels = _extract_set_constant(source, "WS_TICKET_ADMIN_CHANNELS")

    assert "ticket_chat" in allowed_channels
    assert "ticket_chat" not in admin_channels


def test_frontend_ticket_chat_uses_ticket_query_param_not_token() -> None:
    for file_path in FRONTEND_TICKET_CHAT_FILES:
        source = file_path.read_text(encoding="utf-8")
        assert "/auth/ws-ticket" in source
        assert "ticket_chat" in source
        assert "?ticket=" in source
        assert "?token=" not in source
