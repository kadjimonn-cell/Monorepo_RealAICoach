"""Standardized agent memory and context management (Mongo-backed sessions)."""

from datetime import datetime, timezone
from typing import Dict, List


async def load_memory(agent_key: str, session_id: str, limit: int = 20) -> List[Dict]:
    from routes.db import db

    doc = await db.af_memory.find_one(
        {"agent_key": agent_key, "session_id": session_id}, {"_id": 0}
    )
    messages = (doc or {}).get("messages", [])
    return messages[-limit:]


async def append_memory(agent_key: str, session_id: str, role: str, content: str, max_messages: int = 20) -> None:
    from routes.db import db

    now = datetime.now(timezone.utc).isoformat()
    await db.af_memory.update_one(
        {"agent_key": agent_key, "session_id": session_id},
        {
            "$push": {"messages": {"$each": [{"role": role, "content": content[:8000], "at": now}], "$slice": -max_messages}},
            "$set": {"updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def render_memory_context(messages: List[Dict]) -> str:
    if not messages:
        return ""
    lines = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
    return "Previous conversation:\n" + "\n".join(lines) + "\n\n"
