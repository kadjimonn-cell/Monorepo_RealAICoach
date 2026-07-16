"""Reusable, versioned prompt templates with {{variable}} interpolation."""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def render_template(template: str, variables: Dict[str, Any]) -> str:
    def _sub(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))

    return re.sub(r"\{\{([^{}]+)\}\}", _sub, template or "")


DEFAULT_PROMPTS = [
    {
        "prompt_key": "code_review",
        "name": "Code Review",
        "description": "Structured review of a code diff or snippet.",
        "template": "Review the following code for correctness, security, and maintainability.\n\nLanguage: {{language}}\n\nCode:\n{{code}}\n\nReturn findings grouped by severity (critical/major/minor) with actionable fixes.",
        "variables": ["language", "code"],
        "tags": ["engineering", "qa"],
    },
    {
        "prompt_key": "security_audit",
        "name": "Security Audit",
        "description": "Threat-model style audit of a component description.",
        "template": "Perform a security audit of the following component.\n\nComponent: {{component}}\nContext: {{context}}\n\nIdentify vulnerabilities (OWASP-aligned), risk ratings, and remediation steps.",
        "variables": ["component", "context"],
        "tags": ["security"],
    },
    {
        "prompt_key": "career_advice",
        "name": "Career Advice",
        "description": "Personalized career coaching guidance.",
        "template": "Provide career coaching for the following situation.\n\nGoal: {{goal}}\nBackground: {{background}}\n\nGive a concrete 30/60/90-day action plan.",
        "variables": ["goal", "background"],
        "tags": ["coaching"],
    },
    {
        "prompt_key": "doc_summary",
        "name": "Documentation Summary",
        "description": "Summarize technical content into concise docs.",
        "template": "Summarize the following content into clear developer documentation with headings and bullet points.\n\nContent:\n{{content}}",
        "variables": ["content"],
        "tags": ["documentation"],
    },
    {
        "prompt_key": "bug_triage",
        "name": "Bug Triage",
        "description": "Structured triage of a defect report.",
        "template": "Triage this bug report.\n\nReport: {{report}}\nAffected area: {{area}}\n\nReturn: severity, likely root cause hypotheses (ranked), reproduction plan, and suggested owner role.",
        "variables": ["report", "area"],
        "tags": ["qa", "engineering"],
    },
    {
        "prompt_key": "api_design",
        "name": "API Design Review",
        "description": "Review or design a REST API contract.",
        "template": "Design or review a REST API for the following capability.\n\nCapability: {{capability}}\nConstraints: {{constraints}}\n\nReturn endpoints with methods, request/response examples, status codes, and pagination/versioning notes.",
        "variables": ["capability", "constraints"],
        "tags": ["engineering", "api"],
    },
    {
        "prompt_key": "seo_audit",
        "name": "SEO Audit",
        "description": "Audit a page or content for search optimization.",
        "template": "Perform an SEO audit.\n\nPage/topic: {{page}}\nTarget keywords: {{keywords}}\n\nCover technical SEO, content-intent match, internal linking, and prioritized fixes by traffic impact.",
        "variables": ["page", "keywords"],
        "tags": ["seo", "growth"],
    },
    {
        "prompt_key": "incident_postmortem",
        "name": "Incident Postmortem",
        "description": "Blameless postmortem from an incident summary.",
        "template": "Write a blameless postmortem.\n\nIncident summary: {{summary}}\nTimeline notes: {{timeline}}\n\nInclude: impact, root cause, contributing factors, what went well, and prevention action items with owners.",
        "variables": ["summary", "timeline"],
        "tags": ["security", "sre"],
    },
]


async def ensure_prompts_seeded() -> None:
    from routes.db import db

    existing_keys = set(await db.af_prompts.distinct("prompt_key"))
    missing = [p for p in DEFAULT_PROMPTS if p["prompt_key"] not in existing_keys]
    if not missing:
        return
    now = datetime.now(timezone.utc).isoformat()
    for p in missing:
        await db.af_prompts.update_one(
            {"prompt_key": p["prompt_key"]},
            {"$setOnInsert": {**p, "version": 1, "created_at": now, "updated_at": now, "is_seed": True}},
            upsert=True,
        )


async def list_prompts() -> List[Dict[str, Any]]:
    from routes.db import db

    await ensure_prompts_seeded()
    return await db.af_prompts.find({}, {"_id": 0}).sort("prompt_key", 1).to_list(length=200)


async def get_prompt(prompt_key: str) -> Optional[Dict[str, Any]]:
    from routes.db import db

    return await db.af_prompts.find_one({"prompt_key": prompt_key}, {"_id": 0})


async def upsert_prompt(payload: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    now = datetime.now(timezone.utc).isoformat()
    prompt_key = payload["prompt_key"]
    existing = await get_prompt(prompt_key)
    if existing:
        await db.af_prompt_versions.insert_one({
            "version_id": str(uuid.uuid4()), "prompt_key": prompt_key,
            "snapshot": existing, "archived_at": now, "archived_by": actor_id,
        })
        version = int(existing.get("version", 1)) + 1
    else:
        version = 1
    doc = {
        "prompt_key": prompt_key,
        "name": payload.get("name", prompt_key),
        "description": payload.get("description", ""),
        "template": payload.get("template", ""),
        "variables": payload.get("variables", []),
        "tags": payload.get("tags", []),
        "version": version,
        "updated_at": now,
        "updated_by": actor_id,
    }
    if not existing:
        doc["created_at"] = now
    await db.af_prompts.update_one({"prompt_key": prompt_key}, {"$set": doc}, upsert=True)
    await log_audit("prompt_upserted", actor_id, "prompt", prompt_key, {"version": version})
    return await get_prompt(prompt_key)


async def delete_prompt(prompt_key: str, actor_id: str) -> bool:
    from routes.db import db
    from agent_framework.audit import log_audit

    result = await db.af_prompts.delete_one({"prompt_key": prompt_key})
    if result.deleted_count:
        await log_audit("prompt_deleted", actor_id, "prompt", prompt_key)
        return True
    return False
