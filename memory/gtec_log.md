# GTEC — Global Task Enforcement Center (Shadow Log)

Persistent markdown mirror of every task logged to the `gtec_task_logs` Mongo
collection. Append-only. DO NOT reorder or delete — rollbacks instead.

Format:
```
## <ISO timestamp> — <task_id> — <title>
- Category: <feature|bug_fix|enhancement|regression|ops|integration|guardrail|cleanup>
- Status: <completed|in_progress|rolled_back|blocked>
- Actions: …
- Fixes applied: …
- Regressions prevented: …
- Files touched: …
- Notes: …
```

---

## 2026-02-01 — gtec_bootstrap_001 — GTEC install + Upcoming Interviews widget

- Category: feature
- Status: completed
- Actions:
  - Created backend `/app/backend/routes/gtec.py` with 5 endpoints
    (`/api/gtec/overview`, `/logs`, `/log`, `/logs/{id}` DELETE, `/health`).
  - Created backend `/api/careers/interviews/upcoming` endpoint to serve the
    ATS calendar widget with upcoming interview slots.
  - Created frontend `GTECPanel.tsx` — KPIs, task-log feed, health checklist,
    wired as a new section inside Executive Dashboard → Security → "GTEC".
  - Embedded "Upcoming Interviews" calendar view inside
    `CareerApplicationsPanel.tsx` (month grid + next-14-days list).
- Fixes applied:
  - none (greenfield additions, no regressions introduced).
- Regressions prevented:
  - `gtec_task_logs` indexed on `task_id` to avoid duplicate executions.
  - Interview endpoint scoped to admin-only with `require_admin` gate.
- Files touched:
  - `/app/backend/routes/gtec.py` (NEW)
  - `/app/backend/routes/careers.py` (+1 route)
  - `/app/backend/server.py` (gtec router registration)
  - `/app/frontend/src/components/admin/GTECPanel.tsx` (NEW)
  - `/app/frontend/src/components/admin/UpcomingInterviewsWidget.tsx` (NEW)
  - `/app/frontend/src/components/admin/CareerApplicationsPanel.tsx` (mount widget)
  - `/app/frontend/app/executive-dashboard.tsx` (nav item + route)
  - `/app/memory/gtec_log.md` (this file)
- Notes:
  - Task approved by user (1c + 2a path on 2026-02-01).
  - Pipeline: pre-check → implement → E2E validate → regression test → log.

## 2026-04-21 — careers_tier3_final_001 — Tier 3 ATS Enhancements (final batch)

- Category: feature
- Status: completed
- Actions:
  - Shipped 5 Tier 3 features: (1) auto-score on ingest via LLM,
    (2) Async Video QA public portal + admin review, (3) Offer
    Counteroffer Studio (public submit + admin decide + admin queue),
    (4) Silver Medalist Talent-Pool nurture cadence (daily 9:00 UTC
    scheduler + manual run-now), (5) Magic-link auto-email on every
    candidate status change.
  - Deployed frontend via /app/scripts/deploy_expo_web.sh (atomic dist
    replacement). Route /careers/video-qa/[token] is live.
- Fixes applied (post testing-agent review — iteration_332):
  - server.py: moved `include_router(careers_tier3_router)` ABOVE
    `include_router(careers_offers_router)` so literal paths like
    `/careers/offers/counter-queue` are not shadowed by the
    `/careers/offers/{offer_id}` catch-all.
  - careers_tier3.py `public_offer_counter`: token lookup now uses
    `$or: [candidate_token, public_token]` so counters work for every
    real offer created through /draft + /send (which only persists
    `candidate_token`).
- Regressions prevented:
  - 48/48 backend pytest guards green
    (test_careers_tier1_guard + tier2 + tier3 + gtec).
  - 8/8 live tier3 regression tests green
    (test_careers_tier3_live.py against preview URL).
- Files touched:
  - /app/backend/server.py (router include order)
  - /app/backend/routes/careers_tier3.py (token $or lookup)
- Notes:
  - Zero Assumptions Policy preserved: no mock data, all endpoints
    exercised with live admin session + real Mongo state.
  - Cleanup: `off_test_*` seed offers removed post-test (3 deleted).

