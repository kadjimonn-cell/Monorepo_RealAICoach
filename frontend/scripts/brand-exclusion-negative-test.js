#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const REPORT_DIR = path.join(ROOT, '.quality');
const PROOF_PATH = path.join(REPORT_DIR, 'brand_exclusion_negative_proof.json');

function runGate(args = []) {
  return spawnSync('node', ['scripts/brand-exclusion-gate.js', ...args], {
    cwd: ROOT,
    encoding: 'utf8',
  });
}

function main() {
  if (!fs.existsSync(REPORT_DIR)) fs.mkdirSync(REPORT_DIR, { recursive: true });

  const baseline = runGate();
  const negative = runGate(['--with-negative-fixture']);

  const proof = {
    generated_at: new Date().toISOString(),
    baseline: {
      exit_code: baseline.status,
      pass_expected: true,
      pass_actual: baseline.status === 0,
      stdout: (baseline.stdout || '').trim().split('\n').slice(-6),
      stderr: (baseline.stderr || '').trim().split('\n').slice(-6),
    },
    negative_fixture: {
      exit_code: negative.status,
      fail_expected: true,
      fail_actual: negative.status !== 0,
      stdout: (negative.stdout || '').trim().split('\n').slice(-10),
      stderr: (negative.stderr || '').trim().split('\n').slice(-10),
    },
  };

  fs.writeFileSync(PROOF_PATH, JSON.stringify(proof, null, 2));

  const ok = proof.baseline.pass_actual && proof.negative_fixture.fail_actual;
  if (!ok) {
    console.error('[brand-exclusion-negative-test] FAILED');
    console.error(` - Proof: ${PROOF_PATH}`);
    process.exit(1);
  }

  console.log('[brand-exclusion-negative-test] PASS');
  console.log(` - Proof: ${PROOF_PATH}`);
}

main();
