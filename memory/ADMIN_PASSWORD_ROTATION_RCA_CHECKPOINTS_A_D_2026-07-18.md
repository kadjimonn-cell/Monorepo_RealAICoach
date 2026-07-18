# RCA: "Rotated admin password in Secrets tab, but old password still works" — Checkpoints A-D
Date: 2026-07-18 · Env: preview (user observed on production realaicoach.app)

## Checkpoint A/B — Root cause (verified in code)
Trace: `ADMIN_PASSWORD` env → `ADMIN_SEED_PASSWORD` (routes/db.py:39, read at import) →
`ensure_admin_users()` (db.py:496) ← called by `create_db_indexes` ← deferred-init step
`db_indexes_and_platform_init` (server.py:3226) — runs on EVERY backend boot.

Finding: the original hypothesis ("env only seeds, never rewrites") was WRONG for this codebase.
The code ALREADY rewrote the stored bcrypt hash whenever it differed from ADMIN_PASSWORD (always-on).
Therefore the outage layer is DEPLOYMENT MECHANICS, not code:
1. Panel (Secrets tab) changes do NOT reach the running production container. They apply only on the
   next **Re-publish** — until then the process keeps its old env, so `ensure_admin_users` still sees
   the OLD value and the old password keeps working.
2. Preview reads /app/backend/.env, not panel values — a panel change never affects preview at all.
3. Additionally the env is read at module import, so even in preview a .env edit requires a backend restart.

Hidden flaw found during the trace: the always-on rewrite silently REVERTED any in-app admin password
change on the next restart (change-password flow existed at routes/auth.py:3975 but couldn't stick).

## Checkpoint C — Fix (minimal, routes/db.py ensure_admin_users)
- Initial seeding (account exists but has NO password_hash, e.g. SSO-registered): still automatic (safe).
- Rewriting an EXISTING hash from env is now OPT-IN: `ADMIN_PASSWORD_ENFORCE_SYNC=true|1|yes`
  (read at call time). Default OFF -> boot logs "differs from ADMIN_PASSWORD env; sync SKIPPED".
  Enabled -> rewrites hash, stamps admin_seed_password_rotated_at, logs "rotated from ADMIN_PASSWORD env".
- No plaintext passwords in any log line (verified by grep over full log corpus: 0 hits).

## Checkpoint D — Verification evidence (preview)
1. Baseline login (current pw): 200
2. .env ADMIN_PASSWORD=<new> + ENFORCE_SYNC=true, restart -> "rotated" log; OLD pw 401, NEW pw 200 ✔
3. .env ADMIN_PASSWORD=<decoy> + ENFORCE_SYNC=false, restart -> "sync SKIPPED" log; stored pw 200, decoy 401 ✔
4. Reverted: original ADMIN_PASSWORD restored via one ENFORCE_SYNC=true boot, then flag set false.
   Final state: original credentials work (200), /api/health 200, flag=false in preview .env.
5. Regression: /app/test_reports/iteration_12.json — 6/6 pass (web cookie auth, wrong-pw 401, /auth/me,
   native Bearer contract, scaling status, log hygiene).

## User runbook — make rotation take effect in PRODUCTION
Option 1 (env-driven, needs deploy): in the deployment panel Secrets set
  ADMIN_PASSWORD=<new password>  and  ADMIN_PASSWORD_ENFORCE_SYNC=true
then **Re-publish**. After it's live, verify old password rejected, then (recommended) set
ADMIN_PASSWORD_ENFORCE_SYNC=false and re-publish again (or leave off until next rotation) so future
in-app changes are never overwritten.
Option 2 (no deploy): log in and use the in-app change-password flow (POST /api/auth/change-password).
With this fix the change now PERSISTS across restarts (previously it was silently reverted).

## Side observation (unrelated, flagged by regression)
llm_circuit_breaker is currently paused=true (3 real consecutive upstream LLM failures) — the breaker
working as designed. Re-arm via POST /api/admin/scaling/rearm after checking the LLM key/balance.