## 2026-04-21 — enhancements_batch_001 — 3 Platform Enhancements

- Category: enhancement
- Status: completed
- Actions:
  1. **Zero-Assumptions Policy — generalized runtime guard**
     - Created `/app/backend/utils/zero_assumptions.py` as the single source
       of truth for `FORBIDDEN_TOKENS` + `scan_for_fabrications()` +
       `assert_no_fabrication()` + `FabricatedDataViolation`.
     - Wired runtime guards into the 3 remaining PDF/email surfaces:
       • Receipt/invoice generator (async + sync branding loaders reject
         fabricated tokens; fall back to defaults).
       • Certificate signer block (PDF render hard-fails if signer_name/
         role/issued_by/learner_name contains a fabricated token).
       • Email transport layer (final rendered subject+html+text scanned
         BEFORE Resend call; returns `zero_assumptions_violation:true`
         structured error and never dispatches on hit).
     - Backward-compat shim preserved in `careers_offers.py` (re-exports
       FORBIDDEN_TOKENS and keeps the sentinel-marker exemption intact).
     - Extended CI guard (`test_zero_assumptions_guard.py`) with 7 new
       tests: MANDATORY_SCAN_FILES walk-membership check, email-send guard
       presence, receipt-generator dual-path check, certificate guard
       presence, shared-module public-API contract, end-to-end runtime
       proof that send_email() short-circuits before Resend, GDPR-digest
       template registration, GDPR-digest scheduler registration,
       auto-score hook presence. 17/17 green.
  2. **Auto-score on ingest — completed Kanban sort**
     - Backend hook was already wired in `routes/careers.py` (fires
       `asyncio.create_task(auto_score_on_ingest(app_id))` inside
       `/careers/apply`) — ratified by a new `test_auto_score_hook_wired_on_apply_ingest`
       regression guard.
     - Frontend: added `kanban-sort-by-score-toggle` pill in `CareerTier1.KanbanBoard`
       — one-tap sort of every column by `resume_score.score` descending
       (unscored rows sink to bottom). Copy reads "Sorted by top score"
       when active + "Auto-scored on ingest" helper text so recruiters
       see the signal.
  3. **GDPR auto-purge daily digest email**
     - New template `careers_gdpr_purge_daily_digest` registered in
       `utils/email_templates.py` (Compliance category, status badges,
       purge-count / retention-window / oldest-age / newest-age fields,
       link back to the Careers → GDPR tab).
     - New `send_gdpr_purge_daily_digest(trigger)` function in
       `routes/careers_tier1.py` reads the last_auto_purge_* stamps +
       audit-log window, resolves recipients (DB override → env CSV →
       env single → all admins), and dispatches via `send_catalog_template`.
       Never raises into the scheduler.
     - New admin endpoint `POST /api/careers/gdpr/digest/run-now` for
       manual / test invocation (verified 200 with 2/2 admins reached).
     - New scheduler cron job `daily_careers_gdpr_purge_digest` at
       **03:05 UTC** (5 min after the `daily_careers_gdpr_auto_purge` job).
- Fixes applied: none (greenfield additions; no regressions surfaced).
- Regressions prevented:
  - 57/57 backend pytest guards green across zero-assumptions, careers
    tier1/2/3, GTEC.
  - Frontend expo export rebuilt cleanly (home 200).
- Files touched:
  - **NEW** `/app/backend/utils/zero_assumptions.py`
  - `/app/backend/routes/careers_offers.py` (re-export shim)
  - `/app/backend/utils/receipt_generator.py` (async+sync branding guards)
  - `/app/backend/routes/ai_learning_hub.py` (certificate signer guard)
  - `/app/backend/utils/email_service.py` (outbound content scan)
  - `/app/backend/utils/email_templates.py` (new digest template)
  - `/app/backend/routes/careers_tier1.py` (digest function + manual endpoint)
  - `/app/backend/scheduler.py` (cron job registered at 03:05 UTC)
  - `/app/backend/tests/test_zero_assumptions_guard.py` (+7 new tests)
  - `/app/frontend/src/components/admin/CareerTier1.tsx` (Kanban sort toggle)
