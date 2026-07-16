#!/usr/bin/env node
/**
 * Pre-build guard: verifies that the package.json scripts required by the
 * supervisor config (and by CI) actually resolve to the LOCAL expo CLI
 * rather than a global `expo` binary that may not exist in the pod.
 *
 * Why this file exists
 * --------------------
 * On 2026-04-24 we had a silent regression where `"start": "expo start"`
 * was shipped without a `"expo"` script and without a global `expo`
 * binary installed. The supervisor's `yarn expo start` call failed with
 * `error Command "expo" not found.` — Metro never booted — the mobile
 * Expo Go preview rendered an infinite black-screen spinner for hours
 * before it was noticed.
 *
 * This script runs as part of `yarn export:web` (web production build)
 * and any CI pipeline so a broken package.json is caught BEFORE it reaches
 * the pod. Failure exit code is non-zero so the build halts loudly.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const PKG = path.resolve(__dirname, '..', 'package.json');
const LOCAL_CLI = 'node_modules/expo/bin/cli';

/**
 * Scripts that MUST exist and route to the local expo CLI.
 * Keyed by script name → array of substrings any of which must appear in
 * the value. This guards against `"expo start"` (global) but allows
 * `"node node_modules/expo/bin/cli start"` (local) and yarn-workspace
 * variants.
 */
const REQUIRED_LOCAL = {
  start: [LOCAL_CLI],
};

function main() {
  if (!fs.existsSync(PKG)) {
    console.error('[verify-package-json] package.json not found at', PKG);
    process.exit(2);
  }

  let pkg;
  try {
    pkg = JSON.parse(fs.readFileSync(PKG, 'utf8'));
  } catch (err) {
    console.error('[verify-package-json] package.json is not valid JSON:', err.message);
    process.exit(2);
  }

  const scripts = pkg.scripts || {};
  const problems = [];

  for (const [name, mustInclude] of Object.entries(REQUIRED_LOCAL)) {
    const value = scripts[name];
    if (!value) {
      problems.push(`✗ scripts["${name}"] is MISSING — add it so \`yarn ${name}\` routes to ${LOCAL_CLI}`);
      continue;
    }
    const hasAllowedTarget = mustInclude.some((needle) => value.includes(needle));
    if (!hasAllowedTarget) {
      problems.push(
        `✗ scripts["${name}"] = "${value}" — expected to include "${LOCAL_CLI}" ` +
        `(supervisor runs \`yarn ${name}\` which fails if ${name} resolves to a global \`expo\` binary that isn't installed in the pod)`,
      );
    }
  }

  // Optional script: if an explicit "expo" script is present, ensure it also
  // resolves to the local CLI. If absent, `yarn expo` can still resolve via
  // node_modules/.bin/expo and that is acceptable.
  if (scripts.expo) {
    const value = scripts.expo;
    if (!value.includes(LOCAL_CLI)) {
      problems.push(
        `✗ scripts["expo"] = "${value}" — expected to include "${LOCAL_CLI}" when present. ` +
        'Either delete scripts["expo"] to use yarn bin resolution, or point it to the local CLI.',
      );
    }
  }

  // Also verify the `expo` package is installed as a local dependency —
  // the CLI ships inside the `expo` package.
  const depVersion = (pkg.dependencies && pkg.dependencies.expo) || (pkg.devDependencies && pkg.devDependencies.expo);
  if (!depVersion) {
    problems.push('✗ "expo" is not listed as a dependency — install it with `yarn add expo`');
  } else {
    if (/^[~^><*]/.test(String(depVersion).trim())) {
      problems.push(`✗ expo version must be exact pinned (found "${depVersion}") — use "54.0.34"`);
    }
    const cliPath = path.resolve(__dirname, '..', LOCAL_CLI);
    if (!fs.existsSync(cliPath)) {
      problems.push(`✗ expo@${depVersion} is in dependencies but ${LOCAL_CLI} does not exist — run \`yarn install\``);
    }
  }

  if (problems.length === 0) {
    console.log('[verify-package-json] ✓ all required scripts resolve to the local expo CLI');
    process.exit(0);
  }

  console.error('');
  console.error('[verify-package-json] BUILD GUARD FAILED — package.json scripts are broken:');
  for (const p of problems) console.error('  ' + p);
  console.error('');
  console.error('  Required scripts:');
  for (const [name, needles] of Object.entries(REQUIRED_LOCAL)) {
    console.error(`    "${name}": "node ${LOCAL_CLI}${name === 'start' ? ' start' : ''}"`);
  }
  console.error('');
  process.exit(1);
}

main();
