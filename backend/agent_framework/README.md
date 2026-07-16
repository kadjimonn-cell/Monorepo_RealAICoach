# Native AI Agent Framework

Provider-agnostic, modular AI agent architecture built natively on RealAICoach
infrastructure (FastAPI + MongoDB + existing Emergent LLM gateway). Zero external
framework dependencies, zero vendor lock-in.

## Modules

| Module | Responsibility |
|---|---|
| `providers.py` | `AIProvider` interface + `ProviderRegistry`. Agents reference logical provider names (`openai`, `anthropic`, `google`); all routed through the existing platform LLM gateway. New providers plug in via `provider_registry.register()`. |
| `agents.py` | Role-based agent registry (10 seeded roles: Security, Engineering, Architecture, QA, Data, DevOps, Product, Research, Documentation, Career Coaching). Full CRUD with automatic version snapshots (`af_agent_versions`). |
| `prompts.py` | Reusable versioned prompt templates with `{{variable}}` interpolation (`af_prompts` / `af_prompt_versions`). |
| `tools.py` | Extensible tool/plugin registry. Register new tools with `@tool_registry.register(...)` — no core changes required. Built-ins: `template_render`, `db_read` (allow-listed, read-only), `http_fetch` (HTTPS GET only). |
| `memory.py` | Standardized Mongo-backed conversation memory per `(agent_key, session_id)` with automatic trimming. |
| `policy.py` | Centralized config (`af_config`): step limits, timeout/retry clamps, hourly execution quota, per-agent tool allowlists. |
| `engine.py` | Native workflow engine: **sequential**, **parallel**, **conditional**, **human-in-the-loop** steps. Per-step retries + timeouts, resumable HITL pauses, execution records (`af_executions`). |
| `audit.py` | Centralized audit trail (`af_audit_log`) for every mutation and execution event. |

## Workflow step schema

```json
{
  "step_id": "s1",
  "type": "agent | tool | condition | parallel | human_approval",
  "agent_key": "security_auditor",          // type=agent
  "input_template": "Audit: {{input}}",     // {{input}}, {{steps.s1.output}}
  "tool_name": "http_fetch", "args": {},    // type=tool
  "condition": {"field": "steps.s1.output", "op": "contains", "value": "critical"},
  "then_steps": [], "else_steps": [],       // type=condition
  "branches": [[...], [...]],                // type=parallel
  "prompt": "Approve remediation?",         // type=human_approval (top level only)
  "retries": 1, "timeout_seconds": 45, "continue_on_error": false
}
```

Condition operators: `exists`, `not_exists`, `equals`, `not_equals`, `contains`, `gt`, `lt`.

## Execution lifecycle

`running` → `completed` | `failed` | `waiting_human` → (approve/reject) → `running` | `rejected`

## API (admin-only, `/api/agent-framework/*`)

- `GET /overview` — dashboard stats
- `GET|POST /agents`, `GET|DELETE /agents/{key}`, `GET /agents/{key}/versions`, `POST /agents/{key}/execute`
- `GET|POST /prompts`, `DELETE /prompts/{key}`, `POST /prompts/{key}/render`
- `GET|POST /workflows`, `PUT|DELETE /workflows/{id}`, `POST /workflows/{id}/execute`
- `GET /executions`, `GET /executions/{id}`, `POST /executions/{id}/approve|reject`
- `GET /tools`, `GET /providers`, `GET|PUT /policy`, `GET /audit`

## Collections

`af_agents`, `af_agent_versions`, `af_prompts`, `af_prompt_versions`, `af_workflows`,
`af_workflow_versions`, `af_executions`, `af_memory`, `af_config`, `af_audit_log`

## Admin UI

Operations Console panel: `/admin/ai-agents` (theme v2 light/dark compliant).