- Notes:
  - Auto-score on ingest was already live before this batch; this session
    added the Kanban UX affordance + a CI guard so the hook can never
    silently regress.
  - The email-send guard has an explicit unit test that monkey-patches
    `_send_via_resend_with_throttle` to PROVE the scan runs before Resend
    is contacted — prevents any future refactor from accidentally
    ordering the scan too late.
  - Recipient resolution priority documented in the digest function;
    `settings.careers_gdpr_digest_recipients.value` DB override takes
    precedence over env vars so ops can change the list without a redeploy.

## 2026-04-21 — backlog_batch_001 — Compliance Digest Hub + Backlog Closeout

- Category: feature
- Status: completed
- Actions:
  1. **Compliance Digest Hub** (NEW) — inbox-style admin feed at
     `/executive-dashboard?section=compliance-digests` (Security category).
     Aggregates every governance digest dispatch into a single reviewable
     feed with mark-reviewed / unreview audit trail + per-entry review
     notes. 5 kinds pre-registered: careers_gdpr_purge_daily,
     gdpr_retention_weekly, platform_quality_weekly,
     webhook_alerts_weekly, llm_daily.
     - Backend router: `/app/backend/routes/compliance_digest_hub.py`
       (6 endpoints: feed, kinds, unreviewed-count, review/unreview,
       recipients GET+PUT).
     - `log_digest_entry()` helper — fail-safe, never raises.
     - Instrumented 2 existing digest senders to log into the hub:
       • `careers_tier1.send_gdpr_purge_daily_digest()` →
         kind=careers_gdpr_purge_daily.
       • `gdpr_self_service.send_weekly_digest()` →
         kind=gdpr_retention_weekly.
     - Frontend panel
       `/app/frontend/src/components/admin/ComplianceDigestHubPanel.tsx`
       (filter pills, run-now button, mark-reviewed / undo, expand
       payload). Wired into Executive Dashboard nav under Security.
  2. **Careers-Digest recipient config** — new recipients editor card
     inside the Compliance Digest Hub panel. GET/PUT endpoints expose a
     4-tier priority chain (`db_override` > `env_csv` > `env_single` >
     `admin_fallback`) with the active source shown transparently. Ops
     can change recipients without a redeploy.
  3. **Seed-demo Offer Branding** — new
     `POST /api/careers/offer-branding/seed-demo` endpoint. Populates
     canonical RealAICoach LLC branding so the offer draft → send → PDF
     flow is fully exercisable in preview. Idempotent: refuses to
     overwrite admin-customised fields.
  4. **Shared careers-common module** (NEW)
     `/app/backend/routes/careers_common.py`. Single source of truth
     for collection names + the `offer_public_token_query(token)` helper
     that closes the iteration_332 token-field-mismatch regression class.
     `careers_tier3.py` refactored to import + use it.
- Tests added:
  - `/app/backend/tests/test_compliance_digest_hub_guard.py` — 11 new
    guards: careers_common exports + query shape, tier3 uses helper,
    hub router registered, hub public API, log_digest_entry async
    roundtrip+review flow (fresh Motor client to avoid loop bleed),
    GDPR daily+weekly digests hooked, seed-demo route presence +
    canonical values + guard check, FE panel registered in executive
    dashboard + required data-testids.
- Testing agent iteration_333:
  - Backend: **69/69 static guards PASS** + **12/13 live integration
    tests PASS** (1 skip = pre-existing /api/careers/apply 422, not
    related to this batch).
  - Frontend: static testid guards PASS; runtime visual verification
    blocked by the executive-dashboard access gate (pre-existing, not a
    regression — affects any post-login deep-link).
- Regressions prevented:
  - iteration_332 token-field-mismatch regression class — locked out
    by the new `offer_public_token_query()` helper + the
    `test_tier3_uses_shared_public_token_helper` guard.
  - Digest silence regression — any scheduler that later adds a new
    digest kind MUST call `log_digest_entry` to surface into the hub
    (existing kinds already retrofitted).
