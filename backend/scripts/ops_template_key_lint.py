#!/usr/bin/env python3
"""Centralized lint rule: ops alert send_email calls must include approved template keys.

Rule:
- For monitored ops files, direct send_email(...) calls must include `template_key=...`
- Exception: calls inside functions decorated with @ops_alert_template_enforcer(...)
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List


OPS_FILES = [
    Path("/app/backend/routes/autonomous_engine.py"),
    Path("/app/backend/routes/code_health.py"),
    Path("/app/backend/routes/accessibility_audit.py"),
    Path("/app/backend/routes/performance_guardian.py"),
    Path("/app/backend/routes/ai_panel_insights.py"),
]


def _is_send_email_call(node: ast.Call) -> bool:
    fn = node.func
    if isinstance(fn, ast.Name) and fn.id == "send_email":
        return True
    return isinstance(fn, ast.Attribute) and fn.attr == "send_email"


def _has_template_key_kw(node: ast.Call) -> bool:
    return any(getattr(kw, "arg", None) == "template_key" for kw in node.keywords)


def _decorator_name(deco: ast.expr) -> str:
    if isinstance(deco, ast.Call):
        deco = deco.func
    if isinstance(deco, ast.Name):
        return deco.id
    if isinstance(deco, ast.Attribute):
        return deco.attr
    return ""


def lint_source(source: str, source_name: str = "<memory>") -> List[str]:
    tree = ast.parse(source, filename=source_name)
    violations: List[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.decorated_scope = [False]

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            decorated = any(_decorator_name(d) == "ops_alert_template_enforcer" for d in node.decorator_list)
            self.decorated_scope.append(decorated or self.decorated_scope[-1])
            self.generic_visit(node)
            self.decorated_scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            decorated = any(_decorator_name(d) == "ops_alert_template_enforcer" for d in node.decorator_list)
            self.decorated_scope.append(decorated or self.decorated_scope[-1])
            self.generic_visit(node)
            self.decorated_scope.pop()

        def visit_Call(self, node: ast.Call):
            if _is_send_email_call(node):
                if not self.decorated_scope[-1] and not _has_template_key_kw(node):
                    violations.append(f"{source_name}:{node.lineno} send_email missing template_key")
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


def lint_file(path: Path) -> List[str]:
    if not path.exists():
        return []
    return lint_source(path.read_text(encoding="utf-8"), str(path))


def main() -> int:
    violations: List[str] = []
    for file_path in OPS_FILES:
        violations.extend(lint_file(file_path))

    if violations:
        print("Ops template-key lint FAILED:")
        for row in violations:
            print(f" - {row}")
        return 1

    print("Ops template-key lint PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
