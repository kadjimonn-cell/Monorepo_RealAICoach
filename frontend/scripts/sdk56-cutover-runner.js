#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const frontendRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendRoot, '..');
const reportPath = path.join(repoRoot, 'memory', 'tickets', 'P4_SDK56_CUTOVER_RUNNER_LAST_RUN.md');

function run(cmd, args, cwd = frontendRoot) {
  const res = spawnSync(cmd, args, {
    cwd,
    encoding: 'utf-8',
    env: process.env,
    timeout: 600000,
  });
  return {
    command: `${cmd} ${args.join(' ')}`,
    status: res.status,
    stdout: String(res.stdout || '').trim(),
    stderr: String(res.stderr || '').trim(),
  };
}

function npmView(versionSpec) {
  const res = run('npm', ['view', versionSpec, 'version']);
  if (res.status !== 0) return null;
  const value = res.stdout.trim();
  return value || null;
}

function clip(value, max = 1200) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return raw.length > max ? `${raw.slice(0, max)}...` : raw;
}

function writeReport(lines) {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, `${lines.join('\n')}\n`, 'utf-8');
}

function main() {
  const now = new Date().toISOString();
  const stable56 = npmView('expo@~56.0.0');

  if (!stable56) {
    writeReport([
      '# SDK56 Cutover Runner',
      '',
      `Last run: ${now}`,
      '',
      '## Result',
      '- SKIPPED: stable `expo@~56.0.0` is not available on npm.',
      '- No cutover actions executed.',
      '',
      '## Next',
      '- Re-run `yarn sdk56:cutover:auto` later.',
    ]);
    console.log('[sdk56-cutover] stable expo@~56.0.0 not available, skipped.');
    console.log(`[sdk56-cutover] report: ${reportPath}`);
    process.exit(0);
  }

  const steps = [
    run('npx', ['expo', 'install', 'expo@~56.0.0']),
    run('npx', ['expo', 'install', '--fix']),
    run('npx', ['expo-doctor']),
    run('yarn', ['export:web']),
    run('python', ['-m', 'pytest', '/app/backend/tests/test_p0_p1_regression.py', '-q'], '/app/backend'),
  ];

  const failed = steps.find((s) => s.status !== 0);

  const report = [
    '# SDK56 Cutover Runner',
    '',
    `Last run: ${now}`,
    '',
    '## Detection',
    `- Detected stable SDK56: ${stable56}`,
    '',
    '## Steps',
    ...steps.flatMap((s, i) => [
      `### ${i + 1}. ${s.command}`,
      `- exit_code: ${s.status}`,
      '```',
      clip(s.stdout || s.stderr || 'no output'),
      '```',
      '',
    ]),
    '## Final status',
    failed
      ? `- FAILED at step: \`${failed.command}\``
      : '- SUCCESS: SDK56 cutover + post-cutover P0 regression tests completed.',
  ];

  writeReport(report);
  console.log(`[sdk56-cutover] report: ${reportPath}`);
  if (failed) process.exit(1);
  process.exit(0);
}

main();
