import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const changedFileListPath = process.argv[2];

if (!changedFileListPath || !fs.existsSync(changedFileListPath)) {
  console.error('Missing changed-file list path.');
  process.exit(1);
}

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const frontendRoot = path.join(repoRoot, 'frontend');

const changedFiles = fs
  .readFileSync(changedFileListPath, 'utf8')
  .split('\n')
  .map((line) => line.trim())
  .filter(Boolean)
  .filter((file) => file.startsWith('frontend/'))
  .filter((file) => /\.(js|jsx|ts|tsx|mjs|cjs)$/.test(file));

if (changedFiles.length === 0) {
  console.log('No frontend JS/TS files changed in this PR. Lint gate skipped.');
  process.exit(0);
}

const relativeToFrontend = (file) => file.replace(/^frontend\//, '');
const allFrontendFiles = changedFiles.map(relativeToFrontend);

const isNonAdminFile = (file) => {
  const rel = relativeToFrontend(file);
  if (rel.startsWith('src/components/admin/')) return false;
  if (rel.startsWith('app/admin/')) return false;
  if (rel === 'app/executive-dashboard.tsx') return false;
  if (rel === 'app/admin-system.tsx') return false;
  if (rel === 'app/(tabs)/admin-console.tsx') return false;
  return true;
};

const nonAdminFiles = changedFiles.filter(isNonAdminFile).map(relativeToFrontend);

const runEslintJson = (files) => {
  if (!files.length) {
    return { errors: 0, warnings: 0, output: '[]' };
  }

  const result = spawnSync('npx', ['eslint', '--format', 'json', ...files], {
    cwd: frontendRoot,
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
  });

  const raw = (result.stdout || '').trim();
  let parsed = [];
  try {
    parsed = raw ? JSON.parse(raw) : [];
  } catch {
    console.error('Failed to parse ESLint JSON output.');
    console.error(result.stdout || result.stderr || 'No output');
    process.exit(1);
  }

  const errors = parsed.reduce((sum, entry) => sum + (entry.errorCount || 0), 0);
  const warnings = parsed.reduce((sum, entry) => sum + (entry.warningCount || 0), 0);
  return { errors, warnings, output: raw };
};

const globalRun = runEslintJson(allFrontendFiles);
if (globalRun.errors > 0) {
  console.error(`Lint gate failed: ${globalRun.errors} new ESLint error(s) in changed frontend files.`);
  process.exit(1);
}

const nonAdminRun = runEslintJson(nonAdminFiles);
if (nonAdminRun.warnings > 0) {
  console.error(`Lint gate failed: ${nonAdminRun.warnings} new warning(s) in changed non-admin frontend files.`);
  process.exit(1);
}

console.log(`Lint gate passed. Checked ${allFrontendFiles.length} changed frontend file(s).`);
