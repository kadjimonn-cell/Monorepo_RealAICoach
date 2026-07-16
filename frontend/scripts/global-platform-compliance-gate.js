#!/usr/bin/env node
/* eslint-env node */

/**
 * Global Platform Compliance Gate (non-regression)
 *
 * Runs global frontend compliance checks across:
 * - v2 theme (build gate + warn ratchet)
 * - i18n (route hardcopy + missing-key regression)
 * - v7 boundary isolation
 * - responsiveness/layout non-regression + viewport contracts
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const scriptDir = path.dirname(path.resolve(process.argv[1] || 'scripts/global-platform-compliance-gate.js'));
const FRONTEND_ROOT = path.resolve(scriptDir, '..');
const REPORT_DIR = path.resolve(FRONTEND_ROOT, '.quality');
const REPORT_FILE = path.resolve(REPORT_DIR, 'global_platform_compliance_report.json');

const UPDATE_BASELINES = process.argv.includes('--update-baselines');

function runStep(name, command, args = []) {
  const res = spawnSync(command, args, {
    cwd: FRONTEND_ROOT,
    encoding: 'utf-8',
    env: process.env,
    timeout: 120000,
    killSignal: 'SIGKILL',
  });

  if ((res.stdout || '').trim()) process.stdout.write(res.stdout);
  if ((res.stderr || '').trim()) process.stderr.write(res.stderr);

  return {
    name,
    status: (res.status === 0 && !res.error) ? 'PASS' : 'FAIL',
    exit_code: Number(res.status || 0),
    error: res.error ? String(res.error.message || res.error) : null,
  };
}

function writeReport(payload) {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function main() {
  const started = new Date().toISOString();
  const steps = [];

  steps.push(runStep('theme-build-gate', 'node', ['scripts/theme-build-gate.js']));
  if (steps[steps.length - 1].status === 'FAIL') {
    const payload = {
      generated_at: new Date().toISOString(),
      started_at: started,
      mode: UPDATE_BASELINES ? 'update-baselines' : 'gate',
      status: 'FAIL',
      failed_step: 'theme-build-gate',
      steps,
    };
    writeReport(payload);
    process.exit(1);
  }

  if (UPDATE_BASELINES) {
    steps.push(runStep('theme-warning-ratchet-baseline-update', 'node', ['scripts/theme-warning-ratchet-gate.js', '--update-baseline']));
    steps.push(runStep('i18n-missing-baseline-update', 'node', ['scripts/i18n-new-missing-keys-check.js', '--update-baseline']));
    steps.push(runStep('layout-baseline-update', 'node', ['scripts/layout-validation-gate.js', '--update-baseline']));
  }

  if (!UPDATE_BASELINES) {
    steps.push(runStep('theme-warning-ratchet-gate', 'node', ['scripts/theme-warning-ratchet-gate.js']));
    steps.push(runStep('i18n-route-hardcopy-gate', 'node', ['scripts/i18n-route-hardcopy-gate.js']));
    steps.push(runStep('i18n-missing-keys-regression-gate', 'node', ['scripts/i18n-new-missing-keys-check.js']));
    steps.push(runStep('critical-surface-i18n-gate', 'node', ['scripts/critical-surface-i18n-gate.js']));
    steps.push(runStep('v7-platform-boundary-gate', 'node', ['scripts/v7-platform-boundary-gate.js']));
    steps.push(runStep('layout-validation-regression-gate', 'node', ['scripts/layout-validation-gate.js', '--regression']));
    steps.push(runStep('admin-dashboard-viewport-guard', 'node', ['scripts/admin-dashboard-viewport-guard.js']));
    steps.push(runStep('payment-picker-viewport-guard', 'node', ['scripts/payment-picker-viewport-guard.js']));
    steps.push(runStep('footer-route-contract-gate', 'node', ['scripts/footer-route-contract-gate.js']));
    steps.push(runStep('ui-contract-gate', 'node', ['scripts/ui-contract-gate.js']));
  }

  const failed = steps.find((s) => s.status === 'FAIL');
  const payload = {
    generated_at: new Date().toISOString(),
    started_at: started,
    mode: UPDATE_BASELINES ? 'update-baselines' : 'gate',
    status: failed ? 'FAIL' : 'PASS',
    failed_step: failed ? failed.name : null,
    steps,
  };

  writeReport(payload);
  console.log(`[global-platform-compliance-gate] report=${REPORT_FILE}`);

  if (failed) {
    console.error(`[global-platform-compliance-gate] FAIL at step: ${failed.name}`);
    process.exit(1);
  }

  console.log('[global-platform-compliance-gate] PASS');
}

main();
