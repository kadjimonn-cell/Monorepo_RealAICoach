# [P1] Expo SDK 55 Upgrade — Coordinated Dependency Bump

**Ticket ID**: `GTEC-P1-EXPO55-${YYYYMMDD}`
**Source**: GTEC Scan v2 — `node_outdated` manual-review finding (§4)
**Priority**: P1
**Type**: Dependency upgrade (coordinated SDK)
**Risk**: MEDIUM-HIGH (cross-cutting: native modules, router, metro, web export)
**Estimated effort**: 1–2 engineering days
**Blocks**: clearing remaining `medium`-severity `node_outdated` findings in `STATUS=FAIL` scans.

---

## 1. Background

RealAICoach is currently on **Expo SDK 54**. GTEC Scan v2 reports 25 Expo-
family packages, 10 React-Native-family packages, and 10 other majors as
outdated. This cannot be piecemeal-upgraded: Expo modules are version-locked
to the SDK (every `expo-*` package at `v55.x` must match `expo@55`).

## 2. Scope — exact package list (from `yarn outdated`, 2026-04-24)

### Group A — Expo SDK (25 packages, **must upgrade together**)
| Package | Current | Target |
|---|---|---|
| expo | 54.0.33 | 55.0.17 |
| @expo/cli | 54.0.23 | 55.0.26 |
| @expo/metro-runtime | 6.1.2 | 55.0.10 |
| @expo/vector-icons | 15.0.3 | 15.1.1 |
| expo-router | 6.0.23 | 55.0.13 |
| expo-blur | 15.0.8 | 55.0.14 |
| expo-clipboard | 8.0.8 | 55.0.13 |
| expo-constants | 18.0.13 | 55.0.15 |
| expo-device | 8.0.10 | 55.0.15 |
| expo-document-picker | 14.0.8 | 55.0.13 |
| expo-font | 14.0.11 | 55.0.6 |
| expo-haptics | 15.0.8 | 55.0.14 |
| expo-image | 3.0.11 | 55.0.9 |
| expo-image-picker | 17.0.10 | 55.0.19 |
| expo-linear-gradient | 15.0.8 | 55.0.13 |
| expo-linking | 8.0.11 | 55.0.14 |
| expo-local-authentication | 17.0.8 | 55.0.13 |
| expo-location | 19.0.8 | 55.1.8 |
| expo-notifications | 0.32.16 | 55.0.20 |
| expo-speech | 14.0.8 | 55.0.13 |
| expo-splash-screen | 31.0.13 | 55.0.19 |
| expo-status-bar | 3.0.9 | 55.0.5 |
| expo-symbols | 1.0.8 | 55.0.7 |
| expo-system-ui | 6.0.9 | 55.0.16 |
| expo-web-browser | 15.0.10 | 55.0.14 |

### Group B — React Native family (10 packages, upgrade with SDK)
| Package | Current | Target |
|---|---|---|
| react-native | 0.81.5 | 0.85.2 |
| react-native-reanimated | 4.1.6 | 4.3.0 |
| react-native-gesture-handler | 2.28.0 | 2.31.1 |
| react-native-screens | 4.16.0 | 4.24.0 |
| react-native-safe-area-context | 5.6.2 | 5.7.0 |
| react-native-svg | 15.12.1 | 15.15.4 |
| react-native-webview | 13.15.0 | 13.16.1 |
| react-native-keyboard-controller | 1.18.5 | 1.21.6 |
| react-native-worklets | 0.5.1 | 0.8.1 |
| @react-native-async-storage/async-storage | 2.2.0 | 3.0.2 |

### Group C — Out-of-scope for this ticket (separate P2 tickets)
- `eslint 9 → 10`, `eslint-config-expo 10 → 55` (dev-only; schedule after SDK)
- `ajv 6 → 8`, `undici 6 → 8`, `markdown-it 12 → 14`, `minimatch 3 → 10`,
  `picomatch 2 → 4`, `yaml 1 → 2` (transitive; usually resolved by yarn dedupe)
- `typescript 5 → 6` (language version bump; dedicated ticket)

## 3. Acceptance Criteria (MUST ALL PASS — §4, §6, §7, §11)

- [ ] `yarn install` completes with **zero peer dependency warnings**.
- [ ] `yarn expo-doctor` reports **zero issues**.
- [ ] Web bundle exports cleanly: `yarn run expo export --platform web`
      completes in < 3 min, `dist/_expo/static` generated.
- [ ] **GTEC Scan v2** returns:
  - `STATUS: PASS`
  - `E2E_TESTS: PASS` on all 4 viewports (mobile, tablet, desktop, wide)
  - `RESPONSIVENESS: PASS`
  - `PERFORMANCE: PASS` (desktop p50 render ≤ 6 s)
  - No new `page_errors` or `console_errors` vs. pre-upgrade baseline
