# Job Template Mismatch RCA (Full Stack selected, Expo provisioned) — Checkpoints A–D (2026-07-16)

Task: user asserts this job was created with the "Full Stack App" template and was never built for a Mobile App; asked for honest root cause of deployment failure at global system level.

## Checkpoint A — Environment identity evidence
- /app/.emergent/emergent.yml → env_image_name: "expo_mongo_base_image_cloud_arm:release-11022026-1" (EXPO+Mongo base image; job_id 22957321-afe5-4e3a-a232-116e4e47efa6; file regenerated at deploy-attempt time)
- /app/config.json: missing/empty — no app-level environment override exists
- Supervisor service definition: `yarn expo start --tunnel --port 3000` (Expo template service)
- deployment_agent classification on all 3 runs: "Expo mobile app detected"
- Deploy failure: PullSource → deployer's Expo dynamic_manifest path → Dockerfile template for the expo_mongo base image tag missing in GCS ("storage: object doesn't exist")

## Checkpoint B — Root cause
JOB-LEVEL TEMPLATE MISMATCH. The user selected Full Stack App, but the pod was provisioned on the Expo (mobile) base image. Consequently the deployer routes deployment through the Expo pipeline, whose GCS Dockerfile template for expo_mongo_base_image_cloud_arm:release-11022026-1 does not exist → hard failure before any app code is read. All of this metadata is server-side/platform-generated; nothing in the repo controls it. The app code itself is deployment-clean (static checks pass, yarn build EXIT:0, build/ produced in CRA-convention layout specifically for standard web pipelines).

## Checkpoint C — Actions taken
- No code changes (none applicable; would be fake fixes).
- support_agent consulted: confirmed platform-level provisioning issue requiring support intervention. Options: (1) support switches this job to the Full Stack web deployment pipeline, or (2) user creates a new job with the Full Stack template and re-imports the GitHub repo. Contact: support@emergent.sh with job ID + evidence.

## Checkpoint D — Honest verdict
1. Is RealAICoach a full-stack platform? YES — verified live: FastAPI backend (3,417 /api endpoints), MongoDB (250+ collections), web frontend (219 expo-router routes compiled to a static/SSG WEB build), auth E2E verified in UI, production build proven EXIT:0.
2. Is this JOB a "Full Stack App" job? NO — despite the user's selection, the environment is provably the Expo template (env_image_name + supervisor + pipeline classification above).
3. Is it ready for deployment? The CODE is deployment-ready; the JOB cannot deploy until the platform corrects the template/pipeline mismatch (or the repo is re-imported into a properly provisioned Full Stack job).
- App health at close: backend/expo/mongodb RUNNING, /api/health 200, preview 200 (testing agent smoke 5/5 earlier this session).
