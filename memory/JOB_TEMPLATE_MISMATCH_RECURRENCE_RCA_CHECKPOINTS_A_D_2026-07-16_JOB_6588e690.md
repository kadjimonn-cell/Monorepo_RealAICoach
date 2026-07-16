# Job Template Mismatch RECURRENCE RCA — "Full Stack Web selected, Expo mobile provisioned + deployed" — Checkpoints A–D (2026-07-16)

Task: user created a NEW job explicitly as "Full Stack Web", imported the RealAICoach repo, deployed — and the publish panel again shows "Your mobile app is deployed!" (QR code, App/Play Store buttons). User demands root cause at global system level. Prior occurrence: /app/memory/JOB_TEMPLATE_MISMATCH_RCA_CHECKPOINTS_A_D_2026-07-16.md (job 22957321-afe5-4e3a-a232-116e4e47efa6).

## Checkpoint A — Baseline evidence (this job)
| Item | Evidence |
|---|---|
| Job identity | /app/.emergent/emergent.yml → job_id 6588e690-5465-466f-af17-34d3b02ca00d, created_at 2026-07-16T10:55Z (regenerated at publish time, matches "Publish 1 — 2 minutes ago" / commit 386cfc8) |
| Base image | env_image_name: "expo_mongo_base_image_cloud_arm:release-11022026-1" — the EXPO (mobile) base image, IDENTICAL tag to the prior mismatched job |
| App-level override | /app/config.json MISSING — no repo-side mechanism to declare app type |
| Pipeline classification | deployment_agent classified "Expo Mobile App" on every run (both jobs) |
| Publish outcome | Publish succeeded via the Expo MOBILE pipeline: panel says "Your mobile app is deployed!", offers QR/Expo Go + App/Play Store builds |
| Deployed host behavior | https://coach-web-preview.emergent.host → `/api/health` 200 (FastAPI up), BUT `/` and every web route return FastAPI JSON 404 `{"detail":"Not Found"}` (content-type application/json) with intermittent 520s. `/index.html`, `/auth/login`, `/about` → 404 |
| Interpretation of 404s | In the deployed topology ALL HTTP traffic routes to the FastAPI backend; NO web frontend is served. backend/server.py has no StaticFiles/catch-all web serving (verified). The Expo mobile pipeline deploys backend + Expo Go bundle only; it does NOT run the web export (`yarn build`) nor map `dist/server/*.html` |
| Migration-notes claim disproven | MIGRATION_NOTES §2 claimed "the Emergent expo publish pipeline understands this [web.output=server dist] layout natively" — production evidence (root 404) proves the MOBILE publish path does NOT serve the web build |
| Secondary finding | .gitignore lines 34-37 exclude .env from git (deployment_agent flags as blocker for pipeline config; did not cause this failure — publish succeeded, backend healthy) |
| Env churn explained | The ".env sync" observed all session is the app's own backend (`_sync_frontend_preview_env_keys` / `_sync_backend_preview_env_keys` in server.py) rewriting env keys to its detected canonical preview host — unrelated to the deploy mismatch |

## Checkpoint B — Root cause (global system level)
**PLATFORM-SIDE, DETERMINISTIC, REPO-CONTENT-DRIVEN TEMPLATE CLASSIFICATION.**
1. Emergent's job provisioning selects the runtime base image + deployment pipeline. For this repo — whose /frontend is a genuine Expo (expo-router) project (app.json, expo deps) — the platform provisions the **expo_mongo mobile template**, even when the user selects "Full Stack Web". Reproduced 2/2 on independent jobs with the identical image tag → deterministic classifier behavior, not a random glitch.
2. Nothing inside the repository controls this: config.json is absent/ignored, and .emergent/emergent.yml is platform-generated and REGENERATED at publish time (editing it is futile).
3. Consequence chain: Expo template → Expo MOBILE publish pipeline → deploys FastAPI backend + publishes Metro bundle for Expo Go/QR → no web export, no static HTML serving → deployed web root = backend 404 → the deployed product is unusable as a website even though the publish "succeeded" and the API is healthy.
4. The app CODE remains deployment-clean for a WEB pipeline (hardened `yarn build` export verified EXIT:0 previously; 120 pre-rendered HTML pages in dist/server; build/ provided in CRA-convention layout precisely for standard web pipelines).

## Checkpoint C — Actions taken / remediation paths
- No blind code changes (would be fake fixes for a platform provisioning issue).
- support_agent escalation issued with both job IDs + evidence (response relayed to user verbatim in chat).
- Remediation options presented to user for decision:
  (P1 — platform, correct fix) Support switches this job (6588e690…) to the Full Stack WEB deployment pipeline, or provisions a true Full Stack Web job for this repo. Only the platform can do this.
  (P2 — in-repo mitigation, works even on the mobile pipeline) Make FastAPI serve the pre-rendered web build: mount dist/client assets + catch-all mapping path → dist/server/<path>.html for non-/api routes; ensure dist is present in the deploy image (commit it or build at image start). Deployed host would then serve the full web platform despite mobile pipeline labeling.
  (P3 — hygiene) Optionally un-ignore .env per deployment_agent guidance (user decision; secrets tradeoff).

## Checkpoint D — Honest verdict
1. Did the user's code cause this? NO. Same repo, two fresh jobs, same wrong template — provisioning is platform-side and content-driven.
2. Is the deployed app functional? PARTIALLY: API healthy (200), WEB UI completely absent (root 404). As a web platform, the deployment is NOT functional.
3. Can the agent fully fix it from inside the repo? Not the classification itself; only mitigation P2 can make the web app servable under the mobile pipeline.
4. Preview environment unaffected: frontend 200 + API 200 + all regression suites passed earlier this session.