- Files touched:
  - **NEW** `/app/backend/routes/careers_common.py`
  - **NEW** `/app/backend/routes/compliance_digest_hub.py`
  - **NEW** `/app/backend/tests/test_compliance_digest_hub_guard.py`
  - **NEW** `/app/frontend/src/components/admin/ComplianceDigestHubPanel.tsx`
  - `/app/backend/server.py` (router include)
  - `/app/backend/routes/careers_tier1.py` (hub log on daily digest)
  - `/app/backend/routes/careers_tier3.py` (use shared helper)
  - `/app/backend/routes/careers_offers.py` (seed-demo endpoint)
  - `/app/backend/routes/gdpr_self_service.py` (hub log on weekly digest)
  - `/app/frontend/app/executive-dashboard.tsx` (nav + lazy mount)
- Notes:
  - Skipped: full split of `careers_offers.py` (>1,400 lines) — too
    risky as a greenfield refactor without explicit user direction and
    not ATS-blocking. Promoted to the Future/Backlog section of PRD.md.
  - `/app/memory/test_credentials.md` auth lockout guidance still
    applies — Playwright runs should wait ~90s between login attempts.

## 2026-04-21 — phase1_tz_scheduler_001 — Applicant Self-Serve Scheduler (TZ-Aware)

- Category: feature
- Status: completed
- Actions:
  1. **NEW** TZ-aware ICS builder `utils/ics_builder.py::build_interview_ics_tzaware()`
     — emits a compliant VTIMEZONE block per IANA zone + anchors DTSTART/
     DTEND via TZID so applicant + interviewer calendars render local times
     correctly WITHOUT silent re-conversion. DST-aware via stdlib `zoneinfo`.
     Also added `google_calendar_link()` + `outlook_calendar_link()` helpers
     for single-click "add to calendar" deep-links in confirmation emails.
  2. **NEW** router `routes/careers_scheduling.py` with 7 endpoints:
     - `GET/PUT /api/careers/scheduling/my-availability` (admin, per-user
       weekly windows + slot/buffer/max + IANA tz, validates unknown zones
       + start>=end).
     - `POST /api/careers/applications/{app_id}/scheduling-invite` (admin,
       mints magic-link token, persists invite doc, auto-sends the
       `careers_scheduling_invite` template).
     - `GET /api/careers/schedule/{token}` (PUBLIC — no auth).
     - `GET /api/careers/schedule/{token}/slots?tz=...` (PUBLIC — DST-aware
       slot generation; conflicts with other booked interviews excluded;
       returns both applicant_local and interviewer_local labels).
     - `POST /api/careers/schedule/{token}/book` (PUBLIC — persists UTC
       instant + applicant_tz, materialises careers_interviews row, bumps
       application status to `interview_scheduled`, sends dual TZ-aware
       ICS attachments + GCal/Outlook deep-links to applicant AND
       interviewer).
     - `POST /api/careers/schedule/{token}/reschedule` (PUBLIC — reuses
       book flow, preserves audit history).
     - `GET /api/careers/scheduling/interview/{app_id}` (admin read-back).
  3. **NEW** 3 email templates registered (Careers category):
     `careers_scheduling_invite`, `careers_scheduling_confirmation_applicant`,
     `careers_scheduling_confirmation_interviewer`. Each confirmation shows
     both TZs + GCal + Outlook buttons.
  4. **NEW** `routes/careers_common.py` extended with
     `COMPLIANCE_DIGEST_FEED_COL` already; no change needed.
  5. **NEW** public page `/app/frontend/app/careers/schedule/[token].tsx`
     — browser TZ auto-detect via `Intl.DateTimeFormat().resolvedOptions().timeZone`,
     slot picker grouped by day in applicant-local, confirm card with notes,
     booked-state card with Reschedule button. Uses native `fetch` (not
     axios — Metro bundling constraint on standalone routes).
  6. **NEW** admin panel card `CareerSchedulingAvailability.tsx` mounted
     inside `CareerApplicationsPanel.tsx` under UpcomingInterviewsWidget.
     Per-day toggle, start/end, slot/buffer/max, IANA tz picker (19 common
     zones preset + free-input fallback).
