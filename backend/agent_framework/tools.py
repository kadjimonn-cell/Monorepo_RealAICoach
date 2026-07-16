"""Extensible tool/plugin registry with a standardized interface.

New tools register via the @tool_registry.register decorator without any
change to core architecture.
"""

import logging
import re
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

ToolHandler = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Any]]


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        permission: str = "admin",
    ):
        def decorator(handler: ToolHandler) -> ToolHandler:
            self._tools[name] = {
                "name": name,
                "description": description,
                "input_schema": input_schema,
                "permission": permission,
                "handler": handler,
            }
            return handler

        return decorator

    def get(self, name: str) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool '{name}'. Registered: {sorted(self._tools)}")
        return tool

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {k: v for k, v in t.items() if k != "handler"}
            for t in sorted(self._tools.values(), key=lambda t: t["name"])
        ]

    async def execute(self, name: str, args: Dict[str, Any], context: Dict[str, Any]) -> Any:
        tool = self.get(name)
        return await tool["handler"](args or {}, context or {})


tool_registry = ToolRegistry()


# ── Built-in tools ──

@tool_registry.register(
    name="template_render",
    description="Render a text template by substituting {{variable}} placeholders from args.variables.",
    input_schema={"template": "string", "variables": "object"},
)
async def _template_render(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    template = str(args.get("template", ""))
    variables = args.get("variables") or {}

    def _sub(match):
        return str(variables.get(match.group(1).strip(), match.group(0)))

    return re.sub(r"\{\{([^{}]+)\}\}", _sub, template)


DB_READ_ALLOWED_COLLECTIONS = {
    "af_agents", "af_workflows", "af_executions", "af_prompts",
    "gamification_profiles", "gamification_events",
}


@tool_registry.register(
    name="db_read",
    description="Read-only query against an allow-listed MongoDB collection (max 20 docs).",
    input_schema={"collection": "string", "filter": "object", "limit": "integer"},
)
async def _db_read(args: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    from routes.db import db

    collection = str(args.get("collection", ""))
    if collection not in DB_READ_ALLOWED_COLLECTIONS:
        raise PermissionError(f"Collection '{collection}' is not in the read allowlist")
    limit = min(int(args.get("limit") or 10), 20)
    cursor = db[collection].find(args.get("filter") or {}, {"_id": 0}).limit(limit)
    return await cursor.to_list(length=limit)


@tool_registry.register(
    name="knowledge_search",
    description="Search curated knowledge collections; returns snippets with citations.",
    input_schema={"query": "string", "collection_key": "string", "limit": "integer"},
)
async def _knowledge_search(args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    from agent_framework.knowledge import search_knowledge

    return await search_knowledge(
        str(args.get("collection_key") or ""),
        str(args.get("query", "")),
        min(int(args.get("limit") or 5), 10),
    )


@tool_registry.register(
    name="http_fetch",
    description="Fetch a public HTTPS URL via GET (response capped at 100KB).",
    input_schema={"url": "string"},
)
async def _http_fetch(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    import httpx

    url = str(args.get("url", ""))
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are permitted")
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url)
        return response.text[:100_000]
