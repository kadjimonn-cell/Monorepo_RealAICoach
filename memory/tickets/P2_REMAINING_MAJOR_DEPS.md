# [P2] Coordinated Major-Dependency Bumps (non-Expo ecosystem) — STATUS UPDATE

**Ticket ID**: `GTEC-P2-MAJOR-DEPS-20260424`
**Source**: GTEC Scan v2 — `node_outdated` residual findings (§4)
**Priority**: P2
**Status**: **PARTIALLY DELIVERED** (see §3 for execution log)
**Risk**: MEDIUM
**Effort spent**: ~1 session (resumed after P1 Expo 55 delivery)

---

## 1. Delivered on 2026-04-24 (this session)

### Phase A — Direct alignment ✅
| Package | Before | After | Notes |
|---|---|---|---|
| `@expo/vector-icons` | `^15.0.3` (+ duplicate transitive `15.1.1`) | `^15.1.1` (single copy) | **Dedup resolved** — expo-doctor advisory cleared |
| `@expo/cli` | `54.0.23` | `55.0.26` | Aligned with Expo SDK 55 |

### Phase B — Resolution-pin bumps ✅
| Resolution | Before | After | Notes |
|---|---|---|---|
| `**/@eslint/plugin-kit` | `0.3.4` | `0.7.1` | ESLint internals |
| `**/markdown-it` | `12.3.2` | `14.1.1` | Tooling-only; no runtime impact |
| `**/picomatch` | `2.3.2` | `4.0.4` | Pattern matcher; tooling |
| `**/yaml` | `1.10.3` | `2.8.3` | Tooling-only |

### Phase C — Direct majors
| Package | Before | Result |
|---|---|---|
| `typescript` | `5.9.3` | **LANDED** at `6.0.3` — web export green, @typescript-eslint 8.x peer warning is advisory only |
| `eslint` | `9.39.4` | **ABORTED + reverted** to `9.39.4` — ESLint 10 breaks `eslint-plugin-react` rule API (`context.getFilename is not a function` in `react/display-name`). Requires plugin-level upgrades that are out of scope until `eslint-config-expo` supports v10. |
| `ajv` (resolution) | `6.14.0` → `8.18.0` | **ABORTED + reverted** — ESLint 9 internally loads `ajv/lib/refs/json-schema-draft-04.json` which ajv 8 dropped. Cannot bump ajv until ESLint can be bumped. |

### Build gates (all passing)
- `yarn run expo export --platform web` ✅ (~10s on cached state)
- `yarn lint` ✅ (1010 pre-existing warnings; **0 new regressions**)
- `curl /auth/login` → 200 ✅
- `curl /api/health` → 200 ✅

### Backups
- `/app/memory/backups/p2_stage_AB_20260424_031124/`
- `/app/memory/backups/p2_stage_C_ajv_20260424_031811/`

---

## 2. Still open (tracked for next iteration)

### Coupled revert: `eslint` + `ajv` (bundle)
These two must be bumped **together** because:
- ESLint 10 requires modern plugin APIs (esp. `eslint-plugin-react` 8+).
- ajv 8 requires ESLint 10+ (which doesn't use the removed draft-04 refs).
- Bumping either alone triggers the other's incompatibility.

Action items (next ticket):
1. Bump `eslint-plugin-react` (transitive via `eslint-config-expo`) — need
   upstream support from Expo. If Expo 55's `eslint-config-expo` still pulls
   an old `eslint-plugin-react`, either wait for Expo 56 or override via a
   yarn resolution once a compatible version ships.
2. Once plugins are compatible → bump `eslint@^10`.
3. Simultaneously bump `**/ajv` resolution to `8.18.0`.

### Other residual majors (GTEC `node_outdated`, all MEDIUM)
These are safer to defer; individually low-blast-radius:

- `@react-native-async-storage/async-storage` 2.2.0 → 3.0.2 (native module)
- `@xmldom/xmldom` 0.8.12 → 0.9.10 (currently resolution-pinned)
- `react-native` 0.83.6 → 0.85.2 (constrained by Expo 55 pin — wait for Expo 56)
- `react-native-worklets` 0.7.4 → 0.8.1 (Reanimated stack dependency)
- `undici` 6.24.0 → 8.1.0 (currently resolution-pinned to 6; bump together
  with `ajv`/`eslint` bundle)
- `@babel/core` / `@babel/runtime` 7.28 → 7.29 (safe patches; can be landed
  anytime)

---

## 3. Execution log (2026-04-24)

1. `t+0s` — Baseline capture + backup to `p2_stage_AB_20260424_031124`.
2. `t+2s` — **Phase A.1**: dedup `@expo/vector-icons` (→ `^15.1.1`). Build green.
3. `t+10s` — **Phase A.2**: `@expo/cli` → `55.0.26`. Build green.
4. `t+150s` — Web export gate passes. Login 200, health 200.
5. `t+160s` — **Phase B**: bump 4 resolution pins in one shot. Build green.
6. `t+270s` — Smoke test on new bundle. All green.
7. `t+280s` — **Phase C.1**: `ajv` resolution → `8.18.0`. Build green.
8. `t+390s` — **Phase C.2**: `typescript@~6.0.3`. Build green (peer warning noted).
9. `t+410s` — **Phase C.3**: `eslint@^10.2.1`. Lint breaks with plugin API incompatibility.
10. `t+430s` — Abort per playbook §3.1 clause 2. Revert `eslint` → `^9.39.4`.
11. `t+440s` — Re-run `yarn lint` → works again with 1010 pre-existing issues, **0 new regressions**.
12. `t+450s` — ajv 8 resolution triggers "Cannot find module `ajv/lib/refs/json-schema-draft-04.json`" under ESLint 9. Revert `ajv` resolution → `6.14.0`.
13. `t+460s` — Final full build + smoke. All green.
14. `t+480s` — Updated this ticket + CHANGELOG.md.

---

## 4. GTEC findings delta (expected)

Pre-P2 (2026-04-24 02:59 scan):
- `node_outdated`: 44 MEDIUM

Post-P2 (this session) — landed closures:
- `@expo/cli` 54→55 (1)
- `@expo/vector-icons` dedup (1)
- `@eslint/plugin-kit` 0.3→0.7 (1)
- `markdown-it` 12→14 (1)
- `picomatch` 2→4 (1)
- `yaml` 1→2 (1)
- `typescript` 5→6 (1)

Projected `node_outdated` count post-P2: ~37 MEDIUM (from 44).

Still open (coupled/blocked): `eslint`, `ajv`, `undici`, `react-native`, `async-storage`, `xmldom`, `worklets`.

---

## 5. Exit criteria (this ticket)

- [x] Safest bumps landed and gated.
- [x] All abort conditions triggered correctly; backups preserved.
- [x] Build + smoke + lint gates all green post-session.
- [x] Follow-up work scoped clearly for next ticket.
- [ ] Final GTEC V2 scan rerun — deferred to next session (takes ~25 min;
      changes already verified via build/lint gates).
