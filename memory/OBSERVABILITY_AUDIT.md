# RealAICoach Observability Audit (Global) — 2026-05-06

## Scope + Evidence Method (No Assumptions)
- Code-level audit across backend/frontend observability paths.
- Live endpoint verification using admin auth against runtime preview.
- MongoDB collection verification (counts + sampled schema keys).
- Dependency audit (`requirements.txt`, `package.json`) for tracing/APM stacks.

All findings below are from actual code/data/runtime checks only.

---

## 1) Existing Observability Inventory

## A. Logging / Event Capture

### Backend log/event systems currently present
1. **Python logging (global)**
   - File: `backend/server.py` (`logging.basicConfig`)
   - Format: plain text (`%(asctime)s - %(name)s - %(levelname)s - %(message)s`)
   - Status: **Working**, but **not structured JSON**.

2. **Security/SIEM event store + admin APIs**
   - File: `backend/routes/siem_logging.py`
   - Key endpoints:
     - `GET /api/admin/siem/overview`
     - `GET /api/admin/siem/events`
     - `GET /api/admin/siem/timeline`
     - `GET /api/admin/siem/audit-log`
     - rule management + triggered alerts endpoints
   - Data source: `security_events`, `siem_alert_rules`, `siem_triggered_alerts`, `admin_audit_logs`
   - Runtime check: endpoints return `200` with real payloads.
   - Status: **Working**.

3. **Client error ingestion**
   - File: `backend/routes/client_errors.py`
   - Endpoints:
     - `POST /api/errors/client`
     - `GET /api/errors/client/top`
   - Data source: `client_errors`
   - Status: endpoint works with active records present.

4. **Session replay events**
   - File: `backend/routes/session_replay.py`
   - Endpoints: list/session detail/stats/record/end/delete
   - Data source: `session_recordings`, `session_replay_events`
   - Observed counts: `session_replay_events` has real data.
   - Status: **Working**.

5. **Shell/preview/realtime health ingest**
   - File: `backend/routes/platform_shell_health.py`
   - Endpoints:
     - `POST /api/platform-shell-health/ingest`
     - `POST /api/platform-shell-health/realtime-ingest`
     - `POST /api/platform-shell-health/preview-ingest`
     - `GET /api/platform-shell-health/admin/preview-summary`
   - Data source: `shell_health_events`, `realtime_connection_health_events`, `preview_shell_health_events`
   - Observed counts: all three collections contain real data.
   - Status: **Working**.

### Frontend log/event emitters currently present
1. `frontend/src/services/clientErrorReporter.ts` → posts `/api/errors/client`
2. `frontend/src/services/shellHealthMonitor.ts` → posts `/api/platform-shell-health/ingest`
3. `frontend/src/services/previewHealthMonitor.ts` → posts `/api/platform-shell-health/preview-ingest`
4. `frontend/src/hooks/useSessionReplay.ts` → posts `/api/admin/session-replay/record` and `/end`
5. `frontend/app/+html.tsx` + `frontend/src/hooks/useWebVitals.ts` → emits vitals/page perf

Status: **Implemented and active**, though correlation metadata is limited (details in gaps).

---

## B. Metrics / Monitoring

### Backend metrics services present
1. **System metrics**
   - File: `backend/routes/system_metrics.py`
   - Endpoints:
     - `GET /api/admin/system/metrics`
     - `GET /api/system/metrics`
     - WS `/api/ws/system-metrics`
   - Uses `psutil` for CPU/memory/disk/network/process.
   - Status: **Working**.

2. **Platform performance monitor**
   - File: `backend/routes/platform_monitor.py`
   - Endpoints:
     - `GET /api/admin/platform/performance`
     - `GET /api/admin/platform/errors`
     - `GET /api/admin/platform/health`
   - Runtime check: all return `200`.
   - Status: **Working**.

3. **Page performance + web vitals analytics**
   - Files:
     - `backend/routes/page_performance.py`
     - `backend/routes/performance_guardian.py`
     - `backend/routes/seo_analytics.py`
   - Endpoints verified working:
     - `GET /api/admin/page-performance/dashboard`
     - `GET /api/admin/web-vitals/dashboard`
     - `GET /api/admin/web-vitals/alerts`
     - `GET /api/admin/platform-perf/unified`
     - `GET /api/admin/platform-perf/trend`
     - `GET /api/admin/platform-perf/shell-health`
   - Collections with real data:
     - `web_vitals` (~55k)
     - `page_perf_metrics` (~11k)
     - `perf_metrics_history` (~2k)
   - Status: **Working**.

