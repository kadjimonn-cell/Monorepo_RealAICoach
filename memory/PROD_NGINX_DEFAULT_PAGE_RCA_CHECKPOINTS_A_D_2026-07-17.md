# Production "Welcome to nginx!" RCA — Checkpoints A–D (2026-07-17)

Task: root-cause and fix production (Publish 11, Live) serving the default nginx page at
https://realaicoach.app instead of the app. Code-level only; no docker/nginx changes.

## Checkpoint A — Baseline evidence
- realaicoach.app -> stock "Welcome to nginx!" page; backend boots (nginx proxied /health
  to 127.0.0.1:8001; Lighthouse auditor ran in deployed logs).
- /app/frontend/build (the tree the fullstack platform's nginx serves statically) contained
  NO root index.html: the old `build` script copied dist/ VERBATIM, leaving HTML only at
  build/server/**.html and assets at build/client/**.
- app.json: expo web.output = "server" -> `expo export` emits dist/server/ (215 pre-rendered
  route HTML pages) + dist/client/ (JS bundles/assets) — a layout that requires a Node
  server runtime, which production does not run for the frontend.
- Old spotify-style-2 deployment ran on the EXPO platform template (publish pipeline
  understands the server-mode layout natively); THIS job uses the FULLSTACK template
  (static nginx serving of build/). Template change = serving-contract change.

## Checkpoint B — Root cause
- Build output layout mismatch (hypothesis 1 confirmed): production nginx serves
  /app/frontend/build as plain static files; with no build/index.html it falls back to the
  default nginx site. Not a build failure (BUILD_EXIT:0), not a backend failure.
- Asset references in the pre-rendered HTML are root-relative ("/_expo/...", "/manifest.json"),
  so a purely static assembly is viable without a Node server.

## Checkpoint C — Implementation (code-level)
- NEW /app/frontend/scripts/assemble-static-build.js:
  build/ := dist/client (assets) + all route HTML from dist/server (skips server _expo),
  mirrors every "X.html" to "X/index.html" (+ .br/.gz variants) for nginx directory-index
  resolution, writes 200.html/404.html fallbacks, hard-fails if dist/server/index.html missing.
- package.json "build" := `yarn export:web && node scripts/assemble-static-build.js`
  (verify-package-json gate passes; `start` Metro flow untouched; app.json web.output
  intentionally unchanged).

## Checkpoint D — Final evidence
- Full `yarn build`: EXIT:0 in 364.05s -> "215 route HTML pages (+204 directory-index
  mirrors); root index.html OK".
- Static-serving simulation (python http.server on build/): "/", "/pricing/", "/features/",
  "/auth/" all 200 with RealAICoach content; entry JS bundle /_expo/static/js/web/*.js 200.
- Preview regression: Metro dev server 200, /api/health 200, admin login 200,
  import_bringup suite 7/7. Independently verified by testing_agent iteration_7 (100%).
- Action: user must Re-publish so the production image rebuilds with the new assembler.
