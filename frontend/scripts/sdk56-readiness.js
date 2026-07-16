#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const frontendRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendRoot, '..');
const packageJsonPath = path.join(frontendRoot, 'package.json');
const reportPath = path.join(repoRoot, 'memory', 'tickets', 'P2_SDK56_READINESS.md');

function run(cmd, args, cwd = frontendRoot) {
  return spawnSync(cmd, args, {
    cwd,
    encoding: 'utf-8',
    env: process.env,
    timeout: 300000,
  });
}

function npmView(spec) {
  const res = run('npm', ['view', spec, 'version']);
  if (res.status !== 0) return null;
  const value = (res.stdout || '').trim();
  return value || null;
}

function trimOutput(text, max = 600) {
  const raw = String(text || '').trim();
  if (!raw) return '';
  return raw.length > max ? `${raw.slice(0, max)}...` : raw;
}

function main() {
  const pkg = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
  const currentExpo = pkg.dependencies?.expo || pkg.devDependencies?.expo || 'not-installed';

  const stable56 = npmView('expo@~56.0.0');
  const canary56 = npmView('expo@canary');

  const checkRes = run('npx', ['expo', 'install', '--check']);
  const doctorRes = run('npx', ['expo-doctor']);
  const checkOutput = `${checkRes.stdout || ''}\n${checkRes.stderr || ''}`;
  const lowerCheckOutput = checkOutput.toLowerCase();
  const checkUnsupported = (lowerCheckOutput.includes('unknown option') && lowerCheckOutput.includes('--check'))
    || lowerCheckOutput.includes('legacy expo-cli');
  const checkPass = checkUnsupported ? doctorRes.status === 0 : checkRes.status === 0;

  const blockers = [];
  if (!stable56) {
    blockers.push('Stable `expo@~56.0.0` is not published in npm registry yet (external blocker).');
  }
  if (!checkUnsupported && checkRes.status !== 0) {
    blockers.push('`npx expo install --check` reports dependency alignment issues (internal hygiene blocker).');
  }
  if (doctorRes.status !== 0) {
    blockers.push('`npx expo-doctor` still reports non-zero exit (internal hygiene blocker).');
  }

  const now = new Date().toISOString();
  const markdown = [
    '# P2 SDK 56 Readiness Report',
    '',
    `Generated: ${now}`,
    '',
    '## Current state',
    `- Current Expo dependency: \`${currentExpo}\``,
    `- SDK 56 stable on npm: ${stable56 ? `✅ ${stable56}` : '❌ Not available'}`,
    `- SDK 56 canary on npm: ${canary56 ? `ℹ️ ${canary56}` : 'Not found'}`,
    `- Dependency alignment check (expo install --check): ${checkPass ? '✅ pass' : '❌ fail'}${checkUnsupported ? ' (CLI fallback to expo-doctor)' : ''}`,
    `- Expo doctor: ${doctorRes.status === 0 ? '✅ pass' : '❌ fail'}`,
    '',
    '## Blockers',
    ...(blockers.length ? blockers.map((b) => `- ${b}`) : ['- None.']),
    '',
    '## Command outputs (trimmed)',
    '### npx expo install --check',
    '```',
    trimOutput(checkRes.stdout || checkRes.stderr || 'no output'),
    '```',
    '',
    '### npx expo-doctor',
    '```',
    trimOutput((doctorRes.stdout || '') + '\n' + (doctorRes.stderr || ''), 1500) || 'no output',
    '```',
    '',
    '## Execution decision',
    stable56
      ? '- Stable SDK 56 is available. Proceed with coordinated major upgrade commands.'
      : '- Stable SDK 56 is NOT available. Keep project on latest stable SDK 55 baseline and re-run this readiness check periodically.',
    '',
    '## Next actions',
    '- If/when stable SDK 56 publishes, run: `npx expo install expo@~56.0.0 && npx expo install --fix && npx expo-doctor && yarn export:web`.',
    '- Keep canary adoption optional and gated (do not promote to production without explicit approval).',
  ].join('\n');

  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, markdown, 'utf-8');

  console.log(`[sdk56-readiness] report written: ${reportPath}`);
  if (blockers.length) {
    console.log(`[sdk56-readiness] blockers: ${blockers.length}`);
  } else {
    console.log('[sdk56-readiness] no blockers detected.');
  }
}

main();