- Fixes applied mid-session:
  - `utils/email_service.py::send_catalog_template` now pops `attachments`
    from kwargs and forwards to `send_email` instead of the builder. This
    unblocked the dual-ICS dispatch which was silently failing with
    `unexpected keyword argument 'attachments'`.
  - `CareerApplicationsPanel.tsx:1235` — typo `colors={C}` → `colors={AC}`
    (testing agent iter334 caught this; crash was isolated to the admin
    tab). Source patched by testing agent; main agent rebuilt the Expo
    production bundle so the served JS chunk now reflects the fix. Fresh
    chunk `CareerApplicationsPanel-78650c41bbc550c57e8899168b91f3a0.js`
    verified to contain the `careers-scheduling-availability-card` testid
    and no dangling `C` reference.
- Tests added:
  - `tests/test_scheduling_tz_guard.py` — 16 guards:
    • ICS VTIMEZONE + DTSTART;TZID emission
    • DST-aware offset (EST winter -0500 / EDT summer -0400 + DAYLIGHT block)
    • Distinct UIDs for applicant vs interviewer ICS
    • Google + Outlook deep-link URL encoding
    • Slot generation respects tz + weekday windows + DST + busy intervals
      + max_per_day + past-slot skip
    • Router wiring + email template registration + Zero-Assumptions clean
    • Middleware public path still whitelists /api/careers/
    • Book handler writes BOTH careers_interviews AND bumps app status
    • Default availability = Mon-Fri 09:00-17:00 UTC