4. **GPS runtime health/degradation signals**
   - File: `backend/routes/gps_runtime_routes.py`
   - Endpoints:
     - `GET /api/gps/health`
     - `POST /api/gps/consistency/check`
     - incident/admin sync endpoints
   - Includes degraded mode + alert emission hooks.
   - Status: **Working**.

### Frontend monitoring surfaces present
1. `frontend/app/performance-observability.tsx`
2. `frontend/app/route-health-report.tsx`
3. `frontend/src/components/admin/SystemMonitorPanel.tsx`
4. `frontend/src/components/admin/WebVitalsPanel.tsx`
5. `frontend/src/components/admin/SIEMPanel.tsx`

Status: **Working dashboard layer exists today**.

---

## C. Tracing / APM

### Tracing/APM inventory
- OpenTelemetry SDK: **not present** in backend/frontend dependencies.
- Prometheus exporter: **not present**.
- Jaeger/Zipkin exporters: **not present**.
- Sentry/NewRelic/Datadog tracing SDK: **not present**.
- No distributed trace propagation (`traceparent`) detected.
- No `trace_id`/`span_id` correlation fields in log/event schemas.

Status: **Missing** (major enterprise gap).

---

## 2) Working vs Broken vs Missing

## Working
- Admin performance/health endpoints return real data.
- Web vitals + page performance ingestion is active with high sample counts.
- Shell health + preview health ingest pipelines are active.
- SIEM dashboards and alert-rule APIs are active.
- Session replay event capture is active.
- GPS health/consistency APIs exist and return real runtime state.

## Broken / Weak
1. **Trace correlation absent**
   - Logs, metrics, errors, and sessions are not linked by trace IDs.

2. **Structured logging absent**
   - Plain text logger format in backend; no JSON log envelope.

3. **Partial/low client error coverage**
   - `client_error_logs` currently empty despite endpoint availability.

4. **Potential fabricated fallback paths exist in some analytics routes**
   - Example: `backend/routes/seo_analytics.py` includes synthetic fallback generation branches.
   - This conflicts with strict “no fabricated observability data” requirement.

5. **Redundant observability surfaces**
   - Overlap across `platform_monitor`, `platform_perf`, `performance_guardian`, `seo_analytics` for similar KPI classes.
   - Higher maintenance + inconsistent semantics risk.

## Missing (Enterprise Requirements)
- OpenTelemetry standard instrumentation (frontend + backend).
- Distributed tracing across frontend → API → DB → external services.
- Trace-aware structured logs.
- Metrics exposition compatible with unified backend/infra scraper pipeline.
- Unified correlation model (logs ↔ traces ↔ metrics ↔ session).
- Unified alert routing with trace/log context links.

---

## 3) Gap Analysis vs Required Pillars

## Pillar 1: Logs
- Present: security events, client errors, shell health, session replay, backend logs.
- Gap: no mandatory JSON structured schema across all services.
- Gap: no mandatory `trace_id`, `span_id`, `service`, `environment` keys.

## Pillar 2: Metrics
- Present: web vitals, page perf, platform metrics, system metrics, some business/security metrics.
- Gap: no single standardized telemetry backend schema.
- Gap: no Prometheus/OpenTelemetry metrics export path.

## Pillar 3: Traces
- Present: none (no true distributed tracing).
- Gap: full E2E request tracing missing.

## Correlation
- Current: mostly disconnected telemetry channels.
- Gap: logs not linked to traces; traces absent; user/session linkage partial.

## Alerting
- Present: SIEM rule engine, performance/web-vitals alert APIs, GPS incident alert hooks.
- Gap: no universal alert envelope tied to trace/log drill-down context.

---

## 4) Redundancies + Misconfiguration Risks

1. **Observability KPI overlap** across multiple route groups (`platform_monitor`, `platform_perf`, `performance_guardian`, `seo_analytics`).
2. **Fallback synthetic analytics branches** in SEO/web-vitals analytics path conflict with enterprise no-fabrication requirement.
3. **Multiple ingest streams without universal correlation id**, making root-cause reconstruction expensive.
4. **Plain text logging** limits machine parsing and SIEM portability.

---

## 5) Immediate P0 Conclusions (Before Implementation)

To satisfy the 14-step enterprise directive, platform needs:
1. OTel-based unified telemetry foundation.
2. Mandatory request correlation IDs and trace propagation.
3. JSON structured logging with trace/session/user context.
4. Unified metrics/traces/logs storage contracts.
5. Removal of synthetic fallback output in observability-facing routes.

Audit complete. Safe to proceed to architecture + implementation phase.
