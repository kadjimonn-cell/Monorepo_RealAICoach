#!/usr/bin/env node
/* eslint-env node */

/**
 * Runs i18n seed script in best-effort mode.
 *
 * Why: frontend build environments may not always have backend-only Python
 * deps installed (e.g., motor). We still want export to continue while
 * logging the seed issue clearly.
 */

const { spawnSync } = require('child_process');
const path = require('path');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/i18n-seed-safe.js'));
const frontendRoot = path.resolve(scriptDir, '..');
const seedScript = path.resolve(frontendRoot, '../scripts/i18n_v2_seed_locales.py');
const stripTagsScript = path.resolve(frontendRoot, 'scripts/i18n-strip-language-tags.js');
const routeHardcopyGateScript = path.resolve(frontendRoot, 'scripts/i18n-route-hardcopy-gate.js');
const criticalSurfaceGateScript = path.resolve(frontendRoot, 'scripts/critical-surface-i18n-gate.js');
const v7PlatformBoundaryGateScript = path.resolve(frontendRoot, 'scripts/v7-platform-boundary-gate.js');
const i18nMissingRegressionScript = path.resolve(frontendRoot, 'scripts/i18n-new-missing-keys-check.js');
const layoutRegressionScript = path.resolve(frontendRoot, 'scripts/layout-validation-gate.js');
const adminViewportGuardScript = path.resolve(frontendRoot, 'scripts/admin-dashboard-viewport-guard.js');
const footerRouteContractGateScript = path.resolve(frontendRoot, 'scripts/footer-route-contract-gate.js');
const uiContractGateScript = path.resolve(frontendRoot, 'scripts/ui-contract-gate.js');

function runRouteHardcopyGate() {
  const gateRes = spawnSync('node', [routeHardcopyGateScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] route hardcopy gate failed:', gateErr);
    process.exit(1);
  }
}

function runCriticalSurfaceGate() {
  const gateRes = spawnSync('node', [criticalSurfaceGateScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] critical surface i18n gate failed:', gateErr);
    process.exit(1);
  }
}

function runV7PlatformBoundaryGate() {
  const gateRes = spawnSync('node', [v7PlatformBoundaryGateScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] v7 platform boundary gate failed:', gateErr);
    process.exit(1);
  }
}

function runI18nMissingRegressionGate() {
  const gateRes = spawnSync('node', [i18nMissingRegressionScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] i18n missing-key regression gate failed:', gateErr);
    process.exit(1);
  }
}

function runLayoutRegressionGate() {
  const gateRes = spawnSync('node', [layoutRegressionScript, '--regression'], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] layout regression gate failed:', gateErr);
    process.exit(1);
  }
}

function runAdminViewportGuard() {
  const gateRes = spawnSync('node', [adminViewportGuardScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] admin viewport guard failed:', gateErr);
    process.exit(1);
  }
}

function runUIContractGate() {
  const gateRes = spawnSync('node', [uiContractGateScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] ui-contract gate failed:', gateErr);
    process.exit(1);
  }
}

function runFooterRouteContractGate() {
  const gateRes = spawnSync('node', [footerRouteContractGateScript], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });

  if ((gateRes.stdout || '').trim()) console.log((gateRes.stdout || '').trim());
  if (gateRes.status !== 0 || gateRes.error) {
    const gateErr = (gateRes.stderr || '').trim() || gateRes.error?.message || `exit=${gateRes.status}`;
    console.error('[i18n-seed-safe] footer route contract gate failed:', gateErr);
    process.exit(1);
  }
}

function runGlobalComplianceSubset() {
  runRouteHardcopyGate();
  runCriticalSurfaceGate();
  runV7PlatformBoundaryGate();
  runI18nMissingRegressionGate();
  runLayoutRegressionGate();
  runAdminViewportGuard();
  runFooterRouteContractGate();
  runUIContractGate();
}

const res = spawnSync('python3', [seedScript], {
  cwd: frontendRoot,
  encoding: 'utf-8',
  env: process.env,
  timeout: 45000,
  killSignal: 'SIGKILL',
});

if (res.status === 0 && !res.error) {
  const sanitizeRes = spawnSync('node', [stripTagsScript, '--write'], {
    cwd: frontendRoot,
    encoding: 'utf-8',
    env: process.env,
    timeout: 45000,
    killSignal: 'SIGKILL',
  });
  if (sanitizeRes.status !== 0 || sanitizeRes.error) {
    const sanitizeErr = (sanitizeRes.stderr || '').trim() || sanitizeRes.error?.message || `exit=${sanitizeRes.status}`;
    console.error('[i18n-seed-safe] locale tag sanitization failed:', sanitizeErr);
    process.exit(1);
  }
  const sanitizeOut = (sanitizeRes.stdout || '').trim();
  if (sanitizeOut) console.log(sanitizeOut);
  runGlobalComplianceSubset();
  console.log('[i18n-seed-safe] locale seed completed with strict tag sanitization.');
  process.exit(0);
}

if (res.error && res.error.code === 'ETIMEDOUT') {
  console.warn('[i18n-seed-safe] non-blocking seed skip: timeout after 45s');
  process.exit(0);
}

const stderr = (res.stderr || '').trim();
const first = stderr.split('\n').find(Boolean) || `exit=${res.status}`;
console.warn('[i18n-seed-safe] non-blocking seed skip:', first);
runGlobalComplianceSubset();
process.exit(0);
