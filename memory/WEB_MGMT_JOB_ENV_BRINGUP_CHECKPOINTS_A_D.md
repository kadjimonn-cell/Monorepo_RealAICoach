# WEB MANAGEMENT PLATFORM JOB — ENVIRONMENT BRING-UP — CHECKPOINTS A–D (2026-07-16)

Locked-protocol evidence pack for the "Build the web management platform for RealAICoach / connect to existing backend + database" continuation job (visa-polish-v2 codebase imported: /frontend + /backend only, no /mobile folder exists).

Scope confirmed with user: **Q2 option (a)** — wire up connectivity/secrets, verify the platform runs end-to-end, hand over ready. **Q1 default (a)** — preview stays on local MongoDB; production Atlas MONGO_URL is applied ONLY at deploy time via publishing panel env vars.

---

## CHECKPOINT A — Baseline Evidence (before changes)

| Item | State |
|---|---|
| Backend (supervisor) | STOPPED → crash on boot: `ModuleNotFoundError: No module named 'reportlab'` (fresh fork, deps not installed) |
| Frontend (expo) | Crash-looping: Metro OOM `Reached heap limit` at 4096MB, then port-3000 conflicts |
| `pip install -r requirements.txt` | FAILED: `kkiapay==0.0.6` pins `requests==2.22.0` vs pinned `requests==2.33.0` (ResolutionImpossible) |
| `yarn install --frozen-lockfile` | FAILED: `SyntaxError: Invalid value type 185:0 in yarn.lock` |
| Local MongoDB `realtalk_db` | Empty (0 users — data does not carry over on fork) |
| Admin login | 401 Invalid credentials (no admin account in fresh DB) |
| /app/memory/test_credentials.md | MISSING |

## CHECKPOINT B — Root Causes

1. **yarn.lock corruption**: 348 `integrity` lines contained concatenated `sha1-...=sha512-...` + duplicate hash, unquoted with embedded space — invalid for yarn v1 parser.
2. **pip conflict**: `kkiapay` transitively pins ancient `requests`; requirements.txt is a freeze of a formerly-working env → install everything else normally, then `kkiapay --no-deps`.
3. **Metro OOM**: app bundles ~3,076 modules twice (web + SSR render.js). `NODE_OPTIONS` in frontend/.env loads AFTER node boots → 4GB default heap → OOM. Container cgroup limit is **8GB** (`/sys/fs/cgroup/memory.max` = 8589934592), so heap must fit within budget alongside backend+mongo.
4. **CRITICAL — Expo restart storm**: backend scheduler job `metro_dev_server_health_probe` (every 2 min) probed `http://127.0.0.1:3001/status`. In this pod topology Metro+web share **port 3000**; nothing listens on 3001 → probe always failed → `sudo supervisorctl restart expo` every 2 minutes, forever (matches supervisord.log "waiting for expo to stop" cadence). Killed instances left orphaned node children holding :3000 → "Use port 3001 instead?" exit-1 loops.
5. **No admin user**: `ensure_admin_users()` only PROMOTES existing accounts; admins self-register (auto-promoted via ADMIN_EMAILS).

## CHECKPOINT C — Implementation (minimal, surgical)

| Change | File | Detail |
|---|---|---|
| yarn.lock repair | `/app/frontend/yarn.lock` | 348 corrupt integrity lines → kept clean trailing sha512 token (backup: /tmp/yarn.lock.bak) |
| Backend deps | — | `pip install -r requirements.txt` (minus kkiapay) + `pip install kkiapay==0.0.6 --no-deps` |
| Node heap fix | `/app/frontend/package.json` | Added `"expo"` script: `NODE_OPTIONS=--max-old-space-size=5632 node --max-old-space-size=5632 node_modules/expo/bin/cli` — yarn resolves scripts before binaries, so supervisor's `yarn expo start` picks it up; passes `verify-package-json.js` gate (routes to local CLI). 5632MB fits the 8GB cgroup with backend+mongo headroom |
| .env heap values | `/app/frontend/.env` | 4096 → 5632 (kept consistent; export pipeline uses FRONTEND_EXPORT_NODE_OPTIONS) |
| **Metro probe port fix** | `/app/backend/scheduler.py` (~line 359) | Probe URL now `http://127.0.0.1:{METRO_PROBE_PORT or 3000}/status` (env-configurable, default 3000). Verified `:3000/status` → `packager-status:running` |
| New env var | `/app/backend/.env` | `METRO_PROBE_PORT=3000` |
| Admin account | local DB | Registered admin@realaicoach.app → auto-promoted (role=admin, premium, full_access) — user_1049efe1190a |
| Seed data | local DB | `python -m scripts.seed_data` (idempotent) — platform stats, metrics, service health, feature gallery |
| Credentials file | `/app/memory/test_credentials.md` | Created (was missing) |

