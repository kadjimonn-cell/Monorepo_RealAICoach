from pathlib import Path


SERVER_PATH = Path('/app/backend/server.py')


def test_shutdown_handler_closes_websockets_with_going_away_code() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    assert 'async def shutdown_db_client():' in source
    assert 'from utils.ws_manager import ws_manager' in source
    assert 'ws_manager.connections.values()' in source
    assert 'ws_manager.public_stream' in source
    assert 'ws_manager.admin_activity_listeners' in source
    assert 'ws_manager.automation_listeners' in source
    assert 'ws_manager.aso_listeners' in source
    assert 'await ws.close(code=1001, reason="Server shutting down")' in source


def test_shutdown_closes_websockets_before_mongo_client_close() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    shutdown_idx = source.find('async def shutdown_db_client():')
    assert shutdown_idx != -1

    ws_close_idx = source.find('await ws.close(code=1001, reason="Server shutting down")', shutdown_idx)
    client_close_idx = source.find('client.close()', shutdown_idx)
    assert ws_close_idx != -1
    assert client_close_idx != -1
    assert ws_close_idx < client_close_idx
