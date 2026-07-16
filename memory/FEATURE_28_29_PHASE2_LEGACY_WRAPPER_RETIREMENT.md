## 1) Executive Verdict

> **Superseded note (2026-06-22):** This checkpoint remains historically valid; final runtime ownership has since moved to `/app/backend/routes/watch_audio_shared.py` with `watch_audio_hub.py` retained only as a deprecated tombstone.

- **PASS (P1)**: Remaining audio/podcasts compatibility wrappers in `watch_audio_hub.py` are now isolated behind explicit retirement gates.
- **PASS (P2 workflow)**: Feature-by-feature retirement is now controllable via telemetry-gated admin controls (`phase1_audio_wrappers` and `phase2_audio_podcasts_wrappers`).
- **PASS (no regression)**: Canonical v2 endpoints remain stable while legacy wrappers are retired/restored by phase toggles.

## 2) Checkpoint Matrix (A-D)

### A) Gate Architecture (Explicit Retirement Controls)

Implemented in `/app/backend/routes/watch_audio_hub.py`:

1. Retirement controls key/phase model:
   - `watch_videos_legacy_wrapper_retirement`
   - phases: `observe`, `phase1_audio_wrappers`, `phase2_audio_podcasts_wrappers`
2. Gate readiness calculator over legacy-usage telemetry:
   - events + active-users thresholds
3. Gate enforcement:
   - wrapper family retired → `410 Gone` + migration hint (`/api/audio-studio/v2/*`, `/api/podcasts/v2/*`)
4. Environment fallback toggles:
   - `RETIRE_VIDEOS_AUDIO_WRAPPERS`
   - `RETIRE_VIDEOS_PODCAST_WRAPPERS`
   - `RETIRE_VIDEOS_AUDIO_PODCAST_WRAPPERS`

### B) Telemetry + Admin Controls (Global System)

New admin endpoints under `/api/videos/admin/`:

1. `GET /legacy-wrapper-retirement-readiness`
   - admin-only readiness snapshot per family (`audio_studio`, `podcasts`)
2. `POST /legacy-wrapper-retirement-controls`
   - admin-only phase control with gate validation and optional force apply
3. Telemetry collection:
   - `watch_videos_legacy_wrapper_telemetry`
   - captures wrapper path hits to support zero-consumer retirement decisions

### C) Consumer Migration (Feature-by-Feature Removal Prereq)

Frontend migration completed for shared catalog tab:

- `/app/frontend/src/components/AudioCatalogTab.tsx`
  - audio moved from `/videos/audio-studio/*` to `/audio-studio/v2/*`
  - podcasts moved from `/videos/podcasts/*` to `/podcasts/v2/*`
  - sports remains on `/sports/v2/*`

This removes first-party frontend dependency on legacy audio/podcast wrapper paths.

### D) Verification Evidence

1. Pytest focused runs passed:
   - retirement controls + phase behavior + reset behavior
2. Testing agent report:
   - `/app/test_reports/iteration_366.json` → 33/33 pass
3. Backend deep verification:
   - phase matrix confirmed:
     - phase1: audio wrappers retired, podcasts legacy active
     - phase2: both retired
     - reset observe: legacy restored
4. Sports retirement state preserved:
   - legacy sports remains retired; `/api/sports/v2/*` healthy