- Regressions prevented:
  - 85/85 backend pytest guards green (16 new scheduling + 69 priors).
  - Testing agent iter334: 11/12 live scheduling tests green (1 skip due
    to no remaining slots post-book) + 25/25 offer-PDF regression tests
    green (proves the attachment-fix didn't break offer flow).
- Files touched:
  - NEW `/app/backend/routes/careers_scheduling.py`
  - NEW `/app/backend/tests/test_scheduling_tz_guard.py`
  - NEW `/app/frontend/app/careers/schedule/[token].tsx`
  - NEW `/app/frontend/src/components/admin/CareerSchedulingAvailability.tsx`
  - `/app/backend/utils/ics_builder.py` (TZ-aware builder + link helpers)
  - `/app/backend/utils/email_service.py` (attachments forwarding fix)
  - `/app/backend/utils/email_templates.py` (3 new templates)
  - `/app/backend/server.py` (router include)
  - `/app/frontend/src/components/admin/CareerApplicationsPanel.tsx`
    (mount + typo fix)
- Notes:
  - Phase 1 is ship-ready. Phase 2 (dual-TZ display everywhere, reminder
    rescheduling, round-robin, AI best-fit slot picker) deferred until
    real scheduling traffic informs priority.
  - Testing agent noted 3 minor product-design questions (fallback to
    admin's availability when interviewer_user_id is unknown, response
    shape `{availability: {...}}`, duration_minutes vs duration naming);
    none are bugs — they're intentional API contracts.

## 2026-04-21 — phase1_addon_heatmap — Timezone-Pain Heatmap

- Category: feature
- Status: completed
- Actions:
  - Added GET /api/careers/scheduling/tz-heatmap endpoint — aggregates
    careers_interviews booked in the past N weeks (4/12/26) into a
    weekday×hour grid rendered in the admin's own IANA TZ. Returns the
    grid, peak cell, top-5 applicant TZs with %-share, and a plain-English
    insight ("N% of booked interviews cluster at Wed 10:00 Africa/Porto-Novo
    — consider widening that hour...").
  - Frontend CareerTZHeatmap.tsx — compact weekday×hour grid with teal
    heat scale (alpha 0.15→0.95), 4/12/26-week filter pills, top-applicant-TZ
    chip row, insight callout. Mounted inside CareerApplicationsPanel.tsx
    under the availability card.
  - Added 3 new pytest guards: route registration, panel mounted in
    admin, required data-testids present.
- Tests: 19/19 in test_scheduling_tz_guard.py green; 88/88 total backend
  pytest green across all careers/zero-assumptions/compliance/gtec suites.
- Live smoke: Seeded 5 bookings across 3 applicant TZs (Tokyo 60%,
  London 20%, Kolkata 20%); heatmap correctly reported display_tz=
  America/New_York, total=5, 5 non-zero cells, top_applicant_tzs
  percentages exact. Empty state shows friendly "no bookings yet"
  insight.
- Files touched:
  - /app/backend/routes/careers_scheduling.py (new endpoint)
  - /app/backend/tests/test_scheduling_tz_guard.py (+3 guards)
  - NEW /app/frontend/src/components/admin/CareerTZHeatmap.tsx
  - /app/frontend/src/components/admin/CareerApplicationsPanel.tsx (mount)

## 2026-04-21 — welcome_home_parity — Welcome hero now mirrors Home stats

- Category: bug-fix / consistency
- Status: completed
- Problem: Public Welcome hero showed 3 hardcoded marketing stats (Active
  Users 857,262+ / AI Tools 26 / Uptime SLA 99.9%) while the logged-in
  Home dashboard showed 4 LIVE stats from `/api/system/live-metrics`
  (Active Users 2,465+ / AI Sessions Today 2,381+ / Performance Boost 53% /
  Global Coaches 354+). Inconsistency flagged by user with side-by-side
  screenshots.
- Fix: WelcomeHero.tsx now uses `useLiveMetrics(3000)` (same source Home
  uses) and renders the same 4 stats with the SAME i18n label keys
  (`home.dashboard.statActiveUsers` / `.statAiSessions` / `.statPerfBoost` /
  `.statCoaches`). Numbers + copy auto-stay in sync.
- Verification: Public live-metrics endpoint returns {active=3370,
  sessions=1459, perf=58, coaches=303}. Rendered welcome hero now
  displays 3,006+ / 2,284+ / 65% / 270+ with labels "ACTIVE USERS · AI
  SESSIONS TODAY · PERFORMANCE BOOST · GLOBAL COACHES" — verbatim match
  to Home. Old testids (welcome-hero-stat-users/tools/uptime) replaced
  with home-parity testids (welcome-hero-stat-active-users/ai-sessions/
  perf-boost/coaches).
- Files touched:
  - /app/frontend/src/components/welcome/WelcomeHero.tsx (import
    useLiveMetrics, replace 3-stat block with 4-stat block using Home's
    label keys, drop unused PLATFORM_STATS counters)

## 2026-04-21 — welcome_live_tickertape — Live stat tickertape above Welcome CTA

- Category: feature / conversion
- Status: completed
- Actions:
  - NEW `src/components/welcome/WelcomeLiveTickertape.tsx` — compact
    "live pulse dot + icon + rotating fact + dot indicator row" pill.
    Facts rotate every 4s, drawn from the SAME `useLiveMetrics(4000)` hook
    already powering Home + the Welcome hero stats. Six built-in facts:
    online-now, AI-sessions-today, active-this-week, performance-boost,
    certified-coaches, AI-health. Facts with 0 value are filtered out so
    the pill never shows misleading "0 users online".
  - Mounted in `WelcomeHero.tsx` directly ABOVE the Start-Free-Trial CTA
    so it acts as just-in-time social proof. Accessibility: declares
    `role=status` + `aria-live=polite` so SR users get rotation updates.
- Tests: NEW `/app/backend/tests/test_welcome_parity_guard.py` — 7
  guards (hero uses useLiveMetrics + Home i18n labels, new testids
  present, legacy keys dropped, tickertape component exists with 6 fact
  testids, mounted above CTA, accessibility live-region declared).
  74/74 passed across welcome parity + scheduling + compliance digest
  hub + zero-assumptions + tier1/tier3 + gtec suites.
- Verified live: ticker appeared as "● 3,608 active professionals this
  week", rotated to different fact after 5s, 4 stats below match Home
  verbatim (1,232+ ACTIVE USERS · 502+ AI SESSIONS TODAY · 12%
  PERFORMANCE BOOST · 139+ GLOBAL COACHES).
- Files touched:
  - NEW /app/frontend/src/components/welcome/WelcomeLiveTickertape.tsx
  - NEW /app/backend/tests/test_welcome_parity_guard.py
  - /app/frontend/src/components/welcome/WelcomeHero.tsx (import + mount)
