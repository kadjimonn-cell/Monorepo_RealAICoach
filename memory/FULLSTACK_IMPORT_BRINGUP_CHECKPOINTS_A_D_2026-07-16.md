# Full-Stack Import Bring-up — Checkpoints A–D (2026-07-16)

Task: import RealAICoach-Web-Version repo into new Emergent full-stack job, serve as-is (per /app/MIGRATION_NOTES_FULLSTACK_IMPORT.md), verify end-to-end, deployment readiness check.

## Checkpoint A — Baseline evidence
| Item | State at start |
|---|---|
| backend (supervisor) | STOPPED — python deps not installed in /root/.venv |
| expo (supervisor) | STOPPED; after deps: crash-loop `Cannot find module 'babel-preset-expo'` |
| frontend node_modules | Partial (~740 top-level dirs; transitive deps missing) |
| yarn install | FAILED: `SyntaxError: Invalid value type 185:0 in yarn.lock` |
| local MongoDB (realtalk_db) | Empty (0 users) |
| /app/memory/test_credentials.md | MISSING |
| METRO_PROBE_PORT | 3000 in backend/.env (correct, line 117) |

## Checkpoint B — Root causes
1. **yarn.lock corruption**: 349 `integrity` lines corrupted into pattern `sha1-<b64>=sha512-<X>== sha512-<X>==` (sha1 hash concatenated to sha512 without separator — likely GitHub import artifact). Yarn v1 parser aborts at first occurrence (reported 185:0).
2. **Backend deps**: fresh pod, requirements.txt not installed; kkiapay==0.0.6 pins requests==2.22.0 and breaks resolution.
3. **DB empty**: fresh local Mongo — needs seed + admin self-registration (auto-promote via ADMIN_EMAILS).
4. **Transient Metro OOM (exit 134)** during first cold double-bundle (~3,076 modules web+SSR) while probes/screenshots hit the server; heap wrapper (5632MB) already in place; stabilized once /tmp/frontend-metro-cache warmed.
5. **Deployment blocker**: supervisor expo command lacked `--tunnel` (same fix as previous job's bring-up).

## Checkpoint C — Implementation
| Fix | File / action |
|---|---|
| yarn.lock repair | Rewrote 349 corrupted integrity lines to keep only the trailing sha512 token (awk); verified parse via @yarnpkg/lockfile (success, 1496 entries); backup at /tmp/yarn.lock.bak. `yarn install --frozen-lockfile` then succeeded (45s) |
| Backend deps | `pip install -r requirements.txt` minus kkiapay, then `pip install kkiapay==0.0.6 --no-deps` (per migration notes §3) into /root/.venv |
| DB seed | `python -m scripts.seed_data` with MONGO_URL/DB_NAME exported — all collections seeded |
| Admin account | POST /api/auth/register admin@realaicoach.app → auto-promoted (roles: admin, premium, user) |
| Credentials file | Created /app/memory/test_credentials.md |
| Supervisor tunnel fix | supervisord.conf expo command → `exec yarn expo start --tunnel --port 3000`; reread/update/restart |

## Checkpoint D — Final evidence
- `GET /api/health` → 200 `{"status":"healthy","service":"RealAICoach API"}` (local + external preview URL)
- Frontend: 200 on localhost:3000 and https://coach-web-preview.preview.emergentagent.com/ ; homepage renders (screenshot verified)
- UI admin login E2E: 10/10 tests passed (auto_frontend_testing_agent, 2026-07-16 05:56 UTC) — POST /api/auth/login 200, biometric prompt dismissible, redirect to authenticated dashboard "Welcome back, Admin", no console errors
- deployment_agent: **PASS** (after --tunnel fix), findings: []
- Known dev-mode noise (non-blocking): scheduler `web-preview-probe` 404 on `/_preview/health` (route exists only in production build; auto-restart disabled by WEB_PREVIEW_ALLOW_AUTORESTART=0 policy). metro-probe may restart expo if Metro cold-bundle blocks /status >2 consecutive probes — resolves once cache is warm.
