import ast
from pathlib import Path


SOURCE_PATH = Path("/app/backend/utils/ws_manager.py")


def test_connection_manager_has_single_init_definition() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    class_nodes = [n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "ConnectionManager"]
    assert class_nodes, "ConnectionManager class not found"

    init_nodes = [n for n in class_nodes[0].body if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
    assert len(init_nodes) == 1, "ConnectionManager must define exactly one __init__"


def test_connection_manager_initializer_sets_required_listeners() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "ConnectionManager")
    init_fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")

    assigned_attrs: set[str] = set()

    for node in ast.walk(init_fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    assigned_attrs.add(target.attr)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                assigned_attrs.add(target.attr)

    required = {
        "connections",
        "public_stream",
        "admin_activity_listeners",
        "automation_listeners",
        "aso_listeners",
    }
    missing = required - assigned_attrs
    assert not missing, f"Missing required __init__ assignments: {sorted(missing)}"