- [ ] No regression in `/api/errors/client/top` (React ErrorBoundary crashes
      must not increase in the 24 h post-deploy window).
- [ ] Native build (if iOS/Android apps are shipped via EAS) passes `eas build
      --platform all --profile preview` without errors.
- [ ] Production backend `X-GTEC-Directive-Version` header unchanged
      (backend-side is unaffected; confirms decoupling).

## 4. Pre-upgrade steps

1. **Capture baseline**: run GTEC Scan v2 with `viewports=mobile,tablet,desktop,wide`
   and archive the `task_id` as the pre-upgrade reference.
2. **Branch**: `feat/expo-sdk-55-upgrade` off main.
3. **Backup `package.json` + `yarn.lock`** in the branch's first commit.
4. **Check native module changes** for each `expo-*` in the Expo SDK 55 release
   notes: https://docs.expo.dev/workflow/upgrading-expo-sdk-walkthrough/

## 5. Execution steps

```bash
cd /app/frontend

# Automated path (preferred — Expo's own upgrade tool)
yarn expo install --fix
# This command reads the target SDK from expo@55.x and upgrades all
# expo-* + react-native* peers to compatible versions in one shot.

# Manual verification if the above misses anything:
yarn add expo@55 @expo/cli@55 @expo/metro-runtime@55 \
  expo-router@55 expo-blur@55 expo-clipboard@55 expo-constants@55 \
  expo-device@55 expo-document-picker@55 expo-font@55 expo-haptics@55 \
  expo-image@55 expo-image-picker@55 expo-linear-gradient@55 \
  expo-linking@55 expo-local-authentication@55 expo-location@55 \
  expo-notifications@55 expo-speech@55 expo-splash-screen@55 \
  expo-status-bar@55 expo-symbols@55 expo-system-ui@55 expo-web-browser@55

yarn add react-native@0.85 \
  react-native-reanimated@4.3 react-native-gesture-handler@2.31 \
  react-native-screens@4.24 react-native-safe-area-context@5.7 \
  react-native-svg@15.15 react-native-webview@13.16 \
  react-native-keyboard-controller@1.21 react-native-worklets@0.8

yarn add @react-native-async-storage/async-storage@3

# Health checks
yarn expo-doctor
yarn run expo export --platform web
node scripts/bump-sw.js
sudo supervisorctl restart expo_manual
```

## 6. Validation (runs the full directive pipeline — §5, §6, §7, §11)

```bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
# kick GTEC Scan v2 with all 4 viewports
curl -X POST "$API_URL/api/admin/gtec-scan-v2/run" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"viewports":"mobile,tablet,desktop,wide"}'
```

Required outcome: §12 email `[GTEC v2 · PASS] — crit=0 high=0` lands in
`admin@realaicoach.app` with all 6 pillars green.

## 7. Rollback plan (if scan fails)

Each step is reversible because we gated behind a branch. The directive
requires zero data loss (§2 Step 3) — **no DB schema changes are part of this
ticket**, so rollback is pure `git reset --hard <pre-upgrade-commit>` +
`yarn install` + `yarn run expo export --platform web`.

Expected rollback time: **< 5 min** (yarn cache is warm).

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| New peer dep conflict (React 19 vs RN 0.85) | Medium | Build failure | Run `yarn expo-doctor` before commit; use `yarn resolutions` if needed |
| `react-native-reanimated` worklets API change | Medium | Animation regression | Compare `app/executive-dashboard.tsx` micro-interactions before/after |
| `expo-router` v55 deep-link changes | Low-Medium | Broken links | Run crawler's `dynamic` route probes — GTEC already catches 401/403/404 paths |
| EAS build signing (if applicable) | Low | Store rejection | Keep EAS keys unchanged; test with `--profile preview` first |
| SSR/export differences breaking landing pages | Medium | White-screen on `/` | GTEC Scan v2 `white_screen` detector (body < 40 chars) catches this automatically |

## 9. Out of scope

- Upgrading `typescript` to 6.x (language break — separate ticket).
- Migrating from `yarn@1` to a newer package manager.
- Changing the `app.json` schema (SDK 55 is backward compatible).

## 10. Link back to GTEC Scan v2

- Finding label: `node_outdated`
- Fingerprint (SHA16): tracked in `gtec_scan_v2_memory` collection,
  accessible via `GET /api/admin/gtec-scan-v2/memory`.
- Recurrence count: each GTEC scan without this upgrade bumps the counter.
  When the upgrade ships, expected result: fingerprint removed from memory
  + `STATUS=PASS` on next scan.

---

**Status**: 🔵 OPEN · **Assignee**: _unassigned_ · **Target sprint**: _TBD_
**Source directive clause**: §4 (Auto-Remediation classifies `node_outdated`
as manual_required — not silently suppressed).
**Generated by**: GTEC Scan v2 triage, 2026-04-24.
