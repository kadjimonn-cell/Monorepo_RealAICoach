## 1) Executive Verdict

> **Superseded note (2026-06-22):** Final cutover completed. Active runtime ownership has moved to `/app/backend/routes/watch_audio_shared.py`; `/app/backend/routes/watch_audio_hub.py` is now a deprecated tombstone wrapper module.

- **P1 Evaluation Status: PASS** — `watch_audio_hub.py` is now a legacy compatibility shell with Sports user wrappers retired; remaining responsibilities are clearly scoped and separable.
- **P2 Retirement Status: PASS** — `/api/videos/sports/*` legacy wrappers have been retired from router exposure; Sports traffic is now canonical on `/api/sports/v2/*`.
- **Governance** — executed under parity-freeze sign-off using locked protocol controls.

## 2) Checkpoint Matrix (A-D)

### A) Legacy Responsibility Inventory (Global System)

Remaining `watch_audio_hub.py` responsibilities after Sports wrapper retirement:

1. Audio Studio legacy compatibility routes (`/api/videos/audio-studio/*`) delegating to `audio_studio_v2`.
2. Podcasts legacy compatibility routes (`/api/videos/podcasts/*`) delegating to `podcasts_v2`.
3. Shared legacy helper surface still used by non-sports flows (catalog/drop orchestration + quota helper paths).
4. Admin behavioral ML runtime flag endpoints.

Sports user wrappers retired:

- Removed legacy route exposure for:
  - `/api/videos/sports/bootstrap`
  - `/api/videos/sports/secure-stream`
  - `/api/videos/sports/play`
  - `/api/videos/sports/follow-league`
  - `/api/videos/sports/unfollow-league`
  - `/api/videos/sports/reminder-settings`
  - `/api/videos/sports/daily-drop-inbox`
  - `/api/videos/sports/daily-drop-inbox/mark-listened`

### B) Controlled Deprecation Path (P1)

1. **Route-usage isolation**
   - Enforce canonical Sports endpoints in clients and tests: `/api/sports/v2/*` only.
2. **Contract realignment**
   - Shift regression contracts from legacy Sports wrappers to v2-native routes.
3. **Legacy shell minimization**
   - Keep `watch_audio_hub.py` only for still-live non-sports wrappers until explicit parity sign-off per feature.
4. **Future retirement gates**
   - Gate full module retirement on:
     - sustained route-level parity for audio/podcasts,
     - zero active client dependency on `/api/videos/*` legacy paths,
     - final governance sign-off.

### C) Retirement Execution (P2)

Completed in codebase:

1. Sports legacy wrappers removed from `watch_audio_hub.py` route surface.
2. Frontend residual Sports legacy calls migrated to v2 (`AudioCatalogTab.tsx`).
3. Backend contract suites updated to validate Sports on `/api/sports/v2/*`.
4. Public/skip contract updated from legacy secure-stream path to v2 secure-stream path.

### D) Risk & Rollback Safety

1. **Risk**: stale external clients calling retired Sports legacy routes.
2. **Mitigation**:
   - v2 endpoint parity already validated for Free + Admin paths.
   - tests shifted to canonical v2 routes to prevent regression drift.
3. **Rollback posture**:
   - if emergency compatibility is required, reintroduce explicit temporary 410/redirect stubs on `/api/videos/sports/*` without re-coupling service internals.