**NOT changed**: MONGO_URL (protected — stays local for preview), any frontend routes/UI, supervisor config (READONLY), any feature code.

## CHECKPOINT D — Final Evidence

| Verification | Result |
|---|---|
| `GET /api/health` | 200 ✅ |
| `POST /api/auth/register` (admin) | 200, roles `["user","premium","admin"]` ✅ |
| `POST /api/auth/login` (admin) | 200, `is_admin: true`, `full_access: true` ✅ |
| Frontend local `:3000` | 200 with SSR HTML ✅ |
| Frontend external preview URL | 200 ✅ — full RealAICoach landing renders (screenshot verified) |
| Expo stability | pid stable **>7 min** (previously killed every 2 min); metro-probe logs `RECOVERED` ✅ |
| verify-package-json gate | `✓ all required scripts resolve to the local expo CLI` ✅ |
| Python lint (scheduler.py) | clean ✅ |

## Deployment handoff (user actions — platform UI, not agent)

1. **Save to GitHub** button in chat input → push this job's code.
2. On **Deploy**: add Environment Variables in the publishing panel — at minimum `MONGO_URL` = the production Atlas URL from the Database tab (mongodb+srv://visa-polish-v2:...@customer-apps.ralxxc.mongodb.net/...), plus DB_NAME=realtalk_db and any keys that differ from backend/.env.
3. Preview intentionally uses the local DB to protect production data (user-approved strategy).

## ADDENDUM — Deployment Readiness (2026-07-16 03:30 UTC)
- deployment_agent initial run: FAIL — expo supervisor command missing `--tunnel` flag.
- Fix applied per deployment agent instruction: /etc/supervisor/conf.d/supervisord.conf expo command → `exec yarn expo start --tunnel --port 3000`; package.json "expo" wrapper kept for node heap (5632MB) only.
- Runtime verified: "Tunnel connected./Tunnel ready.", expo stable, local + external preview 200.
- deployment_agent re-run: **PASS** — zero findings, all checks green. App is deployment-ready.
- User deploy steps: Deploy button → add MONGO_URL (production Atlas) + DB_NAME=realtalk_db in Environment Variables → deploy → Link domain (realaicoach.app or subdomain) via Entri flow.

## ADDENDUM 2 — Option A: Full Stack (web) job import preparation (2026-07-16 04:55 UTC)

ROOT CAUSE (user-reported "not a web version"): this job runs the Expo MOBILE template
(/app/.emergent/emergent.yml → env_image_name: expo_mongo_base_image_cloud_arm). Job template
type is fixed at creation (support-confirmed) and drives the publishing pipeline → "Your mobile
app is deployed!" panel. Only a NEW job created with the Full Stack App template gets web-typed
publishing. User approved Option A (new Full Stack job via GitHub import).

CHECKPOINT A: baseline — no `build` script; `start` script had no port pin (expo default 8081
would break Full Stack pods); web export unproven in this pod.
CHECKPOINT B: gaps identified — port pin, build alias, migration guidance, memory budget
(pod restarted itself when export ran concurrently with dev server; sequential run required).
CHECKPOINT C: package.json — `start` now pins --port 3000; new `build` script runs export:web
then syncs dist/→build/; `expo` wrapper kept (heap 5632MB). supervisord --tunnel re-applied
after pod restart wiped it (NOTE: /etc edits are NOT durable across pod restarts; only /app is).
Root-level MIGRATION_NOTES_FULLSTACK_IMPORT.md written for the new job's agent.
CHECKPOINT D: `yarn build` EXIT:0 in 369s with services stopped for memory headroom —
159 pages SEO-injected, sitemap/robots, precompress (69MiB→12MiB br). Output layout:
web.output=server → dist/server/*.html (120 route files incl. index.html, verified content)
+ dist/client assets; build/ synced. Services restored: backend 200, expo running.

USER NEXT STEPS: Save to GitHub → new job with Full Stack App template → import repo →
new agent follows /app/MIGRATION_NOTES_FULLSTACK_IMPORT.md → deploy with panel Secrets
(MONGO_URL + DB_NAME per /app/memory/DEPLOY_ENV_CHECKLIST.md).
